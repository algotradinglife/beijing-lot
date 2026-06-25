#!/usr/bin/env python3
"""Evaluate issue-level risk controls on the current N=7 main strategy."""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import make_depth_weighted_tickets, model_probabilities, transform_legs_for_depth
from scripts.evaluate_n7_depth_draw_cover import compact_summary, coverage_snapshot, group_samples_by_issue, issue_profit_rows
from scripts.evaluate_n7_dynamic_draw_cover import dynamic_draw_cover_ticket
from scripts.walkforward_beidan_result_model_eval import build_samples, load_match_extras, market_probs
from scripts.walkforward_beidan_strategy_eval import (
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    md_table,
    settle_ticket,
    snapshot_odds_p,
    summarize_tickets,
    train_q_model,
    write_csv,
)


@dataclass(frozen=True)
class RiskProfile:
    name: str
    max_leg_uses: int
    max_ticket_overlap: int
    max_high_odds_legs: int
    max_extreme_score_legs: int
    max_action_share: float


PROFILES = {
    "loose": RiskProfile(
        name="loose",
        max_leg_uses=8,
        max_ticket_overlap=6,
        max_high_odds_legs=4,
        max_extreme_score_legs=4,
        max_action_share=0.70,
    ),
    "medium": RiskProfile(
        name="medium",
        max_leg_uses=6,
        max_ticket_overlap=5,
        max_high_odds_legs=3,
        max_extreme_score_legs=3,
        max_action_share=0.62,
    ),
    "strict": RiskProfile(
        name="strict",
        max_leg_uses=5,
        max_ticket_overlap=4,
        max_high_odds_legs=2,
        max_extreme_score_legs=2,
        max_action_share=0.56,
    ),
}


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def append_settled(ticket_rows: list[dict[str, object]], tickets: list[Ticket]) -> None:
    ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)


def ticket_quality(ticket: Ticket) -> float:
    return sum(math.log(max(leg.score_factor, 1e-9)) for leg in ticket.legs)


def leg_proxy_odds(leg: Leg, snapshot: str) -> float:
    odds, _ = snapshot_odds_p(leg.row, snapshot)
    return float(odds or 0.0)


def ticket_metrics(ticket: Ticket, *, snapshot: str, high_odds_threshold: float, extreme_score_threshold: float) -> dict[str, object]:
    high_odds = sum(1 for leg in ticket.legs if leg_proxy_odds(leg, snapshot) >= high_odds_threshold)
    extreme_score = sum(1 for leg in ticket.legs if leg.score_factor >= extreme_score_threshold)
    actions = Counter(leg.row.action_code for leg in ticket.legs)
    return {
        "high_odds_legs": high_odds,
        "extreme_score_legs": extreme_score,
        "actions": actions,
        "leg_ids": set(leg.leg_id for leg in ticket.legs),
        "match_ids": set(leg.row.match_id for leg in ticket.legs),
        "quality": ticket_quality(ticket),
    }


def action_share_ok(
    action_counts: Counter[str],
    ticket_actions: Counter[str],
    *,
    profile: RiskProfile,
    n_legs: int,
    selected_count: int,
) -> bool:
    projected_total = (selected_count + 1) * n_legs
    max_count = int(math.ceil(projected_total * profile.max_action_share))
    projected = action_counts.copy()
    projected.update(ticket_actions)
    return all(count <= max_count for count in projected.values())


