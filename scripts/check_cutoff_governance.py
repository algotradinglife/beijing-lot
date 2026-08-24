#!/usr/bin/env python3
"""Fail on new hidden chronology, duplicated temporal logic or direct fitting."""

from __future__ import annotations

import ast
import json
from pathlib import Path


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


def _assigned_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def violations(root: Path = ROOT) -> list[str]:
    config = json.loads((root / "config/cutoff_governance_legacy_allowlist.json").read_text())
    temporal_allow = set(config["hidden_temporal_global_paths"])
    mapping_allow = set(config["detached_mapping_accepted_paths"])
    direct_fit_allow = set(config["direct_historical_fit_paths"])
    found: list[str] = []
    for path in sorted((root / "src").rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        hidden = _assigned_names(tree) & BANNED_GLOBALS
        if hidden and relative not in temporal_allow:
            found.append(f"{relative}: hidden temporal globals {sorted(hidden)}")
        duplicate_names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        } & DUPLICATE_TEMPORAL_FUNCTIONS
        if duplicate_names and not relative.startswith("src/temporal_learning/"):
            found.append(f"{relative}: duplicated temporal utilities {sorted(duplicate_names)}")
        direct_fit = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"fit", "fit_transform"}
            for node in ast.walk(tree)
        )
        shared_client = (
            "prepare_learning_context" in source
            or "WalkForwardRunner" in source
        )
        if direct_fit and relative not in direct_fit_allow and not shared_client:
            found.append(f"{relative}: direct fit without shared temporal-learning context")
        if (
            "mapping_accepted" in source
            and not relative.startswith("src/cutoff_mapping/")
            and relative not in mapping_allow
        ):
            found.append(f"{relative}: new detached mapping_accepted consumer")
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
