"""Rebuild the complete corrected-N6 fixed R0..R6 diagnostic surface.

Contract: BJ-UNIFIED-N6-CORRECTED-ALL-R-001/v1 (#381).
The construction is preregistered: the exact #376 corrected source-bound
action surface (six selected fixtures per issue, probability Top-2 support)
is reused unchanged, and only the fixed support depth R in 0..6 varies.
No dynamic R, thresholds, selector retuning, seed mining, allocator search,
or post-outcome R selection is performed.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.n6_chronology_sync.pipeline import (
    locate_data_root,
    load_corrected_cells,
    prepare_actions,
    sha256_file,
    stable_frame_sha,
    _read_json,
)
from src.low_n_selector_data.pipeline import verify_package as verify_corrected_source
from src.source_schema.publication import atomic_publish_directory, atomic_write_json

from .contract import (
    ARMS,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CORRECTED_PACKAGE,
    CONTRACT_ID,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    LEGACY_MANIFEST_SHA256,
    LEGACY_PACKAGE,
    MOVING_BLOCK_LENGTH,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    R_GRID,
    RESULT_PACKAGE,
    ROLLING_WINDOWS,
    STAKE_PER_TICKET_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    UNITS_PER_TICKET,
    UPSTREAM_N6_PACKAGE,
    YEARS,
)


class ContractError(ValueError):
    """Raised when a frozen research invariant of #381 fails."""


def _arm_index(arm: str) -> int:
    return ARMS.index(arm)


def _scope_index(scope: str) -> int:
    return YEARS.index(int(scope)) if scope != "ALL" else len(YEARS)


# Local pure helpers. Bodies mirror the program-accepted #377 definitions
# (src/n6_support_transfer_grid/pipeline.py) but close over THIS package's
# frozen constants, so every decision-facing helper is inside pipeline.py and
# is bound by the MANIFEST implementation hash (no transitive helper hole).
def _run_lengths(mask: np.ndarray) -> np.ndarray:
    lengths: list[int] = []
    current = 0
    for value in mask:
        if bool(value):
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return np.asarray(lengths, dtype=int)


def _longest_strict_run(mask: np.ndarray) -> int:
    best = current = 0
    for value in mask:
        current = current + 1 if bool(value) else 0
        best = max(best, current)
    return best


def _path_metrics(pnl: np.ndarray) -> dict[str, float | int]:
    equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
    peaks = np.maximum.accumulate(equity)
    drawdown = (peaks - equity) / np.maximum(peaks, 1e-12)
    peak_indices = np.flatnonzero(drawdown <= 1e-15)
    open_underwater = int(len(pnl) - peak_indices[-1]) if drawdown[-1] > 1e-15 else 0
    loss_runs = _run_lengths(pnl <= 0)
    return {
        "max_drawdown_fraction": float(drawdown.max()),
        "longest_profitable_issue_losing_run": int(loss_runs.max()) if len(loss_runs) else 0,
        "open_underwater_issues": open_underwater,
    }


def _run_summary(pnl: np.ndarray) -> dict[str, float | int]:
    runs = _run_lengths(pnl <= 0)
    if not len(runs):
        return {
            "losing_run_count": 0, "longest_run": 0, "median_run": 0.0,
            "p75_run": 0.0, "p90_run": 0.0, "runs_ge_10": 0, "runs_ge_15": 0,
        }
    return {
        "losing_run_count": int(len(runs)), "longest_run": int(runs.max()),
        "median_run": float(np.quantile(runs, 0.5)), "p75_run": float(np.quantile(runs, 0.75)),
        "p90_run": float(np.quantile(runs, 0.9)), "runs_ge_10": int((runs >= 10).sum()),
        "runs_ge_15": int((runs >= 15).sum()),
    }


def _circular_block_indices(length: int, draws: int, rng: np.random.Generator) -> np.ndarray:
    block = min(MOVING_BLOCK_LENGTH, length)
    blocks_needed = math.ceil(length / block)
    starts = rng.integers(0, length, (draws, blocks_needed))
    offsets = np.arange(block)
    indices = (starts[:, :, None] + offsets[None, None, :]) % length
    return indices.reshape(draws, -1)[:, :length]


def _active_support(selected: pd.DataFrame, r: int) -> pd.Series:
    """Fixed-R support: replace Top-2 with QEU Top-2 on the top-R support-pressure legs.

    R0 activates no leg (baseline calibrated Top-2). R3 reproduces the accepted
    corrected #376 fixed-R3 definition exactly (top-3 pressure legs). The
    replacement member satisfies #376 semantics: on an activated leg the QEU
    Top-2 support replaces the baseline pair, i.e. the QEU-second-ranked member
    of the pair is replaced by the QEU-ranked omitted outcome whenever QEU ranks
    the omitted outcome above it (support pressure > 0).
    """
    if r == 0:
        return selected["baseline_support"].copy()
    ranked = selected.sort_values(
        ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
    )
    activated = set(ranked.head(r)["match_idx"].astype(int))
    return pd.Series(
        np.where(
            selected["match_idx"].isin(activated),
            selected["qeu_support"],
            selected["baseline_support"],
        ),
        index=selected.index,
    )


def construct_r_arms(
    actions: pd.DataFrame,
) -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    """Build the complete R0..R6 arm surface over the exact #376 selected fixtures."""
    decisions: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    settled: list[dict[str, Any]] = []
    attribution: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    saturation: list[dict[str, Any]] = []
    for (issue, year, anchor), group in actions.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        selected = (
            group.sort_values(
                ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
            )
            .head(N_LEGS)
            .copy()
        )
        selected = selected.sort_values("match_idx", kind="stable")
        complete = len(selected) == N_LEGS
        trusted = int(selected["settlement_available"].sum()) if complete else 0
        coverage.append(
            {
                "issue": str(issue),
                "issue_year": int(year),
                "issue_anchor_ts": anchor,
                "available_fixtures": int(len(group)),
                "selected_legs": int(len(selected)),
                "trusted_selected_legs": trusted,
                "settlement_complete": bool(complete and trusted == N_LEGS),
                "excluded_reason": "" if complete and trusted == N_LEGS else (
                    "INSUFFICIENT_FIXTURES" if not complete else "UNTRUSTED_SELECTED_LEG"
                ),
            }
        )
        if not complete:
            continue
        pressure_rank = (
            selected["support_pressure"]
            .rank(method="first", ascending=False)
            .astype(int)
            .to_numpy()
        )
        for r in R_GRID:
            arm = ARMS[r]
            supports = _active_support(selected, r)
            support_map = dict(zip(selected["match_idx"].astype(int), supports, strict=True))
            selected_ids = "|".join(selected["match_idx"].astype(str))
            decisions.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "issue_anchor_ts": anchor,
                    "arm": arm,
                    "selected_match_ids": selected_ids,
                    "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                    "ticket_count": TICKETS,
                    "funded_units": FUNDED_UNITS,
                    "planned_stake_cny": ISSUE_STAKE_CNY,
                    "settlement_status": "SETTLED" if trusted == N_LEGS else "UNTRUSTED_SELECTED_LEG",
                }
            )
            fixture_order = selected["match_idx"].astype(int).tolist()
            support_order = [support_map[key] for key in fixture_order]
            for ordinal, choices in enumerate(itertools.product((0, 1), repeat=N_LEGS)):
                outcomes = [support[choice] for support, choice in zip(support_order, choices, strict=True)]
                tickets.append(
                    {
                        "issue": str(issue), "issue_year": int(year), "arm": arm,
                        "ticket_ordinal": ordinal, "ticket_code": "|".join(outcomes),
                        "units": UNITS_PER_TICKET, "stake_cny": STAKE_PER_TICKET_CNY,
                    }
                )
            active = np.array(supports.astype(str))
            realized = selected["result_code"].fillna("").astype(str).to_numpy()
            included = np.array([value in support for value, support in zip(realized, active, strict=True)])
            misses = int((~included).sum())
            gross = (
                float(STAKE_PER_TICKET_CNY * PAYOUT_FACTOR * selected["winning_sp"].prod())
                if trusted == N_LEGS and misses == 0 else 0.0
            )
            if trusted == N_LEGS:
                settled.append(
                    {
                        "issue": str(issue), "issue_year": int(year), "issue_anchor_ts": anchor,
                        "arm": arm, "selected_match_ids": selected_ids,
                        "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                        "ticket_count": TICKETS, "funded_units": FUNDED_UNITS,
                        "stake_cny": ISSUE_STAKE_CNY, "gross_cny": gross,
                        "pnl_cny": gross - ISSUE_STAKE_CNY, "miss_count": misses,
                        "hit": bool(misses == 0),
                    }
                )
            baseline = selected["baseline_support"].astype(str).to_numpy()
            activated_mask = pressure_rank <= r
            for row, support, base, ok, rank, activated in zip(
                selected.itertuples(), active, baseline, included, pressure_rank,
                activated_mask, strict=True,
            ):
                base_set = set(base)
                active_set = set(str(support))
                dropped = "".join(sorted(base_set - active_set))
                gained = "".join(sorted(active_set - base_set))
                changed = bool(dropped or gained)
                replaced_outcome = dropped if changed else ""
                replacement_outcome = gained if changed else ""
                # Mx3 construction: the baseline pair omits exactly one outcome,
                # so the QEU-ranked omitted-outcome candidate set is a singleton.
                # Set-based saturation (candidate set size > 1) never occurs.
                candidate_set_size = 1
                saturated = False
                # Disclosure: under the accepted #376 QEU Top-2 replacement the
                # dropped member can be the probability-first pair member
                # (counted and disclosed; see PROTOCOL-LOG entry 001).
                probabilities = {
                    outcome: float(getattr(row, f"q_eu_{outcome}"))
                    for outcome in base_set
                }
                dropped_first = changed and bool(
                    probabilities
                    and dropped == max(probabilities.items(), key=lambda item: item[1])[0]
                )
                attribution.append(
                    {
                        "issue": str(issue), "issue_year": int(year), "arm": arm,
                        "match_idx": int(row.match_idx), "fixture_decision_ts": row.fixture_decision_ts,
                        "pressure_rank": int(rank), "support_pressure": float(row.support_pressure),
                        "baseline_support": str(row.baseline_support), "qeu_support": str(row.qeu_support),
                        "active_support": str(support), "activated": bool(activated),
                        "qeu_activated": bool(changed),
                        "support_changed": changed,
                        "noop_activation": bool(activated and not changed),
                        "replaced_outcome": replaced_outcome,
                        "replacement_outcome": replacement_outcome,
                        "dropped_is_probability_first": dropped_first,
                        "candidate_set_size": candidate_set_size,
                        "saturated": saturated,
                        "result_code": str(row.result_code), "winning_sp": float(row.winning_sp),
                        "settlement_available": bool(row.settlement_available),
                        "realized_in_support": bool(ok),
                    }
                )
            noop_mask = activated_mask & (np.asarray(baseline) == active)
            saturation.append(
                {
                    "issue": str(issue), "issue_year": int(year), "arm": arm,
                    "activated_legs": int(activated_mask.sum()),
                    "noop_legs": int(noop_mask.sum()),
                    "replaced_legs": int((activated_mask & (np.asarray(baseline) != active)).sum()),
                    "saturated_legs": 0,
                    "max_candidate_set_size": 1,
                }
            )
    return (
        pd.DataFrame(decisions), pd.DataFrame(tickets), pd.DataFrame(settled),
        pd.DataFrame(attribution), pd.DataFrame(coverage), pd.DataFrame(saturation),
    )


