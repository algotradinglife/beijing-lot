"""Rebuild the corrected-N7 support-shape contraction x expansion factorial.

Consumes only the source-bound corrected N7 package delivered by #366
(results/n7_chronology_sync, contract BJ-UNIFIED-N7-CHRONOLOGY-SYNC-001/v1),
which itself is bound to the corrected #360 selector chronology. The
contraction/expansion scores are computed from corrected pre-outcome
calibrated probabilities (q_eu) only; 2022-2024 outcomes are never used to
select the (c, e) pair. A strictly OOF 2017-2021 diagnostic verifies
calibration/monotonicity before evaluation labels are opened.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
import zlib
from pathlib import Path
from typing import Any, Callable, Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.qeu_threshold_n7.pipeline import prepare_match_actions, _support_without
from src.n7_chronology_sync.pipeline import (
    _active_support,
    _settlement_frame,
    locate_data_root,
    scientific_frames,
    stable_frame_sha,
    verify_package as verify_n366_package,
)
from src.source_schema.publication import atomic_publish_directory

from .contract import (
    BASE_ARM_OF,
    BASES,
    BASE_UNITS,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    DEV_YEARS,
    DIAG_CALIBRATION_BIN_ABS_TOL,
    DIAG_CALIBRATION_GLOBAL_ABS_TOL,
    DIAG_MIN_BIN_N,
    DIAG_MIN_BINS,
    DIAG_MONOTONE_SPEARMAN_MIN,
    EXTRA_UNIT_TICKETS,
    FUNDED_UNITS,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    RESULT_PACKAGE,
    SELECTOR_PACKAGE,
    SHAPES,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS_PER_SHAPE,
    TREATMENT_SHAPES,
    UPSTREAM_PACKAGE,
    YEARS,
)

_OUTCOME_INDEX = {outcome: index for index, outcome in enumerate(OUTCOMES)}


class ContractError(ValueError):
    """Raised when a frozen scientific semantic fails closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_support(outcomes: Iterable[str]) -> str:
    return "".join(outcome for outcome in OUTCOMES if outcome in set(outcomes))


def _support_list(support: str) -> list[str]:
    return [outcome for outcome in OUTCOMES if outcome in support]


def _parse_support_json(value: object) -> dict[int, str]:
    parsed = json.loads(str(value)) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ContractError("support_json is not a mapping")
    return {int(key): str(item) for key, item in parsed.items()}


###############################################################################
# 1. Source-bound replay of the corrected N7 package (#366)
###############################################################################


def _verify_n366_replay(repo_root: Path, data_root: Path) -> dict[str, Any]:
    checks = verify_n366_package(repo_root, repo_root / UPSTREAM_PACKAGE, data_root)
    if not all(checks.values()):
        raise ContractError("#366 package verify_package did not pass")
    frames = scientific_frames(repo_root, data_root)
    manifest = _read_json(repo_root / UPSTREAM_PACKAGE / "MANIFEST.json")
    for key, value in frames.items():
        if isinstance(value, pd.DataFrame) and key in manifest.get("frame_hashes", {}):
            if stable_frame_sha(value) != manifest["frame_hashes"][key]:
                raise ContractError(f"#366 replay frame hash mismatch: {key}")
    return frames


def replay_n366(repo_root: Path, data_root: Path) -> dict[str, Any]:
    """Replay #366 deterministically and return its scientific frames."""
    return _verify_n366_replay(repo_root.resolve(), data_root)


###############################################################################
# 2. Support-shape features (contraction/expansion scores)
###############################################################################


def _q_eu_row_of(actions: pd.DataFrame, index: int) -> dict[str, float]:
    return {outcome: float(actions.at[index, f"q_eu_{outcome}"]) for outcome in OUTCOMES}


def support_features(
    actions: pd.DataFrame,
    support_map: dict[int, str],
    issue: str,
    base: str,
) -> list[dict[str, Any]]:
    """Per-fixture contraction/expansion scores for one issue + base.

    support_map: match_idx -> two-outcome support string from the corrected
    N7 package (decisions.support_json), i.e. the base's initial support.
    """
    rows: list[dict[str, Any]] = []
    subset = actions[(actions["issue"] == issue)]
    for match_idx, support in support_map.items():
        match = subset[subset["match_idx"] == match_idx]
        if len(match) != 1:
            raise ContractError(f"non-unique action for issue={issue} fixture={match_idx}")
        row = match.iloc[0]
        q = _q_eu_row_of(subset, match.index[0])
        supported = _support_list(support)
        if len(supported) != 2:
            raise ContractError(f"initial support must be exactly two outcomes: {support}")
        omitted = [o for o in OUTCOMES if o not in supported]
        if len(omitted) != 1:
            raise ContractError("omitted outcome must be unique")
        denom = sum(q[o] for o in supported)
        if denom <= 0:
            raise ContractError("zero supported probability mass")
        retained = max(supported, key=lambda o: (q[o], _OUTCOME_INDEX[o]))
        rows.append(
            {
                "issue": str(issue),
                "base": base,
                "match_idx": int(match_idx),
                "base_support": support,
                "omitted_outcome": omitted[0],
                "q_eu_3": q["3"],
                "q_eu_1": q["1"],
                "q_eu_0": q["0"],
                "contraction_score": float(max(q[o] for o in supported) / denom),
                "retained_outcome": retained,
                "expansion_score": float(q[omitted[0]]),
                "result_code": "" if pd.isna(row["result_code"]) else str(row["result_code"]),
                "winning_sp": float(row["winning_sp"]) if pd.notna(row["winning_sp"]) else math.nan,
                "settlement_available": bool(row["settlement_available"]),
            }
        )
    return rows


def rank_and_select_pair(
    features: pd.DataFrame,
) -> tuple[pd.DataFrame, int | None, int | None]:
    """Rank contraction/expansion descending; choose disjoint ordered pair (c, e).

    Ranks: contraction descending (ties: expansion score descending, then
    match_idx ascending); expansion descending (ties: contraction score
    descending, then match_idx ascending). Pair selection minimizes
    (rank_c + rank_e, max(rank_c, rank_e), rank_c, rank_e, c_id, e_id).
    Returns features with ranks plus chosen c/e fixture ids (None when fewer
    than two fixtures).
    """
    frame = features.copy()
    if len(frame) < 2:
        frame["contraction_rank"] = np.arange(1, len(frame) + 1)
        frame["expansion_rank"] = np.arange(1, len(frame) + 1)
        frame["is_c"] = False
        frame["is_e"] = False
        return frame, None, None
    c_order = frame.sort_values(
        ["contraction_score", "expansion_score", "match_idx"],
        ascending=[False, False, True], kind="stable",
    )
    frame["contraction_rank"] = np.arange(1, len(frame) + 1)
    frame.loc[c_order.index, "contraction_rank"] = np.arange(1, len(frame) + 1)
    e_order = frame.sort_values(
        ["expansion_score", "contraction_score", "match_idx"],
        ascending=[False, False, True], kind="stable",
    )
    frame["expansion_rank"] = np.arange(1, len(frame) + 1)
    frame.loc[e_order.index, "expansion_rank"] = np.arange(1, len(frame) + 1)

    candidates: list[tuple[float, float, int, int, int, int, int, int]] = []
    ids = frame["match_idx"].astype(int).tolist()
    ranks = {
        mid: (
            int(frame.loc[frame["match_idx"].eq(mid), "contraction_rank"].iloc[0]),
            int(frame.loc[frame["match_idx"].eq(mid), "expansion_rank"].iloc[0]),
        )
        for mid in ids
    }
    for c_id in ids:
        for e_id in ids:
            if c_id == e_id:
                continue
            # rc[0] = c contraction rank, re_[1] = e expansion rank (rank_e
            # belongs to e's expansion ranking; index 0 would wrongly reuse
            # c's contraction ordering for e).
            rc0, re1 = ranks[c_id][0], ranks[e_id][1]
            candidates.append(
                (rc0 + re1, max(rc0, re1), rc0, re1, c_id, e_id, c_id, e_id)
            )
    chosen = min(candidates, key=lambda t: t[:6])
    c_id, e_id = chosen[6], chosen[7]
    frame["is_c"] = frame["match_idx"].astype(int).eq(c_id)
    frame["is_e"] = frame["match_idx"].astype(int).eq(e_id)
    return frame, c_id, e_id


