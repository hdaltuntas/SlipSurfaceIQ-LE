"""Build docs/DXF_Import_Guide.pdf and docs/DXF_Layer_Template.dxf (maintainers only).

    python scripts/build_dxf_guide.py

Before the PDF is written the build checks the guide against the code:
the layer template is exported and imported again, every example script is
run, and every error message quoted in the guide must occur in the source.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guide_pdf import (  # noqa: E402
    CONTENT_W,
    MUTED,
    NAVY,
    ROOT,
    SANS,
    SEMI,
    Chapters,
    CodeBlock,
    P,
    callout,
    code,
    table,
    write,
)
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Polygon, String  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.platypus import Spacer  # noqa: E402

from slipsurface.exchange import export_dxf, import_dxf  # noqa: E402
from slipsurface.project import MaterialSpec, SupportType, empty_project  # noqa: E402

OUT = ROOT / "docs" / "DXF_Import_Guide.pdf"
TEMPLATE = ROOT / "docs" / "DXF_Layer_Template.dxf"

LAYER_COLORS = {
    "SS_EXTERNAL": "#1b2433",
    "SS_MATERIAL": "#8a5a00",
    "SS_WATER": "#1f5fd1",
    "SS_CRACK": "#c0392b",
    "SS_SURFACE": "#0f9d8a",
    "SS_SUPPORT": "#7b3fbf",
}


# ------------------------------------------------------------ the model
def template_project():
    """The model behind the layer figure and the template DXF."""
    p = empty_project()
    p.summary.title = "DXF layer template"
    p.external = [[0, -12], [70, -12], [70, 12], [45, 12], [25, 0], [0, 0]]
    p.materials = [MaterialSpec(name="Fill"), MaterialSpec(name="Clay", color="#3cb371")]
    p.material_boundaries = [[[0, -5], [70, -5]]]
    p.water_table = [[0, -2], [25, -2], [45, 7], [70, 7]]
    p.tension_crack = [[50, 9], [70, 9]]
    p.surfaces.user_surface = [[19, 0], [24, -4.5], [34, -6.5], [44, -4], [54, 12]]
    p.support_types = [SupportType(name="Anchor")]
    p.supports = [{"a": [37, 7.2], "b": [49, 2.5], "type": "Anchor"}]
    return p


def layer_figure() -> Drawing:
    p = template_project()
    w, h = CONTENT_W, 290
    xs = [q[0] for q in p.external]
    ys = [q[1] for q in p.external]
    sx = (w - 150) / (max(xs) - min(xs))
    sy = (h - 40) / (max(ys) - min(ys))
    s = min(sx, sy)

    def t(q):
        return 10 + (q[0] - min(xs)) * s, 20 + (q[1] - min(ys)) * s

    def flat(points):
        return [c for q in points for c in t(q)]

    d = Drawing(w, h)
    d.add(
        Polygon(
            flat(p.external),
            fillColor=colors.HexColor("#f6f1dc"),
            strokeColor=colors.HexColor(LAYER_COLORS["SS_EXTERNAL"]),
            strokeWidth=2,
        )
    )
    lower = [[0, -12], [70, -12], [70, -5], [0, -5]]
    d.add(Polygon(flat(lower), fillColor=colors.HexColor("#e3efe0"), strokeColor=None))
    d.add(
        Polygon(
            flat(p.external), fillColor=None, strokeColor=colors.HexColor("#1b2433"), strokeWidth=2
        )
    )

    def poly(points, layer, width=1.8, dash=None):
        d.add(
            PolyLine(
                flat(points),
                strokeColor=colors.HexColor(LAYER_COLORS[layer]),
                strokeWidth=width,
                strokeDashArray=dash,
            )
        )

    poly(p.material_boundaries[0], "SS_MATERIAL")
    poly(p.water_table, "SS_WATER", dash=[5, 3])
    poly(p.tension_crack, "SS_CRACK", width=2.2)
    poly(p.surfaces.user_surface, "SS_SURFACE", width=2.2, dash=[2, 2])
    a, b = p.supports[0]["a"], p.supports[0]["b"]
    d.add(
        Line(*t(a), *t(b), strokeColor=colors.HexColor(LAYER_COLORS["SS_SUPPORT"]), strokeWidth=2.6)
    )
    # legend
    lx, ly = w - 130, h - 18
    for layer, col in LAYER_COLORS.items():
        d.add(Line(lx, ly + 3, lx + 22, ly + 3, strokeColor=colors.HexColor(col), strokeWidth=2.4))
        d.add(String(lx + 28, ly, layer, fontName=SEMI, fontSize=8.5, fillColor=NAVY))
        ly -= 16
    d.add(String(10, 4, "x →", fontName=SANS, fontSize=8, fillColor=MUTED))
    d.add(String(0, h - 12, "y ↑ (m)", fontName=SANS, fontSize=8, fillColor=MUTED))
    return d


# ------------------------------------------------------------- examples
SNIPPETS: dict[str, str] = {}


def snippet(name: str, source: str) -> CodeBlock:
    SNIPPETS[name] = source
    return CodeBlock(source, name)


# Messages the guide quotes; each must occur in one of these files.
ERRORS = [
    (
        "DXF needs exactly one closed SS_EXTERNAL (or layer 0) boundary.",
        "No external boundary, or more than one closed polyline on SS_EXTERNAL / layer 0. "
        "Keep one closed outline; move other closed shapes to another layer.",
    ),
    (
        "SS_EXTERNAL must be a closed polyline.",
        "The outline is open, or drawn as separate LINEs. Join it into one polyline and "
        "close it (JOIN / PEDIT → Close).",
    ),
    (
        "Multiple entities on SS_WATER; join them before importing.",
        "SS_WATER, SS_CRACK or SS_SURFACE holds more than one entity. Join them into one polyline.",
    ),
    (
        "Only planar XY geometry at Z=0 is supported.",
        "Some vertices have Z ≠ 0. Flatten the drawing (FLATTEN, or set Z to 0).",
    ),
    (
        "The external boundary intersects itself (invalid polygon).",
        "The outline crosses itself. Fix the vertex order or remove the loop.",
    ),
    ("The external boundary has zero area.", "The outline is degenerate (all points on a line)."),
    (
        "Water table points must be in increasing x order.",
        "The water table runs right to left or turns back. Reverse it (REVERSE) and remove "
        "back-steps.",
    ),
    (
        "The tension crack line needs at least 2 points with different x values.",
        "The crack line is a single point or vertical.",
    ),
]
SOURCES = [
    ROOT / "slipsurface" / "exchange.py",
    ROOT / "slipsurface" / "geometry" / "builder.py",
    ROOT / "slipsurface" / "project.py",
]


def check(template: Path = TEMPLATE) -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in SOURCES)
    for message, _ in ERRORS:
        # the layer name is filled in at run time
        message = message.replace("on SS_WATER;", "on {layer};")
        if message not in text:
            raise SystemExit(f"guide quotes a message the code no longer has: {message!r}")
    export_dxf(template_project(), template)
    project, warnings = import_dxf(template)
    ref = template_project()
    assert project.external == ref.external, "template external boundary"
    assert project.material_boundaries == ref.material_boundaries
    assert project.water_table == ref.water_table and project.tension_crack == ref.tension_crack
    assert project.surfaces.user_surface == ref.surfaces.user_surface
    assert any("SS_SUPPORT" in w for w in warnings), "supports are skipped on import"
    with tempfile.TemporaryDirectory() as tmp:
        for name, source in SNIPPETS.items():
            namespace = {"__name__": "__guide__", "TEMPLATE": str(template), "TMP": tmp}
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(source, name, "exec"), namespace)
            except Exception as exc:
                msg = f"guide example {name!r} fails: {type(exc).__name__}: {exc}"
                raise SystemExit(msg) from None


# ----------------------------------------------------------------- text
def build_story() -> list:
    s: list = []
    ch = Chapters(s)

    # 1 -------------------------------------------------------------------
    ch.chapter(
        "Overview",
        "File → Import DXF reads the 2D geometry of a slope from a CAD drawing. Each kind "
        "of line is recognised by its layer name.",
    )
    for text in (
        "<b>Geometry only.</b> The external boundary, material boundaries, water table, "
        "tension crack and a user slip surface are read. Materials, loads, supports and "
        "settings are not part of DXF.",
        "<b>Replaces the open model.</b> Importing creates a new model with one default "
        "material (Soil 1) and the file name as title. <b>Ctrl+Z</b> brings the previous "
        "model back.",
        "<b>Checked on import.</b> The geometry is built immediately; any problem is reported "
        "and nothing changes. Skipped entities and layers are listed in the message after a "
        "successful import.",
        "<b>File → Export DXF</b> writes the same layers, so a model can go to CAD and back.",
    ):
        s.append(P("•  " + text))
    s.append(Spacer(1, 4))
    s.append(layer_figure())
    s.append(
        P(
            '<font color="#5b6678" size="9">The layers of a slope model. The same model is '
            "in the template drawing <b>docs/DXF_Layer_Template.dxf</b>.</font>"
        )
    )

    # 2 -------------------------------------------------------------------
    ch.chapter("Layer reference", "Layer names are not case-sensitive (ss_water = SS_WATER).")
    s.append(
        table(
            ["Layer", "Entities", "Becomes", "Rules"],
            [
                [
                    "SS_EXTERNAL",
                    "exactly 1, closed",
                    "External boundary",
                    "Required. One closed, non-self-intersecting polyline.",
                ],
                [
                    "0",
                    "1 closed",
                    "External boundary",
                    "Used when SS_EXTERNAL is not used: a closed polyline on layer 0 counts as "
                    "the outline. Open entities on layer 0 are skipped.",
                ],
                [
                    "SS_MATERIAL",
                    "any number",
                    "Material boundaries",
                    "Open lines that split the domain into regions; ends must touch the "
                    "outline (see chapter 05).",
                ],
                [
                    "SS_WATER",
                    "at most 1",
                    "Water table",
                    "Left to right with increasing x; extended horizontally to both model ends.",
                ],
                [
                    "SS_CRACK",
                    "at most 1",
                    "Tension crack line",
                    "Its depth below the ground surface is the crack depth.",
                ],
                [
                    "SS_SURFACE",
                    "at most 1",
                    "User slip surface",
                    "Stored as the user-defined surface; select it in Surface Options.",
                ],
                [
                    "SS_SUPPORT",
                    "export only",
                    "—",
                    "Written on export (one line per support); skipped on import.",
                ],
                ["any other", "—", "skipped", "Listed in the import message."],
            ],
            [1.7, 1.6, 1.8, 4.6],
            code_cols=(0,),
        )
    )
    s.append(Spacer(1, 8))
    s.append(
        callout(
            "tip",
            "Start from the template",
            "Open <b>docs/DXF_Layer_Template.dxf</b> in your CAD program: it already has "
            "every layer and one entity on each. Draw over it, delete what you do not need, "
            "and save as DXF.",
        )
    )

    # 3 -------------------------------------------------------------------
    ch.chapter(
        "Entities, curves and units",
        "What is read from the drawing and how it is converted to metres.",
    )
    ch.h2("Entities")
    s.append(
        table(
            ["Entity", "Read as"],
            [
                ["LINE", "Two-point line."],
                ["LWPOLYLINE", "Polyline; arc segments (bulges) are converted to straight pieces."],
                ["POLYLINE", "2D polyline (same as LWPOLYLINE)."],
                ["ARC", "Converted to straight pieces."],
                ["SPLINE", "Converted to straight pieces."],
                [
                    "CIRCLE, ELLIPSE, TEXT, MTEXT, INSERT (blocks), HATCH, DIMENSION, POINT, …",
                    "Skipped and listed in the import message.",
                ],
            ],
            [4.2, 5.4],
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        P(
            "Curves are replaced by straight segments that stay within <b>1 cm</b> of the "
            "true curve. Blocks are not exploded: explode them in CAD first."
        )
    )
    ch.h2("Units")
    s.append(
        P(
            "The drawing unit ($INSUNITS, set with the UNITS command in most CAD programs) is "
            "converted to metres. A drawing without units is read as metres, with a warning."
        )
    )
    s.append(
        table(
            ["Drawing unit", "Factor to metres", "Example: 12 500 drawing units"],
            [
                ["Millimetres", "0.001", "12.5 m"],
                ["Centimetres", "0.01", "125 m"],
                ["Metres", "1", "12 500 m"],
                ["Feet", "0.3048", "3 810 m"],
                ["Inches", "0.0254", "317.5 m"],
                ["Unitless", "1 (warning)", "12 500 m"],
            ],
            [3, 3, 3.6],
        )
    )
    s.append(Spacer(1, 8))
    s.append(
        callout(
            "warn",
            "Coordinates",
            "x is horizontal and y is vertical (elevation), both in the drawing plane at "
            "Z = 0. A cross-section drawn in a rotated UCS or at an elevation Z must be moved "
            "to the world XY plane first. Geometry with Z ≠ 0 is refused.",
        )
    )

    # 4 -------------------------------------------------------------------
    ch.chapter("Preparing a drawing in CAD", "A checklist that avoids nearly every import error.")
    s.append(
        table(
            ["#", "Step", "Typical commands"],
            [
                ["1", "Copy the cross-section into a new drawing.", "WBLOCK, COPYCLIP"],
                ["2", "Set the drawing units (preferably metres).", "UNITS, INSUNITS"],
                ["3", "Explode blocks and groups.", "EXPLODE"],
                ["4", "Move everything to Z = 0 in the world XY plane.", "FLATTEN, UCS World"],
                [
                    "5",
                    "Join the outline into ONE polyline and close it.",
                    "JOIN, PEDIT → Join / Close",
                ],
                [
                    "6",
                    "Put each line on its layer (SS_EXTERNAL, SS_MATERIAL, …).",
                    "LAYER, Properties",
                ],
                [
                    "7",
                    "Join the water table into one polyline running left to right.",
                    "JOIN, REVERSE",
                ],
                [
                    "8",
                    "Extend material boundaries until they meet the outline.",
                    "EXTEND, object snaps",
                ],
                [
                    "9",
                    "Delete hatches, text and dimensions (or keep them on other layers).",
                    "ERASE",
                ],
                ["10", "Save as DXF (any version, e.g. R2010).", "SAVEAS → DXF"],
            ],
            [0.5, 6, 3],
            code_cols=(),
        )
    )

    # 5 -------------------------------------------------------------------
    ch.chapter("Layer details")
    ch.h2("External boundary — SS_EXTERNAL")
    s.append(
        P(
            "One closed outline of the whole model: ground surface on top, the sides and the "
            "base. The vertex order does not matter. Separate LINE entities are not joined "
            "automatically; the import stops with “SS_EXTERNAL must be a closed polyline.”"
        )
    )
    ch.h2("Material boundaries — SS_MATERIAL")
    s.append(
        P(
            "Each open line divides the region it crosses. Line ends lying close to the "
            "outline or to another boundary are snapped onto it. After the import, assign "
            "materials with <b>Properties → Assign Material</b>; until then every region "
            "uses Soil 1."
        )
    )
    s.append(
        callout(
            "warn",
            "Ends must reach the outline",
            "Ends are snapped within <b>0.2 % of the larger model dimension</b> (12 cm for a "
            "60 m wide model). A boundary that stops farther away is kept but does not split "
            "the region — the model then has fewer regions than expected. Extend the lines "
            "onto the outline in CAD.",
        )
    )
    ch.h2("Water table — SS_WATER")
    s.append(
        P(
            "One polyline with increasing x (left to right, no back-steps). It is extended "
            "horizontally from its first and last points to the model ends. After import the "
            "groundwater method is <i>water table</i>; per-material Hu is set in the material "
            "dialog."
        )
    )
    ch.h2("Tension crack — SS_CRACK")
    s.append(
        P(
            "One line or polyline above or on the ground; at least two points with different "
            "x. The crack depth at each x is its distance below the ground surface. Set the "
            "water filling in <b>Project Settings → Groundwater</b>."
        )
    )
    ch.h2("User slip surface — SS_SURFACE")
    s.append(
        P(
            "One polyline, arc or spline. It is stored as the user-defined surface, but the "
            "surface type is not switched: choose <b>Surfaces → Surface Options → "
            "User-defined</b> to analyse it."
        )
    )

    # 6 -------------------------------------------------------------------
    ch.chapter("After the import", "Complete the model in the Modeler.")
    for i, text in enumerate(
        (
            "Read the import message: it lists skipped entities and layers.",
            "Define materials (<b>Properties → Define Materials</b>) and assign "
            "them to the regions.",
            "Add loads, supports and facings, and set seismic coefficients if needed.",
            "Choose the slip surface type and search options.",
            "<b>Compute (F5)</b>, then save the model as <b>.slp.json</b> — that file keeps "
            "everything, DXF keeps only geometry.",
        ),
        1,
    ):
        s.append(P(f"<b>{i}.</b>  {text}"))

    # 7 -------------------------------------------------------------------
    ch.chapter("Exporting to DXF")
    s.append(
        P(
            "<b>File → Export DXF</b> writes an AutoCAD R2010 drawing in metres with the "
            "layers below. It needs an external boundary."
        )
    )
    s.append(
        table(
            ["Written", "Not written"],
            [
                [
                    "SS_EXTERNAL (closed), SS_MATERIAL, SS_WATER, SS_CRACK, SS_SURFACE, "
                    "SS_SUPPORT (single supports)",
                    "Materials and assignments, loads, bolt patterns, facings, notes, "
                    "settings and results",
                ]
            ],
            [5, 5],
            code_cols=(),
        )
    )
    s.append(Spacer(1, 6))
    s.append(
        P(
            "Exported files import back unchanged (the supports layer is skipped on import), "
            "so DXF is a safe way to edit the geometry in CAD and return."
        )
    )

    # 8 -------------------------------------------------------------------
    ch.chapter(
        "DXF from Python",
        "The import and export functions can be used in a Python script (Tools → Python "
        "scripting) or any Python program.",
    )
    s.append(
        snippet(
            "import_in_a_script.py",
            """from slipsurface.exchange import import_dxf