def _enforce_exact_common(settled: pd.DataFrame) -> None:
    """Every scope must share the exact same settled issue set across all arms."""
    for scope in [*(str(year) for year in YEARS), "ALL"]:
        scoped = settled if scope == "ALL" else settled[settled["issue_year"].eq(int(scope))]
        issue_sets = {
            arm: frozenset(scoped.loc[scoped["arm"].eq(arm), "issue"]) for arm in ARMS
        }
        first = issue_sets[ARMS[0]]
        if any(issue_sets[arm] != first for arm in ARMS[1:]):
            raise ContractError(f"scope {scope} is not exact-common across all arms")


def evaluate_r_grid(
    settled: pd.DataFrame,
) -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    """Per arm x scope performance, risk, runs, capital paths, path bootstrap, rolling."""
    _enforce_exact_common(settled)
    performance_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    path_bootstrap_rows: list[dict[str, Any]] = []
    rolling_rows: list[dict[str, Any]] = []
    scopes = [*[(str(year), settled[settled["issue_year"].eq(year)]) for year in YEARS], ("ALL", settled)]
    for scope, scoped in scopes:
        for arm, group in scoped.groupby("arm", sort=True):
            group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            pnl = group["pnl_cny"].to_numpy(float)
            largest = int(np.argmax(pnl))
            payouts = group.loc[group["gross_cny"].gt(0), "gross_cny"].to_numpy(float)
            weights = payouts / payouts.sum() if len(payouts) else np.array([])
            total_tickets = int(group["ticket_count"].sum())
            winning_tickets = int(group["hit"].sum())
            performance_rows.append(
                {
                    "scope": scope, "arm": arm, "issues": int(len(group)),
                    "ticket_count_per_issue": int(group["ticket_count"].iloc[0]),
                    "total_tickets": total_tickets,
                    "ticket_hit_rate": float(winning_tickets / total_tickets) if total_tickets else math.nan,
                    "issue_hit_rate": float(group["hit"].mean()) if len(group) else math.nan,
                    "issue_gross_positive_rate": float(
                        group["gross_cny"].gt(0).mean()
                    ) if len(group) else math.nan,
                    "issue_profitable_rate": float(
                        group["pnl_cny"].gt(0).mean()
                    ) if len(group) else math.nan,
                    "stake_cny": float(group["stake_cny"].sum()),
                    "gross_cny": float(group["gross_cny"].sum()),
                    "pnl_cny": float(pnl.sum()),
                    "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum()) if len(group) else math.nan,
                    "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest]) if len(pnl) else math.nan,
                }
            )
            path_metric = _path_metrics(pnl)
            risk_rows.append(
                {
                    "scope": scope, "arm": arm, **path_metric,
                    "longest_losing_run": int(_longest_strict_run(pnl < 0)),
                    "largest_payout_share": float(weights.max()) if len(weights) else 0.0,
                    "payout_hhi": float(np.square(weights).sum()) if len(weights) else 0.0,
                }
            )
            run_rows.append({"scope": scope, "arm": arm, **_run_summary(pnl)})
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL_CNY, capital])[1:]
            for order, (row, value, peak) in enumerate(
                zip(group.itertuples(), capital, peaks, strict=True), start=1
            ):
                path_rows.append(
                    {
                        "scope": scope, "arm": arm, "issue_order": order,
                        "issue": row.issue, "issue_year": int(row.issue_year),
                        "issue_anchor_ts": row.issue_anchor_ts, "pnl_cny": float(row.pnl_cny),
                        "capital_cny": float(value),
                        "drawdown_fraction": float((peak - value) / max(peak, 1e-12)),
                    }
                )
            rng = np.random.default_rng(
                BOOTSTRAP_SEED + 200 + 10 * _scope_index(scope) + _arm_index(arm)
            )
            indices = _circular_block_indices(len(pnl), BOOTSTRAP_DRAWS, rng)
            longest = np.empty(BOOTSTRAP_DRAWS, dtype=float)
            drawdown = np.empty(BOOTSTRAP_DRAWS, dtype=float)
            underwater = np.empty(BOOTSTRAP_DRAWS, dtype=float)
            for draw, sample_indices in enumerate(indices):
                metrics = _path_metrics(pnl[sample_indices])
                longest[draw] = metrics["longest_profitable_issue_losing_run"]
                drawdown[draw] = metrics["max_drawdown_fraction"]
                underwater[draw] = metrics["open_underwater_issues"]
            path_bootstrap_rows.append(
                {
                    "scope": scope, "arm": arm,
                    "block_length": min(MOVING_BLOCK_LENGTH, len(pnl)),
                    "draws": BOOTSTRAP_DRAWS,
                    "longest_run_p05": float(np.quantile(longest, 0.05)),
                    "longest_run_median": float(np.quantile(longest, 0.5)),
                    "longest_run_p95": float(np.quantile(longest, 0.95)),
                    "max_drawdown_p05": float(np.quantile(drawdown, 0.05)),
                    "max_drawdown_median": float(np.quantile(drawdown, 0.5)),
                    "max_drawdown_p95": float(np.quantile(drawdown, 0.95)),
                    "open_underwater_p05": float(np.quantile(underwater, 0.05)),
                    "open_underwater_median": float(np.quantile(underwater, 0.5)),
                    "open_underwater_p95": float(np.quantile(underwater, 0.95)),
                }
            )
            if scope == "ALL":
                for window in ROLLING_WINDOWS:
                    rolling = pd.Series(pnl).rolling(window).sum().dropna().to_numpy(float)
                    rolling_rows.append(
                        {
                            "arm": arm, "window_issues": window, "windows": int(len(rolling)),
                            "worst_window_pnl_cny": float(rolling.min()),
                            "p10_window_pnl_cny": float(np.quantile(rolling, 0.1)),
                            "median_window_pnl_cny": float(np.quantile(rolling, 0.5)),
                            "positive_window_rate": float((rolling > 0).mean()),
                        }
                    )
    return (
        pd.DataFrame(performance_rows), pd.DataFrame(risk_rows), pd.DataFrame(run_rows),
        pd.DataFrame(path_rows), pd.DataFrame(path_bootstrap_rows), pd.DataFrame(rolling_rows),
    )


