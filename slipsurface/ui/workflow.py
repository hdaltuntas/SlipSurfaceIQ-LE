"Breadcrumb workflow bar (Geometry › Properties › Surfaces), Slide2 style."

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

ARROW = 12


class WorkflowBar(QWidget):
    step_changed = Signal(int)

    def __init__(self, steps: list[str], parent=None) -> None:
        super().__init__(parent)
        self.steps = steps
        self.current = 0
        self.hover = -1
        self.setMouseTracking(True)
        self.setFixedHeight(36)
        self._rects: list[QRectF] = []
        self._font = QFont()
        self._font.setPointSize(9)

    def sizeHint(self):
        from PySide6.QtCore import QSize

        self._layout()
        w = int(self._rects[-1].right() + 8) if self._rects else 200
        return QSize(w, 30)

    def minimumSizeHint(self):
        return self.sizeHint()

    def set_current(self, i: int, emit: bool = True) -> None:
        if i != self.current:
            self.current = i
            self.update()
            if emit:
                self.step_changed.emit(i)

    def _layout(self) -> None:
        fm = QFontMetrics(self._font)
        x = 6.0
        self._rects = []
        for s in self.steps:
            w = fm.horizontalAdvance(s) + 46
            self._rects.append(QRectF(x, 3, w, self.height() - 6))
            x += w - ARROW + 4

    def paintEvent(self, ev) -> None:
        self._layout()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self._font)
        pal = self.palette()
        accent = pal.color(pal.Highlight)
        text_color = pal.color(pal.Text)
        base = pal.color(pal.Base)
        mid = pal.color(pal.AlternateBase)
        for i, (s, r) in enumerate(zip(self.steps, self._rects, strict=False)):
            path = QPainterPath()
            path.moveTo(r.left(), r.top())
            path.lineTo(r.right() - ARROW, r.top())
            path.lineTo(r.right(), r.center().y())
            path.lineTo(r.right() - ARROW, r.bottom())
            path.lineTo(r.left(), r.bottom())
            if i > 0:
                path.lineTo(r.left() + ARROW, r.center().y())
            path.closeSubpath()
            if i == self.current:
                fill, text, edge = accent, QColor("white"), accent.darker(115)
            elif i == self.hover:
                fill, text, edge = mid, text_color, accent
            else:
                fill, text, edge = base, text_color, pal.color(pal.Mid)
            p.setPen(QPen(edge, 1))
            p.setBrush(fill)
            p.drawPath(path)
            p.setPen(text)
            p.drawText(r.adjusted(ARROW if i else 4, 0, -ARROW, 0), Qt.AlignCenter, s)
        p.end()

    def _index_at(self, pos) -> int:
        for i, r in enumerate(self._rects):
            if r.contains(QPointF(pos)):
                return i
        return -1

    def mouseMoveEvent(self, ev) -> None:
        h = self._index_at(ev.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, ev) -> None:
        self.hover = -1
        self.update()

    def mousePressEvent(self, ev) -> None:
        i = self._index_at(ev.position())
        if i >= 0:
            self.set_current(i)
