"""Immutable G0 eligibility audit for SCORE-HCAP-HIST-001.

The audit is deliberately limited to constructing and qualifying the historical
label panel.  It creates no ticket, return, EV, ROI, or production artifact.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = (
    "match_id", "issue", "match_idx", "kickoff_ts", "season_year", "league", "home", "away",
    "handicap_line_norm", "fthg", "ftag", "result_code", "settlement_quality",
)
TEST_SEASONS = tuple(range(2016, 2026))
TRAIN_SEASONS = (2014, 2015)
MIN_ROWS = 100_000
MIN_TEST_ROWS = 1_000
UTC = timezone.utc


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_kickoff(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.startswith("1899-12-30"):
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # The source has naive timestamps.  G0 records this as Evidence C but
        # uses the deterministic UTC convention for chronological ordering.
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds")


def _kickoff_status(value: object) -> str:
    """Classify raw kickoff availability without changing the frozen filter."""

    if value is None or not str(value).strip():
        return "missing"
    text = str(value).strip()
    if text.startswith("1899-12-30"):
        return "sentinel"
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "unparseable"
    return "parseable"


def _label(home_goals: int, away_goals: int, handicap: int) -> str:
    margin = home_goals + handicap - away_goals
    return "3" if margin > 0 else "1" if margin == 0 else "0"


def _normalize(value: object) -> str:
    return " ".join(str(value).strip().casefold().split())


def _schema_inventory(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute("PRAGMA table_info(match_features)").fetchall()
    return {
        "table": "match_features",
        "columns": [{"name": str(row[1]), "type": str(row[2] or "")} for row in rows],
        "required_columns": list(REQUIRED_COLUMNS),
        "missing_required_columns": sorted(set(REQUIRED_COLUMNS) - {str(row[1]) for row in rows}),
        "source_meta": [
            {"key": str(row[0]), "value": str(row[1] or "")}
            for row in connection.execute("SELECT key,value FROM source_meta ORDER BY key")
        ],
    }


MATRIX_COLUMNS = (
    "feature_family", "feature_name", "raw_or_derived", "source_table", "source_fields",
    "earliest_chronology", "latest_chronology", "row_coverage", "missingness_rate", "conflict_rate",
    "time_grade", "construction_rule_using_prior_rows_only", "leakage_risk",
    "proposed_future_ablation_priority", "existing_consumer_status", "notes",
)


def _rate(numerator: int, denominator: int) -> str:
    return f"{(numerator / denominator if denominator else 0.0):.6f}"


def export_feature_availability_matrix(*, source_db: Path, destination: Path) -> dict[str, Any]:
    """Inventory candidate features without calculating a model or a feature outcome.

    This is deliberately a schema/availability audit.  It reads neither score
    values nor result/SP/price values, and hence cannot calculate feature
    performance or accidentally add a feature to B0/B1.
    """

    source = sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    source.execute("PRAGMA query_only = ON")
    try:
        match_feature_columns = {str(row[1]) for row in source.execute("PRAGMA table_info(match_features)")}
        rank_expression = (
            "SUM(CASE WHEN home_rank IS NOT NULL AND TRIM(home_rank) <> '' AND away_rank IS NOT NULL AND TRIM(away_rank) <> '' THEN 1 ELSE 0 END) AS ranks_present"
            if {"home_rank", "away_rank"} <= match_feature_columns else "0 AS ranks_present"
        )
        base = source.execute(
            f"""
            SELECT COUNT(*) AS rows, MIN(kickoff_ts) AS earliest, MAX(kickoff_ts) AS latest,
                   SUM(CASE WHEN league IS NOT NULL AND TRIM(league) <> '' THEN 1 ELSE 0 END) AS league_present,
                   SUM(CASE WHEN home IS NOT NULL AND TRIM(home) <> '' AND away IS NOT NULL AND TRIM(away) <> '' THEN 1 ELSE 0 END) AS teams_present,
                   SUM(CASE WHEN home IS NOT NULL AND TRIM(home) <> '' AND away IS NOT NULL AND TRIM(away) <> '' AND fthg IS NOT NULL AND ftag IS NOT NULL THEN 1 ELSE 0 END) AS score_history_present,
                   SUM(CASE WHEN home IS NOT NULL AND TRIM(home) <> '' AND away IS NOT NULL AND TRIM(away) <> '' AND result_code IS NOT NULL AND TRIM(result_code) <> '' THEN 1 ELSE 0 END) AS result_history_present,
                   {rank_expression}
            FROM match_features
            WHERE season_year BETWEEN 2014 AND 2025
              AND kickoff_ts IS NOT NULL AND kickoff_ts NOT LIKE '1899-12-30%'
            """
        ).fetchone()
        rows = int(base["rows"] or 0)
        identity_conflicts = 0
        names: dict[tuple[str, str], set[str]] = defaultdict(set)
        for row in source.execute(
            """
            SELECT league, home, away FROM match_features
            WHERE season_year BETWEEN 2014 AND 2025
              AND kickoff_ts IS NOT NULL AND kickoff_ts NOT LIKE '1899-12-30%'
              AND league IS NOT NULL AND TRIM(league) <> ''
              AND home IS NOT NULL AND TRIM(home) <> ''
              AND away IS NOT NULL AND TRIM(away) <> ''
            """
        ):
            league = str(row["league"]).strip()
            for team in (str(row["home"]).strip(), str(row["away"]).strip()):
                names[(league, _normalize(team))].add(team)
        identity_conflicts = sum(1 for values in names.values() if len(values) > 1)
        market_table = source.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='market_consensus'"
        ).fetchone()[0] == 1
        market_rows = 0
        if market_table:
            market_rows = int(source.execute(
                """
                SELECT COUNT(DISTINCT mc.match_id)
                FROM market_consensus mc JOIN match_features mf ON mf.match_id = mc.match_id
                WHERE mf.season_year BETWEEN 2014 AND 2025
                  AND mf.kickoff_ts IS NOT NULL AND mf.kickoff_ts NOT LIKE '1899-12-30%'
                  AND mc.market IN ('euro_1x2','asian_handicap','over_under') AND mc.snapshot IN ('final','10h')
                """
            ).fetchone()[0])
    finally:
        source.close()

    earliest, latest = str(base["earliest"] or ""), str(base["latest"] or "")
    team_coverage = int(base["teams_present"] or 0)
    score_coverage = int(base["score_history_present"] or 0)
    result_coverage = int(base["result_history_present"] or 0)
    league_coverage = int(base["league_present"] or 0)
    rank_coverage = int(base["ranks_present"] or 0)
    common = {"earliest_chronology": earliest, "latest_chronology": latest}
    strict_rule = "freeze cutoff; sort (kickoff_utc, match_id); use only rows strictly earlier than the fixture"
    def item(family: str, name: str, kind: str, table: str, fields: str, coverage: int, grade: str, rule: str, risk: str, priority: str, status: str, notes: str, conflicts: int = 0) -> dict[str, str]:
        return {**common, "feature_family": family, "feature_name": name, "raw_or_derived": kind,
                "source_table": table, "source_fields": fields, "row_coverage": _rate(coverage, rows),
                "missingness_rate": _rate(rows - coverage, rows), "conflict_rate": _rate(conflicts, max(coverage, 1)),
                "time_grade": grade, "construction_rule_using_prior_rows_only": rule, "leakage_risk": risk,
                "proposed_future_ablation_priority": priority, "existing_consumer_status": status, "notes": notes}
    matrix = [
        item("rank", "pre_match_ranks", "raw", "match_features", "home_rank;away_rank", rank_coverage, "terminal-prohibited", "requires independently timestamped pre-kickoff rank capture", "no as-of timestamp; terminal row may be revised", "P2", "load_match_extras reads ranks; not eligible as strict evidence", "availability only"),
        item("team_history", "rolling_GF_GA", "derived", "match_features", "kickoff_ts;league;home;away;fthg;ftag", score_coverage, "strict-derived", strict_rule, "must never include same-fixture score", "P1", "not consumed by formal B0/B1", "only score-field presence, not score values, is inspected here" , identity_conflicts),
        item("team_history", "recent_WDL_points", "derived", "match_features", "kickoff_ts;league;home;away;result_code", result_coverage, "strict-derived", strict_rule, "must never include same-fixture result", "P1", "not consumed by formal B0/B1", "only result-field presence, not result values, is inspected here", identity_conflicts),
        item("team_history", "home_away_role_form", "derived", "match_features", "kickoff_ts;league;home;away;result_code", result_coverage, "strict-derived", strict_rule, "role and result must precede fixture", "P1", "TEAM_FORM_PROB_KEYS/team_* are consumed elsewhere but load_match_extras does not populate them", "existing placeholders fall to zero; not evidence of available team form", identity_conflicts),
        item("team_history", "draw_clean_sheet_BTTS_rates", "derived", "match_features", "kickoff_ts;league;home;away;fthg;ftag", score_coverage, "strict-derived", strict_rule, "must never include current score", "P2", "not consumed by formal B0/B1", "only score-field presence, not score values, is inspected here", identity_conflicts),
        item("score_distribution", "score_variance_overdispersion", "derived", "match_features", "kickoff_ts;league;home;away;fthg;ftag", score_coverage, "strict-derived", strict_rule, "requires pre-fixture-only score history", "P2", "not consumed by formal B0/B1", "only score-field presence, not score values, is inspected here", identity_conflicts),
        item("calendar", "rest_days", "derived", "match_features", "kickoff_ts;league;home;away", team_coverage, "strict-derived", strict_rule, "ambiguous team identity or kickoff timezone", "P2", "not consumed by formal B0/B1", "source kickoff timezone provenance is unavailable", identity_conflicts),
        item("calendar", "season_phase", "derived", "match_features", "season_year;kickoff_ts", rows, "strict-derived", "derive fixed ordinal phase from predeclared season calendar rule", "season boundary definition must be frozen", "P3", "not consumed by formal B0/B1", "calendar-only availability"),
        item("opponent_strength", "opponent_Elo", "derived", "match_features", "kickoff_ts;league;home;away;result_code", team_coverage, "strict-derived", strict_rule, "same-fixture or future update leakage", "P1", "not consumed by formal B0/B1", "result values are not read by this matrix", identity_conflicts),
        item("halftime", "historical_halftime_tendencies", "raw_or_derived", "match_features", "no halftime score columns", 0, "terminal-prohibited", "not constructible from this source", "missing source fields", "P4", "not consumed by formal B0/B1", "unavailable"),
        item("identity", "league_identity_pooling", "raw", "match_features", "league", league_coverage, "strict-derived", "freeze normalized league identity before fit", "league renames/aliases", "P1", "B1 may use only if separately preregistered", "availability only"),
        item("market_proxy", "Euro_1X2_Asian_OU_snapshots", "raw", "market_consensus", "market;snapshot;v1_avg;v2_avg;v3_avg", market_rows, "terminal-prohibited", "requires independently verified pre-kickoff observation timestamp", "final/10h snapshot provenance is insufficient here", "P4", "prohibited from formal B0/B1", "no price/SP values are read by this matrix"),
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_COLUMNS)
        writer.writeheader()
        writer.writerows(matrix)
    return {"path": destination.name, "rows": len(matrix), "outcome_independent": True, "sha256": sha256_file(destination)}


def export_g0_panel(*, source_db: Path, work_dir: Path) -> dict[str, Any]:
    """Export the frozen minimal historical panel and return its G0 audit."""

    work_dir.mkdir(parents=True, exist_ok=False)
    panel_path = work_dir / "historical_panel.sqlite"
    schema_path = work_dir / "source_schema.json"
    audit_path = work_dir / "g0_audit.json"
    matrix_path = work_dir / "feature_availability_matrix.csv"
    source = sqlite3.connect(f"file:{source_db.resolve()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    source.execute("PRAGMA query_only = ON")
    source.execute("BEGIN")
    try:
        schema = _schema_inventory(source)
        if schema["missing_required_columns"]:
            raise ValueError(f"missing required source columns: {schema['missing_required_columns']}")
        rows = source.execute(
            "SELECT match_id,issue,match_idx,kickoff_ts,season_year,league,home,away,"
            "handicap_line_norm,fthg,ftag,result_code,settlement_quality "
            "FROM match_features ORDER BY kickoff_ts,match_id"
        ).fetchall()
    finally:
        source.close()

    output = sqlite3.connect(panel_path)
    output.executescript(
        """
        CREATE TABLE panel (
          match_id INTEGER PRIMARY KEY, issue TEXT, match_idx INTEGER, kickoff_utc TEXT NOT NULL,
          season_year INTEGER NOT NULL, league TEXT NOT NULL, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
          normalized_home TEXT NOT NULL, normalized_away TEXT NOT NULL, handicap INTEGER NOT NULL,
          fthg INTEGER NOT NULL, ftag INTEGER NOT NULL, label_310 TEXT NOT NULL, settlement_quality TEXT
        );
        CREATE INDEX panel_season_clock ON panel(season_year,kickoff_utc,match_id);
        """
    )
    raw = len(rows)
    source_db_identity = {"filename": source_db.name, "bytes": source_db.stat().st_size, "sha256": sha256_file(source_db)}
    exclusions: Counter[str] = Counter()
    by_season_raw: Counter[int] = Counter()
    by_season_eligible: Counter[int] = Counter()
    mismatch = 0
    result_comparison_rows = 0
    normalized_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    canonical_keys: dict[tuple[str, int], set[int]] = defaultdict(set)
    source_match_ids: Counter[int] = Counter()
    source_issue_match_idx: dict[tuple[str, int], set[int]] = defaultdict(set)
    source_missing_issue_or_match_idx = 0
    mismatch_quality: Counter[str] = Counter()
    source_issues: set[str] = set()
    qualified_issues: set[str] = set()
    kickoff_diagnostics: Counter[str] = Counter()
    source_score_diagnostics: Counter[str] = Counter()
    score_diagnostics: Counter[str] = Counter()
    settlement_quality_counts: Counter[str] = Counter()
    parseable_kickoff_min: str | None = None
    parseable_kickoff_max: str | None = None
    max_home_goals: int | None = None
    max_away_goals: int | None = None
    source_max_home_goals: int | None = None
    source_max_away_goals: int | None = None
    seen_match_ids: set[int] = set()
    duplicate_match_ids = 0
    inserted: list[tuple[Any, ...]] = []
    for row in rows:
        raw_match_id = int(row["match_id"])
        source_match_ids[raw_match_id] += 1
        raw_issue_text = str(row["issue"] or "").strip()
        if raw_issue_text:
            source_issues.add(raw_issue_text)
        raw_issue = str(row["issue"] or "").strip()
        if not raw_issue or row["match_idx"] is None:
            source_missing_issue_or_match_idx += 1
        else:
            source_issue_match_idx[(raw_issue, int(row["match_idx"]))].add(raw_match_id)
        season = row["season_year"]
        if isinstance(season, int):
            by_season_raw[season] += 1
        settlement_quality_counts[str(row["settlement_quality"] or "")] += 1
        kickoff_diagnostics[_kickoff_status(row["kickoff_ts"])] += 1
        raw_home_goals, raw_away_goals = row["fthg"], row["ftag"]
        if raw_home_goals is None or raw_away_goals is None:
            source_score_diagnostics["rows_with_missing_score"] += 1
            if raw_home_goals is None:
                source_score_diagnostics["missing_fthg"] += 1
            if raw_away_goals is None:
                source_score_diagnostics["missing_ftag"] += 1
        elif not isinstance(raw_home_goals, int) or not isinstance(raw_away_goals, int):
            source_score_diagnostics["rows_with_noninteger_score"] += 1
        elif raw_home_goals < 0 or raw_away_goals < 0:
            source_score_diagnostics["rows_with_negative_score"] += 1
        else:
            source_max_home_goals = raw_home_goals if source_max_home_goals is None else max(source_max_home_goals, raw_home_goals)
            source_max_away_goals = raw_away_goals if source_max_away_goals is None else max(source_max_away_goals, raw_away_goals)
            if raw_home_goals > 20 or raw_away_goals > 20:
                source_score_diagnostics["rows_above_20_goals"] += 1
        kickoff = _parse_kickoff(row["kickoff_ts"])
        if kickoff is None:
            exclusions["invalid_or_sentinel_kickoff"] += 1
            continue
        parseable_kickoff_min = kickoff if parseable_kickoff_min is None else min(parseable_kickoff_min, kickoff)
        parseable_kickoff_max = kickoff if parseable_kickoff_max is None else max(parseable_kickoff_max, kickoff)
        if not isinstance(season, int) or season not in {*TRAIN_SEASONS, *TEST_SEASONS}:
            exclusions["outside_frozen_2014_2025_window"] += 1
            continue
        values = (row["league"], row["home"], row["away"])
        if any(value is None or not str(value).strip() for value in values):
            exclusions["missing_team_identity"] += 1
            continue
        issue = str(row["issue"] or "").strip()
        if not issue or row["match_idx"] is None:
            exclusions["missing_issue_or_match_idx"] += 1
            continue
        handicap_raw = row["handicap_line_norm"]
        if not isinstance(handicap_raw, (int, float)) or not math.isfinite(float(handicap_raw)) or not float(handicap_raw).is_integer():
            exclusions["missing_or_noninteger_handicap"] += 1
            continue
        home_goals, away_goals = row["fthg"], row["ftag"]
        if home_goals is None or away_goals is None:
            score_diagnostics["rows_with_missing_score"] += 1
            if home_goals is None:
                score_diagnostics["missing_fthg"] += 1
            if away_goals is None:
                score_diagnostics["missing_ftag"] += 1
            exclusions["missing_or_invalid_score"] += 1
            continue
        if not isinstance(home_goals, int) or not isinstance(away_goals, int):
            score_diagnostics["rows_with_noninteger_score"] += 1
            exclusions["missing_or_invalid_score"] += 1
            continue
        if home_goals < 0 or away_goals < 0:
            score_diagnostics["rows_with_negative_score"] += 1
            exclusions["missing_or_invalid_score"] += 1
            continue
        max_home_goals = home_goals if max_home_goals is None else max(max_home_goals, home_goals)
        max_away_goals = away_goals if max_away_goals is None else max(max_away_goals, away_goals)
        if home_goals > 20 or away_goals > 20:
            score_diagnostics["rows_above_20_goals"] += 1
        result_comparison_rows += 1
        computed = _label(int(row["fthg"]), int(row["ftag"]), int(handicap_raw))
        stored = str(row["result_code"] or "")
        if stored != computed:
            mismatch += 1
            mismatch_quality[str(row["settlement_quality"] or "")] += 1
            exclusions["stored_result_code_mismatch"] += 1
            continue
        league = str(row["league"]).strip()
        home, away = str(row["home"]).strip(), str(row["away"]).strip()
        normalized_home, normalized_away = _normalize(home), _normalize(away)
        match_id = int(row["match_id"])
        if match_id in seen_match_ids:
            duplicate_match_ids += 1
            exclusions["duplicate_match_id"] += 1
            continue
        seen_match_ids.add(match_id)
        canonical_keys[(issue, int(row["match_idx"]))].add(match_id)
        qualified_issues.add(issue)
        normalized_names[(league, normalized_home)].add(home)
        normalized_names[(league, normalized_away)].add(away)
        inserted.append((
            match_id, issue, int(row["match_idx"]), kickoff, season,
            league, home, away, normalized_home, normalized_away, int(handicap_raw), int(row["fthg"]),
            int(row["ftag"]), computed, str(row["settlement_quality"] or ""),
        ))
        by_season_eligible[season] += 1
    inserted.sort(key=lambda item: (item[3], item[0]))
    output.executemany("INSERT INTO panel VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", inserted)
    output.commit()
    output.execute("VACUUM")
    output.close()

    conflict_names = sum(1 for raw_names in normalized_names.values() if len(raw_names) > 1)
    mismatch_rate = mismatch / result_comparison_rows if result_comparison_rows else 1.0
    canonical_key_conflicts = sum(1 for match_ids in canonical_keys.values() if len(match_ids) > 1)
    source_duplicate_match_ids = sum(count - 1 for count in source_match_ids.values() if count > 1)
    source_issue_match_idx_conflicts = sum(1 for match_ids in source_issue_match_idx.values() if len(match_ids) > 1)
    test_counts = {str(year): by_season_eligible[year] for year in TEST_SEASONS}
    handicap_distribution: dict[str, dict[str, int]] = {}
    cold_start: dict[str, dict[str, float | int]] = {}
    for year in TEST_SEASONS:
        earlier_home = {(str(row[5]), str(row[8])) for row in inserted if int(row[4]) < year}
        earlier_away = {(str(row[5]), str(row[9])) for row in inserted if int(row[4]) < year}
        season_rows = [row for row in inserted if int(row[4]) == year]
        handicap_distribution[str(year)] = dict(sorted(Counter(str(row[10]) for row in season_rows).items(), key=lambda item: int(item[0])))
        cold = sum((str(row[5]), str(row[8])) not in earlier_home or (str(row[5]), str(row[9])) not in earlier_away for row in season_rows)
        cold_start[str(year)] = {"cold_start_rows": cold, "cold_start_rate": cold / len(season_rows) if season_rows else 0.0}
    gate_reasons: list[str] = []
    if len(inserted) < MIN_ROWS:
        gate_reasons.append("qualified_rows_below_100000")
    if len(TEST_SEASONS) < 8 or any(count < MIN_TEST_ROWS for count in test_counts.values()):
        gate_reasons.append("insufficient_complete_test_seasons")
    if mismatch_rate > 0.005:
        gate_reasons.append("result_code_mismatch_rate_above_0_5_percent")
    if duplicate_match_ids or canonical_key_conflicts:
        gate_reasons.append("unresolved_duplicate_or_canonical_key_conflicts")
    if conflict_names:
        gate_reasons.append("normalized_team_identity_conflicts_require_resolution")
    # Source metadata identifies derivation paths but contains no immutable
    # row-level raw-bundle identity, so Evidence B is not supportable.
    evidence_level = "C" if not gate_reasons else "D"
    matrix = export_feature_availability_matrix(source_db=source_db, destination=matrix_path)
    source_column_names = {str(column["name"]) for column in schema["columns"]}
    explicit_special_status_fields = sorted(
        column for column in source_column_names
        if any(token in column.casefold() for token in ("cancel", "postpon", "abandon", "status", "settlement"))
    )
    audit = {
        "experiment_id": "SCORE-HCAP-HIST-001",
        "stage": "G0",
        "experiment_type": "retrospective_walk_forward",
        "outcome_visibility": "historical_known",
        "execution_enabled": False,
        "frontend_selectable": False,
        "roi_authorized": False,
        "release_authorized": False,
        "timezone_normalization": "naive source kickoff timestamps deterministically interpreted as UTC; source timezone provenance is unavailable",
        "query_audit": {
            "read_columns": list(REQUIRED_COLUMNS),
            "prohibited_columns_not_read": ["winning_sp", "official_sp_3", "official_sp_1", "official_sp_0", "history_avg_eu_home", "history_avg_eu_draw", "history_avg_eu_away"],
            "ticket_budget_roi_output": False,
        },
        "coverage": {
            "raw_rows": raw,
            "qualified_rows": len(inserted),
            "issue_range": {
                "source_min": min(source_issues) if source_issues else None,
                "source_max": max(source_issues) if source_issues else None,
                "source_distinct": len(source_issues),
                "qualified_min": min(qualified_issues) if qualified_issues else None,
                "qualified_max": max(qualified_issues) if qualified_issues else None,
                "qualified_distinct": len(qualified_issues),
            },
            "kickoff_parseability": {
                "parseable_rows": kickoff_diagnostics["parseable"],
                "parseable_rate": kickoff_diagnostics["parseable"] / raw if raw else 0.0,
                "missing_rows": kickoff_diagnostics["missing"],
                "sentinel_rows": kickoff_diagnostics["sentinel"],
                "unparseable_rows": kickoff_diagnostics["unparseable"],
                "parseable_min_utc": parseable_kickoff_min,
                "parseable_max_utc": parseable_kickoff_max,
            },
            "score_diagnostics": {
                "source": {
                    **dict(sorted(source_score_diagnostics.items())),
                    "max_fthg": source_max_home_goals,
                    "max_ftag": source_max_away_goals,
                },
                "candidate_after_time_identity_handicap_filters": {
                    **dict(sorted(score_diagnostics.items())),
                    "max_fthg": max_home_goals,
                    "max_ftag": max_away_goals,
                },
            },
            "special_status_diagnostics": {
                "explicit_status_columns": explicit_special_status_fields,
                "settlement_quality_counts": dict(sorted(settlement_quality_counts.items())),
                "treatment": "No explicit cancellation/postponement/abandonment field exists in match_features; rows with missing, noninteger, or negative scores are excluded and counted."
            },
            "exclusions": dict(sorted(exclusions.items())),
            "by_season_raw": {str(year): count for year, count in sorted(by_season_raw.items())},
            "by_season_qualified": {str(year): count for year, count in sorted(by_season_eligible.items())},
            "test_season_counts": test_counts,
            "test_season_handicap_distribution": handicap_distribution,
            "test_season_cold_start": cold_start,
            "result_code_comparison_rows": result_comparison_rows,
            "stored_result_code_mismatches": mismatch,
            "stored_result_code_mismatch_rate": mismatch_rate,
            "stored_result_code_mismatch_by_settlement_quality": dict(sorted(mismatch_quality.items())),
            "source_duplicate_match_ids": source_duplicate_match_ids,
            "source_issue_match_idx_conflicts": source_issue_match_idx_conflicts,
            "source_missing_issue_or_match_idx": source_missing_issue_or_match_idx,
            "duplicate_match_ids": duplicate_match_ids,
            "issue_match_idx_conflicts": canonical_key_conflicts,
            "normalized_team_identity_conflicts": conflict_names,
        },
        "chronology": {"train_seasons": list(TRAIN_SEASONS), "test_seasons": list(TEST_SEASONS), "sort_key": ["kickoff_utc", "match_id"]},
        "provenance": {"source_database": source_db_identity, "source_meta_present": bool(schema["source_meta"]), "row_level_immutable_raw_bundle_verified": False, "evidence_level": evidence_level},
        "historical_peek_scope": "This source has been used by prior project retrospective analyses; all outputs are therefore retrospective re-analysis, not untouched forward validation.",
        "feature_availability_matrix": matrix,
        "gate": {
            "status": "G0_ELIGIBLE_EVIDENCE_C" if not gate_reasons else "INSUFFICIENT_HISTORICAL_DATA",
            "formal_b0_b1_authorized": not gate_reasons,
            "reasons": gate_reasons,
            "next_permitted_action": "freeze preregistered retrospective B0/B1 configuration only" if not gate_reasons else "publish G0 fail-closed evidence only",
        },
    }
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"panel": panel_path, "schema": schema_path, "audit": audit_path, "matrix": matrix_path, "audit_data": audit}
