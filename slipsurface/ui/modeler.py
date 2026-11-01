"""SlipSurfaceIQ LE Modeler — main window (Slide2-style layout).

menu bar
workflow bar   Geometry › Support › Loading › Properties › Surfaces
toolbars       main (file, edit, settings, compute, interpret, view, tools)
               + step toolbar (changes with the workflow step)
centre         CAD area (rulers, grid, snapping, tools)
status bar     hints, coordinates, command box, SNAP GRID ORTHO OSNAP

Document Viewer + Display Options live in the Interpret window. The Modeler
reaches display options from View → Display Options.
"""

from __future__ import annotations

from slipsurface.ui.preferences import fit_to_screen


import copy
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
)

from slipsurface import __version__
from slipsurface.lem import method_name
from slipsurface.loads import FacingType, SupportType, pattern_positions
from slipsurface.project import DEFAULT_DISPLAY, EXAMPLES, Project, empty_project
from slipsurface.ui.cad import CadArea
from slipsurface.ui.cad import tools as T
from slipsurface.ui.annotations import ANNOT_TOOLS, edit_annotation, new_annotation
from slipsurface.ui.cad.model import LABELS, MIN_POINTS, add_entity, get_points, set_points
from slipsurface.ui.dialogs.facing_pattern_annot import (
    FacingEditDialog,
    FacingTypesDialog,
    PatternDialog,
)
from slipsurface.ui.dialogs.loads_supports import (
    CrackFromDepthDialog,
    DistributedLoadDialog,
    LineLoadDialog,
    SupportEditDialog,
    SupportTypesDialog,
)
from slipsurface.ui.dialogs.materials import MaterialsDialog
from slipsurface.ui.dialogs.misc import CoordinatesDialog, GridSettingsDialog
from slipsurface.ui.dialogs.project_settings import ProjectSettingsDialog
from slipsurface.ui.dialogs.summary import ProjectSummaryDialog
from slipsurface.ui.dialogs.surface_options import SurfaceOptionsDialog
from slipsurface.ui.document import Document
from slipsurface.ui.icons import color_icon, icon
from slipsurface.ui.statusbar import CadStatusBar
from slipsurface.ui.updates import UpdateChecker, auto_enabled, set_auto_enabled
from slipsurface.ui.worker import AnalysisWorker, start_worker
from slipsurface.ui.workflow import WorkflowBar

FILE_FILTER = "SlipSurfaceIQ LE project (*.slp.json *.json)"
STEPS = ["Geometry", "Support", "Loading", "Properties", "Surfaces"]


