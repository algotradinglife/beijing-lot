from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from src.n6_chronology_sync.contract import PAYOUT_FACTOR, STAKE_PER_TICKET_CNY
from src.n6_chronology_sync.pipeline import ContractError, verify_package


REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "results/n6_chronology_sync"
DATA_ROOT = Path("/home/drwho1985/workspace/soccer/beijing-lot/data")


def _rehash(package: Path, relative: str) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = (package / relative).read_bytes()
    manifest["files"][relative] = {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(PACKAGE, target)
    return target


def test_committed_package_source_bound_replay() -> None:
    checks = verify_package(REPO, PACKAGE, DATA_ROOT)
    assert all(checks.values())


def test_exact_ticket_budget_and_cartesian() -> None:
    tickets = pd.read_parquet(PACKAGE / "tickets.parquet")
    groups = tickets.groupby(["issue", "arm"], observed=True)
    assert groups.size().eq(64).all()
    assert groups["ticket_code"].nunique().eq(64).all()
    assert groups["units"].sum().eq(512).all()
    assert np.allclose(groups["stake_cny"].sum(), 1_024.0, rtol=0, atol=1e-12)


def test_r3_uses_only_issue_relative_top_three_pressure() -> None:
    attribution = pd.read_parquet(PACKAGE / "support_attribution.parquet")
    r3 = attribution[attribution["arm"].eq("R3")]
    expected = np.where(r3["pressure_rank"].le(3), r3["qeu_support"], r3["baseline_support"])
    assert np.array_equal(r3["active_support"].to_numpy(), expected)


def test_payout_factor_is_applied_once_per_winning_ticket() -> None:
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    attribution = pd.read_parquet(PACKAGE / "support_attribution.parquet")
    winners = bundles[bundles["hit"]]
    for row in winners.itertuples():
        legs = attribution[
            attribution["issue"].eq(row.issue) & attribution["arm"].eq(row.arm)
        ]
        expected = STAKE_PER_TICKET_CNY * PAYOUT_FACTOR * legs["winning_sp"].prod()
        assert row.gross_cny == pytest.approx(expected, rel=0, abs=1e-9)


def test_corrected_registry_and_temporal_receipts() -> None:
    actions = pd.read_parquet(PACKAGE / "action_receipts.parquet")
    assert actions["issue_date_source"].eq("SOURCE_ISSUE_REGISTRY_YEAR").all()
    assert (
        pd.to_datetime(actions["training_label_available_max_ts"], utc=True)
        < pd.to_datetime(actions["fixture_decision_ts"], utc=True)
    ).all()


@pytest.mark.parametrize("kind", ["ticket", "pnl", "missing_group", "receipt"])
def test_coordinated_tamper_fails_source_replay(tmp_path: Path, kind: str) -> None:
    package = _copy(tmp_path)
    if kind == "ticket":
        relative = "tickets.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "ticket_code"] = "0|0|0|0|0|0"
        frame.to_parquet(package / relative, index=False)
    elif kind == "pnl":
        relative = "issue_bundles.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "pnl_cny"] += 1.0
        frame.to_parquet(package / relative, index=False)
    elif kind == "missing_group":
        relative = "tickets.parquet"
        frame = pd.read_parquet(package / relative)
        first = frame.iloc[0]
        frame = frame[~(frame["issue"].eq(first.issue) & frame["arm"].eq(first.arm))]
        frame.to_parquet(package / relative, index=False)
    else:
        relative = "source_receipt.json"
        receipt = json.loads((package / relative).read_text(encoding="utf-8"))
        receipt["chronology"] = "FORGED"
        (package / relative).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rehash(package, relative)
    with pytest.raises(ContractError):
        verify_package(REPO, package, DATA_ROOT)
