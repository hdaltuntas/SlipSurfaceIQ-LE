"""LEM_Engine — vertical slicing and limit equilibrium solvers."""

from __future__ import annotations

from slipsurface.lem.bishop import LEMResult, bishop_simplified, ordinary
from slipsurface.lem.gle import (
    corps1,
    corps2,
    janbu_corrected,
    janbu_simplified,
    lowe_karafiath,
    morgenstern_price,
    solve_gle,
    spencer,
)
from slipsurface.lem.slicing import GAMMA_W, SliceOptions, SliceSet, SlicingError, make_slices

# key -> (solver, display name, circular_only)
METHODS: dict[str, tuple] = {
    "bishop": (bishop_simplified, "Bishop simplified", True),
    "corps1": (corps1, "Corps of Engineers #1", False),
    "corps2": (corps2, "Corps of Engineers #2", False),
    "gle": (morgenstern_price, "GLE/Morgenstern-Price", False),
    "janbu_simplified": (janbu_simplified, "Janbu simplified", False),
    "janbu_corrected": (janbu_corrected, "Janbu corrected", False),
    "lowe_karafiath": (lowe_karafiath, "Lowe-Karafiath", False),
    "ordinary": (ordinary, "Ordinary/Fellenius", True),
    "spencer": (spencer, "Spencer", False),
}
SOLVERS = {k: v[0] for k, v in METHODS.items()}


def method_name(key: str) -> str:
    return METHODS[key][1] if key in METHODS else key


__all__ = ["GAMMA_W", "LEMResult", "METHODS", "SOLVERS", "SliceOptions", "SliceSet",
           "SlicingError", "analyze", "analyze_circle", "bishop_simplified", "make_slices",
           "method_name", "morgenstern_price", "ordinary", "solve_gle", "spencer"]


def analyze(geom, surf, materials, n_slices: int | None = None, method: str = "bishop",
            opts: SliceOptions | None = None, **solver_kw):
    """Slice + solve. Returns (LEMResult, SliceSet | None).

    Ordinary/Fellenius on a non-circular surface uses its force form.
    """
    try:
        s = make_slices(geom, surf, materials, n_slices=n_slices, opts=opts)
    except SlicingError as exc:
        return LEMResult(float("nan"), method, False, 0, message=str(exc)), None
    fn = SOLVERS[method]
    if method in ("bishop", "ordinary"):
        kw = {k: v for k, v in solver_kw.items() if k in ("tol", "max_iter")}
    else:
        kw = {k: v for k, v in solver_kw.items() if k in ("tol", "max_outer")}
        if "max_iter" in solver_kw:
            kw["max_outer"] = solver_kw["max_iter"]
        if method == "gle":
            kw.update({k: v for k, v in solver_kw.items()
                       if k in ("interslice", "f_start", "f_end")})
    return fn(s, **kw), s


analyze_circle = analyze   # backwards-compatible name
