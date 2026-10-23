"""Critical slip surface search.

Two surface families, one optimizer (differential evolution + Nelder-Mead):

Circular  — x1, x2 on the ground surface and theta, half of the central
            angle subtended by the chord, (0, 90°]. The centre lies on the
            chord's perpendicular bisector:  R = (L/2)/sin(theta).
            Every candidate cuts the ground at x1 and x2.

B-spline  — x1, x2 on the ground surface and n_ctrl interior depths
            d_k in [0, 1]. Control ordinates hang below the chord:
                y_k = y_chord(g_k) - d_k * (y_chord(g_k) - y_bottom)
            at the Greville abscissae g_k. With `convex_only` the control
            polygon is replaced by its lower convex hull, which (variation
            diminishing property) makes the spline itself convex — a
            projection, so every candidate stays admissible.

Polyline  — the Slide2-style non-circular surface: straight segments through
            x1, n_ctrl interior vertices (equally spaced in x, same depth
            parametrisation as the spline) and x2; `convex_only` keeps the
            lower convex hull. Kinks are real: the surface is not smoothed.

Admissibility: surfaces whose converged solution has m_alpha < 0.2 on any
slice (Whitman & Bailey 1967; Slide2 "Check m-alpha < 0.2") or a negative
mobilisable base shear (c l + N' tan phi < 0, base in tension) are rejected.
Without these, Spencer/GLE return non-physical, very low FoS for surfaces
with steep negative base angles at the toe and the search exploits them.

Slope limits: x1 is restricted to `left_range`, x2 to `right_range`; a
surface whose actual exit/entry falls outside them is penalised.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from collections.abc import Callable
from typing import cast

import numpy as np
from scipy.optimize import differential_evolution, minimize

from slipsurface.geometry import (
    CircularSurface,
    PolylineSurface,
    SlopeGeometry,
    SplineSurface,
)
from slipsurface.lem import METHODS, LEMResult, SliceOptions, SliceSet, analyze
from slipsurface.materials import Material

PENALTY = 1.0e3


# ------------------------------------------------------------ surfaces
def circle_from_chord(geom: SlopeGeometry, x1: float, x2: float, theta: float) -> CircularSurface:
    if x2 < x1:
        x1, x2 = x2, x1
    p1 = np.array([x1, float(geom.ground_y(x1))])
    p2 = np.array([x2, float(geom.ground_y(x2))])
    chord = p2 - p1
    half = 0.5 * np.hypot(*chord)
    if half < 1e-9:
        raise ValueError("degenerate chord")
    n_up = np.array([-chord[1], chord[0]]) / (2 * half)  # left normal of p1->p2 points up
    theta = float(np.clip(theta, 1e-3, np.pi / 2))
    centre = 0.5 * (p1 + p2) + n_up * half / np.tan(theta)
    return CircularSurface(float(centre[0]), float(centre[1]), float(half / np.sin(theta)))


def _lower_hull(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Ordinates of the lower convex hull of (x, y) evaluated at x."""
    hull: list[int] = []
    for i in range(len(x)):
        while len(hull) >= 2:
            a, b = hull[-2], hull[-1]
            cross = (x[b] - x[a]) * (y[i] - y[a]) - (y[b] - y[a]) * (x[i] - x[a])
            if cross <= 0:  # b is above segment a-i -> drop
                hull.pop()
            else:
                break
        hull.append(i)
    return np.interp(x, x[hull], y[hull])


def _vertex_x(x1: float, x2: float, n_inner: int, kind: str) -> np.ndarray:
    """x of all vertices (ends included) for a spline (Greville abscissae) or
    a polyline (equally spaced)."""
    if kind == "polyline":
        return np.linspace(x1, x2, n_inner + 2)
    return SplineSurface(x1, x2, np.zeros(n_inner + 2)).control_points()[:, 0]


