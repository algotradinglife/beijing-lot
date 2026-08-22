"""Run the Issue #306 fixed-coverage dynamic ticket-composition experiment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from issue306.evaluation import (
    COMMITTED_TICKETS,
    INITIAL_CAPITAL_CNY,
    evaluate_allocations,
    fixed_allocations,
    learned_allocations,
    summarize_paths,
)
from issue306.model import add_policy_scores, fit_predict_expanding

PREDICTION_YEARS = (2021, 2022, 2023)
LEARNED_CANDIDATES = (
    "LEARNED_MEAN_DETERMINISTIC",
    "LEARNED_TAIL_DETERMINISTIC",
    "LEARNED_TAIL_MIXTURE",
)


def run_experiment(
    root: str | Path,
    output: str | Path,
    *,
    reuse_fit_cache: bool = False,
) -> dict[str, object]:
    root, output = Path(root), Path(output)
    ledger = pd.read_parquet(output / "seed_action_ledger.parquet")
    labels = pd.read_parquet(output / "action_labels.parquet")
    states = pd.read_csv(root / "results/issue-209/dynamic_issue_states.csv", dtype={"issue": str})
    states = states[states["issue_year"].between(2019, 2023)]
    if states["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")

    cache_paths = (
        output / "action_value_predictions.parquet",
        output / "seed_action_value_predictions.parquet",
        output / "fit_receipts.csv",
    )
    if reuse_fit_cache:
        if not all(path.exists() for path in cache_paths):
            raise FileNotFoundError("fit cache is incomplete")
        scores = pd.read_parquet(cache_paths[0])
        receipts = pd.read_csv(cache_paths[2])
    else:
        score_frames = []
        seed_frames = []
        receipt_frames = []
        for condition in ["LEARNED", "ISSUE_BLOCK_SHUFFLED", "IDENTITY_SHUFFLED"]:
            scores, seeds, receipts = fit_predict_expanding(
                states, labels, condition=condition
            )
            score_frames.append(add_policy_scores(scores))
            seed_frames.append(seeds)
            receipt_frames.append(receipts)
        scores = pd.concat(score_frames, ignore_index=True)
        scores.to_parquet(cache_paths[0], index=False)
        pd.concat(seed_frames, ignore_index=True).to_parquet(
            cache_paths[1], index=False
        )
        receipts = pd.concat(receipt_frames, ignore_index=True)
        receipts.to_csv(cache_paths[2], index=False)

    allocations: list[pd.DataFrame] = []
    for year in PREDICTION_YEARS:
        local_states = states[states["issue_year"].eq(year)]
        learned = scores[scores["issue_year"].eq(year) & scores["condition"].eq("LEARNED")]
        shuffled = scores[
            scores["issue_year"].eq(year)
            & scores["condition"].eq("ISSUE_BLOCK_SHUFFLED")
        ]
        identity = scores[
            scores["issue_year"].eq(year)
            & scores["condition"].eq("IDENTITY_SHUFFLED")
        ]
        allocations.extend(
            [
                learned_allocations(
                    learned,
                    condition="LEARNED_MEAN_DETERMINISTIC",
                    score_column="mean_score",
                    mixture=False,
                ),
                learned_allocations(
                    learned,
                    condition="LEARNED_TAIL_DETERMINISTIC",
                    score_column="tail_score",
                    mixture=False,
                ),
                learned_allocations(
                    learned,
                    condition="LEARNED_TAIL_MIXTURE",
                    score_column="tail_score",
                    mixture=True,
                ),
                learned_allocations(
                    shuffled,
                    condition="ISSUE_BLOCK_SHUFFLED",
                    score_column="tail_score",
                    mixture=True,
                ),
                learned_allocations(
                    identity,
                    condition="IDENTITY_SHUFFLED",
                    score_column="tail_score",
                    mixture=True,
                ),
            ]
        )
        static_scores = _static_scores(labels, learned, year)
        allocations.extend(
            [
                learned_allocations(
                    static_scores,
                    condition="BEST_STATIC_ACTION",
                    score_column="mean_score",
                    mixture=False,
                ),
                learned_allocations(
                    static_scores,
                    condition="STATIC_TAIL_MIXTURE",
                    score_column="tail_score",
                    mixture=True,
                ),
                _oracle_allocations(labels[labels["issue_year"].eq(year)]),
            ]
        )
        for generator in ["TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR"]:
            allocations.append(
                fixed_allocations(
                    local_states,
                    action_key=f"N7_K512_{generator}",
                    n=7,
                    k=512,
                    generator=generator,
                    condition=f"FIXED_N7_K512_{generator}",
                )
            )
    allocation_frame = pd.concat(allocations, ignore_index=True)
    allocation_frame.to_csv(output / "policy_allocations.csv", index=False)
    paths = evaluate_allocations(allocation_frame, ledger)
    paths.to_csv(output / "capital_paths.csv", index=False)
    summary = summarize_paths(paths)
    summary.to_csv(output / "policy_summary_by_seed.csv", index=False)
    aggregate_summary = _aggregate_summary(summary)
    aggregate_summary.to_csv(output / "policy_summary.csv", index=False)
    action_distribution = allocation_frame.groupby(
        ["condition", "issue_year", "n", "k", "generator"], as_index=False
    ).agg(
        issues=("issue", "nunique"),
        action_rows=("action_key", "size"),
        allocated_tickets=("allocated_tickets", "sum"),
    )
    action_distribution.to_csv(output / "action_distribution.csv", index=False)
    development_primary, development_scores = _development_selected_policy(paths)
    _action_dependence(
        allocation_frame, ledger, condition=development_primary
    ).to_csv(
        output / "selected_action_dependence.csv", index=False
    )

    permutation_frames = []
    for condition in LEARNED_CANDIDATES:
        local_allocations = allocation_frame[
            allocation_frame["condition"].eq(condition)
            & allocation_frame["issue_year"].eq(2023)
        ]
        local = _permutation_control(
            local_allocations,
            ledger[ledger["issue_year"].eq(2023)],
        )
        local.insert(0, "condition", condition)
        permutation_frames.append(local)
    permutation = pd.concat(permutation_frames, ignore_index=True)
    permutation.to_csv(output / "same_exposure_permutation_2023.csv", index=False)
    _plot_capital(paths, output / "capital_paths_2023.png", primary=development_primary)
    _plot_frontier(aggregate_summary, output / "tail_risk_frontier_2023.png")
    _plot_actions(
        action_distribution,
        output / "learned_action_distribution.png",
        primary=development_primary,
    )

    primary = _row(aggregate_summary, development_primary, 2023)
    tail_diagnostic = _row(
        aggregate_summary, "LEARNED_TAIL_DETERMINISTIC", 2023
    )
    static = _row(aggregate_summary, "STATIC_TAIL_MIXTURE", 2023)
    fixed_rows = aggregate_summary[
        aggregate_summary["evaluation_year"].eq(2023)
        & aggregate_summary["condition"].str.startswith("FIXED_N7_K512")
    ]
    best_fixed = fixed_rows.sort_values("median_terminal_capital_cny", ascending=False).iloc[0]
    observed = primary["median_terminal_capital_cny"]
    primary_permutation = permutation[
        permutation["condition"].eq(development_primary)
    ]
    percentile = float(
        (primary_permutation["median_terminal_capital_cny"] <= observed).mean()
    )
    tail_percentile = float(
        (
            permutation.loc[
                permutation["condition"].eq("LEARNED_TAIL_DETERMINISTIC"),
                "median_terminal_capital_cny",
            ]
            <= tail_diagnostic["median_terminal_capital_cny"]
        ).mean()
    )
    seed_rows = summary[
        summary["condition"].eq(development_primary)
        & summary["evaluation_year"].eq(2023)
    ]
    comparator_terminal = max(
        float(static["median_terminal_capital_cny"]),
        float(best_fixed["median_terminal_capital_cny"]),
    )
    comparator_conditions = [
        "STATIC_TAIL_MIXTURE",
        str(best_fixed["condition"]),
    ]
    comparator_by_seed = (
        summary[
            summary["condition"].isin(comparator_conditions)
            & summary["evaluation_year"].eq(2023)
        ]
        .groupby("seed")["terminal_capital_cny"]
        .max()
    )
    primary_by_seed = seed_rows.set_index("seed")["terminal_capital_cny"]
    paired_seed_wins = int((primary_by_seed > comparator_by_seed).sum())
    primary_fits_converged = bool(
        receipts.loc[receipts["condition"].eq("LEARNED"), "converged"].all()
    )
    action_value_signal = bool(
        observed > comparator_terminal and percentile >= 0.95
    )
    dynamic_signal = bool(
        action_value_signal
        and primary["median_ex_largest_pnl_cny"] > 0
        and paired_seed_wins >= 3
        and primary_fits_converged
    )
    verdict = (
        "DYNAMIC_TICKET_SIGNAL"
        if dynamic_signal
        else "ACTION_VALUE_SIGNAL"
        if action_value_signal
        else "INTERFACE_ONLY"
    )
    decision = {
        "verdict": verdict,
        "promotable": False,
        "development_signal": action_value_signal,
        "dynamic_ticket_signal": dynamic_signal,
        "eligible_issue_policy": "ALL_ISSUES_ACTIVE_NO_LEARNED_SKIP",
        "committed_tickets_per_issue": COMMITTED_TICKETS,
        "committed_stake_per_issue_cny": 1_024.0,
        "development_selected_primary": development_primary,
        "development_selection_metric": "median cumulative 2021-2022 physical PnL across nuisance seeds",
        "development_candidate_pnl_cny": development_scores,
        "primary_2023_median_terminal_capital_cny": observed,
        "primary_2023_median_growth_pct": primary["median_capital_growth_pct"],
        "primary_2023_median_turnover_roi_pct": primary["median_turnover_roi_pct"],
        "primary_2023_median_max_drawdown_pct": primary["median_max_drawdown_pct"],
        "primary_2023_median_tail_5x_rate": primary["median_tail_5x_rate"],
        "static_mixture_2023_median_terminal_capital_cny": static["median_terminal_capital_cny"],
        "best_fixed_2023_condition": str(best_fixed["condition"]),
        "best_fixed_2023_median_terminal_capital_cny": float(best_fixed["median_terminal_capital_cny"]),
        "matched_lift_vs_strongest_control_cny": observed - comparator_terminal,
        "same_exposure_permutation_percentile": percentile,
        "positive_vs_strongest_control_nuisance_seeds": paired_seed_wins,
        "primary_model_fits_converged": primary_fits_converged,
        "all_model_and_control_fits_converged": bool(receipts["converged"].all()),
        "tail_diagnostic_2023_median_terminal_capital_cny": tail_diagnostic[
            "median_terminal_capital_cny"
        ],
        "tail_diagnostic_2023_permutation_percentile": tail_percentile,
        "tail_diagnostic_status": "SECONDARY_PREDECLARED_HEAD_NOT_DEVELOPMENT_SELECTED",
        "sealed_years": "2024+ not read",
    }
    payload = {
        "issue": 306,
        "question": "within-issue ticket construction at fixed issue coverage and exposure",
        "decision": decision,
    }
    (output / "decision.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_manifest(output)
    return payload


def _static_scores(labels: pd.DataFrame, template: pd.DataFrame, year: int) -> pd.DataFrame:
    train = labels[labels["issue_year"].lt(year)]
    metrics = train.groupby(["action_key", "n", "k", "generator"], as_index=False).agg(
        predicted_mean_roi=("mean_roi", "mean"),
        predicted_positive_probability=("positive_probability", "mean"),
        predicted_tail_5x_probability=("tail_5x_probability", "mean"),
        predicted_mean_downside_roi=("mean_downside_roi", "mean"),
        predicted_conditional_log_gross=("conditional_log_gross", "mean"),
        predicted_mean_roi_std=("mean_roi", "std"),
    )
    support = template[["issue", "issue_year", "action_key", "n", "k", "generator", "effective_k"]]
    result = support.merge(metrics, on=["action_key", "n", "k", "generator"], validate="many_to_one")
    return add_policy_scores(result)


def _oracle_allocations(labels: pd.DataFrame) -> pd.DataFrame:
    oracle = labels.copy()
    oracle["oracle_score"] = oracle["mean_pnl_cny"] * COMMITTED_TICKETS / oracle["k"]
    oracle["mean_score"] = oracle["oracle_score"]
    return learned_allocations(
        oracle,
        condition="ORACLE_DIAGNOSTIC",
        score_column="mean_score",
        mixture=False,
    )


def _aggregate_summary(summary: pd.DataFrame) -> pd.DataFrame:
    value_columns = [
        "terminal_capital_cny",
        "capital_growth_pct",
        "turnover_roi_pct",
        "max_drawdown_pct",
        "longest_losing_issue_streak",
        "longest_no_payout_streak",
        "ex_largest_pnl_cny",
        "positive_issue_rate",
        "any_payout_rate",
        "tail_2x_rate",
        "tail_5x_rate",
        "tail_10x_rate",
        "rolling_5_tail_capture_probability",
        "rolling_10_tail_capture_probability",
        "rolling_20_tail_capture_probability",
        "mean_distinct_actions",
        "worst_rolling_5_pnl_cny",
        "worst_rolling_10_pnl_cny",
        "worst_rolling_20_pnl_cny",
        "maximum_completed_recovery_issues",
        "open_terminal_underwater_issues",
    ]
    grouped = summary.groupby(["condition", "evaluation_year"], as_index=False)
    result = grouped.agg(
        nuisance_seeds=("seed", "nunique"),
        issues=("issues", "first"),
        stake_cny=("stake_cny", "mean"),
        ruin_seed_rate=("ruin", "mean"),
    )
    for column in value_columns:
        result = result.merge(
            grouped[column].median().rename(columns={column: f"median_{column}"}),
            on=["condition", "evaluation_year"],
            validate="one_to_one",
        )
    return result


def _development_selected_policy(paths: pd.DataFrame) -> tuple[str, dict[str, float]]:
    """Select the one 2023 primary using only earlier OOS issue paths."""

    development = paths[
        paths["condition"].isin(LEARNED_CANDIDATES)
        & paths["evaluation_year"].isin((2021, 2022))
    ]
    by_seed = development.groupby(["condition", "seed"], as_index=False)[
        "pnl_cny"
    ].sum()
    medians = by_seed.groupby("condition")["pnl_cny"].median().sort_values(
        ascending=False
    )
    if medians.empty:
        raise ValueError("no development paths available to select primary")
    return str(medians.index[0]), {
        str(key): float(value) for key, value in medians.items()
    }


def _permutation_control(
    allocations: pd.DataFrame, ledger: pd.DataFrame, *, replicates: int = 2_000
) -> pd.DataFrame:
    """Permute issue/action assignments and replay each physical ticket seed."""

    issues = sorted(allocations["issue"].unique())
    donor_groups = {issue: group.copy() for issue, group in allocations.groupby("issue")}
    pnl = ledger.pivot(index=["issue", "action_key"], columns="seed", values="pnl_cny")
    seeds = sorted(ledger["seed"].unique())
    # effect[d, r, s] is the physical P&L obtained when the action mixture
    # chosen for donor issue d is placed on receiver issue r under ticket seed
    # s.  Building this small cube once avoids millions of pandas index
    # lookups inside the permutation loop.
    effect = np.empty((len(issues), len(issues), len(seeds)), dtype=float)
    for donor_index, donor in enumerate(issues):
        actions = donor_groups[donor]
        for receiver_index, receiver in enumerate(issues):
            total = np.zeros(len(seeds), dtype=float)
            for action in actions.itertuples(index=False):
                total += int(action.copies) * pnl.loc[
                    (receiver, action.action_key), seeds
                ].to_numpy(float)
            effect[donor_index, receiver_index] = total
    rows = []
    receiver_indices = np.arange(len(issues))
    for replicate in range(replicates):
        rng = np.random.default_rng(306_500 + replicate)
        donor_indices = rng.permutation(len(issues))
        totals = effect[donor_indices, receiver_indices].sum(axis=0)
        terminals = INITIAL_CAPITAL_CNY + totals
        row: dict[str, object] = {
            "replicate": replicate,
            "median_terminal_capital_cny": float(np.median(terminals)),
        }
        for seed, terminal in zip(seeds, terminals, strict=True):
            row[f"terminal_seed_{seed}_cny"] = float(terminal)
        rows.append(row)
    return pd.DataFrame(rows)


def _action_dependence(
    allocations: pd.DataFrame, ledger: pd.DataFrame, *, condition: str
) -> pd.DataFrame:
    selected = allocations[allocations["condition"].eq(condition)]
    keys = sorted(selected["action_key"].unique())
    work = ledger[ledger["action_key"].isin(keys)].copy()
    work["roi"] = work["pnl_cny"] / work["stake_cny"].clip(lower=2.0)
    pivot = work.pivot_table(index=["issue", "seed"], columns="action_key", values="roi")
    correlation = pivot.corr()
    rows = []
    for left_index, left in enumerate(keys):
        for right in keys[left_index + 1 :]:
            if left in correlation.index and right in correlation.columns:
                rows.append(
                    {
                        "left_action": left,
                        "right_action": right,
                        "return_correlation": float(correlation.loc[left, right]),
                        "common_issue_seed_rows": int(pivot[[left, right]].dropna().shape[0]),
                    }
                )
    return pd.DataFrame(rows)


def _row(frame: pd.DataFrame, condition: str, year: int) -> dict[str, object]:
    return frame[
        frame["condition"].eq(condition) & frame["evaluation_year"].eq(year)
    ].iloc[0].to_dict()


def _plot_capital(paths: pd.DataFrame, target: Path, *, primary: str) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    focus = [
        primary,
        "LEARNED_TAIL_DETERMINISTIC",
        "STATIC_TAIL_MIXTURE",
        "FIXED_N7_K512_WEIGHTED_WOR",
    ]
    local = paths[paths["evaluation_year"].eq(2023)]
    for condition in focus:
        group = local[local["condition"].eq(condition)].groupby("issue", as_index=False)["pnl_cny"].median().sort_values("issue")
        ax.plot(range(len(group)), 100_000 + group["pnl_cny"].cumsum(), label=condition)
    ax.axhline(100_000, color="black", lw=0.8)
    ax.set(title="#306 fixed-coverage 2023 capital paths", xlabel="issue order", ylabel="median nuisance-seed capital (CNY)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_frontier(frame: pd.DataFrame, target: Path) -> None:
    local = frame[frame["evaluation_year"].eq(2023)]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(local["median_max_drawdown_pct"], local["median_capital_growth_pct"], s=50 + 1000 * local["median_tail_5x_rate"])
    for row in local.itertuples(index=False):
        ax.annotate(row.condition, (row.median_max_drawdown_pct, row.median_capital_growth_pct), fontsize=7)
    ax.axhline(0, color="black", lw=0.8)
    ax.set(title="#306 tail/risk frontier (size = 5x-tail rate)", xlabel="median max drawdown (%)", ylabel="median capital growth (%)")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_actions(frame: pd.DataFrame, target: Path, *, primary: str) -> None:
    local = frame[frame["condition"].eq(primary)]
    pivot = local.groupby(["n", "generator"])["allocated_tickets"].sum().unstack(fill_value=0)
    fig, ax = plt.subplots(figsize=(9, 5))
    pivot.plot(kind="bar", stacked=True, ax=ax)
    ax.set(title="#306 learned tail-mixture ticket allocation", xlabel="N", ylabel="allocated tickets")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _write_manifest(output: Path) -> None:
    files = {}
    for path in sorted(output.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        files[path.name] = {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (output / "manifest.json").write_text(
        json.dumps({"issue": 306, "files": files}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
