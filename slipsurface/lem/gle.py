"""General Limit Equilibrium and force-equilibrium methods.

Valid for circular AND non-circular surfaces.

Frame: solvers work in the frame where the mass moves toward -x and
alpha > 0 where the base rises in +x. Mirrored slice sets (direction = +1)
are reversed and reflected (x -> -x) before solving.

Slice i (boundaries i-1 on the left, i on the right), forces on the slice:
  Wv = (1 - kv) W  vertical load (down)
  Fh = kh W        horizontal seismic force, in the sliding direction (-x)
  N = N'+U         base normal (U = u l), direction (-sin a, cos a)
  S                base shear  = (c l + N' tan phi) / F, direction (cos a, sin a)
  +E_{i-1}, -X_{i-1}   from the left neighbour
  -E_i,     +X_i       from the right neighbour
Interslice shear  X_i = A_i E_i.

Vertical equilibrium:
  N' = [Wv + X_{i-1} - X_i - U cos a - c l sin a / F] / m_a,
  m_a = cos a + sin a tan phi / F
Horizontal equilibrium:
  E_i = E_{i-1} - U sin a + c l cos a / F + K N' - Fh,  K = tan phi cos a / F - sin a
which with X = A E is the linear recurrence E_i = a_i E_{i-1} + b_i.

Methods
  GLE / Morgenstern-Price : A_i = lambda f(x_i); (F, lambda) from E_n = 0 and
                            global moment equilibrium.  f = 1 -> Spencer.
  Janbu simplified        : A = 0, F from E_n = 0 (force equilibrium only)
  Janbu corrected         : f0 * F_Janbu, f0 = 1 + b1 (d/L - 1.4 (d/L)^2)
  Corps of Engineers #1   : interslice inclination = slope of the line joining
                            the surface's exit and entry points
  Corps of Engineers #2   : inclination = ground surface slope at each boundary
  Lowe-Karafiath          : inclination = mean of ground and base slope
For prescribed inclinations theta_i (force methods) A_i = -tan(theta_i): the
internal X is +up on a slice's right face, so a resultant dipping with the
sliding direction has negative A. Reported lambda uses the usual sign.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from scipy.optimize import brentq, root

from slipsurface.geometry import CircularSurface
from slipsurface.lem.bishop import (
    LEMResult,
    M_ALPHA_MIN,
    _initial_sigma_n,
    _strength,
    bishop_simplified,
    check_admissibility,
    ordinary,
)
from slipsurface.lem.slicing import SliceSet

F_MAX = 100.0  # beyond this a surface is practically stable; not solved
FALLBACK_WINDOW = (0.6, 2.5)  # accepted fallback root, relative to the start estimate


# ------------------------------------------------------------- functions
def interslice_function(
    kind: str, xb: np.ndarray, start: float = 0.5, end: float = 0.5
) -> np.ndarray:
    """f(x) at the slice boundaries (normalized over the mass)."""
    t = (xb - xb[0]) / (xb[-1] - xb[0])
    if kind == "constant":
        return np.ones_like(xb)
    if kind == "half-sine":
        return np.sin(np.pi * t)
    if kind == "clipped-sine":
        a0 = np.arcsin(np.clip(start, 0.0, 1.0))
        a1 = np.pi - np.arcsin(np.clip(end, 0.0, 1.0))
        return np.sin(a0 + (a1 - a0) * t)
    if kind == "trapezoidal":
        return np.clip(np.minimum(t, 1 - t) / 0.25, 0.0, 1.0)
    raise ValueError(f"unknown interslice function '{kind}'")


class _Frame:
    """Slice data in the solving frame (mass moves toward -x)."""

    def __init__(self, s: SliceSet) -> None:
        flip = s.direction == +1
        o = slice(None, None, -1) if flip else slice(None)
        sign = -1.0 if flip else 1.0
        self.sign = sign
        self.alpha = s.alpha[o]
        self.sin, self.cos = np.sin(self.alpha), np.cos(self.alpha)
        self.W, self.b, self.l = s.W[o], s.b[o], s.l[o]
        self.Wv, self.Fh = s.Wv[o], s.Fh[o]
        self.U = (s.u * s.l)[o]
        self.xm = sign * s.xm[o]
        self.yb = s.y_base[o]
        self.ytop = s.y_top[o]
        self.ycg = s.y_cg[o]
        xb = np.concatenate([s.xl, s.xr[-1:]])
        self.xb = (sign * xb)[::-1] if flip else xb  # boundaries, increasing
        yb_bound = s.surface.y(xb)
        self.yb_bound = yb_bound[::-1] if flip else yb_bound
        self.order = o
        surf = s.surface
        if hasattr(surf, "r"):
            circ = cast(CircularSurface, surf)
            self.xO, self.yO = sign * circ.xc, circ.yc
        else:
            self.xO = 0.5 * (self.xb[0] + self.xb[-1])
            self.yO = float(np.max(s.y_top)) + 0.5 * (self.xb[-1] - self.xb[0])
        # external loads (frame): x' = sign x, Fx' = sign Fx, M0' = sign M0
        self.Qx_a, self.Qy_a, self.M_a = sign * s.Qx_a[o], s.Qy_a[o], sign * s.M_a[o]
        self.Qx_p, self.Qy_p, self.M_p = sign * s.Qx_p[o], s.Qy_p[o], sign * s.M_p[o]
        self.scale_f = float(np.sum(self.W))
        self.scale_m = self.scale_f * max(1.0, self.xb[-1] - self.xb[0])

    # boundary slopes (frame coordinates)
    def ground_slope_at_boundaries(self) -> np.ndarray:
        g = np.gradient(self.ytop, self.xm) if len(self.xm) > 1 else np.zeros(1)
        return np.concatenate([[g[0]], 0.5 * (g[:-1] + g[1:]), [g[-1]]])

    def base_slope_at_boundaries(self) -> np.ndarray:
        t = np.tan(self.alpha)
        return np.concatenate([[t[0]], 0.5 * (t[:-1] + t[1:]), [t[-1]]])


# ----------------------------------------------------------------- core
def _state(F, A, fr: _Frame, c, tp):
    """E at boundaries, N' per slice, m_a per slice for interslice coeffs A (n+1)."""
    sin, cos, U, l = fr.sin, fr.cos, fr.U, fr.l
    V = fr.Wv - fr.Qy_a - fr.Qy_p / F  # net downward external force
    Hx = -fr.Fh + fr.Qx_a + fr.Qx_p / F  # net horizontal external force (+x)
    ma = cos + sin * tp / F
    K = tp * cos / F - sin
    AL, AR = A[:-1], A[1:]
    P0 = (V - U * cos - c * l * sin / F) / ma
    den = 1.0 + K * AR / ma
    a = (1.0 + K * AL / ma) / den
    bb = (-U * sin + c * l * cos / F + K * P0 + Hx) / den
    n = len(V)
    E = np.zeros(n + 1)
    e = 0.0
    al, bl = a.tolist(), bb.tolist()
    for i in range(n):
        e = al[i] * e + bl[i]
        E[i + 1] = e
    Np = P0 + (AL * E[:-1] - AR * E[1:]) / ma
    return E, Np, ma


