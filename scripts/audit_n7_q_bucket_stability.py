#!/usr/bin/env python3
"""Audit N=7 q-bucket stability and snapshot-pure veto variants."""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import make_depth_weighted_tickets, transform_legs_for_depth
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.snapshot_pure_result_model import fit_predict_snapshot_pure, snapshot_market_probabilities
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras
from scripts.walkforward_beidan_strategy_eval import (
    Leg,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    group_by_issue as group_action_rows_by_issue,
    hcp_bucket,
    load_action_rows,
    md_table,
    q_key,
    settle_ticket,
    snapshot_odds_p,
    snapshot_rank_lookup,
    summarize_tickets,
    train_q_model,
    write_csv,
)


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def q_key_id(key: tuple[str, str, str, str]) -> str:
    return "|".join(key)


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def train_q_bucket_stats(rows, snapshot: str) -> dict[tuple[str, str, str, str], dict[str, float]]:
    rank_lookup = snapshot_rank_lookup(rows, snapshot)
    stats = defaultdict(lambda: {"train_hits": 0.0, "train_p_sum": 0.0, "train_n": 0.0})
    for row in rows:
        if row.action_code not in OUTCOMES:
            continue
        odds, p = snapshot_odds_p(row, snapshot)
        if odds is None or odds <= 1 or p is None or p <= 0:
            continue
        key = q_key(row, p, rank_lookup.get((row.match_id, row.action_code)))
        stats[key]["train_hits"] += row.hit
        stats[key]["train_p_sum"] += p
        stats[key]["train_n"] += 1
    for values in stats.values():
        p_sum = values["train_p_sum"]
        values["train_raw_q"] = values["train_hits"] / p_sum if p_sum > 0 else float("nan")
        values["train_hit_rate"] = values["train_hits"] / values["train_n"] if values["train_n"] > 0 else float("nan")
    return dict(stats)


def pure_meta(sample, action_code: str, pure_probs: np.ndarray, market_probs: np.ndarray) -> dict[str, float]:
    idx = OUTCOMES.index(action_code)
    ranked = np.argsort(-pure_probs)
    pure_rank = 1 + int(np.where(ranked == idx)[0][0])
    return {
        "pure_p": float(pure_probs[idx]),
        "market_p_norm": float(market_probs[idx]),
        "pure_ratio": float(pure_probs[idx]) / max(float(market_probs[idx]), 1e-9),
        "pure_rank": float(pure_rank),
        "pure_top1": 1.0 if pure_rank == 1 else 0.0,
        "pure_top2": 1.0 if pure_rank <= 2 else 0.0,
        "pure_top_p": float(pure_probs[ranked[0]]),
    }


def leg_audit_row(
    *,
    leg: Leg,
    test_issue: str,
    snapshot: str,
    train_q: float,
    key_stats: dict[str, float],
    pure: dict[str, float],
) -> dict[str, object]:
    odds, p = snapshot_odds_p(leg.row, snapshot)
    key = q_key(leg.row, p, None)
    return {
        "test_issue": test_issue,
        "match_id": leg.row.match_id,
        "match_idx": leg.row.match_idx,
        "league": leg.row.league,
        "action_code": leg.row.action_code,
        "hcp": leg.row.hcp,
        "hcp_bucket": hcp_bucket(leg.row.hcp),
        "q_key": q_key_id(key),
        "q_action": key[0],
        "q_hcp_bucket": key[1],
        "q_rank": key[2],
        "q_p_bucket": key[3],
        "train_q": train_q,
        "train_raw_q": key_stats.get("train_raw_q", ""),
        "train_n": key_stats.get("train_n", ""),
        "train_hits": key_stats.get("train_hits", ""),
        "train_p_sum": key_stats.get("train_p_sum", ""),
        "snapshot_odds": odds if odds is not None else "",
        "snapshot_p": p if p is not None else "",
        "p_hat": leg.p_hat,
        "score_factor": leg.score_factor,
        "hit": leg.row.hit,
        "winning_sp": leg.row.winning_sp,
        "factor": leg.row.factor,
        **pure,
    }


