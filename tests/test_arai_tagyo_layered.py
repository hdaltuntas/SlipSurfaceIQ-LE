"""Arai & Tagyo (1985), example 2: Slide2 VP15 layered-slope input checks.

Bentley verification manual section 3.4: circular 0.421/0.410/0.424
(Bishop/Janbu simplified/Spencer), noncircular Janbu 0.394,
Spencer 0.412. Those are *search minima*, not fixed-circle solutions.
"""

from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Point

from slipsurface.analysis import search_settings
from slipsurface.lem import analyze, make_slices
from slipsurface.optimizer import circle_from_chord
from slipsurface.project import Project
from tests.models import arai_tagyo_layered_circular_project, arai_tagyo_layered_noncircular_project

EXAMPLES = [
    (
        "Arai & Tagyo — layered (circular)",
        "arai_tagyo_layered_circular.slp.json",
        "circular",
        ["bishop", "janbu_simplified", "spencer"],
    ),
    (
        "Arai & Tagyo — layered (noncircular)",
        "arai_tagyo_layered_noncircular.slp.json",
        "noncircular",
        ["janbu_simplified", "spencer"],
    ),
]
OUTER = [
    [0, 3],
    [96, 3],
    [96, 35],
    [72, 35],
    [48, 35],
    [24, 19],
    [18, 15],
    [0, 15],
]
BOUNDARIES = [[[24, 19], [72, 35]], [[0, 3], [96, 35]]]


@pytest.mark.parametrize("name,filename,kind,methods", EXAMPLES)
def test_saved_fixture_matches_preset(name, filename, kind, methods, tmp_path):
    make = (
        arai_tagyo_layered_circular_project
        if kind == "circular"
        else arai_tagyo_layered_noncircular_project
    )
    preset = make()
    saved = Project.load(Path(__file__).parent / "data" / filename)
    for p in (preset, saved):
        p.validate()
        assert p.external == OUTER
        assert p.material_boundaries == BOUNDARIES
        assert p.water_table is None
        assert p.groundwater.method == "none"
        assert p.tension_crack is None
        assert p.surfaces.surface_type == kind
        assert p.methods.methods == methods
        assert p.general.failure_direction == "right_to_left"
        assert p.methods.n_slices == 50
        assert [(m.name, m.c, m.phi, m.gamma) for m in p.materials] == [
            ("Upper Layer", 29.4, 12.0, 18.82),
            ("Middle Layer", 9.8, 5.0, 18.82),
            ("Lower Layer", 294.0, 40.0, 18.82),
        ]
    assert preset.analysis_inputs() == saved.analysis_inputs()
    path = tmp_path / filename
    preset.save(path)
    assert Project.load(path).analysis_inputs() == preset.analysis_inputs()


def test_arai_tagyo_geometry_has_three_zones_of_correct_area_and_strength():
    g = arai_tagyo_layered_circular_project().build_geometry()
    assert g.domain.area == pytest.approx(2412)
    assert len(g.regions) == 3
    assert sum(r.polygon.area for r in g.regions) == pytest.approx(2412)
    by_name = {r.material: r.polygon.area for r in g.regions}
    assert by_name == pytest.approx(
        {
            "Upper Layer": 192,
            "Middle Layer": 684,
            "Lower Layer": 1536,
        }
    )
    for point, name in [
        ((48, 31), "Upper Layer"),
        ((48, 24), "Middle Layer"),
        ((48, 12), "Lower Layer"),
    ]:
        assert [r.material for r in g.regions if r.polygon.contains(Point(point))] == [name]
    np.testing.assert_allclose(
        g.ground_y(np.array([0, 18, 24, 48, 72, 96])), [15, 15, 19, 35, 35, 35]
    )


def test_arai_tagyo_dry_slice_material_assignment_and_method_solving():
    p = arai_tagyo_layered_circular_project()
    geom, materials = p.build_geometry(), p.build_materials()
    circle = circle_from_chord(geom, 18, 60, np.deg2rad(22))
    slices = make_slices(geom, circle, materials, opts=p.slice_options())
    assert slices.n >= 30
    np.testing.assert_array_equal(slices.u, np.zeros(slices.n))
    base = {slices.materials[i].name for i in slices.mat_idx}
    assert "Middle Layer" in base
    assert np.isfinite(slices.W).all() and (slices.W > 0).all()

    for method in ["bishop", "janbu_simplified", "spencer"]:
        result, reslices = analyze(
            geom, circle, materials, method=method, opts=p.slice_options(), **p.solver_kw()
        )
        assert reslices is not None, (method, result.message)
        assert result.ok, (method, result.message)
        assert np.isfinite(result.fos)
        assert 0 < result.fos < 3
        # A fixed diagnostic circle does not represent the reference's
        # *optimized* circular minimum; only input and solver mechanics
        # are checked here.


def test_arai_tagyo_search_settings_are_distinct_and_reproducible():
    circ = arai_tagyo_layered_circular_project()
    non = arai_tagyo_layered_noncircular_project()
    assert circ.external == non.external
    assert circ.material_boundaries == non.material_boundaries
    assert circ.groundwater.method == non.groundwater.method == "none"
    circular_search = search_settings(circ, "bishop")
    non_search = search_settings(non, "spencer")
    assert circular_search.surface_type == "circular"
    assert non_search.surface_type == "polyline"
    assert circular_search.n_slices == non_search.n_slices == 50
    assert circular_search.seed == non_search.seed == 0
    assert non_search.n_ctrl == 4
    assert non_search.maxiter >= circular_search.maxiter
    assert "bishop" not in non.methods.methods
