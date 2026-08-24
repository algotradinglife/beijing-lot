"""Corrected-N7 R3 support-transfer count grid and path-risk frontier."""

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

from src.n7_chronology_sync.pipeline import locate_data_root
from src.n7_support_shape.pipeline import (
    scientific_frames as support_shape_frames,
    verify_package as verify_support_shape,
)
from src.source_schema.publication import atomic_publish_directory, atomic_write_json

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CELLS,
    CONTRACTION_COUNTS,
    CONTRACT_ID,
    CONTROL_CELL,
    CONTROL_EXPECTED_369_ROWS,
    CONTROL_EXPECTED_R3_ROWS,
    EXPANSION_COUNTS,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    MAX_ACCEPTABLE_DRAWDOWN_DELTA,
    MAX_ACCEPTABLE_LOSING_RUN,
    MOVING_BLOCK_LENGTH,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    PRIORITY_CELLS,
    ROLLING_WINDOWS,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    UPSTREAM_PACKAGE,
    YEARS,
)


class ContractError(ValueError):
    """Raised when a frozen research invariant fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    columns = sorted(frame.columns)
    projected = frame.loc[:, columns].copy()
    for name in columns:
        if isinstance(projected[name].dtype, pd.CategoricalDtype):
            projected[name] = projected[name].astype("string")
    hashes = np.sort(
        pd.util.hash_pandas_object(projected, index=False, categorize=False).to_numpy(np.uint64)
    )
    schema = [(name, str(projected[name].dtype)) for name in columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode())
    digest.update(hashes.tobytes())
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_cell(cell: str) -> tuple[int, int]:
    contraction, expansion = cell.removeprefix("C").split("E")
    return int(contraction), int(expansion)


def _ticket_count(contraction: int, expansion: int) -> int:
    return 2 ** (N_LEGS - contraction - expansion) * 3**expansion


def validate_development_diagnostics(summary: pd.DataFrame) -> None:
    required = {
        ("R0_CORRECTED", "contraction_score"),
        ("R0_CORRECTED", "expansion_score"),
        ("R3_CORRECTED", "contraction_score"),
        ("R3_CORRECTED", "expansion_score"),
    }
    keys = set(map(tuple, summary[["base", "diagnostic"]].to_numpy()))
    if keys != required or len(summary) != 4:
        raise ContractError("development diagnostic key set is incomplete")
    values = summary["nonnegative_monotonicity"]
    if values.dtype != bool or not values.eq(True).all():  # noqa: E712 - strict bool contract
        raise ContractError("development monotonicity gate is not strictly true")


def validate_control_keysets(grid_control: pd.DataFrame, upstream_control: pd.DataFrame) -> None:
    if len(upstream_control) != CONTROL_EXPECTED_369_ROWS:
        raise ContractError("#369 full CONTROL row count is not 302")
    upstream_r3 = upstream_control[upstream_control["base"].eq("R3_CORRECTED")].copy()
    if len(upstream_r3) != CONTROL_EXPECTED_R3_ROWS or len(grid_control) != CONTROL_EXPECTED_R3_ROWS:
        raise ContractError("corrected R3 CONTROL row count is not 151")
    upstream_keys = set(map(tuple, upstream_r3[["issue", "base"]].to_numpy()))
    grid_keys = set(map(tuple, grid_control[["issue", "base"]].to_numpy()))
    if grid_keys != upstream_keys:
        raise ContractError("CONTROL key sets differ before parity merge")
    grid_projection = grid_control[["issue", "base", "gross_cny", "pnl_cny", "ticket_hit"]].rename(
        columns={"ticket_hit": "hit"}
    )
    merged = grid_projection.merge(
        upstream_r3[["issue", "base", "gross_cny", "pnl_cny", "hit"]],
        on=["issue", "base"],
        suffixes=("_grid", "_369"),
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    exact = (
        merged["_merge"].eq("both")
        & np.isclose(merged["gross_cny_grid"], merged["gross_cny_369"], rtol=0, atol=1e-9)
        & np.isclose(merged["pnl_cny_grid"], merged["pnl_cny_369"], rtol=0, atol=1e-9)
        & merged["hit_grid"].eq(merged["hit_369"])
    )
    if not exact.all():
        raise ContractError("C0E0 does not exactly reproduce #369 corrected R3 CONTROL")


def _maximal_assignment(group: pd.DataFrame) -> tuple[list[int], list[int]]:
    """Anchor #369 c1/e1, then freeze a disjoint nested C2/E3 assignment."""

    if len(group) != N_LEGS or group["match_idx"].nunique() != N_LEGS:
        raise ContractError("shape rank receipt is not exact N7")
    c_anchor = group[group["chosen_contraction"]]
    e_anchor = group[group["chosen_expansion"]]
    if len(c_anchor) != 1 or len(e_anchor) != 1:
        raise ContractError("#369 c1/e1 anchor is not unique")
    c1 = int(c_anchor.iloc[0]["match_idx"])
    e1 = int(e_anchor.iloc[0]["match_idx"])
    if c1 == e1:
        raise ContractError("#369 anchor is not disjoint")
    c_rank = group.set_index("match_idx")["contraction_rank"].astype(int).to_dict()
    e_rank = group.set_index("match_idx")["expansion_rank"].astype(int).to_dict()
    fixtures = sorted(group["match_idx"].astype(int))
    candidates: list[tuple[tuple[Any, ...], int, int, int]] = []
    for c2 in fixtures:
        if c2 in {c1, e1}:
            continue
        remaining = [fixture for fixture in fixtures if fixture not in {c1, c2, e1}]
        for e2, e3 in itertools.combinations(remaining, 2):
            e2, e3 = sorted((e2, e3), key=lambda fixture: (e_rank[fixture], fixture))
            ranks = (c_rank[c1], c_rank[c2], e_rank[e1], e_rank[e2], e_rank[e3])
            objective = (
                sum(ranks), max(ranks), c_rank[c2], e_rank[e2], e_rank[e3],
                c1, c2, e1, e2, e3,
            )
            candidates.append((objective, c2, e2, e3))
    if not candidates:
        raise ContractError("no disjoint C2/E3 assignment exists")
    _, c2, e2, e3 = min(candidates, key=lambda item: item[0])
    contraction = [c1, c2]
    expansion = [e1, e2, e3]
    if len(set(contraction + expansion)) != 5:
        raise ContractError("maximal assignment is not disjoint")
    return contraction, expansion