def polyline_from_params(
    geom: SlopeGeometry, x1: float, x2: float, depths, convex_only: bool = True
) -> PolylineSurface:
    if x2 < x1:
        x1, x2 = x2, x1
    if x2 - x1 < 1e-6:
        raise ValueError("degenerate polyline")
    depths = np.clip(np.asarray(depths, dtype=float), 0.0, 1.0)
    gx = _vertex_x(x1, x2, len(depths), "polyline")
    y1, y2 = float(geom.ground_y(x1)), float(geom.ground_y(x2))
    chord = y1 + (y2 - y1) * (gx - x1) / (x2 - x1)
    room = np.minimum(chord[1:-1] - geom.bounds[1], 0.6 * (x2 - x1)) * 0.98
    y = chord.copy()
    y[1:-1] = chord[1:-1] - depths * np.maximum(room, 0.0)
    if convex_only:
        y = _lower_hull(gx, y)
    return PolylineSurface(np.column_stack([gx, y]))


def spline_from_params(
    geom: SlopeGeometry, x1: float, x2: float, depths, convex_only: bool = True
) -> SplineSurface:
    if x2 < x1:
        x1, x2 = x2, x1
    if x2 - x1 < 1e-6:
        raise ValueError("degenerate spline")
    depths = np.clip(np.asarray(depths, dtype=float), 0.0, 1.0)
    n = len(depths) + 2
    probe = SplineSurface(x1, x2, np.zeros(n))
    gx = probe.control_points()[:, 0]
    y1, y2 = float(geom.ground_y(x1)), float(geom.ground_y(x2))
    chord = y1 + (y2 - y1) * (gx - x1) / (x2 - x1)
    ybot = geom.bounds[1]
    # depth limited by the model bottom and by the chord length (no absurdly
    # deep, steep-sided shapes)
    room = np.minimum(chord[1:-1] - ybot, 0.6 * (x2 - x1)) * 0.98
    y = chord.copy()
    y[1:-1] = chord[1:-1] - depths * np.maximum(room, 0.0)
    if convex_only:
        y = _lower_hull(gx, y)
    return SplineSurface(x1, x2, y)


def spline_params_from_surface(
    geom: SlopeGeometry, surf, x1: float, x2: float, n_ctrl: int, kind: str = "spline"
) -> np.ndarray:
    """Inverse of spline/polyline_from_params: depths that make the surface
    follow `surf` (used to seed the search with the critical circle)."""
    gx = _vertex_x(x1, x2, n_ctrl, kind)[1:-1]
    y1, y2 = float(geom.ground_y(x1)), float(geom.ground_y(x2))
    chord = y1 + (y2 - y1) * (gx - x1) / (x2 - x1)
    ybot = geom.bounds[1]
    room = np.minimum(chord - ybot, 0.6 * (x2 - x1)) * 0.98
    d = (chord - surf.y(gx)) / np.where(room > 1e-9, room, np.inf)
    return np.concatenate([[x1, x2], np.clip(np.nan_to_num(d), 0.0, 1.0)])


# ------------------------------------------------------------ settings
@dataclass
class SearchSettings:
    method: str = "bishop"  # bishop | spencer | gle
    surface_type: str = "circular"  # circular | polyline | spline
    n_slices: int = 30
    popsize: int = 20
    maxiter: int = 80
    tol: float = 1e-4
    seed: int | None = 0
    theta_deg: tuple[float, float] = (5.0, 85.0)
    n_ctrl: int = 4  # interior spline control points
    convex_only: bool = True
    check_admissibility: bool = True  # reject m_alpha < 0.2 and base tension (see lem.bishop)
    left_range: tuple[float, float] | None = None
    right_range: tuple[float, float] | None = None
    min_chord: float = 1.0  # m, ignore tiny surfaces
    slice_opts: SliceOptions = field(default_factory=SliceOptions)
    solver_kw: dict = field(default_factory=dict)  # e.g. interslice function, tol
    polish: bool = True
    keep_top: int = 25  # lowest distinct surfaces returned for display


@dataclass
class SearchResult:
    surface: object
    fos: float
    lem: LEMResult
    slices: SliceSet
    n_evals: int
    top: list[tuple[float, object]] = field(default_factory=list)
    message: str = ""
    method: str = "bishop"
    kv: float | None = None  # governing vertical coefficient; positive is upward
    # every admissible circle tried by the search: columns xc, yc, r, FoS
    # (circular searches only; drawn as the slip-centre FS contour map)
    centres: np.ndarray | None = None


