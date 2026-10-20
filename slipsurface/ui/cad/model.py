"""Editable entities of a project, addressed by keys.

key = ("external", 0) | ("material", i) | ("water", 0) | ("user", 0)
      | ("load", i) | ("support", i)
"""

from __future__ import annotations

from slipsurface.ui.i18n import tr

from dataclasses import dataclass

import numpy as np

from slipsurface.project import Project

LABELS = {"external": tr("Dış sınır"), "material": tr("Malzeme sınırı"), "water": "YASS",
          "user": tr("Kullanıcı yüzeyi"), "load": "Yük", "support": tr("Destek"),
          "crack": tr("Gerilme çatlağı"), "pattern": "Bulon paterni", "facing": "Kaplama",
          "annot": "Not"}
MIN_POINTS = {"external": 3, "material": 2, "water": 2, "user": 2, "load": 1, "support": 2,
              "crack": 2, "pattern": 2, "facing": 2, "annot": 1}
FIXED_POINTS = {"support", "load", "pattern", "facing", "annot"}   # no vertex insert/delete


@dataclass
class Entity:
    key: tuple
    pts: np.ndarray
    closed: bool

    @property
    def label(self) -> str:
        kind, i = self.key
        return f"{LABELS[kind]} {i + 1}" if kind in ("material", "load", "support", "pattern",
                                                      "facing", "annot") else LABELS[kind]

    def segments(self):
        n = len(self.pts)
        m = n if self.closed else n - 1
        for k in range(m):
            yield k, self.pts[k], self.pts[(k + 1) % n]


def entities(p: Project | None) -> list[Entity]:
    if p is None:
        return []
    out = []
    if len(p.external) >= 2:
        out.append(Entity(("external", 0), np.asarray(p.external, float), True))
    for i, b in enumerate(p.material_boundaries):
        if len(b) >= 2:
            out.append(Entity(("material", i), np.asarray(b, float), False))
    if p.water_table and len(p.water_table) >= 2:
        out.append(Entity(("water", 0), np.asarray(p.water_table, float), False))
    if p.tension_crack and len(p.tension_crack) >= 2:
        out.append(Entity(("crack", 0), np.asarray(p.tension_crack, float), False))
    us = p.surfaces.user_surface
    if us and len(us) >= 2:
        out.append(Entity(("user", 0), np.asarray(us, float), False))
    for i, ld in enumerate(p.loads):
        pts = ld["points"] if ld["kind"] == "distributed" else [ld["point"]]
        out.append(Entity(("load", i), np.asarray(pts, float), False))
    for i, sp in enumerate(p.supports):
        out.append(Entity(("support", i), np.asarray([sp["a"], sp["b"]], float), False))
    for i, pt in enumerate(p.support_patterns):
        out.append(Entity(("pattern", i), np.asarray([pt["p1"], pt["p2"]], float), False))
    for i, f in enumerate(p.facings):
        out.append(Entity(("facing", i), np.asarray(facing_points(f), float), False))
    for i, a in enumerate(p.annotations):
        out.append(Entity(("annot", i), np.asarray(a["pts"], float), False))
    return out


def facing_points(f: dict) -> list:
    return f.get("points") or [[f["x1"], 0.0], [f["x2"], 0.0]]


def entity_kinds(p: Project | None, kinds) -> list[Entity]:
    return [e for e in entities(p) if kinds is None or e.key[0] in kinds]


def get_points(p: Project, key) -> list[list[float]]:
    kind, i = key
    if kind == "external":
        return [list(q) for q in p.external]
    if kind == "material":
        return [list(q) for q in p.material_boundaries[i]]
    if kind == "water":
        return [list(q) for q in (p.water_table or [])]
    if kind == "user":
        return [list(q) for q in (p.surfaces.user_surface or [])]
    if kind == "crack":
        return [list(q) for q in (p.tension_crack or [])]
    if kind == "load":
        ld = p.loads[i]
        return [list(q) for q in (ld["points"] if ld["kind"] == "distributed" else [ld["point"]])]
    if kind == "support":
        return [list(p.supports[i]["a"]), list(p.supports[i]["b"])]
    if kind == "pattern":
        return [list(p.support_patterns[i]["p1"]), list(p.support_patterns[i]["p2"])]
    if kind == "facing":
        return [list(q) for q in facing_points(p.facings[i])]
    if kind == "annot":
        return [list(q) for q in p.annotations[i]["pts"]]
    raise KeyError(key)


