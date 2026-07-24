#!/usr/bin/env python3
"""Replay active/shadow decisions as rolling time-segment N-ticket pools."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from select_rolling_segment_n import recommend_segment_n  # noqa: E402
from src.natural_day_manifest import (  # noqa: E402
    NaturalDayManifestError,
    load_published_manifest,
    segment_membership,
    verify_operational_windows,
)
from src.natural_day_segments import build_natural_day_segments  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results/rolling_segment_n_replay"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/research"
OUTCOME_CODES = ("3", "1", "0")


@dataclass(frozen=True)
class LegRow:
    issue: str
    match_idx: int
    match_id: str
    kickoff: datetime
    league: str
    home: str
    away: str
    active_codes: tuple[str, ...]
    shadow_codes: tuple[str, ...]
    probabilities: dict[str, float]
    sp: dict[str, float]
    actual_code: str | None
    winning_sp: float | None


@dataclass(frozen=True)
class Segment:
    segment_idx: int
    start: datetime
    end: datetime
    window_hours: float
    legs: tuple[LegRow, ...]


def fnum(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def parse_codes(value: str) -> tuple[str, ...]:
    return tuple(code for code in str(value or "").split("+") if code in OUTCOME_CODES)


def parse_dt(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"unsupported datetime format: {value!r}")


def coefficient(weights: Iterable[float], degree: int) -> float:
    if degree < 0:
        return 0.0
    coeff = [0.0 for _ in range(degree + 1)]
    coeff[0] = 1.0
    for weight in weights:
        for k in range(degree, 0, -1):
            coeff[k] += coeff[k - 1] * weight
    return coeff[degree]


def load_match_times(db_path: Path, issue: str) -> dict[int, dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT issue, match_idx, end_time, league, home, away, result_code, winning_sp
            FROM matches
            WHERE issue=?
            """,
            (issue,),
        ).fetchall()
    finally:
        conn.close()
    return {int(row["match_idx"]): dict(row) for row in rows}


def load_legs(structured_csv: Path, db_path: Path, issue: str | None = None) -> list[LegRow]:
    with structured_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {
            "issue",
            "match_idx",
            "match_id",
            "active_selection_codes",
            "shadow_selection_codes",
            "p_3",
            "p_1",
            "p_0",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"structured CSV missing required columns: {', '.join(sorted(missing))}")
        csv_rows = list(reader)
    if not csv_rows:
        return []
    target_issue = issue or csv_rows[0]["issue"]
    match_times = load_match_times(db_path, target_issue)
    out: list[LegRow] = []
    for row in csv_rows:
        if row["issue"] != target_issue:
            continue
        match_idx = int(row["match_idx"])
        meta = match_times.get(match_idx)
        if not meta or not meta.get("end_time"):
            continue
        actual_code = row.get("actual_code") or meta.get("result_code") or None
        winning_sp = fnum(row.get("winning_sp") or meta.get("winning_sp"), default=0.0) or None
        out.append(
            LegRow(
                issue=target_issue,
                match_idx=match_idx,
                match_id=row.get("match_id") or f"{target_issue}_{match_idx:03d}",
                kickoff=parse_dt(str(meta["end_time"])),
                league=str(meta.get("league") or row.get("league") or ""),
                home=str(meta.get("home") or row.get("home") or ""),
                away=str(meta.get("away") or row.get("away") or ""),
                active_codes=parse_codes(row.get("active_selection_codes", "")),
                shadow_codes=parse_codes(row.get("shadow_selection_codes", "")),
                probabilities={code: fnum(row.get(f"p_{code}")) for code in OUTCOME_CODES},
                sp={code: fnum(row.get(f"sp_{code}")) for code in OUTCOME_CODES},
                actual_code=str(actual_code) if actual_code in OUTCOME_CODES else None,
                winning_sp=winning_sp,
            )
        )
    return sorted(out, key=lambda leg: (leg.kickoff, leg.match_idx))


def parse_extend_hours(value: str) -> list[float]:
    hours = sorted({float(item) for item in value.split(",") if item.strip()})
    if not hours:
        raise ValueError("extend hours cannot be empty")
    return hours


