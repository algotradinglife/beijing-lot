"""Selective third-outcome protection experiment for Issue #356."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.low_n_match_selector.pipeline import _load_settlement, locate_data_root
from src.source_schema.publication import atomic_publish_directory

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    DEVELOPMENT_YEARS,
    FUNDED_UNITS,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    LANES,
    OUTCOMES,
    PAYOUT_FACTOR,
    SCORE_SURFACE,
    S0_BUNDLES,
    STAKE_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TRANSFER_YEARS,
    UPSTREAM_DECISIONS,
    UPSTREAM_FREEZE,
    UPSTREAM_MANIFEST,
    UPSTREAM_PREOUTCOME,
    UPSTREAM_SELECTIONS,
    UPSTREAM_SOURCE,
    UPSTREAM_TICKETS,
    VALUE_CELLS,
)


class ContractError(ValueError):
    """Raised when frozen Issue #356 semantics are violated."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    columns = sorted(frame.columns)
    projected = frame.loc[:, columns].copy()
    for column in columns:
        if pd.api.types.is_datetime64_any_dtype(projected[column]):
            values = pd.to_datetime(projected[column], utc=True)
            projected[column] = values.map(
                lambda value: "" if pd.isna(value) else value.isoformat()
            )
    hashes = np.sort(
        pd.util.hash_pandas_object(projected, index=False, categorize=False).to_numpy(
            dtype=np.uint64
        )
    )
    schema = [(column, str(projected[column].dtype)) for column in columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode())
    digest.update(hashes.tobytes())
    return digest.hexdigest()


def _strict_bool(series: pd.Series, name: str) -> None:
    if not pd.api.types.is_bool_dtype(series.dtype):
        raise ContractError(f"{name} must be a strict boolean")


