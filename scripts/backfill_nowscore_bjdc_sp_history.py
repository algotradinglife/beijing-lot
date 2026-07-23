#!/usr/bin/env python3
"""Backfill timestamped BJDC SP archives from cp.nowscore.com."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multimarket_p0 import HKT, resolve_kickoff_hkt, sha256_file  # noqa: E402
from src.nowscore_bjdc_sp_history import (  # noqa: E402
    TYPEID_MARKETS,
    NowscoreHistoryError,
    history_url,
    manifest_policy,
    parse_history_page,
    select_asof,
    select_at,
    selected_rows,
    verify_manifest,
)


DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_ROOT = ROOT / "results/data_collection/nowscore_bjdc_sp_history_v1"
USER_AGENT = "Mozilla/5.0 (compatible; BeijingLotResearch/1.0)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    backfill = sub.add_parser("backfill")
    backfill.add_argument("--issue", nargs="+", required=True)
    backfill.add_argument("--typeid", nargs="+", type=int, choices=tuple(TYPEID_MARKETS), default=(6, 7, 8, 9))
    backfill.add_argument("--db", type=Path, default=DEFAULT_DB)
    backfill.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    backfill.add_argument("--workers", type=int, default=4)
    backfill.add_argument("--timeout", type=float, default=30)
    backfill.add_argument("--retries", type=int, default=2)
    backfill.add_argument("--allow-partial", action="store_true")
    selection = backfill.add_mutually_exclusive_group(required=True)
    selection.add_argument("--segment-idx", type=int)
    selection.add_argument("--asof-hkt")
    selection.add_argument("--hours-before", type=float)
    backfill.add_argument("--match-idx", nargs="+", type=int)
    verify = sub.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    return parser.parse_args()


def fetch(url: str, timeout: float, retries: int) -> bytes:
    error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            error = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries + 1} attempts: {url}: {error}")


def load_matches(db: Path, issue: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{db.expanduser().resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT m.match_idx,m.end_time,COALESCE(n.kickoff_time,'') kickoff_time,
                   m.home,m.away,m.league
            FROM matches m LEFT JOIN nowscore_bjdc_matches n
              ON n.issue=m.issue AND n.match_idx=m.match_idx
            WHERE m.issue=? ORDER BY m.match_idx
            """,
            (issue,),
        ).fetchall()
    finally:
        connection.close()
    matches: list[dict[str, Any]] = []
    for row in rows:
        kickoff = resolve_kickoff_hkt(str(row["end_time"] or ""), str(row["kickoff_time"] or ""))
        if kickoff is None:
            raise NowscoreHistoryError(f"kickoff unresolved: issue={issue} match_idx={row['match_idx']}")
        matches.append(
            {
                "issue": issue,
                "match_idx": int(row["match_idx"]),
                "kickoff_hkt": kickoff,
                "home": str(row["home"] or ""),
                "away": str(row["away"] or ""),
                "league": str(row["league"] or ""),
            }
        )
    if not matches:
        raise NowscoreHistoryError(f"issue has no local matches: {issue}")
    return matches


