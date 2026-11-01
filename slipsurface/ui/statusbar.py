"""Status bar shared by Modeler and Interpret: hints, coordinates, command box,
SNAP / GRID / ORTHO / OSNAP toggles (AutoCAD keys F9 / F7 / F8 / F3)."""

from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QLineEdit, QStatusBar, QToolButton

TOGGLE_CSS = (
    "QToolButton{border:none;padding:0 5px;color:#9aa0a6;font-weight:bold;}"
    "QToolButton:checked{color:#111;}"
)


class CadStatusBar(QStatusBar):
    def __init__(self, canvas, parent=None, with_command: bool = True) -> None:
        super().__init__(parent)
        self.c = canvas
        self.showMessage("F1 for Help")
        self.coords = QLabel("x: —   y: —")
        self.coords.setMinimumWidth(190)
        self.addPermanentWidget(self.coords)
        self.cmd = None
        if with_command:
            self.cmd = QLineEdit()
            self.cmd.setPlaceholderText("x,y  |  @dx,dy  |  @L<angle")
            self.cmd.setFixedWidth(170)
            self.cmd.setToolTip(
                "Coordinate entry (drawing tools): absolute x,y, relative @dx,dy, polar @length<angle. Empty Enter = finish, c = close, u = undo."
            )
            self.cmd.returnPressed.connect(self._command)
            self.addPermanentWidget(self.cmd)
        self.toggles = {}
        for name, attr, key, tip in (
            ("SNAP", "snap_on", "F9", "Snap to Grid Points"),
            ("GRID", "grid_on", "F7", "Show Grid"),
            ("ORTHO", "ortho_on", "F8", "Constrain Horizontal/Vertical"),
            ("OSNAP", "osnap_on", "F3", "Object Snap: Endpoint, Midpoint, Intersection, Nearest"),
        ):
            b = QToolButton()
            b.setText(name)
            b.setCheckable(True)
            b.setChecked(getattr(canvas, attr))
            b.setStyleSheet(TOGGLE_CSS)
            b.setToolTip(f"{tip} ({key})")
            b.toggled.connect(lambda on, a=attr: self._toggle(a, on))
            self.addPermanentWidget(b)
            self.toggles[attr] = b
            sc = QShortcut(QKeySequence(key), parent or canvas)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(b.toggle)
        canvas.mouse_world.connect(self._coords)
        canvas.status.connect(lambda m: self.showMessage(m, 8000))

    def _toggle(self, attr: str, on: bool) -> None:
        setattr(self.c, attr, on)
        self.c.update()

    def _coords(self, x: float, y: float) -> None:
        self.coords.setText(f"x: {x:10.3f}   y: {y:10.3f}")

    def _command(self) -> None:
        text = self.cmd.text()
        if self.c.command(text):
            self.cmd.clear()
        self.c.update()
        self.c.setFocus()
