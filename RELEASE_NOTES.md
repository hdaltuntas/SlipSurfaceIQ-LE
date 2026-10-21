# Unreleased

- Optional local Ollama assistant under Tools / Araçlar, with Turkish/English UI
  and setup help, local model selection, streamed plain-text replies and Stop.
- Project context is opt-in and previewable; identifying summary fields and
  annotations are excluded. Only results matching current solver inputs are sent.
- Loopback-only connection, no HTTP proxy/redirects or cloud fallback, and local
  model metadata checks before each chat. Model installation is separate.
- Read-only explanations: no model edits, solver execution, Python execution or
  access to external files. Chats are in memory and reset on project changes.
- Protocol and GUI regression tests cover cancellation, errors, malformed streams,
  cloud aliases, bounded prompts and actual solver-result context. Real-model
  scientific answer quality has not yet been validated.

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
