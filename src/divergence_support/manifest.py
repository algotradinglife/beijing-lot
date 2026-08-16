"""Issue #232 — manifest / SHA256SUMS / replay (self-contained, R2 fresh).

R1 re-exported the #229 resolver, so ``verify`` with no ``--package``
resolved the #229 package and REPLAY.md hard-coded the #229 build workflow
(EV E3).  R2 implements the resolver here: the default package is the #232
package; the replay instructions reference the #232 build/notebook scripts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_sha256sums(package: Path) -> Path:
    """Write SHA256SUMS.json mapping relative paths under package -> sha256."""
    mapping: dict[str, str] = {}
    for path in sorted(package.rglob("*")):
        if path.is_file():
            relative = str(path.relative_to(package))
            mapping[relative] = sha256_file(path)
    target = package / "SHA256SUMS.json"
    target.write_text(
        json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def resolve_package(root: Path, package: str | Path | None) -> Path:
    """Resolve the #232 immutable results package (default: #232 package)."""
    if package is None:
        return root / "results" / "bj232_divergence_support_v2"
    candidate = Path(package)
    if candidate.is_absolute():
        return candidate
    return root / "results" / candidate


def write_replay(package: Path, *, build_script: str, notebook_script: str) -> Path:
    """Write REPLAY.md referencing the #232 build/notebook scripts."""
    content = f"""# Deterministic replay — {package.name}

Run from the repository root with the pinned existing environment.

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/{build_script} verify \
  --package {package.name}

PYTHONPATH=src $PY scripts/{build_script} build \
  --force

PYTHONPATH=src $PY scripts/{notebook_script}
```

The build reads only the four accepted upstream frozen packages plus
allow-listed columns from #203 inference feature values.  No
settlement/result table is opened.  Deterministic loading is
fail-closed: every upstream package is SHA256-verified before use.
"""
    target = package / "REPLAY.md"
    target.write_text(content, encoding="utf-8")
    return target
