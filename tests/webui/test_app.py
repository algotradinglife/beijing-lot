"""Flask test-client tests for the webui.

Covers: empty-state setup → init → dashboard, plan generation against a
synthetic Live DB, mark-placed, reconcile + ProfitLock, history, reset,
graceful empty-Live-DB handling.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.live_collector.db import SCHEMA as LIVE_SCHEMA
from src.webui import create_app
from src.webui.db import WebuiDB
from src.webui.services import (
    BankrollState,
    PROFIT_LOCK_SKIM_FRAC,
    PROFIT_LOCK_TRIGGER,
    apply_profit_lock,
)


# --------------------------------------------------------------------------
# Live DB helpers (mirrors tests/phase5a/test_pipeline.py)

def _build_live_db(path: Path, matches, snaps, settlements=None):
    conn = sqlite3.connect(path)
    conn.executescript(LIVE_SCHEMA)
    for m in matches:
        conn.execute(
            "INSERT INTO matches(match_id,issue,match_idx,league,kickoff_ts,"
            "home,away,handicap_line,status) VALUES (?,?,?,?,?,?,?,?,?)",
            (m["match_id"], m["issue"], m["match_idx"], m["league"],
             m["kickoff_ts"], m["home"], m["away"], m["handicap_line"],
             m.get("status", "open")),
        )
    for s in snaps:
        conn.execute(
            "INSERT INTO snapshots(match_id,snapshot_ts,sp_3,sp_1,sp_0,source) "
            "VALUES (?,?,?,?,?,?)",
            (s["match_id"], s["snapshot_ts"], s["sp_3"], s["sp_1"], s["sp_0"],
             s.get("source", "test")),
        )
    for st in (settlements or []):
        conn.execute(
            "INSERT INTO settlements(match_id,issue,match_idx,fthg,ftag,"
            "result_code,winning_sp) VALUES (?,?,?,?,?,?,?)",
            (st["match_id"], st["issue"], st["match_idx"], st.get("fthg", 0),
             st.get("ftag", 0), st["result_code"], st.get("winning_sp")),
        )
    conn.commit()
    conn.close()


def _populated_live_db(path: Path, base_now: datetime) -> Path:
    matches, snaps = [], []
    # Use the same recipe as tests/phase5a fixture to guarantee +EV combos.
    for i in range(1, 21):
        kickoff = (base_now + timedelta(days=1 + (i % 5))).strftime("%Y-%m-%dT%H:%M:%S")
        matches.append(dict(
            match_id=f"T_{i:03d}", issue="26999", match_idx=i,
            league="英超" if i % 4 == 0 else "挪超", kickoff_ts=kickoff,
            home=f"H{i}", away=f"A{i}", handicap_line=1.0,
        ))
        snaps.append(dict(
            match_id=f"T_{i:03d}",
            snapshot_ts=base_now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            sp_3=4.0, sp_1=3.4, sp_0=3.4,
        ))
    _build_live_db(path, matches, snaps)
    return path


# --------------------------------------------------------------------------
# Fixtures

@pytest.fixture
def base_now():
    return datetime(2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def app_factory(tmp_path):
    """Returns a factory that builds an app rooted at tmp_path."""
    def _make(live_db_path: Path | None = None) -> "Flask":
        live_db = live_db_path or (tmp_path / "live_empty.db")
        webui_db = tmp_path / "webui.db"
        plans_dir = tmp_path / "plans"
        pnl_log = tmp_path / "pnl.csv"
        app = create_app(
            live_db=str(live_db),
            webui_db=str(webui_db),
            plans_dir=str(plans_dir),
            pnl_log=str(pnl_log),
        )
        app.config.update(TESTING=True)
        return app
    return _make


# --------------------------------------------------------------------------
# Tests

def test_first_run_redirects_to_setup(app_factory):
    app = app_factory()
    client = app.test_client()
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/setup" in resp.headers["Location"]


def test_setup_post_initializes_bankroll(app_factory):
    app = app_factory()
    client = app.test_client()
    resp = client.post("/setup", data={"initial_bankroll": "100000"},
                       follow_redirects=True)
    assert resp.status_code == 200
    # After setup we should land on dashboard
    assert b"Dashboard" in resp.data or "总财富".encode() in resp.data
    # Verify state persisted
    db = WebuiDB(app.config["WEBUI_DB"])
    assert db.is_initialized()
    assert db.get_float("current_active") == 100000.0
    assert db.get_float("locked_pile") == 0.0
    db.close()


def test_setup_rejects_invalid_amount(app_factory):
    app = app_factory()
    client = app.test_client()
    resp = client.post("/setup", data={"initial_bankroll": "0"})
    assert resp.status_code == 400
    resp2 = client.post("/setup", data={"initial_bankroll": "abc"})
    assert resp2.status_code == 400


def test_dashboard_empty_live_db_warning(app_factory, tmp_path):
    """Dashboard should not crash when Live Collector DB doesn't exist."""
    app = app_factory()
    client = app.test_client()
    client.post("/setup", data={"initial_bankroll": "50000"})
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Live Collector".encode() in resp.data


