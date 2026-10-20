"""Background analysis so the GUI never freezes."""

from __future__ import annotations

import traceback
import time

from PySide6.QtCore import QObject, QThread, Signal, Slot

from slipsurface.analysis import run_analysis
from slipsurface.optimizer import SearchCancelled


class AnalysisWorker(QObject):
    progress = Signal(int, int, str, int, float)  # i, n, method, generation, best
    detail = Signal(object)  # copy of the live search status dict
    finished = Signal(object)  # AnalysisResults
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, project) -> None:
        super().__init__()
        self.project = project
        self.status: dict = {}
        self._stop = False

    def request_stop(self) -> None:
        self._stop = True

    @Slot()
    def run(self) -> None:
        last_update = 0.0

        def on_progress(i, n, m, gen, best) -> bool:
            nonlocal last_update
            now = time.monotonic()
            if now - last_update >= 0.1:
                self.progress.emit(i, n, m, gen, best)
                self.detail.emit(dict(self.status, done=dict(self.status.get("done", {}))))
                last_update = now
            return self._stop

        try:
            res = run_analysis(self.project, on_progress, status=self.status)
        except SearchCancelled:
            self.cancelled.emit()
        except Exception as exc:  # report, never crash the GUI
            traceback.print_exc()
            self.failed.emit(str(exc))
        else:
            self.finished.emit(res)


def start_worker(worker: AnalysisWorker, parent: QObject | None = None) -> QThread:
    """Move worker to a new parented thread (GC can't kill it while running)."""
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    for sig in (worker.finished, worker.failed, worker.cancelled):
        sig.connect(thread.quit)
        sig.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread
