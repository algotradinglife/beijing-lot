from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import research_freeze_protocol as protocol  # noqa: E402
from src import research_freeze_automation as automation  # noqa: E402
from src.research_freeze_automation import register_experiment, run_due_jobs  # noqa: E402
from src.research_freeze_protocol import ResearchFreezeError, verify_freeze_package  # noqa: E402


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def scheduler_config(tmp_path: Path, *, available_at_utc: str = "2026-07-21T01:30:00+00:00") -> Path:
    write(tmp_path / "inputs/matches.csv", "match,kickoff_hkt,team_home,team_away\n1,2026-07-21T20:00:00+08:00,A,B\n")
    write(tmp_path / "inputs/sp.csv", "match,sp3,sp1,sp0\n1,2.10,3.20,3.40\n")
    write(tmp_path / "outputs/predictions.json", '{"match": 1, "p3": 0.48, "p1": 0.28, "p0": 0.24}\n')
    write(tmp_path / "outputs/decisions.json", '{"match": 1, "research_decision": "observe_home"}\n')
    config = {
        "jobs": [
            {
                "experiment_id": "AUTO-FREEZE-001",
                "research_question": "Can automated freeze capture as-of research output?",
                "model_version": "copy-fixture-v1",
                "scheduled_for_utc": "2026-07-21T02:00:00+00:00",
                "as_of_utc": "2026-07-21T02:00:00+00:00",
                "git_commit": "b" * 40,
                "branch": "research/freeze-automation-v1",
                "input_files": [
                    {
                        "path": "inputs/matches.csv",
                        "source": "fixture-match-data",
                        "data_version": "fixture-v1",
                        "source_timestamp_utc": "2026-07-21T01:00:00+00:00",
                        "available_at_utc": available_at_utc,
                    },
                    {
                        "path": "inputs/sp.csv",
                        "source": "fixture-sp-snapshot",
                        "data_version": "fixture-v1",
                        "source_timestamp_utc": "2026-07-21T01:10:00+00:00",
                        "available_at_utc": available_at_utc,
                    },
                ],
                "output_adapter": {
                    "type": "copy",
                    "prediction_files": ["outputs/predictions.json"],
                    "decision_files": ["outputs/decisions.json"],
                },
            }
        ],
        "freeze_root": str(tmp_path / "freeze"),
        "registry_path": str(tmp_path / "experiment_registry.md"),
    }
    return write(tmp_path / "scheduler.json", json.dumps(config, ensure_ascii=False))


def test_due_scheduler_creates_freeze_package_with_snapshot_metadata_and_registry(tmp_path: Path) -> None:
    config = scheduler_config(tmp_path)
    results = run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")

    assert results[0]["status"] == "frozen"
    package = tmp_path / "freeze/AUTO-FREEZE-001"
    assert {item.name for item in package.iterdir()} == {
        "manifest.json",
        "inputs",
        "predictions",
        "decisions",
        "metadata",
        "SHA256SUMS",
    }
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["frozen_at_utc"] == "2026-07-21T02:05:00.000000+00:00"
    assert manifest["prediction_files"][0]["path"] == "predictions/predictions.json"
    assert manifest["frozen_decisions"][0]["path"] == "decisions/decisions.json"
    assert manifest["execution_enabled"] is False
    assert verify_freeze_package(package)["prediction_files"] == 1
    snapshot_metadata = json.loads((package / "metadata/files/as_of_snapshot_metadata.json").read_text(encoding="utf-8"))
    assert snapshot_metadata["as_of_utc"] == "2026-07-21T02:00:00.000000+00:00"
    assert snapshot_metadata["as_of_boundary_attested"] is True
    assert all(row["available_at_utc"] <= snapshot_metadata["as_of_utc"] for row in snapshot_metadata["snapshot_files"])
    registry = (tmp_path / "experiment_registry.md").read_text(encoding="utf-8")
    assert "| `AUTO-FREEZE-001` |" in registry
    assert f"| `{manifest['freeze_id']}` |" in registry


