"""Independent geometric and root-solving regressions from the numerical audit."""

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface, PolylineSurface
from slipsurface.lem.gle import _root_1d
from slipsurface.loads import Support, SupportType, support_intersection


@pytest.mark.parametrize("mirror", [False, True])
def test_long_support_crossing_short_surface_domain(mirror):
    sign = -1 if mirror else 1
    points = np.array([[499.0, 0.0], [501.0, 0.0]])
    points[:, 0] *= sign
    surf = PolylineSurface(points[::-1] if mirror else points)
    support = Support((0.0, 1.0), (sign * 1000.0, -1.0), SupportType())
    result = support_intersection(support, surf, *surf.x_range())
    # Linear interpolation gives y=0 at exactly half of the support length.
    np.testing.assert_allclose(result, [sign * 500.0, 0.0], atol=1e-8)


@pytest.mark.parametrize("mirror", [False, True])
def test_short_polyline_crossing_cannot_be_skipped(mirror):
    sign = -1 if mirror else 1
    points = np.array([[0, -1], [501, -1], [501.1, 1], [501.2, -1], [1000, -1]])
    points[:, 0] *= sign
    surf = PolylineSurface(points[::-1] if mirror else points)
    support = Support((0.0, 0.0), (sign * 1000.0, 0.0), SupportType())
    result = support_intersection(support, surf, *surf.x_range())
    # The first segment reaches y=0 halfway between x=501 and x=501.1.
    np.testing.assert_allclose(result, [sign * 501.05, 0.0], atol=1e-8)


@pytest.mark.parametrize("mirror", [False, True])
def test_long_support_crosses_circle_before_leaving_its_domain(mirror):
    sign = -1 if mirror else 1
    surf = CircularSurface(sign * 501.0, 1.0, 2.0)
    support = Support((sign * 501.0, 0.0), (sign * 1000.0, 0.0), SupportType())
    result = support_intersection(support, surf, *surf.x_range())
    # (x-xc)^2 + (0-1)^2 = 2^2, taking the root along A -> B.
    np.testing.assert_allclose(result, [sign * (501.0 + np.sqrt(3)), 0.0], atol=1e-7)


def test_intersection_uses_first_crossing_inside_selected_mass():
    surf = PolylineSurface([[0, -1], [1, 1], [2, -1], [3, 1], [4, -1]])
    support = Support((0.0, 0.0), (4.0, 0.0), SupportType())
    np.testing.assert_allclose(support_intersection(support, surf, 2.0, 4.0), [2.5, 0.0])


def test_force_root_exactly_on_log_grid_is_accepted():
    # A strict sign-change test alone loses this exact equilibrium root.
    assert _root_1d(lambda f: f - 1.0, 1.0, span=(0.25, 4), n=5) == 1.0


def test_exact_grid_root_still_requires_physical_validity():
    result = _root_1d(
        lambda f: (f - 1.0) * (f - 3.0),
        1.0,
        span=(0.25, 4),
        n=5,
        valid=lambda f: f > 2.0,
    )
    assert result == pytest.approx(3.0)


def test_nearby_equilibrium_branch_precedes_distant_exact_root():
    result = _root_1d(lambda f: (f - 0.95) * (f - 2.0), 1.0, span=(0.25, 4), n=5)
    assert result == pytest.approx(0.95)


@pytest.mark.parametrize("sampled_force", [False, True])
def test_gle_fallback_accepts_exact_sampled_equilibria(monkeypatch, sampled_force):
    from types import SimpleNamespace

    from slipsurface.lem import gle

    force = np.geomspace(*gle.FALLBACK_WINDOW, 12)[5] if sampled_force else 1.0
    # A failed Newton solve must still recover the independent equations
    # F = force and lambda = 0, including exact roots on either scan grid.
    monkeypatch.setattr(gle, "root", lambda *a, **kw: SimpleNamespace(success=False))
    monkeypatch.setattr(gle, "_start_estimate", lambda *a: 1.0)
    monkeypatch.setattr(gle, "_residuals", lambda F, lam, *a: (F - force, lam, None))
    monkeypatch.setattr(
        gle, "_balanced", lambda F, lam, *a: abs(F - force) < 1e-6 and abs(lam) < 1e-6
    )
    assert gle._solve_linear(None, None, None, None, 1.0, 0.0, 1e-6) == pytest.approx((force, 0.0))
