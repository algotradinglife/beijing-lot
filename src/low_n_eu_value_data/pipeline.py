"""Causal 10h European-average-odds value inputs for Issue #358.

The panel retains raw European bookmaker consensus as a retrospective 10h
proxy and joins it to the #360-corrected strictly-prior calibrated probability
surface.  It never opens the physically separate settlement labels.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.source_schema.publication import (
    atomic_publish_directory,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_parquet,
)

CONTRACT_ID = "BJ-UNIFIED-LOWN-EU-VALUE-DATA-001/v2"
OUTCOMES = ("3", "1", "0")
OUTCOME_ORDER = {outcome: index for index, outcome in enumerate(OUTCOMES)}
HORIZON = "10h"
YEARS = tuple(range(2017, 2025))
PAYOUT_FACTOR = 0.65
SELECTOR_FEATURE_RELATIVE = "results/low_n_selector_data/features/selector_features.parquet"
SELECTOR_RECEIPT_RELATIVE = "results/low_n_selector_data/FREEZE_RECEIPT.json"
CANDIDATE_SQLITE_RELATIVE = "derived/bj268/eu_proxy_backfill_v3/candidate.sqlite"


class ContractError(ValueError):
    """Raised when a source or derived value panel violates the #358 contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    columns = sorted(frame.columns)
    projected = frame.loc[:, columns].copy()
    # Arrow may choose a different physical unit for an all-null timestamp
    # column. Hash its logical UTC representation rather than that unit.
    for column in columns:
        if pd.api.types.is_datetime64_any_dtype(projected[column]):
            normalized = pd.to_datetime(projected[column], utc=True)
            projected[column] = normalized.map(
                lambda value: "" if pd.isna(value) else value.isoformat()
            )
    row_hashes = np.sort(
        pd.util.hash_pandas_object(projected, index=False, categorize=False).to_numpy(
            dtype=np.uint64
        )
    )
    schema = [(column, str(projected[column].dtype)) for column in columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode("utf-8"))
    digest.update(row_hashes.tobytes())
    return digest.hexdigest()


def locate_data_root(repo_root: Path, explicit: Path | None = None) -> Path:
    candidates = [] if explicit is None else [Path(explicit)]
    candidates.extend([repo_root / "data", repo_root.parents[1] / "data"])
    for candidate in candidates:
        if (candidate / CANDIDATE_SQLITE_RELATIVE).is_file():
            return candidate.resolve()
    raise FileNotFoundError("canonical Issue #268 data root was not found")


def _read_only_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _canonical_join(value: object) -> str:
    values = sorted({item.strip() for item in str(value or "").split(",") if item.strip()})
    return ",".join(values)


def read_odds_aggregates(data_root: Path, issue_codes: set[str]) -> pd.DataFrame:
    """Aggregate each complete 10h raw-bookmaker group without outcome labels."""

    if not issue_codes:
        raise ContractError("empty selector issue universe")
    rows: list[pd.DataFrame] = []
    query_template = """
        SELECT CAST(issue_code AS TEXT) AS issue,
               match_idx,
               COUNT(*) AS raw_bookmaker_row_count,
               SUM(CASE WHEN v1 > 1.0 AND v2 > 1.0 AND v3 > 1.0
                             AND v1 = v1 AND v2 = v2 AND v3 = v3
                        THEN 1 ELSE 0 END) AS contributing_bookmaker_count,
               AVG(CASE WHEN v1 > 1.0 AND v2 > 1.0 AND v3 > 1.0
                             AND v1 = v1 AND v2 = v2 AND v3 = v3
                        THEN v1 END) AS average_decimal_odds_3,
               AVG(CASE WHEN v1 > 1.0 AND v2 > 1.0 AND v3 > 1.0
                             AND v1 = v1 AND v2 = v2 AND v3 = v3
                        THEN v2 END) AS average_decimal_odds_1,
               AVG(CASE WHEN v1 > 1.0 AND v2 > 1.0 AND v3 > 1.0
                             AND v1 = v1 AND v2 = v2 AND v3 = v3
                        THEN v3 END) AS average_decimal_odds_0,
               GROUP_CONCAT(DISTINCT source_match_id) AS source_match_ids,
               GROUP_CONCAT(DISTINCT payload_sha256) AS source_payload_sha256s,
               GROUP_CONCAT(DISTINCT bookmaker_id) AS source_bookmakers
        FROM resolved_quotes
        WHERE snapshot_kind = ? AND issue_code IN ({placeholders})
        GROUP BY issue_code, match_idx
        ORDER BY issue_code, match_idx
    """
    ordered = sorted(issue_codes)
    with _read_only_connection(data_root / CANDIDATE_SQLITE_RELATIVE) as connection:
        for offset in range(0, len(ordered), 800):
            chunk = ordered[offset : offset + 800]
            query = query_template.format(placeholders=",".join("?" for _ in chunk))
            rows.append(pd.read_sql_query(query, connection, params=[HORIZON, *chunk]))
    output = pd.concat(rows, ignore_index=True)
    if output.duplicated(["issue", "match_idx"]).any():
        raise ContractError("raw odds aggregate keys are not unique")
    for column in ("source_match_ids", "source_payload_sha256s", "source_bookmakers"):
        output[column] = output[column].map(_canonical_join)
    return output


