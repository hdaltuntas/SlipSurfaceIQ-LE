"""Small dialogs: coordinate table, info viewer, slice data, grid settings."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def _ok_cancel(dlg, ok_slot=None):
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.button(QDialogButtonBox.Ok).setText("Tamam")
    btns.button(QDialogButtonBox.Cancel).setText("İptal")
    btns.accepted.connect(ok_slot or dlg.accept)
    btns.rejected.connect(dlg.reject)
    return btns


def parse_float(text: str, what: str) -> float:
    try:
        return float(str(text).strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"'{what}' sayısal olmalı (girilen: '{text}').") from None


class CoordinatesDialog(QDialog):
    """Edit the vertices of one boundary as a table."""

    def __init__(self, title: str, pts, parent=None, min_points: int = 2) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Koordinatlar — {title}")
        self.resize(380, 460)
        self.min_points = min_points
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["x [m]", "y [m]"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for x, y in pts:
            self._append(x, y)
        add, rem = QPushButton("Satır ekle"), QPushButton("Satır sil")
        add.clicked.connect(self._add)
        rem.clicked.connect(self._remove)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(rem)
        row.addStretch(1)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#b03a2e;")
        lay = QVBoxLayout(self)
        lay.addWidget(self.table, 1)
        lay.addLayout(row)
        lay.addWidget(self.error)
        lay.addWidget(_ok_cancel(self, self._accept))

    def _append(self, x, y, at=None) -> None:
        r = self.table.rowCount() if at is None else at
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(f"{x:g}"))
        self.table.setItem(r, 1, QTableWidgetItem(f"{y:g}"))

    def _add(self) -> None:
        r = self.table.currentRow()
        try:
            pts = self.points()
        except ValueError:
            pts = []
        if pts and 0 <= r < len(pts) - 1:
            x, y = (pts[r][0] + pts[r + 1][0]) / 2, (pts[r][1] + pts[r + 1][1]) / 2
            self._append(x, y, r + 1)
        elif pts:
            self._append(pts[-1][0] + 1, pts[-1][1])
        else:
            self._append(0, 0)

    def _remove(self) -> None:
        r = self.table.currentRow()
        if r >= 0 and self.table.rowCount() > self.min_points:
            self.table.removeRow(r)

    def points(self) -> list[list[float]]:
        out = []
        for r in range(self.table.rowCount()):
            out.append([parse_float(self.table.item(r, c).text() if self.table.item(r, c) else "",
                                    f"satır {r + 1}, {'xy'[c]}") for c in range(2)])
        return out

    def _accept(self) -> None:
        try:
            pts = self.points()
        except ValueError as exc:
            self.error.setText(f"⚠ {exc}")
            return
        if len(pts) < self.min_points:
            self.error.setText(f"⚠ En az {self.min_points} nokta gerekli.")
            return
        self.accept()


class InfoViewer(QDialog):
    def __init__(self, text: str, parent=None, title: str = "Bilgi Görüntüleyici") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(860, 620)
        self.edit = QPlainTextEdit(text)
        self.edit.setReadOnly(True)
        f = QFont("Monospace")
        f.setStyleHint(QFont.TypeWriter)
        f.setPointSize(9)
        self.edit.setFont(f)
        copy_b, save_b, close_b = QPushButton("Kopyala"), QPushButton("Kaydet…"), \
            QPushButton("Kapat")
        copy_b.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.edit.toPlainText()))
        save_b.clicked.connect(self._save)
        close_b.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(copy_b)
        row.addWidget(save_b)
        row.addStretch(1)
        row.addWidget(close_b)
        lay = QVBoxLayout(self)
        lay.addWidget(self.edit, 1)
        lay.addLayout(row)

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Raporu kaydet", "rapor.txt",
                                              "Metin (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.edit.toPlainText())


def slice_rows(res, i: int) -> list[tuple[str, str]]:
    s = res.slices
    mat = s.materials[s.mat_idx[i]]
    c, tp = mat.strength(np.array([max(s.W[i] / s.b[i] - s.u[i], 0.0)]))
    rows = [
        ("Dilim no", f"{i + 1} / {s.n}"),
        ("Taban malzemesi", mat.name),
        ("Sol / sağ kenar x [m]", f"{s.xl[i]:.3f} / {s.xr[i]:.3f}"),
        ("Genişlik b [m]", f"{s.b[i]:.3f}"),
        ("Taban kotu (orta) [m]", f"{s.y_base[i]:.3f}"),
        ("Zemin kotu (orta) [m]", f"{s.y_top[i]:.3f}"),
        ("Taban açısı α [°]", f"{np.degrees(s.alpha[i]) * (-s.direction):.2f}"),
        ("Taban uzunluğu l [m]", f"{s.l[i]:.3f}"),
        ("Ağırlık W [kN/m]", f"{s.W[i]:.3f}"),
        ("Boşluk suyu basıncı u [kPa]", f"{s.u[i]:.3f}"),
        ("Kohezyon c [kPa] (σn ≈ W/b − u)", f"{c[0]:.3f}"),
        ("Sürtünme açısı φ [°]", f"{np.degrees(np.arctan(tp[0])):.2f}"),
    ]
    if s.kh:
        rows.append(("Sismik yatay kuvvet kh·W [kN/m]", f"{s.Fh[i]:.3f}"))
    return rows


class SliceDataDialog(QDialog):
    def __init__(self, res, i: int, method: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Dilim Verisi — {method}")
        self.resize(430, 420)
        rows = slice_rows(res, i)
        t = QTableWidget(len(rows), 2)
        t.setHorizontalHeaderLabels(["Büyüklük", "Değer"])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for r, (k, v) in enumerate(rows):
            t.setItem(r, 0, QTableWidgetItem(k))
            it = QTableWidgetItem(v)
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(r, 1, it)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        b = QPushButton("Kapat")
        b.clicked.connect(self.accept)
        lay = QVBoxLayout(self)
        lay.addWidget(t, 1)
        lay.addWidget(b)


class GridSettingsDialog(QDialog):
    def __init__(self, spacing: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Izgara ve Yakalama Ayarları")
        self.spacing = QDoubleSpinBox()
        self.spacing.setRange(0.001, 1000)
        self.spacing.setDecimals(3)
        self.spacing.setValue(spacing)
        self.spacing.setSuffix(" m")
        f = QFormLayout()
        f.addRow("Izgara / SNAP aralığı:", self.spacing)
        note = QLabel("SNAP açıkken noktalar bu aralıktaki ızgara noktalarına yakalanır.")
        note.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(note)
        lay.addWidget(_ok_cancel(self))
