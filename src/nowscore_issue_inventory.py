"""Source-native Nowscore issue discovery with immutable batch receipts.

This module inventories settlement issue identifiers only. It performs no
settlement correction, payout calculation, historical learning, or source
fallback. Empty archive responses remain distinct from transport/parser errors.
"""
from __future__ import annotations

from src.issue_codes import issue_year

from collections import Counter
from datetime import datetime, timezone
import hashlib
import http.client
import fcntl
from functools import partial
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Callable
import urllib.error
import urllib.request
import sys
import tempfile

from importlib.metadata import version

from bs4 import BeautifulSoup


ARCHIVE_TEMPLATE = (
    "https://cp.nowscore.com/beijingdanchang/rangqiushengpingfu/"
    "kaijiang_dc_5_{issue}.html"
)
PLAN_SCHEMA = "nowscore_issue_inventory_plan_v1"
BATCH_SCHEMA = "nowscore_issue_inventory_batch_v1"
INVENTORY_SCHEMA = "nowscore_issue_inventory_v1"
ISSUE_RE = re.compile(r"\d{5,6}")


def canonical(value: object) -> str:
    """Return deterministic UTF-8 JSON text; reject non-finite numbers."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(payload: bytes) -> str:
    """Return lowercase SHA-256 for immutable payload identity."""
    return hashlib.sha256(payload).hexdigest()


def archive_url(issue: str) -> str:
    """Return the Nowscore SPF settlement archive URL for one issue."""
    if not isinstance(issue, str) or ISSUE_RE.fullmatch(issue) is None:
        raise ValueError("issue must contain five or six digits")
    return ARCHIVE_TEMPLATE.format(issue=issue)


def legacy_candidates(
    start_year: int,
    end_year: int,
    max_monthly_serial: int,
) -> list[str]:
    """Return YYMMNN candidates for pre-2020 years and monthly serial ceiling."""
    if (
        type(start_year) is not int
        or type(end_year) is not int
        or start_year < 2000
        or end_year < start_year
        or end_year >= 2020
    ):
        raise ValueError("legacy years must be ordered within 2000-2019")
    if type(max_monthly_serial) is not int or not 1 <= max_monthly_serial <= 99:
        raise ValueError("legacy monthly max serial must be 1-99")
    return [
        f"{year % 100:02d}{month:02d}{serial:02d}"
        for year in range(start_year, end_year + 1)
        for month in range(1, 13)
        for serial in range(1, max_monthly_serial + 1)
    ]


def modern_candidates(start_year: int, end_year: int, max_serial: int) -> list[str]:
    """Return YYNNN candidates for explicit 2020+ years and serial ceiling."""
    if start_year < 2020 or end_year < start_year or end_year > 2099:
        raise ValueError("modern years must be ordered within 2020-2099")
    if type(max_serial) is not int or not 1 <= max_serial <= 999:
        raise ValueError("modern max serial must be 1-999")
    return [
        f"{year % 100:02d}{serial:03d}"
        for year in range(start_year, end_year + 1)
        for serial in range(1, max_serial + 1)
    ]


def make_plan(
    *,
    legacy_start_year: int,
    legacy_end_year: int,
    legacy_max_monthly_serial: int,
    modern_start_year: int,
    modern_end_year: int,
    modern_max_serial: int,
    batch_size: int,
    control_issue: str,
    generated_at: str,
    request_interval_seconds: float,
) -> dict:
    """Build a complete explicit candidate plan without network or file writes."""
    parsed_time = datetime.fromisoformat(generated_at)
    if parsed_time.tzinfo is None:
        raise ValueError("generated_at requires timezone")
    if type(batch_size) is not int or batch_size <= 0:
        raise ValueError("batch size must be positive")
    if request_interval_seconds < 2:
        raise ValueError("request interval must be at least two seconds")
    archive_url(control_issue)
    candidates = legacy_candidates(
        legacy_start_year,
        legacy_end_year,
        legacy_max_monthly_serial,
    ) + modern_candidates(
        modern_start_year, modern_end_year, modern_max_serial
    )
    if len(candidates) != len(set(candidates)):
        raise ValueError("candidate identities overlap")
    batches = []
    for start_index in range(0, len(candidates), batch_size):
        values = candidates[start_index : start_index + batch_size]
        batches.append(
            {
                "batch_id": f"batch-{len(batches) + 1:04d}",
                "start_index": start_index,
                "end_index_exclusive": start_index + len(values),
                "candidate_count": len(values),
                "first_issue": values[0],
                "last_issue": values[-1],
            }
        )
    planned_requests = len(candidates) + 2 * len(batches)
    return {
        "schema": PLAN_SCHEMA,
        "source": "nowscore",
        "endpoint_template": ARCHIVE_TEMPLATE,
        "generated_at": generated_at,
        "control_issue": control_issue,
        "request_interval_seconds": request_interval_seconds,
        "candidate_contract": {
            "legacy": {
                "start_year": legacy_start_year,
                "end_year": legacy_end_year,
                "max_monthly_serial": legacy_max_monthly_serial,
                "encoding": "YYMMNN with month 01..12 and explicit monthly serial 01..max_monthly_serial",
            },
            "modern": {
                "start_year": modern_start_year,
                "end_year": modern_end_year,
                "max_serial": modern_max_serial,
                "encoding": "YYNNN with explicit inclusive serial 001..max_serial",
            },
        },
        "candidate_count": len(candidates),
        "candidates_sha256": digest(canonical(candidates).encode()),
        "candidates": candidates,
        "batch_size": batch_size,
        "batch_count": len(batches),
        "batches": batches,
        "planned_archive_requests": planned_requests,
        "minimum_inventory_request_seconds": (planned_requests - len(batches)) * request_interval_seconds,
        "implementation_sha256": digest(Path(__file__).read_bytes()),
        "runtime": {"python": sys.version, "beautifulsoup4": version("beautifulsoup4")},
        "historical_coverage_claimed": False,
        "production_enabled": False,
        "historical_learning_functions": [],
    }


def parse_archive(payload: bytes, issue: str) -> dict:
    """Classify an archive response, validating identity and header-only empties.

    Empty bytes or one complete native table containing its header only are
    source-empty observations, not proof that an issue never existed. Missing
    tables, damaged headers and fixture rows without links remain errors.
    """
    archive_url(issue)
    if payload == b"":
        return {
            "classification": "source_empty",
            "issue": issue,
            "match_count": 0,
            "first_slot": None,
            "last_slot": None,
        }
    text = payload.decode("utf-8-sig", errors="strict")
    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if "单场让球胜平负开奖信息" not in title:
        raise ValueError("archive title mismatch")
    selected = soup.select("#dropIssue option[selected]")
    if len(selected) > 1 or (selected and selected[0].get("value") != issue):
        raise ValueError("selected archive issue mismatch")
    active_path = (
        "/beijingdanchang/rangqiushengpingfu/"
        f"kaijiang_dc_5_{issue}.html"
    )
    active_links = soup.select("#mymenu li.myons a[href]")
    if len(active_links) != 1 or active_links[0].get("href") != active_path:
        raise ValueError("active archive issue link mismatch")
    slot_pattern = re.compile(rf"^/sp/danchang/{re.escape(issue)}_(\d+)_5\.html$")
    slots = []
    for link in soup.select("a[href]"):
        match = slot_pattern.fullmatch(link.get("href", ""))
        if match:
            slots.append(int(match.group(1)))
    if not slots:
        tables = soup.select("table.socai")
        headers = ["场次", "赛事", "开赛时间", "主队(让球)", "比分", "客队", "半场",
                   "彩果", "开奖SP", "平均欧*", "Crow*", "数据"]
        rows = tables[0].select("tr") if len(tables) == 1 else []
        if (
            len(rows) == 1
            and "ttis" in rows[0].get("class", [])
            and [cell.get_text(" ", strip=True) for cell in rows[0].find_all("td", recursive=False)] == headers
            and not soup.select('[id^="row_"]')
            and not any("/sp/danchang/" in link.get("href", "") for link in soup.select("a[href]"))
        ):
            return {"classification": "source_empty", "issue": issue, "match_count": 0,
                    "first_slot": None, "last_slot": None}
    if not slots or len(slots) != len(set(slots)) or min(slots) <= 0:
        raise ValueError("archive fixture links missing or duplicated")
    return {
        "classification": "present",
        "issue": issue,
        "match_count": len(slots),
        "first_slot": min(slots),
        "last_slot": max(slots),
    }


def urllib_transport(url: str, timeout_seconds: float) -> dict:
    """Fetch one URL and return status/final URL/body; never write files."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return {
                "status": response.status,
                "final_url": response.geturl(),
                "payload": response.read(),
            }
    except urllib.error.HTTPError as error:
        return {
            "status": error.code,
            "final_url": error.geturl(),
            "payload": error.read(),
        }