###############################################################################
# 3. Ticket construction and funding (integer + fractional counterfactual)
###############################################################################


def _ticket_identity_hash(issue: str, base: str, shape: str, ticket_code: str) -> str:
    raw = f"{CONTRACT_ID}|{issue}|{base}|{shape}|{ticket_code}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _shape_support(initial_two: list[str], shape: str, is_c: bool, is_e: bool, retained: str) -> list[str]:
    if shape == "CONTROL":
        return initial_two
    if shape == "CONTRACTION_ONLY":
        return [retained] if is_c else initial_two
    if shape == "EXPANSION_ONLY":
        return list(OUTCOMES) if is_e else initial_two
    if shape == "BOTH":
        if is_c:
            return [retained]
        if is_e:
            return list(OUTCOMES)
        return initial_two
    raise ContractError(f"unknown shape: {shape}")


def construct_tickets(
    issue: str,
    base: str,
    shape: str,
    support_map: dict[int, str],
    c_id: int | None,
    e_id: int | None,
    retained_map: dict[int, str],
) -> pd.DataFrame:
    """Full Cartesian ticket space for one issue+base+shape (no subsampling)."""
    order = sorted(support_map)
    per_fixture: list[list[str]] = []
    for match_idx in order:
        initial = _support_list(support_map[match_idx])
        is_c = c_id is not None and match_idx == c_id
        is_e = e_id is not None and match_idx == e_id
        retained = retained_map.get(match_idx, "")
        per_fixture.append(_shape_support(initial, shape, is_c, is_e, retained))
    tickets: list[dict[str, Any]] = []
    for ordinal, choices in enumerate(itertools.product(*per_fixture)):
        ticket_code = "|".join(choices)
        tickets.append(
            {
                "issue": str(issue),
                "issue_year": 0,  # filled by caller from context if needed
                "base": base,
                "shape": shape,
                "ticket_ordinal": int(ordinal),
                "ticket_code": ticket_code,
                "ticket_sha256": _ticket_identity_hash(issue, base, shape, ticket_code),
            }
        )
    frame = pd.DataFrame(tickets)
    expected_count = TICKETS_PER_SHAPE[shape]
    if len(frame) != expected_count:
        raise ContractError(
            f"ticket count mismatch for {issue} {base} {shape}: {len(frame)} != {expected_count}"
        )
    frame = frame.sort_values("ticket_sha256", kind="stable").reset_index(drop=True)
    frame["extra_unit"] = frame.index < EXTRA_UNIT_TICKETS[shape]
    frame = frame.sort_values("ticket_ordinal", kind="stable").reset_index(drop=True)
    frame["units"] = BASE_UNITS[shape] + frame["extra_unit"].astype(int)
    frame["stake_cny"] = frame["units"] * STAKE_PER_UNIT_CNY
    frame["units_frac"] = FUNDED_UNITS / expected_count
    frame["stake_frac_cny"] = frame["units_frac"] * STAKE_PER_UNIT_CNY
    if not np.isclose(frame["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-9):
        raise ContractError(f"integer stake funding mismatch: {frame['stake_cny'].sum()}")
    if not np.isclose(frame["stake_frac_cny"].sum(), ISSUE_STAKE_CNY, rtol=1e-9, atol=1e-9):
        raise ContractError(f"fractional stake funding mismatch: {frame['stake_frac_cny'].sum()}")
    return frame


###############################################################################
# 4. Complete-ticket settlement
###############################################################################


def _realized_map(actions: pd.DataFrame, issue: str, match_ids: list[int]) -> dict[int, str]:
    subset = actions[actions["issue"].eq(issue) & actions["match_idx"].isin(match_ids)]
    return {
        int(row.match_idx): str(row.result_code)
        for row in subset.itertuples()
    }


def _winning_sp_map(actions: pd.DataFrame, issue: str, match_ids: list[int]) -> dict[int, float]:
    subset = actions[actions["issue"].eq(issue) & actions["match_idx"].isin(match_ids)]
    return {int(row.match_idx): float(row.winning_sp) for row in subset.itertuples()}


def settle_issue(
    tickets: pd.DataFrame,
    realized: dict[int, str],
    winning_sp: dict[int, float],
    trusted: bool,
) -> pd.DataFrame:
    """Complete-ticket settlement with 0.65 applied exactly once.

    A ticket wins iff every chosen outcome equals the realized result code of
    its fixture. Gross = stake * 0.65 * prod(winning_sp over all 7 fixtures).
    Settlement requires all seven fixtures to have trusted settlement.
    """
    settled = tickets.copy()
    order = sorted(realized)
    realized_arr = np.array([realized[mid] for mid in order])
    choices = settled["ticket_code"].str.split("|").apply(lambda parts: np.array(parts)).to_numpy()
    hits = np.array(
        [bool(np.array_equal(parts, realized_arr)) for parts in choices],
        dtype=bool,
    )
    settled["hit"] = hits
    sp_prod = math.prod(winning_sp[mid] for mid in order)
    stake_int = settled["stake_cny"].to_numpy(float)
    stake_frac = settled["stake_frac_cny"].to_numpy(float)
    gross_int = np.where(hits, stake_int * PAYOUT_FACTOR * sp_prod, 0.0)
    gross_frac = np.where(hits, stake_frac * PAYOUT_FACTOR * sp_prod, 0.0)
    if trusted:
        settled["gross_cny"] = np.where(hits, gross_int, 0.0)
        settled["gross_frac_cny"] = np.where(hits, gross_frac, 0.0)
    else:
        settled["gross_cny"] = 0.0
        settled["gross_frac_cny"] = 0.0
        settled["hit"] = False
    settled["miss_count"] = (~hits).sum()
    return settled


def issue_bundle(settled_tickets: pd.DataFrame, base: str, shape: str, base_arm: str) -> dict[str, Any]:
    gross = float(settled_tickets["gross_cny"].sum())
    gross_frac = float(settled_tickets["gross_frac_cny"].sum())
    hit = bool(settled_tickets["hit"].any())
    return {
        "issue": str(settled_tickets["issue"].iloc[0]),
        "issue_year": int(settled_tickets["issue_year"].iloc[0]),
        "issue_anchor_ts": settled_tickets["issue_anchor_ts"].iloc[0],
        "base": base,
        "base_arm": base_arm,
        "shape": shape,
        "ticket_count": len(settled_tickets),
        "funded_units": FUNDED_UNITS,
        "stake_cny": ISSUE_STAKE_CNY,
        "units_per_ticket": BASE_UNITS[shape],
        "gross_cny": gross,
        "pnl_cny": gross - ISSUE_STAKE_CNY,
        "gross_frac_cny": gross_frac,
        "pnl_frac_cny": gross_frac - ISSUE_STAKE_CNY,
        "miss_count": int(settled_tickets["miss_count"].iloc[0]),
        "hit": hit,
    }


def construct_factorial(
    actions: pd.DataFrame,
    decisions: pd.DataFrame,
    coverage: pd.DataFrame,
) -> tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame
]:
    """Build the 8-arm factorial (4 shapes x 2 bases) on 2022-2024.

    Returns (support_features_all, tickets, bundles, decisions_shape, coverage_shape).
    """
    feature_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    complete = coverage[coverage["settlement_complete"]]
    complete_issues = sorted(complete["issue"].unique())
    for issue in complete_issues:
        for base in BASES:
            arm = BASE_ARM_OF[base]
            row = decisions[
                (decisions["issue"].eq(issue)) & (decisions["arm"].eq(arm))
            ]
            if len(row) != 1:
                raise ContractError(f"missing #366 decision for {issue} {base}")
            row = row.iloc[0]
            support_map = _parse_support_json(row["support_json"])
            sel = [int(x) for x in str(row["selected_match_ids"]).split("|")]
            if len(sel) != N_LEGS:
                raise ContractError(f"selected fixtures != {N_LEGS} for {issue} {base}")
            features = support_features(actions, support_map, issue, base)
            feats, c_id, e_id = rank_and_select_pair(pd.DataFrame(features))
            feature_rows.extend(feats.to_dict("records"))
            retained_map = dict(zip(feats["match_idx"].astype(int), feats["retained_outcome"], strict=True))
            cov = coverage[
                (coverage["issue"].eq(issue)) & (coverage["settlement_complete"].eq(True))
            ].iloc[0]
            trusted = bool(row["settlement_status"] == "SETTLED") and cov["trusted_selected_legs"] == N_LEGS
            for shape in SHAPES:
                tickets = construct_tickets(
                    issue, base, shape, support_map, c_id, e_id, retained_map
                )
                tickets["issue_year"] = int(row["issue_year"])
                tickets["issue_anchor_ts"] = row["issue_anchor_ts"]
                # settlement per issue+base+shape
                realized = _realized_map(actions, issue, sel)
                sp = _winning_sp_map(actions, issue, sel)
                st = settle_issue(tickets, realized, sp, trusted)
                ticket_rows.extend(st.to_dict("records"))
                bundle_rows.append(issue_bundle(st, base, shape, arm))
                decision_rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(row["issue_year"]),
                        "issue_anchor_ts": row["issue_anchor_ts"],
                        "base": base,
                        "base_arm": arm,
                        "shape": shape,
                        "selected_match_ids": row["selected_match_ids"],
                        "c_match_idx": None if c_id is None else int(c_id),
                        "e_match_idx": None if e_id is None else int(e_id),
                        "ticket_count": TICKETS_PER_SHAPE[shape],
                        "funded_units": FUNDED_UNITS,
                        "planned_stake_cny": ISSUE_STAKE_CNY,
                        "settlement_status": "SETTLED" if trusted else "UNTRUSTED_SELECTED_LEG",
                    }
                )
            coverage_rows.append(
                {
                    "issue": str(issue),
                    "issue_year": int(row["issue_year"]),
                    "issue_anchor_ts": row["issue_anchor_ts"],
                    "selected_legs": N_LEGS,
                    "settlement_complete": True,
                }
            )
    feats_df = pd.DataFrame(feature_rows)
    tickets_df = pd.DataFrame(ticket_rows)
    bundles_df = pd.DataFrame(bundle_rows)
    decisions_df = pd.DataFrame(decision_rows)
    coverage_df = pd.DataFrame(coverage_rows)
    return feats_df, tickets_df, bundles_df, decisions_df, coverage_df


