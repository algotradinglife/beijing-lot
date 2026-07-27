from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.decision_artifact_completeness import active_snapshot_completeness, format_completeness_error  # noqa: E402
from src.structured_v333_projection import canonical_v333_decision_projection  # noqa: E402
from src.structured_input_receipt import write_receipt  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/structured_decision_chain_shadow"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/research"
OUTCOME_ORDER = ("3", "1", "0")
OUTCOME_LABEL = {"3": "胜", "1": "平", "0": "负"}
CODE_TO_SIDE = {"3": "home", "1": "draw", "0": "away"}
SIDE_TO_CODE = {"home": "3", "draw": "1", "away": "0"}
Q_STOP_THRESHOLD = 1.0
SHADOW_VERSION = "llm_chain_bet_protect_stop_v3.3.3"
SHADOW_ARM = "active_v3.3.3"
LLM_INTEL_PROTECTION_SCHEMA = "llm_intel_protection_v2"


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def safe_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        loaded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback
    return loaded


def pct(value: float | None) -> str:
    return "缺" if value is None else f"{value:.1%}"


def num(value: float | None, digits: int = 2) -> str:
    return "缺" if value is None else f"{value:.{digits}f}"


def outcome_text(code: str | None, match: dict[str, Any]) -> str:
    if code == "3":
        return f"胜({match.get('home') or '主队'})"
    if code == "1":
        return "平"
    if code == "0":
        return f"负({match.get('away') or '客队'})"
    return "停"


def compact_text(items: Any) -> str:
    if isinstance(items, list):
        text = "。".join(str(item) for item in items if item)
    elif isinstance(items, dict):
        text = " ".join(str(v) for v in items.values() if isinstance(v, str))
    else:
        text = str(items or "")
    return re.sub(r"\s+", " ", text).strip()


def split_clauses(text: str) -> list[str]:
    clauses = [item.strip() for item in re.split(r"[。；;，,.!?！？\n\r]+", text) if item.strip()]
    return clauses[:24]


def result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    probabilities = payload.get("model", {}).get("probabilities", {})
    market_probabilities = payload.get("model", {}).get("market_probabilities", {})
    sp = payload.get("sp", {})
    rows: list[dict[str, Any]] = []
    for code in OUTCOME_ORDER:
        probability = safe_float(probabilities.get(code))
        price = safe_float(sp.get(code))
        market_probability = safe_float(market_probabilities.get(code))
        rows.append(
            {
                "code": code,
                "probability": probability,
                "sp": price,
                "market_probability": market_probability,
                "q": probability * price if probability is not None and price is not None else None,
            }
        )
    return rows


