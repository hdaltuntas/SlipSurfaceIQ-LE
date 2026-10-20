"""Load and support dialogs: Distributed / Line load, Define Support Properties,
Support edit."""

from __future__ import annotations

from slipsurface.ui.preferences import fit_to_screen

from slipsurface.ui.i18n import tr

import copy

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QToolButton,
    QVBoxLayout,
)

from slipsurface.loads import ANCHORAGES, SUPPORT_KINDS, SupportType
from slipsurface.ui.icons import color_icon

TITLE_CSS = "color:#2a7ad0;font-size:16px;"


def _spin(lo, hi, dec, val, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    return s


def _buttons(dlg, ok=None):
    b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    b.button(QDialogButtonBox.Ok).setText(tr("Tamam"))
    b.button(QDialogButtonBox.Cancel).setText(tr("İptal"))
    b.accepted.connect(ok or dlg.accept)
    b.rejected.connect(dlg.reject)
    return b


# ================================================================= loads
class DistributedLoadDialog(QDialog):
    def __init__(self, load: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Yayılı Yük"))
        (x1, _), (x2, _) = load["points"]
        q1, q2 = load["q"]
        self.x1 = _spin(-1e6, 1e6, 3, x1, " m")
        self.x2 = _spin(-1e6, 1e6, 3, x2, " m")
        self.q1 = _spin(-1e6, 1e6, 3, q1, " kPa")
        self.q2 = _spin(-1e6, 1e6, 3, q2, " kPa")
        self.r_uniform = QRadioButton(tr("Üniform (q1 = q2)"))
        self.r_tri = QRadioButton(tr("Doğrusal değişen (üçgen / trapez)"))
        grp = QButtonGroup(self)
        grp.addButton(self.r_uniform)
        grp.addButton(self.r_tri)
        (self.r_uniform if q1 == q2 else self.r_tri).setChecked(True)
        self.r_uniform.toggled.connect(self._shape)
        self.q1.valueChanged.connect(self._shape)
        self.orient = QComboBox()
        self.orient.addItem(tr("Düşey (q, yatay metre başına)"), "vertical")
        self.orient.addItem(tr("Yüzeye dik (q, sınır uzunluğu başına)"), "normal")
        self.orient.setCurrentIndex(0 if load.get("orientation", "vertical") == "vertical" else 1)
        f = QFormLayout()
        f.addRow(tr("Başlangıç x₁:"), self.x1)
        f.addRow(tr("Bitiş x₂:"), self.x2)
        f.addRow(self.r_uniform)
        f.addRow(self.r_tri)
        f.addRow("Büyüklük q₁:", self.q1)
        f.addRow("Büyüklük q₂:", self.q2)
        f.addRow(tr("Yön:"), self.orient)
        note = QLabel("Pozitif q zemine doğru (basınç) etkir. Yük, x₁–x₂ arasında zemin "
                      "yüzeyine uygulanır.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(note)
        lay.addWidget(_buttons(self))
        self._shape()

    def _shape(self, *_):
        uni = self.r_uniform.isChecked()
        self.q2.setEnabled(not uni)
        if uni:
            self.q2.setValue(self.q1.value())

    def apply_to(self, load: dict, ground_y=None) -> None:
        x1, x2 = self.x1.value(), self.x2.value()
        y1 = float(ground_y(x1)) if ground_y else load["points"][0][1]
        y2 = float(ground_y(x2)) if ground_y else load["points"][1][1]
        load["points"] = [[x1, y1], [x2, y2]]
        load["q"] = [self.q1.value(), self.q2.value()]
        load["orientation"] = self.orient.currentData()


class LineLoadDialog(QDialog):
    def __init__(self, load: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Tekil (Çizgisel) Yük"))
        x, y = load["point"]
        self.x = _spin(-1e6, 1e6, 3, x, " m")
        self.mag = _spin(-1e6, 1e6, 3, load.get("magnitude", 50.0), " kN/m")
        self.angle = _spin(-360, 360, 2, load.get("angle", 270.0), " °")
        f = QFormLayout()
        f.addRow("Konum x:", self.x)
        f.addRow(tr("Büyüklük P:"), self.mag)
        f.addRow(tr("Kuvvet açısı:"), self.angle)
        note = QLabel("Açı +x ekseninden saat yönünün tersine ölçülür: 270° = düşey aşağı, "
                      "180° = sola (sağdan sola göçmede itici). Nokta zemin yüzeyine oturtulur.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(note)
        lay.addWidget(_buttons(self))

    def apply_to(self, load: dict, ground_y=None) -> None:
        x = self.x.value()
        y = float(ground_y(x)) if ground_y else load["point"][1]
        load["point"] = [x, y]
        load["magnitude"] = self.mag.value()
        load["angle"] = self.angle.value()


# ============================================================== supports
FORMULAS = {
    "end_anchored": "T = çekme kapasitesi  (kayma yüzeyini kestiği sürece sabit)",
    "grouted_tieback": "T = min(çekme, kök dayanımı × min(kök boyu, L_dış))",
    "soil_nail": "T = min(çekme, kök dayanımı × L_dış, plaka + kök dayanımı × L_iç)",
    "geotextile": "T = min(çekme dayanımı, sıyrılma dayanımı × min(L_iç, L_dış))",
    "geosynthetic": "T = min(C·çekme, P_iç, P_dış);  P = 2·C·∫(adezyon + σv·tan δ) ds,  "
                    "σv = γ·derinlik (ankrajlı uçta sıyrılma yok)",
    "micro_pile": "T = kazık kesme dayanımı / aralık  (kayma yüzeyini kestiği noktada)",
}
FIELDS = {   # which inputs apply to which kind
    "spacing": {"end_anchored", "grouted_tieback", "soil_nail", "micro_pile"},
    "tensile": {"end_anchored", "grouted_tieback", "soil_nail", "geotextile", "geosynthetic"},
    "plate": {"soil_nail"},
    "bond_strength": {"grouted_tieback", "soil_nail"},
    "bond_length": {"grouted_tieback"},
    "pullout": {"geotextile"},
    "coverage": {"geosynthetic"},
    "anchorage": {"geosynthetic"},
    "adhesion": {"geosynthetic"},
    "interface_friction": {"geosynthetic"},
    "overburden_gamma": {"geosynthetic"},
    "pile_shear": {"micro_pile"},
}


class SupportTypesDialog(QDialog):
    """Define Support Properties (list of support types, Slide2 style)."""

    def __init__(self, types: list[SupportType], parent=None, select: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Destek Özelliklerini Tanımla"))
        fit_to_screen(self, 820, 560)
        self.types = [copy.deepcopy(t) for t in types]
        if not self.types:
            self.types = [SupportType()]
        self.renames: dict[str, str] = {}
        self._orig = [t.name for t in self.types]
        self.cur = -1
        self._loading = False

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._select)
        bar = QHBoxLayout()
        for txt, tip, slot in (("+", "Destek tipi ekle", self._add), ("✕", tr("Sil"), self._delete),
                               ("⧉", tr("Kopyala"), self._copy)):
            b = QToolButton()
            b.setText(txt)
            b.setToolTip(tip)
            b.setStyleSheet("QToolButton{font-size:14px;min-width:26px;}")
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch(1)
        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        left.addLayout(bar)

        self.title = QLabel()
        self.title.setStyleSheet(TITLE_CSS)
        self.name = QLineEdit()
        self.name.textEdited.connect(self._rename)
        self.color = QToolButton()
        self.color.clicked.connect(self._pick_color)
        self.kind = QComboBox()
        for k, v in SUPPORT_KINDS.items():
            self.kind.addItem(tr(v), k)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.formula = QLabel()
        self.formula.setStyleSheet("font-style:italic;color:#333;")
        self.formula.setWordWrap(True)

        self.w = {
            "spacing": _spin(0.01, 100, 3, 1.5, " m"),
            "tensile": _spin(0, 1e6, 2, 200, " kN"),
            "plate": _spin(0, 1e6, 2, 100, " kN"),
            "bond_strength": _spin(0, 1e5, 2, 50, " kN/m"),
            "bond_length": _spin(0, 1000, 2, 4, " m"),
            "pullout": _spin(0, 1e5, 2, 20, " kN/m/m"),
            "coverage": _spin(1, 100, 1, 100, " %"),
            "adhesion": _spin(0, 1e5, 2, 0, " kPa"),
            "interface_friction": _spin(0, 60, 2, 25, " °"),
            "overburden_gamma": _spin(0, 50, 2, 19, " kN/m³"),
            "pile_shear": _spin(0, 1e6, 2, 100, " kN"),
            "length": _spin(0.1, 200, 2, 12, " m"),
        }
        self.labels = {"spacing": tr("Düzlem dışı aralık:"), "tensile": tr("Çekme kapasitesi:"),
                       "plate": "Plaka kapasitesi:", "bond_strength": tr("Kök (yapışma) dayanımı:"),
                       "bond_length": tr("Kök boyu:"), "pullout": tr("Sıyrılma dayanımı:"),
                       "coverage": tr("Şerit kaplama oranı:"), "adhesion": tr("Arayüz adezyonu:"),
                       "interface_friction": tr("Arayüz sürtünme açısı δ:"),
                       "overburden_gamma": tr("Örtü birim hacim ağırlığı:"),
                       "pile_shear": tr("Kazık kesme dayanımı:"),
                       "length": tr("Varsayılan boy (otomatik yerleşim):")}
        self.anchorage = QComboBox()
        for k, v in ANCHORAGES.items():
            self.anchorage.addItem(tr(v), k)
        self.anchorage.currentIndexChanged.connect(self._store)
        form = QFormLayout()
        form.addRow(tr("Ad:"), self.name)
        form.addRow(tr("Renk:"), self.color)
        form.addRow("Destek tipi:", self.kind)
        self._rows = {}
        for k, sp in self.w.items():
            lab = QLabel(self.labels[k])
            form.addRow(lab, sp)
            self._rows[k] = lab
            sp.valueChanged.connect(self._store)
        lab = QLabel(tr("Ankraj:"))
        form.addRow(lab, self.anchorage)
        self._rows["anchorage"] = lab
        self.w_extra = {"anchorage": self.anchorage}

        appl = QGroupBox(tr("Kuvvet uygulama yöntemi"))
        al = QVBoxLayout(appl)
        self.r_active = QRadioButton(tr("Aktif — kuvvet itici kuvveti azaltır (F'ye bölünmez)"))
        self.r_passive = QRadioButton(tr("Pasif — kuvvet direnç gibi mobilize olur (T / F)"))
        g = QButtonGroup(self)
        g.addButton(self.r_active)
        g.addButton(self.r_passive)
        al.addWidget(self.r_active)
        al.addWidget(self.r_passive)
        self.r_active.toggled.connect(self._store)
        self.orient = QComboBox()
        self.orient.addItem(tr("Desteğe paralel"), "parallel")
        self.orient.addItem(tr("Kayma yüzeyine teğet"), "tangent")
        self.orient.addItem(tr("Desteğe dik"), "perpendicular")
        self.orient.currentIndexChanged.connect(self._store)
        form2 = QFormLayout()
        form2.addRow(tr("Kuvvet doğrultusu:"), self.orient)

        right = QVBoxLayout()
        right.addWidget(self.title)
        right.addLayout(form)
        right.addWidget(self.formula)
        right.addWidget(appl)
        right.addLayout(form2)
        right.addStretch(1)

        body = QHBoxLayout()
        lw = QListWidget  # noqa: F841 (kept for clarity)
        from PySide6.QtWidgets import QWidget
        lwid = QWidget()
        lwid.setLayout(left)
        lwid.setFixedWidth(220)
        body.addWidget(lwid)
        body.addLayout(right, 1)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#b03a2e;")
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(self.error)
        lay.addWidget(_buttons(self, self._accept))
        self._refresh()
        names = [t.name for t in self.types]
        self.list.setCurrentRow(names.index(select) if select in names else 0)

    def _refresh(self):
        cur = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for t in self.types:
            self.list.addItem(QListWidgetItem(color_icon(t.color), t.name))
        self.list.blockSignals(False)
        if 0 <= cur < len(self.types):
            self.list.setCurrentRow(cur)

    def _select(self, row):
        if not 0 <= row < len(self.types):
            return
        self.cur = row
        t = self.types[row]
        self._loading = True
        self.title.setText(t.name)
        self.name.setText(t.name)
        self.color.setIcon(color_icon(t.color, 18))
        self.kind.setCurrentIndex(list(SUPPORT_KINDS).index(t.kind))
        for k, sp in self.w.items():
            sp.setValue(getattr(t, k))
        (self.r_active if t.application == "active" else self.r_passive).setChecked(True)
        self.orient.setCurrentIndex(max(self.orient.findData(t.orientation), 0))
        self.anchorage.setCurrentIndex(max(self.anchorage.findData(t.anchorage), 0))
        self._loading = False
        self._update_fields()

    def _update_fields(self):
        kind = self.kind.currentData()
        self.formula.setText(FORMULAS[kind])
        for k, kinds in FIELDS.items():
            on = kind in kinds
            w = self.w.get(k) or self.w_extra[k]
            w.setVisible(on)
            self._rows[k].setVisible(on)
        self._rows["tensile"].setText(tr("Çekme dayanımı (kN/m):")
                                      if kind in ("geotextile", "geosynthetic")
                                      else tr("Çekme kapasitesi:"))

    def _kind_changed(self, *_):
        if not self._loading and self.kind.currentData() == "micro_pile" \
                and self.orient.currentData() == "parallel":
            self.orient.setCurrentIndex(self.orient.findData("tangent"))
        self._update_fields()
        self._store()

    def _store(self, *_):
        if self._loading or self.cur < 0:
            return
        t = self.types[self.cur]
        t.kind = self.kind.currentData()
        for k, sp in self.w.items():
            setattr(t, k, sp.value())
        if t.kind in ("geotextile", "geosynthetic"):
            t.spacing = 1.0
        t.anchorage = self.anchorage.currentData()
        t.application = "active" if self.r_active.isChecked() else "passive"
        t.orientation = self.orient.currentData()

    def _rename(self, text):
        if self.cur < 0:
            return
        t = self.types[self.cur]
        old = t.name
        t.name = text
        self.title.setText(text)
        self.list.item(self.cur).setText(text)
        for o, now in list(self.renames.items()):
            if now == old:
                self.renames[o] = text
                break
        else:
            if old in self._orig:
                self.renames[old] = text

    def _pick_color(self):
        t = self.types[self.cur]
        c = QColorDialog.getColor(QColor(t.color), self, "Destek rengi")
        if c.isValid():
            t.color = c.name()
            self.color.setIcon(color_icon(t.color, 18))
            self.list.item(self.cur).setIcon(color_icon(t.color))

    def _unique(self, base):
        names = {t.name for t in self.types}
        i = 1
        while f"{base} {i}" in names:
            i += 1
        return f"{base} {i}"

    def _add(self):
        self.types.append(SupportType(self._unique(tr("Destek"))))
        self._refresh()
        self.list.setCurrentRow(len(self.types) - 1)

    def _copy(self):
        t = copy.deepcopy(self.types[self.cur])
        t.name = self._unique(t.name + " kopya")
        self.types.insert(self.cur + 1, t)
        self._refresh()
        self.list.setCurrentRow(self.cur + 1)

    def _delete(self):
        if len(self.types) <= 1:
            self.error.setText(tr("⚠ En az bir destek tipi kalmalı (destekleri silmek için "
                               "çizimden silin)."))
            return
        del self.types[self.cur]
        self._refresh()
        self.list.setCurrentRow(min(self.cur, len(self.types) - 1))

    def _accept(self):
        names = [t.name.strip() for t in self.types]
        if any(not n for n in names) or len(set(names)) != len(names):
            self.error.setText(tr("⚠ Destek tipi adları boş olamaz ve benzersiz olmalı."))
            return
        self.accept()


class SupportEditDialog(QDialog):
    def __init__(self, sp: dict, type_names: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Destek"))
        self.type = QComboBox()
        self.type.addItems(type_names)
        self.type.setCurrentText(sp["type"])
        self.ax = _spin(-1e6, 1e6, 3, sp["a"][0], " m")
        self.ay = _spin(-1e6, 1e6, 3, sp["a"][1], " m")
        self.bx = _spin(-1e6, 1e6, 3, sp["b"][0], " m")
        self.by = _spin(-1e6, 1e6, 3, sp["b"][1], " m")
        f = QFormLayout()
        f.addRow("Destek tipi:", self.type)
        f.addRow(tr("Baş A — x:"), self.ax)
        f.addRow(tr("Baş A — y:"), self.ay)
        f.addRow(tr("Uç B — x:"), self.bx)
        f.addRow(tr("Uç B — y:"), self.by)
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(_buttons(self))

    def apply_to(self, sp: dict) -> None:
        sp["type"] = self.type.currentText()
        sp["a"] = [self.ax.value(), self.ay.value()]
        sp["b"] = [self.bx.value(), self.by.value()]


# ========================================================= tension crack
class CrackFromDepthDialog(QDialog):
    """Create a tension crack line at a constant depth below the ground."""

    def __init__(self, x1: float, x2: float, z: float, water: float, zc_note: str = "",
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Derinlikten Gerilme Çatlağı"))
        self.x1 = _spin(-1e6, 1e6, 3, x1, " m")
        self.x2 = _spin(-1e6, 1e6, 3, x2, " m")
        self.z = _spin(0.01, 1000, 3, z, " m")
        self.water = _spin(0, 100, 1, 100 * water, " %")
        f = QFormLayout()
        f.addRow(tr("Başlangıç x₁:"), self.x1)
        f.addRow(tr("Bitiş x₂:"), self.x2)
        f.addRow(tr("Çatlak derinliği z:"), self.z)
        f.addRow(tr("Çatlaktaki su (doluluk):"), self.water)
        note = QLabel("Çatlak çizgisi x₁–x₂ arasında zemin yüzeyinin z kadar altına yerleştirilir. "
                      "Kayma yüzeyi bu çizgiyi kret tarafında kestiği yerde kesilir ve çatlak "
                      "yüzü düşey olarak zemine uzanır." + (f"\n{zc_note}" if zc_note else ""))
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        self.error = QLabel("")
        self.error.setStyleSheet("color:#b03a2e;")
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(note)
        lay.addWidget(self.error)
        lay.addWidget(_buttons(self, self._accept))

    def _accept(self):
        if self.x2.value() <= self.x1.value():
            self.error.setText(tr("⚠ x₂ > x₁ olmalı."))
            return
        self.accept()

    def points(self, surface) -> list[list[float]]:
        """Polyline following the ground (vertices of `surface` inside the range)."""
        import numpy as np
        x1, x2, z = self.x1.value(), self.x2.value(), self.z.value()
        xs = [x1] + [float(x) for x in surface[:, 0] if x1 < x < x2] + [x2]
        return [[x, float(np.interp(x, surface[:, 0], surface[:, 1])) - z] for x in xs]