def _periods(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    return [
        *[
            (str(year), frame[frame["issue_year"].eq(year)].copy())
            for year in (*DEVELOPMENT_YEARS, *TRANSFER_YEARS)
        ],
        (
            "ALL_2019_2021",
            frame[frame["issue_year"].isin(DEVELOPMENT_YEARS)].copy(),
        ),
        (
            "ALL_2022_2024",
            frame[frame["issue_year"].isin(TRANSFER_YEARS)].copy(),
        ),
    ]


def _longest_run(mask: np.ndarray) -> int:
    return max(
        (sum(1 for _ in run) for value, run in itertools.groupby(mask) if value),
        default=0,
    )


def _path_risk(pnl: np.ndarray) -> dict[str, Any]:
    """Issue-grain risk with recovery episodes beginning only underwater."""

    equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
    peaks = np.maximum.accumulate(equity)
    running_peak = float(equity[0])
    peak_index = 0
    underwater_peak_index: int | None = None
    completed: list[int] = []
    for index, value in enumerate(equity[1:], start=1):
        if value < running_peak and underwater_peak_index is None:
            underwater_peak_index = peak_index
        if value >= running_peak:
            if underwater_peak_index is not None:
                completed.append(index - underwater_peak_index)
                underwater_peak_index = None
            running_peak = float(value)
            peak_index = index
    open_underwater = (
        int(len(equity) - 1 - underwater_peak_index)
        if underwater_peak_index is not None
        else 0
    )
    return {
        "max_drawdown_cny": float((peaks - equity).max()),
        "max_drawdown_fraction": float(
            ((peaks - equity) / np.maximum(peaks, 1e-12)).max()
        ),
        "longest_losing_run": int(_longest_run(pnl < 0)),
        "completed_recovery_issues": int(max(completed, default=0)),
        "open_underwater_issues": open_underwater,
        "recovery_censored": bool(open_underwater > 0),
    }


def _lane_rows(frame: pd.DataFrame, lane: str) -> pd.DataFrame:
    spec = LANES[lane]
    return frame[
        frame["arm"].eq(spec["upstream_arm"]) & frame["n"].eq(spec["n"])
    ].copy()


def load_inputs(repo_root: Path) -> dict[str, pd.DataFrame]:
    preoutcome = pq.read_table(repo_root / UPSTREAM_PREOUTCOME).to_pandas()
    selections = pq.read_table(repo_root / UPSTREAM_SELECTIONS).to_pandas()
    upstream_tickets = pq.read_table(repo_root / UPSTREAM_TICKETS).to_pandas()
    decisions = pq.read_table(repo_root / UPSTREAM_DECISIONS).to_pandas()
    scores = pq.read_table(repo_root / SCORE_SURFACE).to_pandas()
    values = pq.read_table(repo_root / VALUE_CELLS).to_pandas()

    for frame in (preoutcome, selections, upstream_tickets, decisions, scores, values):
        frame["issue"] = frame["issue"].astype(str)
    _strict_bool(decisions["bet"], "upstream decisions.bet")
    if not set(values["outcome_code"].astype(str)).issubset(set(OUTCOMES)):
        raise ContractError("value cells contain non-canonical outcomes")

    score = scores[scores["arm"].eq("SELECTED_MODEL")][
        ["issue", "match_idx", "selector_score"]
    ].rename(columns={"selector_score": "strict_prior_coverage_score"})
    if score.duplicated(["issue", "match_idx"]).any():
        raise ContractError("coverage score surface has duplicate fixture keys")

    value_projection = values[
        ["issue", "match_idx", "outcome_code", "calibrated_probability"]
    ].copy()
    value_projection["outcome_code"] = value_projection["outcome_code"].astype(str)
    if value_projection.duplicated(["issue", "match_idx", "outcome_code"]).any():
        raise ContractError("value cells have duplicate Mx3 keys")

    lane_selections: list[pd.DataFrame] = []
    lane_bundles: list[pd.DataFrame] = []
    lane_decisions: list[pd.DataFrame] = []
    lane_tickets: list[pd.DataFrame] = []
    for lane in LANES:
        selected = _lane_rows(selections, lane)
        bundles = _lane_rows(preoutcome, lane)
        decision = _lane_rows(decisions, lane)
        lane_ticket = _lane_rows(upstream_tickets, lane)
        selected["lane"] = lane
        bundles["lane"] = lane
        decision["lane"] = lane
        lane_ticket["lane"] = lane
        lane_selections.append(selected)
        lane_bundles.append(bundles)
        lane_decisions.append(decision)
        lane_tickets.append(lane_ticket)
    lane_selections_frame = pd.concat(lane_selections, ignore_index=True)
    lane_bundles_frame = pd.concat(lane_bundles, ignore_index=True)
    lane_decisions_frame = pd.concat(lane_decisions, ignore_index=True)
    lane_tickets_frame = pd.concat(lane_tickets, ignore_index=True)

    lane_selections_frame = lane_selections_frame.merge(
        score, on=["issue", "match_idx"], how="left", validate="many_to_one"
    )
    if lane_selections_frame["strict_prior_coverage_score"].isna().any():
        raise ContractError("selected fixture lacks strictly-prior coverage score")
    if not np.allclose(
        lane_selections_frame["coverage_score"],
        lane_selections_frame["strict_prior_coverage_score"],
        rtol=0,
        atol=1e-12,
    ):
        raise ContractError("#359 selection coverage score does not bind to #355")

    third_rows: list[dict[str, Any]] = []
    value_lookup = value_projection.set_index(["issue", "match_idx", "outcome_code"])[
        "calibrated_probability"
    ].to_dict()
    for row in lane_selections_frame.itertuples(index=False):
        omitted = next(
            outcome for outcome in OUTCOMES if outcome not in row.baseline_support
        )
        probability = value_lookup.get((str(row.issue), int(row.match_idx), omitted))
        if probability is None or not np.isfinite(probability):
            raise ContractError("selected fixture lacks omitted-outcome probability")
        third_rows.append(
            {
                "issue": str(row.issue),
                "lane": str(row.lane),
                "n": int(row.n),
                "match_idx": int(row.match_idx),
                "omitted_outcome": omitted,
                "omitted_probability": float(probability),
            }
        )
    third = pd.DataFrame(third_rows)
    lane_selections_frame = lane_selections_frame.merge(
        third,
        on=["issue", "lane", "n", "match_idx"],
        validate="one_to_one",
    )
    lane_selections_frame["predicted_top2_miss"] = (
        1.0 - lane_selections_frame["strict_prior_coverage_score"]
    )
    if not lane_selections_frame["predicted_top2_miss"].between(0, 1).all():
        raise ContractError("predicted Top-2 miss probability is outside [0,1]")
    lane_selections_frame = lane_selections_frame.sort_values(
        [
            "issue",
            "lane",
            "n",
            "predicted_top2_miss",
            "omitted_probability",
            "match_idx",
        ],
        ascending=[True, True, True, False, False, True],
        kind="stable",
    )
    lane_selections_frame["protection_rank"] = (
        lane_selections_frame.groupby(["issue", "lane", "n"], observed=True)
        .cumcount()
        .add(1)
        .astype(int)
    )
    counts = lane_selections_frame.groupby(["issue", "lane", "n"], observed=True).size()
    if not (counts.index.get_level_values("n").to_numpy() == counts.to_numpy()).all():
        raise ContractError(
            "upstream BET selection does not contain exactly N fixtures"
        )
    return {
        "selections": lane_selections_frame.reset_index(drop=True),
        "bundles": lane_bundles_frame.reset_index(drop=True),
        "decisions": lane_decisions_frame.reset_index(drop=True),
        "tickets": lane_tickets_frame.reset_index(drop=True),
    }


def _ticket_units(issue: str, lane: str, n: int, p: int, count: int) -> np.ndarray:
    base, remainder = divmod(FUNDED_UNITS, count)
    if base < 1:
        raise ContractError("ticket count exceeds funded unit budget")
    units = np.full(count, base, dtype=int)
    if remainder:
        token = f"{CONTRACT_ID}|{issue}|{lane}|N{n}|P{p}".encode()
        offset = int(hashlib.sha256(token).hexdigest(), 16) % count
        recipients = {
            (offset + math.floor(index * count / remainder)) % count
            for index in range(remainder)
        }
        if len(recipients) != remainder:
            raise ContractError("remainder allocation did not produce unique tickets")
        units[list(recipients)] += 1
    if units.sum() != FUNDED_UNITS or units.max() - units.min() > 1:
        raise ContractError("ticket allocation violates exact/even budget")
    return units


def construct_protection(inputs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    selections = inputs["selections"]
    bundles = inputs["bundles"]
    decisions = inputs["decisions"]
    bundle_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    selection_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []

    for row in decisions.itertuples(index=False):
        for p in range(int(row.n) + 1):
            decision_rows.append(
                {
                    "issue": str(row.issue),
                    "issue_year": int(row.issue_year),
                    "issue_anchor_ts": pd.Timestamp(row.issue_anchor_ts),
                    "lane": str(row.lane),
                    "n": int(row.n),
                    "p": p,
                    "upstream_decision": str(row.decision),
                    "bet": bool(row.bet),
                }
            )
    expanded_decisions = pd.DataFrame(decision_rows)
    _strict_bool(expanded_decisions["bet"], "expanded decisions.bet")

    grouped = selections.groupby(["issue", "lane", "n"], observed=True, sort=True)
    bundle_lookup = bundles.set_index(["issue", "lane", "n"]).to_dict("index")
    for (issue, lane, n), group in grouped:
        upstream = bundle_lookup.get((str(issue), str(lane), int(n)))
        if upstream is None:
            raise ContractError("BET selection lacks upstream bundle")
        group = group.sort_values("match_idx", kind="stable")
        ids = group["match_idx"].astype(int).tolist()
        baseline_support = dict(
            zip(
                map(str, ids),
                group["baseline_support"].astype(str).tolist(),
                strict=True,
            )
        )
        ranking = group.set_index("match_idx")["protection_rank"].astype(int).to_dict()
        omitted = group.set_index("match_idx")["omitted_outcome"].astype(str).to_dict()
        for p in range(int(n) + 1):
            protected_ids = sorted(
                match_idx for match_idx in ids if ranking[match_idx] <= p
            )
            final_support = {
                str(match_idx): (
                    baseline_support[str(match_idx)] + omitted[match_idx]
                    if match_idx in protected_ids
                    else baseline_support[str(match_idx)]
                )
                for match_idx in ids
            }
            choice_lists = [list(final_support[str(match_idx)]) for match_idx in ids]
            choices = list(itertools.product(*choice_lists))
            expected_count = 2 ** (int(n) - p) * 3**p
            if len(choices) != expected_count:
                raise ContractError("protection Cartesian ticket count is wrong")
            units = _ticket_units(str(issue), str(lane), int(n), p, len(choices))
            bundle_rows.append(
                {
                    "issue": str(issue),
                    "issue_year": int(upstream["issue_year"]),
                    "issue_anchor_ts": pd.Timestamp(upstream["issue_anchor_ts"]),
                    "lane": str(lane),
                    "n": int(n),
                    "p": p,
                    "selected_match_ids": "|".join(map(str, ids)),
                    "baseline_support_json": json.dumps(
                        baseline_support, sort_keys=True, separators=(",", ":")
                    ),
                    "support_json": json.dumps(
                        final_support, sort_keys=True, separators=(",", ":")
                    ),
                    "protected_match_ids": "|".join(map(str, protected_ids)),
                    "ticket_count": len(choices),
                    "min_units_per_ticket": int(units.min()),
                    "max_units_per_ticket": int(units.max()),
                    "planned_stake_cny": ISSUE_STAKE_CNY,
                }
            )
            for item in group.itertuples(index=False):
                selection_rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(item.issue_year),
                        "issue_anchor_ts": pd.Timestamp(item.issue_anchor_ts),
                        "lane": str(lane),
                        "n": int(n),
                        "p": p,
                        "match_idx": int(item.match_idx),
                        "baseline_support": str(item.baseline_support),
                        "final_support": final_support[str(item.match_idx)],
                        "omitted_outcome": str(item.omitted_outcome),
                        "omitted_probability": float(item.omitted_probability),
                        "strict_prior_coverage_score": float(
                            item.strict_prior_coverage_score
                        ),
                        "predicted_top2_miss": float(item.predicted_top2_miss),
                        "protection_rank": int(item.protection_rank),
                        "protected": bool(int(item.protection_rank) <= p),
                    }
                )
            for ticket_index, (ticket_choices, ticket_units) in enumerate(
                zip(choices, units, strict=True)
            ):
                ticket_key = "|".join(
                    f"{match_idx}={choice}"
                    for match_idx, choice in zip(ids, ticket_choices, strict=True)
                )
                ticket_rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(upstream["issue_year"]),
                        "lane": str(lane),
                        "n": int(n),
                        "p": p,
                        "ticket_index": ticket_index,
                        "ticket_key": ticket_key,
                        "units": int(ticket_units),
                        "stake_cny": float(ticket_units * STAKE_UNIT_CNY),
                    }
                )
    protection_selections = pd.DataFrame(selection_rows)
    _strict_bool(protection_selections["protected"], "protection selections.protected")
    protection_bundles = pd.DataFrame(bundle_rows)
    tickets = pd.DataFrame(ticket_rows)
    budget = tickets.groupby(["issue", "lane", "n", "p"], observed=True).agg(
        tickets=("ticket_key", "nunique"),
        units=("units", "sum"),
        stake=("stake_cny", "sum"),
        min_units=("units", "min"),
        max_units=("units", "max"),
    )
    if not (
        budget["units"].eq(FUNDED_UNITS).all()
        and np.allclose(budget["stake"], ISSUE_STAKE_CNY, rtol=0, atol=1e-12)
        and (budget["max_units"] - budget["min_units"]).le(1).all()
    ):
        raise ContractError("ticket ledger violates budget or balance")

    p0_bundles = protection_bundles[protection_bundles["p"].eq(0)].copy()
    bundle_columns = [
        "issue",
        "issue_year",
        "issue_anchor_ts",
        "lane",
        "n",
        "selected_match_ids",
        "support_json",
        "ticket_count",
        "planned_stake_cny",
    ]
    expected_bundles = (
        inputs["bundles"][bundle_columns]
        .sort_values(
            ["issue_year", "issue_anchor_ts", "issue", "lane", "n"], kind="stable"
        )
        .reset_index(drop=True)
    )
    actual_bundles = (
        p0_bundles[bundle_columns]
        .sort_values(
            ["issue_year", "issue_anchor_ts", "issue", "lane", "n"], kind="stable"
        )
        .reset_index(drop=True)
    )
    try:
        pd.testing.assert_frame_equal(
            actual_bundles, expected_bundles, check_dtype=False, check_exact=True
        )
    except AssertionError as exc:
        raise ContractError(
            "P0 bundle does not exactly reproduce upstream lane"
        ) from exc

    ticket_columns = [
        "issue",
        "issue_year",
        "lane",
        "n",
        "ticket_index",
        "ticket_key",
        "units",
        "stake_cny",
    ]
    expected_tickets = (
        inputs["tickets"][ticket_columns]
        .sort_values(
            ["issue_year", "issue", "lane", "n", "ticket_index"], kind="stable"
        )
        .reset_index(drop=True)
    )
    actual_tickets = (
        tickets[tickets["p"].eq(0)][ticket_columns]
        .sort_values(
            ["issue_year", "issue", "lane", "n", "ticket_index"], kind="stable"
        )
        .reset_index(drop=True)
    )
    try:
        pd.testing.assert_frame_equal(
            actual_tickets, expected_tickets, check_dtype=False, check_exact=True
        )
    except AssertionError as exc:
        raise ContractError(
            "P0 ticket ledger does not exactly reproduce upstream lane"
        ) from exc
    return {
        "selections": protection_selections,
        "bundles": protection_bundles,
        "tickets": tickets,
        "decisions": expanded_decisions,
        "budget": budget.reset_index(),
    }


