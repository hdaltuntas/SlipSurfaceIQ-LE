# Verification suite

This folder checks SlipSurfaceIQ LE against **independent references**: closed-form
solutions, published benchmark problems and results of established programs. The current
results are in [`docs/verification.md`](../docs/verification.md); the suite runs in CI on
every push.

The unit tests in `tests/` protect the code against regressions. The verification suite
answers a different question for users, reviewers and researchers: *how close are the
factors of safety to accepted reference values, and for which kinds of problem has that
been shown?*

## Running

```bash
python verification/run.py            # all active cases (about 20 s)
python verification/run.py --fast     # closed-form cases only (< 1 s)
python verification/run.py --case acads-1a
python verification/run.py --write    # also regenerate docs/verification.md
```

The script exits with status 1 if any check falls outside its tolerance.

## Reference hierarchy

Cases are labelled by the strength of their reference, strongest first:

1. **closed form** — exact equilibrium solutions (rigid planar block, Hoek & Bray plane
   failure with a tension crack, infinite slope). Tolerances are tight (relative 10⁻⁶)
   because the method of slices must reproduce them to round-off.
2. **published benchmark** — problems with referee solutions in the literature, such as
   the ACADS set (Giam & Donald 1989), Fredlund & Krahn (1977) or Arai & Tagyo (1985).
3. **commercial software** — the same model analysed in Slide2, SLOPE/W or similar,
   used where no published solution exists (e.g. reinforcement, Hoek-Brown rock). State
   the program version.

Tolerances for searched (critical) surfaces are looser than for fixed surfaces because the
search and the slicing differ between programs; a difference of about 1 % in FS is normal
for a circular search.

## Adding a case

1. Build the model in the program and save it under `verification/models/` (or reuse a
   file from `examples/`).
2. Add an entry to [`cases.json`](cases.json):

   ```json
   {
     "id": "acads-1b",
     "title": "ACADS EX1(b): three-layer slope",
     "kind": "project",
     "project": "verification/models/acads_1b.slp.json",
     "reference_type": "published benchmark",
     "source": "Giam & Donald (1989), ACADS example EX1(b)",
     "benchmark_fs": 1.39,
     "reference": {"bishop": 1.405, "spencer": 1.375},
     "reference_note": "Comparison values: <program and version>",
     "tolerance": {"abs": 0.02},
     "status": "active"
   }
   ```

   The numbers above are placeholders — always copy the reference values from the
   original source and cite it in `source`. `reference` maps method keys
   (`bishop`, `ordinary`, `janbu_simplified`, `janbu_corrected`, `corps1`, `corps2`,
   `lowe_karafiath`, `spencer`, `gle`) to reference factors of safety. The search
   settings (surface type, effort, seed, number of slices) are taken from the project
   file, so set them there.

   For a closed-form case use `"kind": "analytic"`, add a function to
   [`analytic.py`](analytic.py) returning `{method: (computed, reference)}` and refer to
   it with `"function"` and optional `"kwargs"`.

3. Run `python verification/run.py --case <id> --write` and include the regenerated
   `docs/verification.md` in your pull request.

Cases marked `"status": "planned"` are wanted but not yet built — they are a good place to
start contributing. If a case does not agree with its reference, please open a
[verification discrepancy](https://github.com/hdaltuntas/SlipSurfaceIQ-LE/issues/new?template=verification_discrepancy.yml)
issue rather than loosening the tolerance.
