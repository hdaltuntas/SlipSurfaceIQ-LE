"""Define Material Properties dialog (Slide2 layout)."""

from __future__ import annotations

from slipsurface.ui.preferences import fit_to_screen


import copy

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
from slipsurface.materials.catalog import MODELS
from slipsurface.project import PALETTE, MaterialSpec
from slipsurface.ui.icons import color_icon, icon

TITLE_CSS = "color:#2a7ad0;font-size:16px;"

# (attribute, label, min, max, decimals) per model, from the shared catalogue
ROWS = {
    k: [(a, lab, lo, hi, dec) for a, lab, lo, hi, dec in info.rows] for k, info in MODELS.items()
}
FORMULA = {k: info.formula for k, info in MODELS.items()}
MC_ROWS, HB_ROWS = ROWS["MC"], ROWS["HB"]


def _spin(lo, hi, dec, val):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setValue(val)
    s.setButtonSymbols(QDoubleSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight)
    return s


class MaterialsDialog(QDialog):
    def __init__(
        self, materials: list[MaterialSpec], parent=None, select: str | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Define Material Properties")
        fit_to_screen(self, 980, 700)
        self.mats = [copy.deepcopy(m) for m in materials] or [MaterialSpec()]
        self.renames: dict[str, str] = {}
        self._orig_names = [m.name for m in self.mats]
        self._loading = False
        self.cur = -1

        # ---------------------------------------------------------- left
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._select)
        tb = QHBoxLayout()
        for name, tip, slot in (
            ("add", "Add Material", self._add),
            ("delete", "Delete Selected Material", self._delete),
            ("up", "Move Up", lambda: self._move(-1)),
            ("down", "Move Down", lambda: self._move(1)),
            ("copy", "Copy", self._copy),
        ):
            b = QToolButton()
            b.setToolTip(tip)
            b.setIcon(icon(name))
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
        self.use_sat = QCheckBox("Saturated Unit Weight (kN/m³):")
        self.gamma_sat = _spin(0.1, 100, 3, 20)
        self.use_sat.toggled.connect(self.gamma_sat.setEnabled)
        grid = QGridLayout()
        grid.addWidget(QLabel("Name:"), 0, 0)
        grid.addWidget(self.name, 0, 1)
        grid.addWidget(QLabel("Fill:"), 0, 2)
        grid.addWidget(self.color_btn, 0, 3)
        grid.addWidget(QLabel("Unit Weight (kN/m³):"), 1, 0)
        grid.addWidget(self.gamma, 1, 1)
        grid.addWidget(self.use_sat, 1, 2)
        grid.addWidget(self.gamma_sat, 1, 3)

        # strength tab
        strength = QWidget()
        sl = QVBoxLayout(strength)
        row = QHBoxLayout()
        row.addWidget(QLabel("Failure Criterion:"))
        self.model = QComboBox()
        for key, info in MODELS.items():
            self.model.addItem(info.name, key)
        self.model.currentIndexChanged.connect(self._model_changed)
        row.addWidget(self.model, 1)
        self.formula = QLabel()
        self.formula.setStyleSheet("font-style:italic;font-size:13px;")
        row.addWidget(self.formula, 2)
        sl.addLayout(row)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Property", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setStyleSheet(
            "QHeaderView::section{background:#3a3a3a;color:white;font-weight:bold;}"
        )

        sl.addWidget(self.table, 1)
        self.derived = QLabel()
        sl.addWidget(self.derived)

        # water tab
        water = QWidget()
        wl = QFormLayout(water)
        self.use_water = QCheckBox("Apply Water Table to This Material")
        self.hu = _spin(0, 2, 3, 1.0)
        self.hu.setButtonSymbols(QDoubleSpinBox.UpDownArrows)
        wl.addRow(self.use_water)
        wl.addRow("Hu (Piezometric Head Factor):", self.hu)
        hint = QLabel(
            "u = Hu · γw · h  (h: vertical distance from the slice base to the water table). Hu = 1 hydrostatic; Hu < 1 pressure reduced by seepage."
        )
        hint.setWordWrap(True)
        wl.addRow(hint)

        self.tabs = QTabWidget()
        self.tabs.addTab(strength, "Strength")
        self.tabs.addTab(water, "Water Parameters")

        note = QLabel(
            "Note: material properties are shared by the whole project. Deleting a material reassigns its regions to the first material."
        )
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
        btns.button(QDialogButtonBox.Ok).setText("OK")
        btns.button(QDialogButtonBox.Cancel).setText("Cancel")
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
        self.model.setCurrentIndex(self.model.findData(m.model))
        self.use_water.setChecked(m.use_water)
        self.use_water.setEnabled(m.model != "UD")
        self.hu.setEnabled(m.model != "UD")
        self.hu.setValue(m.hu)
        self._fill_table(m)
        self._loading = False

    def _fill_table(self, m: MaterialSpec) -> None:
        rows = ROWS[m.model]
        self.formula.setText(FORMULA[m.model])
        self.formula.setToolTip(MODELS[m.model].note)
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        for r, (attr, label, lo, hi, _dec) in enumerate(rows):
            it = QTableWidgetItem(label)
            it.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 0, it)
            v = QTableWidgetItem(f"{getattr(m, attr):g}")
            v.setData(Qt.UserRole, (attr, lo, hi))
            self.table.setItem(r, 1, v)
        self.table.blockSignals(False)
        self._update_derived(m)

    def _update_derived(self, m: MaterialSpec) -> None:
        if m.model == "HB":
            try:
                hb = HoekBrown(
                    m.name, gamma=m.gamma, sigma_ci=m.sigma_ci, gsi=m.gsi, mi=m.mi, d=m.d
                )
                self.derived.setText(f"Derived: mb = {hb.mb:.4f}   s = {hb.s:.5f}   a = {hb.a:.4f}")
            except ValueError:
                self.derived.setText("")
        elif m.model == "BB":
            try:
                bb = m.to_material()
                self.derived.setText(f"JRCn = {bb.jrc_n:.3f}   JCSn = {bb.jcs_n:.1f} kPa")
            except ValueError:
                self.derived.setText("")
        else:
            self.derived.setText(MODELS[m.model].note)
        self.derived.setWordWrap(True)

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
                self.error.setText(f"⚠ '{self.table.item(r, 0).text()}' must be numeric.")
                continue
            if not lo <= v <= hi:
                self.error.setText(
                    f"⚠ '{self.table.item(r, 0).text()}' must be between {lo:g} and {hi:g}."
                )
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
        self._loading = True
        if m.model == "UD":
            m.use_water = False
        elif m.model == "SH":
            m.use_water = True  # σ′v needs the water table
        self.use_water.setChecked(m.use_water)
        self.use_water.setEnabled(m.model != "UD")
        self.hu.setEnabled(m.model != "UD")
        self._loading = False
        self._fill_table(m)

    def _pick_color(self) -> None:
        if self.cur < 0:
            return
        m = self.mats[self.cur]
        c = QColorDialog.getColor(QColor(m.color), self, "Fill Color")
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
        self.mats.append(
            MaterialSpec(name=self._unique(f"Material {n}"), color=PALETTE[(n - 1) % len(PALETTE)])
        )
        self._refresh_list()
        self.list.setCurrentRow(len(self.mats) - 1)

    def _copy(self) -> None:
        if self.cur < 0:
            return
        m = copy.deepcopy(self.mats[self.cur])
        m.name = self._unique(m.name + " copy")
        self.mats.insert(self.cur + 1, m)
        self._refresh_list()
        self.list.setCurrentRow(self.cur + 1)

    def _delete(self) -> None:
        if self.cur < 0 or len(self.mats) <= 1:
            self.error.setText("⚠ At least one material must remain.")
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
            self.error.setText("⚠ Material name must not be empty.")
            return
        if len(set(names)) != len(names):
            self.error.setText("⚠ Material names must be unique.")
            return
        if self.error.text():
            return
        self.accept()

    def result_materials(self) -> list[MaterialSpec]:
        return self.mats
