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


def _causal_mask(frame: pd.DataFrame, representation: str) -> pd.Series:
    """The sole availability predicate used by every profiling consumer."""
    name = contract.available_col(representation)
    if name not in frame.columns:
        return pd.Series(False, index=frame.index)
    return frame[name].fillna(False).astype(bool)


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
    complete = _causal_mask(cells, contract.Q_BJ_CALIBRATED)
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
    """Per-outcome distribution on causal support, with empty receipts."""
    parts = []
    causal = _causal_mask(cells, representation)
    exploded = _vector_to_columns(cells.loc[causal].copy(), representation)
    for code in contract.OUTCOME_CODES:
        column = f"{representation}_{code}"
        values = (
            pd.to_numeric(exploded[column], errors="coerce").dropna()
            if column in exploded.columns
            else pd.Series(dtype=float)
        )
        if values.empty:
            parts.append(
                pd.DataFrame(
                    {
                        "stat": ["count"],
                        "value": [np.nan],
                        "representation": [representation],
                        "outcome": [code],
                        "n": [0],
                        "status": ["UNAVAILABLE_NO_CAUSAL_SUPPORT"],
                    }
                )
            )
            continue
        stats = values.describe(
            percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
        ).reset_index()
        stats.columns = ["stat", "value"]
        stats["representation"] = representation
        stats["outcome"] = code
        stats["n"] = len(values)
        stats["status"] = "AVAILABLE"
        parts.append(stats)
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
        both = (
            a.notna()
            & b.notna()
            & _causal_mask(cells, contract.Q_BJ_SP_DEVIG)
            & _causal_mask(cells, contract.Q_BJ_CALIBRATED)
        )
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
        both = (
            a.notna()
            & b.notna()
            & line.notna()
            & _causal_mask(cells, representation)
            & _causal_mask(cells, contract.Q_BJ_CALIBRATED)
            & _causal_mask(cells, contract.BJ_LINE_BOUNDARY)
        )
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
    empty_receipt = pd.DataFrame(
        [
            {
                "quantile": np.nan,
                "value": np.nan,
                "field": column,
                "status": "UNAVAILABLE_NO_CAUSAL_SUPPORT",
            }
        ]
    )
    if column not in cells.columns:
        return empty_receipt
    raw = pd.to_numeric(cells[column], errors="coerce").dropna()
    if raw.empty:
        return empty_receipt
    quantiles = raw.quantile([0.5, 0.9, 0.95, 0.99, 1.0]).reset_index()
    quantiles.columns = ["quantile", "value"]
    quantiles["field"] = column
    quantiles["status"] = "AVAILABLE"
    return quantiles


def missingness_matrix(cells: pd.DataFrame) -> pd.DataFrame:
    """Raw presence and causal availability for every probability source."""
    rows = []
    for representation in contract.PROBABILITY_REPRESENTATIONS:
        raw = cells.get(representation, pd.Series(index=cells.index, dtype=object))
        raw_present = int(
            raw.apply(
                lambda value: isinstance(value, (list, tuple, np.ndarray))
                and len(value) == 3
            ).sum()
        )
        causally_available = int(_causal_mask(cells, representation).sum())
        rows.append(
            {
                "representation": representation,
                "raw_present": raw_present,
                "causally_available": causally_available,
                "unavailable": int(len(cells) - causally_available),
                "unavailable_fraction": (
                    float(1.0 - causally_available / len(cells)) if len(cells) else 1.0
                ),
                "missing_fraction": (
                    float(1.0 - causally_available / len(cells)) if len(cells) else 1.0
                ),
            }
        )
    return pd.DataFrame(rows)


def intersection_coverage(cells: pd.DataFrame) -> pd.DataFrame:
    """BJ/EU/POWER/SP intersection coverage on causal masks only."""
    rows = []
    qbj = _causal_mask(cells, contract.Q_BJ_CALIBRATED)
    eu = _causal_mask(cells, contract.Q_EU_BJLINE)
    power = _causal_mask(cells, contract.P_POWER_BJLINE)
    sp = _causal_mask(cells, contract.Q_BJ_SP_DEVIG)
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


