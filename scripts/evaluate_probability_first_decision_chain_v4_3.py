#!/usr/bin/env python3
"""Backtest a probability-first decision-chain candidate for v4.3."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_structured_decision_chain_shadow import (  # noqa: E402
    OUTCOME_LABEL,
    OUTCOME_ORDER,
    leg_profit,
    result_rows,
    safe_float,
    structured_decision_for_payload,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_REPORT = PROJECT_ROOT / "docs/research/probability_first_decision_chain_v4_3_backtest_2026-07-07.md"
DEFAULT_CSV = PROJECT_ROOT / "docs/research/probability_first_decision_chain_v4_3_backtest_2026-07-07.csv"
DEFAULT_V4_2_SHADOW_DIR = PROJECT_ROOT / "results/structured_decision_chain_shadow"
VERSION = "v4.3.0000_probability_first_2026-07-07"
SOURCE_EURO_ANOMALY_RATIO = 3.0
SOURCE_LATEST_ANOMALY_RATIO = 2.0
Q_PROTECTION_MIN = 1.05
Q_STRONG_PROTECTION_MIN = 1.18
PROTECTION_P_MIN = 0.24
RUNNER_P_MIN = 0.285
RUNNER_CLOSE_GAP = 0.075
RUNNER_SOFT_GAP = 0.105


@dataclass(frozen=True)
class SnapshotRow:
    issue: str
    match_idx: int
    league: str
    home: str
    away: str
    handicap_line: float | None
    score: str
    result_code: str | None
    winning_sp: float | None
    result_source: str
    payload: dict[str, Any]
    latest_sp: dict[str, float | None]


@dataclass(frozen=True)
class V43Decision:
    codes: list[str]
    primary: str
    reasons: list[str]
    risk_tags: list[str]
    source_q_top: str
    stable_q_top: str
    prob_top: str
    source_sp_anomaly_codes: list[str]
    q_source: dict[str, float | None]
    q_stable: dict[str, float | None]
    sp_source: dict[str, float | None]
    sp_stable: dict[str, float | None]


def outcome_text(code: str | None) -> str:
    return OUTCOME_LABEL.get(str(code), "-")


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def num(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def md_table(records: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(title for title, _key in columns) + " |"]
    lines.append("| " + " | ".join("---" for _title, _key in columns) + " |")
    for record in records:
        values = []
        for _title, key in columns:
            value = record.get(key, "")
            if isinstance(value, float):
                value = f"{value:.4f}"
            values.append(str(value).replace("\n", " ").replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def parse_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace("/", "+").replace(",", "+").replace(" ", "+").split("+")
    out: list[str] = []
    for code in raw:
        code = str(code)
        if code in OUTCOME_ORDER and code not in out:
            out.append(code)
    return out


def selection_type(codes: list[str]) -> str:
    if not codes:
        return "no-buy"
    if len(codes) == 1:
        return "single"
    if len(codes) == 2:
        return "double"
    return "full"


def complete_triplet(values: dict[str, float | None]) -> bool:
    return all((values.get(code) or 0.0) > 0 for code in OUTCOME_ORDER)


def top_code(values: dict[str, float | None]) -> str:
    usable = [(code, value) for code, value in values.items() if value is not None]
    return max(usable, key=lambda item: float(item[1]))[0] if usable else ""


def ratio(a: float | None, b: float | None) -> float:
    if not a or not b or a <= 0 or b <= 0:
        return 1.0
    return max(a / b, b / a)


def euro_avg_sp_from_payload(payload: dict[str, Any]) -> dict[str, float | None]:
    current_avg = (
        payload.get("market", {})
        .get("odds_consensus", {})
        .get("current_avg", {})
    )
    return {
        "3": safe_float(current_avg.get("home")),
        "1": safe_float(current_avg.get("draw")),
        "0": safe_float(current_avg.get("away")),
    }


def probabilities_from_payload(payload: dict[str, Any]) -> dict[str, float | None]:
    rows = result_rows(payload)
    return {str(row["code"]): safe_float(row.get("probability")) for row in rows}


def source_sp_from_payload(payload: dict[str, Any]) -> dict[str, float | None]:
    sp = payload.get("sp") if isinstance(payload.get("sp"), dict) else {}
    return {code: safe_float(sp.get(code)) for code in OUTCOME_ORDER}


def q_values(probabilities: dict[str, float | None], sp_values: dict[str, float | None]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for code in OUTCOME_ORDER:
        p = probabilities.get(code)
        sp = sp_values.get(code)
        out[code] = p * sp if p is not None and sp is not None else None
    return out


def stable_sp_values(row: SnapshotRow) -> tuple[dict[str, float | None], str]:
    if complete_triplet(row.latest_sp):
        return row.latest_sp, "latest_beidan_sp"
    euro_sp = euro_avg_sp_from_payload(row.payload)
    if complete_triplet(euro_sp):
        return euro_sp, "euro_avg_sp"
    return source_sp_from_payload(row.payload), "source_sp"


def source_sp_anomaly_codes(
    source_sp: dict[str, float | None],
    euro_sp: dict[str, float | None],
    latest_sp: dict[str, float | None],
) -> list[str]:
    out: list[str] = []
    for code in OUTCOME_ORDER:
        source = source_sp.get(code)
        euro = euro_sp.get(code)
        latest = latest_sp.get(code)
        if ratio(source, euro) >= SOURCE_EURO_ANOMALY_RATIO or ratio(source, latest) >= SOURCE_LATEST_ANOMALY_RATIO:
            out.append(code)
    return out


def probability_first_decision(row: SnapshotRow, *, max_codes: int = 2) -> V43Decision:
    probabilities = probabilities_from_payload(row.payload)
    source_sp = source_sp_from_payload(row.payload)
    euro_sp = euro_avg_sp_from_payload(row.payload)
    stable_sp, stable_sp_source = stable_sp_values(row)
    source_q = q_values(probabilities, source_sp)
    stable_q = q_values(probabilities, stable_sp)
    prob_rank = sorted(
        [(code, probabilities.get(code) or 0.0) for code in OUTCOME_ORDER],
        key=lambda item: item[1],
        reverse=True,
    )
    prob_top = prob_rank[0][0] if prob_rank else ""
    source_q_top = top_code(source_q)
    stable_q_top = top_code(stable_q)
    anomaly_codes = source_sp_anomaly_codes(source_sp, euro_sp, row.latest_sp)
    reasons = ["primary_from_probability_top"]
    risk_tags: list[str] = []
    if anomaly_codes:
        risk_tags.append("source_sp_sanity_anomaly")
        for code in anomaly_codes:
            risk_tags.append(f"source_sp_anomaly_{code}")
    if source_q_top and source_q_top != stable_q_top:
        risk_tags.append(f"q_top_stabilized_{source_q_top}_to_{stable_q_top}")

    codes: list[str] = [prob_top] if prob_top in OUTCOME_ORDER else []
    p_top = probabilities.get(prob_top) or 0.0

    second_scores: dict[str, tuple[float, list[str]]] = {}
    for code in OUTCOME_ORDER:
        if code == prob_top:
            continue
        p = probabilities.get(code) or 0.0
        gap = max(0.0, p_top - p)
        stable_q_value = stable_q.get(code) or 0.0
        source_q_value = source_q.get(code) or 0.0
        score = 0.0
        score_reasons: list[str] = []
        if p >= 0.30 and gap <= 0.12:
            score += 2.0
            score_reasons.append("probability_close_runner")
        elif p >= RUNNER_P_MIN and gap <= RUNNER_SOFT_GAP:
            score += 1.45
            score_reasons.append("probability_soft_runner")
        elif p >= PROTECTION_P_MIN and gap <= 0.22:
            score += 0.55
            score_reasons.append("probability_tail_runner")
        if code == stable_q_top and p >= PROTECTION_P_MIN and stable_q_value >= Q_PROTECTION_MIN:
            score += 0.50
            score_reasons.append(f"stable_q_protection_{stable_sp_source}")
            if stable_q_value >= Q_STRONG_PROTECTION_MIN:
                score += 0.18
                score_reasons.append("stable_q_strong")
        if code == source_q_top and code not in anomaly_codes and p >= PROTECTION_P_MIN and source_q_value >= Q_STRONG_PROTECTION_MIN:
            score += 0.30
            score_reasons.append("source_q_confirmed")
        if code == "1":
            if p >= 0.30:
                score += 0.95
                score_reasons.append("draw_probability_guard")
            elif p >= 0.27:
                score += 0.80
                score_reasons.append("draw_probability_guard")
            elif p >= 0.25 and abs(row.handicap_line or 0.0) <= 0.25:
                score += 0.55
                score_reasons.append("draw_probability_guard")
            if stable_q_value >= 0.90:
                score += 0.20
                score_reasons.append("draw_q_floor")
        if code in anomaly_codes and code == source_q_top and code != stable_q_top:
            score -= 0.45
            score_reasons.append("source_q_sp_anomaly_penalty")
        if p < 0.22:
            score -= 2.0
            score_reasons.append("low_probability_not_protected")
        second_scores[code] = (score, score_reasons)

    if max_codes > 1 and second_scores:
        second_code, (second_score, second_reasons) = max(
            second_scores.items(),
            key=lambda item: (item[1][0], probabilities.get(item[0]) or 0.0),
        )
        if second_score >= 0.65:
            codes.append(second_code)
            reasons.extend(second_reasons)

    if max_codes > 2:
        for code, (score, score_reasons) in sorted(
            second_scores.items(),
            key=lambda item: (item[1][0], probabilities.get(item[0]) or 0.0),
            reverse=True,
        ):
            if code in codes:
                continue
            if score >= 2.20 and len(codes) < max_codes:
                codes.append(code)
                reasons.extend(score_reasons)

    if source_q_top in anomaly_codes and source_q_top not in codes:
        risk_tags.append("drop_source_q_top_after_sp_sanity")
    elif source_q_top in OUTCOME_ORDER and source_q_top not in codes:
        risk_tags.append("q_top_not_used_as_primary")

    primary = codes[0] if codes else ""
    if primary != prob_top:
        risk_tags.append("primary_not_probability_top")
    return V43Decision(
        codes=codes,
        primary=primary,
        reasons=reasons,
        risk_tags=sorted(set(risk_tags)),
        source_q_top=source_q_top,
        stable_q_top=stable_q_top,
        prob_top=prob_top,
        source_sp_anomaly_codes=anomaly_codes,
        q_source=source_q,
        q_stable=stable_q,
        sp_source=source_sp,
        sp_stable=stable_sp,
    )


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def load_rows(conn: sqlite3.Connection, issues: list[str]) -> list[SnapshotRow]:
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in issues)
    has_nowscore = table_exists(conn, "nowscore_bjdc_matches")
    nowscore_cols = (
        """
            n.score AS nowscore_score,
            n.result_code AS nowscore_result_code,
            n.status AS nowscore_status,
            n.status_text AS nowscore_status_text
        """
        if has_nowscore
        else """
            NULL AS nowscore_score,
            NULL AS nowscore_result_code,
            NULL AS nowscore_status,
            NULL AS nowscore_status_text
        """
    )
    nowscore_join = (
        """
        LEFT JOIN nowscore_bjdc_matches n
          ON n.issue=s.issue AND n.match_idx=s.match_idx
        """
        if has_nowscore
        else ""
    )
    rows = conn.execute(
        f"""
        WITH active AS (
            SELECT
                s.*,
                ROW_NUMBER() OVER (
                    PARTITION BY s.issue, s.match_idx
                    ORDER BY s.generated_at DESC, s.snapshot_id DESC
                ) AS rn
            FROM llm_decision_snapshots s
            WHERE s.status='active'
              AND s.issue IN ({placeholders})
        )
        SELECT
            s.issue,
            s.match_idx,
            s.input_payload_json,
            m.league,
            m.home,
            m.away,
            m.handicap_line,
            m.score,
            m.result_code,
            m.winning_sp,
            m.sp_home,
            m.sp_draw,
            m.sp_away,
            {nowscore_cols}
        FROM active s
        LEFT JOIN matches m
          ON m.issue=s.issue AND m.match_idx=s.match_idx
        {nowscore_join}
        WHERE s.rn=1
        ORDER BY s.issue, s.match_idx
        """,
        issues,
    ).fetchall()
    out: list[SnapshotRow] = []
    for db_row in rows:
        try:
            payload = json.loads(db_row["input_payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        nowscore_finished = str(db_row["nowscore_status"] or "") == "finished" or "完场" in str(db_row["nowscore_status_text"] or "")
        result_code = db_row["result_code"]
        result_source = "matches"
        if result_code is None and nowscore_finished and db_row["nowscore_result_code"] is not None:
            result_code = db_row["nowscore_result_code"]
            result_source = "nowscore"
        score = str(db_row["score"] or "")
        if not score and nowscore_finished and db_row["nowscore_score"]:
            score = str(db_row["nowscore_score"])
        match = payload.get("match", {}) if isinstance(payload.get("match"), dict) else {}
        out.append(
            SnapshotRow(
                issue=str(db_row["issue"]),
                match_idx=int(db_row["match_idx"]),
                league=str(db_row["league"] or match.get("league") or ""),
                home=str(db_row["home"] or match.get("home") or ""),
                away=str(db_row["away"] or match.get("away") or ""),
                handicap_line=safe_float(db_row["handicap_line"] if "handicap_line" in db_row.keys() else match.get("handicap_line")),
                score=score,
                result_code=str(result_code) if result_code is not None else None,
                winning_sp=safe_float(db_row["winning_sp"]),
                result_source=result_source if result_code is not None else "",
                payload=payload,
                latest_sp={
                    "3": safe_float(db_row["sp_home"]),
                    "1": safe_float(db_row["sp_draw"]),
                    "0": safe_float(db_row["sp_away"]),
                },
            )
        )
    return out


def available_issues(conn: sqlite3.Connection) -> list[str]:
    conn.row_factory = sqlite3.Row
    return [
        str(row["issue"])
        for row in conn.execute(
            """
            SELECT issue
            FROM llm_decision_snapshots
            WHERE status='active'
            GROUP BY issue
            ORDER BY issue
            """
        )
    ]


def evaluate_v3_3_3(row: SnapshotRow) -> dict[str, Any]:
    decision = structured_decision_for_payload(row.payload)
    codes = parse_codes(decision.get("selection_codes"))
    q_source = q_values(probabilities_from_payload(row.payload), source_sp_from_payload(row.payload))
    return record_from_codes(
        row,
        arm="v3.3.3_recomputed",
        version="llm_chain_bet_protect_stop_v3.3.3_shadow_recomputed",
        codes=codes,
        primary=str(decision.get("primary_pick") or (codes[0] if codes else "")),
        reasons=["recomputed_structured_v3.3.3"],
        risk_tags=[str(tag) for tag in decision.get("risk_tags", [])],
        prob_top=top_code(probabilities_from_payload(row.payload)),
        q_top=top_code(q_source),
        q_source=q_source,
        q_stable=q_source,
        sp_source=source_sp_from_payload(row.payload),
        sp_stable=source_sp_from_payload(row.payload),
    )


def evaluate_v4_3(row: SnapshotRow, *, max_codes: int) -> dict[str, Any]:
    decision = probability_first_decision(row, max_codes=max_codes)
    return record_from_codes(
        row,
        arm="v4.3_probability_first",
        version=VERSION,
        codes=decision.codes,
        primary=decision.primary,
        reasons=decision.reasons,
        risk_tags=decision.risk_tags,
        prob_top=decision.prob_top,
        q_top=decision.stable_q_top,
        q_source=decision.q_source,
        q_stable=decision.q_stable,
        sp_source=decision.sp_source,
        sp_stable=decision.sp_stable,
        extra={
            "source_q_top": decision.source_q_top,
            "stable_q_top": decision.stable_q_top,
            "source_sp_anomaly_codes": "+".join(decision.source_sp_anomaly_codes),
        },
    )


def record_from_codes(
    row: SnapshotRow,
    *,
    arm: str,
    version: str,
    codes: list[str],
    primary: str,
    reasons: list[str],
    risk_tags: list[str],
    prob_top: str,
    q_top: str,
    q_source: dict[str, float | None],
    q_stable: dict[str, float | None],
    sp_source: dict[str, float | None],
    sp_stable: dict[str, float | None],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hit = bool(row.result_code and row.result_code in codes)
    record = {
        "arm": arm,
        "version": version,
        "issue": row.issue,
        "match_idx": row.match_idx,
        "league": row.league,
        "home": row.home,
        "away": row.away,
        "handicap_line": row.handicap_line,
        "score": row.score,
        "actual_code": row.result_code or "",
        "actual": outcome_text(row.result_code),
        "winning_sp": row.winning_sp,
        "result_source": row.result_source,
        "selection_codes": "+".join(codes),
        "selection_labels": "+".join(outcome_text(code) for code in codes),
        "selection_type": selection_type(codes),
        "primary": primary,
        "primary_label": outcome_text(primary),
        "stake": len(codes),
        "coverage_hit": int(hit) if row.result_code else "",
        "primary_hit": int(primary == row.result_code) if row.result_code else "",
        "profit_proxy": leg_profit(codes, row.result_code, row.winning_sp) if row.result_code and row.winning_sp is not None else "",
        "prob_top": prob_top,
        "q_top": q_top,
        "source_q_top": top_code(q_source),
        "stable_q_top": q_top,
        "source_sp_anomaly_codes": "",
        "reasons": ";".join(reasons),
        "risk_tags": ";".join(sorted(set(risk_tags))),
    }
    probabilities = probabilities_from_payload(row.payload)
    for code in OUTCOME_ORDER:
        record[f"p_{code}"] = probabilities.get(code)
        record[f"source_sp_{code}"] = sp_source.get(code)
        record[f"stable_sp_{code}"] = sp_stable.get(code)
        record[f"source_q_{code}"] = q_source.get(code)
        record[f"stable_q_{code}"] = q_stable.get(code)
    if extra:
        record.update(extra)
    return record


def find_v4_2_execution_csv(issue: str, shadow_dir: Path) -> Path | None:
    pattern = f"{issue}_*_shadow_v4.2.0000_execution_late_proxy_fullcap2/structured_shadow_{issue}.csv"
    candidates = sorted(shadow_dir.glob(pattern))
    return candidates[-1] if candidates else None


def load_v4_2_execution_records(rows_by_key: dict[tuple[str, int], SnapshotRow], issues: list[str], shadow_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for issue in issues:
        csv_path = find_v4_2_execution_csv(issue, shadow_dir)
        if csv_path is None:
            continue
        with csv_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for artifact_row in reader:
                match_idx = int(safe_float(artifact_row.get("match_idx")) or 0)
                row = rows_by_key.get((issue, match_idx))
                if row is None:
                    continue
                codes = parse_codes(artifact_row.get("shadow_selection_codes"))
                primary = str(artifact_row.get("shadow_primary") or (codes[0] if codes else ""))
                q_source = {code: safe_float(artifact_row.get(f"source_q_{code}") or artifact_row.get(f"q_{code}")) for code in OUTCOME_ORDER}
                q_stable = {code: safe_float(artifact_row.get(f"execution_q_{code}") or artifact_row.get(f"q_{code}")) for code in OUTCOME_ORDER}
                sp_source = {code: safe_float(artifact_row.get(f"source_sp_{code}") or artifact_row.get(f"sp_{code}")) for code in OUTCOME_ORDER}
                sp_stable = {code: safe_float(artifact_row.get(f"execution_sp_{code}") or artifact_row.get(f"sp_{code}")) for code in OUTCOME_ORDER}
                version = str(artifact_row.get("execution_policy_version") or artifact_row.get("shadow_version") or "")
                version_prefix = next((part for part in version.split("_") if part.startswith("v4.2.")), "v4.2")
                records.append(
                    record_from_codes(
                        row,
                        arm=f"{version_prefix}_execution_late_proxy",
                        version=version,
                        codes=codes,
                        primary=primary,
                        reasons=[str(artifact_row.get("execution_action") or ""), str(artifact_row.get("execution_reasons") or "")],
                        risk_tags=[str(artifact_row.get("risk_tags") or "")],
                        prob_top=str(artifact_row.get("prob_top") or ""),
                        q_top=top_code(q_stable),
                        q_source=q_source,
                        q_stable=q_stable,
                        sp_source=sp_source,
                        sp_stable=sp_stable,
                        extra={
                            "source_q_top": top_code(q_source),
                            "stable_q_top": top_code(q_stable),
                            "source_sp_anomaly_codes": "",
                        },
                    )
                )
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    result_known = [record for record in records if record["actual_code"]]
    bet = [record for record in result_known if int(record["stake"] or 0) > 0]
    profit_known = [record for record in result_known if record["profit_proxy"] != ""]
    stake = sum(int(record["stake"] or 0) for record in profit_known)
    profit = sum(float(record["profit_proxy"]) for record in profit_known if safe_float(record["profit_proxy"]) is not None)
    return {
        "rows": len(records),
        "result_known": len(result_known),
        "profit_known": len(profit_known),
        "bet_matches": len(bet),
        "coverage_hits": sum(1 for record in bet if record["coverage_hit"] == 1),
        "primary_hits": sum(1 for record in bet if record["primary_hit"] == 1),
        "coverage_hit_rate": sum(1 for record in bet if record["coverage_hit"] == 1) / len(bet) if bet else None,
        "primary_hit_rate": sum(1 for record in bet if record["primary_hit"] == 1) / len(bet) if bet else None,
        "stake": stake,
        "avg_depth": stake / len(profit_known) if profit_known else None,
        "profit_proxy": round(profit, 4),
        "roi_proxy": profit / stake if stake else None,
        "selection_types": dict(Counter(str(record["selection_type"]) for record in records)),
    }


def summarize_by_arm(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_arm[str(record["arm"])].append(record)
    out = []
    for arm, arm_records in sorted(by_arm.items()):
        summary = summarize(arm_records)
        out.append(
            {
                "arm": arm,
                "rows": summary["rows"],
                "result_known": summary["result_known"],
                "profit_known": summary["profit_known"],
                "coverage": pct(summary["coverage_hit_rate"]),
                "primary": pct(summary["primary_hit_rate"]),
                "stake": summary["stake"],
                "avg_depth": num(summary["avg_depth"]),
                "profit": summary["profit_proxy"],
                "roi": pct(summary["roi_proxy"]),
                "types": summary["selection_types"],
            }
        )
    return out


def summarize_by_issue(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(str(record["arm"]), str(record["issue"]))].append(record)
    out = []
    for (arm, issue), group in sorted(grouped.items()):
        summary = summarize(group)
        out.append(
            {
                "arm": arm,
                "issue": issue,
                "rows": summary["rows"],
                "coverage": pct(summary["coverage_hit_rate"]),
                "primary": pct(summary["primary_hit_rate"]),
                "profit": summary["profit_proxy"],
                "roi": pct(summary["roi_proxy"]),
                "avg_depth": num(summary["avg_depth"]),
            }
        )
    return out


def switched_records(records: list[dict[str, Any]], base_arm: str, compare_arm: str) -> list[dict[str, Any]]:
    by_key = {(record["issue"], record["match_idx"], record["arm"]): record for record in records}
    keys = sorted({(record["issue"], record["match_idx"]) for record in records})
    out = []
    for issue, match_idx in keys:
        base = by_key.get((issue, match_idx, base_arm))
        comp = by_key.get((issue, match_idx, compare_arm))
        if not base or not comp:
            continue
        if base["selection_codes"] == comp["selection_codes"]:
            continue
        out.append(
            {
                "issue": issue,
                "#": match_idx,
                "match": f"{comp['home']} vs {comp['away']}",
                "score": comp["score"] or "-",
                "actual": comp["actual"],
                "base": base["selection_labels"] or "-",
                "new": comp["selection_labels"] or "-",
                "base_hit": base["coverage_hit"],
                "new_hit": comp["coverage_hit"],
                "prob_top": outcome_text(comp["prob_top"]),
                "source_q_top": outcome_text(comp["source_q_top"]),
                "stable_q_top": outcome_text(comp["stable_q_top"]),
                "risk": comp["risk_tags"],
            }
        )
    return out


def focus_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    focus_keys = {("26072", 51), ("26072", 61)}
    out = []
    for record in records:
        if (str(record["issue"]), int(record["match_idx"])) not in focus_keys:
            continue
        out.append(
            {
                "arm": record["arm"],
                "issue": record["issue"],
                "#": record["match_idx"],
                "match": f"{record['home']} vs {record['away']}",
                "score": record["score"] or "-",
                "actual": record["actual"],
                "selection": record["selection_labels"] or "-",
                "hit": record["coverage_hit"],
                "primary": record["primary_label"],
                "prob_top": outcome_text(record["prob_top"]),
                "source_q_top": outcome_text(record["source_q_top"]),
                "stable_q_top": outcome_text(record["stable_q_top"]),
                "source_sp": f"{num(record.get('source_sp_3'), 2)}/{num(record.get('source_sp_1'), 2)}/{num(record.get('source_sp_0'), 2)}",
                "stable_sp": f"{num(record.get('stable_sp_3'), 2)}/{num(record.get('stable_sp_1'), 2)}/{num(record.get('stable_sp_0'), 2)}",
                "risk": record["risk_tags"],
            }
        )
    return out


def high_q_low_p_records(records: list[dict[str, Any]], arm: str = "v4.3_probability_first") -> list[dict[str, Any]]:
    out = []
    for record in records:
        if record["arm"] != arm:
            continue
        q_top = str(record.get("source_q_top") or "")
        prob_top = str(record.get("prob_top") or "")
        if q_top not in OUTCOME_ORDER or q_top == prob_top:
            continue
        q_p = safe_float(record.get(f"p_{q_top}")) or 0.0
        source_q = safe_float(record.get(f"source_q_{q_top}")) or 0.0
        if source_q < 1.30 or q_p >= 0.34:
            continue
        out.append(
            {
                "issue": record["issue"],
                "#": record["match_idx"],
                "match": f"{record['home']} vs {record['away']}",
                "score": record["score"] or "-",
                "actual": record["actual"],
                "selection": record["selection_labels"],
                "hit": record["coverage_hit"],
                "prob_top": outcome_text(prob_top),
                "source_q_top": outcome_text(q_top),
                "stable_q_top": outcome_text(record.get("stable_q_top")),
                "source_q": num(source_q),
                "q_top_p": pct(q_p),
                "risk": record["risk_tags"],
            }
        )
    return out


def render_report(records: list[dict[str, Any]], csv_path: Path, issues: list[str], v4_2_missing: list[str]) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    summary_rows = summarize_by_arm(records)
    issue_rows = summarize_by_issue(records)
    switches = switched_records(records, "v3.3.3_recomputed", "v4.3_probability_first")
    focus = focus_records(records)
    high_q = high_q_low_p_records(records)[:40]
    missing_text = ", ".join(v4_2_missing) if v4_2_missing else "无"
    return f"""# Probability-first 决策链 v4.3.0000 回测