def build_segments(
    legs: list[LegRow],
    *,
    db_path: Path | None = None,
    require_published_contract: bool = False,
    base_window_hours: float = 12.0,
    extend_hours: list[float] | None = None,
    min_matches: int = 6,
    max_matches: int = 24,
) -> list[Segment]:
    # Arguments remain for CLI compatibility.  Membership is exclusively owned
    # by BJ-SEG-DAY-001; in particular max_matches must not split a busy day.
    if not legs:
        return []
    by_idx = {leg.match_idx: leg for leg in legs}
    if db_path is not None:
        conn = sqlite3.connect(db_path)
        try:
            manifest = load_published_manifest(conn, legs[0].issue)
            if manifest is not None:
                verify_operational_windows(conn, manifest)
                published: list[Segment] = []
                for segment_idx, indices in segment_membership(manifest):
                    segment_legs = tuple(by_idx[idx] for idx in indices if idx in by_idx)
                    if not segment_legs:
                        continue
                    published.append(
                        Segment(
                            segment_idx=segment_idx,
                            start=segment_legs[0].kickoff,
                            end=segment_legs[-1].kickoff,
                            window_hours=round(
                                (
                                    segment_legs[-1].kickoff - segment_legs[0].kickoff
                                ).total_seconds()
                                / 3600,
                                6,
                            ),
                            legs=segment_legs,
                        )
                    )
                return published
            if require_published_contract:
                raise ValueError(
                    "published natural-day segment contract is required for operational by_segment generation"
                )
        except NaturalDayManifestError as exc:
            raise ValueError(
                f"published natural-day segment contract is invalid: {exc}"
            ) from exc
        finally:
            conn.close()
    if require_published_contract:
        raise ValueError(
            "published natural-day segment contract is required for operational by_segment generation"
        )
    result = build_natural_day_segments(legs[0].issue, legs)
    return [
        Segment(
            segment_idx=item.segment_idx,
            start=item.first_kickoff.replace(tzinfo=None),
            end=item.last_kickoff.replace(tzinfo=None),
            window_hours=round(
                (item.last_kickoff - item.first_kickoff).total_seconds() / 3600,
                6,
            ),
            legs=tuple(by_idx[idx] for idx in item.match_indices),
        )
        for item in result.segments
    ]


def selection_probability(leg: LegRow, arm: str) -> float:
    codes = leg.active_codes if arm == "active" else leg.shadow_codes
    return sum(leg.probabilities.get(code, 0.0) for code in codes)


def expanded_cost(legs: Iterable[LegRow], arm: str, n_value: int) -> float:
    widths = [len(leg.active_codes if arm == "active" else leg.shadow_codes) for leg in legs]
    return coefficient(widths, n_value)


def stable_seed(*parts: object) -> int:
    text = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def weighted_choice(items: list[Any], weights: list[float], rng: random.Random) -> Any:
    total = sum(max(0.0, weight) for weight in weights)
    if total <= 0:
        return items[rng.randrange(len(items))]
    marker = rng.random() * total
    running = 0.0
    for item, weight in zip(items, weights):
        running += max(0.0, weight)
        if running >= marker:
            return item
    return items[-1]


def weighted_sample_without_replacement(
    items: list[LegRow],
    weights: list[float],
    k: int,
    rng: random.Random,
) -> list[LegRow]:
    remaining_items = list(items)
    remaining_weights = list(weights)
    selected: list[LegRow] = []
    for _ in range(min(k, len(remaining_items))):
        choice = weighted_choice(remaining_items, remaining_weights, rng)
        idx = remaining_items.index(choice)
        selected.append(choice)
        remaining_items.pop(idx)
        remaining_weights.pop(idx)
    return selected


def selected_codes_for(leg: LegRow, arm: str) -> tuple[str, ...]:
    return leg.active_codes if arm == "active" else leg.shadow_codes


def leg_q_weight(leg: LegRow, arm: str) -> float:
    qs = [leg.probabilities.get(code, 0.0) * leg.sp.get(code, 0.0) for code in selected_codes_for(leg, arm)]
    return max(qs) if qs else 0.0


