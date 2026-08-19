#!/usr/bin/env python3
"""Build the #267 denominator and probe missing historical Nowscore/Titan data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pyarrow.dataset as pa_dataset

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from src.eu_proxy_backfill import (  # noqa: E402
    InventoryPaths,
    ProbeClient,
    StagedProbeClient,
    build_inventory,
    inventory_summary,
    probe_issue,
)
from eu_odds_timeseries.materialize import materialize_proxy_view  # noqa: E402
from src.source_schema import publication  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    """Hash file names, sizes and bytes for one immutable package tree."""

    root = path.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    digest = hashlib.sha256()
    for file_path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = file_path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(file_path.stat().st_size.to_bytes(8, "big"))
        digest.update(bytes.fromhex(sha256_file(file_path)))
    return digest.hexdigest()


def create_sqlite_snapshot(source: Path, target: Path) -> None:
    """Create one transactionally consistent read-only SQLite input snapshot."""

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp.sqlite", dir=target.parent
    )
    os.close(descriptor)
    temp = Path(temp_name)
    source_connection: sqlite3.Connection | None = None
    target_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(
            f"file:{source.expanduser().resolve()}?mode=ro", uri=True
        )
        target_connection = sqlite3.connect(temp)
        source_connection.backup(target_connection)
        target_connection.commit()
        target_connection.close()
        target_connection = None
        source_connection.close()
        source_connection = None
        publication.fsync_file(temp)
        os.replace(temp, target)
        publication.fsync_dir(target.parent)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    finally:
        if target_connection is not None:
            target_connection.close()
        if source_connection is not None:
            source_connection.close()


def overlaps_protected(candidate: Path, protected: set[Path]) -> bool:
    location = candidate.expanduser().resolve()
    return any(
        location == path or location in path.parents or path in location.parents
        for path in protected
    )


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


def _parquet_schema_signature(package: Path, table: str) -> list[dict[str, object]]:
    schema = pa_dataset.dataset(package / table, format="parquet").schema
    return [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in schema
    ]


def materialize_extension_parity(
    extension: Path, target: Path, canonical_package: Path
) -> dict[str, object]:
    """Run the exact #236 normalizer and compare schemas and semantic domains."""

    source_hash = sha256_file(extension)
    summary = materialize_proxy_view(
        extension,
        target,
        source_sha256=source_hash,
        chunksize=100_000,
    )
    tables = ("probabilities", "source_trace", "exclusion_ledger", "translation_readiness")
    schemas = {
        table: {
            "canonical": _parquet_schema_signature(canonical_package, table),
            "extension": _parquet_schema_signature(target, table),
        }
        for table in tables
    }
    schema_parity = all(
        values["canonical"] == values["extension"] for values in schemas.values()
    )
    probability = pd.read_parquet(
        target / "probabilities",
        columns=[
            "canonical_fixture_key",
            "snapshot_kind",
            "source_role",
            "market_type",
            "causal_grade",
            "outcome_code",
            "probability",
            "availability_mask",
        ],
    )
    sums = probability.groupby(
        ["canonical_fixture_key", "snapshot_kind"], sort=False
    ).probability.sum()
    with sqlite3.connect(f"file:{extension.resolve()}?mode=ro", uri=True) as connection:
        extension_fixtures = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue_code, match_idx,
                   CAST(provider_match_id AS TEXT) AS provider_match_id
            FROM matches
            WHERE issue IS NOT NULL AND trim(CAST(issue AS TEXT)) <> ''
              AND match_idx IS NOT NULL
            ORDER BY CAST(issue AS TEXT), match_idx
            """,
            connection,
        )
    matched_keys = set(probability.canonical_fixture_key)
    extension_fixtures["canonical_fixture_key"] = [
        f"bjslot:{str(issue).strip()}:{int(slot):03d}"
        for issue, slot in zip(
            extension_fixtures.issue_code, extension_fixtures.match_idx
        )
    ]
    unmatched = extension_fixtures.loc[
        ~extension_fixtures.canonical_fixture_key.isin(matched_keys)
    ].copy()
    unmatched["disposition"] = "UNAVAILABLE_NO_VALID_EURO_1X2_HORIZON"
    domain_checks = {
        "outcome_codes_3_1_0": set(probability.outcome_code.astype(str))
        == {"3", "1", "0"},
        "horizons_initial_10h_1h": set(probability.snapshot_kind)
        == {"initial", "10h", "1h"},
        "market_euro_1x2": set(probability.market_type) == {"euro_1x2"},
        "causal_grade_retrospective_proxy": set(probability.causal_grade)
        == {"RETROSPECTIVE_RELATIVE_PROXY"},
        "source_role_nowscore_titan": set(probability.source_role)
        == {"Nowscore_Titan_historical_market_proxy"},
        "availability_mask_one": set(probability.availability_mask.astype(str)) == {"1"},
        "probability_range": bool(probability.probability.between(0.0, 1.0).all()),
        "probability_triplets_sum_one": bool((sums.sub(1.0).abs() <= 1e-12).all()),
    }
    facts = json.loads((target / "report_facts.json").read_text(encoding="utf-8"))
    return {
        "source_sha256": source_hash,
        "schema_parity": schema_parity,
        "schemas": schemas,
        "domain_checks": domain_checks,
        "domain_parity": all(domain_checks.values()),
        "strict_forward_rows": int(facts["strict_forward_rows"]),
        "matched_fixture_count": int(summary["matched_fixture_count"]),
        "probability_rows": int(facts["probability_rows"]),
        "trace_rows": int(facts["trace_rows"]),
        "translation_rows": int(facts["translation_rows"]),
        "exclusion_rows": int(facts["exclusion_rows"]),
        "unmatched_fixture_count": int(len(unmatched)),
        "unmatched_fixture_dispositions": unmatched.to_dict("records"),
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
    live_source = data_root / "beidan_live.db"
    extension_source = data_root / "derived/beidan_xlsm/beidan_nowscore_2026.sqlite"
    live_snapshot = staging_root / "input_snapshots/beidan_live.snapshot.sqlite"
    extension_snapshot = (
        staging_root / "input_snapshots/beidan_nowscore_2026.snapshot.sqlite"
    )
    paths = InventoryPaths(
        base_proxy=data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite",
        extension_2026=extension_snapshot,
        history=data_root / "beidan_history.db",
        live=live_snapshot,
    )
    canonical_package = data_root / "derived/bj236/eu_odds_proxy_v1"
    protected = {
        paths.base_proxy.resolve(),
        extension_source.resolve(),
        paths.history.resolve(),
        live_source.resolve(),
        canonical_package.resolve(),
    }
    if overlaps_protected(staging_root, protected):
        raise SystemExit("staging root overlaps a protected source path")
    if overlaps_protected(output_root, protected):
        raise SystemExit("output root overlaps a protected source path")
    if args.replay:
        if not live_snapshot.is_file() or not extension_snapshot.is_file():
            raise SystemExit("replay requires both frozen staged SQLite snapshots")
    else:
        create_sqlite_snapshot(live_source, live_snapshot)
        create_sqlite_snapshot(extension_source, extension_snapshot)
    staging_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    live_source_before = sha256_file(live_source)
    extension_source_before = sha256_file(extension_source)
    before = {
        **source_digests(paths),
        "canonical_236_package": sha256_tree(canonical_package),
    }
    inventory = build_inventory(paths)
    facts = inventory_summary(inventory)
    per_issue = issue_inventory(inventory)
    unresolved = per_issue.loc[per_issue.unresolved_fixture_count.gt(0)].copy()
    selected = list(args.issues or unresolved.issue_code.tolist())
    full_issue_set = set(selected) == set(unresolved.issue_code)
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

    after = {
        **source_digests(paths),
        "canonical_236_package": sha256_tree(canonical_package),
    }
    extension_source_after = sha256_file(extension_source)
    if before != after or extension_source_before != extension_source_after:
        changed = sorted(name for name in before if before[name] != after[name])
        if extension_source_before != extension_source_after:
            changed.append("extension_2026_source")
        raise RuntimeError(f"protected source changed during read-only probe: {changed}")

    extension = extension_profile(paths.extension_2026)
    extension_parity = materialize_extension_parity(
        paths.extension_2026,
        staging_root / "extension_2026_proxy_parity",
        canonical_package,
    )
    publication.atomic_write_json(
        output_root / "EXTENSION_NORMALIZED_PARITY.json", extension_parity
    )
    publication.atomic_write_csv(
        pd.DataFrame(extension_parity["unmatched_fixture_dispositions"]),
        output_root / "EXTENSION_UNMATCHED_FIXTURES.csv",
    )
    all_pages_authoritative = bool(
        not probes.empty
        and probes.status.eq("AUTHORITATIVE_ISSUE_MEMBERSHIP_AVAILABLE").all()
        and probes.source_fixture_count.gt(0).all()
    )
    all_titan_samples = bool(
        not probes.empty
        and probes.sampled_titan_success_count.eq(probes.sampled_titan_match_count).all()
        and not titan_frame.empty
        and titan_frame.status.eq("AVAILABLE").all()
        and titan_frame.complete_initial_triplets.gt(0).all()
        and titan_frame.complete_10h_triplets.gt(0).all()
        and titan_frame.complete_1h_triplets.gt(0).all()
    )
    if (
        full_issue_set
        and all_pages_authoritative
        and all_titan_samples
        and extension["schema_compatible"]
        and extension_parity["schema_parity"]
        and extension_parity["domain_parity"]
        and extension_parity["strict_forward_rows"] == 0
    ):
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
        "full_unresolved_issue_set_selected": full_issue_set,
        "source_recovered_fixture_count": int(len(source_frame)),
        "local_cache_excluded_fixture_count": int(len(local_only)),
        "reconciled_issue_count": int(reconciled.issue_code.nunique()),
        "reconciled_fixture_count": int(len(reconciled)),
        "all_issue_pages_authoritative": all_pages_authoritative,
        "all_titan_samples_available": all_titan_samples,
        "extension_profile": extension,
        "extension_normalized_parity": extension_parity,
        "protected_source_sha256_before": before,
        "protected_source_sha256_after": after,
        "live_source_sha256_before": live_source_before,
        "live_source_sha256_after": sha256_file(live_source),
        "extension_source_sha256_before": extension_source_before,
        "extension_source_sha256_after": extension_source_after,
        "live_snapshot_sha256": sha256_file(live_snapshot),
        "live_inventory_input": "STAGED_READ_ONLY_SNAPSHOT",
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
        "EXTENSION_NORMALIZED_PARITY.json",
        "EXTENSION_UNMATCHED_FIXTURES.csv",
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
                "input_snapshots/beidan_live.snapshot.sqlite",
                "input_snapshots/beidan_nowscore_2026.snapshot.sqlite",
            )
        },
        "compact_artifact_manifest": artifact_manifest,
    }
    publication.atomic_write_json(staging_root / "POC_MANIFEST.json", staging_manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
