"""ACADS 3(a) / VS_7: weak seam + phreatic line verification.

The published minimum (ACADS 1.26; Slide2 Spencer 1.258, GLE 1.246)
is a SEARCH result. A fixed ACADS 3(b) control surface is tested only
for slicing and solver integrity; it is not misreported as that minimum.
"""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Point

from slipsurface.geometry import PolylineSurface
from slipsurface.lem import analyze, make_slices
from slipsurface.project import Project, acads_3a_project, example_project

FIXTURE = Path(__file__).parents[1] / "examples" / "acads_3a.slp.json"
CONTROL_3B = [[41.85, 27.75], [44.0, 26.5], [63.5, 27.0], [73.31, 40.0]]


def test_acads_3a_preset_matches_saved_project():
    preset = acads_3a_project()
    saved = Project.load(FIXTURE)

    for p in (preset, saved, example_project("ACADS 3(a) — weak seam + water table")):
        p.validate()
        assert p.external == [
            [20, 20],
            [84, 20],
            [84, 40],
            [67.5, 40],
            [43, 27.75],
            [20, 27.75],
        ]
        assert p.material_boundaries == [
            [[20, 27.0], [84, 27.0]],
            [[20, 26.5], [84, 26.5]],
        ]
        assert p.water_table == [[20, 26.5], [84, 26.5]]
        assert p.tension_crack is None
        assert [(m.gamma, m.gamma_sat, m.c, m.phi) for m in p.materials] == [
            (18.84, 18.84, 28.5, 20.0),
            (18.84, 18.84, 0.0, 10.0),
        ]
        assert p.groundwater.method == "water_table"
        assert p.groundwater.gamma_w == pytest.approx(9.81)
        assert p.general.failure_direction == "right_to_left"
        assert p.surfaces.surface_type == "noncircular"
        assert p.surfaces.noncircular_shape == "polyline"
        assert p.methods.methods == ["spencer", "gle"]
        assert p.methods.interslice == "half-sine"

    assert preset.analysis_inputs() == saved.analysis_inputs()


def test_acads_3a_seam_is_a_real_region_not_a_drawn_line():
    p = acads_3a_project()
    g = p.build_geometry()

    assert g.domain.area == pytest.approx(848.1875)
    assert len(g.regions) == 3
    assert sorted(r.polygon.area for r in g.regions) == pytest.approx(
        [32.0, 400.1875, 416.0]
    )
    for point, expected in [
        ((60, 32), "Soil 1"),
        ((60, 26.75), "Soil 2"),
        ((60, 23), "Soil 1"),
    ]:
        matches = [r.material for r in g.regions if r.polygon.contains(Point(point))]
        assert matches == [expected]

    np.testing.assert_allclose(g.water_y(np.array([20, 43, 67.5, 84])), 26.5)
    np.testing.assert_allclose(g.ground_y(np.array([20, 43, 67.5, 84])),
                               [27.75, 27.75, 40.0, 40.0])


def test_acads_3a_control_surface_intersects_weak_seam():
    p = acads_3a_project()
    g, mats = p.build_geometry(), p.build_materials()
    s = make_slices(g, PolylineSurface(CONTROL_3B), mats, opts=p.slice_options())
    base_mats = [s.materials[i].name for i in s.mat_idx]

    assert s.n > 10
    assert "Soil 2" in base_mats
    assert s.x_exit == pytest.approx(41.85, abs=0.05)
    assert s.x_entry == pytest.approx(73.31, abs=0.05)
    assert np.all(s.u >= 0.0)


def test_acads_3a_groundwater_is_positive_only_below_phreatic_line():
    p = acads_3a_project()
    g, mats = p.build_geometry(), p.build_materials()
    # This diagnostic trial surface cuts below the water table: ACADS 3(b)
    # happens to run at/above the water elevation along its weak seam.
    trial = PolylineSurface(
        [[41.85, 27.75], [44, 26.0], [63.5, 26.0], [73.31, 40.0]]
    )
    wet = make_slices(g, trial, mats, opts=p.slice_options())
    dry = make_slices(
        g, trial, mats, opts=replace(p.slice_options(), pore="none")
    )

    assert np.any(wet.u > 0)
    np.testing.assert_allclose(
        wet.u, 9.81 * np.maximum(26.5 - wet.y_base, 0.0), rtol=0, atol=1e-9
    )
    np.testing.assert_array_equal(dry.u, np.zeros_like(dry.u))
    np.testing.assert_allclose(wet.W, dry.W, rtol=1e-12, atol=1e-8)


@pytest.mark.parametrize("method", ["spencer", "gle"])
def test_acads_3a_fixed_diagnostic_surface_converges(method):
    p = acads_3a_project()
    result, slices = analyze(
        p.build_geometry(),
        PolylineSurface(CONTROL_3B),
        p.build_materials(),
        method=method,
        opts=p.slice_options(),
        **p.solver_kw(),
    )
    assert slices is not None
    assert result.ok, result.message
    assert np.isfinite(result.fos)
    # Diagnostic only: ACADS 3(b) uses a SPECIFIED surface, while ACADS
    # 3(a) reference FoS=1.26 is a separate OPTIMIZED non-circular search.
    assert 0.9 < result.fos < 1.6
