"""SHANSEP additive A, reference vertical stress and saved/UI parameter regressions."""

import math

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface, PolylineSurface, simple_slope
from slipsurface.lem import SliceOptions, analyze, make_slices
from slipsurface.lem.bishop import _strength, slice_strength
from slipsurface.loads import DistributedLoad, LoadSet
from slipsurface.materials import Shansep
from slipsurface.materials.catalog import MODELS, parameter_text
from slipsurface.project import MaterialSpec, Project, acads_1a_project


@pytest.mark.parametrize("a", [0.0, 5.0, 100.0])
def test_additive_intercept_at_zero_low_and_high_stress(a):
    clay = Shansep("Clay", gamma=18, s_ratio=0.25, m_exp=0.8, ocr=2, su_min=a)
    # Low stress must also ADD to A, even if the stress term is smaller than A.
    vertical = np.array([-10.0, 0.0, 4.0, 100.0])
    expected = np.array([a, a, a + 1.7411011265922482, a + 43.527528164806206])
    np.testing.assert_allclose(clay.su(vertical), expected)
    for normal in (np.zeros(4), np.array([10.0, 1000.0, 20.0, 30.0])):
        c, tp = clay.strength(normal, sigma_v=vertical)
        np.testing.assert_allclose(c, expected)
        np.testing.assert_array_equal(tp, 0.0)


def test_geostudio_reference_hand_calculations():
    clay = Shansep("Clay", gamma=18, s_ratio=0.3)
    # Supplied GeoStudio reference, pp. 7-8, equations 3-6 (A=0, OCR=1).
    assert clay.su(18.0) == pytest.approx(5.4)
    assert clay.su(18.0 * 10 - 9.807 * 9) == pytest.approx(27.5211)


def test_base_normal_stress_cannot_silently_replace_vertical_stress():
    with pytest.raises(ValueError, match="effective vertical stress sigma_v"):
        Shansep("Clay", gamma=18).strength(np.array([100.0]))


