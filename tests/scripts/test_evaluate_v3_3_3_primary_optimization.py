from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate_v3_3_3_primary_optimization.py"


def load_module():
    spec = importlib.util.spec_from_file_location("evaluate_v3_3_3_primary_optimization", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def payload(*, handicap: float = 0.0, probabilities: dict[str, float] | None = None):
    probs = probabilities or {"3": 0.44, "1": 0.31, "0": 0.25}
    return {
        "match": {"issue": "test", "match_idx": 1, "home": "H", "away": "A", "league": "L", "handicap_line": handicap},
        "model": {"probabilities": probs, "market_probabilities": probs},
        "sp": {"3": 2.2, "1": 3.2, "0": 4.0},
        "market": {"odds_consensus": {"drift": {}}},
        "analysis": {"status": "ok", "highlights": []},
        "intelligence": {"status": "missing", "points": []},
    }


def replay_row(module, raw_payload):
    return module.ReplayRow(
        issue="26072",
        match_idx=1,
        match_id="m1",
        league="L",
        home="H",
        away="A",
        handicap_line=float(raw_payload["match"]["handicap_line"]),
        kickoff_at="2026-07-01 12:00:00",
        generated_at="2026-07-01 10:00:00",
        result_code="3",
        winning_sp=2.2,
        payload=raw_payload,
    )


def test_every_candidate_freezes_selection_set_and_depth() -> None:
    module = load_module()
    records = module.evaluate([replay_row(module, payload())], {"26072"})

    assert records
    assert {row["selection_set"] for row in records} == {records[0]["selection_set"]}
    assert {row["depth"] for row in records} == {records[0]["depth"]}
    assert {row["coverage_hit"] for row in records} == {records[0]["coverage_hit"]}
    assert {row["coverage_profit"] for row in records} == {records[0]["coverage_profit"]}


def test_draw_aware_can_only_promote_draw_already_in_frozen_coverage() -> None:
    module = load_module()
    raw_payload = payload(handicap=-1.0, probabilities={"3": 0.38, "1": 0.36, "0": 0.26})
    row = replay_row(module, raw_payload)
    decision = {"primary_pick": "3"}

    with_draw = module.candidate_primaries(row, decision, ["3", "1"])
    without_draw = module.candidate_primaries(row, decision, ["3", "0"])

    assert with_draw["draw_aware_gap_0.02"] == "1"
    assert without_draw["draw_aware_gap_0.06"] != "1"


def test_loader_excludes_post_kickoff_and_unsettled_snapshots(tmp_path: Path) -> None:
    module = load_module()
    db = tmp_path / "sample.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE llm_decision_snapshots (
              snapshot_id TEXT, issue TEXT, match_idx INTEGER, match_id TEXT,
              status TEXT, generated_at TEXT, input_payload_json TEXT
            );
            CREATE TABLE matches (
              issue TEXT, match_idx INTEGER, league TEXT, home TEXT, away TEXT,
              handicap_line REAL, end_time TEXT, result_code TEXT, winning_sp REAL
            );
            """
        )
        raw_payload = json.dumps(payload())
        snapshots = [
            ("s1", "26072", 1, "m1", "active", "2026-07-01 10:00:00", raw_payload),
            ("s2", "26072", 2, "m2", "active", "2026-07-01 13:00:00", raw_payload),
            ("s3", "26072", 3, "m3", "active", "2026-07-01 10:00:00", raw_payload),
        ]
        matches = [
            ("26072", 1, "L", "H", "A", 0.0, "2026-07-01 12:00:00", "3", 2.2),
            ("26072", 2, "L", "H", "A", 0.0, "2026-07-01 12:00:00", "3", 2.2),
            ("26072", 3, "L", "H", "A", 0.0, "2026-07-01 12:00:00", None, None),
        ]
        conn.executemany("INSERT INTO llm_decision_snapshots VALUES (?,?,?,?,?,?,?)", snapshots)
        conn.executemany("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?)", matches)
        rows = module.load_rows(conn, ["26072"])

    assert [(row.issue, row.match_idx) for row in rows] == [("26072", 1)]


def test_candidate_tie_prefers_simple_probability_first_rule() -> None:
    module = load_module()
    records = module.evaluate([replay_row(module, payload())], {"26072"})

    assert module.choose_candidate(records) == "probability_first"
