from __future__ import annotations

import csv
import importlib.util
import sqlite3
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


def _write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _read_first_row(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as f:
        return next(csv.DictReader(f))


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
    assert execution.full_kept is True
    assert execution.action == "execute_full_cover"
    assert execution.selection_codes == ["1", "3", "0"]


def test_late_repriced_layer_conflict_anchors_probability_top_before_compressing() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.42",
        p_1="0.29",
        p_0="0.29",
        q_3="0.92",
        q_1="1.62",
        q_0="0.93",
        execution_sp_reprice_ratio_max="2.80",
    )
    decision = _decision(
        v4_action="wait_late_refresh",
        v4_recommended_codes="1+0+3",
        v4_full_cover_reasons="layer_conflict_requires_full_cover_or_skip",
        v4_merge_flags="layer_conflict_requires_full_cover_or_skip",
        v4_candidate_pool_json='[{"code":"1","score":2.0},{"code":"0","score":1.8},{"code":"3","score":0.1}]',
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=9.0)

    assert execution.action == "downgrade_full_to_double_layer_conflict"
    assert execution.selection_codes == ["3", "1"]
    assert execution.double_codes == ["3", "1"]
    assert "full_required_but_value_below_threshold" in execution.reasons


def test_late_q_top_drift_blocks_direct_buy_without_swapping_codes() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.345",
        p_1="0.251",
        p_0="0.403",
        q_3="1.262",
        q_1="0.857",
        q_0="0.927",
        source_q_3="0.937",
        source_q_1="0.822",
        source_q_0="1.233",
        execution_sp_reprice_ratio_max="1.35",
    )
    decision = _decision(
        v4_action="buy",
        v4_recommended_codes="0+1",
        v4_selection_codes="0+1",
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.action == "skip_late_q_top_drift"
    assert execution.selection_codes == []
    assert execution.double_codes == ["0", "1"]
    assert "late_q_top_drift_uncovered" in execution.reasons


def test_late_q_top_drift_does_not_block_value_only_sp_drift() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.3457146088540445",
        p_1="0.2513695493862822",
        p_0="0.40291584175967327",
        sp_3="3.6000",
        sp_1="3.4100",
        sp_0="2.3200",
        q_3="1.2446",
        q_1="0.8572",
        q_0="0.9348",
        source_sp_3="2.7100",
        source_sp_1="3.2700",
        source_sp_0="3.0600",
        source_q_3="0.9369",
        source_q_1="0.8220",
        source_q_0="1.2329",
        execution_sp_3="3.6000",
        execution_sp_1="3.4100",
        execution_sp_0="2.3200",
        execution_q_3="1.2446",
        execution_q_1="0.8572",
        execution_q_0="0.9348",
        execution_sp_reprice_ratio_max="1.3284",
    )
    decision = _decision(
        v4_action="buy",
        v4_recommended_codes="0+1",
        v4_selection_codes="0+1",
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.action == "execute_double"
    assert execution.selection_codes == ["0", "1"]
    assert execution.double_codes == ["0", "1"]
    assert "value_only_sp_drift" in execution.reasons
    assert "market_implied_p_weakened_3" in execution.reasons


def test_extreme_source_q_single_restores_probability_top_after_late_reprice() -> None:
    mod = _load_module()
    source = _source(
        prob_top="0",
        q_top="1",
        p_3="0.2953664966833232",
        p_1="0.32685944517886906",
        p_0="0.37777405813780773",
        sp_3="2.6500",
        sp_1="4.0600",
        sp_0="2.6400",
        q_3="0.7827",
        q_1="1.3270",
        q_0="0.9973",
        source_sp_3="33.5100",
        source_sp_1="2.0800",
        source_sp_0="2.0300",
        source_q_3="9.8977",
        source_q_1="0.6799",
        source_q_0="0.7669",
        execution_sp_3="2.6500",
        execution_sp_1="4.0600",
        execution_sp_0="2.6400",
        execution_q_3="0.7827",
        execution_q_1="1.3270",
        execution_q_0="0.9973",
        execution_sp_reprice_ratio_max="12.6453",
    )
    decision = _decision(
        v4_action="wait_late_refresh",
        v4_recommended_codes="3",
        v4_selection_codes="",
        v4_mandatory_codes="3",
        v4_full_cover_reasons="extreme_sp_or_source_conflict_full",
        v4_merge_flags="suppress_unbacked_late_refresh_draw",
        v4_candidate_pool_json=(
            '[{"code":"3","score":1.3234,"mandatory":true},'
            '{"code":"1","score":1.1393,"signals":["late_refresh_neighbor_draw"]},'
            '{"code":"0","score":0.8733,"signals":["model_top"]}]'
        ),
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.action == "execute_double"
    assert execution.selection_codes == ["0", "1"]
    assert execution.double_codes == ["0", "1"]
    assert "extreme_source_q_repriced_probability_guard" in execution.reasons


def test_probability_anchor_keeps_cover_win_when_q_top_is_weak() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.426",
        p_1="0.258",
        p_0="0.317",
        sp_3="2.05",
        sp_1="4.30",
        sp_0="3.55",
        q_3="0.873",
        q_1="1.108",
        q_0="1.124",
        execution_sp_reprice_ratio_max="2.15",
    )
    decision = _decision(
        v4_action="full_cover_or_skip",
        v4_recommended_codes="0+1+3",
        v4_mandatory_codes="1",
        v4_protected_codes="1",
        v4_semantic_draw="explicit_draw",
        v4_team_strength_side="home",
        v4_team_strength_confidence="0.90",
        v4_team_strength_codes="3",
        v4_full_cover_reasons="candidate_score_dense;layer_conflict_requires_full_cover_or_skip",
        v4_merge_flags="layer_conflict_requires_full_cover_or_skip",
        v4_candidate_pool_json='[{"code":"0","score":2.0713},{"code":"1","score":1.9761},{"code":"3","score":1.5492}]',
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.action == "downgrade_full_to_double_layer_conflict"
    assert execution.selection_codes == ["3", "1"]
    assert execution.double_codes == ["3", "1"]


def test_probability_anchor_lets_remaining_outcomes_compete_without_promoting_full_cover() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.449",
        p_1="0.243",
        p_0="0.308",
        sp_3="1.30",
        sp_1="10.03",
        sp_0="7.40",
        q_3="0.583",
        q_1="2.437",
        q_0="2.283",
        execution_sp_reprice_ratio_max="2.75",
    )
    decision = _decision(
        v4_action="full_cover_or_skip",
        v4_recommended_codes="3+1+0",
        v4_mandatory_codes="1+0",
        v4_semantic_draw="balanced",
        v4_team_strength_side="away",
        v4_team_strength_confidence="0.90",
        v4_team_strength_codes="0",
        v4_full_cover_reasons="candidate_score_dense;layer_conflict_requires_full_cover_or_skip",
        v4_merge_flags="layer_conflict_requires_full_cover_or_skip",
        v4_candidate_pool_json='[{"code":"3","score":1.5414},{"code":"1","score":1.4005},{"code":"0","score":1.3449}]',
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.6)

    assert execution.action == "downgrade_full_to_double_layer_conflict"
    assert execution.full_candidate is False
    assert execution.selection_codes == ["3", "0"]
    assert execution.double_codes == ["3", "0"]


def test_probability_anchor_can_compress_mandatory_overflow() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.449",
        p_1="0.243",
        p_0="0.308",
        sp_3="1.30",
        sp_1="10.03",
        sp_0="7.40",
        q_3="0.583",
        q_1="2.437",
        q_0="2.283",
        execution_sp_reprice_ratio_max="2.75",
    )
    decision = _decision(
        v4_action="wait_late_refresh",
        v4_recommended_codes="1+3+0",
        v4_mandatory_codes="1+3+0",
        v4_semantic_draw="balanced",
        v4_team_strength_side="away",
        v4_team_strength_confidence="0.90",
        v4_team_strength_codes="0",
        v4_full_cover_reasons="candidate_score_dense;layer_conflict_requires_full_cover_or_skip",
        v4_merge_flags="layer_conflict_requires_full_cover_or_skip",
        v4_candidate_pool_json='[{"code":"1","score":1.5414},{"code":"3","score":1.4005},{"code":"0","score":1.3449}]',
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=9.0)

    assert execution.action == "downgrade_full_to_double_layer_conflict"
    assert execution.selection_codes == ["3", "0"]
    assert execution.double_codes == ["3", "0"]


