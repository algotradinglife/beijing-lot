# Market pipeline handoff — 2026-09-19

## Operational state

Owner requested ALL background collection paused. Collection services and the market progress timer have been stopped and disabled. The half-hour cleaning cron entry is commented out because it may initiate supplementary requests. Notification delivery alone remains enabled. Do not install/start units or resume collection without a new owner instruction.

Local pause receipt: `/home/drwho1985/.local/state/beijing-lot-collection-pause/current.json`. Runtime unit/cron changes are machine state, not recreated automatically by this Git checkout.

## Persistent data and entry points

Data root: `/run/media/drwho1985/Sandisk/data/beijing-lot`. Database: `markets/releases/market-history-v1.sqlite` below that root. Data and independent backups are not transferred through Git; a new host needs the mounted persistent data and backups separately.

Read `config/persistent_data_layout.json`, `skills/beijing-lot-data-storage/SKILL.md`, and `docs/operations/market_sqlite_migration.md`. Validate paths with `scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json` before writes. Resolve inputs through the registry, not directory modification times.

Collection: `scripts/collect_market_history.py`, `scripts/collect_market_queue.py`, `scripts/supervise_market_history.py`, `scripts/supply_market_rosters.py`; source modules in `src/market_*` and imported `src/fundamentals_*`. Cleaning: `scripts/poll_market_cleaning.sh`; notifications: `scripts/poll_market_cleaning_notifications.sh`.

SQLite workflow: prepare/migrate/freeze inventories/stage publication/accept/activate/retain audit/retire via `scripts/*market_sqlite*.py`. Reports: `quarto/market_sqlite_migration.qmd`, `quarto/market_sqlite_retirement.qmd`; reusable R functions in `r/market_sqlite_report.R` and `r/market_retirement_report.R`.

## Migration checkpoints

- `batch-0001-v7`: 101121–110303, 50 issues, accepted and raw retirement verified.
- `batch-0002-v3`: 110304–110513, 50 issues, accepted and raw retirement verified.
- Combined: 12,716 retired files, 13,494,124,544 allocated bytes released (not net disk-space change).
- `batch-0003-v1`: 110514–110805, 50 issues; SQLite content/publication accepted. Raw retirement NOT approved. All 5,903 candidate files retained. Final Codex review found three P2 gate defects; see adjacent review document. Fix gates, regenerate affected evidence and obtain a passing review before any deletion.
- `batch-0004-v1`: 110806–111009, plan only; not imported.

Evidence lives under `audits/market-sqlite/<batch>/` at the persistent root. Third-batch publication acceptance is under `publication-revision-2/`; retirement inputs include `final-retirement-bundle.json`, `raw-retirement-plan.json` and reference snapshots. The active epoch is `markets/manifests/market-sqlite-batch-0003-v1-epoch`; installed collector remains disabled. Retain shared archives and anomaly evidence.

Most recent cleaning acceptance: 150203–151206, 50 issues, `ACCEPTED_DIAGNOSTIC_BATCH`; this is distinct from SQLite retirement acceptance and does not imply complete quote coverage.

## Resume work safely

1. Verify mount, registry, pause receipt, service/cron state and current audit artifacts.
2. Fix all three final-review findings: repeated systemd commands; deployed package initializer identity; epoch plan/receipt/carried-attempt bindings.
3. Run regression tests, refresh review/evidence, then use the gated retirement entry point. Never infer deletion approval from content acceptance.
4. Continue migrations in 50-issue batches. Collection remains paused until separately requested.

GitHub API returned HTTP 401 during handoff; no Issue/Project lifecycle updates were made. Git SSH access is available. This handoff preserves work in progress, not a claim that final retirement review passed. Unrelated research changes in the original workspace are outside this transfer.

## Handoff validation

Scoped SQLite/retirement/capture-recovery/epoch/roster/notification pytest run: 142 passed. This does not resolve the three independent review findings. Historical QMDs were not rerendered for this source-only handoff. Existing trailing whitespace in two source/test lines is retained to avoid changing implementation identities bound to migration receipts.

R report tests: `testthat::test_file("tests/testthat/test-market-sqlite-report.R")` and `testthat::test_file("tests/testthat/test-market-cleaning-quotes.R")`: 13 assertions passed, no failures/skips. Python syntax parsing: 97 staged Python files passed.

Expanded dependency test run (selected 56 Python test modules): 540 passed, 1 failed in 191.97 seconds. Failure: `tests/test_fundamentals_adjudications.py::test_saved_owner_adjudications_preserve_raw_and_chronology`, assertion that default `identity_source` is absent for slots 6/19. This remains an unresolved dependency behavior/test-contract mismatch; no fix was attempted during handoff. The separate 142-test market suite passed. Do not interpret this branch snapshot as merge-ready acceptance.
