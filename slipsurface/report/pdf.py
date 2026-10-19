"""Professional PDF report of a slope stability analysis.

    build_pdf(results, path, ReportOptions(...), ReportFigures(...)) -> page count

Layout (A4 portrait): cover page (title band, project data, key result card,
critical-surface figure), table of contents, numbered sections (summary,
model, materials, analysis settings, loads & supports, results with FS chart
and figures), appendices (slice data, coordinates). Every body page carries a
running header and a footer with "Sayfa n / N".

The module is Qt-free: the drawings are rendered by the GUI
(slipsurface.ui.report_figures) and passed in as PNG bytes, so the report can
also be produced (without figures) from scripts and tests.
"""

from __future__ import annotations

import datetime as _dt
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from slipsurface import __version__
from slipsurface.lem import method_name

# ------------------------------------------------------------------ fonts
FONT_DIR = Path(__file__).parent / "fonts"
F_REG, F_BOLD, F_SEMI, F_IT = "SS3", "SS3-Bold", "SS3-SemiBold", "SS3-Italic"
_fonts_ok = False
log = logging.getLogger(__name__)


def _register_fonts() -> None:
    global _fonts_ok, F_REG, F_BOLD, F_SEMI, F_IT
    if _fonts_ok:
        return
    try:
        pdfmetrics.registerFont(TTFont(F_REG, str(FONT_DIR / "SourceSans3-Regular.ttf")))
        pdfmetrics.registerFont(TTFont(F_BOLD, str(FONT_DIR / "SourceSans3-Bold.ttf")))
        pdfmetrics.registerFont(TTFont(F_SEMI, str(FONT_DIR / "SourceSans3-SemiBold.ttf")))
        pdfmetrics.registerFont(TTFont(F_IT, str(FONT_DIR / "SourceSans3-Italic.ttf")))
        pdfmetrics.registerFontFamily(F_REG, normal=F_REG, bold=F_BOLD, italic=F_IT,
                                      boldItalic=F_BOLD)
    except Exception:                      # fonts missing: fall back (no Turkish glyphs)
        log.warning("PDF fontları yüklenemedi; Helvetica'ya düşülüyor "
                    "(Türkçe karakterler kaybolabilir).", exc_info=True)
        F_REG, F_BOLD, F_SEMI, F_IT = "Helvetica", "Helvetica-Bold", "Helvetica-Bold", \
            "Helvetica-Oblique"
    _fonts_ok = True


# ----------------------------------------------------------------- colours
NAVY = colors.HexColor("#1f3a5f")
NAVY_D = colors.HexColor("#152a45")
ACCENT = colors.HexColor("#2a7ad0")
INK = colors.HexColor("#1c2430")
MUTED = colors.HexColor("#5b6675")
RULE = colors.HexColor("#c9d3de")
HEAD_BG = colors.HexColor("#e6ecf3")
ZEBRA = colors.HexColor("#f6f8fb")
OK = colors.HexColor("#1e8a3c")
WARN = colors.HexColor("#c47f00")
BAD = colors.HexColor("#c0392b")

PAGE_W, PAGE_H = A4
MARGIN_L = MARGIN_R = 18 * mm
MARGIN_T, MARGIN_B = 24 * mm, 20 * mm
FRAME_W = PAGE_W - MARGIN_L - MARGIN_R


# ----------------------------------------------------------------- options
@dataclass
class ReportOptions:
    title: str = "Şev Stabilite Analiz Raporu"
    project: str = ""
    analysis: str = ""
    author: str = ""
    checker: str = ""
    company: str = ""
    report_no: str = ""
    date: str = ""
    target_fs: float | None = 1.5
    toc: bool = True
    model: bool = True
    materials: bool = True
    settings: bool = True
    loads: bool = True
    results: bool = True
    global_figure: bool = True
    method_figures: bool = True
    support_forces: bool = True
    slice_table: bool = True
    coordinates: bool = False
    model_file: str = ""


@dataclass
class ReportFigures:
    """PNG bytes of the drawings (any may be None)."""
    model: bytes | None = None
    global_min: bytes | None = None
    methods: dict[str, bytes] = field(default_factory=dict)


# ------------------------------------------------------------------ styles
def _styles() -> dict[str, ParagraphStyle]:
    _register_fonts()
    base = ParagraphStyle("body", fontName=F_REG, fontSize=9.5, leading=13.5, textColor=INK)
    st = {
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8, leading=10.5, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.3, leading=10.4),
        "cell_r": ParagraphStyle("cell_r", parent=base, fontSize=8.3, leading=10.4,
                                 alignment=TA_RIGHT),
        "cell_c": ParagraphStyle("cell_c", parent=base, fontSize=8.3, leading=10.4,
                                 alignment=TA_CENTER),
        "head": ParagraphStyle("head", parent=base, fontName=F_SEMI, fontSize=8.3,
                               leading=10.4, textColor=NAVY_D),
        "head_c": ParagraphStyle("head_c", parent=base, fontName=F_SEMI, fontSize=8.3,
                                 leading=10.4, textColor=NAVY_D, alignment=TA_CENTER),
        "h1": ParagraphStyle("h1", parent=base, fontName=F_BOLD, fontSize=15, leading=19,
                             textColor=NAVY, spaceBefore=4, spaceAfter=6, keepWithNext=1),
        "h2": ParagraphStyle("h2", parent=base, fontName=F_SEMI, fontSize=11.5, leading=15,
                             textColor=NAVY, spaceBefore=10, spaceAfter=4, keepWithNext=1),
        "caption": ParagraphStyle("caption", parent=base, fontSize=8.5, leading=11,
                                  textColor=MUTED, alignment=TA_CENTER, spaceBefore=3,
                                  spaceAfter=10),
        "tcaption": ParagraphStyle("tcaption", parent=base, fontName=F_SEMI, fontSize=8.5,
                                   leading=11, textColor=MUTED, spaceBefore=6, spaceAfter=3,
                                   keepWithNext=1),
        "toc_title": ParagraphStyle("toc_title", parent=base, fontName=F_BOLD, fontSize=15,
                                    leading=19, textColor=NAVY, spaceAfter=10),
        "card_label": ParagraphStyle("card_label", parent=base, fontSize=8.5, leading=11,
                                     textColor=colors.white),
        "card_value": ParagraphStyle("card_value", parent=base, fontName=F_BOLD, fontSize=26,
                                     leading=30, textColor=colors.white),
        "card_text": ParagraphStyle("card_text", parent=base, fontSize=9, leading=12,
                                    textColor=colors.white),
    }
    return st


