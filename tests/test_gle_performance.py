"""Keep ordinary layered solutions out of the expensive fallback scan."""

import importlib

import numpy as np
import pytest

from slipsurface.lem.slicing import make_slices
from slipsurface.optimizer.search import polyline_from_params
from slipsurface.project import layered_example_project


@pytest.mark.parametrize("tol", [0.005, 1e-6])
@pytest.mark.parametrize("interslice", ["constant", "half-sine", "clipped-sine"])
def test_layered_solution_balances_without_excessive_residual_evaluations(
    monkeypatch, tol, interslice
):
    gle = importlib.import_module("slipsurface.lem.gle")
    project = layered_example_project()
    geom = project.build_geometry()
    # Reproduce a regular search candidate that previously needed thousands
    # of residual evaluations at the default project tolerance (0.005).
    rng = np.random.default_rng(17)
    surface = polyline_from_params(
        geom, float(rng.uniform(5, 20)), float(rng.uniform(45, 65)), rng.uniform(0.1, 0.7, 4)
    )
    slices = make_slices(geom, surface, project.build_materials(), opts=project.slice_options())
    reference = gle.solve_gle(slices, interslice=interslice, tol=1e-10, max_outer=75)
    assert reference.ok and reference.admissible

    calls = 0
    residuals = gle._residuals

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return residuals(*args, **kwargs)

    monkeypatch.setattr(gle, "_residuals", counted)
    result = gle.solve_gle(slices, interslice=interslice, tol=tol, max_outer=75)
    assert result.ok and result.admissible, result
    assert result.fos == pytest.approx(reference.fos, rel=1e-8)
    assert result.lam == pytest.approx(reference.lam, abs=1e-8)
    # Count numerical work, not wall time: this remains reliable on slow CI.
    # The converged solve needs about 20 evaluations; allow ample variation
    # between SciPy versions without permitting a nested fallback scan.
    assert calls < 100

    frame = gle._Frame(slices)
    c, tp = gle._strengths_frame(slices, frame)
    fint = gle.interslice_function(interslice, frame.xb)
    _, normal_eff, _ = gle._state(result.fos, -result.lam * fint, frame, c, tp)
    c, tp = gle._strengths_frame(slices, frame, np.maximum(normal_eff / frame.l, 0))
    assert gle._balanced(result.fos, -result.lam, frame, c, tp, fint)