生成时间：{generated}

## 边界

- 样本：`llm_decision_snapshots.status='active'` 可复算期号：{", ".join(issues)}。
- v3.3.3 为按当前脚本复算的 shadow 口径；v4.2 为现有 `late_proxy_fullcap2` execution artifact，可用期号自动纳入。
- 赛果：优先 `matches.result_code`，主表未结算但 NowScore 完场时只用于命中评估。
- profit proxy：只对已有真实北单 `winning_sp` 的行计算，成本按每覆盖一个结果 1 单位。
- v4.3 不修改 release/default，不写 `llm_decision_snapshots`。
- v4.2 execution artifact 缺失期号：{missing_text}。

复现命令：

```bash
python3 scripts/evaluate_probability_first_decision_chain_v4_3.py --issue 26071 --issue 26072
```

## v4.3 规则摘要

1. 主押先锁让球后三结果概率 top；只有极近概率且有结构证据时才允许偏离，本版回测未主动偏离概率 top。
2. q/EV 只竞争保护位：q top 与概率 top 不一致时，不能成为 mandatory single，也不能替换概率 top。
3. SP sanity：源北单 SP 若相对同 payload 欧赔均值或最新北单 SP 严重背离，则源 q 降为风险标签；保护位改用最新北单 SP，缺失时用欧赔均值作为稳定锚。
4. 默认最多双选，避免把 v4.2 的执行压缩问题继续转嫁给全包。

