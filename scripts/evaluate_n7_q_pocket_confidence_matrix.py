#!/usr/bin/env python3
"""Evaluate q-pocket x result-confidence quadrant depth rules for N=7.

The experiment keeps q-pocket as the primary selector. A snapshot-safe result
model is used only to classify each q-pocket leg into:

* high q / high confidence
* high q / low confidence
* low q / high confidence
* low q / low confidence

The quadrant policy then adjusts coverage depth, or optionally filters the
low/low quadrant. Settlement still uses official winning SP after ticket
construction.
"""
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

from scripts.evaluate_n7_confidence_coverage import confidence_metrics, depth_weight_from_metrics, transform_legs_for_depth
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
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
from scripts.evaluate_n7_sp_drift_depth import predict_sp_multiplier, train_sp_drift_model
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


@dataclass(frozen=True)
class MatrixPolicy:
    name: str
    hh: float
    hl: float
    lh: float
    ll: float
    drop_ll: bool = False
    adjust_score: bool = False
    drift_mode: str = ""
    drift_good_factor: float = 1.0
    drift_bad_factor: float = 1.0
    drift_drop_bad: bool = False
    drift_quantile: float = 0.50


POLICIES = {
    # Isolated LL haircuts: keep all non-LL quadrants at baseline depth.
    "ll_haircut_75": MatrixPolicy("ll_haircut_75", hh=1.00, hl=1.00, lh=1.00, ll=0.75),
    "ll_haircut_50": MatrixPolicy("ll_haircut_50", hh=1.00, hl=1.00, lh=1.00, ll=0.50),
    "ll_haircut_25": MatrixPolicy("ll_haircut_25", hh=1.00, hl=1.00, lh=1.00, ll=0.25),
    # Drift-aware LL controls: only LL legs change, and only by predicted
    # settlement-SP multiplier trained on prior issues.
    "ll_drift_good_keep_bad50": MatrixPolicy(
        "ll_drift_good_keep_bad50",
        hh=1.00,
        hl=1.00,
        lh=1.00,
        ll=1.00,
        drift_mode="ll_threshold",
        drift_good_factor=1.00,
        drift_bad_factor=0.50,
    ),
    "ll_drift_good_keep_bad25": MatrixPolicy(
        "ll_drift_good_keep_bad25",
        hh=1.00,
        hl=1.00,
        lh=1.00,
        ll=1.00,
        drift_mode="ll_threshold",
        drift_good_factor=1.00,
        drift_bad_factor=0.25,
    ),
    "ll_drift_drop_bad": MatrixPolicy(
        "ll_drift_drop_bad",
        hh=1.00,
        hl=1.00,
        lh=1.00,
        ll=1.00,
        drift_mode="ll_threshold",
        drift_good_factor=1.00,
        drift_bad_factor=0.00,
        drift_drop_bad=True,
    ),
    # Conservative: express the idea mainly through reuse depth.
    "matrix_soft": MatrixPolicy("matrix_soft", hh=1.15, hl=0.95, lh=0.90, ll=0.75),
    # More separation between consensus and low/low legs.
    "matrix_balanced": MatrixPolicy("matrix_balanced", hh=1.30, hl=0.90, lh=0.85, ll=0.60),
    # Treat high-confidence low-q legs as stabilizers, not value anchors.
    "matrix_stabilizer": MatrixPolicy("matrix_stabilizer", hh=1.20, hl=0.80, lh=1.00, ll=0.65),
    # Protect high-q legs more than high-confidence legs.
    "matrix_value": MatrixPolicy("matrix_value", hh=1.25, hl=1.00, lh=0.75, ll=0.50),
    # Hard diagnostic: remove legs where both signals are weak.
    "drop_ll_soft": MatrixPolicy("drop_ll_soft", hh=1.20, hl=0.90, lh=0.85, ll=0.0, drop_ll=True),
    # Aggressive diagnostic: depth and rank score both move with the quadrant.
    "score_balanced": MatrixPolicy(
        "score_balanced",
        hh=1.20,
        hl=0.92,
        lh=0.88,
        ll=0.70,
        adjust_score=True,
    ),
}


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def quantile(values: list[float], q: float) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return float("nan")
    return float(np.quantile(finite, q))


