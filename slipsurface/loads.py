"""External loads and support (reinforcement) forces acting on the sliding mass.

Every load ends up as point forces (x, y, Fx, Fy) in world coordinates,
assigned to the slice that contains x. Per slice the solvers receive
    Qx, Qy   force resultants [kN/m]
    M0       moment about the global origin, sum(x Fy - y Fx) [kN m/m]
separately for ACTIVE and PASSIVE forces. Passive forces are divided by the
factor of safety inside the solvers (Slide2 / GeoStudio convention):
  active  : the force is applied as is (reduces the driving force)
  passive : the force is mobilised like shear strength, i.e. applied as T/F

Loads
  DistributedLoad  on the ground surface between x1 and x2, magnitude varying
                   linearly q1 -> q2 [kPa]; orientation
                     "vertical": q per horizontal metre, acting downward
                     "normal"  : q per metre of boundary, normal to the surface
  LineLoad         P [kN/m] at a surface point, direction angle measured
                   counter-clockwise from +x (270 = vertically down)

Supports (straight, from head A on the slope to end B inside the slope);
I = intersection with the slip surface, L_in = |AI| (in the sliding mass),
L_out = |IB| (in stable ground). Force per metre = T / spacing for discrete
supports; geotextile/geosynthetic strengths are already per metre width.
  end_anchored     T = tensile capacity
  grouted_tieback  T = min(tensile, bond * min(bond_length, L_out))
  soil_nail        T = min(tensile, bond * L_out, plate + bond * L_in)
  geotextile       T = min(tensile, pullout * min(L_in, L_out))
  geosynthetic     Slide2 style, per metre width with strip coverage C:
                   pullout on one side = 2 C int (adhesion + sigma_v tan delta) ds,
                   sigma_v = gamma_ob * depth below the ground; anchorage
                     none     T = min(C tensile, P_in, P_out)
                     face     T = min(C tensile, P_out)   (anchored at the slope face)
                     embedded T = min(C tensile, P_in)    (embedded end anchored)
                     both     T = C tensile
  micro_pile       T = pile shear strength (the pile resists by shear)
Direction: "parallel" to the support (A -> B), "tangent" to the slip
surface (opposing the sliding direction) or "perpendicular" to the support
(micro-piles; the side that opposes sliding). Applied at I.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

SUPPORT_KINDS = {
    "end_anchored": "Uç ankrajlı",
    "grouted_tieback": "Enjeksiyonlu ankraj (tieback)",
    "soil_nail": "Zemin çivisi",
    "geotextile": "Geotekstil",
    "geosynthetic": "Geosentetik",
    "micro_pile": "Mikro kazık",
}
ANCHORAGES = {
    "none": "Yok",
    "face": "Şev yüzünde",
    "embedded": "Gömülü uçta",
    "both": "Her iki uçta",
}


@dataclass
class DistributedLoad:
    x1: float
    x2: float
    q1: float
    q2: float
    orientation: str = "vertical"  # vertical | normal

    def q_at(self, x):
        if abs(self.x2 - self.x1) < 1e-12:
            return np.full_like(np.asarray(x, float), self.q1)
        t = (np.asarray(x, float) - self.x1) / (self.x2 - self.x1)
        return self.q1 + (self.q2 - self.q1) * t


@dataclass
class LineLoad:
    x: float
    y: float
    magnitude: float  # kN/m
    angle: float = 270.0  # degrees CCW from +x

    @property
    def force(self) -> tuple[float, float]:
        a = np.radians(self.angle)
        return self.magnitude * float(np.cos(a)), self.magnitude * float(np.sin(a))


@dataclass
class SupportType:
    name: str = "Ankraj 1"
    kind: str = "end_anchored"
    spacing: float = 1.5  # out-of-plane spacing [m]; ignored for geotextile/geosynthetic
    tensile: float = 200.0  # kN; kN/m for geotextile/geosynthetic
    plate: float = 100.0  # kN (soil nail)
    bond_strength: float = 50.0  # kN/m (tieback, soil nail)
    bond_length: float = 4.0  # m (tieback)
    pullout: float = 20.0  # kN/m per m (geotextile)
    application: str = "active"  # active | passive
    orientation: str = "parallel"  # parallel | tangent | perpendicular
    color: str = "#1f3d7a"
    length: float = 12.0  # default length for automatically placed bolts [m]
    # geosynthetic
    coverage: float = 100.0  # strip coverage [%]
    anchorage: str = "none"  # none | face | embedded | both
    adhesion: float = 0.0  # interface adhesion [kPa]
    interface_friction: float = 25.0  # interface friction angle delta [deg]
    overburden_gamma: float = 19.0  # unit weight for the overburden stress [kN/m3]
    # micro pile
    pile_shear: float = 100.0  # shear strength of one pile [kN]


@dataclass
class Support:
    a: tuple[float, float]  # head (slope face)
    b: tuple[float, float]  # end (inside the slope)
    stype: SupportType
    label: str = ""


@dataclass
class SupportForce:
    index: int
    x: float
    y: float
    T: float  # kN/m (before the passive 1/F scaling)
    fx: float
    fy: float
    passive: bool
    L_in: float
    L_out: float
    governing: str
    label: str = ""

    def mobilized(self, fos: float) -> float:
        """Applied force [kN/m] at the solved factor of safety."""
        if not np.isfinite(fos) or fos <= 0:
            raise ValueError("factor of safety must be finite and positive")
        return self.T / fos if self.passive else self.T


@dataclass
class FacingType:
    """Shotcrete facing with welded wire mesh (püskürtme beton + hasır çelik).

    capacity per metre of slope = tau * thickness + As * fy   [kN/m]
      tau        shear strength of the shotcrete [kPa]
      As         mesh steel area [mm2/m] (e.g. Q188 -> 188), fy [MPa]
    """

    name: str = "Püskürtme beton"
    thickness: float = 0.10  # m
    gamma: float = 24.0  # kN/m3
    tau: float = 400.0  # kPa
    mesh: str = "Q188"
    mesh_as: float = 188.0  # mm2/m
    mesh_fy: float = 500.0  # MPa
    application: str = "passive"  # passive (T/F) | active
    color: str = "#7f8c8d"

    @property
    def capacity(self) -> float:
        return self.tau * self.thickness + self.mesh_as * self.mesh_fy / 1000.0

    @property
    def weight_per_m(self) -> float:  # per metre of slope length
        return self.gamma * self.thickness


@dataclass
class Facing:
    x1: float
    x2: float
    ftype: FacingType


@dataclass
class LoadSet:
    distributed: list[DistributedLoad] = field(default_factory=list)
    line: list[LineLoad] = field(default_factory=list)
    supports: list[Support] = field(default_factory=list)
    facings: list[Facing] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.distributed or self.line or self.supports or self.facings)

    def extra_boundaries(self) -> list[float]:
        xs = []
        for d in self.distributed:
            xs += [d.x1, d.x2]
        xs += [ln.x for ln in self.line]
        for f in self.facings:
            xs += [f.x1, f.x2]
        return xs


# ------------------------------------------------------------- supports
def support_intersection(sup: Support, surf, x_exit: float, x_entry: float):
    """First point where the support crosses the slip surface, from A towards B."""
    A, B = np.asarray(sup.a, float), np.asarray(sup.b, float)
    # quick reject: support entirely outside the sliding mass in x
    if max(A[0], B[0]) < x_exit - 1e-9 or min(A[0], B[0]) > x_entry + 1e-9:
        return None
    ts = np.linspace(0.0, 1.0, 241)
    P = A[None, :] + ts[:, None] * (B - A)[None, :]
    with np.errstate(invalid="ignore"):
        vals = P[:, 1] - surf.y(P[:, 0])  # vectorized
    ok = np.isfinite(vals[:-1]) & np.isfinite(vals[1:])
    idx = np.flatnonzero(ok & (vals[:-1] > 0) & (vals[1:] <= 0))
    if idx.size == 0:
        return None
    k = int(idx[0])

    def g(t):
        p = A + t * (B - A)
        return float(p[1] - surf.y(p[0]))

    t = brentq(g, ts[k], ts[k + 1], xtol=1e-10) if vals[k + 1] < 0 else ts[k + 1]
    p = A + t * (B - A)
    if x_exit - 1e-9 <= p[0] <= x_entry + 1e-9:
        return p
    return None


def geosynthetic_pullout(st: SupportType, geom, p0, p1) -> float:
    """Pullout resistance [kN/m] of the geosynthetic segment p0 -> p1 (both faces)."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    L = float(np.hypot(*(p1 - p0)))
    if L <= 0:
        return 0.0
    t = (np.arange(20) + 0.5) / 20
    pts = p0[None, :] + t[:, None] * (p1 - p0)[None, :]
    depth = np.maximum(np.asarray(geom.ground_y(pts[:, 0]), float) - pts[:, 1], 0.0)
    shear = st.adhesion + st.overburden_gamma * depth * np.tan(np.radians(st.interface_friction))
    return float(2.0 * st.coverage / 100.0 * shear.mean() * L)


