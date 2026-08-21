#!/usr/bin/env python3
"""Build and execute the #284 joint-parameter screening notebook."""

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
        default=ROOT / "notebooks/Issue-284-Joint-Parameter-Screen.ipynb",
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
            """# Issue #284 — joint parameter interaction screen

This notebook screens `N × K × generator × subset family` while keeping one
Beijing issue as the independent historical unit. Weighted-ticket stream seeds
and sampled subsets are nuisance replicas: they are averaged and are never
eligible optimization parameters. All results are pre-tax and no 2024+ outcome
is opened."""
        ),
        _code(
            """from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path.cwd()
RESULTS = ROOT / 'results/issue-284'
raw = pd.read_parquet(RESULTS / 'joint_action_grid_confirmatory.parquet')
curve = pd.read_csv(RESULTS / 'joint_action_curve.csv')
yearly = pd.read_csv(RESULTS / 'joint_action_yearly.csv')
family = pd.read_csv(RESULTS / 'joint_family_curve.csv')
lift = pd.read_csv(RESULTS / 'joint_generator_lift.csv')
policy_metrics = pd.read_csv(RESULTS / 'joint_policy_oof_metrics.csv')
policy_selected = pd.read_parquet(RESULTS / 'joint_policy_oof_selected.parquet')
policy_diagnostics = pd.read_csv(RESULTS / 'joint_policy_oof_diagnostics.csv')
policy_actions = pd.read_csv(RESULTS / 'joint_policy_oof_action_counts.csv')
outcome_actions = pd.read_csv(RESULTS / 'outcome_surface_action_summary.csv')
outcome_annual = pd.read_csv(RESULTS / 'outcome_surface_annual.csv')
outcome_focus = pd.read_csv(RESULTS / 'outcome_surface_n7_top_k8.csv')
outcome_receipt = json.loads((RESULTS / 'outcome_surface_reuse_receipt.json').read_text())
outcome_joint = pd.read_csv(RESULTS / 'outcome_joint_issue_actions.csv')
div_n8 = pd.read_csv(RESULTS / 'divergence_n8_shape_k16_action_summary.csv')
div_n9 = pd.read_csv(RESULTS / 'divergence_n9_div_k64_action_summary.csv')
mode_metrics = pd.read_csv(RESULTS / 'divergence_mode_oof_metrics.csv')
mode_selected = pd.read_csv(RESULTS / 'divergence_mode_oof_selected.csv')
receipt = json.loads((RESULTS / 'joint_action_analysis_receipt.json').read_text())
assert raw.issue_year.max() <= 2023
{
    'issues': raw.issue.nunique(),
    'rows': len(raw),
    'subsets': raw.subset_id.nunique(),
    'N': sorted(raw.n.unique().tolist()),
    'weighted_stream_replicas': receipt['weighted_stream_replicas'],
    'sealed_years_opened': receipt['sealed_years_opened'],
}"""
        ),
        _markdown(
            """## Why the hierarchy matters

The optimization vector is `(N, K, generator, subset/selector, later R and W)`.
The stream seed is only Monte Carlo integration, and multiple subsets are
nested observations inside an issue. Selecting the luckiest seed or subset
would leak realized lottery variance into the policy."""
        ),
        _code(
            """curve.sort_values(
    ['ex_largest_roi_pct', 'mean_roi_pct'], ascending=False
).head(20)[[
    'n','generator','requested_k','mean_roi_pct','ex_largest_roi_pct',
    'bootstrap_low_pct','bootstrap_high_pct','positive_years',
    'median_issue_roi_pct','longest_losing_issue_streak'
]]"""
        ),
        _code(
            """fig, axes = plt.subplots(1, 2, figsize=(15, 5))
axes[0].imshow(plt.imread(RESULTS / 'joint_action_roi_heatmaps.png'))
axes[0].axis('off')
axes[1].imshow(plt.imread(RESULTS / 'joint_expected_vs_realized.png'))
axes[1].axis('off')
plt.tight_layout()"""
        ),
        _markdown("## Is generator choice stable after matching N and K?"),
        _code(
            """lift.sort_values('mean_lift_pct', ascending=False).head(24)"""
        ),
        _markdown("## Does the apparent action persist across years?"),
        _code(
            """candidate = curve.sort_values('ex_largest_roi_pct', ascending=False).head(8)
keys = candidate[['n','generator','requested_k']]
candidate_years = yearly.merge(keys, on=['n','generator','requested_k'])
candidate_years.pivot_table(
    index=['n','generator','requested_k'],
    columns='issue_year', values='realized_roi_pct'
).round(2)"""
        ),
        _markdown("## Expanding-window Data-conditioned joint policy"),
        _code(
            """policy_metrics[[
    'policy','mean_roi_pct','mean_matched_lift_pct',
    'bootstrap_lift_low_pct','bootstrap_lift_high_pct',
    'positive_lift_years','ending_capital_cny','max_drawdown_fraction',
    'longest_losing_issue_streak','fallback_fraction','selected_action_entropy'
]]"""
        ),
        _code(
            """fig, ax = plt.subplots(figsize=(12, 5.5))
show = [
    'FIXED_BASELINE','FIXED_N7_TOP_K8','FIXED_N7_TOP_K512',
    'HIST_ACTION_FORCED','HIST_FULL_FORCED','MLP_FORCED'
]
for policy in show:
    group = policy_selected.loc[policy_selected.policy.eq(policy)].sort_values(['issue_year','issue'])
    capital = 100_000 + group.realized_roi_pct.cumsum()
    ax.plot(range(1, len(group)+1), capital, label=policy)
ax.axhline(100_000, color='black', linewidth=1)
ax.set(xlabel='OOF issue order', ylabel='Capital (CNY)', title='Joint-policy OOF capital paths, CNY100 per issue')
ax.legend(ncol=2); plt.tight_layout()"""
        ),
        _code(
            """policy_actions.loc[
    policy_actions.policy.isin(['HIST_ACTION_FORCED','HIST_FULL_FORCED','MLP_FORCED'])
].groupby('policy').head(10)"""
        ),
        _code("policy_diagnostics"),
        _markdown(
            """MLP still collapses onto the static
`N7/TOP_VALUE/K512/ENSEMBLE` action, differing in only 5/328 issues and adding
about +0.086pp with no separated confidence interval. Full-HGB is more
interesting: it chooses K256 in 33 issues and K512 in 295, adding +1.80pp over
fixed K512 (+0.80pp ex-largest), but its paired bootstrap interval still
crosses zero. This is a conditional-K sweet-zone clue rather than a reliable
learned policy. `EXPECTED_ONLY` is strongly harmful, while the q10 safety head
falls back in every issue."""
        ),
        _markdown("## Does one outcome-value surface win across regimes?"),
        _code(
            """outcome_focus[[
    'outcome_weight_mode','development_roi_pct','holdout_roi_pct',
    'mean_roi_pct','ex_largest_roi_pct','bootstrap_low_pct',
    'bootstrap_high_pct','positive_years'
]]"""
        ),
        _code(
            """fig, axes = plt.subplots(1, 2, figsize=(16, 5.5))
axes[0].imshow(plt.imread(RESULTS / 'outcome_surface_n7_top_k8_yearly.png'))
axes[0].axis('off')
axes[1].imshow(plt.imread(RESULTS / 'outcome_surface_dev_holdout_transfer.png'))
axes[1].axis('off')
plt.tight_layout()
outcome_receipt"""
        ),
        _markdown(
            """The outcome-value dimension is real but nonstationary. The
development winner `MARKET_PROBABILITY / N7 / TOP / K8` moves from +38.54% in
2014–2022 to −33.06% in 2023. `DIVERGENCE_VALUE` moves in the opposite direction
but its positive 2023 result is concentrated in one positive issue. Across all
432 fixed actions, development-to-2023 rank Spearman is only 0.305. Therefore
value mode belongs in the learned action vector, but a fixed historical winner
is not an acceptable baseline replacement."""
        ),
        _markdown("## Subset-level alias and nuisance confirmation"),
        _code(
            """mode_pivot = outcome_joint.pivot_table(
    index=['issue','n','proposal_family','generator','requested_k'],
    columns='outcome_weight_mode', values='realized_roi_pct'
).dropna()
{
    'CELL_equals_MARKET_fraction': (
        mode_pivot.CELL_VALUE == mode_pivot.MARKET_PROBABILITY
    ).mean(),
    'maximum_absolute_difference': (
        mode_pivot.CELL_VALUE - mode_pivot.MARKET_PROBABILITY
    ).abs().max(),
}"""
        ),
        _code(
            """pd.concat([
    div_n8.assign(confirmation='N8_SHAPE_K16_8SUBSET_5SEED'),
    div_n9.assign(confirmation='N9_DIV_K64_8SUBSET_5SEED'),
], ignore_index=True)[[
    'confirmation','outcome_weight_mode','mean_roi_pct',
    'ex_largest_roi_pct','mean_lift_to_cell_pct',
    'development_roi_pct','holdout_roi_pct','positive_years'
]]"""
        ),
        _markdown(
            """CELL and MARKET are an algebraic alias after fixing the match
subset: predicted SP is a match-level scalar common to all three outcomes, so
it cannot change complete-ticket ordering. DIVERGENCE genuinely changes the
order, but the N8 apparent Edge collapses under 8-subset × 5-seed integration.
N9/K64 retains +5.27% descriptively, yet becomes −13.41% ex-largest and is
negative in 2023. Neither row is a frozen candidate."""
        ),
        _markdown("## Can issue Data learn the divergence-mode switch?"),
        _code(
            """mode_metrics[[
    'policy','mean_roi_pct','mean_lift_to_cell_pct','ex_largest_roi_pct',
    'bootstrap_lift_low_pct','bootstrap_lift_high_pct',
    'positive_lift_years','divergence_fraction','ending_capital_cny',
    'max_drawdown_fraction'
]]"""
        ),
        _code(
            """fig, ax = plt.subplots(figsize=(12, 5.5))
for policy in ['CELL_FIXED','DIVERGENCE_FIXED','RIDGE','HGB','MLP']:
    group = mode_selected.loc[mode_selected.policy.eq(policy)].sort_values(
        ['issue_year','issue']
    )
    capital = 100_000 + group.realized_roi_pct.cumsum()
    ax.plot(range(1, len(group)+1), capital, label=policy)
ax.axhline(100_000, color='black', linewidth=1)
ax.set(
    xlabel='OOF issue order', ylabel='Capital (CNY)',
    title='Outcome-mode OOF capital paths, CNY100 per issue'
)
ax.legend(); plt.tight_layout()"""
        ),
        _markdown(
            """Fixed divergence is nearly flat in 2018–2023, but it is a
post-selected development hypothesis. Every Data-conditioned switcher performs
worse. The current 18 aggregate issue features do not explain *when* divergence
ranking works. The next iteration must construct M×3 divergence-shape features
before restoring outcome mode to the complete joint policy."""
        ),
        _markdown(
            """## Decision rule

This is an exploratory interaction screen, not a promotion gate. A positive
historical cell is only a hypothesis. It must survive nuisance-seed averaging,
denser subset replication, chronological model selection, ex-largest and
issue-block bootstrap checks. The next learned policy must use richer pre-event
matrix features and abstain to the frozen baseline when the lower advantage
bound is not separated from uncertainty. Current aggregate issue-state features
do not support dynamic parameter selection."""
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
