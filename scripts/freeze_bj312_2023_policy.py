#!/usr/bin/env python3
"""Freeze Issue #312 2023 decisions before physical outcome settlement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue312.model import fit_final_2023  # noqa: E402
from issue312.policy import select_policy_allocations  # noqa: E402


def main() -> None:
    output = ROOT / "results/issue-312"
    labels = pd.read_parquet(output / "development_action_labels.parquet")
    candidates = pd.read_csv(output / "frozen_candidate_registry.csv")
    support = pd.read_csv(
        ROOT / "results/issue-299/support_receipt.csv", dtype={"issue": str}
    )
    common_issues = set(
        support.loc[
            support["support_status"].eq("MATCHED_BASELINE_AND_FEATURES"), "issue"
        ]
    )
    states = pd.read_csv(
        ROOT / "results/issue-209/dynamic_issue_states.csv", dtype={"issue": str}
    )
    states = states[
        states["issue_year"].between(2019, 2023)
        & states["issue"].isin(common_issues)
    ]
    prediction_sets = {}
    receipts = []
    for condition in ("LEARNED", "ISSUE_BLOCK_SHUFFLED", "IDENTITY_SHUFFLED"):
        predictions, local_receipts = fit_final_2023(
            states, labels, candidates, condition=condition
        )
        prediction_sets[condition] = predictions
        receipts.append(local_receipts)
    all_predictions = pd.concat(prediction_sets.values(), ignore_index=True)
    all_predictions.to_parquet(output / "pre2023_action_predictions.parquet", index=False)
    pd.concat(receipts, ignore_index=True).to_csv(
        output / "pre2023_fit_receipts.csv", index=False
    )
    primary_family = json.loads(
        (output / "candidate_freeze_receipt.json").read_text(encoding="utf-8")
    )["primary_family"]
    issue306 = pd.read_csv(
        ROOT / "results/issue-306/policy_allocations.csv", dtype={"issue": str}
    )
    allocations, evaluation_registry = select_policy_allocations(
        prediction_sets,
        primary_family=primary_family,
        issue306_allocations=issue306,
        development_labels=labels,
    )
    allocation_path = output / "pre2023_policy_allocations.csv"
    registry_path = output / "evaluation_action_registry.csv"
    allocations.to_csv(allocation_path, index=False)
    evaluation_registry.to_csv(registry_path, index=False)
    receipt = {
        "issue": 312,
        "stage": "PRE_2023_OUTCOME_POLICY_FREEZE",
        "primary_family": primary_family,
        "conditions": sorted(allocations["condition"].unique()),
        "issues": int(allocations["issue"].nunique()),
        "support_contract": "ISSUE_299_EXACT_B0_COMMON_SUPPORT",
        "tickets_per_condition_issue": 512,
        "stake_per_condition_issue_cny": 1024.0,
        "best_static_action_key": allocations.attrs["best_static_action_key"],
        "evaluation_actions": int(len(evaluation_registry)),
        "allocations_sha256": hashlib.sha256(allocation_path.read_bytes()).hexdigest(),
        "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
        "settlement_fields_read": [],
        "sealed_years": "2023 outcomes not read; 2024+ sealed",
    }
    (output / "pre2023_policy_freeze_receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(receipt)


if __name__ == "__main__":
    main()
