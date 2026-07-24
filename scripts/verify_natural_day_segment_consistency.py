#!/usr/bin/env python3
"""Fail-closed cross-layer verifier for the natural-day operational contract."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.natural_day_manifest import (  # noqa: E402
    NaturalDayManifestError,
    canonical,
    load_published_manifest,
    verify_manifest,
    verify_operational_windows,
)


def verify(
    *,
    manifest_path: Path,
    db_path: Path,
    plan_root: Path | None = None,
) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    claimed = verify_manifest(manifest)
    conn = sqlite3.connect(db_path)
    try:
        published = load_published_manifest(conn, str(manifest["issue"]))
        if published is None:
            raise NaturalDayManifestError(
                "SQLite has no authoritative natural-day publication record"
            )
        if canonical({
            key: value
            for key, value in published.items()
            if key not in {"manifest_path", "published_at_hkt"}
        }) != canonical(manifest):
            raise NaturalDayManifestError(
                "SQLite publication differs from supplied natural-day manifest"
            )
        verify_operational_windows(conn, published)
    finally:
        conn.close()

    checked_plans = 0
    stale_plans: list[str] = []
    if plan_root is not None:
        for summary_path in sorted(
            plan_root.glob(
                f"{manifest['issue']}_*/segment_betting_plan_summary.json"
            )
        ):
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            scope = str(
                payload.get("artifact_planning_scope")
                or payload.get("planning_scope")
                or ""
            )
            if scope != "by_segment":
                continue
            checked_plans += 1
            if str(payload.get("segment_manifest_sha256") or "") != claimed:
                stale_plans.append(str(summary_path))
        if stale_plans:
            raise NaturalDayManifestError(
                "stale by_segment artifacts differ from the published manifest: "
                + ", ".join(stale_plans)
            )

    return {
        "status": "PASS",
        "issue": str(manifest["issue"]),
        "manifest_sha256": claimed,
        "segments": [
            {
                "segment_idx": int(segment["segment_idx"]),
                "freeze_at": str(segment["freeze_at"]),
                "match_count": int(segment["match_count"]),
            }
            for segment in manifest["segments"]
        ],
        "operational_windows": "PASS",
        "decision_api_contract_source": "natural_day_segment_publications",
        "by_segment_artifacts_checked": checked_plans,
        "stale_by_segment_artifacts": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--plan-root", type=Path)
    args = parser.parse_args()
    try:
        report = verify(
            manifest_path=args.manifest,
            db_path=args.db,
            plan_root=args.plan_root,
        )
    except (NaturalDayManifestError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
