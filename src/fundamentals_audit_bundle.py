"""Publish hash-bound fundamentals audit evidence using the NAS version lifecycle."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import shutil
import uuid

from filelock import FileLock
from beidan_backend.catalog.paths import root_path
from beidan_backend.issue_schedule.contract import validate_issue_id
from beidan_backend import versioning


def publish_fundamentals_audit(files, *, issue, label, receipt, environ):
    """Publish one immutable audit bundle; never mutate its input or base data.

    files maps relative POSIX member names to {path, sha256}; all inputs must be
    regular files with the explicitly supplied SHA256. receipt is a JSON object
    binding input identities and limitations (no implicit clock). Explicit catalog
    roots must exist. Returns the shared version result and verified manifest hash.
    Fails on unsafe names, absent/changed bytes, unavailable roots or label reuse
    with different content. Same bytes/receipt are a no-op. Writes only under
    frozen:reports/<issue>-fundamentals-final, serialized with a file lock.
    """
    validate_issue_id(issue)
    frozen = root_path("frozen", environ=environ)
    root_path("hot", environ=environ)
    if not isinstance(files, dict) or not files or not isinstance(receipt, dict):
        raise ValueError("nonempty file inventory and receipt object required")
    inventory = {}
    for name, item in files.items():
        if (not isinstance(name, str) or not name or "\\" in name
                or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                or str(PurePosixPath(name)) != name
                or name in {"asset-manifest.json", "version.json", "inventory.sha256"}):
            raise ValueError("unsafe or reserved bundle member")
        path = Path(item["path"])
        if not path.is_file() or versioning.sha256_file(path) != item["sha256"]:
            raise ValueError("bundle input hash mismatch: " + name)
        inventory[name] = dict(path=path, sha256=item["sha256"])
    # Names such as a and a/b cannot both be files in one bundle.
    for name in inventory:
        if any(str(parent) in inventory for parent in PurePosixPath(name).parents):
            raise ValueError("bundle file/directory collision")
    base = frozen / "reports" / (issue + "-fundamentals-final")
    base.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(json.dumps(dict(schema="beidan_fundamentals_audit_bundle_v1",
        issue=issue,members={name:item["sha256"] for name,item in sorted(inventory.items())},
        receipt=receipt),ensure_ascii=False,allow_nan=False))
    identity = (hashlib.sha256(json.dumps(manifest, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()+"\n").encode()

    def write(directory):
        for name, item in sorted(inventory.items()):
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".copying")
            shutil.copyfile(item["path"], temporary)
            if versioning.sha256_file(temporary) != item["sha256"]:
                raise ValueError("bundle input changed during copying: " + name)
            os.replace(temporary, target)
        # Shared versioning deliberately excludes JSON metadata from identity.
        # Here JSON can itself be raw evidence: bind every member and the exact
        # explicit receipt through a nonvolatile content file.
        temporary=directory/"inventory.sha256.partial"
        temporary.write_bytes(identity)
        if temporary.read_bytes()!=identity:
            raise ValueError("written bundle identity failed verification")
        os.replace(temporary,directory/"inventory.sha256")
        versioning.write_json_atomically(manifest, directory / "asset-manifest.json")
        _verify_bundle(directory,manifest,identity)
        return dict(files=len(inventory), asset_manifest_sha256=versioning.sha256_file(
            directory / "asset-manifest.json"))

    with FileLock(base / "publication.lock", timeout=30):
        directory = versioning.version_directory(base, label)
        existing=directory.exists()
        if existing:
            _verify_bundle(directory,manifest,identity)
            prior_record=json.loads((directory/"version.json").read_text())
            if versioning.sha256_file(directory/"asset-manifest.json")!=prior_record["asset_manifest_sha256"]:
                raise versioning.VersionError("published bundle manifest hash mismatch")
        previous=versioning.read_current(base)
        try:
            result = versioning.publish_version(base, label, write)
            _verify_bundle(directory,manifest,identity)
            manifest_sha256 = versioning.sha256_file(directory / "asset-manifest.json")
            if manifest_sha256 != result["record"]["asset_manifest_sha256"]:
                raise versioning.VersionError("published bundle manifest mismatch")
        except Exception:
            if previous is None:
                (base/"current.json").unlink(missing_ok=True)
            else:
                versioning.write_json_atomically(previous,base/"current.json")
            if not existing and directory.exists():
                os.replace(directory,base/(".failed-"+label+"-"+uuid.uuid4().hex))
            raise
    return dict(publication=result, relative=str(directory.relative_to(frozen)),
                asset_manifest_sha256=manifest_sha256, verified_members=len(inventory))


def _verify_bundle(directory, manifest, identity):
    """Verify all bound bytes and the exact member set, before pointer changes."""
    if json.loads((directory/"asset-manifest.json").read_text())!=manifest:
        raise versioning.VersionError("different content: published bundle manifest mismatch")
    if (directory/"inventory.sha256").read_bytes()!=identity:
        raise versioning.VersionError("published bundle identity mismatch")
    for name,sha256 in manifest["members"].items():
        if versioning.sha256_file(directory/name)!=sha256:
            raise versioning.VersionError("different content: published bundle member mismatch")
    actual={str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}
    expected=set(manifest["members"])|{"asset-manifest.json","inventory.sha256"}
    if actual-{"version.json"}!=expected:
        raise versioning.VersionError("published bundle member inventory mismatch")