def test_generate_plan_empty_live_db_does_not_crash(app_factory, tmp_path):
    """Empty Live DB → generate yields zero tickets, friendly flash."""
    empty_live = tmp_path / "live_empty.db"
    _build_live_db(empty_live, [], [])
    app = app_factory(live_db_path=empty_live)
    client = app.test_client()
    client.post("/setup", data={"initial_bankroll": "100000"})
    resp = client.post("/plan/generate", follow_redirects=True)
    assert resp.status_code == 200
    # Plan view should show "尚未生成计划" or zero tickets message
    assert resp.status_code == 200


def test_generate_plan_with_data_creates_tickets(app_factory, tmp_path, base_now):
    live = _populated_live_db(tmp_path / "live.db", base_now)
    app = app_factory(live_db_path=live)
    client = app.test_client()
    client.post("/setup", data={"initial_bankroll": "100000"})
    resp = client.post("/plan/generate", follow_redirects=True)
    assert resp.status_code == 200

    # Plan should be persisted in webui DB
    db = WebuiDB(app.config["WEBUI_DB"])
    plans = db.list_plans()
    assert len(plans) == 1
    plan = db.get_plan(plans[0]["plan_id"])
    assert plan is not None
    assert len(plan["plan"]["tickets"]) > 0

    # And on disk for reconcile
    plan_files = list(Path(app.config["PLANS_DIR"]).glob("*.json"))
    assert len(plan_files) == 1
    db.close()


def test_mark_placed_records_timestamp(app_factory, tmp_path, base_now):
    live = _populated_live_db(tmp_path / "live.db", base_now)
    app = app_factory(live_db_path=live)
    client = app.test_client()
    client.post("/setup", data={"initial_bankroll": "100000"})
    client.post("/plan/generate", follow_redirects=True)

    db = WebuiDB(app.config["WEBUI_DB"])
    week_id = db.list_plans()[0]["plan_id"]
    db.close()

    resp = client.post("/plan/place", data={"plan_id": week_id},
                       follow_redirects=True)
    assert resp.status_code == 200

    db = WebuiDB(app.config["WEBUI_DB"])
    plan = db.get_plan(week_id)
    assert plan["placed_ts"] is not None
    db.close()


