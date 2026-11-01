"""Annotation (note) tools shared by the Modeler and Interpret windows:
text, line, arrow, rectangle, ellipse."""

from __future__ import annotations

import copy

from slipsurface.ui.dialogs.facing_pattern_annot import AnnotationDialog

ANNOT_TOOLS = [  # (draw kind, label, icon)
    ("annot_text", "Add Text", "annot_text"),
    ("annot_line", "Add Line", "annot_line"),
    ("annot_arrow", "Add Arrow", "annot_arrow"),
    ("annot_rect", "Add Rectangle", "annot_rect"),
    ("annot_ellipse", "Add Ellipse", "annot_ellipse"),
]


def new_annotation(draw_kind: str, pts: list, parent=None) -> dict | None:
    """Annotation dict for points drawn with a DrawTool annot_* kind; a text
    asks for its content first (None if cancelled or empty)."""
    kind = draw_kind.removeprefix("annot_")
    ann = {
        "kind": kind,
        "pts": [list(map(float, q)) for q in pts],
        "color": "#c0392b",
        "width": 1.5,
        "fill": None,
        "text": "",
        "size": 10,
        "bold": False,
        "box": True,
    }
    if kind == "text":
        ann["color"] = "#1b2a3a"
        dlg = AnnotationDialog(ann, parent)
        if not dlg.exec():
            return None
        dlg.apply_to(ann)
        if not ann["text"].strip():
            return None
    return ann


def edit_annotation(doc, i: int, parent=None) -> None:
    ann = copy.deepcopy(doc.project.annotations[i])
    dlg = AnnotationDialog(ann, parent)
    if dlg.exec():
        dlg.apply_to(ann)
        doc.edit("Edit note", lambda p: p.annotations.__setitem__(i, ann))
