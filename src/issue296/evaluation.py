"""Executable whole-bundle capital paths and holding-feasibility diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

INITIAL_CAPITAL_CNY = 100_000.0


def make_issue_table(
    features: pd.DataFrame, panel: pd.DataFrame, expert_ids: list[str]
) -> pd.DataFrame:
    """Pivot long expert economics into one issue-level learning table."""

    result = features.copy()
    for expert in expert_ids:
        local = panel[panel["expert_id"].eq(expert)].set_index("issue")
        indexed = result["issue"].map(local["unit_roi"])
        result[f"return_{expert}"] = indexed.fillna(0.0)
        result[f"available_{expert}"] = (
            result["issue"].map(local["available"]).fillna(False)
        )
        result[f"stake_{expert}"] = (
            result["issue"].map(local["stake_unit_cny"]).fillna(0.0)
        )
        result[f"pnl_{expert}"] = result["issue"].map(local["pnl_unit_cny"]).fillna(0.0)
        result[f"gross_{expert}"] = (
            result["issue"].map(local["gross_unit_cny"]).fillna(0.0)
        )
        result[f"hits_{expert}"] = result["issue"].map(local["hit_count"]).fillna(0.0)
    return result.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def capital_path(
    issue_table: pd.DataFrame,
    weights: pd.DataFrame,
    expert_ids: list[str],
    *,
    initial_capital_cny: float = INITIAL_CAPITAL_CNY,
) -> pd.DataFrame:
    """Apply predicted weights with whole-bundle rounding and no stake cap."""

    weight_columns = [f"weight_{expert}" for expert in expert_ids] + ["weight_CASH"]
    missing_weights = sorted(set(weight_columns) - set(weights.columns))
    if missing_weights:
        raise ValueError(f"capital weights missing columns: {missing_weights}")
    if (weights[weight_columns] < -1e-10).any(axis=None):
        raise ValueError("capital weights must be non-negative")
    if not np.allclose(weights[weight_columns].sum(axis=1), 1.0, atol=1e-8):
        raise ValueError("capital weights must sum to one")
    merged = issue_table.merge(
        weights, on=["issue", "issue_year"], how="inner", validate="one_to_one"
    ).sort_values(["issue_year", "issue"])
    if len(merged) != len(issue_table) or len(weights) != len(issue_table):
        raise ValueError(
            "issue table and capital weights do not have identical support"
        )
    capital = float(initial_capital_cny)
    rows = []
    for row in merged.itertuples(index=False):
        opening = capital
        stake_total = 0.0
        pnl_total = 0.0
        gross_total = 0.0
        hit_total = 0.0
        allocations = {}
        for expert in expert_ids:
            desired = opening * float(getattr(row, f"weight_{expert}"))
            unit_stake = float(getattr(row, f"stake_{expert}"))
            available = bool(getattr(row, f"available_{expert}"))
            multiplier = (
                int(np.floor(desired / unit_stake))
                if available and unit_stake > 0
                else 0
            )
            stake = multiplier * unit_stake
            pnl = multiplier * float(getattr(row, f"pnl_{expert}"))
            gross = multiplier * float(getattr(row, f"gross_{expert}"))
            hits = multiplier * float(getattr(row, f"hits_{expert}"))
            stake_total += stake
            pnl_total += pnl
            gross_total += gross
            hit_total += hits
            allocations[f"multiplier_{expert}"] = multiplier
            allocations[f"stake_{expert}"] = stake
            allocations[f"pnl_{expert}"] = pnl
            allocations[f"gross_{expert}"] = gross
        if stake_total > opening + 1e-6:
            raise AssertionError("capital allocation exceeds opening bankroll")
        capital = opening + pnl_total
        if capital < -1e-6:
            raise AssertionError("whole-bundle path produced negative capital")
        rows.append(
            {
                "issue": int(row.issue),
                "issue_year": int(row.issue_year),
                "condition": str(row.condition),
                "opening_capital_cny": opening,
                "stake_cny": stake_total,
                "pnl_cny": pnl_total,
                "gross_cny": gross_total,
                "hit_ticket_count": hit_total,
                "closing_capital_cny": capital,
                "cash_weight": float(row.weight_CASH),
                "deployed_capital_fraction": stake_total / opening if opening else 0.0,
                "effective_cash_fraction": 1.0 - stake_total / opening
                if opening
                else 1.0,
                **allocations,
            }
        )
    return pd.DataFrame(rows)


def fixed_weights(
    issue_table: pd.DataFrame,
    expert_ids: list[str],
    allocation: dict[str, float],
    *,
    condition: str,
) -> pd.DataFrame:
    """Broadcast a fixed allocation, routing unavailable mass to cash."""

    if any(value < 0 for value in allocation.values()):
        raise ValueError("allocation weights must be non-negative")
    if sum(allocation.values()) > 1.0 + 1e-10:
        raise ValueError("allocation exceeds one unit of bankroll")
    result = issue_table[["issue", "issue_year"]].copy()
    funded = np.zeros(len(result), dtype=float)
    for expert in expert_ids:
        requested = float(allocation.get(expert, 0.0))
        available = issue_table[f"available_{expert}"].to_numpy(bool)
        value = requested * available
        result[f"weight_{expert}"] = value
        funded += value
    result["weight_CASH"] = 1.0 - funded
    result["condition"] = condition
    return result


def fit_static_log_growth_allocation(
    issue_table: pd.DataFrame,
    expert_ids: list[str],
    *,
    l2_penalty: float = 0.02,
) -> dict[str, float]:
    """Fit a train-only constant expert mix under a cash budget constraint."""

    train = issue_table[issue_table["issue_year"].between(2019, 2021)]
    returns = train[[f"return_{expert}" for expert in expert_ids]].to_numpy(float)
    available = train[[f"available_{expert}" for expert in expert_ids]].to_numpy(bool)
    returns = returns * available

    def objective(weights: np.ndarray) -> float:
        realized = returns @ weights
        if np.any(realized <= -1.0):
            return 1e6
        return float(
            -np.mean(np.log1p(realized)) + l2_penalty * np.square(weights).sum()
        )

    initial = np.full(len(expert_ids), 0.5 / len(expert_ids))
    fit = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * len(expert_ids),
        constraints={"type": "ineq", "fun": lambda value: 1.0 - value.sum()},
        options={"maxiter": 1000, "ftol": 1e-12},
    )
    if not fit.success:
        raise RuntimeError(f"static allocation fit failed: {fit.message}")
    return {
        expert: float(weight) for expert, weight in zip(expert_ids, fit.x, strict=True)
    }


def apply_validation_fallback(
    issue_table: pd.DataFrame,
    learned: pd.DataFrame,
    baseline: pd.DataFrame,
    expert_ids: list[str],
    *,
    condition: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Fall back to the frozen baseline when 2022 executable evidence is worse."""

    validation = issue_table[issue_table["issue_year"].eq(2022)]
    learned_path = capital_path(
        validation,
        learned[learned["issue_year"].eq(2022)],
        expert_ids,
    )
    baseline_path = capital_path(
        validation,
        baseline[baseline["issue_year"].eq(2022)],
        expert_ids,
    )
    learned_summary = summarize_path(learned_path)
    baseline_summary = summarize_path(baseline_path)
    accepted = bool(
        learned_summary["terminal_capital_cny"]
        >= baseline_summary["terminal_capital_cny"]
        and learned_summary["max_drawdown_pct"] <= baseline_summary["max_drawdown_pct"]
    )
    source = learned if accepted else baseline
    result = source.copy()
    result["condition"] = condition
    receipt = {
        "condition": condition,
        "decision": "LEARNED" if accepted else "FROZEN_BASELINE_FALLBACK",
        "learned_validation_capital_cny": learned_summary["terminal_capital_cny"],
        "baseline_validation_capital_cny": baseline_summary["terminal_capital_cny"],
        "learned_validation_max_drawdown_pct": learned_summary["max_drawdown_pct"],
        "baseline_validation_max_drawdown_pct": baseline_summary["max_drawdown_pct"],
    }
    return result, receipt


