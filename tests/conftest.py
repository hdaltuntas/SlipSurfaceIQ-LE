"""Pytest setup: headless Qt by default so the suite runs in any IDE/CI."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# GUI tests solve on a worker thread (fast, and some replace run_analysis); the
# separate-process path has its own tests.
os.environ.setdefault("SLIPSURFACE_COMPUTE", "thread")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# PySide6 can crash while the interpreter finalizes after all tests passed
# ("Fatal Python error: none_dealloc", seen with Python 3.10 on Linux). Once
# pytest has printed its summary, leave with its exit status and skip the
# interpreter teardown. Linux only: on Windows os._exit itself faults in the
# Qt DLL teardown, and the normal shutdown works there.
_exit_status = None


def pytest_sessionfinish(session, exitstatus):
    global _exit_status
    _exit_status = int(exitstatus)


def _cleanup_qt_before_shutdown() -> None:
    """Destroy lingering top-level widgets and module-cached Qt GUI resources
    while QApplication is still alive so Windows Qt DLL teardown cannot fault
    on QPixmap / QRawFont / QIconEngine / open QDialog destructors."""
    import gc

    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QDialog

    app = QApplication.instance()
    if app is None:
        return
    # Close open dialogs (e.g. non-blocking QMessageBox.open()) before parent windows
    for w in list(app.topLevelWidgets()):
        if isinstance(w, QDialog):
            try:
                w.done(0)
                w.close()
                w.deleteLater()
            except RuntimeError:
                pass
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()

    for w in list(app.topLevelWidgets()):
        try:
            if w.isVisible():
                if hasattr(w, "doc") and hasattr(w.doc, "mark_clean"):
                    w.doc.mark_clean()
                if hasattr(w, "_result_notes_dirty"):
                    w._result_notes_dirty = False
                w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()

    try:
        from slipsurface.ui import icons, preferences

        icons._qta_icon.cache_clear()
        icons._custom_icon.cache_clear()
        preferences.interface_font.cache_clear()
    except Exception:
        pass
    try:
        import qtawesome as qta

        inst = qta._resource.get("iconic")
        if inst is not None:
            inst.icon_cache.clear()
            inst.rawfont_cache.clear()
            qta._resource["iconic"] = None
    except Exception:
        pass
    gc.collect()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def pytest_unconfigure(config):
    sys.stdout.flush()
    sys.stderr.flush()
    if _exit_status is not None and "PySide6.QtWidgets" in sys.modules:
        if sys.platform.startswith("linux"):
            os._exit(_exit_status)
        _cleanup_qt_before_shutdown()
