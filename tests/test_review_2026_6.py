"""Regressions from the code and interface review: silent rounding in tables,
a dead OK button, marks lost on the dark canvas, damaged project files."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slipsurface.project import MaterialSpec, Project, acads_1a_project  # noqa: E402
from slipsurface.ui import preferences  # noqa: E402
from slipsurface.ui.cad.canvas import CadCanvas  # noqa: E402
from slipsurface.ui.cad.model import set_points  # noqa: E402
from slipsurface.ui.dialogs.loads_supports import DistributedLoadDialog  # noqa: E402
from slipsurface.ui.dialogs.materials import MaterialsDialog  # noqa: E402
from slipsurface.ui.dialogs.misc import CoordinatesDialog  # noqa: E402
from slipsurface.ui.dialogs.project_settings import ProjectSettingsDialog  # noqa: E402
from slipsurface.ui.dialogs.surface_options import SurfaceOptionsDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_coordinate_table_keeps_the_stored_precision(app):
    pts = [[456789.123, 1234.5678], [456801.5, 6.186295]]
    assert CoordinatesDialog("External boundary", pts).points() == pts


def test_material_table_keeps_the_stored_precision(app):
    dlg = MaterialsDialog([MaterialSpec(c=12.345678, phi=31.23456789)])
    dlg.gamma.setValue(21.0)  # any edit stores every table row again
    assert (dlg.mats[0].c, dlg.mats[0].phi) == (12.345678, 31.23456789)


def test_materials_ok_works_after_a_refused_delete(app):
    dlg = MaterialsDialog([MaterialSpec()])
    dlg._delete()
    assert "At least one material" in dlg.error.text()
    dlg._accept()
    assert dlg.result() == MaterialsDialog.Accepted


def test_materials_ok_still_refuses_an_invalid_value(app):
    dlg = MaterialsDialog([MaterialSpec()])
    dlg.table.item(0, 1).setText("abc")
    dlg._accept()
    assert dlg.result() != MaterialsDialog.Accepted and dlg.error.text()


def test_dialog_labels_are_english(app):
    p = acads_1a_project()
    assert ProjectSettingsDialog(p).out_std.text() == "Standard"
    dlg = SurfaceOptionsDialog(p)
    assert dlg.opts.layout().labelForField(dlg.seed).text() == "Random Seed:"


@pytest.mark.parametrize("dark", [False, True])
def test_canvas_ink_contrasts_with_the_canvas_background(app, dark, monkeypatch, tmp_path):
    monkeypatch.setattr(
        preferences,
        "settings",
        lambda: preferences.QSettings(str(tmp_path / "s.ini"), preferences.QSettings.IniFormat),
    )
    preferences.apply_theme(dark)
    try:
        canvas = CadCanvas()
        base = canvas.palette().base().color().lightness()
        assert abs(canvas.ink().lightness() - base) > 120
    finally:
        preferences.apply_theme(False)


def test_distributed_load_needs_a_horizontal_length(app):
    load = {"kind": "distributed", "points": [[5, 0], [5, 0]], "q": [20, 20]}
    dlg = DistributedLoadDialog(load)
    dlg._accept()
    assert dlg.result() != DistributedLoadDialog.Accepted and dlg.error.text()
    dlg.x2.setValue(9.0)
    dlg._accept()
    assert dlg.result() == DistributedLoadDialog.Accepted

    p = acads_1a_project()
    p.loads.append({"kind": "distributed", "points": [[25, 2.5], [35, 7.5]], "q": [20, 20]})
    with pytest.raises(ValueError, match="different x"):
        set_points(p, ("load", 0), [[30, 5], [30, 6]])


def _damaged(change):
    d = acads_1a_project().to_dict()
    change(d)
    return d


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d.update(loads=[{"points": [[0, 0], [1, 1]]}]), "Load 1"),
        (lambda d: d.update(loads=[{"kind": "line", "point": [1]}]), "Load 1"),
        (lambda d: d.update(support_patterns=[{"type": "a"}]), "Bolt pattern 1"),
        (lambda d: d.update(facings=[{"type": "a"}]), "Facing 1"),
        (lambda d: d.update(annotations=[{"kind": "text"}]), "Note 1"),
        (lambda d: d.update(result_annotations=[{"kind": "x", "pts": []}]), "Result note 1"),
        (lambda d: d["geometry"].update(assignments=[{"point": [1, 1]}]), "incomplete"),
        (lambda d: d["surfaces"].update(left_range="abc"), "Left slip limit"),
        (lambda d: d["surfaces"].update(user_surface=[[1]]), "User surface"),
        (lambda d: d["settings"]["methods"].update(n_slices="30"), "n_slices"),
        (lambda d: d["settings"]["seismic"].update(both_vertical="yes"), "both_vertical"),
        (lambda d: d["materials"][0].update(model="XX"), "unknown material model"),
        (lambda d: d.update(supports=[{"a": [1, 1], "type": "a"}]), "incomplete"),
    ],
)
def test_damaged_project_entries_are_refused_with_the_entry_named(change, message):
    with pytest.raises(ValueError, match=message):
        Project.from_dict(_damaged(change))


def test_stored_display_options_of_the_wrong_type_fall_back_to_defaults():
    d = _damaged(lambda d: d.update(display={"line_width": "x", "show_grid": 1, "label_size": 11}))
    p = Project.from_dict(d)
    assert p.display["line_width"] == 2 and p.display["show_grid"] is True
    assert p.display["label_size"] == 11


def test_whole_numbers_stored_as_floats_and_missing_values_still_load():
    d = _damaged(lambda d: d["settings"]["methods"].update(n_slices=30.0, tolerance=1))
    d["summary"]["author"] = None
    p = Project.from_dict(d)
    assert p.methods.n_slices == 30 and isinstance(p.methods.n_slices, int)
    assert p.summary.author == ""
    p.build_geometry()


@pytest.mark.parametrize("path", sorted(os.listdir("examples")))
def test_bundled_examples_pass_the_structure_checks(path):
    Project.load(os.path.join("examples", path)).build_geometry()


# ------------------------------------------------- second review pass (2026.6.0)
def _pdf_text(path) -> str:
    from pypdf import PdfReader

    return "\n".join(page.extract_text() for page in PdfReader(str(path)).pages)


@pytest.fixture(scope="module")
def fixed_surface_results():
    from slipsurface.analysis import run_analysis
    from slipsurface.project import acads_3b_project

    p = acads_3b_project()
    p.methods.methods = ["bishop", "spencer"]  # Bishop cannot solve a polyline
    p.general.failure_direction = "auto"
    p.advanced.m_alpha_min = 0.15
    return run_analysis(p)


def test_report_names_appendix_error_and_settings_in_full(fixed_surface_results, tmp_path):
    from slipsurface.report import ReportOptions, build_pdf

    path = tmp_path / "r.pdf"
    build_pdf(fixed_surface_results, path, ReportOptions(coordinates=True))
    text = _pdf_text(path)
    assert "Appendix A" in text and "Appendix B" in text and "Ek A" not in text
    assert "Bishop is valid for circular surfaces only." in text  # not cut at 40 characters
    assert "analysed without a search" in text and "None (the surface is given)" in text
    assert "Automatic" in text and "mα < 0.15" in text


def test_report_keeps_material_tables_without_the_model_section(fixed_surface_results, tmp_path):
    from slipsurface.report import ReportOptions, build_pdf

    path = tmp_path / "r.pdf"
    build_pdf(fixed_surface_results, path, ReportOptions(model=False, toc=False))
    text = _pdf_text(path)
    assert "Material parameters (Mohr-Coulomb)" in text
    assert "Model and Geometry" not in text


def test_info_viewer_text_names_the_automatic_direction(fixed_surface_results):
    from slipsurface.analysis import report_text

    assert "Failure direction  : Automatic" in report_text(fixed_surface_results)


def test_settings_dialog_keeps_values_it_cannot_show_exactly(app):
    p = acads_1a_project()
    p.general.failure_direction = "auto"
    p.methods.n_slices = 3
    p.methods.max_iter = 2
    p.methods.tolerance = 1.23456789e-7
    p.groundwater.gamma_w = 62.4
    p.groundwater.crack_water = 0.3
    p.seismic.kh = 0.123456789
    p.advanced.m_alpha_min = 0.01
    dlg = ProjectSettingsDialog(p)
    assert dlg.auto_dir.isChecked()
    got = dlg.collect()
    for part in ("general", "methods", "groundwater", "seismic", "advanced"):
        assert getattr(got, part) == getattr(p, part), part
    dlg.kh.setValue(0.2)  # an edited value is taken from the box
    assert dlg.collect().seismic.kh == 0.2


def test_load_and_support_dialogs_keep_untouched_values_exact(app):
    from slipsurface.ui.dialogs.facing_pattern_annot import PatternDialog
    from slipsurface.ui.dialogs.loads_supports import LineLoadDialog, SupportEditDialog

    load = {"kind": "distributed", "points": [[1.23456, 0], [9.87654, 0]], "q": [20.12345, 30]}
    dlg = DistributedLoadDialog(load)
    dlg.q2.setValue(35.0)
    out = {"points": [[0, 0], [0, 0]]}
    dlg.apply_to(out)
    assert out["points"] == [[1.23456, 0], [9.87654, 0]] and out["q"] == [20.12345, 35.0]

    line = {"kind": "line", "point": [3.14159, 2], "magnitude": 12.34567, "angle": 271.123}
    out = dict(line)
    LineLoadDialog(line).apply_to(out)
    assert out == line

    sp = {"a": [1.00049, 2.5], "b": [7.12349, -1.00001], "type": "A"}
    out = dict(sp)
    SupportEditDialog(sp, ["A"]).apply_to(out)
    assert out == sp

    pt = {"p1": [2.00049, 0], "p2": [9, 0], "spacing": 1.2345, "length": 6.0, "type": "A"}
    out = dict(pt)
    PatternDialog(pt, ["A"]).apply_to(out)
    assert out["p1"][0] == 2.00049 and out["spacing"] == 1.2345


def test_surface_options_keep_the_given_circle_exact(app):
    p = acads_1a_project()
    p.surfaces.surface_type = "user"
    p.surfaces.user_circle = [30.12345, 25.5, 22.00049]
    p.surfaces.seed = 123456
    dlg = SurfaceOptionsDialog(p)
    q = p.copy()
    dlg.apply_to(q)
    assert q.surfaces.user_circle == p.surfaces.user_circle and q.surfaces.seed == 123456


def test_failed_update_install_is_not_reported_as_a_failed_check(app, monkeypatch):
    from PySide6.QtWidgets import QWidget

    from slipsurface.ui import updates

    parent = QWidget()
    checker = updates.UpdateChecker(parent)
    shown = []
    monkeypatch.setattr(checker, "_show", lambda kind, title, text: shown.append(text))
    checker._busy = True
    checker._on_apply_failed("hash mismatch for main.py")
    assert not checker.busy
    assert "could not be installed" in shown[0] and "check for updates" not in shown[0]


def test_update_download_url_is_quoted():
    from slipsurface.patch import core

    urls = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"x"

    def opener(request, timeout):
        urls.append(request.full_url)
        return Reply()

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        core.download_file(
            "examples/my model ü.slp.json", "2026.6.0", Path(tmp) / "f", opener=opener
        )
    assert urls[0].endswith("/v2026.6.0/examples/my%20model%20%C3%BC.slp.json")


def test_dxf_import_asks_before_replacing_a_model(app, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from slipsurface.exchange import export_dxf
    from slipsurface.ui.modeler import ModelerWindow

    dxf = tmp_path / "m.dxf"
    export_dxf(acads_1a_project(), dxf)
    win = ModelerWindow(acads_1a_project())
    try:
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(dxf), ""))
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
        asked = []
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a, **k: asked.append(1) or QMessageBox.No
        )
        win.doc.edit("c", lambda p: setattr(p.materials[0], "c", 7.0))
        win.import_dxf()
        assert asked and win.doc.project.materials[0].c == 7.0  # kept
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        win.import_dxf()
        assert win.doc.project.materials[0].c != 7.0  # replaced by the import
    finally:
        win.doc.mark_clean()
        win.close()
