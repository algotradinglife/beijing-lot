"""Bounded, auditable HTTP probing primitives for the #493 Nowscore 3in1 probe.

The probe is authorised for exactly one fixture and one source, with hard caps on
attempts, serial spacing and wall clock. These primitives make those caps
enforceable and auditable rather than aspirational:

* ONE accounting contract: a dispatchable ledger holds a `reservation` per attempt,
  written before dispatch. A ledger with outcomes but no reservations is a
  reconstructed historical record and is REJECTED for dispatch (fail closed);
* the whole check/spacing/reserve/dispatch/record lifecycle is serialised under an
  exclusive file lock, and authoritative state is refreshed under that lock, so
  concurrent processes cannot double-spend or start together;
* the wall-clock deadline is persisted from the first reserved attempt and is
  enforced before waiting, after waiting, before dispatch, and while the response
  body is being consumed;
* redirects are followed manually and every hop must stay inside the authorised
  source and fixture;
* raw bodies are written under attempt-specific immutable filenames.

Importing this module performs no I/O beyond defining constants.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import requests
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

ENTRY = "https://live.nowscore.com/odds/3in1Odds.aspx"
PROVIDER_MATCH_ID = "3061587"
ISSUE = "26085"
MATCH_IDX = 5

MAX_ATTEMPTS = 10
MIN_INTERVAL_SEC = 2.0
TIMEOUT_SEC = 20.0
MAX_WALL_SEC = 300.0
MAX_HOPS = 5
BODY_CHUNK = 65536
REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
AUTHORISED_HOSTS = frozenset({"live.nowscore.com"})

LEDGER_NAME = "requests.jsonl"
LOCK_NAME = "requests.lock"
RESERVATION = "reservation"
OUTCOME = "outcome"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://live.nowscore.com/",
}


class ScopeViolation(RuntimeError):
    """Raised when a request or redirect target leaves the authorised scope."""


class LedgerContractError(RuntimeError):
    """Raised when a ledger cannot support further dispatch."""


class DeadlineExceeded(RuntimeError):
    """Raised when a response body outlives the wall-clock deadline."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def assert_in_scope(url: str) -> str:
    """Every issued URL must stay on the authorised source and fixture."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ScopeViolation(f"unsupported scheme: {url}")
    if parsed.hostname not in AUTHORISED_HOSTS:
        raise ScopeViolation(f"host outside the authorised source: {parsed.hostname}")
    if parse_qs(parsed.query).get("id") != [PROVIDER_MATCH_ID]:
        raise ScopeViolation(f"fixture outside the authorised sample: {url}")
    return url


def load_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def append_ledger(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@contextmanager
def ledger_lock(root: Path):
    """Hold the exclusive lock across the whole check/reserve/dispatch cycle."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / LOCK_NAME).open("w") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def validate_ledger(ledger: list[dict]) -> set[str]:
    """Enforce the single accounting contract and fail closed on a foreign ledger."""
    ids = [r.get("attempt_id") for r in ledger]
    if any(i is None for i in ids):
        raise LedgerContractError("ledger record without an attempt_id")
    reserved = {r["attempt_id"] for r in ledger if r.get("kind") == RESERVATION}
    outcomes = {r["attempt_id"] for r in ledger if r.get("kind") == OUTCOME}
    orphans = outcomes - reserved
    if orphans:
        raise LedgerContractError(
            f"{len(orphans)} outcome record(s) have no reservation; this ledger is a "
            "reconstructed historical record and must not be used for dispatch")
    unknown_kinds = {r.get("kind") for r in ledger} - {RESERVATION, OUTCOME}
    if unknown_kinds:
        raise LedgerContractError(f"unknown ledger record kinds: {sorted(unknown_kinds)}")
    return reserved


def count_attempts(ledger: list[dict]) -> int:
    """Count unique reserved HOP attempts in a DISPATCHABLE ledger.

    A reservation is written once per hop, so this counts hop attempts, not
    top-level requests: one request answering 200 counts once, but a request
    that redirects counts for each hop it follows. Raises LedgerContractError
    on a reconstructed historical ledger.
    """
    return len(validate_ledger(ledger))


