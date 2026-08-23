from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from src.value_veto_r3_n7.contract import (
    ISSUE_STAKE_CNY,
    MAX_RETAINED_MASS_DROP,
    PAYOUT_FACTOR,
)
from src.value_veto_r3_n7.pipeline import (
    _frame_sha,
    sha256_file,
    select_with_veto,
    settle_bundles,
    validate_action_inputs,
    verify_package,
)


def _selector_rows() -> pd.DataFrame:
    rows = []
    for index in range(1, 10):
        rows.append({
            "issue": "23001", "issue_year": 2023, "issue_anchor_ts": "2023-01-01",
            "match_idx": index, "retained_mass": .90 - index / 100,
            "g_point": 1.0, "g_lcb": .95, "g_ucb": 1.05,
        })
    return pd.DataFrame(rows)


def test_veto_requires_strict_interval_dominance() -> None:
    rows = _selector_rows()
    selected, ledger = select_with_veto(rows)
    assert set(selected["match_idx"]) == set(range(1, 8))
    assert ledger.empty


def test_veto_accepts_dominance_with_bounded_mass_loss() -> None:
    rows = _selector_rows()
    rows.loc[rows["match_idx"].eq(8), ["g_point", "g_lcb", "g_ucb"]] = [1.3, 1.2, 1.4]
    selected, ledger = select_with_veto(rows)
    assert 8 in set(selected["match_idx"])
    assert 7 not in set(selected["match_idx"])
    assert len(ledger) == 1
    assert ledger.iloc[0]["retained_mass_delta"] >= -MAX_RETAINED_MASS_DROP


def test_veto_rejects_excess_probability_loss() -> None:
    rows = _selector_rows()
    rows.loc[rows["match_idx"].eq(8), ["retained_mass", "g_lcb", "g_ucb"]] = [.20, 2.0, 2.1]
    selected, ledger = select_with_veto(rows)
    assert 8 not in set(selected["match_idx"])
    assert ledger.empty


def test_settlement_enumerates_128_unique_tickets_and_applies_factor_once() -> None:
    support = {str(index): ["3", "1"] for index in range(1, 8)}
    frozen = pd.DataFrame([{
        "issue": "23001", "issue_year": 2023, "issue_anchor_ts": "2023-01-01",
        "cell": cell, "selector": "S0", "r": 0,
        "selected_match_ids": "|".join(map(str, range(1, 8))),
        "support_json": json.dumps(support, sort_keys=True, separators=(",", ":")),
        "replacement_count": 0, "mean_retained_mass": .8, "min_retained_mass": .75,
        "portfolio_g_point": 1.0, "portfolio_g_lcb": .5, "portfolio_g_ucb": 1.5,
        "portfolio_diagnostic": .65, "activated_changes": 0,
        "ticket_count": 128, "funded_units": 512, "stake_cny": ISSUE_STAKE_CNY,
    } for cell in ("S0R0A0", "S0R3A0", "SVR0A0", "SVR3A0")])
    labels = pd.DataFrame([{
        "issue_code": "23001", "match_idx": index, "result_code": "3", "winning_sp": 2.0,
        "has_trusted_settlement": 1,
    } for index in range(1, 8)])
    bundles, tickets, _ = settle_bundles(frozen, labels)
    assert tickets.groupby("cell")["ticket_code"].nunique().eq(128).all()
    assert tickets.groupby("cell")["stake_cny"].sum().eq(ISSUE_STAKE_CNY).all()
    expected = 2.0 * 4 * PAYOUT_FACTOR * 2.0**7
    assert np.allclose(bundles["gross_cny"], expected, rtol=0, atol=1e-12)


