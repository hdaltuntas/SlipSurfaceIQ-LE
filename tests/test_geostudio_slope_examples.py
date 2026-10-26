"""GeoStudio SLOPE/W tutorial and LE formulation examples.

Two independent public Seequent documents are source references. The tutorial
coordinates, material properties and piezometric points are exact from tables.
Only the *published* critical-circle coordinates/search radius schedule are
unavailable; the illustrative circle below is NOT the vendor's solved circle.
Do not assert that its FS equals SLOPE/W's minimum search FS 1.370.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface, PolylineSurface, layered_geometry, simple_slope
from slipsurface.lem import SliceOptions, analyze, make_slices
from slipsurface.materials import MohrCoulomb


SOURCE = Path(__file__).parent / "data" / "geostudio_slope_examples.json"


def source_case():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def tutorial_model():
    """Convert published descending slope to LE's increasing-crest x direction."""
    case = source_case()["tutorial"]
    points = {int(k): v for k, v in case["geometry_points"].items()}

    # GeoStudio's left-to-right slide is mirrored once, not sign-changed in
    # the numerical solver. The x and y dimensions and material zones persist.
    def flip(point):
        return [40 - point[0], point[1]]

    # Reorder coordinates ascending after mirroring the vendor drawing.
    surface = np.array([flip(points[k]) for k in (6, 5, 3, 2, 1)], dtype=float)
    groundwater = np.array([flip(p) for p in reversed(case["piezometric_points"])], dtype=float)
    geom = layered_geometry(
        surface,
        bottom=0.0,
        layers=[
            ("Upper Layer", None),
            ("Lower Layer", np.array([[0, 9], [40, 9]], dtype=float)),
        ],
        water_table=groundwater,
        name="GeoStudio tutorial – reconstructed published tables",
    )
    mats = {
        name: MohrCoulomb(
            name,
            gamma=values["gamma_kn_m3"],
            c=values["c_kpa"],
            phi=values["phi_deg"],
        )
        for name, values in case["materials"].items()
    }
    return geom, mats


def illustrative_tutorial_circle():
    """A fixed illustrative arc fitted to the Figure 6 silhouette, NOT its exact circle."""
    return CircularSurface(13.984375, 23.4375, 20.33787477566486)


def test_tutorial_all_eight_geometry_points_are_reconstructed():
    case = source_case()["tutorial"]
    assert len(case["geometry_points"]) == 8
    assert case["entry_exit"]["trial_surfaces"] == 396
    assert 6 * 6 * 11 == 396
    assert not case["exact_vendor_circle_and_radius_samples_in_pdf"]

    geom, mats = tutorial_model()
    np.testing.assert_allclose(geom.surface, [[0, 4], [10, 4], [20, 9], [30, 14], [40, 14]])
    np.testing.assert_allclose(geom.water_table, [[0, 7], [16, 7], [24, 8], [40, 10]])
    assert [r.material for r in geom.regions]  # layered model actually created
    assert len(mats) == 2
    for label, expected in (
        ("Upper Layer", (17, 4, 20)),
        ("Lower Layer", (18, 8, 25)),
    ):
        m = mats[label]
        assert (m.gamma, m.c, m.phi) == expected


def test_tutorial_piezometric_pressure_and_ponded_water():
    geom, mats = tutorial_model()
    assert geom.water_y(0) == pytest.approx(7.0)
    assert geom.ground_y(0) == pytest.approx(4.0)
    assert geom.water_y(40) == pytest.approx(10.0)
    assert geom.ground_y(40) == pytest.approx(14.0)
    assert geom.water_y(20) == pytest.approx(7.5)

    arc = illustrative_tutorial_circle()
    wet = make_slices(geom, arc, mats, opts=SliceOptions(pore="water_table"))
    dry = make_slices(geom, arc, mats, opts=SliceOptions(pore="none"))
    assert wet.n > 25 and np.all(wet.W > 0)
    assert set(wet.mat_idx.tolist()) == {0, 1}
    assert wet.u.max() > 0
    assert wet.W.sum() > dry.W.sum()  # toe ponding contributes real weight
    np.testing.assert_array_equal(dry.u, np.zeros_like(dry.u))


