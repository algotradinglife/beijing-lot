from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.decision_api import app as appmod


def test_phase3_forward_summary_is_exposed_as_read_only(monkeypatch, tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({
        "experiment_id": "phase3_drop_switched_ev_home_protection",
        "experiment_version": "v0.1.0000",
        "status": "collecting",
        "execution_enabled": False,
        "sampled_rows": 12,
        "trigger_count": 3,
        "trigger_issue_count": 2,
        "settled_trigger_count": 1,
        "lost_rescues": 0,
        "coverage_delta": -0.01,
        "depth_delta": -0.08,
        "profit_delta": 2.5,
        "gates": {"issues": False, "execution_disabled": True},
        "thresholds": {"min_issues": 5},
    }), encoding="utf-8")
    monkeypatch.setattr(appmod, "PHASE3_PROTECTION_FORWARD_SUMMARY", summary_path)

    payload = appmod._phase3_protection_forward_public()

    assert payload is not None
    assert payload["experiment_id"] == "phase3_drop_switched_ev_home_protection"
    assert payload["execution_enabled"] is False
    assert payload["sampled_rows"] == 12
    assert payload["gates"]["execution_disabled"] is True


def test_phase3_monitor_alerts_are_namespaced_for_operations(monkeypatch, tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({
        "alerts": [{
            "code": "execution_enabled",
            "severity": "bad",
            "label": "执行标志误开",
            "detail": "matches=[43]",
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(appmod, "PHASE3_PROTECTION_FORWARD_SUMMARY", summary_path)

    warnings = appmod._phase3_forward_monitor_warnings("26074", "26074", 10)

    assert len(warnings) == 1
    assert warnings[0]["code"] == "phase3_forward_execution_enabled"
    assert warnings[0]["severity"] == "bad"


def test_checkpoint_alerts_are_namespaced_for_operations(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "forward"
    path = root / "26074" / "checkpoint_health.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "alerts": [{
            "code": "sla_overdue",
            "severity": "bad",
            "label": "segment #3 T2H 刷新超时",
            "detail": "deadline=16:30",
        }],
    }), encoding="utf-8")
    monkeypatch.setattr(appmod, "SEGMENT_CHECKPOINT_HEALTH_ROOT", root)

    warnings = appmod._segment_checkpoint_monitor_warnings("26074", "26074", 10)

    assert len(warnings) == 1
    assert warnings[0]["code"] == "segment_checkpoint_sla_overdue"
    assert warnings[0]["severity"] == "bad"