def sample_exact_ticket(legs: list[LegRow], arm: str, n_value: int, rng: random.Random) -> tuple[tuple[tuple[int, str], ...], float]:
    leg_weights = [leg_q_weight(leg, arm) for leg in legs]
    sampled_legs = sorted(
        weighted_sample_without_replacement(legs, leg_weights, n_value, rng),
        key=lambda leg: leg.match_idx,
    )
    ticket: list[tuple[int, str]] = []
    payout = 1.0
    hit = True
    for leg in sampled_legs:
        codes = list(selected_codes_for(leg, arm))
        code_weights = [leg.probabilities.get(code, 0.0) * leg.sp.get(code, 0.0) for code in codes]
        code = weighted_choice(codes, code_weights, rng)
        ticket.append((leg.match_idx, code))
        if leg.actual_code != code or leg.winning_sp is None:
            hit = False
        payout *= float(leg.winning_sp or 0.0)
    return tuple(ticket), payout if hit else 0.0


def sampled_budget_ticket_payout(
    legs: list[LegRow],
    arm: str,
    n_value: int,
    budget_ticket_units: int,
    *,
    settled: bool,
    rng: random.Random,
) -> tuple[int, float]:
    """Sample exact N tickets without enumerating the full Cartesian basket."""
    if n_value <= 0 or budget_ticket_units <= 0:
        return 0, 0.0
    full_cost = int(round(expanded_cost(legs, arm, n_value)))
    selected_count = min(full_cost, budget_ticket_units)
    if not settled or selected_count <= 0:
        return selected_count, 0.0
    hit_legs = [
        leg
        for leg in legs
        if leg.actual_code
        and leg.winning_sp is not None
        and leg.actual_code in (leg.active_codes if arm == "active" else leg.shadow_codes)
    ]
    if selected_count >= full_cost:
        return selected_count, coefficient([float(leg.winning_sp or 0.0) for leg in hit_legs], n_value)

    seen: set[tuple[tuple[int, str], ...]] = set()
    payout_sum = 0.0
    max_attempts = max(selected_count * 30, 1000)
    attempts = 0
    while len(seen) < selected_count and attempts < max_attempts:
        attempts += 1
        ticket, payout = sample_exact_ticket(legs, arm, n_value, rng)
        if ticket in seen:
            continue
        seen.add(ticket)
        payout_sum += payout
    return len(seen), payout_sum


def auto_budget_coverage(cost: float, budget_units: float) -> str:
    if budget_units <= 0:
        return "ok"
    if cost <= budget_units:
        return "ok"
    if cost <= budget_units * 10:
        return "thin"
    return "insufficient"


