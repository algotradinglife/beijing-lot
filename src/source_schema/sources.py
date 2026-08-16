"""Issue #234 — source hash verification (REQ-DS07).

The census captures raw-content hashes for every accepted upstream package
and raw asset.  The verifier recomputes those hashes from the live tree and
fails closed when the recorded receipt does not match (tamper detection:
rewriting a manifest or a raw source changes its hash and the package verify
must FAIL — REQ-E06).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import contract
from . import publication

HASH_ALGORITHM = "sha256"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def code_hash(root: Path) -> str:
    """Hash the frozen package source (all .py under src/source_schema)."""
    package_dir = root / "src" / "source_schema"
    if not package_dir.exists():
        return ""
    digest = hashlib.sha256()
    for path in sorted(package_dir.rglob("*.py")):
        digest.update(path.relative_to(package_dir).as_posix().encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def notebook_hash(root: Path) -> str:
    """Semantic source-cell hash: notebook code cells only, stable across runs.

    Cell execution inserts output/execution-count metadata; hashing only the
    source text of code cells keeps the recorded hash stable and still binds
    the exact reviewed notebook (same semantic cells -> same hash).
    """
    import json as json_mod

    path = root / contract.NOTEBOOK_DIR / contract.NOTEBOOK_NAME
    if not path.exists():
        return ""
    notebook = json_mod.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        digest.update(source.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def requirements_hash(root: Path) -> str:
    path = root / contract.REQUIREMENTS_HASH_SOURCE
    if not path.exists():
        return ""
    return sha256_file(path)


def verify_package_hashes(package: Path) -> dict[str, str]:
    """Recompute every file hash under ``package`` and compare SHA256SUMS.json.

    Returns {relative_path: sha256} for matching files.  Raises on any
    mismatch or missing entry so the verifier fails closed on tamper.
    """
    sums_path = package / "SHA256SUMS.json"
    if not sums_path.exists():
        raise FileNotFoundError(f"missing SHA256SUMS.json in {package}")
    recorded = json.loads(sums_path.read_text(encoding="utf-8"))
    mismatches: list[str] = []
    checked: dict[str, str] = {}
    for relative, expected in recorded.items():
        path = package / relative
        if not path.exists():
            mismatches.append(f"{relative}: MISSING")
            continue
        actual = sha256_file(path)
        checked[relative] = actual
        if actual != expected:
            mismatches.append(f"{relative}: hash mismatch")
    # Files present but not recorded are also tamper evidence.
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.json":
            continue
        relative = path.relative_to(package).as_posix()
        if relative not in recorded:
            mismatches.append(f"{relative}: UNRECORDED")
    if mismatches:
        raise AssertionError(
            "package tamper detected:\n" + "\n".join(mismatches)
        )
    return checked


def write_sha256sums(package: Path) -> Path:
    sums: dict[str, str] = {}
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            sums[path.relative_to(package).as_posix()] = sha256_file(path)
    target = package / "SHA256SUMS.json"
    publication.atomic_write_json(target, sums)
    return target
