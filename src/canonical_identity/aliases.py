"""Temporal, provenance-bound team and competition alias resolution."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


ALIAS_COLUMNS = (
    "alias_kind",
    "source_id",
    "source_alias",
    "entity_id",
    "valid_from_utc",
    "valid_to_utc",
    "validity_semantics",
    "provenance",
)


@dataclass(frozen=True)
class AliasResolution:
    status: str
    entity_id: str | None
    alias_kind: str
    source_id: str
    source_alias: str
    asof_utc: str


def _timestamps(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(ALIAS_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"alias table missing columns: {sorted(missing)}")
    value = frame.loc[:, ALIAS_COLUMNS].copy()
    value["valid_from_utc"] = pd.to_datetime(value["valid_from_utc"], utc=True, errors="raise")
    value["valid_to_utc"] = pd.to_datetime(value["valid_to_utc"], utc=True, errors="raise")
    if value["provenance"].isna().any() or value["provenance"].astype(str).str.strip().eq("").any():
        raise ValueError("every temporal alias requires provenance")
    if not value["alias_kind"].isin({"team", "competition"}).all():
        raise ValueError("alias_kind must be team or competition")
    if not value["validity_semantics"].eq("OBSERVED_FIRST_LAST_NOT_AUTHORITATIVE").all():
        raise ValueError("observed aliases require explicit diagnostic validity semantics")
    return value


def validate_alias_intervals(frame: pd.DataFrame) -> None:
    """Reject ambiguous/invalid aliases before they can resolve any identity."""
    value = _timestamps(frame)
    for (alias_kind, source_id, source_alias), group in value.groupby(
        ["alias_kind", "source_id", "source_alias"], dropna=False
    ):
        ordered = group.sort_values("valid_from_utc", kind="stable")
        previous_end: pd.Timestamp | None = None
        for position, (_, row) in enumerate(ordered.iterrows()):
            start = pd.Timestamp(row["valid_from_utc"])
            raw_end = row["valid_to_utc"]
            end = None if pd.isna(raw_end) else pd.Timestamp(raw_end)
            if pd.notna(end) and end < start:
                raise ValueError(f"invalid interval for {(alias_kind, source_id, source_alias)}")
            if previous_end is None and len(ordered) > 1 and position > 0:
                raise ValueError(f"overlapping aliases for {(alias_kind, source_id, source_alias)}")
            if previous_end is not None and start <= previous_end:
                raise ValueError(f"overlapping aliases for {(alias_kind, source_id, source_alias)}")
            previous_end = end


def resolve_alias(
    frame: pd.DataFrame,
    alias_kind: str,
    source_id: str,
    source_alias: str,
    asof_utc: str,
) -> AliasResolution:
    """Resolve one exact, kind-aware source-local alias observation."""
    validate_alias_intervals(frame)
    value = _timestamps(frame)
    asof = pd.Timestamp(asof_utc)
    if asof.tzinfo is None:
        raise ValueError("asof_utc must be timezone-aware")
    rows = value.loc[
        value["alias_kind"].eq(alias_kind)
        & value["source_id"].eq(source_id)
        & value["source_alias"].eq(source_alias)
        & value["valid_from_utc"].le(asof)
        & (value["valid_to_utc"].isna() | value["valid_to_utc"].ge(asof))
    ]
    if len(rows) != 1:
        return AliasResolution(
            "UNIDENTIFIED", None, alias_kind, source_id, source_alias, asof.isoformat()
        )
    return AliasResolution(
        "SOURCE_LOCAL",
        str(rows.iloc[0]["entity_id"]),
        alias_kind,
        source_id,
        source_alias,
        asof.isoformat(),
    )