def top_by(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    usable = [row for row in rows if safe_float(row.get(key)) is not None]
    if not usable:
        return {}
    return max(usable, key=lambda row: float(row[key]))


def _add_score(scores: dict[str, float], evidence: dict[str, list[str]], code: str | None, weight: float, reason: str) -> None:
    if code not in OUTCOME_ORDER or weight <= 0:
        return
    scores[str(code)] += weight
    evidence[str(code)].append(reason)


def _sentiment_counts(
    clause: str,
    positive_words: tuple[str, ...],
    negative_words: tuple[str, ...],
    undefeated_words: tuple[str, ...],
) -> tuple[int, int]:
    masked = clause
    undefeated_count = 0
    for word in undefeated_words:
        if word in masked:
            undefeated_count += 1
            masked = masked.replace(word, " ")
    pos = undefeated_count + sum(1 for word in positive_words if word in masked)
    neg = sum(1 for word in negative_words if word in masked)
    if re.search(r"(?:仅|只)胜\d*场", clause):
        neg += 1
    return pos, neg


def classify_raw_strength(payload: dict[str, Any]) -> dict[str, Any]:
    match = payload.get("match", {})
    home = str(match.get("home") or "")
    away = str(match.get("away") or "")
    intelligence = payload.get("intelligence", {})
    analysis = payload.get("analysis", {})
    text = compact_text(intelligence.get("points")) + " " + compact_text(analysis.get("highlights"))
    text = text.strip()
    scores = {"home": 0.0, "draw": 0.0, "away": 0.0}
    evidence = {"home": [], "draw": [], "away": []}
    if not text:
        return {"side": None, "score": 0.0, "confidence": 0.0, "evidence": [], "raw_scores": scores}

    positive_words = (
        "取胜",
        "获胜",
        "胜利",
        "胜利在望",
        "胜券",
        "赢球",
        "看好",
        "看高",
        "优势",
        "更胜",
        "强势",
        "强大",
        "强劲",
        "火力",
        "出色",
        "稳定",
        "不败",
        "有力",
        "胜鼓",
        "轻取",
        "战斗力强",
        "主场龙",
        "连胜",
        "晋级",
        "前进",
        "零封",
    )
    negative_words = (
        "败绩",
        "乏力",
        "隐患",
        "下滑",
        "失球",
        "平庸",
        "不擅",
        "不算出众",
        "未如理想",
        "未尝胜绩",
        "未尝胜",
        "难胜",
        "无胜",
        "防守端存在",
        "争胜乏力",
    )
    undefeated_words = ("未尝败绩", "未尝败", "保持不败", "未输", "未负", "无败", "不败")
    draw_words = ("难分高下", "和局", "平分秋色", "握手言和", "战平", "平局", "平手", "和味")
    home_context_words = ("主场", "主队", "坐镇", "主场作战", "今铺")
    away_context_words = ("作客", "客场", "客队", "远征")

    for clause in split_clauses(text):
        home_hit = bool(home and home in clause)
        away_hit = bool(away and away in clause)
        home_context = any(word in clause for word in home_context_words)
        away_context = any(word in clause for word in away_context_words)
        if any(word in clause for word in draw_words):
            scores["draw"] += 2.0
            evidence["draw"].append(clause)
        if home and away:
            if re.search(re.escape(home) + r".{0,12}(更胜|胜过|优于|力压|淘汰).{0,12}" + re.escape(away), clause):
                scores["home"] += 2.5
                evidence["home"].append(clause)
            if re.search(re.escape(away) + r".{0,12}(更胜|胜过|优于|力压|淘汰).{0,12}" + re.escape(home), clause):
                scores["away"] += 2.5
                evidence["away"].append(clause)
        pos, neg = _sentiment_counts(clause, positive_words, negative_words, undefeated_words)
        context_positive_side = None
        if home_context and not away_context and pos:
            context_positive_side = "home"
            units = float(pos if home_hit else min(pos, 1))
            scores["home"] += units * (1.0 if home_hit else 0.25)
            evidence["home"].append(clause)
        if away_context and not home_context and pos:
            context_positive_side = "away"
            units = float(pos if away_hit else min(pos, 1))
            scores["away"] += units * (1.0 if away_hit else 0.25)
            evidence["away"].append(clause)
        if home_hit and pos and context_positive_side != "away":
            scores["home"] += float(pos)
            evidence["home"].append(clause)
        if away_hit and pos and context_positive_side != "home":
            scores["away"] += float(pos)
            evidence["away"].append(clause)
        if home_hit and neg:
            scores["home"] -= float(neg) * 0.8
            scores["away"] += float(neg) * 0.5
            evidence["away"].append(clause)
        if away_hit and neg:
            scores["away"] -= float(neg) * 0.8
            scores["home"] += float(neg) * 0.5
            evidence["home"].append(clause)
        if home_context and neg and not home_hit and not away_hit:
            units = float(min(neg, 1))
            scores["home"] -= units * 0.35
            scores["away"] += units * 0.15
            evidence["away"].append(clause)
        if away_context and neg and not home_hit and not away_hit:
            units = float(min(neg, 1))
            scores["away"] -= units * 0.35
            scores["home"] += units * 0.15
            evidence["home"].append(clause)

    side = max(scores, key=lambda item: scores[item])
    score = scores[side]
    if score <= 0:
        side = None
        confidence = 0.0
    else:
        runner_up = sorted(scores.values(), reverse=True)[1]
        margin = max(0.0, score - runner_up)
        confidence = min(0.88, 0.35 + score * 0.06 + margin * 0.05)
    return {
        "side": side,
        "score": round(max(0.0, score), 3),
        "confidence": round(confidence, 3),
        "evidence": evidence.get(side, [])[:3] if side else [],
        "raw_scores": {key: round(value, 3) for key, value in scores.items()},
    }


def classify_handicap_fit(payload: dict[str, Any], raw_strength: dict[str, Any]) -> dict[str, Any]:
    match = payload.get("match", {})
    handicap = safe_float(match.get("handicap_line")) or 0.0
    side = raw_strength.get("side")
    raw_confidence = safe_float(raw_strength.get("confidence")) or 0.0
    raw_score = safe_float(raw_strength.get("score")) or 0.0
    intelligence_text = compact_text(payload.get("intelligence", {}).get("points"))
    big_margin_words = (
        "大胜",
        "狂胜",
        "横扫",
        "至少两球",
        "至少攻入",
        "每场至少",
        "净胜",
        "穿盘",
        "完胜",
        "大捷",
        "大比分",
        "火力无人能挡",
        "火力全开",
        "进攻狂潮",
        "大斩四方",
        "狂入",
    )
    narrow_words = ("小胜", "一球", "险胜")
    big_margin = any(word in intelligence_text for word in big_margin_words)
    narrow = any(word in intelligence_text for word in narrow_words)
    risk_tags: list[str] = []
    evidence: list[str] = []
    code: str | None = None
    score = 0.0

    if side is None:
        return {"side": None, "code": None, "score": 0.0, "confidence": 0.0, "evidence": [], "risk_tags": ["raw_strength_missing"]}
    if side == "draw":
        code = "1"
        score = min(0.75, raw_confidence)
        evidence.append("原始情报/数据直接指向常规平局或难分高下。")
    elif abs(handicap) < 0.25:
        code = SIDE_TO_CODE.get(str(side))
        score = raw_confidence
        evidence.append("北单让球为0，原始强弱倾向可直接映射到让球后方向。")
    elif handicap < 0 and side == "home":
        if big_margin:
            code = "3"
            score = raw_confidence * (0.88 if handicap <= -2.0 else 0.75)
            evidence.append(f"主队让 {abs(handicap):.0f} 球，且情报出现明确大胜/穿盘/多球火力表达。")
        elif handicap >= -1.0:
            code = "1"
            score = raw_confidence * 0.55
            risk_tags.append("raw_strength_not_handicap_result")
            evidence.append("原始主队强势更像胜出倾向，未证明能穿过北单让球；优先映射到让球平/观察。")
        else:
            code = None
            score = raw_confidence * 0.25
            risk_tags.append("raw_strength_not_handicap_result")
            evidence.append("主队强势不等于让2球后仍胜；缺少明确大胜证据。")
    elif handicap < 0 and side == "away":
        code = "0"
        score = raw_confidence * 0.70
        evidence.append("主队让球时，客队原始强势/主队负面更支持让球负方向。")
    elif handicap > 0 and side == "home":
        code = "3"
        score = raw_confidence * 0.70
        evidence.append("主队受让时，主队原始强势通常支持让球胜方向。")
    elif handicap > 0 and side == "away":
        if big_margin:
            code = "0"
            score = raw_confidence * (0.88 if handicap >= 2.0 else 0.75)
            evidence.append(f"主队受让 {handicap:.0f} 球，且客队方向出现明确大胜/穿盘/多球火力表达。")
        elif handicap <= 1.0 or narrow:
            code = "1"
            score = raw_confidence * 0.45
            risk_tags.append("raw_strength_not_handicap_result")
            evidence.append("客队强势不等于能穿过主队受让，优先转为让球平/观察。")
        else:
            code = None
            score = raw_confidence * 0.20
            risk_tags.append("raw_strength_not_handicap_result")
            evidence.append("客队强势缺少穿过深受让证据。")

    return {
        "side": CODE_TO_SIDE.get(code) if code else None,
        "code": code,
        "score": round(max(0.0, min(1.0, score)), 3),
        "confidence": round(min(0.90, raw_confidence + raw_score * 0.01), 3),
        "evidence": evidence + list(raw_strength.get("evidence", [])[:2]),
        "risk_tags": risk_tags,
    }


def _recent_record(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"近10场\s*(\d+)胜(\d+)平(\d+)负", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def classify_form_recent(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis", {})
    home_text = str(analysis.get("home_recent") or "")
    away_text = str(analysis.get("away_recent") or "")
    home_record = _recent_record(home_text)
    away_record = _recent_record(away_text)
    evidence = []
    if not home_record or not away_record:
        return {"side": None, "code": None, "score": 0.0, "confidence": 0.0, "evidence": [], "raw": {}}
    h_win, h_draw, h_loss = home_record
    a_win, a_draw, a_loss = away_record
    home_score = h_win + h_draw * 0.25 - h_loss
    away_score = a_win + a_draw * 0.25 - a_loss
    draw_score = min(h_draw, a_draw) / 10.0
    if h_draw >= 4 and a_draw >= 4:
        evidence.append("两队近10场平局占比都不低。")
    if abs(home_score - away_score) < 1.0 and draw_score >= 0.4:
        side = "draw"
        score = draw_score
        confidence = 0.40 + draw_score * 0.35
    elif home_score > away_score:
        side = "home"
        score = min(1.0, (home_score - away_score) / 5.0)
        confidence = 0.35 + score * 0.35
    else:
        side = "away"
        score = min(1.0, (away_score - home_score) / 5.0)
        confidence = 0.35 + score * 0.35
    evidence.extend([home_text, away_text])
    code = SIDE_TO_CODE.get(side)
    return {
        "side": side,
        "code": code,
        "score": round(score, 3),
        "confidence": round(min(0.75, confidence), 3),
        "evidence": evidence[:3],
        "raw": {"home_record": home_record, "away_record": away_record},
    }


def classify_competition_context(payload: dict[str, Any]) -> dict[str, Any]:
    intelligence = payload.get("intelligence", {})
    stage = intelligence.get("stage") if isinstance(intelligence.get("stage"), dict) else {}
    stage_type = str(stage.get("stage_type") or "")
    competition_label = str(stage.get("competition_label") or "")
    tags: list[str] = []
    if stage_type:
        tags.append(stage_type)
    if "杯" in competition_label or "杯" in str(payload.get("match", {}).get("league") or ""):
        tags.append("cup")
    if stage_type == "knockout":
        return {
            "side": None,
            "code": None,
            "score": 0.25,
            "confidence": 0.45,
            "evidence": [f"赛制/阶段：{competition_label or '淘汰赛'}，90分钟平局与保守倾向需要单独留意。"],
            "tags": tags,
        }
    return {
        "side": None,
        "code": None,
        "score": 0.0,
        "confidence": 0.0,
        "evidence": [f"赛制/阶段：{competition_label}"] if competition_label else [],
        "tags": tags,
    }


def classify_market_q_ev(payload: dict[str, Any]) -> dict[str, Any]:
    rows = result_rows(payload)
    q_top = top_by(rows, "q")
    probability_top = top_by(rows, "probability")
    match = payload.get("match", {})
    market = payload.get("market", {})
    odds_consensus = market.get("odds_consensus") if isinstance(market.get("odds_consensus"), dict) else {}
    drift = odds_consensus.get("drift") if isinstance(odds_consensus.get("drift"), dict) else {}
    line_gap = safe_float(match.get("line_gap"))
    risk_tags: list[str] = []
    support_tags: list[str] = []
    q_top_code = str(q_top.get("code") or "") if q_top else ""
    prob_top_code = str(probability_top.get("code") or "") if probability_top else ""
    q_top_prob = safe_float(q_top.get("probability")) if q_top else None
    q_top_q = safe_float(q_top.get("q")) if q_top else None
    if q_top_code and prob_top_code and q_top_code != prob_top_code and (q_top_prob or 0) < 0.30 and (q_top_q or 0) >= 1.20:
        risk_tags.append("q_high_but_probability_low")
    if line_gap is None:
        risk_tags.append("line_gap_missing")
    elif abs(line_gap) >= 0.75:
        risk_tags.append("line_gap_large")
    elif abs(line_gap) >= 0.50:
        risk_tags.append("line_gap_watch")
    for code, drift_key in {"3": "home", "1": "draw", "0": "away"}.items():
        value = safe_float(drift.get(drift_key)) if isinstance(drift, dict) else None
        if value is None:
            continue
        if code == q_top_code and value <= -0.08:
            support_tags.append("q_top_odds_down")
        if code == q_top_code and value >= 0.08:
            risk_tags.append("q_top_odds_up")
    return {
        "side": CODE_TO_SIDE.get(q_top_code) if q_top_code in OUTCOME_ORDER else None,
        "code": q_top_code if q_top_code in OUTCOME_ORDER else None,
        "q": round(q_top_q, 4) if q_top_q is not None else None,
        "probability": round(q_top_prob, 4) if q_top_prob is not None else None,
        "sp": safe_float(q_top.get("sp")) if q_top else None,
        "probability_top_code": prob_top_code if prob_top_code in OUTCOME_ORDER else None,
        "probability_top": round(safe_float(probability_top.get("probability")) or 0.0, 4) if probability_top else None,
        "rows": rows,
        "risk_tags": risk_tags,
        "support_tags": support_tags,
        "drift": drift if isinstance(drift, dict) else {},
        "line_gap": line_gap,
    }


def classify_data_quality(payload: dict[str, Any], market_q_ev: dict[str, Any]) -> dict[str, Any]:
    analysis = payload.get("analysis", {})
    intelligence = payload.get("intelligence", {})
    risk_tags: list[str] = []
    if analysis.get("status") != "ok":
        risk_tags.append("analysis_missing")
    if intelligence.get("status") != "ok":
        risk_tags.append("intelligence_missing")
    if not market_q_ev.get("code"):
        risk_tags.append("q_unavailable")
    rows = market_q_ev.get("rows") if isinstance(market_q_ev.get("rows"), list) else []
    for row in rows:
        if row.get("probability") is None or row.get("sp") is None:
            risk_tags.append("prob_or_sp_missing")
            break
    severe = any(tag in risk_tags for tag in ("q_unavailable", "prob_or_sp_missing"))
    return {
        "side": None,
        "code": None,
        "score": 0.0 if risk_tags else 1.0,
        "confidence": 1.0 if not severe else 0.2,
        "evidence": risk_tags or ["analysis/intelligence/probability/sp inputs available"],
        "risk_tags": risk_tags,
        "severe": severe,
    }


def row_for_code(rows: list[dict[str, Any]], code: str) -> dict[str, Any]:
    return next((row for row in rows if str(row.get("code") or "") == code), {})


def q_for_code(rows: list[dict[str, Any]], code: str) -> float | None:
    return safe_float(row_for_code(rows, code).get("q"))


def probability_for_code(rows: list[dict[str, Any]], code: str) -> float | None:
    return safe_float(row_for_code(rows, code).get("probability"))


def adjacent_protection_code(primary_code: str | None, pressure_code: str | None) -> str | None:
    """Convert reverse pressure into the nearest ordered W/D/L protection.

    In the Beidan W/D/L ordered space, opposite-end pressure should first pull
    the distribution toward draw instead of jumping straight from win to loss
    or loss to win. Example: primary loss + home-positive intel protects draw.
    """
    primary = str(primary_code or "")
    pressure = str(pressure_code or "")
    if primary not in OUTCOME_ORDER or pressure not in OUTCOME_ORDER or primary == pressure:
        return None
    if "1" in {primary, pressure}:
        return pressure
    return "1"


def _normalize_llm_protection_advice(raw: Any) -> dict[str, Any] | None:
    advice = safe_json(raw, {}) if not isinstance(raw, dict) else raw
    if not isinstance(advice, dict) or not advice:
        return None
    protect_code = str(
        advice.get("protect_code")
        or advice.get("recommended_protect_code")
        or advice.get("code")
        or ""
    )
    if protect_code not in OUTCOME_ORDER:
        protect_code = ""
    confidence = safe_float(advice.get("confidence"))
    if confidence is None:
        confidence = safe_float(advice.get("protect_confidence"))
    strength = safe_float(advice.get("strength"))
    if strength is None:
        strength = safe_float(advice.get("protect_strength"))
    if strength is None:
        strength = confidence
    should_protect_raw = advice.get("should_protect")
    should_protect = (
        bool(should_protect_raw)
        if should_protect_raw is not None
        else bool(protect_code and (strength or 0.0) >= 0.55)
    )
    evidence_raw = advice.get("evidence") or advice.get("reasons") or advice.get("reason") or []
    if isinstance(evidence_raw, str):
        evidence = [evidence_raw]
    elif isinstance(evidence_raw, list):
        evidence = [str(item) for item in evidence_raw if str(item or "").strip()]
    else:
        evidence = []
    return {
        "schema_version": LLM_INTEL_PROTECTION_SCHEMA,
        "source": str(advice.get("source") or "payload_llm"),
        "status": "ok",
        "should_protect": bool(should_protect and protect_code),
        "protect_code": protect_code or None,
        "protect_strength": round(max(0.0, min(1.0, strength or 0.0)), 3),
        "confidence": round(max(0.0, min(1.0, confidence or strength or 0.0)), 3),
        "evidence": evidence[:4],
        "risk_tags": [str(item) for item in advice.get("risk_tags", [])] if isinstance(advice.get("risk_tags"), list) else [],
    }


def _has_big_margin_text(text: str) -> bool:
    return any(
        word in text
        for word in (
            "大胜",
            "狂胜",
            "横扫",
            "至少两球",
            "至少攻入",
            "每场至少",
            "净胜",
            "穿盘",
            "完胜",
            "大捷",
            "大比分",
            "火力无人能挡",
            "火力全开",
            "进攻狂潮",
            "大斩四方",
            "狂入",
        )
    )


def _has_narrow_margin_text(text: str) -> bool:
    return any(word in text for word in ("小胜", "一球", "险胜", "小球", "谨慎", "胶着", "僵持"))


def map_recent_form_to_handicap_code(payload: dict[str, Any], form_recent: dict[str, Any]) -> tuple[str | None, str]:
    """Translate recent raw form into a Beidan handicap result candidate.

    Recent form usually describes ordinary strength rather than the Beidan
    handicap result. A strong favorite giving one goal is therefore mapped to
    handicap draw/protection first, not automatically to handicap win.
    """
    side = str(form_recent.get("side") or "")
    if side not in {"home", "draw", "away"}:
        return None, ""
    handicap = safe_float(payload.get("match", {}).get("handicap_line")) or 0.0
    if side == "draw":
        return "1", "近期表现指向双方走势接近或平局率偏高，映射为让球平保护候选。"
    if abs(handicap) < 0.25:
        return SIDE_TO_CODE.get(side), "北单让球为0，近期表现方向可直接映射。"
    if handicap < 0:
        if side == "home":
            if abs(handicap) <= 1.0:
                return "1", "主队近期更强但北单让球，未证明能穿盘，优先映射到让球平保护。"
            return None, "主队近期更强但深让球下缺少穿盘证据，近期表现只作风险提示。"
        return "0", "客队近期更强且主队让球，映射到让球负保护候选。"
    if side == "home":
        return "3", "主队近期更强且主队受让，映射到让球胜保护候选。"
    if abs(handicap) <= 1.0:
        return "1", "客队近期更强但主队受让，未证明客队能穿过受让，优先映射到让球平保护。"
    return None, "客队近期更强但主队深受让下缺少穿盘证据，近期表现只作风险提示。"


def classify_llm_intel_protection(
    payload: dict[str, Any],
    primary_code: str | None,
    rows: list[dict[str, Any]],
    raw_strength: dict[str, Any],
    handicap_fit: dict[str, Any],
    competition_context: dict[str, Any],
    form_recent: dict[str, Any],
) -> dict[str, Any]:
    """Isolate the future LLM intelligence overlay from the deterministic aggregator.

    Live mode can inject a real LLM JSON object under `llm_intel_protection`.
    Historical replay has no such object, so it uses a deterministic proxy with
    the same schema for regression testing and comparison.
    """
    raw_advice = payload.get("llm_intel_protection")
    if raw_advice is None and isinstance(payload.get("intelligence"), dict):
        raw_advice = payload["intelligence"].get("llm_protection")
    normalized = _normalize_llm_protection_advice(raw_advice)
    if normalized:
        return normalized

    intelligence = payload.get("intelligence", {}) if isinstance(payload.get("intelligence"), dict) else {}
    match = payload.get("match", {}) if isinstance(payload.get("match"), dict) else {}
    form_evidence_text = compact_text(form_recent.get("evidence"))
    text = (compact_text(intelligence.get("points")) + " " + form_evidence_text).strip()
    handicap = safe_float(match.get("handicap_line")) or 0.0
    fit_code = str(handicap_fit.get("code") or "")
    raw_side = str(raw_strength.get("side") or "")
    raw_conf = safe_float(raw_strength.get("confidence")) or 0.0
    context_tags = competition_context.get("tags") if isinstance(competition_context.get("tags"), list) else []
    evidence: list[str] = []
    risk_tags: list[str] = []
    protect_code: str | None = None
    strength = 0.0
    recent_form_signal: dict[str, Any] = {
        "code": None,
        "mapped_code": None,
        "confidence": round(safe_float(form_recent.get("confidence")) or 0.0, 3),
        "evidence": [],
    }

    if text and fit_code in OUTCOME_ORDER and fit_code != primary_code:
        adjacent_code = adjacent_protection_code(primary_code, fit_code)
        fit_q = q_for_code(rows, adjacent_code or "") or 0.0
        fit_p = probability_for_code(rows, adjacent_code or "") or 0.0
        if raw_conf >= 0.50 and (fit_q >= 0.75 or fit_p >= 0.24):
            protect_code = adjacent_code
            strength = max(strength, min(0.82, 0.35 + raw_conf * 0.45 + fit_p * 0.25))
            if adjacent_code == fit_code:
                evidence.append("情报强弱经让球映射后与主押不同，建议作为保护方向。")
            else:
                evidence.append("情报强弱与主押在对侧，按有序空间先拉扯到相邻结果作为保护。")

    if text and abs(handicap) == 1.0 and "1" != primary_code:
        draw_q = q_for_code(rows, "1") or 0.0
        draw_p = probability_for_code(rows, "1") or 0.0
        if _has_narrow_margin_text(text) and (draw_q >= 0.72 or draw_p >= 0.23):
            protect_code = "1"
            strength = max(strength, min(0.80, 0.42 + draw_p * 0.60 + min(draw_q, 1.2) * 0.08))
            evidence.append("情报出现一球/胶着倾向，且北单为一球让步，优先考虑让球平保护。")
        if ("knockout" in context_tags or "cup" in context_tags) and draw_p >= 0.26 and (draw_q >= 0.75 or _has_narrow_margin_text(text)):
            protect_code = "1"
            strength = max(strength, min(0.78, 0.45 + draw_p * 0.70))
            evidence.append("杯赛/淘汰赛语境下，一球盘口的让球平具备近邻保护价值。")

    if text and abs(handicap) >= 2.0 and raw_side in {"home", "away"} and not _has_big_margin_text(text):
        if handicap < 0 and raw_side == "home":
            candidate = "0"
        elif handicap > 0 and raw_side == "away":
            candidate = "3"
        else:
            candidate = ""
        adjacent_code = adjacent_protection_code(primary_code, candidate)
        if adjacent_code in OUTCOME_ORDER and adjacent_code != primary_code:
            candidate_q = q_for_code(rows, adjacent_code) or 0.0
            candidate_p = probability_for_code(rows, adjacent_code) or 0.0
            if candidate_q >= 0.80 or candidate_p >= 0.22:
                protect_code = adjacent_code
                strength = max(strength, min(0.76, 0.36 + raw_conf * 0.35 + candidate_p * 0.30))
                evidence.append("情报只支持原始强队，不足以证明能穿过深让球，反向压力先保护相邻结果。")
                risk_tags.append("raw_strength_without_cover_margin")

    form_mapped_code, form_mapping_reason = map_recent_form_to_handicap_code(payload, form_recent)
    form_code = str(form_recent.get("code") or "")
    form_conf = safe_float(form_recent.get("confidence")) or 0.0
    recent_form_signal = {
        "code": form_code if form_code in OUTCOME_ORDER else None,
        "mapped_code": form_mapped_code if form_mapped_code in OUTCOME_ORDER else None,
        "confidence": round(form_conf, 3),
        "evidence": list(form_recent.get("evidence", [])[:3]) if isinstance(form_recent.get("evidence"), list) else [],
        "mapping_reason": form_mapping_reason,
    }
    if form_mapped_code in OUTCOME_ORDER and form_mapped_code != primary_code:
        adjacent_code = adjacent_protection_code(primary_code, form_mapped_code)
        form_q = q_for_code(rows, adjacent_code or "") or 0.0
        form_p = probability_for_code(rows, adjacent_code or "") or 0.0
        if form_conf >= 0.48 and (form_q >= 0.72 or form_p >= 0.22):
            candidate_strength = min(0.80, 0.34 + form_conf * 0.42 + form_p * 0.30 + min(form_q, 1.2) * 0.05)
            if candidate_strength >= strength:
                protect_code = adjacent_code
                strength = max(strength, candidate_strength)
            if adjacent_code != form_mapped_code:
                risk_tags.append("reverse_intel_adjacent_protection")
            evidence.append(
                "近期表现经北单让球映射后与主押不同，进入情报保护评估："
                + form_mapping_reason
                + ("；反向压力先保护相邻结果。" if adjacent_code != form_mapped_code else "")
            )
            risk_tags.append("recent_form_intel_protection")
        elif form_conf >= 0.48:
            risk_tags.append("recent_form_conflict_watch")

    should_protect = bool(protect_code and protect_code != primary_code and strength >= 0.55)
    return {
        "schema_version": LLM_INTEL_PROTECTION_SCHEMA,
        "source": "script_proxy",
        "status": "ok" if text or form_mapped_code else "missing",
        "should_protect": should_protect,
        "protect_code": protect_code if protect_code in OUTCOME_ORDER else None,
        "protect_strength": round(strength, 3),
        "confidence": round(min(0.80, strength), 3),
        "evidence": evidence[:4],
        "risk_tags": risk_tags,
        "recent_form": recent_form_signal,
    }


def structured_decision_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    match = payload.get("match", {})
    rows = result_rows(payload)
    prob_top = top_by(rows, "probability")
    raw_strength = classify_raw_strength(payload)
    handicap_fit = classify_handicap_fit(payload, raw_strength)
    market_q_ev = classify_market_q_ev(payload)
    form_recent = classify_form_recent(payload)
    competition_context = classify_competition_context(payload)
    data_quality = classify_data_quality(payload, market_q_ev)
    sections = {
        "raw_strength": raw_strength,
        "handicap_fit": handicap_fit,
        "market_q_ev": market_q_ev,
        "model_probability": {
            "side": CODE_TO_SIDE.get(str(prob_top.get("code") or "")),
            "code": str(prob_top.get("code") or "") if prob_top else None,
            "score": safe_float(prob_top.get("probability")) if prob_top else None,
            "confidence": safe_float(prob_top.get("probability")) if prob_top else None,
            "evidence": [
                f"让球后概率最高：{outcome_text(str(prob_top.get('code') or ''), match)} {pct(safe_float(prob_top.get('probability')))}"
            ]
            if prob_top
            else [],
        },
        "form_recent": form_recent,
        "competition_context": competition_context,
        "data_quality": data_quality,
    }
    risk_tags = list(handicap_fit.get("risk_tags", [])) + list(market_q_ev.get("risk_tags", [])) + list(data_quality.get("risk_tags", []))
    if (
        market_q_ev.get("code")
        and market_q_ev.get("probability_top_code")
        and market_q_ev.get("code") != market_q_ev.get("probability_top_code")
    ):
        risk_tags.append("q_probability_disagree")
    if raw_strength.get("side") and handicap_fit.get("code") and SIDE_TO_CODE.get(str(raw_strength.get("side"))) != handicap_fit.get("code"):
        risk_tags.append("raw_strength_handicap_remapped")

    scores = {code: 0.0 for code in OUTCOME_ORDER}
    evidence = {code: [] for code in OUTCOME_ORDER}
    for row in rows:
        code = str(row.get("code") or "")
        probability = safe_float(row.get("probability")) or 0.0
        _add_score(scores, evidence, code, probability * 2.0, f"让球后概率 {pct(probability)}")
    _add_score(
        scores,
        evidence,
        str(handicap_fit.get("code") or ""),
        (safe_float(handicap_fit.get("score")) or 0.0) * 0.9,
        "handicap_fit: " + " / ".join(str(item) for item in handicap_fit.get("evidence", [])[:2]),
    )
    _add_score(
        scores,
        evidence,
        str(form_recent.get("code") or ""),
        (safe_float(form_recent.get("score")) or 0.0) * 0.35,
        "recent_form: " + " / ".join(str(item) for item in form_recent.get("evidence", [])[:2]),
    )
    if competition_context.get("tags") and "knockout" in competition_context.get("tags", []):
        draw_probability = next((safe_float(row.get("probability")) for row in rows if row.get("code") == "1"), None) or 0.0
        if draw_probability >= 0.26:
            _add_score(scores, evidence, "1", 0.10, "淘汰赛且让球后平局概率不低，作为保守倾向加权。")

    q_top_code = str(market_q_ev.get("code") or "")
    q_top = safe_float(market_q_ev.get("q"))
    max_score_code = max(scores, key=lambda code: scores[code])
    probability_ranked = sorted(
        [row for row in rows if safe_float(row.get("probability")) is not None],
        key=lambda row: float(row["probability"]),
        reverse=True,
    )
    stop_reasons: list[str] = []
    if data_quality.get("severe"):
        stop_reasons.append("关键概率或SP输入缺失")
    if q_top is None or q_top < Q_STOP_THRESHOLD:
        stop_reasons.append(f"max_q={num(q_top)} 低于 {Q_STOP_THRESHOLD:.2f}")
    high_risk_count = len({tag for tag in risk_tags if tag not in {"q_probability_disagree", "line_gap_watch"}})
    if high_risk_count >= 4 and (q_top or 0.0) < 1.15:
        stop_reasons.append("风险标签过多且q缓冲不足")

    llm_intel_protection = classify_llm_intel_protection(
        payload,
        max_score_code,
        rows,
        raw_strength,
        handicap_fit,
        competition_context,
        form_recent,
    )
    sections["llm_intel_protection"] = llm_intel_protection
    risk_tags.extend(list(llm_intel_protection.get("risk_tags", [])))

    if stop_reasons:
        risk_tags.append("advisory_stop")
    if True:
        primary_code = max_score_code
        selection_codes = [primary_code]
        protect_codes = []
        primary_probability = probability_for_code(rows, primary_code) or 0.0
        probability_runner = next(
            (row for row in probability_ranked if str(row.get("code") or "") != primary_code),
            {},
        )
        probability_runner_code = str(probability_runner.get("code") or "")
        probability_runner_p = safe_float(probability_runner.get("probability")) or 0.0
        probability_runner_q = safe_float(probability_runner.get("q")) or 0.0
        probability_gap = max(0.0, primary_probability - probability_runner_p)
        should_protect_probability_runner = (
            probability_runner_code in OUTCOME_ORDER
            and probability_runner_code not in selection_codes
            and probability_runner_q >= 0.60
            and (
                (probability_runner_p >= 0.30 and probability_gap <= 0.10)
                or (probability_runner_p >= 0.34 and probability_gap <= 0.14)
            )
        )
        if should_protect_probability_runner:
            protect_codes.append(probability_runner_code)
            selection_codes.append(probability_runner_code)
            risk_tags.append("probability_runner_up_protection")
        if q_top_code in OUTCOME_ORDER and q_top_code != primary_code and q_top_code not in selection_codes and (q_top or 0.0) >= Q_STOP_THRESHOLD:
            protect_codes.append(q_top_code)
            selection_codes.append(q_top_code)
        handicap_fit_code = str(handicap_fit.get("code") or "")
        handicap = safe_float(match.get("handicap_line")) or 0.0
        if (
            handicap_fit_code in OUTCOME_ORDER
            and handicap_fit_code != primary_code
            and handicap_fit_code not in selection_codes
            and abs(handicap) == 1.0
            and ((q_for_code(rows, handicap_fit_code) or 0.0) >= 0.95 or (safe_float(handicap_fit.get("score")) or 0.0) >= 0.40)
        ):
            protect_codes.append(handicap_fit_code)
            selection_codes.append(handicap_fit_code)
        draw_q = q_for_code(rows, "1") or 0.0
        draw_probability = probability_for_code(rows, "1") or 0.0
        context_tags = competition_context.get("tags") if isinstance(competition_context.get("tags"), list) else []
        should_protect_handicap_draw = (
            abs(handicap) == 1.0
            and "1" not in selection_codes
            and (draw_q >= 0.75 or draw_probability >= 0.26)
            and ("knockout" in context_tags or "cup" in context_tags or draw_q >= 0.95)
        )
        if should_protect_handicap_draw:
            protect_codes.append("1")
            selection_codes.append("1")
        llm_protect_code = str(llm_intel_protection.get("protect_code") or "")
        llm_strength = safe_float(llm_intel_protection.get("protect_strength")) or 0.0
        llm_protect_q = q_for_code(rows, llm_protect_code) or 0.0
        llm_protect_probability = probability_for_code(rows, llm_protect_code) or 0.0
        llm_risk_tags = llm_intel_protection.get("risk_tags") if isinstance(llm_intel_protection.get("risk_tags"), list) else []
        llm_from_recent_form = "recent_form_intel_protection" in llm_risk_tags
        would_expand_to_full = len(selection_codes) >= 2 and llm_protect_code not in selection_codes
        recent_form_full_allowed = (
            not llm_from_recent_form
            or not would_expand_to_full
            or (
                llm_strength >= 0.78
                and (llm_protect_q >= 0.95 or llm_protect_probability >= 0.28)
            )
        )
        should_apply_llm_protection = (
            bool(llm_intel_protection.get("should_protect"))
            and llm_protect_code in OUTCOME_ORDER
            and llm_protect_code != primary_code
            and llm_protect_code not in selection_codes
            and (llm_strength >= 0.70 or llm_protect_q >= 0.70 or llm_protect_probability >= 0.20)
            and recent_form_full_allowed
        )
        if should_apply_llm_protection:
            protect_codes.append(llm_protect_code)
            selection_codes.append(llm_protect_code)
        elif (
            bool(llm_intel_protection.get("should_protect"))
            and llm_from_recent_form
            and would_expand_to_full
            and not recent_form_full_allowed
        ):
            risk_tags.append("recent_form_full_guard")
        judgment = outcome_text(primary_code, match)
        if protect_codes:
            judgment += "为押，保" + "+".join(outcome_text(code, match) for code in protect_codes)

    confidence = min(0.86, max(0.25, 0.35 + scores.get(primary_code or "", 0.0) * 0.20 - len(risk_tags) * 0.025))
    llm_intel_code = str(llm_intel_protection.get("protect_code") or "")
    if llm_intel_code in OUTCOME_ORDER and llm_intel_protection.get("should_protect"):
        llm_intel_line = (
            f"情报保护层：{llm_intel_protection.get('source')} 建议保护 "
            f"{outcome_text(llm_intel_code, match)}，强度 {num(safe_float(llm_intel_protection.get('protect_strength')))}；"
            + "；".join(str(item) for item in llm_intel_protection.get("evidence", [])[:2])
        )
    else:
        llm_intel_line = f"情报保护层：{llm_intel_protection.get('source')} 未建议新增保护。"
    chain = [
        f"概率主线：最高让球后概率 {outcome_text(str(prob_top.get('code') or ''), match)} {pct(safe_float(prob_top.get('probability')))}。",
        f"EV/q主线：最高q {outcome_text(q_top_code, match)} q={num(q_top)}，概率 {pct(safe_float(market_q_ev.get('probability')))}，SP {num(safe_float(market_q_ev.get('sp')))}。",
        "让球映射：" + "；".join(str(item) for item in handicap_fit.get("evidence", [])[:2]),
        llm_intel_line,
        "动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。",
        "概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。",
    ]
    if stop_reasons:
        chain.append("停牌：" + "；".join(stop_reasons))
    elif protect_codes:
        chain.append("保护：" + "+".join(outcome_text(code, match) for code in protect_codes) + " 来自 q/EV 与主押不一致。")
    else:
        chain.append("保护：q/EV 与主押一致或未形成额外保护方向。")

    return {
        "decision_version": SHADOW_VERSION,
        "match": match,
        "sections": sections,
        "scores": {code: round(value, 4) for code, value in scores.items()},
        "score_evidence": {code: evidence[code][:4] for code in OUTCOME_ORDER},
        "primary_pick": primary_code,
        "protect_picks": protect_codes,
        "selection_codes": selection_codes,
        "selection_type": "no-buy" if not selection_codes else "double" if len(selection_codes) == 2 else "full" if len(selection_codes) >= 3 else "single",
        "stop_flag": 1 if stop_reasons else 0,
        "judgment": judgment,
        "confidence": round(confidence, 3),
        "risk_tags": sorted(set(risk_tags)),
        "chain": chain,
    }


@dataclass
class ReplayRow:
    issue: str
    match_idx: int
    match_id: str
    league: str
    home: str
    away: str
    handicap_line: float | None
    score: str
    result_code: str | None
    result_label: str
    winning_sp: float | None
    active_recommendation: str
    active_primary: str | None
    active_selection_codes: list[str]
    active_decision_version: str
    payload: dict[str, Any]
    structured: dict[str, Any]


def load_issue_rows(conn: sqlite3.Connection, issue: str) -> list[ReplayRow]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        WITH active AS (
            SELECT
                s.*,
                ROW_NUMBER() OVER (
                    PARTITION BY s.issue, s.match_idx
                    ORDER BY s.generated_at DESC, s.snapshot_id DESC
                ) AS rn
            FROM llm_decision_snapshots s
            WHERE s.issue=? AND s.status='active'
        )
        SELECT
            s.*,
            m.league,
            m.home,
            m.away,
            m.handicap_line,
            m.score,
            m.result_code,
            m.result_label,
            m.winning_sp
        FROM active s
        LEFT JOIN matches m
          ON m.issue=s.issue AND m.match_idx=s.match_idx
        WHERE s.rn=1
        ORDER BY s.match_idx
        """,
        (issue,),
    ).fetchall()
    replay_rows: list[ReplayRow] = []
    for row in rows:
        payload = safe_json(row["input_payload_json"], {})
        structured = structured_decision_for_payload(payload)
        replay_rows.append(
            ReplayRow(
                issue=str(row["issue"]),
                match_idx=int(row["match_idx"]),
                match_id=str(row["match_id"] or f"{issue}_{int(row['match_idx']):03d}"),
                league=str(row["league"] or payload.get("match", {}).get("league") or ""),
                home=str(row["home"] or payload.get("match", {}).get("home") or ""),
                away=str(row["away"] or payload.get("match", {}).get("away") or ""),
                handicap_line=safe_float(row["handicap_line"] if row["handicap_line"] is not None else payload.get("match", {}).get("handicap_line")),
                score=str(row["score"] or ""),
                result_code=str(row["result_code"]) if row["result_code"] is not None else None,
                result_label=str(row["result_label"] or ""),
                winning_sp=safe_float(row["winning_sp"]),
                active_recommendation=str(row["recommendation"] or ""),
                active_primary=str(row["primary_pick"]) if row["primary_pick"] else None,
                active_selection_codes=[str(code) for code in safe_json(row["selection_codes_json"], []) if str(code) in OUTCOME_ORDER],
                active_decision_version=str(row["decision_chain_version"] or ""),
                payload=payload,
                structured=structured,
            )
        )
    return replay_rows


def assert_active_snapshots_complete(conn: sqlite3.Connection, issue: str, *, allow_incomplete: bool = False) -> dict[str, Any]:
    status = active_snapshot_completeness(conn, issue)
    if not status.complete and not allow_incomplete:
        raise SystemExit(format_completeness_error(status))
    return status.to_dict()


def leg_profit(codes: list[str], result_code: str | None, winning_sp: float | None) -> float:
    if not codes:
        return 0.0
    stake = float(len(codes))
    if result_code and result_code in codes and winning_sp is not None:
        return float(winning_sp) - stake
    return -stake


def canonical_v333_decision_record(row: ReplayRow) -> dict[str, Any]:
    """Expose the v3.3.3 decision independently of legacy CSV vocabulary."""

    return canonical_v333_decision_projection(
        row,
        result_rows=result_rows,
        category_rows=decision_category_rows,
        outcome_text=outcome_text,
        leg_profit=leg_profit,
    )


def row_to_csv_dict(row: ReplayRow) -> dict[str, Any]:
    payload = row.payload
    structured = row.structured
    rows = result_rows(payload)
    q_by_code = {str(item["code"]): item for item in rows}
    q_top = structured["sections"]["market_q_ev"].get("code")
    prob_top = structured["sections"]["market_q_ev"].get("probability_top_code")
    shadow_codes = list(structured.get("selection_codes", []))
    active_codes = row.active_selection_codes
    actual = row.result_code
    shadow_categories = decision_category_rows(structured, payload)
    return {
        "issue": row.issue,
        "match_idx": row.match_idx,
        "match_id": row.match_id,
        "league": row.league,
        "home": row.home,
        "away": row.away,
        "handicap_line": row.handicap_line,
        "score": row.score,
        "actual_code": actual or "",
        "actual_label": outcome_text(actual, payload.get("match", {})) if actual else "",
        "winning_sp": row.winning_sp if row.winning_sp is not None else "",
        "active_version": row.active_decision_version,
        "active_recommendation": row.active_recommendation,
        "active_primary": row.active_primary or "",
        "active_selection_codes": "+".join(active_codes),
        "active_primary_hit": "" if not actual else int(row.active_primary == actual),
        "active_coverage_hit": "" if not actual else int(actual in active_codes),
        "active_stake": len(active_codes),
        "active_profit_proxy": round(leg_profit(active_codes, actual, row.winning_sp), 4) if actual else "",
        "shadow_judgment": structured.get("judgment", ""),
        "shadow_primary": structured.get("primary_pick") or "",
        "shadow_selection_codes": "+".join(shadow_codes),
        "shadow_stop_flag": int(bool(structured.get("stop_flag"))),
        "shadow_primary_hit": "" if not actual else int(structured.get("primary_pick") == actual),
        "shadow_coverage_hit": "" if not actual else int(actual in shadow_codes),
        "shadow_stake": len(shadow_codes),
        "shadow_profit_proxy": round(leg_profit(shadow_codes, actual, row.winning_sp), 4) if actual else "",
        "shadow_arm": SHADOW_ARM,
        "shadow_version": SHADOW_VERSION,
        "selection_type": structured.get("selection_type", ""),
        "prob_top": prob_top or "",
        "q_top": q_top or "",
        "p_3": q_by_code["3"].get("probability"),
        "p_1": q_by_code["1"].get("probability"),
        "p_0": q_by_code["0"].get("probability"),
        "sp_3": q_by_code["3"].get("sp"),
        "sp_1": q_by_code["1"].get("sp"),
        "sp_0": q_by_code["0"].get("sp"),
        "q_3": q_by_code["3"].get("q"),
        "q_1": q_by_code["1"].get("q"),
        "q_0": q_by_code["0"].get("q"),
        "max_q": structured["sections"]["market_q_ev"].get("q"),
        "raw_strength_side": structured["sections"]["raw_strength"].get("side") or "",
        "handicap_fit_code": structured["sections"]["handicap_fit"].get("code") or "",
        "form_recent_code": structured["sections"]["form_recent"].get("code") or "",
        "form_recent_confidence": structured["sections"]["form_recent"].get("confidence") or "",
        "form_recent_mapped_code": structured["sections"].get("llm_intel_protection", {}).get("recent_form", {}).get("mapped_code") or "",
        "llm_intel_source": structured["sections"].get("llm_intel_protection", {}).get("source", ""),
        "llm_intel_protect": structured["sections"].get("llm_intel_protection", {}).get("protect_code") or "",
        "llm_intel_strength": structured["sections"].get("llm_intel_protection", {}).get("protect_strength", ""),
        "llm_intel_should_protect": int(bool(structured["sections"].get("llm_intel_protection", {}).get("should_protect"))),
        "risk_tags": ";".join(structured.get("risk_tags", [])),
        "shadow_chain_json": json.dumps(structured.get("chain", []), ensure_ascii=False),
        "shadow_categories_json": json.dumps(shadow_categories, ensure_ascii=False),
    }


def decision_category_rows(structured: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    match = payload.get("match", {})
    rows = result_rows(payload)
    sections = structured.get("sections", {}) if isinstance(structured.get("sections"), dict) else {}
    market_q_ev = sections.get("market_q_ev", {}) if isinstance(sections.get("market_q_ev"), dict) else {}
    raw_strength = sections.get("raw_strength", {}) if isinstance(sections.get("raw_strength"), dict) else {}
    handicap_fit = sections.get("handicap_fit", {}) if isinstance(sections.get("handicap_fit"), dict) else {}
    form_recent = sections.get("form_recent", {}) if isinstance(sections.get("form_recent"), dict) else {}
    competition_context = sections.get("competition_context", {}) if isinstance(sections.get("competition_context"), dict) else {}
    llm_intel = sections.get("llm_intel_protection", {}) if isinstance(sections.get("llm_intel_protection"), dict) else {}
    data_quality = sections.get("data_quality", {}) if isinstance(sections.get("data_quality"), dict) else {}

    prob_top_code = str(market_q_ev.get("probability_top_code") or "")
    q_top_code = str(market_q_ev.get("code") or "")
    raw_side = str(raw_strength.get("side") or "")
    form_mapped = llm_intel.get("recent_form", {}).get("mapped_code") if isinstance(llm_intel.get("recent_form"), dict) else None
    quality_risks = data_quality.get("risk_tags") if isinstance(data_quality.get("risk_tags"), list) else []
    context_tags = competition_context.get("tags") if isinstance(competition_context.get("tags"), list) else []
    risk_tags = structured.get("risk_tags") if isinstance(structured.get("risk_tags"), list) else []

    probability_summary = " / ".join(
        f"{OUTCOME_LABEL[str(item['code'])]} {pct(safe_float(item.get('probability')))}"
        for item in rows
    )
    q_summary = " / ".join(
        f"{OUTCOME_LABEL[str(item['code'])]} {num(safe_float(item.get('q')))}"
        for item in rows
    )

    categories = [
        {
            "key": "model_probability",
            "label": "让球后概率",
            "result": outcome_text(prob_top_code, match) if prob_top_code in OUTCOME_ORDER else "缺",
            "score": pct(safe_float(market_q_ev.get("probability_top"))),
            "verdict": "主押基础信号",
            "evidence": [probability_summary],
        },
        {
            "key": "market_q_ev",
            "label": "q / EV",
            "result": outcome_text(q_top_code, match) if q_top_code in OUTCOME_ORDER else "缺",
            "score": f"q {num(safe_float(market_q_ev.get('q')))}",
            "verdict": "只做保护/增厚，不直接反客为主",
            "evidence": [q_summary],
        },
        {
            "key": "handicap_fit",
            "label": "让球映射",
            "result": outcome_text(str(handicap_fit.get("code") or ""), match) if handicap_fit.get("code") else "无明确映射",
            "score": f"强度 {num(safe_float(handicap_fit.get('score')))}",
            "verdict": "情报强弱先过北单让球语境",
            "evidence": [str(item) for item in handicap_fit.get("evidence", [])[:3]] if isinstance(handicap_fit.get("evidence"), list) else [],
        },
        {
            "key": "form_recent",
            "label": "近期形态",
            "result": outcome_text(str(form_mapped or form_recent.get("code") or ""), match) if (form_mapped or form_recent.get("code")) else "无明确方向",
            "score": f"置信 {num(safe_float(form_recent.get('confidence')))}",
            "verdict": "轻权重影响主押，并可触发保护",
            "evidence": [str(item) for item in form_recent.get("evidence", [])[:3]] if isinstance(form_recent.get("evidence"), list) else [],
        },
        {
            "key": "raw_strength",
            "label": "情报强弱",
            "result": {"home": "主队", "draw": "平衡/平局", "away": "客队"}.get(raw_side, "未识别"),
            "score": f"置信 {num(safe_float(raw_strength.get('confidence')))}",
            "verdict": "只判断原始强弱，不直接等同让球结果",
            "evidence": [str(item) for item in raw_strength.get("evidence", [])[:3]] if isinstance(raw_strength.get("evidence"), list) else [],
        },
        {
            "key": "llm_intel_protection",
            "label": "情报保护层",
            "result": outcome_text(str(llm_intel.get("protect_code") or ""), match) if llm_intel.get("protect_code") else "未触发",
            "score": f"强度 {num(safe_float(llm_intel.get('protect_strength')))}",
            "verdict": "只能增加保护，不能改主押",
            "evidence": [str(item) for item in llm_intel.get("evidence", [])[:3]] if isinstance(llm_intel.get("evidence"), list) else [],
        },
        {
            "key": "competition_context",
            "label": "赛制语境",
            "result": " / ".join(str(item) for item in context_tags) if context_tags else "常规",
            "score": f"权重 {num(safe_float(competition_context.get('score')))}",
            "verdict": "只作风险提示或小权重",
            "evidence": [str(item) for item in competition_context.get("evidence", [])[:2]] if isinstance(competition_context.get("evidence"), list) else [],
        },
        {
            "key": "data_quality",
            "label": "数据质量/风险",
            "result": "可用" if not quality_risks else "有缺口",
            "score": f"{len(risk_tags)} 个风险标签",
            "verdict": "关键缺失才触发停牌",
            "evidence": quality_risks[:3] if quality_risks else ["analysis/intelligence/probability/sp inputs available"],
        },
        {
            "key": "final_aggregation",
            "label": "脚本汇总",
            "result": str(structured.get("judgment") or ""),
            "score": f"置信 {num(safe_float(structured.get('confidence')))}",
            "verdict": "固定规则合成押/保/停",
            "evidence": [str(item) for item in structured.get("chain", [])[:4]] if isinstance(structured.get("chain"), list) else [],
        },
    ]
    return categories


def summarize(rows: list[ReplayRow]) -> dict[str, Any]:
    settled = [row for row in rows if row.result_code]

    def metrics(prefix: str) -> dict[str, Any]:
        if prefix == "active":
            codes_fn = lambda row: row.active_selection_codes
            primary_fn = lambda row: row.active_primary
        else:
            codes_fn = lambda row: list(row.structured.get("selection_codes", []))
            primary_fn = lambda row: row.structured.get("primary_pick")
        bet_rows = [row for row in settled if codes_fn(row)]
        primary_hits = sum(1 for row in bet_rows if primary_fn(row) == row.result_code)
        coverage_hits = sum(1 for row in bet_rows if row.result_code in codes_fn(row))
        stake = sum(len(codes_fn(row)) for row in settled)
        profit = sum(leg_profit(codes_fn(row), row.result_code, row.winning_sp) for row in settled)
        type_counts = Counter(
            "no-buy" if not codes_fn(row) else "single" if len(codes_fn(row)) == 1 else "double" if len(codes_fn(row)) == 2 else "full"
            for row in rows
        )
        return {
            "bet_matches": len(bet_rows),
            "primary_hits": primary_hits,
            "coverage_hits": coverage_hits,
            "primary_hit_rate": primary_hits / len(bet_rows) if bet_rows else None,
            "coverage_hit_rate": coverage_hits / len(bet_rows) if bet_rows else None,
            "stake": stake,
            "profit_proxy": round(profit, 4),
            "roi_proxy": profit / stake if stake else None,
            "type_counts": dict(type_counts),
        }

    return {
        "n_matches": len(rows),
        "n_settled": len(settled),
        "n_pending": len(rows) - len(settled),
        "active": metrics("active"),
        "shadow": metrics("shadow"),
    }


def write_csv(rows: list[ReplayRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [row_to_csv_dict(row) for row in rows]
    fieldnames = list(records[0]) if records else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def md_table(records: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = []
    lines.append("| " + " | ".join(title for title, _key in columns) + " |")
    lines.append("| " + " | ".join("---" for _title, _key in columns) + " |")
    for record in records:
        values = []
        for _title, key in columns:
            value = record.get(key, "")
            if isinstance(value, float):
                value = f"{value:.3f}"
            values.append(str(value).replace("\n", " ").replace("|", "/"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def path_for_report(path: Path, *, base: Path = PROJECT_ROOT) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(base.resolve()))
    except ValueError:
        return str(resolved)


def render_report(rows: list[ReplayRow], summary: dict[str, Any], csv_path: Path, *, issue: str) -> str:
    records = [row_to_csv_dict(row) for row in rows]
    switch_records = [
        {
            **record,
            "profit_delta": (
                ""
                if record.get("active_profit_proxy") == "" or record.get("shadow_profit_proxy") == ""
                else round(float(record["shadow_profit_proxy"]) - float(record["active_profit_proxy"]), 4)
            ),
        }
        for record in records
        if record.get("active_primary") != record.get("shadow_primary")
        or record.get("active_selection_codes") != record.get("shadow_selection_codes")
    ]
    active = summary["active"]
    shadow = summary["shadow"]
    metric_records = [
        {
            "arm": "active_v3",
            "bet_matches": active["bet_matches"],
            "primary_hit_rate": pct(active["primary_hit_rate"]),
            "coverage_hit_rate": pct(active["coverage_hit_rate"]),
            "stake": active["stake"],
            "profit_proxy": active["profit_proxy"],
            "roi_proxy": pct(active["roi_proxy"]),
            "type_counts": active["type_counts"],
        },
        {
            "arm": SHADOW_ARM,
            "bet_matches": shadow["bet_matches"],
            "primary_hit_rate": pct(shadow["primary_hit_rate"]),
            "coverage_hit_rate": pct(shadow["coverage_hit_rate"]),
            "stake": shadow["stake"],
            "profit_proxy": shadow["profit_proxy"],
            "roi_proxy": pct(shadow["roi_proxy"]),
            "type_counts": shadow["type_counts"],
        },
    ]
    focus_016 = next((record for record in records if int(record["match_idx"]) == 16), None)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    return f"""# 结构化决策链 {issue} {SHADOW_ARM} 回测

生成时间：{generated}

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`{summary.get("snapshot_completeness", {}).get("actual_count", "缺")}/{summary.get("snapshot_completeness", {}).get("expected_count", "缺")}`；缺失场次 `{summary.get("snapshot_completeness", {}).get("missing_match_idx", [])}`。
- 未结算比赛只生成 shadow 决策，不计入命中率和 profit proxy。
- 本报告不写回 `llm_decision_snapshots`，不生成 active/draft replacement，不改变主策略票池。
- profit proxy 是单腿层面的简化评估：每选一个结果记 1 单位成本，命中返还该场 `winning_sp`；不是 N 串 ticket-level 回放。

## Schema

| 分类 | 作用 | 约束 |
| --- | --- | --- |
| raw_strength | 只判断原始强弱/情报情绪，如“瑞士胜利在望” | 不能直接等同北单让球后胜平负 |
| handicap_fit | 将 raw_strength 谨慎映射到北单整数让球结果 | 深让球必须有大胜/穿盘证据，否则降权或转观察/让球平 |
| market_q_ev | 计算各结果 `q=让球后概率*SP` 和 odds drift 诊断 | q 不再默认决定主押，只在过线且与主押不一致时作为保护/增厚 |
| model_probability | 让球校准后的三结果概率 | 主押基础信号 |
| form_recent | 近期胜平负结构和双方走势 | 轻权重影响主押，并经北单让球映射后输入 `llm_intel_protection` |
| competition_context | 联赛/杯赛/淘汰赛等赛制上下文 | 只作风险提示或小权重 |
| llm_intel_protection | 单独解读情报文本并考虑北单让球，判断是否增加保护 | 只能增加保护，不能改主押；当前历史回测无真实 LLM advice 时使用 `script_proxy` |
| data_quality/risk | 缺失、偏移、q高但胜率低、情报与让球冲突 | 关键输入缺失或风险过高时标记停，不清空押/保 |

## Aggregator

1. `max_q < 1.00` 或关键概率/SP 缺失时标记停；停只是风控观察标签，不覆盖押/保输出。
2. 主押由让球后概率、`handicap_fit` 和近期形态加权得到；raw 情报和近期形态都必须先过北单让球语境。
3. 当 q/EV 最高方向与主押不同且 q 过线时，将 q 方向加入保护，不反客为主。
4. `llm_intel_protection` 可在情报、近期表现与让球结构提示死腿风险时追加保护，但必须通过强度或基础概率/q护栏。
5. 近期表现保护默认只能把单选补成双选；若会把已有双选扩成全包，必须同时满足更高强度与更高概率/q，否则只保留诊断标签。
6. line-gap 和 drift 只进入诊断/风险标签，不作为 hard gate。

## 指标

{md_table(metric_records, [
        ("方案", "arm"),
        ("下注场", "bet_matches"),
        ("主押命中", "primary_hit_rate"),
        ("押+保命中", "coverage_hit_rate"),
        ("成本", "stake"),
        ("profit proxy", "profit_proxy"),
        ("ROI proxy", "roi_proxy"),
        ("票型", "type_counts"),
    ])}

## v3 vs {SHADOW_ARM} 切换明细

{md_table(switch_records, [
        ("#", "match_idx"),
        ("比赛", "league"),
        ("主队", "home"),
        ("客队", "away"),
        ("让球", "handicap_line"),
        ("比分", "score"),
        ("赛果", "actual_label"),
        ("active_v3", "active_selection_codes"),
        ("active命中", "active_coverage_hit"),
        (SHADOW_ARM, "shadow_selection_codes"),
        ("shadow命中", "shadow_coverage_hit"),
        ("profit差", "profit_delta"),
        ("prob_top", "prob_top"),
        ("q_top", "q_top"),
        ("risk_tags", "risk_tags"),
    ])}

## {issue} 全场明细

{md_table(records, [
        ("#", "match_idx"),
        ("比赛", "league"),
        ("主队", "home"),
        ("客队", "away"),
        ("让球", "handicap_line"),
        ("比分", "score"),
        ("赛果", "actual_label"),
        ("active_v3", "active_selection_codes"),
        ("active命中", "active_coverage_hit"),
        (SHADOW_ARM, "shadow_selection_codes"),
        ("情报保", "llm_intel_protect"),
        ("情报强度", "llm_intel_strength"),
        ("shadow命中", "shadow_coverage_hit"),
        ("prob_top", "prob_top"),
        ("q_top", "q_top"),
        ("max_q", "max_q"),
        ("raw", "raw_strength_side"),
        ("fit", "handicap_fit_code"),
        ("近期", "form_recent_code"),
        ("近况映射", "form_recent_mapped_code"),
        ("risk_tags", "risk_tags"),
    ])}

## {issue}_016 专项

{json.dumps(focus_016, ensure_ascii=False, indent=2) if focus_016 else "未找到 #16。"}

结论：`{SHADOW_VERSION}` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`{path_for_report(csv_path)}`
"""


def skipped_summary(issue: str, reason: str, completeness: dict[str, Any], message: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": reason,
        "issue": issue,
        "snapshot_completeness": completeness,
        "message": message,
    }


def run(
    issue: str,
    db_path: Path,
    output_root: Path,
    report_dir: Path,
    *,
    allow_incomplete: bool = False,
    strict_completeness: bool = False,
) -> tuple[Path | None, Path | None, dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    try:
        status = active_snapshot_completeness(conn, issue)
        completeness = status.to_dict()
        if not status.complete and not allow_incomplete:
            message = format_completeness_error(status)
            if strict_completeness:
                raise SystemExit(message)
            return None, None, skipped_summary(issue, "active_decision_snapshots_incomplete", completeness, message)
        rows = load_issue_rows(conn, issue)
    finally:
        conn.close()
    if not rows:
        return None, None, skipped_summary(
            issue,
            "active_decision_snapshots_missing",
            completeness,
            f"No active snapshots found for issue {issue} in {db_path}",
        )
    date_slug = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = output_root / f"{issue}_{date_slug}_{SHADOW_ARM}"
    csv_path = out_dir / f"structured_shadow_{issue}.csv"
    report_path = report_dir / f"structured_decision_chain_{issue}_{SHADOW_ARM}_{report_date}.md"
    summary = summarize(rows)
    summary["status"] = "generated"
    summary["snapshot_completeness"] = completeness
    write_csv(rows, csv_path)
    write_receipt(
        csv_path,
        issue=issue,
        source={
            "database": str(db_path),
            "snapshot_completeness": completeness,
            "match_indices": [row.match_idx for row in rows],
        },
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(rows, summary, csv_path, issue=issue), encoding="utf-8")
    return csv_path, report_path, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate shadow-only structured Beidan decision chain.")
    parser.add_argument("--issue", default="26071")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--allow-incomplete", action="store_true", help="Generate a review-only artifact even when active snapshots miss match rows.")
    parser.add_argument("--strict-completeness", action="store_true", help="Exit non-zero instead of returning a skipped payload when active snapshots are incomplete.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    csv_path, report_path, summary = run(
        args.issue,
        args.db,
        args.output_root,
        args.report_dir,
        allow_incomplete=args.allow_incomplete,
        strict_completeness=args.strict_completeness,
    )
    print(
        json.dumps(
            {
                "status": summary.get("status", "generated"),
                "csv": str(csv_path) if csv_path else "",
                "report": str(report_path) if report_path else "",
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
