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

**Ordinary/Fellenius in LE 2026.1.4:** GeoStudio Eq. 3 (PDF page 3)
projects the pore pressure into the base normal according to
`(W cos α − u L cos² α) tan φ′`. LE previously used the unprojected
`u L` term and consequently produced approximately **1.0668** for these
same rounded slices. The corrected `ordinary()` now uses `u L cos² α` **for circular
moment equilibrium only** (with its existing effective-normal non-tension
cap) and matches the published **1.170** factor of safety on the same
slice inputs. Non-circular Ordinary uses force equilibrium and retains
`u L`, as verified by the independently derived submerged planar-block
test. This is an intentional numerical change: existing water-bearing
**circular** Ordinary analyses must be rerun, with method assumptions
reviewed before design decisions.

**Bishop:** LE already included pore pressure through the conventional
`(c b + (W − u b) tan φ) / mα` relation with
`mα = cos α + sin α tan φ / F`. In 2026.1.4 the corresponding
total and effective normal-force decomposition is explicitly calculated
and regression-tested using PDF Eq. 10:
`U = u L`, `N = [W − (c L − U tan φ)sinα/F]/mα`,
`N′ = N − U`. Its algebraic equivalence to the original `u b`
term is asserted so pore-water forces cannot silently be omitted or
counted twice. The calculated Bishop factor of safety remains **1.249**
at the precision of the reference.

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
The scope remains slice-level, not GeoStudio CAD geometry or full slip search.

**Precision caveat:** PDF Table 1 rounds base width `b` and length `L`
independently. The identity `b=L*cos α` is exact for consistent geometry
but not exact for the published rounded values. Tests compare the Bishop
normal-force formula against the equivalent compact equation after deriving
`b` from `L*cos α`, rather than diluting physical checks with loose tolerances.
