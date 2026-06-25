#!/usr/bin/env python3
"""Evaluate soft issue-level penalties on the current N=7 main strategy."""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import make_depth_weighted_tickets, model_probabilities, transform_legs_for_depth
from scripts.evaluate_n7_depth_draw_cover import compact_summary, coverage_snapshot, group_samples_by_issue, issue_profit_rows
from scripts.evaluate_n7_dynamic_draw_cover import dynamic_draw_cover_ticket
from scripts.evaluate_n7_issue_risk_control import leg_proxy_odds, ticket_quality
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
    summarize_tickets,
    train_q_model,
    write_csv,
)


@dataclass(frozen=True)
class SoftProfile:
    name: str
    base_weight: float
    rank_penalty: float
    leg_reuse_penalty: float
    match_reuse_penalty: float
    overlap_penalty: float
    high_odds_penalty: float
    extreme_score_penalty: float
    action_share_target: float
    action_share_penalty: float


PROFILES = {
    "soft_light": SoftProfile(
        name="soft_light",
        base_weight=1.00,
        rank_penalty=0.10,
        leg_reuse_penalty=0.08,
        match_reuse_penalty=0.04,
        overlap_penalty=0.08,
        high_odds_penalty=0.05,
        extreme_score_penalty=0.06,
        action_share_target=0.68,
        action_share_penalty=0.80,
    ),
    "soft_medium": SoftProfile(
        name="soft_medium",
        base_weight=0.95,
        rank_penalty=0.16,
        leg_reuse_penalty=0.13,
        match_reuse_penalty=0.07,
        overlap_penalty=0.14,
        high_odds_penalty=0.09,
        extreme_score_penalty=0.11,
        action_share_target=0.62,
        action_share_penalty=1.20,
    ),
    "soft_strong": SoftProfile(
        name="soft_strong",
        base_weight=0.90,
        rank_penalty=0.22,
        leg_reuse_penalty=0.18,
        match_reuse_penalty=0.10,
        overlap_penalty=0.20,
        high_odds_penalty=0.14,
        extreme_score_penalty=0.16,
        action_share_target=0.58,
        action_share_penalty=1.70,
    ),
}


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def append_settled(ticket_rows: list[dict[str, object]], tickets: list[Ticket]) -> None:
    ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)


def ticket_counts(ticket: Ticket, *, snapshot: str, high_odds_threshold: float, extreme_score_threshold: float) -> dict[str, object]:
    leg_ids = set()
    match_ids = set()
    actions: Counter[str] = Counter()
    high_odds = 0
    extreme_score = 0
    for leg in ticket.legs:
        leg_ids.add(leg.leg_id)
        match_ids.add(leg.row.match_id)
        actions[leg.row.action_code] += 1
        if leg_proxy_odds(leg, snapshot) >= high_odds_threshold:
            high_odds += 1
        if leg.score_factor >= extreme_score_threshold:
            extreme_score += 1
    return {
        "leg_ids": leg_ids,
        "match_ids": match_ids,
        "actions": actions,
        "high_odds": high_odds,
        "extreme_score": extreme_score,
    }


def normalized_quality(candidates: list[Ticket]) -> dict[int, float]:
    qualities = np.asarray([ticket_quality(ticket) / max(1, ticket.n_legs) for ticket in candidates], dtype=float)
    if len(qualities) == 0:
        return {}
    std = float(np.std(qualities))
    if std <= 1e-9:
        return {idx: 0.0 for idx in range(len(candidates))}
    mean = float(np.mean(qualities))
    return {idx: float((quality - mean) / std) for idx, quality in enumerate(qualities)}


def action_share_penalty(
    action_counts: Counter[str],
    ticket_actions: Counter[str],
    *,
    selected_count: int,
    n_legs: int,
    profile: SoftProfile,
) -> float:
    projected = action_counts.copy()
    projected.update(ticket_actions)
    total = (selected_count + 1) * n_legs
    max_share = max((count / total for count in projected.values()), default=0.0)
    excess = max(0.0, max_share - profile.action_share_target)
    return profile.action_share_penalty * excess * excess * n_legs


