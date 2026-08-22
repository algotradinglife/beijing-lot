#!/usr/bin/env python3
"""Build and execute the Issue #306 decision notebook."""

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


def main() -> None:
    target = Path("notebooks/research/issue-306/bj306_dynamic_ticket_composition.ipynb")
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.14"},
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            """# Issue #306 — matched-exposure within-issue ticket composition

Every eligible issue receives exactly 512 CNY2 tickets. The model cannot
improve by skipping an issue or shrinking its committed budget; it must learn
N, K, match/outcome sampling and WR/WOR composition. 2024+ is sealed."""
        ),
        nbf.v4.new_code_cell(
            """from pathlib import Path
import json
import pandas as pd
from IPython.display import Image, display

ROOT = next(path for path in (Path.cwd(), *Path.cwd().parents) if (path / 'src' / 'issue306').is_dir())
OUTPUT = ROOT / 'results/issue-306'
decision = json.loads((OUTPUT / 'decision.json').read_text())
decision"""
        ),
        nbf.v4.new_markdown_cell("## Action-surface coverage and fit receipts"),
        nbf.v4.new_code_cell(
            """coverage = pd.read_csv(OUTPUT / 'action_surface_coverage.csv')
display(coverage.groupby('issue_year').agg(issues=('issue','nunique'),
    min_feasible_actions=('feasible_actions','min'), max_missing_actions=('missing_actions','max')))
receipts = pd.read_csv(OUTPUT / 'fit_receipts.csv')
display(receipts.groupby('condition').agg(fits=('model_seed','size'),
    converged=('converged','all'), max_iterations=('iterations','max'),
    train_issues=('train_issues','max')))"""
        ),
        nbf.v4.new_markdown_cell("## Fixed-coverage capital and tail comparison"),
        nbf.v4.new_code_cell(
            """summary = pd.read_csv(OUTPUT / 'policy_summary.csv')
cols = ['evaluation_year','condition','median_terminal_capital_cny',
        'median_capital_growth_pct','median_turnover_roi_pct',
        'median_max_drawdown_pct','median_ex_largest_pnl_cny',
        'median_positive_issue_rate','median_tail_5x_rate',
        'median_mean_distinct_actions']
display(summary[cols].sort_values(['evaluation_year','median_terminal_capital_cny'], ascending=[True,False]))
display(Image(filename=str(OUTPUT / 'capital_paths_2023.png')))
display(Image(filename=str(OUTPUT / 'tail_risk_frontier_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Learned parameter distribution and null"),
        nbf.v4.new_code_cell(
            """primary = decision['decision']['development_selected_primary']
actions = pd.read_csv(OUTPUT / 'action_distribution.csv')
display(actions[actions.condition.eq(primary)]
        .sort_values('allocated_tickets', ascending=False).head(30))
null = pd.read_csv(OUTPUT / 'same_exposure_permutation_2023.csv')
display(null.groupby('condition').median_terminal_capital_cny
        .describe(percentiles=[.05,.5,.95]))
display(Image(filename=str(OUTPUT / 'learned_action_distribution.png')))"""
        ),
        nbf.v4.new_markdown_cell(
            """## Interpretation

The decision payload and controls determine whether the learned composition
adds within-issue value. Any improvement caused only by cash, fewer issues or
less committed stake is structurally impossible in this experiment. The
outcome-aware oracle remains diagnostic and no 2024+ result is opened."""
        ),
    ]
    NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(Path.cwd())}},
    ).execute()
    nbf.write(notebook, target)
    print(target)


if __name__ == "__main__":
    main()