def settle_protection(
    bundles: pd.DataFrame,
    tickets: pd.DataFrame,
    settlement: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    label_lookup = settlement.set_index(["issue", "match_idx"]).to_dict("index")
    ticket_lookup = tickets.set_index(["issue", "lane", "n", "p", "ticket_key"])[
        "units"
    ].to_dict()
    settled_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    for row in bundles.itertuples(index=False):
        ids = [int(value) for value in str(row.selected_match_ids).split("|")]
        baseline = json.loads(row.baseline_support_json)
        support = json.loads(row.support_json)
        observable = True
        result_choices: list[str] = []
        winning_sps: list[float] = []
        baseline_misses = 0
        protected_misses = 0
        for match_idx in ids:
            label = label_lookup.get((str(row.issue), match_idx))
            available = label is not None and bool(label["settlement_available"])
            observable &= available
            result = str(label["result_code"]) if available else ""
            winning_sp = float(label["winning_sp"]) if available else math.nan
            baseline_included = bool(result and result in baseline[str(match_idx)])
            final_included = bool(result and result in support[str(match_idx)])
            baseline_misses += int(not baseline_included)
            protected_misses += int(not final_included)
            result_choices.append(result)
            winning_sps.append(winning_sp)
            attribution_rows.append(
                {
                    "issue": str(row.issue),
                    "issue_year": int(row.issue_year),
                    "lane": str(row.lane),
                    "n": int(row.n),
                    "p": int(row.p),
                    "match_idx": match_idx,
                    "baseline_support": baseline[str(match_idx)],
                    "final_support": support[str(match_idx)],
                    "protected": support[str(match_idx)] != baseline[str(match_idx)],
                    "result_code": result,
                    "winning_sp": winning_sp,
                    "baseline_included": baseline_included,
                    "final_included": final_included,
                    "settlement_available": available,
                }
            )
        base = row._asdict()
        if not observable:
            settled_rows.append(
                {
                    **base,
                    "settlement_status": "UNTRUSTED_SELECTED_LEG",
                    "stake_cny": math.nan,
                    "gross_cny": math.nan,
                    "pnl_cny": math.nan,
                    "hit": False,
                    "baseline_hit": False,
                    "baseline_miss_count": math.nan,
                    "protected_miss_count": math.nan,
                    "winning_ticket_units": math.nan,
                }
            )
            continue
        hit = protected_misses == 0
        baseline_hit = baseline_misses == 0
        winning_ticket_key = "|".join(
            f"{match_idx}={result}"
            for match_idx, result in zip(ids, result_choices, strict=True)
        )
        winning_units = (
            int(
                ticket_lookup[
                    (
                        str(row.issue),
                        str(row.lane),
                        int(row.n),
                        int(row.p),
                        winning_ticket_key,
                    )
                ]
            )
            if hit
            else 0
        )
        gross = (
            winning_units * STAKE_UNIT_CNY * PAYOUT_FACTOR * float(np.prod(winning_sps))
            if hit
            else 0.0
        )
        settled_rows.append(
            {
                **base,
                "settlement_status": "SETTLED",
                "stake_cny": ISSUE_STAKE_CNY,
                "gross_cny": gross,
                "pnl_cny": gross - ISSUE_STAKE_CNY,
                "hit": bool(hit),
                "baseline_hit": bool(baseline_hit),
                "baseline_miss_count": int(baseline_misses),
                "protected_miss_count": int(protected_misses),
                "winning_ticket_units": int(winning_units),
            }
        )
    settled = pd.DataFrame(settled_rows)
    attribution = pd.DataFrame(attribution_rows)
    for column in ("hit", "baseline_hit"):
        _strict_bool(settled[column], f"settled.{column}")
    for column in (
        "protected",
        "baseline_included",
        "final_included",
        "settlement_available",
    ):
        _strict_bool(attribution[column], f"attribution.{column}")
    return settled, attribution


def policy_state(decisions: pd.DataFrame, settled: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "issue",
        "issue_year",
        "lane",
        "n",
        "p",
        "settlement_status",
        "stake_cny",
        "gross_cny",
        "pnl_cny",
        "hit",
        "baseline_hit",
        "baseline_miss_count",
        "protected_miss_count",
        "winning_ticket_units",
        "ticket_count",
    ]
    state = decisions.merge(
        settled[columns],
        on=["issue", "issue_year", "lane", "n", "p"],
        how="left",
        validate="one_to_one",
    )
    no_bet = ~state["bet"]
    state.loc[no_bet, "settlement_status"] = "NO_BET"
    state.loc[no_bet, ["stake_cny", "gross_cny", "pnl_cny"]] = 0.0
    state.loc[no_bet, ["hit", "baseline_hit"]] = False
    state.loc[no_bet, ["baseline_miss_count", "protected_miss_count"]] = math.nan
    state.loc[no_bet, ["winning_ticket_units", "ticket_count"]] = 0
    missing_bet = state["bet"] & state["settlement_status"].isna()
    if missing_bet.any():
        raise ContractError("BET decision lacks a protection settlement")
    state["hit"] = state["hit"].astype(bool)
    state["baseline_hit"] = state["baseline_hit"].astype(bool)
    _strict_bool(state["hit"], "policy state.hit")
    return state.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "lane", "n", "p"],
        kind="stable",
    ).reset_index(drop=True)


