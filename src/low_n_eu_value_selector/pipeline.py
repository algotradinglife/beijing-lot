"""Low-N coverage × European-value × separation factorial for Issue #359."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from nbclient import NotebookClient

from src.low_n_match_selector.pipeline import (
    _load_settlement,
    locate_data_root,
    settle,
)
from src.source_schema.publication import atomic_publish_directory

from .contract import (
    ARMS,
    BASELINE_ARM,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    COMPLETE_TICKET_RETURN_FLOOR,
    CONTRACT_ID,
    COVERAGE_DIAGNOSTIC_ARM,
    COVERAGE_QUANTILES,
    DEVELOPMENT_YEARS,
    FUNDED_UNITS,
    GAP_QUANTILES,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    LABEL_RELATIVE,
    MIN_DEVELOPMENT_BET_COVERAGE,
    N_VALUES,
    OUTCOMES,
    PAYOUT_FACTOR,
    SCORE_SURFACE_RELATIVE,
    S0_BUNDLES_RELATIVE,
    S0_FREEZE_RELATIVE,
    STAKE_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TRANSFER_YEARS,
    VALUE_CELLS_RELATIVE,
    VALUE_FREEZE_RELATIVE,
    VALUE_LEG_FLOORS,
    VALUE_SOURCE_RELATIVE,
)


class ContractError(ValueError):
    """Raised when the frozen Issue #359 semantics are violated."""


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


def _arm_bits(arm: str) -> tuple[int, int, int]:
    if arm not in ARMS:
        raise ContractError(f"unknown factorial arm: {arm}")
    return int(arm[1]), int(arm[3]), int(arm[5])


def _strict_bool(series: pd.Series, name: str) -> None:
    if not pd.api.types.is_bool_dtype(series.dtype):
        raise ContractError(f"{name} must be a strict boolean")


def load_fixture_surface(repo_root: Path) -> pd.DataFrame:
    """Join #358 cells to the two frozen #355 ranking surfaces."""

    value_path = repo_root / VALUE_CELLS_RELATIVE
    values = pq.read_table(value_path).to_pandas()
    required = {
        "issue",
        "issue_year",
        "issue_anchor_ts",
        "match_idx",
        "outcome_code",
        "outcome_order",
        "calibrated_probability",
        "top2_support",
        "top2_included",
        "top2_coverage_reliability",
        "top2_expected_return_per_stake_factor",
        "contributing_bookmaker_count",
        "source_horizon",
        "source_time_status",
        "quality_grade",
        "missingness_reason",
    }
    missing = required - set(values.columns)
    if missing:
        raise ContractError(f"#358 value cells missing columns: {sorted(missing)}")
    _strict_bool(values["top2_included"], "top2_included")
    values["issue"] = values["issue"].astype(str)
    values["outcome_code"] = values["outcome_code"].astype(str)
    values["issue_anchor_ts"] = pd.to_datetime(values["issue_anchor_ts"], utc=True)
    values = values.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx", "outcome_order"],
        kind="stable",
    )
    sizes = values.groupby(["issue", "match_idx"], observed=True).size()
    if not sizes.eq(3).all():
        raise ContractError("#358 fixture grain is not exactly M×3")
    outcome_sets = values.groupby(["issue", "match_idx"], observed=True)[
        "outcome_code"
    ].agg(lambda value: frozenset(value))
    if not outcome_sets.eq(frozenset(OUTCOMES)).all():
        raise ContractError("#358 fixtures do not contain canonical 3/1/0 outcomes")

    probabilities = values.pivot(
        index=["issue", "match_idx"],
        columns="outcome_code",
        values="calibrated_probability",
    ).rename(columns=lambda outcome: f"p_{outcome}")
    fixture = (
        values.groupby(["issue", "match_idx"], observed=True, sort=False)
        .first()
        .reset_index()
        .merge(probabilities.reset_index(), on=["issue", "match_idx"], validate="one_to_one")
    )
    probability_matrix = fixture[["p_3", "p_1", "p_0"]].to_numpy(float)
    if not np.isfinite(probability_matrix).all() or not np.allclose(
        probability_matrix.sum(axis=1), 1.0, rtol=0, atol=1e-12
    ):
        raise ContractError("calibrated probabilities are not finite simplexes")
    ordered = np.sort(probability_matrix, axis=1)[:, ::-1]
    fixture["top2_third_gap"] = ordered[:, 1] - ordered[:, 2]
    fixture = fixture.rename(
        columns={
            "top2_support": "baseline_support",
            "top2_expected_return_per_stake_factor": "value_factor",
            "top2_coverage_reliability": "retained_mass",
        }
    )
    fixture["source_quality_valid"] = (
        fixture["source_horizon"].eq("10h")
        & fixture["quality_grade"].eq("COMPLETE_VALID_10H_AVERAGE_EU_PROXY")
        & fixture["missingness_reason"].eq("COMPLETE")
        & fixture["contributing_bookmaker_count"].astype(int).gt(0)
    )
    _strict_bool(fixture["source_quality_valid"], "source_quality_valid")

    scores = pq.read_table(repo_root / SCORE_SURFACE_RELATIVE).to_pandas()
    scores["issue"] = scores["issue"].astype(str)
    pivot = scores.pivot(
        index=["issue", "issue_year", "issue_anchor_ts", "match_idx", "baseline_support"],
        columns="arm",
        values="selector_score",
    ).reset_index()
    required_arms = {"S0_RAW_MASS", "SELECTED_MODEL"}
    if not required_arms.issubset(pivot.columns):
        raise ContractError("#355 ranking surface lacks S0 or coverage diagnostic")
    pivot = pivot.rename(
        columns={"S0_RAW_MASS": "s0_score", "SELECTED_MODEL": "coverage_score"}
    )
    pivot["issue_anchor_ts"] = pd.to_datetime(pivot["issue_anchor_ts"], utc=True)
    joined = fixture.merge(
        pivot[
            [
                "issue",
                "issue_year",
                "issue_anchor_ts",
                "match_idx",
                "baseline_support",
                "s0_score",
                "coverage_score",
            ]
        ],
        on=["issue", "issue_year", "issue_anchor_ts", "match_idx", "baseline_support"],
        how="inner",
        validate="one_to_one",
    )
    expected_rows = (
        scores.loc[scores["arm"].eq("S0_RAW_MASS"), ["issue", "match_idx"]]
        .drop_duplicates()
        .sort_values(["issue", "match_idx"], kind="stable")
        .reset_index(drop=True)
    )
    actual_rows = (
        joined[["issue", "match_idx"]]
        .drop_duplicates()
        .sort_values(["issue", "match_idx"], kind="stable")
        .reset_index(drop=True)
    )
    if not actual_rows.equals(expected_rows):
        raise ContractError("#358 and #355 fixture universes are not exact-common")
    if not np.allclose(joined["s0_score"], joined["retained_mass"], rtol=0, atol=1e-12):
        raise ContractError("S0 score is not exact retained Top-2 mass")
    return joined.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def development_floors(surface: pd.DataFrame) -> pd.DataFrame:
    development = surface[surface["issue_year"].isin(DEVELOPMENT_YEARS)]
    rows: list[dict[str, Any]] = []
    for n in N_VALUES:
        for quantile in COVERAGE_QUANTILES:
            rows.append(
                {
                    "n": n,
                    "factor": "coverage",
                    "grid_key": float(quantile),
                    "floor": float(development["coverage_score"].quantile(quantile)),
                }
            )
        for floor in VALUE_LEG_FLOORS:
            rows.append(
                {"n": n, "factor": "value", "grid_key": float(floor), "floor": float(floor)}
            )
        for quantile in GAP_QUANTILES:
            rows.append(
                {
                    "n": n,
                    "factor": "gap",
                    "grid_key": float(quantile),
                    "floor": float(development["top2_third_gap"].quantile(quantile)),
                }
            )
    return pd.DataFrame(rows)


