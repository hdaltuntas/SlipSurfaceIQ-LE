# Published benchmark discrepancies: separate the mechanisms before changing a solver

## Review update — 7 November 2026

The [ACADS review](ACADS_REVIEW_2026.md) records the current input corrections,
method-specific fixed-surface comparisons and remaining search-verification
limits. In particular, EX4's inclined seam was previously modeled as a
horizontal layer, and EX1(b)/(c) display names were interchanged.

Two numerical defects were reproduced and corrected independently of those
reference values:

- Force-equilibrium bracketing discarded roots exactly on its sampling grid.
  Exact roots now participate in the existing nearest-branch selection and
  physical-validity checks. GLE's fallback force and lambda scans also retain
  exact sampled equilibria.
- Reinforcement intersection sampling could skip a short slip-surface domain
  or short polyline segment, and an earlier crossing outside the selected
  sliding mass could hide a later valid crossing. Sampling now includes the
  mass/domain bounds, polyline vertices and circle extrema. Arbitrary spline
  intersections still use finite sampling; this is a remaining limitation.

`tests/test_numerical_audit.py` contains 12 focused regressions, including
mirrored geometry, branch ordering and forced Newton fallback.

The UI audit also replaced the overflowing left toolbars with a grouped,
scrollable action rail, kept Compute/Interpret in the top bar, and made
contextual input controls horizontally scrollable. Small-screen tests cover
800×600, 1024×680 and 1366×768; themed tests cover light/dark appearance and
keyboard navigation. Actual previews: [light](images/modeler-light.png),
[dark](images/modeler-dark.png).

Validation on this checkout: **607 regular tests and 15 slow tests passed**,
including the complete ACADS search smoke checks and reinforced-model searches.
Ruff lint/format checks and Mypy (16 computation source files) passed.
`main.py --check` and an offscreen launch at Qt scale factor 1.5 also passed.
GUI checks use Qt's offscreen platform; native desktop behavior on other
operating systems was not exercised in this review.

## Earlier discrepancy investigations

This is a verification audit, NOT a claim that all calculated FoS values
now match. Reported SlipSurfaceIQ-LE outputs (user's 2026-10-28 runs):

| Case | Reported FoS | Published reference | Interpretation |
|---|---:|---:|---|
| Talbingo ACADS **2(b)**, specified circle | Bishop 2.206; Janbu Corrected 2.073 | Slide2 Bishop 2.208; Janbu Corrected 2.073 | Matches the SAME fixed circle and methods |
| Talbingo ACADS **2(a)**, searched upstream face | Not separately evaluated | SLOPE/W 1.951 (Bishop / rigorous) | Distinct search problem, now supplied as a second project |
| ACADS 3(a), weak seam + water table | ~~0.462~~ → **Spencer 1.227 / GLE 1.213 (resolved)** | Spencer ~1.258; GLE ~1.246–1.264 | Tensile roots rejected by the base-tension guard; seam mechanism found |
| Borges & Cardoso (2002), Case 2 | ~~0.861~~ → **Bishop 1.162 (resolved)**; Janbu 0.905; GLE 0.942 | Bishop 1.170; Morgenstern–Price 1.171 | Bishop now matches: the old 0.861 came from a degenerate tangent circle (see below). Janbu/GLE still find a shallow embankment-face mechanism — separate issue |

## Source hierarchy

- GeoStudio SLOPE/W Verification Manual §2.5 vs §2.6 (Talbingo);
  §2.7–2.8 (weak seam); §2.18 (reinforced embankment).
  https://files.seequent.com/GeoStudio/Manuals/Slope%20Stability%20Verification%20Manual.pdf
- Bentley PLAXIS LE, *Slope Stability Verification*, §2.7–2.10.
  https://bentleysystems.service-now.com/sys_attachment.do?sys_id=09696321976e125081d373b0f053af62
- Cross-check independent model/method tables:
  https://xslope.org/en/stable/verification/geostudio/

### Talbingo 2(a) versus 2(b)

2(a) **searches** the upstream critical circle of the dry dam. The
cohesionless upstream face has `tan(beta)=162/315.5`; independent
infinite-slope theory gives `FoS_limit = tan(45 deg)/tan(beta)
= 315.5/162 = 1.94753`, consistent with the published ≈1.95.

2(b) does **not** search; its circle has `(Xc,Yc,R) =
(100.3,291.0,278.8)`. The published Bishop FoS ≈2.208 and
Janbu Corrected FoS ≈2.073 are correct method-specific values on
THIS circle. An FoS of 1.951 is *not* the benchmark for 2(b).

The additional `acads_2a.slp.json` model is a critical circular
search with entry and exit on the upstream face. The existing
`acads_2b.slp.json` remains unchanged. Neither model's numerical
result is overwritten by reference data.

### ACADS 3(a): the search must be inspected

The geometry and strength inputs are already stored in
`examples/acads_3a.slp.json`. It uses a **noncircular**
critical-surface search, thin soil-2 weak seam at y=26.5..27.0,
and a water table at the seam base.

A published mechanism runs along this seam and rises toward the
upper crest; the distinct 3(b) *fixed* diagnostic reference
surface passes through `(41.85,27.75), (44.0,26.5),
(63.5,27.0), (73.31,40)`. This is useful for testing the solver
separately from the **3(a) optimizer**.

The `examples/acads_3b.slp.json` project now makes the exact four-point
specified surface directly selectable for the same section, with no
optimizer. A tight comparison of that solver control with the published
FoS helps distinguish a solver problem from an optimizer search problem.

The low reported FoS=0.462 was investigated using the checks below and
resolved as described after the list. Check that each returned lowest-FoS path:

1. Intersects ground at both ends and remains in the soil domain.
2. Has a physically defensible failure mechanism and positive normal
   and mobilisable base shear forces.
3. Crosses the expected weak seam with correct per-slice base materials.
4. Meets the current admissibility restrictions (`m_alpha_min`, force
   bounds). Recompute its FoS at 40/60/80 slices.
5. Is compared *separately* with a **diagnostically restricted**
   exit/entry search around the published wedge, not labeled as the
   unconstrained global minimum.

**Do not** force the default model to report 1.26 by discarding valid
lower-FoS surfaces or multiplying the result.

**Resolved (2026-10-31):** the low-FoS roots were *tensile*: their
equilibrium requires negative effective base normals far beyond the
slices' cohesive resistance (worst |N'|/cl ≈ 2.5) and half the
interslice forces in tension — physically impossible for soil.
`check_admissibility` now flags base tension beyond 0.5·c·l on more
than the end slices, and widespread interslice tension. With the
guard, the unrestricted 3(a) search reports Spencer 1.227 / GLE 1.213
(published 1.257 / 1.246, both on the seam mechanism), and the Arai–
Tagyo non-circular search improves from Spencer 0.322 to 0.418
(published 0.412). The prescribed 3(b) path (worst ratio 0.41, a
trailing-edge effect within cohesion) remains admissible.

