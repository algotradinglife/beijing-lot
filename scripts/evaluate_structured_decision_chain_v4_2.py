from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results/structured_decision_chain_v4_2"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "docs/research"
OUTCOME_ORDER = ("3", "1", "0")
OUTCOME_LABEL = {"3": "胜", "1": "平", "0": "负"}
CODE_TO_SIDE = {"3": "home", "1": "draw", "0": "away"}
SIDE_TO_CODE = {"home": "3", "draw": "1", "away": "0"}
SCHEMA_VERSION = "decision_chain_v4.2.0000_layered_merge_2026-07-05"
DECISION_VERSION = "llm_chain_structured_v4.2.0000_layered_merge"
MAX_TIGHT_CODES = 2
MAX_WIDE_CODES = 3
EXTREME_SP = 8.0
SEVERE_SP_RATIO = 2.0
WATCH_SP_RATIO = 1.45
LATE_REFRESH_HOURS = 4.0

DRAW_EXPLICIT_WORDS = (
    "各取1分",
    "各取一分",
    "平分秋色",
    "握手言和",
    "难分高下",
    "难分胜负",
    "平局",
    "和局",
    "战平",
    "平手",
    "不分胜负",
    "和味",
)
DRAW_BALANCE_WORDS = ("胶着", "僵持", "谨慎", "小球", "低比分", "势均力敌", "接近")
BIG_MARGIN_WORDS = (
    "大胜",
    "狂胜",
    "横扫",
    "至少两球",
    "净胜",
    "穿盘",
    "完胜",
    "大捷",
    "大比分",
    "火力无人能挡",
    "火力全开",
    "攻陷",
)
NARROW_WORDS = ("小胜", "一球", "险胜", "仅胜", "小负")
POSITIVE_WORDS = (
    "取胜",
    "获胜",
    "胜利",
    "胜券",
    "赢球",
    "看好",
    "值得看好",
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
    "连胜",
    "攻陷",
    "主导",
)
NEGATIVE_WORDS = (
    "败绩",
    "乏力",
    "隐患",
    "下滑",
    "失球",
    "平庸",
    "不擅",
    "未尝胜绩",
    "未尝胜",
    "难胜",
    "无胜",
    "防线崩",
    "负率",
    "连败",
)
TEAM_ALIASES = {
    "德里城": ("德利城",),
    "沃特福德FC": ("沃特福德联队",),
    "沙姆洛克流浪者": ("沙姆洛克流浪",),
    "大田韩亚市民": ("大田市民",),
    "大邱FC": ("FC大邱",),
    "FH哈夫纳夫约杜尔": ("夏拿佐杜亚",),
    "斯塔尔南": ("史达兰",),
    "赫德": ("禾特", "贺特"),
    "斯托姆加斯特": ("史卓加斯特",),
    "卡尔马": ("卡马亚",),
    "厄尔格里特": ("奥基迪", "奥尔格里特"),
}
LEAGUE_ALIASES = {
    "K1联赛": "korea_k1",
    "韩K联": "korea_k1",
    "K联赛": "korea_k1",
    "K2联赛": "korea_k2",
    "韩K2": "korea_k2",
    "爱超": "ireland_premier",
    "挪甲": "norway_first",
    "瑞典超": "sweden_allsvenskan",
    "芬甲": "finland_ykkonen",
    "芬兰杯": "finland_cup",
    "世界杯": "world_cup",
    "世外南美": "world_cup_qual_conmebol",
    "冰岛超": "iceland_premier",
}

