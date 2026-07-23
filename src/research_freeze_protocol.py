"""Generic immutable research freeze, settlement, and review packages.

This module deliberately contains no betting, model, or database logic.  It
turns already-selected inputs and decisions into auditable file packages, then
allows later settlement and review packages to reference those frozen bytes
without modifying them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FREEZE_ROOT = ROOT / "results/freeze"
DEFAULT_SETTLEMENT_ROOT = ROOT / "results/settlement"
DEFAULT_REVIEW_ROOT = ROOT / "results/review"
FREEZE_SCHEMA = "beijing_lot_research_freeze_v1"
SETTLEMENT_SCHEMA = "beijing_lot_research_settlement_v1"
REVIEW_SCHEMA = "beijing_lot_research_review_v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ResearchFreezeError(ValueError):
    """Raised when a freeze lifecycle invariant is violated."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a regular file without loading it all in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def asset_list_sha256(assets: Iterable[Mapping[str, Any]]) -> str:
    """Hash package identities, excluding workstation-local source paths."""

    return canonical_sha256(
        [
            {"path": asset["path"], "bytes": asset["bytes"], "sha256": asset["sha256"]}
            for asset in assets
        ]
    )


def _asset_digest_list(assets: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"path": asset["path"], "bytes": asset["bytes"], "sha256": asset["sha256"]}
        for asset in assets
    ]


