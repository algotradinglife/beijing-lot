from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj98_sampling_gate_a.py"


def load():
    spec = importlib.util.spec_from_file_location("bj98_sampling", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def leg(position: int, probability: tuple[float, float, float]) -> dict[str, object]:
    return {
        "position": position,
        "match_id": f"m{position}",
        "issue": "20001",
        "match_idx": str(position),
        "year": 2021,
        "fold": "OOS_2021",
        "p": dict(zip(("3", "1", "0"), probability)),
        "euro": dict(zip(("3", "1", "0"), probability)),
    }


def test_weighted_sampling_is_deterministic_and_prefers_lower_probability_omissions():
    mod = load()
    probability = {"3": 0.8, "1": 0.15, "0": 0.05}
    first = [
        mod.sampled_code(probability, "g", 1, seed, "WEIGHTED_OMIT")
        for seed in range(1, 10_001)
    ]
    second = [
        mod.sampled_code(probability, "g", 1, seed, "WEIGHTED_OMIT")
        for seed in range(1, 10_001)
    ]
    assert first == second
    assert first.count("0") > first.count("1") > first.count("3")


def test_fixed_omission_uses_frozen_code_tie_order():
    mod = load()
    assert mod.bottom_code({"3": 0.1, "1": 0.1, "0": 0.8}) == "3"
    assert mod.bottom_code({"3": 0.8, "1": 0.1, "0": 0.1}) == "1"


def test_quality_threshold_only_uses_strictly_earlier_years():
    mod = load()
    groups = {
        "a": [leg(position, (0.6, 0.3, 0.1)) for position in range(1, 8)],
        "b": [leg(position, (0.5, 0.3, 0.2)) for position in range(1, 8)],
    }
    for item in groups["a"]:
        item["year"] = 2019
    for item in groups["b"]:
        item["year"] = 2020
    result = mod.thresholds(groups)
    assert result[2019] is None
    assert result[2020] == 0.6


def test_selected_ticket_arithmetic_and_mass_are_analytic():
    mod = load()
    legs = [leg(position, (0.6, 0.3, 0.1)) for position in range(1, 8)]
    omitted = ["0"] * 7
    row = mod.row_for("g", legs, "WEIGHTED_OMIT", "10001", None, omitted)
    assert row["selection_status"] == "SELECTED"
    assert row["selected_sequence_count"] == 128
    assert row["stake_yuan"] == 256
    assert abs(float(str(row["calibrated_mass"])) - 0.9**7) < 1e-12


def test_quality_no_bet_has_zero_ticket_count_and_no_descriptor():
    mod = load()
    legs = [leg(position, (0.4, 0.35, 0.25)) for position in range(1, 8)]
    row = mod.row_for("g", legs, "QUALITY_WEIGHTED_OMIT", "10001", 0.8, ["0"] * 7)
    assert row["selection_status"] == "NO_BET_BY_CHRONO_QUALITY"
    assert row["selected_sequence_count"] == row["stake_yuan"] == 0
    assert row["portfolio_descriptor_sha256"] == ""


def test_descriptor_binds_seed_omissions_and_exact_safe_source():
    mod = load()
    legs = [leg(position, (0.6, 0.3, 0.1)) for position in range(1, 8)]
    omitted = ["0"] * 7
    first = mod.descriptor("g", "WEIGHTED_OMIT", "10001", legs, omitted)
    assert first != mod.descriptor("g", "WEIGHTED_OMIT", "10002", legs, omitted)
    changed = [*omitted]
    changed[0] = "1"
    assert first != mod.descriptor("g", "WEIGHTED_OMIT", "10001", legs, changed)
    payload = {
        "contract": mod.CONTRACT_ID,
        "generator_version": mod.GENERATOR_VERSION,
        "group_id": "g",
        "arm": "WEIGHTED_OMIT",
        "seed": "10001",
        "code_order": mod.CODES,
        "omitted_codes_by_position": omitted,
        "ordered_identities": [
            (leg["match_id"], leg["issue"], leg["match_idx"], leg["fold"])
            for leg in legs
        ],
        "source_safe_leg_sha256": mod.SOURCE_LEGS_SHA,
    }
    assert (
        first
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
