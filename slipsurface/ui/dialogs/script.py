from slipsurface.ui.preferences import fit_to_screen
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
)
from slipsurface.scripting import TEMPLATE, run_script


class ScriptDialog(QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle("Python scripting")
        fit_to_screen(self, 960, 720)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Python scripts run with your account permissions. Run trusted code only.\n"
                "Changes are validated and applied as one undoable operation. Units: m, kN, kPa."
            )
        )
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(TEMPLATE)
        # Text of a script opened from a file that the user has not yet
        # confirmed as trusted; cleared after the first confirmation.
        self.untrusted_source: str | None = None
        self.confirm = self._ask_trust
        self.editor.setStyleSheet("font-family: Consolas; font-size: 13px;")
        layout.addWidget(self.editor, 3)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        buttons = QHBoxLayout()
        for title, slot in (
            ("Open .py", self.load),
            ("Save .py", self.save),
            ("Run / Apply", self.run),
            ("Close", self.accept),
        ):
            button = QPushButton(title)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def load(self):
        from pathlib import Path

        path, _ = QFileDialog.getOpenFileName(self, "Open script", "", "Python (*.py)")
        if path:
            try:
                self.editor.setPlainText(Path(path).read_text(encoding="utf-8"))
                self.untrusted_source = path
            except OSError as exc:
                self.output.setPlainText(str(exc))

    def save(self):
        from pathlib import Path

        path, _ = QFileDialog.getSaveFileName(self, "Save script", "", "Python (*.py)")
        if path:
            try:
                Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
            except OSError as exc:
                self.output.setPlainText(str(exc))

    def _ask_trust(self, path: str) -> bool:
        answer = QMessageBox.warning(
            self,
            "Run Script",
            f"This script was opened from:\n{path}\n\n"
            "Python scripts run with full access to your files and account. "
            "Run it only if you trust its author and have read the code.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return answer == QMessageBox.Yes

    def run(self):
        if self.untrusted_source is not None:
            if not self.confirm(self.untrusted_source):
                self.output.setPlainText("Not run. Project unchanged.")
                return
            self.untrusted_source = None
        try:
            project, output = run_script(self.editor.toPlainText(), self.document.project)
            self.document.edit("Python script", lambda p: p.__dict__.update(project.__dict__))
            self.output.setPlainText(output + "\nApplied. Ctrl+Z in the modeler to undo.")
        except (Exception, SystemExit) as exc:
            self.output.setPlainText(f"{type(exc).__name__}: {exc}\nProject unchanged.")