def load_segment_freeze(db: Path, issue: str, segment_idx: int) -> tuple[datetime, set[int]]:
    connection = sqlite3.connect(f"file:{db.expanduser().resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT freeze_at,manual_frozen_at,match_indices_json FROM segment_decision_windows WHERE issue=? AND segment_idx=?",
            (issue, segment_idx),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise NowscoreHistoryError(f"segment window missing: {issue}#{segment_idx}")
    freeze_text = str(row["manual_frozen_at"] or row["freeze_at"] or "")
    freeze = datetime.fromisoformat(freeze_text)
    if freeze.tzinfo is None:
        freeze = freeze.replace(tzinfo=HKT)
    indices = {int(value) for value in json.loads(row["match_indices_json"])}
    return freeze.astimezone(HKT), indices


def selection_context(arguments: argparse.Namespace, issue: str) -> tuple[str, datetime | None, set[int] | None]:
    if arguments.segment_idx is not None:
        freeze, indices = load_segment_freeze(arguments.db, issue, arguments.segment_idx)
        return "segment_freeze", freeze, indices
    if arguments.asof_hkt:
        parsed = datetime.fromisoformat(arguments.asof_hkt)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=HKT)
        return "explicit_asof", parsed.astimezone(HKT), set(arguments.match_idx or ()) or None
    if arguments.hours_before is not None:
        return "standardized_offset", None, set(arguments.match_idx or ()) or None
    raise NowscoreHistoryError("selection mode is required")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_bundle(bundle: Path) -> dict[str, Any]:
    root = bundle.expanduser().resolve()
    verify_manifest(root / "manifest.json")
    entries = 0
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        target = root / name
        if Path(name).is_absolute() or ".." in Path(name).parts or not target.is_file() or sha256_file(target) != digest:
            raise NowscoreHistoryError(f"bundle checksum mismatch: {name}")
        entries += 1
    return {"status": "valid", "files": entries, "sha256s_sha256": sha256_file(root / "SHA256SUMS")}


