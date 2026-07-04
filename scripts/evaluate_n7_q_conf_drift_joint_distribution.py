#!/usr/bin/env python3
"""Analyze joint q/confidence/SP-drift cells for N=7 keyed q-pocket legs.

This is a diagnostic, not a production strategy.  It keeps the existing
walk-forward data boundary:

* q is trained from prior issues only;
* confidence is predicted from prior issues only;
* SP-drift multiplier is predicted from prior issues only;
* official winning SP is used only after the decision snapshot.

Buckets are issue-local L/M/H tertiles, so a future selector based on these
cells would only depend on same-issue ranks available at entry time.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import (
    confidence_metrics,
    depth_weight_from_metrics,
    transform_legs_for_depth,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_q_pocket_whitelist import (
    compact_summary,
    count_tags,
    filter_legs_for_spec,
    leg_meta,
    make_constrained_depth_tickets,
    parse_gate_specs,
    stress_summary,
)
from scripts.evaluate_n7_sp_drift_depth import predict_sp_multiplier, train_sp_drift_model
from scripts.snapshot_pure_result_model import fit_predict_snapshot_pure, snapshot_market_probabilities
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras
from scripts.walkforward_beidan_strategy_eval import (
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    dedup_legs_by_match,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    md_table,
    settle_ticket,
    snapshot_odds_p,
    summarize_tickets,
    train_q_model,
    write_csv,
)


BUCKETS = ("L", "M", "H")


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def issue_year(issue: object) -> int:
    text = str(issue)
    return 2000 + int(text[:2]) if len(text) >= 2 and text[:2].isdigit() else 0


def finite_mean(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    return sum(finite) / len(finite) if finite else float("nan")


def quantile(values: list[float], q: float) -> float:
    finite = [v for v in values if math.isfinite(v)]
    return float(np.quantile(finite, q)) if finite else float("nan")


def assign_tertile_buckets(items: list[tuple[str, float]]) -> dict[str, str]:
    finite = [(key, value) for key, value in items if math.isfinite(value)]
    out = {key: "M" for key, _ in items}
    if not finite:
        return out
    ranked = sorted(finite, key=lambda kv: (kv[1], kv[0]))
    n = len(ranked)
    for pos, (key, _) in enumerate(ranked):
        frac = (pos + 0.5) / n
        if frac <= 1.0 / 3.0:
            out[key] = "L"
        elif frac <= 2.0 / 3.0:
            out[key] = "M"
        else:
            out[key] = "H"
    return out


def selected_metrics(
    leg: Leg,
    probs_by_match: dict[int, np.ndarray],
    market_by_match: dict[int, np.ndarray],
) -> dict[str, float]:
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
            "conf_weight": float("nan"),
        }
    metrics = confidence_metrics(leg, probs, market)
    conf_weight = depth_weight_from_metrics(
        "depth_constrained_hybrid",
        metrics,
        score_factor=leg.score_factor,
        min_score_factor=1.0,
    )
    return {**metrics, "conf_weight": conf_weight}


def cell_id(q_bucket: str, conf_bucket: str, drift_bucket: str) -> str:
    return f"q{q_bucket}_conf{conf_bucket}_drift{drift_bucket}"


def ticket_strategy(spec_name: str, gate_name: str) -> str:
    return f"{spec_name}__{gate_name}"


def exact_cell_gate_name(row: dict[str, object]) -> str:
    return cell_id(str(row["q_bucket"]), str(row["confidence_bucket"]), str(row["drift_bucket"]))


def gate_definitions() -> list[tuple[str, Callable[[dict[str, object]], bool]]]:
    return [
        ("selector_all_keyed", lambda r: True),
        ("selector_qH_confH_driftH", lambda r: r["q_bucket"] == "H" and r["confidence_bucket"] == "H" and r["drift_bucket"] == "H"),
        ("selector_qH_confH_driftMH", lambda r: r["q_bucket"] == "H" and r["confidence_bucket"] == "H" and r["drift_bucket"] in {"M", "H"}),
        ("selector_qH_confH_anyD", lambda r: r["q_bucket"] == "H" and r["confidence_bucket"] == "H"),
        ("selector_qMH_confMH_driftH", lambda r: r["q_bucket"] in {"M", "H"} and r["confidence_bucket"] in {"M", "H"} and r["drift_bucket"] == "H"),
        ("selector_driftH_any", lambda r: r["drift_bucket"] == "H"),
        ("selector_driftH_low_q_or_conf", lambda r: r["drift_bucket"] == "H" and (r["q_bucket"] == "L" or r["confidence_bucket"] == "L")),
        ("selector_driftH_qL_confL", lambda r: r["drift_bucket"] == "H" and r["q_bucket"] == "L" and r["confidence_bucket"] == "L"),
    ]


def make_tickets_for_gate(
    *,
    strategy: str,
    issue: str,
    legs: list[Leg],
    metas: dict[str, object],
    depth_weights: dict[str, float],
    spec,
    args: argparse.Namespace,
    train_start_issue: str,
    train_end_issue: str,
) -> list[Ticket]:
    if count_tags(legs, metas)["core"] < spec.min_issue_core_legs:
        return []
    if len(dedup_legs_by_match(legs)) < args.n_legs:
        return []
    return make_constrained_depth_tickets(
        legs,
        metas=metas,
        depth_weights=depth_weights,
        spec=spec,
        strategy=strategy,
        issue=issue,
        n_legs=args.n_legs,
        max_tickets=args.max_tickets_per_issue,
        overlap_penalty=args.overlap_penalty,
        train_start_issue=train_start_issue,
        train_end_issue=train_end_issue,
        max_leg_uses=args.max_depth_leg_uses,
    )


def summarize_leg_rows(rows: list[dict[str, object]], *, suffix: str, min_recent_year: int | None = None) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if min_recent_year is not None and int(row["year"]) < min_recent_year:
            continue
        grouped[
            (
                str(row["q_bucket"]),
                str(row["confidence_bucket"]),
                str(row["drift_bucket"]),
                str(row["cell"]),
            )
        ].append(row)

    out: list[dict[str, object]] = []
    for (q_bucket, conf_bucket, drift_bucket, cell), cell_rows in sorted(grouped.items()):
        hits = [r for r in cell_rows if int(r["hit"]) == 1]
        n_legs = len(cell_rows)
        hit_rate = len(hits) / n_legs if n_legs else float("nan")
        avg_snapshot_p = finite_mean([float(r["snapshot_p"]) for r in cell_rows])
        avg_realized_multiplier = finite_mean([float(r["realized_sp_multiplier"]) for r in hits])
        avg_winning_sp = finite_mean([float(r["winning_sp"]) for r in hits])
        market_q_proxy = hit_rate / avg_snapshot_p if avg_snapshot_p and math.isfinite(avg_snapshot_p) else float("nan")
        drift_adjusted_ev_proxy = (
            market_q_proxy * avg_realized_multiplier
            if math.isfinite(market_q_proxy) and math.isfinite(avg_realized_multiplier)
            else float("nan")
        )
        single_leg_sp_ev_proxy = hit_rate * avg_winning_sp if math.isfinite(avg_winning_sp) else float("nan")
        out.append(
            {
                "cell": cell,
                "q_bucket": q_bucket,
                "confidence_bucket": conf_bucket,
                "drift_bucket": drift_bucket,
                f"n_legs{suffix}": n_legs,
                f"n_issues{suffix}": len({r["issue"] for r in cell_rows}),
                f"n_years{suffix}": len({r["year"] for r in cell_rows}),
                f"baseline_ticket_uses{suffix}": sum(int(r["baseline_ticket_uses"]) for r in cell_rows),
                f"hit_rate{suffix}": hit_rate,
                f"avg_q_score{suffix}": finite_mean([float(r["q_score"]) for r in cell_rows]),
                f"avg_conf_weight{suffix}": finite_mean([float(r["conf_weight"]) for r in cell_rows]),
                f"avg_pred_sp_multiplier{suffix}": finite_mean([float(r["pred_sp_multiplier"]) for r in cell_rows]),
                f"avg_snapshot_p{suffix}": avg_snapshot_p,
                f"avg_snapshot_odds{suffix}": finite_mean([float(r["snapshot_odds"]) for r in cell_rows]),
                f"avg_realized_sp_multiplier_on_hits{suffix}": avg_realized_multiplier,
                f"avg_winning_sp_on_hits{suffix}": avg_winning_sp,
                f"market_q_proxy{suffix}": market_q_proxy,
                f"drift_adjusted_ev_proxy{suffix}": drift_adjusted_ev_proxy,
                f"single_leg_sp_ev_proxy{suffix}": single_leg_sp_ev_proxy,
            }
        )
    return out


def summarize_leg_rows_by_year(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["cell"]), int(row["year"]))].append(row)
    out: list[dict[str, object]] = []
    for (cell, year), cell_rows in sorted(grouped.items()):
        hits = [r for r in cell_rows if int(r["hit"]) == 1]
        hit_rate = len(hits) / len(cell_rows) if cell_rows else float("nan")
        avg_snapshot_p = finite_mean([float(r["snapshot_p"]) for r in cell_rows])
        avg_realized_multiplier = finite_mean([float(r["realized_sp_multiplier"]) for r in hits])
        market_q_proxy = hit_rate / avg_snapshot_p if avg_snapshot_p and math.isfinite(avg_snapshot_p) else float("nan")
        out.append(
            {
                "cell": cell,
                "year": year,
                "q_bucket": cell[1],
                "confidence_bucket": cell[7],
                "drift_bucket": cell[-1],
                "n_legs": len(cell_rows),
                "n_issues": len({r["issue"] for r in cell_rows}),
                "hit_rate": hit_rate,
                "avg_realized_sp_multiplier_on_hits": avg_realized_multiplier,
                "drift_adjusted_ev_proxy": (
                    market_q_proxy * avg_realized_multiplier
                    if math.isfinite(market_q_proxy) and math.isfinite(avg_realized_multiplier)
                    else float("nan")
                ),
                "single_leg_sp_ev_proxy": hit_rate * finite_mean([float(r["winning_sp"]) for r in hits]) if hits else float("nan"),
            }
        )
    return out


def annual_replay_rows(issue_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in issue_rows:
        key = (str(row["strategy"]), issue_year(row["issue"]))
        grouped[key]["issues"] += 1
        grouped[key]["tickets"] += float(row["tickets"])
        grouped[key]["hits"] += float(row["hits"])
        grouped[key]["stake"] += float(row["stake_units"])
        grouped[key]["profit"] += float(row["profit_units"])
        if float(row["profit_units"]) > 0:
            grouped[key]["profitable_issues"] += 1
    out: list[dict[str, object]] = []
    for (strategy, year), vals in sorted(grouped.items()):
        out.append(
            {
                "strategy": strategy,
                "year": year,
                "n_issues": int(vals["issues"]),
                "tickets": int(vals["tickets"]),
                "hits": int(vals["hits"]),
                "stake_units": vals["stake"],
                "profit_units": vals["profit"],
                "roi": vals["profit"] / vals["stake"] if vals["stake"] > 0 else float("nan"),
                "hit_rate": vals["hits"] / vals["tickets"] if vals["tickets"] > 0 else float("nan"),
                "issue_win_rate": vals["profitable_issues"] / vals["issues"] if vals["issues"] > 0 else float("nan"),
            }
        )
    return out


def recent_replay_rows(issue_rows: list[dict[str, object]], *, min_year: int) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in issue_rows:
        if issue_year(row["issue"]) < min_year:
            continue
        strategy = str(row["strategy"])
        grouped[strategy]["issues"] += 1
        grouped[strategy]["tickets"] += float(row["tickets"])
        grouped[strategy]["hits"] += float(row["hits"])
        grouped[strategy]["stake"] += float(row["stake_units"])
        grouped[strategy]["profit"] += float(row["profit_units"])
        if float(row["profit_units"]) > 0:
            grouped[strategy]["profitable_issues"] += 1
    out: list[dict[str, object]] = []
    for strategy, vals in sorted(grouped.items()):
        out.append(
            {
                "strategy": strategy,
                "from_year": min_year,
                "n_issues": int(vals["issues"]),
                "tickets": int(vals["tickets"]),
                "hits": int(vals["hits"]),
                "stake_units": vals["stake"],
                "profit_units": vals["profit"],
                "roi": vals["profit"] / vals["stake"] if vals["stake"] > 0 else float("nan"),
                "hit_rate": vals["hits"] / vals["tickets"] if vals["tickets"] > 0 else float("nan"),
                "issue_win_rate": vals["profitable_issues"] / vals["issues"] if vals["issues"] > 0 else float("nan"),
            }
        )
    out.sort(key=lambda row: float(row["roi"]), reverse=True)
    return out


def merge_replay_into_cells(
    cell_rows: list[dict[str, object]],
    replay_summary: list[dict[str, object]],
    *,
    spec_name: str,
    issue_budget_units: float,
) -> list[dict[str, object]]:
    suffix = f"__budget{issue_budget_units:g}_whole"
    summary_by_strategy = {str(row["strategy"]): row for row in replay_summary}
    out = []
    for row in cell_rows:
        gate = str(row["cell"])
        strategy = f"{ticket_strategy(spec_name, gate)}{suffix}"
        replay = summary_by_strategy.get(strategy, {})
        converted = dict(row)
        converted["replay_strategy"] = strategy
        converted["replay_n_tickets"] = replay.get("n_tickets", 0)
        converted["replay_n_issues"] = replay.get("n_issues", 0)
        converted["replay_hit_rate"] = replay.get("hit_rate", float("nan"))
        converted["replay_profit_units"] = replay.get("total_profit_units", float("nan"))
        converted["replay_roi"] = replay.get("roi", float("nan"))
        converted["replay_best_issue_profit_share"] = replay.get("best_issue_profit_share", float("nan"))
        out.append(converted)
    return out


def key_cell_table(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    wanted = {
        "qH_confH_driftH",
        "qH_confH_driftM",
        "qH_confH_driftL",
        "qL_confL_driftH",
        "qL_confL_driftM",
        "qL_confL_driftL",
        "qH_confL_driftH",
        "qL_confH_driftH",
    }
    return [
        {
            "cell": row["cell"],
            "n_legs": row.get("n_legs", row.get("n_legs_all", "")),
            "hit_rate": row.get("hit_rate", row.get("hit_rate_all", "")),
            "realized_mult": row.get(
                "avg_realized_sp_multiplier_on_hits",
                row.get("avg_realized_sp_multiplier_on_hits_all", ""),
            ),
            "ev_proxy": row.get("drift_adjusted_ev_proxy", row.get("drift_adjusted_ev_proxy_all", "")),
            "recent_hit": row.get("hit_rate_2023_2025", ""),
            "recent_ev": row.get("drift_adjusted_ev_proxy_2023_2025", ""),
            "replay_issues": row.get("replay_n_issues", ""),
            "replay_roi": row.get("replay_roi", ""),
        }
        for row in rows
        if row["cell"] in wanted
    ]


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
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    leg_rows: list[dict[str, object]] = []
    ticket_rows: list[dict[str, object]] = []
    issue_cell_rows: list[dict[str, object]] = []
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
        if args.model_source == "snapshot_pure":
            probs, conf_model = fit_predict_snapshot_pure(
                train_samples,
                test_samples,
                snapshot=args.snapshot,
                feature_set=args.snapshot_pure_feature_set,
                l2=args.l2,
                maxiter=args.maxiter,
            )
            train_logloss = conf_model.train_logloss
            train_accuracy = conf_model.train_accuracy
        elif args.model_source == "snapshot_market":
            probs = market
            train_logloss = float("nan")
            train_accuracy = float("nan")
        else:
            raise ValueError(f"unsupported model source: {args.model_source}")

        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        probs_by_match = {sample.match_id: probs[i] for i, sample in enumerate(test_samples)}

        base_legs, base_weights = transform_legs_for_depth(
            q_legs,
            policy="depth_constrained_hybrid",
            probs_by_match=market_by_match,
            market_by_match=market_by_match,
            min_score_factor=threshold,
        )
        if len(base_legs) < args.n_legs:
            continue

        metas = {
            leg.leg_id: meta
            for leg in base_legs
            if (meta := leg_meta(leg, test_action_rows, args.snapshot)) is not None
        }

        for spec in gate_specs:
            policy_legs = filter_legs_for_spec(base_legs, metas, spec)
            if count_tags(policy_legs, metas)["core"] < spec.min_issue_core_legs:
                continue
            if len(dedup_legs_by_match(policy_legs)) < args.n_legs:
                continue

            metrics_by_leg = {leg.leg_id: selected_metrics(leg, probs_by_match, market_by_match) for leg in policy_legs}
            pred_sp_by_leg = {leg.leg_id: predict_sp_multiplier(sp_model, leg.row) for leg in policy_legs}
            q_buckets = assign_tertile_buckets([(leg.leg_id, leg.score_factor) for leg in policy_legs])
            conf_buckets = assign_tertile_buckets(
                [(leg.leg_id, float(metrics_by_leg[leg.leg_id]["conf_weight"])) for leg in policy_legs]
            )
            drift_buckets = assign_tertile_buckets([(leg.leg_id, pred_sp_by_leg[leg.leg_id]) for leg in policy_legs])

            q_cut1 = quantile([leg.score_factor for leg in policy_legs], 1.0 / 3.0)
            q_cut2 = quantile([leg.score_factor for leg in policy_legs], 2.0 / 3.0)
            conf_cut1 = quantile([float(metrics_by_leg[leg.leg_id]["conf_weight"]) for leg in policy_legs], 1.0 / 3.0)
            conf_cut2 = quantile([float(metrics_by_leg[leg.leg_id]["conf_weight"]) for leg in policy_legs], 2.0 / 3.0)
            drift_cut1 = quantile([pred_sp_by_leg[leg.leg_id] for leg in policy_legs], 1.0 / 3.0)
            drift_cut2 = quantile([pred_sp_by_leg[leg.leg_id] for leg in policy_legs], 2.0 / 3.0)

            issue_records: list[dict[str, object]] = []
            leg_by_id = {leg.leg_id: leg for leg in policy_legs}
            for leg in policy_legs:
                odds, snap_p = snapshot_odds_p(leg.row, args.snapshot)
                if odds is None or snap_p is None or odds <= 1.0 or snap_p <= 0:
                    continue
                metrics = metrics_by_leg[leg.leg_id]
                q_bucket = q_buckets[leg.leg_id]
                conf_bucket = conf_buckets[leg.leg_id]
                drift_bucket = drift_buckets[leg.leg_id]
                realized_multiplier = (
                    leg.row.winning_sp / odds
                    if leg.row.hit == 1 and leg.row.winning_sp > 0
                    else float("nan")
                )
                selected_idx = OUTCOMES.index(leg.row.action_code)
                record = {
                    "spec": spec.name,
                    "issue": test_issue,
                    "year": issue_year(test_issue),
                    "match_id": leg.row.match_id,
                    "action_code": leg.row.action_code,
                    "leg_id": leg.leg_id,
                    "cell": cell_id(q_bucket, conf_bucket, drift_bucket),
                    "q_bucket": q_bucket,
                    "confidence_bucket": conf_bucket,
                    "drift_bucket": drift_bucket,
                    "q_score": leg.score_factor,
                    "p_hat_q": leg.p_hat,
                    "selected_model_p": metrics["selected_model_p"],
                    "selected_market_p": metrics["selected_market_p"],
                    "model_market_ratio": metrics["model_market_ratio"],
                    "top_p": metrics["top_p"],
                    "margin": metrics["margin"],
                    "top1_agree": metrics["top1_agree"],
                    "top2_agree": metrics["top2_agree"],
                    "conf_weight": metrics["conf_weight"],
                    "pred_sp_multiplier": pred_sp_by_leg[leg.leg_id],
                    "snapshot_odds": odds,
                    "snapshot_p": snap_p,
                    "winning_sp": leg.row.winning_sp if leg.row.hit == 1 else float("nan"),
                    "realized_sp_multiplier": realized_multiplier,
                    "hit": leg.row.hit,
                    "result_code": leg.row.result_code,
                    "selected_prob_rank": 1 + int(sum(probs_by_match[leg.row.match_id][i] > probs_by_match[leg.row.match_id][selected_idx] for i in range(3))),
                    "league": leg.row.league,
                    "hcp": leg.row.hcp,
                    "q_cut_tertile_1": q_cut1,
                    "q_cut_tertile_2": q_cut2,
                    "conf_cut_tertile_1": conf_cut1,
                    "conf_cut_tertile_2": conf_cut2,
                    "drift_cut_tertile_1": drift_cut1,
                    "drift_cut_tertile_2": drift_cut2,
                    "baseline_ticket_uses": 0,
                }
                issue_records.append(record)

            if not issue_records:
                continue

            # Baseline keyed replay is also used to count how often each cell is
            # used by the existing ticket constructor.
            baseline_strategy = ticket_strategy(spec.name, "selector_all_keyed")
            baseline_tickets = make_tickets_for_gate(
                strategy=baseline_strategy,
                issue=test_issue,
                legs=policy_legs,
                metas=metas,
                depth_weights=base_weights,
                spec=spec,
                args=args,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
            )
            baseline_uses: Counter[str] = Counter()
            for ticket in baseline_tickets:
                for leg in ticket.legs:
                    baseline_uses[leg.leg_id] += 1
            for record in issue_records:
                record["baseline_ticket_uses"] = baseline_uses[str(record["leg_id"])]
            leg_rows.extend(issue_records)
            ticket_rows.extend(settle_ticket(ticket) for ticket in baseline_tickets)

            records_by_cell: dict[str, list[dict[str, object]]] = defaultdict(list)
            for record in issue_records:
                records_by_cell[str(record["cell"])].append(record)

            for cell, records in records_by_cell.items():
                hits = [r for r in records if int(r["hit"]) == 1]
                issue_cell_rows.append(
                    {
                        "spec": spec.name,
                        "issue": test_issue,
                        "year": issue_year(test_issue),
                        "cell": cell,
                        "q_bucket": records[0]["q_bucket"],
                        "confidence_bucket": records[0]["confidence_bucket"],
                        "drift_bucket": records[0]["drift_bucket"],
                        "n_legs": len(records),
                        "baseline_ticket_uses": sum(int(r["baseline_ticket_uses"]) for r in records),
                        "hit_rate": len(hits) / len(records),
                        "avg_realized_sp_multiplier_on_hits": finite_mean([float(r["realized_sp_multiplier"]) for r in hits]),
                    }
                )

            if args.replay_exact_cells:
                for cell, records in records_by_cell.items():
                    strategy = ticket_strategy(spec.name, cell)
                    selected_ids = {str(record["leg_id"]) for record in records}
                    selected_legs = [leg_by_id[leg_id] for leg_id in selected_ids if leg_id in leg_by_id]
                    tickets = make_tickets_for_gate(
                        strategy=strategy,
                        issue=test_issue,
                        legs=selected_legs,
                        metas=metas,
                        depth_weights=base_weights,
                        spec=spec,
                        args=args,
                        train_start_issue=train_issues[0],
                        train_end_issue=train_issues[-1],
                    )
                    ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)

            for gate_name, predicate in gate_definitions()[1:]:
                selected_ids = {str(record["leg_id"]) for record in issue_records if predicate(record)}
                selected_legs = [leg_by_id[leg_id] for leg_id in selected_ids if leg_id in leg_by_id]
                tickets = make_tickets_for_gate(
                    strategy=ticket_strategy(spec.name, gate_name),
                    issue=test_issue,
                    legs=selected_legs,
                    metas=metas,
                    depth_weights=base_weights,
                    spec=spec,
                    args=args,
                    train_start_issue=train_issues[0],
                    train_end_issue=train_issues[-1],
                )
                ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "leakage_guard": "train_issues_before_test_issue",
                "snapshot": args.snapshot,
                "model_source": args.model_source,
                "sp_feature_set": args.sp_feature_set,
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "train_logloss": train_logloss,
                "train_accuracy": train_accuracy,
            }
        )

    budget_rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=args.issue_budget_units, fractional=False)
    replay_summary = summarize_tickets(budget_rows)
    replay_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    replay_stress = stress_summary(budget_rows)
    stress_by_strategy = {str(row["strategy"]): row for row in replay_stress}
    replay_issue_profit = issue_profit_rows(budget_rows)
    replay_annual = annual_replay_rows(replay_issue_profit)
    replay_recent = recent_replay_rows(replay_issue_profit, min_year=2023)

    cell_all = summarize_leg_rows(leg_rows, suffix="")
    cell_recent = summarize_leg_rows(leg_rows, suffix="_2023_2025", min_recent_year=2023)
    recent_by_cell = {str(row["cell"]): row for row in cell_recent}
    cell_summary = []
    for row in cell_all:
        merged = dict(row)
        recent = recent_by_cell.get(str(row["cell"]), {})
        for key, value in recent.items():
            if key in {"cell", "q_bucket", "confidence_bucket", "drift_bucket"}:
                continue
            merged[key] = value
        cell_summary.append(merged)
    spec_name = parse_strings(args.gate_specs)[0]
    cell_summary = merge_replay_into_cells(
        cell_summary,
        replay_summary,
        spec_name=spec_name,
        issue_budget_units=args.issue_budget_units,
    )
    cell_summary.sort(
        key=lambda row: (
            float(row.get("drift_adjusted_ev_proxy", float("-inf"))),
            int(row.get("n_legs", 0)),
        ),
        reverse=True,
    )
    cell_annual = summarize_leg_rows_by_year(leg_rows)

    high_conf_by_drift = [
        row for row in cell_summary if row["q_bucket"] == "H" and row["confidence_bucket"] == "H"
    ]
    high_conf_by_drift.sort(key=lambda row: str(row["drift_bucket"]))
    high_drift_cells = [row for row in cell_summary if row["drift_bucket"] == "H"]
    high_drift_cells.sort(key=lambda row: (str(row["q_bucket"]), str(row["confidence_bucket"])))
    tradeable_top = [
        row for row in cell_summary
        if int(row.get("n_legs", 0)) >= args.min_report_cell_legs
        and int(row.get("n_issues", 0)) >= args.min_report_cell_issues
    ][:12]
    replay_compact = compact_summary(replay_summary, stress_by_strategy)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "joint_leg_rows.csv", leg_rows)
    write_csv(out / "joint_issue_cell_rows.csv", issue_cell_rows)
    write_csv(out / "joint_cell_summary.csv", cell_summary)
    write_csv(out / "joint_cell_annual_summary.csv", cell_annual)
    write_csv(out / "joint_replay_tickets.csv", ticket_rows)
    write_csv(out / "joint_replay_budget_rows.csv", budget_rows)
    write_csv(out / "joint_replay_summary.csv", replay_summary)
    write_csv(out / "joint_replay_stress_summary.csv", replay_stress)
    write_csv(out / "joint_replay_issue_profit.csv", replay_issue_profit)
    write_csv(out / "joint_replay_annual_summary.csv", replay_annual)
    write_csv(out / "joint_replay_recent_2023_2025_summary.csv", replay_recent)
    write_csv(out / "joint_windows.csv", window_rows)

    hhh = next((row for row in cell_summary if row["cell"] == "qH_confH_driftH"), None)
    llh = next((row for row in cell_summary if row["cell"] == "qL_confL_driftH"), None)
    conclusion = "Do not promote a hard joint selector yet."
    if hhh:
        conclusion += (
            " The H/H/H cell has the strongest hit-rate profile, but it does not simultaneously improve payout "
            "and it is too sparse to form standalone N=7 tickets under keyed constraints."
        )
    if llh:
        conclusion += " High-drift low-q/low-confidence legs have better payout on hits but remain a dead-ticket trap when traded directly."

    report = [
        "# N=7 q/confidence/SP-drift joint distribution",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Settlement quality: `{args.settlement_quality}`",
        f"- Gate specs: `{args.gate_specs}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Confidence model: `{args.model_source}` / `{args.snapshot_pure_feature_set}`",
        f"- Drift model: `{args.sp_feature_set}`, target `winning_sp / snapshot_odds` on hit legs",
        f"- Buckets: issue-local L/M/H tertiles",
        f"- Same-budget issue stake: `{args.issue_budget_units}`",
        "",
        "## Conclusion",
        "",
        conclusion,
        "",
        "The useful diagnostic is not high drift by itself.  Drift's meaning changes after conditioning on q and confidence: H/H/H improves hit rate but not payout, while low-q/low-confidence high-drift improves payout but not tradeability.  The next strategy should use these cells as weak depth/risk context, not as a hard selector.",
        "",
        "## Key Cells",
        md_table(key_cell_table(cell_summary)),
        "## High q + High confidence by drift bucket",
        md_table(high_conf_by_drift),
        "## High drift cells by q/confidence",
        md_table(high_drift_cells),
        "## Top cells by drift-adjusted EV proxy",
        md_table(tradeable_top),
        "## Replay Summary",
        md_table(replay_compact[:80]),
        "## 2023-2025 Replay Summary",
        md_table(replay_recent[:80]),
        "## Files",
        "",
        "- `joint_leg_rows.csv`",
        "- `joint_issue_cell_rows.csv`",
        "- `joint_cell_summary.csv`",
        "- `joint_cell_annual_summary.csv`",
        "- `joint_replay_summary.csv`",
        "- `joint_replay_stress_summary.csv`",
        "- `joint_replay_annual_summary.csv`",
        "- `joint_replay_recent_2023_2025_summary.csv`",
        "- `joint_distribution_report.md`",
        "",
    ]
    (out / "joint_distribution_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'joint_distribution_report.md'}")
    print(f"Wrote {len(leg_rows)} leg rows and {len(ticket_rows)} raw replay ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_conf_drift_joint_distribution"))
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
    parser.add_argument("--gate-specs", default="keyed_pockets")
    parser.add_argument("--sp-feature-set", choices=("action_odds", "action_odds_move"), default="action_odds")
    parser.add_argument("--sp-prior-n", type=int, default=80)
    parser.add_argument("--min-sp-multiplier", type=float, default=0.25)
    parser.add_argument("--max-sp-multiplier", type=float, default=1.50)
    parser.add_argument("--settlement-quality", choices=("any", "trusted", "mismatch", "missing_sp"), default="trusted")
    parser.add_argument("--replay-exact-cells", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-report-cell-legs", type=int, default=500)
    parser.add_argument("--min-report-cell-issues", type=int, default=100)
    parser.add_argument("--min-tradeable-issues", type=int, default=80)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    if args.snapshot == "10h" and args.sp_feature_set == "action_odds_move":
        raise SystemExit("action_odds_move is only useful for snapshot=1h/final")
    run(args)


if __name__ == "__main__":
    main()
