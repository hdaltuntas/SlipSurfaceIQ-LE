"""Headless GUI tests (QT_QPA_PLATFORM=offscreen)."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slipsurface.project import (  # noqa: E402
    MaterialSpec,
    acads_1a_project,
    empty_project,
    layered_example_project,
)
from slipsurface.ui.cad import tools as T  # noqa: E402
from slipsurface.ui.cad.tools import parse_coordinate  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app):
    from slipsurface.ui.modeler import ModelerWindow

    w = ModelerWindow(layered_example_project())
    w.resize(1400, 900)
    w.show()
    for _ in range(5):
        app.processEvents()
    yield w
    w.doc.mark_clean()
    for iw in w.interpret_windows:
        iw.close()
    w.close()
    app.processEvents()


def wait_for(app, cond, timeout=120.0):
    t0 = time.time()
    while not cond():
        app.processEvents()
        time.sleep(0.01)
        if time.time() - t0 > timeout:
            raise TimeoutError
    for _ in range(5):
        app.processEvents()


def screen(c, x, y) -> QPoint:
    s = c.w2s(x, y)
    return QPoint(int(round(s.x())), int(round(s.y())))


# ------------------------------------------------------------ parsing
@pytest.mark.parametrize(
    "text,last,expected",
    [
        ("10,5", None, (10, 5)),
        ("10 5", None, (10, 5)),
        ("-2.5;3", None, (-2.5, 3)),
        ("@5,0", (1, 1), (6, 1)),
        ("@10<90", (0, 0), (0, 10)),
        ("@2<0", (1, 1), (3, 1)),
    ],
)
def test_parse_coordinate(text, last, expected):
    x, y = parse_coordinate(text, last)
    assert x == pytest.approx(expected[0], abs=1e-9) and y == pytest.approx(expected[1], abs=1e-9)


def test_parse_coordinate_invalid():
    assert parse_coordinate("abc", None) is None
    assert parse_coordinate("@1,1", None) is None


# ------------------------------------------------------------- window
def test_layout(win):
    assert win.workflow.width() > 200
    titles = [a.text().replace("&", "") for a in win.menuBar().actions()]
    assert titles == [
        "Dosya",
        "Düzen",
        "Görünüm",
        "Analiz",
        "Sınırlar",
        "Yükleme",
        "Destek",
        "Yüzeyler",
        "Özellikler",
        "Araçlar",
        "Yardım",
    ]
    assert win.workflow.steps == ["Geometri", "Destek", "Yükleme", "Özellikler", "Yüzeyler"]
    assert set(win.status.toggles) == {"snap_on", "grid_on", "ortho_on", "osnap_on"}
    assert win.doc.geometry is not None and len(win.doc.geometry.regions) == 4


def test_model_edits_invalidate_results_but_display_edits_do_not(win):
    results = fixed_results(win)
    win.last_results = results
    win._update_actions()
    win.interpret()
    old_window = win.interpret_windows[-1]
    win.doc.edit("display", lambda p: p.display.update(show_grid=False))
    assert win.last_results is results and win.a_report.isEnabled()
    win.doc.edit("material", lambda p: setattr(p.materials[0], "c", 123))
    assert win.last_results is None
    assert not old_window.isVisible()
    assert not win.a_report.isEnabled() and not win.a_interpret.isEnabled()
    win.doc.undo_stack.undo()
    assert win.last_results is None


def fixed_results(win):
    from slipsurface.analysis import AnalysisResults
    from slipsurface.geometry import CircularSurface
    from slipsurface.lem import analyze
    from slipsurface.optimizer import SearchResult

    win.load_project(acads_1a_project())
    p = win.doc.project
    surf = CircularSurface(20, 28, 28)
    lem, slices = analyze(win.doc.geometry, surf, p.build_materials())
    assert lem.ok
    return AnalysisResults(
        p.copy(), win.doc.geometry, results={"bishop": SearchResult(surf, lem.fos, lem, slices, 1)}
    )


def test_empty_results_disable_result_actions(win):
    from slipsurface.analysis import AnalysisResults

    win.last_results = AnalysisResults(win.doc.project.copy(), win.doc.geometry)
    win._update_actions()
    assert not win.a_report.isEnabled() and not win.a_interpret.isEnabled()
    win.interpret()
    assert not win.interpret_windows


def test_interpret_reuses_window_and_explains_partial_results(win):
    win.last_results = fixed_results(win)
    win.last_results.errors["spencer"] = "Yakınsama sağlanamadı."
    win.interpret()
    iw = win.interpret_windows[-1]
    win.interpret()
    assert len(win.interpret_windows) == 1
    assert iw.result_warning.isVisible()
    assert "Spencer" in iw.result_warning.text()
    assert "Yakınsama" in iw.result_warning.text()
    iw._display_option("show_fs_legend", False)
    iw._display_option("show_all_surfaces", True)
    iw._display_reset()
    assert iw.a_fs_legend.isChecked() and not iw.a_all.isChecked()  # default: contour map
    assert not iw.project.display_opt("show_vertices")


def test_close_during_analysis_is_deferred(app, win, monkeypatch):
    from threading import Event
    from slipsurface.optimizer import SearchCancelled

    started, release = Event(), Event()

    def slow_analysis(project, progress, **kw):
        started.set()
        release.wait(5)
        assert progress(0, 1, "bishop", 1, 1.0)
        raise SearchCancelled()

    monkeypatch.setattr("slipsurface.ui.worker.run_analysis", slow_analysis)
    win.compute()
    wait_for(app, started.is_set)
    try:
        win.close()
        assert win.isVisible() and win._close_pending and win.busy
        assert not win.a_compute.isEnabled()
    finally:
        release.set()
    wait_for(app, lambda: not win.busy and not win.isVisible())


def test_compute_stays_disabled_until_thread_finishes(win):
    win._thread = object()
    win._end_compute()
    assert not win.a_compute.isEnabled()
    win._on_thread_finished()
    assert win.a_compute.isEnabled()


@pytest.mark.parametrize("success", [True, False])
def test_image_export_checks_save_result(win, monkeypatch, success):
    from types import SimpleNamespace
    from slipsurface.ui import export

    saved, warnings = [], []
    monkeypatch.setattr(
        export.QFileDialog, "getSaveFileName", lambda *a: ("drawing", "JPEG (*.jpg *.jpeg)")
    )

    def save(path):
        saved.append(path)
        return success

    monkeypatch.setattr(export.QMessageBox, "warning", lambda *a: warnings.append(a))
    widget = SimpleNamespace(grab=lambda: SimpleNamespace(save=save))
    result = export.export_image(win, widget, "model.png")
    assert saved == ["drawing.jpg"]
    assert bool(warnings) is not success
    assert result == ("drawing.jpg" if success else None)


def test_user_surface_disables_search_controls(win):
    from slipsurface.ui.dialogs.surface_options import SurfaceOptionsDialog

    dlg = SurfaceOptionsDialog(win.doc.project, win)
    dlg.r_user.setChecked(True)
    assert not dlg.opt_btn.isEnabled() and not dlg.use_limits.isEnabled()
    dlg.r_non.setChecked(True)
    assert dlg.opt_btn.isEnabled() and dlg.shape.isEnabled()
    assert "poligonal" in dlg.r_non.text()
    dlg.use_limits.setChecked(True)
    dlg.l0.setValue(1000)
    dlg.l1.setValue(1100)
    dlg._accept()
    assert "kesişmeli" in dlg.error.text()


def test_stale_background_result_is_not_installed(win):
    from slipsurface.analysis import AnalysisResults

    results = AnalysisResults(win.doc.project.copy(), win.doc.geometry)
    win.doc.edit("material", lambda p: setattr(p.materials[0], "c", 123))
    win._on_finished(results)
    assert win.last_results is None
    assert not win.a_report.isEnabled()


def test_draw_external_by_commands_undo_redo(app, win):
    win.load_project(empty_project())
    c = win.canvas
    c.set_tool(T.DrawTool(c, "external"))
    for cmd in ["0,-10", "@60,0", "@0,20", "40,10", "20,0", "0,0", "c"]:
        assert c.command(cmd)
    app.processEvents()
    p = win.doc.project
    assert len(p.external) == 6 and win.doc.geometry is not None
    assert win.doc.geometry.domain.area == pytest.approx(
        60 * 20 - 15 * 10 * 0 - 20 * 10 - 0.5 * 20 * 10
    )
    win.doc.undo_stack.undo()
    assert win.doc.project.external == []
    win.doc.undo_stack.redo()
    assert len(win.doc.project.external) == 6


def test_draw_material_boundary_and_assign(app, win):
    win.load_project(acads_1a_project())
    c = win.canvas
    c.set_tool(T.DrawTool(c, "material"))
    assert c.command("0,-2") and c.command("60,-2") and c.command("")
    assert len(win.doc.project.material_boundaries) == 1
    assert len(win.doc.geometry.regions) == 2
    win.doc.edit("mat", lambda p: p.materials.append(MaterialSpec("Kil", color="#8080d0")))
    c.assign_material = "Kil"
    c.set_tool(T.AssignTool(c))
    app.processEvents()
    QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, screen(c, 30, -4))
    mats = {r.material for r in win.doc.geometry.regions}
    assert mats == {"Soil 1", "Kil"}


def test_osnap_and_grid_snap(app, win):
    c = win.canvas
    c.osnap_on, c.snap_on = True, False
    pt, kind = c.snap(c.w2s(40.05, 12.03))
    assert kind == "end" and pt == pytest.approx((40.0, 12.0))
    c.osnap_on, c.snap_on, c.grid_spacing = False, True, 1.0
    pt, kind = c.snap(c.w2s(10.4, 3.6))
    assert kind == "grid" and pt == pytest.approx((10.0, 4.0))
    c.ortho_on = True
    pt, kind = c.snap(c.w2s(13.2, 4.4), ref=(10.0, 4.0))
    assert pt == pytest.approx((13.0, 4.0))
    c.ortho_on = c.snap_on = False
    c.osnap_on = True


def test_drag_vertex_and_undo(app, win):
    c = win.canvas
    c.select_tool()
    c.osnap_on = False
    before = [list(q) for q in win.doc.project.external]
    k = before.index([40.0, 12.0])
    QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, screen(c, 40, 12))
    QTest.mouseMove(c, screen(c, 38, 12))
    QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, screen(c, 38, 12))
    app.processEvents()
    moved = win.doc.project.external[k]
    assert moved[0] == pytest.approx(38, abs=0.2) and moved[1] == pytest.approx(12, abs=0.2)
    win.doc.undo_stack.undo()
    assert win.doc.project.external == before
    c.osnap_on = True


def test_delete_and_insert_vertex(app, win):
    from slipsurface.ui.cad.tools import _delete_vertex, _insert_vertex

    c = win.canvas
    n = len(win.doc.project.water_table)
    _insert_vertex(c, ("water", 0), 0, (10.0, -0.5))
    assert len(win.doc.project.water_table) == n + 1
    _delete_vertex(c, ("water", 0), 1)
    assert len(win.doc.project.water_table) == n


def test_water_table_must_be_x_increasing(app, win):
    c = win.canvas
    win.doc.edit("wt off", lambda p: setattr(p, "water_table", None))
    c.set_tool(T.DrawTool(c, "water"))
    for cmd in ["0,0", "30,5", "20,6", ""]:
        c.command(cmd)
    assert win.doc.project.water_table is None  # rejected


# ------------------------------------------------------------ dialogs
def test_project_settings_dialog(app, win):
    from slipsurface.ui.dialogs.project_settings import ProjectSettingsDialog

    d = ProjectSettingsDialog(win.doc.project, win, 1)
    d.method_checks["gle"].setChecked(True)
    d.method_checks["janbu_simplified"].setChecked(False)
    d.ltr.setChecked(True)
    d.kh.setValue(0.1)
    p = d.collect()
    assert "gle" in p.methods.methods and "janbu_simplified" not in p.methods.methods
    assert p.general.failure_direction == "left_to_right" and p.seismic.kh == 0.1


def test_materials_dialog_rename_propagates(app, win):
    from slipsurface.ui.dialogs.materials import MaterialsDialog

    d = MaterialsDialog(win.doc.project.materials, win, "Soft clay")
    d.name.setText("Kil (CH)")
    d._name_edited("Kil (CH)")
    assert d.renames == {"Soft clay": "Kil (CH)"}
    mats, renames = d.result_materials(), d.renames

    def fn(p):
        p.materials = mats
        for a in p.assignments:
            a["material"] = renames.get(a["material"], a["material"])

    win.doc.edit("mat", fn)
    assert "Kil (CH)" in {r.material for r in win.doc.geometry.regions}


def test_surface_options_dialog(app, win):
    from slipsurface.ui.dialogs.surface_options import SurfaceOptionsDialog

    d = SurfaceOptionsDialog(win.doc.project, win)
    d.r_non.setChecked(True)
    d.use_limits.setChecked(True)
    p = win.doc.project.copy()
    d.apply_to(p)
    assert p.surfaces.surface_type == "noncircular" and p.surfaces.left_range is not None


def test_summary_dialog(app, win):
    from slipsurface.ui.dialogs.summary import ProjectSummaryDialog

    d = ProjectSummaryDialog(win.doc.project.summary, win)
    d.table.item(2, 1).setText("H. D. Altuntaş")
    assert d.summary().author == "H. D. Altuntaş"


# ---------------------------------------------------- compute/interpret
def test_compute_opens_interpret_window(app, win):
    p = acads_1a_project()
    p.methods.methods = ["bishop", "spencer"]
    p.surfaces.effort = "fast"
    win.load_project(p)
    win.compute()
    wait_for(app, lambda: win.last_results is not None and not win.busy)
    assert win.interpret_windows, "Interpret window should open after compute"
    iw = win.interpret_windows[-1]
    assert iw.method_combo.count() == 2
    assert win.last_results.results["bishop"].fos == pytest.approx(0.987, abs=0.015)
    iw.set_method("spencer")
    assert iw.canvas.result_key == "spencer"
    # slice query
    r = win.last_results.results["spencer"]
    rows = __import__("slipsurface.ui.dialogs.misc", fromlist=["slice_rows"]).slice_rows(r, 3)
    assert rows[0][1].startswith("4 /")
    from slipsurface.analysis import report_text

    assert "Spencer" in report_text(win.last_results)


def test_cancel_compute(app, win):
    p = acads_1a_project()
    p.methods.methods = ["spencer", "gle"]
    p.surfaces.effort = "fine"
    win.load_project(p)
    win.compute()
    wait_for(app, lambda: win.progress is not None and "Nesil" in win.progress.labelText())
    win._cancel_compute()
    wait_for(app, lambda: not win.busy)
    assert win.last_results is None


# ---------------------------------------------------- loads & supports
def test_draw_support_by_commands(app, win):
    win.load_project(acads_1a_project())
    c = win.canvas
    c.set_tool(win._support_tool())  # creates a default support type
    assert win.doc.project.support_types
    assert c.command("30,5") and c.command("@20<-15")
    sp = win.doc.project.supports
    assert len(sp) == 1 and sp[0]["a"] == [30.0, 5.0]
    assert sp[0]["type"] == win.doc.project.support_types[0].name
    # still in support mode -> next support
    assert c.tool.name == "draw_support"
    win.doc.undo_stack.undo()
    assert win.doc.project.supports == []


def test_add_loads_via_tools(app, win, monkeypatch):
    from slipsurface.ui.dialogs import loads_supports as LS

    monkeypatch.setattr(LS.DistributedLoadDialog, "exec", lambda self: 1)
    monkeypatch.setattr(LS.LineLoadDialog, "exec", lambda self: 1)
    win.load_project(acads_1a_project())
    c = win.canvas
    c.set_tool(T.DrawTool(c, "load_distributed"))
    c.command("42,11")
    c.command("50,11")
    c.set_tool(T.DrawTool(c, "load_line"))
    c.command("55,10")
    loads = win.doc.project.loads
    assert [ld["kind"] for ld in loads] == ["distributed", "line"]
    assert loads[0]["points"][0][1] == pytest.approx(10.0)  # snapped onto ground
    assert loads[0]["q"] == [20.0, 20.0]
    # deletion of a selected load
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    c.select_tool()
    c.selection = ("load", 0)
    c.tool.key(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert [ld["kind"] for ld in win.doc.project.loads] == ["line"]


def test_support_types_dialog_rename(app, win):
    from slipsurface.project import anchored_example_project
    from slipsurface.ui.dialogs.loads_supports import SupportTypesDialog

    win.load_project(anchored_example_project())
    d = SupportTypesDialog(win.doc.project.support_types, win)
    d.name.setText("TB-60")
    d._rename("TB-60")
    d.kind.setCurrentIndex(2)  # soil nail
    d.r_passive.setChecked(True)
    types, ren = d.types, d.renames
    assert types[0].kind == "soil_nail" and types[0].application == "passive"

    def fn(p):
        p.support_types = types
        for sp in p.supports:
            sp["type"] = ren.get(sp["type"], sp["type"])

    win.doc.edit("sup", fn)
    assert {sp["type"] for sp in win.doc.project.supports} == {"TB-60"}
    assert win.doc.project.load_set().supports[0].stype.kind == "soil_nail"


def test_compute_with_supports(app, win):
    from slipsurface.project import anchored_example_project

    p = anchored_example_project()
    p.methods.methods = ["bishop"]
    p.surfaces.effort = "fast"
    win.load_project(p)
    win.compute()
    wait_for(app, lambda: win.last_results is not None and not win.busy)
    r = win.last_results.results["bishop"]
    assert r.fos > 1.2 and r.slices.support_forces


# ------------------------------------------------------- tension crack
def test_draw_tension_crack_and_settings(app, win):
    from slipsurface.ui.dialogs.project_settings import ProjectSettingsDialog

    win.load_project(acads_1a_project())
    c = win.canvas
    c.set_tool(win._draw("crack"))
    for cmd in ["60,7", "40,7", ""]:  # drawn right-to-left -> stored x-increasing
        c.command(cmd)
    assert win.doc.project.tension_crack == [[40.0, 7.0], [60.0, 7.0]]
    d = ProjectSettingsDialog(win.doc.project, win, 2)
    d.crack_mode.setCurrentIndex(2)
    d.crack_pct.setValue(50)
    assert d.collect().groundwater.crack_water == pytest.approx(0.5)
    win.doc.undo_stack.undo()
    assert win.doc.project.tension_crack is None


def test_crack_from_depth_points(app, win):
    from slipsurface.ui.dialogs.loads_supports import CrackFromDepthDialog

    win.load_project(acads_1a_project())
    d = CrackFromDepthDialog(35, 60, 2.0, 1.0, "", win)
    pts = d.points(win.doc.geometry.surface)
    assert pts[0] == pytest.approx([35, 5.5]) and pts[-1] == pytest.approx([60, 8.0])
    assert [40.0, 8.0] in [list(map(float, q)) for q in pts]  # follows the crest vertex


def test_compute_with_crack(app, win):
    from slipsurface.project import cracked_example_project

    p = cracked_example_project()
    p.methods.methods = ["spencer"]
    p.surfaces.effort = "fast"
    win.load_project(p)
    win.compute()
    wait_for(app, lambda: win.last_results is not None and not win.busy)
    ck = win.last_results.results["spencer"].slices.crack
    assert ck is not None and ck["Pw"] > 0


# ------------------------------------- v0.5: bolts, patterns, facing, notes
def test_single_bolt_tool_15_degrees(app, win):
    win.load_project(acads_1a_project())
    c = win.canvas
    c.set_tool(win._bolt_tool())
    assert win.bolt_angle.value() == 15.0
    st = win.doc.project.support_types[0]
    assert win.bolt_length.value() == pytest.approx(st.length)
    assert c.command("30")  # x on the slope face
    assert c.command("34")  # tool stays active
    sp = win.doc.project.supports
    assert len(sp) == 2 and c.tool.name == "bolt"
    a, b = np.array(sp[0]["a"]), np.array(sp[0]["b"])
    assert a == pytest.approx([30.0, 5.0])  # head on the ground
    d = b - a
    assert np.hypot(*d) == pytest.approx(st.length)
    assert np.degrees(np.arctan2(-d[1], d[0])) == pytest.approx(15.0)  # into slope, 15° down


def test_bolt_pattern_dialog_and_engine(app, win, monkeypatch):
    from slipsurface.ui.dialogs import facing_pattern_annot as D

    def fake_exec(self):
        self.spacing.setValue(2.5)
        self.offset.setValue(1.0)
        return 1

    monkeypatch.setattr(D.PatternDialog, "exec", fake_exec)
    win.load_project(acads_1a_project())
    c = win.canvas
    c.set_tool(win._pattern_tool())
    c.command("20,0")
    c.command("40,10")
    pats = win.doc.project.support_patterns
    assert len(pats) == 1 and pats[0]["spacing"] == 2.5 and pats[0]["angle"] == 15.0
    bolts = win.doc.project.pattern_bolts(pats[0], win.doc.geometry)
    face = np.hypot(20, 10)
    assert len(bolts) == int((face - 1.0) / 2.5) + 1
    ls = win.doc.project.load_set()
    assert len(ls.supports) == len(bolts) and ls.supports[0].label == "Patern 1/1"
    # double click opens the pattern dialog (edits the pattern)
    win.edit_coordinates(("pattern", 0))
    assert len(win.doc.project.support_patterns) == 1


def test_facing_types_dialog_and_assign_face(app, win):
    from slipsurface.ui.dialogs.facing_pattern_annot import FacingTypesDialog
    from slipsurface.loads import FacingType

    d = FacingTypesDialog([FacingType()], win)
    d.thickness.setValue(0.15)
    d.mesh.setCurrentIndex(d.mesh.findData("Q257"))
    t = d.types[0]
    assert t.thickness == 0.15 and t.mesh == "Q257" and t.mesh_as == 257
    assert t.capacity == pytest.approx(400 * 0.15 + 257 * 500 / 1000)
    win.load_project(acads_1a_project())
    assert win.slope_face_range() == (20.0, 40.0)
    win.facing_whole_face()  # creates a default facing type
    p = win.doc.project
    assert p.facing_types and p.facings[0]["x1"] == 20.0 and p.facings[0]["x2"] == 40.0
    assert p.facings[0]["points"][1] == [40.0, 10.0]
    assert len(p.load_set().facings) == 1


def test_annotations_in_modeler(app, win, monkeypatch):
    from slipsurface.ui.dialogs import facing_pattern_annot as D

    def fake_exec(self):
        self.text.setPlainText("Kritik bölge")
        return 1

    monkeypatch.setattr(D.AnnotationDialog, "exec", fake_exec)
    win.load_project(acads_1a_project())
    c = win.canvas
    c.set_tool(T.DrawTool(c, "annot_text"))
    c.command("10,15")
    c.set_tool(T.DrawTool(c, "annot_arrow"))
    c.command("12,14")
    c.command("25,4")
    c.set_tool(T.DrawTool(c, "annot_rect"))
    c.command("18,-2")
    c.command("44,12")
    ann = win.doc.project.annotations
    assert [a["kind"] for a in ann] == ["text", "arrow", "rect"]
    assert ann[0]["text"] == "Kritik bölge"
    c.grab()  # paints annotations (hit rects)
    assert 0 in c._annot_rects
    # translate the arrow
    from slipsurface.ui.cad.model import set_points

    win.doc.edit("taşı", lambda p: set_points(p, ("annot", 1), [[13, 14], [26, 4]]))
    assert win.doc.project.annotations[1]["pts"][0] == [13, 14]
    win.doc.undo_stack.undo()
    assert win.doc.project.annotations[1]["pts"][0] == [12.0, 14.0]


def test_material_labels_option(app, win):
    win.load_project(layered_example_project())
    for mode in ("name", "full"):
        win._display_option("material_labels", mode)
        assert win.doc.project.display["material_labels"] == mode
        assert win.a_labels[mode].isChecked()
        win.canvas.grab()
    g = win.display_opts.grids[0]
    _, typ, cb = g._items["material_labels"]
    assert typ == "choice" and cb.currentData() == "full"


def test_interpret_fs_legend_and_notes(app, win, monkeypatch):
    from slipsurface.ui.dialogs import facing_pattern_annot as D

    monkeypatch.setattr(
        D.AnnotationDialog, "exec", lambda self: (self.text.setPlainText("FS notu"), 1)[1]
    )
    p = acads_1a_project()
    p.methods.methods = ["bishop", "janbu_simplified"]
    p.surfaces.effort = "fast"
    win.load_project(p)
    win.compute()
    wait_for(app, lambda: win.last_results is not None and not win.busy)
    iw = win.interpret_windows[-1]
    assert iw.project.display_opt("show_fs_legend")
    iw.canvas.grab()  # paints the FS legend
    c = iw.canvas
    assert c.edit_kinds == {"annot"}
    c.set_tool(T.DrawTool(c, "annot_text"))
    c.command("30,15")
    assert iw.project.annotations[0]["text"] == "FS notu"
    # passed back to the modeler project (saved with the file)
    assert win.doc.project.result_annotations[0]["text"] == "FS notu"
    assert win.doc.project.annotations == []
    iw.doc.undo_stack.undo()
    assert win.doc.project.result_annotations == []
    # model entities are not editable in Interpret
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    c.select_tool()
    c.selection = ("external", 0)
    c.tool.key(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))
    assert iw.project.external


def test_interpret_window_close_and_recompute(app, win):
    """Regression: closing an Interpret window (WA_DeleteOnClose) and computing
    again must not touch the deleted C++ object."""
    p = acads_1a_project()
    p.methods.methods = ["bishop"]
    p.surfaces.effort = "fast"
    win.load_project(p)
    for _ in range(2):
        win.compute()
        wait_for(app, lambda: win.last_results is not None and not win.busy)
        for iw in list(win.interpret_windows):
            iw.close()
        for _ in range(10):
            app.processEvents()
        win.last_results = None
    win.compute()
    wait_for(app, lambda: win.last_results is not None and not win.busy)
    assert len(win.interpret_windows) == 1


# --------------------------------------------------- v0.6: PDF report
def test_pdf_report_from_interpret(app, win, monkeypatch, tmp_path):
    from slipsurface.ui.dialogs import report as R

    out = tmp_path / "rapor.pdf"
    monkeypatch.setattr(R.ReportDialog, "exec", lambda self: 1)
    monkeypatch.setattr(R.QFileDialog, "getSaveFileName", lambda *a, **k: (str(out), ""))
    monkeypatch.setattr(R.QDesktopServices, "openUrl", lambda *a: True)
    monkeypatch.setattr(
        R, "_settings", lambda: R.QSettings(str(tmp_path / "s.ini"), R.QSettings.IniFormat)
    )
    p = acads_1a_project()
    p.methods.methods = ["bishop"]
    p.surfaces.effort = "fast"
    win.load_project(p)
    assert not win.a_report.isEnabled()
    win.compute()
    wait_for(app, lambda: win.last_results is not None and not win.busy)
    assert win.a_report.isEnabled()
    iw = win.interpret_windows[-1]
    assert iw.project.display_opt("show_vertices") is False
    iw.pdf_report()
    assert out.exists() and out.stat().st_size > 50_000
    out.unlink()
    win.pdf_report()
    assert out.exists()