def support_capacity(
    st: SupportType,
    L_in: float,
    L_out: float,
    po_in: float | None = None,
    po_out: float | None = None,
) -> tuple[float, str]:
    """Force [kN] and which component governs. `po_in` / `po_out` are the
    geosynthetic pullout resistances inside / outside the sliding mass."""
    if st.kind == "end_anchored":
        return st.tensile, "çekme kapasitesi"
    if st.kind == "grouted_tieback":
        bond = st.bond_strength * min(st.bond_length, L_out)
        return (st.tensile, "çekme kapasitesi") if st.tensile <= bond else (bond, "kök sıyrılma")
    if st.kind == "soil_nail":
        cands = [
            (st.tensile, "çekme kapasitesi"),
            (st.bond_strength * L_out, "sıyrılma (dış)"),
            (st.plate + st.bond_strength * L_in, "plaka + sıyrılma (iç)"),
        ]
        return min(cands, key=lambda c: c[0])
    if st.kind == "geotextile":
        po = st.pullout * min(L_in, L_out)
        return (st.tensile, "çekme dayanımı") if st.tensile <= po else (po, "sıyrılma")
    if st.kind == "geosynthetic":
        cands = [(st.coverage / 100.0 * st.tensile, "çekme dayanımı")]
        if st.anchorage in ("none", "embedded"):
            cands.append((po_in if po_in is not None else np.inf, "sıyrılma (iç)"))
        if st.anchorage in ("none", "face"):
            cands.append((po_out if po_out is not None else np.inf, "sıyrılma (dış)"))
        return min(cands, key=lambda c: c[0])
    if st.kind == "micro_pile":
        return st.pile_shear, "kazık kesme dayanımı"
    raise ValueError(f"unknown support kind {st.kind}")


