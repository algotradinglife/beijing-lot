#!/usr/bin/env python3
"""Evaluate whether estimated settlement-SP drift should affect N=7 coverage depth."""
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

from scripts.evaluate_n7_confidence_coverage import (
    avg_depth_weight,
    avg_pair_overlap,
    make_depth_weighted_tickets,
    max_leg_use_in_tickets,
    model_probabilities,
    top_agree_rate,
    transform_legs_for_depth,
)
from scripts.walkforward_beidan_result_model_eval import build_samples, load_match_extras, market_probs
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
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
    snapshot_odds_p,
    summarize_tickets,
    train_q_model,
    write_csv,
)


SINGLE_ACTIONS = {"3", "1", "0"}


@dataclass(frozen=True)
class SpDriftModel:
    key_log_mean: dict[tuple[str, ...], float]
    action_log_mean: dict[str, float]
    global_log_mean: float
    feature_set: str
    snapshot: str
    min_multiplier: float
    max_multiplier: float


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def odds_bucket(odds: float) -> str:
    if odds < 2.0:
        return "<2"
    if odds < 3.0:
        return "2-3"
    if odds < 4.0:
        return "3-4"
    if odds < 6.0:
        return "4-6"
    if odds < 8.0:
        return "6-8"
    return ">=8"


def move_bucket(row: ActionRow, snapshot: str) -> str:
    if snapshot == "10h":
        return "no_move"
    if snapshot == "1h":
        base = row.euro_10h_odds
        current = row.euro_1h_odds
    elif snapshot == "final":
        base = row.euro_10h_odds
        current = row.euro_final_odds
    else:
        raise ValueError(f"unsupported snapshot: {snapshot}")
    if base is None or current is None or base <= 1.0 or current <= 1.0:
        return "missing"
    move = math.log(current / base)
    if move < -0.15:
        return "<-15%"
    if move < -0.05:
        return "-15~-5%"
    if move <= 0.05:
        return "-5~5%"
    if move <= 0.15:
        return "5~15%"
    return ">15%"


def sp_key(row: ActionRow, snapshot: str, feature_set: str) -> tuple[str, ...] | None:
    odds, _ = snapshot_odds_p(row, snapshot)
    if odds is None or odds <= 1.0:
        return None
    base = (row.action_code, odds_bucket(odds))
    if feature_set == "action_odds":
        return base
    if feature_set == "action_odds_move":
        return (*base, move_bucket(row, snapshot))
    raise ValueError(f"unsupported SP feature set: {feature_set}")


def train_sp_drift_model(
    rows: list[ActionRow],
    *,
    snapshot: str,
    feature_set: str,
    prior_n: int,
    min_multiplier: float,
    max_multiplier: float,
) -> SpDriftModel:
    by_key: dict[tuple[str, ...], list[float]] = defaultdict(list)
    by_action: dict[str, list[float]] = defaultdict(list)
    global_values: list[float] = []
    for row in rows:
        if row.action_code not in SINGLE_ACTIONS or row.hit != 1:
            continue
        odds, _ = snapshot_odds_p(row, snapshot)
        if odds is None or odds <= 1.0 or row.winning_sp <= 0:
            continue
        multiplier = row.winning_sp / odds
        if multiplier <= 0 or not math.isfinite(multiplier):
            continue
        value = math.log(max(min_multiplier, min(max_multiplier, multiplier)))
        key = sp_key(row, snapshot, feature_set)
        if key is None:
            continue
        by_key[key].append(value)
        by_action[row.action_code].append(value)
        global_values.append(value)

    global_log_mean = sum(global_values) / len(global_values) if global_values else 0.0
    action_log_mean = {
        action: sum(values) / len(values)
        for action, values in by_action.items()
        if values
    }
    key_log_mean = {}
    for key, values in by_key.items():
        action = key[0]
        prior = action_log_mean.get(action, global_log_mean)
        raw = sum(values) / len(values)
        key_log_mean[key] = (raw * len(values) + prior * prior_n) / (len(values) + prior_n)
    return SpDriftModel(
        key_log_mean=key_log_mean,
        action_log_mean=action_log_mean,
        global_log_mean=global_log_mean,
        feature_set=feature_set,
        snapshot=snapshot,
        min_multiplier=min_multiplier,
        max_multiplier=max_multiplier,
    )


def predict_sp_multiplier(model: SpDriftModel, row: ActionRow) -> float:
    key = sp_key(row, model.snapshot, model.feature_set)
    log_value = None if key is None else model.key_log_mean.get(key)
    if log_value is None:
        log_value = model.action_log_mean.get(row.action_code, model.global_log_mean)
    multiplier = math.exp(log_value)
    return max(model.min_multiplier, min(model.max_multiplier, multiplier))


