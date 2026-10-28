# Published benchmark discrepancies: separate the mechanisms before changing a solver

This is a verification audit, NOT a claim that all calculated FoS values
now match. Reported SlipSurfaceIQ-LE outputs (user's 2026-10-28 runs):

| Case | Reported FoS | Published reference | Interpretation |
|---|---:|---:|---|
| Talbingo ACADS **2(b)**, specified circle | Bishop 2.206; Janbu Corrected 2.073 | Slide2 Bishop 2.208; Janbu Corrected 2.073 | Matches the SAME fixed circle and methods |
| Talbingo ACADS **2(a)**, searched upstream face | Not separately evaluated | SLOPE/W 1.951 (Bishop / rigorous) | Distinct search problem, now supplied as a second project |
| ACADS 3(a), weak seam + water table | 0.462 | Spencer ~1.258; GLE ~1.246–1.264 | Large discrepancy requiring audit of actual optimized path |
| Borges & Cardoso (2002), Case 2 | 0.861 | Bishop 1.170; Morgenstern–Price 1.171 | Large discrepancy requiring reinforcement mobilization / search audit |

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

The very low reported FoS=0.462 is not yet explained. Check that
the returned lowest-FoS path:

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
