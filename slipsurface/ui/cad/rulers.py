"""Rulers along the CAD canvas (left: y, bottom: x), Slide2 style."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from slipsurface.ui.cad.canvas import CadCanvas, nice_step

THICK = 26


class Ruler(QWidget):
    def __init__(self, canvas: CadCanvas, vertical: bool, parent=None) -> None:
        super().__init__(parent)
        self.c = canvas
        self.vertical = vertical
        self.cursor = None
        if vertical:
            self.setFixedWidth(THICK)
        else:
            self.setFixedHeight(THICK)
        canvas.view_changed.connect(self.update)
        canvas.mouse_world.connect(self._on_mouse)

    def _on_mouse(self, x, y) -> None:
        self.cursor = y if self.vertical else x
        self.update()

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        p.setPen(QPen(QColor("#9aa3ad"), 1))
        if self.vertical:
            p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        else:
            p.drawLine(0, 0, self.width(), 0)
        c = self.c
        if c.scale <= 0:
            return
        f = QFont("Source Sans 3", 7)
        p.setFont(f)
        fm = QFontMetrics(f)
        major = nice_step(70 / c.scale)
        minor = major / 10 if major / 10 * c.scale >= 5 else major / 5
        if self.vertical:
            # canvas y (world) -> ruler y: same pixel rows (ruler is aligned with canvas)
            lo, hi = c.s2w(QPointF(0, c.height()))[1], c.s2w(QPointF(0, 0))[1]
        else:
            lo, hi = c.s2w(QPointF(0, 0))[0], c.s2w(QPointF(c.width(), 0))[0]
        k0, k1 = math.floor(lo / minor), math.ceil(hi / minor)
        if k1 - k0 > 4000:
            return
        for k in range(k0, k1 + 1):
            v = k * minor
            is_major = abs(v / major - round(v / major)) < 1e-6
            L = 10 if is_major else (6 if abs(v / (major / 2) - round(v / (major / 2))) < 1e-6
                                     else 3)
            p.setPen(QPen(self.palette().text().color(), 1))
            if self.vertical:
                y = c.w2s(0, v).y()
                p.drawLine(QPointF(self.width() - L, y), QPointF(self.width(), y))
                if is_major:
                    p.save()
                    p.translate(9, y)
                    p.rotate(-90)
                    txt = _fmt(v, major)
                    p.drawText(QRectF(-40, -9, 80, 12), Qt.AlignCenter, txt)
                    p.restore()
            else:
                x = c.w2s(v, 0).x()
                p.drawLine(QPointF(x, 0), QPointF(x, L))
                if is_major:
                    txt = _fmt(v, major)
                    w = fm.horizontalAdvance(txt)
                    p.drawText(QPointF(x - w / 2, THICK - 4), txt)
        if self.cursor is not None:
            p.setPen(QPen(QColor("#d23b2f"), 1))
            if self.vertical:
                y = c.w2s(0, self.cursor).y()
                p.drawLine(QPointF(0, y), QPointF(self.width(), y))
            else:
                x = c.w2s(self.cursor, 0).x()
                p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        p.end()


def _fmt(v: float, step: float) -> str:
    if abs(v) < 1e-9:
        return "0"
    dec = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return f"{v:.{dec}f}"
