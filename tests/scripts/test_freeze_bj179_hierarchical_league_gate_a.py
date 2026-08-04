from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import inspect
import json
import sys
from collections import Counter
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj179_hierarchical_league_gate_a.py"
CORE_SCRIPT = ROOT / "scripts" / "bj179_hierarchical_league_core.py"
PACKAGE = ROOT / "results" / "bj179_gate_a_preoutcome_v1"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def market_row(**overrides):
    row = {
        "match_id": "1",
        "kickoff_ts": "2019-03-01 12:00:00",
        "league": "L1",
        "handicap_line_norm": -0.5,
        "fthg": 2,
        "ftag": 0,
        "euro_initial_v1": 2.30,
        "euro_initial_v2": 3.10,
        "euro_initial_v3": 3.20,
        "euro_1h_v1": 2.10,
        "euro_1h_v2": 3.20,
        "euro_1h_v3": 3.60,
        "euro_1h_min1": 2.00,
        "euro_1h_min2": 3.00,
        "euro_1h_min3": 3.40,
        "euro_1h_max1": 2.20,
        "euro_1h_max2": 3.40,
        "euro_1h_max3": 3.80,
        "euro_1h_n": 20,
        "asian_initial_v2": -0.25,
        "asian_1h_v2": -0.50,
        "asian_1h_n": 15,
        "ou_initial_v2": 2.50,
        "ou_1h_v2": 2.75,
        "ou_1h_n": 15,
    }
    row.update(overrides)
    return row


def test_contract_freezes_exact_comparators_families_and_full_economics():
    module = load(SCRIPT, "bj179_contract")
    core = load(CORE_SCRIPT, "bj179_core_contract")
    assert module.BASE_MAIN_COMMIT == "9ec5cf4856f546861e20fad76d110807576903c7"
    assert module.FULL_TICKETS == 2187
    assert module.FULL_STAKE_YUAN == 4374
    assert tuple(core.FAMILY_WEIGHTS) == module.FAMILIES
    assert sum(core.FAMILY_WEIGHTS.values()) == pytest.approx(1.0)
    assert [row[0] for row in module.ARMS] == [
        "B0_BEST_FULL",
        "Q1_QUICK_LEAGUE",
        "H1_DEEP_ALL",
        "H_MINUS_BASE",
        "H_MINUS_GOAL",
        "H_MINUS_PRICING",
        "H_MINUS_LIQUIDITY",
    ]
    assert all(
        row[0].startswith(("B0_", "Q1_", "H1_", "H_MINUS_")) for row in module.ARMS
    )


def test_chronology_rejects_target_or_future_season_and_keeps_prior_rows():
    core = load(CORE_SCRIPT, "bj179_core_chronology")
    model = core.HierarchicalLeagueModel(target_year=2020)
    model.update(market_row())
    assert model.training_rows == 1
    with pytest.raises(RuntimeError, match="future-season training row"):
        model.update(market_row(kickoff_ts="2020-01-01 00:00:00"))


def test_unknown_league_and_market_missingness_are_explicit_hierarchical_fallbacks():
    core = load(CORE_SCRIPT, "bj179_core_missingness")
    model = core.HierarchicalLeagueModel(target_year=2020)
    model.update(market_row())
    unknown = market_row(
        league="UNSEEN",
        handicap_line_norm=None,
        euro_1h_n=None,
        asian_1h_n=None,
        ou_1h_n=None,
        euro_1h_min1=None,
        euro_1h_min2=None,
        euro_1h_min3=None,
        euro_1h_max1=None,
        euro_1h_max2=None,
        euro_1h_max3=None,
    )
    signature = core.market_signature(unknown)
    assert core.handicap_bucket(None) == "H_MISSING"
    assert signature["breadth"] == "MISSING"
    assert signature["dispersion"] == "MISSING"
    families = model.family_vectors(unknown, (0.40, 0.30, 0.30))
    assert set(families) == set(core.FAMILY_WEIGHTS)
    for vector in families.values():
        assert sum(vector) == pytest.approx(1.0)
        assert all(value > 0 for value in vector)


