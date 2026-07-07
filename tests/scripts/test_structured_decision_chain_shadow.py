from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate_structured_decision_chain_shadow.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("evaluate_structured_decision_chain_shadow", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_raw_home_strength_is_not_direct_handicap_win_when_home_gives_two() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "test",
            "match_idx": 1,
            "home": "强队",
            "away": "弱队",
            "league": "杯赛",
            "handicap_line": -2,
            "line_gap": 0.0,
        },
        "model": {
            "probabilities": {"3": 0.36, "1": 0.33, "0": 0.31},
            "market_probabilities": {"3": 0.36, "1": 0.33, "0": 0.31},
        },
        "sp": {"3": 2.8, "1": 3.2, "0": 3.1},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {"status": "ok", "highlights": []},
        "intelligence": {
            "status": "ok",
            "points": ["资料观点：强队近期状态出色，整体实力更胜弱队一筹，强队胜利在望。"],
        },
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["sections"]["raw_strength"]["side"] == "home"
    assert decision["sections"]["handicap_fit"]["code"] != "3"
    assert "raw_strength_not_handicap_result" in decision["risk_tags"]


def test_big_margin_home_strength_can_map_to_deep_handicap_win() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "test",
            "match_idx": 1,
            "home": "强队",
            "away": "弱队",
            "league": "杯赛",
            "handicap_line": -2,
            "line_gap": 0.0,
        },
        "model": {
            "probabilities": {"3": 0.29, "1": 0.22, "0": 0.49},
            "market_probabilities": {"3": 0.74, "1": 0.16, "0": 0.10},
        },
        "sp": {"3": 2.7, "1": 3.2, "0": 3.1},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {"status": "ok", "highlights": []},
        "intelligence": {
            "status": "ok",
            "points": ["资料观点：强队每场至少攻入3球，强队火力无人能挡，强队火力强劲，强队胜券在握。"],
        },
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["sections"]["raw_strength"]["side"] == "home"
    assert decision["sections"]["handicap_fit"]["code"] == "3"
    assert decision["primary_pick"] == "3"
    assert "raw_strength_not_handicap_result" not in decision["risk_tags"]


def test_minus_one_handicap_draw_can_be_nearby_protection() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "test",
            "match_idx": 7,
            "home": "赫尔辛基",
            "away": "伊尔维斯",
            "league": "芬兰杯",
            "handicap_line": -1,
            "line_gap": -0.25,
        },
        "model": {
            "probabilities": {"3": 0.3029897253399321, "1": 0.2642081934757328, "0": 0.432802081184335},
            "market_probabilities": {"3": 0.5617859026190895, "1": 0.22306204956934433, "0": 0.21515204781156616},
        },
        "sp": {"3": 2.89, "1": 3.84, "0": 2.53},
        "market": {"odds_consensus": {"drift": {"home": -0.018, "draw": 0.0344, "away": 0.0523}}},
        "analysis": {
            "status": "ok",
            "home_recent": "主队近10场 6胜2平2负，进失38/15，半场平2场",
            "away_recent": "客队近10场 5胜2平3负，进失22/18，半场平3场",
            "highlights": [],
        },
        "intelligence": {
            "status": "ok",
            "points": ["资料观点：伊斯韦斯不擅作客，而且近况也出现下滑，是役理应对赫尔辛基的赢面看高一线。"],
            "stage": {"stage_type": "knockout", "competition_label": "26芬兰杯半决赛"},
        },
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["primary_pick"] == "0"
    assert "1" in decision["protect_picks"]
    assert decision["selection_codes"] == ["0", "1"]


def test_26071_016_shape_primary_probability_with_q_protection() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "26071",
            "match_id": "26071_016",
            "match_idx": 16,
            "league": "世界杯",
            "home": "瑞士",
            "away": "阿尔及利亚",
            "handicap_line": 0.0,
            "ah_line": "半球",
            "line_gap": 0.5,
        },
        "model": {
            "probabilities": {"3": 0.4821153953276072, "1": 0.2766075536014063, "0": 0.2412770510709865},
            "market_probabilities": {"3": 0.4739076927505776, "1": 0.2943526041929053, "0": 0.23173970305651717},
        },
        "sp": {"3": 1.77, "1": 3.24, "0": 7.77},
        "market": {
            "odds_consensus": {
                "drift": {
                    "home": 0.163,
                    "draw": -0.1139,
                    "away": -0.1639,
                }
            }
        },
        "analysis": {
            "status": "ok",
            "home_recent": "主队近10场 4胜5平1负，进失20/11，半场平7场，近5走势胜-胜-平-平-胜",
            "away_recent": "客队近10场 5胜3平2负，进失20/10，半场平5场，近5走势平-胜-负-胜-胜",
            "highlights": [
                "主队近10场 4胜5平1负，进失20/11，半场平7场，近5走势胜-胜-平-平-胜",
                "客队近10场 5胜3平2负，进失20/10，半场平5场，近5走势平-胜-负-胜-胜",
                "欧赔均值 主胜+16.3% 平-11.4% 客胜-16.4%",
            ],
        },
        "intelligence": {
            "status": "ok",
            "points": [
                "排名：瑞士第3，阿尔及利亚第7",
                "资料观点：瑞士分组赛表现更胜阿尔及利亚一筹，而且前者近期处于两连胜之中，连胜期间狂入6球，火力相当强劲，瑞士胜利在望。",
            ],
        },
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["decision_version"] == "llm_chain_bet_protect_stop_v3.3.3_shadow"
    assert decision["primary_pick"] == "3"
    assert decision["protect_picks"] == ["0"]
    assert decision["selection_codes"] == ["3", "0"]
    assert "q_high_but_probability_low" in decision["risk_tags"]


