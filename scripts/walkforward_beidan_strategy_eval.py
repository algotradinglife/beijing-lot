#!/usr/bin/env python3
"""Walk-forward evaluation for high-N Beidan combo strategy families.

This script consumes the normalized XLSM SQLite DB built by:

  1. scripts/convert_beidan_xlsm_to_sqlite.py
  2. scripts/normalize_beidan_xlsm_handicap.py
  3. scripts/build_beidan_modeling_tables.py

It evaluates rule families with rolling train windows and settles tickets with
actual winning SP. Non-winning official SP is not present in the source data,
so the q baseline uses company euro odds as the ex-ante price proxy.
"""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Iterable


RETURN_RATE = 0.65
DEFAULT_DB_CANDIDATES = (
    Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite"),
    Path("../../data/derived/beidan_xlsm/beidan_xlsm.sqlite"),
)

SINGLE_ACTIONS = {"3", "1", "0"}
FIXED_EDGE_RULES = {
    ("0", -1.0),
    ("1", 1.0),
    ("0", -2.0),
    ("31", 1.0),
    ("10", -1.0),
    ("3", 1.0),
}


def default_db_path() -> Path:
    for path in DEFAULT_DB_CANDIDATES:
        if path.exists():
            return path
    return DEFAULT_DB_CANDIDATES[0]


@dataclass(frozen=True)
class ActionRow:
    match_id: int
    issue: str
    match_idx: int
    kickoff_ts: str
    season_year: int
    league: str
    hcp: float
    result_code: str
    winning_sp: float
    action_code: str
    action_label: str
    selection_set: str
    cover_count: int
    hit: int
    factor: float
    euro_final_odds: float | None
    euro_final_p: float | None
    euro_1h_odds: float | None
    euro_1h_p: float | None
    euro_10h_odds: float | None
    euro_10h_p: float | None
    euro_final_rank: int | None
    kelly_final: float | None = None
    kelly_10h: float | None = None
    kelly_1h: float | None = None
    kelly_initial: float | None = None
    kelly_move_10h_final: float | None = None


@dataclass(frozen=True)
class Leg:
    row: ActionRow
    strategy: str
    score_factor: float
    p_hat: float
    source_rule: str
    is_full_cover: bool = False

    @property
    def leg_id(self) -> str:
        return f"{self.row.match_id}:{self.row.action_code}"


@dataclass(frozen=True)
class Ticket:
    strategy: str
    issue: str
    n_legs: int
    ticket_idx: int
    train_start_issue: str
    train_end_issue: str
    legs: tuple[Leg, ...]


def break_even_factor(n_legs: int) -> float:
    return (1.0 / RETURN_RATE) ** (1.0 / n_legs)


def p_bucket(p: float | None) -> str:
    if p is None:
        return "missing"
    if p < 0.20:
        return "<20"
    if p < 0.30:
        return "20-30"
    if p < 0.40:
        return "30-40"
    if p < 0.50:
        return "40-50"
    return ">=50"


def hcp_bucket(hcp: float | None) -> str:
    if hcp is None:
        return "missing"
    if hcp <= -2:
        return "<=-2"
    if hcp == -1:
        return "-1"
    if hcp == 0:
        return "0"
    if hcp == 1:
        return "1"
    if hcp >= 2:
        return ">=2"
    return str(hcp)


