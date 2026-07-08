#!/usr/bin/env python3
"""Create post-match review rows for settled live matches.

This script records an audit snapshot of a specific decision-chain variant
against final settled results. It is intentionally append-only per review
version: dynamic match details may keep changing, but a post-match review should
not silently rewrite the prior betting decision basis.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sqlite_runtime import connect_sqlite  # noqa: E402

DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_DECISION_VARIANT_ID = "active_v3.3.3"
REVIEW_VERSION = "v3_decision_variant_active_v3_3_3_tags"
REVIEW_TAG_VERSION = "postmatch_tags_v2"
OUTCOME_LABEL = {"3": "胜", "1": "平", "0": "负"}
REQUIRED_REVIEW_COLUMNS = {
    "decision_variant_id": "TEXT",
    "decision_snapshot_id": "TEXT",
    "decision_snapshot_generated_at": "TEXT",
    "decision_snapshot_status": "TEXT",
    "decision_fingerprint": "TEXT",
    "tag_version": "TEXT",
    "outcome_label": "TEXT",
    "action_suggestion": "TEXT",
    "issue_day_key": "TEXT",
}
REQUIRED_SUMMARY_COLUMNS = {
    "decision_variant_id": "TEXT",
}


def ensure_import_path() -> None:
    root_text = str(ROOT)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def now_hk() -> str:
    return datetime.now(ZoneInfo("Asia/Hong_Kong")).strftime("%Y-%m-%d %H:%M:%S")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS postmatch_reviews (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            review_version TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            decision_generated_ts TEXT,
            decision_source TEXT,
            league TEXT,
            home TEXT,
            away TEXT,
            kickoff_ts TEXT,
            score TEXT,
            halftime_score TEXT,
            result_code TEXT,
            result_label TEXT,
            winning_sp REAL,
            llm_selection TEXT,
            llm_selection_codes_json TEXT,
            llm_judgment TEXT,
            primary_hit INTEGER,
            protect_hit INTEGER,
            coverage_hit INTEGER,
            stopped INTEGER,
            stake REAL,
            gross_return REAL,
            profit REAL,
            roi REAL,
            failure_tags_json TEXT,
            review_summary TEXT,
            review_payload_json TEXT,
            PRIMARY KEY (issue, match_idx, review_version)
        )
        """
    )
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(postmatch_reviews)")}
    for col, col_type in REQUIRED_REVIEW_COLUMNS.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE postmatch_reviews ADD COLUMN {col} {col_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_postmatch_reviews_issue ON postmatch_reviews(issue)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_postmatch_reviews_reviewed_at ON postmatch_reviews(reviewed_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS postmatch_review_issue_summary (
            issue TEXT NOT NULL,
            review_version TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            n_reviews INTEGER NOT NULL,
            stake REAL NOT NULL,
            gross_return REAL NOT NULL,
            profit REAL NOT NULL,
            roi REAL NOT NULL,
            primary_hits INTEGER NOT NULL,
            protect_hits INTEGER NOT NULL,
            coverage_hits INTEGER NOT NULL,
            stopped_correct INTEGER NOT NULL,
            stopped_wrong INTEGER NOT NULL,
            tag_counts_json TEXT NOT NULL,
            PRIMARY KEY (issue, review_version)
        )
        """
    )
    existing_summary_cols = {row[1] for row in conn.execute("PRAGMA table_info(postmatch_review_issue_summary)")}
    for col, col_type in REQUIRED_SUMMARY_COLUMNS.items():
        if col not in existing_summary_cols:
            conn.execute(f"ALTER TABLE postmatch_review_issue_summary ADD COLUMN {col} {col_type}")


def slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value.strip().lower()).strip("_")


def review_version_for_decision_variant(decision_variant_id: str) -> str:
    variant = decision_variant_id.strip()
    return f"v3_decision_variant_{slugify(variant)}_tags" if variant else REVIEW_VERSION


def reviewed_keys(conn: sqlite3.Connection, issue: str, review_version: str) -> set[tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT issue, match_idx
        FROM postmatch_reviews
        WHERE issue=? AND review_version=?
        """,
        (issue, review_version),
    ).fetchall()
    return {(str(row[0]), int(row[1])) for row in rows}


def is_settled(match: dict[str, object]) -> bool:
    return bool(match.get("result_code") and match.get("score") and match.get("winning_sp") is not None)


def has_active_decision_snapshot(match: dict[str, object]) -> bool:
    return bool(match.get("decision_snapshot_id") and match.get("decision_snapshot_status") == "active")


def as_code_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item) in OUTCOME_LABEL]


