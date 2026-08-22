"""Decision-facing report, notebook and figures for Issue #330."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

def annual_summary(state: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, group in state.groupby("issue_year", sort=True):
        allocator = group.allocator_delta.dropna()
        rows.append({
            "issue_year": int(year), "issues": len(group),
            "mean_trusted_fixture_fraction": float(group.trusted_fixture_fraction.mean()),
            "eu_brier": float(group.eu_brier.mean()),
            "line_brier": float(group.line_brier.mean()),
            "eu_top2_residual": float(group.eu_top2_residual.mean()),
            "line_top2_residual": float(group.line_top2_residual.mean()),
            "allocator_observable": len(allocator),
            "allocator_delta_sum": float(allocator.sum()),
            "allocator_nonzero": int(allocator.ne(0).sum()),
            "allocator_positive": int(allocator.gt(0).sum()),
        })
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame, formats: dict[str, str]) -> str:
    columns = list(frame.columns)
    rows = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join("---:" for _ in columns) + "|",
    ]
    for row in frame.itertuples(index=False):
        values = []
        for column, value in zip(columns, row, strict=True):
            if pd.isna(value):
                values.append("NA")
            elif column in formats:
                values.append(format(value, formats[column]))
            else:
                values.append(str(value))
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def write_report(
    repo_root: Path,
    state: pd.DataFrame,
    metrics: pd.DataFrame,
    bootstrap: pd.DataFrame,
    decision: dict,
) -> None:
    annual = annual_summary(state)
    eu_brier_range = float(annual.eu_brier.max() - annual.eu_brier.min())
    brier_advantage = annual.line_brier - annual.eu_brier
    max_top2_bias = float(
        annual[["eu_top2_residual", "line_top2_residual"]].abs().to_numpy().max()
    )
    annual_table = _markdown_table(annual, {
        "mean_trusted_fixture_fraction": ".2%", "eu_brier": ".4f",
        "line_brier": ".4f", "eu_top2_residual": "+.4f",
        "line_top2_residual": "+.4f", "allocator_delta_sum": "+.0f",
    })
    focus = metrics[
        metrics.issue_year.isin([2023, 2024])
        & metrics.condition.isin(["CURRENT_RIDGE", "COMBINED_HGBR", "COMBINED_HGBR_STATE_SHIFT"])
    ][["target", "issue_year", "condition", "issues", "mse", "mse_lift_vs_prior", "spearman"]]
    metric_table = _markdown_table(focus, {
        "mse": ".6f", "mse_lift_vs_prior": "+.6f", "spearman": "+.3f",
    })
    bootstrap_table = _markdown_table(
        bootstrap[bootstrap.issue_year.isin([2023, 2024])],
        {"mean_mse_improvement": "+.6f", "ci95_low": "+.6f", "ci95_high": "+.6f"},
    )
    report = f"""# Issue #330 — Causal lagged regime state ledger

## Decision

`{decision['disposition']}`; promotion is `false`, and #210 remains blocked.

The state panel is useful, but the direct allocator target is not a viable gate:
only {decision['allocator_positive_issues']} of {decision['allocator_observable_issues']}
observable issues have positive A1-minus-A0 PnL, and only
{decision['allocator_nonzero_issues']} are nonzero. The next MoE interface is
`{decision['next_moe_interface']}`: use lagged calibration/coverage state as a
shared auxiliary representation and keep expert PnL as the terminal evaluation,
not the only supervised label.

## Data completeness and annual state

{annual_table}

`Top2 residual = realized Top2 coverage - predicted Top2 probability mass`.
Positive values mean the model covered realized outcomes more often than its
assigned mass implied; this is a calibration diagnostic, not betting profit.

The broad probability layer is much more stable than the allocator payout:
European Brier varies by only {eu_brier_range:.4f} across five years and beats
the Beijing-line control by {brier_advantage.min():.4f} to
{brier_advantage.max():.4f} each year. Absolute annual Top2 calibration bias is
at most {max_top2_bias:.4f}. The large 2023/2024 allocator reversal therefore
does not look like a broad failure of the market probability center; sparse
winning-ticket allocation is the more direct explanation.

## Chronological predictive diagnostics

{metric_table}

The combined lagged model improves the current-only model consistently in
{decision['consistent_calibration_targets']} of four calibration targets across
both 2023 and 2024. Block-bootstrap lower bounds are positive in
{decision['bootstrap_positive_calibration_slices']} calibration year-target
slices. This rejects a deployable fast-regime gate from the present summaries.

The state-shift rows rotate complete lag blocks across issues while leaving the
current pre-event cross-section unchanged. If shifted performance is similar or
better, the apparent lagged signal is not accepted as issue-specific state skill.

## Block-bootstrap MSE increment: combined HGBR minus current Ridge

Positive values favor adding lagged state.

{bootstrap_table}

## Information carried forward

- Admissible current inputs: market probability entropy/concentration, Top1/Top2
  mass, European-vs-Beijing-line divergence, line mix and bookmaker coverage.
- Experimental auxiliary state inputs: strictly shifted rolling/EWMA Brier,
  log loss and Top1/Top2 coverage residuals with observation counts and last
  timestamps. They are causally admissible but **not** established predictors;
  the next issue must retain a no-lag ablation and state-shift falsification.
- Diagnostic-only until more support: lagged A1-A0 PnL, fixed-strategy PnL,
  near-miss and payout concentration. Their labels are too sparse/partial to be
  the sole MoE gating target.
