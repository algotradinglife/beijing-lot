#!/usr/bin/env python3
"""Build the frozen 2023 physical surface after the #312 policy freeze."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue312.design import actions_from_registry  # noqa: E402
from issue312.surface import (  # noqa: E402
    EVALUATION_SEEDS,
    load_causal_issue209_inputs,
    write_year_surface,
)


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
    tensor, probabilities, values, causal_receipt = load_causal_issue209_inputs(
        ROOT / "results/issue-209/market_only_probabilities.parquet",
        ROOT / "results/issue-209/cell_value_distribution.parquet",
        years=(2023,),
        issues=common_issues,
    )
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
    print(
        {
            "issue": 312,
            "stage": "FROZEN_2023_SURFACE",
            "causal_read": causal_receipt,
            **receipt,
        }
    )


if __name__ == "__main__":
    main()
