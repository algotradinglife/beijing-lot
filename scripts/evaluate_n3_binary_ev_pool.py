#!/usr/bin/env python3
"""Evaluate binary high/low EV pools for N=3/4/5 tickets.

This experiment intentionally collapses the previous L/M/H tiering into a
binary decision: high EV outcomes are the main investable pool, low EV outcomes
are used only as limited protection.  It reuses the calibrated outcome table
from the outcome-level EV-depth run, so no future settlement information enters
the selector.  The N sweep tests whether adding more distinct high-EV matches
uses capital better than buying deeper coverage on the same three matches.
"""
from __future__ import annotations

import argparse
import csv
import heapq
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_fixed_loss_streaks import issue_sort_key, issue_year
from scripts.evaluate_n3_independent_selector import (
    BASE_MODEL,
    BASE_POLICY,
    annual_rows,
    compare_with_n7,
    cumulative_rows,
    fnum,
    load_issue_metadata,
    load_n7_base,
    plot_equity,
    summarize_issue_rows,
    write_csv_all,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.walkforward_beidan_strategy_eval import RETURN_RATE, md_table


SOURCE_STRATEGY = "n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev"


@dataclass(frozen=True)
class Option:
    issue: str
    match_id: int
    match_idx: int
    league: str
    hcp: float
    outcome: str
    q_cal: float
    p_cal: float
    estimated_sp: float
    hit: int
    winning_sp: float
    old_tier: str

    @property
    def leg_key(self) -> str:
        return f"{self.match_id}:{self.outcome}@{self.hcp:g}"


@dataclass(frozen=True)
class Arm:
    name: str
    n_legs: int
    high_mode: str
    ticket_cap: int
    high_only_share: float
    one_low_share: float
    two_low_share: float = 0.0
    abs_q_cut: float = 2.0
    local_high_share: float = 0.60


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_options(path: Path, source_strategy: str) -> dict[str, list[Option]]:
    by_issue: dict[str, list[Option]] = defaultdict(list)
    for row in read_csv(path):
        if row.get("strategy") != source_strategy:
            continue
        opt = Option(
            issue=str(row["issue"]),
            match_id=int(fnum(row.get("match_id"))),
            match_idx=int(fnum(row.get("match_idx"))),
            league=str(row.get("league", "")),
            hcp=fnum(row.get("hcp")),
            outcome=str(row.get("outcome", "")),
            q_cal=fnum(row.get("q_cal")),
            p_cal=fnum(row.get("p_cal")),
            estimated_sp=fnum(row.get("estimated_sp")),
            hit=int(fnum(row.get("hit"))),
            winning_sp=fnum(row.get("winning_sp")),
            old_tier=str(row.get("tier", "")),
        )
        if opt.q_cal > 0 and opt.p_cal > 0 and opt.estimated_sp > 0:
            by_issue[opt.issue].append(opt)
    return {
        issue: sorted(vals, key=lambda opt: (opt.q_cal, opt.p_cal, opt.estimated_sp), reverse=True)
        for issue, vals in by_issue.items()
    }


def default_arms() -> list[Arm]:
    return [
        Arm("binary_n3_absq20_t180_high100", 3, "absolute", 180, 1.00, 0.00, abs_q_cut=2.0),
        Arm("binary_n3_absq20_t180_high80_low1_20", 3, "absolute", 180, 0.80, 0.20, abs_q_cut=2.0),
        Arm("binary_n3_absq20_t240_high80_low1_20", 3, "absolute", 240, 0.80, 0.20, abs_q_cut=2.0),
        Arm("binary_n3_absq20_t360_high80_low1_20", 3, "absolute", 360, 0.80, 0.20, abs_q_cut=2.0),
        Arm("binary_n3_local60_t180_high100", 3, "local", 180, 1.00, 0.00, local_high_share=0.60),
        Arm("binary_n3_local60_t180_high80_low1_20", 3, "local", 180, 0.80, 0.20, local_high_share=0.60),
        Arm("binary_n3_local60_t240_high80_low1_20", 3, "local", 240, 0.80, 0.20, local_high_share=0.60),
        Arm("binary_n3_local60_t360_high80_low1_20", 3, "local", 360, 0.80, 0.20, local_high_share=0.60),
        Arm("binary_n3_local60_t180_high70_low1_25_low2_5", 3, "local", 180, 0.70, 0.25, 0.05, local_high_share=0.60),
        Arm("binary_n4_absq20_t120_high100", 4, "absolute", 120, 1.00, 0.00, abs_q_cut=2.0),
        Arm("binary_n4_absq20_t180_high100", 4, "absolute", 180, 1.00, 0.00, abs_q_cut=2.0),
        Arm("binary_n4_local60_t120_high100", 4, "local", 120, 1.00, 0.00, local_high_share=0.60),
        Arm("binary_n4_local60_t180_high100", 4, "local", 180, 1.00, 0.00, local_high_share=0.60),
        Arm("binary_n4_local60_t240_high100", 4, "local", 240, 1.00, 0.00, local_high_share=0.60),
        Arm("binary_n4_local60_t180_high85_low1_15", 4, "local", 180, 0.85, 0.15, local_high_share=0.60),
        Arm("binary_n5_absq20_t80_high100", 5, "absolute", 80, 1.00, 0.00, abs_q_cut=2.0),
        Arm("binary_n5_absq20_t120_high100", 5, "absolute", 120, 1.00, 0.00, abs_q_cut=2.0),
        Arm("binary_n5_local60_t80_high100", 5, "local", 80, 1.00, 0.00, local_high_share=0.60),
        Arm("binary_n5_local60_t120_high100", 5, "local", 120, 1.00, 0.00, local_high_share=0.60),
        Arm("binary_n5_local60_t180_high100", 5, "local", 180, 1.00, 0.00, local_high_share=0.60),
        Arm("binary_n5_local60_t120_high90_low1_10", 5, "local", 120, 0.90, 0.10, local_high_share=0.60),
    ]


def split_high_low(options: list[Option], arm: Arm) -> tuple[list[Option], list[Option], float]:
    if arm.high_mode == "absolute":
        cut = arm.abs_q_cut
        high = [opt for opt in options if opt.q_cal >= cut]
        low = [opt for opt in options if opt.q_cal < cut]
        return high, low, cut
    if arm.high_mode == "local":
        if not options:
            return [], [], math.nan
        high_count = min(len(options), max(arm.n_legs, int(math.ceil(len(options) * arm.local_high_share))))
        ranked = sorted(options, key=lambda opt: (opt.q_cal, opt.p_cal), reverse=True)
        high_set = {id(opt) for opt in ranked[:high_count]}
        cut = ranked[high_count - 1].q_cal
        high = [opt for opt in ranked if id(opt) in high_set]
        low = [opt for opt in ranked if id(opt) not in high_set]
        return high, low, cut
    raise ValueError(f"unknown high_mode: {arm.high_mode}")


def log_score(options: Iterable[Option]) -> float:
    return sum(math.log(max(opt.q_cal, 1e-12)) for opt in options)


def combo_key(options: Iterable[Option]) -> tuple[str, ...]:
    return tuple(sorted(opt.leg_key for opt in options))


def top_same_pool_combos(
    options: list[Option],
    *,
    n: int,
    limit: int,
    exclude: set[tuple[str, ...]] | None = None,
) -> list[tuple[Option, ...]]:
    if len(options) < n or limit <= 0:
        return []
    opts = sorted(options, key=lambda opt: (opt.q_cal, opt.p_cal), reverse=True)
    start = tuple(range(n))
    heap: list[tuple[float, tuple[int, ...]]] = [(-sum(math.log(max(opts[i].q_cal, 1e-12)) for i in start), start)]
    seen_idx = {start}
    seen_combo: set[tuple[str, ...]] = set()
    exclude = exclude or set()
    out: list[tuple[Option, ...]] = []
    popped = 0
    max_popped = max(limit * 220, 5000)
    while heap and len(out) < limit and popped < max_popped:
        neg_score, idxs = heapq.heappop(heap)
        popped += 1
        combo = tuple(opts[i] for i in idxs)
        if len({opt.match_id for opt in combo}) == n:
            key = combo_key(combo)
            if key not in exclude and key not in seen_combo:
                seen_combo.add(key)
                out.append(combo)
        for pos in range(n):
            nxt = list(idxs)
            nxt[pos] += 1
            if max(nxt) >= len(opts) or len(set(nxt)) < n:
                continue
            nxt_tuple = tuple(sorted(nxt))
            if nxt_tuple in seen_idx:
                continue
            seen_idx.add(nxt_tuple)
            heapq.heappush(
                heap,
                (-sum(math.log(max(opts[i].q_cal, 1e-12)) for i in nxt_tuple), nxt_tuple),
            )
    return out


def top_mixed_combos(
    primary: list[Option],
    secondary: list[Option],
    *,
    n_primary: int,
    n_secondary: int,
    limit: int,
    exclude: set[tuple[str, ...]] | None = None,
) -> list[tuple[Option, ...]]:
    if len(primary) < n_primary or len(secondary) < n_secondary or limit <= 0:
        return []
    exclude = exclude or set()
    group_limit = max(limit * 4, 120)
    single_limit = max(limit * 3, 80)

    def groups(pool: list[Option], group_n: int) -> list[tuple[Option, ...]]:
        if group_n == 0:
            return [()]
        if group_n == 1:
            return [
                (opt,)
                for opt in sorted(pool, key=lambda opt: (opt.q_cal, opt.p_cal), reverse=True)[:single_limit]
            ]
        return top_same_pool_combos(pool, n=group_n, limit=group_limit)

    primary_groups = groups(primary, n_primary)
    secondary_groups = groups(secondary, n_secondary)

    rows: list[tuple[float, tuple[Option, ...]]] = []
    seen: set[tuple[str, ...]] = set()
    for group_a in primary_groups:
        for group_b in secondary_groups:
            combo = tuple(group_a + group_b)
            if len(combo) != 3 or len({opt.match_id for opt in combo}) < 3:
                continue
            key = combo_key(combo)
            if key in exclude or key in seen:
                continue
            seen.add(key)
            rows.append((log_score(combo), combo))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [combo for _, combo in rows[:limit]]


def pattern_counts(arm: Arm) -> dict[str, int]:
    high_only = int(round(arm.ticket_cap * arm.high_only_share))
    one_low = int(round(arm.ticket_cap * arm.one_low_share))
    two_low = max(0, arm.ticket_cap - high_only - one_low)
    if arm.two_low_share > 0:
        two_low = int(round(arm.ticket_cap * arm.two_low_share))
        one_low = max(0, arm.ticket_cap - high_only - two_low)
    high_only_pattern = "H" * arm.n_legs
    one_low_pattern = "H" * max(0, arm.n_legs - 1) + "L"
    two_low_pattern = "H" * max(0, arm.n_legs - 2) + "LL"
    return {high_only_pattern: high_only, one_low_pattern: one_low, two_low_pattern: two_low}


def ticket_row(strategy: str, issue: str, idx: int, combo: tuple[Option, ...], pattern: str) -> dict[str, object]:
    q_product = math.prod(max(opt.q_cal, 1e-12) for opt in combo)
    pred_hit_prob = math.prod(max(min(opt.p_cal, 1.0), 0.0) for opt in combo)
    hit = int(all(opt.hit == 1 for opt in combo))
    sp_product = math.prod(max(opt.winning_sp, 0.0) for opt in combo) if hit else 0.0
    payout = RETURN_RATE * sp_product if hit else 0.0
    profit = payout - 1.0 if hit else -1.0
    return {
        "strategy": strategy,
        "issue": issue,
        "n_legs": len(combo),
        "ticket_idx": idx,
        "stake_units": 1.0,
        "hit": hit,
        "payout_units": payout,
        "profit_units": profit,
        "roi": profit,
        "pred_factor_product": q_product,
        "pred_ev_per_stake": RETURN_RATE * q_product - 1.0,
        "pred_hit_prob": pred_hit_prob,
        "legs": ";".join(opt.leg_key for opt in combo),
        "binary_pattern": pattern,
        "old_tier_pattern": "".join(sorted((opt.old_tier for opt in combo), reverse=True)),
        "avg_q_cal": sum(opt.q_cal for opt in combo) / 3.0,
        "min_q_cal": min(opt.q_cal for opt in combo),
        "avg_p_cal": sum(opt.p_cal for opt in combo) / 3.0,
        "estimated_sp_product": math.prod(max(opt.estimated_sp, 0.0) for opt in combo),
        "winning_sp_product": sp_product,
        "outcomes": "".join(opt.outcome for opt in combo),
        "hcps": ";".join(f"{opt.hcp:g}" for opt in combo),
    }


def build_issue_tickets(
    issue: str,
    options: list[Option],
    arm: Arm,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    high, low, cut = split_high_low(options, arm)
    high_matches = {opt.match_id for opt in high}
    low_matches = {opt.match_id for opt in low}
    counts = pattern_counts(arm)
    selected: list[tuple[str, tuple[Option, ...]]] = []
    seen: set[tuple[str, ...]] = set()

    high_only_pattern = "H" * arm.n_legs
    one_low_pattern = "H" * max(0, arm.n_legs - 1) + "L"
    two_low_pattern = "H" * max(0, arm.n_legs - 2) + "LL"

    high_only = top_same_pool_combos(high, n=arm.n_legs, limit=counts[high_only_pattern], exclude=seen)
    for combo in high_only:
        selected.append((high_only_pattern, combo))
        seen.add(combo_key(combo))

    if counts[one_low_pattern] > 0:
        one_low = top_mixed_combos(
            high,
            low,
            n_primary=arm.n_legs - 1,
            n_secondary=1,
            limit=counts[one_low_pattern],
            exclude=seen,
        )
        for combo in one_low:
            selected.append((one_low_pattern, combo))
            seen.add(combo_key(combo))

    if counts[two_low_pattern] > 0 and arm.n_legs >= 3:
        two_low = top_mixed_combos(
            high,
            low,
            n_primary=arm.n_legs - 2,
            n_secondary=2,
            limit=counts[two_low_pattern],
            exclude=seen,
        )
        for combo in two_low:
            selected.append((two_low_pattern, combo))
            seen.add(combo_key(combo))

    # If a protection sleeve cannot be filled because the low pool is too
    # small, backfill with additional high-only combinations.  This keeps the
    # binary premise intact and avoids adding low-quality tickets merely to
    # spend budget.
    if len(selected) < arm.ticket_cap:
        extra = top_same_pool_combos(high, n=arm.n_legs, limit=arm.ticket_cap - len(selected), exclude=seen)
        for combo in extra:
            selected.append((f"{high_only_pattern}_backfill", combo))
            seen.add(combo_key(combo))

    rows = [
        ticket_row(arm.name, issue, idx, combo, pattern)
        for idx, (pattern, combo) in enumerate(selected, start=1)
    ]
    stat = {
        "strategy": arm.name,
        "issue": issue,
        "n_legs": arm.n_legs,
        "high_cut": cut,
        "n_options": len(options),
        "n_high_options": len(high),
        "n_low_options": len(low),
        "n_high_matches": len(high_matches),
        "n_low_matches": len(low_matches),
        "tickets": len(rows),
        "raw_high_only": sum(1 for pattern, _ in selected if pattern.startswith(high_only_pattern)),
        "raw_one_low": sum(1 for pattern, _ in selected if pattern == one_low_pattern),
        "raw_two_low": sum(1 for pattern, _ in selected if pattern == two_low_pattern),
    }
    return rows, stat


def enrich_issue_rows(
    rows: list[dict[str, object]],
    metadata: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    enriched = []
    for row in rows:
        copied = dict(row)
        issue = str(row["issue"])
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


def mix_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)
    out = []
    for strategy, vals in sorted(grouped.items()):
        patterns = Counter(str(row.get("binary_pattern")) for row in vals)
        out.append(
            {
                "strategy": strategy,
                "n_legs": int(fnum(vals[0].get("n_legs"))) if vals else 0,
                "raw_tickets": len(vals),
                "raw_hit_rate": sum(int(fnum(row.get("hit"))) for row in vals) / len(vals) if vals else math.nan,
                "raw_roi": sum(fnum(row.get("profit_units")) for row in vals) / len(vals) if vals else math.nan,
                "avg_pred_ev_per_stake": sum(fnum(row.get("pred_ev_per_stake")) for row in vals) / len(vals) if vals else math.nan,
                "avg_pred_hit_prob": sum(fnum(row.get("pred_hit_prob")) for row in vals) / len(vals) if vals else math.nan,
                "avg_q_product": sum(fnum(row.get("pred_factor_product")) for row in vals) / len(vals) if vals else math.nan,
                "pattern_mix": ";".join(f"{key}:{value}" for key, value in patterns.most_common()),
            }
        )
    return out


def pool_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["strategy"])].append(row)
    out = []
    for strategy, vals in sorted(grouped.items()):
        active = [row for row in vals if fnum(row.get("tickets")) > 0]
        out.append(
            {
                "strategy": strategy,
                "n_legs": int(fnum(vals[0].get("n_legs"))) if vals else 0,
                "active_issues": len(active),
                "avg_high_options": sum(fnum(row.get("n_high_options")) for row in active) / len(active)
                if active
                else math.nan,
                "avg_low_options": sum(fnum(row.get("n_low_options")) for row in active) / len(active)
                if active
                else math.nan,
                "avg_high_matches": sum(fnum(row.get("n_high_matches")) for row in active) / len(active)
                if active
                else math.nan,
                "avg_high_cut": sum(fnum(row.get("high_cut")) for row in active) / len(active) if active else math.nan,
                "avg_raw_tickets": sum(fnum(row.get("tickets")) for row in active) / len(active) if active else math.nan,
            }
        )
    return out


