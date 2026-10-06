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
    parser.add_argument("--label-version", default=None,
                        help="immutable label version for this publication; defaults to today's date")
    parser.add_argument("--list-versions", action="store_true",
                        help="list published label versions and exit")
    args = parser.parse_args(argv)

    frozen = catalog.root_path("frozen")
    entry = catalog.catalog_entry("settlement")
    version_dir = catalog.dataset_path("settlement", entry["version"])
    base = version_dir / "derived" / "spf_labels"

    if args.list_versions:
        current = backfill.read_current(base)
        for name in backfill.list_versions(base):
            marker = "  * " if current and current.get("label_version") == name else "    "
            print(marker + name)
        return 0

    label_version = args.label_version or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cross = backfill.load_cross_source(frozen / args.cross)
    rows = observation_rows(version_dir)
    derived, receipt = backfill.backfill_spf(rows, cross)
    receipt["generated_at"] = args.generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    table = pa.Table.from_pylist([
        {"issue": r["issue"], "slot": r["slot"],
         "handicap": r.get("handicap_backfilled"),
         "handicap_source": r.get("handicap_source"),
         "expected_option": r.get("expected_option_backfilled")}
        for r in derived
    ])
    # Each publication is archived under its own immutable label version; a
    # finalized cutoff is never rewritten in place.
    record = backfill.publish_version(base, label_version, table, receipt)

    c = receipt["counts"]; x = receipt["cross_check"]
    resolved = c["handicap_from_archive"] + c["handicap_from_cross_source"]
    print(f"label version       : {record['label_version']} ({record['status']})")
    print(f"spf rows            : {c['total_spf']:,}")
    print(f"  handicap from archive : {c['handicap_from_archive']:,}")
    print(f"  handicap from cross   : {c['handicap_from_cross_source']:,}")
    print(f"  unresolved            : {c['unresolved']:,}")
    print(f"  resolved              : {resolved:,} ({100*resolved/c['total_spf']:.1f}%)")
    print(f"cross-check contradictions: {x['contradictions']} / {x['compared']:,}")
    print(f"artifact            : {record['artifact']['path']}")
    print(f"versions            : {', '.join(record['versions'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
