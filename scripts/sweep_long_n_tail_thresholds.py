#!/usr/bin/env python3
"""Sweep high-confidence thresholds for long-N tail tickets."""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_long_n_tail import TailProfile, profile_passes, summarize_variable
from scripts.evaluate_n7_confidence_coverage import confidence_metrics, group_samples_by_issue, model_probabilities
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
    train_q_model,
    write_csv,
)


def parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def floor_name(value: float) -> str:
    if value <= 0:
        return "ph0"
    exponent = int(round(-math.log10(value)))
    coefficient = int(round(value * (10**exponent)))
    return f"ph{coefficient}e{exponent}"


def make_profiles(args: argparse.Namespace) -> list[TailProfile]:
    profiles: list[TailProfile] = []
    for min_p in parse_floats(args.min_p_values):
        for margin in parse_floats(args.margin_values):
            for ratio in parse_floats(args.ratio_values):
                for min_n in parse_ints(args.min_n_values):
                    for cap_n in parse_ints(args.cap_n_values):
                        if args.exact_n_only and cap_n != min_n:
                            continue
                        if cap_n < min_n:
                            continue
                        for hit_floor in parse_floats(args.hit_prob_floors):
                            name = (
                                f"p{int(round(min_p * 100)):02d}_"
                                f"r{int(round(ratio * 100)):03d}_"
                                f"m{int(round(margin * 100)):02d}_"
                                f"n{min_n}_cap{cap_n}_{floor_name(hit_floor)}"
                            )
                            profiles.append(
                                TailProfile(
                                    name,
                                    min_n=min_n,
                                    min_selected_p=min_p,
                                    min_top_p=min_p,
                                    min_ratio=ratio,
                                    min_margin=margin,
                                    min_score_factor=args.min_score_factor,
                                    max_n=cap_n,
                                    min_pred_hit_prob=hit_floor,
                                )
                            )
                    if args.include_uncapped:
                        for hit_floor in parse_floats(args.hit_prob_floors):
                            name = (
                                f"p{int(round(min_p * 100)):02d}_"
                                f"r{int(round(ratio * 100)):03d}_"
                                f"m{int(round(margin * 100)):02d}_"
                                f"n{min_n}_all_{floor_name(hit_floor)}"
                            )
                            profiles.append(
                                TailProfile(
                                    name,
                                    min_n=min_n,
                                    min_selected_p=min_p,
                                    min_top_p=min_p,
                                    min_ratio=ratio,
                                    min_margin=margin,
                                    min_score_factor=args.min_score_factor,
                                    max_n=None,
                                    min_pred_hit_prob=hit_floor,
                                )
                            )
    return profiles


def convert_leg_for_profile(leg: Leg, metrics: dict[str, float], profile: TailProfile) -> Leg:
    score = leg.score_factor * math.sqrt(max(0.01, metrics["model_market_ratio"]))
    return replace(
        leg,
        strategy=f"long_tail_{profile.name}",
        score_factor=score,
        p_hat=max(0.001, min(0.999, metrics["selected_model_p"])),
        source_rule=(
            f"{leg.source_rule};long_tail={profile.name};"
            f"model_p={metrics['selected_model_p']:.4f};market_p={metrics['selected_market_p']:.4f};"
            f"ratio={metrics['model_market_ratio']:.4f};top_p={metrics['top_p']:.4f};"
            f"margin={metrics['margin']:.4f}"
        ),
    )


def build_ticket_from_candidates(
    *,
    issue: str,
    train_start_issue: str,
    train_end_issue: str,
    profile: TailProfile,
    candidate_data: list[tuple[Leg, dict[str, float]]],
) -> tuple[Ticket | None, int]:
    candidates: list[tuple[float, Leg]] = []
    for leg, metrics in candidate_data:
        if not profile_passes(profile, leg, metrics):
            continue
        converted = convert_leg_for_profile(leg, metrics, profile)
        sort_score = (
            math.log(max(converted.score_factor, 1e-9))
            + math.log(max(converted.p_hat, 1e-9))
            + 0.25 * metrics["margin"]
        )
        candidates.append((sort_score, converted))

    candidates.sort(key=lambda x: x[0], reverse=True)
    candidate_count = len(candidates)
    legs = [leg for _, leg in candidates]
    if profile.max_n is not None:
        legs = legs[: profile.max_n]
    if len(legs) < profile.min_n:
        return None, candidate_count
    if len({leg.row.match_id for leg in legs}) < len(legs):
        return None, candidate_count
    pred_hit_prob = math.prod(max(0.0, min(1.0, leg.p_hat)) for leg in legs)
    if pred_hit_prob < profile.min_pred_hit_prob:
        return None, candidate_count
    return (
        Ticket(
            strategy=f"long_tail_{profile.name}",
            issue=issue,
            n_legs=len(legs),
            ticket_idx=1,
            train_start_issue=train_start_issue,
            train_end_issue=train_end_issue,
            legs=tuple(legs),
        ),
        candidate_count,
    )