def test_payload_llm_intel_advice_can_add_protection_only() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "test",
            "match_idx": 2,
            "home": "主队",
            "away": "客队",
            "league": "杯赛",
            "handicap_line": 0,
            "line_gap": 0.0,
        },
        "model": {
            "probabilities": {"3": 0.52, "1": 0.26, "0": 0.22},
            "market_probabilities": {"3": 0.50, "1": 0.27, "0": 0.23},
        },
        "sp": {"3": 2.10, "1": 3.20, "0": 3.40},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {"status": "ok", "highlights": []},
        "intelligence": {
            "status": "ok",
            "points": ["资料观点：主队状态稳定，但客队反击效率较高，存在爆冷空间。"],
            "llm_protection": {
                "should_protect": True,
                "protect_code": "0",
                "protect_strength": 0.72,
                "confidence": 0.70,
                "evidence": ["情报认为客队反击与杯赛场景构成保护价值。"],
            },
        },
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["primary_pick"] == "3"
    assert decision["protect_picks"] == ["0"]
    assert decision["selection_codes"] == ["3", "0"]
    assert decision["sections"]["llm_intel_protection"]["source"] == "payload_llm"


def test_weak_payload_llm_intel_advice_is_not_applied() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "test",
            "match_idx": 3,
            "home": "主队",
            "away": "客队",
            "league": "联赛",
            "handicap_line": 0,
            "line_gap": 0.0,
        },
        "model": {
            "probabilities": {"3": 0.61, "1": 0.24, "0": 0.15},
            "market_probabilities": {"3": 0.58, "1": 0.25, "0": 0.17},
        },
        "sp": {"3": 1.80, "1": 3.15, "0": 3.90},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {"status": "ok", "highlights": []},
        "intelligence": {
            "status": "ok",
            "points": ["资料观点：主队基本面更好。"],
            "llm_protection": {
                "should_protect": True,
                "protect_code": "0",
                "protect_strength": 0.45,
                "confidence": 0.45,
                "evidence": ["反面只是一句弱提示。"],
            },
        },
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["primary_pick"] == "3"
    assert decision["protect_picks"] == []
    assert decision["selection_codes"] == ["3"]


def test_recent_form_is_folded_into_shadow_intel_protection() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "test",
            "match_idx": 4,
            "home": "主队",
            "away": "客队",
            "league": "联赛",
            "handicap_line": 0,
            "line_gap": 0.0,
        },
        "model": {
            "probabilities": {"3": 0.48, "1": 0.25, "0": 0.27},
            "market_probabilities": {"3": 0.50, "1": 0.25, "0": 0.25},
        },
        "sp": {"3": 2.30, "1": 3.10, "0": 3.05},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {
            "status": "ok",
            "home_recent": "主队近10场 1胜1平8负，进失7/24，半场平2场",
            "away_recent": "客队近10场 7胜2平1负，进失23/8，半场平3场",
            "highlights": [],
        },
        "intelligence": {"status": "missing", "points": []},
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["primary_pick"] == "3"
    assert "1" in decision["protect_picks"]
    llm_layer = decision["sections"]["llm_intel_protection"]
    assert llm_layer["recent_form"]["code"] == "0"
    assert llm_layer["recent_form"]["mapped_code"] == "0"
    assert llm_layer["protect_code"] == "1"
    assert llm_layer["should_protect"] is True
    assert "reverse_intel_adjacent_protection" in decision["risk_tags"]
    assert "recent_form_intel_protection" in decision["risk_tags"]
    assert any("近期表现" in item for item in llm_layer["evidence"])


