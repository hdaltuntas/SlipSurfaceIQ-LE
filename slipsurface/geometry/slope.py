"""Slope geometry data structures.

Conventions
-----------
* x to the right, y up, metres.
* The slope face dips to the LEFT (crest on the right, toe on the left),
  matching Slide2's default orientation. Sliding direction is therefore -x.
* `surface` is the ground profile polyline ordered by increasing x.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, Polygon


@dataclass
class Region:
    """A material zone: closed polygon + material name."""

    polygon: Polygon
    material: str = "Zemin 1"


@dataclass
class SlopeGeometry:
    surface: np.ndarray  # (n, 2) ground profile, x increasing
    regions: list[Region]  # material zones (union = model domain)
    water_table: np.ndarray | None = None  # (m, 2) piezometric line, x increasing
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.surface = np.asarray(self.surface, dtype=float)
        if self.surface.ndim != 2 or self.surface.shape[1] != 2 or len(self.surface) < 2:
            raise ValueError("surface must be an (n>=2, 2) array")
        if np.any(np.diff(self.surface[:, 0]) <= 0):
            raise ValueError("surface x-coordinates must be strictly increasing")
        if self.water_table is not None:
            self.water_table = np.asarray(self.water_table, dtype=float)
        for r in self.regions:
            if not r.polygon.is_valid:
                raise ValueError(f"invalid polygon for region '{r.material}'")

    # ------------------------------------------------------------ queries
    @property
    def x_min(self) -> float:
        return float(self.surface[0, 0])

    @property
    def x_max(self) -> float:
        return float(self.surface[-1, 0])

    @property
    def domain(self) -> Polygon:
        from shapely.ops import unary_union

        return unary_union([r.polygon for r in self.regions])

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax) of the model domain."""
        return tuple(self.domain.bounds)

    def ground_y(self, x) -> np.ndarray | float:
        """Ground surface elevation at x (linear interpolation)."""
        return np.interp(x, self.surface[:, 0], self.surface[:, 1])

    def water_y(self, x) -> np.ndarray | float | None:
        if self.water_table is None:
            return None
        return np.interp(x, self.water_table[:, 0], self.water_table[:, 1])

    def surface_line(self) -> LineString:
        return LineString(self.surface)


def simple_slope(
    height: float = 10.0,
    ratio_h_to_v: float = 2.0,
    toe_x: float = 15.0,
    left_bench: float = 15.0,
    right_bench: float = 20.0,
    depth_below_toe: float = 10.0,
    material: str = "Zemin 1",
) -> SlopeGeometry:
    """Homogeneous single-face slope.

    `ratio_h_to_v = 2` means 2H:1V (≈26.6°). Toe at (toe_x, 0).

           crest ____________ (x_right, H)
                /
               /  2H:1V
    __________/ toe (toe_x, 0)
    |                         |
    |_________________________| y = -depth_below_toe
    """
    if height <= 0 or ratio_h_to_v <= 0:
        raise ValueError("height and ratio must be positive")
    x0 = toe_x - left_bench
    crest_x = toe_x + ratio_h_to_v * height
    x1 = crest_x + right_bench
    yb = -depth_below_toe

    surface = np.array([[x0, 0.0], [toe_x, 0.0], [crest_x, height], [x1, height]])
    poly = Polygon([(x0, yb), (x1, yb), (x1, height), (crest_x, height), (toe_x, 0.0), (x0, 0.0)])

    return SlopeGeometry(
        surface=surface,
        regions=[Region(poly, material)],
        meta={
            "name": f"Basit şev H={height:g} m, {ratio_h_to_v:g}H:1V",
            "toe": (toe_x, 0.0),
            "crest": (crest_x, height),
            "height": height,
            "angle_deg": float(np.degrees(np.arctan(1.0 / ratio_h_to_v))),
        },
    )


# ---------------------------------------------------------------- layered
def _below(poly_line: np.ndarray, x0: float, x1: float, y_floor: float) -> Polygon:
    """Half-plane-like polygon under a polyline, extended flat to [x0, x1]."""
    pts = np.asarray(poly_line, dtype=float)
    pts = pts[np.argsort(pts[:, 0])]
    if pts[0, 0] > x0:
        pts = np.vstack([[x0, pts[0, 1]], pts])
    if pts[-1, 0] < x1:
        pts = np.vstack([pts, [x1, pts[-1, 1]]])
    ring = [(pts[0, 0], y_floor), *map(tuple, pts), (pts[-1, 0], y_floor)]
    return Polygon(ring).buffer(0)


def layered_geometry(
    surface,
    bottom: float,
    layers: list[tuple[str, np.ndarray | None]],
    water_table=None,
    name: str = "Model",
    min_area: float = 1e-6,
) -> SlopeGeometry:
    """Build regions from a stack of layers.

    layers[0] = (material, None)        top is the ground surface
    layers[i] = (material, top_polyline) top boundary of layer i (i >= 1)

    Each boundary is the TOP of its layer; deeper layers (later in the list)
    take precedence where boundaries cross, so a lower layer may outcrop on
    the slope face. Boundaries are extended horizontally to the model edges
    and clipped by the ground surface automatically.
    """
    from shapely.ops import unary_union

    surface = np.asarray(surface, dtype=float)
    if len(surface) < 2 or np.any(np.diff(surface[:, 0]) <= 0):
        raise ValueError("Zemin yüzeyi en az 2 noktalı olmalı ve x artan sırada olmalı.")
    if not layers:
        raise ValueError("En az bir katman gerekli.")
    if bottom >= surface[:, 1].min():
        raise ValueError("Model tabanı zemin yüzeyinin en alçak noktasından aşağıda olmalı.")

    x0, x1 = surface[0, 0], surface[-1, 0]
    domain = Polygon([(x0, bottom), (x1, bottom), *map(tuple, surface[::-1])]).buffer(0)
    floor = bottom - 1.0

    belows = [domain]
    boundaries = []
    for i, (_mat, top) in enumerate(layers[1:], start=2):
        if top is None or len(top) < 2:
            raise ValueError(f"Katman {i}: üst sınır en az 2 nokta içermeli.")
        top = np.asarray(top, dtype=float)
        belows.append(_below(top, x0, x1, floor).intersection(domain))
        boundaries.append(top)

    regions: list[Region] = []
    for i, (mat, _) in enumerate(layers):
        deeper = unary_union(belows[i + 1 :]) if i + 1 < len(belows) else None
        zone = belows[i] if deeper is None else belows[i].difference(deeper)
        parts = getattr(zone, "geoms", [zone])
        for part in parts:
            if isinstance(part, Polygon) and part.area > min_area:
                regions.append(Region(part, mat))
    if not regions:
        raise ValueError("Katmanlardan geçerli bölge oluşturulamadı.")

    wt = None
    if water_table is not None:
        wt = np.asarray(water_table, dtype=float)
        if len(wt) < 2 or np.any(np.diff(wt[:, 0]) <= 0):
            raise ValueError("YASS en az 2 noktalı olmalı ve x artan sırada olmalı.")
        # extend flat to the model edges so water_y() is defined everywhere
        if wt[0, 0] > x0:
            wt = np.vstack([[x0, wt[0, 1]], wt])
        if wt[-1, 0] < x1:
            wt = np.vstack([wt, [x1, wt[-1, 1]]])

    return SlopeGeometry(
        surface=surface,
        regions=regions,
        water_table=wt,
        meta={"name": name, "boundaries": boundaries, "bottom": bottom},
    )
