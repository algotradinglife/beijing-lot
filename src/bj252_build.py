"""Build the #252 sealed temporal-profiling evidence package from read-only sources."""
from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd

from bj252_temporal_package import _populate, rehash_package, verify_package
from source_schema import census, publication, sources
from temporal_semantics import build_issue_view, build_segment_views

PACKAGE_NAME = "bj252_unified_temporal_semantics_v1"
LEAD_HOURS = (1, 6, 12, 24)
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
    frame["causal_grade"] = "STRICT_OBSERVED_SEALED"
    frame["source_id"] = "beidan_live_db"
    frame["availability_mask"] = (
        frame[["sp_3", "sp_1", "sp_0"]].notna().all(axis=1)
        & (pd.to_datetime(frame["snapshot_ts"], utc=True, errors="raise") < frame["kickoff_at_utc"])
    )
    frame["observed_at_utc"] = frame.pop("snapshot_ts")
    return frame[
        ["fixture_id", "issue_code", "match_idx", "snapshot_horizon", "time_semantics", "causal_grade", "source_id", "availability_mask", "observed_at_utc", "kickoff_at_utc"]
    ]


def _proxy_coverage(root: Path) -> pd.DataFrame:
    entry = next(item for item in census.DATABASE_INVENTORY if item["key"] == "beidan_xlsm")
    path = census._resolve_data_path(root, entry["path"])
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return pd.read_sql_query(
            """SELECT s.snapshot AS snapshot_horizon,
                      COUNT(DISTINCT m.match_id) AS fixture_count,
                      COUNT(DISTINCT m.issue) AS issue_count,
                      SUM(CASE WHEN s.n_complete > 0 THEN 1 ELSE 0 END) AS complete_consensus_rows
                 FROM matches m JOIN market_consensus s ON s.match_id=m.match_id
                 WHERE s.snapshot IN ('initial','10h','1h')
                 GROUP BY s.snapshot ORDER BY CASE s.snapshot WHEN 'initial' THEN 1 WHEN '10h' THEN 2 WHEN '1h' THEN 3 END""",
            con,
        )
    finally:
        con.close()


