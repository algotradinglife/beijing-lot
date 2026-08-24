from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from src.n6_support_transfer_grid.contract import (
    CELLS,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    PAYOUT_FACTOR,
    STAKE_PER_UNIT_CNY,
)
from src.n6_support_transfer_grid.pipeline import (
    ContractError,
    validate_control_keysets,
    validate_development_diagnostics,
    verify_package,
)
from src.n6_support_shape.pipeline import scientific_frames as support_shape_frames


REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "results/n6_support_transfer_grid"
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


def test_source_bound_replay() -> None:
    assert all(verify_package(REPO, PACKAGE, DATA_ROOT).values())


def test_full_grid_ticket_counts_and_budget() -> None:
    tickets = pd.read_parquet(PACKAGE / "tickets.parquet")
    groups = tickets.groupby(["issue", "cell"], observed=True)
    assert set(tickets["cell"].unique()) == set(CELLS)
    assert groups["units"].sum().eq(FUNDED_UNITS).all()
    assert np.allclose(groups["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-12)
    assert groups["ticket_code"].nunique().eq(groups.size()).all()


def test_nested_disjoint_assignments() -> None:
    assignments = pd.read_parquet(PACKAGE / "assignment_receipts.parquet")
    for _, group in assignments.groupby("issue", observed=True):
        c = group.loc[group["contraction_order"].gt(0), "match_idx"].tolist()
        e = group.loc[group["expansion_order"].gt(0), "match_idx"].tolist()
        assert len(c) == 2 and len(e) == 4 and len(set(c + e)) == 6


def test_c1e1_support_preserves_causal_n6_shape_anchor() -> None:
    parity = pd.read_parquet(PACKAGE / "c1e1_support_parity.parquet")
    assert len(parity) == 172
    assert parity["exact_support"].all()


def test_development_gate_rejects_false_boolean() -> None:
    summary = pd.read_csv(PACKAGE / "development_diagnostic_gate.csv")
    summary["nonnegative_monotonicity"] = summary["nonnegative_monotonicity"].astype(bool)
    summary.loc[0, "nonnegative_monotonicity"] = False
    with pytest.raises(ContractError):
        validate_development_diagnostics(summary)


def test_control_keyset_rejects_missing_row() -> None:
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    grid = bundles[bundles["cell"].eq("C0E0")].copy()
    upstream = support_shape_frames(REPO, DATA_ROOT)["bundles"]
    upstream = upstream[upstream["shape"].eq("CONTROL")].copy()
    with pytest.raises(ContractError):
        validate_control_keysets(grid.iloc[1:].copy(), upstream)


def test_payout_and_profitability_identities() -> None:
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    attribution = pd.read_parquet(PACKAGE / "support_attribution.parquet")
    tickets = pd.read_parquet(PACKAGE / "tickets.parquet")
    assert np.allclose(bundles["pnl_cny"], bundles["gross_cny"] - ISSUE_STAKE_CNY, rtol=0, atol=1e-9)
    assert bundles["issue_gross_positive"].eq(bundles["gross_cny"].gt(0)).all()
    assert bundles["issue_profitable"].eq(bundles["pnl_cny"].gt(0)).all()
    settled = attribution.groupby(["issue", "cell"], observed=True).agg(
        winning_code=("result_code", lambda values: "|".join(values.astype(str))),
        winning_sp_product=("winning_sp", "prod"),
    ).reset_index()
    winning_tickets = tickets.merge(
        settled,
        left_on=["issue", "cell", "ticket_code"],
        right_on=["issue", "cell", "winning_code"],
        how="inner",
        validate="many_to_one",
    )
    winning_tickets["independent_gross_cny"] = (
        winning_tickets["units"]
        * STAKE_PER_UNIT_CNY
        * PAYOUT_FACTOR
        * winning_tickets["winning_sp_product"]
    )
    independent = winning_tickets.groupby(["issue", "cell"], observed=True)[
        "independent_gross_cny"
    ].sum()
    actual = bundles.set_index(["issue", "cell"])["gross_cny"]
    expected = actual.copy() * 0.0
    expected.loc[independent.index] = independent
    assert np.allclose(actual, expected, rtol=0, atol=1e-9)


@pytest.mark.parametrize("kind", ["assignment", "ticket", "settlement", "gate"])
def test_coordinated_tamper_rejected(tmp_path: Path, kind: str) -> None:
    package = _copy(tmp_path)
    if kind == "assignment":
        relative = "assignment_receipts.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "contraction_order"] = 2
        frame.to_parquet(package / relative, index=False)
    elif kind == "ticket":
        relative = "tickets.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "units"] += 1
        frame.to_parquet(package / relative, index=False)
    elif kind == "settlement":
        relative = "issue_bundles.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "gross_cny"] += 1.0
        frame.loc[0, "pnl_cny"] += 1.0
        frame.to_parquet(package / relative, index=False)
    else:
        relative = "historical_gate.csv"
        frame = pd.read_csv(package / relative)
        frame.loc[0, "historical_gate_pass"] = True
        frame.to_csv(package / relative, index=False)
    _rehash(package, relative)
    with pytest.raises(ContractError):
        verify_package(REPO, package, DATA_ROOT)
