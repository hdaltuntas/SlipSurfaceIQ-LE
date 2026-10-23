---
title: "SlipSurfaceIQ LE: open-source two-dimensional limit equilibrium slope stability analysis with a desktop CAD interface"
tags:
  - Python
  - geotechnical engineering
  - slope stability
  - limit equilibrium method
  - method of slices
  - rock slopes
authors:
  - name: Hasan Deniz Altuntaş
    # TODO: add your ORCID iD, e.g. orcid: 0000-0000-0000-0000
    affiliation: 1
affiliations:
  - name: General Directorate of Highways (KGM), 13th Regional Directorate, Research and Development Chief Engineering, Antalya, Türkiye
    index: 1
date: 22 October 2026
bibliography: paper.bib
---

<!--
DRAFT. Do not submit before the repository has more than six months of public
development history (first public commit: 19 October 2026). Sections marked TODO
need evidence that does not exist yet. Target length: 750–1750 words.
Build a PDF locally or with the "JOSS paper draft" GitHub Action.
-->

# Summary

Engineers check whether a slope, cut or embankment is stable by computing a factor of
safety: the ratio between the shear strength available along a potential slip surface and
the shear stress needed for equilibrium. The limit equilibrium method (LEM) does this by
dividing the sliding mass into vertical slices and solving the equilibrium equations of
the slices, and it remains the standard tool for slope design in practice
[@Duncan2014]. SlipSurfaceIQ LE is an open-source Python program for two-dimensional LEM
analysis of soil and rock slopes. The user draws the cross-section in a CAD-like desktop
interface, assigns materials, groundwater, loads and reinforcement, and the program
searches for the slip surface with the lowest factor of safety. Results are shown as
safety-factor contour maps, slice data and force diagrams, and are documented in a PDF
report. The same calculation engine can be used without the interface from Python scripts.
The interface and reports are available in English and Turkish.

# Statement of need

Slope stability calculations are carried out daily in highway, railway, mining and dam
engineering, and they are taught in every geotechnical engineering curriculum. The tools
most used for this work are commercial programs whose source code and implementation
details are not available. This makes it hard to see exactly which assumptions a reported
factor of safety rests on, to reproduce published analyses, to run large parametric or
probabilistic studies outside the vendor's interface, or to give students and engineers in
organisations without licences access to the same capabilities.

SlipSurfaceIQ LE targets three groups. **Researchers** need a transparent engine whose
equations they can inspect and modify, which they can call from Python for parametric
studies and data generation, and whose results are verified against independent
references. **Educators and students** need a free program that implements the full
family of classical methods so that differences between them can be explored. **Practising
engineers** need a familiar modeller–interpreter workflow, the material and
reinforcement models used in practice, and reports that document the input and results.
TODO: one sentence on the setting the program was developed for (e.g. slope assessments
in highway engineering in Türkiye), which also explains the bilingual interface.

# State of the field

Widely used commercial LEM programs include Rocscience Slide2 [@Slide2] and GeoStudio
SLOPE/W [@SlopeW]. They are mature and extensively verified but closed source and
licence-bound. Among open-source projects, pyCSS [@Montoya2016] implements the Fellenius
and Bishop methods for circular surfaces, and pySlope [@pySlope] provides Bishop's method
for layered slopes with water and surface loads. XSLOPE [@xslope] is a recent Python
package with seven methods of slices, finite element seepage and strength-reduction
analysis, and a companion desktop interface.

SlipSurfaceIQ LE was built rather than contributed to an existing package because its
target problems required capabilities that would have meant re-architecting those
projects: strength models for rock masses and discontinuities (generalised Hoek-Brown
[@Hoek2002], Barton-Bandis [@Barton1990], power-law and CNI envelopes) used through
instantaneous strength parameters in every method; SHANSEP undrained strength
[@Ladd1974]; reinforcement with capacity models for anchors, grouted tiebacks, soil nails,
geosynthetics, micro-piles and shotcrete facings, applied actively or passively; tension
cracks with water thrust; and a CAD modeller with DXF exchange and engineering reports.
TODO: once comparisons have been run, summarise here how results agree with XSLOPE on the
shared benchmark problems and state the scope that XSLOPE covers and SlipSurfaceIQ LE does
not (finite element seepage and strength reduction).

