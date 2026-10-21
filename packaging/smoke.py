"""Exercise real packaged resources and native libraries after installation."""

import json
import tempfile
from pathlib import Path


def smoke_test(output: Path) -> None:
    import ezdxf
    import qtawesome
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen.canvas import Canvas

    from slipsurface import __version__
    from slipsurface.geometry import CircularSurface
    from slipsurface.lem import analyze_circle
    from slipsurface.project import Project, acads_1a_project
    from slipsurface.report import pdf
    from slipsurface.ui.modeler import ModelerWindow

    app = QApplication.instance() or QApplication([])
    project = acads_1a_project()
    project.validate()
    result, _ = analyze_circle(
        project.build_geometry(), CircularSurface(20, 28, 28), project.build_materials()
    )
    if not result.ok or not 0.85 < result.fos < 1.10:
        raise RuntimeError(f"Packaged calculation failed: {result}")
    pdf._register_fonts()
    if pdf.F_REG != "SS3" or "SS3" not in pdfmetrics.getRegisteredFontNames():
        raise RuntimeError("Bundled report fonts are missing")
    if qtawesome.icon("fa5s.anchor").pixmap(32, 32).isNull():
        raise RuntimeError("Bundled QtAwesome fonts are missing")
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        project.save(folder / "model.slp.json")
        Project.load(folder / "model.slp.json").validate()
        drawing = ezdxf.new()
        drawing.modelspace().add_line((0, 0), (1, 1))
        drawing.saveas(folder / "model.dxf")
        if len(ezdxf.readfile(folder / "model.dxf").modelspace()) != 1:
            raise RuntimeError("DXF round trip failed")
        canvas = Canvas(str(folder / "report.pdf"))
        canvas.setFont("SS3", 12)
        canvas.drawString(50, 750, "Şev stabilitesi — SlipSurfaceIQ LE")
        canvas.save()
        if not (folder / "report.pdf").read_bytes().startswith(b"%PDF"):
            raise RuntimeError("PDF generation failed")
    window = ModelerWindow(project)
    window.show()
    # Import and construct the optional network panel in every native package.
    # No Ollama installation, model weights or network request is needed here.
    window.assistant_dock.show()
    if window.assistant.client.busy or window.assistant.share.isChecked():
        raise RuntimeError("Local assistant must start idle with project sharing disabled")
    QTimer.singleShot(1000, app.quit)
    app.exec()
    window.doc.mark_clean()
    window.close()
    output.write_text(
        json.dumps(
            {
                "version": __version__,
                "fos": result.fos,
                "qt_platform": app.platformName(),
                "checks": ["solver", "project", "dxf", "pdf", "fonts", "icons", "gui", "local_ai"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
