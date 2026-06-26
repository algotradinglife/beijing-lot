#!/usr/bin/env python3
"""Evaluate N=7 depth from joint result + SP-drift uncertainty.

The experiment starts from the existing q-baseline + confidence-depth pipeline,
then decides each leg's coverage depth:

* result posterior uncertainty decides single / double / full cover;
* SP-drift multiplier and recent move decide whether an outcome is eligible;
* coverage score is stake-normalized:
    sum(P(result=o) * decision_odds(o) * predicted_sp_multiplier(o)) / cover_count

Settlement remains the normalized XLSM truth: actual result + official
winning_sp. No final snapshot is used as payout truth.
"""
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

from scripts.evaluate_n7_confidence_coverage import (
    avg_depth_weight,
    avg_pair_overlap,
    make_depth_weighted_tickets,
    max_leg_use_in_tickets,
    model_probabilities as trained_model_probabilities,
    top_agree_rate,
    transform_legs_for_depth,
)
from scripts.evaluate_n7_sp_drift_depth import (
    move_stability_component,
    odds_move_log,
    odds_stability_component,
    predict_sp_multiplier,
    train_sp_drift_model,
)
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
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


ACTION_BY_SET = {
    frozenset({"3"}): "3",
    frozenset({"1"}): "1",
    frozenset({"0"}): "0",
    frozenset({"3", "1"}): "31",
    frozenset({"3", "0"}): "30",
    frozenset({"1", "0"}): "10",
    frozenset({"3", "1", "0"}): "310",
}

PROFILE_CONFIGS = {
    "conservative": {
        "max_cover": 2,
        "single_top_p": 0.45,
        "single_margin": 0.14,
        "double_score_ratio": 1.02,
        "full_score_ratio": 9.99,
        "full_entropy": 9.99,
        "min_sub_q": 0.75,
    },
    "balanced": {
        "max_cover": 3,
        "single_top_p": 0.48,
        "single_margin": 0.16,
        "double_score_ratio": 0.98,
        "full_score_ratio": 1.00,
        "full_entropy": 1.02,
        "min_sub_q": 0.65,
    },
    "aggressive": {
        "max_cover": 3,
        "single_top_p": 0.55,
        "single_margin": 0.20,
        "double_score_ratio": 0.92,
        "full_score_ratio": 0.96,
        "full_entropy": 0.96,
        "min_sub_q": 0.55,
    },
}


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def snapshot_market_probabilities(samples, snapshot: str) -> np.ndarray:
    rows = []
    for sample in samples:
        vals = []
        for code in OUTCOMES:
            odds, p = snapshot_odds_p(sample.rows[code], snapshot)
            if p is not None and p > 0:
                vals.append(float(p))
            elif odds is not None and odds > 1.0:
                vals.append(1.0 / float(odds))
            else:
                vals.append(0.0)
        total = sum(vals)
        if total <= 0:
            rows.append([1 / 3, 1 / 3, 1 / 3])
        else:
            rows.append([v / total for v in vals])
    return np.asarray(rows, dtype=float)


def decision_probabilities(args, train_samples, test_samples) -> np.ndarray:
    if args.model_source == "snapshot_market":
        return snapshot_market_probabilities(test_samples, args.snapshot)
    return trained_model_probabilities(args, train_samples, test_samples)


def entropy(probs: np.ndarray) -> float:
    vals = np.asarray(probs, dtype=float)
    vals = vals[vals > 0]
    return float(-np.sum(vals * np.log(vals))) if len(vals) else 0.0


def coverage_code(codes: set[str]) -> str:
    code = ACTION_BY_SET.get(frozenset(codes))
    if code is None:
        raise ValueError(f"unsupported coverage set: {codes}")
    return code


def coverage_score(stats: dict[str, dict[str, float]], codes: set[str]) -> float:
    return sum(stats[code]["effective_score"] for code in codes) / len(codes)


