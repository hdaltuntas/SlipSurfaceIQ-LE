# SlipSurfaceIQ LE 2026.1.6

Released: 2026-10-27

## Material boundaries starting at the slope toe

- A material boundary that starts or ends at a concave corner of the
  external boundary (typically the slope toe) did not close its layer: its
  end was pushed slightly into the model, so the layers above and below it
  merged into one region and **Assign Material** set both at once. In ACADS
  EX1(b) the top layer silently took the bottom layer's material and FS came
  out about 10 % low (Bishop 1.254 instead of 1.402). Such ends now snap
  exactly onto the boundary vertex. **Reanalyse projects whose material
  boundaries start at the toe or another concave corner.**
- New bundled example *ACADS EX1(b)* (`examples/acads_1b.slp.json`): Bishop
  1.402, Spencer 1.372, GLE 1.371, Janbu simplified 1.258.

## Update notifications

- At start-up (at most once a day, silent when offline) the program checks
  the latest published GitHub release. When a newer version exists, a
  dialog shows the start of its release notes with **Open Download Page**,
  **Skip This Version** and **Later**. Nothing is downloaded or installed
  automatically and no project data is sent.
- **Help → Check for Updates…** and a button in the About dialog check on
  demand and always report the result (up to date, new version, or why the
  check failed). **Help → Check for Updates at Start-up** turns the
  automatic check off.
- Uses only the Python standard library. Bundled builds fall back to the
  distribution's CA certificate bundle when their own store is empty.

## Packaging workflow

- Release publishing accepts both `v2026.1.5` and `2026.1.5` tags. The
  2026.1.5 release was tagged without the `v`, so its package upload was
  refused. To publish its packages, point that release at a `v2026.1.5` tag
  on the same commit and re-run the failed *Native packages* run.

# SlipSurfaceIQ LE 2026.1.5

Released: 2026-10-27

## Slicing: direction-independent slice boundaries

- When an equal-width slice boundary fell within the sliver tolerance
  (0.01 % of the mass width) of a ground, water-table, load or
  polyline-surface vertex, the leftmost point was kept. The vertex could be
  dropped, which left a kinked slice top and made the result depend on the
  failure direction. Geometric boundaries now take precedence.
- A slice boundary is also placed where the slip surface crosses a material
  boundary (as in Slide2), so each slice base lies in one material instead
  of taking the material at its midpoint.
- On the bundled `layered_water_table` example, the same circle analysed
  right-to-left and mirrored left-to-right differed by about 2 % in FS
  (e.g. Bishop 1.197 vs 1.221 with 30 slices). Both directions now agree.
  **FS values of layered models can change slightly; rerun them** before
  relying on earlier results. New regression tests pin the mirror symmetry.

## Force methods: physical root instead of a spurious low one

- The force-equilibrium methods (Janbu, Corps of Engineers #1/#2,
  Lowe-Karafiath) bracketed `E_n(F) = 0` from the lowest F upward and took
  the first root. At low F the interslice recurrence has poles and spurious
  real roots, so Corps #1 on the layered example returned FS 0.31 (base in
  tension) or no result (m_alpha <= 0) depending on the slice count, while
  the physical root was about 1.29. Brackets are now tried nearest the
  Bishop/Ordinary start estimate first, and roots with m_alpha <= 0 are
  rejected. Corps #1 now gives 1.286 / 1.287 / 1.288 with 30 / 31 / 60
  slices. Corps #2 on the Bishop critical circle of `anchored_cut` moves
  from 0.330 to 1.445 and of `soil_nail_shotcrete` from 0.698 to 1.784.
- The spurious roots had a base in tension, so with the default
  admissibility check the search already rejected them; critical-search
  results change only slightly (e.g. `anchored_cut` Corps #2 1.385 ->
  1.382, as surfaces previously lost to a spurious root are now evaluated).
  **With the admissibility check switched off, rerun force-method
  analyses**: they could report these spuriously low FS values.

## Packaging workflow

- A push to `main` no longer fails the *Native packages* workflow when the
  current version has no release tag yet, its application code differs from
  the tag, or the release already has assets. The packages are still built
  and verified, and publishing waits for the release event or a manual
  dispatch, both of which still fail on any mismatch.

## Documentation

- State that ponded water is added as vertical weight only.
- Correct the MSI version mapping example in `packaging/README.md`.

# SlipSurfaceIQ LE 2026.1.4

Released: 2026-10-26

## Ordinary/Fellenius pore-pressure correction

- Align the pore-water contribution to the base normal with the Seequent
  GeoStudio *Verification – Hand Calculations* Ordinary Eq. 3:
  `N′ = max(V cos α + Hx sin α − u L cos² α, 0)`. Previously LE
  subtracted the unprojected `u L`. On the published 29-slice case this
  changes Ordinary FS from ~1.0668 to **1.170**, matching the reference.
- This correction affects the **circular moment-equilibrium** Ordinary
  method. Non-circular Ordinary uses the separate base-force formulation
  and retains the physical normal pore force `u L`; its analytical
  planar-block checks remain unchanged. **Rerun prior water-bearing
  Ordinary circular-surface analyses** (groundwater, pore pressure, Ru)
  before relying on the FS. Dry reference solutions and other methods'
  equilibrium equations are unchanged.

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
