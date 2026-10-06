"""Reconcile collection observations into one master ledger with drift findings.

The ledger answers: which collection / integration objects exist, in which state
(``running`` / ``archived`` / ``retired`` / ``unknown``), and where the repository
registry, the scheduled host, the external registry and the data stores disagree.

It is read-only and deterministic: no network access, no writes, and every input
path is explicit so the result can be reproduced offline from fixtures. Repository
unit definitions and host observations are kept as separate inventories and
reconciled by unit name, so a repository copy never masquerades as host evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .readers import (
    ARCHIVED,
    AVAILABLE,
    RETIRED,
    RETIRED_MARKERS,
    RUNNING,
    UNAVAILABLE,
    UNKNOWN,
    LedgerError,
    expand_unit_path,
    home_directory,
    is_collection_unit,
    looks_like_path,
    read_external_registry,
    read_repo_plan,
    read_repo_units,
    read_store,
    read_systemd_units,
    resolve_declared_path,
    utc_now,
)

LEDGER_SCHEMA = "beijing_lot_collection_ledger_v1"

DEFAULT_HOST_UNIT_DIRS = ("~/.config/systemd/user",)
DEFAULT_EXTERNAL_DATA_ROOT = "/run/media/drwho1985/Sandisk/data/beijing-lot"
DEFAULT_EXTERNAL_REGISTRY = "/run/media/drwho1985/Sandisk/data/beijing-lot/registry"
DEFAULT_REPO_UNIT_RELATIVE = "ops/systemd/user"
DEFAULT_STORE_STALE_DAYS = 30.0
DEFAULT_PLAN_STALE_DAYS = 45.0

# External-root children that are registries, not data stores.
NON_STORE_GROUPS = frozenset({"registry"})

_ERROR_CODES = {
    "missing_code_entry",
    "unit_code_missing",
    "collector_store_missing",
    "registry_store_missing",
    "retirement_without_archive",
    "registry_unreadable",
}


def _severity(code: str) -> str:
    return "error" if code in _ERROR_CODES else "warning"


def _finding(code: str, message: str, *, subject: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "severity": _severity(code), "subject": subject, "message": message, "evidence": evidence or {}}


def _age_days(mtime_iso: str | None, reference: datetime) -> float | None:
    if not mtime_iso:
        return None
    try:
        when = datetime.fromisoformat(mtime_iso)
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (reference - when).total_seconds() / 86400.0)


def _plan_age_days(updated_at: Any, reference: datetime) -> float | None:
    if not updated_at:
        return None
    try:
        when = date.fromisoformat(str(updated_at)[:10])
    except ValueError:
        return None
    return max(0.0, (reference.date() - when).days)


# --------------------------------------------------------------------------- #
# Store classification
# --------------------------------------------------------------------------- #

def _exact_retired_sibling(path: Path) -> str | None:
    """Return ``<name><marker>`` iff it exists and is an exact retirement name."""
    for marker in RETIRED_MARKERS:
        sibling = path.parent / f"{path.name}{marker}"
        if sibling.exists():
            return str(sibling)
    return None


def _collector_store(
    collector: dict[str, Any], *, repo_root: Path, reference: datetime, stale_days: float
) -> dict[str, Any] | None:
    database = collector.get("database")
    if not looks_like_path(database):
        return {"kind": "non-path", "value": database, "state": None, "findings": []}

    rel = str(database)
    info = read_store(Path(rel), base=repo_root)
    resolved = Path(info["resolved"])
    findings: list[dict[str, Any]] = []

    # A live file is never retired, even when a backup sits beside it.
    retired_marker = None
    if info["retired_name"]:
        retired_marker = resolved.name
    sibling = None if info["exists"] else _exact_retired_sibling(resolved)

    if retired_marker:
        state = RETIRED
        findings.append(_finding(
            "collector_store_retired",
            f"registered store {rel!r} carries a retirement marker",
            subject=collector["collector_id"], evidence={"store": info["resolved"]}))
    elif sibling:
        state = RETIRED
        findings.append(_finding(
            "collector_store_retired",
            f"registered store {rel!r} is absent and superseded by {Path(sibling).name!r}",
            subject=collector["collector_id"],
            evidence={"store": info["resolved"], "retired_sibling": sibling}))
    elif not info["exists"]:
        state = UNKNOWN
        findings.append(_finding(
            "collector_store_missing",
            f"registered store {rel!r} is absent from the working tree",
            subject=collector["collector_id"], evidence={"store": info["resolved"]}))
    else:
        age = _age_days(info["mtime_utc"], reference)
        state = RUNNING if (age is None or age <= stale_days) else ARCHIVED

    info.update({"kind": "sqlite", "relpath": rel, "state": state,
                 "retired_sibling": sibling, "retired_marker": retired_marker,
                 "findings": findings})
    return info


# --------------------------------------------------------------------------- #
# Unit inventory reconciliation
# --------------------------------------------------------------------------- #

def _resolve_code_path(
    raw: str, *, working_directory: str | None, home: str
) -> tuple[str, list[str]]:
    """Resolve a unit code path; returns ``(path, unsupported_specifiers)``.

    A non-empty specifier list means the base directory cannot be resolved from
    file evidence, so the caller must treat the path as unknown rather than
    prove its presence or absence.
    """
    expanded, unsupported = expand_unit_path(raw, home=home)
    unsupported = list(unsupported)
    candidate = Path(expanded)
    if candidate.is_absolute():
        return str(candidate), unsupported
    base = home
    if working_directory:
        base, base_unsupported = expand_unit_path(working_directory, home=home)
        unsupported.extend(base_unsupported)
    return str(Path(base) / expanded), sorted(set(unsupported))


def _reconcile_units(
    host_units: list[dict[str, Any]],
    repo_unit_names: set[str],
    *,
    repo_root: Path,
    home: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]], dict[str, list[str]]]:
    by_name = {unit["unit"]: unit for unit in host_units}
    # A timer starts its target service (explicit Unit= or same basename).
    for timer in host_units:
        if timer["unit_kind"] != "timer" or not timer.get("direct_scheduled"):
            continue
        # systemd activates only the explicit ``Unit=`` target; the same-basename
        # service is the default only when ``Unit=`` is absent.
        target = (timer.get("timer_unit") or "").strip()
        if target:
            candidates = [target if target.endswith(".service") else f"{target}.service"]
        else:
            candidates = [timer["unit"].replace(".timer", ".service")]
        for candidate in candidates:
            service = by_name.get(candidate)
            if service is not None:
                service["scheduled_by_timer"] = timer["unit"]

    entries: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    code_index: dict[str, list[str]] = {}
    basename_index: dict[str, list[str]] = {}
    for unit in host_units:
        resolved: list[str] = []
        missing: list[str] = []
        unsupported: list[str] = []
        for path in unit.get("code_paths") or []:
            candidate, path_unsupported = _resolve_code_path(
                path, working_directory=unit.get("working_directory"), home=home)
            if path_unsupported:
                unsupported.extend(path_unsupported)
                continue
            resolved.append(candidate)
            if os.path.exists(candidate):
                code_index.setdefault(os.path.realpath(candidate), []).append(unit["unit"])
            else:
                missing.append(path)
            basename_index.setdefault(Path(path).name, []).append(unit["unit"])

        scheduled = bool(unit.get("direct_scheduled") or unit.get("scheduled_by_timer"))
        if unsupported:
            state = UNKNOWN
            findings.append(_finding(
                "unit_path_unsupported",
                f"{unit['unit']} uses an unsupported systemd specifier",
                subject=unit["unit"], evidence={"specifiers": unsupported}))
        elif missing:
            state = UNKNOWN
            findings.append(_finding(
                "unit_code_missing",
                f"{unit['unit']} references code that is not present: {', '.join(missing)}",
                subject=unit["unit"], evidence={"missing": missing, "working_directory": unit.get("working_directory")}))
        else:
            state = RUNNING if scheduled else ARCHIVED

        if unit.get("dangling_wants"):
            findings.append(_finding(
                "dangling_wants_link",
                f"{unit['unit']} has a dangling want link (does not prove scheduling)",
                subject=unit["unit"], evidence={"dangling": unit["dangling_wants"]}))
        if unit["unit"] not in repo_unit_names:
            findings.append(_finding(
                "unit_not_in_repo",
                f"{unit['unit']} is defined on the host but not committed under {DEFAULT_REPO_UNIT_RELATIVE}",
                subject=unit["unit"], evidence={"unit_dir": unit.get("unit_dir")}))
        external = [p for p in (unit.get("code_paths") or []) if p.startswith("/") and not p.startswith(str(repo_root))]
        if external:
            findings.append(_finding(
                "unit_runs_external_code",
                f"{unit['unit']} runs code outside the repository checkout",
                subject=unit["unit"], evidence={"paths": sorted(set(external))}))

        entries.append({
            "kind": "unit",
            "id": unit["unit"],
            "unit_kind": unit["unit_kind"],
            "state": state,
            "scheduled": scheduled,
            "enabled_by": (unit.get("wants_links") or []),
            "scheduled_by_timer": unit.get("scheduled_by_timer"),
            "dangling_wants": unit.get("dangling_wants") or [],
            "linked_into_repo": bool(unit.get("linked")),
            "description": unit.get("description"),
            "unit_dir": unit.get("unit_dir"),
            "code_paths": unit.get("code_paths"),
            "resolved_code": resolved,
            "missing_code": missing,
            "unsupported_specifiers": unsupported,
            "in_repo_units": unit["unit"] in repo_unit_names,
        })
    return entries, findings, code_index, basename_index


def _classify_collector(
    collector: dict[str, Any],
    *,
    repo_root: Path,
    code_index: dict[str, list[str]],
    basename_index: dict[str, list[str]],
    unit_state: dict[str, str],
    reference: datetime,
    stale_days: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    collector_id = collector["collector_id"]
    code_path = collector["code_path"]
    resolved = (repo_root / code_path) if code_path else None
    code_exists = bool(resolved and resolved.exists())

    # Match by validated code identity: the unit must execute this exact file.
    matched: list[str] = []
    if code_exists:
        matched = sorted(set(code_index.get(os.path.realpath(resolved), [])))
    foreign = [u for u in basename_index.get(collector["code_name"], []) if u not in matched]

    scheduled_units = [u for u in matched if unit_state.get(u) == RUNNING]

    store_info = _collector_store(collector, repo_root=repo_root, reference=reference, stale_days=stale_days)
    if store_info:
        findings.extend(store_info.pop("findings"))
        store_info.pop("findings", None)

    if not code_exists:
        state = UNKNOWN
        evidence = ["code_entry not found in repository"]
        findings.append(_finding(
            "missing_code_entry",
            f"registered code entry {code_path!r} does not exist",
            subject=collector_id, evidence={"code_entry": collector["code_entry"]}))
    elif store_info and store_info.get("state") == RETIRED:
        state = RETIRED
        evidence = ["registered store has been retired"]
    elif scheduled_units:
        state = RUNNING
        evidence = [f"scheduled by {u}" for u in scheduled_units]
    else:
        state = ARCHIVED
        evidence = ["code present, no scheduled unit executes it"]

    if collector["enabled"] and state != RUNNING:
        findings.append(_finding(
            "plan_enabled_but_unscheduled",
            f"collector {collector_id} is enabled in the plan but is not scheduled",
            subject=collector_id, evidence={"state": state, "units": matched}))

    return (
        {
            "kind": "collector",
            "id": collector_id,
            "label": collector["label"],
            "state": state,
            "enabled_in_plan": collector["enabled"],
            "importance": collector["importance"],
            "owner_process": collector["owner_process"],
            "source": collector["source"],
            "code_entry": collector["code_entry"],
            "code_exists": code_exists,
            "units": matched,
            "foreign_units": foreign,
            "store": store_info,
            "evidence": evidence,
        },
        findings,
    )


# --------------------------------------------------------------------------- #
# External stores and registry reconciliation
# --------------------------------------------------------------------------- #

def _external_store_groups(external_root: Path | None) -> list[dict[str, Any]]:
    if external_root is None or not external_root.is_dir():
        return []
    groups: list[dict[str, Any]] = []
    for child in sorted(external_root.iterdir()):
        if not child.is_dir() or child.name in NON_STORE_GROUPS:
            continue
        try:
            entries = sum(1 for _ in child.iterdir())
        except OSError:
            entries = None
        groups.append({
            "kind": "external-store",
            "id": child.name,
            "state": AVAILABLE,
            "path": str(child),
            "entries": entries,
            "exists": True,
            "mtime_utc": read_store(child)["mtime_utc"],
        })
    return groups


def _registry_stores(
    registry_stores: list[dict[str, Any]], *, external_root: Path | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for declared in registry_stores:
        resolved = resolve_declared_path(declared["relpath"], base=external_root)
        info = read_store(resolved)
        state = AVAILABLE if info["exists"] else UNAVAILABLE
        entries.append({
            "kind": "registry-declared",
            "id": f"{declared['registry']}:{declared['key']}",
            "state": state,
            "path": info["resolved"],
            "registry": declared["registry"],
            "key": declared["key"],
            "exists": info["exists"],
            "bytes": info["bytes"],
            "mtime_utc": info["mtime_utc"],
        })
        if not info["exists"]:
            findings.append(_finding(
                "registry_store_missing",
                f"registry {declared['registry']!r} declares {declared['relpath']!r}, which is absent",
                subject=f"{declared['registry']}:{declared['key']}",
                evidence={"resolved": info["resolved"]}))
    return entries, findings


# --------------------------------------------------------------------------- #
# Evidence binding
# --------------------------------------------------------------------------- #

def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 16), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _canonical_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _unit_observations(unit_dirs: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Bounded observation of unit files and their wants links.

    Absolute paths preserve the wants-directory identity, so moving an
    unchanged link between target directories changes the digest.
    """
    observations: list[dict[str, Any]] = []
    for directory in unit_dirs:
        directory = Path(directory)
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if child.is_dir() and child.name.endswith(".target.wants"):
                for link in sorted(child.iterdir()):
                    observations.append({
                        "path": str(link), "kind": "want",
                        "target_exists": link.exists(),
                        "sha256": _sha256_file(link) if link.is_file() else None,
                    })
            elif child.suffix in (".service", ".timer"):
                observations.append({"path": str(child), "kind": child.suffix.lstrip("."),
                                     "sha256": _sha256_file(child)})
    return observations