def _payout_concentration(gross: np.ndarray) -> tuple[float, float]:
    payouts = gross[gross > 0]
    if not len(payouts):
        return 0.0, 0.0
    weights = payouts / payouts.sum()
    return float(weights.max()), float(np.square(weights).sum())


def evaluate(
    decisions: pd.DataFrame,
    settled: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    state = policy_state(decisions, settled)
    performance_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    for (lane, n, p), frame in state.groupby(
        ["lane", "n", "p"], observed=True, sort=True
    ):
        for period, group in _periods(frame):
            group = group[
                group["settlement_status"].isin(["SETTLED", "NO_BET"])
            ].sort_values(["issue_anchor_ts", "issue"], kind="stable")
            if group.empty:
                continue
            pnl = group["pnl_cny"].to_numpy(float)
            gross = group["gross_cny"].to_numpy(float)
            stake = float(group["stake_cny"].sum())
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            largest_share, hhi = _payout_concentration(gross)
            bets = group[group["settlement_status"].eq("SETTLED")]
            performance_rows.append(
                {
                    "lane": lane,
                    "primary_lane": bool(LANES[str(lane)]["primary"]),
                    "n": int(n),
                    "p": int(p),
                    "period": period,
                    "evaluable_issues": int(len(group)),
                    "bet_issues": int(len(bets)),
                    "no_bet_issues": int(group["settlement_status"].eq("NO_BET").sum()),
                    "stake_cny": stake,
                    "gross_cny": float(gross.sum()),
                    "pnl_cny": float(pnl.sum()),
                    "ending_capital_cny": float(capital[-1]),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / stake) if stake else math.nan,
                    "hit_rate_per_bet": float(bets["hit"].mean())
                    if len(bets)
                    else math.nan,
                    "largest_payout_share": largest_share,
                    "payout_hhi": hhi,
                }
            )
            risk_rows.append(
                {
                    "lane": lane,
                    "n": int(n),
                    "p": int(p),
                    "period": period,
                    **_path_risk(pnl),
                }
            )
            for index, row in enumerate(group.itertuples(index=False), start=1):
                path_rows.append(
                    {
                        "lane": lane,
                        "n": int(n),
                        "p": int(p),
                        "period": period,
                        "path_index": index,
                        "issue": str(row.issue),
                        "issue_year": int(row.issue_year),
                        "settlement_status": str(row.settlement_status),
                        "pnl_cny": float(row.pnl_cny),
                        "capital_cny": float(capital[index - 1]),
                    }
                )

    contrast_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    for (lane, n), lane_state in state.groupby(["lane", "n"], observed=True):
        reference = lane_state[lane_state["p"].eq(0)]
        for p, candidate in lane_state.groupby("p", observed=True):
            paired = reference.merge(
                candidate,
                on=["issue", "issue_year", "lane", "n"],
                suffixes=("_p0", "_candidate"),
                validate="one_to_one",
            )
            paired = paired[
                paired["settlement_status_p0"].isin(["SETTLED", "NO_BET"])
                & paired["settlement_status_candidate"].isin(["SETTLED", "NO_BET"])
            ].copy()
            for period, group in _periods(paired):
                group = group.sort_values(
                    ["issue_anchor_ts_p0", "issue"], kind="stable"
                )
                if group.empty:
                    continue
                ref_pnl = group["pnl_cny_p0"].to_numpy(float)
                cand_pnl = group["pnl_cny_candidate"].to_numpy(float)
                delta = cand_pnl - ref_pnl
                ref_gross = group["gross_cny_p0"].to_numpy(float)
                cand_gross = group["gross_cny_candidate"].to_numpy(float)
                largest_delta = int(np.argmax(np.abs(delta)))
                ref_ex = ref_pnl.sum() - ref_pnl[int(np.argmax(ref_gross))]
                cand_ex = cand_pnl.sum() - cand_pnl[int(np.argmax(cand_gross))]
                rng = np.random.default_rng(
                    BOOTSTRAP_SEED
                    + int(n) * 10_000
                    + int(p) * 1_000
                    + sum(map(ord, str(lane) + period))
                )
                draws = rng.choice(
                    delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True
                ).mean(axis=1)
                ref_risk = _path_risk(ref_pnl)
                cand_risk = _path_risk(cand_pnl)
                settled_bets = group[
                    group["settlement_status_p0"].eq("SETTLED")
                    & group["settlement_status_candidate"].eq("SETTLED")
                ]
                contrast_rows.append(
                    {
                        "lane": lane,
                        "primary_lane": bool(LANES[str(lane)]["primary"]),
                        "n": int(n),
                        "p": int(p),
                        "period": period,
                        "common_issues": int(len(group)),
                        "common_bet_issues": int(len(settled_bets)),
                        "p0_pnl_cny": float(ref_pnl.sum()),
                        "candidate_pnl_cny": float(cand_pnl.sum()),
                        "pnl_lift_cny": float(delta.sum()),
                        "mean_pnl_lift_cny": float(delta.mean()),
                        "hit_rate_lift": float(
                            settled_bets["hit_candidate"].mean()
                            - settled_bets["hit_p0"].mean()
                        ),
                        "armwise_ex_largest_pnl_lift_cny": float(cand_ex - ref_ex),
                        "ex_largest_abs_delta_pnl_lift_cny": float(
                            delta.sum() - delta[largest_delta]
                        ),
                        "largest_abs_paired_delta_cny": float(
                            abs(delta[largest_delta])
                        ),
                        "bootstrap_mean_lift_p05_cny": float(np.quantile(draws, 0.05)),
                        "bootstrap_mean_lift_p50_cny": float(np.quantile(draws, 0.50)),
                        "bootstrap_mean_lift_p95_cny": float(np.quantile(draws, 0.95)),
                        **{f"p0_{key}": value for key, value in ref_risk.items()},
                        **{
                            f"candidate_{key}": value
                            for key, value in cand_risk.items()
                        },
                    }
                )
                p0_miss = settled_bets["baseline_miss_count_p0"]
                candidate_hit = settled_bets["hit_candidate"]
                baseline_hit = settled_bets["hit_p0"]
                salvaged = (~baseline_hit) & candidate_hit
                attribution_rows.append(
                    {
                        "lane": lane,
                        "n": int(n),
                        "p": int(p),
                        "period": period,
                        "settled_bet_issues": int(len(settled_bets)),
                        "baseline_hit_issues": int(baseline_hit.sum()),
                        "baseline_one_miss_issues": int(p0_miss.eq(1).sum()),
                        "baseline_two_plus_miss_issues": int(p0_miss.ge(2).sum()),
                        "salvaged_issues": int(salvaged.sum()),
                        "salvaged_one_miss_issues": int(
                            (salvaged & p0_miss.eq(1)).sum()
                        ),
                        "salvaged_two_plus_miss_issues": int(
                            (salvaged & p0_miss.ge(2)).sum()
                        ),
                        "salvage_gross_cny": float(
                            settled_bets.loc[salvaged, "gross_cny_candidate"].sum()
                        ),
                        "incumbent_hit_dilution_cny": float(
                            (
                                settled_bets.loc[baseline_hit, "gross_cny_candidate"]
                                - settled_bets.loc[baseline_hit, "gross_cny_p0"]
                            ).sum()
                        ),
                    }
                )
    return (
        pd.DataFrame(performance_rows),
        pd.DataFrame(risk_rows),
        pd.DataFrame(path_rows),
        pd.DataFrame(contrast_rows),
        pd.DataFrame(attribution_rows),
    )


