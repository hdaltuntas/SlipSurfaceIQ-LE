"""Dialogs: shotcrete facing types, bolt pattern, annotation properties."""

from __future__ import annotations

from slipsurface.ui.preferences import fit_to_screen

from slipsurface.ui.i18n import tr

import copy

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QRadioButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from slipsurface.loads import FacingType
from slipsurface.ui.icons import color_icon

TITLE_CSS = "color:#2a7ad0;font-size:16px;"
# standard welded wire mesh (TS 4559 / EN 10080 style): name -> As [mm2/m]
MESHES = {"Q106": 106, "Q131": 131, "Q158": 158, "Q188": 188, "Q221": 221, "Q257": 257,
          "Q295": 295, "Q335": 335, "Q378": 378, "Q424": 424, "Q524": 524, "Q589": 589,
          "Özel": None}


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


# ================================================================ facing
class FacingTypesDialog(QDialog):
    """Define shotcrete + wire mesh facing types."""

    def __init__(self, types: list[FacingType], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kaplama Tiplerini Tanımla — Püskürtme Beton + Hasır Çelik")
        fit_to_screen(self, 820, 540)
        self.types = [copy.deepcopy(t) for t in types] or [FacingType()]
        self.renames: dict[str, str] = {}
        self._orig = [t.name for t in self.types]
        self.cur = -1
        self._loading = False

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._select)
        bar = QHBoxLayout()
        for txt, tip, slot in (("+", tr("Ekle"), self._add), ("✕", tr("Sil"), self._delete)):
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
        self.thickness = _spin(0.01, 2, 3, 0.10, " m")
        self.gamma = _spin(0, 50, 2, 24, " kN/m³")
        self.tau = _spin(0, 1e5, 1, 400, " kPa")
        self.mesh = QComboBox()
        for k, v in MESHES.items():
            self.mesh.addItem(k if v is None else f"{k}  (As = {v} mm²/m)", k)
        self.mesh_as = _spin(0, 5000, 1, 188, " mm²/m")
        self.mesh_fy = _spin(0, 2000, 0, 500, " MPa")
        self.r_passive = QRadioButton("Pasif (T / F) — önerilen")
        self.r_active = QRadioButton(tr("Aktif"))
        g = QButtonGroup(self)
        g.addButton(self.r_passive)
        g.addButton(self.r_active)
        self.capacity = QLabel()
        self.capacity.setStyleSheet("font-weight:bold;color:#1b3a63;")

        form = QFormLayout()
        form.addRow(tr("Ad:"), self.name)
        form.addRow(tr("Renk:"), self.color)
        form.addRow("Püskürtme beton kalınlığı t:", self.thickness)
        form.addRow("Birim hacim ağırlık γ:", self.gamma)
        form.addRow("Beton kayma dayanımı τ:", self.tau)
        form.addRow("Hasır çelik:", self.mesh)
        form.addRow("Hasır çelik alanı As:", self.mesh_as)
        form.addRow("Çelik akma dayanımı fy:", self.mesh_fy)
        appl = QHBoxLayout()
        appl.addWidget(self.r_passive)
        appl.addWidget(self.r_active)
        form.addRow("Kuvvet uygulama:", appl)
        form.addRow("Kapasite:", self.capacity)
        note = QLabel(
            "Kaplama şev yüzüne atanır. Analizde: (1) ağırlığı γ·t yüzeye yük olarak eklenir; "
            "(2) kayma yüzeyi kaplamalı yüzeyden çıkıyor veya giriyorsa, kaplamanın kesilmesi "
            "için gereken kuvvet T = τ·t + As·fy, o noktada kayma yüzeyine teğet ve kaymaya "
            "karşı uygulanır. τ için tipik değer: 0.02–0.04·fck (C25 için ≈ 0.5–1.0 MPa, "
            "güvenli tarafta 0.3–0.5 MPa).")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        right = QVBoxLayout()
        right.addWidget(self.title)
        right.addLayout(form)
        right.addWidget(note)
        right.addStretch(1)
        body = QHBoxLayout()
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(220)
        body.addWidget(lw)
        body.addLayout(right, 1)
        self.error = QLabel("")
        self.error.setStyleSheet("color:#b03a2e;")
        lay = QVBoxLayout(self)
        lay.addLayout(body, 1)
        lay.addWidget(self.error)
        lay.addWidget(_buttons(self, self._accept))

        for w in (self.thickness, self.gamma, self.tau, self.mesh_as, self.mesh_fy):
            w.valueChanged.connect(self._store)
        self.mesh.currentIndexChanged.connect(self._mesh_changed)
        self.r_passive.toggled.connect(self._store)
        self._refresh()
        self.list.setCurrentRow(0)

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
        self.thickness.setValue(t.thickness)
        self.gamma.setValue(t.gamma)
        self.tau.setValue(t.tau)
        i = self.mesh.findData(t.mesh)
        self.mesh.setCurrentIndex(i if i >= 0 else self.mesh.findData("Özel"))
        self.mesh_as.setValue(t.mesh_as)
        self.mesh_fy.setValue(t.mesh_fy)
        (self.r_passive if t.application == "passive" else self.r_active).setChecked(True)
        self._loading = False
        self._mesh_changed(store=False)
        self._update_capacity()

    def _mesh_changed(self, *_, store=True):
        key = self.mesh.currentData()
        custom = MESHES.get(key) is None
        self.mesh_as.setEnabled(custom)
        if not custom:
            self.mesh_as.setValue(MESHES[key])
        if store:
            self._store()

    def _store(self, *_):
        if self._loading or self.cur < 0:
            return
        t = self.types[self.cur]
        t.thickness = self.thickness.value()
        t.gamma = self.gamma.value()
        t.tau = self.tau.value()
        t.mesh = self.mesh.currentData()
        t.mesh_as = self.mesh_as.value()
        t.mesh_fy = self.mesh_fy.value()
        t.application = "passive" if self.r_passive.isChecked() else "active"
        self._update_capacity()

    def _update_capacity(self):
        if self.cur < 0:
            return
        t = self.types[self.cur]
        self.capacity.setText(tr(f"T = τ·t + As·fy = {t.tau * t.thickness:.1f} + "
                              f"{t.mesh_as * t.mesh_fy / 1000:.1f} = {t.capacity:.1f} kN/m   "
                              f"·   ağırlık {t.weight_per_m:.2f} kN/m²"))

    def _rename(self, text):
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
        c = QColorDialog.getColor(QColor(t.color), self, "Kaplama rengi")
        if c.isValid():
            t.color = c.name()
            self.color.setIcon(color_icon(t.color, 18))
            self.list.item(self.cur).setIcon(color_icon(t.color))

    def _add(self):
        names = {t.name for t in self.types}
        i = 1
        while f"Kaplama {i}" in names:
            i += 1
        self.types.append(FacingType(f"Kaplama {i}"))
        self._refresh()
        self.list.setCurrentRow(len(self.types) - 1)

    def _delete(self):
        if len(self.types) <= 1:
            self.error.setText(tr("⚠ En az bir kaplama tipi kalmalı."))
            return
        del self.types[self.cur]
        self._refresh()
        self.list.setCurrentRow(min(self.cur, len(self.types) - 1))

    def _accept(self):
        names = [t.name.strip() for t in self.types]
        if any(not n for n in names) or len(set(names)) != len(names):
            self.error.setText(tr("⚠ Adlar boş olamaz ve benzersiz olmalı."))
            return
        self.accept()


