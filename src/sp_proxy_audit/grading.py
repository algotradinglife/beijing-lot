"""Frozen vector-grading rules for BJ-UNIFIED-SP-PROXY-AUDIT-001/v1."""

from __future__ import annotations

import math

import pandas as pd

OUTCOMES = ("3", "1", "0")
VECTOR_KEY = ("source_id", "issue_code", "match_idx", "snapshot_kind")
EXCLUSIONS = (
    "MANIFEST_MISMATCH",
    "SOURCE_MISSING",
    "IDENTITY_MISMATCH",
    "DUPLICATE_CONFLICT",
    "POST_KICKOFF",
    "POST_DECISION",
    "TIMESTAMP_UNPROVEN",
    "SETTLEMENT_ONLY",
    "INCOMPLETE_TRIPLET",
    "NONFINITE_PRICE",
    "NONPOSITIVE_PRICE",
)


def _timestamps(vector: pd.DataFrame, column: str) -> pd.Series:
    """Coerce a full column at once so all-null input remains UTC-aware."""
    return pd.to_datetime(vector[column], utc=True, errors="coerce")


def _has_explicit_timezone(value: object) -> bool:
    try:
        return pd.Timestamp(value).tzinfo is not None
    except (TypeError, ValueError):
        return False


def _reason(vector: pd.DataFrame) -> tuple[str, str]:
    """Return atomic vector grade/reason using the contract's precedence order."""
    semantics = set(vector["source_semantics"].astype("string").dropna())
    if "manifest_mismatch" in semantics:
        return "UNUSABLE", "MANIFEST_MISMATCH"
    if "missing" in semantics:
        return "UNUSABLE", "SOURCE_MISSING"
    if not vector["fixture_identity"].astype("string").str.len().gt(0).all():
        return "UNUSABLE", "IDENTITY_MISMATCH"
    if "identity_consistent" in vector and not vector["identity_consistent"].fillna(False).all():
        return "UNUSABLE", "IDENTITY_MISMATCH"

    by_outcome = vector.groupby("outcome_code", dropna=False, sort=False)
    duplicate_conflict = any(
        len(group) > 1
        and group[["sp_value", "provenance_sha256"]].astype("string").drop_duplicates().shape[0]
        != 1
        for _, group in by_outcome
    )
    if duplicate_conflict:
        return "UNUSABLE", "DUPLICATE_CONFLICT"

    observed = _timestamps(vector, "observed_at_utc")
    decision = _timestamps(vector, "decision_epoch_utc")
    kickoff = _timestamps(vector, "kickoff_utc")
    if (observed.notna() & kickoff.notna() & observed.gt(kickoff)).any():
        return "UNUSABLE", "POST_KICKOFF"
    if (observed.notna() & decision.notna() & observed.gt(decision)).any():
        return "UNUSABLE", "POST_DECISION"
    if "settlement" in semantics:
        return "UNUSABLE", "SETTLEMENT_ONLY"

    unique_outcomes = set(vector["outcome_code"].astype(str))
    if unique_outcomes != set(OUTCOMES) or len(by_outcome) != 3:
        return "UNUSABLE", "INCOMPLETE_TRIPLET"
    prices = pd.to_numeric(vector["sp_value"], errors="coerce")
    if not prices.map(lambda value: isinstance(value, (int, float)) and math.isfinite(value)).all():
        return "UNUSABLE", "NONFINITE_PRICE"
    if not prices.gt(0).all():
        return "UNUSABLE", "NONPOSITIVE_PRICE"

    if semantics == {"relative_proxy"}:
        return "HISTORICAL_PROXY", ""
    if semantics == {"strict"}:
        explicit_timezone = all(
            vector[column].map(_has_explicit_timezone).all()
            for column in ("observed_at_utc", "decision_epoch_utc", "kickoff_utc")
        )
        if (
            not explicit_timezone
            or observed.isna().any()
            or decision.isna().any()
            or kickoff.isna().any()
        ):
            return "UNUSABLE", "TIMESTAMP_UNPROVEN"
        if not (observed.le(decision) & decision.lt(kickoff)).all():
            return "UNUSABLE", "TIMESTAMP_UNPROVEN"
        return "STRICT_PRE_EVENT", ""
    return "UNUSABLE", "TIMESTAMP_UNPROVEN"


def grade_vectors(cells: pd.DataFrame) -> pd.DataFrame:
    """Grade every candidate M×3 vector without silently filling any evidence."""
    required = {
        *VECTOR_KEY,
        "outcome_code",
        "sp_value",
        "fixture_identity",
        "provenance_sha256",
        "observed_at_utc",
        "decision_epoch_utc",
        "kickoff_utc",
        "source_semantics",
    }
    missing = required - set(cells.columns)
    if missing:
        raise ValueError(f"missing grading columns: {sorted(missing)}")
    result = cells.copy()
    result["source_grade"] = "UNUSABLE"
    result["exclusion_reason"] = pd.Series(pd.NA, index=result.index, dtype="string")
    for _, index in result.groupby(list(VECTOR_KEY), dropna=False, sort=False).groups.items():
        grade, reason = _reason(result.loc[index])
        result.loc[index, "source_grade"] = grade
        if reason:
            result.loc[index, "exclusion_reason"] = reason
    return result.sort_values([*VECTOR_KEY, "outcome_code"], kind="mergesort").reset_index(drop=True)