def selected_metrics(leg: Leg, probs_by_match: dict[int, np.ndarray], market_by_match: dict[int, np.ndarray]) -> dict[str, float]:
    probs = probs_by_match.get(leg.row.match_id)
    market = market_by_match.get(leg.row.match_id)
    if probs is None or market is None:
        return {
            "selected_model_p": float("nan"),
            "selected_market_p": float("nan"),
            "model_market_ratio": float("nan"),
            "top_p": float("nan"),
            "margin": float("nan"),
            "top1_agree": 0.0,
            "top2_agree": 0.0,
            "conf_weight": 1.0,
        }
    m = confidence_metrics(leg, probs, market)
    conf_weight = depth_weight_from_metrics(
        "depth_constrained_hybrid",
        m,
        score_factor=leg.score_factor,
        min_score_factor=1.0,
    )
    return {**m, "conf_weight": conf_weight}


def quadrant_factor(policy: MatrixPolicy, quadrant: str) -> float:
    if quadrant == "HH":
        return policy.hh
    if quadrant == "HL":
        return policy.hl
    if quadrant == "LH":
        return policy.lh
    if quadrant == "LL":
        return policy.ll
    raise ValueError(f"unknown quadrant: {quadrant}")


def base_q_depth_weight(score_factor: float, threshold: float) -> float:
    ratio = score_factor / max(threshold, 1e-9)
    return max(0.75, min(1.75, math.sqrt(max(0.01, ratio))))


