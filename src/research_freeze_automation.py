"""Automated research freeze scheduling around the generic Freeze Protocol.

This module is infrastructure-only.  It validates as-of metadata, invokes a
generic research-output adapter, creates an immutable freeze package, and appends
the experiment registry.  It does not implement betting, staking, execution, or
strategy selection logic.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from .research_freeze_protocol import (
    DEFAULT_FREEZE_ROOT,
    ResearchFreezeError,
    create_freeze_package,
    current_git_commit,
    explicit_utc,
    safe_protocol_id,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "docs/research/experiment_registry.md"
AUTOMATION_SCHEMA = "beijing_lot_research_freeze_automation_v1"


@dataclass(frozen=True)
class FrozenDataset:
    """As-of checked files passed to a research-output adapter."""

    experiment_id: str
    as_of_utc: str
    input_files: tuple[Path, ...]
    snapshot_metadata_file: Path
    work_dir: Path


@dataclass(frozen=True)
class ResearchOutput:
    """Adapter result consumed by freeze package generation."""

    prediction_files: tuple[Path, ...]
    decision_files: tuple[Path, ...]
    metadata_files: tuple[Path, ...] = ()


class ResearchOutputAdapter(Protocol):
    """Generic research-output interface.

    Implementations may run models or copy precomputed outputs, but they must
    return files that represent research observations only.
    """

    def produce(self, dataset: FrozenDataset) -> ResearchOutput:
        ...


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchFreezeError(f"invalid automation config: {path}") from exc
    if not isinstance(value, dict):
        raise ResearchFreezeError("automation config must be a JSON object")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _source_time(value: Mapping[str, Any], key: str, as_of_utc: str, label: str) -> str:
    timestamp = value.get(key)
    if timestamp is None:
        raise ResearchFreezeError(f"{label} must include {key}")
    normalized = explicit_utc(str(timestamp))
    if normalized > as_of_utc:
        raise ResearchFreezeError(f"{label} {key} is after the as-of boundary")
    return normalized


def _regular(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.is_symlink():
        raise ResearchFreezeError(f"automation source must be a regular file: {path}")
    return resolved


def _config_path(value: Any, default: Path, base_dir: Path) -> Path:
    path = Path(value) if value else default
    return path if path.is_absolute() else base_dir / path


class CopyResearchOutputAdapter:
    """Adapter that copies already-produced prediction and decision artifacts."""

    def __init__(self, prediction_files: tuple[Path, ...], decision_files: tuple[Path, ...]) -> None:
        if not prediction_files:
            raise ResearchFreezeError("copy adapter requires at least one prediction file")
        if not decision_files:
            raise ResearchFreezeError("copy adapter requires at least one decision file")
        self.prediction_files = prediction_files
        self.decision_files = decision_files

    def produce(self, dataset: FrozenDataset) -> ResearchOutput:
        predictions = _copy_named(self.prediction_files, dataset.work_dir / "adapter_output/predictions")
        decisions = _copy_named(self.decision_files, dataset.work_dir / "adapter_output/decisions")
        metadata = _write_json(
            dataset.work_dir / "adapter_output/research_output_interface.json",
            {
                "schema_version": AUTOMATION_SCHEMA,
                "adapter_type": "copy",
                "as_of_utc": dataset.as_of_utc,
                "experiment_id": dataset.experiment_id,
                "research_observation_only": True,
                "execution_enabled": False,
                "frontend_selectable": False,
                "roi_authorized": False,
                "prediction_files": [path.name for path in predictions],
                "decision_files": [path.name for path in decisions],
            },
        )
        return ResearchOutput(tuple(predictions), tuple(decisions), (metadata,))


def _copy_named(sources: tuple[Path, ...], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    used: set[str] = set()
    for index, source in enumerate(sources, start=1):
        resolved = _regular(source)
        target_name = resolved.name if resolved.name not in used else f"{index:03d}_{resolved.name}"
        used.add(target_name)
        target = output_dir / target_name
        shutil.copyfile(resolved, target)
        copied.append(target)
    return copied


def adapter_from_config(config: Mapping[str, Any], base_dir: Path) -> ResearchOutputAdapter:
    adapter = config.get("output_adapter")
    if not isinstance(adapter, dict):
        raise ResearchFreezeError("job output_adapter must be an object")
    adapter_type = adapter.get("type")
    if adapter_type != "copy":
        raise ResearchFreezeError("only the generic 'copy' research-output adapter is available in v1")
    predictions = tuple(base_dir / str(item) for item in adapter.get("prediction_files", []))
    decisions = tuple(base_dir / str(item) for item in adapter.get("decision_files", []))
    return CopyResearchOutputAdapter(predictions, decisions)


def _materialize_snapshot_metadata(job: Mapping[str, Any], base_dir: Path, work_dir: Path) -> tuple[tuple[Path, ...], Path]:
    experiment_id = safe_protocol_id(str(job.get("experiment_id") or ""), "experiment ID")
    as_of_utc = explicit_utc(str(job.get("as_of_utc") or job.get("scheduled_for_utc") or ""))
    inputs = job.get("input_files")
    if not isinstance(inputs, list) or not inputs:
        raise ResearchFreezeError("job input_files must be a non-empty list")

    records: list[dict[str, Any]] = []
    files: list[Path] = []
    for index, item in enumerate(inputs, start=1):
        if not isinstance(item, dict):
            raise ResearchFreezeError("each input file entry must be an object")
        if not item.get("source") or not item.get("data_version"):
            raise ResearchFreezeError("input file entries require source and data_version")
        path = _regular(base_dir / str(item.get("path") or ""))
        source_timestamp_utc = _source_time(item, "source_timestamp_utc", as_of_utc, f"input_files[{index}]")
        available_at_utc = _source_time(item, "available_at_utc", as_of_utc, f"input_files[{index}]")
        files.append(path)
        records.append(
            {
                "path": path.name,
                "source": str(item["source"]),
                "data_version": str(item["data_version"]),
                "source_timestamp_utc": source_timestamp_utc,
                "available_at_utc": available_at_utc,
                "as_of_utc": as_of_utc,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    metadata = _write_json(
        work_dir / "metadata/as_of_snapshot_metadata.json",
        {
            "schema_version": AUTOMATION_SCHEMA,
            "experiment_id": experiment_id,
            "as_of_utc": as_of_utc,
            "snapshot_files": records,
            "as_of_boundary_attested": True,
            "future_data_leakage_check": "source_timestamp_utc and available_at_utc must be <= as_of_utc",
        },
    )
    return tuple(files), metadata


def _job_due(job: Mapping[str, Any], now_utc: str) -> bool:
    scheduled_for = explicit_utc(str(job.get("scheduled_for_utc") or job.get("as_of_utc") or ""))
    return scheduled_for <= now_utc


def _job_config_file(job: Mapping[str, Any], work_dir: Path) -> Path:
    return _write_json(
        work_dir / "metadata/automation_job_config.json",
        {
            "schema_version": AUTOMATION_SCHEMA,
            "experiment_id": job["experiment_id"],
            "model_version": job["model_version"],
            "scheduled_for_utc": explicit_utc(str(job.get("scheduled_for_utc") or job.get("as_of_utc"))),
            "as_of_utc": explicit_utc(str(job.get("as_of_utc") or job.get("scheduled_for_utc"))),
            "research_output_adapter": job.get("output_adapter", {}).get("type"),
            "research_observation_only": True,
            "execution_enabled": False,
            "frontend_selectable": False,
            "roi_authorized": False,
            "job_parameters": job.get("parameters", {}),
        },
    )


def register_experiment(registry_path: Path, entry: Mapping[str, Any]) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if registry_path.exists():
        text = registry_path.read_text(encoding="utf-8")
    else:
        text = "# Experiment Registry\n\n| Experiment ID | Research Question | Branch | Freeze ID | Status | Result | Evidence Level |\n| --- | --- | --- | --- | --- | --- | --- |\n"
    experiment_id = str(entry["experiment_id"])
    row = (
        f"| `{experiment_id}` | {entry['research_question']} | `{entry['branch']}` | "
        f"`{entry['freeze_id']}` | `{entry['status']}` | `{entry['result']}` | `{entry['evidence_level']}` |\n"
    )
    lines = text.splitlines(keepends=True)
    for line in lines:
        if line.startswith(f"| `{experiment_id}` |"):
            if f"| `{entry['freeze_id']}` |" in line:
                return
            raise ResearchFreezeError(f"experiment already registered with a different freeze: {experiment_id}")
    placeholder = "| _No protocol-v1 experiment registered at initialization._ |  |  |  |  |  |  |\n"
    lines = [line for line in lines if line != placeholder]

    insert_at: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("| Experiment ID |"):
            insert_at = index + 1
            while insert_at < len(lines) and lines[insert_at].startswith("|"):
                insert_at += 1
            break
    if insert_at is not None:
        lines.insert(insert_at, row)
        registry_path.write_text("".join(lines), encoding="utf-8")
        return
    if row in lines:
        return
    text = "".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    registry_path.write_text(text + row, encoding="utf-8")


def run_freeze_job(
    job: Mapping[str, Any],
    *,
    base_dir: Path = ROOT,
    freeze_root: Path = DEFAULT_FREEZE_ROOT,
    registry_path: Path = DEFAULT_REGISTRY,
    now_utc: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    experiment_id = safe_protocol_id(str(job.get("experiment_id") or ""), "experiment ID")
    research_question = str(job.get("research_question") or "").strip()
    model_version = str(job.get("model_version") or "").strip()
    if not research_question or not model_version:
        raise ResearchFreezeError("job requires research_question and model_version")

    now = explicit_utc(now_utc) if now_utc else _utc_now()
    if not _job_due(job, now):
        return {"status": "skipped", "reason": "not_due", "experiment_id": experiment_id}
    output_dir = freeze_root / experiment_id
    if output_dir.exists():
        return {"status": "skipped", "reason": "already_frozen", "experiment_id": experiment_id, "package_dir": str(output_dir)}
    if dry_run:
        return {"status": "dry_run", "experiment_id": experiment_id, "package_dir": str(output_dir)}

    work_dir = base_dir / "results/freeze_scheduler_work" / experiment_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    input_files, snapshot_metadata = _materialize_snapshot_metadata(job, base_dir, work_dir)
    dataset = FrozenDataset(
        experiment_id=experiment_id,
        as_of_utc=explicit_utc(str(job.get("as_of_utc") or job.get("scheduled_for_utc"))),
        input_files=input_files,
        snapshot_metadata_file=snapshot_metadata,
        work_dir=work_dir,
    )
    output = adapter_from_config(job, base_dir).produce(dataset)
    scheduler_metadata = _write_json(
        work_dir / "metadata/scheduler_run.json",
        {
            "schema_version": AUTOMATION_SCHEMA,
            "experiment_id": experiment_id,
            "scheduled_for_utc": explicit_utc(str(job.get("scheduled_for_utc") or job.get("as_of_utc"))),
            "ran_at_utc": now,
            "freeze_package_target": str(output_dir),
            "scheduler": "simple_file_due_scheduler_v1",
        },
    )
    config_file = _job_config_file(job, work_dir)
    metadata_files = (snapshot_metadata, scheduler_metadata, *output.metadata_files)
    freeze = create_freeze_package(
        output_dir,
        experiment_id=experiment_id,
        research_question=research_question,
        model_version=model_version,
        input_files=input_files,
        prediction_files=output.prediction_files,
        decision_files=output.decision_files,
        decision_directory="decisions",
        config_file=config_file,
        metadata_files=metadata_files,
        git_commit=str(job.get("git_commit") or current_git_commit()),
        frozen_at_utc=now,
    )
    register_experiment(
        registry_path,
        {
            "experiment_id": experiment_id,
            "research_question": research_question.replace("|", "\\|"),
            "branch": str(job.get("branch") or "research/freeze-automation-v1"),
            "freeze_id": freeze["freeze_id"],
            "status": "frozen",
            "result": "pending",
            "evidence_level": str(job.get("evidence_level") or "A"),
        },
    )
    return {**freeze, "verification_status": freeze["status"], "status": "frozen"}


def run_due_jobs(
    config_path: Path,
    *,
    now_utc: str | None = None,
    once: bool = True,
    poll_seconds: float = 60.0,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    config_path = config_path.expanduser().resolve()
    config = _read_json(config_path)
    jobs = config.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ResearchFreezeError("automation config requires a non-empty jobs list")
    freeze_root = _config_path(config.get("freeze_root"), DEFAULT_FREEZE_ROOT, config_path.parent)
    registry_path = _config_path(config.get("registry_path"), DEFAULT_REGISTRY, config_path.parent)
    while True:
        now = explicit_utc(now_utc) if now_utc else _utc_now()
        results: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, dict):
                raise ResearchFreezeError("jobs must be objects")
            results.append(
                run_freeze_job(
                    job,
                    base_dir=config_path.parent,
                    freeze_root=freeze_root,
                    registry_path=registry_path,
                    now_utc=now,
                    dry_run=dry_run,
                )
            )
        if once:
            return results
        time.sleep(poll_seconds)
