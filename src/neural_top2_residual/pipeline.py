"""End-to-end Issue #334 experiment runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from .contract import DEVELOPMENT_YEAR, FEATURE_COLUMNS, MODEL_SEEDS, STARTING_CAPITAL_CNY, TERMINAL_YEAR
from .data import attach_labels, load_causal_cells, source_receipt
from .evaluation import (
    accepted_baseline_parity,
    bootstrap_lifts,
    factorial_attribution,
    matched_performance,
    select_anchor_shrinkage,
    select_neural_arm,
    select_neural_config,
)
from .model import (
    fit_candidate_surface,
    fit_shuffled_surface,
    prediction_diagnostics,
)
from .policy import anchor_shrinkage_surface, baseline_prediction_surface, build_and_settle


def run_experiment(repo_root: Path, output_dir: Path, *, reuse_models: bool = True) -> dict[str, object]:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    figures = repo_root / "docs/research/figures"
    figures.mkdir(parents=True, exist_ok=True)

    causal = load_causal_cells()
    receipt = source_receipt(causal)
    labelled = attach_labels(causal)
    evaluation_cells = labelled[labelled["issue_year"].isin([DEVELOPMENT_YEAR, TERMINAL_YEAR])].copy()
    candidate_path = output_dir / "candidate_predictions.parquet"
    receipt_path = output_dir / "source_receipt.json"
    cached_receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
    if reuse_models and candidate_path.exists() and cached_receipt == receipt:
        candidate_predictions = pd.read_parquet(candidate_path)
    else:
        candidate_predictions = fit_candidate_surface(labelled)
        candidate_predictions.to_parquet(candidate_path, index=False)
        _write_json(receipt_path, receipt)

    candidate_tickets, candidate_bundles = build_and_settle(
        evaluation_cells,
        candidate_predictions,
        arms=("S0O0", "S1O1"),
        include_tickets=False,
    )
    del candidate_tickets
    selected_config, config_selection = select_neural_config(candidate_bundles)

    selected_predictions = candidate_predictions[candidate_predictions["model"].eq(selected_config)].copy()
    linear_predictions = candidate_predictions[candidate_predictions["model"].eq("LINEAR")].copy()
    shuffled_path = output_dir / "shuffled_predictions.parquet"
    if reuse_models and shuffled_path.exists() and cached_receipt == receipt:
        shuffled_predictions = pd.read_parquet(shuffled_path)
        if not shuffled_predictions["model"].str.startswith(selected_config).all():
            shuffled_predictions = fit_shuffled_surface(labelled, selected_config)
            shuffled_predictions.to_parquet(shuffled_path, index=False)
    else:
        shuffled_predictions = fit_shuffled_surface(labelled, selected_config)
        shuffled_predictions.to_parquet(shuffled_path, index=False)

    baseline_predictions = baseline_prediction_surface(evaluation_cells)
    anchor_predictions = anchor_shrinkage_surface(evaluation_cells)
    baseline_tickets, baseline_bundles = build_and_settle(
        evaluation_cells, baseline_predictions, arms=("S0O0",)
    )
    linear_tickets, linear_bundles = build_and_settle(
        evaluation_cells,
        linear_predictions,
        arms=("S0O0", "S1O0", "S0O1_SUPPORT", "S0O1_ALLOC", "S0O1", "S1O1"),
    )
    neural_tickets, neural_bundles = build_and_settle(
        evaluation_cells,
        selected_predictions,
        arms=("S0O0", "S1O0", "S0O1_SUPPORT", "S0O1_ALLOC", "S0O1", "S1O1"),
    )
    shuffled_tickets, shuffled_bundles = build_and_settle(
        evaluation_cells,
        shuffled_predictions,
        arms=("S0O0", "S1O0", "S0O1_SUPPORT", "S0O1_ALLOC", "S0O1", "S1O1"),
    )
    anchor_tickets, anchor_bundles = build_and_settle(
        evaluation_cells,
        anchor_predictions,
        arms=("S0O0", "S1O0", "S0O1_SUPPORT", "S0O1_ALLOC", "S0O1", "S1O1"),
    )
    tickets = pd.concat(
        [baseline_tickets, linear_tickets, neural_tickets, shuffled_tickets, anchor_tickets],
        ignore_index=True,
    )
    bundles = pd.concat(
        [baseline_bundles, linear_bundles, neural_bundles, shuffled_bundles, anchor_bundles],
        ignore_index=True,
    )
    selected_arm, arm_selection = select_neural_arm(bundles, selected_config)
    selected_anchor, anchor_selection = select_anchor_shrinkage(bundles)
    performance, risk, capital = matched_performance(bundles)
    factorial = factorial_attribution(bundles, selected_config)
    anchor_components = _anchor_components(performance, selected_anchor)
    neural_bootstrap = bootstrap_lifts(bundles, selected_config, selected_arm)
    neural_bootstrap["candidate"] = "NEURAL"
    anchor_bootstrap_frames = []
    for anchor_arm in ("S0O1", "S0O1_SUPPORT", "S0O1_ALLOC"):
        frame = bootstrap_lifts(bundles, selected_anchor, anchor_arm)
        frame["candidate"] = f"ANCHOR_{anchor_arm}"
        frame["arm"] = anchor_arm
        anchor_bootstrap_frames.append(frame)
    anchor_bootstrap = pd.concat(anchor_bootstrap_frames, ignore_index=True)
    bootstrap = pd.concat([neural_bootstrap, anchor_bootstrap], ignore_index=True)
    diagnostics = prediction_diagnostics(
        pd.concat(
            [
                baseline_predictions,
                linear_predictions,
                selected_predictions,
                shuffled_predictions,
                anchor_predictions,
            ],
            ignore_index=True,
        ),
        evaluation_cells,
    )
    parity = accepted_baseline_parity(bundles, repo_root)
    if not parity[["fixture_parity", "support_parity", "gross_parity"]].all().all():
        failures = parity[
            ~parity["fixture_parity"] | ~parity["support_parity"] | ~parity["gross_parity"]
        ]
        raise AssertionError(f"accepted Top-2 fallback parity failed on {len(failures)} issues")

    decision = _decision(
        selected_config,
        selected_arm,
        selected_anchor,
        performance,
        risk,
        neural_bootstrap,
        anchor_bootstrap[anchor_bootstrap["arm"].eq("S0O1")],
        diagnostics,
    )
    cell_coverage = labelled.groupby("issue_year", as_index=False).agg(
        issues=("issue", "nunique"),
        cells=("match_idx", "size"),
        observable_fraction=("settlement_available", "mean"),
        source_absent_cells=("availability_reason", lambda x: int(x.eq("SOURCE_ABSENT").sum())),
        untrusted_or_invalid_cells=("availability_reason", lambda x: int((~x.isin(["OBSERVABLE", "SOURCE_ABSENT"])).sum())),
    )
    match_counts = (
        labelled.drop_duplicates(["issue_year", "issue", "match_idx"])
        .groupby("issue_year", as_index=False)
        .size()
        .rename(columns={"size": "matches"})
    )
    cell_coverage = cell_coverage.merge(match_counts, on="issue_year", validate="one_to_one")
    allocation_audit = tickets.groupby(
        ["issue", "issue_year", "model", "seed", "arm"], as_index=False
    ).agg(
        funded_units=("units", "sum"),
        minimum_units=("units", "min"),
        maximum_units=("units", "max"),
        funded_stake_cny=("stake_cny", "sum"),
        distinct_tickets=("ticket_key", "nunique"),
    )
    tables = {
        "cell_panel.parquet": labelled,
        "candidate_predictions.parquet": candidate_predictions,
        "shuffled_predictions.parquet": shuffled_predictions,
        "tickets.parquet": tickets,
        "issue_policies.parquet": bundles,
        "config_selection.csv": config_selection,
        "arm_selection.csv": arm_selection,
        "anchor_selection.csv": anchor_selection,
        "performance.csv": performance,
        "risk_diagnostics.csv": risk,
        "capital_paths.parquet": capital,
        "factorial_attribution.csv": factorial,
        "anchor_component_attribution.csv": anchor_components,
        "bootstrap_lift.csv": bootstrap,
        "model_diagnostics.csv": diagnostics,
        "accepted_baseline_parity.csv": parity,
        "cell_coverage.csv": cell_coverage,
        "allocation_audit.csv": allocation_audit,
    }
    for name, frame in tables.items():
        path = output_dir / name
        if name.endswith(".parquet"):
            frame.to_parquet(path, index=False)
        else:
            frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")
    _write_json(output_dir / "source_receipt.json", receipt)
    _write_json(output_dir / "decision.json", decision)
    _write_json(output_dir / "model_receipt.json", _model_receipt(selected_config, selected_arm, diagnostics))

    figure_paths = _figures(
        repo_root, performance, capital, factorial, selected_config, selected_arm, selected_anchor
    )
    report_path = repo_root / "docs/research/Issue-Neural-Top2-Residual.md"
    report_path.write_text(
        _report(
            decision,
            receipt,
            performance,
            risk,
            factorial,
            anchor_components,
            diagnostics,
            bootstrap,
        ),
        encoding="utf-8",
    )
    notebook_path = repo_root / "notebooks/research/neural-top2-residual/neural_top2_residual.ipynb"
    _notebook(repo_root, notebook_path)
    _manifest(output_dir, receipt, decision, figure_paths, report_path, notebook_path)
    return decision


def _decision(
    model: str,
    arm: str,
    anchor_model: str,
    performance: pd.DataFrame,
    risk: pd.DataFrame,
    neural_bootstrap: pd.DataFrame,
    anchor_bootstrap: pd.DataFrame,
    diagnostics: pd.DataFrame,
) -> dict[str, object]:
    chosen = performance[(performance["model"].eq(model)) & performance["arm"].eq(arm)]
    development = chosen[chosen["issue_year"].eq(DEVELOPMENT_YEAR)]
    terminal = chosen[chosen["issue_year"].eq(TERMINAL_YEAR)]
    shuffled = performance[
        performance["model"].str.contains("LABEL_SHUFFLED")
        & performance["arm"].eq(arm)
        & performance["issue_year"].eq(TERMINAL_YEAR)
    ]
    terminal_risk = risk[
        risk["model"].eq(model) & risk["arm"].eq(arm) & risk["issue_year"].eq(TERMINAL_YEAR)
    ]
    terminal_bootstrap = neural_bootstrap[neural_bootstrap["issue_year"].eq(TERMINAL_YEAR)]
    raw = float(terminal["matched_lift_cny"].median())
    ex_largest = float(terminal["ex_largest_lift_cny"].median())
    shuffle_lift = float(shuffled["matched_lift_cny"].median()) if len(shuffled) else np.nan
    bootstrap_positive = float(terminal_bootstrap["bootstrap_positive_fraction"].median())
    baseline_advancing = bool(
        raw > 0
        and ex_largest > 0
        and (not np.isfinite(shuffle_lift) or raw > shuffle_lift)
        and bootstrap_positive >= 0.8
    )
    anchor_terminal = performance[
        performance["model"].eq(anchor_model)
        & performance["arm"].eq("S0O1")
        & performance["issue_year"].eq(TERMINAL_YEAR)
    ]
    anchor_raw = float(anchor_terminal["matched_lift_cny"].median())
    anchor_ex_largest = float(anchor_terminal["ex_largest_lift_cny"].median())
    anchor_positive = float(
        anchor_bootstrap.loc[
            anchor_bootstrap["issue_year"].eq(TERMINAL_YEAR),
            "bootstrap_positive_fraction",
        ].median()
    )
    anchor_candidate = bool(
        anchor_raw > 0 and anchor_ex_largest > 0 and anchor_positive >= 0.8
    )
    anchor_components = performance[
        performance["model"].eq(anchor_model)
        & performance["issue_year"].eq(TERMINAL_YEAR)
        & performance["arm"].isin(["S0O1_SUPPORT", "S0O1_ALLOC"])
    ].set_index("arm")
    promotion = baseline_advancing or anchor_candidate
    return {
        "issue": 334,
        "selected_model": model,
        "selected_arm": arm,
        "selection_data": "2023_ONLY",
        "terminal_data": "2024_FROZEN_ONCE",
        "development_median_lift_cny": float(development["matched_lift_cny"].median()),
        "development_median_ex_largest_lift_cny": float(development["ex_largest_lift_cny"].median()),
        "terminal_median_lift_cny": raw,
        "terminal_median_ex_largest_lift_cny": ex_largest,
        "terminal_shuffled_median_lift_cny": shuffle_lift,
        "terminal_bootstrap_positive_fraction_median": bootstrap_positive,
        "terminal_max_drawdown_fraction_median": float(terminal_risk["max_drawdown_fraction"].median()),
        "terminal_probability_brier_median": float(
            diagnostics[
                diagnostics["model"].eq(model) & diagnostics["issue_year"].eq(TERMINAL_YEAR)
            ]["brier"].median()
        ),
        "selected_anchor_control": anchor_model,
        "anchor_terminal_lift_cny": anchor_raw,
        "anchor_terminal_ex_largest_lift_cny": anchor_ex_largest,
        "anchor_terminal_bootstrap_positive_fraction": anchor_positive,
        "anchor_baseline_advancing_candidate": anchor_candidate,
        "anchor_support_only_terminal_lift_cny": float(
            anchor_components.loc["S0O1_SUPPORT", "matched_lift_cny"]
        ),
        "anchor_support_only_terminal_ex_largest_lift_cny": float(
            anchor_components.loc["S0O1_SUPPORT", "ex_largest_lift_cny"]
        ),
        "anchor_allocation_only_terminal_lift_cny": float(
            anchor_components.loc["S0O1_ALLOC", "matched_lift_cny"]
        ),
        "anchor_allocation_only_terminal_ex_largest_lift_cny": float(
            anchor_components.loc["S0O1_ALLOC", "ex_largest_lift_cny"]
        ),
        "accepted_baseline": "#319 P_TOP2_NO_GATE N7 / 512 units / CNY1024",
        "baseline_advancing_candidate": baseline_advancing,
        "promotion": promotion,
        "unlock_210": promotion,
        "disposition": (
            "BASELINE_ADVANCING_CANDIDATE"
            if promotion
            else "ANCHOR_SHRINKAGE_SIGNAL_NOT_YET_PROMOTED"
        ),
        "next_interface": (
            "HELDOUT_REVIEW" if promotion else "ANCHOR_SHRINKAGE_REPLICATION"
        ),
    }


def _model_receipt(model: str, arm: str, diagnostics: pd.DataFrame) -> dict[str, object]:
    return {
        "selected_model": model,
        "selected_arm": arm,
        "model_seeds": list(MODEL_SEEDS),
        "features": list(FEATURE_COLUMNS),
        "fit_years": [2020, 2021, 2022],
        "selection_year": 2023,
        "terminal_year": 2024,
        "terminal_rows_seen_during_selection": 0,
        "models_in_diagnostics": sorted(diagnostics["model"].unique()),
    }


def _figures(
    repo_root: Path,
    performance: pd.DataFrame,
    capital: pd.DataFrame,
    factorial: pd.DataFrame,
    model: str,
    arm: str,
    anchor_model: str,
) -> list[Path]:
    output: list[Path] = []
    figure_dir = repo_root / "docs/research/figures"
    chosen = capital[capital["model"].eq(model) & capital["arm"].eq(arm)].copy()
    fig, ax = plt.subplots(figsize=(12, 6))
    for year, group in chosen.groupby("issue_year"):
        pivot = group.pivot_table(index="issue_order", columns="seed", values="capital_cny")
        median = pivot.median(axis=1)
        ax.plot(median.index, median, label=f"neural {int(year)}")
        if int(year) == TERMINAL_YEAR:
            baseline = group.groupby("issue_order")["baseline_capital_cny"].first()
            ax.plot(baseline.index, baseline, linestyle="--", label="Top-2 baseline 2024")
    ax.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=1)
    ax.set(title="Issue #334 — selected neural residual vs frozen Top-2", xlabel="Issue order", ylabel="Capital (CNY)")
    ax.legend()
    fig.tight_layout()
    path = figure_dir / "issue_334_neural_top2_capital.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    output.append(path)

    anchor = capital[
        capital["model"].eq(anchor_model)
        & capital["arm"].isin(["S0O1_SUPPORT", "S0O1_ALLOC", "S0O1"])
    ].copy()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for axis, year in zip(axes, (DEVELOPMENT_YEAR, TERMINAL_YEAR), strict=True):
        local = anchor[anchor["issue_year"].eq(year)]
        for component_arm, group in local.groupby("arm"):
            axis.plot(group["issue_order"], group["capital_cny"], label=component_arm)
        baseline = local.groupby("issue_order")["baseline_capital_cny"].first()
        axis.plot(baseline.index, baseline, color="black", linestyle="--", label="S0O0 baseline")
        axis.axhline(STARTING_CAPITAL_CNY, color="grey", linewidth=1)
        axis.set_title(str(year))
        axis.set_xlabel("Issue order")
    axes[0].set_ylabel("Capital (CNY)")
    axes[1].legend(fontsize=8)
    fig.suptitle("Value-anchor support and allocation capital paths")
    fig.tight_layout()
    path = figure_dir / "issue_334_anchor_component_capital.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    output.append(path)

    subset = performance[
        performance["issue_year"].eq(TERMINAL_YEAR)
        & (
            performance["model"].eq(model)
            | performance["model"].eq("LINEAR")
            | performance["model"].eq(anchor_model)
            | performance["model"].str.contains("LABEL_SHUFFLED")
        )
    ].copy()
    chart = subset.groupby(["model", "arm"], as_index=False)["matched_lift_cny"].median()
    chart["lane"] = chart["model"] + "/" + chart["arm"]
    chart = chart.sort_values("matched_lift_cny")
    fig, ax = plt.subplots(figsize=(12, max(5, len(chart) * 0.3)))
    ax.barh(chart["lane"], chart["matched_lift_cny"])
    ax.axvline(0, color="black", linewidth=1)
    ax.set(title="Frozen 2024 matched lift vs Top-2", xlabel="Median matched lift (CNY)")
    fig.tight_layout()
    path = figure_dir / "issue_334_neural_top2_lift.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    output.append(path)

    grouped = factorial.groupby("issue_year")[["selection_main_cny", "outcome_allocation_main_cny", "interaction_cny"]].median()
    fig, ax = plt.subplots(figsize=(9, 5))
    grouped.plot(kind="bar", ax=ax)
    ax.axhline(0, color="black", linewidth=1)
    ax.set(title="Neural selection × outcome/allocation attribution", ylabel="Median effect (CNY)")
    fig.tight_layout()
    path = figure_dir / "issue_334_neural_top2_factorial.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    output.append(path)
    return output


def _anchor_components(performance: pd.DataFrame, model: str) -> pd.DataFrame:
    frame = performance[performance["model"].eq(model)].copy()
    return frame[
        frame["arm"].isin(["S0O0", "S0O1_SUPPORT", "S0O1_ALLOC", "S0O1"])
    ][
        [
            "model",
            "arm",
            "issue_year",
            "issues",
            "pnl_cny",
            "matched_lift_cny",
            "ex_largest_lift_cny",
            "payout_issues",
            "ticket_hhi_mean",
        ]
    ].sort_values(["issue_year", "arm"])


def _report(
    decision,
    receipt,
    performance,
    risk,
    factorial,
    anchor_components,
    diagnostics,
    bootstrap,
) -> str:
    chosen = performance[
        performance["model"].eq(decision["selected_model"])
        & performance["arm"].eq(decision["selected_arm"])
    ]
    summary = chosen.groupby("issue_year", as_index=False).agg(
        seeds=("seed", "nunique"),
        issues=("issues", "median"),
        median_pnl_cny=("pnl_cny", "median"),
        median_lift_cny=("matched_lift_cny", "median"),
        median_ex_largest_lift_cny=("ex_largest_lift_cny", "median"),
        median_ending_capital_cny=("ending_capital_cny", "median"),
    )
    factor = factorial.groupby("issue_year", as_index=False).median(numeric_only=True)
    diag = diagnostics[
        diagnostics["model"].isin(
            [
                "BASELINE",
                "LINEAR",
                decision["selected_model"],
                decision["selected_anchor_control"],
            ]
        )
    ].groupby(["model", "issue_year"], as_index=False).median(numeric_only=True)
    risk_summary = risk[
        risk["model"].eq(decision["selected_model"])
        & risk["arm"].eq(decision["selected_arm"])
    ].groupby("issue_year", as_index=False).median(numeric_only=True)
    boot = bootstrap.groupby(["candidate", "issue_year"], as_index=False).median(numeric_only=True)
    return f"""# Issue #334 — Neural Top-2 residual action-value learner

