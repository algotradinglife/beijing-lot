#!/usr/bin/env python3
"""Semantic and cryptographic verifier for BJ-BET-FREEZE-001 packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
        if any(
            int(ticket.get("actual_n", -1)) != requested_n
            or len(ticket.get("match_indices", [])) != requested_n
            or len(ticket.get("leg_codes", [])) != requested_n
            for ticket in tickets
        ):
            raise ValueError("N=4→3 or other leg fallback")
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

    expected_artifacts = {path.name for path in files} | {
        "correct_score_audit.json",
        "decision_input_manifest.json",
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
