"""Historical Titan 1x2 long-table -> cutoff snapshot cross-sections.

Derives four diagnostic historical snapshots; prospective use is prohibited.

Produces snapshots per fixture from the
captured long table:

  * ``initial``  — first timestamped pre-kickoff record of each company
  * ``final``    — last timestamped pre-kickoff record of each company
  * ``10h`` / ``1h`` — as-of slices taken 10 hours / 1 hour before kickoff,
    using each company's latest visible market time strictly before the
    target instant (fail-closed if none)

Time model:
  * 2010 legacy payloads: ``market_time_source_raw`` is a full
    ``YYYY,M-D,DD,HH,MM,SS`` string — no year inference needed.
  * Modern payloads: ``market_time_source_raw`` is ``MM-DD HH:MM`` and the
    year is inferred from ``kickoff_source_raw`` (``YYYY,M-D,DD,HH,MM,SS``):
    rollover is inferred only across adjacent December/January months.
    Other future dates stay in the kickoff year and are excluded, never
    shifted into prior history. These inferred times are diagnostic only.

Everything is derived read-only from the capture tables; nothing here writes
to the control database.  The output carries a source-binding receipt so a
snapshot cannot be replayed against a different capture set.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


# kickoff/legacy 时间戳两种写法：`YYYY,MM-?,DD,HH,MM,SS`（带破折号月-周标记）
# 与 `YYYY,M,D,HH,MM,SS`（纯逗号、数字无前导零）。月后破折号数字忽略。
_KICKOFF_RE = re.compile(r"^(\d{4}),(\d{1,2})(?:-\d{1,2})?,(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2})$")
_MODERN_TIME_RE = re.compile(r"^(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{1,2})$")
_LEGACY_TIME_RE = re.compile(r"^(\d{4}),(\d{1,2})(?:-\d{1,2})?,(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2})$")

SNAPSHOT_KINDS = ("initial", "final", "10h", "1h")
_IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class TitanSnapshotError(ValueError):
    """Raised when a historical snapshot cross-section cannot be derived safely."""


def _parse_kickoff(raw: str | None) -> datetime | None:
    if not raw:
        return None
    match = _KICKOFF_RE.match(raw.strip())
    if match is None:
        return None
    year, month, day, hour, minute, second = map(int, match.groups())
    return datetime(year, month, day, hour, minute, second)


def parse_market_time(raw: str | None, *, kickoff: datetime | None) -> datetime | None:
    """Parse a market_time_source_raw into a naive Shanghai wall clock.

    Legacy format carries a full year; modern format infers the year from the
    fixture kickoff, with rollover only across December/January.
    """
    if not raw:
        return None
    text = raw.strip()
    legacy = _LEGACY_TIME_RE.match(text)
    if legacy is not None:
        year, month, day, hour, minute, second = map(int, legacy.groups())
        return datetime(year, month, day, hour, minute, second)
    modern = _MODERN_TIME_RE.match(text)
    if modern is None:
        return None
    month, day, hour, minute = map(int, modern.groups())
    if kickoff is None:
        return None
    year = kickoff.year
    if kickoff.month == 1 and month == 12:
        year -= 1
    elif kickoff.month == 12 and month == 1:
        year += 1
    return datetime(year, month, day, hour, minute)


@dataclass(frozen=True)
class FixtureSnapshot:
    """One fixture's four cross-sectional slices (per company, ordinal 0-based)."""

    fixture_id: str
    kickoff: datetime | None
    kind: str
    quote_key: str  # company_source_id|bookmaker_source_name|record_source_id
    home_odds: float | None
    draw_odds: float | None
    away_odds: float | None
    market_time: datetime | None
    market_time_source_raw: str | None


@dataclass(frozen=True)
class SnapshotSet:
    fixture_id: str
    kickoff: datetime | None
    rows: tuple[FixtureSnapshot, ...]
    source_binding_sha256: str
    captured_quote_count: int
    derived_snapshot_count: int

    def receipt(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "kickoff_source_raw": self.kickoff.isoformat() if self.kickoff else None,
            "snapshot_kinds": list(SNAPSHOT_KINDS),
            "source_binding_sha256": self.source_binding_sha256,
            "implementation_sha256": _IMPLEMENTATION_SHA256,
            "captured_quote_count": self.captured_quote_count,
            "derived_snapshot_count": self.derived_snapshot_count,
            "availability_policy": "HISTORICAL_PROXY",
            "prospective_use": False,
            "source_timezone": "Asia/Shanghai",
            "predicate": "market_time_source_raw < kickoff (per snapshot target)",
        }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fixture_source_binding(con: sqlite3.Connection, batch_id: str) -> str:
    """Bind a fixture's snapshots to its exact captured quote set."""
    rows = con.execute(
        "SELECT company_source_id, bookmaker_source_name, record_source_id, ordinal, home_odds, draw_odds, away_odds, market_time_source_raw "
        "FROM historical_euro_1x2_quote WHERE batch_id=? ORDER BY company_source_id, bookmaker_source_name, record_source_id, ordinal",
        (batch_id,),
    ).fetchall()
    chronology = con.execute(
        "SELECT kickoff_source_raw FROM historical_fixture_observation WHERE batch_id=?", (batch_id,),
    ).fetchall()
    canonical = json.dumps([batch_id, chronology, rows], ensure_ascii=False, separators=(",", ":"))
    return _sha256(canonical)


