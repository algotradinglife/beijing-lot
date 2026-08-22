#!/usr/bin/env python3
"""Build the executed decision notebook for Issue #306."""

from pathlib import Path

import nbformat as nbf


def main() -> None:
    target = Path("notebooks/research/issue-306/bj306_dynamic_moe.ipynb")
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.14"},
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            """# Issue #306 — state-dependent expert composition and dynamic funding intensity

A small causal mixture-of-experts learner maps pre-event issue state to expert
identity scores, relative expert weights, and total expert funding intensity.
Stage A (frozen BEST_FULL keep/skip from #305 contract, local reference until
#305 delivers), Stage B (shared action-conditioned expert value over four
whole-bundle ledgers), Stage C (composition + intensity). Expanding-window
predictions through 2023; 2024+ stays sealed."""
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
        nbf.v4.new_markdown_cell("## Matched controls on identical support"),
        nbf.v4.new_code_cell(
            """summary = pd.read_csv(OUTPUT / 'policy_summary.csv')
focus = ['CASH_NO_BET','B0_BEST_FULL','RESIDUAL_299','STAGE_A_KEEP_SKIP',
         'STATIC_TRAIN_MIXTURE','COMPOSITION_FIXED_INTENSITY','INTENSITY_FIXED_COMPOSITION',
         'GUARDED_DYNAMIC_EXPERT','ISSUE_BLOCK_SHUFFLED','IDENTITY_SHUFFLED','ORACLE_DIAGNOSTIC']
cols = ['evaluation_year','condition','funded_issues','terminal_capital_cny','capital_growth_pct',
        'max_drawdown_pct','longest_losing_issue_streak','worst_rolling_10_pnl_cny','stake_cny']
display(summary[summary.condition.isin(focus)][cols])
display(Image(filename=str(OUTPUT / 'capital_paths_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Stage A (frozen keep/skip) and Stage B receipts"),
        nbf.v4.new_code_cell(
            """ks = pd.read_csv(OUTPUT / 'stage_a_keep_skip_decisions.csv')
print('Stage A source:', ks['stage_a_source'].iloc[0])
print(ks.groupby(['issue_year','keep_baseline']).size().unstack(fill_value=0))
receipts = pd.read_csv(OUTPUT / 'stage_a_local_reference_receipts.csv')
display(receipts[['prediction_year','active_train_issues','active_test_issues',
                  'mean_converged','downside_converged','expert_label_inputs']].drop_duplicates())
fits = pd.read_csv(OUTPUT / 'fit_receipts.csv')
display(fits[['condition','prediction_year','action_ids','features','target_scale_cny']])"""
        ),
        nbf.v4.new_markdown_cell("## Stage C: composition, intensity and causal objective selection"),
        nbf.v4.new_code_cell(
            """sel = pd.read_csv(OUTPUT / 'objective_selection.csv')
display(sel)
for obj in ('mean','log_wealth','downside'):
    comp = pd.read_csv(OUTPUT / f'composition_{obj}.csv')
    w = [f'weight_{e}' for e in ['SMOOTH_M512','Q_TAIL_M192','DIVERGENCE_Z100_K1','RARE_LOGIT_TOP64']]
    print(obj, comp[w].describe().loc[['mean','max']].round(3).to_dict())
inten = pd.read_csv(OUTPUT / 'intensity_mean.csv')
print('intensity 2023 mean %.4f zero %.3f' % (
    inten.loc[inten.issue_year==2023,'predicted_intensity'].mean(),
    (inten.loc[inten.issue_year==2023,'predicted_intensity']<=1e-9).mean()))
display(Image(filename=str(OUTPUT / 'funding_intensity_2021_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Long-tail capture, funding response and falsification"),
        nbf.v4.new_code_cell(
            """curve = pd.read_csv(OUTPUT / 'funding_response_curve_2023.csv')
display(curve[['funding_intensity','terminal_capital_cny','capital_growth_pct','max_drawdown_pct']].round(2))
null = pd.read_csv(OUTPUT / 'exact_exposure_null_2023.csv')
q = null['terminal_capital_cny'].quantile([.25,.5,.75,.9])
print('null quantiles:', q.round(1).to_dict())
print('primary percentile:', decision['decision']['placement_vs_permutation_percentile'])"""
        ),
        nbf.v4.new_markdown_cell(
            """## Interpretation

The state-dependent dynamic policy (composition + intensity) beats cash, exact
B0_BEST_FULL, the #299 residual, static full-bankroll mixture, and both
shuffled controls in matched 2023 lift. Decomposition shows the value comes
from Stage A keep/skip plus state-dependent funding intensity: a *fixed*
funding intensity selected on earlier OOF folds collapses to zero, reproducing
the #302 finding exactly, while the learned state-dependent intensity deploys
a positive fraction on favorable issues. Composition adds no separate matched
lift at the fixed-intensity margin, and the exact executed-exposure null
percentile (75%) does not clear the 95% bar, so the verdict is
EXPERT_VALUE_SIGNAL — expert layer adds positive matched lift but fails the
cash/static/exact-null barriers for a promotable dynamic expert claim."""
        ),
    ]
    nbf.write(notebook, target)
    print(target)


if __name__ == "__main__":
    main()