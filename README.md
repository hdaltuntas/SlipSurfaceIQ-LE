# SlipSurfaceIQ LE

**2D limit equilibrium slope stability analysis with a desktop CAD interface — version 2026.2.0**

[2026.2.0 release notes](RELEASE_NOTES.md) — source-only distribution. Run the application with `python main.py`; native packages and standalone launchers have been removed. Engineering modules, the CAD interface and verification tests remain available.

SlipSurfaceIQ LE is an open-source program for checking the stability of soil and rock
slopes, cuts and embankments with the limit equilibrium method (LEM). You draw the slope
cross-section, assign materials, add groundwater, loads and supports, and the program
searches for the critical slip surface and its factor of safety (FS) with the classic
methods of slices — Bishop, Janbu, Spencer, Morgenstern-Price/GLE and others.

The workflow follows the layout geotechnical engineers know from commercial tools such as
Slide2: a **Modeler** window for building the model and a separate **Interpret** window for
the results, which shows a slip-centre FS contour map, the critical surface, slice data and
a professional PDF report.

The interface and reports are available in **English and Turkish** and the language can be
switched at any time without losing work. The program runs on Windows, Linux and macOS.

> **Engineering disclaimer.** SlipSurfaceIQ LE is provided without any warranty. Results
> depend entirely on the input geometry, strength parameters, groundwater and loads.
> Always review and verify them with engineering judgement and, where it matters,
> with independent calculations or software.

---

## Contents

