"""Streaming external Parquet materialization for the #236 raw workbook."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from source_schema import publication

from .core import CAUSAL_GRADE, MARKET_TYPE, SOURCE_ROLE
from .source import iter_workbook_proxy


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_part(frame: pd.DataFrame, directory: Path, number: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(directory / f"part-{number:05d}.parquet", index=False)


def _process_chunk(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Vectorized de-vig/aggregation for complete ordered source groups."""
    group_cols = ["issue_code", "match_idx", "source_match_id", "snapshot_kind", "native_handicap_line"]
    work = frame.copy()
    odds = work[["v1", "v2", "v3"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(odds).all(axis=1) & (odds > 1.0).all(axis=1)
    work["is_valid_book"] = valid
    trace = work.groupby(group_cols, dropna=False, sort=True).agg(
        raw_bookmaker_rows=("bookmaker_id", "size"),
        valid_bookmaker_rows=("is_valid_book", "sum"),
    ).reset_index()
    trace["canonical_fixture_key"] = [f"bjslot:{str(issue).strip()}:{int(slot):03d}" for issue, slot in zip(trace.issue_code, trace.match_idx)]
    trace["source_role"] = SOURCE_ROLE
    trace["market_type"] = MARKET_TYPE
    trace["causal_grade"] = CAUSAL_GRADE
    invalid = trace.loc[trace.valid_bookmaker_rows.eq(0), ["canonical_fixture_key", "snapshot_kind", "source_match_id"]].copy()
    invalid["reason"] = "NO_VALID_BOOKMAKER_TRIPLET"
    invalid["detail"] = "all raw bookmaker triplets had missing, non-finite, or decimal odds <= 1"
    good = work.loc[work.is_valid_book].copy()
    if good.empty:
        return pd.DataFrame(), trace, invalid, pd.DataFrame()
    inv = 1.0 / good[["v1", "v2", "v3"]].to_numpy(dtype=float)
    probs = inv / inv.sum(axis=1, keepdims=True)
    good[["p3", "p1", "p0"]] = probs
    aggregated = good.groupby(group_cols, dropna=False, sort=True)[["p3", "p1", "p0"]].mean().reset_index()
    aggregated["canonical_fixture_key"] = [f"bjslot:{str(issue).strip()}:{int(slot):03d}" for issue, slot in zip(aggregated.issue_code, aggregated.match_idx)]
    availability = trace[[*group_cols, "valid_bookmaker_rows"]]
    aggregated = aggregated.merge(availability, on=group_cols, validate="one_to_one")
    probability = aggregated.melt(
        id_vars=["canonical_fixture_key", "issue_code", "match_idx", "source_match_id", "snapshot_kind", "valid_bookmaker_rows"],
        value_vars=["p3", "p1", "p0"], var_name="_cell", value_name="probability",
    )
    probability["outcome_code"] = probability["_cell"].map({"p3": "3", "p1": "1", "p0": "0"})
    probability["source_match_ids"] = probability["source_match_id"].astype(str)
    probability["source_role"] = SOURCE_ROLE
    probability["market_type"] = MARKET_TYPE
    probability["causal_grade"] = CAUSAL_GRADE
    probability["n_available_books"] = probability.pop("valid_bookmaker_rows").astype(int)
    probability["availability_mask"] = "1"
    probability["aggregation_grade"] = "BOOKMAKER_DE_VIG_MEAN"
    probability = probability.drop(columns=["_cell", "source_match_id"])
    readiness = aggregated[["canonical_fixture_key", "snapshot_kind", "native_handicap_line"]].copy()
    readiness["source_role"] = SOURCE_ROLE
    readiness["market_type"] = MARKET_TYPE
    readiness["required_additional_input"] = ""
    readiness["translation_probability_json"] = None
    readiness["translation_status"] = "UNAVAILABLE_NONZERO_LINE_REQUIRES_GOAL_DIFFERENCE"
    missing = readiness.native_handicap_line.isna()
    readiness.loc[missing, "translation_status"] = "UNAVAILABLE_MISSING_OR_CONFLICTING_NATIVE_LINE"
    zero = readiness.native_handicap_line.eq(0)
    if zero.any():
        wide = aggregated.loc[zero, ["canonical_fixture_key", "snapshot_kind", "p3", "p1", "p0"]]
        lookup = {(r.canonical_fixture_key, r.snapshot_kind): f"[{r.p3:.17g},{r.p1:.17g},{r.p0:.17g}]" for r in wide.itertuples(index=False)}
        mask = readiness.index[zero]
        readiness.loc[mask, "translation_status"] = "AVAILABLE_ZERO_LINE_IDENTITY"
        readiness.loc[mask, "translation_probability_json"] = [lookup[(readiness.loc[i, "canonical_fixture_key"], readiness.loc[i, "snapshot_kind"])] for i in mask]
        readiness.loc[mask, "required_additional_input"] = ""
    readiness.loc[~zero & ~missing, "required_additional_input"] = "score_goal_difference_distribution"
    return probability, trace, invalid, readiness


def materialize_proxy_view(workbook: Path, target: Path, *, source_sha256: str, chunksize: int = 100_000) -> dict[str, object]:
    """Build compact external probability views with source-coordinate traceability.

    The raw quotes stay in the immutable source workbook, bound by SHA-256. Each
    output group records its exact source match and bookmaker row counts, so it
    can be replayed without copying a second bulk raw database.
    """
    counts = {"probability_rows": 0, "trace_rows": 0, "translation_rows": 0, "exclusion_rows": 0}
    fixtures: set[str] = set()

    def publish(staging: Path) -> None:
        carry = pd.DataFrame()
        part = 0
        group_cols = ["issue_code", "match_idx", "snapshot_kind"]
        for chunk in iter_workbook_proxy(workbook, chunksize=chunksize):
            combined = pd.concat([carry, chunk], ignore_index=True) if not carry.empty else chunk
            tail = tuple(combined.iloc[-1][group_cols])
            tail_mask = combined[group_cols].eq(tail).all(axis=1)
            complete, carry = combined.loc[~tail_mask].copy(), combined.loc[tail_mask].copy()
            if complete.empty:
                continue
            probability, trace, ledger, readiness = _process_chunk(complete)
            if not probability.empty:
                _write_part(probability, staging / "probabilities", part)
                fixtures.update(probability.canonical_fixture_key.unique())
                counts["probability_rows"] += len(probability)
            _write_part(trace, staging / "source_trace", part)
            _write_part(ledger, staging / "exclusion_ledger", part)
            _write_part(readiness, staging / "translation_readiness", part)
            counts["trace_rows"] += len(trace)
            counts["exclusion_rows"] += len(ledger)
            counts["translation_rows"] += len(readiness)
            part += 1
        if not carry.empty:
            probability, trace, ledger, readiness = _process_chunk(carry)
            if not probability.empty:
                _write_part(probability, staging / "probabilities", part)
                fixtures.update(probability.canonical_fixture_key.unique())
                counts["probability_rows"] += len(probability)
            _write_part(trace, staging / "source_trace", part)
            _write_part(ledger, staging / "exclusion_ledger", part)
            _write_part(readiness, staging / "translation_readiness", part)
            counts["trace_rows"] += len(trace)
            counts["exclusion_rows"] += len(ledger)
            counts["translation_rows"] += len(readiness)
        if _hash(workbook) != source_sha256:
            raise RuntimeError("raw workbook changed during materialization; refusing publication")
        facts = {**counts, "matched_fixture_count": len(fixtures), "strict_forward_rows": 0, "proxy_rows": counts["probability_rows"], "source_sha256": source_sha256, "market_type": MARKET_TYPE, "causal_grade": CAUSAL_GRADE}
        publication.atomic_write_json(staging / "report_facts.json", facts)
        hashes = {str(p.relative_to(staging)): _hash(p) for p in sorted(staging.rglob("*.parquet"))}
        publication.atomic_write_json(staging / "MANIFEST.json", {"contract": "BJ-UNIFIED-EU-ODDS-TIMESERIES-001", **facts, "parts": hashes})

    publication.atomic_publish_directory(target, publish, force=True)
    return {**counts, "matched_fixture_count": len(fixtures), "target": str(target)}
