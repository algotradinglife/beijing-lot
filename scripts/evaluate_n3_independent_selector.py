#!/usr/bin/env python3
"""Evaluate independent N=3 selectors from EV-framework match decisions.

This is intentionally not a protection overlay on the N=7 book. It rebuilds
3-leg tickets directly from per-match single-outcome candidates, then compares
the issue-level curve with the current N=7 reference curve.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_fixed_loss_streaks import issue_sort_key, issue_year
from scripts.evaluate_issue_cooldown import max_underwater
from scripts.evaluate_n7_dynamic_sleeve_allocator import row_order, row_year
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_same_ticket_leg_coverage import max_dead_streak, max_drawdown_units
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    Leg,
    Ticket,
    default_db_path,
    load_action_rows,
    md_table,
    settle_ticket,
    write_csv,
)


SOURCE_STRATEGY = "ev_m0p95_p0p85_full_opt"
BASE_POLICY = "reference::draw_tail_to_n3::w5::dd2::ls4"
BASE_MODEL = "core512_none0"


@dataclass(frozen=True)
class SelectorSpec:
    name: str
    rank_mode: str
    ticket_cap: int
    overlap_penalty: float
    min_p: float = 0.0
    min_odds: float = 0.0
    max_odds: float = 999.0
    min_score: float = 0.0
    min_ev: float = -999.0


def fnum(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_csv(path: Path) -> list[dict[str, str]]:
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


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")


def build_specs(ticket_caps: list[int], overlap_penalties: list[float]) -> list[SelectorSpec]:
    templates = [
        ("prob_mild", "p", 0.38, 1.2, 5.0, 0.0, -999.0),
        ("prob_strict_mild", "p", 0.42, 1.2, 5.0, 0.0, -999.0),
        ("confidence_value", "p2_odds", 0.35, 1.2, 8.0, 0.0, -999.0),
        ("standalone_ev_pos", "standalone_ev", 0.25, 1.2, 15.0, 0.0, 0.0),
        ("mild_ev", "score", 0.35, 1.2, 6.0, 1.10, -999.0),
    ]
    specs: list[SelectorSpec] = []
    for cap in ticket_caps:
        for penalty in overlap_penalties:
            for label, mode, min_p, min_odds, max_odds, min_score, min_ev in templates:
                specs.append(
                    SelectorSpec(
                        name=slug(f"n3_{label}_t{cap}_op{penalty:g}"),
                        rank_mode=mode,
                        ticket_cap=cap,
                        overlap_penalty=penalty,
                        min_p=min_p,
                        min_odds=min_odds,
                        max_odds=max_odds,
                        min_score=min_score,
                        min_ev=min_ev,
                    )
                )
    return specs


def rank_score(spec: SelectorSpec, *, p_hat: float, odds: float, score: float, ev_standalone: float) -> float:
    if spec.rank_mode == "p":
        return p_hat
    if spec.rank_mode == "p_sqrt_odds":
        return p_hat * math.sqrt(max(odds, 1e-9))
    if spec.rank_mode == "p2_odds":
        return p_hat * p_hat * odds
    if spec.rank_mode == "standalone_ev":
        return 1.0 + ev_standalone
    if spec.rank_mode == "score":
        return score
    raise ValueError(f"unknown rank mode: {spec.rank_mode}")


def load_window_map(result_dir: Path) -> dict[str, tuple[str, str]]:
    path = result_dir / "ev_framework_windows.csv"
    out = {}
    if not path.exists():
        return out
    for row in read_csv(path):
        out[str(row["test_issue"])] = (str(row["train_start_issue"]), str(row["train_end_issue"]))
    return out


def load_action_lookup(db_path: Path, min_year: int) -> dict[tuple[str, int, str], ActionRow]:
    rows = load_action_rows(db_path, min_year)
    return {(row.issue, row.match_id, row.action_code): row for row in rows}


def load_issue_metadata(path: Path, *, policy: str, model: str) -> dict[str, dict[str, object]]:
    out = {}
    if not path.exists():
        return out
    for row in read_csv(path):
        if row.get("policy") != policy or row.get("model") != model:
            continue
        issue = str(row["issue"])
        out[issue] = {
            "issue_start_ts": row.get("issue_start_ts", ""),
            "issue_close_ts": row.get("issue_close_ts", ""),
            "issue_order": int(fnum(row.get("issue_order"), 0)),
            "calendar_year": int(fnum(row.get("calendar_year"), issue_year(issue))),
            "season_year": int(fnum(row.get("season_year"), issue_year(issue))),
        }
    return out


def enrich_issue_metadata(rows: list[dict[str, object]], metadata: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    enriched = []
    for row in rows:
        issue = str(row["issue"])
        copied = dict(row)
        copied.update(
            metadata.get(
                issue,
                {
                    "issue_start_ts": "",
                    "issue_close_ts": "",
                    "issue_order": issue_sort_key(issue)[1],
                    "calendar_year": issue_year(issue),
                    "season_year": issue_year(issue),
                },
            )
        )
        enriched.append(copied)
    return enriched


def load_n7_base(path: Path, *, policy: str, model: str) -> list[dict[str, object]]:
    rows = []
    for row in read_csv(path):
        if row.get("policy") != policy or row.get("model") != model:
            continue
        rows.append(dict(row))
    rows.sort(key=row_order)
    return rows


def full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"))
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return float("nan")
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = sum((x - mx) ** 2 for x in xs)
    den_y = sum((y - my) ** 2 for y in ys)
    den = math.sqrt(den_x * den_y)
    return num / den if den > 0 else float("nan")


def summarize_issue_rows(
    rows: list[dict[str, object]],
    *,
    issue_budget_units: float,
    recent_min_year: int,
    recent_max_year: int,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)

    out = []
    for strategy, vals in sorted(grouped.items()):
        vals = sorted(vals, key=row_order)
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        best = max((fnum(row.get("profit_units")) for row in vals), default=0.0)
        recent = [row for row in vals if recent_min_year <= row_year(row) <= recent_max_year]
        recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
        recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
        recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
        summary = {
            "strategy": strategy,
            "n_issues": len(vals),
            "stake_units": stake,
            "profit_units": profit,
            "profit_per_issue": profit / len(vals) if vals else math.nan,
            "roi_on_deployed_stake": profit / stake if stake else math.nan,
            "roi_on_fixed_issue_budget": profit / (len(vals) * issue_budget_units) if vals else math.nan,
            "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
            if vals
            else math.nan,
            "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals) if vals else math.nan,
            "small_loss_rate": sum(
                1 for row in vals if -fnum(row.get("stake_units")) < fnum(row.get("profit_units")) <= 0
            )
            / len(vals)
            if vals
            else math.nan,
            "max_drawdown_units": max_drawdown_units(vals),
            "max_dead_streak": max_dead_streak(vals),
            "best_issue_profit_units": best,
            "best_issue_profit_share": best / profit if profit > 0 else math.nan,
            "roi_ex_best_on_fixed_budget": (profit - best) / (len(vals) * issue_budget_units) if vals else math.nan,
            "recent_profit_units": recent_profit,
            "recent_roi_on_deployed_stake": recent_profit / recent_stake if recent_stake else math.nan,
            "recent_roi_ex_best_on_fixed_budget": (recent_profit - recent_best) / (len(recent) * issue_budget_units)
            if recent
            else math.nan,
            "avg_tickets_per_issue": sum(fnum(row.get("tickets")) for row in vals) / len(vals) if vals else math.nan,
            "avg_hits_per_issue": sum(fnum(row.get("hits")) for row in vals) / len(vals) if vals else math.nan,
        }
        summary.update(max_underwater(vals))
        out.append(summary)
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["strategy"]), row_year(row))].append(row)
    out = []
    for (strategy, year), vals in sorted(grouped.items()):
        vals = sorted(vals, key=row_order)
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "strategy": strategy,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi_on_deployed_stake": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
                if vals
                else math.nan,
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def selector_meta_rows(specs: list[SelectorSpec]) -> list[dict[str, object]]:
    return [
        {
            "strategy_base": spec.name,
            "rank_mode": spec.rank_mode,
            "ticket_cap": spec.ticket_cap,
            "overlap_penalty": spec.overlap_penalty,
            "min_p": spec.min_p,
            "min_odds": spec.min_odds,
            "max_odds": spec.max_odds,
            "min_score": spec.min_score,
            "min_ev": spec.min_ev,
        }
        for spec in specs
    ]


def decision_passes(spec: SelectorSpec, row: dict[str, str]) -> tuple[bool, dict[str, float]]:
    p_hat = fnum(row.get("best_single_p_hat"))
    odds = fnum(row.get("best_single_odds"))
    score = fnum(row.get("best_single_score"))
    ev_standalone = fnum(row.get("best_single_ev_standalone"))
    ok = (
        p_hat >= spec.min_p
        and spec.min_odds <= odds <= spec.max_odds
        and score >= spec.min_score
        and ev_standalone >= spec.min_ev
    )
    return ok, {"p_hat": p_hat, "odds": odds, "score": score, "ev_standalone": ev_standalone}


def build_leg_pool(
    *,
    decisions: list[dict[str, str]],
    source_strategy: str,
    specs: list[SelectorSpec],
    action_lookup: dict[tuple[str, int, str], ActionRow],
) -> dict[str, dict[str, list[Leg]]]:
    pools: dict[str, dict[str, list[Leg]]] = {spec.name: defaultdict(list) for spec in specs}
    by_name = {spec.name: spec for spec in specs}
    for row in decisions:
        if row.get("strategy") != source_strategy:
            continue
        issue = str(row["issue"])
        match_id = int(float(row["match_id"]))
        action_code = str(row["best_single_code"])
        action_row = action_lookup.get((issue, match_id, action_code))
        if action_row is None:
            continue
        for spec_name, spec in by_name.items():
            ok, vals = decision_passes(spec, row)
            if not ok:
                continue
            ranked = rank_score(spec, **vals)
            if ranked <= 0 or not math.isfinite(ranked):
                continue
            pools[spec_name][issue].append(
                Leg(
                    row=action_row,
                    strategy=spec.name,
                    score_factor=ranked,
                    p_hat=vals["p_hat"],
                    source_rule=(
                        f"n3_independent;source_strategy={source_strategy};"
                        f"rank_mode={spec.rank_mode};odds={vals['odds']:.6g};"
                        f"score={vals['score']:.6g};ev={vals['ev_standalone']:.6g}"
                    ),
                )
            )
    return {strategy: dict(by_issue) for strategy, by_issue in pools.items()}


def ticket_rows_for_specs(
    *,
    pools: dict[str, dict[str, list[Leg]]],
    specs: list[SelectorSpec],
    window_map: dict[str, tuple[str, str]],
) -> list[dict[str, object]]:
    out = []
    by_name = {spec.name: spec for spec in specs}
    for strategy, by_issue in sorted(pools.items()):
        spec = by_name[strategy]
        for issue, legs in sorted(by_issue.items(), key=lambda item: issue_sort_key(item[0])):
            if len({leg.row.match_id for leg in legs}) < 3:
                continue
            train_start, train_end = window_map.get(issue, ("", ""))
            tickets = make_n3_tickets_fast(
                legs,
                strategy=strategy,
                issue=issue,
                max_tickets=spec.ticket_cap,
                overlap_penalty=spec.overlap_penalty,
                train_start_issue=train_start,
                train_end_issue=train_end,
            )
            for ticket in tickets:
                settled = settle_ticket(ticket)
                settled.update(
                    {
                        "rank_mode": spec.rank_mode,
                        "ticket_cap": spec.ticket_cap,
                        "overlap_penalty": spec.overlap_penalty,
                        "min_p": spec.min_p,
                        "min_odds": spec.min_odds,
                        "max_odds": spec.max_odds,
                        "min_score": spec.min_score,
                        "min_ev": spec.min_ev,
                    }
                )
                out.append(settled)
    return out


def dedup_best_leg_per_match(legs: list[Leg]) -> list[Leg]:
    best: dict[int, Leg] = {}
    for leg in legs:
        current = best.get(leg.row.match_id)
        if current is None or (leg.score_factor, leg.p_hat) > (current.score_factor, current.p_hat):
            best[leg.row.match_id] = leg
    return sorted(
        best.values(),
        key=lambda leg: (
            math.log(max(leg.score_factor, 1e-9)),
            leg.p_hat,
            -leg.row.match_idx,
        ),
        reverse=True,
    )


def make_n3_tickets_fast(
    legs: list[Leg],
    *,
    strategy: str,
    issue: str,
    max_tickets: int,
    overlap_penalty: float,
    train_start_issue: str,
    train_end_issue: str,
) -> list[Ticket]:
    pool = dedup_best_leg_per_match(legs)
    if len(pool) < 3:
        return []

    scores = [math.log(max(leg.score_factor, 1e-9)) + 0.01 * leg.p_hat for leg in pool]

    def combo_score(idxs: tuple[int, int, int]) -> float:
        return sum(scores[i] for i in idxs)

    import heapq

    start = (0, 1, 2)
    heap: list[tuple[float, tuple[int, int, int]]] = [(-combo_score(start), start)]
    seen_idx = {start}
    candidate_limit = max(max_tickets * 6, max_tickets + 80)
    candidates: list[tuple[float, tuple[int, int, int]]] = []
    while heap and len(candidates) < candidate_limit:
        neg_score, idxs = heapq.heappop(heap)
        candidates.append((-neg_score, idxs))
        for pos in range(3):
            nxt = list(idxs)
            nxt[pos] += 1
            if max(nxt) >= len(pool) or len(set(nxt)) < 3:
                continue
            nxt_tuple = tuple(sorted(nxt))
            if nxt_tuple in seen_idx:
                continue
            seen_idx.add(nxt_tuple)
            heapq.heappush(heap, (-combo_score(nxt_tuple), nxt_tuple))

    target_use = max_tickets * 3 / max(len(pool), 1)
    max_use = max(2, math.ceil(target_use * max(1.05, 1.8 - overlap_penalty)) + 1)
    used: Counter[str] = Counter()
    selected: list[tuple[int, int, int]] = []
    seen_combo_keys: set[tuple[str, ...]] = set()

    def try_add(idxs: tuple[int, int, int], *, enforce_use_limit: bool) -> bool:
        combo = tuple(pool[i] for i in idxs)
        key = tuple(sorted(leg.leg_id for leg in combo))
        if key in seen_combo_keys:
            return False
        if enforce_use_limit and any(used[leg.leg_id] >= max_use for leg in combo):
            return False
        seen_combo_keys.add(key)
        selected.append(idxs)
        for leg in combo:
            used[leg.leg_id] += 1
        return True

    for _, idxs in candidates:
        try_add(idxs, enforce_use_limit=True)
        if len(selected) >= max_tickets:
            break
    if len(selected) < max_tickets:
        for _, idxs in candidates:
            try_add(idxs, enforce_use_limit=False)
            if len(selected) >= max_tickets:
                break

    return [
        Ticket(
            strategy=strategy,
            issue=issue,
            n_legs=3,
            ticket_idx=i + 1,
            train_start_issue=train_start_issue,
            train_end_issue=train_end_issue,
            legs=tuple(pool[idx] for idx in idxs),
        )
        for i, idxs in enumerate(selected)
    ]


def compare_with_n7(n3_rows: list[dict[str, object]], n7_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    n7_by_issue = {str(row["issue"]): row for row in n7_rows}
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in n3_rows:
        if str(row["issue"]) in n7_by_issue:
            grouped[str(row["strategy"])].append(row)

    out = []
    for strategy, rows in sorted(grouped.items()):
        xs = []
        ys = []
        both_negative = 0
        n7_negative = 0
        n3_positive_when_n7_negative = 0
        n3_profit_when_n7_negative = 0.0
        n7_full_loss = 0
        n3_positive_when_n7_full_loss = 0
        same_sign = 0
        for row in rows:
            n7 = n7_by_issue[str(row["issue"])]
            n3_profit = fnum(row.get("profit_units"))
            n3_stake = fnum(row.get("stake_units"))
            n7_profit = fnum(n7.get("profit_units"))
            n7_stake = fnum(n7.get("stake_units"))
            n3_roi = n3_profit / n3_stake if n3_stake else 0.0
            n7_roi = n7_profit / n7_stake if n7_stake else 0.0
            xs.append(n3_roi)
            ys.append(n7_roi)
            if (n3_profit > 0) == (n7_profit > 0):
                same_sign += 1
            if n7_profit < 0:
                n7_negative += 1
                n3_profit_when_n7_negative += n3_profit
                if n3_profit > 0:
                    n3_positive_when_n7_negative += 1
                if n3_profit < 0:
                    both_negative += 1
            if full_loss(n7):
                n7_full_loss += 1
                if n3_profit > 0:
                    n3_positive_when_n7_full_loss += 1
        out.append(
            {
                "strategy": strategy,
                "overlap_issues": len(rows),
                "issue_roi_corr_vs_n7": pearson(xs, ys),
                "same_sign_rate_vs_n7": same_sign / len(rows) if rows else math.nan,
                "n7_negative_issues": n7_negative,
                "both_negative_rate_when_n7_negative": both_negative / n7_negative if n7_negative else math.nan,
                "n3_positive_rate_when_n7_negative": n3_positive_when_n7_negative / n7_negative
                if n7_negative
                else math.nan,
                "n3_profit_when_n7_negative": n3_profit_when_n7_negative,
                "n7_full_loss_issues": n7_full_loss,
                "n3_positive_rate_when_n7_full_loss": n3_positive_when_n7_full_loss / n7_full_loss
                if n7_full_loss
                else math.nan,
            }
        )
    return out


def cumulative_rows(
    *,
    issue_rows: list[dict[str, object]],
    n7_rows: list[dict[str, object]],
    strategies: list[str],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        if str(row["strategy"]) in strategies:
            grouped[str(row["strategy"])].append(row)
    for row in n7_rows:
        grouped["N7_reference_core512"].append(dict(row))

    out = []
    for strategy, rows in sorted(grouped.items()):
        rows = sorted(rows, key=row_order)
        cum_profit = 0.0
        cum_roi_budget = 0.0
        for idx, row in enumerate(rows, start=1):
            profit = fnum(row.get("profit_units"))
            stake = fnum(row.get("stake_units"))
            cum_profit += profit
            cum_roi_budget += profit / stake if stake else 0.0
            out.append(
                {
                    "strategy": strategy,
                    "issue": row.get("issue", ""),
                    "issue_close_ts": row.get("issue_close_ts", ""),
                    "issue_order": row.get("issue_order", ""),
                    "calendar_year": row_year(row),
                    "cum_profit_units": cum_profit,
                    "cum_issue_roi_units": cum_roi_budget,
                    "n_points": idx,
                }
            )
    return out


def plot_equity(curve_rows: list[dict[str, object]], output_path: Path) -> None:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in curve_rows:
        grouped[str(row["strategy"])].append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    width = 1200
    height = 650
    left = 80
    right = 270
    top = 48
    bottom = 70
    plot_w = width - left - right
    plot_h = height - top - bottom
    colors = [
        "#1f77b4",
        "#d62728",
        "#2ca02c",
        "#9467bd",
        "#ff7f0e",
        "#17becf",
        "#8c564b",
        "#7f7f7f",
    ]
    all_vals = [
        fnum(row.get("cum_issue_roi_units"))
        for rows in grouped.values()
        for row in rows
        if math.isfinite(fnum(row.get("cum_issue_roi_units"), float("nan")))
    ]
    if not all_vals:
        output_path.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>\n", encoding="utf-8")
        return
    y_min = min(min(all_vals), 0.0)
    y_max = max(max(all_vals), 0.0)
    if y_max <= y_min:
        y_max = y_min + 1.0
    y_pad = (y_max - y_min) * 0.08
    y_min -= y_pad
    y_max += y_pad
    max_n = max((len(rows) for rows in grouped.values()), default=1)

    def sx(idx: int) -> float:
        return left + (idx / max(max_n - 1, 1)) * plot_w

    def sy(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    def esc(value: object) -> str:
        text = str(value)
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    zero_y = sy(0.0)
    parts = [
        f"<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\">",
        "<rect width=\"100%\" height=\"100%\" fill=\"#ffffff\"/>",
        f"<text x=\"{left}\" y=\"28\" font-family=\"Arial\" font-size=\"18\" font-weight=\"700\">Independent N3 selectors vs N7 reference</text>",
        f"<line x1=\"{left}\" y1=\"{top}\" x2=\"{left}\" y2=\"{height-bottom}\" stroke=\"#333\" stroke-width=\"1\"/>",
        f"<line x1=\"{left}\" y1=\"{height-bottom}\" x2=\"{width-right}\" y2=\"{height-bottom}\" stroke=\"#333\" stroke-width=\"1\"/>",
        f"<line x1=\"{left}\" y1=\"{zero_y:.2f}\" x2=\"{width-right}\" y2=\"{zero_y:.2f}\" stroke=\"#777\" stroke-width=\"1\" stroke-dasharray=\"4 3\"/>",
    ]
    for i in range(6):
        val = y_min + (y_max - y_min) * i / 5
        y = sy(val)
        parts.append(f"<line x1=\"{left}\" y1=\"{y:.2f}\" x2=\"{width-right}\" y2=\"{y:.2f}\" stroke=\"#e6e6e6\" stroke-width=\"1\"/>")
        parts.append(
            f"<text x=\"{left-10}\" y=\"{y+4:.2f}\" text-anchor=\"end\" font-family=\"Arial\" font-size=\"11\" fill=\"#555\">{val:.1f}</text>"
        )
    for idx, (strategy, rows) in enumerate(sorted(grouped.items())):
        rows = sorted(rows, key=lambda row: (row.get("issue_close_ts", ""), str(row.get("issue", ""))))
        color = colors[idx % len(colors)]
        points = []
        for i, row in enumerate(rows):
            value = fnum(row.get("cum_issue_roi_units"))
            points.append(f"{sx(i):.2f},{sy(value):.2f}")
        parts.append(
            f"<polyline points=\"{' '.join(points)}\" fill=\"none\" stroke=\"{color}\" stroke-width=\"1.8\"/>"
        )
        legend_y = top + 20 + idx * 22
        parts.append(f"<line x1=\"{width-right+28}\" y1=\"{legend_y}\" x2=\"{width-right+58}\" y2=\"{legend_y}\" stroke=\"{color}\" stroke-width=\"2\"/>")
        parts.append(
            f"<text x=\"{width-right+64}\" y=\"{legend_y+4}\" font-family=\"Arial\" font-size=\"11\" fill=\"#222\">{esc(strategy)}</text>"
        )
    parts.extend(
        [
            f"<text x=\"{left + plot_w / 2:.1f}\" y=\"{height-24}\" text-anchor=\"middle\" font-family=\"Arial\" font-size=\"12\" fill=\"#333\">Settled issue order</text>",
            f"<text transform=\"translate(24 {top + plot_h / 2:.1f}) rotate(-90)\" text-anchor=\"middle\" font-family=\"Arial\" font-size=\"12\" fill=\"#333\">Cumulative issue ROI units</text>",
            "</svg>",
        ]
    )
    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def compact_summary(rows: list[dict[str, object]], limit: int = 20) -> list[dict[str, object]]:
    keep = [
        "strategy",
        "n_issues",
        "profit_units",
        "roi_on_deployed_stake",
        "issue_win_rate",
        "non_full_loss_rate",
        "max_drawdown_units",
        "max_dead_streak",
        "roi_ex_best_on_fixed_budget",
        "recent_profit_units",
        "recent_roi_on_deployed_stake",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows[:limit]]


def run(args: argparse.Namespace) -> None:
    specs = build_specs(args.ticket_caps, args.overlap_penalties)
    decisions = read_csv(args.result_dir / "ev_framework_decisions.csv")
    action_lookup = load_action_lookup(args.db_path, args.min_year)
    window_map = load_window_map(args.result_dir)
    metadata = load_issue_metadata(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    n7_rows = load_n7_base(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)

    pools = build_leg_pool(
        decisions=decisions,
        source_strategy=args.source_strategy,
        specs=specs,
        action_lookup=action_lookup,
    )
    raw_tickets = ticket_rows_for_specs(pools=pools, specs=specs, window_map=window_map)
    budgeted = budgeted_ticket_rows(
        raw_tickets,
        issue_budget_units=args.issue_budget_units,
        fractional=True,
    )
    issue_rows = enrich_issue_metadata(issue_profit_rows(budgeted), metadata)
    summaries = summarize_issue_rows(
        issue_rows,
        issue_budget_units=args.issue_budget_units,
        recent_min_year=args.recent_min_year,
        recent_max_year=args.recent_max_year,
    )
    summaries.sort(
        key=lambda row: (
            fnum(row.get("roi_on_deployed_stake")),
            fnum(row.get("profit_units")),
            fnum(row.get("issue_win_rate")),
        ),
        reverse=True,
    )
    annual = annual_rows(issue_rows)
    comparison = compare_with_n7(issue_rows, n7_rows)
    comparison_by_strategy = {row["strategy"]: row for row in comparison}
    for row in summaries:
        row.update(
            {
                f"n7_{key}": value
                for key, value in comparison_by_strategy.get(str(row["strategy"]), {}).items()
                if key != "strategy"
            }
        )

    best_plot_strategies = []
    for row in summaries:
        strategy = str(row["strategy"])
        if strategy not in best_plot_strategies:
            best_plot_strategies.append(strategy)
        if len(best_plot_strategies) >= args.plot_top_n:
            break
    curve = cumulative_rows(issue_rows=issue_rows, n7_rows=n7_rows, strategies=best_plot_strategies)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "n3_independent_selector_specs.csv", selector_meta_rows(specs))
    write_csv_all(args.output_dir / "n3_independent_raw_tickets.csv", raw_tickets)
    write_csv_all(args.output_dir / "n3_independent_budget_tickets.csv", budgeted)
    write_csv_all(args.output_dir / "n3_independent_issue_profit.csv", issue_rows)
    write_csv_all(args.output_dir / "n3_independent_summary.csv", summaries)
    write_csv_all(args.output_dir / "n3_independent_annual.csv", annual)
    write_csv_all(args.output_dir / "n3_independent_vs_n7.csv", comparison)
    write_csv_all(args.output_dir / "n3_independent_equity_curve.csv", curve)
    plot_equity(curve, args.figure_path)

    report = [
        "# Independent N3 selector evaluation",
        "",
        f"- Source decision file: `{args.result_dir / 'ev_framework_decisions.csv'}`",
        f"- Source strategy: `{args.source_strategy}`",
        f"- N3 issue budget: `{args.issue_budget_units:g}` units, fractional fill.",
        f"- N7 reference: `{args.n7_base_model}` / `{args.n7_base_policy}`.",
        "- Settlement is rebuilt from SQLite action candidates by `(issue, match_id, action_code)`.",
        "",
        "## Top N3 Selectors By ROI",
        "",
        md_table(compact_summary(summaries, limit=30)),
        "",
        "## N3 vs N7 Shape Comparison",
        "",
        md_table(
            [
                {
                    key: row.get(key, "")
                    for key in [
                        "strategy",
                        "overlap_issues",
                        "issue_roi_corr_vs_n7",
                        "same_sign_rate_vs_n7",
                        "n3_positive_rate_when_n7_negative",
                        "n3_profit_when_n7_negative",
                        "n3_positive_rate_when_n7_full_loss",
                    ]
                }
                for row in sorted(
                    comparison,
                    key=lambda row: fnum(row.get("n3_positive_rate_when_n7_negative")),
                    reverse=True,
                )[:30]
            ]
        ),
        "",
        f"Equity curve SVG: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def parse_floats(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/n7_ev_framework_selector_2014_1h_minodds4_optional"),
    )
    parser.add_argument("--source-strategy", default=SOURCE_STRATEGY)
    parser.add_argument("--db-path", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--ticket-caps", type=parse_ints, default=parse_ints("80,180"))
    parser.add_argument("--overlap-penalties", type=parse_floats, default=parse_floats("0.5"))
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument(
        "--n7-base-issue-profit",
        type=Path,
        default=Path("results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--n7-base-policy", default=BASE_POLICY)
    parser.add_argument("--n7-base-model", default=BASE_MODEL)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--plot-top-n", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_independent_selector_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n3_independent_selector_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n3_independent_selector_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
