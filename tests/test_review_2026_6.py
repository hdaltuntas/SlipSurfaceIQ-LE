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
