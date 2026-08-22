"""Matched allocation, settlement and issue-level path metrics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .contract import (
    EVALUATION_YEARS,
    EXPERT_NAMES,
    INITIAL_CAPITAL_CNY,
    RANK_COUNTS,
    TARGET_COLUMNS,
    TOTAL_TICKETS,
)


def make_allocations(
    panel: pd.DataFrame, predictions: pd.DataFrame
) -> pd.DataFrame:
    """Build frozen static controls and matched dynamic expert allocations."""

    rows: list[dict[str, object]] = []
    for year in EVALUATION_YEARS:
        training = panel[panel["issue_year"].lt(year)]
        evaluation = panel[panel["issue_year"].eq(year)]
        prior = training.groupby("expert", as_index=False).agg(
            mean_roi=("clipped_roi", "mean"),
            observations=("clipped_roi", "size"),
        )
        global_mean = float(training["clipped_roi"].mean())
        prior["shrunk_utility"] = (
            prior["observations"] * prior["mean_roi"] + 20.0 * global_mean
        ) / (prior["observations"] + 20.0)
        prior_score = prior.set_index("expert")["shrunk_utility"].to_dict()
        best = max(EXPERT_NAMES, key=prior_score.__getitem__)
        for issue in sorted(evaluation["issue"].unique()):
            rows.extend(_equal_rows(issue, year))
            rows.extend(
                _rank_rows(
                    issue,
                    year,
                    "STATIC_SHRUNK_MIX",
                    prior_score,
                )
            )
            rows.append(
                _allocation_row(
                    issue,
                    year,
                    "BEST_SINGLE_EXPERT",
                    best,
                    TOTAL_TICKETS,
                    1,
                    prior_score[best],
                )
            )
        year_predictions = predictions[predictions["prediction_year"].eq(year)]
        for (condition, issue), group in year_predictions.groupby(
            ["condition", "issue"], sort=True
        ):
            score = group.set_index("expert")["predicted_utility"].to_dict()
            rows.extend(_rank_rows(issue, year, condition, score))
            if condition == "LAGGED_MULTITASK_MOE":
                best_dynamic = max(EXPERT_NAMES, key=score.__getitem__)
                rows.append(
                    _allocation_row(
                        issue,
                        year,
                        "HARD_TOP1",
                        best_dynamic,
                        TOTAL_TICKETS,
                        1,
                        score[best_dynamic],
                    )
                )
    allocation = pd.DataFrame(rows).sort_values(
        ["issue_year", "condition", "issue", "rank", "expert"]
    )
    totals = allocation.groupby(["condition", "issue"])["ticket_count"].sum()
    if not totals.eq(TOTAL_TICKETS).all():
        raise AssertionError("allocation does not reconcile to 512 tickets")
    return allocation


def _equal_rows(issue: str, year: int) -> list[dict[str, object]]:
    return [
        _allocation_row(issue, year, "EQUAL_MIX", expert, 64, rank + 1, 0.0)
        for rank, expert in enumerate(EXPERT_NAMES)
    ]


def _rank_rows(
    issue: str,
    year: int,
    condition: str,
    scores: dict[str, float],
) -> list[dict[str, object]]:
    ordered = sorted(EXPERT_NAMES, key=lambda expert: (-scores[expert], expert))
    return [
        _allocation_row(
            issue,
            year,
            condition,
            expert,
            RANK_COUNTS[rank],
            rank + 1,
            scores[expert],
        )
        for rank, expert in enumerate(ordered)
    ]


def _allocation_row(
    issue: str,
    year: int,
    condition: str,
    expert: str,
    count: int,
    rank: int,
    utility: float,
) -> dict[str, object]:
    return {
        "issue": str(issue),
        "issue_year": int(year),
        "condition": condition,
        "expert": expert,
        "ticket_count": int(count),
        "rank": int(rank),
        "predicted_utility": float(utility),
        "weight": float(count / TOTAL_TICKETS),
    }


def settle_allocations(
    allocations: pd.DataFrame, evaluation_surface: pd.DataFrame
) -> pd.DataFrame:
    """Settle all policies by exact issue/expert/count/seed lookup."""

    lookup = evaluation_surface.rename(columns={"k": "ticket_count"})
    joined = allocations.merge(
        lookup[
            [
                "issue",
                "issue_year",
                "seed",
                "expert",
                "ticket_count",
                "stake_cny",
                "gross_cny",
                "pnl_cny",
                "hit_count",
                "miss_one_count",
                "miss_two_count",
            ]
        ],
        on=["issue", "issue_year", "expert", "ticket_count"],
        how="left",
        validate="many_to_many",
    )
    if joined[["seed", "stake_cny", "gross_cny"]].isna().any().any():
        missing = joined[joined["seed"].isna()][
            ["issue", "expert", "ticket_count"]
        ].drop_duplicates()
        raise AssertionError(f"missing expert support: {missing.to_dict('records')[:5]}")
    settled = joined.groupby(
        ["issue_year", "condition", "seed", "issue"], as_index=False
    ).agg(
        stake_cny=("stake_cny", "sum"),
        gross_cny=("gross_cny", "sum"),
        pnl_cny=("pnl_cny", "sum"),
        hit_count=("hit_count", "sum"),
        miss_one_count=("miss_one_count", "sum"),
        miss_two_count=("miss_two_count", "sum"),
        expert_hhi=("weight", lambda x: float(np.square(x).sum())),
    )
    expected_stake = TOTAL_TICKETS * 2.0
    if not np.allclose(settled["stake_cny"], expected_stake):
        raise AssertionError("matched stake violated")
    return settled.sort_values(["condition", "seed", "issue_year", "issue"])


def capital_paths(settlement: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for (condition, seed), group in settlement.groupby(["condition", "seed"]):
        frame = group.sort_values(["issue_year", "issue"]).copy()
        frame["capital_cny"] = INITIAL_CAPITAL_CNY + frame["pnl_cny"].cumsum()
        frame["running_peak_cny"] = np.maximum.accumulate(
            np.r_[INITIAL_CAPITAL_CNY, frame["capital_cny"].to_numpy(float)]
        )[1:]
        frame["drawdown_pct"] = (
            frame["capital_cny"] - frame["running_peak_cny"]
        ) / frame["running_peak_cny"]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def policy_summary(settlement: pd.DataFrame) -> pd.DataFrame:
    seed_rows: list[dict[str, object]] = []
    for (year, condition, seed), group in settlement.groupby(
        ["issue_year", "condition", "seed"], sort=True
    ):
        group = group.sort_values("issue")
        pnl = group["pnl_cny"].to_numpy(float)
        capital = INITIAL_CAPITAL_CNY + np.cumsum(pnl)
        peak = np.maximum.accumulate(np.r_[INITIAL_CAPITAL_CNY, capital])[1:]
        drawdown = (capital - peak) / peak
        seed_rows.append(
            {
                "issue_year": int(year),
                "condition": condition,
                "seed": int(seed),
                "issues": len(group),
                "stake_cny": float(group["stake_cny"].sum()),
                "gross_cny": float(group["gross_cny"].sum()),
                "pnl_cny": float(pnl.sum()),
                "terminal_capital_cny": float(capital[-1]),
                "capital_return": float(capital[-1] / INITIAL_CAPITAL_CNY - 1.0),
                "turnover_roi": float(pnl.sum() / group["stake_cny"].sum()),
                "payout_issue_rate": float(group["gross_cny"].gt(0).mean()),
                "profitable_issue_rate": float(group["pnl_cny"].gt(0).mean()),
                "max_drawdown_pct": float(-drawdown.min()),
                "longest_losing_issues": _longest(group["pnl_cny"].lt(0)),
                "worst_rolling_5_pnl_cny": _worst_rolling(pnl, 5),
                "worst_rolling_10_pnl_cny": _worst_rolling(pnl, 10),
                "worst_rolling_20_pnl_cny": _worst_rolling(pnl, 20),
                "maximum_completed_recovery_issues": _maximum_recovery(capital),
                "ex_largest_pnl_cny": float(pnl.sum() - max(0.0, pnl.max())),
                "mean_expert_hhi": float(group["expert_hhi"].mean()),
            }
        )
    seed_summary = pd.DataFrame(seed_rows)
    numeric = [
        column
        for column in seed_summary.columns
        if column not in {"condition", "seed", "issue_year"}
    ]
    summary = seed_summary.groupby(["issue_year", "condition"], as_index=False)[
        numeric
    ].median()
    return summary.sort_values(["issue_year", "terminal_capital_cny"], ascending=[True, False])


def paired_lifts(settlement: pd.DataFrame) -> pd.DataFrame:
    baselines = (
        "EQUAL_MIX",
        "STATIC_SHRUNK_MIX",
        "BEST_SINGLE_EXPERT",
        "CURRENT_ONLY_MOE",
    )
    totals = settlement.groupby(
        ["issue_year", "condition", "seed"], as_index=False
    )["pnl_cny"].sum()
    rows: list[dict[str, object]] = []
    for baseline in baselines:
        base = totals[totals["condition"].eq(baseline)].rename(
            columns={"pnl_cny": "baseline_pnl_cny"}
        )[["issue_year", "seed", "baseline_pnl_cny"]]
        comparison = totals.merge(base, on=["issue_year", "seed"], how="inner")
        comparison["lift_cny"] = comparison["pnl_cny"] - comparison["baseline_pnl_cny"]
        for (year, condition), group in comparison.groupby(
            ["issue_year", "condition"]
        ):
            rows.append(
                {
                    "issue_year": int(year),
                    "condition": condition,
                    "baseline": baseline,
                    "nuisance_seeds": int(group["seed"].nunique()),
                    "median_lift_cny": float(group["lift_cny"].median()),
                    "minimum_lift_cny": float(group["lift_cny"].min()),
                    "maximum_lift_cny": float(group["lift_cny"].max()),
                    "paired_seed_win_rate": float(group["lift_cny"].gt(0).mean()),
                }
            )
    return pd.DataFrame(rows).sort_values(["issue_year", "baseline", "condition"])


def bootstrap_issue_lift(
    settlement: pd.DataFrame,
    *,
    baseline: str = "CURRENT_ONLY_MOE",
    draws: int = 2000,
) -> pd.DataFrame:
    issue_mean = settlement.groupby(
        ["issue_year", "condition", "issue"], as_index=False
    )["pnl_cny"].mean()
    base = issue_mean[issue_mean["condition"].eq(baseline)].rename(
        columns={"pnl_cny": "baseline_pnl_cny"}
    )[["issue_year", "issue", "baseline_pnl_cny"]]
    compared = issue_mean.merge(base, on=["issue_year", "issue"], how="inner")
    compared["lift_cny"] = compared["pnl_cny"] - compared["baseline_pnl_cny"]
    rng = np.random.default_rng(332)
    rows = []
    for (year, condition), group in compared.groupby(["issue_year", "condition"]):
        values = group["lift_cny"].to_numpy(float)
        sampled = values[rng.integers(0, len(values), size=(draws, len(values)))].sum(axis=1)
        rows.append(
            {
                "issue_year": int(year),
                "condition": condition,
                "baseline": baseline,
                "issues": len(values),
                "matched_lift_cny": float(values.sum()),
                "bootstrap_p025_cny": float(np.quantile(sampled, 0.025)),
                "bootstrap_p50_cny": float(np.quantile(sampled, 0.5)),
                "bootstrap_p975_cny": float(np.quantile(sampled, 0.975)),
                "bootstrap_positive_probability": float((sampled > 0).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["issue_year", "condition"])


def auxiliary_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (year, condition), group in predictions.groupby(
        ["prediction_year", "condition"]
    ):
        for target in TARGET_COLUMNS[:-1]:
            actual = group[target].to_numpy(float)
            predicted = group[f"predicted_{target}"].to_numpy(float)
            rows.append(
                {
                    "issue_year": int(year),
                    "condition": condition,
                    "target": target,
                    "mae": float(np.mean(np.abs(actual - predicted))),
                    "correlation": _correlation(actual, predicted),
                }
            )
    return pd.DataFrame(rows)


def allocation_attribution(allocations: pd.DataFrame) -> pd.DataFrame:
    return allocations.groupby(
        ["issue_year", "condition", "expert"], as_index=False
    ).agg(
        mean_weight=("weight", "mean"),
        top_rank_fraction=("rank", lambda x: float((x == 1).mean())),
        mean_predicted_utility=("predicted_utility", "mean"),
    )


def accepted_baseline_comparison(
    repo_root: Path, settlement: pd.DataFrame
) -> pd.DataFrame:
    """Compare on exact active support with the accepted #319 Top-2 N7 baseline."""

    baseline = pd.read_parquet(
        repo_root / "results/top2_n7_stable/issue_bundles.parquet"
    )
    baseline = baseline[
        baseline["horizon"].eq("10h")
        & baseline["arm"].eq("P_TOP2_NO_GATE")
        & baseline["stake"].gt(0)
        & baseline["pnl"].notna()
        & baseline["issue_year"].isin([2023, 2024])
    ].copy()
    baseline["issue"] = baseline["issue_code"].astype(str)
    # The accepted arm carries 128 tickets. Four paid copies make exposure exactly
    # comparable to the 512-ticket Issue #332 policies without changing its logic.
    baseline["baseline_pnl_cny"] = 4.0 * baseline["pnl"]
    policy = settlement.groupby(
        ["issue_year", "condition", "issue"], as_index=False
    )["pnl_cny"].mean()
    matched = policy.merge(
        baseline[["issue_year", "issue", "baseline_pnl_cny"]],
        on=["issue_year", "issue"],
        how="inner",
        validate="many_to_one",
    )
    matched["lift_cny"] = matched["pnl_cny"] - matched["baseline_pnl_cny"]
    rows = []
    for (year, condition), group in matched.groupby(["issue_year", "condition"]):
        lift = group["lift_cny"].to_numpy(float)
        rows.append(
            {
                "issue_year": int(year),
                "condition": condition,
                "baseline": "TOP2_N7_P_TOP2_NO_GATE_X4",
                "matched_issues": len(group),
                "policy_pnl_cny": float(group["pnl_cny"].sum()),
                "baseline_pnl_cny": float(group["baseline_pnl_cny"].sum()),
                "matched_lift_cny": float(lift.sum()),
                "ex_largest_lift_cny": float(lift.sum() - max(0.0, lift.max())),
                "positive_issue_fraction": float((lift > 0).mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["issue_year", "condition"])


def _longest(mask: pd.Series) -> int:
    best = current = 0
    for value in mask.astype(bool):
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def _worst_rolling(values: np.ndarray, window: int) -> float:
    if len(values) < window:
        return float(values.sum())
    return float(pd.Series(values).rolling(window).sum().min())


def _maximum_recovery(capital: np.ndarray) -> int:
    peak_value = INITIAL_CAPITAL_CNY
    peak_index = -1
    maximum = 0
    for index, value in enumerate(capital):
        if value >= peak_value:
            maximum = max(maximum, index - peak_index)
            peak_value = value
            peak_index = index
    return int(maximum)


def _correlation(left: np.ndarray, right: np.ndarray) -> float:
    if np.std(left) == 0 or np.std(right) == 0:
        return 0.0
    return float(np.corrcoef(left, right)[0, 1])
