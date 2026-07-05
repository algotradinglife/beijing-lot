from __future__ import annotations

import csv
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, redirect, render_template_string, request, send_from_directory, session

from src.sqlite_runtime import connect_sqlite


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_500_DB = PROJECT_ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_MODEL_DB = PROJECT_ROOT / "data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results/main_strategy_issue_quality_selector_v2_validation_20260629"
MAIN_STRATEGY_RESULTS_DIR = PROJECT_ROOT / "results/n7_sleeve_mix_capital_plus2026_linefill_20260630"
HIGH_N_SELECTOR_RESULTS_DIR = PROJECT_ROOT / "results/high_n_selector_plus2026_linefill_20260630"
LINEGAP_DRIFT_RESULTS_DIR = PROJECT_ROOT / "results/main_strategy_linegap_drift_depth_20260630"
JOINT_LEG_RESULTS_DIR = PROJECT_ROOT / "results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630"
STRUCTURED_DECISION_SHADOW_DIR = PROJECT_ROOT / "results/structured_decision_chain_shadow"
DECISION_VERSIONS_CONFIG = PROJECT_ROOT / "config/decision_versions.json"
STRATEGY_RELEASE_CONFIG = PROJECT_ROOT / "config/strategy_release.json"
DEFAULT_DASHBOARD_RUNTIME_STATUS = PROJECT_ROOT / "tmp/decision_dashboard/runtime_status.json"
DEFAULT_DASHBOARD_STATIC_DIR = PROJECT_ROOT / "apps/decision-dashboard/dist"
DEFAULT_DECISION_API_HOST = "127.0.0.1"
DEFAULT_CACHE_TTL_SEC = 30.0
OPERATOR_TOKEN_ENV = "BEIDAN_DECISION_API_OPERATOR_TOKEN"
OPERATOR_TOKEN_HEADER = "X-Beidan-Operator-Token"
DASHBOARD_GATE_PASSWORD_ENVS = ("BEIDAN_DASHBOARD_GATE_PASS", "BEIDAN_GATE_PASS")
DASHBOARD_GATE_SECRET_ENVS = ("BEIDAN_DASHBOARD_GATE_SECRET", "BEIDAN_SECRET")
HK_TZ = timezone(timedelta(hours=8))
OUTCOME_LABEL = {"3": "胜", "1": "平", "0": "负"}
OUTCOME_ORDER = ("3", "1", "0")
Q_STOP_THRESHOLD = 1.00
ACTIVE_DECISION_VARIANT_ID = "active_v3"
ACTIVE_DECISION_VARIANT_KIND = "active"
ACTIVE_DECISION_VARIANT_LABEL = "v3"
ACTIVE_DECISION_VARIANT_DISPLAY_LABEL = "v3"
SHADOW_DECISION_VARIANT_ID = "shadow_v3.3.3"
SHADOW_DECISION_VERSION = "llm_chain_bet_protect_stop_v3.3.3_shadow"
SHADOW_DECISION_LABEL = "shadow v3.3.3"
SHADOW_DECISION_VARIANT_KIND = "shadow"
SHADOW_DECISION_FAMILY = "structured_shadow"
MAIN_STRATEGY_ARMS = (
    {
        "arm_id": "b384_dd32_smooth100",
        "label": "A 稳健/回撤控制",
        "role": "stable",
        "recommended_for": "回撤控制、实盘默认保守档",
    },
    {
        "arm_id": "b384_dd32_smooth80_convex19",
        "label": "B 收益/凸性",
        "role": "convex",
        "recommended_for": "追求凸性收益、接受更深回撤",
    },
)
MAIN_STRATEGY_ARM_IDS = tuple(arm["arm_id"] for arm in MAIN_STRATEGY_ARMS)


DEFAULT_DECISION_VERSION_REGISTRY: dict[str, Any] = {
    "schema_version": "decision_versions_v1",
    "probability_model": {
        "version": "bd_prob_handicap_calibrated_v1",
        "parameters": {
            "uses_beidan_integer_handicap": True,
            "uses_market_implied_probability": True,
            "line_gap_policy": "diagnostic_only",
        },
    },
    "q_model": {
        "version": "q_ev_sp_v1",
        "parameters": {
            "stop_threshold": Q_STOP_THRESHOLD,
            "sp_policy": "preclose_sp_if_available_else_live_sp_only_before_result",
        },
    },
    "decision_chain": {
        "version": "llm_chain_bet_protect_stop_v3",
        "prompt_version": "fixed_decision_chain_v3_bet_protect_stop",
        "model_version": "gpt_fixed_decision_chain_v3",
        "parameters": {
            "line_gap_policy": "diagnostic_or_protection_note",
            "q_stop_threshold": Q_STOP_THRESHOLD,
            "manual_override_required_for_snapshot_replacement": True,
        },
    },
    "review_tags": {
        "version": "postmatch_tags_v2",
        "review_version": "v2_active_llm_snapshot_tags",
    },
}

