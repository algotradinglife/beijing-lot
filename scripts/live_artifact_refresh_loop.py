#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.publish_v4_2_execution_artifacts import (  # noqa: E402
    DEFAULT_SHADOW_DIR,
    DEFAULT_WORK_DIR,
    run as publish_v4_2_execution_artifacts,
)
from scripts.verify_exact_n_freeze import (  # noqa: E402
    verify_directory as verify_exact_n_directory,
)
from scripts.estimate_segment_betting_plan import (  # noqa: E402
    BETTING_STRATEGY_VERSION as SEGMENT_BETTING_STRATEGY_VERSION,
    DEFAULT_OUTPUT_DIR as DEFAULT_SEGMENT_BETTING_PLAN_DIR,
    parse_args as parse_segment_betting_plan_args,
    run as estimate_segment_betting_plan,
)
from src.decision_api import app as decision_app  # noqa: E402
from src.natural_day_manifest import (  # noqa: E402
    NaturalDayManifestError,
    load_published_manifest,
    verify_operational_windows,
)
from src.segment_recovery import (  # noqa: E402
    PUBLICATION_TABLE as RECOVERY_PUBLICATION_TABLE,
    SegmentRecoveryError,
    load_exact_terminal_record,
    load_published_recovery,
    publish_exact_terminal_record,
    recovery_exact_event_key,
    recovery_exact_terminal_path,
    verify_operational_window as verify_recovery_operational_window,
)
from src.structured_input_receipt import receipt_path, verify_receipt  # noqa: E402


DEFAULT_INTERVAL_SEC = 300.0
DEFAULT_V4_2_ARTIFACT_VERSIONS = ("v4.2.0005", "v4.2.0000")
DEFAULT_SEGMENT_PLAN_SCOPES = ("by_segment", "entire_issue")
DEFAULT_SEGMENT_PLAN_STAKE_MODE = "scale_to_budget"
DEFAULT_SEGMENT_PLAN_BUDGET_YUAN = 1000.0
DEFAULT_EXACT_N_OUTPUT_ROOT = ROOT / "results/exact_n_segment_freeze"
DEFAULT_EXACT_N_LEDGER_ROOT = ROOT / "results/research/exact_n_segment_freeze_v1/ledger"
DEFAULT_CORRECT_SCORE_ROOT = ROOT / "results/data_collection/correct_score_price_history_v1"
DEFAULT_EXACT_N_TRIGGER_LEAD_MINUTES = 10.0
DEFAULT_FINAL_INPUT_REFRESH_LEAD_MINUTES = 30.0
DEFAULT_RECOVERY_OUTPUT_ROOT = ROOT / "results/research/segment_recovery_v1"


def coordinate_segment_recovery(
    db_path: Path,
    issue: str,
    *,
    parent_segment_idx: int,
    output_root: Path = DEFAULT_RECOVERY_OUTPUT_ROOT,
    exact_ledger_root: Path = DEFAULT_EXACT_N_LEDGER_ROOT,
    hard_stop_hkt: str = "",
) -> dict[str, Any]:
    """Invoke the one-shot wall-clock publisher; it owns idempotency."""
    command = [
        sys.executable,
        str(ROOT / "scripts/publish_segment_recovery.py"),
        "--issue",
        str(issue),
        "--parent-segment",
        str(parent_segment_idx),
        "--db",
        str(db_path),
        "--output-root",
        str(output_root),
        "--exact-ledger-root",
        str(exact_ledger_root),
    ]
    if hard_stop_hkt:
        command.extend(["--hard-stop-hkt", hard_stop_hkt])
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        return {
            "status": "failed_closed_recovery_publish",
            "parent_segment_idx": int(parent_segment_idx),
            "error": (completed.stderr or completed.stdout).strip(),
        }
    try:
        receipt = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "status": "failed_closed_invalid_recovery_receipt",
            "parent_segment_idx": int(parent_segment_idx),
            "stdout": completed.stdout.strip(),
        }
    return receipt


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _status_complete(status: dict[str, Any]) -> bool:
    completeness = status.get("completeness") if isinstance(status.get("completeness"), dict) else {}
    snapshots = status.get("snapshot_completeness") if isinstance(status.get("snapshot_completeness"), dict) else {}
    return (
        status.get("status") == "available"
        and bool(completeness.get("complete"))
        and bool(snapshots.get("complete"))
    )


def _small_status(status: dict[str, Any]) -> dict[str, Any]:
    completeness = status.get("completeness") if isinstance(status.get("completeness"), dict) else {}
    snapshots = status.get("snapshot_completeness") if isinstance(status.get("snapshot_completeness"), dict) else {}
    return {
        "status": status.get("status", ""),
        "message": status.get("message", ""),
        "source_path": status.get("source_path", ""),
        "row_count": status.get("row_count", 0),
        "expected_match_count": status.get("expected_match_count", 0),
        "missing_match_idx": completeness.get("missing_match_idx", []),
        "snapshot_missing_match_idx": snapshots.get("missing_match_idx", []),
    }