def test_unbeaten_home_context_is_not_parsed_as_away_negative() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "26072",
            "match_idx": 3,
            "home": "孔斯温厄尔",
            "away": "松达尔",
            "league": "挪甲",
            "handicap_line": -1,
            "line_gap": 0.0,
        },
        "model": {
            "probabilities": {"3": 0.31530847519009686, "1": 0.2820673865652757, "0": 0.4026241382446274},
            "market_probabilities": {"3": 0.5818857162010219, "1": 0.20810035864136778, "0": 0.21001392515761025},
        },
        "sp": {"3": 2.16, "1": 3.39, "0": 4.11},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {
            "status": "ok",
            "home_recent": "主队近10场 5胜3平2负，进失23/18，半场平1场",
            "away_recent": "客队近10场 4胜3平3负，进失24/21，半场平0场",
            "highlights": [],
        },
        "intelligence": {
            "status": "ok",
            "points": [
                "排名：孔斯温厄尔第3，松达尔第12",
                "资料观点：干斯云加今季联赛主场未尝败绩，本轮面对今季作客仅胜1场的桑恩达，干斯云加有力敲响主场胜鼓。",
                "观点索引：福利贴：康斯文格主场战斗力强大能否轻取松达尔？",
            ],
        },
    }

    raw = mod.classify_raw_strength(payload)
    decision = mod.structured_decision_for_payload(payload)

    assert raw["side"] == "home"
    assert raw["raw_scores"]["home"] > raw["raw_scores"]["away"]
    assert decision["sections"]["raw_strength"]["side"] == "home"
    assert decision["sections"]["handicap_fit"]["code"] == "1"
    assert decision["selection_codes"] == ["0", "3", "1"]


def test_recent_form_guard_does_not_expand_existing_double_to_full() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "26071",
            "match_idx": 10,
            "home": "利恩",
            "away": "奥桑内",
            "league": "挪甲",
            "handicap_line": 0,
            "line_gap": 0.5,
        },
        "model": {
            "probabilities": {
                "3": 0.5226181963451584,
                "1": 0.24241035130360533,
                "0": 0.23497145235123626,
            },
            "market_probabilities": {"3": 0.52, "1": 0.24, "0": 0.24},
        },
        "sp": {"3": 1.99, "1": 4.65, "0": 3.51},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {
            "status": "ok",
            "home_recent": "主队近10场 2胜3平5负，进失12/19，半场平4场",
            "away_recent": "客队近10场 6胜2平2负，进失21/12，半场平2场",
            "highlights": [],
        },
        "intelligence": {"status": "missing", "points": []},
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["primary_pick"] == "3"
    assert decision["selection_codes"] == ["3", "1"]
    assert decision["sections"]["llm_intel_protection"]["recent_form"]["mapped_code"] == "0"
    assert decision["sections"]["llm_intel_protection"]["protect_code"] == "1"
    assert "recent_form_intel_protection" in decision["risk_tags"]
    assert "reverse_intel_adjacent_protection" in decision["risk_tags"]


def test_low_q_marks_stop_without_clearing_pick_or_protection() -> None:
    mod = _load_module()
    payload = {
        "match": {
            "issue": "test",
            "match_idx": 5,
            "home": "主队",
            "away": "客队",
            "league": "联赛",
            "handicap_line": 0,
            "line_gap": 0.0,
        },
        "model": {
            "probabilities": {"3": 0.42, "1": 0.31, "0": 0.27},
            "market_probabilities": {"3": 0.44, "1": 0.30, "0": 0.26},
        },
        "sp": {"3": 2.10, "1": 2.80, "0": 3.10},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {"status": "ok", "highlights": []},
        "intelligence": {"status": "missing", "points": []},
    }

    decision = mod.structured_decision_for_payload(payload)

    assert decision["stop_flag"] == 1
    assert decision["primary_pick"] == "3"
    assert decision["selection_codes"] == ["3"]
    assert decision["selection_type"] == "single"
    assert "advisory_stop" in decision["risk_tags"]


def test_report_path_display_handles_default_internal_and_external_paths(tmp_path: Path) -> None:
    mod = _load_module()

    default_like = mod.DEFAULT_OUTPUT_ROOT / "26071_20260703" / "structured_shadow_26071.csv"
    internal_absolute = ROOT / "results/reviewer_probe_structured_shadow/26071_20260703/structured_shadow_26071.csv"
    external = tmp_path / "structured_shadow_26071.csv"

    assert mod.path_for_report(default_like) == "results/structured_decision_chain_shadow/26071_20260703/structured_shadow_26071.csv"
    assert mod.path_for_report(internal_absolute) == "results/reviewer_probe_structured_shadow/26071_20260703/structured_shadow_26071.csv"
    assert mod.path_for_report(external) == str(external.resolve())


def test_active_snapshot_completeness_guard_blocks_missing_rows() -> None:
    mod = _load_module()
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            """
            CREATE TABLE matches(issue TEXT, match_idx INTEGER);
            CREATE TABLE llm_decision_snapshots(issue TEXT, match_idx INTEGER, status TEXT);
            INSERT INTO matches VALUES('26072', 1);
            INSERT INTO matches VALUES('26072', 2);
            INSERT INTO llm_decision_snapshots VALUES('26072', 1, 'active');
            """
        )

        with pytest.raises(SystemExit) as exc:
            mod.assert_active_snapshots_complete(conn, "26072")

        assert "active_decision_snapshots incomplete" in str(exc.value)
        assert "missing=2" in str(exc.value)
        allowed = mod.assert_active_snapshots_complete(conn, "26072", allow_incomplete=True)
        assert allowed["missing_match_idx"] == [2]
    finally:
        conn.close()