def _require_columns(frame: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ContractError(f"{name} missing columns: {missing}")


def build_value_cells(selector_features: pd.DataFrame, odds: pd.DataFrame) -> pd.DataFrame:
    """Join #360-corrected calibration to 10h odds and derive no-label value cells."""

    selector_required = {
        "issue", "issue_year", "issue_anchor_ts", "match_idx", "baseline_support",
        "q_candidate_3", "q_candidate_1", "q_candidate_0", "n_available_books",
        "causal_grade", "prediction_role", "train_year_max", "calibration_history_max_year",
    }
    odds_required = {
        "issue", "match_idx", "source_match_ids", "source_payload_sha256s",
        "source_bookmakers", "raw_bookmaker_row_count", "contributing_bookmaker_count",
        "average_decimal_odds_3", "average_decimal_odds_1", "average_decimal_odds_0",
    }
    _require_columns(selector_features, selector_required, "selector feature frame")
    _require_columns(odds, odds_required, "raw odds aggregate")
    features = selector_features.copy()
    features["issue"] = features["issue"].astype(str)
    features["match_idx"] = pd.to_numeric(features["match_idx"], errors="raise").astype(int)
    features = features[features["issue_year"].isin(YEARS)].copy()
    if features.empty or features.duplicated(["issue", "match_idx"]).any():
        raise ContractError("selector feature keys are empty or non-unique")
    source = odds.copy()
    source["issue"] = source["issue"].astype(str)
    source["match_idx"] = pd.to_numeric(source["match_idx"], errors="raise").astype(int)
    if source.duplicated(["issue", "match_idx"]).any():
        raise ContractError("raw odds aggregate keys are not unique")
    merged = features.merge(source, on=["issue", "match_idx"], how="left", validate="one_to_one")
    if merged["contributing_bookmaker_count"].isna().any():
        raise ContractError("#360-corrected selector feature escaped the 10h raw-odds source")
    merged["contributing_bookmaker_count"] = merged["contributing_bookmaker_count"].astype(int)
    if not merged["contributing_bookmaker_count"].eq(merged["n_available_books"].astype(int)).all():
        raise ContractError("raw bookmaker count does not match corrected selector bookmaker count")
    records: list[dict[str, object]] = []
    for row in merged.itertuples(index=False):
        calibrated = {outcome: float(getattr(row, f"q_candidate_{outcome}")) for outcome in OUTCOMES}
        if not np.isfinite(list(calibrated.values())).all() or not np.isclose(sum(calibrated.values()), 1.0, atol=1e-10):
            raise ContractError("corrected calibrated probability is not a finite simplex")
        support = "".join(sorted(OUTCOMES, key=lambda code: (-calibrated[code], OUTCOME_ORDER[code]))[:2])
        if str(row.baseline_support) != support:
            raise ContractError("corrected Top-2 support is inconsistent with calibrated probability")
        odds_by_outcome = {outcome: float(getattr(row, f"average_decimal_odds_{outcome}")) for outcome in OUTCOMES}
        if not np.isfinite(list(odds_by_outcome.values())).all() or min(odds_by_outcome.values()) <= 1.0:
            raise ContractError("average European decimal odds are invalid")
        implied = {outcome: 1.0 / odds_by_outcome[outcome] for outcome in OUTCOMES}
        overround = sum(implied.values())
        if not np.isfinite(overround) or overround <= 0:
            raise ContractError("raw implied probability overround is invalid")
        devig = {outcome: implied[outcome] / overround for outcome in OUTCOMES}
        contributions = {outcome: calibrated[outcome] * odds_by_outcome[outcome] for outcome in OUTCOMES}
        top2_factor = sum(contributions[outcome] for outcome in support)
        top2_return_per_stake = top2_factor / 2.0
        for outcome in OUTCOMES:
            records.append(
                {
                    "issue": str(row.issue),
                    "issue_year": int(row.issue_year),
                    "issue_anchor_ts": pd.Timestamp(row.issue_anchor_ts),
                    "match_idx": int(row.match_idx),
                    "outcome_code": outcome,
                    "outcome_order": OUTCOME_ORDER[outcome],
                    "prediction_role": str(row.prediction_role),
                    "train_year_max": int(row.train_year_max),
                    "calibration_history_max_year": int(row.calibration_history_max_year),
                    "source_horizon": HORIZON,
                    "source_observed_at_utc": pd.NaT,
                    "source_time_status": "RELATIVE_HORIZON_LABEL_NO_OBSERVED_TIMESTAMP",
                    "source_causal_grade": str(row.causal_grade),
                    "source_match_ids": str(row.source_match_ids),
                    "source_payload_sha256s": str(row.source_payload_sha256s),
                    "source_bookmakers": str(row.source_bookmakers),
                    "raw_bookmaker_row_count": int(row.raw_bookmaker_row_count),
                    "contributing_bookmaker_count": int(row.contributing_bookmaker_count),
                    "average_decimal_odds": odds_by_outcome[outcome],
                    "raw_implied_probability": implied[outcome],
                    "overround": overround,
                    "devig_probability": devig[outcome],
                    "calibrated_probability": calibrated[outcome],
                    "p_times_odds": contributions[outcome],
                    "top2_support": support,
                    "top2_included": outcome in support,
                    "top2_coverage_reliability": sum(calibrated[outcome] for outcome in support),
                    "top2_expected_gross_factor": top2_factor,
                    "top2_expected_return_per_stake_factor": top2_return_per_stake,
                    "ticket_level_once_65_factor": PAYOUT_FACTOR,
                    "quality_grade": "COMPLETE_VALID_10H_AVERAGE_EU_PROXY",
                    "missingness_reason": "COMPLETE",
                }
            )
    output = pd.DataFrame(records).sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx", "outcome_order"], kind="stable"
    ).reset_index(drop=True)
    verify_cell_frame(output)
    return output


