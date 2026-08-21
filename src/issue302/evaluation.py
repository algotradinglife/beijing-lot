"""Atomic baseline plus dynamic whole-bundle expert bankroll replay."""

from __future__ import annotations

import numpy as np
import pandas as pd

from issue296.evaluation import summarize_path
from issue302.panel import EXPERT_IDS

INITIAL_CAPITAL_CNY = 100_000.0
BASELINE_ID = "B0_BEST_FULL"


def decisions_from_scores(scores: pd.DataFrame) -> pd.DataFrame:
    """Convert Q estimates to atomic keep/skip plus expert/cash fractions."""

    rows: list[dict[str, object]] = []
    for (issue, year), local in scores.groupby(["issue", "issue_year"], sort=True):
        base = local[local["action_id"].eq(BASELINE_ID)].iloc[0]
        expert = local[local["action_id"].isin(EXPERT_IDS)].copy()
        keep = bool(base.utility_cny > 0 and base.available)
        mean = expert["predicted_pnl_cny"].to_numpy(float)
        downside = expert["predicted_downside_cny"].to_numpy(float)
        loss_probability = expert["predicted_loss_probability"].to_numpy(float)
        uncertainty = expert["predicted_pnl_std_cny"].to_numpy(float)
        stake = np.maximum(expert["stake_unit_cny"].to_numpy(float), 1.0)
        # A whole-bundle Kelly proxy: predicted reward divided by estimated
        # second moment. Cross-seed disagreement is explicitly risk, not alpha.
        allocation = np.maximum(mean, 0.0) * stake / (
            np.square(uncertainty)
            + loss_probability * np.square(downside)
            + 0.01 * np.square(stake)
        )
        allocation *= expert["available"].to_numpy(bool)
        allocation /= max(1.0, float(allocation.sum()))
        row: dict[str, object] = {
            "issue": int(issue), "issue_year": int(year),
            "condition": str(local["condition"].iloc[0]),
            "keep_baseline": keep,
            "predicted_baseline_utility_cny": float(base.utility_cny),
            "weight_CASH": 1.0 - float(allocation.sum()),
        }
        for action, weight in zip(expert["action_id"], allocation, strict=True):
            row[f"weight_{action}"] = float(weight)
        rows.append(row)
    return pd.DataFrame(rows)


def scale_expert_weights(decisions: pd.DataFrame, scale: float, condition: str) -> pd.DataFrame:
    """Apply one causally selected funding scalar to an existing dynamic policy."""

    if not 0.0 <= scale <= 1.0:
        raise ValueError("expert funding scale must be in [0, 1]")
    result = decisions.copy()
    for expert in EXPERT_IDS:
        result[f"weight_{expert}"] *= scale
    result["weight_CASH"] = 1.0 - result[[f"weight_{x}" for x in EXPERT_IDS]].sum(axis=1)
    result["condition"] = condition
    result["expert_funding_scale"] = scale
    return result


def constant_decisions(
    issues: pd.DataFrame, *, condition: str, keep_baseline: bool,
    expert_weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    weights = expert_weights or {}
    if sum(weights.values()) > 1 + 1e-9:
        raise ValueError("expert allocation exceeds bankroll")
    frame = issues[["issue", "issue_year"]].copy()
    frame["condition"] = condition
    frame["keep_baseline"] = keep_baseline
    frame["predicted_baseline_utility_cny"] = 0.0
    for expert in EXPERT_IDS:
        frame[f"weight_{expert}"] = float(weights.get(expert, 0.0))
    frame["weight_CASH"] = 1.0 - sum(weights.values())
    return frame


def capital_path(
    issues: pd.DataFrame, actions: pd.DataFrame, decisions: pd.DataFrame,
    *, initial_capital_cny: float = INITIAL_CAPITAL_CNY,
) -> pd.DataFrame:
    """Execute baseline once, then allocate only remaining cash to expert bundles."""

    merged = issues.merge(decisions, on=["issue", "issue_year"], validate="one_to_one")
    lookup = actions.set_index(["issue", "action_id"])
    capital = float(initial_capital_cny)
    rows: list[dict[str, object]] = []
    for row in merged.sort_values(["issue_year", "issue"]).itertuples(index=False):
        opening = capital
        stake = pnl = gross = hits = 0.0
        base = lookup.loc[(int(row.issue), BASELINE_ID)]
        baseline_executed = bool(row.keep_baseline) and float(base.stake_unit_cny) <= opening
        if baseline_executed:
            stake += float(base.stake_unit_cny)
            pnl += float(base.pnl_unit_cny)
            gross += float(base.gross_unit_cny)
            hits += float(base.hit_count)
        remaining = opening - stake
        allocations: dict[str, object] = {}
        for expert in EXPERT_IDS:
            unit = lookup.loc[(int(row.issue), expert)]
            desired = remaining * float(getattr(row, f"weight_{expert}"))
            copies = (
                int(np.floor(desired / float(unit.stake_unit_cny)))
                if bool(unit.available) and float(unit.stake_unit_cny) > 0 else 0
            )
            local_stake = copies * float(unit.stake_unit_cny)
            local_pnl = copies * float(unit.pnl_unit_cny)
            stake += local_stake
            pnl += local_pnl
            gross += copies * float(unit.gross_unit_cny)
            hits += copies * float(unit.hit_count)
            allocations[f"copies_{expert}"] = copies
            allocations[f"stake_{expert}"] = local_stake
            allocations[f"pnl_{expert}"] = local_pnl
        if stake > opening + 1e-6:
            raise AssertionError("allocation exceeded opening bankroll")
        capital = opening + pnl
        if capital < -1e-6:
            raise AssertionError("bankroll became negative")
        rows.append({
            "issue": int(row.issue), "issue_year": int(row.issue_year),
            "condition": str(row.condition), "opening_capital_cny": opening,
            "stake_cny": stake, "pnl_cny": pnl, "gross_cny": gross,
            "hit_ticket_count": hits, "closing_capital_cny": capital,
            "baseline_executed": baseline_executed,
            "deployed_capital_fraction": stake / opening if opening else 0.0,
            "effective_cash_fraction": 1.0 - stake / opening if opening else 1.0,
            **allocations,
        })
    return pd.DataFrame(rows)


def summarize(path: pd.DataFrame) -> dict[str, object]:
    return summarize_path(path)
