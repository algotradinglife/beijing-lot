#!/usr/bin/env python3
"""Freeze #182's outcome-unexposed message-chain forward protocol."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

sys.dont_write_bytecode = True

try:
    from bj182_message_decision_core import (
        ALLOWED_PROVENANCE_TIERS,
        CONTRACT,
        OPTIONAL_FACT_KINDS,
        REQUIRED_KIND_MAX_AGE_SECONDS,
        SCHEMA_VERSION,
        canonical_json,
    )
except ModuleNotFoundError:  # Immutable package uses the shorter copied filename.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from decision_core import (  # type: ignore[no-redef]
        ALLOWED_PROVENANCE_TIERS,
        CONTRACT,
        OPTIONAL_FACT_KINDS,
        REQUIRED_KIND_MAX_AGE_SECONDS,
        SCHEMA_VERSION,
        canonical_json,
    )


VERSION = "bj182-gate-a-forward-protocol-v1"
PREVIOUS_MAX_PROSPECTIVE_ISSUE = 26079
FULL_TICKETS = 2187
STAKE_PER_TICKET_YUAN = 2
FULL_STAKE_YUAN = 4374

SOURCE_181_MERGE = "4e186db4f293e04429898d4077f823e0d0efa62a"
SOURCE_181_LEDGER_SHA = "3c065be028c4022d33487095f08b9838c284853614f6617646dabe5e08c31229"
SOURCE_181_ASOF_SCHEMA_SHA = "e763428d703197ec08eb2c4955ee45bc9925c84941bed8f3a9ac253edec161bd"
SOURCE_181_COVERAGE_SCHEMA_SHA = "22ffbaf6ef79eb484425c48307a29c08ba73d6a0bbf743e4023b37838ed9181d"
SOURCE_180_MERGE = "a662a6efaeed1f9fdbee95575a346dd6813cdb12"
SOURCE_180_GATE_B_MANIFEST = "9f48b29325d817ce873bd1430be459c9e70ad052064f8e03e02ccbc1d8bc6fcf"
SOURCE_180_GATE_B_CONTENT = "d9b41dec45c1c6215755d9dad8774e00fc0f19f564ee6ef8bf2387cb8d309108"


def repo_root() -> Path:
    source = Path(__file__).resolve()
    cwd = Path.cwd().resolve()
    candidates = list(source.parents) + [cwd, *cwd.parents]
    for candidate in dict.fromkeys(candidates):
        if (candidate / "src" / "message_evidence" / "ledger.py").is_file():
            return candidate
    raise RuntimeError(f"repository root unavailable from {source}")


ROOT = repo_root()
DEFAULT_OUTPUT = ROOT / "results" / "bj182_gate_a_forward_protocol_v1"
DECISION_SCHEMA = ROOT / "schemas" / "bj182_message_decision_trace_v1.schema.json"
CORE_SOURCE = ROOT / "scripts" / "bj182_message_decision_core.py"
SOURCE_181_LEDGER = ROOT / "src" / "message_evidence" / "ledger.py"
SOURCE_181_ASOF_SCHEMA = ROOT / "schemas" / "message_evidence_asof_v1.schema.json"
SOURCE_181_COVERAGE_SCHEMA = (
    ROOT / "schemas" / "message_evidence_coverage_v1.schema.json"
)
SOURCE_180_PACKAGE = ROOT / "results" / "bj180_gate_b_team_matchup_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("availability timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_accepted_sources() -> None:
    expected_files = {
        SOURCE_181_LEDGER: SOURCE_181_LEDGER_SHA,
        SOURCE_181_ASOF_SCHEMA: SOURCE_181_ASOF_SCHEMA_SHA,
        SOURCE_181_COVERAGE_SCHEMA: SOURCE_181_COVERAGE_SCHEMA_SHA,
        SOURCE_180_PACKAGE / "SHA256SUMS.json": SOURCE_180_GATE_B_MANIFEST,
        SOURCE_180_PACKAGE / "CONTENT_IDENTITY.json": SOURCE_180_GATE_B_CONTENT,
    }
    for path, expected in expected_files.items():
        if not path.is_file():
            raise RuntimeError(f"accepted source unavailable: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"accepted source hash drift: {path}: expected {expected}, got {actual}"
            )
    source_manifest = json.loads(
        (SOURCE_180_PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8")
    )
    if not isinstance(source_manifest, dict):
        raise RuntimeError("#180 source manifest must be an object")
    for name, expected in source_manifest.items():
        path = SOURCE_180_PACKAGE / name
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"#180 source package payload drift: {name}")


def snapshot_runtime(database: Path) -> dict[str, object]:
    database = database.resolve()
    if not database.is_file():
        raise RuntimeError(f"runtime database unavailable: {database}")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(matches)")}
        required = {
            "issue", "match_id", "match_idx", "kickoff_ts", "league", "home",
            "away", "handicap_line", "created_ts",
        }
        if not required <= columns:
            raise RuntimeError(f"runtime matches projection drift: {sorted(required-columns)}")
        rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT issue, match_id, match_idx, kickoff_ts, league, home, away,
                       handicap_line, created_ts
                FROM matches
                WHERE CAST(issue AS INTEGER) > ?
                  AND CAST(issue AS INTEGER) BETWEEN 26000 AND 26999
                ORDER BY CAST(issue AS INTEGER), match_idx, match_id
                """,
                (PREVIOUS_MAX_PROSPECTIVE_ISSUE,),
            )
        ]
        data_version = int(connection.execute("PRAGMA data_version").fetchone()[0])
        connection.commit()
    finally:
        connection.close()
    if not rows:
        max_issue = PREVIOUS_MAX_PROSPECTIVE_ISSUE
    else:
        max_issue = max(int(str(row["issue"])) for row in rows)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["issue"]), []).append(row)
    issue_rows = []
    for issue in sorted(grouped, key=int):
        native = grouped[issue]
        issue_rows.append(
            {
                "issue": issue,
                "match_count": len(native),
                "first_kickoff_ts": min(str(row["kickoff_ts"]) for row in native),
                "last_kickoff_ts": max(str(row["kickoff_ts"]) for row in native),
                "first_created_ts": min(str(row["created_ts"]) for row in native),
                "last_created_ts": max(str(row["created_ts"]) for row in native),
                "disposition": "EXCLUDED_PRE_PROTOCOL",
            }
        )
    return {
        "database_path": "data/beidan_live.db",
        "database_mode": "READ_ONLY_WAL_SNAPSHOT",
        "sqlite_data_version": data_version,
        "projection": [
            "issue", "match_id", "match_idx", "kickoff_ts", "league", "home",
            "away", "handicap_line", "created_ts",
        ],
        "projection_row_count": len(rows),
        "projection_sha256": hashlib.sha256(canonical_json(rows)).hexdigest(),
        "existing_post_26079_issues": issue_rows,
        "minimum_issue_exclusive": max_issue,
    }


