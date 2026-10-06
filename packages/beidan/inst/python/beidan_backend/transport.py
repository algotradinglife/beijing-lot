"""The package-wide HTTP transport: a bounded, explicit fetch.

Nothing is retried blindly and nothing is fetched implicitly on import. The
caller names the URL, the timeout and the retry budget, and every response's raw
bytes are returned so they can be persisted before any parsing happens.

This is the single shared network layer for the backend. The issue-schedule,
settlement, prematch-SP and market-capture services all fetch through
``fetch_issue_page`` rather than reimplementing timeouts, retries or headers.
"""

from __future__ import annotations

import time
import math
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 25.0
DEFAULT_RETRIES = 2


class FetchError(RuntimeError):
    """A bounded fetch attempt failed and the retry budget is exhausted.

    ``status`` carries the last HTTP status code observed, when there was one,
    so callers can record it in diagnostics without parsing the message.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class FetchResponse:
    """One successful HTTP response, raw bytes included."""

    url: str
    status: int
    body: bytes
    content_type: str | None
    observed_at: str
    elapsed_sec: float
    attempts: int


def fetch_issue_page(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    user_agent: str = DEFAULT_USER_AGENT,
    referer: str | None = None,
    backoff_sec: float = 0.5,
    headers: dict | None = None,
    opener=None,
) -> FetchResponse:
    """Fetch one page with an explicit timeout and transient retry budget.

    @param url Absolute URL to fetch.
    @param timeout Per-attempt socket timeout in seconds; must be finite and > 0.
    @param retries Number of *additional* attempts after the first; >= 0.
    @param user_agent User-Agent header.
    @param referer Optional Referer header.
    @param backoff_sec Sleep between attempts; >= 0.
    @param headers Optional extra request headers, merged over the defaults; used
        by sources that need their own Accept / Accept-Language / Cache-Control.
    @param opener Injection point for tests: a callable ``(request, timeout)``
        returning a context manager with ``read()``, ``status`` and ``headers``.
        Defaults to ``urllib.request.urlopen``. This is how the retry/timeout
        behaviour is tested without a network.
    @return A ``FetchResponse`` carrying the raw bytes and the observation time.
    @raises ValueError for invalid arguments.
    @raises FetchError when every attempt fails.
    """
    if not url or not str(url).strip():
        raise ValueError("url must be a non-empty string")
    if not (type(timeout) in (int, float) and math.isfinite(timeout) and timeout > 0):
        raise ValueError("timeout must be a finite positive number of seconds")
    if not (type(retries) is int and retries >= 0):
        raise ValueError("retries must be a non-negative integer")
    if not math.isfinite(backoff_sec) or backoff_sec < 0:
        raise ValueError("backoff_sec must be non-negative")
    call = opener or urllib.request.urlopen
    request_headers = {"User-Agent": user_agent, "Accept-Encoding": "identity"}
    if referer:
        request_headers["Referer"] = referer
    if headers:
        request_headers.update({str(key): str(value) for key, value in headers.items()})
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        request = urllib.request.Request(url, headers=request_headers)
        started = time.time()
        try:
            with call(request, timeout=timeout) as response:
                body = response.read()
                status = int(getattr(response, "status", 200) or 200)
                content_type = None
                response_headers = getattr(response, "headers", None)
                if response_headers is not None:
                    content_type = response_headers.get("Content-Type")
            if status != 200:
                raise FetchError(f"HTTP {status} from {url}", status=status)
            return FetchResponse(
                url=url,
                status=status,
                body=body,
                content_type=content_type,
                observed_at=_utc_now_iso(),
                elapsed_sec=time.time() - started,
                attempts=attempt,
            )
        except FetchError:
            raise
        except urllib.error.HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504}:
                raise FetchError(f"HTTP {error.code} from {url}", status=error.code) from error
            last_error = error
            if attempt <= retries and backoff_sec:
                time.sleep(backoff_sec)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            last_error = error
            if attempt <= retries and backoff_sec:
                time.sleep(backoff_sec)
    raise FetchError(
        f"fetching {url} failed after {retries + 1} attempt(s): {last_error}",
        status=getattr(last_error, "code", None),
    ) from last_error


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