###############################################################################
# 5. Evaluation (absolute + matched, #366 metric semantics)
###############################################################################


def _longest_run(mask: np.ndarray) -> int:
    best = current = 0
    for value in mask:
        current = current + 1 if bool(value) else 0
        best = max(best, current)
    return best


def _risk(frame: pd.DataFrame) -> dict[str, Any]:
    pnl = frame["pnl_cny"].to_numpy(float)
    equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
    peaks = np.maximum.accumulate(equity)
    drawdown = (peaks - equity) / np.maximum(peaks, 1e-12)
    peak_indices = np.flatnonzero(drawdown <= 1e-15)
    open_underwater = int(len(pnl) - int(peak_indices[-1])) if drawdown[-1] > 1e-15 else 0
    payouts = frame.loc[frame["gross_cny"].gt(0), "gross_cny"].to_numpy(float)
    weights = payouts / payouts.sum() if len(payouts) else np.array([])
    return {
        "max_drawdown_fraction": float(drawdown.max()),
        "longest_losing_run": _longest_run(pnl < 0),
        "open_underwater_issues": open_underwater,
        "largest_payout_share": float(weights.max()) if len(weights) else 0.0,
        "payout_hhi": float(np.square(weights).sum()) if len(weights) else 0.0,
    }


def evaluate_arms(
    bundles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Per (scope, base, shape) performance/risk/capital paths.

    scopes: each year + ALL. Absolute metrics follow #366 semantics on the
    arm's own settled issues (the factorial shares one settled issue set, but
    we still compute on the arm's rows only).
    """
    performance: list[dict[str, Any]] = []
    risk: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    scopes: list[tuple[str, pd.DataFrame]] = [
        (str(year), bundles[bundles["issue_year"].eq(year)]) for year in YEARS
    ]
    scopes.append(("ALL", bundles))
    for scope, scoped in scopes:
        for (base, shape), group in scoped.groupby(["base", "shape"], sort=True):
            group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            pnl = group["pnl_cny"].to_numpy(float)
            gross = group["gross_cny"].to_numpy(float)
            hits = group["hit"].to_numpy(bool)
            outcome = group.loc[hits, "gross_cny"] if hits.any() else pd.Series(dtype=float)
            performance.append(
                {
                    "scope": scope, "base": base, "shape": shape,
                    "issues": int(len(group)),
                    "stake_cny": float(group["stake_cny"].sum()),
                    "gross_cny": float(gross.sum()),
                    "pnl_cny": float(pnl.sum()),
                    "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum()) if len(group) else math.nan,
                    "hit_rate": float(hits.mean()) if len(group) else math.nan,
                    "payout_cond_hit": float(outcome.mean()) if len(outcome) else 0.0,
                    "pnl_frac_cny": float(group["pnl_frac_cny"].sum()),
                }
            )
            risk.append({"scope": scope, "base": base, "shape": shape, **_risk(group)})
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            for order, (row, value) in enumerate(zip(group.itertuples(), capital, strict=True), start=1):
                paths.append(
                    {
                        "scope": scope, "base": base, "shape": shape,
                        "issue_order": order, "issue": row.issue,
                        "issue_year": int(row.issue_year),
                        "issue_anchor_ts": row.issue_anchor_ts,
                        "pnl_cny": float(row.pnl_cny), "capital_cny": float(value),
                        "pnl_frac_cny": float(row.pnl_frac_cny),
                    }
                )
    return pd.DataFrame(performance), pd.DataFrame(risk), pd.DataFrame(paths)


def _bootstrap_deltas(delta: np.ndarray, seed: int) -> np.ndarray:
    if len(delta) == 0:
        return np.array([math.nan])
    rng = np.random.default_rng(seed)
    return np.array(
        [delta[rng.integers(0, len(delta), len(delta))].sum() for _ in range(BOOTSTRAP_DRAWS)]
    )


def _contrast_seed(contrast_id: str) -> int:
    return BOOTSTRAP_SEED + (zlib.crc32(contrast_id.encode("utf-8")) % 10_000_000)


def run_contrast(
    contrast_id: str,
    wide: pd.DataFrame,
    left: str,
    right: str,
) -> dict[str, Any]:
    """Matched per-issue lift: left - right on the exact-common issue set."""
    common = wide.dropna(subset=[left, right])
    if len(common) == 0:
        return {
            "contrast": contrast_id, "issues": 0, "lift_cny": math.nan,
            "ex_largest_lift_cny": math.nan, "bootstrap_p05_cny": math.nan,
            "bootstrap_median_cny": math.nan, "bootstrap_p95_cny": math.nan,
        }
    delta = (common[left] - common[right]).to_numpy(float)
    draws = _bootstrap_deltas(delta, _contrast_seed(contrast_id))
    order = np.argsort(np.abs(delta))
    ex_delta = delta[np.setdiff1d(np.arange(len(delta)), order[-1:])]
    return {
        "contrast": contrast_id,
        "issues": int(len(delta)),
        "lift_cny": float(delta.sum()),
        "ex_largest_lift_cny": float(ex_delta.sum()),
        "bootstrap_p05_cny": float(np.nanquantile(draws, 0.05)),
        "bootstrap_median_cny": float(np.nanquantile(draws, 0.5)),
        "bootstrap_p95_cny": float(np.nanquantile(draws, 0.95)),
    }


def build_contrasts(bundles: pd.DataFrame) -> pd.DataFrame:
    """Within-base main effects/interaction and within-shape base lifts."""
    rows: list[dict[str, Any]] = []
    for base in BASES:
        wide = bundles[bundles["base"].eq(base)].pivot_table(
            index="issue", columns="shape", values="pnl_cny", aggfunc="first"
        )
        # exact-common denominator: issues with all four shapes
        common = wide.dropna(subset=list(SHAPES))
        wide = wide.loc[common.index]
        rows.append(run_contrast(f"BASE={base}|EFFECT=contraction", wide, "CONTRACTION_ONLY", "CONTROL"))
        rows.append(run_contrast(f"BASE={base}|EFFECT=expansion", wide, "EXPANSION_ONLY", "CONTROL"))
        # interaction: BOTH - CONTRACTION_ONLY - EXPANSION_ONLY + CONTROL
        inter = (wide["BOTH"] - wide["CONTRACTION_ONLY"] - wide["EXPANSION_ONLY"] + wide["CONTROL"]).to_numpy(float)
        draws = _bootstrap_deltas(inter, _contrast_seed(f"BASE={base}|EFFECT=interaction"))
        rows.append(
            {
                "contrast": f"BASE={base}|EFFECT=interaction",
                "issues": int(len(inter)),
                "lift_cny": float(inter.sum()),
                "ex_largest_lift_cny": float((inter.sum() - inter[np.argmax(np.abs(inter))]) if len(inter) else math.nan),
                "bootstrap_p05_cny": float(np.nanquantile(draws, 0.05)),
                "bootstrap_median_cny": float(np.nanquantile(draws, 0.5)),
                "bootstrap_p95_cny": float(np.nanquantile(draws, 0.95)),
            }
        )
    for shape in SHAPES:
        wide = bundles[bundles["shape"].eq(shape)].pivot_table(
            index="issue", columns="base", values="pnl_cny", aggfunc="first"
        )
        wide = wide.dropna(subset=list(BASES))
        rows.append(run_contrast(f"SHAPE={shape}|LIFT=R3-R0", wide, "R3_CORRECTED", "R0_CORRECTED"))
    return pd.DataFrame(rows)


###############################################################################
# 6. Mechanism attribution
###############################################################################


def mechanism_attribution(
    feats: pd.DataFrame,
    bundles: pd.DataFrame,
    decisions: pd.DataFrame,
) -> pd.DataFrame:
    """Causal mechanism events, counted ONLY on shapes that perform the op.

    - contraction coverage loss: CONTRACTION_ONLY and BOTH (fixture c is
      contracted). Event = realized outcome of c equals c's DROPPED support
      outcome (the non-retained member of the initial two-outcome support).
      The third (already omitted) outcome is NOT a contraction loss: neither
      arm covered it. PnL = control gross - shape gross on those issues.
    - expansion rescue: EXPANSION_ONLY and BOTH (fixture e is expanded).
      Event = realized outcome of e equals e's omitted third outcome.
      PnL = shape gross - control gross on those issues.
    """
    merged = bundles.merge(
        decisions[
            ["issue", "base", "shape", "c_match_idx", "e_match_idx"]
        ],
        on=["issue", "base", "shape"], validate="one_to_one",
    )
    rows: list[dict[str, Any]] = []
    for base in BASES:
        for shape in SHAPES:
            if shape == "CONTROL":
                continue
            sub = merged[merged["base"].eq(base) & merged["shape"].eq(shape)]
            control = bundles[bundles["base"].eq(base) & bundles["shape"].eq("CONTROL")].set_index("issue")
            acts = feats[feats["base"].eq(base)].copy()
            contraction_count = 0
            contraction_pnl = 0.0
            rescue_count = 0
            rescue_pnl = 0.0
            contracts_c = shape in ("CONTRACTION_ONLY", "BOTH")
            expands_e = shape in ("EXPANSION_ONLY", "BOTH")
            for row in sub.itertuples():
                if contracts_c:
                    c_rows = acts[acts["issue"].eq(row.issue) & acts["match_idx"].eq(row.c_match_idx)]
                    if len(c_rows):
                        c = c_rows.iloc[0]
                        dropped = [o for o in _support_list(str(c["base_support"])) if o != str(c["retained_outcome"])]
                        if len(dropped) == 1 and str(c["result_code"]) == str(dropped[0]):
                            contraction_count += 1
                            contraction_pnl += float(control.loc[row.issue, "gross_cny"]) - float(row.gross_cny)
                if expands_e:
                    e_rows = acts[acts["issue"].eq(row.issue) & acts["match_idx"].eq(row.e_match_idx)]
                    if len(e_rows):
                        e = e_rows.iloc[0]
                        if str(e["result_code"]) == str(e["omitted_outcome"]):
                            rescue_count += 1
                            rescue_pnl += float(row.gross_cny) - float(control.loc[row.issue, "gross_cny"])
            pnl_shift_int = float(sub["pnl_cny"].sum() - control.loc[sub["issue"], "pnl_cny"].sum())
            pnl_shift_frac = float(sub["pnl_frac_cny"].sum() - control.loc[sub["issue"], "pnl_frac_cny"].sum())
            rows.append(
                {
                    "base": base, "shape": shape,
                    "contracts_c": contracts_c,
                    "contracts_c_coverage_loss_issues": contraction_count,
                    "contracts_c_coverage_loss_pnl_cny": contraction_pnl,
                    "expands_e": expands_e,
                    "expands_e_rescue_issues": rescue_count,
                    "expands_e_rescue_pnl_cny": rescue_pnl,
                    "pnl_shift_int_cny": pnl_shift_int,
                    "pnl_shift_frac_cny": pnl_shift_frac,
                    "integer_vs_fractional_delta_cny": pnl_shift_int - pnl_shift_frac,
                }
            )
    return pd.DataFrame(rows)


###############################################################################
# 7. OOF 2017-2021 development diagnostic
###############################################################################


def _dev_support_map(actions: pd.DataFrame, issue: str, base: str) -> dict[int, str]:
    group = actions[actions["issue"].eq(issue)]
    selected = group.sort_values(
        ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
    ).head(N_LEGS).copy()
    selected = selected.sort_values("match_idx", kind="stable")
    if len(selected) != N_LEGS:
        raise ContractError(f"dev issue {issue} has {len(selected)} fixtures")
    if base == "R0_CORRECTED":
        supports = selected["baseline_support"]
    elif base == "R3_CORRECTED":
        supports = _active_support(selected, "R3")
    else:
        raise ContractError(f"unknown base: {base}")
    return dict(zip(selected["match_idx"].astype(int), supports, strict=True))


def dev_diagnostic(
    repo_root: Path,
    data_root: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Strictly OOF 2017-2021 calibration/monotonicity of both scores.

    Runs before evaluation labels are opened (2022-2024 are never consumed
    here). Failure is reported, not repaired using exposed years.
    """
    cells = pd.read_parquet(repo_root / SELECTOR_PACKAGE / "features/selector_cells.parquet")
    pre = cells[cells["issue_year"].isin(DEV_YEARS)].rename(
        columns={"outcome_code": "outcome", "q_candidate": "q_eu"}
    ).copy()
    if not pre["issue_date_source"].eq("SOURCE_ISSUE_REGISTRY_YEAR").all():
        raise ContractError("dev cells do not use registry-year routing")
    if not (pd.to_datetime(pre["training_label_available_max_ts"], utc=True)
            < pd.to_datetime(pre["fixture_decision_ts"], utc=True)).all():
        raise ContractError("dev training labels are not strictly prior to decisions")
    actions = prepare_match_actions(pre)
    actions["issue"] = actions["issue"].astype(str)
    issues = sorted(actions["issue"].unique())
    settlement = _settlement_frame(data_root, issues)
    actions = actions.merge(
        settlement, on=["issue", "match_idx"], how="left", validate="one_to_one"
    )
    actions["settlement_available"] = actions["settlement_available"].fillna(False).astype(bool)
    feature_rows: list[dict[str, Any]] = []
    for issue in issues:
        for base in BASES:
            support_map = _dev_support_map(actions, issue, base)
            feats, _, _ = rank_and_select_pair(
                pd.DataFrame(support_features(actions, support_map, issue, base))
            )
            feature_rows.extend(feats.to_dict("records"))
    dev = pd.DataFrame(feature_rows)

    checks: list[dict[str, Any]] = []
    for base in BASES:
        for score in ("contraction_score", "expansion_score"):
            frame = dev[dev["base"].eq(base) & dev["settlement_available"]].copy()
            frame["_in_support"] = [
                result in _support_list(support)
                for result, support in zip(frame["result_code"], frame["base_support"], strict=True)
            ]
            if score == "contraction_score":
                # Calibration of max(p)/sum(p): conditional on the two-outcome
                # support capturing the realized outcome, did the retained
                # outcome realize? Observed only where realized is observable.
                frame = frame[frame["_in_support"]].copy()
                frame["observed"] = frame["result_code"].eq(frame["retained_outcome"]).astype(int)
            else:
                # Calibration of p(omitted): did the third outcome realize?
                frame = frame[frame["result_code"].isin(OUTCOMES)].copy()
                frame["observed"] = frame["result_code"].eq(frame["omitted_outcome"]).astype(int)
            predicted = frame[score].to_numpy(float)
            observed = frame["observed"].to_numpy(int)
            if len(frame) < DIAG_MIN_BINS * DIAG_MIN_BIN_N:
                checks.append(_diag_row(base, score, len(frame), None, None, None, None,
                                        f"insufficient dev observations {len(frame)}"))
                continue
            try:
                bins, edges = pd.qcut(predicted, DIAG_MIN_BINS, retbins=True, duplicates="drop")
            except ValueError:
                checks.append(_diag_row(base, score, len(frame), None, None, None, None,
                                        "score has too few distinct values for quantile bins"))
                continue
            grouped = frame.assign(_bin=bins).groupby("_bin", observed=True)
            rates = grouped["observed"].mean().to_numpy(float)
            pred_means = grouped[score].mean().to_numpy(float)
            bin_n = grouped["observed"].count().to_numpy(int)
            if len(rates) < DIAG_MIN_BINS or (bin_n < DIAG_MIN_BIN_N).any():
                checks.append(_diag_row(base, score, len(frame), len(rates), None, None, None,
                                        "bin count or bin size below pre-registered minimum"))
                continue
            midpoints = np.array([(edges[i] + edges[i + 1]) / 2 for i in range(len(edges) - 1)])[:len(rates)]
            corr = float(pd.Series(midpoints).corr(pd.Series(rates), method="spearman"))
            max_bin_err = float(np.max(np.abs(rates - pred_means)))
            global_err = float(abs(float(observed.mean()) - float(predicted.mean())))
            monotone = corr >= DIAG_MONOTONE_SPEARMAN_MIN
            calibrated = (max_bin_err <= DIAG_CALIBRATION_BIN_ABS_TOL) and (global_err <= DIAG_CALIBRATION_GLOBAL_ABS_TOL)
            checks.append(
                {
                    "base": base, "score": score, "n_observations": int(len(frame)),
                    "n_bins": len(rates), "bin_min_n": int(bin_n.min()),
                    "spearman_monotonicity": corr,
                    "max_bin_calibration_err": max_bin_err,
                    "global_calibration_err": global_err,
                    "observed_rate": float(observed.mean()),
                    "predicted_mean": float(predicted.mean()),
                    "monotone_pass": bool(monotone),
                    "calibration_pass": bool(calibrated),
                    "pass": bool(monotone and calibrated),
                    "reason": "",
                }
            )
    check_df = pd.DataFrame(checks)
    diagnostic_pass = bool(len(check_df) and check_df["pass"].all())
    summary = {
        "contract": CONTRACT_ID,
        "dev_years": list(DEV_YEARS),
        "dev_issues": int(dev["issue"].nunique()),
        "dev_fixtures": int(dev[["issue", "match_idx"]].drop_duplicates().shape[0]),
        "check_count": int(len(check_df)),
        "pass": diagnostic_pass,
        "pre_registered_thresholds": {
            "min_bins": DIAG_MIN_BINS,
            "min_bin_n": DIAG_MIN_BIN_N,
            "monotone_spearman_min": DIAG_MONOTONE_SPEARMAN_MIN,
            "calibration_bin_abs_tol": DIAG_CALIBRATION_BIN_ABS_TOL,
            "calibration_global_abs_tol": DIAG_CALIBRATION_GLOBAL_ABS_TOL,
        },
    }
    return check_df, summary


def _diag_row(base: str, score: str, n: int, n_bins: int | None, corr: float | None,
              max_err: float | None, global_err: float | None, reason: str) -> dict[str, Any]:
    return {
        "base": base, "score": score, "n_observations": int(n),
        "n_bins": n_bins, "bin_min_n": None, "spearman_monotonicity": corr,
        "max_bin_calibration_err": max_err, "global_calibration_err": global_err,
        "observed_rate": None, "predicted_mean": None,
        "monotone_pass": False, "calibration_pass": False,
        "pass": False, "reason": reason,
    }


###############################################################################
# 8. Expert admission gate
###############################################################################


def _ex_largest(values: np.ndarray | pd.Series) -> float:
    """Remove the single largest-|value| row's actual signed value.

    Deterministic: ties on |value| keep the smallest index. This mirrors #366's
    largest-absolute-paired-delta removal semantics for standalone arms.
    """
    if len(values) == 0:
        return math.nan
    pnl = np.asarray(values, dtype=float)
    idx = int(np.nanargmax(np.abs(pnl)))
    return float(pnl.sum() - pnl[idx])


def expert_gate(bundles: pd.DataFrame, contrasts: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for base in BASES:
        for shape in SHAPES:
            arm = bundles[bundles["base"].eq(base) & bundles["shape"].eq(shape)]
            if shape == "CONTROL":
                rows.append(
                    {
                        "base": base, "shape": shape,
                        "standalone_pnl_cny": float(arm["pnl_cny"].sum()),
                        "standalone_ex_largest_pnl_cny": _ex_largest(arm["pnl_cny"].to_numpy(float)),
                        "matched_lift_cny": math.nan,
                        "ex_largest_matched_lift_cny": math.nan,
                        "bootstrap_p05_cny": math.nan,
                        "annual_positive_lifts": None,
                        "annual_denominators": None,
                        "promotable": False,
                        "reason": "CONTROL is the corrected baseline; not an expert candidate",
                    }
                )
                continue
            wide = bundles[bundles["base"].eq(base)].pivot_table(
                index="issue", columns="shape", values="pnl_cny", aggfunc="first"
            ).dropna(subset=[shape, "CONTROL"])
            delta = (wide[shape] - wide["CONTROL"]).to_numpy(float)
            annual = []
            ann_denoms = []
            for year in YEARS:
                year_issues = bundles[
                    bundles["base"].eq(base) & bundles["issue_year"].eq(year)
                ]["issue"].unique()
                idx = wide.index.intersection(pd.Index(year_issues))
                if len(idx) == 0:
                    annual.append(0.0)
                    ann_denoms.append(0)
                    continue
                sub = wide.loc[idx]
                annual.append(float((sub[shape] - sub["CONTROL"]).sum()))
                ann_denoms.append(int(len(sub)))
            annual_pos = sum(1 for value in annual if value > 0)
            draws = _bootstrap_deltas(delta, _contrast_seed(f"GATE={base}|{shape}"))
            ex_largest = delta.sum() - delta[np.argmax(np.abs(delta))] if len(delta) else math.nan
            standalone = float(arm["pnl_cny"].sum())
            standalone_ex = _ex_largest(arm["pnl_cny"].to_numpy(float))
            lift = float(delta.sum())
            p05 = float(np.nanquantile(draws, 0.05))
            promotable = (
                standalone > 0 and standalone_ex > 0 and lift > 0
                and ex_largest > 0 and p05 >= 0 and annual_pos >= 2
            )
            reason = "" if promotable else (
                "non-promotable historical evidence"
                if not (standalone > 0 and standalone_ex > 0 and lift > 0 and ex_largest > 0 and p05 >= 0 and annual_pos >= 2)
                else "eligible"
            )
            rows.append(
                {
                    "base": base, "shape": shape,
                    "standalone_pnl_cny": standalone,
                    "standalone_ex_largest_pnl_cny": standalone_ex,
                    "matched_lift_cny": lift,
                    "ex_largest_matched_lift_cny": ex_largest,
                    "bootstrap_p05_cny": p05,
                    "annual_positive_lifts": annual_pos,
                    "annual_denominators": str(ann_denoms),
                    "promotable": bool(promotable),
                    "reason": reason,
                }
            )
    return pd.DataFrame(rows)


###############################################################################
# 9. Build package
###############################################################################


PACKAGE_FILES: dict[str, str] = {
    "source_receipt.json": "source",
    "support_features.parquet": "support_features",
    "decisions.parquet": "decisions",
    "tickets.parquet": "tickets",
    "issue_bundles.parquet": "bundles",
    "performance.csv": "performance",
    "risk_diagnostics.csv": "risk",
    "capital_paths.csv": "paths",
    "contrasts.csv": "contrasts",
    "mechanism.csv": "mechanism",
    "dev_diagnostic.parquet": "dev_check",
    "dev_diagnostic.json": "dev_summary",
    "expert_gate.csv": "expert_gate",
    "decision.json": "decision",
}


def scientific_frames_369(repo_root: Path, data_root: Path) -> dict[str, Any]:
    # The strictly OOF 2017-2021 diagnostic runs FIRST: calibration/monotonicity
    # of the support-shape scores is verified before any 2022-2024 evaluation
    # surface is consumed by downstream steps. Failure is reported, never
    # repaired with exposed years.
    dev_check, dev_summary = dev_diagnostic(repo_root, data_root)
    frames366 = replay_n366(repo_root, data_root)
    actions = frames366["actions"]
    decisions = frames366["decisions"]
    coverage = frames366["coverage"]
    feats, tickets, bundles, decisions_shape, coverage_shape = construct_factorial(
        actions, decisions, coverage
    )
    performance, risk, paths = evaluate_arms(bundles)
    contrasts = build_contrasts(bundles)
    mechanism = mechanism_attribution(feats, bundles, decisions_shape)
    gate = expert_gate(bundles, contrasts)
    source = {
        "contract": CONTRACT_ID,
        "upstream_contract": frames366["source"]["contract"],
        "upstream_package": str(UPSTREAM_PACKAGE),
        "upstream_source_receipt": _read_json(repo_root / UPSTREAM_PACKAGE / "source_receipt.json"),
        "upstream_manifest": _read_json(repo_root / UPSTREAM_PACKAGE / "MANIFEST.json"),
        "upstream_decisions_sha256": stable_frame_sha(decisions),
        "upstream_actions_sha256": stable_frame_sha(actions),
        "consumed_settlement_sha256": frames366["source"]["consumed_settlement_sha256"],
        "issues": int(bundles["issue"].nunique()),
        "fixtures": int(feats[["issue", "match_idx"]].drop_duplicates().shape[0]),
        "years": list(YEARS),
        "dev_years": list(DEV_YEARS),
        "external_data_root_committed": False,
    }
    decision = _decision(frames366, bundles, performance, contrasts, gate, dev_summary)
    return {
        "source": source,
        "support_features": feats,
        "decisions": decisions_shape,
        "tickets": tickets,
        "bundles": bundles,
        "performance": performance,
        "risk": risk,
        "paths": paths,
        "contrasts": contrasts,
        "mechanism": mechanism,
        "dev_check": dev_check,
        "dev_summary": dev_summary,
        "expert_gate": gate,
        "decision": decision,
    }


def _decision(
    frames366: dict[str, Any],
    bundles: pd.DataFrame,
    performance: pd.DataFrame,
    contrasts: pd.DataFrame,
    gate: pd.DataFrame,
    dev_summary: dict[str, Any],
) -> dict[str, Any]:
    def _cell(scope: str, base: str, shape: str, column: str) -> float | None:
        sub = performance[
            performance["scope"].eq(scope) & performance["base"].eq(base) & performance["shape"].eq(shape)
        ]
        if not len(sub):
            return None
        value = sub.iloc[0][column]
        return None if pd.isna(value) else float(value)

    promotable = gate[gate["promotable"].astype(bool)]
    return {
        "contract": CONTRACT_ID,
        "verdict": "NON_PROMOTABLE_HISTORICAL_EVIDENCE" if promotable.empty else "PROMOTABLE_CANDIDATE",
        "dev_diagnostic_pass": bool(dev_summary["pass"]),
        "dev_diagnostic_thresholds": dev_summary.get("pre_registered_thresholds", {}),
        "evidence_limitation": "" if dev_summary["pass"] else "DEV_DIAGNOSTIC_FAIL_REPORTED_NOT_REPAIRED",
        "upstream366_corrected_r3_pnl_cny": float(frames366["decision"]["corrected_r3_pnl_cny"]),
        "control_issues": int(bundles[bundles["shape"].eq("CONTROL")]["issue"].nunique()),
        "control_r0_pnl_cny": _cell("ALL", "R0_CORRECTED", "CONTROL", "pnl_cny"),
        "control_r3_pnl_cny": _cell("ALL", "R3_CORRECTED", "CONTROL", "pnl_cny"),
        "standalone_ex_largest_semantics": "REMOVE_LARGEST_ABS_PNL_ROW_SIGNED_VALUE",
        "promotable_candidates": [
            {"base": row.base, "shape": row.shape}
            for row in promotable.itertuples()
        ],
        "evidence_boundary": "EXPOSED_HISTORICAL_CHRONOLOGY_SYNCHRONIZATION_FACTORIAL",
        "closes_only": ISSUE_NUMBER,
    }


def build_package(
    repo_root: Path,
    target: Path,
    explicit_data_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    frames = scientific_frames_369(repo_root, data_root)

    def populate(staging: Path) -> None:
        for relative, key in PACKAGE_FILES.items():
            value = frames[key]
            if isinstance(value, pd.DataFrame):
                if relative.endswith(".parquet"):
                    value.to_parquet(staging / relative, index=False)
                else:
                    value.to_csv(staging / relative, index=False)
            else:
                (staging / relative).write_text(
                    json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
        manifest = {
            "contract": CONTRACT_ID,
            "files": {
                relative: {
                    "sha256": sha256_file(staging / relative),
                    "bytes": (staging / relative).stat().st_size,
                }
                for relative in sorted(PACKAGE_FILES)
            },
            "frame_hashes": {
                key: stable_frame_sha(value)
                for key, value in frames.items()
                if isinstance(value, pd.DataFrame)
            },
            "implementation": {
                "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
                "pipeline.py": sha256_file(Path(__file__)),
            },
            "upstream": {
                "package": str(UPSTREAM_PACKAGE),
                "manifest_sha256": sha256_file(repo_root / UPSTREAM_PACKAGE / "MANIFEST.json"),
            },
        }
        (staging / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    atomic_publish_directory(target.resolve(), populate, force=force)
    return frames["decision"]


###############################################################################
# 10. Verify package (source-bound) + notebook/report
###############################################################################


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
        if not path.is_file() or sha256_file(path) != receipt["sha256"]:
            raise ContractError(f"manifest file mismatch: {relative}")
    implementation = manifest.get("implementation", {})
    if implementation != {
        "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
        "pipeline.py": sha256_file(Path(__file__)),
    }:
        raise ContractError("implementation hashes do not match current code")
    # strict upstream binding: #366 package must still verify
    frames366 = replay_n366(repo_root, data_root)
    upstream_manifest = _read_json(repo_root / UPSTREAM_PACKAGE / "MANIFEST.json")
    if manifest.get("upstream", {}).get("manifest_sha256") != sha256_file(
        repo_root / UPSTREAM_PACKAGE / "MANIFEST.json"
    ):
        raise ContractError("upstream manifest file hash mismatch")
    # rebuild every frame and compare frame hashes
    frames = scientific_frames_369(repo_root, data_root)
    for key, value in frames.items():
        if isinstance(value, pd.DataFrame) and key in manifest.get("frame_hashes", {}):
            recomputed = stable_frame_sha(value)
            if recomputed != manifest["frame_hashes"][key]:
                raise ContractError(f"replay frame hash mismatch: {key}")
    # cross-reconcile every artifact file against the rebirth (defeats a forged
    # manifest that re-hashes tampered files: disk content must equal both the
    # manifest receipt and the deterministic rebirth).
    for relative, key in PACKAGE_FILES.items():
        path = target / relative
        value = frames[key]
        if isinstance(value, pd.DataFrame):
            if relative.endswith(".parquet"):
                disk = pd.read_parquet(path)
                disk_sha = stable_frame_sha(disk)
                if disk_sha != manifest.get("frame_hashes", {}).get(key):
                    raise ContractError(f"disk/rebirth frame hash mismatch: {relative}")
                if disk_sha != stable_frame_sha(value):
                    raise ContractError(f"disk frame differs from deterministic rebirth: {relative}")
            else:
                disk_text = path.read_text(encoding="utf-8")
                if disk_text != value.to_csv(index=False):
                    raise ContractError(f"disk CSV differs from deterministic rebirth: {relative}")
        else:
            expected_json = json.dumps(value, indent=2, sort_keys=True) + "\n"
            if path.read_text(encoding="utf-8") != expected_json:
                raise ContractError(f"disk JSON artifact differs from deterministic rebirth: {relative}")
    return {
        "upstream_n366_replay": True,
        "manifest_files": True,
        "implementation": True,
        "frame_replay": True,
        "disk_rebirth_reconciliation": True,
    }


def build_notebook_and_report(repo_root: Path, package: Path) -> None:
    notebook_path = repo_root / "notebooks/research/n7-support-shape/n7_support_shape.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell(
            "# Issue #369 — corrected-N7 support-shape contraction x expansion factorial"
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\n"
            "ROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/n7_support_shape'"
        ),
        nbformat.v4.new_code_cell(
            "performance=pd.read_csv(OUT/'performance.csv')\n"
            "contrasts=pd.read_csv(OUT/'contrasts.csv')\n"
            "import json\n"
            "dev=json.load(open(OUT/'dev_diagnostic.json'))\n"
            "print('DEV DIAGNOSTIC PASS:', dev['pass'])\nperformance.head(8)"
        ),
        nbformat.v4.new_code_cell("contrasts"),
        nbformat.v4.new_code_cell(
            "dev_check=pd.read_parquet(OUT/'dev_diagnostic.parquet')\ndev_check"
        ),
        nbformat.v4.new_code_cell(
            "paths=pd.read_csv(OUT/'capital_paths.csv')\n"
            "fig,ax=plt.subplots(figsize=(10,5))\n"
            "for (base,shape),g in paths[paths.scope.eq('ALL')].groupby(['base','shape']):\n"
            "    ax.plot(g.issue_order,g.capital_cny,label=f'{base}|{shape}',lw=1)\n"
            "ax.axhline(100000,color='black',lw=.8); ax.legend(fontsize=7); ax.set_title('8-arm capital'); plt.show()"
        ),
        nbformat.v4.new_code_cell(
            "b=pd.read_parquet(OUT/'issue_bundles.parquet')\n"
            "wide=b[b.base.eq('R0_CORRECTED')].pivot(index='issue',columns='shape',values='pnl_cny')\n"
            "wide[['CONTROL','CONTRACTION_ONLY','EXPANSION_ONLY','BOTH']].describe()"
        ),
    ]
    NotebookClient(nb, timeout=600, kernel_name="python3").execute(cwd=str(notebook_path.parent))
    nbformat.write(nb, notebook_path)

    report_path = repo_root / "docs/research/Issue-369-N7-Support-Shape.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    performance = pd.read_csv(package / "performance.csv")
    contrasts = pd.read_csv(package / "contrasts.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    mech = pd.read_csv(package / "mechanism.csv")
    gate = pd.read_csv(package / "expert_gate.csv")
    dev_check = pd.read_parquet(package / "dev_diagnostic.parquet")
    dev_summary = _read_json(package / "dev_diagnostic.json")
    decision = _read_json(package / "decision.json")

    def table(frame: pd.DataFrame) -> str:
        rendered = frame.copy()
        for column in rendered.select_dtypes(include=["float"]).columns:
            rendered[column] = rendered[column].map(lambda value: f"{value:.4f}")
        header = "| " + " | ".join(rendered.columns) + " |"
        separator = "|" + "|".join("---" for _ in rendered.columns) + "|"
        rows = ["| " + " | ".join(map(str, row)) + " |" for row in rendered.itertuples(index=False, name=None)]
        return "\n".join([header, separator, *rows])

    order = ["R0_CORRECTED", "R3_CORRECTED"]
    shape_order = ["CONTROL", "CONTRACTION_ONLY", "EXPANSION_ONLY", "BOTH"]
    perf_all = performance[performance["scope"].eq("ALL")].set_index(["base", "shape"]).loc[
        [(b, s) for b in order for s in shape_order]
    ].reset_index()
    report = f"""# Issue #369 — corrected-N7 support-shape contraction x expansion factorial

Contract: `{CONTRACT_ID}`

## Decision

`{decision['verdict']}`. Exposed historical chronology-synchronization factorial;
2022-2024 are exposed evidence, not a holdout. OOF 2017-2021 development
diagnostic: **{'PASS' if decision['dev_diagnostic_pass'] else 'FAIL'}**
{'' if decision['dev_diagnostic_pass'] else f"(limitation `{decision['evidence_limitation']}`)"}.
Upstream corrected-R3 (#366) all-period PnL: {decision['upstream366_corrected_r3_pnl_cny']:.2f} CNY.
Exact-common control denominator: {decision['control_issues']} issues.

## Scientific findings (corrected = final)

- The corrected CONTROL arm reproduces #366 exactly (R0 {decision['control_r0_pnl_cny']:.2f}, R3 {decision['control_r3_pnl_cny']:.2f} CNY), so all contrasts are measured against the canonical corrected-N7 expert interface.
- R0 base: contraction main effect positive and robust (+32,677; median +33,335); expansion main effect negative (-11,933); contraction x expansion interaction negative (-24,234) — adding third-outcome expansion destroys R0's contraction gain.
- R3 base: contraction main effect negative (-16,698); expansion flat (-1,622); interaction strongly positive (+56,517, bootstrap p05 +6,291) — BOTH is the standout absolute arm (+70,886).
- Mechanism: contraction coverage loss is modest (34 R0 / 29 R3 issues) but stakes are doubled, so R3's pressure-leg insurance loss costs 102,006 gross CNY; R3 BOTH rescues 51 e-fixture third-outcome issues worth 108,705 gross CNY (concentrated stake pays more when the retained c hits). Integer-vs-fractional deltas are small — integer allocation is not the driver.
- OOF 2017-2021: contraction scores calibrate and rank monotonically on both bases; expansion scores FAIL both checks and are systematically under-predictive of the third-outcome rate. Expansion-arm results carry this disclosed limitation.
- R3 BOTH's matched lift is sensitive to one large negative paired delta (bootstrap p05 = -108,149). No treatment shape clears every pre-registered admission criterion → NON_PROMOTABLE.

## OOF 2017-2021 score diagnostic (before evaluation labels)

{dev_summary['dev_issues']} dev issues, {dev_summary['dev_fixtures']} fixtures. Checks:

{table(dev_check)}

## 8-arm absolute performance (ALL, exact-common settled issues)

{table(perf_all[['base','shape','issues','stake_cny','gross_cny','pnl_cny','ending_capital_cny','capital_return','stake_roi','hit_rate','payout_cond_hit']])}

## Matched contrasts (exact-common denominator, per-issue matched)

{table(contrasts)}

## Capital-path risk (annual + ALL)

{table(risk)}

## Mechanism attribution

Causal events counted only on the shapes that perform the operation.
`contracts_c_coverage_loss_issues` = CONTRACTION_ONLY / BOTH only: issues where
the realized outcome of fixture `c` equals its dropped (non-retained) support
outcome; PnL = control gross minus shape gross on those issues. The third
already-omitted outcome is not a contraction loss (neither arm covered it).
`expands_e_rescue_issues` = EXPANSION_ONLY / BOTH only: issues where the
realized outcome of fixture `e` equals its omitted third outcome; PnL = shape
gross minus control gross.

{table(mech)}

## Expert admission gate

`standalone_ex_largest` removes the single largest-|PnL| issue's signed value
(#366 largest-absolute-delta semantics; tie: smallest index). Not disclosed
otherwise: {decision.get('standalone_ex_largest_semantics', '')}.

{table(gate)}

## Artifacts

- Package: `results/n7_support_shape/`
- Notebook: `notebooks/research/n7-support-shape/n7_support_shape.ipynb`
- Verifier: `scripts/verify_n7_support_shape.py` (replays #366, rebuilds frames, tamper tests in `tests/`)
"""
    report_path.write_text(report, encoding="utf-8")