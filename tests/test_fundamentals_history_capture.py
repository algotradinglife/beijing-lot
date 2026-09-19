"""Budget reservations survive failures and process-local state loss."""
import fcntl
import sqlite3

import pytest
import requests

from src.fundamentals_history_capture import capture_history_batch


@pytest.fixture
def doc():
    return {"source": "nowscore", "url": "https://live.nowscore.com/analysis/844632cn.html", "filename": "index.json"}


class Response:
    status_code = 200
    content = b"index"
    url = "https://live.nowscore.com/analysis/844632cn.html"
    headers = {}

    def close(self):
        pass


def test_restart_budget_and_source_clock_across_budgets(tmp_path, doc):
    ledger = tmp_path / "ledger.db"
    stamp = [100.0]
    calls = []

    def sleep(seconds):
        stamp[0] += seconds

    def fetch(*args, **kwargs):
        calls.append(stamp[0])
        return Response()

    for index, budget in enumerate(["a", "a", "b"]):
        capture_history_batch([doc], tmp_path / str(index), ledger_path=ledger,
                              budget_id=budget, request_budget=2, fetch=fetch,
                              wall_clock=lambda: stamp[0], sleeper=sleep)
    assert calls == [100.0, 105.0, 110.0]
    with pytest.raises(ValueError, match="exhausted"):
        capture_history_batch([doc], tmp_path / "exhausted", ledger_path=ledger,
                              budget_id="a", request_budget=2, fetch=fetch)
    assert len(calls) == 3
    with pytest.raises(ValueError, match="policy"):
        capture_history_batch([doc], tmp_path / "changed", ledger_path=ledger,
                              budget_id="a", request_budget=3, fetch=fetch)


def test_failure_consumes_budget_and_releases_lock(tmp_path, doc):
    ledger = tmp_path / "ledger.db"

    def failed(*args, **kwargs):
        raise requests.Timeout("test timeout")

    result = capture_history_batch([doc], tmp_path / "failed", ledger_path=ledger,
                                   budget_id="a", request_budget=1, fetch=failed)
    assert result["documents"][0]["state"] == "TRANSPORT_FAILURE"
    with pytest.raises(ValueError, match="exhausted"):
        capture_history_batch([doc], tmp_path / "retry", ledger_path=ledger,
                              budget_id="a", request_budget=1, fetch=failed)
    with sqlite3.connect(ledger) as con:
        assert con.execute("SELECT used FROM budgets").fetchone() == (1,)


def test_unexpected_failure_also_consumes_reservation(tmp_path, doc):
    def crash(*args, **kwargs):
        raise RuntimeError("simulated crash")
    ledger = tmp_path / "ledger.db"
    with pytest.raises(RuntimeError):
        capture_history_batch([doc], tmp_path / "crash", ledger_path=ledger,
                              budget_id="a", request_budget=1, fetch=crash)
    with pytest.raises(ValueError, match="exhausted"):
        capture_history_batch([doc], tmp_path / "retry", ledger_path=ledger,
                              budget_id="a", request_budget=1, fetch=crash)


def test_concurrency_rejected(tmp_path, doc):
    ledger = tmp_path / "ledger.db"
    with (tmp_path / "ledger.db.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            capture_history_batch([doc], tmp_path / "blocked", ledger_path=ledger,
                                  budget_id="a", request_budget=1)
    assert not ledger.exists()


def test_backwards_clock_and_short_wait_fail_closed(tmp_path, doc):
    ledger = tmp_path / "ledger.db"
    capture_history_batch([doc], tmp_path / "first", ledger_path=ledger,
                          budget_id="a", request_budget=3, wall_clock=lambda: 100,
                          fetch=lambda *a, **kw: Response())
    for stamp, message in [(99, "backwards"), (100, "wait"), (float("nan"), "clock")]:
        with pytest.raises(ValueError, match=message):
            capture_history_batch([doc], tmp_path / "bad", ledger_path=ledger,
                                  budget_id="a", request_budget=3,
                                  wall_clock=lambda: stamp, sleeper=lambda s: None)
    with sqlite3.connect(ledger) as con:
        assert con.execute("SELECT used FROM budgets").fetchone() == (1,)


