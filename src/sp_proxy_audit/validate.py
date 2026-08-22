"""Cryptographic and semantic verification for Issue #318 packages."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .builder import CONTRACT, REQUIRED_COLUMNS
from .data import sha256
from .grading import OUTCOMES
from .metrics import coverage_by_issue, overlap_diagnostics, terminal_decision


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_package(
    root: Path, expected_manifest_sha256: str | None = None
) -> dict[str, object]:
    """Fail closed on inventory, hash, vector, or terminal-decision tampering."""
    manifest_path = root / "MANIFEST.json"
    if not manifest_path.is_file():
        raise ValueError("missing package manifest")
    actual_manifest = sha256(manifest_path)
    if (
        expected_manifest_sha256 is not None
        and actual_manifest != expected_manifest_sha256
    ):
        raise ValueError("trusted manifest anchor mismatch")
    manifest = _load(manifest_path)
    if manifest.get("contract_version") != CONTRACT:
        raise ValueError("wrong contract version")
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict):
        raise ValueError("manifest files is not a map")
    actual_payloads = {path.name for path in root.iterdir() if path.is_file()} - {
        "MANIFEST.json",
        "SHA256SUMS.json",
    }
    if actual_payloads != set(expected_files):
        raise ValueError("manifest payload inventory mismatch")
    for relative, expected in expected_files.items():
        path = root / relative
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"package hash mismatch: {relative}")
    checksum_path = root / "SHA256SUMS.json"
    checksums = _load(checksum_path)
    if checksums.get("MANIFEST.json") != actual_manifest:
        raise ValueError("checksum manifest binding mismatch")
    for relative, expected in checksums.items():
        path = root / relative
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"checksum mismatch: {relative}")

    inventory = pd.read_csv(root / "source_inventory.csv")
    cells = pd.read_parquet(root / "graded_cells.parquet")
    coverage = pd.read_csv(
        root / "coverage_by_issue.csv", dtype={"issue_code": "string"}
    )
    exclusion = pd.read_parquet(root / "exclusion_ledger.parquet")
    decision = _load(root / "decision.json")
    if sha256(root / "source_inventory.csv") != manifest.get("source_inventory_sha256"):
        raise ValueError("source inventory provenance binding mismatch")
    if list(cells.columns) != REQUIRED_COLUMNS + ["provenance_sha256"]:
        raise ValueError("graded cell schema mismatch")
    if not cells.empty:
        key = ["source_id", "issue_code", "match_idx", "snapshot_kind"]
        vector = cells.groupby(key, dropna=False).agg(
            rows=("outcome_code", "size"),
            outcomes=("outcome_code", lambda values: frozenset(values.astype(str))),
            grades=("source_grade", "nunique"),
            reasons=("exclusion_reason", "nunique"),
        )
        if (
            not vector.rows.eq(3).all()
            or not vector.outcomes.map(
                lambda values: values == frozenset(OUTCOMES)
            ).all()
        ):
            raise ValueError(
                "vector does not have exactly the canonical outcome triplet"
            )
        if not vector.grades.eq(1).all() or not vector.reasons.le(1).all():
            raise ValueError("vector grading is not atomic")
        strict = cells.source_grade.eq("STRICT_PRE_EVENT")
        if strict.any():
            parsed = pd.DataFrame(
                {
                    column: pd.to_datetime(
                        cells.loc[strict, column], utc=True, errors="coerce"
                    )
                    for column in (
                        "observed_at_utc",
                        "decision_epoch_utc",
                        "kickoff_utc",
                    )
                }
            )
            if (
                parsed.isna().any().any()
                or not (
                    parsed.observed_at_utc.le(parsed.decision_epoch_utc)
                    & parsed.decision_epoch_utc.lt(parsed.kickoff_utc)
                ).all()
            ):
                raise ValueError("strict cell escaped timestamp proof")
        if (
            cells.loc[cells.source_grade.ne("UNUSABLE"), "exclusion_reason"]
            .notna()
            .any()
        ):
            raise ValueError("accepted cell has exclusion reason")
        if (
            cells.loc[cells.source_grade.eq("UNUSABLE"), "exclusion_reason"]
            .isna()
            .any()
        ):
            raise ValueError("unusable cell lacks exclusion reason")
    if decision.get("terminal_disposition") not in {
        "STRICT_HISTORY_AVAILABLE",
        "PROXY_USABLE_FOR_EXPLORATION",
        "NO_CAUSAL_PRICE_SUPPORT",
    }:
        raise ValueError("invalid terminal disposition")
    if (
        inventory.availability.ne("PRESENT").any()
        and decision.get("terminal_disposition") != "NO_CAUSAL_PRICE_SUPPORT"
    ):
        raise ValueError(
            "incomplete-or-mismatched-source package elevated terminal disposition"
        )
    if not coverage.empty and not set(coverage.columns).issuperset(
        {
            "partition",
            "issue_code",
            "source_id",
            "source_grade",
            "snapshot_kind",
            "feasible_n7",
        }
    ):
        raise ValueError("coverage key/schema mismatch")
    if coverage.loc[coverage.source_grade.eq("UNUSABLE"), "feasible_n7"].any():
        raise ValueError("unusable vectors escaped into N7 capacity")
    if not exclusion.empty and not set(exclusion.exclusion_reason.dropna()).issubset(
        {
            "SOURCE_MISSING",
            "MANIFEST_MISMATCH",
            "TIMESTAMP_UNPROVEN",
            "POST_DECISION",
            "POST_KICKOFF",
            "INCOMPLETE_TRIPLET",
            "IDENTITY_MISMATCH",
            "DUPLICATE_CONFLICT",
            "SETTLEMENT_ONLY",
            "NONFINITE_PRICE",
            "NONPOSITIVE_PRICE",
        }
    ):
        raise ValueError("unknown exclusion reason")
    recomputed_coverage = coverage_by_issue(cells)
    pd.testing.assert_frame_equal(
        coverage.reset_index(drop=True),
        recomputed_coverage.reset_index(drop=True),
        check_dtype=False,
    )
    _, _, recomputed_overlap = overlap_diagnostics(cells)
    overlap = pd.read_csv(root / "overlap_metrics.csv")
    pd.testing.assert_frame_equal(
        overlap.reset_index(drop=True),
        recomputed_overlap.reset_index(drop=True),
        check_dtype=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )
    recomputed_decision = terminal_decision(cells, recomputed_overlap, inventory)
    for field in (
        "terminal_disposition",
        "strict_partition_support",
        "proxy_lane_decisions",
        "conflict_cells",
        "failed_thresholds",
    ):
        if decision.get(field) != recomputed_decision.get(field):
            raise ValueError(f"terminal decision drift: {field}")
    return {
        "verdict": "PASS",
        "manifest_sha256": actual_manifest,
        "payload_files": len(expected_files),
        "graded_cells": int(len(cells)),
        "source_missing": int(inventory.availability.eq("SOURCE_MISSING").sum()),
    }