def backfill_issue(arguments: argparse.Namespace, issue: str) -> dict[str, Any]:
    if arguments.hours_before is not None and arguments.hours_before <= 0:
        raise NowscoreHistoryError("hours-before must be positive")
    matches = load_matches(arguments.db, issue)
    mode, common_asof, selected_indices = selection_context(arguments, issue)
    if selected_indices is not None:
        matches = [match for match in matches if match["match_idx"] in selected_indices]
        missing_indices = selected_indices - {match["match_idx"] for match in matches}
        if missing_indices:
            raise NowscoreHistoryError(f"selected match indices missing locally: {sorted(missing_indices)}")
    fetched_at = datetime.now(timezone.utc).isoformat()
    identity = f"{issue}|{','.join(map(str, arguments.typeid))}|{mode}|{common_asof}|{fetched_at}"
    run_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    final = arguments.output_root.expanduser().resolve() / issue / run_id
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{run_id}.tmp-", dir=final.parent))
    raw_root = stage / "raw"
    raw_root.mkdir()
    page_rows: list[dict[str, Any]] = []
    frozen_rows: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    tasks = [(match, typeid) for match in matches for typeid in arguments.typeid]
    try:
        with ThreadPoolExecutor(max_workers=max(1, arguments.workers)) as pool:
            futures = {
                pool.submit(fetch, history_url(issue, match["match_idx"], typeid), arguments.timeout, arguments.retries): (match, typeid)
                for match, typeid in tasks
            }
            for future in as_completed(futures):
                match, typeid = futures[future]
                url = history_url(issue, match["match_idx"], typeid)
                market_key = TYPEID_MARKETS[typeid][0]
                name = f"{match['match_idx']:03d}_{typeid}.html"
                try:
                    payload = future.result()
                    (raw_root / name).write_bytes(payload)
                    headers, vectors = parse_history_page(payload, typeid, match["kickoff_hkt"])
                    asof = common_asof or match["kickoff_hkt"] - timedelta(hours=arguments.hours_before)
                    if asof >= match["kickoff_hkt"]:
                        raise NowscoreHistoryError("asof is not before kickoff")
                    selected = (
                        select_asof(vectors, match["kickoff_hkt"], arguments.hours_before)
                        if mode == "standardized_offset"
                        else select_at(vectors, asof)
                    )
                    frozen_rows.extend(
                        selected_rows(
                            issue=issue,
                            match_idx=match["match_idx"],
                            typeid=typeid,
                            kickoff_hkt=match["kickoff_hkt"],
                            vector=selected,
                            headers=headers,
                            batch_id=run_id,
                            source_url=url,
                            asof_hkt=asof,
                            selection_mode=mode,
                        )
                    )
                    page_rows.append(
                        {
                            "issue": issue,
                            "match_idx": match["match_idx"],
                            "market_key": market_key,
                            "typeid": typeid,
                            "source_url": url,
                            "raw_file": f"raw/{name}",
                            "raw_sha256": hashlib.sha256(payload).hexdigest(),
                            "history_vectors": len(vectors),
                            "oldest_source_ts_hkt": vectors[0].source_ts_hkt,
                            "newest_source_ts_hkt": vectors[-1].source_ts_hkt,
                            "selected_source_ts_hkt": selected.source_ts_hkt,
                            "asof_hkt": asof.isoformat(),
                            "minutes_to_kickoff": round((match["kickoff_hkt"] - asof).total_seconds() / 60, 3),
                            "source_age_minutes": round((asof - datetime.fromisoformat(selected.source_ts_hkt)).total_seconds() / 60, 3),
                            "status": "selected_asof",
                        }
                    )
                except Exception as exc:
                    rejected.append(
                        {
                            "issue": issue,
                            "match_idx": match["match_idx"],
                            "market_key": market_key,
                            "typeid": typeid,
                            "source_url": url,
                            "reason": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    if not arguments.allow_partial:
                        raise
        page_rows.sort(key=lambda row: (row["match_idx"], row["typeid"]))
        frozen_rows.sort(key=lambda row: (row["match_idx"], row["typeid"], row["outcome_code"]))
        rejected.sort(key=lambda row: (row["match_idx"], row["typeid"]))
        if not page_rows:
            raise NowscoreHistoryError("no archive pages produced a valid as-of vector")
        page_fields = (
            "issue", "match_idx", "market_key", "typeid", "source_url", "raw_file", "raw_sha256",
            "history_vectors", "oldest_source_ts_hkt", "newest_source_ts_hkt", "selected_source_ts_hkt", "status",
            "asof_hkt", "minutes_to_kickoff", "source_age_minutes",
        )
        frozen_fields = tuple(frozen_rows[0]) if frozen_rows else (
            "issue", "match_id", "match_idx", "market_key", "typeid", "outcome_code", "outcome_label", "sp",
            "kickoff_hkt", "asof_hkt", "minutes_to_kickoff", "source_ts_hkt", "source_age_minutes", "source_url",
            "batch_id", "selection_mode", "capture_classification",
        )
        rejection_fields = ("issue", "match_idx", "market_key", "typeid", "source_url", "reason")
        write_csv(stage / "page_inventory.csv", page_rows, page_fields)
        write_csv(stage / "selected_asof.csv", frozen_rows, frozen_fields)
        write_csv(stage / "rejections.csv", rejected, rejection_fields)
        manifest = {
            "schema_version": "nowscore_bjdc_sp_history_v1",
            "issue": issue,
            "run_id": run_id,
            "fetched_at_utc": fetched_at,
            "requested_typeids": list(arguments.typeid),
            "selection_mode": mode,
            "segment_idx": arguments.segment_idx,
            "selected_match_indices": [match["match_idx"] for match in matches],
            "common_asof_hkt": common_asof.isoformat() if common_asof else None,
            "reference_hours_before": arguments.hours_before if mode == "standardized_offset" else None,
            "requested_pages": len(tasks),
            "successful_pages": len(page_rows),
            "rejected_pages": len(rejected),
            "selected_outcome_rows": len(frozen_rows),
            "policy": manifest_policy(
                selection_mode=mode,
                hours_before=arguments.hours_before if mode == "standardized_offset" else None,
                asof_hkt=common_asof.isoformat() if common_asof else "",
            ),
            "status": "complete" if not rejected else "partial",
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        files = sorted(path for path in stage.rglob("*") if path.is_file())
        (stage / "SHA256SUMS").write_text(
            "".join(f"{sha256_file(path)}  {path.relative_to(stage).as_posix()}\n" for path in files), encoding="utf-8"
        )
        stage.rename(final)
        parent_fd = os.open(final.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    verification = verify_bundle(final)
    return {**manifest, "output_dir": str(final), "verification": verification}


def main() -> int:
    arguments = parse_args()
    if arguments.command == "verify":
        result: Any = verify_bundle(arguments.bundle)
    else:
        result = [backfill_issue(arguments, issue) for issue in arguments.issue]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
