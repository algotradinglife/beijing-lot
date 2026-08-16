"""Issue #232 — independent-source reconciliation (contract item 5, R2).

R2 fresh (EV C2): every causal decision flows through the unified gate
(observed_at <= epoch <= kickoff); POWER completeness uses team_primary_p*;
the EU/POWER intersection logic in modelability reuses these reconciliation
views instead of re-deriving with different gates.

Two reconciliation paths are attempted:

1. POWER (``P_POWER_BJLINE``): #180 probabilities are already in native
   3/1/0 BJ space with a per-match handicap line; the identical native-line
   space is enforced by joining on (issue, match_idx) AND comparing the #180
   line to the #204 anchor line.
2. EU (``Q_EU_RAW_1X2`` -> ``Q_EU_BJLINE``): de-vig EURO probabilities are
   translated to native BJ handicap space only when the match has a legal
   zero native line (identity translation); non-zero lines are reported as
   TRANSLATION_NOT_IDENTIFIABLE, never silently blended.

The reconciliation is published only on cells where BOTH sides are causally
available; same-source alias rows (avg-EU cells where Q_BJ and EU share the
same upstream value) are explicitly unavailable for the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import contract
from .causal import causal_available


@dataclass
class Reconciliation:
    power: pd.DataFrame = field(default_factory=pd.DataFrame)
    eu: pd.DataFrame = field(default_factory=pd.DataFrame)
    receipts: pd.DataFrame = field(default_factory=pd.DataFrame)


def _load_anchor(root: Path) -> pd.DataFrame:
    pkg204 = contract.upstream_path(root, "bj204")
    features = pq.read_table(pkg204 / "common_cell_features.parquet").to_pandas()
    features["issue"] = features["issue"].astype(str).str.strip()
    features["match_idx"] = features["match_idx"].astype(int)
    features["outcome_code"] = features["outcome_code"].astype(str)
    identity = pq.read_table(
        contract.upstream_path(root, "bj203") / "inference/cell_identity.parquet"
    ).to_pandas()
    identity["issue"] = identity["issue"].astype(str).str.strip()
    identity["match_idx"] = identity["match_idx"].astype(int)
    meta = identity[
        [
            "issue",
            "match_idx",
            "feature_cutoff_ts_utc",
            "kickoff_ts_utc",
            "euro_1h_available_ts_utc",
            "year",
        ]
    ].drop_duplicates()
    anchor = features.merge(
        meta, on=["issue", "match_idx"], how="left", validate="many_to_one",
        suffixes=("_features", "_meta"),
    )
    is_avg_eu = (
        pd.to_numeric(anchor.get("source_is_average_eu"), errors="coerce")
        .fillna(0)
        .astype(float)
        .eq(1.0)
    )
    anchor["qbj_causal_available"] = is_avg_eu & causal_available(
        anchor["euro_1h_available_ts_utc"],
        anchor["feature_cutoff_ts_utc"],
        anchor["kickoff_ts_utc"],
    )
    anchor["year"] = anchor["year_meta"].fillna(anchor["year_features"])
    return anchor


def _is_legal_handicap(line: float) -> bool:
    value = float(line)
    return bool(np.isfinite(value) and abs(value - round(value * 2) / 2) < 1e-9)


def reconcile(root: Path) -> Reconciliation:
    """Attempt POWER and EU reconciliation on the identical causal space."""
    anchor = _load_anchor(root)
    result = Reconciliation()

    # ------------------------------------------------------------------
    # POWER path (#180)
    # ------------------------------------------------------------------
    pkg180 = contract.upstream_path(root, "bj180")
    power = pd.read_csv(
        pkg180 / "match_probability_freeze.csv.gz", compression="gzip",
        usecols=contract.SOURCE_FIELD_WHITELIST["bj180_match_probability_freeze"],
    )
    power["issue"] = power["issue"].astype(str).str.strip()
    power["match_idx"] = power["match_idx"].astype(int)
    # #180 timestamps are naive Beijing time (+08:00 per #229 verified binding).
    power_ts_raw = pd.to_datetime(power.get("feature_cutoff_ts"), errors="coerce")
    power_ts = power_ts_raw.dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC")
    power["power_cutoff_ts_utc"] = power_ts

    power_matches = power[
        ["issue", "match_idx", "handicap_line_norm", "power_cutoff_ts_utc"]
    ].drop_duplicates()
    merged = anchor.merge(
        power_matches,
        on=["issue", "match_idx"],
        how="inner",
        validate="many_to_one",
        suffixes=("", "_power"),
    )
    merged["power_causal"] = causal_available(
        merged["power_cutoff_ts_utc"],
        merged["feature_cutoff_ts_utc"],
        merged["kickoff_ts_utc"],
    )
    line_both = pd.to_numeric(merged["native_handicap_line"], errors="coerce")
    line_power = pd.to_numeric(merged["handicap_line_norm"], errors="coerce")
    merged["line_reconciled"] = line_both.notna() & line_power.notna() & np.isclose(
        line_both, line_power, atol=1e-9
    )
    merged["line_reconcile_reason"] = np.where(
        merged["line_reconciled"],
        "MATCH",
        np.where(
            line_both.isna() | line_power.isna(),
            contract.REASON_MISSING_NATIVE_LINE,
            contract.REASON_LINE_MISMATCH,
        ),
    )

    power_causal = merged[
        merged["qbj_causal_available"] & merged["power_causal"] & merged["line_reconciled"]
    ]
    power_view = power_causal[
        [
            "issue",
            "match_idx",
            "outcome_code",
            "year",
            "market_probability",
            "native_handicap_line",
            "line_reconcile_reason",
            "qbj_causal_available",
            "power_causal",
        ]
    ].copy()
    result.power = power_view

    # ------------------------------------------------------------------
    # EU path (#203 de-vig -> native BJ line, zero-line identity only)
    # ------------------------------------------------------------------
    pkg203 = contract.upstream_path(root, "bj203")
    values = pq.read_table(
        pkg203 / "inference/feature_values.parquet",
        columns=list(contract.SOURCE_FIELD_WHITELIST["bj203_devig_euro_probability"]),
    ).to_pandas()
    identity = pq.read_table(
        pkg203 / "inference/cell_identity.parquet"
    ).to_pandas()
    key_map = identity[["cell_join_key", "issue", "match_idx", "outcome_code"]]
    key_map["cell_join_key"] = key_map["cell_join_key"].astype(str)
    values["cell_join_key"] = values["cell_join_key"].astype(str)
    eu = values.merge(key_map, on="cell_join_key", how="inner", validate="one_to_one")
    eu["issue"] = eu["issue"].astype(str).str.strip()
    eu["match_idx"] = eu["match_idx"].astype(int)
    eu["outcome_code"] = eu["outcome_code"].astype(str)

    eu_merge = eu.drop(columns=["native_handicap_line"], errors="ignore").merge(
        anchor[
            [
                "issue",
                "match_idx",
                "outcome_code",
                "year",
                "feature_cutoff_ts_utc",
                "kickoff_ts_utc",
                "euro_1h_available_ts_utc",
                "qbj_causal_available",
                "native_handicap_line",
                "source_is_average_eu",
            ]
        ],
        on=["issue", "match_idx", "outcome_code"],
        how="inner",
        validate="one_to_one",
    )
    eu_merge["eu_causal"] = causal_available(
        eu_merge["euro_1h_available_ts_utc"],
        eu_merge["feature_cutoff_ts_utc"],
        eu_merge["kickoff_ts_utc"],
    )
    line = pd.to_numeric(eu_merge["native_handicap_line"], errors="coerce")
    eu_merge["line_is_legal"] = line.map(
        lambda value: bool(_is_legal_handicap(value)) if pd.notna(value) else False
    )
    # Q_EU_BJLINE translation: zero native line -> identity translation;
    # non-zero line -> unavailable with explicit reason.
    eu_merge["translation_available"] = eu_merge["line_is_legal"] & np.isclose(
        line.fillna(np.inf), 0.0, atol=1e-9
    )
    eu_merge["translation_reason"] = np.where(
        eu_merge["translation_available"],
        "IDENTITY_TRANSLATION_ZERO_LINE",
        contract.REASON_TRANSLATION_NOT_IDENTIFIABLE,
    )
    # avg-EU cells share the same upstream value as Q_BJ -> non-independent.
    is_avg_eu = (
        pd.to_numeric(eu_merge.get("source_is_average_eu"), errors="coerce")
        .fillna(0)
        .astype(float)
        .eq(1.0)
    )
    eu_merge["same_source_alias"] = is_avg_eu
    eu_causal = eu_merge[
        eu_merge["eu_causal"]
        & eu_merge["qbj_causal_available"]
        & eu_merge["translation_available"]
        & ~eu_merge["same_source_alias"]
    ]
    eu_view = eu_causal[
        [
            "issue",
            "match_idx",
            "outcome_code",
            "year",
            "devig_euro_probability",
            "native_handicap_line",
            "translation_reason",
            "qbj_causal_available",
            "eu_causal",
            "same_source_alias",
        ]
    ].copy()
    result.eu = eu_view

    result.receipts = pd.DataFrame(
        [
            {
                "interface": "Q_BJ_x_POWER_BJLINE",
                "reconciled_cells": int(len(power_view)),
                "reconciled_issues": int(power_view["issue"].nunique())
                if len(power_view)
                else 0,
                "line_reconciled": int(merged["line_reconciled"].sum())
                if len(merged)
                else 0,
            },
            {
                "interface": "Q_BJ_x_EU_BJLINE",
                "reconciled_cells": int(len(eu_view)),
                "reconciled_issues": int(eu_view["issue"].nunique())
                if len(eu_view)
                else 0,
                "translation_available": int(eu_merge["translation_available"].sum())
                if len(eu_merge)
                else 0,
            },
        ]
    )
    return result
