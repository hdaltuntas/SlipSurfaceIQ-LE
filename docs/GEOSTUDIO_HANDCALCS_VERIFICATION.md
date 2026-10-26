# GeoStudio SLOPE/W — Verification by hand calculations (29 slices)

Source: **Seequent, GeoStudio Example – Verification – Hand Calculations**,
13-page PDF supplied for independent software-verification work.

This is a verification reference, **not** a copied GeoStudio example project
or a claim that SlipSurfaceIQ LE was geometrically modeled in SLOPE/W. The
numeric data in `tests/data/geostudio_handcalcs_29_slices.json` were transcribed
from its Table 1 (PDF page 4). No proprietary GeoStudio model files, logos or
screenshots are redistributed.

## Problem definition

- 2H:1V slope; height 10 m; one prescribed slip surface
- Mohr–Coulomb material, unit weight 20 kN/m³, c′=5 kPa, φ′=30°
- 29 slices, tabulated widths, weights, base angles, lengths and pressures
- Surface phreatic line in the supplied schematic; first two slices have
  tabulated pore pressure set to zero for expediency
- Source base-angle sign convention is inverted when mapping to the LE
  left-directed solver frame

## Reproduced reference values

| Quantity | PDF reference | Recomputed from rounded Table 1 |
| --- | ---: | ---: |
| Ordinary driving force | 795.340 kN | ~795.338 kN |
| Ordinary available resistance | 930.640 kN | ~930.664 kN |
| Ordinary FS | **1.170** | **~1.17015** |
| Bishop first trial F=1.170, numerator | 983.091 kN | ~983.115 kN |
| Bishop first updated FS | **1.236** | **~1.23610** |
| Bishop final FS | **1.249** | **~1.24883** |

The small deviations result from Table 1's three-decimal rounded inputs, and
are expected. The iterative Bishop test checks the intermediate 1.236 and
1.247/1.248 steps, not only the final FS.

**Important formulation distinction:** Source Eq. 3 (PDF page 3) calculates
Ordinary friction resistance as
`(W cos α − u L cos² α) tan φ′`. LE's `ordinary()` currently uses
`max(W cos α − u L, 0) tan φ′`. The latter yields roughly **1.0668**
for the same rounded slices, rather than GeoStudio's **1.170**.
That difference is **not** hidden with a relaxed tolerance or a benchmark
override. The test pins both formulae separately. Whether the Ordinary
method's pore-pressure convention should change requires an engineering
formulation review, backward-compatibility assessment, and independent
reference cases. No solver code has been modified here.

**Bishop:** The existing LE `bishop_simplified()` uses the conventional
`(c b + (W − u b) tan φ) / mα` relation with
`mα = cos α + sin α tan φ / F`. Its final result matches the hand-calculated
Bishop FS within the three-decimal publication precision. The test feeds
the published slice values directly into the real LE solver.

## Source-specific transcription cautions

1. Table 1 rounds L to three decimals, whereas the slice-5 worked example
   on PDF page 6 uses L=1.3232 m. A tolerance accounts for this.
2. On PDF page 3, Eq. 4 prints a denominator of 795.64 kN, while the
   immediately preceding text and Table 2 state 795.340 kN. The tabulated
   value is used.
3. PDF page 7, Eq. 8 appears to omit the factor L multiplying the effective
   normal stress when evaluating shear resistance. Dimensional consistency
   and its tabulated `~39.18 kN` require
   `S = c′L + σ′n L tan φ′`.
4. Tables 5 and 6 reproduce the same rounded 992.967 kN numerator. The text
   on page 7 uses 993.173 kN to quote FS=1.249. We compare the iterated
   converged FS rather than enforce equality of these rounded subtotals.

## Verification layers and limits

1. **Document-level:** independent standard-library arithmetic reconstructs
   the Ordinary/Bishop hand calculations from the 29 published slices.
2. **Solver-level:** a synthetic `SliceSet` with those exact weights,
   inclinations, bases and pressures is passed to the real LE Ordinary
   and Bishop solvers. It is not built by `make_slices()`.
3. **Unverified here:** end-to-end reproduction of the precise SLOPE/W circle,
   topographic discretization, phreatic line interpolation and critical
   slip-surface search. The supplied figure is not a sufficiently precise
   editable geometry definition for exact correspondence.

Run the benchmark:

```bash
python -m pytest tests/test_geostudio_handcalcs.py -q
```

This case is independent of the existing ACADS 1(a) benchmark and protects
against future changes to the selected LE solver's slice-level equilibrium.