## Five-minute decision summary

- Frozen fallback: #319 `P_TOP2_NO_GATE`, N7, 128 distinct tickets funded to 512 CNY2 units.
- Selected on 2023 only: `{decision['selected_model']}` / `{decision['selected_arm']}`.
- Frozen 2024 median lift: CNY {decision['terminal_median_lift_cny']:.2f}; ex-largest: CNY {decision['terminal_median_ex_largest_lift_cny']:.2f}.
- Interpretable anchor control: `{decision['selected_anchor_control']}`; 2024 lift CNY {decision['anchor_terminal_lift_cny']:.2f}, ex-largest CNY {decision['anchor_terminal_ex_largest_lift_cny']:.2f}.
- Decision: **{decision['disposition']}**; promotion={str(decision['promotion']).lower()}; #210 unlock={str(decision['unlock_210']).lower()}.
- The cell target is `result indicator × official winning SP`; 0.65 is applied once only when a complete N7 ticket wins.

## Scientific design

2020–2022 fit the anchored residual models, 2023 selects architecture and S/O arm, and 2024 is read once as the terminal historical transfer. All resampling is issue-clustered. The neural model changes match selection, outcome support and within-support ticket funding only through named factorial arms; the exact Top-2 baseline remains reproducible.

Source coverage: {receipt['issues']} issues, {receipt['matches']} matches and {receipt['cells']} M×3 cells over {receipt['years']}.

