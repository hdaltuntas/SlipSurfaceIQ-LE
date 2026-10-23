"""Left dock panels: Document Viewer and Display Options (property grid)."""

from __future__ import annotations

from slipsurface.ui.i18n import tr

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slipsurface.lem import method_name
from slipsurface.project import DEFAULT_DISPLAY
from slipsurface.ui.icons import color_icon, icon

HEADER_CSS = (
    "QLabel{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #e9f2fd,"
    "stop:1 #cfe2fa);border:1px solid #8fb4e3;color:#1b3a63;font-weight:bold;"
    "padding:2px;}"
)


def header(text: str) -> QLabel:
    lab = QLabel(f"▾  {text}")
    lab.setAlignment(Qt.AlignCenter)
    lab.setStyleSheet(HEADER_CSS)
    return lab


# ============================================================ doc viewer
class DocumentViewer(QWidget):
    summary_requested = Signal()
    settings_requested = Signal()
    entity_activated = Signal(object)  # entity key
    material_activated = Signal(str)
    method_activated = Signal(str)

    def __init__(self, parent=None, interpret: bool = False) -> None:
        super().__init__(parent)
        self.interpret = interpret
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemDoubleClicked.connect(self._double)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)
        lay.addWidget(header(tr("Belge Görüntüleyici")))
        lay.addWidget(self.tree, 1)
        if not interpret:
            b1 = QPushButton(icon("summary"), tr("Proje Özeti…"))
            b2 = QPushButton(icon("settings"), tr("Proje Ayarları…"))
            b1.clicked.connect(self.summary_requested)
            b2.clicked.connect(self.settings_requested)
            lay.addWidget(b1)
            lay.addWidget(b2)

    def refresh(self, project, path=None, results=None, current_method=None) -> None:
        self._last_refresh = (project, path, results, current_method)
        self.tree.clear()
        name = path.name if path else tr("Kaydedilmemiş dosya")
        root = QTreeWidgetItem([name])
        root.setIcon(0, icon("open"))
        self.tree.addTopLevelItem(root)
        scen = QTreeWidgetItem([f"{tr('Senaryo')} 1 – {project.summary.title}"])
        scen.setIcon(0, icon("external"))
        f = QFont()
        f.setBold(True)
        scen.setFont(0, f)
        root.addChild(scen)
        if self.interpret and results is not None:
            for k, r in results.results.items():
                it = QTreeWidgetItem([f"{method_name(k)}   FS = {r.fos:.3f}"])
                it.setData(0, Qt.UserRole, ("method", k))
                if k == current_method:
                    it.setFont(0, f)
                scen.addChild(it)
            for k, e in results.errors.items():
                it = QTreeWidgetItem([f"{method_name(k)}   –"])
                it.setToolTip(0, e)
                it.setForeground(0, QBrush(QColor("#999")))
                scen.addChild(it)
            self._add_notes(scen, project)
        else:
            mats = QTreeWidgetItem([f"{tr('Malzemeler')} ({len(project.materials)})"])
            mats.setIcon(0, icon("materials"))
            scen.addChild(mats)
            for m in project.materials:
                it = QTreeWidgetItem([m.name])
                it.setIcon(0, color_icon(m.color))
                it.setData(0, Qt.UserRole, ("material", m.name))
                mats.addChild(it)
            bnd = QTreeWidgetItem([tr("Sınırlar")])
            bnd.setIcon(0, icon("material_boundary"))
            scen.addChild(bnd)
            if project.external:
                it = QTreeWidgetItem([f"{tr('Dış sınır')} ({len(project.external)} {tr('köşe')})"])
                it.setData(0, Qt.UserRole, ("entity", ("external", 0)))
                bnd.addChild(it)
            for i, b in enumerate(project.material_boundaries):
                it = QTreeWidgetItem([f"{tr('Malzeme sınırı')} {i + 1} ({len(b)} {tr('köşe')})"])
                it.setData(0, Qt.UserRole, ("entity", ("material", i)))
                bnd.addChild(it)
            if project.water_table:
                it = QTreeWidgetItem([f"{tr('YASS')} ({len(project.water_table)} {tr('köşe')})"])
                it.setData(0, Qt.UserRole, ("entity", ("water", 0)))
                bnd.addChild(it)
            if project.tension_crack:
                it = QTreeWidgetItem(
                    [
                        f"Gerilme çatlağı ({len(project.tension_crack)} köşe, "
                        f"su %{100 * project.groundwater.crack_water:.0f})"
                    ]
                )
                it.setData(0, Qt.UserRole, ("entity", ("crack", 0)))
                bnd.addChild(it)
            if project.surfaces.user_surface:
                it = QTreeWidgetItem([tr("Kullanıcı yüzeyi")])
                it.setData(0, Qt.UserRole, ("entity", ("user", 0)))
                bnd.addChild(it)
            if project.supports or project.support_types or project.support_patterns:
                n = len(project.supports) + len(project.support_patterns)
                sup = QTreeWidgetItem([f"{tr('Destekler')} ({n})"])
                sup.setIcon(0, icon("support"))
                scen.addChild(sup)
                for i, sp in enumerate(project.supports):
                    st = project.support_type(sp["type"])
                    it = QTreeWidgetItem([f"Destek {i + 1}: {sp['type']}"])
                    if st is not None:
                        it.setIcon(0, color_icon(st.color))
                    it.setData(0, Qt.UserRole, ("entity", ("support", i)))
                    sup.addChild(it)
                for i, pt in enumerate(project.support_patterns):
                    it = QTreeWidgetItem(
                        [
                            f"Bulon paterni {i + 1}: {pt['type']}, "
                            f"@{pt['spacing']:g} m, {pt.get('angle', 15):g}°"
                        ]
                    )
                    it.setIcon(0, icon("bolt_pattern"))
                    it.setData(0, Qt.UserRole, ("entity", ("pattern", i)))
                    sup.addChild(it)
            if project.facings or project.facing_types:
                fac = QTreeWidgetItem([f"{tr('Kaplamalar')} ({len(project.facings)})"])
                fac.setIcon(0, icon("facing"))
                scen.addChild(fac)
                for i, f in enumerate(project.facings):
                    ft = project.facing_type(f["type"])
                    txt = f"Kaplama {i + 1}: {f['type']}  x = {f['x1']:.1f}…{f['x2']:.1f}"
                    it = QTreeWidgetItem([txt])
                    if ft is not None:
                        it.setIcon(0, color_icon(ft.color))
                        it.setToolTip(
                            0, f"t = {ft.thickness:g} m, {ft.mesh}, T = {ft.capacity:.1f} kN/m"
                        )
                    it.setData(0, Qt.UserRole, ("entity", ("facing", i)))
                    fac.addChild(it)
            if project.loads or project.seismic.kh or project.seismic.kv:
                lds = QTreeWidgetItem([f"{tr('Yükler')} ({len(project.loads)})"])
                lds.setIcon(0, icon("load_distributed"))
                scen.addChild(lds)
                for i, ld in enumerate(project.loads):
                    if ld["kind"] == "distributed":
                        txt = f"Yük {i + 1}: yayılı {ld['q'][0]:g}–{ld['q'][1]:g} kPa"
                    else:
                        txt = f"Yük {i + 1}: tekil {ld['magnitude']:g} kN/m"
                    it = QTreeWidgetItem([txt])
                    it.setData(0, Qt.UserRole, ("entity", ("load", i)))
                    lds.addChild(it)
                if project.seismic.kh or project.seismic.kv:
                    lds.addChild(
                        QTreeWidgetItem(
                            [f"Sismik: {project.seismic.clause()}"]
                        )
                    )
            self._add_notes(scen, project)
            meth = QTreeWidgetItem(
                [
                    tr("Yöntemler")
                    + ": "
                    + ", ".join(method_name(k) for k in project.methods.methods)
                ]
            )
            meth.setIcon(0, icon("compute"))
            scen.addChild(meth)
        self._translate_items()
        self.tree.expandAll()

    def _translate_items(self) -> None:
        """Item captions are built from templates; user names (materials) stay."""
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            data = item.data(0, Qt.UserRole)
            if not (data and data[0] == "material"):
                item.setText(0, tr(item.text(0)))
            it += 1

    def _add_notes(self, scen, project) -> None:
        if not project.annotations:
            return
        nt = QTreeWidgetItem([f"{tr('Notlar')} ({len(project.annotations)})"])
        nt.setIcon(0, icon("annot_text"))
        scen.addChild(nt)
        names = {
            "text": tr("Yazı"),
            "line": tr("Çizgi"),
            "arrow": tr("Ok"),
            "rect": tr("Dikdörtgen"),
            "ellipse": tr("Elips"),
        }
        for i, an in enumerate(project.annotations):
            txt = names.get(an["kind"], an["kind"])
            if an["kind"] == "text":
                first = (an.get("text") or "").splitlines()
                txt += f": {first[0][:24]}" if first else ""
            it = QTreeWidgetItem([txt])
            it.setData(0, Qt.UserRole, ("entity", ("annot", i)))
            nt.addChild(it)

    def _clicked(self, item, col) -> None:
        d = item.data(0, Qt.UserRole)
        if not d:
            return
        kind, val = d
        if kind == "entity":
            self.entity_activated.emit(val)
        elif kind == "method":
            self.method_activated.emit(val)

    def _double(self, item, col) -> None:
        d = item.data(0, Qt.UserRole)
        if d and d[0] == "material":
            self.material_activated.emit(d[1])