def _ticket_units(issue: str, cell: str, codes: list[str]) -> dict[str, int]:
    count = len(codes)
    base_units, residual = divmod(FUNDED_UNITS, count)
    if base_units < 1:
        raise ContractError("complete ticket space exceeds funded units")
    ranked = sorted(
        codes,
        key=lambda code: (
            hashlib.sha256(f"{CONTRACT_ID}|{issue}|{cell}|{code}".encode()).hexdigest(),
            code,
        ),
    )
    extra = set(ranked[:residual])
    result = {code: base_units + int(code in extra) for code in codes}
    if sum(result.values()) != FUNDED_UNITS:
        raise ContractError("integer allocation does not sum to 512 units")
    return result


def construct_grid(upstream: dict[str, Any]) -> dict[str, pd.DataFrame]:
    diagnostics = upstream["dev_summary"].copy()
    validate_development_diagnostics(diagnostics)
    pairs = upstream["pair_receipts"]
    base_attr = upstream["attribution"]
    base_attr = base_attr[
        base_attr["base"].eq("R3_CORRECTED") & base_attr["shape"].eq("CONTROL")
    ].copy()
    base_decisions = upstream["decisions"]
    base_decisions = base_decisions[
        base_decisions["base"].eq("R3_CORRECTED") & base_decisions["shape"].eq("CONTROL")
    ].copy()
    pair_index = pairs[pairs["base"].eq("R3_CORRECTED")].set_index(["issue", "match_idx"])
    attr_index = base_attr.set_index(["issue", "match_idx"])
    if not pair_index.index.is_unique or not attr_index.index.is_unique:
        raise ContractError("upstream selected fixture keys are not unique")
    assignment_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []

    for decision in base_decisions.sort_values(["issue_anchor_ts", "issue"], kind="stable").itertuples():
        issue = str(decision.issue)
        fixture_order = [int(value) for value in str(decision.selected_match_ids).split("|")]
        issue_pairs = pair_index.loc[issue].reset_index()
        contraction_order, expansion_order = _maximal_assignment(issue_pairs)
        for match_idx in fixture_order:
            row = issue_pairs[issue_pairs["match_idx"].eq(match_idx)].iloc[0]
            assignment_rows.append(
                {
                    "issue": issue, "issue_year": int(decision.issue_year),
                    "match_idx": match_idx,
                    "contraction_rank": int(row["contraction_rank"]),
                    "expansion_rank": int(row["expansion_rank"]),
                    "contraction_order": contraction_order.index(match_idx) + 1 if match_idx in contraction_order else 0,
                    "expansion_order": expansion_order.index(match_idx) + 1 if match_idx in expansion_order else 0,
                    "retained_outcome": str(row["retained_outcome"]),
                    "omitted_outcome": str(row["omitted_outcome"]),
                    "contraction_score": float(row["contraction_score"]),
                    "expansion_score": float(row["expansion_score"]),
                    "anchor_c1": bool(match_idx == contraction_order[0]),
                    "anchor_e1": bool(match_idx == expansion_order[0]),
                }
            )
        source_rows = attr_index.loc[[(issue, fixture) for fixture in fixture_order]].reset_index()
        base_support = {
            int(row.match_idx): tuple(str(row.base_support)) for row in source_rows.itertuples()
        }
        score_rows = issue_pairs.set_index("match_idx")
        for contraction in CONTRACTION_COUNTS:
            for expansion in EXPANSION_COUNTS:
                cell = f"C{contraction}E{expansion}"
                support = dict(base_support)
                for match_idx in contraction_order[:contraction]:
                    support[match_idx] = (str(score_rows.loc[match_idx, "retained_outcome"]),)
                for match_idx in expansion_order[:expansion]:
                    support[match_idx] = OUTCOMES
                support_order = [support[fixture] for fixture in fixture_order]
                combinations = list(itertools.product(*support_order))
                codes = ["|".join(outcomes) for outcomes in combinations]
                expected_count = _ticket_count(contraction, expansion)
                if len(codes) != expected_count or expected_count > FUNDED_UNITS:
                    raise ContractError("cell ticket count violates frozen grid")
                units = _ticket_units(issue, cell, codes)
                support_json = json.dumps(
                    {str(key): "".join(value) for key, value in support.items()},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                decision_rows.append(
                    {
                        "issue": issue, "issue_year": int(decision.issue_year),
                        "issue_anchor_ts": decision.issue_anchor_ts, "base": "R3_CORRECTED",
                        "cell": cell, "contraction_count": contraction,
                        "expansion_count": expansion, "selected_match_ids": decision.selected_match_ids,
                        "support_json": support_json, "contraction_match_ids": "|".join(map(str, contraction_order[:contraction])),
                        "expansion_match_ids": "|".join(map(str, expansion_order[:expansion])),
                        "ticket_count": len(codes), "funded_units": FUNDED_UNITS,
                        "planned_stake_cny": ISSUE_STAKE_CNY,
                        "settlement_status": decision.settlement_status,
                    }
                )
                for ordinal, code in enumerate(codes):
                    funded = units[code]
                    ticket_rows.append(
                        {
                            "issue": issue, "issue_year": int(decision.issue_year), "cell": cell,
                            "ticket_ordinal": ordinal, "ticket_code": code, "units": funded,
                            "stake_cny": funded * STAKE_PER_UNIT_CNY,
                        }
                    )
                realized = source_rows["result_code"].fillna("").astype(str).tolist()
                included = [value in choices for value, choices in zip(realized, support_order, strict=True)]
                trusted = bool(source_rows["settlement_available"].astype(bool).all())
                winning_code = "|".join(realized)
                winning_units = units.get(winning_code, 0)
                hit = bool(all(included))
                product_sp = float(source_rows["winning_sp"].prod()) if trusted else math.nan
                gross = winning_units * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR * product_sp if trusted and hit else 0.0
                ideal_units = FUNDED_UNITS / len(codes)
                ideal_gross = ideal_units * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR * product_sp if trusted and hit else 0.0
                if trusted:
                    bundle_rows.append(
                        {
                            "issue": issue, "issue_year": int(decision.issue_year),
                            "issue_anchor_ts": decision.issue_anchor_ts, "base": "R3_CORRECTED",
                            "cell": cell, "contraction_count": contraction,
                            "expansion_count": expansion, "ticket_count": len(codes),
                            "funded_units": FUNDED_UNITS, "stake_cny": ISSUE_STAKE_CNY,
                            "gross_cny": gross, "pnl_cny": gross - ISSUE_STAKE_CNY,
                            "ideal_fractional_gross_cny": ideal_gross,
                            "ideal_fractional_pnl_cny": ideal_gross - ISSUE_STAKE_CNY,
                            "integer_allocation_delta_cny": gross - ideal_gross,
                            "ticket_hit": hit, "issue_gross_positive": bool(gross > 0),
                            "issue_profitable": bool(gross > ISSUE_STAKE_CNY),
                            "miss_count": int(sum(not value for value in included)),
                            "winning_ticket_units": int(winning_units),
                        }
                    )
                for row, choices, realized_ok in zip(source_rows.itertuples(), support_order, included, strict=True):
                    attribution_rows.append(
                        {
                            "issue": issue, "issue_year": int(decision.issue_year), "cell": cell,
                            "match_idx": int(row.match_idx), "base_support": str(row.base_support),
                            "active_support": "".join(choices),
                            "contraction_order": contraction_order.index(int(row.match_idx)) + 1 if int(row.match_idx) in contraction_order else 0,
                            "expansion_order": expansion_order.index(int(row.match_idx)) + 1 if int(row.match_idx) in expansion_order else 0,
                            "result_code": str(row.result_code), "winning_sp": float(row.winning_sp),
                            "settlement_available": bool(row.settlement_available),
                            "realized_in_support": bool(realized_ok),
                        }
                    )
    bundles = pd.DataFrame(bundle_rows)
    upstream_control = upstream["bundles"][upstream["bundles"]["shape"].eq("CONTROL")].copy()
    grid_control = bundles[bundles["cell"].eq(CONTROL_CELL)].copy()
    validate_control_keysets(grid_control, upstream_control)
    return {
        "development_gate": diagnostics,
        "assignments": pd.DataFrame(assignment_rows),
        "decisions": pd.DataFrame(decision_rows),
        "tickets": pd.DataFrame(ticket_rows),
        "bundles": bundles,
        "attribution": pd.DataFrame(attribution_rows),
        "coverage": upstream["coverage"].copy(),
        "upstream_control": upstream_control,
    }


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


def _bootstrap_path_rows(
    scope: str, cell: str, pnl: np.ndarray, rng: np.random.Generator
) -> dict[str, Any]:
    indices = _circular_block_indices(len(pnl), BOOTSTRAP_DRAWS, rng)
    longest = np.empty(BOOTSTRAP_DRAWS, dtype=float)
    drawdown = np.empty(BOOTSTRAP_DRAWS, dtype=float)
    underwater = np.empty(BOOTSTRAP_DRAWS, dtype=float)
    for draw, sample_indices in enumerate(indices):
        metrics = _path_metrics(pnl[sample_indices])
        longest[draw] = metrics["longest_profitable_issue_losing_run"]
        drawdown[draw] = metrics["max_drawdown_fraction"]
        underwater[draw] = metrics["open_underwater_issues"]
    row: dict[str, Any] = {
        "scope": scope, "cell": cell, "issues": len(pnl),
        "block_length": min(MOVING_BLOCK_LENGTH, len(pnl)), "draws": BOOTSTRAP_DRAWS,
    }
    for name, values in [
        ("longest_run", longest), ("max_drawdown_fraction", drawdown),
        ("open_underwater_issues", underwater),
    ]:
        row[f"{name}_p05"] = float(np.quantile(values, 0.05))
        row[f"{name}_median"] = float(np.quantile(values, 0.5))
        row[f"{name}_p95"] = float(np.quantile(values, 0.95))
    return row


def evaluate_grid(bundles: pd.DataFrame) -> dict[str, pd.DataFrame]:
    performance_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    rolling_rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    scopes = [(str(year), bundles[bundles["issue_year"].eq(year)]) for year in YEARS]
    scopes.append(("ALL", bundles))
    for scope, scoped in scopes:
        for cell, group in scoped.groupby("cell", sort=True):
            group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            pnl = group["pnl_cny"].to_numpy(float)
            ideal_pnl = group["ideal_fractional_pnl_cny"].to_numpy(float)
            largest = int(np.argmax(pnl))
            payouts = group.loc[group["gross_cny"].gt(0), "gross_cny"].to_numpy(float)
            weights = payouts / payouts.sum() if payouts.sum() > 0 else np.array([])
            performance_rows.append(
                {
                    "scope": scope, "cell": cell, "contraction_count": int(group["contraction_count"].iloc[0]),
                    "expansion_count": int(group["expansion_count"].iloc[0]),
                    "issues": int(len(group)), "ticket_count_per_issue": int(group["ticket_count"].iloc[0]),
                    "average_ticket_stake_cny": float(
                        ISSUE_STAKE_CNY / group["ticket_count"].iloc[0]
                    ),
                    "total_tickets": int(group["ticket_count"].sum()),
                    "ticket_hit_rate": float(group["ticket_hit"].sum() / group["ticket_count"].sum()),
                    "issue_gross_positive_rate": float(group["issue_gross_positive"].mean()),
                    "issue_profitable_rate": float(group["issue_profitable"].mean()),
                    "stake_cny": float(group["stake_cny"].sum()), "gross_cny": float(group["gross_cny"].sum()),
                    "pnl_cny": float(pnl.sum()), "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                    "conditional_gross_on_hit_cny": float(group.loc[group["ticket_hit"], "gross_cny"].mean()) if group["ticket_hit"].any() else 0.0,
                    "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest]),
                    "ideal_fractional_pnl_cny": float(ideal_pnl.sum()),
                    "integer_minus_ideal_cny": float((pnl - ideal_pnl).sum()),
                }
            )
            path_metric = _path_metrics(pnl)
            risk_rows.append(
                {
                    "scope": scope, "cell": cell, **path_metric,
                    "largest_payout_share": float(weights.max()) if len(weights) else 0.0,
                    "payout_hhi": float(np.square(weights).sum()) if len(weights) else 0.0,
                }
            )
            run_rows.append({"scope": scope, "cell": cell, **_run_summary(pnl)})
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL_CNY, capital])[1:]
            for order, (row, value, peak) in enumerate(
                zip(group.itertuples(), capital, peaks, strict=True), start=1
            ):
                path_rows.append(
                    {
                        "scope": scope, "cell": cell, "issue_order": order,
                        "issue": row.issue, "issue_year": int(row.issue_year),
                        "issue_anchor_ts": row.issue_anchor_ts, "pnl_cny": float(row.pnl_cny),
                        "capital_cny": float(value), "drawdown_fraction": float((peak - value) / max(peak, 1e-12)),
                    }
                )
            bootstrap_rows.append(_bootstrap_path_rows(scope, cell, pnl, rng))
            if scope == "ALL":
                for window in ROLLING_WINDOWS:
                    rolling = pd.Series(pnl).rolling(window).sum().dropna().to_numpy(float)
                    rolling_rows.append(
                        {
                            "cell": cell, "window_issues": window, "windows": int(len(rolling)),
                            "worst_window_pnl_cny": float(rolling.min()),
                            "p10_window_pnl_cny": float(np.quantile(rolling, 0.1)),
                            "median_window_pnl_cny": float(np.quantile(rolling, 0.5)),
                            "positive_window_rate": float((rolling > 0).mean()),
                        }
                    )
    return {
        "performance": pd.DataFrame(performance_rows), "risk": pd.DataFrame(risk_rows),
        "runs": pd.DataFrame(run_rows), "paths": pd.DataFrame(path_rows),
        "path_bootstrap": pd.DataFrame(bootstrap_rows), "rolling": pd.DataFrame(rolling_rows),
    }


