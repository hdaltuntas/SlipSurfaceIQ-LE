"""Document Viewer and Display Options (Interpret left dock; Modeler View dialog)."""

from __future__ import annotations


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
        lay.addWidget(header("Document Viewer"))
        lay.addWidget(self.tree, 1)
        if not interpret:
            b1 = QPushButton(icon("summary"), "Project Summary…")
            b2 = QPushButton(icon("settings"), "Project Settings…")
            b1.clicked.connect(self.summary_requested)
            b2.clicked.connect(self.settings_requested)
            lay.addWidget(b1)
            lay.addWidget(b2)

    def refresh(self, project, path=None, results=None, current_method=None) -> None:
        self.tree.clear()
        name = path.name if path else "Unsaved File"
        root = QTreeWidgetItem([name])
        root.setIcon(0, icon("open"))
        self.tree.addTopLevelItem(root)
        scen = QTreeWidgetItem([f"Scenario 1 – {project.summary.title}"])
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
            mats = QTreeWidgetItem([f"Materials ({len(project.materials)})"])
            mats.setIcon(0, icon("materials"))
            scen.addChild(mats)
            for m in project.materials:
                it = QTreeWidgetItem([m.name])
                it.setIcon(0, color_icon(m.color))
                it.setData(0, Qt.UserRole, ("material", m.name))
                mats.addChild(it)
            bnd = QTreeWidgetItem(["Boundaries"])
            bnd.setIcon(0, icon("material_boundary"))
            scen.addChild(bnd)
            if project.external:
                it = QTreeWidgetItem([f"External boundary ({len(project.external)} vertices)"])
                it.setData(0, Qt.UserRole, ("entity", ("external", 0)))
                bnd.addChild(it)
            for i, b in enumerate(project.material_boundaries):
                it = QTreeWidgetItem([f"Material boundary {i + 1} ({len(b)} vertices)"])
                it.setData(0, Qt.UserRole, ("entity", ("material", i)))
                bnd.addChild(it)
            if project.water_table:
                it = QTreeWidgetItem([f"Water table ({len(project.water_table)} vertices)"])
                it.setData(0, Qt.UserRole, ("entity", ("water", 0)))
                bnd.addChild(it)
            if project.tension_crack:
                it = QTreeWidgetItem(
                    [
                        (
                            f"Tension crack ({len(project.tension_crack)} vertices, water "
                            f"{100 * project.groundwater.crack_water:.0f}%)"
                        )
                    ]
                )
                it.setData(0, Qt.UserRole, ("entity", ("crack", 0)))
                bnd.addChild(it)
            if project.surfaces.user_surface:
                it = QTreeWidgetItem(["User surface"])
                it.setData(0, Qt.UserRole, ("entity", ("user", 0)))
                bnd.addChild(it)
            if project.supports or project.support_types or project.support_patterns:
                n = len(project.supports) + len(project.support_patterns)
                sup = QTreeWidgetItem([f"Supports ({n})"])
                sup.setIcon(0, icon("support"))
                scen.addChild(sup)
                for i, sp in enumerate(project.supports):
                    st = project.support_type(sp["type"])
                    it = QTreeWidgetItem([f"Support {i + 1}: {sp['type']}"])
                    if st is not None:
                        it.setIcon(0, color_icon(st.color))
                    it.setData(0, Qt.UserRole, ("entity", ("support", i)))
                    sup.addChild(it)
                for i, pt in enumerate(project.support_patterns):
                    it = QTreeWidgetItem(
                        [
                            (
                                f"Bolt pattern {i + 1}: {pt['type']}, @{pt['spacing']:g} m, "
                                f"{pt.get('angle', 15):g}°"
                            )
                        ]
                    )
                    it.setIcon(0, icon("bolt_pattern"))
                    it.setData(0, Qt.UserRole, ("entity", ("pattern", i)))
                    sup.addChild(it)
            if project.facings or project.facing_types:
                fac = QTreeWidgetItem([f"Facings ({len(project.facings)})"])
                fac.setIcon(0, icon("facing"))
                scen.addChild(fac)
                for i, f in enumerate(project.facings):
                    ft = project.facing_type(f["type"])
                    txt = f"Facing {i + 1}: {f['type']}  x = {f['x1']:.1f}…{f['x2']:.1f}"
                    it = QTreeWidgetItem([txt])
                    if ft is not None:
                        it.setIcon(0, color_icon(ft.color))
                        it.setToolTip(
                            0, f"t = {ft.thickness:g} m, {ft.mesh}, T = {ft.capacity:.1f} kN/m"
                        )
                    it.setData(0, Qt.UserRole, ("entity", ("facing", i)))
                    fac.addChild(it)
            if project.loads or project.seismic.kh or project.seismic.kv:
                lds = QTreeWidgetItem([f"Loads ({len(project.loads)})"])
                lds.setIcon(0, icon("load_distributed"))
                scen.addChild(lds)
                for i, ld in enumerate(project.loads):
                    if ld["kind"] == "distributed":
                        txt = f"Load {i + 1}: distributed {ld['q'][0]:g}–{ld['q'][1]:g} kPa"
                    else:
                        txt = f"Load {i + 1}: line {ld['magnitude']:g} kN/m"
                    it = QTreeWidgetItem([txt])
                    it.setData(0, Qt.UserRole, ("entity", ("load", i)))
                    lds.addChild(it)
                if project.seismic.kh or project.seismic.kv:
                    lds.addChild(QTreeWidgetItem([f"Seismic: {project.seismic.clause()}"]))
            self._add_notes(scen, project)
            meth = QTreeWidgetItem(
                ["Methods" + ": " + ", ".join(method_name(k) for k in project.methods.methods)]
            )
            meth.setIcon(0, icon("compute"))
            scen.addChild(meth)
        self.tree.expandAll()

    def _add_notes(self, scen, project) -> None:
        if not project.annotations:
            return
        nt = QTreeWidgetItem([f"Notes ({len(project.annotations)})"])
        nt.setIcon(0, icon("annot_text"))
        scen.addChild(nt)
        names = {
            "text": "Text",
            "line": "Line",
            "arrow": "Arrow",
            "rect": "Rectangle",
            "ellipse": "Ellipse",
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
        "Boundaries",
        [
            ("external_color", "External Boundary Color", "color"),
            ("material_boundary_color", "Material Boundary Color", "color"),
            ("water_table_color", "Water table colour", "color"),
            ("show_vertices", "Show Boundary Vertices", "bool"),
            ("line_width", "Line Width", "int"),
        ],
    ),
    (
        "Miscellaneous",
        [
            ("show_ruler", "Show Rulers", "bool"),
            ("show_grid", "Show Grid", "bool"),
            ("fill_materials", "Material fill", "bool"),
            ("show_legend", "Legend", "bool"),
            ("show_slope_limits", "Slope limits", "bool"),
        ],
    ),
    (
        "Material Labels",
        [
            (
                "material_labels",
                "On Region",
                (
                    "choice",
                    [("none", "None"), ("name", "Name"), ("full", "Name + Parameters")],
                ),
            ),
            ("label_size", "Label Font Size", "int"),
        ],
    ),
]

