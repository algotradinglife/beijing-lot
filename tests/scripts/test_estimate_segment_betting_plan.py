from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/estimate_segment_betting_plan.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("estimate_segment_betting_plan", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _leg(mod, idx: int, codes: tuple[str, ...], actual: str, winning_sp: float):
    return mod.rolling.LegRow(
        issue="1001",
        match_idx=idx,
        match_id=f"1001_{idx:03d}",
        kickoff=datetime(2026, 7, 1, idx),
        league="T",
        home=f"H{idx}",
        away=f"A{idx}",
        active_codes=(),
        shadow_codes=codes,
        probabilities={"3": 0.45, "1": 0.30, "0": 0.25},
        sp={"3": 2.0, "1": 3.5, "0": 4.0},
        actual_code=actual,
        winning_sp=winning_sp,
    )


def test_bundle_candidate_uses_small_combo_cost_and_single_winning_ticket() -> None:
    mod = _load_module()
    legs = [
        _leg(mod, 1, ("3", "1"), "3", 2.0),
        _leg(mod, 2, ("0",), "0", 4.0),
        _leg(mod, 3, ("1",), "1", 3.5),
    ]
    metrics = [mod.leg_metrics(leg, "shadow") for leg in legs]
    assert all(metrics)

    candidate = mod.make_bundle_candidate(
        metrics=metrics,
        indices=(0, 1, 2),
        segment_idx=1,
        bundle_idx=1,
        arm="shadow",
        n_value=3,
    )

    assert candidate.cost_units == 2
    assert candidate.realized_hit is True
    assert candidate.payout_units == 28.0
    assert candidate.profit_units == 26.0


def test_settle_segment_selects_bundles_under_budget() -> None:
    mod = _load_module()
    legs = [
        _leg(mod, 1, ("3", "1"), "3", 2.0),
        _leg(mod, 2, ("0",), "0", 4.0),
        _leg(mod, 3, ("1",), "1", 3.5),
        _leg(mod, 4, ("3",), "0", 4.0),
        _leg(mod, 5, ("3",), "3", 2.0),
        _leg(mod, 6, ("3",), "3", 2.0),
    ]
    segment = mod.rolling.Segment(
        segment_idx=1,
        start=legs[0].kickoff,
        end=legs[-1].kickoff,
        window_hours=12,
        legs=tuple(legs),
    )

    row, selected = mod.settle_segment(
        segment,
        arm="shadow",
        segment_budget_yuan=4,
        stake_yuan_per_ticket=2,
        sample_attempts=100,
        sample_seed=7,
        min_n=3,
        max_n=8,
        max_overlap=None,
        positive_ev_only=False,
    )

    assert row["recommended_n"] == 3
    assert row["selected_cost_yuan"] <= 4
    assert len(selected) <= 1
    if selected:
        assert selected[0].cost_units <= 2


def test_run_writes_outputs(tmp_path: Path) -> None:
    mod = _load_module()
    db = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db)
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
        for idx in range(1, 7):
            conn.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("1001", idx, f"2026-07-01 0{idx}:00", "T", f"H{idx}", f"A{idx}", "3", 2.0),
            )
        conn.commit()
    finally:
        conn.close()
    structured = tmp_path / "structured.csv"
    rows = []
    for idx in range(1, 7):
        rows.append(
            {
                "issue": "1001",
                "match_idx": str(idx),
                "match_id": f"1001_{idx:03d}",
                "active_selection_codes": "3",
                "shadow_selection_codes": "3",
                "p_3": "0.70",
                "p_1": "0.20",
                "p_0": "0.10",
                "sp_3": "2.0",
                "sp_1": "3.5",
                "sp_0": "4.0",
            }
        )
    with structured.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    args = mod.parse_args([
        "--issue",
        "1001",
        "--structured-csv",
        str(structured),
        "--db",
        str(db),
        "--output-dir",
        str(tmp_path / "out"),
        "--report-dir",
        str(tmp_path / "reports"),
        "--segment-budget-yuan",
        "20",
        "--sample-attempts",
        "200",
    ])
    payload = mod.run(args)

    assert Path(payload["segment_csv"]).exists()
    assert Path(payload["bundle_csv"]).exists()
    assert Path(payload["seed_summary_csv"]).exists()
    assert Path(payload["segment_seed_summary_csv"]).exists()
    assert Path(payload["summary_json"]).exists()
    assert Path(payload["report_path"]).exists()

    summary_payload = json.loads(Path(payload["summary_json"]).read_text(encoding="utf-8"))
    assert summary_payload["strategy_family"] == "segment_betting_plan"
    assert summary_payload["betting_strategy_version"] == "segment_betting_v0.1.0000"
    assert summary_payload["artifact_schema_version"] == "segment_betting_artifact_v1"
    assert summary_payload["seed_aggregate"]["summary_mode"] == "single_seed"
    assert any(item["key"] == "segment_budget_yuan" for item in summary_payload["parameter_schema"])
    assert "segment_betting_v0.1.0000" in payload["summary_json"]


def test_run_multi_seed_writes_stability_outputs(tmp_path: Path) -> None:
    mod = _load_module()
    db = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db)
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
        for idx in range(1, 9):
            actual = "3" if idx != 4 else "0"
            winning_sp = 2.0 if actual == "3" else 4.0
            conn.execute(
                "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("1001", idx, f"2026-07-01 0{idx}:00", "T", f"H{idx}", f"A{idx}", actual, winning_sp),
            )
        conn.commit()
    finally:
        conn.close()
    structured = tmp_path / "structured.csv"
    rows = []
    for idx in range(1, 9):
        rows.append(
            {
                "issue": "1001",
                "match_idx": str(idx),
                "match_id": f"1001_{idx:03d}",
                "active_selection_codes": "3",
                "shadow_selection_codes": "3,1" if idx % 2 else "3",
                "p_3": "0.70",
                "p_1": "0.20",
                "p_0": "0.10",
                "sp_3": "2.0",
                "sp_1": "3.5",
                "sp_0": "4.0",
            }
        )
    with structured.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    args = mod.parse_args([
        "--issue",
        "1001",
        "--structured-csv",
        str(structured),
        "--betting-strategy-version",
        "segment_betting_v0.1.0001",
        "--db",
        str(db),
        "--output-dir",
        str(tmp_path / "out"),
        "--report-dir",
        str(tmp_path / "reports"),
        "--segment-budget-yuan",
        "80",
        "--sample-attempts",
        "300",
        "--sample-seed",
        "10",
        "--seed-count",
        "3",
    ])
    payload = mod.run(args)

    assert payload["betting_strategy_version"] == "segment_betting_v0.1.0001"
    assert "segment_betting_v0.1.0001" in payload["summary_json"]
    assert payload["seed_aggregate"]["seed_count"] == 3
    assert payload["seed_aggregate"]["seeds"] == [10, 11, 12]
    assert payload["seed_aggregate"]["summary_mode"] == "multi_seed_mean"
    assert "profit_yuan" in payload["seed_aggregate"]["metrics"]

    with Path(payload["seed_summary_csv"]).open(encoding="utf-8", newline="") as f:
        seed_rows = list(csv.DictReader(f))
    assert [row["sample_seed"] for row in seed_rows] == ["10", "11", "12"]

    with Path(payload["segment_seed_summary_csv"]).open(encoding="utf-8", newline="") as f:
        segment_seed_rows = list(csv.DictReader(f))
    assert segment_seed_rows
    assert "recommended_n_values" in segment_seed_rows[0]
