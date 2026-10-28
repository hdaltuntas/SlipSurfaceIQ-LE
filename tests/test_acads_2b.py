"""ACADS 2(b): exact Talbingo Dam dry fixed-circle benchmark.

Coordinates: Rocscience Slide2 VP5/VP6 / GeoStudio SLOPE/W §2.6.
The prescribed circle (100.3, 291.0, 278.8) must be evaluated once,
not approximated by a polyline or optimized to a new minimum.
"""

import numpy as np
import pytest
from shapely.geometry import Point

from slipsurface.geometry import CircularSurface
from slipsurface.project import Project, acads_2b_project, example_project
from slipsurface.analysis import run_analysis

CIRCLE = [100.3, 291.0, 278.8]
EXPECTED = {
    "bishop": 2.208,
    "spencer": 2.292,
    "gle": 2.301,
    "janbu_corrected": 2.073,
}


def test_acads_2b_roundtrip_and_exact_fixed_circle(tmp_path):
    p = acads_2b_project()
    fixture = Project.load("examples/acads_2b.slp.json")
    listed = example_project("ACADS 2(b) — Talbingo fixed circle")
    for case in (p, fixture, listed):
        case.validate()
        assert case.surfaces.surface_type == "user"
        assert case.surfaces.user_circle == CIRCLE
        assert case.surfaces.user_surface is None
        assert case.groundwater.method == "none"
        assert case.water_table is None
        assert case.tension_crack is None
        assert case.methods.methods == list(EXPECTED)
        assert case.general.failure_direction == "right_to_left"
        assert case.external == [
            [0, 0], [648, 0], [577.9, 31.4], [515, 65.3],
            [453.4, 97.9], [386.9, 130.6], [327.6, 162], [315.5, 162],
        ]
        assert len(case.material_boundaries) == 5
        assert [(m.c, m.phi, m.gamma) for m in case.materials] == [
            (0, 45, 20.4), (0, 45, 20.4),
            (0, 45, 20.4), (85, 23, 18.1),
        ]
    assert fixture.analysis_inputs() == p.analysis_inputs()
    fn = tmp_path / "acads_2b_roundtrip.slp.json"
    p.save(fn)
    assert Project.load(fn).surfaces.user_circle == CIRCLE


def test_acads_2b_geometry_builds_six_distinct_material_regions():
    p = acads_2b_project()
    g = p.build_geometry()
    assert g.domain.area == pytest.approx(52957.26, abs=1e-4)
    assert len(g.regions) == 6
    assert sum(r.polygon.area for r in g.regions) == pytest.approx(g.domain.area)
    for (x, y), name in [
        ((100, 20), "Rockfill"),
        ((245, 65), "Transitions"),
        ((287, 65), "Core"),
        ((320.7, 65.3), "Filter"),
        ((341, 65), "Transitions"),
        ((500, 65), "Rockfill"),
    ]:
        assert [r.material for r in g.regions if r.polygon.contains(Point(x, y))] == [name]
    assert sorted(r.material for r in g.regions) == [
        "Core", "Filter", "Rockfill", "Rockfill", "Transitions", "Transitions"
    ]


@pytest.mark.parametrize("value", [[0, 0, 0], [100, 300], [0, 1, -2], [0, 1, float("nan")]])
def test_acads_2b_invalid_circle_is_rejected(value):
    p = acads_2b_project()
    p.surfaces.user_circle = value
    with pytest.raises(ValueError):
        p.validate()


def test_acads_2b_fixed_circle_methods_reproduce_published_benchmark():
    p = acads_2b_project()
    results = run_analysis(p)
    assert not results.errors, results.errors
    assert set(results.results) == set(EXPECTED)
    for method, reference in EXPECTED.items():
        found = results.results[method]
        assert isinstance(found.surface, CircularSurface), method
        assert [found.surface.xc, found.surface.yc, found.surface.r] == CIRCLE
        assert found.n_evals == 1, "Fixed-circle computation must not run search."
        assert found.lem.ok, (method, found.lem.message)
        assert np.isfinite(found.fos), method
        assert found.fos == pytest.approx(reference, abs=0.05), (
            method, found.fos, reference
        )


def test_acads_2b_user_polyline_behavior_is_unchanged():
    p = acads_2b_project()
    p.surfaces.user_circle = None
    p.surfaces.user_surface = [[50, 25], [200, 90], [315.5, 162]]
    p.validate()
    # Previously drawn non-circular user surfaces continue to use the
    # original polyline pathway rather than a fabricated circular surface.
    from slipsurface.ui.cad.model import add_entity

    add_entity(p, "user", [[50, 25], [200, 85], [315.5, 162]])
    assert p.surfaces.user_circle is None
    assert p.surfaces.surface_type == "user"


def test_acads_2b_circle_surface_options_keep_exact_values():
    from PySide6.QtWidgets import QApplication
    from slipsurface.ui.dialogs.surface_options import SurfaceOptionsDialog

    app = QApplication.instance() or QApplication([])
    assert app is not None
    p = acads_2b_project()
    d = SurfaceOptionsDialog(p)
    assert d.r_user.isChecked()
    assert d.use_circle.isChecked()
    assert [f.value() for f in d.circle_fields] == CIRCLE
    assert d._type() == "user"
    q = p.copy()
    d.apply_to(q)
    assert q.surfaces.user_circle == CIRCLE
    assert q.surfaces.surface_type == "user"
    d.close()
