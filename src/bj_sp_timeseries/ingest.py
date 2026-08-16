"""Append-only ingestion from raw capture stores into the canonical schema.

Idempotency (REQ-BJ07): every write is keyed by a deterministic batch/row key
and executed with INSERT OR IGNORE inside a single transaction per batch, so
crash/restart and duplicate ingestion are no-ops.

Sources handled here:
  - beidan_live.db  (snapshots with snapshot_ts trusted receive clock)
  - 500_bjdc.sqlite live_sp_snapshots playid 34 (handicap_3way)
  - multimarket raw XML bundles (manifest + payload_sha256 + SHA256SUMS)
  - beidan_history.db (settlement only)
  - beidan_xlsm.sqlite (retrospective proxy: no exact clock, label only)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from . import OUTCOME_DOMAIN, SCHEMA_SQL, SOURCE_REGISTRY


def connect_canonical(path: str | Path, *, create: bool = True) -> sqlite3.Connection:
    """Open (and initialize) the canonical append-only SQLite store."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    if create:
        con.executescript(SCHEMA_SQL)
        con.commit()
    return con


def register_sources(con: sqlite3.Connection) -> None:
    for row in SOURCE_REGISTRY:
        con.execute(
            """INSERT OR IGNORE INTO source_registry
               (source_id, provider, endpoint, acquisition_method, terms_status,
                timezone, clock_semantics, cadence_seconds, parser_version,
                admissible_use, first_usable_at_utc, last_usable_at_utc)
               VALUES (:source_id,:provider,:endpoint,:acquisition_method,:terms_status,
                       :timezone,:clock_semantics,:cadence_seconds,:parser_version,
                       :admissible_use,:first_usable_at_utc,:last_usable_at_utc)""",
            row,
        )
    con.commit()


