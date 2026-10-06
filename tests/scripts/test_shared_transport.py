"""Both live scrapers must fetch through the shared package transport.

These tests assert the delegation contract: the module-level ``fetch_url`` seam
the scrapers' callers patch must reach ``beidan_backend.transport``, and the
scrapers must preserve their historical return shapes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT, ROOT / "scripts", ROOT / "packages/beidan/inst/python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from beidan_backend.transport import FetchResponse  # noqa: E402
from scripts import scrape_500_bjdc as s500  # noqa: E402
from scripts import scrape_nowscore_bjdc as sns  # noqa: E402


def _response(url: str, body: bytes) -> FetchResponse:
    return FetchResponse(
        url=url, status=200, body=body, content_type="text/html",
        observed_at="2026-10-04T00:00:00+00:00", elapsed_sec=0.1, attempts=1)


def test_scrape_500_fetch_url_delegates_and_preserves_result_shape(monkeypatch):
    captured = {}

    def fake(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _response(url, b"<html/>")

    monkeypatch.setattr(s500, "fetch_issue_page", fake)
    result = s500.fetch_url("https://trade.500.com/bjdc/index.php?expect=26098",
                            timeout=12, user_agent="ua", referer="https://trade.500.com/")
    assert captured["url"].endswith("expect=26098")
    assert captured["kwargs"] == {"timeout": 12, "user_agent": "ua", "referer": "https://trade.500.com/"}
    # Historical FetchResult shape is preserved.
    assert isinstance(result, s500.FetchResult)
    assert result.status == 200 and result.body == b"<html/>" and result.elapsed_sec == 0.1


def test_scrape_nowscore_fetch_url_delegates_with_source_headers(monkeypatch):
    captured = {}

    def fake(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _response(url, b"<html/>")

    monkeypatch.setattr(sns, "fetch_issue_page", fake)
    status, payload, elapsed = sns.fetch_url(
        "https://cp.nowscore.com/buy/DanChang.aspx", 20, "ua")
    assert captured["url"] == "https://cp.nowscore.com/buy/DanChang.aspx"
    assert captured["kwargs"]["timeout"] == 20 and captured["kwargs"]["user_agent"] == "ua"
    assert captured["kwargs"]["headers"] == sns.NOWSCORE_HEADERS
    # Historical tuple shape is preserved.
    assert (status, payload, elapsed) == (200, b"<html/>", 0.1)


def test_scrape_500_fetch_url_propagates_transport_failure(monkeypatch):
    from beidan_backend.transport import FetchError

    def boom(url, **kwargs):
        raise FetchError("HTTP 503 from x", status=503)

    monkeypatch.setattr(s500, "fetch_issue_page", boom)
    try:
        s500.fetch_url("https://trade.500.com/", timeout=5, user_agent="ua")
    except FetchError as exc:
        assert exc.status == 503
    else:  # pragma: no cover
        raise AssertionError("expected FetchError to propagate")


def test_scrapers_no_longer_open_urllib_directly():
    """The hand-rolled transports are gone; delegation is the only path."""
    for module in (s500, sns):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "urllib.request.urlopen" not in source, module.__name__
