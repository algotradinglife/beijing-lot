#!/usr/bin/env python3
"""Evaluate issue-level risk controls for N=7 q-pocket.

The q-pocket selector and ticket construction stay unchanged. This script only
decides whether a whole issue should be played full size, reduced, or skipped.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import transform_legs_for_depth
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_matchpredict_integration import (
    MatchPredictPoissonModel,
    append_prediction_rows,
    load_match_info,
    probability_summary,
)
from scripts.evaluate_n7_q_pocket_whitelist import (
    GateSpec,
    compact_summary,
    count_tags,
    coverage_snapshot,
    filter_legs_for_spec,
    leg_detail_rows,
    leg_meta,
    make_constrained_depth_tickets,
    parse_gate_specs,
    stress_summary,
    ticket_composition_rows,
)
from scripts.evaluate_n7_sp_drift_depth import (
    odds_move_log,
    predict_sp_multiplier,
    train_sp_drift_model,
)
from scripts.snapshot_pure_result_model import fit_predict_snapshot_pure, snapshot_market_probabilities
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras
from scripts.walkforward_beidan_strategy_eval import (
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    dedup_legs_by_match,
    default_db_path,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def normalize_probs(probs: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probs, dtype=float), 1e-9, 1.0)
    return clipped / clipped.sum(axis=1, keepdims=True)


def probability_by_match(samples, probs: np.ndarray) -> dict[int, np.ndarray]:
    return {sample.match_id: probs[i] for i, sample in enumerate(samples)}


def mean(values: list[float]) -> float:
    vals = [v for v in values if math.isfinite(v)]
    return sum(vals) / len(vals) if vals else float("nan")


def quantile(values: list[float], q: float) -> float:
    vals = [v for v in values if math.isfinite(v)]
    return float(np.quantile(vals, q)) if vals else float("nan")


def selected_model_metrics(
    leg: Leg,
    *,
    model_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
) -> dict[str, float]:
    probs = model_by_match.get(leg.row.match_id)
    market = market_by_match.get(leg.row.match_id)
    if probs is None or market is None:
        return {
            "model_ratio": float("nan"),
            "top1_agree": 0.0,
            "top2_agree": 0.0,
            "selected_model_p": float("nan"),
            "selected_market_p": float("nan"),
        }
    idx = OUTCOMES.index(leg.row.action_code)
    ranked = [int(v) for v in np.argsort(-probs)]
    selected_model_p = float(probs[idx])
    selected_market_p = float(market[idx])
    return {
        "model_ratio": selected_model_p / max(selected_market_p, 1e-9),
        "top1_agree": 1.0 if idx == ranked[0] else 0.0,
        "top2_agree": 1.0 if idx in set(ranked[:2]) else 0.0,
        "selected_model_p": selected_model_p,
        "selected_market_p": selected_market_p,
    }


def finite_rate(values: list[float], predicate) -> float:
    vals = [v for v in values if math.isfinite(v)]
    return sum(1 for v in vals if predicate(v)) / len(vals) if vals else float("nan")


def issue_risk_row(
    *,
    strategy: str,
    issue: str,
    spec: GateSpec,
    q_legs: list[Leg],
    policy_legs: list[Leg],
    tickets: list[Ticket],
    metas: dict[str, object],
    model_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    sp_model,
    threshold: float,
    args: argparse.Namespace,
) -> dict[str, object]:
    legs = dedup_legs_by_match(policy_legs)
    tag_counts = count_tags(legs, metas)
    pocket_counts: Counter[str] = Counter()
    model_ratios: list[float] = []
    selected_model_ps: list[float] = []
    selected_market_ps: list[float] = []
    top1: list[float] = []
    top2: list[float] = []
    multipliers: list[float] = []
    move_logs: list[float] = []
    score_margins: list[float] = []

    for leg in legs:
        meta = metas.get(leg.leg_id)
        if meta is not None:
            pocket_counts[meta.pocket] += 1
        m = selected_model_metrics(leg, model_by_match=model_by_match, market_by_match=market_by_match)
        model_ratios.append(float(m["model_ratio"]))
        selected_model_ps.append(float(m["selected_model_p"]))
        selected_market_ps.append(float(m["selected_market_p"]))
        top1.append(float(m["top1_agree"]))
        top2.append(float(m["top2_agree"]))
        multipliers.append(float(predict_sp_multiplier(sp_model, leg.row)))
        move_log = odds_move_log(leg.row, args.snapshot)
        if move_log is not None and math.isfinite(move_log):
            move_logs.append(float(move_log))
        score_margins.append(float(leg.score_factor) / max(threshold, 1e-9) - 1.0)

    n_legs = len(legs)
    max_pocket_share = max(pocket_counts.values()) / n_legs if n_legs and pocket_counts else 0.0
    tailish_rate = (tag_counts["tail"] + tag_counts["draw_tail"]) / n_legs if n_legs else float("nan")
    avg_q_margin = mean(score_margins)
    p10_q_margin = quantile(score_margins, 0.10)
    avg_sp_multiplier = mean(multipliers)
    adverse_sp_rate = finite_rate(multipliers, lambda v: v < args.adverse_sp_multiplier)
    severe_sp_rate = finite_rate(multipliers, lambda v: v < args.severe_sp_multiplier)
    favorable_sp_rate = finite_rate(multipliers, lambda v: v >= args.favorable_sp_multiplier)
    avg_model_ratio = mean(model_ratios)
    low_model_ratio_rate = finite_rate(model_ratios, lambda v: v < args.low_model_ratio)
    top1_agree_rate = mean(top1)
    top2_agree_rate = mean(top2)
    not_top2_rate = 1.0 - top2_agree_rate if math.isfinite(top2_agree_rate) else float("nan")
    avg_move_log = mean(move_logs)
    positive_move_rate = finite_rate(move_logs, lambda v: v > args.adverse_move_log)

    flags: list[str] = []
    if n_legs < args.min_policy_legs_warning:
        flags.append("thin_pool")
    if (
        math.isfinite(avg_q_margin)
        and avg_q_margin < args.min_avg_q_margin
        or math.isfinite(p10_q_margin)
        and p10_q_margin < args.min_p10_q_margin
    ):
        flags.append("low_q_margin")
    if (
        math.isfinite(adverse_sp_rate)
        and adverse_sp_rate >= args.max_adverse_sp_rate
        or math.isfinite(severe_sp_rate)
        and severe_sp_rate >= args.max_severe_sp_rate
        or math.isfinite(avg_sp_multiplier)
        and avg_sp_multiplier < args.min_avg_sp_multiplier
    ):
        flags.append("adverse_sp")
    if (
        math.isfinite(not_top2_rate)
        and not_top2_rate >= args.max_not_top2_rate
        or math.isfinite(low_model_ratio_rate)
        and low_model_ratio_rate >= args.max_low_model_ratio_rate
        or math.isfinite(avg_model_ratio)
        and avg_model_ratio < args.min_avg_model_ratio
    ):
        flags.append("model_conflict")
    if max_pocket_share >= args.max_pocket_share or (
        math.isfinite(tailish_rate) and tailish_rate >= args.max_tailish_rate
    ):
        flags.append("pocket_concentration")
    if args.snapshot == "1h" and (
        math.isfinite(positive_move_rate)
        and positive_move_rate >= args.max_positive_move_rate
        or math.isfinite(avg_move_log)
        and avg_move_log >= args.max_avg_move_log
    ):
        flags.append("up_move")

    risk_score = 0.0
    if math.isfinite(adverse_sp_rate):
        risk_score += 1.20 * adverse_sp_rate
    if math.isfinite(severe_sp_rate):
        risk_score += 0.90 * severe_sp_rate
    if math.isfinite(not_top2_rate):
        risk_score += 0.70 * not_top2_rate
    if math.isfinite(low_model_ratio_rate):
        risk_score += 0.50 * low_model_ratio_rate
    if math.isfinite(avg_model_ratio):
        risk_score += max(0.0, 1.0 - avg_model_ratio)
    if math.isfinite(avg_q_margin):
        risk_score += max(0.0, args.min_avg_q_margin - avg_q_margin) * 8.0
    risk_score += max(0.0, max_pocket_share - 0.45)
    if args.snapshot == "1h" and math.isfinite(positive_move_rate):
        risk_score += 0.60 * positive_move_rate

    return {
        "strategy": strategy,
        "issue": issue,
        "gate_spec": spec.name,
        "n_q_legs": len(q_legs),
        "n_policy_legs": len(policy_legs),
        "n_dedup_policy_legs": n_legs,
        "n_tickets": len(tickets),
        "n_core_legs": tag_counts["core"],
        "n_tail_legs": tag_counts["tail"],
        "n_draw_tail_legs": tag_counts["draw_tail"],
        "tailish_rate": tailish_rate,
        "max_pocket_share": max_pocket_share,
        "avg_q_margin": avg_q_margin,
        "p10_q_margin": p10_q_margin,
        "avg_score_factor": mean([float(leg.score_factor) for leg in legs]),
        "avg_model_ratio": avg_model_ratio,
        "low_model_ratio_rate": low_model_ratio_rate,
        "top1_agree_rate": top1_agree_rate,
        "top2_agree_rate": top2_agree_rate,
        "not_top2_rate": not_top2_rate,
        "avg_selected_model_p": mean(selected_model_ps),
        "avg_selected_market_p": mean(selected_market_ps),
        "avg_sp_multiplier": avg_sp_multiplier,
        "adverse_sp_rate": adverse_sp_rate,
        "severe_sp_rate": severe_sp_rate,
        "favorable_sp_rate": favorable_sp_rate,
        "avg_move_log": avg_move_log,
        "positive_move_rate": positive_move_rate,
        "risk_flag_count": len(flags),
        "risk_flags": ";".join(flags),
        "risk_score": risk_score,
    }


def policy_scale(policy: str, metrics: dict[str, object]) -> float:
    flags = set(str(metrics.get("risk_flags", "")).split(";")) - {""}
    count = int(metrics.get("risk_flag_count", 0))
    adverse_sp = "adverse_sp" in flags
    move_flag = "up_move" in flags or "adverse_move" in flags
    model_conflict = "model_conflict" in flags
    low_q = "low_q_margin" in flags
    concentrated = "pocket_concentration" in flags

    if policy == "full":
        return 1.0
    if policy == "half_any_flag":
        return 0.5 if count >= 1 else 1.0
    if policy == "skip_any_flag":
        return 0.0 if count >= 1 else 1.0
    if policy == "half_2plus":
        return 0.5 if count >= 2 else 1.0
    if policy == "skip_2plus":
        return 0.0 if count >= 2 else 1.0
    if policy == "half_2_skip_3":
        if count >= 3:
            return 0.0
        return 0.5 if count >= 2 else 1.0
    if policy == "sp_half":
        return 0.5 if adverse_sp else 1.0
    if policy == "sp_skip":
        return 0.0 if adverse_sp else 1.0
    if policy == "sp_model_half":
        return 0.5 if adverse_sp or model_conflict else 1.0
    if policy == "sp_model_skip":
        return 0.0 if adverse_sp and model_conflict else 1.0
    if policy == "quality_skip":
        return 0.0 if low_q and (adverse_sp or model_conflict or concentrated) else 1.0
    if policy == "move_flag_only":
        return 1.0 if move_flag else 0.0
    if policy == "move_flag_skip":
        return 0.0 if move_flag else 1.0
    if policy == "move_flag_half_rest":
        return 1.0 if move_flag else 0.5
    raise ValueError(f"unsupported issue-risk policy: {policy}")


def scale_ticket_row(row: dict[str, object], *, strategy_name: str, scale: float, policy: str) -> dict[str, object]:
    converted = dict(row)
    converted["strategy"] = strategy_name
    converted["issue_risk_policy"] = policy
    converted["issue_risk_scale"] = scale
    converted["pre_risk_strategy"] = str(row["strategy"])
    converted["stake_units"] = float(row["stake_units"]) * scale
    converted["payout_units"] = float(row["payout_units"]) * scale
    converted["profit_units"] = float(row["profit_units"]) * scale
    converted["roi"] = (
        float(converted["profit_units"]) / float(converted["stake_units"])
        if float(converted["stake_units"]) > 0
        else float("nan")
    )
    return converted


def apply_issue_risk_policies(
    budget_rows: list[dict[str, object]],
    risk_rows: list[dict[str, object]],
    policies: list[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    risk_by_issue = {
        (str(row["strategy"]), str(row["issue"])): row
        for row in risk_rows
    }
    base_issue_profit: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"stake": 0.0, "profit": 0.0, "hits": 0.0, "tickets": 0.0}
    )
    for row in budget_rows:
        base_strategy = str(row.get("original_strategy", row["strategy"]))
        key = (base_strategy, str(row["issue"]))
        base_issue_profit[key]["stake"] += float(row["stake_units"])
        base_issue_profit[key]["profit"] += float(row["profit_units"])
        base_issue_profit[key]["hits"] += float(row["hit"])
        base_issue_profit[key]["tickets"] += 1.0

    out_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    for key, base_vals in sorted(base_issue_profit.items()):
        base_strategy, issue = key
        metrics = risk_by_issue.get(key)
        if metrics is None:
            continue
        for policy in policies:
            scale = policy_scale(policy, metrics)
            decision_rows.append(
                {
                    "strategy": f"{base_strategy}__risk_{policy}",
                    "base_strategy": base_strategy,
                    "issue": issue,
                    "risk_policy": policy,
                    "scale": scale,
                    "played": int(scale > 0),
                    "risk_flag_count": metrics["risk_flag_count"],
                    "risk_flags": metrics["risk_flags"],
                    "risk_score": metrics["risk_score"],
                    "base_stake_units": base_vals["stake"],
                    "base_profit_units": base_vals["profit"],
                    "scaled_stake_units": base_vals["stake"] * scale,
                    "scaled_profit_units": base_vals["profit"] * scale,
                }
            )

    decision_by = {
        (str(row["base_strategy"]), str(row["issue"]), str(row["risk_policy"])): row
        for row in decision_rows
    }
    for row in budget_rows:
        base_strategy = str(row.get("original_strategy", row["strategy"]))
        issue = str(row["issue"])
        for policy in policies:
            decision = decision_by.get((base_strategy, issue, policy))
            if decision is None:
                continue
            scale = float(decision["scale"])
            if scale <= 0:
                continue
            out_rows.append(
                scale_ticket_row(
                    row,
                    strategy_name=f"{base_strategy}__risk_{policy}",
                    scale=scale,
                    policy=policy,
                )
            )

    decision_summary: list[dict[str, object]] = []
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in decision_rows:
        grouped[str(row["strategy"])].append(row)
    for strategy, rows in sorted(grouped.items()):
        evaluated = len(rows)
        played = sum(int(row["played"]) for row in rows)
        full = sum(1 for row in rows if float(row["scale"]) >= 0.999)
        half = sum(1 for row in rows if 0 < float(row["scale"]) < 0.999)
        skipped = sum(1 for row in rows if float(row["scale"]) <= 0)
        base_stake = sum(float(row["base_stake_units"]) for row in rows)
        scaled_stake = sum(float(row["scaled_stake_units"]) for row in rows)
        base_profit = sum(float(row["base_profit_units"]) for row in rows)
        scaled_profit = sum(float(row["scaled_profit_units"]) for row in rows)
        skipped_profit = sum(float(row["base_profit_units"]) for row in rows if float(row["scale"]) <= 0)
        reduced_profit = sum(
            float(row["base_profit_units"]) * (1.0 - float(row["scale"]))
            for row in rows
            if float(row["scale"]) < 0.999
        )
        decision_summary.append(
            {
                "strategy": strategy,
                "evaluated_issues": evaluated,
                "played_issues": played,
                "full_issues": full,
                "half_issues": half,
                "skipped_issues": skipped,
                "avg_scale": sum(float(row["scale"]) for row in rows) / evaluated if evaluated else float("nan"),
                "base_stake_units": base_stake,
                "scaled_stake_units": scaled_stake,
                "stake_saved_units": base_stake - scaled_stake,
                "base_profit_units": base_profit,
                "scaled_profit_units": scaled_profit,
                "profit_delta_units": scaled_profit - base_profit,
                "skipped_base_profit_units": skipped_profit,
                "reduced_base_profit_units": reduced_profit,
            }
        )
    return out_rows, decision_rows, decision_summary


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    match_info = load_match_info(args.db, args.min_year)
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue: dict[str, list[object]] = defaultdict(list)
    for sample in samples:
        samples_by_issue[sample.issue].append(sample)
    issues = sorted(samples_by_issue)
    gate_specs = parse_gate_specs(args.gate_specs)
    policies = parse_strings(args.risk_policies)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    composition_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    risk_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        if any(issue >= test_issue for issue in train_issues):
            raise RuntimeError(f"leakage guard failed: train={train_issues}, test={test_issue}")
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

        market_probs = snapshot_market_probabilities(test_samples, args.snapshot)
        pure_probs, _ = fit_predict_snapshot_pure(
            train_samples,
            test_samples,
            snapshot=args.snapshot,
            feature_set=args.snapshot_pure_feature_set,
            l2=args.l2,
            maxiter=args.maxiter,
        )
        mp_model = MatchPredictPoissonModel(
            match_info,
            [sample.match_id for sample in train_samples],
            lookback_matches=args.mp_lookback_matches,
            prior_matches=args.mp_prior_matches,
            max_goals=args.mp_max_goals,
            home_advantage=args.mp_home_advantage,
            away_discount=args.mp_away_discount,
        )
        mp_probs = mp_model.predict(test_samples)
        model_probs = normalize_probs((1.0 - args.mp_blend_weight) * pure_probs + args.mp_blend_weight * mp_probs)
        append_prediction_rows(prediction_rows, test_issue, "snapshot_market", test_samples, market_probs)
        append_prediction_rows(prediction_rows, test_issue, "joint_model", test_samples, model_probs)

        market_by_match = probability_by_match(test_samples, market_probs)
        model_by_match = probability_by_match(test_samples, model_probs)
        base_legs, base_weights = transform_legs_for_depth(
            q_legs,
            policy=args.depth_policy,
            probs_by_match=market_by_match,
            market_by_match=market_by_match,
            min_score_factor=threshold,
        )
        if len(base_legs) < args.n_legs:
            continue

        metas = {}
        for leg in base_legs:
            meta = leg_meta(leg, test_action_rows, args.snapshot)
            if meta is not None:
                metas[leg.leg_id] = meta
        candidate_rows.extend(leg_detail_rows(base_legs, metas, "all_q_candidates", test_issue))

        for spec in gate_specs:
            policy_legs = filter_legs_for_spec(base_legs, metas, spec)
            tag_counts = count_tags(policy_legs, metas)
            strategy = f"q_pocket_{spec.name}"
            skipped_reason = ""
            tickets: list[Ticket] = []
            if tag_counts["core"] < spec.min_issue_core_legs:
                skipped_reason = f"core_legs<{spec.min_issue_core_legs}"
            elif len(dedup_legs_by_match(policy_legs)) < args.n_legs:
                skipped_reason = "eligible_legs<n_legs"
            else:
                tickets = make_constrained_depth_tickets(
                    policy_legs,
                    metas=metas,
                    depth_weights=base_weights,
                    spec=spec,
                    strategy=strategy,
                    issue=test_issue,
                    n_legs=args.n_legs,
                    max_tickets=args.max_tickets_per_issue,
                    overlap_penalty=args.overlap_penalty,
                    train_start_issue=train_issues[0],
                    train_end_issue=train_issues[-1],
                    max_leg_uses=args.max_depth_leg_uses,
                )
                if not tickets:
                    skipped_reason = "ticket_constraints_unsatisfied"

            settled = [settle_ticket(ticket) for ticket in tickets]
            ticket_rows.extend(settled)
            composition_rows.extend(ticket_composition_rows(tickets, metas, settled))
            candidate_rows.extend(leg_detail_rows(policy_legs, metas, strategy, test_issue))
            coverage_rows.append(
                coverage_snapshot(
                    strategy=strategy,
                    test_issue=test_issue,
                    q_legs=base_legs,
                    policy_legs=policy_legs,
                    tickets=tickets,
                    metas=metas,
                    skipped_reason=skipped_reason,
                )
            )
            if tickets:
                risk_rows.append(
                    issue_risk_row(
                        strategy=strategy,
                        issue=test_issue,
                        spec=spec,
                        q_legs=base_legs,
                        policy_legs=policy_legs,
                        tickets=tickets,
                        metas=metas,
                        model_by_match=model_by_match,
                        market_by_match=market_by_match,
                        sp_model=sp_model,
                        threshold=threshold,
                        args=args,
                    )
                )

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
    risk_budget_rows, risk_decisions, risk_decision_summary = apply_issue_risk_policies(
        budget_rows,
        risk_rows,
        policies,
    )
    summary = summarize_tickets(risk_budget_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    stress = stress_summary(risk_budget_rows)
    stress_by_strategy = {str(row["strategy"]): row for row in stress}
    issue_profit = issue_profit_rows(risk_budget_rows)
    prob_summary = probability_summary(prediction_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "q_pocket_issue_risk_raw_tickets.csv", ticket_rows)
    write_csv(out / "q_pocket_issue_risk_base_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_issue_risk_budget_rows.csv", risk_budget_rows)
    write_csv(out / "q_pocket_issue_risk_summary.csv", summary)
    write_csv(out / "q_pocket_issue_risk_stress_summary.csv", stress)
    write_csv(out / "q_pocket_issue_risk_issue_profit.csv", issue_profit)
    write_csv(out / "q_pocket_issue_risk_metrics.csv", risk_rows)
    write_csv(out / "q_pocket_issue_risk_decisions.csv", risk_decisions)
    write_csv(out / "q_pocket_issue_risk_decision_summary.csv", risk_decision_summary)
    write_csv(out / "q_pocket_issue_risk_coverage.csv", coverage_rows)
    write_csv(out / "q_pocket_issue_risk_composition.csv", composition_rows)
    write_csv(out / "q_pocket_issue_risk_candidates.csv", candidate_rows)
    write_csv(out / "q_pocket_issue_risk_prediction_rows.csv", prediction_rows)
    write_csv(out / "q_pocket_issue_risk_prediction_summary.csv", prob_summary)
    write_csv(out / "q_pocket_issue_risk_windows.csv", window_rows)

    report = [
        "# N=7 q-pocket issue-level risk evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Gate specs: `{args.gate_specs}`",
        f"- Risk policies: `{args.risk_policies}`",
        f"- Same-budget issue stake before risk scale: `{args.issue_budget_units}`",
        "",
        "q-pocket selector and ticket construction are unchanged. Risk policies only scale whole-issue stake.",
        "",
        "## Prediction Summary",
        md_table(prob_summary),
        "## Decision Summary",
        md_table(risk_decision_summary[:80]),
        "## Budget Summary",
        md_table(compact_summary(summary, stress_by_strategy)[:80]),
        "## Stress Summary",
        md_table(stress[:80]),
        "## Risk Metrics Sample",
        md_table(risk_rows[:80]),
        "",
        "## Files",
        "",
        "- `q_pocket_issue_risk_summary.csv`",
        "- `q_pocket_issue_risk_stress_summary.csv`",
        "- `q_pocket_issue_risk_metrics.csv`",
        "- `q_pocket_issue_risk_decisions.csv`",
        "- `q_pocket_issue_risk_decision_summary.csv`",
        "- `q_pocket_issue_risk_budget_rows.csv`",
        "",
    ]
    (out / "q_pocket_issue_risk_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'q_pocket_issue_risk_report.md'}")
    print(f"Wrote {len(risk_budget_rows)} risk-scaled ticket rows and {len(risk_rows)} issue risk rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_pocket_issue_risk"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--snapshot", choices=("10h", "1h"), default="10h")
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=20.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--gate-specs", default="whitelist_open,core_issue_gate30")
    parser.add_argument(
        "--risk-policies",
        default="full,half_any_flag,skip_any_flag,half_2plus,skip_2plus,half_2_skip_3,sp_half,sp_skip,sp_model_half,sp_model_skip,quality_skip",
    )
    parser.add_argument("--snapshot-pure-feature-set", default="snapshot_priors")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--mp-blend-weight", type=float, default=0.25)
    parser.add_argument("--mp-lookback-matches", type=int, default=10)
    parser.add_argument("--mp-prior-matches", type=float, default=4.0)
    parser.add_argument("--mp-max-goals", type=int, default=8)
    parser.add_argument("--mp-home-advantage", type=float, default=1.10)
    parser.add_argument("--mp-away-discount", type=float, default=0.90)
    parser.add_argument("--sp-feature-set", choices=("action_odds", "action_odds_move"), default="action_odds_move")
    parser.add_argument("--sp-prior-n", type=int, default=40)
    parser.add_argument("--min-sp-multiplier", type=float, default=0.60)
    parser.add_argument("--max-sp-multiplier", type=float, default=1.60)
    parser.add_argument("--adverse-sp-multiplier", type=float, default=0.98)
    parser.add_argument("--severe-sp-multiplier", type=float, default=0.92)
    parser.add_argument("--favorable-sp-multiplier", type=float, default=1.05)
    parser.add_argument("--max-adverse-sp-rate", type=float, default=0.65)
    parser.add_argument("--max-severe-sp-rate", type=float, default=0.30)
    parser.add_argument("--min-avg-sp-multiplier", type=float, default=0.98)
    parser.add_argument("--low-model-ratio", type=float, default=0.90)
    parser.add_argument("--max-low-model-ratio-rate", type=float, default=0.55)
    parser.add_argument("--min-avg-model-ratio", type=float, default=0.95)
    parser.add_argument("--max-not-top2-rate", type=float, default=0.45)
    parser.add_argument("--min-avg-q-margin", type=float, default=0.03)
    parser.add_argument("--min-p10-q-margin", type=float, default=-0.01)
    parser.add_argument("--min-policy-legs-warning", type=int, default=12)
    parser.add_argument("--max-pocket-share", type=float, default=0.55)
    parser.add_argument("--max-tailish-rate", type=float, default=0.65)
    parser.add_argument("--adverse-move-log", type=float, default=0.03)
    parser.add_argument("--max-positive-move-rate", type=float, default=0.55)
    parser.add_argument("--max-avg-move-log", type=float, default=0.02)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
