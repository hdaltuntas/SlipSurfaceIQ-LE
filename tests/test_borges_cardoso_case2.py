"""Borges & Cardoso (2002) Case 2 / SLOPE-W §2.18 regression tests.

These tests verify faithful *inputs*, a depth-dependent total-stress
strength law, real support-force mobilization and fixed-circle solvers.
The published search FoS (1.170/1.209/1.171) remains reference-only.
"""

import numpy as np
import pytest
from shapely.geometry import Point

from slipsurface.analysis import search_settings
from slipsurface.geometry import CircularSurface
from slipsurface.lem import analyze, make_slices
from slipsurface.lem.bishop import slice_strength
from slipsurface.materials import UndrainedDepth
from slipsurface.project import Project, borges_cardoso_case2_project, example_project

CIRCLE = CircularSurface(2.0, 7.0, 15.0)
FILE = "examples/borges_cardoso_case2.slp.json"
NAME = "Borges & Cardoso — geosynthetic embankment #2"


def test_case2_preset_roundtrip_and_materials(tmp_path):
    preset = borges_cardoso_case2_project()
    fixture = Project.load(FILE)
    from_menu = example_project(NAME)
    for p in (preset, fixture, from_menu):
        p.validate()
        assert p.groundwater.method == "none"
        assert p.water_table is None
        assert p.surfaces.surface_type == "circular"
        assert p.methods.methods == ["bishop", "janbu_simplified", "gle"]
        assert p.external == [
            [-30, -27],
            [45, -27],
            [45, 0],
            [42.5, 0],
            [36.41, 5],
            [6.15, 5],
            [0, 0],
            [-30, 0],
        ]
        assert p.material_boundaries == [
            [[0, 0], [42.5, 0]],
            [[-30, -1], [45, -1]],
            [[-30, -4.5], [45, -4.5]],
            [[-30, -7], [45, -7]],
        ]
        assert [m.model for m in p.materials] == ["MC", "UD", "UD", "UDG", "UDG"]
        assert [m.gamma for m in p.materials] == [20, 17, 17, 17, 17]
        assert [(m.su_top, m.su_bottom, m.su_y_top, m.su_y_bottom) for m in p.materials[3:]] == [
            (16, 18.4, -4.5, -7),
            (18.4, 55.1, -7, -27),
        ]
        st = p.support_types[0]
        assert st.kind == "geosynthetic"
        assert st.tensile == 200
        assert st.interface_friction == pytest.approx(33.7)
        assert st.adhesion == 0
        assert st.anchorage == "none"
        assert st.application == "passive"
        assert st.orientation == "parallel"
        assert p.supports == [{"a": [0, 0], "b": [42.5, 0], "type": st.name}]
    assert preset.analysis_inputs() == fixture.analysis_inputs()
    path = tmp_path / "case2.slp.json"
    preset.save(path)
    assert Project.load(path).analysis_inputs() == preset.analysis_inputs()


def test_case2_domain_material_zones_and_strengths():
    p = borges_cardoso_case2_project()
    g = p.build_geometry()
    assert len(g.regions) == 5
    for xy, material in [
        ((20, 2), "Embankment"),
        ((20, -0.5), "Clay 1"),
        ((20, -2), "Clay 2"),
        ((20, -5.5), "Clay 3"),
        ((20, -12), "Clay 4"),
    ]:
        assert [r.material for r in g.regions if r.polygon.contains(Point(xy))] == [material]
    assert sum(r.polygon.area for r in g.regions) == pytest.approx(g.domain.area)
    assert g.ground_y(-25) == 0
    assert g.ground_y(15) == 5


@pytest.mark.parametrize(
    "elevation,su",
    [(-4.5, 16), (-5.75, 17.2), (-7, 18.4), (-12, 27.575), (-27, 55.1)],
)
def test_depth_varying_undrained_strength_exact_at_elevations(elevation, su):
    p = borges_cardoso_case2_project()
    m = p.build_materials()
    mat = m["Clay 3"] if elevation >= -7 else m["Clay 4"]
    assert isinstance(mat, UndrainedDepth)
    c, friction = mat.strength(np.array([100.0]), y=np.array([elevation]))
    assert c[0] == pytest.approx(su, abs=1e-8)
    assert friction[0] == 0
    assert mat.total_stress


def test_depth_gradient_requires_elevation_and_valid_endpoints():
    p = borges_cardoso_case2_project()
    mat = p.build_materials()["Clay 4"]
    with pytest.raises(ValueError, match="elevation"):
        mat.strength(np.array([100]))
    p.materials[4].su_y_bottom = 0
    with pytest.raises(ValueError):
        p.validate()


def test_real_slices_use_depth_gradient_and_unanchored_geosynthetic():
    p = borges_cardoso_case2_project()
    g, m = p.build_geometry(), p.build_materials()
    s = make_slices(g, CIRCLE, m, opts=p.slice_options())
    assert s.n > 20
    np.testing.assert_array_equal(s.u, np.zeros(s.n))
    names = np.asarray([s.materials[i].name for i in s.mat_idx])
    assert "Clay 3" in names and "Clay 4" in names
    mask = names == "Clay 4"
    assert np.any(mask)
    i = int(np.flatnonzero(mask)[0])
    c, friction = slice_strength(s, i)
    expected = 18.4 + (55.1 - 18.4) * (-7 - s.y_base[i]) / 20
    assert c == pytest.approx(expected, abs=1e-9)
    assert friction == 0
    assert len(s.support_forces) == 1
    force = s.support_forces[0]
    assert force.T > 0
    assert force.T <= 200
    assert force.passive
    assert force.fx >= 0
    assert force.governing in ("çekme dayanımı", "sıyrılma (iç)", "sıyrılma (dış)")


@pytest.mark.parametrize("method", ["bishop", "janbu_simplified", "gle"])
def test_case2_fixed_diagnostic_circle_returns_finite_results(method):
    p = borges_cardoso_case2_project()
    r, s = analyze(
        p.build_geometry(),
        CIRCLE,
        p.build_materials(),
        method=method,
        opts=p.slice_options(),
        **p.solver_kw(),
    )
    assert s is not None, r.message
    assert r.ok, (method, r.message)
    assert np.isfinite(r.fos) and r.fos > 0


def test_case2_search_config_reproducible_and_water_free():
    p = borges_cardoso_case2_project()
    st = search_settings(p, "bishop")
    assert st.surface_type == "circular"
    assert st.seed == 0
    assert st.slice_opts.pore == "none"
    assert st.slice_opts.n_slices == 50
    assert len(st.slice_opts.loads.supports) == 1
