#!/usr/bin/env python3
"""Execute #268 Gate 2/3 recovery into an isolated immutable staging root.

The recovery lane is resumable at the logical-issue boundary.  Each completed
issue receives immutable receipt/quote/disposition parts and a final DONE
marker; only marked issue parts are eligible for final aggregation.  This
prevents a killed long crawl from silently losing a denominator member or
reusing unreceipted raw payloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.eu_proxy_backfill.backfill import aggregate_quote_parquet_parts  # noqa: E402
from src.eu_proxy_backfill.inventory import InventoryPaths, build_inventory, inventory_summary  # noqa: E402
from src.eu_proxy_backfill.probe import ISSUE_URL, TITAN_URL  # noqa: E402
from src.eu_proxy_backfill.runner import IssueRecovery, recover_issue  # noqa: E402
from src.source_schema import publication  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_hashes(paths: InventoryPaths) -> dict[str, str]:
    """Hash every read-visible SQLite component, including WAL sidecars."""
    hashes: dict[str, str] = {}
    for name, value in asdict(paths).items():
        database = Path(value)
        for suffix in ("", "-wal", "-shm"):
            component = Path(f"{database}{suffix}")
            if component.is_file():
                hashes[f"{name}{suffix}"] = _sha256(component)
    return hashes


def _client() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
        }
    )
    return session


def _paths(data_root: Path) -> InventoryPaths:
    return InventoryPaths(
        base_proxy=data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite",
        extension_2026=data_root / "derived/beidan_xlsm/beidan_nowscore_2026.sqlite",
        history=data_root / "beidan_history.db",
        live=data_root / "beidan_live.db",
    )


def _new_staging(root: Path, protected: list[Path]) -> None:
    if root.exists():
        raise FileExistsError(f"staging root already exists; use --resume: {root}")
    if any(root == item or root in item.parents or item in root.parents for item in protected):
        raise ValueError("staging root overlaps a protected source or accepted package")
    root.mkdir(parents=True, exist_ok=False)


def _recovery_inventory(inventory: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int | str]]:
    """Return the frozen authoritative #267 issue-page matrix for Gate 3.

    Directly rebuilding from a mutable live cache is permitted only for bounded
    Gate 2.  A complete run must instead consume the reconciled 213,263-fixture
    snapshot whose 14,553 issue-page cells were already identity-resolved.
    """
    required = {
        "issue_code", "match_idx", "provider_match_id", "kickoff_ts", "league",
        "home", "away", "native_handicap_line", "reconciled_source",
    }
    if not required <= set(inventory.columns):
        raise ValueError("Gate 3 requires a reconciled #267 frozen inventory, not a live-cache inventory")
    counts = inventory.reconciled_source.value_counts().to_dict()
    expected = {"ACCEPTED_236": 192709, "AVAILABLE_EXTENSION": 6001, "NOWSCORE_ISSUE_PAGE": 14553}
    if {str(key): int(value) for key, value in counts.items()} != expected:
        raise ValueError(f"frozen reconciled inventory count mismatch: {counts}")
    if len(inventory) != 213263 or inventory.issue_code.astype(str).nunique() != 808:
        raise ValueError("frozen reconciled inventory cardinality is not the #267 accepted denominator")
    recovery = inventory.loc[inventory.reconciled_source.eq("NOWSCORE_ISSUE_PAGE")].copy()
    digest = hashlib.sha256(
        inventory.sort_values(["issue_code", "match_idx"], kind="stable")
        .to_csv(index=False, lineterminator="\n", na_rep="").encode("utf-8")
    ).hexdigest()
    summary: dict[str, int | str] = {
        "inventory_sha256": digest,
        "known_issue_count": 808,
        "known_fixture_count": 213263,
        "accepted_236_issue_count": 701,
        "extension_issue_count": 34,
        "unresolved_issue_count": int(recovery.issue_code.astype(str).nunique()),
        "accepted_236_fixture_count": 192709,
        "extension_fixture_count": 6001,
        "unresolved_fixture_count": 14553,
    }
    return recovery, summary


def _start_or_resume(
    *,
    staging: Path,
    paths: InventoryPaths,
    selected: list[str] | None,
    frozen_inventory: Path | None,
    max_issues: int | None,
    max_fixtures_per_issue: int | None,
    resume: bool,
) -> tuple[pd.DataFrame, dict[str, object], list[str]]:
    """Create exactly one frozen inventory, or reopen it without rereading SQLite."""
    gate_start = staging / "GATE_START.json"
    inventory_path = staging / "FROZEN_INVENTORY.parquet"
    if resume:
        if frozen_inventory is not None:
            raise ValueError("--frozen-inventory is only valid when creating a new staging root")
        if max_issues is not None or max_fixtures_per_issue is not None:
            raise ValueError("resume cannot change frozen recovery limits")
        if not gate_start.is_file() or not inventory_path.is_file():
            raise ValueError("--resume requires immutable GATE_START.json and FROZEN_INVENTORY.parquet")
        start = json.loads(gate_start.read_text(encoding="utf-8"))
        inventory = pd.read_parquet(inventory_path)
        frozen_selected = [str(value) for value in start["selected_issue_codes"]]
        if selected is not None and selected != frozen_selected:
            raise ValueError("resume selection differs from frozen staging selection")
        return inventory, start, frozen_selected

    _new_staging(staging, [*map(Path, asdict(paths).values()), paths.base_proxy.parent.parent / "bj236/eu_odds_proxy_v1"])
    before = _source_hashes(paths)
    if frozen_inventory is None:
        inventory = build_inventory(paths)
        summary = inventory_summary(inventory)
        unresolved = inventory.loc[inventory.proxy_status.eq("UNRESOLVED_SOURCE_RECOVERY")]
        inventory_kind = "LIVE_CACHE_GATE2_ONLY"
    else:
        supplied = frozen_inventory.expanduser().resolve()
        if not supplied.is_file():
            raise FileNotFoundError(supplied)
        inventory = pd.read_parquet(supplied)
        unresolved, summary = _recovery_inventory(inventory)
        inventory_kind = "RECONCILED_267_FROZEN_GATE3"
    known = sorted(unresolved.issue_code.astype(str).unique(), key=int)
    use = selected if selected is not None else known
    unknown = sorted(set(use) - set(known), key=int)
    if unknown:
        raise ValueError(f"requested issues are not in the frozen recovery inventory: {unknown}")
    if max_issues is not None:
        if max_issues < 1:
            raise ValueError("max_issues must be positive")
        use = use[:max_issues]
    if not use:
        raise ValueError("no unresolved issue selected")
    publication.atomic_write_parquet(inventory, staging / "FROZEN_INVENTORY.parquet")
    start = {
        "gate": "Gate 3 full recovery" if frozen_inventory is not None and len(use) == len(known) else "Gate 2 bounded staging",
        "contract": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
        "logical_namespace": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
        "inventory_kind": inventory_kind,
        "inventory_summary": summary,
        "selected_issue_codes": use,
        "run_parameters": {
            "max_issues": max_issues,
            "max_fixtures_per_issue": max_fixtures_per_issue,
        },
        "source_sha256_before": before,
        "resume_protocol": "issue DONE marker is the only eligible completion boundary",
    }
    publication.atomic_write_json(gate_start, start)
    return inventory, start, use


def _issue_dir(staging: Path, issue: str) -> Path:
    if not issue.isdigit():
        raise ValueError(f"unsafe issue code: {issue!r}")
    return staging / "issue_parts" / issue


def _completed(staging: Path, issue: str) -> bool:
    marker = _issue_dir(staging, issue) / "DONE.json"
    if not marker.is_file():
        return False
    payload = json.loads(marker.read_text(encoding="utf-8"))
    required = {"receipts.csv", "raw_quotes.parquet", "fixture_horizon_dispositions.parquet", "issue_disposition.json"}
    found = {str(value) for value in payload.get("files", [])}
    declared_hashes = payload.get("sha256")
    if payload.get("issue_code") != issue or found != required or not isinstance(declared_hashes, dict):
        raise ValueError(f"invalid issue completion marker: {marker}")
    if set(declared_hashes) != required:
        raise ValueError(f"incomplete issue completion hashes: {marker}")
    for name in sorted(required):
        part = _issue_dir(staging, issue) / name
        expected = declared_hashes[name]
        if not part.is_file() or not isinstance(expected, str) or len(expected) != 64 or _sha256(part) != expected:
            raise ValueError(f"issue completion part hash mismatch: {part}")
    return True


def _write_issue_part(staging: Path, issue: str, recovery: IssueRecovery) -> None:
    """Durably complete one issue before any later issue may start.

    A prior partially written issue has no DONE marker and must be investigated,
    rather than overwritten or silently considered recovered on resume.
    """
    part = _issue_dir(staging, issue)
    if part.exists():
        raise FileExistsError(f"incomplete issue part requires investigation, not overwrite: {part}")
    part.mkdir(parents=True, exist_ok=False)
    receipts = pd.DataFrame(recovery.receipts)
    quotes = pd.DataFrame(recovery.quote_rows)
    dispositions = recovery.fixture_horizon_dispositions
    publication.atomic_write_csv(receipts, part / "receipts.csv")
    publication.atomic_write_parquet(quotes, part / "raw_quotes.parquet")
    publication.atomic_write_parquet(dispositions, part / "fixture_horizon_dispositions.parquet")
    publication.atomic_write_json(
        part / "issue_disposition.json",
        {"issue_code": issue, "issue_disposition": recovery.issue_disposition},
    )
    files = ["receipts.csv", "raw_quotes.parquet", "fixture_horizon_dispositions.parquet", "issue_disposition.json"]
    publication.atomic_write_json(
        part / "DONE.json",
        {
            "issue_code": issue,
            "files": files,
            "sha256": {name: _sha256(part / name) for name in files},
        },
    )


def _collect_small_parts(staging: Path, selected: list[str]) -> tuple[pd.DataFrame, list[Path], pd.DataFrame, pd.DataFrame]:
    """Load only bounded receipt/disposition metadata and retain quote paths.

    Quote parts can collectively exceed host memory.  They remain paths until
    the hash-partitioned external duplicate resolver consumes them one at a time.
    """
    if not all(_completed(staging, issue) for issue in selected):
        missing = [issue for issue in selected if not _completed(staging, issue)]
        raise RuntimeError(f"cannot finalize unfinished issue parts: {missing}")
    parts = [_issue_dir(staging, issue) for issue in selected]
    receipts = pd.concat([pd.read_csv(part / "receipts.csv") for part in parts], ignore_index=True)
    quote_paths = [part / "raw_quotes.parquet" for part in parts]
    dispositions = pd.concat([pd.read_parquet(part / "fixture_horizon_dispositions.parquet") for part in parts], ignore_index=True)
    issue_rows = pd.DataFrame([json.loads((part / "issue_disposition.json").read_text(encoding="utf-8")) for part in parts])
    if receipts.duplicated(["source_kind", "source_key"], keep=False).any():
        raise RuntimeError("logical acquisition keys are not unique")
    return receipts, quote_paths, dispositions, issue_rows


def _aggregation_manifest(staging: Path, selected: list[str]) -> dict[str, object]:
    """Return the completed aggregate receipt or fail closed on a partial root."""
    aggregation = staging / "AGGREGATION"
    manifest_path = aggregation / "MANIFEST.json"
    if not aggregation.exists():
        return {}
    if not manifest_path.is_file():
        raise RuntimeError("aggregation directory exists without a terminal manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("selected_issue_codes") != selected:
        raise RuntimeError("aggregation manifest selected issue set differs from frozen staging selection")
    required = {
        "ACQUISITION_RECEIPTS.csv",
        "FIXTURE_HORIZON_DISPOSITIONS.parquet",
        "ISSUE_DISPOSITIONS.csv",
        "RECOVERED_RAW_QUOTES/MANIFEST.json",
    }
    missing = sorted(name for name in required if not (aggregation / name).is_file())
    if missing:
        raise RuntimeError(f"aggregation manifest is incomplete: {missing}")
    return manifest


def _aggregate_parts(staging: Path, selected: list[str]) -> dict[str, object]:
    """Atomically publish the staging-only Gate 3 aggregation from DONE parts."""
    existing = _aggregation_manifest(staging, selected)
    if existing:
        return existing
    receipts, quote_paths, dispositions, issue_rows = _collect_small_parts(staging, selected)
    aggregation = staging / "AGGREGATION"

    def populate(root: Path) -> None:
        publication.atomic_write_csv(receipts, root / "ACQUISITION_RECEIPTS.csv")
        publication.atomic_write_parquet(dispositions, root / "FIXTURE_HORIZON_DISPOSITIONS.parquet")
        publication.atomic_write_csv(issue_rows, root / "ISSUE_DISPOSITIONS.csv")
        quote_manifest = aggregate_quote_parquet_parts(quote_paths, root / "RECOVERED_RAW_QUOTES")
        publication.atomic_write_json(
            root / "MANIFEST.json",
            {
                "algorithm": "BJ268_PART_AT_A_TIME_GATE3_AGGREGATION_V1",
                "selected_issue_codes": selected,
                "terminal_receipt_count": len(receipts),
                "fixture_horizon_disposition_count": len(dispositions),
                "raw_quote_aggregation": quote_manifest,
            },
        )

    publication.atomic_publish_directory(aggregation, populate)
    return _aggregation_manifest(staging, selected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--issues", nargs="*", default=None)
    parser.add_argument("--max-issues", type=int)
    parser.add_argument("--max-fixtures-per-issue", type=int)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--frozen-inventory", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--aggregate-only",
        action="store_true",
        help="consume only existing DONE issue parts; never construct a network client or fetch raw payloads",
    )
    args = parser.parse_args()
    if args.aggregate_only and not args.resume:
        raise ValueError("--aggregate-only requires --resume and an existing immutable staging root")
    if args.aggregate_only and (args.frozen_inventory is not None or args.max_issues is not None or args.max_fixtures_per_issue is not None):
        raise ValueError("--aggregate-only cannot alter the frozen staging inventory or limits")
    data_root = args.data_root.expanduser().resolve()
    paths = _paths(data_root)
    staging = args.staging_root.expanduser().resolve()
    requested = [str(value) for value in args.issues] if args.issues else None
    inventory, start, selected = _start_or_resume(
        staging=staging,
        paths=paths,
        selected=requested,
        frozen_inventory=args.frozen_inventory,
        max_issues=args.max_issues,
        max_fixtures_per_issue=args.max_fixtures_per_issue,
        resume=args.resume,
    )
    if not selected:
        raise ValueError("no unresolved issue selected")

    if start["inventory_kind"] == "RECONCILED_267_FROZEN_GATE3":
        unresolved, _ = _recovery_inventory(inventory)
    else:
        unresolved = inventory.loc[inventory.proxy_status.eq("UNRESOLVED_SOURCE_RECOVERY")].copy()
    if not args.aggregate_only:
        client = _client()
        for number, issue in enumerate(selected, start=1):
            if _completed(staging, issue):
                print(f"[{number}/{len(selected)}] {issue}: already durable", flush=True)
                continue
            issue_expected = unresolved.loc[unresolved.issue_code.astype(str).eq(issue)].copy()
            if args.max_fixtures_per_issue is not None:
                issue_expected = issue_expected.head(args.max_fixtures_per_issue)
            recovery = recover_issue(
                client,
                issue_code=issue,
                expected=issue_expected,
                staging_root=staging,
                issue_url=ISSUE_URL.format(issue=issue),
                titan_url_template=TITAN_URL,
                timeout=args.timeout,
                attempts=args.attempts,
                max_fixtures=args.max_fixtures_per_issue,
            )
            _write_issue_part(staging, issue, recovery)
            print(f"[{number}/{len(selected)}] {issue}: {recovery.issue_disposition}", flush=True)

    aggregation = _aggregate_parts(staging, selected)
    receipts = pd.read_csv(staging / "AGGREGATION" / "ACQUISITION_RECEIPTS.csv")
    after = _source_hashes(paths)
    if start["source_sha256_before"] != after:
        raise RuntimeError("source hash changed during recovery; staging cannot advance")
    quote_summary = aggregation["raw_quote_aggregation"]
    report = {
        "contract": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
        "logical_namespace": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
        "inventory_summary": start["inventory_summary"],
        "selected_issue_count": len(selected),
        "selected_issue_codes": selected,
        "source_sha256_before": start["source_sha256_before"],
        "source_sha256_after": after,
        "terminal_receipt_count": len(receipts),
        "raw_quote_count": quote_summary["selected_row_count"],
        "raw_quote_input_count": quote_summary["input_row_count"],
        "duplicate_ledger_row_count": quote_summary["duplicate_ledger_row_count"],
        "fixture_horizon_disposition_count": aggregation["fixture_horizon_disposition_count"],
        "successful_issue_pages": int((receipts.source_kind.eq("issue_page") & receipts.acquisition_result.eq("SUCCESS")).sum()),
        "successful_titan_acquisitions": int((receipts.source_kind.eq("titan_1x2") & receipts.acquisition_result.eq("SUCCESS")).sum()),
        "failed_acquisitions": int(receipts.acquisition_result.ne("SUCCESS").sum()),
        "aggregation": "PART_AT_A_TIME_HASH_PARTITIONED_NO_FULL_QUOTE_CONCAT",
        "aggregate_only": args.aggregate_only,
        "publication": "DISABLED_STAGING_ONLY",
    }
    publication.atomic_write_json(staging / "GATE_REPORT.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
