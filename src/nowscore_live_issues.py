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
from datetime import datetime, timedelta, timezone

_SELECT = re.compile(r"id=['\"]dropIssueNum['\"].*?</select>", re.S)
_OPTION = re.compile(r"value=['\"](\d{5,6})['\"]")
_CURRENT = re.compile(r"var\s+IssueNum\s*=\s*['\"](\d{5,6})['\"]")
_IS_CURRENT = re.compile(r"var\s+IsCurrentIssue\s*=\s*['\"](\w+)['\"]")
_ROW = re.compile(r"<tr\b.*?</tr>", re.S)
_ROW_DATE = re.compile(r"name=['\"](\d{4}-\d{2}-\d{2})['\"]")
_CLOCK = re.compile(r"<td[^>]*>\s*(\d{2}):(\d{2})\s*</td>")


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


def pending_issues(advertised: list[str], release_issues) -> list[str]:
    """Return the advertised issues the release does not already carry, oldest first.

    Membership, not the release's newest issue, decides what is pending. Using the newest
    issue as a watermark loses an issue that was advertised, refused, and then overtaken: a
    later issue settles, the release's maximum moves past the refused one, and every later run
    skips it while the board still advertises it.

    The board only lists the issues still on sale, so a gap older than the list cannot be
    sized from it: when the release's newest issue is older than the oldest advertised one,
    the number of missing issues is unknown and the caller is told so rather than given [].
    """
    advertised = sorted(advertised)
    if not advertised:
        raise LiveIssueError("the board advertised no issues")
    carried = {str(issue) for issue in release_issues}
    if carried == set(advertised):
        return []
    if carried and max(carried) < advertised[0] and not (carried & set(advertised)):
        raise LiveIssueError(
            f"cannot tell how many issues are missing: the board lists {advertised[0]} and "
            f"later, the release newest is {max(carried)}")
    return [issue for issue in advertised if issue not in carried]


def last_kickoff(payload: bytes) -> datetime | None:
    """Estimate when the round's last fixture starts, to schedule the next check.

    A round can span days, so the date is read from each fixture's own row rather than from
    whichever row happens to come first, and the latest paired (date, kickoff) wins. The
    board renders times without a zone and is a China-facing site, so the result carries the
    source's +08:00 offset; returning naive time would make the scheduling decision depend on
    the reader's locale. Returns None when no row yields both, so the caller polls instead.
    """
    html = payload.decode("utf-8", "replace")
    paired: list[datetime] = []
    for row in _ROW.finditer(html):
        date = _ROW_DATE.search(row.group(0))
        clock = _CLOCK.search(row.group(0))
        if date is None or clock is None:
            continue
        paired.append(datetime.fromisoformat(date.group(1)).replace(
            hour=int(clock.group(1)), minute=int(clock.group(2)),
            tzinfo=timezone(timedelta(hours=8))))
    if not paired:
        return None
    return max(paired) + timedelta(minutes=1)
