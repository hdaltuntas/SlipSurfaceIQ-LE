"""Shared look of the SlipSurfaceIQ LE PDF guides (maintainers only).

Used by scripts/build_scripting_tutorial.py and scripts/build_dxf_guide.py:
fonts, colours, numbered chapters with a table of contents, code panels,
call-outs, tables, the gradient cover and the page frame.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402

from slipsurface import __version__  # noqa: E402

FONT_DIR = ROOT / "slipsurface" / "report" / "fonts"

# ----------------------------------------------------------------- palette
INK = colors.HexColor("#1b2433")
MUTED = colors.HexColor("#5b6678")
ACCENT = colors.HexColor("#2f6fed")
ACCENT_SOFT = colors.HexColor("#e8f0fe")
TEAL = colors.HexColor("#0f9d8a")
TEAL_SOFT = colors.HexColor("#e3f6f3")
AMBER = colors.HexColor("#c27c0e")
AMBER_SOFT = colors.HexColor("#fdf3e1")
CODE_BG = colors.HexColor("#1e2533")
CODE_FG = colors.HexColor("#e6ebf3")
RULE = colors.HexColor("#d9dee7")
ROW_ALT = colors.HexColor("#f5f7fb")
NAVY = colors.HexColor("#14213d")


def _fonts() -> tuple[str, str, str, str]:
    pdfmetrics.registerFont(TTFont("Sans", str(FONT_DIR / "SourceSans3-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Sans-Bold", str(FONT_DIR / "SourceSans3-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Sans-Semi", str(FONT_DIR / "SourceSans3-SemiBold.ttf")))
    pdfmetrics.registerFont(TTFont("Sans-It", str(FONT_DIR / "SourceSans3-Italic.ttf")))
    pdfmetrics.registerFontFamily(
        "Sans", normal="Sans", bold="Sans-Bold", italic="Sans-It", boldItalic="Sans-Bold"
    )
    mono = "Courier"
    for candidate in (
        "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ):
        if Path(candidate).is_file():
            pdfmetrics.registerFont(TTFont("Mono", candidate))
            mono = "Mono"
            break
    return "Sans", "Sans-Bold", "Sans-Semi", mono


SANS, BOLD, SEMI, MONO = _fonts()

STYLES = {
    "body": ParagraphStyle(
        "body", fontName=SANS, fontSize=10.2, leading=14.6, textColor=INK, spaceAfter=6
    ),
    "h1": ParagraphStyle(
        "h1", fontName=BOLD, fontSize=21, leading=25, textColor=NAVY, spaceBefore=4, spaceAfter=4
    ),
    "h2": ParagraphStyle(
        "h2",
        fontName=SEMI,
        fontSize=13.5,
        leading=17,
        textColor=ACCENT,
        spaceBefore=12,
        spaceAfter=4,
        keepWithNext=1,
    ),
    "lead": ParagraphStyle(
        "lead", fontName=SANS, fontSize=11.5, leading=16, textColor=MUTED, spaceAfter=10
    ),
    "cell": ParagraphStyle("cell", fontName=SANS, fontSize=8.8, leading=11.2, textColor=INK),
    "cellcode": ParagraphStyle(
        "cellcode", fontName=MONO, fontSize=8.2, leading=10.6, textColor=NAVY
    ),
    "head": ParagraphStyle("head", fontName=SEMI, fontSize=8.8, leading=11, textColor=colors.white),
    "code": ParagraphStyle(
        "code", fontName=MONO, fontSize=8.4, leading=11.4, textColor=CODE_FG, alignment=TA_LEFT
    ),
    "toc1": ParagraphStyle(
        "toc1", fontName=SANS, fontSize=11, leading=17, textColor=INK, leftIndent=0
    ),
    "callout": ParagraphStyle("callout", fontName=SANS, fontSize=9.6, leading=13.4, textColor=INK),
}

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# ------------------------------------------------------------- flowables
class SectionTitle(Flowable):
    """Numbered chapter heading with an accent bar; registers a TOC entry."""

    def __init__(self, number: int, title: str, lead: str = ""):
        super().__init__()
        self.number, self.title, self.lead = number, title, lead
        self._lead = Paragraph(lead, STYLES["lead"]) if lead else None

    def wrap(self, aw, ah):
        self.width = aw
        h = 40
        if self._lead is not None:
            _, lh = self._lead.wrap(aw, ah)
            h += lh + 4
        self.height = h
        return aw, h

    def draw(self):
        c = self.canv
        top = self.height
        c.setFillColor(ACCENT)
        c.roundRect(0, top - 34, 34, 30, 6, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(BOLD, 15)
        c.drawCentredString(17, top - 24.5, f"{self.number:02d}")
        c.setFillColor(NAVY)
        c.setFont(BOLD, 19)
        c.drawString(46, top - 26, self.title)
        if self._lead is not None:
            self._lead.drawOn(c, 0, 0)


class CodeBlock(Flowable):
    """Dark, rounded code panel with line numbers."""

    def __init__(self, source: str, title: str = "", first: int = 1):
        super().__init__()
        self.lines = source.rstrip("\n").split("\n")
        self.title = title
        self.first = first
        self.leading = 11.4
        self.pad = 9
        self.spaceAfter = 10

    def wrap(self, aw, ah):
        self.width = aw
        for line in self.lines:
            if pdfmetrics.stringWidth(line, MONO, 8.4) > aw - 44:
                raise SystemExit(f"{self.title}: code line too wide for the page: {line!r}")
        bar = 18 if self.title else 0
        self.height = len(self.lines) * self.leading + 2 * self.pad + bar
        return aw, self.height

    def split(self, aw, ah):
        bar = 18 if self.title else 0
        fit = int((ah - 2 * self.pad - bar) // self.leading)
        if fit >= len(self.lines) or fit < 4:
            return []
        first = CodeBlock("\n".join(self.lines[:fit]), self.title, self.first)
        rest = CodeBlock(
            "\n".join(self.lines[fit:]),
            (self.title + " (continued)") if self.title else "",
            self.first + fit,
        )
        return [first, rest]

    def draw(self):
        c = self.canv
        c.setFillColor(CODE_BG)
        c.roundRect(0, 0, self.width, self.height, 7, fill=1, stroke=0)
        y = self.height - self.pad
        if self.title:
            c.setFillColor(colors.HexColor("#2a3346"))
            c.roundRect(0, self.height - 20, self.width, 20, 7, fill=1, stroke=0)
            c.rect(0, self.height - 20, self.width, 8, fill=1, stroke=0)
            for i, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
                c.setFillColor(colors.HexColor(col))
                c.circle(12 + i * 11, self.height - 10, 3.2, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#aab4c5"))
            c.setFont(SANS, 8.5)
            c.drawString(52, self.height - 13, self.title)
            y -= 18
        c.setFont(MONO, 8.4)
        for i, line in enumerate(self.lines, self.first):
            y -= self.leading
            c.setFillColor(colors.HexColor("#5d6a80"))
            c.drawRightString(24, y + 3, str(i))
            stripped = line.lstrip()
            c.setFillColor(colors.HexColor("#7f8ea6") if stripped.startswith("#") else CODE_FG)
            c.drawString(32, y + 3, line)


def callout(kind: str, title: str, text: str) -> Table:
    fg, bg = {"tip": (TEAL, TEAL_SOFT), "note": (ACCENT, ACCENT_SOFT), "warn": (AMBER, AMBER_SOFT)}[
        kind
    ]
    body = Paragraph(
        f'<font name="{SEMI}" color="{fg.hexval()}">{title}</font><br/>{text}', STYLES["callout"]
    )
    t = Table([[body]], colWidths=[CONTENT_W])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LINEBEFORE", (0, 0), (0, -1), 3.5, fg),
                ("LEFTPADDING", (0, 0), (-1, -1), 11),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return t


def table(header: list[str], rows: list[list], widths: list[float], code_cols=(0,)) -> Table:
    data = [[Paragraph(h, STYLES["head"]) for h in header]]
    for row in rows:
        data.append(
            [
                Paragraph(_esc(str(v)), STYLES["cellcode" if i in code_cols else "cell"])
                for i, v in enumerate(row)
            ]
        )
    total = sum(widths)
    t = Table(data, colWidths=[CONTENT_W * w / total for w in widths], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
    ]
    for r in range(1, len(data)):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), ROW_ALT))
    t.setStyle(TableStyle(style))
    return t


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def P(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text, STYLES[style])


def code(text: str) -> str:
    return f'<font name="{MONO}" size="9" color="#14213d">{_esc(text)}</font>'


# --------------------------------------------------------------- document
class GuideDoc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        title = getattr(flowable, "_toc", None)
        if title:
            key = f"sec-{id(flowable)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=0)
            self.notify("TOCEntry", (0, title, self.page, key))


def _cover(canv, doc):
    meta = doc.meta
    canv.saveState()
    steps = 60
    for i in range(steps):  # vertical gradient
        t = i / (steps - 1)
        r = 0x14 + (0x2F - 0x14) * t
        g = 0x21 + (0x6F - 0x21) * t
        b = 0x3D + (0xED - 0x3D) * t
        canv.setFillColorRGB(r / 255, g / 255, b / 255)
        h = PAGE_H / steps
        canv.rect(0, PAGE_H - (i + 1) * h, PAGE_W, h + 1, fill=1, stroke=0)
    # decorative slope silhouette
    canv.setFillColor(colors.Color(1, 1, 1, alpha=0.08))
    path = canv.beginPath()
    path.moveTo(0, 0)
    path.lineTo(0, 210)
    path.lineTo(PAGE_W * 0.38, 210)
    path.lineTo(PAGE_W * 0.70, 360)
    path.lineTo(PAGE_W, 360)
    path.lineTo(PAGE_W, 0)
    path.close()
    canv.drawPath(path, fill=1, stroke=0)
    canv.setStrokeColor(colors.Color(1, 1, 1, alpha=0.35))
    canv.setLineWidth(1.6)
    canv.setDash(6, 4)
    canv.arc(PAGE_W * 0.22, 60, PAGE_W * 0.86, 560, startAng=270, extent=72)
    canv.setDash()
    canv.setFillColor(colors.white)
    canv.setFont(SEMI, 13)
    canv.drawString(MARGIN, PAGE_H - 40 * mm, "SlipSurfaceIQ LE")
    canv.setFont(BOLD, 40)
    for k, line in enumerate(meta["title_lines"]):
        canv.drawString(MARGIN, PAGE_H - (70 + 16 * k) * mm, line)
    canv.setFont(SANS, 14)
    canv.setFillColor(colors.HexColor("#d6e2ff"))
    canv.drawString(MARGIN, PAGE_H - 100 * mm, meta["subtitle"])
    canv.setFillColor(colors.white)
    canv.roundRect(MARGIN, PAGE_H - 122 * mm, 44 * mm, 10 * mm, 5 * mm, fill=1, stroke=0)
    canv.setFillColor(NAVY)
    canv.setFont(SEMI, 11)
    canv.drawCentredString(MARGIN + 22 * mm, PAGE_H - 118.6 * mm, f"Version {__version__}")
    canv.restoreState()


def _page(canv, doc):
    canv.saveState()
    canv.setFillColor(ACCENT)
    canv.rect(0, PAGE_H - 6, PAGE_W, 6, fill=1, stroke=0)
    canv.setFont(SEMI, 8.5)
    canv.setFillColor(MUTED)
    canv.drawString(MARGIN, PAGE_H - 13 * mm, f"SlipSurfaceIQ LE  ·  {doc.meta['name']}")
    canv.drawRightString(PAGE_W - MARGIN, PAGE_H - 13 * mm, f"Version {__version__}")
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.6)
    canv.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
    canv.setFont(SANS, 8.5)
    canv.drawRightString(PAGE_W - MARGIN, 9 * mm, str(doc.page))
    canv.restoreState()


def front_matter() -> list:
    """Cover page break and the table of contents."""
    toc = TableOfContents()
    toc.levelStyles = [STYLES["toc1"]]
    toc.dotsMinLevel = 0
    return [
        NextPageTemplate("body"),
        PageBreak(),
        P("Contents", "h1"),
        Spacer(1, 8),
        toc,
        PageBreak(),
    ]


class Chapters:
    """Appends numbered chapters (with TOC entries) and sub-headings to a story."""

    def __init__(self, story: list):
        self.story = story
        self.n = 0

    def chapter(self, title: str, lead: str = "") -> None:
        self.n += 1
        self.story.append(CondPageBreak(120 * mm))
        flow = SectionTitle(self.n, title, lead)
        flow._toc = f"{self.n:02d}  {title}"
        self.story.append(flow)
        self.story.append(Spacer(1, 6))

    def h2(self, text: str) -> None:
        self.story.append(P(text, "h2"))


def write(
    path: Path,
    story: list,
    name: str,
    title_lines: list[str],
    subtitle: str,
    check: Callable[[], None] | None = None,
) -> Path:
    """Lay out the story behind a cover and write the PDF."""
    if check is not None:
        check()
    doc = GuideDoc(
        str(path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=22 * mm,
        bottomMargin=20 * mm,
        title=f"SlipSurfaceIQ LE — {name}",
        author="SlipSurfaceIQ LE",
        subject=f"{name}, version {__version__}",
    )
    doc.meta = {"name": name, "title_lines": title_lines, "subtitle": subtitle}
    frame = Frame(MARGIN, 20 * mm, CONTENT_W, PAGE_H - 42 * mm, id="body")
    doc.addPageTemplates(
        [
            PageTemplate("cover", [Frame(0, 0, PAGE_W, PAGE_H, id="cover")], onPage=_cover),
            PageTemplate("body", [frame], onPage=_page),
        ]
    )
    doc.multiBuild([Spacer(1, 1), *front_matter(), *story])
    return path
