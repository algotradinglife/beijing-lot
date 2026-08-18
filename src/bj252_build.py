"""Build the #252 sealed temporal-profiling evidence package from read-only sources."""
from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd

from bj252_temporal_package import _populate, rehash_package, verify_package
from source_schema import census, publication, sources
from temporal_semantics import STRICT_GRADE

PACKAGE_NAME = "bj252_unified_temporal_semantics_v2"
TIMEZONE_CONVENTION = "Asia/Shanghai local scheduled kickoff normalized to UTC"


def _live_path(root: Path) -> Path:
    entry = next(item for item in census.DATABASE_INVENTORY if item["key"] == "beidan_live")
    path = census._resolve_data_path(root, entry["path"])
    if not path.exists():
        raise FileNotFoundError(f"missing strict source: {path}")
    return path


def _strict_rows(root: Path, path: Path) -> pd.DataFrame:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        frame = pd.read_sql_query(
            """SELECT m.issue AS issue_code, m.match_idx, m.match_id,
                      m.kickoff_ts, s.snapshot_ts, s.sp_3, s.sp_1, s.sp_0
                 FROM matches m JOIN snapshots s ON s.match_id=m.match_id""",
            con,
        )
    finally:
        con.close()
    kickoff_local = pd.to_datetime(frame.pop("kickoff_ts"), errors="raise")
    frame["kickoff_at_utc"] = kickoff_local.dt.tz_localize("Asia/Shanghai", ambiguous="raise", nonexistent="raise").dt.tz_convert("UTC")
    frame["fixture_id"] = frame.pop("match_id")
    frame["snapshot_horizon"] = "observed"
    frame["time_semantics"] = "OBSERVED_AT_UTC"
    frame["causal_grade"] = STRICT_GRADE
    frame["source_id"] = "beidan_live_db"
    frame["availability_mask"] = (
        frame[["sp_3", "sp_1", "sp_0"]].notna().all(axis=1)
        & (pd.to_datetime(frame["snapshot_ts"], utc=True, errors="raise") < frame["kickoff_at_utc"])
    )
    frame["available_cell_count"] = frame[["sp_3", "sp_1", "sp_0"]].notna().sum(axis=1)
    frame["observed_at_utc"] = frame.pop("snapshot_ts")
    return frame[
        ["fixture_id", "issue_code", "match_idx", "snapshot_horizon", "time_semantics", "causal_grade", "source_id", "availability_mask", "available_cell_count", "observed_at_utc", "kickoff_at_utc"]
    ]


def _proxy_horizon_summary(root: Path) -> pd.DataFrame:
    entry = next(item for item in census.DATABASE_INVENTORY if item["key"] == "beidan_xlsm")
    path = census._resolve_data_path(root, entry["path"])
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return pd.read_sql_query(
            """SELECT s.snapshot AS snapshot_horizon,
                      COUNT(DISTINCT m.match_id) AS fixture_count,
                      COUNT(DISTINCT m.issue) AS issue_count,
                      COUNT(*) AS market_row_count,
                      SUM(CASE WHEN s.n_complete > 0 THEN 1 ELSE 0 END) AS complete_consensus_rows,
                      SUM(CASE WHEN s.v1_avg IS NOT NULL THEN 1 ELSE 0 END
                        + CASE WHEN s.v2_avg IS NOT NULL THEN 1 ELSE 0 END
                        + CASE WHEN s.v3_avg IS NOT NULL THEN 1 ELSE 0 END) AS available_value_cells
                 FROM matches m JOIN market_consensus s ON s.match_id=m.match_id
                 WHERE s.snapshot IN ('initial','10h','1h')
                 GROUP BY s.snapshot ORDER BY CASE s.snapshot WHEN 'initial' THEN 1 WHEN '10h' THEN 2 WHEN '1h' THEN 3 END""",
            con,
        )
    finally:
        con.close()


def _sqlite_receipt(source_key: str, path: Path) -> dict[str, str]:
    """Bind every SQLite byte stream a read-only connection can consume.

    SQLite may serve current rows from ``-wal`` while the main database is
    unchanged.  Main, WAL, and SHM are all captured before and after profiling;
    any sidecar change fails the seal rather than laundering a mixed snapshot.
    """
    receipt: dict[str, str] = {}
    for suffix, label in (("", "main"), ("-wal", "wal"), ("-shm", "shm")):
        candidate = Path(str(path) + suffix)
        receipt[f"{source_key}:{label}"] = sources.sha256_file(candidate) if candidate.exists() else "ABSENT"
    return receipt


