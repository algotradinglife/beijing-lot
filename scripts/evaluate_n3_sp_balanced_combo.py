#!/usr/bin/env python3
"""Evaluate N3 combos with balanced estimated-SP exposure across tickets."""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n3_independent_selector import (
    BASE_MODEL,
    BASE_POLICY,
    SOURCE_STRATEGY,
    SelectorSpec,
    build_specs,
    decision_passes,
    fnum,
    load_action_lookup,
    load_issue_metadata,
    load_n7_base,
    load_window_map,
    plot_equity,
    rank_score,
    summarize_issue_rows,
    annual_rows,
    compare_with_n7,
    cumulative_rows,
    selector_meta_rows,
    write_csv_all,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.walkforward_beidan_strategy_eval import Leg, Ticket, default_db_path, md_table, settle_ticket, write_csv


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def load_leg_pools(
    *,
    decisions_path: Path,
    source_strategy: str,
    specs: list[SelectorSpec],
    action_lookup,
) -> dict[str, dict[str, list[tuple[Leg, float]]]]:
    pools: dict[str, dict[str, list[tuple[Leg, float]]]] = {spec.name: defaultdict(list) for spec in specs}
    for row in read_csv(decisions_path):
        if row.get("strategy") != source_strategy:
            continue
        issue = str(row["issue"])
        match_id = int(float(row["match_id"]))
        action_code = str(row["best_single_code"])
        action_row = action_lookup.get((issue, match_id, action_code))
        if action_row is None:
            continue
        estimated_sp = fnum(row.get("best_single_odds"), math.nan)
        if not math.isfinite(estimated_sp) or estimated_sp <= 0:
            continue
        for spec in specs:
            ok, vals = decision_passes(spec, row)
            if not ok:
                continue
            ranked = rank_score(spec, **vals)
            if ranked <= 0 or not math.isfinite(ranked):
                continue
            leg = Leg(
                row=action_row,
                strategy=f"{spec.name}_sp_balanced",
                score_factor=ranked,
                p_hat=vals["p_hat"],
                source_rule=(
                    f"n3_sp_balanced;source_strategy={source_strategy};rank_mode={spec.rank_mode};"
                    f"estimated_sp={estimated_sp:.6g};score={vals['score']:.6g};ev={vals['ev_standalone']:.6g}"
                ),
            )
            pools[spec.name][issue].append((leg, estimated_sp))
    for by_issue in pools.values():
        for issue, legs in by_issue.items():
            by_issue[issue] = dedup_best_by_match(legs)
    return {strategy: dict(by_issue) for strategy, by_issue in pools.items()}


def dedup_best_by_match(legs: list[tuple[Leg, float]]) -> list[tuple[Leg, float]]:
    best: dict[int, tuple[Leg, float]] = {}
    for leg, estimated_sp in legs:
        current = best.get(leg.row.match_id)
        if current is None or (leg.score_factor, leg.p_hat) > (current[0].score_factor, current[0].p_hat):
            best[leg.row.match_id] = (leg, estimated_sp)
    return sorted(
        best.values(),
        key=lambda item: (item[0].score_factor, item[0].p_hat, item[1]),
        reverse=True,
    )


def sampled_triples(m: int, rng: random.Random, limit: int) -> list[tuple[int, int, int]]:
    total = m * (m - 1) * (m - 2) // 6
    if total <= limit:
        triples = list(itertools.combinations(range(m), 3))
        rng.shuffle(triples)
        return triples
    seen = set()
    triples = []
    attempts = 0
    max_attempts = limit * 60
    while len(triples) < limit and attempts < max_attempts:
        attempts += 1
        triple = tuple(sorted(rng.sample(range(m), 3)))
        if triple in seen:
            continue
        seen.add(triple)
        triples.append(triple)
    return triples


def sp_balanced_triples(
    legs: list[tuple[Leg, float]],
    *,
    ticket_cap: int,
    n_buckets: int,
    seed_parts: tuple[object, ...],
) -> tuple[list[tuple[int, int, int]], dict[str, float]]:
    rng = random.Random(stable_seed(*seed_parts))
    m = len(legs)
    candidate_limit = max(ticket_cap * 30, 2000)
    triples = sampled_triples(m, rng, candidate_limit)
    if not triples:
        return [], {}
    enriched = []
    for triple in triples:
        log_sp = sum(math.log(max(legs[i][1], 1e-9)) for i in triple)
        avg_leg_score = sum(legs[i][0].score_factor for i in triple) / 3.0
        enriched.append((log_sp, avg_leg_score, triple))
    enriched.sort(key=lambda item: item[0])
    buckets: list[list[tuple[float, float, tuple[int, int, int]]]] = [[] for _ in range(n_buckets)]
    for idx, item in enumerate(enriched):
        bucket_idx = min(n_buckets - 1, int(idx * n_buckets / len(enriched)))
        buckets[bucket_idx].append(item)
    for bucket in buckets:
        rng.shuffle(bucket)
    selected = []
    bucket_counts = [0 for _ in buckets]
    cursor = 0
    while len(selected) < ticket_cap and any(buckets):
        bucket_idx = cursor % len(buckets)
        cursor += 1
        if not buckets[bucket_idx]:
            continue
        _, _, triple = buckets[bucket_idx].pop()
        selected.append(triple)
        bucket_counts[bucket_idx] += 1
    if selected and len(selected) < ticket_cap:
        base = list(selected)
        while len(selected) < ticket_cap:
            selected.append(base[len(selected) % len(base)])
    selected_logs = [sum(math.log(max(legs[i][1], 1e-9)) for i in triple) for triple in selected]
    return selected[:ticket_cap], {
        "candidate_combos": len(triples),
        "sp_bucket_count": n_buckets,
        "selected_log_sp_min": min(selected_logs) if selected_logs else math.nan,
        "selected_log_sp_max": max(selected_logs) if selected_logs else math.nan,
        "selected_log_sp_avg": sum(selected_logs) / len(selected_logs) if selected_logs else math.nan,
        "selected_sp_product_avg": sum(math.exp(v) for v in selected_logs) / len(selected_logs) if selected_logs else math.nan,
        "selected_bucket_counts": ",".join(str(count) for count in bucket_counts),
    }


def make_ticket_rows(
    *,
    pools: dict[str, dict[str, list[tuple[Leg, float]]]],
    specs: list[SelectorSpec],
    window_map: dict[str, tuple[str, str]],
    n_buckets: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    out = []
    coverage = []
    spec_by_name = {spec.name: spec for spec in specs}
    for strategy, by_issue in sorted(pools.items()):
        spec = spec_by_name[strategy]
        for issue, legs in sorted(by_issue.items()):
            if len(legs) < 3:
                continue
            triples, stats = sp_balanced_triples(
                legs,
                ticket_cap=spec.ticket_cap,
                n_buckets=n_buckets,
                seed_parts=("n3_sp_balanced", strategy, issue, spec.ticket_cap),
            )
            if not triples:
                continue
            train_start, train_end = window_map.get(issue, ("", ""))
            for idx, triple in enumerate(triples, start=1):
                chosen = tuple(legs[i][0] for i in triple)
                estimated_sp_product = math.prod(legs[i][1] for i in triple)
                ticket = Ticket(
                    strategy=f"{strategy}_sp_balanced",
                    issue=issue,
                    n_legs=3,
                    ticket_idx=idx,
                    train_start_issue=train_start,
                    train_end_issue=train_end,
                    legs=chosen,
                )
                row = settle_ticket(ticket)
                row.update(
                    {
                        "rank_mode": spec.rank_mode,
                        "ticket_cap": spec.ticket_cap,
                        "overlap_penalty": spec.overlap_penalty,
                        "min_p": spec.min_p,
                        "min_odds": spec.min_odds,
                        "max_odds": spec.max_odds,
                        "min_score": spec.min_score,
                        "min_ev": spec.min_ev,
                        "coverage_mode": "estimated_sp_product_balanced",
                        "estimated_sp_product": estimated_sp_product,
                        "estimated_log_sp_product": math.log(max(estimated_sp_product, 1e-9)),
                    }
                )
                out.append(row)
            coverage.append(
                {
                    "strategy": f"{strategy}_sp_balanced",
                    "issue": issue,
                    "candidate_legs": len(legs),
                    "ticket_cap": spec.ticket_cap,
                    "raw_tickets": len(triples),
                    **stats,
                }
            )
    return out, coverage


def run(args: argparse.Namespace) -> None:
    specs = build_specs(args.ticket_caps, [args.overlap_penalty])
    action_lookup = load_action_lookup(args.db_path, args.min_year)
    window_map = load_window_map(args.result_dir)
    pools = load_leg_pools(
        decisions_path=args.result_dir / "ev_framework_decisions.csv",
        source_strategy=args.source_strategy,
        specs=specs,
        action_lookup=action_lookup,
    )
    raw_rows, coverage_rows = make_ticket_rows(
        pools=pools,
        specs=specs,
        window_map=window_map,
        n_buckets=args.sp_buckets,
    )
    budgeted = budgeted_ticket_rows(raw_rows, issue_budget_units=args.issue_budget_units, fractional=True)
    issue_rows = issue_profit_rows(budgeted)
    metadata = load_issue_metadata(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    enriched_issue_rows = []
    for row in issue_rows:
        copied = dict(row)
        issue = str(row["issue"])
        copied.update(metadata.get(issue, {}))
        enriched_issue_rows.append(copied)
    summaries = summarize_issue_rows(
        enriched_issue_rows,
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
    n7_rows = load_n7_base(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    comparison = compare_with_n7(enriched_issue_rows, n7_rows)
    comparison_by_strategy = {row["strategy"]: row for row in comparison}
    for row in summaries:
        row.update(
            {
                f"n7_{key}": value
                for key, value in comparison_by_strategy.get(str(row["strategy"]), {}).items()
                if key != "strategy"
            }
        )
    annual = annual_rows(enriched_issue_rows)
    plot_strategies = [str(row["strategy"]) for row in summaries[: args.plot_top_n]]
    curve = cumulative_rows(issue_rows=enriched_issue_rows, n7_rows=n7_rows, strategies=plot_strategies)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "n3_sp_balanced_selector_specs.csv", selector_meta_rows(specs))
    write_csv_all(args.output_dir / "n3_sp_balanced_raw_tickets.csv", raw_rows)
    write_csv_all(args.output_dir / "n3_sp_balanced_budget_tickets.csv", budgeted)
    write_csv_all(args.output_dir / "n3_sp_balanced_issue_profit.csv", enriched_issue_rows)
    write_csv_all(args.output_dir / "n3_sp_balanced_summary.csv", summaries)
    write_csv_all(args.output_dir / "n3_sp_balanced_annual.csv", annual)
    write_csv_all(args.output_dir / "n3_sp_balanced_vs_n7.csv", comparison)
    write_csv_all(args.output_dir / "n3_sp_balanced_coverage_stats.csv", coverage_rows)
    write_csv_all(args.output_dir / "n3_sp_balanced_equity_curve.csv", curve)
    plot_equity(curve, args.figure_path)

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
        "avg_tickets_per_issue",
    ]
    report = [
        "# N3 estimated-SP balanced combo selector",
        "",
        "- Rule: q/confidence/EV only filters qualified legs.",
        "- Combo stage samples candidate 3-combos and balances ticket exposure across estimated SP product buckets.",
        "- This intentionally avoids putting only the highest estimated-SP legs together.",
        f"- Same fixed `{args.issue_budget_units:g}`-unit issue budget, fractional filled.",
        "",
        "## Summary",
        "",
        md_table([{key: row.get(key, "") for key in keep} for row in summaries], limit=40),
        "",
        f"Equity curve SVG: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


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
    parser.add_argument("--overlap-penalty", type=float, default=0.5)
    parser.add_argument("--sp-buckets", type=int, default=5)
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
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_sp_balanced_combo_selector_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n3_sp_balanced_combo_selector_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n3_sp_balanced_combo_selector_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
