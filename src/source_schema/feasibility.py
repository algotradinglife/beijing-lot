"""Source feasibility matrix (REQ-DS01) and migration-free replacement plan.

Deliverable 3: source feasibility matrix with acquisition cost/access/
licensing/coverage/clock grade and a concrete selected source per downstream
branch (#235 Beijing SP, #236 European odds, #237 power features, #238
materializer).

Deliverable 4: migration-free replacement plan — obsolete ambiguous schemas
are removed from the accepted interface rather than wrapped in compatibility
layers (AGENTS.md principle 1: no backward-compat tax).
"""
from __future__ import annotations

from . import contract

# ---------------------------------------------------------------------------
# Source feasibility matrix
# ---------------------------------------------------------------------------
# Grades: A = fully satisfies, B = partial with conditions, C = insufficient,
#         U = unusable
SOURCE_MATRIX: list[dict] = [
    {
        "source_id": "BJ_OFFICIAL_INSTANT_SP",
        "family": "F1_BJ_FIRST_PARTY",
        "provider": "Beijing Sports Lottery official interface (500.com mirrors)",
        "endpoint": "trade.500.com/bjdc/?expect={issue} + zx.500.com/zqdc/kaijiang.php",
        "acquisition_method": "prospective capture; raw payload + trusted fetch clock",
        "terms_status": "unofficial mirror; public access with rate limits; cookies for vol_pct",
        "cost": "free",
        "access": "A",
        "licensing": "C",  # unofficial mirror, ToS ambiguity
        "coverage": "A",   # full Beijing pool, native lines + instant SP
        "clock_grade": "A",  # TRUSTED_FETCH prospective; NATIVE when provider publishes
        "admissible_use": "STRICT_CAUSAL",
        "selected_for": "BJ_SP_TIMESERIES #235 (primary)",
        "note": "Prospective only; no historical backfill without native timestamp.",
    },
    {
        "source_id": "BEIDAN_LIVE_DB",
        "family": "F1_BJ_FIRST_PARTY",
        "provider": "internal live collector (src/live_collector)",
        "endpoint": "local sqlite (WAL)",
        "acquisition_method": "already captured; reconcile to raw capture hashes",
        "terms_status": "internal",
        "cost": "free",
        "access": "A",
        "licensing": "A",
        "coverage": "B",  # 2026-05 onward only
        "clock_grade": "A",  # ISO-8601 Z snapshot_ts
        "admissible_use": "STRICT_CAUSAL",
        "selected_for": "BJ_SP_TIMESERIES #235 (2026-05+ cohort)",
        "note": "snapshot_ts is NATIVE_PROVEN; kickoff_ts is Beijing local — must be "
                "normalized to UTC with tz binding.",
    },
    {
        "source_id": "BEIDAN_XLSM_WORKBOOK",
        "family": "F2_INTERNAL_ARCHIVE",
        "provider": "internal workbook import (source_meta: beidan.xlsm)",
        "endpoint": "data/derived/beidan_xlsm/beidan_xlsm.sqlite",
        "acquisition_method": "already imported; labels initial/10h/1h/final",
        "terms_status": "internal",
        "cost": "free",
        "access": "A",
        "licensing": "A",
        "coverage": "A",   # 2013-2025 full historical pool
        "clock_grade": "C",  # labels only, not exact timestamps (REQ-DS03)
        "admissible_use": "RETROSPECTIVE_PROXY",
        "selected_for": "EU_ODDS #236 (proxy cohort only; strict requires label proof)",
        "note": "51.5M snapshots across 4 markets; snapshot column holds labels, "
                "NOT timestamps. Identity has 2560 NULL rows — excluded from canonical "
                "identity until resolved.",
    },
    {
        "source_id": "BEIDAN_FEATURES_DB",
        "family": "F2_INTERNAL_ARCHIVE",
        "provider": "internal feature database",
        "endpoint": "data/beidan_features.db",
        "acquisition_method": "already present",
        "terms_status": "internal",
        "cost": "free",
        "access": "A",
        "licensing": "A",
        "coverage": "B",   # 190746 rows, seasons 2014-2025
        "clock_grade": "C",  # kickoff formats mixed; close/open labels no exact clock
        "admissible_use": "RETROSPECTIVE_PROXY",
        "selected_for": "EU_ODDS #236 (proxy cohort)",
        "note": "kickoff column mixes 'YYYY-MM-DDTHH:MM:SS' and bare 'HH:MM:SS' — "
                "min kickoff probe returns '08:00:00' (time-only garbage). Not strict.",
    },
    {
        "source_id": "BEIDAN_HISTORY_DB",
        "family": "F2_INTERNAL_ARCHIVE",
        "provider": "internal settlement/history rows",
        "endpoint": "data/beidan_history.db",
        "acquisition_method": "already present",
        "terms_status": "internal",
        "cost": "free",
        "access": "A",
        "licensing": "A",
        "coverage": "B",   # 2024-2026 (settlement-oriented)
        "clock_grade": "U",  # no settled timestamp column
        "admissible_use": "SETTLEMENT_ONLY",
        "selected_for": "settlement cross-check only",
        "note": "historical_matches has NO settled timestamp column; result codes "
                "3/1/0 + 694 NULLs; 694 rows missing winning_sp.",
    },
    {
        "source_id": "ODDS_API",
        "family": "F3_EU_TIMESTAMPED",
        "provider": "The Odds API (licensed)",
        "endpoint": "api.the-odds-api.com (historical endpoint)",
        "acquisition_method": "paid API; timestamped snapshots from 2020",
        "terms_status": "commercial license required",
        "cost": "paid (user authority required for purchase)",
        "access": "B",   # key needed; user authority for purchase
        "licensing": "A",  # licensed
        "coverage": "C",   # verify football league/event coverage before acceptance
        "clock_grade": "A",  # official timestamped snapshots
        "admissible_use": "STRICT_CAUSAL",
        "selected_for": "EU_ODDS #236 (strict candidate — verify coverage first)",
        "note": "Requires exact league/event coverage, timestamp, bookmaker and "
                "market verification before acceptance (issue contract §source 3); "
                "pending coverage verification — do not count until verified.",
    },
    {
        "source_id": "FOOTBALL_DATA_CSV",
        "family": "F4_FOOTBALL_DATA_CSV",
        "provider": "Football-Data.co.uk",
        "endpoint": "data/raw/football-data/*.csv",
        "acquisition_method": "download CSV archives",
        "terms_status": "free for non-commercial research; attribution required",
        "cost": "free",
        "access": "A",
        "licensing": "B",  # non-commercial
        "coverage": "A",   # major leagues covered
        "clock_grade": "C",  # no exact decision-epoch timestamp; results/open-close only
        "admissible_use": "RETROSPECTIVE_PROXY",
        "selected_for": "POWER_FEATURES #237 (secondary); EU proxy #236",
        "note": "Never silently becomes decision-epoch truth.",
    },
    {
        "source_id": "INTERNAL_RESULTS_POWER",
        "family": "F5_RESULTS_POWER",
        "provider": "internal results + accepted public football data",
        "endpoint": "canonical fixture identity (this contract)",
        "acquisition_method": "reuse existing results; explicit competition mapping",
        "terms_status": "internal",
        "cost": "free",
        "access": "A",
        "licensing": "A",
        "coverage": "B",   # power features limited to covered competitions
        "clock_grade": "A",  # completed matches before decision epoch
        "admissible_use": "STRICT_CAUSAL",
        "selected_for": "POWER_FEATURES #237 (primary)",
        "note": "Features must depend only on events before their decision epoch "
                "(REQ-PW01); StatsBomb Open Data limited coverage must not be "
                "generalized. Strict only within covered competitions.",
    },
]