def _moment(F, Np, fr: _Frame, c, tp) -> float:
    N = Np + fr.U
    S = (c * fr.l + Np * tp) / F
    dx, dy = fr.xm - fr.xO, fr.yb - fr.yO
    qx, qy, m0 = fr.Qx_a + fr.Qx_p / F, fr.Qy_a + fr.Qy_p / F, fr.M_a + fr.M_p / F
    return float(
        np.sum(
            -dx * fr.Wv
            + N * (dx * fr.cos + dy * fr.sin)
            + S * (dx * fr.sin - dy * fr.cos)
            + (fr.ycg - fr.yO) * fr.Fh
            + m0
            - fr.xO * qy
            + fr.yO * qx
        )
    )


def _residuals(F, lam, fr: _Frame, c, tp, fint):
    E, Np, ma = _state(F, lam * fint, fr, c, tp)
    # The free end requires both E_n = 0 and X_n = lambda*f_n*E_n = 0.
    # With an unbounded lambda, E_n alone can tend to zero while X_n stays
    # finite. Scale the signed residual by the resultant's inclination.
    force = E[-1] * np.hypot(1.0, lam * fint[-1]) / fr.scale_f
    return force, _moment(F, Np, fr, c, tp) / fr.scale_m, ma


def _balanced(F, lam, fr: _Frame, c, tp, fint, tolerance=1e-7):
    """Check actual global forces and moment, including the free-end shear."""
    if not np.isfinite(F) or F <= 0 or not np.isfinite(lam):
        return False
    E, Np, _ = _state(F, lam * fint, fr, c, tp)
    N = Np + fr.U
    S = (c * fr.l + Np * tp) / F
    qx = fr.Qx_a + fr.Qx_p / F
    qy = fr.Qy_a + fr.Qy_p / F
    residuals = np.array(
        [
            E[-1] / fr.scale_f,
            lam * fint[-1] * E[-1] / fr.scale_f,
            np.sum(-N * fr.sin + S * fr.cos - fr.Fh + qx) / fr.scale_f,
            np.sum(N * fr.cos + S * fr.sin - fr.Wv + qy) / fr.scale_f,
            _moment(F, Np, fr, c, tp) / fr.scale_m,
        ]
    )
    return bool(np.all(np.isfinite(residuals)) and np.all(np.abs(residuals) <= tolerance))


