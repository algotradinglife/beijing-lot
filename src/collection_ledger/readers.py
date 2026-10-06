"""Read-only inventory readers for data-collection and integration objects.

Every reader takes explicit paths, performs no network access and no writes, and
returns plain dictionaries so results are easy to diff and to test. Unit
enablement is derived from file evidence only: ``*.target.wants`` links that
resolve to an existing unit, plus a timer's ``Unit=`` relationship. Live systemd
state is an optional, explicitly opt-in enrichment (``systemd_states``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Object states shared across the ledger.
RUNNING = "running"
ARCHIVED = "archived"
RETIRED = "retired"
UNKNOWN = "unknown"
AVAILABLE = "available"
UNAVAILABLE = "unavailable"

ALL_STATES = (RUNNING, ARCHIVED, RETIRED, UNKNOWN, AVAILABLE, UNAVAILABLE)

# A path whose name ends with one of these markers is a retired artifact.
RETIRED_MARKERS = (".bak", ".old", ".retired", ".disabled", ".superseded")

# Supported retirement-ledger schemas; only these authorize removal evidence.
RETIREMENT_SCHEMAS = ("beijing_lot_source_retirement_v1",)

try:  # ``src`` is importable (repo convention) ...
    from operations_adapters import CollectionPlanError, load_collection_plan
except ImportError:  # pragma: no cover - package layout only
    from src.operations_adapters import (  # type: ignore[no-redef]
        CollectionPlanError,
        load_collection_plan,
    )


class LedgerError(ValueError):
    """The inputs needed to build the ledger are missing or invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_retired_name(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.endswith(marker) for marker in RETIRED_MARKERS)


def exact_retirement_marker(name: str, original: str) -> str | None:
    """Return the retirement marker iff ``name`` is exactly ``original`` + marker."""
    for marker in RETIRED_MARKERS:
        if name == f"{original}{marker}":
            return marker
    return None


# --------------------------------------------------------------------------- #
# Repository collector plan
# --------------------------------------------------------------------------- #

def read_repo_plan(plan_path: Path) -> dict[str, Any]:
    """Read the repo collector plan and normalize each collector to a dict."""
    plan_path = Path(plan_path)
    try:
        plan = load_collection_plan(plan_path)
    except CollectionPlanError as exc:
        raise LedgerError(str(exc)) from exc

    collectors: list[dict[str, Any]] = []
    for item in plan["collectors"]:
        code_entry = str(item.get("code_entry") or "")
        code_path = code_entry.split(":", 1)[0].strip()
        collectors.append(
            {
                "collector_id": str(item.get("collector_id")),
                "label": item.get("label"),
                "code_entry": code_entry,
                "code_path": code_path,
                "code_name": Path(code_path).name if code_path else "",
                "enabled": bool(item.get("enabled")),
                "importance": item.get("importance"),
                "owner_process": item.get("owner_process"),
                "source": item.get("source"),
                "database": item.get("database"),
                "tables": [str(table) for table in (item.get("tables") or [])],
                "schedule_interval_sec": item.get("schedule_interval_sec"),
                "stale_after_sec": item.get("stale_after_sec"),
            }
        )
    return {
        "path": str(plan_path),
        "schema_version": plan.get("schema_version"),
        "updated_at": plan.get("updated_at"),
        "collectors": collectors,
    }


# --------------------------------------------------------------------------- #
# systemd units (parse from disk; no systemctl required)
# --------------------------------------------------------------------------- #

_PATH_TOKEN = re.compile(r"([A-Za-z0-9_~/.@%+\-]+\.(?:py|sh))")
_MODULE_TOKEN = re.compile(r"-m\s+([A-Za-z_][\w.]*)")
_SPECIFIER = re.compile(r"%[A-Za-z]")


def expand_unit_path(raw: str, *, home: str) -> tuple[str, list[str]]:
    """Expand the supported systemd specifiers in a unit path.

    Returns ``(expanded_path, unsupported_specifiers)``. A non-empty second
    element means the path cannot be resolved from file evidence, and callers
    must treat it as unknown rather than reporting absence.
    """
    unsupported: list[str] = []
    text = raw.strip()
    if text.startswith("~"):
        text = home + text[1:]
    for match in _SPECIFIER.finditer(text):
        specifier = match.group(0)
        if specifier[1].lower() == "h":
            text = text.replace(specifier, home)
        else:
            unsupported.append(specifier)
    return text, sorted(set(unsupported))


