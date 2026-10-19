"""Off-screen rendering of model / result drawings for the PDF report.

The same CadCanvas that draws the Modeler and Interpret views paints into a
high-resolution QImage; a frame with metric x / y axes is drawn around it.
"""

from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from slipsurface.ui.cad.canvas import CadCanvas

AXIS_L, AXIS_B, AXIS_T, AXIS_R = 54, 38, 8, 10      # logical px around the drawing


def _nice(x: float) -> float:
    e = 10 ** math.floor(math.log10(max(x, 1e-9)))
    for m in (1, 2, 2.5, 5, 10):
        if m * e >= x:
            return m * e
    return 10 * e


def render_view(project, geometry, results=None, key=None, size=(1500, 760),
                scale: float = 2.2, display: dict | None = None, axes: bool = True) -> bytes:
    """PNG bytes of the drawing. `size` is the logical size of the drawing
    area (px); `scale` the supersampling factor."""
    p = project.copy()
    p.display.update({"show_vertices": False, "show_slope_limits": False,
                      "show_control_points": False, "show_ruler": False})
    if display:
        p.display.update(display)
    w, h = size
    canvas = CadCanvas(editable=False)
    canvas.setAttribute(Qt.WA_DontShowOnScreen, True)
    canvas.resize(w, h)
    canvas.grid_on = bool(p.display.get("show_grid", True))
    canvas.set_scene(p, geometry, results, key)
    canvas.zoom_extents()
    canvas.mouse_pos = None

    tw = w + (AXIS_L + AXIS_R if axes else 0)
    th = h + (AXIS_T + AXIS_B if axes else 0)
    img = QImage(int(tw * scale), int(th * scale), QImage.Format_RGB32)
    img.fill(QColor("white"))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.scale(scale, scale)
    ox, oy = (AXIS_L, AXIS_T) if axes else (0, 0)
    painter.save()
    painter.translate(ox, oy)
    painter.setClipRect(QRectF(0, 0, w, h))
    canvas.render(painter, QPoint(0, 0))
    painter.restore()
    if axes:
        _axes(painter, canvas, ox, oy, w, h)
    painter.end()
    canvas.deleteLater()

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def _axes(p: QPainter, c: CadCanvas, ox: float, oy: float, w: float, h: float) -> None:
    x0, y1 = c.s2w(QPointF(0, 0))
    x1, y0 = c.s2w(QPointF(w, h))
    font = QFont("Sans", 8)
    p.setFont(font)
    fm = QFontMetrics(font)
    ink, tick = QColor(60, 66, 76), QColor(120, 128, 140)
    p.setPen(QPen(tick, 0.8))
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(ox, oy, w, h))
    step_x = _nice((x1 - x0) / 10)
    step_y = _nice((y1 - y0) / 6)
    step = max(step_x, step_y) if abs(step_x - step_y) / max(step_x, step_y) < 0.6 else None
    sx, sy = (step, step) if step else (step_x, step_y)
    for v in np.arange(math.ceil(x0 / sx) * sx, x1 + 1e-9, sx):
        X = ox + c.w2s(v, 0).x()
        p.setPen(QPen(tick, 0.8))
        p.drawLine(QPointF(X, oy + h), QPointF(X, oy + h + 4))
        p.setPen(ink)
        t = f"{v:g}"
        p.drawText(QPointF(X - fm.horizontalAdvance(t) / 2, oy + h + 6 + fm.ascent()), t)
    for v in np.arange(math.ceil(y0 / sy) * sy, y1 + 1e-9, sy):
        Y = oy + c.w2s(0, v).y()
        p.setPen(QPen(tick, 0.8))
        p.drawLine(QPointF(ox - 4, Y), QPointF(ox, Y))
        p.setPen(ink)
        t = f"{v:g}"
        p.drawText(QPointF(ox - 7 - fm.horizontalAdvance(t), Y + fm.ascent() / 2 - 1), t)
    bold = QFont("Sans", 8, QFont.DemiBold)
    p.setFont(bold)
    p.drawText(QPointF(ox + w / 2 - 12, oy + h + 33), "x [m]")
    p.save()
    p.translate(ox - 40, oy + h / 2 + 12)
    p.rotate(-90)
    p.drawText(QPointF(0, 0), "y [m]")
    p.restore()


def report_figures(results, project_for_display=None, method_figures: bool = True,
                   model_figure: bool = True, global_figure: bool = True):
    """All drawings for the report (ReportFigures)."""
    from slipsurface.report import ReportFigures

    disp = project_for_display or results.project
    figs = ReportFigures()
    geom = results.geometry
    if model_figure:
        mp = results.project.copy()
        mp.display.update(disp.display)
        mp.annotations = list(results.project.annotations)
        mp.display.setdefault("material_labels", "full")
        if mp.display.get("material_labels") in (None, "none"):
            mp.display["material_labels"] = "full"
        figs.model = render_view(mp, geom, size=(1080, 520), scale=3.0)
    rp = results.project.copy()
    rp.display.update(disp.display)
    rp.annotations = list(getattr(disp, "annotations", []) if project_for_display is not None
                          else results.project.result_annotations)
    rp.display.update({"show_fs_legend": True})
    gm = results.global_minimum()
    if gm and global_figure:
        figs.global_min = render_view(rp, geom, results, gm[0], size=(1080, 560), scale=3.0)
    if method_figures:
        single = rp.copy()
        single.display.update({"show_all_surfaces": False})
        for k in results.results:
            if gm and k == gm[0] and global_figure:
                continue
            figs.methods[k] = render_view(single, geom, results, k, size=(1080, 520),
                                          scale=2.4)
    return figs
