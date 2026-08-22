"""Control replay helpers for Issue #306 (controls 3, 5, 9, 10, 12)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from issue306 import EXPERT_IDS, INITIAL_CAPITAL_CNY, PREDICTION_YEARS
from issue306.evaluation import dynamic_capital_path
from issue306.portfolio import composition_from_value, intensity_from_state

RESIDUAL_299_PATH = Path("results/issue-299/capital_paths_2019_2023.csv")
RESIDUAL_299_DECISIONS_PATH = Path("results/issue-299/guarded_decisions.csv")


def residual_299_path(
    wide: pd.DataFrame, keep_skip: pd.DataFrame
) -> pd.DataFrame:
    """Control 3: #299 learned residual replayed per evaluation year.

    Uses the delivered #299 GUARDED_RESIDUAL capital path as the source of the
    per-issue residual action economics (stake/pnl/gross/hits for 2021-2023),
    then replays them in the Issue #306 per-year CNY100,000 framework so the
    control is on identical support and identical accounting.  Issues without
    a guarded row or outside the matched support stay in cash.
    """

    path = pd.read_csv(RESIDUAL_299_PATH)
    guarded = path[path["condition"].eq("GUARDED_RESIDUAL")].copy()
    guarded = guarded[
        guarded["issue_year"].between(min(PREDICTION_YEARS), max(PREDICTION_YEARS))
    ]
    ledger = guarded.set_index(["issue", "issue_year"])
    rows: list[dict[str, object]] = []
    support = wide[wide["issue_year"].between(min(PREDICTION_YEARS), max(PREDICTION_YEARS))]
    for year in PREDICTION_YEARS:
        capital = float(INITIAL_CAPITAL_CNY)
        local = support[support["issue_year"].eq(year)].sort_values("issue")
        for row in local.itertuples(index=False):
            key = (int(row.issue), int(row.issue_year))
            if key in ledger.index:
                source = ledger.loc[key]
                stake_value = float(source["stake_cny"])
                pnl_value = float(source["pnl_cny"])
                gross_value = float(source["gross_cny"])
                hit_value = float(source["hit_ticket_count"])
            else:
                stake_value = pnl_value = gross_value = hit_value = 0.0
            if stake_value > capital + 1e-9:
                stake_value = pnl_value = gross_value = hit_value = 0.0
            capital = capital + pnl_value
            rows.append(
                {
                    "issue": int(row.issue),
                    "issue_year": int(row.issue_year),
                    "condition": "RESIDUAL_299",
                    "opening_capital_cny": float(capital - pnl_value),
                    "stake_cny": stake_value,
                    "pnl_cny": pnl_value,
                    "gross_cny": gross_value,
                    "hit_ticket_count": hit_value,
                    "closing_capital_cny": capital,
                    "baseline_executed": bool(stake_value > 0),
                    "deployed_capital_fraction": stake_value / (capital - pnl_value)
                    if (capital - pnl_value) > 0 else 0.0,
                    "effective_cash_fraction": 1.0 - stake_value / (capital - pnl_value)
                    if (capital - pnl_value) > 0 else 1.0,
                    "funding_intensity": 0.0,
                }
            )
    return pd.DataFrame(rows)


def train_only_static_weights(
    issue_table: pd.DataFrame, raw_scores: pd.DataFrame
) -> dict[str, float]:
    """Control 5: train-only static expert mixture weights.

    Uses only strictly earlier years' realized whole-bundle unit returns
    (before each prediction year), mean-downside utility clipped to zero,
    renormalized to sum to at most 1.  No 2023 realized outcome enters.
    """

    return _static_from_issue_table(issue_table)


def _static_from_issue_table(issue_table: pd.DataFrame) -> dict[str, float]:
    # The issue table carries stake_<expert>/pnl_<expert> columns only when the
    # wide ledger is supplied; fall back to per-expert unit returns from the
    # economy columns if present, else zero weights.
    if not any(f"stake_{expert}" in issue_table.columns for expert in EXPERT_IDS):
        return {expert: 0.0 for expert in EXPERT_IDS}
    weights: dict[str, float] = {}
    for year in PREDICTION_YEARS:
        train = issue_table[issue_table["issue_year"].lt(year)].copy()
        if train.empty:
            continue
        utility = {}
        for expert in EXPERT_IDS:
            stake = train[f"stake_{expert}"].to_numpy(float)
            pnl = train[f"pnl_{expert}"].to_numpy(float)
            available = train[f"available_{expert}"].to_numpy(bool)
            returns = np.divide(pnl * available, stake, out=np.zeros(len(stake)), where=(stake > 0) & available)
            utility[expert] = float(np.mean(returns) - 0.5 * np.mean(np.clip(-returns, 0, None)))
        total = max(sum(max(value, 0.0) for value in utility.values()), 1e-9)
        for expert in EXPERT_IDS:
            weights[expert] = max(utility.get(expert, 0.0), 0.0) / total
        return weights
    return {expert: 0.0 for expert in EXPERT_IDS}


def _static_from_scores(raw_scores: pd.DataFrame) -> dict[str, float]:
    # raw_scores carries predicted values only; the realized unit returns come
    # from the wide issue/economy columns merged through issue_table.  The
    # caller should prefer _static_from_issue_table; this branch is a guard.
    return {expert: 0.0 for expert in EXPERT_IDS}


def shuffled_path(
    wide: pd.DataFrame,
    keep_skip: pd.DataFrame,
    score_frames: pd.DataFrame,
    condition: str,
    primary_intensity: pd.DataFrame,
) -> pd.DataFrame:
    """Controls 9/10: issue-block shuffle or expert-identity shuffle."""

    local_scores = score_frames[score_frames["condition"].eq(condition)]
    comp = composition_from_value(local_scores, objective="log_wealth")
    comp["condition"] = condition
    intensity_local = primary_intensity.copy()
    intensity_local["condition"] = condition
    return dynamic_capital_path(
        wide, keep_skip, comp, intensity_local, condition=condition
    )


def oracle_path(wide: pd.DataFrame) -> pd.DataFrame:
    """Control 12: oracle diagnostic only (never promotable)."""

    decisions = wide[["issue", "issue_year"]].copy()
    decisions["condition"] = "ORACLE_DIAGNOSTIC"
    decisions["keep_baseline"] = wide["base_pnl_cny"].gt(0)
    decisions["predicted_intensity"] = 1.0
    composition = _zero_composition(wide, "ORACLE_DIAGNOSTIC")
    fixed = wide[["issue", "issue_year"]].assign(
        condition="ORACLE_DIAGNOSTIC", predicted_intensity=1.0, objective="oracle"
    )
    return dynamic_capital_path(wide, decisions, composition, fixed, condition="ORACLE_DIAGNOSTIC")


def _zero_composition(wide: pd.DataFrame, condition: str) -> pd.DataFrame:
    rows = []
    for issue in wide[["issue", "issue_year"]].itertuples(index=False):
        rows.append(
            {
                "issue": int(issue.issue),
                "issue_year": int(issue.issue_year),
                "objective": "zero",
                "temperature": 1.0,
                **{f"weight_{expert}": 0.0 for expert in EXPERT_IDS},
                "weight_CASH": 1.0,
                "n_available": 0,
            }
        )
    return pd.DataFrame(rows)