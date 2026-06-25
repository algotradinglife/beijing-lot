#!/usr/bin/env python3
"""Evaluate N=7 confidence depth + draw-cover with one-sided SP-drift penalty."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
from scripts.evaluate_n7_sp_drift_depth import (
    adjust_depth_weights,
    append_sp_eval_rows,
    sp_metric_rows,
    train_sp_drift_model,
)
from scripts.walkforward_beidan_result_model_eval import build_samples, load_match_extras, market_probs
from scripts.walkforward_beidan_strategy_eval import (
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


def append_settled(ticket_rows: list[dict[str, object]], tickets) -> None:
    ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)


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
    ticket_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    sp_eval_rows: list[dict[str, object]] = []

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
        sp_model = train_sp_drift_model(
            train_action_rows,
            snapshot=args.snapshot,
            feature_set=args.sp_feature_set,
            prior_n=args.sp_prior_n,
            min_multiplier=args.min_sp_multiplier,
            max_multiplier=args.max_sp_multiplier,
        )
        append_sp_eval_rows(sp_eval_rows, test_action_rows, sp_model, test_issue)

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

            sp_penalty_weights = adjust_depth_weights(
                depth_legs,
                depth_weights,
                sp_model=sp_model,
                alpha=args.sp_depth_alpha,
                min_weight=args.min_sp_depth_weight,
                max_weight=1.0,
            )
            sp_penalty_strategy = f"{depth_strategy}_sp_penalty"
            sp_penalty_tickets = make_depth_weighted_tickets(
                depth_legs,
                depth_weights=sp_penalty_weights,
                strategy=sp_penalty_strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                max_leg_uses=args.max_depth_leg_uses if policy.startswith("depth_constrained") else 0,
                max_ticket_overlap=args.max_depth_ticket_overlap if policy.startswith("depth_constrained") else 0,
            )
            append_settled(ticket_rows, sp_penalty_tickets)
            coverage_rows.append(coverage_snapshot(sp_penalty_strategy, test_issue, depth_legs, sp_penalty_tickets))
            depth_counts[sp_penalty_strategy] = len(sp_penalty_tickets)

            sp_penalty_cover_tickets = [
                renamed_draw_cover_ticket(
                    ticket,
                    strategy_prefix=sp_penalty_strategy,
                    draw_policy=args.draw_policy,
                    cover_count=args.cover_count,
                    action_lookup=action_lookup,
                    samples_by_match=samples_by_match,
                    model_probs_by_match=model_probs_by_match,
                    market_probs_by_match=market_probs_by_match,
                    require_positive_draw_edge=args.require_positive_draw_edge,
                )
                for ticket in sp_penalty_tickets
            ]
            append_settled(ticket_rows, sp_penalty_cover_tickets)

        row = {
            "test_issue": test_issue,
            "train_start_issue": train_issues[0],
            "train_end_issue": train_issues[-1],
            "snapshot": args.snapshot,
            "sp_feature_set": args.sp_feature_set,
            "sp_depth_alpha": args.sp_depth_alpha,
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
    sp_metrics = sp_metric_rows(sp_eval_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "sp_penalty_draw_tickets.csv", ticket_rows)
    write_csv(out / "sp_penalty_draw_summary.csv", summary)
    write_csv(out / "sp_penalty_draw_issue_profit.csv", issue_rows)
    write_csv(out / "sp_penalty_draw_coverage.csv", coverage_rows)
    write_csv(out / "sp_penalty_draw_windows.csv", window_rows)
    write_csv(out / "sp_prediction_rows.csv", sp_eval_rows)
    write_csv(out / "sp_prediction_metrics.csv", sp_metrics)

    report = [
        "# N=7 SP penalty plus draw-cover evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Depth policies: `{args.depth_policies}`",
        f"- Draw cover: `{args.draw_policy}`, k=`{args.cover_count}`",
        f"- SP feature set: `{args.sp_feature_set}`",
        f"- SP prior N: `{args.sp_prior_n}`",
        f"- SP penalty alpha: `{args.sp_depth_alpha}`",
        f"- SP depth weight clamp: `{args.min_sp_depth_weight}` to `1.0`",
        "",
        "## Strategy Summary",
        md_table(compact_summary(summary)),
        "## SP Prediction Metrics",
        md_table(sp_metrics),
        "## Coverage",
        md_table(coverage_rows[:80]),
        "",
        "## Files",
        "",
        "- `sp_penalty_draw_summary.csv`",
        "- `sp_penalty_draw_tickets.csv`",
        "- `sp_penalty_draw_issue_profit.csv`",
        "- `sp_penalty_draw_coverage.csv`",
        "- `sp_penalty_draw_windows.csv`",
        "- `sp_prediction_rows.csv`",
        "- `sp_prediction_metrics.csv`",
        "",
    ]
    (out / "sp_penalty_draw_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'sp_penalty_draw_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_sp_penalty_draw_cover"))
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
    parser.add_argument("--sp-feature-set", choices=("action_odds", "action_odds_move"), default="action_odds_move")
    parser.add_argument("--sp-prior-n", type=int, default=80)
    parser.add_argument("--min-sp-multiplier", type=float, default=0.15)
    parser.add_argument("--max-sp-multiplier", type=float, default=2.50)
    parser.add_argument("--sp-depth-alpha", type=float, default=0.10)
    parser.add_argument("--min-sp-depth-weight", type=float, default=0.60)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
