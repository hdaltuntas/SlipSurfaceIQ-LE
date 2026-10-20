"""PDF report dialog (report data, target FS, sections) and the export action."""

from __future__ import annotations

from slipsurface.ui.i18n import language, tr

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
    ("toc", "İçindekiler", True),
    ("model", "Model şekli ve geometri", True),
    ("materials", "Malzeme özellikleri", True),
    ("settings", "Analiz ayarları", True),
    ("loads", "Yükler, destekler, kaplama", True),
    ("results", "Sonuç tablosu ve FS grafiği", True),
    ("global_figure", "Kritik yüzey şekli (global minimum)", True),
    ("method_figures", "Her yöntem için kritik yüzey şekli", True),
    ("support_forces", "Mobilize destek kuvvetleri", True),
    ("slice_table", "Ek: dilim verileri", True),
    ("coordinates", "Ek: koordinatlar", False),
]
_SETTINGS_KEYS = ("author", "checker", "company")


def _settings() -> QSettings:
    return QSettings("SlipSurface", "SlipSurface LE")


class ReportDialog(QDialog):
    def __init__(self, project, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PDF Rapor")
        self.setMinimumWidth(620)
        st = _settings()
        sm = project.summary
        title = QLabel("Analiz Raporu (PDF)")
        title.setStyleSheet("color:#2a7ad0;font-size:16px;")

        default = tr("Şev Stabilite Analiz Raporu")
        stored = st.value("report/title", default)
        if stored in ("Şev Stabilite Analiz Raporu", "Slope Stability Analysis Report"):
            stored = default  # default title follows the language
        self.title = QLineEdit(stored)
        self.project = QLineEdit(sm.title)
        self.analysis = QLineEdit(sm.analysis)
        self.author = QLineEdit(sm.author or st.value("report/author", ""))
        self.checker = QLineEdit(st.value("report/checker", ""))
        self.company = QLineEdit(sm.company or st.value("report/company", ""))
        self.report_no = QLineEdit()
        self.report_no.setPlaceholderText("örn. KGM-13-2026-041")
        self.date = QLineEdit(
            _dt.date.today().strftime("%Y-%m-%d" if language() == "en" else "%d.%m.%Y")
        )
        info = QGroupBox("Rapor bilgileri")
        f = QFormLayout(info)
        f.addRow("Rapor başlığı:", self.title)
        f.addRow("Proje:", self.project)
        f.addRow(tr("Analiz:"), self.analysis)
        f.addRow(tr("Hazırlayan:"), self.author)
        f.addRow("Kontrol eden:", self.checker)
        f.addRow("Firma / kurum:", self.company)
        f.addRow("Rapor no:", self.report_no)
        f.addRow(tr("Tarih:"), self.date)

        ev = QGroupBox("Değerlendirme")
        el = QHBoxLayout(ev)
        self.use_target = QCheckBox("Hedef güvenlik sayısı ile değerlendir:")
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

        sec = QGroupBox("Bölümler")
        g = QGridLayout(sec)
        self.checks = {}
        for i, (key, label, default) in enumerate(SECTIONS):
            cb = QCheckBox(label)
            cb.setChecked(st.value(f"report/{key}", default, bool))
            self.checks[key] = cb
            g.addWidget(cb, i // 2, i % 2)
        self.open_after = QCheckBox("Oluşturduktan sonra PDF'i aç")
        self.open_after.setChecked(st.value("report/open_after", True, bool))

        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.button(QDialogButtonBox.Ok).setText("Raporu Oluştur…")
        b.button(QDialogButtonBox.Cancel).setText(tr("İptal"))
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
            title=self.title.text().strip() or tr("Şev Stabilite Analiz Raporu"),
            project=self.project.text().strip(),
            analysis=self.analysis.text().strip(),
            author=self.author.text().strip(),
            checker=self.checker.text().strip(),
            company=self.company.text().strip(),
            report_no=self.report_no.text().strip(),
            date=self.date.text().strip(),
            target_fs=self.target.value() if self.use_target.isChecked() else None,
            language=language(),
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
        QMessageBox.warning(parent, tr("PDF Rapor"), tr("Önce analizi çalıştırın (Hesapla, F5)."))
        return None
    dlg = ReportDialog(results.project, parent)
    if not dlg.exec():
        return None
    dlg.remember()
    opts = dlg.options()
    opts.model_file = Path(model_path).name if model_path else ""
    word = "report" if language() == "en" else "rapor"
    stem = Path(model_path).name.split(".")[0] if model_path else word
    start = str((Path(model_path).parent if model_path else Path.home()) / f"{stem}_{word}.pdf")
    path, _ = QFileDialog.getSaveFileName(parent, tr("PDF raporu kaydet"), start, "PDF (*.pdf)")
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
            tr("PDF Rapor"),
            tr(f"Dosya yazılamadı (başka bir programda açık olabilir):\n{path}"),
        )
        return None
    except Exception as exc:  # report must never crash the app
        QGuiApplication.restoreOverrideCursor()
        QMessageBox.critical(parent, tr("PDF Rapor"), tr(f"Rapor oluşturulamadı:\n{exc}"))
        return None
    QGuiApplication.restoreOverrideCursor()
    if hasattr(parent, "statusBar"):
        parent.statusBar().showMessage(tr(f"PDF rapor kaydedildi ({n} sayfa): {path}"), 10000)
    if dlg.open_after.isChecked():
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return path
