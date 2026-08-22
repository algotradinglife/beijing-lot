"""Physical per-seed action ledgers for Issue #306."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from issue209.dynamic_policy import (
    ActionSpec,
    OUTCOMES,
    OUTCOME_TO_INDEX,
    _derived_seed,
    generate_tickets,
    settle_ticket_arrays,
)
from issue209.models import build_match_units

N_VALUES = tuple(range(3, 11))
K_VALUES = (8, 32, 128, 512)
GENERATORS = ("TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR")
NUISANCE_SEEDS = (306001, 306002, 306003, 306004, 306005)
YEARS = (2019, 2020, 2021, 2022, 2023)


def action_space() -> tuple[ActionSpec, ...]:
    return tuple(
        ActionSpec(n=n, k=k, generator=generator)
        for n in N_VALUES
        for k in K_VALUES
        for generator in GENERATORS
    )


def build_seed_action_ledger(
    tensor: pd.DataFrame,
    probabilities: pd.DataFrame,
    values: pd.DataFrame,
    *,
    years: tuple[int, ...] = YEARS,
    seeds: tuple[int, ...] = NUISANCE_SEEDS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Settle every requested action separately for every physical seed."""

    if tensor["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")
    units = build_match_units(tensor)
    units = units[units["issue_year"].isin(years)]
    unit_h = units[units["snapshot_kind"].eq("10h")]
    winners = tensor[
        tensor["issue_year"].isin(years) & tensor["Y"].eq(1)
    ].drop_duplicates(["issue", "match_idx"])
    winner_lookup = {
        str(issue): group.set_index("match_idx")[["realized_outcome", "SP_SETTLE"]]
        for issue, group in winners.groupby("issue")
    }
    actions = action_space()
    rows: list[dict[str, object]] = []
    issue_rows: list[dict[str, object]] = []
    for issue, group in unit_h.groupby("issue", sort=True):
        issue_text = str(issue)
        index = group.index
        ev = values.reindex(index)[[f"ev_raw_{code}" for code in OUTCOMES]].to_numpy(float)
        probs = probabilities.reindex(index)[list(OUTCOMES)].to_numpy(float)
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
            if len(match_ids) < action.n:
                continue
            feasible += 1
            for nuisance_seed in seeds:
                ticket_matches, ticket_outcomes = generate_tickets(
                    ev,
                    probs,
                    action,
                    seed=_derived_seed(nuisance_seed, issue_text, action.key),
                )
                pnl, hit_rate = settle_ticket_arrays(
                    ticket_matches,
                    ticket_outcomes,
                    realized,
                    winning_sp,
                )
                effective_k = len(ticket_matches)
                stake = effective_k * 2.0
                rows.append(
                    {
                        "issue": issue_text,
                        "issue_year": int(group["issue_year"].iloc[0]),
                        "temporal_role": str(group["temporal_role"].iloc[0]),
                        "seed": nuisance_seed,
                        "action_key": action.key,
                        "n": action.n,
                        "k": action.k,
                        "generator": action.generator,
                        "effective_k": effective_k,
                        "stake_cny": stake,
                        "pnl_cny": pnl,
                        "gross_cny": pnl + stake,
                        "hit_count": int(round(hit_rate * effective_k)),
                        "hit_rate": hit_rate,
                    }
                )
        issue_rows.append(
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
    coverage = pd.DataFrame(issue_rows).sort_values(["issue_year", "issue"])
    if ledger.duplicated(["issue", "action_key", "seed"]).any():
        raise AssertionError("seed action ledger is not unique")
    if ledger["issue_year"].ge(2024).any():
        raise AssertionError("ledger opened a sealed year")
    return ledger.reset_index(drop=True), coverage.reset_index(drop=True)


def aggregate_action_labels(ledger: pd.DataFrame) -> pd.DataFrame:
    """Aggregate nuisance seeds for model targets without losing seed ledgers."""

    work = ledger.copy()
    work["roi"] = work["pnl_cny"] / work["stake_cny"].clip(lower=2.0)
    work["positive"] = work["pnl_cny"].gt(0).astype(float)
    work["tail_5x"] = work["gross_cny"].ge(5.0 * work["stake_cny"]).astype(float)
    work["downside_roi"] = (-work["roi"]).clip(lower=0.0)
    work["conditional_log_gross"] = np.where(
        work["gross_cny"].gt(0), np.log1p(work["gross_cny"]), np.nan
    )
    result = work.groupby(
        ["issue", "issue_year", "temporal_role", "action_key", "n", "k", "generator"],
        as_index=False,
    ).agg(
        effective_k=("effective_k", "min"),
        stake_cny=("stake_cny", "mean"),
        mean_pnl_cny=("pnl_cny", "mean"),
        mean_roi=("roi", "mean"),
        positive_probability=("positive", "mean"),
        tail_5x_probability=("tail_5x", "mean"),
        mean_downside_roi=("downside_roi", "mean"),
        conditional_log_gross=("conditional_log_gross", "mean"),
        mean_hit_rate=("hit_rate", "mean"),
        seed_pnl_std_cny=("pnl_cny", "std"),
    )
    result["conditional_log_gross"] = result["conditional_log_gross"].fillna(0.0)
    return result


def write_surface(
    tensor: pd.DataFrame,
    probabilities: pd.DataFrame,
    values: pd.DataFrame,
    output: str | Path,
    *,
    years: tuple[int, ...] = YEARS,
    finalize: bool = True,
) -> dict[str, object]:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    ledger_frames = []
    coverage_frames = []
    for year in years:
        ledger_path = output / f"seed_action_ledger_{year}.parquet"
        coverage_path = output / f"action_surface_coverage_{year}.csv"
        if ledger_path.exists() and coverage_path.exists():
            year_ledger = pd.read_parquet(ledger_path)
            year_coverage = pd.read_csv(coverage_path, dtype={"issue": str})
            if set(year_ledger["seed"].unique()) != set(NUISANCE_SEEDS):
                raise AssertionError(f"year {year} cached nuisance-seed drift")
            print(f"year={year} status=resume rows={len(year_ledger)}", flush=True)
        else:
            year_ledger, year_coverage = build_seed_action_ledger(
                tensor,
                probabilities,
                values,
                years=(year,),
            )
            temporary_ledger = ledger_path.with_suffix(".tmp.parquet")
            temporary_coverage = coverage_path.with_suffix(".tmp.csv")
            year_ledger.to_parquet(temporary_ledger, index=False)
            year_coverage.to_csv(temporary_coverage, index=False)
            temporary_ledger.replace(ledger_path)
            temporary_coverage.replace(coverage_path)
            print(
                f"year={year} status=complete issues={year_coverage.issue.nunique()} "
                f"rows={len(year_ledger)}",
                flush=True,
            )
        ledger_frames.append(year_ledger)
        coverage_frames.append(year_coverage)
    if not finalize:
        return {
            "issue": 306,
            "years": list(years),
            "status": "PARTIAL_YEAR_SURFACES_COMPLETE",
            "rows": int(sum(len(frame) for frame in ledger_frames)),
        }
    missing_years = [
        year for year in YEARS if not (output / f"seed_action_ledger_{year}.parquet").exists()
    ]
    if missing_years:
        raise FileNotFoundError(f"cannot finalize; missing year surfaces: {missing_years}")
    ledger_frames = [
        pd.read_parquet(output / f"seed_action_ledger_{year}.parquet") for year in YEARS
    ]
    coverage_frames = [
        pd.read_csv(output / f"action_surface_coverage_{year}.csv", dtype={"issue": str})
        for year in YEARS
    ]
    ledger = pd.concat(ledger_frames, ignore_index=True)
    coverage = pd.concat(coverage_frames, ignore_index=True)
    labels = aggregate_action_labels(ledger)
    ledger.to_parquet(output / "seed_action_ledger.parquet", index=False)
    labels.to_parquet(output / "action_labels.parquet", index=False)
    coverage.to_csv(output / "action_surface_coverage.csv", index=False)
    receipt = {
        "issue": 306,
        "years": list(YEARS),
        "sealed_years_opened": [],
        "n_values": list(N_VALUES),
        "k_values": list(K_VALUES),
        "generators": list(GENERATORS),
        "match_and_outcome_selection": "cell-value-weighted inside TOP/WR/WOR generators",
        "protection_surface": "NO_PROTECTION_ONLY",
        "unavailable_dimensions": [
            "explicit selector-family counterfactual ledger",
            "selective-protection counterfactual ledger on the same 512-ticket budget",
        ],
        "nuisance_seeds": list(NUISANCE_SEEDS),
        "issues": int(coverage["issue"].nunique()),
        "requested_actions": len(action_space()),
        "fully_supported_issues": int(coverage["missing_actions"].eq(0).sum()),
        "ledger_rows": int(len(ledger)),
        "independent_unit": "BEIJING_ISSUE",
        "payout_factor": 0.65,
        "payout_application": "once per winning N-fold ticket in upstream settlement",
    }
    (output / "surface_receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return receipt
