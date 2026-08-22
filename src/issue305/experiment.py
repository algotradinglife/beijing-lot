"""Run the Issue #305 dedicated keep/skip correction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from issue299.evaluation import capital_path as residual_capital_path
from issue299.panel import build_action_panel
from issue305.evaluation import (
    capital_path,
    constant_decisions,
    decisions_from_scores,
    exact_exposure_null,
    oracle_decisions,
    summarize,
)
from issue305.model import fit_predict_expanding

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
]
PRIMARY = "DEDICATED_MLP"
PREDICTION_YEARS = (2021, 2022, 2023)


def run_experiment(root: str | Path, output: str | Path) -> dict[str, object]:
    root, output = Path(root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    issues, residual_actions = build_action_panel(root)
    if issues["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")
    issues.to_csv(output / "matched_issue_features.csv", index=False)

    specifications = [
        (PRIMARY, "MLP", 20.0),
        ("DEDICATED_MLP_ALPHA5", "MLP", 5.0),
        ("DEDICATED_MLP_ALPHA50", "MLP", 50.0),
        ("ISSUE_BLOCK_SHUFFLED", "MLP", 20.0),
        ("RIDGE_CONTROL", "RIDGE", 20.0),
    ]
    score_frames: list[pd.DataFrame] = []
    seed_frames: list[pd.DataFrame] = []
    receipt_frames: list[pd.DataFrame] = []
    for condition, model_kind, alpha in specifications:
        scores, seeds, receipts = fit_predict_expanding(
            issues,
            feature_columns=FEATURE_COLUMNS,
            condition=condition,
            model_kind=model_kind,
            alpha=alpha,
        )
        scores["alpha"] = alpha
        seeds["alpha"] = alpha
        receipts["alpha"] = alpha
        score_frames.append(scores)
        seed_frames.append(seeds)
        receipt_frames.append(receipts)
    all_scores = pd.concat(score_frames, ignore_index=True)
    all_seeds = pd.concat(seed_frames, ignore_index=True)
    fit_receipts = pd.concat(receipt_frames, ignore_index=True)
    all_scores.to_csv(output / "baseline_value_predictions.csv", index=False)
    all_seeds.to_csv(output / "seed_baseline_value_predictions.csv", index=False)
    fit_receipts.to_csv(output / "fit_receipts.csv", index=False)

    support = issues[issues["issue_year"].isin(PREDICTION_YEARS)].copy()
    decision_frames: list[pd.DataFrame] = []
    for condition, local in all_scores.groupby("condition", sort=False):
        decision_frames.append(
            decisions_from_scores(support, local, condition=str(condition))
        )
    decision_frames.extend(
        [
            constant_decisions(support, condition="B0_BEST_FULL", keep_active=True),
            constant_decisions(support, condition="CASH_NO_BET", keep_active=False),
            oracle_decisions(support),
        ]
    )
    decisions = pd.concat(decision_frames, ignore_index=True)
    decisions.to_csv(output / "policy_decisions.csv", index=False)

    paths: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []
    for condition, local_decisions in decisions.groupby("condition", sort=False):
        for year in PREDICTION_YEARS:
            year_issues = support[support["issue_year"].eq(year)]
            year_decisions = local_decisions[local_decisions["issue_year"].eq(year)]
            path = capital_path(year_issues, year_decisions)
            path["evaluation_year"] = year
            paths.append(path)
            summaries.append({"evaluation_year": year, **summarize(path)})

    residual_decisions = pd.read_csv(root / "results/issue-299/policy_decisions.csv")
    residual_decisions = residual_decisions[
        residual_decisions["condition"].eq("LEARNED_RESIDUAL")
    ]
    for year in PREDICTION_YEARS:
        year_issues = issues[issues["issue_year"].eq(year)]
        year_actions = residual_actions[residual_actions["issue_year"].eq(year)]
        year_decisions = residual_decisions[residual_decisions["issue_year"].eq(year)]
        path = residual_capital_path(year_issues, year_actions, year_decisions)
        path["condition"] = "ISSUE299_LEARNED_RESIDUAL"
        path["evaluation_year"] = year
        paths.append(path)
        summaries.append({"evaluation_year": year, **summarize(path)})

    path_frame = pd.concat(paths, ignore_index=True)
    summary_frame = pd.DataFrame(summaries)
    path_frame.to_csv(output / "capital_paths.csv", index=False)
    summary_frame.to_csv(output / "policy_summary.csv", index=False)

    primary_decisions = decisions[decisions["condition"].eq(PRIMARY)]
    null_table, null_summary = exact_exposure_null(issues, primary_decisions)
    null_table.to_csv(output / "exact_exposure_null_histogram_2023.csv", index=False)
    (output / "exact_exposure_null_2023.json").write_text(
        json.dumps(null_summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    legacy_decisions = pd.read_csv(root / "results/issue-302/policy_decisions.csv")
    legacy = legacy_decisions[
        legacy_decisions["condition"].eq("GUARDED_DYNAMIC_MOE")
    ][["issue", "issue_year", "keep_baseline"]]
    _, legacy_null = exact_exposure_null(issues, legacy)
    (output / "legacy_302_exact_null.json").write_text(
        json.dumps(legacy_null, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    sensitivity = _sensitivity(decisions, summary_frame)
    sensitivity.to_csv(output / "sensitivity_2023.csv", index=False)
    _plot_capital(path_frame, output / "capital_paths_2023.png")
    _plot_null(null_table, null_summary, output / "exact_exposure_null_2023.png")
    _plot_sensitivity(sensitivity, output / "sensitivity_2023.png")

    primary = _summary(summary_frame, PRIMARY, 2023)
    baseline = _summary(summary_frame, "B0_BEST_FULL", 2023)
    cash = _summary(summary_frame, "CASH_NO_BET", 2023)
    convergence_ok = bool(
        fit_receipts[
            fit_receipts["condition"].isin(
                [PRIMARY, "DEDICATED_MLP_ALPHA5", "DEDICATED_MLP_ALPHA50"]
            )
        ][["mean_converged", "downside_converged"]]
        .all(axis=None)
    )
    alpha_rows = sensitivity[
        sensitivity["condition"].isin(
            [PRIMARY, "DEDICATED_MLP_ALPHA5", "DEDICATED_MLP_ALPHA50"]
        )
    ]
    alpha_sign_stable = bool(
        alpha_rows["lift_vs_best_full_cny"].gt(0).all()
        or alpha_rows["lift_vs_best_full_cny"].le(0).all()
    )
    alpha_decision_stable = bool(
        alpha_rows["decision_jaccard_vs_primary"].ge(0.80).all()
        and alpha_rows["funded_issues"].sub(primary["funded_issues"]).abs().le(2).all()
    )
    accepted_signal = bool(
        primary["terminal_capital_cny"] > baseline["terminal_capital_cny"]
        and null_summary["exact_percentile"] >= 0.95
        and convergence_ok
        and alpha_sign_stable
        and alpha_decision_stable
    )
    decision = {
        "verdict": "DEDICATED_KEEP_SKIP_SIGNAL" if accepted_signal else "SHARED_HEAD_EXPOSURE_REDUCTION_ONLY",
        "promotable": False,
        "development_signal_accepted": accepted_signal,
        "matched_support_issues": int(len(issues)),
        "prediction_years": list(PREDICTION_YEARS),
        "sealed_years": "2024+ not read",
        "primary_2023_terminal_capital_cny": primary["terminal_capital_cny"],
        "primary_2023_capital_growth_pct": primary["capital_growth_pct"],
        "baseline_2023_terminal_capital_cny": baseline["terminal_capital_cny"],
        "baseline_2023_capital_growth_pct": baseline["capital_growth_pct"],
        "cash_2023_terminal_capital_cny": cash["terminal_capital_cny"],
        "matched_lift_cny": primary["terminal_capital_cny"] - baseline["terminal_capital_cny"],
        "matched_lift_pp": primary["capital_growth_pct"] - baseline["capital_growth_pct"],
        "funded_2023_issues": primary["funded_issues"],
        "exact_executed_exposure_percentile": null_summary["exact_percentile"],
        "exact_null_combination_count": null_summary["combination_count"],
        "legacy_302_exact_percentile": legacy_null["exact_percentile"],
        "all_primary_sensitivity_fits_converged": convergence_ok,
        "alpha_lift_sign_stable": alpha_sign_stable,
        "alpha_decision_stable": alpha_decision_stable,
        "expert_label_inputs": 0,
    }
    payload = {
        "issue": 305,
        "baseline": "#299/#302 exact atomic B0_BEST_FULL",
        "model": "dedicated expert-label-invariant expanding BEST_FULL keep/skip",
        "decision": decision,
    }
    (output / "decision.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_manifest(output)
    return payload


def _summary(frame: pd.DataFrame, condition: str, year: int) -> dict[str, object]:
    return frame[
        frame["condition"].eq(condition) & frame["evaluation_year"].eq(year)
    ].iloc[0].to_dict()


def _sensitivity(decisions: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    focus = [
        PRIMARY,
        "DEDICATED_MLP_ALPHA5",
        "DEDICATED_MLP_ALPHA50",
        "RIDGE_CONTROL",
        "ISSUE_BLOCK_SHUFFLED",
    ]
    primary_set = set(
        decisions[
            decisions["condition"].eq(PRIMARY)
            & decisions["issue_year"].eq(2023)
            & decisions["keep_baseline"]
        ]["issue"]
    )
    baseline = _summary(summary, "B0_BEST_FULL", 2023)
    rows = []
    for condition in focus:
        local = decisions[
            decisions["condition"].eq(condition)
            & decisions["issue_year"].eq(2023)
            & decisions["keep_baseline"]
        ]
        selected = set(local["issue"])
        union = primary_set | selected
        metric = _summary(summary, condition, 2023)
        rows.append(
            {
                "condition": condition,
                "funded_issues": metric["funded_issues"],
                "terminal_capital_cny": metric["terminal_capital_cny"],
                "capital_growth_pct": metric["capital_growth_pct"],
                "lift_vs_best_full_cny": metric["terminal_capital_cny"] - baseline["terminal_capital_cny"],
                "max_drawdown_pct": metric["max_drawdown_pct"],
                "decision_jaccard_vs_primary": len(primary_set & selected) / len(union) if union else 1.0,
            }
        )
    return pd.DataFrame(rows)


def _plot_capital(frame: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    for condition in [PRIMARY, "B0_BEST_FULL", "CASH_NO_BET", "ISSUE_BLOCK_SHUFFLED", "ISSUE299_LEARNED_RESIDUAL"]:
        local = frame[
            frame["evaluation_year"].eq(2023) & frame["condition"].eq(condition)
        ]
        ax.plot(range(len(local)), local["closing_capital_cny"], label=condition)
    ax.axhline(100_000, color="black", lw=0.8)
    ax.set(title="#305 dedicated BEST_FULL keep/skip — 2023", xlabel="issue order", ylabel="capital (CNY)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_null(frame: pd.DataFrame, summary: dict[str, object], target: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(frame["bin_midpoint_cny"], frame["probability"], width=250, alpha=0.7)
    ax.axvline(summary["observed_terminal_capital_cny"], color="red", label="observed")
    ax.set(title="#305 exact same-exposure placement null", xlabel="terminal capital (CNY)", ylabel="exact probability")
    ax.legend()
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_sensitivity(frame: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ordered = frame.sort_values("lift_vs_best_full_cny")
    ax.barh(ordered["condition"], ordered["lift_vs_best_full_cny"])
    ax.axvline(0, color="black", lw=0.8)
    ax.set(title="#305 2023 model sensitivity", xlabel="lift vs exact BEST_FULL (CNY)")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _write_manifest(output: Path) -> None:
    files = {}
    for path in sorted(output.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        files[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (output / "manifest.json").write_text(
        json.dumps({"issue": 305, "files": files}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
