"""Issue #234 — source feasibility matrix (REQ-DS01, REQ-DS08).

Every source family receives a scored feasibility row: acquisition cost,
access path, licensing/terms status, coverage grade, clock grade and the
concrete selected source for the downstream branch that must consume it.
Selection is evidence-based (clock provenance + coverage) — never by
reputation (REQ-DS01).

The matrix is frozen contract data: the same rows feed the markdown document
and the machine-readable CSV so they cannot drift apart.
"""

from __future__ import annotations

import pandas as pd

from . import contract

# ---------------------------------------------------------------------------
# Feasibility matrix rows (frozen)
# ---------------------------------------------------------------------------
# Each row: family, source_key, provider, endpoint, acquisition_method,
# terms_status, timezone, clock_semantics, cadence_seconds, parser_version,
# admissible_use, first_usable_at_utc, last_usable_at_utc, coverage_grade,
# cost, access, licensing, selected_for_branch, rationale.
FEASIBILITY_ROWS: tuple[dict[str, str], ...] = (
    {
        "family": contract.FAMILY_BEIJING,
        "source_key": "beijing_official_interface",
        "provider": "Beijing Sports Lottery official interface",
        "endpoint": "official 500.com live/issue feed (prospective capture)",
        "acquisition_method": "prospective capture with raw payload + trusted fetch clock",
        "terms_status": "public display, unlicensed redistribution uncertain",
        "timezone": "Asia/Shanghai",
        "clock_semantics": contract.CLOCK_TIMESTAMPED_UTC,
        "cadence_seconds": "60",
        "parser_version": "live_collector_1",
        "admissible_use": contract.USE_STRICT_CAUSAL,
        "first_usable_at_utc": "2026-05-01T00:00:00Z",
        "last_usable_at_utc": "present",
        "coverage_grade": contract.GRADE_A,
        "cost": "free (self-capture)",
        "access": "direct HTTP scrape; no API key required",
        "licensing": "display terms; store raw payload + fetch clock as evidence",
        "selected_for_branch": contract.BRANCH_BEIJING,
        "rationale": "Primary prospective causal source: native handicap + instant SP "
        "with raw payload and trusted fetch clock; clock TIMESTAMPED_UTC.",
    },
    {
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "source_key": "beidan_xlsm_workbook",
        "provider": "internal collector workbook (beidan.xlsm)",
        "endpoint": "data/derived/beidan_xlsm/beidan_xlsm.sqlite",
        "acquisition_method": "historical workbook conversion (2014-2025)",
        "terms_status": "internal research asset",
        "timezone": "Asia/Shanghai (naive)",
        "clock_semantics": contract.CLOCK_LABEL_RELATIVE,
        "cadence_seconds": "N/A",
        "parser_version": "xlsm_converter_1",
        "admissible_use": contract.USE_RETROSPECTIVE_PROXY,
        "first_usable_at_utc": "2014-01-01T00:00:00Z",
        "last_usable_at_utc": "2025-07-13T00:00:00Z",
        "coverage_grade": contract.GRADE_C,
        "cost": "already owned",
        "access": "local sqlite (read-only census)",
        "licensing": "internal; labels initial/10h/1h/final not accepted as exact "
        "observation timestamps until independently proven",
        "selected_for_branch": "",
        "rationale": "51.5M labelled snapshots with LABEL_RELATIVE clocks; usable only "
        "as RETROSPECTIVE_PROXY until source clock provenance demonstrated.",
    },
    {
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "source_key": "beidan_live_db",
        "provider": "live collector (2026-05+)",
        "endpoint": "data/beidan_live.db:snapshots",
        "acquisition_method": "prospective timestamped capture",
        "terms_status": "internal research asset",
        "timezone": "UTC (snapshot_ts) / naive local (created_ts)",
        "clock_semantics": contract.CLOCK_TIMESTAMPED_UTC,
        "cadence_seconds": "60",
        "parser_version": "live_collector_1",
        "admissible_use": contract.USE_STRICT_CAUSAL,
        "first_usable_at_utc": "2026-05-02T00:57:41Z",
        "last_usable_at_utc": "present",
        "coverage_grade": contract.GRADE_A,
        "cost": "already owned",
        "access": "local sqlite (read-only census)",
        "licensing": "internal",
        "selected_for_branch": contract.BRANCH_BEIJING,
        "rationale": "Primary prospective causal source; snapshot_ts is TIMESTAMPED_UTC "
        "with 1.49M rows observed 2026-05+.",
    },
    {
        "family": contract.FAMILY_EUROPEAN_FEED,
        "source_key": "odds_api_historical",
        "provider": "The Odds API",
        "endpoint": "api.the-odds-api.com (historical snapshots from 2020, paid)",
        "acquisition_method": "licensed API purchase",
        "terms_status": "paid license; usage limits",
        "timezone": "UTC",
        "clock_semantics": contract.CLOCK_TIMESTAMPED_UTC,
        "cadence_seconds": "variable (plan-dependent)",
        "parser_version": "odds_api_1",
        "admissible_use": contract.USE_STRICT_CAUSAL,
        "first_usable_at_utc": "2020-01-01T00:00:00Z",
        "last_usable_at_utc": "present",
        "coverage_grade": contract.GRADE_B,
        "cost": "paid (per-request plan)",
        "access": "REST API with key",
        "licensing": "commercial license required; evaluate exact league/event "
        "coverage, timestamp, bookmaker and market requirements",
        "selected_for_branch": contract.BRANCH_EUROPEAN,
        "rationale": "Selected EU branch source: licensed timestamped European "
        "bookmaker feed; GRADE_B while coverage is evaluated.",
    },
    {
        "family": contract.FAMILY_EUROPEAN_FEED,
        "source_key": "beidan_xlsm_euro_1x2",
        "provider": "internal workbook euro_1x2 snapshots",
        "endpoint": "beidan_xlsm.sqlite:market_snapshots (euro_1x2)",
        "acquisition_method": "historical workbook conversion",
        "terms_status": "internal research asset",
        "timezone": "Asia/Shanghai (naive)",
        "clock_semantics": contract.CLOCK_LABEL_RELATIVE,
        "cadence_seconds": "N/A",
        "parser_version": "xlsm_converter_1",
        "admissible_use": contract.USE_RETROSPECTIVE_PROXY,
        "first_usable_at_utc": "2014-01-01T00:00:00Z",
        "last_usable_at_utc": "2025-07-13T00:00:00Z",
        "coverage_grade": contract.GRADE_C,
        "cost": "already owned",
        "access": "local sqlite (read-only census)",
        "licensing": "internal",
        "selected_for_branch": "",
        "rationale": "EU probability features present historically but clock is "
        "LABEL_RELATIVE; RETROSPECTIVE_PROXY only.",
    },
    {
        "family": contract.FAMILY_FOOTBALL_DATA_CSV,
        "source_key": "football_data_csv",
        "provider": "Football-Data.co.uk",
        "endpoint": "data/raw/football-data/*.csv",
        "acquisition_method": "historical CSV download",
        "terms_status": "free for research with attribution",
        "timezone": "naive local (schedule only)",
        "clock_semantics": contract.CLOCK_SCHEDULE_ONLY,
        "cadence_seconds": "N/A",
        "parser_version": "football_data_csv_1",
        "admissible_use": contract.USE_RETROSPECTIVE_PROXY,
        "first_usable_at_utc": "2020-01-01T00:00:00Z",
        "last_usable_at_utc": "2025-07-01T00:00:00Z",
        "coverage_grade": contract.GRADE_C,
        "cost": "free",
        "access": "local CSV",
        "licensing": "attribution required; timestamp semantics insufficient for "
        "decision-epoch truth",
        "selected_for_branch": "",
        "rationale": "Results/open-or-close odds proxy only; cannot silently become "
        "decision-epoch truth (REQ-DS03).",
    },
    {
        "family": contract.FAMILY_POWER_FEATURES,
        "source_key": "internal_results_public_football",
        "provider": "internal match results + accepted public football data",
        "endpoint": "results + football-data CSV (causal team/league power features)",
        "acquisition_method": "internal results + public CSV",
        "terms_status": "internal + attribution",
        "timezone": "UTC/normalized",
        "clock_semantics": contract.CLOCK_TIMESTAMPED_UTC,
        "cadence_seconds": "N/A",
        "parser_version": "power_features_1",
        "admissible_use": contract.USE_STRICT_CAUSAL,
        "first_usable_at_utc": "2014-01-01T00:00:00Z",
        "last_usable_at_utc": "present",
        "coverage_grade": contract.GRADE_B,
        "cost": "already owned",
        "access": "local",
        "licensing": "internal + attribution",
        "selected_for_branch": contract.BRANCH_POWER,
        "rationale": "Causal team/league power features with explicit competition "
        "coverage and identity mapping (REQ-DS08).",
    },
    {
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "source_key": "beidan_features_db",
        "provider": "internal features database",
        "endpoint": "data/beidan_features.db:matches",
        "acquisition_method": "historical build",
        "terms_status": "internal research asset",
        "timezone": "naive local",
        "clock_semantics": contract.CLOCK_SCHEDULE_ONLY,
        "cadence_seconds": "N/A",
        "parser_version": "features_build_1",
        "admissible_use": contract.USE_RETROSPECTIVE_PROXY,
        "first_usable_at_utc": "2014-01-01T00:00:00Z",
        "last_usable_at_utc": "2025-04-15T00:00:00Z",
        "coverage_grade": contract.GRADE_C,
        "cost": "already owned",
        "access": "local sqlite (read-only census)",
        "licensing": "internal",
        "selected_for_branch": "",
        "rationale": "190k match identities with EU probabilities; kickoff is "
        "SCHEDULE_ONLY so RETROSPECTIVE_PROXY.",
    },
    {
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "source_key": "beidan_history_db",
        "provider": "internal history database",
        "endpoint": "data/beidan_history.db:historical_matches",
        "acquisition_method": "historical scrape",
        "terms_status": "internal research asset",
        "timezone": "naive local",
        "clock_semantics": contract.CLOCK_SETTLEMENT_AFTER_EVENT,
        "cadence_seconds": "N/A",
        "parser_version": "history_scrape_1",
        "admissible_use": contract.USE_SETTLEMENT_ONLY,
        "first_usable_at_utc": "2024-01-01T00:00:00Z",
        "last_usable_at_utc": "2026-12-31T00:00:00Z",
        "coverage_grade": contract.GRADE_D,
        "cost": "already owned",
        "access": "local sqlite (read-only census)",
        "licensing": "internal",
        "selected_for_branch": "",
        "rationale": "Settlement/history rows and average closing odds are not "
        "inference-time observations (REQ-DS03); SETTLEMENT_ONLY.",
    },
    {
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "source_key": "bj234_canonical_schema",
        "provider": "this contract's physical schema",
        "endpoint": "results/bj234_source_schema_contract_v1 (DDL + PyArrow schemas)",
        "acquisition_method": "design freeze (Issue #234)",
        "terms_status": "frozen contract",
        "timezone": "UTC",
        "clock_semantics": contract.CLOCK_TIMESTAMPED_UTC,
        "cadence_seconds": "N/A",
        "parser_version": contract.PACKAGE_NAME,
        "admissible_use": contract.USE_STRICT_CAUSAL,
        "first_usable_at_utc": "2026-08-16T00:00:00Z",
        "last_usable_at_utc": "present",
        "coverage_grade": contract.GRADE_A,
        "cost": "already owned",
        "access": "versioned DDL + parquet schema contract",
        "licensing": "internal contract",
        "selected_for_branch": contract.BRANCH_INTEGRATION,
        "rationale": "The integration branch consumes the canonical physical schema "
        "itself: sql/schema.sql, schemas/parquet_schema.json, domain dictionary "
        "and identity crosswalk (REQ-DS08).",
    },
)


def feasibility_matrix() -> pd.DataFrame:
    """Return the frozen feasibility matrix as a dataframe."""
    return pd.DataFrame(list(FEASIBILITY_ROWS))


def source_registry() -> pd.DataFrame:
    """Build the source_registry table rows (the full registry contract)."""
    rows: list[dict[str, str]] = []
    for item in FEASIBILITY_ROWS:
        rows.append(
            {
                "source_id": item["source_key"],
                "provider": item["provider"],
                "endpoint": item["endpoint"],
                "acquisition_method": item["acquisition_method"],
                "terms_status": item["terms_status"],
                "timezone": item["timezone"],
                "clock_semantics": item["clock_semantics"],
                "cadence_seconds": item["cadence_seconds"],
                "parser_version": item["parser_version"],
                "admissible_use": item["admissible_use"],
                "first_usable_at_utc": item["first_usable_at_utc"],
                "last_usable_at_utc": item["last_usable_at_utc"],
                "coverage_grade": item["coverage_grade"],
                "raw_sha256": "",  # bound by census source_hashes for accepted packages
                "notes": item["rationale"],
            }
        )
    return pd.DataFrame(rows, columns=contract.SOURCE_REGISTRY_COLUMNS)
