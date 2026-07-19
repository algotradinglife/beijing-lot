from __future__ import annotations

from research.handicap_draw_projection import (
    ApproximateReplayConfig,
    ApproximateReplayRow,
    build_checksummed_approximate_artifact,
    fit_final_proxy_candidates,
    run_approximate_issue_replay,
)


def row(issue: str, match_index: int, outcome: str) -> ApproximateReplayRow:
    return ApproximateReplayRow(
        issue_id=issue,
        match_id=f"{issue}_{match_index:03d}",
        match_index=match_index,
        baseline_probabilities=(0.4, 0.3, 0.3),
        g1_probabilities=(0.35, 0.4, 0.25),
        outcome=outcome,  # type: ignore[arg-type]
    )


def test_walk_forward_training_uses_strictly_earlier_issues_not_same_issue_rows():
    rows = (
        row("100", 1, "1"),
        row("100", 2, "3"),
        row("101", 1, "0"),
        row("101", 2, "1"),
        row("102", 1, "1"),
    )
    result = run_approximate_issue_replay(
        rows, ApproximateReplayConfig(min_training_issues=1, min_training_rows=1)
    )
    fitted = [prediction for prediction in result.common_cohort_predictions if prediction.issue_id == "101"]
    assert fitted
    assert all(prediction.training_issue_ids == ("100",) for prediction in fitted)
    assert all("101" not in prediction.training_issue_ids for prediction in fitted)


def test_a5_diagnostic_is_rejected_if_it_overlaps_historical_training():
    historical = (row("100", 1, "1"), row("101", 1, "0"))
    try:
        fit_final_proxy_candidates(
            historical,
            (row("101", 2, "1"),),
            ApproximateReplayConfig(min_training_issues=1, min_training_rows=1),
        )
    except ValueError as error:
        assert str(error) == "diagnostic_issue_overlaps_historical_training"
    else:
        raise AssertionError("A5 overlap must fail closed")


def test_approximate_artifact_is_deterministic_and_explicitly_nonselectable():
    result = run_approximate_issue_replay(
        (row("100", 1, "1"), row("101", 1, "0")),
        ApproximateReplayConfig(min_training_issues=1, min_training_rows=1),
    )
    first = build_checksummed_approximate_artifact(result, evidence={"fixture": "a" * 64}, config=ApproximateReplayConfig(min_training_issues=1, min_training_rows=1))
    second = build_checksummed_approximate_artifact(result, evidence={"fixture": "a" * 64}, config=ApproximateReplayConfig(min_training_issues=1, min_training_rows=1))
    assert first["payload_sha256"] == second["payload_sha256"]
    assert first["payload"]["status"] == "research_only_approximate_non_executable_non_selectable_roi_unauthorized"
