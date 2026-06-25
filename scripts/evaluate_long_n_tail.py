#!/usr/bin/env python3
"""Evaluate tiny-stake long-N tail tickets built from high-confidence legs."""
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

from scripts.evaluate_n7_confidence_coverage import confidence_metrics, group_samples_by_issue, model_probabilities
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras, market_probs
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
    strategy_verdict,
    train_q_model,
    write_csv,
)


@dataclass(frozen=True)
class TailProfile:
    name: str
    min_n: int
    min_selected_p: float
    min_top_p: float
    min_ratio: float
    min_margin: float
    min_score_factor: float
    max_n: int | None = None
    min_pred_hit_prob: float = 0.0


def default_profiles() -> list[TailProfile]:
    return [
        TailProfile("p38_r100_m00_n9_all", min_n=9, min_selected_p=0.38, min_top_p=0.38, min_ratio=1.00, min_margin=0.00, min_score_factor=1.02),
        TailProfile("p40_r100_m00_n9_all", min_n=9, min_selected_p=0.40, min_top_p=0.40, min_ratio=1.00, min_margin=0.00, min_score_factor=1.04),
        TailProfile("p42_r100_m03_n9_all", min_n=9, min_selected_p=0.42, min_top_p=0.42, min_ratio=1.00, min_margin=0.03, min_score_factor=1.04),
        TailProfile("p45_r100_m05_n9_all", min_n=9, min_selected_p=0.45, min_top_p=0.45, min_ratio=1.00, min_margin=0.05, min_score_factor=1.04),
        TailProfile("p40_r110_m00_n9_all", min_n=9, min_selected_p=0.40, min_top_p=0.40, min_ratio=1.10, min_margin=0.00, min_score_factor=1.04),
        TailProfile("p42_r105_m03_n10_all", min_n=10, min_selected_p=0.42, min_top_p=0.42, min_ratio=1.05, min_margin=0.03, min_score_factor=1.04),
        TailProfile("p45_r110_m05_n10_all", min_n=10, min_selected_p=0.45, min_top_p=0.45, min_ratio=1.10, min_margin=0.05, min_score_factor=1.04),
        TailProfile("p40_r100_m00_n12_all", min_n=12, min_selected_p=0.40, min_top_p=0.40, min_ratio=1.00, min_margin=0.00, min_score_factor=1.04),
        TailProfile("p42_r100_m03_n9_cap14", min_n=9, min_selected_p=0.42, min_top_p=0.42, min_ratio=1.00, min_margin=0.03, min_score_factor=1.04, max_n=14),
        TailProfile("p45_r100_m05_n9_cap14", min_n=9, min_selected_p=0.45, min_top_p=0.45, min_ratio=1.00, min_margin=0.05, min_score_factor=1.04, max_n=14),
        TailProfile("p45_r100_m05_n9_cap10_ph1e4", min_n=9, min_selected_p=0.45, min_top_p=0.45, min_ratio=1.00, min_margin=0.05, min_score_factor=1.04, max_n=10, min_pred_hit_prob=1e-4),
        TailProfile("p45_r100_m05_n9_cap12_ph1e4", min_n=9, min_selected_p=0.45, min_top_p=0.45, min_ratio=1.00, min_margin=0.05, min_score_factor=1.04, max_n=12, min_pred_hit_prob=1e-4),
        TailProfile("p48_r100_m06_n9_cap12_ph1e4", min_n=9, min_selected_p=0.48, min_top_p=0.48, min_ratio=1.00, min_margin=0.06, min_score_factor=1.04, max_n=12, min_pred_hit_prob=1e-4),
        TailProfile("p50_r100_m08_n9_cap12_ph1e4", min_n=9, min_selected_p=0.50, min_top_p=0.50, min_ratio=1.00, min_margin=0.08, min_score_factor=1.04, max_n=12, min_pred_hit_prob=1e-4),
        TailProfile("p45_r110_m05_n10_cap12_ph1e4", min_n=10, min_selected_p=0.45, min_top_p=0.45, min_ratio=1.10, min_margin=0.05, min_score_factor=1.04, max_n=12, min_pred_hit_prob=1e-4),
    ]


