#!/usr/bin/env python3
"""Build the decision notebook for Issue #282."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT = Path("notebooks/research/issue-282/bj282_conditional_policy.ipynb")


def cell(kind: str, source: str) -> dict[str, object]:
    result: dict[str, object] = {
        "cell_type": kind,
        "metadata": {},
        "source": source.splitlines(True),
        "id": hashlib.sha1(source.encode()).hexdigest()[:12],
    }
    if kind == "code":
        result.update({"execution_count": None, "outputs": []})
    return result


cells = [
    cell(
        "markdown",
        """# Issue #282 — conditional M×3 action-value policy

Executed prototype analysis. The independent unit is one Beijing issue. Action rows and 16 ticket streams are nested observations. The primary replay is frozen at 2022 year-end and applied to 2023; all 2024+ outcomes remain sealed.""",
    ),
    cell(
        "code",
        """from pathlib import Path
import json
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
ROOT=Path.cwd()
while not (ROOT/'results/issue-282').exists() and ROOT != ROOT.parent: ROOT=ROOT.parent
R=ROOT/'results/issue-282'; F=ROOT/'docs/research/figures'; F.mkdir(parents=True,exist_ok=True)
decision=json.loads((R/'decision.json').read_text())
metrics=pd.read_csv(R/'policy_metrics_2023.csv')
baseline_selection=pd.read_csv(R/'development_fixed_baseline_selection.csv')
parameters=pd.read_csv(R/'parameter_performance_2023.csv')
yearly=pd.read_csv(R/'parameter_performance_by_year.csv')
predictions=pd.read_parquet(R/'predictions_2023.parquet')
ledger=pd.read_parquet(R/'deep_ensemble_ledger_2023.parquet')
print(json.dumps(decision,indent=2)); display(baseline_selection); display(metrics)""",
    ),
    cell(
        "markdown",
        """## Frozen baseline ladder

The fallback control is selected using only 2014–2022 total P&L. The table below is development evidence; no 2023 row participates in baseline selection.""",
    ),
    cell(
        "code",
        """display(baseline_selection.sort_values('development_pnl_cny',ascending=False))
fixed=yearly[(yearly.selector=='ALL')&(yearly.n==7)&(yearly.k==8)&(yearly.generator=='TOP_VALUE')]
fig,ax=plt.subplots(figsize=(11,5))
for mode,g in fixed.groupby('outcome_weight_mode'):
    ax.plot(g.issue_year,g.return_per_cny,marker='o',label=mode)
ax.axhline(0,color='black',lw=.8); ax.set_xlabel('Development year'); ax.set_ylabel('Pre-tax return per CNY')
ax.set_title('Fixed N7/K8 TOP_VALUE: yearly instability by outcome surface'); ax.legend()
plt.tight_layout(); plt.savefig(F/'bj282_fixed_baseline_years.png',dpi=170); plt.show()""",
    ),
    cell(
        "markdown",
        """## Frozen-2022 2023 capital paths

Capital starts at CNY100,000. The learned policies use a prediction-only guard: deviate only if the candidate lower-confidence score beats both the frozen control and cash.""",
    ),
    cell(
        "code",
        """fig,ax=plt.subplots(figsize=(12,5))
for policy in ['deep_ensemble','hgb','linear',decision['strongest_matched_fixed_baseline'].lower()]:
    path=R/f'capital_path_{policy}.csv'
    if path.exists():
        d=pd.read_csv(path,dtype={'issue':str}); ax.plot(d.capital_cny,label=policy)
ax.axhline(100000,color='black',ls='--',lw=.8); ax.set_xlabel('2023 issue sequence'); ax.set_ylabel('Pre-tax capital (CNY)')
ax.set_title('Frozen-2022 2023 issue-level capital paths'); ax.legend()
plt.tight_layout(); plt.savefig(F/'bj282_2023_capital_paths.png',dpi=170); plt.show()""",
    ),
    cell(
        "markdown",
        """## Parameter-performance surface