def _check_x_increasing(kind: str, pts) -> list[list[float]]:
    pts = [list(map(float, q)) for q in pts]
    if kind in ("water", "user", "crack"):
        if len(pts) >= 2 and pts[0][0] > pts[-1][0]:
            pts = pts[::-1]
        xs = [q[0] for q in pts]
        if any(b <= a for a, b in zip(xs, xs[1:], strict=False)):
            raise ValueError(f"{LABELS[kind]} noktaları soldan sağa (x artan) sıralı olmalı.")
    return pts


def set_points(p: Project, key, pts) -> None:
    kind, i = key
    if len(pts) < MIN_POINTS[kind]:
        raise ValueError(f"{LABELS[kind]} en az {MIN_POINTS[kind]} nokta içermeli.")
    pts = _check_x_increasing(kind, pts)
    if kind == "external":
        p.external = pts
    elif kind == "material":
        p.material_boundaries[i] = pts
    elif kind == "water":
        p.water_table = pts
    elif kind == "user":
        p.surfaces.user_surface = pts
    elif kind == "crack":
        p.tension_crack = pts
    elif kind == "load":
        ld = p.loads[i]
        if ld["kind"] == "distributed":
            ld["points"] = pts[:2]
        else:
            ld["point"] = pts[0]
    elif kind == "support":
        p.supports[i]["a"], p.supports[i]["b"] = pts[0], pts[1]
    elif kind == "pattern":
        p.support_patterns[i]["p1"], p.support_patterns[i]["p2"] = pts[0], pts[1]
    elif kind == "facing":
        f = p.facings[i]
        f["points"] = pts[:2]
        f["x1"], f["x2"] = sorted((pts[0][0], pts[1][0]))
    elif kind == "annot":
        p.annotations[i]["pts"] = pts


def add_entity(p: Project, kind: str, pts) -> tuple:
    if len(pts) < MIN_POINTS[kind]:
        raise ValueError(f"{LABELS[kind]} en az {MIN_POINTS[kind]} nokta içermeli.")
    pts = _check_x_increasing(kind, pts)
    if kind == "external":
        p.external = pts
        return ("external", 0)
    if kind == "material":
        p.material_boundaries.append(pts)
        return ("material", len(p.material_boundaries) - 1)
    if kind == "water":
        p.water_table = pts
        return ("water", 0)
    if kind == "user":
        p.surfaces.user_surface = pts
        p.surfaces.surface_type = "user"
        return ("user", 0)
    if kind == "crack":
        p.tension_crack = pts
        return ("crack", 0)
    raise KeyError(kind)


def delete_entity(p: Project, key) -> None:
    kind, i = key
    if kind == "external":
        p.external = []
        p.material_boundaries = []
        p.assignments = []
    elif kind == "material":
        del p.material_boundaries[i]
    elif kind == "water":
        p.water_table = None
    elif kind == "user":
        p.surfaces.user_surface = None
        if p.surfaces.surface_type == "user":
            p.surfaces.surface_type = "circular"
    elif kind == "crack":
        p.tension_crack = None
    elif kind == "load":
        del p.loads[i]
    elif kind == "support":
        del p.supports[i]
    elif kind == "pattern":
        del p.support_patterns[i]
    elif kind == "facing":
        del p.facings[i]
    elif kind == "annot":
        del p.annotations[i]


def point_segment_distance(q, a, b) -> tuple[float, np.ndarray, float]:
    """Distance from q to segment ab, nearest point, parameter t in [0,1]."""
    a, b, q = np.asarray(a, float), np.asarray(b, float), np.asarray(q, float)
    d = b - a
    L2 = float(d @ d)
    t = 0.0 if L2 == 0 else float(np.clip((q - a) @ d / L2, 0.0, 1.0))
    c = a + t * d
    return float(np.hypot(*(q - c))), c, t


def segment_intersection(a, b, c, d):
    """Intersection point of segments ab and cd, or None."""
    a, b, c, d = (np.asarray(v, float) for v in (a, b, c, d))
    r, s = b - a, d - c
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((c - a)[0] * s[1] - (c - a)[1] * s[0]) / den
    u = ((c - a)[0] * r[1] - (c - a)[1] * r[0]) / den
    if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
        return a + t * r
    return None
