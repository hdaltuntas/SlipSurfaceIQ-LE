"""Slip surfaces.

A slip surface is anything with
    y(x)       elevation of the (lower) surface, NaN outside its x-range
    x_range()  (x_lo, x_hi) where y is defined
    points(x0, x1, n)  polyline for drawing
Circular surfaces additionally give the exact base inclination
(`sin_alpha`) and a natural moment centre (xc, yc).

The slipping mass is the x-interval where y(x) lies below the ground.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy.interpolate import BSpline
from scipy.optimize import brentq

from slipsurface.geometry.slope import SlopeGeometry


class SlipSurface(Protocol):
    """Anything that can act as a slip surface (see the module docstring)."""

    def y(self, x) -> np.ndarray: ...
    def x_range(self) -> tuple[float, float]: ...
    def points(self, x0: float, x1: float, n: int = 120) -> np.ndarray: ...


@dataclass(frozen=True)
class CircularSurface:
    xc: float
    yc: float
    r: float

    def y(self, x):
        """Lower arc elevation; NaN outside [xc-r, xc+r]."""
        x = np.asarray(x, dtype=float)
        d2 = self.r**2 - (x - self.xc) ** 2
        tol = 1e-10 * self.r**2  # round-off at x = xc ± r
        return np.where(d2 >= -tol, self.yc - np.sqrt(np.maximum(d2, 0.0)), np.nan)

    def sin_alpha(self, x):
        """Exact base inclination for a circle (dy/dx > 0 -> alpha > 0)."""
        return (np.asarray(x, dtype=float) - self.xc) / self.r

    def x_range(self) -> tuple[float, float]:
        return self.xc - self.r, self.xc + self.r

    def points(self, x0: float, x1: float, n: int = 120) -> np.ndarray:
        xs = np.linspace(x0, x1, n)
        return np.column_stack([xs, self.y(xs)])


class PolylineSurface:
    """Piecewise-linear (non-circular) surface through given vertices."""

    def __init__(self, pts) -> None:
        pts = np.asarray(pts, dtype=float)
        if len(pts) < 2 or np.any(np.diff(pts[:, 0]) <= 0):
            raise ValueError("polyline surface needs >= 2 points with increasing x")
        self.pts = pts

    def y(self, x):
        x = np.asarray(x, dtype=float)
        out = np.interp(x, self.pts[:, 0], self.pts[:, 1])
        bad = (x < self.pts[0, 0] - 1e-12) | (x > self.pts[-1, 0] + 1e-12)
        return np.where(bad, np.nan, out)

    def x_range(self) -> tuple[float, float]:
        return float(self.pts[0, 0]), float(self.pts[-1, 0])

    def points(self, x0: float, x1: float, n: int = 120) -> np.ndarray:
        inner = self.pts[(self.pts[:, 0] > x0) & (self.pts[:, 0] < x1), 0]
        xs = np.unique(np.concatenate([[x0, x1], inner, np.linspace(x0, x1, n)]))
        return np.column_stack([xs, self.y(xs)])

    def __repr__(self) -> str:
        return f"PolylineSurface({len(self.pts)} pts)"


class SplineSurface:
    """Smooth non-circular surface: cubic B-spline graph y(x).

    `ctrl_y` are the B-spline coefficients (control ordinates) on a clamped,
    uniform knot vector over [x0, x1]. The curve passes through the first and
    last control points and stays inside the control polygon's convex hull.
    """

    def __init__(self, x0: float, x1: float, ctrl_y, k: int = 3) -> None:
        c = np.asarray(ctrl_y, dtype=float)
        if x1 <= x0 or len(c) < 2:
            raise ValueError("invalid spline surface")
        k = min(k, len(c) - 1)
        n_inner = len(c) - k - 1
        inner = np.linspace(x0, x1, n_inner + 2)[1:-1]
        t = np.concatenate([[x0] * (k + 1), inner, [x1] * (k + 1)])
        self.x0, self.x1, self.k = float(x0), float(x1), k
        self.ctrl_y = c
        self._bs = BSpline(t, c, k, extrapolate=False)

    def control_points(self) -> np.ndarray:
        t, k = self._bs.t, self.k
        gx = np.array([t[i + 1 : i + k + 1].mean() for i in range(len(self.ctrl_y))])
        return np.column_stack([gx, self.ctrl_y])

    def y(self, x):
        x = np.asarray(x, dtype=float)
        xc = np.clip(x, self.x0, self.x1)
        out = self._bs(xc)
        bad = (x < self.x0 - 1e-12) | (x > self.x1 + 1e-12)
        return np.where(bad, np.nan, out)

    def x_range(self) -> tuple[float, float]:
        return self.x0, self.x1

    def points(self, x0: float, x1: float, n: int = 160) -> np.ndarray:
        xs = np.linspace(x0, x1, n)
        return np.column_stack([xs, self.y(xs)])

    def __repr__(self) -> str:
        return f"SplineSurface(x0={self.x0:.2f}, x1={self.x1:.2f}, n_ctrl={len(self.ctrl_y)})"


def slip_extent(geom: SlopeGeometry, surf, n_scan: int = 400) -> tuple[float, float] | None:
    """Exit (left) and entry (right) x of the slipping mass.

    Returns None when the surface does not cut the ground, or when the
    mass would run out through the left/right model boundary.
    If the arc cuts the ground more than twice, the sub-mass with the
    largest area is used (same idea as Slide2's 'largest mass').
    """
    a, b = surf.x_range()
    lo = max(a, geom.x_min)
    hi = min(b, geom.x_max)
    if hi - lo <= 1e-9:
        return None
    xs = np.linspace(lo, hi, n_scan)
    f = geom.ground_y(xs) - surf.y(xs)  # >0 : arc below ground
    f = np.nan_to_num(f, nan=-1.0)
    eps = 1e-9
    inside = f > eps
    if not inside.any():
        return None

    # contiguous runs of `inside`
    edges = np.flatnonzero(np.diff(inside.astype(int))).tolist()
    starts = [0] if inside[0] else []
    starts += [i + 1 for i in edges if not inside[i]]
    ends = [i for i in edges if inside[i]]
    if inside[-1]:
        ends.append(len(xs) - 1)

    best, best_area = None, 0.0
    for i0, i1 in zip(starts, ends, strict=False):
        area = np.trapezoid(f[i0 : i1 + 1], xs[i0 : i1 + 1]) if i1 > i0 else 0.0
        if area > best_area:
            best, best_area = (i0, i1), area
    if best is None:
        return None
    i0, i1 = best

    # The mass must start and end where the arc crosses the ground. If it
    # runs into a scan end it either leaves through a vertical model
    # boundary, or the arc reaches its vertical tangent (xc ± r) inside the
    # soil — both inadmissible.
    if i0 == 0 or i1 == len(xs) - 1:
        return None

    # root of (f - eps) so the bracket always changes sign, also when an end
    # point of a non-circular surface sits exactly on the ground
    g = lambda x: float(geom.ground_y(x) - surf.y(x)) - eps  # noqa: E731
    try:
        xl = brentq(g, xs[i0 - 1], xs[i0])
        xr = brentq(g, xs[i1], xs[i1 + 1])
    except ValueError:
        return None
    return float(xl), float(xr)