def nfold_cartesian_expected_return_factor(top2_expected_gross_factors: list[float]) -> float:
    """Return expected gross per total stake for an equal-stake Top-2 portfolio."""

    values = np.asarray(top2_expected_gross_factors, dtype=float)
    if values.ndim != 1 or len(values) not in {3, 4, 5}:
        raise ContractError("N-fold Cartesian expectation is defined only for N3-N5")
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ContractError("Top-2 gross factors must be finite and positive")
    return PAYOUT_FACTOR * float(np.prod(values / 2.0))


def verify_cell_frame(cells: pd.DataFrame) -> None:
    """Recompute all per-fixture identities and fail closed on semantic tampering."""

    required = {
        "issue", "issue_year", "match_idx", "outcome_code", "outcome_order",
        "prediction_role", "train_year_max", "calibration_history_max_year",
        "source_horizon", "source_observed_at_utc", "source_time_status", "source_match_ids", "source_payload_sha256s",
        "source_bookmakers", "raw_bookmaker_row_count", "contributing_bookmaker_count",
        "average_decimal_odds", "raw_implied_probability", "overround", "devig_probability",
        "calibrated_probability", "p_times_odds", "top2_support", "top2_included",
        "top2_coverage_reliability", "top2_expected_gross_factor",
        "top2_expected_return_per_stake_factor",
        "ticket_level_once_65_factor", "quality_grade", "missingness_reason",
    }
    _require_columns(cells, required, "value cell frame")
    key = ["issue", "match_idx", "outcome_code"]
    if cells.empty or cells.duplicated(key).any():
        raise ContractError("value cell keys are empty or non-unique")
    if set(cells.outcome_code.astype(str)) != set(OUTCOMES):
        raise ContractError("value cells lack canonical 3/1/0 outcomes")
    if not pd.api.types.is_bool_dtype(cells["top2_included"].dtype):
        raise ContractError("top2_included must be a strict boolean")
    if not cells["source_horizon"].eq(HORIZON).all() or not cells["source_time_status"].eq(
        "RELATIVE_HORIZON_LABEL_NO_OBSERVED_TIMESTAMP"
    ).all():
        raise ContractError("source timing semantics changed")
    if cells["source_observed_at_utc"].notna().any():
        raise ContractError("relative horizon labels must not fabricate source timestamps")
    if not (cells["train_year_max"].astype(int) < cells["issue_year"].astype(int)).all() or not (
        cells["calibration_history_max_year"].astype(int) < cells["issue_year"].astype(int)
    ).all():
        raise ContractError("strictly-prior corrected selector lineage is invalid")
    transfer = cells["issue_year"].astype(int).ge(2022)
    if not cells.loc[transfer, "prediction_role"].eq("FROZEN_THROUGH_2021_TRANSFER").all() or not (
        cells.loc[transfer, ["train_year_max", "calibration_history_max_year"]].eq(2021).all().all()
    ):
        raise ContractError("transfer rows are not frozen through 2021")
    if cells["source_match_ids"].isna().any() or cells["source_payload_sha256s"].isna().any() or cells["source_bookmakers"].isna().any():
        raise ContractError("source provenance is missing")
    if cells[["source_match_ids", "source_payload_sha256s", "source_bookmakers"]].astype(str).apply(lambda column: column.str.len().eq(0)).any().any():
        raise ContractError("source provenance is empty")
    if cells["source_match_ids"].astype(str).str.contains("future", case=False, regex=False).any():
        raise ContractError("source trace declares future information")
    for (issue, match_idx), group in cells.groupby(["issue", "match_idx"], sort=False):
        ordered = group.sort_values("outcome_order", kind="stable")
        if ordered.outcome_code.astype(str).tolist() != list(OUTCOMES):
            raise ContractError(f"outcome order is invalid for {issue}/{match_idx}")
        if ordered["contributing_bookmaker_count"].nunique() != 1 or ordered["raw_bookmaker_row_count"].nunique() != 1:
            raise ContractError("bookmaker metadata is not fixture-constant")
        if int(ordered.contributing_bookmaker_count.iloc[0]) <= 0 or int(ordered.raw_bookmaker_row_count.iloc[0]) < int(ordered.contributing_bookmaker_count.iloc[0]):
            raise ContractError("bookmaker counts are invalid")
        odds = ordered.average_decimal_odds.to_numpy(float)
        calibrated = ordered.calibrated_probability.to_numpy(float)
        if not np.isfinite(odds).all() or (odds <= 1.0).any() or not np.isfinite(calibrated).all() or (calibrated <= 0).any() or not np.isclose(calibrated.sum(), 1.0, atol=1e-10):
            raise ContractError("odds or calibrated probability simplex is invalid")
        implied = 1.0 / odds
        overround = float(implied.sum())
        if not np.allclose(ordered.raw_implied_probability.to_numpy(float), implied, rtol=0, atol=1e-12):
            raise ContractError("raw implied probability identity failed")
        if not np.allclose(ordered.overround.to_numpy(float), overround, rtol=0, atol=1e-12):
            raise ContractError("overround identity failed")
        if not np.allclose(ordered.devig_probability.to_numpy(float), implied / overround, rtol=0, atol=1e-12):
            raise ContractError("devig probability identity failed")
        if not np.allclose(ordered.p_times_odds.to_numpy(float), calibrated * odds, rtol=0, atol=1e-12):
            raise ContractError("p-times-odds identity failed")
        expected_support = "".join(sorted(OUTCOMES, key=lambda code: (-calibrated[OUTCOME_ORDER[code]], OUTCOME_ORDER[code]))[:2])
        if set(ordered.top2_support.astype(str)) != {expected_support}:
            raise ContractError("Top-2 support identity failed")
        expected_included = ordered.outcome_code.astype(str).isin(set(expected_support)).to_numpy()
        if not np.array_equal(ordered.top2_included.to_numpy(bool), expected_included):
            raise ContractError("Top-2 inclusion identity failed")
        expected_reliability = float(calibrated[expected_included].sum())
        expected_factor = float((calibrated * odds)[expected_included].sum())
        if not np.allclose(ordered.top2_coverage_reliability.to_numpy(float), expected_reliability, rtol=0, atol=1e-12):
            raise ContractError("Top-2 coverage reliability identity failed")
        if not np.allclose(ordered.top2_expected_gross_factor.to_numpy(float), expected_factor, rtol=0, atol=1e-12):
            raise ContractError("Top-2 full-Cartesian gross factor identity failed")
        if not np.allclose(
            ordered.top2_expected_return_per_stake_factor.to_numpy(float),
            expected_factor / 2.0,
            rtol=0,
            atol=1e-12,
        ):
            raise ContractError("Top-2 expected return per-stake identity failed")
        if not np.allclose(ordered.ticket_level_once_65_factor.to_numpy(float), PAYOUT_FACTOR, rtol=0, atol=0):
            raise ContractError("ticket-level 0.65 factor identity failed")


