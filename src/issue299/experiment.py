"""End-to-end BEST_FULL-anchored residual experiment for Issue #299."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from issue296.evaluation import summarize_path
from issue299.evaluation import (
    capital_path,
    constant_decisions,
    incremental_path,
    oracle_decisions,
    select_static_control,
    validation_gate,
)
from issue299.model import (
    BASELINE_ACTION,
    fit_residual_ensemble,
    fit_predict_ridge_scores,
    predict_residual_scores,
    select_actions,
)
from issue299.panel import ACTIONS, build_action_panel, build_support_receipt

FEATURE_COLUMNS = [
    "n_matches",
    "n_accepted",
    "accepted_fraction",
    "books_mean",
    "line_abs_mean",
    "line_std",
    "prob_entropy_mean",
    "prob_top_mean",
    "prob_top_q90",
    "value_best_mean",
    "value_best_std",
    "value_best_q50",
    "value_best_q90",
    "value_margin_mean",
    "value_interval_mean",
    "divergence_abs_mean",
    "divergence_abs_q90",
    "divergence_signed_mean",
    "baseline_active",
]


def run_experiment(root: str | Path, output: str | Path) -> dict[str, object]:
    """Fit before 2023, replay exact matched controls and write artifacts."""

    root = Path(root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    issues, actions = build_action_panel(root)
    support = build_support_receipt(root)
    support.to_csv(output / "support_receipt.csv", index=False)
    issues.to_csv(output / "matched_issue_features.csv", index=False)
    actions.to_csv(output / "residual_action_ledger.csv", index=False)

    learned_fits = fit_residual_ensemble(
        issues,
        actions,
        feature_columns=FEATURE_COLUMNS,
        condition="LEARNED_RESIDUAL",
    )
    shuffled_fits = fit_residual_ensemble(
        issues,
        actions,
        feature_columns=FEATURE_COLUMNS,
        condition="IDENTITY_SHUFFLED",
    )
    learned_scores, learned_seed_scores = predict_residual_scores(
        learned_fits, issues, actions
    )
    shuffled_scores, shuffled_seed_scores = predict_residual_scores(
        shuffled_fits, issues, actions
    )
    ridge_scores = fit_predict_ridge_scores(
        issues, actions, feature_columns=FEATURE_COLUMNS
    )
    scores = pd.concat(
        [learned_scores, shuffled_scores, ridge_scores], ignore_index=True
    )
    scores.to_csv(output / "residual_predictions.csv", index=False)
    pd.concat([learned_seed_scores, shuffled_seed_scores], ignore_index=True).to_csv(
        output / "residual_seed_predictions.csv", index=False
    )

    learned_decisions = select_actions(learned_scores)
    shuffled_decisions = select_actions(shuffled_scores)
    ridge_decisions = select_actions(ridge_scores)
    selection_only = learned_decisions.copy()
    selection_only["condition"] = "SELECTION_ONLY_GATE"
    selection_only.loc[
        ~selection_only["action"].eq("BASELINE_SCALE_DOWN"), "action"
    ] = BASELINE_ACTION
    static_action, static_frontier = select_static_control(issues, actions)
    static_frontier.to_csv(output / "static_residual_frontier.csv", index=False)
    baseline_decisions = constant_decisions(
        issues, BASELINE_ACTION, "BEST_FULL_BASELINE"
    )
    cash_decisions = constant_decisions(issues, "BASELINE_SCALE_DOWN", "CASH_NO_BET")
    static_decisions = constant_decisions(
        issues, static_action, f"STATIC_TRAIN_{static_action}"
    )
    oracle = oracle_decisions(issues, actions)
    decision_frames = [
        baseline_decisions,
        cash_decisions,
        static_decisions,
        learned_decisions,
        shuffled_decisions,
        ridge_decisions,
        selection_only,
        oracle,
    ]
    all_decisions = pd.concat(decision_frames, ignore_index=True)
    all_decisions.to_csv(output / "policy_decisions.csv", index=False)

    full_paths: dict[str, pd.DataFrame] = {}
    for frame in decision_frames:
        name = str(frame["condition"].iloc[0])
        full_paths[name] = capital_path(issues, actions, frame)

    seed_decisions: list[pd.DataFrame] = []
    seed_paths_2022: list[pd.DataFrame] = []
    seed_summary_rows: list[dict[str, object]] = []
    for seed, frame in learned_seed_scores.groupby("seed", sort=True):
        chosen = select_actions(frame).assign(condition=f"LEARNED_SEED_{int(seed)}")
        seed_decisions.append(chosen)
        for year in [2022, 2023]:
            local_issues = issues[issues["issue_year"].eq(year)]
            local_actions = actions[actions["issue_year"].eq(year)]
            local_decisions = chosen[chosen["issue_year"].eq(year)]
            path = capital_path(local_issues, local_actions, local_decisions)
            summary = summarize_path(path)
            seed_summary_rows.append({"seed": int(seed), "issue_year": year, **summary})
            if year == 2022:
                seed_paths_2022.append(path)
    pd.concat(seed_decisions, ignore_index=True).to_csv(
        output / "seed_decisions.csv", index=False
    )
    seed_summary = pd.DataFrame(seed_summary_rows)
    seed_summary.to_csv(output / "seed_summary.csv", index=False)

    validation_paths = {
        name: capital_path(
            issues[issues["issue_year"].eq(2022)],
            actions[actions["issue_year"].eq(2022)],
            decisions[decisions["issue_year"].eq(2022)],
        )
        for name, decisions in {
            "BEST_FULL_BASELINE": baseline_decisions,
            "LEARNED_RESIDUAL": learned_decisions,
        }.items()
    }
    gate = validation_gate(validation_paths, seed_paths_2022)
    guarded_source = learned_decisions if gate["accepted"] else baseline_decisions
    guarded = guarded_source.copy()
    guarded["condition"] = "GUARDED_RESIDUAL"
    full_paths["GUARDED_RESIDUAL"] = capital_path(issues, actions, guarded)
    guarded.to_csv(output / "guarded_decisions.csv", index=False)
    (output / "validation_gate.json").write_text(
        json.dumps(_json_safe(gate), indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )

    paths = pd.concat(full_paths.values(), ignore_index=True)
    paths.to_csv(output / "capital_paths_2019_2023.csv", index=False)
    period_rows: list[dict[str, object]] = []
    for condition, path in full_paths.items():
        for year in [2019, 2020, 2021, 2022, 2023]:
            local = path[path["issue_year"].eq(year)].copy()
            if local.empty:
                continue
            local["opening_capital_cny"] = 100_000.0
            local["closing_capital_cny"] = 100_000.0 + local["pnl_cny"].cumsum()
            period_rows.append({"evaluation_year": year, **summarize_path(local)})
    summaries = pd.DataFrame(period_rows)
    summaries.to_csv(output / "policy_summary_by_year.csv", index=False)

    test_baseline = _year_path(full_paths["BEST_FULL_BASELINE"], 2023)
    test_learned = _year_path(full_paths["LEARNED_RESIDUAL"], 2023)
    incremental = incremental_path(test_learned, test_baseline)
    incremental.to_csv(output / "learned_minus_best_full_2023.csv", index=False)
    calibration = _calibration(learned_scores, actions)
    calibration.to_csv(output / "residual_calibration.csv", index=False)
    attribution = _attribution(test_learned, test_baseline)
    attribution.to_csv(output / "action_attribution_2023.csv", index=False)
    permutation = _permutation_control(issues, actions, learned_decisions)
    permutation.to_csv(output / "exposure_matched_permutation.csv", index=False)
    fit_receipts = _fit_receipts(learned_fits, shuffled_fits)
    fit_receipts.to_csv(output / "fit_receipts.csv", index=False)
    baseline_receipt = _baseline_receipt(issues, actions)
    (output / "baseline_reproduction.json").write_text(
        json.dumps(
            _json_safe(baseline_receipt),
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    test_summary = {
        name: summarize_path(_year_path(path, 2023))
        for name, path in full_paths.items()
    }
    learned_summary = test_summary["LEARNED_RESIDUAL"]
    baseline_summary = test_summary["BEST_FULL_BASELINE"]
    incremental_pnl = (
        learned_summary["terminal_capital_cny"]
        - baseline_summary["terminal_capital_cny"]
    )
    relative_signal = bool(
        gate["accepted"]
        and incremental_pnl > 0
        and gate["ex_largest_matched_lift_cny"] >= 0
    )
    permutation_2023 = permutation[permutation["issue_year"].eq(2023)]
    permutation_percentile = float(
        (
            permutation_2023["terminal_capital_cny"]
            <= learned_summary["terminal_capital_cny"]
        ).mean()
    )
    promotion = bool(
        relative_signal
        and learned_summary["terminal_capital_cny"] > 100_000.0
        and permutation_percentile >= 0.95
    )
    decision = {
        "verdict": (
            "CANDIDATE_SIGNAL"
            if promotion
            else "RELATIVE_BASELINE_SIGNAL_NO_PROMOTION"
            if relative_signal
            else "NO_PROMOTION"
        ),
        "promotable": promotion,
        "relative_baseline_signal": relative_signal,
        "validation_gate_accepted": bool(gate["accepted"]),
        "guarded_source": gate["decision"],
        "matched_support_issues": int(len(issues)),
        "excluded_no_exact_baseline": int(
            support["support_status"].eq("EXCLUDED_NO_EXACT_BEST_FULL").sum()
        ),
        "static_train_action": static_action,
        "baseline_2023_capital_growth_pct": baseline_summary["capital_growth_pct"],
        "raw_learned_2023_capital_growth_pct": learned_summary["capital_growth_pct"],
        "raw_learned_matched_lift_cny": incremental_pnl,
        "guarded_2023_capital_growth_pct": test_summary["GUARDED_RESIDUAL"][
            "capital_growth_pct"
        ],
        "learned_2023_activation_rate": float(
            incremental["changed_from_baseline"].mean()
        ),
        "learned_2023_action_label_change_rate": float(
            learned_decisions.loc[learned_decisions["issue_year"].eq(2023), "action"]
            .ne(BASELINE_ACTION)
            .mean()
        ),
        "learned_2023_ex_largest_pnl_cny": learned_summary["ex_largest_pnl_cny"],
        "baseline_2023_ex_largest_pnl_cny": baseline_summary["ex_largest_pnl_cny"],
        "identity_shuffled_2023_capital_growth_pct": test_summary["IDENTITY_SHUFFLED"][
            "capital_growth_pct"
        ],
        "oracle_2023_capital_growth_pct": test_summary["ORACLE_DIAGNOSTIC"][
            "capital_growth_pct"
        ],
        "static_residual_2023_capital_growth_pct": test_summary[
            f"STATIC_TRAIN_{static_action}"
        ]["capital_growth_pct"],
        "selection_only_2023_capital_growth_pct": test_summary["SELECTION_ONLY_GATE"][
            "capital_growth_pct"
        ],
        "ridge_control_2023_capital_growth_pct": test_summary["RIDGE_RESIDUAL_CONTROL"][
            "capital_growth_pct"
        ],
        "exposure_matched_permutation_median_capital_cny": float(
            permutation_2023["terminal_capital_cny"].median()
        ),
        "learned_vs_permutation_percentile": permutation_percentile,
    }
    payload = {
        "issue": 299,
        "development_only": True,
        "train_years": [2019, 2020, 2021],
        "validation_year": 2022,
        "test_year": 2023,
        "sealed_years": "2024+ not read by model runner",
        "baseline_identity": "accepted #167/#170 B0_BEST_FULL",
        "actions": ACTIONS,
        "decision": decision,
    }
    (output / "decision.json").write_text(
        json.dumps(_json_safe(payload), indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )

    _plot_capital(full_paths, output / "capital_paths_2023.png")
    _plot_incremental(incremental, output / "learned_minus_best_full_2023.png")
    _plot_activation(attribution, output / "action_attribution_2023.png")
    _plot_calibration(calibration, output / "residual_calibration.png")
    _write_manifest(root, output)
    return payload


def _year_path(path: pd.DataFrame, year: int) -> pd.DataFrame:
    local = path[path["issue_year"].eq(year)].copy()
    local["opening_capital_cny"] = 100_000.0
    local["closing_capital_cny"] = 100_000.0 + local["pnl_cny"].cumsum()
    return local


def _calibration(scores: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    learned = scores[scores["condition"].eq("LEARNED_RESIDUAL")].merge(
        actions[["issue", "action", "residual_pnl_cny"]],
        on=["issue", "action"],
        how="inner",
        validate="one_to_one",
    )
    learned = learned[learned["action"].ne(BASELINE_ACTION)].copy()
    learned["utility_bin"] = pd.qcut(
        learned["utility_cny"].rank(method="first"), 10, labels=False
    )
    return learned.groupby(["issue_year", "utility_bin"], as_index=False).agg(
        rows=("issue", "size"),
        predicted_utility_cny=("utility_cny", "mean"),
        predicted_residual_pnl_cny=("predicted_residual_pnl_cny", "mean"),
        realized_residual_pnl_cny=("residual_pnl_cny", "mean"),
        realized_positive_rate=(
            "residual_pnl_cny",
            lambda value: float((value > 0).mean()),
        ),
    )


def _attribution(learned: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    merged = learned.merge(
        baseline[["issue", "pnl_cny"]].rename(columns={"pnl_cny": "baseline_pnl"}),
        on="issue",
        how="inner",
        validate="one_to_one",
    )
    merged["incremental_pnl_cny"] = merged["pnl_cny"] - merged["baseline_pnl"]
    return merged.groupby("requested_action", as_index=False).agg(
        issues=("issue", "size"),
        stake_cny=("stake_cny", "sum"),
        pnl_cny=("pnl_cny", "sum"),
        incremental_pnl_cny=("incremental_pnl_cny", "sum"),
        profitable_issue_rate=("pnl_cny", lambda value: float((value > 0).mean())),
    )


def _fit_receipts(learned: list[object], shuffled: list[object]) -> pd.DataFrame:
    rows = []
    for fit in [*learned, *shuffled]:
        for head in fit.heads:
            rows.append(
                {
                    "condition": fit.condition,
                    "seed": fit.seed,
                    "action": head.action,
                    "target_action": head.target_action,
                    "features": len(fit.feature_columns),
                    "mean_model": type(head.mean_model).__name__,
                    "loss_model": type(head.loss_model).__name__,
                    "downside_model": type(head.downside_model).__name__,
                    "target_clip_low": head.target_clip_low,
                    "target_clip_high": head.target_clip_high,
                }
            )
    return pd.DataFrame(rows)


def _permutation_control(
    issues: pd.DataFrame,
    actions: pd.DataFrame,
    learned_decisions: pd.DataFrame,
    *,
    replicates: int = 1000,
) -> pd.DataFrame:
    """Permute the frozen action multiset to test selection beyond exposure reduction."""

    rows = []
    for year in [2022, 2023]:
        local_issues = issues[issues["issue_year"].eq(year)]
        local_actions = actions[actions["issue_year"].eq(year)]
        decisions = learned_decisions[learned_decisions["issue_year"].eq(year)].copy()
        frozen_actions = decisions["action"].to_numpy(copy=True)
        for replicate in range(replicates):
            rng = np.random.default_rng(299_000 + 10_000 * (year - 2022) + replicate)
            permuted = decisions.copy()
            permuted["action"] = rng.permutation(frozen_actions)
            permuted["condition"] = "EXPOSURE_MATCHED_PERMUTATION"
            path = capital_path(local_issues, local_actions, permuted)
            summary = summarize_path(path)
            rows.append(
                {
                    "issue_year": year,
                    "replicate": replicate,
                    "terminal_capital_cny": summary["terminal_capital_cny"],
                    "capital_growth_pct": summary["capital_growth_pct"],
                    "max_drawdown_pct": summary["max_drawdown_pct"],
                    "ex_largest_pnl_cny": summary["ex_largest_pnl_cny"],
                }
            )
    return pd.DataFrame(rows)


def _baseline_receipt(issues: pd.DataFrame, actions: pd.DataFrame) -> dict[str, object]:
    baseline = actions[actions["action"].eq(BASELINE_ACTION)].sort_values("issue")
    expected = issues.sort_values("issue")
    return {
        "matched_issues": len(expected),
        "active_issues": int(expected["baseline_active"].sum()),
        "stake_identical": bool(
            np.allclose(baseline["stake_cny"], expected["baseline_stake_cny"])
        ),
        "pnl_identical": bool(
            np.allclose(baseline["pnl_cny"], expected["baseline_pnl_cny"])
        ),
        "gross_identical": bool(
            np.allclose(baseline["gross_cny"], expected["baseline_gross_cny"])
        ),
        "all_active_atomic_4374": bool(
            expected.loc[expected["baseline_active"].eq(1), "baseline_stake_cny"]
            .eq(4374.0)
            .all()
        ),
    }


def _plot_capital(paths: dict[str, pd.DataFrame], target: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    plotted_paths = [
        "BEST_FULL_BASELINE",
        "LEARNED_RESIDUAL",
        "IDENTITY_SHUFFLED",
        "GUARDED_RESIDUAL",
        *sorted(name for name in paths if name.startswith("STATIC_TRAIN_")),
    ]
    for name in plotted_paths:
        if name not in paths:
            continue
        local = _year_path(paths[name], 2023)
        ax.plot(range(len(local)), local["closing_capital_cny"], label=name)
    ax.axhline(100_000, color="black", linewidth=0.8)
    ax.set(
        title="Issue #299 — 2023 BEST_FULL residual replay",
        xlabel="Issue index",
        ylabel="Capital (CNY)",
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_incremental(frame: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(range(len(frame)), frame["cumulative_incremental_pnl_cny"], color="#355C7D")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set(
        title="Learned residual minus exact BEST_FULL — 2023",
        xlabel="Issue index",
        ylabel="Cumulative lift (CNY)",
    )
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_activation(frame: pd.DataFrame, target: Path) -> None:
    plot = frame.sort_values("incremental_pnl_cny")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(plot["requested_action"], plot["incremental_pnl_cny"], color="#6C5B7B")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set(
        title="2023 residual-action attribution", xlabel="Matched incremental P&L (CNY)"
    )
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_calibration(frame: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    for year, local in frame.groupby("issue_year"):
        ax.plot(
            local["predicted_utility_cny"],
            local["realized_residual_pnl_cny"],
            marker="o",
            label=str(year),
        )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set(
        title="Residual utility calibration by year",
        xlabel="Predicted utility (CNY)",
        ylabel="Realized residual P&L (CNY)",
    )
    ax.legend(ncol=3, fontsize=7)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _write_manifest(root: Path, output: Path) -> None:
    files = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            files.append(
                {
                    "path": str(path.relative_to(root)),
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    payload = {"issue": 299, "files": files}
    (output / "manifest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _json_safe(value: object) -> object:
    """Convert NumPy scalars and non-finite floats to strict JSON values."""

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value
