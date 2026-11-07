# ACADS input and numerical review — 7 November 2026

This review separates input fidelity, fixed-surface solver verification and
critical-surface search. A matching result on a prescribed surface does not
establish that an unrestricted search finds the published minimum.

## Defects corrected

- **EX4 had the wrong weak-layer geometry.** Its factory inherited EX3(a)'s
  horizontal seam and base at y=20. The published EX4 has an inclined seam:
  upper edge (20,18.88)–(84,36.8), lower edge (20,18.28)–(84,36.2), base y=15.
  The factory, serialized `geometry` and region assignment points now use those
  coordinates. Region tests check the weak material at three positions along
  the seam and compare the saved project's complete analysis inputs with the
  factory. Source: RS2 Part I, section 6, Figure 1, printed page 13.
- **Published EX1(b) and EX1(c) names were interchanged.** EX1(b) is the
  water-filled tension crack; EX1(c) is the three-layer slope. Menu and model
  titles now use published numbering. Existing Python names and files remain
  compatible: `acads_1b_project` / `acads_1b.slp.json` still mean the layered
  model; `acads_1c_project` / `acads_1c.slp.json` still mean the crack model.
  Old CLI names remain accepted aliases. README's crack depth was also corrected
  from 2.685 m to the implemented and independently calculated 3.814 m.
- **Some numerical checks were too permissive.** EX3(b) previously accepted
  both Spencer and GLE within ±0.12 of one shared value, 1.26. It now checks
  each method, including Janbu Corrected, against its own published result.
  EX2(b) and Janbu fixed-circle checks also use a 1% relative tolerance.
- **Reference rows were mixed across manuals.** For EX3(a), RS2 Part I section 5
  reports Spencer/GLE/Janbu as 1.258/1.246/1.275; Slide2 2022 Table 7.2 lists
  1.246/1.275/1.258. Documentation now identifies the source for each set.
  These discrepant reference tables are not used to tune solver outputs.

## Measured fixed-surface comparisons

Computed with the bundled slice counts and method settings. Published values
are from the Slide2 manual, tables 1.2, 3.2, 4.2, 6.2 and 8.3. For EX1(a),
EX1(c) and EX1(d), the circles are the published Janbu result circles; for
EX2(b) and EX3(b), the problem itself prescribes the surface.

| Published case | Method | Reference FS | Computed FS | Difference |
| --- | --- | ---: | ---: | ---: |
| EX1(a) | Janbu Corrected | 0.990 | 0.989387 | −0.062% |
| EX1(c), layered | Janbu Corrected | 1.357 | 1.355277 | −0.127% |
| EX1(d), seismic | Janbu Corrected | 0.965 | 0.964538 | −0.048% |
| EX2(b) | Bishop | 2.208 | 2.206311 | −0.076% |
| EX2(b) | Spencer | 2.292 | 2.290116 | −0.082% |
| EX2(b) | GLE, half-sine | 2.301 | 2.299375 | −0.071% |
| EX2(b) | Janbu Corrected | 2.073 | 2.073190 | +0.009% |
| EX3(b) | Spencer | 1.277 | 1.276051 | −0.074% |
| EX3(b) | GLE, half-sine | 1.262 | 1.260354 | −0.130% |
| EX3(b) | Janbu Corrected | 1.294 | 1.294458 | +0.035% |

The largest absolute relative difference in this table is 0.131%. These are
actual calculations; reference FS values are not substituted into the solver.
Janbu Simplified is tested separately from the empirical correction and is
never compared directly with published Janbu Corrected factors.

## Remaining verification limits

- EX1(b)'s crack depth and water loading inputs are checked; this review does
  not claim a reproduced critical minimum for the crack problem.
- EX2(a) is a shallow upstream search. Its independent infinite-slope limit is
  tested separately from EX2(b)'s prescribed circle.
- EX3(a) and EX4 are non-circular optimization problems. Search constraints,
  slice counts, seeds and physical admissibility must be compared as well as
  FS. For EX4, published Spencer FS is 0.760 for block search and 0.707 with
  optimization; a single generic target would mix distinct searches.
- EX5 uses a hydrostatic water-table approximation. The source specifies a
  pore-pressure grid derived from a flow net. Exact EX5 validation requires
  representing that field; numerical proximity alone is insufficient.

## Reproduce the focused checks

The focused checks passed. The corrected EX4 also completed its bundled fine
non-circular search: all three configured methods returned finite, admissible
solutions (110.33 seconds in this environment). This checks execution and
admissibility, not agreement with a published optimized minimum.

```bash
python -m pytest tests/test_acads_2b.py tests/test_acads_3b.py \
  tests/test_acads_janbu_reference.py tests/test_acads_remaining.py \
  tests/test_acads_3a.py tests/test_talbingo_2a.py -m 'not slow'
python -m pytest tests/test_acads_remaining.py -m slow
```

Sources: [Rocscience Slide2 Slope Stability Verification Manual](https://static.rocscience.cloud/assets/verification-and-theory/Slide2/Slide_SlopeStabilityVerification.pdf)
and [Rocscience RS2 Slope Stability Verification Manual, Part I](https://static.rocscience.cloud/assets/verification-and-theory/RS2/RS2_SlopeStabilityVerification_Part1.pdf).
The original ACADS survey is Giam and Donald (1989), as reproduced by these
primary software-verification manuals. Reference edition and method labels
are retained above so differing tables remain distinguishable.
