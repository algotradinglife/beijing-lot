#!/usr/bin/env python3
"""Run expanding-year joint base-action and selective-protection OOF policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue286.policy import chronological_capital_path, same_budget_random  # noqa: E402

CATEGORICAL = ["selector", "outcome_mode", "generator", "n", "k"]
CONTEXT = [
    "issue_match_count",
    "issue_probability_entropy_mean",
    "issue_probability_max_mean",
    "issue_divergence_abs_mean",
    "issue_divergence_abs_max",
    "issue_native_line_abs_mean",
    "issue_books_mean",
]
BASE_NUMERIC = ["ticket_probability_product", "ticket_divergence_sum", *CONTEXT]
CANDIDATE_NUMERIC = [
    "protected_leg",
    "selected_outcome_position",
    "alternative_outcome_position",
    "selected_probability",
    "alternative_probability",
    "probability_delta",
    "selected_divergence",
    "alternative_divergence",
    "divergence_delta",
    "match_entropy",
    "proposal_margin_delta",
    "parent_ticket_probability_product",
    "candidate_probability_product",
    *CONTEXT,
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "results/issue-286")
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-286")
    parser.add_argument("--oof-start", type=int, default=2019)
    parser.add_argument("--negative-sample-per-action", type=int, default=24)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    base = _base_action_table(source / "base_settlement_labels.parquet")
    sample_path = output / "candidate_training_sample.parquet"
    sample = _candidate_training_sample(
        source / "candidate_settlement_labels.parquet",
        negative_per_action=args.negative_sample_per_action,
    )
    base_weight_error = float(
        (base.groupby("issue")["issue_weight"].sum() - 1.0).abs().max()
    )
    candidate_weight_error = float(
        (sample.groupby("issue")["issue_weight"].sum() - 1.0).abs().max()
    )
    if max(base_weight_error, candidate_weight_error) > 1e-10:
        raise RuntimeError("issue-normalized training weights do not sum to one")
    if base["issue_year"].ge(2024).any() or sample["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ outcome leaked into OOF training")
    sample.to_parquet(sample_path, index=False)
    baseline = pd.read_parquet(source / "formal_baseline_n7_k8_market_top.parquet")
    baseline = baseline[["issue", "issue_year", "stake_cny_mean", "pnl_cny_mean"]].rename(
        columns={
            "stake_cny_mean": "formal_baseline_stake_cny",
            "pnl_cny_mean": "formal_baseline_pnl_cny",
        }
    )
    baseline["issue"] = baseline["issue"].astype(str)
    years = sorted(int(value) for value in base["issue_year"].unique())
    oof_years = [year for year in years if year >= args.oof_start]
    selections = []
    for year in oof_years:
        train_base = base[base["issue_year"].lt(year)].copy()
        test_base = base[base["issue_year"].eq(year)].copy()
        train_candidate = sample[sample["issue_year"].lt(year)].copy()
        test_candidate = pd.read_parquet(
            source / "candidate_settlement_labels.parquet",
            filters=[("issue_year", "==", year)],
        )
        if train_base.empty or train_candidate.empty or test_candidate.empty:
            continue
        for model_name in ("ACTION_RIDGE", "DATA_HGB"):
            base_features = CATEGORICAL + ([] if model_name == "ACTION_RIDGE" else BASE_NUMERIC)
            candidate_features = CATEGORICAL + (
                [] if model_name == "ACTION_RIDGE" else CANDIDATE_NUMERIC
            )
            base_model = _model(model_name, base_features)
            candidate_model = _model(model_name, candidate_features)
            base_model.fit(
                train_base[base_features],
                train_base["base_pnl_cny"],
                model__sample_weight=train_base["issue_weight"],
            )
            candidate_model.fit(
                train_candidate[candidate_features],
                train_candidate["pnl_cny"],
                model__sample_weight=train_candidate["issue_weight"],
            )
            scored_base = test_base.copy()
            scored_base["predicted_base_pnl_cny"] = base_model.predict(
                scored_base[base_features]
            )
            scored_candidate = test_candidate.copy()
            scored_candidate["predicted_candidate_pnl_cny"] = candidate_model.predict(
                scored_candidate[candidate_features]
            )
            selected = _select_joint_actions(scored_base, scored_candidate)
            selected["model"] = model_name
            selected["oof_year"] = year
            selected = _attach_exact_budget_controls(selected, scored_candidate, source)
            selections.append(selected)
            print(
                f"oof year={year} model={model_name} issues={len(selected)} "
                f"funded={int(selected['funded'].sum())} "
                f"protected={int(selected['funded_protection_count'].sum())}",
                flush=True,
            )
    selected = pd.concat(selections, ignore_index=True).merge(
        baseline, on=["issue", "issue_year"], how="left", validate="many_to_one"
    )
    selected_path = output / "joint_oof_selected_actions.parquet"
    selected.to_parquet(selected_path, index=False)
    paths = []
    metrics = []
    for model_name, group in selected.groupby("model", sort=True):
        for column, policy in (
            ("actual_total_pnl_cny", "LEARNED_JOINT"),
            ("base_pnl_cny", "SELECTED_BASE_NO_PROTECTION"),
            ("random_control_total_pnl_cny", "SAME_BUDGET_RANDOM"),
            ("continuation_control_total_pnl_cny", "SAME_BUDGET_CONTINUATION"),
            ("adverse_control_total_pnl_cny", "SAME_BUDGET_ADVERSE_HEURISTIC"),
            ("oracle_control_total_pnl_cny", "UNATTAINABLE_ORACLE_UPPER_BOUND"),
            ("formal_baseline_pnl_cny", "FORMAL_N7_K8_MARKET_TOP"),
        ):
            path = chronological_capital_path(group, pnl_column=column)
            path["model"] = model_name
            path["policy"] = policy
            paths.append(path[["issue", "issue_year", column, "capital_cny", "model", "policy"]])
            metrics.append(_metrics(path, column, model_name, policy))
    path_table = pd.concat(paths, ignore_index=True)
    metric_table = pd.DataFrame(metrics)
    path_path = output / "joint_oof_capital_paths.csv"
    metric_path = output / "joint_oof_metrics.csv"
    path_table.to_csv(path_path, index=False)
    metric_table.to_csv(metric_path, index=False)
    settlement_receipt = json.loads((source / "settlement_receipt.json").read_text())
    receipt = {
        "contract": "BJ-UNIFIED-JOINT-PROTECTION-001/oof-v1",
        "oof_years": oof_years,
        "models": ["ACTION_RIDGE", "DATA_HGB"],
        "protection_shares": [0.0, 0.1, 0.25, 0.5, 1.0],
        "candidate_negative_sample_per_issue_action": args.negative_sample_per_action,
        "candidate_sample_rows": len(sample),
        "issue_weighting": "EACH_TRAINING_ISSUE_SUMS_TO_ONE",
        "maximum_base_issue_weight_error": base_weight_error,
        "maximum_candidate_issue_weight_error": candidate_weight_error,
        "formal_baseline": "SALL_OMARKET_N7_TOP_VALUE_K8",
        "cash_action": True,
        "settlement_fields_in_inputs": [],
        "input_sha256": {
            "settlement_labels": settlement_receipt["settlement_output_sha256"],
            "formal_baseline": _sha256(source / "formal_baseline_n7_k8_market_top.parquet"),
            "candidate_training_sample": _sha256(sample_path),
        },
        "output_sha256": {
            "selected_actions": _sha256(selected_path),
            "capital_paths": _sha256(path_path),
            "metrics": _sha256(metric_path),
        },
    }
    _atomic_json(receipt, output / "joint_oof_receipt.json")
    print(metric_table.to_string(index=False), flush=True)
    return 0


def _base_action_table(path: Path) -> pd.DataFrame:
    tickets = pd.read_parquet(path)
    valid = tickets[tickets["settlement_valid"]].copy()
    aggregations = {
        "base_stake_cny": ("stake_cny", "sum"),
        "base_gross_cny": ("gross_cny", "sum"),
        "base_pnl_cny": ("pnl_cny", "sum"),
        "ticket_probability_product": ("ticket_probability_product", "mean"),
        "ticket_divergence_sum": ("ticket_divergence_sum", "mean"),
    }
    for column in [*CATEGORICAL, *CONTEXT]:
        aggregations[column] = (column, "first")
    table = valid.groupby(
        ["issue", "issue_year", "subset_id", "action_key"], as_index=False
    ).agg(**aggregations)
    table["issue_weight"] = 1.0 / table.groupby("issue")["issue"].transform("size")
    return table


def _candidate_training_sample(path: Path, *, negative_per_action: int) -> pd.DataFrame:
    frames = []
    columns = [
        "issue",
        "issue_year",
        "subset_id",
        "action_key",
        "candidate_identity",
        "hit",
        "pnl_cny",
        *CATEGORICAL,
        *CANDIDATE_NUMERIC,
    ]
    for year in range(2014, 2024):
        frame = pd.read_parquet(path, filters=[("issue_year", "==", year)], columns=columns)
        if frame.empty:
            continue
        positive = frame[frame["hit"].eq(1)].copy()
        negative = frame[frame["hit"].eq(0)].copy()
        counts = negative.groupby(["issue", "action_key"])["issue"].transform("size")
        negative["_population"] = counts
        negative["_hash"] = pd.util.hash_pandas_object(
            negative[["issue", "action_key", "candidate_identity"]], index=False
        ).to_numpy()
        negative = (
            negative.sort_values(["issue", "action_key", "_hash"])
            .groupby(["issue", "action_key"], as_index=False)
            .head(negative_per_action)
        )
        sampled_counts = negative.groupby(["issue", "action_key"])["issue"].transform("size")
        negative["sampling_weight"] = negative["_population"] / sampled_counts
        positive["sampling_weight"] = 1.0
        frames.append(pd.concat([positive, negative.drop(columns=["_hash", "_population"])], ignore_index=True))
    sample = pd.concat(frames, ignore_index=True)
    sample["issue_weight"] = sample["sampling_weight"] / sample.groupby("issue")[
        "sampling_weight"
    ].transform("sum")
    return sample


def _model(name: str, features: list[str]) -> Pipeline:
    categorical = [column for column in CATEGORICAL if column in features]
    numeric = [column for column in features if column not in categorical]
    transformer = ColumnTransformer(
        [
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical),
            ("numeric", StandardScaler(), numeric),
        ],
        remainder="drop",
    )
    estimator = (
        Ridge(alpha=10.0)
        if name == "ACTION_RIDGE"
        else HistGradientBoostingRegressor(
            max_iter=120,
            max_leaf_nodes=31,
            learning_rate=0.05,
            l2_regularization=10.0,
            random_state=286_001,
        )
    )
    return Pipeline([("features", transformer), ("model", estimator)])


def _select_joint_actions(base: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    key = ["issue", "issue_year", "subset_id", "action_key"]
    ranked = candidates.loc[candidates["predicted_candidate_pnl_cny"].gt(0)].copy()
    ranked = ranked.sort_values(
        [*key, "predicted_candidate_pnl_cny", "candidate_identity"],
        ascending=[True, True, True, True, False, True],
    )
    ranked["within_action_rank"] = ranked.groupby(key).cumcount() + 1
    ranked["predicted_prefix_pnl"] = ranked.groupby(key)[
        "predicted_candidate_pnl_cny"
    ].cumsum()
    ranked["actual_prefix_pnl"] = ranked.groupby(key)["pnl_cny"].cumsum()
    rows = []
    for share in (0.0, 0.1, 0.25, 0.5, 1.0):
        policy = base.copy()
        policy["protection_share"] = share
        if share == 0:
            policy["funded_protection_count"] = 0
            policy["predicted_protection_pnl_cny"] = 0.0
            policy["actual_protection_pnl_cny"] = 0.0
        else:
            eligible = ranked.loc[
                ranked["within_action_rank"].le(np.floor(ranked["k"] * share))
            ]
            prefixes = eligible.groupby(key, as_index=False).tail(1)[
                [*key, "within_action_rank", "predicted_prefix_pnl", "actual_prefix_pnl"]
            ]
            policy = policy.merge(prefixes, on=key, how="left")
            policy["funded_protection_count"] = policy["within_action_rank"].fillna(0).astype(int)
            policy["predicted_protection_pnl_cny"] = policy["predicted_prefix_pnl"].fillna(0.0)
            policy["actual_protection_pnl_cny"] = policy["actual_prefix_pnl"].fillna(0.0)
        policy["predicted_total_pnl_cny"] = (
            policy["predicted_base_pnl_cny"] + policy["predicted_protection_pnl_cny"]
        )
        policy["actual_total_pnl_cny"] = policy["base_pnl_cny"] + policy["actual_protection_pnl_cny"]
        rows.append(policy)
    surface = pd.concat(rows, ignore_index=True)
    chosen = surface.sort_values(
        ["issue", "predicted_total_pnl_cny", "action_key", "protection_share"],
        ascending=[True, False, True, True],
    ).groupby("issue", as_index=False).head(1)
    chosen["funded"] = chosen["predicted_total_pnl_cny"].gt(0)
    cash = ~chosen["funded"]
    for column in [
        "base_stake_cny",
        "base_gross_cny",
        "base_pnl_cny",
        "actual_protection_pnl_cny",
        "actual_total_pnl_cny",
    ]:
        chosen.loc[cash, column] = 0.0
    chosen.loc[cash, "funded_protection_count"] = 0
    chosen.loc[cash, "protection_share"] = 0.0
    return chosen.reset_index(drop=True)


def _attach_exact_budget_controls(
    selected: pd.DataFrame, candidates: pd.DataFrame, source: Path
) -> pd.DataFrame:
    continuation = pd.read_parquet(
        source / "continuation_settlement_labels.parquet",
        filters=[("issue_year", "==", int(selected["issue_year"].iloc[0]))],
    )
    candidate_groups = {
        key: group
        for key, group in candidates.groupby(["issue", "action_key"], sort=False)
    }
    continuation_groups = {
        key: group
        for key, group in continuation.groupby(["issue", "action_key"], sort=False)
    }
    random_pnl = []
    continuation_pnl = []
    adverse_pnl = []
    oracle_pnl = []
    for row in selected.itertuples(index=False):
        count = int(row.funded_protection_count)
        key = (str(row.issue), str(row.action_key))
        group = candidate_groups.get(key)
        cont = continuation_groups.get(key)
        if count == 0 or group is None:
            random_pnl.append(0.0)
        else:
            random_pnl.append(
                float(
                    same_budget_random(
                        group,
                        funded_count=count,
                        issue=str(row.issue),
                        action_key=str(row.action_key),
                    )["pnl_cny"].sum()
                )
            )
        if count == 0 or cont is None:
            continuation_pnl.append(0.0)
        else:
            continuation_pnl.append(
                float(cont.sort_values("continuation_rank").head(count)["pnl_cny"].sum())
            )
        if count == 0 or group is None:
            adverse_pnl.append(0.0)
        else:
            primary = (
                group.sort_values(
                    [
                        "parent_ticket_index",
                        "selected_divergence",
                        "alternative_probability",
                        "candidate_identity",
                    ],
                    ascending=[True, True, False, True],
                )
                .groupby("parent_ticket_index", as_index=False)
                .head(1)
                .sort_values(
                    ["selected_divergence", "alternative_probability", "candidate_identity"],
                    ascending=[True, False, True],
                )
            )
            adverse = primary.head(count)
            if len(adverse) < count:
                remainder = group.loc[
                    ~group["candidate_identity"].isin(adverse["candidate_identity"])
                ].sort_values(
                    ["selected_divergence", "alternative_probability", "candidate_identity"],
                    ascending=[True, False, True],
                )
                adverse = pd.concat(
                    [adverse, remainder.head(count - len(adverse))], ignore_index=True
                )
            if len(adverse) != count or not adverse["candidate_identity"].is_unique:
                raise AssertionError("adverse heuristic did not meet exact unique-ticket quota")
            adverse_pnl.append(float(adverse["pnl_cny"].sum()))
        if count == 0 or group is None:
            oracle_pnl.append(0.0)
        else:
            oracle = group.sort_values(
                ["hit", "gross_cny", "candidate_identity"],
                ascending=[False, False, True],
            ).head(count)
            oracle_pnl.append(float(oracle["pnl_cny"].sum()))
    selected = selected.copy()
    selected["random_control_total_pnl_cny"] = selected["base_pnl_cny"] + random_pnl
    selected["continuation_control_total_pnl_cny"] = (
        selected["base_pnl_cny"] + continuation_pnl
    )
    selected["adverse_control_total_pnl_cny"] = selected["base_pnl_cny"] + adverse_pnl
    selected["oracle_control_total_pnl_cny"] = selected["base_pnl_cny"] + oracle_pnl
    return selected


def _metrics(path: pd.DataFrame, column: str, model: str, policy: str) -> dict[str, object]:
    pnl = path[column].to_numpy(float)
    capital = path["capital_cny"].to_numpy(float)
    peaks = np.maximum.accumulate(np.r_[100_000.0, capital])
    drawdown = 1.0 - np.r_[100_000.0, capital] / peaks
    return {
        "model": model,
        "policy": policy,
        "issues": len(path),
        "ending_capital_cny": float(capital[-1]),
        "total_pnl_cny": float(pnl.sum()),
        "positive_issue_fraction": float(np.mean(pnl > 0)),
        "max_drawdown_pct": float(drawdown.max() * 100.0),
        "worst_rolling_10_pnl_cny": float(pd.Series(pnl).rolling(10).sum().min()),
    }


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
