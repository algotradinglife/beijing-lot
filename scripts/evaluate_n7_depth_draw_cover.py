#!/usr/bin/env python3
"""Evaluate N=7 depth-weighted coverage combined with draw-cover legs."""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import (
    avg_depth_weight,
    avg_pair_overlap,
    make_depth_weighted_tickets,
    max_leg_use_in_tickets,
    model_probabilities,
    top_agree_rate,
    transform_legs_for_depth,
)
from scripts.evaluate_n7_draw_cover import convert_ticket
from scripts.walkforward_beidan_result_model_eval import (
    build_samples,
    load_match_extras,
    market_probs,
)
from scripts.walkforward_beidan_strategy_eval import (
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    full_cover_lookup,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def issue_profit_rows(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: defaultdict(lambda: {"stake": 0.0, "profit": 0.0, "hits": 0, "tickets": 0}))
    for row in ticket_rows:
        vals = grouped[str(row["strategy"])][str(row["issue"])]
        vals["stake"] += float(row["stake_units"])
        vals["profit"] += float(row["profit_units"])
        vals["hits"] += int(row["hit"])
        vals["tickets"] += 1
    out = []
    for strategy, by_issue in sorted(grouped.items()):
        for issue, vals in sorted(by_issue.items()):
            out.append(
                {
                    "strategy": strategy,
                    "issue": issue,
                    "tickets": vals["tickets"],
                    "hits": vals["hits"],
                    "stake_units": vals["stake"],
                    "profit_units": vals["profit"],
                    "roi": vals["profit"] / vals["stake"] if vals["stake"] else float("nan"),
                }
            )
    return out


def compact_summary(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "strategy",
        "n_tickets",
        "n_issues",
        "hit_rate",
        "profitable_issues",
        "total_stake_units",
        "total_profit_units",
        "roi",
        "excess_roi_vs_baseline",
        "best_issue_profit_share",
        "avg_issue_stake_units",
        "max_drawdown_pct_on_10000",
        "max_ticket_loss_streak",
        "avg_double_cover_per_ticket",
        "verdict",
    ]
    return [{k: row.get(k, "") for k in keep} for row in summary]


def renamed_draw_cover_ticket(
    ticket: Ticket,
    *,
    strategy_prefix: str,
    draw_policy: str,
    cover_count: int,
    action_lookup: dict[tuple[int, str], object],
    samples_by_match: dict[int, object],
    model_probs_by_match: dict[int, np.ndarray],
    market_probs_by_match: dict[int, np.ndarray],
    require_positive_draw_edge: bool,
) -> Ticket:
    converted = convert_ticket(
        ticket,
        policy=draw_policy,
        cover_count=cover_count,
        action_lookup=action_lookup,
        samples_by_match=samples_by_match,
        model_probs_by_match=model_probs_by_match,
        market_probs_by_match=market_probs_by_match,
        require_positive_draw_edge=require_positive_draw_edge,
    )
    suffix = "_posedge" if require_positive_draw_edge else ""
    return replace(converted, strategy=f"{strategy_prefix}__draw_cover_{draw_policy}_k{cover_count}{suffix}")


def append_settled(ticket_rows: list[dict[str, object]], tickets: list[Ticket]) -> None:
    ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)


