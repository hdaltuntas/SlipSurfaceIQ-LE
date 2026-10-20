"""PDF report and Slide2-style polygonal non-circular surfaces."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from slipsurface.analysis import run_analysis  # noqa: E402
from slipsurface.geometry import PolylineSurface  # noqa: E402
from slipsurface.optimizer.search import polyline_from_params  # noqa: E402
from slipsurface.project import (  # noqa: E402
    acads_1a_project,
    layered_example_project,
    nailed_shotcrete_project,
)
from slipsurface.report import ReportOptions, build_pdf  # noqa: E402
from slipsurface.report.pdf import _tr_upper  # noqa: E402


@pytest.fixture(scope="module")
def acads_results():
    p = acads_1a_project()
    p.methods.methods = ["bishop", "spencer"]
    p.surfaces.effort = "fast"
    return run_analysis(p)


def _text(path) -> str:
    from pypdf import PdfReader

    return "\n".join(pg.extract_text() for pg in PdfReader(str(path)).pages)


def test_tr_upper():
    assert _tr_upper("Şev stabilite ı") == "ŞEV STABİLİTE I"


def test_pdf_without_figures(tmp_path, acads_results):
    out = tmp_path / "r.pdf"
    n = build_pdf(acads_results, out, ReportOptions(author="Test", target_fs=1.3))
    assert out.exists() and n >= 5
    txt = _text(out)
    assert "İçindekiler" in txt and "Analiz Sonuçları" in txt
    assert f"{acads_results.results['bishop'].fos:.3f}" in txt
    assert "Yetersiz" in txt  # FS ≈ 0.99 < 1.3
    assert f"Sayfa 2 / {n}" in txt
    assert "Dilim Verileri" in txt


def test_pdf_sections_off(tmp_path, acads_results):
    o = ReportOptions(
        toc=False,
        model=False,
        settings=False,
        loads=False,
        slice_table=False,
        coordinates=False,
        target_fs=None,
    )
    out = tmp_path / "r.pdf"
    n = build_pdf(acads_results, out, o)
    txt = _text(out)
    assert "İçindekiler" not in txt and "Dilim Verileri" not in txt
    assert "Hedef FS tanımlanmadı" in txt
    assert n <= 4


def test_pdf_with_figures_supports_and_facing(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from slipsurface.ui.dialogs.report import make_report

    p = nailed_shotcrete_project()
    p.methods.methods = ["bishop"]
    p.surfaces.effort = "fast"
    r = run_analysis(p)
    out = tmp_path / "nail.pdf"
    n = make_report(r, out, ReportOptions(coordinates=True))
    txt = _text(out)
    assert n >= 6
    for s in (
        "Bulon / ankraj paternleri",
        "Kaplama tipleri",
        "Mobilize destek kuvvetleri",
        "Şekil 1",
        "Koordinatlar",
    ):
        assert s in txt, s
    from pypdf import PdfReader

    imgs = sum(len(pg.images) for pg in PdfReader(str(out)).pages)
    assert imgs >= 3  # cover, model, critical surface


def test_render_view_png():
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from slipsurface.ui.report_figures import render_view

    p = acads_1a_project()
    png = render_view(p, p.build_geometry(), size=(400, 200), scale=1.0)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


# ------------------------------------------------- polygonal surfaces
def test_polyline_from_params_convex():
    p = acads_1a_project()
    g = p.build_geometry()
    s = polyline_from_params(g, 10, 50, [0.9, 0.1, 0.8, 0.3])
    assert isinstance(s, PolylineSurface) and len(s.pts) == 6
    assert s.pts[0, 1] == pytest.approx(0.0) and s.pts[-1, 1] == pytest.approx(10.0)
    slopes = np.diff(s.pts[:, 1]) / np.diff(s.pts[:, 0])
    assert np.all(np.diff(slopes) >= -1e-9)  # convex (lower hull)


def test_noncircular_search_is_polygonal_and_beats_circle():
    p = layered_example_project()
    p.methods.methods = ["spencer"]
    p.surfaces.effort = "fast"
    circ = run_analysis(p).results["spencer"].fos
    p.surfaces.surface_type = "noncircular"
    res = run_analysis(p).results["spencer"]
    assert isinstance(res.surface, PolylineSurface)
    assert len(res.surface.pts) >= 6
    assert res.fos <= circ + 1e-3
    assert res.lem.admissible
