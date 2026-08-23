"""Build and verify Issue #358's pre-outcome European value-proxy panel.

The source's ``10h`` value is a frozen *relative provider horizon*, not an
exact observation timestamp.  This module preserves that limitation explicitly
and never reads a result, settlement, Beijing SP, payout, or selector decision.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pandas.testing import assert_frame_equal

from src.source_schema.publication import (
    atomic_publish_directory,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_parquet,
)

from .contract import (
    CAUSAL_GRADE,
    CONTRACT_ID,
    EU_WORKBOOK_SOURCE_SHA256,
    FEATURE_REQUIRED_COLUMNS,
    HORIZON,
    N_VALUES,
    OUTCOMES,
    RAW_REQUIRED_COLUMNS,
    SELECTOR_FEATURE_FRAME_SHA256,
    SELECTOR_FEATURE_SHA256,
    SOURCE_ROLE,
    SOURCE_TIMESTAMP_SEMANTICS,
    TICKET_PAYOUT_FACTOR,
)


class ContractError(ValueError):
    """Raised when a source or package violates the #358 contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    columns = sorted(frame.columns)
    projected = frame.loc[:, columns]
    hashes = np.sort(
        pd.util.hash_pandas_object(projected, index=False, categorize=False).to_numpy(dtype=np.uint64)
    )
    schema = [(column, str(projected[column].dtype)) for column in columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode("utf-8"))
    digest.update(hashes.tobytes())
    return digest.hexdigest()


