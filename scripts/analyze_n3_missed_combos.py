#!/usr/bin/env python3
"""Analyze missed N3 combos and a small-N increase smoke test.

The input is the outcome-level EV-depth coverage run.  For a selected strategy
arm, this script compares bought tickets with high-EV unbought combinations and
all unbought combinations that would have hit.  It also builds a simple N=4
top-q arm from the same outcome pool to test whether slightly increasing N is
promising.
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
    compact_summary,
    fnum,
    load_issue_metadata,
    load_n7_base,
    summarize_issue_rows,
    annual_rows,
    write_csv_all,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.walkforward_beidan_strategy_eval import RETURN_RATE, md_table


DEFAULT_STRATEGY = "n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev"


@dataclass(frozen=True)
class Option:
    strategy: str
    issue: str
    match_id: int
    match_idx: int
    league: str
    hcp: float
    outcome: str
    tier: str
    q_cal: float
    single_ev: float
    n3_leg_ev: float
    p_cal: float
    estimated_sp: float
    target_depth: float
    actual_depth: int
    hit: int
    winning_sp: float

    @property
    def leg_key(self) -> str:
        return f"{self.match_id}:{self.outcome}@{self.hcp:g}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_legs(raw: str) -> tuple[str, ...]:
    return tuple(sorted(part.strip() for part in str(raw).split(";") if part.strip()))


def load_options(path: Path, strategy: str) -> dict[str, list[Option]]:
    by_issue: dict[str, list[Option]] = defaultdict(list)
    for row in read_csv(path):
        if row.get("strategy") != strategy:
            continue
        opt = Option(
            strategy=strategy,
            issue=str(row["issue"]),
            match_id=int(float(row["match_id"])),
            match_idx=int(float(row["match_idx"])),
            league=str(row.get("league", "")),
            hcp=fnum(row.get("hcp")),
            outcome=str(row["outcome"]),
            tier=str(row["tier"]),
            q_cal=fnum(row.get("q_cal")),
            single_ev=fnum(row.get("single_ev")),
            n3_leg_ev=fnum(row.get("n3_leg_ev")),
            p_cal=fnum(row.get("p_cal")),
            estimated_sp=fnum(row.get("estimated_sp")),
            target_depth=fnum(row.get("target_depth")),
            actual_depth=int(fnum(row.get("actual_depth"))),
            hit=int(fnum(row.get("hit"))),
            winning_sp=fnum(row.get("winning_sp")),
        )
        by_issue[opt.issue].append(opt)
    return {issue: sorted(vals, key=lambda opt: (opt.q_cal, opt.p_cal), reverse=True) for issue, vals in by_issue.items()}


def load_selected(path: Path, strategy: str) -> tuple[dict[str, Counter[tuple[str, ...]]], list[dict[str, str]]]:
    selected: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    rows = []
    for row in read_csv(path):
        if row.get("strategy") != strategy:
            continue
        key = parse_legs(row.get("legs", ""))
        selected[str(row["issue"])][key] += 1
        rows.append(row)
    return dict(selected), rows


def combo_key(options: Iterable[Option]) -> tuple[str, ...]:
    return tuple(sorted(opt.leg_key for opt in options))


def tier_pattern(options: Iterable[Option]) -> str:
    return "".join(sorted((opt.tier for opt in options), reverse=True))


def combo_metrics(options: tuple[Option, ...]) -> dict[str, object]:
    q_product = math.prod(max(opt.q_cal, 1e-12) for opt in options)
    pred_hit_prob = math.prod(max(0.0, min(1.0, opt.p_cal)) for opt in options)
    hit = int(all(opt.hit == 1 for opt in options))
    sp_product = math.prod(max(opt.winning_sp, 0.0) for opt in options)
    payout = RETURN_RATE * sp_product if hit else 0.0
    return {
        "n": len(options),
        "legs": ";".join(opt.leg_key for opt in options),
        "tier_pattern": tier_pattern(options),
        "high_count": sum(1 for opt in options if opt.tier == "H"),
        "q_product": q_product,
        "pred_ev_per_stake": RETURN_RATE * q_product - 1.0,
        "pred_hit_prob": pred_hit_prob,
        "avg_q_cal": sum(opt.q_cal for opt in options) / len(options),
        "avg_single_ev": sum(opt.single_ev for opt in options) / len(options),
        "avg_actual_depth": sum(opt.actual_depth for opt in options) / len(options),
        "min_actual_depth": min(opt.actual_depth for opt in options),
        "avg_target_depth": sum(opt.target_depth for opt in options) / len(options),
        "hit": hit,
        "payout_units": payout,
        "profit_units": payout - 1.0 if hit else -1.0,
        "sp_product": sp_product if hit else 0.0,
        "avg_winning_sp": sum(opt.winning_sp for opt in options) / len(options),
        "outcomes": "".join(opt.outcome for opt in options),
        "hcps": ";".join(f"{opt.hcp:g}" for opt in options),
        "leagues": ";".join(opt.league for opt in options),
    }


def top_combos(
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
    out: list[tuple[Option, ...]] = []
    popped = 0
    max_popped = max(limit * 160, 5000)
    exclude = exclude or set()
    while heap and len(out) < limit and popped < max_popped:
        _neg, idxs = heapq.heappop(heap)
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


def missed_winning_rows(
    by_issue: dict[str, list[Option]],
    selected: dict[str, Counter[tuple[str, ...]]],
    *,
    examples_per_issue: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    issue_rows = []
    example_rows = []
    for issue, options in sorted(by_issue.items(), key=lambda item: issue_sort_key(item[0])):
        hit_opts = [opt for opt in options if opt.hit == 1]
        selected_keys = set(selected.get(issue, Counter()).keys())
        total_win = 0
        selected_win = 0
        missed_win = 0
        pattern_counts: Counter[str] = Counter()
        missed_metrics = []
        selected_metrics = []
        for a in range(len(hit_opts)):
            for b in range(a + 1, len(hit_opts)):
                if hit_opts[a].match_id == hit_opts[b].match_id:
                    continue
                for c in range(b + 1, len(hit_opts)):
                    combo = (hit_opts[a], hit_opts[b], hit_opts[c])
                    if len({opt.match_id for opt in combo}) < 3:
                        continue
                    total_win += 1
                    metrics = combo_metrics(combo)
                    key = combo_key(combo)
                    if key in selected_keys:
                        selected_win += 1
                        selected_metrics.append(metrics)
                    else:
                        missed_win += 1
                        pattern_counts[str(metrics["tier_pattern"])] += 1
                        missed_metrics.append(metrics)
        missed_metrics.sort(key=lambda row: (fnum(row.get("pred_ev_per_stake")), fnum(row.get("pred_hit_prob"))), reverse=True)
        for row in missed_metrics[:examples_per_issue]:
            example = {"issue": issue, **row}
            example_rows.append(example)
        issue_rows.append(
            {
                "issue": issue,
                "n_hit_options": len(hit_opts),
                "selected_tickets": sum(selected.get(issue, Counter()).values()),
                "total_winning_combos": total_win,
                "selected_unique_winning_combos": selected_win,
                "missed_winning_combos": missed_win,
                "selected_win_capture_rate": selected_win / total_win if total_win else math.nan,
                "missed_to_selected_win_ratio": missed_win / selected_win if selected_win else math.nan,
                "avg_missed_win_pred_ev": avg([fnum(row.get("pred_ev_per_stake")) for row in missed_metrics]),
                "avg_selected_win_pred_ev": avg([fnum(row.get("pred_ev_per_stake")) for row in selected_metrics]),
                "avg_missed_win_actual_depth": avg([fnum(row.get("avg_actual_depth")) for row in missed_metrics]),
                "top_missed_patterns": ";".join(f"{k}:{v}" for k, v in pattern_counts.most_common(6)),
            }
        )
    return issue_rows, example_rows


def avg(values: list[float]) -> float:
    vals = [v for v in values if math.isfinite(v)]
    return sum(vals) / len(vals) if vals else math.nan


def top_missed_rows(
    by_issue: dict[str, list[Option]],
    selected: dict[str, Counter[tuple[str, ...]]],
    *,
    n: int,
    top_per_issue: int,
) -> list[dict[str, object]]:
    out = []
    for issue, options in sorted(by_issue.items(), key=lambda item: issue_sort_key(item[0])):
        exclude = set(selected.get(issue, Counter()).keys()) if n == 3 else set()
        combos = top_combos(options, n=n, limit=top_per_issue, exclude=exclude)
        for rank, combo in enumerate(combos, start=1):
            out.append({"issue": issue, "rank": rank, **combo_metrics(combo)})
    return out


def selected_ticket_summary(selected_rows: list[dict[str, str]]) -> dict[str, object]:
    n = len(selected_rows)
    hits = [row for row in selected_rows if int(fnum(row.get("hit"))) == 1]
    return {
        "sample": "selected_n3_tickets",
        "n_tickets": n,
        "hit_rate": len(hits) / n if n else math.nan,
        "avg_pred_ev_per_stake": avg([fnum(row.get("pred_ev_per_stake")) for row in selected_rows]),
        "avg_pred_hit_prob": avg([fnum(row.get("pred_hit_prob")) for row in selected_rows]),
        "avg_profit_per_ticket": avg([fnum(row.get("profit_units")) for row in selected_rows]),
        "avg_payout_on_hits": avg([fnum(row.get("payout_units")) for row in hits]),
    }


def combo_sample_summary(rows: list[dict[str, object]], sample: str) -> dict[str, object]:
    hits = [row for row in rows if int(row.get("hit", 0)) == 1]
    patterns = Counter(str(row.get("tier_pattern")) for row in rows)
    return {
        "sample": sample,
        "n_tickets": len(rows),
        "hit_rate": len(hits) / len(rows) if rows else math.nan,
        "avg_pred_ev_per_stake": avg([fnum(row.get("pred_ev_per_stake")) for row in rows]),
        "avg_pred_hit_prob": avg([fnum(row.get("pred_hit_prob")) for row in rows]),
        "avg_profit_per_ticket": avg([fnum(row.get("profit_units")) for row in rows]),
        "avg_payout_on_hits": avg([fnum(row.get("payout_units")) for row in hits]),
        "avg_high_count": avg([fnum(row.get("high_count")) for row in rows]),
        "avg_actual_depth": avg([fnum(row.get("avg_actual_depth")) for row in rows]),
        "top_patterns": ";".join(f"{k}:{v}" for k, v in patterns.most_common(6)),
    }


def yearly_combo_summary(rows: list[dict[str, object]], sample: str) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[issue_year(row["issue"])].append(row)
    out = []
    for year, vals in sorted(grouped.items()):
        summary = combo_sample_summary(vals, sample)
        summary["year"] = year
        out.append(summary)
    return out


def n4_budget_summary(
    rows: list[dict[str, object]],
    *,
    issue_budget_units: float,
    metadata: dict[str, dict[str, object]],
    recent_min_year: int,
    recent_max_year: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    budgeted = budgeted_ticket_rows(rows, issue_budget_units=issue_budget_units, fractional=True)
    issue_rows = issue_profit_rows(budgeted)
    enriched = []
    for row in issue_rows:
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
    summary = summarize_issue_rows(
        enriched,
        issue_budget_units=issue_budget_units,
        recent_min_year=recent_min_year,
        recent_max_year=recent_max_year,
    )
    annual = annual_rows(enriched)
    return budgeted, enriched, summary + annual


def n4_ticket_rows(top_n4_rows: list[dict[str, object]], strategy: str) -> list[dict[str, object]]:
    out = []
    grouped_counter: Counter[str] = Counter()
    for row in top_n4_rows:
        issue = str(row["issue"])
        grouped_counter[issue] += 1
        out.append(
            {
                "strategy": strategy,
                "issue": issue,
                "n_legs": 4,
                "ticket_idx": grouped_counter[issue],
                "stake_units": 1.0,
                "hit": int(row["hit"]),
                "payout_units": fnum(row.get("payout_units")),
                "profit_units": fnum(row.get("profit_units")),
                "roi": fnum(row.get("profit_units")),
                "pred_factor_product": fnum(row.get("q_product")),
                "pred_ev_per_stake": fnum(row.get("pred_ev_per_stake")),
                "pred_hit_prob": fnum(row.get("pred_hit_prob")),
                "legs": row.get("legs", ""),
            }
        )
    return out


def aggregate_missed_issue_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    total_win = sum(int(fnum(row.get("total_winning_combos"))) for row in rows)
    selected_win = sum(int(fnum(row.get("selected_unique_winning_combos"))) for row in rows)
    missed_win = sum(int(fnum(row.get("missed_winning_combos"))) for row in rows)
    active = [row for row in rows if fnum(row.get("total_winning_combos")) > 0]
    return {
        "issues": len(rows),
        "issues_with_winning_combo": len(active),
        "total_winning_combos": total_win,
        "selected_unique_winning_combos": selected_win,
        "missed_winning_combos": missed_win,
        "selected_win_capture_rate": selected_win / total_win if total_win else math.nan,
        "missed_to_selected_win_ratio": missed_win / selected_win if selected_win else math.nan,
        "avg_issue_missed_win_pred_ev": avg([fnum(row.get("avg_missed_win_pred_ev")) for row in active]),
        "avg_issue_selected_win_pred_ev": avg([fnum(row.get("avg_selected_win_pred_ev")) for row in active]),
    }


def high_quality_missed_winners(rows: list[dict[str, object]], *, min_pred_hit: float, min_payout: float) -> list[dict[str, object]]:
    selected = [
        row
        for row in rows
        if fnum(row.get("pred_hit_prob")) >= min_pred_hit and fnum(row.get("payout_units")) >= min_payout
    ]
    return sorted(
        selected,
        key=lambda row: (
            fnum(row.get("payout_units")),
            fnum(row.get("pred_hit_prob")),
            fnum(row.get("pred_ev_per_stake")),
        ),
        reverse=True,
    )


def high_p_sp_low_depth_options(
    by_issue: dict[str, list[Option]],
    *,
    min_p: float,
    min_sp: float,
    max_depth: int,
    max_depth_to_target: float,
) -> list[dict[str, object]]:
    out = []
    for issue, options in sorted(by_issue.items(), key=lambda item: issue_sort_key(item[0])):
        for opt in options:
            depth_to_target = opt.actual_depth / opt.target_depth if opt.target_depth > 0 else math.nan
            if (
                opt.hit == 1
                and opt.p_cal >= min_p
                and opt.winning_sp >= min_sp
                and opt.actual_depth <= max_depth
                and depth_to_target <= max_depth_to_target
            ):
                out.append(
                    {
                        "issue": issue,
                        "match_id": opt.match_id,
                        "match_idx": opt.match_idx,
                        "league": opt.league,
                        "hcp": opt.hcp,
                        "outcome": opt.outcome,
                        "tier": opt.tier,
                        "p_cal": opt.p_cal,
                        "winning_sp": opt.winning_sp,
                        "q_cal": opt.q_cal,
                        "single_ev": opt.single_ev,
                        "target_depth": opt.target_depth,
                        "actual_depth": opt.actual_depth,
                        "depth_to_target": depth_to_target,
                        "leg_key": opt.leg_key,
                    }
                )
    return sorted(
        out,
        key=lambda row: (
            fnum(row.get("p_cal")) * fnum(row.get("winning_sp")),
            fnum(row.get("winning_sp")),
            fnum(row.get("p_cal")),
        ),
        reverse=True,
    )


def run(args: argparse.Namespace) -> None:
    option_path = args.result_dir / "n3_outcome_ev_depth_option_depth.csv"
    ticket_path = args.result_dir / "n3_outcome_ev_depth_raw_tickets.csv"
    by_issue = load_options(option_path, args.strategy)
    selected, selected_rows = load_selected(ticket_path, args.strategy)

    missed_issue, missed_examples = missed_winning_rows(
        by_issue,
        selected,
        examples_per_issue=args.missed_win_examples_per_issue,
    )
    top_missed_n3 = top_missed_rows(
        by_issue,
        selected,
        n=3,
        top_per_issue=args.top_missed_per_issue,
    )
    top_n4 = top_missed_rows(
        by_issue,
        selected,
        n=4,
        top_per_issue=args.n4_tickets_per_issue,
    )
    n4_raw = n4_ticket_rows(top_n4, "n4_topq_from_n3_evdepth")
    metadata = load_issue_metadata(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    n4_budgeted, n4_issue_rows, n4_summary_annual = n4_budget_summary(
        n4_raw,
        issue_budget_units=args.issue_budget_units,
        metadata=metadata,
        recent_min_year=args.recent_min_year,
        recent_max_year=args.recent_max_year,
    )
    n4_summary = [row for row in n4_summary_annual if "year" not in row]
    n4_annual = [row for row in n4_summary_annual if "year" in row]

    selected_summary = selected_ticket_summary(selected_rows)
    high_quality_missed = high_quality_missed_winners(
        missed_examples,
        min_pred_hit=args.high_quality_min_pred_hit,
        min_payout=args.high_quality_min_payout,
    )
    high_p_sp_low_depth = high_p_sp_low_depth_options(
        by_issue,
        min_p=args.high_p_min_p,
        min_sp=args.high_p_min_sp,
        max_depth=args.high_p_max_depth,
        max_depth_to_target=args.high_p_max_depth_to_target,
    )
    sample_summaries = [
        selected_summary,
        combo_sample_summary(top_missed_n3, f"top_{args.top_missed_per_issue}_unbought_n3_per_issue"),
        combo_sample_summary(missed_examples, "missed_winning_n3_examples_top_ev"),
        combo_sample_summary(top_n4, f"top_{args.n4_tickets_per_issue}_n4_per_issue"),
    ]
    missed_aggregate = aggregate_missed_issue_rows(missed_issue)
    top_missed_yearly = yearly_combo_summary(top_missed_n3, "top_unbought_n3")
    n4_yearly = yearly_combo_summary(top_n4, "top_n4")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "missed_winning_issue_summary.csv", missed_issue)
    write_csv_all(args.output_dir / "missed_winning_examples.csv", missed_examples)
    write_csv_all(args.output_dir / "top_unbought_n3_candidates.csv", top_missed_n3)
    write_csv_all(args.output_dir / "high_quality_missed_winners.csv", high_quality_missed)
    write_csv_all(args.output_dir / "high_p_sp_low_depth_options.csv", high_p_sp_low_depth)
    write_csv_all(args.output_dir / "top_n4_candidates.csv", top_n4)
    write_csv_all(args.output_dir / "sample_summary.csv", sample_summaries)
    write_csv_all(args.output_dir / "top_unbought_n3_yearly.csv", top_missed_yearly)
    write_csv_all(args.output_dir / "top_n4_yearly.csv", n4_yearly)
    write_csv_all(args.output_dir / "n4_raw_tickets.csv", n4_raw)
    write_csv_all(args.output_dir / "n4_budget_tickets.csv", n4_budgeted)
    write_csv_all(args.output_dir / "n4_issue_profit.csv", n4_issue_rows)
    write_csv_all(args.output_dir / "n4_summary.csv", n4_summary)
    write_csv_all(args.output_dir / "n4_annual.csv", n4_annual)

    keep_n4 = [
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
    report = [
        "# N3 missed combos and small-N increase audit",
        "",
        f"- Source strategy: `{args.strategy}`",
        f"- Source directory: `{args.result_dir}`",
        "- Missed N3 means: an unbought 3-outcome combo from the same issue/option pool.",
        "- Winning missed N3 means: all three outcomes in that unbought combo actually hit.",
        "- N4 smoke test uses the same outcome pool and takes top-q 4-leg combos per issue; it is not yet an optimized N4 strategy.",
        "",
        "## Selected vs Missed Samples",
        "",
        md_table(sample_summaries),
        "",
        "## Missed Winning Combo Aggregate",
        "",
        md_table([missed_aggregate]),
        "",
        "## High-Quality Missed Winners",
        "",
        f"Filter: `pred_hit_prob >= {args.high_quality_min_pred_hit:g}` and `payout_units >= {args.high_quality_min_payout:g}`.",
        "",
        md_table(high_quality_missed[:30]),
        "",
        "## High P / High SP Low-Depth Hit Outcomes",
        "",
        (
            f"Filter: hit outcomes with `p_cal >= {args.high_p_min_p:g}`, "
            f"`winning_sp >= {args.high_p_min_sp:g}`, actual depth `<= {args.high_p_max_depth}`, "
            f"and depth/target `<= {args.high_p_max_depth_to_target:g}`."
        ),
        "",
        md_table(high_p_sp_low_depth[:30]),
        "",
        "## N4 Same-Budget Smoke",
        "",
        md_table([{key: row.get(key, "") for key in keep_n4} for row in n4_summary]),
        "",
        "## Top Unbought N3 Yearly Hit Rate",
        "",
        md_table(top_missed_yearly, limit=20),
        "",
        "## Top N4 Yearly Hit Rate",
        "",
        md_table(n4_yearly, limit=20),
        "",
        "## Top Missed Winning Examples",
        "",
        md_table(missed_examples[:30]),
        "",
        "## Files",
        "",
        f"- Sample summary: `{args.output_dir / 'sample_summary.csv'}`",
        f"- Missed winning issue summary: `{args.output_dir / 'missed_winning_issue_summary.csv'}`",
        f"- Top unbought N3 candidates: `{args.output_dir / 'top_unbought_n3_candidates.csv'}`",
        f"- High-quality missed winners: `{args.output_dir / 'high_quality_missed_winners.csv'}`",
        f"- High P / high SP low-depth outcomes: `{args.output_dir / 'high_p_sp_low_depth_options.csv'}`",
        f"- N4 summary: `{args.output_dir / 'n4_summary.csv'}`",
        f"- N4 annual: `{args.output_dir / 'n4_annual.csv'}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, default=Path("results/n3_outcome_ev_depth_coverage_20260628"))
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY)
    parser.add_argument("--top-missed-per-issue", type=int, default=180)
    parser.add_argument("--missed-win-examples-per-issue", type=int, default=20)
    parser.add_argument("--n4-tickets-per-issue", type=int, default=180)
    parser.add_argument("--high-quality-min-pred-hit", type=float, default=0.03)
    parser.add_argument("--high-quality-min-payout", type=float, default=30.0)
    parser.add_argument("--high-p-min-p", type=float, default=0.35)
    parser.add_argument("--high-p-min-sp", type=float, default=3.0)
    parser.add_argument("--high-p-max-depth", type=int, default=2)
    parser.add_argument("--high-p-max-depth-to-target", type=float, default=0.5)
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
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_missed_combos_20260628"))
    parser.add_argument("--report-path", type=Path, default=Path("docs/research/n3_missed_combos_2026-06-28.md"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
