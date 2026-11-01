"""Build docs/Python_Scripting_Tutorial.pdf (maintainers only).

    python scripts/build_scripting_tutorial.py

Field tables are generated from the project dataclasses and the material
catalogue, so the reference always matches the code. Every example in
SNIPPETS is executed through slipsurface.scripting.run_script before the PDF
is written; the build fails if one of them no longer runs.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guide_pdf import (  # noqa: E402
    ROOT,
    Chapters,
    CodeBlock,
    P,
    _esc,
    callout,
    code,
    table,
    write,
)
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import CondPageBreak, Spacer, Table  # noqa: E402

from slipsurface.lem import METHODS  # noqa: E402
from slipsurface.loads import SUPPORT_KINDS, FacingType, SupportType  # noqa: E402
from slipsurface.materials.catalog import MODELS  # noqa: E402
from slipsurface.project import (  # noqa: E402
    DEFAULT_DISPLAY,
    EFFORT,
    AdvancedSettings,
    GeneralSettings,
    GroundwaterSettings,
    MaterialSpec,
    MethodSettings,
    ProjectSummary,
    SeismicSettings,
    SurfaceSettings,
    empty_project,
)
from slipsurface.scripting import run_script  # noqa: E402

OUT = ROOT / "docs" / "Python_Scripting_Tutorial.pdf"

# ------------------------------------------------------- field references
FIELD_HELP: dict[str, dict[str, str]] = {
    "ProjectSummary": {
        "title": "Project title (window caption, report cover).",
        "analysis": "Analysis description.",
        "author": "Author shown in the report.",
        "company": "Company shown in the report.",
        "date_created": "Creation date, YYYY-MM-DD.",
        "comments": "Five free comment lines.",
    },
    "GeneralSettings": {
        "units": "Unit system; metric (m, kN, kPa).",
        "failure_direction": "auto, right_to_left or left_to_right.",
        "data_output": "Amount of result data kept: standard.",
    },
    "MethodSettings": {
        "methods": "Limit equilibrium methods to run (keys in the methods table).",
        "n_slices": "Number of slices (at least 3).",
        "tolerance": "Convergence tolerance on the factor of safety.",
        "max_iter": "Maximum solver iterations.",
        "interslice": "GLE interslice function: half-sine, constant, clipped-sine, trapezoidal.",
        "f_start": "Trapezoidal / clipped function value at the start (0..1).",
        "f_end": "Trapezoidal / clipped function value at the end (0..1).",
    },
    "GroundwaterSettings": {
        "method": "water_table, ru or none.",
        "gamma_w": "Unit weight of water (kN/m3).",
        "ru": "Pore pressure coefficient Ru (0..1) when method = ru.",
        "crack_water": "Tension crack water filling, 0 (dry) .. 1 (full).",
    },
    "SeismicSettings": {
        "kh": "Horizontal seismic coefficient (acts in the failure direction).",
        "kv": "Vertical coefficient; positive is upward: load (1 - kv) W.",
        "both_vertical": "Also solve -kv and keep the lower factor of safety.",
    },
    "AdvancedSettings": {
        "check_admissibility": "Reject surfaces with inadmissible slice forces.",
        "min_depth": "Minimum slide depth (m).",
        "m_alpha_min": "Admissibility threshold for m-alpha (0..1].",
        "e_max_ratio": "Reject interslice forces above ratio x total weight.",
    },
    "SurfaceSettings": {
        "surface_type": "circular, noncircular or user.",
        "search": "Search strategy: auto_refine.",
        "effort": "Search effort: " + ", ".join(EFFORT) + ".",
        "n_ctrl": "Interior vertices of non-circular surfaces.",
        "noncircular_shape": "polyline (straight segments) or spline.",
        "convex_only": "Keep non-circular surfaces convex.",
        "seed": "Random seed of the search (reproducible results).",
        "left_range": "Slope limits for the left end: [x_min, x_max] or None.",
        "right_range": "Slope limits for the right end: [x_min, x_max] or None.",
        "user_surface": "User polyline [[x, y], ...] when surface_type = user.",
        "user_circle": "Exact fixed circle [xc, yc, radius] when surface_type = user.",
    },
    "SupportType": {
        "name": "Unique name; supports and patterns refer to it.",
        "kind": "Support model (see the support kinds table).",
        "spacing": "Out-of-plane spacing (m); not used for geotextile / geosynthetic.",
        "tensile": "Tensile capacity: kN, or kN/m for geotextile / geosynthetic.",
        "plate": "Plate capacity of a soil nail (kN).",
        "bond_strength": "Bond strength of tiebacks and soil nails (kN/m).",
        "bond_length": "Bonded length of a grouted tieback (m).",
        "pullout": "Geotextile pull-out strength (kN/m per m).",
        "application": "active (force reduces driving) or passive (force divided by F).",
        "orientation": "parallel, tangent or perpendicular force direction.",
        "color": "Drawing colour.",
        "length": "Default length of automatically placed bolts (m).",
        "coverage": "Geosynthetic strip coverage (%).",
        "anchorage": "Geosynthetic anchorage: none, face, embedded or both.",
        "adhesion": "Geosynthetic interface adhesion (kPa).",
        "interface_friction": "Geosynthetic interface friction angle (deg).",
        "overburden_gamma": "Unit weight for the geosynthetic overburden stress (kN/m3).",
        "pile_shear": "Shear strength of one micro-pile (kN).",
    },
    "FacingType": {
        "name": "Unique name; facings refer to it.",
        "thickness": "Shotcrete thickness (m).",
        "gamma": "Shotcrete unit weight (kN/m3).",
        "tau": "Shotcrete shear strength (kPa).",
        "mesh": "Mesh designation, e.g. Q188.",
        "mesh_as": "Mesh steel area (mm2/m).",
        "mesh_fy": "Mesh yield strength (MPa).",
        "application": "passive (T/F) or active.",
        "color": "Drawing colour.",
    },
}

COMMON_MATERIAL = {
    "name": "Unique material name (assignments refer to it).",
    "model": "Strength model key, see the models table.",
    "gamma": "Unit weight above the water table (kN/m3).",
    "gamma_sat": "Saturated unit weight (kN/m3), used when use_sat is True.",
    "use_sat": "Use gamma_sat below the water table.",
    "use_water": "The water table acts on this material.",
    "hu": "Pore-pressure factor Hu applied to the water table head.",
    "color": "Fill colour, e.g. '#f0c800'.",
}

DISPLAY_HELP = {
    "external_color": "External boundary colour.",
    "material_boundary_color": "Material boundary colour.",
    "water_table_color": "Water table colour.",
    "show_vertices": "Draw boundary vertices.",
    "line_width": "Boundary line width.",
    "show_ruler": "Show the rulers.",
    "show_grid": "Show the grid.",
    "fill_materials": "Fill regions with material colours.",
    "show_slope_limits": "Show the slope limit markers.",
    "show_slices": "Draw the slices of the critical surface.",
    "slice_fill_color": "Slice fill colour.",
    "show_lines_to_center": "Lines from the critical circle to its centre.",
    "show_fs_text": "Write the factor of safety at the centre.",
    "show_all_surfaces": "Draw the lowest surfaces, not only the critical one.",
    "show_fs_contours": "Slip-centre FS contour map (circular searches).",
    "critical_dashed": "Critical surface as a dashed line.",
    "show_legend": "Material legend.",
    "show_fs_legend": "FS legend of all methods.",
    "material_labels": "Region labels: none, name or full.",
    "label_size": "Label font size.",
    "show_control_points": "Control polygon of a spline critical surface.",
}


def _default(f: dataclasses.Field) -> str:
    if f.name == "date_created":
        return "today"
    if f.default is not dataclasses.MISSING:
        value = f.default
    elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
        value = f.default_factory()  # type: ignore[misc]
    else:
        return ""
    if isinstance(value, str):
        return repr(value) if len(value) < 24 else repr(value[:20] + "…")
    if isinstance(value, list) and len(repr(value)) > 28:
        return "[…]"
    return repr(value)


def field_table(cls, help_map: dict[str, str] | None = None, only=None) -> Table:
    help_map = help_map if help_map is not None else FIELD_HELP.get(cls.__name__, {})
    rows = []
    for f in dataclasses.fields(cls):
        if only is not None and f.name not in only:
            continue
        rows.append([f.name, _default(f), help_map.get(f.name, "")])
    missing = [r[0] for r in rows if not r[2]]
    if missing:
        raise SystemExit(f"{cls.__name__}: no description for {missing}")
    return table(["Field", "Default", "Meaning"], rows, [2.2, 1.9, 5.7], code_cols=(0, 1))


EQUILIBRIUM = {
    "bishop": "moment",
    "ordinary": "moment",
    "janbu_simplified": "force",
    "janbu_corrected": "force (corrected)",
    "corps1": "force",
    "corps2": "force",
    "lowe_karafiath": "force",
    "spencer": "force and moment",
    "gle": "force and moment",
}


# --------------------------------------------------------------- snippets
SNIPPETS: dict[str, str] = {}


def snippet(name: str, source: str) -> CodeBlock:
    SNIPPETS[name] = source
    return CodeBlock(source, name)


def check_snippets() -> None:
    """Run every example; geometry snippets start from a fresh empty project."""
    for name, source in SNIPPETS.items():
        try:
            run_script(source, BASE_PROJECT())
        except Exception as exc:  # report which example broke
            msg = f"tutorial example {name!r} fails: {type(exc).__name__}: {exc}"
            raise SystemExit(msg) from None


def BASE_PROJECT():
    """The project the examples run against: a simple slope with one soil."""
    p = empty_project()
    p.external = [[0, -10], [60, -10], [60, 10], [40, 10], [20, 0], [0, 0]]
    return p


# ------------------------------------------------------------------ text
def build_story() -> list:
    s: list = []
    chapters = Chapters(s)
    chapter, h2 = chapters.chapter, chapters.h2

    # 1 ---------------------------------------------------------------
    chapter(
        "Getting started",
        "Python scripting builds or edits a complete model in a few lines: geometry, "
        "materials, water, loads, supports, settings and notes.",
    )
    s.append(
        P(
            "Open the editor with <b>Tools → Python scripting</b>. It opens empty. Write a "
            "script, or open a <b>.py</b> file, then press <b>Run / Apply</b>. "
            "<b>Save .py</b> stores the editor text; <b>Tutorial</b> opens this document."
        )
    )
    h2("How a script runs")
    for text in (
        "The script receives <b>project</b>, a <i>copy</i> of the open model. Change it in "
        "place, or assign a new project to the same name.",
        "When the script finishes, the result is validated and its geometry is built. If "
        "everything is valid, all changes are applied as <b>one undoable step</b> "
        "(Ctrl+Z in the Modeler reverts the whole script).",
        "If the script raises an error or the model is invalid, the open project is left "
        "unchanged and the message appears in the output pane.",
        "Anything printed with <b>print()</b> is shown in the output pane.",
    ):
        s.append(P("•  " + text))
    s.append(
        callout(
            "note",
            "Units",
            "Lengths in m, forces in kN, stresses in kPa, unit weights in kN/m³, "
            "angles in degrees. The y axis points up.",
        )
    )
    s.append(Spacer(1, 8))
    s.append(
        callout(
            "warn",
            "Trusted code only",
            "Scripts are ordinary Python with your account's permissions. A script opened "
            "from a file asks for confirmation before its first run. Projects never run "
            "scripts on their own.",
        )
    )
    h2("Your first script")
    s.append(
        snippet(
            "first_script.py",
            """project = empty_project()
