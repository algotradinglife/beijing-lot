from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import research_freeze_protocol as protocol  # noqa: E402


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def freeze(tmp_path: Path, name: str = "EXP-001") -> Path:
    inputs = write(tmp_path / f"sources/{name}/asof.csv", "match,probability\n1,0.61\n")
    decisions = write(tmp_path / f"sources/{name}/decision.csv", "match,choice\n1,3\n")
    config = write(tmp_path / f"sources/{name}/config.json", '{"seed": 17}\n')
    output = tmp_path / "freeze" / name
    protocol.create_freeze_package(
        output,
        experiment_id=name,
        research_question="Does a frozen input remain auditable?",
        model_version="test-model-v1",
        input_files=[inputs],
        decision_files=[decisions],
        config_file=config,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-21T00:00:00+00:00",
    )
    return output


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/manage_research_freeze.py"), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_freeze_layout_manifest_and_checksum_are_immutable(tmp_path: Path) -> None:
    output = freeze(tmp_path)
    assert {item.name for item in output.iterdir()} == {
        "manifest.json",
        "inputs",
        "decision",
        "metadata",
        "SHA256SUMS",
    }
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lifecycle_state"] == "FROZEN"
    assert manifest["dataset_snapshot"]["data_sha256"]
    assert manifest["decision_sha256"]
    assert manifest["config"]["path"].startswith("metadata/config/")
    assert "source_path" not in manifest["config"]
    assert all(manifest[flag] is False for flag in ("execution_enabled", "frontend_selectable", "roi_authorized"))
    verified = protocol.verify_freeze_package(output)
    assert verified["input_files"] == 1
    assert verified["decision_files"] == 1

    write(tmp_path / "sources/EXP-001/asof.csv", "match,probability\n1,0.02\n")
    assert protocol.verify_freeze_package(output)["sha256s_sha256"] == verified["sha256s_sha256"]
    with pytest.raises(FileExistsError, match="already exists"):
        protocol.create_freeze_package(
            output,
            experiment_id="EXP-001",
            research_question="Does overwrite happen?",
            model_version="test-model-v1",
            input_files=[tmp_path / "sources/EXP-001/asof.csv"],
            decision_files=[tmp_path / "sources/EXP-001/decision.csv"],
            config_file=tmp_path / "sources/EXP-001/config.json",
            git_commit="a" * 40,
        )


def test_freeze_identity_covers_config_and_model_metadata(tmp_path: Path) -> None:
    inputs = write(tmp_path / "sources/asof.csv", "match,probability\n1,0.61\n")
    decisions = write(tmp_path / "sources/decision.csv", "match,choice\n1,3\n")
    first_config = write(tmp_path / "sources/first-config.json", '{"seed": 17}\n')
    second_config = write(tmp_path / "sources/second-config.json", '{"seed": 18}\n')
    common = {
        "experiment_id": "EXP-IDENTITY",
        "research_question": "Does the identity cover all frozen data?",
        "input_files": [inputs],
        "decision_files": [decisions],
        "git_commit": "a" * 40,
        "frozen_at_utc": "2026-07-21T00:00:00+00:00",
    }
    first = protocol.create_freeze_package(
        tmp_path / "freeze/first", config_file=first_config, model_version="model-v1", **common
    )
    second = protocol.create_freeze_package(
        tmp_path / "freeze/second", config_file=second_config, model_version="model-v1", **common
    )
    third = protocol.create_freeze_package(
        tmp_path / "freeze/third", config_file=first_config, model_version="model-v2", **common
    )
    assert len({first["freeze_id"], second["freeze_id"], third["freeze_id"]}) == 3