project, warnings = import_dxf(TEMPLATE)   # path of a .dxf file
for line in warnings:
    print(line)
project.materials[0].c = 10   # continue the model as usual
project.materials[0].phi = 28""",
        )
    )
    s.append(
        P(
            "In the scripting editor write the file path instead of "
            + code("TEMPLATE")
            + ", e.g. "
            + code('r"C:\\models\\section.dxf"')
            + "."
        )
    )
    s.append(
        snippet(
            "write_a_dxf_with_ezdxf.py",
            """import ezdxf
from pathlib import Path
from slipsurface.exchange import import_dxf

doc = ezdxf.new("R2010")
doc.units = ezdxf.units.M
msp = doc.modelspace()
for layer in ("SS_EXTERNAL", "SS_MATERIAL", "SS_WATER"):
    doc.layers.add(layer)
outline = [(0, -10), (60, -10), (60, 10), (40, 10), (20, 0), (0, 0)]
msp.add_lwpolyline(outline, close=True, dxfattribs={"layer": "SS_EXTERNAL"})
msp.add_line((0, -4), (60, -4), dxfattribs={"layer": "SS_MATERIAL"})
msp.add_lwpolyline([(0, -2), (20, -2), (40, 5), (60, 5)],
                   dxfattribs={"layer": "SS_WATER"})
