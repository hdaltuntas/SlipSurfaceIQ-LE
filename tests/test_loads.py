"""External loads and support forces."""

import math

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface, PolylineSurface, simple_slope
from slipsurface.lem import SliceOptions, analyze
from slipsurface.loads import (
    DistributedLoad,
    LineLoad,
    LoadSet,
    Support,
    SupportType,
    support_capacity,
    support_intersection,
)
from slipsurface.materials import MohrCoulomb

FORCE_EQ = ["spencer", "gle", "janbu_simplified", "corps1", "corps2", "lowe_karafiath",
            "ordinary"]
TH = math.radians(15)
TP = math.tan(math.radians(19.6))


def acads():
    g = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    return g, {"Zemin 1": MohrCoulomb("Zemin 1", gamma=20, c=3, phi=19.6)}


def plane():
    return PolylineSurface([[20, 0], [60, 40 * math.tan(TH)]])


def block():
    xe = 20 + 10 / math.tan(TH)
    W = 20 * 0.5 * (xe - 40) * 10
    L = math.hypot(xe - 20, 10)
    return W, L, xe


def exact_active(Qx, Qy):
    W, L, _ = block()
    N = Qx * math.sin(TH) + (W - Qy) * math.cos(TH)
    D = -Qx * math.cos(TH) + (W - Qy) * math.sin(TH)
    return (3 * L + N * TP) / D


def exact_passive(Px, Py, Qx=0.0, Qy=0.0):
    W, L, _ = block()
    Na = Qx * math.sin(TH) + (W - Qy) * math.cos(TH)
    Da = -Qx * math.cos(TH) + (W - Qy) * math.sin(TH)
    Np = Px * math.sin(TH) - Py * math.cos(TH)
    Dp = -Px * math.cos(TH) - Py * math.sin(TH)
    b = Dp - 3 * L - Na * TP
    return (-b + math.sqrt(b * b + 4 * Da * Np * TP)) / (2 * Da)


@pytest.mark.parametrize("method", FORCE_EQ)
def test_block_with_line_and_distributed_load(method):
    g, mats = acads()
    loads = LoadSet(distributed=[DistributedLoad(42, 52, 10, 30, "vertical")],
                    line=[LineLoad(45, 10, 50, 250)])
    res, _ = analyze(g, plane(), mats, n_slices=40, method=method,
                     opts=SliceOptions(loads=loads))
    qtot = 0.5 * (10 + 30) * 10
    px, py = 50 * math.cos(math.radians(250)), 50 * math.sin(math.radians(250))
    assert res.ok, res.message
    assert res.fos == pytest.approx(exact_active(px, py - qtot), rel=1e-6)


def _anchor(kind="end_anchored", app="active", T=300.0, spacing=1.0, **kw):
    st = SupportType("A", kind, spacing=spacing, tensile=T, application=app, **kw)
    a = (30.0, 5.0)
    d = np.array([math.cos(math.radians(-15)), math.sin(math.radians(-15))])
    return Support(a, tuple(np.array(a) + 20 * d), st), d


@pytest.mark.parametrize("method", FORCE_EQ)
def test_block_with_active_anchor(method):
    g, mats = acads()
    sup, d = _anchor(app="active", T=300, spacing=1.5)
    res, s = analyze(g, plane(), mats, n_slices=40, method=method,
                     opts=SliceOptions(loads=LoadSet(supports=[sup])))
    T = 300 / 1.5
    assert res.ok and len(s.support_forces) == 1
    assert res.fos == pytest.approx(exact_active(T * d[0], T * d[1]), rel=1e-6)


@pytest.mark.parametrize("method", ["spencer", "gle", "janbu_simplified", "corps1", "ordinary"])
def test_block_with_passive_anchor(method):
    g, mats = acads()
    sup, d = _anchor(app="passive", T=300)
    res, _ = analyze(g, plane(), mats, n_slices=40, method=method,
                     opts=SliceOptions(loads=LoadSet(supports=[sup])))
    assert res.ok
    assert res.fos == pytest.approx(exact_passive(300 * d[0], 300 * d[1]), rel=1e-6)


def test_support_intersection_and_lengths():
    sup, d = _anchor()
    p = support_intersection(sup, plane(), 20, 57.3)
    assert p[1] == pytest.approx((p[0] - 20) * math.tan(TH), abs=1e-8)
    # point lies on the support line
    v = np.array(p) - np.array(sup.a)
    assert v[0] * d[1] - v[1] * d[0] == pytest.approx(0, abs=1e-8)


