"""Tension crack: truncation of the slip surface and crack-water thrust."""

import math

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface, PolylineSurface, simple_slope
from slipsurface.lem import SliceOptions, analyze, bishop_simplified, make_slices
from slipsurface.loads import LineLoad, LoadSet, TensionCrack
from slipsurface.materials import MohrCoulomb

TH = math.radians(15)
GW = 9.81
FORCE_EQ = ["spencer", "gle", "janbu_simplified", "corps1", "corps2", "lowe_karafiath", "ordinary"]


def acads():
    g = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    return g, {"Soil 1": MohrCoulomb("Soil 1", gamma=20, c=3, phi=19.6)}


def crack(z=4.0, water=0.0):
    return TensionCrack(np.array([[38.0, 10 - z], [60.0, 10 - z]]), water, GW)


def hoek_bray(z, water):
    """Plane failure with a vertical tension crack in the upper slope surface."""
    xc = 20 + (10 - z) / math.tan(TH)
    # block: toe (20,0) - crest (40,10) - (xc,10) - crack bottom (xc, 10-z)
    pts = [(20, 0), (40, 10), (xc, 10), (xc, 10 - z)]
    area = 0.5 * abs(
        sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=False))
    )
    W = 20 * area
    A = math.hypot(xc - 20, 10 - z)
    hw = water * z
    V = 0.5 * GW * hw * hw
    tp = math.tan(math.radians(19.6))
    return (3 * A + (W * math.cos(TH) - V * math.sin(TH)) * tp) / (
        W * math.sin(TH) + V * math.cos(TH)
    ), xc


@pytest.mark.parametrize("method", FORCE_EQ)
@pytest.mark.parametrize("water", [0.0, 0.5, 1.0])
def test_hoek_bray_plane_failure_with_crack(method, water):
    g, mats = acads()
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(TH)]])
    res, s = analyze(
        g, surf, mats, n_slices=40, method=method, opts=SliceOptions(crack=crack(4.0, water))
    )
    exact, xc = hoek_bray(4.0, water)
    assert res.ok, res.message
    assert s.x_entry == pytest.approx(xc, abs=1e-6)
    assert s.crack["depth"] == pytest.approx(4.0, abs=1e-6)
    assert res.fos == pytest.approx(exact, rel=1e-6)


def test_water_in_crack_reduces_fos():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    dry, s = analyze(g, surf, mats, opts=SliceOptions(crack=crack(3.0, 0.0)))
    wet, _ = analyze(g, surf, mats, opts=SliceOptions(crack=crack(3.0, 1.0)))
    assert s.crack is not None and dry.ok and wet.ok and wet.fos < dry.fos


def test_crack_shortens_mass_and_is_on_crest_side():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    s0 = make_slices(g, surf, mats)
    s = make_slices(g, surf, mats, opts=SliceOptions(crack=crack(2.0)))
    assert s.x_exit == pytest.approx(s0.x_exit) and s.x_entry < s0.x_entry
    assert surf.y(s.x_entry) == pytest.approx(8.0, abs=1e-6)  # on the crack line
    assert s.W.sum() < s0.W.sum()


def test_surface_not_reaching_crack_line_unchanged():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    deep = TensionCrack(np.array([[50.0, 2.0], [60.0, 2.0]]))  # beyond the mass
    s0 = make_slices(g, surf, mats)
    s = make_slices(g, surf, mats, opts=SliceOptions(crack=deep))
    assert s.crack is None and s.x_entry == pytest.approx(s0.x_entry)


def test_mirrored_crack():
    g, mats = acads()
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(TH)]])
    a, _ = analyze(g, surf, mats, method="spencer", opts=SliceOptions(crack=crack(4, 1.0)))
    from slipsurface.project import acads_1a_project

    p = acads_1a_project()
    p.external = [[-x, y] for x, y in p.external]
    gm, m = p.build_geometry(), p.build_materials()
    surf_m = PolylineSurface([[-60, 40 * math.tan(TH)], [-20, 0]])
    mc = TensionCrack(np.array([[-60.0, 6.0], [-38.0, 6.0]]), 1.0, GW)
    b, s = analyze(gm, surf_m, m, method="spencer", opts=SliceOptions(crack=mc))
    assert s.direction == +1 and s.crack is not None
    assert b.fos == pytest.approx(a.fos, rel=1e-6)


def test_bishop_gle_moment_consistency_with_crack_water():
    from slipsurface.lem.gle import _Frame, _residuals, _strengths_frame, interslice_function

    g, mats = acads()
    s = make_slices(
        g,
        CircularSurface(20, 28, 28),
        mats,
        opts=SliceOptions(crack=crack(3.0, 1.0), loads=LoadSet(line=[LineLoad(30, 5, 20, 270)])),
    )
    assert s.crack["Pw"] > 0
    fb = bishop_simplified(s, tol=1e-12).fos
    fr = _Frame(s)
    c, tp = _strengths_frame(s, fr)
    _, r2, _ = _residuals(fb, 0.0, fr, c, tp, interslice_function("constant", fr.xb))
    assert abs(r2) < 1e-8


@pytest.mark.slow
def test_project_crack_roundtrip_and_analysis():
    from slipsurface.analysis import report_text, run_analysis
    from slipsurface.project import Project, acads_1a_project

    p = acads_1a_project()
    p.tension_crack = [[38.0, 7.0], [60.0, 7.0]]
    p.groundwater.crack_water = 1.0
    q = Project.from_dict(p.to_dict())
    assert q.tension_crack == p.tension_crack and q.groundwater.crack_water == 1.0
    p.methods.methods = ["bishop"]
    p.surfaces.effort = "fast"
    r = run_analysis(p)
    base = acads_1a_project()
    base.methods.methods = ["bishop"]
    base.surfaces.effort = "fast"
    assert r.results["bishop"].fos <= run_analysis(base).results["bishop"].fos + 0.02
    assert "Tension crack" in report_text(r)
