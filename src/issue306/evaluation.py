"""Fixed-budget action composition and physical capital replay for Issue #306."""

from __future__ import annotations

import numpy as np
import pandas as pd

COMMITTED_TICKETS = 512
COMMITTED_STAKE_CNY = 1_024.0
INITIAL_CAPITAL_CNY = 100_000.0


def learned_allocations(
    scores: pd.DataFrame,
    *,
    condition: str,
    score_column: str,
    mixture: bool,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (issue, year), local in scores.groupby(["issue", "issue_year"], sort=True):
        feasible = local[local["effective_k"].eq(local["k"])].sort_values(
            [score_column, "action_key"], ascending=[False, True]
        )
        if mixture:
            # A K512 bundle consumes the entire experimental budget and turns
            # the composition arm back into a single-action selector. Keep it
            # in deterministic controls, but require genuine multi-sleeve
            # composition to use K<=128 components.
            feasible = feasible[feasible["k"].le(128)]
        if feasible.empty or not feasible["k"].eq(8).any():
            raise ValueError(f"issue {issue} lacks exact-budget action support")
        allocation: dict[str, tuple[int, int, str, int]] = {}
        remaining = COMMITTED_TICKETS
        if mixture:
            for action in feasible.itertuples(index=False):
                if int(action.k) <= remaining and action.action_key not in allocation:
                    allocation[str(action.action_key)] = (
                        1, int(action.n), str(action.generator), int(action.k)
                    )
                    remaining -= int(action.k)
                if remaining == 0:
                    break
        else:
            action = feasible.iloc[0]
            copies = COMMITTED_TICKETS // int(action["k"])
            allocation[str(action["action_key"])] = (
                copies, int(action["n"]), str(action["generator"]), int(action["k"])
            )
            remaining -= copies * int(action["k"])
        if remaining:
            filler = feasible[feasible["k"].eq(8)].iloc[0]
            copies = remaining // 8
            current = allocation.get(str(filler["action_key"]), (0, int(filler["n"]), str(filler["generator"]), 8))
            allocation[str(filler["action_key"])] = (
                current[0] + copies, current[1], current[2], current[3]
            )
            remaining -= copies * 8
        if remaining != 0:
            raise AssertionError("allocation did not exhaust fixed ticket budget")
        for action_key, (copies, n, generator, k) in allocation.items():
            rows.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "condition": condition,
                    "action_key": action_key,
                    "n": n,
                    "k": k,
                    "generator": generator,
                    "copies": copies,
                    "allocated_tickets": copies * k,
                }
            )
    return pd.DataFrame(rows)


def fixed_allocations(
    issues: pd.DataFrame, *, action_key: str, n: int, k: int, generator: str, condition: str
) -> pd.DataFrame:
    if COMMITTED_TICKETS % k:
        raise ValueError("fixed action K must divide committed ticket budget")
    return issues[["issue", "issue_year"]].assign(
        condition=condition,
        action_key=action_key,
        n=n,
        k=k,
        generator=generator,
        copies=COMMITTED_TICKETS // k,
        allocated_tickets=COMMITTED_TICKETS,
    )


def evaluate_allocations(allocations: pd.DataFrame, ledger: pd.DataFrame) -> pd.DataFrame:
    merged = allocations.merge(
        ledger,
        on=["issue", "issue_year", "action_key", "n", "k", "generator"],
        how="left",
        validate="many_to_many",
    )
    if merged[["seed", "pnl_cny"]].isna().any(axis=None):
        raise ValueError("allocation/physical-ledger support mismatch")
    for column in ["stake_cny", "pnl_cny", "gross_cny", "hit_count", "effective_k"]:
        merged[f"executed_{column}"] = merged[column] * merged["copies"]
    path = merged.groupby(
        ["issue", "issue_year", "condition", "seed"], as_index=False
    ).agg(
        stake_cny=("executed_stake_cny", "sum"),
        pnl_cny=("executed_pnl_cny", "sum"),
        gross_cny=("executed_gross_cny", "sum"),
        hit_count=("executed_hit_count", "sum"),
        executed_tickets=("executed_effective_k", "sum"),
        distinct_action_count=("action_key", "nunique"),
    )
    if not path["executed_tickets"].eq(COMMITTED_TICKETS).all():
        raise AssertionError("physical execution drifted from 512 tickets")
    if not np.allclose(path["stake_cny"], COMMITTED_STAKE_CNY):
        raise AssertionError("physical execution drifted from CNY1,024")
    path["tail_2x"] = path["gross_cny"].ge(2 * path["stake_cny"])
    path["tail_5x"] = path["gross_cny"].ge(5 * path["stake_cny"])
    path["tail_10x"] = path["gross_cny"].ge(10 * path["stake_cny"])
    frames = []
    for (condition, seed, year), local in path.groupby(
        ["condition", "seed", "issue_year"], sort=True
    ):
        local = local.sort_values("issue").copy()
        local["opening_capital_cny"] = INITIAL_CAPITAL_CNY + local["pnl_cny"].cumsum().shift(fill_value=0.0)
        local["closing_capital_cny"] = local["opening_capital_cny"] + local["pnl_cny"]
        local["evaluation_year"] = int(year)
        frames.append(local)
    return pd.concat(frames, ignore_index=True)


