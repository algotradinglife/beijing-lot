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
OUTCOME_LABELS = {"3": "胜", "1": "平", "0": "负"}
SP_COLUMN_BY_CODE = {"3": "sp_3", "1": "sp_1", "0": "sp_0"}
Q_COLUMN_BY_CODE = {"3": "q_3", "1": "q_1", "0": "q_0"}
LIVE_SP_COLUMN_BY_CODE = {"3": "sp_home", "1": "sp_draw", "0": "sp_away"}
MATERIAL_SP_RATIO = 1.45
SEVERE_SP_RATIO = 2.0
TOPLINE_DRIFT_SP_RATIO = 1.30
TOPLINE_DRIFT_Q_MIN = 1.20
TOPLINE_DRIFT_P_MIN = 0.30
TOPLINE_DRIFT_BLEND_GAP_MAX = 0.03
TOPLINE_DRIFT_MARKET_WEAKEN_EPS = 0.01
MARKET_BLEND_BASE_WEIGHT = 0.30
MARKET_BLEND_SEVERE_WEIGHT = 0.45
TIGHT_DENSE_ANCHOR_SP_RATIO = 1.40
TIGHT_DENSE_ANCHOR_MARKET_GAIN = 0.025
TIGHT_DENSE_ANCHOR_P_GAP = 0.06
PENDING_DRAW_RESCUE_P_MIN = 0.28
PENDING_DRAW_RESCUE_SP_MIN = 2.60
PENDING_DRAW_RESCUE_SP_MAX = 5.00
EXTREME_SOURCE_Q_MIN = 2.50
EXTREME_SOURCE_Q_COLLAPSE_MAX = 1.05
EXTREME_SOURCE_Q_REPRICE_RATIO = 2.00
EXTREME_SOURCE_Q_SECOND_P_MIN = 0.25
POLICY_VERSION = "v4.2.0005_execution_policy_2026-07-07_extreme_source_q_guard"
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


@dataclass(frozen=True)
class ExecutionSpSnapshot:
    sp: dict[str, float]
    snapshot_ts: str
    source: str


@dataclass(frozen=True)
class PreparedExecutionRow:
    row: dict[str, Any]
    repricing_reasons: tuple[str, ...]
    missing_execution_sp: bool


def execution_unlock_state(source_action: str, execution: RowExecution) -> str:
    if source_action != "wait_late_refresh":
        return "not_applicable"
    if execution.action == "skip_wait_late_refresh":
        return "waiting_late_refresh"
    if execution.selection_codes:
        return "unlocked_after_late_refresh"
    return "blocked_after_late_refresh"


def safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def fmt_float(value: float | None, *, digits: int = 4) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.{digits}f}"


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


def order_codes_with_primary(codes: list[str], primary: str) -> list[str]:
    if primary not in OUTCOME_CODES:
        return unique_codes(codes)
    return unique_codes([primary, *codes])


def selection_type_from_codes(codes: list[str]) -> str:
    if not codes:
        return "no-buy"
    if len(codes) == 1:
        return "single"
    if len(codes) == 2:
        return "double"
    return "full"


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


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not table_exists(conn, name):
        return set()
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def complete_sp(sp: dict[str, float]) -> bool:
    return all(sp.get(code, 0.0) > 0 for code in OUTCOME_CODES)