class SearchCancelled(RuntimeError):
    pass


def _range(r, geom) -> tuple[float, float]:
    if r is None:
        return geom.x_min, geom.x_max
    a, b = sorted(map(float, r))
    a, b = max(a, geom.x_min), min(b, geom.x_max)
    if b - a < 1e-6:
        raise ValueError("Uç aralığı model sınırları içinde değil.")
    return a, b


# --------------------------------------------------------------- search
def search(
    geom: SlopeGeometry,
    materials: dict[str, Material],
    settings: SearchSettings | None = None,
    progress: Callable[[int, float], bool | None] | None = None,
    status: dict | None = None,
) -> SearchResult:
    """Global minimum FoS. `progress(generation, best)` returning True cancels.

    `status`, if given, is updated in place while the search runs (for a
    progress display): stage (presearch | evolution | polish | vertices |
    refine | final), generation, maxiter, evaluated, valid, rejected, best,
    current (last admissible FoS) and surface_type."""
    st = settings or SearchSettings()
    stat = status if status is not None else {}
    stat.update(
        stage="evolution",
        generation=0,
        maxiter=st.maxiter,
        evaluated=0,
        valid=0,
        rejected=0,
        best=float("nan"),
        current=float("nan"),
        surface_type=st.surface_type,
    )
    if st.surface_type in ("spline", "polyline") and st.method == "bishop":
        raise ValueError(
            "Simplified Bishop yalnızca dairesel yüzeyler için geçerlidir; "
            "dairesel olmayan yüzeylerde Spencer veya GLE seçin."
        )
    if st.method not in METHODS:
        raise ValueError(f"Bilinmeyen yöntem: {st.method}")
    sopts = replace(st.slice_opts, n_slices=st.n_slices)

    def run(surf):
        return analyze(geom, surf, materials, method=st.method, opts=sopts, **st.solver_kw)

    L = _range(st.left_range, geom)
    R = _range(st.right_range, geom)
    tol_x = 1e-6 + 0.002 * (geom.x_max - geom.x_min)

    if st.surface_type == "circular":
        bounds = [L, R, tuple(np.radians(st.theta_deg))]

        def build(p):
            return circle_from_chord(geom, p[0], p[1], p[2])
    elif st.surface_type in ("spline", "polyline"):
        bounds = [L, R] + [(0.0, 1.0)] * st.n_ctrl
        make = spline_from_params if st.surface_type == "spline" else polyline_from_params

        def build(p):
            return make(geom, p[0], p[1], p[2:], st.convex_only)
    else:
        raise ValueError(f"unknown surface type '{st.surface_type}'")

    seen: list[tuple[float, object, tuple[float, float]]] = []
    n_evals = 0
    gen = 0
    best_seen = np.nan

    def check_cancel():
        if progress is not None and progress(gen, best_seen):
            raise SearchCancelled()

    def evaluate(p) -> float:
        check_cancel()
        if abs(p[1] - p[0]) < st.min_chord:
            return PENALTY
        try:
            surf = build(p)
        except ValueError:
            return PENALTY
        return evaluate_surface(surf)

    def evaluate_surface(surf) -> float:
        nonlocal n_evals, best_seen
        check_cancel()
        n_evals += 1
        stat["evaluated"] = n_evals
        res, s = run(surf)
        if (
            not res.ok
            or (st.check_admissibility and not res.admissible)
            or not (
                L[0] - tol_x <= s.x_exit <= L[1] + tol_x
                and R[0] - tol_x <= s.x_entry <= R[1] + tol_x
            )
        ):
            # no solution, numerically / physically unreliable, or the actual
            # ends lie outside the slope limits
            stat["rejected"] += 1
            return PENALTY
        seen.append((res.fos, surf, (s.x_exit, s.x_entry)))
        stat["valid"] += 1
        stat["current"] = res.fos
        if not np.isfinite(best_seen) or res.fos < best_seen:
            best_seen = res.fos
            stat["best"] = res.fos
        return res.fos

    def callback(xk, convergence=None):
        nonlocal gen
        gen += 1
        stat["generation"] = gen
        if progress is not None:
            best = min((f for f, _, _ in seen), default=np.nan)
            if progress(gen, best):
                raise SearchCancelled()

    init = "sobol"
    popsize = st.popsize
    if st.surface_type in ("spline", "polyline"):
        stat["stage"] = "presearch"
        init, popsize = _seeded_population(geom, materials, st, bounds, progress, stat)
        stat.update(stage="evolution", generation=0, maxiter=st.maxiter, best=float("nan"))

    de = differential_evolution(
        evaluate,
        bounds,
        popsize=popsize,
        maxiter=st.maxiter,
        tol=st.tol,
        seed=st.seed,
        polish=False,
        init=init,
        updating="immediate",
        callback=callback,
    )
    x_best, f_best = de.x, de.fun

    if st.polish and f_best < PENALTY:
        stat["stage"] = "polish"
        lo = np.array([b[0] for b in bounds])
        hi = np.array([b[1] for b in bounds])
        nm = minimize(
            lambda p: evaluate(np.clip(p, lo, hi)),
            x_best,
            method="Nelder-Mead",
            options=dict(xatol=1e-4, fatol=1e-6, maxiter=600),
        )
        if nm.fun < f_best:
            x_best, f_best = np.clip(nm.x, lo, hi), nm.fun

    if f_best >= PENALTY:
        raise RuntimeError(
            "Kabul edilebilir kayma yüzeyi bulunamadı (uç aralıklarını ve geometriyi kontrol edin)."
        )

    surf = build(x_best)
    if st.surface_type == "polyline" and st.polish:
        stat["stage"] = "vertices"
        evaluate_surface.status = stat  # type: ignore[attr-defined]
        surf, f_best = _optimize_polyline(geom, surf, f_best, evaluate_surface, st)
    stat["stage"] = "final"
    lem, slices = run(surf)
    check_cancel()
    centres = None
    if st.surface_type == "circular" and seen:
        circles = [(cast(CircularSurface, sf), f) for f, sf, _ in seen]
        centres = np.asarray([[c.xc, c.yc, c.r, f] for c, f in circles], dtype=np.float64)
    return SearchResult(
        surf,
        lem.fos,
        lem,
        slices,
        n_evals,
        top=_distinct_top(seen, st.keep_top, geom),
        message=f"{gen} nesil, {n_evals} yüzey",
        method=st.method,
        centres=centres,
    )


