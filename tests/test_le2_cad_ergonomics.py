"""LE-2 regression tests: non-destructive CAD editing, OSNAP, coordinate entry,
multi-feature ground sync, and 1366x768 / 1920x1080 / HiDPI layout ergonomics."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from slipsurface.loads import into_slope_direction  # noqa: E402
from slipsurface.project import MaterialSpec, Project, acads_1a_project, _mk  # noqa: E402
from slipsurface.ui.cad import tools as T  # noqa: E402
from slipsurface.ui.cad.model import delete_entity, entities  # noqa: E402
from tests.models import layered_example_project, nailed_shotcrete_project  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app):
    from slipsurface.ui.modeler import ModelerWindow

    w = ModelerWindow(layered_example_project())
    w.resize(1366, 768)
    w.show()
    for _ in range(5):
        app.processEvents()
    yield w
    w.doc.mark_clean()
    for iw in list(w.interpret_windows):
        iw.close()
        app.processEvents()
    w.close()
    app.processEvents()


def test_redrawing_and_deleting_external_boundary_is_non_destructive(win):
    orig_bounds = [list(map(list, b)) for b in win.doc.project.material_boundaries]
    orig_assigns = [dict(a) for a in win.doc.project.assignments]
    assert len(orig_bounds) == 2 and len(orig_assigns) == 3

    # Redrawing external boundary must keep existing stratigraphy & material assignments
    new_ext = [[0, -14], [70, -14], [70, 15], [50, 12], [40, 12], [20, 0], [0, 0]]
    win._on_drawn("external", new_ext)
    assert win.doc.project.material_boundaries == orig_bounds
    assert win.doc.project.assignments == orig_assigns
    assert win.doc.geometry is not None and len(win.doc.geometry.regions) >= 3

    # Deleting external boundary also preserves interior material boundaries & assignments
    win.doc.edit("Delete external", lambda p: delete_entity(p, ("external", 0)))
    assert win.doc.project.external == []
    assert win.doc.project.material_boundaries == orig_bounds
    assert win.doc.project.assignments == orig_assigns

    # Undo twice restores the exact initial state
    win.doc.undo_stack.undo()
    win.doc.undo_stack.undo()
    assert win.doc.project.to_dict() == layered_example_project().to_dict()


def test_canvas_typing_forwarding_direct_distance_and_close_guard(app, win):
    c = win.canvas
    c.set_tool(T.DrawTool(c, "external"))
    c.setFocus()
    app.processEvents()

    # Typing coordinate characters while canvas has focus forwards into status.cmd
    QTest.keyClick(c, Qt.Key_1)
    QTest.keyClick(c, Qt.Key_0)
    app.processEvents()
    assert win.status.cmd.text() == "10"

    win.status.cmd.clear()
    assert c.command("0,0")
    # Direct-distance entry along current snapped/ortho preview direction
    c.tool.preview = (25.0, 0.0)
    assert c.command("40")
    assert c.tool.pts[-1] == pytest.approx((40.0, 0.0))

    # Open polyline tools must refuse 'c'/'close' instead of pretending to close
    c.set_tool(T.DrawTool(c, "water"))
    assert c.command("0,2") and c.command("30,4")
    assert c.command("c") is False
    assert c.tool.name == "draw_water" and len(c.tool.pts) == 2


def test_osnap_closest_midpoint_drag_exclusion_and_annotation_filtering(win):
    p = acads_1a_project()
    # Add two close material segments whose midpoints both fall inside PICK_PX:
    # Midpoint 0 at (20, 5.0), Midpoint 1 at (20, 5.08)
    p.material_boundaries = [
        [[10.0, 5.0], [30.0, 5.0]],
        [[10.0, 5.08], [30.0, 5.08]],
    ]
    # Add a text annotation right next to (20, 5.07) — must not hijack OSNAP!
    p.annotations = [{"kind": "text", "pts": [[20.0, 5.07]], "text": "Callout"}]
    win.load_project(p)
    c = win.canvas
    c.osnap_on = True
    c.snap_on = False
    c.zoom_extents()

    # Cursor at (20, 5.075) is much closer to midpoint (20, 5.08) than (20, 5.0)
    sp = c.w2s(20.0, 5.075)
    snapped, kind = c.snap(sp)
    assert kind == "mid"
    assert snapped == pytest.approx((20.0, 5.08), abs=1e-6)

    # Dragging vertex 0 of closed external boundary must exclude its closing segment (n-1 -> 0)
    c.osnap_on = True
    v0 = p.external[0]
    v_last = p.external[-1]
    mid_closing = ((v0[0] + v_last[0]) / 2.0, (v0[1] + v_last[1]) / 2.0)
    # Near a point along closing edge (away from other vertices): must NOT self-snap 'near' or 'mid'
    sp_close = c.w2s(mid_closing[0], mid_closing[1])
    _, drag_kind = c.snap(sp_close, exclude=(("external", 0), 0))
    assert drag_kind not in ("mid", "near")


def test_combined_model_ground_projection_and_grid_spacing_roundtrip(tmp_path, win):
    p = nailed_shotcrete_project()
    p.water_table = [[0.0, -2.0], [20.0, -1.0], [48.0, 4.0]]
    p.groundwater.method = "water_table"
    p.loads.append({"kind": "line", "point": [35.0, 12.0], "magnitude": 50.0, "angle": 270.0})
    win.load_project(p)

    # Raise the slope crest from y = 12 to y = 15
    def raise_crest(proj: Project) -> None:
        proj.external = [[0, -8], [48, -8], [48, 15], [26, 15], [20, 0], [0, 0]]
        proj.display["grid_spacing"] = 2.5

    win.doc.edit("Raise crest", raise_crest)
    assert win.canvas.grid_spacing == pytest.approx(2.5)
    g = win.doc.geometry
    assert g is not None

    # Entity grips for loads, patterns, and facings follow the updated ground profile
    ent_map = {e.key: e for e in entities(win.doc.project, g)}
    assert ent_map[("load", 0)].pts[0, 1] == pytest.approx(15.0)
    assert ent_map[("load", 1)].pts[0, 1] == pytest.approx(15.0)
    assert ent_map[("pattern", 0)].pts[1, 1] == pytest.approx(15.0)
    assert ent_map[("facing", 0)].pts[1, 1] == pytest.approx(15.0)

    # Round-trip save/load preserves everything including grid_spacing
    out = tmp_path / "combined_le2.slp.json"
    win.doc.project.save(out)
    reloaded = Project.load(out)
    assert reloaded.to_dict() == win.doc.project.to_dict()
    assert reloaded.display_opt("grid_spacing") == pytest.approx(2.5)


def test_workflow_step_safety_del_mid_draw_guard_and_embankment_direction(win):
    c = win.canvas
    # Active MeasureTool must NOT be hijacked when clicking Properties step
    c.set_tool(T.MeasureTool(c))
    win._step_changed(3)  # Properties
    assert c.tool.name == "measure"

    # When in SelectTool, entering Properties activates AssignTool, and leaving restores SelectTool
    c.select_tool()
    win._step_changed(3)
    assert c.tool.name == "assign"
    win._step_changed(0)
    assert c.tool.name == "select"

    # Pressing Delete while DrawTool is active must NOT delete a lingering selection
    n_bounds = len(win.doc.project.material_boundaries)
    c.selection = ("material", 0)
    c.set_tool(T.DrawTool(c, "material"))
    win.delete_selection()
    assert len(win.doc.project.material_boundaries) == n_bounds

    # Symmetric embankment (left toe y=0, right toe y=0, crest x=10..20 y=6):
    emb = _mk(
        "Symmetric embankment",
        [MaterialSpec("Fill", "MC", 19, 20, False, 5, 32)],
        [[-10, -5], [40, -5], [40, 0], [30, 0], [20, 6], [10, 6], [0, 0], [-10, 0]],
    ).build_geometry()
    # Left slope / left crest corner x=10 should point +x (into embankment), right corner x=20 -> -x
    assert into_slope_direction(emb, 5.0, 15.0)[0] > 0
    assert into_slope_direction(emb, 10.0, 15.0)[0] > 0
    assert into_slope_direction(emb, 25.0, 15.0)[0] < 0


def test_1366x768_and_1920x1080_dialogs_and_non_overlapping_legends(app, win):
    from slipsurface.analysis import run_analysis
    from slipsurface.ui.dialogs.report import ReportDialog
    from slipsurface.ui.interpret import InterpretWindow

    p = acads_1a_project()
    p.methods.methods = [
        "bishop",
        "ordinary",
        "janbu_simplified",
        "janbu_corrected",
        "spencer",
        "gle",
    ]
    p.surfaces.effort = "fast"
    p.display["show_all_surfaces"] = True
    res = run_analysis(p)

    dlg = ReportDialog(p, win)
    assert dlg.findChild(QScrollArea) is not None
    assert dlg.height() <= 730
    dlg.close()

    for w_px, h_px in ((1366, 768), (1920, 1080)):
        iw = InterpretWindow(res)
        iw.resize(w_px, h_px)
        iw.show()
        for _ in range(5):
            app.processEvents()
        iw.canvas.grab()
        rects = getattr(iw.canvas, "_legend_rects", [])
        assert len(rects) >= 3  # contour + material/all-surfaces + FS table
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                assert not rects[i].intersects(rects[j]), (
                    f"Legend collision at {w_px}x{h_px}: {rects[i]} vs {rects[j]}"
                )
        iw.close()
        app.processEvents()
