"""Outcome-unexposed identity mapping for Issue #251.

The source data proves an issue-local slot, not a refresh-stable real-world
fixture.  This module therefore keeps ``issue_slot_id`` separate from the
nullable ``fixture_entity_id`` and never creates cross-source entities from
fuzzy or merely normalised labels.
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
    "issue_id",
    "issue_slot_id",
    "fixture_entity_id",
    "issue_code",
    "match_idx",
    "source_competition_entity_id",
    "source_home_team_entity_id",
    "source_away_team_entity_id",
    "canonical_competition_id",
    "canonical_home_team_id",
    "canonical_away_team_id",
    "competition_resolution_status",
    "home_team_resolution_status",
    "away_team_resolution_status",
    "kickoff_at_utc",
    "causal_grade",
    "slot_identity_status",
    "fixture_entity_status",
    "rule_version",
)
LEDGER_COLUMNS = (
    "exception_class",
    "disposition",
    "source_id",
    "source_key",
    "issue_slot_id",
    "entity_kind",
    "detail",
    "rule_version",
)
RULE_VERSION = "BJ-UNIFIED-CANONICAL-IDENTITY-001-v2"
PLAY_CODE = "BJ_HANDICAP_3WAY"
OUTCOME_CODES = ("3", "1", "0")


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
    candidate_issue_slot_id: str
    confidence: float
    reason: str


@dataclass
class MappingResult:
    issues: pd.DataFrame
    slots: pd.DataFrame
    plays: pd.DataFrame
    outcome_cells: pd.DataFrame
    traces: pd.DataFrame
    ledger: pd.DataFrame


def _clean_label(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(unicodedata.normalize("NFKC", str(value)).strip().casefold().split())
    return cleaned or None


def _source_local_entity_id(value: str | None, kind: str, source_id: str) -> str | None:
    cleaned = _clean_label(value)
    return None if cleaned is None else f"source:{source_id}:{kind}:{cleaned}"


def _canonical_entity_id(value: str, kind: str) -> str:
    cleaned = _clean_label(value)
    if cleaned is None:
        raise ValueError("canonical entity requires a nonblank exact label")
    return f"{kind}:{cleaned}"


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


def issue_id(issue_code: str) -> str:
    if not _valid_slot(issue_code, 1):
        raise ValueError("issue identity requires a numeric issue_code")
    return f"bjissue:{str(issue_code).strip()}"


def issue_slot_id(issue_code: str, match_idx: int) -> str:
    """Deterministic issue-local slot key; not a real-world fixture entity."""
    if not _valid_slot(issue_code, match_idx):
        raise ValueError("issue slot requires a numeric issue_code and positive match_idx")
    return f"bjslot:{str(issue_code).strip()}:{int(match_idx):03d}"


def play_id(slot_id: str, play_code: str = PLAY_CODE) -> str:
    if not isinstance(slot_id, str) or not slot_id.startswith("bjslot:"):
        raise ValueError("play identity requires a valid issue_slot_id")
    if play_code != PLAY_CODE:
        raise ValueError(f"unsupported play_code: {play_code}")
    return f"bjplay:{slot_id.removeprefix('bjslot:')}:{play_code}"


def outcome_cell_id(slot_id: str, outcome_code: str) -> str:
    if outcome_code not in OUTCOME_CODES:
        raise ValueError(f"unsupported outcome_code: {outcome_code}")
    return f"bjcell:{slot_id.removeprefix('bjslot:')}:{PLAY_CODE}:{outcome_code}"


def _empty(columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(columns))


def _ledger_row(
    *,
    exception_class: str,
    disposition: str,
    source_id: str,
    source_key: str,
    slot_id: str = "",
    entity_kind: str = "",
    detail: str,
) -> dict[str, object]:
    return {
        "exception_class": exception_class,
        "disposition": disposition,
        "source_id": source_id,
        "source_key": source_key,
        "issue_slot_id": slot_id,
        "entity_kind": entity_kind,
        "detail": detail,
        "rule_version": RULE_VERSION,
    }


def reject_fuzzy_candidates(candidates: list[FuzzyCandidate]) -> pd.DataFrame:
    """Materialise fuzzy suggestions as review evidence, never mappings."""
    rows = [
        _ledger_row(
            exception_class="FUZZY_CANDIDATE",
            disposition="MANUAL_REVIEW",
            source_id=item.source_id,
            source_key=item.source_key,
            slot_id=item.candidate_issue_slot_id,
            detail=f"confidence={item.confidence:.6f}; {item.reason}",
        )
        for item in candidates
    ]
    return pd.DataFrame(rows, columns=list(LEDGER_COLUMNS)) if rows else _empty(LEDGER_COLUMNS)


def _identity_tables(traces: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    slot_columns = (
        "issue_slot_id",
        "issue_id",
        "issue_code",
        "match_idx",
        "fixture_entity_id",
        "slot_identity_status",
        "fixture_entity_status",
        "source_count",
        "rule_version",
    )
    if traces.empty:
        return (
            _empty(("issue_id", "issue_code", "rule_version")),
            _empty(slot_columns),
            _empty(("play_id", "issue_slot_id", "play_code", "rule_version")),
            _empty(("outcome_cell_id", "play_id", "issue_slot_id", "outcome_code", "rule_version")),
        )
    ordered = traces.sort_values(
        ["issue_slot_id", "source_id", "source_key"], kind="stable"
    )
    slots = ordered.drop_duplicates("issue_slot_id", keep="first").loc[
        :, ["issue_slot_id", "issue_id", "issue_code", "match_idx"]
    ]
    source_counts = (
        traces.groupby("issue_slot_id", sort=False)["source_id"]
        .nunique()
        .rename("source_count")
    )
    slots = slots.join(source_counts, on="issue_slot_id")
    slots["fixture_entity_id"] = ""
    slots["slot_identity_status"] = "EXACT_SLOT"
    slots["fixture_entity_status"] = "UNRESOLVED_NO_STABLE_KEY"
    slots["rule_version"] = RULE_VERSION
    slots = slots.loc[:, list(slot_columns)].sort_values("issue_slot_id", kind="stable").reset_index(drop=True)
    issues = slots[["issue_id", "issue_code"]].drop_duplicates().sort_values("issue_id", kind="stable")
    issues["rule_version"] = RULE_VERSION
    plays = slots[["issue_slot_id"]].copy()
    plays.insert(0, "play_id", plays["issue_slot_id"].map(play_id))
    plays["play_code"] = PLAY_CODE
    plays["rule_version"] = RULE_VERSION
    cells = slots.loc[slots.index.repeat(len(OUTCOME_CODES)), ["issue_slot_id"]].reset_index(drop=True)
    cells["outcome_code"] = list(OUTCOME_CODES) * len(slots)
    cells["play_id"] = cells["issue_slot_id"].map(play_id)
    cells["outcome_cell_id"] = [
        outcome_cell_id(slot_id, code)
        for slot_id, code in zip(cells["issue_slot_id"], cells["outcome_code"], strict=True)
    ]
    cells["rule_version"] = RULE_VERSION
    cells = cells.loc[
        :, ["outcome_cell_id", "play_id", "issue_slot_id", "outcome_code", "rule_version"]
    ]
    return issues.reset_index(drop=True), slots, plays, cells


def map_records(records: list[IdentityRecord]) -> MappingResult:
    """Map exact issue slots and truthfully expose unresolved entity identity."""
    trace_rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []
    for item in records:
        if not _valid_slot(item.issue_code, item.match_idx):
            ledger_rows.append(
                _ledger_row(
                    exception_class="MISSING_ISSUE_SLOT",
                    disposition="QUARANTINED",
                    source_id=item.source_id,
                    source_key=item.source_key,
                    detail="issue_code and match_idx must both be populated and valid",
                )
            )
            continue
        issue_code = str(item.issue_code).strip()
        match_idx = int(item.match_idx)
        slot_id = issue_slot_id(issue_code, match_idx)
        aliases = {
            "competition": item.competition_alias,
            "home_team": item.home_alias,
            "away_team": item.away_alias,
        }
        for kind, alias in aliases.items():
            if _clean_label(alias) is None:
                ledger_rows.append(
                    _ledger_row(
                        exception_class="MISSING_ENTITY_LABEL",
                        disposition="UNIDENTIFIED",
                        source_id=item.source_id,
                        source_key=item.source_key,
                        slot_id=slot_id,
                        entity_kind=kind,
                        detail="raw source label is missing; entity id remains null",
                    )
                )
        trace_rows.append(
            {
                "source_id": item.source_id,
                "source_key": item.source_key,
                "source_competition_key": item.competition_alias or "",
                "source_home_team_key": item.home_alias or "",
                "source_away_team_key": item.away_alias or "",
                "issue_id": issue_id(issue_code),
                "issue_slot_id": slot_id,
                "fixture_entity_id": "",
                "issue_code": issue_code,
                "match_idx": match_idx,
                "source_competition_entity_id": _source_local_entity_id(
                    item.competition_alias, "competition", item.source_id
                )
                or "",
                "source_home_team_entity_id": _source_local_entity_id(
                    item.home_alias, "team", item.source_id
                )
                or "",
                "source_away_team_entity_id": _source_local_entity_id(
                    item.away_alias, "team", item.source_id
                )
                or "",
                "canonical_competition_id": "",
                "canonical_home_team_id": "",
                "canonical_away_team_id": "",
                "competition_resolution_status": "UNIDENTIFIED"
                if _clean_label(item.competition_alias) is None
                else "SOURCE_LOCAL_ONLY",
                "home_team_resolution_status": "UNIDENTIFIED"
                if _clean_label(item.home_alias) is None
                else "SOURCE_LOCAL_ONLY",
                "away_team_resolution_status": "UNIDENTIFIED"
                if _clean_label(item.away_alias) is None
                else "SOURCE_LOCAL_ONLY",
                "kickoff_at_utc": item.kickoff_at_utc or "",
                "causal_grade": item.causal_grade,
                "slot_identity_status": "EXACT_SLOT",
                "fixture_entity_status": "UNRESOLVED_NO_STABLE_KEY",
                "rule_version": RULE_VERSION,
            }
        )

    traces = (
        pd.DataFrame(trace_rows, columns=list(TRACE_COLUMNS))
        if trace_rows
        else _empty(TRACE_COLUMNS)
    )
    if not traces.empty:
        duplicate = traces.duplicated(["source_id", "issue_slot_id"], keep=False)
        duplicate_rows = traces.loc[duplicate].copy()
        for _, row in duplicate_rows.iterrows():
            ledger_rows.append(
                _ledger_row(
                    exception_class="DUPLICATE_SOURCE_SLOT",
                    disposition="QUARANTINED",
                    source_id=str(row["source_id"]),
                    source_key=str(row["source_key"]),
                    slot_id=str(row["issue_slot_id"]),
                    detail="source emitted more than one row for the exact issue slot",
                )
            )
        traces = traces.loc[~duplicate].copy()

        entity_specs = (
            (
                "competition",
                "source_competition_key",
                "canonical_competition_id",
                "competition_resolution_status",
            ),
            ("home_team", "source_home_team_key", "canonical_home_team_id", "home_team_resolution_status"),
            ("away_team", "source_away_team_key", "canonical_away_team_id", "away_team_resolution_status"),
        )
        slot_key = traces["issue_slot_id"]
        group_size = traces.groupby("issue_slot_id", sort=False)["source_id"].transform("size")
        for kind, source_column, canonical_column, status_column in entity_specs:
            cleaned = traces[source_column].map(_clean_label)
            nonnull_count = cleaned.notna().groupby(slot_key, sort=False).transform("sum")
            unique_count = cleaned.groupby(slot_key, sort=False).transform("nunique")
            exact = group_size.ge(2) & unique_count.eq(1) & nonnull_count.eq(group_size)
            prefix = "competition" if kind == "competition" else "team"
            traces.loc[exact, canonical_column] = cleaned.loc[exact].map(
                lambda value: _canonical_entity_id(str(value), prefix)
            )
            traces.loc[exact, status_column] = "EXACT_CROSS_SOURCE"

            conflict = unique_count.gt(1)
            traces.loc[conflict, status_column] = "UNRESOLVED_CONFLICT"
            if conflict.any():
                evidence = traces.loc[
                    conflict, ["issue_slot_id", "source_id", "source_key"]
                ].sort_values(
                    ["issue_slot_id", "source_id", "source_key"], kind="stable"
                )
                evidence["source_pair"] = (
                    evidence["source_id"].astype(str)
                    + ":"
                    + evidence["source_key"].astype(str)
                )
                pairs = evidence.groupby("issue_slot_id", sort=True)["source_pair"].agg(";".join)
                ledger_rows.extend(
                    _ledger_row(
                        exception_class="CROSS_SOURCE_ENTITY_ALIAS_CONFLICT",
                        disposition="UNRESOLVED",
                        source_id="MULTI_SOURCE",
                        source_key=str(source_pair),
                        slot_id=str(slot_id),
                        entity_kind=kind,
                        detail="exact issue slot mapped; entity labels disagree across sources",
                    )
                    for slot_id, source_pair in pairs.items()
                )

    traces = traces.sort_values(["source_id", "source_key"], kind="stable").reset_index(drop=True)
    issues, slots, plays, cells = _identity_tables(traces)
    ledger = (
        pd.DataFrame(ledger_rows, columns=list(LEDGER_COLUMNS))
        if ledger_rows
        else _empty(LEDGER_COLUMNS)
    )
    return MappingResult(
        issues=issues,
        slots=slots,
        plays=plays,
        outcome_cells=cells,
        traces=traces,
        ledger=ledger,
    )
