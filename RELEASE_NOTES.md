# SlipSurfaceIQ LE 2026.1.4

Released: 2026-10-26

## Ordinary/Fellenius pore-pressure correction

- Align the pore-water contribution to the base normal with the Seequent
  GeoStudio *Verification – Hand Calculations* Ordinary Eq. 3:
  `N′ = max(V cos α + Hx sin α − u L cos² α, 0)`. Previously LE
  subtracted the unprojected `u L`. On the published 29-slice case this
  changes Ordinary FS from ~1.0668 to **1.170**, matching the reference.
- The difference affects **water-bearing** Ordinary circular and
  non-circular calculations. **Rerun any prior Ordinary analyses with
  groundwater, pore-pressure or Ru enabled before relying on the FS.**
  Dry reference solutions and other methods' equilibrium equations are
  unchanged.

## Bishop water-force verification

- Simplified Bishop already includes pore pressure using `u b` in its
  compact moment balance. Version 2026.1.4 makes the equivalent hand-
  calculation base-normal decomposition explicit: `U=u L`,
  `N=[V−(c L−U tanφ)sinα/F]/mα`, and `N′=N−U`.
- Verify the 29 published slice normals, the worked slice-5 Bishop
  total normal force (~103.916 kN at trial FS=1.170), effective normal
  force, wet/dry behaviour and `u b` algebraic equivalence. This
  prevents missing or double-counted pore pressure. No second pore
  pressure force is added to Bishop and the verified Bishop FS stays
  approximately **1.249**.

## Regression and compatibility

- Extend external GeoStudio 29-slice hand-calculation regressions to
  assert the **actual** LE Ordinary/Bishop solver results.
- Keep the standalone native PySide6 application, all nine methods,
  `.slp.json` format version 3, project migrations, and existing
  independent packaging structure.
- No SlipSurfaceIQ Suite integration or module version changes.
- The source project/installer version is **2026.1.4**; native artifacts
  are published separately after the cross-platform release gates.

---

# SlipSurfaceIQ LE 2026.1.3

Released: 2026-10-23

## Layered search performance

- Spencer/GLE now solves each fixed-strength equilibrium system to an internal
  step tolerance of at most 10⁻⁹. The project tolerance still controls the outer
  nonlinear strength iteration. Previously, the default tolerance of 0.005
  could stop the inner solver before force and moment balance passed, sending
  an almost converged solution through expensive nested fallback searches.
- Force, moment, free-end shear and admissibility checks remain in place. Search
  population sizes, iteration budgets and surface refinement are unchanged.
- Added six regression cases for Spencer and two Morgenstern-Price functions.
  They compare against a tight-tolerance solution and limit residual evaluations
  rather than wall time, so slow CI machines can still detect the regression.
- The unchanged layered circular/noncircular search regression completed in
  64.65 seconds locally; the previous run had not finished after about 40 minutes.
  A representative layered candidate fell from 4,164 residual evaluations to 21
  while retaining the same factor of safety.
- Package version and installer examples are now 2026.1.3. Project format remains
  version 3.

# SlipSurfaceIQ LE 2026.1.2

Released: 2026-10-23

This patch keeps reported factors of safety inside what the solver computed,
and states the vertical seismic sign used by the program.

## Calculation and reporting

- The slip-centre FS map stores only centres the search evaluated. The drawing
  blends neighbouring samples into smooth contours; a wide gap with no sampled
  centre stays empty. The legend states that every radius is not scanned.
  Critical centres on the right or upper grid edge are included in the last cell.
- Geosynthetic pullout uses effective overburden, σ′v = max(σv − u, 0). A water
  table uses the material's Hu; the Ru model uses ru·σv.
- Positive kv is upward, so the vertical force is (1 − kv)·W. In Slide2 a
  positive kv acts downward. When kv is not zero, both directions are solved and
  the lower factor of safety is kept. Reports name the governing kv.
  If either requested direction fails, that method is excluded from the critical
  results and the failed kv and reason are reported; both failures are retained.
- Spencer/GLE checks horizontal and vertical force balance, free-end shear and
  moment balance before accepting a solution, including fallback roots. Singular
  cases that cannot satisfy equilibrium now report a solution failure instead of
  an unbalanced factor of safety.
- The solver tolerance is the number entered in the dialog. The previous hidden
  scale of 10⁻² is removed.
- Janbu's 1973 correction factor no longer falls below 1 when d/L is outside
  the chart.
- Hardening Soil is labelled as its Mohr-Coulomb envelope, and SANISAND as an
  approximate peak friction angle. The stored model keys are unchanged.
- The horizontal seismic coefficient is entered from 0 to 1. Project-settings
  labels used by the English interface are in the translation catalogue.

## Verification and compatibility

- Added 25 regression cases covering equilibrium and mirrored slopes, failed
  vertical seismic directions, and critical samples at the contour-grid edges.