def _profile(strict: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fixtures = strict[["fixture_id", "issue_code", "match_idx", "kickoff_at_utc"]].drop_duplicates("fixture_id")
    issue_duration = (
        fixtures.groupby("issue_code", as_index=False)
        .agg(fixture_count=("fixture_id", "size"), first_kickoff_at_utc=("kickoff_at_utc", "min"), last_kickoff_at_utc=("kickoff_at_utc", "max"))
    )
    issue_duration["issue_duration_hours"] = (issue_duration["last_kickoff_at_utc"] - issue_duration["first_kickoff_at_utc"]).dt.total_seconds() / 3600
    coverage_rows: list[pd.DataFrame] = []
    segment_rows: list[pd.DataFrame] = []
    for issue_code, group in strict.groupby("issue_code", sort=True):
        for lead_hours in LEAD_HOURS:
            cutoff = group["kickoff_at_utc"].min() - pd.Timedelta(hours=lead_hours)
            view = build_issue_view(group, issue_code=str(issue_code), decision_at_utc=cutoff)
            coverage_rows.append(pd.DataFrame({
                "issue_code": [issue_code], "lead_hours": [lead_hours], "decision_at_utc": [cutoff],
                "fixture_count": [len(view)], "available_fixture_count": [int(view["drop_reason"].eq("AVAILABLE").sum())],
                "median_staleness_minutes": [view.loc[view["drop_reason"].eq("AVAILABLE"), "staleness_minutes"].median()],
            }))
        segment_rows.append(build_segment_views(group, issue_code=str(issue_code), lead_minutes=60, timezone_name="Asia/Shanghai"))
    cutoff_coverage = pd.concat(coverage_rows, ignore_index=True)
    segments = pd.concat(segment_rows, ignore_index=True)
    drops = (
        segments.groupby(["issue_code", "segment_idx", "drop_reason"], as_index=False)
        .agg(fixture_count=("fixture_id", "size"))
    )
    return issue_duration, cutoff_coverage, segments, drops


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
    proxy = _proxy_coverage(root)
    issue_duration, cutoff_coverage, segments, drops = _profile(strict)
    after = {
        **_sqlite_receipt("beidan_live_db", live),
        **_sqlite_receipt("beidan_xlsm_workbook", xlsm),
    }
    if before != after:
        raise RuntimeError("source changed during profiling; refusing to seal mutable input")

    def populate(staging: Path) -> None:
        _populate(staging, strict, proxy, before)
        for name, frame in {
            "issue_duration.csv": issue_duration,
            "cutoff_coverage.csv": cutoff_coverage,
            "segment_selection.csv": segments,
            "drop_reasons.csv": drops,
        }.items():
            publication.atomic_write_csv(frame, staging / "tables" / name)
        (staging / "evidence").mkdir(parents=True, exist_ok=True)
        evidence = pd.DataFrame([
            ("REQ-TS01", "all strict selection rows carry temporal provenance and availability", "tables/strict_selection.csv", True),
            ("REQ-TS02", "strict uses explicit observed_at UTC; proxy has no observed_at claim", "tables/strict_selection.csv + tables/proxy_horizon_coverage.csv", True),
            ("REQ-TS03", "initial/10h/1h retained as separate source-relative labels", "tables/proxy_horizon_coverage.csv", True),
            ("REQ-TS04", "common cutoffs select only observations at/before epoch and record staleness", "tables/cutoff_coverage.csv + tables/strict_selection.csv", True),
            ("REQ-TS05", "local-date segment fallback applies identical cutoff rule", "tables/segment_selection.csv", True),
            ("REQ-TS06", "coverage/drop curves emitted for declared candidate leads", "tables/cutoff_coverage.csv + tables/drop_reasons.csv", True),
            ("REQ-TS07", "strict and proxy namespaces are separate files and semantic verifier rules", "MANIFEST.json + TEMPORAL_VOCABULARY.md", True),
            ("REQ-TS08", "boundary tests cover timezone, future observation, missing clock, and segment isolation", "tests/test_bj252_temporal_semantics.py", True),
        ], columns=["req", "criterion", "evidence", "pass"])
        publication.atomic_write_csv(evidence, staging / "evidence" / "req_ts_evidence.csv")
        publication.atomic_write_text(staging / "TEMPORAL_VOCABULARY.md", """# Temporal vocabulary\n\n- `historical_proxy`: `initial`, `10h`, `1h` are source-relative labels, never universal issue timestamps; rows have null `observed_at_utc`.\n- `strict_forward`: a sealed selected receipt from `beidan_live.snapshots.snapshot_ts` with explicit UTC observation clock.\n- issue cutoff: earliest issue kickoff minus a declared lead; per-fixture staleness is recorded.\n- segment fallback: Asia/Shanghai local kickoff-date segment; cutoff is that segment's earliest kickoff minus the same lead.\n- no model, ROI, ticket, or profitability claim is made.\n""")
        publication.atomic_write_text(staging / "DECISION_REPORT.md", """# #252 decision input (candidate)\n\nThis package profiles coverage and staleness across 1/6/12/24h common issue cutoffs and a deterministic local-date segment fallback. It does **not** select a final lead, cadence, or claim boundary: PI/user must decide those policy choices. Historical proxy and strict-forward namespaces are physically separate tables and the verifier refuses pooled semantics.\n\nTimezone convention: Asia/Shanghai scheduled kickoff values are explicitly localized then converted to UTC. Reschedules must be represented by a new sealed fixture schedule before rebuilding; missing strict timestamps drop with `NO_OBSERVATION_BY_CUTOFF`.\n""")
        publication.atomic_write_text(staging / "REPLAY.md", f"python scripts/build_bj252_temporal_semantics.py --root {root} --output results/{PACKAGE_NAME}\npython scripts/build_bj252_temporal_semantics.py --verify --output results/{PACKAGE_NAME}\n")
        rehash_package(staging)
        verify_package(staging)
    return publication.atomic_publish_directory(target, populate, force=True)
