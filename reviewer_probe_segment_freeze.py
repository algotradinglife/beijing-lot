#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from argparse import Namespace

from src.decision_api import app as appmod
import scripts.live_artifact_refresh_loop as live_loop


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_plan(plan_dir: Path, name: str, label: str, structured_csv: Path, decision_time: str) -> Path:
    plan = plan_dir / name
    plan.mkdir(parents=True, exist_ok=True)
    summary = {
        "issue": "99130",
        "label": label,
        "strategy_family": "segment_betting_plan",
        "betting_strategy_version": "segment_betting_v0.4.0000",
        "artifact_schema_version": "segment_betting_artifact_v1",
        "planning_scope": "next_segment",
        "decision_time": decision_time,
        "structured_csv": str(structured_csv),
        "source_rows": 2,
        "eligible_rows": 2,
        "available_segments": 1,
        "segments": 1,
        "settings": {
            "planning_scope": "next_segment",
            "decision_time": decision_time,
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
    }
    (plan / "segment_betting_plan_summary.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    write_csv(plan / "segment_betting_plan_segments.csv", [{
        "sample_seed": 7,
        "segment_idx": 1,
        "planning_scope": "next_segment",
        "segment_start": "2000-01-01 01:00",
        "segment_end": "2000-01-01 02:00",
        "recommended_n": 3,
        "selected_bundles": 1,
        "base_cost_yuan": 2,
        "stake_multiplier_units": 1,
        "selected_cost_yuan": 2,
        "dead_segment": 0,
    }])
    write_csv(plan / "segment_betting_plan_bundles.csv", [{
        "sample_seed": 7,
        "segment_idx": 1,
        "bundle_idx": 1,
        "n_value": 3,
        "leg_codes": "3|1|0",
        "widths": "1,1,1",
        "realized_hit": 0,
    }])
    return plan


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="reviewer_segment_freeze_") as td:
        tmp = Path(td)
        db_path = tmp / "bjdc.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE matches (
                    issue TEXT NOT NULL,
                    match_idx INTEGER NOT NULL,
                    fid INTEGER,
                    end_time TEXT,
                    PRIMARY KEY(issue, match_idx)
                );
                INSERT INTO matches(issue, match_idx, fid, end_time)
                VALUES ('99130', 1, 99130001, '2000-01-01 01:00');
                INSERT INTO matches(issue, match_idx, fid, end_time)
                VALUES ('99130', 2, 99130002, '2000-01-01 02:00:00');
                """
            )

        freeze_at = datetime(2000, 1, 1, 0, 0, tzinfo=appmod.HK_TZ)
        late_mtime = freeze_at + timedelta(hours=2)
        source_dir = tmp / "structured"
        pre_source = source_dir / "99130_20260101_shadow_v3.3.3" / "structured_shadow_99130.csv"
        late_source = source_dir / "99130_20260101_shadow_v4.2.0005_execution_late_proxy_fullcap2" / "structured_shadow_99130.csv"
        pre_source.parent.mkdir(parents=True, exist_ok=True)
        late_source.parent.mkdir(parents=True, exist_ok=True)
        pre_source.write_text("issue,match_idx\n99130,1\n99130,2\n", encoding="utf-8")
        late_source.write_text("issue,match_idx\n99130,1\n99130,2\n", encoding="utf-8")
        os.utime(pre_source, (freeze_at.timestamp(), freeze_at.timestamp()))
        os.utime(late_source, (late_mtime.timestamp(), late_mtime.timestamp()))

        plan_dir = tmp / "plans"
        active_plan = make_plan(plan_dir, "99130_v3.3.3_postfreeze_summary_pre_source", "v3.3.3", pre_source, "1999-12-31 23:30:00")
        late_plan = make_plan(plan_dir, "99130_v4.2.0005_late_proxy_postfreeze", "v4.2.0005_late_proxy", late_source, "1999-12-31 23:30:00")
        for path in [active_plan / "segment_betting_plan_summary.json", late_plan / "segment_betting_plan_summary.json"]:
            os.utime(path, (late_mtime.timestamp(), late_mtime.timestamp()))

        release = {"artifacts": {"segment_betting_plan_dir": str(plan_dir)}}
        with appmod._connect(db_path) as conn:
            freeze_state = appmod._segment_plan_freeze_state(conn, "99130")
        active_payload, _ = appmod._segment_betting_plan_payload(
            "99130",
            release=release,
            decision_variant_id="active_v3.3.3",
            planning_scope="next_segment",
            freeze_state=freeze_state,
        )
        late_payload, _ = appmod._segment_betting_plan_payload(
            "99130",
            release=release,
            decision_variant_id="shadow_v4.2.0005_execution_late_proxy_fullcap2",
            planning_scope="next_segment",
            freeze_state=freeze_state,
        )
        assert freeze_state["locked"] is True
        assert freeze_state["first_kickoff"] == "2000-01-01 01:00:00"
        assert freeze_state["freeze_at"] == "2000-01-01 00:00:00"
        assert active_payload["availability_status"] == "available"
        assert active_payload["selected_plan_id"] == active_plan.name
        assert active_payload["artifact_status"]["freeze_info"]["reason"] == "structured_source_prelock"
        assert late_payload["availability_status"] == "missing"
        assert late_payload["unavailable_reason"] == "segment_betting_plan_frozen_requested_variant_rejected"
        assert late_payload["selected_plan_id"] == ""

        calls = {"ensure_segment": 0}
        def fake_active(db: Path, issue: str, *, timeout_sec: int) -> dict[str, object]:
            return {"issue": "99130", "artifact_status": {"status": "available"}}
        def fake_freeze(db: Path, issue: str) -> dict[str, object]:
            return {"locked": True, "freeze_at": "2000-01-01 00:00:00", "first_kickoff": "2000-01-01 01:00:00"}
        def fake_ensure(*args, **kwargs):
            calls["ensure_segment"] += 1
            return [{"status": "SHOULD_NOT_RUN"}]
        old_active, old_freeze, old_ensure = live_loop.ensure_active_artifact, live_loop.segment_plan_freeze_state, live_loop.ensure_segment_betting_plans
        try:
            live_loop.ensure_active_artifact = fake_active
            live_loop.segment_plan_freeze_state = fake_freeze
            live_loop.ensure_segment_betting_plans = fake_ensure
            out = live_loop.run_once(Namespace(
                db=db_path,
                issue="99130",
                timeout=1,
                publish_v4_2=False,
                v4_2_artifact_version=[],
                max_refresh_age_minutes=90.0,
                ensure_segment_betting_plans=True,
                segment_plan_scope=[],
                segment_plan_dir=plan_dir,
                structured_shadow_dir=source_dir,
            ))
        finally:
            live_loop.ensure_active_artifact = old_active
            live_loop.segment_plan_freeze_state = old_freeze
            live_loop.ensure_segment_betting_plans = old_ensure
        assert calls["ensure_segment"] == 0
        assert out["segment_betting_plans"][0]["status"] == "skipped_frozen"

        print(json.dumps({
            "freeze_state": freeze_state,
            "active_status": active_payload["availability_status"],
            "active_selected": active_payload["selected_plan_id"],
            "active_freeze_reason": active_payload["artifact_status"]["freeze_info"]["reason"],
            "late_status": late_payload["availability_status"],
            "late_reason": late_payload["unavailable_reason"],
            "live_loop_segment_generator_calls": calls["ensure_segment"],
            "live_loop_segment_status": out["segment_betting_plans"][0]["status"],
        }, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
