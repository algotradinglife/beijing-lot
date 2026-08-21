#!/usr/bin/env python3
"""Reuse #282 labels to diagnose outcome-value modes before extending #284."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from issue284.outcome_surface import (
    annual_action_returns,
    development_holdout_rank_spearman,
    load_counterfactual_labels,
    summarize_actions,
    summarize_focus_modes,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path("/home/drwho1985/.cache/codex-pi/bj282-policy/results/issue-282")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--bootstrap-draws", type=int, default=5_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    labels = load_counterfactual_labels(source.glob("counterfactual_labels_*.parquet"))
    actions = summarize_actions(labels)
    annual = annual_action_returns(labels)
    focus = summarize_focus_modes(labels, draws=args.bootstrap_draws)
    rank_transfer = development_holdout_rank_spearman(actions)
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-outcome-surface-reuse",
        "source_contract": "BJ-UNIFIED-N-ADAPTIVE-001/#282-counterfactual-labels",
        "source_directory": str(source),
        "issues": int(labels["issue"].nunique()),
        "years": sorted(int(value) for value in labels["issue_year"].unique()),
        "actions": int(len(actions)),
        "outcome_weight_modes": sorted(labels["outcome_weight_mode"].unique()),
        "development_end": 2022,
        "holdout_year": 2023,
        "development_holdout_action_rank_spearman": rank_transfer,
        "sealed_years_opened": [],
        "interpretation": (
            "Outcome-value mode is a candidate action dimension, but development "
            "ranking does not transfer reliably to 2023. Do not promote a fixed "
            "mode or treat the full-period descriptive winner as causal evidence."
        ),
    }
    _atomic_csv(actions, output / "outcome_surface_action_summary.csv")
    _atomic_csv(annual, output / "outcome_surface_annual.csv")
    _atomic_csv(focus, output / "outcome_surface_n7_top_k8.csv")
    _atomic_json(receipt, output / "outcome_surface_reuse_receipt.json")
    _plot_focus(annual, output / "outcome_surface_n7_top_k8_yearly.png")
    _plot_transfer(actions, output / "outcome_surface_dev_holdout_transfer.png")
    print(json.dumps(receipt, indent=2), flush=True)
    print(focus.to_string(index=False), flush=True)
    return 0


def _plot_focus(annual: pd.DataFrame, path: Path) -> None:
    focus = annual.loc[
        annual["selector"].eq("ALL")
        & annual["n"].eq(7)
        & annual["generator"].eq("TOP_VALUE")
        & annual["k"].eq(8)
    ]
    figure, axis = plt.subplots(figsize=(10, 5))
    for mode, group in focus.groupby("outcome_weight_mode"):
        axis.plot(group["issue_year"], group["roi_pct"], marker="o", label=mode)
    axis.axhline(0.0, color="black", linewidth=0.8)
    axis.axvline(2022.5, color="grey", linestyle="--", linewidth=1.0)
    axis.set(title="N7 / TOP / K8 outcome-value mode by year", xlabel="Year", ylabel="Pre-tax ROI (%)")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _plot_transfer(actions: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 6))
    for mode, group in actions.groupby("outcome_weight_mode"):
        axis.scatter(
            group["development_roi_pct"],
            group["holdout_roi_pct"],
            alpha=0.55,
            s=18,
            label=mode,
        )
    axis.axhline(0.0, color="black", linewidth=0.7)
    axis.axvline(0.0, color="black", linewidth=0.7)
    axis.set(
        title="Fixed-action development-to-2023 transfer",
        xlabel="2014–2022 mean ROI (%)",
        ylabel="2023 mean ROI (%)",
    )
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=180)
    plt.close(figure)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