def load_execution_sp_snapshots(db_path: Path, issue: str) -> dict[int, ExecutionSpSnapshot]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        out: dict[int, ExecutionSpSnapshot] = {}
        if table_exists(conn, "live_sp_snapshots"):
            rows = conn.execute(
                """
                SELECT *
                FROM (
                    SELECT
                      l.row_idx AS match_idx,
                      l.sp_home,
                      l.sp_draw,
                      l.sp_away,
                      l.source_updatetime,
                      l.fetched_at,
                      ROW_NUMBER() OVER (
                        PARTITION BY l.issue, l.row_idx
                        ORDER BY COALESCE(l.source_updatetime, '') DESC, l.fetched_at DESC
                      ) AS rn
                    FROM live_sp_snapshots l
                    WHERE l.issue=?
                      AND l.playid=34
                      AND l.sp_home IS NOT NULL
                      AND l.sp_draw IS NOT NULL
                      AND l.sp_away IS NOT NULL
                )
                WHERE rn=1
                """,
                (issue,),
            ).fetchall()
            for row in rows:
                sp = {code: safe_float(row[LIVE_SP_COLUMN_BY_CODE[code]]) for code in OUTCOME_CODES}
                if complete_sp(sp):
                    out[int(row["match_idx"])] = ExecutionSpSnapshot(
                        sp=sp,
                        snapshot_ts=str(row["source_updatetime"] or row["fetched_at"] or ""),
                        source="live_sp_snapshots",
                    )
        match_columns = table_columns(conn, "matches")
        if {"match_idx", "sp_home", "sp_draw", "sp_away"}.issubset(match_columns):
            fetched_expr = "fetched_at" if "fetched_at" in match_columns else "'' AS fetched_at"
            rows = conn.execute(
                f"""
                SELECT match_idx, sp_home, sp_draw, sp_away, {fetched_expr}
                FROM matches
                WHERE issue=?
                  AND sp_home IS NOT NULL
                  AND sp_draw IS NOT NULL
                  AND sp_away IS NOT NULL
                """,
                (issue,),
            ).fetchall()
            for row in rows:
                match_idx = int(row["match_idx"])
                if match_idx in out:
                    continue
                sp = {code: safe_float(row[LIVE_SP_COLUMN_BY_CODE[code]]) for code in OUTCOME_CODES}
                if complete_sp(sp):
                    out[match_idx] = ExecutionSpSnapshot(
                        sp=sp,
                        snapshot_ts=str(row["fetched_at"] or ""),
                        source="matches_current_sp",
                    )
        return out
    finally:
        conn.close()


def with_source_execution_sp_fields(
    source_row: dict[str, Any],
    snapshot: ExecutionSpSnapshot | None,
    *,
    require_execution_sp: bool,
) -> PreparedExecutionRow:
    row = dict(source_row)
    reasons: list[str] = []
    missing_execution_sp = bool(require_execution_sp and snapshot is None)
    max_ratio = 1.0
    repriced = False
    execution_q: dict[str, float] = {}

    for code in OUTCOME_CODES:
        source_sp = safe_float(source_row.get(SP_COLUMN_BY_CODE[code]))
        source_q = safe_float(source_row.get(Q_COLUMN_BY_CODE[code]))
        execution_sp = snapshot.sp[code] if snapshot else source_sp
        probability = safe_float(source_row.get(f"p_{code}"))
        q_value = probability * execution_sp if probability > 0 and execution_sp > 0 else 0.0
        execution_q[code] = q_value

        if snapshot and source_sp > 0 and execution_sp > 0:
            ratio = max(source_sp / execution_sp, execution_sp / source_sp)
            max_ratio = max(max_ratio, ratio)
            if ratio >= MATERIAL_SP_RATIO:
                repriced = True

        row[f"source_sp_{code}"] = fmt_float(source_sp)
        row[f"source_q_{code}"] = fmt_float(source_q)
        row[f"execution_sp_{code}"] = fmt_float(execution_sp) if snapshot or not require_execution_sp else ""
        row[f"execution_q_{code}"] = fmt_float(q_value) if snapshot or not require_execution_sp else ""
        if snapshot:
            row[SP_COLUMN_BY_CODE[code]] = fmt_float(execution_sp)
            row[Q_COLUMN_BY_CODE[code]] = fmt_float(q_value)

    if snapshot:
        q_top = max(execution_q.items(), key=lambda item: item[1])[0]
        row["q_top"] = q_top
        row["max_q"] = fmt_float(execution_q[q_top])
    row["execution_sp_source"] = snapshot.source if snapshot else ("missing_trusted_sp" if require_execution_sp else "source_artifact")
    row["execution_sp_snapshot_ts"] = snapshot.snapshot_ts if snapshot else ""
    row["execution_sp_repriced"] = int(repriced)
    row["execution_sp_reprice_ratio_max"] = fmt_float(max_ratio)
    row["execution_sp_missing"] = int(missing_execution_sp)
    if repriced:
        reasons.append("sp_repriced_after_late_refresh")
    if max_ratio >= SEVERE_SP_RATIO:
        reasons.append("severe_sp_repriced_after_late_refresh")
    if missing_execution_sp:
        reasons.append("missing_execution_sp_after_late_refresh")
    return PreparedExecutionRow(row=row, repricing_reasons=tuple(reasons), missing_execution_sp=missing_execution_sp)