def _analysis_frames(cells: pd.DataFrame) -> dict[str, pd.DataFrame]:
    fixture = cells.drop_duplicates(["issue", "match_idx"]).copy()
    coverage = fixture.groupby("issue_year", sort=True).agg(
        issues=("issue", "nunique"),
        fixtures=("match_idx", "size"),
        mean_contributing_bookmakers=("contributing_bookmaker_count", "mean"),
        min_contributing_bookmakers=("contributing_bookmaker_count", "min"),
        mean_top2_coverage_reliability=("top2_coverage_reliability", "mean"),
        mean_top2_expected_gross_factor=("top2_expected_gross_factor", "mean"),
        mean_top2_expected_return_per_stake_factor=(
            "top2_expected_return_per_stake_factor", "mean"
        ),
    ).reset_index()
    missingness = fixture.groupby(["issue_year", "source_horizon", "source_time_status", "quality_grade", "missingness_reason"], sort=True).agg(
        fixtures=("match_idx", "size"),
        cells=("match_idx", lambda values: int(len(values) * 3)),
    ).reset_index()
    nfold = pd.DataFrame(
        [
            {
                "n": n,
                "full_cartesian_ticket_count": 2**n,
                "gross_expectation_per_unit_per_ticket_formula": "product(selected_fixture.top2_expected_gross_factor)",
                "ticket_payout_factor": PAYOUT_FACTOR,
                "payout_factor_application": "APPLY_ONCE_PER_WINNING_N_FOLD_TICKET",
                "expected_return_per_total_stake_formula": "0.65 * product(selected_fixture.top2_expected_return_per_stake_factor)",
                "equal_leg_break_even_floor": (1.0 / PAYOUT_FACTOR) ** (1.0 / n),
                "selection_status": "NO_SELECTOR_OR_ODDS_FILTER_APPLIED",
            }
            for n in (3, 4, 5)
        ]
    )
    dictionary_rows = []
    for column in cells.columns:
        dictionary_rows.append(
            {
                "artifact": "cells",
                "field": column,
                "dtype": str(cells[column].dtype),
                "availability": "PRE_OUTCOME_PROXY",
            }
        )
    return {
        "coverage": coverage,
        "missingness": missingness,
        "nfold": nfold,
        "field_dictionary": pd.DataFrame(dictionary_rows),
    }