def matched_contrasts(settled: pd.DataFrame) -> pd.DataFrame:
    """Matched lift versus corrected R0 with issue and moving-block bootstrap.

    R0 rows are included with exactly zero comparison fields (contract parity
    convention). Every non-R0 arm is contrasted on the exact-common issue set.
    """
    rows: list[dict[str, Any]] = []
    scopes = [*(str(year) for year in YEARS), "ALL"]
    for scope in scopes:
        scoped = settled if scope == "ALL" else settled[settled["issue_year"].eq(int(scope))]
        wide = scoped.pivot(
            index=["issue_anchor_ts", "issue"], columns="arm", values="pnl_cny"
        ).sort_index(kind="stable")
        if set(wide.columns) != set(ARMS) or wide.isna().any().any():
            raise ContractError(f"contrast denominator is not exact common across all arms: {scope}")
        baseline = wide[ARMS[0]].to_numpy(float)
        for arm in ARMS:
            if arm == ARMS[0]:
                rows.append(
                    {
                        "scope": scope, "arm": arm, "issues": int(len(wide)),
                        "matched_lift_cny": 0.0, "largest_abs_delta_cny": 0.0,
                        "largest_abs_delta_issue": "", "ex_largest_lift_cny": 0.0,
                        "issue_bootstrap_p05_cny": 0.0, "issue_bootstrap_median_cny": 0.0,
                        "issue_bootstrap_p95_cny": 0.0,
                        "moving_block_p05_cny": 0.0, "moving_block_median_cny": 0.0,
                        "moving_block_p95_cny": 0.0,
                    }
                )
                continue
            delta = (wide[arm].to_numpy(float) - baseline)
            largest = int(np.argmax(np.abs(delta)))
            rng_iid = np.random.default_rng(
                BOOTSTRAP_SEED + 10 * _scope_index(scope) + _arm_index(arm)
            )
            iid_draws = delta[
                rng_iid.integers(0, len(delta), (BOOTSTRAP_DRAWS, len(delta)))
            ].sum(axis=1)
            rng_block = np.random.default_rng(
                BOOTSTRAP_SEED + 50 + 10 * _scope_index(scope) + _arm_index(arm)
            )
            block_indices = _circular_block_indices(len(delta), BOOTSTRAP_DRAWS, rng_block)
            block_draws = delta[block_indices].sum(axis=1)
            rows.append(
                {
                    "scope": scope, "arm": arm, "issues": int(len(delta)),
                    "matched_lift_cny": float(delta.sum()),
                    "largest_abs_delta_issue": str(wide.index[largest][1]),
                    "largest_abs_delta_cny": float(delta[largest]),
                    "ex_largest_lift_cny": float(delta.sum() - delta[largest]),
                    "issue_bootstrap_p05_cny": float(np.quantile(iid_draws, 0.05)),
                    "issue_bootstrap_median_cny": float(np.quantile(iid_draws, 0.5)),
                    "issue_bootstrap_p95_cny": float(np.quantile(iid_draws, 0.95)),
                    "moving_block_p05_cny": float(np.quantile(block_draws, 0.05)),
                    "moving_block_median_cny": float(np.quantile(block_draws, 0.5)),
                    "moving_block_p95_cny": float(np.quantile(block_draws, 0.95)),
                }
            )
    return pd.DataFrame(rows)


def _reproduce_n6_bootstrap(settled: pd.DataFrame) -> pd.DataFrame:
    """Reproduce #376's exact iid bootstrap (seed 376_001, 2000 draws) on my R3 deltas.

    This proves the matched R3-minus-R0 delta series is identical to the
    published corrected #376 surface.
    """
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(376_001)
    scopes = [*(str(year) for year in YEARS), "ALL"]
    for scope in scopes:
        scoped = settled if scope == "ALL" else settled[settled["issue_year"].eq(int(scope))]
        wide = scoped.pivot(
            index="issue", columns="arm", values="pnl_cny"
        ).dropna(subset=["R0", "R3"])
        delta = (wide["R3"] - wide["R0"]).to_numpy(float)
        draws = np.array([
            delta[rng.integers(0, len(delta), len(delta))].sum() for _ in range(2_000)
        ]) if len(delta) else np.array([math.nan])
        rows.append(
            {
                "scope": scope, "issues": int(len(delta)),
                "matched_lift_cny": float(delta.sum()),
                "ex_largest_lift_cny": float(
                    delta.sum() - delta[np.argmax(np.abs(delta))]
                ) if len(delta) else math.nan,
                "bootstrap_p025_cny": float(np.nanquantile(draws, 0.025)),
                "bootstrap_median_cny": float(np.nanquantile(draws, 0.5)),
                "bootstrap_p975_cny": float(np.nanquantile(draws, 0.975)),
            }
        )
    return pd.DataFrame(rows)


def _n6_frame_equality(
    left: pd.DataFrame, right: pd.DataFrame, keys: list[str], *, exact: bool = False
) -> bool:
    """Comparable frame equality tolerant of CSV round-trip dtype/float noise.

    exact=True compares float columns bitwise (parquet-to-parquet surfaces);
    the default tolerates only CSV float round-trip noise at 1e-9.
    """
    if list(left.columns) != list(right.columns):
        return False
    if len(left) != len(right):
        return False
    if keys:
        left = left.sort_values(keys, kind="stable").reset_index(drop=True)
        right = right.sort_values(keys, kind="stable").reset_index(drop=True)
    for name in left.columns:
        l = left[name]
        r = right[name]
        if pd.api.types.is_float_dtype(l) and pd.api.types.is_float_dtype(r):
            if exact:
                if not np.array_equal(
                    l.to_numpy(float), r.to_numpy(float), equal_nan=True
                ):
                    return False
            elif not np.allclose(
                l.to_numpy(float), r.to_numpy(float), rtol=0, atol=1e-9, equal_nan=True
            ):
                return False
        elif pd.api.types.is_datetime64_any_dtype(l) or pd.api.types.is_datetime64_any_dtype(r):
            try:
                lns = pd.to_datetime(l, utc=True).astype("int64").to_numpy()
                rns = pd.to_datetime(r, utc=True).astype("int64").to_numpy()
            except (TypeError, ValueError):
                return False
            if not np.array_equal(lns, rns):
                return False
        else:
            a = l.fillna("").astype(str).to_numpy()
            b = r.fillna("").astype(str).to_numpy()
            if not np.array_equal(a, b):
                return False
    return True


def _schema_superset(mine: list[str], upstream: list[str], label: str) -> None:
    missing = sorted(set(upstream) - set(mine))
    if missing:
        raise ContractError(f"#376 parity schema gap on {label}: missing {missing}")


