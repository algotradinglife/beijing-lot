"""Atomic BEST_FULL replay and exact exposure null for Issue #305."""

from __future__ import annotations

from collections import Counter
from math import comb

import numpy as np
import pandas as pd

from issue296.evaluation import summarize_path

INITIAL_CAPITAL_CNY = 100_000.0
ATOMIC_STAKE_CNY = 4_374.0


def decisions_from_scores(
    issues: pd.DataFrame, scores: pd.DataFrame, *, condition: str
) -> pd.DataFrame:
    """Keep an active atomic baseline only when ensemble utility is positive."""

    columns = [
        "issue",
        "issue_year",
        "predicted_pnl_cny",
        "predicted_downside_cny",
        "predicted_loss_probability",
        "predicted_utility_cny",
        "predicted_utility_std_cny",
        "positive_seed_count",
    ]
    result = issues[["issue", "issue_year", "baseline_active"]].merge(
        scores[columns], on=["issue", "issue_year"], how="left", validate="one_to_one"
    )
    result["condition"] = condition
    result["keep_baseline"] = (
        result["baseline_active"].eq(1)
        & result["predicted_utility_cny"].fillna(-np.inf).gt(0)
    )
    return result.drop(columns="baseline_active")


def constant_decisions(
    issues: pd.DataFrame, *, condition: str, keep_active: bool
) -> pd.DataFrame:
    result = issues[["issue", "issue_year", "baseline_active"]].copy()
    result["condition"] = condition
    result["keep_baseline"] = result["baseline_active"].eq(1) & keep_active
    for column in [
        "predicted_pnl_cny",
        "predicted_downside_cny",
        "predicted_loss_probability",
        "predicted_utility_cny",
        "predicted_utility_std_cny",
        "positive_seed_count",
    ]:
        result[column] = 0.0
    return result.drop(columns="baseline_active")


def oracle_decisions(issues: pd.DataFrame) -> pd.DataFrame:
    result = constant_decisions(issues, condition="ORACLE_DIAGNOSTIC", keep_active=False)
    result["keep_baseline"] = issues["baseline_active"].eq(1) & issues["baseline_pnl_cny"].gt(0)
    return result


def capital_path(
    issues: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    initial_capital_cny: float = INITIAL_CAPITAL_CNY,
) -> pd.DataFrame:
    selected = issues.merge(
        decisions, on=["issue", "issue_year"], validate="one_to_one"
    ).sort_values(["issue_year", "issue"])
    capital = float(initial_capital_cny)
    rows: list[dict[str, object]] = []
    for row in selected.itertuples(index=False):
        opening = capital
        execute = bool(row.keep_baseline) and bool(row.baseline_active)
        stake = float(row.baseline_stake_cny) if execute else 0.0
        pnl = float(row.baseline_pnl_cny) if execute else 0.0
        gross = float(row.baseline_gross_cny) if execute else 0.0
        if stake > opening + 1e-9:
            execute = False
            stake = pnl = gross = 0.0
        capital = opening + pnl
        rows.append(
            {
                "issue": int(row.issue),
                "issue_year": int(row.issue_year),
                "condition": str(row.condition),
                "opening_capital_cny": opening,
                "stake_cny": stake,
                "pnl_cny": pnl,
                "gross_cny": gross,
                "closing_capital_cny": capital,
                "baseline_executed": execute,
                "deployed_capital_fraction": stake / opening if opening else 0.0,
                "effective_cash_fraction": 1.0 - stake / opening if opening else 1.0,
            }
        )
    return pd.DataFrame(rows)


def summarize(path: pd.DataFrame) -> dict[str, object]:
    return summarize_path(path)


