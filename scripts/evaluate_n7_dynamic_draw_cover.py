#!/usr/bin/env python3
"""Evaluate dynamic draw-cover count for N=7 q/confidence-depth tickets."""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import (
    make_depth_weighted_tickets,
    model_probabilities,
    transform_legs_for_depth,
)
from scripts.evaluate_n7_depth_draw_cover import (
    compact_summary,
    coverage_snapshot,
    group_samples_by_issue,
    issue_profit_rows,
    renamed_draw_cover_ticket,
)
from scripts.evaluate_n7_draw_cover import COVER_ACTION, DRAW_INDEX, candidate_score
from scripts.walkforward_beidan_result_model_eval import build_samples, load_match_extras, market_probs
from scripts.walkforward_beidan_strategy_eval import (
    Leg,
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


def parse_dynamic_policy(raw: str) -> tuple[str, float, int]:
    match = re.fullmatch(r"([a-zA-Z0-9_]+)_t([0-9.]+)_k([0-9]+)", raw.strip())
    if not match:
        raise ValueError(f"dynamic policy must look like model_draw_ratio_t0.65_k3: {raw}")
    return match.group(1), float(match.group(2)), int(match.group(3))


def append_settled(ticket_rows: list[dict[str, object]], tickets: list[Ticket]) -> None:
    ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)


