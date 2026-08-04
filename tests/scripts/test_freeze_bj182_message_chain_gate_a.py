from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
CORE_SCRIPT = ROOT / "scripts" / "bj182_message_decision_core.py"
FREEZE_SCRIPT = ROOT / "scripts" / "freeze_bj182_message_chain_gate_a.py"
SCHEMA = ROOT / "schemas" / "bj182_message_decision_trace_v1.schema.json"
PACKAGE = ROOT / "results" / "bj182_gate_a_forward_protocol_v1"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CORE = load(CORE_SCRIPT, "bj182_message_decision_core")
FREEZE = load(FREEZE_SCRIPT, "freeze_bj182_message_chain_gate_a")


@pytest.fixture
def tmp_path():
    scratch = ROOT / ".scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bj182-test-", dir=scratch) as directory:
        yield Path(directory)


def coverage(*, match_id="m1", required_fact_kinds=None, **overrides):
    row = {
        "match_id": match_id,
        "kickoff_at_utc": "2026-08-05T12:00:00.000000Z",
        "required_fact_kinds": required_fact_kinds or ["injury"],
        "cutoff_strictly_before_kickoff": True,
        "missing_fact_kinds": [],
        "incomplete_observation_fact_kinds": [],
        "stale_observation_fact_kinds": [],
        "stale_fact_kinds": [],
        "uncovered_entity_ids_by_kind": {},
        "explicit_missing_fact_kinds": [],
        "unresolved_conflict_fact_ids": [],
        "decision_chain_eligible": True,
    }
    row.update(overrides)
    return row


def fact(**overrides):
    row = {
        "fact_id": "a" * 64,
        "fact_kind": "injury",
        "entity_id": "home",
        "active": True,
        "assertion_state": "affirmed",
        "conflicts_with": [],
        "provenance_tier": "TIER_0_OFFICIAL",
        "confidence": 0.9,
        "raw_sha256": "b" * 64,
        "effective_cutoff_utc": "2026-08-05T02:00:00Z",
        "value": {
            "availability": "AVAILABLE",
            "role_class": "KEY_STARTER",
            "severity": "LOW",
            "direction": "NO_DIRECTION",
        },
    }
    row.update(overrides)
    return row


def all_coverage(match_id="m1"):
    return {
        kind: coverage(match_id=match_id, required_fact_kinds=[kind])
        for kind in CORE.REQUIRED_KIND_MAX_AGE_SECONDS
    }


def clear_assessment(match_id: str):
    return {
        "match_id": match_id,
        "kickoff_ts_utc": "2026-08-05T12:00:00.000000Z",
        "decision_status": "ELIGIBLE",
        "risk_flag": "CLEAR",
        "protection_action": "KEEP_BASELINE_ORDER",
    }


def candidate(rank: int, match_ids: list[str]):
    return {
        "source_rank": rank,
        "portfolio_id": f"p{rank}",
        "identity_fingerprint": f"i{rank}",
        "selected_match_ids": match_ids,
        "b0_score": 100.0 - rank,
    }