def test_freeze_records_input_dataset_hashes_in_its_identity(tmp_path: Path) -> None:
    inputs = write(tmp_path / "sources/asof.csv", "match,probability\n1,0.61\n")
    decisions = write(tmp_path / "sources/decision.csv", "match,choice\n1,3\n")
    config = write(tmp_path / "sources/config.json", '{"seed": 17}\n')
    dataset = write(tmp_path / "fixtures/source.db", "fixture database bytes")
    output = tmp_path / "freeze" / "EXP-DATASET"

    protocol.create_freeze_package(
        output,
        experiment_id="EXP-DATASET",
        research_question="Are source dataset hashes retained?",
        model_version="test-model-v1",
        input_files=[inputs],
        input_datasets=[dataset],
        decision_files=[decisions],
        config_file=config,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-21T00:00:00+00:00",
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["input_dataset"] == [{
        "path": "source-001",
        "bytes": len("fixture database bytes"),
        "sha256": protocol.sha256_file(dataset),
    }]
    assert str(tmp_path) not in json.dumps(manifest, sort_keys=True)
    assert protocol.verify_freeze_package(output)["status"] == "valid"


def test_freeze_uses_explicit_pathless_dataset_logical_name(tmp_path: Path) -> None:
    inputs = write(tmp_path / "sources/asof.csv", "match,probability\n1,0.61\n")
    decisions = write(tmp_path / "sources/decision.csv", "match,choice\n1,3\n")
    config = write(tmp_path / "sources/config.json", '{"seed": 17}\n')
    dataset = write(tmp_path / "private/location/source.db", "fixture database bytes")
    output = tmp_path / "freeze" / "EXP-DATASET-LOGICAL"

    protocol.create_freeze_package(
        output,
        experiment_id="EXP-DATASET-LOGICAL",
        research_question="Is the source identity portable without its local path?",
        model_version="test-model-v1",
        input_files=[inputs],
        input_datasets=[dataset],
        input_dataset_labels=["historical_xlsm"],
        decision_files=[decisions],
        config_file=config,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-21T00:00:00+00:00",
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["input_dataset"][0]["path"] == "historical_xlsm"
    assert str(dataset) not in json.dumps(manifest, sort_keys=True)
    assert protocol.verify_freeze_package(output)["status"] == "valid"


def test_metadata_source_named_config_cannot_collide_with_config_directory(tmp_path: Path) -> None:
    inputs = write(tmp_path / "sources/asof.csv", "match,probability\n1,0.61\n")
    decisions = write(tmp_path / "sources/decision.csv", "match,choice\n1,3\n")
    config = write(tmp_path / "sources/config.json", '{"seed": 17}\n')
    metadata = write(tmp_path / "sources/metadata/config", "legal metadata named config\n")

    output = tmp_path / "freeze" / "EXP-METADATA-CONFIG"
    protocol.create_freeze_package(
        output,
        experiment_id="EXP-METADATA-CONFIG",
        research_question="Can metadata use a reserved-looking basename?",
        model_version="test-model-v1",
        input_files=[inputs],
        decision_files=[decisions],
        config_file=config,
        metadata_files=[metadata],
        git_commit="a" * 40,
        frozen_at_utc="2026-07-21T00:00:00+00:00",
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config"]["path"].startswith("metadata/config/")
    assert manifest["metadata_files"][0]["path"] == "metadata/files/config"
    assert protocol.verify_freeze_package(output)["status"] == "valid"


def test_verifier_enforces_metadata_subdirectory_roles(tmp_path: Path) -> None:
    inputs = write(tmp_path / "sources/asof.csv", "match,probability\n1,0.61\n")
    decisions = write(tmp_path / "sources/decision.csv", "match,choice\n1,3\n")
    config = write(tmp_path / "sources/config.json", '{"seed": 17}\n')
    metadata = write(tmp_path / "sources/metadata/info.txt", "metadata\n")
    output = tmp_path / "freeze" / "EXP-METADATA-ROLES"
    protocol.create_freeze_package(
        output,
        experiment_id="EXP-METADATA-ROLES",
        research_question="Does verification enforce metadata roles?",
        model_version="test-model-v1",
        input_files=[inputs],
        decision_files=[decisions],
        config_file=config,
        metadata_files=[metadata],
        git_commit="a" * 40,
        frozen_at_utc="2026-07-21T00:00:00+00:00",
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    config_bytes = (output / manifest["config"]["path"]).read_bytes()
    metadata_bytes = (output / manifest["metadata_files"][0]["path"]).read_bytes()
    shutil.rmtree(output / "metadata")
    swapped_config = write(output / "metadata/files/config.json", config_bytes.decode("utf-8"))
    swapped_metadata = write(output / "metadata/config/info.txt", metadata_bytes.decode("utf-8"))
    manifest["config"].update(
        {
            "path": "metadata/files/config.json",
            "bytes": swapped_config.stat().st_size,
            "sha256": protocol.sha256_file(swapped_config),
        }
    )
    manifest["metadata_files"][0].update(
        {
            "path": "metadata/config/info.txt",
            "bytes": swapped_metadata.stat().st_size,
            "sha256": protocol.sha256_file(swapped_metadata),
        }
    )
    manifest["freeze_id"] = protocol.freeze_identity_sha256(
        experiment_id=manifest["experiment_id"],
        research_question=manifest["research_question"],
        model_version=manifest["model_version"],
        frozen_at_utc=manifest["frozen_at_utc"],
        git_commit=manifest["git_commit"],
        inputs=manifest["dataset_snapshot"]["files"],
        decisions=manifest["frozen_decisions"],
        config=manifest["config"],
        metadata=manifest["metadata_files"],
    )
    protocol._write_json(output / "manifest.json", manifest)
    protocol._write_sums(output, {"inputs", "decision", "metadata"})

    with pytest.raises(protocol.ResearchFreezeError, match="config file must be stored under metadata/config"):
        protocol.verify_freeze_package(output)


def test_verifier_rejects_recomputed_flat_config_path(tmp_path: Path) -> None:
    inputs = write(tmp_path / "sources/asof.csv", "match,probability\n1,0.61\n")
    decisions = write(tmp_path / "sources/decision.csv", "match,choice\n1,3\n")
    config = write(tmp_path / "sources/config.json", '{"seed": 17}\n')
    output = tmp_path / "freeze" / "EXP-FLAT-CONFIG"
    protocol.create_freeze_package(
        output,
        experiment_id="EXP-FLAT-CONFIG",
        research_question="Does verification reject a flat config path?",
        model_version="test-model-v1",
        input_files=[inputs],
        decision_files=[decisions],
        config_file=config,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-21T00:00:00+00:00",
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    config_bytes = (output / manifest["config"]["path"]).read_text(encoding="utf-8")
    shutil.rmtree(output / "metadata/config")
    flat_config = write(output / "metadata/config.json", config_bytes)
    manifest["config"].update(
        {
            "path": "metadata/config.json",
            "bytes": flat_config.stat().st_size,
            "sha256": protocol.sha256_file(flat_config),
        }
    )
    manifest["freeze_id"] = protocol.freeze_identity_sha256(
        experiment_id=manifest["experiment_id"],
        research_question=manifest["research_question"],
        model_version=manifest["model_version"],
        frozen_at_utc=manifest["frozen_at_utc"],
        git_commit=manifest["git_commit"],
        inputs=manifest["dataset_snapshot"]["files"],
        decisions=manifest["frozen_decisions"],
        config=manifest["config"],
        metadata=manifest["metadata_files"],
    )
    protocol._write_json(output / "manifest.json", manifest)
    protocol._write_sums(output, {"inputs", "decision", "metadata"})

    with pytest.raises(protocol.ResearchFreezeError, match="config file must be stored under metadata/config"):
        protocol.verify_freeze_package(output)


def test_verifier_accepts_legacy_flat_auxiliary_metadata(tmp_path: Path) -> None:
    inputs = write(tmp_path / "sources/asof.csv", "match,probability\n1,0.61\n")
    decisions = write(tmp_path / "sources/decision.csv", "match,choice\n1,3\n")
    config = write(tmp_path / "sources/config.json", '{"seed": 17}\n')
    metadata = write(tmp_path / "sources/metadata/info.txt", "metadata\n")
    output = tmp_path / "freeze" / "EXP-LEGACY-METADATA"
    protocol.create_freeze_package(
        output,
        experiment_id="EXP-LEGACY-METADATA",
        research_question="Can legacy flat metadata still verify?",
        model_version="test-model-v1",
        input_files=[inputs],
        decision_files=[decisions],
        config_file=config,
        metadata_files=[metadata],
        git_commit="a" * 40,
        frozen_at_utc="2026-07-21T00:00:00+00:00",
    )

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    metadata_bytes = (output / manifest["metadata_files"][0]["path"]).read_text(encoding="utf-8")
    shutil.rmtree(output / "metadata/files")
    legacy_metadata = write(output / "metadata/info.txt", metadata_bytes)
    manifest["metadata_files"][0].update(
        {
            "path": "metadata/info.txt",
            "bytes": legacy_metadata.stat().st_size,
            "sha256": protocol.sha256_file(legacy_metadata),
        }
    )
    manifest["freeze_id"] = protocol.freeze_identity_sha256(
        experiment_id=manifest["experiment_id"],
        research_question=manifest["research_question"],
        model_version=manifest["model_version"],
        frozen_at_utc=manifest["frozen_at_utc"],
        git_commit=manifest["git_commit"],
        inputs=manifest["dataset_snapshot"]["files"],
        decisions=manifest["frozen_decisions"],
        config=manifest["config"],
        metadata=manifest["metadata_files"],
    )
    protocol._write_json(output / "manifest.json", manifest)
    protocol._write_sums(output, {"inputs", "decision", "metadata"})

    assert protocol.verify_freeze_package(output)["status"] == "valid"


def test_directory_symlink_in_package_is_rejected(tmp_path: Path) -> None:
    output = freeze(tmp_path)
    target = tmp_path / "external-directory"
    target.mkdir()
    try:
        (output / "inputs/linked-directory").symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(protocol.ResearchFreezeError, match="non-regular file"):
        protocol.verify_freeze_package(output)


def test_tampered_freeze_is_rejected(tmp_path: Path) -> None:
    output = freeze(tmp_path)
    with (output / "decision/decision.csv").open("a", encoding="utf-8") as handle:
        handle.write("2,1\n")
    with pytest.raises(protocol.ResearchFreezeError, match="checksum mismatch"):
        protocol.verify_freeze_package(output)


def test_verifier_rejects_manifest_unreferenced_prediction_directory(tmp_path: Path) -> None:
    output = freeze(tmp_path)
    write(output / "predictions/extra.json", '{"unexpected": true}\n')
    protocol._write_sums(output, {"inputs", "decision", "predictions", "metadata"})

    with pytest.raises(protocol.ResearchFreezeError, match="unexpected package file"):
        protocol.verify_freeze_package(output)


def test_settlement_and_review_are_separate_and_linked_to_the_same_freeze(tmp_path: Path) -> None:
    frozen = freeze(tmp_path)
    freeze_sum_before = protocol.sha256_file(frozen / "SHA256SUMS")
    freeze_info = protocol.verify_freeze_package(frozen)
    results = write(tmp_path / "official/results.csv", "match,score\n1,2:0\n")
    settlement = tmp_path / "settlement" / freeze_info["freeze_id"] / "SET-001"
    settlement_info = protocol.create_settlement_package(
        frozen,
        settlement,
        settlement_id="SET-001",
        result_files=[results],
        settled_at_utc="2026-07-22T00:00:00+00:00",
    )
    assert settlement_info["freeze_id"] == freeze_info["freeze_id"]
    assert protocol.sha256_file(frozen / "SHA256SUMS") == freeze_sum_before
    assert not (frozen / "settlement").exists()
    settlement_manifest = json.loads((settlement / "manifest.json").read_text(encoding="utf-8"))
    assert settlement_manifest["lifecycle_state"] == "SETTLED"
    assert settlement_manifest["completion_attested"] is False

    summary = write(tmp_path / "review.md", "# Review\nNo selection was changed.\n")
    review = tmp_path / "review" / freeze_info["freeze_id"] / "REV-001"
    review_info = protocol.create_review_package(
        frozen,
        settlement,
        review,
        review_id="REV-001",
        summary_file=summary,
        reviewed_at_utc="2026-07-23T00:00:00+00:00",
    )
    assert review_info["status"] == "valid"
    assert protocol.verify_settlement_package(settlement)["result_files"] == 1
    assert protocol.verify_review_package(review)["review_files"] == 1

    with pytest.raises(protocol.ResearchFreezeError, match="must not be written inside"):
        protocol.create_settlement_package(
            frozen,
            frozen / "forbidden-settlement",
            settlement_id="SET-002",
            result_files=[results],
        )


def test_review_rejects_settlement_from_another_freeze(tmp_path: Path) -> None:
    first = freeze(tmp_path, "EXP-001")
    second = freeze(tmp_path, "EXP-002")
    result = write(tmp_path / "official/results.csv", "match,score\n1,2:0\n")
    other_settlement = tmp_path / "settlement/other/SET-002"
    protocol.create_settlement_package(
        second, other_settlement, settlement_id="SET-002", result_files=[result]
    )
    with pytest.raises(protocol.ResearchFreezeError, match="does not belong"):
        protocol.create_review_package(
            first,
            other_settlement,
            tmp_path / "review/invalid",
            review_id="REV-INVALID",
            summary_file=write(tmp_path / "review.md", "invalid link\n"),
        )


def test_library_rejects_traversal_and_absolute_protocol_ids(tmp_path: Path) -> None:
    frozen = freeze(tmp_path)
    freeze_info = protocol.verify_freeze_package(frozen)
    result = write(tmp_path / "official/results.csv", "match,score\n1,2:0\n")
    settlement = tmp_path / "settlement" / freeze_info["freeze_id"] / "SET-001"
    protocol.create_settlement_package(
        frozen,
        settlement,
        settlement_id="SET-001",
        result_files=[result],
        settled_at_utc="2026-07-22T00:00:00+00:00",
    )
    summary = write(tmp_path / "review.md", "# Review\n")

    with pytest.raises(protocol.ResearchFreezeError, match="experiment ID must be a safe single path component"):
        protocol.create_freeze_package(
            tmp_path / "freeze/invalid-traversal",
            experiment_id="../escaped-freeze",
            research_question="reject traversal",
            model_version="test-model-v1",
            input_files=[tmp_path / "sources/EXP-001/asof.csv"],
            decision_files=[tmp_path / "sources/EXP-001/decision.csv"],
            config_file=tmp_path / "sources/EXP-001/config.json",
            git_commit="a" * 40,
        )
    with pytest.raises(protocol.ResearchFreezeError, match="experiment ID must be a safe single path component"):
        protocol.create_freeze_package(
            tmp_path / "freeze/invalid-absolute",
            experiment_id=str(tmp_path / "absolute-freeze-id"),
            research_question="reject absolute",
            model_version="test-model-v1",
            input_files=[tmp_path / "sources/EXP-001/asof.csv"],
            decision_files=[tmp_path / "sources/EXP-001/decision.csv"],
            config_file=tmp_path / "sources/EXP-001/config.json",
            git_commit="a" * 40,
        )
    with pytest.raises(protocol.ResearchFreezeError, match="settlement ID must be a safe single path component"):
        protocol.create_settlement_package(
            frozen,
            tmp_path / "settlement/invalid",
            settlement_id="../escaped-settlement",
            result_files=[result],
        )
    with pytest.raises(protocol.ResearchFreezeError, match="settlement ID must be a safe single path component"):
        protocol.create_settlement_package(
            frozen,
            tmp_path / "settlement/invalid-absolute",
            settlement_id=str(tmp_path / "absolute-settlement-id"),
            result_files=[result],
        )
    with pytest.raises(protocol.ResearchFreezeError, match="review ID must be a safe single path component"):
        protocol.create_review_package(
            frozen,
            settlement,
            tmp_path / "review/invalid",
            review_id="../escaped-review",
            summary_file=summary,
        )
    with pytest.raises(protocol.ResearchFreezeError, match="review ID must be a safe single path component"):
        protocol.create_review_package(
            frozen,
            settlement,
            tmp_path / "review/invalid-absolute",
            review_id=str(tmp_path / "absolute-review-id"),
            summary_file=summary,
        )


def test_cli_default_paths_reject_traversal_and_absolute_protocol_ids(tmp_path: Path) -> None:
    frozen = freeze(tmp_path)
    freeze_info = protocol.verify_freeze_package(frozen)
    result = write(tmp_path / "official/results.csv", "match,score\n1,2:0\n")
    settlement = tmp_path / "settlement" / freeze_info["freeze_id"] / "SET-001"
    protocol.create_settlement_package(
        frozen,
        settlement,
        settlement_id="SET-001",
        result_files=[result],
        settled_at_utc="2026-07-22T00:00:00+00:00",
    )
    summary = write(tmp_path / "review.md", "# Review\n")

    freeze_args = [
        "--research-question",
        "reject default path escape",
        "--model-version",
        "test-model-v1",
        "--input",
        str(tmp_path / "sources/EXP-001/asof.csv"),
        "--decision",
        str(tmp_path / "sources/EXP-001/decision.csv"),
        "--config",
        str(tmp_path / "sources/EXP-001/config.json"),
        "--git-commit",
        "a" * 40,
    ]
    freeze_traversal = run_cli("freeze", "--experiment-id", "../escaped-freeze", *freeze_args)
    freeze_absolute = run_cli("freeze", "--experiment-id", str(tmp_path / "absolute-freeze-id"), *freeze_args)
    settlement_traversal = run_cli(
        "settle",
        "--freeze-dir",
        str(frozen),
        "--settlement-id",
        "../escaped-settlement",
        "--result",
        str(result),
    )
    settlement_absolute = run_cli(
        "settle",
        "--freeze-dir",
        str(frozen),
        "--settlement-id",
        str(tmp_path / "absolute-settlement-id"),
        "--result",
        str(result),
    )
    review_traversal = run_cli(
        "review",
        "--freeze-dir",
        str(frozen),
        "--settlement-dir",
        str(settlement),
        "--review-id",
        "../escaped-review",
        "--summary",
        str(summary),
    )
    review_absolute = run_cli(
        "review",
        "--freeze-dir",
        str(frozen),
        "--settlement-dir",
        str(settlement),
        "--review-id",
        str(tmp_path / "absolute-review-id"),
        "--summary",
        str(summary),
    )

    results = [
        freeze_traversal,
        freeze_absolute,
        settlement_traversal,
        settlement_absolute,
        review_traversal,
        review_absolute,
    ]
    assert all(item.returncode != 0 for item in results)
    assert "experiment ID must be a safe single path component" in freeze_traversal.stderr
    assert "experiment ID must be a safe single path component" in freeze_absolute.stderr
    assert "settlement ID must be a safe single path component" in settlement_traversal.stderr
    assert "settlement ID must be a safe single path component" in settlement_absolute.stderr
    assert "review ID must be a safe single path component" in review_traversal.stderr
    assert "review ID must be a safe single path component" in review_absolute.stderr
    assert not (tmp_path / "absolute-freeze-id").exists()
    assert not (tmp_path / "absolute-settlement-id").exists()
    assert not (tmp_path / "absolute-review-id").exists()
