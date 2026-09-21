"""Read the live board's own issue list, so routine discovery needs one request.

The historical inventory walks a candidate space (years x months x serial ceilings) and
probes all 22,437 of them to claim complete coverage, which costs 12.6 hours at the source's
two-second pacing to find about 1,700 issues. That is only necessary once, when the history is
unknown. Afterwards the source states its own issue list on an unscheduled live page:

    var IssueNum = "26096"; var IsCurrentIssue = "True";
    <select id='dropIssueNum'><option selected value='26096'>...

so a routine update asks one page for the current issue and the issues still listed beside
it. The last fixture's kickoff on that page bounds when the next issue can start, which is
enough to schedule the check instead of polling.

No fetching happens here: the caller supplies the page bytes.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_SELECT = re.compile(r"id=['\"]dropIssueNum['\"].*?</select>", re.S)
_OPTION = re.compile(r"value=['\"](\d{5,6})['\"]")
_CURRENT = re.compile(r"var\s+IssueNum\s*=\s*['\"](\d{5,6})['\"]")
_IS_CURRENT = re.compile(r"var\s+IsCurrentIssue\s*=\s*['\"](\w+)['\"]")
_KICKOFF = re.compile(r"<td[^>]*>\s*(\d{2}):(\d{2})\s*</td>")
_PAGE_DATE = re.compile(r"name=['\"](\d{4}-\d{2}-\d{2})['\"]")


class LiveIssueError(ValueError):
    """Raised when a live board page does not carry its issue list."""


def live_issues(payload: bytes) -> dict:
    """Return the issues the live board advertises, newest first.

    ``issues`` is the board's own list -- the current issue plus the ones still on sale --
    so a caller never has to guess a serial. ``current`` is the issue the board selects, and
    ``is_current`` distinguishes a board that is between rounds from one showing a past
    issue. Raises when the list is absent: an empty answer would silently look like "no new
    issues".
    """
    html = payload.decode("utf-8", "replace")
    select = _SELECT.search(html)
    if select is None:
        raise LiveIssueError("live page carries no issue list")
    issues: list[str] = []
    for value in _OPTION.findall(select.group(0)):
        if value not in issues:
            issues.append(value)
    if not issues:
        raise LiveIssueError("issue list is empty")
    current = _CURRENT.search(html)
    flagged = _IS_CURRENT.search(html)
    return {"issues": issues,
            "current": current.group(1) if current else issues[0],
            "is_current": (flagged.group(1).lower() == "true") if flagged else None}


def next_issue_after(issues: list[str], known_max: str) -> list[str]:
    """Return the advertised issues newer than ``known_max``, oldest first.

    Issue identifiers sort chronologically, so the comparison is a string one. A known_max
    the board no longer lists means the gap is wider than the list; that is reported by the
    caller as "too far behind" rather than silently treated as nothing to add.
    """
    newer = [issue for issue in issues if issue > known_max]
    if not newer:
        return []
    oldest_advertised = min(issues)
    if known_max < oldest_advertised and known_max not in issues:
        missing = f"the board lists {oldest_advertised} and later; {known_max} is not on it"
        raise LiveIssueError(f"cannot tell how many issues are missing: {missing}")
    return sorted(newer)


def last_kickoff(payload: bytes, *, today: datetime | None = None) -> datetime | None:
    """Estimate when the last advertised fixture starts, to schedule the next check.

    The board renders kickoff times without a date and carries the round's date in a row
    attribute, so the date is taken from the page and the time from the latest cell. Returns
    None when the page does not carry both, which makes the caller fall back to a fixed
    polling interval rather than guessing.
    """
    html = payload.decode("utf-8", "replace")
    date = _PAGE_DATE.search(html)
    if date is None:
        return None
    times = _KICKOFF.findall(html)
    if not times:
        return None
    latest = max(times)
    day = datetime.fromisoformat(date.group(1))
    return day.replace(hour=int(latest[0]), minute=int(latest[1])) + timedelta(minutes=1)