def prepare_execution_rows(
    source_rows: list[dict[str, str]],
    *,
    db_path: Path,
    issue: str,
    execution_sp_mode: str,
) -> dict[int, PreparedExecutionRow]:
    require_execution_sp = execution_sp_mode == "latest_trusted"
    snapshots = load_execution_sp_snapshots(db_path, issue) if require_execution_sp else {}
    out: dict[int, PreparedExecutionRow] = {}
    for source_row in source_rows:
        if str(source_row.get("issue") or issue) != issue:
            continue
        match_idx = int(safe_float(source_row.get("match_idx")))
        out[match_idx] = with_source_execution_sp_fields(
            source_row,
            snapshots.get(match_idx),
            require_execution_sp=require_execution_sp,
        )
    return out


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


def top_row_code(row: dict[str, Any], prefix: str, field: str) -> tuple[str | None, dict[str, float]]:
    values = {code: safe_float(row.get(f"{prefix}{field}_{code}")) for code in OUTCOME_CODES}
    usable = [(code, value) for code, value in values.items() if value > 0]
    return (max(usable, key=lambda item: item[1])[0] if usable else None, values)


def probability_top_from_row(row: dict[str, Any]) -> str | None:
    code, _values = top_row_code(row, "", "p")
    if code:
        return code
    fallback = str(row.get("prob_top") or "")
    return fallback if fallback in OUTCOME_CODES else None


def execution_q_top_from_row(row: dict[str, Any]) -> tuple[str | None, dict[str, float]]:
    code, values = top_row_code(row, "execution_", "q")
    if code:
        return code, values
    return top_row_code(row, "", "q")


def source_q_top_from_row(row: dict[str, Any]) -> tuple[str | None, dict[str, float]]:
    code, values = top_row_code(row, "source_", "q")
    if code:
        return code, values
    return top_row_code(row, "", "q")


def execution_primary_code(source_row: dict[str, Any], execution: RowExecution) -> tuple[str, str]:
    selected = unique_codes(execution.selection_codes)
    if not selected:
        return "", "no_selection"
    if len(selected) == 1:
        return selected[0], "single_selection"
    q_top, _q_values = execution_q_top_from_row(source_row)
    if q_top in selected:
        return q_top, "execution_q_top"
    prob_top = probability_top_from_row(source_row)
    if prob_top in selected:
        return prob_top, "probability_top"
    return selected[0], "execution_selection_order"


def outcome_text(code: str, row: dict[str, Any]) -> str:
    label = OUTCOME_LABELS.get(code, code)
    if code == "3" and row.get("home"):
        return f"{label}({row['home']})"
    if code == "0" and row.get("away"):
        return f"{label}({row['away']})"
    return label


def execution_judgment(row: dict[str, Any], primary: str, support_codes: list[str]) -> str:
    if primary not in OUTCOME_CODES:
        return "停"
    primary_text = outcome_text(primary, row)
    if not support_codes:
        return primary_text
    support_text = "+".join(outcome_text(code, row) for code in support_codes)
    return f"{primary_text}为押，保{support_text}"


def sp_values_from_row(row: dict[str, Any], prefix: str) -> dict[str, float]:
    values = {code: safe_float(row.get(f"{prefix}sp_{code}")) for code in OUTCOME_CODES}
    if any(value > 0 for value in values.values()):
        return values
    return {code: safe_float(row.get(f"sp_{code}")) for code in OUTCOME_CODES}


def normalized_market_probabilities(sp_values: dict[str, float]) -> dict[str, float]:
    inverse = {code: (1.0 / sp if sp > 0 else 0.0) for code, sp in sp_values.items()}
    total = sum(inverse.values())
    if total <= 0:
        return {code: 0.0 for code in OUTCOME_CODES}
    return {code: value / total for code, value in inverse.items()}


def market_probabilities_from_row(row: dict[str, Any], prefix: str) -> dict[str, float]:
    return normalized_market_probabilities(sp_values_from_row(row, prefix))


def ratio(a: float, b: float) -> float:
    if a <= 0 or b <= 0:
        return 1.0
    high = max(a, b)
    low = min(a, b)
    return high / low if low > 0 else 1.0


def late_market_blend_weight(row: dict[str, Any]) -> float:
    if safe_float(row.get("execution_sp_reprice_ratio_max"), default=1.0) >= SEVERE_SP_RATIO:
        return MARKET_BLEND_SEVERE_WEIGHT
    return MARKET_BLEND_BASE_WEIGHT


