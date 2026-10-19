"""Strength models.

Every material answers one question for the LEM engine:
    strength(sigma_n_eff) -> (c, tan_phi)
i.e. the (instantaneous) Mohr-Coulomb parameters at the given effective
normal stress on the slice base. Linear models ignore sigma_n.

Units: stresses kPa, angles degrees, unit weights kN/m3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Material:
    name: str
    gamma: float                   # unit weight above water table
    gamma_sat: float | None = None  # below water table (defaults to gamma)
    use_water: bool = True          # pore pressure from the water table acts on this material
    hu: float = 1.0                 # piezometric head factor (Slide2 "Hu")

    def __post_init__(self) -> None:
        if self.gamma <= 0:
            raise ValueError("gamma must be positive")
        if self.gamma_sat is None:
            self.gamma_sat = self.gamma

    # True if strength depends on sigma_n (solver must iterate on N')
    nonlinear: bool = field(default=False, init=False, repr=False)

    def strength(self, sigma_n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError


@dataclass
class MohrCoulomb(Material):
    c: float = 0.0       # kPa
    phi: float = 30.0    # deg

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.c < 0 or not (0 <= self.phi < 90):
            raise ValueError("c >= 0 and 0 <= phi < 90 required")

    def strength(self, sigma_n):
        sigma_n = np.asarray(sigma_n, dtype=float)
        return (np.full_like(sigma_n, self.c),
                np.full_like(sigma_n, np.tan(np.radians(self.phi))))


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
        s3_t = -s * sci / mb                       # biaxial tensile strength
        # dense near tension cut-off, up to 0.5*sigma_ci confinement
        s3 = s3_t + (0.5 * sci - s3_t) * np.linspace(0, 1, 400) ** 3
        s3 = s3[1:]                                # avoid singular slope at s3_t
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
