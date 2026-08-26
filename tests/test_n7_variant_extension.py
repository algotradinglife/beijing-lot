from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.n7_variant_extension.contract import (
    BOOTSTRAP_DRAWS,
    ISSUE_STAKE_CNY,
    PAYOUT_FACTOR,
)
from src.n7_variant_extension.pipeline import (
    ContractError,
    PACKAGE_FILES,
    _arm_ex_largest,
    _bootstrap_p05,
    _expected_variant_contract,
    _path_metrics,
    _read,
    _semantic_verify,
    _verify_extension_tickets,
    _verify_mapping_receipts,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _stored() -> dict[str, object]:
    package = REPO_ROOT / "results/n7_variant_extension"
    return {key: _read(package / name) for name, key in PACKAGE_FILES.items()}


def test_ticket_level_once_payout_semantics() -> None:
    units = 4
    product_sp = 9.5
    assert units * 2.0 * PAYOUT_FACTOR * product_sp == 49.4


def test_armwise_ex_largest_differs_from_paired_delta_sensitivity() -> None:
    paired = pd.DataFrame(
        {
            "issue": ["a", "b", "c"],
            "issue_anchor_ts": pd.date_range("2025-01-01", periods=3, tz="UTC"),
            "pnl_a": [-100.0, 300.0, -50.0],
            "gross_a": [924.0, 1324.0, 974.0],
            "pnl_b": [250.0, -100.0, -50.0],
            "gross_b": [1274.0, 924.0, 974.0],
        }
    )
    a = _arm_ex_largest(
        paired.rename(columns={"pnl_a": "pnl_cny", "gross_a": "gross_cny"})
    )
    b = _arm_ex_largest(
        paired.rename(columns={"pnl_b": "pnl_cny", "gross_b": "gross_cny"})
    )
    delta = paired.pnl_a.to_numpy() - paired.pnl_b.to_numpy()
    sensitivity = float(delta.sum() - delta[np.argmax(np.abs(delta))])
    assert a - b != sensitivity


def test_bootstrap_is_paired_mean_per_issue_and_deterministic() -> None:
    delta = np.array([-10.0, 20.0, 30.0, -5.0])
    first = _bootstrap_p05(delta, 400123)
    second = _bootstrap_p05(delta, 400123)
    assert first == second
    assert BOOTSTRAP_DRAWS == 5_000


def test_path_metrics_use_issue_budget_and_capital_path() -> None:
    frame = pd.DataFrame(
        {
            "issue": ["a", "b", "c"],
            "issue_anchor_ts": pd.date_range("2025-01-01", periods=3, tz="UTC"),
            "pnl_cny": [-ISSUE_STAKE_CNY, -ISSUE_STAKE_CNY, 3_000.0],
            "gross_cny": [0.0, 0.0, ISSUE_STAKE_CNY + 3_000.0],
        }
    )
    result = _path_metrics(frame)
    assert result["longest_profitable_issue_losing_run"] == 2
    assert result["max_drawdown_cny"] == 2 * ISSUE_STAKE_CNY


def test_exact_preregistered_variant_registry_has_21_cells() -> None:
    contract = _expected_variant_contract()
    assert len(contract) == 21
    assert contract["R3_C2E3_EQUAL"]["ticket_count"] == 108
    assert contract["MIX_R3_C0E0_C1E3_50_50_EQUAL"]["ticket_count"] == 344


def test_committed_package_passes_full_semantic_verifier() -> None:
    _semantic_verify(REPO_ROOT, _stored())


def test_ticket_unit_or_gross_tamper_is_rejected() -> None:
    stored = _stored()
    tickets = stored["tickets"].copy()
    tickets.loc[tickets.index[0], "units"] += 1
    with pytest.raises(ContractError):
        _verify_extension_tickets(
            stored["bundles"], tickets, stored["attribution"]
        )

    bundles = stored["bundles"].copy()
    mask = bundles["issue_year"].isin((2025, 2026)) & bundles["native_included"]
    bundles.loc[bundles.index[mask][0], "gross_cny"] += 1.0
    with pytest.raises(ContractError):
        _verify_extension_tickets(
            bundles, stored["tickets"], stored["attribution"]
        )


def test_missing_ticket_group_is_rejected() -> None:
    stored = _stored()
    first = stored["tickets"].iloc[0]
    tickets = stored["tickets"][
        ~(
            stored["tickets"]["issue"].astype(str).eq(str(first["issue"]))
            & stored["tickets"]["variant"].eq(str(first["variant"]))
        )
    ]
    with pytest.raises(ContractError, match="key sets differ"):
        _verify_extension_tickets(
            stored["bundles"], tickets, stored["attribution"]
        )


def test_cutoff_receipt_rejects_future_label_and_cross_target_identity() -> None:
    stored = _stored()
    receipt_mutation = copy.deepcopy(stored)
    item = receipt_mutation["mapping_receipts"][0]
    item["receipt"]["maximum_training_label_timestamp"] = item["receipt"][
        "cutoff_ts"
    ]
    with pytest.raises(ContractError, match="at or after"):
        _verify_mapping_receipts(receipt_mutation)

    identity_mutation = copy.deepcopy(stored)
    identity_mutation["mapping_receipts"][0]["receipt"]["cutoff_identity"] = (
        "DECISION_EPOCH_LATER_ISSUE"
    )
    with pytest.raises(ContractError, match="target issue"):
        _verify_mapping_receipts(identity_mutation)


def test_mapping_receipts_cover_all_policy_issue_pairs() -> None:
    stored = _stored()
    _verify_mapping_receipts(stored)
    assert len(stored["mapping_receipts"]) == 366
    assert len(stored["weights"]) == 366