def _parameter_grid(floors: pd.DataFrame, n: int, arm: str) -> list[dict[str, Any]]:
    coverage_on, value_on, gap_on = _arm_bits(arm)
    lookup = floors[floors["n"].eq(n)]
    coverage = (
        lookup[lookup["factor"].eq("coverage")][["grid_key", "floor"]].to_dict("records")
        if coverage_on
        else [{"grid_key": -1.0, "floor": -math.inf}]
    )
    value = (
        lookup[lookup["factor"].eq("value")][["grid_key", "floor"]].to_dict("records")
        if value_on
        else [{"grid_key": -1.0, "floor": -math.inf}]
    )
    gap = (
        lookup[lookup["factor"].eq("gap")][["grid_key", "floor"]].to_dict("records")
        if gap_on
        else [{"grid_key": -1.0, "floor": -math.inf}]
    )
    parameters: list[dict[str, Any]] = []
    for c, v, g in itertools.product(coverage, value, gap):
        parameters.append(
            {
                "coverage_quantile": float(c["grid_key"]),
                "coverage_floor": float(c["floor"]),
                "value_leg_floor": float(v["floor"]),
                "gap_quantile": float(g["grid_key"]),
                "gap_floor": float(g["floor"]),
                "complete_ticket_return_floor": (
                    COMPLETE_TICKET_RETURN_FLOOR if value_on else -math.inf
                ),
            }
        )
    return parameters


def _parameter_key(parameter: dict[str, Any]) -> str:
    def value(key: str) -> str:
        raw = float(parameter[key])
        return "OFF" if not np.isfinite(raw) else f"{raw:.12g}"

    return "|".join(
        [
            f"CQ={value('coverage_quantile')}",
            f"CF={value('coverage_floor')}",
            f"VF={value('value_leg_floor')}",
            f"GQ={value('gap_quantile')}",
            f"GF={value('gap_floor')}",
            f"TF={value('complete_ticket_return_floor')}",
        ]
    )


