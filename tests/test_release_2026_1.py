"""2026.1 regressions: invalid input, passive equilibrium and support units/reports."""

import math
from dataclasses import replace

import numpy as np
import pytest
from pypdf import PdfReader

from slipsurface.analysis import AnalysisResults, report_text, run_analysis
from slipsurface.geometry import CircularSurface, PolylineSurface
from slipsurface.lem import SliceOptions, analyze, make_slices
from slipsurface.lem.gle import _Frame, _residuals, _strengths_frame, interslice_function
from slipsurface.loads import LoadSet, Support, SupportType
from slipsurface.optimizer import SearchResult
from slipsurface.project import Project, acads_1a_project
from slipsurface.report import ReportOptions, build_pdf
from slipsurface.scripting import run_script


@pytest.mark.parametrize(
    "owner,key,value",
    [
        ("groundwater", "method", "water_tabl"),
        ("groundwater", "gamma_w", 0),
        ("groundwater", "ru", 1.1),
        ("groundwater", "gamma_w", float("inf")),
        ("general", "failure_direction", "left"),
        ("methods", "interslice", "sine"),
        ("methods", "tolerance", 0),
        ("methods", "max_iter", 0),
        ("methods", "n_slices", 3.5),
        ("methods", "f_start", -0.1),
        ("surfaces", "surface_type", "circle"),
        ("surfaces", "noncircular_shape", "poly"),
        ("surfaces", "effort", "fats"),
        ("seismic", "kh", float("nan")),
        ("seismic", "kv", 1.1),
        ("advanced", "min_depth", -1),
    ],
)
def test_invalid_settings_rejected_after_file_roundtrip(tmp_path, owner, key, value):
    p = acads_1a_project()
    setattr(getattr(p, owner), key, value)
    path = tmp_path / "invalid.slp.json"
    p.save(path)
    restored = Project.load(path)
    with pytest.raises(ValueError):
        run_analysis(restored)


@pytest.mark.parametrize(
    "update",
    [
        {"kind": "distributedd"},
        {"orientation": "normall"},
        {"q": [10, float("nan")]},
        {"q": ["10", "20"]},
        {"points": [[40, 10]]},
        {"points": [[40, 10], [40, 10]]},
    ],
)
def test_invalid_loads_rejected_by_project_and_load_set(update):
    p = acads_1a_project()
    p.loads = [{"kind": "distributed", "points": [[40, 10], [50, 10]], "q": [10, 20], **update}]
    with pytest.raises(ValueError):
        p.validate()
    with pytest.raises(ValueError):
        p.load_set()


def test_invalid_script_and_direct_pore_option_cannot_silently_become_dry():
    p = acads_1a_project()
    with pytest.raises(ValueError):
        run_script("project.groundwater.method = 'water_tabl'", p)
    assert p.groundwater.method == "water_table"
    result, slices = analyze(
        p.build_geometry(),
        CircularSurface(20, 28, 28),
        p.build_materials(),
        opts=SliceOptions(pore="water_tabl"),
    )
    assert not result.ok and slices is None
    assert "unknown pore-pressure" in result.message


@pytest.mark.parametrize("value", ["10", float("inf"), [10]])
def test_invalid_line_load_magnitude_rejected(value):
    p = acads_1a_project()
    p.loads = [{"kind": "line", "point": [45, 10], "magnitude": value}]
    with pytest.raises(ValueError):
        p.load_set()


def anchor(capacity=1000, application="passive", kind="end_anchored", spacing=1.0):
    a = np.array([30.0, 5.0])
    d = np.array([math.cos(math.radians(15)), -math.sin(math.radians(15))])
    st = SupportType(
        kind=kind, tensile=capacity, application=application, spacing=spacing, pullout=1000
    )
    return Support(tuple(a), tuple(a + 20 * d), st)


@pytest.mark.parametrize("capacity", [1000, 5000, 10000])
@pytest.mark.parametrize("mirror", [False, True])
def test_strong_passive_ordinary_matches_closed_form_block(capacity, mirror):
    p = acads_1a_project()
    th = math.radians(15)
    end = 20 + 10 / math.tan(th)
    W = 20 * 0.5 * (end - 40) * 10
    length = math.hypot(end - 20, 10)
    tp = math.tan(math.radians(19.6))
    px, py = capacity * math.cos(th), -capacity * math.sin(th)
    drive = W * math.sin(th)
    passive_normal = px * math.sin(th) - py * math.cos(th)
    coef = -px * math.cos(th) - py * math.sin(th) - 3 * length - W * math.cos(th) * tp
    expected = (-coef + math.sqrt(coef**2 + 4 * drive * passive_normal * tp)) / (2 * drive)
    points = [[20, 0], [60, 40 * math.tan(th)]]
    support = anchor(capacity)
    if mirror:
        p.external = [[-x, y] for x, y in p.external]
        points = [[-x, y] for x, y in reversed(points)]
        support = replace(support, a=(-support.a[0], support.a[1]), b=(-support.b[0], support.b[1]))
    res, _ = analyze(
        p.build_geometry(),
        PolylineSurface(points),
        p.build_materials(),
        method="ordinary",
        opts=SliceOptions(loads=LoadSet(supports=[support])),
    )
    assert res.ok, res.message
    assert res.fos == pytest.approx(expected, rel=1e-8)