- Rejected inputs: calendar year, issue-code prefix, same-issue outcome, future
  settlement, final SP and any outcome-ranked expert choice.

## Adversarial interpretation

- Smooth year-to-year movement can reflect bookmaker adaptation, source changes
  or sample composition; it is not by itself a tradable regime.
- A small next-issue MSE gain does not establish capital Edge. The following MoE
  must beat static expert weights and issue-block state-shuffled controls on
  matched exposure.
- The 2023/2024 slices are historical diagnostics already opened elsewhere.
  They do not substitute for #210 prospective evidence.
- The sparse allocator response explains why #328 collapsed to A0 and motivates
  multitask learning, but it does not prove that a neural gate will succeed.

## Evidence

- Executed notebook: `notebooks/research/regime-state/regime_state.ipynb`
- State ledger: `results/regime_state/state_ledger.parquet`
- OOF predictions and diagnostics: `oof_predictions.parquet`,
  `prediction_metrics.csv`, `bootstrap_increment.csv`, `persistence.csv`
- Exact source/chronology receipt and package hashes under `results/regime_state/`
"""
    path = repo_root / "docs/research/Issue-Regime-State-Ledger.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report)


def write_figures(repo_root: Path, state: pd.DataFrame, metrics: pd.DataFrame) -> None:
    directory = repo_root / "docs/research/figures"
    directory.mkdir(parents=True, exist_ok=True)
    ordered = state.sort_values(["issue_anchor_ts", "issue_code"]).reset_index(drop=True)
    figure, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    axes[0].plot(ordered.eu_brier, color="#b8b8b8", alpha=0.45, label="issue EU Brier")
    axes[0].plot(ordered.lag_eu_brier_ewm20, color="#0068b5", label="prior-only EWMA20")
    axes[0].plot(ordered.lag_line_brier_ewm20, color="#d55e00", label="line EWMA20")
    axes[0].set(ylabel="Brier", title="Strictly lagged calibration state")
    axes[0].legend()
    axes[1].plot(ordered.eu_top2_residual, color="#b8b8b8", alpha=0.45, label="issue residual")
    axes[1].plot(ordered.lag_eu_top2_residual_ewm20, color="#009e73", label="prior-only EWMA20")
    axes[1].axhline(0, color="black", lw=0.8, ls="--")
    axes[1].set(xlabel="chronological issue index", ylabel="Top2 residual")
    axes[1].legend()
    figure.tight_layout()
    figure.savefig(directory / "issue_330_lagged_regime_paths.png", dpi=160)
    plt.close(figure)

    focus = metrics[
        metrics.condition.isin(["CURRENT_RIDGE", "COMBINED_HGBR"])
        & metrics.issue_year.isin([2023, 2024])
    ].copy()
    current = focus[focus.condition.eq("CURRENT_RIDGE")][
        ["target", "issue_year", "mse"]
    ].rename(columns={"mse": "current_mse"})
    combined = focus[focus.condition.eq("COMBINED_HGBR")].merge(
        current, on=["target", "issue_year"], validate="one_to_one"
    )
    combined["relative_mse_change"] = combined.mse / combined.current_mse - 1
    pivot = combined.pivot(index="target", columns="issue_year", values="relative_mse_change")
    axis = pivot.plot.bar(figsize=(9, 4.8))
    axis.axhline(0, color="black", lw=0.8)
    axis.set(ylabel="Combined HGBR MSE / current Ridge MSE - 1", title="Lagged-state predictive increment")
    axis.figure.tight_layout()
    axis.figure.savefig(directory / "issue_330_regime_model_increment.png", dpi=160)
    plt.close(axis.figure)


def write_notebook(repo_root: Path) -> None:
    import nbformat
    from nbclient import NotebookClient

    directory = repo_root / "notebooks/research/regime-state"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "regime_state.ipynb"
    notebook = nbformat.v4.new_notebook(cells=[
        nbformat.v4.new_markdown_cell(
            "# Issue #330 — Causal lagged regime state\n\nOne Beijing issue is one sample."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\nimport matplotlib.pyplot as plt\n"
            "ROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/regime_state'"
        ),
        nbformat.v4.new_code_cell("decision=json.loads((OUT/'decision.json').read_text()); decision"),
        nbformat.v4.new_code_cell(
            "state=pd.read_parquet(OUT/'state_ledger.parquet'); "
            "metrics=pd.read_csv(OUT/'prediction_metrics.csv'); state.groupby('issue_year').size()"
        ),
        nbformat.v4.new_code_cell(
            "state.groupby('issue_year')[['eu_brier','line_brier','eu_top2_residual','line_top2_residual','allocator_delta']].mean()"
        ),
        nbformat.v4.new_code_cell(
            "metrics[(metrics.issue_year.isin([2023,2024])) & "
            "(metrics.condition.isin(['CURRENT_RIDGE','COMBINED_HGBR','COMBINED_HGBR_STATE_SHIFT']))]"
        ),
        nbformat.v4.new_code_cell(
            "ordered=state.sort_values(['issue_anchor_ts','issue_code']).reset_index(drop=True); "
            "plt.plot(ordered.lag_eu_brier_ewm20,label='EU'); "
            "plt.plot(ordered.lag_line_brier_ewm20,label='line'); plt.legend(); plt.show()"
        ),
    ])
    executed = NotebookClient(notebook, timeout=300, kernel_name="python3").execute(cwd=directory)
    nbformat.write(executed, path)
