"""Profiling views with machine-readable table + figure outputs.

Every plot is backed by a committed CSV/Parquet table.  The notebook renders
figures from these tables; the tables themselves are the durable evidence.

Rework (2026-08-15, class-5 sweep):

- ``census_by_cohort`` counts **(issue, match_idx)** pairs, not the ordinal
  ``match_idx.nunique()`` — the audited version reported 5,395 matches while
  the exact count is 119,235 (e.g. 2019 published 680, actual 17,694).
- Added the contract-required development-only calibration/reliability table,
  predicted-SP vs settlement-SP diagnostics, and outlier/heavy-tail/
  redundancy tables (backed by DQ-10).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import contract

OUTCOME_LABELS = {"3": "home", "1": "draw", "0": "away"}


def _vector_to_columns(
    frame: pd.DataFrame, representation: str
) -> pd.DataFrame:
    out = frame.copy()
    if representation not in out.columns:
        return out
    available = out[representation].apply(
        lambda v: isinstance(v, (list, tuple, np.ndarray)) and len(v) == 3
    )
    if not available.any():
        for code in contract.OUTCOME_CODES:
            out[f"{representation}_{code}"] = np.nan
        return out
    exploded = out[representation].apply(pd.Series)
    exploded.columns = [f"{representation}_{c}" for c in contract.OUTCOME_CODES]
    return pd.concat([out, exploded], axis=1)


def _match_pairs(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[["issue", "match_idx"]].drop_duplicates()


def census_by_cohort(cells: pd.DataFrame) -> pd.DataFrame:
    """Exact date/issue/match/cell census by cohort.

    Matches = count of distinct (issue, match_idx) pairs, never the ordinal
    ``match_idx`` count.  Year is taken from the cells' ``year`` column, not
    the issue prefix (issue 190101 is calendar year 2019).
    """
    matches = _match_pairs(cells).copy()
    year_map = (
        cells[["issue", "year"]].drop_duplicates().set_index("issue")["year"]
    )
    matches["year"] = matches["issue"].map(year_map).astype(int)
    cohort_map = (
        cells[["issue", "cohort"]].drop_duplicates().set_index("issue")["cohort"]
        if "cohort" in cells.columns
        else None
    )
    matches["cohort"] = (
        matches["issue"].map(cohort_map)
        if cohort_map is not None
        else "unknown"
    )
    table = (
        cells.groupby(["year", "cohort"], dropna=False)
        .agg(issues=("issue", "nunique"), cells=("cell_key", "size"))
        .reset_index()
    )
    match_counts = (
        matches.groupby(["year", "cohort"], dropna=False)
        .size()
        .reset_index(name="matches")
    )
    table = table.merge(match_counts, on=["year", "cohort"], how="left")
    table["matches"] = table["matches"].fillna(0).astype(int)
    table["year"] = table["year"].astype(int)
    return table


def issue_count_distribution(cells: pd.DataFrame) -> pd.DataFrame:
    """Issue-level count distribution: matches per issue."""
    issue_matches = (
        cells.groupby(["issue", "cohort"])["match_idx"].nunique().reset_index()
    )
    table = (
        issue_matches.groupby("cohort")["match_idx"]
        .agg(["count", "min", "median", "max", "mean"])
        .reset_index()
        .rename(columns={"count": "issues", "match_idx": "matches"})
    )
    return table


def complete_matches_per_n(
    cells: pd.DataFrame, n_values: tuple[int, ...] = (3, 5, 7, 9)
) -> pd.DataFrame:
    """Fraction of issues with at least N complete matches (Q_BJ available)."""
    if contract.Q_BJ_CALIBRATED not in cells.columns:
        return pd.DataFrame()
    complete = cells[contract.Q_BJ_CALIBRATED].apply(
        lambda v: (
            v is not None
            and isinstance(v, (list, tuple, np.ndarray))
            and len(v) == 3
        )
    )
    issue_matches = (
        cells.loc[complete, ["issue", "cohort", "match_idx"]]
        .groupby(["issue", "cohort"])["match_idx"]
        .nunique()
        .reset_index()
    )
    total_issues = cells.groupby(["issue", "cohort"]).size().reset_index()[
        ["issue", "cohort"]
    ]
    total_issues = total_issues.drop_duplicates()
    rows = []
    for n_value in n_values:
        eligible = issue_matches[issue_matches["match_idx"] >= n_value]
        merged = total_issues.merge(
            eligible[["issue", "cohort"]].assign(eligible=True),
            on=["issue", "cohort"],
            how="left",
        )
        merged["eligible"] = merged["eligible"].fillna(False)
        for cohort, group in merged.groupby("cohort"):
            rows.append(
                {
                    "cohort": cohort,
                    "n": n_value,
                    "eligible_issues": int(group["eligible"].sum()),
                    "total_issues": len(group),
                    "fraction": float(group["eligible"].mean()),
                }
            )
    return pd.DataFrame(rows)


def line_league_year_distribution(cells: pd.DataFrame) -> pd.DataFrame:
    """Native-line, league and year distributions."""
    parts = []
    if contract.BJ_LINE_BOUNDARY in cells.columns:
        line = (
            cells.groupby([contract.BJ_LINE_BOUNDARY, "cohort"])
            .size()
            .reset_index(name="cells")
        )
        line["dimension"] = "native_line"
        parts.append(line.rename(columns={contract.BJ_LINE_BOUNDARY: "value"}))
    if "league" in cells.columns:
        league = cells.groupby(["league", "cohort"]).size().reset_index(name="cells")
        league["dimension"] = "league"
        parts.append(league.rename(columns={"league": "value"}))
    year = cells.groupby(["year", "cohort"]).size().reset_index(name="cells")
    year["dimension"] = "year"
    parts.append(year.rename(columns={"year": "value"}))
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def outcome_distribution(cells: pd.DataFrame) -> pd.DataFrame:
    """Outcome-code distribution per cohort (canonical axis)."""
    table = (
        cells.groupby(["outcome_code", "cohort"])
        .size()
        .reset_index(name="cells")
    )
    return table


def sp_and_implied_distribution(
    cells: pd.DataFrame, column: str
) -> pd.DataFrame:
    if column not in cells.columns:
        return pd.DataFrame()
    raw = pd.to_numeric(cells[column], errors="coerce")
    table = raw.describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).reset_index()
    table.columns = ["stat", column]
    table["field"] = column
    return table


def probability_distribution(
    cells: pd.DataFrame, representation: str
) -> pd.DataFrame:
    if representation not in cells.columns:
        return pd.DataFrame()
    exploded = _vector_to_columns(cells, representation)
    parts = []
    for code in contract.OUTCOME_CODES:
        column = f"{representation}_{code}"
        if column not in exploded.columns:
            continue
        values = pd.to_numeric(exploded[column], errors="coerce").dropna()
        stats = values.describe(
            percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
        ).reset_index()
        stats.columns = ["stat", "value"]
        stats["representation"] = representation
        stats["outcome"] = code
        stats["n"] = len(values)
        parts.append(stats)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def bj_raw_vs_calibrated_reconciliation(cells: pd.DataFrame) -> pd.DataFrame:
    """Per-match reconciliation of Q_BJ_SP_DEVIG vs Q_BJ_CALIBRATED."""
    required = [contract.Q_BJ_SP_DEVIG, contract.Q_BJ_CALIBRATED]
    if not all(c in cells.columns for c in required):
        return pd.DataFrame()
    devig = _vector_to_columns(cells, contract.Q_BJ_SP_DEVIG)
    calib = _vector_to_columns(cells, contract.Q_BJ_CALIBRATED)
    rows = []
    for code in contract.OUTCOME_CODES:
        a = pd.to_numeric(devig[f"{contract.Q_BJ_SP_DEVIG}_{code}"], errors="coerce")
        b = pd.to_numeric(calib[f"{contract.Q_BJ_CALIBRATED}_{code}"], errors="coerce")
        both = a.notna() & b.notna()
        rows.append(
            {
                "outcome": code,
                "n_overlap": int(both.sum()),
                "mean_abs_diff": float((a[both] - b[both]).abs().mean())
                if both.any()
                else np.nan,
                "max_abs_diff": float((a[both] - b[both]).abs().max())
                if both.any()
                else np.nan,
                "correlation": float(a[both].corr(b[both]))
                if both.sum() > 2
                else np.nan,
            }
        )
    return pd.DataFrame(rows)


def eu_vs_bj_scatter_table(
    cells: pd.DataFrame, representation: str = contract.Q_EU_BJLINE
) -> pd.DataFrame:
    """EU-vs-BJ per-outcome comparison table by native line."""
    required = [representation, contract.Q_BJ_CALIBRATED, contract.BJ_LINE_BOUNDARY]
    if not all(c in cells.columns for c in required):
        return pd.DataFrame()
    exploded = _vector_to_columns(cells, representation)
    calib = _vector_to_columns(cells, contract.Q_BJ_CALIBRATED)
    line = pd.to_numeric(cells[contract.BJ_LINE_BOUNDARY], errors="coerce")
    rows = []
    for code in contract.OUTCOME_CODES:
        a = pd.to_numeric(exploded[f"{representation}_{code}"], errors="coerce")
        b = pd.to_numeric(calib[f"{contract.Q_BJ_CALIBRATED}_{code}"], errors="coerce")
        both = a.notna() & b.notna() & line.notna()
        table = pd.DataFrame(
            {
                "outcome": code,
                "line": line[both],
                "source_prob": a[both],
                "qbj_prob": b[both],
            }
        )
        rows.append(table)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def power_vs_bj_scatter_table(
    cells: pd.DataFrame, representation: str = contract.P_POWER_BJLINE
) -> pd.DataFrame:
    return eu_vs_bj_scatter_table(cells, representation)


def direction_agreement_matrix(cells: pd.DataFrame) -> pd.DataFrame:
    """EU/POWER same-direction agreement and conflict matrix."""
    required = [
        "divergence_eu_direction",
        "divergence_power_direction",
        "divergence_eu_power_agreement",
    ]
    if not all(c in cells.columns for c in required):
        return pd.DataFrame()
    table = (
        cells.groupby(
            ["divergence_eu_direction", "divergence_power_direction"]
        )
        .size()
        .reset_index(name="cells")
    )
    agreement = (
        cells.groupby("divergence_eu_power_agreement").size().reset_index(name="cells")
    )
    return pd.concat(
        [table.assign(table="direction_matrix"), agreement.assign(table="agreement")],
        ignore_index=True,
    )


def divergence_magnitude_tail(
    cells: pd.DataFrame, column: str = "divergence_magnitude"
) -> pd.DataFrame:
    """Divergence magnitude distribution and tail-support table."""
    if column not in cells.columns:
        return pd.DataFrame()
    raw = pd.to_numeric(cells[column], errors="coerce").dropna()
    if raw.empty:
        return pd.DataFrame()
    quantiles = raw.quantile([0.5, 0.9, 0.95, 0.99, 1.0]).reset_index()
    quantiles.columns = ["quantile", "value"]
    quantiles["field"] = column
    return quantiles


def missingness_matrix(cells: pd.DataFrame) -> pd.DataFrame:
    """Missingness matrix for the probability representations."""
    rows = []
    for representation in [
        contract.Q_BJ_SP_DEVIG,
        contract.Q_BJ_CALIBRATED,
        contract.Q_EU_RAW_1X2,
        contract.Q_EU_BJLINE,
        contract.P_POWER_BJLINE,
    ]:
        if representation not in cells.columns:
            rows.append(
                {
                    "representation": representation,
                    "available": 0,
                    "missing": len(cells),
                    "missing_fraction": 1.0,
                }
            )
            continue
        raw = cells[representation]
        available = raw.apply(
            lambda v: (
                v is not None
                and isinstance(v, (list, tuple, np.ndarray))
                and len(v) == 3
            )
        ).sum()
        rows.append(
            {
                "representation": representation,
                "available": int(available),
                "missing": int(len(cells) - available),
                "missing_fraction": float(1.0 - available / len(cells)),
            }
        )
    return pd.DataFrame(rows)


def intersection_coverage(cells: pd.DataFrame) -> pd.DataFrame:
    """BJ/EU/POWER/SP intersection coverage."""
    def _available(name: str) -> pd.Series:
        raw = cells.get(name)
        if raw is None:
            return pd.Series(False, index=cells.index)
        return raw.apply(
            lambda v: (
                v is not None
                and isinstance(v, (list, tuple, np.ndarray))
                and len(v) == 3
            )
        )

    rows = []
    qbj = _available(contract.Q_BJ_CALIBRATED)
    eu = _available(contract.Q_EU_BJLINE)
    power = _available(contract.P_POWER_BJLINE)
    sp = _available(contract.Q_BJ_SP_DEVIG)
    for name, mask in [
        ("Q_BJ_CALIBRATED", qbj),
        ("Q_BJ_CALIBRATED & Q_EU_BJLINE", qbj & eu),
        ("Q_BJ_CALIBRATED & P_POWER", qbj & power),
        ("Q_BJ_CALIBRATED & Q_EU_BJLINE & P_POWER", qbj & eu & power),
        ("Q_BJ_CALIBRATED & Q_BJ_SP_DEVIG", qbj & sp),
        ("all four", qbj & eu & power & sp),
    ]:
        rows.append(
            {
                "intersection": name,
                "cell_count": int(mask.sum()),
                "fraction": float(mask.mean()),
            }
        )
    return pd.DataFrame(rows)


def exclusion_ledger(checks: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Combine all per-row exclusion checks into one stable ledger."""
    parts = []
    for name, frame in checks.items():
        if frame is None or frame.empty:
            continue
        frame = frame.copy()
        frame["check"] = name
        if "reason_code" in frame.columns:
            identity = [c for c in ("issue", "match_idx") if c in frame.columns]
            keep = ["check"] + identity + ["reason_code"]
            keep += [c for c in ("field", "detail", "intersection", "subset") if c in frame.columns]
            parts.append(frame[keep])
        else:
            parts.append(frame)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def exclusion_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return pd.DataFrame()
    if "reason_code" in ledger.columns:
        return (
            ledger.groupby(["check", "reason_code"]).size().reset_index(name="count")
        )
    return ledger.groupby("check").size().reset_index(name="count")


