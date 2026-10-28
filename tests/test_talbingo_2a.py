"""ACADS Talbingo 2(a) and 2(b) are different verification exercises."""

import math
from pathlib import Path

import pytest

from slipsurface.project import Project, acads_2a_project, acads_2b_project, example_project

FIXTURE = Path(__file__).parents[1] / "examples" / "acads_2a.slp.json"
NAME = "ACADS 2(a) — Talbingo critical upstream search"


def test_talbingo_2a_is_not_the_prescribed_circle_in_2b():
    a = acads_2a_project()
    b = acads_2b_project()
    saved = Project.load(FIXTURE)
    menu = example_project(NAME)
    for p in (a, saved, menu):
        p.validate()
        assert p.surfaces.surface_type == "circular"
        assert p.surfaces.user_circle is None
        assert p.surfaces.left_range == [0, 315.4]
        assert p.surfaces.right_range == [0.1, 315.5]
        assert p.groundwater.method == "none"
        assert p.methods.methods == ["bishop", "janbu_simplified", "spencer", "gle"]
        assert p.surfaces.seed == 0
        assert p.surfaces.effort == "fine"
        assert p.external == b.external
        assert p.material_boundaries == b.material_boundaries
    assert saved.analysis_inputs() == a.analysis_inputs()
    assert b.surfaces.surface_type == "user"
    assert b.surfaces.user_circle == [100.3, 291.0, 278.8]
    assert a.analysis_inputs() != b.analysis_inputs()


def test_talbingo_upstream_infinite_slope_reference_independent_of_solver():
    # Upstream rockfill: tan(phi)=1 and tan(beta)=162/315.5.
    # This is the limiting mechanism for ACADS 2(a), NOT the 2(b) fixed circle.
    p = acads_2a_project()
    assert (p.materials[0].c, p.materials[0].phi) == (0, 45)
    beta = math.atan2(162, 315.5)
    f_limit = math.tan(math.radians(45)) / math.tan(beta)
    assert f_limit == pytest.approx(315.5 / 162, rel=1e-12)
    assert f_limit == pytest.approx(1.951, abs=0.006)
