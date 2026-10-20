"""Moment-equilibrium solvers for circular surfaces: Simplified Bishop and
Ordinary (Fellenius); plus shared helpers (strength lookup, admissibility).

Simplified Bishop (1955), moment equilibrium about the circle centre,
interslice shear neglected, pseudo-static loads included:

        sum[ (c b + (Wv - u b) tan(phi)) / m_a ]
  F  =  --------------------------------------------------,
         sum[ Wv sin(a) ] + sum[ Fh (yc - y_cg) ] / R

  m_a = cos(a) + sin(a) tan(phi) / F
  N'  = (Wv - u b - c b tan(a) / F) / m_a,  sigma_n' = N' / l
For non-linear materials (Hoek-Brown) c, tan(phi) are re-evaluated at
sigma_n' every iteration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from scipy.optimize import brentq

from slipsurface.geometry import CircularSurface
from slipsurface.lem.slicing import SliceSet

M_ALPHA_MIN = 0.2  # Slide2 / Whitman & Bailey (1967) threshold


@dataclass
class LEMResult:
    fos: float
    method: str
    converged: bool
    iterations: int
    m_alpha_min: float = np.nan
    message: str = ""
    lam: float = np.nan  # interslice force scaling (Spencer / GLE)
    admissible: bool = True  # physical checks passed (see check_admissibility)
    issue: str = ""  # why not admissible

    @property
    def ok(self) -> bool:
        return self.converged and np.isfinite(self.fos) and self.fos > 0


def check_admissibility(
    res: LEMResult,
    ma: np.ndarray,
    base_strength: np.ndarray,
    W: np.ndarray,
    m_alpha_min: float = M_ALPHA_MIN,
) -> LEMResult:
    """Flag numerically/physically unreliable solutions.

    * m_alpha < m_alpha_min on any slice (default 0.2, Whitman & Bailey 1967;
      Slide2 default check)
    * negative mobilisable base shear, c l + N' tan(phi) < 0, i.e. the base is
      in tension beyond what cohesion can carry — typical of spurious low-FoS
      roots on surfaces with steep negative base angles.
    """
    issues = []
    if np.min(ma) < m_alpha_min:
        issues.append(f"mα,min = {np.min(ma):.2f} < {m_alpha_min:g}")
    tol = -1e-3 * float(np.mean(W))
    if np.min(base_strength) < tol:
        issues.append("negatif taban kayma direnci (tabanda çekme)")
    res.admissible = not issues
    res.issue = "; ".join(issues)
    return res


def _strength(s: SliceSet, sigma_n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c = np.empty(s.n)
    tp = np.empty(s.n)
    for i, mat in enumerate(s.materials):
        sel = s.mat_idx == i
        if sel.any():
            if getattr(mat, "uses_vertical_stress", False):
                c[sel], tp[sel] = cast(Any, mat).strength(sigma_n[sel], sigma_v=s.sigma_v_eff[sel])
            else:
                c[sel], tp[sel] = mat.strength(sigma_n[sel])
    return c, tp


def slice_strength(s: SliceSet, i: int) -> tuple[float, float]:
    """(c, tan phi) on the base of slice i at sigma_n ~ W/b - u (reporting)."""
    mat = s.materials[s.mat_idx[i]]
    sn = np.array([max(s.W[i] / s.b[i] - s.u[i], 0.0)])
    if getattr(mat, "uses_vertical_stress", False):
        c, tp = cast(Any, mat).strength(sn, sigma_v=s.sigma_v_eff[i : i + 1])
    else:
        c, tp = mat.strength(sn)
    return float(c[0]), float(tp[0])


def _initial_sigma_n(s: SliceSet) -> np.ndarray:
    return np.maximum(s.Wv / s.b - s.u, 0.0) * np.cos(s.alpha) ** 2


def frame_ext(s: SliceSet, F: float = 1.0):
    """External loads in the solving frame (mass moves toward -x):
    (Qx', Qy, M0') with x' = sign x, Fx' = sign Fx, M0' = sign M0."""
    sign = -1.0 if s.direction == +1 else 1.0
    qx, qy, m0 = s.ext(F)
    return sign * qx, qy, sign * m0


def _driving_moment_over_R(s: SliceSet, F: float = 1.0) -> float:
    """Circle: -(sum of moments of Wv, Fh and external loads about the centre)/R.

    Moments are taken in the solving frame; with sin(a) = (x' - xc')/R the
    weight term is sum Wv sin(a).
    """
    sign = -1.0 if s.direction == +1 else 1.0
    circ = cast(CircularSurface, s.surface)  # only called for circles
    xc, yc, R = sign * circ.xc, circ.yc, circ.r
    qx, qy, m0 = frame_ext(s, F)
    m_ext = np.sum(m0 - xc * qy + yc * qx)
    return float(np.sum(s.Wv * np.sin(s.alpha)) + np.sum(s.Fh * (yc - s.y_cg)) / R - m_ext / R)


def _passive_root(balance, guess, lower, tol, max_iter):
    """Bracket the equilibrium residual without dividing by the driving force.

    T/F can reverse the driving force at a trial F without invalidating the
    eventual equilibrium. Keep Bishop's m-alpha poles outside the bracket.
    """
    lo = max(1e-8, lower + 1e-8 * max(1.0, lower))
    hi = max(1.0, float(guess), 2 * lo)
    flo = balance(lo)
    for _ in range(60):
        fhi = balance(hi)
        if np.isfinite(flo) and np.isfinite(fhi) and flo * fhi <= 0:
            try:
                root, info = brentq(
                    balance,
                    lo,
                    hi,
                    xtol=1e-12,
                    rtol=max(1e-14, min(tol, 1e-10)),
                    maxiter=max_iter,
                    full_output=True,
                )
            except (ValueError, RuntimeError):
                return np.nan, 0
            if abs(balance(root)) <= max(tol, 1e-10) * max(1.0, root):
                return float(root), max(1, info.iterations) if flo * fhi < 0 else 1
            return np.nan, 0
        hi *= 2
    return np.nan, 0


