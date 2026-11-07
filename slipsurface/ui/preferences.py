"""Persistent appearance preferences shared by all windows."""

from PySide6.QtCore import QSettings
from functools import cache
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from slipsurface import __version__


def settings():
    return QSettings("SlipSurface", "SlipSurface LE")


@cache
def interface_font():
    folder = Path(__file__).resolve().parents[1] / "report" / "fonts"
    family = "Segoe UI"
    for name in ("Regular", "SemiBold", "Bold", "Italic"):
        font_id = QFontDatabase.addApplicationFont(str(folder / f"SourceSans3-{name}.ttf"))
        if font_id >= 0:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
    return QFont(family, 10)


DESIGN_SIZE = (1920, 1080)  # logical resolution the window sizes were designed for


def available_geometry(widget=None):
    """Usable area (without taskbar / dock) of the widget's screen or the primary one."""
    app = QApplication.instance()
    screen = (widget.screen() if widget is not None else None) or app.primaryScreen()
    return screen.availableGeometry()


def fit_to_screen(widget, width: int, height: int, center: bool = True) -> None:
    """Size a window / dialog for the detected screen resolution: designed sizes
    scale with the screen (relative to 1920 x 1080) and never exceed 95 % of
    the available area."""
    avail = available_geometry(widget)
    scale = min(avail.width() / DESIGN_SIZE[0], avail.height() / DESIGN_SIZE[1])
    scale = min(max(scale, 0.6), 1.6)
    w = min(int(width * scale), int(avail.width() * 0.95))
    h = min(int(height * scale), int(avail.height() * 0.95))
    widget.resize(max(w, 200), max(h, 150))
    if center:
        frame = widget.frameGeometry()
        frame.moveCenter(avail.center())
        widget.move(frame.topLeft())


def show_screen_sized(window) -> None:
    """Open a main window covering the whole usable screen (maximized)."""
    window.setGeometry(available_geometry(window))
    window.showMaximized()