def _company_rows(con: sqlite3.Connection, batch_id: str) -> dict[str, list[tuple]]:
    """Group a fixture's quotes by record_source_id (company record), ordered by market time."""
    rows = con.execute(
        "SELECT company_source_id, bookmaker_source_name, record_source_id, ordinal, "
        "home_odds, draw_odds, away_odds, market_time_source_raw "
        "FROM historical_euro_1x2_quote WHERE batch_id=? ORDER BY record_source_id, ordinal",
        (batch_id,),
    ).fetchall()
    grouped: dict[str, list[tuple]] = {}
    for row in rows:
        grouped.setdefault(row[2], []).append(row)
    return grouped


def derive_fixture_snapshot(con: sqlite3.Connection, batch_id: str, fixture_id: str) -> SnapshotSet:
    """Derive the four snapshot kinds for one captured fixture."""
    obs = con.execute(
        "SELECT kickoff_source_raw FROM historical_fixture_observation WHERE batch_id=?",
        (batch_id,),
    ).fetchone()
    kickoff = _parse_kickoff(obs[0]) if obs else None
    if kickoff is None:
        raise TitanSnapshotError("missing kickoff chronology")

    grouped = _company_rows(con, batch_id)
    if not grouped:
        raise TitanSnapshotError(f"fixture {fixture_id} has no euro quotes")

    parsed_times: dict[str, datetime | None] = {}
    for record_id, rows in grouped.items():
        for row in rows:
            key = (record_id, row[3])
            if key not in parsed_times:
                parsed_times[key] = parse_market_time(row[7], kickoff=kickoff)

    snapshots: list[FixtureSnapshot] = []
    for record_id, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda r: (parsed_times.get((r[2], r[3])) or datetime.min, r[3]))
        if not rows_sorted:
            continue
        company_id, bookmaker = rows_sorted[0][0], rows_sorted[0][1]

        def make(kind: str, row: tuple) -> FixtureSnapshot:
            return FixtureSnapshot(
                fixture_id=fixture_id, kickoff=kickoff, kind=kind,
                quote_key=f"{company_id}|{bookmaker}|{record_id}",
                home_odds=row[4], draw_odds=row[5], away_odds=row[6],
                market_time=parsed_times.get((row[2], row[3])),
                market_time_source_raw=row[7],
            )

        # initial = 第一条开赛前记录（ordinal 0 或最早时间）
        pre_kickoff = [r for r in rows_sorted if parsed_times.get((r[2], r[3])) is not None
                       and parsed_times[(r[2], r[3])] < kickoff]
        if not pre_kickoff:
            raise TitanSnapshotError("no timestamped pre-kickoff quotes")
        first = pre_kickoff[0]
        last = pre_kickoff[-1]
        snapshots.append(make("initial", first))
        snapshots.append(make("final", last))

        for kind, hours in (("10h", 10), ("1h", 1)):
            if kickoff is None:
                continue
            target = kickoff - timedelta(hours=hours)
            eligible = [r for r in pre_kickoff if (parsed_times.get((r[2], r[3])) or datetime.min) < target]
            if eligible:
                snapshots.append(make(kind, eligible[-1]))

    source_binding = _fixture_source_binding(con, batch_id)
    return SnapshotSet(
        fixture_id=fixture_id, kickoff=kickoff, rows=tuple(snapshots),
        source_binding_sha256=source_binding,
        captured_quote_count=sum(len(rows) for rows in grouped.values()),
        derived_snapshot_count=len(snapshots),
    )


def derive_batch_snapshots(
    data_root: Path | str,
    *,
    fixture_ids: list[str] | None = None,
    limit: int | None = None,
) -> list[SnapshotSet]:
    """Derive snapshots for captured fixtures (optionally a subset).

    Read-only: opens the Titan control DB, derives, and closes.  Returns the
    snapshot sets with their binding receipts; the caller decides how to
    persist them (e.g. an R tibble and its diagnostic receipts).
    """
    database = Path(data_root).resolve() / "control" / "titan" / "control.sqlite"
    con = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        if fixture_ids is not None:
            rows = []
            for fixture_id in fixture_ids:
                batch = con.execute(
                    "SELECT batch_id FROM historical_fixture_capture WHERE source_fixture_id=?",
                    (fixture_id,),
                ).fetchone()
                if batch is None:
                    raise TitanSnapshotError(f"fixture {fixture_id} is absent")
                rows.append((batch[0], fixture_id))
        else:
            rows = con.execute(
                "SELECT batch_id, source_fixture_id FROM historical_fixture_capture ORDER BY source_fixture_id"
            ).fetchall()
            if limit is not None:
                rows = rows[:limit]
        results: list[SnapshotSet] = []
        for batch_id, fixture_id in rows:
            results.append(derive_fixture_snapshot(con, batch_id, fixture_id))
        return results
    finally:
        con.close()