def late_blended_probabilities(row: dict[str, Any]) -> dict[str, float]:
    market_p = market_probabilities_from_row(row, "execution_")
    weight = late_market_blend_weight(row)
    out: dict[str, float] = {}
    for code in OUTCOME_CODES:
        model_p = safe_float(row.get(f"p_{code}"))
        implied_p = market_p.get(code, 0.0)
        if implied_p <= 0:
            out[code] = model_p
        else:
            out[code] = (1.0 - weight) * model_p + weight * implied_p
    return out


def should_probability_anchor_compression(source_row: dict[str, Any], decision_row: dict[str, Any]) -> bool:
    source_action = str(decision_row.get("v4_action") or "")
    if source_action not in {"wait_late_refresh", "full_cover_or_skip"}:
        return False
    return safe_float(source_row.get("execution_sp_reprice_ratio_max"), default=1.0) >= SEVERE_SP_RATIO


def should_tight_dense_probability_anchor(source_row: dict[str, Any], decision_row: dict[str, Any]) -> bool:
    if str(decision_row.get("v4_action") or "") != "full_cover_or_skip":
        return False
    full_reasons = set(str(decision_row.get("v4_full_cover_reasons") or "").split(";"))
    if "tight_dense_requires_full_or_skip" not in full_reasons:
        return False
    if safe_float(source_row.get("execution_sp_reprice_ratio_max"), default=1.0) < TIGHT_DENSE_ANCHOR_SP_RATIO:
        return False
    anchor = probability_top_from_row(source_row)
    if not anchor:
        return False
    q_top, _q_values = execution_q_top_from_row(source_row)
    if anchor == q_top:
        return True
    source_market_p = market_probabilities_from_row(source_row, "source_")
    execution_market_p = market_probabilities_from_row(source_row, "execution_")
    if execution_market_p.get(anchor, 0.0) >= source_market_p.get(anchor, 0.0) + TIGHT_DENSE_ANCHOR_MARKET_GAIN:
        return True
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    anchor_p = safe_float(source_row.get(f"p_{anchor}"))
    other_p = max((safe_float(source_row.get(f"p_{code}")) for code in recommended if code != anchor), default=0.0)
    return anchor_p - other_p >= TIGHT_DENSE_ANCHOR_P_GAP


def second_leg_score(source_row: dict[str, Any], decision_row: dict[str, Any], code: str) -> float:
    metrics = code_metrics(source_row)
    values = metrics[code]
    mandatory = set(parse_codes(decision_row.get("v4_mandatory_codes")))
    protected = set(parse_codes(decision_row.get("v4_protected_codes")))
    team_codes = set(parse_codes(decision_row.get("v4_team_strength_codes")))
    semantic_draw = str(decision_row.get("v4_semantic_draw") or "none")
    score = 0.60 * values["q"] + 0.20 * values["p"]
    if code in team_codes and safe_float(decision_row.get("v4_team_strength_confidence")) >= 0.85:
        score += 0.80
    if code in mandatory:
        score += 0.30
    if code in protected:
        score += 0.30
    if code == "1":
        if semantic_draw == "explicit_draw":
            score += 0.35
        elif semantic_draw == "balanced":
            score += 0.20
    return score


def probability_anchor_double_codes(source_row: dict[str, Any], decision_row: dict[str, Any]) -> list[str]:
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    should_anchor = should_probability_anchor_compression(source_row, decision_row) or should_tight_dense_probability_anchor(
        source_row,
        decision_row,
    )
    if len(recommended) < 3 or not should_anchor:
        return []
    anchor = probability_top_from_row(source_row)
    if anchor not in recommended:
        return []
    remaining = [code for code in recommended if code != anchor]
    if not remaining:
        return [anchor]
    second = max(remaining, key=lambda code: second_leg_score(source_row, decision_row, code))
    return [anchor, second]


def candidate_pool_has_pending_draw(decision_row: dict[str, Any]) -> bool:
    candidates = safe_json(decision_row.get("v4_candidate_pool_json"), [])
    if not isinstance(candidates, list):
        return False
    for item in candidates:
        if not isinstance(item, dict) or str(item.get("code") or "") != "1":
            continue
        signals = set(str(signal) for signal in item.get("signals") or [])
        pending_signals = set(str(signal) for signal in item.get("pending_signals") or [])
        if "late_refresh_neighbor_draw" in signals or "late_refresh_neighbor_draw" in pending_signals:
            return True
    return False