def as_dict(raw: object) -> dict[str, object]:
    return raw if isinstance(raw, dict) else {}


def selected_decision(match: dict[str, object], decision_variant_id: str) -> dict[str, object]:
    if not decision_variant_id:
        selected = as_code_list(match.get("llm_selection_codes") or match.get("selection_codes"))
        primary = str(match.get("llm_selection") or (selected[0] if selected else ""))
        return {
            "variant_id": "",
            "selection_codes": selected,
            "primary_pick": primary,
            "recommendation": str(match.get("llm_judgment") or ""),
            "selection_type": str(match.get("llm_selection_type") or ""),
            "stop_flag": False,
            "source": str(match.get("llm_source") or match.get("selection_source") or ""),
            "version": str(match.get("model_version") or ""),
            "decision_chain": match.get("llm_decision_chain") or [],
        }
    variant = as_dict(match.get("selected_decision_variant"))
    selected = as_code_list(variant.get("selection_codes"))
    primary = str(variant.get("primary_pick") or (selected[0] if selected else ""))
    return {
        "variant_id": str(variant.get("variant_id") or decision_variant_id),
        "selection_codes": selected,
        "primary_pick": primary,
        "recommendation": str(variant.get("recommendation") or ""),
        "selection_type": str(variant.get("selection_type") or ""),
        "stop_flag": bool(variant.get("stop_flag")),
        "source": str(variant.get("source") or ""),
        "version": str(variant.get("version") or variant.get("version_id") or ""),
        "decision_chain": variant.get("decision_chain") or [],
    }


def outcome_probability(match: dict[str, object], code: str) -> float:
    value = match.get(f"model_p_{code}")
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def outcome_q(match: dict[str, object], code: str) -> float:
    try:
        p = outcome_probability(match, code)
        sp = float(match.get(f"sp_{code}") or 0.0)
        return p * sp
    except (TypeError, ValueError):
        return 0.0


def failure_tags(
    match: dict[str, object],
    actual: str,
    primary: str,
    selected: list[str],
    *,
    primary_hit: bool,
    protect_hit: bool,
    coverage_hit: bool,
    stopped: bool,
    profit: float,
) -> list[str]:
    tags: list[str] = []
    if stopped:
        tags.append("stop_wrong" if actual else "stop_unknown")
        return tags
    if primary_hit:
        tags.append("primary_hit")
    if protect_hit:
        tags.append("protection_saved")
    if actual == "1":
        tags.append("missed_draw")
    if selected and not coverage_hit:
        tags.append("uncovered_result")
    if not coverage_hit and outcome_probability(match, actual) >= 0.25:
        tags.append("uncovered_high_prob_alt")
    if not coverage_hit and outcome_q(match, primary) >= 1.0:
        tags.append("q_trap")
    if primary and not primary_hit:
        probs = {code: outcome_probability(match, code) for code in OUTCOME_LABEL}
        top_prob_code = max(probs, key=probs.get)
        if primary == top_prob_code:
            tags.append("wrong_favorite")
    if match.get("line_gap") not in (None, "", "null"):
        try:
            if abs(float(match.get("line_gap") or 0.0)) >= 0.5 and (not coverage_hit or not primary_hit):
                tags.append("line_gap_warning_ignored")
        except (TypeError, ValueError):
            pass
    risks = match.get("llm_risks")
    if risks:
        tags.append("had_pre_match_risks")
        if not coverage_hit:
            tags.append("intel_misread")
    if coverage_hit and profit < 0:
        tags.append("low_sp_double_negative_ev")
    return tags


def review_outcome_label(stopped: bool, primary_hit: bool, protect_hit: bool, coverage_hit: bool) -> str:
    if stopped:
        return "停错" if not coverage_hit else "停正确"
    if primary_hit:
        return "押中"
    if protect_hit:
        return "保中"
    if coverage_hit:
        return "覆盖中"
    return "未中"


