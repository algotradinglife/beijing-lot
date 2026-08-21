#!/usr/bin/env python3
"""Build the executable Issue #296 decision notebook."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf


def main() -> None:
    target = Path("notebooks/research/issue-296/bj296_expert_mixture.ipynb")
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.14"},
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            """# Issue #296 — candidate-warm-start expert mixture

This notebook rebuilds the matched expert panel, trains the chronological
expert gate, applies the frozen validation fallback, and presents the 2023
CNY100,000 issue-level capital paths. The runner refuses to open 2024+ rows.

Primary conclusion: **NO_PROMOTION**. The raw warm-start ensemble is positive
for all five seeds in the 2023 development replay, but fails 2022 validation
and every seed is negative after removing its largest issue. The implementation
safety constraint therefore falls back to the frozen static control before the
2023 path is read."""
        ),
        nbf.v4.new_code_cell(
            """from pathlib import Path
import json
import pandas as pd
from IPython.display import Image, display

from issue296.experiment import run_experiment

ROOT = Path.cwd()
OUTPUT = ROOT / "results/issue-296"
decision = run_experiment(ROOT, OUTPUT)
decision"""
        ),
        nbf.v4.new_markdown_cell("## Frozen expert inventory and support"),
        nbf.v4.new_code_cell(
            """registry = pd.read_csv(OUTPUT / "expert_registry.csv")
panel = pd.read_csv(OUTPUT / "matched_expert_panel.csv")
display(registry)
display(panel.groupby("expert_id").agg(
    calendar_issues=("issue", "size"),
    available_issues=("available", "sum"),
    active_issues=("stake_unit_cny", lambda values: int((values > 0).sum())),
).reset_index())"""
        ),
        nbf.v4.new_markdown_cell(
            """`N7_K16_WR` is intentionally registry-only: #292 supplied a
summary distribution but no trusted issue path. A missing ledger row is kept
unavailable; a real zero-stake row remains a valid frozen NO_BET."""
        ),
        nbf.v4.new_markdown_cell("## Chronological performance"),
        nbf.v4.new_code_cell(
            """period = pd.read_csv(OUTPUT / "policy_period_summary.csv")
focus = [
    "CONTROL_CASH_NO_BET", "CONTROL_FULL_CONTROL", "STATIC_TRAIN_LOG_GROWTH",
    "RIDGE_CONTROL", "candidate_warm", "neutral", "identity_shuffled",
    "candidate_warm_guarded",
]
columns = [
    "condition", "period", "terminal_capital_cny", "capital_growth_pct",
    "turnover_roi_pct", "max_drawdown_pct", "longest_losing_issue_streak",
    "rolling_10_loss_probability", "ex_largest_pnl_cny",
]
display(period[period.condition.isin(focus)][columns])"""
        ),
        nbf.v4.new_code_cell(
            """display(Image(filename=str(OUTPUT / "capital_paths_2023.png")))
display(Image(filename=str(OUTPUT / "drawdown_2023.png")))"""
        ),
        nbf.v4.new_markdown_cell("## Seed stability and validation fallback"),
        nbf.v4.new_code_cell(
            """seed = pd.read_csv(OUTPUT / "seed_summary_2023.csv")
display(seed[[
    "model_condition", "model_seed", "capital_growth_pct",
    "max_drawdown_pct", "ex_largest_pnl_cny",
]])
display(pd.read_csv(OUTPUT / "validation_fallback_receipts.csv"))"""
        ),
        nbf.v4.new_markdown_cell("## What the learned gate allocated"),
        nbf.v4.new_code_cell(
            """weights = pd.read_csv(OUTPUT / "weights_candidate_warm.csv")
weight_columns = [column for column in weights if column.startswith("weight_")]
display(
    weights[weights.issue_year.eq(2023)][weight_columns]
    .mean().sort_values(ascending=False).rename("mean_2023_weight").to_frame()
)
display(Image(filename=str(OUTPUT / "candidate_warm_weights_2023.png")))"""
        ),
        nbf.v4.new_markdown_cell("## Static core–tail curve and expert dependence"),
        nbf.v4.new_code_cell(
            """display(Image(filename=str(OUTPUT / "core_tail_frontier.png")))
display(Image(filename=str(OUTPUT / "expert_return_correlation.png")))
dependence = pd.read_csv(OUTPUT / "expert_dependence.csv")
display(
    dependence[dependence.expert_left < dependence.expert_right]
    .sort_values("return_correlation")
    .head(10)
)"""
        ),
        nbf.v4.new_markdown_cell("## Machine decision and reproducibility receipt"),
        nbf.v4.new_code_cell(
            """display(json.loads((OUTPUT / "decision.json").read_text()))
display(json.loads((OUTPUT / "manifest.json").read_text()))"""
        ),
    ]
    nbf.write(notebook, target)
    print(target)


if __name__ == "__main__":
    main()
