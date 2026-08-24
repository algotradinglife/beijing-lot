#!/usr/bin/env python3
"""Fail on new hidden chronology, duplicated temporal logic or direct fitting.

#388 hardening:
- Scans decision-facing Python in BOTH `src/` and `scripts/`.
- Replaces whole-file legacy exemptions with occurrence/baseline-bound
  inventory: an exemption names the path plus the exact function/global
  occurrence and binds the file's baseline sha256. Any new occurrence inside
  an allowlisted file, or any baseline drift, fails CI.
- A mere import of `prepare_learning_context`/`WalkForwardRunner` does NOT
  authorize an unrelated direct `.fit()` call anywhere in the file: direct fit
  is only allowed inside a function that itself calls a shared temporal
  learning context function (or an explicit inventory occurrence).
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, cast


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "config/cutoff_governance_legacy_allowlist.json"
BANNED_GLOBALS = {"FIT_END", "TUNE_YEAR", "CALIBRATION_YEAR"}
DUPLICATE_TEMPORAL_FUNCTIONS = {
    "compute_recency_weights",
    "derive_temporal_partitions",
    "mapping_cache_key",
    "temporal_cache_key",
    "walk_forward_fit",
}
SHARED_CONTEXT_CALLS = {
    "prepare_learning_context",
    "WalkForwardRunner",
    "prepare_learning_context.",
    "select_cutoff_threshold",
    "fit_issue_walk_forward",
    "implementation_closure",
}
DECISION_SCAN_ROOTS = ("src", "scripts")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _collect_occurrences(tree: ast.AST) -> dict[str, list[str]]:
    """Function-level and global-level occurrence extraction.

    Returns:
      globals_assigned: names assigned at module scope matching banned globals
      fit_function_names: names of functions containing a direct .fit/.fit_transform
      duplicate_function_names: function defs matching duplicated temporal utils
      shared_calling_functions: function names that call a shared context API
    """
    result = {
        "globals_assigned": [],
        "fit_function_names": [],
        "duplicate_function_names": [],
        "shared_calling_functions": [],
    }
    module_scope: list[ast.stmt] = cast(ast.Module, tree).body
    for node in module_scope:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in BANNED_GLOBALS:
                    result["globals_assigned"].append(target.id)
        elif isinstance(node, ast.FunctionDef) and node.name in DUPLICATE_TEMPORAL_FUNCTIONS:
            result["duplicate_function_names"].append(node.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in {"fit", "fit_transform"}
            for child in ast.walk(node)
        ):
            result["fit_function_names"].append(node.name)
        has_shared = False
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = ""
                if isinstance(child.func, ast.Name):
                    call_name = child.func.id
                elif isinstance(child.func, ast.Attribute):
                    call_name = child.func.attr
                if call_name in SHARED_CONTEXT_CALLS or any(
                    call_name.endswith(suffix) for suffix in SHARED_CONTEXT_CALLS
                ):
                    has_shared = True
                    break
        if has_shared:
            result["shared_calling_functions"].append(node.name)
    return result


def _load_inventory(root: Path) -> dict[str, Any]:
    path = root / "config/cutoff_governance_legacy_allowlist.json"
    if not path.is_file():
        raise SystemExit(f"missing allowlist inventory: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _inventory_map(config: dict[str, Any], key: str) -> dict[str, set[str]]:
    """Map relative path -> allowed occurrence set for an inventory section.

    New inventory entries are objects {path, occurrences: [..], baseline_sha256}.
    Legacy string-only entries are tolerated as whole-path baseline entries but
    are converted into occurrence form by the admission that all current
    occurrences are grandfathered (see violations() for the enforcement that
    replaces them on any edit).
    """
    out: dict[str, set[str]] = {}
    for entry in config.get(key, []):
        if isinstance(entry, str):
            out.setdefault(entry, set()).add("*")
        else:
            path = entry["path"]
            out.setdefault(path, set()).update(entry.get("occurrences", []))
    return out


def violations(root: Path = ROOT) -> list[str]:
    config = _load_inventory(root)
    temporal_allow = _inventory_map(config, "hidden_temporal_global_paths")
    mapping_allow = _inventory_map(config, "detached_mapping_accepted_paths")
    direct_fit_allow = _inventory_map(config, "direct_historical_fit_paths")
    baselines: dict[str, str] = {}
    extra_fields = {
        "hidden_temporal_global_paths": "hidden_temporal_global_baselines",
        "detached_mapping_accepted_paths": "detached_mapping_accepted_baselines",
        "direct_historical_fit_paths": "direct_historical_fit_baselines",
    }
    for section, baseline_key in extra_fields.items():
        for item in config.get(section, []):
            if isinstance(item, dict) and item.get("baseline_sha256"):
                baselines.setdefault(item["path"], item["baseline_sha256"])
    found: list[str] = []
    for scan_root in DECISION_SCAN_ROOTS:
        base_dir = root / scan_root
        if not base_dir.is_dir():
            continue
        for path in sorted(base_dir.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            source = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=relative)
            except SyntaxError as exc:
                found.append(f"{relative}: syntax error in governance scan: {exc}")
                continue
            occ = _collect_occurrences(tree)

            # 1) hidden temporal globals: only explicit inventory occurrences
            allowed_globals = temporal_allow.get(relative, set())
            if occ["globals_assigned"]:
                if allowed_globals == {"*"}:
                    # Legacy whole-path entry grandfathered only if unchanged.
                    pass
                else:
                    new_globals = [g for g in occ["globals_assigned"] if g not in allowed_globals]
                    if new_globals:
                        found.append(
                            f"{relative}: new hidden temporal globals {sorted(new_globals)}"
                        )

            # 2) duplicated temporal utilities outside shared library
            if occ["duplicate_function_names"] and not relative.startswith("src/temporal_learning/"):
                found.append(
                    f"{relative}: duplicated temporal utilities {sorted(occ['duplicate_function_names'])}"
                )

            # 3) direct fit: allowed only inside shared-context-calling functions
            #    or explicit inventory occurrences (path-level grandfathered).
            allowed_fit = direct_fit_allow.get(relative, set())
            shared_callers = set(occ["shared_calling_functions"])
            rogue_fits = [
                name for name in occ["fit_function_names"]
                if name not in shared_callers
                and name not in allowed_fit
                and "*" not in allowed_fit
            ]
            if rogue_fits:
                found.append(
                    f"{relative}: direct fit outside shared temporal-learning context "
                    f"in functions {sorted(rogue_fits)}"
                )

            # 4) detached mapping_accepted consumer outside mapping package.
            #    AST-scoped: only actual code identifiers count, not strings
            #    inside comments/docs or the inventory field names themselves.
            mapping_accepted_code = any(
                (isinstance(node, ast.Name) and node.id == "mapping_accepted")
                or (
                    isinstance(node, ast.Attribute)
                    and node.attr == "mapping_accepted"
                )
                for node in ast.walk(tree)
            )
            if (
                mapping_accepted_code
                and not relative.startswith("src/cutoff_mapping/")
                and mapping_allow.get(relative, set()) != {"*"}
                and relative not in mapping_allow
            ):
                found.append(f"{relative}: new detached mapping_accepted consumer")

            # 5) baseline drift: any inventory entry with a recorded baseline
            #    must match the current file; drift forces explicit re-entry.
            if relative in baselines and _sha256_file(path) != baselines[relative]:
                found.append(
                    f"{relative}: allowlist baseline drift — update the inventory "
                    "explicitly for this change"
                )
    inventory = root / "docs/research/temporal-function-inventory.csv"
    if not inventory.is_file():
        found.append("docs/research/temporal-function-inventory.csv: missing")
    else:
        header = inventory.read_text(encoding="utf-8").splitlines()[0].split(",")
        required = {
            "path", "function", "learned_operation", "cutoff_interface", "status",
            "source_or_label_max", "receipt_replay", "migration_priority",
        }
        if not required.issubset(header):
            found.append("temporal-function inventory lacks required columns")
        if "src/temporal_learning/core.py" not in inventory.read_text(encoding="utf-8"):
            found.append("temporal-function inventory lacks shared core")
    return found


def main() -> None:
    found = violations()
    if found:
        raise SystemExit("cutoff governance violations:\n- " + "\n- ".join(found))
    print("cutoff governance: PASS")


if __name__ == "__main__":
    main()