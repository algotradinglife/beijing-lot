from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ticket_policy.fixed_n7 import (
    FEATURES,
    N,
    IssuePanel,
    TicketPolicyError,
    _issue_metric,
    _select,
    _ticket_calibration,
    generate_candidates,
    load_panels,
    verify,
)


def _panel(matches: int = 12) -> IssuePanel:
    probability = np.tile(np.asarray([[0.45, 0.3, 0.25]]), (matches, 1))
    probability[:, 0] -= np.linspace(0, 0.08, matches)
    probability[:, 2] += np.linspace(0, 0.08, matches)
    sp = 1.0 / probability
    realized = np.arange(matches) % 3
    return IssuePanel(
        split="CV_2021",
        issue="synthetic",
        year=2021,
        match_idx=np.arange(1, matches + 1),
        control_probability=probability,
        experimental_probability=probability.copy(),
        predicted_sp=sp,
        sp_seed_std=np.full_like(sp, 0.01),
        official_sp=sp,
        realized_index=realized,
        labels_available=np.ones(matches, dtype=bool),
    )


def _candidate_frame(rows: int = 40) -> pd.DataFrame:
    records = []
    for index in range(rows):
        matches = np.arange(index + 1, index + N + 1)
        identity = "|".join(f"{match}:3" for match in matches)
        record = {
            "split": "CV_2022",
            "issue": "x",
            "year": 2022,
            "ticket_identity": identity,
            "match_indices": "|".join(map(str, matches)),
            "outcomes": "|".join(["3"] * N),
            "candidate_source": "TEST",
            "n": N,
            "control_joint_probability": 0.99 if index == 0 else 1e-6,
            "predicted_sp_product": 2.0,
            "expected_pre_tax_net": float(rows - index),
            "labels_available": True,
            "realized_hit": index == 3,
            "realized_gross": 3.0 if index == 3 else 0.0,
        }
        for feature in FEATURES:
            record[feature] = float(index + 1)
        records.append(record)
    return pd.DataFrame(records)


def _write_matrix(tmp_path: Path, *, promote_experimental: bool = False) -> tuple[Path, Path]:
    rows = []
    for match_idx in range(1, 9):
        for outcome, probability, sp in zip(
            ("3", "1", "0"), (0.45, 0.3, 0.25), (2.2, 3.3, 4.0), strict=True
        ):
            rows.append(
                {
                    "issue": "x",
                    "year": 2021,
                    "split": "CV_2021",
                    "match_idx": match_idx,
                    "outcome_code": outcome,
                    "control_probability": probability,
                    "control_probability_source": "MARKET_ONLY",
                    "control_probability_source_grade": "FROZEN_SAFE_BASELINE",
                    "control_probability_promoted": True,
                    "experimental_probability": probability,
                    "experimental_probability_promoted": promote_experimental,
                    "predicted_final_sp": sp,
                    "sp_seed_std": 0.01,
                    "official_final_sp_label": sp,
                    "realized_outcome": outcome == "3",
                }
            )
    matrix = tmp_path / "matrix.parquet"
    pd.DataFrame(rows).to_parquet(matrix, index=False)
    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps(
            {
                "version": "bj205-joint-n7-value-matrix-v2",
                "safe_control_interface": {
                    "probability": "control_probability",
                    "probability_source": "MARKET_ONLY",
                    "source_grade": "FROZEN_SAFE_BASELINE",
                    "promoted": True,
                    "predicted_sp": "predicted_final_sp",
                    "expected_gross": "control_expected_gross",
                    "expected_pre_tax_net": "control_expected_pre_tax_net",
                    "displayed_scalar": "control_displayed_scalar_utility",
                    "joint_scorer": "MARKET_INDEPENDENCE",
                },
                "experimental_interface": {
                    "promoted": False,
                    "allowed_use": "ablation_feature_only",
                },
            }
        ),
        encoding="utf-8",
    )
    return matrix, schema


