"""Offline tests for the bounded #493 Nowscore 3in1 probe primitives.

No network access: redirect chains, the clock and the response bodies are injected.
Every test asserts observable behaviour of src/n7_493_probe.py.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import n7_493_probe as probe  # noqa: E402

BASE = probe.ENTRY + "?id=" + probe.PROVIDER_MATCH_ID


class StubResponse:
    def __init__(self, status_code, body=b"", location=None, chunks=None):
        self.status_code = status_code
        self.content = body
        self.headers = {"Location": location} if location else {}
        self._chunks = chunks

    def iter_content(self, size):
        if self._chunks is None:
            yield self.content
        else:
            for chunk in self._chunks:
                yield chunk


class StubSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.timeouts = []

    def get(self, url, headers=None, timeout=None, allow_redirects=None,
            stream=None):
        assert allow_redirects is False, "auto-redirects would hide hop accounting"
        assert stream is True, "the deadline needs a streamed body"
        self.calls.append(url)
        self.timeouts.append(timeout)
        if not self.responses:
            raise AssertionError("stub session ran out of scripted responses")
        return self.responses.pop(0)


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def reservation(started=1000.0, attempt_id="r"):
    return {"kind": probe.RESERVATION, "attempt_id": attempt_id,
            "started_epoch": started, "started_at": probe.iso_from_epoch(started)}


def outcome(started=1000.0, ended=1000.5, attempt_id="r"):
    return {"kind": probe.OUTCOME, "attempt_id": attempt_id,
            "started_epoch": started, "ended_epoch": ended}


def seed(root, records):
    for record in records:
        probe.append_ledger(root / probe.LEDGER_NAME, record)


def resolved_attempts(count, start=1000.0, prefix="p"):
    """Attempts that both reserved and completed, so they count as resolved."""
    records = []
    for i in range(count):
        at = start + i
        records.append(reservation(started=at, attempt_id=f"{prefix}{i}"))
        records.append(outcome(started=at, ended=at + 0.5, attempt_id=f"{prefix}{i}"))
    return records


def budget_for(root, clock):
    return probe.Budget(probe.load_ledger(root / probe.LEDGER_NAME), clock=clock)


def recorder_for(root, jar="jar"):
    return probe.Recorder(root, jar)


# --- accounting contract ------------------------------------------------------

def test_missing_ledger_is_empty(tmp_path):
    assert probe.load_ledger(tmp_path / "nope.jsonl") == []


def test_a_redirect_makes_hop_attempts_exceed_top_level_requests(tmp_path):
    """The two counts are different quantities and must not be conflated.

    A reservation is written once per hop, so a single request answered by a
    redirect consumes two hop attempts while remaining one top-level request.
    Reporting the hop count as the request count would overstate it, which is
    exactly why the delivered ledger's hop total stays UNVERIFIED.
    """
    recorder = recorder_for(tmp_path)

    class RedirectingSession:
        def __init__(self):
            self.calls = 0

        def get(self, *a, **k):
            self.calls += 1
            if self.calls == 1:
                # Same fixture, different path, so the hop target is in scope
                # and genuinely differs from the current URL.
                return StubResponse(
                    302, b"",
                    location=f"https://live.nowscore.com/odds/moved.aspx"
                             f"?id={probe.PROVIDER_MATCH_ID}")
            return StubResponse(200, b"<html>ok</html>")

        def close(self):
            pass

    # A frozen clock would give both reservations the same attempt id, collapsing
    # them into one attempt and hiding the hop/request difference under test.
    state = {"t": 1000.0}

    def ticking():
        state["t"] += 0.5
        return state["t"]

    probe.fetch_with_hops(RedirectingSession(), BASE, recorder,
                          "base", tmp_path, clock=ticking)
    ledger = probe.load_ledger(recorder.ledger_path)
    # One logical request issued, two network round trips reserved.
    assert probe.count_top_level_requests(ledger) == 1
    assert probe.count_attempts(ledger) == 2
    # And the two are genuinely different numbers, which is the whole point.
    assert probe.count_top_level_requests(ledger) != probe.count_attempts(ledger)


def test_repeated_labels_are_counted_as_separate_requests(tmp_path):
    """Two dispatches sharing one label are two requests, not one.

    build_request_plan returns one entry per requested company, so the supported
    --companies 1,1 plan issues the same label twice. Counting distinct labels
    would report one request where two were made.
    """
    recorder = recorder_for(tmp_path)

    class OkSession:
        def get(self, *a, **k):
            return StubResponse(200, b"<html>ok</html>")

        def close(self):
            pass

    state = {"t": 1000.0}

    def ticking():
        state["t"] += 0.5
        return state["t"]

    plan = probe.build_request_plan("follow", "1,1")
    assert [label for label, _ in plan] == ["company_1", "company_1"]
    for label, url in plan:
        probe.fetch_with_hops(OkSession(), url, recorder, label, tmp_path,
                              clock=ticking)
    ledger = probe.load_ledger(recorder.ledger_path)
    assert probe.count_top_level_requests(ledger) == 2
    assert probe.count_attempts(ledger) == 2

def test_the_reconstructed_ledger_cannot_yield_a_request_count():
    """The delivered ledger has no hop-0 outcome, so no request count is derivable.

    Reporting 3 here would repeat the very conflation this counter exists to
    prevent: 3 surviving outcomes say nothing about hops or requests issued.
    """
    delivered = ROOT / "results/data_collection/n7_493_3in1_probe_v1/requests.jsonl"
    if not delivered.exists():
        pytest.skip("delivered ledger not present")
    assert probe.count_top_level_requests(probe.load_ledger(delivered)) == 0


def test_outcomes_do_not_inflate_the_attempt_count(tmp_path):
    seed(tmp_path, [reservation(attempt_id="a"), outcome(attempt_id="a"),
                    reservation(started=1001.0, attempt_id="b"),
                    outcome(started=1001.0, attempt_id="b")])
    assert budget_for(tmp_path, FakeClock(1001.0)).attempts == 2


def test_a_reconstructed_outcome_only_ledger_is_rejected(tmp_path):
    """The delivered ledger is historical evidence, not a dispatchable ledger."""
    seed(tmp_path, [{"kind": probe.OUTCOME, "attempt_id": "reconstructed-a",
                     "started_epoch": 1000.0, "ended_epoch": 1000.1}])
    with pytest.raises(probe.LedgerContractError, match="no reservation"):
        budget_for(tmp_path, FakeClock(1000.0))


def test_the_delivered_ledger_fails_closed():
    delivered = ROOT / "results/data_collection/n7_493_3in1_probe_v1/requests.jsonl"
    if not delivered.exists():
        pytest.skip("delivered ledger not present")
    ledger = probe.load_ledger(delivered)
    assert ledger, "delivered ledger should not be empty"
    with pytest.raises(probe.LedgerContractError):
        probe.Budget(ledger)


def test_unknown_record_kind_is_rejected(tmp_path):
    seed(tmp_path, [{"kind": "guess", "attempt_id": "x"}])
    with pytest.raises(probe.LedgerContractError, match="unknown ledger record kinds"):
        budget_for(tmp_path, FakeClock(1000.0))


def test_record_without_attempt_id_is_rejected(tmp_path):
    seed(tmp_path, [{"kind": probe.RESERVATION}])
    with pytest.raises(probe.LedgerContractError, match="attempt_id"):
        budget_for(tmp_path, FakeClock(1000.0))


# --- reservations, interruption, cross-process --------------------------------

def test_prior_reservations_from_another_process_are_counted(tmp_path):
    seed(tmp_path, resolved_attempts(9))
    budget = budget_for(tmp_path, FakeClock(1009.0))
    assert budget.remaining_attempts() == 1
    assert budget.blocked() is None


def test_an_unresolved_reservation_blocks_further_dispatch(tmp_path):
    """An interrupted attempt consumed its slot but produced no timing."""
    seed(tmp_path, [reservation(started=1000.0, attempt_id="lost")])
    budget = budget_for(tmp_path, FakeClock(1000.1))
    assert budget.blocked() == "UNRESOLVED_ATTEMPT"


def test_reservation_is_written_before_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    recorder = recorder_for(tmp_path)

    class BoomSession:
        def get(self, *a, **k):
            raise probe.requests.Timeout("simulated")

    probe.fetch_with_hops(BoomSession(), BASE, recorder, "base", tmp_path,
                          clock=FakeClock())
    records = probe.load_ledger(recorder.ledger_path)
    kinds = [r["kind"] for r in records]
    assert kinds == [probe.RESERVATION, probe.OUTCOME]


# --- concurrency --------------------------------------------------------------

def test_concurrent_processes_cannot_double_spend(tmp_path, monkeypatch):
    """Two probes racing on one ledger must not both take the last slot."""
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    seed(tmp_path, resolved_attempts(9))
    clock = FakeClock(1009.0)
    started, errors = [], []

    class SlowSession:
        def get(self, url, headers=None, timeout=None, allow_redirects=None,
            stream=None):
            started.append(clock.now)
            clock.advance(0.1)
            return StubResponse(200, b"ok")

    def run():
        try:
            probe.fetch_with_hops(SlowSession(), BASE, recorder_for(tmp_path),
                                  "base", tmp_path, clock=clock)
        except Exception as exc:  # pragma: no cover - diagnostic only
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    reservations = [r for r in probe.load_ledger(tmp_path / probe.LEDGER_NAME)
                    if r["kind"] == probe.RESERVATION]
    assert len(reservations) == probe.MAX_ATTEMPTS, (
        f"budget exceeded under concurrency: {len(reservations)}")
    assert len(started) == 1, "only one slot was free, so only one request may start"


def test_the_lock_excludes_concurrent_critical_sections(tmp_path, monkeypatch):
    """Two workers must never occupy the ledger critical section together.

    The critical section is instrumented directly, so the assertion detects the
    absence of the lock (verified by mutation) rather than merely observing that
    no second request happened. A second, independent protection also exists:
    an unresolved reservation blocks any later dispatch (see
    test_an_unresolved_reservation_blocks_dispatch).
    """
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    clock = FakeClock(1000.0)
    inside = []
    peak = []
    release = threading.Event()
    original = probe._dispatch_hop

    def instrumented(*args, **kwargs):
        inside.append(1)
        peak.append(len(inside))
        try:
            release.wait(0.5)          # hold the critical section open
            return original(*args, **kwargs)
        finally:
            inside.pop()

    monkeypatch.setattr(probe, "_dispatch_hop", instrumented)

    def run():
        try:
            probe.fetch_with_hops(StubSession([StubResponse(200, b"a"),
                                               StubResponse(200, b"b")]),
                                  BASE, recorder_for(tmp_path), "base",
                                  tmp_path, clock=clock)
        except Exception:
            pass

    first = threading.Thread(target=run, daemon=True)
    first.start()
    release.wait(0.15)                 # let the first worker enter
    second = threading.Thread(target=run, daemon=True)
    second.start()
    release.wait(0.3)                  # a real window for the second to enter
    observed_peak = max(peak) if peak else 0
    release.set()
    first.join(10.0)
    second.join(10.0)
    assert observed_peak == 1, (
        f"{observed_peak} workers occupied the critical section at once")


def test_the_lock_lets_every_contender_finish(tmp_path, monkeypatch):
    """Exclusion must not deadlock the contenders that lose the race."""
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    seed(tmp_path, resolved_attempts(4))
    clock = FakeClock(1000.0)
    started = []
    gate = threading.Barrier(3)

    class CountingSession:
        def get(self, url, headers=None, timeout=None, allow_redirects=None,
                stream=None):
            started.append(clock.now)
            return StubResponse(200, b"ok")

    def run():
        gate.wait(5.0)
        probe.fetch_with_hops(CountingSession(), BASE, recorder_for(tmp_path),
                              "base", tmp_path, clock=clock)

    threads = [threading.Thread(target=run, daemon=True) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10.0)
    assert all(not thread.is_alive() for thread in threads), "a contender deadlocked"
    assert len(started) == 3, "each contender should have used one spare slot"


# --- wall clock ---------------------------------------------------------------

def test_fresh_budget_starts_with_the_full_window(tmp_path):
    budget = budget_for(tmp_path, FakeClock(1000.0))
    assert budget.blocked() is None
    assert budget.remaining_wall() == probe.MAX_WALL_SEC


def test_deadline_is_persisted_from_the_first_reservation(tmp_path):
    clock = FakeClock(1000.0)
    budget = budget_for(tmp_path, clock)
    budget.reserve()
    assert budget.deadline == 1000.0 + probe.MAX_WALL_SEC
    clock.advance(probe.MAX_WALL_SEC + 0.1)
    assert budget.blocked() == "MAX_WALL_SEC"
    assert budget.remaining_wall() == 0


def test_deadline_spans_processes(tmp_path):
    seed(tmp_path, [reservation(started=1000.0)])
    clock = FakeClock(1000.0 + probe.MAX_WALL_SEC + 1)
    assert budget_for(tmp_path, clock).blocked() == "MAX_WALL_SEC"


def test_request_timeout_never_exceeds_the_remaining_window(tmp_path):
    seed(tmp_path, [reservation(started=1000.0)])
    clock = FakeClock(1000.0 + probe.MAX_WALL_SEC - 3.0)
    budget = budget_for(tmp_path, clock)
    assert budget.request_timeout() == pytest.approx(3.0)
    clock.advance(probe.MAX_WALL_SEC)
    assert budget.request_timeout() < probe.TIMEOUT_SEC


def test_hop_loop_rechecks_the_deadline_after_waiting(tmp_path, monkeypatch):
    """The spacing sleep itself can cross the deadline; that must be rechecked.

    The clock starts BEFORE the deadline and before the required spacing, so the
    initial check passes and only the post-wait recheck can stop the dispatch.
    Removing the recheck makes this test fail (verified by mutation).
    """
    clock = FakeClock(1000.2)
    seed(tmp_path, [reservation(started=1000.0, attempt_id="seed"),
                    outcome(started=1000.0, ended=1000.1, attempt_id="seed")])
    monkeypatch.setattr(probe, "MAX_WALL_SEC", 1.0)      # deadline = 1001.0
    monkeypatch.setattr(probe.time, "sleep", lambda s: clock.advance(s))
    session = StubSession([StubResponse(200, b"x")])
    probe.fetch_with_hops(session, BASE, recorder_for(tmp_path), "base", tmp_path,
                          clock=clock)
    assert clock.now > 1001.0, "the spacing wait should have crossed the deadline"
    assert session.calls == [], "no request may be issued past the deadline"


def test_a_blocking_close_does_not_extend_the_callers_deadline():
    """Cleanup must stay off the deadline path."""
    release = threading.Event()

    class BlockingCloseSession:
        def get(self, *a, **k):
            release.wait(30.0)
            return StubResponse(200, b"late")

        def close(self):
            release.wait(30.0)          # a close() that blocks indefinitely

    session = BlockingCloseSession()
    started = time.time()
    with pytest.raises(probe.DeadlineExceeded):
        probe.request_under_deadline(session, BASE, deadline=started + 0.3,
                                     timeout=20.0)
    elapsed = time.time() - started
    assert elapsed < 2.0, f"a blocking close() extended the deadline ({elapsed:.1f}s)"
    release.set()


def test_close_quietly_swallows_a_failing_close():
    class Bad:
        def close(self):
            raise RuntimeError("already gone")

    probe.close_quietly(Bad())          # must not raise


def test_a_trickling_body_is_cut_off_at_the_deadline(tmp_path, monkeypatch):
    """A scalar socket timeout does not bound the total response duration."""
    clock = FakeClock(1000.0)
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)

    class Trickle:
        status_code = 200
        headers: dict = {}
        content = b""

        def iter_content(self, size):
            for _ in range(100):
                clock.advance(5.0)          # keeps supplying data forever
                yield b"x" * size

    class TrickleSession:
        def get(self, *a, **k):
            return Trickle()

    probe.fetch_with_hops(TrickleSession(), BASE, recorder_for(tmp_path),
                          "base", tmp_path, clock=clock)
    record = [r for r in probe.load_ledger(tmp_path / probe.LEDGER_NAME)
              if r["kind"] == probe.OUTCOME][0]
    assert "DeadlineExceeded" in (record["error"] or "")
    assert record["raw_file"] is None, "a truncated body must not be stored"


def test_consume_body_refuses_once_the_deadline_has_passed():
    clock = FakeClock(1000.0)

    class Response:
        content = b"late"
        status_code = 200
        headers: dict = {}

        def iter_content(self, size):
            yield b"late"

    with pytest.raises(probe.DeadlineExceeded):
        probe.consume_body(Response(), deadline=999.0, clock=clock)


# --- serial interval ----------------------------------------------------------

def test_interval_uses_subsecond_precision(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr(probe.time, "sleep", lambda s: slept.append(s))
    clock = FakeClock(1000.0)
    budget = budget_for(tmp_path, clock)
    budget.reserve()
    budget.last_end = 1000.9
    clock.advance(0.9)
    budget.wait()
    assert slept and slept[0] == pytest.approx(2.0, abs=0.01)
    truncated_end = float(int(1000.9))
    assert probe.MIN_INTERVAL_SEC - (clock.now - truncated_end) == pytest.approx(
        1.1, abs=0.01)


def test_interval_is_satisfied_end_to_end(tmp_path, monkeypatch):
    slept = []
    clock = FakeClock(1000.0)
    monkeypatch.setattr(probe.time, "sleep",
                        lambda s: (slept.append(s), clock.advance(s)))
    recorder = recorder_for(tmp_path)
    session = StubSession([StubResponse(200, b"a"), StubResponse(200, b"b")])
    for _ in range(2):
        probe.fetch_with_hops(session, BASE, recorder, "base", tmp_path, clock=clock)
    outcomes = [r for r in probe.load_ledger(recorder.ledger_path)
                if r["kind"] == probe.OUTCOME]
    assert len(outcomes) == 2
    gap = outcomes[1]["started_epoch"] - outcomes[0]["ended_epoch"]
    assert gap >= probe.MIN_INTERVAL_SEC - 1e-9, f"interval violated: {gap}"


# --- redirect scope -----------------------------------------------------------

def test_redirect_within_the_authorised_source_is_followed(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    recorder = recorder_for(tmp_path)
    session = StubSession([
        StubResponse(302, b"", location="/odds/3in1Odds.aspx?id=3061587"),
        StubResponse(200, b"final"),
    ])
    bodies = probe.fetch_with_hops(session, BASE, recorder, "base", tmp_path,
                                   clock=FakeClock())
    assert len(bodies) == 2
    assert len([r for r in probe.load_ledger(recorder.ledger_path)
                if r["kind"] == probe.RESERVATION]) == 2


def test_redirect_to_another_host_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    recorder = recorder_for(tmp_path)
    session = StubSession([StubResponse(302, b"", location="https://evil.example/x")])
    probe.fetch_with_hops(session, BASE, recorder, "base", tmp_path, clock=FakeClock())
    assert len(session.calls) == 1
    record = [r for r in probe.load_ledger(recorder.ledger_path)
              if r["kind"] == probe.OUTCOME][0]
    assert record["rejected_redirect"] == "https://evil.example/x"
    assert record["redirect_to"] is None


def test_redirect_to_another_fixture_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    session = StubSession([StubResponse(302, b"", location="/odds/3in1Odds.aspx?id=999")])
    probe.fetch_with_hops(session, BASE, recorder_for(tmp_path), "base", tmp_path,
                          clock=FakeClock())
    assert len(session.calls) == 1


def test_out_of_scope_start_url_is_refused():
    with pytest.raises(probe.ScopeViolation):
        probe.assert_in_scope("https://other.example/x?id=3061587")
    with pytest.raises(probe.ScopeViolation):
        probe.assert_in_scope(probe.ENTRY + "?id=1")


# --- immutable raw bodies -----------------------------------------------------

def test_repeated_runs_do_not_overwrite_raw_bodies(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    recorder = recorder_for(tmp_path)
    for body in (b"first", b"second"):
        probe.fetch_with_hops(StubSession([StubResponse(200, body)]), BASE,
                              recorder, "base", tmp_path, clock=FakeClock())
    raw = sorted((tmp_path / "raw").glob("base_*.html"))
    assert len(raw) == 2
    assert sorted(p.read_bytes() for p in raw) == [b"first", b"second"]


# --- hop bounds, errors, plan, hygiene ----------------------------------------

def test_max_hops_bounds_a_redirect_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    session = StubSession([StubResponse(302, b"", location=BASE)] * 10)
    probe.fetch_with_hops(session, BASE, recorder_for(tmp_path), "base", tmp_path,
                          max_hops=3, clock=FakeClock())
    assert len(session.calls) == 3


def test_hop_loop_stops_at_the_attempt_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    seed(tmp_path, resolved_attempts(probe.MAX_ATTEMPTS - 2))
    session = StubSession([StubResponse(302, b"", location=BASE)] * 5)
    probe.fetch_with_hops(session, BASE, recorder_for(tmp_path), "base", tmp_path,
                          clock=FakeClock(1000.0))
    assert len(session.calls) == 2


def test_network_error_is_recorded_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)

    class BoomSession:
        def get(self, *a, **k):
            raise probe.requests.Timeout("simulated")

    recorder = recorder_for(tmp_path)
    probe.fetch_with_hops(BoomSession(), BASE, recorder, "base", tmp_path,
                          clock=FakeClock())
    record = [r for r in probe.load_ledger(recorder.ledger_path)
              if r["kind"] == probe.OUTCOME][0]
    assert record["http_status"] is None and "Timeout" in record["error"]


def test_a_programming_error_is_not_disguised_as_a_network_failure(tmp_path,
                                                                  monkeypatch):
    """Only transport failures may be recorded; bugs must surface."""
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)

    class BuggySession:
        def get(self, *a, **k):
            raise TypeError("stub signature drift")

    with pytest.raises(TypeError):
        probe.fetch_with_hops(BuggySession(), BASE, recorder_for(tmp_path),
                              "base", tmp_path, clock=FakeClock())


def test_request_plan_targets_the_approved_fixture():
    assert probe.build_request_plan("base", "") == [("base_no_company", BASE)]


def test_request_plan_encodes_company_ids():
    plan = probe.build_request_plan("follow", "1,0")
    assert [label for label, _ in plan] == ["company_1", "company_0"]
    assert "companyid=1" in plan[0][1] and "id=3061587" in plan[0][1]


def test_ledger_persists_only_an_anonymous_jar_id(tmp_path, monkeypatch):
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    recorder = recorder_for(tmp_path, "anonjar123")
    probe.fetch_with_hops(StubSession([StubResponse(200, b"ok")]), BASE, recorder,
                          "base", tmp_path, clock=FakeClock())
    records = probe.load_ledger(recorder.ledger_path)
    cookie_keys = {k for r in records for k in r if "cookie" in k.lower()}
    assert cookie_keys == {"cookie_jar_id"}
    assert all(r["cookie_jar_id"] == "anonjar123"
               for r in records if r["kind"] == probe.OUTCOME)
    assert all("cookie_jar_id" not in r
               for r in records if r["kind"] == probe.RESERVATION)
    serialised = (tmp_path / probe.LEDGER_NAME).read_text()
    assert "Cookie" not in serialised and "Set-Cookie" not in serialised
    outcome = [r for r in records if r["kind"] == probe.OUTCOME][0]
    assert outcome["sha256"] == probe.hashlib.sha256(b"ok").hexdigest()


# --- round-12 findings: cancellable deadline, attempt counting, sessions -----


class _StalledResponse:
    """A response whose read blocks until something closes it."""

    def __init__(self):
        self._released = threading.Event()
        self.closed = False

    def iter_content(self, chunk_size):
        self._released.wait(10.0)   # simulates a stalled transport read
        return iter(())

    def close(self):
        self.closed = True
        self._released.set()


def test_watchdog_releases_a_stalled_read_at_the_deadline():
    """A chunk-boundary check alone cannot bound a blocked read."""
    response = _StalledResponse()
    started = time.time()
    with pytest.raises(probe.DeadlineExceeded):
        probe.consume_body(response, deadline=started + 0.3)
    elapsed = time.time() - started
    assert response.closed, "the watchdog must close the response"
    assert elapsed < 3.0, f"watchdog did not release the read (took {elapsed:.1f}s)"


def test_watchdog_returns_a_normal_streamed_body_and_closes_it():
    class _Streamed:
        def __init__(self):
            self.closed = False

        def iter_content(self, chunk_size):
            yield b"ab"
            yield b"cd"

        def close(self):
            self.closed = True

    response = _Streamed()
    body = probe.consume_body(response, deadline=time.time() + 5.0)
    assert body == b"abcd"
    assert response.closed, "the response must be released even on success"


def test_watchdog_does_not_trip_on_a_body_that_finishes_in_time():
    class _Fast:
        def iter_content(self, chunk_size):
            yield b"x"

        def close(self):
            pass

    assert probe.consume_body(_Fast(), deadline=time.time() + 5.0) == b"x"


def test_count_attempts_counts_reservations_not_records():
    """A reservation/outcome pair is one attempt, not two."""
    ledger = []
    for index in range(3):
        ledger.append({"kind": probe.RESERVATION, "attempt_id": f"a{index}",
                       "label": "x", "reserved_at": "2026-01-01T00:00:00Z"})
    assert probe.count_attempts(ledger) == 3
    with_outcomes = ledger + [
        {"kind": probe.OUTCOME, "attempt_id": f"a{index}", "label": "x",
         "ended_at": "2026-01-01T00:00:01Z"} for index in range(3)]
    assert probe.count_attempts(with_outcomes) == 3


def test_count_historical_attempts_works_on_a_reconstructed_ledger():
    """Reporting must not require a dispatchable ledger."""
    ledger = [{"kind": probe.OUTCOME, "attempt_id": f"a{index}", "label": "x",
               "ended_at": "2026-01-01T00:00:01Z"} for index in range(3)]
    with pytest.raises(probe.LedgerContractError):
        probe.count_attempts(ledger)
    assert probe.count_historical_attempts(ledger) == 3


def test_count_historical_attempts_ignores_records_without_an_attempt_id():
    assert probe.count_historical_attempts(
        [{"kind": probe.OUTCOME, "label": "x"}]) == 0


def test_recorder_jar_identity_is_stable_for_one_recorder(tmp_path):
    """One recorder means one jar identity; the entry point reuses one session."""
    recorder = probe.Recorder(tmp_path, "jar-1")
    assert recorder.jar_id == "jar-1"
    for attempt in ("a1", "a2"):
        probe.append_ledger(recorder.ledger_path, {
            "kind": probe.OUTCOME, "attempt_id": attempt, "label": "x",
            "ended_at": "2026-01-01T00:00:00Z", "cookie_jar_id": recorder.jar_id})
    entries = probe.load_ledger(recorder.ledger_path)
    assert {e["cookie_jar_id"] for e in entries} == {"jar-1"}



def test_caller_returns_at_the_deadline_even_if_close_cannot_interrupt():
    """The caller must never outlive the deadline, whatever the transport does."""
    release = threading.Event()

    class UninterruptibleSession:
        closed = False

        def get(self, *a, **k):
            release.wait(30.0)      # a read that close() does NOT release
            return StubResponse(200, b"late")

        def close(self):
            self.closed = True       # deliberately does not release the read
            closed_event.set()

    closed_event = threading.Event()
    session = UninterruptibleSession()
    started = time.time()
    try:
        with pytest.raises(probe.DeadlineExceeded):
            probe.request_under_deadline(session, BASE, deadline=started + 0.3,
                                         timeout=20.0)
        elapsed = time.time() - started
        # Measure the caller's latency itself; cleanup is asynchronous.
        assert elapsed < 2.0, f"caller outlived the deadline ({elapsed:.1f}s)"
        assert closed_event.wait(5.0), "cleanup never ran"
        assert session.closed
    finally:
        release.set()               # never leave the blocked worker stuck


def test_caller_returns_the_body_when_the_request_finishes_in_time():
    class FastSession:
        def get(self, *a, **k):
            assert k.get("stream") is True
            return StubResponse(200, b"ok")

        def close(self):
            pass

    response, body = probe.request_under_deadline(
        FastSession(), BASE, deadline=time.time() + 5.0, timeout=20.0)
    assert response.status_code == 200 and body == b"ok"


def test_caller_surfaces_a_transport_error_from_the_worker():
    class BoomSession:
        def get(self, *a, **k):
            raise probe.requests.Timeout("simulated")

        def close(self):
            pass

    with pytest.raises(probe.requests.Timeout):
        probe.request_under_deadline(BoomSession(), BASE,
                                     deadline=time.time() + 5.0, timeout=20.0)


def test_deadline_exceeded_is_recorded_when_the_lifecycle_times_out(tmp_path,
                                                                   monkeypatch):
    """A timed-out lifecycle records an outcome and stops the hop loop."""
    monkeypatch.setattr(probe.time, "sleep", lambda _s: None)
    release = threading.Event()

    class HangingSession:
        def get(self, *a, **k):
            release.wait(30.0)
            return StubResponse(200, b"late")

        def close(self):
            pass

    recorder = recorder_for(tmp_path)
    clock = FakeClock()
    # Give the probe a tiny remaining budget so the deadline is imminent.
    monkeypatch.setattr(probe, "MAX_WALL_SEC", 0.3)
    bodies = probe.fetch_with_hops(HangingSession(), BASE, recorder, "base",
                                   tmp_path, clock=time.time)
    release.set()
    assert bodies == []
    record = [r for r in probe.load_ledger(recorder.ledger_path)
              if r["kind"] == probe.OUTCOME][0]
    assert record["http_status"] is None
    assert "DeadlineExceeded" in record["error"]

