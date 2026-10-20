"""SlipSurface LE Interpret — results window (opens separately, like Slide2 Interpret)."""

from __future__ import annotations

from slipsurface.ui.i18n import tr

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QLabel,
    QMainWindow,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from slipsurface import __version__
from slipsurface.analysis import report_text
from slipsurface.lem import method_name
from slipsurface.project import DEFAULT_DISPLAY
from slipsurface.ui.annotations import ANNOT_TOOLS, edit_annotation, new_annotation
from slipsurface.ui.cad import CadArea
from slipsurface.ui.cad import tools as T
from slipsurface.ui.dialogs.misc import InfoViewer, SliceDataDialog, slice_rows
from slipsurface.ui.docks import DisplayOptions, DocumentViewer
from slipsurface.ui.document import Document
from slipsurface.ui.icons import icon
from slipsurface.ui.statusbar import CadStatusBar


class InterpretWindow(QMainWindow):
    def __init__(self, results, path=None, parent=None, annotations=None,
                 on_annotations=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(1450, 900)
        self.results = results
        self.path = path
        self.on_annotations = on_annotations
        # local copy of the analysed project: display options + result notes.
        # Only the notes are editable here (own undo stack); they are passed
        # back to the Modeler through `on_annotations`.
        pr = results.project.copy()
        pr.annotations = [dict(a) for a in (annotations if annotations is not None
                                            else pr.result_annotations)]
        self._display = pr.display
        self._display["show_vertices"] = False   # clean result drawing (no edit handles)
        self.doc = Document(pr)
        gm = results.global_minimum()
        self.key = gm[0] if gm else (next(iter(results.results), None))

        self.area = CadArea(editable=True)
        self.canvas = self.area.canvas
        self.canvas.doc = self.doc
        self.canvas.edit_kinds = {"annot"}
        self.result_warning = QLabel()
        self.result_warning.setTextFormat(Qt.PlainText)
        self.result_warning.setWordWrap(True)
        self.result_warning.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_warning.setStyleSheet(
            "QLabel { background: #fff4d6; color: #674900; padding: 10px; "
            "border: 1px solid #e2c36f; border-radius: 4px; }")
        if results.errors:
            details = "\n".join(f"{method_name(k)}: {v}" for k, v in results.errors.items())
            self.result_warning.setText(
                f"{len(results.errors)} yöntem için sonuç alınamadı. "
                "Gösterilen minimum yalnızca tamamlanan yöntemlere aittir.\n" + details)
        self.result_warning.setVisible(bool(results.errors))
        center = QWidget()
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.result_warning)
        layout.addWidget(self.area, 1)
        self.setCentralWidget(center)

        self.viewer = DocumentViewer(interpret=True)
        self.display_opts = DisplayOptions(interpret=True)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.viewer)
        split.addWidget(self.display_opts)
        split.setSizes([300, 500])
        dock = QDockWidget(tr("Sonuçlar"), self)
        dock.setWidget(split)
        dock.setTitleBarWidget(QWidget())
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self.resizeDocks([dock], [300], Qt.Horizontal)

        self._build()
        self.status = CadStatusBar(self.canvas, self, with_command=False)
        self.setStatusBar(self.status)

        self.viewer.method_activated.connect(self.set_method)
        self.viewer.entity_activated.connect(self._select_entity)
        self.doc.changed.connect(self._on_doc_changed)
        self.canvas.drawn.connect(self._on_drawn)
        self.canvas.entity_double_clicked.connect(self._edit_entity)
        self.display_opts.option_changed.connect(self._display_option)
        self.display_opts.reset_requested.connect(self._display_reset)
        self.display_opts.set_values(self.project.display)
        self._refresh()

    @property
    def project(self):
        return self.doc.project

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.canvas.zoom_extents)

    # ------------------------------------------------------------ build
    def _act(self, text, slot, ic=None, shortcut=None, checkable=False):
        a = QAction(text, self)
        if ic:
            a.setIcon(icon(ic))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setToolTip(text)
        a.setCheckable(checkable)
        a.triggered.connect(lambda _=False: slot())
        return a

    def _build(self) -> None:
        c = self.canvas
        A = self._act
        self.a_global = A("Global Minimum", self.show_global_min, "global_min")
        self.a_all = A(tr("Tüm Yüzeyler"), self._toggle_all, "all_surfaces", None, True)
        self.a_all.setChecked(bool(self.project.display_opt("show_all_surfaces")))
        self.a_info = A(tr("Bilgi Görüntüleyici…"), self.info_viewer, "info", "F10")
        self.a_slice = A("Dilim Verisi", lambda: c.set_tool(T.SliceQueryTool(c, self.slice_data)),
                         "slice_query", None, True)
        self.a_legend = A("Lejant", self._toggle_legend, "legend", None, True)
        self.a_legend.setChecked(bool(self.project.display_opt("show_legend")))
        self.a_zoom_all = A(tr("Tümünü Göster"), c.zoom_extents, "zoom_all", "F2")
        self.a_zoom_in = A(tr("Yakınlaştır"), lambda: c.zoom(1.25), "zoom_in")
        self.a_zoom_out = A(tr("Uzaklaştır"), lambda: c.zoom(0.8), "zoom_out")
        self.a_zoom_win = A(tr("Pencereyle Zoom"), lambda: c.set_tool(T.ZoomWindowTool(c)),
                            "zoom_window")
        self.a_pan = A(tr("Kaydır"), lambda: c.set_tool(T.PanTool(c)), "pan")
        self.a_select = A(tr("Seç"), c.select_tool, "select", "Esc")
        self.a_measure = A(tr("Ölç"), lambda: c.set_tool(T.MeasureTool(c)), "measure")
        self.a_export = A(tr("Resmi Dışa Aktar…"), self.export_image, "export")
        self.a_report = A(tr("PDF Rapor…"), self.pdf_report, "report", "Ctrl+P")
        self.a_report.setToolTip("Profesyonel PDF analiz raporu oluştur")
        self.a_close = A(tr("Kapat"), self.close, None, QKeySequence.Close)
        self.a_undo = self.doc.undo_stack.createUndoAction(self, tr("Geri al"))
        self.a_undo.setIcon(icon("undo"))
        self.a_undo.setShortcut(QKeySequence.Undo)
        self.a_redo = self.doc.undo_stack.createRedoAction(self, tr("Yinele"))
        self.a_redo.setIcon(icon("redo"))
        self.a_redo.setShortcut(QKeySequence.Redo)
        self.a_fs_legend = A(tr("FS Lejantı"), self._toggle_fs_legend, "legend", None, True)
        self.a_fs_legend.setToolTip("Sağ altta seçili yöntemlerin güvenlik sayıları")
        self.a_fs_legend.setChecked(bool(self.project.display_opt("show_fs_legend")))
        self.annot_group = QActionGroup(self)
        self.t_annots = {}
        for kind, label, ic in ANNOT_TOOLS:
            a = A(label, lambda k=kind: c.set_tool(T.DrawTool(c, k)), ic, None, True)
            self.annot_group.addAction(a)
            self.t_annots[kind] = a
        self.annot_group.setExclusive(False)
        c.tool_changed.connect(self._sync_annot_actions)
        self.a_delete = A(tr("Seçili Notu Sil"), self._delete_selection, "delete", "Del")

        self.method_combo = QComboBox()
        self.method_combo.setMinimumWidth(260)
        for k, r in self.results.results.items():
            self.method_combo.addItem(f"{method_name(k)}  FS: {r.fos:.3f}", k)
        if self.key is not None:
            self.method_combo.setCurrentIndex(self.method_combo.findData(self.key))
        self.method_combo.currentIndexChanged.connect(
            lambda i: self.set_method(self.method_combo.itemData(i)))

        tb = QToolBar(tr("Yorumla"))
        tb.setIconSize(QSize(24, 24))
        tb.addWidget(self.method_combo)
        for a in (self.a_global, None, self.a_all, self.a_slice, self.a_legend, None,
                  self.a_info, self.a_report, self.a_export, None, self.a_zoom_all, self.a_zoom_in,
                  self.a_zoom_out, self.a_zoom_win, self.a_pan, None, self.a_select,
                  self.a_measure):
            tb.addSeparator() if a is None else tb.addAction(a)
        self.addToolBar(Qt.TopToolBarArea, tb)
        nb = QToolBar(tr("Notlar"))
        nb.setIconSize(QSize(24, 24))
        for a in (*self.t_annots.values(), None, self.a_undo, self.a_redo, self.a_delete):
            nb.addSeparator() if a is None else nb.addAction(a)
        self.addToolBar(Qt.TopToolBarArea, nb)
        self.notes_bar = nb

        mb = self.menuBar()
        m = mb.addMenu(tr("&Dosya"))
        m.addAction(self.a_report)
        m.addAction(self.a_export)
        m.addSeparator()
        m.addAction(self.a_close)
        m = mb.addMenu(tr("Dü&zen"))
        for a in (self.a_undo, self.a_redo, None, self.a_delete):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu(tr("&Görünüm"))
        for a in (self.a_zoom_all, self.a_zoom_in, self.a_zoom_out, self.a_zoom_win, self.a_pan,
                  None, self.a_all, self.a_legend, self.a_fs_legend):
            m.addSeparator() if a is None else m.addAction(a)
        m = mb.addMenu("&Veri")
        m.addAction(self.a_info)
        m.addAction(self.a_slice)
        m.addAction(self.a_global)
        m = mb.addMenu("&Sorgu")
        m.addAction(self.a_slice)
        m.addAction(self.a_measure)
        m = mb.addMenu(tr("&Araçlar"))
        am = m.addMenu(icon("annot_text"), tr("Not Ekle (Yazı / Şekil)"))
        for a in self.t_annots.values():
            am.addAction(a)

    # ------------------------------------------------------------ state
    def _refresh(self) -> None:
        self.canvas.set_scene(self.project, self.results.geometry, self.results, self.key)
        self.viewer.refresh(self.project, self.path, self.results, self.key)
        self.area.show_rulers(bool(self.project.display_opt("show_ruler")))
        name = self.path.name if self.path else tr("Kaydedilmemiş")
        mname = method_name(self.key) if self.key else "—"
        self.setWindowTitle(f"SlipSurface LE Yorumla {__version__} — {name} — "
                            f"[{self.project.summary.title}] — {mname}")
        r = self.results.results.get(self.key)
        if r is not None:
            lam = f", λ = {r.lem.lam:.3f}" if r.lem.lam == r.lem.lam else ""
            self.status.showMessage(f"{mname}: FS = {r.fos:.3f}{lam} — çıkış x = "
                                    f"{r.slices.x_exit:.2f}, giriş x = {r.slices.x_entry:.2f} — "
                                    f"{r.message}", 0)

    def set_method(self, key) -> None:
        if key is None or key not in self.results.results:
            return
        self.key = key
        self.canvas.highlight_slice = None
        self.method_combo.blockSignals(True)
        self.method_combo.setCurrentIndex(self.method_combo.findData(key))
        self.method_combo.blockSignals(False)
        self._refresh()

    def show_global_min(self) -> None:
        gm = self.results.global_minimum()
        if gm:
            self.set_method(gm[0])

    def _display_option(self, key, value) -> None:
        self.project.display[key] = value
        if key == "show_all_surfaces":
            self.a_all.setChecked(bool(value))
        if key == "show_legend":
            self.a_legend.setChecked(bool(value))
        if key == "show_fs_legend":
            self.a_fs_legend.setChecked(bool(value))
        self._refresh()

    def _display_reset(self) -> None:
        self._display.clear()
        self._display.update(DEFAULT_DISPLAY)
        self._display["show_vertices"] = False
        self._sync_display_actions()
        self.display_opts.set_values(self.project.display)
        self._refresh()

    def _toggle_all(self) -> None:
        self.project.display["show_all_surfaces"] = self.a_all.isChecked()
        self.display_opts.set_values(self.project.display)
        self._refresh()

    def _toggle_legend(self) -> None:
        self.project.display["show_legend"] = self.a_legend.isChecked()
        self.display_opts.set_values(self.project.display)
        self._refresh()

    def _toggle_fs_legend(self) -> None:
        self.project.display["show_fs_legend"] = self.a_fs_legend.isChecked()
        self.display_opts.set_values(self.project.display)
        self._refresh()

    def _sync_display_actions(self) -> None:
        for action, key in ((self.a_all, "show_all_surfaces"),
                            (self.a_legend, "show_legend"),
                            (self.a_fs_legend, "show_fs_legend")):
            action.setChecked(bool(self.project.display_opt(key)))

    # ------------------------------------------------------------ notes
    def _on_doc_changed(self) -> None:
        self.doc.project.display = self._display      # display options are not undone
        self._refresh()
        if self.on_annotations is not None:
            self.on_annotations([dict(a) for a in self.doc.project.annotations])

    def _on_drawn(self, kind: str, pts: list) -> None:
        if kind.startswith("annot_"):
            ann = new_annotation(kind, pts, self)
            if ann is not None:
                self.canvas.request_edit("Not ekle", lambda p: p.annotations.append(ann))
        self.canvas.select_tool()

    def _edit_entity(self, key) -> None:
        if key is not None and key[0] == "annot":
            edit_annotation(self.doc, key[1], self)

    def _select_entity(self, key) -> None:
        self.canvas.selection = key
        self.canvas.sel_vertex = None
        self.canvas.update()

    def _delete_selection(self) -> None:
        sel = self.canvas.selection
        if sel is not None and sel[0] == "annot":
            from slipsurface.ui.cad.model import delete_entity
            self.canvas.request_edit("Not sil", lambda p: delete_entity(p, sel))
            self.canvas.selection = None

    def _sync_annot_actions(self, name: str) -> None:
        kind = getattr(self.canvas.tool, "kind", None)
        for k, a in self.t_annots.items():
            a.setChecked(name == f"draw_{k}" and k == kind)
        self.a_slice.setChecked(name == "slice_query")

    # ----------------------------------------------------------- tools
    def slice_data(self, i: int) -> None:
        r = self.results.results.get(self.key)
        if r is None:
            return
        SliceDataDialog(r, i, method_name(self.key), self).exec()

    def info_viewer(self) -> None:
        txt = report_text(self.results)
        if self.results.project.general.data_output == "maximum":
            for k, r in self.results.results.items():
                txt += f"\n\nDilim verisi — {method_name(k)}\n" + "-" * 60 + "\n"
                for i in range(r.slices.n):
                    rows = slice_rows(r, i)
                    txt += "  ".join(f"{a}: {b}" for a, b in rows[:1] + rows[2:10]) + "\n"
        InfoViewer(txt, self).exec()

    def pdf_report(self) -> None:
        from slipsurface.ui.dialogs.report import export_report
        export_report(self, self.results, self.project, self.path)

    def export_image(self) -> None:
        from slipsurface.ui.export import export_image
        export_image(self, self.area, "sonuc.png")
