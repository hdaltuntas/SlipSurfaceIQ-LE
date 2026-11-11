"""Run an analysis in a separate process.

A search evaluates thousands of surfaces in Python; inside the GUI process it
competes with the event loop for the interpreter lock and the window stutters.
Here the analysis runs in its own interpreter: the window stays responsive, a
cancel takes effect even inside a long solver call (the process is ended if it
does not stop by itself) and a crash of the numerical code cannot take the
application down.

No Qt in this module. The parent drives it through :class:`ProcessAnalysis`:

    job = ProcessAnalysis(project)
    job.start()
    for kind, payload in job.events():   # "progress" | "result" | "cancelled" | "error"
        ...
"""

from __future__ import annotations

import multiprocessing as mp
import pickle
import time
import traceback
from collections.abc import Iterator

from slipsurface.project import Project

POLL = 0.05  # s, how often the parent looks for messages
STOP_GRACE = 5.0  # s the child gets to stop by itself after a cancel request
PROGRESS_INTERVAL = 0.1  # s between progress messages


def _child(project_dict: dict, conn, stop) -> None:
    """Entry point of the worker process (must be importable: spawn)."""
    try:
        from slipsurface.analysis import run_analysis
        from slipsurface.optimizer import SearchCancelled

        status: dict = {}
        last = 0.0

        def progress(i, n, method, generation, best) -> bool:
            nonlocal last
            now = time.monotonic()
            if now - last >= PROGRESS_INTERVAL:
                last = now
                snapshot = dict(status, done=dict(status.get("done", {})))
                conn.send(("progress", (i, n, method, generation, best, snapshot)))
            return stop.is_set()

        try:
            results = run_analysis(Project.from_dict(project_dict), progress, status=status)
        except SearchCancelled:
            conn.send(("cancelled", None))
        else:
            conn.send(("result", pickle.dumps(results, pickle.HIGHEST_PROTOCOL)))
    except BaseException as exc:  # report everything; the parent shows it
        traceback.print_exc()
        try:
            conn.send(("error", str(exc) or type(exc).__name__))
        except Exception:
            pass
    finally:
        conn.close()


class ProcessAnalysis:
    """One analysis in a child process (spawned: safe next to Qt and threads)."""

    def __init__(self, project: Project) -> None:
        self._project = project
        ctx = mp.get_context("spawn")
        self._stop = ctx.Event()
        self._parent, self._child_end = ctx.Pipe(duplex=False)
        self._process = ctx.Process(
            target=_child,
            args=(project.to_dict(), self._child_end, self._stop),
            name="slipsurface-analysis",
            daemon=True,
        )
        self._stop_requested_at: float | None = None

    def start(self) -> None:
        self._process.start()
        self._child_end.close()  # the child holds its own copy

    def request_stop(self) -> None:
        if self._stop_requested_at is None:
            self._stop_requested_at = time.monotonic()
        self._stop.set()

    def events(self) -> Iterator[tuple[str, object]]:
        """Messages until the analysis ends. The last one is "result" (the
        AnalysisResults), "cancelled" (None) or "error" (text)."""
        try:
            while True:
                if self._parent.poll(POLL):
                    try:
                        kind, payload = self._parent.recv()
                    except (EOFError, OSError):
                        yield self._ended_without_result()
                        return
                    if kind == "result":
                        results = pickle.loads(payload)
                        # the summary may hold values a file round trip normalises
                        results.project.summary = self._project.copy().summary
                        yield "result", results
                        return
                    yield kind, payload
                    if kind in ("cancelled", "error"):
                        return
                elif not self._process.is_alive():
                    if self._parent.poll(0):  # a last message raced the exit
                        continue
                    yield self._ended_without_result()
                    return
                elif (
                    self._stop_requested_at is not None
                    and time.monotonic() - self._stop_requested_at > STOP_GRACE
                ):
                    self._process.terminate()  # stuck inside one long solver call
                    yield "cancelled", None
                    return
        finally:
            self.close()

    def _ended_without_result(self) -> tuple[str, object]:
        if self._stop_requested_at is not None:
            return "cancelled", None
        self._process.join(1.0)
        return (
            "error",
            "The computation process ended unexpectedly "
            f"(exit code {self._process.exitcode}). The model is unchanged; compute again.",
        )

    def close(self) -> None:
        if self._process.is_alive():
            self._process.join(1.0)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(2.0)
        self._parent.close()