def adjusted_candidate_score(
    *,
    idx: int,
    ticket: Ticket,
    candidates_count: int,
    quality_z: dict[int, float],
    counts: dict[str, object],
    selected_leg_sets: list[set[str]],
    leg_uses: Counter[str],
    match_uses: Counter[int],
    action_counts: Counter[str],
    selected_count: int,
    profile: SoftProfile,
) -> float:
    leg_ids = counts["leg_ids"]
    match_ids = counts["match_ids"]
    actions = counts["actions"]
    overlap = max((len(leg_ids & previous) for previous in selected_leg_sets), default=0)
    leg_reuse = sum(leg_uses[leg_id] for leg_id in leg_ids)
    match_reuse = sum(match_uses[match_id] for match_id in match_ids)
    rank_frac = idx / max(1, candidates_count - 1)

    penalty = (
        profile.rank_penalty * rank_frac
        + profile.leg_reuse_penalty * leg_reuse
        + profile.match_reuse_penalty * match_reuse
        + profile.overlap_penalty * overlap
        + profile.high_odds_penalty * int(counts["high_odds"])
        + profile.extreme_score_penalty * int(counts["extreme_score"])
        + action_share_penalty(
            action_counts,
            actions,
            selected_count=selected_count,
            n_legs=ticket.n_legs,
            profile=profile,
        )
    )
    return profile.base_weight * quality_z.get(idx, 0.0) - penalty


def select_soft_penalty_tickets(
    candidates: list[Ticket],
    *,
    strategy: str,
    profile: SoftProfile,
    snapshot: str,
    max_tickets: int,
    high_odds_threshold: float,
    extreme_score_threshold: float,
) -> tuple[list[Ticket], list[dict[str, object]]]:
    counts_by_idx = [
        ticket_counts(
            ticket,
            snapshot=snapshot,
            high_odds_threshold=high_odds_threshold,
            extreme_score_threshold=extreme_score_threshold,
        )
        for ticket in candidates
    ]
    quality_z = normalized_quality(candidates)
    remaining = set(range(len(candidates)))
    selected: list[Ticket] = []
    selected_leg_sets: list[set[str]] = []
    leg_uses: Counter[str] = Counter()
    match_uses: Counter[int] = Counter()
    action_counts: Counter[str] = Counter()
    selection_rows: list[dict[str, object]] = []

    while remaining and len(selected) < max_tickets:
        scored = [
            (
                adjusted_candidate_score(
                    idx=idx,
                    ticket=candidates[idx],
                    candidates_count=len(candidates),
                    quality_z=quality_z,
                    counts=counts_by_idx[idx],
                    selected_leg_sets=selected_leg_sets,
                    leg_uses=leg_uses,
                    match_uses=match_uses,
                    action_counts=action_counts,
                    selected_count=len(selected),
                    profile=profile,
                ),
                idx,
            )
            for idx in remaining
        ]
        best_score, best_idx = max(scored)
        remaining.remove(best_idx)
        ticket = candidates[best_idx]
        counts = counts_by_idx[best_idx]
        ticket_idx = len(selected) + 1
        selected.append(replace(ticket, strategy=strategy, ticket_idx=ticket_idx))
        selected_leg_sets.append(set(counts["leg_ids"]))
        for leg_id in counts["leg_ids"]:
            leg_uses[leg_id] += 1
        for match_id in counts["match_ids"]:
            match_uses[match_id] += 1
        action_counts.update(counts["actions"])
        selection_rows.append(
            {
                "strategy": strategy,
                "issue": ticket.issue,
                "profile": profile.name,
                "ticket_idx": ticket_idx,
                "candidate_idx": best_idx + 1,
                "candidate_quality_z": quality_z.get(best_idx, 0.0),
                "selected_score": best_score,
                "high_odds_legs": counts["high_odds"],
                "extreme_score_legs": counts["extreme_score"],
                "max_leg_use_after": max(leg_uses.values()) if leg_uses else 0,
            }
        )
    return selected, selection_rows


