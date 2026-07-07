#!/usr/bin/env python3
"""Estimate rolling segment N串1 small-combo betting plans."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import replay_rolling_segment_n_tickets as rolling  # noqa: E402
from select_rolling_segment_n import recommend_segment_n  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results/segment_betting_plan"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/research"
OUTCOME_CODES = ("3", "1", "0")
BETTING_STRATEGY_FAMILY = "segment_betting_plan"
BETTING_STRATEGY_VERSION = "segment_betting_v0.3.0000"
ARTIFACT_SCHEMA_VERSION = "segment_betting_artifact_v1"


@dataclass(frozen=True)
class LegMetrics:
    leg: rolling.LegRow
    codes: tuple[str, ...]
    width: int
    hit_prob: float
    q_sum: float
    value_per_cost: float
    score: float


@dataclass(frozen=True)
class BundleCandidate:
    segment_idx: int
    bundle_idx: int
    arm: str
    n_value: int
    match_indices: tuple[int, ...]
    leg_codes: tuple[str, ...]
    widths: tuple[int, ...]
    cost_units: float
    expected_payout_units: float
    expected_profit_units: float
    expected_roi: float
    hit_prob: float
    payout_units: float
    profit_units: float
    realized_hit: bool
    score: float


@dataclass(frozen=True)
class StakedBundle:
    candidate: BundleCandidate
    stake_multiplier: int


def product(values: Iterable[float]) -> float:
    out = 1.0
    for value in values:
        out *= value
    return out


def stable_seed(*parts: object) -> int:
    text = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)


def parse_optional_decision_time(value: str) -> datetime | None:
    token = str(value or "").strip()
    return rolling.parse_dt(token) if token else None


def format_optional_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def hours_between(start: datetime | None, end: datetime) -> float | str:
    if start is None:
        return ""
    return round((end - start).total_seconds() / 3600.0, 6)


def planning_scope_risk(planning_scope: str) -> tuple[int, str, str]:
    if planning_scope == "remaining_issue":
        return (
            1,
            "elevated",
            "remaining_issue_selected_user_accepts_far_kickoff_sp_drift",
        )
    return 0, "bounded", "next_segment_only_limits_far_kickoff_sp_drift"


def staked_bundle_cost_units(item: StakedBundle) -> float:
    return item.candidate.cost_units * item.stake_multiplier


def staked_bundle_payout_units(item: StakedBundle) -> float:
    return item.candidate.payout_units * item.stake_multiplier


def staked_bundle_expected_profit_units(item: StakedBundle) -> float:
    return item.candidate.expected_profit_units * item.stake_multiplier


def sample_seeds_from_args(args: argparse.Namespace) -> list[int]:
    if getattr(args, "sample_seeds", ""):
        seeds: list[int] = []
        for raw in str(args.sample_seeds).split(","):
            token = raw.strip()
            if not token:
                continue
            seeds.append(int(token))
        if not seeds:
            raise SystemExit("--sample-seeds did not contain any integer seeds")
        return seeds
    seed_count = max(1, int(getattr(args, "seed_count", 1)))
    return [int(args.sample_seed) + offset for offset in range(seed_count)]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[int(pos)]
    weight = pos - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def metric_stats(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [rolling.fnum(row.get(key)) for row in rows if row.get(key) != ""]
    if not values:
        return {"min": 0.0, "p10": 0.0, "mean": 0.0, "median": 0.0, "p90": 0.0, "max": 0.0}
    return {
        "min": round(min(values), 6),
        "p10": round(percentile(values, 0.10), 6),
        "mean": round(sum(values) / len(values), 6),
        "median": round(percentile(values, 0.50), 6),
        "p90": round(percentile(values, 0.90), 6),
        "max": round(max(values), 6),
    }


def mean_summary(seed_summary_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not seed_summary_rows:
        return {}
    out: dict[str, Any] = {}
    for key, value in seed_summary_rows[0].items():
        if key == "sample_seed":
            continue
        values = [rolling.fnum(row.get(key)) for row in seed_summary_rows if row.get(key) != ""]
        if not values:
            out[key] = ""
        elif all(float(value).is_integer() for value in values) and len(set(values)) == 1:
            out[key] = int(values[0])
        else:
            out[key] = round(sum(values) / len(values), 6)
    return out


def aggregate_seed_summaries(seed_summary_rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [
        "base_cost_yuan",
        "selected_cost_yuan",
        "payout_yuan",
        "profit_yuan",
        "roi",
        "selected_bundles",
        "stake_multiplier_units",
        "selected_segments",
        "dead_segments",
    ]
    return {
        "seed_count": len(seed_summary_rows),
        "seeds": [row["sample_seed"] for row in seed_summary_rows],
        "summary_mode": "multi_seed_mean" if len(seed_summary_rows) > 1 else "single_seed",
        "mean_summary": mean_summary(seed_summary_rows),
        "metrics": {metric: metric_stats(seed_summary_rows, metric) for metric in metrics},
    }


def aggregate_segment_seed_rows(segment_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in segment_rows:
        grouped.setdefault((str(row.get("segment_idx")), str(row.get("arm"))), []).append(row)

    out: list[dict[str, Any]] = []
    for (segment_idx, arm), rows in sorted(grouped.items(), key=lambda item: (int(item[0][0]), item[0][1])):
        n_values = sorted({str(row.get("recommended_n", "")) for row in rows if row.get("recommended_n", "") != ""})
        row0 = rows[0]
        out.append(
            {
                "segment_idx": segment_idx,
                "arm": arm,
                "sample_count": len(rows),
                "segment_start": row0.get("segment_start", ""),
                "segment_end": row0.get("segment_end", ""),
                "eligible_matches": row0.get("eligible_matches", ""),
                "expected_coverage_hit_rate": row0.get("expected_coverage_hit_rate", ""),
                "actual_coverage_hits": row0.get("actual_coverage_hits", ""),
                "actual_coverage_hit_rate": row0.get("actual_coverage_hit_rate", ""),
                "recommended_n_values": ",".join(n_values),
                "recommended_n_stable": int(len(n_values) <= 1),
                "selected_bundles_mean": metric_stats(rows, "selected_bundles")["mean"],
                "selected_bundles_min": metric_stats(rows, "selected_bundles")["min"],
                "selected_bundles_max": metric_stats(rows, "selected_bundles")["max"],
                "base_cost_yuan_mean": metric_stats(rows, "base_cost_yuan")["mean"],
                "cost_yuan_mean": metric_stats(rows, "selected_cost_yuan")["mean"],
                "stake_multiplier_units_mean": metric_stats(rows, "stake_multiplier_units")["mean"],
                "payout_yuan_mean": metric_stats(rows, "payout_yuan")["mean"],
                "profit_yuan_min": metric_stats(rows, "profit_yuan")["min"],
                "profit_yuan_p10": metric_stats(rows, "profit_yuan")["p10"],
                "profit_yuan_mean": metric_stats(rows, "profit_yuan")["mean"],
                "profit_yuan_median": metric_stats(rows, "profit_yuan")["median"],
                "profit_yuan_p90": metric_stats(rows, "profit_yuan")["p90"],
                "profit_yuan_max": metric_stats(rows, "profit_yuan")["max"],
                "roi_min": metric_stats(rows, "roi")["min"],
                "roi_mean": metric_stats(rows, "roi")["mean"],
                "roi_max": metric_stats(rows, "roi")["max"],
                "dead_segment_rate": round(
                    sum(1 for row in rows if rolling.fnum(row.get("dead_segment")) > 0) / len(rows),
                    6,
                ),
                "width_counts": row0.get("width_counts", ""),
                "match_indices": row0.get("match_indices", ""),
            }
        )
    return out


def betting_strategy_parameter_schema() -> list[dict[str, Any]]:
    return [
        {
            "key": "stake_mode",
            "label": "stake mode",
            "ui_level": "basic",
            "type": "enum",
            "default": "scale_to_budget",
            "options": ["scale_to_budget", "unit_once"],
            "effect": "Scale selected bundles toward the segment budget, or buy each selected bundle once for audit.",
        },
        {
            "key": "planning_scope",
            "label": "planning scope",
            "ui_level": "basic",
            "type": "enum",
            "default": "next_segment",
            "options": ["next_segment", "remaining_issue"],
            "effect": "Choose only the next dynamic segment, or buy every remaining issue segment while accepting SP drift risk.",
        },
        {
            "key": "decision_time",
            "label": "decision time",
            "ui_level": "basic",
            "type": "datetime",
            "default": "",
            "effect": "Filters out matches that have already kicked off at planning time.",
        },
        {
            "key": "segment_budget_yuan",
            "label": "segment budget",
            "ui_level": "basic",
            "type": "number",
            "unit": "yuan",
            "default": 1000.0,
            "min": 100.0,
            "step": 50.0,
            "effect": "Caps total cost per rolling kickoff segment.",
        },
        {
            "key": "window_hours",
            "label": "base window",
            "ui_level": "basic",
            "type": "number",
            "unit": "hours",
            "default": 12.0,
            "min": 2.0,
            "step": 1.0,
            "effect": "Smaller windows are closer to kickoff but may contain too few matches.",
        },
        {
            "key": "extend_hours",
            "label": "extend windows",
            "ui_level": "basic",
            "type": "string_list",
            "unit": "hours",
            "default": "18,24,36",
            "effect": "Fallback windows used when the base window has too few matches.",
        },
        {
            "key": "min_matches",
            "label": "minimum matches",
            "ui_level": "basic",
            "type": "integer",
            "default": 6,
            "min": 2,
            "step": 1,
            "effect": "Below this count the segment extends to a longer window.",
        },
        {
            "key": "max_matches",
            "label": "maximum matches",
            "ui_level": "basic",
            "type": "integer",
            "default": 24,
            "min": 4,
            "step": 1,
            "effect": "Caps very dense segments before N selection.",
        },
        {
            "key": "max_n",
            "label": "maximum N",
            "ui_level": "basic",
            "type": "integer",
            "default": 8,
            "min": 3,
            "max": 8,
            "step": 1,
            "effect": "Upper bound for N串1; actual N still depends on coverage quality.",
        },
        {
            "key": "seed_count",
            "label": "stability seeds",
            "ui_level": "basic",
            "type": "integer",
            "default": 1,
            "min": 1,
            "step": 1,
            "recommended": 20,
            "effect": "Runs repeated sampled plans and reports mean plus variation interval.",
        },
        {
            "key": "stake_yuan_per_ticket",
            "label": "ticket stake",
            "ui_level": "advanced",
            "type": "number",
            "unit": "yuan",
            "default": 2.0,
            "min": 2.0,
            "step": 2.0,
            "effect": "Cost multiplier per expanded ticket. Current BJDC assumption is 2 yuan.",
        },
        {
            "key": "min_n",
            "label": "minimum N",
            "ui_level": "advanced",
            "type": "integer",
            "default": 3,
            "min": 2,
            "max": 8,
            "step": 1,
            "effect": "Lower bound after budget or coverage downgrades.",
        },
        {
            "key": "sample_attempts",
            "label": "sample attempts",
            "ui_level": "advanced",
            "type": "integer",
            "default": 12000,
            "min": 1000,
            "step": 1000,
            "effect": "More attempts reduce missed candidate noise but cost more CPU.",
        },
        {
            "key": "max_overlap",
            "label": "max overlap",
            "ui_level": "advanced",
            "type": "integer_or_null",
            "default": None,
            "effect": "Limits shared matches between selected bundles; null means N-2.",
        },
        {
            "key": "allow_negative_ev",
            "label": "allow negative EV",
            "ui_level": "advanced",
            "type": "boolean",
            "default": False,
            "effect": "Mostly for diagnostics; live planning should normally keep this off.",
        },
        {
            "key": "sample_seed",
            "label": "primary seed",
            "ui_level": "debug",
            "type": "integer",
            "default": 20260707,
            "effect": "Reproducibility key for the executable primary sampled plan.",
        },
        {
            "key": "sample_seeds",
            "label": "explicit seed list",
            "ui_level": "debug",
            "type": "string",
            "default": "",
            "effect": "Comma-separated replay seeds. Overrides primary seed and seed count.",
        },
    ]


def selected_codes_for(leg: rolling.LegRow, arm: str) -> tuple[str, ...]:
    if arm == "active":
        return leg.active_codes
    if arm == "shadow":
        return leg.shadow_codes
    raise ValueError("arm must be active or shadow")


def leg_metrics(leg: rolling.LegRow, arm: str) -> LegMetrics | None:
    codes = selected_codes_for(leg, arm)
    if not codes:
        return None
    width = len(codes)
    hit_prob = sum(leg.probabilities.get(code, 0.0) for code in codes)
    q_sum = sum(leg.probabilities.get(code, 0.0) * leg.sp.get(code, 0.0) for code in codes)
    value_per_cost = q_sum / width if width else 0.0
    width_penalty = width ** 0.35
    score = max(0.000001, (max(hit_prob, 0.000001) ** 1.35) * max(value_per_cost, 0.000001) / width_penalty)
    return LegMetrics(
        leg=leg,
        codes=codes,
        width=width,
        hit_prob=hit_prob,
        q_sum=q_sum,
        value_per_cost=value_per_cost,
        score=score,
    )


def weighted_sample_indices(weights: list[float], k: int, rng: random.Random) -> tuple[int, ...]:
    remaining = list(range(len(weights)))
    selected: list[int] = []
    for _ in range(min(k, len(remaining))):
        total = sum(max(0.0, weights[idx]) for idx in remaining)
        if total <= 0:
            choice_pos = rng.randrange(len(remaining))
            selected.append(remaining.pop(choice_pos))
            continue
        marker = rng.random() * total
        running = 0.0
        chosen_pos = len(remaining) - 1
        for pos, idx in enumerate(remaining):
            running += max(0.0, weights[idx])
            if running >= marker:
                chosen_pos = pos
                break
        selected.append(remaining.pop(chosen_pos))
    return tuple(sorted(selected))


def make_bundle_candidate(
    *,
    metrics: list[LegMetrics],
    indices: tuple[int, ...],
    segment_idx: int,
    bundle_idx: int,
    arm: str,
    n_value: int,
) -> BundleCandidate:
    legs = [metrics[idx] for idx in indices]
    cost_units = product(float(item.width) for item in legs)
    expected_payout_units = product(item.q_sum for item in legs)
    expected_profit_units = expected_payout_units - cost_units
    expected_roi = expected_profit_units / cost_units if cost_units else -1.0
    hit_prob = product(item.hit_prob for item in legs)
    realized_hit = all(item.leg.actual_code in item.codes and item.leg.winning_sp is not None for item in legs)
    payout_units = product(float(item.leg.winning_sp or 0.0) for item in legs) if realized_hit else 0.0
    profit_units = payout_units - cost_units
    return BundleCandidate(
        segment_idx=segment_idx,
        bundle_idx=bundle_idx,
        arm=arm,
        n_value=n_value,
        match_indices=tuple(item.leg.match_idx for item in legs),
        leg_codes=tuple("+".join(item.codes) for item in legs),
        widths=tuple(item.width for item in legs),
        cost_units=cost_units,
        expected_payout_units=expected_payout_units,
        expected_profit_units=expected_profit_units,
        expected_roi=expected_roi,
        hit_prob=hit_prob,
        payout_units=payout_units,
        profit_units=profit_units,
        realized_hit=realized_hit,
        score=expected_profit_units * (hit_prob ** 0.35),
    )


def candidate_key(candidate: BundleCandidate) -> tuple[int, ...]:
    return candidate.match_indices


def generate_candidates(
    *,
    metrics: list[LegMetrics],
    segment_idx: int,
    arm: str,
    n_value: int,
    budget_units: float,
    sample_attempts: int,
    seed: int,
) -> list[BundleCandidate]:
    if n_value <= 0 or len(metrics) < n_value:
        return []
    weights = [item.score for item in metrics]
    rng = random.Random(seed)
    keys: set[tuple[int, ...]] = set()
    candidates: list[BundleCandidate] = []

    ranked_indices = sorted(range(len(metrics)), key=lambda idx: metrics[idx].score, reverse=True)
    deterministic: list[tuple[int, ...]] = []
    deterministic.append(tuple(sorted(ranked_indices[:n_value])))
    for start in range(0, max(0, min(len(ranked_indices) - n_value + 1, n_value + 6))):
        deterministic.append(tuple(sorted(ranked_indices[start : start + n_value])))

    for indices in deterministic:
        if len(indices) == n_value and indices not in keys:
            keys.add(indices)
            candidates.append(
                make_bundle_candidate(
                    metrics=metrics,
                    indices=indices,
                    segment_idx=segment_idx,
                    bundle_idx=len(candidates) + 1,
                    arm=arm,
                    n_value=n_value,
                )
            )

    for _ in range(sample_attempts):
        indices = weighted_sample_indices(weights, n_value, rng)
        if len(indices) != n_value or indices in keys:
            continue
        keys.add(indices)
        candidate = make_bundle_candidate(
            metrics=metrics,
            indices=indices,
            segment_idx=segment_idx,
            bundle_idx=len(candidates) + 1,
            arm=arm,
            n_value=n_value,
        )
        if candidate.cost_units <= budget_units:
            candidates.append(candidate)
    return candidates


def select_bundles(
    candidates: list[BundleCandidate],
    *,
    budget_units: float,
    max_overlap: int,
    positive_ev_only: bool,
) -> list[BundleCandidate]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.expected_profit_units,
            item.expected_roi,
            item.hit_prob,
            -item.cost_units,
        ),
        reverse=True,
    )
    selected: list[BundleCandidate] = []
    spent = 0.0
    selected_sets: list[set[int]] = []
    for candidate in ordered:
        if positive_ev_only and candidate.expected_profit_units <= 0:
            continue
        if candidate.cost_units <= 0 or spent + candidate.cost_units > budget_units:
            continue
        current = set(candidate.match_indices)
        if max_overlap >= 0 and any(len(current & prev) > max_overlap for prev in selected_sets):
            continue
        selected.append(candidate)
        selected_sets.append(current)
        spent += candidate.cost_units
    return selected


def apply_stake_mode(
    selected: list[BundleCandidate],
    *,
    budget_units: float,
    stake_mode: str,
) -> tuple[list[StakedBundle], float, str]:
    if not selected:
        return [], 0.0, "no_selected_bundle"

    staked = [StakedBundle(candidate=item, stake_multiplier=1) for item in selected]
    base_cost = sum(staked_bundle_cost_units(item) for item in staked)
    if stake_mode == "unit_once":
        return staked, base_cost, "unit_once"
    if stake_mode != "scale_to_budget":
        raise ValueError("stake_mode must be scale_to_budget or unit_once")
    if base_cost <= 0 or base_cost >= budget_units:
        return staked, base_cost, "scale_to_budget_no_room"

    spent = base_cost
    multipliers = [1 for _item in selected]
    scores = [
        max(item.score, item.expected_profit_units, item.expected_roi * item.cost_units, 0.000001)
        for item in selected
    ]
    while True:
        affordable = [
            idx
            for idx, item in enumerate(selected)
            if item.cost_units > 0 and spent + item.cost_units <= budget_units
        ]
        if not affordable:
            break
        idx = max(
            affordable,
            key=lambda pos: (
                scores[pos] / multipliers[pos],
                selected[pos].expected_roi,
                -selected[pos].cost_units,
            ),
        )
        multipliers[idx] += 1
        spent += selected[idx].cost_units

    return (
        [StakedBundle(candidate=item, stake_multiplier=multipliers[idx]) for idx, item in enumerate(selected)],
        spent,
        "scale_to_budget",
    )


def recommend_n_for_segment(metrics: list[LegMetrics], *, min_n: int, max_n: int) -> tuple[int | None, dict[str, Any]]:
    expected_rate = sum(item.hit_prob for item in metrics) / len(metrics) if metrics else 0.0
    recommendation = recommend_segment_n(len(metrics), expected_rate, budget_coverage="ok", min_n=min_n, max_n=max_n)
    return recommendation.recommended_n, {
        "expected_coverage_hit_rate": expected_rate,
        "initial_recommended_n": recommendation.recommended_n or "",
        "n_action": recommendation.action,
        "n_reasons": ";".join(recommendation.reasons),
    }


def settle_segment(
    segment: rolling.Segment,
    *,
    arm: str,
    segment_budget_yuan: float,
    stake_yuan_per_ticket: float,
    sample_attempts: int,
    sample_seed: int,
    min_n: int,
    max_n: int,
    max_overlap: int | None,
    positive_ev_only: bool,
    stake_mode: str = "scale_to_budget",
    planning_scope: str = "next_segment",
    decision_time: datetime | None = None,
) -> tuple[dict[str, Any], list[StakedBundle]]:
    metrics = [item for leg in segment.legs if (item := leg_metrics(leg, arm)) is not None]
    budget_units = segment_budget_yuan / stake_yuan_per_ticket if stake_yuan_per_ticket > 0 else 0.0
    n_value, n_info = recommend_n_for_segment(metrics, min_n=min_n, max_n=max_n)
    reasons = [n_info["n_reasons"]]
    candidates: list[BundleCandidate] = []
    selected: list[BundleCandidate] = []
    dropped_for_budget = 0
    if n_value:
        current_n = n_value
        while current_n >= min_n:
            candidates = generate_candidates(
                metrics=metrics,
                segment_idx=segment.segment_idx,
                arm=arm,
                n_value=current_n,
                budget_units=budget_units,
                sample_attempts=sample_attempts,
                seed=stable_seed(sample_seed, segment.segment_idx, arm, current_n),
            )
            if any(candidate.cost_units <= budget_units for candidate in candidates):
                break
            current_n -= 1
            dropped_for_budget += 1
        if current_n >= min_n:
            n_value = current_n
            overlap_limit = max_overlap if max_overlap is not None else max(0, n_value - 2)
            selected = select_bundles(
                candidates,
                budget_units=budget_units,
                max_overlap=overlap_limit,
                positive_ev_only=positive_ev_only,
            )
        else:
            n_value = None
    if dropped_for_budget:
        reasons.append(f"bundle_cost_budget_drop_{dropped_for_budget}")
    if not selected:
        reasons.append("no_positive_ev_bundle_selected" if positive_ev_only else "no_bundle_selected")
    staked_selected, selected_cost_units, stake_mode_reason = apply_stake_mode(
        selected,
        budget_units=budget_units,
        stake_mode=stake_mode,
    )
    reasons.append(stake_mode_reason)

    width_counts = Counter(item.width for item in metrics)
    actual_hits = sum(1 for item in metrics if item.leg.actual_code in item.codes)
    base_cost_units = sum(item.cost_units for item in selected)
    payout_units = sum(staked_bundle_payout_units(item) for item in staked_selected)
    profit_units = payout_units - selected_cost_units
    expected_profit_units = sum(staked_bundle_expected_profit_units(item) for item in staked_selected)
    drift_accepted, drift_level, drift_reason = planning_scope_risk(planning_scope)
    row = {
        "segment_idx": segment.segment_idx,
        "arm": arm,
        "planning_scope": planning_scope,
        "decision_time": format_optional_dt(decision_time),
        "segment_start": segment.start.strftime("%Y-%m-%d %H:%M"),
        "segment_end": segment.end.strftime("%Y-%m-%d %H:%M"),
        "hours_from_decision_start": hours_between(decision_time, segment.start),
        "hours_from_decision_end": hours_between(decision_time, segment.end),
        "sp_drift_risk_accepted": drift_accepted,
        "sp_drift_risk_level": drift_level,
        "sp_drift_risk_reason": drift_reason,
        "window_hours": round(segment.window_hours, 2),
        "eligible_matches": len(metrics),
        "expected_coverage_hit_rate": round(n_info["expected_coverage_hit_rate"], 6),
        "actual_coverage_hits": actual_hits,
        "actual_coverage_hit_rate": round(actual_hits / len(metrics), 6) if metrics else "",
        "recommended_n": n_value or "",
        "initial_recommended_n": n_info["initial_recommended_n"],
        "stake_mode": stake_mode,
        "selected_bundles": len(selected),
        "candidate_bundles": len(candidates),
        "base_cost_units": round(base_cost_units, 6),
        "base_cost_yuan": round(base_cost_units * stake_yuan_per_ticket, 6),
        "stake_multiplier_units": sum(item.stake_multiplier for item in staked_selected),
        "selected_cost_units": round(selected_cost_units, 6),
        "selected_cost_yuan": round(selected_cost_units * stake_yuan_per_ticket, 6),
        "segment_budget_yuan": round(segment_budget_yuan, 6),
        "expected_profit_units": round(expected_profit_units, 6),
        "expected_profit_yuan": round(expected_profit_units * stake_yuan_per_ticket, 6),
        "payout_units": round(payout_units, 6),
        "payout_yuan": round(payout_units * stake_yuan_per_ticket, 6),
        "profit_units": round(profit_units, 6),
        "profit_yuan": round(profit_units * stake_yuan_per_ticket, 6),
        "roi": round(profit_units / selected_cost_units, 6) if selected_cost_units else "",
        "dead_segment": int(bool(selected) and payout_units <= 0),
        "width_counts": dict(sorted(width_counts.items())),
        "reasons": ";".join(reason for reason in reasons if reason),
        "match_indices": ",".join(str(item.leg.match_idx) for item in metrics),
    }
    return row, staked_selected


def summarize(segment_rows: list[dict[str, Any]], bundle_rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_cost_units = sum(rolling.fnum(row.get("base_cost_units")) for row in segment_rows)
    selected_cost_units = sum(rolling.fnum(row.get("selected_cost_units")) for row in segment_rows)
    payout_units = sum(rolling.fnum(row.get("payout_units")) for row in segment_rows)
    profit_units = payout_units - selected_cost_units
    stake_multiplier_units = sum(rolling.fnum(row.get("stake_multiplier_units")) for row in segment_rows)
    stake = rolling.fnum(segment_rows[0].get("selected_cost_yuan")) / max(
        rolling.fnum(segment_rows[0].get("selected_cost_units")),
        1.0,
    ) if segment_rows else 2.0
    return {
        "segments": len(segment_rows),
        "selected_segments": sum(1 for row in segment_rows if rolling.fnum(row.get("selected_bundles")) > 0),
        "dead_segments": sum(1 for row in segment_rows if rolling.fnum(row.get("dead_segment")) > 0),
        "selected_bundles": len(bundle_rows),
        "stake_multiplier_units": round(stake_multiplier_units, 6),
        "base_cost_units": round(base_cost_units, 6),
        "base_cost_yuan": round(base_cost_units * stake, 6),
        "selected_cost_units": round(selected_cost_units, 6),
        "selected_cost_yuan": round(selected_cost_units * stake, 6),
        "payout_units": round(payout_units, 6),
        "payout_yuan": round(payout_units * stake, 6),
        "profit_units": round(profit_units, 6),
        "profit_yuan": round(profit_units * stake, 6),
        "roi": round(profit_units / selected_cost_units, 6) if selected_cost_units else "",
    }


def candidate_to_row(staked: StakedBundle, *, stake_yuan_per_ticket: float, sample_seed: int | None = None) -> dict[str, Any]:
    candidate = staked.candidate
    prefix = {"sample_seed": sample_seed} if sample_seed is not None else {}
    return {
        **prefix,
        "segment_idx": candidate.segment_idx,
        "bundle_idx": candidate.bundle_idx,
        "arm": candidate.arm,
        "n_value": candidate.n_value,
        "match_indices": ",".join(str(value) for value in candidate.match_indices),
        "leg_codes": "|".join(candidate.leg_codes),
        "widths": ",".join(str(value) for value in candidate.widths),
        "stake_multiplier": staked.stake_multiplier,
        "cost_units": round(candidate.cost_units, 6),
        "cost_yuan": round(candidate.cost_units * stake_yuan_per_ticket, 6),
        "scaled_cost_units": round(candidate.cost_units * staked.stake_multiplier, 6),
        "scaled_cost_yuan": round(candidate.cost_units * staked.stake_multiplier * stake_yuan_per_ticket, 6),
        "expected_payout_units": round(candidate.expected_payout_units, 6),
        "expected_profit_units": round(candidate.expected_profit_units, 6),
        "scaled_expected_profit_units": round(candidate.expected_profit_units * staked.stake_multiplier, 6),
        "expected_roi": round(candidate.expected_roi, 6),
        "hit_prob": round(candidate.hit_prob, 6),
        "realized_hit": int(candidate.realized_hit),
        "payout_units": round(candidate.payout_units, 6),
        "payout_yuan": round(candidate.payout_units * stake_yuan_per_ticket, 6),
        "scaled_payout_units": round(candidate.payout_units * staked.stake_multiplier, 6),
        "scaled_payout_yuan": round(candidate.payout_units * staked.stake_multiplier * stake_yuan_per_ticket, 6),
        "profit_units": round(candidate.profit_units, 6),
        "profit_yuan": round(candidate.profit_units * stake_yuan_per_ticket, 6),
        "scaled_profit_units": round(candidate.profit_units * staked.stake_multiplier, 6),
        "scaled_profit_yuan": round(candidate.profit_units * staked.stake_multiplier * stake_yuan_per_ticket, 6),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(title for title, _key in columns) + " |"]
    lines.append("| " + " | ".join("---" for _title, _key in columns) + " |")
    for row in rows:
        values = []
        for _title, key in columns:
            values.append(str(row.get(key, "")).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_report(
    *,
    issue: str,
    label: str,
    betting_strategy_version: str,
    summary: dict[str, Any],
    seed_aggregate: dict[str, Any],
    seed_summary_rows: list[dict[str, Any]],
    segment_seed_summary_rows: list[dict[str, Any]],
    segment_rows: list[dict[str, Any]],
    bundle_rows: list[dict[str, Any]],
    segment_csv: Path,
    bundle_csv: Path,
    seed_summary_csv: Path,
    segment_seed_summary_csv: Path,
    summary_json: Path,
    args: argparse.Namespace,
) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    top_bundles = sorted(bundle_rows, key=lambda row: rolling.fnum(row.get("scaled_profit_units")), reverse=True)[:12]
    seed_count = len(seed_summary_rows)
    seed_label = (
        f"{seed_count} seeds ({seed_summary_rows[0]['sample_seed']}..{seed_summary_rows[-1]['sample_seed']})"
        if seed_count > 1
        else str(seed_summary_rows[0]["sample_seed"])
    )
    stability_rows = [
        {"metric": key, **values}
        for key, values in seed_aggregate.get("metrics", {}).items()
        if key in {"selected_cost_yuan", "payout_yuan", "profit_yuan", "roi", "dead_segments"}
    ]
    return f"""# Segment Betting Plan {issue} {label} {betting_strategy_version}