def add_coverage_summary(coverage_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: {"issues": 0, "tickets": 0, "candidate_sum": 0, "max_candidates": 0})
    for row in coverage_rows:
        g = grouped[str(row["strategy"])]
        g["issues"] += 1
        g["tickets"] += int(row["ticket_created"])
        g["candidate_sum"] += int(row["candidate_count"])
        g["max_candidates"] = max(g["max_candidates"], int(row["candidate_count"]))
    out = []
    for strategy, g in sorted(grouped.items()):
        out.append(
            {
                "strategy": strategy,
                "issues": g["issues"],
                "tickets": g["tickets"],
                "ticket_rate": g["tickets"] / g["issues"] if g["issues"] else 0.0,
                "avg_candidates": g["candidate_sum"] / g["issues"] if g["issues"] else 0.0,
                "max_candidates": g["max_candidates"],
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    profiles = make_profiles(args)
    threshold = break_even_factor(args.reference_n) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
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
            min_proxy_odds=args.min_proxy_odds,
            max_proxy_odds=args.max_proxy_odds,
            min_score_factor=threshold,
        )
        probs = model_probabilities(args, train_samples, test_samples)
        market = market_probs(test_samples)
        probs_by_match = {sample.match_id: probs[i] for i, sample in enumerate(test_samples)}
        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}

        candidate_data: list[tuple[Leg, dict[str, float]]] = []
        for leg in q_legs:
            probs_row = probs_by_match.get(leg.row.match_id)
            market_row = market_by_match.get(leg.row.match_id)
            if probs_row is None or market_row is None:
                continue
            candidate_data.append((leg, confidence_metrics(leg, probs_row, market_row)))

        created = 0
        for profile in profiles:
            ticket, candidate_count = build_ticket_from_candidates(
                issue=test_issue,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                profile=profile,
                candidate_data=candidate_data,
            )
            coverage_row = {
                "issue": test_issue,
                "strategy": f"long_tail_{profile.name}",
                "candidate_count": candidate_count,
                "ticket_created": 0,
                "n_legs": 0,
            }
            if ticket is not None:
                settled = settle_ticket(ticket)
                ticket_rows.append(settled)
                created += 1
                coverage_row.update(
                    {
                        "ticket_created": 1,
                        "n_legs": ticket.n_legs,
                        "pred_hit_prob": settled["pred_hit_prob"],
                        "pred_ev_per_stake": settled["pred_ev_per_stake"],
                        "hit": settled["hit"],
                        "profit": settled["profit_units"],
                    }
                )
            coverage_rows.append(coverage_row)

        window_rows.append(
            {
                "issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_q_legs": len(q_legs),
                "profiles": len(profiles),
                "tail_tickets_created": created,
            }
        )

    summary = summarize_variable(ticket_rows)
    coverage_summary = add_coverage_summary(coverage_rows)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "threshold_sweep_tickets.csv", ticket_rows)
    write_csv(out / "threshold_sweep_summary.csv", summary)
    write_csv(out / "threshold_sweep_coverage.csv", coverage_rows)
    write_csv(out / "threshold_sweep_coverage_summary.csv", coverage_summary)
    write_csv(out / "threshold_sweep_windows.csv", window_rows)

    interesting = [
        row
        for row in summary
        if int(row["tickets"]) >= args.report_min_tickets
        or int(row["hits"]) > 0
    ][: args.report_rows]
    report = [
        "# Long-N threshold sweep",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Profiles: `{len(profiles)}`",
        f"- min_p: `{args.min_p_values}`",
        f"- margins: `{args.margin_values}`",
        f"- ratios: `{args.ratio_values}`",
        f"- min_n: `{args.min_n_values}`",
        f"- cap_n: `{args.cap_n_values}`",
        f"- hit floors: `{args.hit_prob_floors}`",
        "",
        "## Interesting Summary",
        md_table(interesting),
        "",
        "## Files",
        "",
        "- `threshold_sweep_summary.csv`",
        "- `threshold_sweep_tickets.csv`",
        "- `threshold_sweep_coverage.csv`",
        "- `threshold_sweep_coverage_summary.csv`",
        "- `threshold_sweep_windows.csv`",
        "",
    ]
    (out / "threshold_sweep_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'threshold_sweep_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows across {len(profiles)} profiles")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/long_n_tail_threshold_sweep"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--reference-n", type=int, default=7)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--min-proxy-odds", type=float, default=1.5)
    parser.add_argument("--max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--model-source", choices=("multiclass", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--min-score-factor", type=float, default=1.04)
    parser.add_argument("--min-p-values", default="0.45,0.50,0.55,0.60")
    parser.add_argument("--margin-values", default="0.05,0.10,0.15")
    parser.add_argument("--ratio-values", default="1.00,1.10")
    parser.add_argument("--min-n-values", default="8,9,10,12")
    parser.add_argument("--cap-n-values", default="10,12,14")
    parser.add_argument("--exact-n-only", action="store_true")
    parser.add_argument("--hit-prob-floors", default="0,0.0001")
    parser.add_argument("--include-uncapped", action="store_true")
    parser.add_argument("--report-min-tickets", type=int, default=10)
    parser.add_argument("--report-rows", type=int, default=80)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
