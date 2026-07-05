from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate_structured_decision_chain_v4_2.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("evaluate_structured_decision_chain_v4_2", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _base_row(**overrides):
    row = {
        "issue": "test",
        "match_idx": "1",
        "league": "K1联赛",
        "home": "主队",
        "away": "客队",
        "handicap_line": "0.0",
        "shadow_selection_codes": "",
        "actual_code": "",
        "p_3": "0.42",
        "p_1": "0.28",
        "p_0": "0.30",
        "sp_3": "2.20",
        "sp_1": "3.40",
        "sp_0": "3.10",
        "q_3": "0.924",
        "q_1": "0.952",
        "q_0": "0.930",
        "prob_top": "3",
        "q_top": "1",
        "raw_strength_side": "",
        "form_recent_code": "",
        "form_recent_confidence": "",
        "form_recent_mapped_code": "",
    }
    row.update(overrides)
    return row


def _context(**overrides):
    context = {
        "match": {
            "issue": "test",
            "match_idx": 1,
            "league": "K1联赛",
            "home": "主队",
            "away": "客队",
            "handicap_line": 0.0,
            "disabled": "no",
            "home_rank": 5,
            "away_rank": 8,
            "avg_odds_home": 2.2,
            "avg_odds_draw": 3.3,
            "avg_odds_away": 3.1,
            "sp_home": 2.2,
            "sp_draw": 3.4,
            "sp_away": 3.1,
        },
        "digest": {"headline": "K1联赛 · 联赛 第16轮", "summary": ""},
        "detail": {
            "kickoff_context": "韩K联 开赛时间：2026-07-04 18:30",
            "home_recent_summary": "主队近10场 4胜2平4负，进失12/12，半场平3场",
            "away_recent_summary": "客队近10场 4胜2平4负，进失12/12，半场平3场",
            "h2h_summary": "",
            "league_summary": "",
            "market_summary": "",
            "odds_consensus_json": "",
        },
        "live_sp": {"sp_home": 2.2, "sp_draw": 3.4, "sp_away": 3.1},
        "snapshot": {"generated_at": "2026-07-03 14:00:00"},
        "input_payload": {"match": {"kickoff_ts": "2026-07-04 18:30:00"}},
        "source_timestamps": {},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(context.get(key), dict):
            context[key].update(value)
        else:
            context[key] = value
    return context


def _semantic(
    *,
    raw_side: str = "unknown",
    raw_confidence: float = 0.0,
    draw_signal: str = "none",
    draw_confidence: float = 0.0,
    mismatch: bool = False,
) -> dict:
    return {
        "schema": "semantic_llm_v4_contract",
        "source": "test_semantic",
        "status": "ok",
        "alias_resolution": {
            "home_aliases": ["主队"],
            "away_aliases": ["客队"],
            "known_variant_hits": [],
            "unresolved_names": [],
            "alias_resolution_required": False,
        },
        "raw_strength": {"side": raw_side, "confidence": raw_confidence, "evidence": []},
        "draw_semantics": {"signal": draw_signal, "confidence": draw_confidence, "evidence": []},
        "cover_risk_semantics": {
            "side": "unknown",
            "risk_type": "unknown",
            "codes": [],
            "confidence": 0.0,
            "evidence": [],
        },
        "competition_context": {
            "league": "测试",
            "headline": "测试",
            "detail_context": "",
            "tags": [],
            "mismatch": mismatch,
            "mismatch_sources": ["digest:错配"] if mismatch else [],
        },
        "contradiction_flags": ["competition_context_mismatch"] if mismatch else [],
        "text_digest": "",
    }


def test_v4_2_explicit_draw_keeps_form_side_and_drops_stale_branch() -> None:
    mod = _load_module()
    row = _base_row(
        match_idx="20",
        home="全北现代",
        away="江原FC",
        p_3="0.454432705",
        p_1="0.284765353",
        p_0="0.260801942",
        sp_3="8.22",
        sp_1="2.19",
        sp_0="2.36",
        q_3="3.735436832",
        q_1="0.623636124",
        q_0="0.615492583",
        prob_top="3",
        q_top="3",
        form_recent_code="0",
        form_recent_confidence="0.49",
        form_recent_mapped_code="0",
    )
    context = _context(
        match={"home": "全北现代", "away": "江原FC", "home_rank": 2, "away_rank": 4, "avg_odds_home": 2.63, "avg_odds_away": 2.72},
        detail={
            "home_recent_summary": "主队近10场 5胜3平2负，进失15/7，半场平5场",
            "away_recent_summary": "客队近10场 6胜3平1负，进失16/4，半场平3场",
            "h2h_summary": "近10次交锋主队视角 3胜3平4负，进失14/13",
        },
        live_sp={"sp_home": 2.71, "sp_draw": 2.19, "sp_away": 2.36},
    )

    decision = mod.compile_decision(
        row,
        context,
        semantic_override=_semantic(draw_signal="explicit_draw", draw_confidence=0.82),
    )

    assert decision["recommended_codes"] == ["1", "0"]
    assert "3" not in decision["recommended_codes"]
    assert "replace_stale_branch_with_team_strength" in decision["sections"]["protection_competition"]["merge_flags"]


def test_v4_2_suppresses_unbacked_late_refresh_draw_and_adds_high_q_attraction() -> None:
    mod = _load_module()
    row = _base_row(
        match_idx="40",
        home="朗福德城",
        away="都柏林大学",
        p_3="0.285926063",
        p_1="0.257618042",
        p_0="0.456455895",
        sp_3="16.91",
        sp_1="7.80",
        sp_0="1.23",
        q_3="4.835009719",
        q_1="2.009420728",
        q_0="0.561440751",
        prob_top="0",
        q_top="3",
        form_recent_code="0",
        form_recent_confidence="0.455",
        form_recent_mapped_code="0",
    )
    context = _context(
        match={"home_rank": 7, "away_rank": 2, "avg_odds_home": 3.33, "avg_odds_away": 1.97},
        detail={
            "home_recent_summary": "主队近10场 4胜2平4负，进失14/17，半场平4场",
            "away_recent_summary": "客队近10场 6胜0平4负，进失20/11，半场平0场",
            "h2h_summary": "近10次交锋主队视角 0胜3平7负，进失6/15",
        },
        live_sp={"sp_home": 2.85, "sp_draw": 7.80, "sp_away": 1.23},
    )

    decision = mod.compile_decision(row, context, semantic_override=_semantic(raw_side="away", raw_confidence=0.60))

    assert decision["recommended_codes"] == ["0", "3"]
    assert "1" not in decision["recommended_codes"]
    assert {"suppress_unbacked_late_refresh_draw", "high_q_attraction"}.issubset(
        set(decision["sections"]["protection_competition"]["merge_flags"])
    )


def test_v4_2_market_context_mismatch_promotes_full_cover_or_skip() -> None:
    mod = _load_module()
    row = _base_row(
        match_idx="33",
        league="芬超",
        home="塞伊奈约基",
        away="TPS图尔库",
        handicap_line="-1.0",
        p_3="0.273229277",
        p_1="0.304801797",
        p_0="0.421968927",
        sp_3="1.37",
        sp_1="9.30",
        sp_0="6.01",
        q_3="0.374324109",
        q_1="2.834656708",
        q_0="2.536033250",
        prob_top="0",
        q_top="1",
        form_recent_code="0",
        form_recent_confidence="0.402",
        form_recent_mapped_code="0",
    )
    context = _context(
        match={"league": "芬超", "home_rank": 10, "away_rank": 6, "avg_odds_home": 1.76, "avg_odds_away": 4.07, "handicap_line": -1.0},
        digest={"headline": "俄青联 · 联赛 第13轮", "summary": "摘要错配，不能直接信任。"},
        detail={
            "kickoff_context": "芬超 开赛时间：2026-07-04 22:00",
            "home_recent_summary": "主队近10场 3胜2平5负，进失19/16，半场平4场",
            "away_recent_summary": "客队近10场 4胜1平5负，进失10/9，半场平5场",
            "h2h_summary": "近10次交锋主队视角 6胜1平3负，进失15/7",
        },
        live_sp={"sp_home": 8.95, "sp_draw": 9.30, "sp_away": 1.24},
    )

    decision = mod.compile_decision(row, context, semantic_override=_semantic(mismatch=True))

    assert set(decision["recommended_codes"]) == {"3", "1", "0"}
    assert decision["sections"]["protection_competition"]["full_cover_candidate"] is True
    assert "layer_conflict_requires_full_cover_or_skip" in decision["sections"]["protection_competition"]["merge_flags"]


def test_v4_2_does_not_add_unbacked_high_q_draw_against_directional_strength() -> None:
    mod = _load_module()
    row = _base_row(
        match_idx="32",
        league="芬超",
        home="查路",
        away="伊尔维斯",
        p_3="0.301639076",
        p_1="0.270137893",
        p_0="0.428223031",
        sp_3="7.46",
        sp_1="8.77",
        sp_0="1.32",
        q_3="2.250227506",
        q_1="2.369109326",
        q_0="0.565254400",
        prob_top="0",
        q_top="1",
        form_recent_code="0",
        form_recent_confidence="0.70",
        form_recent_mapped_code="0",
    )
    context = _context(
        match={"home_rank": 11, "away_rank": 9, "avg_odds_home": 3.71, "avg_odds_away": 1.82},
        detail={
            "home_recent_summary": "主队近10场 1胜1平8负，进失12/31，半场平1场",
            "away_recent_summary": "客队近10场 5胜1平4负，进失21/18，半场平2场",
            "h2h_summary": "近9次交锋主队视角 2胜1平6负，进失11/20",
        },
        live_sp={"sp_home": 4.72, "sp_draw": 4.45, "sp_away": 1.77},
    )

    decision = mod.compile_decision(row, context, semantic_override=_semantic(raw_side="away", raw_confidence=0.88))

    assert decision["recommended_codes"] == ["0", "3"]
    assert "1" not in decision["recommended_codes"]
    assert "skip_unbacked_high_q_draw" in decision["sections"]["protection_competition"]["merge_flags"]
