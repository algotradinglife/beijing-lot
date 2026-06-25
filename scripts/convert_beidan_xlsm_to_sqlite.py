#!/usr/bin/env python3
"""Convert the vendor Beidan XLSM workbook into a normalized SQLite DB.

The source workbook is large and macro-enabled. This script never executes
macros; it treats the XLSM as a ZIP of XML files and streams the main data
sheet row by row.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile


SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CELL_RE = re.compile(rb'<c r="([A-Z]+)([0-9]+)"([^>]*)>(.*?)</c>')
VALUE_RE = re.compile(rb"<v>(.*?)</v>")
ROW_RE = re.compile(rb'<row r="([0-9]+)"')

BOOKS_1X2 = [
    "皇冠", "澳门", "Bet365", "香港马会", "韦德", "威廉", "立博", "易博胜",
    "Interwet", "Bwin", "竞彩足球", "10bet", "Oddset", "Pinna*", "18*",
]
BOOKS_ASIAN = [
    "皇冠", "澳门", "Bet365", "香港马会", "韦德", "易胜博", "明升", "金宝博",
    "利*", "12*", "盈*", "18*", "平*", "Interwet*", "10*", "威廉",
    "Bwin", "立博",
]
SNAPSHOTS_1X2 = [("initial", 0), ("1h", 3), ("10h", 6), ("final", 9)]
SNAPSHOTS_LINE = [("initial", 0), ("1h", 3), ("10h", 6), ("final", 9)]

GOAL_OUTCOMES = ["0~1", "2~3", "4~6", "7+"]
HALF_FULL_OUTCOMES = ["主主", "主和", "主客", "和主", "和和", "和负", "客主", "客和", "客客"]
SCORE_OUTCOMES = [
    "1:0", "2:0", "2:1", "3:0", "3:1", "3:2", "4:0", "4:1", "4:2", "4:3",
    "0:0", "1:1", "2:2", "3:3", "4:4", "其他", "0:1", "0:2", "1:2", "0:3",
    "1:3", "2:3", "0:4", "1:4", "2:4", "3:4",
]


def col_index(col: bytes) -> int:
    n = 0
    for b in col:
        n = n * 26 + (b - 64)
    return n


def text_of_si(si: ET.Element) -> str:
    return "".join(t.text or "" for t in si.iter(SHEET_NS + "t"))


def parse_shared_strings(zf: ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return [text_of_si(si) for si in root.findall(SHEET_NS + "si")]


def cell_value(attrs: bytes, inner: bytes, shared: list[str]) -> str:
    m = VALUE_RE.search(inner)
    if not m:
        return ""
    raw = m.group(1).decode("utf-8", errors="replace")
    if b't="s"' in attrs:
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return ""
    return raw


def to_float(value: str | None) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def excel_datetime(value: str | None) -> str | None:
    serial = to_float(value)
    if serial is None or serial <= 0:
        return None
    # Excel's Windows date system, including the 1900 leap-year compatibility.
    dt = datetime(1899, 12, 30) + timedelta(days=serial)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_row(row_xml: bytes, shared: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in CELL_RE.finditer(row_xml):
        out[col_index(m.group(1))] = cell_value(m.group(3), m.group(4), shared)
    return out


def iter_rows(zf: ZipFile, sheet_name: str, shared: list[str]):
    buf = b""
    with zf.open(sheet_name) as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk and not buf:
                break
            buf += chunk
            while True:
                end = buf.find(b"</row>")
                if end < 0:
                    break
                row_xml = buf[: end + 6]
                buf = buf[end + 6 :]
                row_match = ROW_RE.search(row_xml)
                if not row_match:
                    continue
                yield int(row_match.group(1)), parse_row(row_xml, shared)
            if not chunk:
                break


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=MEMORY;
        PRAGMA locking_mode=EXCLUSIVE;

        CREATE TABLE source_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE matches (
            match_id INTEGER PRIMARY KEY,
            sheet_row INTEGER NOT NULL UNIQUE,
            issue TEXT,
            match_idx INTEGER,
            kickoff_serial REAL,
            kickoff_ts TEXT,
            league TEXT,
            home_rank TEXT,
            home TEXT,
            score TEXT,
            away TEXT,
            away_rank TEXT,
            handicap_line REAL,
            halftime_score TEXT,
            result_label TEXT,
            total_goals INTEGER,
            half_full TEXT,
            provider_match_id TEXT,
            ts_10h_serial REAL,
            ts_10h TEXT,
            home_team_id TEXT,
            away_team_id TEXT,
            sclassid TEXT
        );

        CREATE TABLE market_snapshots (
            match_id INTEGER NOT NULL,
            market TEXT NOT NULL,
            bookmaker TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            v1 REAL,
            v2 REAL,
            v3 REAL
        );

        CREATE TABLE exotic_odds (
            match_id INTEGER NOT NULL,
            market TEXT NOT NULL,
            outcome TEXT NOT NULL,
            odds REAL
        );

        CREATE TABLE issue_list (
            issue TEXT PRIMARY KEY
        );

        CREATE TABLE line_lookup (
            row_no INTEGER PRIMARY KEY,
            c1 REAL,
            c2 TEXT,
            c3 TEXT,
            c4 TEXT,
            c5 TEXT,
            c6 TEXT,
            c7 TEXT,
            c8 TEXT
        );
        """
    )


