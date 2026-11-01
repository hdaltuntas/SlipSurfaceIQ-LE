"""Computing dialog: live, detailed state of the critical surface search."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QVBoxLayout,
)

from slipsurface.lem import method_name

STAGES = {
    "presearch": "Circular pre-search (Bishop, population seed)",
    "evolution": "Differential evolution (global search)",
    "polish": "Nelder-Mead refinement",
    "vertices": "Free optimisation of the polyline vertices",
    "refine": "Inserting mid vertices and re-optimising",
    "final": "Final solution of the critical surface",
    "user": "Solving the user-defined surface",
}
SURFACES = {
    "circular": "Circular",
    "polyline": "Non-circular (polyline)",
    "spline": "Non-circular (B-spline)",
    "user": "User-defined",
}


def _clock(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _fs(v) -> str:
    return f"{v:.4f}" if isinstance(v, (int, float)) and math.isfinite(v) else "—"


class ComputeDialog(QDialog):
    """Modal progress window with a details grid and a running log."""

    canceled = Signal()

    def __init__(self, n_methods: int, title: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compute")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(780)
        self.n = max(n_methods, 1)
        self.t0 = time.monotonic()
        self._stage_key = None
        self._done_seen: set = set()
        self._finished = False

        self.header = QLabel("Computing…")
        self.header.setStyleSheet("font-size:16px;font-weight:600;")
        self.subtitle = QLabel(title)
        self.subtitle.setStyleSheet("color:#6b7a90;")
        self.label = QLabel()  # one-line summary (also for tests)
        self.label.setWordWrap(True)
        self.overall = QProgressBar()
        self.overall.setRange(0, self.n * 100)
        self.overall.setFormat("Total" + "  %p%")
        self.stage_bar = QProgressBar()
        self.stage_bar.setRange(0, 100)
        self.stage_bar.setFormat("Stage" + "  %p%")

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self.fields = {}
        rows = [
            ("method", "Method"),
            ("stage", "Stage"),
            ("surface", "Surface type"),
            ("slices", "Number of slices"),
            ("generation", "Generation"),
            ("evaluated", "Surfaces evaluated"),
            ("valid", "Valid / rejected"),
            ("best", "Lowest FS"),
            ("current", "Last valid FS"),
            ("elapsed", "Elapsed time"),
            ("remaining", "Estimated time left"),
        ]
        for r, (key, text) in enumerate(rows):
            lab = QLabel(text + ":")
            lab.setStyleSheet("color:#6b7a90;")
            val = QLabel("—")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(lab, r // 2, 2 * (r % 2))
            grid.addWidget(val, r // 2, 2 * (r % 2) + 1)
            self.fields[key] = val

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(130)
        self.log.setStyleSheet("font-family:Consolas,'DejaVu Sans Mono',monospace;font-size:12px;")

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.cancel_button = buttons.button(QDialogButtonBox.Cancel)
        self.cancel_button.setText("Cancel")
        buttons.rejected.connect(self._cancel)

        lay = QVBoxLayout(self)
        lay.addWidget(self.header)
        lay.addWidget(self.subtitle)
        lay.addWidget(self.overall)
        lay.addWidget(self.stage_bar)
        lay.addWidget(self.label)
        lay.addLayout(grid)
        lay.addWidget(QLabel("Log"))
        lay.addWidget(self.log, 1)
        lay.addWidget(buttons)
        self._log("Analysis started")

    # ----------------------------------------------- QProgressDialog-like API
    def labelText(self) -> str:
        return self.label.text()

    def setLabelText(self, text: str) -> None:
        self.label.setText(text)

    def setValue(self, v: int) -> None:
        self.overall.setValue(int(v))

    def _cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        self.header.setText("Cancelling…")
        self._log("Cancellation requested")
        self.canceled.emit()

    def reject(self) -> None:  # Esc / window close = cancel
        if self._finished:
            super().reject()
        elif self.cancel_button.isEnabled():
            self._cancel()

    def finish(self) -> None:
        """Close for good (the computation ended)."""
        self._finished = True
        self.close()
        self.deleteLater()

    # ------------------------------------------------------------ updates
    def _log(self, text: str) -> None:
        self.log.appendPlainText(f"[{_clock(time.monotonic() - self.t0)}] {text}")

    def update_status(self, st: dict) -> None:
        i = int(st.get("index", 0))
        m = st.get("method")
        mname = method_name(m) if m else "—"
        stage = st.get("stage")
        gen, maxiter = int(st.get("generation", 0) or 0), int(st.get("maxiter", 0) or 0)
        frac = min(gen / maxiter, 0.99) if maxiter else 0.0
        if stage in ("polish", "vertices", "refine", "final"):
            frac = 0.99
        self.overall.setValue(int(100 * i + 100 * frac))
        self.stage_bar.setValue(int(100 * frac))
        elapsed = time.monotonic() - self.t0
        done = i + frac
        remaining = elapsed / done * (self.n - done) if done > 0.05 else float("nan")

        for key, value in st.get("done", {}).items():
            if key in self._done_seen:
                continue
            self._done_seen.add(key)
            if isinstance(value, (int, float)):
                self._log(f"{method_name(key)}: finished, FS = {value:.3f}")
            else:
                self._log(f"{method_name(key)}: no result — {value}")
        if (m, stage) != self._stage_key and stage:
            self._stage_key = (m, stage)
            self._log(f"{mname}: {STAGES.get(stage, stage)}")

        f = self.fields
        f["method"].setText(f"{i + 1} / {self.n}   {mname}")
        f["stage"].setText(STAGES.get(stage, stage or "—"))
        f["surface"].setText(SURFACES.get(st.get("surface_type"), "—"))
        f["slices"].setText(str(st.get("n_slices", "—")))
        f["generation"].setText(f"{gen} / {maxiter}" if maxiter else "—")
        f["evaluated"].setText(str(st.get("evaluated", 0)))
        f["valid"].setText(f"{st.get('valid', 0)} / {st.get('rejected', 0)}")
        f["best"].setText(_fs(st.get("best")))
        f["current"].setText(_fs(st.get("current")))
        f["elapsed"].setText(_clock(elapsed))
        f["remaining"].setText(_clock(remaining) if math.isfinite(remaining) else "—")
        pre = " (pre-search)" if stage == "presearch" else ""
        self.label.setText(
            f"Method {i + 1}/{self.n}: {mname}{pre} — "
            f"Generation {gen}, lowest FS {_fs(st.get('best'))}"
        )