def classify_and_transform(
    legs: list[Leg],
    *,
    policy: MatrixPolicy | None,
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    sp_model=None,
    threshold: float,
    q_quantile: float,
    conf_quantile: float,
    strategy: str,
) -> tuple[list[Leg], dict[str, float], dict[str, dict[str, object]]]:
    metrics_by_leg = {leg.leg_id: selected_metrics(leg, probs_by_match, market_by_match) for leg in legs}
    sp_multiplier_by_leg = {
        leg.leg_id: predict_sp_multiplier(sp_model, leg.row) if sp_model is not None else float("nan")
        for leg in legs
    }
    q_cut = quantile([leg.score_factor for leg in legs], q_quantile)
    conf_cut = quantile([float(metrics_by_leg[leg.leg_id]["conf_weight"]) for leg in legs], conf_quantile)
    drift_cut = quantile(
        [value for value in sp_multiplier_by_leg.values() if math.isfinite(value)],
        policy.drift_quantile if policy is not None else 0.50,
    )
    if not math.isfinite(q_cut):
        q_cut = threshold
    if not math.isfinite(conf_cut):
        conf_cut = 1.0
    if not math.isfinite(drift_cut):
        drift_cut = 1.0

    out: list[Leg] = []
    weights: dict[str, float] = {}
    diagnostics: dict[str, dict[str, object]] = {}
    for leg in legs:
        m = metrics_by_leg[leg.leg_id]
        pred_sp_multiplier = sp_multiplier_by_leg[leg.leg_id]
        q_high = leg.score_factor >= q_cut
        conf_high = float(m["conf_weight"]) >= conf_cut
        quadrant = ("H" if q_high else "L") + ("H" if conf_high else "L")
        factor = quadrant_factor(policy, quadrant) if policy is not None else 1.0
        drift_bucket = "NA"
        if (
            policy is not None
            and policy.drift_mode == "ll_threshold"
            and quadrant == "LL"
            and math.isfinite(pred_sp_multiplier)
        ):
            drift_bucket = "good" if pred_sp_multiplier >= drift_cut else "bad"
            factor *= policy.drift_good_factor if drift_bucket == "good" else policy.drift_bad_factor
        elif policy is not None and policy.drift_mode:
            drift_bucket = "non_ll"
        if policy is not None and policy.drop_ll and quadrant == "LL":
            diagnostics[leg.leg_id] = {
                "quadrant": quadrant,
                "dropped": 1,
                "factor": factor,
                "q_cut": q_cut,
                "conf_cut": conf_cut,
                "pred_sp_multiplier": pred_sp_multiplier,
                "drift_cut": drift_cut,
                "drift_bucket": drift_bucket,
                **m,
            }
            continue
        if (
            policy is not None
            and policy.drift_drop_bad
            and quadrant == "LL"
            and drift_bucket == "bad"
        ):
            diagnostics[leg.leg_id] = {
                "quadrant": quadrant,
                "dropped": 1,
                "factor": factor,
                "q_cut": q_cut,
                "conf_cut": conf_cut,
                "pred_sp_multiplier": pred_sp_multiplier,
                "drift_cut": drift_cut,
                "drift_bucket": drift_bucket,
                **m,
            }
            continue

        base_weight = base_q_depth_weight(leg.score_factor, threshold)
        depth_weight = max(0.35, min(2.50, base_weight * factor))
        score_factor = leg.score_factor * factor if policy is not None and policy.adjust_score else leg.score_factor
        converted = replace(
            leg,
            strategy=strategy,
            score_factor=score_factor,
            p_hat=max(0.001, min(0.999, float(m["selected_model_p"]) if math.isfinite(float(m["selected_model_p"])) else leg.p_hat)),
            source_rule=(
                f"{leg.source_rule};q_conf_quadrant={quadrant};"
                f"q_cut={q_cut:.6f};conf_cut={conf_cut:.6f};"
                f"conf_weight={float(m['conf_weight']):.6f};matrix_factor={factor:.4f}"
            ),
        )
        out.append(converted)
        weights[converted.leg_id] = depth_weight
        diagnostics[converted.leg_id] = {
            "quadrant": quadrant,
            "dropped": 0,
                "factor": factor,
                "q_cut": q_cut,
                "conf_cut": conf_cut,
                "pred_sp_multiplier": pred_sp_multiplier,
                "drift_cut": drift_cut,
                "drift_bucket": drift_bucket,
                "base_depth_weight": base_weight,
                "depth_weight": depth_weight,
            "score_factor_original": leg.score_factor,
            "score_factor_adjusted": score_factor,
            **m,
        }
    return out, weights, diagnostics


