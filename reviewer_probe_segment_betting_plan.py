from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from src.decision_api import app as appmod


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def selected_summary(payload: dict) -> dict:
    return {
        "status": payload.get("availability_status"),
        "selected_plan_id": payload.get("selected_plan_id"),
        "requested_scope": payload.get("requested_planning_scope"),
        "planning_scope": payload.get("planning_scope"),
        "requested_decision_time": payload.get("requested_decision_time"),
        "decision_time": payload.get("decision_time"),
        "betting_strategy_version": payload.get("betting_strategy_version"),
        "artifact_schema_version": payload.get("artifact_schema_version"),
        "sp_drift_risk": payload.get("sp_drift_risk"),
        "available_segments": payload.get("available_segments"),
        "segments_len": len(payload.get("segments") or []),
        "bundles_len": len(payload.get("bundles") or []),
        "segment_seeds": sorted({row.get("sample_seed") for row in (payload.get("segments") or [])}),
        "bundle_seeds": sorted({row.get("sample_seed") for row in (payload.get("bundles") or [])}),
        "seed_summary_len": len(payload.get("seed_summaries") or []),
        "segment_seed_summary_len": len(payload.get("segment_seed_summary") or []),
    }


def live_artifact_checks() -> list[dict]:
    variants = [
        "shadow_v3.3.3",
        "shadow_v4.2.0000_execution_late_proxy_fullcap2",
        "shadow_v4.2.0005_execution_late_proxy_fullcap2",
    ]
    scopes = ["next_segment", "remaining_issue"]
    results = []
    for variant in variants:
        for scope in scopes:
            payload, status = appmod._segment_betting_plan_payload(
                "26072",
                decision_variant_id=variant,
                planning_scope=scope,
            )
            row = selected_summary(payload)
            row.update({"http_status": status, "variant": variant, "scope": scope})
            row["primary_seed_only"] = (
                row["segments_len"] == 0
                or row["segment_seeds"] == [payload.get("settings", {}).get("sample_seed")]
            ) and (
                row["bundles_len"] == 0
                or row["bundle_seeds"] == [payload.get("settings", {}).get("sample_seed")]
            )
            row["scope_matches_request"] = row["planning_scope"] == scope
            row["v02"] = row["betting_strategy_version"] == "segment_betting_v0.2.0000"
            if scope == "remaining_issue":
                row["drift_accepted"] = bool((row["sp_drift_risk"] or {}).get("accepted"))
            results.append(row)
    return results


def fallback_checks() -> dict:
    with tempfile.TemporaryDirectory(prefix="segment-plan-scope-probe-") as tmp:
        root = Path(tmp)
        legacy = root / "99999_v3.3.3_b1000_seed1"
        legacy.mkdir(parents=True)
        (legacy / "segment_betting_plan_summary.json").write_text(json.dumps({
            "issue": "99999",
            "label": "v3.3.3 legacy no scope",
            "strategy_family": "segment_betting_plan",
            "betting_strategy_version": "segment_betting_v0.1.0000",
            "artifact_schema_version": "segment_betting_artifact_v1",
            "settings": {"sample_seed": 1, "segment_budget_yuan": 1000},
            "summary": {"segments": 1, "selected_bundles": 1, "selected_cost_yuan": 2, "profit_yuan": 0, "roi": 0},
        }), encoding="utf-8")
        write_csv(legacy / "segment_betting_plan_segments.csv", [{
            "sample_seed": 1,
            "segment_idx": 1,
            "segment_start": "2026-07-07 10:00",
            "segment_end": "2026-07-07 22:00",
            "recommended_n": 3,
            "dead_segment": 0,
        }])
        write_csv(legacy / "segment_betting_plan_bundles.csv", [{
            "sample_seed": 1,
            "segment_idx": 1,
            "bundle_idx": 1,
            "n_value": 3,
            "leg_codes": "3|1|0",
            "widths": "1,1,1",
            "realized_hit": 0,
        }])
        release = {"artifacts": {"segment_betting_plan_dir": str(root)}}
        next_payload, _ = appmod._segment_betting_plan_payload(
            "99999", decision_variant_id="shadow_v3.3.3", planning_scope="next_segment", release=release
        )
        remaining_payload, _ = appmod._segment_betting_plan_payload(
            "99999", decision_variant_id="shadow_v3.3.3", planning_scope="remaining_issue", release=release
        )
        timed_payload, _ = appmod._segment_betting_plan_payload(
            "99999", decision_variant_id="shadow_v3.3.3", decision_time="2026-07-07 16:00", release=release
        )
        return {
            "next_segment_with_only_legacy_no_scope": selected_summary(next_payload),
            "remaining_issue_with_only_legacy_no_scope": selected_summary(remaining_payload),
            "explicit_decision_time_with_only_legacy_no_time": selected_summary(timed_payload),
        }


if __name__ == "__main__":
    print(json.dumps({
        "live_26072": live_artifact_checks(),
        "fallback": fallback_checks(),
    }, ensure_ascii=False, indent=2, sort_keys=True))
