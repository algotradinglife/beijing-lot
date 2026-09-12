"""Assemble exactly one verified five-play batch per frozen plan slice."""
from datetime import datetime
import json
from pathlib import Path

from src.nowscore_history_capture import verify_history_batch, verify_history_manifest
from src.nowscore_history_plan import validate_history_capture_plan
from src.nowscore_issue_inventory import _write_raw, canonical, digest


def assemble_history_batches(plan: dict, inventory: dict, roots: list[Path],
                             output: Path, *, generated_at: str) -> dict:
    """Create a new source-pure capture bundle accepted by the storage API.

    Replays all batches before writing. Preserves all attempt bodies including
    controls and failed attempts, plus original manifests/logs. Data captures
    exclude controls. Duplicate, missing, stale or unresolved inputs fail closed.
    Paths are operational inputs only and never enter content identities.
    """
    validate_history_capture_plan(plan, inventory)
    generated = datetime.fromisoformat(generated_at)
    if generated.tzinfo is None:
        raise ValueError("assembly generation time requires timezone")
    if output.exists():
        raise FileExistsError(output)
    verified = {}
    for root in roots:
        manifest = verify_history_batch(plan, inventory, root)
        batch_id = manifest["batch"]["batch_id"]
        if batch_id in verified:
            raise ValueError("duplicate batch identity")
        if generated < datetime.fromisoformat(manifest["sealed_at"]):
            raise ValueError("assembly precedes sealed batch")
        manifest_bytes = (root / "manifest.json").read_bytes()
        if json.loads(manifest_bytes) != manifest:
            raise ValueError("batch changed during verification")
        log_bytes = (root / "capture_log.jsonl").read_bytes()
        verified[batch_id] = (root, manifest, manifest_bytes, log_bytes)
    if set(verified) != {batch["batch_id"] for batch in plan["batches"]}:
        raise ValueError("batch set does not completely cover five-play plan")
    output.mkdir(parents=True, exist_ok=False)
    (output / "raw").mkdir()
    captures, receipts = [], {}
    for batch in plan["batches"]:
        batch_id = batch["batch_id"]
        root, manifest, manifest_bytes, log_bytes = verified[batch_id]
        evidence = output / "evidence" / batch_id
        evidence.mkdir(parents=True)
        (evidence / "manifest.json").write_bytes(manifest_bytes)
        (evidence / "capture_log.jsonl").write_bytes(log_bytes)
        for row in manifest["controls"] + manifest["captures"]:
            for attempt in row["attempts"]:
                if "sha256" in attempt:
                    body = (root / "raw" / f"{attempt['sha256']}.html").read_bytes()
                    if digest(body) != attempt["sha256"]:
                        raise ValueError("raw input changed during assembly")
                    _write_raw(output / "raw", body)
        captures.extend(manifest["captures"])
        receipts[batch_id] = {"manifest_sha256": digest(manifest_bytes),
                              "event_log_sha256": digest(log_bytes)}
    result = {"schema": "nowscore_history_capture_v1", "source": "nowscore",
              "requested_issues": inventory["issues"], "captures": captures,
              "scope": "complete five-play task domain of bound source inventory",
              "generated_at": generated_at, "history_plan": plan,
              "history_inventory": inventory, "batch_receipts": receipts,
              "five_play_task_coverage_complete": True,
              "historical_coverage_claimed": False, "production_enabled": False}
    with (output / "manifest.json").open("x", encoding="utf-8") as handle:
        handle.write(canonical(result) + "\n")
    return result


def verify_assembled_history(root: Path, manifest: dict) -> None:
    """Verify a full capture bundle before database writes, including controls.

    Reconciles the complete data ledger against original batch manifests and
    replays all source bytes. Missing logs, changed bodies and incomplete domains
    raise; no writes or network. Coverage flags alone are never sufficient.
    """
    if (manifest.get("schema") != "nowscore_history_capture_v1"
            or manifest.get("source") != "nowscore"
            or manifest.get("five_play_task_coverage_complete") is not True
            or manifest.get("production_enabled") is not False):
        raise ValueError("invalid full-history bundle")
    plan, inventory = manifest["history_plan"], manifest["history_inventory"]
    validate_history_capture_plan(plan, inventory)
    receipts = manifest.get("batch_receipts", {})
    if set(receipts) != {batch["batch_id"] for batch in plan["batches"]}:
        raise ValueError("assembled batch set incomplete")
    generated = datetime.fromisoformat(manifest["generated_at"])
    if generated.tzinfo is None:
        raise ValueError("assembly time lacks timezone")
    captures = []
    for batch in plan["batches"]:
        batch_id = batch["batch_id"]
        evidence = root / "evidence" / batch_id
        body = (evidence / "manifest.json").read_bytes()
        log = (evidence / "capture_log.jsonl").read_bytes()
        if (digest(body) != receipts[batch_id].get("manifest_sha256")
                or digest(log) != receipts[batch_id].get("event_log_sha256")):
            raise ValueError("assembled batch evidence hash mismatch")
        original = verify_history_manifest(plan, inventory, json.loads(body), root)
        if "replay_origin" in original and log != original["replay_origin"]["log_text"].encode():
            raise ValueError("assembled replay event log differs from origin")
        if original["batch"] != batch or generated < datetime.fromisoformat(original["sealed_at"]):
            raise ValueError("assembled batch identity or chronology mismatch")
        captures.extend(original["captures"])
    if captures != manifest.get("captures") or inventory["issues"] != manifest.get("requested_issues"):
        raise ValueError("assembled capture ledger differs from verified evidence")