def summarize_paths(paths: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (condition, seed, year), path in paths.groupby(
        ["condition", "seed", "evaluation_year"], sort=True
    ):
        pnl = path["pnl_cny"].to_numpy(float)
        closing = path["closing_capital_cny"].to_numpy(float)
        peaks = np.maximum.accumulate(np.r_[INITIAL_CAPITAL_CNY, closing])
        drawdown = 1.0 - np.r_[INITIAL_CAPITAL_CNY, closing] / peaks
        rows.append(
            {
                "condition": condition,
                "seed": int(seed),
                "evaluation_year": int(year),
                "issues": int(len(path)),
                "stake_cny": float(path["stake_cny"].sum()),
                "pnl_cny": float(pnl.sum()),
                "terminal_capital_cny": float(closing[-1]),
                "capital_growth_pct": float(100 * (closing[-1] / INITIAL_CAPITAL_CNY - 1)),
                "turnover_roi_pct": float(100 * pnl.sum() / path["stake_cny"].sum()),
                "max_drawdown_pct": float(100 * drawdown.max()),
                "longest_losing_issue_streak": _longest(pnl < 0),
                "longest_no_payout_streak": _longest(path["gross_cny"].to_numpy(float) <= 0),
                "ex_largest_pnl_cny": float(pnl.sum() - pnl.max()),
                "positive_issue_rate": float((pnl > 0).mean()),
                "any_payout_rate": float(path["gross_cny"].gt(0).mean()),
                "tail_2x_rate": float(path["tail_2x"].mean()),
                "tail_5x_rate": float(path["tail_5x"].mean()),
                "tail_10x_rate": float(path["tail_10x"].mean()),
                "rolling_5_tail_capture_probability": _rolling_capture(path["tail_5x"].to_numpy(bool), 5),
                "rolling_10_tail_capture_probability": _rolling_capture(path["tail_5x"].to_numpy(bool), 10),
                "rolling_20_tail_capture_probability": _rolling_capture(path["tail_5x"].to_numpy(bool), 20),
                "mean_distinct_actions": float(path["distinct_action_count"].mean()),
                "worst_rolling_5_pnl_cny": _rolling_min(pnl, 5),
                "worst_rolling_10_pnl_cny": _rolling_min(pnl, 10),
                "worst_rolling_20_pnl_cny": _rolling_min(pnl, 20),
                "maximum_completed_recovery_issues": _recovery(closing)[0],
                "open_terminal_underwater_issues": _recovery(closing)[1],
                "ruin": bool((path["opening_capital_cny"] < COMMITTED_STAKE_CNY).any()),
            }
        )
    return pd.DataFrame(rows)


def _longest(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _rolling_min(values: np.ndarray, window: int) -> float:
    result = pd.Series(values).rolling(window).sum().min()
    return float(result) if np.isfinite(result) else float(values.sum())


def _rolling_capture(values: np.ndarray, window: int) -> float:
    if len(values) < window:
        return float(values.any())
    return float(pd.Series(values.astype(int)).rolling(window).max().dropna().mean())


def _recovery(capital: np.ndarray) -> tuple[int, int]:
    path = np.r_[INITIAL_CAPITAL_CNY, capital]
    peak = path[0]
    underwater_start: int | None = None
    longest = 0
    for index, value in enumerate(path[1:], 1):
        if value >= peak:
            if underwater_start is not None:
                longest = max(longest, index - underwater_start)
                underwater_start = None
            peak = value
        elif underwater_start is None:
            underwater_start = index
    open_underwater = len(path) - underwater_start if underwater_start is not None else 0
    return longest, open_underwater