project.summary.title = "My first slope"
project.external = [[0, -10], [60, -10], [60, 10], [40, 10], [20, 0], [0, 0]]
project.materials = [MaterialSpec(name="Clay", gamma=19, c=8, phi=26)]
project.methods.methods = ["bishop", "spencer"]
print("Materials:", project.material_names())""",
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        P(
            "Press <b>Run / Apply</b>; the slope appears in the Modeler and is ready for "
            "<b>Compute</b>."
        )
    )

    # 2 ---------------------------------------------------------------
    chapter("Names available in a script")
    s.append(
        table(
            ["Name", "What it is"],
            [
                [
                    "project",
                    "Copy of the open model (Project). The result is what it holds at the end.",
                ],
                [
                    "empty_project()",
                    "New project with one default material 'Soil 1' and no geometry.",
                ],
                ["Project", "The project class; Project() has no materials."],
                ["MaterialSpec(...)", "A material: name, model and parameters."],
                ["SupportType(...)", "A support definition (anchor, nail, geosynthetic, …)."],
                ["FacingType(...)", "A shotcrete + mesh facing definition."],
                ["print(...)", "Write to the output pane."],
            ],
            [2.4, 7],
        )
    )
    s.append(Spacer(1, 8))
    s.append(
        P(
            "Everything else in Python works as usual: loops, functions, the <b>math</b> "
            "module and imports from the application, e.g. "
            + code("from slipsurface.loads import SUPPORT_KINDS")
            + "."
        )
    )
    h2("Useful project helpers")
    s.append(
        table(
            ["Call", "Returns"],
            [
                ["project.name", "The title (same as project.summary.title)."],
                ["project.material_names()", "List of material names."],
                ["project.material(name)", "The MaterialSpec with that name, or None."],
                ["project.support_type(name)", "The SupportType with that name, or None."],
                ["project.facing_type(name)", "The FacingType with that name, or None."],
                ["project.validate()", "Raise ValueError if the model is inconsistent."],
                ["project.copy()", "An independent deep copy."],
            ],
            [3, 6.4],
        )
    )

    # 3 ---------------------------------------------------------------
    chapter("Project summary", "Shown in the window title and on the report cover.")
    s.append(field_table(ProjectSummary))
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "summary.py",
            """project.summary.title = "Highway cut, km 12+400"