def summarize_path(path: pd.DataFrame) -> dict[str, object]:
    """Summarize bankroll growth, drawdown and issue-level path risk."""

    if path.empty:
        raise ValueError("capital path is empty")
    closing = path["closing_capital_cny"].to_numpy(float)
    pnl = path["pnl_cny"].to_numpy(float)
    stake = path["stake_cny"].to_numpy(float)
    opening = float(path["opening_capital_cny"].iloc[0])
    peak = np.maximum.accumulate(np.r_[opening, closing])
    drawdown = 1.0 - np.r_[opening, closing] / peak
    annual = path.groupby("issue_year")["pnl_cny"].sum()
    active = path["stake_cny"].to_numpy(float) > 0
    payout = path["gross_cny"].to_numpy(float) > 0
    positive = np.clip(pnl, 0.0, None)
    contribution = (
        positive / positive.sum() if positive.sum() else np.zeros(len(positive))
    )
    hhi = float(np.square(contribution).sum())
    completed_recovery, terminal_underwater = _recovery(closing, opening)
    return {
        "condition": str(path["condition"].iloc[0]),
        "issues": int(len(path)),
        "funded_issues": int((stake > 0).sum()),
        "initial_capital_cny": opening,
        "terminal_capital_cny": float(closing[-1]),
        "capital_growth_pct": float(100.0 * (closing[-1] / opening - 1.0)),
        "stake_cny": float(stake.sum()),
        "pnl_cny": float(pnl.sum()),
        "turnover_roi_pct": float(100.0 * pnl.sum() / stake.sum())
        if stake.sum()
        else 0.0,
        "mean_deployed_capital_fraction": float(
            path["deployed_capital_fraction"].mean()
        ),
        "mean_effective_cash_fraction": float(path["effective_cash_fraction"].mean()),
        "max_drawdown_pct": float(100.0 * drawdown.max()),
        "max_drawdown_cny": float((peak - np.r_[opening, closing]).max()),
        "longest_losing_issue_streak": _longest_streak(pnl < 0),
        "longest_active_losing_issue_streak": _longest_streak(pnl[active] < 0),
        "longest_calendar_no_payout_issue_streak": _longest_streak(~payout),
        "longest_active_no_payout_issue_streak": _longest_streak(~payout[active]),
        "calendar_payout_issue_rate": float(payout.mean()),
        "active_payout_issue_rate": float(payout[active].mean())
        if active.any()
        else 0.0,
        "calendar_profitable_issue_rate": float((pnl > 0).mean()),
        "active_profitable_issue_rate": float((pnl[active] > 0).mean())
        if active.any()
        else 0.0,
        "worst_rolling_5_pnl_cny": _rolling_min(pnl, 5),
        "worst_rolling_10_pnl_cny": _rolling_min(pnl, 10),
        "worst_rolling_20_pnl_cny": _rolling_min(pnl, 20),
        "rolling_5_loss_probability": _rolling_loss_probability(pnl, 5),
        "rolling_10_loss_probability": _rolling_loss_probability(pnl, 10),
        "rolling_20_loss_probability": _rolling_loss_probability(pnl, 20),
        "positive_years": int((annual > 0).sum()),
        "largest_issue_pnl_share": float(pnl.max() / pnl.sum())
        if pnl.sum() > 0
        else np.nan,
        "ex_largest_pnl_cny": float(pnl.sum() - pnl.max()),
        "positive_contribution_hhi": hhi,
        "positive_contribution_ess": float(1.0 / hhi) if hhi else 0.0,
        "maximum_completed_recovery_issues": completed_recovery,
        "terminal_underwater_issues": terminal_underwater,
        "minimum_capital_cny": float(closing.min()),
        "ruin_boundary_hit": bool((closing <= 0).any()),
    }


def _rolling_min(values: np.ndarray, window: int) -> float:
    value = pd.Series(values).rolling(window).sum().min()
    return float(value) if np.isfinite(value) else float(values.sum())


def _longest_streak(mask: np.ndarray) -> int:
    best = current = 0
    for value in mask:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def _rolling_loss_probability(values: np.ndarray, window: int) -> float:
    sums = pd.Series(values).rolling(window).sum().dropna()
    return float(sums.lt(0).mean()) if len(sums) else float(values.sum() < 0)


def _recovery(capital: np.ndarray, opening: float) -> tuple[int, int]:
    path = np.r_[opening, capital]
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
    terminal = len(path) - underwater_start if underwater_start is not None else 0
    return longest, terminal
