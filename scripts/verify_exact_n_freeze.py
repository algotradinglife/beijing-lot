#!/usr/bin/env python3
"""Semantic and cryptographic verifier for BJ-BET-FREEZE-001 packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

N_VALUES = (3, 4, 5, 6, 7)
BUDGETS = (512, 768, 1024)
EXPECTED_GRID = {(n, budget) for n in N_VALUES for budget in BUDGETS}
EXACT_STATUSES = {
    "FROZEN_EXACT_N_BUDGET",
    "UNAVAILABLE_EXACT_N_BUDGET",
}
SCORE_BUDGET_STATUS = "UNAVAILABLE_SCORE_STAKING_RULE"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    claimed = str(unsigned.pop("sha256", ""))
    actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
    if claimed != actual:
        raise ValueError("payload sha256 mismatch")
    return claimed


def _read_sums(root: Path) -> dict[str, str]:
    sums_path = root / "SHA256SUMS"
    if not sums_path.is_file():
        raise ValueError("SHA256SUMS missing")
    entries: dict[str, str] = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise ValueError("invalid SHA256SUMS line") from exc
        if (
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            or Path(name).is_absolute()
            or ".." in Path(name).parts
            or name in entries
        ):
            raise ValueError("invalid SHA256SUMS entry")
        entries[name] = digest
    actual_files = {
        path.name
        for path in root.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(entries) != actual_files:
        raise ValueError("SHA256SUMS does not bind the complete package file set")
    for name, digest in entries.items():
        if _file_hash(root / name) != digest:
            raise ValueError(f"SHA256SUMS mismatch: {name}")
    return entries


def verify_directory(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    sums = _read_sums(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest_hash = _payload_hash(manifest)
    if manifest.get("schema_version") != "exact_n_budget_matrix_freeze_v2":
        raise ValueError("unsupported package schema")

    files = sorted(root.glob("exact_n_*_budget_*.json"))
    if len(files) != 15:
        raise ValueError("expected 15 N×budget cells")
    common: tuple[Any, ...] | None = None
    grid: set[tuple[int, int]] = set()
    artifact_entries = {
        str(item.get("file")): item
        for item in manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        claimed = _payload_hash(payload)
        requested_n = int(payload["requested_n"])
        artifact_n = int(payload["artifact_n"])
        recommended_n = int(payload["recommended_n"])
        if not (requested_n == artifact_n and artifact_n == recommended_n):
            raise ValueError("semantic identity/N mismatch")
        budget = int(payload["requested_budget_yuan"])
        grid.add((requested_n, budget))
        if payload.get("status") not in EXACT_STATUSES:
            raise ValueError("invalid exact-N status vocabulary")
        if "actual_budget_yuan" in payload or "actual_cost_yuan" not in payload:
            raise ValueError("actual_cost_yuan contract field missing")
        actual_cost = float(payload["actual_cost_yuan"])
        base_cost = float(payload["base_cost_yuan"])
        if actual_cost < 0 or base_cost < 0 or actual_cost > budget:
            raise ValueError("budget exceeded or negative cost")
        if abs(float(payload["unused_budget_yuan"]) - (budget - actual_cost)) > 1e-6:
            raise ValueError("unused budget mismatch")
        tickets = payload.get("tickets")
        if not isinstance(tickets, list):
            raise ValueError("tickets must be a list")
        ticket_base_cost = 0.0
        ticket_actual_cost = 0.0
        segment_members = {int(value) for value in payload["segment_match_indices"]}
        for ticket in tickets:
            match_indices = [int(value) for value in ticket.get("match_indices", [])]
            leg_codes = [str(value) for value in ticket.get("leg_codes", [])]
            if (
                int(ticket.get("actual_n", -1)) != requested_n
                or len(match_indices) != requested_n
                or len(set(match_indices)) != requested_n
                or len(leg_codes) != requested_n
                or not set(match_indices).issubset(segment_members)
            ):
                raise ValueError("N=4→3, duplicate leg, or membership fallback")
            ticket_base = float(ticket.get("base_cost_yuan", -1))
            ticket_cost = float(ticket.get("cost_yuan", -1))
            if ticket_base <= 0 or ticket_cost <= 0:
                raise ValueError("ticket cost must be positive")
            ticket_base_cost += ticket_base
            ticket_actual_cost += ticket_cost
        if abs(ticket_base_cost - base_cost) > 1e-6:
            raise ValueError("base cost does not reconcile to ticket costs")
        if abs(ticket_actual_cost - actual_cost) > 1e-6:
            raise ValueError("actual cost does not reconcile to ticket costs")
        frozen = payload["status"] == "FROZEN_EXACT_N_BUDGET"
        if frozen != bool(tickets):
            raise ValueError("exact-N status/ticket consistency mismatch")
        if not frozen and (actual_cost != 0 or base_cost != 0):
            raise ValueError("unavailable exact-N cell has nonzero cost")
        if not str(payload.get("reason") or ""):
            raise ValueError("exact-N availability reason missing")
        expected_utilization = actual_cost / budget
        if (
            abs(float(payload.get("budget_utilization", -1)) - expected_utilization)
            > 1e-9
        ):
            raise ValueError("budget utilization mismatch")
        key = (
            payload["segment_match_indices"],
            payload["segment_manifest_sha256"],
            payload["decision_input_sha256"],
            payload["decision_input_manifest_sha256"],
            payload["scheduled_freeze_at"],
            payload["effective_decision_at"],
            payload["event_key"],
        )
        common = common or key
        if key != common:
            raise ValueError("15 cells do not share one frozen identity")
        entry = artifact_entries.get(path.name)
        if not entry or str(entry.get("sha256")) != claimed:
            raise ValueError(f"manifest artifact hash mismatch: {path.name}")
    if grid != EXPECTED_GRID:
        raise ValueError("exact 5×3 N/budget grid missing or duplicated")

    input_payload = json.loads(
        (root / "decision_input_manifest.json").read_text(encoding="utf-8")
    )
    input_hash = _payload_hash(input_payload)
    if input_hash != common[3]:
        raise ValueError("decision input manifest linkage mismatch")
    if input_payload.get("structured_csv_sha256") != common[2]:
        raise ValueError("decision input bytes linkage mismatch")
    if input_payload.get("segment_manifest_sha256") != common[1]:
        raise ValueError("decision input segment linkage mismatch")
    source_bytes = root / "structured_input.csv"
    source_receipt = json.loads(
        (root / "structured_input_receipt.json").read_text(encoding="utf-8")
    )
    receipt_hash = _payload_hash(source_receipt)
    if (
        _file_hash(source_bytes) != common[2]
        or source_receipt.get("structured_csv_sha256") != common[2]
        or input_payload.get("generator_receipt_sha256") != receipt_hash
        or int(source_receipt.get("structured_csv_size_bytes", -1))
        != source_bytes.stat().st_size
    ):
        raise ValueError("packaged decision input generation receipt mismatch")
    generated_at = datetime.fromisoformat(str(source_receipt["generated_at_utc"]))
    refresh_opens = datetime.fromisoformat(str(input_payload["final_refresh_opens_at"]))
    effective_at = datetime.fromisoformat(str(input_payload["effective_decision_at"]))
    if (
        generated_at.tzinfo is None
        or refresh_opens.tzinfo is None
        or effective_at.tzinfo is None
        or not (
            refresh_opens.astimezone(timezone.utc)
            <= generated_at.astimezone(timezone.utc)
            <= effective_at.astimezone(timezone.utc)
        )
    ):
        raise ValueError("decision input generation clock outside legal window")

    score = json.loads((root / "correct_score_audit.json").read_text(encoding="utf-8"))
    score_hash = _payload_hash(score)
    if (
        score.get("segment_manifest_sha256") != common[1]
        or score.get("decision_input_sha256") != common[2]
        or score.get("effective_decision_at") != common[5]
    ):
        raise ValueError("correct-score audit frozen identity mismatch")
    score_budgets = {
        (
            int(item["requested_budget_yuan"]),
            str(item["status"]),
        )
        for item in score.get("budget_statuses", [])
    }
    if score_budgets != {(budget, SCORE_BUDGET_STATUS) for budget in BUDGETS}:
        raise ValueError("correct-score budget status grid mismatch")
    for status in score.get("budget_statuses", []):
        if (
            float(status.get("actual_cost_yuan", -1)) != 0
            or not str(status.get("reason") or "")
        ):
            raise ValueError("correct-score unavailable budget evidence incomplete")
    expected_matches = {int(value) for value in common[0]}
    verified_bundles = {
        (
            str(item.get("path") or ""),
            str(item.get("sha256s_sha256") or ""),
        )
        for item in score.get("verified_capture_bundles", [])
    }
    match_audit = score.get("per_match_audit")
    if not isinstance(match_audit, list) or {
        int(item.get("match_idx", -1)) for item in match_audit
    } != expected_matches or len(match_audit) != len(expected_matches):
        raise ValueError("correct-score audit does not cover exact segment denominator")
    for item in match_audit:
        eligible = item.get("eligible")
        reasons = item.get("reasons")
        vector = item.get("complete_price_vector")
        if not isinstance(eligible, bool) or not isinstance(reasons, list):
            raise ValueError("correct-score eligibility evidence malformed")
        if not isinstance(vector, list):
            raise ValueError("correct-score price vector missing")
        required = (
            "snapshot_id",
            "snapshot_ts_hkt",
            "source_time_raw",
            "fetched_at_utc",
            "sale_state",
            "raw_payload_sha256",
            "raw_row_sha256",
            "capture_batch_id",
            "capture_bundle_sha256s_sha256",
            "outcome_schema_sha256",
            "correct_score_model_input_sha256",
        )
        if not eligible and not reasons:
            raise ValueError("ineligible correct-score match lacks reasons")
        if not vector:
            if eligible:
                raise ValueError("eligible correct-score match lacks price vector")
            continue
        if any(not str(item.get(key) or "") for key in required):
            raise ValueError("correct-score vector lacks complete source evidence")
        unknown_sale_state = str(item["sale_state"]).startswith("UNKNOWN")
        if eligible and (reasons or unknown_sale_state):
            raise ValueError("eligible correct-score match has unresolved evidence")
        if unknown_sale_state and "missing_source_sale_state" not in reasons:
            raise ValueError("unknown correct-score sale state lacks explicit reason")
        fetched = datetime.fromisoformat(str(item["fetched_at_utc"]))
        snapshot_at = datetime.fromisoformat(str(item["snapshot_ts_hkt"]))
        if (
            fetched.tzinfo is None
            or snapshot_at.tzinfo is None
            or fetched.astimezone(timezone.utc)
            > effective_at.astimezone(timezone.utc)
            or snapshot_at.astimezone(timezone.utc)
            > effective_at.astimezone(timezone.utc)
            or item.get("phase") != "pregame"
        ):
            raise ValueError("correct-score as-of clock/phase violation")
        for hash_key in (
            "raw_payload_sha256",
            "raw_row_sha256",
            "capture_bundle_sha256s_sha256",
            "outcome_schema_sha256",
            "correct_score_model_input_sha256",
        ):
            if not re.fullmatch(r"[0-9a-f]{64}", str(item[hash_key])):
                raise ValueError("correct-score source hash malformed")
        codes = [str(row.get("outcome_code") or "") for row in vector]
        if not all(codes) or len(codes) != len(set(codes)):
            raise ValueError("correct-score vector contains missing/duplicate outcomes")
        model_input = {
            "issue": str(score["issue"]),
            "match_idx": int(item["match_idx"]),
            "snapshot_id": item["snapshot_id"],
            "outcome_schema_sha256": item["outcome_schema_sha256"],
            "prices": vector,
        }
        if item["correct_score_model_input_sha256"] != _digest(model_input):
            raise ValueError("correct-score model input hash mismatch")
        if (
            str(item.get("capture_bundle") or ""),
            str(item.get("capture_bundle_sha256s_sha256") or ""),
        ) not in verified_bundles:
            raise ValueError("correct-score snapshot lacks verified bundle linkage")
    if any(
        score.get(flag) is not False
        for flag in ("execution_enabled", "frontend_selectable", "roi_authorized")
    ):
        raise ValueError("unsafe correct-score policy flag")
    score_entry = artifact_entries.get("correct_score_audit.json")
    if not score_entry or score_entry.get("sha256") != score_hash:
        raise ValueError("correct-score manifest linkage mismatch")
    input_entry = artifact_entries.get("decision_input_manifest.json")
    if not input_entry or input_entry.get("sha256") != input_hash:
        raise ValueError("decision-input manifest linkage mismatch")
    source_entry = artifact_entries.get("structured_input.csv")
    if not source_entry or source_entry.get("sha256") != _file_hash(source_bytes):
        raise ValueError("structured input bytes manifest linkage mismatch")
    receipt_entry = artifact_entries.get("structured_input_receipt.json")
    if not receipt_entry or receipt_entry.get("sha256") != receipt_hash:
        raise ValueError("structured input receipt manifest linkage mismatch")

    expected_artifacts = {path.name for path in files} | {
        "correct_score_audit.json",
        "decision_input_manifest.json",
        "structured_input.csv",
        "structured_input_receipt.json",
    }
    if set(artifact_entries) != expected_artifacts:
        raise ValueError("manifest artifact file set mismatch")
    if set(sums) != expected_artifacts | {"manifest.json"}:
        raise ValueError("package contains an unexpected or unbound file")
    return {
        "status": "PASS",
        "cells": 15,
        "grid": sorted([list(item) for item in grid]),
        "shared_freeze_at": common[4],
        "effective_decision_at": common[5],
        "segment_manifest_sha256": common[1],
        "decision_input_sha256": common[2],
        "decision_input_manifest_sha256": common[3],
        "correct_score_audit_sha256": score_hash,
        "artifact_manifest_sha256": _file_hash(root / "manifest.json"),
        "artifact_manifest_payload_sha256": manifest_hash,
        "package_sha256s_sha256": _file_hash(root / "SHA256SUMS"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        report = verify_directory(args.directory)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
