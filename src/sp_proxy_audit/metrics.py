"""Issue-equal coverage and strict-versus-proxy diagnostics for Issue #318."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from .grading import OUTCOMES, VECTOR_KEY

ACCEPTED_GRADES = {"STRICT_PRE_EVENT", "HISTORICAL_PROXY"}
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 3_182_026
ISSUE_OVERLAP_COLUMNS = [
    "source_id",
    "snapshot_kind",
    "partition",
    "issue_code",
    "fixture_count",
    "price_bias",
    "median_abs_log_price_error",
    "price_spearman",
    "top2_agreement",
    "top7_jaccard",
    "q_distortion",
    "abs_relative_q_distortion",
]
OVERLAP_SUMMARY_COLUMNS = [
    "proxy_source_id",
    "snapshot_kind",
    "partition",
    "issue_count",
    "fixture_count",
    *[
        f"{metric}_{suffix}"
        for metric in (
            "price_bias",
            "median_abs_log_price_error",
            "price_spearman",
            "top2_agreement",
            "top7_jaccard",
            "q_distortion",
            "abs_relative_q_distortion",
        )
        for suffix in ("issue_equal", "p025", "p50", "p975")
    ],
]


def partition_from_kickoff(values: pd.Series) -> pd.Series:
    year = pd.to_datetime(values, utc=True, errors="coerce").dt.year
    result = pd.Series("outside_contract", index=values.index, dtype="string")
    result.loc[year.between(2019, 2022)] = "development"
    result.loc[year.eq(2023)] = "validation"
    result.loc[year.eq(2024)] = "terminal"
    return result


def coverage_by_issue(cells: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "partition",
        "issue_code",
        "source_id",
        "source_grade",
        "snapshot_kind",
        "fixture_count",
        "vector_count",
        "cell_count",
        "feasible_n7",
    ]
    if cells.empty:
        return pd.DataFrame(columns=columns)
    work = cells.copy()
    work["partition"] = partition_from_kickoff(work["kickoff_utc"])
    keys = ["partition", "issue_code", "source_id", "source_grade", "snapshot_kind"]
    vector = (
        work.groupby([*keys, "match_idx"], dropna=False, sort=True)
        .agg(cell_rows=("outcome_code", "size"), outcomes=("outcome_code", "nunique"))
        .reset_index()
    )
    vector["is_triplet"] = vector["cell_rows"].eq(3) & vector["outcomes"].eq(3)
    summary = (
        vector.groupby(keys, dropna=False, sort=True)
        .agg(fixture_count=("match_idx", "nunique"), vector_count=("is_triplet", "sum"))
        .reset_index()
    )
    cells_count = (
        work.groupby(keys, dropna=False, sort=True)
        .size()
        .rename("cell_count")
        .reset_index()
    )
    summary = summary.merge(cells_count, on=keys, validate="one_to_one")
    summary["feasible_n7"] = summary["source_grade"].isin(ACCEPTED_GRADES) & summary[
        "vector_count"
    ].ge(7)
    return summary[columns]


def exclusion_ledger(cells: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in inventory.loc[inventory["availability"].ne("PRESENT")].itertuples(
        index=False
    ):
        rows.append(
            {
                "source_id": row.source_id,
                "snapshot_kind": "SOURCE",
                "exclusion_reason": row.availability,
                "cell_count": 0,
                "vector_count": 0,
                "issue_count": 0,
                "denominator_note": "frozen logical input",
            }
        )
    excluded = cells.loc[cells["exclusion_reason"].notna()].copy()
    if not excluded.empty:
        ledger_keys = ["source_id", "snapshot_kind", "exclusion_reason"]
        summary = (
            excluded.groupby(ledger_keys, dropna=False, sort=True)
            .agg(
                cell_count=("outcome_code", "size"),
                issue_count=("issue_code", "nunique"),
            )
            .reset_index()
        )
        vectors = (
            excluded.drop_duplicates([*VECTOR_KEY])
            .groupby(ledger_keys, dropna=False, sort=True)
            .size()
            .rename("vector_count")
            .reset_index()
        )
        summary = summary.merge(vectors, on=ledger_keys, validate="one_to_one")
        for record in summary.to_dict("records"):
            rows.append({**record, "denominator_note": "graded Mx3 cells"})
    columns = [
        "source_id",
        "snapshot_kind",
        "exclusion_reason",
        "cell_count",
        "vector_count",
        "issue_count",
        "denominator_note",
    ]
    return pd.DataFrame(rows, columns=columns)


def _spearman(proxy: pd.Series, strict: pd.Series) -> float:
    left = proxy.rank(method="average").to_numpy(dtype=float)
    right = strict.rank(method="average").to_numpy(dtype=float)
    if np.std(left) == 0 or np.std(right) == 0:
        return np.nan
    return float(np.corrcoef(left, right)[0, 1])


def _top_outcomes(frame: pd.DataFrame, column: str, count: int = 2) -> tuple[str, ...]:
    order = pd.Categorical(
        frame["outcome_code"], categories=list(OUTCOMES), ordered=True
    ).codes
    ranked = frame.assign(_outcome_order=order).sort_values(
        [column, "_outcome_order"], ascending=[False, True], kind="mergesort"
    )
    return tuple(ranked.head(count)["outcome_code"].astype(str))


def overlap_diagnostics(
    cells: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return cell, issue, and issue-equal horizon diagnostics."""
    proxy = cells.loc[cells["source_grade"].eq("HISTORICAL_PROXY")].copy()
    strict = cells.loc[cells["source_grade"].eq("STRICT_PRE_EVENT")].copy()
    join = ["issue_code", "match_idx", "outcome_code"]
    paired = proxy.merge(
        strict[
            join
            + [
                "sp_value",
                "kickoff_utc",
                "fixture_identity",
                "provenance_sha256",
            ]
        ].rename(
            columns={
                "sp_value": "strict_sp",
                "kickoff_utc": "strict_kickoff_utc",
                "fixture_identity": "strict_fixture_identity",
                "provenance_sha256": "strict_provenance_sha256",
            }
        ),
        on=join,
        how="inner",
        validate="many_to_one",
    )
    paired = paired.loc[
        paired["probability_value"].notna()
        & paired["sp_value"].gt(0)
        & paired["strict_sp"].gt(0)
    ].copy()
    if paired.empty:
        return (
            paired,
            pd.DataFrame(columns=ISSUE_OVERLAP_COLUMNS),
            pd.DataFrame(columns=OVERLAP_SUMMARY_COLUMNS),
        )
    paired["partition"] = partition_from_kickoff(paired["strict_kickoff_utc"])
    paired["proxy_sp"] = paired["sp_value"]
    paired["log_price_error"] = np.log(paired["proxy_sp"] / paired["strict_sp"])
    paired["abs_log_price_error"] = paired["log_price_error"].abs()
    paired["q_proxy"] = paired["probability_value"] * paired["proxy_sp"]
    paired["q_strict"] = paired["probability_value"] * paired["strict_sp"]
    paired["q_distortion"] = paired["q_proxy"] - paired["q_strict"]
    paired["abs_relative_q_distortion"] = (
        paired["q_distortion"].abs() / paired["q_strict"].abs()
    )

    fixture_rows: list[dict[str, object]] = []
    fixture_keys = [
        "source_id",
        "snapshot_kind",
        "partition",
        "issue_code",
        "match_idx",
    ]
    for key, frame in paired.groupby(fixture_keys, sort=True, observed=True):
        if len(frame) != 3 or frame["outcome_code"].nunique() != 3:
            continue
        proxy_top2 = _top_outcomes(frame, "q_proxy")
        strict_top2 = _top_outcomes(frame, "q_strict")
        fixture_rows.append(
            {
                **dict(zip(fixture_keys, key)),
                "price_bias": float(frame["log_price_error"].mean()),
                "median_abs_log_price_error": float(
                    frame["abs_log_price_error"].median()
                ),
                "price_spearman": _spearman(frame["proxy_sp"], frame["strict_sp"]),
                "top2_agreement": float(set(proxy_top2) == set(strict_top2)),
                "q_distortion": float(frame["q_distortion"].mean()),
                "abs_relative_q_distortion": float(
                    frame["abs_relative_q_distortion"].mean()
                ),
                "proxy_mean_top2_value": float(
                    frame.nlargest(2, "q_proxy")["q_proxy"].mean()
                ),
                "strict_mean_top2_value": float(
                    frame.nlargest(2, "q_strict")["q_strict"].mean()
                ),
            }
        )
    fixture = pd.DataFrame(fixture_rows)
    if fixture.empty:
        return paired, fixture, pd.DataFrame(columns=OVERLAP_SUMMARY_COLUMNS)

    issue_rows: list[dict[str, object]] = []
    issue_keys = ["source_id", "snapshot_kind", "partition", "issue_code"]
    for key, frame in fixture.groupby(issue_keys, sort=True, observed=True):
        proxy_top7 = set(
            frame.sort_values(
                ["proxy_mean_top2_value", "match_idx"],
                ascending=[False, True],
                kind="mergesort",
            ).head(7)["match_idx"]
        )
        strict_top7 = set(
            frame.sort_values(
                ["strict_mean_top2_value", "match_idx"],
                ascending=[False, True],
                kind="mergesort",
            ).head(7)["match_idx"]
        )
        union = proxy_top7 | strict_top7
        issue_rows.append(
            {
                **dict(zip(issue_keys, key)),
                "fixture_count": int(len(frame)),
                "price_bias": float(frame["price_bias"].mean()),
                "median_abs_log_price_error": float(
                    frame["median_abs_log_price_error"].median()
                ),
                "price_spearman": float(frame["price_spearman"].mean()),
                "top2_agreement": float(frame["top2_agreement"].mean()),
                "top7_jaccard": float(len(proxy_top7 & strict_top7) / len(union))
                if len(frame) >= 7 and union
                else np.nan,
                "q_distortion": float(frame["q_distortion"].mean()),
                "abs_relative_q_distortion": float(
                    frame["abs_relative_q_distortion"].mean()
                ),
            }
        )
    issue = pd.DataFrame(issue_rows, columns=ISSUE_OVERLAP_COLUMNS)
    return paired, issue, _summarize_issue_metrics(issue)