def test_deep_model_and_each_ablation_are_fixed_normalized_outputs():
    core = load(CORE_SCRIPT, "bj179_core_ablation")
    model = core.HierarchicalLeagueModel(target_year=2020)
    for index, score in enumerate(((2, 0), (0, 1), (1, 1), (3, 2), (0, 2))):
        model.update(
            market_row(
                match_id=str(index),
                kickoff_ts=f"2019-03-{index + 1:02d} 12:00:00",
                fthg=score[0],
                ftag=score[1],
                euro_1h_v1=2.10 + index * 0.05,
            )
        )
    target = market_row(fthg=None, ftag=None)
    baseline = (0.40, 0.30, 0.30)
    outputs = {"ALL": model.probabilities(target, baseline)}
    outputs.update(
        {
            family: model.probabilities(target, baseline, family)
            for family in core.FAMILY_WEIGHTS
        }
    )
    assert (
        len(
            {tuple(round(value, 12) for value in vector) for vector in outputs.values()}
        )
        >= 3
    )
    assert all(sum(vector) == pytest.approx(1.0) for vector in outputs.values())


def test_target_probability_projection_is_invariant_to_appended_outcome_fields():
    module = load(SCRIPT, "bj179_target_boundary")
    core = module.load_core()
    model = core.HierarchicalLeagueModel(target_year=2020)
    model.update(market_row())
    target = {
        **market_row(fthg=None, ftag=None),
        "issue": "20001",
        "match_idx": "1",
        "year": "2020",
        "p_market_cal3": "0.40",
        "p_market_cal1": "0.30",
        "p_market_cal0": "0.30",
        "league_p3": "0.39",
        "league_p1": "0.31",
        "league_p0": "0.30",
    }
    role = {
        "p_market_cal3": "0.40",
        "p_market_cal1": "0.30",
        "p_market_cal0": "0.30",
    }
    baseline = module.probability_freeze([target], {"1": role}, {2020: model}, core)
    exposed = {
        **target,
        "fthg": 9,
        "ftag": 0,
        "result_code": "3",
        "winning_sp": 99,
        "payout": 999,
        "tax": 1,
        "roi": 4,
    }
    assert (
        module.probability_freeze([exposed], {"1": role}, {2020: model}, core)
        == baseline
    )
    source = inspect.getsource(module.probability_freeze).lower()
    for forbidden in module.FORBIDDEN_TARGET_FIELDS:
        assert f'row["{forbidden}"]' not in source


def test_accepted_best_full_and_quick_identity_reproduction_without_outcomes():
    module = load(SCRIPT, "bj179_reproduction")
    source = module.load_source_inputs()
    role_by_match = module.canonical_role_by_match(source["roles"])
    probabilities = []
    for match_id, role in role_by_match.items():
        row = {"match_id": match_id}
        for name in (
            "deep_all",
            "deep_minus_base",
            "deep_minus_goal",
            "deep_minus_pricing",
            "deep_minus_liquidity",
        ):
            for code in ("3", "1", "0"):
                row[f"{name}_p{code}"] = role[f"p_market_cal{code}"]
        probabilities.append(row)
    scores = module.score_candidates(
        source["candidates"], source["roles"], probabilities
    )
    selection = module.build_selection(source, scores)
    reproduction = module.reproduce_baselines(source, selection)
    assert [row["reproduction_status"] for row in reproduction] == ["PASS", "PASS"]
    assert [row["selected_identity_count"] for row in reproduction] == [189, 189]
    for arm in {row["arm"] for row in selection}:
        assert Counter(
            row["policy_status"] for row in selection if row["arm"] == arm
        ) == {
            "SELECTED_PREOUTCOME": 189,
            "NO_BET_FROZEN": 159,
        }


def test_generated_package_is_exact_manifest_covered_and_gate_b_is_closed():
    if not PACKAGE.is_dir():
        return
    assert (PACKAGE / "freeze_runner.py").read_bytes() == SCRIPT.read_bytes()
    assert (
        PACKAGE / "bj179_hierarchical_league_core.py"
    ).read_bytes() == CORE_SCRIPT.read_bytes()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert set(manifest) == actual
    for name, expected in manifest.items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["gate_b_status"] == "NOT_AUTHORIZED_PENDING_PI_GATE_A_REVIEW"
    assert card["denominator"] == {
        "no_bet_rows": 159 * 7,
        "planned_stake_per_arm_yuan": 189 * 4374,
        "selected_by_arm": {arm: 189 for arm, *_ in load(SCRIPT, "bj179_package").ARMS},
        "selected_rows": 189 * 7,
        "selection_rows": 348 * 7,
    }
    with gzip.open(
        PACKAGE / "match_probability_freeze.csv.gz", "rt", newline="", encoding="utf-8"
    ) as handle:
        probabilities = list(csv.DictReader(handle))
    assert len(probabilities) == 1558
    assert not set(probabilities[0]).intersection(
        load(SCRIPT, "bj179_fields").FORBIDDEN_TARGET_FIELDS
    )
