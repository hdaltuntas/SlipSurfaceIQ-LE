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


def test_tensile_roots_are_inadmissible_but_reference_paths_pass():
    """The base-tension admissibility guard separates spurious and real roots.

    The ACADS 3(a) unrestricted search used to stop at a Spencer root whose
    equilibrium required |N'| > c*l on interior slices (soil in tension).
    The prescribed 3(b) seam path, in contrast, only shows small trailing-
    edge tensions well within cohesion. Both must stay classified that way.
    """
    from slipsurface.lem import make_slices, spencer, solve_gle
    from slipsurface.geometry import PolylineSurface

    g, m = acads_3a_project().build_geometry(), acads_3a_project().build_materials()
    # a surface of the spurious family: dips below the seam to y ~ 20
    # (captured from the pre-guard 3(a) search result)
    surf_bad = PolylineSurface(
        [
            [46.106, 29.303],
            [49.829, 23.866],
            [52.435, 20.058],
            [55.536, 22.876],
            [58.236, 25.329],
            [61.022, 27.869],
            [63.740, 30.346],
            [66.769, 33.109],
            [69.626, 35.726],
            [70.433, 36.465],
            [74.292, 40.0],
        ]
    )
    s = make_slices(g, surf_bad, m, opts=acads_3a_project().slice_options())
    r = spencer(s, tol=1e-10)
    assert r.ok and not r.admissible, (r.fos, r.admissible, r.issue)
    assert "tension" in r.issue

    # the prescribed 3(b) path remains admissible for both solvers
    p3b = acads_3b_project()
    s2 = make_slices(
        g, PolylineSurface(p3b.surfaces.user_surface), m, opts=acads_3a_project().slice_options()
    )
    r2 = spencer(s2, tol=1e-10)
    assert r2.ok and r2.admissible, (r2.fos, r2.issue)
    rg = solve_gle(s2, interslice="half-sine", tol=1e-10)
    assert rg.ok and rg.admissible, (rg.fos, rg.issue)