def count_top_level_requests(ledger: list[dict]) -> int:
    """Count logical requests issued: one per distinct hop-0 attempt.

    Only outcomes carry an attempt id and a hop index, and a followed redirect
    writes hop 1, 2, ... So hop 0 is exactly the set of requests actually issued,
    while every later hop is one request making extra round trips. Counting every
    record (or every reservation) instead would report the hop total as the
    request total and overstate it whenever a redirect occurred.

    The identity is the attempt id, not the dispatch label: build_request_plan
    returns one entry per requested company, so a repeated --companies 1,1 (or a
    re-run) issues several genuinely separate requests that share one label.
    Counting labels would collapse those into one and understate the count.

    A ledger with no recorded hop index -- the reconstructed historical one,
    where the field is absent rather than 0 -- yields 0, which is the honest
    answer: that ledger proves only how many outcomes survived, not how many
    requests were made.
    """
    return len({r.get("attempt_id") for r in ledger
                if r.get("kind") == OUTCOME and r.get("hop") == 0})


def count_historical_attempts(ledger: list[dict]) -> int:
    """Count unique attempt ids in any ledger, for reporting only.

    Never use this to authorise dispatch; it deliberately does not validate the
    accounting contract.
    """
    return len({r.get("attempt_id") for r in ledger if r.get("attempt_id")})


class Budget:
    """Hard caps shared across processes, derived from the durable ledger."""

    def __init__(self, ledger: list[dict], clock=time.time) -> None:
        self.clock = clock
        reserved = validate_ledger(ledger)
        self.attempts = len(reserved)
        starts = [r["started_epoch"] for r in ledger
                  if r.get("kind") == RESERVATION and r.get("started_epoch")]
        self.first_start = min(starts) if starts else None
        self.deadline = (self.first_start + MAX_WALL_SEC
                         if self.first_start is not None else None)
        ends = [r["ended_epoch"] for r in ledger if r.get("ended_epoch")]
        self.last_end = max(ends) if ends else None
        # A reservation with no outcome consumed an attempt but produced no timing.
        self.unresolved = reserved - {r["attempt_id"] for r in ledger
                                      if r.get("kind") == OUTCOME and r.get("ended_epoch")}

    def wall_sec(self) -> float:
        if self.first_start is None:
            return 0.0
        return max(0.0, self.clock() - self.first_start)

    def remaining_wall(self) -> float:
        if self.deadline is None:
            return MAX_WALL_SEC
        return max(0.0, self.deadline - self.clock())

    def blocked(self) -> str | None:
        if self.attempts >= MAX_ATTEMPTS:
            return "MAX_ATTEMPTS"
        if self.deadline is not None and self.clock() >= self.deadline:
            return "MAX_WALL_SEC"
        if self.unresolved:
            return "UNRESOLVED_ATTEMPT"
        return None

    def remaining_attempts(self) -> int:
        return max(0, MAX_ATTEMPTS - self.attempts)

    def request_timeout(self) -> float:
        """The socket timeout never exceeds the remaining wall clock."""
        return max(0.001, min(TIMEOUT_SEC, self.remaining_wall()))

    def wait(self) -> None:
        """Honour the serial interval using subsecond timing."""
        if self.last_end is None:
            return
        gap = MIN_INTERVAL_SEC - (self.clock() - self.last_end)
        if gap > 0:
            time.sleep(gap)

    def reserve(self) -> dict:
        """Record the attempt BEFORE dispatch so interruption cannot refund it."""
        started = self.clock()
        if self.first_start is None:
            self.first_start = started
            self.deadline = started + MAX_WALL_SEC
        self.attempts += 1
        reservation = {
            "kind": RESERVATION,
            "attempt_id": uuid.uuid4().hex[:12],
            "started_epoch": started,
            "started_at": iso_from_epoch(started),
        }
        self.unresolved.add(reservation["attempt_id"])
        return reservation


