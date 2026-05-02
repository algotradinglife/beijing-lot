"""HTTP layer: polite, retrying, UA-rotating scraper.

No JS rendering required — all targets are static HTML. Encoding handling:

- ``trade.500.com`` and ``zx.500.com`` declare gb2312, but in practice we
  decode with gb18030 (a superset) for safety.
- ``cp.zgzcw.com`` is UTF-8.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:124.0) "
    "Gecko/20100101 Firefox/124.0",
]

URL_BJDC_500 = "https://trade.500.com/bjdc/?expect={issue}"
URL_BJDC_500_INDEX = "https://trade.500.com/bjdc/"
URL_PROJECT_LIST = (
    "https://trade.500.com/pages/comm/projectlist.php?lotid=9&playid=34&"
    "needleft=1&type=2"
)
URL_BET_ZGZCW = "https://cp.zgzcw.com/lottery/bdplayvsforJsp.action?lotteryId=200"
URL_KAIJIANG_500 = "https://zx.500.com/zqdc/kaijiang.php?playid=1&expect={issue}"


class Scraper:
    """Thin requests wrapper with throttle, UA rotation, and 429/5xx backoff."""

    def __init__(self, *, min_interval: float = 1.0, max_retries: int = 3,
                 timeout: int = 20, session: Optional[requests.Session] = None):
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_req_at = 0.0
        self.session = session or requests.Session()

    # ---- low-level -------------------------------------------------------
    def _throttle(self):
        elapsed = time.time() - self._last_req_at
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.3))

    def get(self, url: str, *, encoding: str = "gb18030",
            referer: Optional[str] = None) -> str:
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self._throttle()
            headers = {
                "User-Agent": random.choice(UAS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            if referer:
                headers["Referer"] = referer
            try:
                self._last_req_at = time.time()
                r = self.session.get(url, headers=headers, timeout=self.timeout,
                                     allow_redirects=True)
                if r.status_code == 200:
                    # respect declared encoding when sensible
                    try:
                        return r.content.decode(encoding, errors="replace")
                    except LookupError:
                        return r.content.decode("utf-8", errors="replace")
                if r.status_code in (429, 500, 502, 503, 504):
                    backoff = 2 ** attempt + random.uniform(0, 1.0)
                    log.warning("HTTP %s on %s, sleeping %.1fs",
                                r.status_code, url, backoff)
                    time.sleep(backoff)
                    continue
                # other status — log and abort retries (e.g. 403/404)
                log.warning("HTTP %s on %s (no retry)", r.status_code, url)
                return ""
            except requests.RequestException as e:
                last_err = e
                backoff = 2 ** attempt + random.uniform(0, 1.0)
                log.warning("network err on %s: %s, sleeping %.1fs",
                            url, e, backoff)
                time.sleep(backoff)
        if last_err:
            log.error("giving up on %s after %d retries: %s", url,
                      self.max_retries, last_err)
        return ""

    # ---- semantic --------------------------------------------------------
    def fetch_bjdc_500(self, issue: Optional[str] = None) -> str:
        url = URL_BJDC_500.format(issue=issue) if issue else URL_BJDC_500_INDEX
        return self.get(url, encoding="gb18030")

    def fetch_zgzcw_bet(self) -> str:
        return self.get(URL_BET_ZGZCW, encoding="utf-8",
                        referer="https://cp.zgzcw.com/")

    def fetch_kaijiang_500(self, issue: str) -> str:
        return self.get(URL_KAIJIANG_500.format(issue=issue), encoding="gb18030")
