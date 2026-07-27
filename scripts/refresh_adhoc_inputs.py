#!/usr/bin/env python3
"""One-shot, same-cycle refresh for adhoc eligibility inputs.

The command fetches the official issue page, Nowscore issue page and playid-34
SP XML before opening a write transaction.  If any source or binding check
fails, no partial eligibility batch is published.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import scrape_500_bjdc as source_500  # noqa: E402
from scripts import scrape_nowscore_bjdc as source_nowscore  # noqa: E402
from src.adhoc_input_freshness import (  # noqa: E402
    build_same_cycle_batch,
    canonical_json,
    explicit_utc,
    sha256_bytes,
)
from src.sqlite_runtime import connect_sqlite  # noqa: E402


DEFAULT_DB = source_500.DEFAULT_DB
DEFAULT_RECEIPT_ROOT = ROOT / "results" / "adhoc_input_freshness"
PARLAY_MODE_MARKERS = ("自由过关",)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json(payload) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(temporary).replace(path)
    finally:
        candidate = Path(temporary)
        if candidate.exists():
            candidate.unlink()


def _persist_bound_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO live_market_sp_snapshots(
            issue, playid, market_key, fetched_at, source_updatetime, row_idx,
            home, away, league, outcome_code, outcome_label, sp,
            source_attribute, raw_node, match_id, batch_id, source_url,
            fetched_at_utc, source_updated_at_hkt, sale_status, sale_cutoff_hkt,
            parlay_allowed, parlay_modes_json, stake_limit_json,
            capture_classification, eligibility_evidence_json,
            eligibility_reasons_json
        ) VALUES(
            :issue, :playid, :market_key, :fetched_at, :source_updatetime, :row_idx,
            :home, :away, :league, :outcome_code, :outcome_label, :sp,
            :source_attribute, :raw_node, :match_id, :batch_id, :source_url,
            :fetched_at_utc, :source_updated_at_hkt, :sale_status, :sale_cutoff_hkt,
            :parlay_allowed, :parlay_modes_json, :stake_limit_json,
            :capture_classification, :eligibility_evidence_json,
            :eligibility_reasons_json
        )
        """,
        rows,
    )


def refresh_adhoc_inputs(
    *,
    issue: str,
    db_path: Path,
    receipt_root: Path = DEFAULT_RECEIPT_ROOT,
    timeout: float = 25.0,
    user_agent: str = source_500.DEFAULT_UA,
    clock: Callable[[], str] = utc_now,
    fetch_500: Callable[..., source_500.FetchResult] = source_500.fetch_url,
    fetch_nowscore: Callable[..., tuple[int, bytes, float]] = source_nowscore.fetch_url,
) -> dict[str, Any]:
    """Fetch and atomically publish one content-addressed eligibility batch."""

    issue_url = f"{source_500.TRADE_URL}?expect={issue}"
    issue_result = fetch_500(
        issue_url,
        timeout=timeout,
        user_agent=user_agent,
        referer=source_500.TRADE_URL,
    )
    issue_clock = explicit_utc(clock())

    nowscore_url = source_nowscore.NOWSCORE_URL.format(issue=issue)
    nowscore_status, nowscore_payload, _nowscore_elapsed = fetch_nowscore(
        nowscore_url,
        timeout,
        user_agent,
    )
    if int(nowscore_status) != 200:
        raise RuntimeError(f"Nowscore refresh failed with HTTP {nowscore_status}")
    nowscore_clock = explicit_utc(clock())

    live_url = source_500.LIVE_SP_URL.format(issue=issue, playid=34)
    live_result = fetch_500(
        live_url,
        timeout=timeout,
        user_agent=user_agent,
        referer=f"{source_500.TRADE_URL}?expect={issue}",
    )
    live_clock = explicit_utc(clock())

    issue_text = source_500.decode_html(issue_result.body)
    nowscore_text = nowscore_payload.decode("utf-8", errors="replace")
    issue_rows = source_500.parse_issue_rows(
        issue,
        issue_text,
        fetched_at=issue_clock,
    )
    nowscore_rows = source_nowscore.parse_rows(
        issue,
        nowscore_text,
        nowscore_clock,
    )
    source_updatetime, market_rows = source_500.parse_live_market_sp(
        issue,
        34,
        live_result.body,
        live_clock,
    )
    if not source_updatetime:
        raise RuntimeError("live SP source clock is missing")
    for row in market_rows:
        row["source_url"] = live_url

    parlay_modes = [marker for marker in PARLAY_MODE_MARKERS if marker in issue_text]
    batch = build_same_cycle_batch(
        issue=issue,
        issue_rows=issue_rows,
        nowscore_rows=nowscore_rows,
        market_rows=market_rows,
        source_clocks_utc={
            "issue_html": issue_clock,
            "nowscore_html": nowscore_clock,
            "live_sp_xml": live_clock,
        },
        source_sha256={
            "issue_html": sha256_bytes(issue_result.body),
            "nowscore_html": sha256_bytes(nowscore_payload),
            "live_sp_xml": sha256_bytes(live_result.body),
        },
        parlay_modes=parlay_modes,
    )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_sqlite(db_path, row_factory=True) as conn:
        source_500.create_schema(conn)
        source_nowscore.create_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            source_500.upsert_matches(conn, issue_rows)
            source_nowscore.upsert_match_rows(conn, nowscore_rows)
            _persist_bound_rows(conn, list(batch["rows"]))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    receipt = dict(batch["receipt"])
    receipt_path = receipt_root / issue / f"{batch['batch_id']}.json"
    _atomic_json(receipt_path, receipt)
    return {
        "status": receipt["status"],
        "issue": issue,
        "batch_id": batch["batch_id"],
        "eligible_match_count": receipt["eligible_match_count"],
        "match_count": receipt["match_count"],
        "rejection_counts": receipt["rejection_counts"],
        "receipt": str(receipt_path.resolve()),
        "receipt_sha256": sha256_bytes(receipt_path.read_bytes()),
        "database": str(db_path.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--user-agent", default=source_500.DEFAULT_UA)
    args = parser.parse_args()
    result = refresh_adhoc_inputs(
        issue=str(args.issue),
        db_path=args.db,
        receipt_root=args.receipt_root,
        timeout=args.timeout,
        user_agent=args.user_agent,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
