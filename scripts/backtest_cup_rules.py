"""Backtest: old (11-rule) niche table vs new (13-rule, with 2 cup rules)
on the historical 3SP dataset, simulating per-issue plan generation.

For each historical issue:
  1. Build LiveSnapshot-equivalent rows from `beidan_full_3sp.csv`
  2. Qualify candidates with each niche config
  3. Run `build_plan` (the same combo optimiser used live)
  4. Settle each ticket against actual `result_code`
  5. Aggregate stake / payout / PnL

Reports old-vs-new lift over the chosen window.
"""
from __future__ import annotations
import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.phase5a.data_loader import LiveSnapshot
from src.phase5a.filter import NicheConfig, NicheRule, qualify_candidates
from src.phase5a.planner import build_weekly_plan
from src.niche_analysis.sp_native import RETURN_RATE


NICHES_JSON = ROOT / "src" / "phase5a" / "niches_default.json"


# ---------------------------------------------------------------------------
# Build configs
# ---------------------------------------------------------------------------
def load_new_config() -> NicheConfig:
    return NicheConfig.load(league_q_min=0.0)


def load_old_config() -> NicheConfig:
    """Same JSON but with the 2 *_CUP rules stripped → emulates pre-change state."""
    data = json.loads(NICHES_JSON.read_text())
    data = deepcopy(data)
    data["rules"] = [r for r in data["rules"] if not r["name"].endswith("_CUP")]
    # Build directly via NicheRule (don't write to disk)
    rules = tuple(
        NicheRule(
            name=r["name"], p_hat_train=float(r["p_hat_train"]),
            option=r.get("option"), sp_lo=r.get("sp_lo"), sp_hi=r.get("sp_hi"),
            league_tier=r.get("league_tier"), handicap_class=r.get("handicap_class"),
            comp_type=r.get("comp_type"),
        )
        for r in data["rules"]
    )
    return NicheConfig(return_rate=float(data.get("return_rate", 0.65)),
                       rules=rules, league_q_min=0.0, league_q_table=())


# ---------------------------------------------------------------------------
# Per-issue snapshot builder
# ---------------------------------------------------------------------------
def issue_to_snapshots(issue_df: pd.DataFrame) -> list[LiveSnapshot]:
    out: list[LiveSnapshot] = []
    for r in issue_df.itertuples(index=False):
        out.append(LiveSnapshot(
            match_id=f"{int(r.expect)}_{int(r.match_no):03d}",
            issue=str(int(r.expect)),
            match_idx=int(r.match_no),
            league=str(r.league) if pd.notna(r.league) else None,
            kickoff_ts=str(r.kickoff_ts),
            home=str(r.home) if pd.notna(r.home) else None,
            away=str(r.away) if pd.notna(r.away) else None,
            handicap_line=(float(r.handicap) if pd.notna(r.handicap) else None),
            sp_3=(float(r.sp_3) if pd.notna(r.sp_3) else None),
            sp_1=(float(r.sp_1) if pd.notna(r.sp_1) else None),
            sp_0=(float(r.sp_0) if pd.notna(r.sp_0) else None),
            snapshot_ts=str(r.last_update_ts),
        ))
    return out


# ---------------------------------------------------------------------------
# Plan settlement
# ---------------------------------------------------------------------------
def settle_plan(tickets, results: dict[str, str]) -> dict:
    """Settle a list of TicketPlan objects against {match_id: result_code}.
    Returns aggregated stats."""
    n_tickets = len(tickets)
    n_hits = 0
    total_stake = 0.0
    total_payout = 0.0
    for t in tickets:
        legs = t.combo.legs
        stake = float(t.total_stake)
        total_stake += stake
        all_hit = all(
            results.get(leg.match_id) == str(int(leg.selection))
            for leg in legs
        )
        if all_hit:
            n_hits += 1
            total_payout += stake * t.combo.payout_per_yuan
    return dict(
        n_tickets=n_tickets, n_hits=n_hits,
        stake=total_stake, payout=total_payout,
        pnl=total_payout - total_stake,
    )


