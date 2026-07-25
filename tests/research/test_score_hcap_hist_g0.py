from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from research.score_hcap_hist import g0
from research.score_hcap_hist import walkforward


def _source_fixture(path: Path, rows: list[tuple[object, ...]]) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE match_features (
          match_id INTEGER, issue TEXT, match_idx INTEGER, kickoff_ts TEXT, season_year INTEGER,
          league TEXT, home TEXT, away TEXT, home_rank TEXT, away_rank TEXT, handicap_line_norm REAL, fthg INTEGER, ftag INTEGER,
          result_code TEXT, settlement_quality TEXT, winning_sp REAL, official_sp_3 REAL
        );
        CREATE TABLE source_meta (key TEXT, value TEXT);
        INSERT INTO source_meta VALUES ('built_at', '2026-07-26T00:00:00Z');
        """
    )
    connection.executemany("INSERT INTO match_features VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()


def _row(match_id: int, season: int, *, issue: str | None = None, match_idx: int = 1) -> tuple[object, ...]:
    return (
        match_id, issue or f"{season}01", match_idx, f"{season}-06-01 12:00:00", season,
        "League", "Home FC", "Away FC", None, None, 0, 1, 0, "3", "trusted", 999.0, 888.0,
    )


def _eligible_rows() -> list[tuple[object, ...]]:
    return [_row(1, 2014), _row(2, 2015)] + [
        _row(index + 3, year) for index, year in enumerate(g0.TEST_SEASONS)
    ]


def test_g0_exports_outcome_panel_without_sp_fields_and_is_byte_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(g0, "MIN_ROWS", 1)
    monkeypatch.setattr(g0, "MIN_TEST_ROWS", 1)
    first_source, second_source = tmp_path / "first.db", tmp_path / "second.db"
    rows = _eligible_rows()
    _source_fixture(first_source, rows)
    _source_fixture(second_source, list(reversed(rows)))

    first = g0.export_g0_panel(source_db=first_source, work_dir=tmp_path / "first")
    second = g0.export_g0_panel(source_db=second_source, work_dir=tmp_path / "second")

    assert first["audit_data"]["gate"]["status"] == "G0_ELIGIBLE_EVIDENCE_C"
    assert first["audit_data"]["gate"]["formal_b0_b1_authorized"] is True
    assert first["audit_data"]["query_audit"]["ticket_budget_roi_output"] is False
    assert g0.sha256_file(first["panel"]) == g0.sha256_file(second["panel"])
    panel = sqlite3.connect(first["panel"])
    columns = {row[1] for row in panel.execute("PRAGMA table_info(panel)")}
    first_clock = panel.execute("SELECT kickoff_utc FROM panel ORDER BY match_id LIMIT 1").fetchone()[0]
    panel.close()
    assert "winning_sp" not in columns
    assert "official_sp_3" not in columns
    assert first_clock.endswith("+00:00")


def test_g0_fails_closed_for_result_mismatch_and_identity_conflicts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(g0, "MIN_ROWS", 1)
    monkeypatch.setattr(g0, "MIN_TEST_ROWS", 1)
    rows = _eligible_rows()
    mismatch = list(_row(99, 2016, issue="bad", match_idx=9))
    mismatch[11] = "0"
    rows.append(tuple(mismatch))
    rows.append(_row(100, 2017, issue="same", match_idx=5))
    rows.append(_row(101, 2017, issue="same", match_idx=5))
    source = tmp_path / "invalid.db"
    _source_fixture(source, rows)

    result = g0.export_g0_panel(source_db=source, work_dir=tmp_path / "result")
    coverage = result["audit_data"]["coverage"]
    assert result["audit_data"]["gate"]["status"] == "INSUFFICIENT_HISTORICAL_DATA"
    assert result["audit_data"]["gate"]["formal_b0_b1_authorized"] is False
    assert coverage["stored_result_code_mismatches"] == 1
    assert coverage["issue_match_idx_conflicts"] == 1
    assert "result_code_mismatch_rate_above_0_5_percent" in result["audit_data"]["gate"]["reasons"]
    assert "unresolved_duplicate_or_canonical_key_conflicts" in result["audit_data"]["gate"]["reasons"]
    audit = json.loads(result["audit"].read_text(encoding="utf-8"))
    assert audit == result["audit_data"]


def _panel_fixture(path: Path, *, future_extra: bool = False) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE panel (
          match_id INTEGER PRIMARY KEY, issue TEXT, match_idx INTEGER, kickoff_utc TEXT, season_year INTEGER,
          league TEXT, home_team TEXT, away_team TEXT, normalized_home TEXT, normalized_away TEXT,
          handicap INTEGER, fthg INTEGER, ftag INTEGER, label_310 TEXT, settlement_quality TEXT
        );
        """
    )
    rows = [
        (1, "1401", 1, "2014-01-01T00:00:00+00:00", 2014, "L", "A", "B", "a", "b", 0, 1, 0, "3", "trusted"),
        (2, "1501", 1, "2015-01-01T00:00:00+00:00", 2015, "L", "B", "A", "b", "a", 0, 0, 1, "0", "trusted"),
        (3, "1601", 1, "2016-01-01T00:00:00+00:00", 2016, "L", "A", "B", "a", "b", 0, 1, 1, "1", "trusted"),
    ]
    if future_extra:
        rows.append((4, "1701", 1, "2017-01-01T00:00:00+00:00", 2017, "L", "A", "B", "a", "b", 0, 9, 0, "3", "trusted"))
    connection.executemany("INSERT INTO panel VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()


def test_skellam_mapping_and_walkforward_are_chronological(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    assert sum(walkforward.handicap_probabilities(1.2, 0.9, -1)) == pytest.approx(1.0, abs=1e-12)
    assert sum(walkforward.handicap_probabilities(1.2, 0.9, 0)) == pytest.approx(1.0, abs=1e-12)
    assert sum(walkforward.handicap_probabilities(1.2, 0.9, 1)) == pytest.approx(1.0, abs=1e-12)
    monkeypatch.setattr(walkforward, "TEST_SEASONS", (2016,))
    monkeypatch.setattr(walkforward, "BOOTSTRAP_REPLICATES", 4)
    first, second = tmp_path / "first.sqlite", tmp_path / "second.sqlite"
    _panel_fixture(first)
    _panel_fixture(second, future_extra=True)
    one = walkforward.run_walkforward(panel=first, output_dir=tmp_path / "one")
    two = walkforward.run_walkforward(panel=second, output_dir=tmp_path / "two")
    assert one["summary"]["aggregate"] == two["summary"]["aggregate"]
    assert (tmp_path / "one" / "bootstrap_deltas.csv").read_bytes() == (tmp_path / "two" / "bootstrap_deltas.csv").read_bytes()
