from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "freeze_bj190_sparse_divergence_gate_a.py"
CORE = ROOT / "scripts" / "bj190_sparse_divergence_core.py"
ACCEPTED_CORE = ROOT / "scripts" / "bj180_team_matchup_core.py"
PACKAGE = ROOT / "results" / "bj190_gate_a_preoutcome_v3"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_score_distribution_reproduces_accepted_poisson_mapping():
    core = load(CORE, "bj190_core_mapping")
    accepted = load(ACCEPTED_CORE, "bj190_accepted_core_mapping")
    for home, away, line in (
        (0.08, 0.08, 0),
        (1.31, 0.87, -1),
        (2.8, 1.2, 1),
        (7.0, 0.01, 2),
    ):
        distribution = core.poisson_difference_distribution(home, away)
        assert sum(distribution.values()) == pytest.approx(1.0)
        assert core.mapped_probabilities(distribution, line) == pytest.approx(
            accepted.poisson_handicap(home, away, line), abs=5e-12
        )


def test_coherent_t1_distribution_controls_both_probability_and_margin():
    core = load(CORE, "bj190_core_coherent")
    distributions = {
        family: core.poisson_difference_distribution(0.7 + index / 10, 1.9)
        for index, family in enumerate(core.FAMILY_ORDER)
    }
    weights = {family: 1.0 / 7 for family in core.FAMILY_ORDER}
    target = (0.55, 0.25, 0.20)
    distribution = core.group_mass_calibrated_distribution(
        distributions, weights, target, 0
    )
    assert core.mapped_probabilities(distribution, 0) == pytest.approx(target)
    assert core.expected_margin(distribution) > 0

    half_line = core.group_mass_calibrated_distribution(
        distributions, weights, (0.7, 0.0, 0.3), -0.5
    )
    assert core.mapped_probabilities(half_line, -0.5) == pytest.approx((0.7, 0.0, 0.3))
    with pytest.raises(RuntimeError, match="empty score-difference outcome group"):
        core.group_mass_calibrated_distribution(
            distributions, weights, (0.69, 0.01, 0.30), -0.5
        )

    runner = load(RUNNER, "bj190_coherent_metric")
    record = runner.MatchRecord(
        match_id="1",
        issue="1",
        issue_instance="1@CANONICAL_2025",
        match_idx=1,
        kickoff_ts="2025-01-01 00:00:00",
        year=2025,
        league="L",
        line=0.0,
        line_stratum="0",
        min_history_n=20,
        market_breadth="B05_19",
        market_dispersion="D_LOW",
        market_uncertainty=0.06,
        fundamental_p=target,
        calibrated_p=(0.4, 0.3, 0.3),
        consensus_p=(0.35, 0.3, 0.35),
        fundamental_delta=(0.2, -0.05, -0.15),
        calibrated_delta=(0.05, 0.0, -0.05),
        fundamental_z=(2.0, -0.5, -1.5),
        calibrated_z=(0.5, 0.0, -0.5),
        t1_expected_margin=core.expected_margin(distribution),
        line_residual_mu=core.expected_margin(distribution),
        line_residual_z=1.25,
    )
    metric = runner.metric_for_record(
        record, "LINE_RESIDUAL_MU", "FUNDAMENTAL_INDEPENDENT"
    )
    assert metric is not None
    assert metric.favored_code == "3"
    assert metric.estimator_source == "FUNDAMENTAL_T1_SCORE_DISTRIBUTION"
    assert metric.allocation_p == target


def test_directional_ticket_enumerator_freezes_exact_multiplicities_and_ties():
    core = load(CORE, "bj190_directional_tickets")
    probabilities = [(1 / 3, 1 / 3, 1 / 3)] * 7
    vector = core.directional_ticket_multiplicity_vector(probabilities, 2, "1")
    assert vector == core.directional_ticket_multiplicity_vector(probabilities, 2, "1")
    stats = core.validate_ticket_multiplicity_vector(vector, "1", 2)
    assert stats == {
        "zero_count": 729,
        "one_count": 729,
        "two_count": 729,
        "executed_ticket_count": 2187,
        "unique_ticket_count": 1458,
        "max_multiplicity": 2,
    }
    eligible = [
        ordinal
        for ordinal in range(2187)
        if core.decode_ticket_ordinal(ordinal)[2] != "1"
    ]
    assert [ordinal for ordinal in eligible if vector[ordinal] == 2] == eligible[:729]
    assert all(
        vector[ordinal] == 0
        for ordinal in range(2187)
        if core.decode_ticket_ordinal(ordinal)[2] == "1"
    )
    assert (
        core.validate_ticket_multiplicity_vector(
            core.full_ticket_multiplicity_vector()
        )["unique_ticket_count"]
        == 2187
    )