def _root_1d(fn, F_guess, span=(0.2, 5.0), n=17, resid_tol=1e-6, valid=None):
    """Bracket and solve fn(F) = 0 on a log grid around F_guess.

    A sign change can also come from a pole (a denominator crossing zero);
    such 'roots' are rejected by checking the residual afterwards. At low F
    the interslice recurrence has poles and spurious real roots, so brackets
    are tried nearest F_guess first, and `valid(F)` can reject a root.
    """
    grid = F_guess * np.geomspace(span[0], span[1], n)
    vals = np.array([fn(F) for F in grid])
    mids = np.abs(np.log(np.sqrt(grid[:-1] * grid[1:]) / F_guess))
    for k in np.argsort(mids, kind="stable"):
        if np.isfinite(vals[k]) and np.isfinite(vals[k + 1]) and vals[k] * vals[k + 1] < 0:
            try:
                r = brentq(fn, grid[k], grid[k + 1], xtol=1e-10)
            except (ValueError, RuntimeError):
                continue
            if abs(fn(r)) < resid_tol and (valid is None or valid(r)):
                return r
    return np.nan


E_MAX_RATIO = 50.0  # |E| larger than this times the total weight -> singular solution


def _singular(E, fr, e_max_ratio: float = E_MAX_RATIO) -> bool:
    return not np.all(np.isfinite(E)) or float(np.max(np.abs(E))) > e_max_ratio * fr.scale_f


def _start_estimate(fr, c, tp, fint, F_guess):
    """Mean of force-only (Janbu-like) and moment-only F at lambda = 0."""
    ff = _root_1d(lambda F: _residuals(F, 0.0, fr, c, tp, fint)[0], F_guess)
    fm = _root_1d(lambda F: _residuals(F, 0.0, fr, c, tp, fint)[1], F_guess)
    vals = [v for v in (ff, fm) if np.isfinite(v) and v > 0]
    return float(np.mean(vals)) if vals else F_guess


