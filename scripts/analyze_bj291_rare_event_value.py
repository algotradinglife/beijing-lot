#!/usr/bin/env python3
"""Create compact decision diagnostics for Issue #291."""

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
    parser.add_argument("--input", type=Path, default=ROOT / "results/issue-291")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/research/artifacts/issue-291"
    )
    parser.add_argument(
        "--figure",
        type=Path,
        default=ROOT / "docs/research/figures/issue_291_rare_event_value.png",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(source / "model_metrics.csv")
    ranking = pd.read_csv(source / "ranking_metrics.csv")
    paths = pd.read_csv(source / "ranking_issue_paths.csv")
    selected_tickets = pd.read_csv(
        source / "ranking_selected_tickets.csv",
        dtype={"ticket_identity": "string", "candidate_identity": "string"},
        low_memory=False,
    )
    reliability = pd.read_csv(source / "reliability_bins.csv")
    attribution = pd.read_csv(source / "issue_2023_top_predictions.csv")

    model_summary = metrics.groupby(["domain", "model"], as_index=False).agg(
        brier=("brier", "mean"),
        log_loss=("log_loss", "mean"),
        average_precision=("average_precision", "mean"),
        event_rate=("weighted_event_rate", "mean"),
        predicted_rate=("weighted_predicted_rate", "mean"),
        conditional_gross_mae_cny=("conditional_gross_mae_cny", "mean"),
    )
    model_summary["average_precision_lift"] = (
        model_summary["average_precision"] / model_summary["event_rate"]
    )
    rows = []
    capital_paths = []
    for keys, group in paths.groupby(
        ["domain", "model", "score", "ticket_budget_per_issue"], sort=True
    ):
        domain, model, score, budget = keys
        group = group.copy()
        group["issue_numeric"] = pd.to_numeric(group["issue"], errors="raise")
        group = group.sort_values(["oof_year", "issue_numeric"]).reset_index(drop=True)
        pnl = group["pnl_cny"].to_numpy(float)
        stake = group["stake_cny"].to_numpy(float)
        capital = 100_000.0 + np.cumsum(pnl)
        peaks = np.maximum.accumulate(np.r_[100_000.0, capital])
        drawdown = 1.0 - np.r_[100_000.0, capital] / peaks
        completed_recovery, open_underwater = _recovery_diagnostics(capital)
        group["capital_cny"] = capital
        capital_paths.append(group)
        total_pnl = float(pnl.sum())
        largest_issue_pnl = float(pnl.max())
        annual = group.groupby("oof_year")["pnl_cny"].sum()
        bootstrap = _bootstrap_roi(pnl, stake)
        rows.append(
            {
                "domain": domain,
                "model": model,
                "score": score,
                "ticket_budget_per_issue": int(budget),
                "issues": int(group["issue"].nunique()),
                "tickets": int(group["tickets"].sum()),
                "hits": int(group["hits"].sum()),
                "hit_rate": float(group["hits"].sum() / group["tickets"].sum()),
                "gross_cny": float(group["gross_cny"].sum()),
                "pnl_cny": total_pnl,
                "global_ex_largest_issue_pnl_cny": total_pnl - largest_issue_pnl,
                "bootstrap_roi_p025": float(np.quantile(bootstrap, 0.025) * 100.0),
                "bootstrap_roi_p975": float(np.quantile(bootstrap, 0.975) * 100.0),
                "positive_years": int((annual > 0).sum()),
                "max_drawdown_pct": float(drawdown.max() * 100.0),
                "longest_losing_issue_streak": _longest_loss_streak(pnl),
                "worst_rolling_5_pnl_cny": float(pd.Series(pnl).rolling(5).sum().min()),
                "worst_rolling_10_pnl_cny": float(pd.Series(pnl).rolling(10).sum().min()),
                "worst_rolling_20_pnl_cny": float(pd.Series(pnl).rolling(20).sum().min()),
                "maximum_completed_recovery_issues": completed_recovery,
                "open_terminal_underwater_issues": open_underwater,
            }
        )
    ranking_summary = pd.DataFrame(rows)
    candidate = selected_tickets.loc[
        selected_tickets["domain"].eq("BASE")
        & selected_tickets["model"].eq("DATA_LOGIT_RIDGE")
        & selected_tickets["score"].eq("DIRECT_PNL")
        & selected_tickets["ticket_budget_per_issue"].eq(64)
    ].copy()
    action_distribution = candidate.groupby(
        ["n", "k", "selector", "outcome_mode", "generator"], as_index=False
    ).agg(
        tickets=("rank", "size"),
        issues=("issue", "nunique"),
        hits=("hit", "sum"),
        gross_cny=("gross_cny", "sum"),
        pnl_cny=("pnl_cny", "sum"),
    )
    candidate_2023 = candidate.loc[candidate["oof_year"].eq(2023)].copy()
    outputs = {
        "model_summary": output / "model_summary.csv",
        "ranking_summary": output / "ranking_summary.csv",
        "ranking_annual": output / "ranking_annual.csv",
        "ranking_paths": output / "ranking_issue_paths.csv",
        "reliability": output / "reliability_bins.csv",
        "attribution_2023": output / "issue_2023_top_predictions.csv",
        "candidate_action_distribution": output / "candidate_action_distribution.csv",
        "candidate_2023_tickets": output / "candidate_2023_selected_tickets.csv",
    }
    model_summary.to_csv(outputs["model_summary"], index=False)
    ranking_summary.to_csv(outputs["ranking_summary"], index=False)
    ranking.to_csv(outputs["ranking_annual"], index=False)
    pd.concat(capital_paths, ignore_index=True).to_csv(outputs["ranking_paths"], index=False)
    reliability.to_csv(outputs["reliability"], index=False)
    attribution.to_csv(outputs["attribution_2023"], index=False)
    action_distribution.to_csv(outputs["candidate_action_distribution"], index=False)
    candidate_2023.to_csv(outputs["candidate_2023_tickets"], index=False)
    _figure(model_summary, ranking_summary, args.figure.resolve())
    upstream = json.loads((source / "oof_receipt.json").read_text())
    receipt = {
        "contract": "BJ-UNIFIED-RARE-EVENT-VALUE-001/analysis-v1",
        "independent_unit": "BEIJING_ISSUE",
        "sealed_years_opened": upstream["sealed_years_opened"],
        "input_sha256": {
            "oof_receipt": _sha256(source / "oof_receipt.json"),
            "model_metrics": _sha256(source / "model_metrics.csv"),
            "ranking_metrics": _sha256(source / "ranking_metrics.csv"),
            "ranking_issue_paths": _sha256(source / "ranking_issue_paths.csv"),
            "ranking_selected_tickets": _sha256(source / "ranking_selected_tickets.csv"),
        },
        "output_sha256": {name: _sha256(path) for name, path in outputs.items()},
    }
    (output / "analysis_receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(model_summary.to_string(index=False), flush=True)
    print(
        ranking_summary.loc[
            ranking_summary["ticket_budget_per_issue"].eq(64)
            & ranking_summary["domain"].eq("PROTECTION")
        ].to_string(index=False),
        flush=True,
    )
    return 0


def _figure(
    model_summary: pd.DataFrame,
    ranking_summary: pd.DataFrame,
    destination: Path,
) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    pivot = model_summary.pivot(
        index="model", columns="domain", values="average_precision_lift"
    )
    pivot.plot.bar(ax=axes[0], color=["#4C78A8", "#F58518"])
    axes[0].axhline(1.0, color="black", linewidth=0.8)
    axes[0].set(title="Average-precision lift", ylabel="AP / event rate", xlabel="")

    protection = ranking_summary.loc[
        ranking_summary["domain"].eq("PROTECTION")
        & ranking_summary["ticket_budget_per_issue"].eq(64)
        & (
            ranking_summary["score"].eq("HIT_PROBABILITY")
            | ranking_summary["score"].isin(
                ["MARKET_PRODUCT", "ADVERSE_DIVERGENCE", "RANDOM"]
            )
        )
    ].copy()
    protection["label"] = np.where(
        protection["model"].eq("CONTROL"), protection["score"], protection["model"]
    )
    protection = protection.sort_values("hit_rate", ascending=False)
    axes[1].bar(protection["label"], protection["hit_rate"] * 100.0, color="#54A24B")
    axes[1].tick_params(axis="x", rotation=70)
    axes[1].set(title="Protection Top-64 hit rate", ylabel="Percent", xlabel="")
    axes[2].bar(
        protection["label"],
        protection["pnl_cny"],
        color=np.where(protection["pnl_cny"].ge(0), "#54A24B", "#E45756"),
    )
    axes[2].axhline(0, color="black", linewidth=0.8)
    axes[2].tick_params(axis="x", rotation=70)
    axes[2].set(title="Protection Top-64 P&L", ylabel="CNY", xlabel="")
    fig.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bootstrap_roi(pnl: np.ndarray, stake: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(291_999)
    draws = np.empty(5_000)
    for index in range(len(draws)):
        sampled = rng.integers(0, len(pnl), len(pnl))
        draws[index] = pnl[sampled].sum() / stake[sampled].sum()
    return draws


def _longest_loss_streak(pnl: np.ndarray) -> int:
    longest = current = 0
    for value in pnl:
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
    return longest


def _recovery_diagnostics(capital: np.ndarray) -> tuple[int, int]:
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


if __name__ == "__main__":
    raise SystemExit(main())
