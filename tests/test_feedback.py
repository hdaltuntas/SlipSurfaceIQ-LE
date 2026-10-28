"""Feedback round: new strength models, supports, search status, FS contour map,
note picking, English catalogue templates and screen-sized windows."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from slipsurface.analysis import run_analysis  # noqa: E402
from slipsurface.lem import analyze  # noqa: E402
from slipsurface.loads import SupportType, support_capacity  # noqa: E402
from slipsurface.materials import (  # noqa: E402
    BartonBandis,
    CNIRockMass,
    HoekBrown,
    HoekBrownDirect,
    PowerCurve,
    Sanisand,
    Shansep,
)
from slipsurface.materials.catalog import MODELS, parameter_text  # noqa: E402
from slipsurface.optimizer import SearchSettings, search  # noqa: E402
from slipsurface.project import MaterialSpec, Project, acads_1a_project  # noqa: E402


# --------------------------------------------------------------- materials
def _tau(m, s):
    c, tp = m.strength(np.atleast_1d(s))
    return c + np.atleast_1d(s) * tp


@pytest.mark.parametrize("key", list(MODELS))
def test_every_catalogue_model_builds_and_round_trips(key):
    spec = MaterialSpec(name="M", model=key)
    m = spec.to_material()
    stress = np.array([0.0, 50.0, 500.0])
    if key == "SH":
        c, tp = m.strength(stress, sigma_v=stress)
    elif key == "UDG":
        # A depth-dependent material needs the *elevation* of the slice
        # base, not a proxy based on normal or vertical stress.
        c, tp = m.strength(stress, y=np.array([0.0, -0.5, -1.0]))
        assert c[0] == pytest.approx(spec.su_top)
        assert c[-1] == pytest.approx(spec.su_bottom)
    else:
        c, tp = m.strength(stress)
    assert np.all(np.isfinite(c)) and np.all(c >= 0) and np.all(tp >= 0)
    assert parameter_text(spec)
    p = acads_1a_project()
    p.materials[0] = MaterialSpec(name=p.materials[0].name, model=key)
    q = Project.from_dict(p.to_dict())
    assert q.materials[0].model == key
    q.validate()


@pytest.mark.parametrize(
    "model",
    [
        PowerCurve("p", gamma=20, pc_a=2.0, pc_b=0.7, pc_c=3.0, pc_d=10.0),
        BartonBandis("b", gamma=26, phi_r=28, jrc=12, jcs=60_000, l0=0.1, ln=1.0),
        CNIRockMass("c", gamma=26, sigma_cm=8000, cni_a=0.5, cni_n=0.7, tensile=80),
        Sanisand("s", gamma=19),
    ],
)
def test_tangent_strength_matches_envelope(model):
    """(c, tan phi) is the tangent of tau(sigma): c + s tan phi = tau and the
    slope equals the numerical derivative (away from the 70 degree cap)."""
    s = np.array([40.0, 150.0, 600.0])
    c, tp = model.strength(s)
    np.testing.assert_allclose(c + s * tp, model.tau(s), rtol=1e-6, atol=1e-6)
    h = 1e-3
    fd = (model.tau(s + h) - model.tau(s - h)) / (2 * h)
    np.testing.assert_allclose(tp, fd, rtol=2e-3)


def test_barton_bandis_formula_and_scale_effect():
    m = BartonBandis("b", gamma=26, phi_r=25, jrc=10, jcs=50_000)
    s = 500.0
    expected = s * np.tan(np.radians(25 + 10 * np.log10(50_000 / s)))
    assert m.tau(s) == pytest.approx(expected)
    big = BartonBandis("b", gamma=26, phi_r=25, jrc=10, jcs=50_000, l0=0.1, ln=2.0)
    assert big.jrc_n == pytest.approx(10 * 20 ** (-0.2))
    assert big.jcs_n == pytest.approx(50_000 * 20 ** (-0.3))
    assert big.tau(s) < m.tau(s)
    # friction angle capped at 70 degrees at very low stress
    _, tp = m.strength(np.array([1e-3]))
    assert np.degrees(np.arctan(tp[0])) == pytest.approx(70.0)


def test_cni_and_power_curve_formulas():
    cni = CNIRockMass("c", gamma=26, sigma_cm=10_000, cni_a=0.6, cni_n=0.75, tensile=100)
    assert cni.tau(200.0) == pytest.approx(0.6 * 10_000 * (300 / 10_000) ** 0.75)
    pc = PowerCurve("p", gamma=20, pc_a=1.5, pc_b=0.8, pc_c=4.0, pc_d=5.0)
    assert pc.tau(95.0) == pytest.approx(1.5 * 100**0.8 + 4.0)


def test_hoek_brown_direct_matches_generalized():
    hb = HoekBrown("h", gamma=25, sigma_ci=30_000, gsi=55, mi=12, d=0.2)
    direct = HoekBrownDirect("d", gamma=25, sigma_ci=30_000, mb_in=hb.mb, s_in=hb.s, a_in=hb.a)
    s = np.array([100.0, 1000.0])
    np.testing.assert_allclose(direct.tau(s), hb.tau(s))


def test_shansep_uses_effective_vertical_stress():
    m = Shansep("s", gamma=18, s_ratio=0.25, m_exp=0.8, ocr=2.0, su_min=5.0)
    su = 5.0 + 0.25 * 100 * 2**0.8
    c, tp = m.strength(np.array([10.0]), sigma_v=np.array([100.0]))
    assert c[0] == pytest.approx(su) and tp[0] == 0
    c, _ = m.strength(np.array([10.0]), sigma_v=np.array([0.0]))
    assert c[0] == pytest.approx(5.0)
    # in the solver: dry homogeneous slope, su = S W/b at each base
    p = acads_1a_project()
    p.methods.methods = ["spencer"]
    p.materials[0] = MaterialSpec(
        name=p.materials[0].name, model="SH", gamma=18, shansep_s=0.3, shansep_m=0.8, ocr=1.0
    )
    geom, mats = p.build_geometry(), p.build_materials()
    from slipsurface.geometry import CircularSurface

    res, s = analyze(
        geom, CircularSurface(20.0, 30.0, 30.0), mats, method="spencer", opts=p.slice_options()
    )
    np.testing.assert_allclose(s.sigma_v_eff, s.W / s.b)
    assert res.ok and np.isfinite(res.fos)


def test_new_models_run_through_the_search():
    p = acads_1a_project()
    p.methods.methods = ["bishop"]
    p.surfaces.effort = "fast"
    for key in ("SH", "BB", "CN", "PC", "SS", "HS", "HBD"):
        q = p.copy()
        q.materials[0] = MaterialSpec(name=p.materials[0].name, model=key)
        r = run_analysis(q)
        assert np.isfinite(r.results["bishop"].fos), key


# ---------------------------------------------------------------- supports
def test_micro_pile_and_geosynthetic_capacity():
    pile = SupportType("P", "micro_pile", pile_shear=150)
    assert support_capacity(pile, 3, 3) == (150, "kazık kesme dayanımı")
    geo = SupportType("G", "geosynthetic", tensile=80, coverage=50)
    T, gov = support_capacity(geo, 2, 2, po_in=30.0, po_out=60.0)
    assert (T, gov) == (30.0, "sıyrılma (iç)")
    geo.anchorage = "embedded"
    assert support_capacity(geo, 2, 2, 30.0, 60.0)[0] == 30.0
    geo.anchorage = "face"
    assert support_capacity(geo, 2, 2, 30.0, 60.0) == (40.0, "çekme dayanımı")
    geo.anchorage = "both"
    assert support_capacity(geo, 2, 2, 1.0, 1.0)[0] == 40.0


@pytest.mark.parametrize(
    "kind,extra",
    [
        ("micro_pile", dict(pile_shear=150, orientation="perpendicular", application="passive")),
        ("micro_pile", dict(pile_shear=150, orientation="tangent", application="passive")),
        ("geosynthetic", dict(tensile=60, anchorage="none", interface_friction=30)),
    ],
)
def test_new_supports_raise_the_factor_of_safety(kind, extra):
    p = acads_1a_project()
    p.methods.methods = ["spencer"]
    p.surfaces.effort = "fast"
    surf = run_analysis(p).results["spencer"].surface
    base, _ = analyze(
        p.build_geometry(),
        surf,
        p.build_materials(),
        method="spencer",
        opts=p.slice_options(),
        **p.solver_kw(),
    )
    p.support_types = [SupportType("S", kind, spacing=1.0, **extra)]
    p.supports = (
        [{"a": [30, 5], "b": [30, -4], "type": "S"}]
        if kind == "micro_pile"
        else [{"a": [25.0, 2.5], "b": [45.0, 2.5], "type": "S"}]
    )
    res, s = analyze(
        p.build_geometry(),
        surf,
        p.build_materials(),
        method="spencer",
        opts=p.slice_options(),
        **p.solver_kw(),
    )
    assert len(s.support_forces) == 1
    f = s.support_forces[0]
    assert f.fx > 0  # opposes the right-to-left movement
    assert res.fos > base.fos + 0.05
    q = Project.from_dict(p.to_dict())
    assert q.support_types[0].kind == kind


# ------------------------------------------------------- search status / map
def test_search_reports_status_and_keeps_centres():
    p = acads_1a_project()
    st = {}
    settings = SearchSettings(method="bishop", popsize=8, maxiter=10, slice_opts=p.slice_options())
    res = search(p.build_geometry(), p.build_materials(), settings, None, st)
    assert st["stage"] == "final" and st["evaluated"] == res.n_evals
    assert st["valid"] + st["rejected"] == st["evaluated"]
    assert st["best"] == pytest.approx(min(f for f, _ in res.top), rel=1e-9)
    assert res.centres is not None and res.centres.shape[1] == 4
    assert res.centres[:, 3].min() == pytest.approx(min(f for f, _ in res.top))


def test_run_analysis_status_lists_finished_methods():
    p = acads_1a_project()
    p.methods.methods = ["bishop", "spencer"]
    p.surfaces.effort = "fast"
    st = {}
    r = run_analysis(p, None, status=st)
    assert set(st["done"]) == {"bishop", "spencer"}
    assert st["done"]["spencer"] == pytest.approx(r.results["spencer"].fos)


def test_fs_contour_grid():
    from slipsurface.ui.cad import fs_contour

    rng = np.random.default_rng(1)
    xy = rng.uniform([0, 10], [20, 40], size=(600, 2))
    fs = 1.0 + 0.05 * np.hypot(xy[:, 0] - 8, xy[:, 1] - 25)
    centres = np.column_stack([xy, np.full(600, 30.0), fs])
    g = fs_contour.build_grid(centres)
    assert g is not None and g["crit"][2] == pytest.approx(fs.min())
    assert g["vmax"] >= 6 * fs.min() * 0.99
    assert np.all(g["values"][g["mask"]] >= fs.min() - 1e-12)
    img = fs_contour.render_image(g)
    assert img.width() > 10 * g["nx"]
    seg = fs_contour.contour_segments(g)
    assert seg.shape[1] == 4 and len(seg) > 10
    xs, ys = seg[:, [0, 2]], seg[:, [1, 3]]
    assert xs.min() >= g["x0"] - 1e-9 and ys.min() >= g["y0"] - 1e-9
    labels = fs_contour.legend_labels(g["vmax"])
    assert labels[0] == "0" and labels[-1].endswith("+")
    assert fs_contour.build_grid(centres[:5]) is None
    # unsampled cells stay empty; smoothing must not invent a factor of safety
    # two separated columns, each tall enough to fill several cells, with a gap between
    left = np.column_stack(
        [np.full(40, 0.0), np.linspace(0, 40, 40), np.full(40, 10.0), np.full(40, 1.1)]
    )
    right = np.column_stack(
        [np.full(40, 80.0), np.linspace(0, 40, 40), np.full(40, 10.0), np.full(40, 2.2)]
    )
    gap = fs_contour.build_grid(np.vstack([left, right]))
    assert gap is not None and not gap["mask"].all()
    assert np.isnan(gap["values"][~gap["mask"]]).all()
    assert np.all(gap["values"][gap["mask"]] >= 1.1 - 1e-12)
    # the drawing blends across a shared edge, and a wide gap stays clear
    block = np.ones((8, 8))
    block[:, 4:] = 3.0
    smooth = {
        "values": block,
        "mask": np.ones((8, 8), dtype=bool),
        "nx": 8,
        "ny": 8,
        "crit": (0.0, 0.0, 1.0),
    }
    blended, _ = fs_contour._fine_fields(smooth, 8)
    assert np.all((blended[:, 32] > 1.2) & (blended[:, 32] < 2.8))
    _, gap_w = fs_contour._fine_fields(gap, 4)
    assert float(np.median(gap_w[:, gap_w.shape[1] // 2])) < 0.2


# ---------------------------------------------------------------- GUI parts
@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_note_picking_by_shape(app):
    from PySide6.QtCore import QPointF
    from slipsurface.ui.cad import CadArea

    area = CadArea()
    area.resize(800, 600)
    c = area.canvas
    p = acads_1a_project()
    base = {
        "color": "#c00",
        "width": 1.5,
        "fill": None,
        "text": "",
        "size": 10,
        "bold": False,
        "box": True,
    }
    p.annotations = [
        dict(base, kind="arrow", pts=[[0, 20], [20, 20]]),
        dict(base, kind="rect", pts=[[30, 15], [40, 25]]),
        dict(base, kind="ellipse", pts=[[45, 10], [59, 30]]),
    ]
    c.set_scene(p, p.build_geometry())
    c.zoom_extents()
    c.grab()

    def at(x, y, dx=0.0, dy=0.0):
        s = c.w2s(x, y)
        return c.pick_annotation(QPointF(s.x() + dx, s.y() + dy))

    assert at(10, 20) == ("annot", 0)
    assert at(10, 20, dy=5) == ("annot", 0)  # within the pick distance
    assert at(10, 20, dy=30) is None
    assert at(35, 20) == ("annot", 1)  # inside the rectangle
    assert at(52, 20) == ("annot", 2)  # inside the ellipse
    assert at(45.5, 10.5) is None  # bounding-box corner, outside ellipse
    c.selection = ("annot", 1)
    c.grab()  # paints grips + frame


def test_example_aliases():
    from slipsurface.project import EXAMPLE_ALIASES, EXAMPLES, example_project

    assert all(v in EXAMPLES for v in EXAMPLE_ALIASES.values())
    assert example_project("Katmanlı şev + YASS").summary.title == "Layered slope with water table"


def test_english_templates():
    from slipsurface.ui import i18n

    old = i18n.language()
    i18n._language = "en"
    try:
        assert (
            i18n.tr("Hesaplama tamamlandı (3.2 s). Global minimum: Spencer FS = 0.984")
            == "Computation finished (3.2 s). Global minimum: Spencer FS = 0.984"
        )
        assert i18n.tr("⚠ Yakında köşe yok.") == "⚠ No vertex nearby."
        assert i18n.tr("Destek 2: Ankraj 1") == "Support 2: Ankraj 1"  # user name kept
        assert i18n.tr("Göçme yönü         : Sağdan sola") == "Failure direction  : Right to left"
        assert i18n.trf("Malzeme {}", 3) == "Material 3"
        assert i18n.tr("Zemin 1") == "Zemin 1"
    finally:
        i18n._language = old


def test_fit_to_screen(app):
    from PySide6.QtWidgets import QDialog
    from slipsurface.ui.preferences import available_geometry, fit_to_screen

    d = QDialog()
    fit_to_screen(d, 5000, 4000)
    avail = available_geometry(d)
    assert d.width() <= avail.width() and d.height() <= avail.height()