def feasibility_matrix() -> list[dict]:
    return SOURCE_MATRIX


# ---------------------------------------------------------------------------
# Migration-free replacement plan (deliverable 4)
# ---------------------------------------------------------------------------
REPLACEMENT_PLAN = {
    "contract": "BJ-UNIFIED-DATA-SOURCE-SCHEMA-001/v1",
    "principle": "AGENTS.md principle 1 — no backward-compat tax. Obsolete "
                 "ambiguous schemas are removed from the accepted interface, "
                 "not wrapped in compatibility layers.",
    "replaced_schemas": [
        {
            "legacy": "beidan_xlsm.sqlite market_snapshots.snapshot column",
            "problem": "holds labels (initial/10h/1h/final) not timestamps; "
                       "cannot satisfy REQ-DS03 exact observed_at semantics",
            "replacement": "market_observation.observed_at_utc (exact) OR "
                           "snapshot_kind='PROXY_LABEL' with NULL observed_at "
                           "and explicit proxy namespace",
            "migration": "none — legacy column is not part of the canonical interface",
        },
        {
            "legacy": "beidan_features.db matches.kickoff mixed formats",
            "problem": "time-only strings ('08:00:00') sort before dates; "
                       "no tz binding",
            "replacement": "fixture.kickoff_at_utc (ISO-8601 Z, UTC)",
            "migration": "none — parsed only into canonical fixture when "
                         "identity resolves; otherwise UNRESOLVED",
        },
        {
            "legacy": "beidan_history.db historical_matches (no settled ts)",
            "problem": "settlement rows have no settled_at column; cannot "
                       "distinguish settlement time from kickoff",
            "replacement": "settlement.settled_at_utc + result_code + source_id",
            "migration": "none — SETTLEMENT_ONLY rows are re-derived by #235/#238 "
                         "from raw archives where clock exists, else excluded",
        },
        {
            "legacy": "beidan_xlsm.sqlite matches NULL issue/match_idx (2560 rows)",
            "problem": "identity broken; REQ-DS02 unique (issue, match_idx) violated",
            "replacement": "fixture requires issue_code+match_idx NOT NULL with "
                           "UNIQUE constraint; unresolved rows excluded",
            "migration": "none — orphan rows are not migrated, they are rejected "
                         "by the canonical constraint",
        },
        {
            "legacy": "probability vectors stored as wide columns "
                      "(p_close_3/1/0, sp_3/1/0)",
            "problem": "not long-form; risks column-order drift and partial "
                       "triplets",
            "replacement": "market_quote / probability_estimate long-form "
                           "outcome_code-scalar rows with UNIQUE "
                           "(observation, outcome_code)",
            "migration": "none — wide columns are not part of the canonical interface",
        },
    ],
    "concurrency_justification": {
        "engine": "SQLite WAL",
        "rationale": "one-writer append-only capture/control tables; WAL allows "
                     "concurrent readers during writes; measured 262 MB live DB "
                     "with 1.49M snapshots operates fine today",
        "scale_measurements": {
            "beidan_live_db_size_mb": 262,
            "snapshot_rows": 1494539,
            "xlsm_snapshot_rows": 51551016,
            "decision": "Do not introduce a new service/database until measured "
                        "concurrency requires it (issue contract).",
        },
        "research_snapshots": "immutable partitioned Parquet read by "
                              "pandas/PyArrow — no JSON-blob probability vectors",
    },
    "acceptance_binding": {
        "REQ-DS01": "source_feasibility_matrix.csv (classification with evidence)",
        "REQ-DS02": "fixture UNIQUE(issue_code, match_idx) + identity_crosswalk.csv",
        "REQ-DS03": "market_observation.observed_at_utc vs received_at_utc vs "
                    "fixture.kickoff_at_utc vs decision_epoch.decision_at_utc "
                    "distinct columns with domain dictionary notes",
        "REQ-DS04": "market_quote UNIQUE(observation_id, outcome_code) + "
                    "CHECK outcome_code IN ('3','1','0')",
        "REQ-DS05": "physical namespaces: capture / inference / settlement tables "
                    "separate; settlement table physically separate",
        "REQ-DS06": "SQLite WAL + PyArrow; scale/concurrency justification above",
        "REQ-DS07": "MANIFEST.json + SHA256SUMS.json binding machine-readable "
                    "outputs and source hashes",
        "REQ-DS08": "handoff section in replacement_plan.md names exact "
                    "interfaces for #235/#236/#237/#238",
    },
}