def matched_contrasts(bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    contrast_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED + 1)
    scopes = [(str(year), bundles[bundles["issue_year"].eq(year)]) for year in YEARS]
    scopes.append(("ALL", bundles))
    for scope, scoped in scopes:
        wide = scoped.pivot(
            index=["issue_anchor_ts", "issue"], columns="cell", values="pnl_cny"
        ).sort_index(kind="stable")
        ideal = scoped.pivot(
            index=["issue_anchor_ts", "issue"], columns="cell", values="ideal_fractional_pnl_cny"
        ).sort_index(kind="stable")
        if set(wide.columns) != set(CELLS) or wide.isna().any().any():
            raise ContractError("contrast denominator is not exact common across all cells")
        for cell in CELLS:
            if cell == CONTROL_CELL:
                continue
            delta = (wide[cell] - wide[CONTROL_CELL]).to_numpy(float)
            ideal_delta = (ideal[cell] - ideal[CONTROL_CELL]).to_numpy(float)
            largest = int(np.argmax(np.abs(delta)))
            row = {
                "scope": scope, "cell": cell, "issues": int(len(delta)),
                "matched_lift_cny": float(delta.sum()),
                "ideal_fractional_matched_lift_cny": float(ideal_delta.sum()),
                "integer_contribution_to_lift_cny": float((delta - ideal_delta).sum()),
                "largest_abs_delta_issue": str(wide.index[largest][1]),
                "largest_abs_delta_cny": float(delta[largest]),
                "ex_largest_lift_cny": float(delta.sum() - delta[largest]),
            }
            contrast_rows.append(row)
            indices = _circular_block_indices(len(delta), BOOTSTRAP_DRAWS, rng)
            draws = delta[indices].sum(axis=1)
            ideal_draws = ideal_delta[indices].sum(axis=1)
            bootstrap_rows.append(
                {
                    **row, "block_length": min(MOVING_BLOCK_LENGTH, len(delta)),
                    "draws": BOOTSTRAP_DRAWS,
                    "lift_p05_cny": float(np.quantile(draws, 0.05)),
                    "lift_median_cny": float(np.quantile(draws, 0.5)),
                    "lift_p95_cny": float(np.quantile(draws, 0.95)),
                    "ideal_lift_p05_cny": float(np.quantile(ideal_draws, 0.05)),
                    "ideal_lift_median_cny": float(np.quantile(ideal_draws, 0.5)),
                    "ideal_lift_p95_cny": float(np.quantile(ideal_draws, 0.95)),
                }
            )
    return pd.DataFrame(contrast_rows), pd.DataFrame(bootstrap_rows)


