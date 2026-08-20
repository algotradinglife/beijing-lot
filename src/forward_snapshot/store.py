"""Append-only Nowscore TypeID=5 raw capture and semantic verification.

The raw body is content-addressed below BEIJING_LOT_DATA_ROOT.  Every poll has
its own receipt keyed by caller-provided capture_key; a retry with the same key
is a no-op, while an independently observed repeat is retained.  The normalized
vectors are re-derived from raw bodies by ``verify_store`` rather than trusted.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bs4 import BeautifulSoup

FORWARD_SOURCE_ID = "nowscore_bj_sp_change_typeid5"
DATA_ROOT_ENV = "BEIJING_LOT_DATA_ROOT"
HKT = timezone(timedelta(hours=8))
OUTCOMES = ("3", "1", "0")


@dataclass(frozen=True)
class Vector:
    outcome_code: str
    sp: float
    source_changed_at_utc: str


@dataclass(frozen=True)
class ParsedHistory:
    source_id: str
    source_url: str
    vectors: tuple[Vector, ...]


@dataclass(frozen=True)
class RecordResult:
    inserted_vectors: int


def _utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value!r}")
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_utc(value: str) -> str:
    """Normalize every persisted/comparison time to one sortable UTC spelling."""
    return _iso(_utc(value))


def validate_history_url(source_url: str, *, issue: str, match_idx: int) -> str:
    """Allow only the exact Nowscore TypeID=5 history route for this fixture."""
    parts = urlsplit(source_url)
    expected_path = f"/sp/danchang/{issue}_{match_idx}_5.html"
    if (parts.scheme, parts.hostname, parts.port, parts.username, parts.password, parts.path, parts.fragment) != (
        "https", "cp.nowscore.com", None, None, None, expected_path, ""
    ):
        raise ValueError("history URL is not an allowlisted Nowscore TypeID=5 endpoint")
    return source_url


def _source_time(text: str, kickoff_at_utc: str) -> str:
    try:
        month, day = (int(part) for part in text.split()[0].split("-"))
        hour, minute = (int(part) for part in text.split()[1].split(":"))
    except (IndexError, ValueError) as exc:
        raise ValueError(f"invalid Nowscore source change time: {text!r}") from exc
    kickoff = _utc(kickoff_at_utc).astimezone(HKT)
    candidates = []
    for year in (kickoff.year - 1, kickoff.year, kickoff.year + 1):
        try:
            candidates.append(datetime(year, month, day, hour, minute, tzinfo=HKT))
        except ValueError:
            pass
    if not candidates:
        raise ValueError(f"unresolvable Nowscore source change time: {text!r}")
    chosen = min(candidates, key=lambda candidate: abs((candidate - kickoff).total_seconds()))
    if chosen >= kickoff or chosen < kickoff - timedelta(days=45):
        raise ValueError(f"Nowscore source change time is not strictly pre-kickoff: {chosen.isoformat()}")
    return _iso(chosen)


def parse_nowscore_sp_history(payload: bytes, *, issue: str, match_idx: int,
                               kickoff_at_utc: str, source_url: str) -> ParsedHistory:
    """Fail closed unless the page is the exact 3/1/0 Sp值变化表 shape."""
    soup = BeautifulSoup(payload.decode("utf-8", errors="replace"), "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if "Sp值变化表" not in title:
        raise ValueError(f"unexpected Nowscore SP history title: {title!r}")
    table = soup.find("table")
    if table is None:
        raise ValueError("Nowscore SP history table missing")
    rows = table.find_all("tr")
    if len(rows) < 2:
        raise ValueError("Nowscore SP history requires rows")
    header = tuple(cell.get_text(" ", strip=True) for cell in rows[0].find_all("td"))
    if header != ("胜", "平", "负", "变化时间"):
        raise ValueError(f"Nowscore TypeID=5 header mismatch: {header!r}")
    vectors: list[Vector] = []
    for row in rows[1:]:
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cells) != 4:
            raise ValueError("Nowscore TypeID=5 complete 3/1/0 row required")
        try:
            values = tuple(float(item) for item in cells[:3])
        except ValueError as exc:
            raise ValueError("Nowscore TypeID=5 complete 3/1/0 numeric vector required") from exc
        if any(not math.isfinite(item) or item <= 1.0 or item == 0.65 for item in values):
            raise ValueError("Nowscore TypeID=5 complete 3/1/0 domain-valid vector required")
        changed = _source_time(cells[3], kickoff_at_utc)
        vectors.extend(Vector(outcome, value, changed) for outcome, value in zip(OUTCOMES, values, strict=True))
    # A duplicated source timestamp is either exactly the same vector (dedupe)
    # or contradictory source evidence; never use last-write-wins.
    unique: dict[tuple[str, str], float] = {}
    for vector in vectors:
        key = (vector.source_changed_at_utc, vector.outcome_code)
        if key in unique and unique[key] != vector.sp:
            raise ValueError("conflicting Nowscore change rows at the same source timestamp")
        unique[key] = vector.sp
    deduped = tuple(
        Vector(code, value, changed)
        for (changed, code), value in sorted(
            unique.items(), key=lambda item: (item[0][0], OUTCOMES.index(item[0][1]))
        )
    )
    if not deduped or len(deduped) % 3:
        raise ValueError("Nowscore TypeID=5 complete 3/1/0 vector required")
    return ParsedHistory(
        FORWARD_SOURCE_ID,
        validate_history_url(source_url, issue=issue, match_idx=match_idx),
        deduped,
    )


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


class SnapshotStore:
    """The live control store.  All paths are rooted by an operator-selected root."""

    def __init__(self, root: Path, conn: sqlite3.Connection):
        self.root = root
        self.conn = conn
        self.raw_dir = root / "forward_snapshot" / "raw"
        self.manifest_path = root / "forward_snapshot" / "capture_manifest.json"

    @classmethod
    def open(cls, root: Path | None = None) -> "SnapshotStore":
        selected = Path(root or os.environ.get(DATA_ROOT_ENV, Path.cwd() / "data"))
        selected.mkdir(parents=True, exist_ok=True)
        control = selected / "forward_snapshot" / "control"
        control.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(control / "forward_snapshot.sqlite", isolation_level=None)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS capture_receipt (
              capture_key TEXT PRIMARY KEY, source_id TEXT NOT NULL,
              issue_code TEXT NOT NULL, match_idx INTEGER NOT NULL,
              fixture_key TEXT NOT NULL,
              issue_capture_key TEXT NOT NULL REFERENCES issue_capture_receipt(capture_key),
              source_url TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL, raw_path TEXT NOT NULL,
              requested_at_utc TEXT NOT NULL, trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL, acquisition_result TEXT NOT NULL,
              sale_status TEXT NOT NULL, native_handicap_line REAL,
              kickoff_at_utc TEXT NOT NULL,
              CHECK(requested_at_utc <= trusted_received_at_utc)
            );
            CREATE TABLE IF NOT EXISTS issue_capture_receipt (
              capture_key TEXT PRIMARY KEY, source_id TEXT NOT NULL,
              issue_code TEXT NOT NULL, source_url TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL, raw_path TEXT NOT NULL,
              requested_at_utc TEXT NOT NULL, trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL, acquisition_result TEXT NOT NULL,
              rows_parsed INTEGER NOT NULL,
              CHECK(requested_at_utc <= trusted_received_at_utc)
            );
            CREATE TABLE IF NOT EXISTS sp_change_vector (
              capture_key TEXT NOT NULL REFERENCES capture_receipt(capture_key),
              source_changed_at_utc TEXT NOT NULL,
              outcome_code TEXT NOT NULL CHECK(outcome_code IN ('3','1','0')),
              sp REAL NOT NULL CHECK(sp > 1.0 AND sp != 0.65),
              PRIMARY KEY(capture_key, source_changed_at_utc, outcome_code)
            );
        """)
        return cls(selected, conn)

    def close(self) -> None:
        self.conn.close()

    def count(self, table: str) -> int:
        if table not in {"capture_receipt", "sp_change_vector"}:
            raise ValueError("unrecognized table")
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def raw_payload_count(self) -> int:
        return len(list(self.raw_dir.rglob("*.html"))) if self.raw_dir.exists() else 0

    def record_issue_page(self, *, capture_key: str, issue: str, payload: bytes, source_url: str,
                          requested_at_utc: str, trusted_received_at_utc: str,
                          parser_version: str, acquisition_result: str, rows_parsed: int) -> bool:
        """Record the raw TypeID=5 issue-page state for every poll, append-only."""
        requested_at_utc = _canonical_utc(requested_at_utc)
        trusted_received_at_utc = _canonical_utc(trusted_received_at_utc)
        if _utc(requested_at_utc) > _utc(trusted_received_at_utc):
            raise ValueError("requested time cannot follow trusted receive time")
        raw_sha = _sha(payload)
        raw_rel = f"{raw_sha[:2]}/{raw_sha}.html"
        expected = (FORWARD_SOURCE_ID, issue, source_url, raw_sha, raw_rel, requested_at_utc,
                    trusted_received_at_utc, parser_version, acquisition_result, rows_parsed)
        existing = self.conn.execute("""
            SELECT source_id,issue_code,source_url,raw_sha256,raw_path,requested_at_utc,
                   trusted_received_at_utc,parser_version,acquisition_result,rows_parsed
            FROM issue_capture_receipt WHERE capture_key=?
        """, (capture_key,)).fetchone()
        if existing:
            if tuple(existing) == expected:
                return False
            raise ValueError(f"capture key collision for issue page: {capture_key}")
        _atomic_bytes(self.raw_dir / raw_rel, payload)
        with self.conn:
            self.conn.execute("""
                INSERT INTO issue_capture_receipt VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (capture_key, FORWARD_SOURCE_ID, issue, source_url, raw_sha, raw_rel,
                  requested_at_utc, trusted_received_at_utc, parser_version,
                  acquisition_result, rows_parsed))
        self._write_manifest()
        return True

    def record_history(self, *, capture_key: str, payload: bytes, issue: str, match_idx: int,
                       kickoff_at_utc: str, native_handicap_line: float | None,
                       sale_status: str, issue_capture_key: str, source_url: str, requested_at_utc: str,
                       trusted_received_at_utc: str, parser_version: str,
                       acquisition_result: str) -> RecordResult:
        """Append one complete raw capture; collisions are never silently discarded."""
        if not capture_key or not issue or match_idx <= 0:
            raise ValueError("capture key, issue and positive match index are required")
        requested_at_utc = _canonical_utc(requested_at_utc)
        trusted_received_at_utc = _canonical_utc(trusted_received_at_utc)
        kickoff_at_utc = _canonical_utc(kickoff_at_utc)
        if _utc(requested_at_utc) > _utc(trusted_received_at_utc):
            raise ValueError("requested time cannot follow trusted receive time")
        if _utc(trusted_received_at_utc) >= _utc(kickoff_at_utc):
            raise ValueError("post-kickoff receipt cannot enter forward store")
        issue_receipt = self.conn.execute("""
            SELECT issue_code,acquisition_result,raw_sha256,raw_path,trusted_received_at_utc
            FROM issue_capture_receipt WHERE capture_key=?
        """, (issue_capture_key,)).fetchone()
        if issue_receipt is None or issue_receipt[:2] != (issue, "OK"):
            raise ValueError("history receipt requires its successful raw issue-page receipt")
        _, _, issue_raw_sha, issue_raw_path, issue_received = issue_receipt
        issue_path = self.raw_dir / issue_raw_path
        if not issue_path.exists() or _sha(issue_path.read_bytes()) != issue_raw_sha:
            raise ValueError("history receipt source trace raw issue evidence is unavailable")
        from scripts.scrape_nowscore_bjdc import parse_rows
        issue_rows = parse_rows(issue, issue_path.read_bytes().decode("utf-8", errors="replace"), issue_received)
        if (match_idx, source_url) not in {(int(row["match_idx"]), str(row["sp_url"])) for row in issue_rows}:
            raise ValueError("history receipt source trace is absent from its linked raw issue page")
        parsed = parse_nowscore_sp_history(payload, issue=issue, match_idx=match_idx,
                                            kickoff_at_utc=kickoff_at_utc, source_url=source_url)
        if any(_utc(vector.source_changed_at_utc) > _utc(trusted_received_at_utc)
               for vector in parsed.vectors):
            raise ValueError("source change time cannot follow trusted receive time")
        raw_sha = _sha(payload)
        raw_rel = f"{raw_sha[:2]}/{raw_sha}.html"
        fixture_key = f"{issue}:{match_idx}"
        expected = (parsed.source_id, issue, match_idx, fixture_key, issue_capture_key, parsed.source_url,
                    raw_sha, raw_rel, requested_at_utc, trusted_received_at_utc, parser_version,
                    acquisition_result, sale_status, native_handicap_line, kickoff_at_utc)
        existing = self.conn.execute("""
            SELECT source_id,issue_code,match_idx,fixture_key,issue_capture_key,source_url,raw_sha256,
                   raw_path,requested_at_utc,trusted_received_at_utc,parser_version,acquisition_result,
                   sale_status,native_handicap_line,kickoff_at_utc
            FROM capture_receipt WHERE capture_key=?
        """, (capture_key,)).fetchone()
        if existing:
            if tuple(existing) == expected:
                return RecordResult(0)
            raise ValueError(f"capture key collision for history receipt: {capture_key}")
        _atomic_bytes(self.raw_dir / raw_rel, payload)
        with self.conn:
            self.conn.execute("""
                INSERT INTO capture_receipt VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (capture_key, parsed.source_id, issue, match_idx, fixture_key, issue_capture_key,
                  parsed.source_url, raw_sha, raw_rel, requested_at_utc, trusted_received_at_utc,
                  parser_version, acquisition_result, sale_status, native_handicap_line, kickoff_at_utc))
            self.conn.executemany("""
                INSERT INTO sp_change_vector(capture_key,source_changed_at_utc,outcome_code,sp)
                VALUES(?,?,?,?)
            """, [(capture_key, vector.source_changed_at_utc, vector.outcome_code, vector.sp)
                   for vector in parsed.vectors])
        self._write_manifest()
        return RecordResult(len(parsed.vectors))

    def _manifest_payload(self) -> bytes:
        receipts = [dict(zip(("capture_key", "source_id", "issue_code", "match_idx", "fixture_key", "issue_capture_key", "source_url", "raw_sha256", "raw_path", "requested_at_utc", "trusted_received_at_utc", "parser_version", "acquisition_result", "sale_status", "native_handicap_line", "kickoff_at_utc"), row))
                    for row in self.conn.execute("SELECT * FROM capture_receipt ORDER BY capture_key")]
        vectors = [dict(zip(("capture_key", "source_changed_at_utc", "outcome_code", "sp"), row))
                   for row in self.conn.execute("SELECT * FROM sp_change_vector ORDER BY capture_key,source_changed_at_utc,outcome_code")]
        issue_pages = [dict(zip(("capture_key", "source_id", "issue_code", "source_url", "raw_sha256", "raw_path", "requested_at_utc", "trusted_received_at_utc", "parser_version", "acquisition_result", "rows_parsed"), row))
                       for row in self.conn.execute("SELECT * FROM issue_capture_receipt ORDER BY capture_key")]
        return (json.dumps({"schema_version": "bj248-forward-snapshot-v1", "issue_pages": issue_pages,
                            "receipts": receipts, "vectors": vectors}, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

    def _write_manifest(self) -> None:
        _atomic_bytes(self.manifest_path, self._manifest_payload())

    def seal_manifest(self) -> str:
        self._write_manifest()
        return _sha(self.manifest_path.read_bytes())


def verify_store(store: SnapshotStore, *, trusted_manifest_sha256: str) -> list[str]:
    """Rebuild vectors and source traces from raw evidence plus an external anchor."""
    from scripts.scrape_nowscore_bjdc import parse_rows

    problems: list[str] = []
    if not store.manifest_path.exists():
        return ["manifest missing"]
    if _sha(store.manifest_path.read_bytes()) != trusted_manifest_sha256:
        problems.append("manifest does not match trusted anchor")
    if store.manifest_path.read_bytes() != store._manifest_payload():
        problems.append("semantic payload mismatch: manifest does not match control ledger")

    issue_traces: dict[str, tuple[str, set[tuple[int, str]]]] = {}
    for key, issue, sha, raw_path, received, result in store.conn.execute("""
        SELECT capture_key,issue_code,raw_sha256,raw_path,trusted_received_at_utc,acquisition_result
        FROM issue_capture_receipt ORDER BY capture_key
    """):
        path = store.raw_dir / raw_path
        if not path.exists() or _sha(path.read_bytes()) != sha:
            problems.append(f"raw issue evidence mismatch: {key}")
            continue
        if result != "OK":
            continue
        rows = parse_rows(issue, path.read_bytes().decode("utf-8", errors="replace"), received)
        issue_traces[key] = (issue, {(int(row["match_idx"]), str(row["sp_url"])) for row in rows})

    for row in store.conn.execute("""
        SELECT capture_key,issue_code,match_idx,kickoff_at_utc,issue_capture_key,source_url,
               raw_sha256,raw_path
        FROM capture_receipt ORDER BY capture_key
    """):
        key, issue, index, kickoff, issue_key, url, sha, raw_path = row
        trace = issue_traces.get(issue_key)
        if trace is None or trace[0] != issue or (index, url) not in trace[1]:
            problems.append(f"semantic payload mismatch: source trace {key}")
        path = store.raw_dir / raw_path
        if not path.exists() or _sha(path.read_bytes()) != sha:
            problems.append(f"raw evidence mismatch: {key}")
            continue
        try:
            parsed = parse_nowscore_sp_history(path.read_bytes(), issue=issue, match_idx=index,
                                                kickoff_at_utc=kickoff, source_url=url)
        except ValueError as exc:
            problems.append(f"semantic payload mismatch: {key}: {exc}")
            continue
        expected = {(v.source_changed_at_utc, v.outcome_code, v.sp) for v in parsed.vectors}
        actual = set(store.conn.execute(
            "SELECT source_changed_at_utc,outcome_code,sp FROM sp_change_vector WHERE capture_key=?", (key,)
        ))
        if expected != actual:
            problems.append(f"semantic payload mismatch: vectors {key}")
    return problems