def profile_passes(profile: TailProfile, leg: Leg, metrics: dict[str, float]) -> bool:
    return (
        metrics["top1_agree"] >= 0.5
        and metrics["selected_model_p"] >= profile.min_selected_p
        and metrics["top_p"] >= profile.min_top_p
        and metrics["model_market_ratio"] >= profile.min_ratio
        and metrics["margin"] >= profile.min_margin
        and leg.score_factor >= profile.min_score_factor
    )


def convert_leg(leg: Leg, metrics: dict[str, float], profile: TailProfile) -> Leg:
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


def build_tail_ticket(
    *,
    issue: str,
    train_start_issue: str,
    train_end_issue: str,
    profile: TailProfile,
    q_legs: list[Leg],
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    ticket_idx: int,
) -> Ticket | None:
    candidates: list[tuple[float, Leg]] = []
    for leg in q_legs:
        probs = probs_by_match.get(leg.row.match_id)
        market = market_by_match.get(leg.row.match_id)
        if probs is None or market is None:
            continue
        metrics = confidence_metrics(leg, probs, market)
        if not profile_passes(profile, leg, metrics):
            continue
        converted = convert_leg(leg, metrics, profile)
        sort_score = (
            math.log(max(converted.score_factor, 1e-9))
            + math.log(max(converted.p_hat, 1e-9))
            + 0.25 * metrics["margin"]
        )
        candidates.append((sort_score, converted))

    candidates.sort(key=lambda x: x[0], reverse=True)
    legs = [leg for _, leg in candidates]
    if profile.max_n is not None:
        legs = legs[: profile.max_n]
    if len(legs) < profile.min_n:
        return None
    if len({leg.row.match_id for leg in legs}) < len(legs):
        return None
    pred_hit_prob = math.prod(max(0.0, min(1.0, leg.p_hat)) for leg in legs)
    if pred_hit_prob < profile.min_pred_hit_prob:
        return None
    return Ticket(
        strategy=f"long_tail_{profile.name}",
        issue=issue,
        n_legs=len(legs),
        ticket_idx=ticket_idx,
        train_start_issue=train_start_issue,
        train_end_issue=train_end_issue,
        legs=tuple(legs),
    )


def summarize_variable(tickets: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in tickets:
        grouped[str(row["strategy"])].append(row)
    out = []
    for strategy, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda r: (str(r["issue"]), int(r["ticket_idx"])))
        stake = sum(float(r["stake_units"]) for r in rows)
        profit = sum(float(r["profit_units"]) for r in rows)
        hits = sum(int(r["hit"]) for r in rows)
        issue_profit: dict[str, float] = defaultdict(float)
        issue_stake: dict[str, float] = defaultdict(float)
        cur_loss = 0
        max_loss = 0
        n_counts: Counter[int] = Counter()
        for row in rows:
            issue_profit[str(row["issue"])] += float(row["profit_units"])
            issue_stake[str(row["issue"])] += float(row["stake_units"])
            n_counts[int(row["n_legs"])] += 1
            if int(row["hit"]) == 1:
                cur_loss = 0
            else:
                cur_loss += 1
                max_loss = max(max_loss, cur_loss)
        best_issue_profit = max(issue_profit.values()) if issue_profit else 0.0
        roi = profit / stake if stake else float("nan")
        hit_rate = hits / len(rows) if rows else 0.0
        best_share = best_issue_profit / profit if profit > 0 and best_issue_profit > 0 else None
        expected_hits = sum(float(r["pred_hit_prob"]) for r in rows)
        verdict, reason = strategy_verdict(
            n_tickets=len(rows),
            roi=roi,
            profitable_issues=sum(1 for v in issue_profit.values() if v > 0),
            best_issue_profit_share=best_share,
            hit_rate=hit_rate,
        )
        out.append(
            {
                "strategy": strategy,
                "tickets": len(rows),
                "issues_with_ticket": len(issue_profit),
                "stake": stake,
                "profit": profit,
                "roi": roi,
                "hit_rate": hit_rate,
                "hits": hits,
                "avg_n_legs": sum(int(r["n_legs"]) for r in rows) / len(rows) if rows else 0.0,
                "min_n_legs": min(n_counts) if n_counts else "",
                "max_n_legs": max(n_counts) if n_counts else "",
                "n_mix": ";".join(f"N{k}:{v}" for k, v in sorted(n_counts.items())),
                "profitable_issues": sum(1 for v in issue_profit.values() if v > 0),
                "best_issue_profit_share": best_share if best_share is not None else "",
                "max_ticket_loss_streak": max_loss,
                "avg_pred_hit_prob": sum(float(r["pred_hit_prob"]) for r in rows) / len(rows) if rows else 0.0,
                "expected_hits": expected_hits,
                "poisson_p_ge_1_hit": 1.0 - math.exp(-expected_hits),
                "avg_pred_ev_per_stake": sum(float(r["pred_ev_per_stake"]) for r in rows) / len(rows) if rows else 0.0,
                "verdict": verdict,
                "verdict_reason": reason,
            }
        )
    out.sort(key=lambda r: float(r["roi"]) if math.isfinite(float(r["roi"])) else -999.0, reverse=True)
    return out