@pytest.mark.parametrize("parameter", ["s_ratio", "m_exp", "ocr", "su_min"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_invalid_shansep_parameters_rejected_for_direct_api(parameter, value):
    with pytest.raises(ValueError, match="Finite S"):
        Shansep("Clay", gamma=18, **{parameter: value})


@pytest.mark.parametrize(
    "method",
    [
        "ordinary",
        "spencer",
        "gle",
        "janbu_simplified",
        "janbu_corrected",
        "corps1",
        "corps2",
        "lowe_karafiath",
    ],
)
@pytest.mark.parametrize("ru", [0.0, 0.4])
def test_planar_block_matches_closed_form_with_surcharge_and_seismic(method, ru):
    theta = math.radians(15)
    geom = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    surf = PolylineSurface([[20, 0], [60, 40 * math.tan(theta)]])
    clay = Shansep("Zemin 1", gamma=20, s_ratio=0.25, ocr=2, m_exp=0.8, su_min=5)
    # Static overburden defines strength; this applied load and seismic inertia
    # change equilibrium without being mistaken for consolidation stresses.
    loads = LoadSet(distributed=[DistributedLoad(42, 52, 10, 10, "vertical")])
    opts = SliceOptions(n_slices=40, pore="ru", ru=ru, kh=0.1, kv=0.05, loads=loads)
    result, _ = analyze(geom, surf, {clay.name: clay}, method=method, opts=opts)
    x_entry = 20 + 10 / math.tan(theta)
    weight = 20 * 0.5 * (x_entry - 40) * 10
    length = math.hypot(x_entry - 20, 10)
    resistance = 5 * length + 0.25 * 2**0.8 * (1 - ru) * weight / math.cos(theta)
    driving = (weight * 0.95 + 100) * math.sin(theta) + weight * 0.1 * math.cos(theta)
    assert result.ok, result.message
    assert result.fos == pytest.approx(resistance / driving, rel=1e-6)


@pytest.mark.parametrize("method", ["bishop", "ordinary"])
def test_circular_phi_zero_moment_equilibrium(method):
    p = acads_1a_project()
    clay = Shansep(p.materials[0].name, gamma=18, s_ratio=0.3, ocr=2, su_min=5)
    result, slices = analyze(
        p.build_geometry(),
        CircularSurface(20, 30, 30),
        {clay.name: clay},
        method=method,
        opts=SliceOptions(pore="ru", ru=0.4),
    )
    # Independent moment balance for a circular total-stress slip surface.
    h = slices.y_top - slices.y_base
    su = 5 + 0.3 * (1 - 0.4) * 18 * h * 2**0.8
    expected = np.sum(su * slices.l) / np.sum(18 * h * slices.b * np.sin(slices.alpha))
    assert result.ok, result.message
    assert result.fos == pytest.approx(expected, rel=1e-7)


@pytest.mark.parametrize("pore", ["none", "water_table", "ru"])
def test_groundwater_reference_stress_is_retained_for_solver_and_slice_report(pore):
    p = acads_1a_project()
    p.water_table = [[0, 15], [60, 15]]  # ponded above the entire slope
    clay = Shansep(p.materials[0].name, gamma=20, gamma_sat=20, s_ratio=0.3, su_min=5)
    slices = make_slices(
        p.build_geometry(),
        CircularSurface(20, 30, 30),
        {clay.name: clay},
        opts=SliceOptions(pore=pore, ru=0.4, kh=0.1, kv=0.05),
    )
    h = slices.y_top - slices.y_base
    # Hydrostatic pressure cancels the ponded water weight; submerged soil
    # contributes its buoyant unit weight to the reference effective stress.
    expected_vertical = {"none": 20 * h, "water_table": (20 - 9.81) * h, "ru": 12 * h}[pore]
    np.testing.assert_allclose(slices.sigma_v_eff, expected_vertical)
    np.testing.assert_array_equal(slices.u, 0.0)  # no second pore-pressure subtraction
    expected_su = 5 + 0.3 * expected_vertical
    for normal in (np.zeros(slices.n), np.full(slices.n, 1000.0)):
        actual, tp = _strength(slices, normal)
        np.testing.assert_allclose(actual, expected_su)
        np.testing.assert_array_equal(tp, 0.0)
    for i in range(slices.n):
        c, tp = slice_strength(slices, i)
        assert c == pytest.approx(expected_su[i]) and tp == 0


def test_existing_project_minimum_field_round_trip_and_missing_default(tmp_path):
    p = acads_1a_project()
    p.materials[0] = MaterialSpec(
        name=p.materials[0].name, model="SH", shansep_su_min=5, shansep_s=0.25, ocr=2
    )
    path = tmp_path / "shansep.slp.json"
    p.save(path)
    restored = Project.load(path)
    restored.validate()
    spec = restored.materials[0]
    assert spec.shansep_su_min == 5
    assert spec.to_material().su(100) == pytest.approx(48.527528164806206)
    assert "A = 5 kPa" in parameter_text(spec)
    data = p.to_dict()
    assert data["version"] == 3
    del data["materials"][0]["shansep_su_min"]
    default = Project.from_dict(data).materials[0]
    assert default.shansep_su_min == 0
    assert default.to_material().su(100) == pytest.approx(43.527528164806206)


@pytest.mark.parametrize("language", ["tr", "en"])
def test_dialog_edits_additive_a_and_explains_reference_stress(language, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from slipsurface.ui import i18n
    from slipsurface.ui.dialogs.materials import MaterialsDialog

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(i18n, "_language", language)
    spec = MaterialSpec(model="SH", shansep_su_min=5, shansep_s=0.25, ocr=2)
    dialog = MaterialsDialog([spec])
    try:
        i18n.translate_window(dialog)
        row = next(i for i, entry in enumerate(MODELS["SH"].rows) if entry[0] == "shansep_su_min")
        assert dialog.formula.text() == "τ = su = A + S · σ′v · OCR^m"
        assert dialog.table.item(row, 0).text() == i18n.tr(MODELS["SH"].rows[row][1])
        assert dialog.derived.text() == i18n.tr(MODELS["SH"].note)
        dialog.table.item(row, 1).setText("7.5")
        app.processEvents()
        assert dialog.mats[0].shansep_su_min == 7.5
        assert dialog.mats[0].to_material().su(100) == pytest.approx(51.027528164806206)
        assert spec.shansep_su_min == 5  # original project only changes on acceptance
    finally:
        dialog.close()