def issue_profile_row(
    issue: str,
    strategy: str,
    profile: SoftProfile,
    selected: list[Ticket],
    candidates_count: int,
    *,
    snapshot: str,
    high_odds_threshold: float,
    extreme_score_threshold: float,
) -> dict[str, object]:
    leg_uses: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    high_odds_counts = []
    extreme_score_counts = []
    overlaps = []
    prev_sets: list[set[str]] = []
    for ticket in selected:
        counts = ticket_counts(
            ticket,
            snapshot=snapshot,
            high_odds_threshold=high_odds_threshold,
            extreme_score_threshold=extreme_score_threshold,
        )
        leg_ids = counts["leg_ids"]
        overlaps.extend(len(leg_ids & previous) for previous in prev_sets)
        prev_sets.append(set(leg_ids))
        high_odds_counts.append(int(counts["high_odds"]))
        extreme_score_counts.append(int(counts["extreme_score"]))
        action_counts.update(counts["actions"])
        for leg_id in leg_ids:
            leg_uses[leg_id] += 1
    total_legs = sum(action_counts.values())
    return {
        "strategy": strategy,
        "issue": issue,
        "profile": profile.name,
        "candidate_tickets": candidates_count,
        "selected_tickets": len(selected),
        "distinct_legs_used": len(leg_uses),
        "max_leg_uses": max(leg_uses.values()) if leg_uses else 0,
        "avg_pair_overlap": sum(overlaps) / len(overlaps) if overlaps else 0.0,
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

    profiles = [PROFILES[name] for name in parse_strings(args.soft_profiles)]
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    ticket_rows: list[dict[str, object]] = []
    profile_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []
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

        candidates = make_depth_weighted_tickets(
            depth_legs,
            depth_weights=depth_weights,
            strategy=f"confidence_{args.depth_policy}_candidate",
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
            strategy = f"confidence_{args.depth_policy}_{profile.name}"
            selected, selected_rows = select_soft_penalty_tickets(
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
            profile_rows.append(
                issue_profile_row(
                    test_issue,
                    strategy,
                    profile,
                    selected,
                    len(candidates),
                    snapshot=args.snapshot,
                    high_odds_threshold=args.high_odds_threshold,
                    extreme_score_threshold=args.extreme_score_threshold,
                )
            )
            selection_rows.extend(selected_rows)

            cover_tickets = [
                dynamic_draw_cover_ticket(
                    ticket,
                    strategy_prefix=strategy,
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
    write_csv(out / "issue_soft_tickets.csv", ticket_rows)
    write_csv(out / "issue_soft_summary.csv", summary)
    write_csv(out / "issue_soft_profit.csv", profit_rows)
    write_csv(out / "issue_soft_profiles.csv", profile_rows)
    write_csv(out / "issue_soft_selection.csv", selection_rows)
    write_csv(out / "issue_soft_coverage.csv", coverage_rows)
    write_csv(out / "issue_soft_windows.csv", window_rows)

    report = [
        "# N=7 issue-level soft-penalty evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Depth policy: `{args.depth_policy}`",
        f"- Dynamic draw policy: `{args.dynamic_policy}`",
        f"- Candidate tickets per issue: `{args.max_candidate_tickets_per_issue}`",
        f"- Soft profiles: `{args.soft_profiles}`",
        "",
        "## Strategy Summary",
        md_table(compact_summary(summary)),
        "## Soft Profiles",
        md_table(profile_rows[:80]),
        "",
        "## Files",
        "",
        "- `issue_soft_summary.csv`",
        "- `issue_soft_tickets.csv`",
        "- `issue_soft_profit.csv`",
        "- `issue_soft_profiles.csv`",
        "- `issue_soft_selection.csv`",
        "- `issue_soft_coverage.csv`",
        "- `issue_soft_windows.csv`",
        "",
    ]
    (out / "issue_soft_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'issue_soft_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_issue_soft_penalty"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--max-candidate-tickets-per-issue", type=int, default=100)
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
    parser.add_argument("--soft-profiles", default="soft_light,soft_medium,soft_strong")
    parser.add_argument("--high-odds-threshold", type=float, default=6.0)
    parser.add_argument("--extreme-score-threshold", type=float, default=2.0)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