def make_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX idx_matches_issue_idx ON matches(issue, match_idx);
        CREATE INDEX idx_matches_league ON matches(league);
        CREATE INDEX idx_market_match ON market_snapshots(match_id);
        CREATE INDEX idx_market_lookup ON market_snapshots(market, bookmaker, snapshot);
        CREATE INDEX idx_exotic_match ON exotic_odds(match_id);
        CREATE INDEX idx_exotic_market ON exotic_odds(market, outcome);
        """
    )


def append_market_rows(
    out: list[tuple],
    match_id: int,
    values: dict[int, str],
    *,
    market: str,
    start_col: int,
    books: list[str],
) -> None:
    for book_i, book in enumerate(books):
        base = start_col + book_i * 12
        for snapshot, offset in SNAPSHOTS_1X2:
            out.append(
                (
                    match_id,
                    market,
                    book,
                    snapshot,
                    to_float(values.get(base + offset)),
                    to_float(values.get(base + offset + 1)),
                    to_float(values.get(base + offset + 2)),
                )
            )


def append_exotic_rows(out: list[tuple], match_id: int, values: dict[int, str]) -> None:
    for i, outcome in enumerate(GOAL_OUTCOMES, start=815):
        out.append((match_id, "goals", outcome, to_float(values.get(i))))
    for i, outcome in enumerate(HALF_FULL_OUTCOMES, start=819):
        out.append((match_id, "half_full", outcome, to_float(values.get(i))))
    for i, outcome in enumerate(SCORE_OUTCOMES, start=828):
        out.append((match_id, "score", outcome, to_float(values.get(i))))


def insert_batches(conn: sqlite3.Connection, batches: dict[str, list]) -> None:
    if batches["matches"]:
        conn.executemany(
            """
            INSERT INTO matches (
                match_id, sheet_row, issue, match_idx, kickoff_serial, kickoff_ts,
                league, home_rank, home, score, away, away_rank, handicap_line,
                halftime_score, result_label, total_goals, half_full,
                provider_match_id, ts_10h_serial, ts_10h, home_team_id,
                away_team_id, sclassid
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            batches["matches"],
        )
        batches["matches"].clear()
    if batches["market"]:
        conn.executemany(
            "INSERT INTO market_snapshots(match_id, market, bookmaker, snapshot, v1, v2, v3) VALUES (?,?,?,?,?,?,?)",
            batches["market"],
        )
        batches["market"].clear()
    if batches["exotic"]:
        conn.executemany(
            "INSERT INTO exotic_odds(match_id, market, outcome, odds) VALUES (?,?,?,?)",
            batches["exotic"],
        )
        batches["exotic"].clear()