def _ground_slope(geom, x, h=1e-4):
    return (geom.ground_y(x + h) - geom.ground_y(x - h)) / (2 * h)


def slice_forces(loads: LoadSet, geom, surf, xl, xr, x_exit, x_entry, direction: int):
    """Per-slice active/passive force arrays and support details.

    Returns dict with Qx_a, Qy_a, M_a, Qx_p, Qy_p, M_p (world coordinates) and
    a list of SupportForce.
    """
    n = len(xl)
    out = {k: np.zeros(n) for k in ("Qx_a", "Qy_a", "M_a", "Qx_p", "Qy_p", "M_p")}
    info: list[SupportForce] = []

    def add(i, x, y, fx, fy, passive=False):
        s = "_p" if passive else "_a"
        out["Qx" + s][i] += fx
        out["Qy" + s][i] += fy
        out["M" + s][i] += x * fy - y * fx

    def slice_of(x):
        idx = np.flatnonzero((xl - 1e-9 <= x) & (x <= xr + 1e-9))
        return int(idx[0]) if idx.size else None

    # distributed loads (midpoint rule on the overlap with each slice top)
    for d in loads.distributed:
        lo, hi = sorted((d.x1, d.x2))
        for i in range(n):
            a, b = max(xl[i], lo), min(xr[i], hi)
            if b - a <= 1e-12:
                continue
            m = 8
            xs = a + (np.arange(m) + 0.5) * (b - a) / m
            dx = (b - a) / m
            q = d.q_at(xs)
            ys = geom.ground_y(xs)
            if d.orientation == "normal":
                dy = _ground_slope(geom, xs) * dx
                fx, fy = q * dy, -q * dx
            else:
                fx, fy = np.zeros(m), -q * dx
            for xk, yk, fxk, fyk in zip(xs, ys, fx, fy, strict=False):
                add(i, xk, yk, fxk, fyk)

    # line loads
    for ln in loads.line:
        if not (x_exit <= ln.x <= x_entry):
            continue
        i = slice_of(ln.x)
        if i is not None:
            fx, fy = ln.force
            add(i, ln.x, float(geom.ground_y(ln.x)), fx, fy)

    # supports
    for k, sup in enumerate(loads.supports):
        p = support_intersection(sup, surf, x_exit, x_entry)
        if p is None:
            continue
        A, B = np.asarray(sup.a, float), np.asarray(sup.b, float)
        L_in, L_out = float(np.hypot(*(p - A))), float(np.hypot(*(B - p)))
        po_in = po_out = None
        if sup.stype.kind == "geosynthetic":
            po_in = geosynthetic_pullout(sup.stype, geom, A, p)
            po_out = geosynthetic_pullout(sup.stype, geom, p, B)
        T, gov = support_capacity(sup.stype, L_in, L_out, po_in, po_out)
        spacing = 1.0 if sup.stype.kind in ("geotextile", "geosynthetic") else sup.stype.spacing
        T = max(T, 0.0) / max(spacing, 1e-9)
        if sup.stype.orientation == "perpendicular":
            d = (B - A) / np.hypot(*(B - A))
            u = np.array([-d[1], d[0]])
            if u[0] * direction > 0:  # pick the normal that opposes sliding
                u = -u
        elif sup.stype.orientation == "tangent":
            h = 1e-5
            slope = (surf.y(p[0] + h) - surf.y(p[0] - h)) / (2 * h)
            t = np.array([1.0, slope]) / np.hypot(1.0, slope)
            u = -direction * t  # opposes the sliding direction
        else:
            u = (B - A) / np.hypot(*(B - A))
        i = slice_of(p[0])
        if i is None:
            continue
        passive = sup.stype.application == "passive"
        add(i, p[0], p[1], T * u[0], T * u[1], passive)
        info.append(
            SupportForce(
                k,
                float(p[0]),
                float(p[1]),
                T,
                T * u[0],
                T * u[1],
                passive,
                L_in,
                L_out,
                gov,
                sup.label or f"Destek {k + 1}",
            )
        )

    # shotcrete facing: weight on the faced surface + resistance where the slip
    # surface daylights through it (exit and/or entry point)
    for f in loads.facings:
        lo, hi = sorted((f.x1, f.x2))
        ft = f.ftype
        for i in range(n):
            a, b = max(xl[i], lo), min(xr[i], hi)
            if b - a <= 1e-12:
                continue
            m = 6
            xs = a + (np.arange(m) + 0.5) * (b - a) / m
            dx = (b - a) / m
            ds = np.hypot(1.0, _ground_slope(geom, xs)) * dx
            for xk, dsk in zip(xs, ds, strict=False):
                add(i, xk, float(geom.ground_y(xk)), 0.0, -ft.weight_per_m * dsk)
        applied = False  # capacity mobilised once per facing: at the first
        for x, i in ((x_exit, 0), (x_entry, n - 1)):  # end the slip surface daylights through
            if applied or not (lo - 1e-6 <= x <= hi + 1e-6):
                continue
            y = float(geom.ground_y(x))
            if abs(float(surf.y(x)) - y) > 1e-3:  # end is not on the ground (e.g. crack)
                continue
            h = 1e-5
            slope = (surf.y(x + h) - surf.y(x - h)) / (2 * h)
            if not np.isfinite(slope):
                slope = (
                    (surf.y(x + 2 * h) - surf.y(x)) / (2 * h)
                    if i == 0
                    else (surf.y(x) - surf.y(x - 2 * h)) / (2 * h)
                )
            t = np.array([1.0, slope]) / np.hypot(1.0, slope)
            u = -direction * t  # opposes sliding
            T = ft.capacity
            passive = ft.application == "passive"
            add(i, x, y, T * u[0], T * u[1], passive)
            info.append(
                SupportForce(
                    -1,
                    x,
                    y,
                    T,
                    T * u[0],
                    T * u[1],
                    passive,
                    0.0,
                    0.0,
                    "kaplama (τ·t + As·fy)",
                    ft.name,
                )
            )
            applied = True
    return out, info


