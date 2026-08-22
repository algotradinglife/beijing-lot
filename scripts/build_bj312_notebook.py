#!/usr/bin/env python3
"""Build and execute the Issue #312 decision notebook."""

from pathlib import Path
import sys

from nbclient import NotebookClient
import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue312.experiment import write_manifest  # noqa: E402


def main() -> None:
    target = Path(
        "notebooks/research/issue-312/bj312_explicit_joint_action_cube.ipynb"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.14"},
    }
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            """# Issue #312 — explicit within-issue joint action cube

Every exact-B0-common-support 2023 issue receives exactly 512 CNY2 tickets. The model learns
match selector, candidate pool, outcome direction, N/K, generator and bounded
protection; it cannot skip an issue or reduce its committed budget."""
        ),
        nbf.v4.new_code_cell(
            """from pathlib import Path
import json
import pandas as pd
from IPython.display import Image, display

ROOT = next(path for path in (Path.cwd(), *Path.cwd().parents)
            if (path / 'src' / 'issue312').is_dir())
OUTPUT = ROOT / 'results/issue-312'
decision = json.loads((OUTPUT / 'decision.json').read_text())
decision"""
        ),
        nbf.v4.new_markdown_cell("## Frozen design and support"),
        nbf.v4.new_code_cell(
            """registry = pd.read_csv(OUTPUT / 'action_registry.csv')
marginal = pd.read_csv(OUTPUT / 'action_design_marginals.csv')
pairwise = pd.read_csv(OUTPUT / 'action_design_pairwise_coverage.csv')
display(registry.groupby('is_anchor').size().rename('actions'))
display(marginal.pivot(index='level', columns='factor', values='count').fillna(''))
display(pairwise.sort_values('coverage_fraction').head(10))"""
        ),
        nbf.v4.new_markdown_cell("## Development freeze and model receipts"),
        nbf.v4.new_code_cell(
            """development = pd.read_csv(OUTPUT / 'development_policy_selection.csv')
fits = pd.read_csv(OUTPUT / 'pre2023_fit_receipts.csv')
display(development)
display(fits.groupby('condition').agg(fits=('model_seed','size'),
    converged=('converged','all'), max_iterations=('iterations','max'),
    train_issues=('train_issues','max')))"""
        ),
        nbf.v4.new_markdown_cell("## Fixed-exposure capital, tails and attribution"),
        nbf.v4.new_code_cell(
            """summary = pd.read_csv(OUTPUT / 'policy_summary.csv')
cols = ['condition','median_terminal_capital_cny','median_capital_growth_pct',
        'median_turnover_roi_pct','median_max_drawdown_pct',
        'median_ex_largest_pnl_cny','median_positive_issue_rate',
        'median_tail_5x_rate']
display(summary[cols].sort_values('median_terminal_capital_cny', ascending=False))
display(pd.read_csv(OUTPUT / 'exact_b0_reference_2023.csv'))
display(pd.read_csv(OUTPUT / 'factor_attribution.csv'))
display(Image(filename=str(OUTPUT / 'capital_paths_2023.png')))
display(Image(filename=str(OUTPUT / 'risk_tail_frontier_2023.png')))"""
        ),
        nbf.v4.new_markdown_cell("## Learned parameter distribution and physical null"),
        nbf.v4.new_code_cell(
            """display(pd.read_csv(OUTPUT / 'primary_parameter_distribution.csv')
        .sort_values('allocated_tickets', ascending=False).head(30))
null = pd.read_csv(OUTPUT / 'same_exposure_permutation_2023.csv')
display(null.median_terminal_capital_cny.describe(percentiles=[.05,.5,.95]))
display(Image(filename=str(OUTPUT / 'primary_parameter_distribution.png')))"""
        ),
        nbf.v4.new_markdown_cell(
            """## Decision boundary

The primary claim is judged against fixed/static controls on inherited exact-B0
common support, paired physical ticket seeds, factor resets, a same-exposure
permutation null and ex-largest performance. #306 is interface-only context,
not an accepted positive baseline. Ticket seeds remain nested within Beijing
issues. 2024+ is sealed."""
        ),
    ]
    NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(Path.cwd())}},
    ).execute()
    nbf.write(notebook, target)
    write_manifest(ROOT / "results/issue-312")
    print(target)


if __name__ == "__main__":
    main()