def convert(
    input_path: Path,
    output_path: Path,
    *,
    batch_size: int,
    no_exotic: bool,
    limit: int | None = None,
) -> None:
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    conn = sqlite3.connect(tmp_path)
    create_schema(conn)
    conn.execute("BEGIN")
    batches: dict[str, list] = {"matches": [], "market": [], "exotic": []}

    with ZipFile(input_path) as zf:
        shared = parse_shared_strings(zf)
        conn.executemany(
            "INSERT OR IGNORE INTO issue_list(issue) VALUES (?)",
            ((str(values.get(1)),) for row_no, values in iter_rows(zf, "xl/worksheets/sheet2.xml", shared) if row_no > 1 and values.get(1)),
        )
        conn.executemany(
            "INSERT INTO line_lookup(row_no, c1, c2, c3, c4, c5, c6, c7, c8) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                (
                    row_no,
                    to_float(values.get(1)),
                    values.get(2),
                    values.get(3),
                    values.get(4),
                    values.get(5),
                    values.get(6),
                    values.get(7),
                    values.get(8),
                )
                for row_no, values in iter_rows(zf, "xl/worksheets/sheet3.xml", shared)
            ),
        )

        match_id = 0
        for row_no, values in iter_rows(zf, "xl/worksheets/sheet1.xml", shared):
            if row_no <= 2:
                continue
            match_id += 1
            if limit is not None and match_id > limit:
                break
            kickoff_serial = to_float(values.get(3))
            ts_10h_serial = to_float(values.get(16))
            batches["matches"].append(
                (
                    match_id,
                    row_no,
                    values.get(1),
                    int(to_float(values.get(2)) or 0) or None,
                    kickoff_serial,
                    excel_datetime(values.get(3)),
                    values.get(4),
                    values.get(5),
                    values.get(6),
                    values.get(7),
                    values.get(8),
                    values.get(9),
                    to_float(values.get(10)),
                    values.get(11),
                    values.get(12),
                    int(to_float(values.get(13)) or 0) if to_float(values.get(13)) is not None else None,
                    values.get(14),
                    values.get(15),
                    ts_10h_serial,
                    excel_datetime(values.get(16)),
                    values.get(17),
                    values.get(18),
                    values.get(814),
                )
            )

            append_market_rows(batches["market"], match_id, values, market="euro_1x2", start_col=19, books=BOOKS_1X2)
            append_market_rows(batches["market"], match_id, values, market="kelly_1x2", start_col=200, books=BOOKS_1X2)
            append_market_rows(batches["market"], match_id, values, market="asian_handicap", start_col=381, books=BOOKS_ASIAN)
            append_market_rows(batches["market"], match_id, values, market="over_under", start_col=598, books=BOOKS_ASIAN)
            if not no_exotic:
                append_exotic_rows(batches["exotic"], match_id, values)

            if match_id % batch_size == 0:
                insert_batches(conn, batches)
                conn.commit()
                conn.execute("BEGIN")
                elapsed = time.time() - started
                print(
                    f"converted matches={match_id:,} elapsed={elapsed/60:.1f}m",
                    file=sys.stderr,
                    flush=True,
                )

    insert_batches(conn, batches)
    conn.execute("COMMIT")
    conn.executemany(
        "INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)",
        [
            ("source_path", str(input_path)),
            ("converted_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("no_exotic", str(int(no_exotic))),
        ],
    )
    conn.commit()
    print("building indexes...", file=sys.stderr, flush=True)
    make_indexes(conn)
    conn.close()
    if output_path.exists():
        output_path.unlink()
    os.replace(tmp_path, output_path)
    elapsed = time.time() - started
    print(f"done output={output_path} elapsed={elapsed/60:.1f}m", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--no-exotic", action="store_true", help="Skip goals/half-full/score odds.")
    parser.add_argument("--limit", type=int, help="Convert only the first N data rows for smoke testing.")
    args = parser.parse_args()
    convert(
        args.input,
        args.output,
        batch_size=args.batch_size,
        no_exotic=args.no_exotic,
        limit=args.limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
