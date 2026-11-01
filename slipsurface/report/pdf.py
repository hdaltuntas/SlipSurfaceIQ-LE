"""Professional PDF report of a slope stability analysis.

    build_pdf(results, path, ReportOptions(...), ReportFigures(...)) -> page count

Layout (A4 portrait): cover page (title band, project data, key result card,
critical-surface figure), table of contents, numbered sections (summary,
model, materials, analysis settings, loads & supports, results with FS chart
and figures), appendices (slice data, coordinates). Every body page carries a
running header and a footer with "Page n / N".

The module is Qt-free: the drawings are rendered by the GUI
(slipsurface.ui.report_figures) and passed in as PNG bytes, so the report can
also be produced (without figures) from scripts and tests.
"""

from __future__ import annotations

from slipsurface.lem.bishop import slice_strength

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
from slipsurface.analysis import governing_kv_lines
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
        pdfmetrics.registerFontFamily(
            F_REG, normal=F_REG, bold=F_BOLD, italic=F_IT, boldItalic=F_BOLD
        )
    except Exception:  # fonts missing: fall back (no Turkish glyphs)
        log.warning(
            "PDF fonts could not be loaded; falling back to Helvetica (some characters may be missing).",
            exc_info=True,
        )
        F_REG, F_BOLD, F_SEMI, F_IT = (
            "Helvetica",
            "Helvetica-Bold",
            "Helvetica-Bold",
            "Helvetica-Oblique",
        )
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
    title: str = "Slope Stability Analysis Report"
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
        "cell_r": ParagraphStyle(
            "cell_r", parent=base, fontSize=8.3, leading=10.4, alignment=TA_RIGHT
        ),
        "cell_c": ParagraphStyle(
            "cell_c", parent=base, fontSize=8.3, leading=10.4, alignment=TA_CENTER
        ),
        "head": ParagraphStyle(
            "head", parent=base, fontName=F_SEMI, fontSize=8.3, leading=10.4, textColor=NAVY_D
        ),
        "head_c": ParagraphStyle(
            "head_c",
            parent=base,
            fontName=F_SEMI,
            fontSize=8.3,
            leading=10.4,
            textColor=NAVY_D,
            alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base,
            fontName=F_BOLD,
            fontSize=15,
            leading=19,
            textColor=NAVY,
            spaceBefore=4,
            spaceAfter=6,
            keepWithNext=1,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base,
            fontName=F_SEMI,
            fontSize=11.5,
            leading=15,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=1,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base,
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=10,
        ),
        "tcaption": ParagraphStyle(
            "tcaption",
            parent=base,
            fontName=F_SEMI,
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
            spaceBefore=6,
            spaceAfter=3,
            keepWithNext=1,
        ),
        "toc_title": ParagraphStyle(
            "toc_title",
            parent=base,
            fontName=F_BOLD,
            fontSize=15,
            leading=19,
            textColor=NAVY,
            spaceAfter=10,
        ),
        "card_label": ParagraphStyle(
            "card_label", parent=base, fontSize=8.5, leading=11, textColor=colors.white
        ),
        "card_value": ParagraphStyle(
            "card_value",
            parent=base,
            fontName=F_BOLD,
            fontSize=26,
            leading=30,
            textColor=colors.white,
        ),
        "card_text": ParagraphStyle(
            "card_text", parent=base, fontSize=9, leading=12, textColor=colors.white
        ),
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
        super().__init__(
            str(path),
            pagesize=A4,
            leftMargin=MARGIN_L,
            rightMargin=MARGIN_R,
            topMargin=MARGIN_T,
            bottomMargin=MARGIN_B,
            **kw,
        )
        self.opts, self.st = opts, styles
        cover = Frame(
            MARGIN_L,
            MARGIN_B,
            FRAME_W,
            PAGE_H - MARGIN_B - 92 * mm,
            id="cover",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        body = Frame(
            MARGIN_L,
            MARGIN_B,
            FRAME_W,
            PAGE_H - MARGIN_T - MARGIN_B,
            id="body",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(
            [
                PageTemplate("cover", [cover], onPage=self._cover_page),
                PageTemplate("body", [body], onPage=self._body_page),
            ]
        )
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
        c.drawString(
            MARGIN_L, PAGE_H - 16 * mm, "SLIPSURFACEIQ LE  ·  2D LIMIT EQUILIBRIUM ANALYSIS"
        )
        if o.report_no:
            c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 16 * mm, f"Report No.: {o.report_no}")
        c.setFillColor(colors.white)
        c.setFont(F_BOLD, 25)
        y = PAGE_H - 36 * mm
        title = str(o.title).upper()
        for line in _wrap(title, F_BOLD, 25, FRAME_W)[:2]:
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
        c.drawString(MARGIN_L, PAGE_H - 13 * mm, "SlipSurfaceIQ LE  ·  " + o.title)
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
        c.drawString(MARGIN_L, 10 * mm, f"Produced with SlipSurfaceIQ LE {__version__}.")
        c.drawRightString(PAGE_W - MARGIN_R, 10 * mm, f"{n} pages")
        c.restoreState()

    def _footer_body(self, c, n):
        o = self.opts
        c.saveState()
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(MARGIN_L, 14 * mm, PAGE_W - MARGIN_R, 14 * mm)
        c.setFont(F_REG, 7.5)
        c.setFillColor(MUTED)
        left = "  ·  ".join(x for x in (o.company, o.author and f"Prepared by: {o.author}") if x)
        c.drawString(MARGIN_L, 10 * mm, left)
        c.drawCentredString(PAGE_W / 2, 10 * mm, o.date)
        c.setFont(F_SEMI, 8)
        c.setFillColor(NAVY)
        c.drawRightString(PAGE_W - MARGIN_R, 10 * mm, f"Page {c.getPageNumber()} / {n}")
        c.restoreState()

    # --------------------------------------------------------------- TOC
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "toc_level", None) is not None:
            text = flowable.getPlainText()
            key = f"h{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (flowable.toc_level, text, self.page, key))
            self.canv.addOutlineEntry(text, key, level=flowable.toc_level, closed=False)


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

    def table(
        self,
        header: list[str],
        rows: list[list],
        widths: list[float],
        caption: str | None = None,
        align: list[str] | None = None,
        repeat: bool = True,
        swatches: dict[int, str] | None = None,
        row_colors: dict[tuple[int, int], colors.Color] | None = None,
        bold_rows: set[int] | None = None,
        compact: bool = False,
    ) -> None:
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
            self.story += [
                _p(f"Table {self.n_tab} – {_e(caption)}", self.st["tcaption"]),
                t,
            ]
        else:
            self.story.append(t)
        self.story.append(Spacer(1, 8))

    def kv_table(
        self, rows: list[tuple[str, str]], caption: str | None = None, widths=(0.38, 0.62)
    ) -> None:
        data = [[_p(k, self.st["head"]), _p(v, self.st["cell"])] for k, v in rows]
        t = Table(data, colWidths=[w * FRAME_W for w in widths])
        style = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEABOVE", (0, 0), (-1, 0), 1.0, NAVY),
            ("LINEBELOW", (0, -1), (-1, -1), 0.8, NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 2.8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]
        for i in range(len(data)):
            style.append(("BACKGROUND", (0, i), (0, i), HEAD_BG))
            if i < len(data) - 1:
                style.append(("LINEBELOW", (0, i), (-1, i), 0.25, RULE))
        t.setStyle(TableStyle(style))
        if caption:
            self.n_tab += 1
            self.story += [
                _p(f"Table {self.n_tab} – {_e(caption)}", self.st["tcaption"]),
                t,
            ]
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
        frame.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        frame.keepWithNext = 1
        self.story += [
            frame,
            _p(f"Figure {self.n_fig} – {_e(caption)}", self.st["caption"]),
        ]

    # ------------------------------------------------------- evaluation
    def status(self, fs: float):
        t = self.o.target_fs
        if t is None or not np.isfinite(fs):
            return "—", MUTED
        if fs >= t:
            return "Adequate", OK
        if fs >= 0.95 * t:
            return "Marginal", WARN
        return "Inadequate", BAD

    # ============================================================ sections
    def cover(self) -> None:
        o, st = self.o, self.st
        gm = self.r.global_minimum()
        rows = [
            ("Project", o.project or "—"),
            ("Analysis", o.analysis or "—"),
            ("Author", o.author or "—"),
            ("Checked by", o.checker or "—"),
            ("Company", o.company or "—"),
            ("Report date", o.date or "—"),
            ("Analysed at", f"{self.r.finished}  ({self.r.elapsed:.1f} s)"),
            ("Model file", o.model_file or "not saved"),
        ]
        info = Table(
            [[_p(k, st["head"]), _p(_e(v), st["cell"])] for k, v in rows],
            colWidths=[30 * mm, FRAME_W * 0.58 - 30 * mm],
        )
        info.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, -2), 0.25, RULE),
                    ("LINEABOVE", (0, 0), (-1, 0), 1, NAVY),
                    ("LINEBELOW", (0, -1), (-1, -1), 1, NAVY),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        # key result card
        if gm:
            k, res = gm
            label, col = self.status(res.fos)
            tgt = (
                f"Target FS = {o.target_fs:.2f}  ·  <b>{label}</b>"
                if o.target_fs is not None
                else "No target FS defined"
            )
            card_rows = [
                [_p("CRITICAL FACTOR OF SAFETY", st["card_label"])],
                [_p(f"FS = {res.fos:.3f}", st["card_value"])],
                [_p(_e(method_name(k)) + " (global minimum)", st["card_text"])],
                [_p(tgt, st["card_text"])],
            ]
            card_bg = col if o.target_fs is not None else NAVY
        else:
            card_rows = [[_p("NO RESULT", st["card_label"])], [_p("—", st["card_value"])]]
            card_bg = MUTED
        card = Table(card_rows, colWidths=[FRAME_W * 0.38])
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), card_bg),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (0, 0), 10),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                ]
            )
        )
        top = Table([[info, card]], colWidths=[FRAME_W * 0.6, FRAME_W * 0.4])
        top.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ]
            )
        )
        self.story += [top, Spacer(1, 9 * mm)]
        if self.figs.global_min:
            img = ImageReader(io.BytesIO(self.figs.global_min))
            iw, ih = img.getSize()
            h = min(FRAME_W * ih / iw, 92 * mm)
            w = h * iw / ih
            fig = Table(
                [[Image(io.BytesIO(self.figs.global_min), width=w, height=h)]], colWidths=[FRAME_W]
            )
            fig.setStyle(
                TableStyle(
                    [("BOX", (0, 0), (-1, -1), 0.5, RULE), ("ALIGN", (0, 0), (-1, -1), "CENTER")]
                )
            )
            self.story += [fig, _p("Critical slip surface (global minimum)", st["caption"])]
        comments = [c for c in self.p.summary.comments if c and c.strip()]
        if comments:
            self.story.append(_p("<b>Comments</b>", st["small"]))
            for c in comments:
                self.story.append(_p("• " + _e(c), st["small"]))

    def toc(self) -> None:
        toc = TableOfContents()
        toc.levelStyles = [
            ParagraphStyle(
                "toc0", fontName=F_SEMI, fontSize=10.5, leading=16, leftIndent=0, textColor=NAVY
            ),
            ParagraphStyle(
                "toc1", fontName=F_REG, fontSize=9.5, leading=13, leftIndent=14, textColor=INK
            ),
        ]
        toc.dotsMinLevel = 0
        self.story += [_p("Table of contents", self.st["toc_title"]), _Rule(), Spacer(1, 4), toc]

    # ------------------------------------------------------------ summary
    def summary(self) -> None:
        r, o = self.r, self.o
        self.h1("Summary")
        gm = r.global_minimum()
        p = self.p
        shape = "B-spline" if p.surfaces.noncircular_shape == "spline" else "polyline"
        kind = {
            "circular": "circular",
            "noncircular": f"non-circular ({shape})",
            "user": "user-defined",
        }[p.surfaces.surface_type]
        n = len(r.results)
        txt = f"This report presents the 2D limit equilibrium analysis of the <b>{_e(o.project or p.summary.title)}</b> slope. {n} method(s) were used and the critical slip surface was found by a {kind} surface search."
        if gm:
            k, res = gm
            txt += " The lowest factor of safety, <b>FS = {}</b>, was obtained with the <b>{}</b> method".format(
                f"{res.fos:.3f}", _e(method_name(k))
            )
            if o.target_fs is not None:
                label, col = self.status(res.fos)
                cmp = "above" if res.fos >= o.target_fs else "below"
                txt += "; this value is {} the target factor of safety FS = {} (<font color='{}'><b>{}</b></font>).".format(
                    cmp, f"{o.target_fs:.2f}", col.hexval(), label
                )
            else:
                txt += "."
            fs = [x.fos for x in r.results.values() if np.isfinite(x.fos)]
            if len(fs) > 1:
                txt += " Across the methods FS ranges from {} to {} (difference {}%).".format(
                    f"{min(fs):.3f}", f"{max(fs):.3f}", f"{100 * (max(fs) - min(fs)) / min(fs):.1f}"
                )
        extras = []
        if p.loads:
            extras.append(f"{len(p.loads)} external load(s)")
        nsup = len(p.supports) + sum(
            len(_pattern_xs(p, pt, r.geometry)) for pt in p.support_patterns
        )
        if nsup:
            extras.append(f"{nsup} support element(s)")
        if p.facings:
            extras.append("shotcrete + wire mesh facing")
        if p.tension_crack:
            extras.append("a tension crack")
        if p.seismic.kh or p.seismic.kv:
            extras.append("pseudo-static seismic load (kh = {})".format(f"{p.seismic.kh:g}"))
        if p.groundwater.method == "water_table" and p.water_table:
            extras.append("a water table")
        if extras:
            txt += " The model includes {}.".format(", ".join(extras))
        self.story.append(Paragraph(txt, self.st["body"]))
        self.story.append(Spacer(1, 6))
        if r.results:
            self.results_table(caption="Critical factors of safety by method")
            self.story.append(self.fs_chart())

    def results_table(self, caption: str) -> None:
        r = self.r
        gm = r.global_minimum()
        header = [
            "Method",
            "FS",
            "λ",
            "Exit x [m]",
            "Entry x [m]",
            "Centre (x; y) [m]",
            "R [m]",
            "Surfaces",
            "Status",
        ]
        rows, rc, bold = [], {}, set()
        for i, (k, res) in enumerate(r.results.items()):
            s = res.surface
            circ = hasattr(s, "r")
            lab, col = self.status(res.fos)
            rows.append(
                [
                    _e(method_name(k)),
                    f"{res.fos:.3f}",
                    _f(res.lem.lam, 3),
                    f"{res.slices.x_exit:.2f}",
                    f"{res.slices.x_entry:.2f}",
                    f"{s.xc:.2f}; {s.yc:.2f}" if circ else "—",
                    f"{s.r:.2f}" if circ else "—",
                    str(res.n_evals),
                    lab,
                ]
            )
            rc[(i, 8)] = col
            if gm and k == gm[0]:
                bold.add(i)
        for k, e in r.errors.items():
            rows.append([_e(method_name(k)), "—", "—", "—", "—", "—", "—", "—", _e(e[:40])])
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
            self.para(
                "The bold row is the global minimum. λ: interslice force scale factor (Spencer / GLE). Surfaces: number of surfaces evaluated in the search.",
                "small",
            )
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
        d.add(
            String(
                0,
                H - 12,
                "Factor of safety comparison",
                fontName=F_SEMI,
                fontSize=9,
                fillColor=NAVY,
            )
        )
        step = _nice_step(vmax / 5)
        v = 0.0
        while v <= vmax + 1e-9:
            x = left + v * sx
            d.add(Line(x, bottom, x, H - top, strokeColor=RULE, strokeWidth=0.4))
            d.add(
                String(
                    x,
                    bottom - 11,
                    f"{v:g}",
                    fontName=F_REG,
                    fontSize=7.5,
                    fillColor=MUTED,
                    textAnchor="middle",
                )
            )
            v += step
        d.add(
            String(
                left + (W - left - right) / 2,
                2,
                "FS",
                fontName=F_SEMI,
                fontSize=8,
                fillColor=MUTED,
                textAnchor="middle",
            )
        )
        gm = self.r.global_minimum()
        for i, (k, f) in enumerate(res):
            y = H - top - (i + 1) * (bar_h + gap) + gap / 2
            _, col = self.status(f)
            if tgt is None:
                col = NAVY
            d.add(Rect(left, y, f * sx, bar_h, fillColor=col, strokeColor=None))
            if gm and k == gm[0]:
                d.add(
                    Rect(left, y, f * sx, bar_h, fillColor=None, strokeColor=INK, strokeWidth=1.1)
                )
            d.add(
                String(
                    left - 6,
                    y + 3.5,
                    method_name(k),
                    fontName=F_REG,
                    fontSize=8.5,
                    fillColor=INK,
                    textAnchor="end",
                )
            )
            d.add(
                String(
                    left + f * sx + 4,
                    y + 3.5,
                    f"{f:.3f}",
                    fontName=F_SEMI,
                    fontSize=8.5,
                    fillColor=INK,
                )
            )
        if tgt:
            x = left + tgt * sx
            d.add(
                Line(
                    x,
                    bottom - 2,
                    x,
                    H - top + 4,
                    strokeColor=BAD,
                    strokeWidth=1.1,
                    strokeDashArray=[4, 2],
                )
            )
            d.add(
                String(
                    x + 3,
                    H - top + 2,
                    f"Target FS = {tgt:.2f}",
                    fontName=F_SEMI,
                    fontSize=7.5,
                    fillColor=BAD,
                )
            )
        return d

    # -------------------------------------------------------------- model
    def model(self) -> None:
        p, o = self.p, self.o
        self.h1("Model and Geometry")
        g = self.r.geometry
        self.para(
            f"The model consists of {len(g.regions)} region(s) and {len(p.materials)} material(s). The external boundary has {len(p.external)} vertices; the model spans x = {g.x_min:.2f} – {g.x_max:.2f} m."
            + (" " + "A water table is defined." if p.water_table else "")
            + (" " + "A tension crack boundary is defined." if p.tension_crack else "")
        )
        self.story.append(Spacer(1, 4))
        self.figure(self.figs.model, "Analysis model: geometry, materials, loads and supports")
        if o.materials:
            self.h2("Material properties")
            mc = [m for m in p.materials if m.model == "MC"]
            hb = [m for m in p.materials if m.model == "HB"]
            if mc:
                rows, sw = [], {}
                for i, m in enumerate(mc):
                    sw[i] = m.color
                    rows.append(
                        [
                            "",
                            _e(m.name),
                            "Mohr-Coulomb",
                            _g(m.gamma),
                            _g(m.gamma_sat) if m.use_sat else "—",
                            _g(m.c),
                            _g(m.phi),
                            _water(m),
                        ]
                    )
                self.table(
                    [
                        "",
                        "Material",
                        "Model",
                        "γ [kN/m³]",
                        "γ<sub>sat</sub> [kN/m³]",
                        "c' [kPa]",
                        "φ' [°]",
                        "Water",
                    ],
                    rows,
                    [0.04, 0.22, 0.15, 0.1, 0.12, 0.1, 0.09, 0.18],
                    "Material parameters (Mohr-Coulomb)",
                    ["c", "l", "l", "r", "r", "r", "r", "l"],
                    swatches=sw,
                )
            if hb:
                rows, sw = [], {}
                for i, m in enumerate(hb):
                    sw[i] = m.color
                    rows.append(
                        [
                            "",
                            _e(m.name),
                            _g(m.gamma),
                            _g(m.gamma_sat) if m.use_sat else "—",
                            _g(m.sigma_ci),
                            _g(m.gsi),
                            _g(m.mi),
                            _g(m.d),
                            _water(m),
                        ]
                    )
                self.table(
                    [
                        "",
                        "Material",
                        "γ [kN/m³]",
                        "γ<sub>sat</sub>",
                        "σ<sub>ci</sub> [kPa]",
                        "GSI",
                        "m<sub>i</sub>",
                        "D",
                        "Water",
                    ],
                    rows,
                    [0.04, 0.2, 0.1, 0.09, 0.12, 0.08, 0.08, 0.07, 0.22],
                    "Material parameters (generalized Hoek-Brown)",
                    ["c", "l", "r", "r", "r", "r", "r", "r", "l"],
                    swatches=sw,
                )

            extra = [m for m in p.materials if m.model not in ("MC", "HB")]
            if extra:
                from slipsurface.materials.catalog import model_name, parameter_text

                rows, sw = [], {}
                for i, m in enumerate(extra):
                    sw[i] = m.color
                    rows.append(
                        [
                            "",
                            _e(m.name),
                            _e(model_name(m.model)),
                            _g(m.gamma),
                            _g(m.gamma_sat) if m.use_sat else "—",
                            _e(parameter_text(m)),
                            _water(m),
                        ]
                    )
                self.table(
                    [
                        "",
                        "Material",
                        "Model",
                        "γ [kN/m³]",
                        "γ<sub>sat</sub>",
                        "Strength parameters",
                        "Water",
                    ],
                    rows,
                    [0.04, 0.16, 0.16, 0.09, 0.08, 0.33, 0.14],
                    "Material parameters (other strength models)",
                    ["c", "l", "l", "r", "r", "l", "l"],
                    swatches=sw,
                )

    # ----------------------------------------------------------- settings
    def settings(self) -> None:
        p = self.p
        self.h1("Analysis Settings")
        gw = p.groundwater
        gwt = {
            "water_table": "Water table",
            "ru": f"Ru coefficient (Ru = {gw.ru:g})",
            "none": "None (dry)",
        }.get(gw.method, gw.method)
        s = p.surfaces
        lim = []
        if s.left_range:
            lim.append(f"left end x = {s.left_range[0]:.2f} – {s.left_range[1]:.2f}")
        if s.right_range:
            lim.append(f"right end x = {s.right_range[0]:.2f} – {s.right_range[1]:.2f}")
        from slipsurface.project import EFFORT

        pop, it = EFFORT.get(s.effort, EFFORT["normal"])
        shape = (
            "B-spline, {} control points"
            if s.noncircular_shape == "spline"
            else "polyline, {} interior vertices"
        ).format(s.n_ctrl)
        surf_txt = {
            "circular": "Circular",
            "noncircular": f"Non-circular ({shape}"
            + (", " + "convex" if s.convex_only else "")
            + ")",
            "user": "User-defined surface",
        }[s.surface_type]
        inter = {
            "half-sine": "half-sine",
            "constant": "constant",
            "clipped-sine": "clipped sine",
            "trapezoidal": "trapezoidal",
        }.get(p.methods.interslice, p.methods.interslice)
        rows = [
            ("Methods", ", ".join(_e(method_name(k)) for k in p.methods.methods)),
            ("Units", "Metric — kN, kPa, m"),
            (
                "Failure Direction",
                "Right to left"
                if p.general.failure_direction == "right_to_left"
                else "Left to right",
            ),
            ("Number of slices", str(p.methods.n_slices)),
            ("Tolerance / max. iterations", f"{p.methods.tolerance:g} / {p.methods.max_iter}"),
            ("GLE interslice function", inter),
            ("Slip surface", surf_txt),
            (
                "Search",
                f"Differential evolution + Nelder-Mead (population {pop}, at most {it} generations, seed {s.seed})",
            ),
            ("Slope limits", "; ".join(x for x in lim) if lim else "Whole model"),
            ("Minimum sliding mass depth", f"{p.advanced.min_depth:g} m"),
            (
                "Admissibility check",
                "On (mα &lt; 0.2 and negative base shear resistance are rejected)"
                if p.advanced.check_admissibility
                else "Off",
            ),
            ("Pore Water Pressure", gwt + f", γ<sub>w</sub> = {gw.gamma_w:g} kN/m³"),
            ("Seismic coefficients", p.seismic.clause()),
        ]
        critical_kv = governing_kv_lines(p, self.r.results)
        if critical_kv:
            rows.append(("Critical vertical", "\n".join(critical_kv)))
        if p.tension_crack:
            rows.append(("Tension crack", f"Crack water {100 * gw.crack_water:.0f}% full"))
        self.kv_table(rows, "Analysis and search parameters")

    # ------------------------------------------------- loads and supports
    def loads(self) -> None:
        p = self.p
        has = p.loads or p.supports or p.support_patterns or p.facings or p.tension_crack
        if not has:
            return
        self.h1("Loads, Supports and Facing")
        if p.loads:
            self.h2("External loads")
            rows = []
            for i, ld in enumerate(p.loads, 1):
                if ld["kind"] == "distributed":
                    (x1, _), (x2, _) = ld["points"]
                    yon = (
                        "vertical"
                        if ld.get("orientation", "vertical") == "vertical"
                        else "normal to surface"
                    )
                    q = ld["q"]
                    rows.append(
                        [
                            str(i),
                            "Distributed",
                            f"x = {min(x1, x2):.2f} – {max(x1, x2):.2f}",
                            f"{q[0]:g}" + (f" – {q[1]:g}" if q[1] != q[0] else "") + " kPa",
                            yon,
                        ]
                    )
                else:
                    x, y = ld["point"]
                    rows.append(
                        [
                            str(i),
                            "Line",
                            f"({x:.2f}; {y:.2f})",
                            f"{ld['magnitude']:g} kN/m",
                            f"{ld.get('angle', 270):g}°",
                        ]
                    )
            self.table(
                ["No", "Type", "Location [m]", "Quantity", "Direction / angle"],
                rows,
                [0.07, 0.13, 0.32, 0.25, 0.23],
                "External loads",
                ["c", "l", "l", "r", "l"],
            )
        if p.supports or p.support_patterns:
            from slipsurface.loads import SUPPORT_KINDS

            self.h2("Support elements")
            used = {sp["type"] for sp in p.supports + p.support_patterns}
            rows, sw = [], {}
            for i, t in enumerate([t for t in p.support_types if t.name in used]):
                sw[i] = t.color
                kind = t.kind
                bond = (
                    f"{t.bond_strength:g}"
                    if kind in ("grouted_tieback", "soil_nail")
                    else (
                        f"{t.pullout:g}"
                        if kind == "geotextile"
                        else (
                            f"a={t.adhesion:g}, δ={t.interface_friction:g}°"
                            if kind == "geosynthetic"
                            else "—"
                        )
                    )
                )
                strength = (
                    _g(t.pile_shear) + " " + "(shear)"
                    if kind == "micro_pile"
                    else _g(t.tensile)
                    + (f" ×{t.coverage:g}%" if kind == "geosynthetic" and t.coverage != 100 else "")
                )
                rows.append(
                    [
                        "",
                        _e(t.name),
                        SUPPORT_KINDS[kind],
                        _g(t.spacing) if kind not in ("geotextile", "geosynthetic") else "—",
                        strength,
                        _g(t.plate) if kind == "soil_nail" else "—",
                        bond,
                        _g(t.bond_length) if kind == "grouted_tieback" else "—",
                        "passive" if t.application == "passive" else "active",
                        {
                            "parallel": "parallel",
                            "tangent": "tangent",
                            "perpendicular": "perpendicular",
                        }.get(t.orientation, t.orientation),
                    ]
                )
            self.table(
                [
                    "",
                    "Name",
                    "Type",
                    "Spacing [m]",
                    "Capacity [kN]",
                    "Plate [kN]",
                    "Bond [kN/m]",
                    "Bond length [m]",
                    "Application",
                    "Orientation",
                ],
                rows,
                [0.035, 0.14, 0.2, 0.08, 0.09, 0.08, 0.09, 0.09, 0.09, 0.095],
                "Support types",
                ["c", "l", "l", "r", "r", "r", "r", "r", "c", "c"],
                swatches=sw,
            )
            if p.supports:
                rows = []
                for i, sp in enumerate(p.supports, 1):
                    a, b = np.array(sp["a"], float), np.array(sp["b"], float)
                    d = b - a
                    L = float(np.hypot(*d))
                    ang = float(np.degrees(np.arctan2(-d[1], abs(d[0]))))
                    rows.append(
                        [
                            str(i),
                            _e(sp["type"]),
                            f"({a[0]:.2f}; {a[1]:.2f})",
                            f"({b[0]:.2f}; {b[1]:.2f})",
                            f"{L:.2f}",
                            f"{ang:.1f}",
                        ]
                    )
                self.table(
                    [
                        "No",
                        "Type",
                        "Head A (x; y) [m]",
                        "End B (x; y) [m]",
                        "Length [m]",
                        "Inclination [°]",
                    ],
                    rows,
                    [0.07, 0.23, 0.22, 0.22, 0.12, 0.14],
                    "Individual supports",
                    ["c", "l", "r", "r", "r", "r"],
                )
            if p.support_patterns:
                rows = []
                for i, pt in enumerate(p.support_patterns, 1):
                    n = len(_pattern_xs(p, pt, self.r.geometry))
                    rows.append(
                        [
                            str(i),
                            _e(pt["type"]),
                            f"{pt['p1'][0]:.2f} – {pt['p2'][0]:.2f}",
                            f"{pt['spacing']:g}",
                            f"{pt.get('offset', 0):g}",
                            f"{pt.get('angle', 15):g}",
                            f"{pt['length']:g}",
                            str(n),
                        ]
                    )
                self.table(
                    [
                        "No",
                        "Type",
                        "x range [m]",
                        "Spacing [m]",
                        "First [m]",
                        "Inclination [°]",
                        "Length [m]",
                        "Count",
                    ],
                    rows,
                    [0.07, 0.23, 0.18, 0.1, 0.1, 0.1, 0.1, 0.12],
                    "Bolt / anchor patterns (equally spaced along the slope face)",
                    ["c", "l", "r", "r", "r", "r", "r", "r"],
                )
        if p.facings:
            self.h2("Facing (shotcrete + wire mesh)")
            used = {f["type"] for f in p.facings}
            rows, sw = [], {}
            for i, t in enumerate([t for t in p.facing_types if t.name in used]):
                sw[i] = t.color
                rows.append(
                    [
                        "",
                        _e(t.name),
                        f"{100 * t.thickness:g}",
                        _g(t.gamma),
                        _g(t.tau),
                        f"{_e(t.mesh)} ({t.mesh_as:g})",
                        _g(t.mesh_fy),
                        f"{t.capacity:.1f}",
                        "passive" if t.application == "passive" else "active",
                    ]
                )
            self.table(
                [
                    "",
                    "Name",
                    "t [cm]",
                    "γ [kN/m³]",
                    "τ [kPa]",
                    "Mesh (A<sub>s</sub> [mm²/m])",
                    "f<sub>y</sub> [MPa]",
                    "T [kN/m]",
                    "Application",
                ],
                rows,
                [0.035, 0.24, 0.07, 0.09, 0.08, 0.16, 0.09, 0.1, 0.105],
                "Facing types",
                ["c", "l", "r", "r", "r", "l", "r", "r", "c"],
                swatches=sw,
            )
            rows = [
                [
                    str(i),
                    _e(f["type"]),
                    f"{min(f['x1'], f['x2']):.2f}",
                    f"{max(f['x1'], f['x2']):.2f}",
                ]
                for i, f in enumerate(p.facings, 1)
            ]
            self.table(
                ["No", "Facing type", "x<sub>1</sub> [m]", "x<sub>2</sub> [m]"],
                rows,
                [0.08, 0.52, 0.2, 0.2],
                "Facing assignments",
                ["c", "l", "r", "r"],
            )
            self.para(
                "Facing capacity T = τ·t + A<sub>s</sub>·f<sub>y</sub>; applied tangent to the slip surface, against sliding, where the slip surface exits/enters through the faced surface. The facing weight γ·t is added as a surface load.",
                "small",
            )
        if p.tension_crack:
            self.h2("Tension crack")
            xs = [q[0] for q in p.tension_crack]
            self.para(
                f"The tension crack boundary is defined between x = {min(xs):.2f} – {max(xs):.2f} m; the crack is {100 * p.groundwater.crack_water:.0f}% full of water. The water thrust V = ½·γ<sub>w</sub>·h<sub>w</sub>² acts in the failure direction at h<sub>w</sub>/3 height."
            )

    # ------------------------------------------------------------ results
    def results(self) -> None:
        r, o = self.r, self.o
        self.h1("Analysis Results")
        gm = r.global_minimum()
        if not r.results:
            self.para("No method produced a valid solution.")
            return
        self.results_table(caption="Critical slip surfaces and factors of safety")
        if o.global_figure and gm:
            self.h2("Critical slip surface (global minimum)")
            k, res = gm
            self.figure(
                self.figs.global_min,
                f"{method_name(k)} — FS = {res.fos:.3f}; "
                + "slip centre FS contours and critical surface",
                max_h=125 * mm,
            )
        if o.method_figures and len(self.figs.methods) > 0:
            self.h2("Critical surfaces by method")
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
                    rows.append(
                        [
                            _e(method_name(k)),
                            _e(f.label),
                            f"{f.x:.2f}",
                            f"{f.y:.2f}",
                            f"{f.T:.1f}",
                            f"{f.mobilized(res.fos):.1f}",
                            _f(f.L_in),
                            _f(f.L_out),
                            _e(f.governing),
                            "passive" if f.passive else "active",
                        ]
                    )
            if rows:
                self.h2("Mobilised support forces")
                self.table(
                    [
                        "Method",
                        "Element",
                        "x [m]",
                        "y [m]",
                        "T<sub>cap</sub> [kN/m]",
                        "T<sub>mob</sub> [kN/m]",
                        "L<sub>in</sub> [m]",
                        "L<sub>out</sub> [m]",
                        "Governing",
                        "Appl.",
                    ],
                    rows,
                    [0.16, 0.12, 0.07, 0.07, 0.10, 0.10, 0.07, 0.07, 0.16, 0.08],
                    "Forces of the supports and facings crossing the critical surfaces",
                    ["l", "l", "r", "r", "r", "r", "r", "r", "l", "c"],
                )
                self.para(
                    "Tcap: capacity per unit width (kN/m). Tmob: mobilised force at equilibrium; Tcap/F for passive elements, Tcap for active elements.",
                    "small",
                )
        if self.p.tension_crack:
            rows = []
            for k, res in r.results.items():
                ck = res.slices.crack
                if ck is None:
                    rows.append([_e(method_name(k)), "—", "—", "—", "—"])
                else:
                    rows.append(
                        [
                            _e(method_name(k)),
                            f"{ck['x']:.2f}",
                            f"{ck['depth']:.2f}",
                            f"{ck['hw']:.2f}",
                            f"{ck['Pw']:.2f}",
                        ]
                    )
            self.h2("Tension crack on the critical surfaces")
            self.table(
                ["Method", "x [m]", "Depth [m]", "h<sub>w</sub> [m]", "V [kN/m]"],
                rows,
                [0.36, 0.16, 0.16, 0.16, 0.16],
                "Tension crack and crack water thrust",
                ["l", "r", "r", "r", "r"],
            )

    # --------------------------------------------------------- appendices
    def slice_table(self, letter: str) -> None:
        gm = self.r.global_minimum()
        if not gm:
            return
        k, res = gm
        s = res.slices
        self.appendix(letter, f"Slice Data — {method_name(k)}")
        self.para(
            f"Data of the {s.n} slices of the global minimum slip surface ({method_name(k)}, FS = {res.fos:.3f}). α: base angle (positive in the failure direction), c, φ: strength used on the base (instantaneous values at σ<sub>n</sub>' ≈ W/b − u for non-linear models).",
            "small",
            keep_next=True,
        )
        rows = []
        for i in range(s.n):
            mat = s.materials[s.mat_idx[i]]
            c, tp = (np.array([v]) for v in slice_strength(s, i))
            rows.append(
                [
                    str(i + 1),
                    f"{0.5 * (s.xl[i] + s.xr[i]):.2f}",
                    f"{s.b[i]:.3f}",
                    f"{s.y_base[i]:.2f}",
                    f"{s.y_top[i] - s.y_base[i]:.2f}",
                    f"{np.degrees(s.alpha[i]) * (-s.direction):.1f}",
                    f"{s.l[i]:.3f}",
                    f"{s.W[i]:.2f}",
                    f"{s.u[i]:.2f}",
                    f"{c[0]:.2f}",
                    f"{np.degrees(np.arctan(tp[0])):.1f}",
                    _e(mat.name),
                ]
            )
        self.table(
            [
                "No",
                "x<sub>mid</sub> [m]",
                "b [m]",
                "y<sub>base</sub> [m]",
                "h [m]",
                "α [°]",
                "l [m]",
                "W [kN/m]",
                "u [kPa]",
                "c [kPa]",
                "φ [°]",
                "Material",
            ],
            rows,
            [0.05, 0.08, 0.07, 0.08, 0.07, 0.07, 0.07, 0.09, 0.08, 0.08, 0.07, 0.19],
            f"Slice data ({method_name(k)})",
            ["c", "r", "r", "r", "r", "r", "r", "r", "r", "r", "r", "l"],
            compact=True,
        )

    def coordinates(self, letter: str) -> None:
        p = self.p
        self.appendix(letter, "Coordinates")

        def block(title, pts):
            rows = [[str(i), f"{q[0]:.3f}", f"{q[1]:.3f}"] for i, q in enumerate(pts, 1)]
            # three side-by-side columns to save space
            self.table(["No", "x [m]", "y [m]"], rows, [0.1, 0.2, 0.2], title, ["c", "r", "r"])

        block("External boundary", p.external)
        for i, b in enumerate(p.material_boundaries, 1):
            block(f"Material boundary {i}", b)
        if p.water_table:
            block("Water table", p.water_table)
        if p.tension_crack:
            block("Tension crack boundary", p.tension_crack)
        gm = self.r.global_minimum()
        if gm:
            k, res = gm
            s = res.surface
            if hasattr(s, "r"):
                self.kv_table(
                    [
                        ("Centre", f"({s.xc:.3f}; {s.yc:.3f}) m"),
                        ("Radius", f"{s.r:.3f} m"),
                        (
                            "Exit / entry x",
                            f"{res.slices.x_exit:.3f} / {res.slices.x_entry:.3f} m",
                        ),
                    ],
                    f"Critical circle ({method_name(k)})",
                )
            else:
                pts = s.points(res.slices.x_exit, res.slices.x_entry, 25)
                block(f"Critical surface points ({method_name(k)})", pts)

    def closing(self) -> None:
        self.story.append(Spacer(1, 10))
        self.para(
            f"This report was generated automatically with SlipSurfaceIQ LE {__version__}. The results rely on the geometry, material and loading data entered; evaluating and verifying them with engineering judgement is the responsibility of the user.",
            "small",
        )

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
        doc = _Doc(
            path,
            o,
            self.st,
            title=o.title,
            author=o.author,
            subject=o.project,
            creator=f"SlipSurfaceIQ LE {__version__}",
        )
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
        return "No water"
    return "Water Table" + (f", H<sub>u</sub> = {m.hu:g}" if m.hu != 1 else "")


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
        log.warning("Bolt pattern could not be drawn in the report: %s", pt, exc_info=True)
        return []


# ================================================================ public
def build_pdf(
    results, path, opts: ReportOptions | None = None, figs: ReportFigures | None = None
) -> int:
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
        opts.date = _dt.date.today().strftime("%Y-%m-%d")
    b = _Builder(results, opts, figs)
    return b.build(Path(path))