def action_suggestion(tags: list[str], outcome_label: str) -> str:
    if "uncovered_high_prob_alt" in tags and "missed_draw" in tags:
        return "平局高概率替代结果未覆盖；复查半球/让球偏移/近期平局率的保护阈值。"
    if "protection_saved" in tags:
        return "保护腿有效；保留该类押保拆分逻辑并评估串关中的保护深度。"
    if "low_sp_double_negative_ev" in tags:
        return "双选命中但单场收益为负；仅作为高N防死腿成本纳入。"
    if outcome_label == "未中":
        return "未覆盖实际结果；检查 q/胜率/情报是否一致，以及是否应降低单选暴露。"
    return "复盘无新增动作。"


def build_review(match: dict[str, object], reviewed_at: str, *, review_version: str, decision_variant_id: str) -> dict[str, object]:
    issue = str(match["issue"])
    match_idx = int(match["match_idx"])
    actual = str(match["result_code"])
    actual_label = str(match.get("result_label") or OUTCOME_LABEL.get(actual, actual))
    winning_sp = float(match.get("winning_sp") or 0.0)
    decision = selected_decision(match, decision_variant_id)
    selected = as_code_list(decision.get("selection_codes"))
    primary = str(decision.get("primary_pick") or (selected[0] if selected else ""))
    stopped = 1 if not selected or bool(decision.get("stop_flag")) or str(decision.get("selection_type") or "") in {"stop", "no-buy"} else 0
    protect_codes = [code for code in selected if code != primary]
    primary_hit = 1 if primary == actual else 0
    protect_hit = 1 if actual in protect_codes else 0
    coverage_hit = 1 if actual in selected else 0
    stake = 2.0 * len(selected)
    gross_return = 2.0 * winning_sp if coverage_hit else 0.0
    profit = gross_return - stake
    roi = profit / stake if stake else 0.0
    tags = failure_tags(
        match,
        actual,
        primary,
        selected,
        primary_hit=bool(primary_hit),
        protect_hit=bool(protect_hit),
        coverage_hit=bool(coverage_hit),
        stopped=bool(stopped),
        profit=profit,
    )
    outcome = review_outcome_label(bool(stopped), bool(primary_hit), bool(protect_hit), bool(coverage_hit))
    suggestion = action_suggestion(tags, outcome)
    selected_labels = "/".join(OUTCOME_LABEL.get(code, code) for code in selected) or "停"
    primary_label = OUTCOME_LABEL.get(primary, primary) if primary else "停"
    if stopped:
        summary = f"停牌复盘：实际{actual_label}，结算SP {winning_sp:.2f}。"
    elif primary_hit:
        summary = f"主押命中：押{primary_label}，实际{actual_label}，结算SP {winning_sp:.2f}。"
    elif protect_hit:
        summary = f"保护命中：押{primary_label}未中，{selected_labels}覆盖实际{actual_label}，结算SP {winning_sp:.2f}。"
    elif coverage_hit:
        summary = f"覆盖命中：{selected_labels}覆盖实际{actual_label}，结算SP {winning_sp:.2f}。"
    else:
        summary = f"未命中：{selected_labels}未覆盖实际{actual_label}，结算SP {winning_sp:.2f}。"

    payload = {
        "issue": issue,
        "match_idx": match_idx,
        "match_id": match.get("match_id"),
        "review_version": review_version,
        "decision_variant_id": decision_variant_id,
        "reviewed_at": reviewed_at,
        "decision_chain": decision.get("decision_chain") or match.get("llm_decision_chain") or [],
        "decision_snapshot_id": match.get("decision_snapshot_id"),
        "decision_snapshot_generated_at": match.get("decision_snapshot_generated_at"),
        "decision_snapshot_status": match.get("decision_snapshot_status"),
        "llm_support": match.get("llm_support") or [],
        "llm_risks": match.get("llm_risks") or [],
        "model_selection_codes": match.get("model_selection_codes") or [],
        "model_probabilities": {
            "3": match.get("model_p_3"),
            "1": match.get("model_p_1"),
            "0": match.get("model_p_0"),
        },
        "q": {
            "max": match.get("q_max"),
            "score": match.get("q_score"),
            "calculated_ts": match.get("q_calculated_ts"),
        },
        "sp": {
            "3": match.get("sp_3"),
            "1": match.get("sp_1"),
            "0": match.get("sp_0"),
            "snapshot_ts": match.get("sp_snapshot_ts"),
        },
        "result": {
            "code": actual,
            "label": actual_label,
            "score": match.get("score"),
            "halftime_score": match.get("halftime_score"),
            "winning_sp": winning_sp,
        },
        "money": {
            "stake": stake,
            "gross_return": gross_return,
            "profit": profit,
            "roi": roi,
        },
        "tags": tags,
        "outcome_label": outcome,
        "action_suggestion": suggestion,
        "summary": summary,
    }
    return {
        "issue": issue,
        "match_idx": match_idx,
        "match_id": str(match.get("match_id") or f"{issue}_{match_idx:03d}"),
        "review_version": review_version,
        "decision_variant_id": decision_variant_id,
        "reviewed_at": reviewed_at,
        "decision_generated_ts": str(match.get("decision_snapshot_generated_at") or match.get("generated_ts") or ""),
        "decision_source": str(decision.get("source") or decision.get("version") or match.get("llm_source") or match.get("selection_source") or ""),
        "decision_snapshot_id": str(match.get("decision_snapshot_id") or ""),
        "decision_snapshot_generated_at": str(match.get("decision_snapshot_generated_at") or ""),
        "decision_snapshot_status": str(match.get("decision_snapshot_status") or ""),
        "decision_fingerprint": str(match.get("decision_snapshot_input_hash") or ""),
        "tag_version": REVIEW_TAG_VERSION,
        "outcome_label": outcome,
        "action_suggestion": suggestion,
        "issue_day_key": f"{issue}:{str(match.get('kickoff_date') or match.get('kickoff_ts') or '')[:10]}",
        "league": str(match.get("league") or ""),
        "home": str(match.get("home") or ""),
        "away": str(match.get("away") or ""),
        "kickoff_ts": str(match.get("kickoff_ts") or ""),
        "score": str(match.get("score") or ""),
        "halftime_score": str(match.get("halftime_score") or ""),
        "result_code": actual,
        "result_label": actual_label,
        "winning_sp": winning_sp,
        "llm_selection": primary,
        "llm_selection_codes_json": json.dumps(selected, ensure_ascii=False),
        "llm_judgment": str(decision.get("recommendation") or match.get("llm_judgment") or ""),
        "primary_hit": primary_hit,
        "protect_hit": protect_hit,
        "coverage_hit": coverage_hit,
        "stopped": stopped,
        "stake": stake,
        "gross_return": gross_return,
        "profit": profit,
        "roi": roi,
        "failure_tags_json": json.dumps(tags, ensure_ascii=False),
        "review_summary": summary,
        "review_payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
    }


