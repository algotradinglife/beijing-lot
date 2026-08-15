"""Manifest, SHA256SUMS and replay receipt for the immutable package.

Rework (2026-08-15, class-5 sweep): ``write_replay`` now embeds the exact
reviewed commit / code / notebook hashes so "clean replay binds the exact
reviewed SHA" (REQ-D09).  The verify command resolves the package name
relative to ``results/`` so the documented replay command works from the repo
root (the audited REPLAY.md used a bare name that failed outside the build
worktree).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from . import contract
from . import sources


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256sums(package: Path) -> Path:
    """Write SHA256SUMS.json covering every file under ``package``."""
    sums: dict[str, str] = {}
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            sums[path.relative_to(package).as_posix()] = sha256_file(path)
    target = package / "SHA256SUMS.json"
    target.write_text(
        json.dumps(sums, indent=2, sort_keys=True), encoding="utf-8"
    )
    return target


def resolve_package(root: Path, package: str | Path | None) -> Path:
    """Resolve a package name or path relative to ``root/results``.

    Accepts ``results/bj229_divergence_profile_v1``, the bare package name
    ``bj229_divergence_profile_v1``, or an absolute Path.  This fixes the
    audited verify command which used a bare name and failed from the repo
    root.
    """
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


def write_replay(package: Path, receipt, root: Path, manifest: dict | None = None) -> Path:
    """Write REPLAY.md with exact replay commands + reviewed-SHA binding."""
    payload = manifest or json.loads((package / "MANIFEST.json").read_text())
    reviewed = payload.get("reviewed_commit_sha", "unknown")
    code_hash = payload.get("code_hash", "unknown")
    notebook_hash = payload.get("notebook_hash", "unknown")
    lines = [
        "# Deterministic replay — " + package.name,
        "",
        "Run from the repository root with the pinned existing environment.",
        "",
        "```bash",
        "PY=.venv/bin/python",
        f"PYTHONPATH=src $PY scripts/build_bj229_divergence_profile.py verify \\",
        f"  --package {package.name}",
        "",
        "PYTHONPATH=src $PY scripts/build_bj229_divergence_profile.py build \\",
        "  --force",
        "",
        "PYTHONPATH=src $PY scripts/execute_bj229_notebook.py",
        "```",
        "",
        "The build reads only the four accepted upstream frozen packages plus",
        "allow-listed columns from #203 inference feature values.  No",
        "settlement/result table is opened.  Deterministic loading is",
        "fail-closed: every upstream package is SHA256-verified before use.",
        "",
        "## Reviewed-SHA binding (REQ-D09)",
        "",
        f"- reviewed_commit_sha: `{reviewed}`",
        f"- code_hash (src/divergence_profile): `{code_hash}`",
        f"- notebook_hash: `{notebook_hash}`",
        f"- requirements_hash: `{payload.get('requirements_hash', 'unknown')}`",
        "",
        "## Upstream source hashes (recorded at build)",
        "",
        "```json",
        json.dumps(receipt.source_hashes, indent=2, sort_keys=True),
        "```",
        "",
        "## Environment identity",
        "",
        "```json",
        json.dumps(payload.get("environment", {}), indent=2, sort_keys=True),
        "```",
        "",
        f"Built at {datetime.now(timezone.utc).isoformat()}.",
        "",
    ]
    target = package / "REPLAY.md"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
