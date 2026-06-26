#!/usr/bin/env python3
"""Evaluate result-probability overlays on top of N=7 q-pocket selection.

The q-pocket structure remains the primary selector. Result probabilities are
tested only as a depth/gate/scoring overlay so we can tell whether independent
match prediction improves capital allocation without destroying the pocket edge.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
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


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def normalize_probs(probs: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probs, dtype=float), 1e-9, 1.0)
    return clipped / clipped.sum(axis=1, keepdims=True)


def blend_probabilities(sources: dict[str, np.ndarray], blends: list[float]) -> dict[str, np.ndarray]:
    out = dict(sources)
    pure = sources.get("snapshot_pure")
    mp = sources.get("mp_poisson")
    if pure is None or mp is None:
        return out
    for weight in blends:
        name = f"blend_pure{int(round((1.0 - weight) * 100)):02d}_mp{int(round(weight * 100)):02d}"
        out[name] = normalize_probs((1.0 - weight) * pure + weight * mp)
    return out


def probability_by_match(samples, probs: np.ndarray) -> dict[int, np.ndarray]:
    return {sample.match_id: probs[i] for i, sample in enumerate(samples)}


def selected_model_ratio(leg: Leg, probs_by_match: dict[int, np.ndarray], market_by_match: dict[int, np.ndarray]) -> float:
    probs = probs_by_match.get(leg.row.match_id)
    market = market_by_match.get(leg.row.match_id)
    if probs is None or market is None:
        return 0.0
    idx = OUTCOMES.index(leg.row.action_code)
    return float(probs[idx]) / max(float(market[idx]), 1e-9)


def selected_is_top2(leg: Leg, probs_by_match: dict[int, np.ndarray]) -> bool:
    probs = probs_by_match.get(leg.row.match_id)
    if probs is None:
        return False
    idx = OUTCOMES.index(leg.row.action_code)
    return idx in set(int(v) for v in np.argsort(-probs)[:2])


def blend_score_leg(
    leg: Leg,
    *,
    probs_by_match: dict[int, np.ndarray],
    blend_weight: float,
    snapshot: str,
    min_score_factor: float,
) -> Leg | None:
    odds, _ = snapshot_odds_p(leg.row, snapshot)
    probs = probs_by_match.get(leg.row.match_id)
    if odds is None or odds <= 1.0 or probs is None:
        return None
    idx = OUTCOMES.index(leg.row.action_code)
    p_q = float(leg.score_factor) / float(odds)
    p_model = float(probs[idx])
    p_blend = max(0.001, min(0.999, (1.0 - blend_weight) * p_q + blend_weight * p_model))
    score = p_blend * float(odds)
    if score < min_score_factor:
        return None
    return replace(
        leg,
        score_factor=score,
        p_hat=p_blend,
        source_rule=(
            f"{leg.source_rule};result_overlay=blend_score;"
            f"p_q={p_q:.4f};p_model={p_model:.4f};blend_weight={blend_weight:.2f}"
        ),
    )


def overlay_legs_and_weights(
    legs: list[Leg],
    *,
    overlay: str,
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
    depth_policy: str,
    snapshot: str,
    min_score_factor: float,
    veto_ratio: float,
    blend_weight: float,
) -> tuple[list[Leg], dict[str, float]]:
    working = list(legs)
    if overlay == "depth":
        pass
    elif overlay == "veto_ratio":
        working = [leg for leg in working if selected_model_ratio(leg, probs_by_match, market_by_match) >= veto_ratio]
    elif overlay == "veto_not_top2":
        working = [leg for leg in working if selected_is_top2(leg, probs_by_match)]
    elif overlay == "blend_score":
        blended = [
            blend_score_leg(
                leg,
                probs_by_match=probs_by_match,
                blend_weight=blend_weight,
                snapshot=snapshot,
                min_score_factor=min_score_factor,
            )
            for leg in working
        ]
        working = [leg for leg in blended if leg is not None]
    else:
        raise ValueError(f"unsupported overlay: {overlay}")

    return transform_legs_for_depth(
        working,
        policy=depth_policy,
        probs_by_match=probs_by_match,
        market_by_match=market_by_match,
        min_score_factor=min_score_factor,
    )


def overlay_stats_row(
    *,
    strategy: str,
    issue: str,
    source: str,
    overlay: str,
    spec: GateSpec,
    q_legs: list[Leg],
    policy_legs_before: list[Leg],
    policy_legs_after: list[Leg],
    tickets: list[Ticket],
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
) -> dict[str, object]:
    ratios = [selected_model_ratio(leg, probs_by_match, market_by_match) for leg in policy_legs_after]
    top2 = [selected_is_top2(leg, probs_by_match) for leg in policy_legs_after]
    return {
        "strategy": strategy,
        "issue": issue,
        "source": source,
        "overlay": overlay,
        "gate_spec": spec.name,
        "n_q_legs": len(q_legs),
        "n_policy_before": len(policy_legs_before),
        "n_policy_after": len(policy_legs_after),
        "n_dedup_after": len(dedup_legs_by_match(policy_legs_after)),
        "n_tickets": len(tickets),
        "avg_model_market_ratio": sum(ratios) / len(ratios) if ratios else float("nan"),
        "min_model_market_ratio": min(ratios) if ratios else float("nan"),
        "top2_agree_rate": sum(1 for ok in top2 if ok) / len(top2) if top2 else float("nan"),
    }


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    match_info = load_match_info(args.db, args.min_year)
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue: dict[str, list[object]] = {}
    for sample in samples:
        samples_by_issue.setdefault(sample.issue, []).append(sample)
    issues = sorted(samples_by_issue)
    gate_specs = parse_gate_specs(args.gate_specs)
    overlays = parse_strings(args.overlays)
    blend_weights = parse_floats(args.blend_weights)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    composition_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    overlay_rows: list[dict[str, object]] = []
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
        sources = blend_probabilities(
            {
                "snapshot_market": normalize_probs(market_probs),
                "snapshot_pure": normalize_probs(pure_probs),
                "mp_poisson": normalize_probs(mp_probs),
            },
            blend_weights,
        )
        market_by_match = probability_by_match(test_samples, market_probs)
        source_by_match = {name: probability_by_match(test_samples, probs) for name, probs in sources.items()}
        for name, probs in sources.items():
            append_prediction_rows(prediction_rows, test_issue, name, test_samples, probs)

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

            base_strategy = f"q_pocket_{spec.name}__snapshot_market_depth"
            base_tickets = make_constrained_depth_tickets(
                policy_legs,
                metas=metas,
                depth_weights=base_weights,
                spec=spec,
                strategy=base_strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                max_leg_uses=args.max_depth_leg_uses,
            )
            settled = [settle_ticket(ticket) for ticket in base_tickets]
            ticket_rows.extend(settled)
            composition_rows.extend(ticket_composition_rows(base_tickets, metas, settled))
            coverage_rows.append(
                coverage_snapshot(
                    strategy=base_strategy,
                    test_issue=test_issue,
                    q_legs=base_legs,
                    policy_legs=policy_legs,
                    tickets=base_tickets,
                    metas=metas,
                )
            )
            overlay_rows.append(
                overlay_stats_row(
                    strategy=base_strategy,
                    issue=test_issue,
                    source="snapshot_market",
                    overlay="depth",
                    spec=spec,
                    q_legs=base_legs,
                    policy_legs_before=policy_legs,
                    policy_legs_after=policy_legs,
                    tickets=base_tickets,
                    probs_by_match=market_by_match,
                    market_by_match=market_by_match,
                )
            )

            for source, probs_by_match in source_by_match.items():
                if source == "snapshot_market":
                    continue
                for overlay in overlays:
                    overlay_legs, overlay_weights = overlay_legs_and_weights(
                        policy_legs,
                        overlay=overlay,
                        probs_by_match=probs_by_match,
                        market_by_match=market_by_match,
                        depth_policy=args.depth_policy,
                        snapshot=args.snapshot,
                        min_score_factor=threshold,
                        veto_ratio=args.veto_ratio,
                        blend_weight=args.score_blend_weight,
                    )
                    strategy = f"q_pocket_{spec.name}__{source}_{overlay}"
                    skipped_reason = ""
                    tickets: list[Ticket] = []
                    if count_tags(overlay_legs, metas)["core"] < spec.min_issue_core_legs:
                        skipped_reason = f"core_legs<{spec.min_issue_core_legs}"
                    elif len(dedup_legs_by_match(overlay_legs)) < args.n_legs:
                        skipped_reason = "eligible_legs<n_legs"
                    else:
                        tickets = make_constrained_depth_tickets(
                            overlay_legs,
                            metas=metas,
                            depth_weights=overlay_weights,
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
                    candidate_rows.extend(leg_detail_rows(overlay_legs, metas, strategy, test_issue))
                    coverage_rows.append(
                        coverage_snapshot(
                            strategy=strategy,
                            test_issue=test_issue,
                            q_legs=base_legs,
                            policy_legs=overlay_legs,
                            tickets=tickets,
                            metas=metas,
                            skipped_reason=skipped_reason,
                        )
                    )
                    overlay_rows.append(
                        overlay_stats_row(
                            strategy=strategy,
                            issue=test_issue,
                            source=source,
                            overlay=overlay,
                            spec=spec,
                            q_legs=base_legs,
                            policy_legs_before=policy_legs,
                            policy_legs_after=overlay_legs,
                            tickets=tickets,
                            probs_by_match=probs_by_match,
                            market_by_match=market_by_match,
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
    write_csv(out / "q_pocket_overlay_tickets.csv", ticket_rows)
    write_csv(out / "q_pocket_overlay_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_overlay_summary.csv", summary)
    write_csv(out / "q_pocket_overlay_stress_summary.csv", stress)
    write_csv(out / "q_pocket_overlay_issue_profit.csv", issue_profit)
    write_csv(out / "q_pocket_overlay_composition.csv", composition_rows)
    write_csv(out / "q_pocket_overlay_coverage.csv", coverage_rows)
    write_csv(out / "q_pocket_overlay_candidates.csv", candidate_rows)
    write_csv(out / "q_pocket_overlay_stats.csv", overlay_rows)
    write_csv(out / "q_pocket_overlay_prediction_rows.csv", prediction_rows)
    write_csv(out / "q_pocket_overlay_prediction_summary.csv", prob_summary)
    write_csv(out / "q_pocket_overlay_windows.csv", window_rows)

    report = [
        "# N=7 q-pocket result-probability overlay evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Gate specs: `{args.gate_specs}`",
        f"- Overlays: `{args.overlays}`",
        f"- Snapshot-pure feature set: `{args.snapshot_pure_feature_set}`",
        f"- Same-budget issue stake: `{args.issue_budget_units}`",
        "",
        "This evaluates result probabilities as an overlay on q-pocket selection; q-pocket remains the primary selector.",
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
        "- `q_pocket_overlay_summary.csv`",
        "- `q_pocket_overlay_stress_summary.csv`",
        "- `q_pocket_overlay_issue_profit.csv`",
        "- `q_pocket_overlay_stats.csv`",
        "- `q_pocket_overlay_prediction_summary.csv`",
        "- `q_pocket_overlay_tickets.csv`",
        "",
    ]
    (out / "q_pocket_overlay_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'q_pocket_overlay_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows and {len(prediction_rows)} prediction rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_pocket_result_overlay"))
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
    parser.add_argument("--gate-specs", default="whitelist_open,core_issue_gate30,keyed_pockets")
    parser.add_argument("--overlays", default="depth,veto_ratio,veto_not_top2,blend_score")
    parser.add_argument("--veto-ratio", type=float, default=0.75)
    parser.add_argument("--score-blend-weight", type=float, default=0.25)
    parser.add_argument("--blend-weights", default="0.25")
    parser.add_argument("--snapshot-pure-feature-set", default="snapshot_priors")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--mp-lookback-matches", type=int, default=10)
    parser.add_argument("--mp-prior-matches", type=float, default=4.0)
    parser.add_argument("--mp-max-goals", type=int, default=8)
    parser.add_argument("--mp-home-advantage", type=float, default=1.10)
    parser.add_argument("--mp-away-discount", type=float, default=0.90)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
