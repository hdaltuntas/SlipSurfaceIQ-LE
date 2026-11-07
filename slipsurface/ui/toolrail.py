"""Scrollable action rail: every CAD tool stays reachable on short screens."""

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class ActionRail(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("action_rail")
        self.setAccessibleName("Modeling tools")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFixedWidth(76)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.content = QWidget()
        self.content.setObjectName("action_rail_content")
        self.column = QVBoxLayout(self.content)
        self.column.setContentsMargins(5, 6, 5, 8)
        self.column.setSpacing(10)
        self.column.setAlignment(Qt.AlignTop)
        self.buttons = {}
        self.setWidget(self.content)

    def add_group(self, title, actions):
        group = QWidget(self.content)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        heading = QLabel(title)
        heading.setProperty("railHeading", True)
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)
        for action in actions:
            button = QToolButton(group)
            button.setProperty("railButton", True)
            button.setDefaultAction(action)
            button.setAccessibleName(action.text().replace("&", "").replace("…", ""))
            shortcut = action.shortcut().toString()
            if shortcut:
                button.setToolTip(f"{action.toolTip()} ({shortcut})")
            button.setIconSize(QSize(22, 22))
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setFixedSize(40, 36)
            button.setFocusPolicy(Qt.StrongFocus)
            button.installEventFilter(self)
            layout.addWidget(button, 0, Qt.AlignHCenter)
            self.buttons[action] = button
        self.column.addWidget(group)
        return group

    def eventFilter(self, watched, event):
        if event.type() == QEvent.FocusIn and isinstance(watched, QToolButton):
            self.ensureWidgetVisible(watched, 0, 8)
        return super().eventFilter(watched, event)


class ToolStrip(QScrollArea):
    """Keep contextual input widgets reachable when a toolbar is too wide.

    Qt's toolbar overflow is suitable for actions, but cannot reliably expose
    the existing combo boxes and spin boxes in an overflow menu.
    """

    def __init__(self, toolbar, parent=None):
        super().__init__(parent)
        self.setObjectName("context_strip")
        self.setAccessibleName(toolbar.windowTitle())
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toolbar = toolbar
        self._pending = False
        self.setWidget(toolbar)
        toolbar.installEventFilter(self)
        for child in toolbar.findChildren(QWidget):
            child.installEventFilter(self)
        self._sync_size()

    def ensureWidgetVisible(self, child, xmargin=8, ymargin=0):
        # QScrollArea uses the input-method cursor rectangle for editors. Show
        # the whole spin box / selector, including its buttons, instead.
        left = child.mapTo(self.toolbar, QPoint(0, 0)).x()
        right = left + child.width()
        scroll = self.horizontalScrollBar()
        if left - xmargin < scroll.value():
            scroll.setValue(left - xmargin)
        elif right + xmargin > scroll.value() + self.viewport().width():
            scroll.setValue(right + xmargin - self.viewport().width())

    def _sync_size(self):
        self._pending = False
        hint = self.toolbar.sizeHint()
        self.toolbar.setMinimumSize(hint)
        # Reserve a thin scrolling track so switching steps never moves the CAD
        # viewport or changes the model's apparent position.
        self.setFixedHeight(hint.height() + self.horizontalScrollBar().sizeHint().height())

    def eventFilter(self, watched, event):
        if event.type() == QEvent.FocusIn and isinstance(watched, QWidget):
            control = watched
            while control.parentWidget() not in (None, self.toolbar):
                control = control.parentWidget()
            if control.parentWidget() is self.toolbar:
                self.ensureWidgetVisible(control)
        if event.type() in (QEvent.LayoutRequest, QEvent.StyleChange, QEvent.FontChange):
            if not self._pending:
                self._pending = True
                QTimer.singleShot(0, self._sync_size)
        return super().eventFilter(watched, event)
