"""Physical development and evaluation surfaces for Issue #312."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from issue209.dynamic_policy import OUTCOMES, OUTCOME_TO_INDEX, _derived_seed, settle_ticket_arrays
from issue209.models import build_match_units

from .design import CubeAction
from .tickets import generate_cube_tickets

DEVELOPMENT_YEARS = (2019, 2020, 2021, 2022)
DEVELOPMENT_SEEDS = tuple(range(312001, 312012))
EVALUATION_SEEDS = tuple(range(312101, 312132))


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