Generated: {generated}

## Strategy {betting_strategy_version}

- Use rolling kickoff segments, not natural days: start with `{args.window_hours}`h, extend through `{args.extend_hours}`h until at least `{args.min_matches}` eligible matches, cap a segment at `{args.max_matches}` matches.
- Planning scope is `{args.planning_scope}`. `next_segment` buys only the next dynamic segment; `remaining_issue` buys all remaining issue segments and marks SP drift risk as accepted.
- Stake mode is `{args.stake_mode}`. `scale_to_budget` repeats selected bundles by score until the segment budget is nearly exhausted; `unit_once` buys each selected bundle once.
- Eligible matches are rows with executable selected codes for `--arm {args.arm}`. Rows with no-buy/stop are excluded from bundle selection.
- N starts from half of eligible match count, capped at `{args.max_n}`, then drops by expected coverage hit rate using `select_rolling_segment_n.py`.
- Each selected bundle is one small-combo N串1 ticket group: cost units are `product(width_i)`, yuan cost is `{args.stake_yuan_per_ticket}` times that. A hit pays one expanded ticket: `product(winning_sp_i)`.
- Candidate bundles are sampled by leg hit probability and unit value `sum(p*sp)/width`; the selector buys positive-EV bundles under `{args.segment_budget_yuan}` yuan per segment with overlap guard `{args.max_overlap if args.max_overlap is not None else 'N-2'}`.
- Sampling stability is measured with `{seed_label}`. Multi-seed reports use the mean as the main estimate and min/p10/median/p90/max as the variation interval.
- This is a settled replay for estimating behavior, not a promotion gate. If the structured artifact has fewer rows than the settled issue, missing rows are not backfilled after the fact.

