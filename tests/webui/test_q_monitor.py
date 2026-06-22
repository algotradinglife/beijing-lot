"""Live per-league / per-option q monitoring + auto-downweight selection.

q is the realized per-leg return multiple: RETURN_RATE × (sum of bet SP over
winning legs) / n. q < 1 means the bucket loses money per unit staked.
"""
from __future__ import annotations

import json

from src.combo_optimizer import RETURN_RATE
from src.webui.services import q_buckets, select_downweight_leagues


def _init(app):
    c = app.test_client()
    c.post("/setup", data={"initial_bankroll": "100000"}, follow_redirects=False)
    return c


def test_q_monitor_endpoint_returns_buckets(app_factory):
    client = _init(app_factory())
    resp = client.get("/api/q_monitor")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert set(("by_league", "by_option", "overall", "downweight_candidates")) <= set(data)


def test_apply_downweight_endpoint_ok_on_empty(app_factory):
    client = _init(app_factory())
    resp = client.post("/q_monitor/apply_downweight")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["ok"] is True
    assert data["added"] == []


def _leg(league, sel, sp, hit):
    return {"league": league, "selection": sel, "sp": sp, "hit": hit}


def test_q_buckets_empty():
    out = q_buckets([])
    assert out["by_league"] == {}
    assert out["by_option"] == {}


def test_q_buckets_single_league_math():
    # 2 legs in 英超: one hit at SP 4.0, one miss at SP 3.0.
    legs = [_leg("英超", "3", 4.0, True), _leg("英超", "3", 3.0, False)]
    lg = q_buckets(legs)["by_league"]["英超"]
    assert lg["n"] == 2
    assert lg["hits"] == 1
    assert lg["hit_rate"] == 0.5
    assert lg["avg_sp"] == 3.5
    # q = RETURN_RATE * (sum sp over hits)/n = 0.65 * 4.0/2 = 1.3
    assert lg["q"] == round(RETURN_RATE * 4.0 / 2, 4)


def test_q_buckets_splits_by_option():
    legs = [_leg("A", "3", 4.0, True), _leg("A", "0", 5.0, False)]
    by_opt = q_buckets(legs)["by_option"]
    assert set(by_opt) == {"3", "0"}
    assert by_opt["3"]["hit_rate"] == 1.0
    assert by_opt["0"]["hit_rate"] == 0.0


def test_select_downweight_only_sufficient_sample_and_low_q():
    by_league = {
        "K1联赛": {"n": 10, "q": 0.4, "hit_rate": 0.1, "avg_sp": 4.0, "hits": 1},
        "英超":   {"n": 12, "q": 1.2, "hit_rate": 0.3, "avg_sp": 4.0, "hits": 4},
        "芬超":   {"n": 3,  "q": 0.2, "hit_rate": 0.0, "avg_sp": 5.0, "hits": 0},
    }
    picked = select_downweight_leagues(by_league, min_n=8, q_threshold=0.7)
    names = {league for league, _reason in picked}
    assert names == {"K1联赛"}        # 芬超 too few samples; 英超 q ok


def test_select_downweight_reason_records_n_and_q():
    by_league = {"罗甲": {"n": 9, "q": 0.55, "hit_rate": 0.2, "avg_sp": 3.5, "hits": 2}}
    picked = select_downweight_leagues(by_league, min_n=8, q_threshold=0.7)
    assert len(picked) == 1
    _league, reason = picked[0]
    assert "0.55" in reason and "9" in reason
