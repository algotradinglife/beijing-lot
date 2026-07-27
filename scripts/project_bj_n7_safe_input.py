#!/usr/bin/env python3
"""Project the one authorized mixed #66 CSV into an outcome-free canonical CSV.

This is Stage 1 of BJ-N7-COMPRESS-001.  It is intentionally the *only* tool
allowed to open the mixed source.  The output is suitable for a blind Stage 2
combination generator, but this script itself is not blind.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import sys
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTHORIZED_SOURCE = ROOT / "results/research/bj_n4_sp_prevalence_001/prevalence_r2/chosen_pre_decision_vectors.csv"
AUTHORIZED_SOURCE_SHA256 = "2f04f50d7fe6085f1353b6690c5e69bc6fb9befc2180fae780aa0bbd056b0233"
SOURCE_HEADER = (
    "issue", "match_idx", "match_id", "home", "away", "kickoff_ts",
    "decision_cutoff_ts", "snapshot_ts", "snapshot_age_hours_at_cutoff",
    "selected_codes", "quoted_sp_3", "quoted_sp_1", "quoted_sp_0",
    "effective_sp_3", "effective_sp_1", "effective_sp_0",
    "official_result_code", "coverage_hit",
)
SAFE_HEADER = (
    "issue", "match_idx", "match_id", "kickoff_ts", "decision_cutoff_ts",
    "snapshot_ts", "quoted_sp_3", "quoted_sp_1", "quoted_sp_0",
)


class ProjectionError(RuntimeError):
    """A deliberately value-free failure for the mixed source boundary."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sp(raw: str) -> str:
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ProjectionError("invalid quoted SP in allowlisted projection") from exc
    if not math.isfinite(value) or value <= 0.0:
        raise ProjectionError("invalid quoted SP in allowlisted projection")
    return f"{value:.8f}"


def project(source: Path, destination: Path, *, expected_sha256: str = AUTHORIZED_SOURCE_SHA256) -> tuple[int, str, str]:
    """Validate and project source without ever reading a forbidden field value."""
    if source.resolve() == destination.resolve():
        raise ProjectionError("projection destination equals authorized source")
    if destination.exists() or destination.is_symlink():
        raise ProjectionError("projection destination already exists")
    try:
        source_bytes = source.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        source_text = source_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProjectionError("authorized source is unreadable") from exc
    if source_sha256 != expected_sha256:
        raise ProjectionError("source SHA-256 mismatch")
    with StringIO(source_text, newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SOURCE_HEADER:
            raise ProjectionError("source header mismatch")
        safe_rows: list[dict[str, str]] = []
        identities: set[tuple[str, str, str]] = set()
        for row in reader:
            # Access only fields in SAFE_HEADER.  Forbidden source values are never
            # interpolated into messages, stdout, exceptions, or output.
            projected = {name: row[name] for name in SAFE_HEADER}
            try:
                issue = str(int(projected["issue"]))
                match_idx = str(int(projected["match_idx"]))
            except (TypeError, ValueError) as exc:
                raise ProjectionError("invalid allowlisted identity") from exc
            if not projected["match_id"] or not projected["kickoff_ts"] or not projected["decision_cutoff_ts"] or not projected["snapshot_ts"]:
                raise ProjectionError("missing allowlisted identity or timestamp")
            identity = (issue, match_idx, projected["match_id"])
            if identity in identities:
                raise ProjectionError("duplicate allowlisted identity")
            identities.add(identity)
            safe_rows.append({
                "issue": issue,
                "match_idx": match_idx,
                "match_id": projected["match_id"],
                "kickoff_ts": projected["kickoff_ts"],
                "decision_cutoff_ts": projected["decision_cutoff_ts"],
                "snapshot_ts": projected["snapshot_ts"],
                "quoted_sp_3": _canonical_sp(projected["quoted_sp_3"]),
                "quoted_sp_1": _canonical_sp(projected["quoted_sp_1"]),
                "quoted_sp_0": _canonical_sp(projected["quoted_sp_0"]),
            })
    safe_rows.sort(key=lambda item: (int(item["issue"]), int(item["match_idx"]), item["match_id"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAFE_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(safe_rows)
    return len(safe_rows), expected_sha256, sha256_file(destination)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BJ-N7 Stage 1 safe-input projector")
    parser.add_argument("--input", type=Path, default=AUTHORIZED_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.input.resolve() != AUTHORIZED_SOURCE.resolve():
        raise ProjectionError("unauthorized source path")
    count, source_sha, projection_sha = project(args.input, args.output)
    # Contract: stdout contains only these three non-sensitive values.
    print(f"row_count={count}")
    print(f"source_sha256={source_sha}")
    print(f"projection_sha256={projection_sha}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProjectionError as exc:
        print(f"projection_failed={exc}", file=sys.stderr)
        raise SystemExit(2)
