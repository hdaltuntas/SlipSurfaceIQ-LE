"""Background analysis so the GUI never freezes: a separate process by default
(see slipsurface.compute_process), relayed to Qt signals by a worker thread."""

from __future__ import annotations

import os
import traceback
import time

from PySide6.QtCore import QObject, QThread, Signal, Slot

from slipsurface.analysis import run_analysis
from slipsurface.optimizer import SearchCancelled


def use_process() -> bool:
    """Whether analyses run in a separate process (the default).

    SLIPSURFACE_COMPUTE=thread keeps the analysis in the GUI process, on a
    worker thread: for environments that cannot start processes, and for
    tests that replace run_analysis."""
    return os.environ.get("SLIPSURFACE_COMPUTE", "process").strip().lower() != "thread"


class AnalysisWorker(QObject):
    progress = Signal(int, int, str, int, float)  # i, n, method, generation, best
    detail = Signal(object)  # copy of the live search status dict
    finished = Signal(object)  # AnalysisResults
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, project, in_process: bool | None = None) -> None:
        super().__init__()
        self.project = project
        self.status: dict = {}
        self._stop = False
        self._job = None
        self.in_process = use_process() if in_process is None else in_process

    def request_stop(self) -> None:
        self._stop = True
        job = self._job
        if job is not None:
            job.request_stop()

    @Slot()
    def run(self) -> None:
        if self.in_process:
            self._run_in_process()
        else:
            self._run_in_thread()

    def _run_in_process(self) -> None:
        """Relay the child's messages; this thread only waits, so the window
        keeps the interpreter to itself."""
        from slipsurface.compute_process import ProcessAnalysis

        try:
            job = ProcessAnalysis(self.project)
            job.start()
        except Exception as exc:  # no processes here: solve on this thread instead
            traceback.print_exc()
            self.status["note"] = f"separate process unavailable ({exc})"
            self._run_in_thread()
            return
        self._job = job
        if self._stop:
            job.request_stop()
        try:
            for kind, payload in job.events():
                if kind == "progress":
                    i, n, method, generation, best, status = payload
                    self.status = status
                    self.progress.emit(i, n, method, generation, best)
                    self.detail.emit(status)
                elif kind == "result":
                    self.finished.emit(payload)
                elif kind == "cancelled":
                    self.cancelled.emit()
                else:
                    self.failed.emit(str(payload))
        except Exception as exc:  # report, never crash the GUI
            traceback.print_exc()
            self.failed.emit(str(exc))
        finally:
            self._job = None

    def _run_in_thread(self) -> None:
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
