"""LE-3 regression tests: LEM solver convergence guarantees, equilibrium residuals,
slice mechanics recording, mirrored weak-seam search seeding, and boundary edge cases."""

from __future__ import annotations

import numpy as np
import pytest

from slipsurface.analysis import AnalysisResults
from slipsurface.geometry import CircularSurface, PolylineSurface, simple_slope
from slipsurface.lem import (
    LEMResult,
    SliceOptions,
    SlicingError,
    bishop_simplified,
    janbu_corrected,
    janbu_simplified,
    make_slices,
    morgenstern_price,
    ordinary,
    spencer,
)
from slipsurface.loads import (
    LineLoad,
    LoadSet,
    Support,
    SupportType,
    TensionCrack,
    pattern_positions,
)
from slipsurface.materials import HoekBrown, MohrCoulomb
from slipsurface.optimizer import SearchResult, SearchSettings, search, search_circular
from slipsurface.optimizer.search import _boundary_seeds
from slipsurface.project import MaterialSpec, Project, acads_1a_project


def _geom_from_ext(external, material="Soil", boundaries=None, assignments=None):
    p = Project(
        materials=[MaterialSpec(name=material)],
        external=external,
        material_boundaries=boundaries or [],
        assignments=assignments or [],
    )
    return p.build_geometry()


def _simple_slices():
    p = acads_1a_project()
    geom = p.build_geometry()
    mats = p.build_materials()
    surf = CircularSurface(26.0, 28.0, 26.0)
    return geom, mats, surf, make_slices(geom, surf, mats, opts=p.slice_options())


def test_unconverged_solvers_never_return_finite_fos_fallback():
    geom, _mats, surf, s = _simple_slices()
    geom_hb = simple_slope(
        height=10.0, ratio_h_to_v=2.0, toe_x=20.0, left_bench=20.0, right_bench=20.0, material="HB"
    )
    s_hb = make_slices(
        geom_hb,
        surf,
        {"HB": HoekBrown(name="HB", gamma=24.0, sigma_ci=25000.0, gsi=45.0, mi=10.0)},
        n_slices=30,
    )

    r_b = bishop_simplified(s, max_iter=1, f0=8.0, tol=1e-12)
    assert not r_b.converged and not r_b.ok and np.isnan(r_b.fos)

    r_sp = spencer(s_hb, max_outer=1, tol=1e-12)
    assert not r_sp.converged and not r_sp.ok and np.isnan(r_sp.fos)

    r_j = janbu_simplified(s_hb, max_outer=1, tol=1e-12)
    assert not r_j.converged and not r_j.ok and np.isnan(r_j.fos)

    # AnalysisResults.global_minimum must ignore any entry where lem.ok is False
    ar = AnalysisResults(
        acads_1a_project(),
        geom,
        results={
            "bishop": SearchResult(surf, 0.50, LEMResult(0.50, "Bishop", False, 1), s, 1),
            "spencer": SearchResult(surf, 1.25, LEMResult(1.25, "Spencer", True, 4), s, 1),
        },
    )
    gm = ar.global_minimum()
    assert gm is not None and gm[0] == "spencer"


def test_nonlinear_bishop_does_not_exit_prematurely_on_iteration_one():
    geom_hb = simple_slope(
        height=10.0, ratio_h_to_v=2.0, toe_x=20.0, left_bench=20.0, right_bench=20.0, material="HB"
    )
    mats = {"HB": HoekBrown(name="HB", gamma=25.0, sigma_ci=20000.0, gsi=40.0, mi=12.0)}
    surf = CircularSurface(26.0, 26.0, 24.0)
    s = make_slices(geom_hb, surf, mats, n_slices=30)

    tight = bishop_simplified(s, tol=1e-10, max_iter=100)
    assert tight.ok

    # Seed f0 right at the iteration-1 initial-stress fixed point
    from slipsurface.lem.bishop import _driving_moment_over_R, _initial_sigma_n, _strength

    c0, tp0 = _strength(s, _initial_sigma_n(s))
    f_init = 1.5
    for _ in range(30):
        ma = np.cos(s.alpha) + np.sin(s.alpha) * tp0 / f_init
        f_init = float(np.sum((c0 * s.b + s.Wv * tp0) / ma) / _driving_moment_over_R(s, f_init))

    res = bishop_simplified(s, f0=f_init, tol=1e-3, max_iter=100)
    assert res.ok
    assert res.iterations >= 2
    assert res.fos == pytest.approx(tight.fos, rel=2e-3)


