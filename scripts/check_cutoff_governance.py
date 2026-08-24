#!/usr/bin/env python3
"""Reject hidden chronology and unregistered historical fitting repository-wide."""

from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "config/cutoff_governance_legacy_allowlist.json"
BANNED_GLOBALS = {"FIT_END", "TUNE_YEAR", "CALIBRATION_YEAR"}
DUPLICATE_TEMPORAL_FUNCTIONS = {
    "compute_recency_weights",
    "derive_temporal_partitions",
    "mapping_cache_key",
    "temporal_cache_key",
    "walk_forward_fit",
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _function_calls_shared_context(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    return any(
        isinstance(child, ast.Call)
        and (
            isinstance(child.func, ast.Name)
            and child.func.id == "prepare_learning_context"
            or isinstance(child.func, ast.Attribute)
            and child.func.attr == "prepare_learning_context"
        )
        for child in ast.walk(node)
    )


def _occurrence(
    *, rule: str, path: str, scope: str, symbol: str, node: ast.AST, source: str
) -> dict[str, Any]:
    node_identity = (ast.get_source_segment(source, node) or symbol).strip()
    fingerprint = _digest("|".join([rule, path, scope, symbol, node_identity]))
    return {
        "fingerprint": fingerprint,
        "rule": rule,
        "path": path,
        "scope": scope,
        "symbol": symbol,
        "line": int(getattr(node, "lineno", 0)),
    }


class _OccurrenceVisitor(ast.NodeVisitor):
    def __init__(self, relative: str, source: str) -> None:
        self.relative = relative
        self.source = source
        self.scope: list[str] = []
        self.temporal_client_depth = 0
        self.occurrences: list[dict[str, Any]] = []
        self.hard_violations: list[str] = []

    @property
    def scope_name(self) -> str:
        return ".".join(self.scope) or "<module>"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name in DUPLICATE_TEMPORAL_FUNCTIONS and not self.relative.startswith(
            "src/temporal_learning/"
        ):
            self.hard_violations.append(
                f"{self.relative}:{node.lineno}: duplicated temporal utility {node.name}"
            )
        decorated = any(
            _decorator_name(value) == "temporal_client" for value in node.decorator_list
        )
        if decorated and not _function_calls_shared_context(node):
            self.hard_violations.append(
                f"{self.relative}:{node.lineno}: temporal_client does not call shared context"
            )
        self.scope.append(node.name)
        previous = self.temporal_client_depth
        if decorated:
            self.temporal_client_depth += 1
        self.generic_visit(node)
        self.temporal_client_depth = previous
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in BANNED_GLOBALS:
                self.occurrences.append(
                    _occurrence(
                        rule="hidden_temporal_global",
                        path=self.relative,
                        scope=self.scope_name,
                        symbol=target.id,
                        node=node,
                        source=self.source,
                    )
                )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        target = node.target
        if isinstance(target, ast.Name) and target.id in BANNED_GLOBALS:
            self.occurrences.append(
                _occurrence(
                    rule="hidden_temporal_global",
                    path=self.relative,
                    scope=self.scope_name,
                    symbol=target.id,
                    node=node,
                    source=self.source,
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"fit", "fit_transform"}
            and self.temporal_client_depth == 0
        ):
            self.occurrences.append(
                _occurrence(
                    rule="direct_historical_fit",
                    path=self.relative,
                    scope=self.scope_name,
                    symbol=node.func.attr,
                    node=node,
                    source=self.source,
                )
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "mapping_accepted" and not self.relative.startswith(
            "src/cutoff_mapping/"
        ):
            self.occurrences.append(
                _occurrence(
                    rule="detached_mapping_accepted",
                    path=self.relative,
                    scope=self.scope_name,
                    symbol=node.id,
                    node=node,
                    source=self.source,
                )
            )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "mapping_accepted" and not self.relative.startswith(
            "src/cutoff_mapping/"
        ):
            self.occurrences.append(
                _occurrence(
                    rule="detached_mapping_accepted",
                    path=self.relative,
                    scope=self.scope_name,
                    symbol=node.attr,
                    node=node,
                    source=self.source,
                )
            )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if node.value == "mapping_accepted" and not self.relative.startswith(
            "src/cutoff_mapping/"
        ):
            self.occurrences.append(
                _occurrence(
                    rule="detached_mapping_accepted",
                    path=self.relative,
                    scope=self.scope_name,
                    symbol="mapping_accepted",
                    node=node,
                    source=self.source,
                )
            )


def collect_occurrences(root: Path = ROOT) -> tuple[list[dict[str, Any]], list[str]]:
    occurrences: list[dict[str, Any]] = []
    hard: list[str] = []
    for directory in (root / "src", root / "scripts"):
        for path in sorted(directory.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative)
            except (SyntaxError, UnicodeDecodeError) as error:
                hard.append(f"{relative}: cannot parse for cutoff governance: {error}")
                continue
            visitor = _OccurrenceVisitor(relative, source)
            visitor.visit(tree)
            occurrences.extend(visitor.occurrences)
            hard.extend(visitor.hard_violations)
    return occurrences, hard


def baseline_payload(root: Path = ROOT) -> dict[str, Any]:
    occurrences, hard = collect_occurrences(root)
    if hard:
        raise ValueError("cannot baseline hard violations: " + "; ".join(hard))
    grouped: dict[str, dict[str, Any]] = {}
    counts = Counter(item["fingerprint"] for item in occurrences)
    for item in occurrences:
        grouped.setdefault(
            item["fingerprint"],
            {
                key: item[key]
                for key in ("fingerprint", "rule", "path", "scope", "symbol")
            },
        )["count"] = counts[item["fingerprint"]]
    return {
        "schema_version": 2,
        "description": "Exact AST occurrence baseline for historical-only code; no whole-file exemption.",
        "legacy_occurrences": sorted(
            grouped.values(),
            key=lambda row: (
                row["path"],
                row["rule"],
                row["scope"],
                row["fingerprint"],
            ),
        ),
    }


def violations(root: Path = ROOT) -> list[str]:
    config_path = root / "config/cutoff_governance_legacy_allowlist.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 2 or not isinstance(
        config.get("legacy_occurrences"), list
    ):
        return [
            "config/cutoff_governance_legacy_allowlist.json: occurrence baseline v2 required"
        ]
    current, found = collect_occurrences(root)
    current_counts = Counter(item["fingerprint"] for item in current)
    baseline_rows = {item["fingerprint"]: item for item in config["legacy_occurrences"]}
    baseline_counts = Counter(
        {key: int(value["count"]) for key, value in baseline_rows.items()}
    )
    for item in current:
        expected = baseline_counts[item["fingerprint"]]
        if expected == 0:
            found.append(
                f"{item['path']}:{item['line']}: new {item['rule']} in {item['scope']} ({item['symbol']})"
            )
    for fingerprint in sorted(set(current_counts) | set(baseline_counts)):
        actual, expected = current_counts[fingerprint], baseline_counts[fingerprint]
        if actual != expected:
            row = baseline_rows.get(fingerprint)
            if row is not None:
                found.append(
                    f"{row['path']}: legacy {row['rule']} occurrence count {actual} != baseline {expected}"
                )
    inventory = root / "docs/research/temporal-function-inventory.csv"
    if not inventory.is_file():
        found.append("docs/research/temporal-function-inventory.csv: missing")
    else:
        header = inventory.read_text(encoding="utf-8").splitlines()[0].split(",")
        required = {
            "path",
            "function",
            "learned_operation",
            "cutoff_interface",
            "status",
            "source_or_label_max",
            "receipt_replay",
            "migration_priority",
        }
        if not required.issubset(header):
            found.append("temporal-function inventory lacks required columns")
        if "src/temporal_learning/core.py" not in inventory.read_text(encoding="utf-8"):
            found.append("temporal-function inventory lacks shared core")
    return sorted(set(found))


def main() -> None:
    found = violations()
    if found:
        raise SystemExit("cutoff governance violations:\n- " + "\n- ".join(found))
    print("cutoff governance: PASS")


if __name__ == "__main__":
    main()
