from __future__ import annotations

import json
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


def test_tampered_freeze_is_rejected(tmp_path: Path) -> None:
    output = freeze(tmp_path)
    with (output / "decision/decision.csv").open("a", encoding="utf-8") as handle:
        handle.write("2,1\n")
    with pytest.raises(protocol.ResearchFreezeError, match="checksum mismatch"):
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
