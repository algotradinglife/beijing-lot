from __future__ import annotations

from datetime import datetime, timedelta, timezone

import math

from research.handicap_draw_projection import (
    HistoricalP1P2Row,
    LoopConfig,
    build_checksummed_artifact,
    independent_poisson_handicap_probabilities,
    run_chronological_loop,
)


UTC = timezone.utc
SHA = "a" * 64


def row(index: int, *, p2_late: bool = False) -> HistoricalP1P2Row:
    decision = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=index)
    return HistoricalP1P2Row(
        record_id=f"record-{index}",
        issue_id=f"issue-{index}",
        match_id=f"match-{index}",
        handicap=0,
        p1_probabilities=(0.40, 0.30, 0.30),
        p2_lambda_home=1.1 + index * 0.01,
        p2_lambda_away=0.9,
        outcome=("1", "3", "0", "1")[index % 4],
        p1_as_of=decision - timedelta(minutes=10),
        p2_as_of=decision + timedelta(minutes=1) if p2_late else decision - timedelta(minutes=5),
        decision_at=decision,
        sale_cutoff_at=decision + timedelta(minutes=5),
        kickoff_at=decision + timedelta(minutes=10),
        settled_at=decision + timedelta(hours=2),
        p1_sha256=SHA,
        p2_sha256=SHA,
    )


def test_projected_handicap_draw_is_a_normalized_three_way_probability():
    probabilities = independent_poisson_handicap_probabilities(1.0, 1.0, 0)
    assert math.isclose(sum(probabilities), 1.0)
    assert probabilities[0] == probabilities[2]
    assert probabilities[1] > 0


def test_loop_fails_closed_when_p2_timing_is_late():
    result = run_chronological_loop((row(0), row(1, p2_late=True)))
    assert not result.eligibility.eligible
    assert "p1_or_p2_after_decision" in result.eligibility.reasons
    assert result.predictions == ()


def test_calibrated_and_blended_rows_only_train_on_earlier_settlements():
    records = tuple(row(index) for index in range(5))
    result = run_chronological_loop(records, LoopConfig(min_training_rows=1))
    fitted = [prediction for prediction in result.predictions if prediction.candidate != "p1_baseline" and prediction.training_record_ids]
    assert fitted
    for prediction in fitted:
        current = next(record for record in records if record.record_id == prediction.record_id)
        trained = [record for record in records if record.record_id in prediction.training_record_ids]
        assert trained
        assert all(record.settled_at < current.decision_at for record in trained)
    assert {summary.candidate for summary in result.summaries} >= {"p1_baseline", "g1_independent_poisson", "g1_logit_calibrated"}


def test_checksum_artifact_is_deterministic_and_has_no_roi_or_selection_output():
    result = run_chronological_loop(tuple(row(index) for index in range(4)), LoopConfig(min_training_rows=1))
    first = build_checksummed_artifact(result, evidence={"committed_reference": "b" * 64})
    second = build_checksummed_artifact(result, evidence={"committed_reference": "b" * 64})
    assert first["payload_sha256"] == second["payload_sha256"]
    assert first["payload"]["status"] == "research_only_nonselectable_roi_unauthorized"
    assert "return" not in str(first["payload"]).lower()
