"""Decision report, figures and executed notebook for Issue #332."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from .contract import INITIAL_CAPITAL_CNY


def write_report(
    repo_root: Path,
    decision: dict[str, object],
    summary: pd.DataFrame,
    paired: pd.DataFrame,
    bootstrap: pd.DataFrame,
    auxiliary: pd.DataFrame,
    attribution: pd.DataFrame,
    paths: pd.DataFrame,
    accepted: pd.DataFrame,
) -> None:
    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    _plot_capital(paths, figure_dir / "issue_332_fixed_expert_capital.png")
    _plot_lifts(paired, figure_dir / "issue_332_moe_lift.png")
    _plot_weights(attribution, figure_dir / "issue_332_expert_weights.png")

    selected = summary[
        summary["condition"].isin(
            [
                "BEST_SINGLE_EXPERT",
                "EQUAL_MIX",
                "STATIC_SHRUNK_MIX",
                "CURRENT_ONLY_MOE",
                "LAGGED_MULTITASK_MOE",
                "LAGGED_HGB_MOE",
                "LAG_STATE_SHIFTED",
            ]
        )
    ][
        [
            "issue_year",
            "condition",
            "terminal_capital_cny",
            "capital_return",
            "turnover_roi",
            "max_drawdown_pct",
            "longest_losing_issues",
            "ex_largest_pnl_cny",
        ]
    ]
    lag_lift = paired[
        paired["condition"].eq("LAGGED_MULTITASK_MOE")
        & paired["baseline"].isin(
            ["CURRENT_ONLY_MOE", "BEST_SINGLE_EXPERT", "EQUAL_MIX"]
        )
    ]
    aux = auxiliary[
        auxiliary["condition"].isin(
            ["CURRENT_ONLY_MOE", "LAGGED_MULTITASK_MOE", "LAG_STATE_SHIFTED"]
        )
    ]
    body = f"""# Issue #332 — Fixed-expert causal multitask MoE

## Five-minute result

- Disposition: **{decision['disposition']}**.
- The experiment uses eight frozen #314 experts and always allocates exactly 512 paid tickets per issue. There is no cash/no-bet escape hatch.
- The model first predicts dense hit/near-miss/positive-seed outcomes, then fits a Ridge utility head only on chronological OOF dense predictions. Realized expert PnL is not the sole representation target.
- 2023 and 2024 are reported independently; 2025+ is untouched.
- Promotion: **{decision['promotion']}**; #210 unlock: **{decision['unlock_210']}**.

## What was tested

The expert set spans N7–N10, MARKET/VALUE/DIVERGENCE direction, WR/WOR generation and selective protection. Current issue features are compared with the strictly prior #330 global state plus expert-specific prior hit/near-miss history. `LAG_STATE_SHIFTED` delays lag inputs by seven additional anchors, and `EXPERT_IDENTITY_SHUFFLED` breaks the training identity-to-mechanism map.

The primary soft allocation is fixed before settlement: experts are ranked by predicted utility and receive 205/128/77/51/26/15/8/2 tickets. Every arm therefore stakes CNY 1,024 per issue. The 0.65 factor is applied once to a complete winning ticket.

## Capital and risk summary

    {_table(selected)}

## Primary matched lifts

    {_table(lag_lift)}

## Bootstrap against current-only

{_table(bootstrap[bootstrap['condition'].isin(['LAGGED_MULTITASK_MOE','LAGGED_HGB_MOE','LAG_STATE_SHIFTED'])])}

## Accepted #319 Top-2 N7 baseline (exact common support, 512-ticket matched exposure)

{_table(accepted[accepted['condition'].isin(['BEST_SINGLE_EXPERT','CURRENT_ONLY_MOE','LAGGED_MULTITASK_MOE','LAGGED_HGB_MOE'])])}

## Auxiliary representation diagnostics

    {_table(aux)}

## PI interpretation

{decision['interpretation']}

The adversarial reading is decisive: an apparent capital lift is not credited if it disappears after the largest issue, is confined to one nuisance seed/year, is reproduced by delayed state, or merely reflects the strongest fixed expert receiving more capital. The correct baseline for a dynamic gate is both the strongest prior-only fixed expert and an otherwise identical current-only gate.

## Figures

![capital paths](figures/issue_332_fixed_expert_capital.png)

![matched lift](figures/issue_332_moe_lift.png)

