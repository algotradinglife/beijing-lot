from __future__ import annotations

import json
import csv
import sqlite3
import shutil
from pathlib import Path

import pytest

from research.score_hcap_hist import g0
from research.score_hcap_hist import binding
from research.score_hcap_hist import walkforward
from src.research_freeze_protocol import ResearchFreezeError, create_freeze_package


def _source_fixture(path: Path, rows: list[tuple[object, ...]]) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE match_features (
          match_id INTEGER, issue TEXT, match_idx INTEGER, kickoff_ts TEXT, season_year INTEGER,
          league TEXT, home TEXT, away TEXT, home_rank TEXT, away_rank TEXT, handicap_line_norm REAL, fthg INTEGER, ftag INTEGER,
          result_code TEXT, settlement_quality TEXT, has_trusted_settlement INTEGER,
          winning_sp REAL, official_sp_3 REAL
        );
        CREATE TABLE source_meta (key TEXT, value TEXT);
        INSERT INTO source_meta VALUES ('built_at', '2026-07-26T00:00:00Z');
        """
    )
    connection.executemany("INSERT INTO match_features VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()


def _row(match_id: int, season: int, *, issue: str | None = None, match_idx: int = 1) -> tuple[object, ...]:
    return (
        match_id, issue or f"{season}01", match_idx, f"{season}-06-01 12:00:00", season,
        "League", "Home FC", "Away FC", None, None, 0, 1, 0, "3", "trusted", 1, 999.0, 888.0,
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
    assert first["audit_data"]["provenance"]["source_database"]["sha256"] == g0.sha256_file(first_source)
    assert first["audit_data"]["coverage"]["issue_range"]["source_min"] == "201401"
    assert first["audit_data"]["coverage"]["kickoff_parseability"]["parseable_rows"] == len(rows)
    assert first["audit_data"]["chronology"]["fold_mapping"] == g0.FOLD_MAPPING
    assert first["audit_data"]["chronology"]["admitted_rows_with_source_season_disagreement"] == 0
    assert first["audit_data"]["query_audit"]["ticket_budget_roi_output"] is False
    assert g0.sha256_file(first["panel"]) == g0.sha256_file(second["panel"])
    panel = sqlite3.connect(first["panel"])
    columns = {row[1] for row in panel.execute("PRAGMA table_info(panel)")}
    first_clock = panel.execute("SELECT kickoff_utc FROM panel ORDER BY match_id LIMIT 1").fetchone()[0]
    panel.close()
    assert "winning_sp" not in columns
    assert "official_sp_3" not in columns
    assert "fold_year" in columns
    assert "source_season_year" in columns
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
    rows.append(_row(102, 2018, issue=" ", match_idx=6))
    missing_score = list(_row(103, 2018, issue="missing-score", match_idx=7))
    missing_score[11] = None
    rows.append(tuple(missing_score))
    non_trusted = list(_row(104, 2018, issue="missing-sp", match_idx=8))
    non_trusted[14], non_trusted[15] = "missing_sp", 0
    rows.append(tuple(non_trusted))
    season_mismatch = list(_row(105, 2015, issue="season-mismatch", match_idx=9))
    season_mismatch[3] = "2016-06-01 12:00:00"
    rows.append(tuple(season_mismatch))
    source = tmp_path / "invalid.db"
    _source_fixture(source, rows)

    result = g0.export_g0_panel(source_db=source, work_dir=tmp_path / "result")
    coverage = result["audit_data"]["coverage"]
    assert result["audit_data"]["gate"]["status"] == "INSUFFICIENT_HISTORICAL_DATA"
    assert result["audit_data"]["gate"]["formal_b0_b1_authorized"] is False
    assert coverage["stored_result_code_mismatches"] == 1
    assert coverage["issue_match_idx_conflicts"] == 1
    assert coverage["source_missing_issue_or_match_idx"] == 1
    assert coverage["exclusions"]["missing_issue_or_match_idx"] == 1
    assert coverage["score_diagnostics"]["source"]["rows_with_missing_score"] == 1
    assert coverage["score_diagnostics"]["candidate_after_time_identity_handicap_filters"]["rows_with_missing_score"] == 1
    status = coverage["special_status_diagnostics"]
    assert status["eligible_settlement_qualities"] == ["trusted"]
    assert status["candidate_quality_counts_after_clock_identity_handicap_score_filters"]["missing_sp"] == 1
    assert coverage["exclusions"]["ineligible_settlement_quality_missing_sp"] == 1
    assert coverage["exclusions"]["source_season_kickoff_year_mismatch"] == 1
    assert result["audit_data"]["chronology"]["diagnostics"]["source_season_disagreement_in_canonical_window"] == 1
    assert "result_code_mismatch_rate_above_0_5_percent" in result["audit_data"]["gate"]["reasons"]
    assert "unresolved_duplicate_or_canonical_key_conflicts" in result["audit_data"]["gate"]["reasons"]
    audit = json.loads(result["audit"].read_text(encoding="utf-8"))
    assert audit == result["audit_data"]


def _freeze_g0_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict[str, object], Path]:
    monkeypatch.setattr(g0, "MIN_ROWS", 1)
    monkeypatch.setattr(g0, "MIN_TEST_ROWS", 1)
    source = tmp_path / "source.db"
    _source_fixture(source, _eligible_rows())
    result = g0.export_g0_panel(source_db=source, work_dir=tmp_path / "g0-work")
    decision = tmp_path / "g0-work" / "g0_decision.json"
    config = tmp_path / "g0-work" / "g0_config.json"
    decision.write_text(json.dumps(result["audit_data"]["gate"], sort_keys=True) + "\n", encoding="utf-8")
    config.write_text(json.dumps({"execution_enabled": False, "fold_mapping": g0.FOLD_MAPPING, "eligible_settlement_qualities": list(g0.ELIGIBLE_SETTLEMENT_QUALITIES)}, sort_keys=True) + "\n", encoding="utf-8")
    freeze = tmp_path / "freeze" / "g0"
    create_freeze_package(
        freeze,
        experiment_id=binding.G0_EXPERIMENT_ID,
        research_question="fixture G0 eligibility",
        model_version="fixture-g0-v1",
        input_files=[result["panel"], result["schema"], result["audit"], result["matrix"]],
        input_datasets=[source],
        decision_files=[decision],
        config_file=config,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-26T00:00:00+00:00",
    )
    return source, result, freeze


def test_b0_b1_requires_verified_g0_package_exact_panel_and_source_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source, result, g0_freeze = _freeze_g0_fixture(tmp_path, monkeypatch)
    verified = binding.verified_g0_binding(g0_freeze_dir=g0_freeze, source_db=source)
    assert binding.require_bound_panel(verified.panel, verified) == verified.panel
    assert verified.panel_sha256 == g0.sha256_file(result["panel"])

    invalid = tmp_path / "invalid-g0"
    invalid.mkdir()
    with pytest.raises(ResearchFreezeError, match="invalid freeze manifest"):
        binding.verified_g0_binding(g0_freeze_dir=invalid, source_db=source)

    wrong_g0 = tmp_path / "freeze" / "wrong-g0"
    decision = tmp_path / "g0-work" / "g0_decision.json"
    config = tmp_path / "g0-work" / "g0_config.json"
    create_freeze_package(
        wrong_g0,
        experiment_id="WRONG-G0",
        research_question="fixture wrong identity",
        model_version="fixture-g0-v1",
        input_files=[result["panel"], result["schema"], result["audit"], result["matrix"]],
        input_datasets=[source],
        decision_files=[decision],
        config_file=config,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-26T00:00:00+00:00",
    )
    with pytest.raises(ResearchFreezeError, match="requires a SCORE-HCAP-HIST-001-G0 freeze"):
        binding.verified_g0_binding(g0_freeze_dir=wrong_g0, source_db=source)

    alien_panel = tmp_path / "alien" / "historical_panel.sqlite"
    alien_panel.parent.mkdir()
    shutil.copyfile(verified.panel, alien_panel)
    with alien_panel.open("ab") as handle:
        handle.write(b"not the frozen panel")
    with pytest.raises(ResearchFreezeError, match="panel SHA-256"):
        binding.require_bound_panel(alien_panel, verified)

    b0_b1_config = tmp_path / "b0-b1-config.json"
    b0_b1_decision = tmp_path / "b0-b1-decision.json"
    b0_b1_config.write_text(json.dumps({"g0_binding": verified.as_config()}, sort_keys=True) + "\n", encoding="utf-8")
    b0_b1_decision.write_text('{"status":"fixture"}\n', encoding="utf-8")
    b0_b1 = tmp_path / "freeze" / "b0-b1"
    create_freeze_package(
        b0_b1,
        experiment_id=binding.B0_B1_EXPERIMENT_ID,
        research_question="fixture B0/B1",
        model_version="fixture-b1-v1",
        input_files=[verified.panel],
        input_datasets=[source],
        decision_files=[b0_b1_decision],
        config_file=b0_b1_config,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-26T00:00:00+00:00",
    )
    binding.verify_b0_b1_package_binding(b0_b1, verified)

    mismatched_b0_b1 = tmp_path / "freeze" / "mismatched-b0-b1"
    create_freeze_package(
        mismatched_b0_b1,
        experiment_id=binding.B0_B1_EXPERIMENT_ID,
        research_question="fixture B0/B1 mismatch",
        model_version="fixture-b1-v1",
        input_files=[alien_panel],
        input_datasets=[source],
        decision_files=[b0_b1_decision],
        config_file=b0_b1_config,
        git_commit="a" * 40,
        frozen_at_utc="2026-07-26T00:00:00+00:00",
    )
    with pytest.raises(ResearchFreezeError, match="panel SHA-256"):
        binding.verify_b0_b1_package_binding(mismatched_b0_b1, verified)

    wrong_source = tmp_path / "wrong-source.db"
    shutil.copyfile(source, wrong_source)
    with wrong_source.open("ab") as handle:
        handle.write(b"different snapshot")
    with pytest.raises(ResearchFreezeError, match="source database SHA-256"):
        binding.verified_g0_binding(g0_freeze_dir=g0_freeze, source_db=wrong_source)


def _panel_fixture(path: Path, *, future_extra: bool = False, same_season_extra: bool = False, cold_start: bool = False) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE panel (
          match_id INTEGER PRIMARY KEY, issue TEXT, match_idx INTEGER, kickoff_utc TEXT,
          fold_year INTEGER, source_season_year INTEGER,
          league TEXT, home_team TEXT, away_team TEXT, normalized_home TEXT, normalized_away TEXT,
          handicap INTEGER, fthg INTEGER, ftag INTEGER, label_310 TEXT, settlement_quality TEXT
        );
        """
    )
    rows = [
        (1, "1401", 1, "2014-01-01T00:00:00+00:00", 2014, 2014, "L", "A", "B", "a", "b", 0, 1, 0, "3", "trusted"),
        (2, "1501", 1, "2015-01-01T00:00:00+00:00", 2015, 2015, "L", "B", "A", "b", "a", 0, 0, 1, "0", "trusted"),
        (3, "1601", 1, "2016-01-01T00:00:00+00:00", 2016, 2016, "L", "C" if cold_start else "A", "D" if cold_start else "B", "c" if cold_start else "a", "d" if cold_start else "b", 0, 1, 1, "1", "trusted"),
    ]
    if same_season_extra:
        rows.append((5, "1602", 1, "2016-06-01T00:00:00+00:00", 2016, 2016, "L", "A", "B", "a", "b", 0, 8, 0, "3", "trusted"))
    if future_extra:
        rows.append((4, "1701", 1, "2017-01-01T00:00:00+00:00", 2017, 2017, "L", "A", "B", "a", "b", 0, 9, 0, "3", "trusted"))
    connection.executemany("INSERT INTO panel VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.commit()
    connection.close()


def test_skellam_mapping_and_walkforward_are_chronological(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    assert g0._label(1, 0, 0) == "3"
    assert g0._label(1, 1, 0) == "1"
    assert g0._label(0, 1, 0) == "0"
    assert g0._label(0, 1, 1) == "1"
    assert g0._label(1, 0, -1) == "1"
    assert sum(walkforward.handicap_probabilities(1.2, 0.9, -1)) == pytest.approx(1.0, abs=1e-12)
    assert sum(walkforward.handicap_probabilities(1.2, 0.9, 0)) == pytest.approx(1.0, abs=1e-12)
    assert sum(walkforward.handicap_probabilities(1.2, 0.9, 1)) == pytest.approx(1.0, abs=1e-12)
    monkeypatch.setattr(walkforward, "TEST_SEASONS", (2016,))
    monkeypatch.setattr(walkforward, "BOOTSTRAP_REPLICATES", 4)
    first, second = tmp_path / "first.sqlite", tmp_path / "second.sqlite"
    _panel_fixture(first)
    _panel_fixture(second, future_extra=True)
    same_season = tmp_path / "same-season.sqlite"
    _panel_fixture(same_season, same_season_extra=True)
    config = {"g0_freeze_id": "fixture-g0", "execution_enabled": False}
    one = walkforward.run_walkforward(panel=first, output_dir=tmp_path / "one", frozen_config=config)
    two = walkforward.run_walkforward(panel=second, output_dir=tmp_path / "two")
    assert one["summary"]["aggregate"] == two["summary"]["aggregate"]
    assert (tmp_path / "one" / "bootstrap_deltas.csv").read_bytes() == (tmp_path / "two" / "bootstrap_deltas.csv").read_bytes()
    receipt = json.loads((tmp_path / "one" / "reproducibility_receipt.json").read_text(encoding="utf-8"))
    assert receipt["outputs"]["frozen_b0_b1_config.json"] == walkforward.sha256_file(tmp_path / "one" / "frozen_b0_b1_config.json")
    first_prediction = next(row for row in walkforward._fit_predict(first) if row["match_id"] == 3)
    same_season_prediction = next(row for row in walkforward._fit_predict(same_season) if row["match_id"] == 3)
    assert first_prediction == same_season_prediction
    calibration_rows = list(csv.DictReader((tmp_path / "one" / "calibration_bins.csv").open(encoding="utf-8")))
    assert len(calibration_rows) == 2 * 3 * 10
    assert not any("ticket" in path.name or "roi" in path.name for path in (tmp_path / "one").iterdir())


def test_walkforward_cold_start_uses_global_role_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(walkforward, "TEST_SEASONS", (2016,))
    monkeypatch.setattr(walkforward, "BOOTSTRAP_REPLICATES", 2)
    panel = tmp_path / "cold.sqlite"
    _panel_fixture(panel, cold_start=True)
    result = walkforward.run_walkforward(panel=panel, output_dir=tmp_path / "cold")
    row = next(csv.DictReader((tmp_path / "cold" / "predictions.csv").open(encoding="utf-8")))
    assert row["cold_start"] == "1"
    assert float(row["lambda_home"]) > 0
    assert float(row["lambda_away"]) > 0
    assert result["summary"]["final_decision"]["decision_rule"]["test_season_count"] == 1
