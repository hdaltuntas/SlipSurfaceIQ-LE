"""Strength models.

Every material answers one question for the LEM engine:
    strength(sigma_n_eff) -> (c, tan_phi)
i.e. the (instantaneous) Mohr-Coulomb parameters at the given effective
normal stress on the slice base. Linear models ignore sigma_n.
SHANSEP additionally requires sigma_v, the reference effective vertical stress.

Units: stresses kPa, angles degrees, unit weights kN/m3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Material:
    name: str
    gamma: float  # unit weight above water table
    gamma_sat: float | None = None  # below water table (defaults to gamma)
    use_water: bool = True  # pore pressure from the water table acts on this material
    hu: float = 1.0  # piezometric head factor (Slide2 "Hu")

    def __post_init__(self) -> None:
        if self.gamma <= 0:
            raise ValueError("gamma must be positive")
        if self.gamma_sat is None:
            self.gamma_sat = self.gamma

    # True if strength depends on sigma_n (solver must iterate on N')
    nonlinear: bool = field(default=False, init=False, repr=False)
    total_stress: bool = field(default=False, init=False, repr=False)

    def strength(self, sigma_n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError


@dataclass
class MohrCoulomb(Material):
    c: float = 0.0  # kPa
    phi: float = 30.0  # deg

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.c < 0 or not (0 <= self.phi < 90):
            raise ValueError("c >= 0 and 0 <= phi < 90 required")

    def strength(self, sigma_n):
        sigma_n = np.asarray(sigma_n, dtype=float)
        return (np.full_like(sigma_n, self.c), np.full_like(sigma_n, np.tan(np.radians(self.phi))))


@dataclass
class HoekBrown(Material):
    """Generalized Hoek-Brown (2002).

    sigma_ci : intact UCS [kPa]  (e.g. 25 MPa -> 25_000)
    gsi, mi, d : GSI, intact constant, disturbance factor
    The sigma1-sigma3 envelope is converted to a tau-sigma_n curve
    (Balmer 1952) and tabulated; instantaneous c, phi are the tangent.
    """

    sigma_ci: float = 25_000.0
    gsi: float = 50.0
    mi: float = 10.0
    d: float = 0.0
    _sn: np.ndarray = field(init=False, repr=False)
    _tau: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        self.nonlinear = True
        g, d = self.gsi, self.d
        self.mb = self.mi * np.exp((g - 100) / (28 - 14 * d))
        self.s = np.exp((g - 100) / (9 - 3 * d))
        self.a = 0.5 + (np.exp(-g / 15) - np.exp(-20 / 3)) / 6
        self._build_table()

    def _build_table(self) -> None:
        sci, mb, s, a = self.sigma_ci, self.mb, self.s, self.a
        s3_t = -s * sci / mb  # biaxial tensile strength
        # dense near tension cut-off, up to 0.5*sigma_ci confinement
        s3 = s3_t + (0.5 * sci - s3_t) * np.linspace(0, 1, 400) ** 3
        s3 = s3[1:]  # avoid singular slope at s3_t
        base = np.maximum(mb * s3 / sci + s, 1e-12)
        s1 = s3 + sci * base**a
        ds = 1 + a * mb * base ** (a - 1)
        self._sn = (s1 + s3) / 2 - (s1 - s3) / 2 * (ds - 1) / (ds + 1)
        self._tau = (s1 - s3) * np.sqrt(ds) / (ds + 1)

    def tau(self, sigma_n):
        return np.interp(sigma_n, self._sn, self._tau)

    def strength(self, sigma_n):
        sn = np.clip(np.asarray(sigma_n, dtype=float), self._sn[0], self._sn[-1])
        tan_phi = np.interp(sn, self._sn, np.gradient(self._tau, self._sn))
        c = self.tau(sn) - sn * tan_phi
        return np.maximum(c, 0.0), np.maximum(tan_phi, 0.0)


@dataclass
class Undrained(Material):
    """Total-stress Tresca strength. Pore pressure must not be subtracted."""

    su: float = 25.0

    def __post_init__(self):
        super().__post_init__()
        if not np.isfinite(self.su) or self.su < 0:
            raise ValueError("su must be finite and nonnegative")
        self.use_water = False
        self.total_stress = True

    def strength(self, sigma_n):
        sn = np.asarray(sigma_n, dtype=float)
        return np.full_like(sn, self.su), np.zeros_like(sn)


@dataclass
class UndrainedDepth(Material):
    """Total-stress undrained shear strength linear in absolute elevation.

    Both endpoints are specified in world coordinates, top elevation > bottom.
    Evaluate at the slice-base midpoint, not at its mean overburden stress.
    The model is constant outside the stated layer range.
    """

    su_top: float = 25.0
    su_bottom: float = 25.0
    y_top: float = 0.0
    y_bottom: float = -1.0
    uses_elevation: bool = field(default=True, init=False, repr=False)

    def __post_init__(self):
        super().__post_init__()
        if (
            not np.isfinite([self.su_top, self.su_bottom, self.y_top, self.y_bottom]).all()
            or min(self.su_top, self.su_bottom) < 0
            or self.y_top <= self.y_bottom
        ):
            raise ValueError("Undrained-depth material needs finite su >= 0 and y_top > y_bottom")
        self.total_stress = True
        self.use_water = False

    def strength(self, sigma_n, *, y=None):
        if y is None:
            raise ValueError("Undrained-depth strength requires slice-base elevation y")
        sn, elevation = np.broadcast_arrays(np.asarray(sigma_n, float), np.asarray(y, float))
        fraction = np.clip((self.y_top - elevation) / (self.y_top - self.y_bottom), 0.0, 1.0)
        su = self.su_top + fraction * (self.su_bottom - self.su_top)
        return su, np.zeros_like(sn)


@dataclass
class PowerLaw(Material):
    """Concave envelope tau = a * pa * (1 + max(sigma',0)/pa)^b.

    pa is a reference stress in kPa; a is dimensionless, 0 < b <= 1.
    Returns the exact local tangent for the iterative LEM solver.
    """

    coefficient: float = 0.2
    exponent: float = 0.5
    reference_pressure: float = 100.0

    def __post_init__(self):
        super().__post_init__()
        if (
            not np.isfinite([self.coefficient, self.exponent, self.reference_pressure]).all()
            or self.coefficient < 0
            or not 0 < self.exponent <= 1
            or self.reference_pressure <= 0
        ):
            raise ValueError("a >= 0, 0 < b <= 1 and pa > 0 required")
        self.nonlinear = True

    def strength(self, sigma_n):
        sn = np.maximum(np.asarray(sigma_n, dtype=float), 0)
        x = 1 + sn / self.reference_pressure
        slope = self.coefficient * self.exponent * x ** (self.exponent - 1)
        tau = self.coefficient * self.reference_pressure * x**self.exponent
        return tau - sn * slope, slope


def _clip_friction(tau, slope, sn, max_phi_deg=70.0):
    """Instantaneous (c, tan phi) of a curved envelope with phi capped (Slide2:
    70 degrees); the cohesion intercept is never negative."""
    cap = np.tan(np.radians(max_phi_deg))
    slope = np.clip(slope, 0.0, cap)
    return np.maximum(tau - sn * slope, 0.0), slope


@dataclass
class HoekBrownDirect(HoekBrown):
    """Hoek-Brown with mb, s and a entered directly (Slide2 "Hoek-Brown")."""

    mb_in: float = 1.0
    s_in: float = 0.001
    a_in: float = 0.5

    def __post_init__(self) -> None:
        Material.__post_init__(self)
        if (
            self.sigma_ci <= 0
            or self.mb_in <= 0
            or not 0 <= self.s_in <= 1
            or not 0.5 <= self.a_in < 1
        ):
            raise ValueError("sigma_ci > 0, mb > 0, 0 <= s <= 1, 0.5 <= a < 1 required")
        self.nonlinear = True
        self.mb, self.s, self.a = self.mb_in, self.s_in, self.a_in
        self._build_table()


@dataclass
class Shansep(Material):
    """SHANSEP undrained strength (Ladd & Foott 1974), total stress:
        su = A + S * max(sigma'_v, 0) * OCR^m
    A is stored as su_min for compatibility with existing projects/scripts.
    It is an additive intercept, not a lower-bound clamp on the stress term.
    sigma'_v is the effective vertical stress at the slice base (overburden
    minus pore pressure), independent of the trial base normal stress.
    The reference stress must represent the consolidation state of the soil;
    the model does not simulate excess pore pressure or staged construction.
    """

    s_ratio: float = 0.22
    m_exp: float = 0.8
    ocr: float = 1.0
    su_min: float = 0.0  # A, additive minimum undrained strength [kPa]
    uses_vertical_stress: bool = field(default=True, init=False, repr=False)

    def __post_init__(self):
        super().__post_init__()
        if (
            not np.isfinite([self.s_ratio, self.m_exp, self.ocr, self.su_min]).all()
            or self.s_ratio <= 0
            or self.m_exp < 0
            or self.ocr < 1
            or self.su_min < 0
        ):
            raise ValueError("Finite S > 0, m >= 0, OCR >= 1 and A (su_min) >= 0 required")
        self.total_stress = True

    def su(self, sigma_v_eff):
        sv = np.maximum(np.asarray(sigma_v_eff, dtype=float), 0.0)
        return self.su_min + self.s_ratio * sv * self.ocr**self.m_exp

    def strength(self, sigma_n, sigma_v=None):
        if sigma_v is None:
            raise ValueError("SHANSEP requires effective vertical stress sigma_v; use su(sigma_v)")
        sn = np.asarray(sigma_n, dtype=float)
        return self.su(sigma_v) * np.ones_like(sn), np.zeros_like(sn)


@dataclass
class HardeningSoil(MohrCoulomb):
    """Hardening Soil (Schanz et al. 1999). Its failure surface is Mohr-Coulomb
    (c', phi'); in limit equilibrium only this envelope is used. The stiffness
    parameters are stored for reference and are not used by the LEM solver."""

    psi: float = 0.0  # dilatancy angle [deg]
    e50_ref: float = 30_000.0  # kPa
    eoed_ref: float = 30_000.0  # kPa
    eur_ref: float = 90_000.0  # kPa
    m_power: float = 0.5
    p_ref: float = 100.0  # kPa
    rf: float = 0.9

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0 <= self.psi <= self.phi:
            raise ValueError("0 <= psi <= phi required")
        if (
            min(self.e50_ref, self.eoed_ref, self.eur_ref, self.p_ref) <= 0
            or not 0 <= self.m_power <= 1
            or not 0 < self.rf <= 1
        ):
            raise ValueError("stiffnesses > 0, 0 <= m <= 1 and 0 < Rf <= 1 required")


@dataclass
class Sanisand(Material):
    """SANISAND (Dafalias & Manzari 2004) state-dependent peak strength.

    Critical state line  e_c = e_c0 - lambda_c (p'/p_at)^xi,
    state parameter      psi = e - e_c,
    peak stress ratio    M_b = M exp(-n_b psi)   (triaxial compression),
    friction angle       sin phi = 3 M_b / (6 + M_b).
    In LEM the mean stress is approximated by the base normal stress
    (p' ~ sigma'_n); the instantaneous tangent of tau = sigma'_n tan phi(sigma'_n)
    is returned. phi is limited to [phi_cs - 10, 50] degrees.
    """

    m_c: float = 1.25
    void_ratio: float = 0.75
    e_c0: float = 0.934
    lambda_c: float = 0.019
    xi: float = 0.7
    n_b: float = 1.1
    p_at: float = 101.3

    def __post_init__(self):
        super().__post_init__()
        if (
            not 0 < self.m_c < 3
            or self.void_ratio <= 0
            or self.e_c0 <= 0
            or self.lambda_c < 0
            or not 0 < self.xi <= 1
            or self.n_b < 0
            or self.p_at <= 0
        ):
            raise ValueError(
                "0 < M < 3, e > 0, e_c0 > 0, lambda_c >= 0, 0 < xi <= 1, "
                "n_b >= 0, p_at > 0 required"
            )
        self.nonlinear = True

    @staticmethod
    def _phi(M):
        return np.degrees(np.arcsin(np.clip(3 * M / (6 + M), 0, 0.99)))

    def friction_angle(self, sigma_n):
        p = np.maximum(np.asarray(sigma_n, dtype=float), 1e-6)
        psi = self.void_ratio - (self.e_c0 - self.lambda_c * (p / self.p_at) ** self.xi)
        mb = self.m_c * np.exp(-self.n_b * psi)
        phi_cs = self._phi(self.m_c)
        return np.clip(self._phi(mb), max(phi_cs - 10.0, 1.0), 50.0)

    def tau(self, sigma_n):
        sn = np.maximum(np.asarray(sigma_n, dtype=float), 0.0)
        return sn * np.tan(np.radians(self.friction_angle(sn)))

    def strength(self, sigma_n):
        sn = np.maximum(np.asarray(sigma_n, dtype=float), 0.0)
        h = np.maximum(1e-3 * sn, 1e-3)
        slope = (self.tau(sn + h) - self.tau(np.maximum(sn - h, 0.0))) / (
            sn + h - np.maximum(sn - h, 0.0)
        )
        return _clip_friction(self.tau(sn), slope, sn)


@dataclass
class PowerCurve(Material):
    """Slide2 Power Curve: tau = a (sigma'_n + d)^b + c   [kPa]."""

    pc_a: float = 1.5
    pc_b: float = 0.8
    pc_c: float = 0.0
    pc_d: float = 0.0

    def __post_init__(self):
        super().__post_init__()
        if self.pc_a < 0 or not 0 < self.pc_b <= 1 or self.pc_c < 0 or self.pc_d < 0:
            raise ValueError("a >= 0, 0 < b <= 1, c >= 0 and d >= 0 required")
        self.nonlinear = True

    def tau(self, sigma_n):
        x = np.maximum(np.asarray(sigma_n, dtype=float) + self.pc_d, 0.0)
        return self.pc_a * x**self.pc_b + self.pc_c

    def strength(self, sigma_n):
        sn = np.maximum(np.asarray(sigma_n, dtype=float), 0.0)
        x = np.maximum(sn + self.pc_d, 1e-9)
        slope = self.pc_a * self.pc_b * x ** (self.pc_b - 1)
        return _clip_friction(self.tau(sn), slope, sn)


@dataclass
class BartonBandis(Material):
    """Barton-Bandis joint strength (Barton & Bandis 1990; Hoek, Practical Rock
    Engineering ch. 4):
        tau = sigma_n tan(phi_r + JRC_n log10(JCS_n / sigma_n))
    with the scale corrections
        JRC_n = JRC_0 (L_n/L_0)^(-0.02 JRC_0),  JCS_n = JCS_0 (L_n/L_0)^(-0.03 JRC_0)
    and the total friction angle limited to 70 degrees."""

    phi_r: float = 25.0
    jrc: float = 10.0
    jcs: float = 50_000.0  # kPa
    l0: float = 0.1  # laboratory sample length [m]
    ln: float = 0.1  # field block size [m]

    def __post_init__(self):
        super().__post_init__()
        if (
            not 0 <= self.phi_r < 90
            or not 0 <= self.jrc <= 20
            or self.jcs <= 0
            or self.l0 <= 0
            or self.ln <= 0
        ):
            raise ValueError("0 <= phi_r < 90, 0 <= JRC <= 20, JCS > 0, L0 > 0, Ln > 0 required")
        self.nonlinear = True
        r = self.ln / self.l0
        self.jrc_n = self.jrc * r ** (-0.02 * self.jrc)
        self.jcs_n = self.jcs * r ** (-0.03 * self.jrc)

    def _angle(self, sn):
        return np.minimum(self.phi_r + self.jrc_n * np.log10(self.jcs_n / sn), 70.0)

    def tau(self, sigma_n):
        sn = np.maximum(np.asarray(sigma_n, dtype=float), 1e-9)
        return sn * np.tan(np.radians(self._angle(sn)))

    def strength(self, sigma_n):
        sn = np.maximum(np.asarray(sigma_n, dtype=float), 1e-6)
        ang = self._angle(sn)
        t = np.tan(np.radians(ang))
        capped = ang >= 70.0
        slope = t - np.where(capped, 0.0, np.pi * self.jrc_n / (180 * np.log(10)) * (t**2 + 1))
        return _clip_friction(sn * t, slope, sn)


@dataclass
class CNIRockMass(Material):
    """CNI non-linear rock mass criterion (Cylwik, Killian & Cicchini 2023), in
    the variables of Slide2:
        tau = a * sigma_c * ((sigma_n - T0) / sigma_c)^n
    sigma_c rock mass compressive strength [kPa], a strength magnitude
    coefficient, n curvature coefficient, T0 direct tensile strength (entered
    as a positive magnitude, used as -T0). Instantaneous phi capped at 70 deg."""

    sigma_cm: float = 10_000.0
    cni_a: float = 0.6
    cni_n: float = 0.75
    tensile: float = 100.0

    def __post_init__(self):
        super().__post_init__()
        if self.sigma_cm <= 0 or self.cni_a <= 0 or not 0 < self.cni_n <= 1 or self.tensile < 0:
            raise ValueError("sigma_c > 0, a > 0, 0 < n <= 1 and T0 >= 0 required")
        self.nonlinear = True

    def tau(self, sigma_n):
        x = np.maximum((np.asarray(sigma_n, dtype=float) + self.tensile) / self.sigma_cm, 0.0)
        return self.cni_a * self.sigma_cm * x**self.cni_n

    def strength(self, sigma_n):
        sn = np.maximum(np.asarray(sigma_n, dtype=float), 0.0)
        x = np.maximum((sn + self.tensile) / self.sigma_cm, 1e-12)
        slope = self.cni_a * self.cni_n * x ** (self.cni_n - 1)
        return _clip_friction(self.tau(sn), slope, sn)
