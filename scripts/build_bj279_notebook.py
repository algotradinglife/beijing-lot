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
ROOT=Path.cwd()
while not (ROOT/'results/issue-279').exists() and ROOT != ROOT.parent: ROOT=ROOT.parent
R=ROOT/'results/issue-279'; F=ROOT/'docs/research/figures'; F.mkdir(parents=True,exist_ok=True)
d=json.loads((R/'decision.json').read_text()); features=pd.read_parquet(R/'action_features.parquet')
dictionary=pd.read_csv(R/'feature_dictionary.csv'); profile=pd.read_csv(R/'conditional_oracle_profile.csv')
budget=pd.read_parquet(R/'budget_matched_targets.parquet'); budget_profile=pd.read_csv(R/'conditional_budget_profile.csv')
ledger=pd.read_csv(R/'issue_2023_attribution.csv',dtype={'issue':str}); topb=pd.read_csv(R/'issue_2023_topb_actions.csv',dtype={'issue':str})
trace_summary=pd.read_csv(R/'issue_2023_trace_summary.csv',dtype={'issue':str})
print(json.dumps(d,indent=2)); display(dictionary)"""),
    cell("markdown", """## Conditional—not annual—parameter profile

Oracle rows are outcome-aware diagnostics. They describe where the historical return surface lies, not an executable policy. The raw oracle is shown only to demonstrate why its K512 concentration is invalid as a label."""),
    cell("code", """pivot=profile.pivot(index='breadth_bin',columns='divergence_bin',values='oracle_n_median')
display(profile); fig,ax=plt.subplots(figsize=(10,5)); im=ax.imshow(pivot,aspect='auto',cmap='viridis')
ax.set_xticks(range(len(pivot.columns)),pivot.columns,rotation=35,ha='right'); ax.set_yticks(range(len(pivot.index)),pivot.index)
ax.set_xlabel('Mean absolute divergence quartile'); ax.set_ylabel('Issue breadth quartile'); ax.set_title('Outcome-aware median oracle N | issue Data')
fig.colorbar(im,ax=ax,label='Median oracle N'); plt.tight_layout(); plt.savefig(F/'bj279_conditional_oracle_n.png',dpi=160); plt.show()"""),
    cell("markdown", """## Budget-matched action targets and marginal K

Every active action is rescaled to the same CNY16 reference stake before comparison. This removes the mechanical advantage of larger K while preserving the return-per-yuan label. Marginal K observations are noisy because adjacent ticket samples are not nested; they are diagnostics for a later expected-curve model, not a stopping policy by themselves."""),
    cell("code", """n7=(budget[budget.n.eq(7)&budget.generator.ne('NO_BET')]
    .groupby(['generator','k']).agg(mean_budget_pnl=('budget_matched_pnl','mean'),median_budget_pnl=('budget_matched_pnl','median'),positive_fraction=('budget_matched_pnl',lambda x:(x>0).mean())).reset_index())
display(n7)
fig,ax=plt.subplots(figsize=(10,5))
for generator,g in n7.groupby('generator'):
    ax.plot(g.k,g.mean_budget_pnl,marker='o',label=generator)
ax.axhline(0,color='black',lw=.8); ax.set_xscale('log',base=2); ax.set_xticks(sorted(n7.k.unique()),sorted(n7.k.unique()))
ax.set_xlabel('K anchor'); ax.set_ylabel('Mean PnL at matched CNY16 budget'); ax.set_title('Development N7 budget-matched K curves'); ax.legend()
plt.tight_layout(); plt.savefig(F/'bj279_budget_matched_n7_k.png',dpi=160); plt.show()"""),
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
    cell("markdown", """## Pre-outcome structural attribution

The replay now persists all 2023 cell values, Top-B action alternatives, complete ticket identities and every ticket leg before outcomes are joined. Match, outcome and ticket Jaccard scores show where the learned final portfolio structurally diverges from fixed N7/K8 TOP_VALUE. They are not pure Stage-1/Stage-2 attribution because WR/WOR and K at Stage 3 also change coverage, and they do not pretend that nonlinear N-fold PnL can be additively assigned to individual stages."""),
    cell("code", """display(ledger[['issue','action_key','lift_pnl_vs_fixed','match_set_jaccard','leg_identity_jaccard','ticket_identity_jaccard','shared_match_modal_outcome_disagreement']].head(20))
fig,ax=plt.subplots(figsize=(9,5)); ax.scatter(ledger.match_set_jaccard,ledger.lift_pnl_vs_fixed,alpha=.75)
ax.axhline(0,color='black',lw=.8); ax.set_xlabel('Chosen vs fixed match-set Jaccard'); ax.set_ylabel('Realized matched PnL lift (CNY)'); ax.set_title('2023 structural divergence and realized lift')
plt.tight_layout(); plt.savefig(F/'bj279_2023_structure_vs_lift.png',dpi=160); plt.show()
print('Pre-outcome artifacts:', {'Top-B rows':len(topb),'issues':trace_summary.issue.nunique(),'cell rows':d['2023_preoutcome_cell_rows'],'ticket rows':d['2023_preoutcome_ticket_rows'],'leg rows':d['2023_preoutcome_leg_rows']})"""),
    cell("markdown", """## Interpretation

The first feature slice is action-aware and leakage-safe. Budget matching removes the raw-oracle K exposure artifact, but the resulting targets remain extremely skewed: most action/issue outcomes lose the full CNY16 reference budget and a few large hits dominate means. Therefore the next model must learn conditional return distributions and downside probabilities, not regress a single mean or imitate a hindsight argmax.

The new trace makes final-portfolio match and outcome changes observable, while Stage 1/2 versus Stage 3 effects and their separate causal PnL contributions remain non-identifiable because a ticket pays only when all N legs hit. 2023 remains development evidence and grants no promotion authority."""),
]
nb={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3 (beijing-lot)","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"}},"nbformat":4,"nbformat_minor":5}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1))
print("wrote", OUT)