def test_tight_dense_compression_keeps_market_supported_probability_top() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.3166063325742699",
        p_1="0.3006215407033773",
        p_0="0.38277212672235283",
        sp_3="4.7000",
        sp_1="2.8400",
        sp_0="2.2900",
        q_3="1.4880",
        q_1="0.8538",
        q_0="0.8765",
        source_sp_3="3.1400",
        source_sp_1="2.1700",
        source_sp_0="4.5200",
        source_q_3="0.9941",
        source_q_1="0.6523",
        source_q_0="1.7301",
        execution_sp_3="4.7000",
        execution_sp_1="2.8400",
        execution_sp_0="2.2900",
        execution_q_3="1.4880",
        execution_q_1="0.8538",
        execution_q_0="0.8765",
        execution_sp_reprice_ratio_max="1.9738",
    )
    decision = _decision(
        v4_action="full_cover_or_skip",
        v4_recommended_codes="3+1+0",
        v4_mandatory_codes="3+1",
        v4_semantic_draw="explicit_draw",
        v4_full_cover_reasons="candidate_score_dense;layer_conflict_requires_full_cover_or_skip;tight_dense_requires_full_or_skip",
        v4_merge_flags="layer_conflict_requires_full_cover_or_skip",
        v4_candidate_pool_json='[{"code":"3","score":1.6784},{"code":"1","score":1.4550},{"code":"0","score":1.1420}]',
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.action == "downgrade_full_to_double_layer_conflict"
    assert execution.selection_codes == ["0", "3"]
    assert execution.double_codes == ["0", "3"]


def test_late_refresh_pending_draw_rescue_for_skipped_unbacked_high_q_draw() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.44497214737447593",
        p_1="0.297789526187624",
        p_0="0.25723832643790007",
        sp_3="2.8000",
        sp_1="3.0700",
        sp_0="3.1400",
        q_3="1.2459",
        q_1="0.9142",
        q_0="0.8077",
        execution_sp_3="2.8000",
        execution_sp_1="3.0700",
        execution_sp_0="3.1400",
        execution_sp_reprice_ratio_max="3.2052",
    )
    decision = _decision(
        v4_action="wait_late_refresh",
        v4_recommended_codes="3+0",
        v4_selection_codes="",
        v4_team_strength_confidence="0.748",
        v4_merge_flags="skip_unbacked_high_q_draw",
        v4_full_cover_reasons="extreme_sp_or_source_conflict_full",
        v4_candidate_pool_json=(
            '[{"code":"3","score":1.2025},{"code":"0","score":0.9859},'
            '{"code":"1","score":0.7714,"pending_score":0.45,'
            '"signals":["late_refresh_neighbor_draw","model_probability"],"pending_signals":["market_q_ev"]}]'
        ),
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.action == "execute_double"
    assert execution.selection_codes == ["3", "1"]
    assert execution.double_codes == ["3", "1"]
    assert "late_refresh_pending_draw_rescue" in execution.reasons


def test_late_refresh_pending_draw_rescue_does_not_override_high_q_make_room() -> None:
    mod = _load_module()
    source = _source(
        p_3="0.44984094521808515",
        p_1="0.2994669214860346",
        p_0="0.25069213329588025",
        sp_3="2.0800",
        sp_1="3.8300",
        sp_0="3.8400",
        q_3="0.9357",
        q_1="1.1470",
        q_0="0.9627",
        execution_sp_3="2.0800",
        execution_sp_1="3.8300",
        execution_sp_0="3.8400",
        execution_sp_reprice_ratio_max="9.2891",
    )
    decision = _decision(
        v4_action="wait_late_refresh",
        v4_recommended_codes="3+0",
        v4_selection_codes="",
        v4_team_strength_confidence="0.547",
        v4_merge_flags="high_q_attraction;make_room_for_high_q_attraction",
        v4_full_cover_reasons="extreme_sp_or_source_conflict_full",
        v4_candidate_pool_json=(
            '[{"code":"3","score":2.0056},{"code":"1","score":1.2681,'
            '"signals":["handicap_translation:ordinary_draw_translation","late_refresh_neighbor_draw","model_probability"]},'
            '{"code":"0","score":0.4136,"pending_score":0.45,"pending_signals":["market_q_ev"]}]'
        ),
    )

    execution = mod.evaluate_row_policy(source, decision, late_refresh_mode="proxy", full_score_threshold=1.4)

    assert execution.action == "execute_double"
    assert execution.selection_codes == ["3", "0"]
    assert execution.double_codes == ["3", "0"]
    assert "late_refresh_pending_draw_rescue" not in execution.reasons


def test_segment_annotation_does_not_cap_or_downgrade_full_candidates() -> None:
    mod = _load_module()
    first = mod.RowExecution(["3", "1", "0"], "execute_full_cover", [], ["3", "1"], 2.0, True, True)
    second = mod.RowExecution(["3", "1", "0"], "execute_full_cover", [], ["0", "1"], 1.5, True, True)
    executions = {1: first, 2: second}
    segment_lookup = {1: 1, 2: 1}

    mod.annotate_execution_segments(executions, segment_lookup)

    assert first.action == "execute_full_cover"
    assert first.selection_codes == ["3", "1", "0"]
    assert first.full_kept is True
    assert first.segment_idx == 1
    assert second.action == "execute_full_cover"
    assert second.selection_codes == ["3", "1", "0"]
    assert second.full_kept is True
    assert second.segment_idx == 1


def test_late_proxy_reprices_stale_source_sp_before_full_cover_scoring(tmp_path: Path) -> None:
    mod = _load_module()
    issue = "26072"
    db_path = tmp_path / "500.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE matches (
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                end_time TEXT,
                league TEXT,
                home TEXT,
                away TEXT,
                result_code TEXT,
                winning_sp REAL,
                PRIMARY KEY (issue, match_idx)
            );
            CREATE TABLE live_sp_snapshots (
                issue TEXT NOT NULL,
                playid INTEGER NOT NULL,
                fetched_at TEXT NOT NULL,
                source_updatetime TEXT,
                row_idx INTEGER NOT NULL,
                home TEXT,
                away TEXT,
                league TEXT,
                handicap_line REAL,
                sp_home REAL,
                sp_draw REAL,
                sp_away REAL,
                raw_node TEXT,
                PRIMARY KEY (issue, playid, fetched_at, row_idx)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO matches(issue, match_idx, end_time, league, home, away, result_code, winning_sp)
            VALUES('26072', 51, '2026-07-05 20:00:00', 'K2联赛', '庆南FC', '天安城', NULL, NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO live_sp_snapshots(
                issue, playid, fetched_at, source_updatetime, row_idx,
                home, away, league, handicap_line, sp_home, sp_draw, sp_away, raw_node
            )
            VALUES('26072', 34, '2026-07-05T12:00:00+00:00', '2026-07-05T12:00:00+00:00', 51,
                   '庆南FC', '天安城', 'K2联赛', 0, 2.37, 3.26, 3.65, 'fresh')
            """
        )
        conn.commit()
    finally:
        conn.close()

    source_csv = _write_rows(
        tmp_path / "source.csv",
        [
            {
                "issue": issue,
                "match_idx": "51",
                "match_id": "26072_051",
                "active_selection_codes": "3",
                "shadow_selection_codes": "1+0+3",
                "p_3": "0.40",
                "p_1": "0.28",
                "p_0": "0.3255",
                "sp_3": "14.84",
                "sp_1": "1.08",
                "sp_0": "70.94",
                "q_3": "5.9360",
                "q_1": "0.3024",
                "q_0": "23.0900",
                "prob_top": "3",
                "q_top": "0",
                "max_q": "23.0900",
                "shadow_arm": "shadow_v3.3.3",
                "shadow_version": "fixture",
                "shadow_primary": "1",
                "shadow_judgment": "",
                "shadow_stop_flag": "0",
                "selection_type": "full",
            }
        ],
        [
            "issue",
            "match_idx",
            "match_id",
            "active_selection_codes",
            "shadow_selection_codes",
            "p_3",
            "p_1",
            "p_0",
            "sp_3",
            "sp_1",
            "sp_0",
            "q_3",
            "q_1",
            "q_0",
            "prob_top",
            "q_top",
            "max_q",
            "shadow_arm",
            "shadow_version",
            "shadow_primary",
            "shadow_judgment",
            "shadow_stop_flag",
            "selection_type",
        ],
    )
    decision_csv = _write_rows(
        tmp_path / "decision.csv",
        [
            {
                "match_idx": "51",
                "v4_action": "wait_late_refresh",
                "v4_recommended_codes": "1+0+3",
                "v4_selection_codes": "",
                "v4_semantic_draw": "balanced",
                "v4_team_strength_side": "mixed",
                "v4_team_strength_confidence": "0.55",
                "v4_team_strength_codes": "",
                "v4_mandatory_codes": "",
                "v4_protected_codes": "",
                "v4_full_cover_reasons": "layer_conflict_requires_full_cover_or_skip;candidate_score_dense;extreme_sp_or_source_conflict_full",
                "v4_merge_flags": "layer_conflict_requires_full_cover_or_skip",
                "v4_candidate_pool_json": '[{"code":"1","score":1.2},{"code":"0","score":1.1},{"code":"3","score":1.0}]',
            }
        ],
        [
            "match_idx",
            "v4_action",
            "v4_recommended_codes",
            "v4_selection_codes",
            "v4_semantic_draw",
            "v4_team_strength_side",
            "v4_team_strength_confidence",
            "v4_team_strength_codes",
            "v4_mandatory_codes",
            "v4_protected_codes",
            "v4_full_cover_reasons",
            "v4_merge_flags",
            "v4_candidate_pool_json",
        ],
    )
    output_csv = tmp_path / "out.csv"
    mod.apply_policy(
        issue=issue,
        source_csv=source_csv,
        decision_csv=decision_csv,
        db_path=db_path,
        output_csv=output_csv,
        report_path=tmp_path / "report.md",
        late_refresh_mode="proxy",
        full_score_threshold=1.40,
        max_full_per_segment=2,
        window_hours=12.0,
        extend_hours="18,24,36",
        min_matches=1,
        max_matches=24,
        policy_name="late_proxy_fullcap2",
        execution_sp_mode="latest_trusted",
    )

    row = _read_first_row(output_csv)
    assert row["source_sp_0"] == "70.9400"
    assert row["execution_sp_0"] == "3.6500"
    assert row["sp_0"] == "3.6500"
    assert row["execution_q_0"] == "1.1881"
    assert row["execution_sp_source"] == "live_sp_snapshots"
    assert row["execution_sp_repriced"] == "1"
    assert "sp_repriced_after_late_refresh" in row["execution_reasons"]
    assert row["execution_action"] != "execute_full_cover"
    assert row["execution_full_kept"] == "0"
    assert row["shadow_selection_codes"] != "1+0+3"


def test_late_proxy_blocks_unlock_when_execution_sp_is_missing(tmp_path: Path) -> None:
    mod = _load_module()
    issue = "26072"
    db_path = tmp_path / "500.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE matches (
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                end_time TEXT,
                league TEXT,
                home TEXT,
                away TEXT,
                result_code TEXT,
                winning_sp REAL,
                PRIMARY KEY (issue, match_idx)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO matches(issue, match_idx, end_time, league, home, away, result_code, winning_sp)
            VALUES('26072', 51, '2026-07-05 20:00:00', 'K2联赛', '庆南FC', '天安城', NULL, NULL)
            """
        )
        conn.commit()
    finally:
        conn.close()

    source_csv = _write_rows(
        tmp_path / "source.csv",
        [_source(issue=issue, match_idx="51", match_id="26072_051", active_selection_codes="3", shadow_selection_codes="3+1")],
        [
            "issue",
            "match_idx",
            "match_id",
            "active_selection_codes",
            "shadow_selection_codes",
            "prob_top",
            "q_top",
            "p_3",
            "p_1",
            "p_0",
            "sp_3",
            "sp_1",
            "sp_0",
            "q_3",
            "q_1",
            "q_0",
        ],
    )
    decision_csv = _write_rows(
        tmp_path / "decision.csv",
        [_decision(match_idx="51", v4_action="wait_late_refresh", v4_recommended_codes="3+1", v4_selection_codes="")],
        [
            "match_idx",
            "v4_action",
            "v4_recommended_codes",
            "v4_selection_codes",
            "v4_semantic_draw",
            "v4_team_strength_side",
            "v4_team_strength_confidence",
            "v4_team_strength_codes",
            "v4_mandatory_codes",
            "v4_protected_codes",
            "v4_full_cover_reasons",
            "v4_merge_flags",
            "v4_candidate_pool_json",
        ],
    )
    output_csv = tmp_path / "out.csv"
    mod.apply_policy(
        issue=issue,
        source_csv=source_csv,
        decision_csv=decision_csv,
        db_path=db_path,
        output_csv=output_csv,
        report_path=tmp_path / "report.md",
        late_refresh_mode="proxy",
        full_score_threshold=1.40,
        max_full_per_segment=2,
        window_hours=12.0,
        extend_hours="18,24,36",
        min_matches=1,
        max_matches=24,
        policy_name="late_proxy_fullcap2",
        execution_sp_mode="latest_trusted",
    )

    row = _read_first_row(output_csv)
    assert row["execution_action"] == "skip_missing_execution_sp"
    assert row["execution_unlock_state"] == "blocked_after_late_refresh"
    assert row["execution_sp_missing"] == "1"
    assert row["shadow_selection_codes"] == ""
