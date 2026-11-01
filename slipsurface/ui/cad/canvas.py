"""CAD canvas: world/screen transform, grid, snapping, rendering, tools.

Everything is painted in screen coordinates from the world model each frame
(no scene graph), so text stays upright and pixel-sized items (vertices,
markers, pick boxes) keep a constant size at any zoom.

Mouse:  wheel = zoom at cursor, middle drag = pan, middle double-click =
        zoom extents; left/right go to the active tool.
Keys:   Esc = cancel / select tool, Enter = finish, Backspace = undo point,
        Delete = delete selection, F2 = zoom extents, +/- = zoom.
"""

from __future__ import annotations

from slipsurface.ui.i18n import tr

import math

import numpy as np
import shapely
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QMenu, QWidget

from slipsurface.geometry import slip_extent
from slipsurface.lem import method_name
from slipsurface.project import DEFAULT_DISPLAY, Project
from slipsurface.ui.cad.model import entities, point_segment_distance, segment_intersection

PICK_PX = 9  # pick / snap tolerance in pixels
SELECT_COLOR = QColor("#1e88ff")
SNAP_COLOR = QColor("#00a020")


def nice_step(raw: float) -> float:
    """1, 2, 5 x 10^n step >= raw."""
    if raw <= 0:
        return 1.0
    e = math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        step = m * 10**e
        if step >= raw:
            return step
    return 10 ** (e + 1)


def fs_color(t: float) -> QColor:
    """t in [0,1]: 0 = critical (red) ... 1 = highest shown (blue)."""
    stops = [
        (0.0, (220, 30, 30)),
        (0.25, (240, 140, 20)),
        (0.5, (230, 220, 30)),
        (0.75, (60, 180, 75)),
        (1.0, (40, 100, 220)),
    ]
    t = min(max(t, 0.0), 1.0)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:], strict=False):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return QColor(*[int(a + f * (b - a)) for a, b in zip(c0, c1, strict=False)])
    return QColor(*stops[-1][1])


