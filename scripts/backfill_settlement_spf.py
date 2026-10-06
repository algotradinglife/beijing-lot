#!/usr/bin/env python3
"""Derive SPF labels for the settlement dataset using the cross-source handicap.

Reads the settlement observation table, resolves the let-ball from the archive
when it is rendered and from the independent 500.com settlement table otherwise,
derives ``expected_option``, cross-checks it against the archive result, and
publishes a Parquet table plus a receipt. Nothing is inferred from the archive's
own rendering, so a fixture with no handicap in either source stays unresolved.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "packages/beidan/inst/python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import pyarrow as pa  # noqa: E402

from beidan_backend import catalog, settlement_backfill as backfill  # noqa: E402

DEFAULT_CROSS = "backfill/settlement_500/handicap_line.csv"


def observation_rows(version_dir: Path) -> list[dict]:
    import pyarrow.dataset as ds

    table = ds.dataset(version_dir / "tables/observation", format="parquet",
                       partitioning="hive").to_table()
    rows = []
    for record in table.to_pylist():
        payload = json.loads(record["payload_json"]) if record.get("payload_json") else {}
        rows.append({
            "issue": record["issue"], "slot": record["slot"], "play": record["play"],
            "score": record["score"], "expected_option": record["expected_option"],
            "handicap": payload.get("handicap"),
            "archive_result_raw": payload.get("archive_result_raw"),
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross", default=DEFAULT_CROSS, help="cross-source CSV, relative to the frozen root")
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args(argv)

    frozen = catalog.root_path("frozen")
    entry = catalog.catalog_entry("settlement")
    version_dir = catalog.dataset_path("settlement", entry["version"])

    cross = backfill.load_cross_source(frozen / args.cross)
    rows = observation_rows(version_dir)
    derived, receipt = backfill.backfill_spf(rows, cross)

    out_dir = frozen / "datasets/settlement/versions" / entry["version"] / "derived"
    out_dir.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([
        {"issue": r["issue"], "slot": r["slot"],
         "handicap": r.get("handicap_backfilled"),
         "handicap_source": r.get("handicap_source"),
         "expected_option": r.get("expected_option_backfilled")}
        for r in derived
    ])
    parquet_path = out_dir / "spf_labels.parquet"
    # Atomic publish: an in-place overwrite on this CIFS mount produced a
    # truncated, unreadable file, so the writer verifies a temp file first.
    receipt["output"] = backfill.write_parquet_atomically(table, parquet_path)
    receipt["generated_at"] = args.generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    backfill.write_json_atomically(receipt, out_dir / "spf_labels.receipt.json")

    c = receipt["counts"]; x = receipt["cross_check"]
    resolved = c["handicap_from_archive"] + c["handicap_from_cross_source"]
    print(f"spf rows            : {c['total_spf']:,}")
    print(f"  handicap from archive : {c['handicap_from_archive']:,}")
    print(f"  handicap from cross   : {c['handicap_from_cross_source']:,}")
    print(f"  unresolved            : {c['unresolved']:,}")
    print(f"  resolved              : {resolved:,} ({100*resolved/c['total_spf']:.1f}%)")
    print(f"cross-check contradictions: {x['contradictions']} / {x['compared']:,}")
    print(f"output              : {parquet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
