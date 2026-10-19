"""LEM engine verification."""

import math

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface, simple_slope, slip_extent
from slipsurface.lem import analyze_circle, bishop_simplified, make_slices, ordinary
from slipsurface.materials import HoekBrown, MohrCoulomb


def acads_1a():
    """ACADS EX1(a), Donald & Giam (1989): H=10 m, 2H:1V, c=3 kPa, phi=19.6°, gamma=20.
    Reference FoS = 1.00; Slide2 verification #1 Bishop = 0.987."""
    g = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    mats = {"Zemin 1": MohrCoulomb("Zemin 1", gamma=20, c=3, phi=19.6)}
    return g, mats


# ------------------------------------------------------------ geometry
def test_slip_extent_toe_circle():
    g, _ = acads_1a()
    surf = CircularSurface(20, 28, 28)                 # passes through the toe
    xl, xr = slip_extent(g, surf)
    assert xl == pytest.approx(20.0, abs=1e-6)
    # entry on crest plateau y=10: (x-20)^2 + 18^2 = 28^2
    assert xr == pytest.approx(20 + math.sqrt(28**2 - 18**2), abs=1e-6)


def test_surface_outside_model_rejected():
    g, mats = acads_1a()
    res, s = analyze_circle(g, CircularSurface(30, 30, 50), mats)   # cuts the bottom
    assert s is None and not res.ok
    res, s = analyze_circle(g, CircularSurface(30, 40, 5), mats)    # above ground
    assert s is None and not res.ok


def test_slice_weights_sum_to_mass_area():
    g, mats = acads_1a()
    surf = CircularSurface(20, 28, 28)
    s = make_slices(g, surf, mats, n_slices=400)
    xl, xr = s.x_exit, s.x_entry
    xs = np.linspace(xl, xr, 200_001)
    area = np.trapezoid(g.ground_y(xs) - surf.y(xs), xs)
    assert s.W.sum() == pytest.approx(20 * area, rel=1e-4)


# --------------------------------------------------------------- Bishop
def _bishop_reference(g, surf, c, phi, gamma, n=2000):
    """Independent loop-based Bishop with analytic slice areas."""
    xl, xr = slip_extent(g, surf)
    xs = np.linspace(xl, xr, n + 1)
    tp = math.tan(math.radians(phi))
    W, a, b = [], [], []
    for x0, x1 in zip(xs[:-1], xs[1:]):
        sub = np.linspace(x0, x1, 9)
        area = np.trapezoid(g.ground_y(sub) - surf.y(sub), sub)
        W.append(gamma * area)
        b.append(x1 - x0)
        a.append(math.asin((0.5 * (x0 + x1) - surf.xc) / surf.r))
    W, a, b = map(np.array, (W, a, b))
    f = 1.0
    for _ in range(200):
        m = np.cos(a) + np.sin(a) * tp / f
        f = np.sum((c * b + W * tp) / m) / np.sum(W * np.sin(a))
    return f


@pytest.mark.parametrize("surf", [CircularSurface(20, 28, 28), CircularSurface(25, 25, 25),
                                  CircularSurface(30, 22, 20)])
def test_bishop_matches_independent_reference(surf):
    g, mats = acads_1a()
    res, _ = analyze_circle(g, surf, mats, n_slices=200)
    assert res.ok
    assert res.fos == pytest.approx(_bishop_reference(g, surf, 3, 19.6, 20), rel=2e-3)


def test_bishop_vs_ordinary():
    """Bishop >= Fellenius for frictional soils (well-known ordering)."""
    g, mats = acads_1a()
    s = make_slices(g, CircularSurface(20, 28, 28), mats)
    assert bishop_simplified(s).fos > ordinary(s).fos


def test_acads_1a_minimum():
    """Coarse grid minimum must match the benchmark within 2 %."""
    g, mats = acads_1a()
    best = np.inf
    for xc in np.arange(16, 30, 1.0):
        for yc in np.arange(20, 36, 1.0):
            for r in np.arange(15, 40, 1.0):
                res, _ = analyze_circle(g, CircularSurface(xc, yc, r), mats)
                if res.ok:
                    best = min(best, res.fos)
    assert best == pytest.approx(0.987, abs=0.02)