def replay_segment_arm(
    segment: Segment,
    arm: str,
    *,
    budget_ticket_units: int,
    stake_yuan_per_ticket: float,
    budget_coverage: str,
    max_expanded_cost_multiple: float,
    min_n: int,
    max_n: int,
    selection_mode: str,
    sample_seed: int,
) -> dict[str, Any]:
    legs = list(segment.legs)
    l_count = len(legs)
    expected_rate = sum(selection_probability(leg, arm) for leg in legs) / l_count if legs else 0.0
    if budget_coverage == "auto":
        initial = recommend_segment_n(l_count, expected_rate, budget_coverage="ok", min_n=min_n, max_n=max_n)
        initial_n = initial.recommended_n or min_n
        budget_state = auto_budget_coverage(expanded_cost(legs, arm, initial_n), float(budget_ticket_units))
    else:
        budget_state = budget_coverage
    recommendation = recommend_segment_n(l_count, expected_rate, budget_coverage=budget_state, min_n=min_n, max_n=max_n)
    n_value = recommendation.recommended_n
    initial_recommended_n = n_value
    action = recommendation.action
    reasons = list(recommendation.reasons)
    codes_for = (lambda leg: leg.active_codes) if arm == "active" else (lambda leg: leg.shadow_codes)
    widths = [len(codes_for(leg)) for leg in legs]
    type_counts = Counter("single" if width == 1 else "double" if width == 2 else "full" if width >= 3 else "no-buy" for width in widths)
    guardrail_target = float(budget_ticket_units) * max_expanded_cost_multiple if max_expanded_cost_multiple > 0 else 0.0
    guardrail_drops = 0
    if n_value and guardrail_target > 0:
        while n_value > min_n and expanded_cost(legs, arm, n_value) > guardrail_target:
            n_value -= 1
            guardrail_drops += 1
        if guardrail_drops:
            reasons.append(f"expanded_cost_guardrail_drop_{guardrail_drops}")
            action = f"cost_guarded_{action}"

    settled = all(leg.actual_code is not None and leg.winning_sp is not None for leg in legs)
    actual_hits = sum(1 for leg in legs if leg.actual_code and leg.actual_code in codes_for(leg))
    full_cost = expanded_cost(legs, arm, n_value) if n_value else 0.0
    if n_value and guardrail_target > 0 and full_cost > guardrail_target:
        reasons.append("expanded_cost_still_above_guardrail_at_min_n")
        action = "sample_budget_extreme_expansion"
    hit_legs = [leg for leg in legs if leg.actual_code and leg.actual_code in codes_for(leg) and leg.winning_sp is not None]
    winning_tickets = coefficient([1.0 for _leg in hit_legs], n_value) if n_value else 0.0
    full_payout = coefficient([float(leg.winning_sp or 0.0) for leg in hit_legs], n_value) if n_value else 0.0
    if selection_mode == "full_basket":
        selected_tickets = int(round(full_cost))
        payout = full_payout
    elif selection_mode == "sample_budget":
        rng = random.Random(stable_seed(sample_seed, segment.segment_idx, arm, n_value, budget_ticket_units))
        selected_tickets, payout = sampled_budget_ticket_payout(
            legs,
            arm,
            n_value or 0,
            budget_ticket_units,
            settled=settled,
            rng=rng,
        )
    else:
        raise ValueError("selection_mode must be full_basket or sample_budget")
    profit = payout - selected_tickets if settled and n_value else None
    roi = profit / selected_tickets if profit is not None and selected_tickets else None
    match_indices = ",".join(str(leg.match_idx) for leg in legs)
    return {
        "segment_idx": segment.segment_idx,
        "arm": arm,
        "segment_start": segment.start.strftime("%Y-%m-%d %H:%M"),
        "segment_end": segment.end.strftime("%Y-%m-%d %H:%M"),
        "window_hours": round(segment.window_hours, 2),
        "l_count": l_count,
        "expected_coverage_hit_rate": round(expected_rate, 6),
        "actual_coverage_hits": actual_hits if settled else "",
        "actual_coverage_hit_rate": round(actual_hits / l_count, 6) if settled and l_count else "",
        "budget_coverage": budget_state,
        "initial_recommended_n": initial_recommended_n or "",
        "recommended_n": n_value or "",
        "action": action,
        "reasons": ";".join(reasons),
        "type_counts": dict(type_counts),
        "selection_mode": selection_mode,
        "expanded_cost": round(full_cost, 6),
        "expanded_cost_guardrail_multiple": max_expanded_cost_multiple,
        "expanded_cost_guardrail_target": round(guardrail_target, 6),
        "expanded_cost_guardrail_drops": guardrail_drops,
        "selected_tickets": selected_tickets,
        "selected_cost_yuan": round(selected_tickets * stake_yuan_per_ticket, 6),
        "segment_budget_yuan": round(budget_ticket_units * stake_yuan_per_ticket, 6),
        "winning_tickets": int(round(winning_tickets)) if settled else "",
        "full_basket_payout": round(full_payout, 6) if settled else "",
        "total_payout": round(payout, 6) if settled else "",
        "profit": round(profit, 6) if profit is not None else "",
        "profit_yuan": round(profit * stake_yuan_per_ticket, 6) if profit is not None else "",
        "roi": round(roi, 6) if roi is not None else "",
        "budget_ticket_units": budget_ticket_units,
        "sample_seed": sample_seed,
        "match_indices": match_indices,
    }


