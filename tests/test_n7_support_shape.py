from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from src.n7_support_shape.contract import FUNDED_UNITS, ISSUE_STAKE_CNY, PAYOUT_FACTOR, TICKET_COUNTS
from src.n7_support_shape.pipeline import ContractError, verify_package


REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "results/n7_support_shape"
DATA_ROOT = Path("/home/drwho1985/workspace/soccer/beijing-lot/data")


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(PACKAGE, target)
    return target


def _rehash(package: Path, relative: str) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = (package / relative).read_bytes()
    manifest["files"][relative] = {
        "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_committed_package_source_bound_replay() -> None:
    assert all(verify_package(REPO, PACKAGE, DATA_ROOT).values())


def test_ticket_counts_budget_and_uniqueness() -> None:
    tickets = pd.read_parquet(PACKAGE / "tickets.parquet")
    groups = tickets.groupby(["issue", "base", "shape"], observed=True)
    for (_, _, shape), count in groups.size().items():
        assert count == TICKET_COUNTS[shape]
    assert groups["ticket_code"].nunique().eq(groups.size()).all()
    assert groups["units"].sum().eq(FUNDED_UNITS).all()
    assert np.allclose(groups["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-12)


def test_shape_pair_is_disjoint_and_shared() -> None:
    decisions = pd.read_parquet(PACKAGE / "decisions.parquet")
    groups = decisions.groupby(["issue", "base"], observed=True)
    assert groups["contraction_match_idx"].nunique().eq(1).all()
    assert groups["expansion_match_idx"].nunique().eq(1).all()
    assert (decisions["contraction_match_idx"] != decisions["expansion_match_idx"]).all()


def test_control_exactly_reproduces_366() -> None:
    parity = pd.read_parquet(PACKAGE / "control_parity.parquet")
    assert parity[["exact_pnl", "exact_gross", "exact_hit"]].all().all()


def test_payout_factor_once_and_pnl_identity() -> None:
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    attribution = pd.read_parquet(PACKAGE / "support_attribution.parquet")
    assert np.allclose(bundles["pnl_cny"], bundles["gross_cny"] - ISSUE_STAKE_CNY, rtol=0, atol=1e-9)
    for row in bundles[bundles["hit"]].head(50).itertuples():
        legs = attribution[
            attribution["issue"].eq(row.issue)
            & attribution["base"].eq(row.base)
            & attribution["shape"].eq(row.shape)
        ]
        expected = row.winning_ticket_units * 2.0 * PAYOUT_FACTOR * legs["winning_sp"].prod()
        assert row.gross_cny == pytest.approx(expected, rel=0, abs=1e-9)


def test_development_diagnostic_excludes_exposed_years() -> None:
    receipt = json.loads((PACKAGE / "source_receipt.json").read_text(encoding="utf-8"))
    assert receipt["development"]["years"] == [2017, 2018, 2019, 2020, 2021]
    assert receipt["development"]["no_2022_2024_selection"] is True


@pytest.mark.parametrize("kind", ["ticket", "pnl", "pair", "receipt", "admission"])
def test_coordinated_tamper_is_rejected(tmp_path: Path, kind: str) -> None:
    package = _copy(tmp_path)
    if kind == "ticket":
        relative = "tickets.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "units"] += 1
        frame.to_parquet(package / relative, index=False)
    elif kind == "pnl":
        relative = "issue_bundles.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "pnl_cny"] += 1.0
        frame.to_parquet(package / relative, index=False)
    elif kind == "pair":
        relative = "shape_pair_receipts.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "chosen_contraction"] = not bool(frame.loc[0, "chosen_contraction"])
        frame.to_parquet(package / relative, index=False)
    elif kind == "receipt":
        relative = "source_receipt.json"
        receipt = json.loads((package / relative).read_text(encoding="utf-8"))
        receipt["corrected_chronology"] = "FORGED"
        (package / relative).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        relative = "expert_admission.csv"
        frame = pd.read_csv(package / relative)
        frame.loc[0, "admitted"] = True
        frame.to_csv(package / relative, index=False)
    _rehash(package, relative)
    with pytest.raises(ContractError):
        verify_package(REPO, package, DATA_ROOT)
