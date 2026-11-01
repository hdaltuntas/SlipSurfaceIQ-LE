"""Shared image export feedback for the model and result windows."""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox


def export_image(parent, widget, default_name: str) -> str | None:
    path, selected_filter = QFileDialog.getSaveFileName(
        parent, "Export image", default_name, "PNG (*.png);;JPEG (*.jpg *.jpeg)"
    )
    if not path:
        return None
    if not Path(path).suffix:
        path += ".jpg" if selected_filter.startswith("JPEG") else ".png"
    if not widget.grab().save(path):
        QMessageBox.warning(
            parent,
            "Image could not be saved",
            f"The file could not be written:\n{path}\n\nCheck that the folder is writable and the file extension is PNG or JPEG.",
        )
        return None
    parent.statusBar().showMessage(f"Saved: {path}", 5000)
    return path
