# ACADS Janbu audit — matching method, search and surface

## Reference

Primary source: Rocscience, *Slide2 Slope Stability Verification Manual*
(2022), VP1–VP10, tables 1.2, 3.2, 4.2, 5.3, 6.2, 7.2 and 8.3:
https://static.rocscience.cloud/assets/verification-and-theory/Slide2/Slide_SlopeStabilityVerification.pdf

The Janbu figures in those tables are **Janbu Corrected**. The
**Janbu Simplified** method is a separate, uncorrected force-equilibrium
result. It is not valid to compare Janbu Simplified to a published
Janbu Corrected FoS, or a minimum found by search to the FoS of a
**prescribed** surface.

| ACADS example | Verification problem | Janbu Corrected reference FoS | Comparison |
| --- | --- | ---: | --- |
| EX1(a), dry homogeneous | VP1 | 0.990 | critical circular search |
| EX1(b), tension crack | VP2 | 1.489 | critical circular search |
| EX1(c), three materials | VP3 | 1.357 | critical circular search |
| EX1(d), seismic | VP4 | 0.965 | critical circular search |
| 2(a), Talbingo Dam | VP5 | 1.949 | shallow upstream critical circle search |
| 2(b), Talbingo Dam | VP6 | 2.073 | one **given** circle (100.3,291.0,R=278.8 m) |
| 3(a), weak seam | VP7 | 1.258 | critical non-circular search |
| 3(b), weak seam | VP8 | 1.294 | one **given** four-vertex non-circular surface |
| 4, weak seam / water / surcharge | VP9 | 0.699 | block search with optimization |
| 5, excavated slope | VP10 | 1.457 | source pore-pressure **grid** |

ACADS 5's project uses an approximated *water-table line* rather
than the published pore-pressure grid; direct agreement must **not**
be claimed until that field is modeled.

The 3(a) value above is from the Slide2 2022 table. RS2 Part I section 5
instead reports Janbu Corrected 1.275; the two manuals' method rows differ.
Do not interchange those reference sets. Legacy `acads_1b` file/factory identifiers
refer to published EX1(c), and legacy `acads_1c` identifiers refer to EX1(b).
See [the ACADS review](ACADS_REVIEW_2026.md) for the corrected mapping and measured results.

### What was corrected

1. All bundled ACADS example menus and editable project fixtures
   include Janbu Corrected where the source reference uses it. Some
   retain Janbu Simplified side by side, intentionally.
2. Janbu's geometric depth `d` is now the maximum **downward**
   perpendicular distance from the exit–entry chord to the base.
   An upward bulge no longer artificially adds depth.
3. The empirical polynomial `f0 = 1 + b1(r - 1.4r²)` has its maximum
   at `r=d/L=1/2.8`. Outside its original range the expression
   turns downward, eventually reaching `f0=1`. Deep models
   saturate at that maximum (the XSLOPE convention) rather than
   silently losing the correction.
4. `b1` remains 0.31 for pure friction, 0.69 for cohesion-only,
   and 0.50 for combined c–φ or mixed-layer paths, consistent
   with Rocscience's Janbu documentation.

The underlying **Janbu Simplified force-equilibrium equations have
not been modified** and the factor of safety is never overwritten
with a reference number.

### Independent specified-surface checks

`tests/test_acads_janbu_reference.py` uses the published VP1,
VP3, VP4, VP6 circles and the VP8 non-circular path. It checks
actual Janbu Corrected FoS at the **same slip surface** to a
1% relative tolerance, and `F_corrected = f0 F_simplified`.

It does not claim that the search engine reproduced the published
critical minimum: optimizer bounds, slice counts, source method
configuration and admissibility checks can change the minimum.
For VP5/7/9 the minimum must be audited separately, including
critical surface coordinates and material attribution.

Run:

```bash
python -m pytest tests/test_acads_janbu_reference.py tests/test_methods.py -q
python main.py --example "ACADS 2(b) — Talbingo fixed circle"
python main.py --example "ACADS 2(a) — Talbingo critical upstream search"
python main.py --example "ACADS 3(b) — weak seam specified path"
```

For deep or non-convex surfaces outside the validated Janbu
empirical chart, report the capped correction explicitly and
supplement with Spencer or GLE full-equilibrium validation.