def select_risk_controlled_tickets(
    candidates: list[Ticket],
    *,
    strategy: str,
    profile: RiskProfile,
    snapshot: str,
    max_tickets: int,
    high_odds_threshold: float,
    extreme_score_threshold: float,
) -> list[Ticket]:
    # Keep the generator order. It already embeds score ranking plus reuse penalties;
    # sorting by raw ticket quality re-concentrates the issue around high-score legs.
    ranked = list(candidates)
    selected: list[Ticket] = []
    selected_leg_sets: list[set[str]] = []
    leg_uses: Counter[str] = Counter()
    match_uses: Counter[int] = Counter()
    action_counts: Counter[str] = Counter()

    for ticket in ranked:
        metrics = ticket_metrics(
            ticket,
            snapshot=snapshot,
            high_odds_threshold=high_odds_threshold,
            extreme_score_threshold=extreme_score_threshold,
        )
        if int(metrics["high_odds_legs"]) > profile.max_high_odds_legs:
            continue
        if int(metrics["extreme_score_legs"]) > profile.max_extreme_score_legs:
            continue
        leg_ids = metrics["leg_ids"]
        match_ids = metrics["match_ids"]
        if any(leg_uses[leg_id] >= profile.max_leg_uses for leg_id in leg_ids):
            continue
        if any(match_uses[match_id] >= profile.max_leg_uses for match_id in match_ids):
            continue
        if any(len(leg_ids & previous) > profile.max_ticket_overlap for previous in selected_leg_sets):
            continue
        if not action_share_ok(
            action_counts,
            metrics["actions"],
            profile=profile,
            n_legs=ticket.n_legs,
            selected_count=len(selected),
        ):
            continue

        ticket_idx = len(selected) + 1
        selected.append(replace(ticket, strategy=strategy, ticket_idx=ticket_idx))
        selected_leg_sets.append(set(leg_ids))
        for leg_id in leg_ids:
            leg_uses[leg_id] += 1
        for match_id in match_ids:
            match_uses[match_id] += 1
        action_counts.update(metrics["actions"])
        if len(selected) >= max_tickets:
            break
    return selected