def freeze_identity_sha256(
    *,
    experiment_id: str,
    research_question: str,
    model_version: str,
    frozen_at_utc: str,
    git_commit: str,
    inputs: Iterable[Mapping[str, Any]],
    predictions: Iterable[Mapping[str, Any]] = (),
    decisions: Iterable[Mapping[str, Any]],
    config: Mapping[str, Any],
    metadata: Iterable[Mapping[str, Any]],
    input_datasets: Iterable[Mapping[str, Any]] = (),
) -> str:
    """Return the portable identity of every immutable freeze input."""

    prediction_assets = _asset_digest_list(predictions)
    identity = {
        "experiment_id": experiment_id,
        "research_question": research_question,
        "model_version": model_version,
        "frozen_at_utc": frozen_at_utc,
        "git_commit": git_commit,
        "inputs_sha256": asset_list_sha256(inputs),
        "decisions_sha256": asset_list_sha256(decisions),
        "config_sha256": asset_list_sha256([config]),
        "metadata_sha256": asset_list_sha256(metadata),
    }
    if prediction_assets:
        identity["predictions_sha256"] = asset_list_sha256(prediction_assets)
    dataset_assets = _asset_digest_list(input_datasets)
    if dataset_assets:
        identity["input_datasets_sha256"] = asset_list_sha256(dataset_assets)
    return canonical_sha256(
        identity
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def explicit_utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ResearchFreezeError("timestamp must include an explicit timezone")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def current_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResearchFreezeError("unable to resolve the current git commit; pass --git-commit") from exc


def _safe_relative_name(name: str) -> str:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ResearchFreezeError(f"unsafe package path: {name!r}")
    return candidate.as_posix()


def _is_flat_metadata_path(path: str) -> bool:
    return path.startswith("metadata/") and "/" not in path.removeprefix("metadata/")


def _is_config_metadata_path(path: str) -> bool:
    return path.startswith("metadata/config/")


def _is_auxiliary_metadata_path(path: str) -> bool:
    return path.startswith("metadata/files/") or _is_flat_metadata_path(path)


def safe_protocol_id(value: str, label: str) -> str:
    """Return an ID that is safe to use as one default package path component."""

    candidate = value.strip()
    if (
        not candidate
        or candidate != value
        or candidate in {".", ".."}
        or "/" in candidate
        or "\\" in candidate
        or Path(candidate).is_absolute()
        or len(Path(candidate).parts) != 1
    ):
        raise ResearchFreezeError(f"{label} must be a safe single path component")
    return candidate


def _require_regular_source(path: Path) -> Path:
    source = path.expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise ResearchFreezeError(f"source must be a regular file: {path}")
    return source


def _copy_assets(stage: Path, directory: str, sources: Iterable[Path]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    used: set[str] = set()
    for index, item in enumerate(sources, start=1):
        source = _require_regular_source(item)
        base = source.name
        target_name = base if base not in used else f"{index:03d}_{base}"
        used.add(target_name)
        relative = f"{directory}/{target_name}"
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        assets.append(
            {
                "path": relative,
                "bytes": target.stat().st_size,
                "sha256": sha256_file(target),
            }
        )
    if not assets:
        raise ResearchFreezeError(f"at least one {directory} source is required")
    return assets


def _copy_optional_assets(stage: Path, directory: str, sources: Iterable[Path]) -> list[dict[str, Any]]:
    optional_sources = tuple(sources)
    if not optional_sources:
        return []
    return _copy_assets(stage, directory, optional_sources)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _package_files(package: Path, allowed_roots: set[str]) -> set[str]:
    files: set[str] = set()
    for candidate in package.rglob("*"):
        if candidate.is_symlink():
            raise ResearchFreezeError(f"package contains a non-regular file: {candidate}")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise ResearchFreezeError(f"package contains a non-regular file: {candidate}")
        relative = candidate.relative_to(package).as_posix()
        top_level = relative.split("/", 1)[0]
        if relative not in {"manifest.json", "SHA256SUMS"} and top_level not in allowed_roots:
            raise ResearchFreezeError(f"unexpected package file: {relative}")
        files.add(relative)
    return files


def _write_sums(package: Path, allowed_roots: set[str]) -> None:
    names = sorted(_package_files(package, allowed_roots) - {"SHA256SUMS"})
    (package / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(package / name)}  {name}\n" for name in names), encoding="utf-8"
    )


def _verify_sums(package: Path, allowed_roots: set[str]) -> dict[str, str]:
    sums = package / "SHA256SUMS"
    if not sums.is_file():
        raise ResearchFreezeError(f"SHA256SUMS missing: {package}")
    entries: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise ResearchFreezeError(f"invalid SHA256SUMS line: {line!r}") from exc
        name = _safe_relative_name(name)
        if not SHA256_RE.fullmatch(digest) or name in entries:
            raise ResearchFreezeError(f"invalid SHA256SUMS entry: {line!r}")
        target = package / name
        if not target.is_file() or target.is_symlink() or sha256_file(target) != digest:
            raise ResearchFreezeError(f"checksum mismatch: {target}")
        entries[name] = digest
    actual = _package_files(package, allowed_roots) - {"SHA256SUMS"}
    if set(entries) != actual:
        raise ResearchFreezeError("SHA256SUMS does not cover exactly the immutable package files")
    return entries


def _verify_asset_list(
    package: Path, assets: Any, directory: str, *, required: bool = True
) -> list[dict[str, Any]]:
    if not isinstance(assets, list) or (required and not assets):
        raise ResearchFreezeError(f"{directory} asset list is missing or empty")
    verified: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            raise ResearchFreezeError(f"invalid {directory} asset entry")
        path = asset.get("path")
        digest = asset.get("sha256")
        if not isinstance(path, str) or not path.startswith(f"{directory}/"):
            raise ResearchFreezeError(f"invalid {directory} asset path")
        _safe_relative_name(path)
        target = package / path
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest) or not target.is_file():
            raise ResearchFreezeError(f"invalid {directory} asset digest")
        if sha256_file(target) != digest or target.stat().st_size != asset.get("bytes"):
            raise ResearchFreezeError(f"{directory} asset mismatch: {path}")
        verified.append(asset)
    return verified


def _manifest_asset_paths(*asset_groups: Iterable[Mapping[str, Any]], config: Mapping[str, Any]) -> set[str]:
    paths = {"manifest.json", str(config["path"])}
    for assets in asset_groups:
        paths.update(str(asset["path"]) for asset in assets)
    return paths