![expert weights](figures/issue_332_expert_weights.png)
"""
    (repo_root / "docs/research/Issue-Fixed-Expert-MoE.md").write_text(
        body, encoding="utf-8"
    )


def write_notebook(repo_root: Path) -> None:
    target = repo_root / "notebooks/research/fixed-expert-moe/fixed_expert_moe.ipynb"
    target.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook()
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(
            "# Issue #332 — fixed-expert causal multitask MoE\n"
            "Executed decision notebook. Heavy ticket replay lives in the reproducible runner; "
            "this notebook audits the frozen outputs and decision evidence."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\n"
            "ROOT=Path.cwd()\nOUT=ROOT/'results/fixed_expert_moe'\n"
            "decision=json.loads((OUT/'decision.json').read_text())\ndecision"
        ),
        nbformat.v4.new_markdown_cell("## Data completeness and chronology"),
        nbformat.v4.new_code_cell(
            "panel=pd.read_parquet(OUT/'learning_panel.parquet')\n"
            "surface=pd.read_parquet(OUT/'model_surface.parquet')\n"
            "pd.DataFrame({'issues':panel.groupby('issue_year').issue.nunique(),"
            "'experts_per_issue_min':panel.groupby(['issue_year','issue']).expert.nunique().groupby(level=0).min(),"
            "'surface_seeds':surface.groupby('issue_year').seed.nunique()})"
        ),
        nbformat.v4.new_markdown_cell("## Matched capital and risk"),
        nbformat.v4.new_code_cell(
            "summary=pd.read_csv(OUT/'policy_summary.csv')\n"
            "summary[summary.condition.isin(['BEST_SINGLE_EXPERT','EQUAL_MIX','STATIC_SHRUNK_MIX','CURRENT_ONLY_MOE','LAGGED_MULTITASK_MOE','LAGGED_HGB_MOE','LAG_STATE_SHIFTED'])]"
        ),
        nbformat.v4.new_markdown_cell("## Paired lift and bootstrap stability"),
        nbformat.v4.new_code_cell(
            "paired=pd.read_csv(OUT/'paired_lifts.csv')\nboot=pd.read_csv(OUT/'bootstrap_lift.csv')\n"
            "display(paired[(paired.condition=='LAGGED_MULTITASK_MOE') & paired.baseline.isin(['CURRENT_ONLY_MOE','BEST_SINGLE_EXPERT','EQUAL_MIX'])])\n"
            "boot[boot.condition.isin(['LAGGED_MULTITASK_MOE','LAGGED_HGB_MOE','LAG_STATE_SHIFTED'])]"
        ),
        nbformat.v4.new_markdown_cell("## Expert mechanism allocation"),
        nbformat.v4.new_code_cell(
            "weights=pd.read_csv(OUT/'allocation_attribution.csv')\n"
            "weights[weights.condition=='LAGGED_MULTITASK_MOE'].pivot(index='expert',columns='issue_year',values='mean_weight')"
        ),
        nbformat.v4.new_markdown_cell("## Decision figures"),
        nbformat.v4.new_code_cell(
            "from IPython.display import Image, display\n"
            "for name in ['issue_332_fixed_expert_capital.png','issue_332_moe_lift.png','issue_332_expert_weights.png']:\n"
            "    display(Image(filename=str(ROOT/'docs/research/figures'/name)))"
        ),
    ]
    notebook["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    NotebookClient(notebook, timeout=180, kernel_name="python3", resources={"metadata": {"path": str(repo_root)}}).execute()
    nbformat.write(notebook, target)


def _plot_capital(paths: pd.DataFrame, target: Path) -> None:
    conditions = [
        "BEST_SINGLE_EXPERT",
        "EQUAL_MIX",
        "CURRENT_ONLY_MOE",
        "LAGGED_MULTITASK_MOE",
        "LAG_STATE_SHIFTED",
    ]
    plt.figure(figsize=(11, 6))
    for condition in conditions:
        frame = paths[paths["condition"].eq(condition)]
        if frame.empty:
            continue
        pivot = frame.pivot_table(index=["issue_year", "issue"], columns="seed", values="capital_cny").sort_index()
        x = np.arange(len(pivot))
        median = pivot.median(axis=1).to_numpy(float)
        plt.plot(x, median, label=condition)
        if condition == "LAGGED_MULTITASK_MOE":
            plt.fill_between(x, pivot.quantile(.1, axis=1), pivot.quantile(.9, axis=1), alpha=.15)
    plt.axhline(INITIAL_CAPITAL_CNY, color="black", linewidth=.8)
    plt.xlabel("Issue order (2022–2024)")
    plt.ylabel("Capital (CNY)")
    plt.title("Fixed-expert MoE — median issue-level capital paths")
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(target, dpi=160)
    plt.close()


def _plot_lifts(paired: pd.DataFrame, target: Path) -> None:
    frame = paired[
        paired["baseline"].eq("CURRENT_ONLY_MOE")
        & paired["condition"].isin(
            ["LAGGED_MULTITASK_MOE", "LAGGED_HGB_MOE", "LAG_STATE_SHIFTED"]
        )
    ]
    pivot = frame.pivot(index="condition", columns="issue_year", values="median_lift_cny")
    pivot.plot(kind="bar", figsize=(9, 5))
    plt.axhline(0, color="black", linewidth=.8)
    plt.ylabel("Median matched lift vs current-only (CNY)")
    plt.title("Does lagged state add incremental expert-allocation value?")
    plt.xticks(rotation=15, ha="right")
    plt.tight_layout()
    plt.savefig(target, dpi=160)
    plt.close()


def _plot_weights(attribution: pd.DataFrame, target: Path) -> None:
    frame = attribution[attribution["condition"].eq("LAGGED_MULTITASK_MOE")]
    pivot = frame.pivot(index="expert", columns="issue_year", values="mean_weight")
    plt.figure(figsize=(8, 6))
    plt.imshow(pivot.to_numpy(float), aspect="auto", cmap="viridis")
    plt.colorbar(label="Mean capital weight")
    plt.xticks(range(len(pivot.columns)), pivot.columns)
    plt.yticks(range(len(pivot.index)), pivot.index, fontsize=8)
    plt.title("Lagged multitask MoE expert allocation")
    plt.tight_layout()
    plt.savefig(target, dpi=160)
    plt.close()


def _table(frame: pd.DataFrame) -> str:
    return "```text\n" + frame.to_string(index=False, float_format=lambda x: f"{x:.4f}") + "\n```"
