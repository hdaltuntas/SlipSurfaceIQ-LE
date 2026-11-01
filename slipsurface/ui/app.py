"""QApplication bootstrap, invoked exclusively by the root main.py entry point."""

from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from slipsurface import __version__
from slipsurface.ui.icons import icon


def _install_excepthook() -> None:
    """Show unexpected errors in a dialog (and the IDE console) instead of a
    silent crash; the application keeps running."""

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        if sys.__stderr__ is not None:  # None under pythonw.exe
            sys.__stderr__.write(text)
        app = QApplication.instance()
        if app is not None and not app.closingDown():
            box = QMessageBox(
                QMessageBox.Critical, "Unexpected error", f"{exc_type.__name__}: {exc}"
            )
            box.setDetailedText(text)
            box.exec()

    sys.excepthook = hook


def light_palette() -> QPalette:
    """Fixed light palette: the CAD drawing, legends and property grids are
    designed for a light background (as in Slide2), so the OS dark mode must
    not invert text colours."""
    pal = QPalette()
    c = {
        QPalette.Window: "#f0f0f0",
        QPalette.WindowText: "#000000",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f5f6f8",
        QPalette.ToolTipBase: "#ffffdc",
        QPalette.ToolTipText: "#000000",
        QPalette.Text: "#000000",
        QPalette.Button: "#f0f0f0",
        QPalette.ButtonText: "#000000",
        QPalette.BrightText: "#ff0000",
        QPalette.Highlight: "#3478d4",
        QPalette.HighlightedText: "#ffffff",
        QPalette.Link: "#2a7ad0",
        QPalette.PlaceholderText: "#8a8a8a",
    }
    for role, col in c.items():
        pal.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#9a9a9a"))
    return pal


def run(
    argv: list[str] | None = None,
    project_path: str | None = None,
    example: str | None = None,
    smoke: float | None = None,
) -> int:
    argv = list(argv if argv is not None else sys.argv)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("SlipSurfaceIQ LE")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("SlipSurface")  # settings storage key, kept for existing preferences
    app.setStyle("Fusion")
    from slipsurface.ui.preferences import apply_theme

    apply_theme()
    app.setWindowIcon(icon("interpret"))
    _install_excepthook()

    from slipsurface.project import EXAMPLES
    from slipsurface.ui.modeler import ModelerWindow

    if example is not None and example not in EXAMPLES:
        print(f"[ERROR] Example not found: {example!r}. Options: {', '.join(EXAMPLES)}")
        return 1

    win = ModelerWindow(EXAMPLES[example]() if example else None)
    if project_path:
        win.open_project(project_path)
    from slipsurface.ui.preferences import show_screen_sized

    show_screen_sized(win)
    if not smoke:
        QTimer.singleShot(3000, win.auto_check_updates)  # once a day, silent on failure
    if smoke:

        def _quit():
            win.doc.mark_clean()
            win.close()
            app.quit()

        QTimer.singleShot(int(smoke * 1000), _quit)
    return app.exec()