def apply_theme(dark=None):
    """Apply the SlipSurfaceIQ FEA-style theme (explicit light / dark palettes).

    The light mode mirrors the SlipSurfaceIQ-FEA desktop app: an explicit
    palette independent of the system dark mode, with matching QSS for
    menus, toolbars, buttons, tabs and headers.
    """
    app = QApplication.instance()
    if dark is None:
        dark = settings().value("dark", False, type=bool)
    settings().setValue("dark", dark)
    if dark:
        c = dict(
            bg="#1b2735",
            base="#223042",
            text="#e6edf7",
            border="#39516b",
            mid="#31435c",
            hover="#2a3d54",
            checked="#3a5f8f",
            sel_bg="#3a5f8f",
            sel_text="#ffffff",
            disabled="#7f90a5",
            header="#26354a",
            highlight="#4d8fd1",
            tab_sel_bg="#2e4260",
        )
    else:  # FEA-style explicit light palette
        c = dict(
            bg="#eef2f6",
            base="#ffffff",
            text="#243746",
            border="#d5dee7",
            mid="#e8eef4",
            hover="#e8f3fb",
            checked="#d8ecf8",
            sel_bg="#dcecf7",
            sel_text="#124d70",
            disabled="#71818d",
            header="#edf2f6",
            highlight="#1879aa",
            tab_sel_bg="#ffffff",
        )
    pal = QPalette()
    for role in (QPalette.Window, QPalette.Button):
        pal.setColor(role, QColor(c["bg"]))
    for role in (QPalette.Base, QPalette.AlternateBase, QPalette.ToolTipBase):
        pal.setColor(role, QColor(c["base"]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText, QPalette.ToolTipText):
        pal.setColor(role, QColor(c["text"]))
        pal.setColor(QPalette.Disabled, role, QColor(c["disabled"]))
    pal.setColor(QPalette.Highlight, QColor(c["highlight"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)
    app.setFont(interface_font())
    app.setStyleSheet(f"""
        QWidget {{ font-family: "Source Sans 3"; font-size: 14px; color: {c["text"]}; }}
        QMainWindow, QDialog {{ background: {c["bg"]}; }}
        QMainWindow::separator {{ background: {c["border"]}; width: 1px; height: 1px; }}
        QMenuBar {{
            background: {c["base"]}; color: {c["text"]};
            border-bottom: 1px solid {c["border"]}; padding: 2px 6px;
        }}
        QMenuBar::item {{ padding: 8px 13px; margin: 2px 1px; border-radius: 6px; }}
        QMenuBar::item:selected, QMenu::item:selected {{
            background: {c["sel_bg"]}; color: {c["sel_text"]}; }}
        QMenu {{
            background: {c["base"]}; color: {c["text"]};
            border: 1px solid {c["border"]}; padding: 5px; border-radius: 8px;
        }}
        QMenu::item {{ padding: 8px 30px 8px 12px; border-radius: 5px; }}
        QToolBar {{
            background: {c["base"]}; spacing: 6px; padding: 6px 8px;
            border: 0; border-bottom: 1px solid {c["border"]};
        }}
        QToolBar#workflow_toolbar {{
            background: {c["bg"]}; padding: 6px 12px; border-bottom: 1px solid {c["border"]};
        }}
        QToolBar#main_toolbar, QToolBar#notes_toolbar {{
            background: {c["base"]}; padding: 8px 6px; border-right: 1px solid {c["border"]};
        }}
        QToolBar#main_toolbar QToolButton, QToolBar#notes_toolbar QToolButton {{
            min-width: 38px; min-height: 38px; padding: 5px; border-radius: 8px;
        }}
        QToolBar#main_toolbar::separator, QToolBar#notes_toolbar::separator {{
            height: 10px; width: 10px; background: transparent;
        }}
        QToolButton, QPushButton {{
            background: {c["base"]}; color: {c["text"]};
            border: 1px solid {c["border"]}; border-radius: 6px;
            padding: 7px 11px; min-height: 20px; }}
        QToolButton:hover, QPushButton:hover {{
            background: {c["hover"]}; border-color: {c["mid"]}; }}
        QToolButton:checked, QPushButton:checked {{
            background: {c["checked"]}; color: {c["sel_text"] if not dark else "#ffffff"};
            border-color: {c["highlight"]}; }}
        QPushButton:default {{
            background: {c["highlight"]}; color: #ffffff;
            border-color: {c["highlight"]}; font-weight: 600;
        }}
        QPushButton:default:hover {{ background: {c["sel_text"]}; }}
        QToolButton:disabled, QPushButton:disabled {{
            background: {c["mid"]}; color: {c["disabled"]}; }}
        QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QAbstractItemView {{
            background: {c["base"]}; color: {c["text"]};
            selection-background-color: {c["sel_bg"]};
            selection-color: {c["sel_text"]};
            border: 1px solid {c["border"]}; border-radius: 6px; padding: 5px; }}
        QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
            border: 1px solid {c["highlight"]};
        }}
        QSpinBox, QDoubleSpinBox {{
            background: {c["base"]}; color: {c["text"]}; min-height: 28px;
            border: 1px solid {c["border"]}; border-radius: 6px; padding: 2px 5px;
        }}
        QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {{ padding: 0; border: none; }}
        QAbstractItemView::item:selected {{ background: {c["sel_bg"]}; color: {c["sel_text"]}; }}
        QListWidget::item {{ padding: 7px 6px; border-radius: 4px; }}
        QHeaderView::section {{
            background: {c["header"]}; color: {c["text"]};
            padding: 7px; border: 0; border-bottom: 1px solid {c["border"]}; }}
        QTabWidget::pane {{
            border: 1px solid {c["border"]}; background: {c["base"]}; border-radius: 6px; }}
        QTabBar::tab {{
            background: {c["header"]}; color: {c["text"]};
            padding: 9px 15px; margin-right: 2px; }}
        QTabBar::tab:selected {{
            background: {c["tab_sel_bg"]}; color: {c["sel_text"] if not dark else c["text"]};
            border-bottom: 2px solid {c["highlight"]}; }}
        QDockWidget::title {{
            background: {c["mid"]}; color: {c["text"]};
            padding: 8px 10px; font-weight: 600; }}
        QSplitter::handle {{ background: {c["mid"]}; }}
        QTreeWidget, QListWidget, QTableWidget {{
            border: 1px solid {c["border"]}; border-radius: 6px; }}
        QStatusBar {{
            background: {c["mid"]}; color: {c["text"]};
            border-top: 1px solid {c["border"]}; }}
        QStatusBar QLabel {{ padding: 2px 8px; }}
        QStatusBar QToolButton {{
            border: 0; background: transparent; padding: 4px 8px;
            color: {c["disabled"]}; font-weight: 600; border-radius: 5px;
        }}
        QStatusBar QToolButton:hover {{ background: {c["hover"]}; color: {c["text"]}; }}
        QStatusBar QToolButton:checked {{
            background: {c["checked"]}; color: {c["sel_text"]}; }}
        QWidget#ruler_corner {{ background: {c["mid"]}; }}
        QProgressBar {{
            background: {c["header"]}; color: {c["text"]}; border: 0; text-align: center; }}
        QProgressBar::chunk {{ background: {c["highlight"]}; }}
        QToolTip {{ background: {c["text"]}; color: {c["bg"]}; border: 0; padding: 6px 8px; }}
    """)
    for widget in app.topLevelWidgets():
        widget.update()


TECHNOLOGIES = f"""
<h3>SlipSurfaceIQ LE {__version__}</h3>
<p>2D Limit Equilibrium Slope Stability</p>
<p>© 2026 Hasan Deniz Altuntaş — GNU AGPL v3 or later. No warranty.</p>
<table cellpadding="5">
<tr><th>Technology</th><th>License</th></tr>
<tr><td>Python</td><td>PSF License</td></tr>
<tr><td>PySide6 / Qt / Shiboken6</td><td>LGPL-3.0 / GPL-3.0 / commercial</td></tr>
<tr><td>NumPy · SciPy</td><td>BSD-3-Clause</td></tr>
<tr><td>Shapely</td><td>BSD-3-Clause (GEOS: LGPL-2.1)</td></tr>
<tr><td>ReportLab</td><td>BSD</td></tr>
<tr><td>ezdxf</td><td>MIT</td></tr>
<tr><td>QtAwesome · QtPy</td><td>MIT</td></tr>
<tr><td>Material Design Icons (Pictogrammers)</td><td>Apache-2.0</td></tr>
<tr><td>Source Sans 3</td><td>SIL Open Font License 1.1</td></tr>
</table>
<p><a href="https://doc.qt.io/qtforpython-6/licenses.html">Qt licenses</a> ·
<a href="https://github.com/spyder-ide/qtawesome/blob/master/LICENSE.txt">QtAwesome licenses</a> ·
<a href="https://github.com/Templarian/MaterialDesign/blob/master/LICENSE">Icon license</a> ·
<a href="https://github.com/mozman/ezdxf/blob/master/LICENSE">ezdxf license</a></p>
"""
