# LLM Decision Snapshot Handoff

Date: 2026-07-02

## Goal

Match details remain dynamic, while the LLM betting decision is persisted as an auditable snapshot. Issue Board recommendations should use the active snapshot when present. New data can create a draft replacement, but it cannot silently overwrite the active decision.

## Data Model

SQLite DB: `data/derived/500_bjdc/500_bjdc.sqlite`

Table: `llm_decision_snapshots`

Key fields:

- `snapshot_id`
- `issue`, `match_idx`, `match_id`
- `status`: `active`, `draft_replacement`, `superseded`
- `generated_at`, `checked_at`, `superseded_at`
- `input_hash`, `last_checked_input_hash`, `decision_fingerprint`
- `recommendation`, `primary_pick`, `protect_picks_json`, `selection_codes_json`, `stop_flag`
- `decision_chain_json`, `support_json`, `risks_json`, `explanation`
- `model_probabilities_json`, `market_probabilities_json`, `q_values_json`, `sp_snapshot_json`, `source_timestamps_json`
- `input_payload_json`, `decision_payload_json`
- `prompt_version`, `model_version`

The `input_payload_json` deliberately excludes score, halftime score, result code, and winning SP. Those belong to dynamic match details or post-match review, not to the pre-match decision basis.

## API

- `POST /api/issues/:issue/decision-snapshots`
  - Materializes snapshots for all matches in an issue.
  - If no active exists, creates `active`.
  - If active exists and the decision is unchanged, updates `checked_at`.
  - If the decision changes, creates `draft_replacement`.

- `POST /api/matches/:match_id/decision-snapshot`
  - Same behavior for one match.

- `POST /api/matches/:match_id/decision-snapshot/confirm`
  - Promotes draft replacement to active.
  - Marks previous active as superseded.

- `GET /api/issues/:issue/dashboard`
  - Match rows include `decision_snapshot_*` fields.
  - LLM selection fields are overlaid from active snapshot when available.

- `GET /api/matches/:match_id`
  - Returns dynamic match facts plus:
    - `decision_snapshot`
    - `draft_decision_snapshot`
    - `dynamic_decision`

## Frontend

Issue Board:

- The betting cell shows a small decision snapshot timestamp.
- If a draft replacement exists, it shows `有新版待确认`.

Match Detail:

- LLM Decision panel shows active snapshot status, decision time, checked time, and model version.
- Draft replacement is displayed as a warning banner but does not replace active decision.

## Current State

Generated active snapshots for current issue `26071`: 16 matches.

Repeated materialization returns `checked_active_unchanged` for all 16 matches.

## Validation

- `python3 -m py_compile src/decision_api/app.py scripts/review_settled_matches.py`
- `npm test -- --run`
- `npm run build`
- HTTP smoke:
  - `GET /healthz`
  - `POST /api/issues/current/decision-snapshots`
  - `GET /api/issues/current/dashboard`
  - `GET /api/matches/26071_008`
  - temp-DB smoke for `POST /api/matches/:match_id/decision-snapshot/confirm`

