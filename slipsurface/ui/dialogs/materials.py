"""Define Material Properties dialog (Slide2 layout)."""

from __future__ import annotations

import copy

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from slipsurface.materials import HoekBrown
from slipsurface.project import PALETTE, MaterialSpec
from slipsurface.ui.icons import color_icon, icon

TITLE_CSS = "color:#2a7ad0;font-size:16px;"

# (attribute, label, min, max, decimals)
MC_ROWS = [("c", "Kohezyon c (kPa)", 0, 1e6, 3), ("phi", "İçsel sürtünme açısı φ (°)", 0, 89.9, 3)]
HB_ROWS = [("sigma_ci", "Tek eksenli basınç dayanımı σci (kPa)", 1, 1e9, 1),
           ("gsi", "GSI", 1, 100, 1), ("mi", "mi", 0.1, 100, 2), ("d", "Örselenme faktörü D", 0, 1, 2)]
FORMULA = {"MC": "τ = c′ + σ′n · tan φ′",
           "HB": "σ1 = σ3 + σci (mb σ3/σci + s)^a   (genelleştirilmiş Hoek-Brown, 2002)"}


def _spin(lo, hi, dec, val):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setValue(val)
    s.setButtonSymbols(QDoubleSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight)
    return s


class MaterialsDialog(QDialog):
    def __init__(self, materials: list[MaterialSpec], parent=None, select: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Malzeme Özelliklerini Tanımla")
        self.resize(980, 700)
        self.mats = [copy.deepcopy(m) for m in materials] or [MaterialSpec()]
        self.renames: dict[str, str] = {}
        self._orig_names = [m.name for m in self.mats]
        self._loading = False
        self.cur = -1

        # ---------------------------------------------------------- left
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._select)
        tb = QHBoxLayout()
        for name, tip, slot in (("add", "Malzeme ekle", self._add),
                                ("delete", "Seçili malzemeyi sil", self._delete),
                                ("up", "Yukarı taşı", lambda: self._move(-1)),
                                ("down", "Aşağı taşı", lambda: self._move(1)),
                                ("copy", "Kopyala", self._copy)):
            b = QToolButton()
            b.setToolTip(tip)
            b.setText({"add": "+", "delete": "✕", "up": "▲", "down": "▼", "copy": "⧉"}[name])
            b.setStyleSheet("QToolButton{font-size:14px;min-width:26px;}")
            b.clicked.connect(slot)
            tb.addWidget(b)
        tb.addStretch(1)
        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        left.addLayout(tb)

        # --------------------------------------------------------- right
        self.title = QLabel()
        self.title.setStyleSheet(TITLE_CSS)
        self.name = QLineEdit()
        self.name.textEdited.connect(self._name_edited)
        self.color_btn = QToolButton()
        self.color_btn.setFixedWidth(90)
        self.color_btn.clicked.connect(self._pick_color)
        self.gamma = _spin(0.1, 100, 3, 19)
        self.use_sat = QCheckBox("Doygun birim hacim ağırlık (kN/m³):")
        self.gamma_sat = _spin(0.1, 100, 3, 20)
        self.use_sat.toggled.connect(self.gamma_sat.setEnabled)
        grid = QGridLayout()
        grid.addWidget(QLabel("Ad:"), 0, 0)
        grid.addWidget(self.name, 0, 1)
        grid.addWidget(QLabel("Dolgu:"), 0, 2)
        grid.addWidget(self.color_btn, 0, 3)
        grid.addWidget(QLabel("Birim hacim ağırlık (kN/m³):"), 1, 0)
        grid.addWidget(self.gamma, 1, 1)
        grid.addWidget(self.use_sat, 1, 2)
        grid.addWidget(self.gamma_sat, 1, 3)

        # strength tab
        strength = QWidget()
        sl = QVBoxLayout(strength)
        row = QHBoxLayout()
        row.addWidget(QLabel("Göçme kriteri:"))
        self.model = QComboBox()
        self.model.addItem("Mohr-Coulomb", "MC")
        self.model.addItem("Genelleştirilmiş Hoek-Brown", "HB")
        self.model.currentIndexChanged.connect(self._model_changed)
        row.addWidget(self.model, 1)
        self.formula = QLabel()
        self.formula.setStyleSheet("font-style:italic;font-size:13px;")
        row.addWidget(self.formula, 2)
        sl.addLayout(row)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Özellik", "Değer"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setStyleSheet(
            "QHeaderView::section{background:#3a3a3a;color:white;font-weight:bold;}")
        self.table.setStyleSheet("QTableWidget{background:#a8a8a8;}")
        sl.addWidget(self.table, 1)
        self.derived = QLabel()
        self.derived.setStyleSheet("color:#333;")
        sl.addWidget(self.derived)

        # water tab
        water = QWidget()
        wl = QFormLayout(water)
        self.use_water = QCheckBox("Su tablosu bu malzemeye etki eder")
        self.hu = _spin(0, 2, 3, 1.0)
        self.hu.setButtonSymbols(QDoubleSpinBox.UpDownArrows)
        wl.addRow(self.use_water)
        wl.addRow("Hu (piyezometrik yükseklik katsayısı):", self.hu)
        hint = QLabel("u = Hu · γw · h  (h: dilim tabanından su tablosuna düşey mesafe). "
                      "Hu = 1 hidrostatik; Hu < 1 akım nedeniyle azaltılmış basınç.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;")
        wl.addRow(hint)

        self.tabs = QTabWidget()
        self.tabs.addTab(strength, "Dayanım")
        self.tabs.addTab(water, "Su Parametreleri")

        note = QLabel("Not: Malzeme özellikleri tüm projede ortaktır. Bir malzeme silinirse, "
                      "ona atanmış bölgeler ilk malzemeye döner.")
        note.setStyleSheet("color:#b00000;font-weight:bold;")
        note.setWordWrap(True)

        right = QVBoxLayout()
        right.addWidget(self.title)
        right.addLayout(grid)
        right.addWidget(self.tabs, 1)
        right.addWidget(note)

        body = QHBoxLayout()
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(240)
        body.addWidget(lw)
        body.addLayout(right, 1)

        self.error = QLabel("")
        self.error.setStyleSheet("color:#b03a2e;")
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Tamam")
        btns.button(QDialogButtonBox.Cancel).setText("İptal")
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(self.error)
        lay.addWidget(btns)

        for w in (self.gamma, self.gamma_sat, self.hu):
            w.valueChanged.connect(self._store)
        self.use_sat.toggled.connect(self._store)
        self.use_water.toggled.connect(self._store)
        self.table.itemChanged.connect(self._store)

        self._refresh_list()
        idx = self._names().index(select) if select in self._names() else 0
        self.list.setCurrentRow(idx)

    # --------------------------------------------------------- helpers
    def _names(self):
        return [m.name for m in self.mats]

    def _refresh_list(self) -> None:
        cur = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for m in self.mats:
            it = QListWidgetItem(color_icon(m.color, 14), m.name)
            self.list.addItem(it)
        self.list.blockSignals(False)
        if 0 <= cur < len(self.mats):
            self.list.setCurrentRow(cur)

    def _select(self, row: int) -> None:
        if row < 0 or row >= len(self.mats):
            return
        self.cur = row
        m = self.mats[row]
        self._loading = True
        self.title.setText(m.name)
        self.name.setText(m.name)
        self.color_btn.setIcon(color_icon(m.color, 18))
        self.color_btn.setText("  ▾")
        self.color_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.gamma.setValue(m.gamma)
        self.use_sat.setChecked(m.use_sat)
        self.gamma_sat.setValue(m.gamma_sat)
        self.gamma_sat.setEnabled(m.use_sat)
        self.model.setCurrentIndex(0 if m.model == "MC" else 1)
        self.use_water.setChecked(m.use_water)
        self.hu.setValue(m.hu)
        self._fill_table(m)
        self._loading = False

    def _fill_table(self, m: MaterialSpec) -> None:
        rows = MC_ROWS if m.model == "MC" else HB_ROWS
        self.formula.setText(FORMULA[m.model])
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for r, (attr, label, lo, hi, dec) in enumerate(rows):
            it = QTableWidgetItem(label)
            it.setFlags(Qt.ItemIsEnabled)
            it.setBackground(QColor("white"))
            self.table.setItem(r, 0, it)
            v = QTableWidgetItem(f"{getattr(m, attr):g}")
            v.setData(Qt.UserRole, (attr, lo, hi))
            v.setBackground(QColor("white"))
            self.table.setItem(r, 1, v)
        self.table.blockSignals(False)
        self._update_derived(m)

    def _update_derived(self, m: MaterialSpec) -> None:
        if m.model == "HB":
            try:
                hb = HoekBrown(m.name, gamma=m.gamma, sigma_ci=m.sigma_ci, gsi=m.gsi, mi=m.mi,
                               d=m.d)
                self.derived.setText(f"Türetilen: mb = {hb.mb:.4f}   s = {hb.s:.5f}   "
                                     f"a = {hb.a:.4f}")
            except ValueError:
                self.derived.setText("")
        else:
            self.derived.setText("")

    def _store(self, *_) -> None:
        if self._loading or self.cur < 0:
            return
        m = self.mats[self.cur]
        m.gamma = self.gamma.value()
        m.use_sat = self.use_sat.isChecked()
        m.gamma_sat = self.gamma_sat.value()
        m.use_water = self.use_water.isChecked()
        m.hu = self.hu.value()
        self.error.setText("")
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            attr, lo, hi = item.data(Qt.UserRole)
            try:
                v = float(item.text().replace(",", "."))
            except ValueError:
                self.error.setText(f"⚠ '{self.table.item(r, 0).text()}' sayısal olmalı.")
                continue
            if not lo <= v <= hi:
                self.error.setText(f"⚠ '{self.table.item(r, 0).text()}' {lo:g} – {hi:g} "
                                   f"aralığında olmalı.")
                continue
            setattr(m, attr, v)
        self._update_derived(m)

    def _name_edited(self, text: str) -> None:
        if self.cur < 0:
            return
        m = self.mats[self.cur]
        old = m.name
        m.name = text
        self.title.setText(text)
        self.list.item(self.cur).setText(text)
        # track renames relative to the original names
        for orig, now in list(self.renames.items()):
            if now == old:
                self.renames[orig] = text
                break
        else:
            if old in self._orig_names:
                self.renames[old] = text

    def _model_changed(self, *_) -> None:
        if self._loading or self.cur < 0:
            return
        m = self.mats[self.cur]
        m.model = self.model.currentData()
        self._fill_table(m)

    def _pick_color(self) -> None:
        if self.cur < 0:
            return
        m = self.mats[self.cur]
        c = QColorDialog.getColor(QColor(m.color), self, "Dolgu rengi")
        if c.isValid():
            m.color = c.name()
            self.color_btn.setIcon(color_icon(m.color, 18))
            self.list.item(self.cur).setIcon(color_icon(m.color, 14))

    def _unique(self, base: str) -> str:
        names = set(self._names())
        if base not in names:
            return base
        i = 2
        while f"{base} ({i})" in names:
            i += 1
        return f"{base} ({i})"

    def _add(self) -> None:
        n = len(self.mats) + 1
        self.mats.append(MaterialSpec(name=self._unique(f"Malzeme {n}"),
                                      color=PALETTE[(n - 1) % len(PALETTE)]))
        self._refresh_list()
        self.list.setCurrentRow(len(self.mats) - 1)

    def _copy(self) -> None:
        if self.cur < 0:
            return
        m = copy.deepcopy(self.mats[self.cur])
        m.name = self._unique(m.name + " kopya")
        self.mats.insert(self.cur + 1, m)
        self._refresh_list()
        self.list.setCurrentRow(self.cur + 1)

    def _delete(self) -> None:
        if self.cur < 0 or len(self.mats) <= 1:
            self.error.setText("⚠ En az bir malzeme kalmalı.")
            return
        del self.mats[self.cur]
        self._refresh_list()
        self.list.setCurrentRow(min(self.cur, len(self.mats) - 1))

    def _move(self, d: int) -> None:
        i, j = self.cur, self.cur + d
        if i < 0 or not 0 <= j < len(self.mats):
            return
        self.mats[i], self.mats[j] = self.mats[j], self.mats[i]
        self._refresh_list()
        self.list.setCurrentRow(j)

    def _accept(self) -> None:
        names = self._names()
        if any(not n.strip() for n in names):
            self.error.setText("⚠ Malzeme adı boş olamaz.")
            return
        if len(set(names)) != len(names):
            self.error.setText("⚠ Malzeme adları benzersiz olmalı.")
            return
        if self.error.text():
            return
        self.accept()

    def result_materials(self) -> list[MaterialSpec]:
        return self.mats