def test_h2h_empirical_tail_preserves_code_on_bounded_score_support():
    core = load(CORE, "bj190_h2h_tail")

    class State:
        h2h = {("H", "A"): [(99.0, 0.0), (0.0, 99.0)]}

    prior = core.poisson_difference_distribution(1.2, 1.1)
    distribution = core.h2h_difference_distribution(
        State(), {"home_team_id": "H", "away_team_id": "A"}, prior
    )
    assert sum(distribution.values()) == pytest.approx(1.0)
    assert distribution[-12] > prior[-12]
    assert distribution[12] > prior[12]


def test_detector_grid_preserves_probability_line_and_unidentified_mu_axes():
    runner = load(RUNNER, "bj190_grid")
    rows = runner.build_detector_grid()
    counts = Counter((row["detector_family"], row["availability"]) for row in rows)
    assert len(rows) == 2424
    assert counts == {
        ("DELTA_P", "AVAILABLE"): 2304,
        ("LINE_RESIDUAL_MU", "AVAILABLE"): 60,
        ("DELTA_MU", "DIAGNOSTIC_UNAVAILABLE"): 60,
    }
    assert {row["top_k"] for row in rows} == {"1", "2", "4", "ALL"}
    available = [row for row in rows if row["availability"] == "AVAILABLE"]
    assert all("inherited source rank" not in row["tie_break"] for row in available)
    assert all("first seven" in row["tie_break"] for row in available)
    assert all("fewer than seven" in row["no_bet_rule"] for row in available)


def test_independent_registry_excludes_market_and_tl_feature_paths():
    runner = load(RUNNER, "bj190_provenance")
    rows = runner.build_estimator_provenance_registry()
    independent = [row for row in rows if row["estimator"] == "FUNDAMENTAL_INDEPENDENT"]
    market = [row for row in rows if row["estimator"] == "CALIBRATED_MARKET_ESTIMATOR"]
    assert {row["feature_family"] for row in independent} == set(
        runner.core190.FAMILY_ORDER
    )
    assert all(row["uses_market_input"] == 0 for row in independent)
    assert all(row["uses_market_input"] == 1 for row in market)
    assert all(row["source_branch"] == "#180 T1_DEEP_TEAM" for row in independent)


def test_complete_issue_universe_census_and_native_line_coverage():
    runner = load(RUNNER, "bj190_full_census")
    source_runner = runner.load_module(
        "bj190_test_source_180",
        ROOT / "scripts" / "freeze_bj180_team_matchup_gate_a.py",
    )
    issues, lines = runner.build_canonical_issue_specs(
        runner.locate_database(), source_runner.load_sources()
    )
    assert len(issues) == 344
    assert sum(issue.eligible_match_count for issue in issues) == 101_970
    assert min(issue.eligible_match_count for issue in issues) >= 7
    assert sum(bool(issue.b0_match_ids) for issue in issues) == 189
    assert lines["-2.000000000000"] == 4877
    assert lines["-1.000000000000"] == 24561
    assert lines["0.000000000000"] == 61275
    assert lines["1.000000000000"] == 9357
    assert lines["2.000000000000"] == 1467
    assert lines["MISSING_EXCLUDED"] == 252


def test_database_path_contract_supports_detached_replay_and_verifies_hash(
    monkeypatch, tmp_path
):
    runner = load(RUNNER, "bj190_database_contract")
    canonical = runner.locate_database()
    monkeypatch.setenv(runner.DB_ENVIRONMENT_VARIABLE, str(canonical))
    monkeypatch.setattr(runner, "ROOT", tmp_path / "detached-checkout")
    assert runner.locate_database() == canonical
    assert runner.locate_database(canonical) == canonical
    assert runner.sha256_file(canonical) == runner.SOURCE_DB_SHA256
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(RuntimeError, match="explicit source database unavailable"):
        runner.locate_database(missing)


def test_union_and_agreement_freeze_explicit_per_leg_probability_sources():
    runner = load(RUNNER, "bj190_variant_sources")
    record = runner.MatchRecord(
        match_id="1",
        issue="1",
        issue_instance="1@CANONICAL_2025",
        match_idx=1,
        kickoff_ts="2025-01-01 00:00:00",
        year=2025,
        league="L",
        line=0.0,
        line_stratum="0",
        min_history_n=20,
        market_breadth="B05_19",
        market_dispersion="D_LOW",
        market_uncertainty=0.06,
        fundamental_p=(0.6, 0.25, 0.15),
        calibrated_p=(0.5, 0.3, 0.2),
        consensus_p=(0.35, 0.3, 0.35),
        fundamental_delta=(0.25, -0.05, -0.20),
        calibrated_delta=(0.15, 0.0, -0.15),
        fundamental_z=(1.25, -0.5, -99.0),
        calibrated_z=(1.5, 0.0, -1.5),
        t1_expected_margin=0.3,
        line_residual_mu=0.3,
        line_residual_z=1.0,
    )
    union = runner.metric_for_record(record, "DELTA_P", "UNION")
    agreement = runner.metric_for_record(record, "DELTA_P", "MODEL_AGREEMENT")
    assert union is not None and agreement is not None
    assert union.estimator_source == "FUNDAMENTAL_T1_SCORE_DISTRIBUTION"
    assert union.allocation_p == record.fundamental_p
    assert union.abs_z == 1.25
    assert agreement.estimator_source == (
        "STRICT_AGREEMENT_WEAKER::CALIBRATED_MARKET_ESTIMATOR"
    )
    assert agreement.allocation_p == record.calibrated_p


