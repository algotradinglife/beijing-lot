"""Polite HTTP scraper for 500.com kaijiang.php pages."""
from __future__ import annotations

import logging
import time
from typing import Iterable

import requests

LOG = logging.getLogger(__name__)

KAIJIANG_URL = "https://zx.500.com/zqdc/kaijiang.php?playid=1&expect={issue}"
PROJECTLIST_URL = (
    "https://trade.500.com/pages/comm/projectlist.php"
    "?lotid=9&playid=34&needleft=1&type=2"
)
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


def fetch_issue_list(session: requests.Session, timeout: int = 30) -> list[str]:
    """Return all issues advertised by the projectlist dropdown.

    Filters to plausible 5-digit YYNNN issues (NNN in 1..170).
    """
    import re

    r = session.get(PROJECTLIST_URL, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    body = r.content.decode("gb18030", errors="replace")
    raw = re.findall(r"\b(2[0-9]\d{3})\b", body)
    keep: list[str] = []
    seen: set[str] = set()
    for x in raw:
        if x in seen:
            continue
        if 1 <= int(x[2:]) <= 170:
            keep.append(x)
            seen.add(x)
    return sorted(keep)


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
