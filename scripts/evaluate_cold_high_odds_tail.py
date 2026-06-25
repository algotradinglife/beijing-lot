#!/usr/bin/env python3
"""Evaluate small-N high-odds cold tickets with rolling result probabilities."""
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

from scripts.evaluate_n7_confidence_coverage import group_samples_by_issue, model_probabilities
from scripts.evaluate_long_n_tail import summarize_variable
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras, market_probs
from scripts.walkforward_beidan_strategy_eval import (
    Leg,
    Ticket,
    break_even_factor,
    default_db_path,
    load_action_rows,
    md_table,
    settle_ticket,
    snapshot_odds_p,
    snapshot_rank_lookup,
    write_csv,
)


@dataclass(frozen=True)
class ColdProfile:
    name: str
    n_legs: int
    min_odds: float
    max_odds: float
    min_model_p: float
    min_ratio: float
    rank_min: int
    score_margin: float
    require_top2: bool


def parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def build_profiles(args: argparse.Namespace) -> list[ColdProfile]:
    profiles: list[ColdProfile] = []
    for n_legs in parse_ints(args.n_values):
        for min_odds in parse_floats(args.min_odds_values):
            for min_model_p in parse_floats(args.min_model_p_values):
                for min_ratio in parse_floats(args.min_ratio_values):
                    for rank_min in parse_ints(args.rank_min_values):
                        for score_margin in parse_floats(args.score_margin_values):
                            for require_top2 in ([False, True] if args.include_top2_variants else [False]):
                                name = (
                                    f"n{n_legs}_odds{min_odds:g}_"
                                    f"p{int(round(min_model_p * 100)):02d}_"
                                    f"r{int(round(min_ratio * 100)):03d}_"
                                    f"rank{rank_min}_"
                                    f"m{int(round(score_margin * 100)):02d}"
                                    f"{'_top2' if require_top2 else ''}"
                                )
                                profiles.append(
                                    ColdProfile(
                                        name=name,
                                        n_legs=n_legs,
                                        min_odds=min_odds,
                                        max_odds=args.max_odds,
                                        min_model_p=min_model_p,
                                        min_ratio=min_ratio,
                                        rank_min=rank_min,
                                        score_margin=score_margin,
                                        require_top2=require_top2,
                                    )
                                )
    return profiles


def profile_passes(profile: ColdProfile, candidate: dict[str, object]) -> bool:
    odds = float(candidate["odds"])
    model_p = float(candidate["model_p"])
    ratio = float(candidate["model_market_ratio"])
    rank = int(candidate["rank"])
    score = float(candidate["score_factor"])
    top2 = bool(candidate["top2_agree"])
    threshold = break_even_factor(profile.n_legs) + profile.score_margin
    return (
        odds >= profile.min_odds
        and odds <= profile.max_odds
        and model_p >= profile.min_model_p
        and ratio >= profile.min_ratio
        and rank >= profile.rank_min
        and score >= threshold
        and (top2 or not profile.require_top2)
    )


def make_leg(candidate: dict[str, object], profile: ColdProfile) -> Leg:
    row = candidate["row"]
    assert not isinstance(row, dict)
    return replace(
        candidate["base_leg"],
        strategy=f"cold_high_odds_{profile.name}",
        source_rule=(
            f"cold_high_odds={profile.name};"
            f"odds={float(candidate['odds']):.4f};"
            f"model_p={float(candidate['model_p']):.4f};"
            f"market_p={float(candidate['market_p']):.4f};"
            f"ratio={float(candidate['model_market_ratio']):.4f};"
            f"rank={int(candidate['rank'])};"
            f"top2={int(bool(candidate['top2_agree']))}"
        ),
    )