def test_generator_is_deterministic_exact_n7_and_uses_multiple_subsets() -> None:
    first = generate_candidates(_panel(), draws_per_seed=8)
    second = generate_candidates(_panel(), draws_per_seed=8)
    assert first.ticket_identity.to_list() == second.ticket_identity.to_list()
    assert first.n.eq(N).all()
    assert first.ticket_identity.is_unique
    assert first.match_indices.nunique() > 1
    assert first.ticket_identity.str.split("|").map(len).eq(N).all()
    assert first.match_indices.str.split("|").map(lambda x: len(set(x))).eq(N).all()
    source_cells = json.loads(first.source_cells_json.iloc[0])
    assert len(source_cells) == N
    assert all("predicted_final_sp_seed_std" in cell for cell in source_cells)


def test_ticket_calibration_reports_hit_and_payout_channels() -> None:
    frame = _candidate_frame()
    frame["split"] = "CV_2022"
    calibration = _ticket_calibration(frame)
    assert calibration.tickets.sum() == len(frame)
    assert {
        "mean_joint_probability",
        "realized_hit_rate",
        "mean_expected_gross",
        "mean_realized_gross",
        "payout_mae",
    }.issubset(calibration.columns)


def test_wor_is_distinct_and_wr_is_explicit_repeat_stake() -> None:
    frame = _candidate_frame()
    wor = _select(frame, "MARKET_WOR", 32)
    wr = _select(frame, "MARKET_WR", 32)
    assert wor.ticket_identity.is_unique
    assert wr.ticket_identity.duplicated().any()
    assert wr.repeat_count.max() > 1


def test_overlap_controls_preserve_budget_and_reduce_or_penalize_overlap() -> None:
    frame = _candidate_frame()
    full = _select(frame, "BEST_FULL", 16)
    capped = _select(frame, "OVERLAP_CAPPED", 16)
    penalized = _select(frame, "OVERLAP_PENALIZED", 16)
    full_metric = _issue_metric(full)
    capped_metric = _issue_metric(capped)
    penalized_metric = _issue_metric(penalized)
    assert full_metric["turnover"] == capped_metric["turnover"] == penalized_metric["turnover"]
    assert capped_metric["match_overlap"] <= full_metric["match_overlap"] + 1e-12
    assert penalized_metric["match_overlap"] <= full_metric["match_overlap"] + 1e-12


def test_loader_preserves_complete_m_by_3_safe_interface(tmp_path: Path) -> None:
    matrix, schema = _write_matrix(tmp_path)
    panels = load_panels(matrix, schema)
    assert len(panels) == 1
    assert panels[0].control_probability.shape == (8, 3)
    assert np.array_equal(panels[0].match_idx, np.arange(1, 9))


def test_loader_rejects_promoted_experimental_lane(tmp_path: Path) -> None:
    matrix, schema = _write_matrix(tmp_path, promote_experimental=True)
    with pytest.raises(TicketPolicyError, match="promoted experimental"):
        load_panels(matrix, schema)


def test_loader_scrubs_locked_labels_before_ticket_construction(tmp_path: Path) -> None:
    matrix, schema = _write_matrix(tmp_path)
    frame = pd.read_parquet(matrix)
    frame["split"] = "LOCKED_TEST"
    frame["year"] = 2025
    frame.to_parquet(matrix, index=False)
    panel = load_panels(matrix, schema)[0]
    assert not panel.labels_available.any()
    assert (panel.realized_index == -1).all()
    assert np.isnan(panel.official_sp).all()


def test_verify_rejects_locked_label_use(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    output.mkdir()
    requests = pd.DataFrame(
        [
            {
                "issue": "x",
                "n": N,
                "ticket_identity": "|".join(f"{i}:3" for i in range(N)),
                "requested_stake": 2,
                "labels_used": True,
                "fallback_applied": True,
                "policy": "BEST_FULL",
            }
        ]
    )
    requests.to_parquet(output / "ticket_requests.parquet", index=False)
    pd.DataFrame([{"stake_budget_matched": True}]).to_csv(
        output / "policy_surface.csv", index=False
    )
    (output / "decision.json").write_text(
        json.dumps(
            {
                "disposition": "INHERIT_STRONGEST_FROZEN_CONTROL",
                "safe_control_policy": "BEST_FULL",
            }
        ),
        encoding="utf-8",
    )
    from ticket_policy.fixed_n7 import _digest

    manifest = {
        path.name: _digest(path)
        for path in output.iterdir()
        if path.name != "SHA256SUMS.json"
    }
    (output / "SHA256SUMS.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(TicketPolicyError, match="locked label"):
        verify(output)
