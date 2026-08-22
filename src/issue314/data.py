"""Causal feature and settlement boundaries for Issue #314."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

OUTCOMES = ("3", "1", "0")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = Path(
    os.environ.get("BEIJING_LOT_RUNTIME_ROOT", REPOSITORY_ROOT)
).resolve()
INFERENCE = (
    RUNTIME_ROOT
    / "data/derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
)
SETTLEMENT = RUNTIME_ROOT / "data/derived/beidan_xlsm/beidan_xlsm.sqlite"
SUPPORT = REPOSITORY_ROOT / "results/issue-299/support_receipt.csv"


def load_pre_event_units(years: tuple[int, ...]) -> pd.DataFrame:
    """Read only the frozen 10h pre-event projection for requested years."""

    columns = [
        "issue_code",
        "match_idx",
        "snapshot_kind",
        "issue_anchor_ts",
        "issue_year",
        "temporal_role",
        "native_handicap_line",
        "n_available_books",
        "mapping_accepted",
        "outcome_code",
        "q_eu_bjline",
        "q_line_only_control",
        "eu_vs_line_divergence",
    ]
    long = pq.read_table(
        INFERENCE,
        filters=[("issue_year", "in", list(years)), ("snapshot_kind", "=", "10h")],
        columns=columns,
    ).to_pandas()
    long["issue"] = long.pop("issue_code").astype(str)
    long["outcome_code"] = long["outcome_code"].astype(str)
    long = long[long["outcome_code"].isin(OUTCOMES)].copy()
    keys = ["issue", "match_idx"]
    fixed = long.groupby(keys, as_index=False).agg(
        issue_year=("issue_year", "first"),
        issue_anchor_ts=("issue_anchor_ts", "first"),
        source_temporal_role=("temporal_role", "first"),
        native_handicap_line=("native_handicap_line", "first"),
        n_available_books=("n_available_books", "first"),
        mapping_accepted=("mapping_accepted", "min"),
    )
    wide = long.pivot_table(
        index=keys,
        columns="outcome_code",
        values=["q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence"],
        aggfunc="first",
    )
    wide.columns = [f"{name}_{outcome}" for name, outcome in wide.columns]
    units = fixed.merge(wide.reset_index(), on=keys, validate="one_to_one")
    for prefix in ("q_eu_bjline", "q_line_only_control"):
        cols = [f"{prefix}_{outcome}" for outcome in OUTCOMES]
        units[cols] = units[cols].apply(pd.to_numeric, errors="coerce")
        total = units[cols].sum(axis=1).replace(0.0, np.nan)
        units[cols] = units[cols].div(total, axis=0)
    units["experiment_role"] = np.select(
        [
            units["issue_year"].le(2021),
            units["issue_year"].eq(2022),
            units["issue_year"].eq(2023),
            units["issue_year"].eq(2024),
        ],
        ["train", "screen", "validation", "terminal"],
        default="excluded",
    )
    units = _apply_support(units)
    required = [
        *(f"q_eu_bjline_{outcome}" for outcome in OUTCOMES),
        *(f"q_line_only_control_{outcome}" for outcome in OUTCOMES),
        *(f"eu_vs_line_divergence_{outcome}" for outcome in OUTCOMES),
    ]
    units = units.dropna(subset=required).sort_values(
        ["issue_year", "issue", "match_idx"]
    )
    if units.duplicated(keys).any():
        raise AssertionError("pre-event unit key is not unique")
    if set(units["source_temporal_role"].dropna()) & set(
        units["experiment_role"].dropna()
    ):
        # Equal text is not inherently wrong, but the interfaces must remain distinct.
        pass
    return units.reset_index(drop=True)


def load_settlement(issues: set[str]) -> pd.DataFrame:
    """Open settlement only for an explicit frozen issue set."""

    if not issues:
        return pd.DataFrame()
    ordered = sorted(str(issue) for issue in issues)
    placeholders = ",".join("?" for _ in ordered)
    database = SETTLEMENT.resolve()
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        frame = pd.read_sql_query(
            f"""
            SELECT CAST(issue AS TEXT) AS issue, match_idx, result_code,
                   winning_sp, official_sp_3, official_sp_1, official_sp_0,
                   has_trusted_settlement
            FROM match_features
            WHERE CAST(issue AS TEXT) IN ({placeholders})
            """,
            connection,
            params=ordered,
        )
    frame["issue"] = frame["issue"].astype(str)
    frame["result_code"] = frame["result_code"].astype("string")
    frame = frame.drop_duplicates(["issue", "match_idx"], keep="first")
    fallback = pd.Series(np.nan, index=frame.index, dtype=float)
    for outcome in OUTCOMES:
        mask = frame["result_code"].eq(outcome)
        fallback.loc[mask] = pd.to_numeric(
            frame.loc[mask, f"official_sp_{outcome}"], errors="coerce"
        )
    frame["settlement_sp"] = pd.to_numeric(frame["winning_sp"], errors="coerce")
    frame["settlement_sp"] = frame["settlement_sp"].fillna(fallback)
    frame["settlement_available"] = frame["result_code"].isin(OUTCOMES) & frame[
        "settlement_sp"
    ].gt(0)
    if not set(frame["issue"]).issubset(issues):
        raise AssertionError("settlement query escaped frozen issue set")
    return frame[
        [
            "issue",
            "match_idx",
            "result_code",
            "settlement_sp",
            "settlement_available",
            "has_trusted_settlement",
        ]
    ].reset_index(drop=True)


def issue_features(units: pd.DataFrame) -> pd.DataFrame:
    """Aggregate Mx3 pre-event cells without settlement fields."""

    rows: list[dict[str, object]] = []
    for issue, group in units.groupby("issue", sort=True):
        market = group[[f"q_eu_bjline_{c}" for c in OUTCOMES]].to_numpy(float)
        line = group[[f"q_line_only_control_{c}" for c in OUTCOMES]].to_numpy(float)
        divergence = market - line
        value = market / np.clip(line, 1e-6, None)
        entropy = -np.sum(market * np.log(np.clip(market, 1e-12, 1.0)), axis=1)
        rows.append(
            {
                "issue": str(issue),
                "issue_year": int(group["issue_year"].iloc[0]),
                "source_temporal_role": str(group["source_temporal_role"].iloc[0]),
                "experiment_role": str(group["experiment_role"].iloc[0]),
                "n_matches": int(len(group)),
                "books_mean": float(group["n_available_books"].mean()),
                "line_abs_mean": float(group["native_handicap_line"].abs().mean()),
                "line_std": float(group["native_handicap_line"].std(ddof=0)),
                "market_top_mean": float(market.max(axis=1).mean()),
                "market_top_q90": float(np.quantile(market.max(axis=1), 0.9)),
                "entropy_mean": float(entropy.mean()),
                "divergence_abs_mean": float(np.abs(divergence).mean()),
                "divergence_abs_q90": float(np.quantile(np.abs(divergence), 0.9)),
                "divergence_signed_mean": float(divergence.mean()),
                "value_best_mean": float(value.max(axis=1).mean()),
                "value_best_q90": float(np.quantile(value.max(axis=1), 0.9)),
                "accepted_fraction": float(
                    group["mapping_accepted"].astype(bool).mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def source_receipt(
    units: pd.DataFrame, settlement: pd.DataFrame | None = None
) -> dict[str, object]:
    """Return path-independent hashes of the exact projections consumed."""

    feature_columns = sorted(units.columns)
    feature_hash = hashlib.sha256(
        pd.util.hash_pandas_object(
            units.sort_values(["issue", "match_idx"])[feature_columns], index=False
        ).values.tobytes()
    ).hexdigest()
    payload: dict[str, object] = {
        "feature_projection_sha256": feature_hash,
        "feature_rows": int(len(units)),
        "issues": int(units["issue"].nunique()),
        "years": sorted(int(v) for v in units["issue_year"].unique()),
        "inference_schema_sha256": hashlib.sha256(
            str(pq.read_schema(INFERENCE)).encode()
        ).hexdigest(),
        "external_sources_committed_to_git": False,
        "access": "BEIJING_LOT_RUNTIME_ROOT/data/derived; see README data operations",
    }
    if settlement is not None:
        columns = sorted(settlement.columns)
        payload["settlement_projection_sha256"] = hashlib.sha256(
            pd.util.hash_pandas_object(
                settlement.sort_values(["issue", "match_idx"])[columns], index=False
            ).values.tobytes()
        ).hexdigest()
        payload["settlement_rows"] = int(len(settlement))
    return payload


def _apply_support(units: pd.DataFrame) -> pd.DataFrame:
    historical = pd.read_csv(SUPPORT, dtype={"issue": str})
    accepted = set(
        historical.loc[
            historical["support_status"].eq("MATCHED_BASELINE_AND_FEATURES"), "issue"
        ]
    )
    keep = units["issue_year"].eq(2024) | units["issue"].isin(accepted)
    return units[keep].copy()