def test_tangent_support_at_surface_endpoint_and_negative_pattern_offset():
    geom = simple_slope(
        height=10.0,
        ratio_h_to_v=2.0,
        toe_x=20.0,
        left_bench=20.0,
        right_bench=20.0,
        material="Soil",
    )
    mats = {"Soil": MohrCoulomb(name="Soil", gamma=19.0, c=10.0, phi=28.0)}
    # Polyline slip surface starting at x=18, y=0 where surf.y(18 - 1e-5) is NaN!
    surf = PolylineSurface([[18.0, 0.0], [28.0, -3.0], [45.0, 10.0]])
    st = SupportType(
        name="Sheet",
        kind="end_anchored",
        tensile=150.0,
        spacing=1.5,
        orientation="tangent",
        application="active",
    )
    ls = LoadSet(supports=[Support((18.0, 0.5), (18.0, -4.0), st)])
    s = make_slices(geom, surf, mats, opts=SliceOptions(n_slices=25, pore="none", loads=ls))
    assert len(s.support_forces) == 1
    assert np.all(np.isfinite(s.Qx_a)) and np.all(np.isfinite(s.Qy_a))
    res = spencer(s)
    assert res.ok

    with pytest.raises(ValueError, match="offset"):
        pattern_positions(geom, 20.0, 40.0, spacing=2.0, offset=-0.5)


def test_mirrored_weak_seam_boundary_seeds_immutability_and_high_fos_ceiling():
    mats = [
        MaterialSpec("Upper", "MC", 19, 20, False, 20, 32),
        MaterialSpec("Seam", "MC", 18, 19, False, 0, 10),
        MaterialSpec("Base", "MC", 22, 22, False, 50, 40),
    ]
    ext_rtl = [[0, -10], [70, -10], [70, 12], [45, 12], [25, 0], [0, 0]]
    mb_rtl = [[[0, -2], [70, -1]], [[0, -3], [70, -2]]]
    assign_rtl = [
        {"point": [50.0, 5.0], "material": "Upper"},
        {"point": [35.0, -2.0], "material": "Seam"},
        {"point": [35.0, -6.0], "material": "Base"},
    ]
    p_rtl = Project(
        materials=mats, external=ext_rtl, material_boundaries=mb_rtl, assignments=assign_rtl
    )
    g_rtl = p_rtl.build_geometry()

    ext_ltr = [[70 - x, y] for x, y in reversed(ext_rtl)]
    mb_ltr = [[[70 - x, y] for x, y in reversed(b)] for b in mb_rtl]
    assign_ltr = [
        {"point": [70 - a["point"][0], a["point"][1]], "material": a["material"]}
        for a in assign_rtl
    ]
    p_ltr = Project(
        materials=mats, external=ext_ltr, material_boundaries=mb_ltr, assignments=assign_ltr
    )
    g_ltr = p_ltr.build_geometry()

    st = SearchSettings(method="spencer", surface_type="polyline", n_ctrl=4)
    lo = np.array([0.0, 0.0] + [0.0] * 4)
    hi = np.array([70.0, 70.0] + [1.0] * 4)
    seeds_rtl = _boundary_seeds(g_rtl, st, lo, hi)
    seeds_ltr = _boundary_seeds(g_ltr, st, lo, hi)
    assert len(seeds_rtl) > 0
    assert len(seeds_ltr) == len(seeds_rtl)

    # search_circular must not mutate caller's SearchSettings
    caller_st = SearchSettings(method="bishop", surface_type="polyline", popsize=6, maxiter=5)
    g1 = acads_1a_project().build_geometry()
    m1 = acads_1a_project().build_materials()
    _ = search_circular(g1, m1, caller_st)
    assert caller_st.surface_type == "polyline"

    # Very strong intact rock mass with true FoS > 1000 must not fail PENALTY = 1000 check
    rock = {"Rock": MohrCoulomb(name="Rock", gamma=25.0, c=60000.0, phi=45.0)}
    g_rock = simple_slope(
        height=10.0,
        ratio_h_to_v=2.0,
        toe_x=20.0,
        left_bench=20.0,
        right_bench=20.0,
        material="Rock",
    )
    res_high = search(
        g_rock,
        rock,
        SearchSettings(method="bishop", surface_type="circular", popsize=8, maxiter=10, seed=1),
    )
    assert res_high.lem.ok and res_high.fos > 1000.0


