"""Surface Options dialog."""

from __future__ import annotations

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
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

from slipsurface.project import EFFORT, Project, SurfaceSettings

SEARCH = {
    "circular": ("Otomatik iyileştirmeli arama (Diferansiyel Evrim + Nelder-Mead)", "auto_refine"),
    "noncircular": ("Yol araması + optimizasyon (DE + Nelder-Mead)", "path_search"),
    "user": ("— (kullanıcı tanımlı yüzey analiz edilir)", "none"),
}
EFFORT_LABELS = [("fast", "Hızlı"), ("normal", "Normal"), ("fine", "Hassas")]


class SurfaceOptionsDialog(QDialog):
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yüzey Seçenekleri")
        self.resize(560, 470)
        s = project.surfaces
        self.p = project

        grid = QGridLayout()
        grid.addWidget(QLabel("Yüzey tipi:"), 0, 0)
        self.r_circ = QRadioButton("Dairesel")
        self.r_non = QRadioButton("Dairesel olmayan (poligonal / B-spline)")
        self.r_user = QRadioButton("Kullanıcı tanımlı")
        self.type_group = QButtonGroup(self)
        for i, rb in enumerate((self.r_circ, self.r_non, self.r_user)):
            self.type_group.addButton(rb, i)
            grid.addWidget(rb, i, 1)
        {"circular": self.r_circ, "noncircular": self.r_non, "user": self.r_user}[
            s.surface_type].setChecked(True)
        if not s.user_surface:
            self.r_user.setToolTip("Önce Yüzeyler → Kullanıcı Yüzeyi Çiz ile bir yüzey çizin.")

        grid.addWidget(QLabel("Arama yöntemi:"), 3, 0)
        self.search = QComboBox()
        grid.addWidget(self.search, 3, 1)
        self.opt_btn = QPushButton("▾  Seçenekler")
        self.opt_btn.setCheckable(True)
        grid.addWidget(self.opt_btn, 3, 2)

        self.opts = QGroupBox("Arama seçenekleri")
        f = QFormLayout(self.opts)
        self.effort = QComboBox()
        for k, label in EFFORT_LABELS:
            pop, it = EFFORT[k]
            self.effort.addItem(f"{label}  (popülasyon {pop}×boyut, {it} nesil)", k)
        self.effort.setCurrentIndex([k for k, _ in EFFORT_LABELS].index(s.effort))
        self.seed = QSpinBox()
        self.seed.setRange(0, 10_000)
        self.seed.setValue(s.seed)
        self.n_ctrl = QSpinBox()
        self.n_ctrl.setRange(2, 10)
        self.n_ctrl.setValue(s.n_ctrl)
        self.shape = QComboBox()
        self.shape.addItem("Poligonal — doğru parçaları (Slide2)", "polyline")
        self.shape.addItem("Yumuşak eğri (B-spline)", "spline")
        self.shape.setCurrentIndex(max(0, self.shape.findData(s.noncircular_shape)))
        self.convex = QCheckBox("Yalnızca konveks yüzeyler")
        self.convex.setChecked(s.convex_only)
        f.addRow("Arama yoğunluğu:", self.effort)
        f.addRow("Rastgele tohum:", self.seed)
        f.addRow("Dairesel olmayan yüzey biçimi:", self.shape)
        f.addRow("Ara köşe / kontrol noktası sayısı:", self.n_ctrl)
        f.addRow(self.convex)
        self.opts.setVisible(False)
        self.opt_btn.toggled.connect(self.opts.setVisible)

        typeopts = QGroupBox("Yüzey tipi seçenekleri")
        tl = QVBoxLayout(typeopts)
        comp = QCheckBox("Kompozit yüzeyler")
        comp.setEnabled(False)
        comp.setToolTip("Bu sürümde desteklenmiyor.")
        tl.addWidget(comp)
        weak = QComboBox()
        weak.addItem("Otomatik durum üretimi")
        weak.setEnabled(False)
        wrow = QHBoxLayout()
        wl = QLabel("Zayıf tabaka işleme:")
        wl.setEnabled(False)
        wrow.addWidget(wl)
        wrow.addWidget(weak, 1)
        tl.addLayout(wrow)

        lim = QGroupBox("Kayma sınırları (slope limits)")
        lf = QGridLayout(lim)
        self.use_limits = QCheckBox("Kayma sınırlarını kullan")
        self.use_limits.setChecked(bool(s.left_range or s.right_range))
        lf.addWidget(self.use_limits, 0, 0, 1, 4)
        g = project
        xs = [q[0] for q in g.external] or [0, 1]
        x0, x1 = min(xs), max(xs)
        L = s.left_range or [x0, x0 + 0.35 * (x1 - x0)]
        R = s.right_range or [x0 + 0.5 * (x1 - x0), x1]
        self.l0, self.l1, self.r0, self.r1 = (self._x(v, x0, x1) for v in (*L, *R))
        lf.addWidget(QLabel("Sol uç aralığı x:"), 1, 0)
        lf.addWidget(self.l0, 1, 1)
        lf.addWidget(QLabel("–"), 1, 2)
        lf.addWidget(self.l1, 1, 3)
        lf.addWidget(QLabel("Sağ uç aralığı x:"), 2, 0)
        lf.addWidget(self.r0, 2, 1)
        lf.addWidget(QLabel("–"), 2, 2)
        lf.addWidget(self.r1, 2, 3)
        self.use_limits.toggled.connect(self._limits_enabled)
        self._limits_enabled(self.use_limits.isChecked())

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#b03a2e;")
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Tamam")
        btns.button(QDialogButtonBox.Cancel).setText("İptal")
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        defaults = QPushButton("Varsayılanlar…")
        defaults.clicked.connect(self._defaults)
        bottom = QHBoxLayout()
        bottom.addWidget(defaults)
        bottom.addStretch(1)
        bottom.addWidget(btns)

        lay = QVBoxLayout(self)
        lay.addLayout(grid)
        lay.addWidget(self.opts)
        lay.addWidget(typeopts)
        lay.addWidget(lim)
        lay.addStretch(1)
        lay.addWidget(self.error)
        lay.addLayout(bottom)

        self.type_group.idToggled.connect(lambda *_: self._update_search())
        self._update_search()

    @staticmethod
    def _x(v, lo, hi):
        sp = QDoubleSpinBox()
        sp.setRange(lo - 1e4, hi + 1e4)
        sp.setDecimals(3)
        sp.setValue(v)
        return sp

    def _limits_enabled(self, on: bool) -> None:
        for w in (self.l0, self.l1, self.r0, self.r1):
            w.setEnabled(on and self._type() != "user")

    def _type(self) -> str:
        return ["circular", "noncircular", "user"][self.type_group.checkedId()]

    def _update_search(self) -> None:
        t = self._type()
        self.search.clear()
        label, key = SEARCH[t]
        self.search.addItem(label, key)
        self.n_ctrl.setEnabled(t == "noncircular")
        self.shape.setEnabled(t == "noncircular")
        self.convex.setEnabled(t == "noncircular")
        self.search.setEnabled(t != "user")
        self.opt_btn.setEnabled(t != "user")
        self.opts.setEnabled(t != "user")
        self.use_limits.setEnabled(t != "user")
        self._limits_enabled(self.use_limits.isChecked())

    def _defaults(self) -> None:
        d = SurfaceSettings()
        self.r_circ.setChecked(True)
        self.effort.setCurrentIndex(1)
        self.seed.setValue(d.seed)
        self.n_ctrl.setValue(d.n_ctrl)
        self.shape.setCurrentIndex(0)
        self.convex.setChecked(d.convex_only)
        self.use_limits.setChecked(False)

    def _accept(self) -> None:
        if self._type() == "user" and not self.p.surfaces.user_surface:
            self.error.setText("⚠ Kullanıcı tanımlı yüzey yok. Önce Yüzeyler → Kullanıcı Yüzeyi "
                               "Çiz ile çizin.")
            return
        if self._type() != "user" and self.use_limits.isChecked():
            if self.l1.value() <= self.l0.value() or self.r1.value() <= self.r0.value():
                self.error.setText("⚠ Aralık bitişi başlangıçtan büyük olmalı.")
                return
            xs = [q[0] for q in self.p.external]
            if xs:
                lo, hi = min(xs), max(xs)
                for start, end in ((self.l0.value(), self.l1.value()),
                                   (self.r0.value(), self.r1.value())):
                    if min(end, hi) <= max(start, lo):
                        self.error.setText("⚠ Her uç aralığı modelin yatay sınırlarıyla "
                                           f"kesişmeli ({lo:g} – {hi:g} m).")
                        return
        self.accept()

    def apply_to(self, p: Project) -> None:
        s = p.surfaces
        s.surface_type = self._type()
        s.search = self.search.currentData()
        s.effort = self.effort.currentData()
        s.seed = self.seed.value()
        s.n_ctrl = self.n_ctrl.value()
        s.noncircular_shape = self.shape.currentData()
        s.convex_only = self.convex.isChecked()
        if self.use_limits.isChecked():
            s.left_range = [self.l0.value(), self.l1.value()]
            s.right_range = [self.r0.value(), self.r1.value()]
        else:
            s.left_range = s.right_range = None
