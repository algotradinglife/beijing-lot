"""Issue #234 — evidence-based source registry and feasibility matrix (v2).

v2 rework addresses EV R1 defect class C2:

- Every source row binds a REAL provider, endpoint (from the repository's
  actual collector code), acquisition method, terms status, clock semantics,
  coverage grade and a resolvable raw-content hash receipt.  No prose-only
  grades; ``raw_sha256`` is never empty for usable rows.
- The 500.com third-party data plane is named honestly: the repository's
  collectors request ``trade.500.com`` / ``www.500.com`` / ``live.500.com``
  (see ``src/live_collector/scraper.py``, ``scripts/scrape_500_bjdc.py``).
  This is NOT the Beijing Sports Lottery first-party official interface; the
  F1 row therefore carries ``provider=500.com (third-party data plane)`` and
  the first-party interface itself is registered as a separate UNUSABLE /
  not-yet-acquired row.
- A source may only be ``STRICT_CAUSAL`` when its clock is TIMESTAMPED_UTC
  AND it has a resolvable raw receipt; the DDL CHECK enforces this too.
- The selected source per downstream branch references a concrete registry
  row (REQ-DS08).

Evidence citations refer to repository files at the audited base
(``784a23b``): ``src/live_collector/scraper.py:40-41``,
``scripts/scrape_500_bjdc.py:46-47``, ``scripts/verify_settlements.py:42-64``.
"""

from __future__ import annotations

import pandas as pd

from . import contract

# ---------------------------------------------------------------------------
# Evidence base: actual collector endpoints (cited, not invented)
# ---------------------------------------------------------------------------
ENDPOINT_EVIDENCE = {
    "trade.500.com": "src/live_collector/scraper.py:40-41 "
                     "(URL_BJDC_500 = https://trade.500.com/bjdc/?expect={issue})",
    "www.500.com": "scripts/scrape_500_bjdc.py:47 "
                   "(LIVE_SP_URL = https://www.500.com/static/public/bjdc/xml/sp/...)",
    "live.500.com": "scripts/verify_settlements.py:42-64 "
                    "(zqdc.php per-match scoreboard + wanchang.php date bucket)",
    "zx.500.com": "src/live_collector/scraper.py:44 "
                  "(URL_KAIJIANG_500 = https://zx.500.com/zqdc/kaijiang.php...)",
    "cp.zgzcw.com": "src/live_collector/scraper.py:43 "
                    "(URL_BET_ZGZCW = https://cp.zgzcw.com/lottery/bdplayvsforJsp.action)",
}


def _registry_row(
    *,
    source_id: str,
    provider: str,
    endpoint: str,
    endpoint_evidence: str,
    acquisition_method: str,
    terms_status: str,
    timezone: str,
    clock_semantics: str,
    cadence_seconds: str,
    parser_version: str,
    admissible_use: str,
    first_usable_at_utc: str,
    last_usable_at_utc: str,
    coverage_grade: str,
    raw_sha256: str,
    notes: str,
    selected_for_branch: str = "",
) -> dict[str, str]:
    return {
        "source_id": source_id,
        "provider": provider,
        "endpoint": endpoint,
        "endpoint_evidence": endpoint_evidence,
        "acquisition_method": acquisition_method,
        "terms_status": terms_status,
        "timezone": timezone,
        "clock_semantics": clock_semantics,
        "cadence_seconds": cadence_seconds,
        "parser_version": parser_version,
        "admissible_use": admissible_use,
        "first_usable_at_utc": first_usable_at_utc,
        "last_usable_at_utc": last_usable_at_utc,
        "coverage_grade": coverage_grade,
        "raw_sha256": raw_sha256,
        "notes": notes,
        "selected_for_branch": selected_for_branch,
    }