## Summary

| metric | value |
| --- | --- |
| segments | {summary["segments"]} |
| selected segments | {summary["selected_segments"]} |
| selected bundles | {summary["selected_bundles"]} |
| stake multiplier units | {summary["stake_multiplier_units"]} |
| base cost yuan | {summary["base_cost_yuan"]} |
| cost yuan | {summary["selected_cost_yuan"]} |
| payout yuan | {summary["payout_yuan"]} |
| profit yuan | {summary["profit_yuan"]} |
| ROI | {summary["roi"]} |

## Seed Stability

{md_table(stability_rows, [
        ("metric", "metric"),
        ("min", "min"),
        ("p10", "p10"),
        ("mean", "mean"),
        ("median", "median"),
        ("p90", "p90"),
        ("max", "max"),
    ])}

## Tunable Parameters

{md_table(betting_strategy_parameter_schema(), [
        ("key", "key"),
        ("level", "ui_level"),
        ("type", "type"),
        ("default", "default"),
        ("effect", "effect"),
    ])}

## Segment Stability

{md_table(segment_seed_summary_rows, [
        ("seg", "segment_idx"),
        ("L", "eligible_matches"),
        ("p_exp", "expected_coverage_hit_rate"),
        ("hits", "actual_coverage_hits"),
        ("N values", "recommended_n_values"),
        ("N stable", "recommended_n_stable"),
        ("bundles mean", "selected_bundles_mean"),
        ("base cost", "base_cost_yuan_mean"),
        ("cost mean", "cost_yuan_mean"),
        ("profit mean", "profit_yuan_mean"),
        ("profit min", "profit_yuan_min"),
        ("profit max", "profit_yuan_max"),
        ("dead rate", "dead_segment_rate"),
    ])}

