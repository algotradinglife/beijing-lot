from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.decision_api import app as appmod


def _minimal_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS issues (
                issue TEXT PRIMARY KEY,
                ordinal INTEGER,
                label TEXT,
                is_current INTEGER,
                first_seen_at TEXT,
                last_seen_at TEXT
            );
            CREATE TABLE IF NOT EXISTS matches (
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                fid INTEGER,
                PRIMARY KEY (issue, match_idx)
            );
            INSERT INTO issues(issue, ordinal, label, is_current, first_seen_at, last_seen_at)
            VALUES ('99123', 99123, '99123', 0, '2026-07-07', '2026-07-07');
            INSERT INTO matches(issue, match_idx, fid)
            VALUES ('99123', 1, 99123001);
            INSERT INTO issues(issue, ordinal, label, is_current, first_seen_at, last_seen_at)
            VALUES ('99124', 99124, '99124', 0, '2026-07-07', '2026-07-07');
            INSERT INTO matches(issue, match_idx, fid)
            VALUES ('99124', 1, 99124001);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_segment_betting_plan_endpoint_reads_release_artifact(tmp_path: Path, monkeypatch) -> None:
    plan_dir = tmp_path / "segment_plans"
    plan = plan_dir / "99123_v3.3.3_b1000_seed42"
    plan.mkdir(parents=True)
    (plan / "segment_betting_plan_summary.json").write_text(
        json.dumps(
            {
                "issue": "99123",
                "label": "v3.3.3",
                "strategy_family": "segment_betting_plan",
                "betting_strategy_version": "segment_betting_v0.3.0000",
                "artifact_schema_version": "segment_betting_artifact_v1",
                "arm": "shadow",
                "source_rows": 8,
                "eligible_rows": 8,
                "available_segments": 1,
                "segments": 1,
                "planning_scope": "next_segment",
                "decision_time": "",
                "sp_drift_risk": {
                    "accepted": False,
                    "level": "low",
                    "reason": "next segment only",
                },
                "settings": {
                    "planning_scope": "next_segment",
                    "decision_time": "",
                    "stake_mode": "scale_to_budget",
                    "window_hours": 12.0,
                    "segment_budget_yuan": 1000.0,
                    "stake_yuan_per_ticket": 2.0,
                    "sample_seed": 42,
                    "min_n": 3,
                    "max_n": 8,
                    "positive_ev_only": True,
                    "betting_strategy_version": "segment_betting_v0.3.0000",
                },
                "summary": {
                    "segments": 1,
                    "selected_segments": 1,
                    "dead_segments": 0,
                    "selected_bundles": 1,
                    "base_cost_yuan": 32.0,
                    "stake_multiplier_units": 2.0,
                    "selected_cost_yuan": 64.0,
                    "payout_yuan": 192.0,
                    "profit_yuan": 128.0,
                    "roi": 2.0,
                },
                "seed_aggregate": {
                    "seed_count": 2,
                    "seeds": [42, 43],
                    "summary_mode": "multi_seed_mean",
                    "metrics": {
                        "profit_yuan": {"min": -64.0, "p10": -44.8, "mean": 128.0, "median": 128.0, "p90": 300.8, "max": 320.0},
                        "roi": {"min": -1.0, "p10": -0.7, "mean": 2.0, "median": 2.0, "p90": 4.7, "max": 5.0},
                    },
                },
                "parameter_schema": [
                    {"key": "segment_budget_yuan", "label": "segment budget", "ui_level": "basic", "type": "number", "unit": "yuan", "default": 1000.0, "effect": "Caps total cost."},
                    {"key": "sample_seed", "label": "sample seed", "ui_level": "debug", "type": "integer", "default": 42, "effect": "Primary seed."},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    unit_plan = plan_dir / "99123_v3.3.3_unit_once_b1000_seed99"
    unit_plan.mkdir(parents=True)
    (unit_plan / "segment_betting_plan_summary.json").write_text(
        json.dumps(
            {
                "issue": "99123",
                "label": "v3.3.3",
                "strategy_family": "segment_betting_plan",
                "betting_strategy_version": "segment_betting_v0.3.0000",
                "artifact_schema_version": "segment_betting_artifact_v1",
                "source_rows": 8,
                "eligible_rows": 8,
                "available_segments": 1,
                "segments": 1,
                "planning_scope": "next_segment",
                "decision_time": "",
                "settings": {
                    "planning_scope": "next_segment",
                    "decision_time": "",
                    "stake_mode": "unit_once",
                    "segment_budget_yuan": 1000.0,
                    "sample_seed": 99,
                    "seed_count": 3,
                    "betting_strategy_version": "segment_betting_v0.3.0000",
                },
                "summary": {
                    "segments": 1,
                    "selected_segments": 1,
                    "selected_bundles": 1,
                    "base_cost_yuan": 32.0,
                    "stake_multiplier_units": 1.0,
                    "selected_cost_yuan": 32.0,
                    "profit_yuan": 96.0,
                    "roi": 3.0,
                },
                "seed_aggregate": {
                    "seed_count": 3,
                    "seeds": [99, 100, 101],
                    "summary_mode": "multi_seed_mean",
                    "metrics": {},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _write_csv(
        plan / "segment_betting_plan_segments.csv",
        [
            {
                "segment_idx": 1,
                "arm": "shadow",
                "planning_scope": "next_segment",
                "hours_from_decision_start": 2,
                "hours_from_decision_end": 14,
                "sp_drift_risk_accepted": 0,
                "sp_drift_risk_level": "low",
                "sp_drift_risk_reason": "next segment only",
                "segment_start": "2026-07-07 10:00",
                "segment_end": "2026-07-07 22:00",
                "window_hours": 12,
                "eligible_matches": 8,
                "expected_coverage_hit_rate": 0.7,
                "actual_coverage_hits": 7,
                "actual_coverage_hit_rate": 0.875,
                "recommended_n": 5,
                "initial_recommended_n": 5,
                "selected_bundles": 1,
                "candidate_bundles": 12,
                "stake_mode": "scale_to_budget",
                "base_cost_yuan": 32,
                "stake_multiplier_units": 2,
                "selected_cost_yuan": 64,
                "segment_budget_yuan": 1000,
                "expected_profit_yuan": 120,
                "payout_yuan": 192,
                "profit_yuan": 128,
                "roi": 2,
                "dead_segment": 0,
                "width_counts": "{1: 2, 2: 3}",
                "reasons": "budget_coverage_ok;coverage_hit_rate_good_use_half_n",
                "match_indices": "1,2,3,4,5,6,7,8",
            }
        ],
    )
    _write_csv(
        plan / "segment_betting_plan_bundles.csv",
        [
            {
                "segment_idx": 1,
                "bundle_idx": 7,
                "arm": "shadow",
                "n_value": 5,
                "match_indices": "1,2,3,4,5",
                "leg_codes": "3+1|0|3|1+0|3+0",
                "widths": "2,1,1,2,2",
                "stake_multiplier": 2,
                "cost_yuan": 16,
                "scaled_cost_yuan": 32,
                "expected_profit_yuan": 64,
                "scaled_expected_profit_yuan": 128,
                "expected_roi": 4,
                "hit_prob": 0.12,
                "realized_hit": 1,
                "payout_yuan": 80,
                "scaled_payout_yuan": 160,
                "profit_yuan": 64,
                "scaled_profit_yuan": 128,
            }
        ],
    )
    _write_csv(
        plan / "segment_betting_plan_seed_summary.csv",
        [
            {"sample_seed": 42, "selected_segments": 1, "dead_segments": 0, "selected_bundles": 1, "selected_cost_yuan": 64, "payout_yuan": 192, "profit_yuan": 128, "roi": 2},
            {"sample_seed": 43, "selected_segments": 1, "dead_segments": 1, "selected_bundles": 1, "selected_cost_yuan": 64, "payout_yuan": 0, "profit_yuan": -64, "roi": -1},
        ],
    )
    _write_csv(
        plan / "segment_betting_plan_segment_seed_summary.csv",
        [
            {
                "segment_idx": 1,
                "arm": "shadow",
                "sample_count": 2,
                "segment_start": "2026-07-07 10:00",
                "segment_end": "2026-07-07 22:00",
                "eligible_matches": 8,
                "expected_coverage_hit_rate": 0.7,
                "actual_coverage_hits": 7,
                "actual_coverage_hit_rate": 0.875,
                "recommended_n_values": "5",
                "recommended_n_stable": 1,
                "selected_bundles_mean": 1,
                "selected_bundles_min": 1,
                "selected_bundles_max": 1,
                "base_cost_yuan_mean": 32,
                "stake_multiplier_units_mean": 2,
                "cost_yuan_mean": 64,
                "payout_yuan_mean": 96,
                "profit_yuan_min": -64,
                "profit_yuan_p10": -44.8,
                "profit_yuan_mean": 128,
                "profit_yuan_median": 128,
                "profit_yuan_p90": 300.8,
                "profit_yuan_max": 320,
                "roi_min": -1,
                "roi_mean": 2,
                "roi_max": 5,
                "dead_segment_rate": 0.5,
                "width_counts": "{1: 2, 2: 3}",
                "match_indices": "1,2,3,4,5,6,7,8",
            }
        ],
    )

    release_config = tmp_path / "strategy_release.json"
    release_config.write_text(
        json.dumps(
            {
                "active_release_id": appmod.DEFAULT_STRATEGY_RELEASE_ID,
                "releases": {
                    appmod.DEFAULT_STRATEGY_RELEASE_ID: {
                        "artifacts": {
                            "segment_betting_plan_dir": str(plan_dir),
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "bjdc.sqlite"
    _minimal_db(db_path)
    monkeypatch.setattr(appmod, "STRATEGY_RELEASE_CONFIG", release_config)
    appmod._strategy_release_registry.cache_clear()

    client = appmod.create_app(sqlite_db=db_path).test_client()
    response = client.get("/api/issues/99123/segment-betting-plan?decision_variant=shadow_v3.3.3&planning_scope=next_segment")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["availability_status"] == "available"
    assert payload["artifact_status"]["status"] == "available"
    assert payload["artifact_status"]["artifact_key"] == "segment_betting_plan_dir"
    assert payload["artifact_status"]["artifact_path"].endswith("99123_v3.3.3_b1000_seed42")
    assert payload["artifact_status"]["source_path"].endswith("segment_betting_plan_summary.json")
    assert payload["artifact_status"]["updated_at"]
    assert payload["_artifact_path"].endswith("99123_v3.3.3_b1000_seed42")
    assert payload["strategy_release"]["active_release_id"] == appmod.DEFAULT_STRATEGY_RELEASE_ID
    assert payload["requested_planning_scope"] == "by_segment"
    assert payload["requested_segment_budget_yuan"] is None
    assert payload["requested_stake_mode"] == ""
    assert payload["requested_betting_strategy_version"] == ""
    assert payload["requested_label"] == ""
    assert payload["strategy_family"] == "segment_betting_plan"
    assert payload["betting_strategy_version"] == "segment_betting_v0.3.0000"
    assert payload["artifact_schema_version"] == "segment_betting_artifact_v1"
    assert payload["planning_scope"] == "by_segment"
    assert payload["artifact_planning_scope"] == "next_segment"
    assert payload["selection_binding"]["match_selection_source"] == "issue_board_same_decision_variant"
    assert payload["available_segments"] == 1
    assert payload["sp_drift_risk"] == {"accepted": False, "level": "low", "reason": "next segment only"}
    assert payload["selected_plan_id"] == "99123_v3.3.3_b1000_seed42"
    assert payload["selected_plan"]["decision_variant_id"] == "active_v3.3.3"
    assert payload["selected_plan"]["betting_strategy_version"] == "segment_betting_v0.3.0000"
    assert payload["selected_plan"]["planning_scope"] == "by_segment"
    assert payload["selected_plan"]["artifact_planning_scope"] == "next_segment"
    assert payload["selected_plan"]["stake_mode"] == "scale_to_budget"
    assert payload["selected_plan"]["sp_drift_risk_level"] == "low"
    assert payload["selected_plan"]["seed_count"] == 2
    assert payload["selected_plan"]["summary_mode"] == "multi_seed_mean"
    assert payload["selected_plan"]["base_cost_yuan"] == 32.0
    assert payload["selected_plan"]["stake_multiplier_units"] == 2.0
    assert payload["settings"]["stake_mode"] == "scale_to_budget"
    assert payload["summary"]["base_cost_yuan"] == 32.0
    assert payload["summary"]["stake_multiplier_units"] == 2.0
    assert payload["summary"]["profit_yuan"] == 128.0
    assert payload["seed_aggregate"]["summary_mode"] == "multi_seed_mean"
    assert payload["seed_aggregate"]["metrics"]["profit_yuan"]["mean"] == 128.0
    assert payload["parameter_schema"][0]["key"] == "segment_budget_yuan"
    assert payload["segment_csv"].endswith("segment_betting_plan_segments.csv")
    assert payload["bundle_csv"].endswith("segment_betting_plan_bundles.csv")
    assert payload["seed_summary_csv"].endswith("segment_betting_plan_seed_summary.csv")
    assert payload["segment_seed_summary_csv"].endswith("segment_betting_plan_segment_seed_summary.csv")
    assert payload["segments"][0]["recommended_n"] == 5
    assert payload["segments"][0]["planning_scope"] == "by_segment"
    assert payload["segments"][0]["artifact_planning_scope"] == "next_segment"
    assert payload["segments"][0]["stake_mode"] == "scale_to_budget"
    assert payload["segments"][0]["base_cost_yuan"] == 32.0
    assert payload["segments"][0]["stake_multiplier_units"] == 2.0
    assert payload["segments"][0]["sp_drift_risk_accepted"] is False
    assert payload["segments"][0]["hours_from_decision_start"] == 2.0
    assert payload["segments"][0]["match_indices"] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert payload["bundles"][0]["leg_codes"] == ["3+1", "0", "3", "1+0", "3+0"]
    assert payload["bundles"][0]["stake_multiplier"] == 2.0
    assert payload["bundles"][0]["scaled_cost_yuan"] == 32.0
    assert payload["bundles"][0]["scaled_expected_profit_yuan"] == 128.0
    assert payload["bundles"][0]["scaled_payout_yuan"] == 160.0
    assert payload["bundles"][0]["scaled_profit_yuan"] == 128.0
    assert payload["bundles"][0]["realized_hit"] is True
    assert payload["seed_summaries"][1]["sample_seed"] == 43
    assert payload["segment_seed_summary"][0]["recommended_n_values"] == [5]
    assert payload["segment_seed_summary"][0]["base_cost_yuan_mean"] == 32.0
    assert payload["segment_seed_summary"][0]["stake_multiplier_units_mean"] == 2.0
    assert payload["segment_seed_summary"][0]["dead_segment_rate"] == 0.5
    assert payload["source"]["artifact_dir"] == plan_dir.name
    assert str(tmp_path) not in payload["selected_plan"]["artifact_path"]

    explicit_unit = client.get(
        "/api/issues/99123/segment-betting-plan"
        "?decision_variant=shadow_v3.3.3"
        "&planning_scope=next_segment"
        "&plan_id=99123_v3.3.3_unit_once_b1000_seed99"
    )
    assert explicit_unit.status_code == 200
    unit_payload = explicit_unit.get_json()
    assert unit_payload["availability_status"] == "degraded"
    assert unit_payload["selected_plan_id"] == "99123_v3.3.3_unit_once_b1000_seed99"
    assert unit_payload["selected_plan"]["stake_mode"] == "unit_once"
    assert unit_payload["settings"]["stake_mode"] == "unit_once"

    unit_by_mode = client.get(
        "/api/issues/99123/segment-betting-plan"
        "?decision_variant=shadow_v3.3.3"
        "&planning_scope=next_segment"
        "&segment_budget_yuan=1000"
        "&stake_mode=unit_once"
    )
    assert unit_by_mode.status_code == 200
    unit_by_mode_payload = unit_by_mode.get_json()
    assert unit_by_mode_payload["requested_segment_budget_yuan"] == 1000.0
    assert unit_by_mode_payload["requested_stake_mode"] == "unit_once"
    assert unit_by_mode_payload["selected_plan_id"] == "99123_v3.3.3_unit_once_b1000_seed99"

    version_and_label = client.get(
        "/api/issues/99123/segment-betting-plan"
        "?decision_variant=shadow_v3.3.3"
        "&planning_scope=next_segment"
        "&betting_strategy_version=segment_betting_v0.3.0000"
        "&label=v3.3.3"
    )
    assert version_and_label.status_code == 200
    version_and_label_payload = version_and_label.get_json()
    assert version_and_label_payload["requested_betting_strategy_version"] == "segment_betting_v0.3.0000"
    assert version_and_label_payload["requested_label"] == "v3.3.3"
    assert version_and_label_payload["selected_plan_id"] == "99123_v3.3.3_b1000_seed42"

    missing_label = client.get(
        "/api/issues/99123/segment-betting-plan"
        "?decision_variant=shadow_v3.3.3"
        "&planning_scope=next_segment"
        "&label=not-this-plan"
    )
    assert missing_label.status_code == 200
    missing_label_payload = missing_label.get_json()
    assert missing_label_payload["availability_status"] == "missing"
    assert missing_label_payload["artifact_status"]["status"] == "missing"
    assert missing_label_payload["requested_label"] == "not-this-plan"
    assert missing_label_payload["selected_plan_id"] == ""

    scaled_budget = client.get(
        "/api/issues/99123/segment-betting-plan"
        "?decision_variant=shadow_v3.3.3"
        "&planning_scope=next_segment"
        "&segment_budget_yuan=2000"
        "&stake_mode=scale_to_budget"
    )
    assert scaled_budget.status_code == 200
    scaled_budget_payload = scaled_budget.get_json()
    assert scaled_budget_payload["availability_status"] == "available"
    assert scaled_budget_payload["artifact_status"]["status"] == "available"
    assert scaled_budget_payload["requested_segment_budget_yuan"] == 2000.0
    assert scaled_budget_payload["requested_stake_mode"] == "scale_to_budget"
    assert scaled_budget_payload["selected_plan_id"] == "99123_v3.3.3_b1000_seed42"
    assert scaled_budget_payload["settings"]["segment_budget_yuan"] == 2000.0
    assert scaled_budget_payload["budget_rescale"]["applied"] is True
    assert scaled_budget_payload["budget_rescale"]["scale_factor"] == 2.0
    assert scaled_budget_payload["budget_rescale"]["method"] == "integer_budget_projection_from_selected_artifact"
    assert scaled_budget_payload["summary"]["selected_cost_yuan"] == 2000.0
    assert scaled_budget_payload["summary"]["stake_multiplier_units"] == 125
    assert scaled_budget_payload["segments"][0]["selected_cost_yuan"] == 2000.0
    assert scaled_budget_payload["segments"][0]["stake_multiplier_units"] == 125
    assert scaled_budget_payload["bundles"][0]["stake_multiplier"] == 125
    assert isinstance(scaled_budget_payload["bundles"][0]["stake_multiplier"], int)
    assert scaled_budget_payload["bundles"][0]["scaled_cost_yuan"] == 2000.0

    missing_scope = client.get("/api/issues/99123/segment-betting-plan?decision_variant=shadow_v3.3.3&planning_scope=remaining_issue")
    assert missing_scope.status_code == 200
    missing_payload = missing_scope.get_json()
    assert missing_payload["availability_status"] == "missing"
    assert missing_payload["requested_planning_scope"] == "entire_issue"
    assert missing_payload["selected_plan_id"] == ""


def test_segment_betting_plan_explicit_scope_and_time_do_not_use_legacy_artifact(tmp_path: Path, monkeypatch) -> None:
    plan_dir = tmp_path / "segment_plans"
    legacy = plan_dir / "99124_v3.3.3_b1000_seed1"
    legacy.mkdir(parents=True)
    (legacy / "segment_betting_plan_summary.json").write_text(
        json.dumps(
            {
                "issue": "99124",
                "label": "v3.3.3 legacy no scope",
                "strategy_family": "segment_betting_plan",
                "betting_strategy_version": "segment_betting_v0.1.0000",
                "artifact_schema_version": "segment_betting_artifact_v1",
                "planning_scope": "remaining_issue",
                "settings": {"planning_scope": "remaining_issue", "sample_seed": 1, "segment_budget_yuan": 1000.0},
                "summary": {"segments": 1, "selected_bundles": 1, "selected_cost_yuan": 2.0, "profit_yuan": 0.0, "roi": 0.0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _write_csv(
        legacy / "segment_betting_plan_segments.csv",
        [
            {
                "sample_seed": 1,
                "segment_idx": 1,
                "planning_scope": "remaining_issue",
                "segment_start": "2026-07-07 10:00",
                "segment_end": "2026-07-07 22:00",
                "recommended_n": 3,
                "dead_segment": 0,
            }
        ],
    )
    _write_csv(
        legacy / "segment_betting_plan_bundles.csv",
        [
            {
                "sample_seed": 1,
                "segment_idx": 1,
                "bundle_idx": 1,
                "n_value": 3,
                "leg_codes": "3|1|0",
                "widths": "1,1,1",
                "realized_hit": 0,
            }
        ],
    )

    release_config = tmp_path / "strategy_release.json"
    release_config.write_text(
        json.dumps(
            {
                "active_release_id": appmod.DEFAULT_STRATEGY_RELEASE_ID,
                "releases": {
                    appmod.DEFAULT_STRATEGY_RELEASE_ID: {
                        "artifacts": {
                            "segment_betting_plan_dir": str(plan_dir),
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "bjdc.sqlite"
    _minimal_db(db_path)
    monkeypatch.setattr(appmod, "STRATEGY_RELEASE_CONFIG", release_config)
    appmod._strategy_release_registry.cache_clear()

    client = appmod.create_app(sqlite_db=db_path).test_client()

    explicit_scope = client.get("/api/issues/99124/segment-betting-plan?decision_variant=shadow_v3.3.3&planning_scope=next_segment")
    assert explicit_scope.status_code == 200
    scope_payload = explicit_scope.get_json()
    assert scope_payload["availability_status"] == "missing"
    assert scope_payload["requested_planning_scope"] == "by_segment"
    assert scope_payload["selected_plan_id"] == ""

    explicit_time = client.get("/api/issues/99124/segment-betting-plan?decision_variant=shadow_v3.3.3&decision_time=2026-07-07%2016:00")
    assert explicit_time.status_code == 200
    time_payload = explicit_time.get_json()
    assert time_payload["availability_status"] == "missing"
    assert time_payload["requested_decision_time"] == "2026-07-07 16:00"
    assert time_payload["selected_plan_id"] == ""

    legacy_entry = client.get("/api/issues/99124/segment-betting-plan?decision_variant=shadow_v3.3.3")
    assert legacy_entry.status_code == 200
    legacy_payload = legacy_entry.get_json()
    assert legacy_payload["availability_status"] == "missing"
    assert legacy_payload["requested_planning_scope"] == "by_segment"
    assert legacy_payload["selected_plan_id"] == ""

    entire_scope = client.get("/api/issues/99124/segment-betting-plan?decision_variant=shadow_v3.3.3&planning_scope=remaining_issue")
    assert entire_scope.status_code == 200
    entire_payload = entire_scope.get_json()
    assert entire_payload["availability_status"] == "available"
    assert entire_payload["requested_planning_scope"] == "entire_issue"
    assert entire_payload["planning_scope"] == "entire_issue"
    assert entire_payload["artifact_planning_scope"] == "remaining_issue"
    assert entire_payload["selected_plan_id"] == "99124_v3.3.3_b1000_seed1"


def test_segment_betting_plan_rejects_unresolved_glob_issue(tmp_path: Path, monkeypatch) -> None:
    plan_dir = tmp_path / "segment_plans"
    plan = plan_dir / "99123_v3.3.3_b1000_seed42"
    plan.mkdir(parents=True)
    (plan / "segment_betting_plan_summary.json").write_text(
        json.dumps(
            {
                "issue": "99123",
                "label": "v3.3.3",
                "strategy_family": "segment_betting_plan",
                "betting_strategy_version": "segment_betting_v0.4.0000",
                "artifact_schema_version": "segment_betting_artifact_v1",
                "planning_scope": "by_segment",
                "settings": {"planning_scope": "by_segment", "sample_seed": 42, "segment_budget_yuan": 1000.0},
                "summary": {"segments": 1, "selected_bundles": 1, "selected_cost_yuan": 2.0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    release_config = tmp_path / "strategy_release.json"
    release_config.write_text(
        json.dumps(
            {
                "active_release_id": appmod.DEFAULT_STRATEGY_RELEASE_ID,
                "releases": {
                    appmod.DEFAULT_STRATEGY_RELEASE_ID: {
                        "artifacts": {
                            "segment_betting_plan_dir": str(plan_dir),
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "bjdc.sqlite"
    _minimal_db(db_path)
    monkeypatch.setattr(appmod, "STRATEGY_RELEASE_CONFIG", release_config)
    appmod._strategy_release_registry.cache_clear()

    client = appmod.create_app(sqlite_db=db_path).test_client()
    response = client.get("/api/issues/%2A/segment-betting-plan?decision_variant=shadow_v3.3.3")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Unknown issue: *"


def test_segment_betting_plan_freeze_accepts_prelock_source_and_rejects_late_variant(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bjdc.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE matches (
                issue TEXT NOT NULL,
                match_idx INTEGER NOT NULL,
                fid INTEGER,
                end_time TEXT,
                PRIMARY KEY (issue, match_idx)
            );
            INSERT INTO matches(issue, match_idx, fid, end_time)
            VALUES ('99125', 1, 99125001, '2000-01-01 01:00:00');
            """
        )
        conn.commit()
    finally:
        conn.close()

    freeze_at = datetime(2000, 1, 1, 0, 0, tzinfo=appmod.HK_TZ)
    late_mtime = freeze_at + timedelta(hours=2)
    plan_dir = tmp_path / "segment_plans"
    source_dir = tmp_path / "structured_sources"
    prelock_source = source_dir / "99125_20260101_shadow_v3.3.3" / "structured_shadow_99125.csv"
    late_source = source_dir / "99125_20260101_shadow_v4.2.0005_execution_late_proxy_fullcap2" / "structured_shadow_99125.csv"
    prelock_source.parent.mkdir(parents=True)
    late_source.parent.mkdir(parents=True)
    prelock_source.write_text("issue,match_idx\n99125,1\n", encoding="utf-8")
    late_source.write_text("issue,match_idx\n99125,1\n", encoding="utf-8")
    os.utime(prelock_source, (freeze_at.timestamp(), freeze_at.timestamp()))
    os.utime(late_source, (late_mtime.timestamp(), late_mtime.timestamp()))

    def write_plan(plan_name: str, label: str, structured_csv: Path) -> Path:
        plan = plan_dir / plan_name
        plan.mkdir(parents=True)
        summary_path = plan / "segment_betting_plan_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "issue": "99125",
                    "label": label,
                    "strategy_family": "segment_betting_plan",
                    "betting_strategy_version": "segment_betting_v0.4.0000",
                    "artifact_schema_version": "segment_betting_artifact_v1",
                    "planning_scope": "next_segment",
                    "decision_time": "1999-12-31 23:30:00",
                    "structured_csv": str(structured_csv),
                    "source_rows": 1,
                    "eligible_rows": 1,
                    "available_segments": 1,
                    "segments": 1,
                    "settings": {
                        "planning_scope": "next_segment",
                        "decision_time": "1999-12-31 23:30:00",
                        "stake_mode": "scale_to_budget",
                        "segment_budget_yuan": 1000.0,
                        "sample_seed": 7,
                        "seed_count": 1,
                        "betting_strategy_version": "segment_betting_v0.4.0000",
                    },
                    "summary": {
                        "segments": 1,
                        "selected_bundles": 1,
                        "base_cost_yuan": 2.0,
                        "stake_multiplier_units": 1.0,
                        "selected_cost_yuan": 2.0,
                        "profit_yuan": 0.0,
                        "roi": 0.0,
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.utime(summary_path, (late_mtime.timestamp(), late_mtime.timestamp()))
        return plan

    active_plan = write_plan("99125_v3.3.3_locked_materialized_late", "v3.3.3", prelock_source)
    write_plan("99125_v4.2.0005_late_proxy_postfreeze", "v4.2.0005_late_proxy", late_source)
    _write_csv(
        active_plan / "segment_betting_plan_segments.csv",
        [
            {
                "sample_seed": 7,
                "segment_idx": 1,
                "planning_scope": "next_segment",
                "segment_start": "2000-01-01 01:00:00",
                "segment_end": "2000-01-01 01:00:00",
                "recommended_n": 3,
                "selected_bundles": 1,
                "base_cost_yuan": 2,
                "stake_multiplier_units": 1,
                "selected_cost_yuan": 2,
                "dead_segment": 0,
            }
        ],
    )
    _write_csv(
        active_plan / "segment_betting_plan_bundles.csv",
        [
            {
                "sample_seed": 7,
                "segment_idx": 1,
                "bundle_idx": 1,
                "n_value": 3,
                "leg_codes": "3|1|0",
                "widths": "1,1,1",
                "realized_hit": 0,
            }
        ],
    )

    release_config = tmp_path / "strategy_release.json"
    release_config.write_text(
        json.dumps(
            {
                "active_release_id": appmod.DEFAULT_STRATEGY_RELEASE_ID,
                "releases": {
                    appmod.DEFAULT_STRATEGY_RELEASE_ID: {
                        "artifacts": {
                            "segment_betting_plan_dir": str(plan_dir),
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(appmod, "STRATEGY_RELEASE_CONFIG", release_config)
    appmod._strategy_release_registry.cache_clear()

    client = appmod.create_app(sqlite_db=db_path).test_client()
    active_response = client.get(
        "/api/issues/99125/segment-betting-plan"
        "?decision_variant=active_v3.3.3"
        "&planning_scope=next_segment"
    )
    assert active_response.status_code == 200
    active_payload = active_response.get_json()
    assert active_payload["availability_status"] == "available"
    assert active_payload["freeze_state"]["locked"] is True
    assert active_payload["freeze_state"]["freeze_at"] == "2000-01-01 00:00:00"
    assert active_payload["selected_plan_id"] == "99125_v3.3.3_locked_materialized_late"
    assert active_payload["artifact_status"]["freeze_info"]["reason"] == "structured_source_prelock"
    assert active_payload["freeze_state"]["rejected_plan_count"] == 1
    assert active_payload["rejected_frozen_plans"][0]["label"] == "v4.2.0005_late_proxy"

    late_response = client.get(
        "/api/issues/99125/segment-betting-plan"
        "?decision_variant=shadow_v4.2.0005_execution_late_proxy_fullcap2"
        "&planning_scope=next_segment"
    )
    assert late_response.status_code == 200
    late_payload = late_response.get_json()
    assert late_payload["availability_status"] == "missing"
    assert late_payload["unavailable_reason"] == "segment_betting_plan_frozen_requested_variant_rejected"
    assert late_payload["selected_plan_id"] == ""
    assert late_payload["available_plans"][0]["label"] == "v3.3.3"
