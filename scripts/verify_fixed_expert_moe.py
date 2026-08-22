#!/usr/bin/env python3
"""Verify the frozen Issue #332 package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from fixed_expert_moe.contract import EXPERT_NAMES, TOTAL_STAKE_CNY, TOTAL_TICKETS


def verify(root: Path) -> dict[str, object]:
    output = root / "results/fixed_expert_moe"
    decision = json.loads((output / "decision.json").read_text())
    panel = pd.read_parquet(output / "learning_panel.parquet")
    allocations = pd.read_parquet(output / "allocations.parquet")
    settlement = pd.read_parquet(output / "settlement.parquet")
    predictions = pd.read_parquet(output / "oof_predictions.parquet")
    hashes = json.loads((output / "SHA256SUMS.json").read_text())
    checks = {
        "decision_no_unearned_unlock": not decision["unlock_210"] or decision["promotion"],
        "complete_expert_library": panel.groupby("issue")["expert"].nunique().min() == len(EXPERT_NAMES),
        "one_issue_expert_row": not panel.duplicated(["issue", "expert"]).any(),
        "allocation_reconciliation": allocations.groupby(["condition", "issue"])["ticket_count"].sum().eq(TOTAL_TICKETS).all(),
        "matched_stake": settlement["stake_cny"].eq(TOTAL_STAKE_CNY).all(),
        "evaluation_years": set(settlement["issue_year"].unique()) == {2022, 2023, 2024},
        "no_2025_consumption": panel["issue_year"].max() == 2024,
        "finite_predictions": predictions.filter(like="predicted_").notna().all().all(),
        "payout_once": decision["payout_application"] == "ONCE_PER_WINNING_COMPLETE_TICKET",
        "hashes": all(_sha256(output / name) == digest for name, digest in hashes.items()),
        "notebook_executed": _notebook_executed(root / "notebooks/research/fixed-expert-moe/fixed_expert_moe.ipynb"),
    }
    checks = {key: bool(value) for key, value in checks.items()}
    if not all(checks.values()):
        raise AssertionError({key: value for key, value in checks.items() if not value})
    return {"status": "PASS", "checks": checks}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def _notebook_executed(path: Path) -> bool:
    payload = json.loads(path.read_text())
    code = [cell for cell in payload["cells"] if cell["cell_type"] == "code"]
    return bool(code) and all(cell.get("execution_count") is not None for cell in code)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(verify(root), indent=2, sort_keys=True))
