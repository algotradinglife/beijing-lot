from __future__ import annotations

from datetime import timedelta

import pandas as pd

from model_support_panel.builder import SCHEDULE_EPOCH_RULES, assemble_panel
from model_support_panel.contract import (
    CONTRACT_VERSION,
    SUPPORT_GATE,
    chronological_role,
)


def test_chronological_roles_preserve_frozen_30_5_2_boundary() -> None:
    assert SUPPORT_GATE.minimum_total_issues == 37
    assert chronological_role(0) == "development"
    assert chronological_role(29) == "development"
    assert chronological_role(30) == "chronological_evaluation"
    assert chronological_role(34) == "chronological_evaluation"
    assert chronological_role(35) == "prospective_confirmation"
    assert chronological_role(36) == "prospective_confirmation"
    assert chronological_role(37) == "post_gate_extension"
    assert CONTRACT_VERSION == "bj216-causal-p34-model-support-v1"


def _causal_fixture(issue_count: int = 37) -> tuple[pd.DataFrame, pd.DataFrame]:
    matches: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    row_id = 1
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    for issue_offset in range(issue_count):
        issue = str(27000 + issue_offset)
        epoch = start + timedelta(days=issue_offset)
        for match_idx in range(1, 8):
            match_id = f"{issue}-{match_idx}"
            kickoff = epoch + timedelta(hours=10 + match_idx)
            matches.append(
                {
                    "match_id": match_id,
                    "issue": issue,
                    "match_idx": match_idx,
                    "kickoff_ts_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "identity_observed_ts_utc": (
                        epoch - timedelta(hours=2)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "handicap_line": 0.0,
                    "upstream_cohort": (
                        "post_203_operational_observational"
                        if issue_offset < 35
                        else "prospective_post_activation"
                    ),
                }
            )
            snapshots.append(
                {
                    "id": row_id,
                    "match_id": match_id,
                    "market_observed_ts_utc": (
                        epoch - timedelta(minutes=15)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "sp_3": 2.1,
                    "sp_1": 3.2,
                    "sp_0": 3.6,
                    "eu_h": 2.2,
                    "eu_d": 3.3,
                    "eu_a": 3.7,
                    "source": "fixture",
                }
            )
            row_id += 1
    return pd.DataFrame(matches), pd.DataFrame(snapshots)


def test_panel_is_outcome_blind_causal_and_three_way() -> None:
    matches, snapshots = _causal_fixture()
    assembled = assemble_panel(
        matches,
        snapshots,
        source_freeze_cutoff_utc="2026-03-01T00:00:00Z",
    )
    support = assembled["issue_support"]
    panel = assembled["panel"]
    assert support["eligible_issue_epoch"].sum() == 37
    assert len(panel) == 37 * 7 * 3
    assert set(panel["outcome_code"]) == {"3", "1", "0"}
    assert not {
        "result_code",
        "score",
        "settlement",
        "winning_sp",
    }.intersection(panel.columns)
    decision = pd.to_datetime(panel["decision_epoch_utc"], utc=True)
    observed = pd.to_datetime(panel["market_observed_ts_utc"], utc=True)
    kickoff = pd.to_datetime(panel["kickoff_ts_utc"], utc=True)
    assert observed.le(decision).all()
    assert kickoff.gt(decision).all()
    sums = panel.groupby(["epoch_id", "match_id"])[
        "devig_euro_probability"
    ].sum()
    assert sums.sub(1.0).abs().max() < 1e-12
    sensitivity = assembled["epoch_sensitivity"]
    assert len(sensitivity) == 37 * len(SCHEDULE_EPOCH_RULES)
    assert set(sensitivity["epoch_rule"]) == set(SCHEDULE_EPOCH_RULES)
    assert sensitivity["controlling_readiness_vote"].sum() == 37
    controlling = sensitivity[sensitivity["controlling_readiness_vote"]]
    assert controlling["epoch_rule"].eq("MEDIAN_KICKOFF_MINUS_10H").all()
    assert sensitivity.loc[
        ~sensitivity["controlling_readiness_vote"], "sensitivity_only"
    ].all()
    assert set(panel["upstream_cohort"]) == {
        "post_203_operational_observational",
        "prospective_post_activation",
    }
    assert not panel["upstream_cohort"].eq(panel["chronological_role"]).any()


def test_post_epoch_snapshot_is_not_selected() -> None:
    matches, snapshots = _causal_fixture(issue_count=1)
    snapshots.loc[0, "market_observed_ts_utc"] = "2026-01-01T23:59:59Z"
    assembled = assemble_panel(
        matches,
        snapshots,
        source_freeze_cutoff_utc="2026-02-01T00:00:00Z",
    )
    support = assembled["issue_support"].iloc[0]
    assert support["candidate_matches"] == 7
    assert support["core_complete_matches"] == 6
    assert len(assembled["panel"]) == 6 * 3
