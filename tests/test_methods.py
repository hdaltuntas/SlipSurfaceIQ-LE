"""Additional methods, pseudo-static loads, Ru, failure direction."""

import math

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface, PolylineSurface, simple_slope
from slipsurface.lem import METHODS, SliceOptions, analyze
from slipsurface.materials import MohrCoulomb

FORCE_EQ = ["spencer", "gle", "janbu_simplified", "janbu_corrected", "corps1", "corps2",
            "lowe_karafiath", "ordinary"]


def acads():
    g = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    return g, {"Zemin 1": MohrCoulomb("Zemin 1", gamma=20, c=3, phi=19.6)}


def block_exact(theta, kh=0.0, kv=0.0, c=3.0, phi=19.6, gamma=20.0):
    xe = 20 + 10 / math.tan(theta)
    W = gamma * 0.5 * (xe - 40) * 10
    L = math.hypot(xe - 20, 10)
    Wv, Fh = W * (1 - kv), kh * W
    N = Wv * math.cos(theta) - Fh * math.sin(theta)
    return (c * L + N * math.tan(math.radians(phi))) / (Wv * math.sin(theta) + Fh * math.cos(theta))


@pytest.mark.parametrize("method", FORCE_EQ)
@pytest.mark.parametrize("kh,kv", [(0.0, 0.0), (0.15, 0.0), (0.1, 0.05)])
def test_planar_block_all_force_methods(method, kh, kv):
    g, mats = acads()
    th = math.radians(15)
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(th)]])
    res, _ = analyze(g, surf, mats, n_slices=40, method=method,
                     opts=SliceOptions(kh=kh, kv=kv))
    assert res.ok, res.message
    assert res.fos == pytest.approx(block_exact(th, kh, kv), rel=1e-6)


def test_seismic_bishop_vs_spencer_circle():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    o = SliceOptions(kh=0.1)
    b, _ = analyze(g, surf, mats, method="bishop", opts=o)
    s, _ = analyze(g, surf, mats, method="spencer", opts=o)
    b0, _ = analyze(g, surf, mats, method="bishop")
    assert b.ok and s.ok and b.fos < b0.fos
    assert s.fos == pytest.approx(b.fos, rel=0.02)


@pytest.mark.parametrize("method", list(METHODS))
def test_all_methods_reasonable_on_acads_circle(method):
    """All methods within the usual spread around Bishop (≈0.986)."""
    g, mats = acads()
    res, _ = analyze(g, CircularSurface(20, 28, 28), mats, method=method)
    assert res.ok, res.message
    assert 0.85 < res.fos < 1.10


@pytest.mark.parametrize("method", ["janbu_simplified", "corps1", "corps2", "lowe_karafiath"])
def test_force_methods_mirror_invariant(method):
    from slipsurface.project import acads_1a_project
    p = acads_1a_project()
    a, _ = analyze(p.build_geometry(), CircularSurface(20, 28, 28), p.build_materials(),
                   method=method)
    p.external = [[0, -5], [60, -5], [60, 0], [40, 0], [20, 10], [0, 10]]
    b, s = analyze(p.build_geometry(), CircularSurface(40, 28, 28), p.build_materials(),
                   method=method)
    assert s.direction == +1
    assert b.fos == pytest.approx(a.fos, rel=1e-6)


def test_janbu_correction_increases_fos():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    js, _ = analyze(g, surf, mats, method="janbu_simplified")
    jc, _ = analyze(g, surf, mats, method="janbu_corrected")
    assert 1.0 < jc.fos / js.fos < 1.1


def test_ru_pore_pressure():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    dry, _ = analyze(g, surf, mats)
    wet, s = analyze(g, surf, mats, opts=SliceOptions(pore="ru", ru=0.25))
    assert wet.fos < dry.fos
    np.testing.assert_allclose(s.u, 0.25 * s.W / s.b)


def test_material_without_water_ignores_table():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    g.water_table = np.array([[0.0, 0.0], [20.0, 0.0], [40.0, 6.0], [60.0, 6.0]])
    wet, _ = analyze(g, surf, mats)
    mats["Zemin 1"].use_water = False
    nowater, s = analyze(g, surf, mats)
    assert np.all(s.u == 0) and nowater.fos > wet.fos


def test_forced_failure_direction():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    ok, _ = analyze(g, surf, mats, opts=SliceOptions(direction="right_to_left"))
    bad, s = analyze(g, surf, mats, opts=SliceOptions(direction="left_to_right"))
    assert ok.ok and not bad.ok and s is None


def test_min_depth_filter():
    g, mats = acads()
    res, s = analyze(g, CircularSurface(20, 28, 28), mats, opts=SliceOptions(min_depth=50))
    assert s is None and "minimum depth" in res.message


def test_admissibility_threshold_is_configurable():
    """check_admissibility flags m_alpha below the given threshold."""
    from slipsurface.lem.bishop import LEMResult, check_admissibility

    ma = np.array([0.15, 0.9, 1.1])
    bs = np.full(3, 10.0)
    W = np.full(3, 100.0)
    strict = check_admissibility(LEMResult(1.0, "X", True, 1), ma, bs, W, m_alpha_min=0.2)
    loose = check_admissibility(LEMResult(1.0, "X", True, 1), ma, bs, W, m_alpha_min=0.1)
    assert not strict.admissible and "mα" in strict.issue
    assert loose.admissible


@pytest.mark.parametrize("method", list(METHODS))
def test_advanced_thresholds_accepted_by_all_methods(method):
    """solver_kw()'s m_alpha_min / e_max_ratio flow into every solver."""
    from slipsurface.project import acads_1a_project

    p = acads_1a_project()
    p.advanced.m_alpha_min = 0.1
    p.advanced.e_max_ratio = 80.0
    kw = p.solver_kw()
    assert kw["m_alpha_min"] == 0.1 and kw["e_max_ratio"] == 80.0
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    res, _ = analyze(g, surf, mats, method=method, **kw)
    assert res.converged, res.message
