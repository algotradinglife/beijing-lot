#!/usr/bin/env python3
"""Materialize #279 action features and development/2023 attribution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue279.features import build_action_features, feature_dictionary  # noqa: E402


def main() -> int:
    source = ROOT / "results/issue-209"
    output = ROOT / "results/issue-279"
    output.mkdir(parents=True, exist_ok=True)
    states = pd.read_csv(source / "dynamic_issue_states.csv", dtype={"issue": str})
    outcomes = pd.read_parquet(source / "dynamic_action_counterfactuals.parquet")
    outcomes["issue"] = outcomes["issue"].astype(str)
    if states["issue_year"].ge(2024).any() or outcomes["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ outcome seal violated")

    actions = outcomes[["action_key", "n", "k", "generator"]].drop_duplicates()
    features = build_action_features(states, actions)
    features.to_parquet(output / "action_features.parquet", index=False)
    feature_dictionary().to_csv(output / "feature_dictionary.csv", index=False)

    joined = outcomes.merge(
        features, on=["issue", "issue_year", "action_key", "n", "k", "generator"],
        how="inner", validate="one_to_one", suffixes=("", "_feature"),
    )
    oracle = (
        joined.sort_values(["issue", "utility_bps", "action_key"], ascending=[True, False, True])
        .groupby("issue", as_index=False).first()
    )
    oracle["oracle_n"] = oracle["n"]
    oracle["oracle_k"] = oracle["k"]
    oracle["oracle_generator"] = oracle["generator"]
    oracle["breadth_bin"] = pd.qcut(oracle["n_matches"], 4, duplicates="drop")
    oracle["divergence_bin"] = pd.qcut(oracle["divergence_abs_mean"], 4, duplicates="drop")
    oracle["value_bin"] = pd.qcut(oracle["value_best_mean"], 4, duplicates="drop")
    profile = (
        oracle.groupby(["breadth_bin", "divergence_bin"], observed=True)
        .agg(
            issues=("issue", "size"), oracle_n_median=("oracle_n", "median"),
            oracle_k_median=("oracle_k", "median"), oracle_utility_mean=("utility_bps", "mean"),
            oracle_positive_fraction=("mean_pnl", lambda x: float((x > 0).mean())),
        ).reset_index()
    )
    profile.to_csv(output / "conditional_oracle_profile.csv", index=False)

    chosen = pd.read_csv(source / "dynamic_calibration_actions.csv", dtype={"issue": str})
    fixed = outcomes[
        outcomes["temporal_role"].eq("calibration")
        & outcomes["action_key"].eq("N7_K8_TOP_VALUE")
    ][["issue", "mean_pnl", "utility_bps"]].rename(
        columns={"mean_pnl": "fixed_pnl", "utility_bps": "fixed_utility_bps"}
    )
    oracle_2023 = oracle[oracle["issue_year"].eq(2023)][
        ["issue", "oracle_n", "oracle_k", "oracle_generator", "mean_pnl", "utility_bps"]
    ].rename(columns={"mean_pnl": "oracle_pnl", "utility_bps": "oracle_utility_bps"})
    ledger = chosen.merge(fixed, on="issue", validate="one_to_one").merge(
        oracle_2023, on="issue", validate="one_to_one"
    )
    ledger["lift_pnl_vs_fixed"] = ledger["mean_pnl"] - ledger["fixed_pnl"]
    ledger["oracle_regret_pnl"] = ledger["oracle_pnl"] - ledger["mean_pnl"]
    ledger["n_changed"] = ledger["n"].ne(7)
    ledger["k_changed"] = ledger["k"].ne(8)
    ledger["generator_changed"] = ledger["generator"].ne("TOP_VALUE")
    ledger["selection_attribution"] = "NOT_IDENTIFIABLE_AGGREGATE_TICKET_TRACE"
    ledger["outcome_attribution"] = "NOT_IDENTIFIABLE_AGGREGATE_TICKET_TRACE"
    ledger["failure_stage"] = "NO_FAILURE_VS_FIXED"
    lost = ledger["lift_pnl_vs_fixed"].lt(0)
    changed_count = ledger[["n_changed", "k_changed", "generator_changed"]].sum(axis=1)
    ledger.loc[lost & changed_count.gt(1), "failure_stage"] = "JOINT_N_K_GENERATOR"
    ledger.loc[lost & changed_count.eq(1) & ledger["n_changed"], "failure_stage"] = "N_ONLY"
    ledger.loc[lost & changed_count.eq(1) & ledger["k_changed"], "failure_stage"] = "K_ONLY"
    ledger.loc[lost & changed_count.eq(1) & ledger["generator_changed"], "failure_stage"] = "GENERATOR_ONLY"
    ledger = ledger.sort_values("issue").reset_index(drop=True)
    ledger["dynamic_capital"] = 100_000.0 + ledger["mean_pnl"].cumsum()
    ledger["fixed_capital"] = 100_000.0 + ledger["fixed_pnl"].cumsum()
    ledger.to_csv(output / "issue_2023_attribution.csv", index=False)

    decision = {
        "contract": "BJ-UNIFIED-ACTION-FEATURES-001/v1",
        "development_years": [int(states.issue_year.min()), 2023],
        "development_issues": int(states.issue.nunique()),
        "action_feature_rows": int(len(features)),
        "independent_unit": "Beijing_issue",
        "2023_issues": int(len(ledger)),
        "2023_dynamic_pnl": float(ledger.mean_pnl.sum()),
        "2023_fixed_pnl": float(ledger.fixed_pnl.sum()),
        "2023_lift_pnl": float(ledger.lift_pnl_vs_fixed.sum()),
        "2023_mean_oracle_regret_pnl": float(ledger.oracle_regret_pnl.mean()),
        "oracle_parameter_label_valid": False,
        "oracle_bias_warning": "RAW_ARGMAX_CONFOUNDED_BY_K_EXPOSURE_AND_MULTIPLE_ACTION_HINDSIGHT",
        "2023_selection_outcome_attribution": "NOT_IDENTIFIABLE_WITH_CURRENT_AGGREGATE_TRACE",
        "seal": {"rows_opened_2024_plus": 0},
        "promotion_authority": False,
    }
    (output / "decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")
    print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
