"""Accessible workflow tabs shared with the modeler's contextual tools."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QToolButton, QWidget


class WorkflowBar(QWidget):
    step_changed = Signal(int)

    def __init__(self, steps: list[str], parent=None) -> None:
        super().__init__(parent)
        self.steps = steps
        self.current = 0
        self.setObjectName("workflow_steps")
        self.setAccessibleName("Modeling workflow")
        self.buttons = []
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(3)
        for i, step in enumerate(steps):
            button = QToolButton(self)
            button.setText(f"{i + 1}  {step}")
            button.setAccessibleName(step)
            button.setToolTip(f"{step} tools · use Left / Right to switch steps")
            button.setProperty("workflowStep", True)
            button.setCheckable(True)
            button.setFocusPolicy(Qt.StrongFocus)
            button.installEventFilter(self)
            self.group.addButton(button, i)
            self.buttons.append(button)
            layout.addWidget(button)
        self.group.idClicked.connect(self.set_current)
        if self.buttons:
            self.buttons[0].setChecked(True)
            self.setFocusProxy(self.buttons[0])

    def set_current(self, i: int, emit: bool = True) -> None:
        if not 0 <= i < len(self.steps):
            raise IndexError(f"Workflow step {i} is out of range")
        self.buttons[i].setChecked(True)
        if i != self.current:
            self.current = i
            if emit:
                self.step_changed.emit(i)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and watched in self.buttons:
            key = event.key()
            index = self.buttons.index(watched)
            if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Home, Qt.Key_End):
                if key == Qt.Key_Home:
                    index = 0
                elif key == Qt.Key_End:
                    index = len(self.buttons) - 1
                else:
                    index = (index + (1 if key == Qt.Key_Right else -1)) % len(self.buttons)
                self.set_current(index)
                self.buttons[index].setFocus(Qt.TabFocusReason)
                return True
        return super().eventFilter(watched, event)