- [Highlights](#highlights)
- [Installation and start-up](#installation-and-start-up)
- [A typical workflow](#a-typical-workflow)
- [The Modeler window](#the-modeler-window)
- [The Interpret window](#the-interpret-window)
- [Calculation engine](#calculation-engine)
- [Material models](#material-models)
- [Groundwater, seismic loads and tension cracks](#groundwater-seismic-loads-and-tension-cracks)
- [External loads](#external-loads)
- [Supports and facings](#supports-and-facings)
- [Critical surface search](#critical-surface-search)
- [PDF report](#pdf-report)
- [Project files, DXF and Python scripting](#project-files-dxf-and-python-scripting)
- [Bundled examples](#bundled-examples)
- [Verification](#verification)
- [Keyboard and mouse reference](#keyboard-and-mouse-reference)
- [Development](#development)
- [Project layout](#project-layout)
- [Roadmap](#roadmap)
- [License](#license)

---

## Highlights

- **Nine limit equilibrium methods** — Bishop simplified, Ordinary/Fellenius, Janbu
  simplified and corrected, Corps of Engineers #1 and #2, Lowe-Karafiath, Spencer and
  GLE/Morgenstern-Price (four interslice functions).
- **Circular, non-circular and user-defined slip surfaces** with an automatic global search
  (differential evolution + Nelder-Mead), slope limits and a minimum depth.
- **Eleven strength models** — Mohr-Coulomb, generalized Hoek-Brown, Hoek-Brown (mb, s, a),
  Undrained (Tresca), SHANSEP, Hardening Soil, SANISAND, power-law envelope, Power Curve,
  Barton-Bandis, CNI rock mass.
- **Groundwater** by water table (with per-material Hu) or Ru coefficient, ponded water,
  **pseudo-static seismic** loading and **tension cracks** with crack water.
- **Supports** — end-anchored anchors, grouted tiebacks, soil nails, geotextiles,
  geosynthetics and micro-piles, single or as automatically placed **bolt patterns**;
  **shotcrete + wire-mesh facing**.
- **CAD-style drawing** with rulers, adaptive grid, SNAP / GRID / ORTHO / OSNAP, typed
  coordinates (`x,y`, `@dx,dy`, `@length<angle`) and unlimited undo/redo.
- **Results**: slip-centre FS contour map with a banded legend, critical surface, lowest
  25 surfaces, FS legend for all methods, slice query, text report and notes/shapes on the
  drawing.
- **Detailed computing dialog** showing method, search stage, generation, surfaces
  evaluated / valid / rejected, best FS, elapsed and remaining time and a log.
- **Professional PDF report** with cover, contents, summary, tables, figures and appendices.
- **DXF import/export** of the geometry and a built-in **Python scripting** console.
- **English / Turkish** interface and reports, light / dark theme, windows sized to the
  detected screen.

---

## Installation and start-up

### Source-only execution

SlipSurfaceIQ LE is distributed as **Python source code**. There are
**no MSI, DEB, RPM, Arch or PyInstaller application packages**, no installers,
and no separate launcher scripts. The **only supported application entry point
is `main.py`**. Python 3.10 or newer and the dependencies from
`requirements.txt` are required.

Get the repository using Git or download its source archive and extract it.
Run these commands from the repository root:

```bash
python -m pip install -r requirements.txt
python main.py
```

For an isolated environment (recommended):

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\python.exe -m pip install -r requirements.txt
# Windows PowerShell: .venv\Scripts\python.exe main.py
# Linux / macOS: .venv/bin/python -m pip install -r requirements.txt
# Linux / macOS: .venv/bin/python main.py
```

You can also run `main.py` directly from VS Code, PyCharm, or another
Python IDE, using an interpreter with the dependencies installed.
Neither `pip install -e .` nor OS-level package installation is required.

On minimal Linux desktops, install the Qt runtime shared libraries from your
operating system's repository if PySide6 reports that they are missing:

```bash
sudo apt install libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3       # Debian / Ubuntu
sudo dnf install libglvnd-egl libglvnd-opengl libxkbcommon fontconfig dbus-libs  # Fedora
sudo pacman -S libglvnd libxkbcommon fontconfig dbus                            # Arch Linux
sudo zypper install libglvnd libxkbcommon0 fontconfig libdbus-1-3              # openSUSE
```

### Command line

```bash
python main.py                                    # empty project, window sized to the screen
python main.py examples/anchored_cut.slp.json     # open a project file
python main.py --example "ACADS EX1(a)"           # open a bundled example
python main.py --list-examples                    # list the bundled examples
python main.py --check                            # check Python and the required packages
```

### Update notifications

The optional update checker shows source-release information from GitHub.
It never downloads or installs software. When an update is published, open the
release page to review its changes; update your local source checkout with
`git pull` (or download the newer source archive), reinstall requirements
if necessary, and start it with `python main.py`. Automatic checks can be
disabled under **Help → Check for Updates at Start-up**.

---

## A typical workflow

The workflow bar at the top of the Modeler follows the steps of a slope model; each step
shows its own toolbar.

1. **Geometry** — draw the external boundary (closed polygon) by clicking or typing
   coordinates, then material boundaries, the water table and, if needed, a tension crack
   line. Regions are created automatically from the boundaries.
2. **Properties** — define materials (*Properties → Define Material Properties*) and click
   inside the regions to assign them. Define shotcrete facing types and assign them to the
   slope face.
3. **Loading** — add distributed and line loads; set seismic coefficients in *Project
   Settings → Seismic*.
4. **Support** — define support types and draw single supports, click on the slope face to
   place bolts at a fixed inclination, or create bolt patterns.
5. **Surfaces** — choose circular, non-circular or a drawn user surface, the search effort
   and optional slope limits (entry/exit ranges).
6. **Compute (F5)** — the computing dialog shows the progress; when finished, the results
   open in the **Interpret** window.
7. **Interpret** — review the critical surfaces of all methods, query slices, add notes and
   create the **PDF report** (Ctrl+P).

Every edit can be undone (Ctrl+Z / Ctrl+Y). Changing the model invalidates the results and
asks for a new computation; display-only changes (colours, labels, notes) do not.

---

## The Modeler window

- **Menus:** File, Edit, View, Analysis, Boundaries, Loading, Support, Surfaces, Properties,
  Tools, Help.
- **Workflow bar:** Geometry › Support › Loading › Properties › Surfaces.
- **Left panel:** *Document Viewer* (materials, boundaries, supports, facings, loads, notes,
  methods — click an item to select it in the drawing) and *Display Options* (colours, line
  width, grid, ruler, material fill, legend, slope limits, material labels).
- **Dialogs:** Project Settings (General, Methods, Groundwater, Seismic, Advanced), Project
  Summary, Define Material Properties, Surface Options, Define Support Properties, Define
  Facing Types, coordinate table, grid settings.
- **Material labels** on the regions: none, name, or name + strength parameters and unit
  weights.
- **Notes:** text, line, arrow, rectangle and ellipse annotations, also on the results.
- **View → Language** switches between English and Turkish instantly (open project, undo
  history and results are kept); the theme (light / dark) is in the same menu. Both are
  remembered.
- On first start the Modeler and Interpret windows open at the size of the detected screen;
  dialogs scale with the screen resolution. **F11** toggles full screen.

### CAD drawing area

- Rulers, adaptive grid, crosshair cursor, material and FS legends.
- Wheel = zoom at the cursor, middle button = pan, middle double-click / F2 = zoom all,
  zoom window and pan tools.
- **SNAP** (F9, to the grid), **GRID** (F7), **ORTHO** (F8), **OSNAP** (F3: endpoint,
  midpoint, intersection, nearest).
- Coordinate box in the status bar: `x,y` · `@dx,dy` · `@length<angle` · `c` close ·
  `u` undo point · empty Enter finish.
- Editing: drag vertices, add/delete vertices, double-click for the coordinate table or the
  properties of loads, supports, facings and notes, Delete, right-click context menu.

---

## The Interpret window

- **Method selector** (e.g. "Spencer FS: 0.984") and **Global Minimum** button.
- **Slip-centre FS contour map** (circular searches): every admissible circle evaluated by
  the search contributes its centre; each grid cell shows the lowest FS of the circles
  centred there, smoothed into continuous bands with contour lines and a banded **FS
  legend** (0 … ≈6.4·FSmin). The critical centre carries an `FS = …` label, with dashed
  lines to the exit and entry points and the critical surface as a dashed line.
- Optional: slices and sliding-mass fill, the lowest 25 surfaces coloured by FS, spline
  control points — all switchable in *Display Options*.
- **FS legend** (bottom right) with the factor of safety of every method; the current
  method is highlighted and the global minimum shown in green.
- **Slice Data** query (click a slice), **Information Viewer** (complete text report — save
  or copy), image export.
- **Notes and shapes** on the results with their own undo/redo; they are picked by shape
  (on a line or arrow, inside a rectangle or ellipse), show grips and a selection frame,
  can be moved by dragging, edited by double-click and deleted from the context menu. They
  are saved in the project file and appear in the report.

---

## Calculation engine

| Method | Equilibrium | Surfaces |
|---|---|---|
| Bishop simplified | moment | circular |
| Ordinary / Fellenius | moment (circle) / force | circular and non-circular |
| Janbu simplified / corrected (f0) | force | circular and non-circular |
| Corps of Engineers #1, #2 | force | circular and non-circular |
| Lowe-Karafiath | force | circular and non-circular |
| Spencer | force + moment | circular and non-circular |
| GLE / Morgenstern-Price (half-sine, constant, clipped sine, trapezoidal) | force + moment | circular and non-circular |

- **Slicing:** a chosen number of equal-width slices plus extra boundaries at every ground,
  water table, load and polyline-surface vertex, so the top of each slice is straight, and
  where the slip surface crosses a material boundary, so each slice base lies in one
  material. These geometric boundaries take precedence when they nearly coincide with an
  equal-width one, so the result does not depend on the failure direction.
  Slice weights are integrated through all material regions (γ above, γsat below the water
  table).
- **Non-linear strength:** for curved envelopes the solvers iterate on the effective normal
  stress on each slice base and use the instantaneous (tangent) c and φ.
- **Admissibility:** solutions with mα < 0.2 (Whitman & Bailey) or a negative mobilised base
  shear (tension at the base) are rejected; interslice forces above a configurable multiple
  of the total weight are treated as singular. Both checks can be tuned in *Project Settings
  → Advanced*.
- **Failure direction:** right-to-left or left-to-right (*Project Settings → General*).
- **Geometry:** the ground must be a continuous, single-valued profile y(x).
  Vertical slope faces and overhangs are rejected with an explanatory message;
  vertical sides at the outer model limits remain supported.

---

## Material models

Choose the model in *Define Material Properties → Strength*. Every material has a unit
weight, an optional saturated unit weight, a colour and water parameters (whether the water
table acts on it and the piezometric factor Hu).

| Model | Strength | Notes |
|---|---|---|
| **Mohr-Coulomb** | τ = c′ + σ′n tan φ′ | |
| **Undrained (Tresca)** | τ = su | total stress, pore pressure not used |
| **SHANSEP** | τ = su = A + S · σ′v · OCR^m | A is additive; σ′v = max(W/b − u, 0) is the reference effective vertical overburden stress; total-stress analysis. [Details and limitations](docs/SHANSEP.md). |
| **Hardening Soil** | τ = c′ + σ′n tan φ′ | Mohr-Coulomb failure surface of the HS model; E50,ref, Eoed,ref, Eur,ref, m, pref, Rf and ψ are stored for reference — LEM uses only the failure envelope |
| **SANISAND** | τ = σ′n tan φ(ψ), sin φ = 3Mb / (6 + Mb), Mb = M exp(−nb ψ) | state parameter ψ = e − ec, critical state line ec = ec0 − λc (p′/pat)^ξ (Dafalias & Manzari 2004); in LEM p′ ≈ σ′n |
| **Power-law envelope** | τ = a · pa · (1 + σ′n/pa)^b | concave envelope for granular materials |
| **Power Curve** | τ = a (σ′n + d)^b + c | as in Slide2 |
| **Barton-Bandis** | τ = σ′n tan(φr + JRCn log10(JCSn / σ′n)) | joints; scale correction JRCn = JRC0 (Ln/L0)^(−0.02 JRC0), JCSn = JCS0 (Ln/L0)^(−0.03 JRC0); total friction angle ≤ 70° |
| **CNI rock mass** | τ = a · σc · ((σn − T0) / σc)^n | Cylwik, Killian & Cicchini (2023), in the variables of Slide2; instantaneous φ ≤ 70° |
| **Generalized Hoek-Brown** | σ1 = σ3 + σci (mb σ3/σci + s)^a | mb, s, a from GSI, mi and D (Hoek et al. 2002) |
| **Hoek-Brown (mb, s, a)** | same envelope | mb, s and a entered directly |

The Hoek-Brown envelopes are converted to τ–σn curves (Balmer) and used with instantaneous
c and φ.

---

## Groundwater, seismic loads and tension cracks

- **Water table:** u = Hu · γw · (water table − base elevation); Hu and whether the water
  acts are set per material. Ponded water above the ground is added to the slice weight
  as a vertical load only; the horizontal component of the water pressure on a sloping
  submerged ground surface is not modelled. Where that thrust matters (a submerged toe,
  a reservoir drawdown), model it explicitly with a surface-normal distributed load.
- **Ru coefficient:** u = Ru · σv (total vertical stress at the base).
- **Pseudo-static seismic loading:** horizontal force kh·W in the failure direction at the
  slice centroid; kv positive upward gives a vertical load (1 − kv)·W.
- **Tension crack:** a crack line is drawn (or created from a depth, with the Rankine
  z_c = 2c / (γ√Ka) as a suggestion). A slip surface crossing the line on the crest side is
  cut there and a vertical crack face rises to the ground. The crack can be dry, full or
  partially filled; the water thrust V = ½ γw hw² acts in the failure direction at hw/3.

---

## External loads

- **Distributed loads** on the ground surface between two points, uniform or linearly
  varying, acting vertically or normal to the surface.
- **Line loads** at a surface point with any direction angle.

All loads are included as forces and moments in every method.

---

## Supports and facings

| Support type | Force T (per support, then divided by the out-of-plane spacing) |
|---|---|
| End anchored | tensile capacity |
| Grouted tieback | min(tensile, bond strength × min(bond length, L_out)) |
| Soil nail | min(tensile, bond × L_out, plate + bond × L_in) |
| Geotextile | min(tensile strength, pullout × min(L_in, L_out)) |
| Geosynthetic | min(C · tensile, P_in, P_out), P = 2 · C · ∫(adhesion + σv tan δ) ds, σv = γ · depth; anchorage none / slope face / embedded end / both ends |
| Micro-pile | pile shear strength |

L_in and L_out are the support lengths inside and outside the sliding mass, C the strip
coverage. Each support type has:

- **Application:** *active* (the force reduces the driving force) or *passive* (the force is
  mobilised like shear strength, T/F).
- **Direction:** parallel to the support, tangent to the slip surface, or perpendicular to
  the support (micro-piles).

**Single bolts** are placed by clicking on the slope face with a given inclination (default
15° below horizontal) and length. **Bolt patterns** fill a stretch of the slope face with
equally spaced bolts and are edited as one object; each bolt acts as a separate support.

**Shotcrete + wire-mesh facing:** thickness, unit weight, shear strength τ, mesh (Q106 …
Q589 or a custom As) and fy. Its weight γ·t is applied as a surface load; where the slip
surface exits or enters through the faced surface, T = τ·t + As·fy acts tangent to the slip
surface against sliding (passive by default).

---

## Critical surface search

- **Circular:** each candidate is defined by its two ground intersections and the central
  angle, so every candidate is a valid circle.
- **Non-circular, polyline** (default, as in Slide2): straight segments through interior
  vertices. After the global search all vertices of the best surface are optimised freely,
  then a vertex is inserted in the middle of every segment and the surface is optimised
  again.
- **Non-circular, B-spline:** smooth surface; optionally convex only.
- **User-defined:** a surface drawn by hand is analysed directly.
- **Optimiser:** differential evolution (global) + Nelder-Mead (local); non-circular
  searches are seeded with the critical circle of a quick circular pre-search. Search
  effort: fast / normal / fine.
- **Slope limits:** left and right ranges for the exit and entry points, drawn on the
  ground; optional minimum sliding-mass depth.
- The **computing dialog** reports the method (i/n), the current stage, generation,
  surfaces evaluated / valid / rejected, lowest and last FS, slices, elapsed and estimated
  remaining time, with a time-stamped log. The computation runs in the background and can be
  cancelled at any time.

---

## PDF report

*File → PDF Report* (Ctrl+P) in either window creates a report in the current interface
language:

- cover with project data and a **critical FS card** assessed against a target FS
  (Adequate / Marginal / Inadequate);
- contents, summary, model figure and geometry description;
- material tables, analysis and search settings, loads, supports and facings;
- results table and FS comparison chart, critical surface figures for the global minimum
  and for each method;
- mobilised support forces, tension crack results;
- appendices with slice data and coordinates;
- page headers and footers, "Page n / N", PDF bookmarks.

The sections can be switched on or off; author, checker and company are remembered.

---

## Project files, DXF and Python scripting

### Project files

Projects are saved as `.slp.json` (format version 3). Files from earlier versions (1 and 2)
are converted automatically when opened. A project stores the geometry, materials,
groundwater, loads, supports, facings, search settings, display options and the notes of
both windows.

### DXF

*File → Import DXF / Export DXF* exchanges the 2D geometry. Importing replaces the current
model and can be undone with Ctrl+Z.

| Layer | Content |
|---|---|
| `SS_EXTERNAL` | one closed external boundary (alternatively a single closed polyline on layer `0`) |
| `SS_MATERIAL` | material boundaries |
| `SS_WATER` | one water table polyline |
| `SS_CRACK` | one tension crack polyline |
| `SS_SURFACE` | one user slip surface |
| `SS_SUPPORT` | support lines (export only) |

LINE, LWPOLYLINE, POLYLINE, ARC and SPLINE are read; curves are converted to straight
segments with a 1 cm tolerance. Drawing units are converted to metres (unitless drawings are
taken as metres with a warning); geometry outside z = 0 is rejected and skipped entities are
listed. DXF carries geometry only — use `.slp.json` for materials, loads, supports and
results.

### Python scripting

*Tools → Python scripting* opens an editor where a script can modify the `project` object
(`external`, `material_boundaries`, `assignments`, `water_table`, `tension_crack`,
`materials`, `support_types`, `supports`, `support_patterns`, `facing_types`, `facings`,
`loads`, `seismic`, `methods`, `surfaces`, `annotations`, …). `MaterialSpec`,
`SupportType`, `FacingType`, `Project` and `empty_project` are available. The script runs on
a copy of the project; if validation succeeds, all changes become a single undoable step,
otherwise the open project is left unchanged. Scripts run with your local Python
permissions — run trusted code only.

A complete example that builds a model with geometry, loads, supports, facings and materials
is [`examples/scripted_slope.py`](examples/scripted_slope.py).

---

## Bundled examples

Available under *File → Examples* and from the command line with `--example "<name>"`
(`python main.py --list-examples` prints the names). The same models are in the
[`examples`](examples) folder as project files.

| Example (`--example`) | File | Shows |
|---|---|---|
| Simple slope (10 m, 2H:1V) | `simple_slope.slp.json` | homogeneous slope |
| ACADS EX1(a) | `acads_1a.slp.json` | ACADS verification problem (homogeneous slope) |
| ACADS EX1(b) | `acads_1b.slp.json` | ACADS verification problem (three layers, weak lens; layer starts at the toe) |
| ACADS EX1(c) | `acads_1c.slp.json` | homogeneous slope with a water-filled tension crack (Craig depth 2.685 m); Spencer ref 1.592 |
| ACADS EX1(d) | `acads_1d.slp.json` | the EX1(b) three-layer slope with kh = 0.15; Spencer ref 0.991 |
| ACADS 2(a) — Talbingo critical upstream search | `acads_2a.slp.json` | upstream-face critical-circle search; infinite-slope reference FoS ~1.951 |
| ACADS 2(b) — Talbingo fixed circle | `acads_2b.slp.json` | four-material dry embankment; exact circle (100.3, 291, 278.8); Bishop/Spencer/GLE/Janbu |
| ACADS 3(a) — weak seam + water table | `acads_3a.slp.json` | two materials, 0.5 m weak seam, water table at its base; non-circular Spencer/GLE search |
| ACADS 3(b) — weak seam specified path | `acads_3b.slp.json` | exact four-point noncircular path for a fixed-surface solver control; no critical search |
| ACADS EX4 | `acads_4.slp.json` | weak seam, inclined piezometric surface and two surcharges; Spencer ref 0.761 (block search) |
| ACADS EX5 | `acads_5.slp.json` | excavated 1:2 slope, water-table approximation of the published flow net; Spencer ~1.486 vs 1.500 |
| Arai & Tagyo — layered (circular) | `arai_tagyo_layered_circular.slp.json` | dry three-layer VP15; critical circular Bishop/Janbu/Spencer searches |
| Arai & Tagyo — layered (noncircular) | `arai_tagyo_layered_noncircular.slp.json` | same VP15 cross-section; non-circular Janbu/Spencer polyline searches |
| Borges & Cardoso — geosynthetic embankment #2 | `borges_cardoso_case2.slp.json` | dry 5 m embankment, four clays including depth-variable su, unanchored 200 kN/m geosynthetic |
| Layered slope + water table | `layered_water_table.slp.json` | fill, soft clay and weathered rock (Hoek-Brown) with a water table |
| Anchored cut + surcharge | `anchored_cut.slp.json` | two rows of grouted tiebacks, distributed and line loads |
| Slope with tension crack | `tension_crack.slp.json` | water-filled tension crack in stiff clay |
| Soil nail + shotcrete | `soil_nail_shotcrete.slp.json` | soil-nail pattern, shotcrete facing, notes |
| Undrained clay | `undrained_clay.slp.json` | total-stress (su) analysis |
| Power-law envelope | `power_law.slp.json` | non-linear strength |
| Seismic kh=0.15 | `seismic.slp.json` | pseudo-static seismic loading |

---

## Verification

A reproducible 29-slice **GeoStudio / Seequent hand-calculation reference**
now checks the Ordinary and Simplified Bishop equilibrium equations and the
existing LE solver independently. In 2026.1.4, Ordinary's pore-pressure
projection for circular moment equilibrium was aligned with the published
`u L cos² α` formulation (non-circular force equilibrium retains `u L`),
and the Bishop pore-water normal-force decomposition was added as a checked
solver relation. See
[GeoStudio Hand Calculations Verification](docs/GEOSTUDIO_HANDCALCS_VERIFICATION.md).

Additional official **SLOPE/W Tutorial** and **Limit Equilibrium Formulation**
examples are now covered by exact published tutorial geometry/material/pore
inputs and solver-level analytical/method tests. Vendor critical-search FS
numbers are labelled **reference-only** until the original solved
circle/search settings are available; no false cross-program equality is
claimed. See
[Additional GeoStudio Verification](docs/GEOSTUDIO_ADDITIONAL_VERIFICATION.md).

Run `python -m pytest tests/test_geostudio_handcalcs.py tests/test_geostudio_slope_examples.py -q`.

**Reference discrepancies:** The [verification discrepancy audit](docs/VERIFICATION_DISCREPANCY_AUDIT.md)
separates Talbingo 2(a) versus 2(b) and provides a read-only diagnostic
for ACADS 3(a) and Borges–Cardoso Case 2. Do not accept very low optimized
FoS without checking the actual surface and support mobilization.

The [ACADS 2(b) Talbingo Dam verification](docs/ACADS_2B_VERIFICATION.md)
adds an exact fixed-circle solver case, without an optimizer search, to check
four methods on the same published surface. The circle is editable under
Surface Options → User-defined → Fixed circle.

The [Borges–Cardoso Case 2 geosynthetic benchmark](docs/BORGES_CARDOSO_CASE2_VERIFICATION.md)
adds a 5-layer reinforced embankment model and a new elevation-dependent
undrained total-stress material (UDG). Published FoS are verification
references, not hardcoded results; global critical-circle matching remains
pending independent analysis.

The [Arai & Tagyo VP15 layered-slope verification note](docs/ARAI_TAGYO_LAYERED_VERIFICATION.md)
provides the circular and non-circular models, material region checks, and
published vendor FoS values. The benchmark global-search match remains
unverified until separately calculated and reviewed.

The [ACADS 3(a) verification note](docs/ACADS_3A_VERIFICATION.md) gives the
exact groundwater/weak-seam geometry and published Spencer/GLE references.
The regression tests check material regions, pore pressures, and a fixed
non-circular diagnostic path; no match of optimized FS is claimed until a
full critical search has been checked.


The test suite checks the engine against reference solutions, among them:

- **ACADS EX1(a):** Bishop 0.985, Spencer 0.984, GLE 0.984 (Slide2: 0.987 / 0.986 / 0.986).
- **Planar block:** every force-equilibrium method reproduces the closed-form rigid-block
  solution to 10⁻⁶, with seismic loads, external loads and active and passive anchors
  (a quadratic in F).
- **Hoek & Bray planar sliding with a vertical tension crack** (dry, half full, full): seven
  methods to 10⁻⁶.
- Bishop–GLE moment consistency with loads, passive anchors and crack water; support
  capacity formulas; mirror symmetry; an independent Bishop reference; the infinite slope
  limit; weight = area × γ.
- Tangent consistency of every non-linear strength model, the Barton-Bandis and CNI
  formulas, SHANSEP with the effective vertical stress, and the effect of micro-piles and
  geosynthetics on the FS.

---

## Keyboard and mouse reference

| Key / action | Function |
|---|---|
| F5 / F6 | compute / open Interpret |
| F2, middle double-click | zoom all |
| Wheel / middle drag | zoom at cursor / pan |
| F3 / F7 / F8 / F9 | OSNAP / GRID / ORTHO / SNAP |
| F10 | Information Viewer (Interpret) |
| F11 | full screen on / off |
| Ctrl+Z / Ctrl+Y | undo / redo |
| Ctrl+P | PDF report |
| Enter, `c`, Backspace, Esc | finish, close, undo last point, cancel (drawing) |
| Double-click | coordinate table or properties of the picked object |
| Delete | delete the selection |

---

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -p no:cacheprovider --durations=15    # Qt tests run headless
python -m ruff check .
python -m mypy                                         # computation core
```

The full suite takes a few minutes because of the non-circular searches and the PDF and GUI
tests. GitHub Actions runs the lint and type checks and the tests on Windows and Ubuntu
(Python 3.10, 3.13, 3.14) and in Arch Linux, Fedora and openSUSE Tumbleweed containers.

---

## Project layout

```
main.py              start-up script (IDE / command line)
pyproject.toml       lint, type-check and test configuration only
requirements*.txt    runtime and development requirements
slipsurface/
  geometry/          slope geometry, slip surfaces (circle, polyline, B-spline), regions from boundaries
  materials/         strength models and the model catalogue
  lem/               slicing, Bishop / Fellenius, Spencer, GLE, Janbu, Corps, Lowe-Karafiath
  optimizer/         critical surface search (differential evolution + Nelder-Mead)
  loads.py           external loads, support forces, facings, bolt placement
  project.py         project model and JSON file format
  analysis.py        multi-method runner and text report
  exchange.py        DXF import / export
  scripting.py       Python scripting
  textcat.py         translation catalogue with templates
  report/            PDF report (ReportLab) and fonts (Source Sans 3, SIL OFL)
  ui/                Modeler, Interpret, CAD canvas and tools, dialogs, translations
examples/            example projects and the scripting example
tests/               test suite
```

---

## Roadmap

- Probabilistic analysis (Monte Carlo)
- Sarma method
- Back analysis

---

## License

Copyright © 2026 Hasan Deniz Altuntaş.

SlipSurfaceIQ LE is free software: you can redistribute it and/or modify it under the terms
of the [GNU Affero General Public License](LICENSE) as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version. If you
modify the program and make it available to users over a network (for example as a server
or web service), the AGPL requires you to offer them the corresponding source code.

The program is distributed in the hope that it will be useful, but **without any warranty**;
without even the implied warranty of merchantability or fitness for a particular purpose.

Third-party components and their licenses are listed under *Help → About*: Qt / PySide6
(LGPL-3.0), NumPy, SciPy and Shapely (BSD), ReportLab (BSD), ezdxf and QtAwesome (MIT),
Material Design Icons (Apache-2.0), Source Sans 3 (SIL Open Font License 1.1).
