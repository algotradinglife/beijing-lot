"""Transitive implementation-closure hashing for shared learning receipts.

#388: receipt-bind the actual decision-facing imported-module closure,
including contract/constants modules. Any mutation of an imported blob must
invalidate replay because the closure hash feeds the cache key and the
implementation receipt.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .core import TemporalContractError, stable_json_hash

_REPO_ROOTS = ("src", "scripts")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _module_to_file(module: str) -> str:
    return module.replace(".", "/") + ".py"


def _module_to_paths(module: str) -> tuple[str, str]:
    """Candidate paths for a module: module.py then package __init__.py."""
    direct = module.replace(".", "/") + ".py"
    package_init = module.replace(".", "/") + "/__init__.py"
    return direct, package_init


def _resolve_import(
    module: str,
    node: ast.AST,
    current: str,
) -> str | None:
    """Resolve an import node to an absolute repo module, or None external."""
    level = getattr(node, "level", 0)
    name = getattr(node, "module", None)
    if level == 0 and name:
        candidate = name
    elif level > 0:
        base_parts = current.split(".")
        if level > len(base_parts):
            return None
        base = base_parts[: len(base_parts) - (level - 1)]
        candidate = ".".join(base + ([name] if name else []))
    else:
        return None
    if candidate.split(".")[0] not in _REPO_ROOTS:
        return None
    return candidate


def _relative_parent(current: str, level: int) -> str:
    parts = current.split(".")
    if level - 1 >= len(parts):
        return current
    return ".".join(parts[: len(parts) - (level - 1)])


def _imported_modules(tree: ast.AST, current: str) -> set[str]:
    """Collect repo-internal module names from a syntax tree.

    Handles absolute `src.x`/`scripts.x` imports and relative imports
    (`from . import core`, `from .sub import x`).
    """
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                candidate = _resolve_import(alias.name, node, current)
                if candidate:
                    modules.add(candidate)
        elif isinstance(node, ast.ImportFrom):
            base = _relative_parent(current, node.level) if node.level else current
            name = node.module or ""
            if node.level == 0:
                candidate = name
            else:
                candidate = ".".join(filter(None, [base, name]))
            if candidate.split(".")[0] in _REPO_ROOTS:
                modules.add(candidate)
            if node.level > 0:
                # `from . import x` binds x as a submodule; keep the parent too
                parent = ".".join(filter(None, [base]))
                if parent.split(".")[0] in _REPO_ROOTS and parent:
                    modules.add(parent)
                for alias in node.names:
                    if alias.name != "*":
                        modules.add(".".join(filter(None, [base, alias.name])))
    return modules


def _entry_module_names(paths: Iterable[Path], root: Path) -> set[str]:
    names: set[str] = set()
    for path in paths:
        path = path.resolve()
        try:
            relative = path.relative_to(root.resolve())
        except ValueError:
            raise TemporalContractError(f"closure entry {path} is outside repo root {root}")
        parts = list(relative.parts)
        if parts and parts[0] in _REPO_ROOTS and parts[-1].endswith(".py"):
            names.add(".".join(parts[:-1] + [parts[-1][: -len(".py")]]))
        else:
            raise TemporalContractError(f"closure entry must be a repo python file: {path}")
    return names


@dataclass(frozen=True)
class ImplementationClosure:
    """Immutable map of decision-facing imported module blob hashes."""

    entries: Mapping[str, str]
    modules: Mapping[str, str]

    def receipt(self) -> dict[str, dict[str, str]]:
        return {
            "entries": dict(sorted(self.entries.items())),
            "modules": dict(sorted(self.modules.items())),
        }

    def hash(self) -> str:
        return stable_json_hash(self.receipt())


def implementation_closure(
    root: Path,
    entries: Iterable[Path],
    *,
    follow_relative: bool = True,
) -> ImplementationClosure:
    """Compute the transitive repo-internal import closure of entry files.

    `entries` are decision-facing python files (e.g. a client module plus its
    contract/constants). The closure includes every repo module reachable
    through absolute `src.*`/`scripts.*` imports and relative imports.
    """
    root = root.resolve()
    entry_names = _entry_module_names(entries, root)
    pending = list(entry_names)
    visited: set[str] = set()
    module_hashes: dict[str, str] = {}
    file_cache: dict[str, tuple[str, set[str]]] = {}

    def load(module: str) -> tuple[str, set[str]]:
        cached = file_cache.get(module)
        if cached is not None:
            return cached
        direct, package_init = _module_to_paths(module)
        path = root / direct
        if not path.is_file():
            candidate = root / package_init
            if not candidate.is_file():
                raise TemporalContractError(f"closure module missing on disk: {module}")
            path = candidate
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path.relative_to(root)))
        imports = _imported_modules(tree, module)
        file_cache[module] = (source, imports)
        return file_cache[module]

    while pending:
        module = pending.pop(0)
        if module in visited:
            continue
        visited.add(module)
        source, imports = load(module)
        module_hashes[module] = _sha256_bytes(source.encode("utf-8"))
        for imported in imports:
            if imported in visited or imported in pending:
                continue
            try:
                load(imported)
            except TemporalContractError:
                if not follow_relative:
                    raise
                # Non-repo external modules (stdlib/site-packages) are not part
                # of the repository closure; they are pinned by environment
                # policy, not by an immutable blob here.
                continue
            pending.append(imported)
    entries_map = {name: module_hashes[name] for name in sorted(entry_names)}
    return ImplementationClosure(entries_map, dict(sorted(module_hashes.items())))


def closure_receipt(
    closure: ImplementationClosure,
    *,
    extra: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the receipt-bound implementation snapshot for a closure."""
    payload: dict[str, dict[str, str]] = closure.receipt()
    if extra:
        payload["extra"] = dict(sorted(extra.items()))
    return payload