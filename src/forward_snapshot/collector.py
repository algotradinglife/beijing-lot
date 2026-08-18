"""Rate-limited live collector for Nowscore BJ TypeID=5 pages.

Network acquisition is explicit: callers pass a fetch function so tests and
replay never hit the network.  The CLI uses urllib only after an operator sets
BEIJING_LOT_DATA_ROOT.  It captures the raw issue page, then every discovered
per-match Sp值变化表 page, retaining parse failures as structured log records.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Callable

from .store import HKT, SnapshotStore

ISSUE_URL = "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum={issue}"
PARSER_VERSION = "bj248-nowscore-v1"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_bytes(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; beijing-lot/forward-snapshot)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if int(response.status) != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        return response.read()


def _kickoff_utc(schedule_date: str, kickoff_time: str) -> str:
    """Strictly parse Nowscore schedule date/time; ambiguity fails closed."""
    candidates = (f"{schedule_date} {kickoff_time}", kickoff_time)
    for candidate in candidates:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(candidate.strip(), fmt)
            except ValueError:
                continue
            if fmt == "%m-%d %H:%M":
                parsed = parsed.replace(year=datetime.now(HKT).year)
            return parsed.replace(tzinfo=HKT).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ValueError(f"unparseable Nowscore kickoff: {schedule_date!r} {kickoff_time!r}")


def _log_failure(store: SnapshotStore, record: dict) -> None:
    directory = store.root / "forward_snapshot" / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "collector_failures.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def collect_issue(store: SnapshotStore, issue: str, *, fetch: Callable[[str], bytes] = fetch_bytes,
                  clock: Callable[[], str] = now_utc, min_interval_seconds: float = 1.0) -> dict:
    """Capture one active issue once. Failures are returned and logged, never zero-filled."""
    from scripts.scrape_nowscore_bjdc import parse_rows

    poll_key = f"{issue}:{clock()}"
    issue_url = ISSUE_URL.format(issue=issue)
    requested = clock()
    try:
        issue_payload = fetch(issue_url)
        received = clock()
        rows = parse_rows(issue, issue_payload.decode("utf-8", errors="replace"), received)
        store.record_issue_page(capture_key=f"{poll_key}:issue", issue=issue, payload=issue_payload,
                                source_url=issue_url, requested_at_utc=requested,
                                trusted_received_at_utc=received, parser_version=PARSER_VERSION,
                                acquisition_result="OK", rows_parsed=len(rows))
    except Exception as exc:
        failure = {"issue": issue, "source_url": issue_url, "requested_at_utc": requested,
                   "trusted_received_at_utc": clock(), "stage": "issue_page", "error": repr(exc)}
        _log_failure(store, failure)
        return {"issue": issue, "captured": 0, "failures": [failure]}

    captured, failures = 0, []
    for index, row in enumerate(rows):
        sp_url = str(row.get("sp_url") or "")
        try:
            kickoff = _kickoff_utc(str(row.get("schedule_date") or ""), str(row.get("kickoff_time") or ""))
            if not sp_url:
                raise ValueError("Nowscore issue row has no TypeID=5 Sp值变化表 URL")
            requested = clock()
            payload = fetch(sp_url)
            received = clock()
            store.record_history(capture_key=f"{poll_key}:match:{row['match_idx']}", payload=payload,
                                 issue=issue, match_idx=int(row["match_idx"]), kickoff_at_utc=kickoff,
                                 native_handicap_line=row.get("handicap_line"), sale_status=("OPEN" if row.get("can_sale") else "CLOSED"),
                                 issue_url=issue_url, requested_at_utc=requested,
                                 trusted_received_at_utc=received, parser_version=PARSER_VERSION,
                                 acquisition_result="OK")
            captured += 1
        except Exception as exc:
            failure = {"issue": issue, "match_idx": row.get("match_idx"), "source_url": sp_url,
                       "trusted_received_at_utc": clock(), "stage": "sp_history", "error": repr(exc)}
            failures.append(failure)
            _log_failure(store, failure)
        if index < len(rows) - 1 and min_interval_seconds > 0:
            time.sleep(min_interval_seconds)
    return {"issue": issue, "captured": captured, "failures": failures}
