"""Drive the combo optimizer over historical weekly batches.

For each issue (weekly 期号):
  1. Build Candidate pool from avg-EU-derived model probs + empirical
     proxy SP per outcome (B2's OLS fit). Apply edge filter (≥ 0.05).
  2. Call ``src.combo_optimizer.build_plan`` to get TicketPlans.
  3. Settle each plan against the actual results.
  4. Aggregate per-issue stats.

Returns a per-issue DataFrame and a per-plan ledger.
"""
from __future__ import annotations

import logging
import sqlite3
from collections import Counter
from typing import List, Optional

import numpy as np
import pandas as pd

from src.backtest.ev import (
    EmpiricalSPModel,
    fit_empirical_sp_model,
)
from src.backtest.model import model_probs_from_eu
from src.backtest.simulator import load_matches
from src.combo_optimizer import build_plan
from src.combo_optimizer.types import RETURN_RATE, Candidate, TicketPlan

from .settler import ComboSettlement, settle_plan

log = logging.getLogger(__name__)

# How many of the most-frequent leg IDs from tier N to propagate as
# cross-tier penalty seeds for tier N+1. Prevents full-pool saturation
# (previously all top_k=14 legs were added, making the penalty uniform).
_CROSS_N_TOP_LEGS = 5


def _top_freq_leg_ids(sub_plans: List[TicketPlan], top_k: int) -> set:
    """Return the top_k most-frequent 'match_id:selection' strings across sub_plans."""
    freq: Counter = Counter(
        f"{leg.match_id}:{leg.selection}"
        for plan in sub_plans
        for leg in plan.combo.legs
    )
    return {lid for lid, _ in freq.most_common(top_k)}


# ---------------------------------------------------------------------------
# Empirical SP model (re-uses B2's per-result-code OLS fit)
# ---------------------------------------------------------------------------

def fit_sp_model_from_db(df: pd.DataFrame) -> EmpiricalSPModel:
    """Fit the per-result-code OLS sp ~ winning_eu_odds on the full dataset."""
    winning_eu = np.where(
        df["result_code"] == "3", df["avg_eu_home"],
        np.where(df["result_code"] == "1", df["avg_eu_draw"],
                 df["avg_eu_away"])
    )
    return fit_empirical_sp_model(
        np.asarray(winning_eu, dtype=float),
        df["winning_sp"].to_numpy(dtype=float),
        df["result_code"].to_numpy(),
    )


# ---------------------------------------------------------------------------
# Candidate construction per issue
# ---------------------------------------------------------------------------

def build_candidates_for_issue(
    issue_df: pd.DataFrame,
    sp_model: EmpiricalSPModel,
    *,
    edge_floor: float = 0.05,
) -> List[Candidate]:
    """Return all (match × selection) candidates whose edge ≥ ``edge_floor``.

    For each match we compute model p3/p1/p0 (de-vigged + draw correction)
    and predict proxy SP per option from the per-result-code OLS. We
    evaluate all 3 selections per match and emit any with edge ≥ floor.
    Same-match dedup is the optimizer's job.
    """
    cands: List[Candidate] = []
    for row in issue_df.itertuples(index=False):
        try:
            handicap = int(row.handicap_line)
        except Exception:
            continue
        try:
            probs = model_probs_from_eu(
                row.avg_eu_home, row.avg_eu_draw, row.avg_eu_away,
                handicap,
                apply_correction=True,
            )
        except Exception:
            continue

        match_id = f"{row.issue}-{row.match_idx:03d}"
        eu = {"3": row.avg_eu_home, "1": row.avg_eu_draw, "0": row.avg_eu_away}
        ps = {"3": probs.p3, "1": probs.p1, "0": probs.p0}
        for code in ("3", "1", "0"):
            sp = sp_model.predict(float(eu[code]), code)
            if sp <= 0 or not np.isfinite(sp):
                continue
            p = float(ps[code])
            edge = p * sp * RETURN_RATE - 1.0
            if edge < edge_floor:
                continue
            cands.append(Candidate(
                match_id=match_id,
                selection=int(code),
                p_hat=p,
                sp=float(sp),
            ))
    return cands


