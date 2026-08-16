"""Immutable package publication for the BJ #234 source-schema contract.

Follows the #229/#203/#214 package discipline: a results directory written
atomically (temp dir + rename), MANIFEST.json + SHA256SUMS.json binding
every machine-readable artifact and the source hashes (REQ-DS07), and a
deterministic replay path.

Fault-injection rule (class 6): publication must preserve the previous
package if a write fails mid-way.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from . import contract
from .schemas import render_ddl, render_ddl_sha256


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk_files(package_dir: Path) -> list[Path]:
    return sorted(p for p in package_dir.rglob("*") if p.is_file())


def build_sha256sums(package_dir: Path) -> dict[str, str]:
    return {str(p.relative_to(package_dir)): sha256_file(p)
            for p in walk_files(package_dir)}


def manifest_for(package_dir: Path, *, code_hash: str, notebook_hash: str,
                 profile: dict, source_hashes: dict, raw_hashes: dict,
                 environment: dict, producer_commit_sha: str,
                 contract_version: str = "",
                 audit_mode: str = "candidate",
                 disposition: str = "FROZEN_CONTRACT",
                 built_at_utc: Optional[str] = None) -> dict:
    import datetime

    if built_at_utc is None:
        built_at_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if not contract_version:
        contract_version = f"{contract.CONTRACT_VERSION}/{contract.CONTRACT_REVISION}"
    sums = build_sha256sums(package_dir)
    return {
        "contract_version": contract_version,
        "audit_mode": audit_mode,
        "disposition": disposition,
        "built_at_utc": built_at_utc,
        "producer_commit_sha": producer_commit_sha,
        "code_hash": code_hash,
        "notebook_hash": notebook_hash,
        "notebook_hash_mode": "semantic_source_cells_v1",
        "environment": environment,
        "ddl_sha256": render_ddl_sha256(),
        "schema_sha256": hashlib.sha256(
            json.dumps(_schema_bundle(), sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "source_hashes": source_hashes,
        "raw_archive_hashes": raw_hashes,
        "profile_summary": _profile_summary(profile),
        "sha256sums": sums,
    }


def _schema_bundle() -> dict:
    """The schema artifacts that schema_sha256 commits to."""
    from .schemas import all_arrow_schemas_json, domain_dictionary

    return {
        "ddl": render_ddl(),
        "arrow_schemas": all_arrow_schemas_json(),
        "domain_dictionary": domain_dictionary(),
        "identity_rule": {"unique_within": "issue_code x match_idx"},
    }


def _profile_summary(profile: dict) -> dict:
    out = {}
    for db, info in profile.items():
        if not info.get("present"):
            out[db] = {"present": False}
            continue
        out[db] = {
            "size_mb": info.get("size_mb"),
            "journal_mode": info.get("journal_mode"),
            "tables": [t["name"] for t in info.get("tables", [])],
            "identity_dup": info.get("identity_dup"),
        }
    return out


def write_package(package_dir: Path, *, files: dict[str, str | bytes],
                  profile: dict, source_hashes: dict, raw_hashes: dict,
                  code_hash: str, notebook_hash: str, environment: dict,
                  producer_commit_sha: str, keep_previous: bool = True) -> Path:
    """Atomically write a package: temp dir → fsync → rename over target.

    ``files`` maps relative path → str/bytes content (JSON/CSV/MD rendered by
    the builder).  SHA256SUMS.json and MANIFEST.json are generated inside the
    temp dir so the manifest's own sha256sums reflect final content.
    """
    package_dir = Path(package_dir)
    parent = package_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{package_dir.name}.tmp-", dir=str(parent)))
    try:
        for rel, content in files.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                p.write_text(content, encoding="utf-8")
            else:
                p.write_bytes(content)
        sums = build_sha256sums(tmp)
        (tmp / "SHA256SUMS.json").write_text(
            json.dumps(sums, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        manifest = manifest_for(tmp, code_hash=code_hash, notebook_hash=notebook_hash,
                                profile=profile, source_hashes=source_hashes,
                                raw_hashes=raw_hashes, environment=environment,
                                producer_commit_sha=producer_commit_sha)
        # Recompute sums including SHA256SUMS.json itself for full binding.
        sums2 = build_sha256sums(tmp)
        (tmp / "SHA256SUMS.json").write_text(
            json.dumps(sums2, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        manifest["sha256sums"] = build_sha256sums(tmp)
        (tmp / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")

        # fsync the temp tree before rename (atomic durable publish).
        for p in walk_files(tmp):
            with open(p, "rb") as f:
                os.fsync(f.fileno())
        dirfd = os.open(tmp, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)

        if keep_previous and package_dir.exists():
            backup = package_dir.with_name(package_dir.name + ".prev")
            if backup.exists():
                shutil.rmtree(backup)
            package_dir.rename(backup)
        if package_dir.exists():
            shutil.rmtree(package_dir)
        tmp.rename(package_dir)
        # fsync parent dir so the rename is durable
        pfd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(pfd)
        finally:
            os.close(pfd)
        return package_dir
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def verify_package(package_dir: Path, *, require_manifest: bool = True) -> dict:
    """Verify a published package: census + hashes + manifest consistency.

    Returns a verdict dict; raises AssertionError on mismatch.
    """
    package_dir = Path(package_dir)
    assert package_dir.exists(), f"package missing: {package_dir}"
    files = walk_files(package_dir)
    sums_now = build_sha256sums(package_dir)
    if require_manifest:
        mpath = package_dir / "MANIFEST.json"
        assert mpath.exists(), "MANIFEST.json missing"
        manifest = json.loads(mpath.read_text())
        assert manifest.get("contract_version", "").startswith(
            contract.CONTRACT_VERSION), "contract version mismatch"
        recorded = manifest.get("sha256sums", {})
        # MANIFEST.json is self-referential by design (cannot contain its own
        # hash before being written); SHA256SUMS.json and all artifacts are bound.
        mismatch = {k: (recorded.get(k), sums_now.get(k))
                    for k in sorted(set(recorded) | set(sums_now))
                    if k != "MANIFEST.json" and recorded.get(k) != sums_now.get(k)}
        assert not mismatch, f"sha256 mismatch: {mismatch}"
        ddl = render_ddl()
        ddl_sha = sha256_bytes(ddl.encode("utf-8"))
        assert manifest.get("ddl_sha256") == ddl_sha, "ddl_sha256 mismatch"
        # Bound source hashes must match the referenced immutable packages
        # (REQ-DS07: bind to reviewed hashes, not mutable working files).
        recorded_src = manifest.get("source_hashes", {})
        for rel, h in recorded_src.items():
            if h is None:
                continue
            p = package_dir.parent.parent / rel
            assert p.exists(), f"bound source hash target missing: {rel}"
            assert sha256_file(p) == h, f"bound source hash mismatch: {rel}"
        # MANIFEST.json itself must be consistent with its own recorded sums
        # SHA256SUMS.json is self-referential too (cannot contain its final
        # hash before being written); MANIFEST.json binds it instead.
        sums_file = package_dir / "SHA256SUMS.json"
        recorded_sums = json.loads(sums_file.read_text())
        for rel, h in recorded_sums.items():
            if rel == "SHA256SUMS.json":
                continue
            p = package_dir / rel
            assert p.exists(), f"sha256sums entry missing: {rel}"
            assert sha256_file(p) == h, f"sha256sums mismatch: {rel}"
    return {
        "package": str(package_dir),
        "files": len(files),
        "verified": True,
        "ddl_sha256": render_ddl_sha256(),
    }
