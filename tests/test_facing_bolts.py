"""Shotcrete + wire-mesh facing, automatic bolts and bolt patterns."""

import math

import pytest

from slipsurface.geometry import PolylineSurface, simple_slope
from slipsurface.lem import SliceOptions, analyze
from slipsurface.loads import Facing, FacingType, LoadSet, bolt_at, pattern_positions
from slipsurface.materials import MohrCoulomb

TH = math.radians(15)
TP = math.tan(math.radians(19.6))
FORCE_EQ = ["spencer", "gle", "janbu_simplified", "corps1", "lowe_karafiath", "ordinary"]


def acads():
    g = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    return g, {"Soil 1": MohrCoulomb("Soil 1", gamma=20, c=3, phi=19.6)}


def exact_block(Px, Py, Qx, Qy, passive=True):
    xe = 20 + 10 / math.tan(TH)
    W = 20 * 0.5 * (xe - 40) * 10
    L = math.hypot(xe - 20, 10)
    Na = Qx * math.sin(TH) + (W - Qy) * math.cos(TH)
    Da = -Qx * math.cos(TH) + (W - Qy) * math.sin(TH)
    Np = Px * math.sin(TH) - Py * math.cos(TH)
    Dp = -Px * math.cos(TH) - Py * math.sin(TH)
    if not passive:
        return (3 * L + (Na + Np) * TP) / (Da + Dp)
    b = Dp - 3 * L - Na * TP
    return (-b + math.sqrt(b * b + 4 * Da * Np * TP)) / (2 * Da)


def test_facing_type_capacity():
    f = FacingType(thickness=0.15, tau=500, mesh_as=257, mesh_fy=500)
    assert f.capacity == pytest.approx(0.15 * 500 + 257 * 0.5)
    assert f.weight_per_m == pytest.approx(24 * 0.15)


@pytest.mark.parametrize("method", FORCE_EQ)
@pytest.mark.parametrize("app", ["passive", "active"])
def test_block_with_facing_exact(method, app):
    """Facing on the whole face: its weight + capacity at the toe exit, tangent to the plane."""
    g, mats = acads()
    ft = FacingType(thickness=0.1, gamma=24, tau=400, mesh_as=188, mesh_fy=500, application=app)
    loads = LoadSet(facings=[Facing(20, 40, ft)])
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(TH)]])
    res, s = analyze(g, surf, mats, n_slices=40, method=method, opts=SliceOptions(loads=loads))
    Wf = 24 * 0.1 * math.hypot(20, 10)
    T = ft.capacity
    assert res.ok and len(s.support_forces) == 1
    exact = exact_block(T * math.cos(TH), T * math.sin(TH), 0.0, -Wf, passive=(app == "passive"))
    assert res.fos == pytest.approx(exact, rel=1e-6)


def test_facing_not_counted_when_surface_daylights_elsewhere():
    g, mats = acads()
    loads = LoadSet(facings=[Facing(25, 35, FacingType())])
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(TH)]])
    _, s = analyze(g, surf, mats, n_slices=40, opts=SliceOptions(loads=loads))
    assert s.support_forces == []  # toe at x=20 is not faced
    assert s.Qy_a.sum() == pytest.approx(-FacingType().weight_per_m * math.hypot(10, 5))


def test_facing_capacity_counted_once_when_both_ends_faced():
    """Facing spans the whole slip surface: capacity mobilises once, not at both ends."""
    g, mats = acads()
    loads = LoadSet(facings=[Facing(20, 40, FacingType())])
    surf = PolylineSurface([[22, 1.0], [30, 3.0], [38, 9.0]])  # both ends on the face
    _, s = analyze(g, surf, mats, n_slices=40, opts=SliceOptions(loads=loads))
    assert len(s.support_forces) == 1
    assert s.support_forces[0].T == pytest.approx(FacingType().capacity)


def test_bolt_direction_15_degrees():
    g, _ = acads()
    A, B = bolt_at(g, 30.0, 15.0, 12.0)
    assert A == pytest.approx([30.0, 5.0])
    d = (B - A) / 12.0
    assert d[0] > 0 and math.degrees(math.atan2(-d[1], d[0])) == pytest.approx(15.0)
    # mirrored slope -> bolt points to -x
    gm = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    gm.surface[:, 0] *= -1
    gm.surface = gm.surface[::-1].copy()
    A2, B2 = bolt_at(gm, -30.0, 15.0, 12.0)
    assert B2[0] < A2[0]


def test_pattern_positions_follow_arc_length():
    g, _ = acads()
    xs = pattern_positions(g, 20, 40, spacing=math.hypot(4, 2), offset=0.0)
    assert xs == pytest.approx([20, 24, 28, 32, 36, 40])
    xs = pattern_positions(g, 15, 25, spacing=2.0, offset=1.0)  # across the toe kink
    assert xs[0] == pytest.approx(16.0) and xs[2] == pytest.approx(20.0)
    assert xs[3] == pytest.approx(20 + 2 / math.hypot(1, 0.5))


@pytest.mark.slow
def test_project_patterns_and_facings_roundtrip_and_analysis():
    from slipsurface.analysis import report_text, run_analysis
    from slipsurface.loads import SupportType
    from slipsurface.project import Project, acads_1a_project

    p = acads_1a_project()
    p.support_types = [
        SupportType(
            "Bulon", "soil_nail", spacing=1.5, tensile=150, plate=60, bond_strength=40, length=8
        )
    ]
    p.support_patterns = [
        {
            "p1": [21, 0.5],
            "p2": [39, 9.5],
            "spacing": 2.0,
            "offset": 1.0,
            "angle": 15.0,
            "length": 8.0,
            "type": "Bulon",
        }
    ]
    p.facing_types = [FacingType()]
    p.facings = [{"x1": 20.0, "x2": 40.0, "type": FacingType().name}]
    q = Project.from_dict(p.to_dict())
    assert q.to_dict() == p.to_dict()
    ls = p.load_set()
    assert len(ls.supports) == len(pattern_positions(p.build_geometry(), 21, 39, 2.0, 1.0))
    assert ls.supports[0].label == "Pattern 1/1" and len(ls.facings) == 1
    p.methods.methods = ["bishop"]
    p.surfaces.effort = "fast"
    base = acads_1a_project()
    base.methods.methods = ["bishop"]
    base.surfaces.effort = "fast"
    r = run_analysis(p)
    assert r.results["bishop"].fos > run_analysis(base).results["bishop"].fos
    txt = report_text(r)
    assert "Bolt patterns" in txt and "Facings" in txt