def as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def load_action_rows(db_path: Path, min_year: int, settlement_quality: str | None = None) -> list[ActionRow]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    quality_clause = ""
    quality_params: list[object] = []
    if settlement_quality:
        quality_clause = "AND settlement_quality = ?"
        quality_params.append(settlement_quality)

    outcome_sql = f"""
        SELECT
            match_id,
            outcome_code,
            euro_final_odds,
            euro_final_p,
            euro_1h_odds,
            euro_1h_p,
            euro_10h_odds,
            euro_10h_p,
            euro_final_rank,
            kelly_final,
            kelly_10h,
            kelly_1h,
            kelly_initial,
            kelly_move_10h_final
        FROM outcome_features
        WHERE has_winning_sp = 1
          AND season_year >= ?
          {quality_clause}
          AND outcome_code IN ('3','1','0')
    """
    outcome_map: dict[tuple[int, str], sqlite3.Row] = {
        (int(r["match_id"]), str(r["outcome_code"])): r
        for r in conn.execute(outcome_sql, [min_year, *quality_params])
    }

    sql = f"""
        SELECT
            ac.match_id,
            ac.issue,
            ac.match_idx,
            ac.kickoff_ts,
            ac.season_year,
            ac.league,
            ac.handicap_line_norm AS hcp,
            ac.result_code,
            ac.winning_sp,
            ac.action_code,
            ac.action_label,
            ac.selection_set,
            ac.cover_count,
            ac.hit,
            ac.factor
        FROM action_candidates ac
        WHERE ac.has_winning_sp = 1
          AND ac.season_year >= ?
          {quality_clause}
          AND ac.handicap_line_norm IS NOT NULL
          AND ac.winning_sp IS NOT NULL
          AND ac.winning_sp > 0
          AND ac.cover_count > 0
        ORDER BY ac.issue, ac.match_idx, ac.action_code
    """
    out: list[ActionRow] = []
    for r in conn.execute(sql, [min_year, *quality_params]):
        of = outcome_map.get((int(r["match_id"]), str(r["action_code"])))
        out.append(
            ActionRow(
                match_id=int(r["match_id"]),
                issue=str(r["issue"]),
                match_idx=int(r["match_idx"]),
                kickoff_ts=str(r["kickoff_ts"]),
                season_year=int(r["season_year"]),
                league=str(r["league"]) if r["league"] is not None else "",
                hcp=float(r["hcp"]),
                result_code=str(r["result_code"]),
                winning_sp=float(r["winning_sp"]),
                action_code=str(r["action_code"]),
                action_label=str(r["action_label"]),
                selection_set=str(r["selection_set"]),
                cover_count=int(r["cover_count"]),
                hit=int(r["hit"]),
                factor=float(r["factor"]),
                euro_final_odds=as_float(of["euro_final_odds"]) if of else None,
                euro_final_p=as_float(of["euro_final_p"]) if of else None,
                euro_1h_odds=as_float(of["euro_1h_odds"]) if of else None,
                euro_1h_p=as_float(of["euro_1h_p"]) if of else None,
                euro_10h_odds=as_float(of["euro_10h_odds"]) if of else None,
                euro_10h_p=as_float(of["euro_10h_p"]) if of else None,
                euro_final_rank=(int(of["euro_final_rank"]) if of and of["euro_final_rank"] is not None else None),
                kelly_final=as_float(of["kelly_final"]) if of else None,
                kelly_10h=as_float(of["kelly_10h"]) if of else None,
                kelly_1h=as_float(of["kelly_1h"]) if of else None,
                kelly_initial=as_float(of["kelly_initial"]) if of else None,
                kelly_move_10h_final=as_float(of["kelly_move_10h_final"]) if of else None,
            )
        )
    conn.close()
    return out


def snapshot_odds_p(row: ActionRow, snapshot: str) -> tuple[float | None, float | None]:
    if snapshot == "final":
        return row.euro_final_odds, row.euro_final_p
    if snapshot == "1h":
        return row.euro_1h_odds, row.euro_1h_p
    if snapshot == "10h":
        return row.euro_10h_odds, row.euro_10h_p
    raise ValueError(f"unsupported snapshot: {snapshot}")


def issue_order(rows_: list[ActionRow]) -> list[str]:
    return sorted({r.issue for r in rows_})


def group_by_issue(rows_: list[ActionRow]) -> dict[str, list[ActionRow]]:
    grouped: dict[str, list[ActionRow]] = defaultdict(list)
    for r in rows_:
        grouped[r.issue].append(r)
    return dict(grouped)


def snapshot_rank_lookup(rows_: Iterable[ActionRow], snapshot: str) -> dict[tuple[int, str], int]:
    grouped: dict[int, dict[str, float]] = defaultdict(dict)
    for row in rows_:
        if row.action_code not in SINGLE_ACTIONS:
            continue
        _, p = snapshot_odds_p(row, snapshot)
        if p is None or p <= 0:
            continue
        grouped[row.match_id][row.action_code] = p

    ranks: dict[tuple[int, str], int] = {}
    for match_id, by_action in grouped.items():
        if not all(action in by_action for action in SINGLE_ACTIONS):
            continue
        for action, p in by_action.items():
            ranks[(match_id, action)] = 1 + sum(1 for other_p in by_action.values() if other_p > p)
    return ranks


