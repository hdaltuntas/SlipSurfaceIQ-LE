"""Project Settings dialog (Slide2 layout: page list on the left)."""

from __future__ import annotations

from slipsurface.ui.preferences import fit_to_screen


from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from slipsurface.lem import METHODS
from slipsurface.project import (
    AdvancedSettings,
    GeneralSettings,
    GroundwaterSettings,
    MethodSettings,
    Project,
    SEISMIC_NOTE,
    SeismicSettings,
)

TITLE_CSS = "color:#2a7ad0;font-size:16px;"
INTERSLICE = [
    ("half-sine", "Half Sine"),
    ("constant", "Constant (Equivalent to Spencer)"),
    ("clipped-sine", "Clipped Sine"),
    ("trapezoidal", "Trapezoidal"),
]
# Slide2 order of the method check boxes
METHOD_ORDER = [
    "bishop",
    "corps1",
    "corps2",
    "gle",
    "janbu_simplified",
    "janbu_corrected",
    "lowe_karafiath",
    "ordinary",
    "spencer",
]


def _dspin(lo, hi, dec, step, val, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    return s


def _direction_pixmap(left: bool) -> QPixmap:
    pm = QPixmap(46, 30)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pts = (
        [(2, 22), (14, 22), (30, 8), (44, 8), (44, 22)]
        if left
        else [(2, 8), (16, 8), (32, 22), (44, 22), (44, 22)]
    )
    p.setPen(QPen(QColor("#555"), 1.5))
    p.setBrush(QColor("#c8c8c8"))
    p.drawPolygon(QPolygonF([QPointF(*q) for q in pts] + [QPointF(44, 26), QPointF(2, 26)]))
    p.setPen(QPen(QColor("#d4b000"), 2))
    if left:
        p.drawLine(QPointF(14, 22), QPointF(32, 8))
    else:
        p.drawLine(QPointF(14, 8), QPointF(32, 22))
    p.setPen(QPen(QColor("black"), 2))
    y = 28
    if left:
        p.drawLine(QPointF(10, y), QPointF(34, y))
        p.drawLine(QPointF(10, y), QPointF(15, y - 3))
    else:
        p.drawLine(QPointF(10, y), QPointF(34, y))
        p.drawLine(QPointF(34, y), QPointF(29, y - 3))
    p.end()
    return pm


class ProjectSettingsDialog(QDialog):
    PAGES = ["General", "Methods", "Groundwater", "Seismic", "Advanced"]

    def __init__(self, project: Project, parent=None, page: int = 0) -> None:
        super().__init__(parent)
        self.setWindowTitle("Project Settings")
        fit_to_screen(self, 760, 560)
        self.p = project.copy()

        self.nav = QListWidget()
        self.nav.addItems(self.PAGES)
        self.nav.setFixedWidth(160)
        self.stack = QStackedWidget()
        for build in (
            self._page_general,
            self._page_methods,
            self._page_groundwater,
            self._page_seismic,
            self._page_advanced,
        ):
            self.stack.addWidget(build())
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(page)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("OK")
        btns.button(QDialogButtonBox.Cancel).setText("Cancel")
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        defaults = QPushButton("Defaults…")
        defaults.clicked.connect(self._defaults)

        top = QHBoxLayout()
        top.addWidget(self.nav)
        top.addWidget(self.stack, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(defaults)
        bottom.addStretch(1)
        bottom.addWidget(btns)
        lay = QVBoxLayout(self)
        lay.addLayout(top, 1)
        lay.addLayout(bottom)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#b03a2e;")
        lay.insertWidget(1, self.error)

    # ------------------------------------------------------------- pages
    def _page(self, title):
        w = QWidget()
        lay = QVBoxLayout(w)
        t = QLabel(title)
        t.setStyleSheet(TITLE_CSS)
        lay.addWidget(t)
        return w, lay

    def _page_general(self):
        w, lay = self._page("General")
        g = self.p.general
        units = QGroupBox("Units")
        f = QFormLayout(units)
        self.units = QComboBox()
        self.units.addItem("Metric (kN, kPa, m)", "metric")
        f.addRow("Stress units:", self.units)
        lay.addWidget(units)

        row = QHBoxLayout()
        dirbox = QGroupBox("Failure Direction")
        gl = QGridLayout(dirbox)
        self.rtl = QRadioButton("Right to left")
        self.ltr = QRadioButton("Left to right")
        self.dir_group = QButtonGroup(self)
        self.dir_group.addButton(self.rtl)
        self.dir_group.addButton(self.ltr)
        (self.rtl if g.failure_direction == "right_to_left" else self.ltr).setChecked(True)
        i1, i2 = QLabel(), QLabel()
        i1.setPixmap(_direction_pixmap(True))
        i2.setPixmap(_direction_pixmap(False))
        gl.addWidget(self.rtl, 0, 0)
        gl.addWidget(i1, 0, 1)
        gl.addWidget(self.ltr, 1, 0)
        gl.addWidget(i2, 1, 1)
        out = QGroupBox("Data Output")
        ol = QVBoxLayout(out)
        self.out_std = QRadioButton("Standart")
        self.out_max = QRadioButton("Maximum (Slice Tables in Report)")
        (self.out_std if g.data_output == "standard" else self.out_max).setChecked(True)
        ol.addWidget(self.out_std)
        ol.addWidget(self.out_max)
        row.addWidget(dirbox)
        row.addWidget(out)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _page_methods(self):
        w, lay = self._page("Methods")
        m = self.p.methods
        row = QHBoxLayout()
        left = QVBoxLayout()
        self.vertical = QRadioButton("Vertical Slices")
        self.vertical.setChecked(True)
        sarma_ns = QRadioButton("Sarma Nonvertical Slices")
        sarma_ns.setEnabled(False)
        sarma_ns.setToolTip("Not supported in this version.")
        left.addWidget(self.vertical)
        left.addWidget(sarma_ns)
        box = QGroupBox("Methods")
        bl = QVBoxLayout(box)
        self.method_checks: dict[str, QCheckBox] = {}
        for key in METHOD_ORDER:
            cb = QCheckBox(METHODS[key][1])
            cb.setChecked(key in m.methods)
            self.method_checks[key] = cb
            bl.addWidget(cb)
        sarma = QCheckBox("Sarma")
        sarma.setEnabled(False)
        sarma.setToolTip("Not supported in this version.")
        bl.addWidget(sarma)
        left.addWidget(box)
        left.addStretch(1)

        right = QVBoxLayout()
        conv = QGroupBox("Convergence Options")
        cf = QFormLayout(conv)
        self.n_slices = QSpinBox()
        self.n_slices.setRange(5, 500)
        self.n_slices.setValue(m.n_slices)
        self.tol = _dspin(1e-6, 0.1, 6, 0.001, m.tolerance)
        self.tol.setToolTip(
            "Relative convergence tolerance. The solver uses this number as entered."
        )
        self.max_iter = QSpinBox()
        self.max_iter.setRange(5, 1000)
        self.max_iter.setValue(m.max_iter)
        cf.addRow("Number of Slices:", self.n_slices)
        cf.addRow("Tolerance:", self.tol)
        cf.addRow("Maximum iterations:", self.max_iter)
        right.addWidget(conv)
        inter = QGroupBox("Interslice Force Function (GLE/Morgenstern-Price)")
        il = QFormLayout(inter)
        self.interslice = QComboBox()
        for k, label in INTERSLICE:
            self.interslice.addItem(label, k)
        self.interslice.setCurrentIndex(
            max(
                0,
                [k for k, _ in INTERSLICE].index(m.interslice)
                if m.interslice in dict(INTERSLICE)
                else 0,
            )
        )
        self.f_start = _dspin(0, 1, 3, 0.05, m.f_start)
        self.f_end = _dspin(0, 1, 3, 0.05, m.f_end)
        il.addRow("Function:", self.interslice)
        il.addRow("Start Value:", self.f_start)
        il.addRow("End Value:", self.f_end)
        self.inter_box = inter
        right.addWidget(inter)
        right.addStretch(1)
        self.method_checks["gle"].toggled.connect(self._update_interslice)
        self.interslice.currentIndexChanged.connect(self._update_interslice)
        self._update_interslice()

        row.addLayout(left, 1)
        row.addLayout(right, 1)
        lay.addLayout(row)
        return w

    def _update_interslice(self, *_):
        on = self.method_checks["gle"].isChecked()
        self.inter_box.setEnabled(on)
        clipped = self.interslice.currentData() == "clipped-sine"
        self.f_start.setEnabled(on and clipped)
        self.f_end.setEnabled(on and clipped)

    def _page_groundwater(self):
        w, lay = self._page("Groundwater")
        gw = self.p.groundwater
        box = QGroupBox("Pore Water Pressure")
        f = QFormLayout(box)
        self.gw_method = QComboBox()
        self.gw_method.addItem("Water table (phreatic)", "water_table")
        self.gw_method.addItem("Ru Coefficient", "ru")
        self.gw_method.addItem("Dry (No Pore Water)", "none")
        self.gw_method.setCurrentIndex(["water_table", "ru", "none"].index(gw.method))
        self.gamma_w = _dspin(1, 20, 3, 0.01, gw.gamma_w, " kN/m³")
        self.ru = _dspin(0, 1, 3, 0.05, gw.ru)
        f.addRow("Method:", self.gw_method)
        f.addRow("Water Unit Weight γw:", self.gamma_w)
        f.addRow("Ru:", self.ru)
        lay.addWidget(box)
        cbox = QGroupBox("Tension Crack Water")
        cf = QFormLayout(cbox)
        self.crack_mode = QComboBox()
        self.crack_mode.addItem("Dry", "dry")
        self.crack_mode.addItem("Full", "full")
        self.crack_mode.addItem("Partially Filled (%)", "percent")
        cw = gw.crack_water
        self.crack_mode.setCurrentIndex(0 if cw == 0 else 1 if cw == 1 else 2)
        self.crack_pct = _dspin(0, 100, 1, 5, 100 * cw, " %")
        self.crack_mode.currentIndexChanged.connect(self._crack_mode_changed)
        cf.addRow("Crack Water:", self.crack_mode)
        cf.addRow("Fill level:", self.crack_pct)
        lay.addWidget(cbox)
        self._crack_mode_changed()
        note = QLabel(
            "Water table: u = Hu · γw · (water table elevation − base elevation); Hu and whether water acts are set per material in Material Properties → Water Parameters."
            + "\n"
            + "Ru: u = Ru · σv (total vertical stress at the slice base)."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        lay.addWidget(note)
        self.gw_method.currentIndexChanged.connect(
            lambda: self.ru.setEnabled(self.gw_method.currentData() == "ru")
        )
        self.ru.setEnabled(gw.method == "ru")
        lay.addStretch(1)
        return w

    def _crack_mode_changed(self, *_):
        mode = self.crack_mode.currentData()
        self.crack_pct.setEnabled(mode == "percent")
        if mode == "dry":
            self.crack_pct.setValue(0)
        elif mode == "full":
            self.crack_pct.setValue(100)

    def _page_seismic(self):
        w, lay = self._page("Seismic")
        s = self.p.seismic
        box = QGroupBox("Pseudo-static Seismic Coefficients")
        f = QFormLayout(box)
        self.kh = _dspin(0, 1, 4, 0.01, max(s.kh, 0.0))
        self.kh.setToolTip("kh always acts in the failure direction.")
        self.kv = _dspin(-1, 1, 4, 0.01, s.kv)
        f.addRow("Horizontal Coefficient kh:", self.kh)
        f.addRow("Vertical Coefficient kv:", self.kv)
        self.both_kv = QCheckBox("Check both vertical directions and use the critical one")
        self.both_kv.setChecked(s.both_vertical)
        self.both_kv.setToolTip(
            "kv and -kv are solved separately; the lower FS is kept. No second solution is run when kv = 0."
        )
        f.addRow(self.both_kv)
        lay.addWidget(box)
        note = QLabel(SEISMIC_NOTE)
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        lay.addWidget(note)
        lay.addStretch(1)
        return w

    def _page_advanced(self):
        w, lay = self._page("Advanced")
        a = self.p.advanced
        box = QGroupBox("Solution Checks")
        v = QVBoxLayout(box)
        self.check_adm = QCheckBox(
            "Reject surfaces with mα below threshold or negative base shear resistance"
        )
        self.check_adm.setChecked(a.check_admissibility)
        v.addWidget(self.check_adm)
        f = QFormLayout()
        self.m_alpha_min = _dspin(0.05, 1.0, 2, 0.05, a.m_alpha_min)
        self.e_max_ratio = _dspin(1, 1000, 0, 5, a.e_max_ratio)
        self.min_depth = _dspin(0, 1000, 3, 0.5, a.min_depth, " m")
        f.addRow("mα Threshold (Default 0.2):", self.m_alpha_min)
        f.addRow("Maximum Interslice Force Ratio (E/W):", self.e_max_ratio)
        f.addRow("Minimum Slip Depth:", self.min_depth)
        v.addLayout(f)
        lay.addWidget(box)
        note = QLabel(
            "If the mα check (Whitman & Bailey 1967) is switched off or its threshold lowered, numerically unreliable low FS values can be found on surfaces with steep negative base angles at the toe. The interslice force ratio caps the forces relative to the total weight to reject singular solutions."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        lay.addWidget(note)
        lay.addStretch(1)
        return w

    # ---------------------------------------------------------- result
    def collect(self) -> Project:
        p = self.p.copy()
        p.general.units = self.units.currentData()
        p.general.failure_direction = "right_to_left" if self.rtl.isChecked() else "left_to_right"
        p.general.data_output = "standard" if self.out_std.isChecked() else "maximum"
        p.methods.methods = [k for k in METHOD_ORDER if self.method_checks[k].isChecked()]
        p.methods.n_slices = self.n_slices.value()
        p.methods.tolerance = self.tol.value()
        p.methods.max_iter = self.max_iter.value()
        p.methods.interslice = self.interslice.currentData()
        p.methods.f_start = self.f_start.value()
        p.methods.f_end = self.f_end.value()
        p.groundwater.method = self.gw_method.currentData()
        p.groundwater.gamma_w = self.gamma_w.value()
        p.groundwater.ru = self.ru.value()
        p.groundwater.crack_water = self.crack_pct.value() / 100.0
        p.seismic.kh = self.kh.value()
        p.seismic.kv = self.kv.value()
        p.seismic.both_vertical = self.both_kv.isChecked()
        p.advanced.check_admissibility = self.check_adm.isChecked()
        p.advanced.min_depth = self.min_depth.value()
        p.advanced.m_alpha_min = self.m_alpha_min.value()
        p.advanced.e_max_ratio = self.e_max_ratio.value()
        return p

    def _accept(self) -> None:
        p = self.collect()
        if not p.methods.methods:
            self.error.setText("Select at least one method.")
            self.nav.setCurrentRow(1)
            return
        self.result_project = p
        self.accept()

    def _defaults(self) -> None:
        self.p.general = GeneralSettings()
        self.p.methods = MethodSettings()
        self.p.groundwater = GroundwaterSettings()
        self.p.seismic = SeismicSettings()
        self.p.advanced = AdvancedSettings()
        page = self.nav.currentRow()
        # rebuild pages with defaults
        while self.stack.count():
            wdg = self.stack.widget(0)
            self.stack.removeWidget(wdg)
            wdg.deleteLater()
        for build in (
            self._page_general,
            self._page_methods,
            self._page_groundwater,
            self._page_seismic,
            self._page_advanced,
        ):
            self.stack.addWidget(build())
        self.stack.setCurrentIndex(page)
