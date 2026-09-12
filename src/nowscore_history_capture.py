"""Immutable five-play batches with immediate evidence and offline replay."""
from datetime import datetime, timezone
from functools import partial
import http.client
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

from src.nowscore_history_plan import validate_history_capture_plan
from src.nowscore_issue_inventory import (
    _write_raw, canonical, digest, rate_limited_transport, urllib_transport,
)
from src.nowscore_settlement import RosterConflict, parse_page, source_url


def classify_play(payload: bytes, issue: str, typeid: int) -> dict:
    """Validate a play page and return reproducible parsed identity and row count.

    Zero bytes or an identity-valid page without rows is source_empty, not a
    transport/parser failure. A contradictory embedded/visible roster is an
    explicit quarantined page, never an empty or usable observation. A data
    control must nevertheless be present. Other parser failures still raise.
    """
    source_url(issue, typeid)
    try:
        rows = parse_page(payload, issue, typeid) if payload else []
    except RosterConflict as error:
        return {"classification": "quarantined", "match_count": 0,
                "parsed_sha256": digest(canonical([]).encode()),
                "quarantine_reason": error.args[0], "quarantine_detail": error.args[1]}
    return {"classification": "present" if rows else "source_empty",
            "match_count": len(rows), "parsed_sha256": digest(canonical(rows).encode())}


def append_event(path: Path, event: dict) -> None:
    """Append one JSON event and fsync; persistence errors propagate."""
    with path.open("a", encoding="utf-8") as log:
        log.write(canonical(event) + "\n")
        log.flush()
        os.fsync(log.fileno())


def fetch_play(request: dict, *, role: str, root: Path, timeout: float,
               max_attempts: int, interval: float, transport, now, sleep) -> dict:
    """Fetch one task with bounded retries, persisting responses before parsing.

    Explicit injectable network/clock callbacks enable offline failure tests.
    Raises after exhaustion; all received bytes and failure events remain.
    """
    attempts = []
    for number in range(1, max_attempts + 1):
        if number > 1:
            sleep(interval)
        attempt = {"attempt": number}
        payload = None
        try:
            response = transport(request["url"], timeout)
            if (type(response["status"]) is not int
                    or not isinstance(response["final_url"], str)
                    or not isinstance(response["payload"], bytes)):
                raise ValueError("transport contract mismatch")
            payload = response["payload"]
            attempt.update(status=response["status"], final_url=response["final_url"])
        except (OSError, http.client.HTTPException, KeyError, TypeError, ValueError) as error:
            attempt["error"] = f"{type(error).__name__}: {error}"
            if isinstance(error, http.client.IncompleteRead):
                payload = error.partial
                attempt["partial"] = True
        attempt["received_at"] = now().isoformat()
        if payload is not None:
            attempt.update(sha256=_write_raw(root / "raw", payload), byte_count=len(payload))
            append_event(root / "capture_log.jsonl",
                         {**request, "role": role, "event": "response", **attempt})
        parsed = None
        if "error" not in attempt:
            if attempt.get("status") != 200 or attempt.get("final_url") != request["url"]:
                attempt["error"] = "unexpected HTTP status or redirect"
            else:
                try:
                    parsed = classify_play(payload, request["issue"], request["typeid"])
                except (ValueError, UnicodeError) as error:
                    attempt["error"] = f"{type(error).__name__}: {error}"
        append_event(root / "capture_log.jsonl",
                     {**request, "role": role, "event": "attempt", **attempt})
        attempts.append(attempt)
        if "error" not in attempt:
            return {**request, **parsed, "received_at": attempt["received_at"],
                    "sha256": attempt["sha256"], "attempts": attempts}
    raise ValueError("play request exhausted retries; batch remains unsealed")


