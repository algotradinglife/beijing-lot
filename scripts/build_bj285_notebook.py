#!/usr/bin/env python3
"""Build and execute the #285 near-miss protection notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "notebooks/Issue-285-Near-Miss-Protection-Atlas.ipynb",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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
            """# Issue #285 — ticket miss distance and protection

The independent unit is a Beijing issue. Tickets, sampled subsets and stream
seeds are nested diagnostics. The notebook asks whether a protection choice
made before the result can locate a ticket's future wrong leg and earn more
than its extra stake. All values are pre-tax; 0.65 is applied once to a winning
complete N-fold. No 2024+ outcome is opened."""
        ),
        _code(
            """from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path.cwd()
RESULTS = ROOT / 'results/issue-285'
distance = pd.read_csv(RESULTS / 'near_miss_distance_summary.csv')
thin = pd.read_csv(RESULTS / 'protection_rule_summary.csv')
broad = pd.read_parquet(RESULTS / 'protection_confirmation_panel.parquet')
dense = pd.read_csv(RESULTS / 'n8-dense/dense_protection_summary.csv')
dense_panel = pd.read_parquet(
    RESULTS / 'n8-dense/protection_confirmation_panel.parquet'
)
dense_year = pd.read_csv(RESULTS / 'n8-dense/dense_protection_by_year.csv')
receipt = json.loads(
    (RESULTS / 'n8-dense/dense_analysis_receipt.json').read_text()
)
assert broad.issue_year.max() <= 2023
assert dense_panel.issue_year.max() <= 2023
{'broad_rows': len(broad), 'dense_rows': len(dense_panel), **receipt}"""
        ),
        _markdown("## How close were the original N9/K64 tickets?"),
        _code("distance"),
        _code(
            """thin[[
    'rule','marginal_protection_roi','ex_largest_marginal_roi',
    'missed_leg_localization_rate','single_flip_rescue_rate',
    'bootstrap_marginal_roi_p025','bootstrap_marginal_roi_p975'
]].sort_values('marginal_protection_roi', ascending=False)"""
        ),
        _markdown(
            """Only 81 of 38,784 base tickets missed by exactly one leg. The
thin adverse-divergence rule looked profitable and localized the missed leg
more often than random, but its interval crossed zero and one issue dominated.
That observation triggered nuisance confirmation; it did not freeze a
candidate."""
        ),
        _markdown("## Broad N/K confirmation"),
        _code(
            """keys = ['issue','issue_year','n','k','proposal_family','rule']
broad_issue = broad.groupby(keys, as_index=False).mean(numeric_only=True)
broad_curve = broad_issue.groupby(
    ['n','k','proposal_family','rule'], as_index=False
).agg(
    lift=('protection_lift_cny','sum'),
    stake=('extra_stake_cny','sum'),
    continuation=('continuation_lift_cny','sum'),
)
broad_curve['marginal_roi'] = broad_curve.lift / broad_curve.stake
broad_curve['excess_vs_continuation'] = (
    broad_curve.lift - broad_curve.continuation
) / broad_curve.stake
broad_curve.loc[
    broad_curve.rule.eq('ADVERSE_SIGNED_DIVERGENCE')
].sort_values('marginal_roi', ascending=False).head(12)"""
        ),
        _markdown(
            """The original N9/K64 cell reversed under three new stream seeds.
N8/K16 and N8/K64 survived the broad pass and were therefore the only cells
expanded to four subsets and five seeds."""
        ),
        _markdown("## Dense N8 confirmation"),
        _code(
            """dense[[
    'n','k','rule','marginal_protection_roi','ex_largest_marginal_roi',
    'protection_excess_roi_vs_continuation',
    'missed_leg_localization_rate','single_flip_rescue_rate','positive_years',
    'bootstrap_marginal_roi_p025','bootstrap_marginal_roi_p975',
    'bootstrap_adverse_minus_random_p025',
    'bootstrap_adverse_minus_random_p975'
]]"""
        ),
        _code(
            """issue = dense_panel.groupby(
    ['issue','issue_year','k','rule'], as_index=False
).mean(numeric_only=True)
fig, ax = plt.subplots(figsize=(12,5))
for (k, rule), group in issue.groupby(['k','rule'], sort=True):
    group = group.sort_values('issue')
    capital = 100_000 + group.protection_lift_cny.cumsum()
    ax.plot(
        range(1, len(group)+1), capital,
        label=f'K{k} / {rule.replace("_BUDGET_CONTROL", "").replace("_SIGNED_DIVERGENCE", "")}'
    )
ax.axhline(100_000, color='black', linewidth=0.8)
ax.set(
    title='Incremental protection sleeve capital, issue by issue',
    xlabel='Chronological issue index', ylabel='Capital from CNY100,000'
)
ax.legend(); plt.tight_layout()"""
        ),
        _code(
            """dense_year.loc[
    dense_year.rule.eq('ADVERSE_SIGNED_DIVERGENCE'),
    ['k','issue_year','marginal_protection_roi','excess_roi_vs_continuation']
].pivot(index='issue_year', columns='k')"""
        ),
        _markdown(
            """## Decision

Blanket protection does not advance: dense N8/K16 is −13.21% on incremental
capital and N8/K64 is −4.87%; both ex-largest results remain negative and both
issue-bootstrap intervals cross zero. Yet adverse-divergence localization is
about 20% versus 11% for random, and the correct single flip is about 12–13%
versus 6–7%. The information signal survives while the fixed-cost policy does
not.

The justified successor is a selective-protection learner. Its target must be
the counterfactual incremental P&L of protecting a ticket, not a conditional
near-miss classification alone. It may abstain on most tickets and must fall
back to the unprotected base portfolio."""
        ),
    ]
    client = NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, args.output)
    return 0


def _markdown(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_markdown_cell(source)


def _code(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(source)


if __name__ == "__main__":
    raise SystemExit(main())