def q_key(row: ActionRow, market_p: float | None, market_rank: int | None = None) -> tuple[str, str, str, str]:
    rank = str(market_rank) if market_rank is not None else "missing"
    return (row.action_code, hcp_bucket(row.hcp), rank, p_bucket(market_p))


def train_q_model(
    rows_: Iterable[ActionRow],
    *,
    snapshot: str,
    prior_n: int,
) -> tuple[dict[tuple[str, str, str, str], float], float]:
    rows_list = list(rows_)
    rank_lookup = snapshot_rank_lookup(rows_list, snapshot)
    sums: dict[tuple[str, str, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    global_hit = 0.0
    global_p = 0.0
    for row in rows_list:
        if row.action_code not in SINGLE_ACTIONS:
            continue
        odds, p = snapshot_odds_p(row, snapshot)
        if odds is None or odds <= 1 or p is None or p <= 0:
            continue
        key = q_key(row, p, rank_lookup.get((row.match_id, row.action_code)))
        sums[key][0] += row.hit
        sums[key][1] += p
        sums[key][2] += 1
        global_hit += row.hit
        global_p += p
    global_q = (global_hit / global_p) if global_p > 0 else 1.0
    model: dict[tuple[str, str, str, str], float] = {}
    for key, (hits, p_sum, n) in sums.items():
        if p_sum <= 0 or n <= 0:
            continue
        raw_q = hits / p_sum
        model[key] = (raw_q * n + global_q * prior_n) / (n + prior_n)
    return model, global_q


def train_action_factor_model(
    rows_: Iterable[ActionRow],
    *,
    prior_n: int,
) -> tuple[dict[tuple[str, float], dict[str, float]], dict[str, float]]:
    per_rule: dict[tuple[str, float], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    per_action: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for row in rows_:
        key = (row.action_code, row.hcp)
        per_rule[key][0] += row.factor
        per_rule[key][1] += row.hit
        per_rule[key][2] += 1
        per_action[row.action_code][0] += row.factor
        per_action[row.action_code][1] += row.hit
        per_action[row.action_code][2] += 1

    action_avg: dict[str, float] = {}
    action_hit: dict[str, float] = {}
    for action, (factor_sum, hit_sum, n) in per_action.items():
        action_avg[action] = factor_sum / n if n > 0 else 1.0
        action_hit[action] = hit_sum / n if n > 0 else 0.0

    model: dict[tuple[str, float], dict[str, float]] = {}
    for key, (factor_sum, hit_sum, n) in per_rule.items():
        action = key[0]
        raw_factor = factor_sum / n if n > 0 else 0.0
        prior_factor = action_avg.get(action, 1.0)
        raw_hit = hit_sum / n if n > 0 else 0.0
        prior_hit = action_hit.get(action, raw_hit)
        model[key] = {
            "n": n,
            "factor": (raw_factor * n + prior_factor * prior_n) / (n + prior_n),
            "raw_factor": raw_factor,
            "hit_rate": (raw_hit * n + prior_hit * prior_n) / (n + prior_n),
            "raw_hit_rate": raw_hit,
        }
    return model, action_avg


def train_selected_local_rules(
    action_model: dict[tuple[str, float], dict[str, float]],
    *,
    n_legs: int,
    min_rule_n: int,
    margin: float,
) -> set[tuple[str, float]]:
    threshold = break_even_factor(n_legs) + margin
    selected = set()
    for key, stats in action_model.items():
        action, hcp = key
        if action == "NONE":
            continue
        if stats["n"] < min_rule_n:
            continue
        if stats["factor"] >= threshold:
            selected.add((action, hcp))
    return selected


def build_q_baseline_legs(
    issue_rows: Iterable[ActionRow],
    q_model: dict[tuple[str, str, str, str], float],
    global_q: float,
    *,
    snapshot: str,
    min_proxy_odds: float,
    max_proxy_odds: float,
    min_score_factor: float,
) -> list[Leg]:
    rows_list = list(issue_rows)
    rank_lookup = snapshot_rank_lookup(rows_list, snapshot)
    out: list[Leg] = []
    for row in rows_list:
        if row.action_code not in SINGLE_ACTIONS:
            continue
        odds, p = snapshot_odds_p(row, snapshot)
        if odds is None or odds < min_proxy_odds or odds > max_proxy_odds or p is None or p <= 0:
            continue
        key = q_key(row, p, rank_lookup.get((row.match_id, row.action_code)))
        q = q_model.get(key, global_q)
        p_hat = min(0.98, max(0.001, q * p))
        score = p_hat * odds
        if score < min_score_factor:
            continue
        out.append(
            Leg(
                row=row,
                strategy="baseline_q_high_sp",
                score_factor=score,
                p_hat=p_hat,
                source_rule=f"q_bucket={key};snapshot_rank={snapshot}",
            )
        )
    return out


def build_action_rule_legs(
    issue_rows: Iterable[ActionRow],
    action_model: dict[tuple[str, float], dict[str, float]],
    selected_rules: set[tuple[str, float]],
    *,
    strategy: str,
    min_score_factor: float,
) -> list[Leg]:
    out: list[Leg] = []
    for row in issue_rows:
        key = (row.action_code, row.hcp)
        if key not in selected_rules:
            continue
        stats = action_model.get(key)
        if not stats:
            continue
        score = stats["factor"]
        if score < min_score_factor:
            continue
        out.append(
            Leg(
                row=row,
                strategy=strategy,
                score_factor=score,
                p_hat=min(0.999, max(0.001, stats["hit_rate"])),
                source_rule=f"action_hcp={row.action_code}@{row.hcp:g};train_n={int(stats['n'])}",
            )
        )
    return out


def dedup_legs_by_match(legs: Iterable[Leg]) -> list[Leg]:
    best: dict[int, Leg] = {}
    for leg in legs:
        prev = best.get(leg.row.match_id)
        if prev is None:
            best[leg.row.match_id] = leg
            continue
        prev_key = (prev.score_factor, prev.p_hat, -prev.row.cover_count)
        new_key = (leg.score_factor, leg.p_hat, -leg.row.cover_count)
        if new_key > prev_key:
            best[leg.row.match_id] = leg
    return sorted(best.values(), key=lambda x: (x.score_factor, x.p_hat), reverse=True)


def full_cover_lookup(issue_rows: Iterable[ActionRow]) -> dict[int, ActionRow]:
    out = {}
    for row in issue_rows:
        if row.action_code == "310":
            out[row.match_id] = row
    return out


def protect_with_full_cover(
    legs: tuple[Leg, ...],
    full_rows: dict[int, ActionRow],
    action_model: dict[tuple[str, float], dict[str, float]],
    *,
    count: int,
) -> tuple[Leg, ...]:
    if count <= 0:
        return legs
    converted = list(legs)
    candidates = sorted(
        [i for i, leg in enumerate(converted) if leg.row.cover_count < 3 and leg.row.match_id in full_rows],
        key=lambda i: (converted[i].p_hat, converted[i].score_factor),
    )
    for i in candidates[:count]:
        full = full_rows[converted[i].row.match_id]
        stats = action_model.get(("310", full.hcp), {})
        score = float(stats.get("factor", 1.0))
        converted[i] = Leg(
            row=full,
            strategy=converted[i].strategy,
            score_factor=score,
            p_hat=1.0,
            source_rule=f"full_cover_replace({converted[i].source_rule})",
            is_full_cover=True,
        )
    return tuple(converted)


def make_tickets(
    legs: Iterable[Leg],
    *,
    strategy: str,
    issue: str,
    n_legs: int,
    max_tickets: int,
    overlap_penalty: float,
    train_start_issue: str,
    train_end_issue: str,
    full_rows: dict[int, ActionRow],
    action_model: dict[tuple[str, float], dict[str, float]],
    protect_full_count: int = 0,
) -> list[Ticket]:
    pool = dedup_legs_by_match(legs)
    if len(pool) < n_legs:
        return []

    used: Counter[str] = Counter()
    seen_combo_keys: set[tuple[str, ...]] = set()
    tickets: list[Ticket] = []
    attempts = 0
    max_attempts = max_tickets * 10
    while len(tickets) < max_tickets and attempts < max_attempts:
        attempts += 1
        ranked = sorted(
            pool,
            key=lambda leg: (
                math.log(max(leg.score_factor, 1e-9)) - overlap_penalty * used[leg.leg_id],
                leg.p_hat,
            ),
            reverse=True,
        )
        chosen = tuple(ranked[:n_legs])
        if len({leg.row.match_id for leg in chosen}) < n_legs:
            break
        chosen = protect_with_full_cover(
            chosen,
            full_rows,
            action_model,
            count=protect_full_count,
        )
        combo_key = tuple(sorted(leg.leg_id for leg in chosen))
        if combo_key in seen_combo_keys:
            for leg in chosen:
                used[leg.leg_id] += 1
            continue
        seen_combo_keys.add(combo_key)
        ticket_idx = len(tickets) + 1
        tickets.append(
            Ticket(
                strategy=strategy,
                issue=issue,
                n_legs=n_legs,
                ticket_idx=ticket_idx,
                train_start_issue=train_start_issue,
                train_end_issue=train_end_issue,
                legs=chosen,
            )
        )
        for leg in chosen:
            used[leg.leg_id] += 1
    return tickets


def settle_ticket(ticket: Ticket) -> dict[str, object]:
    stake_units = 1
    pred_factor_product = 1.0
    p_product = 1.0
    sp_product = 1.0
    hit = 1
    n_full = 0
    n_double = 0
    legs_desc = []
    for leg in ticket.legs:
        row = leg.row
        stake_units *= row.cover_count
        pred_factor_product *= max(leg.score_factor, 0.0)
        p_product *= max(0.0, min(1.0, leg.p_hat))
        if row.cover_count == 3:
            n_full += 1
        elif row.cover_count == 2:
            n_double += 1
        if row.hit != 1:
            hit = 0
        sp_product *= row.winning_sp
        legs_desc.append(
            f"{row.match_id}:{row.action_code}@{row.hcp:g}"
        )

    if hit:
        payout = RETURN_RATE * sp_product
        profit = payout - stake_units
    else:
        payout = 0.0
        profit = -float(stake_units)

    return {
        "strategy": ticket.strategy,
        "issue": ticket.issue,
        "n_legs": ticket.n_legs,
        "ticket_idx": ticket.ticket_idx,
        "train_start_issue": ticket.train_start_issue,
        "train_end_issue": ticket.train_end_issue,
        "n_full_cover": n_full,
        "n_double_cover": n_double,
        "stake_units": stake_units,
        "hit": hit,
        "payout_units": payout,
        "profit_units": profit,
        "roi": profit / stake_units if stake_units else 0.0,
        "pred_factor_product": pred_factor_product,
        "pred_ev_per_stake": RETURN_RATE * pred_factor_product - 1.0,
        "pred_hit_prob": p_product,
        "legs": ";".join(legs_desc),
    }


def summarize_tickets(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in ticket_rows:
        grouped[(str(row["strategy"]), int(row["n_legs"]))].append(row)

    baseline_roi: dict[int, float] = {}
    for (strategy, n), rows_ in grouped.items():
        if strategy == "baseline_q_high_sp":
            stake = sum(float(r["stake_units"]) for r in rows_)
            profit = sum(float(r["profit_units"]) for r in rows_)
            baseline_roi[n] = profit / stake if stake > 0 else float("nan")

    out: list[dict[str, object]] = []
    for (strategy, n), rows_ in sorted(grouped.items()):
        rows_ = sorted(rows_, key=lambda r: (str(r["issue"]), int(r["ticket_idx"])))
        stake = sum(float(r["stake_units"]) for r in rows_)
        profit = sum(float(r["profit_units"]) for r in rows_)
        hits = sum(int(r["hit"]) for r in rows_)
        issue_stakes: dict[str, float] = defaultdict(float)
        issue_profit: dict[str, float] = defaultdict(float)
        equity = 10_000.0
        peak = equity
        max_dd = 0.0
        max_loss_streak = 0
        cur_loss_streak = 0
        for r in rows_:
            issue_stakes[str(r["issue"])] += float(r["stake_units"])
            issue_profit[str(r["issue"])] += float(r["profit_units"])
            equity += float(r["profit_units"])
            peak = max(peak, equity)
            if peak > 0:
                max_dd = min(max_dd, (equity - peak) / peak)
            if int(r["hit"]) == 1:
                cur_loss_streak = 0
            else:
                cur_loss_streak += 1
                max_loss_streak = max(max_loss_streak, cur_loss_streak)

        issue_win_rate = (
            sum(1 for v in issue_profit.values() if v > 0) / len(issue_profit)
            if issue_profit
            else float("nan")
        )
        profitable_issues = sum(1 for v in issue_profit.values() if v > 0)
        best_issue_profit = max(issue_profit.values()) if issue_profit else 0.0
        roi = profit / stake if stake > 0 else float("nan")
        base = baseline_roi.get(n)
        verdict, verdict_reason = strategy_verdict(
            n_tickets=len(rows_),
            roi=roi,
            profitable_issues=profitable_issues,
            best_issue_profit_share=(
                best_issue_profit / profit if profit > 0 and best_issue_profit > 0 else None
            ),
            hit_rate=hits / len(rows_) if rows_ else 0.0,
        )
        out.append(
            {
                "strategy": strategy,
                "n_legs": n,
                "n_tickets": len(rows_),
                "n_issues": len(issue_profit),
                "hit_rate": hits / len(rows_) if rows_ else float("nan"),
                "issue_win_rate": issue_win_rate,
                "profitable_issues": profitable_issues,
                "total_stake_units": stake,
                "total_profit_units": profit,
                "roi": roi,
                "excess_roi_vs_baseline": (
                    roi - base if base is not None and math.isfinite(base) and strategy != "baseline_q_high_sp" else ""
                ),
                "best_issue_profit_units": best_issue_profit,
                "best_issue_profit_share": (
                    best_issue_profit / profit if profit > 0 and best_issue_profit > 0 else ""
                ),
                "avg_issue_stake_units": mean(issue_stakes.values()) if issue_stakes else 0.0,
                "max_issue_stake_units": max(issue_stakes.values()) if issue_stakes else 0.0,
                "max_drawdown_pct_on_10000": max_dd,
                "max_ticket_loss_streak": max_loss_streak,
                "avg_full_cover_per_ticket": mean(float(r["n_full_cover"]) for r in rows_) if rows_ else 0.0,
                "avg_double_cover_per_ticket": mean(float(r["n_double_cover"]) for r in rows_) if rows_ else 0.0,
                "avg_pred_ev_per_stake": mean(float(r["pred_ev_per_stake"]) for r in rows_) if rows_ else 0.0,
                "verdict": verdict,
                "verdict_reason": verdict_reason,
            }
        )
    return out


def strategy_verdict(
    *,
    n_tickets: int,
    roi: float,
    profitable_issues: int,
    best_issue_profit_share: float | None,
    hit_rate: float,
) -> tuple[str, str]:
    if n_tickets < 1000:
        return "insufficient_volume", "fewer than 1000 simulated tickets"
    if hit_rate <= 0:
        return "fail_no_hits", "zero winning tickets"
    if roi <= 0:
        return "fail_negative_roi", "realized ROI is not positive"
    if profitable_issues < 3:
        return "fail_concentrated", "positive result comes from fewer than 3 profitable issues"
    if best_issue_profit_share is not None and best_issue_profit_share > 0.70:
        return "fail_concentrated", "best issue contributes more than 70% of net profit"
    return "pass_watchlist", "passes initial ROI and concentration gates"


def write_csv(path: Path, rows_: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        if not rows_:
            f.write("")
            return
        writer = csv.DictWriter(f, fieldnames=list(rows_[0].keys()))
        writer.writeheader()
        writer.writerows(rows_)


def fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.4f}"
    return str(value)


def md_table(rows_: list[dict[str, object]], limit: int | None = None) -> str:
    if limit is not None:
        rows_ = rows_[:limit]
    if not rows_:
        return "_No rows._\n"
    headers = list(rows_[0].keys())
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows_:
        out.append("| " + " | ".join(fmt(row.get(h)) for h in headers) + " |")
    return "\n".join(out) + "\n"


def compact_summary(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "strategy",
        "n_legs",
        "n_tickets",
        "n_issues",
        "hit_rate",
        "issue_win_rate",
        "profitable_issues",
        "roi",
        "excess_roi_vs_baseline",
        "total_profit_units",
        "best_issue_profit_share",
        "avg_issue_stake_units",
        "max_drawdown_pct_on_10000",
        "max_ticket_loss_streak",
        "avg_full_cover_per_ticket",
        "avg_double_cover_per_ticket",
        "verdict",
        "verdict_reason",
    ]
    return [{k: row[k] for k in keep} for row in summary]


def verdict_counts(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    counts: Counter[str] = Counter(str(row["verdict"]) for row in summary)
    return [{"verdict": k, "count": v} for k, v in sorted(counts.items())]


def run_walkforward(args: argparse.Namespace) -> None:
    all_rows = load_action_rows(args.db, args.min_year)
    if not all_rows:
        raise SystemExit("No settled action rows found. Build modeling tables first.")

    by_issue = group_by_issue(all_rows)
    issues = issue_order(all_rows)
    if len(issues) <= args.train_issues:
        raise SystemExit(
            f"Need more issues than train window. issues={len(issues)} train_issues={args.train_issues}"
        )

    ticket_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    n_values = tuple(int(x) for x in args.n_values.split(",") if x.strip())

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues:issue_idx]
        train_rows = [r for issue in train_issues for r in by_issue[issue]]
        test_rows = by_issue[test_issue]
        train_start, train_end = train_issues[0], train_issues[-1]

        q_model, global_q = train_q_model(
            train_rows,
            snapshot=args.snapshot,
            prior_n=args.q_prior_n,
        )
        action_model, _ = train_action_factor_model(
            train_rows,
            prior_n=args.rule_prior_n,
        )
        full_rows = full_cover_lookup(test_rows)

        for n_legs in n_values:
            threshold = break_even_factor(n_legs) + args.min_factor_margin
            local_rules = train_selected_local_rules(
                action_model,
                n_legs=n_legs,
                min_rule_n=args.min_rule_n,
                margin=args.min_factor_margin,
            )
            fixed_rules = {
                rule
                for rule in FIXED_EDGE_RULES
                if action_model.get(rule, {}).get("n", 0) >= args.min_rule_n
                and action_model.get(rule, {}).get("factor", 0.0) >= threshold
            }
            window_rows.append(
                {
                    "test_issue": test_issue,
                    "n_legs": n_legs,
                    "train_start_issue": train_start,
                    "train_end_issue": train_end,
                    "train_action_rows": len(train_rows),
                    "test_action_rows": len(test_rows),
                    "global_q": global_q,
                    "threshold_factor": threshold,
                    "n_q_buckets": len(q_model),
                    "n_local_rules": len(local_rules),
                    "n_fixed_rules_active": len(fixed_rules),
                    "local_rules": ";".join(f"{a}@{h:g}" for a, h in sorted(local_rules)),
                    "fixed_rules": ";".join(f"{a}@{h:g}" for a, h in sorted(fixed_rules)),
                }
            )

            strategies: list[tuple[str, list[Leg], int]] = []
            strategies.append(
                (
                    "baseline_q_high_sp",
                    build_q_baseline_legs(
                        test_rows,
                        q_model,
                        global_q,
                        snapshot=args.snapshot,
                        min_proxy_odds=args.baseline_min_proxy_odds,
                        max_proxy_odds=args.baseline_max_proxy_odds,
                        min_score_factor=threshold,
                    ),
                    0,
                )
            )
            strategies.append(
                (
                    "fixed_handicap_edges",
                    build_action_rule_legs(
                        test_rows,
                        action_model,
                        fixed_rules,
                        strategy="fixed_handicap_edges",
                        min_score_factor=threshold,
                    ),
                    0,
                )
            )
            strategies.append(
                (
                    "local_best_action_hcp",
                    build_action_rule_legs(
                        test_rows,
                        action_model,
                        local_rules,
                        strategy="local_best_action_hcp",
                        min_score_factor=threshold,
                    ),
                    0,
                )
            )
            strategies.append(
                (
                    "local_best_plus_1_full",
                    build_action_rule_legs(
                        test_rows,
                        action_model,
                        local_rules,
                        strategy="local_best_plus_1_full",
                        min_score_factor=threshold,
                    ),
                    1,
                )
            )

            for strategy, legs, protect_full_count in strategies:
                tickets = make_tickets(
                    legs,
                    strategy=strategy,
                    issue=test_issue,
                    n_legs=n_legs,
                    max_tickets=args.max_tickets_per_issue,
                    overlap_penalty=args.overlap_penalty,
                    train_start_issue=train_start,
                    train_end_issue=train_end,
                    full_rows=full_rows,
                    action_model=action_model,
                    protect_full_count=protect_full_count,
                )
                ticket_rows.extend(settle_ticket(t) for t in tickets)

    summary = summarize_tickets(ticket_rows)
    summary_sorted = sorted(
        summary,
        key=lambda r: (
            int(r["n_legs"]),
            -float(r["roi"]) if isinstance(r["roi"], float) and math.isfinite(float(r["roi"])) else 0,
            str(r["strategy"]),
        ),
    )

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "walkforward_tickets.csv", ticket_rows)
    write_csv(out / "walkforward_summary.csv", summary_sorted)
    write_csv(out / "walkforward_windows.csv", window_rows)

    break_even = [
        {"n_legs": n, "break_even_factor": break_even_factor(n)}
        for n in n_values
    ]
    report = [
        "# Beidan high-N walk-forward strategy evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Settled min year: `{args.min_year}`",
        f"- Issue train window: `{args.train_issues}`",
        f"- Snapshot proxy for q baseline: `{args.snapshot}` company euro odds",
        f"- Max tickets per issue per strategy/N: `{args.max_tickets_per_issue}`",
        f"- Baseline proxy odds band: `{args.baseline_min_proxy_odds}` to `{args.baseline_max_proxy_odds}`",
        f"- Test issues: `{max(0, len(issues) - args.train_issues)}`",
        "",
        "## Important limitation",
        "",
        "The source history has actual official winning SP, but not official pre-match SP "
        "for every losing outcome. Therefore settlement uses actual winning SP, while "
        "the high-SP/q baseline ranks candidates with company euro odds as the ex-ante "
        "price proxy. Handicap-rule strategies are trained from realized historical "
        "factor and are directly settled with actual winning SP.",
        "",
        "## Break-even factor",
        md_table(break_even),
        "## Decision gates",
        "",
        "- `pass_watchlist` requires positive ROI, at least 3 profitable issues, "
        "and no single issue contributing more than 70% of net profit.",
        "- Positive ROI with fewer than 3 profitable issues is treated as concentrated "
        "and not ready for live observation.",
        "- These gates are deliberately conservative because high-N returns are extremely lumpy.",
        "",
        "## Verdict counts",
        md_table(verdict_counts(summary_sorted)),
        "## Summary",
        md_table(compact_summary(summary_sorted)),
        "## Active rule counts by window",
        md_table(window_rows[:40]),
        "## Files",
        "",
        "- `walkforward_summary.csv`: aggregate metrics by strategy and N",
        "- `walkforward_tickets.csv`: ticket-level ledger and leg IDs",
        "- `walkforward_windows.csv`: train/test windows and active rules",
        "",
    ]
    (out / "walkforward_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'walkforward_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows and {len(summary_sorted)} summary rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_walkforward"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=24)
    parser.add_argument("--n-values", default="8,10,12,15")
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--max-tickets-per-issue", type=int, default=50)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--rule-prior-n", type=int, default=120)
    parser.add_argument("--min-rule-n", type=int, default=160)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run_walkforward(args)


if __name__ == "__main__":
    main()
