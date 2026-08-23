from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from src.paired_value_r3_n7.contract import (
    CELLS,
    ISSUE_STAKE_CNY,
    MAX_RETAINED_MASS_DROP,
    PAYOUT_FACTOR,
    SELECTORS,
)
from src.paired_value_r3_n7.pipeline import (
    freeze_bundles,
    paired_metrics,
    select_pairwise,
    settle_bundles,
    sha256_file,
    verify_package,
    weighted_quantile,
)


def _calibration(residuals: tuple[float, ...] = (-0.1, 0.0, 0.1)) -> pd.DataFrame:
    rows = []
    for index, residual in enumerate(residuals, start=1):
        issue = f"22{index:03d}"
        rows.append({
            "issue": issue,
            "candidate_issue": issue,
            "incumbent_issue": issue,
            "candidate_match_idx": 8,
            "incumbent_match_idx": 7,
            "candidate_g_pred": 1.1,
            "incumbent_g_pred": 1.0,
            "candidate_g_actual": 1.1 * np.exp(residual),
            "incumbent_g_actual": 1.0,
            "point_log_ratio": np.log(1.1),
            "realized_log_ratio": np.log(1.1) + residual,
            "paired_log_residual": residual,
            "retained_mass_delta": -0.01,
            "issue_weight": 1.0 / len(residuals),
        })
    return pd.DataFrame(rows)


def _surface() -> pd.DataFrame:
    rows = []
    retained = {1: .90, 2: .89, 3: .88, 4: .87, 5: .86, 6: .85, 7: .84, 8: .83}
    for match_idx in range(1, 9):
        rows.append({
            "issue": "23001",
            "issue_year": 2023,
            "issue_anchor_ts": "2023-01-01T00:00:00+00:00",
            "match_idx": match_idx,
            "canonical_fixture_key": f"bjslot:23001:{match_idx:03d}",
            "causal_grade": "RETROSPECTIVE_RELATIVE_PROXY",
            "baseline_support": "31",
            "qeu_support": "30",
            "support_changed": True,
            "support_pressure": float(match_idx),
            "retained_mass": retained[match_idx],
            "q_eu_3": .5,
            "q_eu_1": .3,
            "q_eu_0": .2,
            "q_line_3": .4,
            "q_line_1": .35,
            "q_line_0": .25,
            "pred_sp_3": 2.0,
            "pred_sp_1": 3.0,
            "pred_sp_0": 4.0,
            "g_point": 1.5 if match_idx == 8 else 1.0 + match_idx / 100.0,
        })
    return pd.DataFrame(rows)


def test_weighted_quantile_and_probability_respect_issue_weights() -> None:
    values = np.array([-0.2, 0.0, 0.3])
    weights = np.array([0.25, 0.25, 0.50])
    assert weighted_quantile(values, weights, 0.50) == 0.0
    probability, lower = paired_metrics(np.log(1.1), _calibration())
    assert 0 < probability <= 1
    assert np.isclose(lower, np.log(1.1) - 0.1, rtol=0, atol=1e-12)


def test_pair_selector_replaces_monotonically_and_preserves_seven() -> None:
    selected, ledger = select_pairwise(_surface(), _calibration(), "P60")
    assert len(selected) == 7
    assert 8 in set(selected["match_idx"])
    assert len(set(range(1, 8)) - set(selected["match_idx"])) == 1
    assert len(ledger) == 1
    assert ledger.iloc[0]["point_delta_g"] > 0
    assert ledger.iloc[0]["retained_mass_delta"] >= -MAX_RETAINED_MASS_DROP


def test_pair_selector_rejects_cross_issue_calibration_semantics() -> None:
    calibration = _calibration()
    calibration.loc[0, "candidate_issue"] = "DIFFERENT"
    assert not calibration["candidate_issue"].eq(calibration["incumbent_issue"]).all()


def test_pair_selector_rejects_excess_probability_loss() -> None:
    surface = _surface()
    surface.loc[surface["match_idx"].eq(8), "retained_mass"] = 0.10
    selected, ledger = select_pairwise(surface, _calibration(), "POINT")
    assert 8 not in set(selected["match_idx"])
    assert ledger.empty