These are fixed-policy 2023 slices, not independently validated discoveries. They reveal where selector, outcome direction, N, generator and K interact before the learned policy chooses among them.""",
    ),
    cell(
        "code",
        """n_curve=(parameters.groupby(['outcome_weight_mode','n'],as_index=False)
         .agg(turnover=('turnover_cny','sum'),pnl=('pnl_cny','sum')))
n_curve['return_per_cny']=n_curve.pnl/n_curve.turnover
display(n_curve)
fig,ax=plt.subplots(figsize=(10,5))
for mode,g in n_curve.groupby('outcome_weight_mode'):
    ax.plot(g.n,g.return_per_cny,marker='o',label=mode)
ax.axhline(0,color='black',lw=.8); ax.set_xlabel('N'); ax.set_ylabel('Pre-tax return per CNY')
ax.set_title('2023 pooled N curve by outcome proposal surface'); ax.legend()
plt.tight_layout(); plt.savefig(F/'bj282_2023_n_surface.png',dpi=170); plt.show()
display(parameters.sort_values('return_per_cny',ascending=False).head(25))""",
    ),
    cell(
        "markdown",
        """## Learned action path and issue attribution

Oracle regret is joined only after each frozen action and is diagnostic. It is never a feature, class label or fallback rule.""",
    ),
    cell(
        "code",
        """display(ledger[['issue','action_key','guard_reason','predicted_score','pnl_cny_mean','matched_lift_cny','oracle_regret_cny_diagnostic','matched_failure_attribution']].head(25))
fig,axes=plt.subplots(1,3,figsize=(14,4))
ledger.n.value_counts().sort_index().plot.bar(ax=axes[0],title='Selected N')
ledger.k.value_counts().sort_index().plot.bar(ax=axes[1],title='Selected K')
ledger.generator.value_counts().plot.bar(ax=axes[2],title='Selected generator')
plt.tight_layout(); plt.savefig(F/'bj282_2023_selected_parameters.png',dpi=170); plt.show()
display(ledger.matched_failure_attribution.value_counts().rename('issues').to_frame())""",
    ),
    cell(
        "markdown",
        """## Distribution calibration

Because action rows within an issue are correlated, these plots diagnose model behavior but do not turn action rows into independent statistical evidence.""",
    ),
    cell(
        "code",
        """predictions['actual_positive']=predictions.normalized_pnl_cny100.gt(0)
predictions['probability_bin']=pd.qcut(predictions.deep_positive_probability_median,10,duplicates='drop')
cal=(predictions.groupby('probability_bin',observed=True)
     .agg(predicted=('deep_positive_probability_median','mean'),observed=('actual_positive','mean'),rows=('actual_positive','size')).reset_index())
display(cal)
fig,axes=plt.subplots(1,2,figsize=(12,5))
axes[0].plot(cal.predicted,cal.observed,marker='o'); axes[0].plot([0,1],[0,1],ls='--',color='black'); axes[0].set(xlabel='Predicted positive probability',ylabel='Observed positive fraction',title='Nested-row calibration')
lo,hi=predictions.normalized_pnl_cny100.quantile([.01,.99]); axes[1].scatter(predictions.deep_expected_value_median,predictions.normalized_pnl_cny100.clip(lo,hi),s=8,alpha=.25)
axes[1].axhline(0,color='black',lw=.7); axes[1].set(xlabel='Predicted normalized P&L',ylabel='Realized normalized P&L (1–99% clipped)',title='Predicted vs realized action value')
plt.tight_layout(); plt.savefig(F/'bj282_2023_calibration.png',dpi=170); plt.show()""",
    ),
    cell(
        "markdown",
        """## Decision reading

The decision JSON applies the preregistered holdout criteria jointly. A failed criterion is information about the current model and does not justify opening 2024+ outcomes. A positive-looking mean is challenged with ex-largest lift, seed dispersion, drawdown, rolling windows and action-support checks before any handoff.""",
    ),
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3 (beijing-lot)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.14"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print("wrote", OUT)
