"""Janbu verification against original Slide2/ACADS specified slip surfaces.

Reference: Rocscience Slide2 Slope Stability Verification Manual (2022),
VP1, VP3, VP4, VP6 and VP8. All references here are Janbu CORRECTED,
not Janbu Simplified or a different method's global-search minimum.

Only one prescribed surface is calculated per test. Optimizer quality
is not inferred from a fixed-surface numerical match.
"""

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface, PolylineSurface
from slipsurface.lem import analyze
from slipsurface.lem.gle import janbu_correction_factor
from slipsurface.project import (
    acads_1a_project,
    acads_1b_project,
    acads_1d_project,
    acads_2b_project,
    acads_3b_project,
)

# VP1's source geometry has its toe at (30,25); the repository's
# translated toe is (20,0), so subtract (10,25) from the published
# center but DO NOT alter its radius.
CASES = [
    ("VP1-ACADS-1a", acads_1a_project, (20.149, 26.471, 26.407), 0.990),
    ("VP3-ACADS-1c", acads_1b_project, (35.109, 40.222, 16.389), 1.357),
    ("VP4-ACADS-1d", acads_1d_project, (35.109, 41.233, 17.205), 0.965),
    ("VP6-Talbingo-2b", acads_2b_project, (100.3, 291.0, 278.8), 2.073),
]


@pytest.mark.parametrize("name,factory,circle,reference", CASES)
def test_janbu_corrected_on_published_circle(name, factory, circle, reference):
    p = factory()
    geom, mats = p.build_geometry(), p.build_materials()
    surf = CircularSurface(*circle)
    corrected, slices = analyze(
        geom, surf, mats, method="janbu_corrected", opts=p.slice_options(), **p.solver_kw()
    )
    simplified, raw_slices = analyze(
        geom, surf, mats, method="janbu_simplified", opts=p.slice_options(), **p.solver_kw()
    )
    assert corrected.ok and simplified.ok, (name, corrected.message, simplified.message)
    assert slices is not None and raw_slices is not None
    assert np.isfinite(corrected.fos)
    f0 = janbu_correction_factor(slices)
    assert corrected.fos == pytest.approx(simplified.fos * f0, rel=1e-10)
    assert 1 <= f0 <= 1.125
    # One percent allows slice discretization differences; current deviations
    # are below 0.14%, so a several-percent drift should fail this check.
    assert corrected.fos == pytest.approx(reference, rel=0.01), (
        name,
        corrected.fos,
        simplified.fos,
        f0,
        reference,
    )


def test_acads_3b_janbu_corrected_on_published_noncircular_path():
    p = acads_3b_project()
    path = PolylineSurface(p.surfaces.user_surface)
    corrected, slices = analyze(
        p.build_geometry(),
        path,
        p.build_materials(),
        method="janbu_corrected",
        opts=p.slice_options(),
        **p.solver_kw(),
    )
    assert corrected.ok, corrected.message
    assert slices is not None
    assert corrected.fos == pytest.approx(1.294, rel=0.01), corrected.fos


def test_acads_preset_method_names_are_distinct():
    for factory in (acads_1a_project, acads_1b_project):
        methods = factory().methods.methods
        assert "janbu_simplified" in methods
        assert "janbu_corrected" in methods
    for factory in (acads_2b_project, acads_3b_project):
        assert "janbu_corrected" in factory().methods.methods
