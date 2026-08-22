"""Exposure-matched Top-2 ticket construction and settlement."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .contract import (
    DISTINCT_TICKETS,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    STAKE_PER_UNIT,
)

OUTCOME_ORDER = {outcome: index for index, outcome in enumerate(OUTCOMES)}


def build_and_settle(
    labelled_cells: pd.DataFrame,
    predictions: pd.DataFrame,
    *,
    arms: tuple[str, ...],
    include_tickets: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build policies for one or more model/seed prediction surfaces."""

    cell_groups = {
        str(issue): group.copy()
        for issue, group in labelled_cells.groupby("issue", sort=True)
    }
    ticket_frames: list[pd.DataFrame] = []
    bundle_rows: list[dict[str, object]] = []
    for (model, seed, issue), predicted in predictions.groupby(
        ["model", "seed", "issue"], sort=True
    ):
        cells = cell_groups[str(issue)]
        base = _match_table(cells, predicted)
        if len(base) < N_LEGS:
            continue
        for arm in arms:
            tickets, bundle = _one_arm(
                base, str(model), int(seed), arm, include_tickets=include_tickets
            )
            if include_tickets:
                ticket_frames.append(tickets)
            bundle_rows.append(bundle)
    tickets = pd.concat(ticket_frames, ignore_index=True) if ticket_frames else pd.DataFrame()
    bundles = pd.DataFrame(bundle_rows)
    return tickets, bundles


def baseline_prediction_surface(cells: pd.DataFrame) -> pd.DataFrame:
    result = cells[
        ["issue", "issue_year", "issue_anchor_ts", "match_idx", "outcome", "q_eu", "q_line", "market_value_anchor"]
    ].copy()
    result["model"] = "BASELINE"
    result["seed"] = -1
    result["predicted_probability"] = result["q_eu"]
    result["predicted_value"] = result["market_value_anchor"]
    result["probability_residual"] = 0.0
    result["value_residual"] = 0.0
    return result


def anchor_shrinkage_surface(
    cells: pd.DataFrame,
    alphas: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0),
) -> pd.DataFrame:
    """Interpretable bridge from q_eu/q_line value anchor to equal Top-2 funding."""

    frames: list[pd.DataFrame] = []
    for alpha in alphas:
        frame = baseline_prediction_surface(cells)
        frame["model"] = f"ANCHOR_SHRINK_A{int(round(alpha * 100)):03d}"
        frame["predicted_value"] = (
            (1.0 - alpha) * frame["market_value_anchor"] + alpha
        ).clip(lower=1e-6)
        frame["value_residual"] = frame["predicted_value"] - frame["market_value_anchor"]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _match_table(cells: pd.DataFrame, predicted: pd.DataFrame) -> pd.DataFrame:
    merged = cells.merge(
        predicted[["match_idx", "outcome", "predicted_probability", "predicted_value"]],
        on=["match_idx", "outcome"], validate="one_to_one",
    )
    merged["outcome_order"] = merged["outcome"].map(OUTCOME_ORDER)
    merged = merged.sort_values(["match_idx", "outcome_order"], kind="stable")
    if len(merged) % 3 or merged.groupby("match_idx")["outcome"].nunique().ne(3).any():
        raise AssertionError("prediction surface lacks a complete M×3 match")
    representatives = merged.iloc[::3].reset_index(drop=True)
    q = merged["q_eu"].to_numpy(float).reshape(-1, 3)
    probability = merged["predicted_probability"].to_numpy(float).reshape(-1, 3)
    value = merged["predicted_value"].to_numpy(float).reshape(-1, 3)
    market_order = np.argsort(-q, axis=1, kind="stable")
    outcome_tie = np.broadcast_to(np.arange(3), value.shape)
    learned_order = np.lexsort((outcome_tie, -probability, -value), axis=1)
    outcome_array = np.asarray(OUTCOMES)
    return pd.DataFrame(
        {
            "issue": representatives["issue"].astype(str).to_numpy(),
            "issue_year": representatives["issue_year"].astype(int).to_numpy(),
            "issue_anchor_ts": representatives["issue_anchor_ts"].to_numpy(),
            "match_idx": representatives["match_idx"].astype(int).to_numpy(),
            "market_support": [tuple(outcome_array[index[:2]]) for index in market_order],
            "learned_support": [tuple(outcome_array[index[:2]]) for index in learned_order],
            "market_selection_score": np.take_along_axis(q, market_order[:, :2], axis=1).sum(axis=1),
            "learned_selection_score": np.take_along_axis(value, learned_order[:, :2], axis=1).sum(axis=1),
            "predicted_values": [tuple(row) for row in value],
            "result_code": representatives["result_code"].astype(str).to_numpy(),
            "winning_sp": pd.to_numeric(representatives["winning_sp"], errors="coerce").to_numpy(float),
            "settlement_available": representatives["settlement_available"].astype(bool).to_numpy(),
        }
    )