def test_generated_gate_a_package_is_complete_and_outcome_unexposed():
    if not PACKAGE.is_dir():
        pytest.skip("formal immutable package not generated yet")
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    assert all(
        hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
        for name, expected in manifest.items()
    )
    content = json.loads(
        (PACKAGE / "CONTENT_IDENTITY.json").read_text(encoding="utf-8")
    )
    assert content["package"] == "bj190_gate_a_preoutcome_v3"
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["cohort"] == {
        "canonical_numeric_issue_count": 344,
        "eligible_match_count": 101970,
        "excluded_missing_native_line_match_count": 252,
        "source_b0_no_bet_issue_count": 155,
        "source_b0_participating_issue_count": 189,
        "source_issue_instance_count": 348,
    }
    assert card["detector_grid"]["policy_count"] == 2424
    assert card["detector_grid"]["policy_issue_selection_row_count"] == 2424 * 344
    assert card["gate_b_authorized"] is False
    estimators = read_gzip(PACKAGE / "estimator_match_freeze.csv.gz")
    forecasts = read_gzip(PACKAGE / "coverage_forecast.csv.gz")
    strata = read_gzip(PACKAGE / "line_direction_forecast.csv.gz")
    vectors = read_gzip(PACKAGE / "ticket_multiplicity_vector_catalog.csv.gz")
    allocations = read_gzip(PACKAGE / "directional_allocation_input_catalog.csv.gz")
    assert len(estimators) == 101970
    assert len(forecasts) == 2424
    assert len(strata) == 2424 * 24
    assert {row["line_stratum"] for row in estimators} == {
        "-2",
        "-1",
        "0",
        "+1",
        "+2",
        "OTHER",
    }
    assert allocations
    assert all(row["per_leg_probability_source_json"] for row in allocations)
    assert any(int(row["zero_count"]) == 729 for row in vectors)
    assert all(row["native_handicap_line"] for row in estimators)
    training = read_gzip(PACKAGE / "estimator_match_freeze.csv.gz")
    assert len(training) == 101970
    with (PACKAGE / "market_model_training_freeze.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        market_training = list(csv.DictReader(handle))
    assert len(market_training) == 344
    assert all(int(row["target_issue_overlap_count"]) == 0 for row in market_training)
    assert all(
        int(row["post_available_cutoff_row_count"]) == 0 for row in market_training
    )
    assert all(row["history_identity_sha256"] for row in market_training)
    cross_year = {
        "190101",
        "20011",
        "21011",
        "22011",
        "23011",
        "24011",
        "25011",
    }
    assert cross_year.issubset({row["issue"] for row in market_training})
    for row in market_training:
        if row["training_max_kickoff_ts"]:
            assert row["training_max_kickoff_ts"] <= row["score_available_through_ts"]
    forbidden = {"fthg", "ftag", "result_code", "winning_sp", "payout", "tax", "roi"}
    for name in (
        "poisson_latent_reconciliation.csv.gz",
        "estimator_match_freeze.csv.gz",
    ):
        assert not forbidden.intersection(read_gzip(PACKAGE / name)[0])
    selection_shards = sorted(
        PACKAGE.glob("policy_issue_selection_freeze_part_*_of_04.csv.gz")
    )
    assert len(selection_shards) == 4
    assert sum(len(read_gzip(path)) for path in selection_shards) == 2424 * 344
    assert all(
        not forbidden.intersection(read_gzip(path)[0]) for path in selection_shards
    )
    with (PACKAGE / "detector_grid.csv").open(newline="", encoding="utf-8") as handle:
        grid = list(csv.DictReader(handle))
    assert Counter(row["availability"] for row in grid) == {
        "AVAILABLE": 2364,
        "DIAGNOSTIC_UNAVAILABLE": 60,
    }
    assert all(
        path.read_bytes()[:4] == bytes((0x1F, 0x8B, 0x08, 0x00))
        for path in selection_shards
    )