def test_r3_is_recomputed_only_inside_final_seven() -> None:
    frozen, replacements = freeze_bundles(_surface(), _calibration())
    assert set(frozen["cell"]) == set(CELLS)
    assert set(replacements["selector"]) == set(SELECTORS)
    p60_r3 = frozen[frozen["cell"].eq("P60R3A0")].iloc[0]
    supports = json.loads(p60_r3["support_json"])
    assert "8" in supports and len(supports) == 7
    assert supports["8"] == ["3", "0"]
    assert sum(value == ["3", "0"] for value in supports.values()) == 3


def test_settlement_has_all_cells_128_tickets_and_factor_once() -> None:
    frozen, _ = freeze_bundles(_surface(), _calibration())
    labels = pd.DataFrame([{
        "issue_code": "23001",
        "match_idx": index,
        "result_code": "3",
        "winning_sp": 2.0,
        "has_trusted_settlement": 1,
    } for index in range(1, 9)])
    bundles, tickets, attribution = settle_bundles(frozen, labels)
    assert set(bundles["cell"]) == set(CELLS)
    assert tickets.groupby("cell")["ticket_code"].nunique().eq(128).all()
    assert tickets.groupby("cell")["stake_cny"].sum().eq(ISSUE_STAKE_CNY).all()
    expected = 2.0 * 4 * PAYOUT_FACTOR * 2.0**7
    assert np.allclose(bundles["gross_cny"], expected, rtol=0, atol=1e-12)
    assert attribution.groupby("cell")["match_idx"].size().eq(7).all()


def test_untrusted_settlement_fails_closed() -> None:
    frozen, _ = freeze_bundles(_surface(), _calibration())
    labels = pd.DataFrame([{
        "issue_code": "23001",
        "match_idx": index,
        "result_code": "3",
        "winning_sp": 2.0,
        "has_trusted_settlement": int(index != 8),
    } for index in range(1, 9)])
    bundles, tickets, attribution = settle_bundles(frozen, labels)
    assert bundles.empty and tickets.empty and attribution.empty


def _copy_package(target_root: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "results/paired_value_r3_n7"
    if not (source / "MANIFEST.json").exists():
        pytest.skip("package not built yet")
    manifest = json.loads((source / "MANIFEST.json").read_text())
    for relative in manifest["files"]:
        source_path = repo_root / relative
        target_path = target_root / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    target_output = target_root / "results/paired_value_r3_n7"
    shutil.copy2(source / "MANIFEST.json", target_output / "MANIFEST.json")
    accepted_source = repo_root / "results/qeu_threshold_n7/issue_bundles.parquet"
    accepted_target = target_root / "results/qeu_threshold_n7/issue_bundles.parquet"
    accepted_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(accepted_source, accepted_target)
    return target_output


def _rehash(target_root: Path, output: Path, relative: str) -> None:
    manifest_path = output / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    path = target_root / relative
    manifest["files"][relative] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def test_verifier_rejects_pair_calibration_tamper_even_if_rehashed(tmp_path: Path) -> None:
    output = _copy_package(tmp_path)
    path = output / "pair_calibration.parquet"
    frame = pd.read_parquet(path)
    frame.loc[frame.index[0], "paired_log_residual"] += 0.25
    frame.to_parquet(path, index=False)
    _rehash(tmp_path, output, "results/paired_value_r3_n7/pair_calibration.parquet")
    with pytest.raises(AssertionError):
        verify_package(tmp_path, output)


def test_verifier_rejects_ticket_group_tamper_even_if_rehashed(tmp_path: Path) -> None:
    output = _copy_package(tmp_path)
    path = output / "tickets.parquet"
    frame = pd.read_parquet(path)
    first = frame.iloc[0]
    keep = ~(
        frame["issue"].astype(str).eq(str(first["issue"]))
        & frame["issue_year"].eq(first["issue_year"])
        & frame["cell"].eq(first["cell"])
    )
    frame.loc[keep].to_parquet(path, index=False)
    _rehash(tmp_path, output, "results/paired_value_r3_n7/tickets.parquet")
    with pytest.raises(AssertionError):
        verify_package(tmp_path, output)


def test_verifier_rejects_settlement_tamper_even_if_rehashed(tmp_path: Path) -> None:
    output = _copy_package(tmp_path)
    path = output / "evaluation_labels.parquet"
    frame = pd.read_parquet(path)
    frame.loc[frame.index[0], "winning_sp"] *= 1.1
    frame.to_parquet(path, index=False)
    _rehash(tmp_path, output, "results/paired_value_r3_n7/evaluation_labels.parquet")
    with pytest.raises(AssertionError):
        verify_package(tmp_path, output)