@pytest.mark.parametrize("kwargs", [{"budget_id": " "}, {"request_budget": True},
    {"request_budget": 0}, {"min_interval_seconds": 0.9}, {"min_interval_seconds": float("nan")}])
def test_invalid_policy_rejected_before_io(tmp_path, doc, kwargs):
    policy = {"budget_id": "a", "request_budget": 1, **kwargs}
    with pytest.raises(ValueError):
        capture_history_batch([doc], tmp_path / "out", ledger_path=tmp_path / "ledger", **policy)
    assert list(tmp_path.iterdir()) == []


def test_invalid_input_and_existing_output(tmp_path, doc):
    for docs in ([], [{**doc, "source": "independent"}], [{**doc, "url": "https://example.org"}]):
        with pytest.raises(ValueError):
            capture_history_batch(docs, tmp_path / "out", ledger_path=tmp_path / "ledger",
                                  budget_id="a", request_budget=1)
    with pytest.raises(FileExistsError):
        capture_history_batch([doc], tmp_path, ledger_path=tmp_path / "ledger",
                              budget_id="a", request_budget=1)


def test_two_seconds_new_policy_preserves_old_budget(tmp_path, doc):
    stamp = [100.0]
    calls = []
    def sleep(seconds):
        stamp[0] += seconds
    def fetch(*args, **kwargs):
        calls.append(stamp[0])
        return Response()
    ledger = tmp_path / 'ledger'
    for index, interval in enumerate((5, 2, 2, 5)):
        capture_history_batch([doc], tmp_path / str(index), ledger_path=ledger,
            budget_id=str(interval), request_budget=2, min_interval_seconds=interval,
            wall_clock=lambda: stamp[0], sleeper=sleep, fetch=fetch)
    assert calls == [100, 105, 107, 109]
    with pytest.raises(ValueError, match='policy'):
        capture_history_batch([doc], tmp_path / 'bad', ledger_path=ledger,
            budget_id='5', request_budget=2, min_interval_seconds=2)

def test_one_second_budget_preserves_old_policy(tmp_path, doc):
    stamp = [100.0]
    calls = []
    def sleep(seconds):
        stamp[0] += seconds
    def fetch(*args, **kwargs):
        calls.append(stamp[0])
        return Response()
    ledger = tmp_path / "ledger"
    for index, interval in enumerate((2, 1, 1, 2)):
        capture_history_batch([doc], tmp_path / str(index), ledger_path=ledger,
            budget_id=str(interval), request_budget=2, min_interval_seconds=interval,
            wall_clock=lambda: stamp[0], sleeper=sleep, fetch=fetch)
    assert calls == [100, 102, 103, 104]
    with pytest.raises(ValueError, match="policy"):
        capture_history_batch([doc], tmp_path / "bad", ledger_path=ledger,
            budget_id="2", request_budget=2, min_interval_seconds=1)


def test_nowscore_euro_endpoint_uses_shared_nowscore_rate_key():
    from src.fundamentals_history_capture import capture_rate_source
    assert capture_rate_source({'source':'nowscore','url':'https://1x2.nowscore.com/547279.js'}) == 'nowscore'
    import pytest
    with pytest.raises(ValueError):
        capture_rate_source({'source':'titan','url':'https://1x2.nowscore.com/547279.js'})


def test_queued_lock_waits_without_spending_request(tmp_path, doc):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    ledger=tmp_path/'queued.sqlite'
    started=Event()
    def capture():
        started.set()
        return capture_history_batch([doc],tmp_path/'queued',ledger_path=ledger,
            budget_id='queue',request_budget=1,wait_for_lock=True,fetch=lambda *a,**k:Response())
    with ledger.with_suffix('.sqlite.lock').open('a+b') as lock, ThreadPoolExecutor(max_workers=1) as executor:
        fcntl.flock(lock,fcntl.LOCK_EX)
        future=executor.submit(capture)
        try:
            assert started.wait(2)
            assert not future.done()
            assert not (tmp_path/'queued').exists()
        finally:
            fcntl.flock(lock,fcntl.LOCK_UN)
        assert future.result(timeout=5)['documents'][0]['state']=='HTTP_OK'
    with sqlite3.connect(ledger) as con:
        assert con.execute('select used from budgets').fetchone()[0]==1