def readiness_support(cells: pd.DataFrame) -> dict[str, int]:
    """Return the causal interfaces that #209 can actually consume.

    A market anchor by itself is not a divergence/value interface.  The
    downstream learner needs both a pre-event SP leg and at least one
    independent probability source expressed in the same BJ outcome space.
    """
    qbj = _causal_mask(cells, contract.Q_BJ_CALIBRATED)
    eu = _causal_mask(cells, contract.Q_EU_BJLINE)
    power = _causal_mask(cells, contract.P_POWER_BJLINE)
    sp = _causal_mask(cells, contract.Q_BJ_SP_DEVIG)
    return {
        "qbj_anchor": int(qbj.sum()),
        "qbj_x_eu": int((qbj & eu).sum()),
        "qbj_x_power": int((qbj & power).sum()),
        "qbj_x_sp": int((qbj & sp).sum()),
        "qbj_x_eu_x_sp": int((qbj & eu & sp).sum()),
        "qbj_x_power_x_sp": int((qbj & power & sp).sum()),
    }


def readiness_disposition(
    cells: pd.DataFrame, *, has_post_decision_exclusions: bool = False
) -> str:
    """Apply the frozen #209 minimum-support gate."""
    support = readiness_support(cells)
    has_eu_interface = support["qbj_x_eu_x_sp"] > 0
    has_power_interface = support["qbj_x_power_x_sp"] > 0
    if not (has_eu_interface or has_power_interface):
        return "BLOCKED_DATA_DEFECT"
    if has_post_decision_exclusions or not (
        has_eu_interface and has_power_interface
    ):
        return "READY_WITH_EXPLICIT_LIMITATIONS"
    return "READY_FOR_209"


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
    """Chronological drift by probability source × year × cohort."""
    rows = []
    for (year, cohort), group in cells.groupby(["year", "cohort"], dropna=False):
        for representation in contract.PROBABILITY_REPRESENTATIONS:
            available = _causal_mask(group, representation)
            raw = group.get(representation, pd.Series(index=group.index, dtype=object))
            raw_present = int(
                raw.apply(
                    lambda value: isinstance(value, (list, tuple, np.ndarray))
                    and len(value) == 3
                ).sum()
            )
            rows.append(
                {
                    "year": int(year) if pd.notna(year) else np.nan,
                    "cohort": cohort,
                    "representation": representation,
                    "cells": len(group),
                    "raw_present_cells": raw_present,
                    "causally_available_cells": int(available.sum()),
                    "causal_coverage_fraction": float(available.mean()),
                    "status": (
                        "AVAILABLE"
                        if available.any()
                        else "UNAVAILABLE_NO_CAUSAL_SUPPORT"
                    ),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Development-only reliability / calibration (REQ-D06, class-5 sweep)
# ---------------------------------------------------------------------------
def development_only_calibration(
    cells: pd.DataFrame, labels: pd.DataFrame
) -> pd.DataFrame:
    """Reliability for every source × outcome × development cohort.

    ``labels`` is the physical handoff table and already carries authoritative
    ``cell_key``/``year``.  This function intentionally has no path to private
    upstream maps.
    Empty overlaps are first-class rows rather than vanished analyses.
    """
    if labels is None or labels.empty:
        return pd.DataFrame()
    required = {"cell_key", "year", "outcome_code"}
    if not required.issubset(labels.columns):
        raise ValueError(f"development labels missing package keys: {sorted(required - set(labels.columns))}")
    lab = labels[labels["year"].astype(int) <= contract.LABEL_OPEN_MAX_YEAR].copy()
    if "is_winner" not in lab.columns:
        if "result_code" not in lab.columns:
            raise ValueError("development labels require is_winner or result_code")
        lab["is_winner"] = (
            lab["result_code"].astype(str).str.strip()
            == lab["outcome_code"].astype(str).str.strip()
        )
    cohorts = sorted(cells.get("cohort", pd.Series(["development"])).dropna().astype(str).unique())
    cohorts = [cohort for cohort in cohorts if cohort == "development"] or ["development"]
    rows: list[dict[str, object]] = []
    for representation in contract.PROBABILITY_REPRESENTATIONS:
        available = _causal_mask(cells, representation)
        sub_cells = cells.loc[available].copy()
        for cohort in cohorts:
            cohort_cells = sub_cells[sub_cells.get("cohort", "development") == cohort]
            for outcome in contract.OUTCOME_CODES:
                outcome_cells = cohort_cells[
                    cohort_cells["outcome_code"].astype(str) == outcome
                ].copy()
                if outcome_cells.empty:
                    merged = pd.DataFrame()
                else:
                    outcome_cells["probability"] = outcome_cells[representation].apply(
                        lambda value: float(value[contract.OUTCOME_ORDER[outcome]])
                        if isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3
                        else np.nan
                    )
                    merged = outcome_cells[["cell_key", "probability"]].merge(
                        lab[["cell_key", "is_winner"]], on="cell_key", how="inner", validate="one_to_one"
                    ).dropna(subset=["probability"])
                if merged.empty:
                    rows.append(
                        {
                            "representation": representation,
                            "outcome": outcome,
                            "cohort": cohort,
                            "year_namespace": "through_2023",
                            "bin": np.nan,
                            "n": 0,
                            "observed_freq": np.nan,
                            "mean_prob": np.nan,
                            "reliability_gap": np.nan,
                            "status": "UNAVAILABLE_NO_CAUSAL_LABEL_OVERLAP",
                        }
                    )
                    continue
                merged["bin"] = pd.cut(
                    merged["probability"], bins=np.linspace(0.0, 1.0, 11),
                    labels=False, include_lowest=True
                )
                grouped = merged.groupby("bin", dropna=False).agg(
                    n=("is_winner", "size"),
                    observed_freq=("is_winner", "mean"),
                    mean_prob=("probability", "mean"),
                ).reset_index()
                grouped["reliability_gap"] = grouped["observed_freq"] - grouped["mean_prob"]
                for record in grouped.to_dict("records"):
                    rows.append(
                        {
                            "representation": representation,
                            "outcome": outcome,
                            "cohort": cohort,
                            "year_namespace": "through_2023",
                            **record,
                            "status": "AVAILABLE",
                        }
                    )
    return pd.DataFrame(rows)


def predicted_sp_vs_settlement_sp(
    cells: pd.DataFrame, labels: pd.DataFrame
) -> pd.DataFrame:
    """Predicted-SP vs settlement-SP diagnostics on development labels only."""
    if labels is None or labels.empty:
        return pd.DataFrame()
    if not {"cell_key", "year"}.issubset(labels.columns):
        raise ValueError("development labels require physical cell_key and authoritative year")
    lab = labels[labels["year"].astype(int) <= contract.LABEL_OPEN_MAX_YEAR].copy()
    cells2 = cells.copy()
    if contract.available_col("predicted_final_sp_input") in cells2.columns:
        cells2 = cells2[cells2[contract.available_col("predicted_final_sp_input")].fillna(False)]
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


def chart_source_mapping(
    tables: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Machine-readable chart lineage with honest availability receipts."""
    definitions = [
            ("prob_dist_Q_BJ_CALIBRATED.png", "tables/probability_distribution_qbj_calibrated.csv", "Q_BJ_CALIBRATED"),
            ("eu_vs_bj_scatter.png", "tables/eu_vs_bj_scatter_table.csv", "Q_EU_BJLINE & Q_BJ_CALIBRATED"),
            ("power_vs_bj_scatter.png", "tables/power_vs_bj_scatter_table.csv", "P_POWER_BJLINE & Q_BJ_CALIBRATED"),
            ("direction_agreement.png", "tables/direction_agreement_matrix.csv", "causal divergence directions"),
            ("divergence_tail.png", "tables/divergence_magnitude_tail.csv", "causal divergence magnitude"),
            ("missingness_matrix.png", "tables/missingness_matrix.csv", "causal availability masks"),
            ("drift.png", "tables/drift_table.csv", "all probability representations"),
            ("intersection_coverage.png", "tables/intersection_coverage.csv", "causal support intersections"),
            ("development_only_calibration.png", "tables/development_only_calibration.csv", "all sources × outcomes × cohort"),
            ("predicted_sp_vs_settlement_sp.png", "tables/predicted_sp_vs_settlement_sp.csv", "causal predicted SP × development labels"),
    ]
    rows: list[dict[str, object]] = []
    for figure, source_table, scope in definitions:
        table_name = Path(source_table).stem
        source = None if tables is None else tables.get(table_name)
        if source is None:
            status = "UNASSESSED"
            reason = "SOURCE_TABLE_NOT_PROVIDED"
            row_count = -1
        else:
            row_count = len(source)
            unavailable_statuses = (
                source["status"].dropna().astype(str)
                if "status" in source.columns
                else pd.Series(dtype=str)
            )
            unavailable = source.empty or (
                not unavailable_statuses.empty
                and unavailable_statuses.str.startswith("UNAVAILABLE").all()
            )
            status = "UNAVAILABLE" if unavailable else "BOUND"
            reason = (
                "NO_CAUSAL_SUPPORT"
                if unavailable
                else "NOT_APPLICABLE"
            )
        rows.append(
            {
                "figure": figure,
                "source_table": source_table,
                "scope": scope,
                "status": status,
                "reason": reason,
                "row_count": row_count,
            }
        )
    return pd.DataFrame(rows)