def drift_table(cells: pd.DataFrame) -> pd.DataFrame:
    """Chronological drift: per-year calibration availability + source mix."""
    rows = []
    groups = cells.groupby("year", dropna=False)
    for year, group in groups:
        if contract.Q_BJ_CALIBRATED in group.columns:
            qbj_available = group[contract.Q_BJ_CALIBRATED].apply(
                lambda v: (
                    v is not None
                    and isinstance(v, (list, tuple, np.ndarray))
                    and len(v) == 3
                )
            ).mean()
        else:
            qbj_available = np.nan
        if "source_grade" in group.columns:
            source_mix = group["source_grade"].value_counts().to_dict()
        else:
            source_mix = {}
        rows.append(
            {
                "year": year,
                "cells": len(group),
                "qbj_available_fraction": qbj_available,
                "source_mix": source_mix,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Development-only reliability / calibration (REQ-D06, class-5 sweep)
# ---------------------------------------------------------------------------
def development_only_calibration(
    cells: pd.DataFrame, labels: pd.DataFrame, root: Path | None = None
) -> pd.DataFrame:
    """Per-source reliability/calibration on development labels (<=2023).

    For each representation with a valid vector on a development cell, bin
    the cell's own-outcome probability into deciles and compare against the
    observed outcome frequency from ``result_code``.  Uses only rows whose
    issue year is <= LABEL_OPEN_MAX_YEAR.
    """
    if labels is None or labels.empty or contract.Q_BJ_CALIBRATED not in cells.columns:
        return pd.DataFrame()
    lab = labels.copy()
    lab["year"] = lab["issue"].astype(str).str[:4].astype(int)
    lab = lab[lab["year"] <= contract.LABEL_OPEN_MAX_YEAR].copy()
    # map raw match_id -> match_idx through #203 identity
    from . import sources as _sources

    root = root or Path(".").resolve()
    identity = _sources.load_bj203_identity(root)
    id_map = (
        identity[["cell_join_key", "issue", "match_idx"]]
        .drop_duplicates()
        .set_index("cell_join_key")["match_idx"]
    )
    lab["match_idx"] = lab["cell_join_key"].map(id_map)
    lab = lab[lab["match_idx"].notna()].copy()
    lab["match_idx"] = lab["match_idx"].astype(int)
    lab["cell_key"] = (
        lab["issue"].astype(str)
        + ":"
        + lab["match_idx"].astype(str)
        + ":"
        + lab["outcome_code"].astype(str)
    )
    # result_code is the native 3/1/0 outcome
    lab["outcome_matched"] = (
        lab["result_code"].astype(str).str.strip() == lab["outcome_code"].astype(str).str.strip()
    )

    exploded = _vector_to_columns(cells, contract.Q_BJ_CALIBRATED)
    exploded["cell_key"] = (
        exploded["issue"].astype(str)
        + ":"
        + exploded["match_idx"].astype(str)
        + ":"
        + exploded["outcome_code"].astype(str)
    )
    calib_col = f"{contract.Q_BJ_CALIBRATED}_{'3'}"
    # build one row per (cell_key, outcome) probability of the cell's own outcome
    own_prob = exploded.apply(
        lambda r: (
            float(r[f"{contract.Q_BJ_CALIBRATED}_{r['outcome_code']}"])
            if pd.notna(r[f"{contract.Q_BJ_CALIBRATED}_{'3'}"])
            and r["outcome_code"] in contract.OUTCOME_CODES
            else np.nan
        ),
        axis=1,
    )
    exploded["own_probability"] = own_prob

    merged = lab.merge(
        exploded[["cell_key", "own_probability"]], on="cell_key", how="left"
    )
    merged = merged[merged["own_probability"].notna()].copy()
    if merged.empty:
        return pd.DataFrame()

    merged["decile"] = pd.qcut(
        merged["own_probability"], 10, labels=False, duplicates="drop"
    )
    table = (
        merged.groupby("decile", dropna=False)
        .agg(
            n=("outcome_matched", "size"),
            observed_freq=("outcome_matched", "mean"),
            mean_prob=("own_probability", "mean"),
        )
        .reset_index()
    )
    table["reliability_gap"] = table["observed_freq"] - table["mean_prob"]
    return table


def predicted_sp_vs_settlement_sp(
    cells: pd.DataFrame, labels: pd.DataFrame, root: Path | None = None
) -> pd.DataFrame:
    """Predicted-SP vs settlement-SP diagnostics on development labels only."""
    if labels is None or labels.empty:
        return pd.DataFrame()
    lab = labels.copy()
    lab["year"] = lab["issue"].astype(str).str[:4].astype(int)
    lab = lab[lab["year"] <= contract.LABEL_OPEN_MAX_YEAR].copy()
    from . import sources as _sources

    root = root or Path(".").resolve()
    identity = _sources.load_bj203_identity(root)
    id_map = (
        identity[["cell_join_key", "issue", "match_idx"]]
        .drop_duplicates()
        .set_index("cell_join_key")["match_idx"]
    )
    lab["match_idx"] = lab["cell_join_key"].map(id_map)
    lab = lab[lab["match_idx"].notna()].copy()
    lab["match_idx"] = lab["match_idx"].astype(int)
    lab["cell_key"] = (
        lab["issue"].astype(str)
        + ":"
        + lab["match_idx"].astype(str)
        + ":"
        + lab["outcome_code"].astype(str)
    )
    cells2 = cells.copy()
    cells2["cell_key"] = (
        cells2["issue"].astype(str)
        + ":"
        + cells2["match_idx"].astype(str)
        + ":"
        + cells2["outcome_code"].astype(str)
    )
    merged = lab.merge(
        cells2[["cell_key", "predicted_final_sp_input"]], on="cell_key", how="left"
    )
    both = merged[
        merged["predicted_final_sp_input"].notna() & merged["final_sp"].notna()
    ].copy()
    if both.empty:
        return pd.DataFrame()
    both["pred"] = pd.to_numeric(both["predicted_final_sp_input"], errors="coerce")
    both["settled"] = pd.to_numeric(both["final_sp"], errors="coerce")
    both = both[both["pred"].notna() & both["settled"].notna()]
    if both.empty:
        return pd.DataFrame()
    diff = (both["pred"] - both["settled"]).abs()
    return pd.DataFrame(
        {
            "stat": [
                "n",
                "mean_abs_diff",
                "median_abs_diff",
                "max_abs_diff",
                "correlation",
            ],
            "value": [
                len(both),
                float(diff.mean()),
                float(diff.median()),
                float(diff.max()),
                float(both["pred"].corr(both["settled"])),
            ],
        }
    )


def outlier_heavy_tail_table(dq10: pd.DataFrame) -> pd.DataFrame:
    """Outlier/heavy-tail/redundancy summary table from DQ-10."""
    if dq10 is None or dq10.empty:
        return pd.DataFrame(
            {"field": [], "reason_code": [], "detail": []}
        )
    return dq10.copy()