def parse_unit_text(text: str) -> dict[str, list[str]]:
    """Parse a unit file into ``section.key -> [values]``.

    Duplicate keys are preserved in order and backslash line continuations are
    joined first.
    """
    joined: list[str] = []
    for raw in text.splitlines():
        if joined and joined[-1].endswith("\\"):
            joined[-1] = joined[-1][:-1] + raw.strip()
        else:
            joined.append(raw)

    entries: dict[str, list[str]] = {}
    section = ""
    for line in joined:
        stripped = line.strip()
        if not stripped or stripped[0] in "#;":
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        entries.setdefault(f"{section}.{key.strip().lower()}", []).append(value.strip())
    return entries


def extract_paths(commands: Iterable[str]) -> list[str]:
    found: list[str] = []
    for command in commands:
        for match in _PATH_TOKEN.finditer(command):
            token = match.group(1)
            if token not in found:
                found.append(token)
    return found


def extract_modules(commands: Iterable[str]) -> list[str]:
    found: list[str] = []
    for command in commands:
        for match in _MODULE_TOKEN.finditer(command):
            if match.group(1) not in found:
                found.append(match.group(1))
    return found


def discover_wants_dirs(directory: Path) -> list[str]:
    """Names of every ``*.target.wants`` directory present in ``directory``."""
    try:
        return sorted(
            child.name for child in directory.iterdir()
            if child.is_dir() and child.name.endswith(".target.wants")
        )
    except OSError:
        return []


def _wants_links(unit_dir: Path, unit_name: str, wants_dirs: Iterable[str]) -> tuple[list[str], list[str]]:
    """Return ``(valid_wants, dangling_wants)`` for a unit.

    A want counts only when its target exists; a dangling symlink is recorded
    separately and never proves scheduling.
    """
    valid: list[str] = []
    dangling: list[str] = []
    for wants in wants_dirs:
        link = unit_dir / wants / unit_name
        if not (link.is_symlink() or link.exists()):
            continue
        if link.is_symlink() and not link.exists():
            dangling.append(wants)
        else:
            valid.append(wants)
    return valid, dangling


def read_systemd_units(unit_dirs: Iterable[Path]) -> list[dict[str, Any]]:
    """Inventory ``*.service`` and ``*.timer`` units across the given dirs."""
    units: list[dict[str, Any]] = []
    for directory in unit_dirs:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        wants_dirs = discover_wants_dirs(directory)
        paths = sorted(directory.glob("*.service")) + sorted(directory.glob("*.timer"))
        for path in paths:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            entries = parse_unit_text(text)
            commands = entries.get("service.execstart", []) + entries.get("service.execstartpre", [])
            code_paths = extract_paths(commands)
            valid, dangling = _wants_links(directory, path.name, wants_dirs)
            units.append(
                {
                    "unit": path.name,
                    "unit_kind": path.suffix.lstrip("."),
                    "unit_dir": str(directory),
                    "linked": path.is_symlink(),
                    "fragment": str(path.resolve()) if path.is_symlink() else str(path),
                    "description": (entries.get("unit.description") or [None])[0],
                    "exec_start": entries.get("service.execstart", []),
                    "exec_pre": entries.get("service.execstartpre", []),
                    "working_directory": (entries.get("service.workingdirectory") or [None])[0],
                    "environment": entries.get("service.environment", []),
                    "code_paths": code_paths,
                    "code_names": [Path(p).name for p in code_paths],
                    "modules": extract_modules(commands),
                    "wants_links": valid,
                    "dangling_wants": dangling,
                    "direct_scheduled": bool(valid),
                    "timer_unit": (entries.get("timer.unit") or [None])[0],
                    "is_template": "@" in path.stem,
                }
            )
    return units


def read_repo_units(repo_root: Path, relative: str = "ops/systemd/user") -> list[dict[str, Any]]:
    """Inventory the unit files committed under ``ops/systemd/user``."""
    return read_systemd_units([Path(repo_root) / relative])


