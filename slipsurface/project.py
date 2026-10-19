"""Project model (file format v2): Slide2-style boundaries + all settings.

File (.slp.json):
{
  "format": "slipsurface-le", "version": 2,
  "summary":   {title, analysis, author, company, date_created, comments[5]},
  "materials": [{name, model, gamma, gamma_sat, use_sat, c, phi, sigma_ci, gsi, mi, d,
                 use_water, hu, color}],
  "geometry":  {external: [[x,y],...], material_boundaries: [[[x,y],...],...],
                water_table: [[x,y],...] | null, assignments: [{point:[x,y], material}]},
  "settings":  {general, methods, groundwater, seismic, advanced},
  "surfaces":  {...},
  "loads":     [{kind: "distributed", points: [[x1,y1],[x2,y2]], q: [q1,q2],
                 orientation: "vertical"|"normal"},
                {kind: "line", point: [x,y], magnitude, angle}],
  "support_types": [{name, kind, spacing, tensile, plate, bond_strength, bond_length,
                     pullout, application, orientation, color}],
  "supports":  [{a: [x,y], b: [x,y], type: name}],
  "display":   {...}
}
Version-1 files (ground surface + layer stack) are converted on load;
version-2 files simply have no loads / supports.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import numpy as np

from slipsurface.geometry import SlopeGeometry
from slipsurface.geometry.builder import boundary_geometry
from slipsurface.lem import METHODS, SliceOptions
from slipsurface.loads import (
    SUPPORT_KINDS,
    DistributedLoad,
    Facing,
    FacingType,
    LineLoad,
    LoadSet,
    Support,
    SupportType,
    TensionCrack,
    bolt_at,
    pattern_positions,
)
from slipsurface.materials import HoekBrown, Material, MohrCoulomb

FORMAT = "slipsurface-le"
VERSION = 3
PALETTE = ["#f0c800", "#3cb371", "#ff7f3f", "#8080d0", "#8b8b00", "#c97bb4", "#5fb3c9",
           "#c4a484", "#9acd32", "#d2691e"]


def _today() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d, %H:%M:%S")


def _from_dict(cls, d: dict):
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (d or {}).items() if k in known})


# ------------------------------------------------------------------ parts
@dataclass
class ProjectSummary:
    title: str = "Yeni proje"
    analysis: str = ""
    author: str = ""
    company: str = ""
    date_created: str = field(default_factory=_today)
    comments: list[str] = field(default_factory=lambda: [""] * 5)


@dataclass
class MaterialSpec:
    name: str = "Zemin 1"
    model: str = "MC"            # "MC" | "HB"
    gamma: float = 19.0
    gamma_sat: float = 20.0
    use_sat: bool = False        # Slide2: saturated unit weight checkbox
    c: float = 5.0
    phi: float = 30.0
    sigma_ci: float = 25_000.0   # kPa
    gsi: float = 50.0
    mi: float = 10.0
    d: float = 0.0
    use_water: bool = True       # water table acts on this material
    hu: float = 1.0
    color: str = PALETTE[0]

    def to_material(self) -> Material:
        gs = self.gamma_sat if self.use_sat else self.gamma
        common = dict(gamma=self.gamma, gamma_sat=gs, use_water=self.use_water, hu=self.hu)
        if self.model == "MC":
            return MohrCoulomb(self.name, c=self.c, phi=self.phi, **common)
        if self.model == "HB":
            return HoekBrown(self.name, sigma_ci=self.sigma_ci, gsi=self.gsi, mi=self.mi,
                             d=self.d, **common)
        raise ValueError(f"Bilinmeyen malzeme modeli: {self.model}")


@dataclass
class GeneralSettings:
    units: str = "metric"                     # kN, kPa, m
    failure_direction: str = "right_to_left"  # right_to_left | left_to_right
    data_output: str = "standard"


@dataclass
class MethodSettings:
    methods: list[str] = field(default_factory=lambda: ["bishop", "janbu_simplified",
                                                        "spencer"])
    n_slices: int = 50
    tolerance: float = 0.005
    max_iter: int = 75
    interslice: str = "half-sine"   # GLE: half-sine | constant | clipped-sine | trapezoidal
    f_start: float = 0.5
    f_end: float = 0.5


@dataclass
class GroundwaterSettings:
    method: str = "water_table"               # water_table | ru | none
    gamma_w: float = 9.81
    ru: float = 0.0
    crack_water: float = 0.0                  # tension crack filled fraction (0 dry .. 1 full)


@dataclass
class SeismicSettings:
    kh: float = 0.0
    kv: float = 0.0


@dataclass
class AdvancedSettings:
    check_admissibility: bool = True
    min_depth: float = 0.0


@dataclass
class SurfaceSettings:
    surface_type: str = "circular"            # circular | noncircular | user
    search: str = "auto_refine"
    effort: str = "normal"                    # fast | normal | fine
    n_ctrl: int = 4
    noncircular_shape: str = "polyline"       # polyline (Slide2, straight segments) | spline
    convex_only: bool = True
    seed: int = 0
    left_range: list[float] | None = None     # slope limits, left end
    right_range: list[float] | None = None    # slope limits, right end
    user_surface: list[list[float]] | None = None


EFFORT = {"fast": (12, 50), "normal": (20, 80), "fine": (30, 150)}

DEFAULT_DISPLAY = {
    "external_color": "#606060",
    "material_boundary_color": "#808080",
    "water_table_color": "#1f5fd1",
    "show_vertices": True,
    "line_width": 2,
    "show_ruler": True,
    "show_grid": True,
    "fill_materials": True,
    "show_slope_limits": True,
    "show_slices": True,
    "slice_fill_color": "#f6d65a",
    "show_lines_to_center": True,
    "show_fs_text": True,
    "show_all_surfaces": True,
    "show_legend": True,
    "show_fs_legend": True,
    "material_labels": "none",       # none | name | full
    "label_size": 8,
    "show_control_points": False,    # B-spline control polygon of the critical surface
}


@dataclass
class Project:
    summary: ProjectSummary = field(default_factory=ProjectSummary)
    materials: list[MaterialSpec] = field(default_factory=list)
    external: list[list[float]] = field(default_factory=list)
    material_boundaries: list[list[list[float]]] = field(default_factory=list)
    water_table: list[list[float]] | None = None
    tension_crack: list[list[float]] | None = None
    assignments: list[dict] = field(default_factory=list)
    general: GeneralSettings = field(default_factory=GeneralSettings)
    methods: MethodSettings = field(default_factory=MethodSettings)
    groundwater: GroundwaterSettings = field(default_factory=GroundwaterSettings)
    seismic: SeismicSettings = field(default_factory=SeismicSettings)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    surfaces: SurfaceSettings = field(default_factory=SurfaceSettings)
    loads: list[dict] = field(default_factory=list)
    support_types: list[SupportType] = field(default_factory=list)
    supports: list[dict] = field(default_factory=list)
    support_patterns: list[dict] = field(default_factory=list)
    facing_types: list[FacingType] = field(default_factory=list)
    facings: list[dict] = field(default_factory=list)
    annotations: list[dict] = field(default_factory=list)          # Modeler notes
    result_annotations: list[dict] = field(default_factory=list)   # Interpret notes
    display: dict = field(default_factory=lambda: dict(DEFAULT_DISPLAY))

    # ---------------------------------------------------------- helpers
    @property
    def name(self) -> str:
        return self.summary.title

    def copy(self) -> "Project":
        return copy.deepcopy(self)

    def analysis_inputs(self) -> dict:
        """Comparable solver inputs, excluding presentation-only edits."""
        d = self.to_dict()
        for key in ("summary", "display", "annotations", "result_annotations"):
            d.pop(key)
        return d

    def material_names(self) -> list[str]:
        return [m.name for m in self.materials]

    def material(self, name: str) -> MaterialSpec | None:
        return next((m for m in self.materials if m.name == name), None)

    def colors(self) -> dict[str, str]:
        return {m.name: m.color for m in self.materials}

    def display_opt(self, key):
        return self.display.get(key, DEFAULT_DISPLAY.get(key))

    # ------------------------------------------------------- validation
    def validate(self) -> None:
        names = self.material_names()
        if not names:
            raise ValueError("En az bir malzeme tanımlayın.")
        if len(set(names)) != len(names):
            raise ValueError("Malzeme adları benzersiz olmalı.")
        for m in self.materials:
            if not m.name.strip():
                raise ValueError("Malzeme adı boş olamaz.")
            if m.gamma <= 0 or m.gamma_sat <= 0:
                raise ValueError(f"{m.name}: birim hacim ağırlıklar pozitif olmalı.")
            if m.model == "MC" and (m.c < 0 or not 0 <= m.phi < 90):
                raise ValueError(f"{m.name}: c ≥ 0 ve 0 ≤ φ < 90 olmalı.")
            if m.model == "HB" and (m.sigma_ci <= 0 or not 0 < m.gsi <= 100 or m.mi <= 0
                                    or not 0 <= m.d <= 1):
                raise ValueError(f"{m.name}: σci > 0, 0 < GSI ≤ 100, mi > 0, 0 ≤ D ≤ 1 olmalı.")
        for a in self.assignments:
            if a["material"] not in names:
                raise ValueError(f"Atanmış malzeme '{a['material']}' tanımlı değil.")
        tc = self.tension_crack
        if tc:
            xs = sorted(q[0] for q in tc)
            if len(tc) < 2 or any(b <= a for a, b in zip(xs, xs[1:])):
                raise ValueError("Gerilme çatlağı çizgisi en az 2 nokta ve farklı x değerleri "
                                 "içermeli.")
        if not 0 <= self.groundwater.crack_water <= 1:
            raise ValueError("Çatlak suyu oranı 0 ile 1 arasında olmalı.")
        snames = [t.name for t in self.support_types]
        if len(set(snames)) != len(snames):
            raise ValueError("Destek tipi adları benzersiz olmalı.")
        for t in self.support_types:
            if t.kind not in SUPPORT_KINDS:
                raise ValueError(f"{t.name}: bilinmeyen destek tipi.")
            if t.spacing <= 0 or t.tensile < 0:
                raise ValueError(f"{t.name}: aralık > 0 ve kapasite ≥ 0 olmalı.")
        for sp in self.supports + self.support_patterns:
            if sp["type"] not in snames:
                raise ValueError(f"Destek tipi '{sp['type']}' tanımlı değil.")
        for pt in self.support_patterns:
            if pt["spacing"] <= 0 or pt["length"] <= 0:
                raise ValueError("Bulon paterni: aralık ve boy pozitif olmalı.")
        fnames = [t.name for t in self.facing_types]
        if len(set(fnames)) != len(fnames):
            raise ValueError("Kaplama tipi adları benzersiz olmalı.")
        for t in self.facing_types:
            if t.thickness <= 0 or t.gamma < 0 or t.tau < 0 or t.mesh_as < 0:
                raise ValueError(f"{t.name}: kalınlık > 0, diğer değerler ≥ 0 olmalı.")
        for f in self.facings:
            if f["type"] not in fnames:
                raise ValueError(f"Kaplama tipi '{f['type']}' tanımlı değil.")
        for k in self.methods.methods:
            if k not in METHODS:
                raise ValueError(f"Bilinmeyen yöntem: {k}")
        if self.methods.n_slices < 3:
            raise ValueError("Dilim sayısı en az 3 olmalı.")

    @property
    def has_geometry(self) -> bool:
        return len(self.external) >= 3

    # ------------------------------------------------------------ build
    def build_geometry(self) -> SlopeGeometry:
        self.validate()
        if not self.has_geometry:
            raise ValueError("Dış sınır tanımlı değil (Sınırlar → Dış Sınır Ekle).")
        assign = [(a["point"][0], a["point"][1], a["material"]) for a in self.assignments]
        return boundary_geometry(self.external, self.material_boundaries, assign,
                                 self.materials[0].name, self.water_table, self.name)

    def build_materials(self) -> dict[str, Material]:
        self.validate()
        return {m.name: m.to_material() for m in self.materials}

    def support_type(self, name: str) -> SupportType | None:
        return next((t for t in self.support_types if t.name == name), None)

    def load_set(self) -> LoadSet:
        ls = LoadSet()
        for ld in self.loads:
            if ld["kind"] == "distributed":
                (x1, _), (x2, _) = ld["points"]
                q1, q2 = ld["q"]
                if x2 < x1:
                    x1, x2, q1, q2 = x2, x1, q2, q1
                ls.distributed.append(DistributedLoad(x1, x2, q1, q2,
                                                      ld.get("orientation", "vertical")))
            elif ld["kind"] == "line":
                x, y = ld["point"]
                ls.line.append(LineLoad(x, y, ld["magnitude"], ld.get("angle", 270.0)))
        for i, sp in enumerate(self.supports):
            st = self.support_type(sp["type"])
            if st is not None:
                ls.supports.append(Support(tuple(sp["a"]), tuple(sp["b"]), st,
                                           f"Destek {i + 1}"))
        geom = None
        for j, pt in enumerate(self.support_patterns):
            st = self.support_type(pt["type"])
            if st is None:
                continue
            if geom is None:
                geom = self.build_geometry()
            for k, (a, b) in enumerate(self.pattern_bolts(pt, geom)):
                ls.supports.append(Support(tuple(a), tuple(b), st, f"Patern {j + 1}/{k + 1}"))
        for f in self.facings:
            ft = self.facing_type(f["type"])
            if ft is not None:
                ls.facings.append(Facing(f["x1"], f["x2"], ft))
        return ls

    def facing_type(self, name: str) -> FacingType | None:
        return next((t for t in self.facing_types if t.name == name), None)

    @staticmethod
    def pattern_bolts(pt: dict, geom) -> list:
        """(A, B) of every bolt of a pattern, heads on the ground surface."""
        xs = pattern_positions(geom, pt["p1"][0], pt["p2"][0], pt["spacing"],
                               pt.get("offset", 0.0))
        return [bolt_at(geom, x, pt.get("angle", 15.0), pt["length"]) for x in xs]

    def slice_options(self) -> SliceOptions:
        gw = self.groundwater
        pore = gw.method
        if pore == "water_table" and not self.water_table:
            pore = "none"
        ls = self.load_set()
        return SliceOptions(n_slices=self.methods.n_slices, gamma_w=gw.gamma_w, pore=pore,
                            ru=gw.ru, kh=self.seismic.kh, kv=self.seismic.kv,
                            direction=self.general.failure_direction,
                            min_depth=self.advanced.min_depth,
                            loads=None if ls.empty else ls,
                            crack=self.crack())

    def crack(self) -> TensionCrack | None:
        tc = self.tension_crack
        if not tc or len(tc) < 2:
            return None
        return TensionCrack(sorted(map(tuple, tc)), self.groundwater.crack_water,
                            self.groundwater.gamma_w)

    def solver_kw(self) -> dict:
        m = self.methods
        return {"tol": m.tolerance * 1e-2, "max_iter": m.max_iter, "interslice": m.interslice,
                "f_start": m.f_start, "f_end": m.f_end}

    # ------------------------------------------------------------- JSON
    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "version": VERSION,
            "summary": asdict(self.summary),
            "materials": [asdict(m) for m in self.materials],
            "geometry": {
                "external": self.external,
                "material_boundaries": self.material_boundaries,
                "water_table": self.water_table,
                "tension_crack": self.tension_crack,
                "assignments": self.assignments,
            },
            "settings": {
                "general": asdict(self.general),
                "methods": asdict(self.methods),
                "groundwater": asdict(self.groundwater),
                "seismic": asdict(self.seismic),
                "advanced": asdict(self.advanced),
            },
            "surfaces": asdict(self.surfaces),
            "loads": self.loads,
            "support_types": [asdict(t) for t in self.support_types],
            "supports": self.supports,
            "support_patterns": self.support_patterns,
            "facing_types": [asdict(t) for t in self.facing_types],
            "facings": self.facings,
            "annotations": self.annotations,
            "result_annotations": self.result_annotations,
            "display": dict(self.display),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        if d.get("format") != FORMAT:
            raise ValueError("Bu dosya bir SlipSurface LE projesi değil.")
        ver = int(d.get("version", 0))
        if ver > VERSION:
            raise ValueError("Dosya daha yeni bir sürümle kaydedilmiş.")
        if ver < 2:
            return _from_v1(d)
        g, st = d.get("geometry", {}), d.get("settings", {})
        disp = dict(DEFAULT_DISPLAY)
        disp.update(d.get("display", {}))
        return cls(
            summary=_from_dict(ProjectSummary, d.get("summary")),
            materials=[_from_dict(MaterialSpec, m) for m in d.get("materials", [])],
            external=[list(map(float, p)) for p in g.get("external", [])],
            material_boundaries=[[list(map(float, p)) for p in b]
                                 for b in g.get("material_boundaries", [])],
            water_table=([list(map(float, p)) for p in g["water_table"]]
                         if g.get("water_table") else None),
            tension_crack=([list(map(float, p)) for p in g["tension_crack"]]
                           if g.get("tension_crack") else None),
            assignments=[{"point": list(map(float, a["point"])), "material": a["material"]}
                         for a in g.get("assignments", [])],
            general=_from_dict(GeneralSettings, st.get("general")),
            methods=_from_dict(MethodSettings, st.get("methods")),
            groundwater=_from_dict(GroundwaterSettings, st.get("groundwater")),
            seismic=_from_dict(SeismicSettings, st.get("seismic")),
            advanced=_from_dict(AdvancedSettings, st.get("advanced")),
            surfaces=_from_dict(SurfaceSettings, d.get("surfaces")),
            loads=[dict(ld) for ld in d.get("loads", [])],
            support_types=[_from_dict(SupportType, t) for t in d.get("support_types", [])],
            supports=[{"a": list(map(float, sp["a"])), "b": list(map(float, sp["b"])),
                       "type": sp["type"]} for sp in d.get("supports", [])],
            support_patterns=[dict(p) for p in d.get("support_patterns", [])],
            facing_types=[_from_dict(FacingType, t) for t in d.get("facing_types", [])],
            facings=[dict(f) for f in d.get("facings", [])],
            annotations=[dict(a) for a in d.get("annotations", [])],
            result_annotations=[dict(a) for a in d.get("result_annotations", [])],
            display=disp,
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=f".{path.name}.", suffix=".tmp",
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ------------------------------------------------------------ v1 import
def _from_v1(d: dict) -> Project:
    """Convert a v1 file (ground surface + layer stack) to boundaries."""
    from slipsurface.geometry import layered_geometry

    g = d["geometry"]
    surface = np.asarray(g["surface"], float)
    layers = [(lay["material"], None if i == 0 else np.asarray(lay["top"], float))
              for i, lay in enumerate(g["layers"])]
    old = layered_geometry(surface, float(g["bottom"]), layers)
    ext = np.asarray(old.domain.exterior.coords)[:-1].tolist()
    x0, x1 = surface[0, 0], surface[-1, 0]
    bounds = []
    for top in old.meta.get("boundaries", []):
        line = np.asarray(top, float)
        line = line[np.argsort(line[:, 0])]
        if line[0, 0] > x0:
            line = np.vstack([[x0, line[0, 1]], line])
        if line[-1, 0] < x1:
            line = np.vstack([line, [x1, line[-1, 1]]])
        bounds.append(line.tolist())
    assigns = [{"point": list(r.polygon.representative_point().coords[0]),
                "material": r.material} for r in old.regions]
    mats = []
    for m in d.get("materials", []):
        spec = _from_dict(MaterialSpec, m)
        spec.use_sat = m.get("gamma_sat", spec.gamma) != m.get("gamma", spec.gamma)
        mats.append(spec)
    w = d.get("water", {})
    a = d.get("analysis", {})
    p = Project(summary=ProjectSummary(title=d.get("name", "Model")), materials=mats,
                external=ext, material_boundaries=bounds,
                water_table=w.get("points") if w.get("enabled") else None,
                assignments=assigns)
    p.groundwater.gamma_w = float(w.get("gamma_w", 9.81))
    if a.get("method") in METHODS:
        p.methods.methods = [a["method"]]
    p.methods.n_slices = int(a.get("n_slices", p.methods.n_slices))
    return p


# ---------------------------------------------------------------- presets
def _mk(title, mats, ext, bounds=(), wt=None, assigns=(), methods=None, n_slices=None):
    p = Project(summary=ProjectSummary(title=title), materials=list(mats),
                external=[list(map(float, q)) for q in ext],
                material_boundaries=[[list(map(float, q)) for q in b] for b in bounds],
                water_table=wt,
                assignments=[{"point": list(map(float, pt)), "material": m}
                             for pt, m in assigns])
    if methods:
        p.methods.methods = list(methods)
    if n_slices:
        p.methods.n_slices = n_slices
    return p


def default_project() -> Project:
    """10 m high 2H:1V homogeneous slope."""
    return _mk("Basit şev H=10 m, 2H:1V",
               [MaterialSpec("Zemin 1", "MC", 18, 20, False, 10, 30, color=PALETTE[0])],
               [[0, -10], [55, -10], [55, 10], [35, 10], [15, 0], [0, 0]])


def empty_project() -> Project:
    return _mk("Yeni proje", [MaterialSpec("Zemin 1", color=PALETTE[0])], [])


def acads_1a_project() -> Project:
    return _mk("ACADS EX1(a) — homojen şev",
               [MaterialSpec("Zemin 1", "MC", 20, 20, False, 3, 19.6, color=PALETTE[0])],
               [[0, -5], [60, -5], [60, 10], [40, 10], [20, 0], [0, 0]],
               methods=["bishop", "spencer", "gle", "janbu_simplified"], n_slices=30)


def layered_example_project() -> Project:
    """Three materials, a weak clay band outcropping on the face, water table."""
    return _mk(
        "Katmanlı şev + YASS (örnek)",
        [MaterialSpec("Dolgu", "MC", 19, 20, True, 8, 32, color=PALETTE[0]),
         MaterialSpec("Yumuşak kil", "MC", 17, 18, True, 15, 18, color=PALETTE[3]),
         MaterialSpec("Ayrışmış kaya", "HB", 23, 24, True, sigma_ci=8_000, gsi=35, mi=8,
                      d=0.3, color=PALETTE[2])],
        [[0, -12], [70, -12], [70, 14], [50, 12], [40, 12], [20, 0], [0, 0]],
        bounds=[[[0, -1], [70, 5]], [[0, -5], [70, -2]]],
        wt=[[0, -0.5], [20, -0.5], [45, 6], [70, 8]],
        assigns=[((60, 10), "Dolgu"), ((60, 2), "Yumuşak kil"), ((60, -6), "Ayrışmış kaya")],
        n_slices=30)


def anchored_example_project() -> Project:
    """Steep cut with a crest surcharge, stabilised by two rows of grouted tiebacks."""
    p = _mk("Ankrajlı yarma + sürşarj (örnek)",
            [MaterialSpec("Kumlu kil", "MC", 19, 20, True, 12, 26, color=PALETTE[0])],
            [[0, -8], [50, -8], [50, 12], [26, 12], [18, 0], [0, 0]], n_slices=40,
            methods=["bishop", "spencer", "janbu_corrected"])
    p.support_types = [SupportType("Tieback 1", "grouted_tieback", spacing=2.0, tensile=400,
                                   bond_strength=60, bond_length=6, application="active")]
    p.supports = [{"a": [21.33, 5.0], "b": [37.0, -0.5], "type": "Tieback 1"},
                  {"a": [24.0, 9.0], "b": [40.0, 3.5], "type": "Tieback 1"}]
    p.loads = [{"kind": "distributed", "points": [[29, 12], [37, 12]], "q": [20, 20],
                "orientation": "vertical"},
               {"kind": "line", "point": [42, 12], "magnitude": 60, "angle": 270.0}]
    return p


def cracked_example_project() -> Project:
    """Cohesive slope with a water-filled tension crack in the crest zone."""
    p = _mk("Gerilme çatlaklı şev (çatlak dolu)",
            [MaterialSpec("Katı kil", "MC", 19, 20, False, 18, 20, color=PALETTE[1])],
            [[0, -10], [60, -10], [60, 12], [32, 12], [14, 0], [0, 0]], n_slices=40,
            methods=["bishop", "spencer", "gle"])
    p.tension_crack = [[32.0, 9.0], [60.0, 9.0]]
    p.groundwater.crack_water = 1.0
    return p


def nailed_shotcrete_project() -> Project:
    """Steep cut stabilised with a soil-nail pattern (15°) and a shotcrete +
    wire mesh facing on the slope face."""
    p = _mk("Zemin çivili + püskürtme betonlu yarma (örnek)",
            [MaterialSpec("Siltli kum", "MC", 19, 20, False, 8, 30, color=PALETTE[0]),
             MaterialSpec("Ayrışmış kaya", "MC", 22, 23, False, 40, 36, color=PALETTE[2])],
            [[0, -8], [48, -8], [48, 12], [26, 12], [20, 0], [0, 0]], n_slices=40,
            methods=["bishop", "spencer", "janbu_corrected"])
    p.material_boundaries = [[[0, -3], [48, -3]]]
    p.assignments = [{"point": [24, 5], "material": "Siltli kum"},
                     {"point": [24, -6], "material": "Ayrışmış kaya"}]
    p.support_types = [SupportType("Çivi Ø28", "soil_nail", spacing=1.5, tensile=240,
                                   plate=80, bond_strength=40, application="passive",
                                   color="#1f3d7a", length=9.0)]
    p.support_patterns = [{"p1": [20.0, 0.0], "p2": [26.0, 12.0], "spacing": 1.5,
                           "offset": 0.75, "angle": 15.0, "length": 9.0, "type": "Çivi Ø28"}]
    p.facing_types = [FacingType("Püskürtme beton 10 cm + Q188")]
    p.facings = [{"x1": 20.0, "x2": 26.0, "type": "Püskürtme beton 10 cm + Q188",
                  "points": [[20.0, 0.0], [26.0, 12.0]]}]
    p.loads = [{"kind": "distributed", "points": [[29, 12], [40, 12]], "q": [15, 15],
                "orientation": "vertical"}]
    p.annotations = [{"kind": "text", "pts": [[30.0, 17.0]], "text":
                      "Zemin çivisi paterni: 1.5 m aralık, 15°, L = 9 m\n"
                      "Kaplama: 10 cm püskürtme beton + Q188", "color": "#1b2a3a",
                      "size": 9, "bold": False, "box": True},
                     {"kind": "arrow", "pts": [[29.5, 16.0], [24.5, 9.5]], "color": "#c0392b",
                      "width": 1.5}]
    p.display["material_labels"] = "full"
    return p


EXAMPLES = {
    "Basit şev (10 m, 2H:1V)": default_project,
    "ACADS EX1(a)": acads_1a_project,
    "Katmanlı şev + YASS": layered_example_project,
    "Ankrajlı yarma + sürşarj": anchored_example_project,
    "Gerilme çatlaklı şev": cracked_example_project,
    "Zemin çivisi + püskürtme beton": nailed_shotcrete_project,
}