def _require_columns(frame: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ContractError(f"{name} missing required columns: {sorted(missing)}")


def _valid_quote_mask(quotes: pd.DataFrame) -> np.ndarray:
    odds = quotes[["v1", "v2", "v3"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    return np.isfinite(odds).all(axis=1) & (odds > 1.0).all(axis=1)


def _raw_group_sha(group: pd.DataFrame) -> str:
    payload = [
        {
            "source_match_id": str(row.source_match_id),
            "bookmaker_id": str(row.bookmaker_id),
            "v1": _optional_float(row.v1),
            "v2": _optional_float(row.v2),
            "v3": _optional_float(row.v3),
        }
        for row in group.sort_values("bookmaker_id", kind="stable").itertuples(index=False)
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _optional_float(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric)


def _validate_features(features: pd.DataFrame) -> pd.DataFrame:
    _require_columns(features, FEATURE_REQUIRED_COLUMNS, "#354 selector features")
    output = features.copy()
    output["issue"] = output["issue"].astype(str)
    output["match_idx"] = pd.to_numeric(output["match_idx"], errors="raise").astype(int)
    key = ["issue", "match_idx"]
    if output.duplicated(key).any():
        raise ContractError("#354 selector features have duplicate issue/match keys")
    if not output["causal_grade"].eq(CAUSAL_GRADE).all():
        raise ContractError("#354 feature causal grade is not the declared relative proxy")
    if not (output["train_year_max"] < output["issue_year"]).all():
        raise ContractError("#354 probability lineage is not strictly prior")
    candidate = output[[f"q_candidate_{code}" for code in OUTCOMES]].to_numpy(dtype=float)
    raw = output[[f"q_raw_eu_{code}" for code in OUTCOMES]].to_numpy(dtype=float)
    if not np.isfinite(candidate).all() or not np.isfinite(raw).all():
        raise ContractError("#354 probability surface has non-finite cells")
    if not np.allclose(candidate.sum(axis=1), 1.0, atol=1e-10, rtol=0):
        raise ContractError("#354 calibrated probability triplets are not normalized")
    if not np.allclose(raw.sum(axis=1), 1.0, atol=1e-10, rtol=0):
        raise ContractError("#354 source consensus triplets are not normalized")
    support = output["baseline_support"].astype(str)
    if (~support.map(lambda value: len(value) == 2 and set(value).issubset(set(OUTCOMES)))).any():
        raise ContractError("#354 Top-2 support is malformed")
    return output


def _aggregate_quotes(quotes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    _require_columns(quotes, RAW_REQUIRED_COLUMNS, "raw European quotes")
    work = quotes.copy()
    work["issue_code"] = work["issue_code"].astype(str)
    work["match_idx"] = pd.to_numeric(work["match_idx"], errors="raise").astype(int)
    work = work.loc[work["snapshot_kind"].eq(HORIZON)].copy()
    if work.empty:
        raise ContractError("raw quote source has no 10h rows")
    key = ["issue_code", "match_idx", "bookmaker_id"]
    if work.duplicated(key).any():
        raise ContractError("raw source has duplicate 10h bookmaker rows")
    work["valid_bookmaker"] = _valid_quote_mask(work)
    work[["v1", "v2", "v3"]] = work[["v1", "v2", "v3"]].apply(pd.to_numeric, errors="coerce")
    keys = ["issue_code", "match_idx"]
    source_counts = work.groupby(keys, sort=True)["source_match_id"].nunique()
    if source_counts.ne(1).any():
        raise ContractError("source issue/match key maps to multiple source fixtures")
    work["_raw_entry"] = [
        json.dumps({"bookmaker_id": str(row.bookmaker_id), "source_match_id": str(row.source_match_id), "v1": _optional_float(row.v1), "v2": _optional_float(row.v2), "v3": _optional_float(row.v3)}, sort_keys=True, separators=(",", ":"))
        for row in work.itertuples(index=False)
    ]
    raw = work.sort_values([*keys, "bookmaker_id"], kind="stable").groupby(keys, sort=True).agg(
        source_match_id=("source_match_id", "first"),
        raw_bookmaker_rows=("bookmaker_id", "size"),
        contributing_bookmaker_count=("valid_bookmaker", "sum"),
        raw_group_sha256=("_raw_entry", lambda values: hashlib.sha256("".join(values).encode("utf-8")).hexdigest()),
    ).reset_index().rename(columns={"issue_code": "issue"})
    raw["invalid_bookmaker_rows"] = raw["raw_bookmaker_rows"] - raw["contributing_bookmaker_count"]
    raw["missing_bookmaker_fraction"] = raw["invalid_bookmaker_rows"] / raw["raw_bookmaker_rows"]
    valid = work.loc[work["valid_bookmaker"]].copy()
    if valid.empty:
        raise ContractError("no valid 10h European quote triplets")
    valid["book_inverse_sum"] = (1.0 / valid[["v1", "v2", "v3"]]).sum(axis=1)
    for code, column in zip(OUTCOMES, ("v1", "v2", "v3"), strict=True):
        valid[f"book_devig_{code}"] = (1.0 / valid[column]) / valid["book_inverse_sum"]
    odds = valid.groupby(keys, sort=True)[["v1", "v2", "v3"]].mean().reset_index().rename(columns={"issue_code": "issue"})
    consensus = valid.groupby(keys, sort=True)[[f"book_devig_{code}" for code in OUTCOMES]].mean().reset_index().rename(columns={"issue_code": "issue"})
    aggregate = raw.merge(odds, on=["issue", "match_idx"], validate="one_to_one").merge(consensus, on=["issue", "match_idx"], validate="one_to_one")
    if aggregate.empty or aggregate.duplicated(["issue", "match_idx"]).any():
        raise ContractError("aggregated raw quote surface is not unique")
    inverse_columns = []
    for code, column in zip(OUTCOMES, ("v1", "v2", "v3"), strict=True):
        aggregate[f"average_european_decimal_odds_{code}"] = aggregate.pop(column)
        inverse_name = f"raw_implied_probability_{code}"
        aggregate[inverse_name] = 1.0 / aggregate[f"average_european_decimal_odds_{code}"]
        inverse_columns.append(inverse_name)
        aggregate[f"source_consensus_devig_probability_{code}"] = aggregate.pop(f"book_devig_{code}")
    aggregate["average_odds_overround"] = aggregate[inverse_columns].sum(axis=1)
    for code in OUTCOMES:
        aggregate[f"average_odds_devig_probability_{code}"] = aggregate[f"raw_implied_probability_{code}"] / aggregate["average_odds_overround"]
    aggregate["source_horizon"] = HORIZON
    aggregate["source_timestamp_utc"] = None
    aggregate["source_timestamp_semantics"] = SOURCE_TIMESTAMP_SEMANTICS
    aggregate["source_role"] = SOURCE_ROLE
    aggregate["source_provenance"] = "beidan_xlsm.sqlite:market_snapshots/euro_1x2"
    aggregate["quality_grade"] = np.select(
        [aggregate["contributing_bookmaker_count"].ge(10) & aggregate["invalid_bookmaker_rows"].eq(0), aggregate["contributing_bookmaker_count"].ge(5)],
        ["A", "B"], default="C",
    )
    quality = aggregate[[
        "issue", "match_idx", "raw_bookmaker_rows", "contributing_bookmaker_count",
        "invalid_bookmaker_rows", "missing_bookmaker_fraction", "quality_grade",
        "source_horizon", "source_timestamp_semantics", "source_provenance",
    ]].copy()
    return aggregate, quality


def build_value_cells(features: pd.DataFrame, quotes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return one transparent 3/1/0 value row per frozen #354 fixture/outcome."""
    feature = _validate_features(features)
    aggregate, quality = _aggregate_quotes(quotes)
    merged = feature.merge(aggregate, on=["issue", "match_idx"], how="left", validate="one_to_one")
    if merged["source_match_id"].isna().any():
        raise ContractError("#354 feature rows have no valid raw 10h European quote group")
    rows: list[dict[str, Any]] = []
    for item in merged.itertuples(index=False):
        expected = np.array([getattr(item, f"q_raw_eu_{code}") for code in OUTCOMES], dtype=float)
        observed = np.array([getattr(item, f"source_consensus_devig_probability_{code}") for code in OUTCOMES], dtype=float)
        if not np.allclose(expected, observed, atol=1e-12, rtol=0):
            raise ContractError("raw source consensus does not match frozen #354 source surface")
        calibrated = np.array([getattr(item, f"q_candidate_{code}") for code in OUTCOMES], dtype=float)
        support = str(item.baseline_support)
        top2_values = [
            calibrated[pos] * float(getattr(item, f"average_european_decimal_odds_{code}"))
            for pos, code in enumerate(OUTCOMES)
            if code in support
        ]
        if len(top2_values) != 2:
            raise ContractError("Top-2 support must resolve exactly two outcomes")
        top2_contribution = float(sum(top2_values) / 2.0)
        for position, code in enumerate(OUTCOMES):
            odds = float(getattr(item, f"average_european_decimal_odds_{code}"))
            probability = float(calibrated[position])
            rows.append({
                "issue": str(item.issue),
                "issue_year": int(item.issue_year),
                "decision_anchor_timestamp_utc": pd.Timestamp(item.issue_anchor_ts).isoformat(),
                "match_idx": int(item.match_idx),
                "source_match_id": str(item.source_match_id),
                "outcome_code": code,
                "outcome_order": position,
                "source_horizon": HORIZON,
                "source_timestamp_utc": None,
                "source_timestamp_semantics": SOURCE_TIMESTAMP_SEMANTICS,
                "source_role": SOURCE_ROLE,
                "source_provenance": str(item.source_provenance),
                "causal_grade": str(item.causal_grade),
                "prediction_role_354": str(item.prediction_role),
                "train_year_max_354": int(item.train_year_max),
                "average_european_decimal_odds": odds,
                "contributing_bookmaker_count": int(item.contributing_bookmaker_count),
                "raw_bookmaker_rows": int(item.raw_bookmaker_rows),
                "invalid_bookmaker_rows": int(item.invalid_bookmaker_rows),
                "missing_bookmaker_fraction": float(item.missing_bookmaker_fraction),
                "quality_grade": str(item.quality_grade),
                "raw_group_sha256": str(item.raw_group_sha256),
                "raw_implied_probability": float(getattr(item, f"raw_implied_probability_{code}")),
                "average_odds_overround": float(item.average_odds_overround),
                "average_odds_devig_probability": float(getattr(item, f"average_odds_devig_probability_{code}")),
                "source_consensus_devig_probability": float(getattr(item, f"source_consensus_devig_probability_{code}")),
                "calibrated_probability_354": probability,
                "p_times_odds_contribution": probability * odds,
                "top2_member": code in support,
                "top2_support": support,
                "top2_retained_mass": float(item.retained_mass),
                "top2_reliability": float(item.prior_global_hit_rate),
                "top2_full_cartesian_contribution": top2_contribution,
                "ticket_level_payout_factor": TICKET_PAYOUT_FACTOR,
                "payout_factor_application": "ONCE_PER_COMPLETE_TICKET",
            })
    cells = pd.DataFrame(rows).sort_values(["issue_year", "issue", "match_idx", "outcome_order"], kind="stable").reset_index(drop=True)
    if cells.duplicated(["issue", "match_idx", "outcome_code"]).any():
        raise ContractError("value cells are not unique")
    outcome_triplets = cells.groupby(["issue", "match_idx"], sort=False)["outcome_code"].agg(tuple)
    if not outcome_triplets.map(lambda triplet: triplet == OUTCOMES).all():
        raise ContractError("value cells do not preserve 3/1/0 outcome order")
    return cells, quality.sort_values(["issue", "match_idx"], kind="stable").reset_index(drop=True)


def build_n_recipe() -> pd.DataFrame:
    """State N3-N5 full-cartesian accounting without selecting any fixtures."""
    return pd.DataFrame([
        {
            "n": n,
            "outcomes_per_fixture": 2,
            "full_cartesian_ticket_count": 2 ** n,
            "ticket_level_payout_factor": TICKET_PAYOUT_FACTOR,
            "payout_factor_application": "ONCE_PER_COMPLETE_TICKET",
            "gross_multiplier_formula": "0.65 * product(top2_full_cartesian_contribution_i)",
            "fixture_selection_performed": False,
            "interpretation": "ingredient only; no fixture subset or strategy is selected",
        }
        for n in N_VALUES
    ])


def _sqlite_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def load_raw_10h_quotes(source_sqlite: Path, feature_keys: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    """Read declared raw 1X2 quote fields only, in read-only mode."""
    path = Path(source_sqlite).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        if {"matches", "market_snapshots", "source_meta"} - {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }:
            raise ContractError("raw European source database is missing required tables")
        if {"match_id", "issue", "match_idx"} - _sqlite_columns(connection, "matches"):
            raise ContractError("raw European source matches schema is incomplete")
        if {"match_id", "market", "bookmaker", "snapshot", "v1", "v2", "v3"} - _sqlite_columns(connection, "market_snapshots"):
            raise ContractError("raw European source snapshots schema is incomplete")
        issues = sorted(feature_keys["issue"].astype(str).unique().tolist())
        if not issues:
            raise ContractError("#354 feature keys are empty")
        placeholders = ",".join("?" for _ in issues)
        query = f"""
            SELECT CAST(m.issue AS TEXT) AS issue_code, m.match_idx,
                   CAST(m.match_id AS TEXT) AS source_match_id,
                   s.snapshot AS snapshot_kind, CAST(s.bookmaker AS TEXT) AS bookmaker_id,
                   s.v1, s.v2, s.v3
            FROM market_snapshots AS s
            JOIN matches AS m ON m.match_id = s.match_id
            WHERE s.market = 'euro_1x2' AND s.snapshot = ?
              AND CAST(m.issue AS TEXT) IN ({placeholders})
            ORDER BY issue_code, m.match_idx, bookmaker_id
        """
        quotes = pd.read_sql_query(query, connection, params=[HORIZON, *issues])
        meta = {str(key): str(value) for key, value in connection.execute("SELECT key, value FROM source_meta")}
    keys = feature_keys[["issue", "match_idx"]].copy()
    keys["issue"] = keys["issue"].astype(str)
    keys["match_idx"] = keys["match_idx"].astype(int)
    quotes["issue_code"] = quotes["issue_code"].astype(str)
    quotes["match_idx"] = quotes["match_idx"].astype(int)
    quotes = quotes.merge(keys.drop_duplicates(), left_on=["issue_code", "match_idx"], right_on=["issue", "match_idx"], how="inner", validate="many_to_one").drop(columns="issue")
    if quotes.empty:
        raise ContractError("raw source query produced no #354-matched 10h quotes")
    return quotes, meta


def _implementation_hashes(repo_root: Path) -> dict[str, str]:
    files = [
        "src/low_n_eu_value/__init__.py",
        "src/low_n_eu_value/contract.py",
        "src/low_n_eu_value/pipeline.py",
        "scripts/run_low_n_eu_value.py",
        "scripts/build_low_n_eu_value_notebook.py",
        "scripts/verify_low_n_eu_value.py",
    ]
    return {relative: sha256_file(repo_root / relative) for relative in files}


def _load_selector_features(path: Path) -> pd.DataFrame:
    source = Path(path).resolve()
    if sha256_file(source) != SELECTOR_FEATURE_SHA256:
        raise ContractError("#354 selector feature payload does not match its committed receipt")
    features = pq.read_table(source).to_pandas()
    if stable_frame_sha(features) != SELECTOR_FEATURE_FRAME_SHA256:
        raise ContractError("#354 selector feature frame does not match frozen receipt")
    return _validate_features(features)


def _trusted_sqlite_sha(path: Path) -> str:
    """Hash a stable SQLite source; a live WAL is an unreceipted read surface."""
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    sidecars = [source.with_name(source.name + suffix) for suffix in ("-wal", "-shm")]
    live = [str(candidate) for candidate in sidecars if candidate.exists() and candidate.stat().st_size > 0]
    if live:
        raise ContractError(f"raw European SQLite has live unreceipted sidecars: {live}")
    return sha256_file(source)


def _scientific_frames(selector_features: Path, source_sqlite: Path) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    features = _load_selector_features(selector_features)
    raw_sqlite_sha256 = _trusted_sqlite_sha(Path(source_sqlite))
    if raw_sqlite_sha256 != EU_WORKBOOK_SOURCE_SHA256:
        raise ContractError("raw European SQLite bytes do not match the trusted #236 source receipt")
    quotes, meta = load_raw_10h_quotes(source_sqlite, features[["issue", "match_idx"]])
    cells, quality = build_value_cells(features, quotes)
    recipe = build_n_recipe()
    year_profile = (
        cells.groupby(["issue_year", "quality_grade"], observed=True, sort=True)
        .agg(
            issues=("issue", "nunique"), fixtures=("match_idx", "nunique"), cells=("outcome_code", "size"),
            mean_contributing_books=("contributing_bookmaker_count", "mean"),
            mean_missing_bookmaker_fraction=("missing_bookmaker_fraction", "mean"),
            mean_overround=("average_odds_overround", "mean"),
            mean_top2_reliability=("top2_reliability", "mean"),
        ).reset_index()
    )
    source = {
        "contract": CONTRACT_ID,
        "selector_feature_path": str(Path(selector_features).resolve()),
        "selector_feature_sha256": SELECTOR_FEATURE_SHA256,
        "selector_feature_frame_sha256": SELECTOR_FEATURE_FRAME_SHA256,
        "raw_european_sqlite_path": str(Path(source_sqlite).resolve()),
        "raw_european_sqlite_sha256": sha256_file(Path(source_sqlite)),
        "trusted_workbook_source_sha256": EU_WORKBOOK_SOURCE_SHA256,
        "source_meta_sha256": hashlib.sha256(json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
    }
    return {"value_cells": cells, "quality": quality, "n_recipe": recipe, "year_profile": year_profile}, source


def build_package(repo_root: Path, target: Path, selector_features: Path, source_sqlite: Path, *, force: bool = False) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    target = Path(target).resolve()
    frames, source = _scientific_frames(selector_features, source_sqlite)
    freeze = {
        "contract": CONTRACT_ID,
        "outcome_order": list(OUTCOMES),
        "horizon": HORIZON,
        "source_timestamp_semantics": SOURCE_TIMESTAMP_SEMANTICS,
        "payout_factor": TICKET_PAYOUT_FACTOR,
        "fixture_selection_performed": False,
        "value_cells_sha256": stable_frame_sha(frames["value_cells"]),
        "quality_sha256": stable_frame_sha(frames["quality"]),
        "n_recipe_sha256": stable_frame_sha(frames["n_recipe"]),
        "year_profile_sha256": stable_frame_sha(frames["year_profile"]),
        "value_cell_count": int(len(frames["value_cells"])),
    }

    def populate(staging: Path) -> None:
        atomic_write_parquet(frames["value_cells"], staging / "value_cells.parquet")
        atomic_write_csv(frames["quality"], staging / "quality_by_fixture.csv")
        atomic_write_csv(frames["year_profile"], staging / "year_profile.csv")
        atomic_write_csv(frames["n_recipe"], staging / "n3_n5_full_cartesian_recipe.csv")
        atomic_write_json(staging / "SOURCE_RECEIPT.json", source)
        atomic_write_json(staging / "FREEZE_RECEIPT.json", freeze)
        files = {str(path.relative_to(staging)): sha256_file(path) for path in sorted(staging.rglob("*")) if path.is_file()}
        atomic_write_json(staging / "MANIFEST.json", {"contract": CONTRACT_ID, "implementation_files": _implementation_hashes(repo_root), "files": files})

    atomic_publish_directory(target, populate, force=force)
    return freeze


def verify_package(repo_root: Path, target: Path, selector_features: Path, source_sqlite: Path) -> dict[str, bool]:
    repo_root, target = Path(repo_root).resolve(), Path(target).resolve()
    manifest = json.loads((target / "MANIFEST.json").read_text(encoding="utf-8"))
    required = {
        "value_cells.parquet", "quality_by_fixture.csv", "year_profile.csv", "n3_n5_full_cartesian_recipe.csv",
        "SOURCE_RECEIPT.json", "FREEZE_RECEIPT.json",
    }
    actual = {str(path.relative_to(target)) for path in target.rglob("*") if path.is_file() and path.name != "MANIFEST.json"}
    if set(manifest.get("files", {})) != required or actual != required:
        raise AssertionError("package inventory is incomplete or has unexpected files")
    if not all(sha256_file(target / relative) == digest for relative, digest in manifest["files"].items()):
        raise AssertionError("package file hashes do not match manifest")
    if manifest.get("implementation_files") != _implementation_hashes(repo_root):
        raise AssertionError("implementation hashes do not match")
    frames, source = _scientific_frames(selector_features, source_sqlite)
    receipt = json.loads((target / "SOURCE_RECEIPT.json").read_text(encoding="utf-8"))
    if receipt != source:
        raise AssertionError("source receipt does not match trusted source replay")
    cells = pq.read_table(target / "value_cells.parquet").to_pandas()
    quality = pd.read_csv(target / "quality_by_fixture.csv", dtype={"issue": "string"})
    profile = pd.read_csv(target / "year_profile.csv")
    recipe = pd.read_csv(target / "n3_n5_full_cartesian_recipe.csv")
    freeze = json.loads((target / "FREEZE_RECEIPT.json").read_text(encoding="utf-8"))
    recomputed = {
        "value_cells_sha256": stable_frame_sha(frames["value_cells"]),
        "quality_sha256": stable_frame_sha(frames["quality"]),
        "n_recipe_sha256": stable_frame_sha(frames["n_recipe"]),
        "year_profile_sha256": stable_frame_sha(frames["year_profile"]),
    }
    if {key: freeze.get(key) for key in recomputed} != recomputed:
        raise AssertionError("freeze receipt does not bind recomputed value facts")
    if stable_frame_sha(cells) != recomputed["value_cells_sha256"]:
        raise AssertionError("value-cell semantic replay does not match packaged values")
    try:
        assert_frame_equal(
            quality.sort_index(axis=1).sort_values(["issue", "match_idx"], kind="stable").reset_index(drop=True),
            frames["quality"].sort_index(axis=1).sort_values(["issue", "match_idx"], kind="stable").reset_index(drop=True),
            check_dtype=False, check_exact=False, atol=1e-12, rtol=0,
        )
        assert_frame_equal(
            profile.sort_index(axis=1).sort_values(["issue_year", "quality_grade"], kind="stable").reset_index(drop=True),
            frames["year_profile"].sort_index(axis=1).sort_values(["issue_year", "quality_grade"], kind="stable").reset_index(drop=True),
            check_dtype=False, check_exact=False, atol=1e-12, rtol=0,
        )
        assert_frame_equal(
            recipe.sort_index(axis=1).sort_values("n", kind="stable").reset_index(drop=True),
            frames["n_recipe"].sort_index(axis=1).sort_values("n", kind="stable").reset_index(drop=True),
            check_dtype=False, check_exact=False, atol=1e-12, rtol=0,
        )
    except AssertionError as exc:
        raise AssertionError("derived-table semantic replay does not match package") from exc
    temporal = (
        cells["source_horizon"].eq(HORIZON).all()
        and cells["causal_grade"].eq(CAUSAL_GRADE).all()
        and cells["source_timestamp_utc"].isna().all()
        and cells["source_timestamp_semantics"].eq(SOURCE_TIMESTAMP_SEMANTICS).all()
        and (cells["train_year_max_354"] < cells["issue_year"]).all()
    )
    if not temporal:
        raise AssertionError("relative-horizon temporal contract failed")
    delivered_outcome_triplets = cells.groupby(["issue", "match_idx"])["outcome_code"].agg(tuple)
    if not delivered_outcome_triplets.map(lambda triplet: triplet == OUTCOMES).all():
        raise AssertionError("outcome order is not 3/1/0")
    if not recipe["ticket_level_payout_factor"].eq(TICKET_PAYOUT_FACTOR).all() or not recipe["fixture_selection_performed"].eq(False).all():
        raise AssertionError("N3-N5 payout/selection boundary failed")
    return {"manifest_hashes": True, "implementation_hashes": True, "source_bound_replay": True, "semantic_replay": True, "temporal_boundary": True, "outcome_identity": True, "n3_n5_boundary": True}
