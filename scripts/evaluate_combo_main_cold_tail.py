#!/usr/bin/env python3
"""Combine the current N=7 main strategy with a tiny cold high-odds N=3 tail."""
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

from scripts.evaluate_cold_high_odds_tail import ColdProfile, build_ticket as build_cold_ticket
from scripts.evaluate_n7_confidence_coverage import make_depth_weighted_tickets, model_probabilities, transform_legs_for_depth
from scripts.evaluate_n7_depth_draw_cover import group_samples_by_issue
from scripts.evaluate_n7_dynamic_draw_cover import dynamic_draw_cover_ticket
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
    snapshot_odds_p,
    snapshot_rank_lookup,
    train_q_model,
    write_csv,
)


def parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def snapshot_market_probs(samples: list[object], snapshot: str) -> np.ndarray:
    out = []
    for sample in samples:
        probs = []
        for code in OUTCOMES:
            _, p = snapshot_odds_p(sample.rows[code], snapshot)
            probs.append(float(p or 0.0))
        total = sum(probs)
        if total <= 0:
            out.append([1 / 3, 1 / 3, 1 / 3])
        else:
            out.append([p / total for p in probs])
    return np.asarray(out, dtype=float)


def build_cold_candidates(
    *,
    test_samples: list[object],
    model_probs: np.ndarray,
    snapshot: str,
) -> list[dict[str, object]]:
    market = snapshot_market_probs(test_samples, snapshot)
    rank_lookup = snapshot_rank_lookup([row for sample in test_samples for row in sample.rows.values()], snapshot)
    candidates: list[dict[str, object]] = []
    for sample_idx, sample in enumerate(test_samples):
        ranked = np.argsort(-model_probs[sample_idx])
        top2 = {int(ranked[0]), int(ranked[1])}
        for outcome_idx, code in enumerate(OUTCOMES):
            row = sample.rows[code]
            odds, _ = snapshot_odds_p(row, snapshot)
            if odds is None or odds <= 1.0:
                continue
            model_p = float(model_probs[sample_idx, outcome_idx])
            market_p = float(market[sample_idx, outcome_idx])
            ratio = model_p / max(market_p, 1e-9)
            score = model_p * float(odds)
            rank = rank_lookup.get((sample.match_id, code), 0)
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
    return candidates


def main_covered_pairs(tickets: list[Ticket]) -> tuple[set[tuple[int, str]], set[tuple[int, str]], set[int]]:
    exact_pairs: set[tuple[int, str]] = set()
    covered_pairs: set[tuple[int, str]] = set()
    match_ids: set[int] = set()
    for ticket in tickets:
        for leg in ticket.legs:
            match_id = leg.row.match_id
            match_ids.add(match_id)
            exact_pairs.add((match_id, leg.row.action_code))
            for action in str(leg.row.selection_set):
                if action in OUTCOMES:
                    covered_pairs.add((match_id, action))
    return exact_pairs, covered_pairs, match_ids


