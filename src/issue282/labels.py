"""Historical counterfactual labels for complete Issue #282 actions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

import numpy as np
import pandas as pd

from .actions import PrototypeAction, prototype_action_space
from .counterfactuals import settle_distinct_prefixes
from .tickets import DistinctTicketStream, build_distinct_ticket_stream

OUTCOMES = ("3", "1", "0")
OUTCOME_TO_POSITION = {outcome: position for position, outcome in enumerate(OUTCOMES)}
TICKET_STREAM_SEEDS = tuple(282_000 + offset for offset in range(1, 17))


def materialize_action_labels(
    units: pd.DataFrame,
    probabilities: pd.DataFrame,
    values: pd.DataFrame,
    settlement_tensor: pd.DataFrame,
    *,
    actions: Iterable[PrototypeAction] | None = None,
    horizon: str = "10h",
    stream_seeds: tuple[int, ...] = TICKET_STREAM_SEEDS,
) -> pd.DataFrame:
    """Settle the bounded action catalog while nesting stream noise by issue.

    The returned action row aggregates nuisance ticket streams; the independent
    sample remains one Beijing issue.  WR and WOR share the same unique ticket
    discovery order.  Their difference is proposal-frequency evidence only
    until Stage 4 explicitly maps that evidence into stake multipliers.
    """

    catalog = tuple(actions or prototype_action_space())
    if not catalog:
        raise ValueError("at least one action is required")
    if not stream_seeds:
        raise ValueError("at least one ticket stream seed is required")
    _validate_source_alignment(units, probabilities, values)
    unit_h = units[units["snapshot_kind"].eq(horizon)]
    settlement = _settlement_lookup(settlement_tensor)
    grouped_actions: dict[tuple[str, str, int], list[PrototypeAction]] = defaultdict(list)
    for action in catalog:
        grouped_actions[
            (action.selector, action.outcome_weight_mode, action.n)
        ].append(action)

    rows: list[dict[str, object]] = []
    for issue, group in unit_h.groupby("issue", sort=True):
        issue_text = str(issue)
        settled = settlement.get(issue_text)
        if settled is None:
            continue
        index = group.index
        match_ids = group["match_idx"].to_numpy(dtype=int)
        probability = probabilities.reindex(index)[list(OUTCOMES)].to_numpy(dtype=float)
        cell_value = values.reindex(index)[
            [f"ev_raw_{outcome}" for outcome in OUTCOMES]
        ].to_numpy(dtype=float)
        realized = np.array(
            [
                OUTCOME_TO_POSITION.get(
                    str(settled["realized_outcome"].get(match_id)), -1
                )
                for match_id in match_ids
            ],
            dtype=int,
        )
        winning_sp = np.array(
            [float(settled["SP_SETTLE"].get(match_id, np.nan)) for match_id in match_ids],
            dtype=float,
        )
        if np.any(realized < 0):
            raise ValueError(f"issue {issue_text} has incomplete realized outcomes")
        for (selector, outcome_mode, n), group_catalog in grouped_actions.items():
            if n > len(group):
                continue
            eligible = _eligible_match_positions(cell_value, selector=selector, n=n)
            local_probability = probability[eligible]
            local_value = cell_value[eligible]
            proposal_surface = (
                local_value
                if outcome_mode == "CELL_VALUE"
                else local_probability
            )
            local_realized = realized[eligible]
            local_sp = winning_sp[eligible]
            requested_ks = sorted({action.k for action in group_catalog})
            max_k = max(requested_ks)

            top_actions = [a for a in group_catalog if a.generator == "TOP_VALUE"]
            if top_actions:
                stream = build_distinct_ticket_stream(
                    proposal_surface,
                    local_probability,
                    n=n,
                    generator="TOP_VALUE",
                    requested_unique=max_k,
                    seed=0,
                )
                settled_prefix = settle_distinct_prefixes(
                    stream, local_realized, local_sp, requested_ks
                )
                rows.extend(
                    _aggregate_rows(
                        issue_text,
                        group,
                        selector,
                        outcome_mode,
                        n,
                        "TOP_VALUE",
                        len(eligible),
                        [settled_prefix],
                    )
                )

            weighted_actions = [
                action
                for action in group_catalog
                if action.generator in {"WEIGHTED_WR", "WEIGHTED_WOR"}
            ]
            if weighted_actions:
                wr_results: list[pd.DataFrame] = []
                wor_results: list[pd.DataFrame] = []
                for base_seed in stream_seeds:
                    stream = build_distinct_ticket_stream(
                        proposal_surface,
                        local_probability,
                        n=n,
                        generator="WEIGHTED_WR",
                        requested_unique=max_k,
                        seed=_derived_seed(
                            base_seed, issue_text, selector, outcome_mode, n
                        ),
                    )
                    wr_results.append(
                        settle_distinct_prefixes(
                            stream, local_realized, local_sp, requested_ks
                        )
                    )
                    wor_stream = DistinctTicketStream(
                        match_positions=stream.match_positions,
                        outcome_positions=stream.outcome_positions,
                        proposal_identity_indices=np.arange(stream.unique_k, dtype=int),
                        generator="WEIGHTED_WOR",
                        seed=stream.seed,
                    )
                    wor_results.append(
                        settle_distinct_prefixes(
                            wor_stream, local_realized, local_sp, requested_ks
                        )
                    )
                for generator, seed_results in (
                    ("WEIGHTED_WR", wr_results),
                    ("WEIGHTED_WOR", wor_results),
                ):
                    if any(a.generator == generator for a in weighted_actions):
                        rows.extend(
                            _aggregate_rows(
                                issue_text,
                                group,
                                selector,
                                outcome_mode,
                                n,
                                generator,
                                len(eligible),
                                seed_results,
                            )
                        )
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("no counterfactual action labels were generated")
    return result.sort_values(["issue_year", "issue", "action_key"]).reset_index(
        drop=True
    )


def _eligible_match_positions(
    cell_value: np.ndarray, *, selector: str, n: int
) -> np.ndarray:
    if selector == "ALL":
        return np.arange(len(cell_value), dtype=int)
    if selector == "TOP_HALF_VALUE":
        count = max(n, int(np.ceil(len(cell_value) / 2)))
        best = np.nanmax(cell_value, axis=1)
        ranked = np.argsort(-np.nan_to_num(best, nan=-np.inf), kind="stable")
        return np.sort(ranked[:count])
    raise ValueError(f"unsupported selector: {selector}")


def _aggregate_rows(
    issue: str,
    group: pd.DataFrame,
    selector: str,
    outcome_mode: str,
    n: int,
    generator: str,
    selected_match_count: int,
    seed_results: list[pd.DataFrame],
) -> list[dict[str, object]]:
    stacked = pd.concat(
        [frame.assign(stream_index=index) for index, frame in enumerate(seed_results)],
        ignore_index=True,
    )
    rows: list[dict[str, object]] = []
    for requested_k, values in stacked.groupby("requested_k", sort=True):
        stake = values["stake_cny"].to_numpy(dtype=float)
        pnl = values["pnl_cny"].to_numpy(dtype=float)
        return_per_cny = np.divide(
            pnl, stake, out=np.zeros_like(pnl), where=stake > 0
        )
        normalized_pnl = return_per_cny * 100.0
        action = PrototypeAction(
            selector=selector,
            outcome_weight_mode=outcome_mode,
            n=n,
            generator=generator,
            k=int(requested_k),
        )
        rows.append(
            {
                "issue": issue,
                "issue_year": int(group["issue_year"].iloc[0]),
                "temporal_role": str(group["temporal_role"].iloc[0]),
                "action_key": action.key,
                "selector": selector,
                "outcome_weight_mode": outcome_mode,
                "n": n,
                "generator": generator,
                "k": int(requested_k),
                "selected_match_count": selected_match_count,
                "stream_count": int(len(seed_results)),
                "effective_k_mean": float(values["effective_k"].mean()),
                "proposal_count_mean": float(values["proposal_count"].mean()),
                "stake_cny_mean": float(stake.mean()),
                "pnl_cny_mean": float(pnl.mean()),
                "pnl_cny_q10": float(np.quantile(pnl, 0.10)),
                "pnl_cny_std": float(pnl.std(ddof=0)),
                "return_per_cny_mean": float(return_per_cny.mean()),
                "normalized_pnl_cny100": float(normalized_pnl.mean()),
                "positive_stream_fraction": float((pnl > 0).mean()),
                "hit_rate_mean": float(values["hit_rate"].mean()),
                "stake_hhi_mean": float(values["stake_hhi"].mean()),
                "stake_ess_mean": float(values["stake_ess"].mean()),
            }
        )
    return rows


def _settlement_lookup(
    tensor: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    winners = tensor[tensor["Y"].eq(1)].drop_duplicates(["issue", "match_idx"])
    return {
        str(issue): frame.set_index("match_idx")[["realized_outcome", "SP_SETTLE"]]
        for issue, frame in winners.groupby("issue")
    }


def _validate_source_alignment(
    units: pd.DataFrame, probabilities: pd.DataFrame, values: pd.DataFrame
) -> None:
    if not (len(units) == len(probabilities) == len(values)):
        raise ValueError("unit/probability/value source lengths are not aligned")
    if not units.index.equals(probabilities.index) or not units.index.equals(values.index):
        raise ValueError("unit/probability/value source indexes are not aligned")


def _derived_seed(
    seed: int, issue: str, selector: str, outcome_mode: str, n: int
) -> int:
    payload = f"{seed}:{issue}:{selector}:{outcome_mode}:N{n}".encode()
    value = 2166136261
    for byte in payload:
        value = (value ^ byte) * 16777619 & 0xFFFFFFFF
    return int(value)