def test_cohesionless_infinite_slope_limit():
    """c=0, dry: shallow circles approach tan(phi)/tan(beta) from above."""
    g = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    mats = {"Zemin 1": MohrCoulomb("Zemin 1", gamma=18, c=0, phi=30)}
    target = math.tan(math.radians(30)) / 0.5
    # very large, shallow circle tangent-ish to the face
    nx, ny = -1 / math.sqrt(5), 2 / math.sqrt(5)       # outward face normal
    mid = np.array([30.0, 5.0])
    # R small enough that the arc's lowest point (yc - R) stays above the toe
    # bench, otherwise the arc re-enters the ground left of the toe.
    R, depth = 40.0, 0.05
    centre = mid + (R - depth) * np.array([nx, ny])
    res, _ = analyze_circle(g, CircularSurface(*centre, R), mats, n_slices=50)
    assert res.ok
    assert target <= res.fos < target * 1.02


def test_water_table_reduces_fos():
    g, mats = acads_1a()
    surf = CircularSurface(20, 28, 28)
    dry, _ = analyze_circle(g, surf, mats)
    g.water_table = np.array([[0.0, 0.0], [20.0, 0.0], [40.0, 6.0], [60.0, 6.0]])
    wet, _ = analyze_circle(g, surf, mats)
    assert wet.ok and wet.fos < dry.fos


# ----------------------------------------------------------- Hoek-Brown
def test_hoek_brown_parameters_and_envelope():
    hb = HoekBrown("Kaya", gamma=25, sigma_ci=50_000, gsi=60, mi=10, d=0)
    # Hoek et al. (2002) closed forms
    assert hb.mb == pytest.approx(10 * math.exp(-40 / 28))
    assert hb.s == pytest.approx(math.exp(-40 / 9))
    sn = np.array([0.0, 100.0, 500.0, 2000.0])
    c, tp = hb.strength(sn)
    assert np.all(np.diff(np.degrees(np.arctan(tp))) < 0)         # phi_i decreases
    np.testing.assert_allclose(c + sn * tp, hb.tau(sn), rtol=1e-3)  # tangent passes curve


def test_bishop_runs_with_hoek_brown():
    g, _ = acads_1a()
    mats = {"Zemin 1": HoekBrown("Zemin 1", gamma=22, sigma_ci=5_000, gsi=30, mi=8, d=0.7)}
    res, _ = analyze_circle(g, CircularSurface(20, 28, 28), mats)
    assert res.ok and 0.5 < res.fos < 20


# ------------------------------------------------------------ optimizer
def test_de_search_acads_1a():
    from slipsurface.optimizer import SearchSettings, search_circular
    g, mats = acads_1a()
    for seed in (0, 1):
        r = search_circular(g, mats, SearchSettings(seed=seed))
        assert r.lem.ok
        assert r.fos == pytest.approx(0.987, abs=0.01)
        assert r.slices.x_exit == pytest.approx(20.0, abs=0.5)   # toe circle


def test_circle_from_chord_passes_through_points():
    from slipsurface.optimizer import circle_from_chord
    g, _ = acads_1a()
    for x1, x2, th in [(20, 41, 0.6), (10, 50, 1.2), (30, 45, 0.2)]:
        c = circle_from_chord(g, x1, x2, th)
        for x in (x1, x2):
            assert math.hypot(x - c.xc, g.ground_y(x) - c.yc) == pytest.approx(c.r)
            assert c.y(x) == pytest.approx(g.ground_y(x))         # on the LOWER arc


# ------------------------------------------------------- Spencer / GLE
from slipsurface.geometry import PolylineSurface, SplineSurface  # noqa: E402
from slipsurface.lem import analyze, morgenstern_price, spencer  # noqa: E402
from slipsurface.lem.gle import _Frame, _residuals, interslice_function  # noqa: E402
from slipsurface.lem.bishop import _strength, _initial_sigma_n  # noqa: E402


def _planar_case(theta_deg=15.0):
    g, mats = acads_1a()
    th = math.radians(theta_deg)
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(th)]])
    xe = 20 + 10 / math.tan(th)
    W = 20 * 0.5 * abs((40 - 20) * 10 - (xe - 20) * 10)   # triangle toe-crest-entry
    W = 20 * 0.5 * (xe - 40) * 10
    L = math.hypot(xe - 20, 10)
    exact = (3 * L + W * math.cos(th) * math.tan(math.radians(19.6))) / (W * math.sin(th))
    return g, mats, surf, exact, th


