"""包场 backtest with recalibrated q.

Walks history by ISO week, picks top-N matches in qualifying leagues,
enumerates 3^N outcome combos, ranks by EV, stakes top-K%.
Compares old (league-only SP[5,8]) vs new (league x bucket) q models.

Two stake modes: flat (2 yuan) and kelly_proportional.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "raw" / "beidan_full_3sp.csv"
Q_NEW_PATH = ROOT / "data" / "raw" / "q_recalibrated.json"
Q_OLD_PATH = ROOT / "src" / "phase5a" / "league_quality.json"

BUCKETS = [
    (1.0, 1.5, "[1.0,1.5)"),
    (1.5, 2.0, "[1.5,2.0)"),
    (2.0, 3.0, "[2.0,3.0)"),
    (3.0, 5.0, "[3.0,5.0)"),
    (5.0, 8.0, "[5.0,8.0)"),
    (8.0, 15.0, "[8.0,15.0)"),
    (15.0, math.inf, "[15.0,inf)"),
]


def bucket_of(sp: float) -> str | None:
    for lo, hi, name in BUCKETS:
        if lo <= sp < hi:
            return name
    return None


@dataclass
class Match:
    kickoff: datetime
    league: str
    sps: dict  # {3: x, 1: y, 0: z}
    result_code: int


def load_matches() -> list[Match]:
    out = []
    with CSV_PATH.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ko = datetime.fromisoformat(row["kickoff_ts"])
                rc = int(row["result_code"])
                sps = {3: float(row["sp_3"]), 1: float(row["sp_1"]), 0: float(row["sp_0"])}
            except (ValueError, KeyError):
                continue
            if any(s <= 1.0 for s in sps.values()):
                continue
            out.append(Match(ko, row["league"].strip(), sps, rc))
    out.sort(key=lambda m: m.kickoff)
    return out


def load_q_new() -> dict:
    return json.loads(Q_NEW_PATH.read_text())


def load_q_old() -> dict:
    return json.loads(Q_OLD_PATH.read_text())


def q_lookup_new(q_data: dict, league: str, sp: float) -> float:
    b = bucket_of(sp)
    if b is None:
        return 1.0
    key = f"{league}|{b}"
    if key in q_data:
        return q_data[key]["q"]
    overall = q_data.get("__overall__", {})
    if b in overall:
        return overall[b]["q"]
    return 1.0


def q_lookup_old(q_data: dict, league: str, sp: float) -> float:
    # old model = league-only (SP[5,8] calibration). Apply uniformly.
    info = q_data.get(league)
    if info is None:
        return 1.0
    return info["q"]


def match_score_new(q_data: dict, m: Match) -> float:
    """Sum of bucket-q across the 3 candidate sides — how informative is this match."""
    return sum(q_lookup_new(q_data, m.league, sp) for sp in m.sps.values())


def match_score_old(q_data: dict, m: Match) -> float:
    return q_lookup_old(q_data, m.league, 0.0) * 3  # constant per match; doesn't matter for ranking


def has_high_q_new(q_data: dict, league: str, threshold: float = 0.65) -> bool:
    for key, val in q_data.items():
        if key == "__overall__":
            continue
        if key.startswith(league + "|") and val["q"] >= threshold and not val.get("fallback", False):
            return True
    return False


def has_high_q_old(q_data: dict, league: str, threshold: float = 0.65) -> bool:
    info = q_data.get(league)
    return info is not None and info["q"] >= threshold


def iso_week(dt: datetime) -> tuple[int, int]:
    iso = dt.isocalendar()
    return (iso[0], iso[1])


def enumerate_combos(matches: list[Match], q_lookup, q_data) -> list[tuple]:
    """Returns list of (ev_per_yuan, joint_payout, picked_sides_tuple)."""
    sides_per_match = []  # list of [(side, sp, q), ...]
    for m in matches:
        sides = [(s, m.sps[s], q_lookup(q_data, m.league, m.sps[s])) for s in (3, 1, 0)]
        sides_per_match.append(sides)

    out = []
    for combo in product(*sides_per_match):
        joint_p = 1.0
        joint_payout = 1.0
        sides_tup = []
        for (side, sp, q) in combo:
            joint_p *= q * (1.0 / sp / 0.65)
            joint_payout *= sp * 0.65
            sides_tup.append(side)
        ev = joint_p * joint_payout - 1.0
        out.append((ev, joint_payout, tuple(sides_tup)))
    return out


def settle_combo(combo_sides: tuple, matches: list[Match], stake: float, joint_payout: float) -> float:
    """Returns net pnl for one ticket."""
    if all(combo_sides[i] == matches[i].result_code for i in range(len(matches))):
        gross = stake * joint_payout
        # tax 20% on per-ticket payout > 5000
        if gross > 5000.0:
            tax = (gross - stake) * 0.20  # tax on winnings
            # 北单 actual rule: 20% on payout if single-ticket wins > 10000; here using >5000 as instructed
            # Per instructions: "20% on per-ticket payout > 5,000 元"
            # Apply: tax = 0.20 * gross
            tax = 0.20 * gross
            gross -= tax
        return gross - stake
    return -stake


def run_backtest(
    matches_all: list[Match],
    q_data,
    q_lookup,
    has_high_q,
    match_score,
    N: int,
    K_pct: float,
    sizing: str,
) -> dict:
    # group by ISO week
    weeks = defaultdict(list)
    for m in matches_all:
        weeks[iso_week(m.kickoff)].append(m)

    sorted_weeks = sorted(weeks.keys())

    bankroll = 100_000.0
    initial = bankroll
    total_stake = 0.0
    weekly_pnl = []
    equity_curve = [bankroll]
    n_weeks_traded = 0

    for wk in sorted_weeks:
        wk_matches = weeks[wk]
        # filter to qualifying leagues
        qual = [m for m in wk_matches if has_high_q(q_data, m.league)]
        if len(qual) < N:
            continue
        # rank by match_score, take top N
        qual.sort(key=lambda m: -match_score(q_data, m))
        picks = qual[:N]
        combos = enumerate_combos(picks, q_lookup, q_data)
        if not combos:
            continue
        # rank by EV desc
        combos.sort(key=lambda x: -x[0])
        k_count = max(1, int(len(combos) * K_pct))
        top = combos[:k_count]
        max_ev = top[0][0]

        if sizing == "flat":
            stakes = [2.0] * len(top)
        else:  # kelly_proportional
            if max_ev <= 0:
                stakes = [2.0] * len(top)
            else:
                stakes = [max(2.0, round(ev / max_ev * 10.0)) for (ev, _, _) in top]

        week_stake = sum(stakes)
        if week_stake > bankroll:
            # skip (insufficient bankroll)
            continue
        # settle
        week_pnl = 0.0
        for (ev, payout, sides), stake in zip(top, stakes):
            week_pnl += settle_combo(sides, picks, stake, payout)
        bankroll += week_pnl
        total_stake += week_stake
        weekly_pnl.append(week_pnl)
        equity_curve.append(bankroll)
        n_weeks_traded += 1
        if bankroll <= 0:
            break

    final = bankroll
    if total_stake == 0 or n_weeks_traded == 0:
        return None
    per_yuan_loss = (final - initial) / total_stake
    # CAGR
    years = n_weeks_traded / 52.0
    if final > 0 and years > 0:
        cagr = (final / initial) ** (1 / years) - 1
    else:
        cagr = -1.0
    # Sharpe (weekly)
    if len(weekly_pnl) > 1:
        mu = statistics.mean(weekly_pnl)
        sd = statistics.pstdev(weekly_pnl)
        sharpe = (mu / sd * math.sqrt(52)) if sd > 0 else 0.0
    else:
        sharpe = 0.0
    # MaxDD
    peak = equity_curve[0]
    maxdd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        dd = (v - peak) / peak
        maxdd = min(maxdd, dd)

    return {
        "weeks": n_weeks_traded,
        "total_stake": total_stake,
        "total_loss": final - initial,
        "per_yuan_loss_pct": per_yuan_loss * 100,
        "cagr_pct": cagr * 100,
        "sharpe": sharpe,
        "maxdd_pct": maxdd * 100,
        "after_rebate_pct": (per_yuan_loss + 0.07) * 100,
        "final": final,
    }


def main() -> None:
    print("Loading matches...")
    matches = load_matches()
    print(f"  {len(matches)} matches loaded.")

    q_new = load_q_new()
    q_old = load_q_old()

    configs = []
    for q_name, q_data, qf, hf, sf in [
        ("new", q_new, q_lookup_new, has_high_q_new, match_score_new),
        ("old", q_old, q_lookup_old, has_high_q_old, match_score_old),
    ]:
        for N in (5, 6):
            for K in (0.05, 0.10, 0.15, 0.20, 0.30):
                for sizing in ("flat", "kelly_proportional"):
                    configs.append((q_name, q_data, qf, hf, sf, N, K, sizing))

    results = []
    for cfg in configs:
        q_name, q_data, qf, hf, sf, N, K, sizing = cfg
        label = f"{q_name}/N={N}/K={int(K*100)}%/{sizing}"
        print(f"  running {label}...")
        r = run_backtest(matches, q_data, qf, hf, sf, N, K, sizing)
        if r is None:
            print(f"    skipped (no trades)")
            continue
        r["label"] = label
        r["q_model"] = q_name
        r["N"] = N
        r["K"] = K
        r["sizing"] = sizing
        results.append(r)

    # sort by per_yuan_loss_pct desc (least loss first)
    results.sort(key=lambda r: -r["per_yuan_loss_pct"])

    print("\n" + "=" * 130)
    print(f"{'Config':<40} {'Weeks':>6} {'TotStake':>12} {'TotLoss':>12} {'Per元%':>9} {'CAGR%':>8} {'Sharpe':>7} {'MaxDD%':>8} {'+7%reb%':>9}")
    print("=" * 130)
    for r in results:
        print(f"{r['label']:<40} {r['weeks']:>6d} {r['total_stake']:>12.0f} {r['total_loss']:>12.0f} "
              f"{r['per_yuan_loss_pct']:>9.2f} {r['cagr_pct']:>8.2f} {r['sharpe']:>7.2f} "
              f"{r['maxdd_pct']:>8.2f} {r['after_rebate_pct']:>9.2f}")
    print("=" * 130)

    # save CSV
    out_csv = ROOT / "notebooks" / "coverage_v2_recalibrated_results.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"\nResults written to {out_csv}")


if __name__ == "__main__":
    main()
