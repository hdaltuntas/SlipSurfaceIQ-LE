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