def is_collection_unit(unit: dict[str, Any], *, markers: Iterable[str]) -> bool:
    """True when a unit belongs to the data-collection surface."""
    name = unit.get("unit", "")
    if name.startswith(("beidanlot-", "beijing-lot-", "titan-")):
        return True
    if "collect" in name or "capture" in name or "market" in name:
        return True
    for path in unit.get("code_paths") or []:
        if any(marker in path for marker in markers):
            return True
    working = unit.get("working_directory") or ""
    if working and any(marker in working for marker in markers):
        return True
    return False


def systemd_states(units: Iterable[str]) -> dict[str, dict[str, str]]:
    """Query the user manager for live unit state (opt-in, best-effort)."""
    states: dict[str, dict[str, str]] = {}
    for unit in units:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "show", unit,
                 "--property=ActiveState", "--property=UnitFileState"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        props = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        states[unit] = {"active": props.get("ActiveState", ""), "enabled": props.get("UnitFileState", "")}
    return states


# --------------------------------------------------------------------------- #
# External registry and data stores
# --------------------------------------------------------------------------- #

def read_external_registry(registry_dir: Path | None) -> dict[str, Any]:
    """Inventory ``registry/*.json`` files, referenced stores and retirements."""
    files: list[dict[str, Any]] = []
    stores: list[dict[str, Any]] = []
    retired: list[dict[str, Any]] = []
    directory = Path(registry_dir) if registry_dir else None
    result = {
        "directory": str(directory) if directory else None,
        "available": bool(directory and directory.is_dir()),
        "files": files,
        "stores": stores,
        "retired": retired,
    }
    if directory is None or not directory.is_dir():
        return result

    for path in sorted(directory.glob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            files.append({"file": path.name, "schema": None, "status": None, "error": "unreadable"})
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            files.append({"file": path.name, "schema": None, "status": None, "error": "unreadable"})
            continue
        if not isinstance(payload, dict):
            files.append({"file": path.name, "schema": None, "status": None, "error": "not-an-object"})
            continue
        status = payload.get("status") or payload.get("state")
        schema = payload.get("schema")
        files.append({"file": path.name, "schema": schema, "status": status, "error": None})

        for key, value in payload.items():
            if isinstance(value, str) and (key == "database" or key.endswith("_root")):
                stores.append({"registry": path.name, "key": key, "relpath": value, "status": status})

        # Only a validated retirement-ledger schema authorizes removal evidence.
        if schema in RETIREMENT_SCHEMAS:
            entries = payload.get("entries")
            if isinstance(entries, dict):
                for source, meta in entries.items():
                    if not isinstance(meta, dict):
                        continue
                    state = str(meta.get("state") or "").upper()
                    if state in {"REMOVED", "RETIRED"}:
                        retired.append(
                            {
                                "source": source,
                                "archive": meta.get("archive"),
                                "archive_sha256": meta.get("archive_sha256") or meta.get("archive_sha"),
                                "removed_at_utc": meta.get("removed_at_utc"),
                                "registry": path.name,
                            }
                        )
    return result


def read_store(path: Path, *, base: Path | None = None) -> dict[str, Any]:
    """Describe a data store path: existence, size and modification time."""
    path = Path(path)
    resolved = (Path(base) / path) if (base is not None and not path.is_absolute()) else path
    info: dict[str, Any] = {
        "path": str(path),
        "resolved": str(resolved),
        "exists": False,
        "bytes": None,
        "mtime_utc": None,
        "retired_name": is_retired_name(resolved.name),
    }
    if resolved.exists():
        stat = resolved.stat()
        info["exists"] = True
        info["bytes"] = stat.st_size
        info["mtime_utc"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return info


def looks_like_path(value: Any) -> bool:
    """True when a plan ``database`` field names an actual path."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or any(ch.isspace() for ch in text):
        return False
    return text.endswith((".sqlite", ".db", ".sqlite3")) or "/" in text


def resolve_declared_path(value: str, *, base: Path | None) -> Path:
    """Resolve a registry-declared path against a base when it is relative."""
    candidate = Path(value)
    if candidate.is_absolute() or base is None:
        return candidate
    return Path(base) / candidate


def home_directory() -> str:
    return os.path.expanduser("~")
