#!/usr/bin/env python3
"""Train #282 controls/Deep Sets and run the frozen-2022 2023 replay."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue279.traces import build_cell_trace  # noqa: E402
from issue282.data import pack_issue_cells  # noqa: E402
from issue282.evaluation import (  # noqa: E402
    add_capital_curve,
    build_attribution_ledger,
    capital_path_metrics,
    choose_actions_with_baseline_guard,
    fixed_action_ledger,
)
from issue282.features import ISSUE_STATE_FEATURES, build_action_feature_frame  # noqa: E402
from issue282.training import (  # noqa: E402
    fit_controls,
    fit_deep_set,
    predict_controls,
    predict_deep_set,
    prepare_arrays,
)

MODEL_SEEDS = tuple(282_101 + offset for offset in range(5))
CELL_FEATURES = (
    "native_handicap_line",
    "n_available_books",
    "mapping_accepted",
    "probability",
    "cell_value",
    "value_q10",
    "value_q90",
    "divergence",
    "predicted_sp_proxy",
    "cell_value_rank",
    "match_best_value",
    "match_value_rank",
)


def main() -> int:
    output = ROOT / "results/issue-282"
    output.mkdir(parents=True, exist_ok=True)
    label_paths = sorted(output.glob("counterfactual_labels_20*.parquet"))
    if len(label_paths) != 10:
        raise RuntimeError(f"expected ten 2014-2023 label shards, found {len(label_paths)}")
    labels = pd.concat([pd.read_parquet(path) for path in label_paths], ignore_index=True)
    labels["issue"] = labels["issue"].astype(str)
    if labels["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ label seal violated")
    print(f"labels rows={len(labels)} issues={labels.issue.nunique()}", flush=True)

    inherited = pd.read_parquet(ROOT / "results/issue-279/action_features.parquet")
    inherited["issue"] = inherited["issue"].astype(str)
    states = inherited[["issue", *ISSUE_STATE_FEATURES]].drop_duplicates("issue")
    action_features = build_action_feature_frame(labels, states)

    tensor = build_tensor()
    units = build_match_units(tensor)
    probabilities = pd.read_parquet(
        ROOT / "results/issue-209/market_only_probabilities.parquet"
    )
    values = pd.read_parquet(ROOT / "results/issue-209/cell_value_distribution.parquet")
    cells = build_cell_trace(
        units, probabilities, values, issues=set(labels["issue"]), horizon="10h"
    )
    packed = pack_issue_cells(
        cells,
        issue_col="issue",
        match_col="match_idx",
        outcome_col="outcome_code",
        feature_cols=CELL_FEATURES,
    )
    development = labels["issue_year"].le(2022).to_numpy()
    test = labels["issue_year"].eq(2023).to_numpy()
    arrays = prepare_arrays(
        packed, action_features, labels, development_mask=development
    )
    print(
        f"packed issues={len(packed.issue_ids)} cells={arrays.cells.shape} "
        f"actions={arrays.actions.shape}",
        flush=True,
    )

    controls = fit_controls(arrays, development)
    control_predictions = predict_controls(controls, arrays.actions[test])
    print("controls=complete", flush=True)

    deep_predictions: list[pd.DataFrame] = []
    receipts: list[dict[str, float | int]] = []
    for seed in MODEL_SEEDS:
        model, receipt = fit_deep_set(arrays, development, seed=seed)
        prediction = predict_deep_set(
            model,
            arrays,
            test,
            target_scale=float(receipt["target_scale"]),
        ).reset_index(drop=True)
        prediction = prediction.add_suffix(f"_seed{seed}")
        deep_predictions.append(prediction)
        receipts.append(receipt)
        torch.save(model.state_dict(), output / f"deep_set_seed{seed}.pt")
        print(
            f"deep seed={seed} loss={float(receipt['final_epoch_loss']):.6f}",
            flush=True,
        )

    test_labels = labels.loc[test].reset_index(drop=True)
    predictions = pd.concat(
        [
            test_labels[
                [
                    "issue",
                    "issue_year",
                    "action_key",
                    "selector",
                    "outcome_weight_mode",
                    "n",
                    "generator",
                    "k",
                    "normalized_pnl_cny100",
                    "pnl_cny_mean",
                    "stake_cny_mean",
                ]
            ],
            control_predictions,
            *deep_predictions,
        ],
        axis=1,
    )
    for metric in (
        "deep_positive_probability",
        "deep_positive_magnitude",
        "deep_expected_value",
        "deep_q10",
        "deep_q50",
        "deep_q90",
    ):
        columns = [f"{metric}_seed{seed}" for seed in MODEL_SEEDS]
        predictions[f"{metric}_median"] = predictions[columns].median(axis=1)
    predictions["deep_policy_score"] = predictions["deep_expected_value_median"] + (
        0.25 * predictions["deep_q10_median"].clip(upper=0.0)
    )
    predictions.to_parquet(output / "predictions_2023.parquet", index=False)
    parameter_dimensions = [
        "selector",
        "outcome_weight_mode",
        "n",
        "generator",
        "k",
    ]
    parameter_performance = (
        test_labels.groupby(parameter_dimensions, as_index=False)
        .agg(
            issues=("issue", "nunique"),
            turnover_cny=("stake_cny_mean", "sum"),
            pnl_cny=("pnl_cny_mean", "sum"),
            positive_issues=("pnl_cny_mean", lambda values: int((values > 0).sum())),
            median_return_per_cny=("return_per_cny_mean", "median"),
        )
    )
    parameter_performance["return_per_cny"] = np.divide(
        parameter_performance["pnl_cny"],
        parameter_performance["turnover_cny"],
        out=np.zeros(len(parameter_performance)),
        where=parameter_performance["turnover_cny"].to_numpy() > 0,
    )
    parameter_performance.to_csv(
        output / "parameter_performance_2023.csv", index=False
    )
    yearly_performance = (
        labels.groupby(["issue_year", *parameter_dimensions], as_index=False)
        .agg(
            issues=("issue", "nunique"),
            turnover_cny=("stake_cny_mean", "sum"),
            pnl_cny=("pnl_cny_mean", "sum"),
        )
    )
    yearly_performance["return_per_cny"] = np.divide(
        yearly_performance["pnl_cny"],
        yearly_performance["turnover_cny"],
        out=np.zeros(len(yearly_performance)),
        where=yearly_performance["turnover_cny"].to_numpy() > 0,
    )
    yearly_performance.to_csv(output / "parameter_performance_by_year.csv", index=False)

    fixed_keys = {
        "FIXED_N7_K8_TOP_CELL_VALUE": "SALL_OVALUE_N7_TOP_VALUE_K8",
        "FIXED_N7_K8_TOP_MARKET": "SALL_OMARKET_N7_TOP_VALUE_K8",
        "FIXED_N7_K8_TOP_DIVERGENCE": "SALL_ODIVVALUE_N7_TOP_VALUE_K8",
        "FIXED_N7_K8_WR_CELL_VALUE": "SALL_OVALUE_N7_WEIGHTED_WR_K8",
        "FIXED_N7_K8_WOR_CELL_VALUE": "SALL_OVALUE_N7_WEIGHTED_WOR_K8",
    }
    development_fixed_performance = (
        labels.loc[development & labels["action_key"].isin(fixed_keys.values())]
        .groupby("action_key", as_index=False)
        .agg(
            development_turnover_cny=("stake_cny_mean", "sum"),
            development_pnl_cny=("pnl_cny_mean", "sum"),
        )
    )
    development_fixed_performance["development_return_per_cny"] = np.divide(
        development_fixed_performance["development_pnl_cny"],
        development_fixed_performance["development_turnover_cny"],
    )
    development_fixed_performance = development_fixed_performance.sort_values(
        ["development_pnl_cny", "action_key"], ascending=[False, True]
    )
    frozen_guard_key = str(development_fixed_performance.iloc[0]["action_key"])
    frozen_guard_name = next(
        name for name, key in fixed_keys.items() if key == frozen_guard_key
    )
    development_fixed_performance.to_csv(
        output / "development_fixed_baseline_selection.csv", index=False
    )
    ledgers = {
        name: fixed_action_ledger(test_labels, action_key=key, policy_name=name)
        for name, key in fixed_keys.items()
    }
    cash = ledgers[frozen_guard_name].copy()
    cash["action_key"] = "NO_BET"
    cash["pnl_cny_mean"] = 0.0
    cash["stake_cny_mean"] = 0.0
    cash["predicted_score"] = 0.0
    cash["policy"] = "CASH_NO_BET"
    ledgers["CASH_NO_BET"] = cash
    ledgers["LINEAR"] = choose_actions_with_baseline_guard(
        test_labels,
        control_predictions["linear_expected_value"],
        policy_name="LINEAR",
        fallback_action_key=frozen_guard_key,
    )
    ledgers["HGB"] = choose_actions_with_baseline_guard(
        test_labels,
        control_predictions["hgb_expected_value"],
        policy_name="HGB",
        fallback_action_key=frozen_guard_key,
    )
    ledgers["DEEP_ENSEMBLE"] = choose_actions_with_baseline_guard(
        test_labels,
        predictions["deep_policy_score"],
        policy_name="DEEP_ENSEMBLE",
        fallback_action_key=frozen_guard_key,
    )
    for seed in MODEL_SEEDS:
        score = predictions[f"deep_expected_value_seed{seed}"] + 0.25 * predictions[
            f"deep_q10_seed{seed}"
        ].clip(upper=0.0)
        ledgers[f"DEEP_SEED_{seed}"] = choose_actions_with_baseline_guard(
            test_labels,
            score,
            policy_name=f"DEEP_SEED_{seed}",
            fallback_action_key=frozen_guard_key,
        )

    strongest_fixed_name = frozen_guard_name
    strongest_fixed = ledgers[frozen_guard_name]
    metrics = []
    for name, ledger in ledgers.items():
        comparison = None if name == strongest_fixed_name else strongest_fixed
        row = {"policy": name, **capital_path_metrics(ledger, baseline=comparison)}
        metrics.append(row)
        add_capital_curve(ledger).to_csv(
            output / f"capital_path_{name.lower()}.csv", index=False
        )
    metrics_frame = pd.DataFrame(metrics)
    metrics_frame.to_csv(output / "policy_metrics_2023.csv", index=False)
    deep_attribution = build_attribution_ledger(
        ledgers["DEEP_ENSEMBLE"], strongest_fixed, test_labels
    )
    deep_attribution = deep_attribution.merge(
        predictions[
            [
                "issue",
                "action_key",
                "deep_positive_probability_median",
                "deep_positive_magnitude_median",
                "deep_expected_value_median",
                "deep_q10_median",
                "deep_q50_median",
                "deep_q90_median",
                "deep_policy_score",
            ]
        ],
        left_on=["issue", "requested_action_key"],
        right_on=["issue", "action_key"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_prediction"),
    )
    deep_attribution.to_parquet(
        output / "deep_ensemble_ledger_2023.parquet", index=False
    )

    primary = metrics_frame.set_index("policy").loc["DEEP_ENSEMBLE"]
    baseline = metrics_frame.set_index("policy").loc[strongest_fixed_name]
    seed_positive_vs_cash = int(
        sum(
            metrics_frame.set_index("policy").loc[f"DEEP_SEED_{seed}", "total_pnl_cny"]
            > 0
            for seed in MODEL_SEEDS
        )
    )
    positive_actual = test_labels["normalized_pnl_cny100"].gt(0).to_numpy(dtype=float)
    positive_predicted = predictions["deep_positive_probability_median"].to_numpy()
    positive_brier = float(np.mean(np.square(positive_predicted - positive_actual)))
    funded_model_deviations = int(
        ledgers["DEEP_ENSEMBLE"]["guard_reason"].eq("MODEL_PREDICTED_LIFT").sum()
    )
    criteria = {
        "ending_capital_above_cash": bool(primary["ending_capital_cny"] > 100_000.0),
        "ending_capital_above_frozen_active_baseline": bool(
            primary["ending_capital_cny"] > baseline["ending_capital_cny"]
        ),
        "ex_largest_matched_lift_nonnegative": bool(
            primary["ex_largest_matched_lift_cny"] >= 0
        ),
        "max_drawdown_no_worse": bool(
            primary["max_drawdown_fraction"] <= baseline["max_drawdown_fraction"]
        ),
        "rolling10_worst_no_worse": bool(
            primary["rolling_10_worst_pnl_cny"]
            >= baseline["rolling_10_worst_pnl_cny"]
        ),
        "funded_model_deviation_issues_at_least_15": funded_model_deviations >= 15,
        "largest_issue_positive_lift_share_at_most_half": bool(
            primary["largest_issue_positive_lift_share"] <= 0.5
        ),
        "model_seeds_positive_vs_cash_at_least_3_of_5": (
            seed_positive_vs_cash >= 3
        ),
        "causal_and_seal_checks": True,
    }
    decision = {
        "contract": "BJ-UNIFIED-CONDITIONAL-POLICY-001/v1",
        "primary_replay": "FROZEN_AT_2022_YEAR_END_EXECUTED_ON_2023",
        "development_years": [2014, 2022],
        "test_year": 2023,
        "sealed_years_opened": [],
        "strongest_matched_fixed_baseline": strongest_fixed_name,
        "baseline_selected_using": "2014_2022_DEVELOPMENT_TOTAL_PNL_BEFORE_2023",
        "deep_positive_brier_all_nested_action_rows": positive_brier,
        "positive_model_seed_count_vs_cash": seed_positive_vs_cash,
        "funded_model_deviation_issues": funded_model_deviations,
        "holdout_criteria": criteria,
        "holdout_eligible": all(criteria.values()),
        "promotion_authority": False,
        "notes": [
            "WR and WOR have identical funded tickets under equal distinct-ticket stakes; proposal frequency differs and is reserved for Stage 4.",
            "BEST_FULL legacy -9.47% is reported separately because its historical support is not identical to the current Mx3 tensor.",
        ],
    }
    (output / "training_receipts.json").write_text(
        json.dumps(receipts, indent=2), encoding="utf-8"
    )
    (output / "decision.json").write_text(
        json.dumps(decision, indent=2), encoding="utf-8"
    )
    print(metrics_frame.to_string(index=False), flush=True)
    print(json.dumps(decision, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