- Project format remains version 3. Existing files load. `both_vertical` defaults
  to on, so a saved analysis with kv ≠ 0 should be rerun: the governing direction
  may differ from the single sign stored before. A = 0 SHANSEP strength is unchanged.
- Pullout resistance below the water table is lower than the previous total-stress
  value. Deep circles whose Janbu factor would have dropped below 1 now stay at
  the simplified Janbu result.

# SlipSurfaceIQ LE 2026.1.1

Released: 2026-10-21

This patch corrects the SHANSEP undrained-strength equation and clarifies its
reference effective vertical stress in the calculation API, interface and reports.

## SHANSEP correction

- Corrected the strength law to `su = A + S * sigma'_v * OCR^m`. The minimum
  undrained strength A is an additive intercept; it was previously applied as
  `max(A, S * sigma'_v * OCR^m)`, which underestimated strength when A > 0.
- The materials dialog and report parameter summaries now identify A explicitly.
  The existing `shansep_su_min` project field and `su_min` Python parameter store A;
  project format remains version 3. Existing projects still load, but analyses
  with nonzero A must be rerun and their changed factors of safety reviewed.
- SHANSEP's Python `strength` method now requires explicit `sigma_v`, preventing
  accidental use of slip-base normal stress. Use `su(sigma_v_eff)` for direct
  strength evaluation. Non-finite SHANSEP parameters are rejected.
- Documented the reference stress and short-term fill limitations: B-bar,
  staged construction and depth-dependent OCR are not implemented.
- Added analytical force/moment-equilibrium, groundwater, reference-strength,
  project compatibility and Turkish/English dialog regressions.

## Verification and compatibility

- 41 new SHANSEP regression cases; 403 tests passed on the corrected source.
  GitHub CI passed on Windows and Ubuntu with Python 3.10, 3.13 and 3.14, plus
  Arch Linux, Fedora and openSUSE. Ruff and mypy checks passed.
- Project format remains version 3. **Rerun existing SHANSEP analyses with A > 0**
  and review their changed factors of safety. A = 0 retains the same strength law.
- Python scripts calling `Shansep.strength` must provide `sigma_v`; the GUI and
  LEM solvers supply it automatically.
- Native x86-64 packages target Windows (MSI), Ubuntu (DEB), Fedora/openSUSE (RPM)
  and Arch Linux. Packages are attached after installation, calculation,
  GUI/reporting and uninstallation checks pass on all five targets.

See [SHANSEP formulation and limitations](docs/SHANSEP.md) for the equation,
worked examples and short-term embankment limitations.

# SlipSurfaceIQ LE 2026.1.0

Released: 2026-10-20

This release improves calculation reliability and keeps support-force reporting
consistent with the forces used by the solvers.

## Fixes

- **Input validation:** unknown load kinds, load orientations and groundwater
  methods now produce an error instead of silently omitting a load or calculating
  a dry slope. Analysis settings, non-finite numbers and malformed loads are
  checked before analysis, including projects loaded from JSON or Python scripts.
- **Passive supports:** Ordinary/Fellenius and Simplified Bishop now solve the
  equilibrium equation with a bracketed root for passive forces. A trial value
  of FS=1 can no longer reject an otherwise valid solution merely because the
  trial support force reverses the driving force. Nonlinear strength updates and
  physical admissibility checks remain in effect.
- **Geotextile units:** geotextile capacities are consistently treated as kN/m
  in the calculation engine, including direct Python/API use. Out-of-plane bolt
  spacing no longer incorrectly scales these per-width capacities.
- **Support-force reporting:** text and PDF reports distinguish capacity
  (`Tcap`) from mobilised force (`Tmob`). Passive force is reported as `Tcap/FS`;
  active force equals `Tcap`. Result drawings display the mobilised force.

## Earlier review fixes included in this release

- Unsupported vertical slope faces and overhangs are explicitly rejected instead
  of being silently replaced by an interpolated sloping profile. Vertical outer
  model boundaries remain supported.
- Ponded-water weight is included in the mass centroid used for seismic moments.
- Janbu correction classifies actual base strengths correctly for Undrained and
  SHANSEP materials.
- Report metadata follows project-summary edits, undo/redo and edits made while
  an analysis is running.
- Launcher argument checks, English runner messages and consistent Ruff formatting.

## Verification and compatibility

- Regression coverage includes analytical passive-support block solutions,
  moment equilibrium, nonlinear-strength checks, mirrored models, invalid
  JSON/script input, geotextile units and Turkish/English report values.
- Project file format remains version 3. Valid existing projects remain readable;
  invalid settings that previously fell back silently now require correction.
- Python 3.10+; start with `run_windows.bat` on Windows or
  `./run_linux_mac.sh` on Linux/macOS.