def create_runtime_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE matches (
            issue TEXT NOT NULL,
            match_id TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            kickoff_ts TEXT NOT NULL,
            league TEXT NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            handicap_line REAL,
            created_ts TEXT NOT NULL,
            fthg INTEGER,
            ftag INTEGER,
            final_sp TEXT
        )
        """
    )
    for issue, count in (("26081", 2), ("26082", 1)):
        for index in range(1, count + 1):
            connection.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    issue,
                    f"{issue}-m{index}",
                    index,
                    f"2026-08-0{index + 4}T12:00:00Z",
                    "L1",
                    f"H{index}",
                    f"A{index}",
                    -0.5,
                    "2026-08-04T03:00:00Z",
                    index,
                    0,
                    "1.1|2.2|3.3",
                ),
            )
    connection.commit()
    connection.close()


def test_fail_closed_coverage_and_symmetric_risk_translation():
    missing = all_coverage()
    missing["expected_lineup"] = coverage(
        required_fact_kinds=["expected_lineup"],
        missing_fact_kinds=["expected_lineup"], decision_chain_eligible=False
    )
    blocked = CORE.assess_match(
        match_id="m1",
        kickoff_ts_utc="2026-08-05T12:00:00Z",
        home_team_id="home",
        away_team_id="away",
        coverage_by_kind=missing,
        facts=[],
    )
    assert blocked["decision_status"] == "ABSTAIN"
    assert blocked["risk_flag"] == "NOT_EVALUATED"
    assert "MISSING_REQUIRED_FACT" in blocked["error_codes"]

    swapped = all_coverage()
    swapped["injury"] = coverage(match_id="wrong", required_fact_kinds=["injury"])
    mismatched = CORE.assess_match(
        match_id="m1",
        kickoff_ts_utc="2026-08-05T12:00:00Z",
        home_team_id="home",
        away_team_id="away",
        coverage_by_kind=swapped,
        facts=[],
    )
    assert mismatched["decision_status"] == "ABSTAIN"
    assert "COVERAGE_REPORT_IDENTITY_MISMATCH" in mismatched["error_codes"]

    high = fact(
        value={
            "availability": "UNAVAILABLE",
            "role_class": "KEY_GOALKEEPER",
            "severity": "HIGH",
            "direction": "HOME_NEGATIVE",
        }
    )
    assessed = CORE.assess_match(
        match_id="m1",
        kickoff_ts_utc="2026-08-05T12:00:00Z",
        home_team_id="home",
        away_team_id="away",
        coverage_by_kind=all_coverage(),
        facts=[high],
    )
    assert assessed["decision_status"] == "ELIGIBLE"
    assert assessed["risk_flag"] == "HIGH"
    assert assessed["protection_action"] == "REJECT_IDENTITY"
    assert assessed["handicap_translation"] == "HOME_NEGATIVE"

    same_player = fact(
        fact_id="c" * 64,
        fact_kind="suspension",
        value={
            "availability": "UNAVAILABLE",
            "role_class": "STARTER",
            "severity": "MEDIUM",
            "direction": "HOME_NEGATIVE",
        },
    )
    duplicated = CORE.assess_match(
        match_id="m1",
        kickoff_ts_utc="2026-08-05T12:00:00Z",
        home_team_id="home",
        away_team_id="away",
        coverage_by_kind=all_coverage(),
        facts=[
            fact(
                value={
                    "availability": "UNAVAILABLE",
                    "role_class": "STARTER",
                    "severity": "MEDIUM",
                    "direction": "HOME_NEGATIVE",
                }
            ),
            same_player,
        ],
    )
    assert duplicated["risk_flag"] == "MEDIUM"
    assert duplicated["protection_action"] == "ANNOTATE_ONLY"


def test_message_selector_only_filters_the_exact_frozen_candidate_order():
    first = [f"m{i}" for i in range(1, 8)]
    second = [f"m{i}" for i in range(8, 15)]
    assessments = {match_id: clear_assessment(match_id) for match_id in first + second}
    assessments["m1"] = {
        **clear_assessment("m1"),
        "risk_flag": "HIGH",
        "protection_action": "REJECT_IDENTITY",
    }
    selected = CORE.select_message_identity(
        [candidate(1, first), candidate(2, second)], assessments
    )
    assert selected == {
        "policy_status": "SELECTED_PREOUTCOME",
        "selected_portfolio_id": "p2",
        "selected_identity_fingerprint": "i2",
        "selected_match_ids": second,
        "source_rank": 2,
    }
    with pytest.raises(CORE.DecisionContractError, match="seven unique"):
        CORE.select_message_identity(
            [candidate(1, ["m1"] * 7)], {"m1": clear_assessment("m1")}
        )


def test_nonfinite_confidence_and_candidate_scores_fail_closed():
    with pytest.raises(CORE.DecisionContractError, match="finite and between"):
        CORE.consumer_confidence_band(fact(confidence=float("nan")))
    rows = [candidate(1, [f"m{i}" for i in range(1, 8)])]
    rows[0]["b0_score"] = float("inf")
    with pytest.raises(CORE.DecisionContractError, match="b0_score must be finite"):
        CORE.validate_frozen_candidate_order(rows)


def test_runtime_snapshot_ignores_outcomes_and_excludes_preprotocol_issues(tmp_path):
    database = tmp_path / "beidan_live.db"
    create_runtime_db(database)
    before = FREEZE.snapshot_runtime(database)
    connection = sqlite3.connect(database)
    connection.execute("UPDATE matches SET fthg=99, ftag=98, final_sp='OUTCOME-DRIFT'")
    connection.commit()
    connection.close()
    after = FREEZE.snapshot_runtime(database)
    assert before["projection_sha256"] == after["projection_sha256"]
    assert after["minimum_issue_exclusive"] == 26082
    assert [row["issue"] for row in after["existing_post_26079_issues"]] == [
        "26081",
        "26082",
    ]
    assert all(
        row["disposition"] == "EXCLUDED_PRE_PROTOCOL"
        for row in after["existing_post_26079_issues"]
    )
    assert not ({"fthg", "ftag", "final_sp"} & set(after["projection"]))


def test_accepted_source_bindings_are_exact_and_fail_closed(monkeypatch, tmp_path):
    FREEZE.verify_accepted_sources()
    drift = tmp_path / "ledger.py"
    drift.write_text("drift\n", encoding="utf-8")
    monkeypatch.setattr(FREEZE, "SOURCE_181_LEDGER", drift)
    with pytest.raises(RuntimeError, match="accepted source hash drift"):
        FREEZE.verify_accepted_sources()


def test_package_build_is_atomic_deterministic_and_manifest_complete(tmp_path):
    database = tmp_path / "beidan_live.db"
    create_runtime_db(database)
    first = tmp_path / "package-a"
    second = tmp_path / "package-b"
    checked = "2026-08-04T19:30:00+08:00"
    receipt = FREEZE.build(
        output=first, runtime_db=database, availability_checked_at_utc=checked
    )
    FREEZE.build(
        output=second, runtime_db=database, availability_checked_at_utc=checked
    )
    assert receipt["minimum_issue_exclusive"] == 26082
    assert receipt["sample_status"] == "WAITING_FOR_POST_ACTIVATION_INPUT"
    assert sorted(path.name for path in first.iterdir()) == sorted(
        path.name for path in second.iterdir()
    )
    assert all(
        (first / path.name).read_bytes() == (second / path.name).read_bytes()
        for path in first.iterdir()
    )
    replay = tmp_path / "package-replayed"
    completed = subprocess.run(
        [
            sys.executable,
            str(first / "freeze_runner.py"),
            "--runtime-db",
            str(database),
            "--availability-checked-at",
            checked,
            "--output",
            str(replay),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout)["manifest_sha256"] == receipt[
        "manifest_sha256"
    ]
    assert not (first / "__pycache__").exists()
    assert all(
        (first / path.name).read_bytes() == (replay / path.name).read_bytes()
        for path in first.iterdir()
    )
    availability = json.loads((first / "availability_receipt.json").read_text())
    assert availability["availability_checked_at_utc"] == "2026-08-04T11:30:00Z"
    assert availability["message_ledger_database_status"] == "ABSENT_AT_GATE_A_FREEZE"
    assert availability["sample_status"] == "WAITING_FOR_POST_ACTIVATION_INPUT"
    card = json.loads((first / "gate_a_card.json").read_text())
    assert card["outcome_accessed"] is False
    assert card["historical_message_backfill_permitted"] is False
    assert card["cross_field_validator"] == "decision_core.validate_decision_trace"
    with (first / "error_taxonomy.csv").open(newline="", encoding="utf-8") as handle:
        taxonomy = {row["code"] for row in csv.DictReader(handle)}
    assert {
        "CUTOFF_NOT_BEFORE_KICKOFF",
        "COVERAGE_REPORT_MISSING",
        "COVERAGE_REPORT_IDENTITY_MISMATCH",
        "COVERAGE_POLICY_MISMATCH",
        "COVERAGE_KICKOFF_MISMATCH",
        "COVERAGE_INELIGIBLE_OTHER",
        "MATCH_KICKOFF_INVALID",
        "MISSING_REQUIRED_FACT",
        "INCOMPLETE_COLLECTION",
        "STALE_EVIDENCE",
        "INCOMPLETE_ENTITY_COVERAGE",
        "EXPLICIT_MISSINGNESS",
        "UNRESOLVED_CONTRADICTION",
        "FACT_EXTRACTION_SCHEMA_INVALID",
    } <= taxonomy
    manifest = json.loads((first / "SHA256SUMS.json").read_text())
    assert sorted(manifest) == sorted(
        path.name
        for path in first.iterdir()
        if path.name != "SHA256SUMS.json"
    )
    assert all(
        hashlib.sha256((first / name).read_bytes()).hexdigest() == expected
        for name, expected in manifest.items()
    )
    with pytest.raises(RuntimeError, match="immutable output already exists"):
        FREEZE.build(
            output=first, runtime_db=database, availability_checked_at_utc=checked
        )
    assert not list(tmp_path.glob(".package-*.stage.*"))


def test_decision_trace_schema_requires_all_three_distinct_arms():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.FormatChecker()
    )
    matches = [f"m{i}" for i in range(1, 8)]
    selected = {
        "policy_status": "SELECTED_PREOUTCOME",
        "selected_portfolio_id": "1" * 64,
        "selected_identity_fingerprint": "2" * 64,
        "selected_match_ids": matches,
        "source_rank": 1,
        "planned_ticket_count": 2187,
        "planned_stake_yuan": 4374,
    }
    trace = {
        "schema_version": CORE.SCHEMA_VERSION,
        "contract": CORE.CONTRACT,
        "sample_id": "SAMPLE_1",
        "decision_id": "3" * 64,
        "issue": "26083",
        "freeze_ts_utc": "2026-08-05T01:00:00Z",
        "activation": {
            "gate_a_acceptance_url": "https://github.com/algotradinglife/beijing-lot/issues/182#issuecomment-1",
            "gate_a_acceptance_recorded_at_utc": "2026-08-04T12:00:00Z",
            "minimum_issue_exclusive": 26082,
        },
        "baseline": {
            "selector": "B0_BEST_FULL",
            "request_id": "request-1",
            "package_id": "4" * 64,
            "package_created_at_utc": "2026-08-05T00:10:00Z",
            "input_as_of_utc": "2026-08-05T00:00:00Z",
            "candidate_universe_sha256": "5" * 64,
            "candidate_order": [
                {
                    "source_rank": 1,
                    "portfolio_id": "1" * 64,
                    "identity_fingerprint": "2" * 64,
                    "selected_match_ids": matches,
                    "b0_score": 1.0,
                }
            ],
            "selected_portfolio_id": "1" * 64,
            "selected_identity_fingerprint": "2" * 64,
            "selected_match_ids": matches,
            "planned_ticket_count": 2187,
            "planned_stake_yuan": 4374,
        },
        "evidence": {
            "ledger_schema_version": "message_evidence_ledger_v1",
            "as_of_export_sha256": "6" * 64,
            "coverage_report_sha256_by_kind": {
                kind: hashlib.sha256(kind.encode()).hexdigest()
                for kind in CORE.REQUIRED_KIND_MAX_AGE_SECONDS
            },
            "cutoff_ts_utc": "2026-08-05T00:30:00Z",
            "max_receipt_sequence": 1,
            "latest_receipt_recorded_at_utc": "2026-08-05T00:20:00Z",
            "allowed_provenance_tiers": list(CORE.ALLOWED_PROVENANCE_TIERS),
            "required_kind_max_age_seconds": CORE.REQUIRED_KIND_MAX_AGE_SECONDS,
        },
        "match_assessments": [
            {
                "match_id": match_id,
                "kickoff_ts_utc": "2026-08-05T12:00:00.000000Z",
                "decision_status": "ELIGIBLE",
                "risk_flag": "CLEAR",
                "protection_action": "KEEP_BASELINE_ORDER",
                "handicap_translation": "NO_CHANGE",
                "error_codes": [],
                "fact_ids": [],
                "extractions": [],
            }
            for match_id in matches
        ],
        "arms": [
            {"arm": "B0_BASELINE_SHADOW", "role": "CONTROLLING_BASELINE", **selected},
            {"arm": "M0_MESSAGE_ANNOTATION", "role": "DIAGNOSTIC", **selected},
            {"arm": "M1_MESSAGE_RISK_RERANK", "role": "PRIMARY_CHALLENGER", **selected},
        ],
        "audit": {
            "outcome_accessed": False,
            "probability_retuned": False,
            "selector_retuned": False,
            "allocator_changed": False,
            "ticket_economics_changed": False,
            "source_hashes": {
                **CORE.FROZEN_SOURCE_HASHES,
                "baseline_package_sha256": "4" * 64,
                "as_of_export_sha256": "6" * 64,
            },
        },
    }
    trace = CORE.build_decision_trace(trace)
    validator.validate(trace)
    CORE.validate_decision_trace(trace)

    old_issue = json.loads(json.dumps(trace))
    old_issue["issue"] = "26081"
    old_issue["decision_id"] = CORE.compute_decision_id(old_issue)
    with pytest.raises(CORE.DecisionContractError, match="activation boundary"):
        CORE.validate_decision_trace(old_issue)

    pre_activation_freeze = json.loads(json.dumps(trace))
    pre_activation_freeze["freeze_ts_utc"] = "2026-08-04T11:59:59Z"
    pre_activation_freeze["decision_id"] = CORE.compute_decision_id(
        pre_activation_freeze
    )
    with pytest.raises(CORE.DecisionContractError, match="activation and freeze"):
        CORE.validate_decision_trace(pre_activation_freeze)

    drift = json.loads(json.dumps(trace))
    drift["baseline"]["selected_portfolio_id"] = "8" * 64
    drift["decision_id"] = CORE.compute_decision_id(drift)
    with pytest.raises(CORE.DecisionContractError, match="candidate rank 1"):
        CORE.validate_decision_trace(drift)

    swapped_roles = json.loads(json.dumps(trace))
    swapped_roles["arms"][0]["role"], swapped_roles["arms"][2]["role"] = (
        swapped_roles["arms"][2]["role"],
        swapped_roles["arms"][0]["role"],
    )
    swapped_roles["decision_id"] = CORE.compute_decision_id(swapped_roles)
    with pytest.raises(CORE.DecisionContractError, match="frozen policy output"):
        CORE.validate_decision_trace(swapped_roles)

    zero_selected = json.loads(json.dumps(trace))
    zero_selected["arms"][2]["planned_ticket_count"] = 0
    zero_selected["arms"][2]["planned_stake_yuan"] = 0
    zero_selected["decision_id"] = CORE.compute_decision_id(zero_selected)
    with pytest.raises(CORE.DecisionContractError, match="frozen policy output"):
        CORE.validate_decision_trace(zero_selected)

    fake_coverage = json.loads(json.dumps(trace))
    fake_coverage["evidence"]["coverage_report_sha256_by_kind"] = {
        f"fake_{index}": hashlib.sha256(str(index).encode()).hexdigest()
        for index in range(5)
    }
    fake_coverage["decision_id"] = CORE.compute_decision_id(fake_coverage)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(fake_coverage)
    with pytest.raises(CORE.DecisionContractError, match="required fact kinds"):
        CORE.validate_decision_trace(fake_coverage)

    arbitrary_id = json.loads(json.dumps(trace))
    arbitrary_id["decision_id"] = "a" * 64
    with pytest.raises(CORE.DecisionContractError, match="canonical trace content hash"):
        CORE.validate_decision_trace(arbitrary_id)

    early = json.loads(json.dumps(trace))
    early["baseline"]["package_created_at_utc"] = "2026-08-04T11:59:59Z"
    early["decision_id"] = CORE.compute_decision_id(early)
    with pytest.raises(CORE.DecisionContractError, match="activation and freeze"):
        CORE.validate_decision_trace(early)
    hindsight = json.loads(json.dumps(trace))
    hindsight["match_assessments"][0]["kickoff_ts_utc"] = "2026-08-05T00:59:59Z"
    hindsight["decision_id"] = CORE.compute_decision_id(hindsight)
    with pytest.raises(CORE.DecisionContractError, match="strictly before"):
        CORE.validate_decision_trace(hindsight)
    incomplete = json.loads(json.dumps(trace))
    incomplete["match_assessments"].pop()
    incomplete["decision_id"] = CORE.compute_decision_id(incomplete)
    with pytest.raises(CORE.DecisionContractError, match="candidate match universe"):
        CORE.validate_decision_trace(incomplete)
    unhashed = json.loads(json.dumps(trace))
    unhashed["audit"]["source_hashes"]["source_181_ledger_sha256"] = "9" * 64
    unhashed["decision_id"] = CORE.compute_decision_id(unhashed)
    with pytest.raises(CORE.DecisionContractError, match="source hash mismatch"):
        CORE.validate_decision_trace(unhashed)
    trace["arms"][2] = dict(trace["arms"][1])
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(trace)


def test_formal_package_manifest_if_present():
    if not PACKAGE.is_dir():
        pytest.skip("formal package not generated yet")
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    assert all(
        hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
        for name, expected in manifest.items()
    )
    availability = json.loads((PACKAGE / "availability_receipt.json").read_text())
    assert availability["sample_status"] == "WAITING_FOR_POST_ACTIVATION_INPUT"
    assert availability["minimum_issue_exclusive"] >= 26082