SEMANTIC_LLM_V4_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema",
        "source",
        "status",
        "alias_resolution",
        "raw_strength",
        "draw_semantics",
        "cover_risk_semantics",
        "competition_context",
        "contradiction_flags",
        "text_digest",
    ],
    "properties": {
        "schema": {"type": "string", "enum": ["semantic_llm_v4_contract"]},
        "source": {"type": "string"},
        "status": {"type": "string", "enum": ["ok", "missing", "invalid"]},
        "alias_resolution": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "home_aliases",
                "away_aliases",
                "known_variant_hits",
                "unresolved_names",
                "alias_resolution_required",
            ],
            "properties": {
                "home_aliases": {"type": "array", "items": {"type": "string"}},
                "away_aliases": {"type": "array", "items": {"type": "string"}},
                "known_variant_hits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["alias", "canonical"],
                        "properties": {
                            "alias": {"type": "string"},
                            "canonical": {"type": "string"},
                        },
                    },
                },
                "unresolved_names": {"type": "array", "items": {"type": "string"}},
                "alias_resolution_required": {"type": "boolean"},
            },
        },
        "raw_strength": {
            "type": "object",
            "additionalProperties": False,
            "required": ["side", "confidence", "evidence"],
            "properties": {
                "side": {"type": "string", "enum": ["home", "away", "draw", "mixed", "unknown"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
        },
        "draw_semantics": {
            "type": "object",
            "additionalProperties": False,
            "required": ["signal", "confidence", "evidence"],
            "properties": {
                "signal": {"type": "string", "enum": ["explicit_draw", "balanced", "low_score", "none"]},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
        },
        "cover_risk_semantics": {
            "type": "object",
            "additionalProperties": False,
            "required": ["side", "risk_type", "codes", "confidence", "evidence"],
            "properties": {
                "side": {"type": "string", "enum": ["home", "away", "draw", "unknown"]},
                "risk_type": {
                    "type": "string",
                    "enum": [
                        "favorite_one_goal_or_cover",
                        "home_favorite_one_goal_or_cover",
                        "away_favorite_one_goal_or_cover",
                        "underdog_survival",
                        "ordinary_draw_translation",
                        "unknown",
                    ],
                },
                "codes": {"type": "array", "items": {"type": "string", "enum": ["3", "1", "0"]}},
                "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
        },
        "competition_context": {
            "type": "object",
            "additionalProperties": False,
            "required": ["league", "headline", "detail_context", "tags", "mismatch", "mismatch_sources"],
            "properties": {
                "league": {"type": "string"},
                "headline": {"type": "string"},
                "detail_context": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "mismatch": {"type": "boolean"},
                "mismatch_sources": {"type": "array", "items": {"type": "string"}},
            },
        },
        "contradiction_flags": {"type": "array", "items": {"type": "string"}},
        "text_digest": {"type": "string"},
    },
}


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
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def pct(value: float | None) -> str:
    return "缺" if value is None else f"{value:.1%}"


def num(value: float | None, digits: int = 2) -> str:
    return "缺" if value is None else f"{value:.{digits}f}"


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for candidate in (text, text.replace("T", " ")):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def compact_text(value: Any) -> str:
    if isinstance(value, list):
        text = "。".join(str(item) for item in value if item)
    elif isinstance(value, dict):
        text = "。".join(str(item) for item in value.values() if isinstance(item, str))
    else:
        text = str(value or "")
    return re.sub(r"\s+", " ", text).strip()


def split_clauses(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。；;，,.!?！？\n\r]+", text) if item.strip()][:80]


def code_text(code: str | None) -> str:
    return OUTCOME_LABEL.get(str(code or ""), "停")


def parse_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[+,/;|\s]+", str(value or ""))
    return [str(code) for code in raw if str(code) in OUTCOME_ORDER]


def row_numeric(row: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    rows: dict[str, dict[str, float | None]] = {}
    for code in OUTCOME_ORDER:
        p = safe_float(row.get(f"p_{code}"))
        sp = safe_float(row.get(f"sp_{code}"))
        q = safe_float(row.get(f"q_{code}"))
        if q is None and p is not None and sp is not None:
            q = p * sp
        rows[code] = {"p": p, "sp": sp, "q": q}
    return rows


def top_code(rows: dict[str, dict[str, float | None]], key: str) -> str | None:
    usable = [(code, safe_float(values.get(key))) for code, values in rows.items()]
    usable = [(code, value) for code, value in usable if value is not None]
    if not usable:
        return None
    return max(usable, key=lambda item: item[1])[0]


def validate_required(mapping: dict[str, Any], keys: tuple[str, ...], *, path: str) -> None:
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise ValueError(f"{path} missing required keys: {', '.join(missing)}")


def semantic_json_schema() -> dict[str, Any]:
    return json.loads(json.dumps(SEMANTIC_LLM_V4_SCHEMA))


def _list_of_strings(value: Any, *, max_items: int = 8) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    return [str(item).strip() for item in raw if str(item or "").strip()][:max_items]


def _list_of_alias_hits(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    hits = []
    for item in value:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("alias") or "").strip()
        canonical = str(item.get("canonical") or "").strip()
        if alias or canonical:
            hits.append({"alias": alias, "canonical": canonical})
    return hits[:8]


def _semantic_side(value: Any, *, allow_mixed: bool = True) -> str:
    allowed = {"home", "away", "draw", "unknown"}
    if allow_mixed:
        allowed.add("mixed")
    text = str(value or "unknown").strip()
    return text if text in allowed else "unknown"


def _semantic_draw_signal(value: Any) -> str:
    text = str(value or "none").strip()
    return text if text in {"explicit_draw", "balanced", "low_score", "none"} else "none"


def _semantic_risk_type(value: Any) -> str:
    text = str(value or "unknown").strip()
    allowed = {
        "favorite_one_goal_or_cover",
        "home_favorite_one_goal_or_cover",
        "away_favorite_one_goal_or_cover",
        "underdog_survival",
        "ordinary_draw_translation",
        "unknown",
    }
    return text if text in allowed else "unknown"


def _semantic_codes(value: Any) -> list[str]:
    return [code for code in parse_codes(value) if code in OUTCOME_ORDER][:3]


def normalize_semantic_contract(raw: dict[str, Any], *, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = fallback or {}
    alias = raw.get("alias_resolution") if isinstance(raw.get("alias_resolution"), dict) else {}
    fallback_alias = fallback.get("alias_resolution") if isinstance(fallback.get("alias_resolution"), dict) else {}
    raw_strength = raw.get("raw_strength") if isinstance(raw.get("raw_strength"), dict) else {}
    fallback_raw = fallback.get("raw_strength") if isinstance(fallback.get("raw_strength"), dict) else {}
    draw = raw.get("draw_semantics") if isinstance(raw.get("draw_semantics"), dict) else {}
    fallback_draw = fallback.get("draw_semantics") if isinstance(fallback.get("draw_semantics"), dict) else {}
    cover = raw.get("cover_risk_semantics") if isinstance(raw.get("cover_risk_semantics"), dict) else {}
    fallback_cover = fallback.get("cover_risk_semantics") if isinstance(fallback.get("cover_risk_semantics"), dict) else {}
    competition = raw.get("competition_context") if isinstance(raw.get("competition_context"), dict) else {}
    fallback_comp = fallback.get("competition_context") if isinstance(fallback.get("competition_context"), dict) else {}
    normalized = {
        "schema": "semantic_llm_v4_contract",
        "source": str(raw.get("source") or fallback.get("source") or "external_semantic"),
        "status": str(raw.get("status") or fallback.get("status") or "ok"),
        "alias_resolution": {
            "home_aliases": _list_of_strings(alias.get("home_aliases") or fallback_alias.get("home_aliases")),
            "away_aliases": _list_of_strings(alias.get("away_aliases") or fallback_alias.get("away_aliases")),
            "known_variant_hits": _list_of_alias_hits(alias.get("known_variant_hits") or fallback_alias.get("known_variant_hits")),
            "unresolved_names": _list_of_strings(alias.get("unresolved_names") or fallback_alias.get("unresolved_names")),
            "alias_resolution_required": bool(alias.get("alias_resolution_required", fallback_alias.get("alias_resolution_required", False))),
        },
        "raw_strength": {
            "side": _semantic_side(raw_strength.get("side", fallback_raw.get("side"))),
            "confidence": round(clamp(safe_float(raw_strength.get("confidence", fallback_raw.get("confidence"))) or 0.0), 3),
            "evidence": _list_of_strings(raw_strength.get("evidence") or fallback_raw.get("evidence"), max_items=6),
        },
        "draw_semantics": {
            "signal": _semantic_draw_signal(draw.get("signal", fallback_draw.get("signal"))),
            "confidence": round(clamp(safe_float(draw.get("confidence", fallback_draw.get("confidence"))) or 0.0), 3),
            "evidence": _list_of_strings(draw.get("evidence") or fallback_draw.get("evidence"), max_items=6),
        },
        "cover_risk_semantics": {
            "side": _semantic_side(cover.get("side", fallback_cover.get("side")), allow_mixed=False),
            "risk_type": _semantic_risk_type(cover.get("risk_type", fallback_cover.get("risk_type"))),
            "codes": _semantic_codes(cover.get("codes") or fallback_cover.get("codes")),
            "confidence": round(clamp(safe_float(cover.get("confidence", fallback_cover.get("confidence"))) or 0.0), 3),
            "evidence": _list_of_strings(cover.get("evidence") or fallback_cover.get("evidence"), max_items=6),
        },
        "competition_context": {
            "league": str(competition.get("league", fallback_comp.get("league", "")) or ""),
            "headline": str(competition.get("headline", fallback_comp.get("headline", "")) or ""),
            "detail_context": str(competition.get("detail_context", fallback_comp.get("detail_context", "")) or ""),
            "tags": _list_of_strings(competition.get("tags") or fallback_comp.get("tags")),
            "mismatch": bool(competition.get("mismatch", fallback_comp.get("mismatch", False))),
            "mismatch_sources": _list_of_strings(competition.get("mismatch_sources") or fallback_comp.get("mismatch_sources")),
        },
        "contradiction_flags": _list_of_strings(raw.get("contradiction_flags") or fallback.get("contradiction_flags"), max_items=10),
        "text_digest": str(raw.get("text_digest") or fallback.get("text_digest") or "")[:1200],
    }
    if normalized["status"] not in {"ok", "missing", "invalid"}:
        normalized["status"] = "ok"
    return normalized


def validate_semantic_contract(semantic: dict[str, Any]) -> None:
    validate_required(
        semantic,
        (
            "schema",
            "source",
            "status",
            "alias_resolution",
            "raw_strength",
            "draw_semantics",
            "cover_risk_semantics",
            "competition_context",
            "contradiction_flags",
            "text_digest",
        ),
        path="semantic",
    )
    if semantic.get("schema") != "semantic_llm_v4_contract":
        raise ValueError("semantic.schema must be semantic_llm_v4_contract")
    if semantic.get("status") not in {"ok", "missing", "invalid"}:
        raise ValueError("semantic.status invalid")
    alias = semantic.get("alias_resolution")
    raw = semantic.get("raw_strength")
    draw = semantic.get("draw_semantics")
    cover = semantic.get("cover_risk_semantics")
    comp = semantic.get("competition_context")
    if not all(isinstance(item, dict) for item in (alias, raw, draw, cover, comp)):
        raise ValueError("semantic nested sections must be objects")
    validate_required(alias, ("home_aliases", "away_aliases", "known_variant_hits", "unresolved_names", "alias_resolution_required"), path="semantic.alias_resolution")
    validate_required(raw, ("side", "confidence", "evidence"), path="semantic.raw_strength")
    validate_required(draw, ("signal", "confidence", "evidence"), path="semantic.draw_semantics")
    validate_required(cover, ("side", "risk_type", "codes", "confidence", "evidence"), path="semantic.cover_risk_semantics")
    validate_required(comp, ("league", "headline", "detail_context", "tags", "mismatch", "mismatch_sources"), path="semantic.competition_context")
    if raw.get("side") not in {"home", "away", "draw", "mixed", "unknown"}:
        raise ValueError("semantic.raw_strength.side invalid")
    if draw.get("signal") not in {"explicit_draw", "balanced", "low_score", "none"}:
        raise ValueError("semantic.draw_semantics.signal invalid")
    if cover.get("side") not in {"home", "away", "draw", "unknown"}:
        raise ValueError("semantic.cover_risk_semantics.side invalid")
    if cover.get("risk_type") not in {
        "favorite_one_goal_or_cover",
        "home_favorite_one_goal_or_cover",
        "away_favorite_one_goal_or_cover",
        "underdog_survival",
        "ordinary_draw_translation",
        "unknown",
    }:
        raise ValueError("semantic.cover_risk_semantics.risk_type invalid")
    for path, value in (
        ("semantic.raw_strength.confidence", raw.get("confidence")),
        ("semantic.draw_semantics.confidence", draw.get("confidence")),
        ("semantic.cover_risk_semantics.confidence", cover.get("confidence")),
    ):
        number = safe_float(value)
        if number is None or not 0.0 <= number <= 1.0:
            raise ValueError(f"{path} must be 0..1")
    for path, value in (
        ("semantic.alias_resolution.home_aliases", alias.get("home_aliases")),
        ("semantic.alias_resolution.away_aliases", alias.get("away_aliases")),
        ("semantic.alias_resolution.unresolved_names", alias.get("unresolved_names")),
        ("semantic.raw_strength.evidence", raw.get("evidence")),
        ("semantic.draw_semantics.evidence", draw.get("evidence")),
        ("semantic.cover_risk_semantics.codes", cover.get("codes")),
        ("semantic.cover_risk_semantics.evidence", cover.get("evidence")),
        ("semantic.competition_context.tags", comp.get("tags")),
        ("semantic.competition_context.mismatch_sources", comp.get("mismatch_sources")),
        ("semantic.contradiction_flags", semantic.get("contradiction_flags")),
    ):
        if not isinstance(value, list):
            raise ValueError(f"{path} must be a list")
    for code in cover.get("codes", []):
        if code not in OUTCOME_ORDER:
            raise ValueError("semantic.cover_risk_semantics.codes invalid")


def validate_decision(decision: dict[str, Any]) -> None:
    validate_required(
        decision,
        (
            "schema_version",
            "decision_version",
            "issue",
            "match_idx",
            "sections",
            "candidate_pool",
            "action",
            "recommended_codes",
            "selection_codes",
            "chain",
        ),
        path="decision",
    )
    sections = decision["sections"]
    if not isinstance(sections, dict):
        raise ValueError("decision.sections must be an object")
    validate_required(
        sections,
        (
            "hard_gates",
            "numeric_context",
            "semantic_llm",
            "handicap_translation",
            "protection_competition",
            "final_policy",
        ),
        path="decision.sections",
    )
    for code in decision["recommended_codes"] + decision["selection_codes"]:
        if code not in OUTCOME_ORDER:
            raise ValueError(f"invalid outcome code: {code}")


def load_structured_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _fetch_one(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row is not None else {}


def fetch_match_context(conn: sqlite3.Connection | None, issue: str, match_idx: int) -> dict[str, Any]:
    if conn is None:
        return {}
    conn.row_factory = sqlite3.Row
    match = _fetch_one(conn, "SELECT * FROM matches WHERE issue=? AND match_idx=?", (issue, match_idx))
    digest = _fetch_one(
        conn,
        """
        SELECT * FROM match_intel_digest
        WHERE issue=? AND match_idx=?
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        (issue, match_idx),
    )
    detail = _fetch_one(
        conn,
        """
        SELECT * FROM nowscore_match_details
        WHERE issue=? AND match_idx=?
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        (issue, match_idx),
    )
    live_sp = _fetch_one(
        conn,
        """
        SELECT * FROM live_sp_snapshots
        WHERE issue=? AND row_idx=?
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        (issue, match_idx),
    )
    snapshot = _fetch_one(
        conn,
        """
        SELECT generated_at, source_timestamps_json, input_payload_json
        FROM llm_decision_snapshots
        WHERE issue=? AND match_idx=? AND status='active'
        ORDER BY generated_at DESC, snapshot_id DESC
        LIMIT 1
        """,
        (issue, match_idx),
    )
    input_payload = safe_json(snapshot.get("input_payload_json"), {}) if snapshot else {}
    source_timestamps = safe_json(snapshot.get("source_timestamps_json"), {}) if snapshot else {}
    return {
        "match": match,
        "digest": digest,
        "detail": detail,
        "live_sp": live_sp,
        "snapshot": snapshot,
        "input_payload": input_payload,
        "source_timestamps": source_timestamps,
    }


def context_text(context: dict[str, Any]) -> str:
    digest = context.get("digest") if isinstance(context.get("digest"), dict) else {}
    detail = context.get("detail") if isinstance(context.get("detail"), dict) else {}
    payload = context.get("input_payload") if isinstance(context.get("input_payload"), dict) else {}
    intelligence = payload.get("intelligence") if isinstance(payload.get("intelligence"), dict) else {}
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    parts = [
        digest.get("headline"),
        digest.get("summary"),
        compact_text(safe_json(digest.get("digest_json"), {}).get("points", [])),
        detail.get("title"),
        detail.get("description"),
        detail.get("kickoff_context"),
        detail.get("home_recent_summary"),
        detail.get("away_recent_summary"),
        detail.get("h2h_summary"),
        detail.get("league_summary"),
        detail.get("panlu_summary"),
        detail.get("market_summary"),
        compact_text(safe_json(detail.get("highlights_json"), [])),
        compact_text(intelligence.get("points")),
        compact_text(analysis.get("highlights")),
    ]
    return "。".join(str(part) for part in parts if str(part or "").strip())


def latest_sp_by_code(context: dict[str, Any]) -> dict[str, float | None]:
    live_sp = context.get("live_sp") if isinstance(context.get("live_sp"), dict) else {}
    match = context.get("match") if isinstance(context.get("match"), dict) else {}
    source = live_sp if live_sp else match
    return {
        "3": safe_float(source.get("sp_home")),
        "1": safe_float(source.get("sp_draw")),
        "0": safe_float(source.get("sp_away")),
    }


def snapshot_match(context: dict[str, Any]) -> dict[str, Any]:
    payload = context.get("input_payload") if isinstance(context.get("input_payload"), dict) else {}
    match = payload.get("match") if isinstance(payload.get("match"), dict) else {}
    return match if isinstance(match, dict) else {}


def hours_to_kickoff(context: dict[str, Any]) -> float | None:
    snapshot = context.get("snapshot") if isinstance(context.get("snapshot"), dict) else {}
    source_ts = context.get("source_timestamps") if isinstance(context.get("source_timestamps"), dict) else {}
    generated = parse_datetime(snapshot.get("generated_at") or source_ts.get("generated_ts") or source_ts.get("calculated_ts"))
    match_payload = snapshot_match(context)
    match_db = context.get("match") if isinstance(context.get("match"), dict) else {}
    kickoff = parse_datetime(match_payload.get("kickoff_ts") or match_db.get("end_time"))
    if generated is None or kickoff is None:
        return None
    return max(0.0, (kickoff - generated).total_seconds() / 3600.0)


def detect_hard_gates(row: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    rows = row_numeric(row)
    latest_sp = latest_sp_by_code(context)
    q_top = str(row.get("q_top") or top_code(rows, "q") or "")
    p_top = str(row.get("prob_top") or top_code(rows, "p") or "")
    sp_diffs: dict[str, dict[str, Any]] = {}
    severe_codes: list[str] = []
    watch_codes: list[str] = []
    for code in OUTCOME_ORDER:
        csv_sp = rows[code].get("sp")
        ref_sp = latest_sp.get(code)
        if not csv_sp or not ref_sp:
            continue
        ratio = max(float(csv_sp) / float(ref_sp), float(ref_sp) / float(csv_sp))
        entry = {"csv_sp": round(float(csv_sp), 4), "latest_sp": round(float(ref_sp), 4), "ratio": round(ratio, 4)}
        sp_diffs[code] = entry
        if ratio >= SEVERE_SP_RATIO:
            severe_codes.append(code)
        elif ratio >= WATCH_SP_RATIO:
            watch_codes.append(code)

    csv_extreme_codes = [code for code, values in rows.items() if (values.get("sp") or 0.0) >= EXTREME_SP]
    latest_extreme_codes = [code for code, value in latest_sp.items() if (value or 0.0) >= EXTREME_SP]
    h_to_kickoff = hours_to_kickoff(context)
    extreme_codes = sorted(set(csv_extreme_codes + latest_extreme_codes))
    requires_late_refresh = bool(extreme_codes) and (h_to_kickoff is None or h_to_kickoff > LATE_REFRESH_HOURS)

    match_db = context.get("match") if isinstance(context.get("match"), dict) else {}
    match_payload = snapshot_match(context)
    payload_disabled = str(match_payload.get("disabled") or "").lower() in {"yes", "true", "1", "disabled"}
    db_disabled = str(match_db.get("disabled") or "").lower() in {"yes", "true", "1", "disabled"}
    hard_stop = payload_disabled

    risk_tags: list[str] = []
    if hard_stop:
        risk_tags.append("payload_disabled")
    elif db_disabled:
        risk_tags.append("db_disabled_current_state_only")
    if severe_codes:
        risk_tags.append("sp_source_conflict_severe")
    elif watch_codes:
        risk_tags.append("sp_source_conflict_watch")
    if csv_extreme_codes:
        risk_tags.append("csv_extreme_sp")
    if latest_extreme_codes:
        risk_tags.append("latest_extreme_sp")
    if requires_late_refresh:
        risk_tags.append("requires_late_refresh")

    return {
        "status": "stop" if hard_stop else "requires_late_refresh" if requires_late_refresh else "allow",
        "risk_tags": risk_tags,
        "q_top": q_top if q_top in OUTCOME_ORDER else None,
        "p_top": p_top if p_top in OUTCOME_ORDER else None,
        "csv_extreme_codes": csv_extreme_codes,
        "latest_extreme_codes": latest_extreme_codes,
        "sp_source_conflict_codes": severe_codes,
        "sp_source_watch_codes": watch_codes,
        "sp_unstable_codes": extreme_codes,
        "sp_diffs": sp_diffs,
        "latest_sp": latest_sp,
        "hours_to_kickoff_at_decision": round(h_to_kickoff, 2) if h_to_kickoff is not None else None,
        "hard_stop_reasons": ["payload disabled at decision input"] if hard_stop else [],
        "soft_stop_reasons": ["current DB disabled only; do not infer pre-match stop"] if db_disabled and not hard_stop else [],
    }


def _league_key(label: str) -> str:
    for raw, key in LEAGUE_ALIASES.items():
        if raw and raw in label:
            return key
    return re.sub(r"\s+", "", label)


def _headline_league(headline: str) -> str:
    if "·" in headline:
        return headline.split("·", 1)[0].strip()
    if " " in headline:
        return headline.split(" ", 1)[0].strip()
    return headline.strip()


def detect_competition_context(row: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    match_db = context.get("match") if isinstance(context.get("match"), dict) else {}
    digest = context.get("digest") if isinstance(context.get("digest"), dict) else {}
    detail = context.get("detail") if isinstance(context.get("detail"), dict) else {}
    row_league = str(row.get("league") or match_db.get("league") or "")
    headline = str(digest.get("headline") or "")
    detail_context = str(detail.get("kickoff_context") or "")
    digest_league = _headline_league(headline)
    detail_league = detail_context.split(" ", 1)[0].strip() if detail_context else ""
    row_key = _league_key(row_league)
    digest_key = _league_key(digest_league)
    detail_key = _league_key(detail_league)
    mismatch_sources = []
    if digest_league and digest_key != row_key:
        mismatch_sources.append(f"digest:{digest_league}")
    if detail_league and detail_key != row_key:
        mismatch_sources.append(f"detail:{detail_league}")
    tags = []
    if "杯" in headline or "杯" in row_league:
        tags.append("cup")
    if any(word in headline for word in ("决赛", "1/16", "半决赛", "淘汰")):
        tags.append("knockout")
    return {
        "league": row_league,
        "headline": headline,
        "detail_context": detail_context,
        "tags": tags,
        "mismatch": bool(mismatch_sources),
        "mismatch_sources": mismatch_sources,
    }


def detect_alias_resolution(row: dict[str, Any], text: str) -> dict[str, Any]:
    home = str(row.get("home") or "")
    away = str(row.get("away") or "")

    def aliases_for(team: str) -> list[str]:
        aliases = [team] if team else []
        aliases.extend(TEAM_ALIASES.get(team, ()))
        return [item for item in aliases if item]

    home_aliases = [alias for alias in aliases_for(home) if alias in text]
    away_aliases = [alias for alias in aliases_for(away) if alias in text]
    known_variant_hits = []
    for canonical, aliases in TEAM_ALIASES.items():
        for alias in aliases:
            if alias in text:
                known_variant_hits.append({"alias": alias, "canonical": canonical})
    unresolved = []
    if home and not home_aliases:
        unresolved.append(home)
    if away and not away_aliases:
        unresolved.append(away)
    alias_required = any(item["alias"] != item["canonical"] for item in known_variant_hits)
    return {
        "home_aliases": home_aliases,
        "away_aliases": away_aliases,
        "known_variant_hits": known_variant_hits,
        "unresolved_names": unresolved,
        "alias_resolution_required": alias_required,
    }


def _record_score(text: str) -> float | None:
    match = re.search(r"近10场\s*(\d+)胜(\d+)平(\d+)负", text)
    if not match:
        return None
    wins, draws, losses = (int(value) for value in match.groups())
    return wins - losses + draws * 0.25


def _extract_rank_from_league_summary(text: str, team: str) -> int | None:
    if not team:
        return None
    pattern = re.escape(team) + r"[^|]{0,80}?排名(\d+)"
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def _score_team_text(text: str, aliases: list[str]) -> tuple[float, list[str]]:
    score = 0.0
    evidence: list[str] = []
    for clause in split_clauses(text):
        if not any(alias and alias in clause for alias in aliases):
            continue
        targeted_negative = any(
            re.search(r"(?:攻陷|击败|战胜|轻取|大胜).{0,4}" + re.escape(alias), clause)
            or re.search(re.escape(alias) + r".{0,6}(?:被攻陷|落败|惨败|防线崩)", clause)
            for alias in aliases
            if alias
        )
        if targeted_negative:
            score -= 1.8
            evidence.append(clause)
            continue
        pos = sum(1 for word in POSITIVE_WORDS if word in clause)
        neg = sum(1 for word in NEGATIVE_WORDS if word in clause)
        if pos:
            score += min(2.5, pos)
            evidence.append(clause)
        if neg:
            score -= min(2.0, neg) * 0.8
            evidence.append(clause)
    return score, evidence[:4]


def classify_raw_strength_v4(row: dict[str, Any], context: dict[str, Any], alias_resolution: dict[str, Any]) -> dict[str, Any]:
    text = context_text(context)
    match_db = context.get("match") if isinstance(context.get("match"), dict) else {}
    detail = context.get("detail") if isinstance(context.get("detail"), dict) else {}
    scores = {"home": 0.0, "draw": 0.0, "away": 0.0}
    evidence = {"home": [], "draw": [], "away": []}

    csv_raw = str(row.get("raw_strength_side") or "")
    if csv_raw in scores:
        scores[csv_raw] += 1.2
        evidence[csv_raw].append(f"v3.3.3 raw_strength_side={csv_raw}")

    home_rank = safe_float(match_db.get("home_rank"))
    away_rank = safe_float(match_db.get("away_rank"))
    if home_rank and away_rank and home_rank > 0 and away_rank > 0:
        rank_gap = abs(home_rank - away_rank)
        if rank_gap >= 3:
            side = "home" if home_rank < away_rank else "away"
            weight = clamp(0.35 + rank_gap * 0.045, 0.35, 1.35)
            scores[side] += weight
            evidence[side].append(f"排名差：主{int(home_rank)} / 客{int(away_rank)}。")

    league_summary = str(detail.get("league_summary") or "")
    if league_summary:
        home = str(row.get("home") or "")
        away = str(row.get("away") or "")
        home_rank2 = _extract_rank_from_league_summary(league_summary, home)
        away_rank2 = _extract_rank_from_league_summary(league_summary, away)
        if home_rank2 and away_rank2 and abs(home_rank2 - away_rank2) >= 3:
            side = "home" if home_rank2 < away_rank2 else "away"
            scores[side] += clamp(0.30 + abs(home_rank2 - away_rank2) * 0.04, 0.30, 1.10)
            evidence[side].append(f"积分榜摘要：主{home_rank2} / 客{away_rank2}。")

    avg_home = safe_float(match_db.get("avg_odds_home"))
    avg_away = safe_float(match_db.get("avg_odds_away"))
    if avg_home and avg_away:
        odds_ratio = max(avg_home / avg_away, avg_away / avg_home)
        if odds_ratio >= 1.35:
            side = "home" if avg_home < avg_away else "away"
            scores[side] += clamp(0.40 + (odds_ratio - 1.0) * 0.18, 0.40, 1.35)
            evidence[side].append(f"欧赔均值强弱：主{avg_home:.2f} / 客{avg_away:.2f}。")

    home_recent = str(detail.get("home_recent_summary") or "")
    away_recent = str(detail.get("away_recent_summary") or "")
    home_form = _record_score(home_recent)
    away_form = _record_score(away_recent)
    if home_form is not None and away_form is not None:
        diff = home_form - away_form
        if abs(diff) >= 2.0:
            side = "home" if diff > 0 else "away"
            scores[side] += clamp(abs(diff) * 0.12, 0.25, 0.95)
            evidence[side].append(f"近况差：{home_recent} / {away_recent}")
        if "平" in home_recent and "平" in away_recent:
            draw_points = sum(int(v) for v in re.findall(r"近10场\s*\d+胜(\d+)平", home_recent + " " + away_recent))
            if draw_points >= 7:
                scores["draw"] += 0.40
                evidence["draw"].append("两队近10场平局数量合计偏高。")

    home_aliases = alias_resolution.get("home_aliases") or [str(row.get("home") or "")]
    away_aliases = alias_resolution.get("away_aliases") or [str(row.get("away") or "")]
    home_text_score, home_text_evidence = _score_team_text(text, [str(item) for item in home_aliases])
    away_text_score, away_text_evidence = _score_team_text(text, [str(item) for item in away_aliases])
    if home_text_score > 0:
        scores["home"] += home_text_score
        evidence["home"].extend(home_text_evidence)
    elif home_text_score < 0:
        scores["away"] += min(1.0, abs(home_text_score) * 0.5)
        evidence["away"].extend(home_text_evidence)
    if away_text_score > 0:
        scores["away"] += away_text_score
        evidence["away"].extend(away_text_evidence)
    elif away_text_score < 0:
        scores["home"] += min(1.0, abs(away_text_score) * 0.5)
        evidence["home"].extend(away_text_evidence)

    for clause in split_clauses(text):
        if "主队防线崩" in clause or "主队" in clause and "防线崩" in clause:
            scores["away"] += 0.8
            evidence["away"].append(clause)
        if "客队" in clause and any(word in clause for word in POSITIVE_WORDS):
            scores["away"] += 0.4
            evidence["away"].append(clause)
        if "主队" in clause and any(word in clause for word in POSITIVE_WORDS):
            scores["home"] += 0.4
            evidence["home"].append(clause)

    if any(word in text for word in DRAW_EXPLICIT_WORDS):
        scores["draw"] += 1.4
        evidence["draw"].extend([clause for clause in split_clauses(text) if any(word in clause for word in DRAW_EXPLICIT_WORDS)][:3])

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    side, score = ranked[0]
    runner_up = ranked[1][1]
    if score <= 0.30 or score - runner_up < 0.20:
        side_out: str | None = None
        confidence = 0.0
    else:
        side_out = side
        confidence = clamp(0.38 + score * 0.065 + (score - runner_up) * 0.08, 0.38, 0.88)
    return {
        "side": side_out,
        "confidence": round(confidence, 3),
        "score": round(score if side_out else 0.0, 3),
        "raw_scores": {key: round(value, 3) for key, value in scores.items()},
        "evidence": evidence.get(side, [])[:5] if side_out else [],
    }


def classify_draw_semantics(text: str, detail: dict[str, Any]) -> dict[str, Any]:
    explicit_clauses = [clause for clause in split_clauses(text) if any(word in clause for word in DRAW_EXPLICIT_WORDS)]
    if explicit_clauses:
        return {
            "signal": "explicit_draw",
            "confidence": 0.82,
            "evidence": explicit_clauses[:4],
        }
    balanced_clauses = [clause for clause in split_clauses(text) if any(word in clause for word in DRAW_BALANCE_WORDS)]
    home_recent = str(detail.get("home_recent_summary") or "")
    away_recent = str(detail.get("away_recent_summary") or "")
    draw_counts = [int(value) for value in re.findall(r"近10场\s*\d+胜(\d+)平", home_recent + " " + away_recent)]
    if balanced_clauses or (len(draw_counts) >= 2 and sum(draw_counts) >= 7):
        evidence = balanced_clauses[:3]
        if draw_counts:
            evidence.append(f"近10场平局数合计 {sum(draw_counts)}。")
        return {
            "signal": "balanced",
            "confidence": 0.58 if balanced_clauses else 0.52,
            "evidence": evidence[:4],
        }
    return {"signal": "none", "confidence": 0.0, "evidence": []}


def extract_semantic_llm(row: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    text = context_text(context)
    detail = context.get("detail") if isinstance(context.get("detail"), dict) else {}
    alias_resolution = detect_alias_resolution(row, text)
    competition = detect_competition_context(row, context)
    raw_strength = classify_raw_strength_v4(row, context, alias_resolution)
    draw_semantics = classify_draw_semantics(text, detail)
    normalized_raw_side = _semantic_side(raw_strength.get("side"))
    normalized_draw_signal = _semantic_draw_signal(draw_semantics.get("signal"))
    contradiction_flags = []
    if competition.get("mismatch"):
        contradiction_flags.append("competition_context_mismatch")
    if alias_resolution.get("alias_resolution_required"):
        contradiction_flags.append("team_alias_resolution_required")
    if alias_resolution.get("unresolved_names"):
        contradiction_flags.append("team_name_unresolved")

    return {
        "schema": "semantic_llm_v4_contract",
        "source": "rule_proxy_llm_ready",
        "status": "ok" if text else "missing",
        "alias_resolution": alias_resolution,
        "raw_strength": {
            "side": normalized_raw_side,
            "confidence": raw_strength.get("confidence", 0.0),
            "evidence": raw_strength.get("evidence", []),
            "score": raw_strength.get("score", 0.0),
            "raw_scores": raw_strength.get("raw_scores", {}),
        },
        "draw_semantics": {
            "signal": normalized_draw_signal,
            "confidence": draw_semantics.get("confidence", 0.0),
            "evidence": draw_semantics.get("evidence", []),
        },
        "cover_risk_semantics": {
            "side": "unknown",
            "risk_type": "unknown",
            "codes": [],
            "confidence": 0.0,
            "evidence": [],
        },
        "competition_context": competition,
        "contradiction_flags": contradiction_flags,
        "text_digest": text[:600],
    }


def ordinary_draw_code(handicap: float) -> str:
    if handicap > 0.25:
        return "3"
    if handicap < -0.25:
        return "0"
    return "1"


def has_big_margin_text(text: str) -> bool:
    return any(word in text for word in BIG_MARGIN_WORDS)


def has_narrow_text(text: str) -> bool:
    return any(word in text for word in NARROW_WORDS + DRAW_BALANCE_WORDS)


def translate_handicap(row: dict[str, Any], context: dict[str, Any], semantic: dict[str, Any]) -> dict[str, Any]:
    handicap = safe_float(row.get("handicap_line"))
    if handicap is None:
        handicap = safe_float((context.get("match") or {}).get("handicap_line")) or 0.0
    text = context_text(context)
    raw_strength = semantic.get("raw_strength") if isinstance(semantic.get("raw_strength"), dict) else {}
    draw_semantics = semantic.get("draw_semantics") if isinstance(semantic.get("draw_semantics"), dict) else {}
    side = str(raw_strength.get("side") or "")
    raw_conf = safe_float(raw_strength.get("confidence")) or 0.0
    draw_conf = safe_float(draw_semantics.get("confidence")) or 0.0
    translations: list[dict[str, Any]] = []

    def add_translation(code: str, kind: str, confidence: float, reason: str, mandatory: bool = False) -> None:
        if code not in OUTCOME_ORDER:
            return
        translations.append(
            {
                "code": code,
                "kind": kind,
                "confidence": round(clamp(confidence), 3),
                "mandatory": bool(mandatory),
                "reason": reason,
            }
        )

    if draw_semantics.get("signal") in {"explicit_draw", "balanced"} and draw_conf >= 0.50:
        code = ordinary_draw_code(handicap)
        add_translation(
            code,
            "ordinary_draw_translation",
            draw_conf,
            f"语义指向常规平局/均势，按北单让球 {num(handicap, 0)} 映射到 {code_text(code)}。",
            mandatory=draw_semantics.get("signal") == "explicit_draw" and abs(handicap) < 0.25 and draw_conf >= 0.70,
        )

    big_margin = has_big_margin_text(text)
    narrow = has_narrow_text(text)
    if side == "draw":
        add_translation("1" if abs(handicap) < 0.25 else ordinary_draw_code(handicap), "raw_draw", raw_conf, "原始语义强弱为平衡/平局。", mandatory=abs(handicap) < 0.25 and raw_conf >= 0.70)
    elif side in {"home", "away"}:
        if abs(handicap) < 0.25:
            add_translation(SIDE_TO_CODE[side], "raw_strength_direct", raw_conf, "让球为0，原始强弱方向可直接映射。", mandatory=raw_conf >= 0.72)
        elif handicap > 0 and side == "home":
            add_translation("3", "underdog_or_home_strength_survival", raw_conf * 0.95, "主队受让且原始主队不弱，映射为让球胜。", mandatory=raw_conf >= 0.72)
        elif handicap > 0 and side == "away":
            one_goal_mandatory = raw_conf >= 0.58 and abs(handicap) < 1.75
            add_translation("1", "favorite_one_goal_win", raw_conf * (0.92 if narrow else 0.84), "客队强但主队受让，先纳入客队一球小胜的让球平。", mandatory=one_goal_mandatory)
            add_translation("0", "favorite_cover_win", raw_conf * (0.92 if big_margin else 0.82), "客队强且主队受让，必须单独评估客队穿过受让的让球负。", mandatory=raw_conf >= 0.64)
        elif handicap < 0 and side == "home":
            one_goal_mandatory = raw_conf >= 0.58 and abs(handicap) < 1.75
            add_translation("1", "favorite_one_goal_win", raw_conf * (0.92 if narrow else 0.84), "主队强但主队让球，先纳入主队一球小胜的让球平。", mandatory=one_goal_mandatory)
            add_translation("3", "favorite_cover_win", raw_conf * (0.92 if big_margin else 0.76), "主队强且主队让球，评估主队穿盘后的让球胜。", mandatory=raw_conf >= 0.70 and big_margin)
        elif handicap < 0 and side == "away":
            add_translation("0", "away_strength_against_home_handicap", raw_conf * 0.92, "主队让球但客队方向更强，映射为让球负。", mandatory=raw_conf >= 0.66)

    cover_risk = {"side": None, "risk_type": None, "codes": [], "confidence": 0.0, "evidence": []}
    if handicap > 0 and side == "away" and raw_conf >= 0.50:
        cover_risk = {
            "side": "away",
            "risk_type": "away_favorite_one_goal_or_cover",
            "codes": ["1", "0"],
            "confidence": round(raw_conf, 3),
            "evidence": ["受让一球时，客队强势必须拆成一球小胜(1)和穿盘(0)，不能只保让球平。"],
        }
    elif handicap < 0 and side == "home" and raw_conf >= 0.50:
        cover_risk = {
            "side": "home",
            "risk_type": "home_favorite_one_goal_or_cover",
            "codes": ["1", "3"],
            "confidence": round(raw_conf, 3),
            "evidence": ["让一球时，主队强势必须拆成一球小胜(1)和穿盘(3)。"],
        }

    llm_cover = semantic.get("cover_risk_semantics") if isinstance(semantic.get("cover_risk_semantics"), dict) else {}
    llm_cover_codes = [code for code in llm_cover.get("codes", []) if code in OUTCOME_ORDER] if isinstance(llm_cover.get("codes"), list) else []
    llm_cover_conf = safe_float(llm_cover.get("confidence")) or 0.0
    if cover_risk["risk_type"] is None and llm_cover_codes and llm_cover_conf >= 0.60:
        cover_risk = {
            "side": _semantic_side(llm_cover.get("side"), allow_mixed=False),
            "risk_type": _semantic_risk_type(llm_cover.get("risk_type")),
            "codes": llm_cover_codes,
            "confidence": round(llm_cover_conf, 3),
            "evidence": ["LLM cover_risk 只作诊断，不直接增加候选码。"]
            + _list_of_strings(llm_cover.get("evidence"), max_items=3),
        }

    return {
        "handicap_line": handicap,
        "translations": translations,
        "cover_risk_semantics": cover_risk,
    }


def _side_primary_support_codes(side: str, handicap: float) -> tuple[list[str], list[str]]:
    if side == "home":
        if handicap < -0.25:
            return ["3"], ["1"]
        return ["3"], []
    if side == "away":
        if handicap > 0.25:
            return ["0"], ["1"]
        return ["0"], []
    if side == "draw":
        return [ordinary_draw_code(handicap)], []
    return [], []


def _row_precomputed_code_side(code: str | None, handicap: float) -> str:
    if code == "3":
        return "home"
    if code == "0":
        return "away"
    if code == "1":
        if handicap < -0.25:
            return "home"
        if handicap > 0.25:
            return "away"
        return "draw"
    return "unknown"


def _odds_pair_from_context(context: dict[str, Any]) -> tuple[float | None, float | None, str]:
    detail = context.get("detail") if isinstance(context.get("detail"), dict) else {}
    odds_consensus = safe_json(detail.get("odds_consensus_json"), {})
    if isinstance(odds_consensus, dict):
        current = odds_consensus.get("current_avg") if isinstance(odds_consensus.get("current_avg"), dict) else {}
        home = safe_float(current.get("home"))
        away = safe_float(current.get("away"))
        if home and away:
            return home, away, "nowscore_current_avg"
        opened = odds_consensus.get("open_avg") if isinstance(odds_consensus.get("open_avg"), dict) else {}
        home = safe_float(opened.get("home"))
        away = safe_float(opened.get("away"))
        if home and away:
            return home, away, "nowscore_open_avg"

    match_db = context.get("match") if isinstance(context.get("match"), dict) else {}
    home = safe_float(match_db.get("avg_odds_home"))
    away = safe_float(match_db.get("avg_odds_away"))
    if home and away:
        return home, away, "match_avg_odds"
    return None, None, ""


def _h2h_score(text: str) -> float | None:
    match = re.search(r"近10次交锋主队视角\s*(\d+)胜(\d+)平(\d+)负", text)
    if not match:
        return None
    wins, draws, losses = (int(value) for value in match.groups())
    return wins - losses + draws * 0.15


def _team_strength_signal_codes(side: str, handicap: float) -> tuple[list[str], list[str]]:
    primary, support = _side_primary_support_codes(side, handicap)
    return [code for code in primary if code in OUTCOME_ORDER], [code for code in support if code in OUTCOME_ORDER]


def detect_team_strength_sanity(
    row: dict[str, Any],
    context: dict[str, Any],
    semantic: dict[str, Any],
    translation: dict[str, Any],
) -> dict[str, Any]:
    handicap = safe_float(translation.get("handicap_line")) or 0.0
    match_db = context.get("match") if isinstance(context.get("match"), dict) else {}
    detail = context.get("detail") if isinstance(context.get("detail"), dict) else {}
    rows = row_numeric(row)
    p_top = str(row.get("prob_top") or top_code(rows, "p") or "")
    q_top = str(row.get("q_top") or top_code(rows, "q") or "")
    scores = {"home": 0.0, "away": 0.0, "draw": 0.0}
    evidence_by_side: dict[str, list[str]] = {"home": [], "away": [], "draw": []}
    code_scores = {code: 0.0 for code in OUTCOME_ORDER}
    signal_sides: dict[str, str] = {}

    def add_side_signal(side: str, weight: float, source: str, evidence: str) -> None:
        if side not in scores or weight <= 0:
            return
        scores[side] += weight
        signal_sides[source] = side
        evidence_by_side[side].append(f"{source}: {evidence}")
        primary_codes, support_codes = _team_strength_signal_codes(side, handicap)
        for code in primary_codes:
            code_scores[code] += weight
        for code in support_codes:
            code_scores[code] += weight * 0.55

    odds_home, odds_away, odds_source = _odds_pair_from_context(context)
    if odds_home and odds_away:
        odds_ratio = max(odds_home / odds_away, odds_away / odds_home)
        if odds_ratio >= 1.35:
            side = "home" if odds_home < odds_away else "away"
            weight = clamp(0.85 + (odds_ratio - 1.35) * 0.28, 0.85, 1.70)
            add_side_signal(side, weight, "odds_consensus", f"{odds_source} 主{odds_home:.3f}/客{odds_away:.3f}")

    home_rank = safe_float(match_db.get("home_rank"))
    away_rank = safe_float(match_db.get("away_rank"))
    if home_rank and away_rank and home_rank > 0 and away_rank > 0:
        rank_gap = abs(home_rank - away_rank)
        if rank_gap >= 3:
            side = "home" if home_rank < away_rank else "away"
            weight = clamp(0.40 + rank_gap * 0.06, 0.40, 1.15)
            add_side_signal(side, weight, "rank_gap", f"主{int(home_rank)} / 客{int(away_rank)}")

    home_recent = str(detail.get("home_recent_summary") or "")
    away_recent = str(detail.get("away_recent_summary") or "")
    home_form = _record_score(home_recent)
    away_form = _record_score(away_recent)
    if home_form is not None and away_form is not None:
        diff = home_form - away_form
        if abs(diff) >= 1.5:
            side = "home" if diff > 0 else "away"
            weight = clamp(0.30 + abs(diff) * 0.12, 0.30, 1.05)
            add_side_signal(side, weight, "recent_form", f"{home_recent} / {away_recent}")

    h2h = _h2h_score(str(detail.get("h2h_summary") or ""))
    if h2h is not None and abs(h2h) >= 1.8:
        side = "home" if h2h > 0 else "away"
        weight = clamp(0.35 + abs(h2h) * 0.08, 0.35, 0.95)
        add_side_signal(side, weight, "h2h", str(detail.get("h2h_summary") or ""))

    precomputed_code = str(row.get("form_recent_mapped_code") or row.get("form_recent_code") or "")
    precomputed_confidence = safe_float(row.get("form_recent_confidence")) or 0.0
    precomputed_side = _row_precomputed_code_side(precomputed_code, handicap)
    if precomputed_code in OUTCOME_ORDER and precomputed_confidence >= 0.38:
        weight = clamp(precomputed_confidence * 1.20, 0.40, 0.95)
        add_side_signal(precomputed_side, weight, "precomputed_form_code", f"{precomputed_code} conf={precomputed_confidence:.3f}")
        code_scores[precomputed_code] += weight * 0.35

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    side, top_score = ranked[0]
    runner_score = ranked[1][1]
    if top_score < 0.55:
        side = "unknown"
        confidence = 0.0
    elif top_score - runner_score < 0.20:
        side = "balanced"
        confidence = clamp(0.40 + top_score * 0.05, 0.40, 0.58)
    else:
        confidence = clamp(0.40 + top_score * 0.10 + (top_score - runner_score) * 0.08, 0.40, 0.90)

    primary_codes, support_codes = _team_strength_signal_codes(side, handicap)
    sorted_code_scores = sorted(code_scores.items(), key=lambda item: item[1], reverse=True)
    contradiction_flags: list[str] = []
    semantic_comp = semantic.get("competition_context") if isinstance(semantic.get("competition_context"), dict) else {}
    if semantic_comp.get("mismatch"):
        contradiction_flags.append("competition_context_mismatch")
    if primary_codes and p_top in OUTCOME_ORDER and p_top not in primary_codes + support_codes:
        contradiction_flags.append("team_strength_vs_model_probability")
    if primary_codes and q_top in OUTCOME_ORDER and q_top not in primary_codes + support_codes:
        contradiction_flags.append("team_strength_vs_q_top")
    market_side = signal_sides.get("odds_consensus")
    if market_side and precomputed_side in {"home", "away", "draw"} and market_side != precomputed_side:
        contradiction_flags.append("market_vs_precomputed_form_split")
    raw_strength = semantic.get("raw_strength") if isinstance(semantic.get("raw_strength"), dict) else {}
    raw_side = str(raw_strength.get("side") or "")
    raw_conf = safe_float(raw_strength.get("confidence")) or 0.0
    if raw_side in {"home", "away"} and side in {"home", "away"} and raw_side != side and raw_conf >= 0.55:
        contradiction_flags.append("team_strength_vs_semantic_raw")

    return {
        "side": side,
        "confidence": round(confidence, 3),
        "side_scores": {key: round(value, 3) for key, value in scores.items()},
        "code_scores": {key: round(value, 3) for key, value in code_scores.items()},
        "primary_codes": primary_codes,
        "support_codes": support_codes,
        "top_code_by_strength": sorted_code_scores[0][0] if sorted_code_scores and sorted_code_scores[0][1] > 0 else None,
        "precomputed_code": precomputed_code if precomputed_code in OUTCOME_ORDER else None,
        "precomputed_confidence": round(precomputed_confidence, 3),
        "signal_sides": signal_sides,
        "contradiction_flags": sorted(set(contradiction_flags)),
        "evidence": evidence_by_side.get(side if side in evidence_by_side else ranked[0][0], [])[:6],
    }


def add_candidate(
    candidates: dict[str, dict[str, Any]],
    code: str | None,
    weight: float,
    signal: str,
    evidence: str,
    *,
    status: str = "active",
    mandatory: bool = False,
) -> None:
    if code not in OUTCOME_ORDER or weight <= 0:
        return
    candidate = candidates[str(code)]
    if status == "pending":
        candidate["pending_score"] += weight
        candidate["pending_signals"].append(signal)
    else:
        candidate["score"] += weight
        candidate["signals"].append(signal)
    if mandatory:
        candidate["mandatory"] = True
        candidate["mandatory_reasons"].append(signal)
    candidate["evidence"].append(evidence)


def protect_candidate(candidates: dict[str, dict[str, Any]], code: str | None, reason: str) -> None:
    if code not in OUTCOME_ORDER:
        return
    candidate = candidates[str(code)]
    candidate["protected"] = True
    candidate["protected_reasons"].append(reason)


def build_candidate_pool(
    row: dict[str, Any],
    context: dict[str, Any],
    gates: dict[str, Any],
    semantic: dict[str, Any],
    translation: dict[str, Any],
) -> dict[str, Any]:
    rows = row_numeric(row)
    p_top = gates.get("p_top") or top_code(rows, "p")
    q_top = gates.get("q_top") or top_code(rows, "q")
    handicap = safe_float(translation.get("handicap_line")) or 0.0
    p_values = {code: rows[code].get("p") or 0.0 for code in OUTCOME_ORDER}
    sorted_p = sorted(p_values.items(), key=lambda item: item[1], reverse=True)
    primary_p = sorted_p[0][1] if sorted_p else 0.0
    sp_unstable = set(gates.get("sp_unstable_codes") or [])
    candidates = {
        code: {
            "code": code,
            "score": 0.0,
            "pending_score": 0.0,
            "signals": [],
            "pending_signals": [],
            "evidence": [],
            "mandatory": False,
            "mandatory_reasons": [],
            "protected": False,
            "protected_reasons": [],
            "model_p": rows[code].get("p"),
            "sp": rows[code].get("sp"),
            "q": rows[code].get("q"),
        }
        for code in OUTCOME_ORDER
    }

    for code, values in rows.items():
        p = values.get("p") or 0.0
        q = values.get("q") or 0.0
        add_candidate(candidates, code, p * 1.65, "model_probability", f"模型概率 {code_text(code)}={pct(p)}")
        if code == p_top:
            add_candidate(candidates, code, 0.25, "model_top", f"模型概率最高为 {code_text(code)}。", mandatory=p >= 0.50)
            if code == q_top and (abs(handicap) >= 1.75 or p >= 0.47):
                protect_candidate(candidates, code, "model_q_top_agree")
            elif p >= 0.47:
                protect_candidate(candidates, code, "model_top_strong")
        if q >= 1.0:
            status = "pending" if code in sp_unstable else "active"
            add_candidate(
                candidates,
                code,
                min(0.45, max(0.05, (q - 0.80) * 0.28)),
                "market_q_ev",
                f"q={num(q)}，SP={num(values.get('sp'))}" + ("；SP 待临场复核。" if status == "pending" else ""),
                status=status,
            )
            if code == q_top and status == "active" and abs(handicap) >= 1.75 and q >= 1.18 and p >= 0.26:
                protect_candidate(candidates, code, "q_top_value")

    if len(sorted_p) >= 2:
        runner_code, runner_p = sorted_p[1]
        gap = max(0.0, primary_p - runner_p)
        runner_q = rows[runner_code].get("q") or 0.0
        if runner_p >= 0.30 and gap <= 0.14 and runner_q >= 0.60:
            add_candidate(
                candidates,
                runner_code,
                0.32,
                "probability_runner_up_protection",
                f"第二概率 {code_text(runner_code)}={pct(runner_p)}，与第一差 {pct(gap)}。",
            )

    for item in translation.get("translations", []):
        code = str(item.get("code") or "")
        confidence = safe_float(item.get("confidence")) or 0.0
        weight = 0.95 * confidence
        if item.get("kind") in {"favorite_cover_win", "favorite_one_goal_win"}:
            weight += 0.15
        add_candidate(
            candidates,
            code,
            weight,
            "handicap_translation:" + str(item.get("kind") or ""),
            str(item.get("reason") or ""),
            mandatory=bool(item.get("mandatory")),
        )

    draw_semantics = semantic.get("draw_semantics") if isinstance(semantic.get("draw_semantics"), dict) else {}
    raw_strength = semantic.get("raw_strength") if isinstance(semantic.get("raw_strength"), dict) else {}
    if gates.get("status") == "requires_late_refresh":
        draw_p = rows["1"].get("p") or 0.0
        if abs(handicap) < 0.25 and draw_p >= 0.23:
            add_candidate(candidates, "1", 0.28, "late_refresh_neighbor_draw", "极值/冲突 SP 下，平局作为不依赖异常 SP 的相邻保护。")
        elif handicap > 0 and raw_strength.get("side") == "away":
            add_candidate(candidates, "1", 0.24, "late_refresh_handicap_draw", "客队强+主队受让时，极值 SP 下先保护让球平。")
        elif handicap < 0 and raw_strength.get("side") == "home":
            add_candidate(candidates, "1", 0.24, "late_refresh_handicap_draw", "主队强+主队让球时，极值 SP 下先保护让球平。")

    if draw_semantics.get("signal") == "explicit_draw" and abs(handicap) < 0.25:
        add_candidate(candidates, "1", 0.18, "mandatory_explicit_draw_guard", "明确平局语义在让球0时必须入候选。", mandatory=True)

    competition = semantic.get("competition_context") if isinstance(semantic.get("competition_context"), dict) else {}
    competition_tags = set(competition.get("tags") or [])
    draw_signal = str(draw_semantics.get("signal") or "")
    draw_p = rows["1"].get("p") or 0.0
    p_gap_to_top = max(0.0, primary_p - draw_p)
    margin_guard = (
        0.75 <= abs(handicap) <= 1.25
        and draw_p >= 0.24
        and p_gap_to_top <= 0.20
        and (draw_signal == "explicit_draw" or competition_tags.intersection({"cup", "knockout"}))
    )
    if margin_guard:
        weight = 0.62
        if draw_signal == "explicit_draw":
            weight += 0.18
        if competition_tags.intersection({"cup", "knockout"}):
            weight += 0.08
        add_candidate(
            candidates,
            "1",
            weight,
            "one_goal_margin_guard",
            "一球盘口下，杯赛/平局语义/概率接近触发让球平保护。",
        )
        protect_candidate(candidates, "1", "one_goal_margin_guard")

    for code, candidate in candidates.items():
        candidate["score"] = round(candidate["score"], 4)
        candidate["pending_score"] = round(candidate["pending_score"], 4)
        candidate["status"] = "active" if candidate["score"] > 0 else "pending" if candidate["pending_score"] > 0 else "empty"
        candidate["evidence"] = candidate["evidence"][:6]
        candidate["signals"] = sorted(set(candidate["signals"]))
        candidate["pending_signals"] = sorted(set(candidate["pending_signals"]))
        candidate["mandatory_reasons"] = sorted(set(candidate["mandatory_reasons"]))
        candidate["protected_reasons"] = sorted(set(candidate["protected_reasons"]))

    ranked = sorted(candidates.values(), key=lambda item: (item["score"], item["pending_score"]), reverse=True)
    return {"candidates": ranked, "p_top": p_top, "q_top": q_top}


def select_codes(candidate_pool: dict[str, Any], gates: dict[str, Any], *, budget_mode: str) -> dict[str, Any]:
    candidates = candidate_pool.get("candidates") if isinstance(candidate_pool.get("candidates"), list) else []
    active = [item for item in candidates if item.get("status") == "active"]
    mandatory = [item for item in active if item.get("mandatory")]
    protected = [item for item in active if item.get("protected")]
    max_codes = MAX_WIDE_CODES if budget_mode == "wide" else MAX_TIGHT_CODES
    selected: list[str] = []

    def append_items(items: list[dict[str, Any]]) -> None:
        for item in items:
            code = str(item.get("code") or "")
            if code not in selected and len(selected) < max_codes:
                selected.append(code)

    locked = [
        item
        for item in protected
        if set(item.get("protected_reasons") or []).intersection({"model_q_top_agree", "model_top_strong"})
    ]
    margin_guards = [item for item in protected if "one_goal_margin_guard" in (item.get("protected_reasons") or [])]
    q_value = [item for item in protected if "q_top_value" in (item.get("protected_reasons") or [])]

    append_items(sorted(locked, key=lambda row: row.get("score", 0.0), reverse=True))
    append_items(sorted(margin_guards, key=lambda row: row.get("score", 0.0), reverse=True))
    if locked:
        append_items(sorted(q_value, key=lambda row: row.get("score", 0.0), reverse=True))
        append_items(sorted(mandatory, key=lambda row: row.get("score", 0.0), reverse=True))
    else:
        append_items(sorted(mandatory, key=lambda row: row.get("score", 0.0), reverse=True))
        append_items(sorted(q_value, key=lambda row: row.get("score", 0.0), reverse=True))
    append_items(active)

    if not selected and candidates:
        code = str(candidates[0].get("code") or "")
        if code in OUTCOME_ORDER:
            selected.append(code)

    candidate_codes = [str(item.get("code")) for item in active if (safe_float(item.get("score")) or 0.0) >= 0.95]
    dense_full_candidate = (
        len(active) >= 3
        and active[2].get("score", 0.0) >= 0.90
        and active[2].get("score", 0.0) >= active[0].get("score", 0.0) - 0.55
    )
    unstable_full_candidate = (
        bool(gates.get("csv_extreme_codes") or gates.get("latest_extreme_codes") or gates.get("sp_source_conflict_codes"))
        and len(active) >= 3
        and active[2].get("score", 0.0) >= 0.80
    )
    full_cover_candidate = len(candidate_codes) >= 3 or dense_full_candidate or unstable_full_candidate
    full_reasons = []
    if len(candidate_codes) >= 3 or dense_full_candidate:
        full_reasons.append("candidate_score_dense")
    if gates.get("csv_extreme_codes") or gates.get("latest_extreme_codes") or gates.get("sp_source_conflict_codes"):
        full_reasons.append("extreme_sp_or_source_conflict_full")
    mandatory_overflow = len(mandatory) > max_codes
    if mandatory_overflow:
        full_reasons.append("mandatory_candidates_over_budget")
    protected_overflow = len(protected) > max_codes
    if protected_overflow:
        full_reasons.append("protected_candidates_over_budget")
    full_cover_required = budget_mode == "tight" and (len(candidate_codes) >= 3 or dense_full_candidate)
    if full_cover_required:
        full_reasons.append("tight_dense_requires_full_or_skip")
        selected = [str(item.get("code")) for item in active[:MAX_WIDE_CODES] if str(item.get("code")) in OUTCOME_ORDER]

    action = "buy"
    action_reasons: list[str] = []
    if gates.get("status") == "stop":
        action = "stop"
        action_reasons.extend(gates.get("hard_stop_reasons") or [])
    elif gates.get("status") == "requires_late_refresh" and (
        set(selected).intersection(set(gates.get("sp_unstable_codes") or [])) or gates.get("sp_source_conflict_codes")
    ):
        action = "wait_late_refresh"
        action_reasons.append("selected candidates depend on extreme/stale SP; refresh within final hours")
    elif full_cover_required:
        action = "full_cover_or_skip"
        action_reasons.append("dense candidates require full cover; do not force tight double")

    return {
        "recommended_codes": selected,
        "selection_codes": selected if action == "buy" else [],
        "action": action,
        "action_reasons": action_reasons,
        "full_cover_candidate": bool(full_cover_candidate),
        "full_cover_reasons": sorted(set(full_reasons)),
        "candidate_codes_over_cut": candidate_codes,
        "mandatory_codes": [str(item.get("code")) for item in mandatory],
        "protected_codes": [str(item.get("code")) for item in protected],
        "mandatory_overflow": mandatory_overflow,
        "protected_overflow": protected_overflow,
        "budget_mode": budget_mode,
        "max_codes": max_codes,
    }


def _candidate_by_code(candidate_pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates = candidate_pool.get("candidates") if isinstance(candidate_pool.get("candidates"), list) else []
    return {str(item.get("code")): item for item in candidates if str(item.get("code")) in OUTCOME_ORDER}


def _candidate_has_signal(candidate: dict[str, Any], signal: str) -> bool:
    return signal in set(candidate.get("signals") or []) or signal in set(candidate.get("pending_signals") or [])


def apply_layered_final_merge(
    row: dict[str, Any],
    gates: dict[str, Any],
    semantic: dict[str, Any],
    candidate_pool: dict[str, Any],
    base_selection: dict[str, Any],
    team_strength: dict[str, Any],
    *,
    budget_mode: str,
) -> dict[str, Any]:
    max_codes = MAX_WIDE_CODES if budget_mode == "wide" else MAX_TIGHT_CODES
    base_recommended = [code for code in base_selection.get("recommended_codes", []) if code in OUTCOME_ORDER]
    selected = list(base_recommended)
    mandatory_codes = [code for code in base_selection.get("mandatory_codes", []) if code in OUTCOME_ORDER]
    protected_codes = [code for code in base_selection.get("protected_codes", []) if code in OUTCOME_ORDER]
    candidates = _candidate_by_code(candidate_pool)
    rows = row_numeric(row)
    p_top = gates.get("p_top") or top_code(rows, "p")
    q_top = gates.get("q_top") or top_code(rows, "q")
    sp_conflict_codes = set(gates.get("sp_source_conflict_codes") or [])
    sp_unstable_codes = set(gates.get("sp_unstable_codes") or [])
    merge_flags: list[str] = []
    merge_reasons: list[str] = []

    def append_code(code: str, reason: str) -> bool:
        if code not in OUTCOME_ORDER or code in selected:
            return False
        selected.append(code)
        merge_flags.append(reason)
        return True

    def drop_code(code: str, reason: str) -> bool:
        if code not in selected or code in mandatory_codes:
            return False
        selected.remove(code)
        merge_flags.append(reason)
        return True

    draw_semantics = semantic.get("draw_semantics") if isinstance(semantic.get("draw_semantics"), dict) else {}
    draw_signal = str(draw_semantics.get("signal") or "none")
    team_conf = safe_float(team_strength.get("confidence")) or 0.0
    team_side = str(team_strength.get("side") or "unknown")
    team_primary = [code for code in team_strength.get("primary_codes", []) if code in OUTCOME_ORDER]
    team_support = [code for code in team_strength.get("support_codes", []) if code in OUTCOME_ORDER]
    team_flags = set(team_strength.get("contradiction_flags") or [])

    # Remove the v4.1 emergency draw only when no semantic draw signal supports it and
    # independent team-strength is directional.
    draw_candidate = candidates.get("1", {})
    if (
        "1" in selected
        and "1" not in mandatory_codes
        and "one_goal_margin_guard" not in set(draw_candidate.get("protected_reasons") or [])
        and draw_signal == "none"
        and team_side in {"home", "away"}
        and team_conf >= 0.58
        and _candidate_has_signal(draw_candidate, "late_refresh_neighbor_draw")
    ):
        drop_code("1", "suppress_unbacked_late_refresh_draw")

    # Strong structured side evidence should repair stale model/q branches before
    # the tight two-code cap is applied.
    strong_team_codes = team_primary + [code for code in team_support if code not in team_primary]
    if team_conf >= 0.50 and strong_team_codes:
        for code in strong_team_codes:
            if code in selected:
                continue
            if len(selected) >= max_codes:
                removable = [
                    old_code
                    for old_code in selected
                    if old_code not in mandatory_codes
                    and old_code not in protected_codes
                    and (old_code in sp_conflict_codes or old_code in sp_unstable_codes or old_code == p_top == q_top)
                ]
                if removable:
                    drop_code(removable[0], "replace_stale_branch_with_team_strength")
            if len(selected) < max_codes:
                append_code(code, "add_team_strength_code")

    # If independent layers materially disagree, tight mode should surface the
    # three-code conflict as a budget decision instead of hiding it in ranking.
    full_cover_required = bool(base_selection.get("full_cover_candidate")) and budget_mode == "tight" and len(selected) >= 3
    conflict_requires_full = bool(team_flags.intersection({"competition_context_mismatch", "market_vs_precomputed_form_split"}))
    model_team_split = bool(team_flags.intersection({"team_strength_vs_model_probability", "team_strength_vs_q_top"}))
    conflict_union = []
    for code in base_recommended + selected + team_primary + team_support:
        if code in OUTCOME_ORDER and code not in conflict_union:
            conflict_union.append(code)
    if team_conf >= 0.62 and (conflict_requires_full or (model_team_split and len(conflict_union) > max_codes)):
        for code in conflict_union:
            if code not in selected:
                append_code(code, "layer_conflict_add_team_code")
        if len(selected) > max_codes:
            full_cover_required = True
            merge_flags.append("layer_conflict_requires_full_cover_or_skip")

    # High-q attraction is useful only when q_top differs from p_top. If they are
    # the same stale branch, it should not resurrect that branch by itself.
    if q_top in OUTCOME_ORDER and q_top != p_top and q_top not in selected:
        q_value = rows[q_top].get("q") or 0.0
        p_value = rows[q_top].get("p") or 0.0
        unbacked_draw_q = q_top == "1" and draw_signal == "none" and team_side in {"home", "away"} and team_conf >= 0.58
        if unbacked_draw_q:
            merge_flags.append("skip_unbacked_high_q_draw")
        elif q_value >= 1.80 and p_value >= 0.22:
            if len(selected) >= max_codes:
                removable = [
                    code
                    for code in selected
                    if code not in mandatory_codes
                    and code not in protected_codes
                    and code != p_top
                ]
                if removable:
                    drop_code(removable[-1], "make_room_for_high_q_attraction")
            if len(selected) < max_codes:
                append_code(str(q_top), "high_q_attraction")

    # Bring precomputed form code into tight recommendations when it is the
    # independent tiebreaker behind an explicit draw or a stale SP branch.
    precomputed_code = str(team_strength.get("precomputed_code") or "")
    precomputed_conf = safe_float(team_strength.get("precomputed_confidence")) or 0.0
    if (
        precomputed_code in OUTCOME_ORDER
        and precomputed_code not in selected
        and precomputed_conf >= 0.45
        and ("1" in mandatory_codes or selected and bool(sp_conflict_codes.intersection(selected)))
    ):
        if len(selected) >= max_codes:
            removable = [
                code
                for code in selected
                if code not in mandatory_codes
                and code not in protected_codes
                and code in sp_conflict_codes.union(sp_unstable_codes)
            ]
            if removable:
                drop_code(removable[0], "replace_stale_branch_with_precomputed_form")
        if len(selected) < max_codes:
            append_code(precomputed_code, "add_precomputed_form_tiebreaker")

    if len(selected) > MAX_WIDE_CODES:
        selected = selected[:MAX_WIDE_CODES]

    if full_cover_required and len(set(selected)) >= 3:
        ordered = []
        for code in selected + [str(item.get("code")) for item in candidate_pool.get("candidates", [])]:
            if code in OUTCOME_ORDER and code not in ordered:
                ordered.append(code)
            if len(ordered) >= MAX_WIDE_CODES:
                break
        selected = ordered

    action = str(base_selection.get("action") or "buy")
    action_reasons = list(base_selection.get("action_reasons") or [])
    full_cover_candidate = bool(base_selection.get("full_cover_candidate")) or full_cover_required
    full_cover_reasons = list(base_selection.get("full_cover_reasons") or [])
    if full_cover_required:
        full_cover_reasons.append("layer_conflict_requires_full_cover_or_skip")
    if merge_flags:
        merge_reasons.extend(sorted(set(merge_flags)))

    depends_on_stale_sp = bool(set(selected).intersection(sp_unstable_codes) or sp_conflict_codes)
    if gates.get("status") == "stop":
        action = "stop"
        action_reasons = list(gates.get("hard_stop_reasons") or action_reasons)
    elif gates.get("status") == "requires_late_refresh" and depends_on_stale_sp:
        action = "wait_late_refresh"
        if "selected candidates depend on extreme/stale SP; refresh within final hours" not in action_reasons:
            action_reasons.append("selected candidates depend on extreme/stale SP; refresh within final hours")
    elif full_cover_required and budget_mode == "tight":
        action = "full_cover_or_skip"
        if "layer conflict requires budget-controlled full cover" not in action_reasons:
            action_reasons.append("layer conflict requires budget-controlled full cover")
    elif action == "full_cover_or_skip" and not full_cover_required and len(selected) <= max_codes:
        action = "buy"
        action_reasons = [reason for reason in action_reasons if "dense candidates" not in reason]

    result = {
        "recommended_codes": selected,
        "selection_codes": selected if action == "buy" else [],
        "action": action,
        "action_reasons": action_reasons,
        "full_cover_candidate": bool(full_cover_candidate),
        "full_cover_reasons": sorted(set(full_cover_reasons)),
        "candidate_codes_over_cut": base_selection.get("candidate_codes_over_cut", []),
        "mandatory_codes": mandatory_codes,
        "protected_codes": protected_codes,
        "mandatory_overflow": bool(base_selection.get("mandatory_overflow")),
        "protected_overflow": bool(base_selection.get("protected_overflow")),
        "budget_mode": budget_mode,
        "max_codes": max_codes,
        "merge_flags": sorted(set(merge_flags)),
        "merge_reasons": merge_reasons,
    }
    return result


def compile_decision(
    row: dict[str, Any],
    context: dict[str, Any] | None = None,
    *,
    budget_mode: str = "tight",
    semantic_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or {}
    issue = str(row.get("issue") or (context.get("match") or {}).get("issue") or "")
    match_idx = int(safe_float(row.get("match_idx")) or 0)
    gates = detect_hard_gates(row, context)
    rule_semantic = extract_semantic_llm(row, context)
    if semantic_override is not None:
        semantic = normalize_semantic_contract(semantic_override, fallback=rule_semantic)
        try:
            validate_semantic_contract(semantic)
        except ValueError as exc:
            semantic = normalize_semantic_contract(
                {
                    "source": "invalid_external_semantic",
                    "status": "invalid",
                    "contradiction_flags": ["invalid_external_semantic"],
                    "text_digest": f"invalid semantic override: {exc}",
                },
                fallback=rule_semantic,
            )
    else:
        semantic = normalize_semantic_contract(rule_semantic)
    validate_semantic_contract(semantic)
    translation = translate_handicap(row, context, semantic)
    candidate_pool = build_candidate_pool(row, context, gates, semantic, translation)
    base_selection = select_codes(candidate_pool, gates, budget_mode=budget_mode)
    team_strength = detect_team_strength_sanity(row, context, semantic, translation)
    selection = apply_layered_final_merge(
        row,
        gates,
        semantic,
        candidate_pool,
        base_selection,
        team_strength,
        budget_mode=budget_mode,
    )
    numeric = {
        "rows": row_numeric(row),
        "probability_top": gates.get("p_top"),
        "q_top": gates.get("q_top"),
        "shadow_selection_codes": parse_codes(row.get("shadow_selection_codes")),
        "actual_code": str(row.get("actual_code") or "") if row.get("actual_code") else None,
    }
    contradiction_flags = semantic.get("contradiction_flags") if isinstance(semantic.get("contradiction_flags"), list) else []
    team_flags = team_strength.get("contradiction_flags") if isinstance(team_strength.get("contradiction_flags"), list) else []
    risk_tags = sorted(set((gates.get("risk_tags") or []) + contradiction_flags + team_flags))
    protection = {
        "mandatory_codes": selection["mandatory_codes"],
        "protected_codes": selection["protected_codes"],
        "candidate_codes_over_cut": selection["candidate_codes_over_cut"],
        "full_cover_candidate": selection["full_cover_candidate"],
        "full_cover_reasons": selection["full_cover_reasons"],
        "merge_flags": selection["merge_flags"],
        "merge_reasons": selection["merge_reasons"],
        "budget_mode": budget_mode,
    }
    final_policy = {
        "action": selection["action"],
        "action_reasons": selection["action_reasons"],
        "recommended_codes": selection["recommended_codes"],
        "selection_codes": selection["selection_codes"],
        "risk_tags": risk_tags,
    }
    chain = [
        f"模型主线：prob_top={code_text(gates.get('p_top'))}；q_top={code_text(gates.get('q_top'))}。",
        "硬门槛：" + (" / ".join(risk_tags) if risk_tags else "未触发 SP/数据硬风险。"),
        "语义层：" + json.dumps(
            {
                "raw": semantic.get("raw_strength", {}).get("side"),
                "draw": semantic.get("draw_semantics", {}).get("signal"),
                "flags": contradiction_flags,
            },
            ensure_ascii=False,
        ),
        "盘口翻译：" + "；".join(str(item.get("reason")) for item in translation.get("translations", [])[:4]),
        "强弱校验：" + json.dumps(
            {
                "side": team_strength.get("side"),
                "confidence": team_strength.get("confidence"),
                "codes": team_strength.get("primary_codes"),
                "flags": team_strength.get("contradiction_flags"),
            },
            ensure_ascii=False,
        ),
        f"最终动作：{selection['action']}；建议 { '+'.join(selection['recommended_codes']) or '停' }。",
    ]
    decision = {
        "schema_version": SCHEMA_VERSION,
        "decision_version": DECISION_VERSION,
        "issue": issue,
        "match_idx": match_idx,
        "match": {
            "league": row.get("league") or (context.get("match") or {}).get("league") or "",
            "home": row.get("home") or (context.get("match") or {}).get("home") or "",
            "away": row.get("away") or (context.get("match") or {}).get("away") or "",
            "handicap_line": safe_float(row.get("handicap_line")),
        },
        "sections": {
            "hard_gates": gates,
            "numeric_context": numeric,
            "semantic_llm": semantic,
            "handicap_translation": translation,
            "team_strength_sanity": team_strength,
            "protection_competition": protection,
            "final_policy": final_policy,
        },
        "candidate_pool": candidate_pool["candidates"],
        "action": selection["action"],
        "recommended_codes": selection["recommended_codes"],
        "selection_codes": selection["selection_codes"],
        "risk_tags": risk_tags,
        "chain": chain,
    }
    validate_decision(decision)
    return decision


def decision_to_csv(row: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    semantic = decision["sections"]["semantic_llm"]
    final_policy = decision["sections"]["final_policy"]
    hard_gates = decision["sections"]["hard_gates"]
    protection = decision["sections"]["protection_competition"]
    team_strength = decision["sections"].get("team_strength_sanity", {})
    actual = str(row.get("actual_code") or "")
    recommended = decision.get("recommended_codes", [])
    selection = decision.get("selection_codes", [])
    return {
        "issue": row.get("issue", ""),
        "match_idx": row.get("match_idx", ""),
        "league": row.get("league", ""),
        "home": row.get("home", ""),
        "away": row.get("away", ""),
        "handicap_line": row.get("handicap_line", ""),
        "score": row.get("score", ""),
        "actual_code": actual,
        "shadow_v3_3_3_codes": row.get("shadow_selection_codes", ""),
        "v4_action": decision.get("action", ""),
        "v4_recommended_codes": "+".join(recommended),
        "v4_selection_codes": "+".join(selection),
        "v4_recommended_hit": "" if not actual else int(actual in recommended),
        "v4_selection_hit": "" if not actual else int(actual in selection),
        "v4_risk_tags": ";".join(decision.get("risk_tags", [])),
        "v4_gate_status": hard_gates.get("status", ""),
        "v4_semantic_raw": semantic.get("raw_strength", {}).get("side") or "",
        "v4_semantic_draw": semantic.get("draw_semantics", {}).get("signal") or "",
        "v4_competition_mismatch": int(bool(semantic.get("competition_context", {}).get("mismatch"))),
        "v4_alias_required": int(bool(semantic.get("alias_resolution", {}).get("alias_resolution_required"))),
        "v4_team_strength_side": team_strength.get("side", ""),
        "v4_team_strength_confidence": team_strength.get("confidence", ""),
        "v4_team_strength_codes": "+".join(team_strength.get("primary_codes", []) or []),
        "v4_team_strength_flags": ";".join(team_strength.get("contradiction_flags", []) or []),
        "v4_team_strength_scores_json": json.dumps(team_strength.get("code_scores", {}), ensure_ascii=False),
        "v4_mandatory_codes": "+".join(protection.get("mandatory_codes", [])),
        "v4_protected_codes": "+".join(protection.get("protected_codes", [])),
        "v4_full_cover_candidate": int(bool(protection.get("full_cover_candidate"))),
        "v4_full_cover_reasons": ";".join(protection.get("full_cover_reasons", [])),
        "v4_merge_flags": ";".join(protection.get("merge_flags", [])),
        "v4_action_reasons": ";".join(final_policy.get("action_reasons", [])),
        "v4_candidate_pool_json": json.dumps(decision.get("candidate_pool", []), ensure_ascii=False),
    }


def write_jsonl(decisions: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for decision in decisions:
            f.write(json.dumps(decision, ensure_ascii=False, sort_keys=True) + "\n")


def load_semantic_jsonl(path: Path | None) -> dict[int, dict[str, Any]]:
    if path is None:
        return {}
    items: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            item = safe_json(line, {})
            if not isinstance(item, dict):
                raise ValueError(f"{path}:{line_no} semantic row must be an object")
            match_idx = int(safe_float(item.get("match_idx")) or 0)
            semantic = item.get("semantic_llm") if isinstance(item.get("semantic_llm"), dict) else item
            if match_idx <= 0:
                raise ValueError(f"{path}:{line_no} missing match_idx")
            items[match_idx] = semantic
    return items


def write_csv(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0]) if records else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def md_table(records: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    lines = ["| " + " | ".join(title for title, _key in columns) + " |"]
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


def summarize_csv_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts = Counter(record["v4_action"] for record in records)
    recommended_type_counts = Counter(
        "no-buy"
        if not parse_codes(record["v4_recommended_codes"])
        else "single"
        if len(parse_codes(record["v4_recommended_codes"])) == 1
        else "double"
        if len(parse_codes(record["v4_recommended_codes"])) == 2
        else "full"
        for record in records
    )
    return {
        "n_matches": len(records),
        "action_counts": dict(action_counts),
        "recommended_type_counts": dict(recommended_type_counts),
        "full_cover_candidates": sum(int(record["v4_full_cover_candidate"]) for record in records),
        "late_refresh": sum(1 for record in records if record["v4_action"] == "wait_late_refresh"),
    }


def render_report(
    records: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    summary: dict[str, Any],
    csv_path: Path,
    jsonl_path: Path,
    *,
    issue: str,
) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    focus_indices = {7, 8, 9, 11, 17, 20, 21, 23, 25, 28, 35, 47, 54}
    focus = [record for record in records if int(record.get("match_idx") or 0) in focus_indices]
    full_records = [record for record in records if int(record.get("v4_full_cover_candidate") or 0)]
    action_records = [
        {"key": key, "value": value}
        for key, value in {
            "matches": summary["n_matches"],
            "actions": summary["action_counts"],
            "recommended_type": summary["recommended_type_counts"],
            "full_cover_candidates": summary["full_cover_candidates"],
            "late_refresh": summary["late_refresh"],
        }.items()
    ]
    schema_excerpt = {
        "semantic_llm": {
            "alias_resolution": "home_aliases/away_aliases/unresolved_names",
            "raw_strength": "side/confidence/evidence",
            "draw_semantics": "explicit_draw|balanced|none",
            "competition_context": "league/headline/mismatch",
            "contradiction_flags": "competition/alias/source flags",
        },
        "handicap_translation": "raw strength and draw semantics mapped to Beidan handicap result codes",
        "team_strength_sanity": "odds/rank/form/h2h/precomputed code independent sanity layer",
        "protection_competition": "mandatory codes, full-cover candidate, merge flags, budget policy",
        "hard_gates": "disabled, extreme SP, source conflict, late refresh",
    }
    return f"""# 结构化决策链 v4.2.0000 旁路回放 {issue}

生成时间：{generated}

## 边界

- 本脚本只读取已有 shadow CSV 和 SQLite 上下文，输出 v4.2.0000 旁路 artifact；不写 `llm_decision_snapshots`，不修改 active/shadow release 配置。
- v4.2.0000 的目标不是直接上线，而是把 LLM 必须填写的语义槽、北单让球翻译、独立强弱校验、保护候选竞争、极值 SP 临场门槛拆开验证。
- `v4_action=wait_late_refresh` 表示当前建议不能直接下注，需要临场数小时内刷新 SP 后再落单；`v4_recommended_codes` 保留当前结构化建议。

## Schema 摘要

```json
{json.dumps(schema_excerpt, ensure_ascii=False, indent=2)}
```

## 汇总

{md_table(action_records, [("指标", "key"), ("值", "value")])}

## 重点复盘场次

{md_table(focus, [
        ("#", "match_idx"),
        ("比赛", "league"),
        ("主队", "home"),
        ("客队", "away"),
        ("让球", "handicap_line"),
        ("v3.3.3", "shadow_v3_3_3_codes"),
        ("v4动作", "v4_action"),
        ("v4建议", "v4_recommended_codes"),
        ("硬门槛", "v4_gate_status"),
        ("raw", "v4_semantic_raw"),
        ("draw", "v4_semantic_draw"),
        ("必选", "v4_mandatory_codes"),
        ("full候选", "v4_full_cover_candidate"),
        ("risk", "v4_risk_tags"),
    ])}

## Full-cover 候选

{md_table(full_records, [
        ("#", "match_idx"),
        ("比赛", "league"),
        ("主队", "home"),
        ("客队", "away"),
        ("v3.3.3", "shadow_v3_3_3_codes"),
        ("v4动作", "v4_action"),
        ("v4建议", "v4_recommended_codes"),
        ("full原因", "v4_full_cover_reasons"),
        ("risk", "v4_risk_tags"),
    ]) if full_records else "无。"}

## 初步结论

1. v4.2.0000 在 v4.1 的语义/盘口拆分之外新增独立强弱校验层，用结构化事实源修正摘要错配和候选压平问题。
2. 极值 SP 或 CSV/当前 SP 严重冲突时，v4.2.0000 仍输出 `wait_late_refresh`，避免在离比赛过远时基于异常 SP 落单。
3. full-cover 在 v4.2.0000 中是预算诊断；tight 模式默认双选，只有层间冲突无法压缩时才升级为全包或跳过。

CSV：`{path_for_report(csv_path)}`

JSONL：`{path_for_report(jsonl_path)}`
"""


def run(
    *,
    issue: str,
    structured_csv: Path,
    db_path: Path | None,
    output_dir: Path,
    report_path: Path,
    budget_mode: str,
    semantic_jsonl: Path | None = None,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    rows = load_structured_rows(structured_csv)
    semantic_overrides = load_semantic_jsonl(semantic_jsonl)
    conn: sqlite3.Connection | None = None
    if db_path is not None and db_path.exists():
        conn = sqlite3.connect(db_path)
    decisions: list[dict[str, Any]] = []
    try:
        for row in rows:
            if str(row.get("issue") or issue) != issue:
                continue
            match_idx = int(safe_float(row.get("match_idx")) or 0)
            context = fetch_match_context(conn, issue, match_idx) if conn else {}
            decisions.append(
                compile_decision(
                    row,
                    context,
                    budget_mode=budget_mode,
                    semantic_override=semantic_overrides.get(match_idx),
                )
            )
    finally:
        if conn is not None:
            conn.close()
    if not decisions:
        raise SystemExit(f"No rows compiled for issue {issue}")

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"structured_v4_2_{issue}.csv"
    jsonl_path = output_dir / f"structured_v4_2_{issue}.jsonl"
    source_rows_by_idx = {int(safe_float(row.get("match_idx")) or 0): row for row in rows}
    records = [decision_to_csv(source_rows_by_idx[decision["match_idx"]], decision) for decision in decisions]
    write_csv(records, csv_path)
    write_jsonl(decisions, jsonl_path)
    summary = summarize_csv_records(records)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(records, decisions, summary, csv_path, jsonl_path, issue=issue),
        encoding="utf-8",
    )
    return csv_path, jsonl_path, report_path, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay structured v4.2.0000 decision-chain overlay from shadow CSV.")
    parser.add_argument("--issue", required=True)
    parser.add_argument("--structured-csv", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--budget-mode", choices=("tight", "wide"), default="tight")
    parser.add_argument("--semantic-jsonl", type=Path, default=None, help="Optional external semantic_llm JSONL keyed by match_idx.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    date_slug = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_dir = args.output_dir or DEFAULT_OUTPUT_ROOT / f"{args.issue}_{date_slug}_v4_2"
    report_path = args.report or DEFAULT_REPORT_DIR / f"structured_decision_chain_v4_2_{args.issue}_{report_date}.md"
    csv_path, jsonl_path, report_path, summary = run(
        issue=args.issue,
        structured_csv=args.structured_csv,
        db_path=args.db,
        output_dir=output_dir,
        report_path=report_path,
        budget_mode=args.budget_mode,
        semantic_jsonl=args.semantic_jsonl,
    )
    print(json.dumps({"csv": str(csv_path), "jsonl": str(jsonl_path), "report": str(report_path), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
