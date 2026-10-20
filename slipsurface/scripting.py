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


TEMPLATE = """# Trusted Python: has access to your computer. Units: m, kN, kPa.
# Every Project field is available: geometry, materials, loads, supports,
# support_patterns, facing_types, facings, water_table, tension_crack, settings.
project = empty_project()
project.summary.title = "Scripted slope"
project.external = [[0,-10],[55,-10],[55,10],[35,10],[15,0],[0,0]]
project.materials = [MaterialSpec(name="Soil", model="MC", gamma=19, c=10, phi=30)]
project.support_types = [SupportType(name="Anchor", tensile=200)]
project.supports = [{"a":[25,5], "b":[38,1], "type":"Anchor"}]
project.loads = [{"kind":"distributed", "points":[[38,10],[48,10]],
                  "q":[15,15], "orientation":"vertical"}]
print("Project ready:", project.name)
"""
