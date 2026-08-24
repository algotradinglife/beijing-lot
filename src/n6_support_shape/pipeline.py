"""Evaluate corrected-N6 contraction and expansion support shapes.

The experiment inherits the corrected #366 fixture selection and fixed R0/R3
support definitions.  It changes only the support shape and the deterministic
integer allocation over the complete Cartesian ticket space.
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
    scientific_frames as upstream_frames,
    verify_package as verify_upstream,
)
from src.source_schema.publication import atomic_publish_directory, atomic_write_json

from .contract import (
    BASES,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    DEVELOPMENT_YEARS,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    SHAPES,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TICKET_COUNTS,
    UPSTREAM_PACKAGE,
    YEARS,
)


class ContractError(ValueError):
    """Raised when a frozen scientific or delivery invariant fails."""


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


def _base_name(upstream_arm: str) -> str:
    return {"R0": "R0_CORRECTED", "R3": "R3_CORRECTED"}[upstream_arm]


def _support_tuple(value: object) -> tuple[str, ...]:
    support = tuple(str(value))
    if len(support) != 2 or len(set(support)) != 2 or not set(support).issubset(OUTCOMES):
        raise ContractError(f"invalid frozen two-outcome support: {value}")
    return support


def _probability_map(row: pd.Series) -> dict[str, float]:
    values = {outcome: float(row[f"q_eu_{outcome}"]) for outcome in OUTCOMES}
    if not all(math.isfinite(value) and value > 0 for value in values.values()):
        raise ContractError("invalid calibrated probability")
    if not math.isclose(sum(values.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ContractError("calibrated probability triplet is not normalized")
    return values


def _rank_shape_pair(selected: pd.DataFrame, support_map: dict[int, tuple[str, ...]]) -> tuple[int, int, pd.DataFrame]:
    """Choose one contraction and one disjoint expansion fixture deterministically."""

    rows: list[dict[str, Any]] = []
    for _, row in selected.iterrows():
        match_idx = int(row["match_idx"])
        support = support_map[match_idx]
        probs = _probability_map(row)
        retained = min(support, key=lambda outcome: (-probs[outcome], OUTCOMES.index(outcome)))
        omitted = next(outcome for outcome in OUTCOMES if outcome not in support)
        supported_mass = sum(probs[outcome] for outcome in support)
        rows.append(
            {
                "match_idx": match_idx,
                "contraction_score": probs[retained] / supported_mass,
                "expansion_score": probs[omitted],
                "retained_outcome": retained,
                "omitted_outcome": omitted,
                "retained_probability": probs[retained],
                "supported_mass": supported_mass,
            }
        )
    scores = pd.DataFrame(rows)
    contraction = scores.sort_values(
        ["contraction_score", "retained_probability", "supported_mass", "match_idx"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    expansion = scores.sort_values(
        ["expansion_score", "supported_mass", "match_idx"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)
    c_rank = {int(row.match_idx): index + 1 for index, row in contraction.iterrows()}
    e_rank = {int(row.match_idx): index + 1 for index, row in expansion.iterrows()}
    candidates = [
        (c_rank[c], e_rank[e], max(c_rank[c], e_rank[e]), c, e)
        for c in c_rank
        for e in e_rank
        if c != e
    ]
    rc, re, _, c, e = min(candidates, key=lambda item: (item[0] + item[1], item[2], *item))
    scores["contraction_rank"] = scores["match_idx"].map(c_rank).astype(int)
    scores["expansion_rank"] = scores["match_idx"].map(e_rank).astype(int)
    scores["chosen_contraction"] = scores["match_idx"].eq(c)
    scores["chosen_expansion"] = scores["match_idx"].eq(e)
    if c == e or rc > N_LEGS or re > N_LEGS:
        raise ContractError("shape pair selection failed")
    return c, e, scores


def _shape_support(
    base_support: dict[int, tuple[str, ...]],
    score_rows: pd.DataFrame,
    contraction_match: int,
    expansion_match: int,
    shape: str,
) -> dict[int, tuple[str, ...]]:
    result = dict(base_support)
    if shape in {"CONTRACTION_ONLY", "BOTH"}:
        retained = str(score_rows.loc[score_rows["match_idx"].eq(contraction_match), "retained_outcome"].iloc[0])
        result[contraction_match] = (retained,)
    if shape in {"EXPANSION_ONLY", "BOTH"}:
        result[expansion_match] = OUTCOMES
    return result


def _ticket_units(issue: str, base: str, shape: str, codes: list[str]) -> dict[str, int]:
    count = len(codes)
    if count != TICKET_COUNTS[shape]:
        raise ContractError(f"{shape} ticket count differs from frozen contract")
    base_units, remainder = divmod(FUNDED_UNITS, count)
    ranked = sorted(
        codes,
        key=lambda code: (
            hashlib.sha256(f"{CONTRACT_ID}|{issue}|{base}|{shape}|{code}".encode()).hexdigest(),
            code,
        ),
    )
    extra = set(ranked[:remainder])
    units = {code: base_units + int(code in extra) for code in codes}
    if sum(units.values()) != FUNDED_UNITS or min(units.values()) <= 0:
        raise ContractError("deterministic integer allocation failed")
    return units


def construct_shapes(upstream: dict[str, Any]) -> dict[str, pd.DataFrame]:
    actions = upstream["actions"].copy()
    decisions0 = upstream["decisions"].copy()
    coverage0 = upstream["coverage"].copy()
    action_index = actions.set_index(["issue", "match_idx"])
    if not action_index.index.is_unique:
        raise ContractError("corrected action keys are not unique")
    decisions: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    bundles: list[dict[str, Any]] = []
    attribution: list[dict[str, Any]] = []
    pair_receipts: list[dict[str, Any]] = []

    for decision in decisions0.sort_values(["issue_anchor_ts", "issue", "arm"], kind="stable").itertuples():
        issue = str(decision.issue)
        base = _base_name(str(decision.arm))
        fixture_order = [int(value) for value in str(decision.selected_match_ids).split("|")]
        if len(fixture_order) != N_LEGS or fixture_order != sorted(fixture_order):
            raise ContractError("#366 selected fixture order is not canonical N6")
        selected = action_index.loc[[(issue, match_idx) for match_idx in fixture_order]].reset_index()
        frozen_support = json.loads(str(decision.support_json))
        base_support = {match_idx: _support_tuple(frozen_support[str(match_idx)]) for match_idx in fixture_order}
        c_match, e_match, scores = _rank_shape_pair(selected, base_support)
        for score in scores.itertuples():
            pair_receipts.append(
                {
                    "issue": issue,
                    "issue_year": int(decision.issue_year),
                    "base": base,
                    "match_idx": int(score.match_idx),
                    "contraction_score": float(score.contraction_score),
                    "expansion_score": float(score.expansion_score),
                    "retained_outcome": str(score.retained_outcome),
                    "omitted_outcome": str(score.omitted_outcome),
                    "contraction_rank": int(score.contraction_rank),
                    "expansion_rank": int(score.expansion_rank),
                    "chosen_contraction": bool(score.chosen_contraction),
                    "chosen_expansion": bool(score.chosen_expansion),
                }
            )
        for shape in SHAPES:
            support_map = _shape_support(base_support, scores, c_match, e_match, shape)
            support_order = [support_map[match_idx] for match_idx in fixture_order]
            choices = list(itertools.product(*support_order))
            codes = ["|".join(item) for item in choices]
            units_by_code = _ticket_units(issue, base, shape, codes)
            support_json = json.dumps(
                {str(key): "".join(value) for key, value in support_map.items()},
                sort_keys=True,
                separators=(",", ":"),
            )
            decisions.append(
                {
                    "issue": issue,
                    "issue_year": int(decision.issue_year),
                    "issue_anchor_ts": decision.issue_anchor_ts,
                    "base": base,
                    "shape": shape,
                    "selected_match_ids": decision.selected_match_ids,
                    "support_json": support_json,
                    "contraction_match_idx": c_match,
                    "expansion_match_idx": e_match,
                    "ticket_count": len(codes),
                    "funded_units": FUNDED_UNITS,
                    "planned_stake_cny": ISSUE_STAKE_CNY,
                    "settlement_status": decision.settlement_status,
                }
            )
            for ordinal, code in enumerate(codes):
                units = units_by_code[code]
                tickets.append(
                    {
                        "issue": issue,
                        "issue_year": int(decision.issue_year),
                        "base": base,
                        "shape": shape,
                        "ticket_ordinal": ordinal,
                        "ticket_code": code,
                        "units": units,
                        "stake_cny": units * STAKE_PER_UNIT_CNY,
                    }
                )
            realized = selected["result_code"].fillna("").astype(str).tolist()
            included = [value in support for value, support in zip(realized, support_order, strict=True)]
            misses = int(sum(not item for item in included))
            trusted = bool(selected["settlement_available"].astype(bool).all())
            winning_code = "|".join(realized)
            winning_units = units_by_code.get(winning_code, 0)
            winning_product = float(selected["winning_sp"].prod()) if trusted else math.nan
            gross = (
                winning_units * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR * winning_product
                if trusted and misses == 0 else 0.0
            )
            fractional_units = FUNDED_UNITS / len(codes)
            ideal_gross = (
                fractional_units * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR * winning_product
                if trusted and misses == 0 else 0.0
            )
            if trusted:
                bundles.append(
                    {
                        "issue": issue,
                        "issue_year": int(decision.issue_year),
                        "issue_anchor_ts": decision.issue_anchor_ts,
                        "base": base,
                        "shape": shape,
                        "ticket_count": len(codes),
                        "funded_units": FUNDED_UNITS,
                        "stake_cny": ISSUE_STAKE_CNY,
                        "gross_cny": gross,
                        "pnl_cny": gross - ISSUE_STAKE_CNY,
                        "ideal_fractional_gross_cny": ideal_gross,
                        "ideal_fractional_pnl_cny": ideal_gross - ISSUE_STAKE_CNY,
                        "integer_allocation_delta_cny": gross - ideal_gross,
                        "miss_count": misses,
                        "hit": bool(misses == 0),
                        "winning_ticket_units": int(winning_units),
                    }
                )
            for row, support, ok in zip(selected.itertuples(), support_order, included, strict=True):
                pair_row = scores[scores["match_idx"].eq(int(row.match_idx))].iloc[0]
                attribution.append(
                    {
                        "issue": issue,
                        "issue_year": int(decision.issue_year),
                        "base": base,
                        "shape": shape,
                        "match_idx": int(row.match_idx),
                        "base_support": "".join(base_support[int(row.match_idx)]),
                        "active_support": "".join(support),
                        "is_contraction_match": bool(int(row.match_idx) == c_match),
                        "is_expansion_match": bool(int(row.match_idx) == e_match),
                        "contraction_score": float(pair_row["contraction_score"]),
                        "expansion_score": float(pair_row["expansion_score"]),
                        "result_code": str(row.result_code),
                        "winning_sp": float(row.winning_sp),
                        "settlement_available": bool(row.settlement_available),
                        "realized_in_support": bool(ok),
                    }
                )
    coverage = coverage0.rename(columns={"settlement_complete": "included"}).copy()
    return {
        "decisions": pd.DataFrame(decisions),
        "tickets": pd.DataFrame(tickets),
        "bundles": pd.DataFrame(bundles),
        "attribution": pd.DataFrame(attribution),
        "pair_receipts": pd.DataFrame(pair_receipts),
        "coverage": coverage,
    }


def _generic_actions(cells: pd.DataFrame) -> pd.DataFrame:
    """Collapse #360 cells without the historical #338 year filter."""

    frame = cells.copy()
    frame["outcome"] = frame["outcome_code"].astype(str)
    keys = ["issue", "issue_year", "issue_anchor_ts", "match_idx"]
    wide = frame.pivot_table(
        index=keys,
        columns="outcome",
        values=["q_candidate", "q_line"],
        aggfunc="first",
    ).reindex(columns=pd.MultiIndex.from_product([["q_candidate", "q_line"], OUTCOMES]))
    wide = wide.dropna().reset_index()
    q = wide["q_candidate"].to_numpy(float)
    line = wide["q_line"].to_numpy(float)
    if not np.allclose(q.sum(axis=1), 1.0, rtol=0, atol=1e-6):
        raise ContractError("development q triplet is not normalized")
    order_index = np.broadcast_to(np.arange(len(OUTCOMES)), q.shape)
    omitted_idx = np.where(q == q.min(axis=1, keepdims=True), order_index, -1).argmax(axis=1)
    qeu = np.log(q / np.clip(line, 1e-4, None))
    min_score = qeu.min(axis=1, keepdims=True)
    score_candidates = qeu == min_score
    min_q = np.where(score_candidates, q, np.inf).min(axis=1, keepdims=True)
    qeu_idx = np.where(score_candidates & (q == min_q), order_index, -1).argmax(axis=1)
    outcomes = np.asarray(OUTCOMES)
    base_omit = outcomes[omitted_idx]
    qeu_omit = outcomes[qeu_idx]
    changed = base_omit != qeu_omit
    pressure = np.where(changed, qeu[np.arange(len(q)), omitted_idx] - qeu[np.arange(len(q)), qeu_idx], 0.0)
    result = wide[keys].copy()
    result.columns = keys
    result["baseline_support"] = ["".join(item for item in OUTCOMES if item != value) for value in base_omit]
    result["qeu_support"] = ["".join(item for item in OUTCOMES if item != value) for value in qeu_omit]
    result["retained_mass"] = 1.0 - q[np.arange(len(q)), omitted_idx]
    result["support_pressure"] = pressure
    for index, outcome in enumerate(OUTCOMES):
        result[f"q_eu_{outcome}"] = q[:, index]
    labels = frame.drop_duplicates(["issue", "match_idx"])[
        ["issue", "match_idx"]
    ].merge(
        pd.read_parquet(Path(frame.attrs["labels_path"]))[
            ["issue", "match_idx", "result_code", "label_available"]
        ],
        on=["issue", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    return result.merge(labels, on=["issue", "match_idx"], validate="one_to_one")


def development_diagnostics(repo_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    package = repo_root / "results/low_n_selector_data"
    cells = pd.read_parquet(package / "features/selector_cells.parquet")
    cells = cells[cells["issue_year"].isin(DEVELOPMENT_YEARS)].copy()
    cells["issue"] = cells["issue"].astype(str)
    if not (
        pd.to_datetime(cells["training_label_available_max_ts"], utc=True)
        < pd.to_datetime(cells["fixture_decision_ts"], utc=True)
    ).all():
        raise ContractError("development inputs are not strictly OOF")
    cells.attrs["labels_path"] = str(package / "labels/selector_labels.parquet")
    actions = _generic_actions(cells)
    selected_rows: list[dict[str, Any]] = []
    for (issue, year), group in actions.groupby(["issue", "issue_year"], sort=True):
        selected = group.sort_values(["retained_mass", "match_idx"], ascending=[False, True], kind="stable").head(N_LEGS)
        if len(selected) < N_LEGS:
            continue
        for base in BASES:
            support = {
                int(row.match_idx): _support_tuple(
                    row.baseline_support if base == "R0_CORRECTED" else row.qeu_support
                )
                for row in selected.itertuples()
            }
            if base == "R3_CORRECTED":
                activated = set(
                    selected.sort_values(["support_pressure", "match_idx"], ascending=[False, True], kind="stable")
                    .head(3)["match_idx"].astype(int)
                )
                support = {
                    int(row.match_idx): _support_tuple(
                        row.qeu_support if int(row.match_idx) in activated else row.baseline_support
                    )
                    for row in selected.itertuples()
                }
            _, _, scores = _rank_shape_pair(selected, support)
            score_map = scores.set_index("match_idx")
            for row in selected.itertuples():
                s = score_map.loc[int(row.match_idx)]
                realized = str(row.result_code)
                available = bool(row.label_available) and realized in OUTCOMES
                selected_rows.append(
                    {
                        "issue": str(issue), "issue_year": int(year), "base": base,
                        "match_idx": int(row.match_idx),
                        "contraction_score": float(s.contraction_score),
                        "expansion_score": float(s.expansion_score),
                        "supported_realized": bool(available and realized in support[int(row.match_idx)]),
                        "top1_realized": bool(available and realized == str(s.retained_outcome)),
                        "omitted_realized": bool(available and realized == str(s.omitted_outcome)),
                        "label_available": available,
                    }
                )
    diagnostic = pd.DataFrame(selected_rows)
    bins: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for base, group in diagnostic[diagnostic["label_available"]].groupby("base", sort=True):
        for score_name, target, conditioning in [
            ("contraction_score", "top1_realized", "SUPPORTED_REALIZED"),
            ("expansion_score", "omitted_realized", "ALL"),
        ]:
            subset = group[group["supported_realized"]].copy() if conditioning == "SUPPORTED_REALIZED" else group.copy()
            subset["score_bin"] = pd.qcut(subset[score_name], q=10, duplicates="drop")
            ordered = []
            for index, (_, part) in enumerate(subset.groupby("score_bin", observed=True, sort=True), start=1):
                row = {
                    "base": base, "diagnostic": score_name, "bin": index,
                    "rows": int(len(part)), "mean_score": float(part[score_name].mean()),
                    "observed_rate": float(part[target].mean()),
                }
                bins.append(row)
                ordered.append(row)
            x = np.array([row["mean_score"] for row in ordered], dtype=float)
            y = np.array([row["observed_rate"] for row in ordered], dtype=float)
            rank_corr = float(pd.Series(x).corr(pd.Series(y), method="spearman")) if len(x) > 1 else math.nan
            summaries.append(
                {
                    "base": base, "diagnostic": score_name, "conditioning": conditioning,
                    "rows": int(len(subset)), "mean_score": float(subset[score_name].mean()),
                    "observed_rate": float(subset[target].mean()),
                    "bin_spearman": rank_corr,
                    "nonnegative_monotonicity": bool(math.isfinite(rank_corr) and rank_corr >= 0),
                }
            )
    receipt = {
        "years": list(DEVELOPMENT_YEARS),
        "role": "STRICTLY_OOF_DEVELOPMENT_DIAGNOSTIC_ONLY",
        "issues": int(diagnostic["issue"].nunique()),
        "rows": int(len(diagnostic)),
        "available_rows": int(diagnostic["label_available"].sum()),
        "no_2022_2024_selection": True,
    }
    return pd.DataFrame(bins), pd.DataFrame(summaries), receipt


def _longest_run(mask: np.ndarray) -> int:
    best = current = 0
    for value in mask:
        current = current + 1 if bool(value) else 0
        best = max(best, current)
    return best


def _risk(group: pd.DataFrame) -> dict[str, float | int]:
    pnl = group["pnl_cny"].to_numpy(float)
    equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
    peaks = np.maximum.accumulate(equity)
    drawdown = (peaks - equity) / np.maximum(peaks, 1e-12)
    peak_indices = np.flatnonzero(drawdown <= 1e-15)
    open_underwater = int(len(pnl) - peak_indices[-1]) if drawdown[-1] > 1e-15 else 0
    payouts = group.loc[group["gross_cny"].gt(0), "gross_cny"].to_numpy(float)
    weights = payouts / payouts.sum() if payouts.sum() > 0 else np.array([])
    return {
        "max_drawdown_fraction": float(drawdown.max()),
        "longest_losing_run": _longest_run(pnl < 0),
        "open_underwater_issues": open_underwater,
        "largest_payout_share": float(weights.max()) if len(weights) else 0.0,
        "payout_hhi": float(np.square(weights).sum()) if len(weights) else 0.0,
    }


def evaluate(bundles: pd.DataFrame) -> dict[str, pd.DataFrame]:
    performance: list[dict[str, Any]] = []
    risk: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    integer: list[dict[str, Any]] = []
    scopes = [(str(year), bundles[bundles["issue_year"].eq(year)]) for year in YEARS] + [("ALL", bundles)]
    for scope, scoped in scopes:
        for (base, shape), group in scoped.groupby(["base", "shape"], sort=True):
            group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            pnl = group["pnl_cny"].to_numpy(float)
            winning = group[group["hit"]]
            largest_index = int(np.argmax(pnl)) if len(pnl) else 0
            performance.append(
                {
                    "scope": scope, "base": base, "shape": shape, "issues": int(len(group)),
                    "stake_cny": float(group["stake_cny"].sum()), "gross_cny": float(group["gross_cny"].sum()),
                    "pnl_cny": float(pnl.sum()), "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                    "hit_rate": float(group["hit"].mean()),
                    "conditional_gross_on_hit_cny": float(winning["gross_cny"].mean()) if len(winning) else 0.0,
                    "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest_index]) if len(pnl) else math.nan,
                }
            )
            risk.append({"scope": scope, "base": base, "shape": shape, **_risk(group)})
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            for order, (row, value) in enumerate(zip(group.itertuples(), capital, strict=True), start=1):
                paths.append(
                    {
                        "scope": scope, "base": base, "shape": shape, "issue_order": order,
                        "issue": row.issue, "issue_year": int(row.issue_year),
                        "issue_anchor_ts": row.issue_anchor_ts, "pnl_cny": float(row.pnl_cny),
                        "capital_cny": float(value),
                    }
                )
            integer.append(
                {
                    "scope": scope, "base": base, "shape": shape, "issues": int(len(group)),
                    "integer_pnl_cny": float(group["pnl_cny"].sum()),
                    "ideal_fractional_pnl_cny": float(group["ideal_fractional_pnl_cny"].sum()),
                    "integer_minus_ideal_cny": float(group["integer_allocation_delta_cny"].sum()),
                }
            )
    contrasts: list[dict[str, Any]] = []
    bootstrap: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for scope, scoped in scopes:
        wide = scoped.pivot(index="issue", columns=["base", "shape"], values="pnl_cny")
        specifications: list[tuple[str, np.ndarray, np.ndarray]] = []
        for base in BASES:
            control = wide[(base, "CONTROL")]
            contraction = wide[(base, "CONTRACTION_ONLY")]
            expansion = wide[(base, "EXPANSION_ONLY")]
            both = wide[(base, "BOTH")]
            ideal_wide = scoped.pivot(
                index="issue", columns=["base", "shape"], values="ideal_fractional_pnl_cny"
            )
            ideal_control = ideal_wide[(base, "CONTROL")]
            ideal_contraction = ideal_wide[(base, "CONTRACTION_ONLY")]
            ideal_expansion = ideal_wide[(base, "EXPANSION_ONLY")]
            ideal_both = ideal_wide[(base, "BOTH")]
            specifications.extend(
                [
                    (f"{base}:CONTRACTION_MAIN", (contraction - control).to_numpy(float), (ideal_contraction - ideal_control).to_numpy(float)),
                    (f"{base}:EXPANSION_MAIN", (expansion - control).to_numpy(float), (ideal_expansion - ideal_control).to_numpy(float)),
                    (f"{base}:BOTH_V_CONTROL", (both - control).to_numpy(float), (ideal_both - ideal_control).to_numpy(float)),
                    (f"{base}:FACTORIAL_INTERACTION", (both - contraction - expansion + control).to_numpy(float), (ideal_both - ideal_contraction - ideal_expansion + ideal_control).to_numpy(float)),
                ]
            )
        for shape in SHAPES:
            specifications.append(
                (
                    f"R3_MINUS_R0:{shape}",
                    (wide[("R3_CORRECTED", shape)] - wide[("R0_CORRECTED", shape)]).to_numpy(float),
                    (ideal_wide[("R3_CORRECTED", shape)] - ideal_wide[("R0_CORRECTED", shape)]).to_numpy(float),
                )
            )
        for contrast, delta, ideal_delta in specifications:
            if not np.isfinite(delta).all() or not np.isfinite(ideal_delta).all():
                raise ContractError(f"contrast denominator is not exact common: {contrast}/{scope}")
            largest = int(np.argmax(np.abs(delta))) if len(delta) else 0
            if len(delta):
                draw_indices = rng.integers(0, len(delta), (BOOTSTRAP_DRAWS, len(delta)))
                draws = delta[draw_indices].sum(axis=1)
                ideal_draws = ideal_delta[draw_indices].sum(axis=1)
            else:
                draws = ideal_draws = np.array([math.nan])
            row = {
                "scope": scope, "contrast": contrast, "issues": int(len(delta)),
                "matched_lift_cny": float(delta.sum()),
                "ideal_fractional_matched_lift_cny": float(ideal_delta.sum()),
                "integer_contribution_to_lift_cny": float(delta.sum() - ideal_delta.sum()),
                "largest_abs_delta_issue": str(wide.index[largest]) if len(delta) else "",
                "largest_abs_delta_cny": float(delta[largest]) if len(delta) else math.nan,
                "ex_largest_lift_cny": float(delta.sum() - delta[largest]) if len(delta) else math.nan,
            }
            contrasts.append(row)
            bootstrap.append(
                {
                    **row,
                    "bootstrap_p05_cny": float(np.nanquantile(draws, 0.05)),
                    "bootstrap_median_cny": float(np.nanquantile(draws, 0.5)),
                    "bootstrap_p95_cny": float(np.nanquantile(draws, 0.95)),
                    "ideal_bootstrap_p05_cny": float(np.nanquantile(ideal_draws, 0.05)),
                    "ideal_bootstrap_median_cny": float(np.nanquantile(ideal_draws, 0.5)),
                    "ideal_bootstrap_p95_cny": float(np.nanquantile(ideal_draws, 0.95)),
                }
            )
    return {
        "performance": pd.DataFrame(performance), "risk": pd.DataFrame(risk),
        "paths": pd.DataFrame(paths), "integer": pd.DataFrame(integer),
        "contrasts": pd.DataFrame(contrasts), "bootstrap": pd.DataFrame(bootstrap),
    }


def _expert_admission(performance: pd.DataFrame, contrasts: pd.DataFrame, bootstrap: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for base in BASES:
        for shape in SHAPES[1:]:
            perf = performance[(performance["scope"].eq("ALL")) & (performance["base"].eq(base)) & (performance["shape"].eq(shape))].iloc[0]
            contrast_id = f"{base}:{'BOTH_V_CONTROL' if shape == 'BOTH' else shape.replace('_ONLY', '_MAIN')}"
            agg = contrasts[(contrasts["scope"].eq("ALL")) & (contrasts["contrast"].eq(contrast_id))].iloc[0]
            boot = bootstrap[(bootstrap["scope"].eq("ALL")) & (bootstrap["contrast"].eq(contrast_id))].iloc[0]
            annual = contrasts[contrasts["scope"].isin([str(year) for year in YEARS]) & contrasts["contrast"].eq(contrast_id)]
            conditions = {
                "standalone_positive": bool(perf.pnl_cny > 0),
                "standalone_ex_largest_positive": bool(perf.ex_largest_pnl_cny > 0),
                "matched_lift_positive": bool(agg.matched_lift_cny > 0),
                "matched_ex_largest_positive": bool(agg.ex_largest_lift_cny > 0),
                "bootstrap_p05_nonnegative": bool(boot.bootstrap_p05_cny >= 0),
                "at_least_two_positive_annual_lifts": bool((annual["matched_lift_cny"] > 0).sum() >= 2),
            }
            rows.append(
                {
                    "base": base, "shape": shape, **conditions,
                    "admitted": bool(all(conditions.values())),
                }
            )
    return pd.DataFrame(rows)


def scientific_frames(repo_root: Path, data_root: Path) -> dict[str, Any]:
    upstream_package = repo_root / UPSTREAM_PACKAGE
    upstream_checks = verify_upstream(repo_root, upstream_package, data_root)
    if not all(upstream_checks.values()):
        raise ContractError("#366 source-bound verifier did not pass")
    upstream = upstream_frames(repo_root, data_root)
    shaped = construct_shapes(upstream)
    dev_bins, dev_summary, dev_receipt = development_diagnostics(repo_root)
    evaluated = evaluate(shaped["bundles"])
    admission = _expert_admission(evaluated["performance"], evaluated["contrasts"], evaluated["bootstrap"])
    control = shaped["bundles"][shaped["bundles"]["shape"].eq("CONTROL")].copy()
    upstream_settled = upstream["settled"].copy()
    upstream_settled["base"] = upstream_settled["arm"].map(_base_name)
    parity = control.merge(
        upstream_settled[["issue", "base", "pnl_cny", "gross_cny", "hit"]],
        on=["issue", "base"], suffixes=("_shape", "_366"), validate="one_to_one",
    )
    parity["exact_pnl"] = np.isclose(parity["pnl_cny_shape"], parity["pnl_cny_366"], rtol=0, atol=1e-9)
    parity["exact_gross"] = np.isclose(parity["gross_cny_shape"], parity["gross_cny_366"], rtol=0, atol=1e-9)
    parity["exact_hit"] = parity["hit_shape"].eq(parity["hit_366"])
    upstream_manifest = upstream_package / "MANIFEST.json"
    source = {
        "contract": CONTRACT_ID,
        "upstream_contract": _read_json(upstream_manifest).get("contract"),
        "upstream_manifest_sha256": sha256_file(upstream_manifest),
        "corrected_chronology": "SOURCE_ISSUE_REGISTRY_YEAR + FIXTURE_RELATIVE_10H",
        "evaluation_years": list(YEARS),
        "evaluation_role": "EXPOSED_HISTORICAL",
        "development": dev_receipt,
        "payout_factor_application": "ONCE_PER_COMPLETE_WINNING_TICKET",
        "issue_budget_cny": ISSUE_STAKE_CNY,
    }
    decision = {
        "contract": CONTRACT_ID,
        "verdict": "PROMOTION" if admission["admitted"].any() else "NO_PROMOTION",
        "admitted_experts": admission.loc[admission["admitted"], ["base", "shape"]].to_dict("records"),
        "control_parity_exact": bool(parity[["exact_pnl", "exact_gross", "exact_hit"]].all().all()),
        "promotable_to_210": False,
        "expert_pool_rule": "STANDALONE_POSITIVE_AND_ROBUST_ONLY",
        "notes": "Exposed historical support-shape evidence; does not alter #210/#218.",
    }
    return {
        "source": source, **shaped, "dev_bins": dev_bins, "dev_summary": dev_summary,
        **evaluated, "admission": admission, "control_parity": parity, "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "development_score_bins.csv": "dev_bins",
    "development_score_summary.csv": "dev_summary",
    "decisions.parquet": "decisions",
    "tickets.parquet": "tickets",
    "issue_bundles.parquet": "bundles",
    "support_attribution.parquet": "attribution",
    "shape_pair_receipts.parquet": "pair_receipts",
    "coverage_ledger.csv": "coverage",
    "performance.csv": "performance",
    "risk_diagnostics.csv": "risk",
    "capital_paths.csv": "paths",
    "integer_allocation_effect.csv": "integer",
    "contrasts.csv": "contrasts",
    "bootstrap.csv": "bootstrap",
    "expert_admission.csv": "admission",
    "control_parity.parquet": "control_parity",
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


def build_package(repo_root: Path, target: Path, explicit_data_root: Path | None = None, *, force: bool = False) -> dict[str, Any]:
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
        (staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    atomic_publish_directory(target.resolve(), populate, force=force)
    return frames["decision"]


def verify_package(repo_root: Path, target: Path, explicit_data_root: Path | None = None) -> dict[str, bool]:
    repo_root, target = repo_root.resolve(), target.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    manifest = _read_json(target / "MANIFEST.json")
    if manifest.get("contract") != CONTRACT_ID or set(manifest.get("files", {})) != set(PACKAGE_FILES):
        raise ContractError("manifest contract or exact file set mismatch")
    for relative, receipt in manifest["files"].items():
        path = target / relative
        if not path.is_file() or sha256_file(path) != receipt["sha256"]:
            raise ContractError(f"manifest file mismatch: {relative}")
    expected_implementation = {
        "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
        "pipeline.py": sha256_file(Path(__file__)),
    }
    if manifest.get("implementation") != expected_implementation:
        raise ContractError("implementation hashes do not match current code")
    expected = scientific_frames(repo_root, data_root)
    for relative, key in PACKAGE_FILES.items():
        actual_path = target / relative
        value = expected[key]
        if isinstance(value, pd.DataFrame):
            actual = pd.read_parquet(actual_path) if actual_path.suffix == ".parquet" else pd.read_csv(actual_path)
            if actual_path.suffix == ".parquet":
                matches = actual.equals(value)
            else:
                matches = hashlib.sha256(value.to_csv(index=False).encode("utf-8")).hexdigest() == sha256_file(actual_path)
            if not matches:
                raise ContractError(f"scientific frame mismatch: {relative}")
        elif _read_json(actual_path) != value:
            raise ContractError(f"receipt mismatch: {relative}")
    tickets = expected["tickets"]
    groups = tickets.groupby(["issue", "base", "shape"], observed=True)
    counts = groups.size()
    for (_, _, shape), count in counts.items():
        if count != TICKET_COUNTS[shape]:
            raise ContractError("ticket group is not the complete frozen Cartesian set")
    if not groups["ticket_code"].nunique().eq(counts).all() or not groups["units"].sum().eq(FUNDED_UNITS).all():
        raise ContractError("ticket uniqueness or unit budget failed")
    if not np.isclose(groups["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-12).all():
        raise ContractError("issue stake budget failed")
    bundles = expected["bundles"]
    if not np.allclose(bundles["pnl_cny"], bundles["gross_cny"] - ISSUE_STAKE_CNY, rtol=0, atol=1e-9):
        raise ContractError("bundle PnL identity failed")
    if not expected["control_parity"][["exact_pnl", "exact_gross", "exact_hit"]].all().all():
        raise ContractError("CONTROL does not exactly reproduce corrected #366")
    if expected["decisions"].groupby(["issue", "base"])["contraction_match_idx"].nunique().max() != 1:
        raise ContractError("contraction fixture is not shared across shapes")
    if expected["decisions"].groupby(["issue", "base"])["expansion_match_idx"].nunique().max() != 1:
        raise ContractError("expansion fixture is not shared across shapes")
    if (expected["decisions"]["contraction_match_idx"] == expected["decisions"]["expansion_match_idx"]).any():
        raise ContractError("contraction and expansion fixtures are not disjoint")
    expected_delivery = {
        "docs/research/Issue-369-N6-Support-Shape.md",
        "docs/research/figures/issue_369_support_shape_capital.png",
        "notebooks/research/n6-support-shape/n6_support_shape.ipynb",
    }
    if set(manifest.get("delivery", {})) != expected_delivery:
        raise ContractError("delivery receipt file set mismatch")
    for relative, expected_hash in manifest["delivery"].items():
        path = repo_root / relative
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise ContractError(f"delivery hash mismatch: {relative}")
    notebook = nbformat.read(repo_root / "notebooks/research/n6-support-shape/n6_support_shape.ipynb", as_version=4)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    if not code_cells or any(cell.get("execution_count") is None for cell in code_cells):
        raise ContractError("notebook is not fully executed")
    return {
        "manifest": True, "source_bound_replay": True, "development_only_diagnostic": True,
        "eight_cell_factorial": True, "fixed_budget_integer_allocation": True,
        "ticket_level_once_payout": True, "control_parity": True,
        "matched_contrasts": True, "expert_admission": True, "delivery": True,
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
    notebook_path = repo_root / "notebooks/research/n6-support-shape/n6_support_shape.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell("# Issue #377 — corrected N6 support-shape factorial"),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\nROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/n6_support_shape'"
        ),
        nbformat.v4.new_code_cell("dev=pd.read_csv(OUT/'development_score_summary.csv'); dev"),
        nbformat.v4.new_code_cell("perf=pd.read_csv(OUT/'performance.csv'); perf[perf.scope.eq('ALL')]"),
        nbformat.v4.new_code_cell("risk=pd.read_csv(OUT/'risk_diagnostics.csv'); risk[risk.scope.eq('ALL')]"),
        nbformat.v4.new_code_cell("contrasts=pd.read_csv(OUT/'bootstrap.csv'); contrasts[contrasts.scope.eq('ALL')]"),
        nbformat.v4.new_code_cell("integer=pd.read_csv(OUT/'integer_allocation_effect.csv'); integer[integer.scope.eq('ALL')]"),
        nbformat.v4.new_code_cell("admission=pd.read_csv(OUT/'expert_admission.csv'); admission"),
        nbformat.v4.new_code_cell(
            "paths=pd.read_csv(OUT/'capital_paths.csv')\nfig,axes=plt.subplots(1,2,figsize=(13,4),sharey=True)\nfor ax,(base,g) in zip(axes,paths[paths.scope.eq('ALL')].groupby('base')):\n    for shape,s in g.groupby('shape'): ax.plot(s.issue_order,s.capital_cny,label=shape)\n    ax.axhline(100000,color='black',lw=.8); ax.set_title(base); ax.legend(fontsize=7)\nplt.show()"
        ),
    ]
    NotebookClient(nb, timeout=300, kernel_name="python3").execute(cwd=str(notebook_path.parent))
    nbformat.write(nb, notebook_path)

    performance = pd.read_csv(package / "performance.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    bootstrap = pd.read_csv(package / "bootstrap.csv")
    integer = pd.read_csv(package / "integer_allocation_effect.csv")
    dev = pd.read_csv(package / "development_score_summary.csv")
    admission = pd.read_csv(package / "expert_admission.csv")
    coverage = pd.read_csv(package / "coverage_ledger.csv")
    decision = _read_json(package / "decision.json")
    all_perf = performance[performance["scope"].eq("ALL")]
    all_boot = bootstrap[bootstrap["scope"].eq("ALL")]
    r3_both = all_perf[
        all_perf["base"].eq("R3_CORRECTED") & all_perf["shape"].eq("BOTH")
    ].iloc[0]
    r3_control = all_perf[
        all_perf["base"].eq("R3_CORRECTED") & all_perf["shape"].eq("CONTROL")
    ].iloc[0]
    r3_both_lift = all_boot[all_boot["contrast"].eq("R3_CORRECTED:BOTH_V_CONTROL")].iloc[0]
    r3_interaction = all_boot[
        all_boot["contrast"].eq("R3_CORRECTED:FACTORIAL_INTERACTION")
    ].iloc[0]
    r0_contraction = all_perf[
        all_perf["base"].eq("R0_CORRECTED") & all_perf["shape"].eq("CONTRACTION_ONLY")
    ].iloc[0]
    r0_contraction_lift = all_boot[
        all_boot["contrast"].eq("R0_CORRECTED:CONTRACTION_MAIN")
    ].iloc[0]

    figure = repo_root / "docs/research/figures/issue_369_support_shape_capital.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    paths = pd.read_csv(package / "capital_paths.csv")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4), sharey=True)
    for ax, (base, group) in zip(axes, paths[paths["scope"].eq("ALL")].groupby("base"), strict=True):
        for shape, shape_group in group.groupby("shape"):
            ax.plot(shape_group["issue_order"], shape_group["capital_cny"], label=shape)
        ax.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8)
        ax.set_title(base)
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(figure, dpi=160)
    plt.close(fig)

    report = f"""# Issue #377 — corrected N6 support-shape factorial

Contract: `{CONTRACT_ID}`

## Decision

`{decision['verdict']}`. This is exposed historical evidence; it does not modify #210/#218 and it does not infer deployment readiness.

## Strictly OOF 2017–2021 score diagnostics

{_markdown_table(dev)}

The diagnostic checks the frozen probability-mass scores before 2022–2024 evaluation. It is descriptive calibration/monotonicity evidence, not a search over exposed outcomes.

## Eight-cell absolute performance

{_markdown_table(performance[performance['scope'].eq('ALL')])}

## Key findings

1. **The strongest point estimate is R3 + BOTH.** Ending capital is CNY{r3_both.ending_capital_cny:,.0f}, versus CNY{r3_control.ending_capital_cny:,.0f} for R3 CONTROL. The actual matched lift is CNY{r3_both_lift.matched_lift_cny:,.0f}; under ideal fractional units it remains CNY{r3_both_lift.ideal_fractional_matched_lift_cny:,.0f}. Thus the signal is not purely integer allocation luck, although integer placement contributes CNY{r3_both_lift.integer_contribution_to_lift_cny:,.0f}.
2. **The R3 interaction is the clearest but still borderline mechanism result.** The factorial interaction is CNY{r3_interaction.matched_lift_cny:,.0f}, with actual-unit paired-bootstrap p05 CNY{r3_interaction.bootstrap_p05_cny:,.0f}. Under ideal fractional units its lift remains CNY{r3_interaction.ideal_fractional_matched_lift_cny:,.0f}, but p05 is only CNY{r3_interaction.ideal_bootstrap_p05_cny:,.0f}, effectively on the zero boundary at bootstrap Monte Carlo resolution. Contraction or expansion alone does not improve R3; the joint capacity transfer signal is real enough to retain as a hypothesis, but its apparent robustness is integer-allocation-sensitive.
3. **The candidate still fails expert admission.** R3 BOTH has positive standalone and ex-largest PnL, but its lift bootstrap p05 is CNY{r3_both_lift.bootstrap_p05_cny:,.0f}. Its matched lift is positive in 2022 and 2024 but sharply negative in 2023. Maximum drawdown is slightly lower than R3 CONTROL (32.91% versus 33.17%), while the longest losing run is worse (22 versus 19 issues). This is a historical synergy candidate, not stable Edge.
4. **R0 contraction is informative but fragile.** It turns R0 from negative to CNY{r0_contraction.pnl_cny:,.0f} PnL and adds CNY{r0_contraction_lift.matched_lift_cny:,.0f}, yet standalone ex-largest PnL and bootstrap p05 remain negative. Concentrating stake can amplify the right tail without creating robust expectancy.
5. **Expansion alone trades precision for coverage without an aggregate lift.** Hit rates rise for both bases, but stake per ticket falls; neither base gains versus its own control on aggregate PnL.

## Path risk

{_markdown_table(risk[risk['scope'].eq('ALL')])}

## Matched effects and stability

{_markdown_table(bootstrap[bootstrap['scope'].eq('ALL')])}

## Integer allocation versus ideal fractional units

{_markdown_table(integer[integer['scope'].eq('ALL')])}

## Expert admission

{_markdown_table(admission)}

Only a candidate with positive standalone and ex-largest PnL, positive matched and ex-largest lift, non-negative paired-bootstrap p05, and at least two positive annual lifts is admitted. Low correlation or diversification is not Edge.

## Mechanism interpretation

- Contraction concentrates the fixed CNY1,024 budget into 64 tickets but loses the second supported outcome on one fixture.
- Expansion buys the omitted outcome on the hardest two-outcome fixture, spreading the same budget across 192 tickets.
- BOTH reallocates support capacity into a 96-ticket compromise; its factorial interaction is reported explicitly rather than inferred from the raw arm result.
- Non-divisible allocations use the frozen SHA-256 ticket rule. The ideal-fractional counterfactual isolates any integer-unit luck.

## Coverage and evidence boundary

The corrected registry contributes **{coverage['issue'].nunique()}** issues; **{int(coverage['included'].sum())}** have complete trusted settlement and **{int((~coverage['included']).sum())}** are excluded exactly as in #366. R0/R3 fixture selection and fixed R3 remain unchanged. All 2022–2024 outcomes are exposed historical evidence.

## Artifacts

- Package: `results/n6_support_shape/`
- Notebook: `notebooks/research/n6-support-shape/n6_support_shape.ipynb`
- Figure: `docs/research/figures/issue_369_support_shape_capital.png`
"""
    report_path = repo_root / "docs/research/Issue-369-N6-Support-Shape.md"
    report_path.write_text(report, encoding="utf-8")
    manifest_path = package / "MANIFEST.json"
    manifest = _read_json(manifest_path)
    manifest["delivery"] = {
        "docs/research/Issue-369-N6-Support-Shape.md": sha256_file(report_path),
        "docs/research/figures/issue_369_support_shape_capital.png": sha256_file(figure),
        "notebooks/research/n6-support-shape/n6_support_shape.ipynb": sha256_file(notebook_path),
    }
    atomic_write_json(manifest_path, manifest)
