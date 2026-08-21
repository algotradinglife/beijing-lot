#!/usr/bin/env python3
"""Build and execute the Issue #291 decision notebook."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
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
            """# Issue #291 — decomposed rare-event value heads

This notebook evaluates complete-ticket hit probability, conditional winning
gross and direct-P&L ranking. Beijing issue is the independent unit. OOF covers
2019–2023 and 2024+ remains sealed."""
        ),
        _code(
            """from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path.cwd()
ART = ROOT / 'docs/research/artifacts/issue-291'
summary = pd.read_csv(ART / 'model_summary.csv')
ranking = pd.read_csv(ART / 'ranking_summary.csv')
annual = pd.read_csv(ART / 'ranking_annual.csv')
paths = pd.read_csv(ART / 'ranking_issue_paths.csv')
actions = pd.read_csv(ART / 'candidate_action_distribution.csv')
receipt = json.loads((ART / 'analysis_receipt.json').read_text())
assert receipt['sealed_years_opened'] == []
receipt"""
        ),
        _markdown("## Probability and payoff heads"),
        _code(
            """summary[['domain','model','event_rate','average_precision',
         'average_precision_lift','conditional_gross_mae_cny']]"""
        ),
        _markdown(
            """Probability ranking contains modest Data signal, especially in the
linear model. Conditional-gross error remains large, so the decomposed expected
value head is not automatically the best economic ranker."""
        ),
        _markdown("## Same-budget base-ticket comparison"),
        _code(
            """ranking.loc[
    ranking.domain.eq('BASE') & ranking.ticket_budget_per_issue.eq(64),
    ['model','score','hits','pnl_cny','global_ex_largest_issue_pnl_cny',
     'bootstrap_roi_p025','bootstrap_roi_p975','positive_years',
     'max_drawdown_pct','longest_losing_issue_streak']
].sort_values('pnl_cny', ascending=False)"""
        ),
        _markdown("## Candidate yearly and issue-level capital path"),
        _code(
            """annual.loc[
    annual.domain.eq('BASE') & annual.model.eq('DATA_LOGIT_RIDGE') &
    annual.score.eq('DIRECT_PNL') & annual.ticket_budget_per_issue.eq(64)
][['oof_year','tickets','hits','gross_cny','pnl_cny']]"""
        ),
        _code(
            """candidate = paths.loc[
    paths.domain.eq('BASE') & paths.model.eq('DATA_LOGIT_RIDGE') &
    paths.score.eq('DIRECT_PNL') & paths.ticket_budget_per_issue.eq(64)
].sort_values(['oof_year','issue_numeric'])
ax = candidate.plot(x='issue', y='capital_cny', figsize=(12,4), legend=False)
ax.axhline(100_000, color='black', linewidth=.8)
ax.set(title='Candidate issue-level capital path', ylabel='CNY', xlabel='Issue')
plt.tight_layout()"""
        ),
        _markdown("## Learned parameter distribution"),
        _code(
            """actions.groupby(['n','k'], as_index=False).agg(
    tickets=('tickets','sum'), hits=('hits','sum'), pnl_cny=('pnl_cny','sum')
)"""
        ),
        _markdown("## Protection falsifier"),
        _code(
            """ranking.loc[
    ranking.domain.eq('PROTECTION') & ranking.ticket_budget_per_issue.eq(64),
    ['model','score','hits','pnl_cny','global_ex_largest_issue_pnl_cny',
     'bootstrap_roi_p025','positive_years']
].sort_values('pnl_cny', ascending=False)"""
        ),
        _markdown(
            """## Decision

Protection remains NO_PROMOTION. The base DATA_LOGIT_RIDGE direct-P&L Top-64
path is retained as a candidate signal because it is positive ex-largest and in
four OOF years, including 2023. Its bootstrap lower bound remains slightly
negative and its longest losing streak is 112 issues, so #292 must confirm the
signal with nuisance replicas and explicit cash/baseline competition before any
held-out or funding decision."""
        ),
    ]
    NotebookClient(
        notebook,
        timeout=600,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    ).execute()
    destination = ROOT / "notebooks/Issue-291-Rare-Event-Value-Heads.ipynb"
    destination.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(notebook, destination)
    return 0


def _markdown(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_markdown_cell(source)


def _code(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(source)


if __name__ == "__main__":
    raise SystemExit(main())
