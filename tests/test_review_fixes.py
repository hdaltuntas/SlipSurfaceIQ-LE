"""Regressions for geometry, ponded seismic mass, Janbu and report metadata."""

from dataclasses import replace

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader
from shapely.geometry import LineString, Polygon

from slipsurface.analysis import report_text
from slipsurface.geometry import CircularSurface
from slipsurface.geometry.builder import boundary_geometry
from slipsurface.lem import SliceOptions, analyze, make_slices
from slipsurface.lem.gle import janbu_correction_factor
from slipsurface.materials import MohrCoulomb, Shansep, Undrained
from slipsurface.optimizer import SearchResult
from tests.models import default_project


@pytest.mark.parametrize(
    "external",
    [
        [[0, -10], [40, -10], [40, 10], [20, 10], [20, 0], [0, 0]],
        [[0, -10], [40, -10], [40, 0], [20, 0], [20, 10], [0, 10]],
        [[0, -10], [40, -10], [40, 10], [15, 10], [20, 0], [0, 0]],
    ],
)
def test_unsupported_faces_are_rejected_instead_of_interpolated(external):
    with pytest.raises(ValueError, match="Vertical slope faces and overhangs"):
        boundary_geometry(external)


def test_continuous_profile_preserves_polygon_top_with_vertical_model_sides():
    p = default_project()
    g = p.build_geometry()
    polygon = Polygon(p.external)
    for x in (1, 14, 15, 25, 35, 54):
        actual = LineString([(x, -11), (x, 11)]).intersection(polygon).bounds[3]
        assert g.ground_y(x) == pytest.approx(actual)


@pytest.mark.parametrize("method", ["bishop", "spencer", "gle"])
@pytest.mark.parametrize("water_level", [6.0, 12.0])
def test_ponded_seismic_mass_matches_explicit_water_forces(method, water_level):
    from slipsurface.lem import SOLVERS

    p = default_project()
    p.materials[0].gamma = 18.0
    p.materials[0].c = 40.0
    p.water_table = [[0, water_level], [55, water_level]]
    surf = CircularSurface(15, 28, 28)
    s = make_slices(
        p.build_geometry(),
        surf,
        p.build_materials(),
        opts=SliceOptions(n_slices=50, kh=0.15, kv=0.05),
    )
    # Independent representation: keep only soil as mass and apply the
    # water's vertical/seismic forces at the water column's own centroid.
    soil_weight = 18.0 * (s.y_top - s.y_base) * s.b
    water_weight = 9.81 * np.maximum(water_level - s.y_top, 0.0) * s.b
    soil_cg = 0.5 * (s.y_top + s.y_base)
    water_cg = 0.5 * (water_level + s.y_top)
    qx = s.direction * s.kh * water_weight
    qy = -(1 - s.kv) * water_weight
    separate = replace(
        s, W=soil_weight, y_cg=soil_cg, Qx_a=qx, Qy_a=qy, M_a=s.xm * qy - water_cg * qx
    )
    expected = SOLVERS[method](separate)
    actual = SOLVERS[method](s)
    assert actual.ok and expected.ok
    assert actual.fos == pytest.approx(expected.fos, rel=1e-7)
    np.testing.assert_allclose(
        s.W * s.y_cg, soil_weight * soil_cg + water_weight * water_cg, rtol=1e-12
    )


@pytest.mark.parametrize(
    "material",
    [
        Undrained("Soil 1", gamma=18, su=35),
        Shansep("Soil 1", gamma=18, s_ratio=0.3),
    ],
)
def test_janbu_total_stress_models_use_cohesive_correction(material):
    p = default_project()
    g = p.build_geometry()
    surf = CircularSurface(15, 28, 28)
    slices = make_slices(g, surf, {"Soil 1": material})
    points = slices.base_points()
    chord = points[-1] - points[0]
    length = np.linalg.norm(chord)
    normal = np.array([-chord[1], chord[0]]) / length
    ratio = np.max(np.abs((points - points[0]) @ normal)) / length
    expected_factor = 1 + 0.69 * (ratio - 1.4 * ratio**2)
    assert janbu_correction_factor(slices) == pytest.approx(expected_factor)
    simple, _ = analyze(g, surf, {"Soil 1": material}, method="janbu_simplified")
    corrected, _ = analyze(g, surf, {"Soil 1": material}, method="janbu_corrected")
    assert simple.ok and corrected.ok
    assert corrected.fos == pytest.approx(simple.fos * expected_factor)
    if isinstance(material, Undrained):
        equivalent = MohrCoulomb("Soil 1", gamma=18, c=35, phi=0)
        mc, _ = analyze(g, surf, {"Soil 1": equivalent}, method="janbu_corrected")
        assert mc.ok and corrected.fos == pytest.approx(mc.fos, rel=1e-9)


@pytest.fixture
def summary_window():
    from slipsurface.analysis import AnalysisResults
    from slipsurface.ui.modeler import ModelerWindow

    app = QApplication.instance() or QApplication([])
    p = default_project()
    p.summary.title, p.summary.author = "Original title", "Original author"
    w = ModelerWindow(p)
    surf = CircularSurface(15, 28, 28)
    lem, slices = analyze(w.doc.geometry, surf, p.build_materials())
    assert lem.ok
    w.last_results = AnalysisResults(
        p.copy(), w.doc.geometry, results={"bishop": SearchResult(surf, lem.fos, lem, slices, 1)}
    )
    yield app, w
    w.doc.mark_clean()
    w.close()
    app.processEvents()


def test_summary_edits_and_undo_refresh_both_report_paths(summary_window, tmp_path):
    from slipsurface.report import ReportOptions, build_pdf
    from slipsurface.ui.dialogs.report import ReportDialog

    app, w = summary_window
    w.interpret()
    app.processEvents()
    iw = w.interpret_windows[-1]
    results = w.last_results
    fos = results.results["bishop"].fos

    def edit(p):
        p.summary.title, p.summary.author = "Updated title", "Updated author"

    w.doc.edit("summary", edit)
    for action, title, author in (
        (lambda: None, "Updated title", "Updated author"),
        (w.doc.undo_stack.undo, "Original title", "Original author"),
        (w.doc.undo_stack.redo, "Updated title", "Updated author"),
    ):
        action()
        assert w.last_results is results and results.results["bishop"].fos == fos
        assert iw.isVisible() and iw.project.summary.title == title
        assert title in iw.windowTitle()
        assert title in report_text(results) and author in report_text(results)
        for project in (results.project, iw.results.project):
            dialog = ReportDialog(project)
            assert dialog.project.text() == title and dialog.author.text() == author
            dialog.close()
    out = tmp_path / "summary.pdf"
    build_pdf(
        results,
        out,
        ReportOptions(
            toc=False,
            model=False,
            method_figures=False,
            global_figure=False,
            slice_table=False,
            coordinates=False,
        ),
    )
    text = "\n".join(page.extract_text() for page in PdfReader(out).pages)
    assert "Updated title" in text and "Updated author" in text


def test_summary_changed_during_analysis_is_used_on_completion(summary_window, monkeypatch):
    _, w = summary_window
    results = w.last_results
    w.last_results = None
    w.doc.edit("summary", lambda p: setattr(p.summary, "title", "Edited while solving"))
    monkeypatch.setattr(w, "interpret", lambda: None)
    w._on_finished(results)
    assert w.last_results is results
    assert results.project.summary.title == "Edited while solving"
