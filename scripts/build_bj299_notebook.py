#!/usr/bin/env python3
"""Build the executed decision notebook for Issue #299."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf


def main() -> None:
    target = Path("notebooks/research/issue-299/bj299_best_full_residual.ipynb")
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
            """# Issue #299 — BEST_FULL-anchored residual learning

This notebook reproduces `exact BEST_FULL + learned residual` on the 227-issue
matched calendar. The model trains on 2019–2021, uses 2022 for the no-regression
gate, freezes for 2023, and cannot open 2024+ rows.

Primary conclusion: **RELATIVE_BASELINE_SIGNAL_NO_PROMOTION**. Dynamic residual
learning materially reduces the accepted baseline loss and drawdown, but 2023
remains negative and the learned action placement does not beat an
exposure-matched random permutation control."""
        ),
        nbf.v4.new_code_cell(
            """from pathlib import Path
import sys
import json
import pandas as pd
from IPython.display import Image, display

ROOT = next(
    path
    for path in (Path.cwd(), *Path.cwd().parents)
    if (path / "src" / "issue299").is_dir()
)
sys.path.insert(0, str(ROOT / "src"))
from issue299.experiment import run_experiment

OUTPUT = ROOT / "results/issue-299"
decision = run_experiment(ROOT, OUTPUT)
decision"""
        ),
        nbf.v4.new_markdown_cell("## Exact support and baseline reproduction"),
        nbf.v4.new_code_cell(
            """support = pd.read_csv(OUTPUT / "support_receipt.csv")
display(support.support_status.value_counts().rename("issues").to_frame())
display(json.loads((OUTPUT / "baseline_reproduction.json").read_text()))"""
        ),
        nbf.v4.new_markdown_cell("## Matched capital and residual lift"),
        nbf.v4.new_code_cell(
            """summary = pd.read_csv(OUTPUT / "policy_summary_by_year.csv")
focus = ["BEST_FULL_BASELINE", "LEARNED_RESIDUAL", "GUARDED_RESIDUAL",
         "RIDGE_RESIDUAL_CONTROL", "SELECTION_ONLY_GATE",
         "STATIC_TRAIN_BASELINE_PLUS_MIXED", "IDENTITY_SHUFFLED"]
cols = ["evaluation_year", "condition", "terminal_capital_cny",
        "capital_growth_pct", "max_drawdown_pct", "stake_cny",
        "worst_rolling_10_pnl_cny", "ex_largest_pnl_cny"]
display(summary[(summary.evaluation_year >= 2022) & summary.condition.isin(focus)][cols])
display(Image(filename=str(OUTPUT / "capital_paths_2023.png")))
display(Image(filename=str(OUTPUT / "learned_minus_best_full_2023.png")))"""
        ),
        nbf.v4.new_markdown_cell("## What changed and whether placement added skill"),
        nbf.v4.new_code_cell(
            """display(pd.read_csv(OUTPUT / "action_attribution_2023.csv"))
permutation = pd.read_csv(OUTPUT / "exposure_matched_permutation.csv")
display(permutation.groupby("issue_year").terminal_capital_cny.describe(percentiles=[.05,.5,.95]))
display(Image(filename=str(OUTPUT / "action_attribution_2023.png")))"""
        ),
        nbf.v4.new_markdown_cell("## Calibration, seed stability and validation gate"),
        nbf.v4.new_code_cell(
            """display(pd.read_csv(OUTPUT / "seed_summary.csv"))
display(json.loads((OUTPUT / "validation_gate.json").read_text()))
display(Image(filename=str(OUTPUT / "residual_calibration.png")))"""
        ),
        nbf.v4.new_markdown_cell("## Machine decision and manifest"),
        nbf.v4.new_code_cell(
            """display(json.loads((OUTPUT / "decision.json").read_text()))
display(json.loads((OUTPUT / "manifest.json").read_text()))"""
        ),
    ]
    nbf.write(notebook, target)
    print(target)


if __name__ == "__main__":
    main()