DEFAULT_STRATEGY_RELEASE_ID = "main_n7_384_2026_07_04"
DEFAULT_STRATEGY_RELEASE_REGISTRY: dict[str, Any] = {
    "schema_version": "strategy_release_registry_v1",
    "active_release_id": DEFAULT_STRATEGY_RELEASE_ID,
    "releases": {
        DEFAULT_STRATEGY_RELEASE_ID: {
            "release_id": DEFAULT_STRATEGY_RELEASE_ID,
            "version_id": "1.0.0",
            "status": "active",
            "owner": "codex",
            "strategy_family": "N=7 fixed-384 main strategy",
            "generated_at": "2026-07-04T14:30:00+08:00",
            "effective_from_issue": "26072",
            "artifact_scope": {
                "historical_data_start": "2014",
                "backtest_through_issue": "26071",
                "live_issue_policy": "resolve_current_from_500_sqlite",
                "freeze_policy": "strategy artifacts must be generated before the issue is traded; post-settlement artifacts are review-only",
            },
            "snapshot_timestamps": {
                "probability_model": "2026-07-04T14:30:00+08:00",
                "q_model": "2026-07-04T14:30:00+08:00",
                "confidence_model": "2026-07-04T14:30:00+08:00",
                "decision_chain": "2026-07-04T14:30:00+08:00",
            },
            "model_versions": {
                "probability_model": "bd_prob_handicap_calibrated_v1",
                "q_model": "q_ev_sp_v1",
                "decision_chain": "llm_chain_bet_protect_stop_v3",
                "shadow_decision_chain": SHADOW_DECISION_VERSION,
            },
            "decision_variants": [
                {
                    "variant_id": ACTIVE_DECISION_VARIANT_ID,
                    "version_id": "3.0.0",
                    "kind": ACTIVE_DECISION_VARIANT_KIND,
                    "label": ACTIVE_DECISION_VARIANT_LABEL,
                    "source": "active_snapshot",
                    "is_default": False,
                    "selectable": True,
                },
                {
                    "variant_id": SHADOW_DECISION_VARIANT_ID,
                    "version_id": "3.3.3",
                    "kind": SHADOW_DECISION_VARIANT_KIND,
                    "label": SHADOW_DECISION_LABEL,
                    "source": "structured_shadow_csv",
                    "artifact_key": "structured_shadow_dir",
                    "is_default": True,
                    "selectable": True,
                },
            ],
            "main_strategy_arms": list(MAIN_STRATEGY_ARMS),
            "artifacts": {
                "main_strategy_dir": str(MAIN_STRATEGY_RESULTS_DIR.relative_to(PROJECT_ROOT)),
                "ticket_pool_dir": str(HIGH_N_SELECTOR_RESULTS_DIR.relative_to(PROJECT_ROOT)),
                "ticket_pool_csv": str((HIGH_N_SELECTOR_RESULTS_DIR / "high_n_selector_selected_tickets.csv").relative_to(PROJECT_ROOT)),
                "linegap_drift_dir": str(LINEGAP_DRIFT_RESULTS_DIR.relative_to(PROJECT_ROOT)),
                "joint_leg_rows_csv": str((JOINT_LEG_RESULTS_DIR / "joint_leg_rows.csv").relative_to(PROJECT_ROOT)),
                "structured_shadow_dir": str(STRUCTURED_DECISION_SHADOW_DIR.relative_to(PROJECT_ROOT)),
            },
            "required_artifacts": [
                "main_strategy_dir/sleeve_mix_summary.csv",
                "main_strategy_dir/sleeve_mix_annual.csv",
                "main_strategy_dir/sleeve_mix_issue_profit.csv",
                "ticket_pool_csv",
                "joint_leg_rows_csv",
            ],
            "promotion": {
                "mode": "shadow_first_or_validated_default",
                "validated": True,
                "promoted_at": "2026-07-04",
                "promoted_by": "codex",
                "rollback_release_id": "",
            },
            "validation": {
                "report": "docs/strategy/strategy_worktree_model_ev_handoff_2026-07-02.md",
                "no_future_leakage": True,
                "notes": "line-gap and SP drift remain diagnostics unless a strategy release explicitly validates them.",
            },
        }
    },
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(_canonical_json(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


@lru_cache(maxsize=1)
def _decision_version_registry() -> dict[str, Any]:
    if DECISION_VERSIONS_CONFIG.exists():
        try:
            loaded = json.loads(DECISION_VERSIONS_CONFIG.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return _deep_merge_dict(DEFAULT_DECISION_VERSION_REGISTRY, loaded)
        except (OSError, json.JSONDecodeError):
            pass
    return json.loads(_canonical_json(DEFAULT_DECISION_VERSION_REGISTRY))


@lru_cache(maxsize=1)
def _strategy_release_registry() -> dict[str, Any]:
    fallback = json.loads(_canonical_json(DEFAULT_STRATEGY_RELEASE_REGISTRY))
    if STRATEGY_RELEASE_CONFIG.exists():
        try:
            loaded = json.loads(STRATEGY_RELEASE_CONFIG.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                merged = _deep_merge_dict(DEFAULT_STRATEGY_RELEASE_REGISTRY, loaded)
                merged["_load_status"] = {
                    "status": "ok",
                    "source": _relative_display_path(STRATEGY_RELEASE_CONFIG),
                    "error": "",
                    "fallback_release_id": "",
                }
                return merged
        except (OSError, json.JSONDecodeError) as exc:
            fallback["_load_status"] = {
                "status": "degraded",
                "source": _relative_display_path(STRATEGY_RELEASE_CONFIG),
                "error": f"failed to load strategy release config: {exc}",
                "fallback_release_id": DEFAULT_STRATEGY_RELEASE_ID,
            }
            return fallback
    fallback["_load_status"] = {
        "status": "default",
        "source": _relative_display_path(STRATEGY_RELEASE_CONFIG),
        "error": "",
        "fallback_release_id": "",
    }
    return fallback


def _relative_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _project_path(value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else PROJECT_ROOT / path


def _active_strategy_release() -> dict[str, Any]:
    registry = _strategy_release_registry()
    active_id = str(registry.get("active_release_id") or DEFAULT_STRATEGY_RELEASE_ID)
    configured_active_id = active_id
    load_status = registry.get("_load_status", {})
    if not isinstance(load_status, dict):
        load_status = {"status": "ok", "error": "", "fallback_release_id": ""}
    releases = registry.get("releases", {})
    if not isinstance(releases, dict):
        releases = {}
    release = releases.get(active_id)
    fallback_used = False
    if not isinstance(release, dict):
        release = DEFAULT_STRATEGY_RELEASE_REGISTRY["releases"][DEFAULT_STRATEGY_RELEASE_ID]
        fallback_used = True
        load_status = {
            "status": "degraded",
            "source": load_status.get("source", _relative_display_path(STRATEGY_RELEASE_CONFIG)),
            "error": f"active strategy release not found: {configured_active_id}",
            "configured_active_release_id": configured_active_id,
            "fallback_release_id": DEFAULT_STRATEGY_RELEASE_ID,
        }
    out = json.loads(_canonical_json(release))
    out.setdefault("release_id", active_id)
    out["release_id"] = str(out["release_id"] or (DEFAULT_STRATEGY_RELEASE_ID if fallback_used else active_id))
    out["schema_version"] = registry.get("schema_version", "strategy_release_registry_v1")
    out["active_release_id"] = configured_active_id
    out["configured_active_release_id"] = configured_active_id
    out["fallback_release_id"] = str(load_status.get("fallback_release_id") or "")
    out["fallback_used"] = fallback_used or bool(load_status.get("fallback_release_id"))
    out["release_load_status"] = str(load_status.get("status") or "ok")
    out["release_load_error"] = str(load_status.get("error") or "")
    out["config_path"] = _relative_display_path(STRATEGY_RELEASE_CONFIG)
    return out


def _strategy_release_artifacts(release: dict[str, Any] | None = None) -> dict[str, Any]:
    release = release or _active_strategy_release()
    artifacts = release.get("artifacts", {})
    return artifacts if isinstance(artifacts, dict) else {}


def _strategy_artifact_path(
    artifact_key: str,
    fallback: Path,
    release: dict[str, Any] | None = None,
) -> Path:
    artifacts = _strategy_release_artifacts(release)
    value = artifacts.get(artifact_key)
    if value in {None, ""}:
        return fallback
    return _project_path(value)


def _strategy_ticket_pool_csv(release: dict[str, Any] | None = None) -> Path:
    pool_dir = _strategy_artifact_path("ticket_pool_dir", HIGH_N_SELECTOR_RESULTS_DIR, release)
    return _strategy_artifact_path("ticket_pool_csv", pool_dir / "high_n_selector_selected_tickets.csv", release)


def _strategy_joint_leg_rows_csv(release: dict[str, Any] | None = None) -> Path:
    return _strategy_artifact_path("joint_leg_rows_csv", JOINT_LEG_RESULTS_DIR / "joint_leg_rows.csv", release)


def _strategy_main_dir(release: dict[str, Any] | None = None) -> Path:
    return _strategy_artifact_path("main_strategy_dir", MAIN_STRATEGY_RESULTS_DIR, release)


def _strategy_linegap_drift_dir(release: dict[str, Any] | None = None) -> Path:
    return _strategy_artifact_path("linegap_drift_dir", LINEGAP_DRIFT_RESULTS_DIR, release)


def _strategy_shadow_dir(release: dict[str, Any] | None = None) -> Path:
    return _strategy_artifact_path("structured_shadow_dir", STRUCTURED_DECISION_SHADOW_DIR, release)


def _main_strategy_arms(release: dict[str, Any] | None = None) -> tuple[dict[str, Any], ...]:
    release = release or _active_strategy_release()
    arms = release.get("main_strategy_arms")
    if not isinstance(arms, list):
        return MAIN_STRATEGY_ARMS
    cleaned = [arm for arm in arms if isinstance(arm, dict) and arm.get("arm_id")]
    return tuple(cleaned) if cleaned else MAIN_STRATEGY_ARMS


def _main_strategy_arm_ids(release: dict[str, Any] | None = None) -> tuple[str, ...]:
    return tuple(str(arm["arm_id"]) for arm in _main_strategy_arms(release))


def _resolve_strategy_required_artifact(spec: Any, release: dict[str, Any] | None = None) -> Path:
    release = release or _active_strategy_release()
    text = str(spec or "")
    artifacts = _strategy_release_artifacts(release)
    if text in artifacts:
        return _project_path(artifacts[text])
    if "/" in text:
        key, suffix = text.split("/", 1)
        if key in artifacts:
            return _project_path(artifacts[key]) / suffix
    return _project_path(text)


def _strategy_release_artifact_health(release: dict[str, Any] | None = None) -> dict[str, Any]:
    release = release or _active_strategy_release()
    artifacts = {
        key: {
            "path": _relative_display_path(_project_path(value)),
            "exists": _project_path(value).exists(),
        }
        for key, value in _strategy_release_artifacts(release).items()
        if value not in {None, ""}
    }
    required = []
    for spec in release.get("required_artifacts", []) if isinstance(release.get("required_artifacts"), list) else []:
        path = _resolve_strategy_required_artifact(spec, release)
        required.append({
            "spec": str(spec),
            "path": _relative_display_path(path),
            "exists": path.exists(),
        })
    return {
        "artifacts": artifacts,
        "required": required,
        "missing_required": [item for item in required if not item["exists"]],
    }


def _strategy_release_public_payload(release: dict[str, Any] | None = None) -> dict[str, Any]:
    release = release or _active_strategy_release()
    resolved_artifacts = {
        key: _relative_display_path(_project_path(value))
        for key, value in _strategy_release_artifacts(release).items()
        if value not in {None, ""}
    }
    health = _strategy_release_artifact_health(release)
    return {
        "schema_version": release.get("schema_version", "strategy_release_registry_v1"),
        "active_release_id": release.get("active_release_id") or release.get("release_id"),
        "configured_active_release_id": release.get("configured_active_release_id", release.get("active_release_id", "")),
        "release_id": release.get("release_id"),
        "fallback_release_id": release.get("fallback_release_id", ""),
        "fallback_used": bool(release.get("fallback_used")),
        "release_load_status": release.get("release_load_status", "ok"),
        "release_load_error": release.get("release_load_error", ""),
        "version_id": release.get("version_id", ""),
        "status": release.get("status", ""),
        "owner": release.get("owner", ""),
        "strategy_family": release.get("strategy_family", ""),
        "generated_at": release.get("generated_at", ""),
        "effective_from_issue": release.get("effective_from_issue", ""),
        "artifact_scope": release.get("artifact_scope", {}),
        "snapshot_timestamps": release.get("snapshot_timestamps", {}),
        "model_versions": release.get("model_versions", {}),
        "decision_variants": release.get("decision_variants", []),
        "main_strategy_arms": list(_main_strategy_arms(release)),
        "artifacts": resolved_artifacts,
        "required_artifacts": release.get("required_artifacts", []),
        "artifact_health": health,
        "promotion": release.get("promotion", {}),
        "validation": release.get("validation", {}),
        "config_path": release.get("config_path", _relative_display_path(STRATEGY_RELEASE_CONFIG)),
    }


def _decision_config_hash() -> str:
    registry = _decision_version_registry()
    payload = {
        name: {
            "version": section.get("version"),
            "prompt_version": section.get("prompt_version"),
            "model_version": section.get("model_version"),
            "review_version": section.get("review_version"),
            "parameters": section.get("parameters", {}),
        }
        for name, section in registry.items()
        if isinstance(section, dict)
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def _dashboard_runtime_status_path() -> Path:
    return Path(os.environ.get("BEIDAN_DASHBOARD_RUNTIME_STATUS", DEFAULT_DASHBOARD_RUNTIME_STATUS))


def _read_dashboard_runtime_status() -> dict[str, Any]:
    path = _dashboard_runtime_status_path()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _public_diagnostics_enabled() -> bool:
    return _truthy_env("BEIDAN_DECISION_API_PUBLIC_DIAGNOSTICS")


def _public_diagnostics_path(path: Any) -> str:
    return str(path) if _public_diagnostics_enabled() else "redacted"


def _allowed_cors_origins() -> set[str]:
    raw = os.environ.get("BEIDAN_DECISION_API_CORS_ORIGINS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _operator_token() -> str:
    return str(os.environ.get(OPERATOR_TOKEN_ENV, "")).strip()


def _operator_token_error(code: str, message: str) -> tuple[Any, int]:
    return jsonify({"error": message, "code": code}), 403


def _require_operator_token() -> tuple[Any, int] | None:
    expected = _operator_token()
    if not expected:
        return _operator_token_error(
            "operator_token_unconfigured",
            f"{OPERATOR_TOKEN_ENV} is required for mutating API requests.",
        )
    provided = request.headers.get(OPERATOR_TOKEN_HEADER, "")
    if not provided or not hmac.compare_digest(provided, expected):
        return _operator_token_error(
            "operator_token_required",
            f"{OPERATOR_TOKEN_HEADER} is required for mutating API requests.",
        )
    return None


def _health_probe_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload = {
        "ok": bool(value.get("ok")),
        "status": int(value.get("status") or 0),
    }
    if value.get("latency_ms") is not None:
        payload["latency_ms"] = value.get("latency_ms")
    for key in ("issue", "workflow_status", "review_task_status"):
        if value.get(key) not in {None, ""}:
            payload[key] = value.get(key)
    return payload


def _runtime_health_summary(health: Any) -> dict[str, Any]:
    if not isinstance(health, dict):
        return {}
    host_smokes = health.get("host_smokes")
    host_smokes = host_smokes if isinstance(host_smokes, list) else []
    return {
        "api": _health_probe_summary(health.get("api")),
        "frontend_local": _health_probe_summary(health.get("frontend_local")),
        "operations": _health_probe_summary(health.get("operations")),
        "host_smoke_count": len(host_smokes),
        "host_smoke_ok_count": sum(1 for item in host_smokes if isinstance(item, dict) and item.get("ok")),
    }


def _runtime_access_mode(api: dict[str, Any], frontend: dict[str, Any], urls: dict[str, Any]) -> str:
    if urls.get("funnel"):
        return "public_funnel_configured"
    if urls.get("magic_dns") or urls.get("frontend_remote"):
        return "tailnet_metadata_recorded"
    exposed_hosts = {"0.0.0.0", "::", ""}
    if str(api.get("bind_host") or "") in exposed_hosts or str(frontend.get("bind_host") or "") in exposed_hosts:
        return "direct_bind_non_loopback"
    return "local_only"


def _dashboard_runtime_summary() -> dict[str, Any]:
    status = _read_dashboard_runtime_status()
    public_diagnostics = _public_diagnostics_enabled()
    if not status:
        return {
            "checked_at": "",
            "public_diagnostics": public_diagnostics,
            "access_mode": "runtime_status_missing",
            "external_access_configured": False,
            "api_process_status": "unknown",
            "frontend_process_status": "unknown",
            "health": {},
        }
    api = status.get("api") if isinstance(status.get("api"), dict) else {}
    frontend = status.get("frontend") if isinstance(status.get("frontend"), dict) else {}
    health = status.get("health") if isinstance(status.get("health"), dict) else {}
    urls = status.get("urls") if isinstance(status.get("urls"), dict) else {}
    logs = status.get("logs") if isinstance(status.get("logs"), dict) else {}
    external_access_configured = bool(urls.get("frontend_remote") or urls.get("magic_dns") or urls.get("funnel"))
    payload: dict[str, Any] = {
        "schema": status.get("schema", ""),
        "checked_at": status.get("checked_at", ""),
        "public_diagnostics": public_diagnostics,
        "access_mode": _runtime_access_mode(api, frontend, urls),
        "external_access_configured": external_access_configured,
        "api_process_status": api.get("status", ""),
        "frontend_process_status": frontend.get("status", ""),
        "health": _runtime_health_summary(health),
    }
    if public_diagnostics:
        payload["diagnostics"] = {
            "status_path": status.get("status_path") or str(_dashboard_runtime_status_path()),
            "runtime_dir": status.get("runtime_dir", ""),
            "urls": urls,
            "api_pid": api.get("pid"),
            "api_bind_host": api.get("bind_host", ""),
            "api_command": api.get("command", []),
            "api_log": api.get("log") or logs.get("api", ""),
            "frontend_pid": frontend.get("pid"),
            "frontend_bind_host": frontend.get("bind_host", ""),
            "frontend_command": frontend.get("command", []),
            "frontend_log": frontend.get("log") or logs.get("frontend", ""),
        }
    return payload


def _active_version_bundle() -> dict[str, Any]:
    registry = _decision_version_registry()
    probability = registry.get("probability_model", {}) if isinstance(registry.get("probability_model"), dict) else {}
    q_model = registry.get("q_model", {}) if isinstance(registry.get("q_model"), dict) else {}
    chain = registry.get("decision_chain", {}) if isinstance(registry.get("decision_chain"), dict) else {}
    review = registry.get("review_tags", {}) if isinstance(registry.get("review_tags"), dict) else {}
    return {
        "schema_version": registry.get("schema_version", "decision_versions_v1"),
        "prob_model_version": probability.get("version", "bd_prob_handicap_calibrated_v1"),
        "q_model_version": q_model.get("version", "q_ev_sp_v1"),
        "decision_chain_version": chain.get("version", "llm_chain_bet_protect_stop_v3"),
        "decision_prompt_version": chain.get("prompt_version", "fixed_decision_chain_v3_bet_protect_stop"),
        "decision_model_version": chain.get("model_version", "gpt_fixed_decision_chain_v3"),
        "review_tag_version": review.get("version", "postmatch_tags_v2"),
        "review_version": review.get("review_version", "v2_active_llm_snapshot_tags"),
        "decision_config_hash": _decision_config_hash(),
        "config_path": str(DECISION_VERSIONS_CONFIG.relative_to(PROJECT_ROOT)),
    }


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _query_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=16)
def _read_csv_cached(path_text: str) -> tuple[dict[str, Any], ...]:
    return tuple(_read_csv(Path(path_text)))


@lru_cache(maxsize=8)
def _main_issue_rows_cached(path_text: str, portfolios: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    path = Path(path_text)
    if not path.exists():
        return ()
    wanted = set(portfolios)
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("portfolio") in wanted:
                rows.append(row)
    return tuple(rows)


@lru_cache(maxsize=64)
def _selected_ticket_rows_for_issue(path_text: str, issue: str) -> tuple[dict[str, Any], ...]:
    path = Path(path_text)
    if not path.exists():
        return ()
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if str(row.get("issue", "")) == str(issue):
                rows.append(row)
    return tuple(rows)


def _csv_float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = _safe_float(row.get(key))
    return default if value is None else value


def _csv_int(row: dict[str, Any], key: str, default: int = 0) -> int:
    value = _safe_int(row.get(key))
    return default if value is None else value


def _csv_bool(row: dict[str, Any], key: str) -> bool | None:
    value = row.get(key)
    if value in {True, False}:
        return bool(value)
    if value in {None, ""}:
        return None
    parsed = _safe_int(value)
    return None if parsed is None else bool(parsed)


def _csv_semicolon_list(row: dict[str, Any], key: str) -> list[str]:
    value = row.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _connect(path: Path) -> sqlite3.Connection:
    return connect_sqlite(path, row_factory=True)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _ensure_decision_snapshot_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_decision_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            status TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            checked_at TEXT,
            last_checked_input_hash TEXT,
            confirmed_at TEXT,
            superseded_at TEXT,
            supersedes_snapshot_id TEXT,
            input_hash TEXT NOT NULL,
            decision_fingerprint TEXT NOT NULL,
            recommendation TEXT,
            primary_pick TEXT,
            protect_picks_json TEXT NOT NULL,
            stop_flag INTEGER NOT NULL,
            selection_codes_json TEXT NOT NULL,
            selection_type TEXT NOT NULL,
            confidence REAL,
            confidence_label TEXT,
            q_score REAL,
            probability REAL,
            decision_chain_json TEXT NOT NULL,
            support_json TEXT NOT NULL,
            risks_json TEXT NOT NULL,
            explanation TEXT,
            model_probabilities_json TEXT NOT NULL,
            market_probabilities_json TEXT NOT NULL,
            q_values_json TEXT NOT NULL,
            sp_snapshot_json TEXT NOT NULL,
            source_timestamps_json TEXT NOT NULL,
            input_payload_json TEXT NOT NULL,
            decision_payload_json TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            model_version TEXT NOT NULL,
            prob_model_version TEXT,
            q_model_version TEXT,
            decision_chain_version TEXT,
            decision_config_hash TEXT,
            review_tag_version TEXT,
            version_bundle_json TEXT,
            created_by TEXT NOT NULL DEFAULT 'decision_api',
            CHECK (status IN ('active', 'draft_replacement', 'superseded'))
        )
        """
    )
    version_columns = {
        "confirmed_at": "TEXT",
        "prob_model_version": "TEXT",
        "q_model_version": "TEXT",
        "decision_chain_version": "TEXT",
        "decision_config_hash": "TEXT",
        "review_tag_version": "TEXT",
        "version_bundle_json": "TEXT",
    }
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(llm_decision_snapshots)")}
    for col, col_type in version_columns.items():
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE llm_decision_snapshots ADD COLUMN {col} {col_type}")
    versions = _active_version_bundle()
    conn.execute(
        """
        UPDATE llm_decision_snapshots
        SET
          prob_model_version=COALESCE(prob_model_version, ?),
          q_model_version=COALESCE(q_model_version, ?),
          decision_chain_version=COALESCE(decision_chain_version, ?),
          decision_config_hash=COALESCE(decision_config_hash, ?),
          review_tag_version=COALESCE(review_tag_version, ?),
          version_bundle_json=CASE
            WHEN version_bundle_json IS NULL OR version_bundle_json='' THEN ?
            ELSE version_bundle_json
          END
        """,
        (
            versions["prob_model_version"],
            versions["q_model_version"],
            versions["decision_chain_version"],
            versions["decision_config_hash"],
            versions["review_tag_version"],
            _canonical_json(versions),
        ),
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_decision_active
        ON llm_decision_snapshots(issue, match_idx)
        WHERE status='active'
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_decision_draft
        ON llm_decision_snapshots(issue, match_idx)
        WHERE status='draft_replacement'
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_decision_match ON llm_decision_snapshots(issue, match_idx, status)")


def _ensure_live_workflow_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS live_workflow_runs (
            run_id TEXT PRIMARY KEY,
            issue TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            dry_run INTEGER NOT NULL,
            requested_by TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            elapsed_sec REAL,
            error TEXT,
            plan_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS live_workflow_steps (
            run_id TEXT NOT NULL,
            step_idx INTEGER NOT NULL,
            step_key TEXT NOT NULL,
            label TEXT NOT NULL,
            status TEXT NOT NULL,
            command_json TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            elapsed_sec REAL,
            error TEXT,
            result_json TEXT NOT NULL,
            PRIMARY KEY (run_id, step_idx)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_live_workflow_runs_issue ON live_workflow_runs(issue, started_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_live_workflow_steps_run ON live_workflow_steps(run_id, step_idx)")


def _ensure_postmatch_review_run_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS postmatch_review_runs (
            run_id TEXT PRIMARY KEY,
            issue TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            dry_run INTEGER NOT NULL,
            requested_by TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            elapsed_sec REAL,
            error TEXT,
            command_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_postmatch_review_runs_issue ON postmatch_review_runs(issue, started_at DESC)")


def _json_loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return fallback


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    return row[key] if key in row.keys() else default


def _latest_decision_snapshot(
    conn: sqlite3.Connection,
    issue: str,
    match_idx: int,
    status: str,
) -> sqlite3.Row | None:
    if not _table_exists(conn, "llm_decision_snapshots"):
        return None
    return conn.execute(
        """
        SELECT *
        FROM llm_decision_snapshots
        WHERE issue=? AND match_idx=? AND status=?
        ORDER BY generated_at DESC, snapshot_id DESC
        LIMIT 1
        """,
        (issue, match_idx, status),
    ).fetchone()


def _snapshot_public_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    protect_picks = _json_loads(row["protect_picks_json"], [])
    selection_codes = _json_loads(row["selection_codes_json"], [])
    decision_chain = _json_loads(row["decision_chain_json"], [])
    support = _json_loads(row["support_json"], [])
    risks = _json_loads(row["risks_json"], [])
    source_timestamps = _json_loads(row["source_timestamps_json"], {})
    input_payload = _json_loads(row["input_payload_json"], {})
    decision_payload = _json_loads(row["decision_payload_json"], {})
    version_bundle = _json_loads(_row_get(row, "version_bundle_json"), {})
    prob_model_version = _row_get(row, "prob_model_version") or version_bundle.get("prob_model_version")
    q_model_version = _row_get(row, "q_model_version") or version_bundle.get("q_model_version")
    decision_chain_version = _row_get(row, "decision_chain_version") or version_bundle.get("decision_chain_version") or row["model_version"]
    decision_config_hash = _row_get(row, "decision_config_hash") or version_bundle.get("decision_config_hash") or ""
    review_tag_version = _row_get(row, "review_tag_version") or version_bundle.get("review_tag_version") or ""
    return {
        "snapshot_id": row["snapshot_id"],
        "issue": row["issue"],
        "match_idx": row["match_idx"],
        "match_id": row["match_id"],
        "status": row["status"],
        "generated_at": row["generated_at"],
        "checked_at": row["checked_at"],
        "input_hash": row["input_hash"],
        "last_checked_input_hash": row["last_checked_input_hash"],
        "confirmed_at": _row_get(row, "confirmed_at"),
        "decision_fingerprint": row["decision_fingerprint"],
        "recommendation": row["recommendation"],
        "primary_pick": row["primary_pick"],
        "protect_picks": protect_picks,
        "stop_flag": bool(row["stop_flag"]),
        "selection_codes": selection_codes,
        "selection_type": row["selection_type"],
        "confidence": row["confidence"],
        "confidence_label": row["confidence_label"],
        "q_score": row["q_score"],
        "probability": row["probability"],
        "decision_chain": decision_chain,
        "support": support,
        "risks": risks,
        "explanation": row["explanation"],
        "source_timestamps": source_timestamps,
        "input_summary": input_payload,
        "decision_payload": decision_payload,
        "prompt_version": row["prompt_version"],
        "model_version": row["model_version"],
        "prob_model_version": prob_model_version,
        "q_model_version": q_model_version,
        "decision_chain_version": decision_chain_version,
        "decision_config_hash": decision_config_hash,
        "review_tag_version": review_tag_version,
        "version_bundle": version_bundle,
        "supersedes_snapshot_id": row["supersedes_snapshot_id"],
        "superseded_at": row["superseded_at"],
    }


def _snapshot_row_to_summary_fields(row: sqlite3.Row) -> dict[str, Any]:
    selection_codes = [str(code) for code in _json_loads(row["selection_codes_json"], []) if str(code) in OUTCOME_ORDER]
    primary = str(row["primary_pick"] or "") if row["primary_pick"] else None
    decision_chain = _json_loads(row["decision_chain_json"], [])
    support = _json_loads(row["support_json"], [])
    risks = _json_loads(row["risks_json"], [])
    selection_type = str(row["selection_type"] or _selection_type_from_codes(selection_codes))
    version_bundle = _json_loads(_row_get(row, "version_bundle_json"), {})
    return {
        "llm_judgment": row["recommendation"] or ("停" if row["stop_flag"] else ""),
        "llm_selection": primary,
        "llm_selection_codes": selection_codes,
        "llm_selection_type": selection_type,
        "llm_explanation": row["explanation"] or "",
        "llm_confidence": row["confidence"],
        "llm_confidence_label": row["confidence_label"] or "",
        "llm_support": support if isinstance(support, list) else [],
        "llm_risks": risks if isinstance(risks, list) else [],
        "llm_decision_chain": decision_chain if isinstance(decision_chain, list) else [],
        "llm_source": f"{row['model_version']}:snapshot_active",
        "llm_q_score": row["q_score"],
        "llm_probability": row["probability"],
        "llm_stop_flag": bool(row["stop_flag"]),
        "selection": primary,
        "selection_codes": selection_codes,
        "selection_source": f"{row['model_version']}:snapshot_active",
        "selection_type": selection_type,
        "decision_snapshot_id": row["snapshot_id"],
        "decision_snapshot_status": row["status"],
        "decision_snapshot_generated_at": row["generated_at"],
        "decision_snapshot_checked_at": row["checked_at"],
        "decision_snapshot_input_hash": row["input_hash"],
        "prob_model_version": _row_get(row, "prob_model_version") or version_bundle.get("prob_model_version"),
        "q_model_version": _row_get(row, "q_model_version") or version_bundle.get("q_model_version"),
        "decision_chain_version": _row_get(row, "decision_chain_version") or version_bundle.get("decision_chain_version") or row["model_version"],
        "decision_config_hash": _row_get(row, "decision_config_hash") or version_bundle.get("decision_config_hash") or "",
        "review_tag_version": _row_get(row, "review_tag_version") or version_bundle.get("review_tag_version") or "",
    }


def _postmatch_review_payload(conn: sqlite3.Connection, issue: str, match_idx: int) -> dict[str, Any] | None:
    if not _table_exists(conn, "postmatch_reviews"):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM postmatch_reviews
        WHERE issue=? AND match_idx=?
        ORDER BY
          CASE WHEN review_version='v2_active_llm_snapshot_tags' THEN 0 ELSE 1 END,
          reviewed_at DESC
        LIMIT 1
        """,
        (issue, match_idx),
    ).fetchone()
    if not row:
        return None
    keys = set(row.keys())
    tags = _json_loads(row["failure_tags_json"], [])
    payload = {
        "issue": row["issue"],
        "match_idx": row["match_idx"],
        "match_id": row["match_id"],
        "review_version": row["review_version"],
        "reviewed_at": row["reviewed_at"],
        "decision_snapshot_id": row["decision_snapshot_id"] if "decision_snapshot_id" in keys else "",
        "decision_snapshot_generated_at": row["decision_snapshot_generated_at"] if "decision_snapshot_generated_at" in keys else "",
        "tag_version": row["tag_version"] if "tag_version" in keys else "",
        "outcome_label": row["outcome_label"] if "outcome_label" in keys else "",
        "summary": row["review_summary"],
        "action_suggestion": row["action_suggestion"] if "action_suggestion" in keys else "",
        "tags": tags if isinstance(tags, list) else [],
        "primary_hit": bool(row["primary_hit"]),
        "protect_hit": bool(row["protect_hit"]),
        "coverage_hit": bool(row["coverage_hit"]),
        "stopped": bool(row["stopped"]),
        "stake": row["stake"],
        "gross_return": row["gross_return"],
        "profit": row["profit"],
        "roi": row["roi"],
    }
    return payload


def _postmatch_issue_summary_payload(conn: sqlite3.Connection, issue: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "postmatch_review_issue_summary"):
        return None
    row = conn.execute(
        """
        SELECT *
        FROM postmatch_review_issue_summary
        WHERE issue=?
        ORDER BY
          CASE WHEN review_version='v2_active_llm_snapshot_tags' THEN 0 ELSE 1 END,
          reviewed_at DESC
        LIMIT 1
        """,
        (issue,),
    ).fetchone()
    if not row:
        return None
    tag_counts = _json_loads(row["tag_counts_json"], {})
    return {
        "issue": row["issue"],
        "review_version": row["review_version"],
        "reviewed_at": row["reviewed_at"],
        "n_reviews": row["n_reviews"],
        "stake": row["stake"],
        "gross_return": row["gross_return"],
        "profit": row["profit"],
        "roi": row["roi"],
        "primary_hits": row["primary_hits"],
        "protect_hits": row["protect_hits"],
        "coverage_hits": row["coverage_hits"],
        "stopped_correct": row["stopped_correct"],
        "stopped_wrong": row["stopped_wrong"],
        "tag_counts": tag_counts if isinstance(tag_counts, dict) else {},
    }


def _postmatch_review_rows_payload(conn: sqlite3.Connection, issue: str) -> list[dict[str, Any]]:
    if not _table_exists(conn, "postmatch_reviews"):
        return []
    rows = conn.execute(
        """
        SELECT *
        FROM postmatch_reviews
        WHERE issue=?
        ORDER BY
          match_idx ASC,
          CASE WHEN review_version='v2_active_llm_snapshot_tags' THEN 0 ELSE 1 END,
          reviewed_at DESC
        """,
        (issue,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        match_idx = int(row["match_idx"])
        if match_idx in seen:
            continue
        seen.add(match_idx)
        keys = set(row.keys())
        tags = _json_loads(row["failure_tags_json"], [])
        selection_codes = _json_loads(row["llm_selection_codes_json"], [])
        out.append({
            "issue": row["issue"],
            "match_idx": match_idx,
            "match_id": row["match_id"],
            "review_version": row["review_version"],
            "reviewed_at": row["reviewed_at"],
            "decision_snapshot_id": row["decision_snapshot_id"] if "decision_snapshot_id" in keys else "",
            "decision_snapshot_generated_at": row["decision_snapshot_generated_at"] if "decision_snapshot_generated_at" in keys else "",
            "tag_version": row["tag_version"] if "tag_version" in keys else "",
            "league": row["league"] or "",
            "home": row["home"] or "",
            "away": row["away"] or "",
            "kickoff_ts": row["kickoff_ts"] or "",
            "score": row["score"] or "",
            "halftime_score": row["halftime_score"] or "",
            "result_code": row["result_code"] or "",
            "result_label": row["result_label"] or "",
            "winning_sp": row["winning_sp"],
            "llm_selection": row["llm_selection"] or "",
            "llm_selection_codes": selection_codes if isinstance(selection_codes, list) else [],
            "llm_judgment": row["llm_judgment"] or "",
            "outcome_label": row["outcome_label"] if "outcome_label" in keys else "",
            "primary_hit": bool(row["primary_hit"]),
            "protect_hit": bool(row["protect_hit"]),
            "coverage_hit": bool(row["coverage_hit"]),
            "stopped": bool(row["stopped"]),
            "stake": row["stake"],
            "gross_return": row["gross_return"],
            "profit": row["profit"],
            "roi": row["roi"],
            "tags": tags if isinstance(tags, list) else [],
            "review_summary": row["review_summary"] or "",
            "action_suggestion": row["action_suggestion"] if "action_suggestion" in keys else "",
        })
    return out


def _today_hk() -> str:
    return os.environ.get("BEIDAN_DASHBOARD_DATE") or datetime.now(HK_TZ).strftime("%Y-%m-%d")


def _requested_decision_variant_id() -> str:
    return str(
        request.args.get("decision_variant")
        or request.args.get("variant")
        or request.args.get("version")
        or ""
    ).strip()


def _now_hk_iso() -> str:
    return datetime.now(HK_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _parse_timestamp_to_hk(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            parsed = datetime.fromisoformat(text[:-1] + "+00:00")
        elif "T" in text:
            parsed = datetime.fromisoformat(text)
        else:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=HK_TZ)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HK_TZ)
    return parsed.astimezone(HK_TZ)


def _minutes_since_hk(value: str | None) -> float | None:
    parsed = _parse_timestamp_to_hk(value)
    if parsed is None:
        return None
    return max(0.0, (datetime.now(HK_TZ) - parsed).total_seconds() / 60)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _workflow_run_id(issue: str, dry_run: bool) -> str:
    seed = f"{issue}|{_now_hk_iso()}|{os.getpid()}|{dry_run}"
    return f"wf_{issue}_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _postmatch_review_run_id(issue: str, dry_run: bool) -> str:
    seed = f"postmatch|{issue}|{_now_hk_iso()}|{os.getpid()}|{dry_run}"
    return f"pmr_{issue}_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _live_workflow_step_defs(issue: str, db_path: Path) -> list[dict[str, Any]]:
    py = os.environ.get("PYTHON") or sys.executable
    db_arg = str(db_path)
    return [
        {
            "step_key": "monitor_500_nowscore",
            "label": "刷新 500/捷报/赛果/SP",
            "kind": "subprocess",
            "timeout_sec": 240,
            "command": [
                py,
                str(PROJECT_ROOT / "scripts/monitor_500_bjdc.py"),
                "--db",
                db_arg,
                "--once",
                "--recent-count",
                "6",
                "--open-limit",
                "20",
                "--sleep",
                "0",
                "--timeout",
                "20",
            ],
        },
        {
            "step_key": "collect_match_intel",
            "label": "采集当前期情报摘要",
            "kind": "subprocess",
            "timeout_sec": 240,
            "command": [
                py,
                str(PROJECT_ROOT / "scripts/collect_match_intel.py"),
                "--db",
                db_arg,
                "--issue",
                issue,
                "--limit",
                "64",
                "--sleep",
                "0",
                "--timeout",
                "20",
            ],
        },
        {
            "step_key": "materialize_decision_snapshots",
            "label": "生成/检查 LLM 决策快照",
            "kind": "internal_decision_snapshots",
            "timeout_sec": 180,
            "command": ["internal", "materialize_issue_decision_snapshots", issue],
        },
    ]


def _insert_workflow_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    issue: str,
    dry_run: bool,
    status: str,
    plan: list[dict[str, Any]],
    requested_by: str,
) -> None:
    conn.execute(
        """
        INSERT INTO live_workflow_runs (
          run_id, issue, mode, status, dry_run, requested_by, started_at,
          finished_at, elapsed_sec, error, plan_json, result_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, '', ?, ?)
        """,
        (
            run_id,
            issue,
            "live_day_refresh_v1",
            status,
            int(dry_run),
            requested_by,
            _now_hk_iso(),
            _json_dumps(plan),
            _json_dumps({}),
        ),
    )
    for idx, step in enumerate(plan, start=1):
        conn.execute(
            """
            INSERT INTO live_workflow_steps (
              run_id, step_idx, step_key, label, status, command_json,
              started_at, finished_at, elapsed_sec, error, result_json
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, '', ?)
            """,
            (
                run_id,
                idx,
                step["step_key"],
                step["label"],
                "planned",
                _json_dumps(step.get("command") or []),
                _json_dumps({}),
            ),
        )


def _update_workflow_step(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    step_idx: int,
    status: str,
    started_at: str | None = None,
    finished_at: str | None = None,
    elapsed_sec: float | None = None,
    error: str = "",
    result: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        UPDATE live_workflow_steps
        SET status=?,
            started_at=COALESCE(?, started_at),
            finished_at=COALESCE(?, finished_at),
            elapsed_sec=COALESCE(?, elapsed_sec),
            error=?,
            result_json=?
        WHERE run_id=? AND step_idx=?
        """,
        (
            status,
            started_at,
            finished_at,
            elapsed_sec,
            error,
            _json_dumps(result or {}),
            run_id,
            step_idx,
        ),
    )


def _finish_workflow_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    started_at: datetime,
    error: str = "",
    result: dict[str, Any] | None = None,
) -> None:
    finished_at = _now_hk_iso()
    elapsed = max(0.0, (datetime.now(HK_TZ) - started_at).total_seconds())
    conn.execute(
        """
        UPDATE live_workflow_runs
        SET status=?, finished_at=?, elapsed_sec=?, error=?, result_json=?
        WHERE run_id=?
        """,
        (status, finished_at, elapsed, error, _json_dumps(result or {}), run_id),
    )


def _workflow_step_rows(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    if not _table_exists(conn, "live_workflow_steps"):
        return []
    return conn.execute(
        """
        SELECT *
        FROM live_workflow_steps
        WHERE run_id=?
        ORDER BY step_idx ASC
        """,
        (run_id,),
    ).fetchall()


def _workflow_run_payload(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "live_workflow_runs"):
        return None
    row = conn.execute("SELECT * FROM live_workflow_runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        return None
    steps = []
    for step in _workflow_step_rows(conn, run_id):
        steps.append(
            {
                "step_idx": step["step_idx"],
                "step_key": step["step_key"],
                "label": step["label"],
                "status": step["status"],
                "command": _json_loads(step["command_json"], []),
                "started_at": step["started_at"] or "",
                "finished_at": step["finished_at"] or "",
                "elapsed_sec": step["elapsed_sec"],
                "error": step["error"] or "",
                "result": _json_loads(step["result_json"], {}),
            }
        )
    return {
        "run_id": row["run_id"],
        "issue": row["issue"],
        "mode": row["mode"],
        "status": row["status"],
        "dry_run": bool(row["dry_run"]),
        "requested_by": row["requested_by"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"] or "",
        "elapsed_sec": row["elapsed_sec"],
        "error": row["error"] or "",
        "plan": _json_loads(row["plan_json"], []),
        "result": _json_loads(row["result_json"], {}),
        "steps": steps,
    }


def _latest_workflow_payload(conn: sqlite3.Connection, issue: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "live_workflow_runs"):
        return None
    row = conn.execute(
        """
        SELECT run_id
        FROM live_workflow_runs
        WHERE issue=?
        -- started_at is second-precision; rowid preserves insertion order for same-second runs.
        ORDER BY started_at DESC, rowid DESC
        LIMIT 1
        """,
        (issue,),
    ).fetchone()
    if not row:
        return None
    return _workflow_run_payload(conn, row["run_id"])


def _run_live_workflow(conn: sqlite3.Connection, db_path: Path, issue: str, *, dry_run: bool, requested_by: str) -> dict[str, Any]:
    _ensure_decision_snapshot_schema(conn)
    _ensure_live_workflow_schema(conn)
    resolved = _resolve_issue(conn, issue)
    plan = _live_workflow_step_defs(resolved, db_path)
    run_id = _workflow_run_id(resolved, dry_run)
    started_at = datetime.now(HK_TZ)
    _insert_workflow_run(
        conn,
        run_id=run_id,
        issue=resolved,
        dry_run=dry_run,
        status="dry_run" if dry_run else "running",
        plan=plan,
        requested_by=requested_by,
    )
    conn.commit()
    if dry_run:
        result = {"planned_steps": len(plan), "dry_run": True}
        _finish_workflow_run(conn, run_id=run_id, status="dry_run", started_at=started_at, result=result)
        conn.commit()
        return _workflow_run_payload(conn, run_id) or {"run_id": run_id, "issue": resolved, "status": "dry_run"}

    overall_status = "succeeded"
    overall_error = ""
    for idx, step in enumerate(plan, start=1):
        step_started = datetime.now(HK_TZ)
        _update_workflow_step(conn, run_id=run_id, step_idx=idx, status="running", started_at=_now_hk_iso())
        conn.commit()
        try:
            if step["kind"] == "subprocess":
                completed = subprocess.run(
                    step["command"],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=int(step.get("timeout_sec") or 240),
                    check=False,
                )
                stdout_tail = (completed.stdout or "")[-4000:]
                stderr_tail = (completed.stderr or "")[-4000:]
                if completed.returncode != 0:
                    raise RuntimeError(f"exit={completed.returncode}; stderr={stderr_tail or stdout_tail}")
                result = {"returncode": completed.returncode, "stdout_tail": stdout_tail, "stderr_tail": stderr_tail}
            elif step["kind"] == "internal_decision_snapshots":
                result = _materialize_issue_decision_snapshots(conn, resolved, only_date=None)
                conn.commit()
            else:
                raise RuntimeError(f"unknown workflow step kind: {step['kind']}")
            elapsed = max(0.0, (datetime.now(HK_TZ) - step_started).total_seconds())
            _update_workflow_step(
                conn,
                run_id=run_id,
                step_idx=idx,
                status="succeeded",
                finished_at=_now_hk_iso(),
                elapsed_sec=elapsed,
                result=result if isinstance(result, dict) else {"result": result},
            )
            conn.commit()
        except Exception as exc:
            elapsed = max(0.0, (datetime.now(HK_TZ) - step_started).total_seconds())
            overall_status = "failed"
            overall_error = str(exc)
            _update_workflow_step(
                conn,
                run_id=run_id,
                step_idx=idx,
                status="failed",
                finished_at=_now_hk_iso(),
                elapsed_sec=elapsed,
                error=overall_error,
            )
            conn.commit()
            break

    _finish_workflow_run(
        conn,
        run_id=run_id,
        status=overall_status,
        started_at=started_at,
        error=overall_error,
        result={"completed_steps": sum(1 for row in _workflow_step_rows(conn, run_id) if row["status"] == "succeeded")},
    )
    conn.commit()
    return _workflow_run_payload(conn, run_id) or {"run_id": run_id, "issue": resolved, "status": overall_status}


def _postmatch_review_run_payload(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "postmatch_review_runs"):
        return None
    row = conn.execute("SELECT * FROM postmatch_review_runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        return None
    return {
        "run_id": row["run_id"],
        "issue": row["issue"],
        "mode": row["mode"],
        "status": row["status"],
        "dry_run": bool(row["dry_run"]),
        "requested_by": row["requested_by"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"] or "",
        "elapsed_sec": row["elapsed_sec"],
        "error": row["error"] or "",
        "command": _json_loads(row["command_json"], []),
        "result": _json_loads(row["result_json"], {}),
    }


def _latest_postmatch_review_run_payload(conn: sqlite3.Connection, issue: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "postmatch_review_runs"):
        return None
    row = conn.execute(
        """
        SELECT run_id
        FROM postmatch_review_runs
        WHERE issue=?
        ORDER BY started_at DESC, rowid DESC
        LIMIT 1
        """,
        (issue,),
    ).fetchone()
    if not row:
        return None
    return _postmatch_review_run_payload(conn, row["run_id"])


def _run_postmatch_review_task(
    conn: sqlite3.Connection,
    db_path: Path,
    issue: str,
    *,
    dry_run: bool,
    requested_by: str,
) -> dict[str, Any]:
    _ensure_decision_snapshot_schema(conn)
    _ensure_postmatch_review_run_schema(conn)
    resolved = _resolve_issue(conn, issue)
    py = os.environ.get("PYTHON") or sys.executable
    command = [
        py,
        str(PROJECT_ROOT / "scripts/review_settled_matches.py"),
        "--db",
        str(db_path),
        "--issue",
        resolved,
    ]
    if dry_run:
        command.append("--dry-run")
    run_id = _postmatch_review_run_id(resolved, dry_run)
    started = datetime.now(HK_TZ)
    started_at = _now_hk_iso()
    conn.execute(
        """
        INSERT INTO postmatch_review_runs (
          run_id, issue, mode, status, dry_run, requested_by, started_at,
          finished_at, elapsed_sec, error, command_json, result_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, '', ?, ?)
        """,
        (
            run_id,
            resolved,
            "postmatch_review_v1",
            "dry_run" if dry_run else "running",
            int(dry_run),
            requested_by,
            started_at,
            _json_dumps(command),
            _json_dumps({}),
        ),
    )
    conn.commit()

    status = "dry_run" if dry_run else "succeeded"
    error = ""
    result: dict[str, Any] = {}
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if stdout:
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                result = {"stdout": stdout}
        if stderr:
            result = {**result, "stderr": stderr[-2000:]}
        if completed.returncode != 0:
            status = "failed"
            error = stderr or stdout or f"review_settled_matches exited {completed.returncode}"
    except Exception as exc:
        status = "failed"
        error = str(exc)

    finished_at = _now_hk_iso()
    elapsed = max(0.0, (datetime.now(HK_TZ) - started).total_seconds())
    conn.execute(
        """
        UPDATE postmatch_review_runs
        SET status=?, finished_at=?, elapsed_sec=?, error=?, result_json=?
        WHERE run_id=?
        """,
        (status, finished_at, elapsed, error, _json_dumps(result), run_id),
    )
    conn.commit()
    return _postmatch_review_run_payload(conn, run_id) or {"run_id": run_id, "issue": resolved, "status": status}


def _resolve_issue(conn: sqlite3.Connection, issue: str) -> str:
    if issue in {"current", "latest"}:
        row = conn.execute(
            "SELECT issue FROM issues WHERE is_current=1 ORDER BY ordinal ASC, last_seen_at DESC LIMIT 1"
        ).fetchone()
        if row:
            return str(row["issue"])
        row = conn.execute(
            "SELECT issue FROM issues ORDER BY last_seen_at DESC, ordinal ASC LIMIT 1"
        ).fetchone()
        if row:
            return str(row["issue"])
    row = conn.execute("SELECT 1 FROM matches WHERE issue=? LIMIT 1", (issue,)).fetchone()
    if row:
        return issue
    raise LookupError(f"500.com issue not found in SQLite: {issue}")


def _live_issue_exists(conn: sqlite3.Connection, issue: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM matches WHERE issue=? LIMIT 1", (issue,)).fetchone())


def _main_strategy_issue_exists(issue: str) -> bool:
    if any(str(row.get("issue", "")) == str(issue) for row in _main_strategy_issue_rows()):
        return True
    if _selected_ticket_rows_for_issue(str(_strategy_ticket_pool_csv()), issue):
        return True
    return bool(_match_context_for_issue(str(DEFAULT_MODEL_DB), issue))


def _resolve_main_strategy_issue(conn: sqlite3.Connection, issue: str) -> str:
    if issue in {"current", "latest"}:
        return _resolve_issue(conn, issue)
    if _main_strategy_issue_exists(issue):
        return str(issue)
    if _live_issue_exists(conn, issue):
        return str(issue)
    raise LookupError(f"main-strategy issue not found: {issue}")


def _latest_live_sp_subquery(issue: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        SELECT *
        FROM (
            SELECT
              l.*,
              ROW_NUMBER() OVER (
                PARTITION BY l.issue, l.row_idx
                ORDER BY COALESCE(l.source_updatetime, '') DESC, l.fetched_at DESC
              ) AS rn
            FROM live_sp_snapshots l
            WHERE l.issue=?
              AND l.playid=34
              AND l.sp_home IS NOT NULL
              AND l.sp_draw IS NOT NULL
              AND l.sp_away IS NOT NULL
        )
        WHERE rn=1
        """,
        (issue,),
    )


def _preclose_live_sp_subquery(issue: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        SELECT *
        FROM (
            SELECT
              l.*,
              ROW_NUMBER() OVER (
                PARTITION BY l.issue, l.row_idx
                ORDER BY COALESCE(l.source_updatetime, '') DESC, l.fetched_at DESC
              ) AS rn
            FROM live_sp_snapshots l
            JOIN matches m
              ON m.issue=l.issue
             AND m.match_idx=l.row_idx
            WHERE l.issue=?
              AND l.playid=34
              AND l.sp_home IS NOT NULL
              AND l.sp_draw IS NOT NULL
              AND l.sp_away IS NOT NULL
              AND (l.source_updatetime IS NULL OR m.end_time IS NULL OR l.source_updatetime <= m.end_time)
        )
        WHERE rn=1
        """,
        (issue,),
    )


def _first_live_sp_subquery(issue: str) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        SELECT *
        FROM (
            SELECT
              l.*,
              ROW_NUMBER() OVER (
                PARTITION BY l.issue, l.row_idx
                ORDER BY l.fetched_at ASC, COALESCE(l.source_updatetime, '') ASC
              ) AS rn
            FROM live_sp_snapshots l
            WHERE l.issue=?
              AND l.playid=34
              AND l.sp_home IS NOT NULL
              AND l.sp_draw IS NOT NULL
              AND l.sp_away IS NOT NULL
        )
        WHERE rn=1
        """,
        (issue,),
    )


def _issue_rows(
    conn: sqlite3.Connection,
    issue: str,
    *,
    only_date: str | None,
) -> list[sqlite3.Row]:
    live_sql, live_args = _latest_live_sp_subquery(issue)
    preclose_sql, preclose_args = _preclose_live_sp_subquery(issue)
    first_sql, first_args = _first_live_sp_subquery(issue)
    has_nowscore = _table_exists(conn, "nowscore_bjdc_matches")
    nowscore_cols = (
        """
          n.provider_match_id AS nowscore_provider_match_id,
          n.status_text AS nowscore_status_text,
          n.status AS nowscore_status,
          n.score AS nowscore_score,
          n.halftime_score AS nowscore_halftime_score,
          n.result_code AS nowscore_result_code,
          n.fetched_at AS nowscore_fetched_at,
          n.analysis_url AS nowscore_analysis_url,
          n.recommendation_url AS nowscore_recommendation_url,
          n.asian_url AS nowscore_asian_url,
          n.europe_url AS nowscore_europe_url
        """
        if has_nowscore
        else """
          NULL AS nowscore_provider_match_id,
          NULL AS nowscore_status_text,
          NULL AS nowscore_status,
          NULL AS nowscore_score,
          NULL AS nowscore_halftime_score,
          NULL AS nowscore_result_code,
          NULL AS nowscore_fetched_at,
          NULL AS nowscore_analysis_url,
          NULL AS nowscore_recommendation_url,
          NULL AS nowscore_asian_url,
          NULL AS nowscore_europe_url
        """
    )
    nowscore_join = (
        """
        LEFT JOIN nowscore_bjdc_matches n
          ON n.issue=m.issue
         AND n.match_idx=m.match_idx
        """
        if has_nowscore
        else ""
    )
    where = ["m.issue=?"]
    args: list[Any] = [issue]
    if only_date:
        where.append("substr(m.end_time, 1, 10)=?")
        args.append(only_date)
    sql = f"""
        SELECT
          m.issue,
          m.match_idx,
          m.fid,
          m.league,
          m.home,
          m.away,
          m.end_time,
          m.schedule_date,
          m.handicap_line,
          m.disabled,
          m.home_rank,
          m.away_rank,
          m.score,
          m.result_label,
          m.result_code,
          m.winning_sp,
          m.sp_home AS html_sp_home,
          m.sp_draw AS html_sp_draw,
          m.sp_away AS html_sp_away,
          m.avg_odds_home,
          m.avg_odds_draw,
          m.avg_odds_away,
          m.asian_handicap,
          m.fetched_at AS html_fetched_at,
          l.sp_home AS live_sp_home,
          l.sp_draw AS live_sp_draw,
          l.sp_away AS live_sp_away,
          l.source_updatetime,
          l.fetched_at AS live_fetched_at,
          pc.sp_home AS preclose_sp_home,
          pc.sp_draw AS preclose_sp_draw,
          pc.sp_away AS preclose_sp_away,
          pc.source_updatetime AS preclose_source_updatetime,
          pc.fetched_at AS preclose_fetched_at,
          fs.sp_home AS first_sp_home,
          fs.sp_draw AS first_sp_draw,
          fs.sp_away AS first_sp_away,
          fs.source_updatetime AS first_source_updatetime,
          fs.fetched_at AS first_fetched_at,
          {nowscore_cols}
        FROM matches m
        LEFT JOIN ({live_sql}) l
          ON l.issue=m.issue
         AND l.row_idx=m.match_idx
        LEFT JOIN ({preclose_sql}) pc
          ON pc.issue=m.issue
         AND pc.row_idx=m.match_idx
        LEFT JOIN ({first_sql}) fs
          ON fs.issue=m.issue
         AND fs.row_idx=m.match_idx
        {nowscore_join}
        WHERE {" AND ".join(where)}
        ORDER BY m.match_idx
    """
    return list(conn.execute(sql, (*live_args, *preclose_args, *first_args, *args)))


def _find_match(conn: sqlite3.Connection, match_id: str) -> tuple[str, int]:
    if "_" in match_id:
        issue, idx = match_id.split("_", 1)
        return issue, int(idx)
    if "-" in match_id:
        issue, idx = match_id.split("-", 1)
        return issue, int(idx)
    row = conn.execute(
        "SELECT issue, match_idx FROM matches WHERE fid=? ORDER BY issue DESC LIMIT 1",
        (_safe_int(match_id),),
    ).fetchone()
    if row:
        return str(row["issue"]), int(row["match_idx"])
    raise LookupError(f"500.com match not found: {match_id}")


def _match_id(row: sqlite3.Row) -> str:
    return f"{row['issue']}_{int(row['match_idx']):03d}"


def _visible_sp(row: sqlite3.Row, outcome: str) -> float | None:
    key = {"3": "sp_home", "1": "sp_draw", "0": "sp_away"}[outcome]
    return _safe_float(row[f"live_{key}"]) or _safe_float(row[f"html_{key}"])


def _sp_triplet(row: sqlite3.Row, prefix: str) -> dict[str, float | None]:
    return {
        "3": _safe_float(row[f"{prefix}_sp_home"]),
        "1": _safe_float(row[f"{prefix}_sp_draw"]),
        "0": _safe_float(row[f"{prefix}_sp_away"]),
    }


ASIAN_HANDICAP_VALUES = {
    "平手": 0.0,
    "平": 0.0,
    "半球": 0.5,
    "半": 0.5,
    "一球": 1.0,
    "一": 1.0,
    "球半": 1.5,
    "一球半": 1.5,
    "两球": 2.0,
    "二球": 2.0,
    "两": 2.0,
    "二": 2.0,
    "两球半": 2.5,
    "二球半": 2.5,
    "三球": 3.0,
    "三": 3.0,
    "三球半": 3.5,
    "四球": 4.0,
    "四": 4.0,
    "四球半": 4.5,
    "五球": 5.0,
    "五": 5.0,
}


def _parse_asian_line_part(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    numeric = re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text)
    if numeric:
        return float(text)
    return ASIAN_HANDICAP_VALUES.get(text)


def _asian_handicap_to_home_line(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    numeric = re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text)
    if numeric:
        return float(text)

    sign = 1.0 if text.startswith("受") else -1.0
    text = text.removeprefix("受").removeprefix("让").replace(" ", "")
    parts = [_parse_asian_line_part(part) for part in text.split("/") if part]
    if not parts or any(part is None for part in parts):
        return None
    magnitude = sum(float(part) for part in parts if part is not None) / len(parts)
    if magnitude == 0:
        return 0.0
    return sign * magnitude


def _line_gap(row: sqlite3.Row) -> float | None:
    beidan_line = _safe_float(row["handicap_line"])
    asian_line = _asian_handicap_to_home_line(row["asian_handicap"])
    if beidan_line is None or asian_line is None:
        return None
    return round(beidan_line - asian_line, 2)


def _sp_change_values(row: sqlite3.Row, current_sp: dict[str, float | None]) -> dict[str, float | None]:
    first_sp = _sp_triplet(row, "first")
    values: dict[str, float | None] = {}
    for code in OUTCOME_ORDER:
        first = first_sp[code]
        current = current_sp[code]
        values[code] = float(current) / float(first) - 1 if first and current else None
    return values


def _sp_change_label(values: dict[str, float | None]) -> str:
    labels = []
    for code in OUTCOME_ORDER:
        value = values[code]
        if value is None:
            continue
        labels.append(f"{OUTCOME_LABEL[code]}{value:+.1%}")
    return " ".join(labels) if labels else "样本不足"


def _complete_sp_triplet(values: dict[str, float | None]) -> bool:
    return all(values[code] is not None and float(values[code] or 0) > 0 for code in ("3", "1", "0"))


def _nowscore_is_finished(status: Any, status_text: Any) -> bool:
    text = str(status_text or "").strip()
    if "完场" in text:
        return True
    if text in {"上", "中", "下", "加", "点"} or "中场" in text or "半场" in text or "'" in text:
        return False
    return str(status or "").strip() == "finished"


def _row_has_result(row: sqlite3.Row) -> bool:
    nowscore_status = str(row["nowscore_status"] or "").strip() if "nowscore_status" in row.keys() else ""
    nowscore_status_text = str(row["nowscore_status_text"] or "").strip() if "nowscore_status_text" in row.keys() else ""
    nowscore_result = row["nowscore_result_code"] if "nowscore_result_code" in row.keys() else None
    return (
        row["winning_sp"] is not None
        or row["result_code"] is not None
        or (_nowscore_is_finished(nowscore_status, nowscore_status_text) and nowscore_result is not None)
    )


def _sp_source_timestamp(row: sqlite3.Row, source: str) -> str:
    if source.startswith("500_preclose") or source.startswith("preclose"):
        return row["preclose_source_updatetime"] or row["preclose_fetched_at"] or ""
    if source.startswith("500_live") or source.startswith("live"):
        return row["source_updatetime"] or row["live_fetched_at"] or ""
    if source.startswith("500_trade_html") or source.startswith("html"):
        return row["html_fetched_at"] or ""
    return ""


def _display_sp(row: sqlite3.Row) -> tuple[dict[str, float | None], str]:
    preclose_sp = _sp_triplet(row, "preclose")
    if _complete_sp_triplet(preclose_sp):
        return preclose_sp, "preclose_complete_sp"
    live_sp = _sp_triplet(row, "live")
    if _complete_sp_triplet(live_sp):
        return live_sp, "live_complete_sp"
    html_sp = _sp_triplet(row, "html")
    has_result = row["winning_sp"] is not None or row["result_code"] is not None
    if not has_result and _complete_sp_triplet(html_sp):
        return html_sp, "html_open_complete_sp"
    return {"3": None, "1": None, "0": None}, "missing_complete_sp"


def _prediction_sp(row: sqlite3.Row) -> tuple[dict[str, float | None], str]:
    preclose_sp = _sp_triplet(row, "preclose")
    if _complete_sp_triplet(preclose_sp):
        return preclose_sp, "500_preclose_sp_complete"
    has_result = _row_has_result(row)
    if has_result:
        return {"3": None, "1": None, "0": None}, "no_pre_result_complete_sp"
    live_sp = _sp_triplet(row, "live")
    if _complete_sp_triplet(live_sp):
        return live_sp, "500_live_sp_complete"
    html_sp = _sp_triplet(row, "html")
    if _complete_sp_triplet(html_sp):
        return html_sp, "500_trade_html_complete_open"
    return {"3": None, "1": None, "0": None}, "no_pre_result_complete_sp"


def _prob_from_avg_euro(row: sqlite3.Row) -> dict[str, float | None]:
    return _prob_from_odds(
        _safe_float(row["avg_odds_home"]),
        _safe_float(row["avg_odds_draw"]),
        _safe_float(row["avg_odds_away"]),
    )


def _prob_from_odds(home: float | None, draw: float | None, away: float | None) -> dict[str, float | None]:
    odds = [home, draw, away]
    if not all(v and v > 0 for v in odds):
        return {"3": None, "1": None, "0": None}
    inv = [1 / float(v) for v in odds]
    total = sum(inv)
    return {"3": inv[0] / total, "1": inv[1] / total, "0": inv[2] / total}


def _prob_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 0.30:
        return "<30"
    if value < 0.40:
        return "30-40"
    if value < 0.50:
        return "40-50"
    if value < 0.60:
        return "50-60"
    return ">=60"


def _handicap_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    rounded = round(float(value))
    if abs(float(value) - rounded) < 1e-6:
        value = float(rounded)
    if value <= -2:
        return "<=-2"
    if value == -1:
        return "-1"
    if value == 0:
        return "0"
    if value == 1:
        return "1"
    if value >= 2:
        return ">=2"
    return f"{value:.1f}"


def _count_key_parts(
    *,
    league: str,
    handicap_bucket: str,
    top_code: str,
    top_prob_bucket: str,
) -> list[tuple[str, ...]]:
    return [
        ("global",),
        ("hcp", handicap_bucket),
        ("hcp_top", handicap_bucket, top_code),
        ("hcp_top_p", handicap_bucket, top_code, top_prob_bucket),
        ("league_hcp_top_p", league, handicap_bucket, top_code, top_prob_bucket),
    ]


@lru_cache(maxsize=32)
def _handicap_calibration_counts(db_path_text: str, before_issue: str) -> dict[tuple[str, ...], tuple[int, int, int]]:
    path = Path(db_path_text)
    if not path.exists():
        return {}
    counts: dict[tuple[str, ...], list[int]] = defaultdict(lambda: [0, 0, 0])
    conn = _connect(path)
    try:
        rows = conn.execute(
            """
            SELECT
              issue,
              league,
              handicap_line_norm,
              result_code,
              official_500_avg_eu_home,
              official_500_avg_eu_draw,
              official_500_avg_eu_away
            FROM match_features
            WHERE has_trusted_settlement=1
              AND issue < ?
              AND result_code IN ('3','1','0')
              AND official_500_avg_eu_home > 1
              AND official_500_avg_eu_draw > 1
              AND official_500_avg_eu_away > 1
            """,
            (before_issue,),
        )
        for row in rows:
            probs = _prob_from_odds(
                _safe_float(row["official_500_avg_eu_home"]),
                _safe_float(row["official_500_avg_eu_draw"]),
                _safe_float(row["official_500_avg_eu_away"]),
            )
            if any(probs[code] is None for code in OUTCOME_ORDER):
                continue
            top_code = max(OUTCOME_ORDER, key=lambda code: float(probs[code] or 0))
            hcp_bucket = _handicap_bucket(_safe_float(row["handicap_line_norm"]))
            top_prob_bucket = _prob_bucket(probs[top_code])
            result_code = str(row["result_code"])
            result_idx = OUTCOME_ORDER.index(result_code)
            for key in _count_key_parts(
                league=str(row["league"] or ""),
                handicap_bucket=hcp_bucket,
                top_code=top_code,
                top_prob_bucket=top_prob_bucket,
            ):
                counts[key][result_idx] += 1
    finally:
        conn.close()
    return {key: tuple(value) for key, value in counts.items()}


def _smooth_distribution(
    prior: dict[str, float | None],
    counts: tuple[int, int, int] | None,
    alpha: float,
) -> dict[str, float | None]:
    if not counts:
        return prior
    total = sum(counts)
    if total <= 0:
        return prior
    return {
        code: (counts[idx] + alpha * float(prior[code] or 0)) / (total + alpha)
        for idx, code in enumerate(OUTCOME_ORDER)
    }


def _handicap_calibrated_probs(row: sqlite3.Row) -> tuple[dict[str, float | None], str]:
    market_probs = _prob_from_avg_euro(row)
    if any(market_probs[code] is None for code in OUTCOME_ORDER):
        return market_probs, "market_probability_missing"
    top_code = max(OUTCOME_ORDER, key=lambda code: float(market_probs[code] or 0))
    hcp_bucket = _handicap_bucket(_safe_float(row["handicap_line"]))
    top_prob_bucket = _prob_bucket(market_probs[top_code])
    keys = _count_key_parts(
        league=str(row["league"] or ""),
        handicap_bucket=hcp_bucket,
        top_code=top_code,
        top_prob_bucket=top_prob_bucket,
    )
    counts = _handicap_calibration_counts(str(DEFAULT_MODEL_DB), str(row["issue"]))
    calibrated = market_probs
    applied = []
    for key, alpha in zip(keys, (240.0, 160.0, 120.0, 80.0, 60.0)):
        if key in counts:
            calibrated = _smooth_distribution(calibrated, counts[key], alpha)
            applied.append(key[0])
    source = f"handicap_calibrated_hist_v1:{applied[-1]}" if applied else "handicap_calibrated_hist_v1:market_prior_only"
    return calibrated, source


def _ranked_outcomes(row: sqlite3.Row) -> tuple[list[tuple[str, float, float, float]], str]:
    probs, probability_source = _handicap_calibrated_probs(row)
    pred_sp, source = _prediction_sp(row)
    scored: list[tuple[str, float, float, float]] = []
    for code in OUTCOME_ORDER:
        p = probs[code]
        sp = pred_sp[code]
        if p and sp:
            scored.append((code, float(p), float(sp), float(p) * float(sp)))
    scored.sort(key=lambda item: (item[3], item[1]), reverse=True)
    return scored, f"{source};{probability_source}"


def _best_outcome(row: sqlite3.Row) -> tuple[str | None, float | None, float | None, str]:
    scored, source = _ranked_outcomes(row)
    if not scored:
        return None, None, None, source
    code, p, _sp, q = scored[0]
    if not p or q < 1.0:
        return None, None, None, source
    return code, p, q, source


def _coverage_from_ranked_outcomes(scored: list[tuple[str, float, float, float]]) -> tuple[list[str], str]:
    if not scored:
        return [], "no-buy"
    top_q = scored[0][3]
    if top_q < 1.0:
        return [], "no-buy"
    codes = [scored[0][0]]
    if len(scored) > 1:
        second_q = scored[1][3]
        if second_q >= 1.0 and second_q / max(top_q, 1e-9) >= 0.80:
            codes.append(scored[1][0])
    return codes, "double" if len(codes) == 2 else "single"


def _capture_status(row: sqlite3.Row) -> str:
    display_sp, _source = _display_sp(row)
    sp_count = sum(1 for code in ("3", "1", "0") if display_sp[code] is not None)
    euro_ok = all(row[k] is not None for k in ("avg_odds_home", "avg_odds_draw", "avg_odds_away"))
    if sp_count == 3 and euro_ok:
        return "ok"
    if sp_count > 0 or euro_ok:
        return "partial"
    return "missing"


def _match_summary(row: sqlite3.Row) -> dict[str, Any]:
    selected, confidence, q_score, selection_source = _best_outcome(row)
    ranked_outcomes, ranked_source = _ranked_outcomes(row)
    selection_codes, selection_type = _coverage_from_ranked_outcomes(ranked_outcomes)
    if selected and selected not in selection_codes:
        selection_codes = [selected]
        selection_type = "single"
    market_probs = _prob_from_avg_euro(row)
    probs, probability_source = _handicap_calibrated_probs(row)
    display_sp, display_sp_source = _display_sp(row)
    prediction_sp_source = ranked_source.split(";", 1)[0]
    prediction_sp_snapshot_ts = _sp_source_timestamp(row, prediction_sp_source)
    display_sp_snapshot_ts = _sp_source_timestamp(row, display_sp_source)
    probability_snapshot_ts = row["html_fetched_at"] or ""
    calculated_ts = datetime.now(timezone.utc).isoformat()
    sp_3 = display_sp["3"]
    sp_1 = display_sp["1"]
    sp_0 = display_sp["0"]
    sp_change = _sp_change_values(row, display_sp)
    sp_change_label = _sp_change_label(sp_change)
    source_ts = row["source_updatetime"] or row["live_fetched_at"] or row["nowscore_fetched_at"] or row["html_fetched_at"]
    nowscore_score = str(row["nowscore_score"] or "").strip()
    nowscore_status = str(row["nowscore_status"] or "").strip()
    nowscore_status_text = str(row["nowscore_status_text"] or "").strip()
    official_result_code = str(row["result_code"]) if row["result_code"] is not None else ""
    nowscore_result_code = str(row["nowscore_result_code"]) if row["nowscore_result_code"] is not None else ""
    result_code = official_result_code or (
        nowscore_result_code if _nowscore_is_finished(nowscore_status, nowscore_status_text) else ""
    )
    prediction_hit = result_code in selection_codes if result_code and selection_codes else None
    displayed_score = nowscore_score or row["score"]
    displayed_status = "settled" if row["winning_sp"] is not None else "open"
    return {
        "match_id": _match_id(row),
        "issue": str(row["issue"]),
        "match_idx": row["match_idx"],
        "league": row["league"],
        "kickoff_ts": row["end_time"],
        "kickoff_date": row["end_time"][:10] if row["end_time"] else "",
        "home": row["home"],
        "away": row["away"],
        "handicap_line": row["handicap_line"],
        "score": displayed_score,
        "halftime_score": row["nowscore_halftime_score"] or "",
        "live_score_status": nowscore_status,
        "live_score_status_text": row["nowscore_status_text"] or "",
        "live_score_source": "nowscore" if row["nowscore_provider_match_id"] else ("500_settlement" if row["score"] else ""),
        "nowscore_provider_match_id": row["nowscore_provider_match_id"],
        "nowscore_urls": {
            "analysis": row["nowscore_analysis_url"] or "",
            "recommendation": row["nowscore_recommendation_url"] or "",
            "asian": row["nowscore_asian_url"] or "",
            "europe": row["nowscore_europe_url"] or "",
        },
        "sp_3": sp_3,
        "sp_1": sp_1,
        "sp_0": sp_0,
        "eu_home": row["avg_odds_home"],
        "eu_draw": row["avg_odds_draw"],
        "eu_away": row["avg_odds_away"],
        "ah_line": row["asian_handicap"],
        "line_gap": _line_gap(row),
        "sp_drift_3": sp_change["3"],
        "sp_drift_1": sp_change["1"],
        "sp_drift_0": sp_change["0"],
        "sp_drift_band": sp_change_label if sp_change_label != "样本不足" else display_sp_source,
        "sp_snapshot_ts": display_sp_snapshot_ts,
        "display_sp_source": display_sp_source,
        "display_sp_snapshot_ts": display_sp_snapshot_ts,
        "prediction_sp_source": prediction_sp_source,
        "prediction_sp_snapshot_ts": prediction_sp_snapshot_ts,
        "probability_snapshot_ts": probability_snapshot_ts,
        "q_input_sp_snapshot_ts": prediction_sp_snapshot_ts,
        "q_input_probability_snapshot_ts": probability_snapshot_ts,
        "q_input_policy": "preclose_sp_if_available_else_live_sp_only_before_result",
        "q_calculated_ts": calculated_ts,
        "q_max": q_score,
        "q_score": q_score,
        "confidence_weight": confidence,
        "model_p_3": probs["3"],
        "model_p_1": probs["1"],
        "model_p_0": probs["0"],
        "market_p_3": market_probs["3"],
        "market_p_1": market_probs["1"],
        "market_p_0": market_probs["0"],
        "selection": selected,
        "selection_codes": selection_codes,
        "selection_source": selection_source,
        "probability_source": probability_source,
        "selection_type": selection_type if selected else "no-buy",
        "status": displayed_status,
        "capture_status": _capture_status(row),
        "result_code": result_code,
        "result_label": OUTCOME_LABEL.get(result_code, row["result_label"] or ""),
        "prediction_hit": prediction_hit,
        "winning_sp": row["winning_sp"],
        "generated_ts": source_ts or datetime.now(timezone.utc).isoformat(),
        "calculated_ts": calculated_ts,
    }


def _fallback_500_analysis_urls(fid: Any) -> dict[str, str]:
    if fid is None:
        return {}
    fid_text = str(fid)
    return {
        "data": f"https://odds.500.com/fenxi/shuju-{fid_text}.shtml",
        "recommendation": f"https://odds.500.com/fenxi/youliao-{fid_text}.shtml?channel=pc_score",
        "asian": f"https://odds.500.com/fenxi/yazhi-{fid_text}.shtml",
        "europe": f"https://odds.500.com/fenxi/ouzhi-{fid_text}.shtml",
    }


def _analysis_500(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    fid = row["fid"]
    base = {
        "fid": fid,
        "status": "missing",
        "fetched_at": "",
        "title": "",
        "description": "",
        "urls": _fallback_500_analysis_urls(fid),
        "home_recent": {"team": row["home"] or "", "summary": "", "rows": []},
        "away_recent": {"team": row["away"] or "", "summary": "", "rows": []},
        "h2h": {"summary": "", "rows": []},
        "league_table": "",
        "source": "odds.500.com/fenxi/shuju",
        "error": "",
    }
    if fid is None or not _table_exists(conn, "match_details_500"):
        return base
    detail = conn.execute(
        """
        SELECT *
        FROM match_details_500
        WHERE issue=? AND match_idx=?
        LIMIT 1
        """,
        (row["issue"], row["match_idx"]),
    ).fetchone()
    if not detail:
        return base
    payload: dict[str, Any] = {}
    if detail["payload_json"]:
        try:
            parsed = json.loads(str(detail["payload_json"]))
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    urls = payload.get("urls") if isinstance(payload.get("urls"), dict) else {}
    home_recent = payload.get("home_recent") if isinstance(payload.get("home_recent"), dict) else {}
    away_recent = payload.get("away_recent") if isinstance(payload.get("away_recent"), dict) else {}
    h2h = payload.get("h2h") if isinstance(payload.get("h2h"), dict) else {}
    return {
        "fid": fid,
        "status": detail["status"] or "missing",
        "fetched_at": detail["fetched_at"] or "",
        "title": detail["title"] or payload.get("title", ""),
        "description": detail["description"] or payload.get("description", ""),
        "urls": {
            **_fallback_500_analysis_urls(fid),
            **{str(k): str(v) for k, v in urls.items() if v},
        },
        "home_recent": {
            "team": home_recent.get("team") or row["home"] or "",
            "summary": detail["home_recent_summary"] or home_recent.get("summary", ""),
            "rows": home_recent.get("rows", []),
        },
        "away_recent": {
            "team": away_recent.get("team") or row["away"] or "",
            "summary": detail["away_recent_summary"] or away_recent.get("summary", ""),
            "rows": away_recent.get("rows", []),
        },
        "h2h": {
            "summary": detail["h2h_summary"] or h2h.get("summary", ""),
            "rows": h2h.get("rows", []),
        },
        "league_table": detail["league_table_summary"] or payload.get("league_table", ""),
        "source": "odds.500.com/fenxi/shuju",
        "error": detail["error"] or "",
    }


def _nowscore_detail_payload(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    if not _table_exists(conn, "nowscore_match_details"):
        return {}
    detail = conn.execute(
        """
        SELECT *
        FROM nowscore_match_details
        WHERE issue=? AND match_idx=?
        LIMIT 1
        """,
        (row["issue"], row["match_idx"]),
    ).fetchone()
    if not detail or detail["status"] != "ok":
        return {}
    try:
        payload = json.loads(str(detail["payload_json"] or "{}"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        highlights = json.loads(str(detail["highlights_json"] or "[]"))
    except json.JSONDecodeError:
        highlights = []
    payload["_detail_row"] = {
        "fetched_at": detail["fetched_at"] or "",
        "title": detail["title"] or "",
        "description": detail["description"] or "",
        "home_recent_summary": detail["home_recent_summary"] or "",
        "away_recent_summary": detail["away_recent_summary"] or "",
        "h2h_summary": detail["h2h_summary"] or "",
        "league_summary": detail["league_summary"] or "",
        "panlu_summary": detail["panlu_summary"] or "",
        "market_summary": detail["market_summary"] or "",
        "highlights": highlights if isinstance(highlights, list) else [],
    }
    return payload


def _analysis_nowscore(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    provider_id = row["nowscore_provider_match_id"]
    urls = {
        "data": row["nowscore_analysis_url"] or "",
        "recommendation": row["nowscore_recommendation_url"] or "",
        "asian": row["nowscore_asian_url"] or "",
        "europe": row["nowscore_europe_url"] or "",
    }
    base = {
        "fid": provider_id,
        "status": "missing",
        "fetched_at": row["nowscore_fetched_at"] or "",
        "title": "",
        "description": "",
        "urls": urls,
        "home_recent": {"team": row["home"] or "", "summary": "", "rows": []},
        "away_recent": {"team": row["away"] or "", "summary": "", "rows": []},
        "h2h": {"summary": "", "rows": []},
        "league_table": "",
        "source": "cp.nowscore.com/buy",
        "highlights": [],
        "market_summary": "",
        "odds_consensus": {},
        "error": "",
    }
    if not provider_id:
        return base
    detail_payload = _nowscore_detail_payload(conn, row)
    detail_row = detail_payload.get("_detail_row", {}) if isinstance(detail_payload.get("_detail_row"), dict) else {}
    recent = detail_payload.get("recent", {}) if isinstance(detail_payload.get("recent"), dict) else {}
    league = detail_payload.get("league", {}) if isinstance(detail_payload.get("league"), dict) else {}
    panlu = detail_payload.get("panlu", {}) if isinstance(detail_payload.get("panlu"), dict) else {}
    urls = detail_payload.get("urls", urls) if isinstance(detail_payload.get("urls"), dict) else urls
    if detail_payload:
        return {
            "fid": provider_id,
            "status": "ok",
            "fetched_at": detail_row.get("fetched_at", "") or row["nowscore_fetched_at"] or "",
            "title": detail_row.get("title", "") or detail_payload.get("title", "") or f"{row['home']} VS {row['away']} - 捷报数据",
            "description": detail_row.get("description", "") or detail_payload.get("description", ""),
            "urls": urls,
            "home_recent": {
                "team": row["home"] or "",
                "summary": recent.get("home_summary") or league.get("home_full") or "",
                "rows": [],
            },
            "away_recent": {
                "team": row["away"] or "",
                "summary": recent.get("away_summary") or league.get("away_full") or "",
                "rows": [],
            },
            "h2h": {
                "summary": recent.get("h2h_summary") or "",
                "rows": [],
            },
            "league_table": " | ".join(value for value in [
                league.get("home_full", ""),
                league.get("away_full", ""),
                league.get("home_half", ""),
                league.get("away_half", ""),
                panlu.get("home_full", ""),
                panlu.get("away_full", ""),
            ] if value),
            "source": "live.nowscore.com/analysis",
            "highlights": detail_row.get("highlights", []) or detail_payload.get("highlights", []),
            "market_summary": detail_row.get("market_summary", ""),
            "odds_consensus": detail_payload.get("odds_consensus", {}),
            "error": "",
        }
    score = str(row["nowscore_score"] or "").strip() or "-"
    halftime = str(row["nowscore_halftime_score"] or "").strip() or "-"
    status_text = str(row["nowscore_status_text"] or "").strip() or str(row["nowscore_status"] or "").strip() or "-"
    base.update({
        "status": "ok",
        "title": f"{row['home']} VS {row['away']} - 捷报数据",
        "description": f"捷报ID {provider_id}；赛况 {status_text}；比分 {score}；半场 {halftime}。",
        "home_recent": {"team": row["home"] or "", "summary": f"当前赛况 {status_text}", "rows": []},
        "away_recent": {"team": row["away"] or "", "summary": f"全场 {score}；半场 {halftime}", "rows": []},
        "h2h": {"summary": "点击数据分析查看捷报单场详情。", "rows": []},
        "league_table": "捷报用于实时比分、半场比分和单场分析入口；500.com 仍用于北单 SP 与结算字段。",
    })
    return base


def _match_intelligence(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    base = {
        "status": "missing",
        "fetched_at": "",
        "headline": "",
        "points": [],
        "tags": [],
        "stage": {},
        "sources": [],
        "source_count": 0,
        "error": "",
    }
    if not _table_exists(conn, "match_intel_digest"):
        return base
    digest_row = conn.execute(
        """
        SELECT *
        FROM match_intel_digest
        WHERE issue=? AND match_idx=?
        LIMIT 1
        """,
        (row["issue"], row["match_idx"]),
    ).fetchone()
    if not digest_row:
        return base
    digest: dict[str, Any] = {}
    if digest_row["digest_json"]:
        try:
            parsed = json.loads(str(digest_row["digest_json"]))
            if isinstance(parsed, dict):
                digest = parsed
        except json.JSONDecodeError:
            digest = {}
    sources: list[dict[str, Any]] = []
    if _table_exists(conn, "match_intel_sources"):
        for src in conn.execute(
            """
            SELECT source, source_tier, status, title, url, error
            FROM match_intel_sources
            WHERE issue=? AND match_idx=?
            ORDER BY
              CASE source_tier
                WHEN 'official' THEN 1
                WHEN 'editorial' THEN 2
                WHEN 'raw_data' THEN 3
                WHEN 'expert_pool' THEN 4
                ELSE 9
              END,
              source
            """,
            (row["issue"], row["match_idx"]),
        ):
            sources.append({
                "source": src["source"] or "",
                "tier": src["source_tier"] or "",
                "status": src["status"] or "missing",
                "title": src["title"] or "",
                "url": src["url"] or "",
                "error": src["error"] or "",
            })
    points = digest.get("points", [])
    tags = digest.get("tags", [])
    return {
        "status": digest_row["status"] or digest.get("status", "missing"),
        "fetched_at": digest_row["fetched_at"] or "",
        "headline": digest_row["headline"] or digest.get("headline", ""),
        "points": points if isinstance(points, list) else [],
        "tags": tags if isinstance(tags, list) else [],
        "stage": digest.get("stage", {}) if isinstance(digest.get("stage"), dict) else {},
        "sources": sources,
        "source_count": digest_row["source_count"] or digest.get("source_count", 0) or len(sources),
        "error": digest_row["error"] or "",
    }


def _outcome_text(code: str | None, summary: dict[str, Any]) -> str:
    if code == "3":
        return f"胜({summary.get('home') or '主'})"
    if code == "1":
        return "平"
    if code == "0":
        return f"负({summary.get('away') or '客'})"
    return "观察"


def _pct_text(value: float | None) -> str:
    return "缺" if value is None else f"{value:.1%}"


def _signed_pct_text(value: float | None) -> str:
    return "缺" if value is None else f"{value:+.1%}"


def _number_text(value: float | None, digits: int = 2) -> str:
    return "缺" if value is None else f"{value:.{digits}f}"


def _summary_outcome_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code in OUTCOME_ORDER:
        prob = _safe_float(summary.get(f"model_p_{code}"))
        sp = _safe_float(summary.get(f"sp_{code}"))
        market_prob = _safe_float(summary.get(f"market_p_{code}"))
        rows.append({
            "code": code,
            "label": _outcome_text(code, summary),
            "prob": prob,
            "sp": sp,
            "market_prob": market_prob,
            "q": (prob * sp) if prob is not None and sp is not None else None,
        })
    rows.sort(key=lambda item: (item["q"] is not None, item["q"] or -1, item["prob"] or -1), reverse=True)
    return rows


def _info_signal_from_text(text: str, summary: dict[str, Any]) -> tuple[str | None, dict[str, int]]:
    home = str(summary.get("home") or "")
    away = str(summary.get("away") or "")
    scores = {"3": 0, "1": 0, "0": 0}
    positive = ("取胜", "获胜", "赢", "胜券", "剑指", "看高", "晋级", "信心", "强势", "火力", "出色", "稳定", "不败", "优势", "头名", "零封")
    negative = ("败绩", "乏力", "隐患", "下滑", "失球", "平庸", "不擅", "跌跌撞撞", "争胜乏力", "防守端存在")
    draw_words = ("难分高下", "和局", "平分秋色", "握手言和", "战平", "平局", "平手", "和味")
    for segment in re.split(r"[，。；;,.!?？]", text):
        segment = segment.strip()
        if not segment:
            continue
        if any(word in segment for word in draw_words):
            scores["1"] += 2
        pos = sum(1 for word in positive if word in segment)
        neg = sum(1 for word in negative if word in segment)
        delta = pos - neg
        if delta == 0:
            continue
        if home and home in segment:
            scores["3"] += delta
        if away and away in segment:
            scores["0"] += delta
    best_code = max(scores, key=lambda code: scores[code])
    if scores[best_code] <= 0:
        return None, scores
    return best_code, scores


def _analysis_points(analysis: dict[str, Any]) -> list[str]:
    points: list[str] = []
    highlights = analysis.get("highlights")
    if isinstance(highlights, list):
        for item in highlights:
            text = str(item or "")
            if "℃" in text or "体育场" in text:
                continue
            points.append(text)
            if len(points) >= 2:
                break
    for key in ("home_recent", "away_recent", "h2h"):
        item = analysis.get(key)
        if isinstance(item, dict) and item.get("summary"):
            points.append(str(item["summary"]))
    compact: list[str] = []
    for point in points:
        text = re.sub(r"\s+", " ", point).strip()
        if text:
            compact.append(text)
        if len(compact) >= 3:
            break
    return compact


def _gpt_fixed_chain_decision(
    summary: dict[str, Any],
    analysis: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    rows = _summary_outcome_rows(summary)
    top = rows[0] if rows else {}
    top_code = str(top.get("code") or summary.get("selection") or "")
    top_label = _outcome_text(top_code, summary)
    top_q = _safe_float(top.get("q"))
    top_prob = _safe_float(top.get("prob"))
    top_sp = _safe_float(top.get("sp"))
    prob_candidates = [row for row in rows if row.get("prob") is not None]
    prob_top = max(prob_candidates, key=lambda item: float(item["prob"] or 0), default={})
    prob_top_code = str(prob_top.get("code") or "")
    if top_code not in OUTCOME_ORDER and prob_top_code in OUTCOME_ORDER:
        top_code = prob_top_code
        top_label = _outcome_text(top_code, summary)
    prob_top_label = _outcome_text(prob_top_code, summary)
    prob_top_prob = _safe_float(prob_top.get("prob"))
    second = rows[1] if len(rows) > 1 else {}
    second_code = str(second.get("code") or "")
    second_label = _outcome_text(second_code, summary)
    counter_scores: dict[str, float] = defaultdict(float)
    counter_reasons: dict[str, list[str]] = defaultdict(list)

    def add_counter_signal(code: str | None, weight: float, reason: str) -> None:
        if not code or code not in OUTCOME_ORDER or code == top_code:
            return
        counter_scores[code] += weight
        counter_reasons[code].append(reason)

    support: list[str] = []
    risks: list[str] = []
    chain: list[str] = []

    chain.append(
        f"概率/收益拆分：让球后概率最高是 {prob_top_label} {_pct_text(prob_top_prob)}；"
        f"EV优选是 {top_label}，其让球后概率 {_pct_text(top_prob)}，SP {_number_text(top_sp)}，q=概率×SP={_number_text(top_q)}。"
    )
    if prob_top_code and prob_top_code != top_code:
        risks.append(f"EV优选不是最高概率结果：最高概率为 {prob_top_label}，{top_label} 主要来自赔率补偿。")
        prob_gap = (prob_top_prob or 0) - (top_prob or 0)
        add_counter_signal(prob_top_code, 0.8 + max(0.0, prob_gap) * 3.0, f"最高概率方向是 {prob_top_label}。")
    selected_codes = summary.get("selection_codes") if isinstance(summary.get("selection_codes"), list) else []
    if selected_codes:
        support.append("模型EV建议：" + "+".join(_outcome_text(str(code), summary) for code in selected_codes) + "；依据是 q/预期收益，不等同于最高胜率预测。")
    if top_q is None or top_q < Q_STOP_THRESHOLD:
        risks.append(f"q 低于硬停线 {Q_STOP_THRESHOLD:.2f}，结果倾向只能作观察。")
    elif top_q >= 1.35:
        support.append(f"q={top_q:.2f}，赔率补偿后具备较强预期收益凸性。")
    else:
        support.append(f"q={top_q:.2f}，刚过预期收益买入线，需结合盘口和信息面确认。")

    line_gap = _safe_float(summary.get("line_gap"))
    if line_gap is None:
        risks.append("让球偏移缺失，盘口校验不完整。")
        chain.append("盘口校验：让球偏移缺失。")
    else:
        chain.append(f"盘口校验：北单让球 {summary.get('handicap_line')}，亚盘 {summary.get('ah_line') or '缺'}，让球偏移 {line_gap:+.2f}。")
        if abs(line_gap) >= 0.75:
            risks.append(f"让球偏移 {line_gap:+.2f} 偏大，优先降低单选确定性。")
            add_counter_signal(prob_top_code or second_code, 0.8, "北单让球与亚盘偏移偏大。")
        elif abs(line_gap) >= 0.5:
            risks.append(f"让球偏移 {line_gap:+.2f} 需要观察。")
            add_counter_signal(prob_top_code or second_code, 0.4, "北单让球与亚盘存在偏移。")
        else:
            support.append("北单让球与亚盘参考没有明显冲突。")

    consensus = summary.get("odds_consensus") if isinstance(summary.get("odds_consensus"), dict) else {}
    drift = consensus.get("drift") if isinstance(consensus.get("drift"), dict) else {}
    drift_key = {"3": "home", "1": "draw", "0": "away"}.get(top_code, "")
    selected_drift = _safe_float(drift.get(drift_key)) if drift_key else None
    if selected_drift is not None:
        chain.append(f"欧赔校验：{top_label} 均值变化 {_signed_pct_text(selected_drift)}。")
        if selected_drift >= 0.08:
            risks.append(f"{top_label} 欧赔上升 {_signed_pct_text(selected_drift)}，市场支持减弱。")
            add_counter_signal(prob_top_code or second_code, 0.9, f"{top_label} 欧赔上升，市场支持减弱。")
        elif selected_drift <= -0.08:
            support.append(f"{top_label} 欧赔下降 {_signed_pct_text(selected_drift)}，市场支持增强。")
    for code, key in {"3": "home", "1": "draw", "0": "away"}.items():
        if code == top_code:
            continue
        value = _safe_float(drift.get(key)) if isinstance(drift, dict) else None
        if value is not None and value <= -0.08:
            add_counter_signal(code, 0.7, f"{_outcome_text(code, summary)} 欧赔下降 {_signed_pct_text(value)}。")

    analysis_lines = _analysis_points(analysis)
    analysis_code: str | None = None
    if analysis_lines:
        chain.append("数据分析：" + "；".join(analysis_lines[:2]))
        support.append("数据分析已纳入：近期战绩/交锋/赔率均值摘要。")
        analysis_code, _analysis_scores = _info_signal_from_text(" ".join(analysis_lines), summary)
        if analysis_code and analysis_code == top_code:
            support.append(f"数据分析倾向与EV方向一致：{_outcome_text(analysis_code, summary)}。")
        elif analysis_code:
            risks.append(f"数据分析倾向偏向 {_outcome_text(analysis_code, summary)}，与EV方向 {top_label} 不一致。")
            add_counter_signal(analysis_code, 1.2, f"数据分析偏向 {_outcome_text(analysis_code, summary)}。")
    else:
        risks.append("数据分析摘要不足，不能补造伤停或赛事情报。")

    intel_points = intelligence.get("points") if isinstance(intelligence.get("points"), list) else []
    intel_text = " ".join(str(point) for point in intel_points)
    intel_code, intel_scores = _info_signal_from_text(intel_text, summary)
    if intel_text:
        chain.append("情报摘要：" + re.sub(r"\s+", " ", intel_text).strip()[:180])
    if intel_code:
        intel_label = _outcome_text(intel_code, summary)
        if intel_code == top_code:
            support.append(f"情报倾向与EV优选方向一致：{intel_label}。")
        else:
            risks.append(f"情报倾向偏向 {intel_label}，与EV优选方向 {top_label} 不一致。")
            add_counter_signal(intel_code, 1.5, f"情报倾向偏向 {intel_label}。")
    elif intel_points:
        support.append("情报摘要未给出明确反向信号。")

    high_market_risk = any("欧赔上升" in item or "偏移" in item for item in risks)
    stop_reasons: list[str] = []
    if top_q is None or top_q < Q_STOP_THRESHOLD:
        stop_reasons.append(f"最大q={_number_text(top_q)} 低于硬停线 {Q_STOP_THRESHOLD:.2f}，EV不足。")
    decision_codes: list[str] = []
    counter_code = max(counter_scores, key=lambda code: counter_scores[code], default="")
    counter_score = counter_scores.get(counter_code, 0.0)
    counter_label = _outcome_text(counter_code, summary) if counter_code else ""
    should_bet_counter = bool(counter_code) and (
        counter_score >= 2.0
        or (counter_score >= 1.5 and high_market_risk and (top_q or 0) < 1.60)
    )
    primary_code = counter_code if should_bet_counter else top_code
    if should_bet_counter:
        decision_codes = [primary_code]
        if top_code and top_code != primary_code and top_q is not None:
            decision_codes.append(top_code)
            support.append(f"保护逻辑：q/EV 倾向仍是 {top_label}，但反面信息集中，主押 {counter_label}，用 {top_label} 对冲。")
        reasons = "；".join(counter_reasons.get(counter_code, [])[:3])
        chain.append(f"押保拆分：反面信号评分 {counter_score:.1f}，主押切到 {counter_label}；EV方向 {top_label} 只作保护。{reasons}")
        judgment = f"{counter_label}为押，保{top_label}" if top_code != primary_code else counter_label
    else:
        model_ev_codes = [str(code) for code in selected_codes if str(code) in OUTCOME_ORDER]
        if top_code and top_code in OUTCOME_ORDER and top_code not in model_ev_codes:
            model_ev_codes.insert(0, top_code)
        decision_codes = model_ev_codes or ([top_code] if top_code in OUTCOME_ORDER else [])
        if len(decision_codes) > 1:
            protected = "+".join(_outcome_text(code, summary) for code in decision_codes[1:])
            chain.append(
                f"押保拆分：反面信号评分 {counter_score:.1f}，未达到反打阈值；"
                f"主押沿用EV方向 {top_label}，并保留模型EV双选保护 {protected}。"
            )
            judgment = f"{top_label}为押，保{protected}"
        elif decision_codes:
            chain.append(f"押保拆分：反面信号评分 {counter_score:.1f}，未达到反打阈值；主押沿用EV方向 {top_label}，不额外保护。")
            judgment = top_label
        else:
            judgment = "待预测"
    if stop_reasons:
        chain.append("停牌提示：" + "；".join(stop_reasons) + " 押/保方向保留，仅作为观察标签。")

    risk_penalty = min(0.28, 0.08 * len(risks))
    support_bonus = min(0.14, 0.035 * len(support))
    q_bonus = min(0.18, max(0.0, (top_q or 0) - 1.0) * 0.25)
    prob_bonus = min(0.10, max(0.0, top_prob or 0) * 0.20)
    confidence = max(0.25, min(0.82, 0.42 + q_bonus + prob_bonus + support_bonus - risk_penalty))
    confidence_label = "高" if confidence >= 0.68 else "中" if confidence >= 0.48 else "低"
    chain.append(f"裁决：{judgment}；置信 {confidence_label}。")
    explanation = "固定决策链：押=LLM综合盘口/数据/情报后的主判断；保=当q/EV倾向与LLM主押不一致时的保护对冲；停=风控观察标签，不清空押/保；" + " ".join(chain[-3:])
    return {
        "judgment": judgment,
        "selection_codes": decision_codes,
        "stop_flag": bool(stop_reasons),
        "stop_reasons": stop_reasons,
        "confidence": round(confidence, 3),
        "confidence_label": confidence_label,
        "support": support[:5],
        "risks": risks[:5],
        "chain": chain,
        "explanation": explanation,
        "source": "gpt_fixed_decision_chain_v3_bet_protect_stop",
    }


def _selection_type_from_codes(codes: list[str]) -> str:
    if not codes:
        return "no-buy"
    if len(codes) >= 3:
        return "full"
    if len(codes) == 2:
        return "double"
    return "single"


def _selection_codes_from_value(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").replace(",", "+").replace("/", "+").split("+")
    return [str(code).strip() for code in raw if str(code).strip() in OUTCOME_ORDER]


def _structured_shadow_csv_candidates(issue: str, release: dict[str, Any] | None = None) -> list[Path]:
    shadow_dir = _strategy_shadow_dir(release)
    candidates = [
        path
        for path in shadow_dir.glob(f"{issue}_*/structured_shadow_{issue}.csv")
        if path.is_file()
    ]
    return sorted(candidates, key=lambda path: (path.parent.name, path.stat().st_mtime))


def _structured_shadow_rows_from_csv(path: Path) -> tuple[dict[int, dict[str, Any]], str]:
    rows: dict[int, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            idx = _safe_int(row.get("match_idx"))
            if idx is None:
                continue
            rows[idx] = dict(row)
    try:
        source = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        source = str(path)
    return rows, source


def _shadow_variant_id(rows: dict[int, dict[str, Any]]) -> str:
    first = next(iter(rows.values()), {})
    return str(first.get("shadow_arm") or SHADOW_DECISION_VARIANT_ID)


def _shadow_variant_display_label(variant_id: str) -> str:
    return str(variant_id or SHADOW_DECISION_VARIANT_ID).replace("_", " ")


def _decision_variant_version_key(variant_id: Any) -> tuple[int, int, int, str]:
    text = str(variant_id or "")
    match = re.search(r"(?:^|v)(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return (-1, -1, -1, text)
    major, minor, revision = (int(part) for part in match.groups())
    return (major, minor, revision, text)


def _decision_variant_default_key(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
    variant_id = str(item.get("variant_id") or item.get("version_id") or "")
    major, minor, revision, text = _decision_variant_version_key(variant_id)
    if "_execution_late_proxy_" in variant_id:
        execution_rank = 2
    elif "_execution_strict_" in variant_id:
        execution_rank = 1
    else:
        execution_rank = 0
    return (major, minor, revision, execution_rank, text)


def _structured_shadow_variant_scan(
    issue: str,
    release: dict[str, Any] | None = None,
) -> tuple[list[tuple[dict[int, dict[str, Any]], str]], list[str]]:
    allowed_shadow_ids = _manifest_variant_ids(release, kind=SHADOW_DECISION_VARIANT_KIND)
    variants: dict[str, tuple[dict[int, dict[str, Any]], str, float]] = {}
    suppressed: set[str] = set()
    for path in _structured_shadow_csv_candidates(issue, release):
        rows, source = _structured_shadow_rows_from_csv(path)
        if not rows:
            continue
        variant_id = _shadow_variant_id(rows)
        if variant_id not in allowed_shadow_ids:
            suppressed.add(variant_id)
            continue
        mtime = path.stat().st_mtime
        existing = variants.get(variant_id)
        if existing is None or mtime >= existing[2]:
            variants[variant_id] = (rows, source, mtime)

    def sort_key(item: tuple[str, tuple[dict[int, dict[str, Any]], str, float]]) -> tuple[int, int, int, str]:
        return _decision_variant_version_key(item[0])

    return (
        [(rows, source) for _variant_id, (rows, source, _mtime) in sorted(variants.items(), key=sort_key)],
        sorted(suppressed),
    )


def _structured_shadow_variants(issue: str, release: dict[str, Any] | None = None) -> list[tuple[dict[int, dict[str, Any]], str]]:
    variants, _suppressed = _structured_shadow_variant_scan(issue, release)
    return variants


def _issue_all_has_result(rows: list[sqlite3.Row]) -> bool:
    return bool(rows) and all(_row_has_result(row) for row in rows)


def _active_decision_variant(summary: dict[str, Any]) -> dict[str, Any]:
    codes = _selection_codes_from_value(summary.get("llm_selection_codes") or summary.get("selection_codes"))
    primary = codes[0] if codes else ""
    result_code = str(summary.get("result_code") or "")
    prediction_hit = result_code in codes if result_code and codes else None
    manifest = _manifest_variant_by_id().get(ACTIVE_DECISION_VARIANT_ID, {})
    version = summary.get("decision_chain_version") or _active_version_bundle()["decision_chain_version"]
    return {
        "variant_id": ACTIVE_DECISION_VARIANT_ID,
        "kind": ACTIVE_DECISION_VARIANT_KIND,
        "family": "active_snapshot",
        "label": ACTIVE_DECISION_VARIANT_LABEL,
        "display_label": ACTIVE_DECISION_VARIANT_DISPLAY_LABEL,
        "version": version,
        "source": "active_snapshot",
        "is_default": bool(manifest.get("is_default", False)),
        "recommendation": summary.get("llm_judgment") or ("停" if not codes else "+".join(OUTCOME_LABEL[code] for code in codes)),
        "primary_pick": primary,
        "protect_picks": codes[1:],
        "selection_codes": codes,
        "selection_type": summary.get("llm_selection_type") or summary.get("selection_type") or _selection_type_from_codes(codes),
        "stop_flag": bool(summary.get("llm_stop_flag")) if summary.get("llm_stop_flag") is not None else not codes,
        "q_score": summary.get("llm_q_score") if summary.get("llm_q_score") is not None else summary.get("q_score"),
        "probability": summary.get("llm_probability") if summary.get("llm_probability") is not None else summary.get("confidence_weight"),
        "confidence_label": summary.get("llm_confidence_label") or "",
        "prediction_hit": prediction_hit,
        "primary_hit": result_code == primary if result_code and primary else None,
        "coverage_hit": prediction_hit,
    }


def _shadow_decision_variant(row: dict[str, Any], source_path: str, *, result_code: str = "") -> dict[str, Any]:
    codes = _selection_codes_from_value(row.get("shadow_selection_codes"))
    variant_id = str(row.get("shadow_arm") or SHADOW_DECISION_VARIANT_ID)
    manifest = _manifest_variant_by_id().get(variant_id, {})
    primary = str(row.get("shadow_primary") or (codes[0] if codes else ""))
    if primary not in OUTCOME_ORDER:
        primary = codes[0] if codes else ""
    primary_hit = _csv_bool(row, "shadow_primary_hit")
    coverage_hit = _csv_bool(row, "shadow_coverage_hit")
    if result_code and codes:
        primary_hit = result_code == primary if primary else None
        coverage_hit = result_code in codes
    return {
        "variant_id": variant_id,
        "kind": SHADOW_DECISION_VARIANT_KIND,
        "family": SHADOW_DECISION_FAMILY,
        "label": manifest.get("label") or _shadow_variant_display_label(variant_id),
        "display_label": _shadow_variant_display_label(variant_id),
        "version": row.get("shadow_version") or SHADOW_DECISION_VERSION,
        "source": "structured_shadow_csv",
        "source_path": source_path,
        "is_default": bool(manifest.get("is_default", False)),
        "recommendation": row.get("shadow_judgment") or ("停" if not codes else "+".join(OUTCOME_LABEL[code] for code in codes)),
        "primary_pick": primary,
        "protect_picks": codes[1:],
        "selection_codes": codes,
        "selection_type": row.get("selection_type") or _selection_type_from_codes(codes),
        "stop_flag": _csv_bool(row, "shadow_stop_flag") if row.get("shadow_stop_flag") != "" else not codes,
        "q_score": _safe_float(row.get("max_q")),
        "probability": _safe_float(row.get(f"p_{primary}")) if primary else _safe_float(row.get("prob_top")),
        "confidence_label": row.get("shadow_confidence_label") or "",
        "prediction_hit": coverage_hit,
        "primary_hit": primary_hit,
        "coverage_hit": coverage_hit,
        "execution_policy_version": row.get("execution_policy_version") or "",
        "execution_policy_name": row.get("execution_policy_name") or "",
        "execution_action": row.get("execution_action") or "",
        "execution_reasons": _csv_semicolon_list(row, "execution_reasons"),
        "execution_source_action": row.get("execution_source_action") or "",
        "execution_recommended_codes": row.get("execution_recommended_codes") or "",
        "execution_double_codes": row.get("execution_double_codes") or "",
        "execution_full_score": _safe_float(row.get("execution_full_score")),
        "execution_full_candidate": _csv_bool(row, "execution_full_candidate"),
        "execution_full_kept": _csv_bool(row, "execution_full_kept"),
        "execution_segment_idx": _safe_int(row.get("execution_segment_idx")),
        "execution_unlock_state": row.get("execution_unlock_state") or "",
        "notes": [
            note
            for note in [
                f"prob_top={row.get('prob_top')}" if row.get("prob_top") else "",
                f"q_top={row.get('q_top')}" if row.get("q_top") else "",
                row.get("risk_tags", ""),
            ]
            if note
        ],
        "decision_chain": _json_loads(row.get("shadow_chain_json"), []),
        "decision_categories": _json_loads(row.get("shadow_categories_json"), []),
    }


def _manifest_decision_variants(release: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    release = release or _active_strategy_release()
    variants = release.get("decision_variants", [])
    return [item for item in variants if isinstance(item, dict)]


def _manifest_variant_by_id(release: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("variant_id") or ""): item
        for item in _manifest_decision_variants(release)
        if item.get("variant_id")
    }


def _manifest_variant_ids(release: dict[str, Any] | None = None, *, kind: str | None = None) -> set[str]:
    return {
        str(item.get("variant_id") or "")
        for item in _manifest_decision_variants(release)
        if item.get("variant_id") and (kind is None or item.get("kind") == kind)
    }


def _manifest_default_active_variant(release: dict[str, Any] | None = None) -> dict[str, Any]:
    variants = _manifest_decision_variants(release)
    for item in variants:
        if item.get("kind") == ACTIVE_DECISION_VARIANT_KIND and item.get("is_default"):
            return item
    for item in variants:
        if item.get("kind") == ACTIVE_DECISION_VARIANT_KIND:
            return item
    return {}


def _shadow_decision_option(
    rows: dict[int, dict[str, Any]],
    source_path: str,
    *,
    release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    first = next(iter(rows.values()), {})
    variant_id = first.get("shadow_arm") or SHADOW_DECISION_VARIANT_ID
    manifest = _manifest_variant_by_id(release).get(str(variant_id), {})
    return {
        "variant_id": variant_id,
        "kind": SHADOW_DECISION_VARIANT_KIND,
        "family": SHADOW_DECISION_FAMILY,
        "label": manifest.get("label") or _shadow_variant_display_label(variant_id),
        "display_label": _shadow_variant_display_label(variant_id),
        "version": first.get("shadow_version") or manifest.get("version_id") or SHADOW_DECISION_VERSION,
        "version_id": manifest.get("version_id") or first.get("shadow_version") or SHADOW_DECISION_VERSION,
        "source": "structured_shadow_csv",
        "source_path": source_path,
        "artifact_key": manifest.get("artifact_key", "structured_shadow_dir"),
        "is_default": bool(manifest.get("is_default", False)),
        "selectable": bool(manifest.get("selectable", True)),
        "available": True,
    }


def _is_execution_strict_variant_id(variant_id: str) -> bool:
    return "_execution_strict_" in variant_id


def _is_execution_late_proxy_variant_id(variant_id: str) -> bool:
    return "_execution_late_proxy_" in variant_id


def _manifest_shadow_option(manifest: dict[str, Any], *, available: bool) -> dict[str, Any]:
    variant_id = str(manifest.get("variant_id") or "")
    return {
        "variant_id": variant_id,
        "kind": SHADOW_DECISION_VARIANT_KIND,
        "family": SHADOW_DECISION_FAMILY,
        "label": manifest.get("label") or _shadow_variant_display_label(variant_id),
        "display_label": _shadow_variant_display_label(variant_id),
        "version": manifest.get("version_id") or "",
        "version_id": manifest.get("version_id") or "",
        "source": "structured_shadow_csv",
        "source_path": "",
        "artifact_key": manifest.get("artifact_key", "structured_shadow_dir"),
        "is_default": bool(manifest.get("is_default", False)),
        "selectable": bool(manifest.get("selectable", True)),
        "available": available,
    }


def _missing_manifest_shadow_options(
    present_variant_ids: set[str],
    release: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for manifest in _manifest_decision_variants(release):
        variant_id = str(manifest.get("variant_id") or "")
        if manifest.get("kind") != SHADOW_DECISION_VARIANT_KIND or not variant_id:
            continue
        if variant_id in present_variant_ids:
            continue
        # late_proxy is only actionable after the late-refresh artifact exists.
        if _is_execution_late_proxy_variant_id(variant_id):
            continue
        if _is_execution_strict_variant_id(variant_id):
            options.append(_manifest_shadow_option(manifest, available=False))
    return options


def _manifest_shadow_placeholder_decision_variant(manifest: dict[str, Any]) -> dict[str, Any]:
    variant_id = str(manifest.get("variant_id") or "")
    if not _is_execution_strict_variant_id(variant_id):
        return {}
    return {
        "variant_id": variant_id,
        "kind": SHADOW_DECISION_VARIANT_KIND,
        "family": SHADOW_DECISION_FAMILY,
        "label": manifest.get("label") or _shadow_variant_display_label(variant_id),
        "display_label": _shadow_variant_display_label(variant_id),
        "version": manifest.get("version_id") or "",
        "version_id": manifest.get("version_id") or "",
        "source": "structured_shadow_csv",
        "source_path": "",
        "is_default": bool(manifest.get("is_default", False)),
        "available": False,
        "recommendation": "等待晚盘",
        "primary_pick": "",
        "protect_picks": [],
        "selection_codes": [],
        "selection_type": "no-buy",
        "stop_flag": True,
        "q_score": None,
        "probability": None,
        "confidence_label": "",
        "prediction_hit": None,
        "primary_hit": None,
        "coverage_hit": None,
        "execution_policy_version": manifest.get("version_id") or "",
        "execution_policy_name": "strict_fullcap2",
        "execution_action": "skip_wait_late_refresh",
        "execution_reasons": ["execution_artifact_missing_for_issue"],
        "execution_source_action": "wait_late_refresh",
        "execution_recommended_codes": "",
        "execution_double_codes": "",
        "execution_full_score": None,
        "execution_full_candidate": False,
        "execution_full_kept": False,
        "execution_segment_idx": None,
        "execution_unlock_state": "waiting_late_refresh",
        "notes": ["strict execution artifact missing; no executable pick"],
        "decision_chain": [],
        "decision_categories": [],
    }


def _normalize_decision_variant_defaults(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not options:
        return options
    shadow_options = [
        item for item in options
        if item.get("kind") == SHADOW_DECISION_VARIANT_KIND and item.get("variant_id")
    ]
    if shadow_options:
        default_variant_id = str(max(
            shadow_options,
            key=_decision_variant_default_key,
        ).get("variant_id") or "")
    else:
        default_option = next((item for item in options if item.get("is_default")), options[0])
        default_variant_id = str(default_option.get("variant_id") or "")
    for item in options:
        item["is_default"] = bool(default_variant_id and str(item.get("variant_id") or "") == default_variant_id)
    return options


def _decision_variant_options(
    shadow_variants: list[tuple[dict[int, dict[str, Any]], str]] | None = None,
    *,
    release: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    active_manifest = _manifest_default_active_variant(release)
    active_variant_id = str(active_manifest.get("variant_id") or ACTIVE_DECISION_VARIANT_ID)
    options = [
        {
            "variant_id": active_variant_id,
            "kind": ACTIVE_DECISION_VARIANT_KIND,
            "family": "active_snapshot",
            "label": active_manifest.get("label") or ACTIVE_DECISION_VARIANT_LABEL,
            "display_label": ACTIVE_DECISION_VARIANT_DISPLAY_LABEL,
            "version": active_manifest.get("version_id") or _active_version_bundle()["decision_chain_version"],
            "version_id": active_manifest.get("version_id") or "",
            "source": "active_snapshot",
            "is_default": bool(active_manifest.get("is_default", False)),
            "selectable": bool(active_manifest.get("selectable", True)),
            "available": True,
        }
    ]
    for rows, source_path in shadow_variants or []:
        if rows and source_path:
            option = _shadow_decision_option(rows, source_path, release=release)
            options.append(option)
    present_shadow_ids = {
        str(item.get("variant_id") or "")
        for item in options
        if item.get("kind") == SHADOW_DECISION_VARIANT_KIND
    }
    options.extend(_missing_manifest_shadow_options(present_shadow_ids, release))
    return _normalize_decision_variant_defaults(options)


def _strategy_version_context(
    release: dict[str, Any],
    options: list[dict[str, Any]],
    requested_variant_id: str | None = None,
    *,
    suppressed_shadow_variant_ids: list[str] | None = None,
) -> dict[str, Any]:
    requested = str(requested_variant_id or "").strip()
    default_option = next((item for item in options if item.get("is_default")), options[0] if options else {})
    selected_option = next((item for item in options if str(item.get("variant_id") or "") == requested), None) if requested else None
    selection_status = "ok"
    selection_error = ""
    if requested and selected_option is None:
        selected_option = default_option
        selection_status = "unavailable"
        selection_error = f"decision variant not available for this issue: {requested}"
    elif selected_option is None:
        selected_option = default_option
    if selected_option and selected_option.get("available") is False and selection_status == "ok":
        selection_status = "degraded"
        selection_error = f"decision variant artifact unavailable for this issue: {selected_option.get('variant_id')}"

    release_payload = _strategy_release_public_payload(release)
    if release_payload.get("release_load_status") == "degraded" and selection_status == "ok":
        selection_status = "degraded"
    if release_payload.get("artifact_health", {}).get("missing_required") and selection_status == "ok":
        selection_status = "degraded"
        selection_error = "strategy release has missing required artifacts"
    contract_warnings = []
    if suppressed_shadow_variant_ids:
        contract_warnings.append({
            "type": "undeclared_shadow_artifacts_suppressed",
            "variant_ids": suppressed_shadow_variant_ids,
            "message": "shadow artifacts not declared in strategy release manifest were suppressed",
        })

    return {
        "schema_version": "strategy_version_context_v1",
        "requested_variant_id": requested,
        "selected_variant_id": str(selected_option.get("variant_id") or "") if selected_option else "",
        "selection_status": selection_status,
        "selection_error": selection_error,
        "available_variant_ids": [str(item.get("variant_id") or "") for item in options if item.get("variant_id")],
        "contract_warnings": contract_warnings,
        "options": options,
        "strategy_release": release_payload,
    }


def _attach_selected_decision_variant(
    matches: list[dict[str, Any]],
    selected_variant_id: str | None,
) -> list[dict[str, Any]]:
    requested = str(selected_variant_id or "").strip()
    for match in matches:
        variants = [item for item in match.get("decision_variants", []) if isinstance(item, dict)]
        default_variant = next((item for item in variants if item.get("is_default")), variants[0] if variants else {})
        selected = next((item for item in variants if str(item.get("variant_id") or "") == requested), None) if requested else None
        status = "ok"
        if requested and selected is None:
            selected = default_variant
            status = "unavailable"
        elif selected is None:
            selected = default_variant
        match["selected_decision_variant_id"] = str(selected.get("variant_id") or "") if selected else ""
        match["selected_decision_variant"] = selected or {}
        match["selected_decision_variant_status"] = status
    return matches


def _compact_decision_variant(variant: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "variant_id",
        "kind",
        "family",
        "label",
        "display_label",
        "version",
        "version_id",
        "source",
        "is_default",
        "available",
        "recommendation",
        "primary_pick",
        "protect_picks",
        "selection_codes",
        "selection_type",
        "stop_flag",
        "q_score",
        "probability",
        "confidence_label",
        "prediction_hit",
        "primary_hit",
        "coverage_hit",
        "execution_policy_version",
        "execution_policy_name",
        "execution_action",
        "execution_reasons",
        "execution_source_action",
        "execution_recommended_codes",
        "execution_double_codes",
        "execution_full_score",
        "execution_full_candidate",
        "execution_full_kept",
        "execution_segment_idx",
        "execution_unlock_state",
    }
    return {key: value for key, value in variant.items() if key in keep}


def _dashboard_summary_match(match: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "match_id",
        "issue",
        "match_idx",
        "league",
        "kickoff_ts",
        "kickoff_date",
        "home",
        "away",
        "handicap_line",
        "score",
        "halftime_score",
        "live_score_status",
        "live_score_status_text",
        "sp_3",
        "sp_1",
        "sp_0",
        "eu_home",
        "eu_draw",
        "eu_away",
        "ah_line",
        "line_gap",
        "sp_drift_3",
        "sp_drift_1",
        "sp_drift_0",
        "sp_drift_band",
        "q_max",
        "q_score",
        "confidence_weight",
        "model_p_3",
        "model_p_1",
        "model_p_0",
        "market_p_3",
        "market_p_1",
        "market_p_0",
        "model_selection",
        "model_selection_codes",
        "model_selection_type",
        "model_selection_source",
        "model_prediction_hit",
        "llm_judgment",
        "llm_selection",
        "llm_selection_codes",
        "llm_selection_type",
        "llm_confidence",
        "llm_confidence_label",
        "llm_source",
        "llm_q_score",
        "llm_probability",
        "llm_prediction_hit",
        "llm_stop_flag",
        "selection",
        "selection_codes",
        "selection_source",
        "selection_type",
        "status",
        "capture_status",
        "result_code",
        "result_label",
        "prediction_hit",
        "winning_sp",
        "generated_ts",
        "q_input_sp_snapshot_ts",
        "q_input_probability_snapshot_ts",
        "q_calculated_ts",
        "decision_snapshot_id",
        "decision_snapshot_status",
        "decision_snapshot_generated_at",
        "decision_snapshot_checked_at",
        "draft_decision_snapshot_id",
        "draft_decision_snapshot_status",
        "postmatch_review_outcome",
        "postmatch_review_summary",
        "postmatch_review_tags",
        "postmatch_review_action",
        "postmatch_review_profit",
        "postmatch_review_reviewed_at",
        "selected_decision_variant_id",
        "selected_decision_variant_status",
    }
    out = {key: match.get(key) for key in keep if key in match}
    selected = match.get("selected_decision_variant")
    if isinstance(selected, dict):
        out["selected_decision_variant"] = _compact_decision_variant(selected)
    return out


def _attach_decision_variants(
    matches: list[dict[str, Any]],
    shadow_variants: list[tuple[dict[int, dict[str, Any]], str]],
    *,
    release: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    present_shadow_ids = {
        _shadow_variant_id(rows)
        for rows, _source_path in shadow_variants
        if rows
    }
    placeholder_manifests = [
        manifest
        for manifest in _manifest_decision_variants(release)
        if str(manifest.get("variant_id") or "") in {
            str(item.get("variant_id") or "")
            for item in _missing_manifest_shadow_options(present_shadow_ids, release)
        }
    ]
    for match in matches:
        idx = _safe_int(match.get("match_idx"))
        variants = [_active_decision_variant(match)]
        result_code = str(match.get("result_code") or "")
        for shadow_rows, shadow_source_path in shadow_variants:
            if idx is not None and idx in shadow_rows and shadow_source_path:
                variants.append(_shadow_decision_variant(shadow_rows[idx], shadow_source_path, result_code=result_code))
        for manifest in placeholder_manifests:
            placeholder = _manifest_shadow_placeholder_decision_variant(manifest)
            if placeholder:
                variants.append(placeholder)
        match["decision_variants"] = variants
    return matches


def _apply_llm_issue_decision(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    summary: dict[str, Any],
    *,
    use_active_snapshot: bool = True,
) -> dict[str, Any]:
    """Use the fixed LLM decision chain as the live betting recommendation.

    The model/q selection is kept under model_* fields for audit and replay.
    """
    model_codes = [str(code) for code in summary.get("selection_codes", []) if str(code) in OUTCOME_ORDER]
    model_prediction_hit = summary.get("prediction_hit")
    summary.update(
        {
            "model_selection": summary.get("selection"),
            "model_selection_codes": model_codes,
            "model_selection_type": summary.get("selection_type"),
            "model_selection_source": summary.get("selection_source"),
            "model_prediction_hit": model_prediction_hit,
        }
    )

    detail_payload = _nowscore_detail_payload(conn, row)
    if detail_payload:
        summary["odds_consensus"] = detail_payload.get("odds_consensus", {})
        summary["market_highlights"] = detail_payload.get("highlights", [])

    analysis = _analysis_nowscore(conn, row)
    if analysis["status"] != "ok":
        analysis = _analysis_500(conn, row)
    intelligence = _match_intelligence(conn, row)
    decision = _gpt_fixed_chain_decision(summary, analysis, intelligence)
    llm_codes = [str(code) for code in decision.get("selection_codes", []) if str(code) in OUTCOME_ORDER]
    primary_code = llm_codes[0] if llm_codes else None
    outcome_rows = {str(item.get("code")): item for item in _summary_outcome_rows(summary)}
    primary_row = outcome_rows.get(primary_code or "", {})
    llm_prediction_hit = (
        summary.get("result_code") in llm_codes
        if summary.get("result_code") and llm_codes
        else None
    )
    summary.update(
        {
            "llm_judgment": decision["judgment"],
            "llm_selection": primary_code,
            "llm_selection_codes": llm_codes,
            "llm_selection_type": _selection_type_from_codes(llm_codes),
            "llm_explanation": decision["explanation"],
            "llm_confidence": decision["confidence"],
            "llm_confidence_label": decision["confidence_label"],
            "llm_stop_flag": bool(decision.get("stop_flag")),
            "llm_stop_reasons": decision.get("stop_reasons") or [],
            "llm_support": decision["support"],
            "llm_risks": decision["risks"],
            "llm_decision_chain": decision["chain"],
            "llm_source": decision["source"],
            "llm_q_score": primary_row.get("q"),
            "llm_probability": primary_row.get("prob"),
            "llm_prediction_hit": llm_prediction_hit,
            "selection": primary_code,
            "selection_codes": llm_codes,
            "selection_source": decision["source"],
            "selection_type": _selection_type_from_codes(llm_codes),
            "prediction_hit": llm_prediction_hit,
        }
    )
    if use_active_snapshot:
        active = _latest_decision_snapshot(conn, str(row["issue"]), int(row["match_idx"]), "active")
        if active:
            summary.update(_snapshot_row_to_summary_fields(active))
            active_codes = [str(code) for code in summary.get("llm_selection_codes", []) if str(code) in OUTCOME_ORDER]
            active_hit = (
                summary.get("result_code") in active_codes
                if summary.get("result_code") and active_codes
                else None
            )
            summary["llm_prediction_hit"] = active_hit
            summary["prediction_hit"] = active_hit
        draft = _latest_decision_snapshot(conn, str(row["issue"]), int(row["match_idx"]), "draft_replacement")
        if draft:
            summary["draft_decision_snapshot_id"] = draft["snapshot_id"]
            summary["draft_decision_snapshot_generated_at"] = draft["generated_at"]
            summary["draft_decision_snapshot_status"] = draft["status"]
        elif active:
            summary["draft_decision_snapshot_status"] = ""
    else:
        summary["decision_snapshot_status"] = "unpersisted"
    review = _postmatch_review_payload(conn, str(row["issue"]), int(row["match_idx"]))
    if review:
        summary["postmatch_review"] = review
        summary["postmatch_review_outcome"] = review.get("outcome_label") or ""
        summary["postmatch_review_summary"] = review.get("summary") or ""
        summary["postmatch_review_tags"] = review.get("tags") or []
        summary["postmatch_review_action"] = review.get("action_suggestion") or ""
        summary["postmatch_review_profit"] = review.get("profit")
        summary["postmatch_review_reviewed_at"] = review.get("reviewed_at") or ""
    return summary


def _decision_input_payload(summary: dict[str, Any], analysis: dict[str, Any], intelligence: dict[str, Any]) -> dict[str, Any]:
    """Build the audited pre-match input payload.

    Result fields such as score, result_code, halftime_score, and winning_sp are
    intentionally excluded so late refreshes cannot contaminate the decision
    basis used for betting.
    """
    analysis_compact = {
        "status": analysis.get("status"),
        "fetched_at": analysis.get("fetched_at"),
        "source": analysis.get("source"),
        "home_recent": (analysis.get("home_recent") or {}).get("summary") if isinstance(analysis.get("home_recent"), dict) else "",
        "away_recent": (analysis.get("away_recent") or {}).get("summary") if isinstance(analysis.get("away_recent"), dict) else "",
        "h2h": (analysis.get("h2h") or {}).get("summary") if isinstance(analysis.get("h2h"), dict) else "",
        "league_table": analysis.get("league_table"),
        "highlights": analysis.get("highlights") if isinstance(analysis.get("highlights"), list) else [],
        "market_summary": analysis.get("market_summary"),
    }
    intelligence_compact = {
        "status": intelligence.get("status"),
        "fetched_at": intelligence.get("fetched_at"),
        "headline": intelligence.get("headline"),
        "points": intelligence.get("points") if isinstance(intelligence.get("points"), list) else [],
        "tags": intelligence.get("tags") if isinstance(intelligence.get("tags"), list) else [],
        "stage": intelligence.get("stage") if isinstance(intelligence.get("stage"), dict) else {},
        "source_count": intelligence.get("source_count"),
    }
    return {
        "match": {
            "issue": summary.get("issue"),
            "match_id": summary.get("match_id"),
            "match_idx": summary.get("match_idx"),
            "league": summary.get("league"),
            "kickoff_ts": summary.get("kickoff_ts"),
            "home": summary.get("home"),
            "away": summary.get("away"),
            "handicap_line": summary.get("handicap_line"),
            "ah_line": summary.get("ah_line"),
            "line_gap": summary.get("line_gap"),
        },
        "model": {
            "selection": summary.get("model_selection"),
            "selection_codes": summary.get("model_selection_codes"),
            "selection_type": summary.get("model_selection_type"),
            "selection_source": summary.get("model_selection_source"),
            "probabilities": {
                "3": summary.get("model_p_3"),
                "1": summary.get("model_p_1"),
                "0": summary.get("model_p_0"),
            },
            "market_probabilities": {
                "3": summary.get("market_p_3"),
                "1": summary.get("market_p_1"),
                "0": summary.get("market_p_0"),
            },
        },
        "q": {
            "q_max": summary.get("q_max"),
            "q_score": summary.get("q_score"),
            "calculated_ts": summary.get("q_calculated_ts"),
            "input_policy": summary.get("q_input_policy"),
            "sp_snapshot_ts": summary.get("q_input_sp_snapshot_ts"),
            "probability_snapshot_ts": summary.get("q_input_probability_snapshot_ts"),
        },
        "sp": {
            "3": summary.get("sp_3"),
            "1": summary.get("sp_1"),
            "0": summary.get("sp_0"),
            "snapshot_ts": summary.get("sp_snapshot_ts"),
            "display_source": summary.get("display_sp_source"),
            "prediction_source": summary.get("prediction_sp_source"),
            "prediction_snapshot_ts": summary.get("prediction_sp_snapshot_ts"),
        },
        "market": {
            "odds_consensus": summary.get("odds_consensus") if isinstance(summary.get("odds_consensus"), dict) else {},
            "market_highlights": summary.get("market_highlights") if isinstance(summary.get("market_highlights"), list) else [],
        },
        "analysis": analysis_compact,
        "intelligence": intelligence_compact,
        "source_timestamps": {
            "generated_ts": summary.get("generated_ts"),
            "calculated_ts": summary.get("calculated_ts"),
            "sp_snapshot_ts": summary.get("sp_snapshot_ts"),
            "probability_snapshot_ts": summary.get("probability_snapshot_ts"),
            "analysis_fetched_at": analysis.get("fetched_at"),
            "intelligence_fetched_at": intelligence.get("fetched_at"),
        },
    }


def _decision_fingerprint(summary: dict[str, Any]) -> str:
    payload = {
        "judgment": summary.get("llm_judgment"),
        "selection": summary.get("llm_selection"),
        "selection_codes": summary.get("llm_selection_codes") or [],
        "selection_type": summary.get("llm_selection_type"),
        "stop_flag": bool(summary.get("llm_stop_flag")),
    }
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _decision_input_hash(input_payload: dict[str, Any]) -> str:
    hash_payload = json.loads(_json_dumps(input_payload))
    if isinstance(hash_payload.get("q"), dict):
        hash_payload["q"]["calculated_ts"] = ""
    if isinstance(hash_payload.get("source_timestamps"), dict):
        hash_payload["source_timestamps"]["generated_ts"] = ""
        hash_payload["source_timestamps"]["calculated_ts"] = ""
    return hashlib.sha256(_json_dumps(hash_payload).encode("utf-8")).hexdigest()


def _snapshot_record_from_summary(
    summary: dict[str, Any],
    analysis: dict[str, Any],
    intelligence: dict[str, Any],
    *,
    status: str,
    supersedes_snapshot_id: str | None = None,
) -> dict[str, Any]:
    input_payload = _decision_input_payload(summary, analysis, intelligence)
    input_hash = _decision_input_hash(input_payload)
    fingerprint = _decision_fingerprint(summary)
    versions = _active_version_bundle()
    issue = str(summary["issue"])
    match_idx = int(summary["match_idx"])
    selection_codes = [str(code) for code in summary.get("llm_selection_codes", []) if str(code) in OUTCOME_ORDER]
    primary = str(summary.get("llm_selection") or "") if selection_codes else ""
    protect = selection_codes[1:] if selection_codes else []
    generated_at = _now_hk_iso()
    decision_payload = {
        "judgment": summary.get("llm_judgment"),
        "selection": primary,
        "selection_codes": selection_codes,
        "selection_type": summary.get("llm_selection_type"),
        "stop_flag": bool(summary.get("llm_stop_flag")),
        "stop_reasons": summary.get("llm_stop_reasons") or [],
        "confidence": summary.get("llm_confidence"),
        "confidence_label": summary.get("llm_confidence_label"),
        "support": summary.get("llm_support") or [],
        "risks": summary.get("llm_risks") or [],
        "chain": summary.get("llm_decision_chain") or [],
        "explanation": summary.get("llm_explanation"),
        "versions": versions,
    }
    snapshot_hash = hashlib.sha256(
        _json_dumps(
            {
                "issue": issue,
                "match_idx": match_idx,
                "status": status,
                "input_hash": input_hash,
                "fingerprint": fingerprint,
                "config_hash": versions["decision_config_hash"],
                "generated_at": generated_at,
            }
        ).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "snapshot_id": f"{issue}_{match_idx:03d}_{status}_{snapshot_hash}",
        "issue": issue,
        "match_idx": match_idx,
        "match_id": str(summary.get("match_id") or f"{issue}_{match_idx:03d}"),
        "status": status,
        "generated_at": generated_at,
        "checked_at": generated_at,
        "last_checked_input_hash": input_hash,
        "confirmed_at": None,
        "superseded_at": None,
        "supersedes_snapshot_id": supersedes_snapshot_id,
        "input_hash": input_hash,
        "decision_fingerprint": fingerprint,
        "recommendation": summary.get("llm_judgment") or ("停" if not selection_codes else ""),
        "primary_pick": primary,
        "protect_picks_json": _json_dumps(protect),
        "stop_flag": 1 if summary.get("llm_stop_flag") else 0,
        "selection_codes_json": _json_dumps(selection_codes),
        "selection_type": summary.get("llm_selection_type") or _selection_type_from_codes(selection_codes),
        "confidence": summary.get("llm_confidence"),
        "confidence_label": summary.get("llm_confidence_label"),
        "q_score": summary.get("llm_q_score"),
        "probability": summary.get("llm_probability"),
        "decision_chain_json": _json_dumps(summary.get("llm_decision_chain") or []),
        "support_json": _json_dumps(summary.get("llm_support") or []),
        "risks_json": _json_dumps(summary.get("llm_risks") or []),
        "explanation": summary.get("llm_explanation") or "",
        "model_probabilities_json": _json_dumps(input_payload["model"]["probabilities"]),
        "market_probabilities_json": _json_dumps(input_payload["model"]["market_probabilities"]),
        "q_values_json": _json_dumps(input_payload["q"]),
        "sp_snapshot_json": _json_dumps(input_payload["sp"]),
        "source_timestamps_json": _json_dumps(input_payload["source_timestamps"]),
        "input_payload_json": _json_dumps(input_payload),
        "decision_payload_json": _json_dumps(decision_payload),
        "prompt_version": versions["decision_prompt_version"],
        "model_version": versions["decision_model_version"],
        "prob_model_version": versions["prob_model_version"],
        "q_model_version": versions["q_model_version"],
        "decision_chain_version": versions["decision_chain_version"],
        "decision_config_hash": versions["decision_config_hash"],
        "review_tag_version": versions["review_tag_version"],
        "version_bundle_json": _canonical_json(versions),
        "created_by": "decision_api",
    }


def _insert_snapshot_record(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    columns = list(record)
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"""
        INSERT INTO llm_decision_snapshots ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        [record[col] for col in columns],
    )


def _current_decision_snapshot_candidate(conn: sqlite3.Connection, row: sqlite3.Row) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    summary = _apply_llm_issue_decision(conn, row, _match_summary(row), use_active_snapshot=False)
    analysis = _analysis_nowscore(conn, row)
    if analysis["status"] != "ok":
        analysis = _analysis_500(conn, row)
    intelligence = _match_intelligence(conn, row)
    return summary, analysis, intelligence


def _materialize_decision_snapshot_for_row(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    _ensure_decision_snapshot_schema(conn)
    summary, analysis, intelligence = _current_decision_snapshot_candidate(conn, row)
    issue = str(row["issue"])
    match_idx = int(row["match_idx"])
    candidate = _snapshot_record_from_summary(summary, analysis, intelligence, status="active")
    active = _latest_decision_snapshot(conn, issue, match_idx, "active")
    if not active:
        _insert_snapshot_record(conn, candidate)
        return {"action": "created_active", "snapshot": _snapshot_public_payload(_latest_decision_snapshot(conn, issue, match_idx, "active"))}

    active_config_hash = _row_get(active, "decision_config_hash") or candidate.get("decision_config_hash")
    if active["decision_fingerprint"] == candidate["decision_fingerprint"] and active_config_hash == candidate.get("decision_config_hash"):
        conn.execute(
            """
            UPDATE llm_decision_snapshots
            SET checked_at=?, last_checked_input_hash=?
            WHERE snapshot_id=?
            """,
            (_now_hk_iso(), candidate["input_hash"], active["snapshot_id"]),
        )
        return {"action": "checked_active_unchanged", "snapshot": _snapshot_public_payload(_latest_decision_snapshot(conn, issue, match_idx, "active"))}

    draft = _snapshot_record_from_summary(
        summary,
        analysis,
        intelligence,
        status="draft_replacement",
        supersedes_snapshot_id=str(active["snapshot_id"]),
    )
    conn.execute(
        "DELETE FROM llm_decision_snapshots WHERE issue=? AND match_idx=? AND status='draft_replacement'",
        (issue, match_idx),
    )
    _insert_snapshot_record(conn, draft)
    return {
        "action": "created_draft_replacement",
        "active": _snapshot_public_payload(active),
        "draft": _snapshot_public_payload(_latest_decision_snapshot(conn, issue, match_idx, "draft_replacement")),
    }


def _materialize_issue_decision_snapshots(conn: sqlite3.Connection, issue: str, *, only_date: str | None = None) -> dict[str, Any]:
    resolved = _resolve_issue(conn, issue)
    rows = _issue_rows(conn, resolved, only_date=only_date)
    actions: dict[str, int] = defaultdict(int)
    items = []
    for row in rows:
        result = _materialize_decision_snapshot_for_row(conn, row)
        action = str(result.get("action") or "unknown")
        actions[action] += 1
        items.append({
            "match_id": _match_id(row),
            "match_idx": int(row["match_idx"]),
            "action": action,
            "snapshot_id": (result.get("snapshot") or result.get("draft") or {}).get("snapshot_id") if isinstance(result.get("snapshot") or result.get("draft"), dict) else "",
        })
    return {
        "issue": resolved,
        "count": len(items),
        "actions": dict(actions),
        "items": items,
    }


def _confirm_decision_snapshot_override(conn: sqlite3.Connection, issue: str, match_idx: int) -> dict[str, Any]:
    _ensure_decision_snapshot_schema(conn)
    draft = _latest_decision_snapshot(conn, issue, match_idx, "draft_replacement")
    if not draft:
        raise LookupError(f"no draft replacement decision snapshot for {issue}_{match_idx:03d}")
    active = _latest_decision_snapshot(conn, issue, match_idx, "active")
    previous_active_id = active["snapshot_id"] if active else None
    now = _now_hk_iso()
    if active:
        conn.execute(
            """
            UPDATE llm_decision_snapshots
            SET status='superseded', superseded_at=?
            WHERE snapshot_id=?
            """,
            (now, active["snapshot_id"]),
        )
    conn.execute(
        """
        UPDATE llm_decision_snapshots
        SET status='active', checked_at=?, confirmed_at=?, supersedes_snapshot_id=?
        WHERE snapshot_id=?
        """,
        (now, now, previous_active_id, draft["snapshot_id"]),
    )
    previous_active = (
        conn.execute("SELECT * FROM llm_decision_snapshots WHERE snapshot_id=?", (previous_active_id,)).fetchone()
        if previous_active_id
        else None
    )
    return {
        "action": "confirmed_override",
        "confirmed_at": now,
        "previous_active": _snapshot_public_payload(previous_active),
        "active": _snapshot_public_payload(_latest_decision_snapshot(conn, issue, match_idx, "active")),
    }


def _main_strategy_summary_rows(release: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    release = release or _active_strategy_release()
    rows = _read_csv_cached(str(_strategy_main_dir(release) / "sleeve_mix_summary.csv"))
    meta_by_arm = {str(arm["arm_id"]): arm for arm in _main_strategy_arms(release)}
    out: list[dict[str, Any]] = []
    for row in rows:
        arm_id = str(row.get("portfolio", ""))
        if arm_id not in meta_by_arm:
            continue
        meta = meta_by_arm[arm_id]
        out.append({
            "arm_id": arm_id,
            "label": meta["label"],
            "role": meta["role"],
            "recommended_for": meta["recommended_for"],
            "issue_budget": _csv_float(row, "issue_budget"),
            "extra_budget": _csv_float(row, "extra_budget"),
            "stake_units": _csv_float(row, "stake_units"),
            "profit_units": _csv_float(row, "profit_units"),
            "profit_per_256": _csv_float(row, "profit_per_256"),
            "roi": _csv_float(row, "roi"),
            "issue_win_rate": _csv_float(row, "issue_win_rate"),
            "non_full_loss_rate": _csv_float(row, "non_full_loss_rate"),
            "full_loss_rate": _csv_float(row, "full_loss_rate"),
            "max_drawdown_units": _csv_float(row, "max_drawdown_units"),
            "max_drawdown_per_256": _csv_float(row, "max_drawdown_per_256"),
            "max_drawdown_budget_equiv": _csv_float(row, "max_drawdown_budget_equiv"),
            "max_loss_streak": _csv_int(row, "max_loss_streak"),
            "max_dead_streak": _csv_int(row, "max_dead_streak"),
            "best_issue_profit_units": _csv_float(row, "best_issue_profit_units"),
            "roi_ex_best_issue": _csv_float(row, "roi_ex_best_issue"),
            "recent_profit_per_256": _csv_float(row, "recent_profit_per_256"),
            "recent_roi": _csv_float(row, "recent_roi"),
            "avg_tickets_per_issue": _csv_float(row, "avg_tickets_per_issue"),
            "allocation": row.get("allocation", ""),
            "rationale": row.get("rationale", ""),
            "risk_tags": [
                "fixed_384_units",
                "line_gap_diagnostic_only",
                "sp_drift_not_main_depth_gate",
            ],
        })
    role_order = {"stable": 0, "convex": 1}
    return sorted(out, key=lambda item: role_order.get(str(item["role"]), 99))


def _main_strategy_annual_rows(release: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    release = release or _active_strategy_release()
    annual = _read_csv_cached(str(_strategy_main_dir(release) / "sleeve_mix_annual.csv"))
    arm_ids = _main_strategy_arm_ids(release)
    rows = []
    for row in annual:
        arm_id = str(row.get("portfolio", ""))
        if arm_id not in arm_ids:
            continue
        rows.append({
            "arm_id": arm_id,
            "year": _csv_int(row, "year"),
            "n_issues": _csv_int(row, "n_issues"),
            "stake_units": _csv_float(row, "stake_units"),
            "profit_units": _csv_float(row, "profit_units"),
            "roi": _csv_float(row, "roi"),
            "issue_win_rate": _csv_float(row, "issue_win_rate"),
            "non_full_loss_rate": _csv_float(row, "non_full_loss_rate"),
            "max_drawdown_units": _csv_float(row, "max_drawdown_units"),
        })
    return rows


def _main_strategy_issue_rows(release: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    release = release or _active_strategy_release()
    path = _strategy_main_dir(release) / "sleeve_mix_issue_profit.csv"
    return list(_main_issue_rows_cached(str(path), _main_strategy_arm_ids(release)))


def _issue_review_rows(issue: str, *, limit: int = 14, release: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    release = release or _active_strategy_release()
    raw_rows = _main_strategy_issue_rows(release)
    arm_ids = _main_strategy_arm_ids(release)
    by_issue: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        issue_id = str(row.get("issue", ""))
        arm_id = str(row.get("portfolio", ""))
        if arm_id not in arm_ids:
            continue
        item = by_issue.setdefault(issue_id, {
            "issue": issue_id,
            "issue_order": _csv_int(row, "issue_order"),
            "calendar_year": _csv_int(row, "calendar_year"),
            "issue_close_ts": row.get("issue_close_ts", ""),
            "arms": [],
        })
        item["arms"].append({
            "arm_id": arm_id,
            "stake_units": _csv_float(row, "stake_units"),
            "profit_units": _csv_float(row, "profit_units"),
            "roi": _csv_float(row, "roi"),
            "tickets": _csv_float(row, "tickets"),
            "hits": _csv_float(row, "hits"),
            "parts": row.get("parts", ""),
            "state": row.get("state", ""),
            "allocation": row.get("allocation", ""),
        })
    target = by_issue.get(str(issue))
    latest = sorted(by_issue.values(), key=lambda row: _safe_int(row.get("issue_order")) or 0, reverse=True)[:limit]
    if target and all(row["issue"] != str(issue) for row in latest):
        latest = [target, *latest[:-1]]
    return sorted(latest, key=lambda row: _safe_int(row.get("issue_order")) or 0, reverse=True)


def _risk_state(release: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = [
        row for row in _main_strategy_issue_rows(release)
        if str(row.get("portfolio", "")) == "b384_dd32_smooth80_convex19"
    ]
    rows.sort(key=lambda row: _csv_int(row, "issue_order"))
    equity = 0.0
    peak = 0.0
    loss_streak = 0
    current_drawdown = 0.0
    latest_issue = ""
    for row in rows:
        latest_issue = str(row.get("issue", ""))
        profit = _csv_float(row, "profit_units")
        equity += profit
        peak = max(peak, equity)
        current_drawdown = equity - peak
        loss_streak = loss_streak + 1 if profit < 0 else 0
    if current_drawdown <= -9000 or loss_streak >= 6:
        risk_level = "defensive"
        recommended = "b384_dd32_smooth100"
        reason = "历史状态触发防守：回撤或连续亏损接近阈值。"
    elif current_drawdown <= -5000 or loss_streak >= 3:
        risk_level = "watch"
        recommended = "b384_dd32_smooth100"
        reason = "历史状态进入观察：优先稳健 A，人工确认是否切 B。"
    else:
        risk_level = "normal"
        recommended = "b384_dd32_smooth80_convex19"
        reason = "历史状态正常：B 可作为收益/凸性候选，A 仍作为回撤控制对照。"
    return {
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "latest_backtest_issue": latest_issue,
        "risk_level": risk_level,
        "recommended_arm": recommended,
        "reason": reason,
        "cooldown": {
            "state": "off",
            "policy": "不做真实冷却；固定 384 投入，风险态只影响 A/B 候选与人工确认。",
            "pre_loss_streak": loss_streak,
            "pre_drawdown_units": current_drawdown,
        },
        "budget": {
            "mode": "fixed",
            "selected_units": 384,
            "base_units": 256,
            "extra_units": 128,
            "notes": "不复利，不锁盈；实盘按固定 384 单位评估。",
        },
        "guardrails": [
            "line-gap 只显示诊断标签，不作为 hard gate。",
            "SP drift 只显示诊断/极小 paper convex sleeve，不进入主 depth gate。",
            "当前期必须有真实抓取数据；未生成正式主策略 EV pool 时禁止静默 fallback mock。",
        ],
    }


def _parse_ticket_legs(raw: Any) -> list[dict[str, Any]]:
    legs = []
    for part in str(raw or "").split(";"):
        if not part:
            continue
        try:
            match_text, rest = part.split(":", 1)
            code_text, hcp_text = rest.split("@", 1)
        except ValueError:
            continue
        match_id = _safe_int(match_text)
        hcp = _safe_float(hcp_text)
        if match_id is None:
            continue
        legs.append({"match_id": match_id, "selection": code_text, "hcp": hcp})
    return legs


def _line_gap_state(code: str, line_gap: float | None, threshold: float = 0.5) -> str:
    if line_gap is None or not math.isfinite(line_gap) or abs(line_gap) < threshold or code == "1":
        return "neutral"
    if line_gap >= threshold:
        return "support" if code == "0" else "oppose"
    return "support" if code == "3" else "oppose"


@lru_cache(maxsize=64)
def _match_context_for_issue(model_db_text: str, issue: str) -> dict[int, dict[str, Any]]:
    path = Path(model_db_text)
    if not path.exists():
        return {}
    sql = """
        SELECT
          mf.match_id,
          mf.issue,
          mf.match_idx,
          mf.kickoff_ts,
          mf.league,
          mf.home,
          mf.away,
          mf.score,
          mf.handicap_line_norm,
          mf.result_label,
          mf.result_code,
          mf.winning_sp,
          mf.official_sp_3,
          mf.official_sp_1,
          mf.official_sp_0,
          mf.official_500_avg_eu_home,
          mf.official_500_avg_eu_draw,
          mf.official_500_avg_eu_away,
          ah.v2_avg AS asian_1h_line
        FROM match_features mf
        LEFT JOIN market_consensus ah
          ON ah.match_id=mf.match_id
         AND ah.market='asian_handicap'
         AND ah.snapshot='1h'
        WHERE mf.issue=?
    """
    with _connect(path) as conn:
        return {
            int(row["match_id"]): {
                "match_id": int(row["match_id"]),
                "issue": str(row["issue"]),
                "match_idx": row["match_idx"],
                "kickoff_ts": row["kickoff_ts"],
                "league": row["league"],
                "home": row["home"],
                "away": row["away"],
                "score": row["score"],
                "handicap_line": _safe_float(row["handicap_line_norm"]),
                "result_label": row["result_label"],
                "result_code": str(row["result_code"]) if row["result_code"] is not None else "",
                "winning_sp": _safe_float(row["winning_sp"]),
                "sp_3": _safe_float(row["official_sp_3"]),
                "sp_1": _safe_float(row["official_sp_1"]),
                "sp_0": _safe_float(row["official_sp_0"]),
                "eu_home": _safe_float(row["official_500_avg_eu_home"]),
                "eu_draw": _safe_float(row["official_500_avg_eu_draw"]),
                "eu_away": _safe_float(row["official_500_avg_eu_away"]),
                "asian_1h_line": _safe_float(row["asian_1h_line"]),
                "line_gap": (
                    -float(row["handicap_line_norm"]) - float(row["asian_1h_line"])
                    if row["handicap_line_norm"] is not None and row["asian_1h_line"] is not None
                    else None
                ),
            }
            for row in conn.execute(sql, (issue,))
        }


@lru_cache(maxsize=64)
def _joint_leg_meta_for_issue(path_text: str, issue: str) -> dict[tuple[int, str], dict[str, Any]]:
    path = Path(path_text)
    if not path.exists():
        return {}
    out: dict[tuple[int, str], dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if str(row.get("issue", "")) != str(issue):
                continue
            match_id = _safe_int(row.get("match_id"))
            action_code = str(row.get("action_code", ""))
            if match_id is None or action_code not in OUTCOME_LABEL:
                continue
            out[(match_id, action_code)] = {
                "q_score": _csv_float(row, "q_score"),
                "confidence_weight": _csv_float(row, "conf_weight"),
                "drift_bucket": row.get("drift_bucket", ""),
                "q_bucket": row.get("q_bucket", ""),
                "confidence_bucket": row.get("confidence_bucket", ""),
                "pred_sp_multiplier": _csv_float(row, "pred_sp_multiplier"),
                "selected_model_p": _csv_float(row, "selected_model_p"),
                "selected_market_p": _csv_float(row, "selected_market_p"),
            }
    return out


def _issue_year(issue: str) -> int | None:
    if len(issue) < 2 or not issue[:2].isdigit():
        return None
    year = 2000 + int(issue[:2])
    return year if 2000 <= year <= 2099 else None


def _available_issues(conn: sqlite3.Connection, *, limit: int = 80, include_replay: bool = True) -> list[dict[str, Any]]:
    by_issue: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        """
        SELECT
          i.issue,
          i.label,
          i.is_current,
          i.last_seen_at,
          COUNT(m.fid) AS match_count,
          SUM(CASE WHEN m.fid IS NOT NULL AND m.winning_sp IS NOT NULL THEN 1 ELSE 0 END) AS settled_match_count,
          SUM(CASE WHEN m.fid IS NOT NULL AND m.winning_sp IS NULL THEN 1 ELSE 0 END) AS open_match_count
        FROM issues i
        LEFT JOIN matches m ON m.issue=i.issue
        GROUP BY i.issue, i.label, i.is_current, i.last_seen_at
        ORDER BY i.is_current DESC, i.last_seen_at DESC, i.issue DESC
        LIMIT ?
        """,
        (limit,),
    ):
        issue = str(row["issue"])
        match_count = int(row["match_count"] or 0)
        settled_match_count = int(row["settled_match_count"] or 0)
        open_match_count = int(row["open_match_count"] or 0)
        is_fully_settled = match_count > 0 and open_match_count == 0 and settled_match_count == match_count
        by_issue[issue] = {
            "issue": issue,
            "label": row["label"] or issue,
            "status": "current" if row["is_current"] else "live_history",
            "source": "500_live_sqlite",
            "is_current": bool(row["is_current"]),
            "year": _issue_year(issue),
            "match_count": match_count,
            "settled_match_count": settled_match_count,
            "open_match_count": open_match_count,
            "is_fully_settled": is_fully_settled,
            "has_settlement": is_fully_settled,
            "last_seen_at": row["last_seen_at"] or "",
            "issue_order": 10_000_000 + (_safe_int(issue) or 0),
            "issue_close_ts": "",
        }

    if include_replay:
        historical: dict[str, dict[str, Any]] = {}
        for row in _main_strategy_issue_rows():
            issue = str(row.get("issue", ""))
            if not issue:
                continue
            item = historical.setdefault(issue, {
                "issue": issue,
                "label": f"{issue} 历史回放",
                "status": "historical_replay",
                "source": "main_strategy_replay",
                "is_current": False,
                "year": _csv_int(row, "calendar_year") or _issue_year(issue),
                "match_count": 0,
                "settled_match_count": 0,
                "open_match_count": 0,
                "is_fully_settled": False,
                "has_settlement": False,
                "last_seen_at": row.get("issue_close_ts", ""),
                "issue_order": _csv_int(row, "issue_order"),
                "issue_close_ts": row.get("issue_close_ts", ""),
            })
            item["issue_order"] = max(_safe_int(item.get("issue_order")) or 0, _csv_int(row, "issue_order"))
            if row.get("issue_close_ts"):
                item["last_seen_at"] = row.get("issue_close_ts", "")
                item["issue_close_ts"] = row.get("issue_close_ts", "")
        for issue, item in historical.items():
            if issue not in by_issue:
                by_issue[issue] = item

    rows = list(by_issue.values())
    rows.sort(
        key=lambda item: (
            1 if item.get("is_current") else 0,
            _safe_int(item.get("issue_order")) or 0,
            _safe_int(item.get("issue")) or 0,
        ),
        reverse=True,
    )
    return rows[:limit]


def _historical_best_selection(
    match_id: int,
    joint_meta: dict[tuple[int, str], dict[str, Any]],
) -> tuple[str | None, dict[str, Any]]:
    scored: list[tuple[float, float, str, dict[str, Any]]] = []
    for code in ("3", "1", "0"):
        meta = joint_meta.get((match_id, code), {})
        q_score = _safe_float(meta.get("q_score")) or 0.0
        model_p = _safe_float(meta.get("selected_model_p")) or 0.0
        if meta:
            scored.append((q_score, model_p, code, meta))
    if not scored:
        return None, {}
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    q_score, _model_p, code, meta = scored[0]
    return (code, meta) if q_score > 0 else (None, {})


def _historical_match_summary(
    issue: str,
    context: dict[str, Any],
    joint_meta: dict[tuple[int, str], dict[str, Any]],
) -> dict[str, Any]:
    raw_match_id = int(context["match_id"])
    match_idx = _safe_int(context.get("match_idx")) or 0
    selected, selected_meta = _historical_best_selection(raw_match_id, joint_meta)
    result_code = str(context.get("result_code") or "")
    prediction_hit = result_code == selected if result_code and selected else None
    q_score = selected_meta.get("q_score") if selected_meta else None
    confidence = selected_meta.get("confidence_weight") if selected_meta else None
    model_probs = {
        code: (joint_meta.get((raw_match_id, code), {}).get("selected_model_p"))
        for code in ("3", "1", "0")
    }
    market_probs = {
        code: (joint_meta.get((raw_match_id, code), {}).get("selected_market_p"))
        for code in ("3", "1", "0")
    }
    kickoff_ts = str(context.get("kickoff_ts") or "")
    return {
        "match_id": f"{issue}_{match_idx:03d}" if match_idx else f"{issue}_{raw_match_id}",
        "source_match_id": str(raw_match_id),
        "issue": issue,
        "match_idx": match_idx,
        "league": context.get("league", ""),
        "kickoff_ts": kickoff_ts,
        "kickoff_date": kickoff_ts[:10] if kickoff_ts else "",
        "home": context.get("home", ""),
        "away": context.get("away", ""),
        "handicap_line": context.get("handicap_line"),
        "score": context.get("score", ""),
        "sp_3": context.get("sp_3"),
        "sp_1": context.get("sp_1"),
        "sp_0": context.get("sp_0"),
        "eu_home": context.get("eu_home"),
        "eu_draw": context.get("eu_draw"),
        "eu_away": context.get("eu_away"),
        "ah_line": context.get("asian_1h_line"),
        "line_gap": context.get("line_gap"),
        "sp_drift_band": f"drift_bucket:{selected_meta.get('drift_bucket')}" if selected_meta.get("drift_bucket") else "historical_diagnostic",
        "q_max": q_score,
        "q_score": q_score,
        "q_bucket": selected_meta.get("q_bucket", ""),
        "confidence_bucket": selected_meta.get("confidence_bucket", ""),
        "confidence_weight": confidence,
        "model_p_3": model_probs["3"],
        "model_p_1": model_probs["1"],
        "model_p_0": model_probs["0"],
        "market_p_3": market_probs["3"],
        "market_p_1": market_probs["1"],
        "market_p_0": market_probs["0"],
        "selection": selected,
        "selection_source": "historical_joint_q_confidence" if selected else "not_in_algorithm_pool",
        "selection_type": "single" if selected else "no-buy",
        "candidate_role": "core" if (q_score or 0) >= 2 else "protect" if selected else "watch",
        "status": "settled" if result_code or context.get("winning_sp") is not None else "open",
        "capture_status": "ok" if result_code else "partial",
        "result_code": result_code,
        "result_label": OUTCOME_LABEL.get(result_code, context.get("result_label") or ""),
        "prediction_hit": prediction_hit,
        "winning_sp": context.get("winning_sp"),
        "generated_ts": datetime.now(timezone.utc).isoformat(),
    }


def _historical_match_by_display_id(
    match_id: str,
    release: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[tuple[int, str], dict[str, Any]]]:
    if "_" not in match_id and "-" not in match_id:
        raise LookupError(f"historical match id must include issue prefix: {match_id}")
    issue, idx_text = match_id.split("_", 1) if "_" in match_id else match_id.split("-", 1)
    idx = _safe_int(idx_text)
    if idx is None:
        raise LookupError(f"historical match index not found: {match_id}")
    match_context = _match_context_for_issue(str(DEFAULT_MODEL_DB), issue)
    context = next((row for row in match_context.values() if _safe_int(row.get("match_idx")) == idx), None)
    if not context:
        raise LookupError(f"historical match not found: {match_id}")
    joint_meta = _joint_leg_meta_for_issue(str(_strategy_joint_leg_rows_csv(release)), issue)
    return issue, context, joint_meta


def _historical_dashboard(issue: str, release: dict[str, Any] | None = None) -> dict[str, Any]:
    release = release or _active_strategy_release()
    resolved = str(issue)
    match_context = _match_context_for_issue(str(DEFAULT_MODEL_DB), resolved)
    if not match_context:
        raise LookupError(f"historical issue not found: {issue}")
    joint_meta = _joint_leg_meta_for_issue(str(_strategy_joint_leg_rows_csv(release)), resolved)
    contexts = sorted(match_context.values(), key=lambda row: _safe_int(row.get("match_idx")) or 0)
    matches = [_historical_match_summary(resolved, context, joint_meta) for context in contexts]
    q_values = [m["q_max"] for m in matches if m["q_max"] is not None]
    hits = [m["prediction_hit"] for m in matches if m["prediction_hit"] is not None]
    review = next((row for row in _issue_review_rows(resolved, limit=120, release=release) if row["issue"] == resolved), None)
    return {
        "issue": resolved,
        "issue_date": matches[0]["kickoff_date"] if matches else "",
        "status": "open" if any(m["status"] == "open" for m in matches) else "settled",
        "capture_status": "complete" if all(m["capture_status"] == "ok" for m in matches) else "partial",
        "last_snapshot_ts": review.get("issue_close_ts", "") if review else "",
        "sales_deadline": max((m["kickoff_ts"] for m in matches if m["kickoff_ts"]), default=""),
        "stats": {
            "n_matches": len(matches),
            "qualified_matches": sum(1 for m in matches if m["q_max"] is not None),
            "qualified_legs": len(q_values),
            "q_avg": sum(q_values) / len(q_values) if q_values else 0,
            "settled_matches": sum(1 for m in matches if m["status"] == "settled"),
            "prediction_hits": sum(1 for hit in hits if hit),
            "prediction_hit_rate": sum(1 for hit in hits if hit) / len(hits) if hits else 0,
            "pool_quality_flag": "green" if matches and q_values else "yellow" if matches else "red",
        },
        "matches": matches,
        "source": {
            "kind": "historical_replay",
            "provider": "beidan_modeling_plus_2026",
            "issue_label": f"{resolved} 历史回放",
            "scope_date": None,
            "path": _public_diagnostics_path(DEFAULT_MODEL_DB),
            "tables": ["match_features", "market_consensus", "joint_leg_rows.csv"],
        },
    }


def _historical_match_detail(match_id: str) -> dict[str, Any]:
    release = _active_strategy_release()
    issue, context, joint_meta = _historical_match_by_display_id(match_id, release)
    summary = _historical_match_summary(issue, context, joint_meta)
    return {
        "match": summary,
        "prediction": {
            "model_version": "historical-q-confidence-replay",
            "generated_ts": summary["generated_ts"],
            "q_score": summary["q_score"] or 0,
            "confidence_weight": summary["confidence_weight"] or 0,
            "model_p_3": summary["model_p_3"],
            "model_p_1": summary["model_p_1"],
            "model_p_0": summary["model_p_0"],
            "market_p_3": summary["market_p_3"],
            "market_p_1": summary["market_p_1"],
            "market_p_0": summary["market_p_0"],
            "strategy_arms": [{
                "arm_id": "historical_main_strategy_leg_rank",
                "selection": summary["selection"] or "pass",
                "selection_type": summary["selection_type"],
                "active": True,
            }],
            "llm_judgment": summary["selection"] or "pass",
            "llm_explanation": "历史回放：按同一期腿级 q/confidence 元数据选最高 q 结果；比分/命中只在赛后复盘显示。",
            "llm_confidence": summary["confidence_weight"] or 0,
            "llm_source": "none",
        },
    }


def _historical_ticket_draft(issue: str) -> dict[str, Any]:
    pool = _historical_ev_pool(issue)
    tickets = []
    for ticket in pool.get("tickets", [])[:6]:
        legs = []
        for leg in ticket.get("legs", []):
            legs.append({
                "leg_id": leg.get("leg_id"),
                "match_id": f"{issue}_{_safe_int(leg.get('match_idx')):03d}" if _safe_int(leg.get("match_idx")) else str(leg.get("match_id")),
                "league": leg.get("league", ""),
                "home": leg.get("home", ""),
                "away": leg.get("away", ""),
                "handicap": leg.get("beidan_handicap", leg.get("handicap")),
                "selection": leg.get("selection_code"),
                "cover_type": "single",
                "sp": leg.get("winning_sp"),
                "q_score": leg.get("q_score") or 0,
                "confidence_weight": leg.get("confidence_weight") or 0,
                "risk_warnings": leg.get("diagnostic_tags", []),
            })
        stake = _safe_float(ticket.get("stake_units")) or 0
        tickets.append({
            "candidate_id": ticket.get("ticket_id"),
            "stake_yuan": stake,
            "expected_return_yuan": (_safe_float(ticket.get("payout_units")) or 0),
            "pred_ev_per_stake": ticket.get("pred_ev_per_stake") or 0,
            "expected_payout": ticket.get("payout_units") or 0,
            "coverage_detail": {"n_full": 0, "n_double": 0},
            "risk_warnings": ticket.get("diagnostic_tags", []),
            "legs": legs,
        })
    return {
        "issue": issue,
        "plan_id": f"{issue}-historical-main-strategy",
        "tickets": tickets,
        "total": len(tickets),
        "source": pool.get("source", ""),
    }


def _historical_signals(issue: str) -> dict[str, Any]:
    dashboard = _historical_dashboard(issue)
    signals = []
    for match in dashboard["matches"]:
        if not match.get("selection"):
            continue
        signals.append({
            "match_id": match["match_id"],
            "qualified_options": [{
                "selection": match["selection"],
                "q_score": match["q_score"] or 0,
                "sp_drift_band": match["sp_drift_band"],
                "arms_recommending": ["historical_main_strategy_leg_rank"],
            }],
        })
    return {
        "issue": issue,
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "freshness": "historical_replay",
        "signals": signals,
    }


def _historical_settlement(issue: str) -> tuple[dict[str, Any], int]:
    dashboard = _historical_dashboard(issue)
    settled = [m for m in dashboard["matches"] if m["status"] == "settled"]
    if not settled:
        return {"error": "not settled", "issue": issue}, 404
    hits = [m for m in settled if m.get("prediction_hit")]
    total_payout = sum(float(m.get("winning_sp") or 0) for m in settled)
    return {
        "issue": issue,
        "settled_ts": datetime.now(timezone.utc).isoformat(),
        "n_tickets": 0,
        "n_hits": len(hits),
        "n_legs_total": len(settled),
        "n_legs_hit": len(hits),
        "n_legs_missed_by_1": 0,
        "total_stake": 0,
        "total_payout": total_payout,
        "pnl": total_payout,
        "roi": 0,
        "quality_review": "historical match-level replay settlement; ticket-level PnL is shown in main-strategy EV pool.",
        "per_match_settlements": [{
            "match_id": match["match_id"],
            "result_code": match["result_code"],
            "winning_sp": match["winning_sp"],
            "selected_by_arms": ["historical_main_strategy_leg_rank"] if match.get("selection") else [],
            "arm_hits": {"historical_main_strategy_leg_rank": bool(match.get("prediction_hit"))},
            "sp_drift": match.get("sp_drift_band"),
        } for match in settled[:100]],
    }, 200


def _aggregate_ticket_rows(rows: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("source_strategy") or row.get("strategy") or ""), str(row.get("ticket_idx", "")), str(row.get("legs", "")))
        if key not in grouped:
            grouped[key] = dict(row)
            continue
        item = grouped[key]
        item["selected_stake_units"] = str(_csv_float(item, "selected_stake_units") + _csv_float(row, "selected_stake_units"))
        item["selected_profit_units"] = str(_csv_float(item, "selected_profit_units") + _csv_float(row, "selected_profit_units"))
        item["selected_payout_units"] = str(_csv_float(item, "selected_payout_units") + _csv_float(row, "selected_payout_units"))
    return list(grouped.values())


def _ticket_leg_details(row: dict[str, Any], match_context: dict[int, dict[str, Any]], joint_meta: dict[tuple[int, str], dict[str, Any]]) -> list[dict[str, Any]]:
    details = []
    for index, leg in enumerate(_parse_ticket_legs(row.get("legs")), start=1):
        match_id = int(leg["match_id"])
        selection = str(leg["selection"])
        context = match_context.get(match_id, {})
        meta = joint_meta.get((match_id, selection), {})
        line_gap = context.get("line_gap")
        result_code = str(context.get("result_code", ""))
        hit = result_code == selection if result_code else None
        diagnostics = [
            f"line_gap:{_line_gap_state(selection, line_gap)}",
            "drift:diagnostic_only",
        ]
        if meta.get("drift_bucket"):
            diagnostics.append(f"drift_bucket:{meta['drift_bucket']}")
        details.append({
            "leg_id": f"L{index}",
            "match_id": str(match_id),
            "match_idx": context.get("match_idx"),
            "league": context.get("league", ""),
            "home": context.get("home", ""),
            "away": context.get("away", ""),
            "label": (
                f"{context.get('league', '')} {context.get('home', match_id)} vs {context.get('away', '')}".strip()
                if context else str(match_id)
            ),
            "kickoff_ts": context.get("kickoff_ts", ""),
            "handicap": leg.get("hcp"),
            "beidan_handicap": context.get("handicap_line"),
            "asian_1h_line": context.get("asian_1h_line"),
            "line_gap": line_gap,
            "selection_code": selection,
            "selection_label": OUTCOME_LABEL.get(selection, selection),
            "result_code": result_code,
            "result_label": OUTCOME_LABEL.get(result_code, result_code),
            "hit": hit,
            "winning_sp": context.get("winning_sp"),
            "q_score": meta.get("q_score"),
            "confidence_weight": meta.get("confidence_weight"),
            "selected_model_p": meta.get("selected_model_p"),
            "selected_market_p": meta.get("selected_market_p"),
            "pred_sp_multiplier": meta.get("pred_sp_multiplier"),
            "diagnostic_tags": diagnostics,
        })
    return details


def _historical_ev_pool(issue: str, release: dict[str, Any] | None = None) -> dict[str, Any]:
    release = release or _active_strategy_release()
    ticket_pool_csv = _strategy_ticket_pool_csv(release)
    joint_leg_rows_csv = _strategy_joint_leg_rows_csv(release)
    rows = _selected_ticket_rows_for_issue(str(ticket_pool_csv), issue)
    core_rows = tuple(row for row in rows if str(row.get("selector", "")) == "all") or rows
    aggregated = _aggregate_ticket_rows(core_rows)
    match_context = _match_context_for_issue(str(DEFAULT_MODEL_DB), issue)
    joint_meta = _joint_leg_meta_for_issue(str(joint_leg_rows_csv), issue)
    aggregated.sort(
        key=lambda row: (
            _csv_float(row, "selected_stake_units"),
            _csv_float(row, "pred_ev_per_stake"),
            _csv_float(row, "pred_hit_prob"),
        ),
        reverse=True,
    )
    tickets = []
    for row in aggregated[:30]:
        legs = _ticket_leg_details(row, match_context, joint_meta)
        hit = _csv_bool(row, "hit")
        tickets.append({
            "ticket_id": f"{issue}-{row.get('source_strategy') or row.get('strategy')}-{row.get('ticket_idx')}",
            "ticket_idx": _csv_int(row, "ticket_idx"),
            "source_strategy": row.get("source_strategy") or row.get("strategy") or "",
            "selector": row.get("selector", ""),
            "n_legs": _csv_int(row, "n_legs"),
            "stake_units": _csv_float(row, "selected_stake_units", _csv_float(row, "stake_units")),
            "raw_stake_units": _csv_float(row, "stake_units"),
            "pred_ev_per_stake": _csv_float(row, "pred_ev_per_stake"),
            "pred_hit_prob": _csv_float(row, "pred_hit_prob"),
            "pred_factor_product": _csv_float(row, "pred_factor_product"),
            "hit": hit,
            "payout_units": _csv_float(row, "selected_payout_units", _csv_float(row, "payout_units")),
            "profit_units": _csv_float(row, "selected_profit_units", _csv_float(row, "profit_units")),
            "topology": row.get("topology", ""),
            "avg_q_score": _csv_float(row, "avg_q_score"),
            "avg_confidence_weight": _csv_float(row, "avg_conf_weight"),
            "line_gap_support_net": _csv_float(row, "line_gap_support_net"),
            "avg_abs_line_gap": _csv_float(row, "avg_abs_line_gap"),
            "selector_score": _csv_float(row, "selector_score"),
            "diagnostic_tags": [
                "historical_core_ev_pool",
                "line_gap_diagnostic_only",
                "sp_drift_diagnostic_only",
            ],
            "legs": legs,
        })
    return {
        "available": bool(tickets),
        "status": "historical_core_ev_pool" if tickets else "no_replay_pool_for_issue",
        "source": _relative_display_path(ticket_pool_csv),
        "pool_filter": "selector=all; extra sleeves are shown in A/B allocation/review, not duplicated as separate ticket rows.",
        "ticket_count": len(tickets),
        "tickets": tickets,
    }


def _live_proxy_pool(conn: sqlite3.Connection, issue: str, *, only_date: str | None) -> dict[str, Any]:
    draft = _ticket_draft(conn, issue, only_date=only_date)
    return {
        "available": bool(draft.get("tickets")),
        "status": "live_market_proxy_not_main_ev_pool",
        "source": "500_bjdc.sqlite live/html odds; not production N=7 selector",
        "ticket_count": len(draft.get("tickets", [])),
        "tickets": draft.get("tickets", []),
    }


def _paper_diagnostics(release: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = _read_csv_cached(str(_strategy_linegap_drift_dir(release) / "paper_arm_summary.csv"))
    wanted = {"paper_drift_top8_256", "paper_linegap_drift_hybrid_top8_256", "baseline_384_convex", "baseline_384_smooth"}
    out = []
    for row in rows:
        arm = str(row.get("arm", ""))
        if arm not in wanted:
            continue
        out.append({
            "arm_id": arm,
            "issues": _csv_int(row, "issues"),
            "stake_units": _csv_float(row, "stake_units"),
            "profit_units": _csv_float(row, "profit_units"),
            "profit_per_256": _csv_float(row, "profit_per_256"),
            "roi": _csv_float(row, "roi"),
            "issue_win_rate": _csv_float(row, "issue_win_rate"),
            "non_full_loss_rate": _csv_float(row, "non_full_loss_rate"),
            "max_drawdown_units": _csv_float(row, "max_drawdown_units"),
            "max_loss_streak": _csv_int(row, "max_loss_streak"),
            "recent_roi": _csv_float(row, "recent_roi"),
            "production_status": "diagnostic_only" if arm != "paper_drift_top8_256" else "paper_convex_sleeve_only",
        })
    return out


def _main_strategy_payload(
    conn: sqlite3.Connection,
    issue: str,
    *,
    only_date: str | None,
    decision_variant_id: str | None = None,
) -> dict[str, Any]:
    release = _active_strategy_release()
    resolved = _resolve_main_strategy_issue(conn, issue)
    shadow_variants: list[tuple[dict[int, dict[str, Any]], str]] = []
    suppressed_shadow_variant_ids: list[str] = []
    if _live_issue_exists(conn, resolved):
        rows = _issue_rows(conn, resolved, only_date=None)
        if not _issue_all_has_result(rows):
            shadow_variants, suppressed_shadow_variant_ids = _structured_shadow_variant_scan(resolved, release)
    variant_options = _decision_variant_options(shadow_variants, release=release)
    historical_pool = _historical_ev_pool(resolved, release)
    live_proxy = (
        None
        if historical_pool["available"] or not _live_issue_exists(conn, resolved)
        else _live_proxy_pool(conn, resolved, only_date=only_date)
    )
    return {
        "issue": resolved,
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "mode": "historical_replay" if historical_pool["available"] else "live_monitoring",
        "strategy_family": release.get("strategy_family", "N=7 fixed-384 main strategy"),
        "strategy_release": _strategy_release_public_payload(release),
        "strategy_version_context": _strategy_version_context(
            release,
            variant_options,
            decision_variant_id,
            suppressed_shadow_variant_ids=suppressed_shadow_variant_ids,
        ),
        "decision_variant_options": variant_options,
        "candidates": _main_strategy_summary_rows(release),
        "annual_performance": _main_strategy_annual_rows(release),
        "ev_pool": historical_pool,
        "live_proxy": live_proxy,
        "risk_state": _risk_state(release),
        "diagnostics": {
            "line_gap_policy": "diagnostic_only_not_hard_gate",
            "sp_drift_policy": "diagnostic_only_or_tiny_paper_convex_sleeve_not_main_depth_gate",
            "paper_arms": _paper_diagnostics(release),
        },
        "review": {
            "issues": _issue_review_rows(resolved, release=release),
            "source": _relative_display_path(_strategy_main_dir(release) / "sleeve_mix_issue_profit.csv"),
        },
        "source": {
            "main_strategy_dir": _relative_display_path(_strategy_main_dir(release)),
            "ticket_pool_dir": _relative_display_path(_strategy_artifact_path("ticket_pool_dir", HIGH_N_SELECTOR_RESULTS_DIR, release)),
            "ticket_pool_csv": _relative_display_path(_strategy_ticket_pool_csv(release)),
            "joint_leg_rows_csv": _relative_display_path(_strategy_joint_leg_rows_csv(release)),
            "structured_shadow_dir": _relative_display_path(_strategy_shadow_dir(release)),
            "model_db": _public_diagnostics_path(DEFAULT_MODEL_DB),
            "live_db": _public_diagnostics_path(conn.execute("PRAGMA database_list").fetchone()["file"]),
            "strategy_release_config": _relative_display_path(STRATEGY_RELEASE_CONFIG),
            "no_future_leakage": "当前期只读 live/html odds；历史 replay 才显示 hit/payout/profit。",
        },
    }


def _source_statuses(conn: sqlite3.Connection, issue: str) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fetch_log"):
        return []
    rows = conn.execute(
        """
        SELECT
          kind,
          MAX(fetched_at) AS last_attempt_at,
          MAX(CASE WHEN ok=1 THEN fetched_at ELSE '' END) AS last_success_at,
          SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END) AS ok_count,
          SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS fail_count,
          COUNT(*) AS total_attempts,
          SUM(COALESCE(rows_parsed, 0)) AS rows_parsed,
          MAX(error) AS error
        FROM fetch_log
        WHERE issue=? OR issue IS NULL
        GROUP BY kind
        ORDER BY kind
        """,
        (issue,),
    )
    source_statuses: list[dict[str, Any]] = []
    for row in rows:
        ok_count = int(row["ok_count"] or 0)
        fail_count = int(row["fail_count"] or 0)
        last_success_at = str(row["last_success_at"] or "")
        age_minutes = _minutes_since_hk(last_success_at)
        if ok_count == 0:
            status = "failed"
        elif age_minutes is not None and age_minutes > 360:
            status = "stale"
        elif fail_count > 0:
            status = "partial"
        else:
            status = "ok"
        source_statuses.append(
            {
                "source_name": row["kind"],
                "status": status,
                "last_attempt_at": row["last_attempt_at"] or "",
                "last_success_at": last_success_at,
                "age_minutes": age_minutes,
                "ok_count": ok_count,
                "fail_count": fail_count,
                "total_attempts": int(row["total_attempts"] or 0),
                "rows_parsed": int(row["rows_parsed"] or 0),
                "error": row["error"] or "",
            }
        )
    return source_statuses


def _latest_issue_specific_success(source_statuses: list[dict[str, Any]]) -> str:
    source_names = {"issue_html", "live_sp_xml", "nowscore_bjdc"}
    parsed_candidates = [
        (parsed, str(value))
        for source in source_statuses
        if source.get("source_name") in source_names
        for value in [source.get("last_success_at")]
        if value
        for parsed in [_parse_timestamp_to_hk(str(value))]
        if parsed is not None
    ]
    return max(parsed_candidates, default=(None, ""))[1] if parsed_candidates else ""


def _dashboard(
    conn: sqlite3.Connection,
    issue: str,
    *,
    only_date: str | None,
    decision_variant_id: str | None = None,
    summary_view: bool = False,
) -> dict[str, Any]:
    _ensure_decision_snapshot_schema(conn)
    release = _active_strategy_release()
    resolved = _resolve_issue(conn, issue)
    rows = _issue_rows(conn, resolved, only_date=only_date)
    matches = [_apply_llm_issue_decision(conn, row, _match_summary(row)) for row in rows]
    shadow_variants: list[tuple[dict[int, dict[str, Any]], str]] = []
    suppressed_shadow_variant_ids: list[str] = []
    if not _issue_all_has_result(rows):
        shadow_variants, suppressed_shadow_variant_ids = _structured_shadow_variant_scan(resolved, release)
    matches = _attach_decision_variants(matches, shadow_variants, release=release)
    variant_options = _decision_variant_options(shadow_variants, release=release)
    version_context = _strategy_version_context(
        release,
        variant_options,
        decision_variant_id,
        suppressed_shadow_variant_ids=suppressed_shadow_variant_ids,
    )
    matches = _attach_selected_decision_variant(matches, version_context.get("selected_variant_id") or decision_variant_id)
    if summary_view:
        matches = [_dashboard_summary_match(match) for match in matches]
    complete = sum(1 for m in matches if m["capture_status"] == "ok")
    partial = sum(1 for m in matches if m["capture_status"] == "partial")
    q_values = [m["q_max"] for m in matches if m["q_max"] is not None]
    issue_meta = conn.execute("SELECT * FROM issues WHERE issue=?", (resolved,)).fetchone()
    source_statuses = _source_statuses(conn, resolved)
    last_snapshot_ts = _latest_issue_specific_success(source_statuses)
    status = "complete" if rows and complete == len(rows) else "partial" if rows else "missing"
    return {
        "issue": resolved,
        "issue_date": only_date or (matches[0]["kickoff_ts"][:10] if matches and matches[0]["kickoff_ts"] else ""),
        "status": "open" if any(m["status"] == "open" for m in matches) else "settled",
        "capture_status": status,
        "last_snapshot_ts": last_snapshot_ts,
        "source_freshness": source_statuses,
        "sales_deadline": max((m["kickoff_ts"] for m in matches if m["kickoff_ts"]), default=""),
        "stats": {
            "n_matches": len(matches),
            "qualified_matches": sum(1 for m in matches if m["q_max"] is not None),
            "qualified_legs": len(q_values),
            "q_avg": sum(q_values) / len(q_values) if q_values else 0,
            "pool_quality_flag": "green" if matches and complete == len(matches) else "yellow" if complete + partial else "red",
        },
        "decision_variant_options": variant_options,
        "strategy_version_context": version_context,
        "matches": matches,
        "source": {
            "kind": "sqlite",
            "provider": "500.com",
            "issue_label": issue_meta["label"] if issue_meta else resolved,
            "scope_date": only_date,
            "path": _public_diagnostics_path(conn.execute("PRAGMA database_list").fetchone()["file"]),
            "tables": ["issues", "matches", "live_sp_snapshots", "fetch_log", "llm_decision_snapshots"],
        },
    }


def _operations_status_payload(conn: sqlite3.Connection, issue: str) -> dict[str, Any]:
    _ensure_decision_snapshot_schema(conn)
    _ensure_live_workflow_schema(conn)
    _ensure_postmatch_review_run_schema(conn)
    resolved = _resolve_issue(conn, issue)
    rows = _issue_rows(conn, resolved, only_date=None)
    versions = _active_version_bundle()
    preferred_review = str(versions.get("review_version") or "v2_active_llm_snapshot_tags")
    settled_rows = [row for row in rows if row["result_code"] is not None or row["winning_sp"] is not None]
    winning_sp_rows = [row for row in rows if row["winning_sp"] is not None]

    source_statuses = _source_statuses(conn, resolved)

    snapshot_counts = {row["status"]: int(row["n"]) for row in conn.execute(
        "SELECT status, COUNT(*) AS n FROM llm_decision_snapshots WHERE issue=? GROUP BY status",
        (resolved,),
    )}
    pending_drafts = [
        {
            "match_idx": int(row["match_idx"]),
            "match_id": row["match_id"] or f"{resolved}_{int(row['match_idx']):03d}",
            "generated_at": row["generated_at"] or "",
            "checked_at": row["checked_at"] or "",
        }
        for row in conn.execute(
            """
            SELECT match_idx, match_id, generated_at, checked_at
            FROM llm_decision_snapshots
            WHERE issue=? AND status='draft_replacement'
            ORDER BY generated_at DESC, match_idx ASC
            """,
            (resolved,),
        )
    ]

    reviewed_indices: set[int] = set()
    latest_review_at = ""
    if _table_exists(conn, "postmatch_reviews"):
        review_rows = conn.execute(
            """
            SELECT match_idx, MAX(reviewed_at) AS reviewed_at
            FROM postmatch_reviews
            WHERE issue=? AND review_version=?
            GROUP BY match_idx
            """,
            (resolved, preferred_review),
        ).fetchall()
        reviewed_indices = {int(row["match_idx"]) for row in review_rows}
        review_times = [str(row["reviewed_at"] or "") for row in review_rows if row["reviewed_at"]]
        if review_times:
            latest_review_at = max(review_times)

    settled_indices = {int(row["match_idx"]) for row in settled_rows}
    unreviewed_indices = sorted(settled_indices - reviewed_indices)
    row_by_idx = {int(row["match_idx"]): row for row in rows}
    unreviewed_matches = [
        {
            "match_idx": idx,
            "match_id": _match_id(row_by_idx[idx]),
            "label": f"{row_by_idx[idx]['home'] or ''} vs {row_by_idx[idx]['away'] or ''}",
            "result_label": row_by_idx[idx]["result_label"] or "",
            "winning_sp": row_by_idx[idx]["winning_sp"],
        }
        for idx in unreviewed_indices
        if idx in row_by_idx
    ]

    latest_candidates = [source.get("last_success_at") for source in source_statuses]
    latest_candidates.extend([row["html_fetched_at"] for row in rows if row["html_fetched_at"]])
    parsed_candidates = [
        (parsed, str(value))
        for value in latest_candidates
        if value
        for parsed in [_parse_timestamp_to_hk(str(value))]
        if parsed is not None
    ]
    latest_snapshot_at = max(parsed_candidates, default=(None, ""))[1] if parsed_candidates else ""

    runtime_status = _dashboard_runtime_summary()
    runtime_health = runtime_status.get("health") if isinstance(runtime_status.get("health"), dict) else {}
    api_probe = runtime_health.get("api") if isinstance(runtime_health.get("api"), dict) else {}
    frontend_probe = runtime_health.get("frontend_local") if isinstance(runtime_health.get("frontend_local"), dict) else {}

    warnings: list[dict[str, Any]] = []
    if not rows:
        warnings.append({"code": "no_matches", "severity": "bad", "label": "当前期无比赛", "detail": "SQLite matches 表未返回当前期比赛。"})
    for source in source_statuses:
        if source["status"] in {"failed", "stale", "partial"}:
            severity = "bad" if source["status"] == "failed" else "warn"
            warnings.append({
                "code": f"source_{source['status']}",
                "severity": severity,
                "label": f"{source['source_name']} {source['status']}",
                "detail": source.get("error") or f"last_success={source.get('last_success_at') or '缺'}",
            })
    if pending_drafts:
        warnings.append({
            "code": "draft_replacement_pending",
            "severity": "warn",
            "label": f"{len(pending_drafts)} 条 draft 待确认",
            "detail": "需要人工确认后才会覆盖 active 决策。",
        })
    if unreviewed_matches:
        warnings.append({
            "code": "postmatch_review_missing",
            "severity": "warn",
            "label": f"{len(unreviewed_matches)} 场已结算未复盘",
            "detail": f"review_version={preferred_review}",
        })
    if snapshot_counts.get("active", 0) < len(rows):
        warnings.append({
            "code": "active_snapshot_missing",
            "severity": "warn",
            "label": "active 决策快照未覆盖全部比赛",
            "detail": f"active={snapshot_counts.get('active', 0)} / matches={len(rows)}",
        })
    latest_workflow = _latest_workflow_payload(conn, resolved)
    workflow_trigger_endpoint = f"POST /api/issues/{resolved}/live-workflow?dry_run=1"
    if latest_workflow:
        latest_workflow = {**latest_workflow, "trigger_endpoint": workflow_trigger_endpoint}
    if latest_workflow and latest_workflow.get("status") == "failed":
        warnings.append({
            "code": "workflow_failed",
            "severity": "bad",
            "label": "最近实盘刷新失败",
            "detail": str(latest_workflow.get("error") or "workflow step failed"),
        })
    latest_review_task = _latest_postmatch_review_run_payload(conn, resolved)
    postmatch_trigger_endpoint = f"POST /api/issues/{resolved}/postmatch-review?dry_run=1"
    if latest_review_task:
        latest_review_task = {**latest_review_task, "trigger_endpoint": postmatch_trigger_endpoint}
    if latest_review_task and latest_review_task.get("status") == "failed":
        warnings.append({
            "code": "postmatch_review_failed",
            "severity": "bad",
            "label": "最近赛后复盘失败",
            "detail": str(latest_review_task.get("error") or "review_settled_matches failed"),
        })

    if not rows:
        capture_status = "missing"
    elif any(source["status"] in {"failed", "stale"} for source in source_statuses):
        capture_status = "warn"
    elif any(source["status"] == "partial" for source in source_statuses):
        capture_status = "partial"
    else:
        capture_status = "ok"

    return {
        "issue": resolved,
        "generated_at": _now_hk_iso(),
        "issue_status": {
            "current_issue": _resolve_issue(conn, "current"),
            "match_count": len(rows),
            "finished_count": len(settled_rows),
            "settled_sp_count": len(winning_sp_rows),
            "open_count": max(0, len(rows) - len(settled_rows)),
            "capture_status": capture_status,
            "latest_snapshot_at": latest_snapshot_at,
            "latest_snapshot_age_minutes": _minutes_since_hk(latest_snapshot_at),
        },
        "runtime": {
            "api_health": "ok" if api_probe.get("ok") else "warn",
            "api_url": "",
            "api_health_url": "",
            "api_port": "",
            "frontend_local_url": "",
            "frontend_remote_url": "",
            "frontend_port": "",
            "frontend_health": "ok" if frontend_probe.get("ok") else "warn",
            **runtime_status,
        },
        "sources": source_statuses,
        "snapshots": {
            "active_count": snapshot_counts.get("active", 0),
            "draft_replacement_count": snapshot_counts.get("draft_replacement", 0),
            "superseded_count": snapshot_counts.get("superseded", 0),
            "pending_drafts": pending_drafts,
        },
        "review": {
            "review_version": preferred_review,
            "settled_match_count": len(settled_rows),
            "reviewed_match_count": len(reviewed_indices & settled_indices),
            "unreviewed_settled_count": len(unreviewed_matches),
            "latest_review_at": latest_review_at,
            "unreviewed_matches": unreviewed_matches,
            "task": latest_review_task
            or {
                "run_id": "",
                "issue": resolved,
                "mode": "postmatch_review_v1",
                "status": "not_run",
                "dry_run": False,
                "requested_by": "",
                "started_at": "",
                "finished_at": "",
                "elapsed_sec": None,
                "error": "",
                "command": [],
                "result": {},
                "trigger_endpoint": postmatch_trigger_endpoint,
            },
        },
        "workflow": latest_workflow
        or {
            "run_id": "",
            "issue": resolved,
            "mode": "live_day_refresh_v1",
            "status": "not_run",
            "dry_run": False,
            "requested_by": "",
            "started_at": "",
            "finished_at": "",
            "elapsed_sec": None,
            "error": "",
            "steps": [],
            "trigger_endpoint": workflow_trigger_endpoint,
        },
        "versions": versions,
        "warnings": warnings,
        "source": {
            "sqlite_db": _public_diagnostics_path(conn.execute("PRAGMA database_list").fetchone()["file"]),
            "tables": ["matches", "fetch_log", "llm_decision_snapshots", "postmatch_reviews", "postmatch_review_issue_summary"],
        },
    }


def _match_detail(
    conn: sqlite3.Connection,
    match_id: str,
    *,
    decision_variant_id: str | None = None,
) -> dict[str, Any]:
    _ensure_decision_snapshot_schema(conn)
    issue, idx = _find_match(conn, match_id)
    rows = _issue_rows(conn, issue, only_date=None)
    row = next((r for r in rows if int(r["match_idx"]) == idx), None)
    if row is None:
        raise LookupError(f"500.com match not found: {match_id}")
    release = _active_strategy_release()
    summary = _match_summary(row)
    detail_payload = _nowscore_detail_payload(conn, row)
    if detail_payload:
        summary["odds_consensus"] = detail_payload.get("odds_consensus", {})
        summary["market_highlights"] = detail_payload.get("highlights", [])
    analysis = _analysis_nowscore(conn, row)
    if analysis["status"] != "ok":
        analysis = _analysis_500(conn, row)
    intelligence = _match_intelligence(conn, row)
    gpt_decision = _gpt_fixed_chain_decision(summary, analysis, intelligence)
    active_snapshot = _latest_decision_snapshot(conn, str(row["issue"]), int(row["match_idx"]), "active")
    draft_snapshot = _latest_decision_snapshot(conn, str(row["issue"]), int(row["match_idx"]), "draft_replacement")
    postmatch_review = _postmatch_review_payload(conn, str(row["issue"]), int(row["match_idx"]))
    if active_snapshot:
        summary.update(_snapshot_row_to_summary_fields(active_snapshot))
        active_codes = [str(code) for code in summary.get("llm_selection_codes", []) if str(code) in OUTCOME_ORDER]
        active_hit = summary.get("result_code") in active_codes if summary.get("result_code") and active_codes else None
        summary["prediction_hit"] = active_hit
    else:
        summary.update(
            {
                "llm_judgment": gpt_decision["judgment"],
                "llm_selection_codes": gpt_decision["selection_codes"],
                "llm_explanation": gpt_decision["explanation"],
                "llm_confidence": gpt_decision["confidence"],
                "llm_confidence_label": gpt_decision["confidence_label"],
                "llm_support": gpt_decision["support"],
                "llm_risks": gpt_decision["risks"],
                "llm_decision_chain": gpt_decision["chain"],
                "llm_source": gpt_decision["source"],
            }
        )
    shadow_variants: list[tuple[dict[int, dict[str, Any]], str]] = []
    suppressed_shadow_variant_ids: list[str] = []
    if not _issue_all_has_result(rows):
        shadow_variants, suppressed_shadow_variant_ids = _structured_shadow_variant_scan(str(row["issue"]), release)
    _attach_decision_variants([summary], shadow_variants, release=release)
    variant_options = _decision_variant_options(shadow_variants, release=release)
    version_context = _strategy_version_context(
        release,
        variant_options,
        decision_variant_id,
        suppressed_shadow_variant_ids=suppressed_shadow_variant_ids,
    )
    _attach_selected_decision_variant([summary], version_context.get("selected_variant_id") or decision_variant_id)
    versions = _active_version_bundle()
    return {
        "match": summary,
        "decision_variant_options": variant_options,
        "strategy_version_context": version_context,
        "decision_variants": summary.get("decision_variants", []),
        "analysis_500": analysis,
        "intelligence": intelligence,
        "decision_snapshot": _snapshot_public_payload(active_snapshot),
        "draft_decision_snapshot": _snapshot_public_payload(draft_snapshot),
        "postmatch_review": postmatch_review,
        "dynamic_decision": {
            "judgment": gpt_decision["judgment"],
            "selection_codes": gpt_decision["selection_codes"],
            "confidence": gpt_decision["confidence"],
            "source": gpt_decision["source"],
        },
        "prediction": {
            "model_version": summary.get("prob_model_version") or versions["prob_model_version"],
            "prob_model_version": summary.get("prob_model_version") or versions["prob_model_version"],
            "q_model_version": summary.get("q_model_version") or versions["q_model_version"],
            "decision_chain_version": summary.get("decision_chain_version") or versions["decision_chain_version"],
            "decision_config_hash": summary.get("decision_config_hash") or versions["decision_config_hash"],
            "review_tag_version": summary.get("review_tag_version") or versions["review_tag_version"],
            "version_bundle": versions,
            "generated_ts": summary["generated_ts"],
            "calculated_ts": summary.get("calculated_ts"),
            "q_calculated_ts": summary.get("q_calculated_ts"),
            "q_input_sp_snapshot_ts": summary.get("q_input_sp_snapshot_ts"),
            "q_input_probability_snapshot_ts": summary.get("q_input_probability_snapshot_ts"),
            "q_input_policy": summary.get("q_input_policy"),
            "prediction_sp_source": summary.get("prediction_sp_source"),
            "prediction_sp_snapshot_ts": summary.get("prediction_sp_snapshot_ts"),
            "probability_snapshot_ts": summary.get("probability_snapshot_ts"),
            "probability_source": summary.get("probability_source"),
            "q_score": summary["q_score"] or 0,
            "confidence_weight": summary["confidence_weight"] or 0,
            "model_p_3": summary["model_p_3"],
            "model_p_1": summary["model_p_1"],
            "model_p_0": summary["model_p_0"],
            "market_p_3": summary["market_p_3"],
            "market_p_1": summary["market_p_1"],
            "market_p_0": summary["market_p_0"],
            "strategy_arms": [{
                "arm_id": "500_market_proxy",
                "selection": summary["selection"] or "pass",
                "selection_codes": summary.get("selection_codes", []),
                "selection_type": summary["selection_type"],
                "active": True,
            }],
            "llm_judgment": summary.get("llm_judgment") or gpt_decision["judgment"],
            "llm_selection_codes": summary.get("llm_selection_codes") or gpt_decision["selection_codes"],
            "llm_explanation": summary.get("llm_explanation") or gpt_decision["explanation"],
            "llm_confidence": summary.get("llm_confidence") or gpt_decision["confidence"],
            "llm_confidence_label": summary.get("llm_confidence_label") or gpt_decision["confidence_label"],
            "llm_support": summary.get("llm_support") or gpt_decision["support"],
            "llm_risks": summary.get("llm_risks") or gpt_decision["risks"],
            "llm_decision_chain": summary.get("llm_decision_chain") or gpt_decision["chain"],
            "llm_source": summary.get("llm_source") or gpt_decision["source"],
            "decision_snapshot_id": summary.get("decision_snapshot_id"),
            "decision_snapshot_status": summary.get("decision_snapshot_status") or ("missing" if not active_snapshot else "active"),
            "decision_snapshot_generated_at": summary.get("decision_snapshot_generated_at"),
            "draft_decision_snapshot_id": draft_snapshot["snapshot_id"] if draft_snapshot else "",
        },
    }


def _ticket_draft(conn: sqlite3.Connection, issue: str, *, only_date: str | None) -> dict[str, Any]:
    resolved = _resolve_issue(conn, issue)
    rows = _issue_rows(conn, resolved, only_date=only_date)
    scored = []
    for row in rows:
        summary = _apply_llm_issue_decision(conn, row, _match_summary(row))
        if summary["selection"] and summary["q_score"] is not None:
            scored.append((_safe_float(summary.get("llm_q_score")) or summary["q_score"], row, summary))
    scored.sort(key=lambda item: item[0], reverse=True)
    legs = []
    for rank, (_score, row, summary) in enumerate(scored[:7], start=1):
        selected = str(summary["selection"])
        sp_map = {"3": summary["sp_3"], "1": summary["sp_1"], "0": summary["sp_0"]}
        legs.append({
            "leg_id": f"L{rank}",
            "match_id": summary["match_id"],
            "league": row["league"],
            "home": row["home"],
            "away": row["away"],
            "handicap": row["handicap_line"],
            "selection": selected,
            "selection_codes": summary.get("selection_codes", []),
            "cover_type": summary.get("selection_type") or "single",
            "sp": sp_map[selected],
            "q_score": summary["q_score"] or 0,
            "llm_q_score": summary.get("llm_q_score") or 0,
            "confidence_weight": summary["confidence_weight"] or 0,
            "llm_confidence": summary.get("llm_confidence") or 0,
            "q_input_sp_snapshot_ts": summary.get("q_input_sp_snapshot_ts") or "",
            "q_input_probability_snapshot_ts": summary.get("q_input_probability_snapshot_ts") or "",
            "q_calculated_ts": summary.get("q_calculated_ts") or "",
            "risk_warnings": ["llm_fixed_chain_recommendation"],
        })
    stake = len(legs) * 2
    return {
        "issue": resolved,
        "plan_id": f"{resolved}-{only_date or 'all'}-500-market-proxy",
        "tickets": [{
            "candidate_id": f"{resolved}-{only_date or 'all'}-market-proxy",
            "stake_yuan": stake,
            "expected_return_yuan": 0,
            "pred_ev_per_stake": 0,
            "expected_payout": 0,
            "coverage_detail": {"n_full": 0, "n_double": 0},
            "risk_warnings": ["真实 500 数据已接入；这里是数据连通性 draft，不是正式 N=7 selector 出票。"],
            "legs": legs,
        }] if legs else [],
        "total": 1 if legs else 0,
        "source": "500_bjdc.sqlite",
    }


def _signals(conn: sqlite3.Connection, issue: str, *, only_date: str | None) -> dict[str, Any]:
    resolved = _resolve_issue(conn, issue)
    rows = _issue_rows(conn, resolved, only_date=only_date)
    signals = []
    for row in rows:
        summary = _apply_llm_issue_decision(conn, row, _match_summary(row))
        if not summary["selection"]:
            continue
        signals.append({
            "match_id": summary["match_id"],
            "qualified_options": [{
                "selection": summary["selection"],
                "selection_codes": summary.get("selection_codes", []),
                "selection_type": summary.get("selection_type", "single"),
                "q_score": summary["q_score"] or 0,
                "llm_q_score": summary.get("llm_q_score") or 0,
                "llm_confidence": summary.get("llm_confidence") or 0,
                "sp_drift_band": summary["sp_drift_band"],
                "arms_recommending": [summary.get("selection_source") or "gpt_fixed_decision_chain_v1"],
            }],
        })
    return {
        "issue": resolved,
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "freshness": "500_sqlite_snapshot",
        "signals": signals,
    }


def _settlement(
    conn: sqlite3.Connection,
    issue: str,
    *,
    decision_variant_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    resolved = _resolve_issue(conn, issue)
    release = _active_strategy_release()
    variant_options = _decision_variant_options([], release=release)
    rows = _issue_rows(conn, resolved, only_date=None)
    settled = [row for row in rows if row["winning_sp"] is not None]
    if not settled:
        return {"error": "not settled", "issue": resolved}, 404
    total_payout = sum(float(row["winning_sp"] or 0) for row in settled)
    postmatch_summary = _postmatch_issue_summary_payload(conn, resolved)
    postmatch_reviews = _postmatch_review_rows_payload(conn, resolved)
    payload = {
        "issue": resolved,
        "settled_ts": datetime.now(timezone.utc).isoformat(),
        "strategy_version_context": _strategy_version_context(release, variant_options, decision_variant_id),
        "decision_variant_options": variant_options,
        "n_tickets": 0,
        "n_hits": 0,
        "n_legs_total": len(rows),
        "n_legs_hit": len(settled),
        "n_legs_missed_by_1": 0,
        "total_stake": 0,
        "total_payout": total_payout,
        "pnl": total_payout,
        "roi": 0,
        "quality_review": "500.com settlement rows only; no generated ticket settlement in this endpoint",
        "per_match_settlements": [{
            "match_id": _match_id(row),
            "result_code": str(row["result_code"]) if row["result_code"] is not None else "",
            "winning_sp": row["winning_sp"],
            "selected_by_arms": [],
            "arm_hits": {},
            "sp_drift": None,
        } for row in settled[:100]],
    }
    if postmatch_summary:
        payload["postmatch_review_issue_summary"] = postmatch_summary
    if postmatch_reviews:
        payload["postmatch_reviews"] = postmatch_reviews
    return payload, 200


def _sample_equity(rows: list[dict[str, Any]], portfolio: str) -> list[float]:
    points = [r for r in rows if r.get("portfolio") == portfolio]
    total = 100.0
    curve = [total]
    for r in points:
        total += _csv_float(r, "profit_units")
        curve.append(total)
    if len(curve) <= 6:
        return curve
    idxs = [round(i * (len(curve) - 1) / 5) for i in range(6)]
    return [curve[i] for i in idxs]


def _strategy_lab(results_dir: Path) -> dict[str, Any]:
    _ = results_dir
    release = _active_strategy_release()
    summary = _main_strategy_summary_rows(release)
    annual = _main_strategy_annual_rows(release)
    issue_profit = _main_strategy_issue_rows(release)
    arms = []
    for row in summary:
        portfolio = row.get("arm_id", "")
        arms.append({
            "arm_id": portfolio,
            "arm_name": row.get("label", portfolio),
            "active": True,
            "roi": row.get("roi", 0),
            "profit": row.get("profit_units", 0),
            "hit_rate": row.get("issue_win_rate", 0),
            "max_dd": row.get("max_drawdown_units", 0),
            "equity_curve": _sample_equity(issue_profit, portfolio),
            "recent_roi": row.get("recent_roi", row.get("roi", 0)),
            "description": row.get("rationale", "Current main strategy candidate"),
        })
    return {
        "strategies": [{
            "strategy_id": "main_strategy_fixed_384",
            "strategy_name": "Current Main Strategy A/B",
            "arms": arms,
            "annual_performance": [{
                "year": row.get("year", 0),
                "n_issues": row.get("n_issues", 0),
                "tickets": 0,
                "stake": row.get("stake_units", 0),
                "profit": row.get("profit_units", 0),
                "roi": row.get("roi", 0),
                "hit_rate": row.get("issue_win_rate", 0),
                "max_dd": row.get("max_drawdown_units", 0),
                "arm_id": row.get("arm_id", ""),
            } for row in annual],
        }],
        "strategy_release": _strategy_release_public_payload(release),
        "source": _relative_display_path(_strategy_main_dir(release)),
    }


def _selector_shadow(results_dir: Path, issue: str) -> dict[str, Any]:
    summary = _read_csv(results_dir / "frozen_selector_summary.csv")
    switch = _read_csv(results_dir / "frozen_selector_switch_summary.csv")
    rolling = _read_csv(results_dir / "frozen_selector_rolling_summary.csv")
    decisions = _read_csv(results_dir / "frozen_selector_decision_log.csv")
    target = "state_L6_DD9000_OR_weakcount_ge4_q0p1_h120"
    latest = decisions[-1] if decisions else {}
    role_map = {
        "baseline_384_hybrid": "baseline",
        "state_L6_DD9000": "state",
        target: "selector",
        "defensive_smooth90_convex10": "defensive",
    }
    arms = []
    for row in summary:
        portfolio = row.get("portfolio", "")
        if portfolio not in role_map:
            continue
        arms.append({
            "arm_id": portfolio,
            "label": portfolio,
            "role": role_map[portfolio],
            "profit_per_256": _csv_float(row, "profit_per_256"),
            "roi": _csv_float(row, "roi"),
            "max_drawdown_units": _csv_float(row, "max_drawdown_units"),
            "max_loss_streak": _csv_int(row, "max_loss_streak"),
            "issue_win_rate": _csv_float(row, "issue_win_rate"),
            "full_loss_rate": _csv_float(row, "full_loss_rate"),
            "recent_profit_per_256": _csv_float(row, "recent_profit_per_256"),
            "delta_profit_per_256_vs_base": _csv_float(row, "delta_profit_per_256_vs_base"),
            "delta_max_drawdown_units_vs_base": _csv_float(row, "delta_maxdd_units_vs_base"),
            "delta_loss_streak_vs_base": _csv_float(row, "delta_loss_streak_vs_base"),
        })
    return {
        "issue": issue,
        "rule_name": target,
        "mode": "live-shadow",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_decision": {
            "chosen_arm": latest.get("chosen_portfolio") or "baseline_384_hybrid",
            "baseline_arm": "baseline_384_hybrid",
            "defensive_arm": "defensive_smooth90_convex10",
            "state_signal": bool(_csv_int(latest, "state_signal")),
            "quality_signal": bool(_csv_int(latest, "quality_signal")),
            "reason": latest.get("switch_reason") or "no current selector run for this issue",
            "pre_loss_streak": _csv_int(latest, "pre_loss_streak"),
            "pre_drawdown_units": _csv_float(latest, "pre_drawdown_units"),
            "weak_count": _csv_int(latest, "weak_count"),
            "weak_score": _csv_float(latest, "weak_score"),
            "quality_history_issues": _csv_int(latest, "quality_history_n"),
            "budget_units": _csv_float(latest, "stake_units", 384),
        },
        "feature_flags": [{
            "feature": key,
            "value": _csv_float(latest, key),
            "threshold": "",
            "weak": False,
            "severity": 0,
        } for key in ["core_avg_pred_ev", "core_avg_q", "core_avg_conf", "core_ticket_count", "same_ticket4_full_risk_avg_source_line_gap"]],
        "arms": arms,
        "switch_attribution": [{
            "group": row.get("group", ""),
            "count": _csv_int(row, "n"),
            "delta_vs_base_units": _csv_float(row, "delta_vs_base_units"),
            "helped": _csv_int(row, "helped_count"),
            "hurt": _csv_int(row, "hurt_count"),
            "flat": _csv_int(row, "flat_count"),
        } for row in switch],
        "rolling_stability": [{
            "window": _csv_int(row, "window"),
            "profit_positive_rate": _csv_float(row, "positive_profit_delta_rate"),
            "max_drawdown_positive_rate": _csv_float(row, "positive_maxdd_delta_rate"),
            "both_positive_rate": _csv_float(row, "both_positive_rate"),
            "avg_profit_delta": _csv_float(row, "avg_profit_delta"),
            "avg_maxdrawdown_delta": _csv_float(row, "avg_maxdd_delta"),
            "avg_loss_streak_delta": _csv_float(row, "avg_loss_streak_delta"),
        } for row in rolling if row.get("portfolio") == target],
        "recent_decisions": [{
            "issue": row.get("issue", ""),
            "year": _csv_int(row, "calendar_year"),
            "chosen_arm": row.get("chosen_portfolio", ""),
            "reason": row.get("switch_reason", ""),
            "delta_vs_base_units": _csv_float(row, "delta_vs_base_units"),
            "base_profit_units": _csv_float(row, "base_profit_units"),
            "selector_profit_units": _csv_float(row, "profit_units"),
            "weak_count": _csv_int(row, "weak_count"),
            "pre_loss_streak": _csv_int(row, "pre_loss_streak"),
            "pre_drawdown_units": _csv_float(row, "pre_drawdown_units"),
            "outcome": "helped" if _csv_int(row, "switch_helped") else "hurt" if _csv_int(row, "switch_hurt") else "flat",
        } for row in decisions[-8:]][::-1],
        "guardrail": f"source={_relative_display_path(results_dir)}; no mock fallback. Current issue selector run must be generated separately before real staking.",
    }


def create_app(
    *,
    sqlite_db: str | os.PathLike[str] = DEFAULT_500_DB,
    results_dir: str | os.PathLike[str] = DEFAULT_RESULTS_DIR,
) -> Flask:
    app = Flask(__name__, static_folder=None)
    db_path = Path(sqlite_db)
    result_path = Path(results_dir)
    static_dir = Path(os.environ.get("BEIDAN_DASHBOARD_STATIC_DIR", DEFAULT_DASHBOARD_STATIC_DIR))
    gate_password = next((os.environ.get(name) for name in DASHBOARD_GATE_PASSWORD_ENVS if os.environ.get(name)), "")
    gate_secret = next((os.environ.get(name) for name in DASHBOARD_GATE_SECRET_ENVS if os.environ.get(name)), gate_password)
    if gate_password:
        app.secret_key = gate_secret or gate_password
        app.permanent_session_lifetime = timedelta(days=30)
    configured_cache_ttl = _safe_float(os.environ.get("BEIDAN_DECISION_API_CACHE_TTL_SEC"))
    cache_ttl_sec = max(0.0, DEFAULT_CACHE_TTL_SEC if configured_cache_ttl is None else configured_cache_ttl)
    response_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}

    def _cache_get(key: tuple[Any, ...]) -> Any | None:
        if cache_ttl_sec <= 0:
            return None
        cached = response_cache.get(key)
        if not cached:
            return None
        expires_at, payload = cached
        if expires_at <= time.monotonic():
            response_cache.pop(key, None)
            return None
        return payload

    def _cache_set(key: tuple[Any, ...], payload: Any) -> None:
        if cache_ttl_sec <= 0:
            return
        if len(response_cache) > 64:
            response_cache.clear()
        response_cache[key] = (time.monotonic() + cache_ttl_sec, payload)

    def _cache_clear() -> None:
        response_cache.clear()

    def _serve_index():
        index_path = static_dir / "index.html"
        if not index_path.exists():
            return jsonify({
                "error": "decision dashboard frontend build is missing",
                "expected": str(index_path),
                "hint": "run npm --prefix apps/decision-dashboard run build",
            }), 503
        response = send_from_directory(static_dir, "index.html")
        response.headers["Cache-Control"] = "no-cache"
        return response

    def _serve_asset(path: str):
        asset_path = static_dir / path
        if not asset_path.is_file():
            return jsonify({"error": f"frontend asset not found: {path}"}), 404
        response = send_from_directory(static_dir, path, max_age=31536000)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.before_request
    def _request_gates():
        if gate_password:
            if request.endpoint in {"dashboard_gate", "dashboard_gate_logout"}:
                return None
            if request.path == "/favicon.ico":
                return None
            if not session.get("dashboard_gate_ok"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "dashboard gate required", "login": "/gate"}), 401
                return redirect("/gate")
        if request.method == "POST" and request.path.startswith("/api/"):
            return _require_operator_token()
        return None

    @app.after_request
    def _cors(resp):
        origin = request.headers.get("Origin", "")
        allowed = _allowed_cors_origins()
        if origin and origin in allowed:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = f"Content-Type,{OPERATOR_TOKEN_HEADER}"
            resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
            resp.headers.add("Vary", "Origin")
        return resp

    @app.route("/gate", methods=["GET", "POST"])
    def dashboard_gate():
        if not gate_password:
            return redirect("/")
        error = ""
        if request.method == "POST":
            passphrase = request.form.get("passphrase") or ""
            if hmac.compare_digest(passphrase, gate_password):
                session["dashboard_gate_ok"] = True
                session.permanent = True
                return redirect("/")
            error = "口令不正确"
        return render_template_string(
            """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>验证 · 北单决策台</title>
  <style>
    :root { color-scheme: light; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; background:#f5f7fb; color:#111827; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    form { width:min(340px, calc(100vw - 36px)); background:#fff; border:1px solid #e5e7eb; border-radius:10px; box-shadow:0 18px 50px rgba(15,23,42,.12); padding:26px; }
    h1 { margin:0 0 18px; font-size:20px; font-weight:650; }
    label { display:block; margin:0 0 8px; font-size:14px; color:#4b5563; }
    input { width:100%; box-sizing:border-box; border:1px solid #cbd5e1; border-radius:8px; padding:11px 12px; font-size:16px; }
    button { width:100%; margin-top:16px; border:0; border-radius:8px; background:#2563eb; color:white; padding:11px 12px; font-size:15px; font-weight:650; cursor:pointer; }
    .err { margin-top:12px; color:#dc2626; font-size:13px; }
  </style>
</head>
<body>
  <form method="post" action="/gate">
    <h1>北单决策台</h1>
    <label for="passphrase">访问口令</label>
    <input id="passphrase" name="passphrase" type="password" autocomplete="current-password" autofocus>
    <button type="submit">进入</button>
    {% if error %}<div class="err">{{ error }}</div>{% endif %}
  </form>
</body>
</html>
            """,
            error=error,
        ), 401 if error else 200

    @app.get("/gate/logout")
    def dashboard_gate_logout():
        session.pop("dashboard_gate_ok", None)
        return redirect("/gate")

    @app.get("/")
    def frontend_index():
        return _serve_index()

    @app.get("/assets/<path:path>")
    def frontend_assets(path: str):
        return _serve_asset(f"assets/{path}")

    @app.get("/<path:path>")
    def frontend_spa(path: str):
        if path == "api" or path.startswith("api/"):
            return jsonify({"error": f"API route not found: /{path}"}), 404
        candidate = static_dir / path
        if candidate.is_file():
            return _serve_asset(path)
        return _serve_index()

    @app.get("/healthz")
    def healthz():
        with _connect(db_path) as conn:
            current = _resolve_issue(conn, "current")
        release = _active_strategy_release()
        release_payload = _strategy_release_public_payload(release)
        payload = {
            "ok": db_path.exists(),
            "provider": "500.com",
            "current_issue": current,
            "scope_date": _today_hk(),
            "strategy_release_id": release.get("release_id"),
            "strategy_release_missing_required_count": len(release_payload["artifact_health"]["missing_required"]),
            "public_diagnostics": _public_diagnostics_enabled(),
        }
        if _public_diagnostics_enabled():
            payload.update({
                "sqlite_db": str(db_path),
                "results_dir": str(result_path),
                "strategy_release_config": release.get("config_path"),
                "strategy_release_missing_required": release_payload["artifact_health"]["missing_required"],
                "main_strategy_dir": _relative_display_path(_strategy_main_dir(release)),
                "high_n_selector_dir": _relative_display_path(_strategy_artifact_path("ticket_pool_dir", HIGH_N_SELECTOR_RESULTS_DIR, release)),
                "model_db": str(DEFAULT_MODEL_DB),
            })
        return jsonify(payload)

    @app.get("/api/strategy-release")
    def strategy_release():
        return jsonify(_strategy_release_public_payload())

    @app.get("/api/issues")
    def issues():
        limit = _safe_int(request.args.get("limit")) or 80
        include_replay = _query_bool(request.args.get("include_replay"), True)
        cacheable = not include_replay
        cache_key = ("issues", limit, include_replay)
        if cacheable:
            cached = _cache_get(cache_key)
            if cached is not None:
                response = jsonify(cached)
                response.headers["X-Beidan-Cache"] = "hit"
                response.headers["Cache-Control"] = "private, max-age=5"
                return response
        with _connect(db_path) as conn:
            payload = {"issues": _available_issues(conn, limit=limit, include_replay=include_replay)}
            if cacheable:
                _cache_set(cache_key, payload)
                response = jsonify(payload)
                response.headers["X-Beidan-Cache"] = "miss"
                response.headers["Cache-Control"] = "private, max-age=5"
                return response
            return jsonify(payload)

    @app.get("/api/issues/<issue>/dashboard")
    def issue_dashboard(issue: str):
        only_date = request.args.get("date")
        decision_variant_id = _requested_decision_variant_id()
        summary_view = str(request.args.get("view") or "").strip().lower() == "summary" or _query_bool(request.args.get("summary"), False)
        cache_key = ("dashboard_summary", issue, only_date, decision_variant_id)
        if summary_view:
            cached = _cache_get(cache_key)
            if cached is not None:
                response = jsonify(cached)
                response.headers["X-Beidan-Cache"] = "hit"
                response.headers["Cache-Control"] = "private, max-age=5"
                return response
        with _connect(db_path) as conn:
            try:
                payload = _dashboard(conn, issue, only_date=only_date, decision_variant_id=decision_variant_id, summary_view=summary_view)
                if summary_view:
                    _cache_set(cache_key, payload)
                    response = jsonify(payload)
                    response.headers["X-Beidan-Cache"] = "miss"
                    response.headers["Cache-Control"] = "private, max-age=5"
                    return response
                return jsonify(payload)
            except LookupError as exc:
                if _main_strategy_issue_exists(issue):
                    return jsonify(_historical_dashboard(issue))
                return jsonify({"error": str(exc)}), 404

    @app.get("/api/matches/<match_id>")
    def match_detail(match_id: str):
        decision_variant_id = _requested_decision_variant_id()
        with _connect(db_path) as conn:
            try:
                return jsonify(_match_detail(conn, match_id, decision_variant_id=decision_variant_id))
            except LookupError as exc:
                try:
                    return jsonify(_historical_match_detail(match_id))
                except LookupError:
                    pass
                return jsonify({"error": str(exc)}), 404

    @app.post("/api/issues/<issue>/decision-snapshots")
    def materialize_issue_decision_snapshots(issue: str):
        only_date = request.args.get("date")
        with _connect(db_path) as conn:
            try:
                payload = _materialize_issue_decision_snapshots(conn, issue, only_date=only_date)
                conn.commit()
                _cache_clear()
                return jsonify(payload)
            except LookupError as exc:
                return jsonify({"error": str(exc)}), 404

    @app.post("/api/matches/<match_id>/decision-snapshot")
    def materialize_match_decision_snapshot(match_id: str):
        with _connect(db_path) as conn:
            try:
                issue, idx = _find_match(conn, match_id)
                rows = _issue_rows(conn, issue, only_date=None)
                row = next((r for r in rows if int(r["match_idx"]) == idx), None)
                if row is None:
                    raise LookupError(f"500.com match not found: {match_id}")
                payload = _materialize_decision_snapshot_for_row(conn, row)
                conn.commit()
                _cache_clear()
                return jsonify(payload)
            except LookupError as exc:
                return jsonify({"error": str(exc)}), 404

    @app.post("/api/matches/<match_id>/decision-snapshot/confirm")
    def confirm_match_decision_snapshot(match_id: str):
        with _connect(db_path) as conn:
            try:
                issue, idx = _find_match(conn, match_id)
                payload = _confirm_decision_snapshot_override(conn, issue, idx)
                conn.commit()
                _cache_clear()
                return jsonify(payload)
            except LookupError as exc:
                return jsonify({"error": str(exc)}), 404

    @app.get("/api/issues/<issue>/tickets")
    def tickets(issue: str):
        _ = request.args.get("status", "candidate")
        only_date = request.args.get("date")
        if issue in {"current", "latest"} and only_date is None:
            only_date = _today_hk()
        with _connect(db_path) as conn:
            try:
                return jsonify(_ticket_draft(conn, issue, only_date=only_date))
            except LookupError as exc:
                if _main_strategy_issue_exists(issue):
                    return jsonify(_historical_ticket_draft(issue))
                return jsonify({"error": str(exc)}), 404

    @app.get("/api/issues/<issue>/main-strategy")
    def main_strategy(issue: str):
        only_date = request.args.get("date")
        decision_variant_id = _requested_decision_variant_id()
        if issue in {"current", "latest"} and only_date is None:
            only_date = _today_hk()
        with _connect(db_path) as conn:
            return jsonify(_main_strategy_payload(conn, issue, only_date=only_date, decision_variant_id=decision_variant_id))

    @app.get("/api/issues/<issue>/signals")
    def signals(issue: str):
        only_date = request.args.get("date")
        if issue in {"current", "latest"} and only_date is None:
            only_date = _today_hk()
        with _connect(db_path) as conn:
            try:
                return jsonify(_signals(conn, issue, only_date=only_date))
            except LookupError as exc:
                if _main_strategy_issue_exists(issue):
                    return jsonify(_historical_signals(issue))
                return jsonify({"error": str(exc)}), 404

    @app.get("/api/issues/<issue>/operations")
    def operations_status(issue: str):
        with _connect(db_path) as conn:
            try:
                return jsonify(_operations_status_payload(conn, issue))
            except LookupError as exc:
                return jsonify({"error": str(exc)}), 404

    @app.post("/api/issues/<issue>/live-workflow")
    def live_workflow(issue: str):
        dry_run_arg = str(request.args.get("dry_run") or request.args.get("dryRun") or "").lower()
        body = request.get_json(silent=True) or {}
        dry_run = dry_run_arg in {"1", "true", "yes", "y"} or bool(body.get("dry_run") or body.get("dryRun"))
        requested_by = request.headers.get("X-Requested-By") or "decision_dashboard"
        with _connect(db_path) as conn:
            try:
                payload = _run_live_workflow(conn, db_path, issue, dry_run=dry_run, requested_by=requested_by)
                _cache_clear()
                return jsonify(payload), 200 if payload.get("status") != "failed" else 500
            except LookupError as exc:
                return jsonify({"error": str(exc)}), 404
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

    @app.post("/api/issues/<issue>/postmatch-review")
    def postmatch_review(issue: str):
        dry_run_arg = str(request.args.get("dry_run") or request.args.get("dryRun") or "").lower()
        body = request.get_json(silent=True) or {}
        dry_run = dry_run_arg in {"1", "true", "yes", "y"} or bool(body.get("dry_run") or body.get("dryRun"))
        requested_by = request.headers.get("X-Requested-By") or "decision_dashboard"
        with _connect(db_path) as conn:
            try:
                payload = _run_postmatch_review_task(conn, db_path, issue, dry_run=dry_run, requested_by=requested_by)
                _cache_clear()
                return jsonify(payload), 200 if payload.get("status") != "failed" else 500
            except LookupError as exc:
                return jsonify({"error": str(exc)}), 404
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

    @app.get("/api/issues/<issue>/settlement")
    def settlement(issue: str):
        decision_variant_id = _requested_decision_variant_id()
        with _connect(db_path) as conn:
            try:
                payload, status = _settlement(conn, issue, decision_variant_id=decision_variant_id)
            except LookupError as exc:
                if _main_strategy_issue_exists(issue):
                    payload, status = _historical_settlement(issue)
                else:
                    return jsonify({"error": str(exc)}), 404
            return jsonify(payload), status

    @app.get("/api/strategies/lab")
    def strategy_lab():
        return jsonify(_strategy_lab(result_path))

    @app.get("/api/issues/<issue>/selector-shadow")
    def selector_shadow(issue: str):
        return jsonify(_selector_shadow(result_path, issue))

    return app


def main() -> None:
    app = create_app(
        sqlite_db=os.environ.get("BEIDAN_500_DB", DEFAULT_500_DB),
        results_dir=os.environ.get("BEIDAN_SELECTOR_RESULTS_DIR", DEFAULT_RESULTS_DIR),
    )
    host = os.environ.get("BEIDAN_DECISION_API_HOST", DEFAULT_DECISION_API_HOST)
    port = int(os.environ.get("BEIDAN_DECISION_API_PORT", "8790"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
