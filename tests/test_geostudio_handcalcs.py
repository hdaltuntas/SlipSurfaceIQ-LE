"""External 29-slice SLOPE/W hand-calculation benchmark (Seequent, pp. 2–13).

IMPORTANT: This fixture checks the exact *published slice quantities*, not
independently reconstructed ground geometry or critical-surface search.
The source's Ordinary pore-force convention differs from the native LE solver.
Do not "fix" the solver merely to force those two distinct formulas to agree.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from slipsurface.geometry import CircularSurface
from slipsurface.lem import bishop_simplified, ordinary
from slipsurface.lem.bishop import bishop_base_normal_forces
from slipsurface.lem.slicing import SliceSet
from slipsurface.materials import MohrCoulomb


BENCHMARK_PATH = Path(__file__).parent / "data" / "geostudio_handcalcs_29_slices.json"


def _case():
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def _terms():
    """Return documented slices in the source sign convention (degrees)."""
    return _case()["rows"]


def _driving(slices):
    # GeoStudio Table 1 uses alpha negative for the downslope left half;
    # the slide moves towards -x, as in LE's solver frame.
    return sum(-r["weight_kn"] * math.sin(math.radians(r["alpha_deg"])) for r in slices)


def _ordinary_reference(slices):
    """GeoStudio Eq. 3 / Table 2, using u L cos²(alpha) (NOT LE's u L)."""
    tan_phi = math.tan(math.radians(_case()["soil"]["friction_angle_deg"]))
    cohesion = _case()["soil"]["cohesion_kpa"]
    strength = 0.0
    for r in slices:
        alpha = math.radians(r["alpha_deg"])
        W, L, u = r["weight_kn"], r["base_length_m"], r["pore_pressure_kpa"]
        strength += cohesion * L + (W * math.cos(alpha) - u * L * math.cos(alpha) ** 2) * tan_phi
    return strength


def _bishop_reference(slices, trial_fs):
    """GeoStudio Eq. 10/11, sign-adjusted to its positive driving direction."""
    c = _case()["soil"]["cohesion_kpa"]
    tan_phi = math.tan(math.radians(_case()["soil"]["friction_angle_deg"]))
    strength = 0.0
    normals = []
    for r in slices:
        alpha = math.radians(-r["alpha_deg"])  # solver-frame alpha
        W, L, u = r["weight_kn"], r["base_length_m"], r["pore_pressure_kpa"]
        ma = math.cos(alpha) + math.sin(alpha) * tan_phi / trial_fs
        N = (W - (c * L - u * L * tan_phi) * math.sin(alpha) / trial_fs) / ma
        strength += c * L + (N - u * L) * tan_phi
        normals.append(N)
    return strength / _driving(slices), strength, normals


def _prepared_slices():
    """Feed exact published slice numbers into the real LE *solvers*.

    The circular surface here is solely a marker enabling circular moment
    equilibrium; its centre is not used by either solver without external
    horizontal forces. No claim is made of reproducing Seequent CAD geometry.
    """
    rows = _terms()
    b = np.array([r["width_m"] for r in rows])
    xr = np.cumsum(b)
    xl = xr - b
    W = np.array([r["weight_kn"] for r in rows])
    u = np.array([r["pore_pressure_kpa"] for r in rows])
    return SliceSet(
        xl=xl,
        xr=xr,
        xm=(xl + xr) / 2,
        b=b,
        y_base=np.zeros(len(rows)),
        y_top=np.array([r["height_m"] for r in rows]),
        alpha=np.radians([-r["alpha_deg"] for r in rows]),
        l=np.array([r["base_length_m"] for r in rows]),
        W=W,
        u=u,
        mat_idx=np.zeros(len(rows), dtype=int),
        materials=[MohrCoulomb("GeoStudio single material", gamma=20, c=5, phi=30)],
        surface=CircularSurface(0, 50, 55),
        x_exit=0.0,
        x_entry=float(xr[-1]),
    )


def test_geostudio_slice_data_and_driving_sum():
    case = _case()
    slices = case["rows"]
    assert len(slices) == 29
    assert [r["n"] for r in slices] == list(range(1, 30))
    assert slices[4]["pore_pressure_kpa"] == 25.571
    assert case["soil"] == {
        "unit_weight_kn_m3": 20,
        "cohesion_kpa": 5,
        "friction_angle_deg": 30,
    }
    assert _driving(slices) == pytest.approx(795.340, abs=0.02)
    for r in slices:
        assert r["weight_kn"] == pytest.approx(20 * r["height_m"] * r["width_m"], abs=0.065)
        assert r["base_length_m"] == pytest.approx(
            r["width_m"] / math.cos(math.radians(r["alpha_deg"])), abs=0.0012
        )


def test_geostudio_ordinary_reference_and_slice5_normal():
    slices = _terms()
    resistance = _ordinary_reference(slices)
    driving = _driving(slices)
    assert resistance == pytest.approx(930.640, abs=0.05)
    assert resistance / driving == pytest.approx(1.170, abs=0.001)
    r = slices[4]
    alpha = math.radians(r["alpha_deg"])
    # The text uses L=1.3232 m, whereas Table 1 rounds it to 1.323 m.
    L = 1.3232
    sigma_n_eff = (
        r["weight_kn"] * math.cos(alpha) / L - r["pore_pressure_kpa"] * math.cos(alpha) ** 2
    )
    total_normal = (sigma_n_eff + r["pore_pressure_kpa"]) * L
    assert sigma_n_eff == pytest.approx(42.6320, abs=0.02)
    assert total_normal == pytest.approx(90.2462, abs=0.02)


@pytest.mark.parametrize(
    "trial,expected_resistance,expected_next",
    [
        (1.170, 983.091, 1.236),
        (1.236, 991.636, 1.247),
        (1.247, 992.967, 1.248),
    ],
)
def test_geostudio_bishop_hand_iteration(trial, expected_resistance, expected_next):
    next_fs, resistance, normals = _bishop_reference(_terms(), trial)
    assert resistance == pytest.approx(expected_resistance, abs=0.12)
    assert next_fs == pytest.approx(expected_next, abs=0.002)
    if trial == 1.170:
        assert normals[4] == pytest.approx(103.916, abs=0.04)


def test_geostudio_bishop_converges_to_published_one_point_249():
    f = 1.170
    for _ in range(30):
        new_f, _, _ = _bishop_reference(_terms(), f)
        if abs(new_f - f) < 1e-10:
            f = new_f
            break
        f = new_f
    assert f == pytest.approx(1.249, abs=0.001)
    assert abs(_bishop_reference(_terms(), f)[0] - f) < 1e-9


def test_actual_le_bishop_solver_agrees_with_external_hand_reference():
    s = _prepared_slices()
    result = bishop_simplified(s, tol=1e-10, f0=1.170)
    assert result.ok and result.admissible, result
    assert result.fos == pytest.approx(1.249, abs=0.001)
    assert result.iterations > 1


def test_actual_le_ordinary_matches_external_geostudio_hand_reference():
    """Corrected Ordinary projects u*L*cos²(alpha), as in PDF Eq. 3."""
    s = _prepared_slices()
    result = ordinary(s)
    assert result.ok
    source_fs = _ordinary_reference(_terms()) / _driving(_terms())
    assert source_fs == pytest.approx(1.170, abs=0.001)
    assert result.fos == pytest.approx(source_fs, abs=1e-10)


def test_actual_le_ordinary_pore_pressure_effect_is_not_doubled():
    s = _prepared_slices()
    wet = ordinary(s)
    dry_s = _prepared_slices()
    dry_s.u[:] = 0
    dry = ordinary(dry_s)
    assert wet.ok and dry.ok
    assert wet.fos < dry.fos
    assert wet.fos == pytest.approx(1.170, abs=0.001)


def test_bishop_total_and_effective_normals_match_geostudio_slice_five():
    """Explicit Eq. 10: u is *base pressure*, U=u*L is the pore force."""
    s = _prepared_slices()
    c = np.full(s.n, 5.0)
    tp = np.full(s.n, math.tan(math.radians(30)))
    N, N_eff = bishop_base_normal_forces(s, 1.170, c, tp)
    assert N[4] == pytest.approx(103.916, abs=0.04)
    assert N_eff[4] == pytest.approx(N[4] - 25.571 * 1.323, abs=1e-12)
    # Algebraic equivalence to the existing compact Bishop u*b term.
    ma = np.cos(s.alpha) + np.sin(s.alpha) * tp / 1.170
    compact = (
        s.W - s.u * s.b - c * s.b * np.tan(s.alpha) / 1.170
    ) / ma
    np.testing.assert_allclose(N_eff, compact, rtol=0, atol=1e-10)


def test_bishop_wet_dry_and_null_pressure_are_consistent():
    s = _prepared_slices()
    wet = bishop_simplified(s, tol=1e-10, f0=1.170)
    dry_s = _prepared_slices()
    dry_s.u[:] = 0
    dry = bishop_simplified(dry_s, tol=1e-10, f0=1.170)
    assert wet.ok and dry.ok
    assert wet.fos == pytest.approx(1.249, abs=0.001)
    assert wet.fos < dry.fos
    c = np.full(s.n, 5.0)
    tp = np.full(s.n, math.tan(math.radians(30)))
    N, N_eff = bishop_base_normal_forces(dry_s, dry.fos, c, tp)
    np.testing.assert_allclose(N, N_eff, rtol=0, atol=1e-12)