def close_quietly(resource) -> None:
    """Best-effort close; swallows errors and never raises to the caller.

    Must be called OFF the deadline path: a blocking close() would otherwise
    extend the very budget it is meant to enforce.
    """
    try:
        resource.close()
    except Exception:
        pass


def request_under_deadline(session, url: str, deadline: float, timeout: float,
                          clock=time.time):
    """Run the ENTIRE request lifecycle under a hard caller-side deadline.

    A chunk-boundary check and a watchdog inside consume_body() cannot bound the
    caller's wall clock: session.get() may block during connection or header
    handling, and response.close() need not interrupt an in-flight read. Running
    the whole lifecycle in a worker thread means the caller always returns at the
    deadline, whatever the transport does.

    What is guaranteed: the caller returns by the deadline. What is NOT: the
    abandoned worker cannot be forcibly terminated, so its thread and socket
    release are best effort and may outlive the deadline.
    """
    outcome: dict = {}

    def worker() -> None:
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout,
                                   allow_redirects=False, stream=True)
            outcome["response"] = response
            outcome["body"] = consume_body(response, deadline, clock)
        except BaseException as exc:  # re-raised on the caller's thread
            outcome["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=max(0.0, deadline - clock()))
    if thread.is_alive():
        # Cleanup must never block the caller: a blocking close() would defeat the
        # deadline it is meant to enforce. Hand it to a daemon and return now.
        threading.Thread(target=close_quietly, args=(session,),
                         daemon=True).start()
        raise DeadlineExceeded("request lifecycle outlived the wall-clock deadline")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["response"], outcome["body"]


def consume_body(response, deadline: float, clock=time.time) -> bytes:
    """Read the body under a watchdog that attempts cancellation at the deadline.

    A chunk-boundary check alone cannot bound the total duration: a trickling
    response can block inside a single read past the deadline. The watchdog closes
    the response at the deadline, which is a best-effort attempt to release a
    blocked read; a transport that ignores close() is not interruptible this way,
    which is why request_under_deadline() enforces the caller's deadline instead.
    """
    if not hasattr(response, "iter_content"):
        if clock() >= deadline:
            raise DeadlineExceeded("deadline passed before the body was read")
        return response.content

    aborted = threading.Event()

    def abort() -> None:
        aborted.set()
        try:
            response.close()
        except Exception:  # closing an already-closed response is not an error
            pass

    timer = threading.Timer(max(0.0, deadline - clock()), abort)
    timer.daemon = True
    timer.start()
    chunks = []
    try:
        for chunk in response.iter_content(BODY_CHUNK):
            if clock() >= deadline or aborted.is_set():
                raise DeadlineExceeded("response body outlived the wall-clock deadline")
            chunks.append(chunk)
        if clock() >= deadline or aborted.is_set():
            raise DeadlineExceeded("response body outlived the wall-clock deadline")
        return b"".join(chunks)
    finally:
        timer.cancel()
        try:
            response.close()
        except Exception:
            pass


class Recorder:
    """Appends to the shared ledger and writes attempt-specific raw bodies."""

    def __init__(self, root: Path, jar_id: str) -> None:
        self.root = root
        self.jar_id = jar_id
        self.ledger_path = root / LEDGER_NAME
        self.raw_dir = root / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def write_raw(self, label: str, attempt_id: str, body: bytes) -> tuple[str, str]:
        """Attempt-specific names keep repeated runs from overwriting bytes."""
        raw_path = self.raw_dir / f"{label}_{attempt_id}.html"
        raw_path.write_bytes(body)
        return str(raw_path.relative_to(self.root)), hashlib.sha256(body).hexdigest()

    def record_outcome(self, *, reservation: dict, url: str, status: int | None,
                       body: bytes | None, ended_epoch: float, error: str | None,
                       label: str, hop: int, redirect_to: str | None = None,
                       rejected_redirect: str | None = None) -> None:
        raw_file = None
        digest = None
        if body is not None:
            raw_file, digest = self.write_raw(label, reservation["attempt_id"], body)
        append_ledger(self.ledger_path, {
            "kind": OUTCOME,
            "attempt_id": reservation["attempt_id"],
            "label": label,
            "hop": hop,
            "url": url,
            "redirect_to": redirect_to,
            "rejected_redirect": rejected_redirect,
            "http_status": status,
            "started_at": reservation["started_at"],
            "started_epoch": reservation["started_epoch"],
            "ended_at": iso_from_epoch(ended_epoch),
            "ended_epoch": ended_epoch,
            "body_bytes": len(body) if body is not None else 0,
            "sha256": digest,
            "raw_file": raw_file,
            "error": error,
            "cookie_jar_id": self.jar_id,
        })


def _dispatch_hop(session, current: str, label: str, hop: int, recorder: Recorder,
                  clock) -> tuple[str | None, bytes | None]:
    """One hop. Must be called while holding the ledger lock."""
    ledger = load_ledger(recorder.ledger_path)
    budget = Budget(ledger, clock=clock)
    stop = budget.blocked()
    if stop:
        return stop, None
    budget.wait()
    # The sleep may have crossed the deadline or another process may have spent.
    ledger = load_ledger(recorder.ledger_path)
    budget = Budget(ledger, clock=clock)
    stop = budget.blocked()
    if stop:
        return stop, None
    reservation = budget.reserve()
    append_ledger(recorder.ledger_path, reservation)
    deadline = budget.deadline if budget.deadline is not None else clock() + MAX_WALL_SEC
    try:
        try:
            response, body = request_under_deadline(
                session, current, deadline, budget.request_timeout(), clock)
        except DeadlineExceeded as exc:
            recorder.record_outcome(
                reservation=reservation, url=current, status=None,
                body=None, ended_epoch=clock(), error=f"DeadlineExceeded: {exc}",
                label=f"{label}_hop{hop}" if hop else label, hop=hop)
            return "MAX_WALL_SEC", None
        status = response.status_code
        location = response.headers.get("Location") if status in REDIRECT_CODES else None
        target = urljoin(current, location) if location else None
        rejected = None
        if target is not None:
            try:
                assert_in_scope(target)
            except ScopeViolation:
                rejected = target
                target = None
        recorder.record_outcome(
            reservation=reservation, url=current, status=status, body=body,
            ended_epoch=clock(), error=None,
            label=f"{label}_hop{hop}" if hop else label, hop=hop,
            redirect_to=target, rejected_redirect=rejected)
        return target, body
    except ScopeViolation:
        raise
    except requests.RequestException as exc:
        # Only transport failures are recorded as an attempt outcome; a
        # programming error must surface instead of looking like a network fault.
        recorder.record_outcome(
            reservation=reservation, url=current, status=None, body=None,
            ended_epoch=clock(), error=f"{type(exc).__name__}: {exc}",
            label=f"{label}_hop{hop}" if hop else label, hop=hop)
        return None, None


def fetch_with_hops(session, url: str, recorder: Recorder, label: str, root: Path,
                    max_hops: int = MAX_HOPS, clock=time.time) -> list[str]:
    """Follow redirects manually; each hop reserves an attempt under the lock."""
    bodies: list[str] = []
    current = assert_in_scope(url)
    for hop in range(max_hops):
        with ledger_lock(root):
            target, body = _dispatch_hop(session, current, label, hop, recorder, clock)
        if body is None:
            break
        bodies.append(body.decode("utf-8", errors="replace"))
        if target is None:
            break
        current = target
    return bodies


def build_request_plan(plan: str, companies: str) -> list[tuple[str, str]]:
    if plan == "base":
        return [("base_no_company", f"{ENTRY}?id={PROVIDER_MATCH_ID}")]
    return [(f"company_{cid}",
             f"{ENTRY}?{urlencode({'companyid': cid, 'id': PROVIDER_MATCH_ID})}")
            for cid in [c.strip() for c in companies.split(",") if c.strip()]]