def aggregate_leg_rows(rows: list[dict[str, object]], group_fields: list[str]) -> list[dict[str, object]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(str(row.get(field, "")) for field in group_fields)].append(row)
    out = []
    for key, vals in sorted(grouped.items()):
        n = len(vals)
        p_sum = sum(float(v["snapshot_p"] or 0.0) for v in vals)
        hits = sum(int(v["hit"]) for v in vals)
        row = {field: key[i] for i, field in enumerate(group_fields)}
        row.update(
            {
                "n": n,
                "issues": len({str(v["test_issue"]) for v in vals}),
                "hits": hits,
                "hit_rate": hits / n if n else float("nan"),
                "p_sum": p_sum,
                "oos_q": hits / p_sum if p_sum > 0 else float("nan"),
                "avg_train_q": sum(float(v["train_q"]) for v in vals) / n if n else float("nan"),
                "avg_train_raw_q": mean_numeric(vals, "train_raw_q"),
                "avg_train_n": mean_numeric(vals, "train_n"),
                "avg_odds": mean_numeric(vals, "snapshot_odds"),
                "avg_score_factor": mean_numeric(vals, "score_factor"),
                "avg_pure_ratio": mean_numeric(vals, "pure_ratio"),
                "pure_top2_rate": sum(1 for v in vals if float(v["pure_top2"]) >= 0.5) / n if n else float("nan"),
            }
        )
        out.append(row)
    out.sort(key=lambda r: (-(float(r.get("n") or 0)), str(r.get(group_fields[0], ""))))
    return out


def mean_numeric(rows: list[dict[str, object]], field: str) -> float:
    vals = []
    for row in rows:
        value = row.get(field, "")
        if value == "":
            continue
        try:
            vals.append(float(value))
        except (TypeError, ValueError):
            pass
    return sum(vals) / len(vals) if vals else float("nan")


def apply_pure_veto(
    legs: list[Leg],
    pure_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    *,
    mode: str,
    min_ratio: float,
    min_p: float,
) -> list[Leg]:
    out: list[Leg] = []
    for leg in legs:
        pure_probs = pure_by_match.get(leg.row.match_id)
        market_probs = market_by_match.get(leg.row.match_id)
        if pure_probs is None or market_probs is None:
            continue
        meta = pure_meta(None, leg.row.action_code, pure_probs, market_probs)
        ratio = meta["pure_ratio"]
        keep = True
        adjusted = leg
        if mode == "none":
            keep = True
        elif mode == "top2":
            keep = meta["pure_top2"] >= 0.5
        elif mode == "ratio075":
            keep = ratio >= 0.75
        elif mode == "ratio090":
            keep = ratio >= 0.90
        elif mode == "soft_veto":
            keep = meta["pure_top2"] >= 0.5 or ratio >= min_ratio or meta["pure_p"] >= min_p
        elif mode == "soft_score":
            multiplier = max(0.70, min(1.20, math.sqrt(max(0.01, ratio))))
            adjusted = replace(
                leg,
                strategy=f"{leg.strategy}__pure_soft_score",
                score_factor=leg.score_factor * multiplier,
                source_rule=f"{leg.source_rule};pure_ratio={ratio:.4f};pure_soft_mult={multiplier:.4f}",
            )
        else:
            raise ValueError(f"unsupported veto mode: {mode}")
        if keep:
            out.append(adjusted)
    return out