def parity_with_n6(
    repo_root: Path,
    decisions: pd.DataFrame,
    tickets: pd.DataFrame,
    settled: pd.DataFrame,
    attribution: pd.DataFrame,
    performance: pd.DataFrame,
    risk: pd.DataFrame,
    paths: pd.DataFrame,
    contrasts: pd.DataFrame,
    coverage: pd.DataFrame,
) -> dict[str, Any]:
    """Exact R0/R3 parity versus the published corrected #376 package.

    Evidence-gate strictness: every upstream field must be present on the #381
    side (schema superset) and compared; parquet-to-parquet surfaces compare
    exactly; CSV-published surfaces tolerate only float round-trip noise (1e-9).
    """
    package = repo_root / UPSTREAM_N6_PACKAGE
    manifest = _read_json(package / "MANIFEST.json")
    up_decisions = pd.read_parquet(package / "decisions.parquet")
    up_tickets = pd.read_parquet(package / "tickets.parquet")
    up_bundles = pd.read_parquet(package / "issue_bundles.parquet")
    up_attribution = pd.read_parquet(package / "support_attribution.parquet")
    up_performance = pd.read_csv(package / "performance.csv")
    up_risk = pd.read_csv(package / "risk_diagnostics.csv")
    up_paths = pd.read_csv(package / "capital_paths.csv")
    up_bootstrap = pd.read_csv(package / "bootstrap_lift.csv")
    up_coverage = pd.read_csv(package / "coverage_ledger.csv")
    _schema_superset(list(decisions.columns), list(up_decisions.columns), "decisions")
    _schema_superset(list(tickets.columns), list(up_tickets.columns), "tickets")
    _schema_superset(list(settled.columns), list(up_bundles.columns), "issue_bundles")
    _schema_superset(list(attribution.columns), list(up_attribution.columns), "support_attribution")
    _schema_superset(list(performance.columns), list(set(up_performance.columns) - {"hit_rate"}), "performance")
    _schema_superset(list(risk.columns), ["scope", "arm", "max_drawdown_fraction",
                                          "longest_losing_run", "open_underwater_issues",
                                          "largest_payout_share", "payout_hhi"], "risk")
    _schema_superset(list(paths.columns), list(up_paths.columns), "capital_paths")
    _schema_superset(list(coverage.columns), list(up_coverage.columns), "coverage_ledger")
    decision_keys = ["issue", "issue_year", "issue_anchor_ts", "arm"]
    decisions_eq = _n6_frame_equality(
        up_decisions[list(up_decisions.columns)],
        decisions.loc[decisions["arm"].isin(["R0", "R3"]), list(up_decisions.columns)],
        decision_keys, exact=True,
    )
    tickets_eq = _n6_frame_equality(
        up_tickets[list(up_tickets.columns)],
        tickets.loc[tickets["arm"].isin(["R0", "R3"]), list(up_tickets.columns)],
        ["issue", "issue_year", "arm", "ticket_ordinal"], exact=True,
    )
    settled_eq = _n6_frame_equality(
        up_bundles[list(up_bundles.columns)],
        settled.loc[settled["arm"].isin(["R0", "R3"]), list(up_bundles.columns)],
        ["issue", "issue_year", "arm"], exact=True,
    )
    attribution_eq = _n6_frame_equality(
        up_attribution[list(up_attribution.columns)],
        attribution.loc[attribution["arm"].isin(["R0", "R3"]), list(up_attribution.columns)],
        ["issue", "issue_year", "arm", "match_idx"], exact=True,
    )
    share_perf = sorted(set(up_performance.columns) & set(performance.columns))
    performance_eq = _n6_frame_equality(
        up_performance[share_perf],
        performance.loc[performance["arm"].isin(["R0", "R3"]), share_perf],
        ["scope", "arm"],
    )
    # #376 names the issue hit rate `hit_rate`; #381 keeps it as `issue_hit_rate`.
    hit_rate_eq = _n6_frame_equality(
        up_performance[["scope", "arm", "hit_rate"]].rename(
            columns={"hit_rate": "issue_hit_rate"}
        ),
        performance.loc[performance["arm"].isin(["R0", "R3"]), ["scope", "arm", "issue_hit_rate"]],
        ["scope", "arm"],
    )
    share_risk = sorted(
        set(up_risk.columns)
        & set(risk.columns)
        | {"longest_losing_run"}
    )
    risk_eq = _n6_frame_equality(
        up_risk[share_risk],
        risk.loc[risk["arm"].isin(["R0", "R3"]), share_risk],
        ["scope", "arm"],
    )
    paths_eq = _n6_frame_equality(
        up_paths[list(up_paths.columns)],
        paths.loc[paths["arm"].isin(["R0", "R3"]), list(up_paths.columns)],
        ["scope", "arm", "issue_order"],
    )
    coverage_eq = _n6_frame_equality(
        up_coverage[list(up_coverage.columns)],
        coverage[list(up_coverage.columns)],
        ["issue", "issue_year"],
    )
    reproduction = _reproduce_n6_bootstrap(settled)
    reproduction_eq = _n6_frame_equality(
        up_bootstrap[list(reproduction.columns)],
        reproduction[list(reproduction.columns)],
        ["scope"],
    )
    contrast_r3 = contrasts[contrasts["arm"].eq("R3")].sort_values(
        ["scope"], kind="stable"
    ).reset_index(drop=True)
    up_lift = up_bootstrap.sort_values(["scope"], kind="stable").reset_index(drop=True)
    point_lift_eq = bool(
        len(contrast_r3) == len(up_lift)
        and np.allclose(
            contrast_r3["matched_lift_cny"].to_numpy(float),
            up_lift["matched_lift_cny"].to_numpy(float),
            rtol=0, atol=1e-9,
        )
        and np.allclose(
            contrast_r3["ex_largest_lift_cny"].to_numpy(float),
            up_lift["ex_largest_lift_cny"].to_numpy(float),
            rtol=0, atol=1e-9,
        )
    )
    result = {
        "manifest_sha256": sha256_file(package / "MANIFEST.json"),
        "decisions_exact": decisions_eq,
        "tickets_exact": tickets_eq,
        "issue_bundles_exact": settled_eq,
        "attribution_exact": attribution_eq,
        "performance_exact": performance_eq,
        "hit_rate_exact": hit_rate_eq,
        "risk_exact": risk_eq,
        "capital_paths_exact": paths_eq,
        "coverage_exact": coverage_eq,
        "bootstrap_reproduction_exact": reproduction_eq,
        "point_lift_exact": point_lift_eq,
        "manifest_files": manifest.get("files"),
    }
    bool_fields = [
        value for key, value in result.items()
        if key not in {"manifest_sha256", "manifest_files"}
    ]
    if not all(value is True for value in bool_fields):
        raise ContractError("R0/R3 exact parity with corrected #376 failed")
    return result


def _canonical_support(value: object) -> str:
    """Canonicalize a set-valued support (string, list or JSON map value) to a
    deterministic outcome-set string so equal sets compare equal regardless of
    member ordering (defect-class fix for the corrected-vs-legacy #352 ledger)."""
    text = "" if pd.isna(value) else str(value)
    if not text:
        return ""
    lowered = text.strip().lstrip("{").rstrip("}")
    members: list[str] = []
    if text.startswith("{") and ":" in text:
        parsed = json.loads(text)
        items = parsed.values() if isinstance(parsed, dict) else parsed
        for item in items:
            members.extend(str(item) if isinstance(item, str) else list(item))
    else:
        members = [char for char in lowered if char in OUTCOMES] or lowered.split(",")
    members = [member.strip() for member in members if member.strip()]
    return "".join(sorted(set(member for member in members if member)))


