"""Physical development and evaluation surfaces for Issue #312."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from issue209.contract import INFERENCE_VIEW, LABELS_PRE2024, LABELS_SQLITE
from issue209.dynamic_policy import OUTCOMES, OUTCOME_TO_INDEX, _derived_seed, settle_ticket_arrays
from issue209.models import build_match_units

from .design import CubeAction
from .tickets import generate_cube_tickets

DEVELOPMENT_YEARS = (2019, 2020, 2021, 2022)
DEVELOPMENT_SEEDS = tuple(range(312001, 312012))
EVALUATION_SEEDS = tuple(range(312101, 312132))


def _read_tensor_through_year(max_year: int) -> pd.DataFrame:
    """Load labels only through ``max_year`` and query SP for those issues.

    PyArrow applies the year predicate before materializing either Parquet file.
    The SQLite query is restricted to the issue identifiers exposed by that
    filtered label projection.  This prevents the development runner from
    opening 2023 settlement labels and filtering them only afterwards.
    """

    if max_year >= 2024:
        raise AssertionError("2024+ settlement labels are sealed")
    view = pq.read_table(
        INFERENCE_VIEW,
        filters=[("issue_year", "<=", max_year)],
    ).to_pandas()
    labels = pq.read_table(
        LABELS_PRE2024,
        filters=[("issue_year", "<=", max_year)],
    ).to_pandas()
    if view.empty or labels.empty:
        raise AssertionError(f"no causal rows available through {max_year}")
    if pd.to_numeric(view["issue_year"], errors="raise").max() > max_year:
        raise AssertionError("inference predicate was not enforced")
    if pd.to_numeric(labels["issue_year"], errors="raise").max() > max_year:
        raise AssertionError("label predicate was not enforced")

    view["issue_code"] = view["issue_code"].astype(str)
    view["outcome_code"] = view["outcome_code"].astype(str)
    labels["issue_code"] = labels["issue_code"].astype(str)
    issue_ids = sorted(labels["issue_code"].dropna().unique().tolist())
    placeholders = ",".join("?" for _ in issue_ids)
    database = Path(LABELS_SQLITE).resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        sp = pd.read_sql_query(
            f"""
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   winning_sp, result_code
            FROM match_features
            WHERE CAST(issue AS TEXT) IN ({placeholders})
            """,
            connection,
            params=issue_ids,
        )
    sp["issue"] = sp["issue"].astype(str)
    if not set(sp["issue"]).issubset(set(issue_ids)):
        raise AssertionError("SQLite issue predicate was not enforced")

    lab = labels[["issue_code", "match_idx", "target_outcome"]].rename(
        columns={"issue_code": "issue", "target_outcome": "realized_outcome"}
    )
    spk = sp.dropna(subset=["issue", "match_idx"]).drop_duplicates(
        ["issue", "match_idx"], keep="first"
    )
    merged = view.merge(
        lab,
        left_on=["issue_code", "match_idx"],
        right_on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    merged["has_label"] = merged["realized_outcome"].notna().astype(int)
    merged["Y"] = 0
    labeled = merged["has_label"].eq(1)
    merged.loc[labeled, "Y"] = (
        merged.loc[labeled, "outcome_code"]
        == merged.loc[labeled, "realized_outcome"]
    ).astype(int)
    merged = merged.merge(
        spk[["issue", "match_idx", "winning_sp", "result_code"]],
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    merged["SP_SETTLE"] = np.where(
        merged["Y"].eq(1), merged["winning_sp"], np.nan
    )
    merged["SP_AVAILABLE"] = merged["SP_SETTLE"].notna().astype(int)
    merged["R_RAW"] = merged["Y"] * merged["SP_SETTLE"].fillna(0.0)
    tensor = merged[merged["has_label"].eq(1)].copy()
    if tensor.columns.duplicated().any():
        tensor = tensor.loc[:, ~tensor.columns.duplicated()].copy()
    tensor["issue"] = tensor["issue"].combine_first(tensor["issue_code"])
    tensor = tensor.drop(columns=["issue_code"])
    if pd.to_numeric(tensor["issue_year"], errors="raise").max() > max_year:
        raise AssertionError("settlement boundary drifted after joins")
    return tensor.reset_index(drop=True)


def load_causal_issue209_inputs(
    probabilities_path: str | Path,
    values_path: str | Path,
    *,
    years: tuple[int, ...],
    issues: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Load a causal tensor and its position-aligned frozen #209 outputs.

    The #209 outputs predate an explicit unit-key column.  We reconstruct their
    complete unit-key index from pre-event inference rows plus the label table's
    identity columns only.  PyArrow never materializes ``target_outcome`` for a
    future year; realized outcomes are loaded separately only through the
    requested year boundary.
    """

    if not years:
        raise ValueError("at least one year is required")
    max_year = max(years)
    tensor_prefix = _read_tensor_through_year(max_year)
    probabilities_all = pd.read_parquet(probabilities_path).reset_index(drop=True)
    values_all = pd.read_parquet(values_path).reset_index(drop=True)
    if len(probabilities_all) != len(values_all):
        raise AssertionError("#209 probability/value row counts differ")
    feature_identity = pq.read_table(
        INFERENCE_VIEW,
        filters=[("issue_year", "<", 2024)],
        columns=["issue_code", "match_idx", "snapshot_kind", "issue_year"],
    ).to_pandas()
    label_identity = pq.read_table(
        LABELS_PRE2024,
        columns=["issue_code", "match_idx"],
    ).to_pandas()
    feature_identity["issue_code"] = feature_identity["issue_code"].astype(str)
    label_identity["issue_code"] = label_identity["issue_code"].astype(str)
    label_identity = label_identity.drop_duplicates(["issue_code", "match_idx"])
    output_index = feature_identity.merge(
        label_identity,
        on=["issue_code", "match_idx"],
        how="inner",
        validate="many_to_one",
    )
    output_index = (
        output_index.rename(columns={"issue_code": "issue"})
        .groupby(["issue", "match_idx", "snapshot_kind"], as_index=False)
        .agg(issue_year=("issue_year", "first"))
    )
    if len(output_index) != len(probabilities_all):
        raise AssertionError("reconstructed #209 output identity row count drifted")

    target = output_index["issue_year"].isin(years)
    if issues is not None:
        target &= output_index["issue"].astype(str).isin(issues)
    probabilities = probabilities_all.loc[target].reset_index(drop=True)
    values = values_all.loc[target].reset_index(drop=True)
    tensor = tensor_prefix[
        tensor_prefix["issue_year"].isin(years)
        & (
            tensor_prefix["issue"].astype(str).isin(issues)
            if issues is not None
            else True
        )
    ].reset_index(drop=True)
    target_units = build_match_units(tensor).reset_index(drop=True)
    keys = ["issue", "match_idx", "snapshot_kind"]
    expected_keys = output_index.loc[target, keys].reset_index(drop=True)
    if not target_units[keys].equals(expected_keys):
        raise AssertionError("causal tensor and #209 output keys are misaligned")
    if not (len(target_units) == len(probabilities) == len(values)):
        raise AssertionError("causal model input row counts differ")
    receipt = {
        "requested_years": list(years),
        "label_max_year_opened": max_year,
        "label_predicate": f"issue_year <= {max_year}",
        "sqlite_issue_count": int(tensor_prefix["issue"].nunique()),
        "target_issue_count": int(target_units["issue"].nunique()),
        "target_unit_count": int(len(target_units)),
        "future_outcome_label_rows_opened": 0,
        "future_label_identity_columns_opened": ["issue_code", "match_idx"],
        "future_outcome_columns_opened": [],
        "output_alignment": "FEATURE_PLUS_IDENTITY_INDEX_VERIFIED",
    }
    return tensor, probabilities, values, receipt