def quadrant_issue_row(
    *,
    strategy: str,
    issue: str,
    policy_legs: list[Leg],
    selected_legs: list[Leg],
    diagnostics: dict[str, dict[str, object]],
    tickets: list[Ticket],
) -> dict[str, object]:
    selected_ids = {leg.leg_id for leg in selected_legs}
    ticket_counts: Counter[str] = Counter()
    for ticket in tickets:
        for leg in ticket.legs:
            ticket_counts[leg.leg_id] += 1

    counts: Counter[str] = Counter()
    selected_counts: Counter[str] = Counter()
    uses: Counter[str] = Counter()
    hits: Counter[str] = Counter()
    drift_counts: Counter[str] = Counter()
    drift_selected_counts: Counter[str] = Counter()
    drift_uses: Counter[str] = Counter()
    drift_hits: Counter[str] = Counter()
    model_ratios: dict[str, list[float]] = defaultdict(list)
    conf_weights: dict[str, list[float]] = defaultdict(list)
    for leg in policy_legs:
        diag = diagnostics.get(leg.leg_id, {})
        quadrant = str(diag.get("quadrant", "NA"))
        drift_bucket = str(diag.get("drift_bucket", "NA"))
        counts[quadrant] += 1
        if leg.leg_id in selected_ids:
            selected_counts[quadrant] += 1
        uses[quadrant] += ticket_counts[leg.leg_id]
        if leg.row.hit == 1:
            hits[quadrant] += 1
        if quadrant == "LL":
            drift_key = f"LL_{drift_bucket}"
            drift_counts[drift_key] += 1
            if leg.leg_id in selected_ids:
                drift_selected_counts[drift_key] += 1
            drift_uses[drift_key] += ticket_counts[leg.leg_id]
            if leg.row.hit == 1:
                drift_hits[drift_key] += 1
        ratio = diag.get("model_market_ratio")
        conf = diag.get("conf_weight")
        if isinstance(ratio, (float, int)) and math.isfinite(float(ratio)):
            model_ratios[quadrant].append(float(ratio))
        if isinstance(conf, (float, int)) and math.isfinite(float(conf)):
            conf_weights[quadrant].append(float(conf))

    row: dict[str, object] = {
        "strategy": strategy,
        "issue": issue,
        "n_policy_legs": len(policy_legs),
        "n_selected_legs": len(selected_legs),
        "n_tickets": len(tickets),
    }
    for quadrant in ("HH", "HL", "LH", "LL"):
        n = counts[quadrant]
        row[f"{quadrant}_legs"] = n
        row[f"{quadrant}_selected_legs"] = selected_counts[quadrant]
        row[f"{quadrant}_ticket_uses"] = uses[quadrant]
        row[f"{quadrant}_hit_rate"] = hits[quadrant] / n if n else float("nan")
        row[f"{quadrant}_avg_model_ratio"] = (
            sum(model_ratios[quadrant]) / len(model_ratios[quadrant])
            if model_ratios[quadrant]
            else float("nan")
        )
        row[f"{quadrant}_avg_conf_weight"] = (
            sum(conf_weights[quadrant]) / len(conf_weights[quadrant])
            if conf_weights[quadrant]
            else float("nan")
        )
    for drift_key in ("LL_good", "LL_bad", "LL_NA"):
        n = drift_counts[drift_key]
        row[f"{drift_key}_legs"] = n
        row[f"{drift_key}_selected_legs"] = drift_selected_counts[drift_key]
        row[f"{drift_key}_ticket_uses"] = drift_uses[drift_key]
        row[f"{drift_key}_hit_rate"] = drift_hits[drift_key] / n if n else float("nan")
    return row