def dynamic_draw_cover_ticket(
    ticket: Ticket,
    *,
    strategy_prefix: str,
    dynamic_policy: str,
    action_lookup: dict[tuple[int, str], object],
    samples_by_match: dict[int, object],
    model_probs_by_match: dict[int, np.ndarray],
    market_probs_by_match: dict[int, np.ndarray],
    require_positive_draw_edge: bool,
) -> Ticket:
    score_policy, threshold, max_cover = parse_dynamic_policy(dynamic_policy)
    candidates = []
    for idx, leg in enumerate(ticket.legs):
        target_action = COVER_ACTION.get(leg.row.action_code)
        if not target_action:
            continue
        target_row = action_lookup.get((leg.row.match_id, target_action))
        sample = samples_by_match.get(leg.row.match_id)
        model_probs = model_probs_by_match.get(leg.row.match_id)
        market = market_probs_by_match.get(leg.row.match_id)
        if target_row is None or sample is None or model_probs is None or market is None:
            continue
        draw_odds = float(sample.rows["1"].euro_final_odds or 0.0)
        draw_edge = float(model_probs[DRAW_INDEX]) * 0.65 * draw_odds - 1.0
        if require_positive_draw_edge and draw_edge <= 0:
            continue
        score = candidate_score(score_policy, leg, sample, model_probs, market)
        if score < threshold:
            continue
        candidates.append((score, idx, target_row, float(model_probs[DRAW_INDEX]), float(market[DRAW_INDEX]), draw_edge))

    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen = {
        idx: (score, target_row, model_p, market_p, draw_edge)
        for score, idx, target_row, model_p, market_p, draw_edge in candidates[:max_cover]
    }
    legs = list(ticket.legs)
    for idx, (score, target_row, model_p, market_p, draw_edge) in chosen.items():
        old = legs[idx]
        legs[idx] = Leg(
            row=target_row,
            strategy=f"dynamic_draw_cover_{dynamic_policy}",
            score_factor=old.score_factor,
            p_hat=min(0.999, old.p_hat + model_p),
            source_rule=(
                f"{old.source_rule};dynamic_draw_cover={old.row.action_code}->{target_row.action_code};"
                f"score_policy={score_policy};score={score:.4f};threshold={threshold:.4f};"
                f"model_p_draw={model_p:.4f};market_p_draw={market_p:.4f};draw_edge={draw_edge:.4f}"
            ),
            is_full_cover=False,
        )
    suffix = "_posedge" if require_positive_draw_edge else ""
    return replace(ticket, strategy=f"{strategy_prefix}__draw_dynamic_{dynamic_policy}{suffix}", legs=tuple(legs))


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    depth_policies = parse_strings(args.depth_policies)
    dynamic_policies = parse_strings(args.dynamic_policies)
    ticket_rows: list[dict[str, object]] = []
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
        coverage_rows.append(coverage_snapshot("baseline_q_high_sp", test_issue, q_legs, base_tickets))

        fixed_base_cover_tickets = [
            renamed_draw_cover_ticket(
                ticket,
                strategy_prefix="baseline_q_high_sp",
                draw_policy=args.fixed_draw_policy,
                cover_count=args.fixed_cover_count,
                action_lookup=action_lookup,
                samples_by_match=samples_by_match,
                model_probs_by_match=model_probs_by_match,
                market_probs_by_match=market_probs_by_match,
                require_positive_draw_edge=args.require_positive_draw_edge,
            )
            for ticket in base_tickets
        ]
        append_settled(ticket_rows, fixed_base_cover_tickets)
        for dynamic_policy in dynamic_policies:
            tickets = [
                dynamic_draw_cover_ticket(
                    ticket,
                    strategy_prefix="baseline_q_high_sp",
                    dynamic_policy=dynamic_policy,
                    action_lookup=action_lookup,
                    samples_by_match=samples_by_match,
                    model_probs_by_match=model_probs_by_match,
                    market_probs_by_match=market_probs_by_match,
                    require_positive_draw_edge=args.require_positive_draw_edge,
                )
                for ticket in base_tickets
            ]
            append_settled(ticket_rows, tickets)

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
            coverage_rows.append(coverage_snapshot(depth_strategy, test_issue, depth_legs, depth_tickets))
            depth_counts[depth_strategy] = len(depth_tickets)

            fixed_depth_cover_tickets = [
                renamed_draw_cover_ticket(
                    ticket,
                    strategy_prefix=depth_strategy,
                    draw_policy=args.fixed_draw_policy,
                    cover_count=args.fixed_cover_count,
                    action_lookup=action_lookup,
                    samples_by_match=samples_by_match,
                    model_probs_by_match=model_probs_by_match,
                    market_probs_by_match=market_probs_by_match,
                    require_positive_draw_edge=args.require_positive_draw_edge,
                )
                for ticket in depth_tickets
            ]
            append_settled(ticket_rows, fixed_depth_cover_tickets)
            for dynamic_policy in dynamic_policies:
                tickets = [
                    dynamic_draw_cover_ticket(
                        ticket,
                        strategy_prefix=depth_strategy,
                        dynamic_policy=dynamic_policy,
                        action_lookup=action_lookup,
                        samples_by_match=samples_by_match,
                        model_probs_by_match=model_probs_by_match,
                        market_probs_by_match=market_probs_by_match,
                        require_positive_draw_edge=args.require_positive_draw_edge,
                    )
                    for ticket in depth_tickets
                ]
                append_settled(ticket_rows, tickets)

        row = {
            "test_issue": test_issue,
            "train_start_issue": train_issues[0],
            "train_end_issue": train_issues[-1],
            "snapshot": args.snapshot,
            "n_train_matches": len(train_samples),
            "n_test_matches": len(test_samples),
            "n_q_legs": len(q_legs),
            "n_base_tickets": len(base_tickets),
        }
        for strategy, count in depth_counts.items():
            row[f"n_{strategy}_tickets"] = count
        window_rows.append(row)

    summary = summarize_tickets(ticket_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    issue_rows = issue_profit_rows(ticket_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "dynamic_draw_tickets.csv", ticket_rows)
    write_csv(out / "dynamic_draw_summary.csv", summary)
    write_csv(out / "dynamic_draw_issue_profit.csv", issue_rows)
    write_csv(out / "dynamic_draw_coverage.csv", coverage_rows)
    write_csv(out / "dynamic_draw_windows.csv", window_rows)

    report = [
        "# N=7 dynamic draw-cover evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Depth policies: `{args.depth_policies}`",
        f"- Fixed draw cover: `{args.fixed_draw_policy}`, k=`{args.fixed_cover_count}`",
        f"- Dynamic policies: `{args.dynamic_policies}`",
        "",
        "## Strategy Summary",
        md_table(compact_summary(summary)),
        "## Coverage",
        md_table(coverage_rows[:80]),
        "",
        "## Files",
        "",
        "- `dynamic_draw_summary.csv`",
        "- `dynamic_draw_tickets.csv`",
        "- `dynamic_draw_issue_profit.csv`",
        "- `dynamic_draw_coverage.csv`",
        "- `dynamic_draw_windows.csv`",
        "",
    ]
    (out / "dynamic_draw_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'dynamic_draw_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_dynamic_draw_cover"))
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
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--depth-policies", default="depth_constrained_hybrid")
    parser.add_argument("--fixed-draw-policy", default="model_draw_ratio")
    parser.add_argument("--fixed-cover-count", type=int, default=2)
    parser.add_argument(
        "--dynamic-policies",
        default="model_draw_ratio_t0.55_k2,model_draw_ratio_t0.65_k2,model_draw_ratio_t0.75_k2,model_draw_ratio_t0.55_k3,model_draw_ratio_t0.65_k3,model_draw_ratio_t0.75_k3",
    )
    parser.add_argument("--require-positive-draw-edge", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