def test_freeze_with_predictions_and_matching_digest_verifies(tmp_path: Path) -> None:
    config = scheduler_config(tmp_path)
    run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")
    package = tmp_path / "freeze/AUTO-FREEZE-001"
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["prediction_files"]
    assert manifest["prediction_sha256"] == protocol.asset_list_sha256(manifest["prediction_files"])
    assert verify_freeze_package(package)["status"] == "valid"


@pytest.mark.parametrize("missing_mode", ["null", "missing"])
def test_freeze_with_predictions_requires_prediction_digest(tmp_path: Path, missing_mode: str) -> None:
    config = scheduler_config(tmp_path)
    run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")
    package = tmp_path / "freeze/AUTO-FREEZE-001"
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["prediction_files"]
    if missing_mode == "null":
        manifest["prediction_sha256"] = None
    else:
        manifest.pop("prediction_sha256")
    protocol._write_json(manifest_path, manifest)
    protocol._write_sums(package, {"inputs", "predictions", "decisions", "metadata"})

    with pytest.raises(ResearchFreezeError, match="prediction digest mismatch"):
        verify_freeze_package(package)


def test_scheduler_rejects_inputs_available_after_as_of_boundary(tmp_path: Path) -> None:
    config = scheduler_config(tmp_path, available_at_utc="2026-07-21T02:01:00+00:00")
    with pytest.raises(ResearchFreezeError, match="after the as-of boundary"):
        run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")


def test_verified_automation_package_rejects_unmanifested_prediction_file(tmp_path: Path) -> None:
    config = scheduler_config(tmp_path)
    run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")
    package = tmp_path / "freeze/AUTO-FREEZE-001"
    write(package / "predictions/extra.json", '{"unexpected": true}\n')

    protocol._write_sums(package, {"inputs", "predictions", "decisions", "metadata"})

    with pytest.raises(ResearchFreezeError, match="not declared by the freeze manifest"):
        verify_freeze_package(package)


def test_registry_inserts_rows_inside_existing_markdown_table(tmp_path: Path) -> None:
    registry = tmp_path / "experiment_registry.md"
    registry.write_text(
        "# Experiment Registry\n\n"
        "| Experiment ID | Research Question | Branch | Freeze ID | Status | Result | Evidence Level |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| _No protocol-v1 experiment registered at initialization._ |  |  |  |  |  |  |\n\n"
        "## 字段约定\n\n"
        "details\n",
        encoding="utf-8",
    )

    register_experiment(
        registry,
        {
            "experiment_id": "AUTO-FREEZE-001",
            "research_question": "Question",
            "branch": "research/freeze-automation-v1",
            "freeze_id": "abc123",
            "status": "frozen",
            "result": "pending",
            "evidence_level": "A",
        },
    )

    text = registry.read_text(encoding="utf-8")
    assert "| `AUTO-FREEZE-001` | Question |" in text
    assert text.index("| `AUTO-FREEZE-001` |") < text.index("## 字段约定")
    assert "_No protocol-v1 experiment" not in text


def test_registry_duplicate_detection_compares_same_row_only(tmp_path: Path) -> None:
    registry = tmp_path / "experiment_registry.md"
    registry.write_text(
        "| Experiment ID | Research Question | Branch | Freeze ID | Status | Result | Evidence Level |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| `AUTO-FREEZE-001` | Old | `branch` | `old-freeze` | `frozen` | `pending` | `A` |\n"
        "| `OTHER` | Other | `branch` | `new-freeze` | `frozen` | `pending` | `A` |\n",
        encoding="utf-8",
    )

    with pytest.raises(ResearchFreezeError, match="different freeze"):
        register_experiment(
            registry,
            {
                "experiment_id": "AUTO-FREEZE-001",
                "research_question": "Question",
                "branch": "research/freeze-automation-v1",
                "freeze_id": "new-freeze",
                "status": "frozen",
                "result": "pending",
                "evidence_level": "A",
            },
        )