class FacingEditDialog(QDialog):
    """Edit one facing assignment (type + x range on the slope face)."""

    def __init__(self, f: dict, type_names: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kaplama")
        self.type = QComboBox()
        self.type.addItems(type_names)
        self.type.setCurrentText(f["type"])
        self.x1 = _spin(-1e6, 1e6, 3, f["x1"], " m")
        self.x2 = _spin(-1e6, 1e6, 3, f["x2"], " m")
        form = QFormLayout()
        form.addRow("Kaplama tipi:", self.type)
        form.addRow(tr("Başlangıç x₁:"), self.x1)
        form.addRow(tr("Bitiş x₂:"), self.x2)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(_buttons(self))

    def apply_to(self, f: dict, ground_y=None) -> None:
        x1, x2 = sorted((self.x1.value(), self.x2.value()))
        f["type"] = self.type.currentText()
        f["x1"], f["x2"] = x1, x2
        if ground_y is not None:
            f["points"] = [[x1, float(ground_y(x1))], [x2, float(ground_y(x2))]]


# =============================================================== pattern
class PatternDialog(QDialog):
    def __init__(self, pt: dict, type_names: list[str], count_fn=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bulon / Ankraj Paterni")
        self.pt = pt
        self.count_fn = count_fn
        self.type = QComboBox()
        self.type.addItems(type_names)
        self.type.setCurrentText(pt["type"])
        self.x1 = _spin(-1e6, 1e6, 3, pt["p1"][0], " m")
        self.x2 = _spin(-1e6, 1e6, 3, pt["p2"][0], " m")
        self.spacing = _spin(0.1, 100, 3, pt.get("spacing", 2.0), " m")
        self.offset = _spin(0, 100, 3, pt.get("offset", 1.0), " m")
        self.angle = _spin(-89, 89, 1, pt.get("angle", 15.0), " °")
        self.length = _spin(0.1, 200, 2, pt.get("length", 12.0), " m")
        self.count = QLabel()
        self.count.setStyleSheet("font-weight:bold;color:#1b3a63;")
        f = QFormLayout()
        f.addRow("Destek tipi:", self.type)
        f.addRow(tr("Başlangıç x₁:"), self.x1)
        f.addRow(tr("Bitiş x₂:"), self.x2)
        f.addRow("Aralık (şev yüzü boyunca):", self.spacing)
        f.addRow("İlk bulon mesafesi:", self.offset)
        f.addRow("Eğim (yataydan aşağı):", self.angle)
        f.addRow("Boy:", self.length)
        f.addRow("Bulon sayısı:", self.count)
        note = QLabel("Bulonlar zemin yüzeyi boyunca x₁'den itibaren eşit aralıkla yerleştirilir, "
                      "başlıklar yüzeyde, doğrultu şevin içine doğrudur. Düzlem dışı aralık "
                      "destek tipinde tanımlıdır.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(note)
        lay.addWidget(_buttons(self))
        for w in (self.x1, self.x2, self.spacing, self.offset):
            w.valueChanged.connect(self._update_count)
        self._update_count()

    def _update_count(self, *_):
        if self.count_fn is None:
            self.count.setText("—")
            return
        try:
            n = self.count_fn(self.x1.value(), self.x2.value(), self.spacing.value(),
                              self.offset.value())
            self.count.setText(str(n))
        except ValueError:
            self.count.setText("—")

    def apply_to(self, pt: dict, ground_y=None) -> None:
        x1, x2 = self.x1.value(), self.x2.value()
        pt["type"] = self.type.currentText()
        pt["p1"] = [x1, float(ground_y(x1)) if ground_y else pt["p1"][1]]
        pt["p2"] = [x2, float(ground_y(x2)) if ground_y else pt["p2"][1]]
        pt["spacing"] = self.spacing.value()
        pt["offset"] = self.offset.value()
        pt["angle"] = self.angle.value()
        pt["length"] = self.length.value()


# ============================================================ annotation
class AnnotationDialog(QDialog):
    def __init__(self, ann: dict, parent=None) -> None:
        super().__init__(parent)
        kind = ann["kind"]
        self.setWindowTitle({"text": tr("Yazı"), "line": tr("Çizgi"), "arrow": tr("Ok"),
                             "rect": tr("Dikdörtgen"), "ellipse": tr("Elips")}[kind])
        self.ann = ann
        self.color = ann.get("color", "#c0392b")
        self.fill = ann.get("fill")
        self.color_btn = QToolButton()
        self.color_btn.setIcon(color_icon(self.color, 18))
        self.color_btn.clicked.connect(self._pick_color)
        f = QFormLayout()
        if kind == "text":
            self.text = QPlainTextEdit(ann.get("text", ""))
            self.text.setMinimumHeight(80)
            self.size = QSpinBox()
            self.size.setRange(6, 72)
            self.size.setValue(int(ann.get("size", 10)))
            self.bold = QCheckBox(tr("Kalın"))
            self.bold.setChecked(bool(ann.get("bold", False)))
            self.box = QCheckBox("Arka plan kutusu")
            self.box.setChecked(bool(ann.get("box", True)))
            f.addRow(tr("Metin:"), self.text)
            f.addRow("Yazı boyutu (pt):", self.size)
            f.addRow(self.bold)
            f.addRow(self.box)
        else:
            self.width = _spin(0.5, 10, 1, float(ann.get("width", 1.5)), " px")
            f.addRow("Çizgi kalınlığı:", self.width)
            if kind in ("rect", "ellipse"):
                self.fill_cb = QCheckBox("Dolgu")
                self.fill_cb.setChecked(self.fill is not None)
                self.fill_btn = QToolButton()
                self.fill_btn.setIcon(color_icon(self.fill or "#f6d65a", 18))
                self.fill_btn.clicked.connect(self._pick_fill)
                row = QHBoxLayout()
                row.addWidget(self.fill_cb)
                row.addWidget(self.fill_btn)
                row.addStretch(1)
                f.addRow(tr("Dolgu:"), row)
        f.addRow(tr("Renk:"), self.color_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(_buttons(self))

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.color), self, tr("Renk"))
        if c.isValid():
            self.color = c.name()
            self.color_btn.setIcon(color_icon(self.color, 18))

    def _pick_fill(self):
        c = QColorDialog.getColor(QColor(self.fill or "#f6d65a"), self, tr("Dolgu rengi"))
        if c.isValid():
            self.fill = c.name()
            self.fill_btn.setIcon(color_icon(self.fill, 18))
            self.fill_cb.setChecked(True)

    def apply_to(self, ann: dict) -> None:
        ann["color"] = self.color
        if ann["kind"] == "text":
            ann["text"] = self.text.toPlainText()
            ann["size"] = self.size.value()
            ann["bold"] = self.bold.isChecked()
            ann["box"] = self.box.isChecked()
        else:
            ann["width"] = self.width.value()
            if ann["kind"] in ("rect", "ellipse"):
                ann["fill"] = (self.fill or "#f6d65a") if self.fill_cb.isChecked() else None
