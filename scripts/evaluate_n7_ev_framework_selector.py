#!/usr/bin/env python3
"""Evaluate an explicit EV-first N=7 selector.

This script makes the layers explicit:

* outcome EV: P(result=o) * estimated_sp(o)
* coverage EV: stake-normalized value for 3/1/0/31/30/10/310
* match EV: best coverage value available for the match
* ticket EV: return_rate * product(coverage_value_i / cover_count_i) - 1

The first implementation uses existing q pockets for P(result=o) and snapshot
odds as estimated SP. Settlement still uses official winning SP from the
normalized Beidan SQLite data.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_high_sp_anchor_protection import (
    ACTION_BY_SET,
    OUTCOMES,
    AnchorCandidate,
    annual_rows,
    clamp,
    compact_summary,
    issue_regime_rows,
    make_composition_tickets,
    option_stats,
    regime_summary_rows,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_unified_leg_selector import ex_best_issue_rows, recent_subset
from scripts.walkforward_beidan_strategy_eval import (
    RETURN_RATE,
    ActionRow,
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    group_by_issue,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)


COVERAGE_SETS = (
    frozenset({"3"}),
    frozenset({"1"}),
    frozenset({"0"}),
    frozenset({"3", "1"}),
    frozenset({"3", "0"}),
    frozenset({"1", "0"}),
    frozenset({"3", "1", "0"}),
)


@dataclass(frozen=True)
class EvMatchCandidate:
    issue: str
    match_id: int
    match_idx: int
    league: str
    hcp: float
    best_single_code: str
    best_single_score: float
    best_single_leg: Leg
    best_protected_code: str | None
    best_protected_score: float | None
    best_protected_leg: Leg | None
    match_score: float
    match_ev_n7: float
    match_ev_standalone: float
    decision: dict[str, object]


def parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def score_to_ev_n7(score: float, threshold: float) -> float:
    return score / threshold - 1.0


def score_to_ev_standalone(score: float) -> float:
    return RETURN_RATE * score - 1.0


def action_lookup(rows: list[ActionRow]) -> dict[tuple[int, str], ActionRow]:
    return {(row.match_id, row.action_code): row for row in rows}


def coverage_code(codes: frozenset[str]) -> str:
    code = ACTION_BY_SET.get(codes)
    if code is None:
        raise ValueError(f"unsupported coverage set: {sorted(codes)}")
    return code


def coverage_metrics(
    stats: dict[str, dict[str, float]],
    codes: frozenset[str],
    *,
    threshold: float,
) -> dict[str, float | str | int]:
    value_sum = sum(stats[code]["p_hat"] * stats[code]["odds"] for code in codes)
    score = value_sum / len(codes)
    hit_prob = sum(stats[code]["p_hat"] for code in codes)
    min_outcome_ev_n7 = min(score_to_ev_n7(stats[code]["p_hat"] * stats[code]["odds"], threshold) for code in codes)
    avg_outcome_ev_n7 = sum(score_to_ev_n7(stats[code]["p_hat"] * stats[code]["odds"], threshold) for code in codes) / len(codes)
    return {
        "coverage_code": coverage_code(codes),
        "cover_count": len(codes),
        "selected_outcomes": "".join(code for code in OUTCOMES if code in codes),
        "coverage_value_sum": value_sum,
        "coverage_score": score,
        "coverage_ev_n7": score_to_ev_n7(score, threshold),
        "coverage_ev_standalone": score_to_ev_standalone(score),
        "coverage_hit_prob": clamp(hit_prob, 0.001, 0.999),
        "avg_outcome_ev_n7": avg_outcome_ev_n7,
        "min_outcome_ev_n7": min_outcome_ev_n7,
    }


def build_ev_candidates(
    rows: list[ActionRow],
    stats_by_match: dict[int, dict[str, dict[str, float]]],
    *,
    strategy: str,
    threshold: float,
    min_match_score_ratio: float,
    protection_score_floor_ratio: float,
    min_single_odds: float,
    max_single_odds: float,
    min_protected_hit_gain: float,
    require_protection_contains_best_single: bool,
    allow_full: bool,
) -> tuple[list[AnchorCandidate], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    lookup = action_lookup(rows)
    by_match: dict[int, list[ActionRow]] = defaultdict(list)
    for row in rows:
        if row.action_code in OUTCOMES:
            by_match[row.match_id].append(row)

    candidates: list[AnchorCandidate] = []
    decisions: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    min_match_score = threshold * min_match_score_ratio

    for match_id, match_rows in sorted(by_match.items()):
        stats = stats_by_match.get(match_id, {})
        if not all(code in stats for code in OUTCOMES):
            continue
        row0 = match_rows[0]

        for code in OUTCOMES:
            stat = stats[code]
            outcome_value = stat["p_hat"] * stat["odds"]
            outcome_rows.append(
                {
                    "strategy": strategy,
                    "issue": row0.issue,
                    "match_id": match_id,
                    "match_idx": row0.match_idx,
                    "league": row0.league,
                    "hcp": row0.hcp,
                    "outcome": code,
                    "estimated_sp": stat["odds"],
                    "market_p": stat["market_p"],
                    "q": stat["q"],
                    "p_hat": stat["p_hat"],
                    "outcome_value": outcome_value,
                    "outcome_ev_n7": score_to_ev_n7(outcome_value, threshold),
                    "outcome_ev_standalone": score_to_ev_standalone(outcome_value),
                    "move_log": stat.get("move_log", ""),
                }
            )

        valid_coverages = []
        for codes in COVERAGE_SETS:
            if not allow_full and len(codes) == 3:
                continue
            action_code = coverage_code(codes)
            target = lookup.get((match_id, action_code))
            if target is None:
                continue
            metrics = coverage_metrics(stats, codes, threshold=threshold)
            coverage_row = {
                "strategy": strategy,
                "issue": row0.issue,
                "match_id": match_id,
                "match_idx": row0.match_idx,
                "league": row0.league,
                "hcp": row0.hcp,
                **metrics,
                "hit": target.hit,
                "winning_sp": target.winning_sp,
            }
            coverage_rows.append(coverage_row)
            valid_coverages.append((codes, target, metrics))

        singles = [
            (codes, target, metrics)
            for codes, target, metrics in valid_coverages
            if len(codes) == 1
            and min_single_odds <= stats[next(iter(codes))]["odds"] <= max_single_odds
        ]
        if not singles:
            continue
        best_single_codes, best_single_target, best_single_metrics = max(
            singles,
            key=lambda item: (
                float(item[2]["coverage_score"]),
                float(item[2]["coverage_hit_prob"]),
                stats[next(iter(item[0]))]["odds"],
            ),
        )
        best_single_code = next(iter(best_single_codes))
        best_single_score = float(best_single_metrics["coverage_score"])
        if best_single_score < min_match_score:
            continue

        protected_options = [
            (codes, target, metrics)
            for codes, target, metrics in valid_coverages
            if len(codes) > 1
            and float(metrics["coverage_score"]) >= best_single_score * protection_score_floor_ratio
            and float(metrics["coverage_hit_prob"]) >= float(best_single_metrics["coverage_hit_prob"]) + min_protected_hit_gain
            and (
                not require_protection_contains_best_single
                or best_single_code in codes
            )
        ]
        best_protected = max(
            protected_options,
            key=lambda item: (
                float(item[2]["coverage_score"]),
                float(item[2]["coverage_hit_prob"]),
                -int(item[2]["cover_count"]),
            ),
            default=None,
        )

        best_match_metrics = max(valid_coverages, key=lambda item: float(item[2]["coverage_score"]))[2]
        single_leg = Leg(
            row=best_single_target,
            strategy=strategy,
            score_factor=best_single_score,
            p_hat=float(best_single_metrics["coverage_hit_prob"]),
            source_rule=(
                f"ev_single;chosen={best_single_code};"
                f"coverage_score={best_single_score:.4f};"
                f"coverage_ev_n7={float(best_single_metrics['coverage_ev_n7']):.4f}"
            ),
            is_full_cover=False,
        )

        protected_leg = None
        protected_code = ""
        protected_score = ""
        protected_hit_prob = ""
        protected_ev_n7 = ""
        protected_cover_count = ""
        if best_protected is not None:
            protected_codes, protected_target, protected_metrics = best_protected
            protected_code = str(protected_metrics["coverage_code"])
            protected_score = float(protected_metrics["coverage_score"])
            protected_hit_prob = float(protected_metrics["coverage_hit_prob"])
            protected_ev_n7 = float(protected_metrics["coverage_ev_n7"])
            protected_cover_count = int(protected_metrics["cover_count"])
            protected_leg = Leg(
                row=protected_target,
                strategy=strategy,
                score_factor=protected_score,
                p_hat=protected_hit_prob,
                source_rule=(
                    f"ev_protected;single={best_single_code};chosen={protected_code};"
                    f"coverage_score={protected_score:.4f};"
                    f"coverage_ev_n7={protected_ev_n7:.4f};"
                    f"stake_norm_cover_count={protected_target.cover_count}"
                ),
                is_full_cover=protected_target.cover_count == 3,
            )

        chosen_leg = protected_leg or single_leg
        decision = {
            "strategy": strategy,
            "issue": row0.issue,
            "match_id": match_id,
            "match_idx": row0.match_idx,
            "league": row0.league,
            "hcp": row0.hcp,
            "decision_stage": "match_ev_then_coverage_ev",
            "best_single_code": best_single_code,
            "best_single_odds": stats[best_single_code]["odds"],
            "best_single_p_hat": stats[best_single_code]["p_hat"],
            "best_single_score": best_single_score,
            "best_single_ev_n7": float(best_single_metrics["coverage_ev_n7"]),
            "best_single_ev_standalone": float(best_single_metrics["coverage_ev_standalone"]),
            "match_score": float(best_match_metrics["coverage_score"]),
            "match_ev_n7": float(best_match_metrics["coverage_ev_n7"]),
            "match_ev_standalone": float(best_match_metrics["coverage_ev_standalone"]),
            "chosen_action": chosen_leg.row.action_code,
            "chosen_cover_count": chosen_leg.row.cover_count,
            "chosen_score": chosen_leg.score_factor,
            "chosen_p_hat": chosen_leg.p_hat,
            "protected_code": protected_code,
            "protected_cover_count": protected_cover_count,
            "protected_score": protected_score,
            "protected_hit_prob": protected_hit_prob,
            "protected_ev_n7": protected_ev_n7,
            "protection_score_floor_ratio": protection_score_floor_ratio,
            "min_match_score_ratio": min_match_score_ratio,
            "min_match_score": min_match_score,
            "min_protected_hit_gain": min_protected_hit_gain,
            "hit": chosen_leg.row.hit,
            "winning_sp": chosen_leg.row.winning_sp,
        }
        candidates.append(
            AnchorCandidate(
                strategy=strategy,
                issue=row0.issue,
                match_id=match_id,
                anchor=best_single_code,
                anchor_odds=stats[best_single_code]["odds"],
                single_leg=single_leg,
                protected_leg=protected_leg,
                decision=decision,
            )
        )
        decisions.append(decision)

    return candidates, decisions, outcome_rows, coverage_rows


def strategy_name(
    min_match_ratio: float,
    protection_floor_ratio: float,
    *,
    allow_full: bool,
    n_legs: int,
    target_protected_per_ticket: int,
    ticket_protection_mode: str,
) -> str:
    match_part = f"m{min_match_ratio:g}".replace(".", "p")
    floor_part = f"p{protection_floor_ratio:g}".replace(".", "p")
    full_part = "full" if allow_full else "nofull"
    if ticket_protection_mode == "optional":
        return f"ev_{match_part}_{floor_part}_{full_part}_opt"
    if ticket_protection_mode == "single":
        return f"ev_{match_part}_{floor_part}_{full_part}_{n_legs}s0p"
    single_count = max(0, n_legs - target_protected_per_ticket)
    return f"ev_{match_part}_{floor_part}_{full_part}_{single_count}s{target_protected_per_ticket}p"


def selected_legs_for_mode(candidates: list[AnchorCandidate], mode: str) -> list[Leg]:
    if mode == "single":
        return [candidate.single_leg for candidate in candidates]
    if mode == "optional":
        return [candidate.protected_leg or candidate.single_leg for candidate in candidates]
    raise ValueError(f"unsupported non-quota protection mode: {mode}")


def make_tickets_for_protection_mode(
    candidates: list[AnchorCandidate],
    *,
    strategy: str,
    issue: str,
    n_legs: int,
    max_tickets: int,
    overlap_penalty: float,
    train_start_issue: str,
    train_end_issue: str,
    ticket_protection_mode: str,
    target_protected_per_ticket: int,
    max_full_cover_per_ticket: int,
    require_target_protection: bool,
    max_leg_uses: int,
) -> list[Ticket]:
    if ticket_protection_mode == "quota":
        return make_composition_tickets(
            candidates,
            strategy=strategy,
            issue=issue,
            n_legs=n_legs,
            max_tickets=max_tickets,
            overlap_penalty=overlap_penalty,
            train_start_issue=train_start_issue,
            train_end_issue=train_end_issue,
            target_protected_per_ticket=target_protected_per_ticket,
            max_full_cover_per_ticket=max_full_cover_per_ticket,
            require_target_protection=require_target_protection,
            max_leg_uses=max_leg_uses,
        )
    return make_tickets(
        selected_legs_for_mode(candidates, ticket_protection_mode),
        strategy=strategy,
        issue=issue,
        n_legs=n_legs,
        max_tickets=max_tickets,
        overlap_penalty=overlap_penalty,
        train_start_issue=train_start_issue,
        train_end_issue=train_end_issue,
        full_rows={},
        action_model={},
    )


def decision_chain_rows(
    *,
    outcome_rows: list[dict[str, object]],
    decision_rows: list[dict[str, object]],
    ticket_rows: list[dict[str, object]],
    budget_summary: list[dict[str, object]],
    threshold: float,
) -> list[dict[str, object]]:
    base_matches = {(str(row["issue"]), int(row["match_id"])) for row in outcome_rows}
    decisions_by_strategy: dict[str, list[dict[str, object]]] = defaultdict(list)
    tickets_by_strategy: dict[str, list[dict[str, object]]] = defaultdict(list)
    budget_by_base_strategy: dict[str, dict[str, object]] = {}

    for row in decision_rows:
        decisions_by_strategy[str(row["strategy"])].append(row)
    for row in ticket_rows:
        tickets_by_strategy[str(row["strategy"])].append(row)
    for row in budget_summary:
        strategy = str(row["strategy"])
        base = strategy.split("__budget", 1)[0]
        budget_by_base_strategy[base] = row

    out = []
    for strategy, rows in sorted(decisions_by_strategy.items()):
        ticket_rows_for_strategy = tickets_by_strategy.get(strategy, [])
        budget = budget_by_base_strategy.get(strategy, {})
        selected_matches = {(str(row["issue"]), int(row["match_id"])) for row in rows}
        cover_counts = Counter(int(row["chosen_cover_count"]) for row in rows if row.get("chosen_cover_count") != "")
        protected_rows = [row for row in rows if str(row.get("protected_code", ""))]
        avg = lambda vals: sum(vals) / len(vals) if vals else float("nan")

        out.append(
            {
                "strategy": strategy,
                "stage": "outcome_estimation",
                "n_base_matches": len(base_matches),
                "n_rows": len(outcome_rows),
                "pass_rate_vs_base": 1.0,
                "avg_best_single_ev_n7": "",
                "avg_match_ev_n7": "",
                "avg_chosen_ev_n7": "",
                "n_cover1": "",
                "n_cover2": "",
                "n_cover3": "",
                "n_protected_candidates": "",
                "protected_candidate_rate": "",
                "n_tickets": "",
                "budget_profit_units": "",
                "budget_roi": "",
                "verdict": "",
            }
        )
        out.append(
            {
                "strategy": strategy,
                "stage": "match_ev_filter",
                "n_base_matches": len(base_matches),
                "n_rows": len(rows),
                "pass_rate_vs_base": len(selected_matches) / len(base_matches) if base_matches else float("nan"),
                "avg_best_single_ev_n7": avg([float(row["best_single_ev_n7"]) for row in rows]),
                "avg_match_ev_n7": avg([float(row["match_ev_n7"]) for row in rows]),
                "avg_chosen_ev_n7": "",
                "n_cover1": "",
                "n_cover2": "",
                "n_cover3": "",
                "n_protected_candidates": "",
                "protected_candidate_rate": "",
                "n_tickets": "",
                "budget_profit_units": "",
                "budget_roi": "",
                "verdict": "",
            }
        )
        out.append(
            {
                "strategy": strategy,
                "stage": "coverage_choice",
                "n_base_matches": len(base_matches),
                "n_rows": len(rows),
                "pass_rate_vs_base": len(selected_matches) / len(base_matches) if base_matches else float("nan"),
                "avg_best_single_ev_n7": avg([float(row["best_single_ev_n7"]) for row in rows]),
                "avg_match_ev_n7": avg([float(row["match_ev_n7"]) for row in rows]),
                "avg_chosen_ev_n7": avg([float(row["chosen_score"]) / threshold - 1.0 for row in rows]),
                "n_protected_candidates": len(protected_rows),
                "protected_candidate_rate": len(protected_rows) / len(rows) if rows else float("nan"),
                "n_cover1": cover_counts[1],
                "n_cover2": cover_counts[2],
                "n_cover3": cover_counts[3],
                "n_tickets": "",
                "budget_profit_units": "",
                "budget_roi": "",
                "verdict": "",
            }
        )
        out.append(
            {
                "strategy": strategy,
                "stage": "ticket_construction",
                "n_base_matches": len(base_matches),
                "n_rows": len(ticket_rows_for_strategy),
                "pass_rate_vs_base": "",
                "avg_best_single_ev_n7": "",
                "avg_match_ev_n7": "",
                "avg_chosen_ev_n7": "",
                "n_cover1": "",
                "n_cover2": sum(int(row["n_double_cover"]) for row in ticket_rows_for_strategy),
                "n_cover3": sum(int(row["n_full_cover"]) for row in ticket_rows_for_strategy),
                "n_protected_candidates": "",
                "protected_candidate_rate": "",
                "n_tickets": len(ticket_rows_for_strategy),
                "budget_profit_units": "",
                "budget_roi": "",
                "verdict": "",
            }
        )
        out.append(
            {
                "strategy": strategy,
                "stage": "portfolio_result",
                "n_base_matches": len(base_matches),
                "n_rows": budget.get("n_tickets", ""),
                "pass_rate_vs_base": "",
                "avg_best_single_ev_n7": "",
                "avg_match_ev_n7": "",
                "avg_chosen_ev_n7": "",
                "n_cover1": "",
                "n_cover2": "",
                "n_cover3": "",
                "n_protected_candidates": "",
                "protected_candidate_rate": "",
                "n_tickets": budget.get("n_tickets", ""),
                "budget_profit_units": budget.get("total_profit_units", ""),
                "budget_roi": budget.get("roi", ""),
                "verdict": budget.get("verdict", ""),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    rows = load_action_rows(args.db, args.min_year)
    by_issue = group_by_issue(rows)
    issues = sorted(by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    match_ratios = parse_floats(args.min_match_score_ratios)
    protection_floors = parse_floats(args.protection_score_floor_ratios)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        if any(issue >= test_issue for issue in train_issues):
            raise RuntimeError(f"leakage guard failed: train={train_issues}, test={test_issue}")
        train_rows = [row for issue in train_issues for row in by_issue[issue]]
        test_rows = by_issue[test_issue]
        train_start, train_end = train_issues[0], train_issues[-1]
        q_model, global_q = train_q_model(train_rows, snapshot=args.snapshot, prior_n=args.q_prior_n)
        stats_by_match = option_stats(test_rows, q_model, global_q, snapshot=args.snapshot)

        q_legs = build_q_baseline_legs(
            test_rows,
            q_model,
            global_q,
            snapshot=args.snapshot,
            min_proxy_odds=args.baseline_min_proxy_odds,
            max_proxy_odds=args.baseline_max_proxy_odds,
            min_score_factor=threshold,
        )
        q_tickets = make_tickets(
            q_legs,
            strategy="baseline_q_high_sp",
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_start,
            train_end_issue=train_end,
            full_rows={},
            action_model={},
        )
        ticket_rows.extend(settle_ticket(ticket) for ticket in q_tickets)

        emitted_base_rows = False
        for match_ratio in match_ratios:
            for protection_floor in protection_floors:
                for allow_full in ([False, True] if args.sweep_full else [args.allow_full]):
                    strategy = strategy_name(
                        match_ratio,
                        protection_floor,
                        allow_full=allow_full,
                        n_legs=args.n_legs,
                        target_protected_per_ticket=args.target_protected_per_ticket,
                        ticket_protection_mode=args.ticket_protection_mode,
                    )
                    candidates, decisions, issue_outcomes, issue_coverages = build_ev_candidates(
                        test_rows,
                        stats_by_match,
                        strategy=strategy,
                        threshold=threshold,
                        min_match_score_ratio=match_ratio,
                        protection_score_floor_ratio=protection_floor,
                        min_single_odds=args.min_single_odds,
                        max_single_odds=args.max_single_odds,
                        min_protected_hit_gain=args.min_protected_hit_gain,
                        require_protection_contains_best_single=args.require_protection_contains_best_single,
                        allow_full=allow_full,
                    )
                    tickets = make_tickets_for_protection_mode(
                        candidates,
                        strategy=strategy,
                        issue=test_issue,
                        n_legs=args.n_legs,
                        max_tickets=args.max_tickets_per_issue,
                        overlap_penalty=args.overlap_penalty,
                        train_start_issue=train_start,
                        train_end_issue=train_end,
                        ticket_protection_mode=args.ticket_protection_mode,
                        target_protected_per_ticket=args.target_protected_per_ticket,
                        max_full_cover_per_ticket=args.max_full_cover_per_ticket,
                        require_target_protection=args.require_target_protection,
                        max_leg_uses=args.max_composition_leg_uses,
                    )
                    ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)
                    decision_rows.extend(decisions)
                    if not emitted_base_rows:
                        outcome_rows.extend(issue_outcomes)
                        coverage_rows.extend(issue_coverages)
                        emitted_base_rows = True

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_start,
                "train_end_issue": train_end,
                "leakage_guard": "train_issues_before_test_issue",
                "snapshot": args.snapshot,
                "threshold": threshold,
                "n_train_rows": len(train_rows),
                "n_test_rows": len(test_rows),
                "n_q_tickets": len(q_tickets),
            }
        )

    raw_summary = summarize_tickets(ticket_rows)
    raw_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    raw_issue_profit = issue_profit_rows(ticket_rows)
    raw_annual = annual_rows(ticket_rows)
    raw_ex_best = ex_best_issue_rows(raw_issue_profit)

    budget_rows = budgeted_ticket_rows(
        ticket_rows,
        issue_budget_units=args.issue_budget_units,
        fractional=True,
    )
    summary = summarize_tickets(budget_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    chain = decision_chain_rows(
        outcome_rows=outcome_rows,
        decision_rows=decision_rows,
        ticket_rows=ticket_rows,
        budget_summary=summary,
        threshold=threshold,
    )
    issue_profit = issue_profit_rows(budget_rows)
    annual = annual_rows(budget_rows)
    ex_best = ex_best_issue_rows(issue_profit)
    recent_summary = summarize_tickets(recent_subset(budget_rows, 2023, 2025))
    recent_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    regime = issue_regime_rows(issue_profit, big_loss_roi_threshold=args.regime_big_loss_roi_threshold)
    regime_summary = regime_summary_rows(regime)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "ev_framework_tickets.csv", ticket_rows)
    write_csv(out / "ev_framework_raw_summary.csv", raw_summary)
    write_csv(out / "ev_framework_raw_issue_profit.csv", raw_issue_profit)
    write_csv(out / "ev_framework_raw_annual_summary.csv", raw_annual)
    write_csv(out / "ev_framework_raw_ex_best_issue_summary.csv", raw_ex_best)
    write_csv(out / "ev_framework_budget_fractional_tickets.csv", budget_rows)
    write_csv(out / "ev_framework_summary.csv", summary)
    write_csv(out / "ev_framework_decision_chain.csv", chain)
    write_csv(out / "ev_framework_issue_profit.csv", issue_profit)
    write_csv(out / "ev_framework_annual_summary.csv", annual)
    write_csv(out / "ev_framework_recent_2023_2025_summary.csv", recent_summary)
    write_csv(out / "ev_framework_ex_best_issue_summary.csv", ex_best)
    write_csv(out / "ev_framework_regime.csv", regime)
    write_csv(out / "ev_framework_regime_summary.csv", regime_summary)
    write_csv(out / "ev_framework_decisions.csv", decision_rows)
    write_csv(out / "ev_framework_outcomes.csv", outcome_rows)
    write_csv(out / "ev_framework_coverages.csv", coverage_rows)
    write_csv(out / "ev_framework_windows.csv", window_rows)

    report = [
        "# N=7 explicit EV framework selector",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Min year: `{args.min_year}`",
        f"- Train issues: `{args.train_issues}`",
        f"- N legs: `{args.n_legs}`",
        f"- N=7 break-even leg score: `{threshold:.6f}`",
        f"- Issue budget: `{args.issue_budget_units}`",
        f"- Min match score ratios: `{args.min_match_score_ratios}`",
        f"- Protection score floor ratios: `{args.protection_score_floor_ratios}`",
        f"- Ticket protection mode: `{args.ticket_protection_mode}`",
        f"- Require protection contains best single: `{args.require_protection_contains_best_single}`",
        f"- Target protected per ticket: `{args.target_protected_per_ticket}`",
        f"- Max full cover per ticket: `{args.max_full_cover_per_ticket}`",
        f"- Require target protection: `{args.require_target_protection}`",
        "",
        "## Same-Budget Fractional Summary",
        "",
        md_table(compact_summary(summary), limit=80),
        "## Decision Chain",
        "",
        md_table(chain, limit=120),
        "## 2023-2025 Same-Budget Summary",
        "",
        md_table(compact_summary(recent_summary), limit=80),
        "## Ex-Best Issue Summary",
        "",
        md_table(ex_best, limit=80),
        "## K-Line Regime Summary",
        "",
        md_table(regime_summary, limit=120),
        "## Raw Summary",
        "",
        md_table(compact_summary(raw_summary), limit=80),
        "## Files",
        "",
        "- `ev_framework_summary.csv`",
        "- `ev_framework_decision_chain.csv`",
        "- `ev_framework_recent_2023_2025_summary.csv`",
        "- `ev_framework_ex_best_issue_summary.csv`",
        "- `ev_framework_decisions.csv`",
        "- `ev_framework_outcomes.csv`",
        "- `ev_framework_coverages.csv`",
        "- `ev_framework_budget_fractional_tickets.csv`",
        "",
    ]
    (out / "ev_framework_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'ev_framework_report.md'}")
    print(f"Wrote {len(ticket_rows)} raw ticket rows and {len(decision_rows)} decision rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_ev_framework_selector"))
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--train-issues", type=int, default=24)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--min-match-score-ratios", default="0.95,1,1.05")
    parser.add_argument("--protection-score-floor-ratios", default="0.8,0.85,0.9")
    parser.add_argument("--min-single-odds", type=float, default=1.0)
    parser.add_argument("--max-single-odds", type=float, default=30.0)
    parser.add_argument("--min-protected-hit-gain", type=float, default=0.02)
    parser.add_argument("--target-protected-per-ticket", type=int, default=2)
    parser.add_argument("--max-full-cover-per-ticket", type=int, default=1)
    parser.add_argument("--max-composition-leg-uses", type=int, default=0)
    parser.add_argument("--ticket-protection-mode", choices=("quota", "single", "optional"), default="quota")
    parser.add_argument("--require-target-protection", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-protection-contains-best-single", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow-full", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sweep-full", action="store_true")
    parser.add_argument("--regime-big-loss-roi-threshold", type=float, default=-0.75)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