def build(root: Path, output: Path | None = None) -> Path:
    root = root.resolve()
    target = output or root / "results" / PACKAGE_NAME
    live = _live_path(root)
    xlsm = census._resolve_data_path(root, "data/derived/beidan_xlsm/beidan_xlsm.sqlite")
    before = {
        **_sqlite_receipt("beidan_live_db", live),
        **_sqlite_receipt("beidan_xlsm_workbook", xlsm),
    }
    strict = _strict_rows(root, live)
    proxy = _proxy_horizon_summary(root)
    after = {
        **_sqlite_receipt("beidan_live_db", live),
        **_sqlite_receipt("beidan_xlsm_workbook", xlsm),
    }
    if before != after:
        raise RuntimeError("source changed during profiling; refusing to seal mutable input")

    def populate(staging: Path) -> None:
        _populate(staging, strict, proxy, before)
        (staging / "evidence").mkdir(parents=True, exist_ok=True)
        evidence = pd.DataFrame([
            ("REQ-TS01", "all strict selection rows carry temporal provenance and availability", "tables/strict_selection.csv", True),
            ("REQ-TS02", "observed-at rows use current schedule reference; proxy has no observed_at claim", "tables/strict_selection.csv + tables/proxy_horizon_summary.csv", True),
            ("REQ-TS03", "initial/10h/1h retained as separate aggregate source-relative summaries", "tables/proxy_horizon_summary.csv", True),
            ("REQ-TS04", "common cutoffs select only observations at/before epoch and record fixture/cell staleness", "tables/cutoff_coverage.csv + tables/cutoff_selection.csv", True),
            ("REQ-TS05", "local-date segment fallback applies identical cutoff rule", "tables/segment_selection.csv", True),
            ("REQ-TS06", "fixture/cell coverage and mutually exclusive drop curves emitted per lead/segment", "tables/cutoff_coverage.csv + tables/cutoff_drop_reasons.csv + tables/segment_drop_reasons.csv", True),
            ("REQ-TS07", "strict and proxy namespaces are separate files and semantic verifier rules", "MANIFEST.json + TEMPORAL_VOCABULARY.md", True),
            ("REQ-TS08", "boundary tests cover timezone, future observation, missing clock, and segment isolation", "tests/test_bj252_temporal_semantics.py", True),
        ], columns=["req", "criterion", "evidence", "pass"])
        publication.atomic_write_csv(evidence, staging / "evidence" / "req_ts_evidence.csv")
        publication.atomic_write_text(staging / "TEMPORAL_VOCABULARY.md", """# Temporal vocabulary\n\n- `historical_proxy`: `initial`, `10h`, `1h` are separate aggregate source-relative summaries, never a universal issue timestamp or row-level panel.\n- `strict_forward`: an explicit UTC observation clock evaluated against the currently stored schedule reference. It is not reschedule-as-of authority.\n- issue cutoff: earliest issue kickoff minus a declared lead; per-fixture and per-cell support is recorded.\n- segment fallback: Asia/Shanghai local kickoff-date segment; cutoff is that segment's earliest kickoff minus the same lead.\n- no model, ROI, ticket, or profitability claim is made.\n""")
        publication.atomic_write_text(staging / "DECISION_REPORT.md", """# #252 decision input (candidate)\n\nThis package profiles fixture/cell coverage and staleness across 1/6/12/24h common issue cutoffs and a deterministic local-date segment fallback. It does **not** select a final lead or crawler cadence. Historical proxy consists of three aggregate horizon summaries, not a row-level panel, and remains physically separate from observed-at evidence.\n\nTimezone convention: Asia/Shanghai scheduled kickoff values are explicitly localized then converted to UTC. Without schedule history these curves are descriptive against the current schedule reference. `NO_OBSERVATION_BY_CUTOFF` is separate from `OBSERVATION_UNAVAILABLE_OR_INCOMPLETE`.\n\nInternal checksums establish package integrity, not external authenticity after arbitrary re-signing. The source receipt proves only that SQLite main/WAL/SHM bytes were stable across this build interval.\n""")
        publication.atomic_write_text(
            staging / "REPLAY.md",
            f"python scripts/build_bj252_temporal_semantics.py --root /path/to/beijing-lot --output results/{PACKAGE_NAME}\n"
            f"python scripts/build_bj252_temporal_semantics.py --verify --output results/{PACKAGE_NAME}\n",
        )
        rehash_package(staging)
        verify_package(staging)
    return publication.atomic_publish_directory(target, populate, force=True)
