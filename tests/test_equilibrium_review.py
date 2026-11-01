"""Regressions for equilibrium, incomplete seismic cases and contour boundaries."""

from types import SimpleNamespace

import numpy as np
import pytest

from slipsurface.analysis import report_text, run_analysis
from slipsurface.geometry import PolylineSurface, simple_slope
from slipsurface.lem import LEMResult, SliceOptions, analyze
from slipsurface.materials import MohrCoulomb
from tests.models import default_project
from slipsurface.ui.cad.fs_contour import build_grid


@pytest.mark.parametrize("tol", [0.005, 1e-6, 1e-10])
@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("kh", [0.0, 0.15])
def test_spencer_cohesionless_plane_satisfies_all_force_balances(tol, mirror, kh):
    geom = simple_slope(10, 0.25, toe_x=10, left_bench=10, right_bench=80, depth_below_toe=5)
    angle = np.radians(30)
    pts = np.array([[10, 0], [10 + 11 / np.tan(angle), 11]])
    if mirror:
        from shapely.affinity import scale

        geom.surface = geom.surface[::-1] * [-1, 1]
        for region in geom.regions:
            region.polygon = scale(region.polygon, xfact=-1, yfact=1, origin=(0, 0))
        pts = pts[::-1] * [-1, 1]
    mat = MohrCoulomb("Soil 1", gamma=18, c=0, phi=38)
    result, slices = analyze(
        geom,
        PolylineSurface(pts),
        {mat.name: mat},
        method="spencer",
        opts=SliceOptions(n_slices=50, kh=kh),
        tol=tol,
    )
    # Independent rigid-block balance: F = N tan(phi) / driving shear.
    expected = (
        (np.cos(angle) - kh * np.sin(angle))
        * np.tan(np.radians(38))
        / (np.sin(angle) + kh * np.cos(angle))
    )
    # A cohesionless plane under seismic loading can make Spencer's recurrence
    # singular. Rejecting it is acceptable; accepting an unbalanced FS is not.
    if kh and not result.ok:
        assert not result.converged
        assert result.message
        return
    assert result.ok and result.admissible, result
    assert result.fos == pytest.approx(expected, rel=1e-6)
    if kh:
        assert result.fos < 1.0

    from slipsurface.lem.gle import _Frame, _state, _strengths_frame

    frame = _Frame(slices)
    c, tp = _strengths_frame(slices, frame)
    e, normal_eff, _ = _state(result.fos, -result.lam * np.ones(slices.n + 1), frame, c, tp)
    normal = normal_eff + frame.U
    shear = (c * frame.l + normal_eff * tp) / result.fos
    weight = slices.W.sum()
    assert abs(result.lam * e[-1]) < 1e-7 * weight
    assert abs(np.sum(normal * frame.cos + shear * frame.sin - frame.Wv)) < 1e-7 * weight
    assert abs(np.sum(-normal * frame.sin + shear * frame.cos - frame.Fh)) < 1e-7 * weight


@pytest.mark.parametrize("surface_type", ["user", "circular"])
@pytest.mark.parametrize("failed_kv", [0.25, -0.25])
@pytest.mark.parametrize("failure_kind", ["unconverged", "inadmissible"])
def test_incomplete_vertical_cases_cannot_supply_a_critical_result(
    monkeypatch, surface_type, failed_kv, failure_kind
):
    p = default_project()
    p.methods.methods = ["ordinary"]
    p.surfaces.surface_type = surface_type
    p.surfaces.user_surface = [[10, 0], [25, -2], [45, 10]]
    p.seismic.kv = 0.25
    p.seismic.both_vertical = True
    calls = []
    reason = "no equilibrium" if failure_kind == "unconverged" else "base tension"

    def analyze_case(*args, opts, **kwargs):
        calls.append(opts.kv)
        if opts.kv == failed_kv:
            return LEMResult(
                0.5,
                "Ordinary",
                failure_kind != "unconverged",
                1,
                message=reason,
                admissible=False,
                issue=reason,
            ), object()
        return LEMResult(1.5, "Ordinary", True, 1), object()

    def search_case(geom, mats, settings, *args):
        result, _ = analyze_case(opts=settings.slice_opts)
        if not result.ok or not result.admissible:
            raise RuntimeError(reason)
        return SimpleNamespace(fos=result.fos, kv=None)

    monkeypatch.setattr("slipsurface.analysis.analyze", analyze_case)
    monkeypatch.setattr("slipsurface.analysis.search", search_case)
    status = {}
    result = run_analysis(p, status=status)
    assert calls == [0.25, -0.25]
    assert "ordinary" not in result.results
    assert result.global_minimum() is None
    assert f"kv = {failed_kv:g}" in result.errors["ordinary"]
    assert reason in result.errors["ordinary"]
    assert status["done"]["ordinary"] == result.errors["ordinary"]