def build_seed_action_ledger(
    tensor: pd.DataFrame,
    probabilities: pd.DataFrame,
    values: pd.DataFrame,
    actions: tuple[CubeAction, ...],
    *,
    years: tuple[int, ...],
    seeds: tuple[int, ...],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Settle explicit actions for each issue and physical ticket seed."""

    if any(year >= 2024 for year in years):
        raise AssertionError("2024+ is sealed")
    units = build_match_units(tensor)
    unit_h = units[
        units["issue_year"].isin(years) & units["snapshot_kind"].eq("10h")
    ]
    winners = tensor[
        tensor["issue_year"].isin(years) & tensor["Y"].eq(1)
    ].drop_duplicates(["issue", "match_idx"])
    winner_lookup = {
        str(issue): group.set_index("match_idx")[["realized_outcome", "SP_SETTLE"]]
        for issue, group in winners.groupby("issue")
    }
    rows: list[dict[str, object]] = []
    availability_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    for issue, group in unit_h.groupby("issue", sort=True):
        issue_text = str(issue)
        index = group.index
        ev = values.reindex(index)[
            [f"ev_raw_{code}" for code in OUTCOMES]
        ].to_numpy(float)
        probs = probabilities.reindex(index)[list(OUTCOMES)].to_numpy(float)
        divergence = group[
            [f"eu_vs_line_divergence_{code}" for code in OUTCOMES]
        ].to_numpy(float)
        match_ids = group["match_idx"].to_numpy(int)
        settlement = winner_lookup.get(issue_text)
        if settlement is None:
            continue
        realized = np.array(
            [
                OUTCOME_TO_INDEX.get(str(settlement["realized_outcome"].get(match)), -1)
                for match in match_ids
            ],
            dtype=int,
        )
        winning_sp = np.array(
            [float(settlement["SP_SETTLE"].get(match, np.nan)) for match in match_ids],
            dtype=float,
        )
        feasible = 0
        for action in actions:
            reason = "AVAILABLE"
            if len(match_ids) < action.n:
                reason = "INSUFFICIENT_MATCHES"
                seed_payloads: list[tuple[int, np.ndarray, np.ndarray, int]] = []
            else:
                seed_payloads = []
                for nuisance_seed in seeds:
                    ticket_matches, ticket_outcomes, protected = generate_cube_tickets(
                        ev,
                        probs,
                        divergence,
                        action,
                        seed=_derived_seed(nuisance_seed, issue_text, action.key),
                    )
                    if len(ticket_matches) != action.k:
                        reason = "INSUFFICIENT_DISTINCT_TICKETS"
                        seed_payloads = []
                        break
                    seed_payloads.append(
                        (nuisance_seed, ticket_matches, ticket_outcomes, protected)
                    )
            availability_rows.append(
                {
                    "issue": issue_text,
                    "issue_year": int(group["issue_year"].iloc[0]),
                    "action_key": action.key,
                    "status": reason,
                }
            )
            if reason != "AVAILABLE":
                continue
            feasible += 1
            for nuisance_seed, ticket_matches, ticket_outcomes, protected in seed_payloads:
                pnl, hit_rate = settle_ticket_arrays(
                    ticket_matches,
                    ticket_outcomes,
                    realized,
                    winning_sp,
                )
                stake = action.k * 2.0
                rows.append(
                    {
                        "issue": issue_text,
                        "issue_year": int(group["issue_year"].iloc[0]),
                        "temporal_role": str(group["temporal_role"].iloc[0]),
                        "seed": nuisance_seed,
                        "action_key": action.key,
                        **asdict(action),
                        "effective_k": action.k,
                        "stake_cny": stake,
                        "pnl_cny": pnl,
                        "gross_cny": pnl + stake,
                        "hit_count": int(round(hit_rate * action.k)),
                        "hit_rate": hit_rate,
                        "protected_tickets": protected,
                        "protected_fraction": protected / action.k,
                    }
                )
        coverage_rows.append(
            {
                "issue": issue_text,
                "issue_year": int(group["issue_year"].iloc[0]),
                "n_matches": int(len(match_ids)),
                "requested_actions": len(actions),
                "feasible_actions": feasible,
                "missing_actions": len(actions) - feasible,
                "seed_count": len(seeds),
            }
        )
    ledger = pd.DataFrame(rows).sort_values(
        ["issue_year", "issue", "action_key", "seed"]
    )
    availability = pd.DataFrame(availability_rows).sort_values(
        ["issue_year", "issue", "action_key"]
    )
    coverage = pd.DataFrame(coverage_rows).sort_values(["issue_year", "issue"])
    if ledger.duplicated(["issue", "action_key", "seed"]).any():
        raise AssertionError("physical seed ledger is not unique")
    return (
        ledger.reset_index(drop=True),
        availability.reset_index(drop=True),
        coverage.reset_index(drop=True),
    )


def aggregate_action_labels(ledger: pd.DataFrame) -> pd.DataFrame:
    """Aggregate physical seeds while preserving issue as the unit."""

    work = ledger.copy()
    work["roi"] = work["pnl_cny"] / work["stake_cny"]
    work["positive"] = work["pnl_cny"].gt(0).astype(float)
    work["tail_2x"] = work["gross_cny"].ge(2 * work["stake_cny"]).astype(float)
    work["tail_5x"] = work["gross_cny"].ge(5 * work["stake_cny"]).astype(float)
    work["tail_10x"] = work["gross_cny"].ge(10 * work["stake_cny"]).astype(float)
    work["downside_roi"] = (-work["roi"]).clip(lower=0.0)
    work["conditional_log_gross"] = np.where(
        work["gross_cny"].gt(0), np.log1p(work["gross_cny"]), np.nan
    )
    keys = [
        "issue",
        "issue_year",
        "temporal_role",
        "action_key",
        "n",
        "k",
        "match_selector",
        "pool_excess",
        "outcome_direction",
        "generator",
        "protection",
    ]
    result = work.groupby(keys, as_index=False).agg(
        effective_k=("effective_k", "min"),
        stake_cny=("stake_cny", "mean"),
        mean_pnl_cny=("pnl_cny", "mean"),
        mean_roi=("roi", "mean"),
        positive_probability=("positive", "mean"),
        tail_2x_probability=("tail_2x", "mean"),
        tail_5x_probability=("tail_5x", "mean"),
        tail_10x_probability=("tail_10x", "mean"),
        mean_downside_roi=("downside_roi", "mean"),
        conditional_log_gross=("conditional_log_gross", "mean"),
        mean_hit_rate=("hit_rate", "mean"),
        mean_protected_fraction=("protected_fraction", "mean"),
        seed_pnl_std_cny=("pnl_cny", "std"),
    )
    result["conditional_log_gross"] = result["conditional_log_gross"].fillna(0.0)
    return result


def write_year_surface(
    tensor: pd.DataFrame,
    probabilities: pd.DataFrame,
    values: pd.DataFrame,
    actions: tuple[CubeAction, ...],
    output: str | Path,
    *,
    year: int,
    seeds: tuple[int, ...],
    prefix: str,
) -> dict[str, object]:
    """Write one restartable year surface atomically."""

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    ledger_path = output / f"{prefix}_seed_action_ledger_{year}.parquet"
    availability_path = output / f"{prefix}_action_availability_{year}.csv"
    coverage_path = output / f"{prefix}_coverage_{year}.csv"
    if ledger_path.exists() and availability_path.exists() and coverage_path.exists():
        ledger = pd.read_parquet(ledger_path)
        if set(ledger["seed"].unique()) != set(seeds):
            raise AssertionError(f"cached {year} physical seeds drifted")
        return {"year": year, "status": "RESUMED", "rows": int(len(ledger))}
    ledger, availability, coverage = build_seed_action_ledger(
        tensor,
        probabilities,
        values,
        actions,
        years=(year,),
        seeds=seeds,
    )
    temporary_ledger = ledger_path.with_suffix(".tmp.parquet")
    temporary_availability = availability_path.with_suffix(".tmp.csv")
    temporary_coverage = coverage_path.with_suffix(".tmp.csv")
    ledger.to_parquet(temporary_ledger, index=False)
    availability.to_csv(temporary_availability, index=False)
    coverage.to_csv(temporary_coverage, index=False)
    temporary_ledger.replace(ledger_path)
    temporary_availability.replace(availability_path)
    temporary_coverage.replace(coverage_path)
    return {
        "year": year,
        "status": "COMPLETE",
        "rows": int(len(ledger)),
        "issues": int(coverage["issue"].nunique()),
        "minimum_feasible_actions": int(coverage["feasible_actions"].min()),
    }