def sp_adjusted_leg(
    leg: Leg,
    *,
    sp_model: SpDriftModel,
    min_score_factor: float,
    filter_on_score: bool,
) -> Leg | None:
    multiplier = predict_sp_multiplier(sp_model, leg.row)
    score = leg.score_factor * multiplier
    if filter_on_score and score < min_score_factor:
        return None
    return replace(
        leg,
        strategy=f"{leg.strategy}_sp_entry",
        score_factor=score,
        source_rule=f"{leg.source_rule};sp_mult={multiplier:.4f};sp_score={score:.4f}",
    )


def odds_move_log(row: ActionRow, snapshot: str) -> float | None:
    if snapshot == "10h":
        return None
    current, _ = snapshot_odds_p(row, snapshot)
    base = row.euro_10h_odds
    if base is None or current is None or base <= 1.0 or current <= 1.0:
        return None
    return math.log(current / base)


def odds_stability_component(odds: float) -> float:
    if odds < 3.5:
        return 1.10
    if odds < 4.5:
        return 1.00
    if odds < 5.0:
        return 0.75
    if odds < 8.0:
        return 0.45
    return 0.20


def move_stability_component(move_log: float | None) -> float:
    if move_log is None:
        return 1.0
    return max(0.25, min(1.15, math.exp(-abs(move_log) / 0.16)))


def sp_stability_metrics(leg: Leg, sp_model: SpDriftModel) -> dict[str, float | str]:
    odds, _ = snapshot_odds_p(leg.row, sp_model.snapshot)
    if odds is None or odds <= 1.0:
        return {
            "odds": float("nan"),
            "move_log": float("nan"),
            "pred_multiplier": float("nan"),
            "stability_score": float("nan"),
            "reason": "missing_odds",
        }
    move_log = odds_move_log(leg.row, sp_model.snapshot)
    multiplier = predict_sp_multiplier(sp_model, leg.row)
    stability_score = multiplier * odds_stability_component(odds) * move_stability_component(move_log)
    return {
        "odds": odds,
        "move_log": move_log if move_log is not None else float("nan"),
        "pred_multiplier": multiplier,
        "stability_score": stability_score,
        "reason": "pass",
    }


def stable_sp_leg(
    leg: Leg,
    *,
    sp_model: SpDriftModel,
    min_score_factor: float,
    max_odds: float,
    min_multiplier: float,
    max_abs_move_log: float,
    min_stability_score: float,
    filter_on_score: bool,
) -> Leg | None:
    metrics = sp_stability_metrics(leg, sp_model)
    odds = float(metrics["odds"])
    multiplier = float(metrics["pred_multiplier"])
    stability_score = float(metrics["stability_score"])
    move_log = float(metrics["move_log"])
    if not math.isfinite(odds) or odds > max_odds:
        return None
    if not math.isfinite(multiplier) or multiplier < min_multiplier:
        return None
    if math.isfinite(move_log) and abs(move_log) > max_abs_move_log:
        return None
    if not math.isfinite(stability_score) or stability_score < min_stability_score:
        return None
    score = leg.score_factor * multiplier
    if filter_on_score and score < min_score_factor:
        return None
    return replace(
        leg,
        strategy=f"{leg.strategy}_sp_stable",
        score_factor=score,
        source_rule=(
            f"{leg.source_rule};sp_stable_mult={multiplier:.4f};"
            f"sp_stable_score={stability_score:.4f};sp_stable_odds={odds:.3f};"
            f"sp_stable_move_log={move_log:.4f}"
        ),
    )


def stable_depth_weight(
    base_weight: float,
    *,
    stability_score: float,
    alpha: float,
    min_weight: float,
    max_weight: float,
) -> float:
    if not math.isfinite(stability_score) or stability_score <= 0:
        return base_weight * min_weight
    return base_weight * max(min_weight, min(max_weight, stability_score**alpha))


def adjust_depth_weights(
    legs: list[Leg],
    depth_weights: dict[str, float],
    *,
    sp_model: SpDriftModel,
    alpha: float,
    min_weight: float,
    max_weight: float,
) -> dict[str, float]:
    adjusted = dict(depth_weights)
    for leg in legs:
        multiplier = predict_sp_multiplier(sp_model, leg.row)
        sp_weight = max(min_weight, min(max_weight, multiplier**alpha))
        adjusted[leg.leg_id] = adjusted.get(leg.leg_id, 1.0) * sp_weight
    return adjusted


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
        "verdict",
    ]
    return [{k: row.get(k, "") for k in keep} for row in summary]


