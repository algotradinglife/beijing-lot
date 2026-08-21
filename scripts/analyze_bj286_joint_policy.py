#!/usr/bin/env python3
"""Create compact decision diagnostics for Issue #286."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "results/issue-286")
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-286")
    parser.add_argument(
        "--figure-output",
        type=Path,
        default=ROOT / "docs/research/figures/issue_286_joint_policy.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    selected = pd.read_parquet(source / "joint_oof_selected_actions.parquet")
    policies = {
        "LEARNED_JOINT": ("actual_total_pnl_cny", "joint_stake_cny"),
        "SELECTED_BASE_NO_PROTECTION": ("base_pnl_cny", "base_stake_cny"),
        "SAME_BUDGET_RANDOM": ("random_control_total_pnl_cny", "joint_stake_cny"),
        "SAME_BUDGET_CONTINUATION": (
            "continuation_control_total_pnl_cny",
            "joint_stake_cny",
        ),
        "SAME_BUDGET_ADVERSE_HEURISTIC": (
            "adverse_control_total_pnl_cny",
            "joint_stake_cny",
        ),
        "UNATTAINABLE_ORACLE_UPPER_BOUND": (
            "oracle_control_total_pnl_cny",
            "joint_stake_cny",
        ),
        "FORMAL_N7_K8_MARKET_TOP": (
            "formal_baseline_pnl_cny",
            "formal_baseline_stake_cny",
        ),
    }
    selected["joint_stake_cny"] = (
        selected["base_stake_cny"] + 2.0 * selected["funded_protection_count"]
    )
    summary_rows = []
    annual_rows = []
    path_rows = []
    for model, model_frame in selected.groupby("model", sort=True):
        for policy, (pnl_column, stake_column) in policies.items():
            frame = model_frame.copy()
            frame["issue_numeric"] = pd.to_numeric(frame["issue"], errors="raise")
            frame = frame.sort_values(["issue_year", "issue_numeric"])
            pnl = frame[pnl_column].to_numpy(float)
            stake = frame[stake_column].to_numpy(float)
            capital = 100_000.0 + np.cumsum(pnl)
            peaks = np.maximum.accumulate(np.r_[100_000.0, capital])
            drawdown = 1.0 - np.r_[100_000.0, capital] / peaks
            largest = int(np.argmax(pnl))
            bootstrap = _bootstrap_roi(pnl, stake)
            annual = frame.assign(_pnl=pnl, _stake=stake).groupby(
                "issue_year", as_index=False
            ).agg(pnl_cny=("_pnl", "sum"), stake_cny=("_stake", "sum"))
            annual["roi_pct"] = np.divide(
                annual["pnl_cny"], annual["stake_cny"],
                out=np.full(len(annual), np.nan), where=annual["stake_cny"].gt(0),
            ) * 100.0
            annual["model"] = model
            annual["policy"] = policy
            annual_rows.append(annual)
            formal = frame["formal_baseline_pnl_cny"].to_numpy(float)
            lift = pnl - formal
            completed_recovery, open_underwater = _recovery_diagnostics(capital)
            summary_rows.append(
                {
                    "model": model,
                    "policy": policy,
                    "issues": len(frame),
                    "turnover_cny": float(stake.sum()),
                    "pnl_cny": float(pnl.sum()),
                    "roi_pct": float(pnl.sum() / stake.sum() * 100.0) if stake.sum() else np.nan,
                    "ending_capital_cny": float(capital[-1]),
                    "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest]),
                    "ex_largest_roi_pct": float(
                        (pnl.sum() - pnl[largest]) / (stake.sum() - stake[largest]) * 100.0
                    ) if stake.sum() > stake[largest] else np.nan,
                    "bootstrap_roi_p025": float(np.quantile(bootstrap, 0.025) * 100.0),
                    "bootstrap_roi_p975": float(np.quantile(bootstrap, 0.975) * 100.0),
                    "positive_years": int((annual["pnl_cny"] > 0).sum()),
                    "max_drawdown_pct": float(drawdown.max() * 100.0),
                    "longest_losing_issue_streak": _longest_loss_streak(pnl),
                    "worst_rolling_5_pnl_cny": float(pd.Series(pnl).rolling(5).sum().min()),
                    "worst_rolling_10_pnl_cny": float(pd.Series(pnl).rolling(10).sum().min()),
                    "worst_rolling_20_pnl_cny": float(pd.Series(pnl).rolling(20).sum().min()),
                    "maximum_completed_recovery_issues": completed_recovery,
                    "open_terminal_underwater_issues": open_underwater,
                    "matched_lift_vs_formal_cny": float(lift.sum()),
                    "ex_largest_matched_lift_cny": float(lift.sum() - lift.max()),
                }
            )
            path_rows.append(
                pd.DataFrame(
                    {
                        "issue": frame["issue"].to_numpy(),
                        "issue_year": frame["issue_year"].to_numpy(),
                        "model": model,
                        "policy": policy,
                        "pnl_cny": pnl,
                        "stake_cny": stake,
                        "capital_cny": capital,
                    }
                )
            )
    summary = pd.DataFrame(summary_rows)
    annual = pd.concat(annual_rows, ignore_index=True)
    paths = pd.concat(path_rows, ignore_index=True)
    protection = selected.groupby(["model", "issue_year"], as_index=False).agg(
        issues=("issue", "nunique"),
        funded_issues=("funded", "sum"),
        protection_tickets=("funded_protection_count", "sum"),
        predicted_protection_pnl_cny=("predicted_protection_pnl_cny", "sum"),
        actual_protection_pnl_cny=("actual_protection_pnl_cny", "sum"),
        base_pnl_cny=("base_pnl_cny", "sum"),
        joint_pnl_cny=("actual_total_pnl_cny", "sum"),
    )
    action_distribution = (
        selected.loc[selected["funded"]]
        .groupby(
            ["model", "n", "k", "selector", "outcome_mode", "generator", "protection_share"],
            as_index=False,
        )
        .agg(issues=("issue", "nunique"), protection_tickets=("funded_protection_count", "sum"))
        .sort_values(["model", "issues"], ascending=[True, False])
    )
    candidate_labels = pd.read_parquet(
        source / "candidate_settlement_labels.parquet",
        columns=["issue_year", "settlement_valid", "hit", "stake_cny", "gross_cny", "pnl_cny"],
    )
    candidate_universe = candidate_labels.groupby("issue_year", as_index=False).agg(
        candidates=("hit", "size"),
        valid_candidates=("settlement_valid", "sum"),
        winning_candidates=("hit", "sum"),
        stake_cny=("stake_cny", "sum"),
        gross_cny=("gross_cny", "sum"),
        pnl_cny=("pnl_cny", "sum"),
    )
    candidate_universe["winner_rate"] = (
        candidate_universe["winning_candidates"]
        / candidate_universe["valid_candidates"]
    )
    outputs = {
        "comparison": output / "joint_policy_comparison_summary.csv",
        "annual": output / "joint_policy_annual.csv",
        "capital_paths": output / "joint_policy_capital_paths.csv",
        "protection": output / "joint_policy_protection_attribution.csv",
        "action_distribution": output / "joint_policy_action_distribution.csv",
        "candidate_universe": output / "candidate_universe_summary.csv",
    }
    summary.to_csv(outputs["comparison"], index=False)
    annual.to_csv(outputs["annual"], index=False)
    paths.to_csv(outputs["capital_paths"], index=False)
    protection.to_csv(outputs["protection"], index=False)
    action_distribution.to_csv(outputs["action_distribution"], index=False)
    candidate_universe.to_csv(outputs["candidate_universe"], index=False)
    _figure(paths, args.figure_output.resolve())
    receipt = {
        "contract": "BJ-UNIFIED-JOINT-PROTECTION-001/analysis-v1",
        "independent_unit": "BEIJING_ISSUE",
        "primary_capital": "ACTUAL_CNY2_PER_UNIQUE_TICKET",
        "bootstrap_draws": 5000,
        "bootstrap_seed": 286_999,
        "chronology": "ISSUE_YEAR_THEN_NUMERIC_ISSUE",
        "formal_baseline_causality_note": "SELECTED_ON_2014_2022; ONLY_2023_IS_FROZEN_HOLDOUT",
        "input_sha256": {
            "selected_actions": _sha256(source / "joint_oof_selected_actions.parquet"),
            "candidate_labels": _sha256(source / "candidate_settlement_labels.parquet"),
        },
        "output_sha256": {name: _sha256(path) for name, path in outputs.items()},
    }
    (output / "joint_policy_analysis_receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(summary.to_string(index=False), flush=True)
    return 0


def _bootstrap_roi(pnl: np.ndarray, stake: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(286_999)
    draws = np.empty(5000)
    for draw in range(len(draws)):
        index = rng.integers(0, len(pnl), len(pnl))
        sampled_stake = stake[index].sum()
        draws[draw] = pnl[index].sum() / sampled_stake if sampled_stake else 0.0
    return draws


def _figure(paths: pd.DataFrame, destination: Path) -> None:
    focus = paths.loc[
        paths["model"].eq("DATA_HGB")
        & paths["policy"].isin(
            ["LEARNED_JOINT", "SELECTED_BASE_NO_PROTECTION", "FORMAL_N7_K8_MARKET_TOP"]
        )
    ]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for policy, group in focus.groupby("policy", sort=True):
        axes[0].plot(np.arange(1, len(group) + 1), group["capital_cny"], label=policy)
        annual = group.groupby("issue_year", as_index=False)["pnl_cny"].sum()
        axes[1].plot(annual["issue_year"], annual["pnl_cny"], marker="o", label=policy)
    axes[0].axhline(100_000, color="black", linewidth=0.8)
    axes[0].set(title="Issue-level capital path", xlabel="Chronological OOF issue", ylabel="CNY")
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set(title="Annual OOF P&L", xlabel="Year", ylabel="CNY")
    for axis in axes:
        axis.legend(fontsize=8)
    fig.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def _longest_loss_streak(pnl: np.ndarray) -> int:
    longest = current = 0
    for value in pnl:
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
    return longest


def _recovery_diagnostics(capital: np.ndarray) -> tuple[int, int]:
    """Separate completed recovery time from terminal right-censoring."""

    path = np.r_[100_000.0, capital]
    peak = path[0]
    underwater_start: int | None = None
    longest = 0
    for index, value in enumerate(path[1:], 1):
        if value >= peak:
            if underwater_start is not None:
                longest = max(longest, index - underwater_start)
                underwater_start = None
            peak = value
        elif underwater_start is None:
            underwater_start = index
    open_underwater = len(path) - underwater_start if underwater_start is not None else 0
    return longest, open_underwater


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