## Selected-policy performance

```
{summary.to_string(index=False)}
```

## Selection × outcome/allocation attribution

```
{factor.to_string(index=False)}
```

## Value-anchor support vs allocation decomposition

`S0O1_SUPPORT` changes only which two outcomes are retained; `S0O1_ALLOC` keeps the market Top-2 support and changes only ticket funding; `S0O1` combines both.

```
{anchor_components.to_string(index=False)}
```

## Risk and holding path

```
{risk_summary.to_string(index=False)}
```

## Model diagnostics

```
{diag.to_string(index=False)}
```

## Issue-cluster bootstrap

```
{boot.to_string(index=False)}
```

## PI adversarial interpretation

1. A lower Brier score is not sufficient: promotion is decided only by matched payout value on frozen 2024.
2. The factorial table separates match selection, outcome/allocation and their interaction; a joint headline is not accepted without this attribution.
3. Ex-largest and shuffled-label controls test jackpot concentration and spurious model identity.
4. The anchored linear control asks whether neural capacity contributes beyond a simpler residual model.
5. The baseline remains the deployment fallback regardless of this exploratory result.

![Capital path](figures/issue_334_neural_top2_capital.png)

![Terminal lift](figures/issue_334_neural_top2_lift.png)

![Factorial attribution](figures/issue_334_neural_top2_factorial.png)

