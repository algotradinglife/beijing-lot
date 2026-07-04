# Decision Dashboard Data Chain Hardening

Date: 2026-07-04

This handoff covers the live decision dashboard data chain after the SQLite/update/frontend robustness pass.

## What Changed

- SQLite connections now use `src.sqlite_runtime.connect_sqlite()` on the live path, with `timeout=30s`, `PRAGMA busy_timeout=30000`, `foreign_keys=ON`, and WAL for writers.
- 500.com and Jiebao/Nowscore upserts now prevent blank/partial scrape rows from erasing known settled or finished fields.
- Live SP selection now takes the latest complete SP triplet per match row, not the latest issue-wide fetch batch.
- Dashboard freshness is split by source via `source_freshness`; `last_snapshot_ts` now reflects issue-specific sources only.
- Frontend refreshes use a request sequence guard. A failed refresh keeps the last successful dashboard visible and shows an error banner; real mode still never falls back to mock.

## Data Chain

- 500 issue list and issue HTML: `scripts/scrape_500_bjdc.py`
  - tables: `issues`, `matches`, `fetch_log`
  - high-value fields protected on upsert: score, result, winning SP, visible SP, teams, kickoff metadata.
- 500 live SP XML: `scripts/scrape_500_bjdc.py --live-sp`
  - table: `live_sp_snapshots`
  - API reads latest complete triplet per `(issue, playid, row_idx)`.
- Jiebao/Nowscore score rows: `scripts/scrape_nowscore_bjdc.py`
  - table: `nowscore_bjdc_matches`
  - finished score/half/result are protected from blank or lower-confidence refreshes.
- Match details/intel:
  - `scripts/scrape_500_match_details.py`
  - `scripts/scrape_nowscore_match_details.py`
  - `scripts/collect_match_intel.py`
- Runtime orchestration:
  - `scripts/monitor_500_bjdc.py`
  - `scripts/live_score_refresh_loop.py`
  - `scripts/manage_decision_dashboard.py`

## API Smoke Paths

- `GET /healthz`
- `GET /api/issues/current/dashboard`
- `GET /api/matches/<match_id>`
- `GET /api/issues/<issue>/operations`
- `GET /api/issues/<issue>/signals`
- `GET /api/issues/<issue>/main-strategy`
- `GET /api/issues/<settled_issue>/settlement`

Repeatable local smoke:

```bash
export BEIDAN_LIVE_SQLITE=/path/to/populated/500_bjdc.sqlite
python3.14 scripts/smoke_decision_dashboard_data_chain.py --issue current
```

The smoke script validates that the SQLite file contains the required live
tables before creating the Flask app. This prevents an empty default SQLite
file from being silently created when the local data artifact is missing.

Full validation used in this pass:

```bash
python3.14 -m py_compile src/sqlite_runtime.py src/decision_api/app.py scripts/scrape_500_bjdc.py scripts/scrape_nowscore_bjdc.py scripts/monitor_500_bjdc.py scripts/live_score_refresh_loop.py scripts/scrape_500_match_details.py scripts/scrape_nowscore_match_details.py scripts/review_settled_matches.py scripts/smoke_decision_dashboard_data_chain.py tests/scripts/test_live_upsert_regression.py tests/decision_api/test_sqlite_runtime.py tests/decision_api/test_live_workflow.py
pytest -q tests/decision_api tests/scripts/test_live_upsert_regression.py
npm --prefix apps/decision-dashboard test -- --run
npm --prefix apps/decision-dashboard run build
```

## Frontend Boundary

- Real mode is the default. Mock data is only allowed when `VITE_DATA_MODE=mock`.
- API base URL is still resolved by the frontend adapter/runtime config; no silent fallback is introduced.
- On refresh failure, the page displays the last successful snapshot plus a visible error banner.
- The issue selector keeps the user-selected issue even if the new issue refresh fails.

## Reviewer Results

- `t_0136b46b`: PASS. SQLite helper covered decision API and live scraper/runtime scripts; no DB files introduced.
- `t_33ce2ce6`: PASS. Upsert guards prevent blank/low-confidence refreshes from clearing settled/finished fields; non-empty corrections still update.
- `t_28be3f87`: PASS. Per-match complete SP selection and source freshness passed reviewer probe; no future-SP contamination found in Q/prediction path.
- `t_1a1548d6`: PASS. Frontend keeps last good data, blocks stale request overwrite, and does not fall back to mock in real mode.

## Remaining Risks

- Historical research scripts still contain direct `sqlite3.connect()` calls; this pass intentionally covered the live dashboard path only.
- Upsert protection can preserve a wrong old value if both the old value and a later blank scrape are bad. Non-empty corrections still overwrite.
- The smoke script does not perform network scraping by default. Network refresh remains covered by monitor/workflow runs and should be tested separately when changing scraper parsing.
- Reviewer probe files may be left untracked by reviewer runs; do not commit them unless intentionally promoted into tests.