def capture_history_batch(plan: dict, inventory: dict, batch_id: str, root: Path, *,
                          timeout: float = 40, max_attempts: int = 3,
                          transport=urllib_transport, sleep=time.sleep,
                          now=lambda: datetime.now(timezone.utc)) -> dict:
    """Capture one new plan-bound directory; failures never seal a manifest.

    Uses the same host/user lock as inventory discovery for real HTTP calls.
    Each batch has before/after SPF controls; empty data pages remain explicit.
    """
    validate_history_capture_plan(plan, inventory)
    if not math.isfinite(timeout) or timeout <= 0 or type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("invalid timeout or retry limit")
    started = now()
    if started.tzinfo is None or datetime.fromisoformat(plan["generated_at"]) > started:
        raise ValueError("capture cannot precede plan")
    batches = [row for row in plan["batches"] if row["batch_id"] == batch_id]
    if len(batches) != 1:
        raise ValueError("batch identity missing or duplicated")
    root.mkdir(parents=True, exist_ok=False)
    (root / "raw").mkdir()
    interval = plan["interval_seconds"]
    if transport is urllib_transport:
        transport = partial(rate_limited_transport,
                            lock_path=Path(tempfile.gettempdir()) / f"nowscore-inventory-{os.getuid()}.lock",
                            interval=interval)
    control = {"issue": plan["control_issue"], "typeid": 5, "url": plan["control_url"]}
    tasks = [("pre_control", control)] + [("data", r) for r in batches[0]["requests"]] + [("post_control", control)]
    captures, controls = [], []
    for index, (role, request) in enumerate(tasks):
        if index:
            sleep(interval)
        row = fetch_play(request, role=role, root=root, timeout=timeout,
                         max_attempts=max_attempts, interval=interval,
                         transport=transport, now=now, sleep=sleep)
        if role != "data":
            if row["classification"] != "present":
                raise ValueError("source control empty; batch remains unsealed")
            controls.append(row)
        else:
            captures.append(row)
    manifest = {"schema": "nowscore_history_batch_v1", "source": "nowscore",
                "plan_sha256": plan["plan_sha256"], "inventory_sha256": plan["inventory_sha256"],
                "batch": batches[0], "controls": controls, "captures": captures,
                "started_at": started.isoformat(), "sealed_at": now().isoformat(),
                "implementation_sha256": plan["implementation_sha256"]}
    with (root / "manifest.json").open("x", encoding="utf-8") as handle:
        handle.write(canonical(manifest) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return manifest


def replay_play(row: dict, request: dict, root: Path, *, started: datetime, sealed: datetime) -> None:
    """Check all attempt bytes, HTTP/chronology evidence, and parsed page content."""
    if any(row.get(key) != value for key, value in request.items()):
        raise ValueError("play identity mismatch")
    attempts = row.get("attempts", [])
    if not attempts:
        raise ValueError("attempt ledger missing")
    for index, attempt in enumerate(attempts, 1):
        received = datetime.fromisoformat(attempt["received_at"])
        if (attempt.get("attempt") != index or received.tzinfo is None
                or not started <= received <= sealed):
            raise ValueError("attempt chronology/sequence mismatch")
        if "sha256" in attempt:
            sha = attempt["sha256"]
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise ValueError("invalid response hash")
            payload = (root / "raw" / f"{sha}.html").read_bytes()
            if digest(payload) != sha or len(payload) != attempt.get("byte_count"):
                raise ValueError("response hash or size mismatch")
    last = attempts[-1]
    if ("error" in last or last.get("partial") or last.get("status") != 200
            or last.get("final_url") != request["url"] or "sha256" not in last
            or row.get("sha256") != last["sha256"] or row.get("received_at") != last["received_at"]):
        raise ValueError("successful HTTP receipt mismatch")
    parsed = classify_play(payload, request["issue"], request["typeid"])
    if any(row.get(key) != value for key, value in parsed.items()):
        raise ValueError("parsed play replay mismatch")


def verify_history_batch(plan: dict, inventory: dict, root: Path) -> dict:
    """Replay a single batch against its complete inventory and frozen plan."""
    manifest = json.loads((root / "manifest.json").read_bytes())
    if ("replay_origin" in manifest and (root / "capture_log.jsonl").read_bytes()
            != manifest["replay_origin"]["log_text"].encode()):
        raise ValueError("replayed event log changed")
    return verify_history_manifest(plan, inventory, manifest, root)


def verify_history_manifest(plan: dict, inventory: dict, manifest: dict, raw_parent: Path) -> dict:
    """Replay a manifest using an explicit parent directory of raw response files.

    Supports both original batches and assembled evidence without copying
    validation rules or requiring machine-specific paths in receipts.
    """
    validate_history_capture_plan(plan, inventory)
    if (manifest.get("schema") != "nowscore_history_batch_v1"
            or manifest.get("source") != "nowscore"
            or manifest.get("plan_sha256") != plan["plan_sha256"]
            or manifest.get("inventory_sha256") != plan["inventory_sha256"]
            or manifest.get("implementation_sha256") != plan["implementation_sha256"]
            or manifest.get("batch") not in plan["batches"]):
        raise ValueError("batch does not bind plan")
    started = datetime.fromisoformat(manifest["started_at"])
    sealed = datetime.fromisoformat(manifest["sealed_at"])
    earliest = datetime.fromisoformat(plan["generated_at"])
    if "replay_origin" in manifest:
        earliest, original_sealed = verify_history_replay_origin(plan, manifest)
    else:
        original_sealed = sealed
    if started.tzinfo is None or sealed.tzinfo is None or not earliest <= started <= original_sealed <= sealed:
        raise ValueError("batch chronology mismatch")
    controls = manifest.get("controls", [])
    if len(controls) != 2:
        raise ValueError("controls missing")
    request = {"issue": plan["control_issue"], "typeid": 5, "url": plan["control_url"]}
    for row in controls:
        replay_play(row, request, raw_parent, started=started, sealed=original_sealed)
        if row["classification"] != "present":
            raise ValueError("control is empty")
    captures = manifest.get("captures", [])
    if len(captures) != len(manifest["batch"]["requests"]):
        raise ValueError("capture coverage mismatch")
    for row, request in zip(captures, manifest["batch"]["requests"], strict=True):
        replay_play(row, request, raw_parent, started=started, sealed=original_sealed)
    return manifest


def verify_history_replay_origin(plan: dict, manifest: dict) -> tuple[datetime, datetime]:
    """Validate unchanged original receipts under a later implementation plan.

    Original plan/manifest/log text is embedded, not machine-dependent paths.
    Scope and observations cannot change; raw parsing is checked by the caller.
    Nested replay and future/source chronology violations are rejected.
    """
    origin = manifest["replay_origin"]
    for key in ("plan", "manifest", "log"):
        if digest(origin[f"{key}_text"].encode()) != origin[f"{key}_sha256"]:
            raise ValueError("history replay origin hash mismatch")
    old_plan = json.loads(origin["plan_text"])
    old = json.loads(origin["manifest_text"])
    if "replay_origin" in old:
        raise ValueError("nested history replay forbidden")
    if old_plan.get("plan_sha256") != digest(canonical({
            k: v for k, v in old_plan.items() if k != "plan_sha256"}).encode()):
        raise ValueError("original history plan hash mismatch")
    variable = {"generated_at", "implementation_sha256", "plan_sha256"}
    if ({k: v for k, v in old_plan.items() if k not in variable}
            != {k: v for k, v in plan.items() if k not in variable}):
        raise ValueError("history replay cannot change source scope")
    implementation = old_plan.get("implementation_sha256", {})
    if (set(implementation) != set(plan["implementation_sha256"])
            or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
                   for v in implementation.values())):
        raise ValueError("original implementation identity invalid")
    expected_old = {k: v for k, v in manifest.items() if k != "replay_origin"}
    expected_old.update(plan_sha256=old_plan["plan_sha256"],
                        implementation_sha256=implementation, sealed_at=old["sealed_at"])
    if old != expected_old:
        raise ValueError("history replay changed original observations")
    old_generated = datetime.fromisoformat(old_plan["generated_at"])
    old_sealed = datetime.fromisoformat(old["sealed_at"])
    new_generated = datetime.fromisoformat(plan["generated_at"])
    sealed = datetime.fromisoformat(manifest["sealed_at"])
    if (any(t.tzinfo is None for t in (old_generated, old_sealed, new_generated, sealed))
            or not old_generated <= old_sealed <= new_generated <= sealed):
        raise ValueError("history replay chronology mismatch")
    events = [json.loads(line) for line in origin["log_text"].splitlines()]
    attempts = []
    for role, rows in (("pre_control", old["controls"][:1]), ("data", old["captures"]),
                       ("post_control", old["controls"][1:])):
        for row in rows:
            request = {key: row[key] for key in ("issue", "typeid", "url")}
            attempts.extend({**request, "role": role, "event": "attempt", **a} for a in row["attempts"])
    if [e for e in events if e.get("event") == "attempt"] != attempts:
        raise ValueError("original attempt log differs from manifest")
    expected_responses = [a for a in attempts if "sha256" in a]
    responses = [e for e in events if e.get("event") == "response"]
    if len(responses) != len(expected_responses) or len(events) != len(attempts) + len(responses):
        raise ValueError("original response event coverage mismatch")
    for response, attempt in zip(responses, expected_responses, strict=True):
        if (any(response.get(k) != v for k, v in attempt.items() if k not in {"event", "error"})
                or ("error" in response and response["error"] != attempt.get("error"))):
            raise ValueError("original response event differs from attempt")
    return old_generated, old_sealed