A residual question is documented rather than forced: a single
trailing-edge slice in tension is accepted as the usual exit/entry
artifact; two or more such slices, or interior tension, reject the
root.

### Borges & Cardoso Case 2: support contribution is a priority

The existing input is a dry 5 m embankment with four undrained
soft-clay layers and geosynthetic tensile strength 200 kN/m,
33.7-degree interface friction, no anchorage and no adhesion.

The critical slip surface used by an independent reconstruction
develops the full 200 kN/m in its reinforcement, resulting in an
M–P factor near 1.15–1.17. Check whether SlipSurfaceIQ-LE's
FoS=0.861 surface intersects the geosynthetic and develops
`T = min(200, pullout_in, pullout_out)`. If it does *not*, the
comparison involves a different mechanism or pullout treatment.
Review the support intersection coordinates, available embedment
lengths, the effective overburden and the force direction before
altering the material strength.

**Resolved (2026-10-28):** the FoS=0.861 surface was a *degenerate
tangent circle* — a circle tangent to the flat base (y = 0) whose
sliding mass was numerically ~1.5e-4 m thick, i.e. a zero-mass
geometric artifact. Because it hugged the ground it never crossed
the geosynthetic, so `T = 0` and the reported 0.861 was effectively
the *unreinforced* embankment-face mechanism. Two fixes now guard
against this:

1. The slice engine rejects surfaces whose sliding mass is
   numerically zero relative to the model extent (degenerate-mass
   guard, active even at `min_depth = 0`).
2. The Borges fixture sets `advanced.min_depth = 1 m` so the search
   cannot stop at any near-tangent shallow artifact.

With these guards the Bishop search finds a deep circle that crosses
the geosynthetic, mobilises `T = 200 kN/m` (tensile capacity) and
reports **FoS = 1.162**, matching the published Bishop 1.170 within
0.7%. The Janbu/GLE searches now avoid the tangent artifact too but
still stop on a shallow embankment-face mechanism (~0.90-0.94); that
remaining difference concerns the *search's* mechanism selection, not
the reinforcement treatment, and remains open.

The older GeoStudio 2022 manual prints uncorrected Janbu FoS=1.233,
while the user-supplied reproduction quotes 1.209. Use the document
edition and exactly the same Janbu formulation when scoring.

### Reproducible audit (real solver, no reference-value substitution)

```bash
# Initial diagnostic with lower search effort (not an acceptance run):
python scripts/audit_verification.py --case borges --effort fast --output borges_audit.json
python scripts/audit_verification.py --case acads-3a --effort fast --output acads_3a_audit.json
python scripts/audit_verification.py --case talbingo-2a --effort fast --output talbingo_2a_audit.json

# Compare search domains ONLY as a sensitivity exercise:
python scripts/audit_verification.py --case acads-3a --effort fast --restrict-seam

# Final search and sensitivity analysis (higher computational effort):
python scripts/audit_verification.py --case acads-3a --effort fine --seed 0
python scripts/audit_verification.py --case borges --effort fine --seed 0
```

The audit prints the actual factor of safety, critical slip surface
coordinates, slices' base-material counts, pore pressure, admissibility
state, and reinforcement intersection/capacity/available pullout.
This permits an evidence-based separation between **solver error**,
**surface search error**, **support capacity error** and **a reference
from a different problem**.

**Status:** model identification and read-only instrumentation are
completed. ACADS 3(a) and Borges–Cardoso numerical agreement remain
open pending the captured solver diagnostics and independent comparison.
