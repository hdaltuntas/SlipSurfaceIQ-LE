"""PDF guides shipped in docs/, opened in the system PDF viewer."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

DOCS = Path(__file__).resolve().parents[2] / "docs"
SCRIPTING_TUTORIAL = DOCS / "Python_Scripting_Tutorial.pdf"
DXF_GUIDE = DOCS / "DXF_Import_Guide.pdf"


def open_guide(path: Path, parent: QWidget | None = None) -> bool:
    """Open a guide; warn instead when the file is missing."""
    if not path.is_file():
        QMessageBox.warning(parent, "Guide", f"Not found: {path}")
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
