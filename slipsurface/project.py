"""Project model (file format v2/v3): Slide2-style boundaries + all settings.

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
from typing import Any

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
from slipsurface.materials import (
    BartonBandis,
    CNIRockMass,
    HardeningSoil,
    HoekBrown,
    HoekBrownDirect,
    Material,
    MohrCoulomb,
    PowerCurve,
    PowerLaw,
    Sanisand,
    Shansep,
    Undrained,
    UndrainedDepth,
)
from slipsurface.materials.catalog import MODELS

FORMAT = "slipsurface-le"
VERSION = 4  # newest format this program reads
BASE_VERSION = 3  # written unless a version-4 feature is used (see Project.file_version)
PALETTE = [
    "#f0c800",
    "#3cb371",
    "#ff7f3f",
    "#8080d0",
    "#8b8b00",
    "#c97bb4",
    "#5fb3c9",
    "#c4a484",
    "#9acd32",
    "#d2691e",
]


def _today() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d, %H:%M:%S")


def _from_dict(cls, d: dict | None):
    """Dataclass from stored values. A value of the wrong basic type is
    refused here: the dialogs pass these straight to spin boxes and combos."""
    if d is not None and not isinstance(d, dict):
        raise ValueError(f"{cls.__name__}: an object with named values is required.")
    stored = d or {}
    defaults = cls()
    values = {}
    for key in (f.name for f in fields(cls)):
        if stored.get(key) is None:
            continue
        value, default = stored[key], getattr(defaults, key)
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, int):
            ok = number  # 30.0 is read as 30; 3.5 is kept for validate() to name
            if ok and float(value).is_integer():
                value = int(value)
        elif isinstance(default, float):
            ok = number
        elif isinstance(default, str):
            ok = isinstance(value, str)
        else:
            ok = True  # lists and optional values are checked by validate()
        if not ok:
            raise ValueError(
                f"{cls.__name__}.{key}: a value like {default!r} is required (found {value!r})."
            )
        values[key] = value
    return cls(**values)


def _finite_inputs(value, path="project") -> None:
    """Reject NaN/Infinity, including values accepted by Python's JSON reader."""
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_inputs(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _finite_inputs(item, f"{path}[{i}]")
    elif isinstance(value, (float, np.floating)) and not np.isfinite(value):
        raise ValueError(f"{path}: a finite number is required.")


def _choice(value, allowed, label) -> None:
    if value not in allowed:
        raise ValueError(f"{label}: unknown option '{value}'.")


def _validate_loads(loads) -> None:
    def numbers(value, shape):
        a = np.asarray(value)
        if a.shape != shape or a.dtype.kind not in "iuf":
            raise ValueError(f"numeric data in the form {shape} is required")
        return a.astype(float)

    for i, ld in enumerate(loads, 1):
        label = f"Load {i}"
        kind = ld.get("kind")
        _choice(kind, ("distributed", "line"), label)
        try:
            if kind == "distributed":
                pts, q = numbers(ld["points"], (2, 2)), numbers(ld["q"], (2,))
                if pts[0, 0] == pts[1, 0]:
                    raise ValueError("distributed load horizontal length must be positive")
                _choice(ld.get("orientation", "vertical"), ("vertical", "normal"), label)
                values = np.concatenate([pts.ravel(), q])
            else:
                pt = numbers(ld["point"], (2,))
                magnitude = float(numbers(ld["magnitude"], ()))
                angle = float(numbers(ld.get("angle", 270), ()))
                values = np.array([*pt, magnitude, angle])
            if not np.all(np.isfinite(values)):
                raise ValueError("load values must be finite")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{label}: invalid load data ({exc}).") from None


ANNOTATION_KINDS = ("text", "line", "arrow", "rect", "ellipse")


def _is_number(value) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool)


def _is_point(value) -> bool:
    return (
        isinstance(value, (list, tuple)) and len(value) == 2 and all(_is_number(c) for c in value)
    )


def _validate_structure(p: Project) -> None:
    """Reject lists whose entries do not have the shape the drawing and the
    solver read (a hand-edited or damaged file, a script). Without this the
    first repaint fails on a missing key instead of naming the entry."""

    def entry(item, label) -> dict:
        if not isinstance(item, dict):
            raise ValueError(f"{label}: an object with named values is required.")
        return item

    def point(item, key, label) -> None:
        if not _is_point(item.get(key)):
            raise ValueError(f"{label}: '{key}' must be an [x, y] pair of numbers.")

    def number(item, key, label, required=True) -> None:
        if key not in item and not required:
            return
        if not _is_number(item.get(key)):
            raise ValueError(f"{label}: '{key}' must be a number.")

    def name(item, key, label) -> None:
        if not isinstance(item.get(key), str):
            raise ValueError(f"{label}: '{key}' must be a name.")

    if not (isinstance(p.external, (list, tuple)) and all(_is_point(q) for q in p.external)):
        raise ValueError("External boundary: a list of [x, y] pairs is required.")
    if not isinstance(p.material_boundaries, (list, tuple)):
        raise ValueError("Material boundaries: a list of polylines is required.")
    for i, b in enumerate(p.material_boundaries, 1):
        if not (isinstance(b, (list, tuple)) and all(_is_point(q) for q in b)):
            raise ValueError(f"Material boundary {i}: a list of [x, y] pairs is required.")
    for label, line in (
        ("Water table", p.water_table),
        ("Tension crack", p.tension_crack),
    ):
        if line is not None and not (
            isinstance(line, (list, tuple)) and all(_is_point(q) for q in line)
        ):
            raise ValueError(f"{label}: a list of [x, y] pairs is required.")
    for m in p.materials:
        if m.model not in MODELS:
            raise ValueError(
                f"{m.name}: unknown material model '{m.model}' (must be {', '.join(MODELS)})."
            )
    for i, ld in enumerate(p.loads, 1):
        label = f"Load {i}"
        kind = entry(ld, label).get("kind")
        if kind == "distributed":
            pts, q = ld.get("points"), ld.get("q")
            if not (
                isinstance(pts, (list, tuple)) and len(pts) == 2 and all(_is_point(v) for v in pts)
            ):
                raise ValueError(f"{label}: 'points' must be two [x, y] pairs.")
            if not _is_point(q):
                raise ValueError(f"{label}: 'q' must be a [q1, q2] pair of numbers.")
        elif kind == "line":
            point(ld, "point", label)
            number(ld, "magnitude", label)
            number(ld, "angle", label, required=False)
        else:
            raise ValueError(f"{label}: unknown option '{kind}'.")
    for i, a in enumerate(p.assignments, 1):
        label = f"Material assignment {i}"
        point(entry(a, label), "point", label)
        name(a, "material", label)
    for i, sp in enumerate(p.supports, 1):
        label = f"Support {i}"
        entry(sp, label)
        point(sp, "a", label)
        point(sp, "b", label)
        name(sp, "type", label)
    for i, pt in enumerate(p.support_patterns, 1):
        label = f"Bolt pattern {i}"
        entry(pt, label)
        point(pt, "p1", label)
        point(pt, "p2", label)
        name(pt, "type", label)
        number(pt, "spacing", label)
        number(pt, "length", label)
        number(pt, "offset", label, required=False)
        number(pt, "angle", label, required=False)
    for i, f in enumerate(p.facings, 1):
        label = f"Facing {i}"
        entry(f, label)
        number(f, "x1", label)
        number(f, "x2", label)
        name(f, "type", label)
        pts = f.get("points")
        if pts is not None and not (
            isinstance(pts, (list, tuple)) and len(pts) == 2 and all(_is_point(q) for q in pts)
        ):
            raise ValueError(f"{label}: 'points' must be two [x, y] pairs.")
    for title, notes in (("Note", p.annotations), ("Result note", p.result_annotations)):
        for i, a in enumerate(notes, 1):
            label = f"{title} {i}"
            kind = entry(a, label).get("kind")
            if kind not in ANNOTATION_KINDS:
                raise ValueError(f"{label}: unknown kind '{kind}'.")
            pts = a.get("pts")
            need = 1 if kind == "text" else 2
            if not (
                isinstance(pts, (list, tuple))
                and len(pts) >= need
                and all(_is_point(q) for q in pts)
            ):
                raise ValueError(f"{label}: 'pts' must hold at least {need} [x, y] pair(s).")
    for label, rng in (
        ("Left slip limit", p.surfaces.left_range),
        ("Right slip limit", p.surfaces.right_range),
    ):
        if rng is not None and not _is_point(rng):
            raise ValueError(f"{label}: a [start, end] pair of numbers is required.")
    us = p.surfaces.user_surface
    if us is not None and not (isinstance(us, (list, tuple)) and all(_is_point(q) for q in us)):
        raise ValueError("User surface: a list of [x, y] pairs is required.")