def capture_summary(
    budget_rows: list[dict[str, object]],
    high_quality_path: Path,
) -> list[dict[str, object]]:
    if not high_quality_path.exists():
        return []
    hq_rows = read_csv(high_quality_path)

    def norm_legs(raw: object) -> str:
        return ";".join(sorted(part.strip() for part in str(raw).split(";") if part.strip()))

    hq_keys = {norm_legs(row.get("legs")) for row in hq_rows}
    hq_hits = {norm_legs(row.get("legs")): fnum(row.get("payout_units")) for row in hq_rows}
    grouped: dict[str, set[str]] = defaultdict(set)
    stake_by_strategy: dict[str, float] = defaultdict(float)
    for row in budget_rows:
        strategy = str(row["strategy"])
        key = norm_legs(row.get("legs", ""))
        stake_by_strategy[strategy] += fnum(row.get("stake_units"))
        if key in hq_keys:
            grouped[strategy].add(key)
    out = []
    for strategy in sorted(stake_by_strategy):
        keys = grouped.get(strategy, set())
        out.append(
            {
                "strategy": strategy,
                "captured_hq_missed_winners": len(keys),
                "captured_hq_share": len(keys) / len(hq_keys) if hq_keys else math.nan,
                "captured_hq_payout_sum": sum(hq_hits[key] for key in keys),
            }
        )
    return out


