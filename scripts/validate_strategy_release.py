#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config/strategy_release.json"
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DECISION_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.(?:[0-9]{4}|[0-9]+)$")
RELEASE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*_[0-9]{4}_[0-9]{2}_[0-9]{2}$")
ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
DEFAULTABLE_WHEN = {"always", "available", "never"}
MISSING_BEHAVIOR = {"builtin_active", "fallback_to_active", "diagnostic_placeholder", "hidden_until_artifact", "artifact_missing", "unavailable"}
LATE_REFRESH_POLICY = {"not_applicable", "strict_wait_before_valid_live_sp_refresh", "unlock_after_valid_live_sp_refresh"}


def _project_path(value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else PROJECT_ROOT / path


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError(f"{_display_path(path)} must contain a JSON object")
    return loaded


def _active_release(config: dict[str, Any], release_id: str | None) -> tuple[str, dict[str, Any]]:
    releases = config.get("releases")
    if not isinstance(releases, dict) or not releases:
        raise ValueError("strategy release config must contain non-empty releases object")
    active_id = release_id or str(config.get("active_release_id") or "")
    if not active_id:
        raise ValueError("strategy release config must set active_release_id or --release")
    release = releases.get(active_id)
    if not isinstance(release, dict):
        raise ValueError(f"release not found: {active_id}")
    return active_id, release


def _artifact_paths(release: dict[str, Any]) -> dict[str, Path]:
    artifacts = release.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return {}
    return {
        str(key): _project_path(value)
        for key, value in artifacts.items()
        if value not in {None, ""}
    }


def _resolve_required_artifact(spec: str, artifacts: dict[str, Path]) -> Path:
    if spec in artifacts:
        return artifacts[spec]
    if "/" in spec:
        key, suffix = spec.split("/", 1)
        if key in artifacts:
            return artifacts[key] / suffix
    return _project_path(spec)


def _read_csv_headers(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        return next(reader, [])


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _is_iso_datetime(value: Any) -> bool:
    text = str(value or "")
    if not ISO_DATETIME_RE.fullmatch(text):
        return False
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _validate_release_contract(release_key: str, release: dict[str, Any], errors: list[str]) -> None:
    if not RELEASE_ID_RE.fullmatch(release_key):
        errors.append(f"release key must be lowercase snake-case with YYYY_MM_DD suffix: {release_key}")
    if str(release.get("release_id") or "") != release_key:
        errors.append(f"release_id must match release key: {release_key}")
    if not RELEASE_ID_RE.fullmatch(str(release.get("release_id") or "")):
        errors.append(f"{release_key} release_id must be lowercase snake-case with YYYY_MM_DD suffix")
    if not SEMVER_RE.fullmatch(str(release.get("version_id") or "")):
        errors.append(f"{release_key} version_id must use x.y.z")
    if not _is_iso_datetime(release.get("generated_at")):
        errors.append(f"{release_key} generated_at must be ISO datetime with timezone")
    if not str(release.get("effective_from_issue") or ""):
        errors.append(f"{release_key} must set effective_from_issue")

    artifact_scope = release.get("artifact_scope", {})
    if not isinstance(artifact_scope, dict):
        errors.append(f"{release_key} artifact_scope must be an object")
        artifact_scope = {}
    for key in ("historical_data_start", "backtest_through_issue", "live_issue_policy", "freeze_policy"):
        if not str(artifact_scope.get(key) or ""):
            errors.append(f"{release_key} artifact_scope.{key} is required")

    snapshots = release.get("snapshot_timestamps", {})
    if not isinstance(snapshots, dict):
        errors.append(f"{release_key} snapshot_timestamps must be an object")
        snapshots = {}
    for key in ("probability_model", "q_model", "confidence_model", "decision_chain"):
        if not _is_iso_datetime(snapshots.get(key)):
            errors.append(f"{release_key} snapshot_timestamps.{key} must be ISO datetime with timezone")

    model_versions = release.get("model_versions", {})
    if not isinstance(model_versions, dict):
        errors.append(f"{release_key} model_versions must be an object")
        model_versions = {}
    for key in ("probability_model", "q_model", "decision_chain", "shadow_decision_chain"):
        if not str(model_versions.get(key) or ""):
            errors.append(f"{release_key} model_versions.{key} is required")

    artifacts = release.get("artifacts", {})
    if not isinstance(artifacts, dict):
        errors.append(f"{release_key} artifacts must be an object")
        artifacts = {}
    for key in ("main_strategy_dir", "ticket_pool_csv", "joint_leg_rows_csv"):
        if not str(artifacts.get(key) or ""):
            errors.append(f"{release_key} artifacts.{key} is required")

    variants = release.get("decision_variants", [])
    if not isinstance(variants, list) or not variants:
        errors.append(f"{release_key} must declare decision_variants")
        return
    variant_ids: set[str] = set()
    legacy_aliases: dict[str, str] = {}
    if not any(isinstance(item, dict) and item.get("kind") == "active" for item in variants):
        errors.append(f"{release_key} must declare one active decision variant")
    default_variants = [
        item
        for item in variants
        if isinstance(item, dict) and item.get("is_default")
    ]
    if not default_variants:
        errors.append(f"{release_key} must declare one default decision variant")
    elif len(default_variants) > 1:
        errors.append(f"{release_key} must declare only one default decision variant")
    for idx, variant in enumerate(variants):
        if not isinstance(variant, dict):
            errors.append(f"{release_key} decision_variants[{idx}] must be an object")
            continue
        variant_id = str(variant.get("variant_id") or "")
        if not variant_id:
            errors.append(f"{release_key} decision_variants[{idx}].variant_id is required")
        elif variant_id in variant_ids:
            errors.append(f"{release_key} decision variant duplicated: {variant_id}")
        else:
            variant_ids.add(variant_id)
        if not DECISION_VERSION_RE.fullmatch(str(variant.get("version_id") or "")):
            errors.append(f"{release_key} decision_variants[{idx}].version_id must use x.y.abcd")
        kind = str(variant.get("kind") or "")
        if kind not in {"active", "shadow", "draft"}:
            errors.append(f"{release_key} decision_variants[{idx}].kind is invalid")
        if kind == "shadow":
            artifact_key = str(variant.get("artifact_key") or "")
            if not artifact_key:
                errors.append(f"{release_key} shadow decision variant {variant.get('variant_id', idx)} must set artifact_key")
            elif artifact_key not in artifacts:
                errors.append(f"{release_key} shadow decision variant {variant.get('variant_id', idx)} artifact_key not in artifacts: {artifact_key}")
        readiness = variant.get("readiness", {})
        if readiness:
            if not isinstance(readiness, dict):
                errors.append(f"{release_key} decision variant {variant.get('variant_id', idx)} readiness must be an object")
                continue
            if "artifact_required" in readiness and not isinstance(readiness.get("artifact_required"), bool):
                errors.append(f"{release_key} decision variant {variant.get('variant_id', idx)} readiness.artifact_required must be boolean")
            if readiness.get("defaultable_when") not in {None, "", *DEFAULTABLE_WHEN}:
                errors.append(f"{release_key} decision variant {variant.get('variant_id', idx)} readiness.defaultable_when is invalid")
            if readiness.get("missing_behavior") not in {None, "", *MISSING_BEHAVIOR}:
                errors.append(f"{release_key} decision variant {variant.get('variant_id', idx)} readiness.missing_behavior is invalid")
            if readiness.get("late_refresh") not in {None, "", *LATE_REFRESH_POLICY}:
                errors.append(f"{release_key} decision variant {variant.get('variant_id', idx)} readiness.late_refresh is invalid")
        aliases = variant.get("legacy_aliases", [])
        if aliases:
            if not isinstance(aliases, list):
                errors.append(f"{release_key} decision variant {variant.get('variant_id', idx)} legacy_aliases must be a list")
            else:
                for alias in aliases:
                    alias_text = str(alias or "")
                    if not alias_text:
                        errors.append(f"{release_key} decision variant {variant.get('variant_id', idx)} legacy_aliases cannot contain empty values")
                    elif alias_text == variant_id:
                        errors.append(f"{release_key} decision variant {variant_id} legacy_aliases cannot contain itself")
                    elif alias_text in legacy_aliases:
                        errors.append(f"{release_key} legacy alias duplicated: {alias_text}")
                    else:
                        legacy_aliases[alias_text] = variant_id
        if variant_id == "active_v3":
            readiness_payload = variant.get("readiness") if isinstance(variant.get("readiness"), dict) else {}
            if variant.get("is_default"):
                errors.append(f"{release_key} active_v3 is retired and cannot be default")
            if variant.get("selectable") is not False:
                errors.append(f"{release_key} active_v3 is retired and cannot be selectable")
            if readiness_payload.get("defaultable_when") != "never":
                errors.append(f"{release_key} active_v3 readiness.defaultable_when must be never")

    active_v333 = next(
        (item for item in variants if isinstance(item, dict) and item.get("variant_id") == "active_v3.3.3"),
        None,
    )
    if active_v333:
        readiness_payload = active_v333.get("readiness") if isinstance(active_v333.get("readiness"), dict) else {}
        aliases = {str(alias) for alias in active_v333.get("legacy_aliases", [])}
        if "shadow_v3.3.3" not in aliases:
            errors.append(f"{release_key} active_v3.3.3 must declare shadow_v3.3.3 as a legacy alias")
        if readiness_payload.get("missing_behavior") != "artifact_missing":
            errors.append(f"{release_key} active_v3.3.3 missing_behavior must be artifact_missing")


def validate_strategy_release(
    config_path: Path = DEFAULT_CONFIG,
    *,
    release_id: str | None = None,
    allow_missing: bool = False,
) -> dict[str, Any]:
    config = _load_json(config_path)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        active_id, release = _active_release(config, release_id)
    except ValueError as exc:
        active_id = release_id or str(config.get("active_release_id") or "")
        release = {}
        errors.append(str(exc))
    artifacts = _artifact_paths(release)

    if str(config.get("schema_version") or "") != "strategy_release_registry_v1":
        errors.append("schema_version must be strategy_release_registry_v1")
    releases = config.get("releases")
    if not isinstance(releases, dict) or not releases:
        errors.append("strategy release config must contain non-empty releases object")
        releases = {}
    active_release_id = str(config.get("active_release_id") or "")
    if active_release_id and not RELEASE_ID_RE.fullmatch(active_release_id):
        errors.append(f"active_release_id must be lowercase snake-case with YYYY_MM_DD suffix: {active_release_id}")
    if active_release_id and active_release_id not in releases:
        errors.append(f"active_release_id not found in releases: {active_release_id}")
    for release_key, release_value in releases.items():
        if isinstance(release_value, dict):
            _validate_release_contract(str(release_key), release_value, errors)
        else:
            errors.append(f"release must be an object: {release_key}")
    if str(release.get("release_id") or active_id) != active_id:
        errors.append("release_id must match active release key")

    required_specs = release.get("required_artifacts", [])
    if not isinstance(required_specs, list) or not required_specs:
        errors.append("release must declare required_artifacts")
        required_specs = []

    required = []
    for spec in required_specs:
        path = _resolve_required_artifact(str(spec), artifacts)
        exists = path.exists()
        required.append({"spec": str(spec), "path": _display_path(path), "exists": exists})
        if not exists:
            message = f"missing required artifact {spec}: {_display_path(path)}"
            if allow_missing:
                warnings.append(message)
            else:
                errors.append(message)

    arms = release.get("main_strategy_arms", [])
    arm_ids = [str(arm.get("arm_id")) for arm in arms if isinstance(arm, dict) and arm.get("arm_id")]
    if not arm_ids:
        errors.append("release must declare at least one main_strategy_arms[].arm_id")

    summary_csv = _resolve_required_artifact("main_strategy_dir/sleeve_mix_summary.csv", artifacts)
    if summary_csv.exists():
        headers = _read_csv_headers(summary_csv)
        for col in ["portfolio", "roi", "profit_units", "max_drawdown_units"]:
            if col not in headers:
                errors.append(f"{_display_path(summary_csv)} missing expected column: {col}")
        rows = _read_csv_rows(summary_csv)
        portfolios = {str(row.get("portfolio") or "") for row in rows}
        missing_arms = [arm for arm in arm_ids if arm not in portfolios]
        if missing_arms:
            errors.append(f"sleeve_mix_summary.csv missing configured arms: {', '.join(missing_arms)}")

    ticket_pool = artifacts.get("ticket_pool_csv")
    if ticket_pool and ticket_pool.exists():
        headers = _read_csv_headers(ticket_pool)
        for col in ["issue", "legs", "selected_stake_units"]:
            if col not in headers:
                errors.append(f"{_display_path(ticket_pool)} missing expected column: {col}")

    variants = release.get("decision_variants", [])
    if not isinstance(variants, list) or not variants:
        warnings.append("release has no decision_variants; UI will only expose built-in active fallback")
    elif not any(isinstance(item, dict) and item.get("kind") == "shadow" for item in variants):
        warnings.append("release has no shadow decision variant")

    report = {
        "ok": not errors,
        "config_path": _display_path(config_path),
        "schema_version": config.get("schema_version", ""),
        "active_release_id": active_id,
        "release_status": release.get("status", ""),
        "strategy_family": release.get("strategy_family", ""),
        "model_versions": release.get("model_versions", {}),
        "main_strategy_arms": arm_ids,
        "decision_variants": [
            {
                "variant_id": item.get("variant_id"),
                "kind": item.get("kind"),
                "source": item.get("source"),
                "is_default": item.get("is_default"),
                "readiness": item.get("readiness", {}),
            }
            for item in variants
            if isinstance(item, dict)
        ],
        "artifacts": {key: _display_path(path) for key, path in artifacts.items()},
        "required_artifacts": required,
        "errors": errors,
        "warnings": warnings,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate dashboard strategy release manifest and artifacts.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="strategy release JSON path")
    parser.add_argument("--release", default=None, help="release id to validate; defaults to active_release_id")
    parser.add_argument("--allow-missing", action="store_true", help="downgrade missing artifact files to warnings")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        report = validate_strategy_release(
            Path(args.config),
            release_id=args.release,
            allow_missing=args.allow_missing,
        )
    except Exception as exc:
        report = {
            "ok": False,
            "config_path": args.config,
            "errors": [str(exc)],
            "warnings": [],
        }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        status = "OK" if report["ok"] else "FAILED"
        print(f"strategy release validation: {status}")
        print(f"active_release_id: {report.get('active_release_id', '')}")
        for warning in report.get("warnings", []):
            print(f"warning: {warning}")
        for error in report.get("errors", []):
            print(f"error: {error}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