def build_ticket(
    *,
    issue: str,
    train_start_issue: str,
    train_end_issue: str,
    profile: ColdProfile,
    candidates: list[dict[str, object]],
) -> tuple[Ticket | None, int]:
    passing: list[dict[str, object]] = [c for c in candidates if profile_passes(profile, c)]
    passing.sort(
        key=lambda c: (
            math.log(max(float(c["score_factor"]), 1e-9))
            + 0.20 * math.log(max(float(c["odds"]), 1e-9))
            + 0.15 * math.log(max(float(c["model_market_ratio"]), 1e-9)),
            float(c["model_p"]),
        ),
        reverse=True,
    )
    used_matches: set[int] = set()
    legs: list[Leg] = []
    for candidate in passing:
        match_id = int(candidate["match_id"])
        if match_id in used_matches:
            continue
        legs.append(make_leg(candidate, profile))
        used_matches.add(match_id)
        if len(legs) >= profile.n_legs:
            break
    if len(legs) < profile.n_legs:
        return None, len({int(c["match_id"]) for c in passing})
    return (
        Ticket(
            strategy=f"cold_high_odds_{profile.name}",
            issue=issue,
            n_legs=profile.n_legs,
            ticket_idx=1,
            train_start_issue=train_start_issue,
            train_end_issue=train_end_issue,
            legs=tuple(legs),
        ),
        len({int(c["match_id"]) for c in passing}),
    )


def issue_rows(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: {"tickets": 0, "hits": 0, "stake": 0.0, "profit": 0.0})
    for row in ticket_rows:
        key = (str(row["strategy"]), str(row["issue"]))
        g = grouped[key]
        g["tickets"] += 1
        g["hits"] += int(row["hit"])
        g["stake"] += float(row["stake_units"])
        g["profit"] += float(row["profit_units"])
    out: list[dict[str, object]] = []
    for (strategy, issue), g in sorted(grouped.items()):
        out.append(
            {
                "strategy": strategy,
                "issue": issue,
                "tickets": g["tickets"],
                "hits": g["hits"],
                "stake": g["stake"],
                "profit": g["profit"],
                "roi": g["profit"] / g["stake"] if g["stake"] else "",
            }
        )
    return out


