"""Persistent appearance preferences shared by all windows."""

from PySide6.QtCore import QSettings
from functools import cache
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


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
    app = QApplication.instance()
    if dark is None:
        dark = settings().value("dark", False, type=bool)
    settings().setValue("dark", dark)
    bg, base, text, border = (
        ("#161e2c", "#202c3e", "#e6edf7", "#36465d")
        if dark
        else ("#f1f5f9", "#ffffff", "#243348", "#d9e2ed")
    )
    pal = QPalette()
    for role in (QPalette.Window, QPalette.Button):
        pal.setColor(role, QColor(bg))
    for role in (QPalette.Base, QPalette.AlternateBase, QPalette.ToolTipBase):
        pal.setColor(role, QColor(base))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText, QPalette.ToolTipText):
        pal.setColor(role, QColor(text))
        pal.setColor(QPalette.Disabled, role, QColor("#8491a4"))
    pal.setColor(QPalette.Highlight, QColor("#287ae6"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)
    app.setFont(interface_font())
    app.setStyleSheet(f"""
        QWidget {{ font-family: "Source Sans 3"; font-size: 14px; }}
        QMainWindow, QDialog {{ background: {bg}; }}
        QToolBar {{ spacing: 5px; padding: 7px; border: none;
                    border-bottom: 1px solid {border}; }}
        QToolButton {{ padding: 6px; border-radius: 6px; }}
        QToolButton:hover, QPushButton:hover {{ background: {border}; }}
        QToolButton:checked {{ background: #315b88; color: white; }}
        QPushButton {{ padding: 7px 16px; border: 1px solid {border}; border-radius: 6px; }}
        QLineEdit, QComboBox, QPlainTextEdit {{
            padding: 5px; border: 1px solid {border}; border-radius: 5px;
            background: {base}; color: {text}; }}
        QSpinBox, QDoubleSpinBox {{ background: {base}; color: {text}; min-height: 28px; }}
        QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {{ padding: 0; border: none; }}
        QTreeWidget, QListWidget, QTableWidget {{ border: 1px solid {border}; }}
        QMenu {{ padding: 5px; }}
        QMenu::item {{ padding: 7px 26px; }}
        QMenu::item:selected {{ background: #287ae6; color: white; }}
        QStatusBar {{ border-top: 1px solid {border}; }}
    """)
    for widget in app.topLevelWidgets():
        widget.update()


TECHNOLOGIES = """
<h3>SlipSurfaceIQ LE 2026.0.0</h3>
<p>2D Limit Equilibrium / Limit Denge</p>
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
