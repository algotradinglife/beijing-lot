"""Data-quality checks DQ-01..DQ-12 with stable exclusion reason codes.

Rework (2026-08-15):

- **DQ-02/DQ-03 use the exact match-level timestamps** from #203 identity
  (one row per (issue, match_idx)) instead of an issue-level broadcast.
- **DQ-12 scans every manifest payload** (inference cells, development
  labels, tables, notebook/report) for the 0.65 payout boundary — the audited
  check only scanned the inference namespace and therefore self-reported 0.
- **run_all_checks is fail-closed**: any check exception is raised (never
  degraded to a receipt row), so a broken check cannot masquerade as PASS.
- **DQ-10** implements the full contract: outliers (z-score), heavy tails
  (kurtosis), constant/near-constant fields and high redundancy
  (correlation), not just constant-field detection.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import contract
from . import probabilities as prob


def _is_vector(value: object) -> bool:
    return isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3


def _available_mask(cells: pd.DataFrame, representation: str) -> pd.Series:
    raw = cells.get(representation)
    if raw is None:
        return pd.Series(False, index=cells.index)
    return raw.apply(_is_vector)


# ---------------------------------------------------------------------------
# DQ-01 duplicate identities
# ---------------------------------------------------------------------------
def dq01_duplicate_identity(cells: pd.DataFrame) -> pd.DataFrame:
    """Detect duplicate issue/match/outcome identities."""
    key = cells[["issue", "match_idx", "outcome_code"]]
    duplicated = key.duplicated(keep=False)
    flagged = cells.loc[duplicated, ["issue", "match_idx", "outcome_code"]].copy()
    flagged["reason_code"] = contract.REASON_DUPLICATE_CELL_IDENTITY
    return flagged


# ---------------------------------------------------------------------------
# DQ-02 timestamps: missing / non-monotone / post-decision observations
# ---------------------------------------------------------------------------
def dq02_timestamp_checks(cells: pd.DataFrame) -> pd.DataFrame:
    """Flag missing or impossible decision-epoch/kickoff timestamps.

    A timestamp with year < 2000 is an encoding artifact (e.g. pandas
    Timestamp.min / Excel zero date), not a genuine kickoff; it is flagged
    separately from genuine post-decision rows (DQ-03).
    """
    rows = []
    for column in (contract.DECISION_EPOCH_COLUMN, contract.KICKOFF_COLUMN):
        if column not in cells.columns:
            continue
        raw = pd.to_datetime(cells[column], errors="coerce", utc=True)
        missing = raw.isna()
        impossible = raw.notna() & (raw.dt.year < 2000)
        for _, row in cells.loc[missing, ["issue", "match_idx"]].iterrows():
            rows.append(
                {
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "reason_code": contract.REASON_MISSING_TIMESTAMP,
                    "detail": column,
                }
            )
        for _, row in cells.loc[impossible, ["issue", "match_idx"]].iterrows():
            rows.append(
                {
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "reason_code": contract.REASON_MISSING_TIMESTAMP,
                    "detail": f"{column} impossible year < 2000",
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DQ-03 already-started/ineligible matches in a decision roster
# ---------------------------------------------------------------------------
def dq03_started_matches(cells: pd.DataFrame) -> pd.DataFrame:
    """Flag rows whose kickoff precedes the decision epoch (post-decision).

    Uses the exact match-level ``kickoff_ts_utc`` and ``feature_cutoff_ts_utc``
    joined by the builder at (issue, match_idx) granularity — the audited
    issue-level broadcast is gone.
    """
    rows = []
    if (
        contract.KICKOFF_COLUMN in cells.columns
        and contract.DECISION_EPOCH_COLUMN in cells.columns
    ):
        kickoff = pd.to_datetime(
            cells[contract.KICKOFF_COLUMN], errors="coerce", utc=True
        )
        cutoff = pd.to_datetime(
            cells[contract.DECISION_EPOCH_COLUMN], errors="coerce", utc=True
        )
        post = (kickoff.notna() & cutoff.notna() & (kickoff < cutoff)).fillna(False)
        for _, row in cells.loc[post, ["issue", "match_idx"]].iterrows():
            rows.append(
                {
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "reason_code": contract.REASON_POST_DECISION_OBSERVATION,
                    "detail": "kickoff before decision epoch",
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DQ-04 invalid handicap/result-code mappings
# ---------------------------------------------------------------------------
def dq04_invalid_handicap_result_mapping(cells: pd.DataFrame) -> pd.DataFrame:
    """Flag rows where the native line is missing, non-finite or not an
    integer/half-goal value."""
    rows = []
    if contract.BJ_LINE_BOUNDARY in cells.columns:
        line = pd.to_numeric(cells[contract.BJ_LINE_BOUNDARY], errors="coerce")
        missing = line.isna()
        invalid = ~missing & (~line.apply(prob.is_legal_handicap))
        for _, row in cells.loc[missing, ["issue", "match_idx"]].iterrows():
            rows.append(
                {
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "reason_code": contract.REASON_MISSING_NATIVE_LINE,
                    "detail": "native handicap line missing",
                }
            )
        for _, row in cells.loc[invalid, ["issue", "match_idx"]].iterrows():
            rows.append(
                {
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "reason_code": contract.REASON_INVALID_HANDICAP_RESULT_MAPPING,
                    "detail": f"line={row.get(contract.BJ_LINE_BOUNDARY)}",
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DQ-05 incomplete/non-normalized probability triplets
# ---------------------------------------------------------------------------
def dq05_invalid_probability_triplets(cells: pd.DataFrame) -> pd.DataFrame:
    """Flag any representation vector that is not a valid probability."""
    rows = []
    for representation in [
        contract.Q_BJ_SP_DEVIG,
        contract.Q_BJ_CALIBRATED,
        contract.Q_EU_RAW_1X2,
        contract.Q_EU_BJLINE,
        contract.P_POWER_BJLINE,
    ]:
        if representation not in cells.columns:
            continue
        raw = cells[representation]
        for index, value in raw.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple, np.ndarray)):
                try:
                    vector = np.asarray(value, dtype=np.float64)
                    ok, reason = prob.validate_probability_vector(vector)
                    if not ok:
                        rows.append(
                            {
                                "issue": cells.at[index, "issue"],
                                "match_idx": cells.at[index, "match_idx"],
                                "reason_code": contract.REASON_INVALID_PROBABILITY_TRIPLET,
                                "detail": f"{representation}:{reason}",
                            }
                        )
                except (ValueError, TypeError):
                    rows.append(
                        {
                            "issue": cells.at[index, "issue"],
                            "match_idx": cells.at[index, "match_idx"],
                            "reason_code": contract.REASON_INVALID_PROBABILITY_TRIPLET,
                            "detail": f"{representation}:unparsable",
                        }
                    )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DQ-06 impossible SP / probability / margin / uncertainty
# ---------------------------------------------------------------------------
def dq06_impossible_values(cells: pd.DataFrame) -> pd.DataFrame:
    """Flag impossible SP (<=1 or non-finite) in any SP-bearing column."""
    rows = []
    for column in ["final_sp", "predicted_final_sp_input"]:
        if column not in cells.columns:
            continue
        raw = pd.to_numeric(cells[column], errors="coerce")
        impossible = raw.notna() & ((raw <= 1.0) | ~np.isfinite(raw))
        for _, row in cells.loc[impossible, ["issue", "match_idx"]].iterrows():
            rows.append(
                {
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "reason_code": contract.REASON_IMPOSIBLE_SP,
                    "detail": f"{column}={cells.loc[_, column]}",
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DQ-07 source/provenance conflicts and silent fallback
# ---------------------------------------------------------------------------
def dq07_source_provenance_conflicts(cells: pd.DataFrame) -> pd.DataFrame:
    """Flag rows where both pclose and average-EU sources claim the cell."""
    rows = []
    if "source_is_pclose" in cells.columns and "source_is_average_eu" in cells.columns:
        both = cells["source_is_pclose"].fillna(0).astype(float) * cells[
            "source_is_average_eu"
        ].fillna(0).astype(float) > 0
        for _, row in cells.loc[both, ["issue", "match_idx"]].iterrows():
            rows.append(
                {
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "reason_code": contract.REASON_SOURCE_PROVENANCE_CONFLICT,
                    "detail": "source_is_pclose and source_is_average_eu both true",
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DQ-08 feature-label namespace overlap
# ---------------------------------------------------------------------------
def dq08_feature_label_overlap(cells: pd.DataFrame) -> pd.DataFrame:
    """Flag inference cells that carry a settlement/label column."""
    forbidden = [
        "result_code",
        "final_sp",
        "winning_zero_return_units",
        "payout_factor",
        "payout_after_65_units",
        "tax_rate",
        "tax_realized_yuan",
    ]
    present = [c for c in forbidden if c in cells.columns]
    rows = []
    for column in present:
        non_null = cells[column].notna()
        count = int(non_null.sum())
        if count:
            rows.append(
                {
                    "issue": None,
                    "match_idx": None,
                    "reason_code": contract.REASON_FEATURE_LABEL_OVERLAP,
                    "detail": f"inference namespace contains {column} with {count} non-null",
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DQ-09 year/league/line/source support drift
# ---------------------------------------------------------------------------
def dq09_support_drift(cells: pd.DataFrame) -> pd.DataFrame:
    """Table of per-year coverage so drift is observable (not an exclusion)."""
    if contract.BJ_LINE_BOUNDARY not in cells.columns:
        return pd.DataFrame()
    table = (
        cells.groupby("year")
        .agg(
            total_cells=("cell_key", "size"),
            calibrated_available=(
                contract.Q_BJ_CALIBRATED,
                lambda s: s.apply(
                    lambda v: (
                        v is not None
                        and isinstance(v, (list, tuple, np.ndarray))
                        and len(v) == 3
                    )
                ).sum(),
            ),
        )
        .reset_index()
    )
    table["calibrated_coverage"] = table["calibrated_available"] / table["total_cells"]
    return table


# ---------------------------------------------------------------------------
# DQ-10 outliers / heavy tails / constant fields / redundancy
# ---------------------------------------------------------------------------
def dq10_outlier_constant_fields(cells: pd.DataFrame) -> pd.DataFrame:
    """Report constant fields, outliers (|z|>5), heavy tails (|kurt|>15) and
    high-redundancy (|r|>0.99) numeric fields."""
    rows = []
    numeric = cells.select_dtypes(include=[np.number])
    for column in numeric.columns:
        values = numeric[column].dropna()
        if len(values) == 0:
            continue
        unique = values.nunique()
        if unique <= 1:
            rows.append(
                {
                    "field": column,
                    "reason_code": contract.REASON_CONSTANT_NEAR_CONSTANT,
                    "detail": f"constant field ({unique} unique value)",
                }
            )
            continue
        if values.std(ddof=0) <= 0:
            continue
        z = (values - values.mean()) / values.std(ddof=0)
        outlier_count = int((z.abs() > 5).sum())
        kurtosis = float(values.kurt())
        heavy_tail = kurtosis > 15
        if outlier_count or heavy_tail:
            rows.append(
                {
                    "field": column,
                    "reason_code": contract.REASON_OUTLIER_REFERENCE,
                    "detail": (
                        f"outliers(|z|>5)={outlier_count} kurtosis={kurtosis:.2f} "
                        f"heavy_tail={heavy_tail}"
                    ),
                }
            )
    # high-redundancy: pairwise |corr| > 0.99 among numeric columns
    corr_columns = [c for c in numeric.columns if numeric[c].nunique() > 1]
    if len(corr_columns) > 1:
        corr = numeric[corr_columns].corr()
        for i, col_a in enumerate(corr_columns):
            for col_b in corr_columns[i + 1:]:
                r = corr.loc[col_a, col_b]
                if pd.notna(r) and abs(float(r)) > 0.99:
                    rows.append(
                        {
                            "field": f"{col_a}~{col_b}",
                            "reason_code": contract.REASON_OUTLIER_REFERENCE,
                            "detail": f"high redundancy |r|={float(r):.4f}",
                        }
                    )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# DQ-11 matched-support loss when requiring BJ+EU+POWER simultaneously
# ---------------------------------------------------------------------------
def dq11_matched_support_loss(cells: pd.DataFrame) -> pd.DataFrame:
    """Census of cells available under each source intersection."""
    qbj = _available_mask(cells, contract.Q_BJ_CALIBRATED)
    eu = _available_mask(cells, contract.Q_EU_BJLINE)
    power = _available_mask(cells, contract.P_POWER_BJLINE)
    sp = _available_mask(cells, contract.Q_BJ_SP_DEVIG)
    table = pd.DataFrame(
        {
            "subset": [
                "Q_BJ_CALIBRATED only",
                "Q_BJ + EU_BJLINE",
                "Q_BJ + POWER",
                "Q_BJ + EU + POWER",
                "Q_BJ + SP_DEVIG",
                "Q_BJ + EU + POWER + SP_DEVIG",
            ],
            "cell_count": [
                int(qbj.sum()),
                int((qbj & eu).sum()),
                int((qbj & power).sum()),
                int((qbj & eu & power).sum()),
                int((qbj & sp).sum()),
                int((qbj & eu & power & sp).sum()),
            ],
        }
    )
    table["fraction_of_total"] = table["cell_count"] / len(cells)
    return table


# ---------------------------------------------------------------------------
# DQ-12 payout-factor boundary: 0.65 at cell/per-leg level, 0.65^N
# ---------------------------------------------------------------------------
_PAYOUT_NAME_TOKENS = (
    "payout",
    "winning_zero_return",
    "settlement",
    "tax_",
    "65",
    "0_65",
    "0.65",
)


def _scan_payout_named_column(rows: list[dict[str, object]], column: str,
                              raw: pd.Series) -> None:
    """Flag a payout-named column and any 0.65^N construction value."""
    rows.append(
        {
            "field": column,
            "reason_code": contract.REASON_PAYOUT_FACTOR_AT_CELL_LEVEL,
            "detail": "payout/settlement-named column present in payload",
        }
    )
    values: list[float] = []
    if raw.dtype == object:
        for value in raw:
            if isinstance(value, (list, tuple, np.ndarray)):
                try:
                    values.extend(np.asarray(value, dtype=np.float64).ravel().tolist())
                except (ValueError, TypeError):
                    continue
    else:
        numeric = pd.to_numeric(raw, errors="coerce").dropna()
        if not numeric.empty:
            values = numeric.to_numpy(dtype=np.float64).tolist()
    if values:
        _flag_payout_power_values(rows, column, np.asarray(values, dtype=np.float64))


def _flag_payout_power_values(
    rows: list[dict[str, object]], column: str, values: np.ndarray
) -> None:
    """Flag values equal to 0.65^N for N>=1 (a construction, not a probability)."""
    for n in range(1, 10):
        target = contract.PAYOUT_FACTOR_BJ ** n
        if np.any(np.isclose(values, target, atol=1e-9)):
            rows.append(
                {
                    "field": column,
                    "reason_code": contract.REASON_0_65_N_CONSTRUCTION,
                    "detail": f"value equals 0.65^{n} construction",
                }
            )
            return


def dq12_payout_factor_boundary(cells: pd.DataFrame) -> pd.DataFrame:
    """Assert the payout-factor coefficient is absent from every payload.

    The inference namespace must carry no payout/0.65-named column and no
    0.65^N value.  This check runs on the assembled cell frame AND on the
    development-label payload (the audited version only scanned inference
    cells and therefore reported 0 while the label payload carried 243,462
    rows of payout_factor=0.65).
    """
    rows = []
    for column in cells.columns:
        lowered = column.lower()
        payout_typed = any(token in lowered for token in _PAYOUT_NAME_TOKENS)
        if payout_typed:
            _scan_payout_named_column(rows, column, cells[column])
    return pd.DataFrame(rows)


def dq12_payout_boundary_payload(payload: pd.DataFrame, payload_name: str) -> pd.DataFrame:
    """DQ-12 variant for a non-cell payload (dev labels, tables, report)."""
    rows = []
    for column in payload.columns:
        lowered = column.lower()
        payout_typed = any(token in lowered for token in _PAYOUT_NAME_TOKENS)
        if payout_typed:
            _scan_payout_named_column(rows, f"{payload_name}.{column}",
                                      payload[column])
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Causal eligibility (REQ-D01): per-feature observed_at <= decision epoch
# ---------------------------------------------------------------------------
def causal_eligibility(cells: pd.DataFrame) -> pd.DataFrame:
    """Per-representation availability mask with reasons.

    Returns a one-row-per-cell frame with boolean ``available`` and
    ``unavailable_reason`` for each representation, computed from the
    per-feature observed_at columns vs the decision epoch.  Post-decision
    matches are excluded everywhere (REQ-D01 fail closed).
    """
    rows = []
    representations = [
        contract.Q_BJ_SP_DEVIG,
        contract.Q_BJ_CALIBRATED,
        contract.Q_EU_RAW_1X2,
        contract.Q_EU_BJLINE,
        contract.P_POWER_BJLINE,
    ]
    epoch = pd.to_datetime(
        cells.get(contract.DECISION_EPOCH_COLUMN), errors="coerce", utc=True
    )
    kickoff = pd.to_datetime(
        cells.get(contract.KICKOFF_COLUMN), errors="coerce", utc=True
    )
    post_decision = (
        kickoff.notna() & epoch.notna() & (kickoff < epoch)
    ).fillna(False)

    output_rows: list[dict[str, object]] = []
    for representation in representations:
        observed_col = cells.get(contract.observed_at_col(representation))
        observed = (
            pd.to_datetime(observed_col, errors="coerce", utc=True)
            if observed_col is not None
            else pd.Series(pd.NaT, index=cells.index)
        )
        present = _available_mask(cells, representation).to_numpy()
        post_arr = post_decision.to_numpy()
        epoch_arr = epoch.to_numpy()
        observed_arr = observed.to_numpy()
        for i in range(len(cells)):
            if bool(post_arr[i]):
                reason = contract.REASON_POST_DECISION_OBSERVATION
                available = False
            elif not bool(present[i]):
                reason = None
                available = False
            elif pd.isna(observed_arr[i]) or pd.isna(epoch_arr[i]):
                reason = contract.REASON_NO_CAUSAL_EPOCH
                available = False
            elif observed_arr[i] > epoch_arr[i]:
                reason = contract.REASON_OBSERVED_AFTER_EPOCH
                available = False
            else:
                reason = None
                available = True
            output_rows.append(
                {
                    "representation": representation,
                    "available": available,
                    "unavailable_reason": reason,
                }
            )
    return pd.DataFrame(output_rows)


def run_all_checks(cells: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Run DQ-01..DQ-12.  Fail closed: a check exception raises."""
    checks = {
        "DQ01_duplicate_identity": dq01_duplicate_identity,
        "DQ02_timestamp_checks": dq02_timestamp_checks,
        "DQ03_started_matches": dq03_started_matches,
        "DQ04_invalid_handicap_result_mapping": dq04_invalid_handicap_result_mapping,
        "DQ05_invalid_probability_triplets": dq05_invalid_probability_triplets,
        "DQ06_impossible_values": dq06_impossible_values,
        "DQ07_source_provenance_conflicts": dq07_source_provenance_conflicts,
        "DQ08_feature_label_overlap": dq08_feature_label_overlap,
        "DQ09_support_drift": dq09_support_drift,
        "DQ10_outlier_constant_fields": dq10_outlier_constant_fields,
        "DQ11_matched_support_loss": dq11_matched_support_loss,
        "DQ12_payout_factor_boundary": dq12_payout_factor_boundary,
    }
    results: dict[str, pd.DataFrame] = {}
    for name, check in checks.items():
        results[name] = check(cells)  # exceptions propagate (fail closed)
    return results
