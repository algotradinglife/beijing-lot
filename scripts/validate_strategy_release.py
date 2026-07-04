#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config/strategy_release.json"


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


def validate_strategy_release(
    config_path: Path = DEFAULT_CONFIG,
    *,
    release_id: str | None = None,
    allow_missing: bool = False,
) -> dict[str, Any]:
    config = _load_json(config_path)
    active_id, release = _active_release(config, release_id)
    artifacts = _artifact_paths(release)
    errors: list[str] = []
    warnings: list[str] = []

    if str(config.get("schema_version") or "") != "strategy_release_registry_v1":
        errors.append("schema_version must be strategy_release_registry_v1")
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