def legacy_ledger(
    repo_root: Path,
    actions: pd.DataFrame,
    tickets: pd.DataFrame,
    settled: pd.DataFrame,
    attribution: pd.DataFrame,
) -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    """Corrected-versus-legacy #352 ledger over the full R0..R6 grid."""
    legacy_root = repo_root / LEGACY_PACKAGE
    legacy_bundles = pd.read_parquet(legacy_root / "settled_bundles.parquet")
    legacy_bundles = legacy_bundles[legacy_bundles["n"].eq(6)].copy()
    legacy_bundles["arm"] = np.where(legacy_bundles["r"].eq(0), "R0", "R" + legacy_bundles["r"].astype(str))
    if set(legacy_bundles["arm"]) != set(ARMS):
        raise ContractError("legacy N6 package does not contain the full R0..R6 grid")
    old = legacy_bundles.rename(
        columns={name: f"old_{name}" for name in legacy_bundles.columns if name not in ["issue", "arm"]}
    )
    new = settled.rename(
        columns={name: f"new_{name}" for name in settled.columns if name not in ["issue", "arm"]}
    )
    issue_ledger = old.merge(new, on=["issue", "arm"], how="outer", indicator=True)
    for column in ["issue_year", "selected_match_ids", "support_json", "stake_cny", "gross_cny", "pnl_cny", "hit"]:
        left, right = f"old_{column}", f"new_{column}"
        if left in issue_ledger and right in issue_ledger:
            if column in {"stake_cny", "gross_cny", "pnl_cny"}:
                issue_ledger[f"exact_{column}"] = np.isclose(
                    issue_ledger[left], issue_ledger[right], rtol=0, atol=1e-9, equal_nan=False
                )
            elif column == "support_json":
                issue_ledger[f"exact_{column}"] = (
                    issue_ledger[left].astype(object).map(_canonical_support)
                    == issue_ledger[right].astype(object).map(_canonical_support)
                )
            else:
                issue_ledger[f"exact_{column}"] = issue_ledger[left].eq(issue_ledger[right])
    issue_ledger["exact_issue_arm"] = issue_ledger["_merge"].eq("both")
    for column in [
        "exact_issue_year", "exact_selected_match_ids", "exact_support_json",
        "exact_stake_cny", "exact_gross_cny", "exact_pnl_cny", "exact_hit",
    ]:
        issue_ledger["exact_issue_arm"] &= issue_ledger[column]
    common = issue_ledger["_merge"].eq("both")
    year_routing = issue_ledger.loc[
        common & ~issue_ledger["exact_issue_year"],
        ["issue", "arm", "old_issue_year", "new_issue_year"],
    ].copy()
    old_design = pd.read_parquet(legacy_root / "preoutcome_bundles.parquet")
    old_design = old_design[old_design["n"].eq(6)].copy()
    old_design["arm"] = np.where(old_design["r"].eq(0), "R0", "R" + old_design["r"].astype(str))
    new_ticket_summary = tickets.groupby(["issue", "arm"], observed=True).agg(
        new_ticket_count=("ticket_code", "size"),
        new_unique_tickets=("ticket_code", "nunique"),
        new_funded_units=("units", "sum"),
        new_stake_cny=("stake_cny", "sum"),
    ).reset_index()
    ticket_ledger = old_design[[
        "issue", "arm", "ticket_count", "funded_units", "planned_stake_cny"
    ]].rename(columns={
        "ticket_count": "old_ticket_count",
        "funded_units": "old_funded_units",
        "planned_stake_cny": "old_stake_cny",
    }).merge(new_ticket_summary, on=["issue", "arm"], how="outer", indicator=True)
    ticket_ledger["exact_ticket"] = (
        ticket_ledger["_merge"].eq("both")
        & ticket_ledger["old_ticket_count"].eq(ticket_ledger["new_ticket_count"])
        & ticket_ledger["new_ticket_count"].eq(ticket_ledger["new_unique_tickets"])
        & ticket_ledger["old_funded_units"].eq(ticket_ledger["new_funded_units"])
        & np.isclose(ticket_ledger["old_stake_cny"], ticket_ledger["new_stake_cny"], rtol=0, atol=1e-12)
    )
    old_actions = pd.read_parquet(legacy_root / "match_support.parquet")
    new_actions = actions.copy()
    action_ledger = old_actions.merge(
        new_actions,
        on=["issue", "match_idx"], how="outer", suffixes=("_old", "_new"), indicator=True,
    )
    both = action_ledger["_merge"].eq("both")
    action_ledger["exact_year"] = both & action_ledger["issue_year_old"].eq(action_ledger["issue_year_new"])
    action_ledger["exact_baseline_support"] = both & (
        action_ledger["baseline_support_old"].astype(object).map(_canonical_support)
        == action_ledger["baseline_support_new"].astype(object).map(_canonical_support)
    )
    action_ledger["exact_qeu_support"] = both & (
        action_ledger["qeu_support_old"].astype(object).map(_canonical_support)
        == action_ledger["qeu_support_new"].astype(object).map(_canonical_support)
    )
    action_ledger["exact_score_surface"] = (
        both
        & np.isclose(action_ledger["retained_mass_old"], action_ledger["retained_mass_new"], rtol=0, atol=1e-12)
        & np.isclose(action_ledger["support_pressure_old"], action_ledger["support_pressure_new"], rtol=0, atol=1e-12)
    )
    # Per-leg corrected-vs-legacy attribution ledger (n=6).
    legacy_att = pd.read_parquet(legacy_root / "support_attribution.parquet")
    legacy_att = legacy_att[legacy_att["n"].eq(6)].copy()
    legacy_att["arm"] = np.where(legacy_att["r"].eq(0), "R0", "R" + legacy_att["r"].astype(str))
    legacy_att = legacy_att.rename(columns={
        "baseline_support": "old_baseline_support",
        "qeu_support": "old_qeu_support",
        "support": "old_active_support",
        "pressure_rank": "old_pressure_rank",
        "qeu_activated": "old_qeu_activated",
        "result_code": "old_result_code",
        "winning_sp": "old_winning_sp",
        "included": "old_included",
        "settlement_available": "old_settlement_available",
    })
    mine_att = attribution[[
        "issue", "arm", "match_idx", "baseline_support", "qeu_support",
        "active_support", "pressure_rank", "qeu_activated", "result_code",
        "winning_sp", "realized_in_support", "settlement_available",
    ]].copy()
    att_ledger = legacy_att[[
        "issue", "arm", "match_idx", "old_baseline_support", "old_qeu_support",
        "old_active_support", "old_pressure_rank", "old_qeu_activated",
        "old_result_code", "old_winning_sp", "old_included",
        "old_settlement_available",
    ]].merge(mine_att, on=["issue", "arm", "match_idx"], how="outer", indicator=True)
    att_both = att_ledger["_merge"].eq("both")
    att_ledger["exact_active_support"] = att_both & (
        att_ledger["old_active_support"].astype(object).map(_canonical_support)
        == att_ledger["active_support"].astype(object).map(_canonical_support)
    )
    att_ledger["exact_result_code"] = att_both & att_ledger["old_result_code"].eq(
        att_ledger["result_code"]
    )
    att_ledger["exact_winning_sp"] = att_both & np.isclose(
        att_ledger["old_winning_sp"], att_ledger["winning_sp"], rtol=0, atol=1e-9, equal_nan=False
    )
    att_ledger["exact_realized_in_support"] = att_both & att_ledger["old_included"].eq(
        att_ledger["realized_in_support"]
    )
    att_ledger["exact_settlement_available"] = att_both & att_ledger["old_settlement_available"].eq(
        att_ledger["settlement_available"]
    )
    att_ledger["exact_leg"] = (
        att_ledger["exact_active_support"] & att_ledger["exact_result_code"]
        & att_ledger["exact_winning_sp"] & att_ledger["exact_realized_in_support"]
        & att_ledger["exact_settlement_available"]
    )
    summary_rows: list[dict[str, Any]] = []
    totals = {
        "old": 0, "new": 0, "common": 0, "exact": 0, "changed_pnl": 0,
        "year_changed": 0, "old_only": 0, "new_only": 0,
        "att_common": 0, "att_exact": 0,
    }
    for arm in ARMS:
        sub = issue_ledger[issue_ledger["arm"].eq(arm)]
        common_arm = sub["_merge"].eq("both")
        changed_pnl = int((common_arm & ~sub["exact_pnl_cny"]).sum())
        year_changed = int((common_arm & ~sub["exact_issue_year"]).sum())
        att_sub = att_ledger[att_ledger["arm"].eq(arm)]
        att_common = int(att_sub["_merge"].eq("both").sum())
        att_exact = int(att_sub["exact_leg"].sum())
        old_only = int((sub["_merge"].eq("left_only")).sum())
        new_only = int((sub["_merge"].eq("right_only")).sum())
        summary_rows.append(
            {
                "arm": arm,
                "legacy_rows": int((sub["_merge"].isin(["both", "left_only"])).sum()),
                "corrected_rows": int((sub["_merge"].isin(["both", "right_only"])).sum()),
                "common_issues": int(common_arm.sum()),
                "exact_rows": int(sub["exact_issue_arm"].sum()),
                "changed_pnl_rows": changed_pnl,
                "year_routing_changed_rows": year_changed,
                "legacy_only_issue_arm_rows": old_only,
                "corrected_only_issue_arm_rows": new_only,
                "attribution_common_legs": att_common,
                "attribution_exact_legs": att_exact,
            }
        )
        totals["old"] += int((sub["_merge"].isin(["both", "left_only"])).sum())
        totals["new"] += int((sub["_merge"].isin(["both", "right_only"])).sum())
        totals["common"] += int(common_arm.sum())
        totals["exact"] += int(sub["exact_issue_arm"].sum())
        totals["changed_pnl"] += changed_pnl
        totals["year_changed"] += year_changed
        totals["old_only"] += old_only
        totals["new_only"] += new_only
        totals["att_common"] += att_common
        totals["att_exact"] += att_exact
    all_left = issue_ledger["_merge"].eq("left_only")
    all_right = issue_ledger["_merge"].eq("right_only")
    summary_rows.append(
        {
            "arm": "ALL", "legacy_rows": totals["old"], "corrected_rows": totals["new"],
            "common_issues": totals["common"], "exact_rows": totals["exact"],
            "changed_pnl_rows": totals["changed_pnl"],
            "year_routing_changed_rows": totals["year_changed"],
            "legacy_only_issue_arm_rows": totals["old_only"],
            "corrected_only_issue_arm_rows": totals["new_only"],
            "legacy_only_unique_issues": int(issue_ledger.loc[all_left, "issue"].nunique()),
            "corrected_only_unique_issues": int(issue_ledger.loc[all_right, "issue"].nunique()),
            "attribution_common_legs": totals["att_common"],
            "attribution_exact_legs": totals["att_exact"],
        }
    )
    summary = pd.DataFrame(summary_rows)
    return (
        pd.DataFrame(issue_ledger), pd.DataFrame(ticket_ledger),
        pd.DataFrame(action_ledger), pd.DataFrame(att_ledger),
        year_routing, summary,
    )


def _decision(
    performance: pd.DataFrame,
    contrasts: pd.DataFrame,
    parity: dict[str, Any],
    legacy_summary: pd.DataFrame,
    attribution: pd.DataFrame,
) -> dict[str, Any]:
    all_perf = performance[performance["scope"].eq("ALL")].set_index("arm")
    all_contrast = contrasts[contrasts["scope"].eq("ALL")].set_index("arm")
    replaced = attribution["support_changed"]
    return {
        "contract": CONTRACT_ID,
        "verdict": "FIXED_R_GRID_EXPOSED_DIAGNOSTIC_COMPLETE",
        "r_grid": list(R_GRID),
        "arms": list(ARMS),
        "r3_canonical_unchanged": True,
        "r0_r3_exact_parity_376": bool(
            parity["decisions_exact"] and parity["tickets_exact"]
            and parity["issue_bundles_exact"] and parity["attribution_exact"]
            and parity["performance_exact"] and parity["hit_rate_exact"]
            and parity["risk_exact"]
            and parity["capital_paths_exact"] and parity["coverage_exact"]
            and parity["bootstrap_reproduction_exact"] and parity["point_lift_exact"]
        ),
        "legacy_common_issue_arm_rows": int(
            legacy_summary.loc[legacy_summary["arm"].eq("ALL"), "common_issues"].iloc[0]
        ),
        "legacy_changed_pnl_rows": int(
            legacy_summary.loc[legacy_summary["arm"].eq("ALL"), "changed_pnl_rows"].iloc[0]
        ),
        "replacement_disclosure": {
            "replaced_legs_total": int(replaced.sum()),
            "dropped_probability_first_legs": int(
                attribution.loc[replaced, "dropped_is_probability_first"].sum()
            ),
            "noop_activated_legs_total": int(attribution["noop_activation"].sum()),
            "candidate_set_size_max": int(attribution["candidate_set_size"].max()),
            "saturated_legs": int(attribution["saturated"].sum()),
            "protocol_log": "docs/research/Issue-381-PROTOCOL-LOG.md entry 001",
        },
        "corrected_r0_pnl_cny": float(all_perf.loc["R0", "pnl_cny"]),
        "corrected_r3_pnl_cny": float(all_perf.loc["R3", "pnl_cny"]),
        "corrected_r3_lift_r0_cny": float(all_contrast.loc["R3", "matched_lift_cny"]),
        "non_r3_positive_standalone_arms": [
            str(arm) for arm in ARMS
            if arm != "R3" and float(all_perf.loc[arm, "pnl_cny"]) > 0
        ],
        "promotable_to_210": False,
        "evidence_boundary": "EXPOSED_HISTORICAL_DIAGNOSTIC_ONLY",
        "consumers": {
            "378": "non-R3 comparator admitted as exposed diagnostic evidence only",
            "210": "unchanged",
            "218": "unchanged",
        },
    }