def _one_arm(
    matches: pd.DataFrame,
    model: str,
    seed: int,
    arm: str,
    *,
    include_tickets: bool,
) -> tuple[pd.DataFrame, dict[str, object]]:
    learned_selection = arm in {"S1O0", "S1O1"}
    learned_support = arm in {"S0O1", "S1O1", "S0O1_SUPPORT"}
    learned_allocation = arm in {"S0O1", "S1O1", "S0O1_ALLOC"}
    score = "learned_selection_score" if learned_selection else "market_selection_score"
    selected = matches.sort_values([score, "match_idx"], ascending=[False, True], kind="stable").head(N_LEGS)
    selected = selected.sort_values("match_idx", kind="stable").reset_index(drop=True)
    support_column = "learned_support" if learned_support else "market_support"
    supports = np.asarray(selected[support_column].tolist(), dtype=object)
    combinations = np.asarray(list(itertools.product((0, 1), repeat=N_LEGS)), dtype=int)
    chosen_outcomes = supports[np.arange(N_LEGS)[None, :], combinations]
    issue = str(selected.iloc[0]["issue"])
    match_indices = selected["match_idx"].to_numpy(int)
    ticket_keys = (
        [
            "|".join(
                f"bjslot:{issue}:{match_indices[position]:03d}={outcomes[position]}"
                for position in range(N_LEGS)
            )
            for outcomes in chosen_outcomes
        ]
        if include_tickets
        else [f"ticket-{index:03d}" for index in range(DISTINCT_TICKETS)]
    )
    if learned_allocation:
        value_matrix = np.asarray(selected["predicted_values"].tolist(), dtype=float)
        chosen_indices = np.vectorize(OUTCOME_ORDER.__getitem__)(chosen_outcomes)
        raw_weights = np.prod(
            value_matrix[np.arange(N_LEGS)[None, :], chosen_indices], axis=1
        )
    else:
        raw_weights = np.ones(DISTINCT_TICKETS)
    units = largest_remainder_units(raw_weights, ticket_keys)
    realized = selected["result_code"].to_numpy(str)
    observable = bool(selected["settlement_available"].all())
    miss = (chosen_outcomes != realized[None, :]).sum(axis=1)
    winning = np.flatnonzero(miss == 0)
    winning_position = int(winning[0]) if len(winning) else -1
    if observable:
        gross = (
            STAKE_PER_UNIT
            * int(units[winning_position])
            * PAYOUT_FACTOR
            * float(np.prod(selected["winning_sp"].to_numpy(float)))
            if winning_position >= 0
            else 0.0
        )
        stake = ISSUE_STAKE_CNY
        pnl = gross - stake
        settlement_status = "SETTLED"
    else:
        gross = stake = pnl = np.nan
        settlement_status = "UNOBSERVABLE_SETTLEMENT"
    tickets = (
        pd.DataFrame(
            {
                "issue": issue,
                "issue_year": int(selected.iloc[0]["issue_year"]),
                "issue_anchor_ts": selected.iloc[0]["issue_anchor_ts"],
                "model": model,
                "seed": seed,
                "arm": arm,
                "ticket_index": np.arange(DISTINCT_TICKETS),
                "ticket_key": ticket_keys,
                "units": units,
                "stake_cny": units * STAKE_PER_UNIT,
                "miss_distance": miss if observable else np.nan,
            }
        )
        if include_tickets
        else pd.DataFrame()
    )
    selected_keys = "|".join(
        f"bjslot:{row.issue}:{int(row.match_idx):03d}" for row in selected.itertuples()
    )
    support_repr = "|".join(
        f"{int(selected.iloc[position]['match_idx']):03d}:{','.join(supports[position])}"
        for position in range(N_LEGS)
    )
    concentration = units / FUNDED_UNITS
    bundle = {
        "issue": issue,
        "issue_year": int(selected.iloc[0]["issue_year"]),
        "issue_anchor_ts": selected.iloc[0]["issue_anchor_ts"],
        "model": model,
        "seed": seed,
        "arm": arm,
        "selected_fixture_keys": selected_keys,
        "support": support_repr,
        "settlement_status": settlement_status,
        "stake_cny": stake,
        "gross_cny": gross,
        "pnl_cny": pnl,
        "hit": bool(winning_position >= 0) if observable else np.nan,
        "winning_units": int(units[winning_position]) if observable and winning_position >= 0 else 0,
        "minimum_ticket_units": int(units.min()),
        "maximum_ticket_units": int(units.max()),
        "ticket_hhi": float(np.sum(concentration**2)),
        "distinct_ticket_count": DISTINCT_TICKETS,
        "support_miss_count": int(sum(result not in support for result, support in zip(realized, supports, strict=True)))
        if observable
        else np.nan,
    }
    return tickets, bundle


def largest_remainder_units(weights: np.ndarray, ticket_keys: list[str]) -> np.ndarray:
    """Allocate 512 units deterministically while retaining every Top-2 ticket."""

    if len(weights) != DISTINCT_TICKETS or not np.isfinite(weights).all() or (weights < 0).any():
        weights = np.ones(DISTINCT_TICKETS)
    if float(weights.sum()) <= 0:
        weights = np.ones(DISTINCT_TICKETS)
    remaining = FUNDED_UNITS - DISTINCT_TICKETS
    quota = weights / weights.sum() * remaining
    floor = np.floor(quota).astype(int)
    units = np.ones(DISTINCT_TICKETS, dtype=int) + floor
    residual = FUNDED_UNITS - int(units.sum())
    order = sorted(
        range(DISTINCT_TICKETS),
        key=lambda index: (-(quota[index] - floor[index]), ticket_keys[index]),
    )
    units[order[:residual]] += 1
    if int(units.sum()) != FUNDED_UNITS or int(units.min()) < 1:
        raise AssertionError("invalid ticket unit allocation")
    return units
