#!/usr/bin/env python3
"""Run Issue #292 dynamic N/K policy and low-N plus tail barbell."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue292.policy import (  # noqa: E402
    attach_action_economics,
    average_seed_predictions,
    capital_path,
    combine_sleeves,
    select_capped_tail_sleeve,
    select_single_sleeve,
    summarize_policy,
)

N_VALUES = tuple(range(3, 11))
K_VALUES = (8, 16, 32, 64, 128, 256, 512)
GENERATORS = ("TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR")
NUISANCE_SEEDS = (292001, 292002, 292003, 292004, 292005)
MODEL_SEEDS = (292101, 292102, 292103)
CORE_THRESHOLDS = (-0.05, -0.03, -0.01, 0.0)
TAIL_THRESHOLDS = (0.0, 0.10, 0.25)
TAIL_CAPITAL_FRACTIONS = (0.10, 0.20)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-209",
        type=Path,
        default=ROOT / "results/issue-209",
    )
    parser.add_argument(
        "--source-291",
        type=Path,
        default=ROOT / "results/issue-291",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-292")
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", ROOT)),
    )
    parser.add_argument("--rebuild-surface", action="store_true")
    parser.add_argument("--limit-issues", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ["BEIJING_LOT_RUNTIME_ROOT"] = str(args.runtime_root.resolve())
    from issue209.data import build_tensor
    from issue209.dynamic_policy import (
        ActionSpec,
        build_issue_states,
        evaluate_counterfactual_actions,
        fit_action_models,
        join_states_and_actions,
        predict_action_models,
    )
    from issue209.models import build_match_units

    source209 = args.source_209.resolve()
    source291 = args.source_291.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    surface_path = output / "full_action_counterfactuals.parquet"
    state_path = output / "issue_states.csv"

    all_actions = (
        ActionSpec(0, 0, "NO_BET"),
        *(
            ActionSpec(n=n, k=k, generator=generator)
            for n in N_VALUES
            for k in K_VALUES
            for generator in GENERATORS
        ),
    )
    existing = (
        pd.read_parquet(surface_path)
        if surface_path.exists() and not args.rebuild_surface
        else pd.DataFrame()
    )
    present_keys = set(existing.get("action_key", pd.Series(dtype=str)).astype(str))
    missing_actions = tuple(
        action for action in all_actions if action.key not in present_keys
    )
    if missing_actions:
        tensor = build_tensor()
        if tensor["issue_year"].ge(2024).any():
            raise RuntimeError("2024+ outcome seal violated")
        units = build_match_units(tensor)
        probabilities = pd.read_parquet(source209 / "market_only_probabilities.parquet")
        values = pd.read_parquet(source209 / "cell_value_distribution.parquet")
        if not (len(units) == len(probabilities) == len(values)):
            raise RuntimeError("#209 unit/probability/value support mismatch")
        if args.limit_issues:
            keep = (
                units[["issue", "issue_year"]]
                .drop_duplicates()
                .sort_values(["issue_year", "issue"])
                .groupby("issue_year", group_keys=False)
                .head(args.limit_issues)["issue"]
                .astype(str)
            )
            keep_set = set(keep)
            mask = units["issue"].astype(str).isin(keep_set)
            units = units.loc[mask].copy()
            probabilities = probabilities.reindex(units.index)
            values = values.reindex(units.index)
            tensor = tensor[tensor["issue"].astype(str).isin(keep_set)].copy()
        states = build_issue_states(units, values, probabilities, horizon="10h")
        states.to_csv(state_path, index=False)
        extension = evaluate_counterfactual_actions(
            units,
            values,
            probabilities,
            tensor,
            states,
            actions=missing_actions,
            horizon="10h",
            seeds=NUISANCE_SEEDS,
        )
        surface = pd.concat([existing, extension], ignore_index=True)
        surface = surface.drop_duplicates(["issue", "action_key"], keep="last")
        surface = surface.sort_values(["issue_year", "issue", "action_key"])
        surface.to_parquet(surface_path, index=False)
    else:
        states = pd.read_csv(state_path, dtype={"issue": str})
        surface = existing

    surface["issue"] = surface["issue"].astype(str)
    states["issue"] = states["issue"].astype(str)
    _validate_surface(surface, states)
    learning = join_states_and_actions(states, surface)

    decision_frames: list[pd.DataFrame] = []
    prediction_frames: list[pd.DataFrame] = []
    family_rows: list[dict[str, object]] = []
    for year in range(2019, 2024):
        train = learning[learning["issue_year"].lt(year - 1)].copy()
        tune = learning[learning["issue_year"].eq(year - 1)].copy()
        test = learning[learning["issue_year"].eq(year)].copy()
        if min(train.issue.nunique(), tune.issue.nunique(), test.issue.nunique()) < 2:
            raise RuntimeError(f"insufficient chronological support for {year}")
        raw_predictions: dict[str, dict[str, list[pd.DataFrame]]] = {
            family: {"tune": [], "test": []}
            for family in ("LOGISTIC_TWO_PART", "MLP_TWO_PART")
        }
        for seed in MODEL_SEEDS:
            bundle = fit_action_models(train, seed=seed)
            for family in raw_predictions:
                raw_predictions[family]["tune"].append(
                    predict_action_models(bundle, tune, family)
                )
                raw_predictions[family]["test"].append(
                    predict_action_models(bundle, test, family)
                )
        family_predictions: dict[str, dict[str, pd.DataFrame]] = {}
        for family, raw in raw_predictions.items():
            family_predictions[family] = {
                "tune": attach_action_economics(
                    average_seed_predictions(raw["tune"]), tune
                ),
                "test": attach_action_economics(
                    average_seed_predictions(raw["test"]), test
                ),
            }
        family_scores = {}
        for family, frames in family_predictions.items():
            selected = select_single_sleeve(
                frames["tune"],
                policy=f"TUNE_{family}",
                n_min=3,
                n_max=10,
                score_column="predicted_risk_score",
                threshold=-np.inf,
                threshold_column="predicted_risk_score",
            )
            pnl = selected["pnl_cny"].to_numpy(float)
            family_scores[family] = (float(pnl.sum() - pnl.max()), float(pnl.sum()))
            family_rows.append(
                {
                    "oof_year": year,
                    "family": family,
                    "tune_ex_largest_pnl_cny": family_scores[family][0],
                    "tune_pnl_cny": family_scores[family][1],
                }
            )
        chosen_family = max(family_scores, key=family_scores.get)
        predicted = family_predictions[chosen_family]["test"].copy()
        predicted["oof_year"] = year
        predicted["chosen_family"] = chosen_family
        prediction_frames.append(predicted)
        decision_frames.extend(_policy_panel(predicted, year))

    decisions = pd.concat(decision_frames, ignore_index=True)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    fixed = _fixed_control(surface)
    continuation = _continuation_control(decisions, surface)
    candidate_paths = _issue291_controls(source291)
    all_paths = [decisions, fixed, continuation, *candidate_paths]
    paths = pd.concat([capital_path(frame) for frame in all_paths], ignore_index=True)
    summary = pd.DataFrame(
        [summarize_policy(group) for _, group in paths.groupby("policy", sort=True)]
    ).sort_values(["ex_largest_pnl_cny", "pnl_cny"], ascending=False)

    outputs = {
        "surface": surface_path,
        "states": state_path,
        "predictions": output / "oof_action_predictions.parquet",
        "decisions": output / "oof_policy_decisions.csv",
        "paths": output / "oof_capital_paths.csv",
        "summary": output / "policy_summary.csv",
        "families": output / "family_selection.csv",
    }
    predictions.to_parquet(outputs["predictions"], index=False)
    decisions.to_csv(outputs["decisions"], index=False)
    paths.to_csv(outputs["paths"], index=False)
    summary.to_csv(outputs["summary"], index=False)
    pd.DataFrame(family_rows).to_csv(outputs["families"], index=False)
    receipt = {
        "contract": "BJ-UNIFIED-CALIBRATED-JOINT-OPTIMIZER-001/oof-v1",
        "independent_unit": "BEIJING_ISSUE",
        "n_values": list(N_VALUES),
        "k_values": list(K_VALUES),
        "generators": list(GENERATORS),
        "nuisance_seeds": list(NUISANCE_SEEDS),
        "model_seeds": list(MODEL_SEEDS),
        "oof_years": list(range(2019, 2024)),
        "sealed_years_opened": [],
        "input_sha256": {
            "probabilities": _sha256(source209 / "market_only_probabilities.parquet"),
            "cell_values": _sha256(source209 / "cell_value_distribution.parquet"),
            "issue291_oof": _sha256(source291 / "oof_receipt.json"),
        },
        "producer_sha256": {
            "runner": _sha256(Path(__file__).resolve()),
            "policy": _sha256(ROOT / "src/issue292/policy.py"),
            "action_engine": _sha256(ROOT / "src/issue209/dynamic_policy.py"),
        },
        "environment": {
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "output_sha256": {name: _sha256(path) for name, path in outputs.items()},
    }
    _atomic_json(receipt, output / "receipt.json")
    print(summary.head(30).to_string(index=False), flush=True)
    return 0


def _policy_panel(predicted: pd.DataFrame, year: int) -> list[pd.DataFrame]:
    frames = []
    frames.append(
        select_single_sleeve(
            predicted,
            policy="DYNAMIC_FULL_ACTIVE",
            n_min=3,
            n_max=10,
            score_column="predicted_risk_score",
            threshold=-np.inf,
            threshold_column="predicted_risk_score",
        )
    )
    frames.append(
        select_single_sleeve(
            predicted,
            policy="CORE_ACTIVE",
            n_min=3,
            n_max=6,
            score_column="predicted_risk_score",
            threshold=-np.inf,
            threshold_column="predicted_mean_roi",
        )
    )
    frames.append(
        select_single_sleeve(
            predicted,
            policy="DYNAMIC_FULL_SAFE",
            n_min=3,
            n_max=10,
            score_column="predicted_risk_score",
            threshold=0.0,
            threshold_column="predicted_risk_score",
        )
    )
    tails: dict[float, pd.DataFrame] = {}
    for tail_threshold in TAIL_THRESHOLDS:
        tail = select_single_sleeve(
            predicted,
            policy=f"TAIL_EV_{tail_threshold:+.2f}",
            n_min=7,
            n_max=10,
            score_column="predicted_mean_roi",
            threshold=tail_threshold,
            threshold_column="predicted_mean_roi",
        )
        tails[tail_threshold] = tail
        frames.append(tail)
    for core_threshold in CORE_THRESHOLDS:
        core_name = f"CORE_EV_{core_threshold:+.2f}"
        core = select_single_sleeve(
            predicted,
            policy=core_name,
            n_min=3,
            n_max=6,
            score_column="predicted_risk_score",
            threshold=core_threshold,
            threshold_column="predicted_mean_roi",
        )
        frames.append(core)
        for tail_threshold in TAIL_THRESHOLDS:
            for tail_fraction in TAIL_CAPITAL_FRACTIONS:
                capped_tail = select_capped_tail_sleeve(
                    predicted,
                    core,
                    policy="TAIL_CAPPED_COMPONENT",
                    threshold=tail_threshold,
                    maximum_fraction=tail_fraction,
                )
                frames.append(
                    combine_sleeves(
                        core,
                        capped_tail,
                        policy=(
                            f"BARBELL_C{core_threshold:+.2f}_"
                            f"T{tail_threshold:+.2f}_F{tail_fraction:.2f}"
                        ),
                    )
                )
    for frame in frames:
        frame["oof_year"] = year
    return frames


def _fixed_control(surface: pd.DataFrame) -> pd.DataFrame:
    selected = surface[
        surface["issue_year"].between(2019, 2023)
        & surface["action_key"].eq("N7_K8_TOP_VALUE")
    ].copy()
    selected["policy"] = "FIXED_N7_K8_TOP_VALUE"
    selected["funded"] = True
    selected["stake_cny"] = selected["stake_total"]
    selected["pnl_cny"] = selected["mean_pnl"]
    selected["pnl_seed_q10_cny"] = selected["pnl_seed_q10"]
    return selected


def _continuation_control(
    decisions: pd.DataFrame, surface: pd.DataFrame
) -> pd.DataFrame:
    dynamic = decisions[decisions["policy"].eq("DYNAMIC_FULL_ACTIVE")].copy()
    dynamic["issue_numeric"] = pd.to_numeric(dynamic["issue"], errors="raise")
    dynamic = dynamic.sort_values(["issue_year", "issue_numeric"])
    dynamic["continuation_key"] = dynamic.groupby("issue_year")[
        "selected_action_key"
    ].shift()
    dynamic["continuation_key"] = dynamic["continuation_key"].fillna("N7_K8_TOP_VALUE")
    actual = surface[surface["issue_year"].between(2019, 2023)][
        [
            "issue",
            "issue_year",
            "action_key",
            "stake_total",
            "mean_pnl",
            "pnl_seed_q10",
        ]
    ]
    result = dynamic[["issue", "issue_year", "continuation_key"]].merge(
        actual,
        left_on=["issue", "issue_year", "continuation_key"],
        right_on=["issue", "issue_year", "action_key"],
        how="left",
        validate="one_to_one",
    )
    unavailable = result["stake_total"].isna()
    if unavailable.any():
        fallback = actual[actual["action_key"].eq("N7_K8_TOP_VALUE")].set_index(
            ["issue", "issue_year"]
        )
        keys = pd.MultiIndex.from_frame(
            result.loc[unavailable, ["issue", "issue_year"]]
        )
        replacement = fallback.reindex(keys)
        for column in ("action_key", "stake_total", "mean_pnl", "pnl_seed_q10"):
            result.loc[unavailable, column] = replacement[column].to_numpy()
        result.loc[unavailable, "continuation_key"] = "N7_K8_TOP_VALUE"
    result["policy"] = "CONTINUATION_PREVIOUS_ACTION"
    result["funded"] = True
    result["stake_cny"] = result["stake_total"]
    result["pnl_cny"] = result["mean_pnl"]
    result["pnl_seed_q10_cny"] = result["pnl_seed_q10"]
    return result


def _issue291_controls(source: Path) -> list[pd.DataFrame]:
    frame = pd.read_csv(source / "ranking_issue_paths.csv", dtype={"issue": str})
    specs = [
        ("DATA_LOGIT_RIDGE", "DIRECT_PNL", "ISSUE291_PRIMARY_B"),
        ("DATA_HGB", "DECOMPOSED_EV", "ISSUE291_CHALLENGER_B"),
    ]
    result = []
    for model, score, prefix in specs:
        for budget in (1, 4, 16, 64):
            selected = frame[
                frame["domain"].eq("BASE")
                & frame["model"].eq(model)
                & frame["score"].eq(score)
                & frame["ticket_budget_per_issue"].eq(budget)
            ].copy()
            selected = selected.rename(columns={"oof_year": "issue_year"})
            selected["policy"] = f"{prefix}{budget}"
            selected["funded"] = True
            selected["stake_cny"] = selected["stake_cny"]
            selected["pnl_seed_q10_cny"] = selected["pnl_cny"]
            result.append(selected)
    cash = frame[
        frame["domain"].eq("BASE")
        & frame["model"].eq("DATA_LOGIT_RIDGE")
        & frame["score"].eq("DIRECT_PNL")
        & frame["ticket_budget_per_issue"].eq(1)
    ][["issue", "oof_year"]].copy()
    cash = cash.rename(columns={"oof_year": "issue_year"})
    cash["policy"] = "CASH_NO_BET"
    cash["funded"] = False
    cash["stake_cny"] = 0.0
    cash["pnl_cny"] = 0.0
    cash["pnl_seed_q10_cny"] = 0.0
    result.append(cash)
    return result


def _validate_surface(surface: pd.DataFrame, states: pd.DataFrame) -> None:
    if surface["issue_year"].ge(2024).any():
        raise RuntimeError("surface contains sealed years")
    active = surface[surface["generator"].ne("NO_BET")]
    if set(active["n"].unique()) != set(N_VALUES):
        raise RuntimeError("full N3-N10 support is incomplete")
    if set(active["k"].unique()) != set(K_VALUES):
        raise RuntimeError("full K support is incomplete")
    actual = surface.groupby("issue")["action_key"].agg(lambda values: set(values))
    matches = states.set_index("issue")["n_matches"]
    for issue, n_matches in matches.items():
        expected = {"NO_BET"}
        expected.update(
            f"N{n}_K{k}_{generator}"
            for n in N_VALUES
            if n <= int(n_matches)
            for k in K_VALUES
            for generator in GENERATORS
        )
        if actual.get(str(issue), set()) != expected:
            missing = sorted(expected - actual.get(str(issue), set()))
            extra = sorted(actual.get(str(issue), set()) - expected)
            raise RuntimeError(
                f"issue/action surface is incomplete for {issue}: "
                f"missing={missing[:3]} extra={extra[:3]}"
            )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
