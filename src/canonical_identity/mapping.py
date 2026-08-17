"""Outcome-unexposed canonical fixture mapping for Issue #251.

Only an exact `(issue_code, match_idx)` source slot becomes a canonical fixture.
Names, schedules, and fuzzy scores are diagnostic evidence only: none may create
an automatic match.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

import pandas as pd


TRACE_COLUMNS = (
    "source_id",
    "source_key",
    "source_competition_key",
    "source_home_team_key",
    "source_away_team_key",
    "fixture_id",
    "issue_code",
    "match_idx",
    "competition_id",
    "home_team_id",
    "away_team_id",
    "kickoff_at_utc",
    "causal_grade",
    "identity_status",
    "rule_version",
)
LEDGER_COLUMNS = (
    "exception_class",
    "disposition",
    "source_id",
    "source_key",
    "fixture_id",
    "detail",
    "rule_version",
)
RULE_VERSION = "BJ-UNIFIED-CANONICAL-IDENTITY-001-v1"


@dataclass(frozen=True)
class IdentityRecord:
    source_id: str
    source_key: str
    issue_code: str | None
    match_idx: int | None
    competition_alias: str | None
    home_alias: str | None
    away_alias: str | None
    kickoff_at_utc: str | None
    causal_grade: str


@dataclass(frozen=True)
class FuzzyCandidate:
    source_id: str
    source_key: str
    candidate_fixture_id: str
    confidence: float
    reason: str


@dataclass
class MappingResult:
    fixtures: pd.DataFrame
    traces: pd.DataFrame
    ledger: pd.DataFrame


def _normalise_label(value: str | None, prefix: str) -> str:
    """Produce an exact, deterministic label key without fuzzy equivalence."""
    if value is None:
        return f"{prefix}:unidentified"
    cleaned = " ".join(unicodedata.normalize("NFKC", str(value)).strip().casefold().split())
    if not cleaned:
        return f"{prefix}:unidentified"
    return f"{prefix}:{cleaned}"


def _valid_slot(issue_code: str | None, match_idx: int | None) -> bool:
    if issue_code is None or match_idx is None:
        return False
    issue = str(issue_code).strip()
    if not issue or not re.fullmatch(r"[0-9]+", issue):
        return False
    try:
        slot = int(match_idx)
    except (TypeError, ValueError):
        return False
    return slot > 0


def canonical_fixture_id(issue_code: str, match_idx: int) -> str:
    """Stable natural fixture identifier; deliberately has no outcome argument."""
    if not _valid_slot(issue_code, match_idx):
        raise ValueError("canonical fixture requires a numeric issue_code and positive match_idx")
    return f"bjfi:{str(issue_code).strip()}:{int(match_idx):03d}"


def _empty(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def reject_fuzzy_candidates(candidates: list[FuzzyCandidate]) -> pd.DataFrame:
    """Materialise fuzzy suggestions as manual-review evidence, never mappings."""
    rows = [
        {
            "exception_class": "FUZZY_CANDIDATE",
            "disposition": "MANUAL_REVIEW",
            "source_id": item.source_id,
            "source_key": item.source_key,
            "fixture_id": item.candidate_fixture_id,
            "detail": f"confidence={item.confidence:.6f}; {item.reason}",
            "rule_version": RULE_VERSION,
            "identity_status": "UNIDENTIFIED",
        }
        for item in candidates
    ]
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=[*LEDGER_COLUMNS, "identity_status"]
    )


def map_records(records: list[IdentityRecord]) -> MappingResult:
    """Map exact source slots and surface all non-exact/conflicting rows.

    A canonical fixture is produced exclusively from the issue slot.  Every
    resolved row retains its source key and rule version, making automatic
    matches reproducible and independently replayable.
    """
    trace_rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []
    for item in records:
        if not _valid_slot(item.issue_code, item.match_idx):
            ledger_rows.append(
                {
                    "exception_class": "MISSING_CANONICAL_SLOT",
                    "disposition": "QUARANTINED",
                    "source_id": item.source_id,
                    "source_key": item.source_key,
                    "fixture_id": "",
                    "detail": "issue_code and match_idx must both be populated and valid",
                    "rule_version": RULE_VERSION,
                }
            )
            continue
        issue_code = str(item.issue_code).strip()
        match_idx = int(item.match_idx)  # _valid_slot proved conversion
        trace_rows.append(
            {
                "source_id": item.source_id,
                "source_key": item.source_key,
                "source_competition_key": item.competition_alias or "",
                "source_home_team_key": item.home_alias or "",
                "source_away_team_key": item.away_alias or "",
                "fixture_id": canonical_fixture_id(issue_code, match_idx),
                "issue_code": issue_code,
                "match_idx": match_idx,
                "competition_id": _normalise_label(item.competition_alias, "competition"),
                "home_team_id": _normalise_label(item.home_alias, "team"),
                "away_team_id": _normalise_label(item.away_alias, "team"),
                "kickoff_at_utc": item.kickoff_at_utc or "",
                "causal_grade": item.causal_grade,
                "identity_status": "ALIAS",
                "rule_version": RULE_VERSION,
            }
        )

    traces = pd.DataFrame(trace_rows, columns=list(TRACE_COLUMNS)) if trace_rows else _empty(TRACE_COLUMNS)
    if not traces.empty:
        duplicate = traces.duplicated(["source_id", "fixture_id"], keep=False)
        for _, row in traces.loc[duplicate].iterrows():
            ledger_rows.append(
                {
                    "exception_class": "DUPLICATE_SOURCE_FIXTURE",
                    "disposition": "MANUAL_REVIEW",
                    "source_id": row["source_id"],
                    "source_key": row["source_key"],
                    "fixture_id": row["fixture_id"],
                    "detail": "source emitted more than one row for the exact issue slot",
                    "rule_version": RULE_VERSION,
                }
            )
            traces.loc[(traces["source_id"] == row["source_id"]) & (traces["fixture_id"] == row["fixture_id"]), "identity_status"] = "AMBIGUOUS"

        identity_columns = ["competition_id", "home_team_id", "away_team_id"]
        for fixture_id, group in traces.groupby("fixture_id", sort=True):
            if len(group) < 2:
                continue
            if len(group[identity_columns].drop_duplicates()) > 1:
                # The exact issue slot remains the canonical fixture match.
                # Only the entity-alias evidence is unresolved; treating that
                # as a fuzzy fixture failure would discard a deterministic key.
                ledger_rows.append(
                    {
                        "exception_class": "CROSS_SOURCE_ENTITY_ALIAS_CONFLICT",
                        "disposition": "MANUAL_REVIEW",
                        "source_id": "MULTI_SOURCE",
                        "source_key": ";".join(
                            f"{row['source_id']}:{row['source_key']}"
                            for _, row in group.sort_values(["source_id", "source_key"], kind="stable").iterrows()
                        ),
                        "fixture_id": fixture_id,
                        "detail": "exact issue slot mapped; competition or team aliases require temporal provenance",
                        "rule_version": RULE_VERSION,
                    }
                )

    fixture_rows: list[dict[str, object]] = []
    for fixture_id, group in traces.groupby("fixture_id", sort=True):
        representative = group.sort_values(["source_id", "source_key"], kind="stable").iloc[0]
        fixture_rows.append(
            {
                "fixture_id": fixture_id,
                "issue_code": representative["issue_code"],
                "match_idx": int(representative["match_idx"]),
                "identity_status": "AMBIGUOUS" if (group["identity_status"] == "AMBIGUOUS").any() else "CANONICAL",
                "source_count": int(group["source_id"].nunique()),
                "rule_version": RULE_VERSION,
            }
        )
    fixtures = pd.DataFrame(fixture_rows, columns=["fixture_id", "issue_code", "match_idx", "identity_status", "source_count", "rule_version"])
    ledger = pd.DataFrame(ledger_rows, columns=list(LEDGER_COLUMNS)) if ledger_rows else _empty(LEDGER_COLUMNS)
    return MappingResult(fixtures=fixtures, traces=traces.sort_values(["source_id", "source_key"], kind="stable").reset_index(drop=True), ledger=ledger)