def risk_profile_rows(
    issue: str,
    strategy: str,
    profile: RiskProfile,
    selected: list[Ticket],
    candidates: list[Ticket],
    *,
    snapshot: str,
    high_odds_threshold: float,
    extreme_score_threshold: float,
) -> dict[str, object]:
    leg_uses: Counter[str] = Counter()
    high_odds_counts = []
    extreme_score_counts = []
    action_counts: Counter[str] = Counter()
    for ticket in selected:
        metrics = ticket_metrics(
            ticket,
            snapshot=snapshot,
            high_odds_threshold=high_odds_threshold,
            extreme_score_threshold=extreme_score_threshold,
        )
        high_odds_counts.append(int(metrics["high_odds_legs"]))
        extreme_score_counts.append(int(metrics["extreme_score_legs"]))
        action_counts.update(metrics["actions"])
        for leg in ticket.legs:
            leg_uses[leg.leg_id] += 1
    total_legs = sum(action_counts.values())
    return {
        "strategy": strategy,
        "issue": issue,
        "profile": profile.name,
        "candidate_tickets": len(candidates),
        "selected_tickets": len(selected),
        "distinct_legs_used": len(leg_uses),
        "max_leg_uses": max(leg_uses.values()) if leg_uses else 0,
        "avg_high_odds_legs": sum(high_odds_counts) / len(high_odds_counts) if high_odds_counts else float("nan"),
        "avg_extreme_score_legs": sum(extreme_score_counts) / len(extreme_score_counts) if extreme_score_counts else float("nan"),
        "max_action_share": max((count / total_legs for count in action_counts.values()), default=float("nan")),
    }


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    profile_names = parse_strings(args.risk_profiles)
    profiles = [PROFILES[name] for name in profile_names]
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    issue_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

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

        depth_legs, depth_weights = transform_legs_for_depth(
            q_legs,
            policy=args.depth_policy,
            probs_by_match=model_probs_by_match,
            market_by_match=market_probs_by_match,
            min_score_factor=threshold,
        )

        reference_strategy = f"confidence_{args.depth_policy}"
        reference_tickets = make_depth_weighted_tickets(
            depth_legs,
            depth_weights=depth_weights,
            strategy=reference_strategy,
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            max_leg_uses=args.reference_max_leg_uses,
            max_ticket_overlap=args.reference_max_ticket_overlap,
        )
        append_settled(ticket_rows, reference_tickets)
        coverage_rows.append(coverage_snapshot(reference_strategy, test_issue, depth_legs, reference_tickets))

        reference_cover_tickets = [
            dynamic_draw_cover_ticket(
                ticket,
                strategy_prefix=reference_strategy,
                dynamic_policy=args.dynamic_policy,
                action_lookup=action_lookup,
                samples_by_match=samples_by_match,
                model_probs_by_match=model_probs_by_match,
                market_probs_by_match=market_probs_by_match,
                require_positive_draw_edge=args.require_positive_draw_edge,
            )
            for ticket in reference_tickets
        ]
        append_settled(ticket_rows, reference_cover_tickets)

        candidate_strategy = f"confidence_{args.depth_policy}_candidate"
        candidates = make_depth_weighted_tickets(
            depth_legs,
            depth_weights=depth_weights,
            strategy=candidate_strategy,
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_candidate_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            max_leg_uses=0,
            max_ticket_overlap=0,
        )

        for profile in profiles:
            strategy = f"confidence_{args.depth_policy}_risk_{profile.name}"
            selected = select_risk_controlled_tickets(
                candidates,
                strategy=strategy,
                profile=profile,
                snapshot=args.snapshot,
                max_tickets=args.max_tickets_per_issue,
                high_odds_threshold=args.high_odds_threshold,
                extreme_score_threshold=args.extreme_score_threshold,
            )
            append_settled(ticket_rows, selected)
            coverage_rows.append(coverage_snapshot(strategy, test_issue, depth_legs, selected))
            issue_rows.append(
                risk_profile_rows(
                    test_issue,
                    strategy,
                    profile,
                    selected,
                    candidates,
                    snapshot=args.snapshot,
                    high_odds_threshold=args.high_odds_threshold,
                    extreme_score_threshold=args.extreme_score_threshold,
                )
            )

            cover_strategy_prefix = strategy
            cover_tickets = [
                dynamic_draw_cover_ticket(
                    ticket,
                    strategy_prefix=cover_strategy_prefix,
                    dynamic_policy=args.dynamic_policy,
                    action_lookup=action_lookup,
                    samples_by_match=samples_by_match,
                    model_probs_by_match=model_probs_by_match,
                    market_probs_by_match=market_probs_by_match,
                    require_positive_draw_edge=args.require_positive_draw_edge,
                )
                for ticket in selected
            ]
            append_settled(ticket_rows, cover_tickets)

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "snapshot": args.snapshot,
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "n_depth_legs": len(depth_legs),
                "n_reference_tickets": len(reference_tickets),
                "n_candidate_tickets": len(candidates),
            }
        )

    summary = summarize_tickets(ticket_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    profit_rows = issue_profit_rows(ticket_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "issue_risk_tickets.csv", ticket_rows)
    write_csv(out / "issue_risk_summary.csv", summary)
    write_csv(out / "issue_risk_profit.csv", profit_rows)
    write_csv(out / "issue_risk_profiles.csv", issue_rows)
    write_csv(out / "issue_risk_coverage.csv", coverage_rows)
    write_csv(out / "issue_risk_windows.csv", window_rows)

    report = [
        "# N=7 issue-level risk-control evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Depth policy: `{args.depth_policy}`",
        f"- Dynamic draw policy: `{args.dynamic_policy}`",
        f"- Candidate tickets per issue: `{args.max_candidate_tickets_per_issue}`",
        f"- Risk profiles: `{args.risk_profiles}`",
        f"- High odds threshold: `{args.high_odds_threshold}`",
        f"- Extreme score threshold: `{args.extreme_score_threshold}`",
        "",
        "## Strategy Summary",
        md_table(compact_summary(summary)),
        "## Risk Profiles",
        md_table(issue_rows[:80]),
        "",
        "## Files",
        "",
        "- `issue_risk_summary.csv`",
        "- `issue_risk_tickets.csv`",
        "- `issue_risk_profit.csv`",
        "- `issue_risk_profiles.csv`",
        "- `issue_risk_coverage.csv`",
        "- `issue_risk_windows.csv`",
        "",
    ]
    (out / "issue_risk_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'issue_risk_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_issue_risk_control"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--max-candidate-tickets-per-issue", type=int, default=80)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--reference-max-leg-uses", type=int, default=8)
    parser.add_argument("--reference-max-ticket-overlap", type=int, default=6)
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
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--dynamic-policy", default="model_draw_ratio_t0.55_k2")
    parser.add_argument("--require-positive-draw-edge", action="store_true")
    parser.add_argument("--risk-profiles", default="loose,medium,strict")
    parser.add_argument("--high-odds-threshold", type=float, default=6.0)
    parser.add_argument("--extreme-score-threshold", type=float, default=2.0)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