def test_hump_above_ground_tension_crack_forced_dir_and_flat_load_direction():
    mats = {"Soil": MohrCoulomb(name="Soil", gamma=19.0, c=15.0, phi=30.0)}
    # 1) Narrow ground V-notch rising below a polyline slip surface inside the mass
    geom_notch = _geom_from_ext(
        [
            [0, -10],
            [50, -10],
            [50, 10],
            [35, 10],
            [25.02, 2.0],
            [25.01, -2.5],
            [25.0, -2.5],
            [24.99, 2.0],
            [15, 0],
            [0, 0],
        ]
    )
    bad_surf = PolylineSurface([[10.0, 0.0], [25.005, -2.0], [42.0, 10.0]])
    with pytest.raises(SlicingError):
        make_slices(geom_notch, bad_surf, mats, opts=SliceOptions(pore="none"))

    # 2) Slope with a local toe flood-berm where ground_y(x_exit) > ground_y(x_entry) locally,
    #    with forced direction="right_to_left" and right-side crest tension crack
    geom_berm = _geom_from_ext(
        [[0, -10], [60, -10], [60, 10], [40, 10], [20, 0], [12, 11.0], [8, 0], [0, 0]]
    )
    tc = TensionCrack([[38.0, 7.5], [58.0, 7.5]], water=0.5)
    arc = CircularSurface(28.0, 26.0, 22.0)
    s_tc = make_slices(
        geom_berm,
        arc,
        mats,
        opts=SliceOptions(pore="none", direction="right_to_left", crack=tc),
    )
    assert s_tc.crack is not None and s_tc.crack["uphill_right"] is True

    # 3) Flat ground (y = 10 everywhere) + symmetric circle + horizontal LineLoad pushing +x
    geom_flat = _geom_from_ext([[0, 0], [40, 0], [40, 10], [0, 10]])
    sym_circle = CircularSurface(20.0, 15.0, 10.0)
    horiz_load = LoadSet(line=[LineLoad(x=15.0, y=10.0, magnitude=200.0, angle=0.0)])
    s_flat = make_slices(
        geom_flat,
        sym_circle,
        mats,
        opts=SliceOptions(pore="none", direction="auto", loads=horiz_load),
    )
    assert s_flat.direction == 1
    assert bishop_simplified(s_flat).ok


def test_lem_result_records_equilibrium_residuals_and_mirrored_slice_forces():
    _geom, _mats, _surf, s = _simple_slices()

    rb = bishop_simplified(s)
    rj = janbu_simplified(s)
    rjc = janbu_corrected(s)
    rsp = spencer(s)
    rgle = morgenstern_price(s)
    ro = ordinary(s)

    assert rb.ok and abs(rb.moment_residual) < 1e-6
    assert rb.base_normal_eff is not None and len(rb.base_normal_eff) == s.n
    assert rb.base_shear_mob is not None and len(rb.base_shear_mob) == s.n

    assert rj.ok and abs(rj.force_residual) < 1e-6
    assert rjc.ok and rjc.janbu_f0 > 1.0

    for r in (rsp, rgle):
        assert r.ok
        assert abs(r.force_residual) < 1e-7
        assert abs(r.moment_residual) < 1e-7
        assert r.base_normal_eff is not None and len(r.base_normal_eff) == s.n
        assert r.interslice_E is not None and len(r.interslice_E) == s.n + 1
        assert r.interslice_X is not None and len(r.interslice_X) == s.n + 1
        assert abs(r.interslice_E[0]) < 1e-9 and abs(r.interslice_E[-1]) < 1e-5

    assert ro.ok and ro.base_normal_eff is not None and len(ro.base_normal_eff) == s.n

    # Mirrored left-to-right slope must map base_normal_eff back to left-to-right slice order 0..n-1
    p_rtl = acads_1a_project()
    L = 60.0
    p_ltr = p_rtl.copy()
    p_ltr.general.failure_direction = "left_to_right"
    p_ltr.external = [[L - x, y] for x, y in reversed(p_rtl.external)]
    p_ltr.assignments = [
        {"point": [L - a["point"][0], a["point"][1]], "material": a["material"]}
        for a in p_rtl.assignments
    ]
    g_ltr = p_ltr.build_geometry()
    m_ltr = p_ltr.build_materials()
    s_ltr = make_slices(
        g_ltr, CircularSurface(L - 26.0, 28.0, 26.0), m_ltr, opts=p_ltr.slice_options()
    )
    rsp_ltr = spencer(s_ltr)
    assert rsp_ltr.fos == pytest.approx(rsp.fos, rel=1e-10)
    assert rsp_ltr.base_normal_eff == pytest.approx(rsp.base_normal_eff[::-1], rel=1e-7)