def scientific_frames(repo_root: Path, data_root: Path) -> dict[str, Any]:
    cells, settlement, source = load_corrected_cells(repo_root, data_root)
    actions = prepare_actions(cells)
    decisions, tickets, settled, attribution, coverage, saturation = construct_r_arms(actions)
    performance, risk, runs, paths, path_bootstrap, rolling = evaluate_r_grid(settled)
    contrasts = matched_contrasts(settled)
    n6_parity = parity_with_n6(
        repo_root, decisions, tickets, settled, attribution,
        performance, risk, paths, contrasts, coverage,
    )
    issue_ledger, ticket_ledger, action_ledger, attribution_ledger, year_routing, legacy_summary = legacy_ledger(
        repo_root, actions, tickets, settled, attribution
    )
    decision = _decision(performance, contrasts, n6_parity, legacy_summary, attribution)
    source["contract"] = CONTRACT_ID
    source["corrected_source_contract"] = (
        "BJ-UNIFIED-LOWN-CHRONOLOGY-CORRECTION-001/v2"
    )
    source["upstream_n6_contract"] = "BJ-UNIFIED-N6-CHRONOLOGY-SYNC-001/v1"
    source["upstream_n6_manifest_sha256"] = n6_parity["manifest_sha256"]
    changed_legs = attribution.loc[
        attribution["support_changed"], "dropped_is_probability_first"
    ]
    source["arms_receipt"] = {
        "r_grid": list(R_GRID),
        "arms": list(ARMS),
        "definition": (
            "fixed R: on the top-R support-pressure legs apply the accepted #376 "
            "QEU Top-2 replacement (replace the QEU-second-ranked support member "
            "with the QEU-ranked omitted outcome); R0 activates nothing; R3 equals "
            "corrected #376 fixed R3. PROTOCOL-LOG entry 001 records the "
            "interpretation disclosure (dropped member can be the probability-first "
            "pair member; parity with #376 is binding)."
        ),
        "saturation": (
            "Mx3 construction yields a singleton omitted-outcome candidate set on "
            "every leg; set-based saturation (candidate set size > 1) never occurs. "
            "Activated no-op count is disclosed per arm in depth_saturation.csv."
        ),
        "replaced_legs_total": int(attribution["support_changed"].sum()),
        "dropped_probability_first_legs": int(changed_legs.sum()),
        "noop_activated_legs_total": int(attribution["noop_activation"].sum()),
    }
    return {
        "source": source,
        "actions": actions,
        "decisions": decisions,
        "tickets": tickets,
        "settled": settled,
        "attribution": attribution,
        "coverage": coverage,
        "saturation": saturation,
        "performance": performance,
        "risk": risk,
        "runs": runs,
        "paths": paths,
        "path_bootstrap": path_bootstrap,
        "rolling": rolling,
        "contrasts": contrasts,
        "n6_parity": n6_parity,
        "issue_ledger": issue_ledger,
        "ticket_ledger": ticket_ledger,
        "action_ledger": action_ledger,
        "attribution_ledger": attribution_ledger,
        "year_routing": year_routing,
        "legacy_summary": legacy_summary,
        "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "action_receipts.parquet": "actions",
    "decisions.parquet": "decisions",
    "tickets.parquet": "tickets",
    "issue_bundles.parquet": "settled",
    "support_attribution.parquet": "attribution",
    "coverage_ledger.csv": "coverage",
    "depth_saturation.csv": "saturation",
    "performance.csv": "performance",
    "risk_diagnostics.csv": "risk",
    "losing_run_diagnostics.csv": "runs",
    "capital_paths.csv": "paths",
    "path_bootstrap.csv": "path_bootstrap",
    "rolling_windows.csv": "rolling",
    "matched_contrasts.csv": "contrasts",
    "n6_parity.json": "n6_parity",
    "legacy_issue_ledger.parquet": "issue_ledger",
    "legacy_ticket_ledger.parquet": "ticket_ledger",
    "legacy_action_ledger.parquet": "action_ledger",
    "legacy_attribution_ledger.parquet": "attribution_ledger",
    "legacy_year_routing.csv": "year_routing",
    "legacy_summary.csv": "legacy_summary",
    "decision.json": "decision",
}


