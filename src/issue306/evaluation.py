"""Replay, controls, and long-tail diagnostics for Issue #306.

The dynamic policy is executed as:

1. Stage A decides keep/skip for the exact atomic BEST_FULL (frozen).
2. Stage C composition weights decide the relative expert mix.
3. Stage C intensity decides how much of the current bankroll the expert mix
   may use; integer copies of complete bundles are floor-rounded so total
   stake never exceeds intensity x bankroll.
4. Remaining capital stays in cash.

All twelve Issue-#306 controls are produced as replay tables on identical
support and CNY100,000 pre-tax bankroll.  Long-tail diagnostics (tail-capture
probabilities, holding-window capture, survival) are computed from the same
replays.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from issue296.evaluation import summarize_path

from issue306 import BASELINE_ID, EXPERT_IDS, INITIAL_CAPITAL_CNY
from issue306.portfolio import allocate_integer_bundles


def wide_issue_ledger(issues: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    """One wide row per issue with per-expert bundle economics and availability."""

    wide = issues[["issue", "issue_year", "baseline_active"]].copy()
    lookup = actions.set_index(["issue", "action_id"])
    for expert in EXPERT_IDS:
        selected = lookup.loc[(slice(None), expert), ["stake_unit_cny", "pnl_unit_cny", "gross_unit_cny", "available"]]
        selected = selected.reset_index().set_index("issue")
        wide = wide.merge(
            selected.rename(
                columns={
                    "stake_unit_cny": f"stake_{expert}",
                    "pnl_unit_cny": f"pnl_{expert}",
                    "gross_unit_cny": f"gross_{expert}",
                    "available": f"available_{expert}",
                }
            ).drop(columns="action_id"),
            on="issue",
            how="left",
            validate="one_to_one",
        )
    base = lookup.loc[(slice(None), BASELINE_ID), ["stake_unit_cny", "pnl_unit_cny", "gross_unit_cny", "hit_count"]].reset_index().set_index("issue")
    wide = wide.merge(
        base.rename(
            columns={
                "stake_unit_cny": "base_stake_cny",
                "pnl_unit_cny": "base_pnl_cny",
                "gross_unit_cny": "base_gross_cny",
                "hit_count": "base_hits",
            }
        ).drop(columns="action_id"),
        on="issue",
        how="left",
        validate="one_to_one",
    )
    return wide.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def dynamic_capital_path(
    wide: pd.DataFrame,
    keep_skip: pd.DataFrame,
    composition: pd.DataFrame,
    intensity: pd.DataFrame,
    *,
    initial_capital_cny: float = INITIAL_CAPITAL_CNY,
    condition: str = "DYNAMIC_EXPERT_POLICY",
) -> pd.DataFrame:
    """Replay the fully dynamic composition + intensity policy."""

    comp_map = composition.set_index(["issue", "issue_year"])
    int_map = intensity.set_index(["issue", "issue_year"])["predicted_intensity"]
    merged = wide.merge(
        keep_skip[["issue", "issue_year", "keep_baseline"]],
        on=["issue", "issue_year"], validate="one_to_one",
    )
    capital = float(initial_capital_cny)
    rows: list[dict[str, object]] = []
    for row in merged.sort_values(["issue_year", "issue"]).itertuples(index=False):
        opening = capital
        stake = pnl = gross = hits = 0.0
        if bool(row.keep_baseline) and float(row.base_stake_cny) <= opening + 1e-9:
            stake += float(row.base_stake_cny)
            pnl += float(row.base_pnl_cny)
            gross += float(row.base_gross_cny)
            hits += float(row.base_hits)
        comp = comp_map.loc[(int(row.issue), int(row.issue_year))]
        intensity_value = float(int_map.loc[(int(row.issue), int(row.issue_year))])
        expert_budget = opening - stake
        allocation = allocate_integer_bundles(
            row, comp, intensity_value, initial_capital_cny=expert_budget
        )
        stake += float(allocation["stake_cny"])
        pnl += float(allocation["pnl_cny"])
        gross += float(allocation["gross_cny"])
        if stake > opening + 1e-6:
            raise AssertionError("allocation exceeded opening bankroll")
        capital = opening + pnl
        if capital < -1e-6:
            raise AssertionError("bankroll became negative")
        total_keys = ("stake_cny", "pnl_cny", "gross_cny")
        expert_fields = {
            key: value for key, value in allocation.items() if key not in total_keys
        }
        rows.append(
            {
                "issue": int(row.issue),
                "issue_year": int(row.issue_year),
                "condition": condition,
                "opening_capital_cny": opening,
                "stake_cny": stake,
                "pnl_cny": pnl,
                "gross_cny": gross,
                "hit_ticket_count": hits,
                "closing_capital_cny": capital,
                "baseline_executed": bool(row.keep_baseline),
                "deployed_capital_fraction": stake / opening if opening else 0.0,
                "effective_cash_fraction": 1.0 - stake / opening if opening else 1.0,
                "funding_intensity": intensity_value,
                **expert_fields,
            }
        )
    return pd.DataFrame(rows)


def constant_intensity_capital_path(
    wide: pd.DataFrame,
    keep_skip: pd.DataFrame,
    composition: pd.DataFrame,
    intensity_value: float,
    *,
    condition: str = "FIXED_INTENSITY",
) -> pd.DataFrame:
    """Replay a learned composition with one fixed funding intensity."""

    fixed = wide[["issue", "issue_year"]].assign(
        condition=condition, predicted_intensity=intensity_value, objective="fixed"
    )
    return dynamic_capital_path(
        wide, keep_skip, composition, fixed, condition=condition
    )


def constant_composition_capital_path(
    wide: pd.DataFrame,
    keep_skip: pd.DataFrame,
    intensity: pd.DataFrame,
    weights: dict[str, float],
    *,
    condition: str = "FIXED_COMPOSITION",
) -> pd.DataFrame:
    """Replay learned intensity with one fixed expert composition."""

    comp = _constant_composition(wide, weights, condition)
    return dynamic_capital_path(wide, keep_skip, comp, intensity, condition=condition)


def static_mixture_capital_path(
    wide: pd.DataFrame,
    keep_skip: pd.DataFrame,
    weights: dict[str, float],
    intensity_value: float = 1.0,
    *,
    condition: str = "STATIC_EXPERT_MIXTURE",
) -> pd.DataFrame:
    """Replay a train-only static mixture with Stage-A keep/skip."""

    comp = _constant_composition(wide, weights, condition)
    fixed = wide[["issue", "issue_year"]].assign(
        condition=condition, predicted_intensity=intensity_value, objective="static"
    )
    return dynamic_capital_path(wide, keep_skip, comp, fixed, condition=condition)


def constant_decisions(
    wide: pd.DataFrame,
    *,
    condition: str,
    keep_baseline: bool,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Build a constant decision frame (cash, B0, or static mixture)."""

    weights = weights or {}
    frame = wide[["issue", "issue_year"]].copy()
    frame["condition"] = condition
    frame["keep_baseline"] = keep_baseline
    frame["predicted_intensity"] = 1.0
    for expert in EXPERT_IDS:
        frame[f"weight_{expert}"] = float(weights.get(expert, 0.0))
    frame["weight_CASH"] = 1.0 - sum(weights.values())
    return frame


