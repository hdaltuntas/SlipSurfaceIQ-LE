# SlipSurfaceIQ LE — Independent Development Plan

Status: planned development work based on the `main` baseline at **2026.1.3**.
This document does not itself change a solver, a project format, or a release.

## Product boundary

**SlipSurfaceIQ LE is an independent native desktop product**, not a module of
SlipSurfaceIQ Suite. The repositories remain separate:

- LE repository: `hdaltuntas/SlipSurfaceIQ-LE`
- Suite repository: `hdaltuntas/SlipSurfaceIQ-Suite`
- LE continues with its own release numbers, CI, packaging and road map.
- There are **no cross-repository imports, shared runtime packages, module
  manifests or automatic Suite installation of LE**.
- The existing modeler and Interpret UI remain LE-owned. Their separation is
  not changed without a dedicated GUI architecture decision.
- Retain the existing `.slp.json` project format v3 and its migrations.
- Preserve the existing GNU AGPL v3-or-later repository license and original
  copyright/third-party notices.

The applications can have consistent *branding* if approved later, but neither
product must inherit the other's theme or CAD implementation.

## Verified architectural baseline (main)

- Qt/PySide6 native desktop UI under `slipsurface/ui/`
- Geometry and CAD tools under `slipsurface/geometry/` and `ui/cad/`
- Limit-equilibrium solvers under `slipsurface/lem/` (including Bishop,
  Janbu, Spencer and GLE)
- Search/optimization under `slipsurface/optimizer/`
- Independent analysis and project serialization
- Windows MSI and Linux DEB/RPM/Arch packaging workflows
- Turkish/English UI, PDF reports, loads/supports and DXF workflows

Read the release notes and the CI results before modifying a numerical method.

## Development sequence

### LE-1 — Reliability baseline and acceptance gates (next)

1. Record current CI status for Linux and Windows and run the test suite without
   mutating models or solver tolerances.
2. Use benchmark examples (especially ACADS EX1(a), layered cases, supported
   slopes and seismic cases) as regression inputs.
3. For each discovered defect: write a failing test, fix the narrow root cause,
   verify equilibrium residuals and unchanged reference results, then issue a
   patch release only for an actual fix.
4. Classify failures separately as numerical correctness, convergence/search,
   geometry validity, and native GUI issues.

**Gate:** no unreviewed changes to FS, force/moment equilibrium acceptance, or
serialized inputs. Discrepancies need reproduced inputs and expected values.

### LE-2 — CAD modeling ergonomics

1. Audit active drawing tools, selection, coordinate entry and zoom/pan.
2. Check SNAP/GRID/ORTHO/OSNAP, multi-region editing and undo/redo.
3. Check support, facing, load and groundwater interaction in the same model.
4. Keep all CAD source and Qt widgets native and resident in the LE modeler.
5. Test typical 1366×768 and 1920×1080 displays and HiDPI configurations.

**Gate:** editing remains non-destructive; projects round-trip without geometry
changes; no solver adjustments for purely visual fixes.

### LE-3 — LEM numerical verification

1. Maintain independent closed-form and published reference cases.
2. Verify Bishop, Janbu, Spencer and GLE residual/convergence acceptance.
3. Cover water, tension cracks, support forces, vertical/horizontal seismic
   terms, non-circular surfaces and difficult layered models.
4. Investigate unsupported geometry and solver failure messages explicitly.
5. Separate computational speed optimizations from numerical changes, with
   acceptance thresholds for both.

**Gate:** results do not regress on reference factors of safety and
force/moment checks. No silent fallback to unconverged FS values.

### LE-4 — Results, reporting and cross-platform release QA

1. Improve Interpret navigation, contour legend, slip-surface queries and
   evidence of method-specific convergence.
2. Preserve printer-readable PDF outputs and report method traceability.
3. Validate project migrations and DXF import/export.
4. Run source tests, native UI smoke tests, package install-launch-uninstall
   checks and accessibility checks for English and Turkish.
5. Publish independent LE release notes and packages after all gates pass.

## Existing PR boundaries

- PR #5: optional local Ollama assistant. Do not merge without quality/privacy
  review and explicitly approved scope.
- PR #6: community, verification and JOSS work. Do not merge until metadata and
  author-specific disclosures are confirmed.
- Keep these PRs independent of solver, CAD and GUI changes to `main`.
- Rebase or resolve conflicts only after evaluating the full differences; do
  not overwrite external contributors' pending work.

## Versioning

- Baseline: **2026.1.3** (LE only).
- An accepted bug fix may warrant an LE patch number; a substantial new
  capability requires its own release decision.
- `slipsurface/project.py` project format v3 is not tied to marketing version.
- Suite module versions and core API versions have no bearing on LE numbering.

## Immediate next implementation task

Start LE-1 with a **reproducible numerical and CAD regression audit**.
Choose one evidenced defect or gap, add a targeted failing regression, and
implement the smallest corrective patch. Publish no release before the
Linux/Windows matrix is green and the result has been independently checked.

No changes to source calculations are authorized by this plan alone.
