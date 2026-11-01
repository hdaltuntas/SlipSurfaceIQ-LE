"""Trusted local Python scripts, evaluated against an isolated project copy."""

import contextlib
import io

from slipsurface.loads import FacingType, SupportType
from slipsurface.project import MaterialSpec, Project, empty_project


def run_script(source: str, project: Project) -> tuple[Project, str]:
    candidate = project.copy()
    namespace = {
        "project": candidate,
        "Project": Project,
        "MaterialSpec": MaterialSpec,
        "SupportType": SupportType,
        "FacingType": FacingType,
        "empty_project": empty_project,
    }
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exec(compile(source, "<project-script>", "exec"), namespace)
    candidate = namespace["project"]
    if not isinstance(candidate, Project):
        raise ValueError("project must be a Project instance")
    candidate.validate()
    candidate.build_geometry()
    return candidate, output.getvalue()