def action_lookup_for_issue(rows: list[ActionRow]) -> dict[tuple[int, str], ActionRow]:
    return {(row.match_id, row.action_code): row for row in rows}


def option_stats(
    *,
    sample,
    probs: np.ndarray,
    market: np.ndarray,
    sp_model,
    snapshot: str,
    max_odds: float,
    min_multiplier: float,
    max_abs_log_move: float,
    min_stability_score: float,
    directional_drift: bool,
    positive_move_penalty: float,
    negative_move_bonus: float,
    min_positive_move_component: float,
    max_negative_move_component: float,
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for idx, code in enumerate(OUTCOMES):
        row = sample.rows[code]
        odds, _ = snapshot_odds_p(row, snapshot)
        if odds is None or odds <= 1.0:
            continue
        multiplier = predict_sp_multiplier(sp_model, row)
        move_log = odds_move_log(row, snapshot)
        move_abs = abs(move_log) if move_log is not None and math.isfinite(move_log) else 0.0
        if not directional_drift or move_log is None or not math.isfinite(move_log):
            direction_component = 1.0
            move_direction = 0.0
        elif move_log > 0:
            direction_component = max(
                min_positive_move_component,
                math.exp(-positive_move_penalty * move_log),
            )
            move_direction = 1.0
        else:
            direction_component = min(
                max_negative_move_component,
                math.exp(negative_move_bonus * abs(move_log)),
            )
            move_direction = -1.0
        stability = multiplier * odds_stability_component(float(odds)) * move_stability_component(move_log)
        q_final = float(probs[idx]) * float(odds) * float(multiplier)
        effective_score = q_final * direction_component
        stable = (
            float(odds) <= max_odds
            and multiplier >= min_multiplier
            and move_abs <= max_abs_log_move
            and stability >= min_stability_score
        )
        out[code] = {
            "p": float(probs[idx]),
            "market_p": float(market[idx]),
            "odds": float(odds),
            "multiplier": float(multiplier),
            "settlement_drift_log": math.log(max(float(multiplier), 1e-9)),
            "move_log": float(move_log) if move_log is not None and math.isfinite(move_log) else 0.0,
            "move_abs": float(move_abs),
            "move_direction": move_direction,
            "direction_component": direction_component,
            "stability": float(stability),
            "q_final": q_final,
            "effective_score": effective_score,
            "stable": 1.0 if stable else 0.0,
        }
    return out


def choose_coverage(
    *,
    leg: Leg,
    sample,
    probs: np.ndarray,
    market: np.ndarray,
    action_lookup: dict[tuple[int, str], ActionRow],
    sp_model,
    snapshot: str,
    profile: str,
    threshold: float,
    coverage_threshold: float,
    max_odds: float,
    min_multiplier: float,
    max_abs_log_move: float,
    min_stability_score: float,
    min_anchor_score_ratio: float,
    directional_drift: bool,
    positive_move_penalty: float,
    negative_move_bonus: float,
    min_positive_move_component: float,
    max_negative_move_component: float,
) -> tuple[Leg, float, dict[str, object]] | None:
    cfg = PROFILE_CONFIGS[profile]
    stats = option_stats(
        sample=sample,
        probs=probs,
        market=market,
        sp_model=sp_model,
        snapshot=snapshot,
        max_odds=max_odds,
        min_multiplier=min_multiplier,
        max_abs_log_move=max_abs_log_move,
        min_stability_score=min_stability_score,
        directional_drift=directional_drift,
        positive_move_penalty=positive_move_penalty,
        negative_move_bonus=negative_move_bonus,
        min_positive_move_component=min_positive_move_component,
        max_negative_move_component=max_negative_move_component,
    )
    anchor = leg.row.action_code
    if anchor not in stats:
        return None
    ranked_by_p = sorted(OUTCOMES, key=lambda code: stats.get(code, {}).get("p", -1.0), reverse=True)
    ranked_by_q = sorted(OUTCOMES, key=lambda code: stats.get(code, {}).get("effective_score", -1.0), reverse=True)
    top = ranked_by_p[0]
    second = ranked_by_p[1]
    top_p = stats[top]["p"]
    second_p = stats[second]["p"]
    margin = top_p - second_p
    ent = entropy(probs)
    anchor_stat = stats[anchor]
    if not anchor_stat["stable"] or anchor_stat["effective_score"] < threshold * min_anchor_score_ratio:
        return None

    chosen = {anchor}
    decision = "single"
    stable_ranked = [code for code in ranked_by_q if code in stats and stats[code]["stable"]]
    single_confident = anchor == top and top_p >= cfg["single_top_p"] and margin >= cfg["single_margin"]

    if not single_confident and cfg["max_cover"] >= 2:
        sub_candidates = [
            code
            for code in stable_ranked
            if code != anchor and stats[code]["effective_score"] >= cfg["min_sub_q"]
        ]
        if sub_candidates:
            candidate = {anchor, sub_candidates[0]}
            if coverage_score(stats, candidate) >= coverage_threshold * cfg["double_score_ratio"]:
                chosen = candidate
                decision = "double"

    if cfg["max_cover"] >= 3 and ent >= cfg["full_entropy"]:
        all_codes = set(OUTCOMES)
        if all(code in stats and stats[code]["stable"] for code in all_codes):
            if coverage_score(stats, all_codes) >= coverage_threshold * cfg["full_score_ratio"]:
                chosen = all_codes
                decision = "full"

    action_code = coverage_code(chosen)
    target_row = action_lookup.get((leg.row.match_id, action_code))
    if target_row is None:
        return None
    score = coverage_score(stats, chosen)
    p_hat = min(0.999, max(0.001, sum(stats[code]["p"] for code in chosen)))
    depth_weight = max(0.45, min(2.25, (score / max(threshold, 1e-9)) ** 0.5))
    converted = Leg(
        row=target_row,
        strategy=f"joint_uncertainty_{profile}",
        score_factor=score,
        p_hat=p_hat,
        source_rule=(
            f"{leg.source_rule};joint_profile={profile};decision={decision};"
            f"anchor={anchor};chosen={action_code};score={score:.4f};"
            f"entropy={ent:.4f};top={top};top_p={top_p:.4f};margin={margin:.4f};"
            f"anchor_q_final={anchor_stat['q_final']:.4f};anchor_effective_score={anchor_stat['effective_score']:.4f};"
            f"anchor_mult={anchor_stat['multiplier']:.4f};anchor_settlement_drift_log={anchor_stat['settlement_drift_log']:.4f};"
            f"anchor_move_log={anchor_stat['move_log']:.4f};anchor_direction_component={anchor_stat['direction_component']:.4f};"
            f"anchor_stability={anchor_stat['stability']:.4f};"
            f"depth_weight={depth_weight:.4f}"
        ),
        is_full_cover=target_row.cover_count == 3,
    )
    metrics = {
        "profile": profile,
        "decision": decision,
        "match_id": leg.row.match_id,
        "anchor": anchor,
        "action_code": action_code,
        "cover_count": target_row.cover_count,
        "score": score,
        "p_hat": p_hat,
        "entropy": ent,
        "top": top,
        "top_p": top_p,
        "margin": margin,
        "anchor_q_final": anchor_stat["q_final"],
        "anchor_effective_score": anchor_stat["effective_score"],
        "anchor_multiplier": anchor_stat["multiplier"],
        "anchor_settlement_drift_log": anchor_stat["settlement_drift_log"],
        "anchor_move_log": anchor_stat["move_log"],
        "anchor_move_direction": anchor_stat["move_direction"],
        "anchor_direction_component": anchor_stat["direction_component"],
        "anchor_stability": anchor_stat["stability"],
        "depth_weight": depth_weight,
    }
    return converted, depth_weight, metrics


def issue_profit_rows(ticket_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped = defaultdict(lambda: defaultdict(lambda: {"stake": 0.0, "profit": 0.0, "hits": 0, "tickets": 0}))
    for row in ticket_rows:
        vals = grouped[str(row["strategy"])][str(row["issue"])]
        vals["stake"] += float(row["stake_units"])
        vals["profit"] += float(row["profit_units"])
        vals["hits"] += int(row["hit"])
        vals["tickets"] += 1
    out = []
    for strategy, by_issue in sorted(grouped.items()):
        for issue, vals in sorted(by_issue.items()):
            out.append(
                {
                    "strategy": strategy,
                    "issue": issue,
                    "tickets": vals["tickets"],
                    "hits": vals["hits"],
                    "stake_units": vals["stake"],
                    "profit_units": vals["profit"],
                    "roi": vals["profit"] / vals["stake"] if vals["stake"] else float("nan"),
                }
            )
    return out


def budgeted_ticket_rows(
    ticket_rows: list[dict[str, object]],
    *,
    issue_budget_units: float,
    fractional: bool,
) -> list[dict[str, object]]:
    def convert(row: dict[str, object], scale: float, strategy_name: str) -> dict[str, object]:
        raw_stake = float(row["stake_units"])
        converted = dict(row)
        converted["strategy"] = strategy_name
        converted["original_strategy"] = str(row["strategy"])
        converted["raw_stake_units"] = raw_stake
        converted["stake_scale"] = scale
        converted["stake_units"] = raw_stake * scale
        converted["payout_units"] = float(row["payout_units"]) * scale
        converted["profit_units"] = float(row["profit_units"]) * scale
        converted["roi"] = (
            float(converted["profit_units"]) / float(converted["stake_units"])
            if float(converted["stake_units"]) > 0
            else float("nan")
        )
        converted["issue_budget_units"] = issue_budget_units
        return converted

    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in ticket_rows:
        grouped[(str(row["strategy"]), str(row["issue"]))].append(row)

    out: list[dict[str, object]] = []
    suffix = f"__budget{issue_budget_units:g}_{'fractional' if fractional else 'whole'}"
    for (strategy, issue), rows in sorted(grouped.items()):
        remaining = issue_budget_units
        ranked = sorted(
            rows,
            key=lambda row: (
                float(row.get("pred_ev_per_stake", 0.0)),
                float(row.get("pred_hit_prob", 0.0)),
                -float(row.get("stake_units", 0.0)),
            ),
            reverse=True,
        )
        strategy_name = f"{strategy}{suffix}"
        if fractional:
            selected: list[tuple[dict[str, object], float]] = []
            for row in ranked:
                raw_stake = float(row["stake_units"])
                if raw_stake <= 0 or remaining <= 1e-9:
                    break
                scale = 1.0 if raw_stake <= remaining + 1e-9 else remaining / raw_stake
                selected.append((row, scale))
                remaining -= raw_stake * scale
            spent = sum(float(row["stake_units"]) * scale for row, scale in selected)
            fill_scale = issue_budget_units / spent if 0 < spent < issue_budget_units else 1.0
            for row, scale in selected:
                out.append(convert(row, scale * fill_scale, strategy_name))
            continue

        counts = [0 for _ in ranked]
        raw_stakes = [float(row["stake_units"]) for row in ranked]
        while remaining > 1e-9:
            progressed = False
            for i, raw_stake in enumerate(raw_stakes):
                if raw_stake <= 0:
                    continue
                if raw_stake <= remaining + 1e-9:
                    counts[i] += 1
                    remaining -= raw_stake
                    progressed = True
                if remaining <= 1e-9:
                    break
            if not progressed:
                break
        for row, count in zip(ranked, counts):
            if count > 0:
                out.append(convert(row, float(count), strategy_name))
    return out


def coverage_snapshot(strategy: str, test_issue: str, legs: list[Leg], tickets: list[Ticket], decisions: list[dict[str, object]]) -> dict[str, object]:
    use_counts: Counter[str] = Counter()
    for ticket in tickets:
        for leg in ticket.legs:
            use_counts[leg.leg_id] += 1
    decision_counts = Counter(str(row["decision"]) for row in decisions)
    avg_cover = sum(float(row["cover_count"]) for row in decisions) / len(decisions) if decisions else float("nan")
    return {
        "strategy": strategy,
        "test_issue": test_issue,
        "n_policy_legs": len(legs),
        "n_tickets": len(tickets),
        "avg_score_factor": sum(leg.score_factor for leg in legs) / len(legs) if legs else float("nan"),
        "avg_model_p": sum(leg.p_hat for leg in legs) / len(legs) if legs else float("nan"),
        "avg_cover_count": avg_cover,
        "n_single": decision_counts.get("single", 0),
        "n_double": decision_counts.get("double", 0),
        "n_full": decision_counts.get("full", 0),
        "top1_agree_rate": top_agree_rate(legs),
        "avg_depth_weight": avg_depth_weight(legs),
        "max_leg_use_in_tickets": max_leg_use_in_tickets(tickets),
        "avg_pair_overlap": avg_pair_overlap(tickets),
        "distinct_legs_used": len(use_counts),
    }


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
        "excess_roi_vs_baseline",
        "best_issue_profit_share",
        "avg_issue_stake_units",
        "max_drawdown_pct_on_10000",
        "max_ticket_loss_streak",
        "avg_full_cover_per_ticket",
        "avg_double_cover_per_ticket",
        "verdict",
    ]
    return [{k: row.get(k, "") for k in keep} for row in summary]


def budget_sweep_summary(ticket_rows: list[dict[str, object]], budgets: list[float]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for budget in budgets:
        for fractional in (False, True):
            mode = "fractional" if fractional else "whole"
            rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=budget, fractional=fractional)
            for row in summarize_tickets(rows):
                converted = dict(row)
                converted["budget_mode"] = mode
                converted["issue_budget_units"] = budget
                out.append(converted)
    out.sort(
        key=lambda row: (
            float(row["issue_budget_units"]),
            str(row["budget_mode"]),
            -float(row["roi"]) if math.isfinite(float(row["roi"])) else 999.0,
        )
    )
    return out


def compact_budget_sweep(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "issue_budget_units",
        "budget_mode",
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
    profiles = parse_strings(args.profiles)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    coverage_threshold = threshold * args.min_coverage_score_ratio

    ticket_rows: list[dict[str, object]] = []
    issue_rows_window: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []

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
        sp_model = train_sp_drift_model(
            train_action_rows,
            snapshot=args.snapshot,
            feature_set=args.sp_feature_set,
            prior_n=args.sp_prior_n,
            min_multiplier=args.min_sp_multiplier,
            max_multiplier=args.max_sp_multiplier,
        )
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

        probs = decision_probabilities(args, train_samples, test_samples)
        market = snapshot_market_probabilities(test_samples, args.snapshot)
        samples_by_match = {sample.match_id: sample for sample in test_samples}
        probs_by_match = {sample.match_id: probs[i] for i, sample in enumerate(test_samples)}
        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        action_lookup = action_lookup_for_issue(test_action_rows)

        base_legs, base_weights = transform_legs_for_depth(
            q_legs,
            policy=args.depth_policy,
            probs_by_match=probs_by_match,
            market_by_match=market_by_match,
            min_score_factor=threshold,
        )
        base_strategy = f"confidence_{args.depth_policy}"
        base_tickets = make_depth_weighted_tickets(
            base_legs,
            depth_weights=base_weights,
            strategy=base_strategy,
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            max_leg_uses=args.max_depth_leg_uses,
            max_ticket_overlap=args.max_depth_ticket_overlap,
        )
        ticket_rows.extend(settle_ticket(ticket) for ticket in base_tickets)
        coverage_rows.append(coverage_snapshot(base_strategy, test_issue, base_legs, base_tickets, []))

        for profile in profiles:
            joint_legs: list[Leg] = []
            joint_weights: dict[str, float] = {}
            issue_decisions: list[dict[str, object]] = []
            for leg in base_legs:
                sample = samples_by_match.get(leg.row.match_id)
                p = probs_by_match.get(leg.row.match_id)
                m = market_by_match.get(leg.row.match_id)
                if sample is None or p is None or m is None:
                    continue
                chosen = choose_coverage(
                    leg=leg,
                    sample=sample,
                    probs=p,
                    market=m,
                    action_lookup=action_lookup,
                    sp_model=sp_model,
                    snapshot=args.snapshot,
                    profile=profile,
                    threshold=threshold,
                    coverage_threshold=coverage_threshold,
                    max_odds=args.max_stable_odds,
                    min_multiplier=args.min_stable_multiplier,
                    max_abs_log_move=args.max_abs_log_move,
                    min_stability_score=args.min_stability_score,
                    min_anchor_score_ratio=args.min_anchor_score_ratio,
                    directional_drift=not args.disable_directional_drift,
                    positive_move_penalty=args.positive_move_penalty,
                    negative_move_bonus=args.negative_move_bonus,
                    min_positive_move_component=args.min_positive_move_component,
                    max_negative_move_component=args.max_negative_move_component,
                )
                if chosen is None:
                    continue
                new_leg, depth_weight, metrics = chosen
                joint_legs.append(new_leg)
                joint_weights[new_leg.leg_id] = base_weights.get(leg.leg_id, 1.0) * depth_weight
                metrics = dict(metrics)
                metrics.update({"test_issue": test_issue, "train_start_issue": train_issues[0], "train_end_issue": train_issues[-1]})
                issue_decisions.append(metrics)
                decision_rows.append(metrics)

            strategy = f"joint_uncertainty_{profile}"
            tickets = make_depth_weighted_tickets(
                joint_legs,
                depth_weights=joint_weights,
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
            ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)
            coverage_rows.append(coverage_snapshot(strategy, test_issue, joint_legs, tickets, issue_decisions))

        issue_rows_window.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "n_base_legs": len(base_legs),
                "n_base_tickets": len(base_tickets),
            }
        )

    summary = summarize_tickets(ticket_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    issue_profit = issue_profit_rows(ticket_rows)
    budget_whole_rows = budgeted_ticket_rows(
        ticket_rows,
        issue_budget_units=args.issue_budget_units,
        fractional=False,
    )
    budget_fractional_rows = budgeted_ticket_rows(
        ticket_rows,
        issue_budget_units=args.issue_budget_units,
        fractional=True,
    )
    budget_whole_summary = summarize_tickets(budget_whole_rows)
    budget_whole_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    budget_fractional_summary = summarize_tickets(budget_fractional_rows)
    budget_fractional_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    budget_whole_issue_profit = issue_profit_rows(budget_whole_rows)
    budget_fractional_issue_profit = issue_profit_rows(budget_fractional_rows)
    sweep_summary = budget_sweep_summary(ticket_rows, parse_floats(args.budget_sweep_units))

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "joint_uncertainty_tickets.csv", ticket_rows)
    write_csv(out / "joint_uncertainty_summary.csv", summary)
    write_csv(out / "joint_uncertainty_issue_profit.csv", issue_profit)
    write_csv(out / "joint_uncertainty_budget_whole_tickets.csv", budget_whole_rows)
    write_csv(out / "joint_uncertainty_budget_whole_summary.csv", budget_whole_summary)
    write_csv(out / "joint_uncertainty_budget_whole_issue_profit.csv", budget_whole_issue_profit)
    write_csv(out / "joint_uncertainty_budget_fractional_tickets.csv", budget_fractional_rows)
    write_csv(out / "joint_uncertainty_budget_fractional_summary.csv", budget_fractional_summary)
    write_csv(out / "joint_uncertainty_budget_fractional_issue_profit.csv", budget_fractional_issue_profit)
    write_csv(out / "joint_uncertainty_budget_sweep_summary.csv", sweep_summary)
    write_csv(out / "joint_uncertainty_coverage.csv", coverage_rows)
    write_csv(out / "joint_uncertainty_windows.csv", issue_rows_window)
    write_csv(out / "joint_uncertainty_decisions.csv", decision_rows)

    report = [
        "# N=7 joint uncertainty depth evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Depth policy: `{args.depth_policy}`",
        f"- Profiles: `{args.profiles}`",
        f"- Same-budget issue stake: `{args.issue_budget_units}` units",
        f"- Coverage score threshold ratio: `{args.min_coverage_score_ratio}`",
        f"- Directional drift: `{not args.disable_directional_drift}` "
        f"(positive_move_penalty={args.positive_move_penalty}, negative_move_bonus={args.negative_move_bonus})",
        f"- Stable gate: max_odds={args.max_stable_odds}, min_multiplier={args.min_stable_multiplier}, "
        f"max_abs_log_move={args.max_abs_log_move}, min_stability_score={args.min_stability_score}",
        "",
        "## Raw Summary",
        md_table(compact_summary(summary)),
        "## Same Budget Whole-Ticket Summary",
        md_table(compact_summary(budget_whole_summary)),
        "## Same Budget Fractional Summary",
        md_table(compact_summary(budget_fractional_summary)),
        "## Budget Sweep Summary",
        md_table(compact_budget_sweep(sweep_summary)),
        "## Coverage",
        md_table(coverage_rows[:80]),
        "## Files",
        "",
        "- `joint_uncertainty_summary.csv`",
        "- `joint_uncertainty_tickets.csv`",
        "- `joint_uncertainty_issue_profit.csv`",
        "- `joint_uncertainty_budget_whole_summary.csv`",
        "- `joint_uncertainty_budget_whole_tickets.csv`",
        "- `joint_uncertainty_budget_whole_issue_profit.csv`",
        "- `joint_uncertainty_budget_fractional_summary.csv`",
        "- `joint_uncertainty_budget_fractional_tickets.csv`",
        "- `joint_uncertainty_budget_fractional_issue_profit.csv`",
        "- `joint_uncertainty_budget_sweep_summary.csv`",
        "- `joint_uncertainty_coverage.csv`",
        "- `joint_uncertainty_windows.csv`",
        "- `joint_uncertainty_decisions.csv`",
        "",
    ]
    (out / "joint_uncertainty_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'joint_uncertainty_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_joint_uncertainty_depth"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--issue-budget-units", type=float, default=20.0)
    parser.add_argument("--budget-sweep-units", default="20,50,100,200")
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="1h")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--model-source", choices=("snapshot_market", "multiclass", "ovr_shared", "ovr_separate"), default="snapshot_market")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--profiles", default="conservative,balanced,aggressive")
    parser.add_argument("--sp-feature-set", choices=("action_odds", "action_odds_move"), default="action_odds_move")
    parser.add_argument("--sp-prior-n", type=int, default=80)
    parser.add_argument("--min-sp-multiplier", type=float, default=0.15)
    parser.add_argument("--max-sp-multiplier", type=float, default=2.50)
    parser.add_argument("--max-stable-odds", type=float, default=5.0)
    parser.add_argument("--min-stable-multiplier", type=float, default=0.75)
    parser.add_argument("--max-abs-log-move", type=float, default=0.20)
    parser.add_argument("--min-stability-score", type=float, default=0.55)
    parser.add_argument("--min-anchor-score-ratio", type=float, default=0.95)
    parser.add_argument("--min-coverage-score-ratio", type=float, default=1.0)
    parser.add_argument("--disable-directional-drift", action="store_true")
    parser.add_argument("--positive-move-penalty", type=float, default=2.0)
    parser.add_argument("--negative-move-bonus", type=float, default=1.0)
    parser.add_argument("--min-positive-move-component", type=float, default=0.60)
    parser.add_argument("--max-negative-move-component", type=float, default=1.20)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
