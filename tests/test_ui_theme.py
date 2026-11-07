"""Keyboard workflow and themed layout regressions on laptop-sized windows."""

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from slipsurface.ui import preferences
from slipsurface.ui.workflow import WorkflowBar


@pytest.fixture
def themed_app(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    palette, font, stylesheet = app.palette(), app.font(), app.styleSheet()
    store = QSettings(str(tmp_path / "appearance.ini"), QSettings.IniFormat)
    monkeypatch.setattr(preferences, "settings", lambda: store)
    yield app
    app.setPalette(palette)
    app.setFont(font)
    app.setStyleSheet(stylesheet)
    app.processEvents()


def test_workflow_keyboard_and_mouse_select_same_step(themed_app):
    bar = WorkflowBar(["Geometry", "Support", "Loading", "Properties", "Surfaces"])
    bar.show()
    spy = QSignalSpy(bar.step_changed)
    try:
        QTest.mouseClick(bar.buttons[1], Qt.LeftButton)
        assert bar.current == 1 and spy.count() == 1
        QTest.keyClick(bar.buttons[1], Qt.Key_Right)
        assert bar.current == 2 and spy.count() == 2
        QTest.keyClick(bar.buttons[2], Qt.Key_End)
        assert bar.current == 4
        QTest.keyClick(bar.buttons[4], Qt.Key_Home)
        assert bar.current == 0
        QTest.keyClick(bar.buttons[0], Qt.Key_Left)
        assert bar.current == 4
        assert [b.isChecked() for b in bar.buttons] == [False, False, False, False, True]
        before = spy.count()
        bar.set_current(4)
        assert spy.count() == before
        bar.set_current(0, emit=False)
        assert spy.count() == before and bar.buttons[0].isChecked()
        with pytest.raises(IndexError):
            bar.set_current(5)
        assert bar.current == 0
    finally:
        bar.close()


@pytest.mark.parametrize("dark", [False, True])
def test_themed_modeler_fits_and_workflow_changes_tools(themed_app, dark):
    from slipsurface.ui.modeler import ModelerWindow

    preferences.apply_theme(dark)
    win = ModelerWindow()
    win.resize(800, 600)
    win.show()
    try:
        for _ in range(5):
            themed_app.processEvents()
        assert (win.width(), win.height()) == (800, 600)
        assert win.canvas.height() > 380
        assert win.tool_rail.verticalScrollBar().maximum() > 0
        for i, button in enumerate(win.workflow.buttons):
            QTest.mouseClick(button, Qt.LeftButton)
            themed_app.processEvents()
            assert win.workflow.current == i
            assert win.step_bars[i].isVisible()
        # Toggling appearance updates existing controls through the shared QSS;
        # no local black-text override can defeat the selected dark palette.
        preferences.apply_theme(not dark)
        themed_app.processEvents()
        assert all(not button.styleSheet() for button in win.status.toggles.values())
        win.status.toggles["snap_on"].toggle()
        assert win.canvas.snap_on == win.status.toggles["snap_on"].isChecked()
    finally:
        win.doc.mark_clean()
        win.close()