def _implementation_hashes(repo_root: Path) -> dict[str, str]:
    paths = [
        repo_root / "src/low_n_eu_value_data/__init__.py",
        repo_root / "src/low_n_eu_value_data/pipeline.py",
        repo_root / "scripts/run_low_n_eu_value_data.py",
        repo_root / "scripts/verify_low_n_eu_value_data.py",
        repo_root / "scripts/build_low_n_eu_value_notebook.py",
    ]
    return {str(path.relative_to(repo_root)): sha256_file(path) for path in paths}


def _scientific_frames(repo_root: Path, data_root: Path) -> dict[str, Any]:
    feature_path = repo_root / SELECTOR_FEATURE_RELATIVE
    receipt_path = repo_root / SELECTOR_RECEIPT_RELATIVE
    selector = pq.read_table(feature_path).to_pandas()
    issue_codes = set(selector.loc[selector.issue_year.isin(YEARS), "issue"].astype(str))
    odds = read_odds_aggregates(data_root, issue_codes)
    cells = build_value_cells(selector, odds)
    analysis = _analysis_frames(cells)
    source_receipt = {
        "contract": CONTRACT_ID,
        "selector_feature_sha256": sha256_file(feature_path),
        "selector_freeze_receipt_sha256": sha256_file(receipt_path),
        "candidate_sqlite_sha256": sha256_file(data_root / CANDIDATE_SQLITE_RELATIVE),
        "input_horizon": HORIZON,
        "source_time_semantics": "RELATIVE_HORIZON_LABEL_NO_OBSERVED_TIMESTAMP",
        "labels_opened": False,
    }
    freeze_receipt = {
        "contract": CONTRACT_ID,
        "years": list(YEARS),
        "cell_rows": int(len(cells)),
        "fixture_rows": int(cells[["issue", "match_idx"]].drop_duplicates().shape[0]),
        "cell_frame_sha256": stable_frame_sha(cells),
        "top2_policy": "INHERIT_360_CORRECTED_FIXED_TOP2_SUPPORT_NO_REPLACEMENT",
        "selection_policy": "NONE; DATA_INGREDIENTS_ONLY",
        "raw_odds_filter": "NONE; ALL_VALID_BOOKMAKER_TRIPLETS_AVERAGED",
        "payout_65_semantics": "0.65_APPLIED_ONCE_PER_WINNING_N_FOLD_TICKET",
        "labels_opened": False,
    }
    return {
        "cells": cells,
        **analysis,
        "source_receipt": source_receipt,
        "freeze_receipt": freeze_receipt,
        "implementation_hashes": _implementation_hashes(repo_root),
    }