def replay_history_batch(plan: dict, inventory: dict, source_plan: Path,
                         source_root: Path, output: Path, *, generated_at: str) -> dict:
    """Reparse one original sealed batch under a later plan, without networking.

    Preserves original request times, all response bytes, and plan/manifest/log
    text. Publishes a new manifest only after verification; no overwrites.
    Semantic changes require a new capture, not relabeling the old receipt.
    """
    validate_history_capture_plan(plan, inventory)
    if output.exists():
        raise FileExistsError(output)
    texts = {"plan": source_plan.read_text(encoding="utf-8"),
             "manifest": (source_root / "manifest.json").read_text(encoding="utf-8"),
             "log": (source_root / "capture_log.jsonl").read_text(encoding="utf-8")}
    original = json.loads(texts["manifest"])
    if "replay_origin" in original:
        raise ValueError("nested history replay forbidden")
    origin = {}
    for key, value in texts.items():
        origin[f"{key}_text"] = value
        origin[f"{key}_sha256"] = digest(value.encode())
    manifest = {**original, "plan_sha256": plan["plan_sha256"],
                "implementation_sha256": plan["implementation_sha256"],
                "sealed_at": generated_at, "replay_origin": origin}
    verify_history_replay_origin(plan, manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="history-replay-", dir=output.parent) as directory:
        stage = Path(directory)
        shutil.copytree(source_root / "raw", stage / "raw")
        (stage / "capture_log.jsonl").write_text(texts["log"], encoding="utf-8")
        verify_history_manifest(plan, inventory, manifest, stage)
        shutil.copytree(stage, output)
        with (output / "manifest.json").open("x", encoding="utf-8") as handle:
            handle.write(canonical(manifest) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return manifest