def diagnose_protection_rank(
    selections: pd.DataFrame, support_attribution: pd.DataFrame
) -> pd.DataFrame:
    """Compare the frozen pre-outcome protection rank with realized Top-2 misses."""

    frozen = selections[selections["p"].eq(0)][
        [
            "issue",
            "issue_year",
            "lane",
            "n",
            "match_idx",
            "protection_rank",
            "predicted_top2_miss",
        ]
    ]
    labels = support_attribution[support_attribution["p"].eq(0)][
        [
            "issue",
            "lane",
            "n",
            "match_idx",
            "baseline_included",
            "settlement_available",
        ]
    ]
    frame = frozen.merge(
        labels,
        on=["issue", "lane", "n", "match_idx"],
        validate="one_to_one",
    )
    frame = frame[frame["settlement_available"]].copy()
    frame["observed_top2_miss"] = ~frame["baseline_included"]
    rows: list[dict[str, Any]] = []
    for (lane, n, rank), group in frame.groupby(
        ["lane", "n", "protection_rank"], observed=True, sort=True
    ):
        for period, sample in _periods(group):
            if sample.empty:
                continue
            predicted = float(sample["predicted_top2_miss"].mean())
            observed = float(sample["observed_top2_miss"].mean())
            rows.append(
                {
                    "lane": str(lane),
                    "n": int(n),
                    "protection_rank": int(rank),
                    "period": period,
                    "evaluated_fixtures": int(len(sample)),
                    "predicted_top2_miss_rate": predicted,
                    "observed_top2_miss_rate": observed,
                    "calibration_error": observed - predicted,
                }
            )
    return pd.DataFrame(rows)


def select_development_p(contrasts: pd.DataFrame) -> pd.DataFrame:
    selected_rows: list[dict[str, Any]] = []
    for lane, spec in LANES.items():
        n = int(spec["n"])
        pooled = contrasts[
            contrasts["lane"].eq(lane)
            & contrasts["n"].eq(n)
            & contrasts["period"].eq("ALL_2019_2021")
        ]
        annual = contrasts[
            contrasts["lane"].eq(lane)
            & contrasts["n"].eq(n)
            & contrasts["period"].isin(map(str, DEVELOPMENT_YEARS))
        ]
        candidates: list[dict[str, Any]] = []
        for row in pooled.itertuples(index=False):
            yearly = annual[annual["p"].eq(row.p)]
            positive_years = int((yearly["pnl_lift_cny"] > 0).sum())
            risk_ok = bool(
                row.candidate_max_drawdown_fraction
                <= row.p0_max_drawdown_fraction + 0.02
                and row.candidate_longest_losing_run <= row.p0_longest_losing_run + 2
            )
            passes = bool(
                row.p > 0
                and row.pnl_lift_cny > 0
                and positive_years >= 2
                and row.armwise_ex_largest_pnl_lift_cny > 0
                and risk_ok
            )
            candidates.append(
                {
                    "lane": lane,
                    "n": n,
                    "p": int(row.p),
                    "primary_lane": bool(spec["primary"]),
                    "development_positive_years": positive_years,
                    "development_lift_cny": float(row.pnl_lift_cny),
                    "development_ex_largest_lift_cny": float(
                        row.armwise_ex_largest_pnl_lift_cny
                    ),
                    "development_hit_rate_lift": float(row.hit_rate_lift),
                    "development_risk_gate": risk_ok,
                    "development_gate_pass": passes,
                }
            )
        passing = [row for row in candidates if row["development_gate_pass"]]
        if passing:
            chosen = max(
                passing,
                key=lambda row: (
                    row["development_positive_years"],
                    row["development_ex_largest_lift_cny"],
                    row["development_lift_cny"],
                    row["development_hit_rate_lift"],
                    -row["p"],
                ),
            )
        else:
            chosen = next(row for row in candidates if row["p"] == 0)
        selected_rows.append(chosen)
    return (
        pd.DataFrame(selected_rows)
        .sort_values(["primary_lane", "n", "lane"], ascending=[False, True, True])
        .reset_index(drop=True)
    )


def decide(selected: pd.DataFrame, contrasts: pd.DataFrame) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for selection in selected.itertuples(index=False):
        pooled = contrasts[
            contrasts["lane"].eq(selection.lane)
            & contrasts["n"].eq(selection.n)
            & contrasts["p"].eq(selection.p)
            & contrasts["period"].eq("ALL_2022_2024")
        ].iloc[0]
        annual = contrasts[
            contrasts["lane"].eq(selection.lane)
            & contrasts["n"].eq(selection.n)
            & contrasts["p"].eq(selection.p)
            & contrasts["period"].isin(map(str, TRANSFER_YEARS))
        ]
        positive_years = int((annual["pnl_lift_cny"] > 0).sum())
        risk_ok = bool(
            pooled.candidate_max_drawdown_fraction
            <= pooled.p0_max_drawdown_fraction + 0.02
            and pooled.candidate_longest_losing_run <= pooled.p0_longest_losing_run + 2
        )
        historical = bool(
            selection.p > 0
            and pooled.pnl_lift_cny > 0
            and positive_years >= 2
            and pooled.armwise_ex_largest_pnl_lift_cny > 0
            and risk_ok
        )
        robust = bool(historical and pooled.bootstrap_mean_lift_p05_cny > 0)
        rows.append(
            {
                "lane": selection.lane,
                "n": int(selection.n),
                "selected_p": int(selection.p),
                "primary_lane": bool(selection.primary_lane),
                "development_gate_pass": bool(selection.development_gate_pass),
                "transfer_lift_cny": float(pooled.pnl_lift_cny),
                "transfer_positive_years": positive_years,
                "transfer_ex_largest_lift_cny": float(
                    pooled.armwise_ex_largest_pnl_lift_cny
                ),
                "bootstrap_mean_lift_p05_cny": float(
                    pooled.bootstrap_mean_lift_p05_cny
                ),
                "path_risk_gate": risk_ok,
                "historical_signal": historical,
                "robust_historical_signal": robust,
            }
        )
    primary = [row for row in rows if row["primary_lane"]]
    verdict = (
        "ROBUST_HISTORICAL_SIGNAL"
        if any(row["robust_historical_signal"] for row in primary)
        else "HISTORICAL_SIGNAL"
        if any(row["historical_signal"] for row in primary)
        else "NO_INCREMENT"
    )
    return {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "verdict": verdict,
        "selected_p_results": rows,
        "primary_decision_only_s0": True,
        "diagnostic_sleeves_are_exposed": True,
        "production_or_holdout_authorized": False,
        "changes_210_or_218": False,
    }


def _implementation_hashes(repo_root: Path) -> dict[str, str]:
    paths = (
        "src/low_n_third_outcome_protection/__init__.py",
        "src/low_n_third_outcome_protection/contract.py",
        "src/low_n_third_outcome_protection/pipeline.py",
        "scripts/run_low_n_third_outcome_protection.py",
        "scripts/verify_low_n_third_outcome_protection.py",
        "scripts/build_low_n_third_outcome_protection_notebook.py",
        "tests/test_low_n_third_outcome_protection.py",
    )
    return {path: sha256_file(repo_root / path) for path in paths}


