"""Repository-local transitive implementation provenance for temporal clients."""

from __future__ import annotations

import ast
import hashlib
from importlib import metadata
from pathlib import Path
from typing import Iterable

from .core import TemporalContractError, stable_json_hash


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _module_path(repo_root: Path, module: str) -> tuple[Path, bool] | None:
    relative = Path(*module.split("."))
    source = repo_root / relative.with_suffix(".py")
    if source.is_file():
        return source, False
    package = repo_root / relative / "__init__.py"
    if package.is_file():
        return package, True
    return None


def _resolve_from(
    module: str, is_package: bool, level: int, imported: str | None
) -> str:
    package = module if is_package else module.rsplit(".", 1)[0]
    parts = package.split(".")
    if level > 1:
        parts = parts[: -(level - 1)]
    if imported:
        parts.extend(imported.split("."))
    return ".".join(parts)


def _local_imports(
    repo_root: Path, module: str, path: Path, is_package: bool
) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        candidates: list[str] = []
        if isinstance(node, ast.Import):
            candidates.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_from(module, is_package, node.level, node.module)
                if node.level
                else (node.module or "")
            )
            if base:
                candidates.append(base)
                for alias in node.names:
                    candidates.append(f"{base}.{alias.name}")
        for candidate in candidates:
            if candidate.startswith(("src.", "scripts.")) and _module_path(
                repo_root, candidate
            ):
                imports.add(candidate)
    return imports


def implementation_closure(
    repo_root: Path,
    root_modules: Iterable[str],
    *,
    distributions: Iterable[str] = (),
) -> dict[str, object]:
    """Hash the exact repository-local import closure of decision-facing clients."""

    repo_root = repo_root.resolve()
    pending = list(dict.fromkeys(str(value) for value in root_modules))
    if not pending:
        raise TemporalContractError("implementation provenance requires root modules")
    visited: set[str] = set()
    files: dict[str, str] = {}
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        resolved = _module_path(repo_root, module)
        if resolved is None:
            raise TemporalContractError(
                f"local implementation module is missing: {module}"
            )
        visited.add(module)
        path, is_package = resolved
        relative = path.relative_to(repo_root).as_posix()
        files[relative] = _sha256(path)
        pending.extend(
            sorted(_local_imports(repo_root, module, path, is_package) - visited)
        )
    versions: dict[str, str] = {}
    for distribution in sorted(set(distributions)):
        try:
            versions[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError as error:
            raise TemporalContractError(
                f"implementation distribution is unavailable: {distribution}"
            ) from error
    payload: dict[str, object] = {
        "root_modules": sorted(set(root_modules)),
        "files": dict(sorted(files.items())),
        "distributions": versions,
    }
    payload["closure_sha256"] = stable_json_hash(payload)
    return payload


def verify_implementation_closure(repo_root: Path, receipt: dict[str, object]) -> None:
    expected = implementation_closure(
        repo_root,
        receipt.get("root_modules", []),
        distributions=receipt.get("distributions", {}).keys(),
    )
    if expected != receipt:
        raise TemporalContractError("transitive implementation closure differs")


def verify_callable_binding(repo_root: Path, receipt: dict[str, object], callback,
                            *, expected_identity: str) -> dict[str, object]:
    """Bind a module-level callback to executing source, not its claimed name.

    Requires the loaded module and globals to originate at the explicit root,
    and compares code objects to freshly compiled frozen files without executing
    those files. Directly referenced local Python functions are checked likewise.
    This is an accidental cross-checkout/monkeypatch guard, not a hostile-Python
    sandbox. Returns a deterministic identity ledger; raises on any mismatch.
    """
    import inspect
    import sys
    import types

    root = Path(repo_root).resolve()
    if not inspect.isfunction(callback):
        raise TemporalContractError('callback must be a Python function')
    identity = f'{callback.__module__}:{callback.__qualname__}'
    if identity != expected_identity or '<locals>' in callback.__qualname__:
        raise TemporalContractError('callback qualified identity differs')
    pending = [callback]; checked = {}; compiled = {}
    while pending:
        function = pending.pop()
        name = f'{function.__module__}:{function.__qualname__}'
        if name in checked:
            if checked[name] is not function:
                raise TemporalContractError('multiple executing callback implementations')
            continue
        module = sys.modules.get(function.__module__)
        resolved = _module_path(root, function.__module__)
        if module is None or resolved is None:
            raise TemporalContractError('callback module is not bound')
        path = resolved[0].resolve(); relative = path.relative_to(root).as_posix()
        if (relative not in receipt['files'] or _sha256(path) != receipt['files'][relative]
                or not getattr(module, '__file__', None) or Path(module.__file__).resolve() != path
                or function.__globals__ is not vars(module)
                or Path(function.__code__.co_filename).resolve() != path):
            raise TemporalContractError('executing callback source differs from frozen root')
        if relative not in compiled:
            code = compile(path.read_bytes(), str(path), 'exec', dont_inherit=True, optimize=sys.flags.optimize)
            codes = {}; stack = [code]
            while stack:
                node = stack.pop(); codes[node.co_qualname] = node
                stack.extend(c for c in node.co_consts if isinstance(c, types.CodeType))
            compiled[relative] = codes
        if compiled[relative].get(function.__qualname__) != function.__code__:
            raise TemporalContractError('executing callback code differs from frozen source')
        checked[name] = function
        for symbol in function.__code__.co_names:
            other = function.__globals__.get(symbol)
            if inspect.isfunction(other) and _module_path(root, other.__module__) is not None:
                pending.append(other)
    return dict(identity=identity, executing_functions=sorted(checked))
