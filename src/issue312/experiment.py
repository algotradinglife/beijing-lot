"""Terminal 2023 experiment and decision package for Issue #312."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .evaluation import (
    add_oracle_allocation,
    aggregate_summary,
    evaluate,
    factor_attribution,
    physical_permutation,
)
from .surface import aggregate_action_labels


def run_experiment(output: str | Path) -> dict[str, object]:
    output = Path(output)
    allocations = pd.read_csv(
        output / "pre2023_policy_allocations.csv", dtype={"issue": str}
    )
    ledger = pd.read_parquet(output / "evaluation_seed_action_ledger_2023.parquet")
    allocations = add_oracle_allocation(allocations, ledger)
    paths, seed_summary = evaluate(allocations, ledger)
    summary = aggregate_summary(seed_summary)
    paths.to_csv(output / "capital_paths.csv", index=False)
    seed_summary.to_csv(output / "policy_summary_by_seed.csv", index=False)
    summary.to_csv(output / "policy_summary.csv", index=False)
    attribution = factor_attribution(paths)
    attribution.to_csv(output / "factor_attribution.csv", index=False)
    primary_allocations = allocations[allocations["condition"].eq("JOINT_PRIMARY")]
    permutation = physical_permutation(primary_allocations, ledger)
    permutation.to_csv(output / "same_exposure_permutation_2023.csv", index=False)
    parameter_distribution = primary_allocations.groupby(
        [
            "n",
            "k",
            "match_selector",
            "pool_excess",
            "outcome_direction",
            "generator",
            "protection",
        ],
        as_index=False,
    ).agg(issues=("issue", "nunique"), allocated_tickets=("allocated_tickets", "sum"))
    parameter_distribution.to_csv(output / "primary_parameter_distribution.csv", index=False)
    diagnostics = _model_diagnostics(output, allocations, ledger)
    diagnostics["prediction"].to_csv(
        output / "prediction_diagnostics_2023.csv", index=False
    )
    diagnostics["transfer"].to_csv(
        output / "static_rank_transfer.csv", index=False
    )
    diagnostics["factor"].to_csv(
        output / "realized_factor_marginals_2023.csv", index=False
    )
    diagnostics["rows"].to_csv(
        output / "prediction_realized_2023.csv", index=False
    )
    baseline = _exact_b0_reference(output)
    baseline.to_csv(output / "exact_b0_reference_2023.csv", index=False)
    _plot_capital(paths, output / "capital_paths_2023.png")
    _plot_frontier(summary, output / "risk_tail_frontier_2023.png")
    _plot_parameters(primary_allocations, output / "primary_parameter_distribution.png")
    _plot_prediction_transfer(
        diagnostics["rows"], output / "prediction_vs_realized_2023.png"
    )

    primary = _row(summary, "JOINT_PRIMARY")
    issue306 = _row(summary, "ISSUE306_PRIMARY")
    control_conditions = ["FIXED_N7_K512_WOR", "BEST_STATIC_ACTION"]
    controls = summary[summary["condition"].isin(control_conditions)]
    strongest = controls.sort_values("median_terminal_capital_cny", ascending=False).iloc[0]
    observed = float(primary["median_terminal_capital_cny"])
    percentile = float(
        (permutation["median_terminal_capital_cny"] <= observed).mean()
    )
    seed_pivot = seed_summary[
        seed_summary["condition"].isin(["JOINT_PRIMARY", *control_conditions])
    ].pivot(index="seed", columns="condition", values="terminal_capital_cny")
    paired_control = seed_pivot[control_conditions].max(axis=1)
    paired_wins = int((seed_pivot["JOINT_PRIMARY"] > paired_control).sum())
    required_seed_wins = math.ceil(0.60 * len(seed_pivot))
    beats_controls = observed > float(strongest["median_terminal_capital_cny"])
    ex_largest_not_worse = float(primary["median_ex_largest_pnl_cny"]) >= float(
        strongest["median_ex_largest_pnl_cny"]
    )
    joint_signal = bool(
        beats_controls
        and percentile >= 0.95
        and paired_wins >= required_seed_wins
        and ex_largest_not_worse
    )
    factor_signal = bool(
        beats_controls
        and (
            attribution["median_seed_lift_cny"].gt(0)
            & attribution["positive_seed_fraction"].ge(0.50)
        ).any()
    )
    candidate_signal = bool(
        joint_signal
        and observed > 100_000.0
        and float(primary["median_ex_largest_pnl_cny"]) > 0
    )
    verdict = (
        "CANDIDATE_SIGNAL"
        if candidate_signal
        else "JOINT_ACTION_SIGNAL"
        if joint_signal
        else "FACTOR_SIGNAL"
        if factor_signal
        else "NO_INCREMENT"
    )
    fit_receipts = pd.read_csv(output / "pre2023_fit_receipts.csv")
    decision = {
        "verdict": verdict,
        "promotable": candidate_signal,
        "eligible_issue_policy": "ALL_ISSUES_ACTIVE_NO_LEARNED_SKIP",
        "committed_tickets_per_issue": 512,
        "committed_stake_per_issue_cny": 1024.0,
        "evaluation_physical_seeds": int(ledger["seed"].nunique()),
        "primary_2023_median_terminal_capital_cny": observed,
        "primary_2023_median_growth_pct": float(primary["median_capital_growth_pct"]),
        "primary_2023_median_turnover_roi_pct": float(primary["median_turnover_roi_pct"]),
        "primary_2023_median_max_drawdown_pct": float(primary["median_max_drawdown_pct"]),
        "primary_2023_median_ex_largest_pnl_cny": float(
            primary["median_ex_largest_pnl_cny"]
        ),
        "issue306_2023_median_terminal_capital_cny": float(
            issue306["median_terminal_capital_cny"]
        ),
        "issue306_role": "INTERFACE_ONLY_SECONDARY_COMPARATOR",
        "exact_b0_reference_terminal_capital_cny": float(
            baseline.iloc[0]["terminal_capital_cny"]
        ),
        "exact_b0_reference_turnover_roi_pct": float(
            baseline.iloc[0]["turnover_roi_pct"]
        ),
        "exact_b0_reference_matched_budget_translation": "UNAVAILABLE_NO_COMMITTED_TICKET_IDENTITIES",
        "strongest_control": str(strongest["condition"]),
        "strongest_control_median_terminal_capital_cny": float(
            strongest["median_terminal_capital_cny"]
        ),
        "matched_lift_vs_strongest_control_cny": observed
        - float(strongest["median_terminal_capital_cny"]),
        "same_exposure_permutation_percentile": percentile,
        "paired_seed_wins_vs_strongest_control": paired_wins,
        "paired_seed_win_requirement": required_seed_wins,
        "ex_largest_not_worse_than_strongest_fixed_static": ex_largest_not_worse,
        "primary_fits_converged": bool(
            fit_receipts.loc[fit_receipts["condition"].eq("LEARNED"), "converged"].all()
        ),
        "predicted_mean_roi_pooled_spearman": float(
            diagnostics["prediction"].loc[
                diagnostics["prediction"]["target"].eq("mean_roi"),
                "pooled_spearman",
            ].iloc[0]
        ),
        "static_action_rank_transfer_spearman": float(
            diagnostics["transfer"].iloc[0]["development_vs_2023_spearman"]
        ),
        "sealed_years": "2024+ not read",
    }
    payload = {
        "issue": 312,
        "question": "explicit within-issue selector, outcome and protection joint action value",
        "decision": decision,
    }
    (output / "decision.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_manifest(output)
    return payload


def _model_diagnostics(
    output: Path, allocations: pd.DataFrame, ledger: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    """Diagnose whether learned action scores transfer without changing the verdict."""

    actual = aggregate_action_labels(ledger)
    predictions = pd.read_parquet(output / "pre2023_action_predictions.parquet")
    predictions = predictions[predictions["condition"].eq("LEARNED")].copy()
    columns = [
        "issue",
        "action_key",
        "predicted_mean_roi",
        "predicted_positive_probability",
        "predicted_tail_5x_probability",
    ]
    rows = predictions[columns].merge(
        actual[
            [
                "issue",
                "action_key",
                "mean_roi",
                "positive_probability",
                "tail_5x_probability",
            ]
        ],
        on=["issue", "action_key"],
        validate="one_to_one",
    )
    primary = allocations[allocations["condition"].eq("JOINT_PRIMARY")][
        ["issue", "action_key"]
    ].assign(selected_primary=True)
    rows = rows.merge(primary, on=["issue", "action_key"], how="left")
    rows["selected_primary"] = rows["selected_primary"].fillna(False).astype(bool)
    diagnostics = []
    for target, prediction in (
        ("mean_roi", "predicted_mean_roi"),
        ("positive_probability", "predicted_positive_probability"),
        ("tail_5x_probability", "predicted_tail_5x_probability"),
    ):
        within = []
        for _, group in rows.groupby("issue"):
            correlation = group[prediction].corr(group[target], method="spearman")
            if pd.notna(correlation):
                within.append(float(correlation))
        diagnostics.append(
            {
                "target": target,
                "rows": len(rows),
                "issues": rows["issue"].nunique(),
                "pooled_spearman": rows[prediction].corr(rows[target], method="spearman"),
                "median_within_issue_spearman": float(np.median(within)),
                "positive_within_issue_fraction": float(np.mean(np.array(within) > 0)),
            }
        )
    development = pd.read_parquet(output / "development_action_labels.parquet")
    development = development[development["issue_year"].isin((2021, 2022))]
    dev_rank = development.groupby("action_key", as_index=False).agg(
        development_mean_roi=("mean_roi", "mean"),
        development_issues=("issue", "nunique"),
    )
    test_rank = actual.groupby("action_key", as_index=False).agg(
        evaluation_mean_roi=("mean_roi", "mean"),
        evaluation_issues=("issue", "nunique"),
    )
    transfer_rows = dev_rank.merge(test_rank, on="action_key", validate="one_to_one")
    transfer = pd.DataFrame(
        [
            {
                "actions": len(transfer_rows),
                "development_vs_2023_spearman": transfer_rows[
                    "development_mean_roi"
                ].corr(transfer_rows["evaluation_mean_roi"], method="spearman"),
                "development_top_action": str(
                    transfer_rows.sort_values("development_mean_roi", ascending=False)
                    .iloc[0]["action_key"]
                ),
                "development_top_2023_mean_roi": float(
                    transfer_rows.sort_values("development_mean_roi", ascending=False)
                    .iloc[0]["evaluation_mean_roi"]
                ),
                "evaluation_top_action": str(
                    transfer_rows.sort_values("evaluation_mean_roi", ascending=False)
                    .iloc[0]["action_key"]
                ),
                "evaluation_top_mean_roi": float(
                    transfer_rows["evaluation_mean_roi"].max()
                ),
            }
        ]
    )
    factors = []
    for factor in (
        "n",
        "k",
        "match_selector",
        "pool_excess",
        "outcome_direction",
        "generator",
        "protection",
    ):
        for level, group in actual.groupby(factor, dropna=False):
            factors.append(
                {
                    "factor": factor,
                    "level": level,
                    "issue_action_rows": len(group),
                    "actions": group["action_key"].nunique(),
                    "mean_realized_roi": group["mean_roi"].mean(),
                    "median_realized_roi": group["mean_roi"].median(),
                    "positive_issue_action_fraction": group["mean_roi"].gt(0).mean(),
                    "mean_tail_5x_probability": group["tail_5x_probability"].mean(),
                }
            )
    return {
        "prediction": pd.DataFrame(diagnostics),
        "transfer": transfer,
        "factor": pd.DataFrame(factors),
        "rows": rows,
    }


def _plot_prediction_transfer(rows: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(
        rows["predicted_mean_roi"],
        rows["mean_roi"],
        s=np.where(rows["selected_primary"], 28, 8),
        alpha=np.where(rows["selected_primary"], 0.9, 0.25),
    )
    ax.axhline(0, color="black", lw=0.8)
    ax.set(
        title="#312 predicted vs realized action ROI (2023)",
        xlabel="pre-outcome predicted mean ROI",
        ylabel="31-seed realized mean ROI",
    )
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _exact_b0_reference(output: Path) -> pd.DataFrame:
    """Load exact inherited one-bundle economics on the frozen common support."""

    root = output.parents[1]
    support = pd.read_csv(root / "results/issue-299/support_receipt.csv", dtype={"issue": str})
    common = set(
        support.loc[
            support["support_status"].eq("MATCHED_BASELINE_AND_FEATURES")
            & support["issue_year"].eq(2023),
            "issue",
        ]
    )
    ledger = pd.read_csv(root / "results/issue-302/action_ledger.csv", dtype={"issue": str})
    b0 = ledger[
        ledger["action_id"].eq("B0_BEST_FULL")
        & ledger["issue_year"].eq(2023)
        & ledger["issue"].isin(common)
    ].copy()
    if set(b0["issue"]) != common:
        raise AssertionError("exact B0 reference does not match frozen common support")
    stake = float(b0["stake_unit_cny"].sum())
    pnl = float(b0["pnl_unit_cny"].sum())
    return pd.DataFrame(
        [
            {
                "condition": "EXACT_B0_BEST_FULL_ONE_BUNDLE",
                "issues": len(common),
                "stake_cny": stake,
                "pnl_cny": pnl,
                "terminal_capital_cny": 100_000.0 + pnl,
                "turnover_roi_pct": 100.0 * pnl / stake,
                "matched_budget_translation": "UNAVAILABLE_NO_COMMITTED_TICKET_IDENTITIES",
            }
        ]
    )


def _row(summary: pd.DataFrame, condition: str) -> dict[str, object]:
    return summary[summary["condition"].eq(condition)].iloc[0].to_dict()


def _plot_capital(paths: pd.DataFrame, target: Path) -> None:
    focus = [
        "JOINT_PRIMARY",
        "ISSUE306_PRIMARY",
        "FIXED_N7_K512_WOR",
        "ABLATE_SELECTOR",
        "ABLATE_OUTCOME",
        "ABLATE_PROTECTION",
    ]
    fig, ax = plt.subplots(figsize=(11, 6))
    for condition in focus:
        local = (
            paths[paths["condition"].eq(condition)]
            .groupby("issue", as_index=False)["pnl_cny"]
            .median()
            .sort_values("issue")
        )
        ax.plot(range(len(local)), 100_000 + local["pnl_cny"].cumsum(), label=condition)
    ax.axhline(100_000, color="black", lw=0.8)
    ax.set(
        title="#312 fixed-exposure 2023 capital paths",
        xlabel="issue order",
        ylabel="median physical-seed capital (CNY)",
    )
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_frontier(summary: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(
        summary["median_max_drawdown_pct"],
        summary["median_capital_growth_pct"],
        s=50 + 1000 * summary["median_tail_5x_rate"],
    )
    for row in summary.itertuples(index=False):
        ax.annotate(
            row.condition,
            (row.median_max_drawdown_pct, row.median_capital_growth_pct),
            fontsize=7,
        )
    ax.axhline(0, color="black", lw=0.8)
    ax.set(
        title="#312 risk/tail frontier (size = 5x-tail rate)",
        xlabel="median max drawdown (%)",
        ylabel="median capital growth (%)",
    )
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_parameters(allocations: pd.DataFrame, target: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, column in zip(axes, ("n", "match_selector", "protection"), strict=True):
        allocations[column].astype(str).value_counts().sort_index().plot.bar(ax=ax)
        ax.set(title=column, ylabel="issues")
        ax.tick_params(axis="x", labelrotation=60)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def write_manifest(output: Path) -> None:
    """Inventory committed-size deliverables, never local physical caches."""

    files = {}
    for path in sorted(output.iterdir()):
        if (
            path.name == "manifest.json"
            or not path.is_file()
            or path.suffix not in {".csv", ".json", ".parquet", ".png"}
        ):
            continue
        files[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    payload = {"issue": 312, "files": files, "excluded_local_caches": []}
    (output / "manifest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