def _clean_display(display: dict) -> dict:
    """Display options of the expected type; anything else falls back to the default."""
    out = dict(DEFAULT_DISPLAY)
    for key, value in display.items():
        default = DEFAULT_DISPLAY.get(key)
        if default is None:
            out[key] = value  # option of another version: keep as stored
        elif isinstance(default, bool):
            if isinstance(value, bool):
                out[key] = value
        elif isinstance(default, int):
            if _is_number(value) and float(value).is_integer() and value >= 1:
                out[key] = int(value)
        elif isinstance(default, float):
            if _is_number(value) and np.isfinite(value) and float(value) > 0:
                out[key] = float(value)
        elif isinstance(value, str):
            out[key] = value
    return out


# ------------------------------------------------------------------ parts
@dataclass
class ProjectSummary:
    title: str = "New Project"
    analysis: str = ""
    author: str = ""
    company: str = ""
    date_created: str = field(default_factory=_today)
    comments: list[str] = field(default_factory=lambda: [""] * 5)


@dataclass
class MaterialSpec:
    name: str = "Soil 1"
    model: str = "MC"  # key of slipsurface.materials.catalog.MODELS
    gamma: float = 19.0
    gamma_sat: float = 20.0
    use_sat: bool = False  # Slide2: saturated unit weight checkbox
    c: float = 5.0
    phi: float = 30.0
    sigma_ci: float = 25_000.0  # kPa
    gsi: float = 50.0
    mi: float = 10.0
    d: float = 0.0
    use_water: bool = True  # water table acts on this material
    hu: float = 1.0
    bbar: float = 0.0  # excess pore pressure coefficient (undrained loading)
    excess_load: bool = False  # its weight creates excess pore pressure in B-bar materials
    color: str = PALETTE[0]

    su: float = 25.0
    su_top: float = 25.0
    su_bottom: float = 25.0
    su_y_top: float = 0.0
    su_y_bottom: float = -1.0
    coefficient: float = 0.2
    exponent: float = 0.5
    reference_pressure: float = 100.0
    # SHANSEP
    shansep_s: float = 0.22
    shansep_m: float = 0.8
    ocr: float = 1.0
    shansep_su_min: float = 0.0  # additive intercept A [kPa]; keep the JSON key
    # OCR profile: `ocr` at ocr_y_top to ocr_bottom at ocr_y_bottom; equal elevations = constant
    ocr_bottom: float = 1.0
    ocr_y_top: float = 0.0
    ocr_y_bottom: float = 0.0
    # Hardening Soil (failure envelope c, phi above)
    hs_psi: float = 0.0
    hs_e50: float = 30_000.0
    hs_eoed: float = 30_000.0
    hs_eur: float = 90_000.0
    hs_m: float = 0.5
    hs_pref: float = 100.0
    hs_rf: float = 0.9
    # SANISAND (Toyoura sand defaults, Dafalias & Manzari 2004)
    ss_m: float = 1.25
    ss_e: float = 0.75
    ss_ec0: float = 0.934
    ss_lambda: float = 0.019
    ss_xi: float = 0.7
    ss_nb: float = 1.1
    ss_pat: float = 101.3
    # Power Curve
    pc_a: float = 1.5
    pc_b: float = 0.8
    pc_c: float = 0.0
    pc_d: float = 0.0
    # Barton-Bandis
    bb_phir: float = 25.0
    bb_jrc: float = 10.0
    bb_jcs: float = 50_000.0
    bb_l0: float = 0.1
    bb_ln: float = 0.1
    # CNI rock mass
    cni_sigma_c: float = 10_000.0
    cni_a: float = 0.6
    cni_n: float = 0.75
    cni_t: float = 100.0
    # Hoek-Brown with direct mb, s, a
    hb_mb: float = 1.0
    hb_s: float = 0.001
    hb_a: float = 0.5

    def to_material(self) -> Material:
        gs = self.gamma_sat if self.use_sat else self.gamma
        common: dict[str, Any] = dict(
            gamma=self.gamma,
            gamma_sat=gs,
            use_water=self.use_water,
            hu=self.hu,
            bbar=self.bbar,
            excess_load=self.excess_load,
        )
        if self.model == "UD":
            return Undrained(self.name, su=self.su, **common)
        if self.model == "UDG":
            return UndrainedDepth(
                self.name,
                su_top=self.su_top,
                su_bottom=self.su_bottom,
                y_top=self.su_y_top,
                y_bottom=self.su_y_bottom,
                **common,
            )
        if self.model == "PL":
            return PowerLaw(
                self.name,
                coefficient=self.coefficient,
                exponent=self.exponent,
                reference_pressure=self.reference_pressure,
                **common,
            )
        if self.model == "MC":
            return MohrCoulomb(self.name, c=self.c, phi=self.phi, **common)
        if self.model == "HB":
            return HoekBrown(
                self.name, sigma_ci=self.sigma_ci, gsi=self.gsi, mi=self.mi, d=self.d, **common
            )
        if self.model == "HBD":
            return HoekBrownDirect(
                self.name,
                sigma_ci=self.sigma_ci,
                mb_in=self.hb_mb,
                s_in=self.hb_s,
                a_in=self.hb_a,
                **common,
            )
        if self.model == "SH":
            return Shansep(
                self.name,
                s_ratio=self.shansep_s,
                m_exp=self.shansep_m,
                ocr=self.ocr,
                su_min=self.shansep_su_min,
                ocr_bottom=self.ocr_bottom,
                y_top=self.ocr_y_top,
                y_bottom=self.ocr_y_bottom,
                **common,
            )
        if self.model == "HS":
            return HardeningSoil(
                self.name,
                c=self.c,
                phi=self.phi,
                psi=self.hs_psi,
                e50_ref=self.hs_e50,
                eoed_ref=self.hs_eoed,
                eur_ref=self.hs_eur,
                m_power=self.hs_m,
                p_ref=self.hs_pref,
                rf=self.hs_rf,
                **common,
            )
        if self.model == "SS":
            return Sanisand(
                self.name,
                m_c=self.ss_m,
                void_ratio=self.ss_e,
                e_c0=self.ss_ec0,
                lambda_c=self.ss_lambda,
                xi=self.ss_xi,
                n_b=self.ss_nb,
                p_at=self.ss_pat,
                **common,
            )
        if self.model == "PC":
            return PowerCurve(
                self.name, pc_a=self.pc_a, pc_b=self.pc_b, pc_c=self.pc_c, pc_d=self.pc_d, **common
            )
        if self.model == "BB":
            return BartonBandis(
                self.name,
                phi_r=self.bb_phir,
                jrc=self.bb_jrc,
                jcs=self.bb_jcs,
                l0=self.bb_l0,
                ln=self.bb_ln,
                **common,
            )
        if self.model == "CN":
            return CNIRockMass(
                self.name,
                sigma_cm=self.cni_sigma_c,
                cni_a=self.cni_a,
                cni_n=self.cni_n,
                tensile=self.cni_t,
                **common,
            )
        raise ValueError(f"Unknown material model: {self.model}")