def _p(text, style) -> Paragraph:
    return Paragraph(text, style)


def _e(s) -> str:
    return escape(str(s))


def _f(v, nd=2, dash="—") -> str:
    try:
        if v is None or not np.isfinite(v):
            return dash
    except TypeError:
        return dash
    return f"{v:.{nd}f}"


def _g(v) -> str:
    return f"{v:g}"


# ---------------------------------------------------------- doc template
class _NumberedCanvas(rl_canvas.Canvas):
    """Two-pass canvas: knows the total page count when drawing footers."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            if getattr(self, "_draw_footer", None):
                self._draw_footer(self, n)
            super().showPage()
        super().save()


class _Doc(BaseDocTemplate):
    def __init__(self, path, opts: ReportOptions, styles, **kw):
        super().__init__(str(path), pagesize=A4, leftMargin=MARGIN_L, rightMargin=MARGIN_R,
                         topMargin=MARGIN_T, bottomMargin=MARGIN_B, **kw)
        self.opts, self.st = opts, styles
        cover = Frame(MARGIN_L, MARGIN_B, FRAME_W, PAGE_H - MARGIN_B - 92 * mm, id="cover",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        body = Frame(MARGIN_L, MARGIN_B, FRAME_W, PAGE_H - MARGIN_T - MARGIN_B, id="body",
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate("cover", [cover], onPage=self._cover_page),
                               PageTemplate("body", [body], onPage=self._body_page)])
        self._h1 = 0

    # ---------------------------------------------------- page decorations
    def _cover_page(self, c, doc):
        o = self.opts
        c.saveState()
        c.setFillColor(NAVY)
        c.rect(0, PAGE_H - 78 * mm, PAGE_W, 78 * mm, stroke=0, fill=1)
        c.setFillColor(ACCENT)
        c.rect(0, PAGE_H - 80 * mm, PAGE_W, 2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#9fb4cc"))
        c.setFont(F_SEMI, 9)
        c.drawString(MARGIN_L, PAGE_H - 16 * mm, "SLIPSURFACE LE  ·  2B LİMİT DENGE ANALİZİ")
        if o.report_no:
            c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 16 * mm, f"Rapor No: {o.report_no}")
        c.setFillColor(colors.white)
        c.setFont(F_BOLD, 25)
        y = PAGE_H - 36 * mm
        for line in _wrap(_tr_upper(o.title), F_BOLD, 25, FRAME_W)[:2]:
            c.drawString(MARGIN_L, y, line)
            y -= 10 * mm
        c.setFont(F_REG, 13)
        c.setFillColor(colors.HexColor("#dbe5f1"))
        for line in _wrap(o.project, F_REG, 13, FRAME_W)[:2]:
            c.drawString(MARGIN_L, y, line)
            y -= 6.5 * mm
        c.restoreState()
        c._draw_footer = self._footer_cover

    def _body_page(self, c, doc):
        o = self.opts
        c.saveState()
        c.setFont(F_SEMI, 8)
        c.setFillColor(NAVY)
        c.drawString(MARGIN_L, PAGE_H - 13 * mm, "SlipSurface LE  ·  " + o.title)
        c.setFont(F_REG, 8)
        c.setFillColor(MUTED)
        proj = o.project if len(o.project) < 70 else o.project[:67] + "…"
        c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 13 * mm, proj)
        c.setStrokeColor(NAVY)
        c.setLineWidth(0.8)
        c.line(MARGIN_L, PAGE_H - 15.5 * mm, PAGE_W - MARGIN_R, PAGE_H - 15.5 * mm)
        c.restoreState()
        c._draw_footer = self._footer_body

    def _footer_cover(self, c, n):
        c.saveState()
        c.setFont(F_REG, 7.5)
        c.setFillColor(MUTED)
        c.drawString(MARGIN_L, 10 * mm, f"SlipSurface LE {__version__} ile üretilmiştir.")
        c.drawRightString(PAGE_W - MARGIN_R, 10 * mm, f"{n} sayfa")
        c.restoreState()

    def _footer_body(self, c, n):
        o = self.opts
        c.saveState()
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
        c.setFont(F_REG, 7.5)
        c.setFillColor(MUTED)
        left = "  ·  ".join(x for x in (o.company, o.author and f"Hazırlayan: {o.author}") if x)
        c.drawString(MARGIN_L, 10 * mm, left)
        c.drawCentredString(PAGE_W / 2, 10 * mm, o.date)
        c.setFont(F_SEMI, 8)
        c.setFillColor(NAVY)
        c.drawRightString(PAGE_W - MARGIN_R, 10 * mm, f"Sayfa {c.getPageNumber()} / {n}")
        c.restoreState()

    # --------------------------------------------------------------- TOC
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "toc_level", None) is not None:
            text = flowable.getPlainText()
            key = f"h{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (flowable.toc_level, text, self.page, key))
            self.canv.addOutlineEntry(text, key, level=flowable.toc_level, closed=False)


def _tr_upper(s: str) -> str:
    """Turkish-aware upper case (i -> İ, ı -> I)."""
    return str(s).replace("i", "İ").replace("ı", "I").upper()


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(t, font, size) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------- builder class
class _Builder:
    def __init__(self, results, opts: ReportOptions, figs: ReportFigures):
        self.r, self.o, self.figs = results, opts, figs
        self.p = results.project
        self.st = _styles()
        self.story: list = []
        self.n_fig = 0
        self.n_tab = 0
        self.sec = 0
        self.sub = 0

    # ----------------------------------------------------------- helpers
    def h1(self, text: str) -> None:
        self.sec += 1
        self.sub = 0
        para = _p(f"{self.sec}&nbsp;&nbsp;&nbsp;{_e(text)}", self.st["h1"])
        para.toc_level = 0
        self.story.append(CondPageBreak(60 * mm))
        self.story.append(para)
        self.story.append(_Rule())

    def h2(self, text: str) -> None:
        self.sub += 1
        para = _p(f"{self.sec}.{self.sub}&nbsp;&nbsp;{_e(text)}", self.st["h2"])
        para.toc_level = 1
        self.story.append(CondPageBreak(40 * mm))
        self.story.append(para)

    def appendix(self, letter: str, text: str) -> None:
        para = _p(f"Ek {letter}&nbsp;&nbsp;&nbsp;{_e(text)}", self.st["h1"])
        para.toc_level = 0
        self.story.append(PageBreak())
        self.story.append(para)
        self.story.append(_Rule())

    def para(self, text: str, style="body", keep_next: bool = False) -> None:
        para = _p(text, self.st[style])
        if keep_next:
            para.keepWithNext = 1
        self.story.append(para)

    def table(self, header: list[str], rows: list[list], widths: list[float],
              caption: str | None = None, align: list[str] | None = None,
              repeat: bool = True, swatches: dict[int, str] | None = None,
              row_colors: dict[tuple[int, int], colors.Color] | None = None,
              bold_rows: set[int] | None = None, compact: bool = False) -> None:
        """Styled table. widths are fractions of the frame width."""
        align = align or ["l"] * len(header)
        hs = {"l": self.st["head"], "r": self.st["head_c"], "c": self.st["head_c"]}
        cs = {"l": self.st["cell"], "r": self.st["cell_r"], "c": self.st["cell_c"]}
        data = [[_p(h, hs[a]) for h, a in zip(header, align, strict=False)]]
        for i, row in enumerate(rows):
            cells = []
            for j, (v, a) in enumerate(zip(row, align, strict=False)):
                txt = v if isinstance(v, str) else str(v)
                if bold_rows and i in bold_rows:
                    txt = f"<b>{txt}</b>"
                if row_colors and (i, j) in row_colors:
                    txt = f'<font color="{row_colors[(i, j)].hexval()}">{txt}</font>'
                cells.append(_p(txt, cs[a]))
            data.append(cells)
        t = Table(data, colWidths=[w * FRAME_W for w in widths], repeatRows=1 if repeat else 0)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
            ("LINEABOVE", (0, 0), (-1, 0), 1.0, NAVY),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, NAVY),
            ("LINEBELOW", (0, -1), (-1, -1), 0.8, NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.3 if compact else 2.6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3 if compact else 2.6),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), ZEBRA))
            if i < len(data) - 1:
                style.append(("LINEBELOW", (0, i), (-1, i), 0.25, RULE))
        if swatches:
            for i, col in swatches.items():
                style.append(("BACKGROUND", (0, i + 1), (0, i + 1), colors.HexColor(col)))
        t.setStyle(TableStyle(style))
        if caption:
            self.n_tab += 1
            # caption keeps with the table (keepWithNext); headings chain onto it.
            # No KeepTogether here: platypus cannot chain keepWithNext into one.
            self.story += [_p(f"Tablo {self.n_tab} – {_e(caption)}", self.st["tcaption"]), t]
        else:
            self.story.append(t)
        self.story.append(Spacer(1, 8))

    def kv_table(self, rows: list[tuple[str, str]], caption: str | None = None,
                 widths=(0.38, 0.62)) -> None:
        data = [[_p(k, self.st["head"]), _p(v, self.st["cell"])] for k, v in rows]
        t = Table(data, colWidths=[w * FRAME_W for w in widths])
        style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("LINEABOVE", (0, 0), (-1, 0), 1.0, NAVY),
                 ("LINEBELOW", (0, -1), (-1, -1), 0.8, NAVY),
                 ("TOPPADDING", (0, 0), (-1, -1), 2.8),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8),
                 ("LEFTPADDING", (0, 0), (-1, -1), 5)]
        for i in range(len(data)):
            style.append(("BACKGROUND", (0, i), (0, i), HEAD_BG))
            if i < len(data) - 1:
                style.append(("LINEBELOW", (0, i), (-1, i), 0.25, RULE))
        t.setStyle(TableStyle(style))
        if caption:
            self.n_tab += 1
            self.story += [_p(f"Tablo {self.n_tab} – {_e(caption)}", self.st["tcaption"]), t]
        else:
            self.story.append(t)
        self.story.append(Spacer(1, 8))

    def figure(self, png: bytes | None, caption: str, max_h: float = 120 * mm) -> None:
        if not png:
            return
        img = ImageReader(io.BytesIO(png))
        iw, ih = img.getSize()
        w = FRAME_W
        h = w * ih / iw
        if h > max_h:
            h = max_h
            w = h * iw / ih
        self.n_fig += 1
        im = Image(io.BytesIO(png), width=w, height=h)
        frame = Table([[im]], colWidths=[FRAME_W])
        frame.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, RULE),
                                   ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 3),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        frame.keepWithNext = 1
        self.story += [frame, _p(f"Şekil {self.n_fig} – {_e(caption)}", self.st["caption"])]

    # ------------------------------------------------------- evaluation
    def status(self, fs: float):
        t = self.o.target_fs
        if t is None or not np.isfinite(fs):
            return "—", MUTED
        if fs >= t:
            return "Yeterli", OK
        if fs >= 0.95 * t:
            return "Sınırda", WARN
        return "Yetersiz", BAD

    # ============================================================ sections
    def cover(self) -> None:
        o, st = self.o, self.st
        gm = self.r.global_minimum()
        rows = [("Proje", o.project or "—"), ("Analiz", o.analysis or "—"),
                ("Hazırlayan", o.author or "—"), ("Kontrol eden", o.checker or "—"),
                ("Firma / kurum", o.company or "—"), ("Rapor tarihi", o.date or "—"),
                ("Analiz zamanı", f"{self.r.finished}  ({self.r.elapsed:.1f} s)"),
                ("Model dosyası", o.model_file or "kaydedilmemiş")]
        info = Table([[_p(k, st["head"]), _p(_e(v), st["cell"])] for k, v in rows],
                     colWidths=[30 * mm, FRAME_W * 0.58 - 30 * mm])
        info.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
                                  ("LINEABOVE", (0, 0), (-1, 0), 1, NAVY),
                                  ("LINEBELOW", (0, -1), (-1, -1), 1, NAVY),
                                  ("TOPPADDING", (0, 0), (-1, -1), 3.2),
                                  ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
        # key result card
        if gm:
            k, res = gm
            label, col = self.status(res.fos)
            tgt = (f"Hedef FS = {o.target_fs:.2f}  ·  <b>{label}</b>"
                   if o.target_fs is not None else "Hedef FS tanımlanmadı")
            card_rows = [[_p("KRİTİK GÜVENLİK SAYISI", st["card_label"])],
                         [_p(f"FS = {res.fos:.3f}", st["card_value"])],
                         [_p(_e(method_name(k)) + " (global minimum)", st["card_text"])],
                         [_p(tgt, st["card_text"])]]
            card_bg = col if o.target_fs is not None else NAVY
        else:
            card_rows = [[_p("SONUÇ YOK", st["card_label"])],
                         [_p("—", st["card_value"])]]
            card_bg = MUTED
        card = Table(card_rows, colWidths=[FRAME_W * 0.38])
        card.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), card_bg),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                  ("TOPPADDING", (0, 0), (0, 0), 10),
                                  ("BOTTOMPADDING", (0, -1), (-1, -1), 10)]))
        top = Table([[info, card]], colWidths=[FRAME_W * 0.6, FRAME_W * 0.4])
        top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                 ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
        self.story += [top, Spacer(1, 9 * mm)]
        if self.figs.global_min:
            img = ImageReader(io.BytesIO(self.figs.global_min))
            iw, ih = img.getSize()
            h = min(FRAME_W * ih / iw, 92 * mm)
            w = h * iw / ih
            fig = Table([[Image(io.BytesIO(self.figs.global_min), width=w, height=h)]],
                        colWidths=[FRAME_W])
            fig.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, RULE),
                                     ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
            self.story += [fig, _p("Kritik kayma yüzeyi (global minimum)", st["caption"])]
        comments = [c for c in self.p.summary.comments if c and c.strip()]
        if comments:
            self.story.append(_p("<b>Açıklamalar</b>", st["small"]))
            for c in comments:
                self.story.append(_p("• " + _e(c), st["small"]))

    def toc(self) -> None:
        toc = TableOfContents()
        toc.levelStyles = [
            ParagraphStyle("toc0", fontName=F_SEMI, fontSize=10.5, leading=16, leftIndent=0,
                           textColor=NAVY),
            ParagraphStyle("toc1", fontName=F_REG, fontSize=9.5, leading=13, leftIndent=14,
                           textColor=INK),
        ]
        toc.dotsMinLevel = 0
        self.story += [_p("İçindekiler", self.st["toc_title"]), _Rule(), Spacer(1, 4), toc]

    # ------------------------------------------------------------ summary
    def summary(self) -> None:
        r, o = self.r, self.o
        self.h1("Özet")
        gm = r.global_minimum()
        p = self.p
        kind = {"circular": "dairesel", "noncircular": "dairesel olmayan ("
                + ("B-spline" if p.surfaces.noncircular_shape == "spline" else "poligonal")
                + ")",
                "user": "kullanıcı tanımlı"}[p.surfaces.surface_type]
        n = len(r.results)
        txt = (f"Bu raporda <b>{_e(o.project or p.summary.title)}</b> şevinin 2B limit denge "
               f"analizi sunulmaktadır. Analizde {n} yöntem kullanılmış, kritik kayma yüzeyi "
               f"{kind} yüzey araması ile belirlenmiştir.")
        if gm:
            k, res = gm
            txt += (f" En düşük güvenlik sayısı <b>{_e(method_name(k))}</b> yöntemiyle "
                    f"<b>FS = {res.fos:.3f}</b> olarak bulunmuştur")
            if o.target_fs is not None:
                label, col = self.status(res.fos)
                cmp = "üzerindedir" if res.fos >= o.target_fs else "altındadır"
                txt += (f"; bu değer hedef güvenlik sayısı FS = {o.target_fs:.2f} değerinin "
                        f"{cmp} (<font color='{col.hexval()}'><b>{label}</b></font>).")
            else:
                txt += "."
            fs = [x.fos for x in r.results.values() if np.isfinite(x.fos)]
            if len(fs) > 1:
                txt += (f" Yöntemler arasında FS {min(fs):.3f} – {max(fs):.3f} aralığında "
                        f"değişmektedir (fark %{100 * (max(fs) - min(fs)) / min(fs):.1f}).")
        extras = []
        if p.loads:
            extras.append(f"{len(p.loads)} dış yük")
        nsup = len(p.supports) + sum(len(_pattern_xs(p, pt, r.geometry))
                                     for pt in p.support_patterns)
        if nsup:
            extras.append(f"{nsup} destek elemanı")
        if p.facings:
            extras.append("püskürtme beton + hasır çelik kaplama")
        if p.tension_crack:
            extras.append("gerilme çatlağı")
        if p.seismic.kh or p.seismic.kv:
            extras.append(f"psödo-statik deprem yükü (kh = {p.seismic.kh:g})")
        if p.groundwater.method == "water_table" and p.water_table:
            extras.append("yeraltı suyu tablası")
        if extras:
            txt += " Modelde " + ", ".join(extras) + " dikkate alınmıştır."
        self.para(txt)
        self.story.append(Spacer(1, 6))
        if r.results:
            self.results_table(caption="Yöntemlere göre kritik güvenlik sayıları")
            self.story.append(self.fs_chart())

    def results_table(self, caption: str) -> None:
        r = self.r
        gm = r.global_minimum()
        header = ["Yöntem", "FS", "λ", "Çıkış x [m]", "Giriş x [m]", "Merkez (x; y) [m]",
                  "R [m]", "Yüzey", "Durum"]
        rows, rc, bold = [], {}, set()
        for i, (k, res) in enumerate(r.results.items()):
            s = res.surface
            circ = hasattr(s, "r")
            lab, col = self.status(res.fos)
            rows.append([_e(method_name(k)), f"{res.fos:.3f}", _f(res.lem.lam, 3),
                         f"{res.slices.x_exit:.2f}", f"{res.slices.x_entry:.2f}",
                         f"{s.xc:.2f}; {s.yc:.2f}" if circ else "—",
                         f"{s.r:.2f}" if circ else "—", str(res.n_evals),
                         lab])
            rc[(i, 8)] = col
            if gm and k == gm[0]:
                bold.add(i)
        for k, e in r.errors.items():
            rows.append([_e(method_name(k)), "—", "—", "—", "—", "—", "—", "—",
                         _e(e[:40])])
        widths = [0.21, 0.07, 0.07, 0.1, 0.1, 0.15, 0.07, 0.1, 0.13]
        align = ["l", "r", "r", "r", "r", "r", "r", "r", "c"]
        if not any(hasattr(res.surface, "r") for res in r.results.values()):
            # non-circular surfaces only: no centre / radius columns
            drop = (5, 6)
            header = [h for i, h in enumerate(header) if i not in drop]
            rows = [[v for i, v in enumerate(row) if i not in drop] for row in rows]
            align = [a for i, a in enumerate(align) if i not in drop]
            widths = [0.27, 0.09, 0.09, 0.13, 0.13, 0.13, 0.16]
            rc = {(i, 6): c for (i, _), c in rc.items()}
        self.table(header, rows, widths, caption, align, row_colors=rc, bold_rows=bold)
        if gm:
            self.para("Kalın satır global minimumu gösterir. λ: ara-dilim kuvvet ölçek "
                      "katsayısı (Spencer / GLE). Yüzey: aramada değerlendirilen yüzey sayısı.",
                      "small")
            self.story.append(Spacer(1, 6))

    def fs_chart(self) -> Drawing:
        res = [(k, v.fos) for k, v in self.r.results.items() if np.isfinite(v.fos)]
        tgt = self.o.target_fs
        n = len(res)
        bar_h, gap, left, right, top, bottom = 13, 7, 128, 40, 22, 26
        H = top + bottom + n * (bar_h + gap)
        W = FRAME_W
        d = Drawing(W, H)
        vmax = max([f for _, f in res] + ([tgt] if tgt else [])) * 1.15
        vmax = max(vmax, 0.5)
        sx = (W - left - right) / vmax
        d.add(String(0, H - 12, "Güvenlik sayısı karşılaştırması", fontName=F_SEMI,
                     fontSize=9, fillColor=NAVY))
        step = _nice_step(vmax / 5)
        v = 0.0
        while v <= vmax + 1e-9:
            x = left + v * sx
            d.add(Line(x, bottom, x, H - top, strokeColor=RULE, strokeWidth=0.4))
            d.add(String(x, bottom - 11, f"{v:g}", fontName=F_REG, fontSize=7.5,
                         fillColor=MUTED, textAnchor="middle"))
            v += step
        d.add(String(left + (W - left - right) / 2, 2, "FS", fontName=F_SEMI, fontSize=8,
                     fillColor=MUTED, textAnchor="middle"))
        gm = self.r.global_minimum()
        for i, (k, f) in enumerate(res):
            y = H - top - (i + 1) * (bar_h + gap) + gap / 2
            _, col = self.status(f)
            if tgt is None:
                col = NAVY
            d.add(Rect(left, y, f * sx, bar_h, fillColor=col, strokeColor=None))
            if gm and k == gm[0]:
                d.add(Rect(left, y, f * sx, bar_h, fillColor=None, strokeColor=INK,
                           strokeWidth=1.1))
            d.add(String(left - 6, y + 3.5, method_name(k), fontName=F_REG, fontSize=8.5,
                         fillColor=INK, textAnchor="end"))
            d.add(String(left + f * sx + 4, y + 3.5, f"{f:.3f}", fontName=F_SEMI, fontSize=8.5,
                         fillColor=INK))
        if tgt:
            x = left + tgt * sx
            d.add(Line(x, bottom - 2, x, H - top + 4, strokeColor=BAD, strokeWidth=1.1,
                       strokeDashArray=[4, 2]))
            d.add(String(x + 3, H - top + 2, f"Hedef FS = {tgt:.2f}", fontName=F_SEMI,
                         fontSize=7.5, fillColor=BAD))
        return d

    # -------------------------------------------------------------- model
    def model(self) -> None:
        p, o = self.p, self.o
        self.h1("Model ve Geometri")
        g = self.r.geometry
        self.para(f"Model {len(g.regions)} bölge ve {len(p.materials)} malzemeden "
                  f"oluşmaktadır. Dış sınır {len(p.external)} köşelidir; model x = "
                  f"{g.x_min:.2f} – {g.x_max:.2f} m aralığındadır. "
                  + ("Yeraltı suyu tablası tanımlıdır. " if p.water_table else "")
                  + ("Gerilme çatlağı sınırı tanımlıdır." if p.tension_crack else ""))
        self.story.append(Spacer(1, 4))
        self.figure(self.figs.model, "Analiz modeli: geometri, malzemeler, yükler ve destekler")
        if o.materials:
            self.h2("Malzeme özellikleri")
            mc = [m for m in p.materials if m.model == "MC"]
            hb = [m for m in p.materials if m.model == "HB"]
            if mc:
                rows, sw = [], {}
                for i, m in enumerate(mc):
                    sw[i] = m.color
                    rows.append(["", _e(m.name), "Mohr-Coulomb", _g(m.gamma),
                                 _g(m.gamma_sat) if m.use_sat else "—", _g(m.c), _g(m.phi),
                                 _water(m)])
                self.table(["", "Malzeme", "Model", "γ [kN/m³]", "γ<sub>sat</sub> [kN/m³]",
                            "c' [kPa]", "φ' [°]", "Su"], rows,
                           [0.04, 0.22, 0.15, 0.1, 0.12, 0.1, 0.09, 0.18],
                           "Malzeme parametreleri (Mohr-Coulomb)",
                           ["c", "l", "l", "r", "r", "r", "r", "l"], swatches=sw)
            if hb:
                rows, sw = [], {}
                for i, m in enumerate(hb):
                    sw[i] = m.color
                    rows.append(["", _e(m.name), _g(m.gamma),
                                 _g(m.gamma_sat) if m.use_sat else "—", _g(m.sigma_ci),
                                 _g(m.gsi), _g(m.mi), _g(m.d), _water(m)])
                self.table(["", "Malzeme", "γ [kN/m³]", "γ<sub>sat</sub>", "σ<sub>ci</sub> [kPa]",
                            "GSI", "m<sub>i</sub>", "D", "Su"], rows,
                           [0.04, 0.2, 0.1, 0.09, 0.12, 0.08, 0.08, 0.07, 0.22],
                           "Malzeme parametreleri (genelleştirilmiş Hoek-Brown)",
                           ["c", "l", "r", "r", "r", "r", "r", "r", "l"], swatches=sw)

    # ----------------------------------------------------------- settings
    def settings(self) -> None:
        p = self.p
        self.h1("Analiz Ayarları")
        gw = p.groundwater
        gwt = {"water_table": "Yeraltı suyu tablası (YASS)", "ru": f"Ru katsayısı (Ru = {gw.ru:g})",
               "none": "Yok (kuru)"}.get(gw.method, gw.method)
        s = p.surfaces
        lim = []
        if s.left_range:
            lim.append(f"sol uç x = {s.left_range[0]:.2f} – {s.left_range[1]:.2f}")
        if s.right_range:
            lim.append(f"sağ uç x = {s.right_range[0]:.2f} – {s.right_range[1]:.2f}")
        from slipsurface.project import EFFORT
        pop, it = EFFORT.get(s.effort, EFFORT["normal"])
        shape = ("B-spline, kontrol noktası" if s.noncircular_shape == "spline"
                 else "poligonal, ara köşe")
        surf_txt = {"circular": "Dairesel", "noncircular":
                    f"Dairesel olmayan ({shape} sayısı {s.n_ctrl}"
                    + (", konveks" if s.convex_only else "") + ")",
                    "user": "Kullanıcı tanımlı yüzey"}[s.surface_type]
        inter = {"half-sine": "yarım sinüs", "constant": "sabit", "clipped-sine":
                 "kırpılmış sinüs", "trapezoidal": "trapez"}.get(p.methods.interslice,
                                                                p.methods.interslice)
        rows = [
            ("Yöntemler", ", ".join(_e(method_name(k)) for k in p.methods.methods)),
            ("Birim sistemi", "Metrik — kN, kPa, m"),
            ("Göçme yönü", "Sağdan sola" if p.general.failure_direction == "right_to_left"
             else "Soldan sağa"),
            ("Dilim sayısı", str(p.methods.n_slices)),
            ("Tolerans / maks. iterasyon", f"{p.methods.tolerance:g} / {p.methods.max_iter}"),
            ("GLE ara-dilim fonksiyonu", inter),
            ("Kayma yüzeyi", surf_txt),
            ("Arama", f"Diferansiyel evrim + Nelder-Mead (popülasyon {pop}, en çok {it} nesil, "
                      f"çekirdek {s.seed})"),
            ("Kayma sınırları", "; ".join(lim) if lim else "Tüm model"),
            ("Minimum kayan kütle derinliği", f"{p.advanced.min_depth:g} m"),
            ("Kabul edilebilirlik kontrolü", "Açık (mα &lt; 0.2 ve negatif taban kayma "
             "direnci reddedilir)" if p.advanced.check_admissibility else "Kapalı"),
            ("Boşluk suyu basıncı", gwt + f", γ<sub>w</sub> = {gw.gamma_w:g} kN/m³"),
            ("Sismik katsayılar", f"k<sub>h</sub> = {p.seismic.kh:g}, "
                                  f"k<sub>v</sub> = {p.seismic.kv:g}"),
        ]
        if p.tension_crack:
            rows.append(("Gerilme çatlağı", f"Çatlak suyu %{100 * gw.crack_water:.0f} dolu"))
        self.kv_table(rows, "Analiz ve arama parametreleri")

    # ------------------------------------------------- loads and supports
    def loads(self) -> None:
        p = self.p
        has = p.loads or p.supports or p.support_patterns or p.facings or p.tension_crack
        if not has:
            return
        self.h1("Yükler, Destekler ve Kaplama")
        if p.loads:
            self.h2("Dış yükler")
            rows = []
            for i, ld in enumerate(p.loads, 1):
                if ld["kind"] == "distributed":
                    (x1, _), (x2, _) = ld["points"]
                    yon = "düşey" if ld.get("orientation", "vertical") == "vertical" \
                        else "yüzeye dik"
                    q = ld["q"]
                    rows.append([str(i), "Yayılı", f"x = {min(x1, x2):.2f} – {max(x1, x2):.2f}",
                                 f"{q[0]:g}" + (f" – {q[1]:g}" if q[1] != q[0] else "") + " kPa",
                                 yon])
                else:
                    x, y = ld["point"]
                    rows.append([str(i), "Tekil", f"({x:.2f}; {y:.2f})",
                                 f"{ld['magnitude']:g} kN/m", f"{ld.get('angle', 270):g}°"])
            self.table(["No", "Tip", "Konum [m]", "Büyüklük", "Yön / açı"], rows,
                       [0.07, 0.13, 0.32, 0.25, 0.23], "Dış yükler",
                       ["c", "l", "l", "r", "l"])
        if p.supports or p.support_patterns:
            from slipsurface.loads import SUPPORT_KINDS
            self.h2("Destek elemanları")
            used = {sp["type"] for sp in p.supports + p.support_patterns}
            rows, sw = [], {}
            for i, t in enumerate([t for t in p.support_types if t.name in used]):
                sw[i] = t.color
                kind = t.kind
                bond = (f"{t.bond_strength:g}" if kind in ("grouted_tieback", "soil_nail")
                        else (f"{t.pullout:g}" if kind == "geotextile" else "—"))
                rows.append(["", _e(t.name), SUPPORT_KINDS[kind],
                             _g(t.spacing) if kind != "geotextile" else "—", _g(t.tensile),
                             _g(t.plate) if kind == "soil_nail" else "—", bond,
                             _g(t.bond_length) if kind == "grouted_tieback" else "—",
                             "pasif" if t.application == "passive" else "aktif",
                             "paralel" if t.orientation == "parallel" else "teğet"])
            self.table(["", "Ad", "Tip", "Aralık [m]", "Çekme [kN]", "Plaka [kN]",
                        "Kök [kN/m]", "Kök boyu [m]", "Uygulama", "Doğrultu"], rows,
                       [0.035, 0.14, 0.2, 0.08, 0.09, 0.08, 0.09, 0.09, 0.09, 0.095],
                       "Destek tipleri", ["c", "l", "l", "r", "r", "r", "r", "r", "c", "c"],
                       swatches=sw)
            if p.supports:
                rows = []
                for i, sp in enumerate(p.supports, 1):
                    a, b = np.array(sp["a"], float), np.array(sp["b"], float)
                    d = b - a
                    L = float(np.hypot(*d))
                    ang = float(np.degrees(np.arctan2(-d[1], abs(d[0]))))
                    rows.append([str(i), _e(sp["type"]), f"({a[0]:.2f}; {a[1]:.2f})",
                                 f"({b[0]:.2f}; {b[1]:.2f})", f"{L:.2f}", f"{ang:.1f}"])
                self.table(["No", "Tip", "Baş A (x; y) [m]", "Uç B (x; y) [m]", "Boy [m]",
                            "Eğim [°]"], rows, [0.07, 0.23, 0.22, 0.22, 0.12, 0.14],
                           "Tekil destekler", ["c", "l", "r", "r", "r", "r"])
            if p.support_patterns:
                rows = []
                for i, pt in enumerate(p.support_patterns, 1):
                    n = len(_pattern_xs(p, pt, self.r.geometry))
                    rows.append([str(i), _e(pt["type"]),
                                 f"{pt['p1'][0]:.2f} – {pt['p2'][0]:.2f}", f"{pt['spacing']:g}",
                                 f"{pt.get('offset', 0):g}", f"{pt.get('angle', 15):g}",
                                 f"{pt['length']:g}", str(n)])
                self.table(["No", "Tip", "x aralığı [m]", "Aralık [m]", "İlk [m]", "Eğim [°]",
                            "Boy [m]", "Adet"], rows,
                           [0.07, 0.23, 0.18, 0.1, 0.1, 0.1, 0.1, 0.12],
                           "Bulon / ankraj paternleri (şev yüzü boyunca eşit aralıklı)",
                           ["c", "l", "r", "r", "r", "r", "r", "r"])
        if p.facings:
            self.h2("Kaplama (püskürtme beton + hasır çelik)")
            used = {f["type"] for f in p.facings}
            rows, sw = [], {}
            for i, t in enumerate([t for t in p.facing_types if t.name in used]):
                sw[i] = t.color
                rows.append(["", _e(t.name), f"{100 * t.thickness:g}", _g(t.gamma), _g(t.tau),
                             f"{_e(t.mesh)} ({t.mesh_as:g})", _g(t.mesh_fy),
                             f"{t.capacity:.1f}",
                             "pasif" if t.application == "passive" else "aktif"])
            self.table(["", "Ad", "t [cm]", "γ [kN/m³]", "τ [kPa]", "Hasır (A<sub>s</sub> "
                        "[mm²/m])", "f<sub>y</sub> [MPa]", "T [kN/m]", "Uygulama"], rows,
                       [0.035, 0.24, 0.07, 0.09, 0.08, 0.16, 0.09, 0.1, 0.105],
                       "Kaplama tipleri", ["c", "l", "r", "r", "r", "l", "r", "r", "c"],
                       swatches=sw)
            rows = [[str(i), _e(f["type"]), f"{min(f['x1'], f['x2']):.2f}",
                     f"{max(f['x1'], f['x2']):.2f}"] for i, f in enumerate(p.facings, 1)]
            self.table(["No", "Kaplama tipi", "x<sub>1</sub> [m]", "x<sub>2</sub> [m]"], rows,
                       [0.08, 0.52, 0.2, 0.2], "Kaplama atamaları", ["c", "l", "r", "r"])
            self.para("Kaplama kapasitesi T = τ·t + A<sub>s</sub>·f<sub>y</sub>; kayma yüzeyinin "
                      "kaplamalı yüzeyden çıktığı/girdiği noktada yüzeye teğet ve kaymaya karşı "
                      "uygulanır. Kaplama ağırlığı γ·t yüzey yükü olarak eklenir.", "small")
        if p.tension_crack:
            self.h2("Gerilme çatlağı")
            xs = [q[0] for q in p.tension_crack]
            self.para(f"Gerilme çatlağı sınırı x = {min(xs):.2f} – {max(xs):.2f} m arasında "
                      f"tanımlıdır; çatlak suyu %{100 * p.groundwater.crack_water:.0f} doludur. "
                      "Çatlak suyu itkisi V = ½·γ<sub>w</sub>·h<sub>w</sub>² göçme yönünde, "
                      "h<sub>w</sub>/3 yükseklikte uygulanır.")

    # ------------------------------------------------------------ results
    def results(self) -> None:
        r, o = self.r, self.o
        self.h1("Analiz Sonuçları")
        gm = r.global_minimum()
        if not r.results:
            self.para("Hiçbir yöntemde geçerli bir çözüm bulunamadı.")
            return
        self.results_table(caption="Kritik kayma yüzeyleri ve güvenlik sayıları")
        if o.global_figure and gm:
            self.h2("Kritik kayma yüzeyi (global minimum)")
            k, res = gm
            self.figure(self.figs.global_min,
                        f"{method_name(k)} — FS = {res.fos:.3f}; dilimler, en düşük "
                        f"yüzeyler ve FS lejantı", max_h=125 * mm)
        if o.method_figures and len(self.figs.methods) > 0:
            self.h2("Yöntemlere göre kritik yüzeyler")
            for k, png in self.figs.methods.items():
                if gm and k == gm[0] and o.global_figure:
                    continue
                res = r.results.get(k)
                if res is None:
                    continue
                self.figure(png, f"{method_name(k)} — FS = {res.fos:.3f}", max_h=100 * mm)
        if o.support_forces:
            rows = []
            for k, res in r.results.items():
                for f in res.slices.support_forces:
                    rows.append([_e(method_name(k)), _e(f.label), f"{f.x:.2f}", f"{f.y:.2f}",
                                 f"{f.T:.1f}", _f(f.L_in), _f(f.L_out), _e(f.governing),
                                 "pasif" if f.passive else "aktif"])
            if rows:
                self.h2("Mobilize destek kuvvetleri")
                self.table(["Yöntem", "Eleman", "x [m]", "y [m]", "T [kN/m]", "L<sub>iç</sub> [m]",
                            "L<sub>dış</sub> [m]", "Belirleyici", "Uyg."], rows,
                           [0.19, 0.15, 0.08, 0.08, 0.09, 0.08, 0.08, 0.17, 0.08],
                           "Kritik yüzeyleri kesen destek ve kaplama elemanlarının kuvvetleri",
                           ["l", "l", "r", "r", "r", "r", "r", "l", "c"])
                self.para("T: düzlem dışı aralığa bölünmüş kapasite (kN/m). Pasif uygulamada "
                          "kuvvet dengede T/F olarak mobilize olur.", "small")
        if self.p.tension_crack:
            rows = []
            for k, res in r.results.items():
                ck = res.slices.crack
                if ck is None:
                    rows.append([_e(method_name(k)), "—", "—", "—", "—"])
                else:
                    rows.append([_e(method_name(k)), f"{ck['x']:.2f}", f"{ck['depth']:.2f}",
                                 f"{ck['hw']:.2f}", f"{ck['Pw']:.2f}"])
            self.h2("Kritik yüzeylerde gerilme çatlağı")
            self.table(["Yöntem", "x [m]", "Derinlik [m]", "h<sub>w</sub> [m]", "V [kN/m]"], rows,
                       [0.36, 0.16, 0.16, 0.16, 0.16], "Gerilme çatlağı ve çatlak suyu itkisi",
                       ["l", "r", "r", "r", "r"])

    # --------------------------------------------------------- appendices
    def slice_table(self, letter: str) -> None:
        gm = self.r.global_minimum()
        if not gm:
            return
        k, res = gm
        s = res.slices
        self.appendix(letter, f"Dilim Verileri — {method_name(k)}")
        self.para(f"Global minimum kayma yüzeyinin ({method_name(k)}, FS = {res.fos:.3f}) "
                  f"{s.n} dilimine ait veriler. α: taban açısı (göçme yönünde pozitif), "
                  "c, φ: tabanda kullanılan dayanım parametreleri (Hoek-Brown için "
                  "σ<sub>n</sub>' ≈ W/b − u ile anlık değerler).", "small", keep_next=True)
        rows = []
        for i in range(s.n):
            mat = s.materials[s.mat_idx[i]]
            c, tp = mat.strength(np.array([max(s.W[i] / s.b[i] - s.u[i], 0.0)]))
            rows.append([str(i + 1), f"{0.5 * (s.xl[i] + s.xr[i]):.2f}", f"{s.b[i]:.3f}",
                         f"{s.y_base[i]:.2f}", f"{s.y_top[i] - s.y_base[i]:.2f}",
                         f"{np.degrees(s.alpha[i]) * (-s.direction):.1f}", f"{s.l[i]:.3f}",
                         f"{s.W[i]:.2f}", f"{s.u[i]:.2f}", f"{c[0]:.2f}",
                         f"{np.degrees(np.arctan(tp[0])):.1f}", _e(mat.name)])
        self.table(["No", "x<sub>orta</sub> [m]", "b [m]", "y<sub>taban</sub> [m]", "h [m]",
                    "α [°]", "l [m]", "W [kN/m]", "u [kPa]", "c [kPa]", "φ [°]", "Malzeme"],
                   rows, [0.05, 0.08, 0.07, 0.08, 0.07, 0.07, 0.07, 0.09, 0.08, 0.08, 0.07,
                          0.19], f"Dilim verileri ({method_name(k)})",
                   ["c", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "l"], compact=True)

    def coordinates(self, letter: str) -> None:
        p = self.p
        self.appendix(letter, "Koordinatlar")

        def block(title, pts):
            rows = [[str(i), f"{q[0]:.3f}", f"{q[1]:.3f}"] for i, q in enumerate(pts, 1)]
            # three side-by-side columns to save space
            self.table(["No", "x [m]", "y [m]"], rows, [0.1, 0.2, 0.2], title,
                       ["c", "r", "r"])
        block("Dış sınır", p.external)
        for i, b in enumerate(p.material_boundaries, 1):
            block(f"Malzeme sınırı {i}", b)
        if p.water_table:
            block("Yeraltı suyu tablası", p.water_table)
        if p.tension_crack:
            block("Gerilme çatlağı sınırı", p.tension_crack)
        gm = self.r.global_minimum()
        if gm:
            k, res = gm
            s = res.surface
            if hasattr(s, "r"):
                self.kv_table([("Merkez", f"({s.xc:.3f}; {s.yc:.3f}) m"),
                               ("Yarıçap", f"{s.r:.3f} m"),
                               ("Çıkış / giriş x", f"{res.slices.x_exit:.3f} / "
                                                   f"{res.slices.x_entry:.3f} m")],
                              f"Kritik daire ({method_name(k)})")
            else:
                pts = s.points(res.slices.x_exit, res.slices.x_entry, 25)
                block(f"Kritik yüzey noktaları ({method_name(k)})", pts)

    def closing(self) -> None:
        self.story.append(Spacer(1, 10))
        self.para(f"Bu rapor SlipSurface LE {__version__} ile otomatik olarak üretilmiştir. "
                  "Sonuçlar girilen geometri, malzeme ve yükleme verilerine dayanır; "
                  "mühendislik yargısıyla değerlendirilmesi ve doğrulanması kullanıcının "
                  "sorumluluğundadır.", "small")

    # ------------------------------------------------------------- build
    def build(self, path) -> int:
        o = self.o
        self.story.append(NextPageTemplate("body"))
        self.cover()
        self.story.append(PageBreak())
        if o.toc:
            self.toc()
            self.story.append(PageBreak())
        self.summary()
        if o.model:
            self.story.append(PageBreak())
            self.model()
        if o.settings:
            self.settings()
        if o.loads:
            self.loads()
        if o.results:
            self.story.append(PageBreak())
            self.results()
        letters = iter("ABCDEF")
        if o.slice_table:
            self.slice_table(next(letters))
        if o.coordinates:
            self.coordinates(next(letters))
        self.closing()
        doc = _Doc(path, o, self.st, title=o.title, author=o.author,
                   subject=o.project, creator=f"SlipSurface LE {__version__}")
        story = [NextPageTemplate("cover")] + self.story
        # the cover template must be the first page template
        doc.multiBuild(story, canvasmaker=_NumberedCanvas)
        return doc.page


class _Rule(Spacer):
    """Thin accent rule under section headings."""

    def __init__(self):
        super().__init__(FRAME_W, 6)
        self.keepWithNext = 1

    def draw(self):
        c = self.canv
        c.setStrokeColor(ACCENT)
        c.setLineWidth(1.6)
        c.line(0, 4, 28 * mm, 4)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(28 * mm, 4, FRAME_W, 4)


def _water(m) -> str:
    if not m.use_water:
        return "Su etkisi yok"
    return "YASS" + (f", H<sub>u</sub> = {m.hu:g}" if m.hu != 1 else "")


def _nice_step(x: float) -> float:
    if x <= 0:
        return 1.0
    e = 10 ** np.floor(np.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if m * e >= x:
            return float(m * e)
    return float(10 * e)


def _pattern_xs(p, pt, geom) -> list:
    try:
        return p.pattern_bolts(pt, geom)
    except Exception:
        log.warning("Bulon paterni rapora çizilemedi: %s", pt, exc_info=True)
        return []


# ================================================================ public
def build_pdf(results, path, opts: ReportOptions | None = None,
              figs: ReportFigures | None = None) -> int:
    """Write the report; returns the number of pages."""
    opts = opts or ReportOptions()
    figs = figs or ReportFigures()
    p = results.project
    if not opts.project:
        opts.project = p.summary.title
    if not opts.analysis:
        opts.analysis = p.summary.analysis
    if not opts.author:
        opts.author = p.summary.author
    if not opts.company:
        opts.company = p.summary.company
    if not opts.date:
        opts.date = _dt.date.today().strftime("%d.%m.%Y")
    b = _Builder(results, opts, figs)
    return b.build(Path(path))