class ModelerWindow(QMainWindow):
    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        fit_to_screen(self, 1500, 920)
        self.setIconSize(QSize(24, 24))
        self.doc = Document(project or empty_project())
        self.interpret_windows: list = []
        self._worker = None
        self._thread = None
        self.last_results = None
        self._close_pending = False
        self._cancel_requested = False

        # ------------------------------------------------------ central
        self.area = CadArea(editable=True)
        self.canvas = self.area.canvas
        self.canvas.doc = self.doc
        self.workflow = WorkflowBar(STEPS)
        self.setCentralWidget(self.area)

        # --------------------------------------------------------- docks
        # The left Project dock (Document Viewer + Display Options) is shown
        # only in the Interpret window; the Modeler keeps the full canvas.
        # Display options are still reachable from the View menu / toolbar.
        self.viewer = None
        self.display_opts = None
        self.dock = None

        # ------------------------------------------- actions/menus/toolbars
        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self.status = CadStatusBar(self.canvas, self)
        self.setStatusBar(self.status)
        self.updates = UpdateChecker(self)

        # -------------------------------------------------------- signals
        self.doc.changed.connect(self._on_doc_changed)
        self.doc.undo_stack.cleanChanged.connect(lambda *_: self._update_title())
        self.canvas.drawn.connect(self._on_drawn)
        self.canvas.entity_double_clicked.connect(self.edit_coordinates)
        self.canvas.material_activated.connect(lambda n: self.define_materials(n))
        self.canvas.tool_changed.connect(self._sync_tool_actions)
        self.canvas.selection_changed.connect(lambda *_: self._update_actions())
        self.workflow.step_changed.connect(self._step_changed)

        self._on_doc_changed()
        self.canvas.zoom_extents()
        self._step_changed(0)

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self.canvas.zoom_extents)

    # ============================================================ actions
    def _act(self, text, slot, ic=None, shortcut=None, tip=None, checkable=False):
        a = QAction(text, self)
        if ic:
            a.setIcon(icon(ic))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setToolTip(tip or text.replace("&", "").replace("…", ""))
        a.setStatusTip(tip or text.replace("&", ""))
        a.setCheckable(checkable)
        a.triggered.connect(lambda _=False: slot())
        return a

    def _build_actions(self) -> None:
        A = self._act
        self.a_new = A("&New", self.new_project, "new", QKeySequence.New)
        self.a_open = A("&Open…", self.open_project, "open", QKeySequence.Open)
        self.a_save = A("&Save", self.save_project, "save", QKeySequence.Save)
        self.a_save_as = A("Save &As…", self.save_project_as, None, QKeySequence.SaveAs)
        self.a_export = A("Export Drawing…", self.export_image, "export")
        self.a_quit = A("E&xit", self.close, None, QKeySequence.Quit)

        self.a_undo = self.doc.undo_stack.createUndoAction(self, "Undo")
        self.a_undo.setIcon(icon("undo"))
        self.a_undo.setShortcut(QKeySequence.Undo)
        self.a_redo = self.doc.undo_stack.createRedoAction(self, "Redo")
        self.a_redo.setIcon(icon("redo"))
        self.a_redo.setShortcut(QKeySequence.Redo)
        self.a_delete = A("Delete Selected", self.delete_selection, "delete", "Del")

        self.a_zoom_all = A("Zoom Extents", self.canvas.zoom_extents, "zoom_all", "F2")
        self.a_zoom_in = A("Zoom In", lambda: self.canvas.zoom(1.25), "zoom_in", "Ctrl++")
        self.a_zoom_out = A("Zoom Out", lambda: self.canvas.zoom(0.8), "zoom_out", "Ctrl+-")
        self.a_grid_settings = A("Grid and Snap Settings…", self.grid_settings, "grid")
        self.a_display_opts = A("Display Options…", self.display_options)

        self.a_settings = A("Project Settings…", self.project_settings, "settings", "Ctrl+Shift+J")
        self.a_summary = A("Project Summary…", self.project_summary, "summary")
        self.a_compute = A(
            "Compute",
            self.compute,
            "compute",
            "F5",
            "Compute the critical surfaces with the selected methods",
        )
        self.a_interpret = A(
            "Interpret",
            self.interpret,
            "interpret",
            "F6",
            "Open the results in the Interpret window",
        )
        self.a_report = A(
            "PDF Report…",
            self.pdf_report,
            "report",
            "Ctrl+P",
            "Create a professional PDF report of the last analysis",
        )

        self.a_define_mat = A("Define Materials…", self.define_materials, "materials")
        self.a_surface_opts = A("Surface Options…", self.surface_options, "surface_options")
        self.a_clear_limits = A("Reset Slip Limits", self.clear_slope_limits)
        self.a_coords = A(
            "Edit Coordinates…",
            lambda: self.edit_coordinates(self.canvas.selection),
            "coords",
            None,
            "Edit the vertex coordinates of the selected boundary in a table",
        )

        # tool actions (exclusive)
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        def tool(text, ic, factory, shortcut=None, tip=None):
            a = A(text, lambda: self.canvas.set_tool(factory()), ic, shortcut, tip, True)
            a.setData(factory)
            self.tool_group.addAction(a)
            return a

        c = self.canvas
        self.t_select = tool("Select", "select", lambda: T.SelectTool(c), "Esc")
        self.t_zoom_win = tool("Zoom Window", "zoom_window", lambda: T.ZoomWindowTool(c))
        self.t_pan = tool("Pan", "pan", lambda: T.PanTool(c))
        self.t_measure = tool("Measure", "measure", lambda: T.MeasureTool(c))
        self.t_external = tool("Add External Boundary", "external", lambda: self._draw("external"))
        self.t_material = tool(
            "Add Material Boundary", "material_boundary", lambda: self._draw("material")
        )
        self.t_water = tool("Add Water Table", "water", lambda: self._draw("water"))
        self.t_crack = tool(
            "Add Tension Crack",
            "tension_crack",
            lambda: self._draw("crack"),
            None,
            "Draw the tension crack line (in the crest zone, below the ground)",
        )
        self.a_crack_depth = A("Tension Crack from Depth…", self.crack_from_depth, "tension_crack")
        self.t_add_v = tool("Add Vertex", "add_vertex", lambda: T.AddVertexTool(c))
        self.t_del_v = tool("Delete Vertex", "delete_vertex", lambda: T.DeleteVertexTool(c))
        self.t_assign = tool(
            "Assign Material",
            "assign",
            lambda: T.AssignTool(c),
            None,
            "Assign the selected material to the clicked region",
        )
        self.t_limits = tool(
            "Slip Limits",
            "slope_limits",
            lambda: T.SlopeLimitsTool(c),
            None,
            "Mark the left and right end ranges on the ground",
        )
        self.t_user = tool("Draw User Surface", "user_surface", lambda: self._draw("user"))
        self.t_dist = tool(
            "Add Distributed Load", "load_distributed", lambda: T.DrawTool(c, "load_distributed")
        )
        self.t_line = tool("Add Line Load", "load_line", lambda: T.DrawTool(c, "load_line"))
        self.t_support = tool("Add Support", "support", self._support_tool)
        self.a_seismic = A("Seismic Load…", lambda: self.project_settings(3), "seismic")
        self.a_define_support = A(
            "Define Support Properties…", self.define_supports, "support_props"
        )
        self.t_bolt = tool(
            "Single Bolt/Anchor",
            "bolt",
            self._bolt_tool,
            None,
            (
                "Click on the slope face: a bolt/anchor of the selected support type is "
                "added with the toolbar inclination (default 15°)"
            ),
        )
        self.t_pattern = tool(
            "Bolt Pattern",
            "bolt_pattern",
            self._pattern_tool,
            None,
            (
                "Click the start and end points on the slope face; choose the spacing and "
                "the bolts are placed automatically (group)"
            ),
        )
        self.a_define_facing = A(
            "Define Facing Types…",
            self.define_facings,
            "facing_props",
            None,
            "Define shotcrete + wire mesh facing types",
        )
        self.t_facing = tool(
            "Assign Facing",
            "facing",
            self._facing_tool,
            None,
            "Click the start and end points of the facing on the slope face",
        )
        self.a_facing_face = A(
            "Assign Facing to Slope",
            self.facing_whole_face,
            "facing",
            None,
            "Assign the selected facing to the whole slope face between toe and crest",
        )
        self.t_annots = {}
        for kind, label, ic in ANNOT_TOOLS:
            self.t_annots[kind] = tool(label, ic, lambda k=kind: T.DrawTool(c, k))
        self.label_group = QActionGroup(self)
        self.a_labels = {}
        for val, txt in (
            ("none", "None"),
            ("name", "Material Name"),
            ("full", "Name + Parameters"),
        ):
            a = QAction(txt, self, checkable=True)
            a.triggered.connect(lambda _=False, v=val: self._display_option("material_labels", v))
            self.label_group.addAction(a)
            self.a_labels[val] = a
        self.t_select.setChecked(True)

    def _ensure_support_type(self) -> None:
        if not self.doc.project.support_types:
            self.doc.edit("Add support type", lambda p: p.support_types.append(SupportType()))
            self.status.showMessage(
                (
                    "A default support type was created (change it with Support → Define "
                    "Support Properties)."
                ),
                8000,
            )

    def _support_tool(self):
        self._ensure_support_type()
        return T.DrawTool(self.canvas, "support")

    def _bolt_tool(self):
        self._ensure_support_type()
        return T.BoltTool(self.canvas, self.bolt_angle.value, self.bolt_length.value)

    def _pattern_tool(self):
        self._ensure_support_type()
        return T.DrawTool(self.canvas, "pattern")

    def _ensure_facing_type(self) -> None:
        if not self.doc.project.facing_types:
            self.doc.edit("Add facing type", lambda p: p.facing_types.append(FacingType()))
            self.status.showMessage(
                (
                    "A default facing type was created: 10 cm shotcrete + Q188 (Properties → "
                    "Define Facing Types)."
                ),
                8000,
            )

    def _facing_tool(self):
        self._ensure_facing_type()
        return T.DrawTool(self.canvas, "facing")

    def _draw(self, kind: str):
        if kind == "external" and self.doc.project.external:
            ans = QMessageBox.question(
                self,
                "External boundary",
                (
                    "The model already has an external boundary. Delete it and draw a new "
                    "one?\n(Material boundaries and assignments are deleted too.)"
                ),
            )
            if ans != QMessageBox.Yes:
                return T.SelectTool(self.canvas)
        return T.DrawTool(self.canvas, kind)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&File")
        for a in (self.a_new, self.a_open, self.a_save, self.a_save_as):
            m.addAction(a)
        ex = m.addMenu("Examples")
        for name, factory in EXAMPLES.items():
            ex.addAction(name, lambda f=factory: self._open_example(f))
        m.addSeparator()
        m.addAction("Import DXF…", self.import_dxf)
        m.addAction("Export DXF…", self.export_dxf)
        m.addAction(self.a_export)
        m.addAction(self.a_report)
        m.addSeparator()
        m.addAction(self.a_quit)

        m = mb.addMenu("&Edit")
        m.addAction(self.a_undo)
        m.addAction(self.a_redo)
        m.addSeparator()
        m.addAction(self.a_delete)
        m.addAction(self.a_coords)

        m = mb.addMenu("&View")
        from slipsurface.ui.preferences import apply_theme, settings

        dark = m.addAction("Dark mode")
        dark.setCheckable(True)
        dark.setChecked(settings().value("dark", False, type=bool))
        dark.toggled.connect(apply_theme)
        full = m.addAction("Full screen")
        full.setShortcut("F11")
        full.triggered.connect(
            lambda: self.showMaximized() if self.isFullScreen() else self.showFullScreen()
        )
        for a in (self.a_zoom_all, self.a_zoom_in, self.a_zoom_out, self.t_zoom_win, self.t_pan):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_grid_settings)
        lm = m.addMenu("Material Labels")
        for a in self.a_labels.values():
            lm.addAction(a)
        m.addAction(self.a_display_opts)

        m = mb.addMenu("&Analysis")
        m.addAction(self.a_settings)
        m.addAction(self.a_summary)
        m.addSeparator()
        m.addAction(self.a_compute)
        m.addAction(self.a_interpret)
        m.addAction(self.a_report)

        m = mb.addMenu("&Boundaries")
        for a in (self.t_external, self.t_material, self.t_water):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.t_crack)
        m.addAction(self.a_crack_depth)
        m.addSeparator()
        for a in (self.t_add_v, self.t_del_v):
            m.addAction(a)
        m.addAction(self.a_coords)

        m = mb.addMenu("&Loading")
        m.addAction(self.t_dist)
        m.addAction(self.t_line)
        m.addSeparator()
        m.addAction(self.a_seismic)

        m = mb.addMenu("&Support")
        m.addAction(self.a_define_support)
        m.addAction(self.t_support)
        m.addSeparator()
        m.addAction(self.t_bolt)
        m.addAction(self.t_pattern)

        m = mb.addMenu("&Surfaces")
        m.addAction(self.a_surface_opts)
        m.addAction(self.t_limits)
        m.addAction(self.a_clear_limits)
        m.addSeparator()
        m.addAction(self.t_user)

        m = mb.addMenu("&Properties")
        m.addAction(self.a_define_mat)
        m.addAction(self.t_assign)
        m.addSeparator()
        m.addAction(self.a_define_facing)
        m.addAction(self.t_facing)
        m.addAction(self.a_facing_face)

        m = mb.addMenu("&Tools")
        m.addAction("Python scripting…", self.script_editor)
        m.addAction(self.t_measure)
        am = m.addMenu(icon("annot_text"), "Add Annotation (Text / Shape)")
        for a in self.t_annots.values():
            am.addAction(a)

        m = mb.addMenu("&Help")
        m.addAction("Keyboard Shortcuts", self._shortcuts_help, "F1")
        m.addSeparator()
        m.addAction("Check for Updates…", self.check_updates)
        self.a_auto_updates = m.addAction("Check for Updates at Start-up")
        self.a_auto_updates.setCheckable(True)
        self.a_auto_updates.setChecked(auto_enabled())
        self.a_auto_updates.toggled.connect(set_auto_enabled)
        m.addSeparator()
        m.addAction("About", self._about)

    def _build_toolbars(self) -> None:
        wf = QToolBar("Workflow")
        wf.setObjectName("workflow_toolbar")
        wf.setMovable(False)
        wf.addWidget(self.workflow)
        self.addToolBar(Qt.TopToolBarArea, wf)
        self.addToolBarBreak()
        tb = QToolBar("Main Toolbar")
        tb.setObjectName("main_toolbar")
        tb.setIconSize(QSize(24, 24))
        for a in (
            self.a_new,
            self.a_open,
            self.a_save,
            None,
            self.a_undo,
            self.a_redo,
            None,
            self.a_settings,
            self.a_summary,
            self.a_define_mat,
            None,
            self.a_compute,
            self.a_interpret,
            self.a_report,
            None,
            self.a_zoom_all,
            self.a_zoom_in,
            self.a_zoom_out,
            self.t_zoom_win,
            self.t_pan,
            None,
            self.t_select,
            self.t_measure,
            None,
            self.a_export,
        ):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(Qt.TopToolBarArea, tb)
        notes = QToolBar("Notes")
        notes.setObjectName("notes_toolbar")
        notes.setIconSize(QSize(24, 24))
        for a in self.t_annots.values():
            notes.addAction(a)
        self.addToolBar(Qt.TopToolBarArea, notes)
        self.notes_bar = notes
        self.addToolBarBreak()

        self.step_bars = []
        geo = QToolBar("Geometry")
        geo.setObjectName("geometry_toolbar")
        for a in (
            self.t_external,
            self.t_material,
            self.t_water,
            self.t_crack,
            None,
            self.t_add_v,
            self.t_del_v,
            self.a_coords,
            self.a_delete,
        ):
            geo.addSeparator() if a is None else geo.addAction(a)
        sup = QToolBar("Support")
        sup.setObjectName("support_toolbar")
        sup.addAction(self.a_define_support)
        sup.addSeparator()
        sup.addWidget(QLabel(" Support type: "))
        self.support_combo = QComboBox()
        self.support_combo.setMinimumWidth(170)
        sup.addWidget(self.support_combo)
        sup.addAction(self.t_support)
        sup.addSeparator()
        sup.addWidget(QLabel(" Inclination: "))
        self.bolt_angle = QDoubleSpinBox()
        self.bolt_angle.setRange(-89, 89)
        self.bolt_angle.setDecimals(1)
        self.bolt_angle.setValue(15.0)
        self.bolt_angle.setSuffix(" °")
        self.bolt_angle.setToolTip("Inclination below horizontal (into the slope)")
        sup.addWidget(self.bolt_angle)
        sup.addWidget(QLabel(" Length: "))
        self.bolt_length = QDoubleSpinBox()
        self.bolt_length.setRange(0.5, 200)
        self.bolt_length.setDecimals(2)
        self.bolt_length.setValue(12.0)
        self.bolt_length.setSuffix(" m")
        sup.addWidget(self.bolt_length)
        sup.addAction(self.t_bolt)
        sup.addAction(self.t_pattern)
        self.support_combo.currentTextChanged.connect(self._support_type_changed)
        load = QToolBar("Loading")
        load.setObjectName("loading_toolbar")
        for a in (self.t_dist, self.t_line, None, self.a_seismic):
            load.addSeparator() if a is None else load.addAction(a)
        props = QToolBar("Properties")
        props.setObjectName("properties_toolbar")
        props.addAction(self.a_define_mat)
        props.addSeparator()
        props.addWidget(QLabel(" Material to assign: "))
        self.mat_combo = QComboBox()
        self.mat_combo.setMinimumWidth(170)
        self.mat_combo.currentTextChanged.connect(self._assign_material_changed)
        props.addWidget(self.mat_combo)
        props.addAction(self.t_assign)
        props.addSeparator()
        props.addAction(self.a_define_facing)
        props.addWidget(QLabel(" Facing: "))
        self.facing_combo = QComboBox()
        self.facing_combo.setMinimumWidth(150)
        props.addWidget(self.facing_combo)
        props.addAction(self.t_facing)
        props.addAction(self.a_facing_face)
        surf = QToolBar("Surfaces")
        surf.setObjectName("surfaces_toolbar")
        for a in (
            self.a_surface_opts,
            None,
            self.t_limits,
            self.a_clear_limits,
            None,
            self.t_user,
            None,
            self.a_compute,
        ):
            surf.addSeparator() if a is None else surf.addAction(a)
        for bar in (geo, sup, load, props, surf):
            bar.setIconSize(QSize(24, 24))
            bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            self.addToolBar(Qt.TopToolBarArea, bar)
            self.step_bars.append(bar)

    def _step_changed(self, i: int) -> None:
        for k, bar in enumerate(self.step_bars):
            bar.setVisible(k == i)
        if STEPS[i] == "Properties":
            self.canvas.set_tool(T.AssignTool(self.canvas))
            self.t_assign.setChecked(True)

    # ============================================================ document
    def _on_doc_changed(self) -> None:
        p, g = self.doc.project, self.doc.geometry
        if (
            self.last_results is not None
            and p.analysis_inputs() != self.last_results.project.analysis_inputs()
        ):
            self._invalidate_results()
        if self.last_results is not None and self.last_results.project.summary != p.summary:
            self.last_results.project.summary = copy.deepcopy(p.summary)
            self._prune_interpret_windows()
            for window in self.interpret_windows:
                if window.results is self.last_results:
                    window.update_summary(p.summary)
        self.canvas.set_scene(p, g)
        self.area.show_rulers(bool(p.display_opt("show_ruler")))
        names = p.material_names()
        cur = self.mat_combo.currentText()
        self.mat_combo.blockSignals(True)
        self.mat_combo.clear()
        for m in p.materials:
            self.mat_combo.addItem(color_icon(m.color), m.name)
        self.mat_combo.setCurrentText(cur if cur in names else (names[0] if names else ""))
        self.mat_combo.blockSignals(False)
        self.canvas.assign_material = self.mat_combo.currentText() or None
        snames = [t.name for t in p.support_types]
        scur = self.support_combo.currentText()
        self.support_combo.blockSignals(True)
        self.support_combo.clear()
        for t in p.support_types:
            self.support_combo.addItem(color_icon(t.color), t.name)
        self.support_combo.setCurrentText(scur if scur in snames else (snames[0] if snames else ""))
        self.support_combo.blockSignals(False)
        if self.support_combo.currentText() != scur:
            self._support_type_changed(self.support_combo.currentText())
        fnames = [t.name for t in p.facing_types]
        fcur = self.facing_combo.currentText()
        self.facing_combo.blockSignals(True)
        self.facing_combo.clear()
        for t in p.facing_types:
            self.facing_combo.addItem(color_icon(t.color), t.name)
        self.facing_combo.setCurrentText(fcur if fcur in fnames else (fnames[0] if fnames else ""))
        self.facing_combo.blockSignals(False)
        mode = p.display_opt("material_labels") or "none"
        if mode in self.a_labels:
            self.a_labels[mode].setChecked(True)
        if self.doc.geometry_error and p.has_geometry:
            self.status.showMessage(f"⚠ Model: {self.doc.geometry_error}", 10000)
        self._update_title()
        self._update_actions()

    def _update_title(self) -> None:
        import shiboken6

        if getattr(self, "_closing", False) or not shiboken6.isValid(self.doc.undo_stack):
            return  # application is shutting down
        name = self.doc.path.name if self.doc.path else "Unsaved"
        star = " *" if self.doc.dirty else ""
        self.setWindowTitle(
            f"SlipSurfaceIQ LE {__version__} — [{name}{star}] — {self.doc.project.summary.title}"
        )

    def _update_actions(self) -> None:
        sel = self.canvas.selection
        self.a_coords.setEnabled(sel is not None)
        self.a_delete.setEnabled(sel is not None)
        has_results = self.last_results is not None and bool(self.last_results.results)
        self.a_interpret.setEnabled(has_results and not self.busy)
        self.a_report.setEnabled(has_results and not self.busy)
        self.a_compute.setEnabled(not self.busy)

    def _sync_tool_actions(self, name: str) -> None:
        for a in self.tool_group.actions():
            if a.isChecked():
                break
        if name == "select":
            self.t_select.setChecked(True)

    def _select_entity(self, key) -> None:
        self.canvas.selection = key
        self.canvas.sel_vertex = None
        self.canvas.update()
        self._update_actions()

    def _support_type_changed(self, name: str) -> None:
        st = self.doc.project.support_type(name)
        if st is not None:
            self.bolt_length.setValue(st.length)

    def _assign_material_changed(self, name: str) -> None:
        self.canvas.assign_material = name or None

    def _display_option(self, key, value) -> None:
        self.doc.edit("Display option", lambda p: p.display.__setitem__(key, value))

    def _display_reset(self) -> None:
        self.doc.edit(
            "Display options: defaults",
            lambda p: (p.display.clear(), p.display.update(DEFAULT_DISPLAY)),
        )

    def _make_display_dialog(self):
        """Modeler View-menu replacement for the removed left-dock Display Options."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

        from slipsurface.ui.docks import DisplayOptions

        dlg = QDialog(self)
        dlg.setWindowTitle("Display Options")
        fit_to_screen(dlg, 340, 520)
        opts = DisplayOptions(dlg)
        opts.setObjectName("modeler_display_options")
        opts.set_values(self.doc.project.display)

        def reset() -> None:
            self._display_reset()
            opts.set_values(self.doc.project.display)

        opts.option_changed.connect(self._display_option)
        opts.reset_requested.connect(reset)
        lay = QVBoxLayout(dlg)
        lay.addWidget(opts, 1)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.button(QDialogButtonBox.Close).setText("Close")
        box.rejected.connect(dlg.close)
        lay.addWidget(box)
        return dlg

    def display_options(self) -> None:
        self._make_display_dialog().exec()

    # ============================================================ drawing
    def _on_drawn(self, kind: str, pts: list) -> None:
        if kind in ("load_distributed", "load_line", "support"):
            self._add_load_or_support(kind, pts)
            return
        if kind == "bolt":
            name = self.support_combo.currentText()
            sp = {"a": pts[0], "b": pts[1], "type": name}
            if self.canvas.request_edit("Add bolt/anchor", lambda p: p.supports.append(sp)):
                self.status.showMessage(
                    (
                        f"{name} added: head ({pts[0][0]:.2f}, {pts[0][1]:.2f}), inclination "
                        f"{self.bolt_angle.value():g}°, length {self.bolt_length.value():g} m. "
                        "Click to continue, Esc = finish."
                    ),
                    8000,
                )
            return  # tool stays active
        if kind == "pattern":
            self._add_pattern(pts)
            return
        if kind == "facing":
            self._add_facing(pts[0][0], pts[1][0])
            self.canvas.select_tool()
            self.t_select.setChecked(True)
            return
        if kind.startswith("annot_"):
            ann = new_annotation(kind, pts, self)
            if ann is not None:
                self.canvas.request_edit("Add note", lambda p: p.annotations.append(ann))
            self.canvas.select_tool()
            self.t_select.setChecked(True)
            return

        def fn(p):
            if kind == "external":
                p.external = []
                p.material_boundaries = []
                p.assignments = []
            add_entity(p, kind, pts)

        ok = self.canvas.request_edit(f"Add {LABELS[kind]}", fn)
        if ok:
            self.status.showMessage(f"{LABELS[kind]} added ({len(pts)} points).", 5000)
            if kind == "external":
                self.canvas.zoom_extents()
        self.canvas.select_tool()
        self.t_select.setChecked(True)

    def _ground(self):
        g = self.doc.geometry
        return g.ground_y if g is not None else None

    def _add_load_or_support(self, kind: str, pts: list) -> None:
        gy = self._ground()
        if kind == "support":
            name = self.support_combo.currentText()
            sp = {"a": pts[0], "b": pts[1], "type": name}
            self.canvas.request_edit("Add support", lambda p: p.supports.append(sp))
            self.status.showMessage(f"Support added ({name}).", 5000)
            self.canvas.set_tool(T.DrawTool(self.canvas, "support"))  # keep adding
            return
        if kind == "load_distributed":
            ld = {
                "kind": "distributed",
                "points": pts,
                "q": [20.0, 20.0],
                "orientation": "vertical",
            }
            dlg = DistributedLoadDialog(ld, self)
        else:
            ld = {"kind": "line", "point": pts[0], "magnitude": 50.0, "angle": 270.0}
            dlg = LineLoadDialog(ld, self)
        if dlg.exec():
            dlg.apply_to(ld, gy)
            self.canvas.request_edit("Add load", lambda p: p.loads.append(ld))
        self.canvas.select_tool()
        self.t_select.setChecked(True)

    def _pattern_count_fn(self):
        g = self.doc.geometry
        if g is None:
            return None
        return lambda x1, x2, s, o: len(pattern_positions(g, x1, x2, s, o))

    def _add_pattern(self, pts) -> None:
        gy = self._ground()
        self.canvas.select_tool()
        self.t_select.setChecked(True)
        if gy is None:
            return
        x1, x2 = sorted((pts[0][0], pts[1][0]))
        pt = {
            "p1": [x1, float(gy(x1))],
            "p2": [x2, float(gy(x2))],
            "spacing": 2.0,
            "offset": 1.0,
            "angle": self.bolt_angle.value(),
            "length": self.bolt_length.value(),
            "type": self.support_combo.currentText(),
        }
        dlg = PatternDialog(
            pt, [t.name for t in self.doc.project.support_types], self._pattern_count_fn(), self
        )
        if dlg.exec():
            dlg.apply_to(pt, gy)
            if self.canvas.request_edit(
                "Add bolt pattern", lambda p: p.support_patterns.append(pt)
            ):
                n = self._pattern_count_fn()(pt["p1"][0], pt["p2"][0], pt["spacing"], pt["offset"])
                self.status.showMessage(f"Bolt pattern added: {n} × {pt['type']}.", 8000)

    def _add_facing(self, x1: float, x2: float) -> bool:
        gy = self._ground()
        if gy is None:
            return False
        x1, x2 = sorted((float(x1), float(x2)))
        if x2 - x1 < 1e-6:
            return False
        f = {
            "x1": x1,
            "x2": x2,
            "type": self.facing_combo.currentText(),
            "points": [[x1, float(gy(x1))], [x2, float(gy(x2))]],
        }
        ok = self.canvas.request_edit("Assign facing", lambda p: p.facings.append(f))
        if ok:
            self.status.showMessage(
                f"Facing '{f['type']}' assigned: x = {x1:.2f} … {x2:.2f}.", 8000
            )
        return ok

    def slope_face_range(self, min_angle: float = 20.0):
        """x range of the slope face: ground segments steeper than `min_angle`."""
        import math

        g = self.doc.geometry
        if g is None:
            return None
        s = g.surface
        xs = []
        for (xa, ya), (xb, yb) in zip(s[:-1], s[1:], strict=False):
            if xb - xa > 1e-9 and math.degrees(math.atan2(abs(yb - ya), xb - xa)) >= min_angle:
                xs += [xa, xb]
        return (min(xs), max(xs)) if xs else None

    def facing_whole_face(self) -> None:
        rng = self.slope_face_range()
        if rng is None:
            QMessageBox.information(
                self,
                "Facing",
                (
                    "No slope face found (no ground segment steeper than 20°). Use the Assign "
                    "Facing tool."
                ),
            )
            return
        self._ensure_facing_type()
        self._on_doc_changed()
        self._add_facing(*rng)

    def define_facings(self) -> None:
        dlg = FacingTypesDialog(self.doc.project.facing_types, self)
        if dlg.exec():
            types, ren = dlg.types, dlg.renames
            names = {t.name for t in types}

            def fn(p):
                p.facing_types = types
                for f in p.facings:
                    f["type"] = ren.get(f["type"], f["type"])
                    if f["type"] not in names:
                        f["type"] = types[0].name

            self.doc.edit("Facing types", fn)

    def crack_from_depth(self) -> None:
        import math

        p, g = self.doc.project, self.doc.geometry
        if g is None:
            QMessageBox.warning(self, "Tension crack", "Draw a valid external boundary first.")
            return
        surf = g.surface
        # default range: crest (highest ground) towards the uphill model edge
        ymax = surf[:, 1].max()
        crest = surf[surf[:, 1] >= ymax - 1e-9][:, 0]
        uphill_right = surf[-1, 1] >= surf[0, 1]
        x1, x2 = (crest.min(), g.x_max) if uphill_right else (g.x_min, crest.max())
        if p.tension_crack:
            xs = [q[0] for q in p.tension_crack]
            x1, x2 = min(xs), max(xs)
        # Rankine crack depth for the first material (suggestion)
        m = p.materials[0]
        zc, note = 2.0, ""
        if m.model == "MC" and m.c > 0:
            ka = math.tan(math.radians(45 - m.phi / 2)) ** 2
            zc = 2 * m.c / (m.gamma * math.sqrt(ka))
            note = f"Suggestion (Rankine, {m.name}): z_c = 2c / (γ·√Ka) = {zc:.2f} m"
        dlg = CrackFromDepthDialog(x1, x2, round(zc, 2), p.groundwater.crack_water, note, self)
        if dlg.exec():
            pts = dlg.points(surf)
            w = dlg.water.value() / 100.0

            def fn(q):
                q.tension_crack = pts
                q.groundwater.crack_water = w

            self.doc.edit("Tension crack", fn)

    def define_supports(self, select: str | None = None) -> None:
        dlg = SupportTypesDialog(self.doc.project.support_types, self, select)
        if dlg.exec():
            types, ren = dlg.types, dlg.renames
            names = {t.name for t in types}

            def fn(p):
                p.support_types = types
                for sp in p.supports + p.support_patterns:
                    sp["type"] = ren.get(sp["type"], sp["type"])
                    if sp["type"] not in names:
                        sp["type"] = types[0].name

            self.doc.edit("Support properties", fn)

    def edit_coordinates(self, key) -> None:
        if key is None:
            return
        if key[0] == "load":
            ld = dict(self.doc.project.loads[key[1]])
            ld = __import__("copy").deepcopy(ld)
            dlg = (DistributedLoadDialog if ld["kind"] == "distributed" else LineLoadDialog)(
                ld, self
            )
            if dlg.exec():
                dlg.apply_to(ld, self._ground())
                self.doc.edit("Edit load", lambda p: p.loads.__setitem__(key[1], ld))
            return
        if key[0] == "support":
            sp = __import__("copy").deepcopy(self.doc.project.supports[key[1]])
            dlg = SupportEditDialog(sp, [t.name for t in self.doc.project.support_types], self)
            if dlg.exec():
                dlg.apply_to(sp)
                self.doc.edit("Edit support", lambda p: p.supports.__setitem__(key[1], sp))
            return
        if key[0] == "pattern":
            pt = copy.deepcopy(self.doc.project.support_patterns[key[1]])
            dlg = PatternDialog(
                pt, [t.name for t in self.doc.project.support_types], self._pattern_count_fn(), self
            )
            if dlg.exec():
                dlg.apply_to(pt, self._ground())
                self.doc.edit(
                    "Edit bolt pattern", lambda p: p.support_patterns.__setitem__(key[1], pt)
                )
            return
        if key[0] == "facing":
            f = copy.deepcopy(self.doc.project.facings[key[1]])
            dlg = FacingEditDialog(f, [t.name for t in self.doc.project.facing_types], self)
            if dlg.exec():
                dlg.apply_to(f, self._ground())
                self.doc.edit("Edit facing", lambda p: p.facings.__setitem__(key[1], f))
            return
        if key[0] == "annot":
            edit_annotation(self.doc, key[1], self)
            return
        pts = get_points(self.doc.project, key)
        title = LABELS[key[0]] + (f" {key[1] + 1}" if key[0] == "material" else "")
        dlg = CoordinatesDialog(title, pts, self, MIN_POINTS[key[0]])
        if dlg.exec():
            new = dlg.points()
            try:
                self.doc.edit(f"{title}: coordinates", lambda p: set_points(p, key, new))
            except ValueError as exc:
                QMessageBox.warning(self, "Coordinates", str(exc))

    def delete_selection(self) -> None:
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)
        T.SelectTool(self.canvas).key(ev)

    def clear_slope_limits(self) -> None:
        def fn(p):
            p.surfaces.left_range = None
            p.surfaces.right_range = None

        self.doc.edit("Reset slope limits", fn)

    # ============================================================ dialogs
    def project_settings(self, page: int = 0) -> None:
        dlg = ProjectSettingsDialog(self.doc.project, self, page)
        if dlg.exec():
            new = dlg.result_project

            def fn(p):
                p.general, p.methods, p.groundwater = new.general, new.methods, new.groundwater
                p.seismic, p.advanced = new.seismic, new.advanced

            self.doc.edit("Project settings", fn)

    def project_summary(self) -> None:
        dlg = ProjectSummaryDialog(self.doc.project.summary, self)
        if dlg.exec():
            s = dlg.summary()
            self.doc.edit("Project summary", lambda p: setattr(p, "summary", s))

    def define_materials(self, select: str | None = None) -> None:
        dlg = MaterialsDialog(self.doc.project.materials, self, select)
        if dlg.exec():
            mats = dlg.result_materials()
            renames = dlg.renames
            names = {m.name for m in mats}

            def fn(p):
                p.materials = mats
                for a in p.assignments:
                    a["material"] = renames.get(a["material"], a["material"])
                p.assignments = [a for a in p.assignments if a["material"] in names]

            self.doc.edit("Material properties", fn)

    def surface_options(self) -> None:
        dlg = SurfaceOptionsDialog(self.doc.project, self)
        if dlg.exec():
            self.doc.edit("Surface options", dlg.apply_to)

    def grid_settings(self) -> None:
        dlg = GridSettingsDialog(self.canvas.grid_spacing, self)
        if dlg.exec():
            self.canvas.grid_spacing = dlg.spacing.value()
            self.canvas.update()

    # ============================================================== files
    def _confirm_discard(self) -> bool:
        if not self.doc.dirty:
            return True
        ans = QMessageBox.question(
            self,
            "Unsaved Changes",
            "The model has changed. Continue without saving?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        if ans == QMessageBox.Save:
            return self.save_project()
        return ans == QMessageBox.Discard

    def load_project(self, p: Project, path: Path | None = None) -> None:
        self._invalidate_results()
        self.doc.set_project(p, path)
        self.last_results = None
        self.canvas.select_tool()
        self.canvas.zoom_extents()
        self._update_actions()

    def new_project(self) -> None:
        if self._confirm_discard():
            self.load_project(empty_project())
            self.status.showMessage(
                "New project: start with Boundaries → Add External Boundary.", 8000
            )

    def _open_example(self, factory) -> None:
        if self._confirm_discard():
            self.load_project(factory())

    def open_project(self, path: str | None = None) -> None:
        if not self._confirm_discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", FILE_FILTER)
            if not path:
                return
        try:
            p = Project.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could Not Open", f"{path}\n\n{exc}")
            return
        self.load_project(p, Path(path))
        self.status.showMessage(f"Opened: {path}", 5000)

    def save_project(self) -> bool:
        if self.doc.path is None:
            return self.save_project_as()
        return self._write(self.doc.path)

    def save_project_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save As", "model.slp.json", FILE_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".json"):
            path += ".slp.json"
        return self._write(Path(path))

    def _write(self, path: Path) -> bool:
        try:
            self.doc.project.save(path)
        except OSError as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return False
        self.doc.path = Path(path)
        self.doc.mark_clean()
        self._update_title()
        self.status.showMessage(f"Saved: {path}", 5000)
        return True

    def export_image(self) -> None:
        from slipsurface.ui.export import export_image

        export_image(self, self.area, "model.png")

    # ============================================================ compute
    @property
    def busy(self) -> bool:
        return self._worker is not None or self._thread is not None

    def compute(self) -> None:
        if self.busy:
            return
        p = self.doc.project
        if self.doc.geometry is None:
            QMessageBox.warning(self, "Compute", self.doc.geometry_error or "Invalid Model.")
            return
        if not p.methods.methods:
            QMessageBox.warning(
                self, "Compute", "Project Settings → Methods: select at least one method."
            )
            return
        n = len(p.methods.methods)
        self._cancel_requested = False
        from slipsurface.ui.dialogs.compute import ComputeDialog

        self.progress = ComputeDialog(n, p.summary.title, self)
        self.progress.canceled.connect(self._cancel_compute)
        self.progress.show()
        self._maxiter = max(1, {"fast": 50, "normal": 80, "fine": 150}.get(p.surfaces.effort, 80))
        self._worker = AnalysisWorker(p.copy())
        self._worker.progress.connect(self._on_progress)
        self._worker.detail.connect(self._on_detail)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._thread = start_worker(self._worker, self)
        self._thread.finished.connect(self._on_thread_finished)
        self._update_actions()

    def _on_progress(self, i, n, m, gen, best) -> None:
        if self._cancel_requested or self._close_pending:
            return
        if not hasattr(self, "progress") or self.progress is None:
            return
        frac = 0.0 if gen <= 0 else min(abs(gen) / self._maxiter, 0.99)
        self.progress.setValue(int(100 * i + 100 * frac))

    def _on_detail(self, status: dict) -> None:
        if self._cancel_requested or self._close_pending:
            return
        if getattr(self, "progress", None) is not None:
            self.progress.update_status(status)

    def _cancel_compute(self) -> None:
        self._cancel_requested = True
        if self._worker is not None:
            self._worker.request_stop()
            self.status.showMessage("Cancelling computation…", 0)

    def _end_compute(self) -> None:
        if getattr(self, "progress", None) is not None:
            self.progress.canceled.disconnect()
            self.progress.finish()
            self.progress = None
        self._update_actions()

    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._update_actions()
        if self._close_pending:
            QTimer.singleShot(0, self.close)

    def _on_finished(self, results) -> None:
        self._end_compute()
        if self._close_pending or self._cancel_requested:
            return
        if results.project.analysis_inputs() != self.doc.project.analysis_inputs():
            self.status.showMessage("The model changed; compute again (F5).", 8000)
            return
        self._invalidate_results()
        # Summary edits may have been made while the worker was solving.
        results.project.summary = copy.deepcopy(self.doc.project.summary)
        self.last_results = results
        self._update_actions()
        gm = results.global_minimum()
        if gm:
            self.status.showMessage(
                (
                    f"Computation finished ({results.elapsed:.1f} s). Global minimum: "
                    f"{method_name(gm[0])} FS = {gm[1].fos:.3f}"
                ),
                15000,
            )
        if results.errors and not results.results:
            QMessageBox.warning(
                self,
                "Compute",
                "\n".join(f"{method_name(k)}: {v}" for k, v in results.errors.items()),
            )
            return
        self.interpret()

    def _on_failed(self, msg) -> None:
        self._end_compute()
        if self._close_pending:
            return
        QMessageBox.critical(self, "Computation Error", msg)

    def _on_cancelled(self) -> None:
        self._end_compute()
        self.status.showMessage("Computation cancelled.", 6000)

    def _invalidate_results(self) -> None:
        self.last_results = None
        self._prune_interpret_windows()
        for window in list(self.interpret_windows):
            window.close()
        self._prune_interpret_windows()
        self.status.showMessage("The model changed; compute again (F5).", 8000)

    def interpret(self) -> None:
        if self.last_results is None or not self.last_results.results:
            self.status.showMessage("Run Compute (F5) first.", 5000)
            return
        self._prune_interpret_windows()
        for window in self.interpret_windows:
            if window.results is self.last_results:
                if window.isMinimized():
                    window.showNormal()
                window.raise_()
                window.activateWindow()
                return
        from slipsurface.ui.interpret import InterpretWindow

        w = InterpretWindow(
            self.last_results,
            self.doc.path,
            annotations=self.doc.project.result_annotations,
            on_annotations=self._result_annotations_changed,
        )
        from slipsurface.ui.preferences import show_screen_sized

        show_screen_sized(w)
        w.canvas.zoom_extents()
        self._prune_interpret_windows()
        self.interpret_windows.append(w)
        # the window deletes itself on close (WA_DeleteOnClose): drop our reference
        w.destroyed.connect(lambda *_: self._prune_interpret_windows())

    def pdf_report(self) -> None:
        from slipsurface.ui.dialogs.report import export_report

        disp = self.doc.project.copy()
        disp.annotations = copy.deepcopy(self.doc.project.result_annotations)
        export_report(self, self.last_results, disp, self.doc.path)

    def _result_annotations_changed(self, notes: list) -> None:
        """Notes drawn in an Interpret window are stored in the project."""
        import shiboken6

        if getattr(self, "_closing", False) or not shiboken6.isValid(self):
            return
        notes = copy.deepcopy(notes)
        self.doc.edit("Result notes", lambda p: setattr(p, "result_annotations", notes))

    def _prune_interpret_windows(self) -> None:
        """Keep only Interpret windows whose C++ object still exists."""
        import shiboken6

        self.interpret_windows = [
            x for x in self.interpret_windows if shiboken6.isValid(x) and x.isVisible()
        ]

    # ============================================================== misc
    def _shortcuts_help(self) -> None:
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            (
                "Mouse: wheel = zoom, middle drag = pan, middle double-click = zoom "
                "all\nF2 zoom all   F5 compute   F6 interpret\nF3 OSNAP   F7 GRID   F8 "
                "ORTHO   F9 SNAP\nDrawing: click / type coordinates (x,y  @dx,dy  "
                "@L<angle), Enter finish, C close,\nBackspace undo last point, Esc "
                "cancel\nSelect: drag a vertex, double-click = coordinate table, Delete = "
                "delete, right-click = menu\nCtrl+Z / Ctrl+Y undo / redo\nLoads and "
                "supports: double-click = properties, drag = move, Delete = delete\nSingle "
                "bolt: enter inclination/length in the Support step and click the slope "
                "face\nNotes (text/shapes): drag = move, double-click = properties, Delete "
                "= delete"
            ),
        )

    def script_editor(self):
        from slipsurface.ui.dialogs.script import ScriptDialog

        ScriptDialog(self.doc, self).exec()
        self.canvas.zoom_extents()

    def import_dxf(self):
        from slipsurface.exchange import import_dxf

        path, _ = QFileDialog.getOpenFileName(self, "Import DXF", "", "DXF (*.dxf)")
        if not path:
            return
        try:
            project, warnings = import_dxf(path)
            self.doc.edit("Import DXF", lambda p: p.__dict__.update(project.__dict__))
            self.canvas.zoom_extents()
            QMessageBox.information(self, "DXF", "\n".join(warnings))
        except Exception as exc:
            QMessageBox.warning(self, "DXF", str(exc))

    def export_dxf(self):
        from slipsurface.exchange import export_dxf

        path, _ = QFileDialog.getSaveFileName(self, "Export DXF", "", "DXF (*.dxf)")
        if path:
            try:
                export_dxf(self.doc.project, path)
            except Exception as exc:
                QMessageBox.warning(self, "DXF", str(exc))

    def _about(self) -> None:
        from slipsurface.ui.preferences import TECHNOLOGIES

        box = QMessageBox(QMessageBox.NoIcon, "About", TECHNOLOGIES, QMessageBox.NoButton, self)
        box.setTextFormat(Qt.RichText)
        box.setTextInteractionFlags(Qt.TextBrowserInteraction)
        box.setIconPixmap(self.windowIcon().pixmap(64, 64))
        check = box.addButton("Check for Updates…", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        if box.clickedButton() is check:
            self.check_updates()

    def check_updates(self) -> None:
        """Help → Check for Updates (always reports the outcome)."""
        self.updates.check(manual=True)

    def auto_check_updates(self) -> None:
        """Silent start-up check, at most once a day (see ui.updates)."""
        self.updates.check_if_due()

    def closeEvent(self, ev) -> None:
        if not self._close_pending and not self._confirm_discard():
            ev.ignore()
            return
        if self.busy:
            self._close_pending = True
            self._cancel_compute()
            self.status.showMessage("Stopping computation; the window will close afterwards…", 0)
            self.setEnabled(False)
            ev.ignore()
            return
        self._closing = True
        try:
            self.doc.undo_stack.cleanChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._prune_interpret_windows()
        for w in list(self.interpret_windows):
            w.close()
        super().closeEvent(ev)
