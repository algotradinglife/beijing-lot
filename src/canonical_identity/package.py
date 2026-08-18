"""Immutable, tamper-evident #251 identity evidence package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from . import aliases as alias_contract
from . import mapping, profile


PACKAGE_NAME = "bj251_canonical_identity_v3"

TABLE_SCHEMAS = {
    "source_input_snapshot.csv": set(mapping.SOURCE_INPUT_COLUMNS),
    "issue_identity.csv": {"issue_id", "issue_code", "rule_version"},
    "issue_slot_identity.csv": {
        "issue_slot_id", "issue_id", "issue_code", "match_idx",
        "fixture_entity_id", "slot_identity_status", "fixture_entity_status",
        "source_count", "rule_version",
    },
    "play_identity.csv": {"play_id", "issue_slot_id", "play_code", "rule_version"},
    "outcome_cell_identity.csv": {
        "outcome_cell_id", "play_id", "issue_slot_id", "outcome_code", "rule_version",
    },
    "source_trace.csv": set(mapping.TRACE_COLUMNS),
    "ambiguity_ledger.csv": set(mapping.LEDGER_COLUMNS),
    "coverage.csv": {
        "source_id", "year", "source_competition_key", "causal_grade", "rows",
        "exact_slot_rows", "diagnostic_label_agreement_fields",
        "source_local_entity_fields", "settlement_only_entity_fields",
        "conflicting_entity_fields", "unidentified_entity_fields", "unmatched_slot_rows",
    },
    "temporal_aliases.csv": set(alias_contract.ALIAS_COLUMNS),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False)
        handle.flush()
        os.fsync(handle.fileno())


def _write_json(payload: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _checksums(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }


def checksums_anchor(package_path: Path) -> str:
    """Return the out-of-package trust anchor for a published checksum set."""
    return _sha256(package_path / "SHA256SUMS.json")


def build_package(
    output_root: Path,
    result: mapping.MappingResult,
    coverage: pd.DataFrame,
    aliases: pd.DataFrame,
) -> Path:
    """Durably publish exactly one complete package; no partial directory leaks."""
    target = output_root / PACKAGE_NAME
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{PACKAGE_NAME}.staging-", dir=output_root))
    previous = output_root / f".{PACKAGE_NAME}.previous"
    try:
        profile.validate_identity_tables(result)
        alias_contract.validate_alias_intervals(aliases)
        _write_csv(result.source_inputs, staging / "tables" / "source_input_snapshot.csv")
        _write_csv(result.issues, staging / "tables" / "issue_identity.csv")
        _write_csv(result.slots, staging / "tables" / "issue_slot_identity.csv")
        _write_csv(result.plays, staging / "tables" / "play_identity.csv")
        _write_csv(result.outcome_cells, staging / "tables" / "outcome_cell_identity.csv")
        _write_csv(result.traces, staging / "tables" / "source_trace.csv")
        _write_csv(result.ledger, staging / "tables" / "ambiguity_ledger.csv")
        _write_csv(coverage, staging / "tables" / "coverage.csv")
        _write_csv(aliases, staging / "tables" / "temporal_aliases.csv")
        manifest = {
            "contract_version": mapping.RULE_VERSION,
            "package": PACKAGE_NAME,
            "issue_slot_identity_rule": "exact issue_code + match_idx; issue-local only",
            "fixture_entity_rule": "nullable unless provenance-backed stable event key exists",
            "entity_resolution_rule": "canonical entity disabled; source-local or diagnostic equality only",
            "source_input_snapshot_sha256": _sha256(staging / "tables" / "source_input_snapshot.csv"),
            "outcome_exposed_inputs": False,
            "fuzzy_auto_acceptance": False,
            "issue_count": int(len(result.issues)),
            "source_input_count": int(len(result.source_inputs)),
            "issue_slot_count": int(len(result.slots)),
            "play_count": int(len(result.plays)),
            "outcome_cell_count": int(len(result.outcome_cells)),
            "trace_count": int(len(result.traces)),
            "exception_count": int(len(result.ledger)),
        }
        _write_json(manifest, staging / "MANIFEST.json")
        _write_json(_checksums(staging), staging / "SHA256SUMS.json")
        for directory in sorted([item for item in staging.rglob("*") if item.is_dir()], key=lambda item: len(item.parts), reverse=True):
            _fsync_directory(directory)
        _fsync_directory(staging)
        _fsync_directory(output_root)
        if previous.exists():
            shutil.rmtree(previous)
        if target.exists():
            os.replace(target, previous)
            _fsync_directory(output_root)
        os.replace(staging, target)
        _fsync_directory(output_root)
        if previous.exists():
            shutil.rmtree(previous)
            _fsync_directory(output_root)
        return target
    except BaseException:
        if target.exists() is False and previous.exists():
            os.replace(previous, target)
            _fsync_directory(output_root)
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_package(package_path: Path, *, trusted_anchor: str | None = None) -> None:
    """Verify content hashes and key semantic boundaries; fail closed on tampering."""
    if trusted_anchor is not None and checksums_anchor(package_path) != trusted_anchor:
        raise AssertionError("trusted anchor does not match SHA256SUMS.json")
    recorded = json.loads((package_path / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = _checksums(package_path)
    if recorded != actual:
        raise AssertionError("package hash verification failed")
    manifest = json.loads((package_path / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("issue_slot_identity_rule") != "exact issue_code + match_idx; issue-local only":
        raise AssertionError("unexpected issue-slot mapping rule")
    if manifest.get("fixture_entity_rule") != "nullable unless provenance-backed stable event key exists":
        raise AssertionError("unexpected fixture-entity rule")
    if manifest.get("entity_resolution_rule") != "canonical entity disabled; source-local or diagnostic equality only":
        raise AssertionError("unexpected entity-resolution rule")
    if manifest.get("outcome_exposed_inputs") is not False or manifest.get("fuzzy_auto_acceptance") is not False:
        raise AssertionError("identity boundary violation")
    read_csv = lambda name: pd.read_csv(  # noqa: E731
        package_path / "tables" / name, dtype=str, keep_default_na=False
    )
    frames = {name: read_csv(name) for name in TABLE_SCHEMAS}
    for name, expected in TABLE_SCHEMAS.items():
        if set(frames[name].columns) != expected:
            raise AssertionError(f"unexpected table schema: {name}")
    if _sha256(package_path / "tables" / "source_input_snapshot.csv") != manifest.get(
        "source_input_snapshot_sha256"
    ):
        raise AssertionError("source input snapshot identity mismatch")
    result = mapping.MappingResult(
        source_inputs=frames["source_input_snapshot.csv"],
        issues=frames["issue_identity.csv"],
        slots=frames["issue_slot_identity.csv"],
        plays=frames["play_identity.csv"],
        outcome_cells=frames["outcome_cell_identity.csv"],
        traces=frames["source_trace.csv"],
        ledger=frames["ambiguity_ledger.csv"],
    )
    coverage = frames["coverage.csv"]
    alias_rows = frames["temporal_aliases.csv"]
    try:
        profile.validate_identity_tables(result)
        alias_contract.validate_alias_intervals(alias_rows)
    except ValueError as error:
        raise AssertionError(f"identity semantic verification failed: {error}") from error
    traces = result.traces
    prohibited = {"result_code", "winning_sp", "payout"}
    all_headers = set().union(*(set(frame.columns) for frame in frames.values()))
    outcome_code_elsewhere = any(
        "outcome_code" in frame.columns
        for name, frame in frames.items()
        if name != "outcome_cell_identity.csv"
    )
    if prohibited & all_headers or outcome_code_elsewhere:
        raise AssertionError("outcome-exposed trace columns are forbidden")
    if traces.duplicated(["source_id", "issue_slot_id"]).any():
        raise AssertionError("duplicate source slot escaped quarantine")
    if traces[["source_id", "source_key"]].astype(str).apply(
        lambda column: column.str.strip().eq("")
    ).any().any() or traces.duplicated(["source_id", "source_key"]).any():
        raise AssertionError("invalid source-record lineage escaped quarantine")
    for _, row in result.issues.iterrows():
        if row["issue_id"] != mapping.issue_id(str(row["issue_code"])):
            raise AssertionError("issue identity formula mismatch")
    for _, row in result.slots.iterrows():
        expected = mapping.issue_slot_id(str(row["issue_code"]), int(row["match_idx"]))
        if row["issue_slot_id"] != expected or row["fixture_entity_id"]:
            raise AssertionError("issue-slot or fixture-entity semantic mismatch")
    slot_ids = set(result.slots["issue_slot_id"])
    if not set(traces["issue_slot_id"]).issubset(slot_ids):
        raise AssertionError("trace references unknown issue slot")
    missing_entity_specs = (
        ("source_competition_key", "source_competition_entity_id", "competition_resolution_status"),
        ("source_home_team_key", "source_home_team_entity_id", "home_team_resolution_status"),
        ("source_away_team_key", "source_away_team_entity_id", "away_team_resolution_status"),
    )
    for raw_column, source_entity_column, status_column in missing_entity_specs:
        missing = traces[raw_column].astype(str).str.strip().eq("")
        invalid = missing & (
            traces[source_entity_column].astype(str).str.strip().ne("")
            | traces[status_column].ne("UNIDENTIFIED")
        )
        if invalid.any():
            raise AssertionError("missing entity label was promoted to an identity")
    canonical_columns = [
        "canonical_competition_id", "canonical_home_team_id", "canonical_away_team_id"
    ]
    if traces[canonical_columns].astype(str).apply(lambda column: column.str.strip().ne("")).any().any():
        raise AssertionError("canonical entity promotion is disabled")

    recomputed = mapping.map_records(mapping.records_from_snapshot(result.source_inputs))
    rebuilt_coverage = profile.coverage_table(recomputed).astype(str)
    output_pairs = (
        ("issue identity", result.issues, recomputed.issues),
        ("issue-slot identity", result.slots, recomputed.slots),
        ("play identity", result.plays, recomputed.plays),
        ("outcome-cell identity", result.outcome_cells, recomputed.outcome_cells),
        ("source trace", result.traces, recomputed.traces),
        ("ambiguity ledger", result.ledger, recomputed.ledger),
    )
    try:
        for label, published, expected in output_pairs:
            pd.testing.assert_frame_equal(
                published.astype(str).reset_index(drop=True),
                expected.astype(str).reset_index(drop=True),
                check_dtype=False,
            )
        pd.testing.assert_frame_equal(
            coverage.astype(str).reset_index(drop=True),
            rebuilt_coverage.reset_index(drop=True),
            check_dtype=False,
        )
        rebuilt_aliases = profile.derive_temporal_aliases(recomputed.traces).astype(str)
        pd.testing.assert_frame_equal(
            alias_rows.astype(str).reset_index(drop=True),
            rebuilt_aliases.reset_index(drop=True),
            check_dtype=False,
        )
    except AssertionError as error:
        raise AssertionError("source-snapshot semantic reconciliation failed") from error
    expected_counts = {
        "source_input_count": len(result.source_inputs),
        "issue_count": len(result.issues),
        "issue_slot_count": len(result.slots),
        "play_count": len(result.plays),
        "outcome_cell_count": len(result.outcome_cells),
        "trace_count": len(result.traces),
        "exception_count": len(result.ledger),
    }
    if any(int(manifest.get(key, -1)) != value for key, value in expected_counts.items()):
        raise AssertionError("manifest identity counts do not reconcile")
