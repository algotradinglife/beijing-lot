"""Policy selection and path diagnostics for Issue #292."""

from __future__ import annotations

import numpy as np
import pandas as pd

INITIAL_CAPITAL = 100_000.0


def average_seed_predictions(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Average fitted-model predictions while preserving action identity."""

    if not frames:
        raise ValueError("at least one prediction frame is required")
    identity = [
        "issue",
        "issue_year",
        "temporal_role",
        "action_key",
        "n",
        "k",
        "generator",
    ]
    values = [
        "predicted_mean_utility_bps",
        "predicted_positive_probability",
        "predicted_positive_pnl",
        "predicted_nonpositive_pnl",
        "predicted_q10_utility_bps",
        "predicted_risk_score",
    ]
    stacked = pd.concat(
        [frame.assign(model_seed_index=index) for index, frame in enumerate(frames)],
        ignore_index=True,
    )
    expected = len(frames)
    counts = stacked.groupby(identity)["model_seed_index"].nunique()
    if not counts.eq(expected).all():
        raise ValueError("model-seed prediction support is not identical")
    return stacked.groupby(identity, as_index=False)[values].mean()


def attach_action_economics(
    predictions: pd.DataFrame,
    actual: pd.DataFrame,
) -> pd.DataFrame:
    """Attach pre-event stake and post-selection outcomes to predictions."""

    columns = [
        "issue",
        "action_key",
        "stake_total",
        "mean_pnl",
        "pnl_seed_q10",
        "mean_hit_rate",
    ]
    result = predictions.merge(
        actual[columns], on=["issue", "action_key"], how="left", validate="one_to_one"
    )
    if result[["stake_total", "mean_pnl"]].isna().any(axis=None):
        raise ValueError("prediction/action economics support mismatch")
    predicted_mean_pnl = INITIAL_CAPITAL * np.expm1(
        result["predicted_mean_utility_bps"] / 10_000.0
    )
    predicted_q10_pnl = INITIAL_CAPITAL * np.expm1(
        result["predicted_q10_utility_bps"] / 10_000.0
    )
    physical_floor = -result["stake_total"].to_numpy(float)
    predicted_mean_pnl = np.maximum(predicted_mean_pnl, physical_floor)
    predicted_q10_pnl = np.maximum(predicted_q10_pnl, physical_floor)
    stake = result["stake_total"].replace(0.0, np.nan)
    result["predicted_mean_roi"] = (predicted_mean_pnl / stake).fillna(0.0)
    result["predicted_q10_roi"] = (predicted_q10_pnl / stake).fillna(0.0)
    return result


def select_single_sleeve(
    frame: pd.DataFrame,
    *,
    policy: str,
    n_min: int,
    n_max: int,
    score_column: str,
    threshold: float,
    threshold_column: str,
) -> pd.DataFrame:
    """Select one active action or cash per issue from predictions only."""

    active = frame[frame["n"].between(n_min, n_max)].copy()
    selected = (
        active.sort_values(
            ["issue", score_column, "action_key"],
            ascending=[True, False, True],
            kind="stable",
        )
        .groupby("issue", as_index=False)
        .first()
    )
    funded = selected[threshold_column].ge(threshold)
    selected["funded"] = funded
    selected["selected_action_key"] = np.where(
        funded, selected["action_key"], "CASH_NO_BET"
    )
    selected["selected_n"] = np.where(funded, selected["n"], 0).astype(int)
    selected["selected_k"] = np.where(funded, selected["k"], 0).astype(int)
    selected["selected_generator"] = np.where(funded, selected["generator"], "NO_BET")
    selected["stake_cny"] = np.where(funded, selected["stake_total"], 0.0)
    selected["pnl_cny"] = np.where(funded, selected["mean_pnl"], 0.0)
    selected["pnl_seed_q10_cny"] = np.where(funded, selected["pnl_seed_q10"], 0.0)
    selected["hit_rate"] = np.where(funded, selected["mean_hit_rate"], 0.0)
    selected["policy"] = policy
    return selected


def combine_sleeves(
    core: pd.DataFrame, tail: pd.DataFrame, *, policy: str
) -> pd.DataFrame:
    """Combine disjoint core/tail action sleeves issue by issue."""

    columns = [
        "issue",
        "issue_year",
        "selected_action_key",
        "selected_n",
        "selected_k",
        "selected_generator",
        "funded",
        "stake_cny",
        "pnl_cny",
        "pnl_seed_q10_cny",
        "hit_rate",
    ]
    merged = core[columns].merge(
        tail[columns],
        on=["issue", "issue_year"],
        how="inner",
        validate="one_to_one",
        suffixes=("_core", "_tail"),
    )
    merged["policy"] = policy
    merged["stake_cny"] = merged["stake_cny_core"] + merged["stake_cny_tail"]
    merged["pnl_cny"] = merged["pnl_cny_core"] + merged["pnl_cny_tail"]
    merged["pnl_seed_q10_cny"] = (
        merged["pnl_seed_q10_cny_core"] + merged["pnl_seed_q10_cny_tail"]
    )
    merged["funded"] = merged["funded_core"] | merged["funded_tail"]
    merged["tail_capital_fraction"] = np.divide(
        merged["stake_cny_tail"],
        merged["stake_cny"],
        out=np.zeros(len(merged), dtype=float),
        where=merged["stake_cny"].gt(0),
    )
    return merged


def select_capped_tail_sleeve(
    frame: pd.DataFrame,
    core: pd.DataFrame,
    *,
    policy: str,
    threshold: float,
    maximum_fraction: float,
) -> pd.DataFrame:
    """Choose a high-N action that fits a physical tail-capital fraction."""

    if not 0.0 < maximum_fraction < 1.0:
        raise ValueError("maximum_fraction must be strictly between zero and one")
    core_budget = core[["issue", "stake_cny", "funded"]].rename(
        columns={"stake_cny": "core_stake_cny", "funded": "core_funded"}
    )
    candidates = frame[frame["n"].between(7, 10)].merge(
        core_budget, on="issue", how="inner", validate="many_to_one"
    )
    maximum_tail = (
        maximum_fraction / (1.0 - maximum_fraction) * candidates["core_stake_cny"]
    )
    candidates = candidates[
        candidates["core_funded"].astype(bool)
        & candidates["stake_total"].le(maximum_tail + 1e-9)
    ].copy()
    selected = (
        candidates.sort_values(
            ["issue", "predicted_mean_roi", "action_key"],
            ascending=[True, False, True],
            kind="stable",
        )
        .groupby("issue", as_index=False)
        .first()
    )
    selected = core[["issue", "issue_year"]].merge(
        selected, on=["issue", "issue_year"], how="left", validate="one_to_one"
    )
    funded = selected["predicted_mean_roi"].ge(threshold).fillna(False)
    selected["funded"] = funded
    selected["selected_action_key"] = np.where(
        funded, selected["action_key"], "CASH_NO_BET"
    )
    selected["selected_n"] = np.where(funded, selected["n"].fillna(0), 0).astype(int)
    selected["selected_k"] = np.where(funded, selected["k"].fillna(0), 0).astype(int)
    selected["selected_generator"] = np.where(funded, selected["generator"], "NO_BET")
    selected["stake_cny"] = np.where(funded, selected["stake_total"], 0.0)
    selected["pnl_cny"] = np.where(funded, selected["mean_pnl"], 0.0)
    selected["pnl_seed_q10_cny"] = np.where(funded, selected["pnl_seed_q10"], 0.0)
    selected["hit_rate"] = np.where(funded, selected["mean_hit_rate"], 0.0)
    selected["policy"] = policy
    return selected


def capital_path(frame: pd.DataFrame) -> pd.DataFrame:
    """Return an issue-ordered CNY100k capital path."""

    result = frame.copy()
    result["issue_numeric"] = pd.to_numeric(result["issue"], errors="raise")
    result = result.sort_values(["issue_year", "issue_numeric"]).reset_index(drop=True)
    result["capital_cny"] = INITIAL_CAPITAL + result["pnl_cny"].cumsum()
    return result


def summarize_policy(frame: pd.DataFrame) -> dict[str, object]:
    """Summarize actual capital, tail dependence and holding feasibility."""

    path = capital_path(frame)
    pnl = path["pnl_cny"].to_numpy(float)
    stake = path["stake_cny"].to_numpy(float)
    capital = path["capital_cny"].to_numpy(float)
    peaks = np.maximum.accumulate(np.r_[INITIAL_CAPITAL, capital])
    drawdown = 1.0 - np.r_[INITIAL_CAPITAL, capital] / peaks
    largest = float(pnl.max()) if len(pnl) else 0.0
    total_stake = float(stake.sum())
    annual = path.groupby("issue_year")["pnl_cny"].sum()
    tail_fraction = path.get(
        "tail_capital_fraction", pd.Series(0.0, index=path.index)
    ).fillna(0.0)
    funded_tail_fraction = tail_fraction[path["funded"].astype(bool)]
    tail_stake = path.get("stake_cny_tail", pd.Series(0.0, index=path.index)).fillna(
        0.0
    )
    return {
        "policy": str(path["policy"].iloc[0]),
        "issues": int(path["issue"].nunique()),
        "funded_issues": int(path["funded"].sum()),
        "stake_cny": total_stake,
        "pnl_cny": float(pnl.sum()),
        "roi_pct": float(100.0 * pnl.sum() / total_stake) if total_stake else 0.0,
        "ex_largest_pnl_cny": float(pnl.sum() - largest),
        "positive_years": int((annual > 0).sum()),
        "max_drawdown_pct": float(drawdown.max() * 100.0),
        "longest_losing_issue_streak": _longest_loss_streak(pnl),
        "worst_rolling_5_pnl_cny": _rolling_min(pnl, 5),
        "worst_rolling_10_pnl_cny": _rolling_min(pnl, 10),
        "worst_rolling_20_pnl_cny": _rolling_min(pnl, 20),
        "maximum_completed_recovery_issues": _recovery(capital)[0],
        "open_terminal_underwater_issues": _recovery(capital)[1],
        "mean_tail_capital_fraction": float(funded_tail_fraction.mean())
        if len(funded_tail_fraction)
        else 0.0,
        "maximum_tail_capital_fraction": float(tail_fraction.max()),
        "total_tail_capital_fraction": float(tail_stake.sum() / total_stake)
        if total_stake
        else 0.0,
    }


def _rolling_min(values: np.ndarray, window: int) -> float:
    result = pd.Series(values).rolling(window).sum().min()
    return float(result) if np.isfinite(result) else float(values.sum())


def _longest_loss_streak(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
    return longest


def _recovery(capital: np.ndarray) -> tuple[int, int]:
    path = np.r_[INITIAL_CAPITAL, capital]
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
    open_underwater = (
        len(path) - underwater_start if underwater_start is not None else 0
    )
    return longest, open_underwater
