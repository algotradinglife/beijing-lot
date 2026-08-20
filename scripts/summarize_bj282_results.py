#!/usr/bin/env python3
"""Create compact, reviewable #282 robustness summaries from label shards."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/issue-282"


def main() -> int:
    labels = pd.concat(
        [
            pd.read_parquet(path)
            for path in sorted(RESULTS.glob("counterfactual_labels_20*.parquet"))
        ],
        ignore_index=True,
    )
    dimensions = [
        "action_key",
        "selector",
        "outcome_weight_mode",
        "n",
        "generator",
        "k",
    ]
    yearly = (
        labels.groupby([*dimensions, "issue_year"], as_index=False)
        .agg(
            issues=("issue", "nunique"),
            turnover_cny=("stake_cny_mean", "sum"),
            pnl_cny=("pnl_cny_mean", "sum"),
        )
    )
    yearly["return_per_cny"] = np.divide(
        yearly["pnl_cny"],
        yearly["turnover_cny"],
        out=np.zeros(len(yearly)),
        where=yearly["turnover_cny"].to_numpy() > 0,
    )
    development = (
        yearly.loc[yearly["issue_year"].le(2022)]
        .groupby(dimensions, as_index=False)
        .agg(
            development_years=("issue_year", "nunique"),
            development_positive_years=("pnl_cny", lambda values: int((values > 0).sum())),
            development_turnover_cny=("turnover_cny", "sum"),
            development_pnl_cny=("pnl_cny", "sum"),
            development_worst_year_return=("return_per_cny", "min"),
            development_median_year_return=("return_per_cny", "median"),
        )
    )
    development["development_return_per_cny"] = np.divide(
        development["development_pnl_cny"],
        development["development_turnover_cny"],
        out=np.zeros(len(development)),
        where=development["development_turnover_cny"].to_numpy() > 0,
    )
    test = labels.loc[labels["issue_year"].eq(2023)].copy()

    def summarize_test(group: pd.DataFrame) -> pd.Series:
        pnl = group["pnl_cny_mean"].to_numpy(dtype=float)
        positive = pnl[pnl > 0]
        largest = float(positive.max()) if len(positive) else 0.0
        return pd.Series(
            {
                "test_issues": int(group["issue"].nunique()),
                "test_turnover_cny": float(group["stake_cny_mean"].sum()),
                "test_pnl_cny": float(pnl.sum()),
                "test_positive_issues": int((pnl > 0).sum()),
                "test_ex_largest_pnl_cny": float(pnl.sum() - largest),
                "test_largest_positive_share": (
                    largest / float(positive.sum()) if positive.sum() > 0 else 0.0
                ),
            }
        )

    test_summary = (
        test.groupby(dimensions, observed=True)
        .apply(summarize_test, include_groups=False)
        .reset_index()
    )
    test_summary["test_return_per_cny"] = np.divide(
        test_summary["test_pnl_cny"],
        test_summary["test_turnover_cny"],
        out=np.zeros(len(test_summary)),
        where=test_summary["test_turnover_cny"].to_numpy() > 0,
    )
    robustness = test_summary.merge(
        development, on=dimensions, how="left", validate="one_to_one"
    ).sort_values(
        ["test_pnl_cny", "test_ex_largest_pnl_cny", "action_key"],
        ascending=[False, False, True],
    )
    robustness.to_csv(RESULTS / "static_action_robustness_2023.csv", index=False)
    print(robustness.head(20).to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
