from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QVBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
)

from slipsurface.ui import guides
from slipsurface.ui.preferences import fit_to_screen
from slipsurface.scripting import run_script

TUTORIAL = guides.SCRIPTING_TUTORIAL


def open_tutorial(parent=None) -> bool:
    """Open the scripting tutorial PDF in the system viewer."""
    return guides.open_guide(TUTORIAL, parent)


class ScriptDialog(QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle("Python scripting")
        fit_to_screen(self, 960, 720)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Scripts change a copy of the model; the result is validated and applied as "
                "one undoable operation. Units: m, kN, kPa.\n"
                "Restricted mode (default): no file access and no imports except math and "
                "the slipsurface model classes."
            )
        )
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "# Write a Python script here, or Open .py.\n"
            "# Example:  project.seismic.kh = 0.1\n"
            "# Every command is explained in the Tutorial (PDF)."
        )
        # Text of a script opened from a file that the user has not yet
        # confirmed as trusted; cleared after the first confirmation.
        self.untrusted_source: str | None = None
        self.confirm = self._ask_trust
        self.editor.setStyleSheet("font-family: Consolas; font-size: 13px;")
        layout.addWidget(self.editor, 3)
        self.full_access = QCheckBox(
            "Full Python access (any import, files, network) — only for scripts you trust"
        )
        self.full_access.setToolTip(
            "Off: the script is checked first and refused if it imports other modules, "
            "opens files or uses exec/eval or names starting with an underscore.\n"
            "On: the script runs as ordinary Python with your account permissions."
        )
        layout.addWidget(self.full_access)
        self._full_access_confirmed = False
        self.confirm_full = self._ask_full_access
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        buttons = QHBoxLayout()
        for title, slot in (
            ("Open .py", self.load),
            ("Save .py", self.save),
            ("Run / Apply", self.run),
            ("Tutorial (PDF)", lambda: open_tutorial(self)),
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
                self._full_access_confirmed = False  # another script: ask again
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
            "It changes the open model. With 'Full Python access' ticked it also runs "
            "with full access to your files and account.\n"
            "Run it only if you trust its author and have read the code.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return answer == QMessageBox.Yes

    def _ask_full_access(self) -> bool:
        answer = QMessageBox.warning(
            self,
            "Full Python Access",
            "The script will run as ordinary Python: it can read, change and delete your "
            "files and use the network.\n\nRun it only if you wrote it or have read it.",
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
        trusted = self.full_access.isChecked()
        if trusted and not self._full_access_confirmed:
            if not self.confirm_full():
                self.output.setPlainText("Not run. Project unchanged.")
                return
            self._full_access_confirmed = True
        try:
            project, output = run_script(
                self.editor.toPlainText(), self.document.project, trusted=trusted
            )
            changed = self.document.edit(
                "Python script", lambda p: p.__dict__.update(project.__dict__)
            )
            self.output.setPlainText(
                output
                + (
                    "\nApplied. Ctrl+Z in the modeler to undo."
                    if changed
                    else "\nThe script ran; the project is unchanged."
                )
            )
        except (Exception, SystemExit) as exc:
            self.output.setPlainText(f"{type(exc).__name__}: {exc}\nProject unchanged.")
