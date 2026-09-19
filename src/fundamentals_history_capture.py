"""Durable bounded historical capture using the authoritative response writer.

All workers in this collection must share one explicit ledger path. Linux flock
serializes request reservations; SQLite commits reservations before network I/O so a
crash consumes budget rather than permitting invisible retries. No import I/O.
"""
from __future__ import annotations

import fcntl
import math
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.fundamentals_capture import SOURCE_HOSTS, capture_documents


class CaptureCircuitOpen(RuntimeError):
    """No reservation was consumed because the shared circuit is open."""


def capture_rate_source(document):
    """Validate a primary or exact Titan market URL and return its shared rate key.

    Market transport retains ``independent`` solely for the response writer's
    generic HTTPS class; Titan/Jina market bytes are not independent evidence.
    """
    if not isinstance(document, dict):
        raise ValueError("invalid capture document")
    source, url = document.get('source'), str(document.get('url', ''))
    if source in SOURCE_HOSTS and urlparse(url).hostname in SOURCE_HOSTS[source]:
        return source
    if source == 'independent' and (re.fullmatch(r'https://1x2d\.titan007\.com/\d+\.js', url)
            or re.fullmatch(r'https://r\.jina\.ai/https://vip\.titan007\.com/OverDown_n\.aspx\?id=\d+&l=0', url)):
        return 'titan'
    raise ValueError("historical capture source host mismatch")


def capture_history_batch(documents: list[dict], output_dir: str | Path, *,
                          ledger_path: str | Path, budget_id: str, request_budget: int,
                          min_interval_seconds: float = 5.0, fetch=None,
                          wall_clock=None, sleeper=None, cancel_event=None, wait_for_lock=False) -> dict:
    """Capture one immutable batch under a durable request budget.

    Explicit `ledger_path` is shared by all historical workers. Budget identity,
    cap and minimum interval cannot change on reuse. Every request (including
    failures) consumes one reservation; retries require a new output directory
    and consume the same budget. The ledger also shares per-source timing across
    budget IDs. Only reservation/pacing holds the cross-process lock; network and
    persistence may overlap. Backwards wall time fails closed.
    With wait_for_lock=True, queue for the initial ledger lock rather than fail
    immediately; no request is reserved until ownership is acquired.
    Returns the existing capture manifest. Writes ledger, lock and raw output;
    exceptions release all connections/locks. Timeout is 20 seconds, no redirects
    or automatic retries; HTTP failures remain raw evidence. Tests may inject a
    requests-compatible fetch and seconds-since-epoch clock/sleeper.
    """
    if type(wait_for_lock) is not bool:
        raise ValueError("wait_for_lock must be boolean")
    if not isinstance(budget_id, str) or not budget_id.strip():
        raise ValueError("budget_id must be nonblank")
    if type(request_budget) is not int or request_budget < 1:
        raise ValueError("request_budget must be a positive integer")
    if (type(min_interval_seconds) not in (float, int) or
            not math.isfinite(min_interval_seconds) or min_interval_seconds < 1):
        raise ValueError("historical minimum interval is one second")
    if not isinstance(documents, list) or not documents:
        raise ValueError("nonempty documents required")
    for doc in documents:
        capture_rate_source(doc)
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(output)
    ledger = Path(ledger_path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    now = wall_clock or time.time
    pause = sleeper or time.sleep
    source_by_url = {doc["url"]: capture_rate_source(doc) for doc in documents}
    with ledger.with_suffix(ledger.suffix + ".lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait_for_lock else fcntl.LOCK_NB))
        con = sqlite3.connect(ledger)
        session = requests.Session() if fetch is None else None
        if session is not None:
            session.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity', 'X-Return-Format': 'html'})
        try:
            con.execute("PRAGMA synchronous=FULL")
            con.execute("CREATE TABLE IF NOT EXISTS budgets (id TEXT PRIMARY KEY, cap INTEGER NOT NULL, interval REAL NOT NULL, used INTEGER NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS source_clock (source TEXT PRIMARY KEY, started REAL NOT NULL, next_allowed REAL NOT NULL)")
            con.execute("INSERT OR IGNORE INTO budgets VALUES (?, ?, ?, 0)",
                        (budget_id, request_budget, min_interval_seconds))
            policy = con.execute("SELECT cap, interval FROM budgets WHERE id=?", (budget_id,)).fetchone()
            if policy != (request_budget, min_interval_seconds):
                raise ValueError("immutable budget policy mismatch")
            con.commit()
            used = con.execute("SELECT used FROM budgets WHERE id=?", (budget_id,)).fetchone()[0]
            if len(documents) > request_budget - used:
                raise ValueError("request budget exhausted for declared batch")

            def reserved_fetch(url, timeout, stream):
                fcntl.flock(lock, fcntl.LOCK_EX)
                source = source_by_url[url]
                stamp = now()
                if type(stamp) not in (int, float) or not math.isfinite(stamp):
                    raise ValueError("invalid wall clock")
                previous = con.execute("SELECT started, next_allowed FROM source_clock WHERE source=?", (source,)).fetchone()
                if previous:
                    if stamp < previous[0]:
                        raise ValueError("wall clock moved backwards")
                    if stamp < previous[1]:
                        pause(previous[1] - stamp)
                        stamp = now()
                        if not math.isfinite(stamp) or stamp < previous[1]:
                            raise ValueError("rate-limit wait did not advance clock")
                if cancel_event is not None and cancel_event.is_set():
                    raise CaptureCircuitOpen("capture circuit open")
                con.execute("BEGIN IMMEDIATE")
                used = con.execute("SELECT used FROM budgets WHERE id=?", (budget_id,)).fetchone()[0]
                if used >= request_budget:
                    con.rollback()
                    raise ValueError("request budget exhausted")
                con.execute("UPDATE budgets SET used=used+1 WHERE id=?", (budget_id,))
                con.execute("INSERT INTO source_clock VALUES (?, ?, ?) ON CONFLICT(source) DO UPDATE SET started=excluded.started, next_allowed=excluded.next_allowed",
                            (source, stamp, stamp + min_interval_seconds))
                con.commit()
                fcntl.flock(lock, fcntl.LOCK_UN)
                if fetch is not None:
                    return fetch(url, timeout=timeout, stream=stream)
                return session.get(url, timeout=timeout, stream=stream, allow_redirects=False)

            return capture_documents(documents, output, fetch=reserved_fetch,
                                     max_attempts=1, timeout_seconds=20)
        finally:
            if session is not None:
                session.close()
            con.close()
