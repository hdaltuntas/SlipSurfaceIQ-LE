from pathlib import Path

import numpy as np
import pytest
import shapely

from slipsurface.analysis import report_text, run_analysis
from slipsurface.geometry import CircularSurface
from slipsurface.geometry.builder import boundary_geometry, upper_profile
from slipsurface.lem import analyze
from slipsurface.project import (
    EXAMPLES,
    MaterialSpec,
    Project,
    acads_1a_project,
    default_project,
    layered_example_project,
)

DATA = Path(__file__).parent / "data"


def test_json_roundtrip(tmp_path):
    for factory in EXAMPLES.values():
        p = factory()
        path = tmp_path / "m.slp.json"
        p.save(path)
        assert Project.load(path).to_dict() == p.to_dict()


def test_wrong_format_rejected():
    with pytest.raises(ValueError):
        Project.from_dict({"format": "other"})


def test_regions_partition_domain():
    g = layered_example_project().build_geometry()
    assert sum(r.polygon.area for r in g.regions) == pytest.approx(g.domain.area, rel=1e-9)
    polys = [r.polygon for r in g.regions]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            assert polys[i].intersection(polys[j]).area < 1e-9


def test_assignment_points():
    g = layered_example_project().build_geometry()

    def mat_at(x, y):
        for r in g.regions:
            if shapely.contains_xy(r.polygon, x, y):
                return r.material

    assert mat_at(60, 10) == "Fill"
    assert mat_at(60, 2) == "Soft clay"
    assert mat_at(60, -6) == "Weathered rock"
    assert mat_at(5, -0.65) == "Soft clay"  # clay top at x=5 is y≈-0.571
    assert mat_at(5, -0.50) == "Fill"  # unassigned sliver -> default (first) material


def test_material_line_snapped_to_boundary():
    """A line ending slightly short of the boundary still splits the region."""
    ext = [[0, -5], [40, -5], [40, 10], [25, 10], [10, 0], [0, 0]]
    g = boundary_geometry(ext, [[[0.03, -2], [39.95, -2]]], [(20, -4, "B")], "A")
    assert {r.material for r in g.regions} == {"A", "B"}
    b = sum(r.polygon.area for r in g.regions if r.material == "B")
    assert b == pytest.approx(40 * 3)


def test_upper_profile():
    poly = shapely.Polygon([[0, -5], [40, -5], [40, 10], [25, 10], [10, 0], [0, 0]])
    np.testing.assert_allclose(upper_profile(poly), [[0, 0], [10, 0], [25, 10], [40, 10]])


def test_validation_messages():
    p = default_project()
    p.assignments.append({"point": [1, 1], "material": "Yok"})
    with pytest.raises(ValueError, match="tanımlı değil"):
        p.build_geometry()
    p = default_project()
    p.materials[0].phi = 95
    with pytest.raises(ValueError):
        p.build_materials()
    with pytest.raises(ValueError, match="Dış sınır"):
        Project(materials=[MaterialSpec()]).build_geometry()


def test_project_matches_direct_api():
    p = acads_1a_project()
    res, _ = analyze(
        p.build_geometry(), CircularSurface(20, 28, 28), p.build_materials(), opts=p.slice_options()
    )
    assert res.fos == pytest.approx(0.9855, abs=2e-3)


def test_v1_file_is_converted():
    p = Project.load(DATA / "v1_katmanli.slp.json")
    q = layered_example_project()
    g1, g2 = p.build_geometry(), q.build_geometry()
    assert g1.domain.area == pytest.approx(g2.domain.area)
    # the legacy v1 file keeps its original (Turkish) material names
    for m1, m2 in (
        ("Dolgu", "Fill"),
        ("Yumuşak kil", "Soft clay"),
        ("Ayrışmış kaya", "Weathered rock"),
    ):
        a1 = sum(r.polygon.area for r in g1.regions if r.material == m1)
        a2 = sum(r.polygon.area for r in g2.regions if r.material == m2)
        assert a1 == pytest.approx(a2, rel=1e-6), m2


def test_run_analysis_multiple_methods():
    p = acads_1a_project()
    p.methods.methods = ["bishop", "spencer", "janbu_simplified"]
    p.surfaces.effort = "fast"
    r = run_analysis(p)
    assert set(r.results) == {"bishop", "spencer", "janbu_simplified"}
    assert r.results["bishop"].fos == pytest.approx(0.987, abs=0.015)
    assert r.results["spencer"].fos == pytest.approx(0.986, abs=0.015)
    assert r.results["janbu_simplified"].fos < r.results["bishop"].fos
    txt = report_text(r)
    assert "Global minimum" in txt and "Spencer" in txt


def test_user_defined_surface():
    p = acads_1a_project()
    p.surfaces.surface_type = "user"
    xs = np.linspace(20, 41.4476, 25)
    c = CircularSurface(20, 28, 28)
    p.surfaces.user_surface = np.column_stack([xs, c.y(xs)]).tolist()
    p.methods.methods = ["bishop", "spencer"]
    r = run_analysis(p)
    assert "bishop" in r.errors and r.results["spencer"].fos == pytest.approx(0.985, abs=0.02)
