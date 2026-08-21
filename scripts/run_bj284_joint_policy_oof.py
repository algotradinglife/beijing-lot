#!/usr/bin/env python3
"""Run the #284 Data-conditioned joint-action expanding-window OOF prototype."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue284.joint_policy import (  # noqa: E402
    JOINT_FEATURES,
    build_joint_action_table,
    select_policy,
)
from issue282.features import ISSUE_STATE_FEATURES  # noqa: E402

ACTION_ONLY_FEATURES = (
    "action_n",
    "action_n_fraction",
    "action_log2_k",
    "action_generator_top",
    "action_generator_weighted",
    "action_family_uniform",
    "action_family_value",
    "action_family_divergence",
    "action_family_shape",
    "action_family_ensemble",
)
STATE_ACTION_FEATURES = (
    *ISSUE_STATE_FEATURES,
    *ACTION_ONLY_FEATURES,
    "action_n_x_value",
    "action_n_x_divergence",
    "action_k_x_probability_concentration",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("/home/drwho1985/.cache/codex-pi/bj282-policy"),
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--first-validation-year", type=int, default=2018)
    parser.add_argument("--last-validation-year", type=int, default=2023)
    parser.add_argument("--bootstrap-draws", type=int, default=2_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    raw = pd.read_parquet(output / "joint_action_grid_confirmatory.parquet")
    state = pd.read_parquet(
        args.artifact_root.resolve() / "results/issue-279/action_features.parquet"
    )
    table = build_joint_action_table(raw, state)
    if table["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ joint-policy seal violated")
    predictions: list[pd.DataFrame] = []
    fold_receipts: list[dict[str, float | int]] = []
    feature_columns = list(JOINT_FEATURES)
    for validation_year in range(
        args.first_validation_year, args.last_validation_year + 1
    ):
        train_mask = table["issue_year"].lt(validation_year)
        validation_mask = table["issue_year"].eq(validation_year)
        if table.loc[train_mask, "issue"].nunique() < 100 or not validation_mask.any():
            continue
        train = table.loc[train_mask].copy()
        validation = table.loc[validation_mask].copy()
        x_train = train[feature_columns]
        x_validation = validation[feature_columns]
        target = np.arcsinh(train["realized_lift_pct"].to_numpy(float) / 100.0)
        weights = train["issue_training_weight"].to_numpy(float)
        model_weights = weights / weights.mean()
        models = _models(validation_year)
        fold = validation[
            [
                "issue",
                "issue_year",
                "action_key",
                "n",
                "generator",
                "requested_k",
                "realized_roi_pct",
                "realized_lift_pct",
                "baseline_realized_roi_pct",
                "expected_mean",
                "expected_lift_to_baseline",
                "subsets",
                "families",
            ]
        ].copy()
        fold["predicted_lift_EXPECTED_ONLY"] = validation[
            "expected_lift_to_baseline"
        ].to_numpy(float)
        action_prior = train.groupby("action_key")["realized_lift_pct"].median()
        fold["predicted_lift_ACTION_MEDIAN"] = validation["action_key"].map(
            action_prior
        ).fillna(0.0)
        feature_sets = {
            "RIDGE": feature_columns,
            "HIST_ACTION": list(ACTION_ONLY_FEATURES),
            "HIST_STATE": list(STATE_ACTION_FEATURES),
            "HIST_FULL": feature_columns,
            "MLP": feature_columns,
        }
        for name, model_features in feature_sets.items():
            model = models[name]
            if name.startswith("HIST_"):
                model.fit(
                    train[model_features], target, sample_weight=model_weights
                )
            elif name == "RIDGE":
                model.fit(
                    train[model_features],
                    target,
                    ridge__sample_weight=model_weights,
                )
            elif name == "MLP":
                model.fit(
                    train[model_features],
                    target,
                    mlpregressor__sample_weight=model_weights,
                )
            else:
                raise RuntimeError(f"unhandled model fit semantics: {name}")
            fold[f"predicted_lift_{name}"] = (
                np.sinh(model.predict(validation[model_features])) * 100.0
            )
        quantile = models["HIST_Q10"]
        quantile.fit(
            x_train,
            train["realized_lift_pct"].to_numpy(float),
            sample_weight=model_weights,
        )
        fold["predicted_lift_q10"] = quantile.predict(x_validation)
        predictions.append(fold)
        fold_receipts.append(
            {
                "validation_year": validation_year,
                "training_issues": int(train["issue"].nunique()),
                "validation_issues": int(validation["issue"].nunique()),
                "training_rows": int(len(train)),
                "validation_rows": int(len(validation)),
            }
        )
    oof = pd.concat(predictions, ignore_index=True)
    selected = _select_all_policies(oof)
    metrics = _policy_metrics(
        selected, draws=args.bootstrap_draws, seed=284_950
    )
    diagnostics = _prediction_diagnostics(oof)
    action_counts = (
        selected.groupby(["policy", "action_key"], as_index=False)
        .agg(issues=("issue", "nunique"), realized_roi_pct=("realized_roi_pct", "mean"))
        .sort_values(["policy", "issues"], ascending=[True, False])
    )
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-joint-policy-oof",
        "experimental_unit": "Beijing issue",
        "target": (
            "nuisance-averaged issue/action realized CNY100 lift versus fixed "
            "N7_WEIGHTED_WR_K128_FENSEMBLE baseline"
        ),
        "training_weight": (
            "each issue has equal aggregate weight; weights are rescaled to "
            "mean one before fitting so estimator regularization is invariant "
            "to row count"
        ),
        "feature_columns": feature_columns,
        "models": {
            "RIDGE": "sklearn Ridge on asinh lift",
            "HIST_ACTION": "action geometry only HistGradientBoosting control",
            "HIST_STATE": "issue state + action geometry HistGradientBoosting",
            "HIST_FULL": "state + action + expected surface HistGradientBoosting",
            "MLP": "sklearn MLPRegressor(64,32) on asinh lift",
            "HIST_Q10": "sklearn HistGradientBoosting quantile=0.10 on raw lift",
        },
        "selection": (
            "forced argmax plus q10<=0 fallback to fixed baseline; random subset "
            "and stream seed are never actions"
        ),
        "folds": fold_receipts,
        "sealed_years_opened": [],
        "accepted_baseline_note": (
            "the matched panel baseline is not a replacement for external "
            "BEST_FULL -9.47%"
        ),
    }
    _atomic_parquet(table, output / "joint_policy_action_table.parquet")
    _atomic_parquet(oof, output / "joint_policy_oof_predictions.parquet")
    _atomic_parquet(selected, output / "joint_policy_oof_selected.parquet")
    _atomic_csv(metrics, output / "joint_policy_oof_metrics.csv")
    _atomic_csv(diagnostics, output / "joint_policy_oof_diagnostics.csv")
    _atomic_csv(action_counts, output / "joint_policy_oof_action_counts.csv")
    _atomic_json(receipt, output / "joint_policy_oof_receipt.json")
    print(metrics.to_string(index=False), flush=True)
    print("\nPrediction diagnostics", flush=True)
    print(diagnostics.to_string(index=False), flush=True)
    print("\n" + json.dumps(receipt, indent=2), flush=True)
    return 0


def _models(year: int) -> dict[str, object]:
    return {
        "RIDGE": TransformedTargetRegressor(
            regressor=make_pipeline(
                SimpleImputer(strategy="median", add_indicator=True),
                StandardScaler(),
                Ridge(alpha=100.0),
            ),
            transformer=StandardScaler(),
        ),
        **{
            name: HistGradientBoostingRegressor(
                loss="absolute_error",
                learning_rate=0.04,
                max_iter=150,
                max_leaf_nodes=7,
                min_samples_leaf=80,
                l2_regularization=20.0,
                random_state=284_000 + year + offset,
            )
            for offset, name in enumerate(
                ("HIST_ACTION", "HIST_STATE", "HIST_FULL")
            )
        },
        "MLP": make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True),
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(64, 32),
                activation="relu",
                alpha=5.0,
                batch_size=256,
                learning_rate_init=0.001,
                max_iter=250,
                early_stopping=True,
                validation_fraction=0.15,
                n_iter_no_change=20,
                random_state=284_000 + year,
            ),
        ),
        "HIST_Q10": HistGradientBoostingRegressor(
            loss="quantile",
            quantile=0.10,
            learning_rate=0.04,
            max_iter=150,
            max_leaf_nodes=7,
            min_samples_leaf=80,
            l2_regularization=20.0,
            random_state=285_000 + year,
        ),
    }


def _select_all_policies(oof: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for action_key, policy in (
        ("N7_WEIGHTED_WR_K128_FENSEMBLE", "FIXED_BASELINE"),
        ("N7_TOP_VALUE_K8_FENSEMBLE", "FIXED_N7_TOP_K8"),
        ("N7_TOP_VALUE_K512_FENSEMBLE", "FIXED_N7_TOP_K512"),
    ):
        fixed = oof.loc[oof["action_key"].eq(action_key)].copy()
        fixed["policy"] = policy
        fixed["used_fallback"] = False
        rows.append(fixed)
    for model in (
        "EXPECTED_ONLY",
        "ACTION_MEDIAN",
        "RIDGE",
        "HIST_ACTION",
        "HIST_STATE",
        "HIST_FULL",
        "MLP",
    ):
        score = f"predicted_lift_{model}"
        rows.append(
            select_policy(oof, score_column=score, policy=f"{model}_FORCED")
        )
        if model in {"RIDGE", "HIST_ACTION", "HIST_STATE", "HIST_FULL", "MLP"}:
            rows.append(
                select_policy(
                    oof,
                    score_column=score,
                    fallback_column="predicted_lift_q10",
                    policy=f"{model}_Q10_FALLBACK",
                )
            )
    return pd.concat(rows, ignore_index=True).sort_values(
        ["issue_year", "issue", "policy"]
    )


def _policy_metrics(
    selected: pd.DataFrame, *, draws: int, seed: int
) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    rng = np.random.default_rng(seed)
    for policy, frame in selected.groupby("policy", sort=False):
        frame = frame.sort_values(["issue_year", "issue"])
        pnl = frame["realized_roi_pct"].to_numpy(float)
        lift = frame["realized_lift_pct"].to_numpy(float)
        boot = np.empty(draws, dtype=float)
        for draw in range(draws):
            boot[draw] = rng.choice(lift, len(lift), replace=True).mean()
        positive_lift = lift[lift > 0]
        capital = 100_000.0 + np.cumsum(pnl)
        prior_peak = np.maximum.accumulate(np.r_[100_000.0, capital])[:-1]
        drawdown = (prior_peak - capital) / prior_peak
        yearly_lift = frame.assign(lift=lift).groupby("issue_year")["lift"].sum()
        rows.append(
            {
                "policy": policy,
                "issues": len(frame),
                "mean_roi_pct": pnl.mean(),
                "ending_capital_cny": capital[-1],
                "mean_matched_lift_pct": lift.mean(),
                "matched_lift_cny100": lift.sum(),
                "ex_largest_matched_lift_cny100": (
                    lift.sum() - (positive_lift.max() if len(positive_lift) else 0.0)
                ),
                "bootstrap_lift_low_pct": np.quantile(boot, 0.025),
                "bootstrap_lift_high_pct": np.quantile(boot, 0.975),
                "bootstrap_probability_positive_lift": np.mean(boot > 0),
                "positive_lift_years": int((yearly_lift > 0).sum()),
                "max_drawdown_fraction": drawdown.max(initial=0.0),
                "longest_losing_issue_streak": _longest_run(pnl < 0),
                "worst_5_issue_pnl": _worst_window(pnl, 5),
                "worst_10_issue_pnl": _worst_window(pnl, 10),
                "worst_20_issue_pnl": _worst_window(pnl, 20),
                "fallback_fraction": frame["used_fallback"].mean(),
                "selected_action_entropy": _entropy(frame["action_key"]),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["mean_matched_lift_pct", "mean_roi_pct"], ascending=False
    )


def _prediction_diagnostics(oof: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    for model in (
        "EXPECTED_ONLY",
        "ACTION_MEDIAN",
        "RIDGE",
        "HIST_ACTION",
        "HIST_STATE",
        "HIST_FULL",
        "MLP",
    ):
        score = oof[f"predicted_lift_{model}"]
        rows.append(
            {
                "model": model,
                "overall_spearman": score.corr(oof["realized_lift_pct"], method="spearman"),
                "within_action_spearman_mean": np.nanmean(
                    [
                        group[f"predicted_lift_{model}"].corr(
                            group["realized_lift_pct"], method="spearman"
                        )
                        for _, group in oof.groupby("action_key")
                    ]
                ),
                "within_issue_spearman_mean": np.nanmean(
                    [
                        group[f"predicted_lift_{model}"].corr(
                            group["realized_lift_pct"], method="spearman"
                        )
                        for _, group in oof.groupby("issue")
                    ]
                ),
                "q10_empirical_below_fraction": np.mean(
                    oof["realized_lift_pct"] < oof["predicted_lift_q10"]
                ),
            }
        )
    return pd.DataFrame(rows)


def _entropy(values: pd.Series) -> float:
    probability = values.value_counts(normalize=True).to_numpy(float)
    return float(-(probability * np.log(probability)).sum())


def _longest_run(mask: np.ndarray) -> int:
    longest = current = 0
    for value in mask:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _worst_window(values: np.ndarray, width: int) -> float:
    if len(values) < width:
        return float("nan")
    return float(pd.Series(values).rolling(width).sum().min())


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(".tmp.csv")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(".tmp.parquet")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
