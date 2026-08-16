"""Immutable Parquet snapshot export + manifest + SHA256SUMS.

Exports the canonical tables to partitioned Parquet (pyarrow) under a
results/ directory, plus a machine-readable manifest and SHA256SUMS so the
package is replayable and hash-bound (REQ-BJ07/REQ-S10-style binding).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd

EXPORT_TABLES = (
    "source_registry",
    "ingestion_batch",
    "fixture",
    "market_observation",
    "market_quote",
    "decision_epoch",
    "as_of_selection",
    "probability_estimate",
    "settlement",
    "exclusion_ledger",
)


def export_parquet(con: sqlite3.Connection, out_dir: str | Path) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tables = out / "tables"
    tables.mkdir(parents=True, exist_ok=True)

    written = {}
    for name in EXPORT_TABLES:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {name}", con)
        except Exception as exc:
            # table may be absent in a minimal build
            written[name] = {"rows": 0, "file": None, "error": str(exc)}
            continue
        fp = tables / f"{name}.parquet"
        df.to_parquet(fp, index=False)
        written[name] = {"rows": len(df), "file": fp.name}

    # manifest
    manifest = {
        "package": "bj235_bj_sp_timeseries_v1",
        "contract": "BJ-UNIFIED-BJ-SP-TIMESERIES-001",
        "tables": written,
        "asof_rule": "asof_latest_complete_pre_kickoff_v1",
        "exported_at_utc": _now_utc(),
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    # SHA256SUMS for every file under out_dir
    sums = {}
    for fp in sorted(out.rglob("*")):
        if fp.is_file():
            sums[str(fp.relative_to(out))] = _sha256(fp)
    (out / "SHA256SUMS.json").write_text(
        json.dumps(sums, indent=2, sort_keys=True, ensure_ascii=False)
    )
    return {"files": len(sums), "tables": written}


def _sha256(fp: Path) -> str:
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