def late_refresh_pending_draw_double_codes(source_row: dict[str, Any], decision_row: dict[str, Any]) -> list[str]:
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    if str(decision_row.get("v4_action") or "") != "wait_late_refresh":
        return []
    if len(recommended) != 2 or "1" in recommended:
        return []
    if safe_float(source_row.get("execution_sp_reprice_ratio_max"), default=1.0) < SEVERE_SP_RATIO:
        return []
    merge_flags = set(str(decision_row.get("v4_merge_flags") or "").split(";"))
    if "skip_unbacked_high_q_draw" not in merge_flags:
        return []
    if not candidate_pool_has_pending_draw(decision_row):
        return []
    if safe_float(source_row.get("p_1")) < PENDING_DRAW_RESCUE_P_MIN:
        return []
    draw_sp = safe_float(source_row.get("execution_sp_1") or source_row.get("sp_1"))
    if not (PENDING_DRAW_RESCUE_SP_MIN <= draw_sp <= PENDING_DRAW_RESCUE_SP_MAX):
        return []
    anchor = probability_top_from_row(source_row)
    keep = anchor if anchor in recommended else max(recommended, key=lambda code: safe_float(source_row.get(f"p_{code}")))
    return [keep, "1"]


def extreme_source_q_guard_double_codes(source_row: dict[str, Any], decision_row: dict[str, Any]) -> list[str]:
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    if not recommended or len(recommended) > 2:
        return []
    if str(decision_row.get("v4_action") or "") != "wait_late_refresh":
        return []
    if safe_float(source_row.get("execution_sp_reprice_ratio_max"), default=1.0) < SEVERE_SP_RATIO:
        return []
    prob_top = probability_top_from_row(source_row)
    if not prob_top or prob_top in recommended:
        return []
    source_q_top, source_q_values = source_q_top_from_row(source_row)
    execution_q_top, execution_q_values = execution_q_top_from_row(source_row)
    if not source_q_top or source_q_top not in recommended:
        return []
    if not execution_q_top or execution_q_top == source_q_top:
        return []

    source_q = source_q_values.get(source_q_top, 0.0)
    execution_q_for_source_top = execution_q_values.get(source_q_top, 0.0)
    source_sp = sp_values_from_row(source_row, "source_").get(source_q_top, 0.0)
    execution_sp = sp_values_from_row(source_row, "execution_").get(source_q_top, 0.0)
    source_reprice_ratio = ratio(source_sp, execution_sp)
    if source_q < EXTREME_SOURCE_Q_MIN and source_reprice_ratio < EXTREME_SOURCE_Q_REPRICE_RATIO:
        return []
    if execution_q_for_source_top > EXTREME_SOURCE_Q_COLLAPSE_MAX:
        return []

    prob_top_p = safe_float(source_row.get(f"p_{prob_top}"))
    source_q_top_p = safe_float(source_row.get(f"p_{source_q_top}"))
    if source_q_top_p >= prob_top_p:
        return []

    second_scores: dict[str, float] = {}
    for code in unique_codes([execution_q_top, *recommended]):
        if code == prob_top:
            continue
        probability = safe_float(source_row.get(f"p_{code}"))
        if probability < EXTREME_SOURCE_Q_SECOND_P_MIN:
            continue
        execution_q = execution_q_values.get(code, 0.0)
        score = 2.0 * probability + 0.35 * execution_q
        if code == execution_q_top:
            score += 0.45
        if code in recommended and code != source_q_top:
            score += 0.10
        if code == source_q_top:
            score -= 0.30
        second_scores[code] = score
    if not second_scores:
        return [prob_top]
    second = max(second_scores.items(), key=lambda item: item[1])[0]
    return unique_codes([prob_top, second])


def late_repriced_conflict_skip_reasons(
    source_row: dict[str, Any],
    source_action: str,
    selection_codes: list[str],
) -> list[str]:
    if source_action != "wait_late_refresh":
        return []
    if safe_float(source_row.get("execution_sp_reprice_ratio_max"), default=1.0) < SEVERE_SP_RATIO:
        return []
    prob_top = probability_top_from_row(source_row)
    if prob_top and prob_top not in selection_codes:
        return ["late_repriced_conflict_missing_prob_top", f"missing_prob_top_{prob_top}"]
    return []


