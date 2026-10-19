"""CAD area = canvas + rulers (left and bottom)."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QWidget

from slipsurface.ui.cad.canvas import CadCanvas
from slipsurface.ui.cad.rulers import THICK, Ruler


class CadArea(QFrame):
    def __init__(self, parent: QWidget | None = None, editable: bool = True) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.canvas = CadCanvas(self, editable=editable)
        self.vruler = Ruler(self.canvas, vertical=True)
        self.hruler = Ruler(self.canvas, vertical=False)
        corner = QWidget()
        corner.setFixedSize(THICK, THICK)
        corner.setStyleSheet("background:#f4f5f7;")
        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.vruler, 0, 0)
        lay.addWidget(self.canvas, 0, 1)
        lay.addWidget(corner, 1, 0)
        lay.addWidget(self.hruler, 1, 1)
        self._corner = corner

    def show_rulers(self, on: bool) -> None:
        for w in (self.vruler, self.hruler, self._corner):
            w.setVisible(on)
