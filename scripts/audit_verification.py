"""Reproducible safety-factor discrepancy audit for published verification cases.

Read-only: the analysis runs the real solver; no result is forced to a
reference. The important evidence is the critical surface, slice materials
and whether reinforcement is mobilized at that surface.

Usage:
  python scripts/audit_verification.py --case all --effort fast
  python scripts/audit_verification.py --case acads-3a --effort fine
  python scripts/audit_verification.py --case acads-3a --effort fast --restrict-seam
  python scripts/audit_verification.py --case borges --effort fast
  python scripts/audit_verification.py --case talbingo-2a --effort normal
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slipsurface.analysis import run_analysis  # noqa: E402
from slipsurface.project import (  # noqa: E402
    acads_2a_project,
    acads_2b_project,
    acads_3a_project,
    borges_cardoso_case2_project,
)

CASES = {
    "acads-3a": acads_3a_project,
    "borges": borges_cardoso_case2_project,
    "talbingo-2a": acads_2a_project,
    "talbingo-2b": acads_2b_project,
}


def audit(name: str, effort: str, seed: int, restrict_seam: bool) -> dict:
    project = CASES[name]()
    project.surfaces.effort = effort
    project.surfaces.seed = seed
    # Strictly a diagnostic alternative: the user's supplied Bentley
    # ACADS 3(a) figure places the reference wedge near x=42..73 m.
    # Never silently restrict the unbounded baseline search or label
    # this as an independent global minimum.
    if name == "acads-3a" and restrict_seam:
        project.surfaces.left_range = [40.0, 46.0]
        project.surfaces.right_range = [67.5, 78.0]
    results = run_analysis(project)
    out = {
        "case": name,
        "search_effort": effort,
        "seed": seed,
        "diagnostic_seam_restriction": restrict_seam and name == "acads-3a",
        "errors": results.errors,
        "methods": {},
    }
    for method, found in results.results.items():
        slices = found.slices
        shape = found.surface
        if hasattr(shape, "r"):
            surface = {
                "type": "circle",
                "center": [float(shape.xc), float(shape.yc)],
                "radius": float(shape.r),
            }
        else:
            surface = {
                "type": type(shape).__name__,
                "vertices": [[float(a), float(b)] for a, b in shape.points(
                    slices.x_exit, slices.x_entry, 24
                )],
            }
        supports = []
        for f in slices.support_forces:
            supports.append(
                {
                    "label": f.label,
                    "capacity_kN_per_m": float(f.T),
                    "mobilized_kN_per_m": float(f.mobilized(found.fos)),
                    "governing": f.governing,
                    "embedment_in_m": float(f.L_in),
                    "embedment_out_m": float(f.L_out),
                    "intersection": [float(f.x), float(f.y)],
                    "direction": [float(f.fx), float(f.fy)],
                }
            )
        base_names = [slices.materials[int(i)].name for i in slices.mat_idx]
        out["methods"][method] = {
            "fos": float(found.fos),
            "converged": bool(found.lem.ok),
            "admissible": bool(found.lem.admissible),
            "admissibility_issue": found.lem.issue,
            "lambda": float(found.lem.lam) if math.isfinite(found.lem.lam) else None,
            "x_exit": float(slices.x_exit),
            "x_entry": float(slices.x_entry),
            "n_slices": int(slices.n),
            "n_evaluations": int(found.n_evals),
            "base_material_counts": {
                mat: base_names.count(mat) for mat in sorted(set(base_names))
            },
            "max_pore_pressure_kpa": float(np.max(slices.u)),
            "supports_crossing_surface": supports,
            "surface": surface,
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=(*CASES, "all"), default="all")
    parser.add_argument("--effort", choices=("fast", "normal", "fine"), default="fast")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--restrict-seam", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    names = list(CASES) if args.case == "all" else [args.case]
    data = [audit(name, args.effort, args.seed, args.restrict_seam) for name in names]
    payload = json.dumps(data, indent=2, allow_nan=False)
    print(payload)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0 if all(not item["errors"] for item in data) else 1


if __name__ == "__main__":
    raise SystemExit(main())
