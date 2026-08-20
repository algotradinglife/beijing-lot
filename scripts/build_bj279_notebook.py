#!/usr/bin/env python3
"""Build #279 executed profiling notebook."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT = Path("notebooks/research/issue-279/bj279_action_features.ipynb")


def cell(kind: str, source: str) -> dict[str, object]:
    result = {"cell_type": kind, "metadata": {}, "source": source.splitlines(True)}
    if kind == "code":
        result.update({"execution_count": None, "outputs": []})
    result["id"] = hashlib.sha1(source.encode()).hexdigest()[:12]
    return result


cells = [
    cell("markdown", """# Issue #279 — action-aware features and 2023 attribution

Exploratory development analysis only. The independent unit is one Beijing issue; action rows and seeds are nested. All 2024+ outcomes remain sealed."""),
    cell("code", """from pathlib import Path
import json
import matplotlib.pyplot as plt
import pandas as pd
ROOT=Path.cwd(); R=ROOT/'results/issue-279'; F=ROOT/'docs/research/figures'; F.mkdir(parents=True,exist_ok=True)
d=json.loads((R/'decision.json').read_text()); features=pd.read_parquet(R/'action_features.parquet')
dictionary=pd.read_csv(R/'feature_dictionary.csv'); profile=pd.read_csv(R/'conditional_oracle_profile.csv')
ledger=pd.read_csv(R/'issue_2023_attribution.csv',dtype={'issue':str})
print(json.dumps(d,indent=2)); display(dictionary)"""),
    cell("markdown", """## Conditional—not annual—parameter profile

Oracle rows are outcome-aware diagnostics. They describe where the historical return surface lies, not an executable policy."""),
    cell("code", """pivot=profile.pivot(index='breadth_bin',columns='divergence_bin',values='oracle_n_median')
display(profile); fig,ax=plt.subplots(figsize=(10,5)); im=ax.imshow(pivot,aspect='auto',cmap='viridis')
ax.set_xticks(range(len(pivot.columns)),pivot.columns,rotation=35,ha='right'); ax.set_yticks(range(len(pivot.index)),pivot.index)
ax.set_xlabel('Mean absolute divergence quartile'); ax.set_ylabel('Issue breadth quartile'); ax.set_title('Outcome-aware median oracle N | issue Data')
fig.colorbar(im,ax=ax,label='Median oracle N'); plt.tight_layout(); plt.savefig(F/'bj279_conditional_oracle_n.png',dpi=160); plt.show()"""),
    cell("markdown", """## 2023 per-issue replay and regret

Decisions are frozen pre-outcome in #209. Realized results and oracle actions are joined only for development diagnosis."""),
    cell("code", """display(ledger[['issue','action_key','mean_pnl','fixed_pnl','lift_pnl_vs_fixed','oracle_regret_pnl','failure_stage']].head(20))
fig,ax=plt.subplots(figsize=(11,5)); ax.plot(ledger.dynamic_capital,label='dynamic'); ax.plot(ledger.fixed_capital,label='fixed N7/K8')
ax.axhline(100000,color='black',ls='--',lw=.8); ax.set_xlabel('2023 issue sequence'); ax.set_ylabel('Pre-tax capital CNY'); ax.legend(); ax.set_title('2023 development replay')
plt.tight_layout(); plt.savefig(F/'bj279_2023_capital_attribution.png',dpi=160); plt.show()"""),
    cell("code", """stages=ledger.failure_stage.value_counts(); display(stages.rename('issues').to_frame())
ax=stages.sort_values().plot.barh(figsize=(9,4),color='#6b8e23'); ax.set_title('2023 realized failure attribution versus fixed control'); ax.set_xlabel('Issues')
plt.tight_layout(); plt.savefig(F/'bj279_2023_failure_stages.png',dpi=160); plt.show()
print('Selection attribution:',ledger.selection_attribution.unique().tolist()); print('Outcome attribution:',ledger.outcome_attribution.unique().tolist())"""),
    cell("markdown", """## Interpretation

The first feature slice is action-aware and leakage-safe, but the inherited aggregate ticket trace cannot identify match-selection versus outcome-direction effects. The subsequent implementation must materialize ticket/leg decisions before claiming four-stage attribution. 2023 remains development evidence and grants no promotion authority."""),
]
nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3 (beijing-lot)","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"}},"nbformat":4,"nbformat_minor":5}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1))
print("wrote", OUT)
