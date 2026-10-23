# Contributing to SlipSurfaceIQ LE

Thank you for considering a contribution. SlipSurfaceIQ LE is an engineering program:
a wrong factor of safety is worse than a missing feature, so the most valuable
contributions are often **independent checks of the results**. You do not need to
write code to help.

Issues and pull requests can be written in **English or Turkish**
(*Türkçe issue ve PR açabilirsiniz*).

## Ways to contribute

| You are… | You can… |
|---|---|
| a practising engineer | report a case where the FS differs from another program or a hand calculation ([verification discrepancy](https://github.com/hdaltuntas/SlipSurfaceIQ-LE/issues/new?template=verification_discrepancy.yml)) |
| a researcher | add a published benchmark to the [verification suite](verification/README.md), or tell us about a paper or thesis that used the program |
| a lecturer or student | report what was confusing in a lab or homework, suggest teaching examples |
| a translator | improve the English and Turkish texts (`slipsurface/ui/translations_en.py`, `slipsurface/report/translations_en.py`) |
| a developer | pick an issue labelled [`good first issue`](https://github.com/hdaltuntas/SlipSurfaceIQ-LE/labels/good%20first%20issue) or [`help wanted`](https://github.com/hdaltuntas/SlipSurfaceIQ-LE/labels/help%20wanted) |

Questions and ideas that are not bugs belong in
[GitHub Discussions](https://github.com/hdaltuntas/SlipSurfaceIQ-LE/discussions).

## Reporting a bug or a suspicious result

Please attach the project file (`*.slp.json`) whenever you can. It contains everything
needed to reproduce the analysis. If the project is confidential, a reduced model that
shows the same behaviour is equally useful. Include the version (*Help → About* or
`python -c "import slipsurface; print(slipsurface.__version__)"`) and your operating
system.

For FS discrepancies, say which program or reference you compared with, which method
and surface type you used, and both FS values.

## Development set-up

```bash
git clone https://github.com/hdaltuntas/SlipSurfaceIQ-LE.git
cd SlipSurfaceIQ-LE
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

Before opening a pull request, run the same checks as CI:

```bash
python -m ruff check .
python -m ruff format --check .
python -m mypy                                    # computation core
python -m pytest -p no:cacheprovider              # Qt tests run headless
python verification/run.py                        # benchmark suite
```

## Pull requests

1. Open an issue first for anything larger than a small fix, so the approach can be
   agreed before you invest time.
2. Create a branch from `main` and keep each pull request focused on one change.
3. **Every change to the calculation core needs a test.** Prefer tests against an
   independent reference (closed-form solution, published benchmark, hand calculation)
   over tests that only freeze the current output.
4. If a change alters factors of safety, say so in the pull request and explain why
   the new value is the correct one.
5. Update `README.md`, the documentation and `RELEASE_NOTES.md` when behaviour visible
   to users changes. User-facing text must be added in both Turkish and English.
6. CI must pass on all platforms.

### Code conventions

- Formatting and linting: `ruff` (line length 100). The computation core
  (`lem`, `geometry`, `materials`, `optimizer`, `analysis.py`, `loads.py`, `project.py`)
  is type-checked with `mypy`.
- Units are SI throughout: m, kN, kPa, kN/m³, degrees.
- The computation core must not import Qt; GUI code lives in `slipsurface/ui/`.
- Short domain names (`c`, `phi`, `l` for base length, `W`, `N`) are fine when they
  match the usual notation of the method of slices.

### AI-assisted contributions

Tools such as code assistants may be used, but you are responsible for every line you
submit: you must understand it, have checked it, and be able to explain it in review.
Please mention significant AI assistance in the pull request description. This keeps
the project consistent with the disclosure policies of journals such as JOSS.

## Licence of contributions

SlipSurfaceIQ LE is licensed under the
[GNU Affero General Public License v3.0 or later](LICENSE). By submitting a contribution
you agree that it is licensed under the same terms (inbound = outbound) and that you have
the right to submit it.

## Code of conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