def test_both_vertical_failures_retain_both_diagnostics(monkeypatch):
    p = default_project()
    p.methods.methods = ["ordinary"]
    p.seismic.kv = 0.25

    def fail(geom, mats, settings, *args):
        raise RuntimeError(f"failed direction {settings.slice_opts.kv:g}")

    monkeypatch.setattr("slipsurface.analysis.search", fail)
    result = run_analysis(p)
    for kv in (0.25, -0.25):
        assert f"kv = {kv:g}: failed direction {kv:g}" in result.errors["ordinary"]


def test_real_seismic_loss_of_resistance_is_reported_as_incomplete():
    p = default_project()
    p.external = [[0, -5], [30, -5], [30, 10], [12.5, 10], [10, 0], [0, 0]]
    p.materials[0].c = 0
    p.materials[0].phi = 35
    p.surfaces.surface_type = "user"
    p.surfaces.user_surface = [[10, 0], [17, 7 * np.sqrt(3)]]
    p.methods.methods = ["ordinary", "janbu_simplified"]
    p.seismic.kh = 0.3
    p.seismic.kv = -0.5
    p.seismic.both_vertical = False
    down = run_analysis(p)
    for result in down.results.values():
        assert result.fos == pytest.approx(0.2368718928)
    assert len(down.results) == 2

    p.seismic.both_vertical = True
    both = run_analysis(p)
    assert not both.results
    for method in p.methods.methods:
        assert "kv = 0.5" in both.errors[method]
    assert "kv = 0.5" in report_text(both)
    assert "Global minimum:" not in report_text(both)


@pytest.mark.parametrize("axis", [0, 1])
def test_contour_includes_critical_sample_on_upper_boundary(axis):
    rng = np.random.default_rng(42)
    centres = np.column_stack(
        [rng.uniform(0, 8, 100), rng.uniform(1, 5, 100), np.ones(100), np.full(100, 2.0)]
    )
    centres = np.vstack([centres, [10, 3, 1, 0.7]])
    if axis == 1:
        centres[:, [0, 1]] = centres[:, [1, 0]]
    grid = build_grid(centres)
    assert grid is not None
    assert np.nanmin(grid["values"]) == pytest.approx(0.7)
    assert grid["crit"] == pytest.approx((*centres[-1, :2], 0.7))
    index = np.argwhere(grid["values"] == 0.7)[0]
    assert index[1 - axis] == grid["nx" if axis == 0 else "ny"] - 1


def test_contour_does_not_fold_outliers_into_boundary_cells():
    # Keep percentile limits exactly [0, 10], with noncritical outliers beyond them.
    xy = np.array([(x, y) for x in range(11) for y in range(11)], dtype=float)
    centres = np.column_stack([xy, np.ones(len(xy)), np.full(len(xy), 2.0)])
    centres[60, 3] = 0.7
    grid = build_grid(centres, n=10)
    extra = np.array([[100, 100, 1, 1.0], [-100, -100, 1, 1.0]])
    with_outliers = build_grid(np.vstack([centres, extra]), n=10)
    np.testing.assert_equal(with_outliers["values"], grid["values"])
