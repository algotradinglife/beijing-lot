"""Issue-level policy selection and capital-path diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd

INITIAL_CAPITAL_CNY = 100_000.0


def choose_actions(
    labels: pd.DataFrame,
    scores: pd.Series | np.ndarray,
    *,
    policy_name: str,
    no_bet_threshold: float = 0.0,
) -> pd.DataFrame:
    """Choose one complete action per issue, with cash as an explicit fallback."""

    if len(labels) != len(scores):
        raise ValueError("labels and scores must align")
    frame = labels.copy()
    frame["predicted_score"] = np.asarray(scores, dtype=float)
    frame = frame.sort_values(
        ["issue", "predicted_score", "action_key"],
        ascending=[True, False, True],
        kind="stable",
    )
    selected = frame.groupby("issue", sort=True, as_index=False).first()
    no_bet = selected["predicted_score"].le(no_bet_threshold)
    selected.loc[no_bet, "action_key"] = "NO_BET"
    selected.loc[no_bet, "pnl_cny_mean"] = 0.0
    selected.loc[no_bet, "stake_cny_mean"] = 0.0
    selected["policy"] = policy_name
    return selected.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def fixed_action_ledger(
    labels: pd.DataFrame, *, action_key: str, policy_name: str
) -> pd.DataFrame:
    """Extract a fixed matched action on exactly one row per issue."""

    selected = labels[labels["action_key"].eq(action_key)].copy()
    expected_issues = labels["issue"].nunique()
    if len(selected) != expected_issues or selected["issue"].nunique() != expected_issues:
        raise ValueError(f"fixed action {action_key} is not supported on every issue")
    selected["predicted_score"] = np.nan
    selected["policy"] = policy_name
    return selected.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def capital_path_metrics(
    ledger: pd.DataFrame,
    *,
    baseline: pd.DataFrame | None = None,
    initial_capital_cny: float = INITIAL_CAPITAL_CNY,
) -> dict[str, float | int | bool]:
    """Summarize holding feasibility at the Beijing-issue granularity."""

    if initial_capital_cny <= 0 or ledger.empty:
        raise ValueError("capital and ledger must be nonempty and positive")
    ordered = ledger.sort_values(["issue_year", "issue"]).reset_index(drop=True)
    pnl = ordered["pnl_cny_mean"].to_numpy(dtype=float)
    capital = initial_capital_cny + np.cumsum(pnl)
    peak = np.maximum.accumulate(np.r_[initial_capital_cny, capital])[:-1]
    drawdown = np.divide(
        capital - peak,
        peak,
        out=np.zeros_like(capital),
        where=peak > 0,
    )
    result: dict[str, float | int | bool] = {
        "issues": len(ordered),
        "ending_capital_cny": float(capital[-1]),
        "total_pnl_cny": float(pnl.sum()),
        "turnover_cny": float(ordered["stake_cny_mean"].sum()),
        "positive_issues": int((pnl > 0).sum()),
        "bet_issues": int(ordered["stake_cny_mean"].gt(0).sum()),
        "max_drawdown_fraction": float(-drawdown.min(initial=0.0)),
        "max_consecutive_losing_issues": _max_consecutive(pnl < 0),
        "max_recovery_issues": _max_recovery(capital, initial_capital_cny),
    }
    for window in (5, 10, 20):
        rolling = pd.Series(pnl).rolling(window).sum().dropna()
        result[f"rolling_{window}_loss_probability"] = (
            float(rolling.lt(0).mean()) if len(rolling) else float("nan")
        )
        result[f"rolling_{window}_worst_pnl_cny"] = (
            float(rolling.min()) if len(rolling) else float("nan")
        )
    if baseline is not None:
        comparison = ordered[["issue", "pnl_cny_mean", "action_key"]].merge(
            baseline[["issue", "pnl_cny_mean", "action_key"]],
            on="issue",
            validate="one_to_one",
            suffixes=("", "_baseline"),
        )
        lift = (
            comparison["pnl_cny_mean"] - comparison["pnl_cny_mean_baseline"]
        ).to_numpy(dtype=float)
        positive_lift = lift[lift > 0]
        total_positive = positive_lift.sum()
        result.update(
            {
                "matched_lift_cny": float(lift.sum()),
                "ex_largest_matched_lift_cny": float(
                    lift.sum() - positive_lift.max(initial=0.0)
                ),
                "largest_issue_positive_lift_share": float(
                    positive_lift.max(initial=0.0) / total_positive
                    if total_positive > 0
                    else 0.0
                ),
                "changed_action_issues": int(
                    comparison["action_key"].ne(comparison["action_key_baseline"]).sum()
                ),
            }
        )
    return result


def add_capital_curve(
    ledger: pd.DataFrame, *, initial_capital_cny: float = INITIAL_CAPITAL_CNY
) -> pd.DataFrame:
    result = ledger.sort_values(["issue_year", "issue"]).reset_index(drop=True).copy()
    result["capital_cny"] = initial_capital_cny + result["pnl_cny_mean"].cumsum()
    return result


def _max_consecutive(condition: np.ndarray) -> int:
    longest = current = 0
    for value in condition:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return int(longest)


def _max_recovery(capital: np.ndarray, initial: float) -> int:
    peak = initial
    underwater_since: int | None = None
    longest = 0
    for index, value in enumerate(capital, start=1):
        if value >= peak:
            if underwater_since is not None:
                longest = max(longest, index - underwater_since)
                underwater_since = None
            peak = value
        elif underwater_since is None:
            underwater_since = index - 1
    if underwater_since is not None:
        longest = max(longest, len(capital) - underwater_since)
    return int(longest)