def coverage_snapshot(strategy: str, test_issue: str, legs, tickets: list[Ticket]) -> dict[str, object]:
    use_counts: Counter[str] = Counter()
    for ticket in tickets:
        for leg in ticket.legs:
            use_counts[leg.leg_id] += 1
    return {
        "strategy": strategy,
        "test_issue": test_issue,
        "n_policy_legs": len(legs),
        "n_tickets": len(tickets),
        "avg_score_factor": sum(leg.score_factor for leg in legs) / len(legs) if legs else float("nan"),
        "avg_model_p": sum(leg.p_hat for leg in legs) / len(legs) if legs else float("nan"),
        "top1_agree_rate": top_agree_rate(legs),
        "avg_depth_weight": avg_depth_weight(legs),
        "max_leg_use_in_tickets": max_leg_use_in_tickets(tickets),
        "avg_pair_overlap": avg_pair_overlap(tickets),
        "distinct_legs_used": len(use_counts),
    }


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    depth_policies = parse_strings(args.depth_policies)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    ticket_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues:issue_idx]
        train_action_rows = [row for issue in train_issues for row in action_by_issue.get(issue, [])]
        test_action_rows = action_by_issue.get(test_issue, [])
        train_samples = [sample for issue in train_issues for sample in samples_by_issue.get(issue, [])]
        test_samples = samples_by_issue.get(test_issue, [])
        if len(train_samples) < args.min_train_matches or not test_samples:
            continue

        q_model, global_q = train_q_model(train_action_rows, snapshot=args.snapshot, prior_n=args.q_prior_n)
        q_legs = build_q_baseline_legs(
            test_action_rows,
            q_model,
            global_q,
            snapshot=args.snapshot,
            min_proxy_odds=args.baseline_min_proxy_odds,
            max_proxy_odds=args.baseline_max_proxy_odds,
            min_score_factor=threshold,
        )
        if len(q_legs) < args.n_legs:
            continue

        model_probs = model_probabilities(args, train_samples, test_samples)
        market = market_probs(test_samples)
        samples_by_match = {sample.match_id: sample for sample in test_samples}
        model_probs_by_match = {sample.match_id: model_probs[i] for i, sample in enumerate(test_samples)}
        market_probs_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        action_lookup = {(row.match_id, row.action_code): row for row in test_action_rows}

        base_tickets = make_tickets(
            q_legs,
            strategy="baseline_q_high_sp",
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            full_rows=full_cover_lookup(test_action_rows),
            action_model={},
            protect_full_count=0,
        )
        append_settled(ticket_rows, base_tickets)
        base_cover_tickets = [
            renamed_draw_cover_ticket(
                ticket,
                strategy_prefix="baseline_q_high_sp",
                draw_policy=args.draw_policy,
                cover_count=args.cover_count,
                action_lookup=action_lookup,
                samples_by_match=samples_by_match,
                model_probs_by_match=model_probs_by_match,
                market_probs_by_match=market_probs_by_match,
                require_positive_draw_edge=args.require_positive_draw_edge,
            )
            for ticket in base_tickets
        ]
        append_settled(ticket_rows, base_cover_tickets)
        coverage_rows.append(coverage_snapshot("baseline_q_high_sp", test_issue, q_legs, base_tickets))

        depth_counts: dict[str, int] = {}
        for policy in depth_policies:
            depth_legs, depth_weights = transform_legs_for_depth(
                q_legs,
                policy=policy,
                probs_by_match=model_probs_by_match,
                market_by_match=market_probs_by_match,
                min_score_factor=threshold,
            )
            depth_strategy = f"confidence_{policy}"
            depth_tickets = make_depth_weighted_tickets(
                depth_legs,
                depth_weights=depth_weights,
                strategy=depth_strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                max_leg_uses=args.max_depth_leg_uses if policy.startswith("depth_constrained") else 0,
                max_ticket_overlap=args.max_depth_ticket_overlap if policy.startswith("depth_constrained") else 0,
            )
            append_settled(ticket_rows, depth_tickets)
            depth_cover_tickets = [
                renamed_draw_cover_ticket(
                    ticket,
                    strategy_prefix=depth_strategy,
                    draw_policy=args.draw_policy,
                    cover_count=args.cover_count,
                    action_lookup=action_lookup,
                    samples_by_match=samples_by_match,
                    model_probs_by_match=model_probs_by_match,
                    market_probs_by_match=market_probs_by_match,
                    require_positive_draw_edge=args.require_positive_draw_edge,
                )
                for ticket in depth_tickets
            ]
            append_settled(ticket_rows, depth_cover_tickets)
            coverage_rows.append(coverage_snapshot(depth_strategy, test_issue, depth_legs, depth_tickets))
            depth_counts[policy] = len(depth_tickets)

        row = {
            "test_issue": test_issue,
            "train_start_issue": train_issues[0],
            "train_end_issue": train_issues[-1],
            "n_train_matches": len(train_samples),
            "n_test_matches": len(test_samples),
            "n_q_legs": len(q_legs),
            "n_base_tickets": len(base_tickets),
        }
        for policy, count in depth_counts.items():
            row[f"n_{policy}_tickets"] = count
        window_rows.append(row)

    summary = summarize_tickets(ticket_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    issue_rows = issue_profit_rows(ticket_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "depth_draw_tickets.csv", ticket_rows)
    write_csv(out / "depth_draw_summary.csv", summary)
    write_csv(out / "depth_draw_issue_profit.csv", issue_rows)
    write_csv(out / "depth_draw_coverage.csv", coverage_rows)
    write_csv(out / "depth_draw_windows.csv", window_rows)

    report = [
        "# N=7 depth plus draw-cover evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- N legs: `{args.n_legs}`",
        f"- Max tickets per issue: `{args.max_tickets_per_issue}`",
        f"- Model source: `{args.model_source}`",
        f"- Feature set / L2: `{args.feature_set}` / `{args.l2}`",
        f"- Depth policies: `{args.depth_policies}`",
        f"- Depth constraints: max leg uses `{args.max_depth_leg_uses}`, max ticket overlap `{args.max_depth_ticket_overlap}`",
        f"- Draw cover: `{args.draw_policy}`, k=`{args.cover_count}`, positive edge only `{args.require_positive_draw_edge}`",
        "",
        "## Summary",
        md_table(compact_summary(summary)),
        "## Coverage",
        md_table(coverage_rows[:80]),
        "",
        "## Files",
        "",
        "- `depth_draw_summary.csv`",
        "- `depth_draw_tickets.csv`",
        "- `depth_draw_issue_profit.csv`",
        "- `depth_draw_coverage.csv`",
        "- `depth_draw_windows.csv`",
        "",
    ]
    (out / "depth_draw_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'depth_draw_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_depth_draw_cover"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--model-source", choices=("multiclass", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--depth-policies", default="depth_constrained_hybrid")
    parser.add_argument("--draw-policy", default="model_draw_ratio")
    parser.add_argument("--cover-count", type=int, default=2)
    parser.add_argument("--require-positive-draw-edge", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
