"""End-to-end orchestration for one issue, as a single explicit call.

This is the entry point the R bridge calls through reticulate. It is deliberately
thin: it wires the decode/parse/crosscheck/validate/persist pieces together and
returns plain, JSON-shaped data, so that no business rule lives here and every
rule stays independently unit-testable in its own module.

Two ordering guarantees matter and are why this module exists rather than the R
caller driving the steps itself:

* when persistence is requested, the **raw bytes are on disk before any parser
  runs**, and
* a parser that raises still leaves a metadata receipt naming the failure, so an
  on-disk observation is never silently lost and never mistaken for an empty
  result.

Fetching is *optional*: when ``pages`` is supplied the function is fully offline,
which is what the frozen-26098 replay and the R tests use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import hashlib
from typing import Any

from .contract import (
    canonical_issue_schedule,
    nowscore_url,
    source_500_url,
    validate_issue_id,
)
from .crosscheck import build_canonical_rows, identity_summary
from .decode import decode_response, declared_charset
from ..transport import fetch_issue_page
from .sources import ProviderRow, parse_500_rows, parse_nowscore_rows
from .store import new_fetch_directory, persist_issue_meta, persist_issue_raw


@dataclass
class IssueScheduleResult:
    """Everything one issue fetch produced, with provenance attached."""

    issue_id: str
    rows: list[dict[str, Any]]
    diagnostics: list[str]
    identity_summary: dict[str, int]
    observed_at: str
    source_500_raw: bytes
    nowscore_raw: bytes
    rows_500: list[ProviderRow]
    rows_nowscore: list[ProviderRow]
    urls: dict[str, str]
    written: dict[str, str]
    parse_errors: dict[str, str] = field(default_factory=dict)


def fetch_issue_schedule(
    issue_id: str,
    raw_dir: str,
    *,
    timeout: float = 25.0,
    retries: int = 2,
    pages: dict[str, bytes] | None = None,
    opener=None,
) -> IssueScheduleResult:
    """Fetch, parse, reconcile, validate and persist one issue's schedule.

    @param issue_id Issue identifier; leading zeros are preserved.
    @param raw_dir Explicit parent directory for raw responses and the metadata
        receipt. Each run writes ``raw_dir/<issue_id>/<fetch_id>/`` and never
        overwrites a previous observation.
    @param timeout Per-request timeout in seconds.
    @param retries Additional attempts per URL after the first.
    @param pages Offline override mapping ``{"500": bytes, "nowscore": bytes}``,
        together with ``"<source>_observed_at"`` ISO-8601 values. When given,
        no network call is made at all. Offline pages keep their **original
        per-source observation instants**; missing or timezone-naive instants fail.
    @param opener Test injection point for the HTTP layer.
    @return An ``IssueScheduleResult``. No CSV is produced: the canonical table
        is exported by the caller with ``readr::write_csv()``.
    @raises ValueError on an invalid issue id.
    @raises IssueScheduleError when the canonical contract is violated.
    @raises DecodeError / SourceParseError when a response cannot be decoded or
        parsed; the persisted raw bytes and metadata receipt remain on disk.
    @details Raw bytes are always written before any parser runs — there is no
        way to fetch without preserving evidence. The canonical ``observed_at``
        is the latest **actual response** instant across sources (not the request
        start), so a slow response is not mislabelled as an earlier observation.
    """
    issue = validate_issue_id(issue_id)
    urls = {"500": source_500_url(issue), "nowscore": nowscore_url(issue)}
    request_started = datetime.now(timezone.utc)

    fetch_id = request_started.strftime("%Y%m%dT%H%M%S.%fZ")
    fetch_dir = new_fetch_directory(raw_dir, issue, fetch_id)
    written = {}
    bodies = {}
    offline = pages is not None
    if offline:
        raw_500 = pages["500"]
        raw_nowscore = pages["nowscore"]
        content_500 = pages.get("500_content_type")
        content_nowscore = pages.get("nowscore_content_type")
        observed_500 = _offline_observed_at(pages, "500")
        observed_nowscore = _offline_observed_at(pages, "nowscore")
    else:
        responses = {}
        try:
            for source, url in urls.items():
                response = fetch_issue_page(
                    url, timeout=timeout, retries=retries, opener=opener)
                responses[source] = response
                bodies[source] = response.body
                written.update(persist_issue_raw(
                    directory=fetch_dir, issue_id=issue, bodies={source: response.body}))
        except Exception as error:
            persist_issue_meta(directory=fetch_dir, issue_id=issue, bodies=bodies,
                rows={}, meta={"issue_id": issue, "urls": urls,
                "fetch_error": str(error),
                "observed_at": {k: v.observed_at for k, v in responses.items()}})
            raise
        response_500, response_nowscore = responses["500"], responses["nowscore"]
        raw_500, raw_nowscore = response_500.body, response_nowscore.body
        observed_500, observed_nowscore = response_500.observed_at, response_nowscore.observed_at
        content_500, content_nowscore = response_500.content_type, response_nowscore.content_type

    observed_at = max(datetime.fromisoformat(x.replace("Z", "+00:00")) for x in (observed_500, observed_nowscore)).astimezone(timezone.utc).isoformat()
    observed_at_value = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))

    bodies = {"500": raw_500, "nowscore": raw_nowscore}
    if offline:
        written.update(persist_issue_raw(directory=fetch_dir, issue_id=issue, bodies=bodies))

    meta: dict[str, Any] = {
        "issue_id": issue,
        "urls": urls,
        "fetch_id": fetch_id,
        "request_started_at": request_started.isoformat(),
        "observed_at": {"500": observed_500, "nowscore": observed_nowscore},
        "observed_at_canonical": observed_at,
        "offline": offline,
        "parser": "beidan_backend.issue_schedule",
        "parser_files_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))},
        "content_type": {"500": content_500, "nowscore": content_nowscore},
        "primary": "nowscore",
        "parse": {"failed": None},
    }
    try:
        meta["encoding"] = {"500": declared_charset(raw_500, content_500),
                            "nowscore": declared_charset(raw_nowscore, content_nowscore)}
        text_500 = decode_response(raw_500, content_500)
        text_nowscore = decode_response(raw_nowscore, content_nowscore)
        rows_500 = parse_500_rows(
            text_500, issue_id=issue, observed_at=observed_500, source_url=urls["500"]
        )
        rows_nowscore = parse_nowscore_rows(
            text_nowscore,
            issue_id=issue,
            observed_at=observed_nowscore,
            source_url=urls["nowscore"],
        )
    except Exception as error:
        meta["parse"]["failed"] = f"{type(error).__name__}: {error}"
        written.update(
            persist_issue_meta(
                directory=fetch_dir, issue_id=issue, bodies=bodies, rows={}, meta=meta
            )
        )
        raise

    try:
        canonical, diagnostics = build_canonical_rows(
            issue_id=issue,
            rows_500=rows_500,
            rows_nowscore=rows_nowscore,
            observed_at_iso=observed_at,
            observed_at_utc=observed_at_value,
            source_url_500=urls["500"],
            source_url_nowscore=urls["nowscore"],
        )
        rows = canonical_issue_schedule(issue_id=issue, rows=canonical, observed_at=observed_at)
        summary = identity_summary(rows)
    except Exception as error:
        meta["parse"]["failed"] = f"{type(error).__name__}: {error}"
        persist_issue_meta(directory=fetch_dir, issue_id=issue, bodies=bodies, rows={}, meta=meta)
        raise
    meta["parse"]["failed"] = None
    meta["row_counts"] = {"500": len(rows_500), "nowscore": len(rows_nowscore)}
    meta["diagnostics"] = diagnostics
    meta["identity_summary"] = summary
    written.update(
        persist_issue_meta(
            directory=fetch_dir,
            issue_id=issue,
            bodies=bodies,
            rows={"500": rows_500, "nowscore": rows_nowscore},
            meta=meta,
        )
    )
    return IssueScheduleResult(
        issue_id=issue,
        rows=rows,
        diagnostics=diagnostics,
        identity_summary=summary,
        observed_at=observed_at,
        source_500_raw=raw_500,
        nowscore_raw=raw_nowscore,
        rows_500=rows_500,
        rows_nowscore=rows_nowscore,
        urls=urls,
        written=written,
        parse_errors={},
    )


def _offline_observed_at(pages: dict[str, Any], source: str) -> str:
    """Return an offline page's own observation instant.

    @param pages Offline page mapping; must carry ``"<source>_observed_at"``.
    @param source ``"500"`` or ``"nowscore"``.
    @return ISO-8601 observation instant.
    @details Offline replay must not pretend a saved page was observed now: a
        timezone-aware per-source instant is required, then normalized to UTC.
    """
    supplied = pages.get(f"{source}_observed_at")
    if not isinstance(supplied, str):
        raise ValueError(f"offline pages require {source}_observed_at")
    value = datetime.fromisoformat(supplied.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("offline observed_at requires an explicit timezone")
    return value.astimezone(timezone.utc).isoformat()