def filter_cold_candidates_for_overlap(
    candidates: list[dict[str, object]],
    main_tickets: list[Ticket],
    mode: str,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    exact_pairs, covered_pairs, match_ids = main_covered_pairs(main_tickets)
    out: list[dict[str, object]] = []
    excluded = 0
    for candidate in candidates:
        match_id = int(candidate["match_id"])
        action_code = str(candidate["action_code"])
        pair = (match_id, action_code)
        if mode == "none":
            blocked = False
        elif mode == "exact":
            blocked = pair in exact_pairs
        elif mode == "covered":
            blocked = pair in covered_pairs
        elif mode == "match":
            blocked = match_id in match_ids
        else:
            raise ValueError(f"unsupported overlap filter: {mode}")
        if blocked:
            excluded += 1
            continue
        out.append(candidate)
    return out, {
        "n_cold_candidates_before_filter": len(candidates),
        "n_cold_candidates_after_filter": len(out),
        "n_cold_candidates_excluded": excluded,
        "n_main_exact_pairs": len(exact_pairs),
        "n_main_covered_pairs": len(covered_pairs),
        "n_main_match_ids": len(match_ids),
    }


def build_main_tickets(
    *,
    args: argparse.Namespace,
    test_issue: str,
    train_issues: list[str],
    train_action_rows: list[object],
    test_action_rows: list[object],
    test_samples: list[object],
    model_probs: np.ndarray,
    market: np.ndarray,
) -> tuple[list[Ticket], dict[str, object]]:
    threshold = break_even_factor(args.main_n_legs) + args.min_factor_margin
    q_model, global_q = train_q_model(train_action_rows, snapshot=args.main_snapshot, prior_n=args.q_prior_n)
    q_legs = build_q_baseline_legs(
        test_action_rows,
        q_model,
        global_q,
        snapshot=args.main_snapshot,
        min_proxy_odds=args.baseline_min_proxy_odds,
        max_proxy_odds=args.baseline_max_proxy_odds,
        min_score_factor=threshold,
    )
    model_probs_by_match = {sample.match_id: model_probs[i] for i, sample in enumerate(test_samples)}
    market_probs_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
    samples_by_match = {sample.match_id: sample for sample in test_samples}
    action_lookup = {(row.match_id, row.action_code): row for row in test_action_rows}
    depth_legs, depth_weights = transform_legs_for_depth(
        q_legs,
        policy=args.depth_policy,
        probs_by_match=model_probs_by_match,
        market_by_match=market_probs_by_match,
        min_score_factor=threshold,
    )
    depth_strategy = f"confidence_{args.depth_policy}"
    base_tickets = make_depth_weighted_tickets(
        depth_legs,
        depth_weights=depth_weights,
        strategy=depth_strategy,
        issue=test_issue,
        n_legs=args.main_n_legs,
        max_tickets=args.max_main_tickets_per_issue,
        overlap_penalty=args.overlap_penalty,
        train_start_issue=train_issues[0],
        train_end_issue=train_issues[-1],
        max_leg_uses=args.max_depth_leg_uses,
        max_ticket_overlap=args.max_depth_ticket_overlap,
    )
    main_tickets = [
        dynamic_draw_cover_ticket(
            ticket,
            strategy_prefix=depth_strategy,
            dynamic_policy=args.dynamic_policy,
            action_lookup=action_lookup,
            samples_by_match=samples_by_match,
            model_probs_by_match=model_probs_by_match,
            market_probs_by_match=market_probs_by_match,
            require_positive_draw_edge=args.require_positive_draw_edge,
        )
        for ticket in base_tickets
    ]
    diagnostics = {
        "n_q_legs": len(q_legs),
        "n_depth_legs": len(depth_legs),
        "n_main_base_tickets": len(base_tickets),
        "n_main_tickets": len(main_tickets),
    }
    return main_tickets, diagnostics


def cold_profile(args: argparse.Namespace) -> ColdProfile:
    return ColdProfile(
        name=(
            f"n{args.cold_n_legs}_odds{args.cold_min_odds:g}_"
            f"p{int(round(args.cold_min_model_p * 100)):02d}_"
            f"r{int(round(args.cold_min_ratio * 100)):03d}_"
            f"rank{args.cold_rank_min}_m00"
            f"{'_top2' if args.cold_require_top2 else ''}"
        ),
        n_legs=args.cold_n_legs,
        min_odds=args.cold_min_odds,
        max_odds=args.cold_max_odds,
        min_model_p=args.cold_min_model_p,
        min_ratio=args.cold_min_ratio,
        rank_min=args.cold_rank_min,
        score_margin=0.0,
        require_top2=args.cold_require_top2,
    )


def settle_rows(tickets: list[Ticket], family: str, ticket_weight: float = 1.0) -> list[dict[str, object]]:
    rows = []
    for row in (settle_ticket(ticket) for ticket in tickets):
        row = dict(row)
        row["family"] = family
        row["ticket_weight"] = ticket_weight
        row["weighted_stake_units"] = float(row["stake_units"]) * ticket_weight
        row["weighted_profit_units"] = float(row["profit_units"]) * ticket_weight
        rows.append(row)
    return rows


def aggregate_issue(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: {"tickets": 0.0, "hits": 0.0, "stake": 0.0, "profit": 0.0})
    for row in rows:
        issue = str(row["issue"])
        out[issue]["tickets"] += 1
        out[issue]["hits"] += int(row["hit"])
        out[issue]["stake"] += float(row["weighted_stake_units"])
        out[issue]["profit"] += float(row["weighted_profit_units"])
    return out


def max_drawdown(profits: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def max_loss_streak(profits: list[float]) -> int:
    cur = 0
    best = 0
    for profit in profits:
        if profit < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def summarize_issue_rows(rows: list[dict[str, object]], *, initial_bankroll: float) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["portfolio"])].append(row)
    out = []
    for portfolio, vals in grouped.items():
        vals = sorted(vals, key=lambda r: str(r["issue"]))
        stake = sum(float(r["stake"]) for r in vals)
        profit = sum(float(r["profit"]) for r in vals)
        profits = [float(r["profit"]) for r in vals]
        best_issue = max(profits) if profits else 0.0
        active_issues = sum(1 for r in vals if float(r["stake"]) > 0)
        tail_stake = sum(float(r["cold_stake"]) for r in vals)
        main_stake = sum(float(r["main_stake"]) for r in vals)
        out.append(
            {
                "portfolio": portfolio,
                "issues": len(vals),
                "active_issues": active_issues,
                "stake": stake,
                "profit": profit,
                "roi": profit / stake if stake else float("nan"),
                "profitable_issues": sum(1 for p in profits if p > 0),
                "hit_issues": sum(1 for r in vals if int(r["hits"]) > 0),
                "max_issue_profit": best_issue,
                "min_issue_profit": min(profits) if profits else 0.0,
                "best_issue_profit_share": best_issue / profit if profit > 0 and best_issue > 0 else "",
                "max_issue_loss_streak": max_loss_streak(profits),
                "max_drawdown_units": max_drawdown(profits),
                "max_drawdown_pct_on_bankroll": max_drawdown(profits) / initial_bankroll if initial_bankroll else "",
                "main_stake": main_stake,
                "cold_stake": tail_stake,
                "cold_stake_share": tail_stake / main_stake if main_stake else "",
            }
        )
    out.sort(key=lambda r: (str(r["portfolio"]) != "main_only", -float(r["roi"]) if math.isfinite(float(r["roi"])) else 999.0))
    return out