def coverage_snapshot(strategy: str, test_issue: str, legs: list[Leg], tickets: list[Ticket]) -> dict[str, object]:
    use_counts: Counter[str] = Counter()
    for ticket in tickets:
        for leg in ticket.legs:
            use_counts[leg.leg_id] += 1
    return {
        "strategy": strategy,
        "test_issue": test_issue,
        "n_policy_legs": len(legs),
        "n_tickets": len(tickets),
        "avg_score_factor": sum(leg.score_factor for leg in legs) / len(legs) if legs else float("nan"),
        "avg_model_p": sum(leg.p_hat for leg in legs) / len(legs) if legs else float("nan"),
        "top1_agree_rate": top_agree_rate(legs),
        "avg_depth_weight": avg_depth_weight(legs),
        "max_leg_use_in_tickets": max_leg_use_in_tickets(tickets),
        "avg_pair_overlap": avg_pair_overlap(tickets),
        "distinct_legs_used": len(use_counts),
    }


def append_sp_eval_rows(out: list[dict[str, object]], rows: list[ActionRow], model: SpDriftModel, issue: str) -> None:
    for row in rows:
        if row.action_code not in SINGLE_ACTIONS or row.hit != 1:
            continue
        odds, _ = snapshot_odds_p(row, model.snapshot)
        if odds is None or odds <= 1.0:
            continue
        actual = row.winning_sp / odds
        pred = predict_sp_multiplier(model, row)
        if actual <= 0 or not math.isfinite(actual):
            continue
        out.append(
            {
                "issue": issue,
                "match_id": row.match_id,
                "action_code": row.action_code,
                "snapshot": model.snapshot,
                "feature_set": model.feature_set,
                "odds": odds,
                "odds_bucket": odds_bucket(odds),
                "move_bucket": move_bucket(row, model.snapshot),
                "actual_multiplier": actual,
                "pred_multiplier": pred,
                "log_error": math.log(pred) - math.log(actual),
                "abs_log_error": abs(math.log(pred) - math.log(actual)),
            }
        )