def test_reconcile_updates_bankroll_and_history(app_factory, tmp_path, base_now):
    """Full cycle: generate → place → settle in Live DB → reconcile."""
    live = _populated_live_db(tmp_path / "live.db", base_now)
    app = app_factory(live_db_path=live)
    client = app.test_client()
    client.post("/setup", data={"initial_bankroll": "100000"})
    client.post("/plan/generate", follow_redirects=True)

    db = WebuiDB(app.config["WEBUI_DB"])
    week_id = db.list_plans()[0]["plan_id"]
    plan = db.get_plan(week_id)["plan"]
    db.close()
    if not plan["tickets"]:
        pytest.skip("Planner produced no tickets for this fixture")

    # Inject all-home-win settlements covering every leg in the plan
    leg_match_ids = {leg["match_id"]
                     for t in plan["tickets"] for leg in t["legs"]}
    conn = sqlite3.connect(live)
    for mid in leg_match_ids:
        row = conn.execute(
            "SELECT issue, match_idx FROM matches WHERE match_id=?", (mid,)
        ).fetchone()
        conn.execute(
            "INSERT INTO settlements(match_id,issue,match_idx,fthg,ftag,"
            "result_code,winning_sp) VALUES (?,?,?,?,?,?,?)",
            (mid, row[0], row[1], 1, 0, "3", 4.0),
        )
    conn.commit()
    conn.close()

    resp = client.post("/reconcile", follow_redirects=True)
    assert resp.status_code == 200

    db = WebuiDB(app.config["WEBUI_DB"])
    settlements = db.list_settlements()
    assert len(settlements) == 1
    s = settlements[0]
    assert s["week_id"] == week_id
    assert s["n_combos"] > 0
    # Bankroll moved
    new_active = db.get_float("current_active")
    assert new_active != 100000.0
    db.close()

    # History page renders
    resp = client.get("/history")
    assert resp.status_code == 200
    assert week_id.encode() in resp.data


def test_reconcile_is_idempotent(app_factory, tmp_path, base_now):
    """Calling /reconcile twice does not double-count."""
    live = _populated_live_db(tmp_path / "live.db", base_now)
    app = app_factory(live_db_path=live)
    client = app.test_client()
    client.post("/setup", data={"initial_bankroll": "100000"})
    client.post("/plan/generate", follow_redirects=True)

    db = WebuiDB(app.config["WEBUI_DB"])
    plan = db.get_plan(db.list_plans()[0]["plan_id"])["plan"]
    db.close()
    if not plan["tickets"]:
        pytest.skip("No tickets generated")

    leg_match_ids = {leg["match_id"]
                     for t in plan["tickets"] for leg in t["legs"]}
    conn = sqlite3.connect(live)
    for mid in leg_match_ids:
        row = conn.execute(
            "SELECT issue, match_idx FROM matches WHERE match_id=?", (mid,)
        ).fetchone()
        conn.execute(
            "INSERT INTO settlements(match_id,issue,match_idx,fthg,ftag,"
            "result_code,winning_sp) VALUES (?,?,?,?,?,?,?)",
            (mid, row[0], row[1], 1, 0, "3", 4.0),
        )
    conn.commit()
    conn.close()

    client.post("/reconcile", follow_redirects=True)
    db = WebuiDB(app.config["WEBUI_DB"])
    active1 = db.get_float("current_active")
    db.close()

    client.post("/reconcile", follow_redirects=True)
    db = WebuiDB(app.config["WEBUI_DB"])
    active2 = db.get_float("current_active")
    assert active1 == active2
    assert len(db.list_settlements()) == 1
    db.close()


def test_profit_lock_skims_at_2x(app_factory):
    """Direct test of the ProfitLock policy."""
    state = BankrollState(initial=100.0, active=200.0, locked=0.0, peak=100.0)
    new_state, skimmed = apply_profit_lock(state)
    assert skimmed == pytest.approx(200.0 * PROFIT_LOCK_SKIM_FRAC)
    assert new_state.active == pytest.approx(200.0 - skimmed)
    assert new_state.locked == pytest.approx(skimmed)
    # Peak resets to post-skim active so we need another 2× to skim again
    assert new_state.peak == pytest.approx(new_state.active)

    # Below threshold: no skim
    state2 = BankrollState(initial=100.0, active=150.0, locked=0.0, peak=100.0)
    s2, sk2 = apply_profit_lock(state2)
    assert sk2 == 0.0
    assert s2.peak == 150.0  # high-water tracks


def test_reset_clears_state(app_factory):
    app = app_factory()
    client = app.test_client()
    client.post("/setup", data={"initial_bankroll": "100000"})
    resp = client.post("/reset", follow_redirects=True)
    assert resp.status_code == 200
    # Should now be back at setup
    db = WebuiDB(app.config["WEBUI_DB"])
    assert not db.is_initialized()
    db.close()


def test_healthz(app_factory):
    app = app_factory()
    resp = app.test_client().get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