def late_q_top_drift_skip_reasons(source_row: dict[str, Any], selection_codes: list[str]) -> list[str]:
    if safe_float(source_row.get("execution_sp_reprice_ratio_max"), default=1.0) < TOPLINE_DRIFT_SP_RATIO:
        return []
    q_top, q_values = execution_q_top_from_row(source_row)
    source_q_top, _source_q_values = source_q_top_from_row(source_row)
    if not q_top or q_top in selection_codes or q_top == source_q_top:
        return []
    q_value = q_values.get(q_top, 0.0)
    blended_p = late_blended_probabilities(source_row)
    probability = blended_p.get(q_top, safe_float(source_row.get(f"p_{q_top}")))
    selected_probability = max((blended_p.get(code, 0.0) for code in selection_codes), default=0.0)
    source_market_p = market_probabilities_from_row(source_row, "source_")
    execution_market_p = market_probabilities_from_row(source_row, "execution_")
    market_delta = execution_market_p.get(q_top, 0.0) - source_market_p.get(q_top, 0.0)
    market_weakened = market_delta < -TOPLINE_DRIFT_MARKET_WEAKEN_EPS
    probability_supported = probability + TOPLINE_DRIFT_BLEND_GAP_MAX >= selected_probability
    if (
        q_value >= TOPLINE_DRIFT_Q_MIN
        and probability >= TOPLINE_DRIFT_P_MIN
        and probability_supported
        and not market_weakened
    ):
        return [
            "late_q_top_drift_uncovered",
            f"late_q_top_drift_{source_q_top or 'none'}_to_{q_top}",
            f"late_blended_p_{q_top}_{probability:.4f}",
        ]
    return []


def late_q_top_drift_watch_reasons(source_row: dict[str, Any], selection_codes: list[str]) -> list[str]:
    if safe_float(source_row.get("execution_sp_reprice_ratio_max"), default=1.0) < TOPLINE_DRIFT_SP_RATIO:
        return []
    q_top, q_values = execution_q_top_from_row(source_row)
    source_q_top, _source_q_values = source_q_top_from_row(source_row)
    if not q_top or q_top in selection_codes or q_top == source_q_top:
        return []
    q_value = q_values.get(q_top, 0.0)
    if q_value < TOPLINE_DRIFT_Q_MIN:
        return []
    blended_p = late_blended_probabilities(source_row)
    probability = blended_p.get(q_top, safe_float(source_row.get(f"p_{q_top}")))
    selected_probability = max((blended_p.get(code, 0.0) for code in selection_codes), default=0.0)
    source_market_p = market_probabilities_from_row(source_row, "source_")
    execution_market_p = market_probabilities_from_row(source_row, "execution_")
    market_delta = execution_market_p.get(q_top, 0.0) - source_market_p.get(q_top, 0.0)
    reasons = [
        "value_only_sp_drift",
        f"late_q_top_drift_watch_{source_q_top or 'none'}_to_{q_top}",
        f"late_blended_p_{q_top}_{probability:.4f}",
    ]
    if market_delta < -TOPLINE_DRIFT_MARKET_WEAKEN_EPS:
        reasons.append(f"market_implied_p_weakened_{q_top}")
    if probability + TOPLINE_DRIFT_BLEND_GAP_MAX < selected_probability:
        reasons.append(f"late_blended_p_below_selected_{q_top}")
    return reasons


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


def compressed_double_codes(
    source_row: dict[str, Any],
    decision_row: dict[str, Any],
    *,
    probability_anchor: bool = True,
) -> list[str]:
    recommended = parse_codes(decision_row.get("v4_recommended_codes"))
    if len(recommended) <= 2:
        pending_draw = late_refresh_pending_draw_double_codes(source_row, decision_row)
        if pending_draw:
            return pending_draw
        return recommended
    if probability_anchor:
        anchored = probability_anchor_double_codes(source_row, decision_row)
        if anchored:
            return anchored
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
    scoring_double_codes = compressed_double_codes(source_row, decision_row, probability_anchor=False)
    full_score = full_cover_score(source_row, decision_row, scoring_double_codes)
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
        extreme_guard = extreme_source_q_guard_double_codes(source_row, decision_row)
        if extreme_guard:
            return RowExecution(
                extreme_guard,
                "execute_double" if len(extreme_guard) == 2 else "execute_single",
                [
                    "late_refresh_proxy",
                    "extreme_source_q_repriced_probability_guard",
                    f"restored_probability_top_{extreme_guard[0]}",
                ],
                extreme_guard,
                full_score,
                False,
                False,
            )
        drift_reasons = late_q_top_drift_skip_reasons(source_row, recommended)
        if source_action != "wait_late_refresh" and drift_reasons:
            return RowExecution([], "skip_late_q_top_drift", drift_reasons, double_codes, full_score, False, False)
        reason = "late_refresh_proxy" if source_action == "wait_late_refresh" else "direct_buy"
        reasons = [reason]
        if source_action == "wait_late_refresh" and double_codes != recommended:
            reasons.append("late_refresh_pending_draw_rescue")
        if source_action != "wait_late_refresh":
            reasons.extend(late_q_top_drift_watch_reasons(source_row, recommended))
        selection_codes = double_codes or recommended
        return RowExecution(selection_codes, "execute_double" if len(selection_codes) == 2 else "execute_single", reasons, double_codes, full_score, False, False)
    if full_candidate:
        return RowExecution(recommended, "execute_full_cover", ["full_score_above_threshold"], double_codes, full_score, True, True)
    if conflict_full:
        if double_codes:
            skip_reasons = late_repriced_conflict_skip_reasons(source_row, source_action, double_codes)
            if skip_reasons:
                return RowExecution(
                    [],
                    "skip_late_repriced_conflict_missing_prob_top",
                    skip_reasons,
                    double_codes,
                    full_score,
                    False,
                    False,
                )
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