def build_package(repo_root: Path, target: Path, explicit_data_root: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    frames = _scientific_frames(repo_root, data_root)

    def populate(staging: Path) -> None:
        atomic_write_parquet(frames["cells"], staging / "cells" / "eu_value_cells.parquet")
        for name in ("coverage", "missingness", "nfold", "field_dictionary"):
            atomic_write_csv(frames[name], staging / "analysis" / f"{name}.csv")
        atomic_write_json(staging / "SOURCE_RECEIPT.json", frames["source_receipt"])
        atomic_write_json(staging / "FREEZE_RECEIPT.json", frames["freeze_receipt"])
        files = {
            str(path.relative_to(staging)): sha256_file(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        atomic_write_json(
            staging / "MANIFEST.json",
            {"contract": CONTRACT_ID, "implementation_files": frames["implementation_hashes"], "files": files},
        )

    atomic_publish_directory(Path(target), populate, force=force)
    return frames["freeze_receipt"]


def render_report_text(freeze: dict[str, Any], coverage: pd.DataFrame) -> str:
    coverage_rows = "\n".join(
        f"| {int(row.issue_year)} | {int(row.issues)} | {int(row.fixtures)} | {row.mean_contributing_bookmakers:.2f} | {row.mean_top2_coverage_reliability:.4f} | {row.mean_top2_expected_gross_factor:.4f} | {row.mean_top2_expected_return_per_stake_factor:.4f} |"
        for row in coverage.itertuples(index=False)
    )
    return f"""# Issue #358 — causal 10h European-average-odds value proxy

Contract: `{CONTRACT_ID}`

## Decision boundary

This package provides pre-outcome, retrospective-relative 10h European-average-odds inputs for low-N research. It is **not** Beijing official SP, does not calibrate Beijing payouts, applies no raw-odds filter, and selects no fixtures or strategy. It inherits the #360-corrected strictly-prior calibrated probabilities and fixed Top-2 support; it does not read settlement labels.

The provider's `10h` field is a relative snapshot label, not an observed quote timestamp. `source_observed_at_utc` therefore remains null and `source_time_status` explicitly records `RELATIVE_HORIZON_LABEL_NO_OBSERVED_TIMESTAMP` rather than fabricating a time.

## Frozen scope and evidence

- Years: 2017–2021 development lineage; 2022–2024 exposed transfer rows generated after the feature freeze.
- Cell frame SHA-256: `{freeze['cell_frame_sha256']}`
- Fixture rows: {freeze['fixture_rows']:,}; outcome cells: {freeze['cell_rows']:,}.
- Labels opened: `{freeze['labels_opened']}`.
- Raw bookmaker treatment: all complete valid 3/1/0 triplets are averaged; none are filtered by price.

## Annual 10h profile

| Year | Issues | Fixtures | Mean contributing books | Mean Top-2 reliability | Mean Top-2 gross factor | Mean per-stake factor |
|---:|---:|---:|---:|---:|---:|---:|
{coverage_rows}

## Low-N ingredients (N=3–5)

Each cell records average European decimal odds, raw implied probability, fixture overround, de-vig probability, corrected calibrated probability and `p_times_odds`. For each fixed Top-2 fixture support, `top2_coverage_reliability` is the calibrated Top-2 mass and `top2_expected_gross_factor` is the sum of `p_times_odds` across its two supported outcomes. Because the fixed budget is spread equally over two supported outcomes per leg, `top2_expected_return_per_stake_factor = top2_expected_gross_factor / 2`.

For any later selected N-fixture set, the full Cartesian portfolio has `2^N` tickets. Its European-proxy expected gross per total stake is `0.65 × product(top2_expected_return_per_stake_factor)`. This divides by the `2^N` tickets exactly once and applies the Beijing 0.65 burden **once per complete winning ticket**, never once per leg. The equal-leg descriptive break-even floor is `(1 / 0.65) ** (1/N)`; decisions remain full-ticket calculations.

## Reproduction

```bash
python scripts/run_low_n_eu_value_data.py --data-root /absolute/path/to/data --force
python scripts/build_low_n_eu_value_notebook.py
python scripts/verify_low_n_eu_value_data.py --data-root /absolute/path/to/data
```

The semantic verifier checks package closure, implementation and source hashes, independently rebuilds every cell from the #360-corrected pre-outcome frame and #268 raw bookmaker source, and rejects tampered values, Top-2 labels, provenance, or remanifested output.
"""


def write_report(repo_root: Path, target: Path) -> Path:
    package = Path(target)
    freeze = json.loads((package / "FREEZE_RECEIPT.json").read_text(encoding="utf-8"))
    coverage = pd.read_csv(package / "analysis" / "coverage.csv")
    report = repo_root / "docs/research/Issue-358-LowN-European-Value-Data.md"
    from src.source_schema.publication import atomic_write_text

    atomic_write_text(report, render_report_text(freeze, coverage))
    return report


def _verify_delivery_artifacts(repo_root: Path, target: Path, frames: dict[str, Any]) -> bool:
    report = repo_root / "docs/research/Issue-358-LowN-European-Value-Data.md"
    notebook = repo_root / "notebooks/research/low-n-eu-value-data/low_n_eu_value_data_profile.ipynb"
    if not report.is_file() or not notebook.is_file():
        raise AssertionError("required report or executed notebook is missing")
    if report.read_text(encoding="utf-8") != render_report_text(frames["freeze_receipt"], frames["coverage"]):
        raise AssertionError("decision report is not the deterministic rendering of package facts")
    payload = json.loads(notebook.read_text(encoding="utf-8"))
    code_cells = [cell for cell in payload.get("cells", []) if cell.get("cell_type") == "code"]
    if not code_cells or any(cell.get("execution_count") is None for cell in code_cells):
        raise AssertionError("profiling notebook is not fully executed")
    if any(output.get("output_type") == "error" for cell in code_cells for output in cell.get("outputs", [])):
        raise AssertionError("profiling notebook contains an execution error")
    if frames["freeze_receipt"]["cell_frame_sha256"] not in notebook.read_text(encoding="utf-8"):
        raise AssertionError("profiling notebook is not bound to the immutable cell frame")
    return True


def verify_package(repo_root: Path, target: Path, explicit_data_root: Path | None = None) -> dict[str, bool]:
    repo_root = Path(repo_root).resolve()
    target = Path(target).resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    manifest = json.loads((target / "MANIFEST.json").read_text(encoding="utf-8"))
    required = {
        "FREEZE_RECEIPT.json", "SOURCE_RECEIPT.json", "cells/eu_value_cells.parquet",
        "analysis/coverage.csv", "analysis/missingness.csv", "analysis/nfold.csv",
        "analysis/field_dictionary.csv",
    }
    actual = {str(path.relative_to(target)) for path in target.rglob("*") if path.is_file() and path.name != "MANIFEST.json"}
    if set(manifest.get("files", {})) != required or actual != required:
        raise AssertionError("package file inventory is incomplete or has unexpected artifacts")
    if not all(sha256_file(target / relative) == expected for relative, expected in manifest["files"].items()):
        raise AssertionError("package manifest hashes do not match")
    frames = _scientific_frames(repo_root, data_root)
    if manifest.get("implementation_files") != frames["implementation_hashes"]:
        raise AssertionError("implementation hashes do not match")
    if json.loads((target / "SOURCE_RECEIPT.json").read_text(encoding="utf-8")) != frames["source_receipt"]:
        raise AssertionError("source receipt no longer binds current sources")
    cells = pq.read_table(target / "cells" / "eu_value_cells.parquet").to_pandas()
    verify_cell_frame(cells)
    if stable_frame_sha(cells) != frames["freeze_receipt"]["cell_frame_sha256"]:
        raise AssertionError("cell frame does not replay from bound sources")
    if json.loads((target / "FREEZE_RECEIPT.json").read_text(encoding="utf-8")) != frames["freeze_receipt"]:
        raise AssertionError("freeze receipt does not match recomputed scientific frame")
    for name in ("coverage", "missingness", "nfold", "field_dictionary"):
        observed = pd.read_csv(target / "analysis" / f"{name}.csv")
        try:
            pd.testing.assert_frame_equal(
                observed,
                frames[name],
                check_dtype=False,
                check_exact=False,
                rtol=0,
                atol=1e-12,
            )
        except AssertionError as exc:
            raise AssertionError(f"analysis/{name}.csv does not replay from bound cells") from exc
    delivery = _verify_delivery_artifacts(repo_root, target, frames)
    return {
        "manifest_hashes": True,
        "implementation_hashes": True,
        "source_bound_replay": True,
        "semantic_cell_replay": True,
        "semantic_analysis_replay": True,
        "cell_identities": True,
        "label_separation": True,
        "delivery_artifacts": delivery,
    }