## Segments

{md_table(segment_rows, [
        ("seed", "sample_seed"),
        ("seg", "segment_idx"),
        ("scope", "planning_scope"),
        ("start", "segment_start"),
        ("end", "segment_end"),
        ("drift", "sp_drift_risk_level"),
        ("L", "eligible_matches"),
        ("p_exp", "expected_coverage_hit_rate"),
        ("hits", "actual_coverage_hits"),
        ("hit%", "actual_coverage_hit_rate"),
        ("N", "recommended_n"),
        ("stake", "stake_mode"),
        ("bundles", "selected_bundles"),
        ("base", "base_cost_yuan"),
        ("cost", "selected_cost_yuan"),
        ("payout", "payout_yuan"),
        ("profit", "profit_yuan"),
        ("ROI", "roi"),
        ("reasons", "reasons"),
    ])}

## Top Realized Bundles

{md_table(top_bundles, [
        ("seg", "segment_idx"),
        ("bundle", "bundle_idx"),
        ("N", "n_value"),
        ("matches", "match_indices"),
        ("codes", "leg_codes"),
        ("x", "stake_multiplier"),
        ("cost", "cost_yuan"),
        ("scaled cost", "scaled_cost_yuan"),
        ("EV roi", "expected_roi"),
        ("hit p", "hit_prob"),
        ("hit", "realized_hit"),
        ("payout", "scaled_payout_yuan"),
        ("profit", "scaled_profit_yuan"),
    ])}

