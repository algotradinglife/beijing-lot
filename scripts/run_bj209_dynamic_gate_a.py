#!/usr/bin/env python3
"""Run the #209 method rework: learned per-issue dynamic ticket actions.

This consumes the already delivered Gate-A probability/value artifacts and
opens no 2024 outcome.  It produces issue-aggregated counterfactual training
rows, 2022 model-family selection, a frozen 2023 pre-outcome policy replay and
matched CNY100k capital paths.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.bankroll import matched_lift, simulate_bankroll, summarize_capital  # noqa: E402
from issue209.contract import INITIAL_BANKROLL, SEEDS  # noqa: E402
from issue209.data import build_tensor  # noqa: E402
from issue209.dynamic_policy import (  # noqa: E402
    action_features,
    build_issue_states,
    default_action_space,
    evaluate_counterfactual_actions,
    family_selection_receipt,
    fit_action_models,
    fixed_control_results,
    join_states_and_actions,
    oracle_diagnostic,
    predict_action_models,
    select_policy_actions,
)
from issue209.models import build_match_units  # noqa: E402


def _issue_results(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame[["issue", "stake_total", "mean_pnl"]].copy()
    result["n_tickets"] = (result["stake_total"] / 2.0).round().astype(int)
    result["realized_gross"] = result["stake_total"] + result["mean_pnl"]
    return result[["issue", "n_tickets", "stake_total", "realized_gross"]]


def _capital_path(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    path = simulate_bankroll(_issue_results(frame), initial=INITIAL_BANKROLL)
    return path, summarize_capital(path)


def _choice_entropy(selected: pd.DataFrame) -> float:
    shares = selected["action_key"].value_counts(normalize=True).to_numpy(dtype=float)
    return float(-np.sum(shares * np.log(np.clip(shares, 1e-12, 1.0))))


def _selection_diagnostics(selected: pd.DataFrame) -> dict[str, object]:
    ordered = selected.sort_values("mean_pnl", ascending=False, kind="stable")
    largest = ordered.iloc[0]
    return {
        "issues": int(len(selected)),
        "positive_issues": int(selected["mean_pnl"].gt(0).sum()),
        "total_pnl": float(selected["mean_pnl"].sum()),
        "ex_largest_total_pnl": float(ordered.iloc[1:]["mean_pnl"].sum()),
        "largest_issue": str(largest["issue"]),
        "largest_issue_pnl": float(largest["mean_pnl"]),
        "action_counts": {
            str(key): int(value)
            for key, value in selected["action_key"].value_counts().items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/issue-209"))
    parser.add_argument("--horizon", default="10h", choices=("initial", "10h", "1h"))
    parser.add_argument("--limit-issues", type=int, default=0)
    parser.add_argument(
        "--reuse-counterfactuals",
        action="store_true",
        help="reuse the already materialized sealed issue/action table and refit policy models only",
    )
    args = parser.parse_args()
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)

    if args.reuse_counterfactuals:
        print("[dynamic-0/2] reuse sealed issue states and seed-aggregated action outcomes")
        states = pd.read_csv(output / "dynamic_issue_states.csv", dtype={"issue": str})
        counterfactuals = pd.read_parquet(output / "dynamic_action_counterfactuals.parquet")
        counterfactuals["issue"] = counterfactuals["issue"].astype(str)
        if states["issue_year"].ge(2024).any() or counterfactuals["issue_year"].ge(2024).any():
            raise RuntimeError("reused action package violates the 2024 outcome seal")
        state_matches = states.set_index("issue")["n_matches"].astype(int)
        expected_actions = state_matches.map(
            lambda count: 1
            + sum(
                1
                for action in default_action_space()
                if action.generator != "NO_BET" and action.n <= count
            )
        )
        action_counts = counterfactuals.groupby("issue")["action_key"].nunique()
        aligned_expected = expected_actions.reindex(action_counts.index)
        if aligned_expected.isna().any() or not action_counts.eq(aligned_expected).all():
            raise RuntimeError("reused action package has incomplete action support")
        if not counterfactuals["seed_count"].eq(len(SEEDS)).all():
            raise RuntimeError("reused action package has wrong nuisance seed aggregation")
    else:
        print("[dynamic-0] rebuild sealed development tensor and match units")
        tensor = build_tensor()
        if int(tensor["issue_year"].ge(2024).sum()):
            raise RuntimeError("2024 outcome seal violated")
        units = build_match_units(tensor)
        probabilities = pd.read_parquet(output / "market_only_probabilities.parquet")
        value = pd.read_parquet(output / "cell_value_distribution.parquet")
        if len(probabilities) != len(units) or len(value) != len(units):
            raise RuntimeError("submitted probability/value artifacts do not align with rebuilt units")

        if args.limit_issues:
            kept = (
                units[["issue", "issue_year"]]
                .drop_duplicates()
                .sort_values(["issue_year", "issue"])
                .groupby("issue_year", group_keys=False)
                .head(args.limit_issues)["issue"]
                .astype(str)
            )
            keep_mask = units["issue"].astype(str).isin(set(kept))
            units = units.loc[keep_mask].copy()
            probabilities = probabilities.reindex(units.index)
            value = value.reindex(units.index)
            tensor = tensor[tensor["issue"].astype(str).isin(set(kept))].copy()

        print("[dynamic-1] pre-event issue states")
        states = build_issue_states(units, value, probabilities, horizon=args.horizon)
        states.to_csv(output / "dynamic_issue_states.csv", index=False)

        print("[dynamic-2] seed-aggregated action counterfactuals")
        counterfactuals = evaluate_counterfactual_actions(
            units,
            value,
            probabilities,
            tensor,
            states,
            actions=default_action_space(),
            horizon=args.horizon,
            seeds=SEEDS,
        )
        counterfactuals.to_parquet(output / "dynamic_action_counterfactuals.parquet", index=False)
    learning = join_states_and_actions(states, counterfactuals)

    fit = learning[learning["temporal_role"].eq("fit")].copy()
    tune = learning[learning["temporal_role"].eq("tune")].copy()
    calibration = learning[learning["temporal_role"].eq("calibration")].copy()
    if min(fit["issue"].nunique(), tune["issue"].nunique(), calibration["issue"].nunique()) < 2:
        raise RuntimeError("chronological roles do not support dynamic policy learning")

    print("[dynamic-3] fit through 2021; select family on 2022")
    fit_bundle = fit_action_models(fit)
    family, tune_metrics, tune_predictions_all = family_selection_receipt(fit_bundle, tune)
    tune_predictions = tune_predictions_all[tune_predictions_all["model_family"].eq(family)].copy()
    tune_selected = select_policy_actions(tune_predictions, tune, allow_no_bet=False)
    tune_selected["evaluation_role"] = "TUNE_2022_OUT_OF_TIME"
    tune_selected["policy_arm"] = "LEARNED_ACTIVE_POLICY"

    print(f"[dynamic-4] refit {family} through 2022; freeze pre-outcome 2023 actions")
    refit = pd.concat([fit, tune], ignore_index=True)
    frozen_bundle = fit_action_models(refit, families=(family,))
    calibration_predictions = predict_action_models(frozen_bundle, calibration, family)
    calibration_selected = select_policy_actions(
        calibration_predictions, calibration, allow_no_bet=False
    )
    calibration_selected["evaluation_role"] = "CALIBRATION_2023_OUT_OF_TIME"
    calibration_selected["policy_arm"] = "LEARNED_ACTIVE_POLICY"
    calibration_safe = select_policy_actions(calibration_predictions, calibration, allow_no_bet=True)
    calibration_safe["evaluation_role"] = "CALIBRATION_2023_OUT_OF_TIME"
    calibration_safe["policy_arm"] = "CAPITAL_SAFE_POLICY"

    predictions = pd.concat(
        [
            tune_predictions.assign(evaluation_role="TUNE_2022_OUT_OF_TIME"),
            calibration_predictions.assign(evaluation_role="CALIBRATION_2023_OUT_OF_TIME"),
        ],
        ignore_index=True,
    )
    predictions.to_parquet(output / "dynamic_policy_predictions.parquet", index=False)
    selected = pd.concat([tune_selected, calibration_selected, calibration_safe], ignore_index=True)
    selected.to_csv(output / "dynamic_selected_actions.csv", index=False)

    calibration_cf = counterfactuals[counterfactuals["temporal_role"].eq("calibration")]
    fixed = fixed_control_results(calibration_cf).sort_values(["issue_year", "issue"])
    oracle = oracle_diagnostic(calibration_cf)
    calibration_selected = calibration_selected.merge(oracle, on="issue", how="left", validate="one_to_one")
    calibration_safe = calibration_safe.merge(oracle, on="issue", how="left", validate="one_to_one")
    calibration_selected.to_csv(output / "dynamic_calibration_actions.csv", index=False)
    calibration_safe.to_csv(output / "dynamic_calibration_safe_actions.csv", index=False)

    dynamic_path, dynamic_summary = _capital_path(calibration_selected)
    safe_path, safe_summary = _capital_path(calibration_safe)
    fixed_path, fixed_summary = _capital_path(fixed)
    dynamic_path["arm"] = "LEARNED_DYNAMIC_POLICY"
    safe_path["arm"] = "CAPITAL_SAFE_POLICY"
    fixed_path["arm"] = "FIXED_N7_K8_TOP_VALUE"
    pd.concat([dynamic_path, safe_path, fixed_path], ignore_index=True).to_csv(
        output / "dynamic_matched_capital_paths.csv", index=False
    )
    lift = matched_lift(dynamic_summary, fixed_summary["ending_capital"])
    active = calibration_selected["generator"].ne("NO_BET")
    unique_actions = int(calibration_selected["action_key"].nunique())
    state_conditioned = unique_actions >= 2 and bool(active.any())

    previous_decision_path = output / "decision.json"
    previous = (
        json.loads(previous_decision_path.read_text(encoding="utf-8"))
        if previous_decision_path.exists()
        else {}
    )
    upstream_probability = previous.get(
        "upstream_probability_gate_a",
        {
            "frozen_identity": previous.get("GATE_A_FROZEN_IDENTITY"),
            "tune_compare": previous.get("tune_compare"),
            "calibration_support_2023": previous.get("gate_a_calibration_support_2023"),
        },
    )
    promoted = bool(
        state_conditioned
        and lift["matched_lift"] > 0.0
        and calibration_selected["mean_pnl"].sum() > fixed["mean_pnl"].sum()
    )
    decision = {
        "contract": "BJ-UNIFIED-FULL-CYCLE-HIST-001/v3-dynamic-method-rework",
        "GATE_A_DYNAMIC_MAPPING_VALID": state_conditioned,
        "GATE_A_DYNAMIC_POLICY_PROMOTED": promoted,
        "GATE_A_DISPOSITION": (
            "PROMOTE_DYNAMIC_POLICY" if promoted else "RETAIN_FIXED_CONTROL_NO_PROMOTION"
        ),
        "GATE_A_DYNAMIC_POLICY_FAMILY": family,
        "GATE_A_DYNAMIC_POLICY_IDENTITY": (
            f"ACTION_CONDITIONED_{family}_N_K_GENERATOR_WITH_NO_BET"
            if state_conditioned
            else "DYNAMIC_POLICY_NOT_IDENTIFIED_RETAIN_FIXED_CONTROL"
        ),
        "probability_identity_inherited": "MARKET_ONLY_CELL",
        "horizon": args.horizon,
        "action_surface": {
            "action_count": len(default_action_space()),
            "n": sorted({action.n for action in default_action_space() if action.n}),
            "k": sorted({action.k for action in default_action_space() if action.k}),
            "generators": sorted({action.generator for action in default_action_space()}),
            "k_boundary": "EXPERIMENTAL_ANCHORS_NOT_OPERATIONAL_STAKE_CAP",
        },
        "independent_unit": "Beijing_issue",
        "seed_semantics": "NUISANCE_REPLICATION_AGGREGATED_WITHIN_ISSUE_ACTION",
        "feature_columns": list(action_features(fit).columns),
        "model_family_selection_2022": tune_metrics,
        "selected_action_unique_count_2023": unique_actions,
        "selected_action_entropy_2023": _choice_entropy(calibration_selected),
        "selected_active_fraction_2023": float(active.mean()),
        "tune_2022_selection_diagnostics": _selection_diagnostics(tune_selected),
        "calibration_2023_selection_diagnostics": _selection_diagnostics(
            calibration_selected
        ),
        "dynamic_capital_2023": dynamic_summary,
        "capital_safe_policy_2023": safe_summary,
        "fixed_control_capital_2023": fixed_summary,
        "matched_lift_vs_fixed_control": lift,
        "oracle_diagnostic_only": {
            "mean_oracle_pnl": float(calibration_selected["oracle_mean_pnl"].mean()),
            "mean_selected_pnl": float(calibration_selected["mean_pnl"].mean()),
            "not_policy_input": True,
        },
        "seal": {"rows_opened_2024": 0, "gate_b_authorized": False},
        "upstream_probability_gate_a": upstream_probability,
    }
    serialized_decision = json.dumps(decision, indent=2, sort_keys=True)
    (output / "dynamic_decision.json").write_text(serialized_decision, encoding="utf-8")
    previous_decision_path.write_text(serialized_decision, encoding="utf-8")
    joblib.dump(
        {
            "family": family,
            "bundle": frozen_bundle,
            "action_surface": default_action_space(),
            "horizon": args.horizon,
        },
        output / "dynamic_policy.joblib",
    )
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
