# Arai & Tagyo (1985) — layered slope, example 2 (Slide2 VP15)

## Source and verification status

The **model geometry, material parameters and search setup** are reproduced
from Bentley Systems, *PLAXIS LE Slope Stability Verification Manual* (2024),
§3.4, Figure 39 and Tables 39–41, model IDs
`VS_15_Circular` and `VS_15_NonCircular`.

- Bentley PDF: https://bentleysystems.service-now.com/sys_attachment.do?sys_id=09696321976e125081d373b0f053af62
- Independent geometry/parameter presentation: Rocscience,
  *RS2 Slope Stability Verification, Part I*, §11,
  https://www.rocscience.com/assets/verification-and-theory/RS2/RS2_SlopeStabilityVerification_Part1.pdf
- Original study: Arai & Tagyo (1985), example 2. Follow-up comparisons:
  Greco (1996), Malkawi et al. (2001), Kim et al. (2002).

This example belongs to the Bentley **Slope Stability Group 1** suite
(section 3.4), not to the original numbered 1(a)–4 ACADS problems.
The two built-in models use **one shared geometry** and different
**search families**. Global-minimum numerical agreement is a *separate
pending verification*. Published reference values below are **not**
hard-coded into either solver or treated as computed outputs.

## Geometry — all coordinates in metres

External boundary (cyclic):

```text
(0,3) → (96,3) → (96,35) → (72,35) → (48,35)
→ (24,19) → (18,15) → (0,15) → close
```

Internal material lines:

- Upper / middle interface: `(24,19) → (72,35)`
- Middle / lower interface: `(0,3) → (96,35)`

These create **three physical polygonal regions**, with exact areas:
upper = 192 m², middle = 684 m², lower = 1536 m²;
overall model = 2412 m². Assignment points:
upper (48,31), middle (48,24), lower (48,12).

| Zone | c′ (kPa) | φ′ (°) | γ (kN/m³) |
|---|---:|---:|---:|
| Upper layer | 29.4 | 12.0 | 18.82 |
| Middle layer, weak | 9.8 | 5.0 | 18.82 |
| Lower layer | 294 | 40.0 | 18.82 |

**Completely dry**: no groundwater line; `groundwater.method="none"`,
`u=0`, no applied loads, no reinforcement, no tension crack and
`kh=kv=0`. Failure direction is right-to-left. Each stored example
uses 50 primary vertical slices; the engine also inserts slices at
material-boundary crossings.

## Separate searches and published FoS

**Circular**, auto-refine search, each method separately optimized:

| Method | Bentley Table 40: Slide | Slope Stability |
|---|---:|---:|
| Bishop Simplified | 0.421 | 0.423 |
| Janbu Simplified | 0.410 | 0.415 |
| Spencer | 0.424 | 0.426 |

**Non-circular**, Bentley Table 41, Greco-style random search +
optimization (the Bentley reference uses 1,000 trial surfaces):

| Method | Slide | Slope Stability |
|---|---:|---:|
| Janbu Simplified (force equilibrium) | 0.394 | 0.397 |
| Spencer (force and moment equilibrium) | 0.412 | 0.424 |

Another publication (Rocscience Slide2 VP15) reports a
**different random-search procedure and corresponding numerical values**;
for example, non-circular Spencer 0.407 and Janbu Simplified 0.387.
Do not combine minima from different searches as if they use
identical slip paths.

**Important**: SlipSurfaceIQ-LE uses differential evolution and
Nelder–Mead rather than Bentley's Greco random search, with its own
kinematic/admissibility checks. It therefore cannot claim exactly
matching optimization histories or critical surfaces without
comparative analysis. Do not adjust the LEM equations just to force
a published number.

## Bundled models

- `examples/arai_tagyo_layered_circular.slp.json`:
  Bishop Simplified, Janbu Simplified and Spencer; circular automatic search.
- `examples/arai_tagyo_layered_noncircular.slp.json`:
  Janbu Simplified and Spencer; optimized non-circular **polyline**,
  four initial interior vertices and fine search effort.

Both examples appear in *File → Examples*. They can be opened directly:

```bash
python main.py --example "Arai & Tagyo — layered (circular)"
python main.py --example "Arai & Tagyo — layered (noncircular)"
```

The corresponding input and geometry/slicing regression:

```bash
python -m pytest tests/test_arai_tagyo_layered.py -q
```

## Full numerical validation (not automatically presumed to pass)

The following explicitly runs **both full searches** and reports the
actual computed FoS. It can require substantial compute time:

```bash
python -c "from slipsurface.project import arai_tagyo_layered_circular_project,arai_tagyo_layered_noncircular_project; from slipsurface.analysis import run_analysis; [(lambda r: print(p.name, {k:round(v.fos,6) for k,v in r.results.items()}, r.errors))(run_analysis(p)) for p in (arai_tagyo_layered_circular_project(),arai_tagyo_layered_noncircular_project())]"
```

Before numeric acceptance, check:

1. Three regions and every slice's base material are correctly assigned.
2. Soil weights and zero pore pressures (dry case) agree with the input.
3. Both circular and non-circular methods converge and return
   **admissible** surfaces inside the model.
4. The independently optimized minimum for each method is recorded,
   including exit/entry abscissae and circle centre/radius or polyline
   vertices.
5. Rerun with 40, 50 and 80 slices, and multiple search seeds to
   distinguish slice discretization from optimizer stochasticity.
6. Compare numeric deviations to **both** published vendor columns.
   Do not assume that a matching FoS implies the same surface.

**Current automated checks cover inputs, zone topology, dry slicing,
one diagnostic circular solver evaluation and correct optimization
configuration. They do not falsely assert the vendor's global search
minimum.**
