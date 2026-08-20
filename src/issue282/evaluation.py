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
    selected["requested_action_key"] = selected["action_key"]
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


def choose_actions_with_baseline_guard(
    labels: pd.DataFrame,
    scores: pd.Series | np.ndarray,
    *,
    policy_name: str,
    fallback_action_key: str,
    cash_score: float = 0.0,
) -> pd.DataFrame:
    """Deviate only when the predicted action beats both baseline and cash."""

    if len(labels) != len(scores):
        raise ValueError("labels and scores must align")
    frame = labels.copy()
    frame["predicted_score"] = np.asarray(scores, dtype=float)
    rows: list[pd.Series] = []
    for _issue, issue_frame in frame.groupby("issue", sort=True):
        ranked = issue_frame.sort_values(
            ["predicted_score", "action_key"],
            ascending=[False, True],
            kind="stable",
        )
        best = ranked.iloc[0].copy()
        fallback_rows = issue_frame[issue_frame["action_key"].eq(fallback_action_key)]
        if len(fallback_rows) != 1:
            raise ValueError(
                f"fallback action {fallback_action_key} is not unique per issue"
            )
        fallback = fallback_rows.iloc[0].copy()
        best["requested_action_key"] = best["action_key"]
        best["fallback_action_key"] = fallback_action_key
        if best["predicted_score"] > max(cash_score, fallback["predicted_score"]):
            best["guard_reason"] = "MODEL_PREDICTED_LIFT"
            selected = best
        elif fallback["predicted_score"] > cash_score:
            fallback["requested_action_key"] = best["requested_action_key"]
            fallback["fallback_action_key"] = fallback_action_key
            fallback["guard_reason"] = "FROZEN_BASELINE_FALLBACK"
            selected = fallback
        else:
            best["action_key"] = "NO_BET"
            best["pnl_cny_mean"] = 0.0
            best["stake_cny_mean"] = 0.0
            best["guard_reason"] = "CASH_FALLBACK"
            selected = best
        selected["policy"] = policy_name
        rows.append(selected)
    return pd.DataFrame(rows).sort_values(["issue_year", "issue"]).reset_index(drop=True)


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


def build_attribution_ledger(
    chosen: pd.DataFrame,
    baseline: pd.DataFrame,
    all_actions: pd.DataFrame,
) -> pd.DataFrame:
    """Attach matched baseline, hindsight regret and stage-change diagnostics."""

    baseline_columns = [
        "issue",
        "action_key",
        "pnl_cny_mean",
        "selector",
        "outcome_weight_mode",
        "n",
        "generator",
        "k",
    ]
    result = chosen.merge(
        baseline[baseline_columns],
        on="issue",
        validate="one_to_one",
        suffixes=("", "_baseline"),
    )
    oracle = (
        all_actions.sort_values(
            ["issue", "pnl_cny_mean", "action_key"],
            ascending=[True, False, True],
        )
        .groupby("issue", as_index=False)
        .first()[["issue", "action_key", "pnl_cny_mean"]]
        .rename(
            columns={
                "action_key": "oracle_action_key_diagnostic",
                "pnl_cny_mean": "oracle_pnl_cny_diagnostic",
            }
        )
    )
    result = result.merge(oracle, on="issue", validate="one_to_one")
    result["matched_lift_cny"] = (
        result["pnl_cny_mean"] - result["pnl_cny_mean_baseline"]
    )
    result["oracle_regret_cny_diagnostic"] = (
        result["oracle_pnl_cny_diagnostic"] - result["pnl_cny_mean"]
    )
    for field, stage in (
        ("selector", "stage1_changed"),
        ("outcome_weight_mode", "stage2_changed"),
        ("n", "stage3_n_changed"),
        ("generator", "stage3_generator_changed"),
        ("k", "stage3_k_changed"),
    ):
        result[stage] = result[field].ne(result[f"{field}_baseline"])
    result["fallback_reason"] = np.where(
        result["action_key"].eq("NO_BET"),
        "PREDICTED_SCORE_NONPOSITIVE",
        "FUNDED_MODEL_ACTION",
    )
    changed_fields = [
        "stage1_changed",
        "stage2_changed",
        "stage3_n_changed",
        "stage3_generator_changed",
        "stage3_k_changed",
    ]
    result["changed_stage_count"] = result[changed_fields].sum(axis=1)
    result["matched_failure_attribution"] = "NO_NEGATIVE_MATCHED_LIFT"
    negative = result["matched_lift_cny"].lt(0)
    result.loc[negative & result["changed_stage_count"].gt(1), "matched_failure_attribution"] = (
        "JOINT_STAGE_CHANGE"
    )
    for field, label in (
        ("stage1_changed", "STAGE1_SELECTION_ONLY"),
        ("stage2_changed", "STAGE2_OUTCOME_ONLY"),
        ("stage3_n_changed", "STAGE3_N_ONLY"),
        ("stage3_generator_changed", "STAGE3_GENERATOR_ONLY"),
        ("stage3_k_changed", "STAGE3_K_ONLY"),
    ):
        result.loc[
            negative & result["changed_stage_count"].eq(1) & result[field],
            "matched_failure_attribution",
        ] = label
    return add_capital_curve(result)


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