@dataclass
class GeneralSettings:
    units: str = "metric"  # kN, kPa, m
    failure_direction: str = "right_to_left"  # right_to_left | left_to_right
    data_output: str = "standard"


@dataclass
class MethodSettings:
    methods: list[str] = field(default_factory=lambda: ["bishop", "janbu_simplified", "spencer"])
    n_slices: int = 50
    tolerance: float = 0.005
    max_iter: int = 75
    interslice: str = "half-sine"  # GLE: half-sine | constant | clipped-sine | trapezoidal
    f_start: float = 0.5
    f_end: float = 0.5


@dataclass
class GroundwaterSettings:
    method: str = "water_table"  # water_table | ru | none
    gamma_w: float = 9.81
    ru: float = 0.0
    crack_water: float = 0.0  # tension crack filled fraction (0 dry .. 1 full)


# Positive kv is upward (vertical load (1-kv)W). Slide2's positive kv is downward.
SEISMIC_BOTH = (
    "kh = {}, kv = ±{} (positive upward, vertical load (1 − kv)·W; in Slide2 "
    "a positive kv acts downward)"
)
SEISMIC_ONE = "kh = {}, kv = {} ({}; Slide2 kv = {}; vertical load (1 − kv)·W)"
SEISMIC_NOTE = (
    "The horizontal force kh·W acts in the failure direction at the slice "
    "centroid. Positive kv is upward: vertical load (1 − kv)·W. In Slide2 a "
    "positive kv acts downward (the sign is opposite)."
)


@dataclass
class SeismicSettings:
    kh: float = 0.0
    kv: float = 0.0  # positive upward: vertical load is (1 - kv) W
    # Solve -kv as well and keep the lower factor of safety.
    both_vertical: bool = True

    def clause(self) -> str:
        """Seismic summary line. Positive kv is upward; Slide2's positive kv is downward."""
        kh, kv = self.kh, self.kv
        if self.both_vertical and kv != 0.0:
            return SEISMIC_BOTH.format(f"{kh:g}", f"{abs(kv):g}")
        sense = "upward" if kv > 0 else ("downward" if kv < 0 else "zero")
        return SEISMIC_ONE.format(f"{kh:g}", f"{kv:g}", sense, f"{-kv:g}")


@dataclass
class AdvancedSettings:
    check_admissibility: bool = True
    min_depth: float = 0.0
    m_alpha_min: float = 0.2  # admissibility threshold (Whitman & Bailey)
    e_max_ratio: float = 50.0  # reject interslice forces > ratio * total weight


@dataclass
class SurfaceSettings:
    surface_type: str = "circular"  # circular | noncircular | user
    search: str = "auto_refine"
    effort: str = "normal"  # fast | normal | fine
    n_ctrl: int = 4
    noncircular_shape: str = "polyline"  # polyline (Slide2, straight segments) | spline
    convex_only: bool = True
    seed: int = 0
    left_range: list[float] | None = None  # slope limits, left end
    right_range: list[float] | None = None  # slope limits, right end
    user_surface: list[list[float]] | None = None
    user_circle: list[float] | None = None  # exact fixed circle [xc, yc, radius]


EFFORT = {"fast": (12, 50), "normal": (20, 80), "fine": (30, 150)}

