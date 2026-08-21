from __future__ import annotations

import pandas as pd
import pytest

from issue286.manifest import (
    JointBaseAction,
    build_action_manifest,
    frame_digest,
    prepare_horizon_surface,
)


def _long_view(n: int = 7) -> pd.DataFrame:
    rows = []
    for match in range(1, n + 1):
        for outcome, eu, line in zip(
            ("3", "1", "0"), (0.5, 0.3, 0.2), (0.4, 0.35, 0.25), strict=True
        ):
            rows.append(
                {
                    "issue_code": "23001",
                    "match_idx": match,
                    "snapshot_kind": "10h",
                    "issue_year": 2023,
                    "outcome_code": outcome,
                    "q_eu_bjline": eu,
                    "q_line_only_control": line,
                    "eu_vs_line_divergence": eu - line,
                    "mapping_accepted": True,
                    "native_handicap_line": 0.0,
                    "n_available_books": 10,
                }
            )
    return pd.DataFrame(rows)


def test_horizon_surface_rejects_settlement_columns() -> None:
    view = _long_view()
    view["winning_sp"] = 2.0
    with pytest.raises(ValueError, match="settlement columns"):
        prepare_horizon_surface(view)


def test_manifest_exposes_two_alternatives_and_exact_continuation() -> None:
    surface = prepare_horizon_surface(_long_view())
    action = JointBaseAction(
        n=7,
        k=16,
        selector="UNIFORM",
        outcome_mode="MARKET_PROBABILITY",
        generator="TOP_VALUE",
        stream_seed=286001,
    )
    base, candidates, continuation = build_action_manifest(
        surface,
        match_ids=[str(value) for value in range(1, 8)],
        subset_id="fixed",
        action=action,
    )
    assert len(base) == 16
    assert base.iloc[0]["ticket_identity"] == "|".join(
        f"{match}:3" for match in range(1, 8)
    )
    assert len(continuation) == 16
    assert set(base["ticket_identity"]).isdisjoint(continuation["ticket_identity"])
    assert candidates["candidate_identity"].is_unique
    assert set(candidates["candidate_identity"]).isdisjoint(base["ticket_identity"])
    assert candidates["alternative_outcome_position"].between(0, 2).all()
    assert candidates["within_action_candidate_weight"].sum() == pytest.approx(1.0)


def test_outcome_mutation_cannot_change_manifest() -> None:
    surface = prepare_horizon_surface(_long_view())
    action = JointBaseAction(7, 16, "UNIFORM", "DIVERGENCE_VALUE", "WEIGHTED_WR", 286001)
    before = build_action_manifest(
        surface,
        match_ids=[str(value) for value in range(1, 8)],
        subset_id="fixed",
        action=action,
    )
    fake_settlement = pd.DataFrame({"Y": [0, 1], "winning_sp": [2.0, 99.0]})
    fake_settlement.loc[:, "Y"] = 1 - fake_settlement["Y"]
    fake_settlement.loc[:, "winning_sp"] *= 100
    after = build_action_manifest(
        surface,
        match_ids=[str(value) for value in range(1, 8)],
        subset_id="fixed",
        action=action,
    )
    assert [frame_digest(frame) for frame in before] == [frame_digest(frame) for frame in after]