def exact_exposure_null(
    issues: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    year: int = 2023,
    initial_capital_cny: float = INITIAL_CAPITAL_CNY,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Exact null over all same-count placements on active destination issues.

    P&L is converted to cents before dynamic programming.  The returned table
    stores each distinct terminal value and its exact multiplicity rather than
    materializing every combination.
    """

    local = issues[
        issues["issue_year"].eq(year) & issues["baseline_active"].eq(1)
    ].sort_values("issue")
    selected = decisions[
        decisions["issue_year"].eq(year) & decisions["keep_baseline"]
    ]
    # Legacy policies may mark inherited NO_BET rows as ``keep=True``.  The
    # executed-exposure null counts only destinations with the atomic CNY4,374
    # baseline actually available, rather than the policy flag itself.
    active_destinations = set(local["issue"])
    selected_issues = set(
        pd.to_numeric(selected["issue"], errors="raise").astype(int)
    ) & active_destinations
    funded_count = len(selected_issues)
    pnl_cents = np.rint(local["baseline_pnl_cny"].to_numpy(float) * 100).astype(np.int64)
    observed_cents = int(
        np.rint(
            local[local["issue"].isin(selected_issues)]["baseline_pnl_cny"].sum() * 100
        )
    )
    distributions: list[Counter[int]] = [Counter() for _ in range(funded_count + 1)]
    distributions[0][0] = 1
    seen = 0
    for value in pnl_cents:
        seen += 1
        for count in range(min(funded_count, seen), 0, -1):
            for subtotal, multiplicity in list(distributions[count - 1].items()):
                distributions[count][subtotal + int(value)] += multiplicity
    distribution = distributions[funded_count]
    total = comb(len(local), funded_count)
    if sum(distribution.values()) != total:
        raise AssertionError("exact combination count drift")
    observed_terminal_cents = int(round(initial_capital_cny * 100)) + observed_cents
    terminal_counts = Counter(
        {
            int(round(initial_capital_cny * 100)) + pnl: multiplicity
            for pnl, multiplicity in distribution.items()
        }
    )
    percentile = sum(
        multiplicity
        for terminal, multiplicity in terminal_counts.items()
        if terminal <= observed_terminal_cents
    ) / total
    ordered = sorted(terminal_counts.items())

    def weighted_quantile(probability: float) -> float:
        target = probability * total
        cumulative = 0
        for terminal, multiplicity in ordered:
            cumulative += multiplicity
            if cumulative >= target:
                return terminal / 100.0
        return ordered[-1][0] / 100.0

    # Preserve the exact calculation in the JSON receipt, but commit a compact
    # exact-mass histogram rather than millions of individual terminal values.
    bin_width_cents = 25_000
    bins: Counter[int] = Counter()
    for terminal, multiplicity in terminal_counts.items():
        lower = (terminal // bin_width_cents) * bin_width_cents
        bins[lower] += multiplicity
    table = pd.DataFrame(
        {
            "bin_lower_cny": [lower / 100.0 for lower in sorted(bins)],
            "bin_upper_cny": [
                (lower + bin_width_cents) / 100.0 for lower in sorted(bins)
            ],
            "multiplicity": [bins[lower] for lower in sorted(bins)],
        }
    )
    table["bin_midpoint_cny"] = (
        table["bin_lower_cny"] + table["bin_upper_cny"]
    ) / 2.0
    table["probability"] = table["multiplicity"] / total
    summary = {
        "year": year,
        "active_destination_issues": int(len(local)),
        "funded_count": funded_count,
        "stake_per_funded_issue_cny": ATOMIC_STAKE_CNY,
        "total_stake_cny": funded_count * ATOMIC_STAKE_CNY,
        "combination_count": total,
        "distinct_terminal_values": int(len(terminal_counts)),
        "histogram_bins": int(len(table)),
        "observed_terminal_capital_cny": observed_terminal_cents / 100.0,
        "exact_percentile": percentile,
        "null_p05_terminal_capital_cny": weighted_quantile(0.05),
        "null_median_terminal_capital_cny": weighted_quantile(0.50),
        "null_p95_terminal_capital_cny": weighted_quantile(0.95),
        "histogram_bin_width_cny": bin_width_cents / 100.0,
    }
    return table, summary
