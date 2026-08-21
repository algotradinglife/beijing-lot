#!/usr/bin/env python3
"""Build and execute the Issue #292 decision notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
import pandas as pd
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "notebooks/Issue-292-Dynamic-Joint-Optimizer.ipynb",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact = ROOT / "docs/research/artifacts/issue-292/policy_summary.csv"
    summary = pd.read_csv(artifact)
    best_dynamic = (
        summary[
            summary["policy"].str.startswith(("DYNAMIC_", "CORE_", "TAIL_", "BARBELL_"))
            & summary["funded_issues"].gt(0)
        ]
        .sort_values(["ex_largest_pnl_cny", "pnl_cny"], ascending=False)
        .iloc[0]
    )
    decision = (
        f"The strongest learned/barbell row by ex-largest P&L is "
        f"`{best_dynamic.policy}`: total P&L CNY{best_dynamic.pnl_cny:,.2f}, "
        f"ex-largest CNY{best_dynamic.ex_largest_pnl_cny:,.2f}, pre-tax ROI "
        f"{best_dynamic.roi_pct:.2f}%, and bootstrap lower bound "
        f"{best_dynamic.bootstrap_roi_p025:.2f}%. It remains an exploratory "
        "candidate unless it beats cash and named controls without relying on "
        "one jackpot. 2024+ is not opened by this notebook."
    )
    notebook = nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3"},
        }
    )
    notebook.cells = [
        _markdown(
            """# Issue #292 — dynamic joint optimizer and low-N/tail barbell

The independent unit is a Beijing issue. The learned decision uses only
pre-event issue Data and action parameters. Outcomes join after selection.
Development OOF covers 2019–2023; 2024+ stays sealed. Economics use actual
CNY2 tickets and apply 0.65 once to a complete winning N-fold."""
        ),
        _code(
            """from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path.cwd()
ART = ROOT / 'docs/research/artifacts/issue-292'
RESULTS = ROOT / 'results/issue-292'
summary = pd.read_csv(ART / 'policy_summary.csv')
annual = pd.read_csv(ART / 'policy_annual.csv')
paths = pd.read_csv(ART / 'policy_capital_paths.csv')
actions = pd.read_csv(ART / 'dynamic_action_distribution.csv')
fixed_n = pd.read_csv(ART / 'fixed_n_summary.csv')
barbell = pd.read_csv(ART / 'barbell_sensitivity.csv')
sensitivity = pd.read_csv(ART / 'shortlist_seed_summary.csv')
receipt = json.loads((RESULTS / 'receipt.json').read_text())
assert receipt['sealed_years_opened'] == []
{'issues': int(paths.issue.nunique()), 'years': sorted(paths.issue_year.unique()),
 'N': receipt['n_values'], 'K': receipt['k_values']}"""
        ),
        _markdown("## Cash, frozen controls and learned policies"),
        _code(
            """focus = summary[
    summary.policy.isin([
        'CASH_NO_BET','FIXED_N7_K8_TOP_VALUE','CONTINUATION_PREVIOUS_ACTION',
        'DYNAMIC_FULL_ACTIVE','DYNAMIC_FULL_SAFE','ISSUE291_PRIMARY_B64',
        'ISSUE291_CHALLENGER_B64'
    ])
]
focus[['policy','funded_issues','stake_cny','pnl_cny','roi_pct',
       'ex_largest_pnl_cny','bootstrap_roi_p025','bootstrap_roi_p975',
       'max_drawdown_pct','longest_losing_issue_streak']]"""
        ),
        _markdown("## Is a low-N near-flat core available?"),
        _code(
            """summary[summary.policy.str.startswith('CORE_')][[
    'policy','funded_issues','stake_cny','pnl_cny','roi_pct',
    'ex_largest_pnl_cny','positive_years','max_drawdown_pct',
    'longest_losing_issue_streak','bootstrap_roi_p025'
]].sort_values('ex_largest_pnl_cny', ascending=False)"""
        ),
        _code(
            """fixed_n.groupby('n', as_index=False).first()[[
    'n','k','generator','roi_pct','ex_largest_pnl_cny','positive_issue_fraction'
]]"""
        ),
        _markdown("## Did the post-hoc fixed-action clues survive nuisance seeds?"),
        _code(
            """sensitivity.pivot(index='nuisance_seed', columns='action_key', values=[
    'roi_pct','ex_largest_pnl_cny','positive_years'
])"""
        ),
        _markdown("## Does a capped tail sleeve improve the holding path?"),
        _code(
            """barbell[[
    'policy','funded_issues','stake_cny','pnl_cny','roi_pct',
    'ex_largest_pnl_cny','mean_tail_capital_fraction','max_drawdown_pct',
    'longest_losing_issue_streak','bootstrap_roi_p025'
]].head(20)"""
        ),
        _markdown("## What parameters did Data choose?"),
        _code(
            """actions[actions.policy.isin(['DYNAMIC_FULL_SAFE','DYNAMIC_FULL_ACTIVE'])].head(30)"""
        ),
        _markdown("## Issue-level capital paths"),
        _code(
            """selected = summary[
    summary.policy.str.startswith(('DYNAMIC_','CORE_','TAIL_','BARBELL_'))
].nlargest(4, 'ex_largest_pnl_cny').policy.tolist()
selected += ['CASH_NO_BET','FIXED_N7_K8_TOP_VALUE','ISSUE291_PRIMARY_B64']
fig, ax = plt.subplots(figsize=(13, 6))
for policy, group in paths[paths.policy.isin(selected)].groupby('policy', sort=True):
    ax.plot(range(1, len(group)+1), group.capital_cny, label=policy)
ax.axhline(100_000, color='black', linewidth=.8)
ax.set(title='Chronological issue-level capital', xlabel='Issue', ylabel='CNY')
ax.legend(fontsize=7); plt.tight_layout()"""
        ),
        _markdown("## Decision\n\n" + decision),
    ]
    NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, args.output)
    return 0


def _markdown(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_markdown_cell(source)


def _code(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(source)


if __name__ == "__main__":
    raise SystemExit(main())
