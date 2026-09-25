"""Authoritative Beijing single-game (北单) issue-schedule parsing.

Split into pure, testable pieces so that fetching, parsing, validation and
persistence never blur together:

``decode``     bytes -> text with the *source-declared* charset, no guessing.
``sources``    one parser per provider; returns raw-faithful provider rows.
``crosscheck`` cross-source identity reconciliation with explicit evidence.
``contract``   the canonical per-match schema and its validators.
``fetch``      the only module that touches the network (bounded, explicit).
``store``      explicit raw-byte / parsed-row / metadata persistence.

Importing any module here performs no I/O and no network access.
"""

from .contract import (
    CANONICAL_NOWSCORE_URL,
    CANONICAL_500_URL,
    IssueScheduleError,
    MatchStatusError,
    canonical_columns,
    canonical_issue_schedule,
    nowscore_url,
    resolve_kickoff_at,
    source_500_url,
    validate_canonical,
)
from .crosscheck import (
    CrossSourceError,
    identity_candidates,
    name_agreement,
    normalize_team_name,
    pick_score,
    reconcile_identity,
)
from .decode import DecodeError, decode_response, declared_charset
from .fetch import FetchError, FetchResponse, fetch_issue_page
from .service import IssueScheduleResult, fetch_issue_schedule
from .sources import (
    SourceParseError,
    parse_500_rows,
    parse_nowscore_kickoff_dates,
    parse_nowscore_rows,
)
from .store import (
    PersistError,
    new_fetch_directory,
    persist_issue_meta,
    persist_issue_raw,
)

__all__ = [
    "CANONICAL_500_URL",
    "CANONICAL_NOWSCORE_URL",
    "CrossSourceError",
    "DecodeError",
    "FetchError",
    "FetchResponse",
    "IssueScheduleError",
    "IssueScheduleResult",
    "MatchStatusError",
    "PersistError",
    "SourceParseError",
    "canonical_columns",
    "canonical_issue_schedule",
    "declared_charset",
    "decode_response",
    "fetch_issue_page",
    "fetch_issue_schedule",
    "identity_candidates",
    "name_agreement",
    "new_fetch_directory",
    "normalize_team_name",
    "nowscore_url",
    "parse_500_rows",
    "parse_nowscore_kickoff_dates",
    "parse_nowscore_rows",
    "pick_score",
    "persist_issue_meta",
    "persist_issue_raw",
    "reconcile_identity",
    "resolve_kickoff_at",
    "source_500_url",
    "validate_canonical",
]
