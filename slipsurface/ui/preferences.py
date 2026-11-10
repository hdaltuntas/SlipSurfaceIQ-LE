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
    """Apply a compact, palette-consistent desktop theme to all windows."""
    app = QApplication.instance()
    if dark is None:
        dark = settings().value("dark", False, type=bool)
    settings().setValue("dark", dark)
    if dark:
        c = dict(
            bg="#141e2d",
            base="#1d2a3c",
            text="#e5edf8",
            border="#34465e",
            mid="#27384e",
            hover="#2b405b",
            checked="#294b76",
            sel_bg="#294b76",
            sel_text="#ffffff",
            disabled="#91a2b9",
            note="#aab8cc",
            header="#233249",
            highlight="#78adf5",
            tab_sel_bg="#1d2a3c",
        )
    else:
        c = dict(
            bg="#f4f6fa",
            base="#ffffff",
            text="#253650",
            border="#d8e0ec",
            mid="#e9eef5",
            hover="#edf4ff",
            checked="#e1edff",
            sel_bg="#e1edff",
            sel_text="#2358a3",
            disabled="#74839a",
            note="#555f6d",
            header="#f0f3f8",
            highlight="#3978d4",
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
    pal.setColor(QPalette.PlaceholderText, QColor(c["disabled"]))
    pal.setColor(QPalette.Mid, QColor(c["border"]))
    app.setPalette(pal)
    app.setFont(interface_font())
    app.setStyleSheet(f"""
        QWidget {{ font-family: "Source Sans 3"; font-size: 14px; color: {c["text"]}; }}
        QMainWindow, QDialog {{ background: {c["bg"]}; }}
        QMenuBar, QMenu, QToolBar {{ background: {c["base"]}; color: {c["text"]}; }}
        QMenuBar::item {{ padding: 6px 10px; background: transparent; }}
        QMenuBar::item:selected, QMenu::item:selected {{
            background: {c["sel_bg"]}; color: {c["sel_text"]}; }}
        QMenu::item {{ padding: 7px 26px; }}
        QToolBar {{ spacing: 4px; padding: 5px; border: 0;
                    border-bottom: 1px solid {c["border"]}; }}
        QToolBar::separator {{ background: {c["border"]}; width: 1px; margin: 5px; }}
        QToolButton, QPushButton {{
            background: {c["base"]}; color: {c["text"]};
            border: 1px solid {c["border"]}; border-radius: 6px;
            padding: 5px 8px; min-height: 18px; }}
        QToolButton:hover, QPushButton:hover {{
            background: {c["hover"]}; border-color: {c["mid"]}; }}
        QToolButton:checked, QPushButton:checked {{
            background: {c["checked"]}; color: {c["sel_text"] if not dark else "#ffffff"};
            border-color: {c["highlight"]}; }}
        QToolButton:disabled, QPushButton:disabled {{
            background: {c["mid"]}; color: {c["disabled"]}; }}
        QToolButton:focus, QPushButton:focus {{ border-color: {c["highlight"]}; }}
        QToolButton[workflowStep="true"] {{
            border: 1px solid transparent; background: transparent;
            font-size: 13px; padding: 6px 9px; }}
        QToolButton[workflowStep="true"]:hover {{ background: {c["hover"]}; }}
        QToolButton[workflowStep="true"]:checked {{
            background: {c["checked"]}; color: {c["sel_text"]}; font-weight: 600; }}
        QToolButton[workflowStep="true"]:focus {{ border-color: {c["highlight"]}; }}
        QToolButton[primaryAction="true"] {{
            background: {c["checked"]}; color: {c["sel_text"]};
            border-color: {c["highlight"]}; font-weight: 600; }}
        QToolButton[primaryAction="true"]:disabled {{
            background: {c["mid"]}; color: {c["disabled"]}; border-color: {c["border"]}; }}
        QScrollArea#action_rail, QWidget#action_rail_content {{
            background: {c["base"]}; border: none; }}
        QScrollArea#action_rail {{ border-right: 1px solid {c["border"]}; }}
        QLabel[railHeading="true"] {{
            color: {c["disabled"]}; font-size: 10px; font-weight: 600; padding: 2px 0; }}
        QToolButton[railButton="true"] {{
            background: transparent; border: 1px solid transparent; padding: 4px; }}
        QToolButton[railButton="true"]:hover {{ background: {c["hover"]}; }}
        QToolButton[railButton="true"]:checked {{
            background: {c["checked"]}; border-color: {c["highlight"]}; }}
        QToolButton[railButton="true"]:focus {{ border-color: {c["highlight"]}; }}
        QToolButton[railButton="true"]:disabled {{ background: transparent; }}
        QLabel[note="true"] {{ color: {c["note"]}; }}
        QLabel[emphasis="true"] {{ color: {c["sel_text"]}; font-weight: 600; }}
        QLabel[sectionHeading="true"] {{
            background: {c["header"]}; color: {c["text"]};
            font-weight: 600; padding: 8px; border-radius: 4px; }}
        QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QAbstractItemView {{
            background: {c["base"]}; color: {c["text"]};
            selection-background-color: {c["sel_bg"]};
            selection-color: {c["sel_text"]};
            border: 1px solid {c["border"]}; border-radius: 3px; padding: 4px; }}
        QSpinBox, QDoubleSpinBox {{
            background: {c["base"]}; color: {c["text"]}; min-height: 24px; }}
        QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {{ padding: 0; border: none; }}
        QAbstractItemView::item:selected {{ background: {c["sel_bg"]}; color: {c["sel_text"]}; }}
        QListWidget::item {{ padding: 5px; }}
        QHeaderView::section {{
            background: {c["header"]}; color: {c["text"]};
            padding: 6px; border: 1px solid {c["border"]}; }}
        QTabWidget::pane {{ border: 1px solid {c["border"]}; background: {c["base"]}; }}
        QTabBar::tab {{ background: {c["header"]}; color: {c["text"]}; padding: 8px 13px; }}
        QTabBar::tab:selected {{
            background: {c["tab_sel_bg"]}; color: {c["sel_text"] if not dark else c["text"]};
            border-bottom: 2px solid {c["highlight"]}; }}
        QDockWidget::title {{ background: {c["mid"]}; color: {c["text"]}; padding: 6px; }}
        QSplitter::handle {{ background: {c["mid"]}; }}
        QTreeWidget, QListWidget, QTableWidget {{ border: 1px solid {c["border"]}; }}
        QStatusBar {{
            background: {c["base"]}; color: {c["text"]};
            border-top: 1px solid {c["border"]}; }}
        QStatusBar::item {{ border: none; }}
        QToolButton[statusToggle="true"] {{
            background: transparent; color: {c["disabled"]}; font-size: 12px;
            border: 1px solid transparent; padding: 2px 5px; font-weight: 600; }}
        QToolButton[statusToggle="true"]:checked {{
            background: {c["checked"]}; color: {c["sel_text"]}; }}
        QToolButton[statusToggle="true"]:hover {{ background: {c["hover"]}; }}
        QToolButton[statusToggle="true"]:focus {{ border-color: {c["highlight"]}; }}
        QScrollBar:vertical {{ width: 10px; background: {c["bg"]}; margin: 0; }}
        QScrollBar:horizontal {{ height: 10px; background: {c["bg"]}; margin: 0; }}
        QScrollBar::handle {{ background: {c["border"]}; border-radius: 4px; }}
        QScrollBar::handle:vertical {{ min-height: 30px; }}
        QScrollBar::handle:horizontal {{ min-width: 30px; }}
        QScrollBar::handle:hover {{ background: {c["disabled"]}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QProgressBar {{
            background: {c["header"]}; color: {c["text"]}; border: 0; text-align: center; }}
        QProgressBar::chunk {{ background: {c["highlight"]}; }}
        QToolTip {{ background: {c["text"]}; color: {c["bg"]}; border: 0; padding: 5px; }}
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