def ensure_active_artifact(
    db_path: Path,
    issue: str,
    *,
    timeout_sec: int,
    force_refresh: bool = False,
) -> dict[str, Any]:
    with decision_app._connect(db_path) as conn:
        resolved = decision_app._resolve_issue(conn, issue)
        before = decision_app._decision_artifact_status_payload(
            conn,
            resolved,
            variant_id=decision_app.STABLE_DECISION_VARIANT_ID,
        )
        if _status_complete(before) and not force_refresh:
            return {
                "issue": resolved,
                "action": "active_artifact_already_available",
                "artifact_status": _small_status(before),
            }

        materialize = decision_app._materialize_issue_decision_snapshots(conn, resolved, only_date=None)
        conn.commit()
        completeness = materialize.get("completeness") if isinstance(materialize.get("completeness"), dict) else {}
        if not completeness.get("complete"):
            return {
                "issue": resolved,
                "action": "skipped_active_snapshot_incomplete",
                "materialize": {
                    "count": materialize.get("count", 0),
                    "actions": materialize.get("actions", {}),
                    "completeness": completeness,
                },
                "artifact_status": _small_status(before),
            }

        generated = decision_app._run_decision_artifact_generator(
            conn,
            db_path,
            resolved,
            variant_id=decision_app.STABLE_DECISION_VARIANT_ID,
            materialize_snapshots=False,
            strict_completeness=True,
            timeout_sec=timeout_sec,
        )
        conn.commit()
        return {
            "issue": resolved,
            "action": (
                "refreshed_active_artifact_for_target_segment"
                if force_refresh
                else "generated_active_artifact"
            ),
            "materialize": {
                "count": materialize.get("count", 0),
                "actions": materialize.get("actions", {}),
                "completeness": completeness,
            },
            "artifact_status": _small_status(generated.get("artifact_status", {})),
        }