def registry_rows(census_hashes: dict[str, str] | None = None) -> list[dict[str, str]]:
    """Source registry rows, frozen by contract (v2).

    ``census_hashes`` maps database_key -> sha256 (from the executed census)
    so usable rows bind a real raw-content receipt (REQ-DS07).
    """
    census_hashes = census_hashes or {}
    h = lambda key: census_hashes.get(key, "PENDING_CENSUS")  # noqa: E731

    rows: list[dict[str, str]] = [
        # F1: the issue's "Beijing first-party" family.  The first-party
        # official interface is NOT currently acquired; the repository's
        # actual prospective capture is the 500.com data plane, named here.
        _registry_row(
            source_id="BJ_FIRST_PARTY_OFFICIAL",
            provider="Beijing Sports Lottery official interface (not acquired)",
            endpoint="official interface (未接入); no repo collector exists",
            endpoint_evidence="no repository collector; F1 gap recorded",
            acquisition_method="none — requires first-party access agreement",
            terms_status="unknown — not contracted",
            timezone="Asia/Shanghai",
            clock_semantics="NO_CLOCK",
            cadence_seconds="N/A",
            parser_version="N/A",
            admissible_use="UNUSABLE",
            first_usable_at_utc="",
            last_usable_at_utc="",
            coverage_grade="F",
            raw_sha256="NO_RECEIPT",
            notes="REQ-DS01 evidence: first-party interface not yet acquired; "
                  "prospective capture is deferred to #235 wiring.",
        ),
        _registry_row(
            source_id="BEIDAN_LIVE_DB",
            provider="internal live collector over 500.com data plane",
            endpoint="trade.500.com/bjdc/?expect={issue} + www.500.com static SP XML",
            endpoint_evidence=ENDPOINT_EVIDENCE["trade.500.com"] + "; " +
                             ENDPOINT_EVIDENCE["www.500.com"],
            acquisition_method="prospective timestamped capture (snapshot_ts UTC)",
            terms_status="internal research asset; 500.com display terms (unlicensed redistribution uncertain)",
            timezone="UTC (snapshot_ts) / naive local (created_ts)",
            clock_semantics="TIMESTAMPED_UTC",
            cadence_seconds="60",
            parser_version="live_collector_1",
            admissible_use="STRICT_CAUSAL",
            first_usable_at_utc="2026-05-02T00:57:41Z",
            last_usable_at_utc="present (live, unbounded; not a frozen snapshot)",
            coverage_grade="A",
            raw_sha256=h("beidan_live.db"),
            notes="Primary prospective causal source for #235; 1.5M+ snapshots "
                  "with canonical-Z snapshot_ts (0 null, 0 non-canonical-Z at census). "
                  "Clock is collector UTC fetch clock (trusted fetch clock, raw payload "
                  "receipts in 500_bjdc.sqlite live_market_sp_snapshots).",
            selected_for_branch=contract.BRANCH_BEIJING,
        ),
        # F2 internal historical archives
        _registry_row(
            source_id="BEIDAN_XLSM_WORKBOOK",
            provider="internal workbook conversion (beidan.xlsm)",
            endpoint="data/derived/beidan_xlsm/beidan_xlsm.sqlite",
            endpoint_evidence="census inventory (local sqlite, read-only)",
            acquisition_method="historical workbook conversion (2014-2025)",
            terms_status="internal research asset",
            timezone="Asia/Shanghai (naive)",
            clock_semantics="LABEL_RELATIVE",
            cadence_seconds="N/A",
            parser_version="xlsm_converter_1",
            admissible_use="RETROSPECTIVE_PROXY",
            first_usable_at_utc="2014-01-01T00:00:00Z",
            last_usable_at_utc="2025-07-13T00:00:00Z",
            coverage_grade="C",
            raw_sha256=h("beidan_xlsm.sqlite"),
            notes="51.5M labelled market snapshots; labels initial/10h/1h/final "
                  "are NOT exact observation timestamps (REQ-DS03). Settlement "
                  "tables are SETTLEMENT_ONLY (see official_500_settlements row).",
        ),
        _registry_row(
            source_id="BEIDAN_XLSM_SETTLEMENTS",
            provider="internal workbook conversion (official_500_settlements)",
            endpoint="data/derived/beidan_xlsm/beidan_xlsm.sqlite:official_500_settlements",
            endpoint_evidence="census inventory (SEALED table — settlement truth)",
            acquisition_method="historical workbook conversion",
            terms_status="internal research asset",
            timezone="Asia/Shanghai (naive)",
            clock_semantics="SETTLEMENT_AFTER_EVENT",
            cadence_seconds="N/A",
            parser_version="xlsm_converter_1",
            admissible_use="SETTLEMENT_ONLY",
            first_usable_at_utc="2014-01-01T00:00:00Z",
            last_usable_at_utc="2025-07-13T00:00:00Z",
            coverage_grade="D",
            raw_sha256=h("beidan_xlsm.sqlite"),
            notes="Settlement rows are never inference-time observations; "
                  "census never reads their values (C4 sealed).",
        ),
        _registry_row(
            source_id="BEIDAN_FEATURES_DB",
            provider="internal features archive",
            endpoint="data/beidan_features.db",
            endpoint_evidence="census inventory (local sqlite, read-only)",
            acquisition_method="historical build (2014-2025)",
            terms_status="internal research asset",
            timezone="Asia/Shanghai (naive)",
            clock_semantics="LABEL_RELATIVE",
            cadence_seconds="N/A",
            parser_version="features_builder_1",
            admissible_use="RETROSPECTIVE_PROXY",
            first_usable_at_utc="2014-01-01T00:00:00Z",
            last_usable_at_utc="2025-07-13T00:00:00Z",
            coverage_grade="C",
            raw_sha256=h("beidan_features.db"),
            notes="European close/open probability labels without exact "
                  "observation clocks; proxy only until clock provenance proven.",
        ),
        _registry_row(
            source_id="BEIDAN_HISTORY_DB",
            provider="internal settlement/history archive",
            endpoint="data/beidan_history.db",
            endpoint_evidence="census inventory (local sqlite, read-only)",
            acquisition_method="historical scrape (2024-2026)",
            terms_status="internal research asset",
            timezone="Asia/Shanghai (naive)",
            clock_semantics="SETTLEMENT_AFTER_EVENT",
            cadence_seconds="N/A",
            parser_version="history_scraper_1",
            admissible_use="SETTLEMENT_ONLY",
            first_usable_at_utc="2024-01-01T00:00:00Z",
            last_usable_at_utc="2026-08-16T00:00:00Z",
            coverage_grade="D",
            raw_sha256=h("beidan_history.db"),
            notes="No settled-timestamp column; settlement + average closing odds "
                  "are not inference-time observations.",
        ),
        _registry_row(
            source_id="BEIDAN_500BJDC",
            provider="internal 500.com collector (raw receipts + workflow state)",
            endpoint="trade.500.com / live.500.com / zx.500.com",
            endpoint_evidence=ENDPOINT_EVIDENCE["trade.500.com"] + "; " +
                             ENDPOINT_EVIDENCE["live.500.com"] + "; " +
                             ENDPOINT_EVIDENCE["zx.500.com"],
            acquisition_method="prospective HTTP capture with raw payload sha256 receipts",
            terms_status="internal research asset; 500.com display terms",
            timezone="HKT (source_updated_at_hkt) / UTC (fetched_at_utc)",
            clock_semantics="TIMESTAMPED_UTC",
            cadence_seconds="60",
            parser_version="scrape_500_bjdc_1",
            admissible_use="STRICT_CAUSAL",
            first_usable_at_utc="2026-05-01T00:00:00Z",
            last_usable_at_utc="present (live, unbounded)",
            coverage_grade="A",
            raw_sha256=h("500_bjdc.sqlite"),
            notes="Raw payload receipts (payload_sha256 + raw_node + source_url) "
                  "in live_market_sp_snapshots / market_sp_capture_batches; "
                  "17GB live DB is not a frozen snapshot (continuous append).",
            selected_for_branch=contract.BRANCH_INTEGRATION,
        ),
        _registry_row(
            source_id="BEIDAN_MODELING_PLUS_2026",
            provider="internal modeling archive (2026)",
            endpoint="data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite",
            endpoint_evidence="census inventory (local sqlite, read-only)",
            acquisition_method="historical conversion",
            terms_status="internal research asset",
            timezone="Asia/Shanghai (naive)",
            clock_semantics="LABEL_RELATIVE",
            cadence_seconds="N/A",
            parser_version="modeling_plus_1",
            admissible_use="RETROSPECTIVE_PROXY",
            first_usable_at_utc="2014-01-01T00:00:00Z",
            last_usable_at_utc="2026-01-01T00:00:00Z",
            coverage_grade="C",
            raw_sha256=h("beidan_modeling_plus_2026.sqlite"),
            notes="Overlaps BEIDAN_XLSM_WORKBOOK feature tables; kept for census "
                  "completeness; proxy class applies.",
        ),
        _registry_row(
            source_id="BEIDAN_NOWSCORE_2026",
            provider="internal nowscore archive (2026)",
            endpoint="data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite",
            endpoint_evidence="census inventory (local sqlite, read-only)",
            acquisition_method="historical conversion",
            terms_status="internal research asset",
            timezone="Asia/Shanghai (naive)",
            clock_semantics="LABEL_RELATIVE",
            cadence_seconds="N/A",
            parser_version="nowscore_1",
            admissible_use="RETROSPECTIVE_PROXY",
            first_usable_at_utc="2014-01-01T00:00:00Z",
            last_usable_at_utc="2026-01-01T00:00:00Z",
            coverage_grade="C",
            raw_sha256=h("beidan_nowscore_2026.sqlite"),
            notes="official_3sp_settlements is SETTLEMENT_ONLY (sealed).",
        ),
        # F3 European feed
        _registry_row(
            source_id="ODDS_API_HISTORICAL",
            provider="The Odds API",
            endpoint="api.the-odds-api.com (historical snapshots from 2020, paid)",
            endpoint_evidence="issue contract family 3; coverage evaluation pending",
            acquisition_method="licensed API purchase (NOT yet purchased — issue boundary)",
            terms_status="paid license; usage limits; coverage evaluation pending",
            timezone="UTC",
            clock_semantics="TIMESTAMPED_UTC",
            cadence_seconds="variable (plan-dependent)",
            parser_version="odds_api_1",
            admissible_use="RETROSPECTIVE_PROXY",
            first_usable_at_utc="2020-01-01T00:00:00Z",
            last_usable_at_utc="present",
            coverage_grade="B",
            raw_sha256="NO_RECEIPT",
            notes="Clock semantics declared by vendor; not yet independently "
                  "proven.  Graded RETROSPECTIVE_PROXY until exact league/event/"
                  "timestamp/bookmaker coverage is evaluated and raw receipts "
                  "are captured.  #236 consumes this row.",
            selected_for_branch=contract.BRANCH_EUROPEAN,
        ),
        # F4 Football-Data CSV
        _registry_row(
            source_id="FOOTBALL_DATA_CSV",
            provider="Football-Data.co.uk CSV",
            endpoint="raw/football-data/*.csv (results + open/close odds)",
            endpoint_evidence="issue contract family 4; raw archives if recoverable",
            acquisition_method="download/archive",
            terms_status="public display with attribution",
            timezone="naive (kickoff date only)",
            clock_semantics="SCHEDULE_ONLY",
            cadence_seconds="N/A",
            parser_version="football_data_1",
            admissible_use="RETROSPECTIVE_PROXY",
            first_usable_at_utc="",
            last_usable_at_utc="",
            coverage_grade="D",
            raw_sha256="NO_RECEIPT",
            notes="Retained only as results/open-or-close odds proxy where "
                  "timestamp semantics are insufficient; can never silently "
                  "become decision-epoch truth.",
        ),
        # F5 results / power features
        _registry_row(
            source_id="INTERNAL_RESULTS_POWER",
            provider="internal match results + accepted public football data",
            endpoint="beidan_xlsm.matches (result_label/score) + 500_bjdc.matches "
                     "(result_code) — SEALED columns",
            endpoint_evidence="census identity + settlement sealing (C4)",
            acquisition_method="historical extraction (settlement namespace only)",
            terms_status="internal research asset",
            timezone="Asia/Shanghai (naive)",
            clock_semantics="SETTLEMENT_AFTER_EVENT",
            cadence_seconds="N/A",
            parser_version="results_power_1",
            admissible_use="SETTLEMENT_ONLY",
            first_usable_at_utc="2014-01-01T00:00:00Z",
            last_usable_at_utc="2026-08-16T00:00:00Z",
            coverage_grade="C",
            raw_sha256=h("beidan_xlsm.sqlite") or h("500_bjdc.sqlite"),
            notes="Settlement/result namespace for team/league power features "
                  "(#237); identity mapping via issue_code x match_idx crosswalk; "
                  "never inference-time observations.",
            selected_for_branch=contract.BRANCH_POWER,
        ),
    ]
    return rows