# --------------------------------------------------- automatic bolts
def into_slope_direction(geom, x: float, angle_deg: float) -> np.ndarray:
    """Unit vector into the slope at surface point x, inclined `angle_deg` below
    the horizontal (towards the uphill side)."""
    sl = float(_ground_slope(geom, x))
    if abs(sl) < 1e-9:
        sl = float(geom.surface[-1, 1] - geom.surface[0, 1])
    s = 1.0 if sl > 0 else -1.0
    a = np.radians(angle_deg)
    return np.array([s * np.cos(a), -np.sin(a)])


def bolt_at(geom, x: float, angle_deg: float, length: float):
    """(A, B) of a bolt with its head on the ground at x."""
    A = np.array([x, float(geom.ground_y(x))])
    return A, A + length * into_slope_direction(geom, x, angle_deg)


def pattern_positions(geom, x1: float, x2: float, spacing: float, offset: float = 0.0):
    """x positions along the ground surface between x1 and x2, spaced by arc length."""
    lo, hi = sorted((x1, x2))
    xs = np.linspace(lo, hi, 2001)
    ys = geom.ground_y(xs)
    s = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(xs), np.diff(ys)))])
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    targets = np.arange(offset, s[-1] + 1e-9, spacing)
    return list(np.interp(targets, s, xs))


