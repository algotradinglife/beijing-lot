#!/usr/bin/env python3
"""Analyze the thin #284 outcome-mode × joint-parameter screen."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from issue284.outcome_joint import (
    annual_actions,
    build_issue_action_table,
    development_holdout_rank_spearman,
    summarize_actions,
)

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--artifact-name", default="joint_outcome_mode_pilot")
    parser.add_argument("--result-prefix", default="outcome_joint")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    prefix = args.result_prefix
    raw = pd.read_parquet(output / f"{args.artifact_name}.parquet")
    table = build_issue_action_table(raw)
    summary = summarize_actions(table)
    annual = annual_actions(table)
    rank_transfer = development_holdout_rank_spearman(summary)
    best_by_mode = (
        summary.sort_values("development_roi_pct", ascending=False)
        .groupby("outcome_weight_mode", as_index=False)
        .head(1)
    )
    receipt = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-outcome-joint-pilot",
        "issues": int(table["issue"].nunique()),
        "raw_rows": int(len(raw)),
        "actions": int(len(summary)),
        "n": sorted(int(value) for value in table["n"].unique()),
        "k": sorted(int(value) for value in table["requested_k"].unique()),
        "generators": sorted(table["generator"].unique()),
        "selector_families": sorted(table["proposal_family"].unique()),
        "outcome_weight_modes": sorted(table["outcome_weight_mode"].unique()),
        "development_holdout_action_rank_spearman": rank_transfer,
        "sealed_years_opened": [],
        "interpretation": (
            "Thin interaction screen. Subset identity and stream seed remain "
            "nuisance; no development winner is a frozen candidate."
        ),
    }
    _atomic_csv(table, output / f"{prefix}_issue_actions.csv")
    _atomic_csv(summary, output / f"{prefix}_action_summary.csv")
    _atomic_csv(annual, output / f"{prefix}_annual.csv")
    _atomic_csv(best_by_mode, output / f"{prefix}_best_by_mode.csv")
    _atomic_json(receipt, output / f"{prefix}_analysis_receipt.json")
    _plot_mode_transfer(summary, output / f"{prefix}_mode_transfer.png")
    print(json.dumps(receipt, indent=2), flush=True)
    print(best_by_mode.to_string(index=False), flush=True)
    return 0


def _plot_mode_transfer(summary: pd.DataFrame, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(8, 6))
    for mode, group in summary.groupby("outcome_weight_mode"):
        axis.scatter(
            group["development_roi_pct"],
            group["holdout_roi_pct"],
            s=18,
            alpha=0.55,
            label=mode,
        )
    axis.axhline(0.0, color="black", linewidth=0.7)
    axis.axvline(0.0, color="black", linewidth=0.7)
    axis.set(
        title="Subset action transfer: development versus 2023",
        xlabel="2014–2022 ROI (%)",
        ylabel="2023 ROI (%)",
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
