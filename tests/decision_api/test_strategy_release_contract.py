from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
RELEASE_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DECISION_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.(?:[0-9]{4}|[0-9]+)$")
RELEASE_ID = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*_[0-9]{4}_[0-9]{2}_[0-9]{2}$")
sys.path.insert(0, str(ROOT))

from scripts.validate_strategy_release import validate_strategy_release  # noqa: E402
from src.decision_api import app as appmod  # noqa: E402


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_iso_datetime(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None


def _assert_release_contract(registry: dict[str, Any]) -> None:
    assert registry["schema_version"] == "strategy_release_registry_v1"
    assert registry["active_release_id"] in registry["releases"]

    for release_id, release in registry["releases"].items():
        assert RELEASE_ID.fullmatch(release_id)
        assert release["release_id"] == release_id
        assert RELEASE_ID.fullmatch(release["release_id"])
        assert RELEASE_VERSION.fullmatch(release["version_id"])
        assert release["status"] in {"active", "shadow", "draft", "superseded", "archived"}
        assert release["owner"]
        assert release["strategy_family"]
        _assert_iso_datetime(release["generated_at"])
        assert release["effective_from_issue"]

        artifact_scope = release["artifact_scope"]
        for key in ("historical_data_start", "backtest_through_issue", "live_issue_policy", "freeze_policy"):
            assert artifact_scope[key]

        snapshots = release["snapshot_timestamps"]
        for key in ("probability_model", "q_model", "confidence_model", "decision_chain"):
            _assert_iso_datetime(snapshots[key])

        versions = release["model_versions"]
        for key in ("probability_model", "q_model", "decision_chain", "shadow_decision_chain"):
            assert versions[key]

        artifacts = release["artifacts"]
        for key in ("main_strategy_dir", "ticket_pool_csv", "joint_leg_rows_csv"):
            assert artifacts[key]
            assert not Path(artifacts[key]).is_absolute()

        assert release["required_artifacts"]
        assert release["main_strategy_arms"]

        variants = release["decision_variants"]
        assert any(item["kind"] == "active" for item in variants)
        assert sum(1 for item in variants if item["is_default"]) == 1
        for variant in variants:
            assert variant["variant_id"]
            assert DECISION_VERSION.fullmatch(variant["version_id"])
            assert variant["kind"] in {"active", "shadow", "draft"}
            assert isinstance(variant["selectable"], bool)
            assert isinstance(variant["is_default"], bool)
            if variant["kind"] == "shadow":
                assert variant["artifact_key"] in artifacts

        assert isinstance(release["promotion"]["validated"], bool)
        assert release["validation"]["no_future_leakage"] is True


def test_strategy_release_contract_schema_and_example_are_valid_json() -> None:
    schema = _load_json(ROOT / "schemas/strategy_release_registry_v1.schema.json")
    example = _load_json(ROOT / "tests/fixtures/strategy_release/strategy_release_manifest.example.json")

    assert schema["title"] == "Beijing Lot strategy release registry v1"
    _assert_release_contract(example)


def test_current_strategy_release_config_follows_contract() -> None:
    registry = _load_json(ROOT / "config/strategy_release.json")

    _assert_release_contract(registry)


def _write_registry(tmp_path: Path, registry: dict[str, Any]) -> Path:
    path = tmp_path / "strategy_release.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (
            lambda registry: registry.update({"active_release_id": "missing_release"}),
            "active_release_id not found in releases",
        ),
        (
            lambda registry: next(
                item
                for item in next(iter(registry["releases"].values()))["decision_variants"]
                if item["kind"] == "shadow"
            ).pop("artifact_key"),
            "must set artifact_key",
        ),
        (
            lambda registry: next(iter(registry["releases"].values())).__setitem__("generated_at", "not-a-date-time"),
            "generated_at must be ISO datetime",
        ),
        (
            lambda registry: next(iter(registry["releases"].values()))["snapshot_timestamps"].pop("q_model"),
            "snapshot_timestamps.q_model must be ISO datetime",
        ),
    ],
)
def test_strategy_release_validator_rejects_contract_breakers(
    tmp_path: Path,
    mutator: Any,
    expected_error: str,
) -> None:
    registry = _load_json(ROOT / "tests/fixtures/strategy_release/strategy_release_manifest.example.json")
    mutator(registry)
    path = _write_registry(tmp_path, registry)

    report = validate_strategy_release(path, allow_missing=True)

    assert report["ok"] is False
    assert any(expected_error in error for error in report["errors"])


def test_strategy_release_runtime_exposes_invalid_active_release_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry = _load_json(ROOT / "config/strategy_release.json")
    registry["active_release_id"] = "missing_release"
    config_path = _write_registry(tmp_path, registry)
    monkeypatch.setattr(appmod, "STRATEGY_RELEASE_CONFIG", config_path)
    appmod._strategy_release_registry.cache_clear()

    try:
        payload = appmod._strategy_release_public_payload()
    finally:
        appmod._strategy_release_registry.cache_clear()

    assert payload["configured_active_release_id"] == "missing_release"
    assert payload["fallback_used"] is True
    assert payload["release_load_status"] == "degraded"
    assert "missing_release" in payload["release_load_error"]
