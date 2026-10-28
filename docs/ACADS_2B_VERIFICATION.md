# ACADS 2(b) — Talbingo Dam, dry prescribed slip circle (VS_6)

## Purpose

This benchmark is the **fixed-surface** companion to ACADS 2(a).
It checks the slice-weight integration and method-specific limit equilibrium
on **one exact circle** rather than checking critical-circle optimization.
The known circle is **center = (100.3, 291.0) m; radius = 278.8 m**.

References:

- Bentley Systems, *ACADS Models*, §2.8, VS_6, supplied screenshot.
- Rocscience, *Slide2 Slope Stability Verification Manual*, VP5/VP6
  (original coordinates, circular methods, results).
- Seequent, *SLOPE/W Slope Stability Verification Manual*, §2.5–2.6:
  https://files.seequent.com/GeoStudio/Manuals/Slope%20Stability%20Verification%20Manual.pdf
- Rocscience, *RS2 Slope Stability Verification Manual, Part I*, §4
  (original Talbingo 2(a) geometry/materials):
  https://www.rocscience.com/assets/verification-and-theory/RS2/RS2_SlopeStabilityVerification_Part1.pdf

## Geometry (meters)

Outer domain, clockwise or anticlockwise orientation normalized by engine:

`(0,0) – (648,0) – (577.9,31.4) – (515,65.3) – (453.4,97.9) –
(386.9,130.6) – (327.6,162) – (315.5,162)`

The **five internal boundaries**, from upstream to downstream, use the
official coordinate table (not manually digitized screenshot pixels):

1. (168.1,0) – (302.2,130.6) – (315.5,162).
2. (200.7,0) – (311.9,130.6) – (319.5,162).
3. (307.1,0) – (331.3,130.6) – (328.8,146.1) – (321.6,162).
4. (310.7,0) – (333.7,130.6) – (331.3,146.1) – (327.6,162).
5. (372.4,0) – (347,130.6) – (327.6,162).

These define **six physical regions**, from left to right:
Rockfill, Transitions, Core, Filter (very narrow), Transitions, Rockfill.
Do **not** merge regions merely because the outer/transition/filter
zones share equal shear strength properties. The core is different.

| Material | c′ (kPa) | φ′ (degrees) | γ (kN/m³) |
| --- | ---: | ---: | ---: |
| Rockfill | 0 | 45 | 20.4 |
| Transitions | 0 | 45 | 20.4 |
| Filter | 0 | 45 | 20.4 |
| Core | 85 | 23 | 18.1 |

End-of-construction **dry** case: groundwater method `none` (zero
pore pressure), no tension crack, surcharge or seismic loads.
Failure direction is right-to-left.

## The critical implementation detail: use an exact circle

The project format supports `surfaces.surface_type = "user"` and
`surfaces.user_circle = [100.3, 291.0, 278.8]`. A defined circle
takes precedence over a user polyline. The analyzer instantiates
`CircularSurface` directly, and calls all chosen LEM methods once.
It does **not** run differential evolution, estimate a circle from a
polyline, or choose a different minimum.

Existing manually drawn user polylines remain supported.

The model uses 50 slices by default; the engine may automatically insert
boundaries where the circle crosses a material zone. Changing slice count
is an explicit sensitivity experiment, not a change to the reference circle.
Only the constant interslice function is used for **Spencer**; the
half-sine function is used for **GLE/Morgenstern–Price**.

## Published results (reference-only until measured)

| Method | Slide2 FoS | Bentley / SVSLOPE FoS |
| --- | ---: | ---: |
| Bishop Simplified | 2.208 | 2.207 |
| Spencer | 2.292 | 2.291 |
| GLE/Morgenstern–Price | 2.301 | 2.298 |
| Janbu Corrected | 2.073 | — |

The original ACADS referee value is **2.29**, which is consistent with
rigorous full-equilibrium methods, **not** with simplified Bishop's
2.208. Do not silently align all methods to 2.29 or mislabel a
reference factor as a locally computed result.

## Usage

```bash
python main.py --example "ACADS 2(b) — Talbingo fixed circle"
python main.py examples/acads_2b.slp.json

# Engine regression, including a real run for four specified-circle solvers:
python -m pytest tests/test_acads_2b.py -q

# Headless single prescribed-circle solution:
python -c "from slipsurface.project import acads_2b_project; from slipsurface.analysis import run_analysis; r=run_analysis(acads_2b_project()); print({m: (x.fos, x.n_evals) for m,x in r.results.items()}, r.errors)"
```

Inspect the exact circle in Interpret, all method outputs, the material
regions and boundary-crossing slices, and rerun at 25/50/100 slices as a
convergence/sensitivity check. Errors in individual methods are reported,
not replaced with an optimization result. When benchmark assertions are
within tolerance the implementation can be marked numerically verified.
