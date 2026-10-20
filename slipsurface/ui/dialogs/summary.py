"""Project Summary dialog."""

from __future__ import annotations

from slipsurface.ui.preferences import fit_to_screen

from slipsurface.ui.i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
)

from slipsurface.project import ProjectSummary
from slipsurface.ui.icons import icon

ROWS = [("title", tr("Proje başlığı")), ("analysis", "Analiz"), ("author", tr("Hazırlayan")),
        ("company", "Kurum"), ("date_created", tr("Oluşturulma tarihi"))] + \
       [(f"comment{i}", f"Not {i + 1}") for i in range(5)]


class ProjectSummaryDialog(QDialog):
    def __init__(self, summary: ProjectSummary, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Proje Özeti"))
        fit_to_screen(self, 560, 470)
        self.table = QTableWidget(len(ROWS), 2)
        self.table.setHorizontalHeaderLabels([tr("Tür"), tr("Açıklama")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for r, (key, label) in enumerate(ROWS):
            it = QTableWidgetItem(label)
            it.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(r, 0, it)
            if key.startswith("comment"):
                val = summary.comments[int(key[7:])] if int(key[7:]) < len(summary.comments) else ""
            else:
                val = getattr(summary, key)
            v = QTableWidgetItem(val)
            if key == "date_created":
                v.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(r, 1, v)

        copy_b, paste_b = QToolButton(), QToolButton()
        copy_b.setIcon(icon("summary"))
        copy_b.setToolTip("Panoya kopyala")
        paste_b.setIcon(icon("coords"))
        paste_b.setToolTip(tr("Panodan yapıştır (satır satır)"))
        copy_b.clicked.connect(self._copy)
        paste_b.clicked.connect(self._paste)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(copy_b)
        top.addWidget(paste_b)

        same = QCheckBox(tr("Tüm senaryolarda aynı proje özeti"))
        same.setChecked(True)
        same.setEnabled(False)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("Tamam"))
        btns.button(QDialogButtonBox.Cancel).setText(tr("İptal"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(same)
        bottom.addStretch(1)
        bottom.addWidget(btns)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.table, 1)
        lay.addLayout(bottom)

    def summary(self) -> ProjectSummary:
        vals = {key: (self.table.item(r, 1).text() if self.table.item(r, 1) else "")
                for r, (key, _) in enumerate(ROWS)}
        return ProjectSummary(title=vals["title"], analysis=vals["analysis"],
                              author=vals["author"], company=vals["company"],
                              date_created=vals["date_created"],
                              comments=[vals[f"comment{i}"] for i in range(5)])

    def _copy(self) -> None:
        lines = [f"{self.table.item(r, 0).text()}\t{self.table.item(r, 1).text()}"
                 for r in range(len(ROWS))]
        QGuiApplication.clipboard().setText("\n".join(lines))

    def _paste(self) -> None:
        lines = QGuiApplication.clipboard().text().splitlines()
        for r, line in enumerate(lines[:len(ROWS)]):
            val = line.split("\t", 1)[-1]
            if ROWS[r][0] != "date_created":
                self.table.item(r, 1).setText(val)
