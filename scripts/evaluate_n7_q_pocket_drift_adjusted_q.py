#!/usr/bin/env python3
"""Evaluate SP-drift-adjusted q depth for N=7 q-pocket tickets.

This experiment does not drop legs by quadrant.  It keeps q-pocket as the
selector and uses a walk-forward SP-drift model to adjust each leg's q score
and coverage depth:

    adjusted_score = raw_score * centered(predicted_sp_multiplier) ** beta

For a 10h snapshot, only 10h-visible features are used.  Movement buckets are
only available for 1h experiments where 10h->1h movement is observable before
the 1h decision.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import transform_legs_for_depth
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
from scripts.walkforward_beidan_result_model_eval import build_samples, load_match_extras
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    Leg,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    dedup_legs_by_match,
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


SINGLE_ACTIONS = {"3", "1", "0"}


@dataclass(frozen=True)
class DriftModel:
    means: dict[tuple[str, ...], float]
    counts: dict[tuple[str, ...], int]
    snapshot: str
    feature_set: str
    prior_n: int
    min_multiplier: float
    max_multiplier: float


@dataclass(frozen=True)
class DriftPolicy:
    name: str
    feature_set: str
    beta: float
    min_component: float
    max_component: float
    adjust_score: bool = True
    adjust_depth: bool = True


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def parse_policies(raw: str) -> list[DriftPolicy]:
    policies: list[DriftPolicy] = []
    for name in parse_strings(raw):
        if name == "base":
            policies.append(DriftPolicy("base", "none", 0.0, 1.0, 1.0, False, False))
            continue
        # Format: NAME:FEATURE_SET:BETA[:MIN:MAX[:MODE]]
        # MODE is one of both, score, depth.  Default is both.
        parts = name.split(":")
        if len(parts) not in {3, 5, 6}:
            raise argparse.ArgumentTypeError(
                "policy must be base or NAME:FEATURE_SET:BETA[:MIN:MAX[:MODE]]"
            )
        label, feature_set, beta = parts[:3]
        min_component = float(parts[3]) if len(parts) >= 5 else 0.70
        max_component = float(parts[4]) if len(parts) >= 5 else 1.30
        mode = parts[5] if len(parts) == 6 else "both"
        if mode not in {"both", "score", "depth"}:
            raise argparse.ArgumentTypeError(f"unsupported drift policy mode: {mode}")
        policies.append(
            DriftPolicy(
                name=label,
                feature_set=feature_set,
                beta=float(beta),
                min_component=min_component,
                max_component=max_component,
                adjust_score=mode in {"both", "score"},
                adjust_depth=mode in {"both", "depth"},
            )
        )
    return policies


def odds_bucket(odds: float | None) -> str:
    if odds is None or odds <= 1.0:
        return "missing"
    if odds < 3.5:
        return "<3.5"
    if odds < 4.5:
        return "3.5-4.5"
    if odds < 5.0:
        return "4.5-5"
    if odds < 6.0:
        return "5-6"
    if odds < 8.0:
        return "6-8"
    return ">=8"


def move_bucket(row: ActionRow, snapshot: str) -> str:
    if snapshot != "1h":
        return "not_available"
    base = row.euro_10h_odds
    current = row.euro_1h_odds
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


def q_parts(row: ActionRow, rank_lookup: dict[tuple[int, str], int], snapshot: str) -> tuple[str, str, str, str]:
    _, p = snapshot_odds_p(row, snapshot)
    return q_key(row, p, rank_lookup.get((row.match_id, row.action_code)))


def hierarchy_keys(
    row: ActionRow,
    *,
    snapshot: str,
    feature_set: str,
    rank_lookup: dict[tuple[int, str], int],
) -> list[tuple[str, ...]]:
    odds, _ = snapshot_odds_p(row, snapshot)
    action, hcp_b, q_rank, q_p_bucket = q_parts(row, rank_lookup, snapshot)
    ob = odds_bucket(odds)
    mb = move_bucket(row, snapshot)
    league = row.league or ""

    if feature_set == "action_odds":
        return [
            ("global",),
            ("action", action),
            ("action_odds", action, ob),
        ]
    if feature_set == "pocket_q":
        return [
            ("global",),
            ("action", action),
            ("action_hcp", action, hcp_b),
            ("pocket_q", action, hcp_b, q_rank, q_p_bucket),
            ("pocket_q_odds", action, hcp_b, q_rank, q_p_bucket, ob),
        ]
    if feature_set == "pocket_q_league":
        return [
            ("global",),
            ("action", action),
            ("action_hcp", action, hcp_b),
            ("pocket_q", action, hcp_b, q_rank, q_p_bucket),
            ("pocket_q_odds", action, hcp_b, q_rank, q_p_bucket, ob),
            ("pocket_q_odds_league", action, hcp_b, q_rank, q_p_bucket, ob, league),
        ]
    if feature_set == "pocket_q_move":
        if snapshot != "1h":
            raise ValueError("pocket_q_move is only valid for snapshot=1h")
        return [
            ("global",),
            ("action", action),
            ("action_hcp", action, hcp_b),
            ("pocket_q", action, hcp_b, q_rank, q_p_bucket),
            ("pocket_q_odds", action, hcp_b, q_rank, q_p_bucket, ob),
            ("pocket_q_odds_move", action, hcp_b, q_rank, q_p_bucket, ob, mb),
        ]
    raise ValueError(f"unsupported drift feature set: {feature_set}")


def train_drift_model(
    rows: list[ActionRow],
    *,
    snapshot: str,
    feature_set: str,
    prior_n: int,
    min_multiplier: float,
    max_multiplier: float,
) -> DriftModel:
    rank_lookup = snapshot_rank_lookup(rows, snapshot)
    values_by_key: dict[tuple[str, ...], list[float]] = defaultdict(list)
    level_order: dict[tuple[str, ...], int] = {}
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
        keys = hierarchy_keys(row, snapshot=snapshot, feature_set=feature_set, rank_lookup=rank_lookup)
        for idx, key in enumerate(keys):
            values_by_key[key].append(value)
            level_order[key] = idx

    means: dict[tuple[str, ...], float] = {}
    counts: dict[tuple[str, ...], int] = {}
    for key in sorted(values_by_key, key=lambda k: (level_order[k], k)):
        vals = values_by_key[key]
        counts[key] = len(vals)
        raw = sum(vals) / len(vals)
        if key == ("global",):
            means[key] = raw
        else:
            # Parent is the most specific known shorter hierarchy key for this row family.
            parent_mean = means.get(("global",), raw)
            for parent in sorted(
                [candidate for candidate in means if level_order.get(candidate, -1) < level_order[key]],
                key=lambda k: level_order.get(k, -1),
                reverse=True,
            ):
                if parent == ("global",) or key[1 : 1 + len(parent[1:])] == parent[1:]:
                    parent_mean = means[parent]
                    break
            means[key] = (raw * len(vals) + parent_mean * prior_n) / (len(vals) + prior_n)

    if ("global",) not in means:
        means[("global",)] = 0.0
        counts[("global",)] = 0
    return DriftModel(
        means=means,
        counts=counts,
        snapshot=snapshot,
        feature_set=feature_set,
        prior_n=prior_n,
        min_multiplier=min_multiplier,
        max_multiplier=max_multiplier,
    )


def predict_multiplier(
    model: DriftModel,
    row: ActionRow,
    *,
    rank_lookup: dict[tuple[int, str], int],
) -> tuple[float, tuple[str, ...], int]:
    keys = hierarchy_keys(row, snapshot=model.snapshot, feature_set=model.feature_set, rank_lookup=rank_lookup)
    chosen = ("global",)
    for key in reversed(keys):
        if key in model.means:
            chosen = key
            break
    multiplier = math.exp(model.means.get(chosen, model.means[("global",)]))
    multiplier = max(model.min_multiplier, min(model.max_multiplier, multiplier))
    return multiplier, chosen, model.counts.get(chosen, 0)


def component_from_multipliers(
    multipliers: dict[str, float],
    *,
    beta: float,
    min_component: float,
    max_component: float,
) -> dict[str, float]:
    finite = [v for v in multipliers.values() if math.isfinite(v) and v > 0]
    if not finite:
        return {key: 1.0 for key in multipliers}
    center = float(np.median(finite))
    if center <= 0 or not math.isfinite(center):
        center = 1.0
    out = {}
    for key, value in multipliers.items():
        if not math.isfinite(value) or value <= 0:
            out[key] = min_component
            continue
        component = (value / center) ** beta
        out[key] = max(min_component, min(max_component, component))
    return out


def apply_drift_policy(
    legs: list[Leg],
    *,
    base_weights: dict[str, float],
    model: DriftModel | None,
    policy: DriftPolicy,
    rank_lookup: dict[tuple[int, str], int],
    snapshot: str,
) -> tuple[list[Leg], dict[str, float], list[dict[str, object]]]:
    if policy.name == "base" or model is None:
        diagnostics = []
        for leg in legs:
            odds, _ = snapshot_odds_p(leg.row, snapshot)
            realized_multiplier = (
                leg.row.winning_sp / odds
                if odds is not None and odds > 1.0 and leg.row.hit == 1 and leg.row.winning_sp > 0
                else float("nan")
            )
            diagnostics.append(
                {
                    "leg_id": leg.leg_id,
                    "match_id": leg.row.match_id,
                    "action_code": leg.row.action_code,
                    "policy": policy.name,
                    "pred_sp_multiplier": 1.0,
                    "drift_component": 1.0,
                    "drift_key": "",
                    "drift_key_n": "",
                    "score_factor_original": leg.score_factor,
                    "score_factor_adjusted": leg.score_factor,
                    "base_depth_weight": base_weights.get(leg.leg_id, 1.0),
                    "adjusted_depth_weight": base_weights.get(leg.leg_id, 1.0),
                    "actual_hit": leg.row.hit,
                    "snapshot_odds": odds if odds is not None else "",
                    "winning_sp": leg.row.winning_sp,
                    "realized_sp_multiplier": realized_multiplier,
                    "league": leg.row.league,
                    "hcp": leg.row.hcp,
                }
                )
        return legs, {leg.leg_id: base_weights.get(leg.leg_id, 1.0) for leg in legs}, diagnostics

    pred: dict[str, float] = {}
    key_by_leg: dict[str, tuple[str, ...]] = {}
    n_by_leg: dict[str, int] = {}
    for leg in legs:
        multiplier, key, n = predict_multiplier(model, leg.row, rank_lookup=rank_lookup)
        pred[leg.leg_id] = multiplier
        key_by_leg[leg.leg_id] = key
        n_by_leg[leg.leg_id] = n
    components = component_from_multipliers(
        pred,
        beta=policy.beta,
        min_component=policy.min_component,
        max_component=policy.max_component,
    )

    out: list[Leg] = []
    weights: dict[str, float] = {}
    diagnostics: list[dict[str, object]] = []
    for leg in legs:
        component = components.get(leg.leg_id, 1.0)
        score_factor = leg.score_factor * component if policy.adjust_score else leg.score_factor
        depth_weight = base_weights.get(leg.leg_id, 1.0) * component if policy.adjust_depth else base_weights.get(leg.leg_id, 1.0)
        depth_weight = max(0.35, min(2.50, depth_weight))
        converted = replace(
            leg,
            strategy=policy.name,
            score_factor=score_factor,
            source_rule=(
                f"{leg.source_rule};drift_policy={policy.name};"
                f"pred_sp_mult={pred[leg.leg_id]:.6f};drift_component={component:.6f};"
                f"drift_key={'|'.join(key_by_leg[leg.leg_id])};drift_key_n={n_by_leg[leg.leg_id]}"
            ),
        )
        out.append(converted)
        weights[converted.leg_id] = depth_weight
        odds, _ = snapshot_odds_p(leg.row, model.snapshot)
        realized_multiplier = (
            leg.row.winning_sp / odds
            if odds is not None and odds > 1.0 and leg.row.hit == 1 and leg.row.winning_sp > 0
            else float("nan")
        )
        diagnostics.append(
            {
                "leg_id": converted.leg_id,
                "match_id": leg.row.match_id,
                "action_code": leg.row.action_code,
                "policy": policy.name,
                "pred_sp_multiplier": pred[leg.leg_id],
                "drift_component": component,
                "drift_key": "|".join(key_by_leg[leg.leg_id]),
                "drift_key_n": n_by_leg[leg.leg_id],
                "score_factor_original": leg.score_factor,
                "score_factor_adjusted": score_factor,
                "base_depth_weight": base_weights.get(leg.leg_id, 1.0),
                "adjusted_depth_weight": depth_weight,
                "actual_hit": leg.row.hit,
                "snapshot_odds": odds if odds is not None else "",
                "winning_sp": leg.row.winning_sp,
                "realized_sp_multiplier": realized_multiplier,
                "league": leg.row.league,
                "hcp": leg.row.hcp,
            }
        )
    return out, weights, diagnostics


def drift_snapshot_row(
    *,
    strategy: str,
    issue: str,
    diagnostics: list[dict[str, object]],
    tickets: list[Ticket],
) -> dict[str, object]:
    values = [float(row["pred_sp_multiplier"]) for row in diagnostics if math.isfinite(float(row["pred_sp_multiplier"]))]
    components = [float(row["drift_component"]) for row in diagnostics if math.isfinite(float(row["drift_component"]))]
    used: dict[str, int] = defaultdict(int)
    for ticket in tickets:
        for leg in ticket.legs:
            used[leg.leg_id] += 1
    used_values = [
        float(row["pred_sp_multiplier"])
        for row in diagnostics
        if used.get(str(row["leg_id"]), 0) > 0 and math.isfinite(float(row["pred_sp_multiplier"]))
    ]
    return {
        "strategy": strategy,
        "issue": issue,
        "n_legs": len(diagnostics),
        "n_tickets": len(tickets),
        "avg_pred_sp_multiplier": sum(values) / len(values) if values else float("nan"),
        "p10_pred_sp_multiplier": float(np.quantile(values, 0.10)) if values else float("nan"),
        "p90_pred_sp_multiplier": float(np.quantile(values, 0.90)) if values else float("nan"),
        "avg_used_pred_sp_multiplier": sum(used_values) / len(used_values) if used_values else float("nan"),
        "avg_drift_component": sum(components) / len(components) if components else float("nan"),
    }


def issue_year(issue: object) -> int:
    text = str(issue)
    if len(text) < 2 or not text[:2].isdigit():
        return 0
    return 2000 + int(text[:2])


def annual_summary_rows(issue_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], dict[str, float]] = {}
    for row in issue_rows:
        key = (str(row["strategy"]), issue_year(row["issue"]))
        bucket = grouped.setdefault(
            key,
            {
                "n_issues": 0.0,
                "stake_units": 0.0,
                "profit_units": 0.0,
                "hits": 0.0,
                "tickets": 0.0,
                "profitable_issues": 0.0,
            },
        )
        bucket["n_issues"] += 1
        bucket["stake_units"] += float(row["stake_units"])
        bucket["profit_units"] += float(row["profit_units"])
        bucket["hits"] += float(row["hits"])
        bucket["tickets"] += float(row["tickets"])
        if float(row["profit_units"]) > 0:
            bucket["profitable_issues"] += 1

    out: list[dict[str, object]] = []
    for (strategy, year), vals in sorted(grouped.items()):
        stake = vals["stake_units"]
        tickets = vals["tickets"]
        n_issues = vals["n_issues"]
        out.append(
            {
                "strategy": strategy,
                "year": year,
                "n_issues": int(n_issues),
                "stake_units": stake,
                "profit_units": vals["profit_units"],
                "roi": vals["profit_units"] / stake if stake > 0 else float("nan"),
                "hits": int(vals["hits"]),
                "tickets": int(tickets),
                "hit_rate": vals["hits"] / tickets if tickets > 0 else float("nan"),
                "profitable_issues": int(vals["profitable_issues"]),
                "issue_win_rate": vals["profitable_issues"] / n_issues if n_issues > 0 else float("nan"),
            }
        )
    return out


def annual_pivot_rows(annual_rows: list[dict[str, object]], *, metric: str) -> list[dict[str, object]]:
    years = sorted({int(row["year"]) for row in annual_rows})
    strategies = sorted({str(row["strategy"]) for row in annual_rows})
    values = {(int(row["year"]), str(row["strategy"])): row.get(metric, "") for row in annual_rows}
    out: list[dict[str, object]] = []
    for year in years:
        row: dict[str, object] = {"year": year}
        for strategy in strategies:
            row[strategy] = values.get((year, strategy), "")
        out.append(row)
    return out


def comparison_rows(
    stress_rows: list[dict[str, object]],
    issue_rows: list[dict[str, object]],
    *,
    recent_start_year: int = 2023,
) -> list[dict[str, object]]:
    base = next((row for row in stress_rows if "__base__" in str(row["strategy"])), None)
    base_profit = float(base["total_profit_units"]) if base else 0.0
    base_roi = float(base["roi"]) if base else 0.0

    recent: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in issue_rows:
        if issue_year(row["issue"]) < recent_start_year:
            continue
        strategy = str(row["strategy"])
        recent[strategy]["issues"] += 1
        recent[strategy]["stake"] += float(row["stake_units"])
        recent[strategy]["profit"] += float(row["profit_units"])
        recent[strategy]["hits"] += float(row["hits"])
        recent[strategy]["tickets"] += float(row["tickets"])
        if float(row["profit_units"]) > 0:
            recent[strategy]["profitable_issues"] += 1

    out: list[dict[str, object]] = []
    for row in sorted(stress_rows, key=lambda r: float(r["roi"]), reverse=True):
        strategy = str(row["strategy"])
        rec = recent.get(strategy, {})
        recent_stake = float(rec.get("stake", 0.0))
        recent_tickets = float(rec.get("tickets", 0.0))
        recent_issues = float(rec.get("issues", 0.0))
        out.append(
            {
                "strategy": strategy,
                "total_profit_units": row["total_profit_units"],
                "roi": row["roi"],
                "ex_top1_roi": row["ex_top1_roi"],
                "ex_top2_roi": row["ex_top2_roi"],
                "hit_rate": row["hit_rate"],
                "issue_win_rate": row["issue_win_rate"],
                "profitable_issues": row["profitable_issues"],
                "best_issue_profit_share": row["best_issue_profit_share"],
                "lottery_stress_verdict": row["lottery_stress_verdict"],
                "recent_profit_units": rec.get("profit", float("nan")),
                "recent_roi": rec.get("profit", float("nan")) / recent_stake if recent_stake > 0 else float("nan"),
                "recent_hit_rate": rec.get("hits", float("nan")) / recent_tickets if recent_tickets > 0 else float("nan"),
                "recent_issue_win_rate": (
                    rec.get("profitable_issues", float("nan")) / recent_issues if recent_issues > 0 else float("nan")
                ),
                "profit_delta_vs_base": float(row["total_profit_units"]) - base_profit,
                "roi_delta_vs_base": float(row["roi"]) - base_roi,
            }
        )
    return out


def drift_calibration_rows(component_rows: list[dict[str, object]], *, n_bins: int = 5) -> list[dict[str, object]]:
    by_strategy: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in component_rows:
        try:
            pred = float(row["pred_sp_multiplier"])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(pred):
            continue
        by_strategy[str(row["strategy"])].append(row)

    out: list[dict[str, object]] = []
    for strategy, rows in sorted(by_strategy.items()):
        if "__base" in strategy or len(rows) < n_bins:
            continue
        rows = sorted(rows, key=lambda r: float(r["pred_sp_multiplier"]))
        for bin_idx in range(n_bins):
            lo = len(rows) * bin_idx // n_bins
            hi = len(rows) * (bin_idx + 1) // n_bins
            chunk = rows[lo:hi]
            if not chunk:
                continue
            hits = [r for r in chunk if int(r.get("actual_hit", 0)) == 1]
            realized = []
            for r in hits:
                try:
                    value = float(r.get("realized_sp_multiplier", float("nan")))
                except (TypeError, ValueError):
                    value = float("nan")
                if math.isfinite(value):
                    realized.append(value)
            preds = [float(r["pred_sp_multiplier"]) for r in chunk]
            components = [float(r["drift_component"]) for r in chunk if math.isfinite(float(r["drift_component"]))]
            odds = []
            for r in chunk:
                try:
                    value = float(r.get("snapshot_odds", float("nan")))
                except (TypeError, ValueError):
                    value = float("nan")
                if math.isfinite(value):
                    odds.append(value)
            out.append(
                {
                    "strategy": strategy,
                    "bin": bin_idx + 1,
                    "n_legs": len(chunk),
                    "pred_min": min(preds),
                    "pred_max": max(preds),
                    "avg_pred_sp_multiplier": sum(preds) / len(preds),
                    "avg_drift_component": sum(components) / len(components) if components else float("nan"),
                    "actual_hit_rate": len(hits) / len(chunk),
                    "n_hit_legs": len(hits),
                    "avg_realized_sp_multiplier_on_hits": (
                        sum(realized) / len(realized) if realized else float("nan")
                    ),
                    "avg_snapshot_odds": sum(odds) / len(odds) if odds else float("nan"),
                }
            )
    return out


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
    policies = parse_policies(args.policies)
    feature_sets = sorted({policy.feature_set for policy in policies if policy.feature_set != "none"})
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    composition_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    drift_rows: list[dict[str, object]] = []
    component_rows: list[dict[str, object]] = []
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
        drift_models = {
            feature_set: train_drift_model(
                train_action_rows,
                snapshot=args.snapshot,
                feature_set=feature_set,
                prior_n=args.sp_prior_n,
                min_multiplier=args.min_sp_multiplier,
                max_multiplier=args.max_sp_multiplier,
            )
            for feature_set in feature_sets
        }
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

        market_rows = []
        for sample in test_samples:
            vals = []
            for code in ("3", "1", "0"):
                _, p = snapshot_odds_p(sample.rows[code], args.snapshot)
                vals.append(float(p) if p is not None and p > 0 else 0.0)
            total = sum(vals)
            market_rows.append([v / total if total > 0 else 1 / 3 for v in vals])
        market_by_match = {sample.match_id: np.asarray(market_rows[i], dtype=float) for i, sample in enumerate(test_samples)}
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
        test_rank_lookup = snapshot_rank_lookup(test_action_rows, args.snapshot)

        for spec in gate_specs:
            policy_legs = filter_legs_for_spec(base_legs, metas, spec)
            if count_tags(policy_legs, metas)["core"] < spec.min_issue_core_legs:
                continue
            if len(dedup_legs_by_match(policy_legs)) < args.n_legs:
                continue
            for policy in policies:
                strategy = f"q_pocket_{spec.name}__{policy.name}"
                model = drift_models.get(policy.feature_set)
                adjusted_legs, adjusted_weights, diagnostics = apply_drift_policy(
                    policy_legs,
                    base_weights=base_weights,
                    model=model,
                    policy=policy,
                    rank_lookup=test_rank_lookup,
                    snapshot=args.snapshot,
                )
                tickets = make_constrained_depth_tickets(
                    adjusted_legs,
                    metas=metas,
                    depth_weights=adjusted_weights,
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
                candidate_rows.extend(leg_detail_rows(adjusted_legs, metas, strategy, test_issue))
                coverage_rows.append(
                    coverage_snapshot(
                        strategy=strategy,
                        test_issue=test_issue,
                        q_legs=base_legs,
                        policy_legs=adjusted_legs,
                        tickets=tickets,
                        metas=metas,
                    )
                )
                drift_rows.append(drift_snapshot_row(strategy=strategy, issue=test_issue, diagnostics=diagnostics, tickets=tickets))
                for row in diagnostics:
                    component_rows.append({"strategy": strategy, "issue": test_issue, **row})

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
                "drift_feature_sets": ",".join(feature_sets),
            }
        )

    budget_rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=args.issue_budget_units, fractional=False)
    summary = summarize_tickets(budget_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    stress = stress_summary(budget_rows)
    stress_by_strategy = {str(row["strategy"]): row for row in stress}
    issue_profit = issue_profit_rows(budget_rows)
    annual = annual_summary_rows(issue_profit)
    annual_profit_pivot = annual_pivot_rows(annual, metric="profit_units")
    annual_roi_pivot = annual_pivot_rows(annual, metric="roi")
    comparison = comparison_rows(stress, issue_profit)
    calibration = drift_calibration_rows(component_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "q_pocket_drift_adjusted_tickets.csv", ticket_rows)
    write_csv(out / "q_pocket_drift_adjusted_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_drift_adjusted_summary.csv", summary)
    write_csv(out / "q_pocket_drift_adjusted_stress_summary.csv", stress)
    write_csv(out / "q_pocket_drift_adjusted_issue_profit.csv", issue_profit)
    write_csv(out / "q_pocket_drift_adjusted_composition.csv", composition_rows)
    write_csv(out / "q_pocket_drift_adjusted_coverage.csv", coverage_rows)
    write_csv(out / "q_pocket_drift_adjusted_candidates.csv", candidate_rows)
    write_csv(out / "q_pocket_drift_adjusted_issue_drift.csv", drift_rows)
    write_csv(out / "q_pocket_drift_adjusted_components.csv", component_rows)
    write_csv(out / "q_pocket_drift_adjusted_windows.csv", window_rows)
    write_csv(out / "q_pocket_drift_adjusted_annual_summary.csv", annual)
    write_csv(out / "q_pocket_drift_adjusted_annual_profit_pivot.csv", annual_profit_pivot)
    write_csv(out / "q_pocket_drift_adjusted_annual_roi_pivot.csv", annual_roi_pivot)
    write_csv(out / "q_pocket_drift_adjusted_comparison.csv", comparison)
    write_csv(out / "q_pocket_drift_adjusted_calibration.csv", calibration)

    report = [
        "# N=7 q-pocket drift-adjusted q evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Settlement quality: `{args.settlement_quality}`",
        f"- Gate specs: `{args.gate_specs}`",
        f"- Policies: `{args.policies}`",
        f"- Same-budget issue stake: `{args.issue_budget_units}`",
        "",
        "q-pocket remains the selector. SP drift adjusts q score/depth; no quadrant drop is applied.",
        "",
        "## Budget Summary",
        md_table(compact_summary(summary, stress_by_strategy)),
        "## Stress Summary",
        md_table(stress[:120]),
        "## Comparison",
        md_table(comparison[:120]),
        "## Annual ROI",
        md_table(annual_roi_pivot[:120]),
        "## Drift Calibration",
        md_table(calibration[:120]),
        "",
        "## Files",
        "",
        "- `q_pocket_drift_adjusted_summary.csv`",
        "- `q_pocket_drift_adjusted_stress_summary.csv`",
        "- `q_pocket_drift_adjusted_issue_profit.csv`",
        "- `q_pocket_drift_adjusted_issue_drift.csv`",
        "- `q_pocket_drift_adjusted_components.csv`",
        "- `q_pocket_drift_adjusted_calibration.csv`",
        "- `q_pocket_drift_adjusted_annual_summary.csv`",
        "- `q_pocket_drift_adjusted_annual_profit_pivot.csv`",
        "- `q_pocket_drift_adjusted_annual_roi_pivot.csv`",
        "- `q_pocket_drift_adjusted_comparison.csv`",
        "- `q_pocket_budget_rows.csv` compatibility alias",
        "",
    ]
    (out / "q_pocket_drift_adjusted_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'q_pocket_drift_adjusted_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_pocket_drift_adjusted_q"))
    parser.add_argument("--min-year", type=int, default=2014)
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
    parser.add_argument("--sp-prior-n", type=int, default=80)
    parser.add_argument("--min-sp-multiplier", type=float, default=0.25)
    parser.add_argument("--max-sp-multiplier", type=float, default=1.50)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--gate-specs", default="keyed_pockets")
    parser.add_argument(
        "--policies",
        default=(
            "base,"
            "daq_action_b50:action_odds:0.50:0.75:1.25,"
            "daq_pocket_b25:pocket_q:0.25:0.80:1.20,"
            "daq_pocket_b50:pocket_q:0.50:0.75:1.25,"
            "daq_pocket_b100:pocket_q:1.00:0.65:1.35,"
            "daq_pocket_league_b50:pocket_q_league:0.50:0.75:1.25"
        ),
    )
    parser.add_argument("--settlement-quality", choices=("any", "trusted", "mismatch", "missing_sp"), default="trusted")
    args = parser.parse_args()
    if args.snapshot == "10h" and "pocket_q_move" in args.policies:
        raise SystemExit("pocket_q_move is only valid with --snapshot 1h")
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
