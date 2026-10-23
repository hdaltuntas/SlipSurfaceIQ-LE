"""Closed-form reference solutions used by the verification suite.

Each function returns ``{method: (computed_fs, reference_fs)}``. The geometry is
the ACADS EX1(a) slope (H = 10 m, 2H:1V, gamma = 20 kN/m3, c' = 3 kPa,
phi' = 19.6 deg) so the cases can be checked by hand.
"""

from __future__ import annotations

import math

import numpy as np

from slipsurface.geometry import CircularSurface, PolylineSurface, simple_slope
from slipsurface.lem import SliceOptions, analyze, analyze_circle
from slipsurface.loads import TensionCrack
from slipsurface.materials import MohrCoulomb

GAMMA_W = 9.81
FORCE_EQUILIBRIUM = [
    "spencer",
    "gle",
    "janbu_simplified",
    "corps1",
    "corps2",
    "lowe_karafiath",
    "ordinary",
]

Result = dict[str, tuple[float, float]]


def _acads(c: float = 3.0, phi: float = 19.6, gamma: float = 20.0):
    geom = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    return geom, {"Zemin 1": MohrCoulomb("Zemin 1", gamma=gamma, c=c, phi=phi)}


def planar_block(theta_deg: float = 15.0) -> Result:
    """Rigid wedge on a plane through the toe (force equilibrium methods).

    FS = (c L + W cos(theta) tan(phi)) / (W sin(theta))
    """
    geom, mats = _acads()
    th = math.radians(theta_deg)
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(th)]])
    x_entry = 20 + 10 / math.tan(th)
    weight = 20 * 0.5 * (x_entry - 40) * 10
    length = math.hypot(x_entry - 20, 10)
    exact = (3 * length + weight * math.cos(th) * math.tan(math.radians(19.6))) / (
        weight * math.sin(th)
    )
    out: Result = {}
    for method in FORCE_EQUILIBRIUM:
        res, _ = analyze(geom, surf, mats, n_slices=40, method=method)
        out[method] = (res.fos if res.ok else math.nan, exact)
    return out


def hoek_bray_tension_crack(depth: float = 4.0, water: float = 0.5) -> Result:
    """Plane failure with a vertical, partly water-filled tension crack.

    Hoek & Bray (1981): FS = (c A + (W cos(theta) - V sin(theta)) tan(phi))
    / (W sin(theta) + V cos(theta)), with V = gamma_w z_w^2 / 2.
    """
    geom, mats = _acads()
    th = math.radians(15.0)
    xc = 20 + (10 - depth) / math.tan(th)
    pts = [(20, 0), (40, 10), (xc, 10), (xc, 10 - depth)]
    area = 0.5 * abs(
        sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1], strict=True))
    )
    weight = 20 * area
    length = math.hypot(xc - 20, 10 - depth)
    zw = water * depth
    thrust = 0.5 * GAMMA_W * zw * zw
    tp = math.tan(math.radians(19.6))
    exact = (3 * length + (weight * math.cos(th) - thrust * math.sin(th)) * tp) / (
        weight * math.sin(th) + thrust * math.cos(th)
    )
    crack = TensionCrack(np.array([[38.0, 10 - depth], [60.0, 10 - depth]]), water, GAMMA_W)
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(th)]])
    out: Result = {}
    for method in FORCE_EQUILIBRIUM:
        res, _ = analyze(
            geom, surf, mats, n_slices=40, method=method, opts=SliceOptions(crack=crack)
        )
        out[method] = (res.fos if res.ok else math.nan, exact)
    return out


def infinite_slope_limit(phi: float = 30.0) -> Result:
    """Dry cohesionless slope: a very shallow circle tends to tan(phi)/tan(beta)."""
    geom, mats = _acads(c=0.0, phi=phi, gamma=18.0)
    exact = math.tan(math.radians(phi)) / 0.5
    nx, ny = -1 / math.sqrt(5), 2 / math.sqrt(5)  # outward normal of the 2H:1V face
    radius, depth = 40.0, 0.05
    centre = np.array([30.0, 5.0]) + (radius - depth) * np.array([nx, ny])
    res, _ = analyze_circle(geom, CircularSurface(*centre, radius), mats, n_slices=50)
    return {"bishop": (res.fos if res.ok else math.nan, exact)}


FUNCTIONS = {
    "planar_block": planar_block,
    "hoek_bray_tension_crack": hoek_bray_tension_crack,
    "infinite_slope_limit": infinite_slope_limit,
}