def compact_annual(rows: list[dict[str, object]], strategies: list[str]) -> list[dict[str, object]]:
    keep = set(strategies)
    out = []
    for row in rows:
        if str(row.get("strategy")) not in keep:
            continue
        out.append(
            {
                "strategy": row.get("strategy"),
                "year": row.get("year"),
                "n_issues": row.get("n_issues"),
                "profit_units": row.get("profit_units"),
                "roi_on_deployed_stake": row.get("roi_on_deployed_stake"),
                "issue_win_rate": row.get("issue_win_rate"),
                "non_full_loss_rate": row.get("non_full_loss_rate"),
                "max_drawdown_units": row.get("max_drawdown_units"),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    option_path = args.result_dir / "n3_outcome_ev_depth_option_depth.csv"
    by_issue = load_options(option_path, args.source_strategy)
    arms = default_arms()

    raw_rows: list[dict[str, object]] = []
    pool_rows: list[dict[str, object]] = []
    for arm in arms:
        for issue, options in sorted(by_issue.items(), key=lambda item: issue_sort_key(item[0])):
            rows, stat = build_issue_tickets(issue, options, arm)
            raw_rows.extend(rows)
            pool_rows.append(stat)

    budgeted = budgeted_ticket_rows(raw_rows, issue_budget_units=args.issue_budget_units, fractional=True)
    metadata = load_issue_metadata(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    issue_rows = enrich_issue_rows(issue_profit_rows(budgeted), metadata)
    summaries = summarize_issue_rows(
        issue_rows,
        issue_budget_units=args.issue_budget_units,
        recent_min_year=args.recent_min_year,
        recent_max_year=args.recent_max_year,
    )
    annual = annual_rows(issue_rows)
    mix = mix_summary(raw_rows)
    pools = pool_summary(pool_rows)
    captures = capture_summary(budgeted, args.high_quality_path)
    n7_rows = load_n7_base(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    comparison = compare_with_n7(issue_rows, n7_rows)

    mix_by_strategy = {row["strategy"]: row for row in mix}
    pool_by_strategy = {row["strategy"]: row for row in pools}
    capture_by_strategy = {row["strategy"]: row for row in captures}
    comparison_by_strategy = {row["strategy"]: row for row in comparison}
    for row in summaries:
        strategy = str(row["strategy"])
        base = strategy.split("__budget", 1)[0]
        row.update({f"mix_{key}": value for key, value in mix_by_strategy.get(base, {}).items() if key != "strategy"})
        row.update({f"pool_{key}": value for key, value in pool_by_strategy.get(base, {}).items() if key != "strategy"})
        row.update({f"hq_{key}": value for key, value in capture_by_strategy.get(strategy, {}).items() if key != "strategy"})
        row.update(
            {
                f"n7_{key}": value
                for key, value in comparison_by_strategy.get(strategy, {}).items()
                if key != "strategy"
            }
        )

    summaries.sort(
        key=lambda row: (
            fnum(row.get("roi_on_deployed_stake")),
            fnum(row.get("profit_units")),
            fnum(row.get("issue_win_rate")),
        ),
        reverse=True,
    )
    plot_strategies = [str(row["strategy"]) for row in summaries[: args.plot_top_n]]
    curve = cumulative_rows(issue_rows=issue_rows, n7_rows=n7_rows, strategies=plot_strategies)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_raw_tickets.csv", raw_rows)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_budget_tickets.csv", budgeted)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_issue_profit.csv", issue_rows)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_summary.csv", summaries)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_annual.csv", annual)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_mix_summary.csv", mix)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_pool_summary.csv", pools)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_hq_capture.csv", captures)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_vs_n7.csv", comparison)
    write_csv_all(args.output_dir / "binary_ev_pool_n_sweep_equity_curve.csv", curve)
    plot_equity(curve, args.figure_path)

    keep = [
        "strategy",
        "pool_n_legs",
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
        "pool_avg_high_options",
        "pool_avg_high_matches",
        "pool_avg_raw_tickets",
        "mix_raw_roi",
        "mix_raw_hit_rate",
        "mix_pattern_mix",
        "hq_captured_hq_missed_winners",
    ]
    report = [
        "# Binary EV pool N sweep",
        "",
        f"- Source outcome table: `{option_path}`",
        f"- Source calibrated arm: `{args.source_strategy}`",
        "- Selector premise: collapse pre-match EV into only `high` and `low`; high outcomes are investable, low outcomes only protect selected tickets.",
        "- `absolute` high means `q_cal >= cut`; `local` high means issue-local top share by `q_cal`.",
        "- Tickets are unique N=3/4/5 combinations with distinct matches. Same-budget replay uses 256 units per active issue with fractional scaling/ranking by predicted EV.",
        "- This directly tests whether increasing N to absorb more high-EV matches uses capital better than deepening N3 coverage.",
        "",
        "## Summary",
        "",
        md_table([{key: row.get(key, "") for key in keep} for row in summaries], limit=40),
        "",
        "## Pool Shape",
        "",
        md_table(pools, limit=40),
        "",
        "## Raw Mix",
        "",
        md_table(mix, limit=40),
        "",
        "## High-Quality Missed Winner Capture",
        "",
        md_table(captures, limit=40) if captures else "_No high-quality missed-winner file found._",
        "",
        "## Annual For Top Strategies",
        "",
        md_table(compact_annual(annual, plot_strategies[:4]), limit=80),
        "",
        "## Interpretation",
        "",
        "- This is a selector test, not a final staking policy. If higher N improves capital efficiency, it should be considered a separate sleeve from N3 high-win coverage.",
        "- The high-quality missed-winner capture section is N3-based only; use the summary/annual rows for N4/N5 evaluation.",
        "- If absolute high activates fewer issues, compare both deployed ROI and unit-time profit before treating it as better.",
        "",
        f"Equity curve SVG: `{args.figure_path}`",
        "",
        "## Files",
        "",
        f"- Summary: `{args.output_dir / 'binary_ev_pool_n_sweep_summary.csv'}`",
        f"- Annual: `{args.output_dir / 'binary_ev_pool_n_sweep_annual.csv'}`",
        f"- Budget tickets: `{args.output_dir / 'binary_ev_pool_n_sweep_budget_tickets.csv'}`",
        f"- Pool summary: `{args.output_dir / 'binary_ev_pool_n_sweep_pool_summary.csv'}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, default=Path("results/n3_outcome_ev_depth_coverage_20260628"))
    parser.add_argument("--source-strategy", default=SOURCE_STRATEGY)
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument(
        "--high-quality-path",
        type=Path,
        default=Path("results/n3_missed_combos_20260628/high_quality_missed_winners.csv"),
    )
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
    parser.add_argument("--output-dir", type=Path, default=Path("results/binary_ev_pool_n_sweep_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/binary_ev_pool_n_sweep_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/binary_ev_pool_n_sweep_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
