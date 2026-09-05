# R / QMD repair and structure handoff — 2026-09-05

- Contract: [#413](https://github.com/algotradinglife/beijing-lot/issues/413), BJ Data Platform. Read native Issue Graph fields for current lifecycle; this document is execution evidence only.
- Owner explicitly authorized PI repair/organization and required migration documents to remain available across sessions.
- Initial 2026-09-05 work was uncommitted in the shared working tree. For the 2026-09-06 continuation and publication state, read the appended section below; unrelated changes remain owned by their tasks.

## Continuation entry points

- [Documentation index](../README.md).
- [Current R/QMD workflow](../operations/rstudio_quarto_data_workflow.md).
- [Architecture](../architecture.md) and [data contracts](../data/analysis_contracts.md).
- [Original Ubuntu migration handoff](ubuntu-migration-project-handoff.md).
- [Original Ubuntu migration acceptance](ubuntu-migration-acceptance-2026-08-27.md).
- Root `MIGRATION.md`, `HANDOFF.md`, `HANDOFF-318.md` remain unchanged.
- Content hashes verified all five migration/root handoff documents unchanged during this work.

## Repaired interfaces

- `fetch_raw(url, encoding, ...)` returns `list(payload, text)`; payload is original bytes. Invalid encoding stops, transient retries are bounded and rate-limited.
- Shared R parsers are in `r/mapping_engine.R`; QMD 03 calls `r/mapping_report.R` on saved input files.
- `run_issue_mapping()` requires explicit capture identity/time, project root, and Python interpreter. Saved `raw_500`/`raw_ns` permit offline replay.
- `src/titan_clean/historical_id_map.py::record_capture()` owns transactional mapping/rebuild. Repeated captures are idempotent; changed receipt inputs conflict; failed rebuild restores mapping and receipt rows.
- Nested SQLite savepoints replace ineffective context-manager transactions on an autocommit connection.
- Remapped void slots are isolated under the corresponding 500 slot.
- Python module calls use `r/python_bridge.R`; preserve the `.venv/bin/python` path instead of resolving its symlink to system Python.
- `r/snapshots.R` returns tibbles, typed UTC timestamps, and source receipts. Duplicate keys fail instead of taking the first row.
- Snapshot reads use SQLite read-only mode and fail on missing chronology; receipts identify historical proxies and prohibit prospective use.
- `.Rprofile` no longer provides a personal data path or changes PATH; copy settings from `config/analysis.env.example` and explicitly supply the data root.
- `DESCRIPTION` / `renv.lock` record the R environment; setup is `Rscript --vanilla r/bootstrap.R`.
- Rebuild/preflight commands now take explicit one-issue arguments. They no longer execute a hardcoded historical issue list.

## Moved paths

- `doc/cross_n_lambda_impact.md` → `docs/research/cross_n_lambda_impact.md`.
- `doc/vol_pct_signal_design.md` → `docs/research/vol_pct_signal_design.md`.
- Six documents under `docs/ops/` → the same filenames under `docs/operations/`.
- `docs/research/rstudio_quarto_data_workflow.md` → `docs/operations/rstudio_quarto_data_workflow.md`; rewritten for verified current behavior.
- README, dashboard README, and affected document references now point to the new locations.
- `research/`, `notebooks/`, migration records, and historical evidence bundles remain at existing paths. Further code relocation requires caller/evidence inventory in its own issue.

## Validation evidence

- Before repair, regression tests reproduced unused `encoding`/`transport` arguments and sparse-slot alignment failure.
- `R_LIBS_USER="$PWD/r_lib" TZ=UTC Rscript --vanilla tests/testthat.R`: all seven R test files passed without skips.
- `.venv/bin/python -m pytest tests/titan_clean -q`: 44 passed, including rollback, retries, void remapping, and chronology failures.
- `.venv/bin/python scripts/check_cutoff_governance.py`: PASS.
- `RENV_PATHS_ROOT=/tmp/beijing-413-renv RENV_CONFIG_CONSENT=TRUE R_LIBS_USER="$PWD/r_lib" TZ=UTC Rscript --vanilla r/bootstrap.R`: project library already synchronized with lockfile.
- Clean QMD 03 render passed with `--execute --no-cache`; three rendered tables verified for input hashes, row count, status, keys, and minute units.
- Local Quarto executable: `/usr/lib/rstudio-server/bin/quarto/bin/quarto`; put Quarto on PATH for portable documented commands.
- Rendered artifact: `quarto/_output/quarto/03_500_nowscore_datatable_demo.html` (generated, ignored).

## Limits and next-session handling

- No live website collection, production database rebuild, service restart, or learned-artifact rewrite was performed.
- External-data reports 00/01/02/04/05 were not rendered against production databases; offline fixtures exercise the repaired interfaces.
- `.github/workflows/analysis-contracts.yml` is configured locally; remote CI and branch-required-check enforcement have not run or been changed.
- `fundamentals-census.yml`, its new modules, and the #406 child graph belong to concurrent fundamentals work; do not overwrite them from this handoff.
- Review and commit the intended files with their existing prerequisites; do not blanket-stage the shared dirty tree.
- Before lifecycle changes, re-read #413 graph fields. Do not close the issue solely because these local checks passed.

## 2026-09-06 continuation

- Active delivery: [PR #414](https://github.com/algotradinglife/beijing-lot/pull/414), branch `codex/issue-413-r-qmd-delivery`.
- Work was isolated at `/tmp/beijing-413-delivery` from base `626e8449`; the original shared checkout and unrelated service/settlement/fundamentals changes remain intact.
- The isolated manifest includes QMD 00–03, 07–08 and the mapping/snapshot dependencies; QMD 04–06 and their unrelated modules/tests remain with their ongoing tasks.
- `scripts/scrape_500_bjdc.py` includes only the cancelled-row parser correction required by the mapping regression test. No service or collection configuration is included.
- Three R files and 41 Python tests pass in the isolated checkout; the earlier seven-file / 44-test counts describe the larger shared tree, not this PR.
- First complete `codex review --base main -c sandbox_mode='"read-only"'` found three P2 issues. Regression tests first reproduced all three, then passed after correcting year rollover, complete receipt binding, and all-void capture handling.
- Legacy automatic schema rewriting was removed from the delivered store. Existing databases are not silently migrated; restore an operator-selected compatible snapshot before use.
- Added strict ID/matrix validation without floating-point provider-ID conversions; documented Python verification dependencies in `requirements-analysis.txt`.
- Analysis CI uses a sparse checkout of declared inputs, avoiding the unrelated multi-gigabyte research bundles.
- Runtime restore, R/Python tests, and all three offline QMD renders passed remotely for `6c653748`; final reviewed revision and CI evidence are recorded in QMD 08 / PR #414 when acceptance completes.
- QMD 08 is the #413 delivery. Original migration/root handoff files retain their five recorded SHA-256 hashes.
- Second review found two further P2 issues: stale active mappings could coexist with isolation, and incomplete per-row identity evidence could pass parsing. Both now fail explicitly; regression tests prove rollback and successful explicit rebuild, including reverse isolation-to-active transitions.
- QMD 00–02 additionally executed and rendered against a temporary synthetic SQLite database. Set `XDG_CACHE_HOME` to an explicitly writable cache directory when the host's default Quarto cache is restricted.