def replay_segments(
    segments: list[Segment],
    *,
    arms: tuple[str, ...] = ("active", "shadow"),
    budget_ticket_units: int = 500,
    stake_yuan_per_ticket: float = 2.0,
    budget_coverage: str = "auto",
    max_expanded_cost_multiple: float = 10.0,
    min_n: int = 3,
    max_n: int = 8,
    selection_mode: str = "sample_budget",
    sample_seed: int = 20260704,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment in segments:
        for arm in arms:
            rows.append(
                replay_segment_arm(
                    segment,
                    arm,
                    budget_ticket_units=budget_ticket_units,
                    stake_yuan_per_ticket=stake_yuan_per_ticket,
                    budget_coverage=budget_coverage,
                    max_expanded_cost_multiple=max_expanded_cost_multiple,
                    min_n=min_n,
                    max_n=max_n,
                    selection_mode=selection_mode,
                    sample_seed=sample_seed,
                )
            )
    return rows


def summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["arm"])].append(row)
    out: list[dict[str, Any]] = []
    for arm, arm_rows in sorted(grouped.items()):
        settled = [row for row in arm_rows if row.get("profit") != ""]
        planned_cost = sum(fnum(row.get("selected_tickets")) for row in arm_rows)
        planned_cost_yuan = sum(fnum(row.get("selected_cost_yuan")) for row in arm_rows)
        settled_cost = sum(fnum(row.get("selected_tickets")) for row in settled)
        payout = sum(fnum(row.get("total_payout")) for row in settled)
        profit = payout - settled_cost
        stake_yuan = fnum(arm_rows[0].get("selected_cost_yuan")) / max(fnum(arm_rows[0].get("selected_tickets")), 1.0) if arm_rows else 2.0
        out.append(
            {
                "arm": arm,
                "segments": len(arm_rows),
                "settled_segments": len(settled),
                "avg_l_count": sum(fnum(row.get("l_count")) for row in arm_rows) / len(arm_rows) if arm_rows else 0.0,
                "avg_n": sum(fnum(row.get("recommended_n")) for row in arm_rows) / len(arm_rows) if arm_rows else 0.0,
                "dead_segments": sum(1 for row in settled if fnum(row.get("winning_tickets")) <= 0),
                "selected_tickets": round(planned_cost, 6),
                "selected_cost_yuan": round(planned_cost_yuan, 6),
                "settled_selected_tickets": round(settled_cost, 6),
                "total_payout": round(payout, 6),
                "profit": round(profit, 6) if settled else "",
                "profit_yuan": round(profit * stake_yuan, 6) if settled else "",
                "roi": round(profit / settled_cost, 6) if settled_cost else "",
            }
        )
    return out


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
            value = row.get(key, "")
            values.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_report(
    *,
    issue: str,
    segment_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
    args: argparse.Namespace,
    segment_csv: Path,
    summary_json: Path,
) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return f"""# Rolling Segment N-Ticket Replay {issue}

Generated: {generated}

## Scope

- This is a research/shadow replay. No active release config is changed.
- Match time uses `matches.end_time` from the SQLite DB.
- Segments are non-overlapping rolling pools, starting from the first remaining
  kickoff. Each pool starts with `{args.window_hours}`h and may extend through
  `{args.extend_hours}`h to reach `--min-matches`.
- N is selected by `scripts/select_rolling_segment_n.py`: half of qualified
  match count, capped at `{args.max_n}`, then adjusted by expected coverage hit
  rate and budget coverage.
- Full-basket expanded cost is computed by polynomial coefficients for exposure
  diagnostics.
- `sample_budget` mode samples exact N tickets by leg/result q weights and keeps
  at most the segment budget; it does not enumerate the full Cartesian basket.
  Full-basket expanded cost is still shown as exposure.
- Expanded-cost guardrail: if full-basket cost is more than
  `{args.max_expanded_cost_multiple}`x the segment ticket budget, N is dropped
  until the diagnostic exposure is within that bound or reaches `--min-n`.
- Segment budget: `{args.segment_budget_yuan}` yuan, stake per exact ticket:
  `{args.stake_yuan_per_ticket}` yuan. Sample seed: `{args.sample_seed}`.

## Summary

{md_table(summary_rows, [
        ("arm", "arm"),
        ("segments", "segments"),
        ("settled", "settled_segments"),
        ("avg L", "avg_l_count"),
        ("avg N", "avg_n"),
        ("dead", "dead_segments"),
        ("selected", "selected_tickets"),
        ("cost yuan", "selected_cost_yuan"),
        ("settled selected", "settled_selected_tickets"),
        ("payout", "total_payout"),
        ("profit", "profit"),
        ("profit yuan", "profit_yuan"),
        ("ROI", "roi"),
    ])}

## Segments

{md_table(segment_rows, [
        ("seg", "segment_idx"),
        ("arm", "arm"),
        ("start", "segment_start"),
        ("end", "segment_end"),
        ("h", "window_hours"),
        ("L", "l_count"),
        ("p_exp", "expected_coverage_hit_rate"),
        ("hits", "actual_coverage_hits"),
        ("N", "recommended_n"),
        ("N0", "initial_recommended_n"),
        ("budget", "budget_coverage"),
        ("action", "action"),
        ("full cost", "expanded_cost"),
        ("guard drops", "expanded_cost_guardrail_drops"),
        ("selected", "selected_tickets"),
        ("cost yuan", "selected_cost_yuan"),
        ("win tickets", "winning_tickets"),
        ("profit", "profit"),
        ("profit yuan", "profit_yuan"),
        ("ROI", "roi"),
        ("matches", "match_indices"),
    ])}

Artifacts:

- Segment CSV: `{segment_csv}`
- Summary JSON: `{summary_json}`
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--structured-csv", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--window-hours", type=float, default=12.0)
    parser.add_argument("--extend-hours", default="18,24,36")
    parser.add_argument("--min-matches", type=int, default=6)
    parser.add_argument("--max-matches", type=int, default=24)
    parser.add_argument("--segment-budget-yuan", type=float, default=1000.0)
    parser.add_argument("--stake-yuan-per-ticket", type=float, default=2.0)
    parser.add_argument("--budget-units", type=int, default=None)
    parser.add_argument("--budget-coverage", choices=("auto", "ok", "thin", "insufficient"), default="auto")
    parser.add_argument("--max-expanded-cost-multiple", type=float, default=10.0)
    parser.add_argument("--selection-mode", choices=("sample_budget", "full_basket"), default="sample_budget")
    parser.add_argument("--sample-seed", type=int, default=20260704)
    parser.add_argument("--min-n", type=int, default=3)
    parser.add_argument("--max-n", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> dict[str, Any]:
    legs = load_legs(args.structured_csv, args.db, issue=args.issue)
    if not legs:
        raise SystemExit(f"No legs loaded for issue {args.issue}")
    segments = build_segments(
        legs,
        db_path=args.db,
        base_window_hours=args.window_hours,
        extend_hours=parse_extend_hours(args.extend_hours),
        min_matches=args.min_matches,
        max_matches=args.max_matches,
    )
    budget_ticket_units = (
        int(args.budget_units)
        if args.budget_units is not None
        else int(args.segment_budget_yuan // args.stake_yuan_per_ticket)
    )
    segment_rows = replay_segments(
        segments,
        budget_ticket_units=budget_ticket_units,
        stake_yuan_per_ticket=args.stake_yuan_per_ticket,
        budget_coverage=args.budget_coverage,
        max_expanded_cost_multiple=args.max_expanded_cost_multiple,
        min_n=args.min_n,
        max_n=args.max_n,
        selection_mode=args.selection_mode,
        sample_seed=args.sample_seed,
    )
    summary_rows = summarize(segment_rows)
    guardrail_slug = "off" if args.max_expanded_cost_multiple <= 0 else f"{args.max_expanded_cost_multiple:g}".replace(".", "p")
    slug = (
        f"{args.issue}_w{int(args.window_hours)}_x{args.extend_hours.replace(',', '-')}"
        f"_n{args.max_n}_b{int(args.segment_budget_yuan)}_m{guardrail_slug}"
    )
    out_dir = args.output_dir / slug
    segment_csv = out_dir / "rolling_segment_n_replay_segments.csv"
    summary_json = out_dir / "rolling_segment_n_replay_summary.json"
    write_csv(segment_csv, segment_rows)
    payload = {
        "issue": args.issue,
        "structured_csv": str(args.structured_csv),
        "db": str(args.db),
        "segment_csv": str(segment_csv),
        "summary_rows": summary_rows,
        "segments": len(segments),
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
            "selection_mode": args.selection_mode,
            "sample_seed": args.sample_seed,
            "min_n": args.min_n,
            "max_n": args.max_n,
        },
    }
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = args.report_dir / f"rolling_segment_n_replay_{slug}_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(
            issue=args.issue,
            segment_rows=segment_rows,
            summary_rows=summary_rows,
            args=args,
            segment_csv=segment_csv,
            summary_json=summary_json,
        ),
        encoding="utf-8",
    )
    payload["report_path"] = str(report_path)
    payload["summary_json"] = str(summary_json)
    return payload


def main() -> None:
    args = parse_args()
    payload = run(args)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {payload['segment_csv']}")
        print(f"Wrote {payload['summary_json']}")
        print(f"Wrote {payload['report_path']}")


if __name__ == "__main__":
    main()