def publish_v4_2_artifacts(
    db_path: Path,
    issue: str,
    *,
    max_refresh_age_minutes: float,
    artifact_versions: list[str],
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for version in artifact_versions:
        summary = publish_v4_2_execution_artifacts(
            issue=issue,
            db_path=db_path,
            shadow_dir=DEFAULT_SHADOW_DIR,
            work_dir=DEFAULT_WORK_DIR,
            artifact_version_id=version,
            max_refresh_age_minutes=max_refresh_age_minutes,
        )
        outputs.append({
            "artifact_version_id": summary.get("artifact_version_id", version),
            "status": summary.get("status", ""),
            "late_proxy_published": summary.get("late_proxy_published", False),
            "late_refresh": summary.get("late_refresh", {}),
            "outputs": {
                key: {
                    "shadow_arm": value.get("shadow_arm", ""),
                    "rows": value.get("rows", 0),
                    "output_csv": value.get("output_csv", ""),
                }
                for key, value in (summary.get("outputs") or {}).items()
                if isinstance(value, dict)
            },
        })
    return outputs


def segment_plan_freeze_state(
    db_path: Path,
    issue: str,
    *,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    try:
        with decision_app._connect(db_path) as conn:
            resolved = decision_app._resolve_issue(conn, issue)
            return decision_app._segment_plan_freeze_state(
                conn, resolved, observed_at=observed_at
            )
    except Exception as exc:
        return {
            "policy": "next_unfrozen_published_segment",
            "issue": str(issue),
            "locked": False,
            "reason": f"freeze_state_unavailable:{type(exc).__name__}",
            "error": str(exc),
        }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_project_path(value: Any) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _segment_plan_label_from_structured_csv(path: Path) -> str:
    parent = path.parent.name
    if "shadow_v3.3.3" in parent:
        return "v3.3.3"
    match = re.search(r"shadow_(v4\.2\.(?:0004|0005))_execution_late_proxy", parent)
    return f"{match.group(1)}_late_proxy" if match else ""


def _segment_plan_specs_from_existing(issue: str, *, plan_dir: Path, structured_dir: Path) -> list[dict[str, Any]]:
    specs: dict[tuple[str, str, str], dict[str, Any]] = {}
    for summary_path in sorted(plan_dir.glob(f"{issue}_*/segment_betting_plan_summary.json")):
        payload = _read_json(summary_path)
        if not payload:
            continue
        settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
        structured_csv = _resolve_project_path(payload.get("structured_csv"))
        if not structured_csv.is_file():
            continue
        label = str(payload.get("label") or "")
        if not label:
            continue
        stake_mode = str(settings.get("stake_mode") or DEFAULT_SEGMENT_PLAN_STAKE_MODE)
        if stake_mode != DEFAULT_SEGMENT_PLAN_STAKE_MODE:
            continue
        version = SEGMENT_BETTING_STRATEGY_VERSION
        key = (label, version, str(structured_csv))
        specs[key] = {
            "label": label,
            "structured_csv": structured_csv,
            "arm": str(payload.get("arm") or "shadow"),
            "betting_strategy_version": version,
            "stake_mode": stake_mode,
            "segment_budget_yuan": _as_float(settings.get("segment_budget_yuan"), DEFAULT_SEGMENT_PLAN_BUDGET_YUAN),
            "stake_yuan_per_ticket": _as_float(settings.get("stake_yuan_per_ticket"), 2.0),
            "window_hours": _as_float(settings.get("window_hours"), 12.0),
            "extend_hours": str(settings.get("extend_hours") or "18,24,36"),
            "min_matches": _as_int(settings.get("min_matches"), 6),
            "max_matches": _as_int(settings.get("max_matches"), 24),
            "sample_attempts": _as_int(settings.get("sample_attempts"), 12000),
            "sample_seed": _as_int(settings.get("sample_seed"), 20260707),
            "seed_count": _as_int(settings.get("seed_count"), 10),
            "sample_seeds": settings.get("sample_seeds") if isinstance(settings.get("sample_seeds"), list) else [],
            "min_n": _as_int(settings.get("min_n"), 3),
            "max_n": _as_int(settings.get("max_n"), 8),
            "max_bundle_spend_pct": _as_float(settings.get("max_bundle_spend_pct"), 0.4),
            "max_overlap": settings.get("max_overlap"),
            "allow_negative_ev": not bool(settings.get("positive_ev_only", True)),
            "decision_time": str(settings.get("decision_time") or payload.get("decision_time") or ""),
        }

    for structured_csv in sorted(structured_dir.glob(f"{issue}_*/structured_shadow_{issue}.csv")):
        structured_csv = structured_csv.resolve()
        label = _segment_plan_label_from_structured_csv(structured_csv)
        if not label:
            continue
        key = (label, SEGMENT_BETTING_STRATEGY_VERSION, str(structured_csv))
        specs.setdefault(key, {
            "label": label,
            "structured_csv": structured_csv,
            "arm": "shadow",
            "betting_strategy_version": SEGMENT_BETTING_STRATEGY_VERSION,
            "stake_mode": DEFAULT_SEGMENT_PLAN_STAKE_MODE,
            "segment_budget_yuan": DEFAULT_SEGMENT_PLAN_BUDGET_YUAN,
            "stake_yuan_per_ticket": 2.0,
            "window_hours": 12.0,
            "extend_hours": "18,24,36",
            "min_matches": 6,
            "max_matches": 24,
            "sample_attempts": 12000,
            "sample_seed": 20260707,
            "seed_count": 10,
            "sample_seeds": [],
            "min_n": 3,
            "max_n": 8,
            "max_bundle_spend_pct": 0.4,
            "max_overlap": None,
            "allow_negative_ev": False,
            "decision_time": "",
        })
    return sorted(specs.values(), key=lambda item: (str(item.get("label") or ""), str(item.get("structured_csv") or "")))


def _segment_plan_exists(
    issue: str,
    spec: dict[str, Any],
    *,
    scope: str,
    plan_dir: Path,
    segment_manifest_sha256: str = "",
) -> bool:
    for summary_path in sorted(plan_dir.glob(f"{issue}_*/segment_betting_plan_summary.json")):
        payload = _read_json(summary_path)
        if not payload:
            continue
        settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
        if str(payload.get("label") or "") != str(spec.get("label") or ""):
            continue
        if str(payload.get("betting_strategy_version") or settings.get("betting_strategy_version") or "") != str(spec.get("betting_strategy_version") or ""):
            continue
        if _resolve_project_path(payload.get("structured_csv")) != _resolve_project_path(spec.get("structured_csv")):
            continue
        structured_path = _resolve_project_path(spec.get("structured_csv"))
        if not structured_path.is_file():
            continue
        if str(payload.get("structured_csv_sha256") or "") != hashlib.sha256(
            structured_path.read_bytes()
        ).hexdigest():
            continue
        if str(payload.get("planning_scope") or settings.get("planning_scope") or "") != scope:
            continue
        if (
            scope == "by_segment"
            and segment_manifest_sha256
            and str(payload.get("segment_manifest_sha256") or "")
            != segment_manifest_sha256
        ):
            continue
        if str(settings.get("stake_mode") or "") != str(spec.get("stake_mode") or ""):
            continue
        if _as_float(settings.get("segment_budget_yuan"), 0.0) != _as_float(spec.get("segment_budget_yuan"), 0.0):
            continue
        if not (summary_path.parent / "segment_betting_plan_segments.csv").is_file():
            continue
        if not (summary_path.parent / "segment_betting_plan_bundles.csv").is_file():
            continue
        if scope == "by_segment" and _as_int(payload.get("segments"), 0) < _as_int(payload.get("available_segments"), 0):
            continue
        return True
    return False


def _run_segment_plan(
    db_path: Path,
    issue: str,
    spec: dict[str, Any],
    *,
    scope: str,
    plan_dir: Path,
) -> dict[str, Any]:
    argv = [
        "--issue", issue,
        "--structured-csv", str(spec["structured_csv"]),
        "--label", str(spec["label"]),
        "--betting-strategy-version", str(spec["betting_strategy_version"]),
        "--arm", str(spec.get("arm") or "shadow"),
        "--planning-scope", scope,
        "--stake-mode", str(spec.get("stake_mode") or DEFAULT_SEGMENT_PLAN_STAKE_MODE),
        "--db", str(db_path),
        "--output-dir", str(plan_dir),
        "--window-hours", str(spec.get("window_hours") or 12.0),
        "--extend-hours", str(spec.get("extend_hours") or "18,24,36"),
        "--min-matches", str(spec.get("min_matches") or 6),
        "--max-matches", str(spec.get("max_matches") or 24),
        "--segment-budget-yuan", str(spec.get("segment_budget_yuan") or DEFAULT_SEGMENT_PLAN_BUDGET_YUAN),
        "--stake-yuan-per-ticket", str(spec.get("stake_yuan_per_ticket") or 2.0),
        "--sample-attempts", str(spec.get("sample_attempts") or 12000),
        "--sample-seed", str(spec.get("sample_seed") or 20260707),
        "--seed-count", str(spec.get("seed_count") or 10),
        "--min-n", str(spec.get("min_n") or 3),
        "--max-n", str(spec.get("max_n") or 8),
        "--max-bundle-spend-pct", str(spec.get("max_bundle_spend_pct") or 0.4),
    ]
    if spec.get("decision_time"):
        argv.extend(["--decision-time", str(spec["decision_time"])])
    sample_seeds = spec.get("sample_seeds")
    if isinstance(sample_seeds, list) and sample_seeds:
        argv.extend(["--sample-seeds", ",".join(str(seed) for seed in sample_seeds)])
    if spec.get("max_overlap") is not None:
        argv.extend(["--max-overlap", str(spec["max_overlap"])])
    if spec.get("allow_negative_ev"):
        argv.append("--allow-negative-ev")
    payload = estimate_segment_betting_plan(parse_segment_betting_plan_args(argv))
    return {
        "label": payload.get("label", spec.get("label", "")),
        "planning_scope": payload.get("planning_scope", scope),
        "segments": payload.get("segments", 0),
        "available_segments": payload.get("available_segments", 0),
        "selected_bundles": (payload.get("summary") or {}).get("selected_bundles", 0)
        if isinstance(payload.get("summary"), dict) else 0,
        "summary_json": payload.get("summary_json", ""),
    }


def ensure_segment_betting_plans(
    db_path: Path,
    issue: str,
    *,
    scopes: list[str],
    plan_dir: Path = DEFAULT_SEGMENT_BETTING_PLAN_DIR,
    structured_dir: Path = DEFAULT_SHADOW_DIR,
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    segment_manifest_sha256 = ""
    try:
        with decision_app._connect(db_path) as conn:
            manifest = load_published_manifest(conn, issue)
            if manifest is not None:
                verify_operational_windows(conn, manifest)
                segment_manifest_sha256 = str(manifest["manifest_sha256"])
            elif "by_segment" in scopes:
                return [{
                    "status": "failed_closed_missing_published_segment_contract",
                    "planning_scope": "by_segment",
                    "error": (
                        "operational by_segment generation requires the canonical "
                        "BJ-SEG-DAY-001 publication"
                    ),
                }]
    except NaturalDayManifestError as exc:
        return [{
            "status": "failed_closed_segment_contract",
            "planning_scope": ",".join(scopes),
            "error": str(exc),
        }]
    specs = _segment_plan_specs_from_existing(issue, plan_dir=plan_dir, structured_dir=structured_dir)
    for spec in specs:
        for scope in scopes:
            if _segment_plan_exists(
                issue,
                spec,
                scope=scope,
                plan_dir=plan_dir,
                segment_manifest_sha256=segment_manifest_sha256,
            ):
                outputs.append({
                    "label": spec.get("label", ""),
                    "planning_scope": scope,
                    "status": "already_available",
                    "segment_manifest_sha256": segment_manifest_sha256,
                })
                continue
            try:
                generated = _run_segment_plan(db_path, issue, spec, scope=scope, plan_dir=plan_dir)
                outputs.append({
                    "status": "generated",
                    "segment_manifest_sha256": segment_manifest_sha256,
                    **generated,
                })
            except Exception as exc:
                outputs.append({
                    "label": spec.get("label", ""),
                    "planning_scope": scope,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                })
    if not specs:
        outputs.append({"status": "skipped_no_structured_artifacts", "planning_scope": ",".join(scopes)})
    return outputs


def coordinate_due_exact_n_freeze(
    db_path: Path,
    issue: str,
    *,
    structured_csv: Path,
    now: datetime | None = None,
    trigger_lead_minutes: float = DEFAULT_EXACT_N_TRIGGER_LEAD_MINUTES,
    output_root: Path = DEFAULT_EXACT_N_OUTPUT_ROOT,
    ledger_root: Path = DEFAULT_EXACT_N_LEDGER_ROOT,
    correct_score_root: Path = DEFAULT_CORRECT_SCORE_ROOT,
) -> dict[str, Any]:
    """Publish one due segment through the same canonical manifest as all consumers."""
    observed_at = (now or datetime.now(timezone.utc)).astimezone()
    try:
        with decision_app._connect(db_path) as conn:
            manifest = load_published_manifest(conn, issue)
            if manifest is None:
                return {"status": "skipped_no_published_segment_contract"}
            verify_operational_windows(conn, manifest)
            recovery_segments: list[dict[str, Any]] = []
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (RECOVERY_PUBLICATION_TABLE,),
            ).fetchone() is not None:
                parent_rows = conn.execute(
                    f"""
                    SELECT parent_segment_idx
                    FROM {RECOVERY_PUBLICATION_TABLE}
                    WHERE issue=?
                    ORDER BY parent_segment_idx
                    """,
                    (str(issue),),
                ).fetchall()
                for row in parent_rows:
                    recovery = load_published_recovery(
                        conn, str(issue), int(row[0])
                    )
                    if recovery is None:
                        continue
                    verify_recovery_operational_window(conn, recovery)
                    if recovery["status"] != "PUBLISHED_RECOVERY":
                        continue
                    recovery_segments.append(
                        {
                            "segment_idx": int(recovery["parent_segment_idx"]),
                            "segment_identity": str(recovery["child_identity"]),
                            "match_indices": [
                                int(item["match_idx"])
                                for item in recovery["included"]
                            ],
                            "match_count": int(recovery["included_match_count"]),
                            "freeze_at": str(recovery["recovery_freeze_at"]),
                            "_manifest_sha256": str(
                                recovery["manifest_sha256"]
                            ),
                            "_manifest_path": str(recovery["manifest_path"]),
                            "_is_recovery": True,
                            "_recovery_contract": recovery,
                        }
                    )
    except NaturalDayManifestError as exc:
        return {"status": "failed_closed_segment_contract", "error": str(exc)}
    except SegmentRecoveryError as exc:
        return {"status": "failed_closed_recovery_contract", "error": str(exc)}
    all_segments = [
        {
            **segment,
            "segment_identity": f"segment_{int(segment['segment_idx'])}",
            "_manifest_sha256": str(manifest["manifest_sha256"]),
            "_manifest_path": str(manifest["manifest_path"]),
            "_is_recovery": False,
        }
        for segment in manifest["segments"]
    ] + recovery_segments
    past_due_recoveries = sorted(
        (
            (
                datetime.fromisoformat(str(segment["freeze_at"])),
                segment,
            )
            for segment in recovery_segments
            if datetime.fromisoformat(str(segment["freeze_at"])) < observed_at
        ),
        key=lambda item: item[0],
    )
    for _past_freeze, segment in past_due_recoveries:
        event_key = recovery_exact_event_key(
            str(issue), str(segment["segment_identity"])
        )
        ledger_path = ledger_root / f"{event_key}.json"
        try:
            existing_terminal = load_exact_terminal_record(
                ledger_root, segment["_recovery_contract"]
            )
        except SegmentRecoveryError as exc:
            return {
                "status": "failed_closed_recovery_terminal",
                "segment_idx": int(segment["segment_idx"]),
                "segment_identity": str(segment["segment_identity"]),
                "error": str(exc),
            }
        if ledger_path.is_file():
            try:
                ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                ledger = {}
            if ledger.get("state") == "PUBLISHED":
                if existing_terminal is not None:
                    return {
                        "status": "failed_closed_conflicting_terminal_event",
                        "segment_idx": int(segment["segment_idx"]),
                        "segment_identity": str(
                            segment["segment_identity"]
                        ),
                        "event_key": event_key,
                    }
                try:
                    artifact_manifest = Path(str(ledger["artifact_manifest"]))
                    verification = verify_exact_n_directory(
                        artifact_manifest.parent
                    )
                    if (
                        verification.get("status") != "PASS"
                        or ledger.get("package_verification") != verification
                        or ledger.get("artifact_manifest_sha256")
                        != verification.get("artifact_manifest_sha256")
                        or ledger.get("package_sha256s_sha256")
                        != verification.get("package_sha256s_sha256")
                        or str(ledger.get("event_key") or "") != event_key
                        or str(ledger.get("segment_manifest_sha256") or "")
                        != str(segment["_manifest_sha256"])
                    ):
                        raise ValueError(
                            "past-due PUBLISHED ledger verification mismatch"
                        )
                except (
                    OSError,
                    KeyError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ) as exc:
                    return {
                        "status": "failed_closed_invalid_ledger",
                        "segment_idx": int(segment["segment_idx"]),
                        "segment_identity": str(
                            segment["segment_identity"]
                        ),
                        "error": (
                            "past-due published package verification failed: "
                            f"{exc}"
                        ),
                    }
                return {
                    "status": "already_published",
                    "segment_idx": int(segment["segment_idx"]),
                    "segment_identity": str(segment["segment_identity"]),
                    "event_key": event_key,
                    "segment_manifest_sha256": str(
                        segment["_manifest_sha256"]
                    ),
                    "verification": verification,
                }
        try:
            terminal, idempotent = publish_exact_terminal_record(
                ledger_root,
                segment["_recovery_contract"],
                observed_at=observed_at,
            )
        except SegmentRecoveryError as exc:
            return {
                "status": "failed_closed_recovery_terminal",
                "segment_idx": int(segment["segment_idx"]),
                "segment_identity": str(segment["segment_identity"]),
                "error": str(exc),
            }
        return {
            "status": "MISSED_RECOVERY_FREEZE",
            "segment_idx": int(segment["segment_idx"]),
            "segment_identity": str(segment["segment_identity"]),
            "event_key": event_key,
            "terminal_receipt": str(
                recovery_exact_terminal_path(
                    ledger_root,
                    str(issue),
                    str(segment["segment_identity"]),
                )
            ),
            "terminal_receipt_sha256": str(
                terminal["terminal_receipt_sha256"]
            ),
            "idempotent": idempotent,
            "exact_n_cells": terminal["exact_n_cells"],
            "correct_score_budget_statuses": terminal[
                "correct_score_budget_statuses"
            ],
        }
    if not structured_csv.is_file():
        return {
            "status": "failed_closed_structured_input_missing",
            "structured_csv": str(structured_csv),
        }

    upcoming: list[tuple[datetime, dict[str, Any]]] = []
    for segment in all_segments:
        freeze_at = datetime.fromisoformat(str(segment["freeze_at"]))
        if freeze_at.tzinfo is None:
            freeze_at = freeze_at.astimezone()
        if freeze_at - timedelta(minutes=trigger_lead_minutes) <= observed_at <= freeze_at:
            upcoming.append((freeze_at, segment))
    if not upcoming:
        future = sorted(
            datetime.fromisoformat(str(segment["freeze_at"]))
            for segment in all_segments
            if datetime.fromisoformat(str(segment["freeze_at"])) > observed_at
        )
        return {
            "status": "pending",
            "next_freeze_at": (
                future[0].isoformat(timespec="seconds") if future else ""
            ),
            "segment_manifest_sha256": str(manifest["manifest_sha256"]),
        }

    _freeze_at, segment = min(upcoming, key=lambda item: item[0])
    source_receipt_path = receipt_path(structured_csv)
    try:
        source_receipt = verify_receipt(
            structured_csv, source_receipt_path, issue=str(issue)
        )
        input_generated_at = source_receipt["generated_at"].astimezone(
            _freeze_at.tzinfo
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "failed_closed_invalid_structured_input_receipt",
            "segment_idx": int(segment["segment_idx"]),
            "structured_csv": str(structured_csv),
            "input_receipt": str(source_receipt_path),
            "error": str(exc),
        }
    final_refresh_opens_at = _freeze_at - timedelta(
        minutes=DEFAULT_FINAL_INPUT_REFRESH_LEAD_MINUTES
    )
    if not (final_refresh_opens_at <= input_generated_at <= observed_at <= _freeze_at):
        return {
            "status": "failed_closed_stale_segment_input",
            "segment_idx": int(segment["segment_idx"]),
            "structured_csv": str(structured_csv),
            "input_generated_at": input_generated_at.isoformat(timespec="seconds"),
            "final_refresh_opens_at": final_refresh_opens_at.isoformat(timespec="seconds"),
            "effective_decision_at": observed_at.isoformat(timespec="seconds"),
            "freeze_at": _freeze_at.isoformat(timespec="seconds"),
        }
    event_key = hashlib.sha256(
        json.dumps(
            (
                {
                    "issue": str(issue),
                    "segment_identity": str(segment["segment_identity"]),
                }
                if segment["_is_recovery"]
                else {"issue": str(issue), "segment_idx": int(segment["segment_idx"])}
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    ledger_path = ledger_root / f"{event_key}.json"
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "status": "failed_closed_invalid_ledger",
                "segment_idx": int(segment["segment_idx"]),
                "error": str(exc),
            }
        if (
            ledger.get("state") == "PUBLISHED"
            and str(ledger.get("segment_manifest_sha256") or "")
            == str(segment["_manifest_sha256"])
            and Path(str(ledger.get("artifact_manifest") or "")).is_file()
        ):
            try:
                artifact_manifest = Path(str(ledger["artifact_manifest"]))
                verification = verify_exact_n_directory(artifact_manifest.parent)
                if (
                    verification.get("status") == "PASS"
                    and ledger.get("package_verification") == verification
                    and ledger.get("artifact_manifest_sha256")
                    == verification.get("artifact_manifest_sha256")
                    and ledger.get("package_sha256s_sha256")
                    == verification.get("package_sha256s_sha256")
                ):
                    return {
                        "status": "already_published",
                        "segment_idx": int(segment["segment_idx"]),
                        "event_key": event_key,
                        "segment_identity": str(segment["segment_identity"]),
                        "segment_manifest_sha256": str(
                            segment["_manifest_sha256"]
                        ),
                        "verification": verification,
                    }
            except (
                OSError,
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                return {
                    "status": "failed_closed_invalid_ledger",
                    "segment_idx": int(segment["segment_idx"]),
                    "error": f"published package verification failed: {exc}",
                }
        return {
            "status": "failed_closed_existing_event_reservation",
            "segment_idx": int(segment["segment_idx"]),
            "event_key": event_key,
            "ledger_state": str(ledger.get("state") or ""),
        }
    command = [
        sys.executable,
        str(ROOT / "scripts/publish_exact_n_segment_freeze.py"),
        "--issue",
        str(issue),
        "--segment",
        str(segment["segment_idx"]),
        (
            "--recovery-manifest"
            if segment["_is_recovery"]
            else "--manifest"
        ),
        str(segment["_manifest_path"]),
        "--structured-csv",
        str(structured_csv),
        "--input-receipt",
        str(source_receipt_path),
        "--db",
        str(db_path),
        "--output-root",
        str(output_root),
        "--ledger-root",
        str(ledger_root),
        "--correct-score-root",
        str(correct_score_root),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "status": "failed_closed_publish",
            "segment_idx": int(segment["segment_idx"]),
            "returncode": completed.returncode,
            "error": (completed.stderr or completed.stdout).strip(),
        }
    try:
        receipt = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {
            "status": "failed_closed_invalid_receipt",
            "segment_idx": int(segment["segment_idx"]),
            "stdout": completed.stdout.strip(),
        }
    verification = (
        receipt.get("verification")
        if isinstance(receipt.get("verification"), dict)
        else {}
    )
    try:
        published_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "failed_closed_invalid_receipt",
            "segment_idx": int(segment["segment_idx"]),
            "error": f"published ledger unavailable: {exc}",
        }
    try:
        artifact_manifest = Path(
            str(published_ledger.get("artifact_manifest") or "")
        )
        coordinator_verification = verify_exact_n_directory(
            artifact_manifest.parent
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "failed_closed_invalid_receipt",
            "segment_idx": int(segment["segment_idx"]),
            "error": f"coordinator package verification failed: {exc}",
        }
    if (
        receipt.get("event_key") != event_key
        or verification.get("status") != "PASS"
        or published_ledger.get("state") != "PUBLISHED"
        or published_ledger.get("package_verification") != verification
        or coordinator_verification != verification
    ):
        return {
            "status": "failed_closed_invalid_receipt",
            "segment_idx": int(segment["segment_idx"]),
            "error": "publisher receipt is not bound to a verified PUBLISHED ledger",
        }
    return {
        "status": "published",
        "segment_idx": int(segment["segment_idx"]),
        "segment_identity": str(segment["segment_identity"]),
        "segment_manifest_sha256": str(segment["_manifest_sha256"]),
        "receipt": receipt,
    }


def run_once(args: argparse.Namespace) -> dict[str, Any]:
    observed_at = datetime.now(timezone.utc).astimezone()
    with decision_app._connect(args.db) as recovery_connection:
        recovery_issue = decision_app._resolve_issue(
            recovery_connection, str(args.issue)
        )
    recovery_parents = list(
        getattr(args, "recovery_parent_segment", [])
    )
    recovery_activation_issue = str(
        getattr(args, "recovery_issue", "") or ""
    )
    if recovery_parents and recovery_activation_issue != recovery_issue:
        segment_recoveries = [
            {
                "status": "skipped_recovery_activation_issue_mismatch",
                "activation_issue": recovery_activation_issue,
                "resolved_issue": recovery_issue,
                "parent_segment_idx": int(parent_segment_idx),
            }
            for parent_segment_idx in recovery_parents
        ]
    else:
        segment_recoveries = [
            coordinate_segment_recovery(
                args.db,
                recovery_issue,
                parent_segment_idx=int(parent_segment_idx),
                output_root=getattr(
                    args,
                    "recovery_output_root",
                    DEFAULT_RECOVERY_OUTPUT_ROOT,
                ),
                exact_ledger_root=getattr(
                    args,
                    "exact_n_ledger_root",
                    DEFAULT_EXACT_N_LEDGER_ROOT,
                ),
                hard_stop_hkt=str(
                    getattr(args, "recovery_hard_stop_hkt", "") or ""
                ),
            )
            for parent_segment_idx in recovery_parents
        ]
    segment_plan_freeze = segment_plan_freeze_state(
        args.db, args.issue, observed_at=observed_at
    )
    freeze_at_text = str(segment_plan_freeze.get("freeze_at") or "")
    freeze_at = datetime.fromisoformat(freeze_at_text) if freeze_at_text else None
    force_final_refresh = bool(
        freeze_at is not None
        and not segment_plan_freeze.get("locked")
        and freeze_at - timedelta(minutes=DEFAULT_FINAL_INPUT_REFRESH_LEAD_MINUTES)
        <= observed_at
        <= freeze_at
    )
    for recovery in segment_recoveries:
        recovery_freeze_text = str(recovery.get("freeze_at") or "")
        if not recovery_freeze_text:
            continue
        recovery_freeze = datetime.fromisoformat(recovery_freeze_text)
        if (
            recovery_freeze - timedelta(
                minutes=DEFAULT_FINAL_INPUT_REFRESH_LEAD_MINUTES
            )
            <= observed_at
            <= recovery_freeze
        ):
            force_final_refresh = True
    active = ensure_active_artifact(
        args.db,
        args.issue,
        timeout_sec=args.timeout,
        force_refresh=force_final_refresh,
    )
    issue = str(active.get("issue") or args.issue)
    status = active.get("artifact_status") if isinstance(active.get("artifact_status"), dict) else {}
    v4_2: list[dict[str, Any]] = []
    if status.get("status") == "available" and args.publish_v4_2:
        v4_2 = publish_v4_2_artifacts(
            args.db,
            issue,
            max_refresh_age_minutes=args.max_refresh_age_minutes,
            artifact_versions=args.v4_2_artifact_version,
        )
    if issue != str(args.issue):
        segment_plan_freeze = segment_plan_freeze_state(
            args.db, issue, observed_at=observed_at
        )
    segment_betting_plans: list[dict[str, Any]] = []
    if status.get("status") == "available" and args.ensure_segment_betting_plans:
        if segment_plan_freeze.get("locked"):
            segment_betting_plans = [{
                "status": "skipped_frozen",
                "reason": "all_published_segments_locked",
                "segment_idx": segment_plan_freeze.get("segment_idx"),
                "freeze_at": segment_plan_freeze.get("freeze_at", ""),
                "first_kickoff": segment_plan_freeze.get("first_kickoff", ""),
            }]
        else:
            scopes = args.segment_plan_scope or list(DEFAULT_SEGMENT_PLAN_SCOPES)
            segment_betting_plans = ensure_segment_betting_plans(
                args.db,
                issue,
                scopes=scopes,
                plan_dir=args.segment_plan_dir,
                structured_dir=args.structured_shadow_dir,
            )
    exact_n_freeze: dict[str, Any] = {"status": "disabled"}
    if status.get("status") == "available" and args.coordinate_exact_n_freeze:
        specs = _segment_plan_specs_from_existing(
            issue,
            plan_dir=args.segment_plan_dir,
            structured_dir=args.structured_shadow_dir,
        )
        stable_specs = [
            spec
            for spec in specs
            if str(spec.get("label") or "") == "v3.3.3"
            and Path(spec["structured_csv"]).is_file()
        ]
        preferred = max(
            stable_specs or specs,
            key=lambda spec: Path(spec["structured_csv"]).stat().st_mtime,
            default=None,
        )
        if preferred is None:
            exact_n_freeze = {"status": "skipped_no_structured_artifacts"}
        else:
            exact_n_freeze = coordinate_due_exact_n_freeze(
                args.db,
                issue,
                structured_csv=Path(preferred["structured_csv"]),
                trigger_lead_minutes=args.exact_n_trigger_lead_minutes,
                output_root=args.exact_n_output_root,
                ledger_root=args.exact_n_ledger_root,
                correct_score_root=args.correct_score_root,
            )
    return {
        "checked_at": now_iso(),
        "issue": issue,
        "active": active,
        "v4_2": v4_2,
        "segment_betting_plan_freeze": segment_plan_freeze,
        "segment_recoveries": segment_recoveries,
        "segment_betting_plans": segment_betting_plans,
        "exact_n_freeze": exact_n_freeze,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Maintain active decision artifacts and v4.2 execution artifacts for the current BJDC issue."
    )
    parser.add_argument("--db", type=Path, default=decision_app.DEFAULT_500_DB)
    parser.add_argument("--issue", default="current")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--max-refresh-age-minutes", type=float, default=90.0)
    parser.add_argument("--v4-2-artifact-version", action="append", default=list(DEFAULT_V4_2_ARTIFACT_VERSIONS))
    parser.add_argument("--no-publish-v4-2", action="store_false", dest="publish_v4_2", default=True)
    parser.add_argument("--no-segment-betting-plans", action="store_false", dest="ensure_segment_betting_plans", default=True)
    parser.add_argument("--segment-plan-scope", action="append", choices=DEFAULT_SEGMENT_PLAN_SCOPES, default=[])
    parser.add_argument("--segment-plan-dir", type=Path, default=DEFAULT_SEGMENT_BETTING_PLAN_DIR)
    parser.add_argument("--structured-shadow-dir", type=Path, default=DEFAULT_SHADOW_DIR)
    parser.add_argument("--no-coordinate-exact-n-freeze", action="store_false", dest="coordinate_exact_n_freeze", default=True)
    parser.add_argument("--exact-n-trigger-lead-minutes", type=float, default=DEFAULT_EXACT_N_TRIGGER_LEAD_MINUTES)
    parser.add_argument("--exact-n-output-root", type=Path, default=DEFAULT_EXACT_N_OUTPUT_ROOT)
    parser.add_argument("--exact-n-ledger-root", type=Path, default=DEFAULT_EXACT_N_LEDGER_ROOT)
    parser.add_argument("--correct-score-root", type=Path, default=DEFAULT_CORRECT_SCORE_ROOT)
    parser.add_argument(
        "--recovery-issue",
        default="",
        help=(
            "exact activated issue; prevents a persistent current-issue loop "
            "from applying recovery to a later issue"
        ),
    )
    parser.add_argument(
        "--recovery-parent-segment",
        type=int,
        action="append",
        default=[],
        help="explicitly activated parent; at most one immutable recovery is published",
    )
    parser.add_argument(
        "--recovery-output-root",
        type=Path,
        default=DEFAULT_RECOVERY_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--recovery-hard-stop-hkt",
        default="",
        help="activation-specific absolute cutoff for honest MISSED evidence",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    recovery_activation_fields = (
        bool(args.recovery_parent_segment),
        bool(args.recovery_issue),
        bool(args.recovery_hard_stop_hkt),
    )
    if any(recovery_activation_fields) and not all(
        recovery_activation_fields
    ):
        parser.error(
            "recovery activation requires --recovery-issue, "
            "--recovery-parent-segment, and --recovery-hard-stop-hkt together"
        )

    while True:
        started = time.monotonic()
        try:
            print(json.dumps(run_once(args), ensure_ascii=False, sort_keys=True), flush=True)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "checked_at": now_iso(),
                        "issue": args.issue,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )
        if args.once:
            return
        elapsed = time.monotonic() - started
        time.sleep(max(30.0, args.interval - elapsed))


if __name__ == "__main__":
    main()