# Software design

The program is split into a calculation core and a Qt (PySide6) user interface. The core
(`geometry`, `materials`, `lem`, `optimizer`, `loads`, `project`) depends only on NumPy
[@Harris2020], SciPy [@Virtanen2020] and Shapely [@Shapely], never imports the interface,
and is type-checked; this keeps it usable from scripts and testable without a display.
A project is a plain JSON file, so models can be generated, version-controlled and
analysed in batch.

**Slicing.** Slice boundaries combine a user-chosen number of equal-width slices with
extra boundaries at every vertex of the ground surface, water table, material boundaries,
loads and polyline slip surfaces, so the top of every slice is straight and slice weights
are integrated exactly through all material regions. This costs extra slices but removes
discretisation error from the weight term, which is what allows the closed-form checks
below to pass to round-off.

**Methods of slices.** Bishop's simplified method [@Bishop1955], the Ordinary method,
Janbu's simplified and corrected methods [@Janbu1973], the Corps of Engineers methods,
Lowe-Karafiath, Spencer [@Spencer1967] and Morgenstern-Price/GLE
[@Morgenstern1965; @Fredlund1981] share one slice representation, one strength interface
and one treatment of pore pressure, seismic forces, external loads, crack water and
support forces. Non-linear strength envelopes are handled by iterating on the effective
normal stress on each slice base and using the tangent cohesion and friction angle.
Solutions are screened for admissibility (m_α < 0.2 [@Whitman1967], tension at the base,
excessive interslice forces) because otherwise the search exploits non-physical solutions
with very low factors of safety.

**Critical surface search.** Circular surfaces are parametrised by their entry and exit
points on the ground and the half central angle, and non-circular surfaces by their end
points and normalised depths of interior control points of a polyline or B-spline. With
this parametrisation every candidate intersects the ground at its end points and stays
inside the model, so the search space is a simple box. A global differential evolution
search [@Storn1997] is followed by a Nelder-Mead [@Nelder1965] refinement; for convex
non-circular surfaces the control polygon is projected onto its lower convex hull, which
keeps the B-spline convex.

**Verification.** In addition to more than 170 unit and regression tests, a verification
suite compares the program with independent references and runs in continuous
integration on every change. All force-equilibrium methods reproduce the closed-form
rigid-block and Hoek & Bray plane-failure solutions with a dry, half-full and full tension
crack [@Hoek1981] to a relative error of 10⁻⁶, and for the ACADS benchmark EX1(a)
[@Giam1989] the program gives 0.985 (Bishop), 0.984 (Spencer) and 0.984 (GLE) against
a referee value of 1.00. TODO: extend with the remaining ACADS problems
[@Giam1989], Fredlund & Krahn [@Fredlund1977] and Arai & Tagyo [@Arai1985] and summarise
the agreement here.

# Research impact statement

TODO — this section must report realised or credible near-term impact, not intentions.
Candidate evidence to collect before submission:

- publications, theses or preprints that used SlipSurfaceIQ LE (including the author's own
  studies) and the verification preprint, with citations;
- documented use in teaching (courses, institutions, number of students) and in
  engineering practice (e.g. use at KGM);
- issues, pull requests or verification cases contributed by people other than the
  author, and download statistics of the installers and PyPI package;
- the open verification suite and example models as reproducible material.

# AI usage disclosure

TODO — the author must review and complete this statement; it must be accurate and
complete. Draft based on the repository history:

Generative AI coding assistants were used in the development of this software:
Claude Code with Anthropic Claude models (versions: TODO) and Mistral's Vibe coding agent
(TODO: confirm). They were used to write and refactor code, tests and documentation under
the author's direction (TODO: describe the scope more precisely). The author defined the
scope, the engineering formulation and the software architecture, reviewed the generated
code, and verified the correctness of the results against closed-form solutions,
published benchmarks and commercial software as described above. TODO: state whether AI
was used in writing this paper.

# Acknowledgements

TODO: acknowledge contributors, testers and funding, or state that the work received no
specific funding.

# References