@pytest.mark.parametrize("method", ["spencer", "gle"])
def test_planar_block_exact(method):
    """Global force equilibrium ⇒ rigid-block solution for a planar surface."""
    g, mats, surf, exact, th = _planar_case()
    res, _ = analyze(g, surf, mats, n_slices=40, method=method)
    assert res.ok
    assert res.fos == pytest.approx(exact, rel=1e-6)


def test_spencer_lambda_planar_is_tan_theta():
    g, mats, surf, _, th = _planar_case()
    res, _ = analyze(g, surf, mats, n_slices=40, method="spencer")
    assert res.lam == pytest.approx(math.tan(th), rel=1e-6)


def test_moment_residual_zero_for_bishop_at_lambda0():
    """About the circle centre with λ=0, R2 = 0 is exactly Bishop's equation."""
    g, mats = acads_1a()
    s = make_slices(g, CircularSurface(20, 28, 28), mats)
    fb = bishop_simplified(s).fos
    fr = _Frame(s)
    c, tp = _strength(s, _initial_sigma_n(s))
    _, r2, _ = _residuals(fb, 0.0, fr, c[fr.order], tp[fr.order],
                          interslice_function("constant", fr.xb))
    assert abs(r2) < 1e-7


def test_spencer_close_to_bishop_on_circle():
    g, mats = acads_1a()
    s = make_slices(g, CircularSurface(20, 28, 28), mats)
    b, sp, mp = bishop_simplified(s), spencer(s), morgenstern_price(s)
    assert sp.ok and mp.ok
    assert sp.fos == pytest.approx(b.fos, rel=0.01)       # Slide2: 0.986 vs 0.987
    assert mp.fos == pytest.approx(sp.fos, rel=0.005)


def test_gle_mirror_invariance():
    from slipsurface.project import acads_1a_project
    p = acads_1a_project()
    surf = CircularSurface(20, 28, 28)
    a, _ = analyze(p.build_geometry(), surf, p.build_materials(), method="spencer")
    p.external = [[0, -5], [60, -5], [60, 0], [40, 0], [20, 10], [0, 10]]
    b, s = analyze(p.build_geometry(), CircularSurface(40, 28, 28), p.build_materials(),
                   method="spencer")
    assert s.direction == +1
    assert b.fos == pytest.approx(a.fos, rel=1e-6)
    assert b.lam == pytest.approx(a.lam, rel=1e-6)


def test_spencer_hoek_brown_converges():
    g, _ = acads_1a()
    mats = {"Zemin 1": HoekBrown("Zemin 1", gamma=22, sigma_ci=5_000, gsi=30, mi=8, d=0.7)}
    surf = CircularSurface(20, 28, 28)
    b, _ = analyze(g, surf, mats, method="bishop")
    sp, _ = analyze(g, surf, mats, method="spencer")
    assert sp.ok and sp.fos == pytest.approx(b.fos, rel=0.03)


def test_bishop_rejects_noncircular():
    g, mats, surf, _, _ = _planar_case()
    res, _ = analyze(g, surf, mats, method="bishop")
    assert not res.ok and "circular" in res.message


def test_spline_surface_properties():
    sp = SplineSurface(20, 45, [0, -3, -4, 2, 10])
    assert sp.y(20) == pytest.approx(0) and sp.y(45) == pytest.approx(10)
    assert np.isnan(sp.y(19)) and np.isnan(sp.y(46))
    cp = sp.control_points()
    assert cp[0, 0] == 20 and cp[-1, 0] == 45
    xs = np.linspace(20, 45, 200)
    assert sp.y(xs).min() >= cp[:, 1].min() - 1e-9        # convex hull property


def test_spencer_on_spline_close_to_circle():
    """A spline fitted to the critical circle gives nearly the same FoS."""
    g, mats = acads_1a()
    circ = CircularSurface(20, 28, 28)
    xe = 20 + math.sqrt(28**2 - 18**2)
    from scipy.interpolate import make_lsq_spline  # noqa: F401
    xs = np.linspace(20, xe, 9)
    sp = SplineSurface(20, xe, circ.y(xs))   # control ordinates ≈ circle samples
    a, _ = analyze(g, circ, mats, method="spencer")
    b, _ = analyze(g, sp, mats, method="spencer")
    assert b.ok and b.fos == pytest.approx(a.fos, abs=0.03)
