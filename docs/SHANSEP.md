# SHANSEP undrained strength

The implemented strength law is:

```text
tau = su = A + S * sigma'_v * OCR^m
sigma'_v = max(W / b - u_ref, 0)
```

| Parameter | Meaning | Units |
|---|---|---|
| A | Additive minimum undrained strength (intercept at zero effective stress) | kPa |
| S | Normally consolidated strength ratio used in the stress-dependent term | dimensionless |
| OCR | Overconsolidation ratio, constant per material, at least 1 | dimensionless |
| m | Stress-history exponent, commonly 0.75 to 1 | dimensionless |
| sigma'_v | Reference effective vertical overburden stress at the slice base | kPa |

A is **added**, not applied as `max(A, stress-dependent strength)`. For example,
A = 5 kPa, S = 0.25, sigma'_v = 100 kPa, OCR = 2 and m = 0.8 give
su = **48.5275 kPa**. With A = 0 the equation reduces to the normalized
SHANSEP relationship described by Ladd and Foott.

The material returns `c = su` and `tan(phi) = 0` to the LEM solver. It uses
effective vertical stress to establish undrained strength, then uses total
stresses for equilibrium; pore pressure is not subtracted a second time.
Trial normal forces on the inclined slip base do not change this strength.

## Reference stress and loading

`W / b` is calculated from the soil column above each slice base, including
the selected dry/saturated unit weights and any ponded-water weight.
`u_ref` follows the selected water-table/Hu, Ru, or dry groundwater setting,
before pore pressure is zeroed for total-stress equilibrium. Negative reference
effective stress is clipped to zero, so the strength remains A.

External loads, supports and pseudo-static seismic coefficients enter equilibrium
but do not increase this reference strength. Soil regions in the geometry do
contribute to the overburden, including any embankment drawn as a soil region.

For rapid fill placement on clay, the reference effective stress must represent
the **pre-loading consolidation state**. Simply adding an embankment to the
geometry with a hydrostatic water table can incorrectly increase the calculated
short-term strength. The application does not currently provide B-bar excess
pore pressures, construction stages, material exclusion factors, spatial
strength functions or depth-dependent OCR. Consequently, that setup alone
does not reproduce the short-term embankment analyses in the GeoStudio example.
This correction implements the strength equation; it does not add those features.

The supplied GeoStudio example's hand calculations are useful reference checks
for A = 0, S = 0.3 and OCR = 1:

- sigma'_v = 18 kPa gives su = 5.4 kPa.
- sigma'_v = 18 * 10 - 9.807 * 9 = 91.737 kPa gives su = 27.5211 kPa.

These check the strength relationship, not the example's complete slip-surface
search or published factors of safety.

## Existing projects and Python use

The project format remains version 3. The existing JSON field `shansep_su_min`
and Python constructor argument `su_min` now represent the additive A value;
their names remain unchanged so saved inputs and scripts still load. Missing
values default to zero. For A > 0, rerun analyses and review the changed results:
the old maximum-based formula produced smaller strengths at positive stress.

```python
import numpy as np
from slipsurface.materials import Shansep

clay = Shansep("Clay", gamma=18, s_ratio=0.25, m_exp=0.8, ocr=2, su_min=5)
su = clay.su(np.array([0.0, 100.0]))
c, tan_phi = clay.strength(np.array([10.0, 50.0]), sigma_v=np.array([0.0, 100.0]))
```

Calling `strength(sigma_n)` without `sigma_v` now raises `ValueError` instead
of silently substituting base normal stress for vertical stress. The LEM
solvers and slice reports already supply the reference vertical stress.

## References

- Rocscience, [Slide Isotropic Models, section 20.6, equation 20.6](https://www.rocscience.com/assets/verification-and-theory/RS2/20-Slide-Isotropic-Models.pdf).
- Seequent, *GeoStudio Example: SHANSEP - Stress History and Normalized Soil
  Engineering Property*, supplied reference, pp. 2-3 and 7-10.
- Ladd, C.C. and Foott, R. (1974), *New design procedure for stability of soft
  clays*, Journal of the Geotechnical Engineering Division, ASCE 100(7), 763-786.
