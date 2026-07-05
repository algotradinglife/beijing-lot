from __future__ import annotations

import csv
import importlib.util
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/replay_rolling_segment_n_tickets.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("replay_rolling_segment_n_tickets", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
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
                PRIMARY KEY(issue, match_idx)
            )
            """
        )
        rows = [
            ("1001", 1, "2026-07-01 00:00", "A", "h1", "a1", "3", 2.0),
            ("1001", 2, "2026-07-01 02:00", "A", "h2", "a2", "0", 3.0),
            ("1001", 3, "2026-07-01 20:00", "A", "h3", "a3", "1", 4.0),
        ]
        conn.executemany("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


def _write_structured(path: Path) -> None:
    rows = [
        {
            "issue": "1001",
            "match_idx": "1",
            "match_id": "1001_001",
            "active_selection_codes": "3",
            "shadow_selection_codes": "3+1",
            "p_3": "0.80",
            "p_1": "0.10",
            "p_0": "0.10",
            "sp_3": "2.0",
            "sp_1": "3.5",
            "sp_0": "4.0",
            "actual_code": "3",
            "winning_sp": "2.0",
        },
        {
            "issue": "1001",
            "match_idx": "2",
            "match_id": "1001_002",
            "active_selection_codes": "0",
            "shadow_selection_codes": "0",
            "p_3": "0.20",
            "p_1": "0.20",
            "p_0": "0.60",
            "sp_3": "4.0",
            "sp_1": "3.2",
            "sp_0": "3.0",
            "actual_code": "0",
            "winning_sp": "3.0",
        },
        {
            "issue": "1001",
            "match_idx": "3",
            "match_id": "1001_003",
            "active_selection_codes": "3",
            "shadow_selection_codes": "1",
            "p_3": "0.40",
            "p_1": "0.35",
            "p_0": "0.25",
            "sp_3": "2.5",
            "sp_1": "4.0",
            "sp_0": "3.5",
            "actual_code": "1",
            "winning_sp": "4.0",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_build_segments_extends_when_initial_window_is_short(tmp_path: Path) -> None:
    mod = _load_module()
    db = tmp_path / "test.sqlite"
    structured = tmp_path / "structured.csv"
    _write_db(db)
    _write_structured(structured)

    legs = mod.load_legs(structured, db, issue="1001")
    segments = mod.build_segments(legs, base_window_hours=12, extend_hours=[24], min_matches=3, max_matches=24)

    assert len(segments) == 1
    assert segments[0].window_hours == 24
    assert [leg.match_idx for leg in segments[0].legs] == [1, 2, 3]


def test_replay_segment_uses_polynomial_cost_and_payout(tmp_path: Path) -> None:
    mod = _load_module()
    db = tmp_path / "test.sqlite"
    structured = tmp_path / "structured.csv"
    _write_db(db)
    _write_structured(structured)

    legs = mod.load_legs(structured, db, issue="1001")
    segment = mod.build_segments(legs, base_window_hours=24, extend_hours=[24], min_matches=3, max_matches=24)[0]
    active = mod.replay_segment_arm(
        segment,
        "active",
        budget_ticket_units=384,
        stake_yuan_per_ticket=2,
        budget_coverage="ok",
        max_expanded_cost_multiple=10,
        min_n=2,
        max_n=8,
        selection_mode="full_basket",
        sample_seed=7,
    )
    shadow = mod.replay_segment_arm(
        segment,
        "shadow",
        budget_ticket_units=384,
        stake_yuan_per_ticket=2,
        budget_coverage="ok",
        max_expanded_cost_multiple=10,
        min_n=2,
        max_n=8,
        selection_mode="full_basket",
        sample_seed=7,
    )

    assert active["recommended_n"] == 2
    assert active["expanded_cost"] == 3
    assert active["winning_tickets"] == 1
    assert active["total_payout"] == 6
    assert active["profit"] == 3
    assert shadow["expanded_cost"] == 5
    assert shadow["winning_tickets"] == 3
    assert shadow["total_payout"] == 26
    assert shadow["profit"] == 21


def test_sample_budget_respects_cap_and_seed(tmp_path: Path) -> None:
    mod = _load_module()
    db = tmp_path / "test.sqlite"
    structured = tmp_path / "structured.csv"
    _write_db(db)
    _write_structured(structured)

    legs = mod.load_legs(structured, db, issue="1001")
    segment = mod.build_segments(legs, base_window_hours=24, extend_hours=[24], min_matches=3, max_matches=24)[0]
    first = mod.replay_segment_arm(
        segment,
        "shadow",
        budget_ticket_units=2,
        stake_yuan_per_ticket=2,
        budget_coverage="ok",
        max_expanded_cost_multiple=10,
        min_n=2,
        max_n=8,
        selection_mode="sample_budget",
        sample_seed=11,
    )
    second = mod.replay_segment_arm(
        segment,
        "shadow",
        budget_ticket_units=2,
        stake_yuan_per_ticket=2,
        budget_coverage="ok",
        max_expanded_cost_multiple=10,
        min_n=2,
        max_n=8,
        selection_mode="sample_budget",
        sample_seed=11,
    )

    assert first["expanded_cost"] == 5
    assert first["selected_tickets"] <= 2
    assert first["selected_cost_yuan"] <= 4
    assert first["total_payout"] == second["total_payout"]


def test_expanded_cost_guardrail_drops_n(tmp_path: Path) -> None:
    mod = _load_module()
    db = tmp_path / "test.sqlite"
    structured = tmp_path / "structured.csv"
    _write_db(db)
    _write_structured(structured)

    base_legs = mod.load_legs(structured, db, issue="1001")
    wide_legs = []
    for idx in range(6):
        leg = base_legs[idx % len(base_legs)]
        codes = leg.shadow_codes
        probabilities = {code: 0.0 for code in mod.OUTCOME_CODES}
        for code in codes:
            probabilities[code] = 0.8 / len(codes)
        wide_legs.append(
            replace(
                leg,
                match_idx=idx + 1,
                probabilities=probabilities,
                sp={code: 2.0 for code in mod.OUTCOME_CODES},
            )
        )
    segment = mod.Segment(
        segment_idx=1,
        start=base_legs[0].kickoff,
        end=base_legs[-1].kickoff,
        window_hours=24,
        legs=tuple(wide_legs),
    )
    guarded = mod.replay_segment_arm(
        segment,
        "shadow",
        budget_ticket_units=10,
        stake_yuan_per_ticket=2,
        budget_coverage="ok",
        max_expanded_cost_multiple=1,
        min_n=1,
        max_n=8,
        selection_mode="sample_budget",
        sample_seed=11,
    )

    assert guarded["initial_recommended_n"] == 3
    assert guarded["recommended_n"] == 1
    assert guarded["expanded_cost_guardrail_drops"] == 2
    assert guarded["expanded_cost"] <= guarded["expanded_cost_guardrail_target"]
