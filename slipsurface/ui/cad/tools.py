"""Interactive CAD tools.

Coordinate entry (status-bar box) for drawing tools, AutoCAD style:
    x,y        absolute            (also "x y")
    @dx,dy     relative to the last point
    @L<a       polar: length L at angle a degrees from the last point
    c / close  close and finish (external boundary)
    u / undo   remove the last point
    (empty)    finish
"""

from __future__ import annotations

from slipsurface.ui.i18n import tr

import math
import re

import numpy as np
import shapely
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen, QPolygonF

from slipsurface.ui.cad.model import (
    FIXED_POINTS,
    LABELS,
    MIN_POINTS,
    delete_entity,
    get_points,
    set_points,
)

_NUM = r"[-+]?\d*[.,]?\d+(?:[eE][-+]?\d+)?"


def parse_coordinate(text: str, last):
    """Parse 'x,y', 'x y', '@dx,dy', '@L<a'. Returns (x, y) or None."""
    t = text.strip().replace(";", ",")
    m = re.fullmatch(rf"@\s*({_NUM})\s*<\s*({_NUM})", t)
    if m and last is not None:
        L = float(m.group(1).replace(",", "."))
        a = math.radians(float(m.group(2).replace(",", ".")))
        return last[0] + L * math.cos(a), last[1] + L * math.sin(a)
    rel = t.startswith("@")
    if rel:
        t = t[1:].strip()
    m = re.fullmatch(rf"({_NUM})\s*(?:,|\s)\s*({_NUM})", t)
    if not m:
        # "1,5,2,5" (Turkish decimals with comma separator) -> use ';' or space
        return None
    x, y = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
    if rel:
        if last is None:
            return None
        return last[0] + x, last[1] + y
    return x, y


class Tool:
    name = "tool"
    hint = ""
    uses_snap = False
    pickbox = False

    def __init__(self, canvas) -> None:
        self.c = canvas

    def activate(self) -> None: ...
    def deactivate(self) -> None: ...
    def press(self, ev) -> None: ...
    def release(self, ev) -> None: ...
    def double_click(self, ev) -> None: ...
    def paint(self, p) -> None: ...

    def move(self, ev) -> None:
        if self.uses_snap:
            pt, kind = self.c.snap(ev.position(), ref=self.ref_point())
            self.c.snap_marker = (kind, pt) if kind else None
        else:
            self.c.snap_marker = None

    def ref_point(self):
        return None

    def key(self, ev) -> bool:
        return False

    def command(self, text: str) -> bool:
        return False

    def context_menu(self, menu, pos) -> None: ...


