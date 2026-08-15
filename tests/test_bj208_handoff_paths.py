"""Issue #208 REWORK v3.1 handoff-path durability tests (PI narrow REJECT).

REWORK v3.1 (PI narrow durability REJECT 1380d42, 2026-08-15): the v3 handoff
serialized `results/issue-208.staging/SHA256SUMS.json` because `_build_handoff`
received the staging output path.  These tests exercise the PRODUCTION entry
point (`verify_handoff_paths` / `verify_package`) and fail closed if:

1. a handoff artifact path references the transient `.staging` directory;
2. a handoff artifact path does not resolve after atomic publication;
3. the runner's `_build_handoff` serializes a canonical post-publication path
   when built inside a staging tree (contract test on the production builder).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from parlay_policy.verify import (  # noqa: E402
    _handoff_ref_in_package,
    verify_handoff_paths,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _mini_handoff() -> dict[str, object]:
    return {
        "handoff_version": "bj208-handoff-for-209-v3.1",
        "fit_boundary": {
            "train_through": "2022",
            "test_2023": True,
            "2024_opened": False,
        },
        "candidate": {"policy": "FROZEN_N7_INCUMBENT", "n": 7, "k": 8},
        "fallback": {"policy": "FROZEN_N7_INCUMBENT", "n": 7, "k": 8},
        "model": {"model_serialized": True},
        "model_file": "results/issue-208/models/fold2_mlp.joblib",
        "package_manifest": "results/issue-208/SHA256SUMS.json",
    }


@pytest.fixture()
def package(tmp_path: Path) -> Path:
    """Final-layout package (canonical name issue-208) with handoff + artifacts."""
    pkg = tmp_path / "issue-208"
    (pkg / "models").mkdir(parents=True)
    (pkg / "SHA256SUMS.json").write_text("{}", encoding="utf-8")
    (pkg / "models" / "fold2_mlp.joblib").write_text("model", encoding="utf-8")
    _write_json(pkg / "handoff_209.json", _mini_handoff())
    return pkg


def test_handoff_paths_accept_canonical_package(package: Path) -> None:
    """Canonical post-publication paths resolve on a final-layout package."""
    failures = verify_handoff_paths(package)
    assert failures == [], failures


def test_handoff_paths_reject_staging_manifest(package: Path) -> None:
    """A `.staging` package_manifest must FAIL the production verifier."""
    handoff = _mini_handoff()
    handoff["package_manifest"] = "results/issue-208.staging/SHA256SUMS.json"
    _write_json(package / "handoff_209.json", handoff)
    failures = verify_handoff_paths(package)
    assert failures, "staging path accepted by verify_handoff_paths"
    assert any(".staging" in f for f in failures), failures


def test_handoff_paths_reject_staging_model_file(package: Path) -> None:
    """A `.staging` model_file must FAIL the production verifier."""
    handoff = _mini_handoff()
    handoff["model_file"] = "results/issue-208.staging/models/fold2_mlp.joblib"
    _write_json(package / "handoff_209.json", handoff)
    failures = verify_handoff_paths(package)
    assert failures, "staging model_file accepted by verify_handoff_paths"


def test_handoff_paths_reject_missing_artifact(package: Path) -> None:
    """An artifact that does not exist after publication must FAIL."""
    handoff = _mini_handoff()
    handoff["model_file"] = "results/issue-208/models/missing.joblib"
    _write_json(package / "handoff_209.json", handoff)
    failures = verify_handoff_paths(package)
    assert failures, "missing artifact accepted by verify_handoff_paths"
    assert any("does not resolve" in f for f in failures), failures


def test_handoff_ref_maps_staging_package_to_canonical_layout(tmp_path: Path) -> None:
    """Ref resolution tolerates the staging dir name while rejecting its use.

    `_handoff_ref_in_package` strips the canonical package-name segment so the
    SAME ref resolves on the staging tree (pre-rename) and the final tree
    (post-rename); the verifier itself rejects `.staging` references.
    """
    staging = tmp_path / "issue-208.staging"
    (staging / "models").mkdir(parents=True)
    (staging / "SHA256SUMS.json").write_text("{}", encoding="utf-8")
    (staging / "models" / "fold2_mlp.joblib").write_text("model", encoding="utf-8")
    target = _handoff_ref_in_package(
        staging, "results/issue-208/SHA256SUMS.json"
    )
    assert target == staging / "SHA256SUMS.json"
    assert target.exists()


def test_build_handoff_serializes_canonical_path(tmp_path: Path) -> None:
    """Runner contract: `_build_handoff` must use the published output path.

    Import the runner module and call the PRODUCTION builder with a staging
    output and the canonical published output; the handoff's package_manifest
    must reference the canonical post-publication location, not `.staging`.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "run_bj208_policy", ROOT / "scripts" / "run_bj208_policy.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    staging = tmp_path / "issue-208.staging"
    published = tmp_path / "issue-208"
    selection = {"frozen_candidate": {"policy": "FROZEN_N7_INCUMBENT"}}
    handoff = mod._build_handoff(
        {"fold2": {"policy_mlp": {}}},
        selection,
        staging,
        published_output=published,
    )
    assert ".staging" not in str(handoff["package_manifest"]), handoff
    assert handoff["package_manifest"] == str(published / "SHA256SUMS.json")
    assert handoff["handoff_version"] == "bj208-handoff-for-209-v4"
