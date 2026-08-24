from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pandas as pd
import pytest

from src.cutoff_hardening.package import (
    HardeningContractError,
    build_package,
    sha256_file,
    verify_package,
)
from src.temporal_learning import (
    AvailabilityFilter,
    AvailabilityPolicy,
    Cutoff,
    TemporalContractError,
    WeightingPolicy,
    prepare_learning_context,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ.get("BJ_DATA_ROOT", ROOT / "data"))


@pytest.fixture(scope="module")
def package(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not DATA_ROOT.is_dir():
        pytest.skip("canonical research data root is not available")
    target = tmp_path_factory.mktemp("bj388") / "package"
    build_package(ROOT, target, DATA_ROOT, force=True)
    return target


def test_real_source_bound_package_replays(package: Path) -> None:
    assert all(verify_package(ROOT, package, DATA_ROOT).values())


def test_manifest_tamper_fails(package: Path, tmp_path: Path) -> None:
    target = tmp_path / "package"
    shutil.copytree(package, target)
    decision = json.loads((target / "decision.json").read_text())
    decision["prospective_authorized"] = True
    (target / "decision.json").write_text(json.dumps(decision))
    manifest = json.loads((target / "MANIFEST.json").read_text())
    manifest["files"]["decision.json"] = {
        "bytes": (target / "decision.json").stat().st_size,
        "sha256": sha256_file(target / "decision.json"),
    }
    (target / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    with pytest.raises(HardeningContractError):
        verify_package(ROOT, target, DATA_ROOT)


def test_target_issue_excluded_even_with_early_label() -> None:
    history = pd.DataFrame(
        {
            "issue_code": ["2018-1", "2019-1", "2020-1", "2021-1", "2022-1"],
            "issue_year": [2018, 2019, 2020, 2021, 2022],
            "label_available_ts": pd.to_datetime(
                [
                    "2018-01-02T00:00:00Z",
                    "2019-01-02T00:00:00Z",
                    "2020-01-02T00:00:00Z",
                    "2021-01-02T00:00:00Z",
                    "2021-12-01T00:00:00Z",
                ]
            ),
        }
    )
    context = prepare_learning_context(
        history,
        Cutoff.decision_epoch("2022-1", "2022-01-01T00:00:00Z"),
        source_hashes={"history": "abc"},
        repository_root=ROOT,
        implementation_modules=("src.cutoff_hardening.package",),
        availability=AvailabilityFilter(AvailabilityPolicy.observed("TEST")),
        intended_use="HISTORICAL_DIAGNOSTIC",
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=1),
    )
    assert "2022-1" not in set(context.eligible["issue_code"])
    assert context.receipt.payload["target_rows_excluded"] == 1


def test_proxy_cannot_authorize_prospective() -> None:
    history = pd.DataFrame(
        {
            "issue_code": ["2018-1", "2019-1", "2020-1"],
            "issue_year": [2018, 2019, 2020],
            "label_available_ts": pd.to_datetime(
                [
                    "2018-01-02T00:00:00Z",
                    "2019-01-02T00:00:00Z",
                    "2020-01-02T00:00:00Z",
                ]
            ),
        }
    )
    with pytest.raises(TemporalContractError, match="prospective"):
        prepare_learning_context(
            history,
            Cutoff.evaluation_year(2021, "2021-01-01T00:00:00Z"),
            source_hashes={"history": "abc"},
            repository_root=ROOT,
            implementation_modules=("src.cutoff_hardening.package",),
            availability=AvailabilityFilter(
                AvailabilityPolicy.historical_proxy("PROXY")
            ),
            intended_use="PROSPECTIVE_DECISION",
            weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=1),
        )


def test_conservative_boundary_applies_safety_margin() -> None:
    history = pd.DataFrame(
        {
            "issue_code": ["2018-1", "2019-1", "2020-1", "2020-2"],
            "issue_year": [2018, 2019, 2020, 2020],
            "label_available_ts": pd.to_datetime(
                [
                    "2018-01-02T00:00:00Z",
                    "2019-01-02T00:00:00Z",
                    "2020-01-02T00:00:00Z",
                    "2021-01-01T11:30:00Z",
                ]
            ),
        }
    )
    context = prepare_learning_context(
        history,
        Cutoff.evaluation_year(2021, "2021-01-01T12:00:00Z"),
        source_hashes={"history": "abc"},
        repository_root=ROOT,
        implementation_modules=("src.cutoff_hardening.package",),
        availability=AvailabilityFilter(
            AvailabilityPolicy.conservative_boundary("ONE_HOUR", 3_600)
        ),
        intended_use="PROSPECTIVE_DECISION",
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=1),
    )
    assert "2020-2" not in set(context.eligible["issue_code"])
    assert context.receipt.payload["availability"]["admissibility_boundary_ts"] == (
        "2021-01-01T11:00:00+00:00"
    )
