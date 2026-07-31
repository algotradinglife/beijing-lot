from __future__ import annotations

import importlib.util
import itertools
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj95_n7_pruning_gate_a.py"


def load():
    spec = importlib.util.spec_from_file_location("bj95_pruning", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def leg(position: int, calibrated: tuple[float, float, float], euro: tuple[float, float, float]):
    return {
        "group_id": "PRIMARY-N7-test", "position": position,
        "calibrated_probability": dict(zip(("3", "1", "0"), calibrated)),
        "euro_probability": dict(zip(("3", "1", "0"), euro)),
        "predicted_sp": {"3": 2.0, "1": 3.0, "0": 4.0},
        "sp5": {"3": 2.0, "1": 3.0, "0": 4.0},
        "handicap_line_norm": "0.0",
    }


def test_analytic_allowed_sets_enumerate_to_the_declared_k():
    mod = load()
    legs = [leg(position, (0.60, 0.30, 0.10), (0.55, 0.35, 0.10)) for position in range(1, 8)]
    order, unavailable = mod.deletion_order(legs, "CAL_MIN_P")
    assert unavailable is None
    for depth in range(8):
        deleted = {item["leg"]["position"]: item["code"] for item in order[:depth]}
        allowed = [tuple(code for code in mod.CODES if code != deleted.get(position)) for position in range(1, 8)]
        sequences = list(itertools.product(*allowed))
        assert len(sequences) == 2**depth * 3**(7 - depth)
        assert len(set(sequences)) == len(sequences)
        assert mod.descriptor("PRIMARY-N7-test", "CAL_MIN_P", depth, allowed) == mod.descriptor(
            "PRIMARY-N7-test", "CAL_MIN_P", depth, allowed
        )


def test_model_market_agree_is_unavailable_only_after_eligible_removals():
    mod = load()
    legs = [leg(position, (0.5, 0.3, 0.2), (0.5, 0.2, 0.3)) for position in range(1, 8)]
    for position in (1, 2, 3):
        legs[position - 1]["euro_probability"] = {"3": 0.5, "1": 0.3, "0": 0.2}
    order, unavailable = mod.deletion_order(legs, "MODEL_MARKET_AGREE")
    assert unavailable == "UNAVAILABLE_BY_RULE"
    assert len(order) == 3
    assert all(item["code"] == "0" for item in order)


def test_random_baseline_is_deterministic_and_outcome_free():
    mod = load()
    legs = [leg(position, (0.5, 0.3, 0.2), (0.4, 0.35, 0.25)) for position in range(1, 8)]
    first, unavailable_first = mod.deletion_order(legs, "RANDOM_HASH_BASELINE")
    second, unavailable_second = mod.deletion_order(legs, "RANDOM_HASH_BASELINE")
    assert unavailable_first is unavailable_second is None
    assert [(item["leg"]["position"], item["code"]) for item in first] == [
        (item["leg"]["position"], item["code"]) for item in second
    ]
    assert "outcome" not in " ".join(mod.LEG_FIELDS + mod.FRONTIER_FIELDS + mod.DELETION_FIELDS).lower()
