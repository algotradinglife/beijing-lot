"""Pure normalization for the #236 Nowscore/Titan historical proxy lane.

The module only processes straight European 1X2 workbook rows.  Its output is
explicitly a RETROSPECTIVE_RELATIVE_PROXY: ``initial``, ``10h`` and ``1h`` are
provider labels, never fabricated observation timestamps or Beijing SP.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable

import numpy as np
import pandas as pd

OUTCOMES = ("3", "1", "0")
MARKET_TYPE = "euro_1x2"
CAUSAL_GRADE = "RETROSPECTIVE_RELATIVE_PROXY"
SOURCE_ROLE = "Nowscore_Titan_historical_market_proxy"
PROBABILITY_COLUMNS = (
    "canonical_fixture_key", "issue_code", "match_idx", "snapshot_kind",
    "source_role", "market_type", "causal_grade", "outcome_code",
    "probability", "n_available_books", "availability_mask",
    "aggregation_grade", "raw_group_sha256", "source_match_ids",
)
RAW_QUOTE_COLUMNS = (
    "canonical_fixture_key", "issue_code", "match_idx", "source_match_id",
    "snapshot_kind", "source_role", "market_type", "causal_grade",
    "bookmaker_id", "outcome_code", "decimal_odds",
    "native_handicap_line_raw", "native_handicap_line",
    "handicap_norm_source", "quote_status",
)
LEDGER_COLUMNS = (
    "canonical_fixture_key", "snapshot_kind", "source_match_id",
    "bookmaker_id", "reason", "detail",
)
TRANSLATION_COLUMNS = (
    "canonical_fixture_key", "snapshot_kind", "source_role",
    "source_match_ids", "market_type", "causal_grade", "availability_mask",
    "native_handicap_line_raw", "native_handicap_line",
    "handicap_norm_source", "translation_status",
    "translation_probability_json", "required_additional_input",
)
REQUIRED_COLUMNS = {
    "issue_code", "match_idx", "source_match_id", "snapshot_kind",
    "bookmaker_id", "v1", "v2", "v3", "native_handicap_line_raw",
    "native_handicap_line", "handicap_norm_source",
}


def canonical_fixture_key(issue_code: object, match_idx: object) -> str:
    """Return the canonical Beijing issue-slot key; never a provider ID."""
    issue = str(issue_code).strip()
    if not issue:
        raise ValueError("issue_code is required")
    try:
        slot = int(match_idx)
    except (TypeError, ValueError) as exc:
        raise ValueError("match_idx must be an integer") from exc
    if slot < 1:
        raise ValueError("match_idx must be positive")
    return f"bjslot:{issue}:{slot:03d}"


def _assert_input(frame: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if frame.empty:
        raise ValueError("no raw historical quote rows supplied")
    duplicate_key = ["issue_code", "match_idx", "snapshot_kind", "bookmaker_id"]
    if frame.duplicated(duplicate_key, keep=False).any():
        raise ValueError("duplicate source bookmaker observation; refuse arbitrary collapse")
    if ~frame["snapshot_kind"].isin({"initial", "10h", "1h"}).all():
        raise ValueError("snapshot_kind must be one of initial/10h/1h")


def _quote_status(values: Iterable[object]) -> str:
    numeric = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(dtype=float)
    return "VALID" if bool(np.isfinite(numeric).all() and (numeric > 1.0).all()) else "INVALID"


def _devig(values: Iterable[object]) -> np.ndarray:
    odds = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(dtype=float)
    if odds.shape != (3,) or not np.isfinite(odds).all() or bool((odds <= 1.0).any()):
        raise ValueError("invalid decimal odds")
    implied = 1.0 / odds
    return implied / implied.sum()


def _raw_group_hash(group: pd.DataFrame) -> str:
    payload = [
        {
            "source_match_id": str(row.source_match_id),
            "bookmaker_id": str(row.bookmaker_id),
            "v1": _canonical_number(row.v1),
            "v2": _canonical_number(row.v2),
            "v3": _canonical_number(row.v3),
        }
        for row in group.sort_values("bookmaker_id").itertuples(index=False)
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_number(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric)


def derive_proxy_probabilities(raw_rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """De-vig valid bookmaker triplets while retaining all raw quote evidence.

    Returns ``(probabilities, raw_quotes, exclusion_ledger)``. Invalid cells
    stay in raw_quotes and are represented in the ledger; they never reach a
    consensus probability. A probability group has one source-trace digest
    covering every raw bookmaker triplet used or excluded beneath it.
    """
    _assert_input(raw_rows)
    work = raw_rows.copy()
    work["canonical_fixture_key"] = [
        canonical_fixture_key(issue, idx) for issue, idx in zip(work.issue_code, work.match_idx)
    ]
    work["quote_status"] = [
        _quote_status((row.v1, row.v2, row.v3)) for row in work.itertuples(index=False)
    ]
    work["market_type"] = MARKET_TYPE
    work["causal_grade"] = CAUSAL_GRADE
    work["source_role"] = SOURCE_ROLE

    raw_quote_rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []
    probability_rows: list[dict[str, object]] = []
    group_cols = ["canonical_fixture_key", "issue_code", "match_idx", "snapshot_kind"]
    for group_key, group in work.groupby(group_cols, sort=True, dropna=False):
        fixture_key, issue_code, match_idx, snapshot_kind = group_key
        digest = _raw_group_hash(group)
        valid_vectors: list[np.ndarray] = []
        for row in group.itertuples(index=False):
            status = row.quote_status
            if status == "VALID":
                valid_vectors.append(_devig((row.v1, row.v2, row.v3)))
            else:
                ledger_rows.append({
                    "canonical_fixture_key": fixture_key,
                    "snapshot_kind": snapshot_kind,
                    "source_match_id": str(row.source_match_id),
                    "bookmaker_id": str(row.bookmaker_id),
                    "reason": "INVALID_DECIMAL_ODDS",
                    "detail": "requires finite decimal odds strictly greater than one for all 3/1/0 cells",
                })
            for outcome, value in zip(OUTCOMES, (row.v1, row.v2, row.v3)):
                numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
                raw_quote_rows.append({
                    "canonical_fixture_key": fixture_key,
                    "issue_code": str(issue_code),
                    "match_idx": int(match_idx),
                    "source_match_id": str(row.source_match_id),
                    "snapshot_kind": snapshot_kind,
                    "source_role": SOURCE_ROLE,
                    "market_type": MARKET_TYPE,
                    "causal_grade": CAUSAL_GRADE,
                    "bookmaker_id": str(row.bookmaker_id),
                    "outcome_code": outcome,
                    "decimal_odds": None if pd.isna(numeric) else float(numeric),
                    "native_handicap_line_raw": row.native_handicap_line_raw,
                    "native_handicap_line": row.native_handicap_line,
                    "handicap_norm_source": row.handicap_norm_source,
                    "quote_status": status,
                })
        if not valid_vectors:
            ledger_rows.append({
                "canonical_fixture_key": fixture_key,
                "snapshot_kind": snapshot_kind,
                "source_match_id": "",
                "bookmaker_id": "",
                "reason": "NO_VALID_BOOKMAKER_TRIPLET",
                "detail": "all raw bookmaker triplets were invalid; availability remains masked",
            })
            continue
        vectors = np.vstack(valid_vectors)
        # Frozen de-vig aggregation: mean of independently proportional de-vigged books.
        aggregate = vectors.mean(axis=0)
        aggregate /= aggregate.sum()
        if not np.isfinite(aggregate).all() or not math.isclose(float(aggregate.sum()), 1.0, abs_tol=1e-12):
            raise ValueError("internal aggregate probability invariant failed")
        for outcome, probability in zip(OUTCOMES, aggregate):
            probability_rows.append({
                "canonical_fixture_key": fixture_key,
                "issue_code": str(issue_code),
                "match_idx": int(match_idx),
                "snapshot_kind": snapshot_kind,
                "source_role": SOURCE_ROLE,
                "market_type": MARKET_TYPE,
                "causal_grade": CAUSAL_GRADE,
                "outcome_code": outcome,
                "probability": float(probability),
                "n_available_books": len(valid_vectors),
                "availability_mask": "1",
                "aggregation_grade": "BOOKMAKER_DE_VIG_MEAN",
                "raw_group_sha256": digest,
                "source_match_ids": ",".join(sorted({str(value) for value in group["source_match_id"]})),
            })
    return (
        pd.DataFrame(probability_rows, columns=PROBABILITY_COLUMNS),
        pd.DataFrame(raw_quote_rows, columns=RAW_QUOTE_COLUMNS),
        pd.DataFrame(ledger_rows, columns=LEDGER_COLUMNS),
    )


def translation_readiness(probabilities: pd.DataFrame, raw_rows: pd.DataFrame) -> pd.DataFrame:
    """Emit an honest #238-facing decision for the BJ-line translation family."""
    if probabilities.empty:
        return pd.DataFrame(columns=TRANSLATION_COLUMNS)
    required = {"canonical_fixture_key", "snapshot_kind", "outcome_code", "probability"}
    if required - set(probabilities.columns):
        raise ValueError("probabilities lack required translation columns")
    _assert_input(raw_rows)
    lines = raw_rows.copy()
    lines["canonical_fixture_key"] = [
        canonical_fixture_key(issue, idx) for issue, idx in zip(lines.issue_code, lines.match_idx)
    ]
    rows: list[dict[str, object]] = []
    for (fixture_key, horizon), group in probabilities.groupby(["canonical_fixture_key", "snapshot_kind"], sort=True):
        vector = group.set_index("outcome_code")["probability"].reindex(OUTCOMES)
        if vector.isna().any():
            raise ValueError("partial probability triplet cannot be translated")
        fixture_lines = lines.loc[lines.canonical_fixture_key.eq(fixture_key)]
        candidates = fixture_lines["native_handicap_line"].dropna().unique()
        raw_candidates = fixture_lines["native_handicap_line_raw"].dropna().unique()
        norm_sources = fixture_lines["handicap_norm_source"].dropna().astype(str).unique()
        source_match_ids = ",".join(
            sorted({str(value) for value in fixture_lines["source_match_id"]})
        )
        line_value = float(candidates[0]) if len(candidates) == 1 else None
        if len(candidates) != 1:
            status, payload = "UNAVAILABLE_MISSING_OR_CONFLICTING_NATIVE_LINE", None
            required_input = "normalized_native_handicap_line"
        elif not np.isfinite(line_value) or not line_value.is_integer() or not -3.0 <= line_value <= 3.0:
            status, payload = "UNAVAILABLE_INVALID_NATIVE_LINE", None
            required_input = "valid_integer_native_handicap_line"
        elif line_value == 0.0:
            status = "AVAILABLE_ZERO_LINE_IDENTITY"
            payload = json.dumps([float(vector[x]) for x in OUTCOMES], separators=(",", ":"))
            required_input = ""
        else:
            status, payload = "UNAVAILABLE_NONZERO_LINE_REQUIRES_GOAL_DIFFERENCE", None
            required_input = "score_goal_difference_distribution"
        rows.append({
            "canonical_fixture_key": fixture_key,
            "snapshot_kind": horizon,
            "source_role": SOURCE_ROLE,
            "source_match_ids": source_match_ids,
            "market_type": MARKET_TYPE,
            "causal_grade": CAUSAL_GRADE,
            "availability_mask": "1" if payload is not None else "0",
            "native_handicap_line_raw": float(raw_candidates[0]) if len(raw_candidates) == 1 else None,
            "native_handicap_line": line_value,
            "handicap_norm_source": str(norm_sources[0]) if len(norm_sources) == 1 else "",
            "translation_status": status,
            "translation_probability_json": payload,
            "required_additional_input": required_input,
        })
    return pd.DataFrame(rows, columns=TRANSLATION_COLUMNS)
