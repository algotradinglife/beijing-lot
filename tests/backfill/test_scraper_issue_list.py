"""Contract tests for trade-index issue discovery in ``src.backfill.scraper``.

``fetch_issue_list`` drives historical backfill and the historical id-map
scripts, so its admission rules are a data contract:

* the ``expect_select`` dropdown on the trade index spans the full history;
* 6-digit ``YYMMNN`` issues are admitted only when the value is ``>= 100101``;
* 5-digit ``YYNNN`` issues are admitted only when ``NNN`` is in ``1..170``;
* league links (``liansai.500.com/zuqiu-<id>``) are not issues;
* duplicates collapse, the result is sorted, and for admitted values that
  order is chronological;
* a page without the dropdown yields an empty list instead of an exception;
* the page is decoded as GB18030 and HTTP errors propagate.

Everything runs offline: the synthetic bodies never touch the network, and the
recorded page replays a real response whose identity is pinned by the adjacent
provenance file.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.backfill import scraper

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "backfill"
RECORDED_PAGE = FIXTURE_DIR / "trade_index_bjdc_20260919.html"
RECORDED_PROVENANCE = FIXTURE_DIR / "trade_index_bjdc_20260919.provenance.json"


class _Response:
    def __init__(self, body: str, status: int = 200) -> None:
        self.content = body.encode("gb18030", errors="replace")
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise scraper.requests.HTTPError(f"HTTP {self.status_code}")


class _Session:
    """Records every request; never performs network access."""

    def __init__(self, body: str, status: int = 200) -> None:
        self._body = body
        self._status = status
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return _Response(self._body, self._status)


def _body(options: list[str], *, extra: str = "", inside: str = "", select: bool = True) -> str:
    """Build a page body; ``extra`` precedes the dropdown and ``inside`` is inside it."""
    opts = "".join(f'<option value="{o}">{o}</option>' for o in options)
    dropdown = f'<select id="expect_select" name="expect">{opts}{inside}</select>' if select else ""
    return f"<html><body>{extra}{dropdown}</body></html>"


# --- parse layer -----------------------------------------------------------------


def test_admits_six_digit_and_five_digit_issues_sorted():
    body = _body(["26049", "100101", "24011", "26001"])
    assert scraper.parse_issue_list_body(body) == ["100101", "24011", "26001", "26049"]


@pytest.mark.parametrize(
    ("option", "admitted"),
    [
        ("100101", True),  # 6-digit lower bound
        ("100100", False),  # just below the 6-digit bound
        ("24001", True),  # 5-digit NNN = 1, lower bound
        ("24170", True),  # 5-digit NNN = 170, upper bound
        ("24000", False),  # 5-digit NNN = 0
        ("24171", False),  # 5-digit NNN = 171
    ],
)
def test_boundary_admission_rules(option: str, admitted: bool):
    assert (scraper.parse_issue_list_body(_body([option])) == [option]) is admitted


def test_drops_values_that_are_not_five_or_six_digits():
    assert scraper.parse_issue_list_body(_body(["0999", "1234567", "2411"])) == []


def test_deduplicates_repeated_options():
    assert scraper.parse_issue_list_body(_body(["26049", "26049", "24011", "26049"])) == [
        "24011",
        "26049",
    ]


def test_league_links_are_not_issues():
    outside = '<a href="https://liansai.500.com/zuqiu-26049">联赛</a>'
    inside = '<a href="https://liansai.500.com/zuqiu-24022">联赛</a>'
    body = _body(["24011"], extra=outside, inside=inside)

    # Guard the fixture itself: one league link must really sit inside the dropdown.
    select_start = body.index('id="expect_select"')
    assert select_start < body.index("24022") < body.index("</select>")

    assert scraper.parse_issue_list_body(body) == ["24011"]


def test_missing_dropdown_returns_empty_list():
    assert scraper.parse_issue_list_body(_body([], select=False)) == []


def test_sorted_order_is_chronological_for_admitted_values():
    body = _body(["26049", "191205", "20011", "100101"])
    issues = scraper.parse_issue_list_body(body)
    assert issues == ["100101", "191205", "20011", "26049"]
    # every 2010s (6-digit) issue precedes every 2020s (5-digit) issue
    assert max(i for i in issues if len(i) == 6) < min(i for i in issues if len(i) == 5)


# --- fetch layer ----------------------------------------------------------------


def test_requests_trade_index_with_redirects_and_timeout():
    session = _Session(_body(["24011"]))
    scraper.fetch_issue_list(session, timeout=7)
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == scraper.TRADE_INDEX_URL
    assert call["allow_redirects"] is True
    assert call["timeout"] == 7


def test_fetch_decodes_gb18030_only_bytes(monkeypatch):
    """The decoded body must survive the GB18030 path, not merely yield issues.

    '㐀' (U+3400) is outside GB2312. Decoding this response as GB2312 or
    Latin-1 mangles that character while leaving the issue list unchanged, so
    the assertion is on the body handed to the parser, not on the issues.
    """
    captured: dict[str, str] = {}
    real_parse = scraper.parse_issue_list_body

    def _capture(body: str) -> list[str]:
        captured["body"] = body
        return real_parse(body)

    monkeypatch.setattr(scraper, "parse_issue_list_body", _capture)
    session = _Session(_body(["24011", "100101"], extra="<span>㐀</span>"))

    assert scraper.fetch_issue_list(session) == ["100101", "24011"]
    assert "㐀" in captured["body"]


def test_http_error_propagates():
    session = _Session(_body(["24011"]), status=503)
    with pytest.raises(scraper.requests.HTTPError):
        scraper.fetch_issue_list(session)


# --- recorded page --------------------------------------------------------------


def test_recorded_page_matches_declared_provenance():
    provenance = json.loads(RECORDED_PROVENANCE.read_text(encoding="utf-8"))
    raw = RECORDED_PAGE.read_bytes()
    assert len(raw) == provenance["bytes"]
    assert hashlib.sha256(raw).hexdigest() == provenance["sha256"]
    assert provenance["source_url"] == scraper.TRADE_INDEX_URL


def test_recorded_page_replays_expected_issue_domain():
    """The recorded page must satisfy the contract and yield its frozen counts.

    The counts are properties of this recording, not of the live site: the
    provenance file pins the bytes, so refreshing it means updating both.
    """
    provenance = json.loads(RECORDED_PROVENANCE.read_text(encoding="utf-8"))
    body = RECORDED_PAGE.read_bytes().decode(provenance["decoded_as"], errors="replace")
    issues = scraper.parse_issue_list_body(body)

    assert len(issues) == 1618
    assert issues == sorted(issues)
    assert len(issues) == len(set(issues))
    assert issues[0] == "100101"
    assert issues[-1] == "26096"

    six_digit = [i for i in issues if len(i) == 6]
    five_digit = [i for i in issues if len(i) == 5]
    assert (len(six_digit), len(five_digit)) == (1213, 405)
    assert all(int(i) >= 100101 for i in six_digit)
    assert all(1 <= int(i[2:]) <= 170 for i in five_digit)
    assert all(i.isdigit() for i in issues)