def forward_protocol(minimum_issue_exclusive: int) -> dict[str, object]:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "stage": "GATE_A_OUTCOME_UNEXPOSED_PROTOCOL",
        "activation": {
            "status": "PENDING_PI_GATE_A_ACCEPTANCE",
            "rule": "A sample is valid only after PI accepts and merges this exact Gate-A package.",
            "minimum_issue_exclusive": minimum_issue_exclusive,
            "baseline_created_after_acceptance_required": True,
            "evidence_receipts_after_acceptance_required": True,
            "preexisting_issues_may_not_be_relabelled": True,
        },
        "sample_selector": {
            "primary": "first integer issue strictly greater than minimum_issue_exclusive with a content-addressed B0 package and cutoff-safe message exports created after activation",
            "one_freeze_per_issue": True,
            "minimum_candidate_match_count": 7,
            "issue_id_reuse": False,
            "same_issue_regeneration_as_new_sample": False,
        },
        "baseline_contract": {
            "arm": "B0_BEST_FULL",
            "source": "externally supplied accepted outcome-unexposed B0 package for the target issue",
            "candidate_order": "frozen B0 score descending, portfolio_id ascending tie break",
            "required_identity": [
                "request_id", "package_id", "package_created_at_utc", "input_as_of_utc",
                "candidate_universe_sha256", "candidate_order",
                "selected_portfolio_id", "selected_identity_fingerprint",
                "selected_match_ids",
            ],
            "n": 7,
            "allocation": "FULL_ENUMERATED",
            "tickets": FULL_TICKETS,
            "stake_yuan": FULL_STAKE_YUAN,
            "missing_baseline": "FAIL_CLOSED_NO_SAMPLE",
        },
        "evidence_contract": {
            "consumer_api": "MessageEvidenceLedger.export_as_of plus one coverage report per required kind",
            "common_cutoff": "one timezone-aware cutoff shared by the issue decision; strictly before every selected match kickoff",
            "required_kind_max_age_seconds": REQUIRED_KIND_MAX_AGE_SECONDS,
            "optional_kinds": list(OPTIONAL_FACT_KINDS),
            "allowed_provenance_tiers": list(ALLOWED_PROVENANCE_TIERS),
            "tier_3_action": "AUDIT_ONLY_NOT_DECISION_ELIGIBLE",
            "unresolved_conflict_action": "ABSTAIN",
            "late_or_stale_action": "ABSTAIN",
            "incomplete_entity_or_collection_action": "ABSTAIN",
            "direct_sql_access_permitted": False,
            "latest_receipt_recorded_at_required": True,
        },
        "decision_chain": {
            "fact_extraction": "strict schema: availability, role_class, severity, direction; immutable fact/raw IDs retained",
            "confidence": "consumer HIGH/MEDIUM/LOW/NOT_ACTIONABLE from active state, contradiction state, producer confidence and provenance eligibility",
            "handicap_translation": "diagnostic direction only; probabilities and handicap line remain unchanged",
            "risk_rule": "HIGH rejects identities containing that match; MEDIUM annotates only; CLEAR keeps B0 order",
            "aggregation": "scan the exact frozen B0 candidate order and select the first fully covered identity without HIGH risk",
            "cross_field_validator": "decision_core.validate_decision_trace must pass before a decision trace is frozen",
            "decision_id": "SHA-256 of canonical trace JSON after removing only decision_id",
            "forbidden": [
                "probability retuning", "selector threshold retuning", "new candidates",
                "M changes", "allocator changes", "ticket changes", "stake scaling",
            ],
        },
        "arms": [
            "B0_BASELINE_SHADOW",
            "M0_MESSAGE_ANNOTATION",
            "M1_MESSAGE_RISK_RERANK",
        ],
        "participation_accounting": {
            "native": "report B0 on every valid baseline issue and message arms only when their policy selects",
            "matched": "restrict B0 and M1 to identical issue set; compare equal CNY4374 issue stakes",
            "coverage": "report ledger coverage, abstention and each error reason separately from selection lift",
            "no_bet": "zero executed tickets and zero stake; never a losing bet",
        },
        "forward_horizon": {
            "diagnostic_checkpoint": "5 matched message-eligible issues; descriptive only",
            "primary_checkpoint": "20 matched message-eligible issues and at least 30 post-activation calendar issues",
            "time_limit_days": 180,
            "insufficient_at_time_limit": "INSUFFICIENT_FORWARD_COVERAGE",
            "outcome_join_before_checkpoint": False,
            "retuning_between_samples": False,
        },
        "outcome_settlement": {
            "authorization": "SEPARATE_PI_GATE_REQUIRED",
            "pre_tax_primary": True,
            "tax_reference_only": True,
            "tax_rule": "per winning CNY2 ticket; no issue/person aggregation",
            "metrics": [
                "coverage", "abstention", "identity changes", "calibration",
                "stake", "gross payout", "pre-tax ROI", "matched lift",
                "YEAR/time block", "ex-largest issue", "HHI", "drawdown",
            ],
            "positive_claim": "strict independent EV plus further forward evidence required",
        },
        "outcome_boundary": "No score, result, final SP, winning SP, payout, tax, ROI or settlement data may enter Gate A or a decision freeze.",
        "production_authority": False,
    }