path = Path(TMP) / "section.dxf"
doc.saveas(path)
project, warnings = import_dxf(path)
print(len(project.build_geometry().regions), "regions")""",
        )
    )
    s.append(
        P(
            "Export works the same way: "
            + code("from slipsurface.exchange import export_dxf")
            + " and "
            + code('export_dxf(project, "section.dxf")')
            + "."
        )
    )

    # 9 -------------------------------------------------------------------
    ch.chapter("Messages and fixes", "Import messages, word for word, and what to do.")
    s.append(table(["Message", "Cause and fix"], [list(e) for e in ERRORS], [4, 5.6]))
    s.append(Spacer(1, 6))
    s.append(
        table(
            ["Notice after a successful import", "Meaning"],
            [
                [
                    "DXF has no units; coordinates interpreted as metres.",
                    "Set the drawing units if the drawing is not in metres.",
                ],
                ["Skipped entities/layers: …", "These entities were ignored (see chapter 03)."],
                [
                    "DXF transfers geometry only. Assign materials, loads and supports separately.",
                    "Always shown; continue with chapter 06.",
                ],
            ],
            [4, 5.6],
        )
    )
    return s


def build(path: Path = OUT, template: Path = TEMPLATE) -> Path:
    """Write the guide to ``path`` and the layer template to ``template``."""
    story = build_story()  # registers the examples that check() runs
    return write(
        path,
        story,
        "DXF Import Guide",
        ["DXF Import", "Guide"],
        "Bring slope cross-sections from CAD into SlipSurfaceIQ LE",
        check=lambda: check(template),
    )


if __name__ == "__main__":
    out = build()
    print(f"wrote {out} ({out.stat().st_size // 1024} KiB) and {TEMPLATE.name}")