def ordinary(s: SliceSet, tol: float = 1e-9, max_iter: int = 50) -> LEMResult:
    """Ordinary (Fellenius / Swedish) method (moment form for circles,
    force form along the base otherwise). Passive loads: bracketed equilibrium."""
    sin_a, cos_a = np.sin(s.alpha), np.cos(s.alpha)

    def state(F):
        qx, qy, _m = frame_ext(s, F)
        Hx = -s.Fh + qx  # horizontal external force (frame, +x)
        V = s.Wv - qy  # net downward external force
        if s.is_circular:
            driving = _driving_moment_over_R(s, F)
        else:
            driving = np.sum(V * sin_a - Hx * cos_a)
        n_eff = np.maximum(V * cos_a + Hx * sin_a - s.u * s.l, 0.0)
        c, tp = _strength(s, n_eff / s.l)
        return driving, float(np.sum(c * s.l + n_eff * tp))

    driving, resistance = state(np.inf if s.has_passive else 1.0)
    if driving <= 0:
        return LEMResult(np.nan, "Ordinary", False, 0, message="non-positive driving moment")
    if s.has_passive:
        scale = max(1.0, float(np.sum(s.W)))

        def balance(F):
            drive, resist = state(F)
            return (F * drive - resist) / scale

        F, it = _passive_root(balance, max(1.0, resistance / driving), 0.0, tol, max_iter)
        if not np.isfinite(F) or state(F)[0] <= 0:
            return LEMResult(np.nan, "Ordinary", False, it, message="did not converge")
    else:
        F, it = resistance / driving, 1
    return LEMResult(F, "Ordinary", True, it, float(np.min(cos_a)))


def bishop_simplified(
    s: SliceSet,
    tol: float = 1e-6,
    max_iter: int = 100,
    f0: float | None = None,
    m_alpha_min: float = M_ALPHA_MIN,
) -> LEMResult:
    if not s.is_circular:
        return LEMResult(
            np.nan,
            "Bishop",
            False,
            0,
            message="Simplified Bishop is defined for circular surfaces only",
        )
    sin_a, cos_a, tan_a = np.sin(s.alpha), np.cos(s.alpha), np.tan(s.alpha)
    if _driving_moment_over_R(s, 1.0 if not s.has_passive else np.inf) <= 0:
        return LEMResult(np.nan, "Bishop", False, 0, message="non-positive driving moment")

    nonlinear = any(m.nonlinear for m in s.materials)
    sigma_n = _initial_sigma_n(s)
    c, tp = _strength(s, sigma_n)

    f = f0 if f0 is not None else ordinary(s).fos
    if not np.isfinite(f) or f <= 0:
        f = 1.0

    def passive_balance(F):
        ma = cos_a + sin_a * tp / F
        _, qy, _ = frame_ext(s, F)
        resistance = np.sum((c * s.b + (s.Wv - qy - s.u * s.b) * tp) / ma)
        return (F * _driving_moment_over_R(s, F) - resistance) / max(1.0, float(s.W.sum()))

    for it in range(1, max_iter + 1):
        if s.has_passive:
            lower = max(0.0, float(np.max(-sin_a * tp / cos_a)))
            solved, _ = _passive_root(passive_balance, f, lower, tol, max_iter)
            if not np.isfinite(solved):
                return LEMResult(np.nan, "Bishop", False, it, message="did not converge")
            previous, f = f, solved
        m_a = cos_a + sin_a * tp / f
        if np.any(m_a <= 1e-9):
            return LEMResult(
                np.nan,
                "Bishop",
                False,
                it,
                float(m_a.min()),
                "m_alpha <= 0 (steep negative base angle)",
            )
        _, qy, _ = frame_ext(s, f)
        eff_w = s.Wv - qy - s.u * s.b
        driving = _driving_moment_over_R(s, f)
        if driving <= 0:
            return LEMResult(np.nan, "Bishop", False, it, message="non-positive driving moment")
        f_new = np.sum((c * s.b + eff_w * tp) / m_a) / driving
        if nonlinear:
            n_eff = (eff_w - c * s.b * tan_a / f_new) / m_a
            sigma_n = np.maximum(n_eff / s.l, 0.0)
            c, tp = _strength(s, sigma_n)
        done = abs(f_new - f) < tol * max(1.0, abs(f))
        if s.has_passive:
            done = not nonlinear or (it > 1 and abs(f_new - previous) < tol * max(1.0, f))
            done = done and abs(passive_balance(f_new)) <= max(tol, 1e-10) * max(1.0, f_new)
        if done:
            m_a = cos_a + sin_a * tp / f_new
            n_eff = (eff_w - c * s.b * tan_a / f_new) / m_a
            res = LEMResult(float(f_new), "Bishop", True, it, float(m_a.min()))
            return check_admissibility(res, m_a, c * s.l + n_eff * tp, s.W, m_alpha_min)
        f = f_new

    return LEMResult(float(f), "Bishop", False, max_iter, message="did not converge")
