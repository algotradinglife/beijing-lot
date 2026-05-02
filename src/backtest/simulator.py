"""Walk through historical matches, compute model EVs, would-bet picks
and realised PnL using actual winning-side SP.

Key honesty caveat: we ONLY know the SP of the winning outcome.  If the
model's pick won, we can compute realised PnL exactly (using the
historical winning_sp).  If the model's pick lost, we know it's a -stake
loss (no SP needed for the loss).  But the *would-be PnL distribution*
for losing picks across the 3 outcomes is unknown — we cannot tell
whether the LOSING side's SP was high or low.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .ev import (
    EmpiricalSPModel,
    fit_empirical_sp_model,
    model_ev,
    naive_proxy_sp,
)
from .kelly import RETURN_RATE, quarter_kelly_stake, realised_pnl
from .model import model_probs_from_eu


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_matches(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT issue, match_idx, league, kickoff_ts, home, away,
               handicap_line, fthg, ftag, result_code, winning_sp,
               avg_eu_home, avg_eu_draw, avg_eu_away
          FROM historical_matches
         WHERE result_code IN ('3','1','0')
           AND winning_sp > 0
           AND avg_eu_home > 1
           AND avg_eu_draw > 1
           AND avg_eu_away > 1
           AND handicap_line IS NOT NULL
        """,
        conn,
    )
    df["kickoff_ts"] = pd.to_datetime(df["kickoff_ts"], errors="coerce")
    df = df.dropna(subset=["kickoff_ts"]).copy()
    return df


# ---------------------------------------------------------------------------
# Per-match analysis
# ---------------------------------------------------------------------------

@dataclass
class Pick:
    issue: str
    match_idx: int
    kickoff_ts: pd.Timestamp
    league: str
    handicap: int
    chosen_outcome: str  # '3' | '1' | '0'
    realised_outcome: str
    p_chosen: float
    proxy_sp_chosen: float
    model_ev: float
    actual_winning_sp: float | None
    won: bool
    stake: float
    pnl: float


def proxy_sp_per_outcome(
    eu_home: float, eu_draw: float, eu_away: float,
    sp_model: EmpiricalSPModel | None,
    use_empirical: bool,
) -> dict[str, float]:
    if not use_empirical or sp_model is None:
        return {
            "3": naive_proxy_sp(eu_home),
            "1": naive_proxy_sp(eu_draw),
            "0": naive_proxy_sp(eu_away),
        }
    return {
        "3": sp_model.predict(eu_home, "3"),
        "1": sp_model.predict(eu_draw, "1"),
        "0": sp_model.predict(eu_away, "0"),
    }


def simulate(
    df: pd.DataFrame,
    bankroll: float = 10_000.0,
    ev_threshold: float = 1.05,
    use_empirical_sp: bool = False,
    apply_draw_correction: bool = True,
) -> tuple[pd.DataFrame, EmpiricalSPModel | None]:
    """Return a DataFrame of all model picks (one row per qualifying outcome)
    with realised PnL.

    Note: we evaluate ALL three outcomes per match against ev_threshold and
    record each as a separate row.  This matches spec §4.2 ("EV-driven
    candidate selection").  Multiple outcomes per match can co-qualify,
    though it's rare.
    """
    sp_model = None
    if use_empirical_sp:
        sp_model = fit_empirical_sp_model(
            df["winning_sp"].to_numpy(),  # placeholder; real x is winning EU
            df["winning_sp"].to_numpy(),
            df["result_code"].to_numpy(),
        )
        # Actually fit on winning-EU vs winning-SP per result code.
        winning_eu = np.where(
            df["result_code"] == "3", df["avg_eu_home"],
            np.where(df["result_code"] == "1", df["avg_eu_draw"],
                     df["avg_eu_away"])
        )
        sp_model = fit_empirical_sp_model(
            np.asarray(winning_eu, dtype=float),
            df["winning_sp"].to_numpy(dtype=float),
            df["result_code"].to_numpy(),
        )

    picks: list[dict] = []
    for row in df.itertuples(index=False):
        try:
            probs = model_probs_from_eu(
                row.avg_eu_home, row.avg_eu_draw, row.avg_eu_away,
                int(row.handicap_line),
                apply_correction=apply_draw_correction,
            )
        except Exception:
            continue

        proxy_sp = proxy_sp_per_outcome(
            row.avg_eu_home, row.avg_eu_draw, row.avg_eu_away,
            sp_model, use_empirical=use_empirical_sp,
        )

        p_by_code = {"3": probs.p3, "1": probs.p1, "0": probs.p0}

        for code in ("3", "1", "0"):
            p = p_by_code[code]
            sp_proxy = proxy_sp[code]
            ev = model_ev(p, sp_proxy)
            if not math.isfinite(ev) or ev < ev_threshold:
                continue

            won = (code == row.result_code)
            # Use ACTUAL winning SP only if our chosen outcome won;
            # else SP for our chosen outcome is unknown — we just take -stake.
            actual_sp = float(row.winning_sp) if won else None
            stake = quarter_kelly_stake(p, sp_proxy, bankroll)
            pnl_yuan = (
                stake * (actual_sp * RETURN_RATE - 1.0) if won and actual_sp
                else -stake
            )

            picks.append(dict(
                issue=row.issue,
                match_idx=row.match_idx,
                kickoff_ts=row.kickoff_ts,
                league=row.league,
                handicap=int(row.handicap_line),
                chosen_outcome=code,
                realised_outcome=row.result_code,
                p_chosen=p,
                proxy_sp_chosen=sp_proxy,
                model_ev=ev,
                actual_winning_sp=actual_sp,
                won=won,
                stake=stake,
                pnl=pnl_yuan,
            ))

    cols = [
        "issue", "match_idx", "kickoff_ts", "league", "handicap",
        "chosen_outcome", "realised_outcome", "p_chosen", "proxy_sp_chosen",
        "model_ev", "actual_winning_sp", "won", "stake", "pnl",
    ]
    return pd.DataFrame(picks, columns=cols), sp_model


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_weekly(picks: pd.DataFrame, bankroll: float = 10_000.0) -> pd.DataFrame:
    if picks.empty:
        return pd.DataFrame(columns=["week", "n_picks", "total_stake", "total_pnl", "roi"])
    p = picks.copy()
    p["week"] = p["kickoff_ts"].dt.to_period("W").astype(str)
    g = p.groupby("week").agg(
        n_picks=("pnl", "size"),
        total_stake=("stake", "sum"),
        total_pnl=("pnl", "sum"),
    ).reset_index()
    g["roi"] = np.where(g["total_stake"] > 0, g["total_pnl"] / g["total_stake"], 0.0)
    return g


def cumulative_roi(picks: pd.DataFrame) -> pd.DataFrame:
    if picks.empty:
        return pd.DataFrame()
    p = picks.sort_values("kickoff_ts").copy()
    p["cum_stake"] = p["stake"].cumsum()
    p["cum_pnl"] = p["pnl"].cumsum()
    p["cum_roi"] = np.where(p["cum_stake"] > 0, p["cum_pnl"] / p["cum_stake"], 0.0)
    return p[["kickoff_ts", "cum_stake", "cum_pnl", "cum_roi"]]
