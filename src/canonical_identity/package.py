"""Immutable, tamper-evident #251 identity evidence package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from . import mapping


PACKAGE_NAME = "bj251_canonical_identity_v1"


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
        _write_csv(result.fixtures, staging / "tables" / "fixture_identity.csv")
        _write_csv(result.traces, staging / "tables" / "source_trace.csv")
        _write_csv(result.ledger, staging / "tables" / "ambiguity_ledger.csv")
        _write_csv(coverage, staging / "tables" / "coverage.csv")
        _write_csv(aliases, staging / "tables" / "temporal_aliases.csv")
        manifest = {
            "contract_version": mapping.RULE_VERSION,
            "package": PACKAGE_NAME,
            "fixture_identity_rule": "exact (issue_code, match_idx) only",
            "outcome_exposed_inputs": False,
            "fuzzy_auto_acceptance": False,
            "fixture_count": int(len(result.fixtures)),
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
    if manifest.get("fixture_identity_rule") != "exact (issue_code, match_idx) only":
        raise AssertionError("unexpected fixture mapping rule")
    if manifest.get("outcome_exposed_inputs") is not False or manifest.get("fuzzy_auto_acceptance") is not False:
        raise AssertionError("identity boundary violation")
    traces = pd.read_csv(package_path / "tables" / "source_trace.csv", dtype=str)
    prohibited = {"result_code", "winning_sp", "outcome_code", "payout"}
    if prohibited & set(traces.columns):
        raise AssertionError("outcome-exposed trace columns are forbidden")
