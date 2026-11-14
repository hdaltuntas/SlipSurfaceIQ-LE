"""Stage LE-4 regressions: Interpret convergence & slice/candidate inspection,
PDF report traceability, project v1->v3/v4 migration & DXF resilience, and
dark-mode contrast, accessibility & in-use type deletion guards."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ezdxf  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from PySide6.QtCore import QEvent, QPoint, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slipsurface.analysis import AnalysisResults, report_text  # noqa: E402
from slipsurface.exchange import import_dxf  # noqa: E402
from slipsurface.geometry import CircularSurface  # noqa: E402
from slipsurface.lem import analyze  # noqa: E402
from slipsurface.loads import FacingType, SupportType  # noqa: E402
from slipsurface.optimizer import SearchResult  # noqa: E402
from slipsurface.project import Project, acads_1a_project  # noqa: E402
from slipsurface.report import ReportOptions, build_pdf  # noqa: E402
from slipsurface.ui import preferences  # noqa: E402
from slipsurface.ui.cad.canvas import CadCanvas  # noqa: E402
from slipsurface.ui.dialogs.facing_pattern_annot import FacingTypesDialog  # noqa: E402
from slipsurface.ui.dialogs.loads_supports import SupportTypesDialog  # noqa: E402
from slipsurface.ui.dialogs.misc import SliceDataDialog, slice_rows  # noqa: E402
from slipsurface.ui.dialogs.report import make_report  # noqa: E402
from slipsurface.ui.docks import DisplayOptions  # noqa: E402
from slipsurface.ui.icons import icon  # noqa: E402
from slipsurface.ui.interpret import InterpretWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _fast_multi_results() -> AnalysisResults:
    p = acads_1a_project()
    p.methods.methods = ["bishop", "spencer", "janbu_corrected"]
    p.methods.interslice = "clipped-sine"
    p.methods.f_start = 0.25
    p.methods.f_end = 0.75
    surf = CircularSurface(20.0, 28.0, 28.0)
    cand = CircularSurface(21.0, 29.0, 29.0)
    geom = p.build_geometry()
    mats = p.build_materials()
    opts = p.slice_options()
    kw = p.solver_kw()
    out = AnalysisResults(p.copy(), geom, elapsed=0.2, finished="2026-11-14 12:00:00")
    for m in p.methods.methods:
        lem, s = analyze(geom, surf, mats, method=m, opts=opts, **kw)
        lem_c, _ = analyze(geom, cand, mats, method=m, opts=opts, **kw)
        assert lem.ok and s is not None
        out.results[m] = SearchResult(
            surf,
            lem.fos,
            lem,
            s,
            2,
            [(lem.fos, surf), (lem_c.fos, cand)],
            "converged",
            m,
        )
    return out


def _pdf_text(path: Path) -> str:
    return "\n".join(pg.extract_text() for pg in PdfReader(str(path)).pages)


# ----------------------------------------------------------------- 1. Interpret
def test_interpret_convergence_slice_forces_navigation_and_candidate_pick(app):
    res = _fast_multi_results()
    txt = report_text(res)
    # Clipped-sine parameters and solver convergence / residual traceability
    assert "0.25" in txt and "0.75" in txt
    assert "mα" in txt and "f0" in txt
    assert "|ΔF|" in txt or "residual" in txt.lower()

    # Slice rows include solved base & interslice forces (and handle Bishop with no E/X)
    bi_rows = dict(slice_rows(res.results["bishop"], 5))
    assert any("N′" in k or "N'" in k for k in bi_rows)
    assert not any("EL / ER" in k for k in bi_rows)
    sp_res = res.results["spencer"]
    rows_dict = dict(slice_rows(sp_res, 5))
    assert any("N′" in k or "N'" in k for k in rows_dict)
    assert any("Smob" in k for k in rows_dict)
    assert any("EL / ER" in k for k in rows_dict)
    assert any("XL / XR" in k for k in rows_dict)

    iw = InterpretWindow(res)
    iw.resize(1200, 800)
    iw.show()
    try:
        for _ in range(3):
            app.processEvents()
        # Status bar exposes solver iterations and m_alpha_min
        msg = iw.status.currentMessage()
        assert "it =" in msg or "iter" in msg.lower()
        assert "mα" in msg

        # View/query tools are checkable and synced; Data menu has no duplicate Slice Data
        assert iw.a_select.isCheckable() and iw.a_pan.isCheckable()
        assert iw.a_zoom_win.isCheckable() and iw.a_measure.isCheckable()
        iw.a_pan.trigger()
        assert iw.a_pan.isChecked() and not iw.a_select.isChecked()
        iw.a_select.trigger()
        assert iw.a_select.isChecked() and not iw.a_pan.isChecked()
        data_menu = next(a.menu() for a in iw.menuBar().actions() if a.text() == "&Data")
        assert iw.a_slice not in data_menu.actions()

        # SliceDataDialog Previous / Next navigation updates canvas.highlight_slice
        dlg = SliceDataDialog(sp_res, 5, "Spencer", iw)
        assert iw.canvas.highlight_slice == 5
        dlg.next_btn.click()
        assert dlg.index == 6 and iw.canvas.highlight_slice == 6
        assert dict(slice_rows(sp_res, 6))["Slice no."] in dlg.table.item(0, 1).text()
        dlg.prev_btn.click()
        assert dlg.index == 5 and iw.canvas.highlight_slice == 5
        dlg.close()

        # Standalone Top-surfaces FS scale bar when show_all_surfaces=True & show_legend=False
        iw._display_option("show_all_surfaces", True)
        iw._display_option("show_legend", False)
        iw._display_option("show_fs_legend", False)
        iw.canvas.zoom_extents()
        iw.canvas.grab()
        assert len(iw.canvas._legend_rects) == 1
        iw._display_option("show_fs_legend", True)
        iw.canvas.grab()
        assert len(iw.canvas._legend_rects) == 2
        assert not iw.canvas._legend_rects[0].intersects(iw.canvas._legend_rects[1])

        # Clicking a non-critical candidate surface reports its candidate FS in status bar
        cand_fos, cand_surf = sp_res.top[1]
        pts = cand_surf.points(21.0, 42.0, 40)
        mid = pts[len(pts) // 2]
        sp = iw.canvas.w2s(float(mid[0]), float(mid[1]))
        ev = QMouseEvent(
            QEvent.MouseButtonPress,
            sp,
            iw.canvas.mapToGlobal(QPoint(int(sp.x()), int(sp.y()))),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        iw.canvas.mousePressEvent(ev)
        assert f"{cand_fos:.3f}" in iw.status.currentMessage()
    finally:
        iw.close()
        app.processEvents()


# --------------------------------------------------------------- 2. PDF Report
def test_pdf_report_global_figure_false_omits_cover_and_section_images(app, tmp_path):
    res = _fast_multi_results()
    out = tmp_path / "no_figs.pdf"
    opts = ReportOptions(
        toc=False,
        model=False,
        global_figure=False,
        method_figures=False,
        slice_table=False,
    )
    make_report(res, out, opts)
    reader = PdfReader(str(out))
    imgs = sum(len(pg.images) for pg in reader.pages)
    assert imgs == 0


def test_pdf_report_traceability_maximum_slices_and_user_coordinates(tmp_path):
    res = _fast_multi_results()
    res.project.general.data_output = "maximum"
    res.project.surfaces.user_surface = [[20.0, 0.0], [30.0, -2.0], [41.5, 10.0]]
    out = tmp_path / "full_trace.pdf"
    build_pdf(res, out, ReportOptions(toc=False, coordinates=True))
    txt = _pdf_text(out)
    # Clipped-sine f_start / f_end
    assert "0.25" in txt and "0.75" in txt
    # Solver convergence & equilibrium residuals table
    assert "Iterations" in txt and "mα" in txt
    # Solved slice forces N' and S_mob + all methods output when data_output == "maximum"
    assert "Smob" in txt or "S_mob" in txt
    assert "Slice data (Bishop simplified)" in txt
    assert "Slice data (Spencer)" in txt
    assert "Slice data (Janbu corrected)" in txt
    # User-defined slip surface in Coordinates appendix
    assert "User-defined slip surface" in txt


# ------------------------------------------------------ 3. Migration & DXF I/O
def test_v1_migration_preserves_analysis_and_dry_water_settings():
    data_path = Path(__file__).parent / "data" / "v1_layered.slp.json"
    raw = json.loads(data_path.read_text(encoding="utf-8"))
    raw["water"]["enabled"] = False
    raw["analysis"]["surface_type"] = "noncircular"
    raw["analysis"]["n_ctrl"] = 6
    raw["analysis"]["seed"] = 42
    raw["analysis"]["exit_range"] = [5.0, 22.0]
    raw["analysis"]["entry_range"] = [42.0, 68.0]
    p = Project.from_dict(raw)
    assert p.to_dict()["version"] == 3
    assert p.groundwater.method == "none"
    assert p.water_table is None
    assert p.surfaces.surface_type == "noncircular"
    assert p.surfaces.n_ctrl == 6
    assert p.surfaces.seed == 42
    assert p.surfaces.left_range == [5.0, 22.0]
    assert p.surfaces.right_range == [42.0, 68.0]


def test_dxf_import_units_z_noise_duplicates_endpoint_closure_and_reverse(tmp_path):
    ext = [[0.0, -5.0], [60.0, -5.0], [60.0, 10.0], [40.0, 10.0], [20.0, 0.0], [0.0, 0.0]]

    # 1) US Survey Feet ($INSUNITS = 21) and unknown unit code (99 -> warning, no crash)
    us_ft = 1200.0 / 3937.0
    doc21 = ezdxf.new("R2010")
    doc21.header["$INSUNITS"] = 21
    doc21.modelspace().add_lwpolyline(
        [(x / us_ft, y / us_ft) for x, y in ext],
        close=True,
        dxfattribs={"layer": "SS_EXTERNAL"},
    )
    p21 = tmp_path / "us_survey_ft.dxf"
    doc21.saveas(p21)
    proj21, _ = import_dxf(p21)
    np.testing.assert_allclose(proj21.external, ext, atol=1e-5)

    doc99 = ezdxf.new("R2010")
    doc99.header["$INSUNITS"] = 99
    doc99.modelspace().add_lwpolyline(ext, close=True, dxfattribs={"layer": "SS_EXTERNAL"})
    p99 = tmp_path / "unknown_units.dxf"
    doc99.saveas(p99)
    proj99, warn99 = import_dxf(p99)
    assert any("unit" in w.lower() for w in warn99)
    np.testing.assert_allclose(proj99.external, ext, atol=1e-6)

    # 2) Sub-micrometre Z noise in mm drawing accepted; real 3D Z rejected with exact guide error
    doc_mm = ezdxf.new("R2010")
    doc_mm.units = ezdxf.units.MM
    msp = doc_mm.modelspace()
    # Endpoint-closed LWPOLYLINE (close=False) + consecutive duplicate vertex + tiny Z elevation
    dup_ext_mm = [
        (0.0, -5000.0),
        (60000.0, -5000.0),
        (60000.0, -5000.0),  # consecutive duplicate
        (60000.0, 10000.0),
        (40000.0, 10000.0),
        (20000.0, 0.0),
        (0.0, 0.0),
        (0.0, -5000.0),  # endpoint-closed without DXF closed flag
    ]
    pl = msp.add_lwpolyline(dup_ext_mm, close=False, dxfattribs={"layer": "SS_EXTERNAL"})
    pl.dxf.elevation = 1e-4  # 1e-4 mm = 1e-7 m <= 1e-6 m -> planar noise
    # Right-to-left water table auto-reversed with warning
    msp.add_lwpolyline(
        [(60000.0, 6000.0), (40000.0, 6000.0), (20000.0, -1000.0), (0.0, -1000.0)],
        dxfattribs={"layer": "SS_WATER"},
    )
    p_mm = tmp_path / "noisy_mm.dxf"
    doc_mm.saveas(p_mm)
    proj_mm, warn_mm = import_dxf(p_mm)
    assert len(proj_mm.external) == 6
    np.testing.assert_allclose(proj_mm.external, ext, atol=1e-6)
    assert proj_mm.water_table == [[0.0, -1.0], [20.0, -1.0], [40.0, 6.0], [60.0, 6.0]]
    assert any("reversed" in w.lower() for w in warn_mm)

    # Genuine Z != 0 (10 mm = 0.01 m) still raises exact guide message
    pl.dxf.elevation = 10.0
    doc_mm.saveas(p_mm)
    with pytest.raises(ValueError, match="Only planar XY geometry at Z=0 is supported."):
        import_dxf(p_mm)


# ------------------------------------ 4. Dark Mode, Accessibility & Type Guards
def test_dark_mode_icons_property_grid_warning_and_unboxed_text(app, monkeypatch, tmp_path):
    palette, font, stylesheet = app.palette(), app.font(), app.styleSheet()
    store = QSettings(str(tmp_path / "theme.ini"), QSettings.IniFormat)
    monkeypatch.setattr(preferences, "settings", lambda: store)
    try:
        preferences.apply_theme(False)
        pm_light = icon("external").pixmap(32, 32).toImage()
        preferences.apply_theme(True)
        pm_dark = icon("external").pixmap(32, 32).toImage()
        # Dark-mode custom vector icon adapts its dark ink strokes
        diffs = sum(
            pm_light.pixelColor(x, y) != pm_dark.pixelColor(x, y)
            for x in range(32)
            for y in range(32)
        )
        assert diffs > 10

        # PropertyGrid category headers contrast with dark background
        opts = DisplayOptions(interpret=True)
        try:
            top_item = opts.grids[0].topLevelItem(0)
            bg_l = top_item.background(0).color().lightness()
            fg_l = top_item.foreground(0).color().lightness()
            assert bg_l < 100 and fg_l > 180
        finally:
            opts.close()

        # InterpretWindow warning banner updates for dark mode
        res = _fast_multi_results()
        res.errors["gle"] = "Did not converge."
        iw = InterpretWindow(res)
        try:
            assert "#fff4d6" not in iw.result_warning.styleSheet()
        finally:
            iw.close()
            app.processEvents()

        # Unboxed dark text annotation contrasts on dark canvas
        p = acads_1a_project()
        p.annotations.append(
            {
                "kind": "text",
                "pts": [[25.0, 5.0]],
                "text": "Crest",
                "color": "#111111",
                "box": False,
                "size": 12,
            }
        )
        c = CadCanvas()
        try:
            c.resize(500, 350)
            c.set_scene(p, p.build_geometry(), fit=True)
            img = c.grab().toImage()
            rect = c._annot_rects[0]
            base_l = c.palette().color(QPalette.Base).lightness()
            bright = sum(
                img.pixelColor(x, y).lightness() > base_l + 80
                for x in range(max(0, int(rect.left())), min(img.width(), int(rect.right())))
                for y in range(max(0, int(rect.top())), min(img.height(), int(rect.bottom())))
            )
            assert bright > 5
        finally:
            c.close()
    finally:
        app.setPalette(palette)
        app.setFont(font)
        app.setStyleSheet(stylesheet)
        app.processEvents()


def test_canvas_accessibility_arrow_pan_and_in_use_type_deletion_guards(app):
    c = CadCanvas()
    try:
        c.resize(400, 300)
        assert c.accessibleName()
        assert c.accessibleDescription()
        cx0, cy0 = c.cx, c.cy
        c.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier))
        assert c.cx > cx0
        c.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier))
        assert c.cy > cy0
    finally:
        c.close()

    # SupportTypesDialog refuses deleting an in-use support type (even after rename)
    s_dlg = SupportTypesDialog(
        [SupportType("Bolt A"), SupportType("Bolt B")],
        in_use={"Bolt A"},
    )
    try:
        s_dlg.list.setCurrentRow(0)
        s_dlg.name.setText("Bolt A Renamed")
        s_dlg._rename("Bolt A Renamed")
        s_dlg._delete()
        assert len(s_dlg.types) == 2
        assert "assigned" in s_dlg.error.text().lower() or "in use" in s_dlg.error.text().lower()
        # Unused type can still be deleted
        s_dlg.list.setCurrentRow(1)
        s_dlg._delete()
        assert len(s_dlg.types) == 1
    finally:
        s_dlg.close()

    # FacingTypesDialog refuses deleting an in-use facing type
    f_dlg = FacingTypesDialog(
        [FacingType("Shotcrete A"), FacingType("Shotcrete B")],
        in_use={"Shotcrete A"},
    )
    try:
        f_dlg.list.setCurrentRow(0)
        f_dlg._delete()
        assert len(f_dlg.types) == 2
        assert "assigned" in f_dlg.error.text().lower() or "in use" in f_dlg.error.text().lower()
    finally:
        f_dlg.close()
    app.processEvents()
