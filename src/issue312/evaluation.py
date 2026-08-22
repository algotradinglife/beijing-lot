"""Fixed-exposure settlement, risk and attribution for Issue #312."""

from __future__ import annotations

import numpy as np
import pandas as pd

from issue306.evaluation import evaluate_allocations, summarize_paths

from .policy import ACTION_COLUMNS, COMMITTED_TICKETS


def add_oracle_allocation(
    allocations: pd.DataFrame, ledger: pd.DataFrame
) -> pd.DataFrame:
    """Append a clearly outcome-exposed best-action diagnostic."""

    mean = ledger.groupby(["issue", "issue_year", "action_key"], as_index=False).agg(
        mean_pnl_cny=("pnl_cny", "mean"),
        k=("k", "first"),
        n=("n", "first"),
        match_selector=("match_selector", "first"),
        pool_excess=("pool_excess", "first"),
        outcome_direction=("outcome_direction", "first"),
        generator=("generator", "first"),
        protection=("protection", "first"),
    )
    mean["fixed_budget_pnl_cny"] = mean["mean_pnl_cny"] * COMMITTED_TICKETS / mean["k"]
    oracle = mean.loc[mean.groupby("issue")["fixed_budget_pnl_cny"].idxmax()].copy()
    oracle["condition"] = "ORACLE_DIAGNOSTIC"
    oracle["copies"] = COMMITTED_TICKETS // oracle["k"]
    oracle["allocated_tickets"] = COMMITTED_TICKETS
    columns = [
        "issue",
        "issue_year",
        "condition",
        "action_key",
        *ACTION_COLUMNS,
        "copies",
        "allocated_tickets",
    ]
    return pd.concat([allocations, oracle[columns]], ignore_index=True)


def evaluate(allocations: pd.DataFrame, ledger: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replay each policy and summarize each physical ticket seed."""

    paths = evaluate_allocations(allocations, ledger)
    summary = summarize_paths(paths)
    return paths, summary


def aggregate_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """Median seed path metrics without treating seeds as issues."""

    identifiers = ["condition", "evaluation_year"]
    fixed = summary.groupby(identifiers, as_index=False).agg(
        nuisance_seeds=("seed", "nunique"),
        issues=("issues", "first"),
        stake_cny=("stake_cny", "mean"),
        ruin_seed_rate=("ruin", "mean"),
    )
    values = [
        column
        for column in summary.columns
        if column
        not in {
            "condition",
            "seed",
            "evaluation_year",
            "issues",
            "stake_cny",
            "pnl_cny",
            "ruin",
        }
    ]
    for column in values:
        local = (
            summary.groupby(identifiers, as_index=False)[column]
            .median()
            .rename(columns={column: f"median_{column}"})
        )
        fixed = fixed.merge(local, on=identifiers, validate="one_to_one")
    return fixed


def factor_attribution(paths: pd.DataFrame) -> pd.DataFrame:
    """Compare the joint primary with each one-factor reset on paired seeds."""

    primary = paths[paths["condition"].eq("JOINT_PRIMARY")][
        ["issue", "seed", "pnl_cny"]
    ].rename(columns={"pnl_cny": "primary_pnl_cny"})
    rows = []
    for condition in ("ABLATE_SELECTOR", "ABLATE_OUTCOME", "ABLATE_PROTECTION"):
        comparator = paths[paths["condition"].eq(condition)][
            ["issue", "seed", "pnl_cny"]
        ].rename(columns={"pnl_cny": "comparator_pnl_cny"})
        paired = primary.merge(comparator, on=["issue", "seed"], validate="one_to_one")
        paired["lift_cny"] = paired["primary_pnl_cny"] - paired["comparator_pnl_cny"]
        seed_lift = paired.groupby("seed")["lift_cny"].sum()
        issue_lift = paired.groupby("issue")["lift_cny"].mean()
        rows.append(
            {
                "ablation": condition,
                "median_seed_lift_cny": float(seed_lift.median()),
                "positive_seed_fraction": float(seed_lift.gt(0).mean()),
                "mean_issue_lift_cny": float(issue_lift.mean()),
                "positive_issue_fraction": float(issue_lift.gt(0).mean()),
                "ex_largest_issue_lift_cny": float(issue_lift.sum() - issue_lift.max()),
            }
        )
    return pd.DataFrame(rows)


def physical_permutation(
    allocations: pd.DataFrame,
    ledger: pd.DataFrame,
    *,
    replicates: int = 2_000,
) -> pd.DataFrame:
    """Reassign the primary action map while preserving every physical seed."""

    issues = sorted(allocations["issue"].unique())
    donor_groups = {issue: group for issue, group in allocations.groupby("issue")}
    pnl = ledger.pivot(index=["issue", "action_key"], columns="seed", values="pnl_cny")
    seeds = sorted(ledger["seed"].unique())
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
    receiver_indices = np.arange(len(issues))
    rows = []
    for replicate in range(replicates):
        donors = np.random.default_rng(312500 + replicate).permutation(len(issues))
        terminals = 100_000.0 + effect[donors, receiver_indices].sum(axis=0)
        row: dict[str, object] = {
            "replicate": replicate,
            "median_terminal_capital_cny": float(np.median(terminals)),
        }
        for seed, terminal in zip(seeds, terminals, strict=True):
            row[f"terminal_seed_{seed}_cny"] = float(terminal)
        rows.append(row)
    return pd.DataFrame(rows)