def construct_preoutcome(
    surface: pd.DataFrame,
    n: int,
    arm: str,
    parameter: dict[str, Any],
    years: Iterable[int],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply a frozen arm to each issue without reading outcomes."""

    coverage_on, value_on, gap_on = _arm_bits(arm)
    subset = surface[surface["issue_year"].isin(tuple(years))].copy()
    selections: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    parameter_key = _parameter_key(parameter)
    for (issue, year, anchor), group in subset.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], observed=True, sort=True
    ):
        quality = group["source_quality_valid"]
        c_ok = group["coverage_score"].ge(parameter["coverage_floor"]) if coverage_on else True
        v_ok = group["value_factor"].ge(parameter["value_leg_floor"]) if value_on else True
        g_ok = group["top2_third_gap"].ge(parameter["gap_floor"]) if gap_on else True
        eligible = group[quality & c_ok & v_ok & g_ok].copy()
        ranking_column = "coverage_score" if coverage_on else "s0_score"
        ranked = eligible.sort_values(
            [ranking_column, "s0_score", "match_idx"],
            ascending=[False, False, True],
            kind="stable",
        )
        selected = ranked.head(n).sort_values("match_idx", kind="stable")
        full_return = (
            PAYOUT_FACTOR * float(np.prod(selected["value_factor"].to_numpy(float)))
            if len(selected) == n
            else math.nan
        )
        reason = "BET"
        if len(selected) < n:
            reason = "INSUFFICIENT_ELIGIBLE_FIXTURES"
        elif value_on and full_return < parameter["complete_ticket_return_floor"]:
            reason = "COMPLETE_TICKET_VALUE_FLOOR"
        bet = reason == "BET"
        decisions.append(
            {
                "issue": str(issue),
                "issue_year": int(year),
                "issue_anchor_ts": pd.Timestamp(anchor),
                "arm": arm,
                "n": n,
                "parameter_key": parameter_key,
                "decision": reason,
                "bet": bool(bet),
                "available_fixtures": int(len(group)),
                "quality_eligible": int(quality.sum()),
                "coverage_eligible": int((quality & c_ok).sum()),
                "value_eligible": int((quality & v_ok).sum()),
                "gap_eligible": int((quality & g_ok).sum()),
                "joint_eligible": int(len(eligible)),
                "complete_ticket_proxy_return": full_return,
            }
        )
        if not bet:
            continue
        ids = selected["match_idx"].astype(int).tolist()
        supports = selected["baseline_support"].astype(str).tolist()
        units = FUNDED_UNITS // (2**n)
        if units * (2**n) != FUNDED_UNITS:
            raise ContractError(f"N{n} ticket budget is not exact")
        for row in selected.itertuples(index=False):
            selections.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "issue_anchor_ts": pd.Timestamp(anchor),
                    "arm": arm,
                    "n": n,
                    "parameter_key": parameter_key,
                    "match_idx": int(row.match_idx),
                    "baseline_support": str(row.baseline_support),
                    "ranking_score": float(getattr(row, ranking_column)),
                    "s0_score": float(row.s0_score),
                    "coverage_score": float(row.coverage_score),
                    "value_factor": float(row.value_factor),
                    "top2_third_gap": float(row.top2_third_gap),
                }
            )
        bundle = {
            "issue": str(issue),
            "issue_year": int(year),
            "issue_anchor_ts": pd.Timestamp(anchor),
            "arm": arm,
            "n": n,
            "parameter_key": parameter_key,
            "selected_match_ids": "|".join(map(str, ids)),
            "support_json": json.dumps(
                dict(zip(map(str, ids), supports, strict=True)),
                sort_keys=True,
                separators=(",", ":"),
            ),
            "ticket_count": 2**n,
            "units_per_ticket": units,
            "planned_stake_cny": ISSUE_STAKE_CNY,
            "complete_ticket_proxy_return": full_return,
        }
        bundles.append(bundle)
        for ticket_index, choices in enumerate(itertools.product((0, 1), repeat=n)):
            legs = [
                f"{match_idx}={support[choice]}"
                for match_idx, support, choice in zip(ids, supports, choices, strict=True)
            ]
            tickets.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "arm": arm,
                    "n": n,
                    "parameter_key": parameter_key,
                    "ticket_index": ticket_index,
                    "ticket_key": "|".join(legs),
                    "units": units,
                    "stake_cny": units * STAKE_UNIT_CNY,
                }
            )
    return (
        pd.DataFrame(selections),
        pd.DataFrame(bundles),
        pd.DataFrame(tickets),
        pd.DataFrame(decisions),
    )


def _path_risk(pnl: np.ndarray) -> dict[str, Any]:
    equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
    peaks = np.maximum.accumulate(equity)
    peak = equity[0]
    peak_index = 0
    completed: list[int] = []
    for index, value in enumerate(equity[1:], start=1):
        if value >= peak:
            if index > peak_index:
                completed.append(index - peak_index)
            peak = value
            peak_index = index
    open_underwater = int(len(equity) - 1 - peak_index) if equity[-1] < peak else 0
    longest_losing = max(
        (
            sum(1 for _ in run)
            for is_loss, run in itertools.groupby(pnl < 0)
            if is_loss
        ),
        default=0,
    )
    return {
        "max_drawdown_cny": float((peaks - equity).max()),
        "max_drawdown_fraction": float(
            ((peaks - equity) / np.maximum(peaks, 1e-12)).max()
        ),
        "longest_losing_run": int(longest_losing),
        "completed_recovery_issues": int(max(completed, default=0)),
        "open_underwater_issues": open_underwater,
        "recovery_censored": bool(open_underwater > 0),
    }


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


def _policy_state(decisions: pd.DataFrame, settled_bundles: pd.DataFrame) -> pd.DataFrame:
    _strict_bool(decisions["bet"], "decisions.bet")
    settlement_columns = [
        "issue",
        "issue_year",
        "arm",
        "n",
        "settlement_status",
        "stake_cny",
        "gross_cny",
        "pnl_cny",
        "hit",
    ]
    state = decisions.merge(
        settled_bundles[settlement_columns],
        on=["issue", "issue_year", "arm", "n"],
        how="left",
        validate="one_to_one",
    )
    no_bet = state["decision"].ne("BET")
    state.loc[no_bet, "settlement_status"] = "NO_BET"
    state.loc[no_bet, ["stake_cny", "gross_cny", "pnl_cny"]] = 0.0
    state.loc[no_bet, "hit"] = False
    bet_missing = state["decision"].eq("BET") & state["settlement_status"].isna()
    if bet_missing.any():
        raise ContractError("BET decision has no settlement row")
    state["hit"] = state["hit"].astype(bool)
    _strict_bool(state["hit"], "policy_state.hit")
    return state.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "arm", "n"], kind="stable"
    ).reset_index(drop=True)


def _grid_diagnostic(
    baseline_state: pd.DataFrame,
    candidate_state: pd.DataFrame,
    arm: str,
    n: int,
    parameter: dict[str, Any],
) -> dict[str, Any]:
    reference = baseline_state[baseline_state["n"].eq(n)].copy()
    candidate = candidate_state[candidate_state["n"].eq(n)].copy()
    paired = reference.merge(
        candidate,
        on=["issue", "issue_year", "n"],
        suffixes=("_s0", "_candidate"),
        validate="one_to_one",
    )
    paired = paired[
        paired["settlement_status_s0"].isin(["SETTLED", "NO_BET"])
        & paired["settlement_status_candidate"].isin(["SETTLED", "NO_BET"])
    ].copy()
    if paired.empty:
        return {
            "arm": arm,
            "n": n,
            "parameter_key": _parameter_key(parameter),
            "eligible_for_selection": False,
            "positive_years": 0,
            "bet_coverage": 0.0,
            "pnl_lift_cny": -math.inf,
            "ex_largest_abs_delta_lift_cny": -math.inf,
            "max_drawdown_fraction": math.inf,
        }
    delta = paired["pnl_cny_candidate"].to_numpy(float) - paired["pnl_cny_s0"].to_numpy(float)
    annual = paired.assign(delta=delta).groupby("issue_year", observed=True)["delta"].sum()
    largest = int(np.argmax(np.abs(delta)))
    risk = _path_risk(paired["pnl_cny_candidate"].to_numpy(float))
    bet_coverage = float(candidate["decision"].eq("BET").mean())
    return {
        "arm": arm,
        "n": n,
        "parameter_key": _parameter_key(parameter),
        "coverage_quantile": parameter["coverage_quantile"],
        "coverage_floor": parameter["coverage_floor"],
        "value_leg_floor": parameter["value_leg_floor"],
        "gap_quantile": parameter["gap_quantile"],
        "gap_floor": parameter["gap_floor"],
        "complete_ticket_return_floor": parameter["complete_ticket_return_floor"],
        "common_issues": int(len(paired)),
        "bet_coverage": bet_coverage,
        "positive_years": int((annual > 0).sum()),
        "pnl_lift_cny": float(delta.sum()),
        "ex_largest_abs_delta_lift_cny": float(delta.sum() - delta[largest]),
        "max_drawdown_fraction": risk["max_drawdown_fraction"],
        "eligible_for_selection": bool(bet_coverage >= MIN_DEVELOPMENT_BET_COVERAGE),
    }


def select_development_parameters(
    surface: pd.DataFrame,
    floors: pd.DataFrame,
    settlement: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[tuple[str, int], dict[str, Any]]]:
    """Select one fixed parameter set per N/arm using 2019–2021 only."""

    baseline_parameter = _parameter_grid(floors, N_VALUES[0], BASELINE_ARM)[0]
    baseline_parts = [
        construct_preoutcome(
            surface, n, BASELINE_ARM, baseline_parameter, DEVELOPMENT_YEARS
        )
        for n in N_VALUES
    ]
    baseline_bundles = pd.concat([part[1] for part in baseline_parts], ignore_index=True)
    baseline_decisions = pd.concat([part[3] for part in baseline_parts], ignore_index=True)
    baseline_settled, _ = settle(baseline_bundles, settlement)
    baseline_state = _policy_state(baseline_decisions, baseline_settled)

    diagnostics: list[dict[str, Any]] = []
    selected: dict[tuple[str, int], dict[str, Any]] = {}
    for n in N_VALUES:
        for arm in ARMS:
            rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for parameter in _parameter_grid(floors, n, arm):
                _, bundles, _, decisions = construct_preoutcome(
                    surface, n, arm, parameter, DEVELOPMENT_YEARS
                )
                settled, _ = settle(bundles, settlement) if not bundles.empty else (
                    pd.DataFrame(columns=["issue", "issue_year", "arm", "n", "settlement_status", "stake_cny", "gross_cny", "pnl_cny", "hit"]),
                    pd.DataFrame(),
                )
                state = _policy_state(decisions, settled)
                diagnostic = _grid_diagnostic(
                    baseline_state, state, arm, n, parameter
                )
                diagnostics.append(diagnostic)
                rows.append((diagnostic, parameter))
            eligible = [row for row in rows if row[0]["eligible_for_selection"]]
            choices = eligible or rows
            best = max(
                choices,
                key=lambda row: (
                    row[0]["positive_years"],
                    row[0]["ex_largest_abs_delta_lift_cny"] > 0,
                    row[0]["ex_largest_abs_delta_lift_cny"],
                    row[0]["pnl_lift_cny"],
                    -row[0]["max_drawdown_fraction"],
                    row[0]["bet_coverage"],
                    row[0]["parameter_key"],
                ),
            )
            selected[(arm, n)] = best[1]
    diagnostic_frame = pd.DataFrame(diagnostics)
    diagnostic_frame["selected"] = diagnostic_frame.apply(
        lambda row: row["parameter_key"]
        == _parameter_key(selected[(str(row["arm"]), int(row["n"]))]),
        axis=1,
    )
    _strict_bool(diagnostic_frame["eligible_for_selection"], "eligible_for_selection")
    _strict_bool(diagnostic_frame["selected"], "selected")
    return diagnostic_frame, selected


def construct_selected_policy(
    surface: pd.DataFrame,
    selected: dict[tuple[str, int], dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pieces = []
    years = (*DEVELOPMENT_YEARS, *TRANSFER_YEARS)
    for n in N_VALUES:
        for arm in ARMS:
            pieces.append(construct_preoutcome(surface, n, arm, selected[(arm, n)], years))
    return tuple(
        pd.concat([piece[index] for piece in pieces], ignore_index=True)
        for index in range(4)
    )  # type: ignore[return-value]


def evaluate(
    decisions: pd.DataFrame,
    settled_bundles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    state = _policy_state(decisions, settled_bundles)
    performance_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    for (arm, n), frame in state.groupby(["arm", "n"], observed=True, sort=True):
        for period, group in _periods(frame):
            group = group[
                group["settlement_status"].isin(["SETTLED", "NO_BET"])
            ].sort_values(["issue_anchor_ts", "issue"], kind="stable")
            if group.empty:
                continue
            pnl = group["pnl_cny"].to_numpy(float)
            gross = group["gross_cny"].to_numpy(float)
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            payouts = gross[gross > 0]
            weights = payouts / payouts.sum() if len(payouts) else np.array([])
            settled_bets = group[group["settlement_status"].eq("SETTLED")]
            performance_rows.append(
                {
                    "arm": arm,
                    "n": int(n),
                    "period": period,
                    "evaluable_issues": int(len(group)),
                    "bet_issues": int(group["decision"].eq("BET").sum()),
                    "no_bet_issues": int(group["decision"].ne("BET").sum()),
                    "bet_coverage": float(group["decision"].eq("BET").mean()),
                    "stake_cny": float(group["stake_cny"].sum()),
                    "gross_cny": float(gross.sum()),
                    "pnl_cny": float(pnl.sum()),
                    "ending_capital_cny": float(capital[-1]),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum())
                    if group["stake_cny"].sum()
                    else math.nan,
                    "hit_rate_per_bet": float(settled_bets["hit"].mean())
                    if len(settled_bets)
                    else math.nan,
                    "largest_payout_share": float(payouts.max() / payouts.sum())
                    if len(payouts)
                    else 0.0,
                    "payout_hhi": float(np.square(weights).sum()) if len(weights) else 0.0,
                }
            )
            risk_rows.append({"arm": arm, "n": int(n), "period": period, **_path_risk(pnl)})
            for index, row in enumerate(group.itertuples(index=False), start=1):
                path_rows.append(
                    {
                        "arm": arm,
                        "n": int(n),
                        "period": period,
                        "path_index": index,
                        "issue": str(row.issue),
                        "issue_year": int(row.issue_year),
                        "decision": str(row.decision),
                        "pnl_cny": float(row.pnl_cny),
                        "capital_cny": float(capital[index - 1]),
                    }
                )

    contrast_rows: list[dict[str, Any]] = []
    for n in N_VALUES:
        for reference_arm in (BASELINE_ARM, COVERAGE_DIAGNOSTIC_ARM):
            reference = state[(state["arm"].eq(reference_arm)) & state["n"].eq(n)]
            for arm in ARMS:
                candidate = state[(state["arm"].eq(arm)) & state["n"].eq(n)]
                paired = reference.merge(
                    candidate,
                    on=["issue", "issue_year", "n"],
                    suffixes=("_reference", "_candidate"),
                    validate="one_to_one",
                )
                paired = paired[
                    paired["settlement_status_reference"].isin(["SETTLED", "NO_BET"])
                    & paired["settlement_status_candidate"].isin(["SETTLED", "NO_BET"])
                ].copy()
                for period, group in _periods(paired):
                    group = group.sort_values(
                        ["issue_anchor_ts_reference", "issue"], kind="stable"
                    )
                    if group.empty:
                        continue
                    ref_pnl = group["pnl_cny_reference"].to_numpy(float)
                    candidate_pnl = group["pnl_cny_candidate"].to_numpy(float)
                    delta = candidate_pnl - ref_pnl
                    largest_delta = int(np.argmax(np.abs(delta)))
                    reference_gross = group["gross_cny_reference"].to_numpy(float)
                    candidate_gross = group["gross_cny_candidate"].to_numpy(float)
                    ex_reference = ref_pnl.sum() - ref_pnl[int(np.argmax(reference_gross))]
                    ex_candidate = candidate_pnl.sum() - candidate_pnl[int(np.argmax(candidate_gross))]
                    rng = np.random.default_rng(
                        BOOTSTRAP_SEED
                        + n * 10_000
                        + sum(map(ord, arm + reference_arm + period))
                    )
                    draws = rng.choice(
                        delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True
                    ).mean(axis=1)
                    contrast_rows.append(
                        {
                            "reference_arm": reference_arm,
                            "candidate_arm": arm,
                            "n": n,
                            "period": period,
                            "common_issues": int(len(group)),
                            "reference_pnl_cny": float(ref_pnl.sum()),
                            "candidate_pnl_cny": float(candidate_pnl.sum()),
                            "pnl_lift_cny": float(delta.sum()),
                            "mean_pnl_lift_cny": float(delta.mean()),
                            "hit_rate_lift": float(
                                group.loc[group["decision_candidate"].eq("BET"), "hit_candidate"].mean()
                                - group.loc[group["decision_reference"].eq("BET"), "hit_reference"].mean()
                            ),
                            "armwise_ex_largest_pnl_lift_cny": float(ex_candidate - ex_reference),
                            "ex_largest_abs_delta_pnl_lift_cny": float(
                                delta.sum() - delta[largest_delta]
                            ),
                            "largest_abs_paired_delta_cny": float(abs(delta[largest_delta])),
                            "bootstrap_mean_lift_p05_cny": float(np.quantile(draws, 0.05)),
                            "bootstrap_mean_lift_p50_cny": float(np.quantile(draws, 0.50)),
                            "bootstrap_mean_lift_p95_cny": float(np.quantile(draws, 0.95)),
                            **{
                                f"reference_{key}": value
                                for key, value in _path_risk(ref_pnl).items()
                            },
                            **{
                                f"candidate_{key}": value
                                for key, value in _path_risk(candidate_pnl).items()
                            },
                        }
                    )

    factorial_rows: list[dict[str, Any]] = []
    evaluable = state[state["settlement_status"].isin(["SETTLED", "NO_BET"])].copy()
    pivot = evaluable.pivot_table(
        index=["issue", "issue_year", "n"],
        columns="arm",
        values="pnl_cny",
        aggfunc="first",
        observed=True,
    ).dropna(subset=list(ARMS)).reset_index()
    effects = {
        "C": (0,),
        "V": (1,),
        "G": (2,),
        "CV": (0, 1),
        "CG": (0, 2),
        "VG": (1, 2),
        "CVG": (0, 1, 2),
    }
    for n, frame in pivot.groupby("n", observed=True):
        for period, group in _periods(frame):
            if group.empty:
                continue
            for effect, indices in effects.items():
                issue_effect = np.zeros(len(group), dtype=float)
                for arm in ARMS:
                    bits = _arm_bits(arm)
                    sign = math.prod(1 if bits[index] else -1 for index in indices)
                    issue_effect += sign * group[arm].to_numpy(float) / 4.0
                factorial_rows.append(
                    {
                        "n": int(n),
                        "period": period,
                        "effect": effect,
                        "issues": int(len(group)),
                        "mean_effect_cny_per_issue": float(issue_effect.mean()),
                        "total_effect_cny": float(issue_effect.sum()),
                    }
                )
    return (
        pd.DataFrame(performance_rows),
        pd.DataFrame(risk_rows),
        pd.DataFrame(path_rows),
        pd.DataFrame(contrast_rows),
        pd.DataFrame(factorial_rows),
    )


def selection_evidence(selections: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    labels = labels.copy()
    labels["issue"] = labels["issue"].astype(str)
    _strict_bool(labels["label_available"], "label_available")
    _strict_bool(labels["top2_hit"], "top2_hit")
    joined = selections.merge(
        labels[["issue", "match_idx", "label_available", "top2_hit"]],
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    joined = joined[joined["label_available"].eq(True)].copy()
    rows: list[dict[str, Any]] = []
    for (arm, n), frame in joined.groupby(["arm", "n"], observed=True, sort=True):
        for period, group in _periods(frame):
            if group.empty:
                continue
            issue_hit = group.groupby("issue", observed=True)["top2_hit"].all()
            rows.append(
                {
                    "arm": arm,
                    "n": int(n),
                    "period": period,
                    "selected_match_rows": int(len(group)),
                    "bet_issues": int(group["issue"].nunique()),
                    "match_top2_hit_rate": float(group["top2_hit"].mean()),
                    "issue_top2_hit_rate": float(issue_hit.mean()),
                    "mean_selected_value_factor": float(group["value_factor"].mean()),
                    "mean_selected_gap": float(group["top2_third_gap"].mean()),
                }
            )
    return pd.DataFrame(rows)


def _implementation_hashes(repo_root: Path) -> dict[str, str]:
    relatives = (
        "src/low_n_eu_value_selector/__init__.py",
        "src/low_n_eu_value_selector/contract.py",
        "src/low_n_eu_value_selector/pipeline.py",
        "scripts/run_low_n_eu_value_selector.py",
        "scripts/verify_low_n_eu_value_selector.py",
        "scripts/build_low_n_eu_value_selector_notebook.py",
        "tests/test_low_n_eu_value_selector.py",
        "src/low_n_match_selector/pipeline.py",
    )
    return {relative: sha256_file(repo_root / relative) for relative in relatives}


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False, lineterminator="\n", float_format="%.17g")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _selected_receipt(selected: dict[tuple[str, int], dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"arm": arm, "n": n, "parameter_key": _parameter_key(parameter), **parameter}
        for (arm, n), parameter in sorted(selected.items())
    ]


def _decision(performance: pd.DataFrame, contrasts: pd.DataFrame) -> dict[str, Any]:
    transfer = contrasts[
        contrasts["reference_arm"].eq(BASELINE_ARM)
        & contrasts["period"].eq("ALL_2022_2024")
        & contrasts["candidate_arm"].ne(BASELINE_ARM)
    ].copy()
    annual = contrasts[
        contrasts["reference_arm"].eq(BASELINE_ARM)
        & contrasts["period"].isin(map(str, TRANSFER_YEARS))
    ]
    candidates: list[dict[str, Any]] = []
    for row in transfer.itertuples(index=False):
        yearly = annual[
            annual["candidate_arm"].eq(row.candidate_arm) & annual["n"].eq(row.n)
        ]
        positive_years = int((yearly["pnl_lift_cny"] > 0).sum())
        path_ok = bool(
            row.candidate_max_drawdown_fraction
            <= row.reference_max_drawdown_fraction + 0.05
            and row.candidate_longest_losing_run
            <= row.reference_longest_losing_run + 3
        )
        passed = bool(
            row.pnl_lift_cny > 0
            and positive_years >= 2
            and row.armwise_ex_largest_pnl_lift_cny > 0
            and path_ok
        )
        candidates.append(
            {
                "arm": row.candidate_arm,
                "n": int(row.n),
                "all_transfer_lift_cny": float(row.pnl_lift_cny),
                "positive_transfer_years": positive_years,
                "armwise_ex_largest_lift_cny": float(
                    row.armwise_ex_largest_pnl_lift_cny
                ),
                "path_risk_gate": path_ok,
                "historical_signal": passed,
            }
        )
    passing = [candidate for candidate in candidates if candidate["historical_signal"]]
    best = max(
        passing or candidates,
        key=lambda row: (
            row["historical_signal"],
            row["positive_transfer_years"],
            row["armwise_ex_largest_lift_cny"],
            row["all_transfer_lift_cny"],
        ),
        default=None,
    )
    return {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "baseline": BASELINE_ARM,
        "coverage_diagnostic": COVERAGE_DIAGNOSTIC_ARM,
        "historical_candidates": candidates,
        "best_observed_candidate": best,
        "verdict": "HISTORICAL_SIGNAL" if passing else "NO_PROMOTION",
        "production_or_holdout_authorized": False,
        "changes_210_or_218": False,
    }


def _scientific_frames(repo_root: Path, data_root: Path) -> dict[str, Any]:
    surface = load_fixture_surface(repo_root)
    floors = development_floors(surface)
    development_issues = sorted(
        surface.loc[surface["issue_year"].isin(DEVELOPMENT_YEARS), "issue"].unique()
    )
    development_settlement = _load_settlement(data_root, development_issues)
    grid, selected = select_development_parameters(
        surface, floors, development_settlement
    )
    selections, preoutcome, tickets, decisions = construct_selected_policy(
        surface, selected
    )
    reference_bundles = pq.read_table(repo_root / S0_BUNDLES_RELATIVE).to_pandas()
    parity_columns = [
        "issue",
        "issue_year",
        "issue_anchor_ts",
        "n",
        "selected_match_ids",
        "support_json",
        "ticket_count",
        "units_per_ticket",
        "planned_stake_cny",
    ]
    parity_pairs = (
        ("S0_RAW_MASS", BASELINE_ARM),
        ("SELECTED_MODEL", COVERAGE_DIAGNOSTIC_ARM),
    )
    for reference_arm, candidate_arm in parity_pairs:
        reference = reference_bundles[
            reference_bundles["arm"].eq(reference_arm)
            & reference_bundles["n"].isin(N_VALUES)
        ][parity_columns].sort_values(
            ["issue_year", "issue_anchor_ts", "issue", "n"], kind="stable"
        ).reset_index(drop=True)
        candidate = preoutcome[preoutcome["arm"].eq(candidate_arm)][
            parity_columns
        ].sort_values(
            ["issue_year", "issue_anchor_ts", "issue", "n"], kind="stable"
        ).reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(
                candidate,
                reference,
                check_dtype=False,
                check_exact=True,
            )
        except AssertionError as exc:
            raise ContractError(
                f"{candidate_arm} is not exact #355 {reference_arm} parity"
            ) from exc
    freeze_receipt = {
        "contract": CONTRACT_ID,
        "development_years": list(DEVELOPMENT_YEARS),
        "transfer_years": list(TRANSFER_YEARS),
        "baseline": BASELINE_ARM,
        "coverage_diagnostic": COVERAGE_DIAGNOSTIC_ARM,
        "selected_parameters": _selected_receipt(selected),
        "surface_sha256": stable_frame_sha(surface),
        "floor_sha256": stable_frame_sha(floors),
        "grid_sha256": stable_frame_sha(grid),
        "selections_sha256": stable_frame_sha(selections),
        "preoutcome_sha256": stable_frame_sha(preoutcome),
        "tickets_sha256": stable_frame_sha(tickets),
        "decisions_sha256": stable_frame_sha(decisions),
        "transfer_labels_opened_at_freeze": False,
        "payout_65_semantics": "TICKET_LEVEL_ONCE",
        "s0_exact_baseline_parity": True,
        "coverage_diagnostic_exact_parity": True,
    }

    transfer_issues = sorted(
        surface.loc[surface["issue_year"].isin(TRANSFER_YEARS), "issue"].unique()
    )
    transfer_settlement = _load_settlement(data_root, transfer_issues)
    settlement = pd.concat(
        [development_settlement, transfer_settlement], ignore_index=True
    ).drop_duplicates(["issue", "match_idx"], keep="first")
    settled_bundles, support_attribution = settle(preoutcome, settlement)
    performance, risk, paths, contrasts, factorial = evaluate(
        decisions, settled_bundles
    )
    labels = pq.read_table(repo_root / LABEL_RELATIVE).to_pandas()
    selection_summary = selection_evidence(selections, labels)
    decision = _decision(performance, contrasts)
    source_receipt = {
        "contract": CONTRACT_ID,
        "value_cells_sha256": sha256_file(repo_root / VALUE_CELLS_RELATIVE),
        "value_freeze_sha256": sha256_file(repo_root / VALUE_FREEZE_RELATIVE),
        "value_source_sha256": sha256_file(repo_root / VALUE_SOURCE_RELATIVE),
        "score_surface_sha256": sha256_file(repo_root / SCORE_SURFACE_RELATIVE),
        "s0_bundles_sha256": sha256_file(repo_root / S0_BUNDLES_RELATIVE),
        "s0_freeze_sha256": sha256_file(repo_root / S0_FREEZE_RELATIVE),
        "label_sha256": sha256_file(repo_root / LABEL_RELATIVE),
        "settlement_semantic_sha256": stable_frame_sha(settlement),
        "implementation_hashes": _implementation_hashes(repo_root),
    }
    return {
        "surface": surface,
        "floors": floors,
        "grid": grid,
        "selections": selections,
        "preoutcome": preoutcome,
        "tickets": tickets,
        "decisions": decisions,
        "settled_bundles": settled_bundles,
        "support_attribution": support_attribution,
        "performance": performance,
        "risk": risk,
        "paths": paths,
        "contrasts": contrasts,
        "factorial": factorial,
        "selection_summary": selection_summary,
        "freeze_receipt": freeze_receipt,
        "source_receipt": source_receipt,
        "decision": decision,
    }


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
        for name in (
            "surface",
            "selections",
            "preoutcome",
            "tickets",
            "decisions",
            "settled_bundles",
            "support_attribution",
            "paths",
        ):
            _write_frame(staging / f"{name}.parquet", frames[name])
        for name in (
            "floors",
            "grid",
            "performance",
            "risk",
            "contrasts",
            "factorial",
            "selection_summary",
        ):
            _write_frame(staging / f"{name}.csv", frames[name])
        _write_json(staging / "freeze_receipt.json", frames["freeze_receipt"])
        _write_json(staging / "source_receipt.json", frames["source_receipt"])
        _write_json(staging / "decision.json", frames["decision"])

    atomic_publish_directory(output, populate, force=force)
    return frames["decision"]


def _report_text(frames: dict[str, Any]) -> str:
    transfer = frames["contrasts"]
    transfer = transfer[
        transfer["reference_arm"].eq(BASELINE_ARM)
        & transfer["period"].eq("ALL_2022_2024")
    ].sort_values(["n", "pnl_lift_cny"], ascending=[True, False])
    rows = "\n".join(
        f"| {int(row.n)} | {row.candidate_arm} | {int(row.common_issues)} | {row.candidate_pnl_cny:,.0f} | {row.pnl_lift_cny:,.0f} | {row.armwise_ex_largest_pnl_lift_cny:,.0f} | {row.candidate_max_drawdown_fraction:.2%} | {int(row.candidate_longest_losing_run)} |"
        for row in transfer.itertuples(index=False)
    )
    selected_rows = "\n".join(
        f"| {row['n']} | {row['arm']} | `{row['parameter_key']}` |"
        for row in frames["freeze_receipt"]["selected_parameters"]
    )
    best = frames["decision"].get("best_observed_candidate")
    best_text = "None" if best is None else json.dumps(best, ensure_ascii=False)
    best_lift_text = "n/a" if best is None else f"CNY {best['all_transfer_lift_cny']:,.0f}"
    shortlist = [(3, "C0V1G0"), (4, "C1V1G0"), (5, "C0V1G1")]
    shortlist_rows: list[str] = []
    for n, arm in shortlist:
        all_row = transfer[
            transfer["n"].eq(n) & transfer["candidate_arm"].eq(arm)
        ].iloc[0]
        annual = frames["contrasts"][
            frames["contrasts"]["reference_arm"].eq(BASELINE_ARM)
            & frames["contrasts"]["candidate_arm"].eq(arm)
            & frames["contrasts"]["n"].eq(n)
            & frames["contrasts"]["period"].isin(map(str, TRANSFER_YEARS))
        ].set_index("period")
        shortlist_rows.append(
            f"| {n} | {arm} | {annual.loc['2022', 'pnl_lift_cny']:,.0f} | "
            f"{annual.loc['2023', 'pnl_lift_cny']:,.0f} | "
            f"{annual.loc['2024', 'pnl_lift_cny']:,.0f} | "
            f"{all_row.pnl_lift_cny:,.0f} | "
            f"{all_row.armwise_ex_largest_pnl_lift_cny:,.0f} | "
            f"{all_row.bootstrap_mean_lift_p05_cny:,.0f} / "
            f"{all_row.bootstrap_mean_lift_p50_cny:,.0f} / "
            f"{all_row.bootstrap_mean_lift_p95_cny:,.0f} |"
        )
    shortlist_text = "\n".join(shortlist_rows)
    return f"""# Issue #359 — low-N coverage × European-value selector

## Decision

- Verdict: **{frames['decision']['verdict']}**.
- Accepted baseline: `{BASELINE_ARM}` (S0 raw retained mass).
- #355 coverage model: `{COVERAGE_DIAGNOSTIC_ARM}` is a non-promoted diagnostic, not the baseline.
- Best observed historical candidate: `{best_text}`.
- 2022–2024 are exposed historical transfer evidence, not a holdout.

## Frozen design

N3/N4/N5 keep fixed Top-2/R0 support, full 8/16/32-ticket Cartesian portfolios, CNY1,024 per bet issue, and 0.65 once per complete winning ticket. C/V/G form a complete 2×2×2 factorial. V uses `EUROPEAN_AVERAGE_ODDS_PROXY`, never raw odds alone or a Beijing-SP claim. A V-enabled arm must pass the complete-ticket proxy floor `0.65 × product(sum_Top2(p×odds)/2) >= 1` and never backfills an ineligible fixture.

## Development-selected parameters

| N | Arm | Frozen parameter |
|---:|---|---|
{selected_rows}

## 2022–2024 capital and matched lift versus S0

| N | Arm | Common issues | Candidate PnL | Lift vs S0 | Ex-largest lift | Max DD | Longest loss |
|---:|---|---:|---:|---:|---:|---:|---:|
{rows}

## Decision shortlist and stability

| N | Arm | 2022 lift | 2023 lift | 2024 lift | Total lift | Armwise ex-largest | Issue-bootstrap mean p05 / p50 / p95 |
|---:|---|---:|---:|---:|---:|---:|---:|
{shortlist_text}

- `N3 C0V1G0` (value-only) and `N4 C1V1G0` (coverage + value) pass the preregistered **historical-signal** screen. Both retain positive armwise ex-largest lift, but both issue-bootstrap 5th percentiles remain below zero. They are research candidates, not deployable Edge.
- N4 is the strongest balanced observation: {best_lift_text} matched lift over 2022–2024, positive in 2022/2023 and negative in 2024. This is evidence that coverage reliability and expected-return filtering can interact, not proof of year-stable additivity.
- N5 `C0V1G1` has the largest raw lift in this shortlist but only 2023 is positive; largest-paired-delta sensitivity also turns negative. It is a concentration warning rather than a stable candidate.
- The separation factor `G` does not add a repeatable benefit at the frozen development-selected cutoffs. In several cells development selected the minimum gap cutoff, making the G arm operationally identical to its no-G counterpart.
- The #355 coverage-only diagnostic exactly reproduces its earlier matched lifts. It remains a diagnostic and does not replace the accepted S0 baseline.

## Interpretation boundary

Issue is the independent unit. Strategy-native capital, calendar-matched S0 lift, annual transfer, issue bootstrap, ex-largest sensitivity, factorial interactions, selection attribution, NO_BET coverage, payout concentration and corrected path-risk semantics are committed in the package. Completed recoveries and terminal open-underwater spells are separate; the withdrawn #355 recovery field is not reused. The historical 10h source is retrospective-relative and does not authorize live deployment. #210 and #218 remain unchanged.

## Artifacts

- Package: `results/low_n_eu_value_selector/`
- Notebook: `notebooks/research/low-n-eu-value-selector/low_n_eu_value_selector.ipynb`
- Figures: `docs/research/figures/issue_359_capital.png`, `docs/research/figures/issue_359_frontier.png`
"""


def write_analysis(repo_root: Path, output: Path) -> list[Path]:
    performance = pd.read_csv(output / "performance.csv")
    contrasts = pd.read_csv(output / "contrasts.csv")
    paths = pd.read_parquet(output / "paths.parquet")
    freeze = json.loads((output / "freeze_receipt.json").read_text())
    decision = json.loads((output / "decision.json").read_text())
    risk = pd.read_csv(output / "risk.csv")
    factorial = pd.read_csv(output / "factorial.csv")
    selection_summary = pd.read_csv(output / "selection_summary.csv")
    frames = {
        "performance": performance,
        "contrasts": contrasts,
        "paths": paths,
        "freeze_receipt": freeze,
        "decision": decision,
        "risk": risk,
        "factorial": factorial,
        "selection_summary": selection_summary,
    }
    figure_dir = repo_root / "docs/research/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    capital_figure = figure_dir / "issue_359_capital.png"
    frontier_figure = figure_dir / "issue_359_frontier.png"
    transfer_paths = paths[paths["period"].eq("ALL_2022_2024")]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), sharey=True)
    for axis, n in zip(axes, N_VALUES, strict=True):
        group = transfer_paths[transfer_paths["n"].eq(n)]
        for arm in ARMS:
            arm_frame = group[group["arm"].eq(arm)]
            axis.plot(
                arm_frame["path_index"],
                arm_frame["capital_cny"],
                label=arm,
                linewidth=1.3 if arm == BASELINE_ARM else 0.8,
                alpha=1.0 if arm == BASELINE_ARM else 0.7,
            )
        axis.set_title(f"N{n}")
        axis.set_xlabel("Issue")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Capital (CNY)")
    axes[-1].legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(capital_figure, dpi=180)
    plt.close(fig)

    transfer_contrasts = contrasts[
        contrasts["reference_arm"].eq(BASELINE_ARM)
        & contrasts["period"].eq("ALL_2022_2024")
    ]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for axis, n in zip(axes, N_VALUES, strict=True):
        group = transfer_contrasts[transfer_contrasts["n"].eq(n)]
        axis.scatter(
            group["candidate_max_drawdown_fraction"],
            group["pnl_lift_cny"],
            s=45,
        )
        for row in group.itertuples(index=False):
            axis.annotate(row.candidate_arm, (row.candidate_max_drawdown_fraction, row.pnl_lift_cny), fontsize=7)
        axis.axhline(0, color="black", linewidth=0.8)
        axis.set_title(f"N{n}")
        axis.set_xlabel("Max drawdown")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Matched PnL lift vs S0 (CNY)")
    fig.tight_layout()
    fig.savefig(frontier_figure, dpi=180)
    plt.close(fig)

    report = repo_root / "docs/research/Issue-359-LowN-European-Value-Selector.md"
    report.write_text(_report_text(frames), encoding="utf-8")
    notebook_path = (
        repo_root
        / "notebooks/research/low-n-eu-value-selector/low_n_eu_value_selector.ipynb"
    )
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                "# Issue #359 — low-N coverage × European-value selector\n\n"
                "Executed decision notebook. 2019–2021 selects parameters; 2022–2024 are exposed transfer evidence."
            ),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\nimport json\nimport pandas as pd\n"
                "repo = Path.cwd()\n"
                "output = repo / 'results/low_n_eu_value_selector'\n"
                "decision = json.loads((output / 'decision.json').read_text())\n"
                "performance = pd.read_csv(output / 'performance.csv')\n"
                "contrasts = pd.read_csv(output / 'contrasts.csv')\n"
                "risk = pd.read_csv(output / 'risk.csv')\n"
                "decision"
            ),
            nbformat.v4.new_code_cell(
                "performance[performance.period.eq('ALL_2022_2024')].sort_values(['n','ending_capital_cny'], ascending=[True,False])"
            ),
            nbformat.v4.new_code_cell(
                "contrasts[(contrasts.reference_arm.eq('C0V0G0')) & contrasts.period.eq('ALL_2022_2024')].sort_values(['n','pnl_lift_cny'], ascending=[True,False])"
            ),
            nbformat.v4.new_code_cell(
                "risk[risk.period.eq('ALL_2022_2024')].sort_values(['n','max_drawdown_fraction'])"
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
    return [report, notebook_path, capital_figure, frontier_figure]


def finalize_manifest(repo_root: Path, output: Path, delivery: list[Path]) -> None:
    delivery_receipt = {
        str(path.relative_to(repo_root)): sha256_file(path) for path in delivery
    }
    _write_json(output / "delivery_receipt.json", delivery_receipt)
    files = {
        str(path.relative_to(output)): sha256_file(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }
    _write_json(
        output / "MANIFEST.json",
        {"contract": CONTRACT_ID, "files": files},
    )


def _assert_frame(actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str]) -> None:
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
    if set(manifest.get("files", {})) != actual_files or not actual_files:
        raise AssertionError("package manifest inventory is incomplete")
    if not all(
        sha256_file(output / relative) == digest
        for relative, digest in manifest["files"].items()
    ):
        raise AssertionError("package manifest hashes do not match")
    expected = _scientific_frames(repo_root, data_root)
    if json.loads((output / "source_receipt.json").read_text()) != expected["source_receipt"]:
        raise AssertionError("source receipt does not replay")
    if json.loads((output / "freeze_receipt.json").read_text()) != expected["freeze_receipt"]:
        raise AssertionError("freeze receipt does not replay")
    if json.loads((output / "decision.json").read_text()) != expected["decision"]:
        raise AssertionError("decision does not replay")
    parquet_frames = {
        "surface": ["issue", "match_idx"],
        "selections": ["issue", "arm", "n", "match_idx"],
        "preoutcome": ["issue", "arm", "n"],
        "tickets": ["issue", "arm", "n", "ticket_index"],
        "decisions": ["issue", "arm", "n"],
        "settled_bundles": ["issue", "arm", "n"],
        "support_attribution": ["issue", "arm", "n", "match_idx"],
        "paths": ["arm", "n", "period", "path_index"],
    }
    for name, keys in parquet_frames.items():
        _assert_frame(pd.read_parquet(output / f"{name}.parquet"), expected[name], keys)
    csv_frames = {
        "floors": ["n", "factor", "grid_key"],
        "grid": ["arm", "n", "parameter_key"],
        "performance": ["arm", "n", "period"],
        "risk": ["arm", "n", "period"],
        "contrasts": ["reference_arm", "candidate_arm", "n", "period"],
        "factorial": ["n", "period", "effect"],
        "selection_summary": ["arm", "n", "period"],
    }
    for name, keys in csv_frames.items():
        _assert_frame(pd.read_csv(output / f"{name}.csv"), expected[name], keys)
    receipt = json.loads((output / "delivery_receipt.json").read_text())
    if not receipt or not all(
        (repo_root / relative).is_file()
        and sha256_file(repo_root / relative) == digest
        for relative, digest in receipt.items()
    ):
        raise AssertionError("delivery artifacts are missing or stale")
    return {
        "manifest": True,
        "source_bound_replay": True,
        "strict_temporal_freeze": True,
        "full_factorial": True,
        "ticket_budget_and_payout": True,
        "settlement_replay": True,
        "risk_semantics": True,
        "decision_replay": True,
        "delivery_artifacts": True,
    }