# ---------------------------------------------------------------------------
# Per-issue simulation
# ---------------------------------------------------------------------------

def actuals_for_issue(issue_df: pd.DataFrame) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in issue_df.itertuples(index=False):
        match_id = f"{row.issue}-{row.match_idx:03d}"
        out[match_id] = {
            "result_code": str(row.result_code),
            "winning_sp": float(row.winning_sp),
            "handicap": int(row.handicap_line) if row.handicap_line is not None else 0,
        }
    return out


def simulate_issue(
    issue: str,
    issue_df: pd.DataFrame,
    sp_model: EmpiricalSPModel,
    *,
    bankroll: float = 100_000.0,
    edge_floor: float = 0.05,
    combo_ev_threshold: float = 0.10,
    n_legs: int = 7,
    top_k: int = 14,
    kelly_fraction: float = 0.25,
    max_combos: int = 50,
    weekly_stake_cap_frac: float = 0.25,
    # Multi-N mix + cross-tier diversity
    mix_n_legs: Optional[tuple] = None,    # e.g. (2, 3, 4); None → single-N
    mix_weights: Optional[tuple] = None,   # normalised bankroll split per N
    mix_kelly: Optional[tuple] = None,     # per-N Kelly; falls back to kelly_fraction
    mix_lambdas: Optional[tuple] = None,   # per-N within-tier diversity lambda
    cross_n_lambda: float = 0.0,           # cross-tier overlap penalty
    diversity_lambda: float = 0.0,         # single-N mode within-tier lambda
) -> tuple[dict, List[ComboSettlement]]:
    """Run optimizer + settle for a single issue.

    When ``mix_n_legs`` is provided the issue is run in multi-N mix mode:
    N tiers are built in ascending order, each receiving the leg IDs
    selected by lower tiers via ``cross_n_used`` so that ``cross_n_lambda``
    can penalise match reuse across tiers.

    Returns (issue_summary_dict, list_of_ComboSettlement).
    """
    cands = build_candidates_for_issue(
        issue_df, sp_model, edge_floor=edge_floor
    )
    plans: List[TicketPlan] = []

    if mix_n_legs and mix_weights and len(cands) > 0:
        wsum = sum(mix_weights)
        cross_n_used: set = set()
        for i, (n, w) in enumerate(zip(mix_n_legs, mix_weights)):
            if w <= 0 or len(cands) < n:
                continue
            w_norm = w / wsum
            k = mix_kelly[i] if mix_kelly else kelly_fraction
            lam = mix_lambdas[i] if mix_lambdas else 0.0
            sub_bankroll = bankroll * w_norm
            sub_max = max(1, round(max_combos * w_norm))
            sub_plans = build_plan(
                cands,
                bankroll=sub_bankroll,
                weekly_stake_cap_frac=weekly_stake_cap_frac,
                n_legs=n,
                top_k=top_k,
                single_leg_edge_floor=edge_floor,
                combo_ev_threshold=combo_ev_threshold,
                kelly_fraction=k,
                max_combos=sub_max,
                diversity_lambda=lam,
                cross_n_used=frozenset(cross_n_used) if cross_n_used else None,
                cross_n_lambda=cross_n_lambda,
            )
            plans.extend(sub_plans)
            if cross_n_lambda > 0 and sub_plans:
                cross_n_used.update(_top_freq_leg_ids(sub_plans, _CROSS_N_TOP_LEGS))
    elif len(cands) >= n_legs:
        plans = build_plan(
            cands,
            bankroll=bankroll,
            weekly_stake_cap_frac=weekly_stake_cap_frac,
            n_legs=n_legs,
            top_k=top_k,
            single_leg_edge_floor=edge_floor,
            combo_ev_threshold=combo_ev_threshold,
            kelly_fraction=kelly_fraction,
            max_combos=max_combos,
            diversity_lambda=diversity_lambda,
            cross_n_lambda=cross_n_lambda,
        )

    actuals = actuals_for_issue(issue_df)
    settlements = [settle_plan(p, actuals) for p in plans]

    n_combos = len(plans)
    n_tickets = sum(p.n_tickets for p in plans)
    total_stake = sum(s.total_stake for s in settlements)
    total_profit = sum(s.total_profit for s in settlements)
    n_hit = sum(1 for s in settlements if s.all_hit)
    sum_pred_p = sum(s.plan.combo.joint_p * s.plan.n_tickets for s in settlements)

    summary = dict(
        issue=issue,
        n_matches=len(issue_df),
        n_candidates=len(cands),
        n_combos=n_combos,
        n_tickets=n_tickets,
        total_stake=total_stake,
        total_profit=total_profit,
        roi=(total_profit / total_stake) if total_stake > 0 else float("nan"),
        n_hit=n_hit,
        hit_rate=(n_hit / n_combos) if n_combos > 0 else float("nan"),
        expected_hit_tickets=sum_pred_p,  # Σ p_combo × n_tickets
    )
    return summary, settlements


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def run_combo_backtest(
    conn: sqlite3.Connection,
    *,
    bankroll: float = 100_000.0,
    edge_floor: float = 0.05,
    combo_ev_threshold: float = 0.10,
    n_legs: int = 7,
    top_k: int = 14,
    kelly_fraction: float = 0.25,
    max_combos: int = 50,
    weekly_stake_cap_frac: float = 0.25,
    mix_n_legs: Optional[tuple] = None,
    mix_weights: Optional[tuple] = None,
    mix_kelly: Optional[tuple] = None,
    mix_lambdas: Optional[tuple] = None,
    cross_n_lambda: float = 0.0,
    df: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, pd.DataFrame, EmpiricalSPModel]:
    """Run the backtest across every issue in the DB.

    Returns (issue_summary_df, plan_ledger_df, sp_model).
    """
    if df is None:
        df = load_matches(conn)
    sp_model = fit_sp_model_from_db(df)

    issue_rows: list[dict] = []
    plan_rows: list[dict] = []

    for issue, idf in df.groupby("issue"):
        summary, settlements = simulate_issue(
            issue, idf, sp_model,
            bankroll=bankroll,
            edge_floor=edge_floor,
            combo_ev_threshold=combo_ev_threshold,
            n_legs=n_legs,
            top_k=top_k,
            kelly_fraction=kelly_fraction,
            max_combos=max_combos,
            weekly_stake_cap_frac=weekly_stake_cap_frac,
            mix_n_legs=mix_n_legs,
            mix_weights=mix_weights,
            mix_kelly=mix_kelly,
            mix_lambdas=mix_lambdas,
            cross_n_lambda=cross_n_lambda,
        )
        kickoff_min = idf["kickoff_ts"].min()
        summary["kickoff_min"] = kickoff_min
        issue_rows.append(summary)

        for s in settlements:
            plan_rows.append(dict(
                issue=issue,
                kickoff_min=kickoff_min,
                joint_p=s.plan.combo.joint_p,
                joint_sp=s.plan.combo.joint_sp,
                ev=s.plan.combo.ev,
                stake_per_ticket=s.plan.stake_per_ticket,
                n_tickets=s.plan.n_tickets,
                total_stake=s.total_stake,
                all_hit=s.all_hit,
                realised_payout_per_yuan=s.realised_payout_per_yuan,
                total_profit=s.total_profit,
                # leg breakdown for attribution
                handicap_classes=",".join(
                    "0" if (abs_h := abs_handicap_for_leg(idf, leg.match_id)) == 0
                    else "1" if abs_h == 1 else "2+"
                    for leg in s.plan.combo.legs
                ),
                selection_mix=",".join(str(leg.selection) for leg in s.plan.combo.legs),
            ))

    return (
        pd.DataFrame(issue_rows).sort_values("kickoff_min").reset_index(drop=True),
        pd.DataFrame(plan_rows),
        sp_model,
    )


def abs_handicap_for_leg(issue_df: pd.DataFrame, match_id: str) -> int:
    """Look up |handicap| for a leg (match_id format "issue-MMM")."""
    try:
        idx = int(match_id.split("-")[1])
    except Exception:
        return 0
    row = issue_df[issue_df["match_idx"] == idx]
    if row.empty:
        return 0
    h = row["handicap_line"].iloc[0]
    if h is None or pd.isna(h):
        return 0
    return abs(int(h))