def run(args: argparse.Namespace) -> None:
    settlement_quality = None if args.settlement_quality == "any" else args.settlement_quality
    action_rows = load_action_rows(args.db, args.min_year, settlement_quality=settlement_quality)
    samples = build_samples(
        action_rows,
        load_match_extras(args.db, args.min_year, settlement_quality=settlement_quality),
    )
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue: dict[str, list[object]] = defaultdict(list)
    for sample in samples:
        samples_by_issue[sample.issue].append(sample)
    issues = sorted(samples_by_issue)
    gate_specs = parse_gate_specs(args.gate_specs)
    policy_names = parse_strings(args.policies)
    missing = [name for name in policy_names if name != "base" and name not in POLICIES]
    if missing:
        raise SystemExit(f"unknown policies: {','.join(missing)}")
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    composition_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    quadrant_rows: list[dict[str, object]] = []
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

        market = snapshot_market_probabilities(test_samples, args.snapshot)
        if args.model_source == "snapshot_market":
            probs = market
            train_logloss = float("nan")
            train_accuracy = float("nan")
        elif args.model_source == "snapshot_pure":
            probs, model = fit_predict_snapshot_pure(
                train_samples,
                test_samples,
                snapshot=args.snapshot,
                feature_set=args.snapshot_pure_feature_set,
                l2=args.l2,
                maxiter=args.maxiter,
            )
            train_logloss = model.train_logloss
            train_accuracy = model.train_accuracy
        else:
            raise ValueError(f"unsupported model source: {args.model_source}")

        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        probs_by_match = {sample.match_id: probs[i] for i, sample in enumerate(test_samples)}
        for i, sample in enumerate(test_samples):
            prediction_rows.append(
                {
                    "issue": test_issue,
                    "match_id": sample.match_id,
                    "model_source": args.model_source,
                    "p3": float(probs[i][0]),
                    "p1": float(probs[i][1]),
                    "p0": float(probs[i][2]),
                    "market_p3": float(market[i][0]),
                    "market_p1": float(market[i][1]),
                    "market_p0": float(market[i][2]),
                    "actual_idx": sample.y,
                }
            )

        all_legs, base_weights = transform_legs_for_depth(
            q_legs,
            policy="depth_constrained_hybrid",
            market_by_match=market_by_match,
            probs_by_match=market_by_match,
            min_score_factor=threshold,
        )
        if len(all_legs) < args.n_legs:
            continue

        _, _, all_diag = classify_and_transform(
            all_legs,
            policy=None,
            probs_by_match=probs_by_match,
            market_by_match=market_by_match,
            sp_model=sp_model,
            threshold=threshold,
            q_quantile=args.q_quantile,
            conf_quantile=args.conf_quantile,
            strategy="all_q_candidates",
        )

        metas = {}
        for leg in all_legs:
            meta = leg_meta(leg, test_action_rows, args.snapshot)
            if meta is not None:
                metas[leg.leg_id] = meta
        candidate_rows.extend(leg_detail_rows(all_legs, metas, "all_q_candidates", test_issue))

        for spec in gate_specs:
            base_policy_legs = filter_legs_for_spec(all_legs, metas, spec)
            if count_tags(base_policy_legs, metas)["core"] < spec.min_issue_core_legs:
                continue
            if len(dedup_legs_by_match(base_policy_legs)) < args.n_legs:
                continue

            for policy_name in policy_names:
                matrix_policy = None if policy_name == "base" else POLICIES[policy_name]
                strategy = f"q_pocket_{spec.name}__{policy_name}"
                if matrix_policy is None:
                    selected_legs = base_policy_legs
                    depth_weights = {
                        leg.leg_id: base_weights.get(leg.leg_id, 1.0)
                        for leg in selected_legs
                    }
                    _, _, diagnostics = classify_and_transform(
                        base_policy_legs,
                        policy=None,
                        probs_by_match=probs_by_match,
                        market_by_match=market_by_match,
                        sp_model=sp_model,
                        threshold=threshold,
                        q_quantile=args.q_quantile,
                        conf_quantile=args.conf_quantile,
                        strategy=strategy,
                    )
                else:
                    selected_legs, depth_weights, diagnostics = classify_and_transform(
                        base_policy_legs,
                        policy=matrix_policy,
                        probs_by_match=probs_by_match,
                        market_by_match=market_by_match,
                        sp_model=sp_model,
                        threshold=threshold,
                        q_quantile=args.q_quantile,
                        conf_quantile=args.conf_quantile,
                        strategy=strategy,
                    )
                skipped_reason = ""
                tickets: list[Ticket] = []
                if count_tags(selected_legs, metas)["core"] < spec.min_issue_core_legs:
                    skipped_reason = f"core_legs<{spec.min_issue_core_legs}"
                elif len(dedup_legs_by_match(selected_legs)) < args.n_legs:
                    skipped_reason = "eligible_legs<n_legs"
                else:
                    tickets = make_constrained_depth_tickets(
                        selected_legs,
                        metas=metas,
                        depth_weights=depth_weights,
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
                candidate_rows.extend(leg_detail_rows(selected_legs, metas, strategy, test_issue))
                coverage_rows.append(
                    coverage_snapshot(
                        strategy=strategy,
                        test_issue=test_issue,
                        q_legs=all_legs,
                        policy_legs=selected_legs,
                        tickets=tickets,
                        metas=metas,
                        skipped_reason=skipped_reason,
                    )
                )
                quadrant_rows.append(
                    quadrant_issue_row(
                        strategy=strategy,
                        issue=test_issue,
                        policy_legs=base_policy_legs,
                        selected_legs=selected_legs,
                        diagnostics=diagnostics,
                        tickets=tickets,
                    )
                )

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "leakage_guard": "train_issues_before_test_issue",
                "snapshot": args.snapshot,
                "model_source": args.model_source,
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "n_all_legs": len(all_legs),
                "train_logloss": train_logloss,
                "train_accuracy": train_accuracy,
                "sp_feature_set": args.sp_feature_set,
                "sp_prior_n": args.sp_prior_n,
            }
        )

    budget_rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=args.issue_budget_units, fractional=False)
    summary = summarize_tickets(budget_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    stress = stress_summary(budget_rows)
    stress_by_strategy = {str(row["strategy"]): row for row in stress}
    issue_profit = issue_profit_rows(budget_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "q_pocket_conf_matrix_tickets.csv", ticket_rows)
    write_csv(out / "q_pocket_conf_matrix_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_conf_matrix_summary.csv", summary)
    write_csv(out / "q_pocket_conf_matrix_stress_summary.csv", stress)
    write_csv(out / "q_pocket_conf_matrix_issue_profit.csv", issue_profit)
    write_csv(out / "q_pocket_conf_matrix_composition.csv", composition_rows)
    write_csv(out / "q_pocket_conf_matrix_coverage.csv", coverage_rows)
    write_csv(out / "q_pocket_conf_matrix_candidates.csv", candidate_rows)
    write_csv(out / "q_pocket_conf_matrix_quadrants.csv", quadrant_rows)
    write_csv(out / "q_pocket_conf_matrix_prediction_rows.csv", prediction_rows)
    write_csv(out / "q_pocket_conf_matrix_windows.csv", window_rows)

    report = [
        "# N=7 q-pocket confidence matrix evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Model source: `{args.model_source}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Settlement quality: `{args.settlement_quality}`",
        f"- Gate specs: `{args.gate_specs}`",
        f"- Policies: `{args.policies}`",
        f"- q/conf quantiles: `{args.q_quantile}` / `{args.conf_quantile}`",
        f"- Same-budget issue stake: `{args.issue_budget_units}`",
        "",
        "q-pocket remains the selector. Result confidence only controls depth or low/low filtering.",
        "",
        "## Budget Summary",
        md_table(compact_summary(summary, stress_by_strategy)),
        "## Stress Summary",
        md_table(stress[:120]),
        "",
        "## Files",
        "",
        "- `q_pocket_conf_matrix_summary.csv`",
        "- `q_pocket_conf_matrix_stress_summary.csv`",
        "- `q_pocket_conf_matrix_issue_profit.csv`",
        "- `q_pocket_conf_matrix_quadrants.csv`",
        "- `q_pocket_conf_matrix_budget_rows.csv`",
        "- `q_pocket_budget_rows.csv` compatibility alias",
        "",
    ]
    (out / "q_pocket_conf_matrix_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'q_pocket_conf_matrix_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_pocket_conf_matrix"))
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--snapshot", choices=("10h", "1h"), default="10h")
    parser.add_argument("--model-source", choices=("snapshot_pure", "snapshot_market"), default="snapshot_pure")
    parser.add_argument("--snapshot-pure-feature-set", default="snapshot_priors")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=20.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--gate-specs", default="whitelist_open,core_issue_gate30,keyed_pockets")
    parser.add_argument(
        "--policies",
        default="base,matrix_soft,matrix_balanced,matrix_stabilizer,matrix_value,drop_ll_soft,score_balanced",
    )
    parser.add_argument("--q-quantile", type=float, default=0.50)
    parser.add_argument("--conf-quantile", type=float, default=0.50)
    parser.add_argument("--sp-feature-set", choices=("action_odds", "action_odds_move"), default="action_odds")
    parser.add_argument("--sp-prior-n", type=int, default=80)
    parser.add_argument("--min-sp-multiplier", type=float, default=0.25)
    parser.add_argument("--max-sp-multiplier", type=float, default=1.50)
    parser.add_argument("--settlement-quality", choices=("any", "trusted", "mismatch", "missing_sp"), default="trusted")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