def _solve_linear(fr, c, tp, fint, F0, lam0, tol):
    """Solve R1 = R2 = 0 for (F, lambda) with fixed strengths.

    Newton-type `hybr` first; the lambda-scan fallback can lock onto
    non-physical roots for odd surfaces, so its answer is accepted only
    inside FALLBACK_WINDOW * F0.
    """

    def fun(v):
        F, lam = v
        if F <= 1e-3:
            return [1e3, 1e3]
        r1, r2, _ = _residuals(F, lam, fr, c, tp, fint)
        return [r1, r2]

    def try_hybr(f_start, lams):
        for l0 in lams:
            # The project tolerance controls the outer strength iteration.
            # A loose inner step tolerance can stop before force balance is
            # satisfied, needlessly sending an almost converged root through
            # the expensive nested Brent fallback.
            sol = root(fun, [f_start, l0], method="hybr", options={"xtol": min(tol, 1e-9)})
            if sol.success and _balanced(*sol.x, fr, c, tp, fint):
                return float(sol.x[0]), float(sol.x[1])
        return None

    out = try_hybr(F0, (lam0,))
    if out is None:
        F0 = _start_estimate(fr, c, tp, fint, F0)
        out = try_hybr(F0, (lam0, -0.3, 0.3))
    if out is not None:
        return out

    def _safe_brentq(fn, a, b):
        try:
            return brentq(fn, a, b, xtol=1e-10)
        except (ValueError, RuntimeError):
            return np.nan

    def f_force(lam):
        g = lambda F: _residuals(F, lam, fr, c, tp, fint)[0]  # noqa: E731
        grid = F0 * np.geomspace(FALLBACK_WINDOW[0], FALLBACK_WINDOW[1], 12)
        vals = [g(F) for F in grid]
        for k in range(len(grid) - 1):
            if np.isfinite(vals[k]) and np.isfinite(vals[k + 1]) and vals[k] * vals[k + 1] < 0:
                return _safe_brentq(g, grid[k], grid[k + 1])
        return np.nan

    def h(lam):
        F = f_force(lam)
        return np.nan if not np.isfinite(F) else _residuals(F, lam, fr, c, tp, fint)[1]

    lams = np.linspace(-1.2, 1.2, 13)
    hv = [h(x) for x in lams]
    lo, hi = FALLBACK_WINDOW[0] * F0, FALLBACK_WINDOW[1] * F0
    for k in range(len(lams) - 1):
        if np.isfinite(hv[k]) and np.isfinite(hv[k + 1]) and hv[k] * hv[k + 1] < 0:
            lam = _safe_brentq(h, lams[k], lams[k + 1])
            if np.isfinite(lam):
                F = float(f_force(lam))
                if lo <= F <= hi and _balanced(F, lam, fr, c, tp, fint):
                    return F, float(lam)
    return np.nan, np.nan


def _start(s: SliceSet):
    start = bishop_simplified(s) if s.is_circular else ordinary(s)
    if start.ok and start.fos > F_MAX:
        return None
    return start.fos if start.ok else 1.0


def _strengths_frame(s, fr, sigma_n_frame=None):
    if sigma_n_frame is None:
        c, tp = _strength(s, _initial_sigma_n(s))
    else:
        sn = np.empty(s.n)
        sn[fr.order] = sigma_n_frame
        c, tp = _strength(s, sn)
    return c[fr.order], tp[fr.order]


# ------------------------------------------------------------------ GLE
def solve_gle(
    s: SliceSet,
    interslice: str = "constant",
    tol: float = 1e-10,
    max_outer: int = 50,
    f_start: float = 0.5,
    f_end: float = 0.5,
    m_alpha_min: float = M_ALPHA_MIN,
    e_max_ratio: float = E_MAX_RATIO,
) -> LEMResult:
    name = "Spencer" if interslice == "constant" else "GLE/M-P"
    try:
        with np.errstate(all="ignore"):
            return _solve_gle(
                s, interslice, tol, max_outer, f_start, f_end, name, m_alpha_min, e_max_ratio
            )
    except (ValueError, FloatingPointError, ZeroDivisionError, np.linalg.LinAlgError) as exc:
        return LEMResult(np.nan, name, False, 0, message=f"GLE failed: {exc}")