# ======================================================= display options
MODELER_OPTIONS = [
    (
        tr("Sınırlar"),
        [
            ("external_color", tr("Dış sınır rengi"), "color"),
            ("material_boundary_color", tr("Malzeme sınırı rengi"), "color"),
            ("water_table_color", "YASS rengi", "color"),
            ("show_vertices", tr("Sınır köşelerini göster"), "bool"),
            ("line_width", tr("Çizgi kalınlığı"), "int"),
        ],
    ),
    (
        tr("Çeşitli"),
        [
            ("show_ruler", tr("Cetveli göster"), "bool"),
            ("show_grid", tr("Izgarayı göster"), "bool"),
            ("fill_materials", "Malzeme dolgusu", "bool"),
            ("show_legend", "Lejant", "bool"),
            ("show_slope_limits", tr("Kayma sınırları"), "bool"),
        ],
    ),
    (
        tr("Malzeme Etiketleri"),
        [
            (
                "material_labels",
                tr("Bölge üzerinde"),
                (
                    "choice",
                    [("none", tr("Yok")), ("name", "Ad"), ("full", tr("Ad + parametreler"))],
                ),
            ),
            ("label_size", tr("Etiket yazı boyutu"), "int"),
        ],
    ),
]

INTERPRET_OPTIONS = {
    tr("Kayma Stabilitesi"): [
        (
            tr("Arama"),
            [
                ("show_slope_limits", tr("Kayma sınırları"), "bool"),
                ("show_fs_contours", tr("Kayma merkezi FS konturları (aranan örnekler)"), "bool"),
                ("show_fs_legend", tr("FS lejantı (sağ alt)"), "bool"),
            ],
        ),
        (
            tr("Dilimler"),
            [
                ("show_slices", tr("Dilim sınırları ve dolgu"), "bool"),
                ("slice_fill_color", tr("Dolgu rengi"), "color"),
            ],
        ),
        (
            tr("Yüzeyler"),
            [
                ("show_lines_to_center", tr("Merkeze çizgiler"), "bool"),
                ("show_fs_text", tr("FS yazısı"), "bool"),
                ("critical_dashed", tr("Kritik yüzey kesikli çizgi"), "bool"),
                ("show_all_surfaces", tr("Tüm yüzeyler (en düşük 25)"), "bool"),
                ("show_control_points", tr("Spline kontrol noktaları"), "bool"),
            ],
        ),
    ],
    tr("Genel"): MODELER_OPTIONS,
}