def test_support_capacities():
    st = SupportType(kind="grouted_tieback", tensile=500, bond_strength=40, bond_length=5)
    assert support_capacity(st, 3, 10)[0] == pytest.approx(200)      # bond governs
    assert support_capacity(st, 3, 2)[0] == pytest.approx(80)        # partial bond length
    st = SupportType(kind="soil_nail", tensile=150, plate=50, bond_strength=20)
    assert support_capacity(st, 2, 10)[0] == pytest.approx(90)       # plate + inner bond
    assert support_capacity(st, 10, 3)[0] == pytest.approx(60)       # outer pullout
    st = SupportType(kind="geotextile", tensile=40, pullout=10)
    assert support_capacity(st, 1, 5)[0] == pytest.approx(10)
    assert support_capacity(st, 8, 9)[0] == pytest.approx(40)


def test_anchor_increases_fos_bishop_close_to_spencer():
    g, mats = acads()
    surf = CircularSurface(20, 28, 28)
    sup, _ = _anchor(T=200)
    o = SliceOptions(loads=LoadSet(supports=[sup]))
    b0, _ = analyze(g, surf, mats, method="bishop")
    b, _ = analyze(g, surf, mats, method="bishop", opts=o)
    sp, _ = analyze(g, surf, mats, method="spencer", opts=o)
    assert b.ok and sp.ok and b.fos > b0.fos * 1.1
    assert sp.fos == pytest.approx(b.fos, rel=0.03)


def test_bishop_consistent_with_gle_moment_under_loads():
    """About the circle centre with lambda = 0 the GLE moment residual vanishes at the
    Bishop FoS — also with line loads, distributed loads and (passive) anchors."""
    from slipsurface.lem import bishop_simplified, make_slices
    from slipsurface.lem.gle import _Frame, _residuals, _strengths_frame, interslice_function
    g, mats = acads()
    loads = LoadSet(line=[LineLoad(30, 5, 40, 250)],
                    distributed=[DistributedLoad(40, 46, 15, 25, "vertical")],
                    supports=[_anchor(app="passive", T=200)[0]])
    s = make_slices(g, CircularSurface(20, 28, 28), mats, opts=SliceOptions(loads=loads))
    fb = bishop_simplified(s, tol=1e-12).fos
    fr = _Frame(s)
    c, tp = _strengths_frame(s, fr)
    _, r2, _ = _residuals(fb, 0.0, fr, c, tp, interslice_function("constant", fr.xb))
    assert abs(r2) < 1e-8


def test_surcharge_reduces_fos_and_mirror_invariance():
    from slipsurface.project import acads_1a_project
    p = acads_1a_project()
    g, m = p.build_geometry(), p.build_materials()
    surf = CircularSurface(20, 28, 28)
    load = LoadSet(distributed=[DistributedLoad(40, 46, 20, 20)],
                   supports=[_anchor(T=150)[0]])
    a0, _ = analyze(g, surf, m, method="spencer")
    a, _ = analyze(g, surf, m, method="spencer", opts=SliceOptions(loads=LoadSet(
        distributed=load.distributed)))
    assert a.fos < a0.fos
    full, _ = analyze(g, surf, m, method="spencer", opts=SliceOptions(loads=load))
    # mirrored model, mirrored loads
    p.external = [[-x, y] for x, y in p.external]
    gm = p.build_geometry()
    sup = load.supports[0]
    mload = LoadSet(distributed=[DistributedLoad(-46, -40, 20, 20)],
                    supports=[Support((-sup.a[0], sup.a[1]), (-sup.b[0], sup.b[1]), sup.stype)])
    b, s = analyze(gm, CircularSurface(-20, 28, 28), m, method="spencer",
                   opts=SliceOptions(loads=mload))
    assert s.direction == +1
    assert b.fos == pytest.approx(full.fos, rel=1e-6)


def test_normal_distributed_load_on_face():
    """Normal load on the slope face: total force = q * length, normal to the face."""
    g, mats = acads()
    loads = LoadSet(distributed=[DistributedLoad(25, 35, 10, 10, "normal")])
    _, s = analyze(g, CircularSurface(20, 28, 28), mats, opts=SliceOptions(loads=loads))
    L = math.hypot(10, 5)
    n = np.array([0.5, -1.0]) / math.hypot(0.5, 1.0)    # into the soil (face dy/dx = 0.5)
    assert s.Qx_a.sum() == pytest.approx(10 * L * n[0], rel=1e-6)
    assert s.Qy_a.sum() == pytest.approx(10 * L * n[1], rel=1e-6)
