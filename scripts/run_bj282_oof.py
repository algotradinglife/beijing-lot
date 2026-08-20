#!/usr/bin/env python3
"""Run annual expanding-window #282 diagnostics for 2018 through 2022."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue279.traces import build_cell_trace  # noqa: E402
from issue282.contract import CELL_FEATURES, FIXED_BASELINE_KEYS  # noqa: E402
from issue282.data import pack_issue_cells  # noqa: E402
from issue282.evaluation import (  # noqa: E402
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

OOF_YEARS = tuple(range(2018, 2023))
OOF_DEEP_SEED = 282_101


def main() -> int:
    output = ROOT / "results/issue-282"
    labels = pd.concat(
        [
            pd.read_parquet(path)
            for path in sorted(output.glob("counterfactual_labels_20*.parquet"))
        ],
        ignore_index=True,
    )
    labels["issue"] = labels["issue"].astype(str)
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

    metric_rows: list[dict[str, object]] = []
    ledger_rows: list[pd.DataFrame] = []
    for year in OOF_YEARS:
        development = labels["issue_year"].lt(year).to_numpy()
        validation = labels["issue_year"].eq(year).to_numpy()
        arrays = prepare_arrays(
            packed, action_features, labels, development_mask=development
        )
        controls = fit_controls(arrays, development, seed=OOF_DEEP_SEED)
        control_prediction = predict_controls(controls, arrays.actions[validation])
        model, receipt = fit_deep_set(
            arrays,
            development,
            seed=OOF_DEEP_SEED,
            epochs=8,
            actions_per_issue=32,
        )
        deep_prediction = predict_deep_set(
            model,
            arrays,
            validation,
            target_scale=float(receipt["target_scale"]),
        ).reset_index(drop=True)
        deep_score = deep_prediction["deep_expected_value"] + 0.25 * deep_prediction[
            "deep_q10"
        ].clip(upper=0.0)
        development_fixed = (
            labels.loc[
                development & labels["action_key"].isin(FIXED_BASELINE_KEYS.values())
            ]
            .groupby("action_key", as_index=False)["pnl_cny_mean"]
            .sum()
            .sort_values(["pnl_cny_mean", "action_key"], ascending=[False, True])
        )
        fallback_key = str(development_fixed.iloc[0]["action_key"])
        fallback_name = next(
            name for name, key in FIXED_BASELINE_KEYS.items() if key == fallback_key
        )
        year_labels = labels.loc[validation].reset_index(drop=True)
        fallback = fixed_action_ledger(
            year_labels, action_key=fallback_key, policy_name=fallback_name
        )
        policies = {
            "LINEAR": control_prediction["linear_expected_value"],
            "HGB": control_prediction["hgb_expected_value"],
            "DEEP": deep_score,
        }
        for policy, score in policies.items():
            ledger = choose_actions_with_baseline_guard(
                year_labels,
                score,
                policy_name=policy,
                fallback_action_key=fallback_key,
            )
            metrics = capital_path_metrics(ledger, baseline=fallback)
            funded_deviations = int(
                ledger["guard_reason"].eq("MODEL_PREDICTED_LIFT").sum()
            )
            metric_rows.append(
                {
                    "validation_year": year,
                    "policy": policy,
                    "fallback_name": fallback_name,
                    "development_end_year": year - 1,
                    "funded_model_deviations": funded_deviations,
                    **metrics,
                }
            )
            ledger_rows.append(ledger.assign(validation_year=year, oof_policy=policy))
        print(
            f"year={year} issues={year_labels.issue.nunique()} "
            f"fallback={fallback_name} deep_loss={receipt['final_epoch_loss']:.6f}",
            flush=True,
        )
    pd.DataFrame(metric_rows).to_csv(output / "expanding_oof_metrics.csv", index=False)
    pd.concat(ledger_rows, ignore_index=True).to_parquet(
        output / "expanding_oof_ledger.parquet", index=False
    )
    print(pd.DataFrame(metric_rows).to_string(index=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
