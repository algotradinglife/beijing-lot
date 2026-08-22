#!/usr/bin/env python3
"""Aggregate development surfaces and freeze #312 candidates before 2023 settlement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue312.model import fit_expanding_oof, select_frozen_candidates  # noqa: E402
from issue312.surface import DEVELOPMENT_YEARS, aggregate_action_labels  # noqa: E402


def main() -> None:
    output = ROOT / "results/issue-312"
    support = pd.read_csv(
        ROOT / "results/issue-299/support_receipt.csv", dtype={"issue": str}
    )
    common_issues = set(
        support.loc[
            support["support_status"].eq("MATCHED_BASELINE_AND_FEATURES")
            & support["issue_year"].isin(DEVELOPMENT_YEARS),
            "issue",
        ]
    )
    ledgers = [
        pd.read_parquet(output / f"development_seed_action_ledger_{year}.parquet")
        for year in DEVELOPMENT_YEARS
    ]
    ledger = pd.concat(ledgers, ignore_index=True)
    ledger = ledger[ledger["issue"].astype(str).isin(common_issues)].copy()
    labels = aggregate_action_labels(ledger)
    labels.to_parquet(output / "development_action_labels.parquet", index=False)
    states = pd.read_csv(
        ROOT / "results/issue-209/dynamic_issue_states.csv", dtype={"issue": str}
    )
    states = states[
        states["issue_year"].between(2019, 2022)
        & states["issue"].isin(common_issues)
    ]
    prediction_frames = []
    receipt_frames = []
    for condition in ("LEARNED", "ISSUE_BLOCK_SHUFFLED", "IDENTITY_SHUFFLED"):
        predictions, receipts = fit_expanding_oof(states, labels, condition=condition)
        prediction_frames.append(predictions)
        receipt_frames.append(receipts)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    predictions.to_parquet(output / "development_oof_predictions.parquet", index=False)
    pd.concat(receipt_frames, ignore_index=True).to_csv(
        output / "development_fit_receipts.csv", index=False
    )
    registry = pd.read_csv(output / "action_registry.csv")
    frozen, policy_summary, primary = select_frozen_candidates(
        predictions, labels, registry
    )
    frozen_path = output / "frozen_candidate_registry.csv"
    frozen.to_csv(frozen_path, index=False)
    policy_summary.to_csv(output / "development_policy_selection.csv", index=False)
    receipt = {
        "issue": 312,
        "stage": "PRE_2023_OUTCOME_CANDIDATE_FREEZE",
        "candidate_actions": int(len(frozen)),
        "primary_family": primary,
        "development_years": list(DEVELOPMENT_YEARS),
        "support_contract": "ISSUE_299_EXACT_B0_COMMON_SUPPORT",
        "development_common_support_issues": int(ledger["issue"].nunique()),
        "development_common_support_by_year": {
            str(year): int(ledger.loc[ledger["issue_year"].eq(year), "issue"].nunique())
            for year in DEVELOPMENT_YEARS
        },
        "physical_seeds": int(ledger["seed"].nunique()),
        "independent_unit": "BEIJING_ISSUE",
        "frozen_registry_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(),
        "sealed_years": "2023 outcomes not read by selection; 2024+ sealed",
    }
    (output / "candidate_freeze_receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(receipt)


if __name__ == "__main__":
    main()
