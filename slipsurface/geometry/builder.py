"""Slide2-style geometry: external boundary + material boundaries + assignments.

* external          closed polygon of the whole model (vertices, any order)
* material lines    polylines that split the external region into zones;
                    ends within `snap_tol` of the boundary are snapped onto it
* assignments       (x, y, material): a zone takes the material of the last
                    assignment point inside it, otherwise `default_material`
* water table       polyline, extended flat to the model edges

The ground surface used for slicing is the upper envelope of the external
boundary (vertical slices assume no overhangs).
"""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from slipsurface.geometry.slope import Region, SlopeGeometry


def upper_profile(poly: Polygon) -> np.ndarray:
    """Upper envelope of a polygon as an x-increasing polyline."""
    xs = np.unique(np.round(np.asarray(poly.exterior.coords)[:, 0], 12))
    ymin, ymax = poly.bounds[1] - 1.0, poly.bounds[3] + 1.0
    pts = []
    for x in xs:
        cut = LineString([(x, ymin), (x, ymax)]).intersection(poly)
        if cut.is_empty:
            continue
        pts.append((x, cut.bounds[3]))
    profile = np.asarray(pts, dtype=float)
    # A graph y(x) cannot represent vertical steps or overhangs. Validate
    # between every pair of vertex abscissae: the polygon edges are linear
    # there, so a midpoint cut detects a falsely interpolated upper face.
    scale = max(1.0, poly.bounds[2] - poly.bounds[0], poly.bounds[3] - poly.bounds[1])
    for left, right in zip(profile[:-1], profile[1:], strict=False):
        x = 0.5 * (left[0] + right[0])
        cut = LineString([(x, ymin), (x, ymax)]).intersection(poly)
        if not isinstance(cut, LineString) or not np.isclose(
            cut.bounds[3], 0.5 * (left[1] + right[1]), rtol=0.0, atol=1e-10 * scale
        ):
            raise ValueError(
                "Dik şev yüzü veya çıkmalı geometri desteklenmiyor. "
                "Zemin yüzeyi sürekli ve x artan bir profil olmalı."
            )
    return profile


def _extend_flat(line: np.ndarray, x0: float, x1: float) -> np.ndarray:
    line = line[np.argsort(line[:, 0])]
    if line[0, 0] > x0:
        line = np.vstack([[x0, line[0, 1]], line])
    if line[-1, 0] < x1:
        line = np.vstack([line, [x1, line[-1, 1]]])
    return line


def _attach_ends(ml: np.ndarray, boundary, domain: Polygon, tol: float) -> np.ndarray:
    """Snap line ends lying within `tol` of the boundary onto it and push them
    slightly outside, so the line properly crosses the boundary."""
    ml = ml.copy()
    for end, prev in ((0, 1), (-1, -2)):
        p = Point(ml[end])
        if boundary.distance(p) <= tol:
            q = boundary.interpolate(boundary.project(p))
            d = ml[end] - ml[prev]
            n = np.hypot(*d)
            d = d / n if n > 0 else np.zeros(2)
            # outward = away from the domain interior along the segment direction
            cand = np.array(q.coords[0]) + d * tol * 0.5
            if domain.contains(Point(cand)):
                cand = np.array(q.coords[0]) - d * tol * 0.5
            if domain.contains(Point(cand)):
                # Concave corner (e.g. a layer starting at the slope toe): both
                # directions stay inside. End exactly on the boundary vertex so
                # the line nodes with it instead of dangling inside the domain.
                verts = np.asarray(boundary.coords)
                k = int(np.argmin(np.hypot(*(verts - q.coords[0]).T)))
                near = np.hypot(*(verts[k] - q.coords[0])) <= tol
                cand = verts[k] if near else np.array(q.coords[0])
            ml[end] = cand
    return ml


def build_regions(
    external,
    material_lines,
    assignments,
    default_material: str,
    snap_tol: float | None = None,
    min_area: float = 1e-6,
):
    """Return (domain polygon, [Region], clipped material lines)."""
    ext = np.asarray(external, dtype=float)
    if len(ext) < 3:
        raise ValueError("Dış sınır en az 3 köşe içermeli.")
    domain = Polygon(ext)
    if not domain.is_valid:
        raise ValueError("Dış sınır kendini kesiyor (geçersiz poligon).")
    if domain.area <= 0:
        raise ValueError("Dış sınırın alanı sıfır.")
    domain = shapely.orient_polygons(domain) if hasattr(shapely, "orient_polygons") else domain
    size = max(domain.bounds[2] - domain.bounds[0], domain.bounds[3] - domain.bounds[1])
    tol = snap_tol if snap_tol is not None else 2e-3 * size

    boundary = domain.exterior
    lines = [boundary]
    clipped = []
    for i, ml in enumerate(material_lines or []):
        ml = np.asarray(ml, dtype=float)
        if len(ml) < 2:
            raise ValueError(f"Malzeme sınırı {i + 1}: en az 2 nokta gerekli.")
        ml = _attach_ends(ml, boundary, domain, tol)
        ls = LineString(ml)
        # the (extended) line crosses the boundary -> robust nodes; parts
        # outside the domain are dangles that polygonize ignores
        lines.append(ls)
        inside = ls.intersection(domain)
        for g in getattr(inside, "geoms", [inside]):
            if isinstance(g, LineString) and g.length > 0:
                clipped.append(np.asarray(g.coords))

    noded = unary_union(lines)
    polys = [
        p
        for p in polygonize(noded)
        if p.area > min_area and domain.buffer(tol).contains(p.representative_point())
    ]
    if not polys:
        polys = [domain]

    regions = []
    for p in polys:
        mat = default_material
        for x, y, name in assignments or []:
            if p.contains(Point(x, y)):
                mat = name
        regions.append(Region(p, mat))
    return domain, regions, clipped


def boundary_geometry(
    external,
    material_lines=(),
    assignments=(),
    default_material="Zemin 1",
    water_table=None,
    name: str = "Model",
) -> SlopeGeometry:
    domain, regions, clipped = build_regions(
        external, material_lines, assignments, default_material
    )
    surface = upper_profile(domain)
    x0, x1 = surface[0, 0], surface[-1, 0]
    wt = None
    if water_table is not None and len(water_table) >= 2:
        wt = np.asarray(water_table, dtype=float)
        if np.any(np.diff(wt[:, 0]) <= 0):
            raise ValueError("YASS noktaları x artan sırada olmalı.")
        wt = _extend_flat(wt, x0, x1)
    return SlopeGeometry(
        surface=surface,
        regions=regions,
        water_table=wt,
        meta={
            "name": name,
            "external": np.asarray(external, float),
            "boundaries": clipped,
            "domain": domain,
        },
    )