def test_tutorial_two_materials_and_water_reach_real_le_solvers():
    geom, mats = tutorial_model()
    arc = illustrative_tutorial_circle()
    outputs = {}
    for method in ("bishop", "janbu_simplified", "spencer"):
        result, slices = analyze(
            geom, arc, mats, method=method, opts=SliceOptions(pore="water_table")
        )
        assert result.ok and result.admissible, (method, result)
        assert slices is not None and slices.n > 25
        assert np.isfinite(result.fos) and result.fos > 0
        outputs[method] = result.fos
    # Method qualitative behaviour is examined on a *fixed* reconstructed
    # surface, not compared with published optimized SLOPE/W minimum.
    assert outputs["janbu_simplified"] < outputs["spencer"]
    assert abs(outputs["spencer"] - outputs["bishop"]) < 0.15


def limit_equilibrium_analogue():
    """Controlled 2H:1V slope with the *published* c, phi, gamma (not source geometry)."""
    inputs = source_case()["limit_equilibrium_formulation"]["soil"]
    geom = simple_slope(10, 2, toe_x=20, left_bench=20, right_bench=20, depth_below_toe=5)
    mats = {
        "Zemin 1": MohrCoulomb(
            "Zemin 1",
            gamma=inputs["gamma_kn_m3"],
            c=inputs["c_kpa"],
            phi=inputs["phi_deg"],
        )
    }
    return geom, mats


@pytest.mark.parametrize("method", ("janbu_simplified", "spencer", "gle", "ordinary"))
def test_limit_equilibrium_planar_translational_force_balance(method):
    """Seequent's planar example: force-based methods agree with rigid-block statics."""
    geom, mats = limit_equilibrium_analogue()
    theta = math.radians(15)
    surface = PolylineSurface([[20, 0], [60, 40 * math.tan(theta)]])
    result, slices = analyze(
        geom, surface, mats, n_slices=40, method=method, opts=SliceOptions(pore="none")
    )
    assert result.ok and result.admissible, (method, result)
    assert slices is not None
    x_entry = 20 + 10 / math.tan(theta)
    weight = 20 * (x_entry - 40) * 10 / 2
    length = math.hypot(x_entry - 20, 10)
    expected = (10 * length + weight * math.cos(theta) * math.tan(math.radians(26))) / (
        weight * math.sin(theta)
    )
    assert result.fos == pytest.approx(expected, rel=1e-6)


def test_limit_equilibrium_circular_method_ordering():
    """Seequent Figure 8: Bishop and Spencer similar, Janbu simplified lower."""
    geom, mats = limit_equilibrium_analogue()
    arc = CircularSurface(20, 28, 28)
    outcomes = {}
    for method in ("bishop", "spencer", "janbu_simplified"):
        result, _ = analyze(geom, arc, mats, method=method)
        assert result.ok and result.admissible, (method, result)
        outcomes[method] = result.fos
    assert outcomes["janbu_simplified"] < outcomes["spencer"]
    assert outcomes["janbu_simplified"] < outcomes["bishop"]
    assert abs(outcomes["spencer"] - outcomes["bishop"]) / outcomes["spencer"] < 0.05


def test_limit_equilibrium_bishop_not_defined_for_planar_slip():
    """The paper's planar moment-FS graph does NOT authorize LE's circular Bishop."""
    geom, mats = limit_equilibrium_analogue()
    line = PolylineSurface([[20, 0], [60, 40 * math.tan(math.radians(15))]])
    result, _ = analyze(geom, line, mats, method="bishop")
    assert not result.ok
    assert "circular" in result.message.lower()


def test_source_reference_numbers_remain_separate_from_fixed_surface_verification():
    sources = source_case()
    tutorial = sources["tutorial"]
    assert tutorial["published_reference"] == {
        "method": "Spencer",
        "minimum_fs": 1.370,
        "bishop_same_surface_fs": 1.366,
        "janbu_same_surface_fs": 1.269,
        "lambda": 0.28,
    }
    assert not tutorial["exact_vendor_circle_and_radius_samples_in_pdf"]
    formula = sources["limit_equilibrium_formulation"]
    assert formula["published_figure_values"] == {
        "circular_fs": 1.523,
        "planar_fs": 2.613,
    }
    assert not formula["exact_surface_geometry_available"]