def _optimize_polyline(geom, surf: PolylineSurface, f_best: float, evaluate_surface, st):
    """Slide2-style surface optimisation: every vertex moves freely (interior
    vertices in x and y, end vertices along the ground), Nelder-Mead on the
    vertex coordinates. Then one vertex is inserted in the middle of each
    segment and the polish is repeated."""

    def unpack(q, n):
        x1, x2 = sorted((q[0], q[1]))
        xi, yi = q[2 : 2 + n], q[2 + n :]
        x = np.concatenate([[x1], xi, [x2]])
        if np.any(np.diff(x) <= 1e-6) or x1 < geom.x_min or x2 > geom.x_max:
            raise ValueError("vertex order")
        y = np.concatenate([[float(geom.ground_y(x1))], yi, [float(geom.ground_y(x2))]])
        if np.any(y[1:-1] < geom.bounds[1]):
            raise ValueError("below model")
        if st.convex_only:
            y = _lower_hull(x, y)
        return PolylineSurface(np.column_stack([x, y]))

    def run_nm(pts, f0, maxiter):
        n = len(pts) - 2
        q0 = np.concatenate([[pts[0, 0], pts[-1, 0]], pts[1:-1, 0], pts[1:-1, 1]])

        def obj(q):
            try:
                return evaluate_surface(unpack(q, n))
            except ValueError:
                return PENALTY

        span = 0.02 * (geom.x_max - geom.x_min)
        simplex = [q0] + [q0 + span * e for e in np.eye(len(q0))]
        res = minimize(
            obj,
            q0,
            method="Nelder-Mead",
            options=dict(
                initial_simplex=np.array(simplex), xatol=1e-3, fatol=1e-5, maxiter=maxiter
            ),
        )
        if res.fun < f0:
            return unpack(res.x, n), float(res.fun)
        return None, f0

    stat = getattr(evaluate_surface, "status", None)
    stat = stat if stat is not None else {}
    best, fb = surf, f_best
    stat["stage"] = "vertices"
    new, f = run_nm(best.pts, fb, 300 + 60 * len(best.pts))
    if new is not None:
        best, fb = new, f
    # refine: add a vertex at the middle of every segment
    pts = best.pts
    mid = 0.5 * (pts[:-1] + pts[1:])
    dense = np.empty((len(pts) + len(mid), 2))
    dense[0::2], dense[1::2] = pts, mid
    stat["stage"] = "refine"
    new, f = run_nm(dense, fb, 300 + 60 * len(dense))
    if new is not None:
        best, fb = new, f
    return best, fb