project.summary.author = "H. Engineer"
project.summary.company = "Geotech Ltd."
project.summary.comments[0] = "Long-term drained analysis\"""",
        )
    )

    # 4 ---------------------------------------------------------------
    chapter(
        "Geometry",
        "Points are [x, y] lists in metres. The external boundary is one closed polygon; "
        "material boundaries split it into regions.",
    )
    s.append(
        table(
            ["Field", "Format", "Meaning"],
            [
                [
                    "external",
                    "[[x, y], ...]",
                    "External boundary polygon, at least 3 points (closed automatically).",
                ],
                [
                    "material_boundaries",
                    "[[[x, y], ...], ...]",
                    "Polylines that divide the domain into regions.",
                ],
                [
                    "assignments",
                    "[{'point': [x, y], 'material': name}]",
                    (
                        "A point inside a region gives it a material. Unassigned regions use the "
                        "first material."
                    ),
                ],
            ],
            [2.3, 3, 4.2],
            code_cols=(0, 1),
        )
    )
    h2("A layered slope")
    s.append(
        snippet(
            "layers.py",
            """project.external = [[0, -12], [70, -12], [70, 12], [45, 12], [25, 0], [0, 0]]
project.materials = [
    MaterialSpec(name="Fill", gamma=19, c=5, phi=32, color="#f0c800"),
    MaterialSpec(name="Clay", gamma=18, c=12, phi=22, color="#3cb371"),
]
project.material_boundaries = [[[0, -4], [70, -4]]]
project.assignments = [
    {"point": [50, 5], "material": "Fill"},
    {"point": [50, -8], "material": "Clay"},
]""",
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        callout(
            "tip",
            "Build boundaries with loops",
            "Geometry is plain data, so loops and functions work well — for example, "
            "several horizontal layers from a list of elevations.",
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "layers_loop.py",
            """tops = [-3, -7]                      # layer boundary elevations
names = ["Sand", "Silt", "Clay"]
project.materials = [MaterialSpec(name=n, c=5 + 5 * i, phi=32 - 4 * i)
                     for i, n in enumerate(names)]
project.material_boundaries = [[[0, y], [60, y]] for y in tops]
mids = [-1.5, -5, -9]                 # a point inside each layer
project.assignments = [{"point": [50, y], "material": n}
                       for y, n in zip(mids, names)]""",
        )
    )

    # 5 ---------------------------------------------------------------
    chapter(
        "Materials",
        "Every material has common fields and the parameters of its strength model.",
    )
    s.append(field_table(MaterialSpec, COMMON_MATERIAL, only=COMMON_MATERIAL))
    h2("Strength models")
    s.append(
        P(
            "Set <b>model</b> to one of the keys below and give the parameters listed for "
            "it; unused parameters are ignored."
        )
    )
    rows = []
    for key, m in MODELS.items():
        params = ", ".join(r[0] for r in m.rows)
        rows.append([key, m.name, params])
    s.append(
        table(["model", "Strength model", "Parameters"], rows, [1, 3.2, 5.2], code_cols=(0, 2))
    )
    for key, m in MODELS.items():
        s.append(CondPageBreak(35 * mm))
        h2(f"{m.name}  ({key})")
        s.append(P(_esc(m.formula)))
        defaults = {f.name: _default(f) for f in dataclasses.fields(MaterialSpec)}
        s.append(
            table(
                ["Parameter", "Default", "Meaning"],
                [[r[0], defaults.get(r[0], ""), r[1]] for r in m.rows],
                [2.2, 1.6, 6],
                code_cols=(0, 1),
            )
        )
    h2("Examples")
    s.append(
        snippet(
            "materials.py",
            """project.materials = [
    MaterialSpec(name="Sand", model="MC", gamma=19, c=0, phi=34),
    MaterialSpec(name="Soft clay", model="UD", gamma=17, su=25, use_water=False),
    MaterialSpec(name="Clay", model="SH", gamma=18,
                 shansep_s=0.25, shansep_m=0.8, ocr=2),
    MaterialSpec(name="Rock", model="HB", gamma=24,
                 sigma_ci=20000, gsi=45, mi=10, d=0),
]
project.assignments = [{"point": [50, 5], "material": "Sand"}]""",
        )
    )

    # 6 ---------------------------------------------------------------
    chapter("Groundwater and tension cracks")
    s.append(
        table(
            ["Field", "Format", "Meaning"],
            [
                ["water_table", "[[x, y], ...] or None", "Piezometric line across the model."],
                [
                    "tension_crack",
                    "[[x, y], ...] or None",
                    (
                        "Line whose depth below the ground defines the crack (at least 2 points, "
                        "increasing x)."
                    ),
                ],
            ],
            [2, 2.6, 5],
            code_cols=(0, 1),
        )
    )
    h2("project.groundwater")
    s.append(field_table(GroundwaterSettings))
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "water.py",
            """project.water_table = [[0, -2], [20, -2], [45, 6], [60, 6]]
project.groundwater.method = "water_table"
project.materials[0].hu = 1.0             # per-material head factor
project.tension_crack = [[45, 7], [60, 7]]   # 3 m deep below the crest
project.groundwater.crack_water = 0.5        # half full""",
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "ru.py",
            """project.groundwater.method = "ru"
project.groundwater.ru = 0.25""",
        )
    )

    # 7 ---------------------------------------------------------------
    chapter("External loads", "project.loads is a list of dictionaries.")
    s.append(
        table(
            ["Key", "Value", "Meaning"],
            [
                ["kind", "'distributed'", "Distributed load between two points."],
                ["points", "[[x1, y1], [x2, y2]]", "Start and end on the surface (x1 ≠ x2)."],
                ["q", "[q1, q2]", "Intensity at the two ends (kPa), linear in between."],
                ["orientation", "'vertical' | 'normal'", "Load direction (default vertical)."],
                ["kind", "'line'", "Point (line) load."],
                ["point", "[x, y]", "Where it acts."],
                ["magnitude", "number", "kN/m."],
                [
                    "angle",
                    "degrees",
                    "Direction from +x, counter-clockwise; 270 = downward (default).",
                ],
            ],
            [1.6, 3, 5],
            code_cols=(0, 1),
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "loads.py",
            """project.loads = [
    {"kind": "distributed", "points": [[45, 10], [55, 10]],
     "q": [20, 20], "orientation": "vertical"},
    {"kind": "line", "point": [50, 10], "magnitude": 60, "angle": 270},
]""",
        )
    )

    # 8 ---------------------------------------------------------------
    chapter(
        "Supports",
        "Define support types once, then place single supports or automatic bolt patterns "
        "that refer to them by name.",
    )
    s.append(
        table(
            ["kind", "Model"],
            [[k, v] for k, v in SUPPORT_KINDS.items()],
            [2.5, 7],
        )
    )
    h2("SupportType fields")
    s.append(field_table(SupportType))
    h2("Single supports — project.supports")
    s.append(
        P(
            "Each item is "
            + code("{'a': [x, y], 'b': [x, y], 'type': name}")
            + ": <b>a</b> is the head on the slope face, <b>b</b> the end inside the slope."
        )
    )
    h2("Bolt patterns — project.support_patterns")
    s.append(
        table(
            ["Key", "Meaning"],
            [
                ["p1, p2", "[x, y] points; bolts are placed on the ground between their x values."],
                ["spacing", "Distance between bolts along the slope (m, > 0)."],
                ["offset", "Distance of the first bolt from p1 (m, default 0)."],
                ["angle", "Inclination below horizontal (deg, default 15)."],
                ["length", "Bolt length (m, > 0)."],
                ["type", "Name of a SupportType."],
            ],
            [1.6, 8],
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "supports.py",
            """project.support_types = [
    SupportType(name="Tieback", kind="grouted_tieback", spacing=2, tensile=300,
                bond_strength=60, bond_length=5, application="active"),
    SupportType(name="Nail", kind="soil_nail", spacing=1.5, tensile=200,
                plate=80, bond_strength=40, application="passive", length=9),
]
project.supports = [{"a": [30, 5], "b": [42, 1], "type": "Tieback"}]
project.support_patterns = [
    {"p1": [20, 0], "p2": [40, 10], "spacing": 2, "offset": 1,
     "angle": 15, "length": 9, "type": "Nail"},
]""",
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "geosynthetic.py",
            """project.support_types = [
    SupportType(name="Geogrid", kind="geosynthetic", tensile=80, coverage=100,
                anchorage="embedded", interface_friction=28),
    SupportType(name="Pile", kind="micro_pile", spacing=1.2, pile_shear=150),
]
project.supports = [
    {"a": [22, 1], "b": [55, 1], "type": "Geogrid"},
    {"a": [35, 7.5], "b": [35, -6], "type": "Pile"},
]""",
        )
    )

    # 9 ---------------------------------------------------------------
    chapter("Facings", "Shotcrete with welded wire mesh on the slope face.")
    s.append(field_table(FacingType))
    s.append(Spacer(1, 6))
    s.append(
        P(
            "Capacity per metre of slope = τ · thickness + As · fy. Place a facing with "
            + code("{'x1': x, 'x2': x, 'type': name, 'points': [[x1, y1], [x2, y2]]}")
            + " in <b>project.facings</b>."
        )
    )
    s.append(
        snippet(
            "facing.py",
            """project.facing_types = [FacingType(name="Shotcrete 10 cm", thickness=0.10,
                                   tau=400, mesh="Q188", mesh_as=188, mesh_fy=500)]
project.facings = [{"x1": 20, "x2": 40, "type": "Shotcrete 10 cm",
                    "points": [[20, 0], [40, 10]]}]""",
        )
    )

    # 10 --------------------------------------------------------------
    chapter("Seismic loading")
    s.append(field_table(SeismicSettings))
    s.append(Spacer(1, 6))
    s.append(
        callout(
            "note",
            "Sign of kv",
            "Positive kv is upward, so the vertical load is (1 − kv)·W. In Slide2 a "
            "positive kv acts downward. With both_vertical = True both signs are solved "
            "and the lower factor of safety is kept.",
        )
    )
    s.append(Spacer(1, 6))
    s.append(snippet("seismic.py", "project.seismic.kh = 0.15\nproject.seismic.kv = 0.05"))

    # 11 --------------------------------------------------------------
    chapter("Analysis methods and settings")
    s.append(
        table(
            ["Key", "Method", "Equilibrium"],
            [[k, v[1], EQUILIBRIUM[k]] for k, v in METHODS.items()],
            [2.4, 4, 3],
        )
    )
    h2("project.methods")
    s.append(field_table(MethodSettings))
    h2("project.general")
    s.append(field_table(GeneralSettings))
    h2("project.advanced")
    s.append(field_table(AdvancedSettings))
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "methods.py",
            """project.methods.methods = ["bishop", "spencer", "gle"]
project.methods.n_slices = 40
project.methods.interslice = "half-sine"
project.general.failure_direction = "right_to_left"
project.advanced.min_depth = 1.0""",
        )
    )

    # 12 --------------------------------------------------------------
    chapter("Slip surfaces", "project.surfaces selects the surface type and the search.")
    s.append(field_table(SurfaceSettings))
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "surfaces.py",
            """# automatic non-circular search with slope limits
project.surfaces.surface_type = "noncircular"
project.surfaces.effort = "normal"
project.surfaces.left_range = [10, 25]
project.surfaces.right_range = [40, 60]""",
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "fixed_surface.py",
            """# analyse one given circle only
project.surfaces.surface_type = "user"
project.surfaces.user_circle = [25, 30, 30]   # xc, yc, radius""",
        )
    )

    # 13 --------------------------------------------------------------
    chapter("Notes and display options")
    h2("Notes on the drawing — project.annotations")
    s.append(
        table(
            ["Key", "Meaning"],
            [
                ["kind", "text, line, arrow, rect or ellipse."],
                ["pts", "[[x, y]] for text; [[x1, y1], [x2, y2]] for the other shapes."],
                ["text", "Text content (text notes); '\\n' starts a new line."],
                ["color", "Line or text colour, e.g. '#c0392b'."],
                ["width", "Line width."],
                ["fill", "Fill colour of rect / ellipse, or None."],
                ["size, bold, box", "Text size, bold text and frame around the text."],
            ],
            [2, 7.5],
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "notes.py",
            """project.annotations = [
    {"kind": "text", "pts": [[30, 16]], "text": "Design section A-A",
     "color": "#1b2a3a", "size": 11, "bold": True, "box": True},
    {"kind": "arrow", "pts": [[30, 15], [26, 3]], "color": "#c0392b", "width": 1.5},
]""",
        )
    )
    h2("project.display")
    s.append(
        table(
            ["Key", "Default", "Meaning"],
            [[k, repr(v), DISPLAY_HELP[k]] for k, v in DEFAULT_DISPLAY.items()],
            [2.6, 1.4, 5.6],
            code_cols=(0, 1),
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        snippet(
            "display.py",
            """project.display["material_labels"] = "full"
project.display["show_slices"] = True""",
        )
    )

    # 14 --------------------------------------------------------------
    chapter("A complete model", "Everything together: copy, run, then Compute.")
    s.append(snippet("complete_model.py", COMPLETE))

    # 15 --------------------------------------------------------------
    chapter("Troubleshooting")
    s.append(
        table(
            ["Message", "Cause and fix"],
            [
                ["Define at least one material.", "project.materials is empty."],
                ["Material names must be unique.", "Two materials share a name."],
                [
                    "Assigned material 'X' is not defined.",
                    "An assignment or the material list has a typo.",
                ],
                [
                    "Support type 'X' is not defined.",
                    "A support or pattern names a missing SupportType.",
                ],
                ["Unknown method: X", "Use a key from the methods table."],
                [
                    "unknown option 'X'",
                    "A choice field has a value that is not allowed; see the tables.",
                ],
                ["No external boundary defined", "project.external needs at least 3 points."],
                [
                    "project must be a Project instance",
                    "The name project was reassigned to something else.",
                ],
            ],
            [3.6, 6],
        )
    )
    s.append(Spacer(1, 8))
    s.append(
        callout(
            "tip",
            "Debugging",
            "Use print() freely, and call project.validate() inside the script to see a "
            "validation error at the line where you made the change.",
        )
    )
    return s


COMPLETE = """project = empty_project()
project.summary.title = "Scripted layered cut"
project.external = [[0, -8], [48, -8], [48, 12], [26, 12], [20, 0], [0, 0]]
project.materials = [
    MaterialSpec(name="Soil", model="MC", gamma=19, c=8, phi=30),
    MaterialSpec(name="Rock", model="HB", gamma=23, sigma_ci=8000, gsi=40, mi=8),
]
project.material_boundaries = [[[0, -3], [48, -3]]]
project.assignments = [
    {"point": [24, 5], "material": "Soil"},
    {"point": [24, -6], "material": "Rock"},
]
project.water_table = [[0, -2], [20, -2], [40, 4], [48, 4]]
project.tension_crack = [[30, 10], [48, 10]]
project.groundwater.crack_water = 0.5
project.support_types = [
    SupportType(name="Nail", kind="soil_nail", spacing=1.5, tensile=240,
                plate=80, bond_strength=40, application="passive", length=9),
]
project.support_patterns = [
    {"p1": [20, 0], "p2": [26, 12], "spacing": 2, "offset": 1,
     "angle": 15, "length": 9, "type": "Nail"},
]
project.facing_types = [FacingType(name="Shotcrete")]
project.facings = [{"x1": 20, "x2": 26, "type": "Shotcrete",
                    "points": [[20, 0], [26, 12]]}]
project.loads = [
    {"kind": "distributed", "points": [[29, 12], [40, 12]],
     "q": [15, 15], "orientation": "vertical"},
    {"kind": "line", "point": [42, 12], "magnitude": 20, "angle": 270},
]
project.seismic.kh = 0.1
project.methods.methods = ["bishop", "spencer"]
project.methods.n_slices = 40
project.surfaces.effort = "fast"
print("Ready:", project.summary.title)"""


def build(path: Path = OUT) -> Path:
    return write(
        path,
        build_story(),
        "Python Scripting Tutorial",
        ["Python Scripting", "Tutorial"],
        "Build and edit complete slope models with Python",
        check=check_snippets,
    )


if __name__ == "__main__":
    out = build()
    print(f"wrote {out} ({out.stat().st_size // 1024} KiB, {len(SNIPPETS)} examples checked)")
