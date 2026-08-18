"""Immutable, semantically verified Issue #235 historical-proxy package."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from bj235_timeseries import (
    CAUSAL_GRADE,
    OUTCOME_CODES,
    PROXY_HORIZONS,
    SOURCE_ID,
    TIME_SEMANTICS,
    build_historical_proxy_frame,
)
from source_schema import publication

CONTRACT_VERSION = "BJ-UNIFIED-BJ-SP-TIMESERIES-001-v2"
PACKAGE_SCHEMA = "bj235_historical_relative_proxy_v2"
REQUIRED_COLUMNS = {
    "fixture_id", "issue_code", "match_idx", "snapshot_horizon", "source_id",
    "time_semantics", "causal_grade", "native_handicap_line", "native_line_state_id",
    "outcome_code", "raw_sp", "normalized_inverse_sp_probability", "availability_mask",
    "unavailable_reason",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rehash_package(package: Path) -> None:
    sums = {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    publication.atomic_write_json(package / "SHA256SUMS.json", sums)


def _coverage(cells: pd.DataFrame) -> pd.DataFrame:
    vectors = cells.groupby(["issue_code", "snapshot_horizon", "fixture_id"], as_index=False).agg(
        native_line_available=("native_handicap_line", lambda values: bool(values.notna().all())),
        vector_available=("availability_mask", lambda values: bool(values.all())),
        valid_cell_count=("raw_sp", lambda values: int(values.notna().sum())),
    )
    return vectors.groupby(["issue_code", "snapshot_horizon"], as_index=False).agg(
        fixture_count=("fixture_id", "size"),
        complete_native_line_fixture_count=("native_line_available", "sum"),
        available_fixture_count=("vector_available", "sum"),
        available_cell_count=("valid_cell_count", "sum"),
    )


def _validate_cells(cells: pd.DataFrame) -> None:
    if not REQUIRED_COLUMNS <= set(cells.columns):
        raise AssertionError("proxy cell schema mismatch")
    if cells.empty:
        raise AssertionError("proxy cell panel is empty")
    if not cells["source_id"].eq(SOURCE_ID).all():
        raise AssertionError("proxy cell source mismatch")
    if not cells["time_semantics"].eq(TIME_SEMANTICS).all():
        raise AssertionError("proxy cell time semantics mismatch")
    if not cells["causal_grade"].eq(CAUSAL_GRADE).all():
        raise AssertionError("proxy cell causal grade mismatch")
    if not set(cells["snapshot_horizon"]).issubset(PROXY_HORIZONS):
        raise AssertionError("prohibited proxy horizon")
    if cells.duplicated(["fixture_id", "snapshot_horizon", "outcome_code"]).any():
        raise AssertionError("proxy cell identity duplicate")
    for _, vector in cells.groupby(["fixture_id", "snapshot_horizon"], sort=False):
        if set(vector["outcome_code"]) != set(OUTCOME_CODES) or len(vector) != 3:
            raise AssertionError("proxy vector is not exact 3/1/0")
        available = vector["availability_mask"]
        if available.nunique() != 1:
            raise AssertionError("proxy vector availability mismatch")
        raw = pd.to_numeric(vector["raw_sp"], errors="coerce")
        probabilities = pd.to_numeric(vector["normalized_inverse_sp_probability"], errors="coerce")
        if bool(available.iloc[0]):
            if raw.isna().any() or (~raw.gt(0)).any() or abs(float(probabilities.sum()) - 1.0) > 1e-9:
                raise AssertionError("available proxy probability reconciliation failed")
            expected = (1.0 / raw) / (1.0 / raw).sum()
            if (expected - probabilities).abs().gt(1e-9).any():
                raise AssertionError("proxy probability reconciliation failed")
            if not vector["unavailable_reason"].eq("AVAILABLE").all():
                raise AssertionError("available proxy vector has an exclusion reason")
        else:
            if not probabilities.eq(0.0).all():
                raise AssertionError("unavailable proxy vector retains probability")
            if vector["unavailable_reason"].eq("AVAILABLE").any():
                raise AssertionError("unavailable proxy vector lacks reason")


def _verify_hashes(package: Path) -> None:
    recorded = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if recorded != actual:
        raise AssertionError("hash closure mismatch")


def verify_package(package: Path) -> dict[str, object]:
    """Verify byte closure and recompute every decision-facing proxy fact."""
    _verify_hashes(package)
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != PACKAGE_SCHEMA or manifest.get("contract_version") != CONTRACT_VERSION:
        raise AssertionError("package contract mismatch")
    if manifest.get("source_id") != SOURCE_ID:
        raise AssertionError("source identity mismatch")
    if manifest.get("time_semantics") != TIME_SEMANTICS:
        raise AssertionError("source time semantics mismatch")
    if manifest.get("causal_grade") != CAUSAL_GRADE:
        raise AssertionError("source causal grade mismatch")
    if manifest.get("forbidden_inputs") != ["final", "settlement", "outcome", "winning_sp", "0.65"]:
        raise AssertionError("forbidden-input boundary mismatch")
    source_hash = str(manifest.get("source_main_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise AssertionError("source receipt hash malformed")
    cells = pd.read_parquet(package / "tables" / "historical_proxy_cells.parquet")
    _validate_cells(cells)
    expected_coverage = _coverage(cells).sort_values(["issue_code", "snapshot_horizon"]).reset_index(drop=True)
    actual_coverage = pd.read_csv(package / "tables" / "coverage_by_issue_horizon.csv", dtype={"issue_code": str})
    actual_coverage = actual_coverage.sort_values(["issue_code", "snapshot_horizon"]).reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(expected_coverage, actual_coverage, check_dtype=False)
    except AssertionError as error:
        raise AssertionError("coverage reconciliation failed") from error
    return {"status": "PASS", "proxy_cells": int(len(cells)), "coverage_rows": int(len(actual_coverage))}


def write_package(package: Path, source: Path) -> Path:
    """Read a stable source twice, then atomically publish a verified proxy package."""
    source = source.resolve()
    before = _sha256(source)
    cells = build_historical_proxy_frame(source)
    after = _sha256(source)
    if before != after:
        raise RuntimeError("historical source changed during read; refusing to publish")
    coverage = _coverage(cells)

    def populate(staging: Path) -> None:
        (staging / "tables").mkdir(parents=True, exist_ok=True)
        publication.atomic_write_parquet(cells, staging / "tables" / "historical_proxy_cells.parquet")
        publication.atomic_write_csv(coverage, staging / "tables" / "coverage_by_issue_horizon.csv")
        report = {
            "strict_historical": {"accepted_cells": 0, "reason": "NO_EXACT_HISTORICAL_CLOCK"},
            "retrospective_proxy": {
                "accepted_cells": int(cells["availability_mask"].sum()),
                "horizons": list(PROXY_HORIZONS),
                "source": SOURCE_ID,
            },
            "prospective": {"accepted_cells": 0, "reason": "NOT_CAPTURED_BY_THIS_HISTORICAL_PACKAGE"},
        }
        publication.atomic_write_json(staging / "RECOVERABILITY_REPORT.json", report)
        publication.atomic_write_text(
            staging / "README.md",
            "# Issue #235 historical relative-horizon proxy\n\n"
            "This package retains `initial`, `10h`, and `1h` separately. It is a "
            "RETROSPECTIVE_PROXY: labels are not wall-clock observations. Raw SP and "
            "normalized inverse-SP probability are separate fields; unavailable vectors "
            "have probability zero and an explicit reason. No final snapshot, settlement, "
            "outcome, winning SP, or Beijing payout coefficient is read or emitted.\n",
        )
        manifest = {
            "schema": PACKAGE_SCHEMA,
            "contract_version": CONTRACT_VERSION,
            "source_id": SOURCE_ID,
            "time_semantics": TIME_SEMANTICS,
            "causal_grade": CAUSAL_GRADE,
            "source_main_sha256": before,
            "horizons": list(PROXY_HORIZONS),
            "forbidden_inputs": ["final", "settlement", "outcome", "winning_sp", "0.65"],
            "table_rows": {"historical_proxy_cells": int(len(cells)), "coverage_by_issue_horizon": int(len(coverage))},
        }
        publication.atomic_write_json(staging / "MANIFEST.json", manifest)
        rehash_package(staging)
        verify_package(staging)

    return publication.atomic_publish_directory(package, populate, force=True)