def _constant_composition(
    wide: pd.DataFrame, weights: dict[str, float], condition: str
) -> pd.DataFrame:
    rows = []
    for issue in wide[["issue", "issue_year"]].itertuples(index=False):
        row: dict[str, object] = {
            "issue": int(issue.issue),
            "issue_year": int(issue.issue_year),
            "objective": "static",
            "temperature": 1.0,
        }
        for expert in EXPERT_IDS:
            row[f"weight_{expert}"] = float(weights.get(expert, 0.0))
        row["weight_CASH"] = 1.0 - float(sum(weights.values()))
        row["n_available"] = int(
            wide.loc[
                wide["issue"].eq(int(issue.issue)),
                [f"available_{expert}" for expert in EXPERT_IDS],
            ].to_numpy(bool).sum()
        )
        rows.append(row)
    return pd.DataFrame(rows)


def cash_path(
    wide: pd.DataFrame, *, condition: str = "CASH"
) -> pd.DataFrame:
    """Pure cash replay: no baseline, no experts, no stake."""

    rows = []
    capital = float(INITIAL_CAPITAL_CNY)
    for row in wide.sort_values(["issue_year", "issue"]).itertuples(index=False):
        rows.append(
            {
                "issue": int(row.issue),
                "issue_year": int(row.issue_year),
                "condition": condition,
                "opening_capital_cny": capital,
                "stake_cny": 0.0,
                "pnl_cny": 0.0,
                "gross_cny": 0.0,
                "hit_ticket_count": 0,
                "closing_capital_cny": capital,
                "baseline_executed": False,
                "deployed_capital_fraction": 0.0,
                "effective_cash_fraction": 1.0,
                "funding_intensity": 0.0,
            }
        )
    return pd.DataFrame(rows)


