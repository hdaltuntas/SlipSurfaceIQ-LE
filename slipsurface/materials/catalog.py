"""Material model catalogue shared by the project file, dialogs, labels and reports.

Each model key (stored in the project file) maps to its display name, the
strength formula shown in the materials dialog, and the editable parameters
as (MaterialSpec attribute, label, minimum, maximum, decimals).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    name: str
    formula: str
    rows: tuple
    total_stress: bool = False
    note: str = ""


MODELS: dict[str, ModelInfo] = {
    "MC": ModelInfo(
        "Mohr-Coulomb",
        "τ = c′ + σ′n · tan φ′",
        (("c", "Cohesion c (kPa)", 0, 1e6, 3), ("phi", "Friction angle φ (°)", 0, 89.9, 3)),
    ),
    "UD": ModelInfo(
        "Undrained (Tresca)",
        "τ = su (total stress; pore pressure not used)",
        (("su", "Undrained shear strength su (kPa)", 0, 1e6, 3),),
        total_stress=True,
    ),
    "UDG": ModelInfo(
        "Undrained – linear with elevation",
        "τ = su(y), linear from layer top to bottom (total stress)",
        (
            ("su_top", "Undrained strength at the top elevation (kPa)", 0, 1e6, 3),
            ("su_bottom", "Undrained strength at the bottom elevation (kPa)", 0, 1e6, 3),
            ("su_y_top", "Top elevation (m)", -1e6, 1e6, 3),
            ("su_y_bottom", "Bottom elevation (m)", -1e6, 1e6, 3),
        ),
        total_stress=True,
        note=(
            "su(y) at the slice base is interpolated linearly; outside the top/bottom "
            "elevations the end value is kept."
        ),
    ),
    "SH": ModelInfo(
        "SHANSEP",
        "τ = su = A + S · σ′v · OCR^m",
        (
            ("shansep_s", "S (normally consolidated su/σ′v)", 0.001, 5, 4),
            ("shansep_m", "m (exponent)", 0, 2, 3),
            ("ocr", "OCR (overconsolidation ratio)", 1, 100, 3),
            ("shansep_su_min", "A — minimum undrained strength (kPa)", 0, 1e6, 3),
        ),
        total_stress=True,
        note=(
            "A is additive. σ′v = max(W/b − u, 0): effective vertical overburden "
            "stress; m is typically 0.75–1. Short-term fill requires the pre-loading "
            "effective stress; B-bar/staged construction is not modelled."
        ),
    ),
    "HS": ModelInfo(
        "Mohr-Coulomb (HS envelope)",
        "τ = c′ + σ′n · tan φ′   (Mohr-Coulomb failure surface)",
        (
            ("c", "Cohesion c′ (kPa)", 0, 1e6, 3),
            ("phi", "Friction angle φ′ (°)", 0, 89.9, 3),
            ("hs_psi", "Dilatancy angle ψ (°)", 0, 89.9, 3),
            ("hs_e50", "E50,ref (kPa)", 1, 1e9, 1),
            ("hs_eoed", "Eoed,ref (kPa)", 1, 1e9, 1),
            ("hs_eur", "Eur,ref (kPa)", 1, 1e9, 1),
            ("hs_m", "m (stress dependency exponent)", 0, 1, 3),
            ("hs_pref", "pref (kPa)", 0.001, 1e6, 3),
            ("hs_rf", "Rf (failure ratio)", 0.01, 1, 3),
        ),
        note=(
            "Limit equilibrium uses only the failure envelope (c′, φ′); the stiffness "
            "parameters are stored for reference."
        ),
    ),
    "SS": ModelInfo(
        "Approximate peak φ (SANISAND)",
        "τ = σ′n tan φ(ψ),  sin φ = 3Mb/(6+Mb),  Mb = M·exp(−nb ψ)",
        (
            ("ss_m", "M (critical state stress ratio)", 0.01, 2.99, 4),
            ("ss_e", "Void ratio e", 0.01, 5, 4),
            ("ss_ec0", "ec0 (CSL reference void ratio)", 0.01, 5, 4),
            ("ss_lambda", "λc", 0, 1, 4),
            ("ss_xi", "ξ", 0.01, 1, 3),
            ("ss_nb", "nb", 0, 10, 3),
            ("ss_pat", "pat (kPa)", 0.001, 1e4, 3),
        ),
        note=(
            "The constitutive model is not solved. Peak φ is approximated from "
            "triaxial compression with p′ ≈ σ′n; plane strain is not used."
        ),
    ),
    "PL": ModelInfo(
        "Power-law envelope",
        "τ = a · pa · (1 + σ′n/pa)^b",
        (
            ("coefficient", "a", 0, 100, 4),
            ("exponent", "b", 0.001, 1, 4),
            ("reference_pressure", "pa (kPa)", 0.001, 1e6, 3),
        ),
    ),
    "PC": ModelInfo(
        "Power Curve",
        "τ = a · (σ′n + d)^b + c",
        (
            ("pc_a", "a", 0, 1e6, 4),
            ("pc_b", "b", 0.001, 1, 4),
            ("pc_c", "c (kPa)", 0, 1e6, 3),
            ("pc_d", "d (kPa)", 0, 1e6, 3),
        ),
    ),
    "BB": ModelInfo(
        "Barton-Bandis",
        "τ = σ′n · tan(φr + JRCn · log10(JCSn/σ′n))",
        (
            ("bb_phir", "Residual friction angle φr (°)", 0, 89.9, 3),
            ("bb_jrc", "JRC0", 0, 20, 3),
            ("bb_jcs", "JCS0 (kPa)", 1, 1e9, 1),
            ("bb_l0", "Laboratory sample length L0 (m)", 0.001, 100, 3),
            ("bb_ln", "Field block size Ln (m)", 0.001, 100, 3),
        ),
        note=(
            "JRCn = JRC0 (Ln/L0)^(−0.02 JRC0), JCSn = JCS0 (Ln/L0)^(−0.03 JRC0); "
            "total friction angle ≤ 70°."
        ),
    ),
    "CN": ModelInfo(
        "CNI Rock Mass",
        "τ = a · σc · ((σn − T0) / σc)^n",
        (
            ("cni_sigma_c", "Rock mass compressive strength σc (kPa)", 1, 1e9, 1),
            ("cni_a", "Strength magnitude coefficient a", 0.001, 100, 4),
            ("cni_n", "Curvature coefficient n", 0.01, 1, 4),
            ("cni_t", "Direct tensile strength |T0| (kPa)", 0, 1e9, 2),
        ),
        note="Cylwik, Killian & Cicchini (2023). Instantaneous φ ≤ 70°.",
    ),
    "HB": ModelInfo(
        "Generalized Hoek-Brown",
        "σ1 = σ3 + σci (mb σ3/σci + s)^a   (generalized Hoek-Brown, 2002)",
        (
            ("sigma_ci", "Intact UCS σci (kPa)", 1, 1e9, 1),
            ("gsi", "GSI", 1, 100, 1),
            ("mi", "mi", 0.1, 100, 2),
            ("d", "Disturbance factor D", 0, 1, 2),
        ),
    ),
    "HBD": ModelInfo(
        "Hoek-Brown (mb, s, a)",
        "σ1 = σ3 + σci (mb σ3/σci + s)^a",
        (
            ("sigma_ci", "Intact UCS σci (kPa)", 1, 1e9, 1),
            ("hb_mb", "mb", 0.001, 100, 4),
            ("hb_s", "s", 0, 1, 6),
            ("hb_a", "a", 0.5, 0.99, 4),
        ),
    ),
}


def model_name(key: str) -> str:
    info = MODELS.get(key)
    return info.name if info else key


def parameter_text(spec) -> str:
    """One-line strength parameter summary, e.g. 'c = 5 kPa, φ = 30°'."""
    short = {
        "MC": lambda m: f"c = {m.c:g} kPa, φ = {m.phi:g}°",
        "UD": lambda m: f"su = {m.su:g} kPa",
        "UDG": lambda m: (
            f"su = {m.su_top:g}–{m.su_bottom:g} kPa; y = {m.su_y_top:g}…{m.su_y_bottom:g} m"
        ),
        "SH": lambda m: (
            f"A = {m.shansep_su_min:g} kPa, S = {m.shansep_s:g}, "
            f"m = {m.shansep_m:g}, OCR = {m.ocr:g}"
        ),
        "HS": lambda m: f"c′ = {m.c:g} kPa, φ′ = {m.phi:g}°, ψ = {m.hs_psi:g}°",
        "SS": lambda m: f"M = {m.ss_m:g}, e = {m.ss_e:g}, ec0 = {m.ss_ec0:g}, nb = {m.ss_nb:g}",
        "PL": lambda m: (
            f"a = {m.coefficient:g}, b = {m.exponent:g}, pa = {m.reference_pressure:g} kPa"
        ),
        "PC": lambda m: f"a = {m.pc_a:g}, b = {m.pc_b:g}, c = {m.pc_c:g}, d = {m.pc_d:g}",
        "BB": lambda m: f"φr = {m.bb_phir:g}°, JRC = {m.bb_jrc:g}, JCS = {m.bb_jcs:g} kPa",
        "CN": lambda m: (
            f"σc = {m.cni_sigma_c:g} kPa, a = {m.cni_a:g}, n = {m.cni_n:g}, T0 = {m.cni_t:g} kPa"
        ),
        "HB": lambda m: f"σci = {m.sigma_ci:g} kPa, GSI = {m.gsi:g}, mi = {m.mi:g}, D = {m.d:g}",
        "HBD": lambda m: (
            f"σci = {m.sigma_ci:g} kPa, mb = {m.hb_mb:g}, s = {m.hb_s:g}, a = {m.hb_a:g}"
        ),
    }
    fn = short.get(spec.model)
    return fn(spec) if fn else ""
