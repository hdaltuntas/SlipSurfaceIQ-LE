"""Layer-based, metre-based 2D DXF geometry exchange."""

from pathlib import Path

import ezdxf
from ezdxf import units
from ezdxf.path import make_path

from slipsurface.project import Project, empty_project


def export_dxf(project: Project, path: str | Path) -> None:
    if not project.has_geometry:
        raise ValueError("Draw an external boundary before exporting.")
    doc = ezdxf.new("R2010")
    doc.units = units.M
    space = doc.modelspace()

    def poly(layer, points, closed=False):
        if points:
            if layer not in doc.layers:
                doc.layers.new(layer)
            space.add_lwpolyline(points, close=closed, dxfattribs={"layer": layer})

    poly("SS_EXTERNAL", project.external, True)
    for points in project.material_boundaries:
        poly("SS_MATERIAL", points)
    poly("SS_WATER", project.water_table)
    poly("SS_CRACK", project.tension_crack)
    poly("SS_SURFACE", project.surfaces.user_surface)
    for support in project.supports:
        poly("SS_SUPPORT", [support["a"], support["b"]])
    doc.saveas(path)


def import_dxf(path: str | Path) -> tuple[Project, list[str]]:
    """Import polylines/lines; flatten arcs to 1 cm tolerance; reject ambiguity."""
    doc = ezdxf.readfile(path)
    factor = units.conversion_factor(doc.units, units.M) if doc.units else 1.0
    warnings = [] if doc.units else ["DXF has no units; coordinates interpreted as metres."]
    project = empty_project()
    project.summary.title = Path(path).stem
    external = []
    ignored = set()
    for entity in doc.modelspace():
        kind = entity.dxftype()
        if kind not in ("LWPOLYLINE", "POLYLINE", "LINE", "ARC", "SPLINE"):
            ignored.add(kind)
            continue
        path_entity = make_path(entity)
        vertices = list(path_entity.flattening(0.01 / factor))
        if any(abs(v.z) > 1e-8 for v in vertices):
            raise ValueError("Only planar XY geometry at Z=0 is supported.")
        points = [[v.x * factor, v.y * factor] for v in vertices]
        closed = path_entity.is_closed
        if closed and points and points[0] == points[-1]:
            points.pop()
        layer = entity.dxf.layer.upper()
        if layer == "SS_EXTERNAL" or (closed and layer == "0"):
            if not closed:
                raise ValueError("SS_EXTERNAL must be a closed polyline.")
            external.append(points)
        elif layer == "SS_MATERIAL":
            project.material_boundaries.append(points)
        elif layer in ("SS_WATER", "SS_CRACK", "SS_SURFACE"):
            target = {
                "SS_WATER": "water_table",
                "SS_CRACK": "tension_crack",
                "SS_SURFACE": "user_surface",
            }[layer]
            owner = project.surfaces if layer == "SS_SURFACE" else project
            if getattr(owner, target):
                raise ValueError(f"Multiple entities on {layer}; join them before importing.")
            setattr(owner, target, points)
        else:
            ignored.add(f"{kind} / {layer}")
    if len(external) != 1:
        raise ValueError("DXF needs exactly one closed SS_EXTERNAL (or layer 0) boundary.")
    project.external = external[0]
    project.build_geometry()
    if ignored:
        warnings.append("Skipped entities/layers: " + ", ".join(sorted(ignored)))
    warnings.append("DXF transfers geometry only. Assign materials, loads and supports separately.")
    return project, warnings