def package_identity(stage: Path, controls: dict[str, object]) -> tuple[str, str]:
    payloads = {
        path.name: sha256_file(path)
        for path in sorted(stage.iterdir())
        if path.is_file() and path.name not in {"CONTENT_IDENTITY.json", "SHA256SUMS.json"}
    }
    write_json(
        stage / "CONTENT_IDENTITY.json",
        {"contract_version": VERSION, "controls": controls, "payloads": payloads},
    )
    sums = {
        path.name: sha256_file(path)
        for path in sorted(stage.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    write_json(stage / "SHA256SUMS.json", sums)
    return sha256_file(stage / "SHA256SUMS.json"), sha256_file(stage / "CONTENT_IDENTITY.json")


def build(*, output: Path, runtime_db: Path, availability_checked_at_utc: str) -> dict[str, object]:
    checked_at = normalize_timestamp(availability_checked_at_utc)
    verify_accepted_sources()
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"immutable output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage.", dir=output.parent))
    try:
        runtime = snapshot_runtime(runtime_db)
        minimum_issue = int(runtime["minimum_issue_exclusive"])
        protocol = forward_protocol(minimum_issue)
        availability = {
            "availability_checked_at_utc": checked_at,
            **runtime,
            "message_ledger_database_status": "ABSENT_AT_GATE_A_FREEZE",
            "sample_status": "WAITING_FOR_POST_ACTIVATION_INPUT",
            "detail": "The accepted #181 ledger contract exists, but no operational message ledger or valid post-activation B0 package exists. Existing issues are excluded; no decision or outcome is fabricated.",
        }
        write_json(stage / "forward_protocol.json", protocol)
        write_json(stage / "availability_receipt.json", availability)
        shutil.copyfile(DECISION_SCHEMA, stage / "decision_trace.schema.json")
        shutil.copyfile(CORE_SOURCE, stage / "decision_core.py")

        arms = [
            {
                "arm": "B0_BASELINE_SHADOW", "role": "CONTROLLING_BASELINE",
                "participation": "ALL_VALID_BASELINE_ISSUES",
                "identity_rule": "exact B0 selected identity", "risk_action": "NONE",
                "allocation": "FULL_ENUMERATED", "tickets": FULL_TICKETS,
                "stake_yuan": FULL_STAKE_YUAN,
            },
            {
                "arm": "M0_MESSAGE_ANNOTATION", "role": "DIAGNOSTIC",
                "participation": "MESSAGE_COVERAGE_ELIGIBLE",
                "identity_rule": "exact B0 identity; annotations only", "risk_action": "ANNOTATE_ONLY",
                "allocation": "FULL_ENUMERATED", "tickets": FULL_TICKETS,
                "stake_yuan": FULL_STAKE_YUAN,
            },
            {
                "arm": "M1_MESSAGE_RISK_RERANK", "role": "PRIMARY_CHALLENGER",
                "participation": "MESSAGE_COVERAGE_ELIGIBLE",
                "identity_rule": "first exact B0-ranked candidate with complete evidence and no HIGH risk match",
                "risk_action": "FILTER_ONLY_NO_RESCORING",
                "allocation": "FULL_ENUMERATED", "tickets": FULL_TICKETS,
                "stake_yuan": FULL_STAKE_YUAN,
            },
        ]
        write_csv(stage / "arm_registry.csv", list(arms[0]), arms)
        evidence_rows = [
            {
                "fact_kind": kind,
                "required": 1,
                "max_age_seconds": age,
                "allowed_tiers": "|".join(ALLOWED_PROVENANCE_TIERS),
                "complete_both_team_observation_required": 1,
                "failure_action": "ABSTAIN_MESSAGE_ARMS",
            }
            for kind, age in REQUIRED_KIND_MAX_AGE_SECONDS.items()
        ] + [
            {
                "fact_kind": kind,
                "required": 0,
                "max_age_seconds": "",
                "allowed_tiers": "|".join(ALLOWED_PROVENANCE_TIERS),
                "complete_both_team_observation_required": 0,
                "failure_action": "RETAIN_EXPLICIT_MISSING_OPTIONAL",
            }
            for kind in OPTIONAL_FACT_KINDS
        ]
        write_csv(stage / "evidence_policy.csv", list(evidence_rows[0]), evidence_rows)
        errors = [
            ("BASELINE_PACKAGE_MISSING", "ISSUE", "NO_SAMPLE"),
            ("PRE_PROTOCOL_ISSUE", "ISSUE", "NO_SAMPLE"),
            ("CUTOFF_NOT_BEFORE_KICKOFF", "MATCH", "ABSTAIN"),
            ("COVERAGE_REPORT_MISSING", "MATCH", "ABSTAIN"),
            ("COVERAGE_REPORT_IDENTITY_MISMATCH", "MATCH", "ABSTAIN"),
            ("COVERAGE_POLICY_MISMATCH", "MATCH", "ABSTAIN"),
            ("COVERAGE_KICKOFF_MISMATCH", "MATCH", "ABSTAIN"),
            ("COVERAGE_INELIGIBLE_OTHER", "MATCH", "ABSTAIN"),
            ("MATCH_KICKOFF_INVALID", "MATCH", "ABSTAIN"),
            ("MISSING_REQUIRED_FACT", "MATCH", "ABSTAIN"),
            ("INCOMPLETE_COLLECTION", "MATCH", "ABSTAIN"),
            ("STALE_EVIDENCE", "MATCH", "ABSTAIN"),
            ("INCOMPLETE_ENTITY_COVERAGE", "MATCH", "ABSTAIN"),
            ("EXPLICIT_MISSINGNESS", "MATCH", "ABSTAIN"),
            ("UNRESOLVED_CONTRADICTION", "MATCH", "ABSTAIN"),
            ("FACT_EXTRACTION_SCHEMA_INVALID", "MATCH", "ABSTAIN"),
            ("NO_ELIGIBLE_IDENTITY", "ISSUE", "ABSTAIN"),
            ("LATE_CAPTURE", "FACT", "AUDIT_ONLY"),
        ]
        error_rows = [{"code": code, "scope": scope, "action": action} for code, scope, action in errors]
        write_csv(stage / "error_taxonomy.csv", list(error_rows[0]), error_rows)
        metrics = [
            ("coverage", "NATIVE", "coverage/eligible/abstain counts and reasons", "PREOUTCOME"),
            ("identity_change", "MATCHED", "M1 versus B0 identity changed", "PREOUTCOME"),
            ("probability_calibration", "MATCHED", "B0 probability LogLoss/Brier/reliability on selected legs", "POSTOUTCOME"),
            ("pre_tax_roi", "NATIVE_AND_MATCHED", "stake/gross/net/stake; B0 versus M1", "POSTOUTCOME"),
            ("risk", "NATIVE_AND_MATCHED", "HHI/ex-largest/drawdown/time blocks", "POSTOUTCOME"),
        ]
        metric_rows = [{"metric": a, "denominator": b, "definition": c, "stage": d} for a,b,c,d in metrics]
        write_csv(stage / "metric_contract.csv", list(metric_rows[0]), metric_rows)
        sample_rows = [{
            "sample_id": "SAMPLE_1", "status": "WAITING_FOR_POST_ACTIVATION_INPUT",
            "minimum_issue_exclusive": minimum_issue,
            "selector": "first valid issue after PI acceptance",
            "decision_count": 0, "outcome_count": 0,
        }]
        write_csv(stage / "sample_registry.csv", list(sample_rows[0]), sample_rows)

        source_binding = {
            "contract": CONTRACT,
            "version": VERSION,
            "source_181": {
                "merge_commit": SOURCE_181_MERGE,
                "ledger_path": "src/message_evidence/ledger.py",
                "ledger_sha256": SOURCE_181_LEDGER_SHA,
                "asof_schema_sha256": SOURCE_181_ASOF_SCHEMA_SHA,
                "coverage_schema_sha256": SOURCE_181_COVERAGE_SCHEMA_SHA,
                "disposition": "ACCEPTED_DATA_CONTRACT_ONLY",
            },
            "source_180": {
                "merge_commit": SOURCE_180_MERGE,
                "gate_b_package": "results/bj180_gate_b_team_matchup_v1",
                "gate_b_manifest_sha256": SOURCE_180_GATE_B_MANIFEST,
                "gate_b_content_identity_sha256": SOURCE_180_GATE_B_CONTENT,
                "disposition": "NO_TEAM_MODEL_PROMOTION_RETAIN_B0",
            },
            "runtime_availability": {
                "database_path": runtime["database_path"],
                "projection_sha256": runtime["projection_sha256"],
                "projection_row_count": runtime["projection_row_count"],
                "boundary": "OUTCOME_UNEXPOSED_ALLOWLIST_PROJECTION_ONLY",
            },
            "decision_schema_sha256": sha256_file(DECISION_SCHEMA),
            "decision_core_sha256": sha256_file(CORE_SOURCE),
        }
        write_json(stage / "source_binding.json", source_binding)
        gate_a_card = {
            "contract": CONTRACT,
            "version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_PROTOCOL",
            "status": "WAITING_FOR_PI_ACCEPTANCE_AND_POST_ACTIVATION_INPUT",
            "minimum_issue_exclusive": minimum_issue,
            "existing_issue_count_excluded": len(runtime["existing_post_26079_issues"]),
            "decision_trace_schema": "decision_trace.schema.json",
            "decision_schema_version": SCHEMA_VERSION,
            "cross_field_validator": "decision_core.validate_decision_trace",
            "arm_count": len(arms),
            "required_fact_kinds": list(REQUIRED_KIND_MAX_AGE_SECONDS),
            "optional_fact_kinds": list(OPTIONAL_FACT_KINDS),
            "full_tickets": FULL_TICKETS,
            "stake_per_ticket_yuan": STAKE_PER_TICKET_YUAN,
            "full_stake_yuan": FULL_STAKE_YUAN,
            "outcome_accessed": False,
            "historical_message_backfill_permitted": False,
            "retuning_permitted": False,
            "gate_b_authorized": False,
            "production_authority": False,
        }
        write_json(stage / "gate_a_card.json", gate_a_card)
        (stage / "README.md").write_text(
            "# #182 Gate A — outcome-unexposed forward message protocol\n\n"
            "This immutable package freezes the decision trace schema, evidence coverage, symmetric risk filter, arms, accounting, error taxonomy and forward horizon before any valid sample outcome. Existing issues at freeze time are explicitly excluded. No operational message ledger or valid post-activation sample existed at generation.\n",
            encoding="utf-8",
        )
        shutil.copyfile(Path(__file__), stage / "freeze_runner.py")
        controls = {
            "source_181_merge": SOURCE_181_MERGE,
            "source_180_merge": SOURCE_180_MERGE,
            "minimum_issue_exclusive": minimum_issue,
            "availability_checked_at_utc": checked_at,
            "arms": [row["arm"] for row in arms],
            "outcome_accessed": False,
            "retuning_permitted": False,
        }
        manifest_hash, content_hash = package_identity(stage, controls)
        os.rename(stage, output)
        return {
            "output": str(output),
            "manifest_sha256": manifest_hash,
            "content_identity_sha256": content_hash,
            "payload_count": len(json.loads((output / "SHA256SUMS.json").read_text())),
            "minimum_issue_exclusive": minimum_issue,
            "sample_status": "WAITING_FOR_POST_ACTIVATION_INPUT",
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-db", type=Path, required=True)
    parser.add_argument("--availability-checked-at", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(output=args.output, runtime_db=args.runtime_db, availability_checked_at_utc=args.availability_checked_at), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
