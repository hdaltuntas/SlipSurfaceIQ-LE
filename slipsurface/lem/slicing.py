"""Vertical slicing of a slipping mass.

Slice boundaries: `n_slices` equal-width slices between exit and entry,
plus extra boundaries at every ground-surface, water-table and polyline
surface vertex inside the mass, so the top of each slice is straight.

Weight: each slice column (base -> ground at slice mid-x) is sampled at
`n_sub` points; each sample takes the unit weight of the region that
contains it (gamma above the water table, gamma_sat below). One vectorized
point-in-polygon query per region handles any number of materials.

Pore pressure at the base (per base material, Slide2-style):
  water_table : u = Hu * gamma_w * (y_wt - y_base)  (if the material uses water)
  ru          : u = ru * sigma_v  (sigma_v = W / b, total vertical stress)
  none        : u = 0

Ponded water: where the water table lies above the ground surface (ponded /
submerged ground), the weight of the water column over the slice top is added
to the slice weight. Base pore pressure already uses the full piezometric head.

Seismic (pseudo-static): horizontal force Fh = kh W acting in the sliding
direction at the column centroid; vertical coefficient kv (positive upward)
gives the vertical load Wv = (1 - kv) W.

Sign convention: solvers assume the mass moves toward -x ("right to left",
Slide2 default) with alpha > 0 where the base rises to the right. A
left-to-right failure is handled by mirroring (alphas negated,
`direction` = +1). The failure direction is detected from sum(W sin a)
unless forced.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np
import shapely

from slipsurface.geometry import SlipSurface, SlopeGeometry, slip_extent
from slipsurface.materials import Material

if TYPE_CHECKING:
    from slipsurface.loads import LoadSet, TensionCrack

GAMMA_W = 9.81  # kN/m3


@dataclass
class SliceOptions:
    n_slices: int = 30
    n_sub: int = 24
    gamma_w: float = GAMMA_W
    pore: str = "water_table"          # water_table | ru | none
    ru: float = 0.0
    kh: float = 0.0
    kv: float = 0.0
    direction: str = "auto"            # auto | right_to_left | left_to_right
    min_depth: float = 0.0             # reject masses thinner than this [m]
    loads: LoadSet | None = None     # slipsurface.loads.LoadSet
    crack: TensionCrack | None = None  # slipsurface.loads.TensionCrack


@dataclass
class SliceSet:
    xl: np.ndarray        # left edge x
    xr: np.ndarray        # right edge x
    xm: np.ndarray        # mid x
    b: np.ndarray         # width
    y_base: np.ndarray    # base elevation at mid
    y_top: np.ndarray     # ground elevation at mid
    alpha: np.ndarray     # base inclination [rad] (solver frame)
    l: np.ndarray         # base length
    W: np.ndarray         # weight [kN/m]
    u: np.ndarray         # pore pressure at base mid [kPa]
    mat_idx: np.ndarray   # index into `materials` for the base material
    materials: list[Material]
    surface: SlipSurface
    x_exit: float         # left end of the mass
    x_entry: float        # right end of the mass
    direction: int = -1   # -1: mass moves toward -x; +1: mirrored (moves to +x)
    # None defaults below are replaced by __post_init__ (zero arrays / centroid)
    y_cg: np.ndarray = None  # type: ignore[assignment]  # column centroid elevation
    kh: float = 0.0
    kv: float = 0.0
    # external forces per slice, world coordinates (see slipsurface.loads)
    Qx_a: np.ndarray = None  # type: ignore[assignment]
    Qy_a: np.ndarray = None  # type: ignore[assignment]
    M_a: np.ndarray = None  # type: ignore[assignment]
    Qx_p: np.ndarray = None  # type: ignore[assignment]
    Qy_p: np.ndarray = None  # type: ignore[assignment]
    M_p: np.ndarray = None  # type: ignore[assignment]
    support_forces: list = None  # type: ignore[assignment]
    crack: dict | None = None          # tension crack at the uphill end (see loads.TensionCrack)

    def __post_init__(self) -> None:
        if self.y_cg is None:
            self.y_cg = 0.5 * (self.y_top + self.y_base)
        for k in ("Qx_a", "Qy_a", "M_a", "Qx_p", "Qy_p", "M_p"):
            if getattr(self, k) is None:
                setattr(self, k, np.zeros(len(self.b)))
        if self.support_forces is None:
            self.support_forces = []

    @property
    def has_passive(self) -> bool:
        return bool(np.any(self.Qx_p) or np.any(self.Qy_p))

    def ext(self, F: float = 1.0):
        """(Qx, Qy, M0) total external force per slice for a given F (world)."""
        return (self.Qx_a + self.Qx_p / F, self.Qy_a + self.Qy_p / F, self.M_a + self.M_p / F)

    @property
    def n(self) -> int:
        return len(self.b)

    @property
    def Wv(self) -> np.ndarray:
        """Vertical load including the vertical seismic coefficient."""
        return self.W * (1.0 - self.kv)

    @property
    def Fh(self) -> np.ndarray:
        """Horizontal seismic force, acting in the sliding direction."""
        return self.W * self.kh

    def base_points(self) -> np.ndarray:
        """Base polyline through the slice edges (for drawing)."""
        xs = np.concatenate([self.xl[:1], self.xr])
        return np.column_stack([xs, self.surface.y(xs)])

    @property
    def is_circular(self) -> bool:
        return hasattr(self.surface, "r")


class SlicingError(ValueError):
    """Surface is kinematically or geometrically inadmissible."""


def make_slices(
    geom: SlopeGeometry,
    surf: SlipSurface,
    materials: dict[str, Material],
    n_slices: int | None = None,
    n_sub: int | None = None,
    gamma_w: float | None = None,
    opts: SliceOptions | None = None,
) -> SliceSet:
    o = replace(opts) if opts is not None else SliceOptions()
    if n_slices is not None:
        o.n_slices = n_slices
    if n_sub is not None:
        o.n_sub = n_sub
    if gamma_w is not None:
        o.gamma_w = gamma_w

    ext = slip_extent(geom, surf)
    if ext is None:
        raise SlicingError("slip surface does not define a sliding mass inside the model")
    x_exit, x_entry = ext
    crack_cut = None
    if o.crack is not None:
        crack_cut = o.crack.cut(geom, surf, x_exit, x_entry)
        if crack_cut is not None:
            x_exit, x_entry = crack_cut[0], crack_cut[1]
    if x_entry - x_exit < 1e-6:
        raise SlicingError("sliding mass too small")

    # ------------------------------------------------- slice boundaries
    xs = np.linspace(x_exit, x_entry, o.n_slices + 1)
    extra = [geom.surface[:, 0]]
    if hasattr(surf, "pts"):                       # polyline surface vertices
        extra.append(surf.pts[:, 0])
    if geom.water_table is not None and o.pore == "water_table":
        extra.append(geom.water_table[:, 0])
    if o.loads is not None:
        extra.append(np.asarray(o.loads.extra_boundaries(), float))
    extra_x = np.concatenate(extra)
    extra_x = extra_x[(extra_x > x_exit + 1e-6) & (extra_x < x_entry - 1e-6)]
    xs = np.unique(np.concatenate([xs, extra_x]))
    keep = np.concatenate([[True], np.diff(xs) > 1e-4 * (x_entry - x_exit)])
    xs = xs[keep]                                            # drop slivers
    xs[-1] = x_entry

    xl, xr = xs[:-1], xs[1:]
    xm = 0.5 * (xl + xr)
    b = xr - xl
    y_base = surf.y(xm)
    y_top = np.asarray(geom.ground_y(xm))
    if hasattr(surf, "sin_alpha"):                       # circle: exact tangent
        alpha = np.arcsin(np.clip(surf.sin_alpha(xm), -1.0, 1.0))
    else:                                                # general: base chord
        alpha = np.arctan2(surf.y(xr) - surf.y(xl), b)
    l = b / np.cos(alpha)

    h = y_top - y_base
    if o.min_depth > 0 and h.max() < o.min_depth:
        raise SlicingError("sliding mass shallower than the minimum depth")

    # ---------------------------------------------- material lookup
    names = list(materials)
    mats = [materials[k] for k in names]
    region_polys = [r.polygon for r in geom.regions]
    try:
        region_mat = np.array([names.index(r.material) for r in geom.regions])
    except ValueError as exc:
        raise SlicingError(f"region material not defined: {exc}") from None
    gam = np.array([m.gamma for m in mats])
    gam_sat = np.array([m.gamma_sat for m in mats])

    def which_material(px, py):
        idx = np.full(px.shape, -1, dtype=int)
        for poly, mi in zip(region_polys, region_mat, strict=False):
            hit = (idx < 0) & shapely.contains_xy(poly, px, py)
            idx[hit] = mi
        return idx

    # base material: sample just above the base (inside the soil)
    eps = 1e-6 * max(1.0, x_entry - x_exit)
    mat_idx = which_material(xm, y_base + np.minimum(eps, 0.5 * np.maximum(h, 0.0)))
    if np.any(mat_idx < 0):
        raise SlicingError("slip surface leaves the model domain")

    # ------------------------------------------------------- weights
    t = (np.arange(o.n_sub) + 0.5) / o.n_sub                 # column fractions
    py = y_base[:, None] + h[:, None] * t[None, :]           # (n, n_sub)
    px = np.broadcast_to(xm[:, None], py.shape)
    col_idx = which_material(px.ravel(), py.ravel()).reshape(py.shape)
    col_idx = np.where(col_idx < 0, mat_idx[:, None], col_idx)  # numeric edge cases

    water_y = geom.water_y(xm) if o.pore == "water_table" else None
    wt = np.asarray(water_y) if water_y is not None else None
    if wt is None:
        g = gam[col_idx]
    else:
        below = py < wt[:, None]
        g = np.where(below, gam_sat[col_idx], gam[col_idx])
    W = b * (h / o.n_sub) * g.sum(axis=1)
    gs = g.sum(axis=1)
    y_cg = np.where(gs > 0, (g * py).sum(axis=1) / np.where(gs > 0, gs, 1.0), 0.5 * (y_top + y_base))

    # Ponded water (Slide2): where the water table rises above the ground
    # surface, the water column resting on the slice top adds weight. It is
    # included in W, so the pseudo-static seismic forces apply to it too.
    if wt is not None and np.any(np.asarray(wt) - y_top > 0.0):
        W = W + o.gamma_w * np.maximum(np.asarray(wt) - y_top, 0.0) * b

    # ------------------------------------------------ pore pressure
    if o.pore == "water_table" and wt is not None:
        hu = np.array([getattr(m, "hu", 1.0) for m in mats])[mat_idx]
        uses = np.array([getattr(m, "use_water", True) for m in mats])[mat_idx]
        u = np.where(uses, hu * o.gamma_w * np.maximum(wt - y_base, 0.0), 0.0)
    elif o.pore == "ru":
        u = o.ru * W / b
    else:
        u = np.zeros_like(xm)

    # ------------------------------------------------ failure direction
    drive = np.sum(W * np.sin(alpha))
    if o.direction == "right_to_left":
        direction = -1
        if drive <= 0:
            raise SlicingError("surface opposes the specified failure direction")
    elif o.direction == "left_to_right":
        direction = +1
        alpha = -alpha
        if -drive <= 0:
            raise SlicingError("surface opposes the specified failure direction")
    else:
        direction = -1
        if drive < 0:                         # left-to-right failure: mirror
            alpha = -alpha
            direction = +1

    forces = {}
    info = []
    if o.loads is not None and not o.loads.empty:
        from slipsurface.loads import slice_forces
        forces, info = slice_forces(o.loads, geom, surf, xl, xr, x_exit, x_entry, direction)

    crack = None
    if crack_cut is not None:
        assert o.crack is not None                 # crack_cut only set when o.crack is
        xc, right = crack_cut[2], crack_cut[3]
        y_bot, y_gr = float(surf.y(xc)), float(geom.ground_y(xc))
        z = max(y_gr - y_bot, 0.0)
        hw = float(np.clip(o.crack.water, 0.0, 1.0)) * z
        Pw = 0.5 * o.crack.gamma_w * hw * hw
        crack = {"x": xc, "y_bottom": y_bot, "y_ground": y_gr, "depth": z, "hw": hw,
                 "Pw": Pw, "uphill_right": right}
        if Pw > 0:
            if not forces:
                forces = {k: np.zeros(len(xl)) for k in
                          ("Qx_a", "Qy_a", "M_a", "Qx_p", "Qy_p", "M_p")}
            i = len(xl) - 1 if right else 0
            fx, yp = direction * Pw, y_bot + hw / 3.0       # thrust in the sliding direction
            forces["Qx_a"][i] += fx
            forces["M_a"][i] += -yp * fx                    # x*Fy - y*Fx with Fy = 0

    return SliceSet(xl, xr, xm, b, y_base, y_top, alpha, l, W, u, mat_idx, mats,
                    surf, x_exit, x_entry, direction, y_cg, o.kh, o.kv,
                    support_forces=info, crack=crack, **forces)
