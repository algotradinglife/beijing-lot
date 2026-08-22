#!/usr/bin/env python3
"""Build the executed decision notebook for Issue #305."""

from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


def main() -> None:
    target = Path("notebooks/research/issue-305/bj305_keep_skip_correction.ipynb")
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.14"},
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            """# Issue #305 — dedicated BEST_FULL keep/skip correction

This notebook tests whether #302's apparent 2023 keep/skip gain survives a
baseline-only head and an exact same-exposure placement null. The independent
unit is an issue; 2024+ is sealed."""
        ),
        nbf.v4.new_code_cell(
            """from pathlib import Path
import json
import pandas as pd
from IPython.display import Image, display

ROOT = next(path for path in (Path.cwd(), *Path.cwd().parents) if (path / 'src' / 'issue305').is_dir())
OUTPUT = ROOT / 'results/issue-305'
decision = json.loads((OUTPUT / 'decision.json').read_text())
decision"""
        ),
        nbf.v4.new_markdown_cell("## Capital paths and matched controls"),
        nbf.v4.new_code_cell(
            """summary = pd.read_csv(OUTPUT / 'policy_summary.csv')
focus = ['DEDICATED_MLP','DEDICATED_MLP_ALPHA5','DEDICATED_MLP_ALPHA50',
         'RIDGE_CONTROL','ISSUE_BLOCK_SHUFFLED','B0_BEST_FULL','CASH_NO_BET',
         'ISSUE299_LEARNED_RESIDUAL','ORACLE_DIAGNOSTIC']
cols = ['evaluation_year','condition','funded_issues','terminal_capital_cny',
        'capital_growth_pct','stake_cny','max_drawdown_pct',
        'longest_losing_issue_streak','worst_rolling_10_pnl_cny']
display(summary[summary.condition.isin(focus)][cols])
display(Image(filename=str(OUTPUT / 'capital_paths_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Exact executed-exposure null"),
        nbf.v4.new_code_cell(
            """null_receipt = json.loads((OUTPUT / 'exact_exposure_null_2023.json').read_text())
legacy_receipt = json.loads((OUTPUT / 'legacy_302_exact_null.json').read_text())
display(null_receipt)
display(legacy_receipt)
display(pd.read_csv(OUTPUT / 'exact_exposure_null_histogram_2023.csv'))
display(Image(filename=str(OUTPUT / 'exact_exposure_null_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Convergence and sensitivity"),
        nbf.v4.new_code_cell(
            """receipts = pd.read_csv(OUTPUT / 'fit_receipts.csv')
display(receipts.groupby('condition')[['mean_iterations','downside_iterations']].max())
display(receipts.groupby('condition')[['mean_converged','downside_converged']].all())
display(pd.read_csv(OUTPUT / 'sensitivity_2023.csv'))
display(Image(filename=str(OUTPUT / 'sensitivity_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell(
            """## Decision interpretation

The independent model loses 7.11% in 2023 while fixed BEST_FULL loses 20.75%,
but its eight funded issues are only at the 42.71st percentile of all exact
same-count placements. Alpha sensitivity changes the funded set materially and
the shuffled-state control chooses cash. Therefore exposure reduction explains
the lift; dedicated issue-selection skill is not identified. The expert-label
NO_PROMOTION from #302 remains controlling."""
        ),
    ]
    client = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(Path.cwd())}},
    )
    client.execute()
    nbf.write(notebook, target)
    print(target)


if __name__ == "__main__":
    main()
