# Borges & Cardoso (2002) Case 2 — geosynthetic embankment

## Purpose and verification boundary

This is GeoStudio SLOPE/W verification example **2.18**, corresponding to
Slide2 **VP31**. A 5 m frictional embankment stands on four soft clay
layers and is reinforced by a single **unanchored** geosynthetic. It is
different from Borges & Cardoso Case 3 (two construction stages).

**Input implementation is included. Published FoS values are NOT solver
outputs.** The global critical-circle search, material and support
constitutive assumptions, and method selection must be compared before
calling the example numerically verified.

Reference: Seequent, *Slope Stability Verification Manual*, §2.18,
Tables 55–56:
https://files.seequent.com/GeoStudio/Manuals/Slope%20Stability%20Verification%20Manual.pdf

Additional independent benchmark details:
https://xslope.org/en/stable/verification/geostudio/#218-borges-cardoso-geosynthetic-embankment-2

## Cross-section in metres

External polygon:
`(-30,-27), (45,-27), (45,0), (42.5,0),
(36.41,5), (6.15,5), (0,0), (-30,0)`.

Internal boundaries:

- Embankment/foundation interface: `(0,0)–(42.5,0)`
- Clay 1 / 2: `(-30,-1)–(45,-1)`
- Clay 2 / 3: `(-30,-4.5)–(45,-4.5)`
- Clay 3 / 4: `(-30,-7)–(45,-7)`

The foundation base is at y = −27 m. Coordinates are manually
transcribed from the provided diagram (some crest abscissae in the
vendor figure are small; retain source files for independent audit).

| Material | Model | c′/su (kPa) | φ′ (°) | γ (kN/m³) | Elevation |
| --- | --- | ---: | ---: | ---: | --- |
| Embankment | Mohr–Coulomb | c′ = 0 | 35 | 20 | y = 0 … 5 |
| Clay 1 | Undrained total stress | su = 33 | 0 | 17 | y = −1 … 0 |
| Clay 2 | Undrained total stress | su = 16 | 0 | 17 | y = −4.5 … −1 |
| Clay 3 | Undrained linear with elevation | su = 16 → 18.4 | 0 | 17 | y = −4.5 → −7 |
| Clay 4 | Undrained linear with elevation | su = 18.4 → 55.1 | 0 | 17 | y = −7 → −27 |

The new `UDG` model stores **top and bottom su plus their absolute
elevations**, and evaluates `su(y)` at each slice-base midpoint:

`su(y) = su_top + (su_bottom - su_top) * clamp((y_top-y)/(y_top-y_bottom), 0, 1)`.

The same total-stress strength is used by Bishop, Janbu and
Morgenstern–Price/GLE. For these undrained layers pore pressure is not
subtracted from normal force; the project explicitly uses groundwater
mode `none` (dry verification reference). The new model is editable
under Define Material Properties; older UD/SHANSEP models are unchanged.

## Geosynthetic

Single horizontal support from `(0,0)` to `(42.5,0)`:

- type: geosynthetic; tensile capacity **200 kN/m**
- interface friction **33.7°**; adhesion **0 kPa**
- anchorage **none**; strip coverage **100%**
- orientation **parallel** to reinforcement
- application **passive** (resisting force divided by FoS)
- overburden unit weight `20 kN/m³` for current approximate pullout
  integration, and 1 m out-of-plane width

The engine limits mobilized force to `min(200 kN/m, P_in, P_out)`.
Both embedment lengths must be sufficient; *unanchored does not mean
full tensile strength is automatically mobilized*. For this model,
evaluate pullout demand and the critical arc before treating the
reference 1.15 FoS as validated. There is no adhesive bonding.
The existing support model is an approximate LEM representation, not
a coupled tension–strain or construction-stage FEM formulation.

## Published factors of safety (not computed by SlipSurfaceIQ-LE)

| Source/method | Published FoS |
| --- | ---: |
| Borges & Cardoso (2002), Case 2 | **1.15** |
| GeoStudio simplified Bishop (moment) | 1.170 |
| GeoStudio Janbu (force) | 1.209 |
| GeoStudio Morgenstern–Price (moment/force) | 1.171 / 1.171 |

The Janbu method in this fixture uses LE's `janbu_simplified`; do not
compare a corrected Janbu factor against a simplified vendor value.

## Run

```bash
python main.py --example "Borges & Cardoso — geosynthetic embankment #2"
python main.py examples/borges_cardoso_case2.slp.json
python -m pytest tests/test_borges_cardoso_case2.py -q

# Full automatic critical-circle search and actual calculated results:
python -c "from slipsurface.project import borges_cardoso_case2_project; from slipsurface.analysis import run_analysis; r=run_analysis(borges_cardoso_case2_project()); print({k: v.fos for k, v in r.results.items()}, r.errors)"
```

The accompanying regression checks test the geometry, depth-gradient
material model, dry pore-pressure state, unanchored geosynthetic support
parameters and the actual slice-strength/force mechanics on one
reproducible diagnostic circle. They **do not substitute for**:
a global critical-circle search, alternate seeds and slice refinements,
comparison of force/moment residuals, and independent verification against
the reference 1.15/1.17 results.