def issue_rows(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: {"tickets": 0, "hits": 0, "stake": 0.0, "profit": 0.0, "n_sum": 0.0})
    for row in ticket_rows:
        key = (str(row["strategy"]), str(row["issue"]))
        g = grouped[key]
        g["tickets"] += 1
        g["hits"] += int(row["hit"])
        g["stake"] += float(row["stake_units"])
        g["profit"] += float(row["profit_units"])
        g["n_sum"] += int(row["n_legs"])
    out = []
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
                "avg_n_legs": g["n_sum"] / g["tickets"] if g["tickets"] else "",
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    profiles = default_profiles()

    ticket_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    threshold = break_even_factor(args.reference_n) + args.min_factor_margin

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

        tickets_for_issue = 0
        for profile in profiles:
            ticket = build_tail_ticket(
                issue=test_issue,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                profile=profile,
                q_legs=q_legs,
                probs_by_match=probs_by_match,
                market_by_match=market_by_match,
                ticket_idx=1,
            )
            if ticket is None:
                coverage_rows.append(
                    {
                        "issue": test_issue,
                        "strategy": f"long_tail_{profile.name}",
                        "n_q_legs": len(q_legs),
                        "ticket_created": 0,
                        "n_legs": 0,
                    }
                )
                continue
            settled = settle_ticket(ticket)
            ticket_rows.append(settled)
            tickets_for_issue += 1
            coverage_rows.append(
                {
                    "issue": test_issue,
                    "strategy": ticket.strategy,
                    "n_q_legs": len(q_legs),
                    "ticket_created": 1,
                    "n_legs": ticket.n_legs,
                    "pred_hit_prob": settled["pred_hit_prob"],
                    "pred_ev_per_stake": settled["pred_ev_per_stake"],
                    "hit": settled["hit"],
                    "profit": settled["profit_units"],
                }
            )

        window_rows.append(
            {
                "issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_q_legs": len(q_legs),
                "tail_tickets_created": tickets_for_issue,
            }
        )

    summary = summarize_variable(ticket_rows)
    issues_summary = issue_rows(ticket_rows)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "long_tail_tickets.csv", ticket_rows)
    write_csv(out / "long_tail_summary.csv", summary)
    write_csv(out / "long_tail_issue_profit.csv", issues_summary)
    write_csv(out / "long_tail_coverage.csv", coverage_rows)
    write_csv(out / "long_tail_windows.csv", window_rows)

    report = [
        "# Long-N tail ticket evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Proxy odds range: `{args.min_proxy_odds}` - `{args.max_proxy_odds}`",
        f"- Reference break-even N: `{args.reference_n}`",
        "- Tail ticket rule: at most one single-cover long ticket per issue/profile.",
        "",
        "## Summary",
        md_table(summary),
        "",
        "## Files",
        "",
        "- `long_tail_summary.csv`",
        "- `long_tail_tickets.csv`",
        "- `long_tail_issue_profit.csv`",
        "- `long_tail_coverage.csv`",
        "- `long_tail_windows.csv`",
        "",
    ]
    (out / "long_tail_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'long_tail_report.md'}")
    print(f"Wrote {len(ticket_rows)} tail ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/long_n_tail"))
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
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