def annotate_execution_segments(
    executions: dict[int, RowExecution],
    segment_lookup: dict[int, int],
) -> None:
    for match_idx, execution in executions.items():
        execution.segment_idx = segment_lookup.get(match_idx)


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
    execution_sp_mode: str = "source",
    shadow_arm_prefix: str = SHADOW_ARM,
) -> tuple[Path, Path, dict[str, Any]]:
    source_rows, source_fieldnames = load_csv(source_csv)
    decisions = load_decisions(decision_csv)
    prepared_rows = prepare_execution_rows(
        source_rows,
        db_path=db_path,
        issue=issue,
        execution_sp_mode=execution_sp_mode,
    )
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
        prepared = prepared_rows.get(match_idx)
        execution_source_row = prepared.row if prepared else source_row
        decision_row = decisions.get(match_idx)
        if not decision_row:
            executions[match_idx] = RowExecution([], "skip_missing_decision", ["missing_v4_2_decision"], [], 0.0, False, False)
            continue
        if late_refresh_mode == "proxy" and prepared and prepared.missing_execution_sp:
            executions[match_idx] = RowExecution(
                [],
                "skip_missing_execution_sp",
                ["missing_execution_sp_after_late_refresh"],
                [],
                0.0,
                False,
                False,
            )
            continue
        executions[match_idx] = evaluate_row_policy(
            execution_source_row,
            decision_row,
            late_refresh_mode=late_refresh_mode,
            full_score_threshold=full_score_threshold,
        )
        if prepared and prepared.repricing_reasons:
            executions[match_idx].reasons = list(prepared.repricing_reasons) + executions[match_idx].reasons
    annotate_execution_segments(executions, segment_lookup)

    extra_fields = [
        "q_top",
        "max_q",
        "shadow_selection_codes",
        "shadow_primary",
        "shadow_judgment",
        "shadow_primary_hit",
        "shadow_coverage_hit",
        "shadow_arm",
        "shadow_version",
        "shadow_stop_flag",
        "selection_type",
        "source_sp_3",
        "source_sp_1",
        "source_sp_0",
        "source_q_3",
        "source_q_1",
        "source_q_0",
        "execution_sp_3",
        "execution_sp_1",
        "execution_sp_0",
        "execution_q_3",
        "execution_q_1",
        "execution_q_0",
        "execution_sp_source",
        "execution_sp_snapshot_ts",
        "execution_sp_repriced",
        "execution_sp_reprice_ratio_max",
        "execution_sp_missing",
        "execution_policy_version",
        "execution_policy_name",
        "execution_action",
        "execution_reasons",
        "execution_source_action",
        "execution_recommended_codes",
        "execution_double_codes",
        "execution_primary_code",
        "execution_primary_source",
        "execution_support_codes",
        "execution_full_score",
        "execution_full_candidate",
        "execution_full_kept",
        "execution_segment_idx",
        "execution_unlock_state",
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
        match_idx = int(safe_float(source_row.get("match_idx")))
        row = dict(prepared_rows.get(match_idx).row if match_idx in prepared_rows else source_row)
        execution = executions.get(match_idx, RowExecution([], "skip_missing_decision", ["missing_v4_2_decision"], [], 0.0, False, False))
        decision_row = decisions.get(match_idx, {})
        primary, primary_source = execution_primary_code(row, execution)
        display_codes = order_codes_with_primary(execution.selection_codes, primary)
        support_codes = [code for code in display_codes if code != primary]
        selection_text = "+".join(display_codes)
        row["shadow_selection_codes"] = selection_text
        row["shadow_primary"] = primary
        row["shadow_judgment"] = execution_judgment(row, primary, support_codes)
        row["shadow_arm"] = f"{shadow_arm_prefix}_{policy_name}"
        row["shadow_version"] = SHADOW_VERSION
        row["shadow_stop_flag"] = "0" if execution.selection_codes else "1"
        row["selection_type"] = selection_type_from_codes(display_codes)
        row["execution_policy_version"] = POLICY_VERSION
        row["execution_policy_name"] = policy_name
        row["execution_action"] = execution.action
        row["execution_reasons"] = ";".join(execution.reasons)
        row["execution_source_action"] = decision_row.get("v4_action", "")
        row["execution_recommended_codes"] = decision_row.get("v4_recommended_codes", "")
        row["execution_double_codes"] = "+".join(execution.double_codes)
        row["execution_primary_code"] = primary
        row["execution_primary_source"] = primary_source
        row["execution_support_codes"] = "+".join(support_codes)
        row["execution_full_score"] = f"{execution.full_score:.4f}"
        row["execution_full_candidate"] = int(execution.full_candidate)
        row["execution_full_kept"] = int(execution.full_kept)
        row["execution_segment_idx"] = execution.segment_idx or ""
        row["execution_unlock_state"] = execution_unlock_state(str(decision_row.get("v4_action") or ""), execution)
        actual = str(row.get("actual_code") or "")
        if actual in OUTCOME_CODES:
            row["shadow_primary_hit"] = int(actual == primary) if primary else ""
            row["shadow_coverage_hit"] = int(actual in display_codes)
            settled_count += 1
            hit_count += int(actual in display_codes)
        action_counts[execution.action] += 1
        width_counts[len(execution.selection_codes)] += 1
        output_rows.append(row)

    write_csv(output_csv, output_rows, fieldnames)
    summary = {
        "issue": issue,
        "policy_version": POLICY_VERSION,
        "policy_name": policy_name,
        "shadow_arm": f"{shadow_arm_prefix}_{policy_name}",
        "late_refresh_mode": late_refresh_mode,
        "execution_sp_mode": execution_sp_mode,
        "full_score_threshold": full_score_threshold,
        "max_full_per_segment": max_full_per_segment,
        "segment_full_cap_applied": False,
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
  value of the third code after baseline double compression, so late probability
  anchoring does not change per-row full-cover candidacy.
- Rolling segment ids are attached for downstream stake optimization, but this
  layer does not cap, skip, or downgrade full-cover candidates by segment.
- Late-proxy rows stop instead of forcing a tight double when severe SP
  repricing cannot be compressed while keeping the probability top.
- Severely repriced full-cover rows compress by anchoring probability top first;
  the remaining two outcomes compete for the second slot.
- Tight-dense full-cover rows with material SP refresh keep a model probability
  top when refreshed q, market-implied probability, or model gap supports it.
- Severe late-refresh rows can restore a pending draw when the source chain had
  skipped an unbacked high-q draw and refreshed draw SP becomes sane.
- Direct-buy rows stop when refreshed q-top drifts to a material uncovered
  outcome only if market-blended probability also supports that uncovered
  outcome. Payout-only SP drift is marked as `value_only_sp_drift` and remains
  executable.
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
    parser.add_argument("--execution-sp-mode", choices=("source", "latest_trusted"), default="")
    parser.add_argument("--full-score-threshold", type=float, default=1.40)
    parser.add_argument("--max-full-per-segment", type=int, default=1)
    parser.add_argument("--window-hours", type=float, default=12.0)
    parser.add_argument("--extend-hours", default="18,24,36")
    parser.add_argument("--min-matches", type=int, default=6)
    parser.add_argument("--max-matches", type=int, default=24)
    parser.add_argument("--policy-name", default="")
    parser.add_argument("--shadow-arm-prefix", default=SHADOW_ARM)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    policy_name = args.policy_name or f"late_{args.late_refresh_mode}_fullcap{args.max_full_per_segment}"
    execution_sp_mode = args.execution_sp_mode or ("latest_trusted" if args.late_refresh_mode == "proxy" else "source")
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
        execution_sp_mode=execution_sp_mode,
        shadow_arm_prefix=args.shadow_arm_prefix,
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Wrote {output_csv}")
        print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
