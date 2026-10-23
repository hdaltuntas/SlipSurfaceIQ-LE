# JOSS submission checklist

Working list for submitting SlipSurfaceIQ LE to the
[Journal of Open Source Software](https://joss.theoj.org). Requirements are from the
[JOSS submission guide](https://joss.readthedocs.io/en/latest/submitting.html) and
[paper format](https://joss.readthedocs.io/en/latest/paper.html) (checked October 2026).

**Earliest submission: after 19 April 2027** — JOSS requires more than six months of
public development history, and the first public commit is dated 19 October 2026.

## Repository settings (maintainer, one-off)

- [ ] Connect the repository to [Zenodo](https://zenodo.org/account/settings/github/) and
      publish a GitHub release so the first DOI is minted (`.zenodo.json` supplies the
      metadata). Add the DOI badge to the README.
- [ ] Add the ORCID iD to `CITATION.cff` and `paper/paper.md`.
- [ ] Enable GitHub Discussions (Settings → Features).
- [ ] Add repository topics: `slope-stability`, `geotechnical-engineering`,
      `limit-equilibrium`, `python`, `pyside6`.
- [ ] Create labels `verification`, `good first issue`, `help wanted`.
- [ ] Turn the roadmap (Monte Carlo, Sarma, back analysis) and the planned verification
      cases into issues.
- [ ] Publish the package on PyPI (`slipsurface-le`).

## Before submission (next six months)

- [ ] Develop in the open: regular commits, work tracked in issues and pull requests,
      releases with notes.
- [ ] Complete the planned verification cases (ACADS EX1(b)–EX4, Fredlund & Krahn 1977,
      Arai & Tagyo 1985, Hoek-Brown and reinforced comparison models).
- [ ] Run the shared benchmarks in XSLOPE and record the comparison (State of the field).
- [ ] Documentation site with installation, tutorial, Python API reference and the
      verification results.
- [ ] Optional install without the GUI (`pip install slipsurface-le` for the engine,
      `[gui]` extra for PySide6) so researchers can script the engine.
- [ ] Collect research-impact evidence: preprint of the verification study (e.g.
      EarthArXiv), papers or theses using the program, teaching use, external issues/PRs.

## Paper

- [ ] Fill every `TODO` in `paper/paper.md`; keep 750–1750 words.
- [ ] Complete the AI usage disclosure accurately (tools, model versions, scope, how the
      output was reviewed and verified).
- [ ] Check that the draft PDF builds (GitHub Action *JOSS paper draft*).
- [ ] Declare related publications and any conflicts of interest in the submission form.

## At submission

- [ ] Tag a release and archive it on Zenodo; use that version and DOI.
- [ ] Submit at <https://joss.theoj.org/papers/new>.
- [ ] Respond to reviewers within two weeks; reviewer conversations must be written
      without AI assistance (translation excepted).
