import numpy as np
import pytest

from slipsurface.exchange import export_dxf, import_dxf
from slipsurface.materials.models import PowerLaw, Undrained
from slipsurface.project import Project, default_project, layered_example_project, EXAMPLES
from slipsurface.scripting import TEMPLATE, run_script


def test_dxf_roundtrip(tmp_path):
    source = layered_example_project()
    source.tension_crack = [[45, 9], [65, 9]]
    source.surfaces.user_surface = [[15, 0], [30, -2], [50, 12]]
    path = tmp_path / "geometry.dxf"
    export_dxf(source, path)
    result, warnings = import_dxf(path)
    assert result.external == source.external
    assert result.material_boundaries == source.material_boundaries
    assert result.water_table == source.water_table
    assert result.tension_crack == source.tension_crack
    assert result.surfaces.user_surface == source.surfaces.user_surface
    assert warnings


def test_dxf_millimetres_and_ambiguity(tmp_path):
    import ezdxf
    doc = ezdxf.new()
    doc.units = 4
    points = [[x * 1000, y * 1000] for x, y in default_project().external]
    doc.modelspace().add_lwpolyline(points, close=True)
    path = tmp_path / "mm.dxf"
    doc.saveas(path)
    result, _ = import_dxf(path)
    assert result.external == default_project().external
    doc.modelspace().add_lwpolyline(points, close=True)
    doc.saveas(path)
    with pytest.raises(ValueError, match="exactly one"):
        import_dxf(path)


def test_script_transaction_and_complete_model():
    original = default_project()
    before = original.to_dict()
    result, output = run_script(TEMPLATE, original)
    assert result.supports and result.loads
    assert "Project ready" in output
    assert original.to_dict() == before
    with pytest.raises(RuntimeError):
        run_script('project.external.clear()\nraise RuntimeError("failed")', original)
    assert original.to_dict() == before
    with pytest.raises(ValueError):
        run_script('project.materials[0].model = "unknown"', original)


@pytest.mark.parametrize("name", list(EXAMPLES))
def test_examples_serialize_and_build(name):
    project = EXAMPLES[name]()
    project.validate()
    restored = Project.from_dict(project.to_dict())
    restored.build_geometry()
    assert restored.to_dict() == project.to_dict()


def test_strength_envelopes():
    stress = np.array([0., 10., 100., 1000.])
    m = PowerLaw("test", gamma=19, coefficient=0.3, exponent=0.7)
    c, slope = m.strength(stress)
    expected = 30 * (1 + stress / 100) ** 0.7
    np.testing.assert_allclose(c + stress * slope, expected)
    epsilon = 1e-4
    derivative = (30 * (1 + (stress + epsilon) / 100) ** 0.7 - expected) / epsilon
    np.testing.assert_allclose(slope, derivative, rtol=1e-5)
    clay = Undrained("clay", gamma=18, su=42)
    c, slope = clay.strength(stress)
    assert np.all(c == 42) and np.all(slope == 0)
    assert not clay.use_water
    with pytest.raises(ValueError):
        PowerLaw("invalid", gamma=19, exponent=1.2)


def test_live_language_preserves_document_and_dialog_values(monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit
    from slipsurface.ui import i18n
    from slipsurface.ui.modeler import ModelerWindow
    app = QApplication.instance() or QApplication([])
    # Do not change the user's persisted language during tests.
    monkeypatch.setattr(i18n, "settings", lambda: _MemorySettings())
    original_language = i18n._language
    win = ModelerWindow(default_project())
    dialog = QDialog(win)
    layout = QVBoxLayout(dialog)
    label = QLabel("Malzemeler")
    editor = QLineEdit("Malzemeler")
    layout.addWidget(label)
    layout.addWidget(editor)
    win.doc.edit("edit", lambda p: setattr(p.materials[0], "c", 12))
    snapshot = win.doc.project.to_dict()
    undo_count = win.doc.undo_stack.count()
    try:
        win.change_language("en")
        app.processEvents()
        assert win.a_new.text() == "&New"
        assert win.workflow.steps[0] == "Geometry"
        assert label.text() == "Materials"
        assert editor.text() == "Malzemeler"  # User data stays untouched.
        assert win.doc.project.to_dict() == snapshot
        assert win.doc.undo_stack.count() == undo_count
        assert win.doc.dirty
        win.change_language("tr")
        assert win.a_new.text() == "&Yeni"
        assert label.text() == "Malzemeler"
    finally:
        i18n._language = original_language
        win.doc.mark_clean()
        dialog.close()
        win.close()


class _MemorySettings:
    def setValue(self, *args):
        pass


@pytest.mark.parametrize("method", ["bishop", "spencer", "gle", "ordinary"])
@pytest.mark.parametrize("model", ["UD", "PL"])
def test_new_models_against_equivalent_linear_material(method, model):
    from slipsurface.project import acads_1a_project
    from slipsurface.lem import analyze
    from slipsurface.geometry import CircularSurface
    p = acads_1a_project()
    material = p.materials[0]
    if model == "UD":
        material.c, material.phi = 30, 0
        material.use_water = False
        material.su = 30
    else:
        # b=1 reduces exactly to MC: c=a*pa, tan(phi)=a.
        material.coefficient, material.reference_pressure, material.exponent = 0.3, 100, 1
        material.c, material.phi = 30, float(np.degrees(np.arctan(0.3)))
    surface = CircularSurface(20, 28, 28)
    expected, _ = analyze(p.build_geometry(), surface, p.build_materials(), method=method)
    material.model = model
    actual, _ = analyze(p.build_geometry(), surface, p.build_materials(), method=method)
    assert expected.ok and actual.ok
    assert actual.fos == pytest.approx(expected.fos, rel=1e-6)


def test_undrained_ignores_global_ru():
    from slipsurface.project import acads_1a_project
    from slipsurface.geometry import CircularSurface
    from slipsurface.lem import analyze, SliceOptions
    project = acads_1a_project()
    project.materials[0].model = "UD"
    result, slices = analyze(project.build_geometry(), CircularSurface(20, 28, 28),
                             project.build_materials(), opts=SliceOptions(pore="ru", ru=0.4))
    assert result.ok
    assert np.all(slices.u == 0)


def test_complete_script_example():
    from pathlib import Path
    source = Path(__file__).parents[1] / "examples" / "scripted_slope.py"
    project, _ = run_script(source.read_text(encoding="utf-8"), default_project())
    assert project.support_patterns and project.facings and project.tension_crack


@pytest.mark.parametrize("model,expected", [("UD", "su ="), ("PL", "pa =")])
def test_new_models_in_pdf(tmp_path, model, expected):
    from pypdf import PdfReader
    from slipsurface.analysis import run_analysis
    from slipsurface.project import acads_1a_project
    from slipsurface.report import build_pdf
    p = acads_1a_project()
    p.materials[0].model = model
    p.surfaces.surface_type = "user"
    p.surfaces.user_surface = [[20, 0], [60, 10.7]]
    p.methods.methods = ["spencer"]
    results = run_analysis(p)
    assert results.results
    path = tmp_path / "new-model.pdf"
    build_pdf(results, path)
    text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    assert "Additional strength models" in text and expected in text
