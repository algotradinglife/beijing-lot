"""The canonical issue-schedule schema and its validators.

The canonical table is one row per ``(issue_id, slot)`` for a single issue. It is
a *schedule* table: it records who plays whom, when, with what handicap, and what
each source reported about sale/status at the observation instant. It deliberately
does not carry odds.

Status vocabulary reuses the package-wide ``match_status_levels()`` contract:
``scheduled``, ``live``, ``finished``, ``postponed``, ``cancelled``,
``abandoned``, ``unknown``. ``unknown`` is a real value meaning "the source
reported nothing we can classify", and it is never replaced by a guess.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

#: Explicit source timezone. Both sites publish Beijing time; naive strings are
#: interpreted here and only here, then converted to UTC for storage.
SOURCE_TZ = timezone(timedelta(hours=8))

CANONICAL_500_URL = "https://trade.500.com/bjdc/?expect={issue}"
CANONICAL_NOWSCORE_URL = "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum={issue}"

MATCH_STATUSES = (
    "scheduled",
    "live",
    "finished",
    "postponed",
    "cancelled",
    "abandoned",
    "unknown",
)

#: How a kickoff date was established. The only accepted evidence is the page's
#: own JS kickoff date, cross-checked against the dated closing instant. The
#: row's *sales-grouping* date is not a kickoff date and is never a source here;
#: ``absent`` means the kickoff could not be established at all.
KICKOFF_DATE_SOURCES = ("js-kickoff-date", "absent")

SALE_STATES = ("open", "closed", "unknown")

#: Identity agreement between the two sources for a slot.
IDENTITY_MATCH_METHODS = ("provider_id", "normalized_name", "unresolved", "conflict")

_ISSUE_RE = re.compile(r"^[0-9]{4,}$")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


class IssueScheduleError(ValueError):
    """Base class for issue-schedule contract failures."""


class MatchStatusError(IssueScheduleError):
    """A status could not be classified from the evidence available."""


def canonical_columns() -> tuple[str, ...]:
    """Return the canonical column order.

    @return Column names in contract order. Order is part of the contract so the
        CSV export and the tibble agree positionally.
    """
    return (
        "issue_id",
        "slot",
        "fixture_key",
        "home_name",
        "away_name",
        "handicap",
        "kickoff_at",
        "kickoff_hhmm",
        "kickoff_group_date",
        "kickoff_date_source",
        "match_status",
        "match_status_raw",
        "sale_state",
        "sale_end_at",
        "sale_end_raw",
        "sale_end_raw_500",
        "sale_end_raw_nowscore",
        "sale_end_date_source",
        "score",
        "provider_id",
        "provider_id_500",
        "provider_id_nowscore",
        "home_500",
        "away_500",
        "home_nowscore",
        "away_nowscore",
        "identity_method",
        "identity_note",
        "observed_at",
        "source_url_500",
        "source_url_nowscore",
        "raw_display_nowscore",
        "raw_display_500",
        "home_display_500",
        "home_title_500",
        "away_display_500",
        "away_title_500",
        "home_display_nowscore",
        "home_title_nowscore",
        "away_display_nowscore",
        "away_title_nowscore",
        "league_500",
        "league_nowscore",

    )


def nowscore_url(issue_id: str) -> str:
    """Return the nowscore ``all=1`` URL for an issue.

    @param issue_id Issue identifier; leading zeros are preserved.
    @return The canonical nowscore schedule URL.
    """
    return CANONICAL_NOWSCORE_URL.format(issue=issue_id)


def source_500_url(issue_id: str) -> str:
    """Return the 500 trade URL for an issue.

    @param issue_id Issue identifier; leading zeros are preserved.
    @return The canonical 500 schedule URL.
    """
    return CANONICAL_500_URL.format(issue=issue_id)


def validate_issue_id(issue_id: str) -> str:
    """Validate an issue identifier.

    @param issue_id Candidate identifier.
    @return The identifier unchanged.
    @raises IssueScheduleError when it is not a non-empty digit string. It is
        validated as a *string* so ``"026098"`` and ``"26098"`` stay distinct.
    """
    if not isinstance(issue_id, str) or not issue_id.strip():
        raise IssueScheduleError("issue_id must be a non-empty string")
    if not _ISSUE_RE.match(issue_id):
        raise IssueScheduleError(
            f"issue_id {issue_id!r} must be digits only (leading zeros preserved)"
        )
    return issue_id


def parse_source_date(value: str | None, *, field: str) -> str | None:
    """Validate a ``YYYY-MM-DD`` date published by a source.

    @param value Raw date string, ``None`` or empty for "absent".
    @param field Field label used in error messages.
    @return The date string unchanged, or ``None``.
    @raises IssueScheduleError on a malformed or impossible calendar date.
    """
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    match = _DATE_RE.match(text)
    if match is None:
        raise IssueScheduleError(f"{field}: {text!r} is not a YYYY-MM-DD date")
    year, month, day = (int(part) for part in match.groups())
    try:
        datetime(year, month, day)
    except ValueError as error:
        raise IssueScheduleError(f"{field}: {text!r} is not a real calendar date") from error
    return text


def source_instant(date_text: str | None, clock_text: str | None) -> datetime | None:
    """Combine a dated source string and a clock into an aware instant.

    Both inputs must already carry what they claim: ``date_text`` is a full
    ``YYYY-MM-DD HH:MM`` (as found in nowscore's ``截止时间：`` title) or a bare
    ``YYYY-MM-DD``; ``clock_text`` is ``HH:MM``.

    @param date_text Dated string, or ``None``.
    @param clock_text ``HH:MM`` string, or ``None``.
    @return An aware ``datetime`` in ``SOURCE_TZ``, or ``None`` when either part
        is missing. Returning ``None`` is the contract's way of saying "the
        source never gave a full date, so no instant exists" — it never invents
        one by borrowing the issue date.
    @raises IssueScheduleError on malformed input.
    """
    if date_text is None or not str(date_text).strip():
        return None
    text = str(date_text).strip()
    full = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})$", text)
    if full:
        day, clock = full.group(1), full.group(2)
    else:
        day = parse_source_date(text, field="source_instant")
        if clock_text is None or not _HHMM_RE.match(str(clock_text).strip()):
            return None
        clock = str(clock_text).strip()
    _validate_clock(clock, field="source_instant")
    parsed = datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M")
    return parsed.replace(tzinfo=SOURCE_TZ)


def resolve_kickoff_at(
    *,
    js_kickoff_date: str | None,
    clock_text: str | None,
    closing_at: datetime | None,
) -> tuple[datetime | None, str, str]:
    """Resolve one match's kickoff instant from independent date evidence.

    @param js_kickoff_date The page's own ``new Date(...)`` calendar date for the
        match (``YYYY-MM-DD``), or ``None``. This is the only kickoff *date*
        evidence: the page rewrites the JS clock while a match runs (slot 1 of
        the frozen 26098 snapshot reads ``14:02:11`` for a 13:00 kickoff), so
        only its calendar date is taken.
    @param clock_text The displayed kickoff clock (``HH:MM``), or ``None``. This
        is the only kickoff *clock* evidence.
    @param closing_at The dated closing instant (nowscore's ``截止时间：``
        title), or ``None``.
    @return ``(kickoff_at, date_source, note)`` where ``kickoff_at`` is an aware
        Beijing-time instant or ``None``, and ``note`` records *why* it is
        ``None`` (empty when resolved). The date source is
        ``"js-kickoff-date"`` whenever the JS date resolved, and ``"absent"``
        otherwise; the group date is never reported as an authoritative date.
    @details The rule is evidence agreement, not arithmetic:

        · both the JS kickoff date and the displayed clock are required; either
          one alone is not a kickoff, so a missing JS date is ``unknown`` and is
          **never** inferred from the row's sales-group date;
        · the closing instant is a cross-check only. It is compared with the
          candidate built from the JS kickoff date plus the displayed clock; a
          candidate that would precede the closing instant is shifted by one
          day, and the resulting candidate's calendar date must match the JS
          kickoff date exactly;
        · a mismatch (candidate on another calendar day) is a diagnostic, and
          the kickoff stays ``None``;
        · a missing closing instant means the JS date cannot be cross-checked;
          the date is still used but the note says so, so downstream can see the
          date is single-source.

        Contradictory or missing evidence yields ``None`` — never a guess, and
        never a fixed ``+5``-minute offset.
    """
    clock = str(clock_text).strip() if clock_text is not None else ""
    if not _HHMM_RE.match(clock) or not _is_real_clock(clock):
        return None, "absent", "kickoff-clock-missing"
    hour, minute = (int(part) for part in clock.split(":"))
    if not js_kickoff_date:
        return None, "absent", "kickoff-date-missing"
    day = parse_source_date(js_kickoff_date, field="js_kickoff_date")
    if closing_at is None:
        return (
            _beijing(day, hour, minute),
            "js-kickoff-date",
            "kickoff-date-from-js-without-closing-crosscheck",
        )
    candidate = _closing_candidate(closing_at, day, hour, minute)
    if candidate is None:
        return None, "absent", "kickoff-precedes-its-own-closing-instant"
    if candidate.date().isoformat() != day:
        return None, "absent", "closing-candidate-on-another-calendar-day"
    return _beijing(day, hour, minute), "js-kickoff-date", ""


def _closing_candidate(
    closing_at: datetime, day: str, hour: int, minute: int
) -> datetime | None:
    """Return the kickoff-candidate instant whose clock is the closing clock.

    The page shows the closing instant with a **full date** in the cell's
    ``title`` (``截止时间：2026-09-25 12:55``), so the date is known and only the
    kickoff clock is bare. The candidate is therefore built from the *closing
    date* and the *displayed kickoff* ``HH:mm``: the sales deadline belongs to
    the match it closes, so a deadline can precede its kickoff (12:55 closes a
    13:00 match) or sit just before a kickoff that tips over midnight (23:55
    closes the next day's 00:00 match). When that candidate falls **before** the
    closing instant, the kickoff is on the following calendar day, so one day is
    added.

    @param closing_at The dated closing instant read from the closing title.
    @param day Kickoff calendar date (``YYYY-MM-DD``) from the page's own JS
        kickoff date. Only its calendar *date* is used, never the JS clock.
    @param hour Displayed kickoff hour.
    @param minute Displayed kickoff minute.
    @return The candidate kickoff instant (Beijing time), or ``None`` when the
        pair is contradictory: the JS kickoff date and the displayed clock
        together must place the kickoff at or after the closing instant (the
        kickoff can never precede its own sales deadline). A contradiction is
        reported, never repaired with a guess.
    """
    candidate = datetime.strptime(day, "%Y-%m-%d").replace(
        hour=hour, minute=minute, tzinfo=SOURCE_TZ
    )
    if candidate < closing_at:
        candidate += timedelta(days=1)
    if candidate < closing_at:
        return None
    return candidate


def _beijing(day: str, hour: int, minute: int) -> datetime:
    return datetime.strptime(f"{day} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M").replace(
        tzinfo=SOURCE_TZ
    )


def _is_real_clock(value: str) -> bool:
    hour, minute = (int(part) for part in value.split(":"))
    return hour <= 23 and minute <= 59


def to_utc(value: datetime | None) -> datetime | None:
    """Convert an aware instant to UTC, preserving the instant exactly.

    @param value Aware datetime or ``None``.
    @return UTC datetime or ``None``.
    @raises IssueScheduleError for a naive datetime (which would silently be
        interpreted in the machine's local zone).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        raise IssueScheduleError("cannot convert a naive datetime to UTC")
    return value.astimezone(timezone.utc)


def canonical_issue_schedule(
    *,
    issue_id: str,
    rows: Iterable[dict[str, Any]],
    observed_at: str,
) -> list[dict[str, Any]]:
    """Build and validate the canonical table for one issue.

    @param issue_id Issue identifier.
    @param rows Canonical candidate rows, already reconciled across sources.
    @param observed_at ISO-8601 observation instant shared by every row.
    @return Validated canonical rows, ordered by slot.
    @raises IssueScheduleError on duplicate slots, missing keys, or unparsable
        timestamps.
    """
    validate_issue_id(issue_id)
    _validate_observed_at(observed_at)
    ordered = sorted(rows, key=lambda row: row["slot"])
    seen: set[int] = set()
    for row in ordered:
        slot = row["slot"]
        if slot in seen:
            raise IssueScheduleError(
                f"duplicate slot {slot} for issue {issue_id}: the canonical key is "
                "(issue_id, slot)"
            )
        seen.add(slot)
    validate_canonical(ordered)
    return ordered


def validate_canonical(rows: list[dict[str, Any]]) -> None:
    """Validate canonical invariants in place.

    @param rows Canonical rows.
    @raises IssueScheduleError when a row breaks the contract:
        unknown column, bad status/sale/date-source token, non-UTC timestamp, a
        kickoff instant paired with a kickoff clock that contradicts it, an
        empty name, a resolved identity without any provider id, a kickoff that
        precedes its own sales deadline, or an explicitly closed sale with a
        nonempty closing raw value.
    """
    columns = canonical_columns()
    for row in rows:
        extra = set(row) - set(columns)
        if extra:
            raise IssueScheduleError(f"unknown canonical columns: {sorted(extra)}")
        for column in columns:
            if column not in row:
                raise IssueScheduleError(f"canonical row is missing column {column}")
        if row["match_status"] not in MATCH_STATUSES:
            raise IssueScheduleError(
                f"slot {row['slot']}: unknown match_status {row['match_status']!r}"
            )
        if row["sale_state"] not in SALE_STATES:
            raise IssueScheduleError(
                f"slot {row['slot']}: unknown sale_state {row['sale_state']!r}"
            )
        if row["identity_method"] not in IDENTITY_MATCH_METHODS:
            raise IssueScheduleError(
                f"slot {row['slot']}: unknown identity_method {row['identity_method']!r}"
            )
        for column in ("observed_at", "kickoff_at", "sale_end_at"):
            value = row[column]
            if value is None:
                continue
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise IssueScheduleError(
                    f"slot {row['slot']}: {column} must be a timezone-aware datetime"
                )
            if value.utcoffset() != timedelta(0):
                raise IssueScheduleError(
                    f"slot {row['slot']}: {column} must be normalized to UTC"
                )
        for column, allowed in (
            ("kickoff_date_source", KICKOFF_DATE_SOURCES),
            ("sale_end_date_source", ("title-attribute", "absent")),
        ):
            if row[column] not in allowed:
                raise IssueScheduleError(
                    f"slot {row['slot']}: unknown {column} {row[column]!r}"
                )
        for column in ("home_name", "away_name"):
            if not str(row[column]).strip():
                raise IssueScheduleError(
                    f"slot {row['slot']}: {column} is empty; a match without both "
                    "sides is not a schedule row"
                )
        if row["issue_id"] != str(row["issue_id"]).strip():
            raise IssueScheduleError(
                f"slot {row['slot']}: issue_id {row['issue_id']!r} carries stray whitespace"
            )
        for column in ("provider_id", "provider_id_500", "provider_id_nowscore"):
            value = str(row[column])
            if value != value.strip():
                raise IssueScheduleError(
                    f"slot {row['slot']}: {column} carries stray whitespace; provider "
                    "identifiers are preserved verbatim"
                )
        kickoff = row["kickoff_at"]
        if kickoff is not None and row["kickoff_hhmm"] is not None:
            local_kickoff = kickoff.astimezone(SOURCE_TZ)
            resolved = (local_kickoff.hour, local_kickoff.minute)
            if resolved != tuple(int(part) for part in row["kickoff_hhmm"].split(":")):
                raise IssueScheduleError(
                    f"slot {row['slot']}: kickoff_at {kickoff.isoformat()} disagrees "
                    f"with kickoff_hhmm {row['kickoff_hhmm']!r}"
                )
        if kickoff is not None and row["kickoff_date_source"] == "absent":
            raise IssueScheduleError(
                f"slot {row['slot']}: kickoff_at is set but kickoff_date_source is 'absent'"
            )
        if kickoff is None and row["kickoff_date_source"] != "absent":
            raise IssueScheduleError(
                f"slot {row['slot']}: kickoff_date_source is "
                f"{row['kickoff_date_source']!r} but kickoff_at is missing"
            )
        closing = row["sale_end_at"]
        if kickoff is not None and closing is not None and kickoff < closing:
            raise IssueScheduleError(
                f"slot {row['slot']}: kickoff {kickoff.isoformat()} is before its own "
                f"sales deadline {closing.isoformat()}"
            )
        if not any(str(row[key]).strip() for key in (
            "provider_id_500", "provider_id_nowscore"
        )) and row["identity_method"] not in (
            "unresolved",
            "conflict",
        ):
            raise IssueScheduleError(
                f"slot {row['slot']}: no provider id at all but identity_method is "
                f"{row['identity_method']!r}"
            )
        if not str(row["source_url_nowscore"]).strip():
            raise IssueScheduleError(
                f"slot {row['slot']}: source_url_nowscore must be non-empty; a status "
                "without a source identity cannot be audited"
            )


def classify_match_status(
    *, nowscore_token: str, nowscore_score: str | None, can_sale: bool | None
) -> str:
    """Classify one nowscore row's match status from real evidence only.

    @param nowscore_token Visible text of nowscore's sale/status cell.
    @param nowscore_score Score text, ``None``/empty when absent.
    @param can_sale Nowscore's ``cansale`` attribute.
    @return One of ``MATCH_STATUSES``.
    @details Rules, each traceable to the frozen snapshot:
        · ``完场`` -> ``finished``. This is the only explicit finished token.
        · ``未``/``未开赛`` and the other explicit pre-match tokens ->
          ``scheduled``. Only a token that names the state counts.
        · ``截止`` -> ``unknown``, *not* ``finished``. Row 6 of 26098 is closed
          with no score, so the source never said the match ended.
        · ``推迟``/``延期`` -> ``postponed``; ``取消`` -> ``cancelled``;
          ``中断`` -> ``abandoned``; live tokens -> ``live``.
        · A bare ``HH:mm``, ``截止`` or an empty token is a *sale* display and
          carries no match-status evidence at all: it is always ``unknown``.
          ``cansale`` is a page-refresh artefact about the sale window and
          **never** promotes a row to ``scheduled`` — a match on sale is not
          evidence that it has not started.
    """
    token = (nowscore_token or "").strip()
    if token == "完场":
        return "finished"
    if "推迟" in token or "延期" in token:
        return "postponed"
    if "取消" in token:
        return "cancelled"
    if "中断" in token or "腰斩" in token:
        return "abandoned"
    if token in {"上", "中", "下", "加", "点"} or "中场" in token or "半场" in token or "'" in token:
        return "live"
    if token in {"未", "未开赛", "未开始", "未开"}:
        return "scheduled"
    return "unknown"


def classify_sale_state(
    can_sale: bool | None, sale_end_at: datetime | None, observed: datetime
) -> str:
    """Classify the sale window of one match.

    @param can_sale Source's explicit sale flag, ``None`` when absent.
    @param sale_end_at Parsed closing instant, ``None`` when the source gave no
        full date.
    @param observed Observation instant (UTC).
    @return One of SALE_STATES. An explicit false sale flag stays closed even
        before a published deadline (suspension is possible). At or after the
        deadline the sale is closed; before it only an explicit true flag
        establishes open. Missing evidence remains unknown.
    """
    if can_sale is False or (sale_end_at is not None and observed >= sale_end_at):
        return "closed"
    if can_sale is True:
        return "open"
    return "unknown"


def _validate_observed_at(observed_at: str) -> None:
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise IssueScheduleError("observed_at must be a non-empty ISO-8601 string")
    try:
        datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise IssueScheduleError(f"observed_at {observed_at!r} is not ISO-8601") from error


def _validate_clock(value: str, *, field: str) -> None:
    match = _HHMM_RE.match(value)
    if match is None:
        raise IssueScheduleError(f"{field}: {value!r} is not HH:MM")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise IssueScheduleError(f"{field}: {value!r} is not a valid clock time")
