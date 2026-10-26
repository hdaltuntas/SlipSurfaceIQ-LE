# GeoStudio SLOPE/W — Additional examples and independent LE checks

Two **official, public Seequent GeoStudio** documents extend the existing
29-slice hand-calculation benchmark. We do **not** redistribute the vendor's
PDFs or proprietary `.gsz` projects. The compact reference data fixture is
`tests/data/geostudio_slope_examples.json`.

## A. SLOPE/W Tutorial – Getting Started

**Source:** https://files.seequent.com/GeoStudio/SlopeW/SLOPE%20Tutorial.pdf

| Data | Published reference | Source location |
| --- | --- | --- |
| Domain | Eight exact point coordinates, two material zones | PDF p. 5, Table 1 |
| Upper material | γ=17 kN/m³, c′=4 kPa, φ′=20° | PDF p. 5, Table 2 |
| Lower material | γ=18 kN/m³, c′=8 kPa, φ′=25° | PDF p. 5, Table 2 |
| Piezometric line | (0,10), (16,8), (24,7), (40,7) m | PDF p. 6, Table 3 |
| Search samples | Six entry × six exit × eleven radii = 396 | PDF p. 7, Figure 5 |
| Vendor critical FS (Spencer) | 1.370 | PDF p. 7 |
| Vendor Bishop on critical surface | 1.366 | PDF p. 8 |
| Vendor Janbu simplified on critical surface | 1.269 | PDF p. 9 |
| Vendor interslice lambda | ≈0.28 | PDF p. 8 |

**Automated tests implemented:**
- Reconstruct the exact 8-point, two-material geometry, mirroring x once so
  the ground profile follows LE's ascending-to-the-right solver convention.
- Check distinct material properties, piezometric ordinates and layering.
- Run the real `make_slices()` for a reproducible **illustrative** fixed circle.
- Confirm both materials are crossed and water above the toe adds actual
  slice weight. Confirm nonzero pore pressure and zero pressure in the
  `pore="none"` control.
- Solve that same constructed circle with real Bishop, Spencer and Janbu
  simplified methods; check convergence/admissibility and broad method
  relationships without mislabelling them vendor results.

**Comparison limitation:** the PDF supplies the 396 search count and two
entry/exit ranges, but not the original vendor's **radius sampling bounds,
complete computed trial circles or exact critical-circle coordinates**.
The plotted shape cannot be used to establish equality to vendor
**FS=1.370** or `lambda=0.28`. The reference numbers are stored as
metadata and explicitly **not scored as a numerical match**. Exact
critical-surface benchmarking requires the solved vendor project or complete
search settings and candidate geometry, plus matching ponded-water and
failure-direction conventions.

## B. Limit Equilibrium Formulation

**Source:** https://files.seequent.com/GeoStudio/SlopeW/Limit%20Equilibrium%20Formulation.pdf

The document demonstrates three qualitative method relations:
1. For a circular slip, Bishop's moment-equilibrium FS is close to Spencer's
   crossing-point FS; Janbu simplified can be substantially lower
   (Figures 7–8, PDF pp. 7–8).
2. For a planar translational slip, Janbu simplified and Spencer coincide at
   force equilibrium; the separate moment-equilibrium factor may exceed them
   (Figures 9–10, PDF pp. 8–9).
3. A composite slip can require nonzero interslice shear, so it is unsafe to
   infer which approximate method is always conservative (Figure 11, p. 9).

**Automated checks implemented:** independently reconstruct a controlled
Mohr–Coulomb model using the **published** γ=20 kN/m³, c′=10 kPa and
φ′=26°. For a separate, precisely specified analytical planar block, verify
the actual LE **Janbu simplified / Spencer / GLE / Ordinary** force solutions
against an independently computed closed-form factor of safety (tight
tolerance, not a snapshot of another LE routine). For a reproducible
circular test, verify Bishop/Spencer closeness and lower Janbu value.
Explicitly require circular-only Bishop to reject a non-circular surface,
rather than call GeoStudio's *moment F* curve a Bishop solver output.

**Comparison limitation:** the vendor shows circular **1.523** and planar
**2.613** on plotted examples (PDF pp. 7–8); the **exact trial-circle
geometry and full planar coordinates needed for numerical equivalence**
are not tabulated. The tests therefore verify method mechanics on separately
specified geometries and record these two vendor figures as non-scored
references. The tested analogue is not the exact GeoStudio project.

## Verification hierarchy

| Level | Coverage | Status |
| --- | --- | --- |
| Published numeric data | Tutorial coordinates, strength, water and reference values | Recorded |
| Slicing/groundwater | Real layered `make_slices()` and toe ponding | Automated |
| Fixed-surface solvers | Real Bishop, Spencer, Janbu, Ordinary/GLE | Automated |
| Independent analytical check | Rigid translational planar block | Automated |
| Vendor search FS equality | GeoStudio Spencer 1.370; LEM formulation 1.523/2.613 | **Not claimed** |
| Full vendor project comparison | Same surface, slices, sampling and pore assumptions | Needs vendor `.gsz` |

The prior `docs/GEOSTUDIO_HANDCALCS_VERIFICATION.md` remains the stronger
**slice-for-slice numerical** vendor benchmark.

Run:

```bash
python -m pytest tests/test_geostudio_slope_examples.py tests/test_geostudio_handcalcs.py -q
```

This is a **verification-only change**: do not edit LEM formulas, the project
format, installers, app UI or product version to make mismatched search
procedures appear numerically identical.
