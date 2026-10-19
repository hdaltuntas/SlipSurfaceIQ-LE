"""Regression coverage for solver validity, cancellation and persistence."""
import importlib
from types import SimpleNamespace

import numpy as np
import pytest

from slipsurface.analysis import run_analysis
from slipsurface.lem import LEMResult, analyze, make_slices, ordinary
from slipsurface.optimizer import SearchCancelled, SearchSettings, circle_from_chord
from slipsurface.project import MaterialSpec, Project, default_project


def hb_case():
    p = default_project()
    p.materials = [MaterialSpec("Zemin 1", "HB", sigma_ci=8000, gsi=35, mi=8, d=.3)]
    g = p.build_geometry()
    surf = circle_from_chord(g, 10, 45, np.radians(35))
    return p, g, surf


@pytest.mark.parametrize("method", ["spencer", "gle", "janbu_simplified", "janbu_corrected",
                                    "corps1", "corps2", "lowe_karafiath"])
def test_iteration_limit_rejects_unconverged_hb(method):
    p, g, surf = hb_case()
    short, _ = analyze(g, surf, p.build_materials(), method=method, max_iter=1)
    full, _ = analyze(g, surf, p.build_materials(), method=method, max_iter=50)
    assert not short.ok and "converge" in short.message
    assert full.ok


def test_ordinary_passive_iteration_limit():
    p, g, surf = hb_case()
    s = make_slices(g, surf, p.build_materials())
    s.Qx_p[:] = 1.0
    assert s.has_passive
    assert not ordinary(s, max_iter=1).ok
    assert ordinary(s).ok


@pytest.mark.parametrize("method", ["bishop", "ordinary", "spencer", "gle", "janbu_simplified",
                                    "janbu_corrected", "corps1", "corps2", "lowe_karafiath"])
def test_solver_settings_are_forwarded(monkeypatch, method):
    import slipsurface.lem as lem
    p, g, surf = hb_case()
    received = {}
    def solver(s, **kw):
        received.update(kw)
        return LEMResult(1.0, method, True, 1)
    monkeypatch.setitem(lem.SOLVERS, method, solver)
    analyze(g, surf, p.build_materials(), method=method, tol=2e-7, max_iter=17,
            interslice="trapezoidal", f_start=.2, f_end=.7)
    assert received["tol"] == 2e-7
    assert received["max_iter" if method in ("bishop", "ordinary") else "max_outer"] == 17
    if method == "gle":
        assert received["interslice"] == "trapezoidal"


@pytest.mark.parametrize("enabled", [True, False])
def test_user_surface_admissibility(monkeypatch, enabled):
    p = default_project()
    p.surfaces.surface_type = "user"
    p.surfaces.user_surface = [[10, 0], [25, -2], [45, 10]]
    p.methods.methods = ["spencer"]
    p.advanced.check_admissibility = enabled
    rejected = LEMResult(.9, "Spencer", True, 5, admissible=False, issue="base tension")
    monkeypatch.setattr("slipsurface.analysis.analyze", lambda *a, **kw: (rejected, object()))
    results = run_analysis(p)
    assert ("spencer" in results.results) is not enabled
    if enabled:
        assert results.errors["spencer"] == "base tension"
        assert results.global_minimum() is None


def test_seed_cancellation_propagates(monkeypatch):
    mod = importlib.import_module("slipsurface.optimizer.search")
    p = default_project()
    def cancel(*a, **kw):
        raise SearchCancelled()
    monkeypatch.setattr(mod, "search", cancel)
    with pytest.raises(SearchCancelled):
        mod._seeded_population(p.build_geometry(), p.build_materials(), SearchSettings(),
                               [(0, 20), (35, 55)] + [(0, 1)] * 4, None)


@pytest.mark.parametrize("stage", ["initial", "polish", "polyline"])
def test_cancellation_during_evaluation(monkeypatch, stage):
    mod = importlib.import_module("slipsurface.optimizer.search")
    p = default_project()
    stopped = stage == "initial"
    def de(fn, bounds, **kw):
        q = np.array([10, 45, .6]) if stage != "polyline" else np.array([10, 45, .2, .2])
        return SimpleNamespace(x=q, fun=fn(q))
    def minimize(fn, q, **kw):
        nonlocal stopped
        if stage == "polish":
            stopped = True
        return SimpleNamespace(x=q, fun=fn(q))
    def refine(g, surf, f, evaluate, st):
        nonlocal stopped
        stopped = True
        evaluate(surf)
        pytest.fail("Cancellation was ignored")
    monkeypatch.setattr(mod, "differential_evolution", de)
    monkeypatch.setattr(mod, "minimize", minimize)
    monkeypatch.setattr(mod, "_optimize_polyline", refine)
    monkeypatch.setattr(mod, "_seeded_population", lambda *a: ("sobol", 5))
    monkeypatch.setattr(mod, "analyze", lambda *a, **kw:
                        (LEMResult(1.2, "Spencer", True, 1), SimpleNamespace(x_exit=10, x_entry=45)))
    st = SearchSettings(method="spencer", surface_type="polyline" if stage == "polyline" else "circular", n_ctrl=2)
    with pytest.raises(SearchCancelled):
        mod.search(p.build_geometry(), p.build_materials(), st, lambda *a: stopped)


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_failed_save_preserves_existing_file(tmp_path, monkeypatch, failure):
    path = tmp_path / "model.slp.json"
    p = default_project()
    p.save(path)
    before = path.read_bytes()
    p.materials[0].c += 10
    def fail(*a):
        raise OSError("simulated write failure")
    monkeypatch.setattr(f"slipsurface.project.os.{failure}", fail)
    with pytest.raises(OSError):
        p.save(path)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_save_replaces_existing_file(tmp_path):
    path = tmp_path / "model.slp.json"
    p = default_project()
    p.save(path)
    p.materials[0].c += 10
    p.save(path)
    assert Project.load(path).to_dict() == p.to_dict()
    assert list(tmp_path.iterdir()) == [path]