def _solve_gle(
    s, interslice, tol, max_outer, f_start, f_end, name, m_alpha_min, e_max_ratio
) -> LEMResult:
    fr = _Frame(s)
    fint = interslice_function(interslice, fr.xb, f_start, f_end)
    nonlinear = any(m.nonlinear for m in s.materials)
    c, tp = _strengths_frame(s, fr)

    F0 = _start(s)
    if F0 is None:
        return LEMResult(
            np.nan, name, False, 0, message=f"FoS > {F_MAX:g} (practically stable; not solved)"
        )
    lam0 = 0.0
    F = lam = np.nan
    it = 0
    for it in range(1, max_outer + 1):
        F, lam = _solve_linear(fr, c, tp, fint, F0, lam0, tol)
        if not np.isfinite(F) or F <= 0:
            return LEMResult(np.nan, name, False, it, message="GLE did not converge")
        if not nonlinear:
            break
        _, Np, _ = _state(F, lam * fint, fr, c, tp)
        c_new, tp_new = _strengths_frame(s, fr, np.maximum(Np / fr.l, 0.0))
        done = abs(F - F0) < max(tol, 1e-10) * F and it > 1
        c, tp, F0, lam0 = c_new, tp_new, F, lam
        if done:
            break
    else:
        return LEMResult(float(F), name, False, it, message="did not converge")

    E, Np, ma = _state(F, lam * fint, fr, c, tp)
    lam_rep = -lam  # usual sign convention (Slide2 / GeoStudio)
    if _singular(E, fr, e_max_ratio) or _singular(lam * fint * E, fr, e_max_ratio):
        return LEMResult(np.nan, name, False, it, message="singular interslice forces")
    if not _balanced(F, lam, fr, c, tp, fint, max(tol, 1e-7)):
        return LEMResult(np.nan, name, False, it, message="unbalanced forces or moment")
    if np.any(ma <= 1e-9):
        return LEMResult(
            np.nan,
            name,
            False,
            it,
            float(ma.min()),
            "m_alpha <= 0 (steep negative base angle)",
            lam=lam_rep,
        )
    res = LEMResult(F, name, True, it, float(ma.min()), lam=lam_rep)
    return check_admissibility(
        res,
        ma,
        c * fr.l + Np * tp,
        fr.W,
        m_alpha_min,
        base_normal_eff=Np,
        interslice_E=E,
        cohesion_force=c * fr.l,
    )


def spencer(s: SliceSet, **kw) -> LEMResult:
    kw.pop("interslice", None)
    return solve_gle(s, "constant", **kw)


def morgenstern_price(s: SliceSet, **kw) -> LEMResult:
    return solve_gle(s, kw.pop("interslice", "half-sine"), **kw)