def _bootstrap_interval(
    values: np.ndarray,
    *,
    reducer: Callable[[np.ndarray], float],
    rng: np.random.Generator,
) -> tuple[float, float, float]:
    clean = values[np.isfinite(values)]
    if clean.size == 0:
        return np.nan, np.nan, np.nan
    draws = rng.choice(clean, size=(BOOTSTRAP_REPLICATES, clean.size), replace=True)
    estimates = np.apply_along_axis(reducer, 1, draws)
    return tuple(float(value) for value in np.quantile(estimates, [0.025, 0.5, 0.975]))


def _summarize_issue_metrics(issue: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    metrics: dict[str, Callable[[np.ndarray], float]] = {
        "price_bias": np.mean,
        "median_abs_log_price_error": np.median,
        "price_spearman": np.mean,
        "top2_agreement": np.mean,
        "top7_jaccard": np.mean,
        "q_distortion": np.mean,
        "abs_relative_q_distortion": np.mean,
    }
    keys = ["source_id", "snapshot_kind", "partition"]
    for group_number, (key, frame) in enumerate(
        issue.groupby(keys, sort=True, observed=True)
    ):
        row: dict[str, object] = {
            "proxy_source_id": key[0],
            "snapshot_kind": key[1],
            "partition": key[2],
            "issue_count": int(frame["issue_code"].nunique()),
            "fixture_count": int(frame["fixture_count"].sum()),
        }
        for metric, reducer in metrics.items():
            values = frame[metric].to_numpy(dtype=float)
            clean = values[np.isfinite(values)]
            row[f"{metric}_issue_equal"] = (
                float(reducer(clean)) if clean.size else np.nan
            )
            rng = np.random.default_rng(
                BOOTSTRAP_SEED + group_number * 101 + len(metric)
            )
            p025, p50, p975 = _bootstrap_interval(values, reducer=reducer, rng=rng)
            row[f"{metric}_p025"] = p025
            row[f"{metric}_p50"] = p50
            row[f"{metric}_p975"] = p975
        rows.append(row)
    return pd.DataFrame(rows, columns=OVERLAP_SUMMARY_COLUMNS)


def strict_partition_support(cells: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    strict = cells.loc[cells["source_grade"].eq("STRICT_PRE_EVENT")].copy()
    strict["partition"] = partition_from_kickoff(strict["kickoff_utc"])
    result: dict[str, dict[str, float | int]] = {}
    for partition in ("development", "validation", "terminal"):
        frame = strict.loc[strict["partition"].eq(partition)]
        per_issue = frame.groupby("issue_code")["fixture_identity"].nunique()
        result[partition] = {
            "issues": int(per_issue.size),
            "n7_issue_rate": float(per_issue.ge(7).mean()) if per_issue.size else 0.0,
            "accepted_vectors": int(frame["fixture_identity"].nunique()),
        }
    return result


def terminal_decision(
    cells: pd.DataFrame,
    overlap: pd.DataFrame,
    inventory: pd.DataFrame,
) -> dict[str, object]:
    strict_support = strict_partition_support(cells)
    strict_pass = all(
        values["issues"] >= 30 and values["n7_issue_rate"] >= 0.80
        for values in strict_support.values()
    )
    # Settlement and unstamped historical lanes are present specifically so
    # their inadmissibility is visible.  They must not poison the proxy-lane
    # promotion test merely by existing.  The zero-conflict threshold applies
    # to the two lanes that can support a scientific decision.
    decision_lanes = cells["source_id"].isin(
        ["eu_consensus_fair_odds_268", "strict_prospective_216"]
    )
    conflicts = int(
        (
            decision_lanes
            & cells["exclusion_reason"].isin(
                ["IDENTITY_MISMATCH", "POST_KICKOFF", "POST_DECISION"]
            )
        ).sum()
    )
    proxy_rows: list[dict[str, object]] = []
    if not overlap.empty:
        for row in overlap.itertuples(index=False):
            passed = (
                row.issue_count >= 20
                and row.fixture_count >= 500
                and row.price_spearman_issue_equal >= 0.75
                and row.top2_agreement_issue_equal >= 0.85
                and row.top7_jaccard_issue_equal >= 0.70
                and row.median_abs_log_price_error_issue_equal <= 0.15
                and conflicts == 0
            )
            proxy_rows.append(
                {
                    "proxy_source_id": row.proxy_source_id,
                    "snapshot_kind": row.snapshot_kind,
                    "partition": row.partition,
                    "passes": bool(passed),
                }
            )
    missing = inventory["availability"].ne("PRESENT")
    proxy_pass = any(row["passes"] for row in proxy_rows) and not missing.any()
    disposition = (
        "STRICT_HISTORY_AVAILABLE"
        if strict_pass and not missing.any()
        else "PROXY_USABLE_FOR_EXPLORATION"
        if proxy_pass
        else "NO_CAUSAL_PRICE_SUPPORT"
    )
    failed: list[str] = []
    if missing.any():
        failed.append("mandatory source missing or mismatched")
    if not strict_pass:
        failed.append("strict 2019-2024 partition thresholds not met")
    if not proxy_pass:
        failed.append("no strict-overlap proxy lane met all frozen thresholds")
    if conflicts:
        failed.append(f"{conflicts} leakage/time/identity-conflict cells")
    return {
        "terminal_disposition": disposition,
        "strict_partition_support": strict_support,
        "proxy_lane_decisions": proxy_rows,
        "conflict_cells": conflicts,
        "failed_thresholds": failed,
    }
