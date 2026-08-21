#!/usr/bin/env python3
"""Learn when to use divergence ranking for the confirmed N9/K64 action."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from issue282.features import ISSUE_STATE_FEATURES
from issue284.mode_policy import apply_mode_policy, build_mode_learning_table

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("/home/drwho1985/.cache/codex-pi/bj282-policy"),
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--bootstrap-draws", type=int, default=5_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    actions = pd.read_csv(output / "divergence_n9_div_k64_issue_actions.csv")
    states = pd.read_parquet(
        args.artifact_root.resolve() / "results/issue-279/action_features.parquet"
    )
    table = build_mode_learning_table(actions, states)
    if table["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ outcome row entered mode-policy learning")
    predictions: list[pd.DataFrame] = []
    folds: list[dict[str, int]] = []
    features = list(ISSUE_STATE_FEATURES)
    for year in range(2018, 2024):
        train = table.loc[table["issue_year"].lt(year)]
        validation = table.loc[table["issue_year"].eq(year)]
        if len(train) < 100 or validation.empty:
            continue
        x_train = train[features]
        x_validation = validation[features]
        target = np.arcsinh(train["realized_lift_pct"].to_numpy(float) / 100.0)
        fold = validation[
            [
                "issue",
                "issue_year",
                "CELL_VALUE",
                "DIVERGENCE_VALUE",
                "realized_lift_pct",
            ]
        ].copy()
        prior = float(train["realized_lift_pct"].mean())
        fold["PRIOR"] = prior
        for name, model in _models(year).items():
            if name == "HGB_Q10":
                model.fit(x_train, train["realized_lift_pct"].to_numpy(float))
                fold[name] = model.predict(x_validation)
            else:
                model.fit(x_train, target)
                fold[name] = np.sinh(model.predict(x_validation)) * 100.0
        predictions.append(fold)
        folds.append(
            {
                "validation_year": year,
                "training_issues": int(train["issue"].nunique()),
                "validation_issues": int(validation["issue"].nunique()),
            }
        )
    oof = pd.concat(predictions, ignore_index=True)
    policies = [
        apply_mode_policy(oof, np.full(len(oof), -1.0), policy="CELL_FIXED"),
        apply_mode_policy(oof, np.full(len(oof), 1.0), policy="DIVERGENCE_FIXED"),
    ]
    for name in ("PRIOR", "RIDGE", "HGB", "MLP", "HGB_Q10"):
        policies.append(apply_mode_policy(oof, oof[name].to_numpy(), policy=name))
    selected = pd.concat(policies, ignore_index=True)
    metrics = _metrics(selected, draws=args.bootstrap_draws, seed=284_997)
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-divergence-mode-oof",
        "fixed_action": "N9/DIVERGENCE_WEIGHTED/WEIGHTED_WR/K64",
        "target": "issue-level matched DIVERGENCE_VALUE minus CELL_VALUE ROI",
        "features": features,
        "folds": folds,
        "selection": "use DIVERGENCE_VALUE only when predicted matched lift > 0",
        "models": {
            "PRIOR": "expanding training mean lift",
            "RIDGE": "sklearn Ridge on asinh matched lift",
            "HGB": "sklearn HistGradientBoosting on asinh matched lift",
            "MLP": "sklearn MLPRegressor(32,16) on asinh matched lift",
            "HGB_Q10": "sklearn quantile HGB lower-bound fallback",
        },
        "sealed_years_opened": [],
    }
    _atomic_csv(oof, output / "divergence_mode_oof_predictions.csv")
    _atomic_csv(selected, output / "divergence_mode_oof_selected.csv")
    _atomic_csv(metrics, output / "divergence_mode_oof_metrics.csv")
    _atomic_json(receipt, output / "divergence_mode_oof_receipt.json")
    print(metrics.to_string(index=False), flush=True)
    print(json.dumps(receipt, indent=2), flush=True)
    return 0


def _models(year: int) -> dict[str, object]:
    return {
        "RIDGE": make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=10.0)
        ),
        "HGB": make_pipeline(
            SimpleImputer(strategy="median"),
            HistGradientBoostingRegressor(
                max_iter=120,
                max_leaf_nodes=12,
                learning_rate=0.05,
                l2_regularization=2.0,
                random_state=year,
            ),
        ),
        "MLP": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(32, 16),
                alpha=0.01,
                early_stopping=True,
                max_iter=300,
                random_state=year,
            ),
        ),
        "HGB_Q10": make_pipeline(
            SimpleImputer(strategy="median"),
            HistGradientBoostingRegressor(
                loss="quantile",
                quantile=0.10,
                max_iter=120,
                max_leaf_nodes=12,
                learning_rate=0.05,
                l2_regularization=2.0,
                random_state=year,
            ),
        ),
    }


def _metrics(selected: pd.DataFrame, *, draws: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float | int | str]] = []
    for policy, group in selected.groupby("policy", sort=True):
        group = group.sort_values(["issue_year", "issue"])
        roi = group["realized_roi_pct"].to_numpy(float)
        lift = group["matched_lift_to_cell_pct"].to_numpy(float)
        bootstrap = np.empty(draws, dtype=float)
        for draw in range(draws):
            bootstrap[draw] = rng.choice(lift, len(lift), replace=True).mean()
        capital = 100_000.0 + np.cumsum(roi)
        prior_peak = np.maximum.accumulate(np.r_[100_000.0, capital])[:-1]
        annual = group.groupby("issue_year")["matched_lift_to_cell_pct"].mean()
        rows.append(
            {
                "policy": policy,
                "issues": len(group),
                "mean_roi_pct": roi.mean(),
                "mean_lift_to_cell_pct": lift.mean(),
                "ex_largest_roi_pct": _ex_largest(roi),
                "ex_largest_lift_pct": _ex_largest(lift),
                "bootstrap_lift_low_pct": np.quantile(bootstrap, 0.025),
                "bootstrap_lift_high_pct": np.quantile(bootstrap, 0.975),
                "positive_lift_years": int((annual > 0).sum()),
                "divergence_fraction": group["selected_mode"]
                .eq("DIVERGENCE_VALUE")
                .mean(),
                "ending_capital_cny": capital[-1],
                "max_drawdown_fraction": ((prior_peak - capital) / prior_peak).max(),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_roi_pct", ascending=False)


def _ex_largest(values: np.ndarray) -> float:
    return float((values.sum() - values.max()) / (len(values) - 1))


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
