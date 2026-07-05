#!/usr/bin/env python3
"""Apply an execution policy on top of structured v4.2.0000 decisions."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import replay_rolling_segment_n_tickets as rolling  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
OUTCOME_CODES = ("3", "1", "0")
POLICY_VERSION = "v4.2.0000_execution_policy_2026-07-05"
SHADOW_ARM = "shadow_v4.2.0000_execution"
SHADOW_VERSION = "llm_chain_structured_v4.2.0000_layered_merge_execution_policy"


@dataclass
class RowExecution:
    selection_codes: list[str]
    action: str
    reasons: list[str]
    double_codes: list[str]
    full_score: float
    full_candidate: bool
    full_kept: bool
    segment_idx: int | None = None


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def safe_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def parse_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace("/", "+").replace(",", "+").replace(" ", "+").split("+")
    return [str(code) for code in raw if str(code) in OUTCOME_CODES]


def unique_codes(codes: list[str]) -> list[str]:
    out: list[str] = []
    for code in codes:
        if code in OUTCOME_CODES and code not in out:
            out.append(code)
    return out


def load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def code_metrics(source_row: dict[str, Any]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for code in OUTCOME_CODES:
        p = safe_float(source_row.get(f"p_{code}"))
        sp = safe_float(source_row.get(f"sp_{code}"))
        q = safe_float(source_row.get(f"q_{code}"))
        if q <= 0 and p > 0 and sp > 0:
            q = p * sp
        out[code] = {"p": p, "sp": sp, "q": q}
    return out


def top_code(metrics: dict[str, dict[str, float]], key: str) -> str | None:
    usable = [(code, values.get(key, 0.0)) for code, values in metrics.items()]
    usable = [(code, value) for code, value in usable if value > 0]
    return max(usable, key=lambda item: item[1])[0] if usable else None


def unbacked_draw(decision_row: dict[str, Any]) -> bool:
    return (
        str(decision_row.get("v4_semantic_draw") or "none") == "none"
        and str(decision_row.get("v4_team_strength_side") or "") in {"home", "away"}
        and safe_float(decision_row.get("v4_team_strength_confidence")) >= 0.58
    )


def candidate_base_scores(decision_row: dict[str, Any]) -> dict[str, float]:
    scores = {code: 0.0 for code in OUTCOME_CODES}
    candidates = safe_json(decision_row.get("v4_candidate_pool_json"), [])
    if isinstance(candidates, list):
        for item in candidates:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "")
            if code in scores:
                scores[code] = max(scores[code], safe_float(item.get("score")))
    return scores


def rank_codes_for_execution(source_row: dict[str, Any], decision_row: dict[str, Any]) -> list[str]:
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    metrics = code_metrics(source_row)
    p_top = str(source_row.get("prob_top") or top_code(metrics, "p") or "")
    q_top = str(source_row.get("q_top") or top_code(metrics, "q") or "")
    mandatory = set(parse_codes(decision_row.get("v4_mandatory_codes")))
    protected = set(parse_codes(decision_row.get("v4_protected_codes")))
    team_codes = set(parse_codes(decision_row.get("v4_team_strength_codes")))
    merge_flags = set(str(decision_row.get("v4_merge_flags") or "").split(";"))
    semantic_draw = str(decision_row.get("v4_semantic_draw") or "none")
    scores = candidate_base_scores(decision_row)

    for code in OUTCOME_CODES:
        values = metrics[code]
        if code in mandatory:
            scores[code] += 5.0
        if code in protected:
            scores[code] += 0.65
        if code in team_codes:
            scores[code] += 0.55
        if code == p_top:
            scores[code] += 0.22
        if code == q_top and not (code == "1" and unbacked_draw(decision_row)):
            scores[code] += 0.25
        if values["q"] >= 1.80 and values["p"] >= 0.22:
            scores[code] += 0.50
        elif values["q"] >= 1.15 and values["p"] >= 0.20:
            scores[code] += 0.18
        if values["sp"] >= 5.0 and values["p"] >= 0.22:
            scores[code] += 0.18
        if code == "1":
            if semantic_draw == "explicit_draw":
                scores[code] += 0.70
            elif semantic_draw == "balanced":
                scores[code] += 0.35
            elif unbacked_draw(decision_row):
                scores[code] -= 0.55
        if code == q_top and "high_q_attraction" in merge_flags:
            scores[code] += 0.35

    return sorted(recommended, key=lambda code: scores.get(code, 0.0), reverse=True)


def compressed_double_codes(source_row: dict[str, Any], decision_row: dict[str, Any]) -> list[str]:
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    if len(recommended) <= 2:
        return recommended
    mandatory = parse_codes(decision_row.get("v4_mandatory_codes"))
    ranked = rank_codes_for_execution(source_row, decision_row)
    selected = unique_codes(mandatory)
    if len(selected) > 2:
        return []
    for code in ranked:
        if code not in selected:
            selected.append(code)
        if len(selected) >= 2:
            break
    return selected[:2]


def full_cover_score(source_row: dict[str, Any], decision_row: dict[str, Any], double_codes: list[str]) -> float:
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    if len(recommended) < 3:
        return 0.0
    metrics = code_metrics(source_row)
    merge_flags = set(str(decision_row.get("v4_merge_flags") or "").split(";"))
    full_reasons = set(str(decision_row.get("v4_full_cover_reasons") or "").split(";"))
    third_codes = [code for code in recommended if code not in set(double_codes)]
    third_q = max((metrics[code]["q"] for code in third_codes), default=0.0)
    third_p = max((metrics[code]["p"] for code in third_codes), default=0.0)
    third_sp = max((metrics[code]["sp"] for code in third_codes), default=0.0)
    max_q = max(values["q"] for values in metrics.values())
    high_q_count = sum(1 for code in recommended if metrics[code]["q"] >= 1.35 and metrics[code]["p"] >= 0.20)

    score = 0.0
    if "layer_conflict_requires_full_cover_or_skip" in merge_flags or "layer_conflict_requires_full_cover_or_skip" in full_reasons:
        score += 0.65
    if "candidate_score_dense" in full_reasons:
        score += 0.20
    if "extreme_sp_or_source_conflict_full" in full_reasons:
        score += 0.12
    if max_q >= 2.0:
        score += 0.45
    elif max_q >= 1.55:
        score += 0.28
    if third_q >= 1.45 and third_p >= 0.22:
        score += 0.70
    elif third_q >= 1.15 and third_p >= 0.20:
        score += 0.35
    if third_sp >= 5.0 and third_p >= 0.22:
        score += 0.25
    if high_q_count >= 2:
        score += 0.25
    if any(code == "1" for code in third_codes) and unbacked_draw(decision_row):
        score -= 0.45
    return round(score, 4)


def evaluate_row_policy(
    source_row: dict[str, Any],
    decision_row: dict[str, Any],
    *,
    late_refresh_mode: str,
    full_score_threshold: float,
) -> RowExecution:
    source_action = str(decision_row.get("v4_action") or "")
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    double_codes = compressed_double_codes(source_row, decision_row)
    full_score = full_cover_score(source_row, decision_row, double_codes)
    full_candidate = len(recommended) >= 3 and full_score >= full_score_threshold
    merge_flags = set(str(decision_row.get("v4_merge_flags") or "").split(";"))
    full_reasons = set(str(decision_row.get("v4_full_cover_reasons") or "").split(";"))
    conflict_full = "layer_conflict_requires_full_cover_or_skip" in merge_flags or "layer_conflict_requires_full_cover_or_skip" in full_reasons

    if source_action == "stop":
        return RowExecution([], "skip_stop", ["source_action_stop"], double_codes, full_score, False, False)
    if source_action == "wait_late_refresh" and late_refresh_mode == "skip":
        return RowExecution([], "skip_wait_late_refresh", ["requires_late_refresh_before_bet"], double_codes, full_score, False, False)
    if not recommended:
        return RowExecution([], "skip_no_recommendation", ["empty_recommended_codes"], double_codes, full_score, False, False)
    if len(recommended) <= 2:
        reason = "late_refresh_proxy" if source_action == "wait_late_refresh" else "direct_buy"
        return RowExecution(recommended, "execute_double" if len(recommended) == 2 else "execute_single", [reason], double_codes, full_score, False, False)
    if full_candidate:
        return RowExecution(recommended, "candidate_full_cover", ["full_score_above_threshold"], double_codes, full_score, True, False)
    if conflict_full:
        if double_codes:
            return RowExecution(
                double_codes,
                "downgrade_full_to_double_layer_conflict",
                ["full_required_but_value_below_threshold"],
                double_codes,
                full_score,
                False,
                False,
            )
        return RowExecution([], "skip_uncompressed_layer_conflict", ["full_required_but_value_below_threshold"], double_codes, full_score, False, False)
    if double_codes:
        return RowExecution(double_codes, "downgrade_full_to_double", ["full_value_below_threshold"], double_codes, full_score, False, False)
    return RowExecution([], "skip_no_compressed_double", ["cannot_compress_full_cover"], double_codes, full_score, False, False)


def load_decisions(path: Path) -> dict[int, dict[str, str]]:
    rows, _fieldnames = load_csv(path)
    out: dict[int, dict[str, str]] = {}
    for row in rows:
        match_idx = int(safe_float(row.get("match_idx")))
        if match_idx > 0:
            out[match_idx] = row
    return out


def segments_by_match_idx(
    source_csv: Path,
    db_path: Path,
    issue: str,
    *,
    window_hours: float,
    extend_hours: str,
    min_matches: int,
    max_matches: int,
) -> dict[int, int]:
    legs = rolling.load_legs(source_csv, db_path, issue=issue)
    segments = rolling.build_segments(
        legs,
        base_window_hours=window_hours,
        extend_hours=rolling.parse_extend_hours(extend_hours),
        min_matches=min_matches,
        max_matches=max_matches,
    )
    out: dict[int, int] = {}
    for segment in segments:
        for leg in segment.legs:
            out[leg.match_idx] = segment.segment_idx
    return out


def apply_segment_full_cap(
    executions: dict[int, RowExecution],
    segment_lookup: dict[int, int],
    *,
    max_full_per_segment: int,
) -> None:
    grouped: dict[int, list[tuple[int, RowExecution]]] = {}
    for match_idx, execution in executions.items():
        execution.segment_idx = segment_lookup.get(match_idx)
        if execution.full_candidate:
            grouped.setdefault(execution.segment_idx or 0, []).append((match_idx, execution))
    for rows in grouped.values():
        rows.sort(key=lambda item: item[1].full_score, reverse=True)
        keep = {match_idx for match_idx, _execution in rows[:max(0, max_full_per_segment)]}
        for match_idx, execution in rows:
            if match_idx in keep:
                execution.full_kept = True
                execution.action = "execute_full_cover"
                execution.reasons = ["segment_full_cap_kept"] + execution.reasons
                continue
            if execution.double_codes:
                execution.selection_codes = execution.double_codes
                execution.action = "downgrade_full_to_double_over_cap"
                execution.reasons = ["segment_full_cap_overflow"] + execution.reasons
            else:
                execution.selection_codes = []
                execution.action = "skip_full_over_cap"
                execution.reasons = ["segment_full_cap_overflow_no_double"] + execution.reasons


def apply_policy(
    *,
    issue: str,
    source_csv: Path,
    decision_csv: Path,
    db_path: Path,
    output_csv: Path,
    report_path: Path,
    late_refresh_mode: str,
    full_score_threshold: float,
    max_full_per_segment: int,
    window_hours: float,
    extend_hours: str,
    min_matches: int,
    max_matches: int,
    policy_name: str,
) -> tuple[Path, Path, dict[str, Any]]:
    source_rows, source_fieldnames = load_csv(source_csv)
    decisions = load_decisions(decision_csv)
    segment_lookup = segments_by_match_idx(
        source_csv,
        db_path,
        issue,
        window_hours=window_hours,
        extend_hours=extend_hours,
        min_matches=min_matches,
        max_matches=max_matches,
    )

    executions: dict[int, RowExecution] = {}
    for source_row in source_rows:
        if str(source_row.get("issue") or issue) != issue:
            continue
        match_idx = int(safe_float(source_row.get("match_idx")))
        decision_row = decisions.get(match_idx)
        if not decision_row:
            executions[match_idx] = RowExecution([], "skip_missing_decision", ["missing_v4_2_decision"], [], 0.0, False, False)
            continue
        executions[match_idx] = evaluate_row_policy(
            source_row,
            decision_row,
            late_refresh_mode=late_refresh_mode,
            full_score_threshold=full_score_threshold,
        )
    apply_segment_full_cap(executions, segment_lookup, max_full_per_segment=max_full_per_segment)

    extra_fields = [
        "execution_policy_version",
        "execution_policy_name",
        "execution_action",
        "execution_reasons",
        "execution_source_action",
        "execution_recommended_codes",
        "execution_double_codes",
        "execution_full_score",
        "execution_full_candidate",
        "execution_full_kept",
        "execution_segment_idx",
    ]
    fieldnames = list(source_fieldnames)
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)

    output_rows: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    width_counts: Counter[int] = Counter()
    hit_count = 0
    settled_count = 0
    for source_row in source_rows:
        row = dict(source_row)
        match_idx = int(safe_float(row.get("match_idx")))
        execution = executions.get(match_idx, RowExecution([], "skip_missing_decision", ["missing_v4_2_decision"], [], 0.0, False, False))
        decision_row = decisions.get(match_idx, {})
        selection_text = "+".join(execution.selection_codes)
        row["shadow_selection_codes"] = selection_text
        row["shadow_primary"] = execution.selection_codes[0] if execution.selection_codes else ""
        row["shadow_arm"] = f"{SHADOW_ARM}_{policy_name}"
        row["shadow_version"] = SHADOW_VERSION
        row["shadow_stop_flag"] = "0" if execution.selection_codes else "1"
        row["execution_policy_version"] = POLICY_VERSION
        row["execution_policy_name"] = policy_name
        row["execution_action"] = execution.action
        row["execution_reasons"] = ";".join(execution.reasons)
        row["execution_source_action"] = decision_row.get("v4_action", "")
        row["execution_recommended_codes"] = decision_row.get("v4_recommended_codes", "")
        row["execution_double_codes"] = "+".join(execution.double_codes)
        row["execution_full_score"] = f"{execution.full_score:.4f}"
        row["execution_full_candidate"] = int(execution.full_candidate)
        row["execution_full_kept"] = int(execution.full_kept)
        row["execution_segment_idx"] = execution.segment_idx or ""
        actual = str(row.get("actual_code") or "")
        if actual in OUTCOME_CODES:
            settled_count += 1
            hit_count += int(actual in execution.selection_codes)
        action_counts[execution.action] += 1
        width_counts[len(execution.selection_codes)] += 1
        output_rows.append(row)

    write_csv(output_csv, output_rows, fieldnames)
    summary = {
        "issue": issue,
        "policy_version": POLICY_VERSION,
        "policy_name": policy_name,
        "late_refresh_mode": late_refresh_mode,
        "full_score_threshold": full_score_threshold,
        "max_full_per_segment": max_full_per_segment,
        "rows": len(output_rows),
        "settled_rows": settled_count,
        "settled_hit_rows": hit_count,
        "settled_hit_rate": round(hit_count / settled_count, 6) if settled_count else None,
        "action_counts": dict(action_counts),
        "width_counts": {str(key): value for key, value in sorted(width_counts.items())},
        "output_csv": str(output_csv),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(summary), encoding="utf-8")
    return output_csv, report_path, summary


def render_report(summary: dict[str, Any]) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return f"""# v4.2.0000 Execution Policy