class CadCanvas(QWidget):
    view_changed = Signal()
    mouse_world = Signal(float, float)
    material_activated = Signal(str)  # double-click a material region to edit it
    status = Signal(str)
    selection_changed = Signal(object)  # key or None
    entity_double_clicked = Signal(object)  # key
    drawn = Signal(str, list)  # kind, points (from draw tools)
    tool_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None, editable: bool = True) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(300, 200)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setCursor(Qt.BlankCursor)
        self.editable = editable

        self.project: Project | None = None
        self.geometry = None
        self.results = None
        self.result_key: str | None = None
        self.doc = None

        self.scale = 10.0  # px per metre
        self.cx, self.cy = 20.0, 5.0
        self.grid_spacing = 1.0  # snap / grid spacing [m]
        self.snap_on = False
        self.grid_on = True
        self.ortho_on = False
        self.osnap_on = True

        self.selection = None  # entity key
        self.sel_vertex = None  # vertex index of the selected entity
        self.hover = None  # (key, vertex) under cursor
        self.snap_marker = None  # (kind, (x, y))
        self.mouse_pos: QPointF | None = None
        self._pan_last = None
        self._snap_cache = None
        self.highlight_slice: int | None = None
        self.edit_kinds: set | None = None  # None = all entity kinds are editable
        self._annot_rects: dict = {}  # annotation index -> screen QRectF (hit test)
        self.assign_material: str | None = None
        self._contour_cache: tuple | None = None  # (result id, grid, image)

        from slipsurface.ui.cad.tools import SelectTool

        self.tool = SelectTool(self)

    # =============================================================== scene
    def set_scene(
        self,
        project: Project | None,
        geometry=None,
        results=None,
        result_key: str | None = None,
        fit: bool = False,
    ) -> None:
        self.project = project
        self.geometry = geometry
        self.results = results
        self.result_key = result_key
        self._snap_cache = None
        if self.selection is not None:
            keys = {e.key for e in entities(project)}
            if self.selection not in keys:
                self.selection = self.sel_vertex = None
                self.selection_changed.emit(None)
        if fit:
            self.zoom_extents()
        self.update()

    def display(self, key):
        if self.project is not None:
            return self.project.display_opt(key)
        return DEFAULT_DISPLAY.get(key)

    def current_result(self):
        if self.results is None or self.result_key not in self.results.results:
            return None
        return self.results.results[self.result_key]

    # ============================================================ transform
    def w2s(self, x, y) -> QPointF:
        return QPointF(
            self.width() / 2 + (x - self.cx) * self.scale,
            self.height() / 2 - (y - self.cy) * self.scale,
        )

    def s2w(self, pt) -> tuple[float, float]:
        return (
            self.cx + (pt.x() - self.width() / 2) / self.scale,
            self.cy - (pt.y() - self.height() / 2) / self.scale,
        )

    def visible_world(self) -> tuple[float, float, float, float]:
        x0, y1 = self.s2w(QPointF(0, 0))
        x1, y0 = self.s2w(QPointF(self.width(), self.height()))
        return x0, y0, x1, y1

    def model_bounds(self):
        pts = []
        for e in entities(self.project):
            pts.append(e.pts)
        res = self.current_result()
        if res is not None and hasattr(res.surface, "r"):
            pts.append(np.array([[res.surface.xc, res.surface.yc + 0.05 * res.surface.r]]))
        cg = self._contour()
        if cg is not None:
            g = cg[0]
            pts.append(
                np.array(
                    [
                        [g["x0"], g["y0"]],
                        [g["x0"] + g["nx"] * g["side"], g["y0"] + g["ny"] * g["side"]],
                    ]
                )
            )
        if not pts:
            return None
        a = np.vstack(pts)
        return a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max()

    def zoom_extents(self) -> None:
        b = self.model_bounds()
        if b is None:
            x0, y0, x1, y1 = -10, -10, 50, 30
        else:
            x0, y0, x1, y1 = b
        w, h = max(x1 - x0, 1e-3), max(y1 - y0, 1e-3)
        margin = 0.08
        sw, sh = max(self.width(), 50), max(self.height(), 50)
        self.scale = min(sw / (w * (1 + 2 * margin)), sh / (h * (1 + 2 * margin)))
        self.cx, self.cy = (x0 + x1) / 2, (y0 + y1) / 2
        self.update()
        self.view_changed.emit()

    def zoom(self, factor: float, anchor: QPointF | None = None) -> None:
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        wx, wy = self.s2w(anchor)
        self.scale = float(np.clip(self.scale * factor, 1e-3, 1e5))
        nx, ny = self.s2w(anchor)
        self.cx += wx - nx
        self.cy += wy - ny
        self.update()
        self.view_changed.emit()

    def zoom_to_rect(self, x0, y0, x1, y1) -> None:
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w * self.scale < 4 or h * self.scale < 4:
            return
        self.scale = min(self.width() / w, self.height() / h)
        self.cx, self.cy = (x0 + x1) / 2, (y0 + y1) / 2
        self.update()
        self.view_changed.emit()

    def pan_pixels(self, dx: float, dy: float) -> None:
        self.cx -= dx / self.scale
        self.cy += dy / self.scale
        self.update()
        self.view_changed.emit()

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self.view_changed.emit()

    # ============================================================== tools
    def set_tool(self, tool) -> None:
        if self.tool is not None:
            self.tool.deactivate()
        self.tool = tool
        tool.activate()
        self.status.emit(tool.hint)
        self.tool_changed.emit(tool.name)
        self.update()

    def select_tool(self) -> None:
        from slipsurface.ui.cad.tools import SelectTool

        self.set_tool(SelectTool(self))

    def request_edit(self, text: str, fn) -> bool:
        if self.doc is None or not self.editable:
            return False
        try:
            return self.doc.edit(text, fn)
        except ValueError as exc:
            self.status.emit(f"⚠ {exc}")
            return False

    def command(self, text: str) -> bool:
        """Coordinate / command entry from the status-bar box."""
        return self.tool.command(text.strip())

    # ============================================================ snapping
    def _snap_targets(self):
        if self._snap_cache is None:
            ents = entities(self.project)
            verts, mids, segs = [], [], []
            for e in ents:
                for k, q in enumerate(e.pts):
                    verts.append((e.key, k, q))
                for k, a, b in e.segments():
                    mids.append((a + b) / 2)
                    segs.append((e.key, k, a, b))
            inter = []
            for i in range(len(segs)):
                for j in range(i + 1, len(segs)):
                    if segs[i][0] == segs[j][0] and abs(segs[i][1] - segs[j][1]) <= 1:
                        continue
                    q = segment_intersection(segs[i][2], segs[i][3], segs[j][2], segs[j][3])
                    if q is not None:
                        inter.append(q)
            self._snap_cache = (verts, mids, segs, inter)
        return self._snap_cache

    def snap(self, sp: QPointF, ref=None, exclude=None):
        """Snapped world point for screen point `sp`.

        Priority: OSNAP endpoint > intersection > midpoint > nearest; else grid
        SNAP; ORTHO constrains to horizontal/vertical from `ref` unless an
        OSNAP (other than 'nearest') hit wins. Returns ((x, y), marker kind).
        """
        w = np.array(self.s2w(sp))
        tol = PICK_PX / self.scale
        if self.osnap_on and self.project is not None:
            verts, mids, segs, inter = self._snap_targets()
            best = None
            for key, k, q in verts:
                if exclude is not None and (key, k) == exclude:
                    continue
                d = np.hypot(*(q - w))
                if d <= tol and (best is None or d < best[0]):
                    best = (d, q)
            if best is not None:
                return (float(best[1][0]), float(best[1][1])), "end"
            for q in inter:
                if np.hypot(*(q - w)) <= tol:
                    return (float(q[0]), float(q[1])), "int"
            for q in mids:
                if np.hypot(*(q - w)) <= tol:
                    return (float(q[0]), float(q[1])), "mid"
        pt = w.copy()
        kind = None
        if self.snap_on:
            g = self.grid_spacing
            pt = np.round(w / g) * g
            kind = "grid"
        if self.ortho_on and ref is not None:
            dx, dy = pt[0] - ref[0], pt[1] - ref[1]
            pt = np.array([pt[0], ref[1]]) if abs(dx) >= abs(dy) else np.array([ref[0], pt[1]])
            kind = "ortho"
        if kind is None and self.osnap_on and self.project is not None:
            _, _, segs, _ = self._snap_targets()
            best = None
            for key, k, a, b in segs:
                if exclude is not None and exclude[0] == key and k in (exclude[1], exclude[1] - 1):
                    continue
                d, c, _ = point_segment_distance(w, a, b)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, c)
            if best is not None:
                return (float(best[1][0]), float(best[1][1])), "near"
        return (float(pt[0]), float(pt[1])), kind

    # ============================================================== picking
    def _editable_entities(self):
        ents = entities(self.project)
        if self.edit_kinds is None:
            return ents
        return [e for e in ents if e.key[0] in self.edit_kinds]

    def pick_annotation(self, sp: QPointF):
        """Topmost annotation under the screen point: text box, line / arrow
        within the pick distance, rectangle or ellipse (inside or on the edge)."""
        if self.edit_kinds is not None and "annot" not in self.edit_kinds:
            return None
        if self.project is None:
            return None
        tol = PICK_PX
        x, y = sp.x(), sp.y()
        for i in reversed(range(len(self.project.annotations))):
            a = self.project.annotations[i]
            kind = a["kind"]
            if kind == "text":
                r = self._annot_rects.get(i)
                if r is not None and r.adjusted(-4, -4, 4, 4).contains(sp):
                    return ("annot", i)
                continue
            if len(a["pts"]) < 2:
                continue
            p0, p1 = self.w2s(*a["pts"][0]), self.w2s(*a["pts"][1])
            if kind in ("line", "arrow"):
                d, _, _ = point_segment_distance((x, y), (p0.x(), p0.y()), (p1.x(), p1.y()))
                if d <= tol:
                    return ("annot", i)
                continue
            r = QRectF(p0, p1).normalized()
            if kind == "rect" and r.adjusted(-tol, -tol, tol, tol).contains(sp):
                return ("annot", i)
            if kind == "ellipse":
                rx, ry = r.width() / 2 + tol, r.height() / 2 + tol
                cx, cy = r.center().x(), r.center().y()
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                    return ("annot", i)
        return None

    def pick_vertex(self, sp: QPointF):
        best = None
        for e in self._editable_entities():
            for k, q in enumerate(e.pts):
                s = self.w2s(*q)
                d = math.hypot(s.x() - sp.x(), s.y() - sp.y())
                if d <= PICK_PX and (best is None or d < best[0]):
                    best = (d, e.key, k)
        return None if best is None else (best[1], best[2])

    def pick_segment(self, sp: QPointF):
        """(key, segment index, nearest world point) within tolerance."""
        w = np.array(self.s2w(sp))
        tol = PICK_PX / self.scale
        best = None
        for e in self._editable_entities():
            for k, a, b in e.segments():
                d, c, _ = point_segment_distance(w, a, b)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, e.key, k, c)
        return None if best is None else best[1:]

    # ============================================================== events
    def mousePressEvent(self, ev) -> None:
        self.setFocus()
        if ev.button() == Qt.MiddleButton:
            self._pan_last = ev.position()
            return
        if ev.button() == Qt.RightButton:
            return  # handled by contextMenuEvent
        self.tool.press(ev)
        self.update()

    def mouseMoveEvent(self, ev) -> None:
        self.mouse_pos = ev.position()
        if self._pan_last is not None:
            d = ev.position() - self._pan_last
            self._pan_last = ev.position()
            self.pan_pixels(d.x(), d.y())
            return
        wx, wy = self.s2w(ev.position())
        self.mouse_world.emit(wx, wy)
        self._hover_material(wx, wy, ev)
        self.tool.move(ev)
        self.update()

    def material_at(self, wx: float, wy: float) -> str | None:
        """Name of the material region under a world point, if any."""
        if self.geometry is None:
            return None
        for r in self.geometry.regions:
            if shapely.contains_xy(r.polygon, wx, wy):
                return r.material
        return None

    def _hover_material(self, wx: float, wy: float, ev) -> None:
        """Show the material name and parameters when the cursor rests on a
        material region (SelectTool only, so drawing tools stay quiet)."""
        from PySide6.QtWidgets import QToolTip

        if self.geometry is None or self.project is None:
            if QToolTip.isVisible():
                QToolTip.hideText()
            return
        from slipsurface.ui.cad.tools import SelectTool

        if not isinstance(self.tool, SelectTool):
            if QToolTip.isVisible():
                QToolTip.hideText()
            return
        hit = self.material_at(wx, wy)
        if hit is None:
            if QToolTip.isVisible():
                QToolTip.hideText()
            return
        spec = self.project.material(hit)
        if spec is None:
            return
        from slipsurface.materials.catalog import model_name, parameter_text

        lines = [f"{hit} ({model_name(spec.model)})" if spec.model != "MC" else hit]
        lines.append(parameter_text(spec))
        lines.append(
            f"\u03b3 = {spec.gamma:g} kN/m\u00b3"
            + (f", \u03b3sat = {spec.gamma_sat:g}" if spec.use_sat else "")
        )
        QToolTip.showText(ev.globalPosition().toPoint(), "\n".join(lines), self)

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.MiddleButton:
            self._pan_last = None
            return
        self.tool.release(ev)
        self.update()

    def mouseDoubleClickEvent(self, ev) -> None:
        if ev.button() == Qt.MiddleButton:
            self.zoom_extents()
            return
        self.tool.double_click(ev)
        self.update()

    def wheelEvent(self, ev) -> None:
        steps = ev.angleDelta().y() / 120.0
        if steps:
            self.zoom(1.2**steps, ev.position())

    def leaveEvent(self, ev) -> None:
        self.mouse_pos = None
        self.snap_marker = None
        self.update()

    def keyPressEvent(self, ev) -> None:
        if self.tool.key(ev):
            self.update()
            return
        k = ev.key()
        if k == Qt.Key_Escape:
            self.select_tool()
        elif k == Qt.Key_F2:
            self.zoom_extents()
        elif k in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom(1.25)
        elif k == Qt.Key_Minus:
            self.zoom(0.8)
        else:
            super().keyPressEvent(ev)

    def contextMenuEvent(self, ev) -> None:
        menu = QMenu(self)
        self.tool.context_menu(menu, ev.pos())
        if not menu.isEmpty():
            menu.addSeparator()
        wx, wy = self.s2w(ev.pos())
        hit = self.material_at(wx, wy)
        if hit is not None:
            menu.addAction(
                tr("Bu Malzemeyi Düzenle…"), lambda n=hit: self.material_activated.emit(n)
            )
            menu.addSeparator()
        menu.addAction(tr("Tümünü göster (F2)"), self.zoom_extents)
        menu.addAction(tr("Yakınlaştır"), lambda: self.zoom(1.25))
        menu.addAction(tr("Uzaklaştır"), lambda: self.zoom(0.8))
        menu.exec(ev.globalPos())
        self.update()

    # ============================================================ painting
    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.palette().base())
        if self.grid_on and self.display("show_grid"):
            self._paint_grid(p)
        self._paint_model(p)
        self._paint_results(p)
        if self.display("material_labels") not in (None, "none"):
            self._paint_material_labels(p)
        self._paint_annotations(p)
        if self.display("show_slope_limits"):
            self._paint_slope_limits(p)
        self.tool.paint(p)
        self._paint_snap_marker(p)
        legend_top = 10.0
        if self.results is not None:
            legend_top = max(legend_top, self._paint_contour_legend(p) + 8)
        if self.display("show_legend"):
            self._paint_legend(p, legend_top)
        if self.results is not None and self.display("show_fs_legend"):
            self._paint_fs_legend(p)
        self._paint_cursor(p)
        p.end()

    # ------------------------------------------------------------- grid
    def _paint_grid(self, p: QPainter) -> None:
        step = self.grid_spacing
        while step * self.scale < 10:
            step = nice_step(step * 2)
        x0, y0, x1, y1 = self.visible_world()
        major = step * 5
        dark = self.palette().base().color().lightness() < 128
        pen_minor = QPen(QColor("#29364a") if dark else QColor(232, 235, 240), 1)
        pen_major = QPen(QColor("#384a62") if dark else QColor(208, 214, 222), 1)
        for lo, hi, vertical in ((x0, x1, True), (y0, y1, False)):
            k0 = math.floor(lo / step)
            k1 = math.ceil(hi / step)
            if k1 - k0 > 2000:
                continue
            for k in range(k0, k1 + 1):
                v = k * step
                is_major = abs(v / major - round(v / major)) < 1e-6
                p.setPen(pen_major if is_major else pen_minor)
                if vertical:
                    s = self.w2s(v, 0).x()
                    p.drawLine(QPointF(s, 0), QPointF(s, self.height()))
                else:
                    s = self.w2s(0, v).y()
                    p.drawLine(QPointF(0, s), QPointF(self.width(), s))

    # ------------------------------------------------------------ model
    def _poly_screen(self, pts) -> QPolygonF:
        return QPolygonF([self.w2s(float(x), float(y)) for x, y in pts])

    def _paint_model(self, p: QPainter) -> None:
        if self.project is None:
            return
        lw = float(self.display("line_width") or 2)
        colors = self.project.colors()
        # regions
        if self.geometry is not None and self.display("fill_materials"):
            for r in self.geometry.regions:
                col = QColor(colors.get(r.material, "#dddddd"))
                p.setPen(QPen(QColor(110, 110, 110), 0.8))
                p.setBrush(col)
                p.drawPolygon(self._poly_screen(np.asarray(r.polygon.exterior.coords)))
        # entities
        ext_col = QColor(self.display("external_color"))
        mat_col = QColor(self.display("material_boundary_color"))
        wt_col = QColor(self.display("water_table_color"))
        for e in entities(self.project):
            kind = e.key[0]
            selected = e.key == self.selection
            if kind in ("load", "support", "pattern", "facing", "annot"):
                continue  # drawn by their own painters
            if kind == "external":
                pen = QPen(ext_col, lw + (1.5 if selected else 0))
            elif kind == "material":
                pen = QPen(mat_col, max(1.0, lw - 0.5) + (1.5 if selected else 0))
            elif kind == "water":
                pen = QPen(wt_col, lw + (1.5 if selected else 0))
            elif kind == "crack":
                pen = QPen(QColor("#8d5524"), 1.6 + (1.5 if selected else 0), Qt.DashDotLine)
            else:
                pen = QPen(QColor("#c0392b"), lw + (1.5 if selected else 0), Qt.DashLine)
            if selected:
                pen.setColor(SELECT_COLOR)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setBrush(Qt.NoBrush)
            poly = self._poly_screen(e.pts)
            if kind == "material" and self.geometry is not None:
                # part outside the external boundary: faint dotted; inside: solid
                faint = QPen(pen.color(), 1, Qt.DotLine)
                p.setPen(faint)
                p.drawPolyline(poly)
                inside = shapely.LineString(e.pts).intersection(self.geometry.domain)
                p.setPen(pen)
                for gpart in getattr(inside, "geoms", [inside]):
                    if isinstance(gpart, shapely.LineString) and not gpart.is_empty:
                        p.drawPolyline(self._poly_screen(np.asarray(gpart.coords)))
                continue
            p.setPen(pen)
            if e.closed:
                p.drawPolygon(poly)
            else:
                p.drawPolyline(poly)
            if kind == "water":
                self._paint_water_symbol(p, e.pts, wt_col)
            if kind == "crack":
                self._paint_crack_symbols(p, e.pts)
        self._paint_loads_supports(p)
        # vertices
        if self.display("show_vertices"):
            for e in entities(self.project):
                for k, q in enumerate(e.pts):
                    s = self.w2s(*q)
                    hov = self.hover is not None and self.hover == (e.key, k)
                    sel = e.key == self.selection and (self.sel_vertex in (None, k))
                    if e.key[0] == "annot" and not (hov or sel):
                        continue  # note handles only when active
                    r = 4.0 if (hov or (sel and self.sel_vertex == k)) else 2.6
                    p.setPen(QPen(SELECT_COLOR if (hov or sel) else QColor(40, 40, 40), 1))
                    p.setBrush(QColor("white") if not hov else SELECT_COLOR)
                    p.drawRect(QRectF(s.x() - r, s.y() - r, 2 * r, 2 * r))

    # ------------------------------------------------- loads & supports
    def _arrow(
        self,
        p: QPainter,
        tip: QPointF,
        direction,
        length: float,
        col: QColor,
        width: float = 1.4,
        head: float = 7.0,
    ) -> QPointF:
        """Arrow ending at `tip`, pointing along screen `direction` (unit). Returns tail."""
        dx, dy = direction
        tail = QPointF(tip.x() - dx * length, tip.y() - dy * length)
        p.setPen(QPen(col, width))
        p.drawLine(tail, tip)
        nx, ny = -dy, dx
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon(
            QPolygonF(
                [
                    tip,
                    QPointF(
                        tip.x() - dx * head + nx * head * 0.45,
                        tip.y() - dy * head + ny * head * 0.45,
                    ),
                    QPointF(
                        tip.x() - dx * head - nx * head * 0.45,
                        tip.y() - dy * head - ny * head * 0.45,
                    ),
                ]
            )
        )
        return tail

    def _paint_loads_supports(self, p: QPainter) -> None:
        pr = self.project
        if pr is None:
            return
        g = self.geometry
        red = QColor("#c0392b")
        p.setFont(QFont("Source Sans 3", 8))
        # distributed loads
        qmax = max(
            [abs(q) for ld in pr.loads if ld["kind"] == "distributed" for q in ld["q"]] or [1.0]
        )
        for i, ld in enumerate(pr.loads):
            sel = self.selection == ("load", i)
            col = SELECT_COLOR if sel else red
            if ld["kind"] == "distributed":
                (x1, y1), (x2, y2) = ld["points"]
                if x2 < x1:
                    (x1, y1), (x2, y2) = (x2, y2), (x1, y1)
                q1, q2 = ld["q"]
                n_arrows = max(2, int(abs(self.w2s(x2, 0).x() - self.w2s(x1, 0).x()) / 22) + 1)
                tails = []
                for t in np.linspace(0, 1, n_arrows):
                    x = x1 + t * (x2 - x1)
                    y = float(g.ground_y(x)) if g is not None else y1 + t * (y2 - y1)
                    q = q1 + t * (q2 - q1)
                    L = 10 + 32 * abs(q) / qmax
                    if ld.get("orientation", "vertical") == "normal" and g is not None:
                        h = 1e-4
                        sl = (g.ground_y(x + h) - g.ground_y(x - h)) / (2 * h)
                        # into-soil normal (world) = (sl, -1)/n -> screen (sl, +1)/n
                        nrm = math.hypot(sl, 1.0)
                        d = (sl / nrm, 1.0 / nrm)
                    else:
                        d = (0.0, 1.0)
                    if q < 0:
                        d = (-d[0], -d[1])
                    tails.append(self._arrow(p, self.w2s(x, y), d, L, col))
                p.setPen(QPen(col, 1.4))
                p.drawPolyline(QPolygonF(tails))
                p.setPen(col)
                p.drawText(tails[0] + QPointF(-4, -5), f"{q1:g} kPa")
                if q2 != q1:
                    p.drawText(tails[-1] + QPointF(-4, -5), f"{q2:g} kPa")
            else:
                x, y = ld["point"]
                if g is not None:
                    y = float(g.ground_y(x))
                a = math.radians(ld.get("angle", 270.0))
                d = (math.cos(a), -math.sin(a))  # screen y is down
                tail = self._arrow(p, self.w2s(x, y), d, 46, col, 2.2, 10)
                p.setPen(col)
                p.drawText(tail + QPointF(4, -4), f"{ld['magnitude']:g} kN/m")
        # shotcrete facings (band along the ground)
        for i, f in enumerate(pr.facings):
            ft = pr.facing_type(f["type"])
            sel = self.selection == ("facing", i)
            lo, hi = sorted((f["x1"], f["x2"]))
            if g is None:
                continue
            xs = np.unique(
                np.concatenate(
                    [[lo, hi], g.surface[(g.surface[:, 0] > lo) & (g.surface[:, 0] < hi), 0]]
                )
            )
            poly = QPolygonF([self.w2s(x, float(g.ground_y(x))) for x in xs])
            col = QColor(SELECT_COLOR if sel else (ft.color if ft else "#7f8c8d"))
            col.setAlpha(210)
            band = QPen(col, 8, Qt.SolidLine, Qt.FlatCap, Qt.RoundJoin)
            p.setPen(band)
            p.drawPolyline(poly)
            p.setPen(QPen(QColor("#2c3e50"), 1, Qt.DashLine))  # wire mesh
            p.drawPolyline(poly)
        # supports
        for i, sp in enumerate(pr.supports):
            self._draw_support(
                p, sp["a"], sp["b"], pr.support_type(sp["type"]), self.selection == ("support", i)
            )
        # bolt patterns (generated)
        if g is not None:
            for i, pt in enumerate(pr.support_patterns):
                st = pr.support_type(pt["type"])
                sel = self.selection == ("pattern", i)
                try:
                    bolts = pr.pattern_bolts(pt, g)
                except ValueError:
                    continue
                for a, b in bolts:
                    self._draw_support(p, a, b, st, sel)
                # bracket along the patterned face
                p.setPen(
                    QPen(
                        SELECT_COLOR if sel else QColor(st.color if st else "#1f3d7a"),
                        1,
                        Qt.DotLine,
                    )
                )
                p.drawLine(self.w2s(*pt["p1"]), self.w2s(*pt["p2"]))

    def _draw_support(self, p: QPainter, a, b, st, sel: bool) -> None:
        col = SELECT_COLOR if sel else QColor(st.color if st else "#1f3d7a")
        A, B = self.w2s(*a), self.w2s(*b)
        kind = st.kind if st else "end_anchored"
        pen = QPen(col, 2.0 + (1 if sel else 0))
        if kind in ("geotextile", "geosynthetic"):
            pen.setStyle(Qt.DashLine)
        if kind == "micro_pile":
            pen.setWidthF(4.0 + (1 if sel else 0))
        p.setPen(pen)
        p.drawLine(A, B)
        L = math.hypot(B.x() - A.x(), B.y() - A.y()) or 1.0
        ux, uy = (B.x() - A.x()) / L, (B.y() - A.y()) / L
        nx, ny = -uy, ux
        if kind == "grouted_tieback" and st is not None:
            world_len = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
            f = min(1.0, st.bond_length / world_len)
            C = QPointF(B.x() - ux * L * f, B.y() - uy * L * f)
            p.setPen(QPen(col, 6, Qt.SolidLine, Qt.FlatCap))
            p.drawLine(C, B)
        if kind == "soil_nail":
            p.setPen(QPen(col, 1))
            for t in np.arange(0.1, 1.0, 0.1):
                q = QPointF(A.x() + ux * L * t, A.y() + uy * L * t)
                p.drawLine(q + QPointF(nx * 3, ny * 3), q - QPointF(nx * 3, ny * 3))
        if kind == "micro_pile":  # pile cap + toe
            p.setPen(QPen(col, 1.5))
            p.setBrush(QColor("white"))
            p.drawEllipse(B, 4, 4)
        if kind not in ("geotextile", "geosynthetic"):  # head plate
            p.setPen(QPen(col, 3))
            p.drawLine(A + QPointF(nx * 6, ny * 6), A - QPointF(nx * 6, ny * 6))
        if kind == "end_anchored":
            p.setPen(QPen(col, 1.5))
            p.setBrush(col)
            p.drawRect(QRectF(B.x() - 3.5, B.y() - 3.5, 7, 7))

    def _paint_crack_symbols(self, p: QPainter, pts) -> None:
        """Small zig-zag cracks from the ground down towards the crack line."""
        g = self.geometry
        if g is None:
            return
        p.setPen(QPen(QColor("#8d5524"), 1.2))
        x0, x1 = pts[0, 0], pts[-1, 0]
        n = max(2, int(abs(self.w2s(x1, 0).x() - self.w2s(x0, 0).x()) / 40))
        for x in np.linspace(x0, x1, n + 2)[1:-1]:
            top = self.w2s(x, float(g.ground_y(x)))
            bot = self.w2s(x, float(np.interp(x, pts[:, 0], pts[:, 1])))
            if bot.y() <= top.y():
                continue
            k = 4
            zig = [
                QPointF(
                    top.x() + (3 if j % 2 else -3) * (1 - j / k),
                    top.y() + (bot.y() - top.y()) * j / k,
                )
                for j in range(k + 1)
            ]
            p.drawPolyline(QPolygonF(zig))

    def _paint_water_symbol(self, p: QPainter, pts, col: QColor) -> None:
        xs = pts[0, 0] + 0.8 * (pts[-1, 0] - pts[0, 0])
        ys = float(np.interp(xs, pts[:, 0], pts[:, 1]))
        s = self.w2s(xs, ys)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(s.x() - 7, s.y() - 14),
                    QPointF(s.x() + 7, s.y() - 14),
                    QPointF(s.x(), s.y() - 3),
                ]
            )
        )
        p.setPen(QPen(col, 1.2))
        p.drawLine(QPointF(s.x() - 7, s.y() + 4), QPointF(s.x() + 7, s.y() + 4))
        p.drawLine(QPointF(s.x() - 4, s.y() + 8), QPointF(s.x() + 4, s.y() + 8))

    def _paint_slope_limits(self, p: QPainter) -> None:
        if self.geometry is None or self.project is None:
            return
        s = self.project.surfaces
        g = self.geometry
        marks = []
        for rng, side in ((s.left_range, "L"), (s.right_range, "R")):
            if rng:
                marks += [(x, side) for x in rng]
        if not marks:
            marks = [(g.x_min, "L"), (g.x_max, "R")]
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#5b7fb8"))
        for x, side in marks:
            q = self.w2s(x, float(g.ground_y(x)))
            y = q.y() - 10
            if side == "L":
                tri = [QPointF(q.x(), y - 6), QPointF(q.x(), y + 6), QPointF(q.x() + 9, y)]
            else:
                tri = [QPointF(q.x(), y - 6), QPointF(q.x(), y + 6), QPointF(q.x() - 9, y)]
            p.drawPolygon(QPolygonF(tri))
            p.setPen(QPen(QColor("#5b7fb8"), 1))
            p.drawLine(QPointF(q.x(), y - 6), QPointF(q.x(), q.y()))
            p.setPen(Qt.NoPen)

    # ---------------------------------------------------------- results
    def _contour(self):
        """(grid, image) of the slip-centre FS contour map of the current result."""
        res = self.current_result()
        if (
            res is None
            or not self.display("show_fs_contours")
            or getattr(res, "centres", None) is None
        ):
            return None
        if self._contour_cache is None or self._contour_cache[0] is not res:
            from slipsurface.ui.cad import fs_contour

            g = fs_contour.build_grid(res.centres)
            self._contour_cache = (res, g, fs_contour.render_image(g) if g else None)
        _, g, img = self._contour_cache
        return None if g is None else (g, img)

    def _paint_contour(self, p: QPainter) -> None:
        cg = self._contour()
        if cg is None:
            return
        g, img = cg
        tl = self.w2s(g["x0"], g["y0"] + g["ny"] * g["side"])
        br = self.w2s(g["x0"] + g["nx"] * g["side"], g["y0"])
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(QRectF(tl, br), img)
        from slipsurface.ui.cad.fs_contour import LINE, contour_segments

        seg = contour_segments(g)
        if len(seg):
            sx = self.width() / 2 + (seg[:, [0, 2]] - self.cx) * self.scale
            sy = self.height() / 2 - (seg[:, [1, 3]] - self.cy) * self.scale
            p.setPen(QPen(QColor(*LINE), 0.9))
            p.drawLines(
                [
                    QLineF(a, b, c, d)
                    for a, c, b, d in np.column_stack([sx[:, 0], sx[:, 1], sy[:, 0], sy[:, 1]])
                ]
            )
        p.restore()

    def _paint_results(self, p: QPainter) -> None:
        res = self.current_result()
        if res is None or self.geometry is None:
            return
        g = self.geometry
        s = res.slices
        surf = res.surface
        # all surfaces (colored by FS)
        if self.display("show_all_surfaces") and res.top:
            fmin = res.fos
            fmax = max(f for f, _ in res.top)
            for f, sf in reversed(res.top[1:]):
                ext = slip_extent(g, sf)
                if ext is None:
                    continue
                t = 0 if fmax <= fmin else (f - fmin) / (fmax - fmin)
                p.setPen(QPen(fs_color(t), 1.0))
                p.setBrush(Qt.NoBrush)
                p.drawPolyline(self._poly_screen(sf.points(*ext, 80)))
        # sliding mass fill and slices
        xs = np.concatenate([s.xl, s.xr[-1:]])
        base = np.column_stack([xs, surf.y(xs)])
        top = np.column_stack([xs[::-1], g.ground_y(xs[::-1])])
        mass = np.vstack([base, top])
        if self.display("show_slices"):
            fill = QColor(self.display("slice_fill_color"))
            fill.setAlpha(170)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawPolygon(self._poly_screen(np.vstack([base, top])))
            p.setPen(QPen(QColor(90, 70, 30), 0.8))
            for x in xs:
                p.drawLine(self.w2s(x, float(surf.y(x))), self.w2s(x, float(g.ground_y(x))))
            if self.highlight_slice is not None and 0 <= self.highlight_slice < s.n:
                i = self.highlight_slice
                quad = [
                    (s.xl[i], surf.y(s.xl[i])),
                    (s.xr[i], surf.y(s.xr[i])),
                    (s.xr[i], g.ground_y(s.xr[i])),
                    (s.xl[i], g.ground_y(s.xl[i])),
                ]
                p.setPen(QPen(SELECT_COLOR, 2))
                p.setBrush(QColor(30, 136, 255, 70))
                p.drawPolygon(self._poly_screen(np.asarray(quad, float)))
        # tension crack face and crack water
        ck = s.crack
        if ck is not None:
            top, bot = self.w2s(ck["x"], ck["y_ground"]), self.w2s(ck["x"], ck["y_bottom"])
            if ck["hw"] > 0:
                wtop = self.w2s(ck["x"], ck["y_bottom"] + ck["hw"])
                dx = (-1 if ck["uphill_right"] else 1) * 0.55 * (bot.y() - wtop.y())
                p.setPen(QPen(QColor("#1f5fd1"), 1))
                p.setBrush(QColor(31, 95, 209, 110))
                p.drawPolygon(QPolygonF([wtop, bot, QPointF(bot.x() + dx, bot.y())]))
                p.setFont(QFont("Source Sans 3", 8))
                p.setPen(QColor("#1f5fd1"))
                p.drawText(
                    QPointF(bot.x() + dx - (60 if dx < 0 else -4), bot.y() + 14),
                    f"V = {ck['Pw']:.1f} kN/m",
                )
            p.setPen(QPen(QColor("#8d5524"), 2.2))
            p.drawLine(top, bot)
        # mobilised support forces at the slip-surface intersections
        for f in s.support_forces:
            q = self.w2s(f.x, f.y)
            p.setPen(QPen(QColor("#1f3d7a"), 1.5))
            p.setBrush(QColor("#ffd54a"))
            p.drawEllipse(q, 4, 4)
            p.setFont(QFont("Source Sans 3", 8, QFont.Bold))
            p.setPen(QColor("#1f3d7a"))
            p.drawText(q + QPointF(6, 14), f"Tmob = {f.mobilized(res.fos):.0f} kN/m")
        contour = self._contour() is not None
        crit = QColor("#0a8a2a")
        dark = QColor(40, 40, 40)
        # centre, lines to centre (under the contour map), FS text
        if hasattr(surf, "r"):
            c = self.w2s(surf.xc, surf.yc)
            anchor = c
            if self.display("show_lines_to_center"):
                p.setPen(
                    QPen(dark if contour else crit, 1.1, Qt.DashLine if contour else Qt.SolidLine)
                )
                for x in (s.x_exit, s.x_entry):
                    p.drawLine(c, self.w2s(x, float(g.ground_y(x))))
            self._paint_contour(p)
            p.setPen(QPen(crit, 1))
            p.setBrush(crit)
            p.drawEllipse(c, 2.5, 2.5)
        else:
            if hasattr(surf, "control_points") and self.display("show_control_points"):
                cp = surf.control_points()
                p.setPen(QPen(crit, 1, Qt.DashLine))
                p.drawPolyline(self._poly_screen(cp))
                p.setPen(QPen(crit, 1))
                p.setBrush(QColor("white"))
                for q in cp:
                    sq = self.w2s(*q)
                    p.drawRect(QRectF(sq.x() - 3, sq.y() - 3, 6, 6))
            # FS label at the centroid of the sliding mass (non-circular surfaces)
            try:
                cen = shapely.Polygon(mass).centroid
                anchor = self.w2s(cen.x, cen.y)
                anchor = QPointF(anchor.x(), anchor.y() + 12)
            except Exception:
                xm = 0.5 * (s.x_exit + s.x_entry)
                anchor = self.w2s(xm, float(g.ground_y(xm)))
        # critical surface
        if self.display("critical_dashed"):
            pen = QPen(dark, 1.6, Qt.DashLine)
        else:
            pen = QPen(crit, 2.4)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(self._poly_screen(surf.points(s.x_exit, s.x_entry, 200)))
        if self.display("show_fs_text"):
            txt = f"FS = {res.fos:.3f}" if contour else f"{res.fos:.3f}"
            f = QFont("Verdana", 9 if contour else 10, QFont.Bold)
            p.setFont(f)
            fm = QFontMetrics(f)
            w, h = fm.horizontalAdvance(txt) + 10, fm.height() + 4
            box = QRectF(anchor.x() - w / 2, anchor.y() - h - 4, w, h)
            if contour:  # centred on the critical centre
                box.moveCenter(anchor)
            p.setPen(QPen(QColor(40, 40, 40), 1))
            p.setBrush(QColor("white"))
            p.drawRect(box)
            p.setPen(QColor("#1f3d7a") if contour else crit)
            p.drawText(box, Qt.AlignCenter, txt)

    def _paint_contour_legend(self, p: QPainter) -> float:
        """Banded FS legend (top right). Returns its bottom edge (screen y)."""
        cg = self._contour()
        if cg is None:
            return 0.0
        from slipsurface.ui.cad import fs_contour as fc

        g = cg[0]
        labels = fc.legend_labels(g["vmax"])
        f = QFont("Source Sans 3", 8)
        fb = QFont("Source Sans 3", 9, QFont.Bold)
        fs = QFont("Source Sans 3", 7)
        fm = QFontMetrics(f)
        title = tr("FS (aranan merkezler)")
        note = tr("Her yarıçap taranmaz")
        band_h = 6
        sw = 16
        lw = max(fm.horizontalAdvance(t) for t in labels) + 8
        w = max(
            sw + lw + 22,
            QFontMetrics(fb).horizontalAdvance(title) + 16,
            QFontMetrics(fs).horizontalAdvance(note) + 16,
        )
        h = 38 + band_h * fc.N_BANDS + fm.height() // 2 + 10
        x0, y0 = self.width() - w - 12, 10
        p.setPen(QPen(QColor(150, 150, 150), 1))
        p.setBrush(QColor(255, 255, 255, 240))
        p.drawRect(QRectF(x0, y0, w, h))
        p.setFont(fb)
        p.setPen(QColor("#e01e1e"))
        p.drawText(QRectF(x0, y0 + 2, w, 16), Qt.AlignHCenter | Qt.AlignVCenter, title)
        p.setFont(fs)
        p.setPen(QColor("#555555"))
        p.drawText(QRectF(x0, y0 + 16, w, 14), Qt.AlignHCenter | Qt.AlignVCenter, note)
        top = y0 + 34 + fm.height() // 4
        bx = x0 + 8
        for k in range(fc.N_BANDS):  # highest band on top
            col = QColor(fc.PALETTE[fc.N_BANDS - 1 - k])
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRect(QRectF(bx, top + k * band_h, sw, band_h))
        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(bx, top, sw, band_h * fc.N_BANDS))
        p.setFont(f)
        p.setPen(QColor(30, 30, 30))
        n = len(labels) - 1
        for k, t in enumerate(labels):  # label k at boundary k*2 from the bottom
            y = top + band_h * fc.N_BANDS - k * (band_h * fc.N_BANDS / n)
            p.drawLine(QPointF(bx + sw, y), QPointF(bx + sw + 3, y))
            p.drawText(
                QRectF(bx + sw + 6, y - fm.height() / 2, lw, fm.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                t,
            )
        return y0 + h

    # ----------------------------------------------------------- legend
    def _paint_legend(self, p: QPainter, top: float = 10.0) -> None:
        if self.project is None or not self.project.materials:
            return
        used = None
        if self.geometry is not None:
            used = {r.material for r in self.geometry.regions}
        mats = [m for m in self.project.materials if used is None or m.name in used]
        if not mats:
            return
        f = QFont("Source Sans 3", 8)
        p.setFont(f)
        fm = QFontMetrics(f)
        row = fm.height() + 4
        w = max(fm.horizontalAdvance(m.name) for m in mats) + 34
        h = row * len(mats) + 8
        res = self.current_result()
        extra = 0
        if res is not None and self.display("show_all_surfaces") and res.top:
            extra = 46
        x0, y0 = self.width() - w - 12, top
        p.setPen(QPen(QColor(150, 150, 150), 1))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRect(QRectF(x0, y0, w, h + extra))
        for i, m in enumerate(mats):
            y = y0 + 4 + i * row
            p.setPen(QPen(QColor(60, 60, 60), 1))
            p.setBrush(QColor(m.color))
            p.drawRect(QRectF(x0 + 6, y + 2, 16, row - 6))
            p.setPen(QColor(30, 30, 30))
            p.drawText(QRectF(x0 + 28, y, w - 30, row), Qt.AlignVCenter | Qt.AlignLeft, m.name)
        if extra:
            fmin = res.fos
            fmax = max(fv for fv, _ in res.top)
            gy = y0 + h + 6
            grad = QLinearGradient(x0 + 6, 0, x0 + w - 6, 0)
            for t in (0, 0.25, 0.5, 0.75, 1.0):
                grad.setColorAt(t, fs_color(t))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRect(QRectF(x0 + 6, gy, w - 12, 10))
            p.setPen(QColor(30, 30, 30))
            p.drawText(QRectF(x0 + 6, gy + 12, w - 12, row), Qt.AlignLeft, f"{fmin:.3f}")
            p.drawText(QRectF(x0 + 6, gy + 12, w - 12, row), Qt.AlignRight, f"{fmax:.3f}")

    # ------------------------------------------------ material labels
    def _paint_material_labels(self, p: QPainter) -> None:
        if self.geometry is None or self.project is None:
            return
        from shapely.ops import polylabel

        mode = self.display("material_labels")
        best: dict[str, object] = {}
        for r in self.geometry.regions:  # label each material at its largest region
            if r.material not in best or r.polygon.area > best[r.material].area:
                best[r.material] = r.polygon
        sz = int(self.display("label_size") or 8)
        f = QFont("Source Sans 3", sz)
        fb = QFont("Source Sans 3", sz, QFont.Bold)
        fm, fmb = QFontMetrics(f), QFontMetrics(fb)
        for name, poly in best.items():
            spec = self.project.material(name)
            if spec is None:
                continue
            lines = [name]
            if mode == "full":
                from slipsurface.materials.catalog import model_name, parameter_text

                if spec.model != "MC":
                    lines.append(model_name(spec.model))
                parts = parameter_text(spec).split(", ")
                lines += [", ".join(parts[k : k + 2]) for k in range(0, len(parts), 2)]
                g_txt = f"γ = {spec.gamma:g} kN/m³"
                if spec.use_sat:
                    g_txt += f",  γsat = {spec.gamma_sat:g}"
                lines.append(g_txt)
            try:
                c = polylabel(poly, tolerance=max(poly.length / 200, 1e-3))
                # long bands have many equally good points: prefer the centroid
                cen = poly.centroid
                if poly.contains(cen) and poly.exterior.distance(
                    cen
                ) >= 0.7 * poly.exterior.distance(c):
                    c = cen
            except Exception:
                c = poly.representative_point()
            q = self.w2s(c.x, c.y)
            w = (
                max(
                    [fmb.horizontalAdvance(lines[0])] + [fm.horizontalAdvance(t) for t in lines[1:]]
                )
                + 10
            )
            h = fm.height() * len(lines) + 6
            box = QRectF(q.x() - w / 2, q.y() - h / 2, w, h)
            if box.width() > 2 * abs(
                self.w2s(*poly.bounds[2:]).x() - self.w2s(*poly.bounds[:2]).x()
            ):
                continue  # region far too small on screen
            p.setPen(QPen(QColor(90, 90, 90), 0.8))
            p.setBrush(QColor(255, 255, 255, 215))
            p.drawRect(box)
            p.setPen(QColor(20, 20, 20))
            y = box.top() + 3
            for k, t in enumerate(lines):
                p.setFont(fb if k == 0 else f)
                p.drawText(QRectF(box.left(), y, w, fm.height()), Qt.AlignCenter, t)
                y += fm.height()

    # ------------------------------------------------------ annotations
    def _paint_annotations(self, p: QPainter) -> None:
        self._annot_rects = {}
        if self.project is None:
            return
        for i, a in enumerate(self.project.annotations):
            sel = self.selection == ("annot", i)
            col = QColor(a.get("color", "#c0392b"))
            width = float(a.get("width", 1.5))
            pen = QPen(SELECT_COLOR if sel else col, width + (1 if sel else 0))
            pts = [self.w2s(*q) for q in a["pts"]]
            kind = a["kind"]
            if kind == "text":
                f = QFont("Source Sans 3", int(a.get("size", 10)))
                f.setBold(bool(a.get("bold", False)))
                p.setFont(f)
                fm = QFontMetrics(f)
                lines = str(a.get("text", "")).split("\n") or [""]
                w = max(fm.horizontalAdvance(t) for t in lines) + 8
                h = fm.height() * len(lines) + 4
                box = QRectF(pts[0].x(), pts[0].y() - h, w, h)
                if a.get("box", True):
                    p.setPen(QPen(SELECT_COLOR if sel else QColor(80, 80, 80), 1))
                    p.setBrush(QColor(255, 255, 255, 230))
                    p.drawRect(box)
                elif sel:
                    p.setPen(QPen(SELECT_COLOR, 1, Qt.DashLine))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(box)
                p.setPen(col)
                y = box.top() + 2
                for t in lines:
                    p.drawText(QRectF(box.left() + 4, y, w, fm.height()), Qt.AlignLeft, t)
                    y += fm.height()
                self._annot_rects[i] = box
                if sel:
                    self._paint_annotation_grips(p, pts[:1], None)
                continue
            if len(pts) < 2:
                continue
            r = QRectF(pts[0], pts[1]).normalized()
            p.setPen(pen)
            fill = a.get("fill")
            if fill:
                fc = QColor(fill)
                fc.setAlpha(90)
                p.setBrush(fc)
            else:
                p.setBrush(Qt.NoBrush)
            if kind == "line":
                p.drawLine(pts[0], pts[1])
            elif kind == "arrow":
                dx, dy = pts[1].x() - pts[0].x(), pts[1].y() - pts[0].y()
                L = math.hypot(dx, dy) or 1.0
                self._arrow(
                    p,
                    pts[1],
                    (dx / L, dy / L),
                    L,
                    SELECT_COLOR if sel else col,
                    width + (1 if sel else 0),
                    8 + 2 * width,
                )
            elif kind == "rect":
                p.drawRect(r)
            elif kind == "ellipse":
                p.drawEllipse(r)
            self._annot_rects[i] = r if kind in ("rect", "ellipse") else QRectF()
            if sel:
                self._paint_annotation_grips(p, pts, r if kind in ("rect", "ellipse") else None)

    def _paint_annotation_grips(self, p: QPainter, pts, frame) -> None:
        """Selection feedback for a note: dashed frame and square grips."""
        if frame is not None:
            p.setPen(QPen(SELECT_COLOR, 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(frame.adjusted(-3, -3, 3, 3))
        p.setPen(QPen(SELECT_COLOR, 1))
        p.setBrush(QColor("white"))
        for q in pts:
            p.drawRect(QRectF(q.x() - 4, q.y() - 4, 8, 8))

    # -------------------------------------------------- FS legend (results)
    def _paint_fs_legend(self, p: QPainter) -> None:
        res = self.results
        if res is None or not (res.results or res.errors):
            return
        gm = res.global_minimum()
        rows = [(k, method_name(k), f"{r.fos:.3f}") for k, r in res.results.items()]
        rows += [(k, method_name(k), "–") for k in res.errors]
        f = QFont("Source Sans 3", 8)
        fb = QFont("Source Sans 3", 8, QFont.Bold)
        fm = QFontMetrics(fb)
        rh = fm.height() + 3
        wn = max(fm.horizontalAdvance(n) for _, n, _ in rows) + 22
        wv = fm.horizontalAdvance("00.000") + 14
        title = tr("Güvenlik sayısı (FS)")
        w = max(wn + wv, fm.horizontalAdvance(title) + 16)
        h = rh * (len(rows) + 1) + 10
        x0, y0 = self.width() - w - 12, self.height() - h - 12
        p.setPen(QPen(QColor(120, 120, 120), 1))
        p.setBrush(QColor(255, 255, 255, 240))
        p.drawRect(QRectF(x0, y0, w, h))
        p.setFont(fb)
        p.setPen(QColor(25, 45, 80))
        p.drawText(QRectF(x0 + 8, y0 + 4, w - 16, rh), Qt.AlignLeft | Qt.AlignVCenter, title)
        p.setPen(QPen(QColor(190, 190, 190), 1))
        p.drawLine(QPointF(x0 + 6, y0 + 4 + rh), QPointF(x0 + w - 6, y0 + 4 + rh))
        for k, (key, name, val) in enumerate(rows):
            y = y0 + 6 + rh * (k + 1)
            cur = key == self.result_key
            is_min = gm is not None and key == gm[0]
            if cur:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(30, 136, 255, 40))
                p.drawRect(QRectF(x0 + 3, y, w - 6, rh))
            p.setFont(fb if cur else f)
            p.setPen(QColor("#0a8a2a") if is_min else QColor(30, 30, 30))
            p.drawText(
                QRectF(x0 + 8, y, wn, rh),
                Qt.AlignLeft | Qt.AlignVCenter,
                ("● " if is_min else "   ") + name,
            )
            p.drawText(QRectF(x0 + wn, y, wv - 8, rh), Qt.AlignRight | Qt.AlignVCenter, val)

    # ----------------------------------------------------- snap / cursor
    def _paint_snap_marker(self, p: QPainter) -> None:
        if self.snap_marker is None or self.mouse_pos is None:
            return
        kind, (x, y) = self.snap_marker
        s = self.w2s(x, y)
        p.setPen(QPen(SNAP_COLOR, 2))
        p.setBrush(Qt.NoBrush)
        r = 6
        if kind == "end":
            p.drawRect(QRectF(s.x() - r, s.y() - r, 2 * r, 2 * r))
        elif kind == "mid":
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(s.x(), s.y() - r),
                        QPointF(s.x() + r, s.y() + r),
                        QPointF(s.x() - r, s.y() + r),
                    ]
                )
            )
        elif kind == "int":
            p.drawLine(QPointF(s.x() - r, s.y() - r), QPointF(s.x() + r, s.y() + r))
            p.drawLine(QPointF(s.x() - r, s.y() + r), QPointF(s.x() + r, s.y() - r))
        elif kind == "near":
            p.drawLine(QPointF(s.x() - r, s.y() - r), QPointF(s.x() + r, s.y() - r))
            p.drawLine(QPointF(s.x() + r, s.y() - r), QPointF(s.x() - r, s.y() + r))
            p.drawLine(QPointF(s.x() - r, s.y() + r), QPointF(s.x() + r, s.y() + r))
        elif kind == "grid":
            p.drawEllipse(s, 4, 4)
        label = {
            "end": "Uç nokta",
            "mid": "Orta nokta",
            "int": "Kesişim",
            "near": "En yakın",
            "grid": "Izgara",
            "ortho": "Orto",
        }.get(kind)
        if label:
            p.setFont(QFont("Source Sans 3", 8))
            p.setPen(QPen(SNAP_COLOR, 1))
            p.drawText(QPointF(s.x() + 9, s.y() + 16), tr(label))

    def _paint_cursor(self, p: QPainter) -> None:
        if self.mouse_pos is None:
            return
        m = self.mouse_pos
        if self.snap_marker is not None and self.tool.uses_snap:
            m = self.w2s(*self.snap_marker[1])
        p.setPen(QPen(QColor(20, 20, 20), 1))
        L = 22
        p.drawLine(QPointF(m.x() - L, m.y()), QPointF(m.x() + L, m.y()))
        p.drawLine(QPointF(m.x(), m.y() - L), QPointF(m.x(), m.y() + L))
        if self.tool.pickbox:
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(m.x() - 4, m.y() - 4, 8, 8))
