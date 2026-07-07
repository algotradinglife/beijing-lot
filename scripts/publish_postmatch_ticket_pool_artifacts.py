#!/usr/bin/env python3
"""Publish post-settlement ticket-pool replay artifacts for one issue/variant."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import replay_rolling_segment_n_tickets as rolling  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results/postmatch_ticket_pool_artifacts"
SCHEMA_VERSION = "postmatch_ticket_pool_artifact_v1"
ARTIFACT_VERSION = "1.0.0"
DEFAULT_REVIEW_VERSION = "postmatch_ticket_pool_replay_v1"
OUTCOME_CODES = rolling.OUTCOME_CODES
OUTCOME_LABELS = {"3": "胜", "1": "平", "0": "负"}


@dataclass(frozen=True)
class TicketOutcome:
    segment_idx: int
    n: int
    ticket: tuple[tuple[int, str], ...]
    payout_units: float
    miss_count: int

    @property
    def hit(self) -> bool:
        return self.miss_count == 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace(",", ";").split(";")
    return [str(item).strip() for item in raw if str(item).strip()]


def load_structured_rows(path: Path, issue: str) -> tuple[dict[int, dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = {
            int(row["match_idx"]): dict(row)
            for row in reader
            if str(row.get("issue") or "") == issue and str(row.get("match_idx") or "").isdigit()
        }
        return rows, list(reader.fieldnames or [])


def infer_variant_id(rows: dict[int, dict[str, str]], arm: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    if arm == "active":
        return "active_v3"
    first = next(iter(rows.values()), {})
    return str(first.get("shadow_arm") or "shadow_unknown")


def infer_variant_version(rows: dict[int, dict[str, str]], arm: str) -> str:
    first = next(iter(rows.values()), {})
    if arm == "active":
        return str(first.get("active_version") or "")
    return str(first.get("shadow_version") or "")


def codes_for(leg: rolling.LegRow, arm: str) -> tuple[str, ...]:
    return leg.active_codes if arm == "active" else leg.shadow_codes


def selection_role(codes: tuple[str, ...]) -> str:
    if not codes:
        return "stop"
    if len(codes) == 1:
        return "single"
    if len(codes) == 2:
        return "primary_protect"
    return "full_cover"


def actual_role(codes: tuple[str, ...], actual_code: str | None) -> str:
    if not codes:
        return "stopped"
    if actual_code is None:
        return "unsettled"
    if actual_code == codes[0]:
        return "primary_hit"
    if actual_code in codes[1:]:
        return "protect_hit"
    return "miss"


def ticket_payout(ticket: tuple[tuple[int, str], ...], legs_by_idx: dict[int, rolling.LegRow]) -> tuple[float, int]:
    payout = 1.0
    misses = 0
    for match_idx, code in ticket:
        leg = legs_by_idx[match_idx]
        if leg.actual_code != code or leg.winning_sp is None:
            misses += 1
        payout *= float(leg.winning_sp or 0.0)
    return (payout if misses == 0 else 0.0), misses


def enumerate_exact_tickets(legs: list[rolling.LegRow], arm: str, n_value: int) -> list[tuple[tuple[int, str], ...]]:
    out: list[tuple[tuple[int, str], ...]] = []
    for combo in itertools.combinations(legs, n_value):
        code_options = [codes_for(leg, arm) for leg in combo]
        if any(not codes for codes in code_options):
            continue
        for codes in itertools.product(*code_options):
            out.append(tuple(sorted(((leg.match_idx, code) for leg, code in zip(combo, codes)), key=lambda item: item[0])))
    return out


def sample_ticket_outcomes(
    segment: rolling.Segment,
    arm: str,
    n_value: int,
    *,
    budget_ticket_units: int,
    sample_seed: int,
    variant_id: str,
    budget_fill_mode: str,
) -> list[TicketOutcome]:
    legs = [leg for leg in segment.legs if codes_for(leg, arm)]
    if n_value <= 0 or len(legs) < n_value or budget_ticket_units <= 0:
        return []
    full_cost = int(round(rolling.expanded_cost(legs, arm, n_value)))
    selected_count = budget_ticket_units if budget_fill_mode == "scale_to_budget" and full_cost > 0 else min(full_cost, budget_ticket_units)
    if selected_count <= 0:
        return []

    legs_by_idx = {leg.match_idx: leg for leg in legs}
    tickets: list[tuple[tuple[int, str], ...]]
    if full_cost <= budget_ticket_units:
        enumerated = enumerate_exact_tickets(legs, arm, n_value)
        if budget_fill_mode == "scale_to_budget" and enumerated:
            repeats, remainder = divmod(budget_ticket_units, len(enumerated))
            tickets = list(enumerated) * repeats
            if remainder:
                rng = rolling.random.Random(rolling.stable_seed(sample_seed, variant_id, segment.segment_idx, n_value, "budget_remainder"))
                shuffled = list(enumerated)
                rng.shuffle(shuffled)
                tickets.extend(shuffled[:remainder])
        else:
            tickets = enumerated
    else:
        rng = rolling.random.Random(rolling.stable_seed(sample_seed, variant_id, segment.segment_idx, n_value, budget_ticket_units))
        seen: set[tuple[tuple[int, str], ...]] = set()
        max_attempts = max(selected_count * 30, 1000)
        attempts = 0
        while len(seen) < selected_count and attempts < max_attempts:
            attempts += 1
            ticket, _payout = rolling.sample_exact_ticket(legs, arm, n_value, rng)
            if len(ticket) == n_value:
                seen.add(ticket)
        tickets = sorted(seen)

    out: list[TicketOutcome] = []
    for ticket in tickets[:selected_count]:
        payout, misses = ticket_payout(ticket, legs_by_idx)
        out.append(TicketOutcome(segment.segment_idx, n_value, ticket, payout, misses))
    return out


def recommended_n_for_segment(
    segment: rolling.Segment,
    arm: str,
    *,
    budget_ticket_units: int,
    budget_coverage: str,
    max_expanded_cost_multiple: float,
    min_n: int,
    max_n: int,
) -> tuple[int | None, dict[str, Any]]:
    legs = [leg for leg in segment.legs if codes_for(leg, arm)]
    if not legs:
        return None, {"action": "skip_empty_segment", "reasons": ["empty_segment"]}
    expected_rate = sum(rolling.selection_probability(leg, arm) for leg in legs) / len(legs)
    if budget_coverage == "auto":
        initial = rolling.recommend_segment_n(len(legs), expected_rate, budget_coverage="ok", min_n=min_n, max_n=max_n)
        initial_n = initial.recommended_n or min_n
        budget_state = rolling.auto_budget_coverage(rolling.expanded_cost(legs, arm, initial_n), float(budget_ticket_units))
    else:
        budget_state = budget_coverage
    recommendation = rolling.recommend_segment_n(len(legs), expected_rate, budget_coverage=budget_state, min_n=min_n, max_n=max_n)
    n_value = recommendation.recommended_n
    reasons = list(recommendation.reasons)
    action = recommendation.action
    guardrail_target = float(budget_ticket_units) * max_expanded_cost_multiple if max_expanded_cost_multiple > 0 else 0.0
    guardrail_drops = 0
    if n_value and guardrail_target > 0:
        while n_value > min_n and rolling.expanded_cost(legs, arm, n_value) > guardrail_target:
            n_value -= 1
            guardrail_drops += 1
        if guardrail_drops:
            reasons.append(f"expanded_cost_guardrail_drop_{guardrail_drops}")
            action = f"cost_guarded_{action}"
    return n_value, {
        "segment_idx": segment.segment_idx,
        "segment_start": segment.start.strftime("%Y-%m-%d %H:%M"),
        "segment_end": segment.end.strftime("%Y-%m-%d %H:%M"),
        "window_hours": round(segment.window_hours, 2),
        "l_count": len(legs),
        "expected_coverage_hit_rate": round(expected_rate, 6),
        "budget_coverage": budget_state,
        "recommended_n": n_value or "",
        "action": action,
        "reasons": reasons,
        "expanded_cost_guardrail_drops": guardrail_drops,
        "match_indices": [leg.match_idx for leg in legs],
    }


def summarize_ticket_outcomes(
    outcomes: list[TicketOutcome],
    *,
    stake_yuan_per_ticket: float,
) -> dict[str, Any]:
    ticket_count = len(outcomes)
    payout_units = sum(outcome.payout_units for outcome in outcomes)
    stake_yuan = ticket_count * stake_yuan_per_ticket
    payout_yuan = payout_units * stake_yuan_per_ticket
    profit_yuan = payout_yuan - stake_yuan
    hit_count = sum(1 for outcome in outcomes if outcome.hit)
    return {
        "ticket_count": ticket_count,
        "hit_ticket_count": hit_count,
        "stake_yuan": round(stake_yuan, 6),
        "payout_yuan": round(payout_yuan, 6),
        "profit_yuan": round(profit_yuan, 6),
        "roi": round(profit_yuan / stake_yuan, 6) if stake_yuan else None,
        "hit_ticket_rate": round(hit_count / ticket_count, 6) if ticket_count else None,
        "miss_by_1": sum(1 for outcome in outcomes if outcome.miss_count == 1),
        "miss_by_2": sum(1 for outcome in outcomes if outcome.miss_count == 2),
        "miss_by_3_or_more": sum(1 for outcome in outcomes if outcome.miss_count >= 3),
    }


def main_drag_legs(outcomes: list[TicketOutcome], legs_by_idx: dict[int, rolling.LegRow], limit: int = 8) -> list[dict[str, Any]]:
    counts: Counter[int] = Counter()
    for outcome in outcomes:
        if outcome.hit:
            continue
        for match_idx, code in outcome.ticket:
            leg = legs_by_idx[match_idx]
            if leg.actual_code != code:
                counts[match_idx] += 1
    rows: list[dict[str, Any]] = []
    for match_idx, count in counts.most_common(limit):
        leg = legs_by_idx[match_idx]
        rows.append({
            "match_idx": match_idx,
            "match_id": leg.match_id,
            "home": leg.home,
            "away": leg.away,
            "actual_code": leg.actual_code or "",
            "winning_sp": leg.winning_sp,
            "miss_ticket_count": count,
        })
    return rows


def build_n_replay(
    segments: list[rolling.Segment],
    arm: str,
    *,
    variant_id: str,
    n_values: list[int],
    budget_ticket_units: int,
    stake_yuan_per_ticket: float,
    sample_seed: int,
    budget_fill_mode: str,
) -> list[dict[str, Any]]:
    legs_by_idx = {leg.match_idx: leg for segment in segments for leg in segment.legs}
    rows: list[dict[str, Any]] = []
    for n_value in n_values:
        outcomes: list[TicketOutcome] = []
        segment_rows: list[dict[str, Any]] = []
        for segment in segments:
            segment_outcomes = sample_ticket_outcomes(
                segment,
                arm,
                n_value,
                budget_ticket_units=budget_ticket_units,
                sample_seed=sample_seed,
                variant_id=f"{variant_id}:fixed",
                budget_fill_mode=budget_fill_mode,
            )
            outcomes.extend(segment_outcomes)
            summary = summarize_ticket_outcomes(segment_outcomes, stake_yuan_per_ticket=stake_yuan_per_ticket)
            segment_rows.append({
                "segment_idx": segment.segment_idx,
                "n": n_value,
                "l_count": len(segment.legs),
                "ticket_count": summary["ticket_count"],
                "hit_ticket_count": summary["hit_ticket_count"],
                "stake_yuan": summary["stake_yuan"],
                "payout_yuan": summary["payout_yuan"],
                "profit_yuan": summary["profit_yuan"],
                "roi": summary["roi"],
                "match_indices": [leg.match_idx for leg in segment.legs],
            })
        aggregate = summarize_ticket_outcomes(outcomes, stake_yuan_per_ticket=stake_yuan_per_ticket)
        aggregate.update({
            "n": n_value,
            "main_drag_legs": main_drag_legs(outcomes, legs_by_idx),
            "segments": segment_rows,
        })
        rows.append(aggregate)
    return rows


def build_dynamic_replay(
    segments: list[rolling.Segment],
    arm: str,
    *,
    variant_id: str,
    budget_ticket_units: int,
    stake_yuan_per_ticket: float,
    budget_coverage: str,
    max_expanded_cost_multiple: float,
    min_n: int,
    max_n: int,
    sample_seed: int,
    budget_fill_mode: str,
) -> tuple[dict[str, Any], list[TicketOutcome], list[dict[str, Any]]]:
    all_outcomes: list[TicketOutcome] = []
    segment_rows: list[dict[str, Any]] = []
    for segment in segments:
        n_value, info = recommended_n_for_segment(
            segment,
            arm,
            budget_ticket_units=budget_ticket_units,
            budget_coverage=budget_coverage,
            max_expanded_cost_multiple=max_expanded_cost_multiple,
            min_n=min_n,
            max_n=max_n,
        )
        outcomes = (
            sample_ticket_outcomes(
                segment,
                arm,
                n_value,
                budget_ticket_units=budget_ticket_units,
                sample_seed=sample_seed,
                variant_id=f"{variant_id}:dynamic",
                budget_fill_mode=budget_fill_mode,
            )
            if n_value
            else []
        )
        all_outcomes.extend(outcomes)
        segment_summary = summarize_ticket_outcomes(outcomes, stake_yuan_per_ticket=stake_yuan_per_ticket)
        info.update(segment_summary)
        segment_rows.append(info)
    summary = summarize_ticket_outcomes(all_outcomes, stake_yuan_per_ticket=stake_yuan_per_ticket)
    profits = [safe_float(row.get("profit_yuan")) for row in segment_rows]
    summary["segment_count"] = len(segment_rows)
    summary["max_segment_loss_yuan"] = round(abs(min([0.0, *profits])), 6)
    summary["segments"] = segment_rows
    return summary, all_outcomes, segment_rows


def coverage_summary(legs: list[rolling.LegRow], arm: str, structured_rows: dict[int, dict[str, str]]) -> dict[str, Any]:
    covered = 0
    primary_hits = 0
    protect_hits = 0
    full_cover_rows = 0
    stopped = 0
    stopped_correct = 0
    stopped_wrong = 0
    role_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    for leg in legs:
        codes = codes_for(leg, arm)
        role = actual_role(codes, leg.actual_code)
        role_counts[role] += 1
        if leg.actual_code and leg.actual_code in codes:
            covered += 1
        if role == "primary_hit":
            primary_hits += 1
        elif role == "protect_hit":
            protect_hits += 1
        if len(codes) >= 3:
            full_cover_rows += 1
        row = structured_rows.get(leg.match_idx, {})
        stop_flag = row.get("active_stop_flag" if arm == "active" else "shadow_stop_flag")
        is_stopped = stop_flag in {"1", "true", "True"} or not codes
        if is_stopped:
            stopped += 1
            if role == "miss" or not codes:
                stopped_correct += 1
            else:
                stopped_wrong += 1
        if role == "miss":
            tag_counts.update(["coverage_miss"])
        tag_counts.update(parse_tags(row.get("risk_tags")))
    leg_count = len(legs)
    return {
        "leg_count": leg_count,
        "covered_leg_count": covered,
        "coverage_rate": round(covered / leg_count, 6) if leg_count else None,
        "primary_hits": primary_hits,
        "protect_hits": protect_hits,
        "full_cover_rows": full_cover_rows,
        "stop_check": {
            "stopped": stopped,
            "stopped_correct": stopped_correct,
            "stopped_wrong": stopped_wrong,
        },
        "actual_role_counts": dict(sorted(role_counts.items())),
        "failure_tag_counts": dict(sorted(tag_counts.items())),
    }


def build_match_attribution(
    legs: list[rolling.LegRow],
    arm: str,
    structured_rows: dict[int, dict[str, str]],
    outcomes: list[TicketOutcome],
    *,
    stake_yuan_per_ticket: float,
) -> list[dict[str, Any]]:
    appearances: Counter[int] = Counter()
    miss_appearances: Counter[int] = Counter()
    hit_appearances: Counter[int] = Counter()
    contribution: defaultdict[int, float] = defaultdict(float)
    code_counts: defaultdict[int, Counter[str]] = defaultdict(Counter)
    legs_by_idx = {leg.match_idx: leg for leg in legs}
    for outcome in outcomes:
        leg_share = stake_yuan_per_ticket / max(len(outcome.ticket), 1)
        payout_share = (outcome.payout_units * stake_yuan_per_ticket / max(len(outcome.ticket), 1)) if outcome.hit else 0.0
        for match_idx, code in outcome.ticket:
            leg = legs_by_idx[match_idx]
            appearances[match_idx] += 1
            code_counts[match_idx][code] += 1
            contribution[match_idx] += payout_share - leg_share
            if outcome.hit:
                hit_appearances[match_idx] += 1
            elif leg.actual_code != code:
                miss_appearances[match_idx] += 1

    rows: list[dict[str, Any]] = []
    for leg in sorted(legs, key=lambda item: item.match_idx):
        codes = codes_for(leg, arm)
        row = structured_rows.get(leg.match_idx, {})
        role = actual_role(codes, leg.actual_code)
        tags = parse_tags(row.get("risk_tags"))
        next_rule = "keep_rule"
        if role == "miss":
            next_rule = f"review_selection_for_actual_{leg.actual_code or 'unknown'}"
        elif role == "protect_hit":
            next_rule = "review_primary_confidence_keep_protection"
        elif len(codes) >= 3:
            next_rule = "review_full_cover_budget_compression"
        elif not codes:
            next_rule = "review_stop_reason"
        rows.append({
            "issue": leg.issue,
            "match_idx": leg.match_idx,
            "match_id": leg.match_id,
            "league": leg.league,
            "home": leg.home,
            "away": leg.away,
            "selection_codes": list(codes),
            "primary_code": codes[0] if codes else "",
            "selection_role": selection_role(codes),
            "actual_role": role,
            "actual_code": leg.actual_code or "",
            "actual_label": OUTCOME_LABELS.get(leg.actual_code or "", ""),
            "winning_sp": leg.winning_sp,
            "ticket_appearances": appearances[leg.match_idx],
            "hit_ticket_appearances": hit_appearances[leg.match_idx],
            "miss_ticket_appearances": miss_appearances[leg.match_idx],
            "selected_code_counts": dict(sorted(code_counts[leg.match_idx].items())),
            "profit_contribution_yuan": round(contribution[leg.match_idx], 6),
            "miss_tags": ["coverage_miss"] if role == "miss" else [],
            "protect_tags": ["protect_hit"] if role == "protect_hit" else [],
            "failure_tags": tags,
            "next_rule_suggestion": next_rule,
        })
    return rows


def slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    structured_rows, fieldnames = load_structured_rows(args.structured_csv, args.issue)
    if not structured_rows:
        raise SystemExit(f"No structured rows for issue {args.issue}: {args.structured_csv}")
    variant_id = infer_variant_id(structured_rows, args.arm, args.variant_id)
    variant_version = args.variant_version or infer_variant_version(structured_rows, args.arm)
    legs = rolling.load_legs(args.structured_csv, args.db, issue=args.issue)
    if not legs:
        raise SystemExit(f"No replay legs loaded for issue {args.issue}")
    segments = rolling.build_segments(
        legs,
        base_window_hours=args.window_hours,
        extend_hours=rolling.parse_extend_hours(args.extend_hours),
        min_matches=args.min_matches,
        max_matches=args.max_matches,
    )
    budget_ticket_units = (
        int(args.budget_units)
        if args.budget_units is not None
        else int(args.segment_budget_yuan // args.stake_yuan_per_ticket)
    )
    n_values = [int(item) for item in str(args.n_values).split(",") if item.strip()]
    dynamic_summary, dynamic_outcomes, _segment_rows = build_dynamic_replay(
        segments,
        args.arm,
        variant_id=variant_id,
        budget_ticket_units=budget_ticket_units,
        stake_yuan_per_ticket=args.stake_yuan_per_ticket,
        budget_coverage=args.budget_coverage,
        max_expanded_cost_multiple=args.max_expanded_cost_multiple,
        min_n=args.min_n,
        max_n=args.max_n,
        sample_seed=args.sample_seed,
        budget_fill_mode=args.budget_fill_mode,
    )
    flat_legs = [leg for segment in segments for leg in segment.legs]
    coverage = coverage_summary(flat_legs, args.arm, structured_rows)
    n_replay = build_n_replay(
        segments,
        args.arm,
        variant_id=variant_id,
        n_values=n_values,
        budget_ticket_units=budget_ticket_units,
        stake_yuan_per_ticket=args.stake_yuan_per_ticket,
        sample_seed=args.sample_seed,
        budget_fill_mode=args.budget_fill_mode,
    )
    dynamic_summary.update({
        "planned_budget_yuan": round(len(segments) * args.segment_budget_yuan, 6),
        "budget_per_segment_yuan": args.segment_budget_yuan,
        "coverage": coverage,
    })
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "issue": args.issue,
        "variant_id": variant_id,
        "variant_version": variant_version,
        "decision_time": {
            "scope": "post_settlement_issue_replay",
            "decision_source": args.arm,
            "structured_csv": str(args.structured_csv),
            "structured_csv_fields": fieldnames,
        },
        "review_version": args.review_version,
        "generated_at": now_iso(),
        "no_future_policy": (
            "Uses finalized settlement only for postmatch replay. The source structured decision CSV "
            "and variant_id are part of the artifact identity; reruns must publish a new variant/version "
            "or explicitly overwrite with --force, and post-settlement artifacts are review-only."
        ),
        "settings": {
            "window_hours": args.window_hours,
            "extend_hours": args.extend_hours,
            "min_matches": args.min_matches,
            "max_matches": args.max_matches,
            "segment_budget_yuan": args.segment_budget_yuan,
            "stake_yuan_per_ticket": args.stake_yuan_per_ticket,
            "budget_ticket_units": budget_ticket_units,
            "budget_coverage": args.budget_coverage,
            "max_expanded_cost_multiple": args.max_expanded_cost_multiple,
            "min_n": args.min_n,
            "max_n": args.max_n,
            "n_values": n_values,
            "selection_mode": "sample_budget_or_full_if_within_budget",
            "budget_fill_mode": args.budget_fill_mode,
            "sample_seed": args.sample_seed,
        },
        "summary": dynamic_summary,
        "n_replay": n_replay,
        "match_attribution": build_match_attribution(
            flat_legs,
            args.arm,
            structured_rows,
            dynamic_outcomes,
            stake_yuan_per_ticket=args.stake_yuan_per_ticket,
        ),
    }


def output_path(args: argparse.Namespace, artifact: dict[str, Any]) -> Path:
    date_slug = args.date_slug or datetime.now(timezone.utc).strftime("%Y%m%d")
    variant_slug = slugify(str(artifact["variant_id"]))
    return (
        args.output_dir
        / f"{artifact['issue']}_{date_slug}_{variant_slug}"
        / f"postmatch_ticket_pool_{artifact['issue']}_{variant_slug}.json"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--structured-csv", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--arm", choices=("active", "shadow"), default="shadow")
    parser.add_argument("--variant-id")
    parser.add_argument("--variant-version")
    parser.add_argument("--review-version", default=DEFAULT_REVIEW_VERSION)
    parser.add_argument("--date-slug")
    parser.add_argument("--window-hours", type=float, default=12.0)
    parser.add_argument("--extend-hours", default="18,24,36")
    parser.add_argument("--min-matches", type=int, default=6)
    parser.add_argument("--max-matches", type=int, default=24)
    parser.add_argument("--segment-budget-yuan", type=float, default=1000.0)
    parser.add_argument("--stake-yuan-per-ticket", type=float, default=2.0)
    parser.add_argument("--budget-units", type=int, default=None)
    parser.add_argument("--budget-coverage", choices=("auto", "ok", "thin", "insufficient"), default="auto")
    parser.add_argument("--max-expanded-cost-multiple", type=float, default=10.0)
    parser.add_argument("--sample-seed", type=int, default=20260707)
    parser.add_argument("--budget-fill-mode", choices=("scale_to_budget", "cap_at_full_cost"), default="scale_to_budget")
    parser.add_argument("--min-n", type=int, default=3)
    parser.add_argument("--max-n", type=int, default=8)
    parser.add_argument("--n-values", default="3,4,5,6,7")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifact = build_artifact(args)
    path = output_path(args, artifact)
    if path.exists() and not args.force:
        raise SystemExit(f"Refusing to overwrite existing postmatch artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"artifact": str(path), "issue": artifact["issue"], "variant_id": artifact["variant_id"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