def test_untrusted_settlement_fails_closed() -> None:
    support = {str(index): ["3", "1"] for index in range(1, 8)}
    frozen = pd.DataFrame([{
        "issue": "23001", "issue_year": 2023, "issue_anchor_ts": "2023-01-01",
        "cell": cell, "selector": "S0", "r": 0,
        "selected_match_ids": "1|2|3|4|5|6|7", "support_json": json.dumps(support),
        "replacement_count": 0, "mean_retained_mass": .8, "min_retained_mass": .75,
        "portfolio_g_point": 1.0, "portfolio_g_lcb": .5, "portfolio_g_ucb": 1.5,
        "portfolio_diagnostic": .65, "activated_changes": 0,
        "ticket_count": 128, "funded_units": 512, "stake_cny": ISSUE_STAKE_CNY,
    } for cell in ("S0R0A0", "S0R3A0", "SVR0A0", "SVR3A0")])
    labels = pd.DataFrame([{
        "issue_code": "23001", "match_idx": index, "result_code": "3", "winning_sp": 2.0,
        "has_trusted_settlement": int(index != 7),
    } for index in range(1, 8)])
    bundles, tickets, attribution = settle_bundles(frozen, labels)
    assert bundles.empty and tickets.empty and attribution.empty


def test_action_input_rejects_string_boolean() -> None:
    actions = pd.DataFrame({
        "support_changed": ["False"], "baseline_support": ["31"],
        "q_eu_3": [.5], "q_eu_1": [.3], "q_eu_0": [.2],
        "q_line_3": [.4], "q_line_1": [.35], "q_line_0": [.25],
    })
    with np.testing.assert_raises(TypeError):
        validate_action_inputs(actions)


def test_action_input_rejects_negative_probability() -> None:
    actions = pd.DataFrame({
        "support_changed": [False], "baseline_support": ["31"], "qeu_support": ["30"],
        "q_eu_3": [-1.0], "q_eu_1": [1.0], "q_eu_0": [1.0],
        "q_line_3": [.4], "q_line_1": [.35], "q_line_0": [.25],
    })
    with np.testing.assert_raises(ValueError):
        validate_action_inputs(actions)


def test_trusted_invalid_result_domain_is_rejected() -> None:
    support = {str(index): ["3", "1"] for index in range(1, 8)}
    frozen = pd.DataFrame([{
        "issue": "23001", "issue_year": 2023, "issue_anchor_ts": "2023-01-01",
        "cell": cell, "selector": "S0", "r": 0,
        "selected_match_ids": "1|2|3|4|5|6|7", "support_json": json.dumps(support),
        "replacement_count": 0, "mean_retained_mass": .8, "min_retained_mass": .75,
        "portfolio_g_point": 1.0, "portfolio_g_lcb": .5, "portfolio_g_ucb": 1.5,
        "portfolio_diagnostic": .65, "activated_changes": 0,
        "ticket_count": 128, "funded_units": 512, "stake_cny": ISSUE_STAKE_CNY,
    } for cell in ("S0R0A0", "S0R3A0", "SVR0A0", "SVR3A0")])
    labels = pd.DataFrame([{
        "issue_code": "23001", "match_idx": index,
        "result_code": "X" if index == 7 else "3", "winning_sp": 2.0,
        "has_trusted_settlement": 1,
    } for index in range(1, 8)])
    with np.testing.assert_raises(ValueError):
        settle_bundles(frozen, labels)


def _copy_committed_package(repo_root: Path, target_root: Path) -> Path:
    source_output = repo_root / "results/value_veto_r3_n7"
    manifest = json.loads((source_output / "MANIFEST.json").read_text())
    for relative in manifest["files"]:
        source = repo_root / relative
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    target_output = target_root / "results/value_veto_r3_n7"
    shutil.copy2(source_output / "MANIFEST.json", target_output / "MANIFEST.json")
    return target_output


def test_verifier_rejects_empty_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output = _copy_committed_package(repo_root, tmp_path)
    (output / "MANIFEST.json").write_text('{"contract":"FORGED","files":{}}\n')
    with np.testing.assert_raises(AssertionError):
        verify_package(tmp_path, output)


