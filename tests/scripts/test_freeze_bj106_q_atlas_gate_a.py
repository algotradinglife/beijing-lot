from __future__ import annotations

import importlib.util
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj106_q_atlas_gate_a.py"
SPEC = importlib.util.spec_from_file_location("freeze_bj106_q_atlas_gate_a", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_fixed_probability_sp_and_q_bands() -> None:
    assert MOD.probability_band(0.0999) == "P00_10"
    assert MOD.probability_band(0.10) == "P10_20"
    assert MOD.sp_band(4.999) == "SP3_5"
    assert MOD.sp_band(5.0) == "SP5_10"
    assert MOD.q_band(MOD.Q_HIGH_BAND_BOUNDARY - 1e-9) == "Q135_1538"
    assert MOD.q_band(MOD.Q_HIGH_BAND_BOUNDARY) == "Q1538_200"


def test_n4_n9_gm_break_even_applies_factor_once_per_complete_ticket() -> None:
    assert set(MOD.GM_REFERENCE_THRESHOLDS) == set(range(4, 10))
    for n_legs, threshold in MOD.GM_REFERENCE_THRESHOLDS.items():
        assert math.isclose(
            MOD.complete_ticket_gross((threshold,) * n_legs),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )


def test_comparison_family_has_no_per_leg_q_gate() -> None:
    assert MOD.comparison_eligible(MOD.MIN_SUPPORT, 3, "L3_CODE_P_QLB")
    assert not MOD.comparison_eligible(MOD.MIN_SUPPORT - 1, 3, "L3_CODE_P_QLB")
    assert not MOD.comparison_eligible(MOD.MIN_SUPPORT, 2, "L3_CODE_P_QLB")
    assert not MOD.comparison_eligible(MOD.MIN_SUPPORT, 3, "L5_CODE_ONLY")


def test_sparse_stratum_fallback_order_is_deterministic() -> None:
    row = {
        "candidate_code": "3",
        "probability_band": "P35_50",
        "q_lb_band": "Q110_135",
        "handicap_line_norm": "0.0",
        "handicap_sign": "HZERO",
    }
    candidates = MOD.stratum_candidates(row)
    assert [level for _candidate, level in candidates] == [
        "L1_EXACT_HANDICAP",
        "L2_HANDICAP_SIGN",
        "L3_CODE_P_QLB",
        "L4_CODE_QLB",
        "L5_CODE_ONLY",
    ]
    assert candidates[0][0] == "CODE=3|P=P35_50|QLB=Q110_135|H=0.0"


def test_gate_a_atlas_uses_candidate_code_not_observed_result() -> None:
    lowered = [field.lower() for field in MOD.ATLAS_FIELDS]
    assert "candidate_code" in lowered
    assert not any(
        "result" in field or "winning" in field or "payout" in field or "roi" in field
        for field in lowered
    )


def test_handicap_sign_is_numeric_and_neutral_safe() -> None:
    assert MOD.handicap_sign("-0.5") == "HNEG"
    assert MOD.handicap_sign("0.0") == "HZERO"
    assert MOD.handicap_sign("0.5") == "HPOS"
