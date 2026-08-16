"""Issue #232 — package hash verification (wraps census fail-closed loader)."""

from __future__ import annotations

from pathlib import Path

from .census import _verify_manifest


def verify_package_hashes(package: Path) -> dict[str, str]:
    """Verify every file listed in the package SHA256SUMS.json (fail-closed)."""
    return _verify_manifest(package)