INTERPRET_OPTIONS = {
    "Slope Stability": [
        (
            "Search",
            [
                ("show_slope_limits", "Slope limits", "bool"),
                ("show_fs_contours", "Slip-centre FS contours (searched samples)", "bool"),
                ("show_fs_legend", "FS Legend (Bottom Right)", "bool"),
            ],
        ),
        (
            "Slices",
            [
                ("show_slices", "Slice Boundaries and Fill", "bool"),
                ("slice_fill_color", "Fill Color", "color"),
            ],
        ),
        (
            "Surfaces",
            [
                ("show_lines_to_center", "Lines to Center", "bool"),
                ("show_fs_text", "FS Text", "bool"),
                ("critical_dashed", "Critical surface as dashed line", "bool"),
                ("show_all_surfaces", "All Surfaces (Lowest 25)", "bool"),
                ("show_control_points", "Spline Control Points", "bool"),
            ],
        ),
    ],
    "General": MODELER_OPTIONS,
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
        col = QColorDialog.getColor(QColor(btn.property("color")), self, "Choose Color")
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
        lay.addWidget(header("Display Options"))
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
        b = QPushButton("Restore Defaults")
        b.clicked.connect(self.reset_requested)
        row.addWidget(b)
        lay.addLayout(row)

    def set_values(self, display: dict) -> None:
        for g in self.grids:
            g.set_values(display)
