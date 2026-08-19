"""Per-issue recovery runner for the #268 immutable full-backfill staging lane."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from scripts.update_beidan_nowscore_sqlite import parse_titan_1x2_text

from .backfill import (
    AcquisitionResult,
    acquire_terminal,
    parse_declared_issue_payload,
    receipt_record,
    write_content_addressed_payload,
)

HORIZONS = ("initial", "10h", "1h")


class ByteClient(Protocol):
    def get(self, url: str, timeout: float) -> bytes: ...


@dataclass(frozen=True)
class IssueRecovery:
    issue_code: str
    issue_disposition: str
    receipts: list[dict[str, object]]
    quote_rows: list[dict[str, object]]
    fixture_horizon_dispositions: pd.DataFrame


def _all_unavailable(expected: pd.DataFrame, disposition: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in expected.itertuples(index=False):
        for horizon in HORIZONS:
            rows.append(
                {
                    "issue_code": str(item.issue_code),
                    "match_idx": int(item.match_idx),
                    "provider_match_id": None,
                    "snapshot_kind": horizon,
                    "disposition": disposition,
                    "detail": "issue-page request did not produce an identity-valid fixture payload",
                }
            )
    return pd.DataFrame(rows)


def _native_line(value: object) -> tuple[float | None, str]:
    try:
        line = float(value) if value is not None else None
    except (TypeError, ValueError):
        line = None
    if line is not None and line.is_integer() and -3.0 <= line <= 3.0:
        return line, "nowscore_issue_page_integer_line"
    return None, "nowscore_issue_page_missing_or_noninteger_line"


def _titan_unavailable(issue: str, slot: int, provider: str, disposition: str, detail: str) -> list[dict[str, object]]:
    return [
        {
            "issue_code": issue,
            "match_idx": slot,
            "provider_match_id": provider,
            "snapshot_kind": horizon,
            "disposition": disposition,
            "detail": detail,
        }
        for horizon in HORIZONS
    ]


def recover_issue(
    client: ByteClient,
    *,
    issue_code: str,
    expected: pd.DataFrame,
    staging_root: Path,
    issue_url: str,
    titan_url_template: str,
    timeout: float,
    attempts: int,
    max_fixtures: int | None = None,
) -> IssueRecovery:
    """Recover every source page fixture in one issue with terminal accounting.

    The result is deliberately usable even when an issue page or a Titan payload
    fails: every frozen local fixture×horizon receives a deterministic
    unavailable disposition rather than silently falling out of the denominator.
    """
    issue = str(issue_code)
    issue_expected = expected.loc[expected.issue_code.astype(str).eq(issue)].copy()
    receipts: list[dict[str, object]] = []
    issue_acquisition = acquire_terminal(
        client,
        source_kind="issue_page",
        source_key=issue,
        source_url=issue_url,
        timeout=timeout,
        attempts=attempts,
    )
    receipts.append(receipt_record(issue_acquisition))
    if issue_acquisition.payload is None:
        return IssueRecovery(
            issue, "UNAVAILABLE_ISSUE_PAGE_REQUEST_ERROR", receipts, [],
            _all_unavailable(issue_expected, "UNAVAILABLE_ISSUE_PAGE_REQUEST_ERROR"),
        )
    write_content_addressed_payload(staging_root, issue_acquisition.receipt, issue_acquisition.payload)
    try:
        parsed = parse_declared_issue_payload(issue_acquisition.payload, requested_issue=issue)
    except ValueError as exc:
        return IssueRecovery(
            issue, "UNAVAILABLE_ISSUE_PAGE_INVALID_IDENTITY", receipts, [],
            _all_unavailable(issue_expected, "UNAVAILABLE_ISSUE_PAGE_INVALID_IDENTITY"),
        )

    quote_rows: list[dict[str, object]] = []
    dispositions: list[dict[str, object]] = []
    expected_slots = {int(value) for value in issue_expected.match_idx}
    source_slots: set[int] = set()
    source_rows = parsed.rows if max_fixtures is None else parsed.rows[:max_fixtures]
    for row in source_rows:
        slot = int(row["match_idx"])
        source_slots.add(slot)
        provider = str(row["provider_match_id"])
        logical_key = f"{issue}:{slot:03d}:{provider}"
        titan = acquire_terminal(
            client,
            source_kind="titan_1x2",
            source_key=logical_key,
            source_url=titan_url_template.format(provider_match_id=provider),
            timeout=timeout,
            attempts=attempts,
        )
        receipts.append(receipt_record(titan))
        if titan.payload is None:
            dispositions.extend(_titan_unavailable(issue, slot, provider, "UNAVAILABLE_TITAN_REQUEST_ERROR", titan.receipt.error_class or "request error"))
            continue
        write_content_addressed_payload(staging_root, titan.receipt, titan.payload)
        try:
            _, odds_rows, _ = parse_titan_1x2_text(titan.payload.decode("utf-8-sig", errors="replace"))
        except ValueError as exc:
            dispositions.extend(_titan_unavailable(issue, slot, provider, "UNAVAILABLE_TITAN_MALFORMED_PAYLOAD", type(exc).__name__))
            continue
        line, line_source = _native_line(row.get("handicap_line"))
        by_horizon: dict[str, int] = {horizon: 0 for horizon in HORIZONS}
        for _, market, bookmaker, horizon, v1, v2, v3 in odds_rows:
            if market != "euro_1x2" or horizon not in by_horizon:
                continue
            by_horizon[str(horizon)] += 1
            quote_rows.append(
                {
                    "issue_code": issue,
                    "match_idx": slot,
                    "source_match_id": logical_key,
                    "provider_match_id": provider,
                    "snapshot_kind": str(horizon),
                    "bookmaker_id": str(bookmaker),
                    "v1": v1,
                    "v2": v2,
                    "v3": v3,
                    "native_handicap_line_raw": row.get("handicap_line"),
                    "native_handicap_line": line,
                    "handicap_norm_source": line_source,
                    "payload_sha256": titan.receipt.payload_sha256,
                }
            )
        for horizon, count in by_horizon.items():
            dispositions.append(
                {
                    "issue_code": issue,
                    "match_idx": slot,
                    "provider_match_id": provider,
                    "snapshot_kind": horizon,
                    "disposition": "RECOVERED_RAW_QUOTE" if count else "UNAVAILABLE_NO_TITAN_HORIZON",
                    "detail": f"raw_bookmaker_rows={count}",
                }
            )
    for slot in sorted(expected_slots - source_slots):
        dispositions.extend(_titan_unavailable(issue, slot, "", "UNAVAILABLE_NOT_IN_AUTHORITATIVE_ISSUE_PAGE", "not present in identity-valid source page"))
    disposition_frame = pd.DataFrame(dispositions)
    if not disposition_frame.empty:
        disposition_frame["_horizon_order"] = disposition_frame["snapshot_kind"].map(
            {"initial": 0, "10h": 1, "1h": 2}
        )
        disposition_frame = disposition_frame.sort_values(
            ["issue_code", "match_idx", "_horizon_order"], kind="stable"
        ).drop(columns="_horizon_order").reset_index(drop=True)
    return IssueRecovery(
        issue,
        "RECOVERED",
        receipts,
        quote_rows,
        disposition_frame,
    )
