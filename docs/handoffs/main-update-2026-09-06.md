# Main workspace update — 2026-09-06

- Local `main` fast-forwarded from `626e8449231a47e047a7f3230f4758ac3f6c2cf3` to `4c7229a51951353377bdd313d3bc51f8cf73e6ef`, matching `origin/main` at verification.
- Includes merged PR #414 (#413) and PR #416 (#408).
- Complete original tracked/untracked workspace saved in stash `732d9be9d035354b6279e1ccc422c1725b3d6c9a` (`main-update-preserve-workspace-2026-09-06`). Retain this stash until owners reconcile remaining snapshots. Ignored data and local runtime directories stayed in place.
- Restored 97 paths; 84 original changes/files were already represented in main. Restored additional snapshot tests and combined the QMD render list, preserving local QMD 04/05 and upstream pipeline QMD.
- Local uncommitted service, backfill, collection, settlement, and audit work remains uncommitted. This update does not accept or publish that work.
- The following 10 formerly untracked paths differ from the merged #408 versions. Kept main's versions in the workspace; original local bytes remain available via `git show 732d9be9d035354b6279e1ccc422c1725b3d6c9a^3:<path>`. Do not apply the entire stash over current main.

- `.github/workflows/fundamentals-census.yml`
- `DESCRIPTION`
- `config/fundamentals_census_runtime.json`
- `r/fundamentals_census.R`
- `scripts/materialize_fundamentals_census_fixture.py`
- `src/fundamentals_census.py`
- `src/nowscore_settlement.py`
- `tests/test_fundamentals_census.py`
- `tests/test_nowscore_settlement.py`
- `tests/testthat/test-fundamentals-census.R`

## Verification

- `git rev-list --left-right --count HEAD...origin/main`: `0 0`.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest tests/titan_clean tests/test_fundamentals_census.py tests/test_fundamentals_pipeline.py tests/test_nowscore_settlement.py -q`: 164 passed in 68.72 seconds.
- `R_LIBS_USER="$PWD/r_lib" BEIJING_LOT_VENV_PYTHON="$PWD/.venv/bin/python" TZ=UTC Rscript --vanilla tests/testthat.R`: no failures; two fundamentals pipeline integration tests skipped because their pre-materialized integration bundle was unavailable. These skipped checks are not acceptance evidence.
- This was a branch synchronization with WIP preservation, not a new implementation delivery. No new Codex review or QMD render was run; prior merged delivery evidence remains in the existing delivery QMDs.
