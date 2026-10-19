"""Document: the project being edited, with undo/redo.

Every edit goes through `Document.edit(text, fn)`: `fn` mutates a copy of the
project; the before/after states are stored as one undo command. Snapshots are
cheap (a project is a few kB of JSON) and make undo trivially correct for
any kind of edit (geometry, materials, settings).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from slipsurface.geometry import SlopeGeometry
from slipsurface.project import Project


class _Snapshot(QUndoCommand):
    def __init__(self, doc: Document, text: str, before: dict, after: dict) -> None:
        super().__init__(text)
        self.doc, self.before, self.after = doc, before, after
        self._first = True

    def redo(self) -> None:
        if self._first:            # already applied by Document.edit
            self._first = False
            return
        self.doc._restore(self.after)

    def undo(self) -> None:
        self.doc._restore(self.before)


class Document(QObject):
    changed = Signal()                 # any change (project replaced or edited)

    def __init__(self, project: Project | None = None) -> None:
        super().__init__()
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(100)   # snapshots are whole projects; keep memory bounded
        self.project = project or Project()
        self.path = None
        self.geometry: SlopeGeometry | None = None
        self.geometry_error = ""
        self._rebuild()

    # ------------------------------------------------------------ state
    def set_project(self, p: Project, path=None) -> None:
        self.project = p
        self.path = path
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self._rebuild()
        self.changed.emit()

    @property
    def dirty(self) -> bool:
        return not self.undo_stack.isClean()

    def mark_clean(self) -> None:
        self.undo_stack.setClean()

    def edit(self, text: str, fn: Callable[[Project], None]) -> bool:
        """Apply `fn` to the project as one undoable step."""
        before = self.project.to_dict()
        p = self.project.copy()
        fn(p)
        after = p.to_dict()
        if after == before:
            return False
        self.project = p
        self._rebuild()
        self.undo_stack.push(_Snapshot(self, text, before, after))
        self.changed.emit()
        return True

    def _restore(self, d: dict) -> None:
        self.project = Project.from_dict(d)
        self._rebuild()
        self.changed.emit()

    def _rebuild(self) -> None:
        self.geometry = None
        self.geometry_error = ""
        if not self.project.has_geometry:
            self.geometry_error = "Dış sınır tanımlı değil."
            return
        try:
            self.geometry = self.project.build_geometry()
        except ValueError as exc:
            self.geometry_error = str(exc)