def rate_limited_transport(
    url: str, timeout_seconds: float, *, lock_path: Path, interval: float,
    transport: Callable[[str, float], dict] = urllib_transport,
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Serialize this user's live inventory requests across processes on one host.

    The explicit shared lock stores the next admissible UTC epoch seconds.
    Holds the lock through the response and releases it even on failure.
    """
    if interval < 2:
        raise ValueError("request interval must be at least two seconds")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+", encoding="ascii") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        value = lock.read()
        next_time = float(value) if value else 0
        delay = next_time - clock()
        if delay > 0:
            sleep(delay)
        lock.seek(0)
        lock.truncate()
        lock.write(str(clock() + interval))
        lock.flush()
        os.fsync(lock.fileno())
        return transport(url, timeout_seconds)


def fetch_archive(
    issue: str,
    *,
    timeout_seconds: float,
    max_attempts: int,
    transport: Callable[[str, float], dict] = urllib_transport,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
    retry_interval_seconds: float = 2,
    record_attempt: Callable[[dict, bytes | None], None] | None = None,
) -> tuple[dict, list[bytes]]:
    """Fetch and validate one issue with bounded transient retries."""
    if (
        timeout_seconds <= 0
        or type(max_attempts) is not int
        or max_attempts <= 0
        or retry_interval_seconds < 2
    ):
        raise ValueError("timeout and max attempts must be positive")
    url = archive_url(issue)
    attempts = []
    payloads = []
    for attempt_number in range(1, max_attempts + 1):
        if attempt_number > 1:
            sleep(retry_interval_seconds)
        attempt = {"attempt": attempt_number, "received_at": now().isoformat()}
        payload = None
        try:
            response = transport(url, timeout_seconds)
            status = response["status"]
            final_url = response["final_url"]
            payload = response["payload"]
            if type(status) is not int or not isinstance(final_url, str) or not isinstance(payload, bytes):
                raise ValueError("transport response contract violated")
            payloads.append(payload)
            attempt = {
                "attempt": attempt_number,
                "received_at": now().isoformat(),
                "status": status,
                "final_url": final_url,
                "sha256": digest(payload),
                "byte_count": len(payload),
            }
            if record_attempt is not None:
                record_attempt({**attempt, "event": "response"}, payload)
            if status == 200 and final_url == url:
                result = parse_archive(payload, issue)
                attempt["classification"] = result["classification"]
                if record_attempt is not None:
                    record_attempt(attempt, payload)
                attempts.append(attempt)
                return ({**result, "url": url, "attempts": attempts}, payloads)
            attempt["error"] = "unexpected HTTP status or redirect"
        except (KeyError, OSError, http.client.HTTPException, TypeError, UnicodeError, ValueError) as error:
            attempt["error"] = f"{type(error).__name__}: {error}"
            if isinstance(error, http.client.IncompleteRead):
                payload = error.partial
                payloads.append(payload)
                attempt.update(partial=True, sha256=digest(payload), byte_count=len(payload))
        if record_attempt is not None:
            record_attempt(attempt, payload)
        attempts.append(attempt)
    return (
        {
            "classification": "fetch_or_parse_failure",
            "issue": issue,
            "url": url,
            "match_count": None,
            "first_slot": None,
            "last_slot": None,
            "attempts": attempts,
        },
        payloads,
    )


def _write_raw(raw_root: Path, payload: bytes) -> str:
    sha256 = digest(payload)
    path = raw_root / f"{sha256}.html"
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("raw hash collision")
    else:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return sha256


def capture_batch(
    plan: dict,
    batch_id: str,
    run_root: Path,
    *,
    timeout_seconds: float,
    max_attempts: int,
    transport: Callable[[str, float], dict] = urllib_transport,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict:
    """Capture one immutable plan batch with before/after source controls.

    Creates a new directory and preserves each raw response plus append-only log.
    Interrupted or failed runs retain evidence but have no sealed manifest.
    """
    validate_plan(plan)
    current_implementation = digest(Path(__file__).read_bytes())
    if plan.get("implementation_sha256") != current_implementation:
        raise ValueError("capture implementation differs from plan")
    planned_at = datetime.fromisoformat(plan["generated_at"])
    if planned_at.tzinfo is None or planned_at > now():
        raise ValueError("plan timestamp must not be later than capture start")
    batch_rows = [row for row in plan["batches"] if row["batch_id"] == batch_id]
    if len(batch_rows) != 1:
        raise ValueError("batch identity missing or duplicated")
    if run_root.exists():
        raise FileExistsError(run_root)
    run_root.mkdir(parents=True)
    raw_root = run_root / "raw"
    raw_root.mkdir()
    log_path = run_root / "capture_log.jsonl"
    batch = batch_rows[0]
    candidates = plan["candidates"][batch["start_index"] : batch["end_index_exclusive"]]
    request_interval = plan["request_interval_seconds"]
    if transport is urllib_transport:
        transport = partial(
            rate_limited_transport,
            lock_path=Path(tempfile.gettempdir()) / f"nowscore-inventory-{os.getuid()}.lock",
            interval=request_interval,
        )
    request_count = 0

    def fetch_paced(issue: str, role: str) -> tuple[dict, list[bytes]]:
        nonlocal request_count
        if request_count:
            sleep(request_interval)
        request_count += 1
        def record_attempt(attempt: dict, payload: bytes | None) -> None:
            if payload is not None:
                _write_raw(raw_root, payload)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(canonical({"event": "attempt", "role": role,
                                     "issue": issue, "url": archive_url(issue),
                                     **attempt}) + "\n")
                log.flush()
                os.fsync(log.fileno())

        return fetch_archive(
            issue,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            transport=transport,
            now=now,
            sleep=sleep,
            retry_interval_seconds=request_interval,
            record_attempt=record_attempt,
        )

    def preserve_payloads(row: dict, payloads: list[bytes]) -> None:
        row["raw_sha256s"] = [_write_raw(raw_root, payload) for payload in payloads]
        row["raw_sha256"] = row["raw_sha256s"][-1] if row["raw_sha256s"] else None

    controls = []
    captures = []
    control, payloads = fetch_paced(plan["control_issue"], "pre_control")
    preserve_payloads(control, payloads)
    controls.append(control)
    if control["classification"] != "present":
        raise ValueError("pre-batch source control failed")
    for issue in candidates:
        capture, payloads = fetch_paced(issue, "candidate")
        preserve_payloads(capture, payloads)
        captures.append(capture)
    control, payloads = fetch_paced(plan["control_issue"], "post_control")
    preserve_payloads(control, payloads)
    controls.append(control)
    if control["classification"] != "present":
        raise ValueError("post-batch source control failed")
    if any(row["classification"] == "fetch_or_parse_failure" for row in captures):
        raise ValueError("unresolved candidate failure; batch remains unsealed")
    manifest = {
        "schema": BATCH_SCHEMA,
        "source": "nowscore",
        "plan_sha256": digest(canonical(plan).encode()),
        "batch": batch,
        "controls": controls,
        "captures": captures,
        "classification_counts": dict(
            sorted(Counter(row["classification"] for row in captures).items())
        ),
        "sealed_at": now().isoformat(),
        "implementation_sha256": digest(Path(__file__).read_bytes()),
        "runtime": {"python": sys.version, "beautifulsoup4": version("beautifulsoup4")},
    }
    (run_root / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
    return manifest


def validate_plan(plan: dict) -> None:
    """Validate candidate/batch coverage and bound deterministic plan hashes."""
    if plan.get("schema") != PLAN_SCHEMA or plan.get("source") != "nowscore":
        raise ValueError("unsupported inventory plan")
    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or not candidates or any(
        not isinstance(issue, str) or ISSUE_RE.fullmatch(issue) is None for issue in candidates
    ):
        raise ValueError("invalid candidate domain")
    if len(candidates) != len(set(candidates)):
        raise ValueError("duplicate candidates")
    contract = plan.get("candidate_contract")
    if not isinstance(contract, dict):
        raise ValueError("candidate contract missing")
    try:
        legacy = contract["legacy"]
        modern = contract["modern"]
        expected_candidates = legacy_candidates(
            legacy["start_year"],
            legacy["end_year"],
            legacy["max_monthly_serial"],
        ) + modern_candidates(
            modern["start_year"],
            modern["end_year"],
            modern["max_serial"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid candidate contract") from error
    if candidates != expected_candidates:
        raise ValueError("candidates do not match candidate contract")
    if plan.get("candidate_count") != len(candidates) or plan.get("candidates_sha256") != digest(
        canonical(candidates).encode()
    ):
        raise ValueError("candidate count/hash mismatch")
    archive_url(plan.get("control_issue"))
    if plan.get("request_interval_seconds", 0) < 2:
        raise ValueError("unsafe request interval")
    covered = []
    for ordinal, batch in enumerate(plan.get("batches", []), 1):
        if batch.get("batch_id") != f"batch-{ordinal:04d}":
            raise ValueError("batch sequence mismatch")
        start = batch.get("start_index")
        end = batch.get("end_index_exclusive")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(candidates):
            raise ValueError("batch bounds invalid")
        values = candidates[start:end]
        if (
            batch.get("candidate_count") != len(values)
            or batch.get("first_issue") != values[0]
            or batch.get("last_issue") != values[-1]
        ):
            raise ValueError("batch content mismatch")
        covered.extend(values)
    if covered != candidates or plan.get("batch_count") != len(plan.get("batches", [])):
        raise ValueError("batches do not exactly cover candidates")


def verify_batch(plan: dict, root: Path) -> dict:
    """Replay one sealed batch without requiring or claiming complete coverage.

    Reads plan-bound manifest and raw files, returning the validated manifest.
    No writes or network; rejects stale implementation and conflicting metadata.
    """
    validate_plan(plan)
    if plan.get("implementation_sha256") != digest(Path(__file__).read_bytes()):
        raise ValueError("replay implementation differs from plan")
    manifest = json.loads((root / "manifest.json").read_bytes())
    if manifest.get("schema") != BATCH_SCHEMA or manifest.get("plan_sha256") != digest(canonical(plan).encode()):
        raise ValueError("batch manifest does not bind plan")
    if manifest.get("implementation_sha256") != plan.get("implementation_sha256"):
        raise ValueError("batch implementation differs from plan")
    batch_id = manifest.get("batch", {}).get("batch_id")
    expected = [row for row in plan["batches"] if row["batch_id"] == batch_id]
    if len(expected) != 1 or manifest["batch"] != expected[0]:
        raise ValueError("batch definition mismatch")
    controls = manifest.get("controls", [])
    if len(controls) != 2 or any(row.get("classification") != "present" for row in controls):
        raise ValueError("batch controls incomplete")
    for row in controls:
        replay_capture(row, root, plan["control_issue"])
    issues = plan["candidates"][expected[0]["start_index"]:expected[0]["end_index_exclusive"]]
    if [row.get("issue") for row in manifest.get("captures", [])] != issues:
        raise ValueError("batch capture order mismatch")
    for row in manifest["captures"]:
        if row.get("classification") not in {"present", "source_empty"}:
            raise ValueError("unresolved candidate failure")
        replay_capture(row, root, row["issue"])
    evidence_plan = _replay_origin(plan, manifest, root) if "replay_origin" in manifest else plan
    planned_at = datetime.fromisoformat(evidence_plan["generated_at"])
    sealed_at = datetime.fromisoformat(manifest["sealed_at"])
    if sealed_at.tzinfo is None or sealed_at < datetime.fromisoformat(plan["generated_at"]):
        raise ValueError("batch seal precedes plan")
    for row in [*controls, *manifest["captures"]]:
        for attempt in row["attempts"]:
            received_at = datetime.fromisoformat(attempt["received_at"])
            if received_at.tzinfo is None or not planned_at <= received_at <= sealed_at:
                raise ValueError("batch receipt chronology mismatch")
    counts = dict(sorted(Counter(row["classification"] for row in manifest["captures"]).items()))
    if manifest.get("classification_counts") != counts:
        raise ValueError("batch classification counts mismatch")
    return manifest


def _replay_origin(plan: dict, manifest: dict, root: Path) -> dict:
    """Validate immutable original receipts for an offline-replayed batch.

    No network or writes. Original observations must be byte-identical in the
    two manifests; current parsing is checked separately by verify_batch.
    One original capture is supported, not nested replay chains.
    """
    origin = manifest["replay_origin"]
    evidence = root / "provenance"
    payloads = {}
    for name in ("plan.json", "manifest.json", "capture_log.jsonl"):
        payloads[name] = (evidence / name).read_bytes()
        if digest(payloads[name]) != origin.get(name):
            raise ValueError("replay origin hash mismatch")
    source_plan = json.loads(payloads["plan.json"])
    source_manifest = json.loads(payloads["manifest.json"])
    validate_plan(source_plan)
    if (
        source_manifest.get("schema") != BATCH_SCHEMA
        or "replay_origin" in source_manifest
        or source_manifest.get("plan_sha256") != digest(canonical(source_plan).encode())
        or source_manifest.get("implementation_sha256") != source_plan.get("implementation_sha256")
        or not re.fullmatch(r"[0-9a-f]{64}", source_plan.get("implementation_sha256", ""))
    ):
        raise ValueError("invalid original capture receipt")
    for key in ("candidates", "batches", "control_issue", "request_interval_seconds", "endpoint_template"):
        if source_plan.get(key) != plan.get(key):
            raise ValueError("replay source candidate contract differs")
    for key in ("batch", "controls", "captures", "classification_counts"):
        if source_manifest.get(key) != manifest.get(key):
            raise ValueError("replay changed original observations")
    source_start = datetime.fromisoformat(source_plan["generated_at"])
    source_end = datetime.fromisoformat(source_manifest["sealed_at"])
    planned_at = datetime.fromisoformat(plan["generated_at"])
    if any(value.tzinfo is None for value in (source_start, source_end, planned_at)) or not (
        source_start <= source_end <= planned_at
    ):
        raise ValueError("replay origin chronology mismatch")
    for row in [*source_manifest["controls"], *source_manifest["captures"]]:
        for attempt in row["attempts"]:
            received_at = datetime.fromisoformat(attempt["received_at"])
            if received_at.tzinfo is None or not source_start <= received_at <= source_end:
                raise ValueError("replay original receipt chronology mismatch")
    if (root / "capture_log.jsonl").read_bytes() != payloads["capture_log.jsonl"]:
        raise ValueError("replay changed original capture log")
    return source_plan


def replay_sealed_batch(
    plan: dict, source_plan_path: Path, source_root: Path, output_root: Path, *, generated_at: str,
) -> dict:
    """Reparse a sealed raw batch under a new plan without new HTTP observations.

    Writes a new batch and copies original plan/manifest/log provenance. Raw
    response times and observations remain unchanged; the new seal records
    replay time, not collection time. Rejects semantic changes, changed scope,
    tampering, unsealed input and an existing output. Failed replay leaves no
    accepted manifest; input files are never modified.
    """
    validate_plan(plan)
    if plan.get("implementation_sha256") != digest(Path(__file__).read_bytes()):
        raise ValueError("replay implementation differs from plan")
    if output_root.exists():
        raise FileExistsError(output_root)
    replayed_at = datetime.fromisoformat(generated_at)
    if replayed_at.tzinfo is None or replayed_at < datetime.fromisoformat(plan["generated_at"]):
        raise ValueError("replay time precedes plan")
    source_manifest_bytes = (source_root / "manifest.json").read_bytes()
    source_manifest = json.loads(source_manifest_bytes)
    if "replay_origin" in source_manifest:
        raise ValueError("replay requires original capture, not nested replay")
    original = {
        "plan.json": source_plan_path.read_bytes(),
        "manifest.json": source_manifest_bytes,
        "capture_log.jsonl": (source_root / "capture_log.jsonl").read_bytes(),
    }
    manifest = {
        **source_manifest,
        "plan_sha256": digest(canonical(plan).encode()),
        "implementation_sha256": plan["implementation_sha256"],
        "sealed_at": generated_at,
        "runtime": {"python": sys.version, "beautifulsoup4": version("beautifulsoup4")},
        "replay_origin": {name: digest(payload) for name, payload in original.items()},
    }
    # Validate the complete staged receipt before publishing any output manifest.
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nowscore-replay-", dir=output_root.parent) as temporary:
        stage = Path(temporary)
        shutil.copytree(source_root / "raw", stage / "raw")
        (stage / "provenance").mkdir()
        for name, payload in original.items():
            (stage / "provenance" / name).write_bytes(payload)
        (stage / "capture_log.jsonl").write_bytes(original["capture_log.jsonl"])
        (stage / "manifest.json").write_text(canonical(manifest) + "\n", encoding="utf-8")
        verify_batch(plan, stage)
        # copytree refuses a concurrently created destination; no overwrite.
        shutil.copytree(stage, output_root, ignore=shutil.ignore_patterns("manifest.json"))
        shutil.copyfile(stage / "provenance" / "manifest.json", output_root / "provenance" / "manifest.json")
        with (output_root / "manifest.json").open("x", encoding="utf-8") as handle:
            handle.write(canonical(manifest) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return verify_batch(plan, output_root)


def merge_batches(
    plan: dict,
    batch_roots: list[Path],
    output: Path,
    *,
    generated_at: str,
) -> dict:
    """Merge sealed batches only when they exactly cover the candidate plan."""
    validate_plan(plan)
    if datetime.fromisoformat(generated_at).tzinfo is None:
        raise ValueError("generated_at requires timezone")
    if output.exists():
        raise FileExistsError(output)
    plan_sha256 = digest(canonical(plan).encode())
    manifests = {}
    captures = {}
    for root in batch_roots:
        manifest = verify_batch(plan, root)
        manifest_bytes = (root / "manifest.json").read_bytes()
        batch_id = manifest.get("batch", {}).get("batch_id")
        if batch_id in manifests:
            raise ValueError("duplicate batch manifest")
        for row in manifest["captures"]:
            if row["issue"] in captures:
                raise ValueError("duplicate candidate capture")
            captures[row["issue"]] = row
        manifests[batch_id] = {
            "sha256": digest(manifest_bytes),
        }
    required_batches = {row["batch_id"] for row in plan["batches"]}
    if set(manifests) != required_batches or set(captures) != set(plan["candidates"]):
        raise ValueError("batch set does not completely cover plan")
    present = [issue for issue in plan["candidates"] if captures[issue]["classification"] == "present"]
    empty = [issue for issue in plan["candidates"] if captures[issue]["classification"] == "source_empty"]
    per_year = Counter(issue_year(issue) for issue in present)
    modern_gaps = []
    for year in range(
        plan["candidate_contract"]["modern"]["start_year"],
        plan["candidate_contract"]["modern"]["end_year"] + 1,
    ):
        values = sorted(int(issue[2:]) for issue in present if issue_year(issue) == year)
        if values:
            observed = set(values)
            modern_gaps.extend(
                f"{year % 100:02d}{serial:03d}"
                for serial in range(min(values), max(values) + 1)
                if serial not in observed
            )
    inventory = {
        "schema": INVENTORY_SCHEMA,
        "source": "nowscore",
        "evidence_class": "OBSERVED_ARCHIVE_AT_CAPTURE_TIME",
        "generated_at": generated_at,
        "plan_sha256": plan_sha256,
        "batch_manifests": dict(sorted(manifests.items())),
        "candidate_count": len(plan["candidates"]),
        "issue_count": len(present),
        "source_empty_count": len(empty),
        "issues": present,
        "source_empty_candidates": empty,
        "issues_by_year": {str(year): count for year, count in sorted(per_year.items())},
        "modern_internal_gaps": modern_gaps,
        "candidate_coverage_complete": True,
        "five_play_pages_to_capture": len(present) * 5,
        "minimum_five_play_request_seconds": len(present)
        * 5
        * plan["request_interval_seconds"],
        "production_enabled": False,
        "historical_learning_functions": [],
        "implementation_sha256": digest(Path(__file__).read_bytes()),
    }
    inventory["inventory_sha256"] = digest(canonical(inventory).encode())
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(canonical(inventory) + "\n")
    return inventory


def replay_capture(row: dict, root: Path, issue: str) -> None:
    """Verify response hashes, successful HTTP receipt and all parsed fields.

    Reads immutable batch raw files; raises on missing or conflicting evidence.
    """
    if row.get("issue") != issue or row.get("url") != archive_url(issue):
        raise ValueError("batch response identity mismatch")
    hashes = row.get("raw_sha256s")
    if not hashes or row.get("raw_sha256") != hashes[-1]:
        raise ValueError("batch raw response ledger missing")
    attempts = row.get("attempts", [])
    if [attempt["sha256"] for attempt in attempts if "sha256" in attempt] != hashes:
        raise ValueError("attempt raw ledger mismatch")
    for sha in hashes:
        if not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None:
            raise ValueError("invalid raw hash")
        payload = (root / "raw" / f"{sha}.html").read_bytes()
        if digest(payload) != sha:
            raise ValueError("batch raw response hash mismatch")
    last = attempts[-1]
    if last.get("status") != 200 or last.get("final_url") != archive_url(issue) or last.get("partial"):
        raise ValueError("successful HTTP receipt missing")
    parsed = parse_archive(payload, issue)
    if any(row.get(key) != value for key, value in parsed.items()):
        raise ValueError("batch replay classification or metadata mismatch")
