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


# ------------------------------------------------------- updater and DXF hardening
def test_manifest_of_another_release_is_refused():
    import json

    from slipsurface.patch.core import fetch_manifest
    from slipsurface.updates import UpdateCheckError

    class Reply:
        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.data

    def serve(version):
        body = json.dumps({"version": version, "files": {"main.py": "0" * 64}}).encode()
        return lambda request, timeout: Reply(body)

    # the inventory of an older release, replayed under the new release's address
    with pytest.raises(UpdateCheckError, match="is for version 2026.3.0, not 2026.6.0"):
        fetch_manifest("2026.6.0", opener=serve("2026.3.0"), require_signature=False)
    ok = fetch_manifest("v2026.6.0", opener=serve("2026.6.0"), require_signature=False)
    assert ok["files"]


def test_dxf_import_refuses_oversized_drawings(tmp_path, monkeypatch):
    import ezdxf

    from slipsurface import exchange

    def drawing(name, build):
        doc = ezdxf.new("R2010")
        doc.units = ezdxf.units.M
        build(doc.modelspace())
        path = tmp_path / name
        doc.saveas(path)
        return path

    box = [(0, 0), (10, 0), (10, 5), (0, 5)]
    many = drawing(
        "many.dxf",
        lambda msp: [msp.add_line((i, 0), (i, 1), dxfattribs={"layer": "X"}) for i in range(30)],
    )
    monkeypatch.setattr(exchange, "MAX_DXF_ENTITIES", 20)
    with pytest.raises(ValueError, match="entities"):
        exchange.import_dxf(many)

    def curved(msp):
        msp.add_lwpolyline(box, close=True, dxfattribs={"layer": "SS_EXTERNAL"})
        msp.add_arc((5, 2), 1000.0, 0, 180, dxfattribs={"layer": "SS_MATERIAL"})

    monkeypatch.setattr(exchange, "MAX_DXF_VERTICES", 50)
    with pytest.raises(ValueError, match="more than 50 vertices"):
        exchange.import_dxf(drawing("arc.dxf", curved))

    monkeypatch.setattr(exchange, "MAX_DXF_BYTES", 10)
    with pytest.raises(ValueError, match="MB"):
        exchange.import_dxf(many)


def test_report_accepts_markup_characters_in_user_text(tmp_path):
    from slipsurface.analysis import run_analysis
    from slipsurface.report import ReportOptions, build_pdf

    p = acads_1a_project()
    p.methods.methods = ["bishop"]
    p.surfaces.effort = "fast"
    p.materials[0].name = "Clay <b> & 'x' </para>"
    p.summary.title = "A & B <i>"
    p.summary.comments[0] = "<font>&"
    opts = ReportOptions(title="T <&>", checker="<c>", author="<x&>", coordinates=True)
    assert build_pdf(run_analysis(p), tmp_path / "r.pdf", opts) >= 5


# ------------------------------------------------------------------ 2026.6.1
@pytest.mark.parametrize(
    "source",
    [
        "import os",
        "import math, subprocess",
        "from slipsurface.project import os",
        "from slipsurface.exchange import export_dxf",
        "from slipsurface.project import *",
        "open('x', 'w')",
        "eval('1')",
        "project.save('x.json')",
        "x = project.__class__",
        "x = ().__class__.__bases__",
        "__import__('os')",
        "getattr(project, 'save')('x')",
        "class A: pass",
    ],
)
def test_restricted_scripts_refuse_escape_routes(source, tmp_path, monkeypatch):
    from slipsurface.scripting import run_script

    monkeypatch.chdir(tmp_path)
    with pytest.raises((ValueError, NameError, ImportError)):
        run_script(source, acads_1a_project())
    assert not list(tmp_path.iterdir())


def test_restricted_script_changes_the_model_and_trusted_mode_is_python():
    from slipsurface.scripting import run_script

    source = (
        "import math\n"
        "from slipsurface.project import MaterialSpec\n"
        "project.materials.append(MaterialSpec('Fill', c=round(math.sqrt(16), 1)))\n"
        "if __name__ == '__main__':\n    print(len(project.materials))\n"
    )
    project, out = run_script(source, acads_1a_project())
    assert project.materials[-1].c == 4.0 and out.strip() == "2"
    project, out = run_script("import os\nprint(os.sep)", acads_1a_project(), trusted=True)
    assert out.strip() == os.sep


