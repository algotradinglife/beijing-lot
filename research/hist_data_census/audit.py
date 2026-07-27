"""Inventory-first, read-only evidence helpers for HIST-DATA-CENSUS-001.

The first phase deliberately does *not* open SQLite databases, workbooks,
CSV/JSON payloads, or capture manifests.  It records only filesystem metadata
and cryptographic identities, then freezes that public inventory.  Later census
phases must verify the frozen inventory before inspecting schema or coverage.

Local source paths and proprietary source bytes are runtime-only values.  The
public artifacts contain logical IDs, repository-relative locators, filenames,
byte counts and digests only.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.research_freeze_protocol import ResearchFreezeError, create_freeze_package, verify_freeze_package


AUDIT_ID = "HIST-DATA-CENSUS-001"
INVENTORY_EXPERIMENT_ID = "HIST-DATA-CENSUS-001-INVENTORY"
AUDIT_SCHEMA = "hist_data_census_v1"
INVENTORY_SCHEMA = "hist_data_census_inventory_v1"
ROOT = Path(__file__).resolve().parents[2]

FULL_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
LOGICAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
ABSOLUTE_PATH_RE = re.compile(r"(?:^|[\"'\s])(?:/[A-Za-z0-9_.~/-]+|[A-Za-z]:[\\/][^\"'\s]*)")
SENSITIVE_NAME_RE = re.compile(r"(?:credential|cookie|password|secret|token|private[_-]?key)", re.IGNORECASE)

DATA_FILE_SUFFIXES = frozenset({".csv", ".db", ".json", ".jsonl", ".parquet", ".sqlite", ".xlsm", ".xlsx"})
SQLITE_SIDECAR_SUFFIXES = ("-journal", "-shm", "-wal")
DISCOVERY_ROOTS: tuple[tuple[str, str, str], ...] = (
    ("repo_data", "data", "repository_data_tree"),
    ("data_collection", "results/data_collection", "immutable_capture_bundle_tree"),
    ("research_artifacts", "results/research", "research_artifact_bundle_tree"),
    ("freeze_packages", "results/freeze", "research_freeze_bundle_tree"),
)
BUNDLE_ROOT_IDS = frozenset({"data_collection", "research_artifacts", "freeze_packages"})
INVENTORY_COLUMNS = (
    "logical_asset_id",
    "logical_source_id",
    "source_group",
    "asset_kind",
    "repository_locator",
    "filename",
    "availability",
    "identity_method",
    "bytes",
    "sha256",
    "bundle_file_count",
    "excluded_reason",
    "inventory_scope_note",
)
SENSITIVE_PUBLIC_KEYS = frozenset({
    "absolute_path",
    "credential",
    "credentials",
    "password",
    "private_url",
    "raw_payload",
    "raw_source_bytes",
    "secret",
    "source_bytes",
    "token",
    "vba_source",
})


class CensusError(ValueError):
    """Raised when an inventory or evidence-boundary invariant is violated."""


@dataclass(frozen=True)
class RuntimeInput:
    """A private runtime source referred to publicly only by a logical ID."""

    logical_id: str
    kind: str
    path: Path


def canonical_json(value: Any) -> str:
    """Render public JSON deterministically."""

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a regular file without retaining its contents."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _full_git_commit(value: str) -> str:
    if not FULL_GIT_COMMIT_RE.fullmatch(value):
        raise CensusError("census evidence requires a full 40-character lowercase git commit")
    return value


def _safe_logical_id(value: str) -> str:
    if not LOGICAL_ID_RE.fullmatch(value):
        raise CensusError("runtime input logical ID must be a short safe identifier")
    return value


def parse_runtime_input(value: str, *, kind: str = "runtime_source") -> RuntimeInput:
    """Parse ``logical_id=runtime_path`` without serializing the private path."""

    logical_id, separator, raw_path = value.partition("=")
    if separator != "=" or not raw_path:
        raise CensusError("runtime input must use logical_id=path")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file() or path.is_symlink():
        raise CensusError("runtime input must resolve to a readable regular file")
    return RuntimeInput(logical_id=_safe_logical_id(logical_id), kind=kind, path=path)


def main_repository_root(worktree_root: Path = ROOT) -> Path:
    """Resolve the shared main repository root from a worktree safely.

    ``git rev-parse --show-toplevel`` points to the *worktree*; source data are
    intentionally kept in the common repository root.  The common git dir is
    therefore the only authority used here.
    """

    root = worktree_root.expanduser().resolve()
    try:
        raw_common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CensusError("unable to resolve git common directory") from exc
    common = Path(raw_common)
    if not common.is_absolute():
        common = (root / common).resolve()
    if common.name != ".git":
        raise CensusError("git common directory does not identify a repository root")
    return common.parent


def _safe_locator(value: Path) -> str:
    """Return a stable public locator that can never be an absolute path."""

    locator = value.as_posix().lstrip("./")
    if not locator or locator.startswith("/") or ".." in Path(locator).parts:
        raise CensusError("unsafe repository-relative locator")
    return locator


def _asset_id(root_id: str, relative: Path) -> str:
    raw_relative = relative.as_posix()
    slug = "root" if raw_relative in {"", "."} else re.sub(r"[^A-Za-z0-9]+", "-", raw_relative).strip("-").lower()
    if not slug:
        raise CensusError("empty logical source locator")
    return f"{root_id}:{slug}"


def _regular_file_metadata(path: Path) -> tuple[int, str]:
    if path.is_symlink() or not path.is_file():
        raise CensusError("source identity requires a regular non-symlink file")
    return path.stat().st_size, sha256_file(path)


def _is_sensitive_name(path: Path) -> bool:
    return any(SENSITIVE_NAME_RE.search(part) is not None for part in path.parts)


def _asset_kind(path: Path) -> str:
    name = path.name.casefold()
    if name.endswith(SQLITE_SIDECAR_SUFFIXES):
        return "sqlite_sidecar"
    suffix = path.suffix.casefold()
    return {
        ".sqlite": "sqlite_database",
        ".db": "sqlite_database",
        ".xlsm": "vendor_workbook",
        ".xlsx": "workbook",
        ".csv": "tabular_export",
        ".parquet": "tabular_export",
        ".json": "json_artifact",
        ".jsonl": "json_artifact",
    }.get(suffix, "runtime_or_auxiliary_file")


def _candidate_file(path: Path) -> bool:
    name = path.name.casefold()
    return path.suffix.casefold() in DATA_FILE_SUFFIXES or name.endswith(SQLITE_SIDECAR_SUFFIXES)


def _file_row(
    *,
    root_id: str,
    source_group: str,
    relative_to_repo: Path,
    source_relative: Path,
    path: Path,
) -> dict[str, Any]:
    """Create a metadata-only file identity row; never inspect file semantics."""

    locator = _safe_locator(relative_to_repo)
    row: dict[str, Any] = {
        "logical_asset_id": _asset_id(root_id, source_relative),
        "logical_source_id": root_id,
        "source_group": source_group,
        "asset_kind": _asset_kind(path),
        "repository_locator": locator,
        "filename": path.name,
        "availability": "PRESENT",
        "identity_method": "sha256_regular_file_metadata_only",
        "bytes": "",
        "sha256": "",
        "bundle_file_count": "",
        "excluded_reason": "",
        "inventory_scope_note": "identity only; payload/schema/coverage intentionally unopened in inventory phase",
    }
    if _is_sensitive_name(source_relative):
        row.update(
            {
                "availability": "EXCLUDED_SENSITIVE",
                "identity_method": "name_only_sensitive_exclusion",
                "excluded_reason": "sensitive_runtime_configuration_or_credential_out_of_scope",
                "inventory_scope_note": "sensitive filename recorded without hashing or opening source",
            }
        )
        return row
    if not _candidate_file(path):
        row.update(
            {
                "availability": "OUT_OF_SCOPE_AUXILIARY",
                "identity_method": "name_and_stat_only",
                "excluded_reason": "not_a_discoverable_tabular_workbook_database_or_sqlite_sidecar_candidate",
            }
        )
        return row
    byte_count, digest = _regular_file_metadata(path)
    row["bytes"] = byte_count
    row["sha256"] = digest
    return row


def _walk_regular_files(root: Path) -> Iterable[Path]:
    """Yield source files deterministically without following links or opening them."""

    for directory, names, files in os.walk(root, followlinks=False):
        names.sort()
        files.sort()
        base = Path(directory)
        for filename in files:
            candidate = base / filename
            if candidate.is_symlink() or not candidate.is_file():
                continue
            yield candidate


def _missing_root_row(root_id: str, relative_root: str, source_group: str) -> dict[str, Any]:
    return {
        "logical_asset_id": f"{root_id}:root",
        "logical_source_id": root_id,
        "source_group": source_group,
        "asset_kind": "discovery_root",
        "repository_locator": relative_root,
        "filename": "",
        "availability": "MISSING",
        "identity_method": "deterministic_missing_root",
        "bytes": "",
        "sha256": "",
        "bundle_file_count": "",
        "excluded_reason": "configured_discovery_root_absent",
        "inventory_scope_note": "no files inspected because configured root is absent",
    }


def _bundle_metadata_row(
    *,
    root_id: str,
    source_group: str,
    repository_root: Path,
    bundle_root: Path,
) -> dict[str, Any]:
    """Represent an immutable bundle through its manifest/checksum identities.

    The bundle payload itself remains unopened during the required pre-coverage
    inventory freeze.  A later audit can verify each ``SHA256SUMS`` exactly.
    """

    relative_to_repo = bundle_root.relative_to(repository_root)
    metadata: list[dict[str, Any]] = []
    total_files = 0
    for candidate in _walk_regular_files(bundle_root):
        total_files += 1
        if candidate.name in {"manifest.json", "SHA256SUMS"} and candidate.parent == bundle_root:
            byte_count, digest = _regular_file_metadata(candidate)
            metadata.append({"filename": candidate.name, "bytes": byte_count, "sha256": digest})
    metadata.sort(key=lambda item: str(item["filename"]))
    if not metadata:
        raise CensusError("bundle record requires manifest.json or SHA256SUMS metadata")
    root_relative = Path(next(item[1] for item in DISCOVERY_ROOTS if item[0] == root_id))
    return {
        "logical_asset_id": _asset_id(root_id, relative_to_repo.relative_to(root_relative)),
        "logical_source_id": root_id,
        "source_group": source_group,
        "asset_kind": "immutable_bundle",
        "repository_locator": _safe_locator(relative_to_repo),
        "filename": bundle_root.name,
        "availability": "PRESENT_BUNDLE_METADATA_ONLY",
        "identity_method": "sha256_manifest_and_or_sha256sums_metadata_only",
        "bytes": sum(int(item["bytes"]) for item in metadata),
        "sha256": sha256_bytes(canonical_bytes(metadata)),
        "bundle_file_count": total_files,
        "excluded_reason": "",
        "inventory_scope_note": "bundle payload and manifest contents intentionally unopened before inventory freeze",
    }


def _bundle_roots(root: Path) -> list[Path]:
    """Find each manifest/checksum directory without opening its contents."""

    roots: set[Path] = set()
    for candidate in _walk_regular_files(root):
        if candidate.name in {"manifest.json", "SHA256SUMS"}:
            roots.add(candidate.parent)
    return sorted(roots, key=lambda item: item.as_posix())


def _runtime_row(item: RuntimeInput) -> dict[str, Any]:
    byte_count, digest = _regular_file_metadata(item.path)
    return {
        "logical_asset_id": f"runtime:{item.logical_id}",
        "logical_source_id": item.logical_id,
        "source_group": "runtime_supplied_source",
        "asset_kind": item.kind,
        "repository_locator": f"runtime:{item.logical_id}",
        "filename": item.path.name,
        "availability": "PRESENT",
        "identity_method": "sha256_runtime_regular_file_metadata_only",
        "bytes": byte_count,
        "sha256": digest,
        "bundle_file_count": "",
        "excluded_reason": "",
        "inventory_scope_note": "runtime path redacted; payload/schema/coverage intentionally unopened in inventory phase",
    }


def build_source_inventory(
    *,
    repository_root: Path,
    runtime_inputs: Sequence[RuntimeInput] = (),
) -> list[dict[str, Any]]:
    """Build the mandated G0 inventory without parsing source data.

    This function must remain free of database, workbook, CSV and JSON parsing.
    It is intentionally the only source-discovery API that can run before a
    frozen inventory package exists.
    """

    source_root = repository_root.expanduser().resolve()
    if not source_root.is_dir():
        raise CensusError("repository source root must be a directory")
    rows: list[dict[str, Any]] = []
    seen_runtime_ids: set[str] = set()
    for item in sorted(runtime_inputs, key=lambda candidate: (candidate.kind, candidate.logical_id)):
        if item.logical_id in seen_runtime_ids:
            raise CensusError("duplicate runtime input logical ID")
        seen_runtime_ids.add(item.logical_id)
        rows.append(_runtime_row(item))

    for root_id, relative_root, source_group in DISCOVERY_ROOTS:
        absolute_root = source_root / relative_root
        if not absolute_root.is_dir() or absolute_root.is_symlink():
            rows.append(_missing_root_row(root_id, relative_root, source_group))
            continue
        if root_id in BUNDLE_ROOT_IDS:
            bundle_roots = _bundle_roots(absolute_root)
            if not bundle_roots:
                rows.append(
                    {
                        **_missing_root_row(root_id, relative_root, source_group),
                        "availability": "PRESENT_NO_BUNDLE_METADATA",
                        "identity_method": "directory_name_metadata_only",
                        "excluded_reason": "no_manifest_json_or_sha256sums_discovered",
                        "inventory_scope_note": "root exists; no immutable bundle metadata was discovered before coverage inspection",
                    }
                )
            rows.extend(
                _bundle_metadata_row(
                    root_id=root_id,
                    source_group=source_group,
                    repository_root=source_root,
                    bundle_root=bundle,
                )
                for bundle in bundle_roots
            )
            continue
        for candidate in _walk_regular_files(absolute_root):
            rows.append(
                _file_row(
                    root_id=root_id,
                    source_group=source_group,
                    relative_to_repo=candidate.relative_to(source_root),
                    source_relative=candidate.relative_to(absolute_root),
                    path=candidate,
                )
            )
    if not rows:
        raise CensusError("source inventory unexpectedly contains no discoverable roots or runtime inputs")
    rows.sort(key=lambda item: (str(item["logical_source_id"]), str(item["repository_locator"]), str(item["logical_asset_id"])))
    duplicates = [
        item["logical_asset_id"]
        for index, item in enumerate(rows[1:], start=1)
        if item["logical_asset_id"] == rows[index - 1]["logical_asset_id"]
    ]
    if duplicates:
        raise CensusError("source inventory has duplicate logical asset IDs")
    return rows


def inventory_identity(rows: Sequence[Mapping[str, Any]]) -> str:
    """Return the stable identity of the public source inventory."""

    normalized = [
        {
            column: "" if row.get(column) is None else str(row.get(column, ""))
            for column in INVENTORY_COLUMNS
        }
        for row in rows
    ]
    return sha256_bytes(canonical_bytes(normalized))


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != INVENTORY_COLUMNS:
            raise CensusError("source inventory CSV schema does not match the census contract")
        return [dict(row) for row in reader]


def _inventory_config() -> dict[str, Any]:
    return {
        "schema_version": INVENTORY_SCHEMA,
        "audit_id": AUDIT_ID,
        "phase": "G0_PRE_COVERAGE_INVENTORY",
        "read_only": True,
        "source_payloads_opened": False,
        "database_connections_opened": False,
        "workbook_macros_executed": False,
        "model_or_backtest_enabled": False,
        "roi_authorized": False,
        "public_source_paths": False,
        "public_source_bytes": False,
    }


def _inventory_decision(rows: Sequence[Mapping[str, Any]], *, git_commit: str) -> dict[str, Any]:
    return {
        "schema_version": INVENTORY_SCHEMA,
        "audit_id": AUDIT_ID,
        "phase": "G0_PRE_COVERAGE_INVENTORY_FROZEN",
        "git_commit": _full_git_commit(git_commit),
        "source_inventory_sha256": inventory_identity(rows),
        "coverage_or_schema_inspected": False,
        "next_permitted_phase": "READ_ONLY_SCHEMA_AND_COVERAGE_AUDIT_AFTER_INVENTORY_VERIFICATION",
    }


def _inventory_receipt(rows: Sequence[Mapping[str, Any]], *, git_commit: str) -> dict[str, Any]:
    return {
        "schema_version": INVENTORY_SCHEMA,
        "audit_id": AUDIT_ID,
        "command_template": (
            "python scripts/run_hist_data_census.py inventory --source-root <main-repository-root> "
            "--runtime-input <logical_id>=<runtime-source> --output-dir <new-inventory-output> "
            "--freeze-dir <new-inventory-freeze> --frozen-at-utc <explicit-UTC>"
        ),
        "git_commit": _full_git_commit(git_commit),
        "source_inventory_sha256": inventory_identity(rows),
        "source_count": len(rows),
        "inventory_precedes_coverage_inspection": True,
        "public_redaction_verified": True,
        "note": "Only logical IDs, repository-relative locators, filenames, byte counts and digests are public.",
    }


def _walk_public(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key), child
            yield from _walk_public(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from _walk_public(child)


def assert_public_redaction(value: Any, *, private_paths: Iterable[Path] = ()) -> None:
    """Reject absolute local paths, sensitive fields and private runtime paths."""

    rendered = canonical_json(value)
    for private_path in private_paths:
        if str(private_path) in rendered:
            raise CensusError("public artifact leaks a private runtime source path")
    if ABSOLUTE_PATH_RE.search(rendered):
        raise CensusError("public artifact appears to contain an absolute local path")
    for key, _ in _walk_public(value):
        if key is not None and key.casefold() in SENSITIVE_PUBLIC_KEYS:
            raise CensusError("public artifact contains a sensitive source field")


def write_inventory_artifacts(
    output_dir: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    git_commit: str,
    runtime_inputs: Sequence[RuntimeInput] = (),
) -> dict[str, Path]:
    """Write the public G0 artifacts that are frozen before data inspection."""

    _full_git_commit(git_commit)
    result = {
        "source_inventory.csv": output_dir / "source_inventory.csv",
        "inventory_freeze_decision.json": output_dir / "inventory_freeze_decision.json",
        "census_config.json": output_dir / "census_config.json",
        "inventory_receipt.json": output_dir / "inventory_receipt.json",
    }
    _write_csv(result["source_inventory.csv"], rows, INVENTORY_COLUMNS)
    decision = _inventory_decision(rows, git_commit=git_commit)
    config = _inventory_config()
    receipt = _inventory_receipt(rows, git_commit=git_commit)
    for payload in (decision, config, receipt):
        assert_public_redaction(payload, private_paths=[item.path for item in runtime_inputs])
    assert_public_redaction(rows, private_paths=[item.path for item in runtime_inputs])
    result["inventory_freeze_decision.json"].write_text(canonical_json(decision), encoding="utf-8")
    result["census_config.json"].write_text(canonical_json(config), encoding="utf-8")
    result["inventory_receipt.json"].write_text(canonical_json(receipt), encoding="utf-8")
    return result


def create_inventory_package(
    artifact_paths: Mapping[str, Path],
    *,
    output_dir: Path,
    git_commit: str,
    frozen_at_utc: str,
) -> dict[str, Any]:
    """Create an immutable G0 package, bound to an exact source inventory."""

    _full_git_commit(git_commit)
    required = {
        "source_inventory.csv",
        "inventory_freeze_decision.json",
        "census_config.json",
        "inventory_receipt.json",
    }
    if set(artifact_paths) != required or any(not artifact_paths[name].is_file() for name in required):
        raise CensusError("inventory package requires the complete G0 artifact set")
    rows = _read_csv(artifact_paths["source_inventory.csv"])
    decision = json.loads(artifact_paths["inventory_freeze_decision.json"].read_text(encoding="utf-8"))
    receipt = json.loads(artifact_paths["inventory_receipt.json"].read_text(encoding="utf-8"))
    if decision.get("source_inventory_sha256") != inventory_identity(rows):
        raise CensusError("inventory freeze decision does not bind the source inventory")
    if receipt.get("source_inventory_sha256") != inventory_identity(rows):
        raise CensusError("inventory receipt does not bind the source inventory")
    if decision.get("git_commit") != git_commit or receipt.get("git_commit") != git_commit:
        raise CensusError("inventory receipt must bind the exact full git commit")
    try:
        return create_freeze_package(
            output_dir,
            experiment_id=INVENTORY_EXPERIMENT_ID,
            research_question="Which long-horizon historical source candidates exist before any schema or coverage inspection?",
            model_version="hist-data-census-inventory-v1",
            input_files=[artifact_paths["source_inventory.csv"]],
            decision_files=[artifact_paths["inventory_freeze_decision.json"]],
            config_file=artifact_paths["census_config.json"],
            metadata_files=[artifact_paths["inventory_receipt.json"]],
            git_commit=git_commit,
            frozen_at_utc=frozen_at_utc,
        )
    except ResearchFreezeError as exc:
        raise CensusError(str(exc)) from exc


def verify_inventory_package(
    package_dir: Path,
    *,
    repository_root: Path | None = None,
    runtime_inputs: Sequence[RuntimeInput] = (),
    verify_current_sources: bool = True,
) -> dict[str, Any]:
    """Verify package hashes and optionally fail closed on source identity drift."""

    package = package_dir.expanduser().resolve()
    try:
        verify_freeze_package(package)
    except ResearchFreezeError as exc:
        raise CensusError(str(exc)) from exc
    try:
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CensusError("inventory package manifest is invalid") from exc
    if manifest.get("experiment_id") != INVENTORY_EXPERIMENT_ID:
        raise CensusError("not a HIST-DATA-CENSUS-001 inventory package")
    git_commit = str(manifest.get("git_commit", ""))
    _full_git_commit(git_commit)
    source_inventory = package / "inputs" / "source_inventory.csv"
    decision_path = package / "decision" / "inventory_freeze_decision.json"
    receipt_path = package / "metadata" / "files" / "inventory_receipt.json"
    config_path = package / "metadata" / "config" / "census_config.json"
    rows = _read_csv(source_inventory)
    try:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CensusError("inventory package contains invalid public JSON") from exc
    expected_identity = inventory_identity(rows)
    if decision.get("source_inventory_sha256") != expected_identity or receipt.get("source_inventory_sha256") != expected_identity:
        raise CensusError("inventory package source identity mismatch")
    if decision.get("git_commit") != git_commit or receipt.get("git_commit") != git_commit:
        raise CensusError("inventory package full git commit binding mismatch")
    if config != _inventory_config():
        raise CensusError("inventory package config does not preserve the G0 boundary")
    assert_public_redaction(rows)
    assert_public_redaction(decision)
    assert_public_redaction(receipt)
    assert_public_redaction(config)
    result = {
        "status": "valid",
        "audit_id": AUDIT_ID,
        "phase": "G0_PRE_COVERAGE_INVENTORY_FROZEN",
        "git_commit": git_commit,
        "source_inventory_sha256": expected_identity,
        "source_count": len(rows),
        "current_source_identity_verified": False,
    }
    if verify_current_sources:
        if repository_root is None:
            raise CensusError("repository root is required when verifying current source identities")
        observed = build_source_inventory(repository_root=repository_root, runtime_inputs=runtime_inputs)
        if inventory_identity(observed) != expected_identity:
            raise CensusError("current runtime source inventory differs from frozen G0 inventory")
        result["current_source_identity_verified"] = True
    return result