def _write_value(path: Path, value: Any) -> None:
    if isinstance(value, pd.DataFrame):
        if path.suffix == ".parquet":
            value.to_parquet(path, index=False)
        else:
            value.to_csv(path, index=False)
    else:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_package(
    repo_root: Path,
    target: Path,
    explicit_data_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    frames = scientific_frames(repo_root, data_root)

    def populate(staging: Path) -> None:
        for relative, key in PACKAGE_FILES.items():
            _write_value(staging / relative, frames[key])
        manifest = {
            "contract": CONTRACT_ID,
            "files": {
                relative: {"sha256": sha256_file(staging / relative), "bytes": (staging / relative).stat().st_size}
                for relative in sorted(PACKAGE_FILES)
            },
            "frame_hashes": {
                key: stable_frame_sha(value) for key, value in frames.items() if isinstance(value, pd.DataFrame)
            },
            "implementation": {
                "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
                "pipeline.py": sha256_file(Path(__file__)),
            },
        }
        (staging / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    atomic_publish_directory(target.resolve(), populate, force=force)
    return frames["decision"]


def verify_package(
    repo_root: Path, target: Path, explicit_data_root: Path | None = None
) -> dict[str, bool]:
    repo_root = repo_root.resolve()
    target = target.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    manifest = _read_json(target / "MANIFEST.json")
    if manifest.get("contract") != CONTRACT_ID or set(manifest.get("files", {})) != set(PACKAGE_FILES):
        raise ContractError("manifest contract or exact file set mismatch")
    for relative, receipt in manifest["files"].items():
        path = target / relative
        if (
            not path.is_file()
            or sha256_file(path) != receipt["sha256"]
            or receipt.get("bytes") != path.stat().st_size
        ):
            raise ContractError(f"manifest file sha256 or byte-size mismatch: {relative}")
    implementation = manifest.get("implementation", {})
    if implementation != {
        "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
        "pipeline.py": sha256_file(Path(__file__)),
    }:
        raise ContractError("implementation hashes do not match current code")
    expected_delivery = {
        "docs/research/Issue-381-N6-All-R-Diagnostic.md",
        "docs/research/Issue-381-PROTOCOL-LOG.md",
        "docs/research/figures/issue_381_n6_all_r_capital.png",
        "docs/research/figures/issue_381_n6_all_r_lift.png",
        "notebooks/research/n6-all-r-diagnostic/n6_all_r_diagnostic.ipynb",
    }
    if set(manifest.get("delivery", {})) != expected_delivery:
        raise ContractError("delivery receipt file set mismatch")
    for relative, expected_hash in manifest["delivery"].items():
        delivery_path = repo_root / relative
        if not delivery_path.is_file() or sha256_file(delivery_path) != expected_hash:
            raise ContractError(f"delivery hash mismatch: {relative}")
    source_receipt = _read_json(target / "source_receipt.json")
    if (
        source_receipt.get("contract") != CONTRACT_ID
        or source_receipt.get("chronology")
        != "SOURCE_ISSUE_REGISTRY_YEAR + FIXTURE_RELATIVE_10H"
        or source_receipt.get("corrected_source_contract")
        != "BJ-UNIFIED-LOWN-CHRONOLOGY-CORRECTION-001/v2"
        or source_receipt.get("arms_receipt", {}).get("r_grid") != list(R_GRID)
    ):
        raise ContractError("source receipt contract, chronology or R-grid mismatch")

    # upstream #360 and #376 must verify before anything else
    if not all(verify_corrected_source(repo_root, repo_root / CORRECTED_PACKAGE, data_root).values()):
        raise ContractError("#360 source-bound verifier did not pass")
    from src.n6_chronology_sync.pipeline import verify_package as verify_n6_package
    if not all(verify_n6_package(repo_root, repo_root / UPSTREAM_N6_PACKAGE, data_root).values()):
        raise ContractError("#376 upstream verifier did not pass")

    expected = scientific_frames(repo_root, data_root)
    recomputed_frame_hashes = {
        key: stable_frame_sha(value)
        for key, value in expected.items()
        if isinstance(value, pd.DataFrame) and key in PACKAGE_FILES.values()
    }
    recorded_frame_hashes = {
        key: value for key, value in manifest.get("frame_hashes", {}).items()
        if key in PACKAGE_FILES.values()
    }
    if recorded_frame_hashes != recomputed_frame_hashes:
        raise ContractError("manifest frame_hashes do not match recomputed frames")
    for relative, key in PACKAGE_FILES.items():
        path = target / relative
        if isinstance(expected[key], pd.DataFrame):
            if path.suffix == ".parquet":
                actual = pd.read_parquet(path)
                matches = actual.equals(expected[key])
            else:
                payload = expected[key].to_csv(index=False).encode("utf-8")
                matches = hashlib.sha256(payload).hexdigest() == sha256_file(path)
            if not matches:
                raise ContractError(f"scientific frame mismatch: {relative}")
        elif _read_json(path) != expected[key]:
            raise ContractError(f"receipt mismatch: {relative}")

    tickets = expected["tickets"]
    groups = tickets.groupby(["issue", "arm"], observed=True)
    if not groups.size().eq(TICKETS).all() or not groups["ticket_code"].nunique().eq(TICKETS).all():
        raise ContractError("ticket groups are not exact 64-ticket Cartesian sets")
    if not groups["units"].sum().eq(FUNDED_UNITS).all() or not np.isclose(
        groups["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-12
    ).all():
        raise ContractError("ticket funding semantics mismatch")
    decisions_frame = expected["decisions"]
    expected_keys = set(map(tuple, decisions_frame[["issue", "arm"]].to_numpy()))
    if set(groups.groups) != expected_keys:
        raise ContractError("ticket group keys differ from decisions")
    bundles = expected["settled"]
    if not np.allclose(
        bundles["pnl_cny"], bundles["gross_cny"] - bundles["stake_cny"],
        rtol=0, atol=1e-9,
    ):
        raise ContractError("bundle PnL identity failed")
    attribution = expected["attribution"]
    r3 = attribution[attribution["arm"].eq("R3")]
    expected_r3_support = np.where(
        r3["pressure_rank"].le(3), r3["qeu_support"], r3["baseline_support"]
    )
    if not np.array_equal(r3["active_support"].to_numpy(), expected_r3_support):
        raise ContractError("arm R3 support semantics deviate from corrected #376")
    for r in R_GRID:
        arm_rows = attribution[attribution["arm"].eq(ARMS[r])]
        oracle = np.where(
            arm_rows["pressure_rank"].le(r),
            arm_rows["qeu_support"],
            arm_rows["baseline_support"],
        )
        if not np.array_equal(arm_rows["active_support"].to_numpy(), oracle):
            raise ContractError(f"arm {ARMS[r]} support semantics deviate from fixed-R oracle")
    if not attribution["candidate_set_size"].eq(1).all() or attribution["saturated"].any():
        raise ContractError("set-based replacement saturation disclosure violated")
    contrasts = expected["contrasts"]
    all_contrast = contrasts[contrasts["scope"].eq("ALL")].set_index("arm")
    if not set(all_contrast.index).issubset(set(ARMS)):
        raise ContractError("contrast rows deviate from the fixed R grid")
    report = repo_root / "docs/research/Issue-381-N6-All-R-Diagnostic.md"
    protocol_log = repo_root / "docs/research/Issue-381-PROTOCOL-LOG.md"
    notebook = repo_root / "notebooks/research/n6-all-r-diagnostic/n6_all_r_diagnostic.ipynb"
    figures = [
        repo_root / "docs/research/figures/issue_381_n6_all_r_capital.png",
        repo_root / "docs/research/figures/issue_381_n6_all_r_lift.png",
    ]
    if not report.is_file() or CONTRACT_ID not in report.read_text(encoding="utf-8"):
        raise ContractError("research report is missing or not contract-bound")
    if not protocol_log.is_file() or "PROTOCOL-LOG" not in protocol_log.read_text(encoding="utf-8"):
        raise ContractError("protocol log delivery is missing or malformed")
    if not notebook.is_file():
        raise ContractError("notebook delivery is missing")
    for figure in figures:
        if not figure.is_file() or figure.stat().st_size <= 0:
            raise ContractError("figure delivery is missing")
    executed = nbformat.read(notebook, as_version=4)
    code_cells = [cell for cell in executed.cells if cell.cell_type == "code"]
    if not code_cells or any(cell.get("execution_count") is None for cell in code_cells):
        raise ContractError("notebook is not fully executed")
    return {
        "manifest": True,
        "source_bound_replay": True,
        "corrected_chronology": True,
        "upstream_n6_verified": True,
        "fixed_r_grid": True,
        "r3_support_semantics": True,
        "ticket_budget_and_payout": True,
        "settlement_reconciliation": True,
        "r0_r3_exact_parity_376": True,
        "legacy_ledger_receipts": True,
        "exact_common_scopes": True,
        "delivery_artifacts": True,
    }


def build_notebook_and_report(repo_root: Path, package: Path) -> None:
    notebook_path = repo_root / "notebooks/research/n6-all-r-diagnostic/n6_all_r_diagnostic.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell("# Issue #381 — corrected N6 fixed R0..R6 complete surface"),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\nROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/n6_all_r_diagnostic'"
        ),
        nbformat.v4.new_code_cell(
            "performance=pd.read_csv(OUT/'performance.csv')\nrisk=pd.read_csv(OUT/'risk_diagnostics.csv')\ncontrasts=pd.read_csv(OUT/'matched_contrasts.csv')\ncoverage=pd.read_csv(OUT/'coverage_ledger.csv')\nlegacy=pd.read_csv(OUT/'legacy_summary.csv')\nperformance"
        ),
        nbformat.v4.new_code_cell("risk"),
        nbformat.v4.new_code_cell("contrasts"),
        nbformat.v4.new_code_cell(
            "legacy"
        ),
        nbformat.v4.new_code_cell(
            "coverage_summary=(coverage.groupby(['issue_year','settlement_complete'],dropna=False).size().rename('issues').reset_index())\ncoverage_summary"
        ),
        nbformat.v4.new_code_cell(
            "paths=pd.read_csv(OUT/'capital_paths.csv')\nfig,ax=plt.subplots(figsize=(10,5))\nfor arm,g in paths[paths.scope.eq('ALL')].groupby('arm'):\n    ax.plot(g.issue_order,g.capital_cny,label=arm)\nax.axhline(100000,color='black',lw=.8); ax.legend(title='arm'); ax.set_title('Corrected N6 fixed-R capital paths (ALL)'); plt.show()"
        ),
        nbformat.v4.new_code_cell(
            "lift=contrasts[contrasts.arm.ne('R0')]\nfig,ax=plt.subplots(figsize=(10,4))\nfor scope,g in lift.groupby('scope'):\n    ax.plot(g.arm,g.matched_lift_cny,marker='o',label=scope)\nax.axhline(0,color='black',lw=.8); ax.legend(); ax.set_title('Matched lift vs corrected R0'); plt.show()"
        ),
        nbformat.v4.new_code_cell(
            "rolling=pd.read_csv(OUT/'rolling_windows.csv')\nrolling"
        ),
    ]
    NotebookClient(nb, timeout=600, kernel_name="python3").execute(cwd=str(notebook_path.parent))
    nbformat.write(nb, notebook_path)

    performance = pd.read_csv(package / "performance.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    contrasts = pd.read_csv(package / "matched_contrasts.csv")
    coverage = pd.read_csv(package / "coverage_ledger.csv")
    legacy = pd.read_csv(package / "legacy_summary.csv")
    n6_parity = _read_json(package / "n6_parity.json")
    decision = _read_json(package / "decision.json")
    paths = pd.read_csv(package / "capital_paths.csv")
    saturation = pd.read_csv(package / "depth_saturation.csv")

    figure = repo_root / "docs/research/figures/issue_381_n6_all_r_capital.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    for arm, group in paths[paths["scope"].eq("ALL")].groupby("arm"):
        ax.plot(group["issue_order"], group["capital_cny"], label=arm)
    ax.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8)
    ax.legend(title="arm")
    ax.set_title("Issue #381 corrected N6 fixed-R capital paths (ALL)")
    fig.tight_layout()
    fig.savefig(figure, dpi=160)
    plt.close(fig)

    lift_figure = repo_root / "docs/research/figures/issue_381_n6_all_r_lift.png"
    fig, ax = plt.subplots(figsize=(10, 4))
    for scope, group in contrasts[contrasts["arm"].ne("R0")].groupby("scope"):
        ax.plot(group["arm"], group["matched_lift_cny"], marker="o", label=scope)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.legend()
    ax.set_title("Issue #381 matched lift vs corrected R0")
    fig.tight_layout()
    fig.savefig(lift_figure, dpi=160)
    plt.close(fig)

    def table(frame: pd.DataFrame) -> str:
        rendered = frame.copy()
        for column in rendered.select_dtypes(include=["float"]).columns:
            rendered[column] = rendered[column].map(lambda value: f"{value:.4f}")
        def render(value: Any) -> str:
            try:
                return "-" if pd.isna(value) else str(value)
            except (TypeError, ValueError):
                return str(value)
        header = "| " + " | ".join(rendered.columns) + " |"
        separator = "|" + "|".join("---" for _ in rendered.columns) + "|"
        rows = ["| " + " | ".join(map(render, row)) + " |" for row in rendered.itertuples(index=False, name=None)]
        return "\n".join([header, separator, *rows])

    disclosure = decision["replacement_disclosure"]
    protocol_log = repo_root / "docs/research/Issue-381-PROTOCOL-LOG.md"
    protocol_text = f"""# Issue #381 — PROTOCOL-LOG

Contract: `{CONTRACT_ID}`. Append-only interpretation record; new entries
`supersede` earlier rows where noted.

## Entry 001 — Fixed-R replacement-rule interpretation disclosure

- **Date / artifact**: 2026-08-24, Issue #381 build (analyst/bj381-n6-all-r branch).
- **Frozen text**: "fixed R means replace the second outcome with the
  QEU-ranked omitted outcome on the top-R support-pressure legs, with set-based
  saturation disclosed."
- **Applied reading**: the replacement is the accepted corrected #376 QEU Top-2
  transfer: on an activated leg the active support becomes
  `OUTCOMES - qeu_worst`, i.e. the baseline pair member that QEU ranks second
  is replaced by the QEU-ranked omitted outcome whenever the omitted outcome
  ranks above it (support pressure > 0). The dropped member can therefore be
  the probability-first pair member while still being QEU-second; on
  pressure-zero activated legs the support is unchanged (noop activation).
- **Why**: the issue requires exact R0/R3 parity with the corrected #376
  package; #376's accepted fixed-R3 definition IS the QEU Top-2 transfer.
  A literal "always keep the probability-first member" swap would break that
  parity on the {disclosure['dropped_probability_first_legs']} legs where the
  dropped member is the probability-first pair member.
- **Disclosure table (settled panel)**:
  - replaced legs total: **{disclosure['replaced_legs_total']}**
  - dropped member is the probability-first pair member: **{disclosure['dropped_probability_first_legs']}**
  - activated no-op legs (activated, support unchanged): **{disclosure['noop_activated_legs_total']}**
  - candidate (omitted-outcome) set size: max **{disclosure['candidate_set_size_max']}** (Mx3 => always 1)
  - set-based saturation events: **{disclosure['saturated_legs']}** (structural zero)
- **Status**: interpretation recorded; no frozen numerical parameter changed.
  May be superseded only by a PI ruling amending the contract text.
"""
    (repo_root / "docs/research/Issue-381-PROTOCOL-LOG.md").write_text(protocol_text, encoding="utf-8")

    sat_total = saturation.groupby("arm", as_index=False).agg(
        activated_legs=("activated_legs", "sum"),
        noop_legs=("noop_legs", "sum"),
        replaced_legs=("replaced_legs", "sum"),
        saturated_legs=("saturated_legs", "sum"),
    )
    report = f"""# Issue #381 — corrected N6 fixed R0..R6 complete surface

Contract: `{CONTRACT_ID}`

## Decision

`{decision['verdict']}`. This is an exposed historical fixed-R diagnostic matrix,
not an R-selection exercise. `promotable_to_210=false`; **no exposed winner
replaces fixed R3**, #210/#218 stay unchanged, and a non-R3 positive standalone
point estimate may enter #378 only as an exposed diagnostic comparator.

Corrected R0/R3 exact parity with #376: **{decision['r0_r3_exact_parity_376']}**.
Legacy #352 common issue-arm rows changed in PnL: **{decision['legacy_changed_pnl_rows']} / {decision['legacy_common_issue_arm_rows']}**.

## Corrected per-arm performance (ALL scope)

{table(performance[performance['scope'].eq('ALL')])}

## Path risk (ALL scope)

{table(risk[risk['scope'].eq('ALL')])}

## Matched lift versus corrected R0 and bootstrap stability

{table(contrasts)}

The issue bootstrap and the chronology-preserving moving-block bootstrap
(block length {MOVING_BLOCK_LENGTH}, {BOOTSTRAP_DRAWS} draws) both remain
negative at their p05 bounds for most arms, consistent with the historical
long-tail challenge established for corrected R3 in #376.

## Rolling 20/30/50-issue windows (ALL scope)

{table(pd.read_csv(package / 'rolling_windows.csv'))}

## Action-depth saturation and set-based replacement attribution

{table(sat_total)}

The Mx3 construction leaves exactly one omitted outcome per leg, so the
candidate replacement set is always a singleton; `saturated_legs == 0` is
structural and disclosed rather than assumed. `noop_legs` records activated
legs whose support is unchanged (pressure-zero). Per-leg replacement detail,
including replaced/replacement outcomes, activation depth and the
`dropped_is_probability_first` flag, is in `support_attribution.parquet`.

## Replacement-rule interpretation disclosure

{disclosure['replaced_legs_total']} replaced legs in total, of which
**{disclosure['dropped_probability_first_legs']}** drop the probability-first
pair member under the accepted #376 QEU Top-2 transfer; activated no-op legs:
**{disclosure['noop_activated_legs_total']}**. Candidate set size max
{disclosure['candidate_set_size_max']}; saturation events
{disclosure['saturated_legs']}. See
`docs/research/Issue-381-PROTOCOL-LOG.md` entry 001.

## Settlement coverage

{table(coverage.groupby(['issue_year', 'settlement_complete'], dropna=False).size().rename('issues').reset_index())}

The corrected registry contains **{coverage['issue'].nunique()}** issues. Exactly
**{int(coverage['settlement_complete'].sum())}** issues are settled on the
exact-common denominator across all seven arms.

## Exact R0/R3 parity with corrected #376

| check | result |
|---|---|
| decisions | {n6_parity['decisions_exact']} |
| tickets | {n6_parity['tickets_exact']} |
| issue bundles | {n6_parity['issue_bundles_exact']} |
| support attribution | {n6_parity['attribution_exact']} |
| performance | {n6_parity['performance_exact']} |
| risk diagnostics | {n6_parity['risk_exact']} |
| capital paths | {n6_parity['capital_paths_exact']} |
| coverage ledger | {n6_parity['coverage_exact']} |
| #376 bootstrap reproduction | {n6_parity['bootstrap_reproduction_exact']} |
| point matched lift | {n6_parity['point_lift_exact']} |

## Corrected-versus-legacy #352 ledger (R0..R6)

{table(legacy)}

## Evidence boundary

- Upstream is the verified corrected #376 package only; #352 is never a source surface.
- Registry year and fixture-relative 10h decision time come from the source-bound
  #360 contract; every training label is strictly earlier than its fixture decision.
- R grid is exactly 0..6. No dynamic R, thresholds, selector retuning, seed mining,
  allocator search, or post-outcome R selection is used.
- 2022–2024 are exposed historical evidence; no row is holdout or tuning data.
- #210 and #218 are unchanged. #378 may consume non-R3 arms only as exposed
  diagnostic comparators.

## Artifacts

- Package: `results/n6_all_r_diagnostic/`
- Notebook: `notebooks/research/n6-all-r-diagnostic/n6_all_r_diagnostic.ipynb`
- Figures: `docs/research/figures/issue_381_n6_all_r_capital.png`,
  `docs/research/figures/issue_381_n6_all_r_lift.png`
- Protocol log: `docs/research/Issue-381-PROTOCOL-LOG.md` (interpretation disclosure)
"""
    (repo_root / "docs/research/Issue-381-N6-All-R-Diagnostic.md").write_text(report, encoding="utf-8")
    manifest_path = package / "MANIFEST.json"
    manifest = _read_json(manifest_path)
    delivery = {
        "docs/research/Issue-381-N6-All-R-Diagnostic.md": sha256_file(
            repo_root / "docs/research/Issue-381-N6-All-R-Diagnostic.md"
        ),
        "docs/research/Issue-381-PROTOCOL-LOG.md": sha256_file(protocol_log),
        "docs/research/figures/issue_381_n6_all_r_capital.png": sha256_file(figure),
        "docs/research/figures/issue_381_n6_all_r_lift.png": sha256_file(lift_figure),
        "notebooks/research/n6-all-r-diagnostic/n6_all_r_diagnostic.ipynb": sha256_file(notebook_path),
    }
    manifest["delivery"] = delivery
    atomic_write_json(manifest_path, manifest)