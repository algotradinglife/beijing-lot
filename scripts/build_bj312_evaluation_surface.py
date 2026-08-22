#!/usr/bin/env python3
"""Build the frozen 2023 physical surface after the #312 policy freeze."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue312.design import actions_from_registry  # noqa: E402
from issue312.surface import EVALUATION_SEEDS, write_year_surface  # noqa: E402


def main() -> None:
    output = ROOT / "results/issue-312"
    freeze = output / "pre2023_policy_freeze_receipt.json"
    if not freeze.exists():
        raise FileNotFoundError("2023 policy must be frozen before settlement")
    registry = pd.read_csv(output / "evaluation_action_registry.csv")
    actions = actions_from_registry(registry)
    support = pd.read_csv(
        ROOT / "results/issue-299/support_receipt.csv", dtype={"issue": str}
    )
    common_issues = set(
        support.loc[
            support["support_status"].eq("MATCHED_BASELINE_AND_FEATURES")
            & support["issue_year"].eq(2023),
            "issue",
        ]
    )
    full_tensor = build_tensor()
    units = build_match_units(full_tensor)
    keep = units["issue_year"].eq(2023) & units["issue"].astype(str).isin(common_issues)
    probabilities = pd.read_parquet(
        ROOT / "results/issue-209/market_only_probabilities.parquet"
    ).loc[keep].reset_index(drop=True)
    values = pd.read_parquet(
        ROOT / "results/issue-209/cell_value_distribution.parquet"
    ).loc[keep].reset_index(drop=True)
    tensor = full_tensor[
        full_tensor["issue_year"].eq(2023)
        & full_tensor["issue"].astype(str).isin(common_issues)
    ].copy().reset_index(drop=True)
    receipt = write_year_surface(
        tensor,
        probabilities,
        values,
        actions,
        output,
        year=2023,
        seeds=EVALUATION_SEEDS,
        prefix="evaluation",
    )
    print({"issue": 312, "stage": "FROZEN_2023_SURFACE", **receipt})


if __name__ == "__main__":
    main()