def _seeded_population(
    geom, materials, st: SearchSettings, bounds, progress, stat: dict | None = None
):
    """Stage 1 for B-spline search: a quick circular search (Bishop) whose
    critical circle, fitted as a spline, seeds the DE population together
    with Sobol samples and perturbed copies of the seed."""
    from scipy.stats import qmc

    circ_st = SearchSettings(
        method="bishop",
        surface_type="circular",
        n_slices=st.n_slices,
        popsize=15,
        maxiter=40,
        seed=st.seed,
        polish=True,
        check_admissibility=st.check_admissibility,
        left_range=st.left_range,
        right_range=st.right_range,
        keep_top=1,
        slice_opts=st.slice_opts,
    )
    dim = len(bounds)
    lo = np.array([b[0] for b in bounds])
    hi = np.array([b[1] for b in bounds])
    m = int(np.ceil(np.log2(max(8, 10 * dim))))
    n_pop = 2**m
    rng = np.random.default_rng(st.seed)
    pop = qmc.scale(qmc.Sobol(dim, seed=st.seed).random_base2(m), lo, hi)

    def stage1_progress(gen, best):
        if stat is not None:
            stat.update(generation=gen, maxiter=circ_st.maxiter, best=best)
        return progress(-gen, best) if progress is not None else None

    try:
        circ = search(geom, materials, circ_st, stage1_progress)
    except SearchCancelled:
        raise
    except (RuntimeError, ValueError):
        return pop, n_pop // dim
    seed = spline_params_from_surface(
        geom, circ.surface, circ.slices.x_exit, circ.slices.x_entry, st.n_ctrl, st.surface_type
    )
    seed = np.clip(seed, lo, hi)
    n_seed = max(3, n_pop // 4)
    span = hi - lo
    jitter = rng.normal(0, 0.03, size=(n_seed - 1, dim)) * span
    pop[:n_seed] = np.clip(np.vstack([seed, seed + jitter]), lo, hi)
    return pop, n_pop // dim


def search_circular(geom, materials, settings=None, progress=None) -> SearchResult:
    """Backwards-compatible wrapper (circular surfaces)."""
    st = settings or SearchSettings()
    st.surface_type = "circular"
    return search(geom, materials, st, progress)


def _distinct_top(seen, k: int, geom) -> list[tuple[float, object]]:
    """Lowest-FoS surfaces, skipping near-duplicates (for display)."""
    tol = 0.01 * (geom.x_max - geom.x_min)
    out: list[tuple[float, object, tuple[float, float]]] = []
    for f, surf, ext in sorted(seen, key=lambda t: t[0]):
        if all(
            abs(ext[0] - e[0]) + abs(ext[1] - e[1]) > tol or abs(f - g) > 1e-3 for g, _, e in out
        ):
            out.append((f, surf, ext))
            if len(out) >= k:
                break
    return [(f, s) for f, s, _ in out]
