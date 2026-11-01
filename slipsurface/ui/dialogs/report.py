"""PDF report dialog (report data, target FS, sections) and the export action."""

from __future__ import annotations


import datetime as _dt
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from slipsurface.report import ReportOptions

SECTIONS = [  # (option attribute, label, default)
    ("toc", "Table of contents", True),
    ("model", "Model figure and geometry", True),
    ("materials", "Material properties", True),
    ("settings", "Analysis settings", True),
    ("loads", "Loads, supports, facing", True),
    ("results", "Results table and FS chart", True),
    ("global_figure", "Critical surface figure (global minimum)", True),
    ("method_figures", "Critical surface figure for every method", True),
    ("support_forces", "Mobilised support forces", True),
    ("slice_table", "Appendix: slice data", True),
    ("coordinates", "Appendix: coordinates", False),
]
_SETTINGS_KEYS = ("author", "checker", "company")


def _settings() -> QSettings:
    return QSettings("SlipSurface", "SlipSurface LE")


class ReportDialog(QDialog):
    def __init__(self, project, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PDF Report")
        self.setMinimumWidth(620)
        st = _settings()
        sm = project.summary
        title = QLabel("Analysis Report (PDF)")
        title.setStyleSheet("color:#2a7ad0;font-size:16px;")

        default = "Slope Stability Analysis Report"
        stored = st.value("report/title", default)
        self.title = QLineEdit(stored)
        self.project = QLineEdit(sm.title)
        self.analysis = QLineEdit(sm.analysis)
        self.author = QLineEdit(sm.author or st.value("report/author", ""))
        self.checker = QLineEdit(st.value("report/checker", ""))
        self.company = QLineEdit(sm.company or st.value("report/company", ""))
        self.report_no = QLineEdit()
        self.report_no.setPlaceholderText("e.g. PRJ-13-2026-041")
        self.date = QLineEdit(_dt.date.today().strftime("%Y-%m-%d"))
        info = QGroupBox("Report information")
        f = QFormLayout(info)
        f.addRow("Report title:", self.title)
        f.addRow("Project:", self.project)
        f.addRow("Analysis:", self.analysis)
        f.addRow("Author:", self.author)
        f.addRow("Checked by:", self.checker)
        f.addRow("Company:", self.company)
        f.addRow("Report no.:", self.report_no)
        f.addRow("Date:", self.date)

        ev = QGroupBox("Assessment")
        el = QHBoxLayout(ev)
        self.use_target = QCheckBox("Assess against the target factor of safety:")
        self.use_target.setChecked(st.value("report/use_target", True, bool))
        self.target = QDoubleSpinBox()
        self.target.setRange(1.0, 5.0)
        self.target.setDecimals(2)
        self.target.setSingleStep(0.05)
        self.target.setValue(float(st.value("report/target", 1.5)))
        self.use_target.toggled.connect(self.target.setEnabled)
        self.target.setEnabled(self.use_target.isChecked())
        el.addWidget(self.use_target)
        el.addWidget(self.target)
        el.addStretch(1)

        sec = QGroupBox("Sections")
        g = QGridLayout(sec)
        self.checks = {}
        for i, (key, label, default) in enumerate(SECTIONS):
            cb = QCheckBox(label)
            cb.setChecked(st.value(f"report/{key}", default, bool))
            self.checks[key] = cb
            g.addWidget(cb, i // 2, i % 2)
        self.open_after = QCheckBox("Open the PDF when created")
        self.open_after.setChecked(st.value("report/open_after", True, bool))

        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.button(QDialogButtonBox.Ok).setText("Create Report…")
        b.button(QDialogButtonBox.Cancel).setText("Cancel")
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addWidget(info)
        lay.addWidget(ev)
        lay.addWidget(sec)
        lay.addWidget(self.open_after)
        lay.addWidget(b)

    def options(self) -> ReportOptions:
        o = ReportOptions(
            title=self.title.text().strip() or "Slope Stability Analysis Report",
            project=self.project.text().strip(),
            analysis=self.analysis.text().strip(),
            author=self.author.text().strip(),
            checker=self.checker.text().strip(),
            company=self.company.text().strip(),
            report_no=self.report_no.text().strip(),
            date=self.date.text().strip(),
            target_fs=self.target.value() if self.use_target.isChecked() else None,
        )
        for key, cb in self.checks.items():
            setattr(o, key, cb.isChecked())
        return o

    def remember(self) -> None:
        st = _settings()
        st.setValue("report/title", self.title.text())
        st.setValue("report/author", self.author.text())
        st.setValue("report/checker", self.checker.text())
        st.setValue("report/company", self.company.text())
        st.setValue("report/use_target", self.use_target.isChecked())
        st.setValue("report/target", self.target.value())
        st.setValue("report/open_after", self.open_after.isChecked())
        for key, cb in self.checks.items():
            st.setValue(f"report/{key}", cb.isChecked())


def make_report(results, path, opts: ReportOptions, display_project=None) -> int:
    """Render the drawings and write the PDF (no dialogs). Returns page count."""
    from slipsurface.report import build_pdf
    from slipsurface.ui.report_figures import report_figures

    figs = report_figures(
        results,
        display_project,
        method_figures=opts.method_figures,
        model_figure=opts.model,
        global_figure=True,
    )
    return build_pdf(results, path, opts, figs)


def export_report(parent, results, display_project=None, model_path=None) -> str | None:
    """Report dialog → file dialog → PDF. Returns the written path."""
    if results is None or not results.results:
        QMessageBox.warning(parent, "PDF Report", "Run the analysis first (Compute, F5).")
        return None
    dlg = ReportDialog(results.project, parent)
    if not dlg.exec():
        return None
    dlg.remember()
    opts = dlg.options()
    opts.model_file = Path(model_path).name if model_path else ""
    stem = Path(model_path).name.split(".")[0] if model_path else "report"
    start = str((Path(model_path).parent if model_path else Path.home()) / f"{stem}_report.pdf")
    path, _ = QFileDialog.getSaveFileName(parent, "Save PDF report", start, "PDF (*.pdf)")
    if not path:
        return None
    if not path.lower().endswith(".pdf"):
        path += ".pdf"
    QGuiApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        n = make_report(results, path, opts, display_project)
    except PermissionError:
        QGuiApplication.restoreOverrideCursor()
        QMessageBox.critical(
            parent,
            "PDF Report",
            f"The file could not be written (it may be open in another program):\n{path}",
        )
        return None
    except Exception as exc:  # report must never crash the app
        QGuiApplication.restoreOverrideCursor()
        QMessageBox.critical(parent, "PDF Report", f"The report could not be created:\n{exc}")
        return None
    QGuiApplication.restoreOverrideCursor()
    if hasattr(parent, "statusBar"):
        parent.statusBar().showMessage(f"PDF report saved ({n} pages): {path}", 10000)
    if dlg.open_after.isChecked():
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return path