Generated: {generated}

## Summary

```json
{json.dumps(summary, ensure_ascii=False, indent=2)}
```

## Policy

- `buy` rows execute their v4.2 selection directly.
- `wait_late_refresh` rows execute only when `late_refresh_mode=proxy`; in
  strict mode they remain no-buy until a real late refresh artifact exists.
- Full-cover rows are scored by layer-conflict value, q/SP attraction, and the
  value of the third code after double compression.
- Full cover is capped per rolling segment. Over-cap full candidates are
  downgraded to the best double when possible.
- Low-value layer conflicts are skipped instead of forcing a tight double.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--source-structured-csv", type=Path, required=True)
    parser.add_argument("--decision-csv", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--late-refresh-mode", choices=("skip", "proxy"), default="skip")
    parser.add_argument("--full-score-threshold", type=float, default=1.40)
    parser.add_argument("--max-full-per-segment", type=int, default=1)
    parser.add_argument("--window-hours", type=float, default=12.0)
    parser.add_argument("--extend-hours", default="18,24,36")
    parser.add_argument("--min-matches", type=int, default=6)
    parser.add_argument("--max-matches", type=int, default=24)
    parser.add_argument("--policy-name", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    policy_name = args.policy_name or f"late_{args.late_refresh_mode}_fullcap{args.max_full_per_segment}"
    output_csv, report_path, summary = apply_policy(
        issue=args.issue,
        source_csv=args.source_structured_csv,
        decision_csv=args.decision_csv,
        db_path=args.db,
        output_csv=args.output_csv,
        report_path=args.report,
        late_refresh_mode=args.late_refresh_mode,
        full_score_threshold=args.full_score_threshold,
        max_full_per_segment=args.max_full_per_segment,
        window_hours=args.window_hours,
        extend_hours=args.extend_hours,
        min_matches=args.min_matches,
        max_matches=args.max_matches,
        policy_name=policy_name,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {output_csv}")
        print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
