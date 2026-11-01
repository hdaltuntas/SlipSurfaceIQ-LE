"""Update notifications: automatic check at start-up and Help → Check for Updates.

The network request runs on a background thread; results come back to the
GUI thread through queued signals. Automatic checks are silent on failure,
run at most once a day and skip a version the user chose to skip.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from slipsurface import __version__
from slipsurface.ui.preferences import settings
from slipsurface.updates import ReleaseInfo, UpdateCheckError, fetch_latest, is_newer

AUTO_KEY = "updates/auto"
LAST_KEY = "updates/last_check"
SKIP_KEY = "updates/skipped"
AUTO_INTERVAL = 24 * 3600.0  # seconds between automatic checks
NOTES_LINES = 8  # release-note lines shown in the dialog; the rest is on the release page


def auto_enabled() -> bool:
    return settings().value(AUTO_KEY, True, type=bool)


def set_auto_enabled(on: bool) -> None:
    settings().setValue(AUTO_KEY, bool(on))


def auto_check_due(now: float | None = None) -> bool:
    if not auto_enabled():
        return False
    last = settings().value(LAST_KEY, 0.0, type=float)
    return (time.time() if now is None else now) - last >= AUTO_INTERVAL


def notes_excerpt(notes: str, lines: int = NOTES_LINES) -> str:
    """First non-empty lines of the release notes as plain text."""
    rows = [r.strip() for r in notes.splitlines() if r.strip()]
    text = "\n".join(r.lstrip("#").strip() for r in rows[:lines])
    return text + ("\n…" if len(rows) > lines else "")


class UpdateChecker(QObject):
    """Owns one check at a time and the dialogs that report it."""

    found = Signal(object, bool)  # ReleaseInfo, manual
    failed = Signal(str, bool)  # reason, manual
    applied = Signal(str, str)  # version, summary (delta update finished)
    progressed = Signal(int, int, str)  # done, total, relpath

    def __init__(self, parent: QWidget, fetch=fetch_latest) -> None:
        super().__init__(parent)
        self._parent = parent
        self._fetch = fetch
        self._busy = False
        self.dialog: QMessageBox | None = None
        self.found.connect(self._on_found)
        self.failed.connect(self._on_failed)
        self.applied.connect(self._on_applied)
        self.progressed.connect(self._on_progressed)

    @property
    def busy(self) -> bool:
        return self._busy

    def check(self, manual: bool = True) -> bool:
        """Start a check; False if one is already running."""
        if self._busy:
            return False
        self._busy = True
        self._status("Checking for updates…")
        threading.Thread(target=self._run, args=(manual,), daemon=True).start()
        return True

    def check_if_due(self) -> bool:
        return auto_check_due() and self.check(manual=False)

    def _run(self, manual: bool) -> None:
        try:
            info = self._fetch()
        except UpdateCheckError as exc:
            self.failed.emit(str(exc), manual)
        except Exception as exc:  # never let a background check crash the GUI
            self.failed.emit(str(exc) or type(exc).__name__, manual)
        else:
            self.found.emit(info, manual)

    # ---------------------------------------------------------- results
    def _on_found(self, info: ReleaseInfo, manual: bool) -> None:
        self._busy = False
        settings().setValue(LAST_KEY, time.time())
        if not is_newer(info.version):
            self._status(f"SlipSurfaceIQ LE is up to date (version {__version__}).")
            if manual:
                self._show(
                    QMessageBox.Information,
                    "No Update Available",
                    f"You are using the latest version ({__version__}).",
                )
            return
        if not manual and settings().value(SKIP_KEY, "") == info.version:
            return
        self._status(f"New version available: {info.version}")
        self._offer(info)

    def _on_failed(self, reason: str, manual: bool) -> None:
        self._busy = False
        self._status("")
        if manual:
            self._show(
                QMessageBox.Warning,
                "Update Check",
                f"Could not check for updates: {reason}",
            )

    def _on_applied(self, version: str, summary: str) -> None:
        """A delta update finished successfully."""
        self._busy = False
        self._status("")
        box = self._box(
            QMessageBox.Information,
            "Update Complete",
            f"SlipSurfaceIQ LE {version} files updated."
            + "\n"
            + summary
            + "\n\n"
            + "Restart the application for all changes to take effect. Previous files are backed up in .update-backup.",
        )
        box.addButton(QMessageBox.Ok)
        box.open()

    def _offer(self, info: ReleaseInfo) -> None:
        box = self._box(
            QMessageBox.Information,
            "Update Available",
            f"SlipSurfaceIQ LE {info.version} has been released (you are using {__version__})."
            + "\n"
            + "Only the changed files are downloaded and copied in place; replaced files are backed up to .update-backup.",
        )
        if info.notes.strip():
            box.setInformativeText(notes_excerpt(info.notes))
        patch = box.addButton("Update Changed Files", QMessageBox.AcceptRole)
        download = box.addButton("Open Source Release Page", QMessageBox.AcceptRole)
        skip = box.addButton("Skip This Version", QMessageBox.DestructiveRole)
        box.addButton("Later", QMessageBox.RejectRole)
        box.setDefaultButton(patch)

        def clicked(button) -> None:
            if button is patch:
                self._apply_delta(info)
            elif button is download:
                QDesktopServices.openUrl(QUrl(info.url))
            elif button is skip:
                settings().setValue(SKIP_KEY, info.version)

        box.buttonClicked.connect(clicked)
        box.open()

    # ------------------------------------------------------ delta update
    def _apply_delta(self, info: ReleaseInfo) -> None:
        """Download and copy only the changed files, on a worker thread."""
        if self._busy:
            return
        self._busy = True
        self._status("Planning update…")

        def run() -> None:
            from slipsurface.patch import apply_update, plan_against_local

            try:
                plan = plan_against_local(info.version)
                summary = apply_update(
                    plan,
                    info.version,
                    progress=lambda done, total, rel: self._progress(done, total, rel),
                )
            except Exception as exc:  # UpdateCheckError or any network error
                self.failed.emit(str(exc), True)
            else:
                self.applied.emit(info.version, summary)

        threading.Thread(target=run, daemon=True).start()

    def _progress(self, done: int, total: int, relpath: str) -> bool:
        """Emit progress to the GUI thread; return True to cancel (never, for now)."""
        self.progressed.emit(done, total, relpath)
        return False

    def _on_progressed(self, done: int, total: int, relpath: str) -> None:
        self._status(f"Updating: {done}/{total} ({relpath})")

    # ---------------------------------------------------------- helpers
    def _box(self, kind, title: str, text: str) -> QMessageBox:
        if self.dialog is not None:
            self.dialog.close()
        box = QMessageBox(kind, title, text, QMessageBox.NoButton, self._parent)
        self.dialog = box
        return box

    def _show(self, kind, title: str, text: str) -> None:
        box = self._box(kind, title, text)
        box.addButton(QMessageBox.Ok)
        box.open()

    def _status(self, text: str) -> None:
        bar = getattr(self._parent, "status", None)
        if bar is None:
            return
        if text:
            bar.showMessage(text, 8000)
        else:
            bar.clearMessage()