@pytest.mark.parametrize("capacity", [1000, 5000])
def test_strong_passive_bishop_satisfies_moment_equilibrium(capacity):
    p = acads_1a_project()
    opts = SliceOptions(loads=LoadSet(supports=[anchor(capacity)]))
    res, s = analyze(
        p.build_geometry(),
        CircularSurface(20, 28, 28),
        p.build_materials(),
        method="bishop",
        opts=opts,
        tol=1e-10,
    )
    assert res.ok and res.admissible, res.message
    fr = _Frame(s)
    c, tp = _strengths_frame(s, fr)
    _, moment, _ = _residuals(res.fos, 0, fr, c, tp, interslice_function("constant", fr.xb))
    assert abs(moment) < 1e-9


@pytest.mark.parametrize("model", ["MC", "UD"])
def test_passive_bishop_constant_strength_matches_closed_form_moment(model):
    p = acads_1a_project()
    m = p.materials[0]
    m.model, m.c, m.phi, m.su = model, 20, 0, 20
    surface = CircularSurface(20, 28, 28)
    opts = SliceOptions(loads=LoadSet(supports=[anchor(5000)]))
    s = make_slices(p.build_geometry(), surface, p.build_materials(), opts=opts)
    passive_moment = np.sum(s.M_p - surface.xc * s.Qy_p + surface.yc * s.Qx_p)
    expected = (20 * s.l.sum() + passive_moment / surface.r) / np.sum(s.W * np.sin(s.alpha))
    res, _ = analyze(
        p.build_geometry(), surface, p.build_materials(), method="bishop", opts=opts, tol=1e-10
    )
    assert res.ok and res.admissible, res.message
    assert res.fos == pytest.approx(expected, rel=1e-8)


@pytest.mark.parametrize("capacity", [1000, 5000])
def test_nonlinear_passive_bishop_matches_equivalent_applied_force(capacity):
    from slipsurface.lem import bishop_simplified

    p = acads_1a_project()
    p.materials[0].model = "PL"
    opts = SliceOptions(loads=LoadSet(supports=[anchor(capacity)]))
    res, s = analyze(
        p.build_geometry(),
        CircularSurface(20, 28, 28),
        p.build_materials(),
        method="bishop",
        opts=opts,
        tol=1e-10,
    )
    assert res.ok and res.admissible, res.message
    # At equilibrium, converting T/F to an active force must leave F unchanged.
    applied = replace(
        s,
        Qx_a=s.Qx_a + s.Qx_p / res.fos,
        Qy_a=s.Qy_a + s.Qy_p / res.fos,
        M_a=s.M_a + s.M_p / res.fos,
        Qx_p=np.zeros(s.n),
        Qy_p=np.zeros(s.n),
        M_p=np.zeros(s.n),
    )
    expected = bishop_simplified(applied, tol=1e-10)
    assert expected.ok
    assert res.fos == pytest.approx(expected.fos, rel=1e-7)


@pytest.mark.parametrize("spacing", [0.5, 1.5, 3.0])
def test_geotextile_per_width_capacity_independent_of_bolt_spacing(spacing):
    p = acads_1a_project()
    support = anchor(150, "active", "geotextile", spacing)
    res, slices = analyze(
        p.build_geometry(),
        CircularSurface(20, 28, 28),
        p.build_materials(),
        opts=SliceOptions(loads=LoadSet(supports=[support])),
    )
    assert res.ok
    assert slices.support_forces[0].T == pytest.approx(150)


@pytest.mark.parametrize("application", ["active", "passive"])
@pytest.mark.parametrize("language", ["tr", "en"])
def test_report_distinguishes_capacity_and_mobilized_force(tmp_path, application, language):
    p = acads_1a_project()
    support = anchor(300, application)
    p.support_types = [support.stype]
    p.supports = [{"type": support.stype.name, "a": list(support.a), "b": list(support.b)}]
    surface = CircularSurface(20, 28, 28)
    result, slices = analyze(
        p.build_geometry(), surface, p.build_materials(), opts=p.slice_options()
    )
    assert result.ok
    force = slices.support_forces[0]
    expected = 300 / result.fos if application == "passive" else 300
    assert force.mobilized(result.fos) == pytest.approx(expected)
    results = AnalysisResults(
        p, p.build_geometry(), {"bishop": SearchResult(surface, result.fos, result, slices, 1)}
    )
    text = report_text(results)
    assert f"T_cap = {300:8.2f}" in text
    assert f"T_mob = {expected:8.2f}" in text
    path = tmp_path / "support.pdf"
    build_pdf(results, path, ReportOptions(language=language))
    pdf = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    assert "Tcap" in pdf and "Tmob" in pdf
    assert f"{expected:.1f}" in pdf
    assert (
        "mobilised force at equilibrium" if language == "en" else "dengede mobilize kuvvet"
    ) in pdf
