#!/usr/bin/env python3
"""Build the executed decision notebook for Issue #302."""

from pathlib import Path

import nbformat as nbf


def main() -> None:
    target = Path("notebooks/research/issue-302/bj302_hierarchical_dynamic_moe.ipynb")
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.14"},
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            """# Issue #302 — BEST_FULL-anchored hierarchical dynamic experts

The experiment asks whether a shared action-conditioned learner can first keep
or skip exact atomic BEST_FULL and then dynamically allocate remaining bankroll
among four realizable experts and cash. All displayed policy decisions are
expanding-window predictions through 2023; 2024+ remains sealed."""
        ),
        nbf.v4.new_code_cell(
            """from pathlib import Path
import json
import pandas as pd
from IPython.display import Image, display

ROOT = next(path for path in (Path.cwd(), *Path.cwd().parents) if (path / 'src' / 'issue302').is_dir())
OUTPUT = ROOT / 'results/issue-302'
decision = json.loads((OUTPUT / 'decision.json').read_text())
decision"""
        ),
        nbf.v4.new_markdown_cell("## Matched results and stage attribution"),
        nbf.v4.new_code_cell(
            """summary = pd.read_csv(OUTPUT / 'policy_summary.csv')
focus = ['B0_BEST_FULL','GUARDED_DYNAMIC_MOE','DYNAMIC_KEEP_ONLY','RAW_DYNAMIC_KELLY',
         'STATIC_TRAIN_ONLY','STATE_SHUFFLED','IDENTITY_SHUFFLED','RIDGE_CONTROL','HGB_CONTROL']
cols = ['evaluation_year','condition','funded_issues','terminal_capital_cny','capital_growth_pct',
        'max_drawdown_pct','longest_losing_issue_streak','worst_rolling_10_pnl_cny','stake_cny']
display(summary[summary.condition.isin(focus)][cols])
display(pd.read_csv(OUTPUT / 'stage_attribution_2023.csv'))
display(Image(filename=str(OUTPUT / 'capital_paths_2023.png')))
display(Image(filename=str(OUTPUT / 'stage_attribution_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Dynamic expert funding and causal selection"),
        nbf.v4.new_code_cell(
            """display(pd.read_csv(OUTPUT / 'funding_scale_receipt.csv'))
curve = pd.read_csv(OUTPUT / 'outcome_exposed_funding_curve_2023.csv')
display(curve.nlargest(10, 'terminal_capital_cny')[['funding_scale','terminal_capital_cny','capital_growth_pct','max_drawdown_pct','stake_cny']])
display(Image(filename=str(OUTPUT / 'dynamic_weights_2023.png')))
display(Image(filename=str(OUTPUT / 'outcome_exposed_funding_curve_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Falsification and calibration"),
        nbf.v4.new_code_cell(
            """permutation = pd.read_csv(OUTPUT / 'exposure_matched_permutation_2023.csv')
display(permutation.terminal_capital_cny.describe(percentiles=[.05,.5,.81,.95]))
display(pd.read_csv(OUTPUT / 'value_calibration.csv'))"""
        ),
        nbf.v4.new_markdown_cell(
            """## Interpretation

The causal funding rule selects zero expert exposure in every prediction year.
The resulting 2023 +2.63% comes entirely from the learned atomic BEST_FULL
keep/skip head. The expert sleeves have a spectacular outcome-exposed 2023
sweet spot, but earlier expanding OOF years reject funding it, and shuffled
controls show that expert identity placement has not been learned. This is a
relative architecture signal, not a promotable dynamic expert Edge."""
        ),
    ]
    nbf.write(notebook, target)
    print(target)


if __name__ == "__main__":
    main()