def _scientific_frames(repo_root: Path, data_root: Path) -> dict[str, Any]:
    inputs = load_inputs(repo_root)
    protection = construct_protection(inputs)
    development_issues = sorted(
        protection["decisions"]
        .loc[protection["decisions"]["issue_year"].isin(DEVELOPMENT_YEARS), "issue"]
        .unique()
    )
    development_settlement = _load_settlement(data_root, development_issues)
    development_bundles = protection["bundles"][
        protection["bundles"]["issue_year"].isin(DEVELOPMENT_YEARS)
    ]
    development_tickets = protection["tickets"][
        protection["tickets"]["issue_year"].isin(DEVELOPMENT_YEARS)
    ]
    development_decisions = protection["decisions"][
        protection["decisions"]["issue_year"].isin(DEVELOPMENT_YEARS)
    ]
    development_settled, _ = settle_protection(
        development_bundles, development_tickets, development_settlement
    )
    _, _, _, development_contrasts, _ = evaluate(
        development_decisions, development_settled
    )
    selected = select_development_p(development_contrasts)
    freeze_receipt = {
        "contract": CONTRACT_ID,
        "development_years": list(DEVELOPMENT_YEARS),
        "transfer_years": list(TRANSFER_YEARS),
        "protection_priority": "1_MINUS_STRICT_PRIOR_COVERAGE_SCORE",
        "tie_break": "OMITTED_PROBABILITY_DESC_MATCH_IDX_ASC",
        "ticket_allocation": "EVEN_INTEGER_WITH_ISSUE_BOUND_ROTATION",
        "payout_65_semantics": "TICKET_LEVEL_ONCE",
        "selected_p": selected.to_dict("records"),
        "selection_surface_sha256": stable_frame_sha(inputs["selections"]),
        "preoutcome_bundles_sha256": stable_frame_sha(protection["bundles"]),
        "tickets_sha256": stable_frame_sha(protection["tickets"]),
        "decisions_sha256": stable_frame_sha(protection["decisions"]),
        "development_contrasts_sha256": stable_frame_sha(development_contrasts),
        "transfer_labels_opened_at_freeze": False,
    }

    transfer_issues = sorted(
        protection["decisions"]
        .loc[protection["decisions"]["issue_year"].isin(TRANSFER_YEARS), "issue"]
        .unique()
    )
    transfer_settlement = _load_settlement(data_root, transfer_issues)
    settlement = pd.concat(
        [development_settlement, transfer_settlement], ignore_index=True
    ).drop_duplicates(["issue", "match_idx"], keep="first")
    settled, support_attribution = settle_protection(
        protection["bundles"], protection["tickets"], settlement
    )
    performance, risk, paths, contrasts, attribution = evaluate(
        protection["decisions"], settled
    )
    rank_diagnostics = diagnose_protection_rank(
        protection["selections"], support_attribution
    )
    decision = decide(selected, contrasts)
    source_receipt = {
        "contract": CONTRACT_ID,
        "upstream_preoutcome_sha256": sha256_file(repo_root / UPSTREAM_PREOUTCOME),
        "upstream_selections_sha256": sha256_file(repo_root / UPSTREAM_SELECTIONS),
        "upstream_tickets_sha256": sha256_file(repo_root / UPSTREAM_TICKETS),
        "upstream_decisions_sha256": sha256_file(repo_root / UPSTREAM_DECISIONS),
        "upstream_freeze_sha256": sha256_file(repo_root / UPSTREAM_FREEZE),
        "upstream_source_sha256": sha256_file(repo_root / UPSTREAM_SOURCE),
        "upstream_manifest_sha256": sha256_file(repo_root / UPSTREAM_MANIFEST),
        "score_surface_sha256": sha256_file(repo_root / SCORE_SURFACE),
        "value_cells_sha256": sha256_file(repo_root / VALUE_CELLS),
        "s0_bundles_sha256": sha256_file(repo_root / S0_BUNDLES),
        "settlement_semantic_sha256": stable_frame_sha(settlement),
        "implementation_hashes": _implementation_hashes(repo_root),
    }
    return {
        "input_selections": inputs["selections"],
        "selections": protection["selections"],
        "preoutcome": protection["bundles"],
        "tickets": protection["tickets"],
        "decisions": protection["decisions"],
        "budget": protection["budget"],
        "settled_bundles": settled,
        "support_attribution": support_attribution,
        "performance": performance,
        "risk": risk,
        "paths": paths,
        "contrasts": contrasts,
        "protection_attribution": attribution,
        "rank_diagnostics": rank_diagnostics,
        "development_contrasts": development_contrasts,
        "selected_p": selected,
        "freeze_receipt": freeze_receipt,
        "source_receipt": source_receipt,
        "decision": decision,
    }


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False, lineterminator="\n", float_format="%.17g")


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def build_package(
    repo_root: Path,
    output: Path,
    data_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    data_root = locate_data_root(repo_root, data_root)
    frames = _scientific_frames(repo_root, data_root)

    def populate(staging: Path) -> None:
        parquet_names = (
            "input_selections",
            "selections",
            "preoutcome",
            "tickets",
            "decisions",
            "settled_bundles",
            "support_attribution",
            "paths",
        )
        csv_names = (
            "budget",
            "performance",
            "risk",
            "contrasts",
            "protection_attribution",
            "rank_diagnostics",
            "development_contrasts",
            "selected_p",
        )
        for name in parquet_names:
            _write_frame(staging / f"{name}.parquet", frames[name])
        for name in csv_names:
            _write_frame(staging / f"{name}.csv", frames[name])
        _write_json(staging / "freeze_receipt.json", frames["freeze_receipt"])
        _write_json(staging / "source_receipt.json", frames["source_receipt"])
        _write_json(staging / "decision.json", frames["decision"])

    atomic_publish_directory(output, populate, force=force)
    return frames["decision"]


def _report_text(output: Path) -> str:
    decision = json.loads((output / "decision.json").read_text())
    selected = pd.read_csv(output / "selected_p.csv")
    contrasts = pd.read_csv(output / "contrasts.csv")
    performance = pd.read_csv(output / "performance.csv")
    attribution = pd.read_csv(output / "protection_attribution.csv")
    rank_diagnostics = pd.read_csv(output / "rank_diagnostics.csv")
    development = pd.read_csv(output / "development_contrasts.csv")

    selected_rows: list[str] = []
    annual_rows: list[str] = []
    attribution_rows: list[str] = []
    for selection in selected.itertuples(index=False):
        result = next(
            row
            for row in decision["selected_p_results"]
            if row["lane"] == selection.lane and int(row["n"]) == int(selection.n)
        )
        selected_rows.append(
            f"| {selection.lane} | {int(selection.n)} | {int(selection.p)} | "
            f"{bool(selection.development_gate_pass)} | "
            f"{selection.development_lift_cny:,.0f} | "
            f"{result['transfer_lift_cny']:,.0f} | "
            f"{result['transfer_ex_largest_lift_cny']:,.0f} | "
            f"{result['bootstrap_mean_lift_p05_cny']:,.1f} |"
        )
        annual = contrasts[
            contrasts["lane"].eq(selection.lane)
            & contrasts["n"].eq(selection.n)
            & contrasts["p"].eq(selection.p)
            & contrasts["period"].isin(map(str, TRANSFER_YEARS))
        ].set_index("period")
        annual_rows.append(
            f"| {selection.lane} | {int(selection.n)} | {int(selection.p)} | "
            f"{annual.loc['2022', 'pnl_lift_cny']:,.0f} | "
            f"{annual.loc['2023', 'pnl_lift_cny']:,.0f} | "
            f"{annual.loc['2024', 'pnl_lift_cny']:,.0f} |"
        )
        attr = attribution[
            attribution["lane"].eq(selection.lane)
            & attribution["n"].eq(selection.n)
            & attribution["p"].eq(selection.p)
            & attribution["period"].eq("ALL_2022_2024")
        ].iloc[0]
        attribution_rows.append(
            f"| {selection.lane} | {int(selection.n)} | {int(selection.p)} | "
            f"{int(attr.baseline_one_miss_issues)} | "
            f"{int(attr.salvaged_one_miss_issues)} | "
            f"{int(attr.salvaged_two_plus_miss_issues)} | "
            f"{attr.salvage_gross_cny:,.0f} | "
            f"{attr.incumbent_hit_dilution_cny:,.0f} |"
        )

    curve = contrasts[contrasts["period"].eq("ALL_2022_2024")].sort_values(
        ["lane", "n", "p"]
    )
    curve_rows = "\n".join(
        f"| {row.lane} | {int(row.n)} | {int(row.p)} | "
        f"{int(row.common_issues)} | {row.pnl_lift_cny:,.0f} | "
        f"{row.hit_rate_lift:+.2%} | {row.armwise_ex_largest_pnl_lift_cny:,.0f} | "
        f"{row.candidate_max_drawdown_fraction:.2%} | "
        f"{int(row.candidate_longest_losing_run)} |"
        for row in curve.itertuples(index=False)
    )
    absolute = performance[performance["period"].eq("ALL_2022_2024")].sort_values(
        ["lane", "n", "p"]
    )
    absolute_rows = "\n".join(
        f"| {row.lane} | {int(row.n)} | {int(row.p)} | "
        f"{int(row.bet_issues)} | {row.pnl_cny:,.0f} | "
        f"{row.ending_capital_cny:,.0f} | {row.stake_roi:.2%} | "
        f"{row.hit_rate_per_bet:.2%} | {row.largest_payout_share:.2%} |"
        for row in absolute.itertuples(index=False)
    )
    development_curve = development[
        development["period"].eq("ALL_2019_2021")
    ].sort_values(["lane", "n", "p"])
    development_rows = "\n".join(
        f"| {row.lane} | {int(row.n)} | {int(row.p)} | "
        f"{row.pnl_lift_cny:,.0f} | "
        f"{row.armwise_ex_largest_pnl_lift_cny:,.0f} | "
        f"{row.bootstrap_mean_lift_p05_cny:,.1f} | "
        f"{row.candidate_max_drawdown_fraction:.2%} | "
        f"{int(row.candidate_longest_losing_run)} |"
        for row in development_curve.itertuples(index=False)
    )
    rank_rows = "\n".join(
        f"| {row.lane} | {int(row.n)} | {int(row.protection_rank)} | "
        f"{int(row.evaluated_fixtures)} | "
        f"{row.predicted_top2_miss_rate:.2%} | "
        f"{row.observed_top2_miss_rate:.2%} | "
        f"{row.calibration_error:+.2%} |"
        for row in rank_diagnostics[
            rank_diagnostics["period"].eq("ALL_2022_2024")
            & rank_diagnostics["lane"].str.startswith("S0_")
        ]
        .sort_values(["n", "protection_rank"])
        .itertuples(index=False)
    )
    return f"""# Issue #356 — low-N selective third-outcome protection

## Decision

- Verdict: **{decision["verdict"]}**.
- The primary decision uses only the exact S0 lane. N3/N4 #359 signal lanes are exposed-history interaction diagnostics.
- No row authorizes deployment, changes #210/#218, or replaces any upstream selector.

## Frozen experiment

For each already-selected N3/N4/N5 match set, P=0 keeps Top-2 and P>0 appends the omitted outcome to the P fixtures with the largest strictly-prior predicted Top-2 miss probability. All `2^(N-P) * 3^P` tickets are generated. Every BET issue retains exactly 512 CNY2 units / CNY1,024 exposure; units differ by at most one when K does not divide 512. The 0.65 factor is applied once per complete winning ticket.

2019–2021 select one fixed P per lane/N. 2022–2024 are exposed historical transfer evidence only. The issue, not tickets or legs, is the independent unit.

## Development-frozen P and transfer result

| Lane | N | P* | Development gate | Development lift | Transfer lift | Transfer ex-largest | Bootstrap mean p05 |
|---|---:|---:|---|---:|---:|---:|---:|
{chr(10).join(selected_rows)}

## Annual transfer lift of frozen P*

| Lane | N | P* | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(annual_rows)}

## Protection attribution for frozen P*

| Lane | N | P* | Baseline one-miss | One-miss salvaged | Two-plus salvaged | Salvage gross | Incumbent-hit dilution |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(attribution_rows)}

`salvage gross` is the payout recovered when P0 lost but protected support hit. `incumbent-hit dilution` is the gross change on issues P0 already won; it is normally negative because the fixed budget is spread across more tickets. Their balance is the economic mechanism under test.

## Scientific interpretation

- Protection raises ticket-hit frequency monotonically, but every primary P>0 arm loses capital versus its matched P0 baseline in 2022–2024. Recovered payouts do not pay for the dilution of already-winning Top-2 tickets.
- The development-selected depths do not transfer: N3/P2, N4/P3 and N5/P5 pass the frozen 2019–2021 gate, then lose CNY19.9k, CNY17.0k and CNY39.0k versus P0. This is a direct instability result, not a deployable dynamic-P signal.
- Shallow P2 is the least harmful transfer compromise for N4/N5 (CNY-3.5k/CNY-1.4k), but both remain negative after removing the largest payout and neither improves the complete risk profile. This is descriptive evidence only.
- Full protection reaches a 100% support-hit rate but converges toward the ticket-level 0.65 drag: transfer stake ROI is roughly -32% to -36%. Higher hit rate is therefore not equivalent to better capital performance.
- The frozen protection ranking itself fails to order realized miss risk monotonically on transfer. In all three S0 lanes, rank 1 has the highest predicted miss probability but a lower realized miss rate than rank 2. That reversal helps explain why selective insurance is economically inefficient.

## Development P curve (selection evidence only)

| Lane | N | P | Lift vs P0 | Ex-largest lift | Bootstrap mean p05 | Max DD | Longest loss |
|---|---:|---:|---:|---:|---:|---:|---:|
{development_rows}

The development table is shown to expose selection pressure. It must not be pooled with 2022–2024 or used to reselect P after transfer outcomes are known.

## Transfer calibration of the protection rank (primary S0)

| Lane | N | Rank | Fixtures | Predicted Top-2 miss | Observed Top-2 miss | Calibration error |
|---|---:|---:|---:|---:|---:|---:|
{rank_rows}

## Complete 2022–2024 matched P curve

| Lane | N | P | Common issues | Lift vs P0 | Hit-rate lift | Armwise ex-largest | Max DD | Longest loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{curve_rows}

## Absolute 2022–2024 strategy paths

| Lane | N | P | Bet issues | PnL | Ending capital | Stake ROI | Hit rate | Largest payout share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{absolute_rows}

## Evidence boundary

The protection ranking is frozen before settlement and uses the retrospective-relative 10h probability lineage. It is suitable for historical hypothesis generation, not an actual-time causal or deployable claim. Completed recoveries are counted only after a genuine underwater episode; terminal underwater duration is separately censored. Full package, attribution, deterministic ticket ledger, source receipts and exact replay are committed under `results/low_n_third_outcome_protection/`.
"""


def write_analysis(repo_root: Path, output: Path) -> list[Path]:
    import matplotlib.pyplot as plt
    import nbformat
    from nbclient import NotebookClient

    contrasts = pd.read_csv(output / "contrasts.csv")
    paths = pd.read_parquet(output / "paths.parquet")
    selected = pd.read_csv(output / "selected_p.csv")
    report = repo_root / "docs/research/Issue-356-LowN-Third-Outcome-Protection.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_report_text(output), encoding="utf-8")

    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    capital_figure = figure_dir / "issue_356_selected_capital.png"
    curve_figure = figure_dir / "issue_356_protection_curve.png"

    fig, axes = plt.subplots(3, 2, figsize=(15, 13), sharey=False)
    for axis, selection in zip(
        axes.flat, selected.itertuples(index=False), strict=False
    ):
        lane_paths = paths[
            paths["lane"].eq(selection.lane)
            & paths["n"].eq(selection.n)
            & paths["period"].eq("ALL_2022_2024")
            & paths["p"].isin([0, selection.p])
        ]
        for p, group in lane_paths.groupby("p", observed=True):
            axis.plot(group["path_index"], group["capital_cny"], label=f"P{int(p)}")
        axis.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8)
        axis.set_title(f"{selection.lane} / N{int(selection.n)}")
        axis.set_xlabel("Issue")
        axis.set_ylabel("Capital (CNY)")
        axis.grid(alpha=0.25)
        axis.legend()
    for axis in axes.flat[len(selected) :]:
        axis.axis("off")
    fig.tight_layout()
    fig.savefig(capital_figure, dpi=180)
    plt.close(fig)

    transfer = contrasts[contrasts["period"].eq("ALL_2022_2024")]
    fig, axes = plt.subplots(3, 2, figsize=(15, 13))
    for axis, ((lane, n), group) in zip(
        axes.flat, transfer.groupby(["lane", "n"], observed=True), strict=False
    ):
        group = group.sort_values("p")
        axis.plot(group["p"], group["pnl_lift_cny"], marker="o", label="PnL lift")
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_title(f"{lane} / N{int(n)}")
        axis.set_xlabel("Protection depth P")
        axis.set_ylabel("Matched lift vs P0 (CNY)")
        axis.grid(alpha=0.25)
    for axis in axes.flat[transfer.groupby(["lane", "n"], observed=True).ngroups :]:
        axis.axis("off")
    fig.tight_layout()
    fig.savefig(curve_figure, dpi=180)
    plt.close(fig)

    notebook_path = (
        repo_root
        / "notebooks/research/low-n-third-outcome-protection/low_n_third_outcome_protection.ipynb"
    )
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                "# Issue #356 — selective third-outcome protection\n\n"
                "Executed decision notebook. P is frozen on 2019–2021; 2022–2024 are exposed transfer."
            ),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\nimport json\nimport pandas as pd\n"
                "repo = Path.cwd()\noutput = repo / 'results/low_n_third_outcome_protection'\n"
                "decision = json.loads((output / 'decision.json').read_text())\n"
                "selected = pd.read_csv(output / 'selected_p.csv')\n"
                "performance = pd.read_csv(output / 'performance.csv')\n"
                "contrasts = pd.read_csv(output / 'contrasts.csv')\n"
                "risk = pd.read_csv(output / 'risk.csv')\n"
                "attribution = pd.read_csv(output / 'protection_attribution.csv')\n"
                "rank_diagnostics = pd.read_csv(output / 'rank_diagnostics.csv')\n"
                "development = pd.read_csv(output / 'development_contrasts.csv')\n"
                "decision"
            ),
            nbformat.v4.new_code_cell("selected"),
            nbformat.v4.new_code_cell(
                "development[development.period.eq('ALL_2019_2021')].sort_values(['lane','n','p'])"
            ),
            nbformat.v4.new_code_cell(
                "contrasts[contrasts.period.eq('ALL_2022_2024')].sort_values(['lane','n','p'])"
            ),
            nbformat.v4.new_code_cell(
                "performance[performance.period.eq('ALL_2022_2024')].sort_values(['lane','n','p'])"
            ),
            nbformat.v4.new_code_cell(
                "risk[risk.period.eq('ALL_2022_2024')].sort_values(['lane','n','p'])"
            ),
            nbformat.v4.new_code_cell(
                "attribution[attribution.period.eq('ALL_2022_2024')].sort_values(['lane','n','p'])"
            ),
            nbformat.v4.new_code_cell(
                "rank_diagnostics[rank_diagnostics.period.eq('ALL_2022_2024')].sort_values(['lane','n','protection_rank'])"
            ),
        ]
    )
    notebook.metadata.kernelspec = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    NotebookClient(notebook, timeout=600, kernel_name="python3").execute(cwd=repo_root)
    nbformat.write(notebook, notebook_path)
    return [report, notebook_path, capital_figure, curve_figure]