def make_portfolio_issue_rows(
    *,
    issues: list[str],
    main_by_issue: dict[str, dict[str, float]],
    cold_by_issue: dict[str, dict[str, float]],
    target_tail_shares: list[float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for issue in issues:
        main = main_by_issue.get(issue, {"tickets": 0.0, "hits": 0.0, "stake": 0.0, "profit": 0.0})
        cold = cold_by_issue.get(issue, {"tickets": 0.0, "hits": 0.0, "stake": 0.0, "profit": 0.0})
        variants = [("main_only", 0.0)]
        if cold["stake"] > 0:
            variants.append(("main_plus_cold_unit", 1.0))
        else:
            variants.append(("main_plus_cold_unit", 0.0))
        for share in target_tail_shares:
            scale = (main["stake"] * share / cold["stake"]) if cold["stake"] > 0 and main["stake"] > 0 else 0.0
            variants.append((f"main_plus_cold_{share:.0%}", scale))

        for portfolio, scale in variants:
            cold_stake = cold["stake"] * scale
            cold_profit = cold["profit"] * scale
            stake = main["stake"] + cold_stake
            profit = main["profit"] + cold_profit
            rows.append(
                {
                    "portfolio": portfolio,
                    "issue": issue,
                    "main_tickets": int(main["tickets"]),
                    "main_hits": int(main["hits"]),
                    "main_stake": main["stake"],
                    "main_profit": main["profit"],
                    "cold_tickets": int(cold["tickets"]),
                    "cold_hits": int(cold["hits"]),
                    "cold_scale": scale,
                    "cold_stake": cold_stake,
                    "cold_profit": cold_profit,
                    "tickets": int(main["tickets"] + cold["tickets"]),
                    "hits": int(main["hits"] + cold["hits"]),
                    "stake": stake,
                    "profit": profit,
                    "roi": profit / stake if stake else float("nan"),
                    "cold_stake_share": cold_stake / main["stake"] if main["stake"] else "",
                }
            )
    return rows


def make_allocation_issue_rows(
    *,
    issues: list[str],
    main_by_issue: dict[str, dict[str, float]],
    cold_by_issue: dict[str, dict[str, float]],
    main_shares: list[float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for issue in issues:
        main = main_by_issue.get(issue, {"tickets": 0.0, "hits": 0.0, "stake": 0.0, "profit": 0.0})
        cold = cold_by_issue.get(issue, {"tickets": 0.0, "hits": 0.0, "stake": 0.0, "profit": 0.0})
        budget = main["stake"]
        for main_share in main_shares:
            cold_share = max(0.0, 1.0 - main_share)
            main_stake = budget * main_share
            main_profit = main["profit"] * main_share
            cold_budget = budget * cold_share
            if cold["stake"] > 0 and cold_budget > 0:
                cold_scale = cold_budget / cold["stake"]
                cold_stake = cold_budget
                cold_profit = cold["profit"] * cold_scale
            else:
                cold_scale = 0.0
                cold_stake = 0.0
                cold_profit = 0.0
            deployed_stake = main_stake + cold_stake
            profit = main_profit + cold_profit
            rows.append(
                {
                    "allocation": f"main_{main_share:.0%}_cold_{cold_share:.0%}",
                    "issue": issue,
                    "budget": budget,
                    "deployed_stake": deployed_stake,
                    "main_share": main_share,
                    "cold_share": cold_share,
                    "main_tickets": int(main["tickets"]),
                    "main_hits": int(main["hits"]),
                    "main_stake": main_stake,
                    "main_profit": main_profit,
                    "cold_tickets": int(cold["tickets"]),
                    "cold_hits": int(cold["hits"]),
                    "cold_scale": cold_scale,
                    "cold_stake": cold_stake,
                    "cold_profit": cold_profit,
                    "profit": profit,
                    "budget_roi": profit / budget if budget else float("nan"),
                    "deployed_roi": profit / deployed_stake if deployed_stake else float("nan"),
                }
            )
    return rows


def summarize_allocation_rows(rows: list[dict[str, object]], *, initial_bankroll: float) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["allocation"])].append(row)
    out: list[dict[str, object]] = []
    for allocation, vals in grouped.items():
        vals = sorted(vals, key=lambda r: str(r["issue"]))
        profits = [float(r["profit"]) for r in vals]
        budget = sum(float(r["budget"]) for r in vals)
        deployed = sum(float(r["deployed_stake"]) for r in vals)
        profit = sum(profits)
        best_issue = max(profits) if profits else 0.0
        out.append(
            {
                "allocation": allocation,
                "issues": len(vals),
                "triggered_issues": sum(1 for r in vals if int(r.get("triggered", 0) or 0) > 0),
                "budget": budget,
                "deployed_stake": deployed,
                "profit": profit,
                "budget_roi": profit / budget if budget else float("nan"),
                "deployed_roi": profit / deployed if deployed else float("nan"),
                "profitable_issues": sum(1 for p in profits if p > 0),
                "cold_ticket_issues": sum(1 for r in vals if int(r["cold_tickets"]) > 0),
                "cold_hit_issues": sum(1 for r in vals if int(r["cold_hits"]) > 0),
                "main_profit": sum(float(r["main_profit"]) for r in vals),
                "cold_profit": sum(float(r["cold_profit"]) for r in vals),
                "cold_deployed_stake": sum(float(r["cold_stake"]) for r in vals),
                "max_issue_profit": best_issue,
                "min_issue_profit": min(profits) if profits else 0.0,
                "best_issue_profit_share": best_issue / profit if profit > 0 and best_issue > 0 else "",
                "max_issue_loss_streak": max_loss_streak(profits),
                "max_drawdown_units": max_drawdown(profits),
                "max_drawdown_pct_on_bankroll": max_drawdown(profits) / initial_bankroll if initial_bankroll else "",
            }
        )
    out.sort(key=lambda r: float(r["main_profit"]), reverse=True)
    return out


def cold_ticket_metrics_by_issue(rows: list[dict[str, object]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        out[str(row["issue"])] = {
            "pred_hit_prob": float(row["pred_hit_prob"]),
            "pred_ev_per_stake": float(row["pred_ev_per_stake"]),
            "stake": float(row["stake_units"]),
            "profit": float(row["profit_units"]),
            "hit": float(row["hit"]),
        }
    return out


def conditional_triggered(
    *,
    budget: float,
    cold: dict[str, float],
    cold_metrics: dict[str, float] | None,
    window: dict[str, object] | None,
    args: argparse.Namespace,
) -> bool:
    if cold["stake"] <= 0 or cold_metrics is None:
        return False
    if args.trigger_min_main_budget > 0 and budget < args.trigger_min_main_budget:
        return False
    if args.trigger_max_main_budget > 0 and budget > args.trigger_max_main_budget:
        return False
    if cold_metrics["pred_hit_prob"] < args.trigger_min_cold_pred_hit_prob:
        return False
    if args.trigger_max_cold_pred_hit_prob > 0 and cold_metrics["pred_hit_prob"] > args.trigger_max_cold_pred_hit_prob:
        return False
    if cold_metrics["pred_ev_per_stake"] < args.trigger_min_cold_pred_ev:
        return False
    if window is not None:
        if int(window.get("n_cold_candidate_matches", 0)) < args.trigger_min_cold_candidate_matches:
            return False
        if int(window.get("n_q_legs", 0)) < args.trigger_min_q_legs:
            return False
        if args.trigger_max_q_legs > 0 and int(window.get("n_q_legs", 0)) > args.trigger_max_q_legs:
            return False
        if int(window.get("n_main_match_ids", 0)) < args.trigger_min_main_match_ids:
            return False
        if args.trigger_max_main_match_ids > 0 and int(window.get("n_main_match_ids", 0)) > args.trigger_max_main_match_ids:
            return False
        if int(window.get("n_main_covered_pairs", 0)) < args.trigger_min_main_covered_pairs:
            return False
        if args.trigger_max_main_covered_pairs > 0 and int(window.get("n_main_covered_pairs", 0)) > args.trigger_max_main_covered_pairs:
            return False
    return True


def make_conditional_allocation_issue_rows(
    *,
    issues: list[str],
    main_by_issue: dict[str, dict[str, float]],
    cold_by_issue: dict[str, dict[str, float]],
    cold_metrics_by_issue: dict[str, dict[str, float]],
    windows_by_issue: dict[str, dict[str, object]],
    args: argparse.Namespace,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    allocation = (
        f"conditional_main_{args.conditional_main_share:.0%}_cold_{1.0 - args.conditional_main_share:.0%}"
        f"_cand{args.trigger_min_cold_candidate_matches}"
    )
    for issue in issues:
        main = main_by_issue.get(issue, {"tickets": 0.0, "hits": 0.0, "stake": 0.0, "profit": 0.0})
        cold = cold_by_issue.get(issue, {"tickets": 0.0, "hits": 0.0, "stake": 0.0, "profit": 0.0})
        budget = main["stake"]
        metrics = cold_metrics_by_issue.get(issue)
        window = windows_by_issue.get(issue)
        triggered = conditional_triggered(
            budget=budget,
            cold=cold,
            cold_metrics=metrics,
            window=window,
            args=args,
        )
        main_share = args.conditional_main_share if triggered else 1.0
        cold_share = max(0.0, 1.0 - main_share)
        main_stake = budget * main_share
        main_profit = main["profit"] * main_share
        if triggered and cold["stake"] > 0:
            cold_scale = budget * cold_share / cold["stake"]
            cold_stake = budget * cold_share
            cold_profit = cold["profit"] * cold_scale
        else:
            cold_scale = 0.0
            cold_stake = 0.0
            cold_profit = 0.0
        deployed = main_stake + cold_stake
        profit = main_profit + cold_profit
        rows.append(
            {
                "allocation": allocation,
                "issue": issue,
                "triggered": int(triggered),
                "budget": budget,
                "deployed_stake": deployed,
                "main_share": main_share,
                "cold_share": cold_share,
                "main_tickets": int(main["tickets"]),
                "main_hits": int(main["hits"]),
                "main_stake": main_stake,
                "main_profit": main_profit,
                "cold_tickets": int(cold["tickets"]),
                "cold_hits": int(cold["hits"]),
                "cold_scale": cold_scale,
                "cold_stake": cold_stake,
                "cold_profit": cold_profit,
                "profit": profit,
                "budget_roi": profit / budget if budget else float("nan"),
                "deployed_roi": profit / deployed if deployed else float("nan"),
                "cold_pred_hit_prob": metrics["pred_hit_prob"] if metrics else "",
                "cold_pred_ev_per_stake": metrics["pred_ev_per_stake"] if metrics else "",
                "n_cold_candidate_matches": int(window.get("n_cold_candidate_matches", 0)) if window else "",
                "n_q_legs": int(window.get("n_q_legs", 0)) if window else "",
                "n_main_match_ids": int(window.get("n_main_match_ids", 0)) if window else "",
                "n_main_covered_pairs": int(window.get("n_main_covered_pairs", 0)) if window else "",
            }
        )
    return rows


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    profile = cold_profile(args)
    target_tail_shares = parse_floats(args.target_tail_shares)

    main_ticket_rows: list[dict[str, object]] = []
    cold_ticket_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    evaluated_issues: list[str] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        train_action_rows = [row for issue in train_issues for row in action_by_issue.get(issue, [])]
        test_action_rows = action_by_issue.get(test_issue, [])
        train_samples = [sample for issue in train_issues for sample in samples_by_issue.get(issue, [])]
        test_samples = samples_by_issue.get(test_issue, [])
        if len(train_samples) < args.min_train_matches or not test_samples:
            continue

        model_probs = model_probabilities(args, train_samples, test_samples)
        main_market = market_probs(test_samples)
        main_tickets, main_diag = build_main_tickets(
            args=args,
            test_issue=test_issue,
            train_issues=train_issues,
            train_action_rows=train_action_rows,
            test_action_rows=test_action_rows,
            test_samples=test_samples,
            model_probs=model_probs,
            market=main_market,
        )
        cold_candidates = build_cold_candidates(
            test_samples=test_samples,
            model_probs=model_probs,
            snapshot=args.cold_snapshot,
        )
        cold_candidates, overlap_diag = filter_cold_candidates_for_overlap(
            cold_candidates,
            main_tickets,
            args.cold_overlap_filter,
        )
        cold_ticket, cold_candidate_matches = build_cold_ticket(
            issue=test_issue,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            profile=profile,
            candidates=cold_candidates,
        )
        cold_tickets = [cold_ticket] if cold_ticket is not None else []
        if cold_tickets and args.cold_strategy_suffix:
            cold_tickets = [replace(ticket, strategy=f"{ticket.strategy}_{args.cold_strategy_suffix}") for ticket in cold_tickets]

        main_ticket_rows.extend(settle_rows(main_tickets, family="main", ticket_weight=1.0))
        cold_ticket_rows.extend(settle_rows(cold_tickets, family="cold", ticket_weight=1.0))
        evaluated_issues.append(test_issue)
        window_rows.append(
            {
                "issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "main_snapshot": args.main_snapshot,
                "cold_snapshot": args.cold_snapshot,
                "cold_overlap_filter": args.cold_overlap_filter,
                **main_diag,
                **overlap_diag,
                "n_cold_candidate_matches": cold_candidate_matches,
                "n_cold_tickets": len(cold_tickets),
            }
        )

    main_by_issue = aggregate_issue(main_ticket_rows)
    cold_by_issue = aggregate_issue(cold_ticket_rows)
    portfolio_issue_rows = make_portfolio_issue_rows(
        issues=evaluated_issues,
        main_by_issue=main_by_issue,
        cold_by_issue=cold_by_issue,
        target_tail_shares=target_tail_shares,
    )
    portfolio_summary = summarize_issue_rows(portfolio_issue_rows, initial_bankroll=args.initial_bankroll)
    allocation_issue_rows = make_allocation_issue_rows(
        issues=evaluated_issues,
        main_by_issue=main_by_issue,
        cold_by_issue=cold_by_issue,
        main_shares=parse_floats(args.allocation_main_shares),
    )
    allocation_summary = summarize_allocation_rows(allocation_issue_rows, initial_bankroll=args.initial_bankroll)
    windows_by_issue = {str(row["issue"]): row for row in window_rows}
    conditional_issue_rows = make_conditional_allocation_issue_rows(
        issues=evaluated_issues,
        main_by_issue=main_by_issue,
        cold_by_issue=cold_by_issue,
        cold_metrics_by_issue=cold_ticket_metrics_by_issue(cold_ticket_rows),
        windows_by_issue=windows_by_issue,
        args=args,
    )
    conditional_summary = summarize_allocation_rows(conditional_issue_rows, initial_bankroll=args.initial_bankroll)

    all_ticket_rows = main_ticket_rows + cold_ticket_rows
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "combo_tickets.csv", all_ticket_rows)
    write_csv(out / "combo_main_tickets.csv", main_ticket_rows)
    write_csv(out / "combo_cold_tickets.csv", cold_ticket_rows)
    write_csv(out / "combo_issue_profit.csv", portfolio_issue_rows)
    write_csv(out / "combo_summary.csv", portfolio_summary)
    write_csv(out / "allocation_issue_profit.csv", allocation_issue_rows)
    write_csv(out / "allocation_summary.csv", allocation_summary)
    write_csv(out / "conditional_allocation_issue_profit.csv", conditional_issue_rows)
    write_csv(out / "conditional_allocation_summary.csv", conditional_summary)
    write_csv(out / "combo_windows.csv", window_rows)

    report = [
        "# Main N=7 + cold high-odds N=3 combo evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Main: `{args.depth_policy}__draw_dynamic_{args.dynamic_policy}` snapshot `{args.main_snapshot}`",
        f"- Cold: `{profile.name}` snapshot `{args.cold_snapshot}`",
        f"- Cold overlap filter: `{args.cold_overlap_filter}`",
        f"- Target tail shares: `{args.target_tail_shares}`",
        "",
        "## Portfolio Summary",
        md_table(portfolio_summary),
        "## Same-Budget Allocation Summary",
        md_table(allocation_summary),
        "## Conditional Allocation Summary",
        md_table(conditional_summary),
        "",
        "## Files",
        "",
        "- `combo_summary.csv`",
        "- `combo_issue_profit.csv`",
        "- `allocation_summary.csv`",
        "- `allocation_issue_profit.csv`",
        "- `conditional_allocation_summary.csv`",
        "- `conditional_allocation_issue_profit.csv`",
        "- `combo_tickets.csv`",
        "- `combo_main_tickets.csv`",
        "- `combo_cold_tickets.csv`",
        "- `combo_windows.csv`",
        "",
    ]
    (out / "combo_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'combo_report.md'}")
    print(f"Wrote {len(main_ticket_rows)} main ticket rows and {len(cold_ticket_rows)} cold ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/combo_main_cold_tail"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--main-n-legs", type=int, default=7)
    parser.add_argument("--max-main-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--main-snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--model-source", choices=("multiclass", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--dynamic-policy", default="model_draw_ratio_t0.55_k2")
    parser.add_argument("--require-positive-draw-edge", action="store_true")
    parser.add_argument("--cold-snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--cold-n-legs", type=int, default=3)
    parser.add_argument("--cold-min-odds", type=float, default=5.0)
    parser.add_argument("--cold-max-odds", type=float, default=20.0)
    parser.add_argument("--cold-min-model-p", type=float, default=0.16)
    parser.add_argument("--cold-min-ratio", type=float, default=1.25)
    parser.add_argument("--cold-rank-min", type=int, default=3)
    parser.add_argument("--cold-require-top2", action="store_true", default=True)
    parser.add_argument("--cold-overlap-filter", choices=("none", "exact", "covered", "match"), default="none")
    parser.add_argument("--cold-strategy-suffix", default="")
    parser.add_argument("--target-tail-shares", default="0.01,0.02,0.03")
    parser.add_argument("--allocation-main-shares", default="1.0,0.8,0.6,0.4")
    parser.add_argument("--conditional-main-share", type=float, default=0.80)
    parser.add_argument("--trigger-min-cold-candidate-matches", type=int, default=15)
    parser.add_argument("--trigger-min-cold-pred-hit-prob", type=float, default=0.0)
    parser.add_argument("--trigger-max-cold-pred-hit-prob", type=float, default=0.0)
    parser.add_argument("--trigger-min-cold-pred-ev", type=float, default=0.0)
    parser.add_argument("--trigger-min-main-budget", type=float, default=0.0)
    parser.add_argument("--trigger-max-main-budget", type=float, default=0.0)
    parser.add_argument("--trigger-min-q-legs", type=int, default=0)
    parser.add_argument("--trigger-max-q-legs", type=int, default=0)
    parser.add_argument("--trigger-min-main-match-ids", type=int, default=0)
    parser.add_argument("--trigger-max-main-match-ids", type=int, default=0)
    parser.add_argument("--trigger-min-main-covered-pairs", type=int, default=0)
    parser.add_argument("--trigger-max-main-covered-pairs", type=int, default=0)
    parser.add_argument("--initial-bankroll", type=float, default=10000.0)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
