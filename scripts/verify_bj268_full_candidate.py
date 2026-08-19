#!/usr/bin/env python3
"""Verify #268's complete SQLite/Parquet candidate and #236 preservation."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_parts(root: Path, table: str) -> pd.DataFrame:
    paths = sorted((root / table).glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"no {table} parts under {root}")
    return pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sqlite", type=Path, required=True)
    parser.add_argument("--parquet-output", type=Path, required=True)
    parser.add_argument("--accepted-parquet", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads((args.parquet_output / "MANIFEST.json").read_text(encoding="utf-8"))
    bad_hashes = [
        relative for relative, expected in manifest["parts"].items()
        if sha256(args.parquet_output / relative) != expected
    ]
    if bad_hashes:
        raise AssertionError(f"Parquet part hash mismatch: {bad_hashes[:3]}")

    with sqlite3.connect(args.candidate_sqlite) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {
            "issues": connection.execute("SELECT COUNT(DISTINCT issue_code) FROM inventory").fetchone()[0],
            "fixtures": connection.execute("SELECT COUNT(*) FROM inventory").fetchone()[0],
            "raw_quotes": connection.execute("SELECT COUNT(*) FROM raw_quote_observations").fetchone()[0],
            "resolved_quotes": connection.execute("SELECT COUNT(*) FROM resolved_quotes").fetchone()[0],
            "market_snapshots": connection.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0],
        }
        coverage = pd.read_sql_query(
            """
            WITH valid AS (
                SELECT DISTINCT m.issue, m.match_idx
                FROM matches AS m JOIN market_snapshots AS s ON s.match_id=m.match_id
                WHERE s.v1>1 AND s.v2>1 AND s.v3>1
            )
            SELECT i.reconciled_source, COUNT(*) AS inventory_fixtures,
                   SUM(v.issue IS NOT NULL) AS covered_fixtures,
                   SUM(v.issue IS NULL) AS unavailable_fixtures
            FROM inventory AS i LEFT JOIN valid AS v
              ON v.issue=i.issue_code AND v.match_idx=i.match_idx
            GROUP BY i.reconciled_source ORDER BY i.reconciled_source
            """,
            connection,
        )
        forbidden = {
            str(row[1]).lower()
            for table in ("inventory", "matches", "market_snapshots", "resolved_quotes")
            for row in connection.execute(f"PRAGMA table_info({table})")
            if any(token in str(row[1]).lower() for token in ("score", "result", "settlement", "winning", "payout"))
        }
    if integrity != "ok" or counts["issues"] != 808 or counts["fixtures"] != 213_263:
        raise AssertionError(f"candidate SQLite invariant failed: {integrity=}, {counts=}")
    if forbidden:
        raise AssertionError(f"forbidden outcome-derived columns: {sorted(forbidden)}")

    inventory = pd.read_parquet(args.inventory, columns=["issue_code", "match_idx", "reconciled_source"])
    lane = inventory.assign(
        canonical_fixture_key=lambda frame: "bjslot:" + frame.issue_code.astype(str)
        + ":" + frame.match_idx.astype(int).astype(str).str.zfill(3)
    ).set_index("canonical_fixture_key").reconciled_source
    probabilities = read_parts(args.parquet_output, "probabilities")
    triplets = probabilities.groupby(["canonical_fixture_key", "snapshot_kind"], sort=False).agg(
        cells=("outcome_code", "nunique"), probability_sum=("probability", "sum")
    )
    if not triplets.cells.eq(3).all() or not triplets.probability_sum.sub(1.0).abs().le(1e-10).all():
        raise AssertionError("probability triplet invariant failed")
    probabilities["lane"] = probabilities.canonical_fixture_key.map(lane)
    lane_rows = probabilities.groupby("lane").agg(
        probability_rows=("probability", "size"),
        covered_fixtures=("canonical_fixture_key", "nunique"),
        covered_issues=("issue_code", "nunique"),
    ).reset_index()

    comparison_columns = [
        "canonical_fixture_key", "snapshot_kind", "outcome_code", "probability",
        "n_available_books", "availability_mask", "aggregation_grade", "source_match_ids",
        "translation_status", "translation_availability_mask", "required_additional_input",
    ]
    accepted = read_parts(args.accepted_parquet, "probabilities")[comparison_columns]
    candidate_accepted = probabilities.loc[
        probabilities.lane.eq("ACCEPTED_236"), comparison_columns
    ]
    order = comparison_columns[:3]
    accepted = accepted.sort_values(order, kind="stable").reset_index(drop=True)
    candidate_accepted = candidate_accepted.sort_values(order, kind="stable").reset_index(drop=True)
    assert_frame_equal(accepted, candidate_accepted, check_exact=True, check_dtype=False)

    result = {
        "verdict": "PASS",
        "sqlite_integrity": integrity,
        "sqlite_counts": counts,
        "parquet_manifest_counts": {
            "probability_rows": manifest["probability_rows"],
            "matched_fixture_count": manifest["matched_fixture_count"],
            "trace_rows": manifest["trace_rows"],
            "translation_rows": manifest["translation_rows"],
            "exclusion_rows": manifest["exclusion_rows"],
        },
        "coverage_by_lane": coverage.to_dict("records"),
        "probability_rows_by_lane": lane_rows.to_dict("records"),
        "probability_triplet_count": len(triplets),
        "accepted_236_exact_parity": True,
        "parquet_hash_mismatches": 0,
        "forbidden_outcome_columns": [],
        "candidate_sqlite_sha256": sha256(args.candidate_sqlite),
        "parquet_manifest_sha256": sha256(args.parquet_output / "MANIFEST.json"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
