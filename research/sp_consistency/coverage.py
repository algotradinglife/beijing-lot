"""G0 strict-coverage audit for SP-CONSISTENCY-001A.

This module deliberately does not load settlement outcomes and cannot compute
log loss, Brier scores, calibration, or a betting action.  It inventories only
the availability and provenance of permissible pre-match inputs.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

from src.multimarket_p0 import MultimarketP0Error, verify_segment_freeze


UTC = timezone.utc
HKT = timezone(timedelta(hours=8))
G0_CONFIG_VERSION = "sp-consistency-g0-v1"
MIN_STRICT_PAIRED_ROWS = 200
MIN_STRICT_PAIRED_ISSUES = 8


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    return connection


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _parse_utc(value: str, *, naive_timezone: timezone | None = None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        if naive_timezone is None:
            return None
        parsed = parsed.replace(tzinfo=naive_timezone)
    return parsed.astimezone(UTC)


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return round(ordered[index], 6)


def _nonempty(value: object) -> bool:
    return value is not None and bool(str(value).strip())


def _p34_coverage(connection: sqlite3.Connection, source_schema_path: Path) -> dict[str, Any]:
    if not (_table_exists(connection, "matches") and _table_exists(connection, "snapshots")):
        return {
            "status": "unavailable",
            "strict_complete_match_markets": 0,
            "rejections": {"missing_p34_matches_or_snapshots_table": 1},
        }

    try:
        source_schema = json.loads(source_schema_path.read_text(encoding="utf-8"))
        provenance_contract = source_schema["required_provenance"]
        all_required_fields_present = bool(source_schema["all_required_fields_present"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {
            "status": "unavailable",
            "strict_complete_match_markets": 0,
            "rejections": {"missing_or_invalid_frozen_p34_source_schema": 1},
            "source_schema_error": type(exc).__name__,
        }

    matches = connection.execute(
        "SELECT match_id, issue, kickoff_ts FROM matches ORDER BY issue, match_idx, match_id"
    ).fetchall()
    issues = sorted({str(row["issue"]) for row in matches})
    rows_by_match: dict[str, sqlite3.Row] = {str(row["match_id"]): row for row in matches}
    season_counts = Counter(f"20{str(row['issue'])[:2]}" for row in matches if str(row["issue"])[:2].isdigit())

    complete_observations = 0
    clocked_pre_kickoff_observations = 0
    latest_leads: dict[str, float] = {}
    malformed_clock_rows = 0
    complete_by_issue: Counter[str] = Counter()
    pre_kickoff_observations_by_issue: Counter[str] = Counter()
    strict_matches: set[str] = set()
    strict_by_issue: Counter[str] = Counter()
    missing_provenance_by_issue: Counter[str] = Counter()
    invalid_provenance_clock_by_issue: Counter[str] = Counter()
    for row in connection.execute(
        "SELECT match_id, snapshot_ts, sp_3, sp_1, sp_0, source_observed_at, fetched_at, raw_batch_id, immutable_bundle_sha256 "
        "FROM snapshots ORDER BY match_id, snapshot_ts"
    ):
        prices = (row["sp_3"], row["sp_1"], row["sp_0"])
        if not all(isinstance(price, (int, float)) and math.isfinite(float(price)) and float(price) > 1 for price in prices):
            continue
        complete_observations += 1
        match = rows_by_match.get(str(row["match_id"]))
        if match is None:
            malformed_clock_rows += 1
            continue
        complete_by_issue[str(match["issue"])] += 1
        snapshot_at = _parse_utc(str(row["snapshot_ts"]))
        kickoff_at = _parse_utc(str(match["kickoff_ts"]), naive_timezone=HKT)
        if snapshot_at is None or kickoff_at is None:
            malformed_clock_rows += 1
            continue
        if snapshot_at >= kickoff_at:
            continue
        clocked_pre_kickoff_observations += 1
        pre_kickoff_observations_by_issue[str(match["issue"])] += 1
        lead_minutes = (kickoff_at - snapshot_at).total_seconds() / 60
        match_id = str(row["match_id"])
        previous = latest_leads.get(match_id)
        if previous is None or lead_minutes < previous:
            latest_leads[match_id] = lead_minutes

        issue = str(match["issue"])
        values = (row["source_observed_at"], row["fetched_at"], row["raw_batch_id"], row["immutable_bundle_sha256"])
        if not all_required_fields_present or not all(_nonempty(value) for value in values):
            missing_provenance_by_issue[issue] += 1
            continue
        source_at = _parse_utc(str(row["source_observed_at"]), naive_timezone=HKT)
        fetched_at = _parse_utc(str(row["fetched_at"]), naive_timezone=HKT)
        if source_at is None or fetched_at is None or source_at > fetched_at or fetched_at > snapshot_at:
            invalid_provenance_clock_by_issue[issue] += 1
            continue
        if match_id not in strict_matches:
            strict_matches.add(match_id)
            strict_by_issue[issue] += 1

    leads = list(latest_leads.values())
    pre_kickoff_matches_by_issue = Counter(str(rows_by_match[match_id]["issue"]) for match_id in latest_leads)
    schema_missing_fields = [
        role for role, details in provenance_contract.items()
        if not isinstance(details, dict) or not details.get("available_in_source_schema")
    ]
    strict_status = "available_strict_provenance" if strict_matches else "partial_no_immutable_provenance"
    return {
        "status": strict_status,
        "issues": len(issues),
        "match_markets": len(matches),
        "by_season": dict(sorted(season_counts.items())),
        "by_issue": [
            {
                "issue": issue,
                "match_markets": sum(1 for row in matches if str(row["issue"]) == issue),
                "complete_vector_observations": complete_by_issue[issue],
                "clocked_pre_kickoff_observations": pre_kickoff_observations_by_issue[issue],
                "clocked_pre_kickoff_match_markets": pre_kickoff_matches_by_issue[issue],
                "strict_complete_match_markets": strict_by_issue[issue],
                "missing_immutable_raw_bundle_provenance": missing_provenance_by_issue[issue],
                "missing_source_and_fetch_dual_clock": missing_provenance_by_issue[issue] + invalid_provenance_clock_by_issue[issue],
                "invalid_provenance_clock_order": invalid_provenance_clock_by_issue[issue],
            }
            for issue in issues
        ],
        "complete_vector_observations": complete_observations,
        "clocked_pre_kickoff_observations": clocked_pre_kickoff_observations,
        "clocked_pre_kickoff_match_markets": len(latest_leads),
        "strict_complete_match_markets": len(strict_matches),
        "lead_minutes_latest_eligible_snapshot": {
            "p50": round(median(leads), 6) if leads else None,
            "p95": _percentile(leads, 0.95),
            "max": round(max(leads), 6) if leads else None,
        },
        "rejections": {
            "required_provenance_fields_absent_from_source_schema": len(schema_missing_fields),
            "missing_immutable_raw_bundle_provenance": sum(missing_provenance_by_issue.values()),
            "missing_source_and_fetch_dual_clock": sum(missing_provenance_by_issue.values()) + sum(invalid_provenance_clock_by_issue.values()),
            "invalid_provenance_clock_order": sum(invalid_provenance_clock_by_issue.values()),
            "post_kickoff_or_unparseable_complete_observation": complete_observations
            - clocked_pre_kickoff_observations,
            "match_mapping_or_clock_missing": malformed_clock_rows,
        },
        "notes": [
            "The frozen p34 source-schema inventory was captured from the same read transaction as the exported rows.",
            "Strict p34 evidence requires source-observed and fetch clocks, a raw batch ID, immutable bundle hash, and source <= fetch <= decision < kickoff.",
        ],
        "source_schema": {
            "all_required_fields_present": all_required_fields_present,
            "missing_required_fields": schema_missing_fields,
            "required_provenance": provenance_contract,
        },
    }


def _p42_frozen_coverage(freeze_root: Path, p0_connection: sqlite3.Connection) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    invalid_packages: list[dict[str, str]] = []
    root = freeze_root.resolve()
    if not root.is_dir():
        return {
            "status": "unavailable",
            "strict_complete_match_markets": 0,
            "exact_tail_mapping_match_markets": 0,
            "packages": [],
            "rejections": {"segment_freeze_root_missing": 1},
        }

    handicap_lines: dict[tuple[str, int], float | None] = {}
    if _table_exists(p0_connection, "matches"):
        for row in p0_connection.execute("SELECT issue, match_idx, handicap_line FROM matches"):
            value = row["handicap_line"]
            handicap_lines[(str(row["issue"]), int(row["match_idx"]))] = float(value) if value is not None else None

    complete_count = 0
    exact_tail_count = 0
    issues: set[str] = set()
    for manifest_path in sorted(root.rglob("manifest.json")):
        package = manifest_path.parent
        # The root also contains a binding/attempt ledger.  Those manifests are
        # evidence *about* a segment package, not segment packages themselves.
        if not (package / "frozen_outcomes.csv").is_file():
            continue
        try:
            verified = verify_segment_freeze(package)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError, MultimarketP0Error) as exc:
            invalid_packages.append({"path": str(package), "reason": type(exc).__name__})
            continue
        if 42 not in manifest.get("target_playids", []):
            continue
        by_match: dict[int, list[dict[str, str]]] = defaultdict(list)
        with (package / "frozen_outcomes.csv").open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("playid") == "42":
                    by_match[int(row["match_idx"])].append(row)
        complete_matches = 0
        exact_tail_matches = 0
        for match_idx, rows in by_match.items():
            codes = {row.get("outcome_code") for row in rows}
            valid_prices = all(
                _is_finite_price(row.get("sp", ""))
                and row.get("sale_status") == "open"
                and row.get("capture_classification") == "forward_complete_open"
                for row in rows
            )
            if len(rows) == 25 and len(codes) == 25 and valid_prices:
                complete_matches += 1
                # The three p42 other-score categories are exactly mappable only
                # at handicap zero.  For non-zero lines, at least one category
                # can straddle the adjusted-margin boundary and must remain an
                # interval/rejection in a later G2 mapper.
                if handicap_lines.get((str(manifest["issue"]), match_idx)) == 0.0:
                    exact_tail_matches += 1
        complete_count += complete_matches
        exact_tail_count += exact_tail_matches
        issues.add(str(manifest["issue"]))
        packages.append(
            {
                "frozen_input_package": package.name,
                "issue": str(manifest["issue"]),
                "segment_idx": int(manifest["segment_idx"]),
                "event_id": str(manifest["event_id"]),
                "freeze_at_hkt": str(manifest["effective_freeze_at_hkt"]),
                "sha256s_sha256": str(verified["sha256s_sha256"]),
                "strict_complete_p42_match_markets": complete_matches,
                "exact_tail_mapping_match_markets": exact_tail_matches,
            }
        )
    return {
        "status": "available" if packages else "unavailable",
        "issues": len(issues),
        "verified_packages": len(packages),
        "strict_complete_match_markets": complete_count,
        "exact_tail_mapping_match_markets": exact_tail_count,
        "packages": packages,
        "rejections": {"invalid_segment_freeze_package": len(invalid_packages)},
        "invalid_packages": invalid_packages,
        "notes": [
            "A p42 package is counted only after recursive segment-freeze verification.",
            "Complete p42 vectors with non-zero handicap are not point-mappable while other-score categories lack goal-difference detail.",
        ],
    }


def _is_finite_price(value: str) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) > 1
    except (TypeError, ValueError):
        return False


def _model_score_coverage(inventory_path: Path) -> dict[str, Any]:
    """Report inventory without asserting contract eligibility absent a validator."""

    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "unavailable",
            "strict_complete_match_markets": 0,
            "rejections": {"missing_or_invalid_frozen_model_inventory": 1},
            "inventory_error": type(exc).__name__,
        }
    eligibility = inventory.get("strict_eligibility")
    observations = inventory.get("inventory_observations", {})
    if not isinstance(eligibility, dict) or not isinstance(observations, dict):
        return {
            "status": "unavailable",
            "strict_complete_match_markets": 0,
            "rejections": {"malformed_frozen_model_inventory": 1},
        }
    return {
        "status": str(eligibility.get("status") or "UNKNOWN_NOT_EVALUATED"),
        "strict_complete_match_markets": None,
        "candidate_table_or_view_count": len(inventory.get("scanned_p0_schema_candidates", [])),
        "candidate_file_count": sum(1 for item in inventory.get("scanned_file_candidates", []) if "path" in item),
        "eligibility_reason": str(eligibility.get("reason") or ""),
        "inventory_observations": observations,
        "inventory_sha256_bound": True,
    }


def run_g0_coverage_audit(
    *, p34_db: Path, p34_source_schema: Path, p0_db: Path, p42_freeze_root: Path, model_inventory: Path, input_fingerprints: Path, audit_at_utc: str
) -> dict[str, Any]:
    """Return a deterministic, outcome-blind G0 coverage report.

    The report intentionally declares formal comparison unauthorised whenever
    either strict p34 coverage or a strict paired score source is absent.
    """

    audit_at = _parse_utc(audit_at_utc)
    if audit_at is None:
        raise ValueError("audit_at_utc must be an explicit ISO-8601 timestamp")
    p34_path = p34_db.resolve()
    p0_path = p0_db.resolve()
    if not p34_path.is_file() or not p34_source_schema.is_file() or not p0_path.is_file() or not model_inventory.is_file() or not input_fingerprints.is_file():
        raise FileNotFoundError("G0 requires complete atomic p34/p0/model input snapshots")

    p34_connection = _read_only_connection(p34_path)
    p0_connection = _read_only_connection(p0_path)
    try:
        p34 = _p34_coverage(p34_connection, p34_source_schema)
        p42 = _p42_frozen_coverage(p42_freeze_root, p0_connection)
    finally:
        p34_connection.close()
        p0_connection.close()

    denominator = int(p34.get("match_markets", 0))
    strict_p34 = int(p34.get("strict_complete_match_markets", 0))
    strict_p42 = int(p42.get("strict_complete_match_markets", 0))
    # There is deliberately no join against approximate/legacy p34 or p42
    # rows.  A common immutable same-decision-time identity is mandatory.
    paired_p34_p42 = 0
    model_score = _model_score_coverage(model_inventory)
    paired_p34_model = 0
    eligibility_reasons = []
    if strict_p34 == 0:
        eligibility_reasons.append("no_strict_p34_asof_provenance")
    if strict_p42 == 0:
        eligibility_reasons.append("no_strict_p42_complete_market")
    if model_score["status"] == "UNKNOWN_NOT_EVALUATED":
        eligibility_reasons.append("model_score_contract_not_evaluated")
    if paired_p34_p42 == 0 and paired_p34_model == 0:
        eligibility_reasons.append("no_strict_common_decision_time_pairs")

    return {
        "schema_version": G0_CONFIG_VERSION,
        "experiment_id": "SP-CONSISTENCY-001A",
        "stage": "G0",
        "audit_at_utc": audit_at.isoformat(timespec="seconds"),
        "outcomes_loaded": False,
        "query_audit": {
            "p34_columns": [
                "matches.match_id", "matches.issue", "matches.match_idx", "matches.kickoff_ts",
                "snapshots.match_id", "snapshots.snapshot_ts", "snapshots.sp_3", "snapshots.sp_1", "snapshots.sp_0",
                "snapshots.source_observed_at", "snapshots.fetched_at", "snapshots.raw_batch_id",
                "snapshots.immutable_bundle_sha256", "p34_source_schema.json",
            ],
            "p0_columns": ["matches.issue", "matches.match_idx", "matches.handicap_line"],
            "prohibited_tables_or_columns": ["settlements", "result_code", "fthg", "ftag", "winning_sp", "score"],
            "outcome_accessed": False,
        },
        "data_sources": json.loads(input_fingerprints.read_text(encoding="utf-8")),
        "coverage": {
            "p34": p34,
            "model_score": model_score,
            "p42": p42,
            "paired": {
                "denominator_p34_match_markets": denominator,
                "p34_model_same_decision_time": None,
                "p34_p42_same_decision_time": paired_p34_p42,
                "strict_pair_rate": None,
                "model_score_pairing_status": "UNKNOWN_NOT_EVALUATED",
            },
        },
        "preregistered_thresholds": {
            "min_strict_paired_rows": MIN_STRICT_PAIRED_ROWS,
            "min_strict_paired_issues": MIN_STRICT_PAIRED_ISSUES,
            "requires_common_immutable_decision_time": True,
            "requires_pre_kickoff_dual_clock": True,
        },
        "gate": {
            "status": "INSUFFICIENT_STRICT_DATA" if eligibility_reasons else "READY_FOR_G1_G2_REVIEW",
            "formal_comparison_authorized": False,
            "reasons": eligibility_reasons,
            "next_permitted_action": "publish G0 readiness evidence only; do not run Stage A or Stage B",
        },
    }