def _fsync_tree(path: Path) -> None:
    for item in sorted(path.rglob("*")):
        if item.is_file():
            with item.open("rb") as handle:
                os.fsync(handle.fileno())
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_publish(final: Path, builder: Any, verifier: Any) -> dict[str, Any]:
    final = final.expanduser().resolve()
    if final.exists():
        raise FileExistsError(f"immutable package already exists: {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.tmp-", dir=final.parent))
    try:
        builder(stage)
        result = verifier(stage)
        _fsync_tree(stage)
        stage.rename(final)
        result["package_dir"] = str(final)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _ensure_outside(output: Path, protected: Path) -> None:
    try:
        output.expanduser().resolve().relative_to(protected.expanduser().resolve())
    except ValueError:
        return
    raise ResearchFreezeError("downstream package must not be written inside the immutable freeze package")


def create_freeze_package(
    output_dir: Path,
    *,
    experiment_id: str,
    research_question: str,
    model_version: str,
    input_files: Iterable[Path],
    decision_files: Iterable[Path],
    config_file: Path,
    prediction_files: Iterable[Path] = (),
    decision_directory: str = "decision",
    metadata_files: Iterable[Path] = (),
    input_datasets: Iterable[Path] = (),
    git_commit: str | None = None,
    frozen_at_utc: str | None = None,
) -> dict[str, Any]:
    """Atomically create an immutable freeze package from pre-selected files."""

    experiment_id = safe_protocol_id(experiment_id, "experiment ID")
    if not research_question.strip() or not model_version.strip():
        raise ResearchFreezeError("research question and model version are required")
    decision_directory = _safe_relative_name(decision_directory)
    if decision_directory not in {"decision", "decisions"}:
        raise ResearchFreezeError("decision directory must be either 'decision' or 'decisions'")
    commit = git_commit or current_git_commit()
    if not re.fullmatch(r"[0-9a-f]{7,64}", commit):
        raise ResearchFreezeError("git commit must be a hexadecimal commit identifier")
    frozen_at = explicit_utc(frozen_at_utc) if frozen_at_utc else utc_now()
    metadata_sources = tuple(metadata_files)
    dataset_sources = tuple(Path(path) for path in input_datasets)
    datasets = [
        {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in dataset_sources
    ]

    def build(stage: Path) -> None:
        inputs = _copy_assets(stage, "inputs", input_files)
        predictions = _copy_optional_assets(stage, "predictions", prediction_files)
        decisions = _copy_assets(stage, decision_directory, decision_files)
        config = _copy_assets(stage, "metadata/config", [config_file])[0]
        metadata = _copy_assets(stage, "metadata/files", metadata_sources) if metadata_sources else []
        # The package identity covers every frozen byte, without storing local source paths.
        freeze_id = freeze_identity_sha256(
            experiment_id=experiment_id,
            research_question=research_question,
            model_version=model_version,
            frozen_at_utc=frozen_at,
            git_commit=commit,
            inputs=inputs,
            predictions=predictions,
            decisions=decisions,
            config=config,
            metadata=metadata,
            input_datasets=datasets,
        )
        manifest = {
            "schema_version": FREEZE_SCHEMA,
            "lifecycle_state": "FROZEN",
            "experiment_id": experiment_id,
            "freeze_id": freeze_id,
            "frozen_at_utc": frozen_at,
            "git_commit": commit,
            "model_version": model_version,
            "research_question": research_question,
            "dataset_snapshot": {"files": inputs, "data_sha256": asset_list_sha256(inputs)},
            "input_dataset": datasets,
            "prediction_files": predictions,
            "prediction_sha256": asset_list_sha256(predictions) if predictions else None,
            "config": config,
            "metadata_files": metadata,
            "frozen_decisions": decisions,
            "decision_sha256": asset_list_sha256(decisions),
            "execution_enabled": False,
            "frontend_selectable": False,
            "roi_authorized": False,
            "protocol_notice": "Frozen decisions are immutable. Settlement and review packages may reference this package but must not modify it.",
        }
        _write_json(stage / "manifest.json", manifest)
        allowed_roots = {"inputs", decision_directory, "metadata"}
        if predictions:
            allowed_roots.add("predictions")
        _write_sums(stage, allowed_roots)

    return _atomic_publish(output_dir, build, verify_freeze_package)


def verify_freeze_package(path: Path) -> dict[str, Any]:
    package = path.expanduser().resolve()
    try:
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchFreezeError("invalid freeze manifest") from exc
    required = {"schema_version", "lifecycle_state", "experiment_id", "freeze_id", "frozen_at_utc", "git_commit",
                "model_version", "research_question", "dataset_snapshot", "config", "metadata_files", "frozen_decisions", "decision_sha256"}
    if not required.issubset(manifest) or manifest.get("schema_version") != FREEZE_SCHEMA:
        raise ResearchFreezeError("unsupported or incomplete freeze manifest")
    if manifest.get("lifecycle_state") != "FROZEN":
        raise ResearchFreezeError("freeze manifest is not in FROZEN state")
    explicit_utc(str(manifest["frozen_at_utc"]))
    if not re.fullmatch(r"[0-9a-f]{7,64}", str(manifest["git_commit"])):
        raise ResearchFreezeError("invalid freeze git commit")
    snapshot = manifest["dataset_snapshot"]
    if not isinstance(snapshot, dict):
        raise ResearchFreezeError("invalid dataset snapshot")
    decisions_payload = manifest.get("frozen_decisions")
    if not isinstance(decisions_payload, list) or not decisions_payload:
        raise ResearchFreezeError("decision asset list is missing or empty")
    decision_paths = [asset.get("path") if isinstance(asset, dict) else None for asset in decisions_payload]
    if all(isinstance(path, str) and path.startswith("decision/") for path in decision_paths):
        decision_directory = "decision"
    elif all(isinstance(path, str) and path.startswith("decisions/") for path in decision_paths):
        decision_directory = "decisions"
    else:
        raise ResearchFreezeError("frozen decision assets must stay under one decision directory")
    prediction_payload = manifest.get("prediction_files", [])
    if not isinstance(prediction_payload, list):
        raise ResearchFreezeError("prediction asset list is invalid")
    allowed_roots = {"inputs", decision_directory, "metadata"}
    if prediction_payload:
        allowed_roots.add("predictions")
    entries = _verify_sums(package, allowed_roots)
    inputs = _verify_asset_list(package, snapshot.get("files"), "inputs")
    decisions = _verify_asset_list(package, decisions_payload, decision_directory)
    predictions = _verify_asset_list(package, prediction_payload, "predictions", required=False)
    config = _verify_asset_list(package, [manifest.get("config")], "metadata")[0]
    metadata = _verify_asset_list(package, manifest.get("metadata_files", []), "metadata", required=False)
    input_datasets = manifest.get("input_dataset", [])
    if not isinstance(input_datasets, list) or any(
        not isinstance(dataset, Mapping)
        or set(dataset) != {"path", "bytes", "sha256"}
        or not isinstance(dataset["path"], str)
        or not isinstance(dataset["bytes"], int)
        or dataset["bytes"] < 0
        or not isinstance(dataset["sha256"], str)
        or not SHA256_RE.fullmatch(dataset["sha256"])
        for dataset in input_datasets
    ):
        raise ResearchFreezeError("invalid input dataset records")
    if not _is_config_metadata_path(config["path"]):
        raise ResearchFreezeError("config file must be stored under metadata/config")
    if any(not _is_auxiliary_metadata_path(asset["path"]) for asset in metadata):
        raise ResearchFreezeError("metadata files must be stored under metadata/files")
    if config in metadata:
        raise ResearchFreezeError("config file must not be duplicated in metadata_files")
    expected_manifest_files = _manifest_asset_paths(inputs, predictions, decisions, metadata, config=config)
    if set(entries) != expected_manifest_files:
        raise ResearchFreezeError("SHA256SUMS contains files not declared by the freeze manifest")
    if snapshot.get("data_sha256") != asset_list_sha256(inputs):
        raise ResearchFreezeError("dataset snapshot digest mismatch")
    prediction_sha256 = manifest.get("prediction_sha256")
    if predictions and prediction_sha256 != asset_list_sha256(predictions):
        raise ResearchFreezeError("prediction digest mismatch")
    if not predictions and prediction_sha256 is not None:
        raise ResearchFreezeError("prediction digest mismatch")
    if manifest.get("decision_sha256") != asset_list_sha256(decisions):
        raise ResearchFreezeError("frozen decision digest mismatch")
    expected_freeze_id = freeze_identity_sha256(
        experiment_id=manifest["experiment_id"],
        research_question=manifest["research_question"],
        model_version=manifest["model_version"],
        frozen_at_utc=manifest["frozen_at_utc"],
        git_commit=manifest["git_commit"],
        inputs=inputs,
        predictions=predictions,
        decisions=decisions,
        config=config,
        metadata=metadata,
        input_datasets=input_datasets,
    )
    if manifest.get("freeze_id") != expected_freeze_id:
        raise ResearchFreezeError("freeze identity mismatch")
    if any(manifest.get(flag) is not False for flag in ("execution_enabled", "frontend_selectable", "roi_authorized")):
        raise ResearchFreezeError("research freeze must remain non-executable and non-selectable")
    return {
        "status": "valid",
        "package_dir": str(package),
        "experiment_id": manifest["experiment_id"],
        "freeze_id": manifest["freeze_id"],
        "input_files": len(inputs),
        "prediction_files": len(predictions),
        "decision_files": len(decisions),
        "sha256s_sha256": sha256_file(package / "SHA256SUMS"),
        "manifest_sha256": entries["manifest.json"],
    }


def create_settlement_package(
    freeze_dir: Path,
    output_dir: Path,
    *,
    settlement_id: str,
    result_files: Iterable[Path],
    settled_at_utc: str | None = None,
) -> dict[str, Any]:
    """Capture real result files in a separate package after verifying a freeze."""

    settlement_id = safe_protocol_id(settlement_id, "settlement ID")
    freeze = freeze_dir.expanduser().resolve()
    freeze_check = verify_freeze_package(freeze)
    _ensure_outside(output_dir, freeze)
    settled_at = explicit_utc(settled_at_utc) if settled_at_utc else utc_now()
    freeze_manifest = json.loads((freeze / "manifest.json").read_text(encoding="utf-8"))

    def build(stage: Path) -> None:
        results = _copy_assets(stage, "results", result_files)
        manifest = {
            "schema_version": SETTLEMENT_SCHEMA,
            "lifecycle_state": "SETTLED",
            "settlement_id": settlement_id,
            "settled_at_utc": settled_at,
            "freeze": {
                "package_dir": str(freeze),
                "freeze_id": freeze_check["freeze_id"],
                "manifest_sha256": freeze_check["manifest_sha256"],
                "sha256s_sha256": freeze_check["sha256s_sha256"],
                "decision_sha256": freeze_manifest["decision_sha256"],
            },
            "real_results": results,
            "result_sha256": asset_list_sha256(results),
            "completion_attested": False,
            "protocol_notice": "This generic package records result evidence only. Domain settlement code must validate completeness without modifying frozen decisions or parameters.",
        }
        _write_json(stage / "manifest.json", manifest)
        _write_sums(stage, {"results"})

    return _atomic_publish(output_dir, build, verify_settlement_package)


def verify_settlement_package(path: Path) -> dict[str, Any]:
    package = path.expanduser().resolve()
    entries = _verify_sums(package, {"results"})
    try:
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchFreezeError("invalid settlement manifest") from exc
    required = {"schema_version", "lifecycle_state", "settlement_id", "settled_at_utc", "freeze", "real_results", "result_sha256"}
    if not required.issubset(manifest) or manifest.get("schema_version") != SETTLEMENT_SCHEMA:
        raise ResearchFreezeError("unsupported or incomplete settlement manifest")
    if manifest.get("lifecycle_state") != "SETTLED":
        raise ResearchFreezeError("settlement package has an invalid lifecycle state")
    explicit_utc(str(manifest["settled_at_utc"]))
    results = _verify_asset_list(package, manifest["real_results"], "results")
    if manifest.get("result_sha256") != asset_list_sha256(results):
        raise ResearchFreezeError("result digest mismatch")
    freeze = manifest.get("freeze")
    if not isinstance(freeze, dict) or not all(isinstance(freeze.get(name), str) for name in ("freeze_id", "manifest_sha256", "sha256s_sha256", "decision_sha256")):
        raise ResearchFreezeError("settlement package has an invalid freeze reference")
    return {
        "status": "valid",
        "package_dir": str(package),
        "settlement_id": manifest["settlement_id"],
        "freeze_id": freeze["freeze_id"],
        "result_files": len(results),
        "sha256s_sha256": sha256_file(package / "SHA256SUMS"),
        "manifest_sha256": entries["manifest.json"],
    }


def create_review_package(
    freeze_dir: Path,
    settlement_dir: Path,
    output_dir: Path,
    *,
    review_id: str,
    summary_file: Path,
    reviewed_at_utc: str | None = None,
) -> dict[str, Any]:
    """Create a separate review package referencing verified freeze and settlement bytes."""

    review_id = safe_protocol_id(review_id, "review ID")
    freeze = freeze_dir.expanduser().resolve()
    settlement = settlement_dir.expanduser().resolve()
    freeze_check = verify_freeze_package(freeze)
    settlement_check = verify_settlement_package(settlement)
    _ensure_outside(output_dir, freeze)
    _ensure_outside(output_dir, settlement)
    if settlement_check["freeze_id"] != freeze_check["freeze_id"]:
        raise ResearchFreezeError("settlement package does not belong to the supplied freeze")
    settlement_manifest = json.loads((settlement / "manifest.json").read_text(encoding="utf-8"))
    settlement_reference = settlement_manifest["freeze"]
    if (
        settlement_reference["manifest_sha256"] != freeze_check["manifest_sha256"]
        or settlement_reference["sha256s_sha256"] != freeze_check["sha256s_sha256"]
    ):
        raise ResearchFreezeError("settlement package freeze hashes do not match the supplied freeze")
    reviewed_at = explicit_utc(reviewed_at_utc) if reviewed_at_utc else utc_now()

    def build(stage: Path) -> None:
        summaries = _copy_assets(stage, "review", [summary_file])
        manifest = {
            "schema_version": REVIEW_SCHEMA,
            "lifecycle_state": "REVIEWED",
            "review_id": review_id,
            "reviewed_at_utc": reviewed_at,
            "freeze": {
                "freeze_id": freeze_check["freeze_id"],
                "manifest_sha256": freeze_check["manifest_sha256"],
                "sha256s_sha256": freeze_check["sha256s_sha256"],
            },
            "settlement": {
                "settlement_id": settlement_check["settlement_id"],
                "manifest_sha256": settlement_check["manifest_sha256"],
                "sha256s_sha256": settlement_check["sha256s_sha256"],
            },
            "review_files": summaries,
            "protocol_notice": "Review is interpretive only. It must not alter frozen decisions, inputs, parameters, or settlement evidence.",
        }
        _write_json(stage / "manifest.json", manifest)
        _write_sums(stage, {"review"})

    return _atomic_publish(output_dir, build, verify_review_package)


def verify_review_package(path: Path) -> dict[str, Any]:
    package = path.expanduser().resolve()
    entries = _verify_sums(package, {"review"})
    try:
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchFreezeError("invalid review manifest") from exc
    required = {"schema_version", "lifecycle_state", "review_id", "reviewed_at_utc", "freeze", "settlement", "review_files"}
    if not required.issubset(manifest) or manifest.get("schema_version") != REVIEW_SCHEMA:
        raise ResearchFreezeError("unsupported or incomplete review manifest")
    if manifest.get("lifecycle_state") != "REVIEWED":
        raise ResearchFreezeError("review package has an invalid lifecycle state")
    explicit_utc(str(manifest["reviewed_at_utc"]))
    files = _verify_asset_list(package, manifest["review_files"], "review")
    for reference in (manifest["freeze"], manifest["settlement"]):
        if not isinstance(reference, dict) or not all(isinstance(reference.get(name), str) for name in ("manifest_sha256", "sha256s_sha256")):
            raise ResearchFreezeError("review package has an invalid upstream reference")
    return {
        "status": "valid",
        "package_dir": str(package),
        "review_id": manifest["review_id"],
        "review_files": len(files),
        "sha256s_sha256": sha256_file(package / "SHA256SUMS"),
        "manifest_sha256": entries["manifest.json"],
    }
