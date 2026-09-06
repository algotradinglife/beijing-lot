"""Offline HTTP adapter tests for bounded immutable fundamentals capture."""
import base64
import json

import pytest
import requests

from src.fundamentals_capture import MAX_BYTES, capture_documents


class Response:
    def __init__(self, status=200, raw=b"ok", url="https://live.nowscore.com/analysis/1cn.html"):
        self.status_code = status
        self.raw = raw
        self.url = url
        self.headers = {"content-type": "text/html; charset=UTF-8"}
        self.closed = False

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.raw

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        from datetime import datetime, timezone
        self.value = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        self.seconds = 0.0
        self.sleeps = []

    def now(self):
        from datetime import timedelta
        value = self.value + timedelta(seconds=self.seconds)
        self.seconds += 0.1
        return value

    def monotonic(self):
        return self.seconds

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.seconds += seconds


def test_success_retry_rate_limit_original_bytes_and_immutability(tmp_path):
    clock = Clock()
    responses = [Response(503, b"busy"), Response(200, b"first"),
                 Response(200, b"second", "https://zq.titan007.com/analysis/1cn.htm")]
    response_refs = list(responses)
    seen = []

    def fetch(url, timeout, stream):
        seen.append((url, timeout, stream))
        return responses.pop(0)

    documents = [
        {"source": "nowscore", "url": "https://live.nowscore.com/analysis/1cn.html", "filename": "nowscore-1.json"},
        {"source": "titan", "url": "https://zq.titan007.com/analysis/1cn.htm", "filename": "titan-1.json"},
    ]
    output = tmp_path / "capture"
    manifest = capture_documents(documents, output, fetch=fetch, clock=clock.now,
                                 monotonic=clock.monotonic, sleeper=clock.sleep,
                                 source_intervals={"nowscore": 2, "titan": 3, "independent": 1})
    assert manifest["documents"][0]["attempts"] == 2
    assert manifest["documents"][0]["state"] == "HTTP_OK"
    assert len(clock.sleeps) == 1 and clock.sleeps[0] > 1.8
    receipt = json.loads((output / "nowscore-1.json").read_text())
    assert base64.b64decode(receipt["body_base64"]) == b"first"
    assert [row["status"] for row in receipt["attempt_receipts"]] == [503, 200]
    assert base64.b64decode(receipt["attempt_receipts"][0]["body_base64"]) == b"busy"
    assert all(response.closed for response in response_refs)
    assert seen[0][1:] == (20, True)
    with pytest.raises(FileExistsError):
        capture_documents(documents, output, fetch=fetch)


def test_transport_failure_is_evidence_and_batch_continues(tmp_path):
    clock = Clock()
    calls = 0

    def fetch(url, timeout, stream):
        nonlocal calls
        del timeout, stream
        calls += 1
        if "nowscore" in url:
            raise requests.Timeout("bounded timeout")
        return Response(url=url)

    output = tmp_path / "capture"
    manifest = capture_documents([
        {"source": "nowscore", "url": "https://live.nowscore.com/analysis/1cn.html", "filename": "nowscore.json"},
        {"source": "titan", "url": "https://zq.titan007.com/analysis/1cn.htm", "filename": "titan.json"},
    ], output, fetch=fetch, max_attempts=2, source_intervals={"nowscore": 0, "titan": 0},
       clock=clock.now, monotonic=clock.monotonic, sleeper=clock.sleep)
    assert calls == 3
    assert [row["state"] for row in manifest["documents"]] == ["TRANSPORT_FAILURE", "HTTP_OK"]
    failure = json.loads((output / "nowscore.json").read_text())
    assert failure["attempts"] == 2 and "body_base64" not in failure
    assert "Timeout" in failure["error"]
    assert len(failure["attempt_receipts"]) == 2
    assert all("Timeout" in row["error"] for row in failure["attempt_receipts"])


@pytest.mark.parametrize("document", [
    {"source": "bad", "url": "https://example.org", "filename": "x.json"},
    {"source": "nowscore", "url": "http://live.nowscore.com/x", "filename": "x.json"},
    {"source": "titan", "url": "https://live.nowscore.com/x", "filename": "x.json"},
    {"source": "independent", "url": "https://user:pass@example.org/x", "filename": "x.json"},
    {"source": "independent", "url": "https://example.org/x", "filename": "../x.json"},
    {"source": "independent", "url": "https://example.org/x", "filename": "capture-manifest.json"},
])
def test_invalid_capture_contract_rolls_back(tmp_path, document):
    output = tmp_path / "capture"
    with pytest.raises(ValueError):
        capture_documents([document], output, fetch=lambda *args, **kwargs: None)
    assert not output.exists()


def test_size_and_clock_fail_closed_without_partial_publish(tmp_path):
    clock = Clock()
    output = tmp_path / "capture"
    with pytest.raises(ValueError, match="10 MiB"):
        capture_documents([{"source": "independent", "url": "https://example.org/report", "filename": "report.json"}],
                          output, fetch=lambda *args, **kwargs: Response(raw=b"x" * (MAX_BYTES + 1), url="https://example.org/report"),
                          clock=clock.now, monotonic=clock.monotonic, sleeper=clock.sleep)
    assert not output.exists()
    assert not list(tmp_path.glob(".fundamentals-capture-*"))


@pytest.mark.parametrize("kwargs", [
    {"max_attempts": 0}, {"max_attempts": 6}, {"timeout_seconds": 0}, {"timeout_seconds": 61},
    {"source_intervals": {"unknown": 1}}, {"source_intervals": {"titan": -1}},
])
def test_invalid_batch_options(tmp_path, kwargs):
    document = {"source": "independent", "url": "https://example.org/report", "filename": "report.json"}
    with pytest.raises(ValueError):
        capture_documents([document], tmp_path / "capture", fetch=lambda *args, **kw: None, **kwargs)
