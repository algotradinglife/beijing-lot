"""Issue #234 — manifest helpers and package resolution."""

from __future__ import annotations

import json
from pathlib import Path

from . import contract


def resolve_package(root: Path, package: str | Path | None) -> Path:
    """Resolve a package name or path relative to ``root/results``."""
    if package is None:
        return contract.package_path(root)
    if isinstance(package, Path):
        candidate = package
    else:
        candidate = Path(str(package))
    if candidate.is_absolute():
        return candidate
    if (root / candidate).exists():
        return root / candidate
    return root / "results" / candidate


def read_manifest(package: Path) -> dict:
    return json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