class PropertyGrid(QTreeWidget):
    option_changed = Signal(str, object)

    def __init__(self, spec, parent=None) -> None:
        super().__init__(parent)
        self.setColumnCount(2)
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setRootIsDecorated(True)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.header().resizeSection(1, 74)
        self.header().setStretchLastSection(False)
        self._items: dict[str, tuple] = {}
        self._loading = False
        bold = QFont()
        bold.setBold(True)
        for cat, rows in spec:
            top = QTreeWidgetItem([cat])
            top.setFont(0, bold)
            top.setBackground(0, QColor("#eef1f5"))
            top.setBackground(1, QColor("#eef1f5"))
            top.setForeground(0, QColor("#1b2a3a"))
            self.addTopLevelItem(top)
            for key, label, typ in rows:
                it = QTreeWidgetItem([label, ""])
                top.addChild(it)
                if isinstance(typ, tuple) and typ[0] == "choice":
                    cb = QComboBox()
                    for val, txt in typ[1]:
                        cb.addItem(txt, val)
                    cb.currentIndexChanged.connect(
                        lambda _i, k=key, c=cb: self._emit(k, c.currentData())
                    )
                    self.setItemWidget(it, 1, cb)
                    self._items[key] = (it, "choice", cb)
                    self.header().resizeSection(1, 128)
                elif typ == "bool":
                    it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                    it.setCheckState(1, Qt.Unchecked)
                    self._items[key] = (it, typ, None)
                elif typ == "color":
                    btn = QToolButton()
                    btn.setAutoRaise(True)
                    btn.clicked.connect(lambda _=False, k=key: self._pick_color(k))
                    self.setItemWidget(it, 1, btn)
                    self._items[key] = (it, typ, btn)
                elif typ == "int":
                    sp = QSpinBox()
                    sp.setRange(*((6, 24) if key == "label_size" else (1, 8)))
                    sp.valueChanged.connect(lambda v, k=key: self._emit(k, v))
                    self.setItemWidget(it, 1, sp)
                    self._items[key] = (it, typ, sp)
        self.itemChanged.connect(self._on_item_changed)
        self.expandAll()

    def set_values(self, display: dict) -> None:
        self._loading = True
        for key, (it, typ, w) in self._items.items():
            v = display.get(key, DEFAULT_DISPLAY.get(key))
            if typ == "bool":
                it.setCheckState(1, Qt.Checked if v else Qt.Unchecked)
            elif typ == "color":
                w.setIcon(color_icon(v, 16))
                w.setText(" …")
                w.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
                w.setProperty("color", v)
            elif typ == "int":
                w.setValue(int(v))
            elif typ == "choice":
                i = w.findData(v)
                w.setCurrentIndex(max(i, 0))
        self._loading = False

    def _on_item_changed(self, item, col) -> None:
        if self._loading or col != 1:
            return
        for key, (it, typ, _) in self._items.items():
            if it is item and typ == "bool":
                self._emit(key, item.checkState(1) == Qt.Checked)

    def _pick_color(self, key) -> None:
        _, _, btn = self._items[key]
        col = QColorDialog.getColor(QColor(btn.property("color")), self, tr("Renk seç"))
        if col.isValid():
            btn.setIcon(color_icon(col.name(), 16))
            btn.setProperty("color", col.name())
            self._emit(key, col.name())

    def _emit(self, key, value) -> None:
        if not self._loading:
            self.option_changed.emit(key, value)


class DisplayOptions(QWidget):
    option_changed = Signal(str, object)
    reset_requested = Signal()

    def __init__(self, parent=None, interpret: bool = False) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)
        lay.addWidget(header(tr("Görüntü Seçenekleri")))
        self.grids: list[PropertyGrid] = []
        if interpret:
            tabs = QTabWidget()
            for name, spec in INTERPRET_OPTIONS.items():
                g = PropertyGrid(spec)
                g.option_changed.connect(self.option_changed)
                self.grids.append(g)
                tabs.addTab(g, name)
            lay.addWidget(tabs, 1)
        else:
            g = PropertyGrid(MODELER_OPTIONS)
            g.option_changed.connect(self.option_changed)
            self.grids.append(g)
            lay.addWidget(g, 1)
        row = QHBoxLayout()
        b = QPushButton(tr("Varsayılanlara Dön"))
        b.clicked.connect(self.reset_requested)
        row.addWidget(b)
        lay.addLayout(row)

    def set_values(self, display: dict) -> None:
        for g in self.grids:
            g.set_values(display)
