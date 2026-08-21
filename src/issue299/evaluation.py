"""Discrete residual-action bankroll replay and path diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from issue296.evaluation import summarize_path

INITIAL_CAPITAL_CNY = 100_000.0
BASELINE_ACTION = "BASELINE_ONLY"


def constant_decisions(
    issue_table: pd.DataFrame, action: str, condition: str
) -> pd.DataFrame:
    """Broadcast a fixed action on the exact issue calendar."""

    return issue_table[["issue", "issue_year"]].assign(
        condition=condition,
        action=action,
        utility_cny=0.0,
        activated=action != BASELINE_ACTION,
    )


def capital_path(
    issue_table: pd.DataFrame,
    action_panel: pd.DataFrame,
    decisions: pd.DataFrame,
    *,
    initial_capital_cny: float = INITIAL_CAPITAL_CNY,
) -> pd.DataFrame:
    """Replay one whole preregistered action per issue with baseline fallback."""

    required = {"issue", "issue_year", "condition", "action"}
    if not required.issubset(decisions):
        raise ValueError(
            f"decisions missing columns: {sorted(required - set(decisions))}"
        )
    if decisions.duplicated(["issue", "issue_year"]).any():
        raise ValueError("decisions must be unique per issue")
    selected = decisions.merge(
        action_panel,
        on=["issue", "issue_year", "action"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if len(selected) != len(issue_table) or selected["_merge"].ne("both").any():
        raise ValueError("decisions and action panel do not have identical support")
    selected = selected.drop(columns="_merge")
    baseline = action_panel[action_panel["action"].eq(BASELINE_ACTION)].set_index(
        "issue"
    )
    capital = float(initial_capital_cny)
    rows: list[dict[str, object]] = []
    for row in selected.sort_values(["issue_year", "issue"]).itertuples(index=False):
        opening = capital
        requested = str(row.action)
        executed = requested
        stake = float(row.stake_cny)
        pnl = float(row.pnl_cny)
        gross = float(row.gross_cny)
        hits = float(row.hits)
        fallback_reason = "NONE"
        if not bool(row.available) or stake > opening + 1e-9:
            base = baseline.loc[int(row.issue)]
            if float(base.stake_cny) <= opening + 1e-9:
                executed = BASELINE_ACTION
                stake = float(base.stake_cny)
                pnl = float(base.pnl_cny)
                gross = float(base.gross_cny)
                hits = float(base.hits)
                fallback_reason = "RESIDUAL_UNAVAILABLE_OR_INFEASIBLE"
            else:
                executed = "CASH_INSUFFICIENT_FOR_ATOMIC_BASELINE"
                stake = pnl = gross = hits = 0.0
                fallback_reason = "BASELINE_INFEASIBLE"
        capital = opening + pnl
        if stake > opening + 1e-6 or capital < -1e-6:
            raise AssertionError("capital feasibility violated")
        rows.append(
            {
                "issue": int(row.issue),
                "issue_year": int(row.issue_year),
                "condition": str(row.condition),
                "requested_action": requested,
                "executed_action": executed,
                "fallback_reason": fallback_reason,
                "opening_capital_cny": opening,
                "stake_cny": stake,
                "pnl_cny": pnl,
                "gross_cny": gross,
                "hit_ticket_count": hits,
                "closing_capital_cny": capital,
                "deployed_capital_fraction": stake / opening if opening else 0.0,
                "effective_cash_fraction": 1.0 - stake / opening if opening else 1.0,
                "baseline_pnl_cny": float(row.pnl_cny - row.residual_pnl_cny),
                "residual_pnl_cny": pnl - float(row.pnl_cny - row.residual_pnl_cny),
                "economic_change_from_baseline": bool(
                    abs(float(row.residual_stake_cny)) > 1e-9
                ),
            }
        )
    return pd.DataFrame(rows)


def select_static_control(
    issue_table: pd.DataFrame, action_panel: pd.DataFrame
) -> tuple[str, pd.DataFrame]:
    """Select a constant residual action using 2019-2021 only."""

    train = issue_table[issue_table["issue_year"].between(2019, 2021)]
    rows = []
    for action in sorted(action_panel["action"].unique()):
        decisions = constant_decisions(train, action, f"STATIC_{action}")
        path = capital_path(
            train, action_panel[action_panel["issue"].isin(train["issue"])], decisions
        )
        summary = summarize_path(path)
        rows.append({"action": action, **summary})
    frontier = pd.DataFrame(rows).sort_values(
        ["terminal_capital_cny", "max_drawdown_pct", "action"],
        ascending=[False, True, True],
    )
    return str(frontier.iloc[0]["action"]), frontier


def oracle_decisions(
    issue_table: pd.DataFrame, action_panel: pd.DataFrame
) -> pd.DataFrame:
    """Return a non-promotable per-issue realized-P&L upper bound."""

    chosen = (
        action_panel[action_panel["available"]]
        .sort_values(
            ["issue_year", "issue", "pnl_cny", "action"],
            ascending=[True, True, False, True],
        )
        .drop_duplicates(["issue", "issue_year"])
    )
    return chosen[["issue", "issue_year", "action"]].assign(
        condition="ORACLE_DIAGNOSTIC",
        utility_cny=np.nan,
        activated=lambda value: value["action"].ne(BASELINE_ACTION),
    )


def validation_gate(
    validation_paths: dict[str, pd.DataFrame],
    seed_paths: list[pd.DataFrame],
) -> dict[str, object]:
    """Apply the preregistered 2022 no-regression conditions."""

    learned = summarize_path(validation_paths["LEARNED_RESIDUAL"])
    baseline = summarize_path(validation_paths["BEST_FULL_BASELINE"])
    seed_summaries = [summarize_path(path) for path in seed_paths]
    incremental = validation_paths["LEARNED_RESIDUAL"]["pnl_cny"].to_numpy(
        float
    ) - validation_paths["BEST_FULL_BASELINE"]["pnl_cny"].to_numpy(float)
    ex_largest_matched_lift = float(incremental.sum() - incremental.max())
    seed_positive = sum(
        item["terminal_capital_cny"] > baseline["terminal_capital_cny"]
        for item in seed_summaries
    )
    checks = {
        "terminal_capital_not_worse": learned["terminal_capital_cny"]
        >= baseline["terminal_capital_cny"],
        "max_drawdown_not_worse": learned["max_drawdown_pct"]
        <= baseline["max_drawdown_pct"],
        "worst_rolling_10_not_worse": learned["worst_rolling_10_pnl_cny"]
        >= baseline["worst_rolling_10_pnl_cny"],
        "ex_largest_matched_lift_nonnegative": ex_largest_matched_lift >= 0,
        "at_least_three_of_five_seeds_positive_lift": seed_positive >= 3,
    }
    return {
        "accepted": bool(all(checks.values())),
        "decision": "LEARNED_RESIDUAL"
        if all(checks.values())
        else "EXACT_BEST_FULL_FALLBACK",
        "checks": checks,
        "learned_validation": learned,
        "baseline_validation": baseline,
        "positive_seed_count": seed_positive,
        "matched_lift_cny": float(incremental.sum()),
        "ex_largest_matched_lift_cny": ex_largest_matched_lift,
    }


def incremental_path(challenger: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """Build the exact per-issue challenger-minus-baseline path."""

    left = challenger[
        [
            "issue",
            "issue_year",
            "pnl_cny",
            "closing_capital_cny",
            "requested_action",
            "economic_change_from_baseline",
        ]
    ].rename(
        columns={
            "pnl_cny": "challenger_pnl_cny",
            "closing_capital_cny": "challenger_capital_cny",
        }
    )
    right = baseline[["issue", "pnl_cny", "closing_capital_cny"]].rename(
        columns={
            "pnl_cny": "baseline_pnl_cny",
            "closing_capital_cny": "baseline_capital_cny",
        }
    )
    result = left.merge(right, on="issue", how="inner", validate="one_to_one")
    result["incremental_pnl_cny"] = (
        result["challenger_pnl_cny"] - result["baseline_pnl_cny"]
    )
    result["cumulative_incremental_pnl_cny"] = result["incremental_pnl_cny"].cumsum()
    result["capital_lift_cny"] = (
        result["challenger_capital_cny"] - result["baseline_capital_cny"]
    )
    result["changed_from_baseline"] = result["economic_change_from_baseline"].astype(
        bool
    )
    return result
