#!/usr/bin/env python3
"""Build and execute the Issue #286 decision notebook."""

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
        default=ROOT / "notebooks/Issue-286-Joint-Selective-Protection.ipynb",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    notebook = nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3"},
        }
    )
    notebook.cells = [
        _markdown(
            """# Issue #286 — joint base-ticket and selective-protection learning

This notebook is the decision surface for the bounded joint action
`(N, selector, outcome mode, generator, K, protection policy)`. The independent
unit is a Beijing issue. All economics are pre-tax, use actual CNY2 unique-ticket
stake, and apply 0.65 once to a winning complete N-fold. 2024+ remains sealed."""
        ),
        _code(
            """from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path.cwd()
ART = ROOT / 'docs/research/artifacts/issue-286'
RESULTS = ROOT / 'results/issue-286'
summary = pd.read_csv(ART / 'joint_policy_comparison_summary.csv')
annual = pd.read_csv(ART / 'joint_policy_annual.csv')
protection = pd.read_csv(ART / 'joint_policy_protection_attribution.csv')
actions = pd.read_csv(ART / 'joint_policy_action_distribution.csv')
candidate_universe = pd.read_csv(ART / 'candidate_universe_summary.csv')
manifest = json.loads((RESULTS / 'label_free_manifest_receipt.json').read_text())
settlement = json.loads((RESULTS / 'settlement_receipt.json').read_text())
oof = json.loads((RESULTS / 'joint_oof_receipt.json').read_text())
assert manifest['settlement_columns_opened'] == []
assert settlement['sealed_years_opened'] == []
{'manifest': manifest['rows'], 'settlement': settlement['settlement_rows'], 'oof': oof}"""
        ),
        _markdown("## Matched capital comparison"),
        _code(
            """summary.loc[
    summary.model.eq('DATA_HGB'),
    ['policy','turnover_cny','pnl_cny','roi_pct','ending_capital_cny',
     'ex_largest_pnl_cny','bootstrap_roi_p025','bootstrap_roi_p975',
     'max_drawdown_pct','worst_rolling_10_pnl_cny']
]"""
        ),
        _markdown(
            """The positive HGB totals are not evidence of stable Edge. Removing
one largest issue makes both the selected base and learned joint paths negative.
The issue bootstrap crosses zero widely. The formal N7/K8 row is a required
reference selected using 2014–2022, so only its 2023 result is a truly frozen
holdout observation."""
        ),
        _code(
            """annual.loc[
    annual.model.eq('DATA_HGB') & annual.policy.isin([
        'LEARNED_JOINT','SELECTED_BASE_NO_PROTECTION','FORMAL_N7_K8_MARKET_TOP'
    ])
].pivot(index='issue_year', columns='policy', values=['pnl_cny','roi_pct'])"""
        ),
        _markdown("## Did selective protection add value?"),
        _code("candidate_universe"),
        _code("protection"),
        _code(
            """hgb = protection.loc[protection.model.eq('DATA_HGB')]
stake = 2 * hgb.protection_tickets.sum()
pd.Series({
    'protection_tickets': int(hgb.protection_tickets.sum()),
    'protection_stake_cny': stake,
    'predicted_incremental_pnl_cny': hgb.predicted_protection_pnl_cny.sum(),
    'actual_incremental_pnl_cny': hgb.actual_protection_pnl_cny.sum(),
    'incremental_roi_pct': hgb.actual_protection_pnl_cny.sum() / stake * 100,
})"""
        ),
        _markdown(
            """The learned ranker loses less than equal-budget adverse, continuation,
and random controls, but loses CNY7,210.65 relative to choosing no protection.
This preserves a ranking clue while rejecting the funded protection action."""
        ),
        _markdown("## Joint action distribution and sparsity"),
        _code(
            """actions.loc[actions.model.eq('DATA_HGB')].sort_values(
    ['issues','protection_tickets'], ascending=False
).head(20)"""
        ),
        _code(
            """paths = pd.read_csv(ART / 'joint_policy_capital_paths.csv')
focus = paths.loc[
    paths.model.eq('DATA_HGB') & paths.policy.isin([
        'LEARNED_JOINT','SELECTED_BASE_NO_PROTECTION','FORMAL_N7_K8_MARKET_TOP'
    ])
]
fig, ax = plt.subplots(figsize=(12,5))
for policy, group in focus.groupby('policy', sort=True):
    ax.plot(range(1, len(group)+1), group.capital_cny, label=policy)
ax.axhline(100_000, color='black', linewidth=.8)
ax.set(title='Issue-level OOF capital path', xlabel='Chronological issue', ylabel='CNY')
ax.legend(); plt.tight_layout()"""
        ),
        _markdown(
            """## Decision

No learned protection policy is promoted. Data-HGB often selects 100% protection,
which reproduces the blanket behavior the contract sought to avoid. The base
selector's positive total is one-issue dominated. Preserve `NO_PROTECTION`, the
candidate score, and the complete label-free interface; next work should improve
base-action value and tail-risk calibration before reopening protection."""
        ),
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
