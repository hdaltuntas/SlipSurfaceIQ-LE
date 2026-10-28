# ACADS 3(a) — water table with weak seam (VS_7)

**Status:** benchmark model and geometry/solver regression checks added; a
numerical match of the optimized critical surface and factor of safety is
**not asserted** until the full non-circular search has been executed and
its output independently reviewed. This benchmark is **ACADS 3(a)**, not the
separately prescribed ACADS 3(b) failure path.

## Original references

- Supplied screenshot: Bentley / SVSLOPE, *ACADS Models*, section 2.9,
  model VS_7, Figure 26 and Tables 19–20.
- Rocscience, *RS2 Slope Stability Verification Manual, Part I*, section 5,
  verification problem #07:
  https://www.rocscience.com/assets/verification-and-theory/RS2/RS2_SlopeStabilityVerification_Part1.pdf
- ACADS original benchmark: Giam & Donald (1989), referee FoS around **1.26**
  (Rocscience quotes the referee interval **1.24–1.27**).

## Exact inputs (metric, kN, m, kPa)

Outer polygon: (20,20), (84,20), (84,40), (67.5,40), (43,27.75),
(20,27.75). The upper slope runs from (43,27.75) to (67.5,40).

The 0.50 m **Soil 2** weak layer is bounded by two horizontal polylines:
(20,27.0)–(84,27.0) and (20,26.5)–(84,26.5).
The phreatic line is exactly (20,26.5)–(84,26.5), at the weak seam base.
Three distinct material *regions* result, with the same **Soil 1** above
and below the thin seam.

| Material | Cohesion c' (kPa) | Friction φ' (deg) | Unit weight γ (kN/m³) |
| --- | ---: | ---: | ---: |
| Soil 1 (both surrounding regions) | 28.5 | 20 | 18.84 |
| Soil 2 (weak seam) | 0 | 10 | 18.84 |

Water: γw=9.81 kN/m³, Hu=1.0, pore pressure
`u = gamma_w * max(0, y_wt - y_base)`. Negative pore-water pressures /
matric suction above the water table are excluded. No tension crack,
surcharge, anchors or pseudo-static load. Both soil materials use
18.84 kN/m³ above and below the phreatic surface.

Methods: Spencer (constant interslice) and GLE/Morgenstern–Price
(half-sine); 60 slices, right-to-left failure. Automatic non-circular
**polyline** search, 4 initially adjustable interior vertices, fine
effort and deterministic seed 0. This is SlipSurfaceIQ-LE's search
configuration; neither ACADS nor SVSLOPE reference is claimed to use
identical search algorithms, admissibility checks or slice discretization.

## Published reference values — NOT program outputs

| Source and method | Published FoS |
| --- | ---: |
| Original ACADS referee | 1.26 |
| Slide2/Rocscience Spencer | 1.258 |
| Slide2/Rocscience GLE | 1.246 |
| SVSLOPE Spencer — Slide | 1.258 |
| SVSLOPE Spencer — Slope Stability | 1.269 |
| SVSLOPE GLE — Slide | 1.246 |
| SVSLOPE GLE — Slope Stability | 1.264 |

The screenshot also lists a 1.268 / 1.264 comparison column; these
are **published comparison values**, not our measured results.
A method-to-method comparison must use each method's **own optimized**
critical surface, not one shared trial circle.

## Run the model and inspect the actual critical surface

From the repository root:

```bash
python main.py --example "ACADS 3(a) — weak seam + water table"
# Or open the serialized, editable example:
python main.py examples/acads_3a.slp.json

# Checks that do not claim an optimizer FoS result:
python -m pytest tests/test_acads_3a.py -q
```

Run **Compute** in the desktop Modeler. Inspect the calculated Spencer
and GLE FoS, the slip path along the thin seam, convergence and the
selected admissibility restrictions. For a fully reproducible command-line
search without launching Qt:

```bash
python -c "from slipsurface.project import acads_3a_project; from slipsurface.analysis import run_analysis; r=run_analysis(acads_3a_project()); print('FoS:', {k: v.fos for k,v in r.results.items()}, 'Errors:', r.errors)"
```

Record the FoS values, end coordinates, per-method critical polyline,
iteration counts, and the effect of refinement (40/60/80 slices; multiple
search seeds) before labeling the model numerically **VERIFIED** against
ACADS. A low FoS found on a physically inadmissible path is not evidence
of agreement with a published critical FoS.

## ACADS 3(b) is a separate test

The prescribed ACADS 3(b) path
(41.85,27.75) → (44,26.5) → (63.5,27) → (73.31,40)
appears in `tests/test_acads_3a.py` only as a repeatable **fixed-path
diagnostic**: check material attribution and that Spencer/GLE can solve
the same cross-section. **Do not** compare its FoS directly to the ACADS
3(a) optimized FoS of 1.26.