DEFAULT_DISPLAY = {
    "external_color": "#606060",
    "material_boundary_color": "#808080",
    "water_table_color": "#1f5fd1",
    "show_vertices": True,
    "line_width": 2,
    "show_ruler": True,
    "show_grid": True,
    "grid_spacing": 1.0,
    "fill_materials": True,
    "show_slope_limits": True,
    "show_slices": False,
    "slice_fill_color": "#f6d65a",
    "show_lines_to_center": True,
    "show_fs_text": True,
    "show_all_surfaces": False,
    "show_fs_contours": True,  # slip-centre FS contour map (circular searches)
    "critical_dashed": True,  # critical surface as a dashed line
    "show_legend": True,
    "show_fs_legend": True,
    "material_labels": "none",  # none | name | full
    "label_size": 8,
    "show_control_points": False,  # B-spline control polygon of the critical surface
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
    annotations: list[dict] = field(default_factory=list)  # Modeler notes
    result_annotations: list[dict] = field(default_factory=list)  # Interpret notes
    display: dict = field(default_factory=lambda: dict(DEFAULT_DISPLAY))

    # ---------------------------------------------------------- helpers
    @property
    def name(self) -> str:
        return self.summary.title

    def copy(self) -> Project:
        return copy.deepcopy(self)

    def analysis_inputs(self) -> dict:
        """Comparable solver inputs, excluding presentation-only edits."""
        d = self.to_dict()
        for key in ("summary", "display", "annotations", "result_annotations"):
            d.pop(key, None)
        for m in d.get("materials", []):
            m.pop("color", None)
        for t in d.get("support_types", []):
            t.pop("color", None)
        for t in d.get("facing_types", []):
            t.pop("color", None)
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
        _validate_structure(self)
        _finite_inputs(self.analysis_inputs())
        _choice(
            self.general.failure_direction,
            ("auto", "right_to_left", "left_to_right"),
            "Failure Direction",
        )
        _choice(self.groundwater.method, ("water_table", "ru", "none"), "Groundwater method")
        _choice(
            self.methods.interslice,
            ("constant", "half-sine", "clipped-sine", "trapezoidal"),
            "Interslice function",
        )
        _choice(self.surfaces.surface_type, ("circular", "noncircular", "user"), "Surface type")
        circle = self.surfaces.user_circle
        if circle is not None and (
            not isinstance(circle, (list, tuple))
            or len(circle) != 3
            or any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in circle)
            or not all(np.isfinite(v) for v in circle)
            or circle[2] <= 0
        ):
            raise ValueError("Fixed circle [Xc, Yc, R] must be finite with R > 0.")
        if self.surfaces.surface_type == "user" and self.surfaces.user_circle is None:
            us = self.surfaces.user_surface
            if not us or len(us) < 2:
                raise ValueError("User surface: at least 2 [x, y] points are required.")
            uxs = [float(q[0]) for q in us]
            if len(set(uxs)) != len(uxs):
                raise ValueError("User surface: points must have strictly increasing x values.")
        _choice(self.surfaces.noncircular_shape, ("polyline", "spline"), "Surface shape")
        _choice(self.surfaces.effort, tuple(EFFORT), "Search effort")
        if self.groundwater.gamma_w <= 0 or not 0 <= self.groundwater.ru <= 1:
            raise ValueError("γw > 0 and 0 ≤ Ru ≤ 1 required.")
        if self.seismic.kh < 0 or not -1 <= self.seismic.kv <= 1:
            raise ValueError("kh ≥ 0 and −1 ≤ kv ≤ 1 required.")
        if self.methods.tolerance <= 0:
            raise ValueError("Solver tolerance must be positive.")
        for label, value, minimum in (
            ("Number of slices", self.methods.n_slices, 3),
            ("Number of iterations", self.methods.max_iter, 1),
            ("Number of control points", self.surfaces.n_ctrl, 2),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, np.integer))
                or value < minimum
            ):
                raise ValueError(f"{label}: an integer of at least {minimum} is required.")
        if not 0 <= self.methods.f_start <= 1 or not 0 <= self.methods.f_end <= 1:
            raise ValueError("Interslice function end values must be between 0 and 1.")
        if self.advanced.min_depth < 0:
            raise ValueError("Minimum depth cannot be negative.")
        _validate_loads(self.loads)
        names = self.material_names()
        if not names:
            raise ValueError("Define at least one material.")
        if len(set(names)) != len(names):
            raise ValueError("Material names must be unique.")
        for m in self.materials:
            if m.model not in MODELS:
                raise ValueError(
                    f"{m.name}: unknown material model '{m.model}' (must be {', '.join(MODELS)})."
                )
            if m.model not in ("MC", "HB"):  # MC/HB give the messages below
                try:
                    m.to_material()
                except ValueError as exc:
                    raise ValueError(f"{m.name}: {exc}") from None
            if not m.name.strip():
                raise ValueError("Material name must not be empty.")
            if m.gamma <= 0 or m.gamma_sat <= 0:
                raise ValueError(f"{m.name}: unit weights must be positive.")
            if not 0 <= m.bbar <= 1:
                raise ValueError(f"{m.name}: B-bar must be between 0 and 1.")
            if m.model == "MC" and (m.c < 0 or not 0 <= m.phi < 90):
                raise ValueError(f"{m.name}: c ≥ 0 and 0 ≤ φ < 90 required.")
            if m.model == "HB" and (
                m.sigma_ci <= 0 or not 0 < m.gsi <= 100 or m.mi <= 0 or not 0 <= m.d <= 1
            ):
                raise ValueError(f"{m.name}: σci > 0, 0 < GSI ≤ 100, mi > 0, 0 ≤ D ≤ 1 required.")
        for a in self.assignments:
            if a["material"] not in names:
                raise ValueError(f"Assigned material '{a['material']}' is not defined.")
        tc = self.tension_crack
        if tc:
            xs = sorted(q[0] for q in tc)
            if len(tc) < 2 or any(b <= a for a, b in zip(xs, xs[1:], strict=False)):
                raise ValueError(
                    "The tension crack line needs at least 2 points with different x values."
                )
        if not 0 <= self.groundwater.crack_water <= 1:
            raise ValueError("The crack water ratio must be between 0 and 1.")
        adv = self.advanced
        if not 0 < adv.m_alpha_min <= 1:
            raise ValueError("The mα threshold must be between 0 and 1.")
        if adv.e_max_ratio < 1:
            raise ValueError("The maximum E ratio must be at least 1.")
        snames = [t.name for t in self.support_types]
        if len(set(snames)) != len(snames):
            raise ValueError("Support type names must be unique.")
        for t in self.support_types:
            _choice(t.application, ("active", "passive"), t.name)
            _choice(t.orientation, ("parallel", "tangent", "perpendicular"), t.name)
            _choice(t.anchorage, ("none", "face", "embedded", "both"), t.name)
            if t.kind not in SUPPORT_KINDS:
                raise ValueError(f"{t.name}: unknown support type.")
            if t.spacing <= 0 or t.tensile < 0 or t.length <= 0:
                raise ValueError(f"{t.name}: spacing > 0, length > 0 and capacity ≥ 0 required.")
            if (
                t.plate < 0
                or t.bond_strength < 0
                or (t.bond_length <= 0 if t.kind == "grouted_tieback" else t.bond_length < 0)
                or t.pullout < 0
                or not 0 < t.coverage <= 100
                or t.adhesion < 0
                or not 0 <= t.interface_friction < 90
                or t.overburden_gamma <= 0
                or t.pile_shear < 0
            ):
                raise ValueError(f"{t.name}: invalid support strength or geometry parameters.")
        for sp in self.supports + self.support_patterns:
            if sp["type"] not in snames:
                raise ValueError(f"Support type '{sp['type']}' is not defined.")
        for i, sp in enumerate(self.supports, 1):
            if np.hypot(sp["b"][0] - sp["a"][0], sp["b"][1] - sp["a"][1]) <= 1e-9:
                raise ValueError(f"Support {i}: head and end points must not coincide.")
        for i, pt in enumerate(self.support_patterns, 1):
            if pt["spacing"] <= 0 or pt["length"] <= 0:
                raise ValueError("Bolt pattern: spacing and length must be positive.")
            if pt.get("offset", 0.0) < 0:
                raise ValueError(f"Bolt pattern {i}: offset must not be negative.")
            if not -90.0 <= pt.get("angle", 0.0) <= 90.0:
                raise ValueError(f"Bolt pattern {i}: inclination must be between -90° and 90°.")
            if np.hypot(pt["p2"][0] - pt["p1"][0], pt["p2"][1] - pt["p1"][1]) <= 1e-9:
                raise ValueError(f"Bolt pattern {i}: start and end points must not coincide.")
        fnames = [t.name for t in self.facing_types]
        if len(set(fnames)) != len(fnames):
            raise ValueError("Facing type names must be unique.")
        for ft in self.facing_types:
            _choice(ft.application, ("active", "passive"), ft.name)
            if ft.thickness <= 0 or ft.gamma < 0 or ft.tau < 0 or ft.mesh_as < 0 or ft.mesh_fy < 0:
                raise ValueError(f"{ft.name}: thickness > 0, other values ≥ 0 required.")
        for i, f in enumerate(self.facings, 1):
            if f["type"] not in fnames:
                raise ValueError(f"Facing type '{f['type']}' is not defined.")
            if abs(f["x2"] - f["x1"]) <= 1e-9:
                raise ValueError(f"Facing {i}: horizontal span must be positive.")
        for k in self.methods.methods:
            if k not in METHODS:
                raise ValueError(f"Unknown method: {k}")
        if self.methods.n_slices < 3:
            raise ValueError("The number of slices must be at least 3.")

    @property
    def has_geometry(self) -> bool:
        return len(self.external) >= 3

    # ------------------------------------------------------------ build
    def build_geometry(self) -> SlopeGeometry:
        self.validate()
        if not self.has_geometry:
            raise ValueError("No external boundary defined (Boundaries → Add External Boundary).")
        assign = [(a["point"][0], a["point"][1], a["material"]) for a in self.assignments]
        return boundary_geometry(
            self.external,
            self.material_boundaries,
            assign,
            self.materials[0].name,
            self.water_table,
            self.name,
        )

    def build_materials(self) -> dict[str, Material]:
        self.validate()
        return {m.name: m.to_material() for m in self.materials}

    def support_type(self, name: str) -> SupportType | None:
        return next((t for t in self.support_types if t.name == name), None)

    def load_set(self) -> LoadSet:
        _validate_loads(self.loads)
        ls = LoadSet()
        for ld in self.loads:
            if ld["kind"] == "distributed":
                (x1, _), (x2, _) = ld["points"]
                q1, q2 = ld["q"]
                if x2 < x1:
                    x1, x2, q1, q2 = x2, x1, q2, q1
                ls.distributed.append(
                    DistributedLoad(x1, x2, q1, q2, ld.get("orientation", "vertical"))
                )
            elif ld["kind"] == "line":
                x, y = ld["point"]
                ls.line.append(LineLoad(x, y, ld["magnitude"], ld.get("angle", 270.0)))
        for i, sp in enumerate(self.supports):
            st = self.support_type(sp["type"])
            if st is not None:
                ls.supports.append(Support(tuple(sp["a"]), tuple(sp["b"]), st, f"Support {i + 1}"))
        geom = None
        for j, pt in enumerate(self.support_patterns):
            st = self.support_type(pt["type"])
            if st is None:
                continue
            if geom is None:
                geom = self.build_geometry()
            for k, (a, b) in enumerate(
                self.pattern_bolts(pt, geom, self.general.failure_direction)
            ):
                ls.supports.append(Support(tuple(a), tuple(b), st, f"Pattern {j + 1}/{k + 1}"))
        for f in self.facings:
            ft = self.facing_type(f["type"])
            if ft is not None:
                ls.facings.append(Facing(f["x1"], f["x2"], ft))
        return ls

    def facing_type(self, name: str) -> FacingType | None:
        return next((t for t in self.facing_types if t.name == name), None)

    @staticmethod
    def pattern_bolts(pt: dict, geom, failure_direction: str = "auto") -> list:
        """(A, B) of every bolt of a pattern, heads on the ground surface."""
        xs = pattern_positions(geom, pt["p1"][0], pt["p2"][0], pt["spacing"], pt.get("offset", 0.0))
        return [
            bolt_at(geom, x, pt.get("angle", 15.0), pt["length"], failure_direction) for x in xs
        ]

    def slice_options(self) -> SliceOptions:
        gw = self.groundwater
        _choice(gw.method, ("water_table", "ru", "none"), "Groundwater method")
        pore = gw.method
        if pore == "water_table" and not self.water_table:
            pore = "none"
        ls = self.load_set()
        return SliceOptions(
            n_slices=self.methods.n_slices,
            gamma_w=gw.gamma_w,
            pore=pore,
            ru=gw.ru,
            kh=self.seismic.kh,
            kv=self.seismic.kv,
            direction=self.general.failure_direction,
            min_depth=self.advanced.min_depth,
            loads=None if ls.empty else ls,
            crack=self.crack(),
        )

    def crack(self) -> TensionCrack | None:
        tc = self.tension_crack
        if not tc or len(tc) < 2:
            return None
        return TensionCrack(
            np.array(sorted(map(tuple, tc)), dtype=float),
            self.groundwater.crack_water,
            self.groundwater.gamma_w,
        )

    def solver_kw(self) -> dict:
        m = self.methods
        return {
            "tol": m.tolerance,
            "max_iter": m.max_iter,
            "interslice": m.interslice,
            "f_start": m.f_start,
            "f_end": m.f_end,
            "m_alpha_min": self.advanced.m_alpha_min,
            "e_max_ratio": self.advanced.e_max_ratio,
        }

    # ------------------------------------------------------------- JSON
    def file_version(self) -> int:
        """3, or 4 when the model uses B-bar excess pore pressure or a SHANSEP
        OCR profile. A program that only knows version 3 would ignore these
        and solve a different model, so such files must not open there."""
        staged = any(m.bbar > 0 for m in self.materials) and any(
            m.excess_load for m in self.materials
        )
        profile = any(m.model == "SH" and m.ocr_y_top != m.ocr_y_bottom for m in self.materials)
        return VERSION if staged or profile else BASE_VERSION

    def to_dict(self) -> dict:
        return {
            "format": FORMAT,
            "version": self.file_version(),
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
    def from_dict(cls, d: dict) -> Project:
        if not isinstance(d, dict) or d.get("format") != FORMAT:
            raise ValueError("This file is not a SlipSurfaceIQ LE project.")
        raw_ver = d.get("version")
        if (
            isinstance(raw_ver, bool)
            or not isinstance(raw_ver, (int, float))
            or not float(raw_ver).is_integer()
        ):
            raise ValueError("The project file version is missing or invalid.")
        ver = int(raw_ver)
        if ver < 1:
            raise ValueError("The project file version is missing or invalid.")
        if ver > VERSION:
            raise ValueError("The file was saved by a newer version.")
        try:
            project = _from_v1(d) if ver < 2 else cls._from_current(d)
        except (KeyError, TypeError, AttributeError, IndexError) as exc:
            raise ValueError(
                f"The project file is incomplete or damaged ({type(exc).__name__}: {exc})."
            ) from None
        _validate_structure(project)
        return project

    @classmethod
    def _from_current(cls, d: dict) -> Project:
        g = d.get("geometry") or {}
        st = d.get("settings") or {}
        if not isinstance(g, dict) or not isinstance(st, dict):
            raise ValueError("The project file is incomplete or damaged.")
        disp_raw = d.get("display") or {}
        if not isinstance(disp_raw, dict):
            raise ValueError("The project file is incomplete or damaged.")
        disp = _clean_display(disp_raw)
        return cls(
            summary=_from_dict(ProjectSummary, d.get("summary")),
            materials=[_from_dict(MaterialSpec, m) for m in (d.get("materials") or [])],
            external=[list(map(float, p)) for p in (g.get("external") or [])],
            material_boundaries=[
                [list(map(float, p)) for p in b] for b in (g.get("material_boundaries") or [])
            ],
            water_table=(
                [list(map(float, p)) for p in g["water_table"]] if g.get("water_table") else None
            ),
            tension_crack=(
                [list(map(float, p)) for p in g["tension_crack"]]
                if g.get("tension_crack")
                else None
            ),
            assignments=[
                {"point": list(map(float, a["point"])), "material": a["material"]}
                for a in (g.get("assignments") or [])
            ],
            general=_from_dict(GeneralSettings, st.get("general")),
            methods=_from_dict(MethodSettings, st.get("methods")),
            groundwater=_from_dict(GroundwaterSettings, st.get("groundwater")),
            seismic=_from_dict(SeismicSettings, st.get("seismic")),
            advanced=_from_dict(AdvancedSettings, st.get("advanced")),
            surfaces=_from_dict(SurfaceSettings, d.get("surfaces")),
            loads=[dict(ld) for ld in (d.get("loads") or [])],
            support_types=[_from_dict(SupportType, t) for t in (d.get("support_types") or [])],
            supports=[
                {"a": list(map(float, sp["a"])), "b": list(map(float, sp["b"])), "type": sp["type"]}
                for sp in (d.get("supports") or [])
            ],
            support_patterns=[dict(p) for p in (d.get("support_patterns") or [])],
            facing_types=[_from_dict(FacingType, t) for t in (d.get("facing_types") or [])],
            facings=[dict(f) for f in (d.get("facings") or [])],
            annotations=[dict(a) for a in (d.get("annotations") or [])],
            result_annotations=[dict(a) for a in (d.get("result_annotations") or [])],
            display=disp,
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def load(cls, path: str | Path) -> Project:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ------------------------------------------------------------ v1 import
def _from_v1(d: dict) -> Project:
    """Convert a v1 file (ground surface + layer stack) to boundaries."""
    from slipsurface.geometry import layered_geometry

    g = d["geometry"]
    surface = np.asarray(g["surface"], float)
    layers = [
        (lay["material"], None if i == 0 else np.asarray(lay["top"], float))
        for i, lay in enumerate(g["layers"])
    ]
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
    assigns = [
        {"point": list(r.polygon.representative_point().coords[0]), "material": r.material}
        for r in old.regions
    ]
    mats = []
    for m in d.get("materials", []):
        spec = _from_dict(MaterialSpec, m)
        spec.use_sat = m.get("gamma_sat", spec.gamma) != m.get("gamma", spec.gamma)
        mats.append(spec)
    w = d.get("water") or {}
    a = d.get("analysis") or {}
    wt_pts = (
        [list(map(float, p)) for p in w["points"]] if w.get("enabled") and w.get("points") else None
    )
    p = Project(
        summary=ProjectSummary(title=d.get("name", "Model")),
        materials=mats,
        external=ext,
        material_boundaries=bounds,
        water_table=wt_pts,
        assignments=assigns,
    )
    p.groundwater.gamma_w = float(w.get("gamma_w", 9.81))
    if "enabled" in w and not w.get("enabled"):
        p.groundwater.method = "none"
    if a.get("method") in METHODS:
        p.methods.methods = [a["method"]]
    raw_ns = a.get("n_slices", p.methods.n_slices)
    if isinstance(raw_ns, bool):
        raise ValueError("n_slices must be an integer.")
    p.methods.n_slices = int(raw_ns)
    if a.get("surface_type") in ("circular", "noncircular", "user"):
        p.surfaces.surface_type = a["surface_type"]
    raw_nc = a.get("n_ctrl")
    if raw_nc is not None and not isinstance(raw_nc, bool):
        p.surfaces.n_ctrl = int(raw_nc)
    raw_seed = a.get("seed")
    if raw_seed is not None and not isinstance(raw_seed, bool):
        p.surfaces.seed = int(raw_seed)
    if a.get("exit_range") is not None:
        p.surfaces.left_range = [float(x) for x in a["exit_range"]]
    if a.get("entry_range") is not None:
        p.surfaces.right_range = [float(x) for x in a["entry_range"]]
    if "show_top" in a:
        p.display["show_all_surfaces"] = bool(a["show_top"])
    return p


# ---------------------------------------------------------------- presets
def _mk(title, mats, ext, bounds=(), wt=None, assigns=(), methods=None, n_slices=None):
    p = Project(
        summary=ProjectSummary(title=title),
        materials=list(mats),
        external=[list(map(float, q)) for q in ext],
        material_boundaries=[[list(map(float, q)) for q in b] for b in bounds],
        water_table=wt,
        assignments=[{"point": list(map(float, pt)), "material": m} for pt, m in assigns],
    )
    if methods:
        p.methods.methods = list(methods)
    if n_slices:
        p.methods.n_slices = n_slices
    return p


def empty_project() -> Project:
    return _mk("New Project", [MaterialSpec("Soil 1", color=PALETTE[0])], [])


def acads_1a_project() -> Project:
    return _mk(
        "ACADS EX1(a) — homogeneous slope",
        [MaterialSpec("Soil 1", "MC", 20, 20, False, 3, 19.6, color=PALETTE[0])],
        [[0, -5], [60, -5], [60, 10], [40, 10], [20, 0], [0, 0]],
        methods=["bishop", "spencer", "gle", "janbu_simplified", "janbu_corrected"],
        n_slices=30,
    )


def acads_1b_project() -> Project:
    """Published ACADS EX1(c), Slide2 VP3: three layers with a weak lens.

    The legacy Python/file identifier ``1b`` is kept for compatibility.
    Layer 1 starts at the toe, a concave corner of the boundary.
    """
    return _mk(
        "ACADS EX1(c) — non-homogeneous slope",
        [
            MaterialSpec("Soil 1", "MC", 19.5, 19.5, False, 0.0, 38.0, color=PALETTE[0]),
            MaterialSpec("Soil 2", "MC", 19.5, 19.5, False, 5.3, 23.0, color=PALETTE[3]),
            MaterialSpec("Soil 3", "MC", 19.5, 19.5, False, 7.2, 20.0, color=PALETTE[2]),
        ],
        [[20, 20], [70, 20], [70, 35], [50, 35], [30, 25], [20, 25]],
        bounds=[
            [[30, 25], [40, 27], [50, 29], [54, 31], [70, 31]],
            [[40, 27], [52, 24], [70, 24]],
        ],
        assigns=[((60, 33), "Soil 1"), ((60, 27), "Soil 2"), ((40, 22), "Soil 3")],
        methods=["bishop", "spencer", "gle", "janbu_simplified", "janbu_corrected"],
        n_slices=30,
    )


def acads_1c_project() -> Project:
    """Published ACADS EX1(b): homogeneous slope with a water-filled crack.

    The legacy Python/file identifier ``1c`` is kept for compatibility.

    Slide2 verification problem #2 / RS2 #2 (Giam & Donald, 1989).
    The crack depth follows Craig (1997):
    z0 = 2c/gamma * sqrt((1 + sin phi) / (1 - sin phi)) = 3.814 m
    for c=32 kPa, phi=10 deg, gamma=20 kN/m3. Published FoS:
    Spencer 1.592, GLE 1.592 (Slide2); referee 1.65 (Giam).
    """
    import math

    phi = math.radians(10.0)
    z0 = 2 * 32.0 / 20.0 * math.sqrt((1 + math.sin(phi)) / (1 - math.sin(phi)))
    p = _mk(
        "ACADS EX1(b) — slope with tension crack",
        [MaterialSpec("Soil 1", "MC", 20, 20, False, 32.0, 10.0, color=PALETTE[0])],
        [[0, -5], [60, -5], [60, 10], [40, 10], [20, 0], [0, 0]],
        methods=["bishop", "spencer", "gle", "janbu_corrected"],
        n_slices=40,
    )
    p.tension_crack = [[42.0, 10 - z0], [60.0, 10 - z0]]
    p.groundwater.crack_water = 1.0  # water-filled crack (Slide2 VP#2)
    p.surfaces.effort = "fine"
    return p


def acads_1d_project() -> Project:
    """ACADS EX1(d): the published EX1(c) three-layer slope with kh = 0.15.

    Slide2 verification problem #4 / RS2 #4 (Giam & Donald, 1989).
    Published FoS: Spencer 0.991, GLE 0.989 (Slide2); referee 1.00 (Giam).
    """
    p = acads_1b_project()
    p.summary.title = "ACADS EX1(d) — seismic kh = 0.15"
    p.methods.methods = ["bishop", "spencer", "gle", "janbu_corrected"]
    p.seismic.kh = 0.15
    return p


def acads_4_project() -> Project:
    """ACADS EX4: weak seam, piezometric surface and surcharge.

    Slide2 verification problem #9 / RS2 #9 (Giam & Donald, 1989).
    The seam is INCLINED, unlike 3(a). Exact coordinates: RS2 slope
    verification Part 1, section 6, Figure 1 (printed page 13).
    Slide2 optimized block-search FoS: Spencer 0.707, GLE 0.683;
    unoptimized block search: Spencer 0.760, GLE 0.720.
    """
    p = acads_3a_project()
    p.summary.title = "ACADS EX4 — weak seam, water table, surcharge"
    p.external = [[20, 15], [84, 15], [84, 40], [67.5, 40], [43, 27.75], [20, 27.75]]
    p.material_boundaries = [
        [[20, 18.88], [84, 36.8]],
        [[20, 18.28], [84, 36.2]],
    ]
    p.assignments = [
        {"point": [60, 36], "material": "Soil 1"},
        {"point": [60, 29.78], "material": "Soil 2"},
        {"point": [60, 22], "material": "Soil 1"},
    ]
    p.water_table = [
        [20, 27.75],
        [43, 27.75],
        [49, 29.8],
        [60, 34.0],
        [66, 35.8],
        [74, 37.6],
        [80, 38.4],
        [84, 38.4],
    ]
    p.loads = [
        {
            "kind": "distributed",
            "points": [[23, 27.75], [43, 27.75]],
            "q": [20, 20],
            "orientation": "vertical",
        },
        {
            "kind": "distributed",
            "points": [[70, 40], [80, 40]],
            "q": [20, 40],
            "orientation": "vertical",
        },
    ]
    return p


def acads_5_project() -> Project:
    """ACADS EX5: excavated 1:2 slope with stabilised groundwater.

    Slide2 verification problem #10 / RS2 #10 (Giam & Donald, 1989).
    The published reference derives pore pressures from a flow net; this
    model approximates them with a water table that falls toward the
    excavation (u = 0 above the table). Published FoS: Spencer 1.500
    (Slide2, pore-pressure grid); referee 1.53 (Giam). With the water-
    table approximation the Spencer search gives ~1.486.
    """
    p = _mk(
        "ACADS EX5 — excavated slope with groundwater",
        [MaterialSpec("Soil 1", "MC", 20, 20, False, 11.0, 28.0, color=PALETTE[0])],
        [[0, -10], [80, -10], [80, 0], [50, 0], [30, 10], [0, 10]],
        wt=[[0, 6], [30, 6], [40, 3], [50, 0], [80, 0]],
        methods=["bishop", "spencer", "gle", "janbu_corrected"],
        n_slices=40,
    )
    p.general.failure_direction = "left_to_right"  # high ground on the left
    p.surfaces.effort = "fine"
    return p


def acads_3a_project() -> Project:
    """ACADS 3(a) / VS_7: water table at the base of a 0.5 m weak seam.

    Reference: ACADS (Giam & Donald, 1989); Rocscience RS2 verification
    problem #07. This is an unrestricted non-circular search, not the
    separately specified surface of ACADS 3(b).
    """
    p = _mk(
        "ACADS 3(a) — water table with weak seam",
        [
            MaterialSpec("Soil 1", "MC", 18.84, 18.84, False, 28.5, 20.0, color=PALETTE[0]),
            MaterialSpec("Soil 2", "MC", 18.84, 18.84, False, 0.0, 10.0, color=PALETTE[3]),
        ],
        [[20, 20], [84, 20], [84, 40], [67.5, 40], [43, 27.75], [20, 27.75]],
        bounds=[
            [[20, 27.0], [84, 27.0]],
            [[20, 26.5], [84, 26.5]],
        ],
        wt=[[20, 26.5], [84, 26.5]],
        assigns=[
            ((60, 32), "Soil 1"),
            ((60, 26.75), "Soil 2"),
            ((60, 23), "Soil 1"),
        ],
        methods=["spencer", "gle", "janbu_corrected"],
        n_slices=60,
    )
    p.surfaces.surface_type = "noncircular"
    p.surfaces.noncircular_shape = "polyline"
    p.surfaces.effort = "fine"
    p.surfaces.n_ctrl = 4
    return p


def acads_3b_project() -> Project:
    """ACADS 3(b): same weak-seam soils as 3(a), prescribed slip path.

    This is a SOLVER check (no optimization), deliberately separate from
    3(a)'s search for a critical non-circular surface.
    """
    p = acads_3a_project()
    p.summary.title = "ACADS 3(b) — weak seam, specified noncircular path"
    p.surfaces.surface_type = "user"
    p.surfaces.search = "none"
    p.surfaces.user_surface = [
        [41.85, 27.75],
        [44.0, 26.5],
        [63.5, 27.0],
        [73.31, 40.0],
    ]
    return p


def acads_2b_project() -> Project:
    """ACADS 2(b), Talbingo Dam: dry, exactly specified circle, no search.

    Geometry and material boundaries: Giam & Donald (1989), as tabulated
    in the Rocscience verification manual (VP5/VP6).
    """
    p = _mk(
        "ACADS 2(b) — Talbingo Dam, specified dry circle",
        [
            MaterialSpec("Rockfill", "MC", 20.4, 20.4, False, 0.0, 45.0, color=PALETTE[0]),
            MaterialSpec("Transitions", "MC", 20.4, 20.4, False, 0.0, 45.0, color=PALETTE[3]),
            MaterialSpec("Filter", "MC", 20.4, 20.4, False, 0.0, 45.0, color=PALETTE[1]),
            MaterialSpec("Core", "MC", 18.1, 18.1, False, 85.0, 23.0, color=PALETTE[2]),
        ],
        [
            [0, 0],
            [648, 0],
            [577.9, 31.4],
            [515, 65.3],
            [453.4, 97.9],
            [386.9, 130.6],
            [327.6, 162],
            [315.5, 162],
        ],
        bounds=[
            [[168.1, 0], [302.2, 130.6], [315.5, 162]],
            [[200.7, 0], [311.9, 130.6], [319.5, 162]],
            [[307.1, 0], [331.3, 130.6], [328.8, 146.1], [321.6, 162]],
            [[310.7, 0], [333.7, 130.6], [331.3, 146.1], [327.6, 162]],
            [[372.4, 0], [347.0, 130.6], [327.6, 162]],
        ],
        assigns=[
            ((100, 20), "Rockfill"),
            ((245, 65), "Transitions"),
            ((287, 65), "Core"),
            ((320.7, 65.3), "Filter"),
            ((341, 65), "Transitions"),
            ((500, 65), "Rockfill"),
        ],
        methods=["bishop", "spencer", "gle", "janbu_corrected"],
        n_slices=50,
    )
    p.groundwater.method = "none"
    p.surfaces.surface_type = "user"
    p.surfaces.search = "none"
    p.surfaces.user_circle = [100.3, 291.0, 278.8]
    return p


def acads_2a_project() -> Project:
    """ACADS 2(a): critical circle SEARCH on the Talbingo upstream face.

    Distinct from 2(b), which evaluates one fixed (Xc, Yc, R) circle.
    The upstream geometry has a 162 / 315.5 face slope and a limiting
    cohesionless infinite-slope FoS of tan(45°)/(162/315.5) = 1.948.
    """
    p = acads_2b_project()
    p.summary.title = "ACADS 2(a) — Talbingo Dam, dry critical upstream search"
    p.surfaces.surface_type = "circular"
    p.surfaces.search = "auto_refine"
    p.surfaces.user_circle = None
    p.surfaces.effort = "fine"
    # Search the UPSTREAM face, as in the published 2(a) limit mechanism.
    # The downstream face is a distinct geometry / mechanism.
    p.surfaces.left_range = [0.0, 315.4]
    p.surfaces.right_range = [0.1, 315.5]
    p.methods.methods = ["bishop", "janbu_simplified", "janbu_corrected", "spencer", "gle"]
    return p


EXAMPLES = {
    "ACADS EX1(a)": acads_1a_project,
    "ACADS EX1(b) — slope with tension crack": acads_1c_project,
    "ACADS EX1(c) — non-homogeneous slope": acads_1b_project,
    "ACADS EX1(d) — seismic kh = 0.15": acads_1d_project,
    "ACADS 2(a) — Talbingo critical upstream search": acads_2a_project,
    "ACADS 2(b) — Talbingo fixed circle": acads_2b_project,
    "ACADS 3(a) — weak seam + water table": acads_3a_project,
    "ACADS 3(b) — weak seam specified path": acads_3b_project,
    "ACADS EX4 — weak seam, water table, surcharge": acads_4_project,
    "ACADS EX5 — excavated slope with groundwater": acads_5_project,
}

# Names used before 2026.5.0, when EX1(b) and EX1(c) were interchanged. They
# still open the same model as before, with a notice that names the current
# example; they do not appear in the example menu.
LEGACY_EXAMPLE_NAMES = {
    "ACADS EX1(b)": "ACADS EX1(c) — non-homogeneous slope",
    "ACADS EX1(c) — slope with tension crack": "ACADS EX1(b) — slope with tension crack",
}
EXAMPLE_ALIASES = {old: EXAMPLES[new] for old, new in LEGACY_EXAMPLE_NAMES.items()}


def legacy_example_notice(name: str) -> str | None:
    """Explain a legacy example name, or None for a current one."""
    new = LEGACY_EXAMPLE_NAMES.get(name)
    if new is None:
        return None
    return (
        f"Example name {name!r} is from an older release and opens {new!r}; "
        "the ACADS EX1(b)/(c) names now follow the published numbering."
    )


def example_project(name: str) -> Project:
    """Bundled example by name (see EXAMPLES); legacy names warn."""
    notice = legacy_example_notice(name)
    if notice is not None:
        import warnings

        warnings.warn(notice, FutureWarning, stacklevel=2)
    factory = EXAMPLES.get(name) or EXAMPLE_ALIASES[name]
    return factory()