def test_verifier_rejects_funding_tamper_even_with_rehashed_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output = _copy_committed_package(repo_root, tmp_path)
    ticket_path = output / "tickets.parquet"
    tickets = pd.read_parquet(ticket_path)
    for _, indices in tickets.groupby(["issue", "issue_year", "cell"]).groups.items():
        first, second = list(indices)[:2]
        tickets.loc[first, ["units", "stake_cny"]] = [3, 6.0]
        tickets.loc[second, ["units", "stake_cny"]] = [5, 10.0]
    tickets.to_parquet(ticket_path, index=False)
    manifest_path = output / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    relative = "results/value_veto_r3_n7/tickets.parquet"
    manifest["files"][relative] = {
        "sha256": sha256_file(ticket_path), "bytes": ticket_path.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with np.testing.assert_raises(AssertionError):
        verify_package(tmp_path, output)


def test_verifier_rejects_missing_ticket_group_even_with_rehashed_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output = _copy_committed_package(repo_root, tmp_path)
    ticket_path = output / "tickets.parquet"
    tickets = pd.read_parquet(ticket_path)
    first = tickets.iloc[0]
    keep = ~(
        tickets["issue"].astype(str).eq(str(first["issue"]))
        & tickets["issue_year"].eq(first["issue_year"])
        & tickets["cell"].eq(first["cell"])
    )
    tickets.loc[keep].to_parquet(ticket_path, index=False)
    manifest_path = output / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    relative = "results/value_veto_r3_n7/tickets.parquet"
    manifest["files"][relative] = {
        "sha256": sha256_file(ticket_path), "bytes": ticket_path.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with np.testing.assert_raises(AssertionError):
        verify_package(tmp_path, output)


def test_verifier_rejects_pnl_tamper_even_with_rehashed_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output = _copy_committed_package(repo_root, tmp_path)
    bundle_path = output / "issue_bundles.parquet"
    bundles = pd.read_parquet(bundle_path)
    bundles.loc[bundles.index[0], "pnl_cny"] += 12_345.0
    bundles.to_parquet(bundle_path, index=False)
    manifest_path = output / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    relative = "results/value_veto_r3_n7/issue_bundles.parquet"
    manifest["files"][relative] = {
        "sha256": sha256_file(bundle_path), "bytes": bundle_path.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with np.testing.assert_raises(AssertionError):
        verify_package(tmp_path, output)


def test_verifier_rejects_interval_tamper_even_with_rehashed_manifest(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output = _copy_committed_package(repo_root, tmp_path)
    receipt_path = output / "sp_interval_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["intervals"]["3"]["low"] -= 0.1
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    manifest_path = output / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    relative = "results/value_veto_r3_n7/sp_interval_receipt.json"
    manifest["files"][relative] = {
        "sha256": sha256_file(receipt_path), "bytes": receipt_path.stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with np.testing.assert_raises(AssertionError):
        verify_package(tmp_path, output)


def test_verifier_rejects_coordinated_settlement_label_tamper(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output = _copy_committed_package(repo_root, tmp_path)
    label_path = output / "evaluation_labels.parquet"
    labels = pd.read_parquet(label_path)
    labels.loc[labels.index[0], "winning_sp"] *= 1.1
    labels.to_parquet(label_path, index=False)
    receipt_path = output / "settlement_source_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["evaluation_label_frame_sha256"] = _frame_sha(labels, list(labels.columns))
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    manifest_path = output / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    for name, path in (
        ("evaluation_labels.parquet", label_path),
        ("settlement_source_receipt.json", receipt_path),
    ):
        relative = f"results/value_veto_r3_n7/{name}"
        manifest["files"][relative] = {
            "sha256": sha256_file(path), "bytes": path.stat().st_size,
        }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with np.testing.assert_raises(AssertionError):
        verify_package(tmp_path, output)