def sp_metric_rows(eval_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in eval_rows:
        grouped["ALL"].append(row)
        grouped[str(row["action_code"])].append(row)
    out = []
    for group, rows in sorted(grouped.items()):
        actual = np.asarray([float(r["actual_multiplier"]) for r in rows], dtype=float)
        pred = np.asarray([float(r["pred_multiplier"]) for r in rows], dtype=float)
        log_error = np.asarray([float(r["log_error"]) for r in rows], dtype=float)
        abs_log_error = np.abs(log_error)
        corr = float(np.corrcoef(np.log(actual), np.log(pred))[0, 1]) if len(rows) > 1 and np.std(pred) > 0 else float("nan")
        out.append(
            {
                "group": group,
                "n": len(rows),
                "actual_mean": float(np.mean(actual)) if len(rows) else float("nan"),
                "pred_mean": float(np.mean(pred)) if len(rows) else float("nan"),
                "mae": float(np.mean(np.abs(pred - actual))) if len(rows) else float("nan"),
                "rmse": float(np.sqrt(np.mean((pred - actual) ** 2))) if len(rows) else float("nan"),
                "mean_log_error": float(np.mean(log_error)) if len(rows) else float("nan"),
                "mean_abs_log_error": float(np.mean(abs_log_error)) if len(rows) else float("nan"),
                "log_corr": corr,
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    ticket_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    sp_eval_rows: list[dict[str, object]] = []
    depth_policies = parse_strings(args.depth_policies)

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
        model_probs_by_match = {sample.match_id: model_probs[i] for i, sample in enumerate(test_samples)}
        market_probs_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}

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
        ticket_rows.extend(settle_ticket(ticket) for ticket in base_tickets)
        coverage_rows.append(coverage_snapshot("baseline_q_high_sp", test_issue, q_legs, base_tickets))

        sp_entry_legs = [
            converted
            for leg in q_legs
            if (
                converted := sp_adjusted_leg(
                    leg,
                    sp_model=sp_model,
                    min_score_factor=threshold,
                    filter_on_score=True,
                )
            )
            is not None
        ]
        sp_entry_tickets = make_tickets(
            sp_entry_legs,
            strategy="baseline_q_sp_entry",
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
        ticket_rows.extend(settle_ticket(ticket) for ticket in sp_entry_tickets)
        coverage_rows.append(coverage_snapshot("baseline_q_sp_entry", test_issue, sp_entry_legs, sp_entry_tickets))

        stable_entry_legs = [
            converted
            for leg in q_legs
            if (
                converted := stable_sp_leg(
                    leg,
                    sp_model=sp_model,
                    min_score_factor=threshold,
                    max_odds=args.stable_sp_max_odds,
                    min_multiplier=args.stable_sp_min_multiplier,
                    max_abs_move_log=args.stable_sp_max_abs_log_move,
                    min_stability_score=args.stable_sp_min_score,
                    filter_on_score=args.stable_sp_filter_on_score,
                )
            )
            is not None
        ]
        stable_entry_tickets = make_tickets(
            stable_entry_legs,
            strategy="baseline_q_sp_stable",
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
        ticket_rows.extend(settle_ticket(ticket) for ticket in stable_entry_tickets)
        coverage_rows.append(coverage_snapshot("baseline_q_sp_stable", test_issue, stable_entry_legs, stable_entry_tickets))

        depth_counts = {}
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
            ticket_rows.extend(settle_ticket(ticket) for ticket in depth_tickets)
            coverage_rows.append(coverage_snapshot(depth_strategy, test_issue, depth_legs, depth_tickets))
            depth_counts[depth_strategy] = len(depth_tickets)

            sp_depth_weights = adjust_depth_weights(
                depth_legs,
                depth_weights,
                sp_model=sp_model,
                alpha=args.sp_depth_alpha,
                min_weight=args.min_sp_depth_weight,
                max_weight=args.max_sp_depth_weight,
            )
            sp_depth_strategy = f"{depth_strategy}_sp_depth"
            sp_depth_tickets = make_depth_weighted_tickets(
                depth_legs,
                depth_weights=sp_depth_weights,
                strategy=sp_depth_strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                max_leg_uses=args.max_depth_leg_uses if policy.startswith("depth_constrained") else 0,
                max_ticket_overlap=args.max_depth_ticket_overlap if policy.startswith("depth_constrained") else 0,
            )
            ticket_rows.extend(settle_ticket(ticket) for ticket in sp_depth_tickets)
            coverage_rows.append(coverage_snapshot(sp_depth_strategy, test_issue, depth_legs, sp_depth_tickets))
            depth_counts[sp_depth_strategy] = len(sp_depth_tickets)

            sp_entry_depth_legs = [
                converted
                for leg in depth_legs
                if (
                    converted := sp_adjusted_leg(
                        leg,
                        sp_model=sp_model,
                        min_score_factor=threshold,
                        filter_on_score=True,
                    )
                )
                is not None
            ]
            sp_entry_depth_weights = {
                leg.leg_id: sp_depth_weights.get(leg.leg_id, 1.0)
                for leg in sp_entry_depth_legs
            }
            sp_entry_depth_strategy = f"{depth_strategy}_sp_entry_depth"
            sp_entry_depth_tickets = make_depth_weighted_tickets(
                sp_entry_depth_legs,
                depth_weights=sp_entry_depth_weights,
                strategy=sp_entry_depth_strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                max_leg_uses=args.max_depth_leg_uses if policy.startswith("depth_constrained") else 0,
                max_ticket_overlap=args.max_depth_ticket_overlap if policy.startswith("depth_constrained") else 0,
            )
            ticket_rows.extend(settle_ticket(ticket) for ticket in sp_entry_depth_tickets)
            coverage_rows.append(coverage_snapshot(sp_entry_depth_strategy, test_issue, sp_entry_depth_legs, sp_entry_depth_tickets))
            depth_counts[sp_entry_depth_strategy] = len(sp_entry_depth_tickets)

            stable_entry_depth_legs = [
                converted
                for leg in depth_legs
                if (
                    converted := stable_sp_leg(
                        leg,
                        sp_model=sp_model,
                        min_score_factor=threshold,
                        max_odds=args.stable_sp_max_odds,
                        min_multiplier=args.stable_sp_min_multiplier,
                        max_abs_move_log=args.stable_sp_max_abs_log_move,
                        min_stability_score=args.stable_sp_min_score,
                        filter_on_score=args.stable_sp_filter_on_score,
                    )
                )
                is not None
            ]
            stable_entry_depth_weights = {}
            for leg in stable_entry_depth_legs:
                metrics = sp_stability_metrics(leg, sp_model)
                stable_entry_depth_weights[leg.leg_id] = stable_depth_weight(
                    depth_weights.get(leg.leg_id, 1.0),
                    stability_score=float(metrics["stability_score"]),
                    alpha=args.stable_sp_depth_alpha,
                    min_weight=args.stable_sp_min_depth_weight,
                    max_weight=args.stable_sp_max_depth_weight,
                )
            stable_entry_depth_strategy = f"{depth_strategy}_sp_stable"
            stable_entry_depth_tickets = make_depth_weighted_tickets(
                stable_entry_depth_legs,
                depth_weights=stable_entry_depth_weights,
                strategy=stable_entry_depth_strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                max_leg_uses=args.max_depth_leg_uses if policy.startswith("depth_constrained") else 0,
                max_ticket_overlap=args.max_depth_ticket_overlap if policy.startswith("depth_constrained") else 0,
            )
            ticket_rows.extend(settle_ticket(ticket) for ticket in stable_entry_depth_tickets)
            coverage_rows.append(coverage_snapshot(stable_entry_depth_strategy, test_issue, stable_entry_depth_legs, stable_entry_depth_tickets))
            depth_counts[stable_entry_depth_strategy] = len(stable_entry_depth_tickets)

        row = {
            "test_issue": test_issue,
            "train_start_issue": train_issues[0],
            "train_end_issue": train_issues[-1],
            "snapshot": args.snapshot,
            "sp_feature_set": args.sp_feature_set,
            "n_train_matches": len(train_samples),
            "n_test_matches": len(test_samples),
            "n_q_legs": len(q_legs),
            "n_base_tickets": len(base_tickets),
            "n_sp_entry_legs": len(sp_entry_legs),
            "n_sp_entry_tickets": len(sp_entry_tickets),
            "n_sp_stable_legs": len(stable_entry_legs),
            "n_sp_stable_tickets": len(stable_entry_tickets),
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
    write_csv(out / "sp_depth_tickets.csv", ticket_rows)
    write_csv(out / "sp_depth_summary.csv", summary)
    write_csv(out / "sp_depth_issue_profit.csv", issue_rows)
    write_csv(out / "sp_depth_coverage.csv", coverage_rows)
    write_csv(out / "sp_depth_windows.csv", window_rows)
    write_csv(out / "sp_prediction_rows.csv", sp_eval_rows)
    write_csv(out / "sp_prediction_metrics.csv", sp_metrics)

    report = [
        "# N=7 SP drift depth evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- SP feature set: `{args.sp_feature_set}`",
        f"- SP prior N: `{args.sp_prior_n}`",
        f"- SP depth alpha: `{args.sp_depth_alpha}`",
        f"- Stable SP max odds: `{args.stable_sp_max_odds}`",
        f"- Stable SP min multiplier: `{args.stable_sp_min_multiplier}`",
        f"- Stable SP max abs log move: `{args.stable_sp_max_abs_log_move}`",
        f"- Stable SP min score: `{args.stable_sp_min_score}`",
        f"- Depth policies: `{args.depth_policies}`",
        "",
        "## Strategy Summary",
        md_table(compact_summary(summary)),
        "## SP Prediction Metrics",
        md_table(sp_metrics),
        "## Files",
        "",
        "- `sp_depth_summary.csv`",
        "- `sp_depth_tickets.csv`",
        "- `sp_depth_issue_profit.csv`",
        "- `sp_depth_coverage.csv`",
        "- `sp_depth_windows.csv`",
        "- `sp_prediction_rows.csv`",
        "- `sp_prediction_metrics.csv`",
        "",
    ]
    (out / "sp_depth_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'sp_depth_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_sp_drift_depth"))
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
    parser.add_argument("--sp-feature-set", choices=("action_odds", "action_odds_move"), default="action_odds_move")
    parser.add_argument("--sp-prior-n", type=int, default=80)
    parser.add_argument("--min-sp-multiplier", type=float, default=0.15)
    parser.add_argument("--max-sp-multiplier", type=float, default=2.50)
    parser.add_argument("--sp-depth-alpha", type=float, default=0.50)
    parser.add_argument("--min-sp-depth-weight", type=float, default=0.60)
    parser.add_argument("--max-sp-depth-weight", type=float, default=1.60)
    parser.add_argument("--stable-sp-max-odds", type=float, default=5.0)
    parser.add_argument("--stable-sp-min-multiplier", type=float, default=0.75)
    parser.add_argument("--stable-sp-max-abs-log-move", type=float, default=0.20)
    parser.add_argument("--stable-sp-min-score", type=float, default=0.55)
    parser.add_argument("--stable-sp-filter-on-score", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--stable-sp-depth-alpha", type=float, default=0.50)
    parser.add_argument("--stable-sp-min-depth-weight", type=float, default=0.65)
    parser.add_argument("--stable-sp-max-depth-weight", type=float, default=1.35)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
