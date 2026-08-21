#!/usr/bin/env python3
"""Test whether pre-event issue data can predict reliable N-specific residuals."""

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
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue284.aggregate import AGGREGATE_FEATURES, build_issue_n_table  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=ROOT,
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--first-validation-year", type=int, default=2018)
    parser.add_argument("--last-validation-year", type=int, default=2023)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    labels = pd.read_parquet(output / "full_subset_labels.parquet")
    state = pd.read_parquet(
        args.artifact_root.resolve() / "results/issue-279/action_features.parquet"
    )
    table = build_issue_n_table(labels, state)
    if table["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ residual-model seal violated")
    feature_columns = list(AGGREGATE_FEATURES)
    predictions: list[pd.DataFrame] = []
    fold_receipts: list[dict[str, float | int]] = []
    for year in range(args.first_validation_year, args.last_validation_year + 1):
        train = table["issue_year"].lt(year)
        validation = table["issue_year"].eq(year)
        if table.loc[train, "issue"].nunique() < 100 or not validation.any():
            continue
        x_train = table.loc[train, feature_columns]
        y_train = table.loc[train, "residual_to_expected"]
        x_validation = table.loc[validation, feature_columns]
        models = {
            "RIDGE": TransformedTargetRegressor(
                regressor=make_pipeline(
                    SimpleImputer(strategy="median", add_indicator=True),
                    StandardScaler(),
                    Ridge(alpha=100.0),
                ),
                transformer=StandardScaler(),
            ),
            "HIST_GB": HistGradientBoostingRegressor(
                learning_rate=0.04,
                max_iter=150,
                max_leaf_nodes=7,
                min_samples_leaf=40,
                l2_regularization=10.0,
                random_state=284,
            ),
        }
        fold = table.loc[
            validation,
            [
                "issue",
                "issue_year",
                "n",
                "expected_mean",
                "realized_mean",
                "n7_realized_mean",
                "residual_to_expected",
            ],
        ].copy()
        prior = y_train.groupby(table.loc[train, "n"]).mean()
        fold["predicted_residual_N_PRIOR"] = fold["n"].map(prior).fillna(
            float(y_train.mean())
        )
        fold["predicted_value_EXPECTED_ONLY"] = fold["expected_mean"]
        fold["predicted_value_N_PRIOR"] = (
            fold["expected_mean"] + fold["predicted_residual_N_PRIOR"]
        )
        for name, model in models.items():
            model.fit(x_train, y_train)
            residual = model.predict(x_validation)
            fold[f"predicted_residual_{name}"] = residual
            fold[f"predicted_value_{name}"] = fold["expected_mean"] + residual
        predictions.append(fold)
        fold_receipts.append(
            {
                "validation_year": year,
                "training_issues": int(table.loc[train, "issue"].nunique()),
                "validation_issues": int(table.loc[validation, "issue"].nunique()),
                "training_rows": int(train.sum()),
                "validation_rows": int(validation.sum()),
            }
        )
    oof = pd.concat(predictions, ignore_index=True)
    policies = _select_policies(oof)
    metrics = _policy_metrics(policies)
    diagnostics = _prediction_diagnostics(oof)
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-issue-n-residual-oof",
        "feature_columns": feature_columns,
        "target": "issue×N mean realized CNY100 P&L minus pre-event expected CNY100 P&L",
        "folds": fold_receipts,
        "sealed_years_opened": [],
        "primary_question": "does issue Data improve N choice beyond expected value and N prior",
    }
    _atomic_parquet(table, output / "issue_n_distribution_table.parquet")
    _atomic_parquet(oof, output / "issue_n_residual_oof_predictions.parquet")
    _atomic_parquet(policies, output / "issue_n_residual_oof_selected.parquet")
    _atomic_csv(metrics, output / "issue_n_residual_oof_metrics.csv")
    _atomic_csv(diagnostics, output / "issue_n_residual_oof_diagnostics.csv")
    _atomic_json(receipt, output / "issue_n_residual_oof_receipt.json")
    print(metrics.to_string(index=False), flush=True)
    print("\nPrediction diagnostics", flush=True)
    print(diagnostics.to_string(index=False), flush=True)
    print("\n" + json.dumps(receipt, indent=2), flush=True)
    return 0


def _select_policies(oof: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    fixed = oof.loc[oof["n"].eq(7)].copy()
    fixed["policy"] = "FIXED_N7"
    rows.append(fixed)
    for name in ("EXPECTED_ONLY", "N_PRIOR", "RIDGE", "HIST_GB"):
        score = f"predicted_value_{name}"
        selected = (
            oof.sort_values(["issue", score, "n"], ascending=[True, False, True])
            .groupby("issue", as_index=False)
            .head(1)
            .copy()
        )
        selected["policy"] = name
        rows.append(selected)
    return pd.concat(rows, ignore_index=True).sort_values(
        ["issue_year", "issue", "policy"]
    )


def _policy_metrics(selected: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for policy, frame in selected.groupby("policy", sort=False):
        frame = frame.sort_values(["issue_year", "issue"])
        pnl = frame["realized_mean"].to_numpy(float)
        lift = (frame["realized_mean"] - frame["n7_realized_mean"]).to_numpy(float)
        positive_lift = lift[lift > 0]
        capital = 100_000.0 + np.cumsum(pnl)
        peak = np.maximum.accumulate(np.r_[100_000.0, capital])[:-1]
        drawdown = (peak - capital) / peak
        yearly_lift = frame.assign(lift=lift).groupby("issue_year")["lift"].sum()
        rows.append(
            {
                "policy": policy,
                "issues": int(len(frame)),
                "mean_roi_pct": float(pnl.mean()),
                "ending_capital_cny": float(100_000.0 + pnl.sum()),
                "matched_lift_cny100": float(lift.sum()),
                "ex_largest_matched_lift_cny100": float(
                    lift.sum()
                    - (positive_lift.max() if len(positive_lift) else 0.0)
                ),
                "positive_lift_years": int((yearly_lift > 0).sum()),
                "max_drawdown_fraction": float(drawdown.max(initial=0.0)),
                "selected_n_entropy": _entropy(frame["n"]),
            }
        )
    return pd.DataFrame(rows)


def _prediction_diagnostics(oof: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float | str]] = []
    for name in ("EXPECTED_ONLY", "N_PRIOR", "RIDGE", "HIST_GB"):
        score = oof[f"predicted_value_{name}"]
        rows.append(
            {
                "model": name,
                "overall_spearman": float(score.corr(oof["realized_mean"], method="spearman")),
                "within_n_spearman_mean": float(
                    np.nanmean(
                        [
                            group[f"predicted_value_{name}"].corr(
                                group["realized_mean"], method="spearman"
                            )
                            for _, group in oof.groupby("n")
                        ]
                    )
                ),
                "residual_spearman": float(
                    oof.get(f"predicted_residual_{name}", pd.Series(np.nan, index=oof.index)).corr(
                        oof["residual_to_expected"], method="spearman"
                    )
                ),
            }
        )
    return pd.DataFrame(rows)


def _entropy(values: pd.Series) -> float:
    probability = values.value_counts(normalize=True).to_numpy(float)
    return float(-(probability * np.log(probability)).sum())


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
