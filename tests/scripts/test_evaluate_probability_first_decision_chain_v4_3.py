from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate_probability_first_decision_chain_v4_3.py"


def load_module():
    spec = importlib.util.spec_from_file_location("evaluate_probability_first_decision_chain_v4_3", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def snapshot(module, *, probabilities, source_sp, euro_avg, latest_sp):
    return module.SnapshotRow(
        issue="26072",
        match_idx=61,
        league="fixture",
        home="home",
        away="away",
        handicap_line=0.0,
        score="",
        result_code=None,
        winning_sp=None,
        result_source="",
        payload={
            "model": {"probabilities": probabilities, "market_probabilities": probabilities},
            "sp": source_sp,
            "market": {"odds_consensus": {"current_avg": euro_avg}},
        },
        latest_sp=latest_sp,
    )


def test_extreme_source_q_cannot_override_probability_top() -> None:
    module = load_module()
    row = snapshot(
        module,
        probabilities={"3": 0.2953664967, "1": 0.3268594452, "0": 0.3777740581},
        source_sp={"3": 33.51, "1": 2.08, "0": 2.03},
        euro_avg={"home": 2.438, "draw": 3.565, "away": 2.556},
        latest_sp={"3": 2.65, "1": 4.06, "0": 2.64},
    )

    decision = module.probability_first_decision(row)

    assert decision.primary == "0"
    assert decision.codes[0] == "0"
    assert "3" not in decision.codes
    assert "1" in decision.codes
    assert "source_sp_sanity_anomaly" in decision.risk_tags
    assert "drop_source_q_top_after_sp_sanity" in decision.risk_tags


def test_probability_top_is_kept_when_high_q_away_is_extreme() -> None:
    module = load_module()
    row = snapshot(
        module,
        probabilities={"3": 0.3736479169, "1": 0.3008056407, "0": 0.3255464424},
        source_sp={"3": 14.84, "1": 1.08, "0": 70.94},
        euro_avg={"home": 2.524, "draw": 3.012, "away": 2.668},
        latest_sp={"3": 2.40, "1": 3.32, "0": 3.52},
    )

    decision = module.probability_first_decision(row)

    assert decision.primary == "3"
    assert decision.codes[0] == "3"
    assert decision.source_q_top != decision.primary
    assert "source_sp_sanity_anomaly" in decision.risk_tags


def test_low_probability_q_top_is_only_a_risk_tag_not_primary() -> None:
    module = load_module()
    row = snapshot(
        module,
        probabilities={"3": 0.52, "1": 0.31, "0": 0.17},
        source_sp={"3": 1.80, "1": 3.20, "0": 9.50},
        euro_avg={"home": 1.82, "draw": 3.18, "away": 9.20},
        latest_sp={"3": 1.80, "1": 3.20, "0": 9.50},
    )

    decision = module.probability_first_decision(row)

    assert decision.primary == "3"
    assert "0" not in decision.codes
    assert "q_top_not_used_as_primary" in decision.risk_tags