Artifacts:

- Segment CSV: `{segment_csv}`
- Bundle CSV: `{bundle_csv}`
- Seed summary CSV: `{seed_summary_csv}`
- Segment seed summary CSV: `{segment_seed_summary_csv}`
- Summary JSON: `{summary_json}`
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--structured-csv", type=Path, required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--betting-strategy-version", default=BETTING_STRATEGY_VERSION)
    parser.add_argument("--arm", choices=("active", "shadow"), default="shadow")
    parser.add_argument("--planning-scope", choices=("next_segment", "remaining_issue"), default="next_segment")
    parser.add_argument("--stake-mode", choices=("scale_to_budget", "unit_once"), default="scale_to_budget")
    parser.add_argument("--decision-time", default="", help="Local issue datetime; filters out matches with kickoff <= decision time.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--window-hours", type=float, default=12.0)
    parser.add_argument("--extend-hours", default="18,24,36")
    parser.add_argument("--min-matches", type=int, default=6)
    parser.add_argument("--max-matches", type=int, default=24)
    parser.add_argument("--segment-budget-yuan", type=float, default=1000.0)
    parser.add_argument("--stake-yuan-per-ticket", type=float, default=2.0)
    parser.add_argument("--sample-attempts", type=int, default=12000)
    parser.add_argument("--sample-seed", type=int, default=20260707)
    parser.add_argument("--seed-count", type=int, default=1)
    parser.add_argument("--sample-seeds", default="", help="Comma-separated seed list. Overrides --sample-seed/--seed-count.")
    parser.add_argument("--min-n", type=int, default=3)
    parser.add_argument("--max-n", type=int, default=8)
    parser.add_argument("--max-overlap", type=int, default=None)
    parser.add_argument("--allow-negative-ev", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    label = args.label or Path(args.structured_csv).parent.name
    legs = rolling.load_legs(args.structured_csv, args.db, issue=args.issue)
    decision_time = parse_optional_decision_time(args.decision_time)
    eligible_before_decision_filter = [leg for leg in legs if selected_codes_for(leg, args.arm)]
    eligible_legs = [
        leg
        for leg in eligible_before_decision_filter
        if decision_time is None or leg.kickoff > decision_time
    ]
    if not eligible_before_decision_filter:
        raise SystemExit(f"No eligible legs loaded for issue {args.issue}")
    if not eligible_legs:
        raise SystemExit(f"No future eligible legs loaded for issue {args.issue}")
    all_segments = rolling.build_segments(
        eligible_legs,
        base_window_hours=args.window_hours,
        extend_hours=rolling.parse_extend_hours(args.extend_hours),
        min_matches=args.min_matches,
        max_matches=args.max_matches,
    )
    segments = all_segments[:1] if args.planning_scope == "next_segment" else all_segments

    seeds = sample_seeds_from_args(args)
    segment_rows: list[dict[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    seed_summary_rows: list[dict[str, Any]] = []
    for sample_seed in seeds:
        seed_segment_rows: list[dict[str, Any]] = []
        selected_candidates: list[StakedBundle] = []
        for segment in segments:
            row, selected = settle_segment(
                segment,
                arm=args.arm,
                segment_budget_yuan=args.segment_budget_yuan,
                stake_yuan_per_ticket=args.stake_yuan_per_ticket,
                sample_attempts=args.sample_attempts,
                sample_seed=sample_seed,
                min_n=args.min_n,
                max_n=args.max_n,
                max_overlap=args.max_overlap,
                positive_ev_only=not args.allow_negative_ev,
                stake_mode=args.stake_mode,
                planning_scope=args.planning_scope,
                decision_time=decision_time,
            )
            row = {"sample_seed": sample_seed, **row}
            seed_segment_rows.append(row)
            selected_candidates.extend(selected)
        seed_bundle_rows = [
            candidate_to_row(candidate, stake_yuan_per_ticket=args.stake_yuan_per_ticket, sample_seed=sample_seed)
            for candidate in selected_candidates
        ]
        seed_summary = {"sample_seed": sample_seed, **summarize(seed_segment_rows, seed_bundle_rows)}
        seed_summary_rows.append(seed_summary)
        segment_rows.extend(seed_segment_rows)
        bundle_rows.extend(seed_bundle_rows)

    seed_aggregate = aggregate_seed_summaries(seed_summary_rows)
    segment_seed_summary_rows = aggregate_segment_seed_rows(segment_rows)
    summary = seed_aggregate["mean_summary"]
    version = args.betting_strategy_version
    slug_label = slugify(label)
    version_slug = slugify(version)
    if len(seeds) == 1:
        seed_slug = f"seed{seeds[0]}"
    else:
        seed_slug = f"seeds{len(seeds)}_{seeds[0]}-{seeds[-1]}"
    scope_slug = slugify(args.planning_scope)
    stake_slug = slugify(args.stake_mode)
    slug = f"{args.issue}_{slug_label}_{version_slug}_{scope_slug}_{stake_slug}_b{int(args.segment_budget_yuan)}_{seed_slug}"
    out_dir = args.output_dir / slug
    segment_csv = out_dir / "segment_betting_plan_segments.csv"
    bundle_csv = out_dir / "segment_betting_plan_bundles.csv"
    seed_summary_csv = out_dir / "segment_betting_plan_seed_summary.csv"
    segment_seed_summary_csv = out_dir / "segment_betting_plan_segment_seed_summary.csv"
    summary_json = out_dir / "segment_betting_plan_summary.json"
    write_csv(segment_csv, segment_rows)
    write_csv(bundle_csv, bundle_rows)
    write_csv(seed_summary_csv, seed_summary_rows)
    write_csv(segment_seed_summary_csv, segment_seed_summary_rows)
    payload = {
        "issue": args.issue,
        "label": label,
        "strategy_family": BETTING_STRATEGY_FAMILY,
        "betting_strategy_version": version,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "arm": args.arm,
        "structured_csv": str(args.structured_csv),
        "source_rows": len(legs),
        "eligible_rows_before_decision_filter": len(eligible_before_decision_filter),
        "eligible_rows": len(eligible_legs),
        "available_segments": len(all_segments),
        "segments": len(segments),
        "planning_scope": args.planning_scope,
        "decision_time": format_optional_dt(decision_time),
        "sp_drift_risk": {
            "accepted": bool(planning_scope_risk(args.planning_scope)[0]),
            "level": planning_scope_risk(args.planning_scope)[1],
            "reason": planning_scope_risk(args.planning_scope)[2],
        },
        "summary": summary,
        "seed_aggregate": seed_aggregate,
        "parameter_schema": betting_strategy_parameter_schema(),
        "settings": {
            "window_hours": args.window_hours,
            "extend_hours": args.extend_hours,
            "planning_scope": args.planning_scope,
            "stake_mode": args.stake_mode,
            "decision_time": format_optional_dt(decision_time),
            "min_matches": args.min_matches,
            "max_matches": args.max_matches,
            "segment_budget_yuan": args.segment_budget_yuan,
            "stake_yuan_per_ticket": args.stake_yuan_per_ticket,
            "betting_strategy_version": version,
            "sample_attempts": args.sample_attempts,
            "sample_seed": args.sample_seed,
            "seed_count": args.seed_count,
            "sample_seeds": seeds,
            "min_n": args.min_n,
            "max_n": args.max_n,
            "max_overlap": args.max_overlap,
            "positive_ev_only": not args.allow_negative_ev,
        },
        "segment_csv": str(segment_csv),
        "bundle_csv": str(bundle_csv),
        "seed_summary_csv": str(seed_summary_csv),
        "segment_seed_summary_csv": str(segment_seed_summary_csv),
    }
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = args.report_dir / f"segment_betting_plan_{slug}_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(
            issue=args.issue,
            label=label,
            betting_strategy_version=version,
            summary=summary,
            seed_aggregate=seed_aggregate,
            seed_summary_rows=seed_summary_rows,
            segment_seed_summary_rows=segment_seed_summary_rows,
            segment_rows=segment_rows,
            bundle_rows=bundle_rows,
            segment_csv=segment_csv,
            bundle_csv=bundle_csv,
            seed_summary_csv=seed_summary_csv,
            segment_seed_summary_csv=segment_seed_summary_csv,
            summary_json=summary_json,
            args=args,
        ),
        encoding="utf-8",
    )
    payload["summary_json"] = str(summary_json)
    payload["report_path"] = str(report_path)
    return payload


def main() -> None:
    args = parse_args()
    payload = run(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {payload['segment_csv']}")
        print(f"Wrote {payload['bundle_csv']}")
        print(f"Wrote {payload['seed_summary_csv']}")
        print(f"Wrote {payload['segment_seed_summary_csv']}")
        print(f"Wrote {payload['summary_json']}")
        print(f"Wrote {payload['report_path']}")


if __name__ == "__main__":
    main()
