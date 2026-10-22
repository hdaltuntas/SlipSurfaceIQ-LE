# Governance and support

## Who maintains the project

SlipSurfaceIQ LE is currently maintained by a single person,
[Hasan Deniz Altuntaş](https://github.com/hdaltuntas), who makes the final decisions on
scope, design and releases. Contributors who make sustained, substantial contributions
(code, verification cases, documentation or translations) will be invited to become
maintainers with merge rights; this file will then list them and describe how decisions
are shared.

## Scope

The project aims to be a transparent, verified and free tool for **two-dimensional limit
equilibrium** slope stability analysis, usable both through a desktop interface and as a
Python library, for practice, teaching and research. Finite element analysis, 3D analysis
and web services are outside the scope of this repository.

## How decisions are made

- Proposals are discussed openly in issues or Discussions before larger changes are made.
- Changes to the calculation core must be backed by tests against independent references
  (see [CONTRIBUTING.md](CONTRIBUTING.md)).
- Behaviour changes that alter factors of safety are always listed in
  [RELEASE_NOTES.md](RELEASE_NOTES.md).

## Releases

Versions follow the `YEAR.MINOR.PATCH` scheme (e.g. `2026.1.1`). Patch releases fix bugs;
minor releases add features. Each release is tagged on GitHub, ships with release notes
and native installers, and is archived on Zenodo with a DOI.

## Getting help

| Need | Where |
|---|---|
| How do I…? / ideas / show your model | [GitHub Discussions](https://github.com/hdaltuntas/SlipSurfaceIQ-LE/discussions) |
| Bug or wrong result | [Issues](https://github.com/hdaltuntas/SlipSurfaceIQ-LE/issues/new/choose) |
| Code of conduct reports | slipsurface@proton.me |

Support is provided on a best-effort basis by volunteers. The maintainer aims to
acknowledge new issues within **one week**; reports of incorrect factors of safety are
given priority. There is no warranty (see the engineering disclaimer in the
[README](README.md)); results must always be checked with engineering judgement.

## Security

Scripts run from *Tools → Python scripting* are ordinary Python code executed with the
user's permissions; only run scripts you trust. Please report security problems privately
to slipsurface@proton.me rather than in a public issue.
