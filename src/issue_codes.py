"""The issue code itself is the authority for an issue's year.

An issue code is the zero-padded `YY` year followed by the round within that year: six digits
(`YYMMNN`) cover 2009-2019 and five digits (`YYNNN`) cover 2020 onward, and the two ranges do not
overlap. The year is therefore always `2000 + int(code[:2])`.

Why this exists as one implementation: the registry table that used to answer "which year is this
issue?" was `data/derived/500_bjdc/500_bjdc.sqlite`, a store of the retired 500 live-refresh line.
Its `issues.year` agreed with this derivation on all 2152 rows it held, so the table never carried
information the code did not already contain -- and the same two-line derivation had been copied
into a dozen modules, one of which used a different rule.
"""

from __future__ import annotations

ISSUE_CODE_LENGTHS = (5, 6)

#: The value an issue's `issue_date_source` carries: it names the issue-level authority for the
#: year, which is this module. The value itself is deliberately unchanged from when that authority
#: was a registry table, because sealed packages record it and are replayed against it -- renaming
#: the value fails the replay of packages that are already frozen. The name is what a reader
#: follows; the value is what the seals hold.
SOURCE_ISSUE_DATE_SOURCE = "SOURCE_ISSUE_REGISTRY_YEAR"

#: First code that uses the five-digit form, and the first that uses the six-digit form.
_FIVE_DIGIT_FROM_YY = 20


class IssueCodeError(ValueError):
    """An issue code that cannot name a year."""


def issue_year(issue: object) -> int:
    """Return the year an issue code names.

    Raises `IssueCodeError` rather than returning a guess: a code that does not match the format
    has no year, and silently deriving one from its first two digits would date rows by whatever
    the malformed value happened to start with.
    """
    code = str(issue).strip()
    # isascii matters: str.isdigit() accepts full-width digits and int() converts them, so a
    # full-width code would silently derive a year from characters no source uses.
    if len(code) not in ISSUE_CODE_LENGTHS or not (code.isascii() and code.isdigit()):
        raise IssueCodeError(
            f"issue code must be {ISSUE_CODE_LENGTHS[0]} or {ISSUE_CODE_LENGTHS[1]} digits, got {issue!r}"
        )
    yy = int(code[:2])
    if len(code) == 5 and yy < _FIVE_DIGIT_FROM_YY:
        raise IssueCodeError(
            f"five-digit issue code {code!r} predates the five-digit range (20xx onward)"
        )
    return 2000 + yy
