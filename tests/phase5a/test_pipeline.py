"""Phase 5a end-to-end tests with a synthetic Live Collector DB."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.live_collector.db import SCHEMA  # reuse exact schema
from src.phase5a import (
    NicheConfig,
    build_weekly_plan,
    load_open_matches,
    qualify_candidates,
    reconcile_plan,
)
from src.phase5a.planner import format_plan_markdown, save_plan_json


# --------------------------------------------------------------------------
# Fixtures

def _build_db(path: Path, matches: list[dict], snaps: list[dict],
              settlements: list[dict] | None = None) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
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


@pytest.fixture
def base_now():
    return datetime(2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def populated_db(tmp_path, base_now):
    """20 matches, all in window, with SPs landing in surviving niches."""
    db = tmp_path / "live.db"
    matches: list[dict] = []
    snaps: list[dict] = []
    # 12 matches with home SP in 3.5-4.5 (qualifies home_sp_3.5-4.5_h_unknown)
    for i in range(1, 21):
        kickoff = (base_now + timedelta(days=1 + (i % 5))).strftime("%Y-%m-%dT%H:%M:%S")
        # All matches use handicap=1.0 → h1 bucket so the strongest niche
        # (away_sp_3.0-3.5_h1, p_hat=0.342) qualifies and produces +EV combos
        # at N=4: (0.342*3.4)^4 * 0.65 ≈ 1.18 ⇒ combo edge ≈ 0.18.
        hcap = 1.0
        league = "英超" if i % 4 == 0 else "挪超"  # Top5EU vs LowerEU mix
        sp_3 = 4.0   # in [3.5, 4.5)
        sp_1 = 3.4
        sp_0 = 3.4   # in [3.0, 3.5) → qualifies away_sp_3.0-3.5_h1
        matches.append(dict(
            match_id=f"T_{i:03d}", issue="26999", match_idx=i,
            league=league, kickoff_ts=kickoff,
            home=f"H{i}", away=f"A{i}",
            handicap_line=hcap,
        ))
        snaps.append(dict(
            match_id=f"T_{i:03d}",
            snapshot_ts=base_now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            sp_3=sp_3, sp_1=sp_1, sp_0=sp_0,
        ))
    _build_db(db, matches, snaps)
    return db


# --------------------------------------------------------------------------
# Tests

def test_load_open_matches_returns_window_only(tmp_path, base_now):
    db = tmp_path / "live.db"
    in_win = (base_now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
    out_win = (base_now + timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%S")
    matches = [
        dict(match_id="A", issue="x", match_idx=1, league="英超",
             kickoff_ts=in_win, home="h", away="a", handicap_line=0.0),
        dict(match_id="B", issue="x", match_idx=2, league="英超",
             kickoff_ts=out_win, home="h", away="a", handicap_line=0.0),
    ]
    snaps = [
        dict(match_id="A", snapshot_ts="2026-05-02T00:00:00Z",
             sp_3=4.0, sp_1=3.4, sp_0=3.7),
    ]
    _build_db(db, matches, snaps)
    out = load_open_matches(db, window_days=7, now=base_now)
    assert len(out) == 1
    assert out[0].match_id == "A"
    assert out[0].sp_3 == 4.0


def test_load_open_matches_handles_missing_db(tmp_path, base_now):
    out = load_open_matches(tmp_path / "does_not_exist.db", now=base_now)
    assert out == []


def test_qualify_candidates_emits_legs(populated_db, base_now):
    snaps = load_open_matches(populated_db, now=base_now)
    cfg = NicheConfig.load()
    quals = qualify_candidates(snaps, cfg)
    assert len(quals) > 0
    # Every qualified leg should have an in-bucket SP and known rule.
    for q in quals:
        assert 3.0 <= q.candidate.sp < 4.5
        assert q.rule_name


def test_build_weekly_plan_produces_markdown(populated_db, base_now):
    snaps = load_open_matches(populated_db, now=base_now)
    cfg = NicheConfig.load()
    plan = build_weekly_plan(
        snaps, bankroll=100_000.0, niche_config=cfg, now=base_now,
        n_legs=4, kelly_fraction=0.0625,
    )
    assert plan.n_open_matches == 20
    assert plan.n_qualified_legs > 0
    md = format_plan_markdown(plan)
    assert "Phase 5a Weekly Bet Plan" in md
    # No tax-cliff breaches
    for t in plan.tickets:
        assert t.is_tax_free
        assert t.stake_per_ticket >= 2 and t.stake_per_ticket % 2 == 0


def test_build_plan_empty_db_graceful(tmp_path, base_now):
    """Empty Live DB should return zero-ticket plan, not raise."""
    db = tmp_path / "live.db"
    _build_db(db, [], [])
    snaps = load_open_matches(db, now=base_now)
    cfg = NicheConfig.load()
    plan = build_weekly_plan(snaps, bankroll=100_000.0,
                             niche_config=cfg, now=base_now)
    assert plan.tickets == []
    md = format_plan_markdown(plan)
    assert "No tickets generated" in md


def test_reconcile_plan_against_settlements(tmp_path, populated_db, base_now):
    snaps = load_open_matches(populated_db, now=base_now)
    cfg = NicheConfig.load()
    plan = build_weekly_plan(
        snaps, bankroll=100_000.0, niche_config=cfg, now=base_now,
        n_legs=4, kelly_fraction=0.0625,
    )
    if not plan.tickets:
        pytest.skip("No tickets generated for reconcile test")

    # Add settlements: every match resolves to home win ('3').
    conn = sqlite3.connect(populated_db)
    for q_id in {leg.match_id for t in plan.tickets for leg in t.combo.legs}:
        # Look up issue/match_idx
        row = conn.execute(
            "SELECT issue, match_idx FROM matches WHERE match_id=?", (q_id,)
        ).fetchone()
        conn.execute(
            "INSERT INTO settlements(match_id,issue,match_idx,fthg,ftag,"
            "result_code,winning_sp) VALUES (?,?,?,?,?,?,?)",
            (q_id, row[0], row[1], 1, 0, "3", 4.0),
        )
    conn.commit()
    conn.close()

    plan_path = save_plan_json(plan, tmp_path / "plans")
    pnl_log = tmp_path / "pnl.csv"
    res = reconcile_plan(plan_path, populated_db, pnl_log, now=base_now)
    assert res.n_tickets == len(plan.tickets)
    assert res.pending == 0
    # Tickets whose first leg picks "3" (home) should hit
    # under our all-home settlement.
    won = sum(1 for o in res.ticket_outcomes if o.status == "won")
    lost = sum(1 for o in res.ticket_outcomes if o.status == "lost")
    assert won + lost == res.n_tickets
    assert pnl_log.exists()
    # PnL log should have one row.
    text = pnl_log.read_text().strip().splitlines()
    assert len(text) == 2  # header + one row


def test_pnl_log_cumulative_increases(tmp_path):
    from src.phase5a.pnl_log import append_pnl_row, read_pnl_log
    log = tmp_path / "pnl.csv"
    append_pnl_row(log, dict(plan_id="A", reconciled_at="t1", n_tickets=1,
                             n_settled_legs=4, n_winning_tickets=0,
                             total_stake=100, gross_payout=0, net_pnl=-100))
    append_pnl_row(log, dict(plan_id="B", reconciled_at="t2", n_tickets=1,
                             n_settled_legs=4, n_winning_tickets=1,
                             total_stake=100, gross_payout=300, net_pnl=200))
    rows = read_pnl_log(log)
    assert [float(r["cumulative_pnl"]) for r in rows] == [-100.0, 100.0]
