"""Stage existing market inputs on persistent storage; never fetch or settle."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from pathlib import Path


def _copy_verified(source, destination, expected_sha256):
    """Copy exact bytes, or verify an existing identical destination; never overwrite."""
    source, destination = Path(source), Path(destination)
    with source.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected_sha256:
            raise ValueError(f"source hash mismatch: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_name(destination.name + f".{os.getpid()}.partial")
        shutil.copyfile(source, temporary)
        with temporary.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected_sha256:
                temporary.unlink()
                raise ValueError("copied bytes differ")
        temporary.rename(destination)
    with destination.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected_sha256:
            raise ValueError(f"destination hash mismatch: {destination}")


def _publish_json(path, value):
    """Atomically publish UTF-8 JSON; an interrupted stage remains unpublished."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.partial")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def stage_market_inputs(plan_path, index_path, data_root, *, mountpoint):
    """Stage plan, roster bytes and cached responses without changing their values.

    Inputs are existing collector plan/index JSON and an existing data root on
    the explicitly supplied mounted volume. Cached-response and inventory hashes
    are validated; roster bytes are copied unchanged. Missing upstream statuses
    remain absent and are listed in the receipt, preserving the collector's wait.
    Outputs are content-addressed files under markets/raw and shared/fixtures,
    plus an input bundle under markets/manifests/persistent-forward-v1.
    The returned receipt binds original inputs and new plan/index hashes.

    No requests, ledger updates, or source removal occur. Retrying interrupted
    staging verifies existing bytes. Failed staging may leave verified files, but a bundle is
    consumable only when its ready.json exists. A prior ready bundle must not be
    overwritten: use a new data root for a different migration snapshot.
    """
    root, mount = Path(data_root).resolve(strict=True), Path(mountpoint).resolve(strict=True)
    if not mount.is_mount() or not root.is_relative_to(mount):
        raise ValueError("data root must be on the supplied mounted volume")
    bundle = root / "markets/manifests/persistent-forward-v1"
    if (bundle / "ready.json").exists():
        raise FileExistsError("input bundle already published")
    plan_bytes, index_bytes = Path(plan_path).read_bytes(), Path(index_path).read_bytes()
    plan, index = json.loads(plan_bytes), json.loads(index_bytes)
    if plan.get("reused_issues"):
        raise ValueError("this relocation requires the active plan without reused issues")
    inventory_hash = plan["inventory_sha256"]
    if not isinstance(inventory_hash, str) or len(inventory_hash) != 64 or any(c not in "0123456789abcdef" for c in inventory_hash):
        raise ValueError("invalid inventory hash")
    inventory = root / "shared/fixtures" / (plan["inventory_sha256"] + ".json")
    _copy_verified(plan["inventory_path"], inventory, plan["inventory_sha256"])
    rosters = root / "shared/fixtures/persistent-forward-v1"
    mappings = {}
    pending_rosters = []
    for batch in plan["batches"]:
        for entry in batch:
            issue = entry["issue"]
            if not isinstance(issue, str) or not issue.isascii() or not issue.isdigit():
                raise ValueError("unsafe issue identifier")
            original_status = Path(plan["roster_root"]) / issue / "status.json"
            if not original_status.exists():
                if (rosters / issue / "status.json").exists():
                    raise ValueError("upstream roster disappeared during staging")
                pending_rosters.append(issue)
                continue
            status_bytes = original_status.read_bytes()
            status = json.loads(status_bytes)
            receipt = {"issue": issue, "processing_complete": status.get("processing_complete", False),
                       "roster_error": status.get("roster_error"),
                       "original_status_sha256": hashlib.sha256(status_bytes).hexdigest()}
            if status.get("roster_path"):
                source = Path(status["roster_path"])
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                target = root / "shared/fixtures" / (digest + ".json")
                _copy_verified(source, target, digest)
                mappings[str(source)] = str(target)
                receipt["roster_path"] = str(target)
            _publish_json(rosters / issue / "status.json", receipt)
    result_index = copy.deepcopy(index)
    for cached in result_index.values():
        for item in [*cached["attempts"], cached["selected"]]:
            original = item["path"]
            digest = item["sha256"]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("invalid response hash")
            target = root / "markets/raw/verified-responses" / (digest + ".json")
            if original not in mappings:
                _copy_verified(original, target, digest)
                mappings[original] = str(target)
            elif mappings[original] != str(target):
                raise ValueError("inconsistent source identity")
            item["path"] = str(target)
    plan["inventory_path"], plan["roster_root"] = str(inventory), str(rosters)
    _publish_json(bundle / "plan.json", plan)
    _publish_json(bundle / "existing-captures.json", result_index)
    _publish_json(bundle / "path-map.json", mappings)
    receipt = {"schema": "beijing_lot_market_input_relocation_v1",
               "original_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
               "original_index_sha256": hashlib.sha256(index_bytes).hexdigest(),
               "plan_sha256": hashlib.sha256((bundle / "plan.json").read_bytes()).hexdigest(),
               "index_sha256": hashlib.sha256((bundle / "existing-captures.json").read_bytes()).hexdigest(),
               "cache_keys": len(index), "pending_roster_issues": pending_rosters,
               "state": "STAGED_NOT_ACTIVATED", "historical_admission": False}
    _publish_json(bundle / "ready.json", receipt)
    return receipt
