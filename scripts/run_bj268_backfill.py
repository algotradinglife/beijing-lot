#!/usr/bin/env python3
"""Execute #268 Gate 2/3 recovery into an isolated immutable staging root.

This script never opens the accepted #236 package or source SQLite inputs writable.
It records every logical request and every fixture×horizon disposition before a
later candidate materialization/publish step may consume the staging namespace.
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

from src.eu_proxy_backfill.backfill import resolve_duplicate_quotes  # noqa: E402
from src.eu_proxy_backfill.inventory import InventoryPaths, build_inventory, inventory_summary  # noqa: E402
from src.eu_proxy_backfill.probe import ISSUE_URL, TITAN_URL  # noqa: E402
from src.eu_proxy_backfill.runner import recover_issue  # noqa: E402
from src.source_schema import publication  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_hashes(paths: InventoryPaths) -> dict[str, str]:
    return {name: _sha256(Path(value)) for name, value in asdict(paths).items()}


def _client() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    })
    return session


def _assert_new_staging(root: Path, protected: list[Path]) -> None:
    location = root.expanduser().resolve()
    if location.exists() and any(location.iterdir()):
        raise ValueError(f"staging root must be new/empty for this immutable run: {location}")
    if any(location == item or location in item.parents or item in location.parents for item in protected):
        raise ValueError("staging root overlaps a protected source or accepted package")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--issues", nargs="*", default=[])
    parser.add_argument("--max-issues", type=int)
    parser.add_argument("--max-fixtures-per-issue", type=int)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--attempts", type=int, default=4)
    args = parser.parse_args()
    data_root = args.data_root.expanduser().resolve()
    paths = InventoryPaths(
        base_proxy=data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite",
        extension_2026=data_root / "derived/beidan_xlsm/beidan_nowscore_2026.sqlite",
        history=data_root / "beidan_history.db",
        live=data_root / "beidan_live.db",
    )
    protected = [*map(Path, asdict(paths).values()), data_root / "derived/bj236/eu_odds_proxy_v1"]
    staging = args.staging_root.expanduser().resolve()
    _assert_new_staging(staging, protected)
    staging.mkdir(parents=True, exist_ok=False)

    before = _source_hashes(paths)
    inventory = build_inventory(paths)
    summary = inventory_summary(inventory)
    unresolved = inventory.loc[inventory.proxy_status.eq("UNRESOLVED_SOURCE_RECOVERY")].copy()
    known = sorted(unresolved.issue_code.astype(str).unique(), key=int)
    selected = [str(value) for value in args.issues] or known
    unknown = sorted(set(selected) - set(known), key=int)
    if unknown:
        raise SystemExit(f"requested issues are not unresolved frozen inventory: {unknown}")
    if args.max_issues is not None:
        selected = selected[:args.max_issues]
    if not selected:
        raise SystemExit("no unresolved issue selected")

    publication.atomic_write_parquet(inventory, staging / "FROZEN_INVENTORY.parquet")
    publication.atomic_write_json(staging / "GATE_START.json", {
        "gate": "Gate 2 bounded staging" if len(selected) < len(known) else "Gate 3 full recovery",
        "logical_namespace": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
        "inventory_summary": summary,
        "selected_issue_codes": selected,
        "source_sha256_before": before,
    })
    client = _client()
    receipts: list[dict[str, object]] = []
    quote_frames: list[pd.DataFrame] = []
    disposition_frames: list[pd.DataFrame] = []
    issue_rows: list[dict[str, object]] = []
    for number, issue in enumerate(selected, start=1):
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
        receipts.extend(recovery.receipts)
        if recovery.quote_rows:
            quote_frames.append(pd.DataFrame(recovery.quote_rows))
        disposition_frames.append(recovery.fixture_horizon_dispositions)
        issue_rows.append({"issue_code": issue, "issue_disposition": recovery.issue_disposition})
        print(f"[{number}/{len(selected)}] {issue}: {recovery.issue_disposition}", flush=True)
    all_quotes = pd.concat(quote_frames, ignore_index=True) if quote_frames else pd.DataFrame(
        columns=["issue_code", "match_idx", "source_match_id", "snapshot_kind", "bookmaker_id", "v1", "v2", "v3", "payload_sha256"]
    )
    resolved, duplicate_ledger = resolve_duplicate_quotes(all_quotes) if not all_quotes.empty else (all_quotes, pd.DataFrame())
    dispositions = pd.concat(disposition_frames, ignore_index=True) if disposition_frames else pd.DataFrame()
    receipt_frame = pd.DataFrame(receipts)
    if receipt_frame.duplicated(["source_kind", "source_key"], keep=False).any():
        raise RuntimeError("logical acquisition keys are not unique")
    publication.atomic_write_csv(receipt_frame, staging / "ACQUISITION_RECEIPTS.csv")
    publication.atomic_write_parquet(resolved, staging / "RECOVERED_RAW_QUOTES.parquet")
    publication.atomic_write_parquet(dispositions, staging / "FIXTURE_HORIZON_DISPOSITIONS.parquet")
    publication.atomic_write_csv(duplicate_ledger, staging / "DUPLICATE_RESOLUTION_LEDGER.csv")
    publication.atomic_write_csv(pd.DataFrame(issue_rows), staging / "ISSUE_DISPOSITIONS.csv")
    after = _source_hashes(paths)
    if before != after:
        raise RuntimeError("read-only source hash changed during recovery; staging cannot advance")
    report = {
        "contract": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
        "logical_namespace": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
        "inventory_summary": summary,
        "selected_issue_count": len(selected),
        "selected_issue_codes": selected,
        "source_sha256_before": before,
        "source_sha256_after": after,
        "terminal_receipt_count": len(receipt_frame),
        "raw_quote_count": len(resolved),
        "fixture_horizon_disposition_count": len(dispositions),
        "successful_issue_pages": int((receipt_frame.source_kind.eq("issue_page") & receipt_frame.acquisition_result.eq("SUCCESS")).sum()),
        "successful_titan_acquisitions": int((receipt_frame.source_kind.eq("titan_1x2") & receipt_frame.acquisition_result.eq("SUCCESS")).sum()),
        "failed_acquisitions": int(receipt_frame.acquisition_result.ne("SUCCESS").sum()),
        "publication": "DISABLED_STAGING_ONLY",
    }
    publication.atomic_write_json(staging / "GATE_REPORT.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