# --------------------------------------------------------- force methods
def _force_method(
    s: SliceSet,
    name: str,
    coeffs,
    max_outer: int = 50,
    tol: float = 1e-6,
    m_alpha_min: float = M_ALPHA_MIN,
    e_max_ratio: float = E_MAX_RATIO,
) -> LEMResult:
    """F from horizontal force equilibrium E_n = 0 with prescribed X/E ratios.

    `coeffs(fr)` returns A (n+1) in the solving frame.
    """
    try:
        with np.errstate(all="ignore"):
            fr = _Frame(s)
            A = coeffs(fr)
            nonlinear = any(m.nonlinear for m in s.materials)
            c, tp = _strengths_frame(s, fr)
            F0 = _start(s)
            if F0 is None:
                return LEMResult(
                    np.nan,
                    name,
                    False,
                    0,
                    message=f"FoS > {F_MAX:g} (practically stable; not solved)",
                )
            F = np.nan
            it = 0
            for it in range(1, max_outer + 1):
                cc, tt = c, tp
                fn = lambda F, cc=cc, tt=tt: _state(F, A, fr, cc, tt)[0][-1] / fr.scale_f  # noqa: E731
                ok = lambda F, tt=tt: bool(np.all(fr.cos + fr.sin * tt / F > 1e-9))  # noqa: E731
                F = _root_1d(fn, F0, resid_tol=tol, valid=ok)
                if not np.isfinite(F):
                    F = _root_1d(fn, F0, span=(0.05, 20.0), n=40, resid_tol=tol, valid=ok)
                if not np.isfinite(F) or F <= 0:
                    return LEMResult(np.nan, name, False, it, message="no force-equilibrium root")
                if not nonlinear:
                    break
                _, Np, _ = _state(F, A, fr, c, tp)
                c_new, tp_new = _strengths_frame(s, fr, np.maximum(Np / fr.l, 0.0))
                done = abs(F - F0) < max(tol, 1e-10) * F and it > 1
                c, tp, F0 = c_new, tp_new, F
                if done:
                    break
            else:
                return LEMResult(float(F), name, False, it, message="did not converge")
            E, Np, ma = _state(F, A, fr, c, tp)
            if _singular(E, fr, e_max_ratio):
                return LEMResult(np.nan, name, False, it, message="singular interslice forces")
            if np.any(ma <= 1e-9):
                return LEMResult(
                    np.nan,
                    name,
                    False,
                    it,
                    float(ma.min()),
                    "m_alpha <= 0 (steep negative base angle)",
                )
            res = LEMResult(float(F), name, True, it, float(ma.min()))
            return check_admissibility(
                res,
                ma,
                c * fr.l + Np * tp,
                fr.W,
                m_alpha_min,
                base_normal_eff=Np,
                interslice_E=E,
                cohesion_force=c * fr.l,
            )
    except (ValueError, FloatingPointError, ZeroDivisionError) as exc:
        return LEMResult(np.nan, name, False, 0, message=f"{name} failed: {exc}")


def janbu_simplified(s: SliceSet, **kw) -> LEMResult:
    return _force_method(s, "Janbu simplified", lambda fr: np.zeros(len(fr.xb)), **kw)


def janbu_correction_factor(s: SliceSet) -> float:
    """Janbu (1973) f0 = 1 + b1 (d/L - 1.4 (d/L)^2)."""
    pts = s.base_points()
    p0, p1 = pts[0], pts[-1]
    L = float(np.hypot(*(p1 - p0)))
    if L <= 0:
        return 1.0
    nvec = np.array([-(p1 - p0)[1], (p1 - p0)[0]]) / L
    d = float(np.max(np.abs((pts - p0) @ nvec)))
    # Classify the actual base strengths, including total-stress models
    # (Undrained / SHANSEP) that do not expose MC's c and phi attributes.
    cs, tp = _strength(s, _initial_sigma_n(s))
    if np.all(cs <= 0):
        b1 = 0.31
    elif np.all(tp <= 0):
        b1 = 0.69
    else:
        b1 = 0.50
    r = d / L
    f0 = 1.0 + b1 * (r - 1.4 * r * r)
    # Janbu's 1973 chart is not valid once this expression falls below 1
    # (d/L > 1/1.4). Do not report a corrected FS below the simplified value.
    return float(max(f0, 1.0))


def janbu_corrected(s: SliceSet, **kw) -> LEMResult:
    res = janbu_simplified(s, **kw)
    if res.ok:
        res.fos *= janbu_correction_factor(s)
    res.method = "Janbu corrected"
    return res


def corps1(s: SliceSet, **kw) -> LEMResult:
    def coeffs(fr):
        slope = (fr.yb_bound[-1] - fr.yb_bound[0]) / (fr.xb[-1] - fr.xb[0])
        return np.full(len(fr.xb), -slope)

    return _force_method(s, "Corps of Engineers #1", coeffs, **kw)


def corps2(s: SliceSet, **kw) -> LEMResult:
    return _force_method(
        s, "Corps of Engineers #2", lambda fr: -fr.ground_slope_at_boundaries(), **kw
    )


def lowe_karafiath(s: SliceSet, **kw) -> LEMResult:
    def coeffs(fr):
        th = 0.5 * (
            np.arctan(fr.ground_slope_at_boundaries()) + np.arctan(fr.base_slope_at_boundaries())
        )
        return -np.tan(th)

    return _force_method(s, "Lowe-Karafiath", coeffs, **kw)