def _dir_child_observations(root: Path | None) -> list[dict[str, Any]]:
    """Direct children of a directory with bounded metadata; no tree walk."""
    if root is None or not Path(root).is_dir():
        return []
    observations: list[dict[str, Any]] = []
    for child in sorted(Path(root).iterdir()):
        if child.is_dir():
            try:
                entries = sum(1 for _ in child.iterdir())
            except OSError:
                entries = None
            observations.append({"path": str(child), "kind": "dir", "entries": entries})
        else:
            try:
                observations.append({"path": str(child), "kind": "file", "bytes": child.stat().st_size})
            except OSError:
                observations.append({"path": str(child), "kind": "file", "bytes": None})
    return observations


def _build_evidence(
    *,
    plan_path: Path,
    host_unit_dirs: list[Path],
    repo_unit_dir: Path,
    registry: dict[str, Any],
    external_root: Path | None,
    store_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Digest a bounded observation manifest of the classification evidence."""
    registry_dir = registry.get("directory")
    registry_obs = []
    if registry_dir:
        for file in registry["files"]:
            registry_obs.append({
                "file": file["file"],
                "error": file.get("error"),
                "sha256": _sha256_file(Path(registry_dir) / file["file"]),
            })
    specs: list[tuple[str, str | None, str, Any]] = [
        ("plan", str(plan_path), "file", {"sha256": _sha256_file(plan_path)}),
        ("host_units", "; ".join(str(d) for d in host_unit_dirs), "units",
         _unit_observations(host_unit_dirs)),
        ("repo_units", str(repo_unit_dir), "units", _unit_observations([repo_unit_dir])),
        ("registry", registry_dir, "registry", registry_obs),
        ("external_data_root", str(external_root) if external_root else None, "children",
         _dir_child_observations(external_root)),
        ("collector_stores", None, "stores", [
            {"id": s["id"], "state": s["state"], "exists": s.get("exists"),
             "bytes": s.get("bytes"), "entries": s.get("entries"), "mtime_utc": s.get("mtime_utc")}
            for s in store_entries
        ]),
    ]
    return [
        {"input": name, "path": path, "kind": kind, "digest": _canonical_digest(payload)}
        for name, path, kind, payload in specs
    ]


def build_ledger(
    *,
    plan_path: Path,
    repo_root: Path,
    unit_dirs: Iterable[str | Path] = DEFAULT_HOST_UNIT_DIRS,
    registry_dir: str | Path | None = DEFAULT_EXTERNAL_REGISTRY,
    external_data_root: str | Path | None = DEFAULT_EXTERNAL_DATA_ROOT,
    repo_unit_relative: str = DEFAULT_REPO_UNIT_RELATIVE,
    generated_at: str | None = None,
    store_stale_days: float = DEFAULT_STORE_STALE_DAYS,
    plan_stale_days: float = DEFAULT_PLAN_STALE_DAYS,
) -> dict[str, Any]:
    """Build the master ledger and its drift findings from explicit inputs."""
    repo_root = Path(repo_root)
    generated = generated_at or utc_now()
    reference = datetime.fromisoformat(generated)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    home = home_directory()

    plan = read_repo_plan(Path(plan_path))
    findings: list[dict[str, Any]] = []

    # Host inventory only; repository definitions are read separately.
    expanded_dirs = [Path(d).expanduser() for d in unit_dirs]
    raw_host_units = read_systemd_units(expanded_dirs)
    host_units = [
        unit for unit in raw_host_units
        if is_collection_unit(unit, markers=(str(repo_root), str(Path.home() / ".local/lib"), str(Path.home() / ".codex/worktrees")))
    ]
    repo_units = read_repo_units(repo_root, repo_unit_relative)
    repo_unit_names = {u["unit"] for u in repo_units}

    unit_entries, unit_findings, code_index, basename_index = _reconcile_units(
        host_units, repo_unit_names, repo_root=repo_root, home=home)
    findings.extend(unit_findings)
    unit_state = {u["id"]: u["state"] for u in unit_entries}

    for directory in expanded_dirs:
        if not directory.is_dir():
            findings.append(_finding(
                "unit_dir_unavailable",
                f"requested unit directory {directory} is not present",
                subject=str(directory)))

    for repo_unit in repo_units:
        if repo_unit["unit"] not in {u["id"] for u in unit_entries}:
            findings.append(_finding(
                "repo_unit_not_scheduled",
                f"{repo_unit['unit']} is committed but not present on the host unit path",
                subject=repo_unit["unit"], evidence={"fragment": repo_unit.get("fragment")}))

    collectors: list[dict[str, Any]] = []
    for collector in plan["collectors"]:
        entry, problems = _classify_collector(
            collector, repo_root=repo_root, code_index=code_index, basename_index=basename_index,
            unit_state=unit_state, reference=reference, stale_days=store_stale_days)
        collectors.append(entry)
        findings.extend(problems)

    external_root = Path(external_data_root) if external_data_root else None
    if external_root is not None and not external_root.is_dir():
        findings.append(_finding(
            "external_data_root_unavailable",
            f"requested external data root {external_root} is not mounted or present",
            subject=str(external_root)))

    registry = read_external_registry(Path(registry_dir) if registry_dir else None)
    if registry_dir and not registry["available"]:
        findings.append(_finding(
            "external_registry_unavailable",
            f"requested registry directory {registry['directory']} is not present",
            subject=str(registry["directory"])))
    for file in registry["files"]:
        if file.get("error") == "unreadable":
            findings.append(_finding(
                "registry_unreadable",
                f"external registry file {file['file']!r} could not be parsed",
                subject=file["file"]))
        elif file.get("error") == "not-an-object":
            findings.append(_finding(
                "registry_unexpected_shape",
                f"external registry file {file['file']!r} is not a JSON object",
                subject=file["file"]))
    for item in registry["retired"]:
        if not (item.get("archive") and item.get("archive_sha256")):
            findings.append(_finding(
                "retirement_without_archive",
                f"retired source {item['source']!r} lacks a verifiable archive receipt",
                subject=item["source"], evidence={"registry": item.get("registry")}))

    store_entries = _external_store_groups(external_root)
    registry_store_entries, registry_store_findings = _registry_stores(
        registry["stores"], external_root=external_root)
    store_entries.extend(registry_store_entries)
    findings.extend(registry_store_findings)

    plan_age = _plan_age_days(plan.get("updated_at"), reference)
    if plan_age is not None and plan_age > plan_stale_days:
        findings.append(_finding(
            "plan_stale",
            f"collector plan updated_at is {plan_age:.0f} days old",
            subject=Path(plan_path).name,
            evidence={"updated_at": plan.get("updated_at"), "threshold_days": plan_stale_days}))

    retired_collectors = [c for c in collectors if (c.get("store") or {}).get("state") == RETIRED]
    if retired_collectors:
        findings.append(_finding(
            "plan_points_at_retired_store",
            "the collector plan still registers a store that has been retired",
            subject="data_collection_plan",
            evidence={"collectors": [c["id"] for c in retired_collectors]}))

    evidence = _build_evidence(
        plan_path=Path(plan_path),
        host_unit_dirs=expanded_dirs,
        repo_unit_dir=repo_root / repo_unit_relative,
        registry=registry,
        external_root=external_root,
        store_entries=store_entries,
    )

    inputs = {
        "plan": {"path": str(plan_path), "available": Path(plan_path).exists()},
        "repo_root": {"path": str(repo_root), "available": repo_root.is_dir()},
        "unit_dirs": [{"path": str(d), "available": d.is_dir()} for d in expanded_dirs],
        "registry_dir": {"path": registry["directory"], "available": registry["available"]},
        "external_data_root": {
            "path": str(external_root) if external_root else None,
            "available": bool(external_root and external_root.is_dir()),
        },
    }

    summary = {
        "collectors": len(collectors),
        "collectors_running": sum(1 for c in collectors if c["state"] == RUNNING),
        "units": len(unit_entries),
        "units_running": sum(1 for u in unit_entries if u["state"] == RUNNING),
        "units_not_in_repo": sum(1 for u in unit_entries if not u["in_repo_units"]),
        "stores": len(store_entries),
        "external_registries": len(registry["files"]),
        "retirements": len(registry["retired"]),
        "findings": len(findings),
        "errors": sum(1 for f in findings if f["severity"] == "error"),
        "warnings": sum(1 for f in findings if f["severity"] == "warning"),
        "inputs_unavailable": (
            sum(1 for key in ("plan", "repo_root", "registry_dir", "external_data_root")
                if inputs[key].get("available") is False)
            + sum(1 for unit in inputs["unit_dirs"] if unit.get("available") is False)
        ),
        "sources": {
            "plan": str(plan_path),
            "repo_root": str(repo_root),
            "unit_dirs": [str(d) for d in expanded_dirs],
            "repo_unit_relative": repo_unit_relative,
            "registry_dir": registry["directory"],
            "external_data_root": str(external_root) if external_root else None,
        },
    }

    return {
        "schema": LEDGER_SCHEMA,
        "generated_at": generated,
        "states": [RUNNING, ARCHIVED, RETIRED, UNKNOWN, AVAILABLE, UNAVAILABLE],
        "evidence": evidence,
        "plan": {
            "path": plan["path"],
            "schema_version": plan["schema_version"],
            "updated_at": plan["updated_at"],
            "age_days": plan_age,
        },
        "inputs": inputs,
        "objects": {
            "collectors": collectors,
            "units": unit_entries,
            "repo_units": [
                {"kind": "repo-unit", "id": u["unit"], "unit_kind": u["unit_kind"],
                 "description": u.get("description"), "code_paths": u.get("code_paths")}
                for u in repo_units
            ],
            "stores": store_entries,
            "registries": registry["files"],
            "retirements": registry["retired"],
        },
        "findings": findings,
        "summary": summary,
    }


# --------------------------------------------------------------------------- #
# Drift and rendering
# --------------------------------------------------------------------------- #

def _state_map(ledger: dict[str, Any]) -> dict[str, str]:
    states: dict[str, str] = {}
    for kind in ("collectors", "units", "stores"):
        for obj in ledger.get("objects", {}).get(kind, []):
            states[f"{kind[:-1]}:{obj['id']}"] = obj["state"]
    return states


def _finding_keys(ledger: dict[str, Any]) -> set[str]:
    return {f"{f['code']}|{f['subject']}" for f in ledger.get("findings", [])}


def diff_ledgers(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Drift between a previous ledger and the current one."""
    prev_states = _state_map(previous)
    curr_states = _state_map(current)
    transitions: list[dict[str, Any]] = []
    for key, state in curr_states.items():
        before = prev_states.get(key)
        if before is not None and before != state:
            transitions.append({"object": key, "from": before, "to": state})
    for key, state in prev_states.items():
        if key not in curr_states:
            transitions.append({"object": key, "from": state, "to": "absent"})
    transitions.sort(key=lambda item: item["object"])
    prev_findings = _finding_keys(previous)
    curr_findings = _finding_keys(current)
    return {
        "previous_generated_at": previous.get("generated_at"),
        "transition_count": len(transitions),
        "transitions": transitions,
        "new_findings": sorted(curr_findings - prev_findings),
        "resolved_findings": sorted(prev_findings - curr_findings),
    }


def render_text(ledger: dict[str, Any]) -> str:
    """Render a compact operator-facing summary of the ledger."""
    lines: list[str] = []
    summary = ledger["summary"]
    lines.append(f"collection ledger {ledger['schema']} @ {ledger['generated_at']}")
    lines.append(f"  plan: {ledger['plan']['path']} (updated_at={ledger['plan']['updated_at']})")
    lines.append(f"  unit dirs: {', '.join(summary['sources']['unit_dirs'])}")
    lines.append(f"  registry: {summary['sources']['registry_dir']}")
    for name, info in ledger["inputs"].items():
        if isinstance(info, dict) and info.get("available") is False:
            lines.append(f"  UNAVAILABLE INPUT: {name} -> {info.get('path')}")
    lines.append("")
    lines.append(f"collectors: {summary['collectors']} ({summary['collectors_running']} running)")
    for collector in ledger["objects"]["collectors"]:
        lines.append(f"  [{collector['state']:8}] {collector['id']:38} {collector['owner_process'] or ''}")
    lines.append(f"units: {summary['units']} ({summary['units_running']} running, {summary['units_not_in_repo']} not in repo)")
    for unit in ledger["objects"]["units"]:
        lines.append(f"  [{unit['state']:8}] {unit['id']}")
    lines.append(f"stores: {summary['stores']}  retirements: {summary['retirements']}")
    lines.append("")
    lines.append(f"findings: {summary['findings']} ({summary['errors']} error, {summary['warnings']} warning)")
    for finding in ledger["findings"]:
        lines.append(f"  {finding['severity'][:5].upper():5} {finding['code']:32} {finding['subject']}")
    return "\n".join(lines)
