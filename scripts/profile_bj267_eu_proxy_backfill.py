#!/usr/bin/env python3
"""Build the #267 denominator and probe missing historical Nowscore/Titan data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eu_proxy_backfill import (  # noqa: E402
    InventoryPaths,
    ProbeClient,
    StagedProbeClient,
    build_inventory,
    inventory_summary,
    probe_issue,
)
from src.source_schema import publication  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_digests(paths: InventoryPaths) -> dict[str, str]:
    return {
        name: sha256_file(path.expanduser().resolve())
        for name, path in asdict(paths).items()
    }


def issue_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    return (
        frame.groupby("issue_code", sort=False)
        .agg(
            expected_fixture_count=("match_idx", "size"),
            accepted_236_fixture_count=("base_236", "sum"),
            extension_fixture_count=("extension_2026", "sum"),
            history_fixture_count=("history", "sum"),
            live_fixture_count=("live", "sum"),
            unresolved_fixture_count=(
                "proxy_status",
                lambda values: values.eq("UNRESOLVED_SOURCE_RECOVERY").sum(),
            ),
        )
        .reset_index()
    )


def extension_profile(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{path.expanduser().resolve()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        columns = {
            table: sorted(row[1] for row in connection.execute(f'PRAGMA table_info("{table}")'))
            for table in ("matches", "market_snapshots", "source_meta")
        }
        required = {
            "matches": {
                "issue",
                "match_idx",
                "provider_match_id",
                "handicap_line",
                "handicap_line_norm",
                "handicap_norm_source",
            },
            "market_snapshots": {"match_id", "market", "bookmaker", "snapshot", "v1", "v2", "v3"},
            "source_meta": {"key", "value"},
        }
        missing = {
            table: sorted(expected - set(columns[table])) for table, expected in required.items()
        }
        counts = pd.read_sql_query(
            """
            SELECT market, snapshot,
                   COUNT(*) AS raw_rows,
                   SUM(v1 IS NOT NULL AND v2 IS NOT NULL AND v3 IS NOT NULL) AS complete_rows
            FROM market_snapshots
            WHERE market='euro_1x2' AND snapshot IN ('initial','10h','1h')
            GROUP BY market, snapshot
            ORDER BY CASE snapshot WHEN 'initial' THEN 1 WHEN '10h' THEN 2 ELSE 3 END
            """,
            connection,
        )
        issue_count, fixture_count = connection.execute(
            "SELECT COUNT(DISTINCT issue), COUNT(*) FROM matches WHERE issue IS NOT NULL"
        ).fetchone()
    finally:
        connection.close()
    return {
        "issue_count": int(issue_count),
        "fixture_count": int(fixture_count),
        "required_columns_missing": missing,
        "schema_compatible": not any(missing.values()),
        "horizon_counts": counts.to_dict("records"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument(
        "--staging-root",
        type=Path,
        required=True,
        help="New isolated namespace; accepted source/canonical paths are rejected.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/bj267_eu_proxy_backfill_poc_v1"),
    )
    parser.add_argument("--issues", nargs="*", help="Optional issue subset; default is all unresolved issues.")
    parser.add_argument("--titan-samples-per-issue", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Replay from immutable staged raw payloads without network I/O.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_root = args.data_root.expanduser().resolve()
    staging_root = args.staging_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    paths = InventoryPaths(
        base_proxy=data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite",
        extension_2026=data_root / "derived/beidan_xlsm/beidan_nowscore_2026.sqlite",
        history=data_root / "beidan_history.db",
        live=data_root / "beidan_live.db",
    )
    protected = {path.expanduser().resolve() for path in asdict(paths).values()}
    if staging_root in protected or any(path == staging_root or staging_root in path.parents for path in protected):
        raise SystemExit("staging root overlaps a protected source path")
    staging_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    before = source_digests(paths)
    inventory = build_inventory(paths)
    facts = inventory_summary(inventory)
    per_issue = issue_inventory(inventory)
    unresolved = per_issue.loc[per_issue.unresolved_fixture_count.gt(0)].copy()
    selected = list(args.issues or unresolved.issue_code.tolist())
    invalid = sorted(set(selected) - set(unresolved.issue_code))
    if invalid:
        raise SystemExit(f"requested issues are not unresolved: {invalid}")

    publication.atomic_write_parquet(inventory, staging_root / "known_issue_fixture_inventory.parquet")
    publication.atomic_write_csv(per_issue, output_root / "ISSUE_INVENTORY.csv")
    publication.atomic_write_csv(unresolved, output_root / "UNRESOLVED_ISSUES.csv")

    client = StagedProbeClient(staging_root) if args.replay else ProbeClient(timeout=args.timeout)
    probe_results: list[dict[str, object]] = []
    receipt_rows: list[dict[str, object]] = []
    source_rows: list[dict[str, object]] = []
    titan_rows: list[dict[str, object]] = []
    for index, issue_code in enumerate(selected, start=1):
        result, receipts, source, titan = probe_issue(
            client,
            issue_code,
            inventory,
            staging_root,
            titan_samples=args.titan_samples_per_issue,
        )
        probe_results.append(asdict(result))
        receipt_rows.extend(receipts)
        source_rows.extend(source)
        titan_rows.extend(titan)
        print(
            f"[{index}/{len(selected)}] issue={issue_code} source={result.source_fixture_count} "
            f"local={result.local_candidate_fixture_count} "
            f"local_only={result.local_only_slot_count} "
            f"source_only={result.source_only_slot_count} "
            f"titan={result.sampled_titan_success_count}/{result.sampled_titan_match_count}",
            flush=True,
        )

    probes = pd.DataFrame(probe_results)
    receipts_frame = pd.DataFrame(receipt_rows)
    source_frame = pd.DataFrame(source_rows)
    titan_frame = pd.DataFrame(titan_rows)
    selected_inventory = inventory.loc[inventory.issue_code.isin(selected)].copy()
    source_keys = source_frame[["issue_code", "match_idx"]].drop_duplicates()
    local_only = selected_inventory.merge(
        source_keys.assign(source_page_present=True),
        on=["issue_code", "match_idx"],
        how="left",
        validate="1:1",
    )
    local_only = local_only.loc[local_only.source_page_present.isna()].drop(
        columns="source_page_present"
    )
    local_only["diagnosis"] = "LOCAL_CACHE_NOT_IN_AUTHORITATIVE_ISSUE_PAGE"

    accepted = inventory.loc[inventory.base_236].copy()
    accepted["reconciled_source"] = "ACCEPTED_236"
    extension_rows = inventory.loc[~inventory.base_236 & inventory.extension_2026].copy()
    extension_rows["reconciled_source"] = "AVAILABLE_EXTENSION"
    recovered = source_frame.rename(
        columns={"present_in_local_candidate": "was_present_in_local_candidate"}
    ).copy()
    recovered["reconciled_source"] = "NOWSCORE_ISSUE_PAGE"
    reconciled = pd.concat(
        [
            accepted[
                [
                    "issue_code",
                    "match_idx",
                    "provider_match_id",
                    "kickoff_ts",
                    "league",
                    "home",
                    "away",
                    "native_handicap_line",
                    "reconciled_source",
                ]
            ],
            extension_rows[
                [
                    "issue_code",
                    "match_idx",
                    "provider_match_id",
                    "kickoff_ts",
                    "league",
                    "home",
                    "away",
                    "native_handicap_line",
                    "reconciled_source",
                ]
            ],
            recovered[
                [
                    "issue_code",
                    "match_idx",
                    "provider_match_id",
                    "kickoff_ts",
                    "league",
                    "home",
                    "away",
                    "native_handicap_line",
                    "reconciled_source",
                ]
            ],
        ],
        ignore_index=True,
    ).sort_values(["issue_code", "match_idx"], kind="stable")
    if reconciled.duplicated(["issue_code", "match_idx"]).any():
        raise RuntimeError("reconciled inventory contains duplicate issue slots")
    publication.atomic_write_csv(probes, output_root / "ISSUE_PROBE_RESULTS.csv")
    publication.atomic_write_csv(titan_frame, output_root / "TITAN_SAMPLE_RESULTS.csv")
    publication.atomic_write_csv(
        probes.loc[
            probes.local_only_slot_count.gt(0),
            [
                "issue_code",
                "local_candidate_fixture_count",
                "source_fixture_count",
                "local_only_slot_count",
            ],
        ],
        output_root / "LOCAL_CACHE_EXCLUSIONS.csv",
    )
    publication.atomic_write_csv(
        reconciled.groupby("reconciled_source", as_index=False).agg(
            issue_count=("issue_code", "nunique"),
            fixture_count=("match_idx", "size"),
        ),
        output_root / "RECONCILED_SOURCE_COUNTS.csv",
    )
    publication.atomic_write_csv(receipts_frame, staging_root / "FETCH_RECEIPTS.csv")
    publication.atomic_write_parquet(source_frame, staging_root / "SOURCE_ISSUE_SLOTS.parquet")
    publication.atomic_write_parquet(local_only, staging_root / "LOCAL_ONLY_SLOTS.parquet")
    publication.atomic_write_parquet(
        reconciled, staging_root / "RECONCILED_ISSUE_FIXTURE_INVENTORY.parquet"
    )

    after = source_digests(paths)
    if before != after:
        changed = sorted(name for name in before if before[name] != after[name])
        raise RuntimeError(f"protected source changed during read-only probe: {changed}")

    extension = extension_profile(paths.extension_2026)
    all_pages_authoritative = bool(
        not probes.empty
        and probes.status.eq("AUTHORITATIVE_ISSUE_MEMBERSHIP_AVAILABLE").all()
        and probes.source_fixture_count.gt(0).all()
    )
    all_titan_samples = bool(
        not probes.empty
        and probes.sampled_titan_success_count.eq(probes.sampled_titan_match_count).all()
        and probes.sampled_complete_triplets.gt(0).all()
    )
    if all_pages_authoritative and all_titan_samples and extension["schema_compatible"]:
        decision = "FULL_BACKFILL_EXECUTABLE"
    elif probes.source_fixture_count.sum() == 0:
        decision = "SOURCE_UNAVAILABLE"
    else:
        decision = "PARTIAL_SOURCE_GAP"
    report = {
        "contract": "BJ-UNIFIED-EU-PROXY-BACKFILL-POC-001",
        "decision": decision,
        "inventory": facts,
        "selected_issue_count": len(selected),
        "source_recovered_fixture_count": int(len(source_frame)),
        "local_cache_excluded_fixture_count": int(len(local_only)),
        "reconciled_issue_count": int(reconciled.issue_code.nunique()),
        "reconciled_fixture_count": int(len(reconciled)),
        "all_issue_pages_authoritative": all_pages_authoritative,
        "all_titan_samples_available": all_titan_samples,
        "extension_profile": extension,
        "protected_source_sha256_before": before,
        "protected_source_sha256_after": after,
        "canonical_write_performed": False,
        "execution_mode": "REPLAY" if args.replay else "NETWORK_PROBE",
        "staging_namespace": staging_root.name,
    }
    publication.atomic_write_json(output_root / "COVERAGE_REPORT.json", report)
    compact_names = (
        "COVERAGE_REPORT.json",
        "ISSUE_INVENTORY.csv",
        "UNRESOLVED_ISSUES.csv",
        "ISSUE_PROBE_RESULTS.csv",
        "TITAN_SAMPLE_RESULTS.csv",
        "LOCAL_CACHE_EXCLUSIONS.csv",
        "RECONCILED_SOURCE_COUNTS.csv",
    )
    compact_files = [output_root / name for name in compact_names]
    artifact_manifest = {
        "contract": report["contract"],
        "files": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in compact_files
        },
    }
    publication.atomic_write_json(
        output_root / "ARTIFACT_MANIFEST.json", artifact_manifest
    )
    staging_manifest = {
        **report,
        "fetch_receipt_count": int(len(receipts_frame)),
        "staging_ledger_sha256": {
            name: sha256_file(staging_root / name)
            for name in (
                "FETCH_RECEIPTS.csv",
                "SOURCE_ISSUE_SLOTS.parquet",
                "LOCAL_ONLY_SLOTS.parquet",
                "RECONCILED_ISSUE_FIXTURE_INVENTORY.parquet",
            )
        },
        "compact_artifact_manifest": artifact_manifest,
    }
    publication.atomic_write_json(staging_root / "POC_MANIFEST.json", staging_manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