# ------------------------------------------------------------ tension crack
@dataclass
class TensionCrack:
    """Tension crack boundary (Slide2 style).

    `line` is a polyline (x increasing) below the ground in the crest zone.
    A slip surface that crosses it on its uphill side is cut there: the part
    of the surface above the line (the cracked zone) carries no shear, and the
    sliding mass ends at a vertical crack face from the cut point to the
    ground. `water` is the filled fraction of the crack depth (0 = dry,
    1 = full); the water thrust V = 0.5 gamma_w hw^2 acts horizontally in the
    sliding direction at hw/3 above the crack bottom.
    """

    line: np.ndarray
    water: float = 0.0
    gamma_w: float = 9.81

    def __post_init__(self) -> None:
        self.line = np.asarray(self.line, dtype=float)
        if len(self.line) < 2 or np.any(np.diff(self.line[:, 0]) <= 0):
            raise ValueError("tension crack line needs >= 2 points with increasing x")

    def y(self, x):
        return np.interp(x, self.line[:, 0], self.line[:, 1])

    def cut(self, geom, surf, x_exit: float, x_entry: float):
        """New (x_exit, x_entry, x_crack, uphill_is_right) or None."""
        lo, hi = max(x_exit, self.line[0, 0]), min(x_entry, self.line[-1, 0])
        if hi - lo <= 1e-9:
            return None
        xs = np.linspace(lo, hi, 401)
        h = surf.y(xs) - self.y(xs)  # > 0: slip surface inside the cracked zone
        right = float(geom.ground_y(x_entry)) >= float(geom.ground_y(x_exit))
        ks = []
        for k in range(len(xs) - 1):
            a, b = h[k], h[k + 1]
            if not (np.isfinite(a) and np.isfinite(b)):
                continue
            if right and a <= 0 < b:
                ks.append(k)
            if not right and a > 0 >= b:
                ks.append(k)
        if not ks:
            return None
        k = ks[-1] if right else ks[0]
        f = lambda x: float(surf.y(x) - self.y(x))  # noqa: E731
        try:
            xc = (
                brentq(f, xs[k], xs[k + 1], xtol=1e-10)
                if f(xs[k]) * f(xs[k + 1]) < 0
                else xs[k + 1]
                if right
                else xs[k]
            )
        except ValueError:
            return None
        if right:
            return x_exit, float(xc), float(xc), True
        return float(xc), x_entry, float(xc), False
