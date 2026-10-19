"""Shared image export feedback for the model and result windows."""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox


def export_image(parent, widget, default_name: str) -> str | None:
    path, selected_filter = QFileDialog.getSaveFileName(
        parent, "Resmi dışa aktar", default_name, "PNG (*.png);;JPEG (*.jpg *.jpeg)")
    if not path:
        return None
    if not Path(path).suffix:
        path += ".jpg" if selected_filter.startswith("JPEG") else ".png"
    if not widget.grab().save(path):
        QMessageBox.warning(parent, "Resim kaydedilemedi",
                            f"Dosya yazılamadı:\n{path}\n\n"
                            "Klasörün yazılabilir olduğunu ve dosya uzantısının "
                            "PNG veya JPEG olduğunu kontrol edin.")
        return None
    parent.statusBar().showMessage(f"Kaydedildi: {path}", 5000)
    return path
