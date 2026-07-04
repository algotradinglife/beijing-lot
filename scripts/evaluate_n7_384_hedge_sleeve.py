#!/usr/bin/env python3
"""Evaluate small-N hedge sleeves against the selected N7 384 profile."""
from __future__ import annotations

import argparse
import csv
import html
import math
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_combo_main_cold_tail import build_cold_candidates
from scripts.evaluate_n7_confidence_coverage import group_samples_by_issue, model_probabilities
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras, market_probs
from scripts.walkforward_beidan_strategy_eval import (
    Leg,
    Ticket,
    break_even_factor,
    default_db_path,
    load_action_rows,
    md_table,
    settle_ticket,
    write_csv,
)


ISSUE_BUDGET = 256.0
BASE_ISSUE_PATH = Path("results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv")
BASE_PORTFOLIO = "b384_dd32_smooth80_convex19"
BASE_BUDGET = 384.0


@dataclass(frozen=True)
class HedgeProfile:
    name: str
    n_legs: int
    min_odds: float
    max_odds: float
    min_model_p: float
    max_model_p: float
    min_ratio: float
    rank_min: int
    min_score: float
    max_score: float
    tickets_per_issue: int


def parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first + extra)
        writer.writeheader()
        writer.writerows(rows)


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def issue_year(issue: object) -> int:
    text = str(issue)
    if len(text) >= 2 and text[:2].isdigit():
        yy = int(text[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def load_issue_calendar(db_path: Path) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            issue,
            MIN(kickoff_ts) AS issue_start_ts,
            MAX(kickoff_ts) AS issue_close_ts,
            MAX(season_year) AS season_year
        FROM action_candidates
        WHERE has_winning_sp = 1
          AND kickoff_ts IS NOT NULL
        GROUP BY issue
        ORDER BY issue_close_ts, issue
        """
    ).fetchall()
    conn.close()
    return {
        str(row["issue"]): {
            "issue_start_ts": str(row["issue_start_ts"]),
            "issue_close_ts": str(row["issue_close_ts"]),
            "issue_order": idx,
            "calendar_year": int(str(row["issue_close_ts"])[:4]),
            "season_year": int(row["season_year"]) if row["season_year"] is not None else issue_year(row["issue"]),
        }
        for idx, row in enumerate(rows)
    }


def row_year(row: dict[str, object]) -> int:
    if row.get("calendar_year") not in ("", None):
        return int(str(row["calendar_year"]))
    close_ts = str(row.get("issue_close_ts", ""))
    if len(close_ts) >= 4 and close_ts[:4].isdigit():
        return int(close_ts[:4])
    return issue_year(row.get("issue", ""))


def row_order(row: dict[str, object]) -> tuple[int, str]:
    order = row.get("issue_order")
    if order not in ("", None):
        return int(float(str(order))), str(row.get("issue", ""))
    return 10**9 + issue_year(row.get("issue", "")), str(row.get("issue", ""))


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("risk_units"), fnum(row.get("stake_units")))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def max_drawdown_units(rows: list[dict[str, object]]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for row in sorted(rows, key=row_order):
        equity += fnum(row.get("profit_units"))
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def max_loss_streak(rows: list[dict[str, object]]) -> int:
    cur = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if fnum(row.get("profit_units")) <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def max_dead_streak(rows: list[dict[str, object]]) -> int:
    cur = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if full_loss(row):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def max_underwater_profit_window(rows: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    equity = 0.0
    peak = 0.0
    peak_idx = -1
    worst = {
        "maxdd_window_start_issue": "",
        "maxdd_window_end_issue": "",
        "maxdd_window_issues": 0,
        "maxdd_window_wins": 0,
        "maxdd_window_full_losses": 0,
    }
    worst_dd = 0.0
    for idx, row in enumerate(ordered):
        equity += fnum(row.get("profit_units"))
        if equity >= peak:
            peak = equity
            peak_idx = idx
            continue
        dd = equity - peak
        if dd < worst_dd:
            segment = ordered[peak_idx + 1 : idx + 1]
            worst_dd = dd
            worst = {
                "maxdd_window_start_issue": str(ordered[peak_idx]["issue"]) if peak_idx >= 0 else "",
                "maxdd_window_end_issue": str(row["issue"]),
                "maxdd_window_issues": len(segment),
                "maxdd_window_wins": sum(1 for item in segment if fnum(item.get("profit_units")) > 0),
                "maxdd_window_full_losses": sum(1 for item in segment if full_loss(item)),
            }
    return worst


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["portfolio"]), row_year(row))].append(row)
    out: list[dict[str, object]] = []
    for (portfolio, year), vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "portfolio": portfolio,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
                if vals
                else math.nan,
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def equity_points(rows: list[dict[str, object]]) -> list[tuple[int, float, str]]:
    equity = 0.0
    points: list[tuple[int, float, str]] = []
    for idx, row in enumerate(sorted(rows, key=row_order)):
        equity += fnum(row.get("profit_units"))
        points.append((idx, equity, str(row.get("issue_close_ts", row.get("issue", "")))))
    return points


def write_equity_svg(
    path: Path,
    series_rows: dict[str, list[dict[str, object]]],
    calendar: dict[str, dict[str, object]],
) -> None:
    width = 1180
    height = 620
    left = 72
    right = 24
    top = 32
    bottom = 72
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#bcbd22"]
    points_by_name = {name: equity_points(rows) for name, rows in series_rows.items()}
    all_points = [point for points in points_by_name.values() for point in points]
    if not all_points:
        path.write_text("", encoding="utf-8")
        return
    max_x = max(x for x, _y, _ts in all_points) or 1
    min_y = min(0.0, min(y for _x, y, _ts in all_points))
    max_y = max(0.0, max(y for _x, y, _ts in all_points))
    pad_y = max((max_y - min_y) * 0.08, 1000.0)
    min_y -= pad_y
    max_y += pad_y

    def sx(x: int) -> float:
        return left + plot_w * x / max_x

    def sy(y: float) -> float:
        return top + plot_h * (max_y - y) / (max_y - min_y)

    ordered_issues = sorted(calendar.items(), key=lambda item: int(item[1].get("issue_order", 10**9)))
    year_ticks = []
    seen_years = set()
    for _issue, meta in ordered_issues:
        year = int(meta.get("calendar_year", 0))
        order = int(meta.get("issue_order", 0))
        if year and year not in seen_years and order <= max_x:
            seen_years.add(year)
            if year % 2 == 0 or year in (2014, 2025):
                year_ticks.append((order, year))

    elems = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222" stroke-width="1"/>',
    ]
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y_value = min_y + (max_y - min_y) * frac
        y = sy(y_value)
        elems.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        elems.append(
            f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="12" fill="#374151">{y_value:,.0f}</text>'
        )
    for order, year in year_ticks:
        x = sx(order)
        elems.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" stroke="#f3f4f6"/>')
        elems.append(f'<text x="{x:.2f}" y="{height - 36}" text-anchor="middle" font-size="12" fill="#374151">{year}</text>')
    zero_y = sy(0.0)
    elems.append(f'<line x1="{left}" y1="{zero_y:.2f}" x2="{left + plot_w}" y2="{zero_y:.2f}" stroke="#9ca3af" stroke-dasharray="4 4"/>')

    for idx, (name, points) in enumerate(points_by_name.items()):
        color = colors[idx % len(colors)]
        coords = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y, _ts in points)
        elems.append(
            f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        lx = left + 12 + (idx % 2) * 430
        ly = top + 18 + (idx // 2) * 22
        elems.append(f'<line x1="{lx}" y1="{ly - 5}" x2="{lx + 26}" y2="{ly - 5}" stroke="{color}" stroke-width="3"/>')
        elems.append(f'<text x="{lx + 34}" y="{ly}" font-size="13" fill="#111827">{html.escape(name)}</text>')
    elems.append(f'<text x="{width / 2:.0f}" y="{height - 12}" text-anchor="middle" font-size="13" fill="#374151">Issue close time</text>')
    elems.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(elems), encoding="utf-8")


def score_bands(raw: str) -> list[tuple[str, float, float]]:
    bands = []
    for item in raw.split(","):
        if not item.strip():
            continue
        name, lo, hi = item.split(":")
        bands.append((name, float(lo), float(hi)))
    return bands


def build_profiles(args: argparse.Namespace) -> list[HedgeProfile]:
    profiles: list[HedgeProfile] = []
    for n_legs in parse_ints(args.n_values):
        for min_odds in parse_floats(args.min_odds_values):
            for min_model_p in parse_floats(args.min_model_p_values):
                for max_model_p in parse_floats(args.max_model_p_values):
                    for min_ratio in parse_floats(args.min_ratio_values):
                        for rank_min in parse_ints(args.rank_min_values):
                            for band_name, min_score, max_score in score_bands(args.score_bands):
                                for tickets_per_issue in parse_ints(args.tickets_per_issue_values):
                                    max_p_label = "any" if max_model_p <= 0 else f"{int(round(max_model_p * 100)):02d}"
                                    max_score_label = "any" if max_score <= 0 else f"{int(round(max_score * 1000)):04d}"
                                    name = (
                                        f"n{n_legs}_odds{min_odds:g}_"
                                        f"p{int(round(min_model_p * 100)):02d}-{max_p_label}_"
                                        f"r{int(round(min_ratio * 100)):03d}_rank{rank_min}_"
                                        f"{band_name}{int(round(min_score * 1000)):04d}-{max_score_label}_"
                                        f"k{tickets_per_issue}"
                                    )
                                    profiles.append(
                                        HedgeProfile(
                                            name=name,
                                            n_legs=n_legs,
                                            min_odds=min_odds,
                                            max_odds=args.max_odds,
                                            min_model_p=min_model_p,
                                            max_model_p=max_model_p,
                                            min_ratio=min_ratio,
                                            rank_min=rank_min,
                                            min_score=min_score,
                                            max_score=max_score,
                                            tickets_per_issue=tickets_per_issue,
                                        )
                                    )
    return profiles


def profile_passes(profile: HedgeProfile, candidate: dict[str, object]) -> bool:
    odds = float(candidate["odds"])
    model_p = float(candidate["model_p"])
    ratio = float(candidate["model_market_ratio"])
    rank = int(candidate["rank"])
    score = float(candidate["score_factor"])
    return (
        odds >= profile.min_odds
        and odds <= profile.max_odds
        and model_p >= profile.min_model_p
        and (profile.max_model_p <= 0 or model_p <= profile.max_model_p)
        and ratio >= profile.min_ratio
        and rank >= profile.rank_min
        and score >= profile.min_score
        and (profile.max_score <= 0 or score < profile.max_score)
    )


def hedge_leg(candidate: dict[str, object], profile: HedgeProfile) -> Leg:
    return replace(
        candidate["base_leg"],
        strategy=f"n7_384_hedge_{profile.name}",
        source_rule=(
            f"hedge={profile.name};"
            f"odds={float(candidate['odds']):.4f};"
            f"model_p={float(candidate['model_p']):.4f};"
            f"market_p={float(candidate['market_p']):.4f};"
            f"ratio={float(candidate['model_market_ratio']):.4f};"
            f"score={float(candidate['score_factor']):.4f};"
            f"rank={int(candidate['rank'])}"
        ),
    )


def candidate_score(
    candidate: dict[str, object],
    *,
    used_matches: dict[int, int],
    used_pairs: dict[tuple[int, str], int],
    args: argparse.Namespace,
) -> float:
    match_id = int(candidate["match_id"])
    pair = (match_id, str(candidate["action_code"]))
    odds = max(float(candidate["odds"]), 1.0001)
    model_p = max(float(candidate["model_p"]), 1e-6)
    ratio = max(float(candidate["model_market_ratio"]), 1e-6)
    score = max(float(candidate["score_factor"]), 1e-6)
    return (
        args.odds_weight * math.log(odds)
        + args.model_p_weight * math.log(model_p)
        + args.ratio_weight * math.log(ratio)
        + args.score_weight * math.log(score)
        - args.reuse_match_penalty * used_matches[match_id]
        - args.reuse_pair_penalty * used_pairs[pair]
    )


def build_hedge_tickets(
    *,
    issue: str,
    train_start_issue: str,
    train_end_issue: str,
    profile: HedgeProfile,
    candidates: list[dict[str, object]],
    args: argparse.Namespace,
) -> tuple[list[Ticket], int]:
    passing = [candidate for candidate in candidates if profile_passes(profile, candidate)]
    candidate_matches = len({int(candidate["match_id"]) for candidate in passing})
    if candidate_matches < profile.n_legs:
        return [], candidate_matches

    tickets: list[Ticket] = []
    used_matches: dict[int, int] = defaultdict(int)
    used_pairs: dict[tuple[int, str], int] = defaultdict(int)
    for ticket_idx in range(1, profile.tickets_per_issue + 1):
        ranked = sorted(
            passing,
            key=lambda candidate: candidate_score(
                candidate,
                used_matches=used_matches,
                used_pairs=used_pairs,
                args=args,
            ),
            reverse=True,
        )
        ticket_match_ids: set[int] = set()
        legs: list[Leg] = []
        for candidate in ranked:
            match_id = int(candidate["match_id"])
            pair = (match_id, str(candidate["action_code"]))
            if match_id in ticket_match_ids:
                continue
            if args.max_pair_uses > 0 and used_pairs[pair] >= args.max_pair_uses:
                continue
            if args.max_match_uses > 0 and used_matches[match_id] >= args.max_match_uses:
                continue
            legs.append(hedge_leg(candidate, profile))
            ticket_match_ids.add(match_id)
            if len(legs) >= profile.n_legs:
                break
        if len(legs) < profile.n_legs:
            break
        tickets.append(
            Ticket(
                strategy=f"n7_384_hedge_{profile.name}",
                issue=issue,
                n_legs=profile.n_legs,
                ticket_idx=ticket_idx,
                train_start_issue=train_start_issue,
                train_end_issue=train_end_issue,
                legs=tuple(legs),
            )
        )
        for leg in legs:
            used_matches[leg.row.match_id] += 1
            used_pairs[(leg.row.match_id, leg.row.action_code)] += 1
    return tickets, candidate_matches


def load_base_rows(path: Path, portfolio: str, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for row in read_csv_rows(path):
        if row.get("portfolio") != portfolio:
            continue
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["issue"])] = copied
    if not out:
        raise SystemExit(f"missing base portfolio {portfolio} in {path}")
    return out


def issue_rows(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: {"tickets": 0, "hits": 0, "stake": 0.0, "profit": 0.0, "payout": 0.0})
    for row in ticket_rows:
        key = (str(row["strategy"]), str(row["issue"]))
        g = grouped[key]
        g["tickets"] += 1
        g["hits"] += int(row["hit"])
        g["stake"] += float(row["stake_units"])
        g["profit"] += float(row["profit_units"])
        g["payout"] += float(row["payout_units"])
    out: list[dict[str, object]] = []
    for (strategy, issue), g in sorted(grouped.items()):
        out.append(
            {
                "strategy": strategy,
                "issue": issue,
                "tickets": g["tickets"],
                "hits": g["hits"],
                "stake_units": g["stake"],
                "profit_units": g["profit"],
                "payout_units": g["payout"],
                "roi": g["profit"] / g["stake"] if g["stake"] else math.nan,
            }
        )
    return out


def summarize_rows(rows: list[dict[str, object]], *, recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in ordered)
    budget = fnum(ordered[0].get("issue_budget"), 0.0) if ordered else 0.0
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    recent = [row for row in ordered if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    out = {
        "portfolio": str(ordered[0].get("portfolio", "")) if ordered else "",
        "mode": str(ordered[0].get("mode", "")) if ordered else "",
        "hedge_strategy": str(ordered[0].get("hedge_strategy", "")) if ordered else "",
        "n_legs": int(fnum(ordered[0].get("hedge_n_legs"), 0)) if ordered else 0,
        "hedge_units": fnum(ordered[0].get("hedge_units"), 0.0) if ordered else 0.0,
        "issue_budget": budget,
        "issues": len(ordered),
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_256": profit / (budget / ISSUE_BUDGET) if budget else math.nan,
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered)
        if ordered
        else math.nan,
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered) if ordered else math.nan,
        "full_loss_rate": sum(1 for row in ordered if full_loss(row)) / len(ordered) if ordered else math.nan,
        "max_drawdown_units": max_drawdown_units(ordered),
        "max_drawdown_per_256": max_drawdown_units(ordered) / (budget / ISSUE_BUDGET) if budget else math.nan,
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "hedge_active_issues": sum(1 for row in ordered if fnum(row.get("hedge_raw_stake")) > 0),
        "hedge_hit_issues": sum(1 for row in ordered if fnum(row.get("hedge_hits")) > 0),
        "base_full_loss_saved": sum(
            1
            for row in ordered
            if int(fnum(row.get("base_full_loss"), 0)) == 1 and not full_loss(row)
        ),
        "base_loss_to_profit": sum(
            1
            for row in ordered
            if fnum(row.get("base_profit_units")) < 0 and fnum(row.get("profit_units")) > 0
        ),
        "recent_profit_units": recent_profit,
        "recent_profit_per_256": recent_profit / (budget / ISSUE_BUDGET) if budget else math.nan,
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
    }
    out.update(max_underwater_profit_window(ordered))
    return out


def combine_with_base(
    *,
    base_rows: dict[str, dict[str, object]],
    hedge_issue: dict[tuple[str, str], dict[str, object]],
    profiles_by_strategy: dict[str, HedgeProfile],
    hedge_units_values: list[float],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    base_issues = sorted(base_rows, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))
    for strategy, profile in profiles_by_strategy.items():
        for hedge_units in hedge_units_values:
            if hedge_units <= 0 or hedge_units >= BASE_BUDGET:
                continue
            for mode in ("additive", "same_budget_adaptive"):
                issue_budget = BASE_BUDGET + hedge_units if mode == "additive" else BASE_BUDGET
                portfolio = (
                    f"{BASE_PORTFOLIO}__{mode}__hedge{hedge_units:g}__"
                    f"{strategy.removeprefix('n7_384_hedge_')}"
                )
                for issue in base_issues:
                    base = base_rows[issue]
                    hedge = hedge_issue.get((strategy, issue))
                    raw_stake = fnum(hedge.get("stake_units")) if hedge else 0.0
                    hedge_scale = hedge_units / raw_stake if raw_stake > 0 else 0.0
                    hedge_profit = fnum(hedge.get("profit_units")) * hedge_scale if hedge else 0.0
                    hedge_hits = fnum(hedge.get("hits")) if hedge else 0.0
                    hedge_tickets = fnum(hedge.get("tickets")) if hedge else 0.0
                    if mode == "same_budget_adaptive" and raw_stake > 0:
                        base_scale = (BASE_BUDGET - hedge_units) / BASE_BUDGET
                    else:
                        base_scale = 1.0
                    risk_units = BASE_BUDGET
                    if mode == "additive" and raw_stake > 0:
                        risk_units += hedge_units
                    base_profit = fnum(base.get("profit_units"))
                    profit = base_profit * base_scale + hedge_profit
                    out = {
                        "portfolio": portfolio,
                        "mode": mode,
                        "hedge_strategy": strategy,
                        "hedge_n_legs": profile.n_legs,
                        "hedge_units": hedge_units,
                        "issue": issue,
                        "stake_units": issue_budget,
                        "risk_units": risk_units,
                        "profit_units": profit,
                        "roi": profit / issue_budget if issue_budget else math.nan,
                        "issue_budget": issue_budget,
                        "base_portfolio": BASE_PORTFOLIO,
                        "base_scale": base_scale,
                        "base_profit_units": base_profit,
                        "base_full_loss": int(full_loss(base)),
                        "hedge_raw_stake": raw_stake,
                        "hedge_scale": hedge_scale,
                        "hedge_profit_units": hedge_profit,
                        "hedge_hits": hedge_hits,
                        "hedge_tickets": hedge_tickets,
                    }
                    out.update(calendar.get(issue, {}))
                    rows.append(out)
    return rows


def base_summary_rows(base_rows: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for row in base_rows.values():
        copied = dict(row)
        copied["mode"] = "base"
        copied["hedge_strategy"] = ""
        copied["hedge_n_legs"] = 0
        copied["hedge_units"] = 0
        copied["issue_budget"] = BASE_BUDGET
        copied["risk_units"] = BASE_BUDGET
        copied["base_profit_units"] = copied.get("profit_units", 0.0)
        copied["base_full_loss"] = int(full_loss(copied))
        copied["hedge_raw_stake"] = 0
        copied["hedge_hits"] = 0
        return_field = copied.get("portfolio", BASE_PORTFOLIO)
        copied["portfolio"] = str(return_field)
        rows.append(copied)
    return rows


def top_rows(
    rows: list[dict[str, object]],
    *,
    mode: str,
    base: dict[str, object],
    sort_key: str,
    descending: bool,
    limit: int,
    min_profit_per_256: float | None = None,
) -> list[dict[str, object]]:
    base_dd = fnum(base.get("max_drawdown_units"))
    filtered = [
        row
        for row in rows
        if row.get("mode") == mode
        and (min_profit_per_256 is None or fnum(row.get("profit_per_256")) >= min_profit_per_256)
    ]
    for row in filtered:
        row["max_drawdown_delta_vs_base"] = fnum(row.get("max_drawdown_units")) - base_dd
    filtered.sort(key=lambda row: fnum(row.get(sort_key)), reverse=descending)
    keep_cols = [
        "portfolio",
        "hedge_units",
        "n_legs",
        "profit_per_256",
        "roi",
        "non_full_loss_rate",
        "max_drawdown_per_256",
        "max_drawdown_delta_vs_base",
        "max_dead_streak",
        "base_full_loss_saved",
        "base_loss_to_profit",
        "recent_profit_per_256",
        "hedge_active_issues",
        "hedge_hit_issues",
    ]
    return [{key: row.get(key, "") for key in keep_cols} for row in filtered[:limit]]


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    base_rows = load_base_rows(args.base_issue_path, args.base_portfolio, calendar)
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    profiles = build_profiles(args)
    profiles_by_strategy = {f"n7_384_hedge_{profile.name}": profile for profile in profiles}

    ticket_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        train_samples = [sample for issue in train_issues for sample in samples_by_issue.get(issue, [])]
        test_samples = samples_by_issue.get(test_issue, [])
        if test_issue not in base_rows:
            continue
        if len(train_samples) < args.min_train_matches or not test_samples:
            continue

        probs = model_probabilities(args, train_samples, test_samples)
        candidates = build_cold_candidates(test_samples=test_samples, model_probs=probs, snapshot=args.snapshot)
        raw_market = market_probs(test_samples)
        favorite_share = float(np.mean(np.argmax(raw_market, axis=1) == np.argmax(probs, axis=1))) if len(test_samples) else 0.0
        created = 0
        for profile in profiles:
            tickets, candidate_matches = build_hedge_tickets(
                issue=test_issue,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                profile=profile,
                candidates=candidates,
                args=args,
            )
            created += len(tickets)
            for row in (settle_ticket(ticket) for ticket in tickets):
                row["profile"] = profile.name
                row["score_band_min"] = profile.min_score
                row["score_band_max"] = profile.max_score
                ticket_rows.append(row)
            coverage_rows.append(
                {
                    "issue": test_issue,
                    "strategy": f"n7_384_hedge_{profile.name}",
                    "n_legs": profile.n_legs,
                    "tickets_per_issue": profile.tickets_per_issue,
                    "candidate_matches": candidate_matches,
                    "tickets_created": len(tickets),
                }
            )
        window_rows.append(
            {
                "issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "raw_candidates": len(candidates),
                "raw_candidate_matches": len({int(candidate["match_id"]) for candidate in candidates}),
                "favorite_agreement_share": favorite_share,
                "profiles": len(profiles),
                "tickets_created": created,
            }
        )

    hedge_issue_rows = issue_rows(ticket_rows)
    hedge_issue = {(str(row["strategy"]), str(row["issue"])): row for row in hedge_issue_rows}
    combo_rows = combine_with_base(
        base_rows=base_rows,
        hedge_issue=hedge_issue,
        profiles_by_strategy=profiles_by_strategy,
        hedge_units_values=parse_floats(args.hedge_units_values),
        calendar=calendar,
    )
    base_rows_list = base_summary_rows(base_rows)
    all_summary_rows = [summarize_rows(base_rows_list, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year)]
    grouped_combo: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in combo_rows:
        grouped_combo[str(row["portfolio"])].append(row)
    for rows in grouped_combo.values():
        all_summary_rows.append(
            summarize_rows(rows, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year)
        )
    base_summary = all_summary_rows[0]
    for row in all_summary_rows[1:]:
        row["max_drawdown_delta_vs_base"] = fnum(row.get("max_drawdown_units")) - fnum(base_summary.get("max_drawdown_units"))
        row["profit_per_256_delta_vs_base"] = fnum(row.get("profit_per_256")) - fnum(base_summary.get("profit_per_256"))
        row["non_full_loss_delta_vs_base"] = fnum(row.get("non_full_loss_rate")) - fnum(base_summary.get("non_full_loss_rate"))

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "hedge_tickets.csv", ticket_rows)
    write_csv(out / "hedge_issue_profit.csv", hedge_issue_rows)
    write_csv(out / "hedge_coverage.csv", coverage_rows)
    write_csv(out / "hedge_windows.csv", window_rows)
    write_csv_all(out / "hedge_combo_summary.csv", all_summary_rows)

    same_dd = top_rows(
        all_summary_rows[1:],
        mode="same_budget_adaptive",
        base=base_summary,
        sort_key="max_drawdown_delta_vs_base",
        descending=True,
        limit=args.report_rows,
        min_profit_per_256=args.min_report_profit_per_256,
    )
    same_nonfull = top_rows(
        all_summary_rows[1:],
        mode="same_budget_adaptive",
        base=base_summary,
        sort_key="non_full_loss_rate",
        descending=True,
        limit=args.report_rows,
        min_profit_per_256=args.min_report_profit_per_256,
    )
    add_profit = top_rows(
        all_summary_rows[1:],
        mode="additive",
        base=base_summary,
        sort_key="profit_per_256",
        descending=True,
        limit=args.report_rows,
        min_profit_per_256=args.min_report_profit_per_256,
    )
    add_dd = top_rows(
        all_summary_rows[1:],
        mode="additive",
        base=base_summary,
        sort_key="max_drawdown_delta_vs_base",
        descending=True,
        limit=args.report_rows,
        min_profit_per_256=args.min_report_profit_per_256,
    )

    selected_series = {BASE_PORTFOLIO: base_rows_list}
    selected_names = [row["portfolio"] for row in same_dd[:2] + same_nonfull[:1] + add_dd[:1]]
    for name in dict.fromkeys(selected_names):
        if name in grouped_combo:
            selected_series[str(name)[:90]] = grouped_combo[name]
    selected_issue_names = set(dict.fromkeys([BASE_PORTFOLIO, *selected_names]))
    selected_issue_rows = [
        row
        for row in base_rows_list + combo_rows
        if str(row.get("portfolio")) in selected_issue_names
    ]
    if args.write_full_combo_issue_profit:
        write_csv_all(out / "hedge_combo_issue_profit.csv", base_rows_list + combo_rows)
        issue_file = out / "hedge_combo_issue_profit.csv"
    else:
        write_csv_all(out / "hedge_combo_issue_profit_selected.csv", selected_issue_rows)
        issue_file = out / "hedge_combo_issue_profit_selected.csv"
    annual = annual_rows(selected_issue_rows if not args.write_full_combo_annual else base_rows_list + combo_rows)
    write_csv_all(out / "hedge_combo_annual.csv", annual)
    fig_path = out / "n7_384_hedge_sleeve_equity.svg"
    write_equity_svg(fig_path, selected_series, calendar)

    report = [
        "# N7 384 profile + small-N hedge sleeve",
        "",
        f"- Base portfolio: `{args.base_portfolio}` from `{args.base_issue_path}`.",
        f"- Hedge snapshot: `{args.snapshot}`; rolling train issues: `{args.train_issues}`.",
        f"- Profiles tested: `{len(profiles)}`; hedge units: `{args.hedge_units_values}`.",
        "- Hedge construction uses only prior issues for model fitting and the selected odds snapshot for current issue prices.",
        "",
        "## Base",
        md_table([base_summary]),
        "## Same-Budget Adaptive: Best MaxDD Improvement",
        md_table(same_dd),
        "## Same-Budget Adaptive: Best Non-Full-Loss Rate",
        md_table(same_nonfull),
        "## Additive: Best Profit Per 256",
        md_table(add_profit),
        "## Additive: Best MaxDD Improvement",
        md_table(add_dd),
        "",
        "## Files",
        "",
        f"- `{out / 'hedge_combo_summary.csv'}`",
        f"- `{issue_file}`",
        f"- `{out / 'hedge_combo_annual.csv'}`",
        f"- `{out / 'hedge_tickets.csv'}`",
        f"- `{fig_path}`",
        "",
    ]
    (out / "n7_384_hedge_sleeve_report.md").write_text("\n".join(report), encoding="utf-8")
    docs = Path("docs/research/n7_384_hedge_sleeve_2026-06-29.md")
    docs.parent.mkdir(parents=True, exist_ok=True)
    docs.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'n7_384_hedge_sleeve_report.md'}")
    print(f"Wrote {docs}")
    print(f"Wrote {fig_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--base-issue-path", type=Path, default=BASE_ISSUE_PATH)
    parser.add_argument("--base-portfolio", default=BASE_PORTFOLIO)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_384_hedge_sleeve_20260629"))
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="1h")
    parser.add_argument("--model-source", choices=("multiclass", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--n-values", default="2,3")
    parser.add_argument("--min-odds-values", default="5,8,12")
    parser.add_argument("--max-odds", type=float, default=80.0)
    parser.add_argument("--min-model-p-values", default="0.05,0.08,0.12")
    parser.add_argument("--max-model-p-values", default="0.25")
    parser.add_argument("--min-ratio-values", default="0.70,1.00,1.20")
    parser.add_argument("--rank-min-values", default="2,3")
    parser.add_argument("--score-bands", default="deep:0.70:1.00,near:0.90:1.063,value:1.063:0")
    parser.add_argument("--tickets-per-issue-values", default="1,2")
    parser.add_argument("--hedge-units-values", default="8,16,32,64")
    parser.add_argument("--odds-weight", type=float, default=0.75)
    parser.add_argument("--model-p-weight", type=float, default=0.80)
    parser.add_argument("--ratio-weight", type=float, default=0.35)
    parser.add_argument("--score-weight", type=float, default=0.35)
    parser.add_argument("--reuse-match-penalty", type=float, default=0.65)
    parser.add_argument("--reuse-pair-penalty", type=float, default=1.25)
    parser.add_argument("--max-match-uses", type=int, default=1)
    parser.add_argument("--max-pair-uses", type=int, default=1)
    parser.add_argument("--report-rows", type=int, default=12)
    parser.add_argument("--min-report-profit-per-256", type=float, default=0.0)
    parser.add_argument("--write-full-combo-issue-profit", action="store_true")
    parser.add_argument("--write-full-combo-annual", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    if not args.base_issue_path.exists():
        raise SystemExit(f"base issue path not found: {args.base_issue_path}")
    _ = break_even_factor(2)
    run(args)


if __name__ == "__main__":
    main()