def test_full_access_needs_one_confirmation(app):
    from slipsurface.ui.dialogs.script import ScriptDialog
    from slipsurface.ui.document import Document

    dlg = ScriptDialog(Document(acads_1a_project()))
    try:
        dlg.editor.setPlainText("import os\nproject.summary.title = os.sep")
        dlg.run()
        assert "restricted mode" in dlg.output.toPlainText()
        asked = []
        dlg.confirm_full = lambda: asked.append(1) or len(asked) > 1
        dlg.full_access.setChecked(True)
        dlg.run()  # declined
        assert "Not run" in dlg.output.toPlainText()
        dlg.run()  # accepted
        dlg.run()  # no further question
        assert len(asked) == 2 and dlg.document.project.summary.title == os.sep
    finally:
        dlg.close()


def test_lock_file_pins_every_runtime_requirement_with_hashes():
    import re
    from pathlib import Path

    from slipsurface.patch import core

    root = Path(__file__).resolve().parents[1]
    lock = (root / "requirements.lock").read_text(encoding="utf-8")
    pinned = {m.lower() for m in re.findall(r"^([A-Za-z0-9_.-]+)==", lock, re.M)}
    for line in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name = re.match(r"[A-Za-z0-9_.-]+", line.strip())
        if name and not line.startswith("#"):
            assert name[0].lower() in pinned, name[0]
    blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", lock[lock.index("charset-normalizer==") :])
    assert all("--hash=sha256:" in block for block in blocks)
    assert core.pip_command(root)[3:5] == ["install", "--require-hashes"]
    assert core.is_managed("requirements.lock")
    plan = core.UpdatePlan("a", "b", changed=[core.FileDelta("requirements.lock", "changed")])
    assert core.requirements_changed(plan)


def test_pip_command_without_a_lock_uses_requirements_txt(tmp_path):
    from slipsurface.patch import core

    assert core.pip_command(tmp_path)[-2:] == ["-r", str(tmp_path / "requirements.txt")]


def test_result_cautions_for_reinforced_janbu_and_humped_surfaces(tmp_path):
    from slipsurface.analysis import method_notes, report_text, run_analysis
    from slipsurface.loads import SupportType
    from slipsurface.project import acads_3b_project
    from slipsurface.report import ReportOptions, build_pdf

    p = acads_3b_project()
    p.methods.methods = ["spencer", "janbu_corrected"]
    assert method_notes(run_analysis(p)) == []  # convex, unreinforced: nothing to say

    p.surfaces.user_surface = [[41.85, 27.75], [48, 26.2], [55, 27.5], [63.5, 27], [73.31, 40]]
    p.support_types.append(SupportType())
    p.supports.append({"a": [50.0, 31.25], "b": [60.0, 26.0], "type": "Anchor 1"})
    r = run_analysis(p)
    notes = " ".join(method_notes(r))
    assert "f0 is empirical" in notes and "not convex" in notes
    assert "f0 is empirical" in report_text(r)
    path = tmp_path / "r.pdf"
    build_pdf(r, path, ReportOptions())
    assert "derived for unreinforced slopes" in " ".join(_pdf_text(path).split())


def test_seismic_key_is_drawn_only_with_seismic_coefficients(app):
    from slipsurface.project import acads_1d_project

    def key_pixels(project):
        canvas = CadCanvas()
        canvas.resize(600, 400)
        canvas.set_scene(project, project.build_geometry(), fit=True)
        image = canvas.grab().toImage()
        red = 0
        for x in range(10, 70):
            for y in range(330, 392):
                c = image.pixelColor(x, y)
                red += c.red() > 150 and c.green() < 90 and c.blue() < 90
        return red

    quiet = acads_1a_project()
    shaken = acads_1d_project()
    shaken.seismic.kv = 0.05
    assert key_pixels(quiet) == 0 and key_pixels(shaken) > 20