def baseline_keep_all_path(
    wide: pd.DataFrame, keep_skip: pd.DataFrame, *, condition: str = "B0_BEST_FULL"
) -> pd.DataFrame:
    """Exact B0_BEST_FULL: keep every active atomic bundle, zero experts."""

    decisions = wide[["issue", "issue_year"]].assign(
        condition=condition, keep_baseline=True, predicted_intensity=0.0
    )
    composition = _constant_composition(wide, {}, condition)
    fixed = wide[["issue", "issue_year"]].assign(
        condition=condition, predicted_intensity=0.0, objective="b0"
    )
    return dynamic_capital_path(wide, decisions, composition, fixed, condition=condition)


def stage_a_keep_skip_path(
    wide: pd.DataFrame, keep_skip: pd.DataFrame, *, condition: str = "STAGE_A_KEEP_SKIP"
) -> pd.DataFrame:
    """#305 corrected dedicated keep/skip alone: no expert funding."""

    composition = _constant_composition(wide, {}, condition)
    fixed = wide[["issue", "issue_year"]].assign(
        condition=condition, predicted_intensity=0.0, objective="stage_a"
    )
    return dynamic_capital_path(wide, keep_skip, composition, fixed, condition=condition)


def summarize(path: pd.DataFrame) -> dict[str, object]:
    return summarize_path(path)


def tail_capture_metrics(path: pd.DataFrame) -> dict[str, object]:
    """Long-tail capture diagnostics on one replay path.

    Thresholds are predeclared on gross/stake multiples and capital-gain
    multiples; holding-window capture uses rolling 5/10/20-issue windows.
    """

    if path.empty:
        raise ValueError("tail path is empty")
    stake = path["stake_cny"].to_numpy(float)
    gross = path["gross_cny"].to_numpy(float)
    pnl = path["pnl_cny"].to_numpy(float)
    ratio = np.divide(gross, stake, out=np.zeros(len(stake)), where=stake > 0)
    gain_ratio = np.divide(pnl, stake, out=np.zeros(len(stake)), where=stake > 0)
    result: dict[str, object] = {
        "any_payout_issue_rate": float((gross > 0).mean()),
        "positive_pnl_issue_rate": float((pnl > 0).mean()),
        "largest_single_issue_gross_cny": float(gross.max()),
        "largest_single_issue_pnl_cny": float(pnl.max()),
    }
    for multiple in (2.0, 5.0, 10.0):
        result[f"tail_gross_{multiple:g}_issue_probability"] = float((ratio >= multiple).mean())
    for multiple in (0.5, 1.0, 2.0):
        result[f"tail_gain_{multiple:g}_issue_probability"] = float((gain_ratio >= multiple).mean())
    for window in (5, 10, 20):
        rolled = pd.Series(gross).rolling(window).apply(
            lambda values: 1.0 if (np.asarray(values) > 0).any() else 0.0, raw=True
        ).dropna()
        result[f"tail_capture_window_{window}_probability"] = float(rolled.mean()) if len(rolled) else 0.0
    return result


def exact_executed_exposure_null(
    wide: pd.DataFrame,
    policy_path: pd.DataFrame,
    *,
    year: int = 2023,
    replicates: int = 500,
    seed_base: int = 306_000,
) -> pd.DataFrame:
    """Null: place the same bundle copies/stakes only among active issues.

    For each replicate the observed per-issue baseline keep/skip and expert
    bundle copies are re-assigned to random active destination issues of the
    same year, preserving funded count, stakes, and exact executed exposure.
    """

    local = policy_path[policy_path["issue_year"].eq(year)].reset_index(drop=True)
    active = wide[wide["issue_year"].eq(year) & wide["baseline_active"].eq(1)].reset_index(drop=True)
    rows = []
    for replicate in range(replicates):
        rng = np.random.default_rng(seed_base + replicate)
        funded = local[local["stake_cny"].gt(0)]
        if funded.empty or active.empty:
            terminal = INITIAL_CAPITAL_CNY
        else:
            destination = active.sample(n=len(funded), replace=False, random_state=seed_base + replicate)
            pnl = 0.0
            for expert in EXPERT_IDS:
                pnl += float(
                    (
                        funded[f"copies_{expert}"].to_numpy(float)
                        * destination[f"pnl_{expert}"].to_numpy(float)
                    ).sum()
                )
            pnl += float(
                (
                    funded["baseline_executed"].to_numpy(bool).astype(float)
                    * destination["base_pnl_cny"].to_numpy(float)
                ).sum()
            )
            terminal = INITIAL_CAPITAL_CNY + pnl
        rows.append({"replicate": replicate, "terminal_capital_cny": float(terminal)})
    return pd.DataFrame(rows)