def ticket_leg_rows(tickets, leg_meta: dict[str, dict[str, object]], settled_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    settled_by_idx = {(str(r["strategy"]), str(r["issue"]), int(r["ticket_idx"])): r for r in settled_rows}
    for ticket in tickets:
        settled = settled_by_idx.get((ticket.strategy, ticket.issue, ticket.ticket_idx))
        if not settled:
            continue
        allocated_profit = float(settled["profit_units"]) / max(1, len(ticket.legs))
        allocated_stake = float(settled["stake_units"]) / max(1, len(ticket.legs))
        for leg in ticket.legs:
            meta = leg_meta.get(leg.leg_id, {})
            out.append(
                {
                    "strategy": ticket.strategy,
                    "issue": ticket.issue,
                    "ticket_idx": ticket.ticket_idx,
                    "ticket_hit": int(settled["hit"]),
                    "allocated_profit_units": allocated_profit,
                    "allocated_stake_units": allocated_stake,
                    **meta,
                }
            )
    return out


def aggregate_ticket_leg_rows(rows: list[dict[str, object]], group_fields: list[str]) -> list[dict[str, object]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(str(row.get(field, "")) for field in group_fields)].append(row)
    out = []
    for key, vals in sorted(grouped.items()):
        stake = sum(float(v["allocated_stake_units"]) for v in vals)
        profit = sum(float(v["allocated_profit_units"]) for v in vals)
        row = {field: key[i] for i, field in enumerate(group_fields)}
        row.update(
            {
                "leg_uses": len(vals),
                "issues": len({str(v["issue"]) for v in vals}),
                "winning_ticket_uses": sum(int(v["ticket_hit"]) for v in vals),
                "winning_ticket_use_rate": sum(int(v["ticket_hit"]) for v in vals) / len(vals) if vals else float("nan"),
                "allocated_stake_units": stake,
                "allocated_profit_units": profit,
                "allocated_roi": profit / stake if stake > 0 else float("nan"),
                "avg_train_q": mean_numeric(vals, "train_q"),
                "avg_pure_ratio": mean_numeric(vals, "pure_ratio"),
                "pure_top2_rate": sum(1 for v in vals if float(v.get("pure_top2", 0.0)) >= 0.5) / len(vals) if vals else float("nan"),
            }
        )
        out.append(row)
    out.sort(key=lambda r: -float(r["leg_uses"]))
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
        "best_issue_profit_share",
        "avg_issue_stake_units",
        "max_drawdown_pct_on_10000",
        "verdict",
    ]
    return [{k: row.get(k, "") for k in keep} for row in summary]


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    veto_modes = parse_strings(args.veto_modes)

    candidate_rows: list[dict[str, object]] = []
    ticket_rows: list[dict[str, object]] = []
    ticket_objects = []
    window_rows: list[dict[str, object]] = []
    leg_meta: dict[str, dict[str, object]] = {}

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
        q_stats = train_q_bucket_stats(train_action_rows, args.snapshot)
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

        market = snapshot_market_probabilities(test_samples, args.snapshot)
        pure_probs, _ = fit_predict_snapshot_pure(
            train_samples,
            test_samples,
            snapshot=args.snapshot,
            feature_set=args.feature_set,
            l2=args.l2,
            maxiter=args.maxiter,
        )
        samples_by_match = {sample.match_id: sample for sample in test_samples}
        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        pure_by_match = {sample.match_id: pure_probs[i] for i, sample in enumerate(test_samples)}

        base_legs, base_weights = transform_legs_for_depth(
            q_legs,
            policy=args.depth_policy,
            probs_by_match=market_by_match,
            market_by_match=market_by_match,
            min_score_factor=threshold,
        )

        rank_lookup = snapshot_rank_lookup(test_action_rows, args.snapshot)
        for leg in base_legs:
            odds, p = snapshot_odds_p(leg.row, args.snapshot)
            key = q_key(leg.row, p, rank_lookup.get((leg.row.match_id, leg.row.action_code)))
            pure = pure_meta(samples_by_match.get(leg.row.match_id), leg.row.action_code, pure_by_match[leg.row.match_id], market_by_match[leg.row.match_id])
            row = leg_audit_row(
                leg=leg,
                test_issue=test_issue,
                snapshot=args.snapshot,
                train_q=q_model.get(key, global_q),
                key_stats=q_stats.get(key, {}),
                pure=pure,
            )
            row["q_key"] = q_key_id(key)
            row["q_rank"] = key[2]
            candidate_rows.append(row)
            leg_meta[leg.leg_id] = row

        for mode in veto_modes:
            legs = apply_pure_veto(
                base_legs,
                pure_by_match,
                market_by_match,
                mode=mode,
                min_ratio=args.veto_min_ratio,
                min_p=args.veto_min_p,
            )
            strategy = f"confidence_{args.depth_policy}__market__pure_{mode}"
            tickets = make_depth_weighted_tickets(
                legs,
                depth_weights=base_weights,
                strategy=strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                max_leg_uses=args.max_depth_leg_uses,
                max_ticket_overlap=args.max_depth_ticket_overlap,
            )
            ticket_objects.extend(tickets)
            ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "n_base_legs": len(base_legs),
            }
        )

    budget_rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=args.issue_budget_units, fractional=False)
    ticket_summary = summarize_tickets(ticket_rows)
    budget_summary = summarize_tickets(budget_rows)
    issue_profit = issue_profit_rows(budget_rows)
    tleg_rows = ticket_leg_rows(ticket_objects, leg_meta, ticket_rows)

    candidate_by_key = aggregate_leg_rows(candidate_rows, ["q_key"])
    candidate_by_action_hcp = aggregate_leg_rows(candidate_rows, ["action_code", "hcp_bucket"])
    ticket_by_key = aggregate_ticket_leg_rows(tleg_rows, ["strategy", "q_key"])
    ticket_by_action_hcp = aggregate_ticket_leg_rows(tleg_rows, ["strategy", "action_code", "hcp_bucket"])

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "q_candidate_legs.csv", candidate_rows)
    write_csv(out / "q_candidate_by_key.csv", candidate_by_key)
    write_csv(out / "q_candidate_by_action_hcp.csv", candidate_by_action_hcp)
    write_csv(out / "q_ticket_rows.csv", ticket_rows)
    write_csv(out / "q_ticket_budget_rows.csv", budget_rows)
    write_csv(out / "q_ticket_summary.csv", ticket_summary)
    write_csv(out / "q_ticket_budget_summary.csv", budget_summary)
    write_csv(out / "q_ticket_issue_profit.csv", issue_profit)
    write_csv(out / "q_ticket_leg_rows.csv", tleg_rows)
    write_csv(out / "q_ticket_by_key.csv", ticket_by_key)
    write_csv(out / "q_ticket_by_action_hcp.csv", ticket_by_action_hcp)
    write_csv(out / "q_audit_windows.csv", window_rows)

    report = [
        "# N=7 q bucket stability audit",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Depth policy: `{args.depth_policy}`",
        f"- Veto modes: `{args.veto_modes}`",
        f"- Same-budget issue stake: `{args.issue_budget_units}`",
        "",
        "## Budget Strategy Summary",
        md_table(compact_summary(budget_summary)),
        "## Candidate By Action/HCP",
        md_table(candidate_by_action_hcp[:40]),
        "## Ticket By Action/HCP",
        md_table(ticket_by_action_hcp[:60]),
        "## Candidate By Q Key",
        md_table(candidate_by_key[:60]),
        "",
        "Note: ticket-level bucket profit is allocated as `ticket profit / n_legs`; it is a diagnostic attribution, not a causal PnL decomposition.",
        "",
    ]
    (out / "q_bucket_audit_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'q_bucket_audit_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_bucket_audit"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--snapshot", choices=("10h", "1h"), default="10h")
    parser.add_argument("--feature-set", choices=("snapshot", "snapshot_priors", "snapshot_kelly", "snapshot_full"), default="snapshot_priors")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=20.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--veto-modes", default="none,soft_veto,ratio075,ratio090,top2,soft_score")
    parser.add_argument("--veto-min-ratio", type=float, default=0.75)
    parser.add_argument("--veto-min-p", type=float, default=0.16)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
