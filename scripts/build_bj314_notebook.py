#!/usr/bin/env python3
"""Build and execute the Issue #314 decision notebook."""

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


def main() -> None:
    target = Path("notebooks/research/issue-314/bj314_core_tail_moe.ipynb")
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            """# Issue #314 — CORE/TAIL soft-MoE and explicit coverage

This notebook reads the immutable result package. It shows the chronological
freeze, exact 2023 baseline anchor, one-shot 2024 capital paths, matched factor
resets and near-miss attribution. Beijing's 0.65 factor is applied once per
complete winning N-fold ticket."""
        ),
        nbf.v4.new_code_cell(
            """from pathlib import Path
import json
import pandas as pd
from IPython.display import Image, display

ROOT = next(path for path in (Path.cwd(), *Path.cwd().parents)
            if (path / 'results' / 'issue-314').is_dir())
OUTPUT = ROOT / 'results' / 'issue-314'
freeze = json.loads((OUTPUT / 'freeze_receipt.json').read_text())
decision = json.loads((OUTPUT / 'decision.json').read_text())
display(freeze)
display(decision)"""
        ),
        nbf.v4.new_markdown_cell("## Causal support and expert library"),
        nbf.v4.new_code_cell(
            """support = pd.read_csv(OUTPUT / 'support_receipt.csv')
experts = pd.read_csv(OUTPUT / 'expert_registry.csv')
display(support)
display(experts[['name','sleeve','n','selector','outcome_direction',
                 'generator','protection','protected_leg_count']])"""
        ),
        nbf.v4.new_markdown_cell("## 2022 screen and model-unseen 2023 validation"),
        nbf.v4.new_code_cell(
            """screen = pd.read_csv(OUTPUT / 'screening_2022.csv')
validation = pd.read_csv(OUTPUT / 'validation_summary_2023.csv')
display(screen[['model_family','tail_fraction','median_terminal_capital_cny',
                'median_stake_cny','median_turnover_roi']])
display(validation.sort_values('median_terminal_capital_cny', ascending=False))"""
        ),
        nbf.v4.new_markdown_cell("## Frozen 2024 allocations and terminal paths"),
        nbf.v4.new_code_cell(
            """alloc = pd.read_json(OUTPUT / 'frozen_allocations_2024.jsonl', lines=True,
                     dtype={'issue': str})
summary = pd.read_csv(OUTPUT / 'terminal_summary_2024.csv')
display(alloc.groupby(['condition','total_k'], as_index=False)
        .agg(issues=('issue','nunique')))
display(summary.sort_values('median_terminal_capital_cny', ascending=False))
display(Image(filename=str(OUTPUT / 'capital_paths_2024.png')))
display(Image(filename=str(OUTPUT / 'risk_return_frontier_2024.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Matched factor attribution"),
        nbf.v4.new_code_cell(
            """factors = pd.read_csv(OUTPUT / 'matched_factor_attribution_2024.csv')
display(factors.sort_values('median_seed_lift_cny', ascending=False))"""
        ),
        nbf.v4.new_markdown_cell("## Near-miss reasons and funded protection counterfactual"),
        nbf.v4.new_code_cell(
            """near = pd.read_parquet(OUTPUT / 'terminal_near_miss_2024.parquet')
display(near.groupby('condition', as_index=False).agg(
    miss_one=('miss_one_count','sum'), miss_two=('miss_two_count','sum'),
    outside_support=('outcome_outside_support','sum'),
    finite_sampling=('finite_sampling_branch','sum'),
    added_stake=('one_more_protection_stake_cny','sum'),
    added_pnl=('one_more_protection_pnl_cny','sum')))
display(Image(filename=str(OUTPUT / 'near_miss_attribution_2024.png')))"""
        ),
        nbf.v4.new_markdown_cell(
            """## Decision reading

The exact #312 control is retained for the 2023 validation anchor. Because its
fitted ticket identities do not exist for 2024, the terminal control is named
`PORTABLE_N7_K512_WOR` and is not represented as a byte-identical continuation.
Only a learned policy that passed 2023 could become promotable; a lucky 2024
raw challenger cannot retroactively pass the guard."""
        ),
    ]
    NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(Path.cwd())}},
    ).execute()
    nbf.write(notebook, target)
    print(target)


if __name__ == "__main__":
    main()
