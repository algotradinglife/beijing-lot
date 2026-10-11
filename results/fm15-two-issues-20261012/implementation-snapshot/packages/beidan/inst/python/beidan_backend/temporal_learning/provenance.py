"""Repository-local transitive implementation provenance for temporal clients."""

from __future__ import annotations

import ast
import hashlib
from importlib import metadata
from pathlib import Path
from typing import Iterable
from types import MappingProxyType

from .core import TemporalContractError, stable_json_hash


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# Capture this installed/source backend once at import. A receipt may describe a
# relocated identical copy, but never a different checkout or a file changed
# after this process imported its implementation.
_LOADED_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_LOADED_BACKEND_HASHES = MappingProxyType({
    path.relative_to(_LOADED_BACKEND_ROOT).as_posix(): _sha256(path)
    for path in _LOADED_BACKEND_ROOT.rglob("*.py")
})


def _module_path(repo_root: Path, module: str) -> tuple[Path, bool] | None:
    relative = Path(*module.split("."))
    if module == "beidan_backend" or module.startswith("beidan_backend."):
        bundle = Path("packages/beidan/inst/python")
        # The caller declares either a repository root or installed Python root.
        # Never resolve through the active interpreter or another checkout.
        if (repo_root / bundle / "beidan_backend").is_dir():
            relative = bundle / relative
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
            if candidate.startswith(("src.", "scripts.", "beidan_backend.")) and _module_path(
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
        # Importing a submodule executes each regular parent package initializer.
        # Bind those files too, including imports performed by the initializers.
        parts = module.split(".")
        for index in range(1, len(parts)):
            parent = ".".join(parts[:index])
            parent_path = _module_path(repo_root, parent)
            if parent_path is not None and parent_path[1] and parent not in visited:
                pending.append(parent)
        path, is_package = resolved
        if module == "beidan_backend" or module.startswith("beidan_backend."):
            suffix = Path(*module.split(".")[1:])
            suffix = suffix / "__init__.py" if is_package else suffix.with_suffix(".py")
            expected = _LOADED_BACKEND_HASHES.get(suffix.as_posix())
            loaded_path = _LOADED_BACKEND_ROOT / suffix
            if (expected is None or not loaded_path.is_file()
                    or _sha256(path) != expected or _sha256(loaded_path) != expected):
                raise TemporalContractError(
                    f"loaded backend implementation differs from declared root: {module}"
                )
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