def pareto_frontier(performance: pd.DataFrame, risk: pd.DataFrame) -> pd.DataFrame:
    frame = performance[performance["scope"].eq("ALL")].merge(
        risk[risk["scope"].eq("ALL")], on=["scope", "cell"], validate="one_to_one"
    )
    maximize = ["pnl_cny", "ex_largest_pnl_cny"]
    minimize = ["max_drawdown_fraction", "longest_profitable_issue_losing_run", "open_underwater_issues"]
    pareto: list[bool] = []
    for _, row in frame.iterrows():
        dominated = False
        for _, other in frame.iterrows():
            weak = all(other[name] >= row[name] for name in maximize) and all(
                other[name] <= row[name] for name in minimize
            )
            strict = any(other[name] > row[name] for name in maximize) or any(
                other[name] < row[name] for name in minimize
            )
            if weak and strict:
                dominated = True
                break
        pareto.append(not dominated)
    frame["pareto"] = pareto
    frame["priority_hypothesis"] = frame["cell"].isin(PRIORITY_CELLS)
    return frame


def historical_gate(
    performance: pd.DataFrame,
    risk: pd.DataFrame,
    contrasts: pd.DataFrame,
    lift_bootstrap: pd.DataFrame,
    diagnostics_valid: bool,
    control_keys_valid: bool,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    all_perf = performance[performance["scope"].eq("ALL")].set_index("cell")
    all_risk = risk[risk["scope"].eq("ALL")].set_index("cell")
    all_contrast = contrasts[contrasts["scope"].eq("ALL")].set_index("cell")
    all_boot = lift_bootstrap[lift_bootstrap["scope"].eq("ALL")].set_index("cell")
    control_drawdown = float(all_risk.loc[CONTROL_CELL, "max_drawdown_fraction"])
    for cell in CELLS:
        if cell == CONTROL_CELL:
            continue
        annual_perf = performance[(performance["scope"].isin(map(str, YEARS))) & performance["cell"].eq(cell)]
        annual_lift = contrasts[(contrasts["scope"].isin(map(str, YEARS))) & contrasts["cell"].eq(cell)]
        conditions = {
            "standalone_positive": bool(all_perf.loc[cell, "pnl_cny"] > 0),
            "standalone_ex_largest_positive": bool(all_perf.loc[cell, "ex_largest_pnl_cny"] > 0),
            "matched_lift_positive": bool(all_contrast.loc[cell, "matched_lift_cny"] > 0),
            "matched_ex_largest_positive": bool(all_contrast.loc[cell, "ex_largest_lift_cny"] > 0),
            "moving_block_lift_p05_nonnegative": bool(all_boot.loc[cell, "lift_p05_cny"] >= 0),
            "drawdown_no_worse_than_control": bool(
                all_risk.loc[cell, "max_drawdown_fraction"]
                <= control_drawdown + MAX_ACCEPTABLE_DRAWDOWN_DELTA
            ),
            "losing_run_no_worse_than_19": bool(
                all_risk.loc[cell, "longest_profitable_issue_losing_run"]
                <= MAX_ACCEPTABLE_LOSING_RUN
            ),
            "two_positive_annual_pnl": bool((annual_perf["pnl_cny"] > 0).sum() >= 2),
            "two_positive_annual_lifts": bool((annual_lift["matched_lift_cny"] > 0).sum() >= 2),
            "development_diagnostics_valid": bool(diagnostics_valid),
            "control_keysets_valid": bool(control_keys_valid),
        }
        historical_pass = bool(all(conditions.values()))
        rows.append(
            {
                "cell": cell, **conditions, "historical_gate_pass": historical_pass,
                "expert_admitted": False,
                "future_frozen_candidate_required": historical_pass,
            }
        )
    return pd.DataFrame(rows)


def scientific_frames(repo_root: Path, data_root: Path) -> dict[str, Any]:
    upstream_package = repo_root / UPSTREAM_PACKAGE
    upstream_checks = verify_support_shape(repo_root, upstream_package, data_root)
    if not all(upstream_checks.values()):
        raise ContractError("#369 source-bound verifier did not pass")
    upstream = support_shape_frames(repo_root, data_root)
    grid = construct_grid(upstream)
    evaluated = evaluate_grid(grid["bundles"])
    contrasts, lift_bootstrap = matched_contrasts(grid["bundles"])
    pareto = pareto_frontier(evaluated["performance"], evaluated["risk"])
    diagnostics_valid = bool(grid["development_gate"]["nonnegative_monotonicity"].eq(True).all())  # noqa: E712
    control_keys_valid = True
    gate = historical_gate(
        evaluated["performance"], evaluated["risk"], contrasts, lift_bootstrap,
        diagnostics_valid, control_keys_valid,
    )
    assignments = grid["assignments"]
    anchor = assignments[
        assignments["anchor_c1"] | assignments["anchor_e1"]
    ][["issue", "match_idx", "anchor_c1", "anchor_e1"]]
    upstream_anchor = upstream["pair_receipts"]
    upstream_anchor = upstream_anchor[
        upstream_anchor["base"].eq("R3_CORRECTED")
        & (upstream_anchor["chosen_contraction"] | upstream_anchor["chosen_expansion"])
    ][["issue", "match_idx", "chosen_contraction", "chosen_expansion"]]
    anchor_parity = anchor.merge(
        upstream_anchor,
        on=["issue", "match_idx"],
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    anchor_parity["exact_anchor"] = (
        anchor_parity["_merge"].eq("both")
        & anchor_parity["anchor_c1"].eq(anchor_parity["chosen_contraction"])
        & anchor_parity["anchor_e1"].eq(anchor_parity["chosen_expansion"])
    )
    c1e1_decisions = grid["decisions"][grid["decisions"]["cell"].eq("C1E1")]
    upstream_both = upstream["decisions"][
        upstream["decisions"]["base"].eq("R3_CORRECTED")
        & upstream["decisions"]["shape"].eq("BOTH")
    ]
    support_parity = c1e1_decisions.merge(
        upstream_both[["issue", "support_json"]], on="issue", how="outer",
        suffixes=("_grid", "_369"), validate="one_to_one", indicator=True,
    )
    support_parity["exact_support"] = (
        support_parity["_merge"].eq("both")
        & support_parity["support_json_grid"].eq(support_parity["support_json_369"])
    )
    pipeline_369 = repo_root / "src/n7_support_shape/pipeline.py"
    contract_369 = repo_root / "src/n7_support_shape/contract.py"
    source = {
        "contract": CONTRACT_ID,
        "upstream_contract": _read_json(upstream_package / "MANIFEST.json").get("contract"),
        "upstream_manifest_sha256": sha256_file(upstream_package / "MANIFEST.json"),
        "decision_facing_imports": {
            "src/n7_support_shape/pipeline.py": sha256_file(pipeline_369),
            "src/n7_support_shape/contract.py": sha256_file(contract_369),
        },
        "evaluation_years": list(YEARS),
        "evaluation_role": "EXPOSED_RETROSPECTIVE_MECHANISM_MAP",
        "development_diagnostic_gate": diagnostics_valid,
        "control_keyset_gate": control_keys_valid,
        "issue_budget_cny": ISSUE_STAKE_CNY,
        "payout_factor_application": "ONCE_PER_COMPLETE_WINNING_TICKET",
        "moving_block_length": MOVING_BLOCK_LENGTH,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }
    historical_passes = gate.loc[gate["historical_gate_pass"], "cell"].tolist()
    retained_hypotheses = pareto.loc[
        pareto["cell"].isin(["C1E2", "C1E3"])
        & pareto["pareto"]
        & pareto["pnl_cny"].gt(0),
        "cell",
    ].tolist()
    decision = {
        "contract": CONTRACT_ID,
        "verdict": (
            "HISTORICAL_GATE_PASS_REQUIRES_FUTURE_FREEZE"
            if historical_passes
            else "HISTORICAL_MECHANISM_FRONTIER_NO_GATE_PASS"
        ),
        "historical_gate_pass_cells": historical_passes,
        "retained_mechanism_hypotheses": retained_hypotheses,
        "expert_admitted_cells": [],
        "requires_future_frozen_evidence": bool(retained_hypotheses),
        "promotable_to_210": False,
        "development_diagnostic_gate": diagnostics_valid,
        "control_keyset_gate": control_keys_valid,
        "notes": "No exposed grid cell enters the expert pool; #210/#218 unchanged.",
    }
    return {
        "source": source, **grid, **evaluated, "contrasts": contrasts,
        "lift_bootstrap": lift_bootstrap, "pareto": pareto, "gate": gate,
        "anchor_parity": anchor_parity, "support_parity": support_parity,
        "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "development_diagnostic_gate.csv": "development_gate",
    "assignment_receipts.parquet": "assignments",
    "decisions.parquet": "decisions",
    "tickets.parquet": "tickets",
    "issue_bundles.parquet": "bundles",
    "support_attribution.parquet": "attribution",
    "coverage_ledger.csv": "coverage",
    "performance.csv": "performance",
    "risk_diagnostics.csv": "risk",
    "losing_run_diagnostics.csv": "runs",
    "capital_paths.csv": "paths",
    "moving_block_path_bootstrap.csv": "path_bootstrap",
    "rolling_windows.csv": "rolling",
    "matched_contrasts.csv": "contrasts",
    "moving_block_lift_bootstrap.csv": "lift_bootstrap",
    "pareto_frontier.csv": "pareto",
    "historical_gate.csv": "gate",
    "anchor_parity.parquet": "anchor_parity",
    "c1e1_support_parity.parquet": "support_parity",
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


def _implementation_hashes() -> dict[str, str]:
    return {
        "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
        "pipeline.py": sha256_file(Path(__file__)),
        "src/n7_support_shape/contract.py": sha256_file(
            Path(__file__).resolve().parents[1] / "n7_support_shape/contract.py"
        ),
        "src/n7_support_shape/pipeline.py": sha256_file(
            Path(__file__).resolve().parents[1] / "n7_support_shape/pipeline.py"
        ),
    }


def build_package(
    repo_root: Path, target: Path, explicit_data_root: Path | None = None, *, force: bool = False
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
            "implementation": _implementation_hashes(),
        }
        (staging / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    atomic_publish_directory(target.resolve(), populate, force=force)
    return frames["decision"]


def verify_package(
    repo_root: Path, target: Path, explicit_data_root: Path | None = None
) -> dict[str, bool]:
    repo_root, target = repo_root.resolve(), target.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    manifest = _read_json(target / "MANIFEST.json")
    if manifest.get("contract") != CONTRACT_ID or set(manifest.get("files", {})) != set(PACKAGE_FILES):
        raise ContractError("manifest contract or exact file set mismatch")
    for relative, receipt in manifest["files"].items():
        path = target / relative
        if not path.is_file() or sha256_file(path) != receipt["sha256"]:
            raise ContractError(f"manifest file mismatch: {relative}")
    if manifest.get("implementation") != _implementation_hashes():
        raise ContractError("implementation/import hashes do not match current code")
    expected = scientific_frames(repo_root, data_root)
    for relative, key in PACKAGE_FILES.items():
        path = target / relative
        value = expected[key]
        if isinstance(value, pd.DataFrame):
            if path.suffix == ".parquet":
                actual = pd.read_parquet(path)
                matches = actual.equals(value)
            else:
                matches = hashlib.sha256(value.to_csv(index=False).encode()).hexdigest() == sha256_file(path)
            if not matches:
                raise ContractError(f"scientific frame mismatch: {relative}")
        elif _read_json(path) != value:
            raise ContractError(f"receipt mismatch: {relative}")
    validate_development_diagnostics(expected["development_gate"])
    validate_control_keysets(
        expected["bundles"][expected["bundles"]["cell"].eq(CONTROL_CELL)],
        expected["upstream_control"],
    )
    decisions = expected["decisions"]
    if set(decisions["cell"].unique()) != set(CELLS):
        raise ContractError("decision grid is incomplete")
    decision_groups = decisions.groupby("issue", observed=True)
    if not decision_groups.size().eq(len(CELLS)).all():
        raise ContractError("each issue does not contain all 12 cells")
    tickets = expected["tickets"]
    ticket_groups = tickets.groupby(["issue", "cell"], observed=True)
    if not ticket_groups["units"].sum().eq(FUNDED_UNITS).all():
        raise ContractError("ticket groups do not fund 512 units")
    if not np.isclose(ticket_groups["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-12).all():
        raise ContractError("ticket groups do not stake CNY1,024")
    for (_, cell), count in ticket_groups.size().items():
        contraction, expansion = _parse_cell(cell)
        if count != _ticket_count(contraction, expansion):
            raise ContractError("ticket group is not complete Cartesian K(C,E)")
    if not ticket_groups["ticket_code"].nunique().eq(ticket_groups.size()).all():
        raise ContractError("ticket codes are not unique within group")
    bundles = expected["bundles"]
    if not np.allclose(bundles["pnl_cny"], bundles["gross_cny"] - ISSUE_STAKE_CNY, rtol=0, atol=1e-9):
        raise ContractError("bundle PnL identity failed")
    if not expected["anchor_parity"]["exact_anchor"].all():
        raise ContractError("c1/e1 differs from #369")
    if not expected["support_parity"]["exact_support"].all():
        raise ContractError("C1E1 support differs from #369 BOTH")
    assignments = expected["assignments"]
    for _, group in assignments.groupby("issue", observed=True):
        c = group.loc[group["contraction_order"].gt(0), "match_idx"].tolist()
        e = group.loc[group["expansion_order"].gt(0), "match_idx"].tolist()
        if len(c) != 2 or len(e) != 3 or len(set(c + e)) != 5:
            raise ContractError("nested maximal assignment is not C2/E3 disjoint")
    expected_delivery = {
        "docs/research/Issue-373-N7-Support-Transfer-Grid.md",
        "docs/research/figures/issue_373_support_transfer_frontier.png",
        "notebooks/research/n7-support-transfer-grid/n7_support_transfer_grid.ipynb",
    }
    if set(manifest.get("delivery", {})) != expected_delivery:
        raise ContractError("delivery receipt file set mismatch")
    for relative, expected_hash in manifest["delivery"].items():
        path = repo_root / relative
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise ContractError(f"delivery hash mismatch: {relative}")
    notebook = nbformat.read(
        repo_root / "notebooks/research/n7-support-transfer-grid/n7_support_transfer_grid.ipynb",
        as_version=4,
    )
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if not code_cells or any(cell.get("execution_count") is None for cell in code_cells):
        raise ContractError("notebook is not fully executed")
    return {
        "manifest": True, "source_bound_replay": True, "development_gate": True,
        "control_keyset_gate": True, "nested_disjoint_assignment": True,
        "complete_count_grid": True, "fixed_budget": True, "ticket_level_once_payout": True,
        "path_risk": True, "moving_block_bootstrap": True, "pareto_and_admission": True,
        "delivery": True,
    }


def _markdown_table(frame: pd.DataFrame) -> str:
    rendered = frame.copy()
    for column in rendered.select_dtypes(include=["float"]).columns:
        rendered[column] = rendered[column].map(lambda value: f"{value:.4f}")
    header = "| " + " | ".join(rendered.columns) + " |"
    separator = "|" + "|".join("---" for _ in rendered.columns) + "|"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in rendered.itertuples(index=False, name=None)]
    return "\n".join([header, separator, *rows])


def build_notebook_and_report(repo_root: Path, package: Path) -> None:
    notebook_path = repo_root / "notebooks/research/n7-support-transfer-grid/n7_support_transfer_grid.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell("# Issue #373 — corrected N7 R3 support-transfer count grid"),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\n"
            "ROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/n7_support_transfer_grid'"
        ),
        nbformat.v4.new_code_cell(
            "dev=pd.read_csv(OUT/'development_diagnostic_gate.csv')\ndev"
        ),
        nbformat.v4.new_code_cell(
            "perf=pd.read_csv(OUT/'performance.csv')\nperf[perf.scope.eq('ALL')]"
        ),
        nbformat.v4.new_code_cell(
            "annual=perf[perf.scope.ne('ALL')].pivot(index='cell',columns='scope',values='pnl_cny')\nannual"
        ),
        nbformat.v4.new_code_cell(
            "risk=pd.read_csv(OUT/'risk_diagnostics.csv')\nruns=pd.read_csv(OUT/'losing_run_diagnostics.csv')\n"
            "risk[risk.scope.eq('ALL')].merge(runs[runs.scope.eq('ALL')],on=['scope','cell'])"
        ),
        nbformat.v4.new_code_cell(
            "annual_path=risk[risk.scope.ne('ALL')].merge("
            "runs[runs.scope.ne('ALL')],on=['scope','cell'])\nannual_path"
        ),
        nbformat.v4.new_code_cell(
            "lift=pd.read_csv(OUT/'moving_block_lift_bootstrap.csv')\nlift[lift.scope.eq('ALL')]"
        ),
        nbformat.v4.new_code_cell(
            "path_boot=pd.read_csv(OUT/'moving_block_path_bootstrap.csv')\npath_boot[path_boot.scope.eq('ALL')]"
        ),
        nbformat.v4.new_code_cell(
            "rolling=pd.read_csv(OUT/'rolling_windows.csv')\nrolling"
        ),
        nbformat.v4.new_code_cell(
            "pareto=pd.read_csv(OUT/'pareto_frontier.csv')\ngate=pd.read_csv(OUT/'historical_gate.csv')\npareto[['cell','pnl_cny','max_drawdown_fraction','longest_profitable_issue_losing_run','pareto']]"
        ),
        nbformat.v4.new_code_cell("gate"),
        nbformat.v4.new_code_cell(
            "paths=pd.read_csv(OUT/'capital_paths.csv')\nfig,axes=plt.subplots(1,2,figsize=(14,4))\n"
            "keep=['C0E0','C1E1','C1E2','C1E3','C0E3']\n"
            "for cell,g in paths[(paths.scope=='ALL') & paths.cell.isin(keep)].groupby('cell'):\n"
            "    axes[0].plot(g.issue_order,g.capital_cny,label=cell)\n"
            "axes[0].axhline(100000,color='black',lw=.8); axes[0].legend(); axes[0].set_title('Priority capital paths')\n"
            "for _,r in pareto.iterrows():\n"
            "    axes[1].scatter(r.max_drawdown_fraction,r.pnl_cny,color=('tab:red' if r.pareto else 'tab:blue'))\n"
            "    axes[1].annotate(r.cell,(r.max_drawdown_fraction,r.pnl_cny),fontsize=7)\n"
            "axes[1].set_xlabel('Max drawdown'); axes[1].set_ylabel('PnL CNY'); axes[1].set_title('No-weight Pareto view'); plt.show()"
        ),
    ]
    NotebookClient(nb, timeout=300, kernel_name="python3").execute(cwd=str(notebook_path.parent))
    nbformat.write(nb, notebook_path)

    perf = pd.read_csv(package / "performance.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    runs = pd.read_csv(package / "losing_run_diagnostics.csv")
    lift = pd.read_csv(package / "moving_block_lift_bootstrap.csv")
    path_boot = pd.read_csv(package / "moving_block_path_bootstrap.csv")
    rolling = pd.read_csv(package / "rolling_windows.csv")
    pareto = pd.read_csv(package / "pareto_frontier.csv")
    gate = pd.read_csv(package / "historical_gate.csv")
    decision = _read_json(package / "decision.json")
    all_perf = perf[perf["scope"].eq("ALL")]
    all_risk = risk[risk["scope"].eq("ALL")]
    all_runs = runs[runs["scope"].eq("ALL")]
    all_lift = lift[lift["scope"].eq("ALL")]
    summary = all_perf.merge(all_risk, on=["scope", "cell"]).merge(
        all_runs, on=["scope", "cell"]
    )
    annual = perf[perf["scope"].ne("ALL")].pivot(index="cell", columns="scope", values="pnl_cny").reset_index()
    annual_path = risk[risk["scope"].ne("ALL")].merge(
        runs[runs["scope"].ne("ALL")], on=["scope", "cell"], validate="one_to_one"
    )

    figure = repo_root / "docs/research/figures/issue_373_support_transfer_frontier.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    paths = pd.read_csv(package / "capital_paths.csv")
    fig, axes = plt.subplots(1, 2, figsize=(14, 4))
    keep = [CONTROL_CELL, "C1E1", "C1E2", "C1E3", "C0E3"]
    for cell, group in paths[(paths["scope"].eq("ALL")) & paths["cell"].isin(keep)].groupby("cell"):
        axes[0].plot(group["issue_order"], group["capital_cny"], label=cell)
    axes[0].axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8)
    axes[0].legend(fontsize=8)
    axes[0].set_title("Priority support-transfer capital paths")
    for row in pareto.itertuples():
        axes[1].scatter(row.max_drawdown_fraction, row.pnl_cny, color="tab:red" if row.pareto else "tab:blue")
        axes[1].annotate(row.cell, (row.max_drawdown_fraction, row.pnl_cny), fontsize=7)
    axes[1].set_xlabel("Max drawdown")
    axes[1].set_ylabel("PnL CNY")
    axes[1].set_title("No-weight Pareto view")
    fig.tight_layout()
    fig.savefig(figure, dpi=160)
    plt.close(fig)

    priority = summary[summary["cell"].isin([CONTROL_CELL, "C1E1", *PRIORITY_CELLS])]
    priority_lift = all_lift[all_lift["cell"].isin(PRIORITY_CELLS)]
    report = f"""# Issue #373 — corrected N7 R3 support-transfer count grid

Contract: `{CONTRACT_ID}`

## Decision

`{decision['verdict']}`. Historical gate-pass cells: `{decision['historical_gate_pass_cells']}`. Retained mechanism hypotheses: `{decision['retained_mechanism_hypotheses']}`. No exposed cell is admitted to the expert pool, and #210/#218 remain unchanged.

## Five-minute interpretation

- **C1E3 is the clearest path-risk compromise.** It ends at CNY132,797 versus CNY132,689 for corrected-R3 CONTROL: actual matched lift CNY108 and ideal-fractional lift CNY1,052. It therefore preserves, rather than materially raises, historical economics.
- Its path is materially smoother: maximum drawdown is 21.90% versus 33.17%; the observed longest profitable-issue losing run is 7 versus 19; issue-profitable rate is 28.48% versus 15.89%. Rolling 20/30/50-issue positive-window rates rise to 68.94%/73.77%/79.41% from 33.33%/44.26%/62.75%.
- This is not a robust Edge claim. C1E3 moving-block matched-lift p05 is CNY-135,691, and its observed open-underwater tail is 8 issues versus CONTROL's 1. The bootstrap median open-underwater duration improves to 24 from 52.5 issues, but the p95 remains very long (139 issues).
- **C1E2 has higher realized PnL but is allocation-sensitive.** Actual matched lift is CNY6,570 while the ideal-fractional lift is CNY-1,131. Its 15-issue losing run meets the target, but only 2024 has positive annual standalone PnL.
- Pure expansion C0E2 reduces drawdown and the losing run, but gives up CNY15,666 versus CONTROL. C0E3 turns standalone PnL negative despite a 9-issue losing run. All C2 cells are economically negative, so a second contraction crosses the observed support-transfer boundary.
- C1E1 remains the highest-PnL exposed cell (CNY52,913), but its 37.34% drawdown and 22-issue losing run do not solve the holding problem. The grid therefore exposes a Pareto mechanism, not one scalar winner.

## Design and evidence boundary

- Full `C0–C2 × E0–E3` grid; every K(C,E) Cartesian ticket is funded under CNY1,024.
- The #369 `(c1,e1)` mechanism is preserved, then extended to a causal, disjoint, nested `c1,c2 / e1,e2,e3` assignment.
- 2017–2021 development diagnostics are hard decision/verifier predicates. All four passed.
- 2022–2024 is exposed retrospective evidence. Pareto membership is descriptive and no weighted score is optimized.

## Full-sample economics and path risk

{_markdown_table(summary)}

## Annual PnL

{_markdown_table(annual)}

## Annual path and payout risk

{_markdown_table(annual_path)}

## Priority hypothesis cells

{_markdown_table(priority)}

## Matched moving-block lift versus C0E0

{_markdown_table(priority_lift)}

## Moving-block path distributions

### Full sample

{_markdown_table(path_boot[path_boot['scope'].eq('ALL')])}

### Annual

{_markdown_table(path_boot[path_boot['scope'].ne('ALL')])}

## Rolling 20/30/50-issue behavior

{_markdown_table(rolling)}

## Pareto frontier

{_markdown_table(pareto)}

## Historical qualification gate

{_markdown_table(gate)}

`historical_gate_pass` is only a mechanism-screen result. Even a passing cell requires a new frozen candidate on genuinely new evidence before expert admission.

## Artifacts

- Package: `results/n7_support_transfer_grid/`
- Notebook: `notebooks/research/n7-support-transfer-grid/n7_support_transfer_grid.ipynb`
- Figure: `docs/research/figures/issue_373_support_transfer_frontier.png`
"""
    report_path = repo_root / "docs/research/Issue-373-N7-Support-Transfer-Grid.md"
    report_path.write_text(report, encoding="utf-8")
    manifest_path = package / "MANIFEST.json"
    manifest = _read_json(manifest_path)
    manifest["delivery"] = {
        "docs/research/Issue-373-N7-Support-Transfer-Grid.md": sha256_file(report_path),
        "docs/research/figures/issue_373_support_transfer_frontier.png": sha256_file(figure),
        "notebooks/research/n7-support-transfer-grid/n7_support_transfer_grid.ipynb": sha256_file(notebook_path),
    }
    atomic_write_json(manifest_path, manifest)