def coverage_summary(coverage_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: {"issues": 0, "tickets": 0, "candidate_sum": 0, "max_candidates": 0})
    for row in coverage_rows:
        g = grouped[str(row["strategy"])]
        g["issues"] += 1
        g["tickets"] += int(row["ticket_created"])
        g["candidate_sum"] += int(row["candidate_matches"])
        g["max_candidates"] = max(g["max_candidates"], int(row["candidate_matches"]))
    out: list[dict[str, object]] = []
    for strategy, g in sorted(grouped.items()):
        out.append(
            {
                "strategy": strategy,
                "issues": g["issues"],
                "tickets": g["tickets"],
                "ticket_rate": g["tickets"] / g["issues"] if g["issues"] else 0.0,
                "avg_candidate_matches": g["candidate_sum"] / g["issues"] if g["issues"] else 0.0,
                "max_candidate_matches": g["max_candidates"],
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    profiles = build_profiles(args)

    ticket_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        train_samples = [sample for issue in train_issues for sample in samples_by_issue.get(issue, [])]
        test_samples = samples_by_issue.get(test_issue, [])
        if len(train_samples) < args.min_train_matches or not test_samples:
            continue

        probs = model_probabilities(args, train_samples, test_samples)
        market = market_probs(test_samples)
        rank_lookup = snapshot_rank_lookup([row for sample in test_samples for row in sample.rows.values()], args.snapshot)
        candidates: list[dict[str, object]] = []
        action_counter: Counter[str] = Counter()
        for sample_idx, sample in enumerate(test_samples):
            ranked = np.argsort(-probs[sample_idx])
            top2 = {int(ranked[0]), int(ranked[1])}
            for outcome_idx, code in enumerate(OUTCOMES):
                row = sample.rows[code]
                odds, _ = snapshot_odds_p(row, args.snapshot)
                if odds is None or odds <= 1.0:
                    continue
                model_p = float(probs[sample_idx, outcome_idx])
                market_p = float(market[sample_idx, outcome_idx])
                ratio = model_p / max(market_p, 1e-9)
                score = model_p * float(odds)
                rank = rank_lookup.get((sample.match_id, code), row.euro_final_rank or 0)
                if not rank:
                    continue
                leg = Leg(
                    row=row,
                    strategy="cold_high_odds_candidate",
                    score_factor=score,
                    p_hat=max(0.001, min(0.999, model_p)),
                    source_rule="cold_high_odds_candidate",
                )
                candidates.append(
                    {
                        "match_id": sample.match_id,
                        "action_code": code,
                        "row": row,
                        "base_leg": leg,
                        "odds": float(odds),
                        "model_p": model_p,
                        "market_p": market_p,
                        "model_market_ratio": ratio,
                        "score_factor": score,
                        "rank": int(rank),
                        "top2_agree": outcome_idx in top2,
                    }
                )
                action_counter[code] += 1

        created = 0
        for profile in profiles:
            ticket, candidate_matches = build_ticket(
                issue=test_issue,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                profile=profile,
                candidates=candidates,
            )
            coverage_row = {
                "issue": test_issue,
                "strategy": f"cold_high_odds_{profile.name}",
                "candidate_matches": candidate_matches,
                "ticket_created": 0,
                "n_legs": profile.n_legs,
            }
            if ticket is not None:
                settled = settle_ticket(ticket)
                ticket_rows.append(settled)
                created += 1
                coverage_row.update(
                    {
                        "ticket_created": 1,
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
                "test_matches": len(test_samples),
                "raw_candidates": len(candidates),
                "raw_candidate_matches": len({int(c["match_id"]) for c in candidates}),
                "raw_action_mix": ";".join(f"{k}:{v}" for k, v in sorted(action_counter.items())),
                "profiles": len(profiles),
                "tickets_created": created,
            }
        )

    summary = summarize_variable(ticket_rows)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "cold_tail_tickets.csv", ticket_rows)
    write_csv(out / "cold_tail_summary.csv", summary)
    write_csv(out / "cold_tail_issue_profit.csv", issue_rows(ticket_rows))
    write_csv(out / "cold_tail_coverage.csv", coverage_rows)
    write_csv(out / "cold_tail_coverage_summary.csv", coverage_summary(coverage_rows))
    write_csv(out / "cold_tail_windows.csv", window_rows)

    interesting = [
        row
        for row in summary
        if int(row["hits"]) > 0
        or int(row["tickets"]) >= args.report_min_tickets
    ][: args.report_rows]
    report = [
        "# Cold high-odds small-N tail evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Profiles: `{len(profiles)}`",
        f"- N values: `{args.n_values}`",
        f"- Min odds: `{args.min_odds_values}`",
        f"- Max odds: `{args.max_odds}`",
        f"- Min model p: `{args.min_model_p_values}`",
        f"- Min model/market ratio: `{args.min_ratio_values}`",
        f"- Rank min: `{args.rank_min_values}`",
        "",
        "## Interesting Summary",
        md_table(interesting),
        "",
        "## Files",
        "",
        "- `cold_tail_summary.csv`",
        "- `cold_tail_tickets.csv`",
        "- `cold_tail_issue_profit.csv`",
        "- `cold_tail_coverage.csv`",
        "- `cold_tail_coverage_summary.csv`",
        "- `cold_tail_windows.csv`",
        "",
    ]
    (out / "cold_tail_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'cold_tail_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows across {len(profiles)} profiles")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/cold_high_odds_tail"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--model-source", choices=("multiclass", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--n-values", default="2,3,4,5,6")
    parser.add_argument("--min-odds-values", default="3,4,5")
    parser.add_argument("--max-odds", type=float, default=20.0)
    parser.add_argument("--min-model-p-values", default="0.08,0.12,0.16")
    parser.add_argument("--min-ratio-values", default="1.00,1.10,1.25")
    parser.add_argument("--rank-min-values", default="2,3")
    parser.add_argument("--score-margin-values", default="0")
    parser.add_argument("--include-top2-variants", action="store_true")
    parser.add_argument("--report-min-tickets", type=int, default=20)
    parser.add_argument("--report-rows", type=int, default=80)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