def test_registry_conflict_blocks_freeze_publish_before_package_creation(tmp_path: Path) -> None:
    config = scheduler_config(tmp_path)
    registry = tmp_path / "experiment_registry.md"
    registry.write_text(
        "| Experiment ID | Research Question | Branch | Freeze ID | Status | Result | Evidence Level |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| `AUTO-FREEZE-001` | Old | `branch` | `old-freeze` | `frozen` | `pending` | `A` |\n",
        encoding="utf-8",
    )

    with pytest.raises(ResearchFreezeError, match="different freeze"):
        run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")

    assert not (tmp_path / "freeze/AUTO-FREEZE-001").exists()
    assert "`old-freeze`" in registry.read_text(encoding="utf-8")


def test_scheduler_skips_jobs_that_are_not_due(tmp_path: Path) -> None:
    config = scheduler_config(tmp_path)
    results = run_due_jobs(config, now_utc="2026-07-21T01:59:00+00:00")

    assert results == [{"status": "skipped", "reason": "not_due", "experiment_id": "AUTO-FREEZE-001"}]
    assert not (tmp_path / "freeze/AUTO-FREEZE-001").exists()


def test_scheduler_skips_due_job_until_its_as_of_boundary(tmp_path: Path) -> None:
    config = scheduler_config(tmp_path)
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["jobs"][0]["as_of_utc"] = "2026-07-21T02:10:00+00:00"
    write(config, json.dumps(payload))

    results = run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")

    assert results == [{"status": "skipped", "reason": "not_ready", "experiment_id": "AUTO-FREEZE-001"}]
    assert not (tmp_path / "freeze/AUTO-FREEZE-001").exists()


def test_scheduler_rejects_input_file_drift_before_freeze_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = scheduler_config(tmp_path)
    source = tmp_path / "inputs/matches.csv"
    original_produce = automation.CopyResearchOutputAdapter.produce

    def mutate_input_after_output(self: object, dataset: object) -> object:
        output = original_produce(self, dataset)  # type: ignore[arg-type]
        write(source, "match,kickoff_hkt,team_home,team_away\n1,2026-07-21T20:00:00+08:00,C,D\n")
        return output

    monkeypatch.setattr(automation.CopyResearchOutputAdapter, "produce", mutate_input_after_output)

    with pytest.raises(ResearchFreezeError, match="changed since as-of snapshot"):
        run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")

    assert not (tmp_path / "freeze/AUTO-FREEZE-001").exists()


def test_scheduler_recovers_registry_after_published_freeze_registration_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = scheduler_config(tmp_path)
    original_register = automation.register_experiment
    attempts = 0

    def fail_once(registry_path: Path, entry: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated registry write failure")
        original_register(registry_path, entry)  # type: ignore[arg-type]

    monkeypatch.setattr(automation, "register_experiment", fail_once)

    with pytest.raises(OSError, match="registry write failure"):
        run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")

    package = tmp_path / "freeze/AUTO-FREEZE-001"
    assert verify_freeze_package(package)["status"] == "valid"
    assert not (tmp_path / "experiment_registry.md").exists()

    results = run_due_jobs(config, now_utc="2026-07-21T02:05:00+00:00")

    assert results[0]["status"] == "frozen"
    assert results[0]["registry_recovered"] is True
    assert attempts == 2
    assert f"`{results[0]['freeze_id']}`" in (tmp_path / "experiment_registry.md").read_text(encoding="utf-8")


def test_scheduler_cli_smoke_creates_reviewable_freeze(tmp_path: Path) -> None:
    config = scheduler_config(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/run_research_freeze_scheduler.py"),
            "--config",
            str(config),
            "--now-utc",
            "2026-07-21T02:05:00+00:00",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload[0]["status"] == "frozen"
    assert verify_freeze_package(tmp_path / "freeze/AUTO-FREEZE-001")["status"] == "valid"