def insert_reviews(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0
    columns = list(rows[0])
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"""
        INSERT OR IGNORE INTO postmatch_reviews ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        [[row[col] for col in columns] for row in rows],
    )
    return int(conn.total_changes)


def write_issue_summary(conn: sqlite3.Connection, issue: str, rows: list[dict[str, object]], reviewed_at: str, *, review_version: str, decision_variant_id: str) -> dict[str, object]:
    tag_counts: dict[str, int] = {}
    for row in rows:
        for tag in json.loads(str(row["failure_tags_json"] or "[]")):
            tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1
    stake = sum(float(row["stake"]) for row in rows)
    gross = sum(float(row["gross_return"]) for row in rows)
    profit = sum(float(row["profit"]) for row in rows)
    summary = {
        "issue": issue,
        "review_version": review_version,
        "decision_variant_id": decision_variant_id,
        "reviewed_at": reviewed_at,
        "n_reviews": len(rows),
        "stake": stake,
        "gross_return": gross,
        "profit": profit,
        "roi": profit / stake if stake else 0.0,
        "primary_hits": sum(int(row["primary_hit"]) for row in rows),
        "protect_hits": sum(int(row["protect_hit"]) for row in rows),
        "coverage_hits": sum(int(row["coverage_hit"]) for row in rows),
        "stopped_correct": sum(1 for row in rows if row.get("outcome_label") == "停正确"),
        "stopped_wrong": sum(1 for row in rows if row.get("outcome_label") == "停错"),
        "tag_counts_json": json.dumps(tag_counts, ensure_ascii=False, sort_keys=True),
    }
    cols = list(summary)
    placeholders = ", ".join("?" for _ in cols)
    update_cols = ", ".join(f"{col}=excluded.{col}" for col in cols if col not in {"issue", "review_version"})
    conn.execute(
        f"""
        INSERT INTO postmatch_review_issue_summary ({", ".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(issue, review_version) DO UPDATE SET {update_cols}
        """,
        [summary[col] for col in cols],
    )
    return summary


def load_review_rows(conn: sqlite3.Connection, issue: str, review_version: str) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM postmatch_reviews
        WHERE issue=? AND review_version=?
        ORDER BY match_idx
        """,
        (issue, review_version),
    ).fetchall()
    return [dict(row) for row in rows]


def load_dashboard(issue: str, db_path: Path, decision_variant_id: str) -> dict[str, object]:
    ensure_import_path()
    from src.decision_api.app import create_app

    app = create_app(sqlite_db=db_path)
    with app.test_client() as client:
        suffix = f"?decision_variant={decision_variant_id}" if decision_variant_id else ""
        response = client.get(f"/api/issues/{issue}/dashboard{suffix}")
        if response.status_code != 200:
            raise RuntimeError(f"dashboard API failed for {issue}: {response.status_code} {response.get_data(as_text=True)}")
        return response.get_json()


def validate_decision_variant_ready(dashboard: dict[str, object], decision_variant_id: str) -> None:
    if not decision_variant_id:
        return
    context = as_dict(dashboard.get("strategy_version_context"))
    status = str(context.get("selection_status") or "")
    if status != "ok":
        error = str(context.get("selection_error") or "decision variant unavailable")
        raise RuntimeError(f"decision variant not reviewable: {decision_variant_id}; status={status}; {error}")
    bad_indices = [
        int(match.get("match_idx") or 0)
        for match in dashboard.get("matches", [])
        if isinstance(match, dict)
        and is_settled(match)
        and str(match.get("selected_decision_variant_status") or "") != "ok"
    ]
    if bad_indices:
        shown = ",".join(str(idx) for idx in bad_indices[:12])
        more = f",...(+{len(bad_indices) - 12})" if len(bad_indices) > 12 else ""
        raise RuntimeError(
            f"decision variant has unavailable settled rows: {decision_variant_id}; match_idx={shown}{more}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", default="current")
    parser.add_argument("--decision-variant", default=DEFAULT_DECISION_VARIANT_ID, help="Decision-chain variant to review, e.g. active_v3.3.3")
    parser.add_argument("--review-version", default="", help="Override persisted postmatch review_version")
    parser.add_argument("--replace", action="store_true", help="Delete existing rows for this issue/review-version before writing")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    decision_variant_id = str(args.decision_variant or "").strip()
    review_version = str(args.review_version or "").strip() or review_version_for_decision_variant(decision_variant_id)

    with connect_sqlite(args.db) as conn:
        ensure_schema(conn)

    dashboard = load_dashboard(args.issue, args.db, decision_variant_id)
    validate_decision_variant_ready(dashboard, decision_variant_id)
    issue = str(dashboard.get("issue") or args.issue)
    reviewed_at = now_hk()

    with connect_sqlite(args.db) as conn:
        ensure_schema(conn)
        if args.replace and not args.dry_run:
            conn.execute("DELETE FROM postmatch_reviews WHERE issue=? AND review_version=?", (issue, review_version))
            conn.execute("DELETE FROM postmatch_review_issue_summary WHERE issue=? AND review_version=?", (issue, review_version))
        existing = reviewed_keys(conn, issue, review_version)
        rows = [
            build_review(match, reviewed_at, review_version=review_version, decision_variant_id=decision_variant_id)
            for match in dashboard.get("matches", [])
            if is_settled(match)
            and has_active_decision_snapshot(match)
            and (str(match.get("issue")), int(match.get("match_idx") or 0)) not in existing
        ]
        if args.dry_run:
            print(json.dumps({"issue": issue, "decision_variant_id": decision_variant_id, "review_version": review_version, "would_insert": len(rows), "rows": rows}, ensure_ascii=False, indent=2))
            return
        before_insert = conn.total_changes
        insert_reviews(conn, rows)
        inserted = conn.total_changes - before_insert
        issue_summary = write_issue_summary(conn, issue, load_review_rows(conn, issue, review_version), reviewed_at, review_version=review_version, decision_variant_id=decision_variant_id)
        conn.commit()

    summary = {
        "issue": issue,
        "decision_variant_id": decision_variant_id,
        "review_version": review_version,
        "inserted": inserted,
        "reviewed_at": reviewed_at,
        "stake": issue_summary["stake"],
        "gross_return": issue_summary["gross_return"],
        "profit": issue_summary["profit"],
        "coverage_hits": issue_summary["coverage_hits"],
        "primary_hits": issue_summary["primary_hits"],
        "protect_hits": issue_summary["protect_hits"],
        "issue_summary": issue_summary,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