## 整体结果

{md_table(summary_rows, [
        ("arm", "arm"),
        ("rows", "rows"),
        ("有赛果", "result_known"),
        ("有SP", "profit_known"),
        ("覆盖命中", "coverage"),
        ("主押命中", "primary"),
        ("成本", "stake"),
        ("均深", "avg_depth"),
        ("profit proxy", "profit"),
        ("ROI proxy", "roi"),
        ("票型", "types"),
    ])}

## 分期结果

{md_table(issue_rows, [
        ("arm", "arm"),
        ("issue", "issue"),
        ("rows", "rows"),
        ("覆盖命中", "coverage"),
        ("主押命中", "primary"),
        ("profit", "profit"),
        ("ROI", "roi"),
        ("均深", "avg_depth"),
    ])}

## #51 / #61 专项

{md_table(focus, [
        ("arm", "arm"),
        ("期号", "issue"),
        ("#", "#"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("押保", "selection"),
        ("命中", "hit"),
        ("主押", "primary"),
        ("prob_top", "prob_top"),
        ("源q top", "source_q_top"),
        ("稳定q top", "stable_q_top"),
        ("源SP 3/1/0", "source_sp"),
        ("稳定SP 3/1/0", "stable_sp"),
        ("risk", "risk"),
    ])}

## v3.3.3 -> v4.3 切换

{md_table(switches[:60], [
        ("期号", "issue"),
        ("#", "#"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("v3.3.3", "base"),
        ("v4.3", "new"),
        ("v3命中", "base_hit"),
        ("v4.3命中", "new_hit"),
        ("prob_top", "prob_top"),
        ("源q top", "source_q_top"),
        ("稳定q top", "stable_q_top"),
        ("risk", "risk"),
    ])}

## 高 q / 低胜率切换样本

{md_table(high_q, [
        ("期号", "issue"),
        ("#", "#"),
        ("比赛", "match"),
        ("比分", "score"),
        ("赛果", "actual"),
        ("v4.3", "selection"),
        ("命中", "hit"),
        ("prob_top", "prob_top"),
        ("源q top", "source_q_top"),
        ("稳定q top", "stable_q_top"),
        ("源q", "source_q"),
        ("q方向p", "q_top_p"),
        ("risk", "risk"),
    ])}

完整 CSV：`{display_path(csv_path)}`

## 结论

当前小样本结论偏向：v4.2 execution 在加入极值 source q guard 后，已经能修复 #61 这类“源北单 SP 极端导致 q 爆表、主押偏离概率 top”的问题，同时保留 v4.2 的高覆盖优势。v4.3 的 probability-first 框架仍能作为诊断参考，但双选默认覆盖率低于 v3.3.3 和 v4.2，说明保护位还不够稳，不能替换默认。

上线判断：

- 不建议上线为 active/default；`shadow_v3.3.3` 继续保持默认。
- 可以继续观察 v4.2 execution late_proxy 作为备选；极值 source q guard 应保留在 v4.2 执行层。
- 可以进入下一步 execution/diagnostic 的逻辑：概率 top 主押硬约束、源 SP sanity 异常标签、q top 稳定化前后切换标签、源 q 不得成为 mandatory single。
- 暂不进入默认执行的逻辑：直接用欧赔均值替代北单 SP、把 stable q top 强制作为保护、扩大到默认全包。
- 下一步应用 26073+ forward settlement 继续观察极值 guard 是否只修复尾部风险，而不会引入新的错删/错增保护。
"""


def write_records(csv_path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "arm",
        "version",
        "issue",
        "match_idx",
        "league",
        "home",
        "away",
        "handicap_line",
        "score",
        "actual_code",
        "actual",
        "winning_sp",
        "result_source",
        "selection_codes",
        "selection_labels",
        "selection_type",
        "primary",
        "primary_label",
        "stake",
        "coverage_hit",
        "primary_hit",
        "profit_proxy",
        "prob_top",
        "q_top",
        "source_q_top",
        "stable_q_top",
        "source_sp_anomaly_codes",
        "reasons",
        "risk_tags",
    ]
    for code in OUTCOME_ORDER:
        fieldnames.extend([f"p_{code}", f"source_sp_{code}", f"stable_sp_{code}", f"source_q_{code}", f"stable_q_{code}"])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key, "") for key in fieldnames})


def run(
    *,
    db_path: Path,
    issues: list[str],
    csv_path: Path,
    report_path: Path,
    v4_2_shadow_dir: Path,
    max_codes: int,
) -> tuple[Path, Path, dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    try:
        resolved_issues = issues or available_issues(conn)
        rows = load_rows(conn, resolved_issues)
    finally:
        conn.close()
    rows_by_key = {(row.issue, row.match_idx): row for row in rows}
    records: list[dict[str, Any]] = []
    for row in rows:
        records.append(evaluate_v3_3_3(row))
        records.append(evaluate_v4_3(row, max_codes=max_codes))
    v4_2_records = load_v4_2_execution_records(rows_by_key, resolved_issues, v4_2_shadow_dir)
    records.extend(v4_2_records)
    v4_2_available = {str(record["issue"]) for record in v4_2_records}
    v4_2_missing = [issue for issue in resolved_issues if issue not in v4_2_available]

    write_records(csv_path, records)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(records, csv_path, resolved_issues, v4_2_missing), encoding="utf-8")
    return report_path, csv_path, {
        "issues": resolved_issues,
        "rows": len(rows),
        "records": len(records),
        "v4_2_missing": v4_2_missing,
        "summary": summarize_by_arm(records),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest probability-first v4.3 decision chain candidate.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", action="append", default=[], help="Issue to include. Repeatable. Defaults to all active snapshot issues.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--v4-2-shadow-dir", type=Path, default=DEFAULT_V4_2_SHADOW_DIR)
    parser.add_argument("--max-codes", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_path, csv_path, summary = run(
        db_path=args.db,
        issues=args.issue,
        csv_path=args.csv,
        report_path=args.report,
        v4_2_shadow_dir=args.v4_2_shadow_dir,
        max_codes=max(1, min(3, int(args.max_codes))),
    )
    print(json.dumps({"report": str(report_path), "csv": str(csv_path), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