# ============================================================== select/edit
class SelectTool(Tool):
    name = "select"
    hint = "Seç: köşeyi sürükleyerek taşıyın, çift tıklayarak koordinatları düzenleyin, Delete ile silin."
    pickbox = True

    def __init__(self, canvas) -> None:
        super().__init__(canvas)
        self.drag = None          # (key, vertex, original points)
        self.drag_pts = None
        self.translate = None     # (key, start world point, original points) — whole annotation

    @property
    def uses_snap(self):
        return self.drag is not None

    def move(self, ev) -> None:
        c = self.c
        if self.translate is not None:
            key, (x0, y0), orig = self.translate
            x, y = c.s2w(ev.position())
            self.drag_pts = [[q[0] + x - x0, q[1] + y - y0] for q in orig]
            c.project.annotations[key[1]]["pts"] = self.drag_pts     # live preview
            c.update()
            return
        if self.drag is not None:
            key, k, _ = self.drag
            ref = None
            if c.ortho_on:
                ref = self.drag[2][k]
            pt, kind = c.snap(ev.position(), ref=ref, exclude=(key, k))
            c.snap_marker = (kind, pt) if kind else None
            self.drag_pts[k] = list(pt)
            c.status.emit(f"Köşe taşınıyor: x = {pt[0]:.3f}, y = {pt[1]:.3f}")
            return
        c.snap_marker = None
        c.hover = c.pick_vertex(ev.position()) if c.editable else None

    def press(self, ev) -> None:
        c = self.c
        if ev.button() != Qt.LeftButton:
            return
        hit = c.pick_vertex(ev.position()) if c.editable else None
        if hit is not None:
            key, k = hit
            c.selection, c.sel_vertex = key, k
            c.selection_changed.emit(key)
            pts = get_points(c.project, key)
            self.drag = (key, k, [list(q) for q in pts])
            self.drag_pts = [list(q) for q in pts]
            return
        # notes are drawn on top of the model, so they are picked first
        ann = c.pick_annotation(ev.position())
        seg = c.pick_segment(ev.position()) if ann is None else None
        c.selection = ann if ann is not None else (seg[0] if seg else None)
        c.sel_vertex = None
        c.selection_changed.emit(c.selection)
        if c.selection is not None and c.selection[0] == "annot" and c.editable:
            orig = [list(q) for q in get_points(c.project, c.selection)]
            self.translate = (c.selection, c.s2w(ev.position()), orig)

    def release(self, ev) -> None:
        c = self.c
        if self.translate is not None:
            key, _, orig = self.translate
            new = self.drag_pts
            self.translate = None
            self.drag_pts = None
            c.project.annotations[key[1]]["pts"] = orig              # undo live preview
            if new is not None and new != orig:
                c.request_edit("Notu taşı", lambda p: set_points(p, key, new))
            c.update()
            return
        if self.drag is None:
            return
        key, k, orig = self.drag
        new = self.drag_pts
        self.drag = None
        self.drag_pts = None
        c.snap_marker = None
        if new[k] != orig[k]:
            c.request_edit(f"{_label(key)}: köşe taşı", lambda p: set_points(p, key, new))

    def paint(self, p) -> None:
        if self.drag is None:
            return
        key, k, _ = self.drag
        pts = np.asarray(self.drag_pts, float)
        closed = key[0] == "external"
        p.setPen(QPen(QColor("#1e88ff"), 1.5, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        poly = QPolygonF([self.c.w2s(*q) for q in pts])
        p.drawPolygon(poly) if closed else p.drawPolyline(poly)

    def double_click(self, ev) -> None:
        c = self.c
        hit = c.pick_vertex(ev.position())
        ann = c.pick_annotation(ev.position())
        seg = c.pick_segment(ev.position())
        key = hit[0] if hit else (ann if ann is not None else (seg[0] if seg else None))
        if key is not None:
            c.entity_double_clicked.emit(key)

    def key(self, ev) -> bool:
        c = self.c
        if ev.key() == Qt.Key_Delete and c.selection is not None and c.editable:
            key, k = c.selection, c.sel_vertex
            if c.edit_kinds is not None and key[0] not in c.edit_kinds:
                return True
            if k is not None and key[0] not in FIXED_POINTS:
                _delete_vertex(c, key, k)
            else:
                c.request_edit(f"{_label(key)} sil", lambda p: delete_entity(p, key))
                c.selection = None
                c.selection_changed.emit(None)
            return True
        return False

    def context_menu(self, menu, pos) -> None:
        c = self.c
        if not c.editable:
            return
        hit = c.pick_vertex(QPointF(pos))
        ann = c.pick_annotation(QPointF(pos))
        seg = c.pick_segment(QPointF(pos))
        if ann is not None and (hit is None or hit[0] == ann):
            c.selection, c.sel_vertex = ann, None
            c.selection_changed.emit(ann)
            menu.addAction(tr("Özellikler…"), lambda: c.entity_double_clicked.emit(ann))
            menu.addAction(tr("Notu sil"),
                           lambda: (c.request_edit(tr("Not sil"), lambda p: delete_entity(p, ann)),
                                    setattr(c, "selection", None),
                                    c.selection_changed.emit(None)))
        elif hit is not None:
            key, k = hit
            menu.addAction("Köşeyi sil", lambda: _delete_vertex(c, key, k))
            menu.addAction("Koordinatları düzenle…", lambda: c.entity_double_clicked.emit(key))
        elif seg is not None:
            key, k, pt = seg
            menu.addAction("Buraya köşe ekle", lambda: _insert_vertex(c, key, k, pt))
            menu.addAction("Koordinatları düzenle…", lambda: c.entity_double_clicked.emit(key))
            menu.addAction(f"{_label(key)} sil",
                           lambda: c.request_edit(f"{_label(key)} sil",
                                                  lambda p: delete_entity(p, key)))


def _label(key) -> str:
    kind, i = key
    return f"{LABELS[kind]} {i + 1}" if kind in ("material", "load", "support", "pattern",
                                                  "facing", "annot") else LABELS[kind]


def _delete_vertex(c, key, k) -> None:
    if key[0] in FIXED_POINTS:
        c.status.emit(f"⚠ {_label(key)} köşesi silinemez; tümünü silmek için Delete.")
        return
    pts = get_points(c.project, key)
    if len(pts) <= MIN_POINTS[key[0]]:
        c.status.emit(f"⚠ {_label(key)} en az {MIN_POINTS[key[0]]} köşe içermeli.")
        return
    del pts[k]
    c.sel_vertex = None
    c.request_edit(f"{_label(key)}: köşe sil", lambda p: set_points(p, key, pts))


def _insert_vertex(c, key, seg_index, pt) -> None:
    if key[0] in FIXED_POINTS:
        c.status.emit(f"⚠ {_label(key)} üzerine köşe eklenemez.")
        return
    pts = get_points(c.project, key)
    pts.insert(seg_index + 1, [float(pt[0]), float(pt[1])])
    c.request_edit(f"{_label(key)}: köşe ekle", lambda p: set_points(p, key, pts))


# ================================================================ drawing
class DrawTool(Tool):
    """Polyline / polygon drawing for boundaries, water table, user surface."""

    uses_snap = True
    TITLES = {"external": tr("Dış sınır"), "material": tr("Malzeme sınırı"), "water": "YASS",
              "user": "Kullanıcı tanımlı kayma yüzeyi", "load_distributed": "Yayılı yük",
              "load_line": "Tekil yük", "support": tr("Destek"), "crack": tr("Gerilme çatlağı"),
              "facing": "Kaplama", "pattern": "Bulon paterni", "annot_text": tr("Yazı"),
              "annot_line": tr("Çizgi"), "annot_arrow": tr("Ok"), "annot_rect": tr("Dikdörtgen"),
              "annot_ellipse": tr("Elips")}
    MIN = {"load_distributed": 2, "load_line": 1, "support": 2, "facing": 2, "pattern": 2,
           "annot_text": 1, "annot_line": 2, "annot_arrow": 2, "annot_rect": 2,
           "annot_ellipse": 2}
    MAX = dict(MIN)
    HINTS = {"load_distributed": "Yayılı yük: yükün başlangıç ve bitiş noktalarını zemin "
                                 "yüzeyinde tıklayın.",
             "load_line": "Tekil yük: yükün etkidiği noktayı zemin yüzeyinde tıklayın.",
             "support": "Destek: önce şev yüzündeki başı (A), sonra zemin içindeki ucu (B) "
                        "tıklayın veya koordinat girin.",
             "facing": "Kaplama: şev yüzünde kaplamanın başlangıç ve bitiş noktalarını tıklayın.",
             "pattern": "Bulon paterni: şev yüzünde paternin başlangıç ve bitiş noktalarını "
                        "tıklayın; aralık ve açı sonra sorulur.",
             "annot_text": "Yazı: yazının konumunu tıklayın.",
             "annot_line": "Çizgi: iki nokta tıklayın.",
             "annot_arrow": "Ok: başlangıç ve uç (ok başı) noktalarını tıklayın.",
             "annot_rect": "Dikdörtgen: iki köşe tıklayın.",
             "annot_ellipse": "Elips: çevreleyen dikdörtgenin iki köşesini tıklayın."}

    def __init__(self, canvas, kind: str) -> None:
        super().__init__(canvas)
        self.kind = kind
        self.name = f"draw_{kind}"
        self.pts: list[tuple[float, float]] = []
        self.preview = None
        self.min_points = self.MIN.get(kind, MIN_POINTS.get(kind, 2))
        self.max_points = self.MAX.get(kind)
        closing = " — ilk noktaya tıklayarak veya C ile kapatın" if kind == "external" else ""
        self.hint = self.HINTS.get(kind) or (
            f"{self.TITLES[kind]}: noktaları tıklayın veya koordinat girin (x,y | "
            f"@dx,dy | @L<açı); Enter/sağ tık = bitir{closing}, Backspace = geri, Esc = iptal")

    def ref_point(self):
        return self.pts[-1] if self.pts else None

    def move(self, ev) -> None:
        pt, kind = self.c.snap(ev.position(), ref=self.ref_point())
        self.c.snap_marker = (kind, pt) if kind else None
        self.preview = pt
        if self.pts:
            dx, dy = pt[0] - self.pts[-1][0], pt[1] - self.pts[-1][1]
            L = math.hypot(dx, dy)
            a = math.degrees(math.atan2(dy, dx))
            self.c.status.emit(f"{self.TITLES[self.kind]}: nokta {len(self.pts) + 1}  "
                               f"x = {pt[0]:.3f}, y = {pt[1]:.3f}   "
                               f"(uzunluk {L:.3f} m, açı {a:.1f}°)")

    def press(self, ev) -> None:
        if ev.button() != Qt.LeftButton:
            return
        pt, _ = self.c.snap(ev.position(), ref=self.ref_point())
        if self.kind == "external" and len(self.pts) >= 3:
            s0 = self.c.w2s(*self.pts[0])
            if math.hypot(s0.x() - ev.position().x(), s0.y() - ev.position().y()) <= 9:
                self.finish()
                return
        self.add_point(pt)

    def add_point(self, pt) -> None:
        if self.pts and math.hypot(pt[0] - self.pts[-1][0], pt[1] - self.pts[-1][1]) < 1e-9:
            return
        self.pts.append((float(pt[0]), float(pt[1])))
        self.c.update()
        if self.max_points and len(self.pts) >= self.max_points:
            self.finish()

    def finish(self) -> None:
        if len(self.pts) < self.min_points:
            self.c.status.emit(f"⚠ {self.TITLES[self.kind]} için en az "
                               f"{self.min_points} nokta gerekli.")
            return
        pts = [list(q) for q in self.pts]
        self.pts = []
        self.preview = None
        self.c.drawn.emit(self.kind, pts)

    def cancel(self) -> None:
        self.pts = []
        self.preview = None
        self.c.select_tool()

    def key(self, ev) -> bool:
        k = ev.key()
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.finish()
            return True
        if k == Qt.Key_Escape:
            self.cancel()
            return True
        if k == Qt.Key_Backspace and self.pts:
            self.pts.pop()
            return True
        if k == Qt.Key_C and self.kind == "external":
            self.finish()
            return True
        return False

    def command(self, text: str) -> bool:
        t = text.lower()
        if t in ("", "done", "bitir"):
            self.finish()
            return True
        if t in ("c", "close", "kapat"):
            self.finish()
            return True
        if t in ("u", "undo", "geri"):
            if self.pts:
                self.pts.pop()
                self.c.update()
            return True
        pt = parse_coordinate(text, self.pts[-1] if self.pts else None)
        if pt is None:
            self.c.status.emit(f"⚠ Koordinat anlaşılamadı: '{text}' (örnek: 10,5  @5,0  @10<30)")
            return False
        self.add_point(pt)
        return True

    def context_menu(self, menu, pos) -> None:
        if self.pts:
            menu.addAction("Bitir (Enter)", self.finish)
            if self.kind == "external":
                menu.addAction("Kapat (C)", self.finish)
            menu.addAction("Son noktayı geri al (Backspace)",
                           lambda: (self.pts.pop() if self.pts else None, self.c.update()))
        menu.addAction("İptal (Esc)", self.cancel)

    def paint(self, p) -> None:
        if not self.pts:
            return
        pts = list(self.pts)
        if self.preview is not None:
            pts.append(self.preview)
        col = {"external": QColor("#303030"), "material": QColor("#e07b00"),
               "water": QColor("#1f5fd1"), "user": QColor("#c0392b"),
               "load_distributed": QColor("#c0392b"), "load_line": QColor("#c0392b"),
               "support": QColor("#1f3d7a"), "crack": QColor("#8d5524")}.get(
                   self.kind, QColor("#c0392b"))
        p.setPen(QPen(col, 2))
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(QPolygonF([self.c.w2s(*q) for q in self.pts]))
        if self.preview is not None:
            p.setPen(QPen(col, 1.5, Qt.DashLine))
            p.drawLine(self.c.w2s(*self.pts[-1]), self.c.w2s(*self.preview))
            if self.kind == "external" and len(self.pts) >= 2:
                p.setPen(QPen(col, 1, Qt.DotLine))
                p.drawLine(self.c.w2s(*self.preview), self.c.w2s(*self.pts[0]))
        p.setPen(QPen(col, 1))
        p.setBrush(QColor("white"))
        for q in self.pts:
            s = self.c.w2s(*q)
            p.drawRect(QRectF(s.x() - 3.5, s.y() - 3.5, 7, 7))


# ============================================================ vertex edits
class AddVertexTool(Tool):
    name = "add_vertex"
    hint = "Köşe ekle: bir sınır çizgisinin üzerine tıklayın."
    pickbox = True

    def move(self, ev) -> None:
        seg = self.c.pick_segment(ev.position())
        self.c.snap_marker = ("near", tuple(seg[2])) if seg else None

    def press(self, ev) -> None:
        if ev.button() != Qt.LeftButton:
            return
        seg = self.c.pick_segment(ev.position())
        if seg is None:
            self.c.status.emit("⚠ Yakında sınır çizgisi yok.")
            return
        key, k, pt = seg
        pt = tuple(pt)
        if self.c.snap_on:      # grid snap along the segment is not exact; keep nearest
            pass
        _insert_vertex(self.c, key, k, pt)


class DeleteVertexTool(Tool):
    name = "delete_vertex"
    hint = "Köşe sil: silinecek köşeye tıklayın."
    pickbox = True

    def move(self, ev) -> None:
        self.c.hover = self.c.pick_vertex(ev.position())
        self.c.snap_marker = None

    def press(self, ev) -> None:
        if ev.button() != Qt.LeftButton:
            return
        hit = self.c.pick_vertex(ev.position())
        if hit is None:
            self.c.status.emit("⚠ Yakında köşe yok.")
            return
        _delete_vertex(self.c, *hit)


# ================================================================= assign
class AssignTool(Tool):
    name = "assign"
    hint = "Özellik ata: malzemeyi araç çubuğundan seçin, sonra bölgelerin içine tıklayın."
    pickbox = True

    def press(self, ev) -> None:
        c = self.c
        if ev.button() != Qt.LeftButton or c.geometry is None:
            return
        mat = c.assign_material
        if not mat:
            c.status.emit("⚠ Önce bir malzeme seçin.")
            return
        x, y = c.s2w(ev.position())
        region = next((r for r in c.geometry.regions if shapely.contains_xy(r.polygon, x, y)),
                      None)
        if region is None:
            c.status.emit("⚠ Tıklanan nokta model içinde değil.")
            return

        def fn(p):
            p.assignments = [a for a in p.assignments
                             if not region.polygon.contains(shapely.Point(*a["point"]))]
            p.assignments.append({"point": [float(x), float(y)], "material": mat})

        if c.request_edit(f"Özellik ata: {mat}", fn):
            c.status.emit(f"Bölgeye '{mat}' atandı.")


# ================================================================ measure
class MeasureTool(Tool):
    name = "measure"
    hint = "Ölç: iki nokta tıklayın (uzaklık, Δx, Δy, açı)."
    uses_snap = True

    def __init__(self, canvas) -> None:
        super().__init__(canvas)
        self.a = None
        self.b = None
        self.preview = None

    def ref_point(self):
        return self.a if self.b is None else None

    def move(self, ev) -> None:
        super().move(ev)
        self.preview, _ = self.c.snap(ev.position(), ref=self.ref_point())

    def press(self, ev) -> None:
        if ev.button() != Qt.LeftButton:
            return
        pt, _ = self.c.snap(ev.position(), ref=self.ref_point())
        if self.a is None or self.b is not None:
            self.a, self.b = pt, None
        else:
            self.b = pt
            dx, dy = self.b[0] - self.a[0], self.b[1] - self.a[1]
            self.c.status.emit(f"Uzaklık = {math.hypot(dx, dy):.3f} m   Δx = {dx:.3f}   "
                               f"Δy = {dy:.3f}   açı = {math.degrees(math.atan2(dy, dx)):.2f}°")

    def paint(self, p) -> None:
        if self.a is None:
            return
        b = self.b or self.preview
        if b is None:
            return
        pa, pb = self.c.w2s(*self.a), self.c.w2s(*b)
        p.setPen(QPen(QColor("#8e24aa"), 1.5, Qt.DashLine))
        p.drawLine(pa, pb)
        d = math.hypot(b[0] - self.a[0], b[1] - self.a[1])
        p.setFont(QFont("Source Sans 3", 9, QFont.Bold))
        p.setPen(QColor("#8e24aa"))
        p.drawText((pa + pb) / 2 + QPointF(6, -6), f"{d:.3f} m")


# ============================================================ zoom / pan
class ZoomWindowTool(Tool):
    name = "zoom_window"
    hint = "Pencereyle zoom: yakınlaştırılacak alanı sürükleyerek seçin."

    def __init__(self, canvas) -> None:
        super().__init__(canvas)
        self.start = None
        self.cur = None

    def press(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.start = self.cur = ev.position()

    def move(self, ev) -> None:
        self.c.snap_marker = None
        if self.start is not None:
            self.cur = ev.position()

    def release(self, ev) -> None:
        if self.start is None:
            return
        x0, y0 = self.c.s2w(self.start)
        x1, y1 = self.c.s2w(ev.position())
        self.start = None
        self.c.zoom_to_rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        self.c.select_tool()

    def paint(self, p) -> None:
        if self.start is not None and self.cur is not None:
            p.setPen(QPen(QColor("#1e88ff"), 1, Qt.DashLine))
            p.setBrush(QColor(30, 136, 255, 40))
            p.drawRect(QRectF(self.start, self.cur).normalized())


class PanTool(Tool):
    name = "pan"
    hint = "Kaydır: sol tuşla sürükleyin (orta tuş her araçta kaydırır)."

    def __init__(self, canvas) -> None:
        super().__init__(canvas)
        self.last = None

    def press(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.last = ev.position()

    def move(self, ev) -> None:
        self.c.snap_marker = None
        if self.last is not None:
            d = ev.position() - self.last
            self.last = ev.position()
            self.c.pan_pixels(d.x(), d.y())

    def release(self, ev) -> None:
        self.last = None


# =========================================================== slope limits
class SlopeLimitsTool(Tool):
    name = "slope_limits"
    uses_snap = True

    def __init__(self, canvas) -> None:
        super().__init__(canvas)
        self.xs: list[float] = []
        self.hint = self._hint()

    def _hint(self) -> str:
        steps = ["sol aralığın başlangıcı", "sol aralığın bitişi", "sağ aralığın başlangıcı",
                 "sağ aralığın bitişi"]
        return f"Kayma sınırları: zemin yüzeyi üzerinde {steps[len(self.xs)]} noktasına tıklayın."

    def press(self, ev) -> None:
        if ev.button() != Qt.LeftButton:
            return
        pt, _ = self.c.snap(ev.position())
        self.xs.append(pt[0])
        if len(self.xs) == 4:
            L = sorted(self.xs[:2])
            R = sorted(self.xs[2:])

            def fn(p):
                p.surfaces.left_range = L
                p.surfaces.right_range = R

            self.c.request_edit(tr("Kayma sınırları"), fn)
            self.c.select_tool()
            return
        self.hint = self._hint()
        self.c.status.emit(self.hint)

    def paint(self, p) -> None:
        g = self.c.geometry
        if g is None:
            return
        p.setPen(QPen(QColor("#5b7fb8"), 2))
        for x in self.xs:
            s = self.c.w2s(x, float(g.ground_y(x)))
            p.drawLine(QPointF(s.x(), s.y() - 18), QPointF(s.x(), s.y()))


# ============================================================ slice query
class SliceQueryTool(Tool):
    name = "slice_query"
    hint = "Dilim verisi: kayan kütle içindeki bir dilime tıklayın."
    pickbox = True

    def __init__(self, canvas, callback) -> None:
        super().__init__(canvas)
        self.callback = callback

    def press(self, ev) -> None:
        res = self.c.current_result()
        if ev.button() != Qt.LeftButton or res is None:
            return
        x, _ = self.c.s2w(ev.position())
        s = res.slices
        idx = np.flatnonzero((s.xl <= x) & (x <= s.xr))
        if idx.size == 0:
            self.c.status.emit("⚠ Tıklanan nokta kayan kütlenin dışında.")
            return
        self.c.highlight_slice = int(idx[0])
        self.callback(int(idx[0]))



# ================================================================ bolts
class BoltTool(Tool):
    """Click on the slope face: a bolt / anchor is added with its head there,
    inclined `angle` degrees below horizontal into the slope (length from the
    support type)."""

    name = "bolt"
    uses_snap = True

    def __init__(self, canvas, angle_getter, length_getter) -> None:
        super().__init__(canvas)
        self.angle_getter, self.length_getter = angle_getter, length_getter
        self.preview = None
        self.hint = ("Tekil bulon/ankraj: şev yüzünde başlığın konumunu tıklayın "
                     "(eğim ve boy araç çubuğundan). Esc = bitir.")

    def _bolt(self, x):
        from slipsurface.loads import bolt_at
        g = self.c.geometry
        if g is None or not (g.x_min <= x <= g.x_max):
            return None
        return bolt_at(g, x, self.angle_getter(), self.length_getter())

    def move(self, ev) -> None:
        super().move(ev)
        pt, _ = self.c.snap(ev.position())
        self.preview = self._bolt(pt[0])

    def press(self, ev) -> None:
        if ev.button() != Qt.LeftButton:
            return
        pt, _ = self.c.snap(ev.position())
        ab = self._bolt(pt[0])
        if ab is None:
            self.c.status.emit("⚠ Model dışında.")
            return
        self.c.drawn.emit("bolt", [list(map(float, ab[0])), list(map(float, ab[1]))])

    def command(self, text: str) -> bool:
        pt = parse_coordinate(text, None)
        if pt is None:
            try:
                pt = (float(text.replace(",", ".")), 0.0)     # just an x value
            except ValueError:
                return False
        ab = self._bolt(pt[0])
        if ab is None:
            return False
        self.c.drawn.emit("bolt", [list(map(float, ab[0])), list(map(float, ab[1]))])
        return True

    def paint(self, p) -> None:
        if self.preview is None:
            return
        a, b = self.preview
        p.setPen(QPen(QColor("#1f3d7a"), 1.5, Qt.DashLine))
        p.drawLine(self.c.w2s(*a), self.c.w2s(*b))
