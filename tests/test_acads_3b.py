"""ACADS 3(b) fixed path distinguishes solver behaviour from 3(a) search."""

import pytest

from slipsurface.project import Project, acads_3a_project, acads_3b_project, example_project

NAME = "ACADS 3(b) — weak seam specified path"
PATH = "examples/acads_3b.slp.json"
POINTS = [[41.85, 27.75], [44.0, 26.5], [63.5, 27.0], [73.31, 40.0]]


def test_acads_3b_fixed_path_is_not_a_3a_optimizer_result():
    a = acads_3a_project()
    b = acads_3b_project()
    saved = Project.load(PATH)
    menu = example_project(NAME)
    for p in (b, saved, menu):
        p.validate()
        assert p.surfaces.surface_type == "user"
        assert p.surfaces.user_surface == POINTS
        assert p.groundwater.method == "water_table"
        assert p.methods.methods == ["spencer", "gle"]
        assert p.external == a.external
        assert p.material_boundaries == a.material_boundaries
        assert p.water_table == a.water_table
    assert saved.analysis_inputs() == b.analysis_inputs()
    assert a.surfaces.surface_type == "noncircular"
    assert a.surfaces.user_surface is None
    assert b.analysis_inputs() != a.analysis_inputs()


def test_acads_3b_really_solves_prescribed_path():
    from slipsurface.analysis import run_analysis

    result = run_analysis(acads_3b_project())
    assert not result.errors, result.errors
    for method in ("spencer", "gle"):
        solution = result.results[method]
        assert solution.lem.ok, (method, solution.lem.message)
        assert solution.n_evals == 1
        assert solution.slices.n > 20
        assert solution.fos == pytest.approx(1.26, abs=0.12)