def _assert_frame(
    actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str]
) -> None:
    actual = actual.sort_values(keys, kind="stable").reset_index(drop=True)
    expected = expected.sort_values(keys, kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(
        actual,
        expected,
        check_dtype=False,
        check_exact=False,
        rtol=0,
        atol=1e-9,
    )


def finalize_manifest(repo_root: Path, output: Path, delivery: list[Path]) -> None:
    receipt = {str(path.relative_to(repo_root)): sha256_file(path) for path in delivery}
    _write_json(output / "delivery_receipt.json", receipt)
    files = {
        str(path.relative_to(output)): sha256_file(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }
    _write_json(output / "MANIFEST.json", {"contract": CONTRACT_ID, "files": files})


def verify_package(
    repo_root: Path, output: Path, data_root: Path | None = None
) -> dict[str, bool]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    data_root = locate_data_root(repo_root, data_root)
    manifest = json.loads((output / "MANIFEST.json").read_text())
    actual_files = {
        str(path.relative_to(output))
        for path in output.rglob("*")
        if path.is_file() and path.name != "MANIFEST.json"
    }
    if not actual_files or set(manifest.get("files", {})) != actual_files:
        raise AssertionError("package manifest inventory is incomplete")
    if not all(
        sha256_file(output / relative) == digest
        for relative, digest in manifest["files"].items()
    ):
        raise AssertionError("package manifest hashes do not match")
    expected = _scientific_frames(repo_root, data_root)
    for name in ("freeze_receipt", "source_receipt", "decision"):
        if json.loads((output / f"{name}.json").read_text()) != expected[name]:
            raise AssertionError(f"{name} does not replay")
    parquet = {
        "input_selections": ["issue", "lane", "n", "match_idx"],
        "selections": ["issue", "lane", "n", "p", "match_idx"],
        "preoutcome": ["issue", "lane", "n", "p"],
        "tickets": ["issue", "lane", "n", "p", "ticket_index"],
        "decisions": ["issue", "lane", "n", "p"],
        "settled_bundles": ["issue", "lane", "n", "p"],
        "support_attribution": ["issue", "lane", "n", "p", "match_idx"],
        "paths": ["lane", "n", "p", "period", "path_index"],
    }
    csv = {
        "budget": ["issue", "lane", "n", "p"],
        "performance": ["lane", "n", "p", "period"],
        "risk": ["lane", "n", "p", "period"],
        "contrasts": ["lane", "n", "p", "period"],
        "protection_attribution": ["lane", "n", "p", "period"],
        "rank_diagnostics": ["lane", "n", "protection_rank", "period"],
        "development_contrasts": ["lane", "n", "p", "period"],
        "selected_p": ["lane", "n"],
    }
    for name, keys in parquet.items():
        _assert_frame(pd.read_parquet(output / f"{name}.parquet"), expected[name], keys)
    for name, keys in csv.items():
        dtype = {"issue": "string"} if "issue" in expected[name].columns else None
        _assert_frame(
            pd.read_csv(output / f"{name}.csv", dtype=dtype), expected[name], keys
        )
    delivery = json.loads((output / "delivery_receipt.json").read_text())
    if not delivery or not all(
        (repo_root / relative).is_file() and sha256_file(repo_root / relative) == digest
        for relative, digest in delivery.items()
    ):
        raise AssertionError("delivery artifacts are missing or stale")
    return {
        "manifest": True,
        "source_bound_replay": True,
        "strict_temporal_freeze": True,
        "upstream_lane_parity": True,
        "full_cartesian_support": True,
        "exact_budget": True,
        "ticket_level_once_65": True,
        "settlement_replay": True,
        "risk_semantics": True,
        "decision_replay": True,
        "delivery_artifacts": True,
    }
