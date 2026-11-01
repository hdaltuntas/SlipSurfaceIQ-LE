from pathlib import Path

import numpy as np
import pytest

from slipsurface.exchange import export_dxf, import_dxf
from slipsurface.materials.models import PowerLaw, Undrained
from slipsurface.project import Project, EXAMPLES
from tests.models import default_project, layered_example_project
from slipsurface.scripting import run_script


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
    source = (Path(__file__).parent / "data" / "scripted_slope.py").read_text(encoding="utf-8")
    result, output = run_script(source, original)
    assert result.supports and result.loads
    assert "Ready: Scripted layered cut" in output
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
    stress = np.array([0.0, 10.0, 100.0, 1000.0])
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
    result, slices = analyze(
        project.build_geometry(),
        CircularSurface(20, 28, 28),
        project.build_materials(),
        opts=SliceOptions(pore="ru", ru=0.4),
    )
    assert result.ok
    assert np.all(slices.u == 0)


def test_complete_script_example():
    from pathlib import Path

    source = Path(__file__).parent / "data" / "scripted_slope.py"
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
    assert "other strength models" in text and expected in text
    assert "Analysis Results" in text


def test_script_from_file_needs_confirmation_once(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog

    from slipsurface.ui.dialogs.script import ScriptDialog

    QApplication.instance() or QApplication([])

    class Doc:
        project = default_project()
        edits = 0

        def edit(self, label, fn):
            Doc.edits += 1
            fn(self.project)

    path = tmp_path / "foreign.py"
    path.write_text('project.summary.title = "From file"\n', encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    dialog = ScriptDialog(Doc())
    asked = []
    answers = iter([False, True])

    def confirm(source):
        asked.append(source)
        return next(answers)

    dialog.confirm = confirm
    dialog.load()
    dialog.run()  # declined: nothing runs
    assert Doc.edits == 0 and "Not run" in dialog.output.toPlainText()
    dialog.run()  # accepted
    assert Doc.edits == 1 and Doc.project.summary.title == "From file"
    dialog.run()  # already trusted in this dialog: no second question
    assert asked == [str(path), str(path)] and Doc.edits == 2
    dialog.close()


def test_script_dialog_opens_empty_with_tutorial():
    from PySide6.QtWidgets import QApplication, QPushButton

    QApplication.instance() or QApplication([])
    from slipsurface.ui.dialogs import script

    dialog = script.ScriptDialog(type("Doc", (), {"project": default_project()})())
    try:
        assert dialog.editor.toPlainText() == ""
        assert "Tutorial" in dialog.editor.placeholderText()
        labels = [b.text() for b in dialog.findChildren(QPushButton)]
        assert "Tutorial (PDF)" in labels
        assert script.TUTORIAL.is_file()
    finally:
        dialog.close()


def test_scripting_tutorial_is_current_and_its_examples_run(tmp_path):
    import importlib.util

    from pypdf import PdfReader

    from slipsurface import __version__

    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "build_scripting_tutorial", root / "scripts" / "build_scripting_tutorial.py"
    )
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    out = builder.build(tmp_path / "tutorial.pdf")  # runs every example first
    assert len(builder.SNIPPETS) >= 15 and out.stat().st_size > 50_000
    shipped = PdfReader(root / "docs" / "Python_Scripting_Tutorial.pdf")
    first_pages = "\n".join(page.extract_text() for page in shipped.pages[:3])
    # rebuild with: python scripts/build_scripting_tutorial.py
    assert f"Version {__version__}" in first_pages
    text = "\n".join(page.extract_text() for page in shipped.pages)
    for key in ("SupportType", "support_patterns", "water_table", "annotations"):
        assert key in text
