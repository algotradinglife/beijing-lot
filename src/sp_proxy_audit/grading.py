"""Vectorized grading rules for BJ-UNIFIED-SP-PROXY-AUDIT-001/v1."""

from __future__ import annotations

import numpy as np
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


def _explicit_timezone(values: pd.Series) -> pd.Series:
    text = values.astype("string")
    return text.str.contains(r"(?:[zZ]|[+-]\d{2}:?\d{2})$", regex=True, na=False)


def grade_vectors(cells: pd.DataFrame) -> pd.DataFrame:
    """Grade Mx3 vectors with contract precedence and one row per outcome cell."""
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
    if cells.empty:
        result = cells.copy()
        result["source_grade"] = pd.Series(dtype="string")
        result["exclusion_reason"] = pd.Series(dtype="string")
        return result

    result = cells.copy()
    result["outcome_code"] = result["outcome_code"].astype("string")
    result["source_semantics"] = result["source_semantics"].astype("string")
    result["sp_value"] = pd.to_numeric(result["sp_value"], errors="coerce")

    # Byte-identical duplicates are one cell under the contract. Conflicting
    # duplicates remain and are rejected at vector level below.
    dedupe = [
        *VECTOR_KEY,
        "outcome_code",
        "sp_value",
        "provenance_sha256",
        "fixture_identity",
        "observed_at_utc",
        "decision_epoch_utc",
        "kickoff_utc",
        "source_semantics",
    ]
    result = result.drop_duplicates(dedupe, keep="first").copy()
    group = result.groupby(list(VECTOR_KEY), dropna=False, sort=False)

    size = group["outcome_code"].transform("size")
    outcome_count = group["outcome_code"].transform("nunique")
    vector_grouper = [result[column] for column in VECTOR_KEY]
    semantics_manifest = (
        result["source_semantics"]
        .eq("manifest_mismatch")
        .groupby(vector_grouper, dropna=False)
        .transform("any")
    )
    semantics_missing = (
        result["source_semantics"]
        .eq("missing")
        .groupby(vector_grouper, dropna=False)
        .transform("any")
    )
    semantics_settlement = (
        result["source_semantics"]
        .eq("settlement")
        .groupby(vector_grouper, dropna=False)
        .transform("any")
    )
    semantics_relative = (
        result["source_semantics"]
        .eq("relative_proxy")
        .groupby(vector_grouper, dropna=False)
        .transform("all")
    )
    semantics_strict = (
        result["source_semantics"]
        .eq("strict")
        .groupby(vector_grouper, dropna=False)
        .transform("all")
    )

    identity_ok = result["fixture_identity"].astype("string").str.len().gt(0)
    if "identity_consistent" in result:
        identity_ok &= result["identity_consistent"].fillna(False).astype(bool)
    identity_bad = (
        (~identity_ok)
        .groupby([result[column] for column in VECTOR_KEY], dropna=False)
        .transform("any")
    )

    cell_key = [*VECTOR_KEY, "outcome_code"]
    duplicate_conflict = pd.Series(False, index=result.index)
    duplicate_rows = result.duplicated(cell_key, keep=False)
    if duplicate_rows.any():
        duplicate_summary = (
            result.loc[duplicate_rows]
            .groupby(cell_key, dropna=False, sort=False)
            .agg(
                price_versions=("sp_value", "nunique"),
                provenance_versions=("provenance_sha256", "nunique"),
            )
        )
        conflicting_cells = duplicate_summary.loc[
            duplicate_summary["price_versions"].gt(1)
            | duplicate_summary["provenance_versions"].gt(1)
        ].reset_index()
        if not conflicting_cells.empty:
            conflicting_vectors = conflicting_cells[list(VECTOR_KEY)].drop_duplicates()
            duplicate_conflict = pd.Series(
                pd.MultiIndex.from_frame(result[list(VECTOR_KEY)]).isin(
                    pd.MultiIndex.from_frame(conflicting_vectors)
                ),
                index=result.index,
            )

    observed = pd.to_datetime(result["observed_at_utc"], utc=True, errors="coerce")
    decision = pd.to_datetime(result["decision_epoch_utc"], utc=True, errors="coerce")
    kickoff = pd.to_datetime(result["kickoff_utc"], utc=True, errors="coerce")
    post_kickoff = (
        (observed.notna() & kickoff.notna() & observed.gt(kickoff))
        .groupby([result[column] for column in VECTOR_KEY], dropna=False)
        .transform("any")
    )
    post_decision = (
        (observed.notna() & decision.notna() & observed.gt(decision))
        .groupby([result[column] for column in VECTOR_KEY], dropna=False)
        .transform("any")
    )

    missing_price = (
        result["sp_value"]
        .isna()
        .groupby([result[column] for column in VECTOR_KEY], dropna=False)
        .transform("any")
    )
    infinite_price = (
        pd.Series(
            np.isinf(result["sp_value"].to_numpy(dtype=float)), index=result.index
        )
        .groupby([result[column] for column in VECTOR_KEY], dropna=False)
        .transform("any")
    )
    nonpositive_price = (
        result["sp_value"]
        .le(0)
        .groupby([result[column] for column in VECTOR_KEY], dropna=False)
        .transform("any")
    )
    incomplete = size.ne(3) | outcome_count.ne(3) | missing_price

    explicit_tz = (
        _explicit_timezone(result["observed_at_utc"])
        & _explicit_timezone(result["decision_epoch_utc"])
        & _explicit_timezone(result["kickoff_utc"])
    )
    strict_time_ok = (
        (
            explicit_tz
            & observed.notna()
            & decision.notna()
            & kickoff.notna()
            & observed.le(decision)
            & decision.lt(kickoff)
        )
        .groupby([result[column] for column in VECTOR_KEY], dropna=False)
        .transform("all")
    )
    timestamp_unproven = (semantics_strict & ~strict_time_ok) | (
        ~(semantics_relative | semantics_strict | semantics_settlement)
    )

    result["source_grade"] = "UNUSABLE"
    reason = pd.Series(pd.NA, index=result.index, dtype="string")
    precedence = (
        (semantics_manifest, "MANIFEST_MISMATCH"),
        (semantics_missing, "SOURCE_MISSING"),
        (identity_bad, "IDENTITY_MISMATCH"),
        (duplicate_conflict, "DUPLICATE_CONFLICT"),
        (post_kickoff, "POST_KICKOFF"),
        (post_decision, "POST_DECISION"),
        (timestamp_unproven, "TIMESTAMP_UNPROVEN"),
        (semantics_settlement, "SETTLEMENT_ONLY"),
        (incomplete, "INCOMPLETE_TRIPLET"),
        (infinite_price, "NONFINITE_PRICE"),
        (nonpositive_price, "NONPOSITIVE_PRICE"),
    )
    for mask, label in precedence:
        reason.loc[reason.isna() & mask] = label

    clean = reason.isna()
    relative = clean & semantics_relative
    strict = clean & semantics_strict & strict_time_ok
    result.loc[relative, "source_grade"] = "HISTORICAL_PROXY"
    result.loc[strict, "source_grade"] = "STRICT_PRE_EVENT"
    reason.loc[clean & ~(relative | strict)] = "TIMESTAMP_UNPROVEN"
    result["exclusion_reason"] = reason
    return result.sort_values(
        [*VECTOR_KEY, "outcome_code"], kind="mergesort"
    ).reset_index(drop=True)
