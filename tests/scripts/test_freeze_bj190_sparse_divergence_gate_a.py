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
PACKAGE = ROOT / "results" / "bj190_gate_a_preoutcome_v1"


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


def test_t1_weighted_intensities_use_only_frozen_pure_team_components():
    core = load(CORE, "bj190_core_weighted")
    captured = {
        family: (1.0 + index / 10, 0.8 + index / 20, 0.0, 12)
        for index, family in enumerate(core.FAMILY_ORDER)
    }
    weights = {family: 1.0 / len(core.FAMILY_ORDER) for family in core.FAMILY_ORDER}
    home, away = core.weighted_family_intensities(captured, weights)
    assert home == pytest.approx(sum(row[0] for row in captured.values()) / 7)
    assert away == pytest.approx(sum(row[1] for row in captured.values()) / 7)
    with pytest.raises(RuntimeError, match="family order drift"):
        core.weighted_family_intensities(dict(reversed(captured.items())), weights)


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
    assert {
        row["estimator_variant"]
        for row in rows
        if row["detector_family"] == "DELTA_P"
    } == {
        "FUNDAMENTAL_INDEPENDENT",
        "CALIBRATED_MARKET_ESTIMATOR",
        "UNION",
        "MODEL_AGREEMENT",
    }


def test_independent_registry_excludes_market_and_tl_feature_paths():
    runner = load(RUNNER, "bj190_provenance")
    rows = runner.build_estimator_provenance_registry()
    independent = [
        row for row in rows if row["estimator"] == "FUNDAMENTAL_INDEPENDENT"
    ]
    market = [
        row for row in rows if row["estimator"] == "CALIBRATED_MARKET_ESTIMATOR"
    ]
    assert {row["feature_family"] for row in independent} == set(
        runner.core190.FAMILY_ORDER
    )
    assert all(row["uses_market_input"] == 0 for row in independent)
    assert all(row["uses_market_input"] == 1 for row in market)
    assert all(row["source_branch"] == "#180 T1_DEEP_TEAM" for row in independent)


def test_line_residual_metric_is_directional_and_probability_agreement_is_not_blended():
    runner = load(RUNNER, "bj190_metrics")
    line_row = {
        "target_safe_price_status": "AVAILABLE",
        "line_residual_mu": -0.75,
        "line_residual_z": -1.5,
    }
    line = runner.detector_metric(
        line_row, "FUNDAMENTAL_INDEPENDENT", "LINE_RESIDUAL_MU"
    )
    assert line == {
        "favored_code": "0",
        "omitted_code": "3",
        "extreme_code": "0",
        "extreme_sign": 1,
        "magnitude": 0.75,
        "abs_z": 1.5,
        "delta": {},
        "z": {},
        "estimator_source": "FUNDAMENTAL_T1_DEEP_TEAM_LINE_RESIDUAL",
    }
    probability_row = {
        "target_safe_price_status": "AVAILABLE",
        "fundamental_delta_p3": 0.20,
        "fundamental_delta_p1": -0.05,
        "fundamental_delta_p0": -0.15,
        "fundamental_z3": 2.0,
        "fundamental_z1": -0.5,
        "fundamental_z0": -1.5,
        "calibrated_delta_p3": 0.10,
        "calibrated_delta_p1": -0.03,
        "calibrated_delta_p0": -0.07,
        "calibrated_z3": 1.0,
        "calibrated_z1": -0.3,
        "calibrated_z0": -0.7,
    }
    agreement = runner.detector_metric(
        probability_row, "MODEL_AGREEMENT", "DELTA_P"
    )
    assert agreement is not None
    assert agreement["delta"] == {
        "3": 0.10,
        "1": -0.03,
        "0": -0.07,
    }
    assert agreement["estimator_source"] == "STRICT_MODEL_AGREEMENT_NO_BLEND"


def test_generated_gate_a_package_is_complete_and_outcome_unexposed():
    if not PACKAGE.is_dir():
        pytest.skip("formal immutable package not generated yet")
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    assert all(
        hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
        for name, expected in manifest.items()
    )
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["cohort"] == {
        "candidate_identity_count": 424,
        "candidate_role_count": 2968,
        "frozen_no_bet_issue_count": 159,
        "issue_count": 348,
        "participating_issue_count": 189,
        "unique_match_count": 1558,
    }
    assert card["detector_grid"]["policy_count"] == 2424
    assert card["detector_grid"]["available_delta_p_policy_count"] == 2304
    assert card["detector_grid"]["available_line_residual_policy_count"] == 60
    assert card["detector_grid"]["unavailable_delta_mu_policy_count"] == 60
    assert card["gate_b_authorized"] is False
    latent = read_gzip(PACKAGE / "poisson_latent_reconciliation.csv.gz")
    estimators = read_gzip(PACKAGE / "estimator_match_freeze.csv.gz")
    forecasts = read_gzip(PACKAGE / "coverage_forecast.csv.gz")
    strata = read_gzip(PACKAGE / "line_direction_forecast.csv.gz")
    assert len(latent) == 1558 * 8
    assert len(estimators) == 1558
    assert len(forecasts) == 2424
    assert len(strata) == 2424 * 24
    assert max(float(row["max_abs_reconciliation_error"]) for row in latent) <= 5e-12
    assert Counter(row["estimator"] for row in latent)["T1_DEEP_TEAM"] == 1558
    assert Counter(row["target_safe_price_status"] for row in estimators) == {
        "AVAILABLE": 1556,
        "UNAVAILABLE": 2,
    }
    assert {row["line_stratum"] for row in estimators} == {"0"}
    forbidden = {"fthg", "ftag", "result_code", "winning_sp", "payout", "tax", "roi"}
    for name in ("poisson_latent_reconciliation.csv.gz", "estimator_match_freeze.csv.gz"):
        assert not forbidden.intersection(read_gzip(PACKAGE / name)[0])
    with (PACKAGE / "detector_grid.csv").open(newline="", encoding="utf-8") as handle:
        grid = list(csv.DictReader(handle))
    assert Counter(row["availability"] for row in grid) == {
        "AVAILABLE": 2364,
        "DIAGNOSTIC_UNAVAILABLE": 60,
    }
    assert (PACKAGE / "policy_issue_selection_freeze.csv.gz").read_bytes()[:4] == bytes(
        (0x1F, 0x8B, 0x08, 0x00)
    )
