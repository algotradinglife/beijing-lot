from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/apply_decision_execution_policy_v4_2.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("apply_decision_execution_policy_v4_2", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _source(**overrides):
    row = {
        "issue": "test",
        "match_idx": "1",
        "prob_top": "3",
        "q_top": "1",
        "p_3": "0.42",
        "p_1": "0.29",
        "p_0": "0.29",
        "sp_3": "2.20",
        "sp_1": "5.60",
        "sp_0": "3.20",
        "q_3": "0.924",
        "q_1": "1.624",
        "q_0": "0.928",
    }
    row.update(overrides)
    return row


def _decision(**overrides):
    row = {
        "v4_action": "buy",
        "v4_recommended_codes": "3+1",
        "v4_selection_codes": "3+1",
        "v4_semantic_draw": "none",
        "v4_team_strength_side": "home",
        "v4_team_strength_confidence": "0.80",
        "v4_team_strength_codes": "3",
        "v4_mandatory_codes": "",
        "v4_protected_codes": "",
        "v4_full_cover_reasons": "",
        "v4_merge_flags": "",
        "v4_candidate_pool_json": (
            '[{"code":"3","score":1.4},{"code":"1","score":0.8},{"code":"0","score":0.5}]'
        ),
    }
    row.update(overrides)
    return row


def test_wait_late_refresh_is_no_buy_until_proxy_mode() -> None:
    mod = _load_module()
    source = _source()
    decision = _decision(v4_action="wait_late_refresh", v4_recommended_codes="3+1", v4_selection_codes="")

    strict = mod.evaluate_row_policy(source, decision, late_refresh_mode="skip", full_score_threshold=1.4)
    proxy = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert strict.selection_codes == []
    assert strict.action == "skip_wait_late_refresh"
    assert mod.execution_unlock_state("wait_late_refresh", strict) == "waiting_late_refresh"
    assert proxy.selection_codes == ["3", "1"]
    assert proxy.action == "execute_double"
    assert mod.execution_unlock_state("wait_late_refresh", proxy) == "unlocked_after_late_refresh"
    assert mod.execution_unlock_state("buy", proxy) == "not_applicable"


def test_low_value_full_cover_is_downgraded_to_best_double() -> None:
    mod = _load_module()
    source = _source(q_top="1", q_1="1.12", p_1="0.24", sp_1="4.67")
    decision = _decision(
        v4_action="buy",
        v4_recommended_codes="3+1+0",
        v4_full_cover_reasons="candidate_score_dense",
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.action == "downgrade_full_to_double"
    assert execution.selection_codes == ["3", "0"]
    assert execution.full_candidate is False


def test_layer_conflict_full_can_be_candidate_when_third_code_has_value() -> None:
    mod = _load_module()
    source = _source(
        prob_top="0",
        q_top="1",
        p_3="0.28",
        p_1="0.31",
        p_0="0.41",
        sp_3="5.80",
        sp_1="8.90",
        sp_0="6.00",
        q_3="1.624",
        q_1="2.759",
        q_0="2.460",
    )
    decision = _decision(
        v4_action="wait_late_refresh",
        v4_recommended_codes="1+3+0",
        v4_team_strength_side="home",
        v4_team_strength_codes="3",
        v4_full_cover_reasons="layer_conflict_requires_full_cover_or_skip;extreme_sp_or_source_conflict_full",
        v4_merge_flags="layer_conflict_requires_full_cover_or_skip",
        v4_candidate_pool_json='[{"code":"1","score":1.2},{"code":"3","score":1.1},{"code":"0","score":1.0}]',
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.full_candidate is True
    assert execution.action == "candidate_full_cover"
    assert execution.selection_codes == ["1", "3", "0"]


def test_segment_full_cap_keeps_top_candidate_and_downgrades_overflow() -> None:
    mod = _load_module()
    first = mod.RowExecution(["3", "1", "0"], "candidate_full_cover", [], ["3", "1"], 2.0, True, False)
    second = mod.RowExecution(["3", "1", "0"], "candidate_full_cover", [], ["0", "1"], 1.5, True, False)
    executions = {1: first, 2: second}
    segment_lookup = {1: 1, 2: 1}

    mod.apply_segment_full_cap(executions, segment_lookup, max_full_per_segment=1)

    assert first.action == "execute_full_cover"
    assert first.selection_codes == ["3", "1", "0"]
    assert first.full_kept is True
    assert second.action == "downgrade_full_to_double_over_cap"
    assert second.selection_codes == ["0", "1"]
