#!/usr/bin/env python3
"""Build and execute the #284 parameter-reliability research notebook."""

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
        default=ROOT / "notebooks/Issue-284-Parameter-Reliability-Pilot.ipynb",
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
            """# Issue #284 — parameter reliability pilot

This notebook tests whether pre-event issue Data can reliably estimate the
N-fold and subset parameters. The independent historical unit is one Beijing
issue; subset rows and model seeds are nested observations. All figures use
pre-tax CNY100-normalized return, and no 2024+ outcome is opened."""
        ),
        _code(
            """from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path.cwd()
RESULTS = ROOT / 'results/issue-284'
labels = pd.read_parquet(RESULTS / 'full_subset_labels.parquet')
issue_n = pd.read_parquet(RESULTS / 'issue_n_distribution_table.parquet')
oof = pd.read_parquet(RESULTS / 'issue_n_residual_oof_selected.parquet')
metrics = pd.read_csv(RESULTS / 'issue_n_residual_oof_metrics.csv')
reliability = json.loads((RESULTS / 'parameter_reliability_receipt.json').read_text())
assert labels.issue_year.max() <= 2023
{
    'issues': labels.issue.nunique(),
    'subset_rows': len(labels),
    'N': sorted(labels.n.unique().tolist()),
    'years': [int(labels.issue_year.min()), int(labels.issue_year.max())],
    'maximum_issue_weight_error': float((labels.groupby('issue').issue_training_weight.sum()-1).abs().max()),
}"""
        ),
        _markdown(
            """## Reliability has three distinct meanings

1. **Value-surface reliability:** model scores have similar ranks across seeds.
2. **Parameter reliability:** seeds select the same N/family/subset with a clear
   top-vs-runner margin.
3. **Capital reliability:** OOF lift has the same sign across years/seeds and is
   not explained by one jackpot.

A stable score surface is not enough if the argmax is unstable or the realized
capital path is concentrated."""
        ),
        _code(
            """pd.DataFrame({
    'measure': ['score Spearman', 'N agreement', 'family agreement', 'subset agreement', 'all-seed N consensus issues'],
    'value': [
        reliability['mean_pairwise_policy_score_spearman'],
        reliability['mean_pairwise_n_agreement'],
        reliability['mean_pairwise_family_agreement'],
        reliability['mean_pairwise_subset_agreement'],
        reliability['all_seed_n_consensus_issues'],
    ],
})"""
        ),
        _markdown(
            """The score surface is reproducible, while its discrete argmax is
not. This is expected when candidate values are close relative to estimation
noise."""
        ),
        _code(
            """fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
img1 = plt.imread(RESULTS / 'parameter_reliability_n.png')
img2 = plt.imread(RESULTS / 'parameter_reliability_margin_vs_seed_sd.png')
axes[0].imshow(img1); axes[0].axis('off')
axes[1].imshow(img2); axes[1].axis('off')
plt.tight_layout()"""
        ),
        _markdown("## Multi-subset aggregation and the N curve"),
        _code(
            """summary=[]
for n, group in issue_n.groupby('n'):
    group=group.sort_values(['issue_year','issue'])
    pnl=group.realized_mean.to_numpy(float)
    capital=100_000+np.cumsum(pnl)
    peak=np.maximum.accumulate(np.r_[100_000,capital])[:-1]
    years=group.groupby('issue_year').realized_mean.mean()
    summary.append({
        'N': int(n), 'mean_roi_pct': pnl.mean(), 'median_issue_roi': np.median(pnl),
        'positive_issue_fraction': (pnl>0).mean(), 'positive_years': int((years>0).sum()),
        'max_drawdown': float(((peak-capital)/peak).max()),
    })
n_curve=pd.DataFrame(summary)
n_curve"""
        ),
        _code(
            """fig, ax1=plt.subplots(figsize=(9,5))
ax1.plot(n_curve.N,n_curve.mean_roi_pct,marker='o',label='mean ROI')
ax1.plot(n_curve.N,n_curve.median_issue_roi,marker='s',label='median issue ROI')
ax1.axhline(0,color='black',linewidth=1)
ax1.set(xlabel='N',ylabel='Pre-tax return (%)',title='Aggregate N curve: mean improves before holding experience does')
ax1.legend(); plt.tight_layout()"""
        ),
        _markdown(
            """N9 has the best aggregate mean, but its median issue loses the
full risk budget. High N therefore behaves like a sparse-jackpot sleeve, not a
uniformly better action."""
        ),
        _markdown("## Expanding-window residual learning, 2018–2023"),
        _code("metrics.sort_values('mean_roi_pct', ascending=False)"),
        _code(
            """fig, ax=plt.subplots(figsize=(11,5))
for policy, group in oof.groupby('policy'):
    group=group.sort_values(['issue_year','issue'])
    capital=100_000+group.realized_mean.cumsum()
    ax.plot(range(1,len(group)+1),capital,label=policy)
ax.axhline(100_000,color='black',linewidth=1)
ax.set(xlabel='OOF issue order',ylabel='Capital (CNY)',title='Issue-level OOF capital paths, CNY100 risk per issue')
ax.legend(ncol=3); plt.tight_layout()"""
        ),
        _markdown(
            """## Decision

Direct expected-value enumeration is the only positive-mean OOF path, but one
2019 N10 jackpot dominates it; ex-largest lift is negative and only two of six
years beat N7. Ridge and histogram gradient boosting cannot predict the
realized residual and degrade the capital path.

**Verdict:** the expected N frontier is computable, but issue-specific realized
parameter selection is not yet reliable. Keep explicit N enumeration and an
uncertainty/abstention boundary. The follow-up joint screen therefore expands a
bounded `N × K × generator × subset` action space with nuisance replication;
it does not treat a one-off realized winner as the training target."""
        ),
    ]
    client = NotebookClient(notebook, timeout=300, kernel_name="python3")
    executed = client.execute(cwd=str(ROOT))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(executed, args.output)
    print(args.output)
    return 0


def _markdown(source: str):
    return nbformat.v4.new_markdown_cell(source)


def _code(source: str):
    return nbformat.v4.new_code_cell(source)


if __name__ == "__main__":
    raise SystemExit(main())
