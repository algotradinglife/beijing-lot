"""Polite HTTP scraper for 500.com kaijiang.php pages."""
from __future__ import annotations

import logging
import re
import time
from typing import Iterable

import requests

LOG = logging.getLogger(__name__)

KAIJIANG_URL = "https://zx.500.com/zqdc/kaijiang.php?playid=1&expect={issue}"
PROJECTLIST_URL = (
    "https://trade.500.com/pages/comm/projectlist.php"
    "?lotid=9&playid=34&needleft=1&type=2"
)
TRADE_INDEX_URL = "https://trade.500.com/bjdc/index.php"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def make_session(user_agent: str = DEFAULT_UA) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9"})
    return s


def fetch_issue_html(session: requests.Session, issue: str, timeout: int = 20) -> str:
    """Fetch the kaijiang.php HTML for one issue, returning a unicode string.

    Raises requests.RequestException on network failure.
    """
    url = KAIJIANG_URL.format(issue=issue)
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    # GB2312 declared but content occasionally contains GB18030-only bytes.
    return r.content.decode("gb18030", errors="replace")


def parse_issue_list_body(body: str) -> list[str]:
    """Return the issues admitted from a decoded trade-index page body.

    The ``expect_select`` dropdown spans the full history (2007-present); we
    admit every issue from 2010 onward:

    * 6-digit ``YYMMNN`` (2010-2019) when the value is ``>= 100101``;
    * 5-digit ``YYNNN`` (2020+) when the ``NNN`` suffix is in ``1..170``.

    Values of any other length are not issues, and league identities that
    appear as ``liansai.500.com/zuqiu-<id>`` links are not issues either.
    Duplicates collapse; the result is sorted, which for admitted values is
    also chronological order (every 2010s issue sorts before every 2020s one).
    A body without the dropdown yields an empty list rather than an error.
    """
    select = re.search(
        r'<select[^>]+id="expect_select"[^>]*>(.*?)</select>', body, re.S | re.I
    )
    if not select:
        return []
    keep: list[str] = []
    seen: set[str] = set()
    for issue in re.findall(r'<option\s+value="(\d+)"', select.group(1)):
        if issue in seen:
            continue
        if len(issue) == 5 and 1 <= int(issue[2:]) <= 170:
            keep.append(issue)
            seen.add(issue)
        elif len(issue) == 6 and int(issue) >= 100101:
            keep.append(issue)
            seen.add(issue)
    return sorted(keep)


def fetch_issue_list(session: requests.Session, timeout: int = 30) -> list[str]:
    """Fetch the trade index page and return every advertised Beijing issue.

    Fetching and decoding live here; admission rules live in
    :func:`parse_issue_list_body`. Raises requests.RequestException on
    network failure.
    """
    r = session.get(TRADE_INDEX_URL, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return parse_issue_list_body(r.content.decode("gb18030", errors="replace"))


def polite_iter(items: Iterable[str], rate_per_sec: float = 0.5):
    """Yield items at most rate_per_sec, sleeping between."""
    interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
    last = 0.0
    for it in items:
        if interval:
            elapsed = time.monotonic() - last
            if elapsed < interval:
                time.sleep(interval - elapsed)
        yield it
        last = time.monotonic()
