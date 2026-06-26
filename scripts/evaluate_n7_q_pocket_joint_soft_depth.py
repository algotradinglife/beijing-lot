#!/usr/bin/env python3
"""Evaluate weak result-model + SP-drift soft depth for N=7 q-pocket.

This is deliberately conservative:

* q-pocket remains the selector;
* result prediction and SP drift only adjust depth weights;
* both soft factors are centered within the current issue and tightly capped.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
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
    snapshot_odds_p,
    summarize_tickets,
    train_q_model,
    write_csv,
)


def parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def normalize_probs(probs: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probs, dtype=float), 1e-9, 1.0)
    return clipped / clipped.sum(axis=1, keepdims=True)


def probability_by_match(samples, probs: np.ndarray) -> dict[int, np.ndarray]:
    return {sample.match_id: probs[i] for i, sample in enumerate(samples)}


def selected_p(row: Leg, probs_by_match: dict[int, np.ndarray]) -> float:
    probs = probs_by_match.get(row.row.match_id)
    if probs is None:
        return float("nan")
    return float(probs[OUTCOMES.index(row.row.action_code)])


def centered_power_components(
    values: dict[str, float],
    *,
    alpha: float,
    min_component: float,
    max_component: float,
) -> dict[str, float]:
    finite = [value for value in values.values() if math.isfinite(value) and value > 0]
    if not finite:
        return {key: 1.0 for key in values}
    center = float(np.median(finite))
    if center <= 0 or not math.isfinite(center):
        center = 1.0
    out: dict[str, float] = {}
    for key, value in values.items():
        if not math.isfinite(value) or value <= 0:
            out[key] = min_component
            continue
        component = (value / center) ** alpha
        out[key] = max(min_component, min(max_component, component))
    return out


def direction_component(
    move_log: float | None,
    *,
    positive_move_penalty: float,
    negative_move_bonus: float,
    min_component: float,
    max_component: float,
) -> float:
    if move_log is None or not math.isfinite(move_log):
        return 1.0
    if move_log > 0:
        raw = math.exp(-positive_move_penalty * move_log)
    elif move_log < 0:
        raw = math.exp(negative_move_bonus * abs(move_log))
    else:
        raw = 1.0
    return max(min_component, min(max_component, raw))


def joint_soft_weights(
    legs: list[Leg],
    base_weights: dict[str, float],
    *,
    model_probs_by_match: dict[int, np.ndarray],
    market_probs_by_match: dict[int, np.ndarray],
    sp_model,
    args: argparse.Namespace,
    use_model: bool,
    use_drift: bool,
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    model_ratio_values: dict[str, float] = {}
    drift_values: dict[str, float] = {}
    direction_values: dict[str, float] = {}

    for leg in legs:
        model_p = selected_p(leg, model_probs_by_match)
        market_p = selected_p(leg, market_probs_by_match)
        model_ratio_values[leg.leg_id] = model_p / max(market_p, 1e-9)

        pred_multiplier = predict_sp_multiplier(sp_model, leg.row)
        drift_values[leg.leg_id] = pred_multiplier
        direction_values[leg.leg_id] = direction_component(
            odds_move_log(leg.row, sp_model.snapshot),
            positive_move_penalty=args.positive_move_penalty,
            negative_move_bonus=args.negative_move_bonus,
            min_component=args.direction_min_component,
            max_component=args.direction_max_component,
        )

    model_components = centered_power_components(
        model_ratio_values,
        alpha=args.model_alpha,
        min_component=args.model_min_component,
        max_component=args.model_max_component,
    )
    drift_components = centered_power_components(
        drift_values,
        alpha=args.drift_alpha,
        min_component=args.drift_min_component,
        max_component=args.drift_max_component,
    )

    adjusted = dict(base_weights)
    diagnostics: dict[str, dict[str, float]] = {}
    for leg in legs:
        model_component = model_components.get(leg.leg_id, 1.0) if use_model else 1.0
        drift_component = drift_components.get(leg.leg_id, 1.0) if use_drift else 1.0
        direction = direction_values.get(leg.leg_id, 1.0) if use_drift else 1.0
        joint = max(
            args.joint_min_component,
            min(args.joint_max_component, model_component * drift_component * direction),
        )
        adjusted[leg.leg_id] = adjusted.get(leg.leg_id, 1.0) * joint
        diagnostics[leg.leg_id] = {
            "model_ratio": model_ratio_values.get(leg.leg_id, float("nan")),
            "pred_sp_multiplier": drift_values.get(leg.leg_id, float("nan")),
            "model_component": model_component,
            "drift_component": drift_component,
            "direction_component": direction,
            "joint_component": joint,
            "base_depth_weight": base_weights.get(leg.leg_id, 1.0),
            "adjusted_depth_weight": adjusted[leg.leg_id],
        }
    return adjusted, diagnostics


def component_snapshot(
    *,
    strategy: str,
    issue: str,
    spec: GateSpec,
    legs: list[Leg],
    diagnostics: dict[str, dict[str, float]],
) -> dict[str, object]:
    rows = [diagnostics.get(leg.leg_id, {}) for leg in legs]

    def avg(field: str) -> float:
        vals = [float(row[field]) for row in rows if field in row and math.isfinite(float(row[field]))]
        return sum(vals) / len(vals) if vals else float("nan")

    def q(field: str, quantile: float) -> float:
        vals = [float(row[field]) for row in rows if field in row and math.isfinite(float(row[field]))]
        return float(np.quantile(vals, quantile)) if vals else float("nan")

    return {
        "strategy": strategy,
        "issue": issue,
        "gate_spec": spec.name,
        "n_legs": len(legs),
        "avg_model_ratio": avg("model_ratio"),
        "avg_pred_sp_multiplier": avg("pred_sp_multiplier"),
        "avg_model_component": avg("model_component"),
        "avg_drift_component": avg("drift_component"),
        "avg_direction_component": avg("direction_component"),
        "avg_joint_component": avg("joint_component"),
        "p10_joint_component": q("joint_component", 0.10),
        "p90_joint_component": q("joint_component", 0.90),
        "avg_base_depth_weight": avg("base_depth_weight"),
        "avg_adjusted_depth_weight": avg("adjusted_depth_weight"),
    }


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
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    composition_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
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
        pure_probs, pure_model = fit_predict_snapshot_pure(
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
            if count_tags(policy_legs, metas)["core"] < spec.min_issue_core_legs:
                continue
            if len(dedup_legs_by_match(policy_legs)) < args.n_legs:
                continue

            variants = [
                ("base", False, False),
                ("soft_model", True, False),
                ("soft_drift", False, True),
                ("soft_joint", True, True),
            ]
            for variant_name, use_model, use_drift in variants:
                strategy = f"q_pocket_{spec.name}__{variant_name}"
                weights, diagnostics = joint_soft_weights(
                    policy_legs,
                    base_weights,
                    model_probs_by_match=model_by_match,
                    market_probs_by_match=market_by_match,
                    sp_model=sp_model,
                    args=args,
                    use_model=use_model,
                    use_drift=use_drift,
                )
                tickets = make_constrained_depth_tickets(
                    policy_legs,
                    metas=metas,
                    depth_weights=weights,
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
                settled = [settle_ticket(ticket) for ticket in tickets]
                ticket_rows.extend(settled)
                composition_rows.extend(ticket_composition_rows(tickets, metas, settled))
                coverage_rows.append(
                    coverage_snapshot(
                        strategy=strategy,
                        test_issue=test_issue,
                        q_legs=base_legs,
                        policy_legs=policy_legs,
                        tickets=tickets,
                        metas=metas,
                    )
                )
                component_rows.append(
                    component_snapshot(
                        strategy=strategy,
                        issue=test_issue,
                        spec=spec,
                        legs=policy_legs,
                        diagnostics=diagnostics,
                    )
                )

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "leakage_guard": "train_issues_before_test_issue",
                "snapshot": args.snapshot,
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "n_base_legs": len(base_legs),
                "pure_train_logloss": pure_model.train_logloss,
                "pure_train_accuracy": pure_model.train_accuracy,
            }
        )

    budget_rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=args.issue_budget_units, fractional=False)
    summary = summarize_tickets(budget_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    stress = stress_summary(budget_rows)
    stress_by_strategy = {str(row["strategy"]): row for row in stress}
    prob_summary = probability_summary(prediction_rows)
    prob_summary.sort(key=lambda row: float(row["logloss"]))
    issue_profit = issue_profit_rows(budget_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "q_pocket_joint_soft_tickets.csv", ticket_rows)
    write_csv(out / "q_pocket_joint_soft_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_joint_soft_summary.csv", summary)
    write_csv(out / "q_pocket_joint_soft_stress_summary.csv", stress)
    write_csv(out / "q_pocket_joint_soft_issue_profit.csv", issue_profit)
    write_csv(out / "q_pocket_joint_soft_composition.csv", composition_rows)
    write_csv(out / "q_pocket_joint_soft_coverage.csv", coverage_rows)
    write_csv(out / "q_pocket_joint_soft_candidates.csv", candidate_rows)
    write_csv(out / "q_pocket_joint_soft_components.csv", component_rows)
    write_csv(out / "q_pocket_joint_soft_prediction_rows.csv", prediction_rows)
    write_csv(out / "q_pocket_joint_soft_prediction_summary.csv", prob_summary)
    write_csv(out / "q_pocket_joint_soft_windows.csv", window_rows)

    report = [
        "# N=7 q-pocket joint soft depth evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Gate specs: `{args.gate_specs}`",
        f"- Model cap: `{args.model_min_component}` to `{args.model_max_component}`, alpha `{args.model_alpha}`",
        f"- Drift cap: `{args.drift_min_component}` to `{args.drift_max_component}`, alpha `{args.drift_alpha}`",
        f"- Joint cap: `{args.joint_min_component}` to `{args.joint_max_component}`",
        f"- Same-budget issue stake: `{args.issue_budget_units}`",
        "",
        "q-pocket remains the selector. Result model and SP drift only adjust depth weights.",
        "",
        "## Prediction Summary",
        md_table(prob_summary),
        "## Budget Summary",
        md_table(compact_summary(summary, stress_by_strategy)),
        "## Stress Summary",
        md_table(stress[:80]),
        "",
        "## Files",
        "",
        "- `q_pocket_joint_soft_summary.csv`",
        "- `q_pocket_joint_soft_stress_summary.csv`",
        "- `q_pocket_joint_soft_components.csv`",
        "- `q_pocket_joint_soft_prediction_summary.csv`",
        "- `q_pocket_joint_soft_tickets.csv`",
        "",
    ]
    (out / "q_pocket_joint_soft_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'q_pocket_joint_soft_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows and {len(prediction_rows)} prediction rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_pocket_joint_soft_depth"))
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
    parser.add_argument("--model-alpha", type=float, default=0.08)
    parser.add_argument("--model-min-component", type=float, default=0.85)
    parser.add_argument("--model-max-component", type=float, default=1.10)
    parser.add_argument("--drift-alpha", type=float, default=0.50)
    parser.add_argument("--drift-min-component", type=float, default=0.85)
    parser.add_argument("--drift-max-component", type=float, default=1.10)
    parser.add_argument("--positive-move-penalty", type=float, default=0.75)
    parser.add_argument("--negative-move-bonus", type=float, default=0.35)
    parser.add_argument("--direction-min-component", type=float, default=0.90)
    parser.add_argument("--direction-max-component", type=float, default=1.08)
    parser.add_argument("--joint-min-component", type=float, default=0.80)
    parser.add_argument("--joint-max-component", type=float, default=1.15)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