![Value-anchor component paths](figures/issue_334_anchor_component_capital.png)
"""


def _notebook(repo_root: Path, notebook_path: Path) -> None:
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    relative_root = "../../.."
    cells = [
        nbformat.v4.new_markdown_cell(
            "# Issue #334 neural Top-2 residual learner\n\nExecuted decision notebook. The Python package is the source of computation; this notebook exposes completeness, diagnostics and capital attribution."
        ),
        nbformat.v4.new_code_cell(
            f"from pathlib import Path\nimport json, pandas as pd\nROOT = Path('{relative_root}').resolve()\nOUT = ROOT / 'results/neural_top2_residual'\njson.loads((OUT / 'decision.json').read_text())"
        ),
        nbformat.v4.new_code_cell(
            "pd.read_csv(OUT / 'cell_coverage.csv')"
        ),
        nbformat.v4.new_code_cell(
            "pd.read_csv(OUT / 'model_diagnostics.csv').groupby(['model','issue_year']).median(numeric_only=True)[['brier','log_loss','value_mae']]"
        ),
        nbformat.v4.new_code_cell(
            "pd.read_csv(OUT / 'performance.csv').groupby(['model','arm','issue_year']).median(numeric_only=True)[['pnl_cny','matched_lift_cny','ex_largest_lift_cny','ending_capital_cny']]"
        ),
        nbformat.v4.new_code_cell(
            "pd.read_csv(OUT / 'factorial_attribution.csv').groupby('issue_year').median(numeric_only=True)"
        ),
        nbformat.v4.new_code_cell(
            "pd.read_csv(OUT / 'risk_diagnostics.csv').groupby(['model','arm','issue_year']).median(numeric_only=True)[['max_drawdown_fraction','max_consecutive_losing_issues','worst_rolling_10_cny','max_recovery_issues']]"
        ),
    ]
    notebook = nbformat.v4.new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}})
    nbformat.write(notebook, notebook_path)
    client = NotebookClient(notebook, timeout=180, kernel_name="python3", resources={"metadata": {"path": str(notebook_path.parent)}})
    executed = client.execute()
    nbformat.write(executed, notebook_path)


def _manifest(output_dir: Path, receipt, decision, figures, report, notebook) -> None:
    local_cache = {
        "candidate_predictions.parquet",
        "shuffled_predictions.parquet",
        "cell_panel.parquet",
        "tickets.parquet",
    }
    payload_files = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name not in {"MANIFEST.json", "SHA256SUMS.json"}
        and path.name not in local_cache
    )
    hashes = {path.name: _sha256(path) for path in payload_files}
    _write_json(output_dir / "SHA256SUMS.json", hashes)
    _write_json(
        output_dir / "MANIFEST.json",
        {
            "issue": 334,
            "contract": "BJ-UNIFIED-NEURAL-TOP2-RESIDUAL-001",
            "source_receipt_sha256": hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest(),
            "decision": decision,
            "payload_hashes": hashes,
            "report": str(report.relative_to(report.parents[2])),
            "notebook": str(notebook.relative_to(notebook.parents[3])),
            "figures": [str(path.name) for path in figures],
            "local_rebuild_cache_excluded_from_git": sorted(local_cache),
        },
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