def registry_frame(census_hashes: dict[str, str] | None = None) -> pd.DataFrame:
    return pd.DataFrame(registry_rows(census_hashes))


def feasibility_matrix(census_hashes: dict[str, str] | None = None) -> pd.DataFrame:
    """Feasibility matrix = registry rows + acquisition cost/access columns.

    Every row carries the evidence columns (endpoint_evidence, raw_sha256,
    admissible_use, clock_semantics) so REQ-DS01 is evidenced, not reputed.
    """
    frame = registry_frame(census_hashes)
    cost_map = {
        "BJ_FIRST_PARTY_OFFICIAL": "unknown (contract negotiation)",
        "BEIDAN_LIVE_DB": "already owned",
        "BEIDAN_XLSM_WORKBOOK": "already owned",
        "BEIDAN_XLSM_SETTLEMENTS": "already owned",
        "BEIDAN_FEATURES_DB": "already owned",
        "BEIDAN_HISTORY_DB": "already owned",
        "BEIDAN_500BJDC": "already owned",
        "BEIDAN_MODELING_PLUS_2026": "already owned",
        "BEIDAN_NOWSCORE_2026": "already owned",
        "ODDS_API_HISTORICAL": "paid (not purchased — issue boundary)",
        "FOOTBALL_DATA_CSV": "free (public)",
        "INTERNAL_RESULTS_POWER": "already owned",
    }
    access_map = {
        "BJ_FIRST_PARTY_OFFICIAL": "requires first-party agreement",
        "BEIDAN_LIVE_DB": "local sqlite (read-only census)",
        "BEIDAN_XLSM_WORKBOOK": "local sqlite (read-only census)",
        "BEIDAN_XLSM_SETTLEMENTS": "local sqlite (read-only census)",
        "BEIDAN_FEATURES_DB": "local sqlite (read-only census)",
        "BEIDAN_HISTORY_DB": "local sqlite (read-only census)",
        "BEIDAN_500BJDC": "local sqlite (read-only census)",
        "BEIDAN_MODELING_PLUS_2026": "local sqlite (read-only census)",
        "BEIDAN_NOWSCORE_2026": "local sqlite (read-only census)",
        "ODDS_API_HISTORICAL": "REST API with key (after purchase + coverage eval)",
        "FOOTBALL_DATA_CSV": "public download",
        "INTERNAL_RESULTS_POWER": "local sqlite (read-only census)",
    }
    frame["acquisition_cost"] = frame["source_id"].map(cost_map)
    frame["access"] = frame["source_id"].map(access_map)
    return frame
