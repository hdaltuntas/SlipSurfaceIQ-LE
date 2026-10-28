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
        (("c", "Kohezyon c (kPa)", 0, 1e6, 3), ("phi", "İçsel sürtünme açısı φ (°)", 0, 89.9, 3)),
    ),
    "UD": ModelInfo(
        "Undrained (Tresca)",
        "τ = su (toplam gerilme; boşluk suyu basıncı kullanılmaz)",
        (("su", "Drenajsız kayma dayanımı su (kPa)", 0, 1e6, 3),),
        total_stress=True,
    ),
    "UDG": ModelInfo(
        "Undrained – linear with elevation",
        "τ = su(y), linear from layer top to bottom (total stress)",
        (
            ("su_top", "Drenajsız dayanım üst kotta (kPa)", 0, 1e6, 3),
            ("su_bottom", "Drenajsız dayanım alt kotta (kPa)", 0, 1e6, 3),
            ("su_y_top", "Üst kot (m)", -1e6, 1e6, 3),
            ("su_y_bottom", "Alt kot (m)", -1e6, 1e6, 3),
        ),
        total_stress=True,
        note="Dilim tabanında su(y) doğrusal enterpolasyonla belirlenir. Üst/alt kot sınırlarının dışında uç değer korunur.",
    ),
    "SH": ModelInfo(
        "SHANSEP",
        "τ = su = A + S · σ′v · OCR^m",
        (
            ("shansep_s", "S (normal konsolide su/σ′v)", 0.001, 5, 4),
            ("shansep_m", "m (üs)", 0, 2, 3),
            ("ocr", "OCR (aşırı konsolidasyon oranı)", 1, 100, 3),
            ("shansep_su_min", "A — minimum drenajsız dayanım (kPa)", 0, 1e6, 3),
        ),
        total_stress=True,
        note="A formüle eklenir. σ′v = max(W/b − u, 0): efektif düşey örtü gerilmesi; "
        "m genellikle 0.75–1 aralığındadır. Kısa süreli dolgu için yükleme öncesi "
        "efektif gerilme esas alınmalıdır; B-bar/kademeli inşaat modellenmez.",
    ),
    "HS": ModelInfo(
        "Mohr-Coulomb (HS zarfı)",
        "τ = c′ + σ′n · tan φ′   (göçme yüzeyi Mohr-Coulomb)",
        (
            ("c", "Kohezyon c′ (kPa)", 0, 1e6, 3),
            ("phi", "İçsel sürtünme açısı φ′ (°)", 0, 89.9, 3),
            ("hs_psi", "Dilatasyon açısı ψ (°)", 0, 89.9, 3),
            ("hs_e50", "E50,ref (kPa)", 1, 1e9, 1),
            ("hs_eoed", "Eoed,ref (kPa)", 1, 1e9, 1),
            ("hs_eur", "Eur,ref (kPa)", 1, 1e9, 1),
            ("hs_m", "m (gerilme bağımlılığı üssü)", 0, 1, 3),
            ("hs_pref", "pref (kPa)", 0.001, 1e6, 3),
            ("hs_rf", "Rf (göçme oranı)", 0.01, 1, 3),
        ),
        note="Limit dengede yalnızca göçme zarfı (c′, φ′) kullanılır; rijitlik "
        "parametreleri bilgi amaçlı saklanır.",
    ),
    "SS": ModelInfo(
        "Yaklaşık pik φ (SANISAND)",
        "τ = σ′n tan φ(ψ),  sin φ = 3Mb/(6+Mb),  Mb = M·exp(−nb ψ)",
        (
            ("ss_m", "M (kritik durum gerilme oranı)", 0.01, 2.99, 4),
            ("ss_e", "Boşluk oranı e", 0.01, 5, 4),
            ("ss_ec0", "ec0 (KDÇ referans boşluk oranı)", 0.01, 5, 4),
            ("ss_lambda", "λc", 0, 1, 4),
            ("ss_xi", "ξ", 0.01, 1, 3),
            ("ss_nb", "nb", 0, 10, 3),
            ("ss_pat", "pat (kPa)", 0.001, 1e4, 3),
        ),
        note="Bünye modeli çözülmez. Pik φ, üç eksenli sıkışma ve p′ ≈ σ′n ile yaklaşık bulunur; "
        "düzlem deformasyon kullanılmaz.",
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
            ("bb_phir", "Rezidüel sürtünme açısı φr (°)", 0, 89.9, 3),
            ("bb_jrc", "JRC0", 0, 20, 3),
            ("bb_jcs", "JCS0 (kPa)", 1, 1e9, 1),
            ("bb_l0", "Laboratuvar numune boyu L0 (m)", 0.001, 100, 3),
            ("bb_ln", "Arazi blok boyu Ln (m)", 0.001, 100, 3),
        ),
        note="JRCn = JRC0 (Ln/L0)^(−0.02 JRC0), JCSn = JCS0 (Ln/L0)^(−0.03 JRC0); "
        "toplam sürtünme açısı ≤ 70°.",
    ),
    "CN": ModelInfo(
        "CNI Rock Mass",
        "τ = a · σc · ((σn − T0) / σc)^n",
        (
            ("cni_sigma_c", "Kaya kütlesi basınç dayanımı σc (kPa)", 1, 1e9, 1),
            ("cni_a", "Dayanım büyüklük katsayısı a", 0.001, 100, 4),
            ("cni_n", "Eğrilik katsayısı n", 0.01, 1, 4),
            ("cni_t", "Direkt çekme dayanımı |T0| (kPa)", 0, 1e9, 2),
        ),
        note="Cylwik, Killian & Cicchini (2023). Anlık φ ≤ 70°.",
    ),
    "HB": ModelInfo(
        "Genelleştirilmiş Hoek-Brown",
        "σ1 = σ3 + σci (mb σ3/σci + s)^a   (genelleştirilmiş Hoek-Brown, 2002)",
        (
            ("sigma_ci", "Tek eksenli basınç dayanımı σci (kPa)", 1, 1e9, 1),
            ("gsi", "GSI", 1, 100, 1),
            ("mi", "mi", 0.1, 100, 2),
            ("d", "Örselenme faktörü D", 0, 1, 2),
        ),
    ),
    "HBD": ModelInfo(
        "Hoek-Brown (mb, s, a)",
        "σ1 = σ3 + σci (mb σ3/σci + s)^a",
        (
            ("sigma_ci", "Tek eksenli basınç dayanımı σci (kPa)", 1, 1e9, 1),
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