# ---------------------------------------------------------------------------
# beidan_live.db
# ---------------------------------------------------------------------------
def ingest_beidan_live(con: sqlite3.Connection, live_db: str | Path,
                       batch_id: str = "beidan_live_full_v1") -> dict:
    """Ingest beidan_live.db matches + snapshots into canonical tables.

    Clock binding: snapshots.snapshot_ts is the trusted receive time of the
    500.com poll (STRICT_CAUSAL). No native source time is recorded in this
    store, so observed_at_utc := received_at_utc and we record snapshot_kind
    'live_poll'. SP triplet 3/1/0 maps sp_3/sp_1/sp_0.
    """
    live_db = Path(live_db)
    src = sqlite3.connect(f"file:{live_db}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    counts = {"fixtures": 0, "observations": 0, "quotes": 0, "exclusions": 0}

    # ingestion_batch row
    con.execute(
        """INSERT OR IGNORE INTO ingestion_batch
           (batch_id, source_id, requested_at_utc, received_at_utc, raw_uri,
            raw_sha256, parser_version, row_count, status)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (batch_id, "beidan_live_500", None, None, str(live_db),
         _sha256_file(live_db), "bj_sp_timeseries/v1", None, "completed"),
    )

    # fixtures from matches
    for m in src.execute(
        "SELECT match_id, issue, match_idx, league, kickoff_ts, home, away, "
        "handicap_line, fid FROM matches ORDER BY issue, match_idx"
    ):
        con.execute(
            """INSERT OR IGNORE INTO fixture
               (fixture_id, issue_code, match_idx, source_match_key, competition,
                home, away, kickoff_at_utc, native_handicap_line, identity_status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (m["match_id"], m["issue"], m["match_idx"], m["fid"], m["league"],
             m["home"], m["away"], _norm_ts(m["kickoff_ts"]), m["handicap_line"],
             "canonical"),
        )
        counts["fixtures"] += 1

    # snapshots -> market_observation + market_quote
    for s in src.execute(
        """SELECT id, match_id, snapshot_ts, sp_3, sp_1, sp_0,
                  vol_pct_3, vol_pct_1, vol_pct_0, pool_total, eu_h, eu_d, eu_a, source
           FROM snapshots ORDER BY match_id, snapshot_ts"""
    ):
        obs_id = f"beidan_live_{s['id']}"
        ts = _norm_ts(s["snapshot_ts"])
        # sale_status is not recorded in beidan_live; NULL is explicit unknown.
        con.execute(
            """INSERT OR IGNORE INTO market_observation
               (observation_id, fixture_id, source_id, market_type, handicap_line,
                observed_at_utc, received_at_utc, snapshot_kind, batch_id, sale_status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (obs_id, s["match_id"], "beidan_live_500", "handicap_3way", None,
             ts, ts, "live_poll", batch_id, None),
        )
        counts["observations"] += 1
        sp = {"3": s["sp_3"], "1": s["sp_1"], "0": s["sp_0"]}
        for code in OUTCOME_DOMAIN:
            val = sp[code]
            qs = "present" if val is not None and val > 0 else "missing"
            con.execute(
                """INSERT OR IGNORE INTO market_quote
                   (quote_id, observation_id, outcome_code, decimal_odds, quote_status)
                   VALUES (?,?,?,?,?)""",
                (f"{obs_id}_{code}", obs_id, code, val, qs),
            )
            counts["quotes"] += 1

    con.commit()
    src.close()
    return counts


# ---------------------------------------------------------------------------
# 500_bjdc.sqlite live_sp_snapshots (playid 34)
# ---------------------------------------------------------------------------
def ingest_500_xml34(con: sqlite3.Connection, bjdc_db: str | Path,
                     batch_id: str = "500_xml34_full_v1") -> dict:
    """Ingest 500_bjdc.sqlite live_sp_snapshots playid=34.

    Clock binding: fetched_at is the trusted receive time; source_updatetime is
    the native source update time (STRICT_CAUSAL). handicap_line is per
    observation (line state preserved, REQ-BJ04). sale status column absent in
    live_sp_snapshots -> NULL explicit unknown (richer sale_status lives in
    live_market_sp_snapshots).
    """
    bjdc_db = Path(bjdc_db)
    src = sqlite3.connect(f"file:{bjdc_db}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row

    counts = {"fixtures": 0, "observations": 0, "quotes": 0, "exclusions": 0}

    con.execute(
        """INSERT OR IGNORE INTO ingestion_batch
           (batch_id, source_id, requested_at_utc, received_at_utc, raw_uri,
            raw_sha256, parser_version, row_count, status)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (batch_id, "bjdc_500_xml_34", None, None, str(bjdc_db),
         _sha256_file(bjdc_db), "bj_sp_timeseries/v1", None, "completed"),
    )

    # fixtures are per (issue, row_idx); the 500 XML does not expose a stable
    # match key, so fixture_id := issue_rowidx with kickoff unknown here.
    seen_fixtures: set[str] = set()
    for s in src.execute(
        """SELECT issue, playid, fetched_at, source_updatetime, row_idx,
                  home, away, league, handicap_line, sp_home, sp_draw, sp_away
           FROM live_sp_snapshots WHERE playid=34
           ORDER BY issue, row_idx, fetched_at"""
    ):
        fid = f"{s['issue']}_{int(s['row_idx']):03d}"
        if fid not in seen_fixtures:
            seen_fixtures.add(fid)
            con.execute(
                """INSERT OR IGNORE INTO fixture
                   (fixture_id, issue_code, match_idx, source_match_key, competition,
                    home, away, kickoff_at_utc, native_handicap_line, identity_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (fid, s["issue"], int(s["row_idx"]), None, s["league"],
                 s["home"], s["away"], None, s["handicap_line"], "canonical"),
            )
            counts["fixtures"] += 1

        recv = _norm_ts(s["fetched_at"])
        obs = _norm_ts(s["source_updatetime"])
        obs_id = f"xml34_{s['issue']}_{s['row_idx']}_{_ts_key(recv)}_{_ts_key(obs)}"
        con.execute(
            """INSERT OR IGNORE INTO market_observation
               (observation_id, fixture_id, source_id, market_type, handicap_line,
                observed_at_utc, received_at_utc, snapshot_kind, batch_id, sale_status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (obs_id, fid, "bjdc_500_xml_34", "handicap_3way", s["handicap_line"],
             obs, recv, "live_poll", batch_id, None),
        )
        counts["observations"] += 1
        sp = {"3": s["sp_home"], "1": s["sp_draw"], "0": s["sp_away"]}
        for code in OUTCOME_DOMAIN:
            val = sp[code]
            qs = "present" if val is not None and val > 0 else "missing"
            con.execute(
                """INSERT OR IGNORE INTO market_quote
                   (quote_id, observation_id, outcome_code, decimal_odds, quote_status)
                   VALUES (?,?,?,?,?)""",
                (f"{obs_id}_{code}", obs_id, code, val, qs),
            )
            counts["quotes"] += 1

    con.commit()
    src.close()
    return counts


# ---------------------------------------------------------------------------
# multimarket raw XML bundles (manifest registry)
# ---------------------------------------------------------------------------
def ingest_multimarket_bundles(con: sqlite3.Connection,
                               bundles_root: str | Path,
                               batch_id: str = "multimarket_bundles_v1") -> dict:
    """Register raw XML capture bundles from results/data_collection.

    These carry fetched_at_utc (trusted receive), source_updated_at_hkt (native
    source clock), payload_sha256 and SHA256SUMS — the raw capture hash
    evidence for prospective SP (REQ-BJ01 source binding). We register the
    batch rows here; the raw payloads are retained in results/ and hashed.
    """
    root = Path(bundles_root)
    counts = {"batches": 0, "exclusions": 0}
    if not root.exists():
        return counts
    for issue_dir in sorted(root.iterdir()):
        if not issue_dir.is_dir():
            continue
        for bundle_dir in sorted(issue_dir.iterdir()):
            if not bundle_dir.is_dir():
                continue
            manifest_path = bundle_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            bid = manifest.get("batch_id") or bundle_dir.name
            raw_sha = manifest.get("payload_sha256")
            if raw_sha is None:
                # fall back to SHA256SUMS file content hash
                sums = bundle_dir / "SHA256SUMS"
                if sums.exists():
                    raw_sha = hashlib.sha256(sums.read_bytes()).hexdigest()
            con.execute(
                """INSERT OR IGNORE INTO ingestion_batch
                   (batch_id, source_id, requested_at_utc, received_at_utc, raw_uri,
                    raw_sha256, parser_version, row_count, status)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (bid, "bjdc_500_xml_34", None,
                 _norm_ts(manifest.get("fetched_at_utc")),
                 manifest.get("source_url"),
                 raw_sha,
                 manifest.get("schema_version") or "multimarket_sp_capture_batch_v1",
                 manifest.get("outcome_rows"), "completed"),
            )
            counts["batches"] += 1
    con.commit()
    return counts


# ---------------------------------------------------------------------------
# Settlement-only + retrospective proxy ledgers
# ---------------------------------------------------------------------------
def ingest_settlement_history(con: sqlite3.Connection, history_db: str | Path,
                              batch_id: str = "beidan_history_v1") -> dict:
    """Register beidan_history.db historical settlement rows in settlement table
    (SETTLEMENT_ONLY — never an inference-time observation)."""
    history_db = Path(history_db)
    src = sqlite3.connect(f"file:{history_db}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    counts = {"settlements": 0, "exclusions": 0}
    con.execute(
        """INSERT OR IGNORE INTO ingestion_batch
           (batch_id, source_id, requested_at_utc, received_at_utc, raw_uri,
            raw_sha256, parser_version, row_count, status)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (batch_id, "beidan_history", None, None, str(history_db),
         _sha256_file(history_db), "bj_sp_timeseries/v1", None, "completed"),
    )
    for r in src.execute(
        """SELECT id, issue, match_idx, kickoff_ts, home, away, handicap_line,
                  result_code, winning_sp FROM historical_matches
           ORDER BY issue, match_idx"""
    ):
        fid = f"{r['issue']}_{int(r['match_idx']):03d}"
        con.execute(
            """INSERT OR IGNORE INTO fixture
               (fixture_id, issue_code, match_idx, source_match_key, competition,
                home, away, kickoff_at_utc, native_handicap_line, identity_status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (fid, r["issue"], int(r["match_idx"]), None, None,
             r["home"], r["away"], _norm_ts(r["kickoff_ts"]), r["handicap_line"],
             "settlement_proxy"),
        )
        con.execute(
            """INSERT OR IGNORE INTO settlement
               (fixture_id, issue_code, result_code, winning_sp, settled_at_utc, source_id)
               VALUES (?,?,?,?,?,?)""",
            (fid, r["issue"], r["result_code"], r["winning_sp"], None,
             "beidan_history"),
        )
        counts["settlements"] += 1
    con.commit()
    src.close()
    return counts


def log_exclusion(con: sqlite3.Connection, *, fixture_id, source_id, issue_code,
                  season_year, native_handicap_line, reason_code, detail,
                  raw_count=1, batch_id=None) -> None:
    """Append an exclusion ledger row (explicit non-causal rows, REQ-BJ02/06)."""
    eid = hashlib.sha1(
        f"{fixture_id}|{source_id}|{reason_code}|{detail}".encode()
    ).hexdigest()[:24]
    con.execute(
        """INSERT OR IGNORE INTO exclusion_ledger
           (exclusion_id, fixture_id, source_id, issue_code, season_year,
            native_handicap_line, reason_code, detail, raw_count, batch_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (eid, fixture_id, source_id, issue_code, season_year,
         native_handicap_line, reason_code, detail, raw_count, batch_id),
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _norm_ts(ts) -> Optional[str]:
    """Normalize heterogeneous timestamp strings to UTC ISO-8601 with Z."""
    if ts is None:
        return None
    s = str(ts).strip()
    if not s:
        return None
    # '2026-05-02T00:57:41Z' / '2026-07-16T13:44:01.000000+00:00' / '2026-07-14 03:13:20'
    s = s.replace(" ", "T")
    if s.endswith("Z") or "+00:00" in s or s.endswith("+0000"):
        if s.endswith("+0000"):
            s = s[:-5] + "Z"
        elif s.endswith("+00:00"):
            s = s[:-6] + "Z"
        # trim microseconds
        if "." in s:
            head, _, tail = s.partition(".")
            tail = tail[:6].rstrip("0").rstrip(".")
            s = f"{head}.{tail}Z" if tail else f"{head}Z"
        return s
    # naive local (Asia/Shanghai source) -> treat as HKT and convert to UTC
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(s)
        hkt = timezone(timedelta(hours=8))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=hkt)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        return s


def _ts_key(ts: Optional[str]) -> str:
    if ts is None:
        return "na"
    return ts.replace("-", "").replace(":", "").replace("T", "").replace("Z", "").replace(".", "")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
