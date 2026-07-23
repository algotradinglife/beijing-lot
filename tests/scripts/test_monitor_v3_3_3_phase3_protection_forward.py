from __future__ import annotations

import importlib.util
import csv
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/monitor_v3_3_3_phase3_protection_forward.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("monitor_v3_3_3_phase3_protection_forward", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_settlement_tracks_coverage_depth_and_lost_rescue() -> None:
    mod = _load_module()
    samples = [
        {
            "issue": "1", "match_idx": 1, "baseline_codes": "0+3", "candidate_codes": "0",
            "triggered": 1, "execution_enabled": 0, "result_code": "3", "winning_sp": 4.0, "settled": 1,
        },
        {
            "issue": "1", "match_idx": 2, "baseline_codes": "0+3", "candidate_codes": "0",
            "triggered": 1, "execution_enabled": 0, "result_code": "0", "winning_sp": 2.5, "settled": 1,
        },
    ]

    records = mod.settled_records(samples)
    summary = mod.summarize(samples, records, artifact_count=1)

    assert summary["lost_rescues"] == 1
    assert summary["coverage_delta"] == -0.5
    assert summary["depth_delta"] == -1.0
    assert summary["profit_delta"] == -2.0
    assert summary["gates"]["execution_disabled"] is True


def test_candidate_row_requires_exact_version_and_disabled_execution() -> None:
    mod = _load_module()
    row = {
        "shadow_arm": "active_v3.3.3",
        "phase3_protection_experiment_id": mod.EXPERIMENT_ID,
        "phase3_protection_experiment_version": mod.EXPERIMENT_VERSION,
        "phase3_protection_execution_enabled": "0",
    }

    assert mod.candidate_row(row) is True
    assert mod.candidate_row({**row, "phase3_protection_execution_enabled": "1"}) is False
    assert mod.candidate_row({**row, "phase3_protection_experiment_version": "v9"}) is False


def test_alert_builder_names_each_actionable_monitor_failure() -> None:
    mod = _load_module()

    alerts = mod.build_alerts(
        missing_field_indices=[41],
        missing_sample_indices=[42],
        execution_enabled_indices=[43],
        settlement_stalled_indices=[44],
    )

    assert [row["code"] for row in alerts] == [
        "artifact_fields_missing",
        "prekick_sample_missing",
        "execution_enabled",
        "settlement_stalled",
    ]
    assert [row["severity"] for row in alerts] == ["bad", "bad", "bad", "warn"]


def test_alert_audit_distinguishes_missing_fields_samples_and_execution(tmp_path: Path) -> None:
    mod = _load_module()
    db = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE matches (issue TEXT, match_idx INTEGER, end_time TEXT, result_code TEXT, winning_sp REAL)")
    conn.executemany(
        "INSERT INTO matches VALUES ('99101', ?, '2099-07-12 18:00:00', '', NULL)",
        [(1,), (2,), (3,)],
    )
    conn.commit()
    root = tmp_path / "artifacts"
    path = root / "99101_test" / "structured_shadow_99101.csv"
    path.parent.mkdir(parents=True)
    rows = [
        {
            "issue": "99101", "match_idx": "1", "shadow_arm": "active_v3.3.3",
            "phase3_protection_experiment_id": "", "phase3_protection_experiment_version": "",
            "phase3_protection_execution_enabled": "0",
        },
        {
            "issue": "99101", "match_idx": "3", "shadow_arm": "active_v3.3.3",
            "phase3_protection_experiment_id": mod.EXPERIMENT_ID,
            "phase3_protection_experiment_version": mod.EXPERIMENT_VERSION,
            "phase3_protection_execution_enabled": "1",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    alerts = mod.audit_alerts(
        conn,
        [root],
        [],
        now=datetime(2099, 7, 12, 12, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )
    conn.close()

    by_code = {row["code"]: row for row in alerts}
    assert by_code["artifact_fields_missing"]["match_indices"] == [1]
    assert by_code["prekick_sample_missing"]["match_indices"] == [2]
    assert by_code["execution_enabled"]["match_indices"] == [3]


def test_write_outputs_refreshes_monitor_heartbeat_when_content_is_unchanged(tmp_path: Path) -> None:
    mod = _load_module()
    summary = mod.summarize([], [], artifact_count=0)

    assert mod.write_outputs(tmp_path, [], [], summary) is True
    summary_path = tmp_path / "summary.json"
    old_timestamp = datetime(2026, 7, 12, 12, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")).timestamp()
    os.utime(summary_path, (old_timestamp, old_timestamp))

    assert mod.write_outputs(tmp_path, [], [], summary) is False
    assert summary_path.stat().st_mtime > old_timestamp