# ---------------------------------------------------------------------------
# Backtest driver
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "raw" / "beidan_full_3sp.csv"))
    ap.add_argument("--n-issues", type=int, default=80,
                    help="Number of most-recent issues to backtest")
    ap.add_argument("--bankroll", type=float, default=100_000)
    ap.add_argument("--mix-strategy", default="S1_mix",
                    choices=("N3_only", "N4_only", "N3_N4_5050", "S1_mix"),
                    help="Backtest strategy mix. S1_mix = production "
                         "Mix 30/40/30 across N=2/3/4 with Kelly 1/32")
    ap.add_argument("--max-combos", type=int, default=200)
    args = ap.parse_args()

    print(f"Loading {args.csv}…")
    df = pd.read_csv(args.csv)
    df["expect"] = pd.to_numeric(df["expect"], errors="coerce")
    df["match_no"] = pd.to_numeric(df["match_no"], errors="coerce")
    for c in ("sp_3", "sp_1", "sp_0", "handicap"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["sp_3", "sp_1", "sp_0", "result_code"]).copy()
    df["result_code"] = df["result_code"].astype(str).str.strip()

    # Sort issues by their max kickoff_ts (issue codes change format over years
    # so a numeric sort doesn't give chronological order).
    df["kickoff_ts"] = pd.to_datetime(df["kickoff_ts"], errors="coerce")
    issue_dates = df.groupby("expect")["kickoff_ts"].max().sort_values()
    recent_issues = issue_dates.index[-args.n_issues:].tolist()
    df = df[df["expect"].isin(recent_issues)].copy()
    print(f"Backtesting {len(recent_issues)} issues "
          f"(dates {issue_dates.loc[recent_issues].min().date()} → "
          f"{issue_dates.loc[recent_issues].max().date()}), "
          f"{len(df):,} matches")

    cfg_old = load_old_config()
    cfg_new = load_new_config()
    print(f"old rules: {len(cfg_old.rules)}  new rules: {len(cfg_new.rules)}")

    # For each issue, run plan with each config
    rows_old, rows_new = [], []
    fired_cup = 0
    for iss in recent_issues:
        idf = df[df["expect"] == iss]
        snaps = issue_to_snapshots(idf)
        results = {f"{int(r.expect)}_{int(r.match_no):03d}": str(r.result_code).strip()
                   for r in idf.itertuples(index=False)}

        for cfg, rows, label in [(cfg_old, rows_old, "old"),
                                   (cfg_new, rows_new, "new")]:
            agg_st = dict(n_tickets=0, n_hits=0, stake=0.0, payout=0.0, pnl=0.0)
            n_qualified_max = 0
            cup_legs_this_iss = 0
            if args.mix_strategy == "S1_mix":
                buckets = [(2, 0.30, 1/32), (3, 0.40, 1/32), (4, 0.30, 1/32)]
            elif args.mix_strategy == "N3_N4_5050":
                buckets = [(3, 0.5, 1/16), (4, 0.5, 1/16)]
            else:
                n_legs = 4 if args.mix_strategy == "N4_only" else 3
                buckets = [(n_legs, 1.0, 1/16)]
            for n_legs, weight, kelly in buckets:
                plan = build_weekly_plan(
                    snaps,
                    bankroll=args.bankroll * weight,
                    niche_config=cfg,
                    n_legs=n_legs,
                    kelly_fraction=kelly,
                    weekly_stake_cap_frac=0.005,
                    combo_ev_threshold=0.05,
                    max_combos=args.max_combos,
                    diversity_lambda=0.5,
                )
                st = settle_plan(plan.tickets, results)
                for k in ("n_tickets", "n_hits", "stake", "payout", "pnl"):
                    agg_st[k] += st[k]
                n_qualified_max = max(n_qualified_max, plan.n_qualified_legs)
                if label == "new":
                    cup_legs_this_iss += sum(
                        1 for name in plan.rule_by_match.values()
                        if name.endswith("_CUP")
                    )
            agg_st["issue"] = int(iss)
            agg_st["n_qualified"] = n_qualified_max
            agg_st["cup_legs"] = cup_legs_this_iss
            rows.append(agg_st)
            if label == "new":
                fired_cup += cup_legs_this_iss

    df_old = pd.DataFrame(rows_old).set_index("issue")
    df_new = pd.DataFrame(rows_new).set_index("issue")

    print()
    print(f"=== OLD vs NEW ({args.mix_strategy}, n={len(recent_issues)} issues) ===")
    for label, dx in [("OLD", df_old), ("NEW", df_new)]:
        n_iss_with_tix = (dx["n_tickets"] > 0).sum()
        tot_stake = dx["stake"].sum()
        tot_payout = dx["payout"].sum()
        tot_pnl = dx["pnl"].sum()
        roi = (tot_pnl / tot_stake * 100) if tot_stake else 0.0
        n_hits = dx["n_hits"].sum()
        n_tickets = dx["n_tickets"].sum()
        hit_rate = (n_hits / n_tickets * 100) if n_tickets else 0.0
        print(f"  {label}  issues_with_tickets={n_iss_with_tix}/{len(recent_issues)}  "
              f"stake={tot_stake:>9.0f}  payout={tot_payout:>9.0f}  "
              f"PnL={tot_pnl:>+9.0f}  ROI={roi:>+5.2f}%  "
              f"hits={n_hits}/{n_tickets} ({hit_rate:.2f}%)")

    diff_pnl = df_new["pnl"].sum() - df_old["pnl"].sum()
    diff_stake = df_new["stake"].sum() - df_old["stake"].sum()
    print()
    print(f"NEW − OLD  ΔPnL={diff_pnl:+.0f}  Δstake={diff_stake:+.0f}  "
          f"cup-rule legs that fired in NEW: {fired_cup}")

    # Slice: issues where cup rules actually fired vs not
    cup_iss = df_new[df_new["cup_legs"] > 0]
    nocup_iss = df_new[df_new["cup_legs"] == 0]
    if not cup_iss.empty:
        cup_old = df_old.loc[cup_iss.index]
        print(f"\nIssues with cup-rule fires (n={len(cup_iss)}):")
        print(f"  OLD PnL={cup_old['pnl'].sum():+.0f}  NEW PnL={cup_iss['pnl'].sum():+.0f}  "
              f"Δ={cup_iss['pnl'].sum() - cup_old['pnl'].sum():+.0f}")
    if not nocup_iss.empty:
        nocup_old = df_old.loc[nocup_iss.index]
        print(f"Issues without cup-rule fires (n={len(nocup_iss)}):")
        print(f"  OLD PnL={nocup_old['pnl'].sum():+.0f}  NEW PnL={nocup_iss['pnl'].sum():+.0f}  "
              f"Δ={nocup_iss['pnl'].sum() - nocup_old['pnl'].sum():+.0f}")

    # Save details
    out = ROOT / "data" / "raw" / "backtest_cup_rules.csv"
    merged = df_old.add_suffix("_old").join(df_new.add_suffix("_new"))
    merged.to_csv(out)
    print(f"\ndetails → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
