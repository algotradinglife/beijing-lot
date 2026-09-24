"""Build and independently verify the corrected-N7 temporal-policy diagnostic."""

from __future__ import annotations

import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
from nbclient import NotebookClient
import numpy as np
import pandas as pd

from src.cutoff_walkforward.pipeline import verify_package as verify_mapping_package
from src.n7_chronology_sync.pipeline import (
    locate_data_root,
    verify_package as verify_n7_package,
)
from src.n7_support_shape.pipeline import _rank_shape_pair
from src.n7_support_transfer_grid.pipeline import (
    _maximal_assignment,
    _ticket_units,
    verify_package as verify_shape_package,
)
from src.qeu_threshold_n7.pipeline import prepare_match_actions
from src.source_schema.publication import atomic_publish_directory
from beidan_backend.temporal_learning import implementation_closure, verify_implementation_closure
from beidan_backend.temporal_learning.core import stable_json_hash

from .contract import (
    ALLOWED_VERDICTS,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    EXPONENTIAL_HALF_LIFE_DAYS,
    FIGURE_PATH,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    MOVING_BLOCK_LENGTH,
    NOTEBOOK_PATH,
    N_LEGS,
    PAYOUT_FACTOR,
    POLICIES,
    PRIMARY_ARM,
    PRIMARY_TICKETS,
    RECENT_BLEND,
    RECENT_WINDOW_ISSUES,
    REPORT_PATH,
    RESULT_PACKAGE,
    SECONDARY_ARM,
    SECONDARY_TICKETS,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    SUPPORT_ARMS,
    UPSTREAM_MAPPING_PACKAGE,
    UPSTREAM_N7_PACKAGE,
    UPSTREAM_SHAPE_PACKAGE,
    YEARS,
)


OUTCOMES = ("3", "1", "0")
OUTCOME_ORDER = {outcome: position for position, outcome in enumerate(OUTCOMES)}


class ContractError(ValueError):
    """Raised when a frozen scientific or evidence invariant fails closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    projected = frame.loc[:, sorted(frame.columns)].copy()
    for name in projected.columns:
        if isinstance(projected[name].dtype, pd.CategoricalDtype):
            projected[name] = projected[name].astype("string")
    hashes = np.sort(
        pd.util.hash_pandas_object(
            projected, index=False, categorize=False
        ).to_numpy(np.uint64)
    )
    schema = [(name, str(projected[name].dtype)) for name in projected.columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode())
    digest.update(hashes.tobytes())
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_upstreams(repo_root: Path, data_root: Path) -> dict[str, str]:
    checks = {
        "mapping": verify_mapping_package(
            repo_root, repo_root / UPSTREAM_MAPPING_PACKAGE, data_root
        ),
        "n7": verify_n7_package(repo_root, repo_root / UPSTREAM_N7_PACKAGE, data_root),
        "shape": verify_shape_package(
            repo_root, repo_root / UPSTREAM_SHAPE_PACKAGE, data_root
        ),
    }
    if any(not all(values.values()) for values in checks.values()):
        raise ContractError("an upstream source-bound verifier did not pass")
    return {
        name: sha256_file(repo_root / package / "MANIFEST.json")
        for name, package in {
            "cutoff_walkforward_manifest_sha256": UPSTREAM_MAPPING_PACKAGE,
            "n7_chronology_manifest_sha256": UPSTREAM_N7_PACKAGE,
            "n7_support_transfer_manifest_sha256": UPSTREAM_SHAPE_PACKAGE,
        }.items()
    }


def _load_inputs(repo_root: Path) -> dict[str, Any]:
    mapping_package = repo_root / UPSTREAM_MAPPING_PACKAGE
    n7_package = repo_root / UPSTREAM_N7_PACKAGE
    mapped = pd.read_parquet(mapping_package / "mapped_probabilities.parquet")
    mapped["issue_code"] = mapped["issue_code"].astype(str)
    mapped["fixture_decision_ts"] = pd.to_datetime(
        mapped["fixture_decision_ts"], utc=True
    )
    if set(mapped["policy"].unique()) != set(POLICIES):
        raise ContractError("mapping policy key set differs from the frozen contract")
    if mapped.duplicated(["issue_code", "match_idx", "policy"]).any():
        raise ContractError("mapped probability keys are not unique")
    if not mapped["issue_year"].isin(YEARS).all():
        raise ContractError("mapped surface contains an out-of-contract year")

    with gzip.open(
        mapping_package / "per_issue_receipts.json.gz", "rt", encoding="utf-8"
    ) as handle:
        receipts = json.load(handle)
    receipt_summary = pd.read_parquet(mapping_package / "receipt_summary.parquet")
    if len(receipts) != mapped[["issue_code", "policy"]].drop_duplicates().shape[0]:
        raise ContractError("per-issue mapping receipt key set is incomplete")
    if not receipt_summary["target_rows_seen"].eq(
        receipt_summary["target_rows_excluded"]
    ).all():
        raise ContractError("target issue was not fully excluded from mapping fit")
    if not (
        pd.to_datetime(receipt_summary["maximum_training_label_timestamp"], utc=True)
        < pd.to_datetime(receipt_summary["cutoff_ts"], utc=True)
    ).all():
        raise ContractError("mapping receipt admits a label at or after cutoff")

    settlement = pd.read_parquet(n7_package / "action_receipts.parquet")[
        [
            "issue",
            "issue_year",
            "issue_anchor_ts",
            "match_idx",
            "fixture_decision_ts",
            "result_code",
            "winning_sp",
            "settlement_available",
            "settlement_quality",
        ]
    ].copy()
    settlement["issue"] = settlement["issue"].astype(str)
    settlement["result_code"] = settlement["result_code"].astype(str)
    settlement["issue_anchor_ts"] = pd.to_datetime(
        settlement["issue_anchor_ts"], utc=True
    )
    settlement["fixture_decision_ts"] = pd.to_datetime(
        settlement["fixture_decision_ts"], utc=True
    )
    if settlement.duplicated(["issue", "match_idx"]).any():
        raise ContractError("corrected N7 settlement fixture keys are not unique")

    bound_receipts: list[dict[str, Any]] = []
    for item in receipts:
        receipt = item["receipt"]
        admitted = str(receipt.get("admitted_history_sha256", ""))
        if len(admitted) != 64:
            raise ContractError("mapping receipt lacks admitted-history identity")
        bound_receipts.append(
            {
                **item,
                "n7_cache_identity": stable_json_hash(
                    {
                        "upstream_cache_key": receipt["cache_key"],
                        "admitted_history_sha256": admitted,
                        "cutoff_identity": receipt["cutoff_identity"],
                        "policy": receipt["weight_receipt"]["policy"],
                        "source_hashes": receipt["source_hashes"],
                        "implementation_closure": receipt["implementation"][
                            "closure_sha256"
                        ],
                    }
                ),
            }
        )
    if len({item["n7_cache_identity"] for item in bound_receipts}) != len(
        bound_receipts
    ):
        raise ContractError("cutoff/admitted-history cache identities collide")
    return {
        "mapped": mapped,
        "receipts": bound_receipts,
        "receipt_summary": receipt_summary,
        "settlement": settlement,
    }


def _mapped_long(mapped: pd.DataFrame) -> pd.DataFrame:
    anchor = mapped.groupby(["policy", "issue_code"], observed=True)[
        "fixture_decision_ts"
    ].transform("min")
    parts: list[pd.DataFrame] = []
    for outcome in OUTCOMES:
        parts.append(
            pd.DataFrame(
                {
                    "policy": mapped["policy"].astype(str),
                    "issue": mapped["issue_code"].astype(str),
                    "issue_year": mapped["issue_year"].astype(int),
                    "issue_anchor_ts": anchor,
                    "match_idx": mapped["match_idx"].astype(int),
                    "outcome": outcome,
                    "q_eu": mapped[f"q_effective_{outcome}"].astype(float),
                    "q_line": mapped[f"q_line_{outcome}"].astype(float),
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def _action_surface(mapped: pd.DataFrame, settlement: pd.DataFrame) -> pd.DataFrame:
    long = _mapped_long(mapped)
    parts: list[pd.DataFrame] = []
    for policy in POLICIES:
        actions = prepare_match_actions(long[long["policy"].eq(policy)]).assign(
            policy=policy
        )
        parts.append(actions)
    actions = pd.concat(parts, ignore_index=True)
    actions = actions.merge(
        settlement,
        on=["issue", "issue_year", "issue_anchor_ts", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    actions["settlement_available"] = (
        actions["settlement_available"].fillna(False).astype(bool)
    )
    actions["winning_sp"] = pd.to_numeric(actions["winning_sp"], errors="coerce")
    return actions.sort_values(
        ["issue_anchor_ts", "issue", "policy", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def _primary_support(selected: pd.DataFrame) -> dict[int, tuple[str, ...]]:
    ranked = selected.sort_values(
        ["support_pressure", "match_idx"],
        ascending=[False, True],
        kind="stable",
    )
    activated = set(ranked.head(3)["match_idx"].astype(int))
    return {
        int(row.match_idx): tuple(
            str(row.qeu_support)
            if int(row.match_idx) in activated
            else str(row.baseline_support)
        )
        for row in selected.itertuples()
    }


def _secondary_support(
    selected: pd.DataFrame, primary: dict[int, tuple[str, ...]]
) -> tuple[dict[int, tuple[str, ...]], list[int], list[int], pd.DataFrame]:
    _, _, scores = _rank_shape_pair(selected, primary)
    contraction, expansion = _maximal_assignment(scores)
    result = dict(primary)
    c1 = contraction[0]
    result[c1] = (
        str(scores.loc[scores["match_idx"].eq(c1), "retained_outcome"].iloc[0]),
    )
    for match_idx in expansion[:3]:
        result[match_idx] = OUTCOMES
    if len(set([c1, *expansion[:3]])) != 4:
        raise ContractError("C1E3 contraction/expansion assignment is not disjoint")
    return result, [c1], expansion[:3], scores


def _ticket_rows(
    *,
    issue: str,
    year: int,
    policy: str,
    arm: str,
    fixture_order: list[int],
    support_map: dict[int, tuple[str, ...]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    combinations = list(
        itertools.product(*(support_map[match_idx] for match_idx in fixture_order))
    )
    codes = ["|".join(values) for values in combinations]
    expected = PRIMARY_TICKETS if arm == PRIMARY_ARM else SECONDARY_TICKETS
    if len(codes) != expected or len(set(codes)) != expected:
        raise ContractError(f"{arm} ticket space is not complete Cartesian")
    if arm == PRIMARY_ARM:
        units_by_code = {code: FUNDED_UNITS // PRIMARY_TICKETS for code in codes}
    else:
        units_by_code = _ticket_units(issue, "C1E3", codes)
    if sum(units_by_code.values()) != FUNDED_UNITS:
        raise ContractError("ticket units do not reconcile to 512")
    rows = []
    for ordinal, (values, code) in enumerate(zip(combinations, codes, strict=True)):
        identity = "|".join(
            f"{match_idx}:{outcome}"
            for match_idx, outcome in zip(fixture_order, values, strict=True)
        )
        rows.append(
            {
                "issue": issue,
                "issue_year": year,
                "policy": policy,
                "support_arm": arm,
                "ticket_ordinal": ordinal,
                "ticket_code": code,
                "ticket_identity": identity,
                "units": units_by_code[code],
                "stake_cny": units_by_code[code] * STAKE_PER_UNIT_CNY,
            }
        )
    return rows, units_by_code


def construct_downstream(
    mapped: pd.DataFrame, settlement: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    actions = _action_surface(mapped, settlement)
    selected_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    for (issue, year, anchor, policy), group in actions.groupby(
        ["issue", "issue_year", "issue_anchor_ts", "policy"],
        sort=True,
        observed=True,
    ):
        selected = (
            group.sort_values(
                ["retained_mass", "match_idx"],
                ascending=[False, True],
                kind="stable",
            )
            .head(N_LEGS)
            .sort_values("match_idx", kind="stable")
            .copy()
        )
        if len(selected) != N_LEGS:
            raise ContractError(f"issue {issue}/{policy} lacks seven fixtures")
        fixture_order = selected["match_idx"].astype(int).tolist()
        primary = _primary_support(selected)
        secondary, contraction, expansion, scores = _secondary_support(
            selected, primary
        )
        for arm, support_map in (
            (PRIMARY_ARM, primary),
            (SECONDARY_ARM, secondary),
        ):
            rows, units_by_code = _ticket_rows(
                issue=str(issue),
                year=int(year),
                policy=str(policy),
                arm=arm,
                fixture_order=fixture_order,
                support_map=support_map,
            )
            ticket_rows.extend(rows)
            trusted = bool(selected["settlement_available"].astype(bool).all())
            realized = selected["result_code"].fillna("").astype(str).tolist()
            winning_code = "|".join(realized)
            winning_units = int(units_by_code.get(winning_code, 0))
            hit = bool(trusted and winning_units > 0)
            gross = (
                float(
                    winning_units
                    * STAKE_PER_UNIT_CNY
                    * PAYOUT_FACTOR
                    * selected["winning_sp"].astype(float).prod()
                )
                if hit
                else 0.0
            )
            decision_rows.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "issue_anchor_ts": anchor,
                    "policy": str(policy),
                    "support_arm": arm,
                    "selected_match_ids": "|".join(map(str, fixture_order)),
                    "support_json": json.dumps(
                        {str(key): "".join(value) for key, value in support_map.items()},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "contraction_match_ids": "|".join(map(str, contraction))
                    if arm == SECONDARY_ARM
                    else "",
                    "expansion_match_ids": "|".join(map(str, expansion))
                    if arm == SECONDARY_ARM
                    else "",
                    "ticket_count": len(rows),
                    "funded_units": FUNDED_UNITS,
                    "planned_stake_cny": ISSUE_STAKE_CNY,
                    "settlement_complete": trusted,
                }
            )
            bundle_rows.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "issue_anchor_ts": anchor,
                    "policy": str(policy),
                    "support_arm": arm,
                    "ticket_count": len(rows),
                    "funded_units": FUNDED_UNITS,
                    "stake_cny": ISSUE_STAKE_CNY,
                    "gross_cny": gross if trusted else np.nan,
                    "pnl_cny": gross - ISSUE_STAKE_CNY if trusted else np.nan,
                    "ticket_hit": hit,
                    "issue_profitable": bool(trusted and gross > ISSUE_STAKE_CNY),
                    "winning_ticket_units": winning_units,
                    "settlement_complete": trusted,
                }
            )
            for row in selected.itertuples():
                active = "".join(support_map[int(row.match_idx)])
                selected_rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(year),
                        "issue_anchor_ts": anchor,
                        "policy": str(policy),
                        "support_arm": arm,
                        "match_idx": int(row.match_idx),
                        "baseline_support": str(row.baseline_support),
                        "r3_support": "".join(primary[int(row.match_idx)]),
                        "active_support": active,
                        "retained_mass": float(row.retained_mass),
                        "support_pressure": float(row.support_pressure),
                    }
                )
                realized_in_support = str(row.result_code) in active
                attribution_rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(year),
                        "policy": str(policy),
                        "support_arm": arm,
                        "match_idx": int(row.match_idx),
                        "active_support": active,
                        "contraction_order": int(
                            1
                            if arm == SECONDARY_ARM
                            and int(row.match_idx) == contraction[0]
                            else 0
                        ),
                        "expansion_order": int(
                            expansion.index(int(row.match_idx)) + 1
                            if arm == SECONDARY_ARM
                            and int(row.match_idx) in expansion
                            else 0
                        ),
                        "result_code": str(row.result_code),
                        "winning_sp": float(row.winning_sp),
                        "settlement_available": bool(row.settlement_available),
                        "realized_in_support": bool(realized_in_support),
                    }
                )
    decisions = pd.DataFrame(decision_rows)
    tickets = pd.DataFrame(ticket_rows)
    bundles = pd.DataFrame(bundle_rows)
    native_complete = bundles["settlement_complete"].astype(bool)
    bundles["native_included"] = native_complete
    arm_counts = (
        bundles[native_complete]
        .groupby(["issue", "support_arm"], observed=True)["policy"]
        .nunique()
    )
    arm_common = {
        (str(issue), str(arm))
        for (issue, arm), count in arm_counts.items()
        if int(count) == len(POLICIES)
    }
    global_counts = (
        bundles[native_complete].groupby("issue", observed=True).size()
    )
    global_common = {
        str(issue)
        for issue, count in global_counts.items()
        if int(count) == len(POLICIES) * len(SUPPORT_ARMS)
    }
    bundles["arm_exact_common"] = [
        (str(row.issue), str(row.support_arm)) in arm_common
        for row in bundles.itertuples()
    ]
    bundles["global_exact_common"] = bundles["issue"].astype(str).isin(global_common)
    coverage = decisions[
        [
            "issue",
            "issue_year",
            "policy",
            "support_arm",
            "selected_match_ids",
            "settlement_complete",
        ]
    ].merge(
        bundles[
            [
                "issue",
                "policy",
                "support_arm",
                "arm_exact_common",
                "global_exact_common",
            ]
        ],
        on=["issue", "policy", "support_arm"],
        validate="one_to_one",
    )
    coverage["inclusion_status"] = np.select(
        [
            coverage["global_exact_common"],
            coverage["arm_exact_common"],
            coverage["settlement_complete"],
        ],
        [
            "INCLUDED_GLOBAL_EXACT_COMMON",
            "INCLUDED_ARM_EXACT_COMMON",
            "NATIVE_ONLY_OTHER_POLICY_INCOMPLETE",
        ],
        default="EXCLUDED_SELECTED_FIXTURE_UNTRUSTED",
    )
    return {
        "action_surface": actions,
        "selected_actions": pd.DataFrame(selected_rows),
        "decisions": decisions,
        "tickets": tickets,
        "bundles": bundles,
        "attribution": pd.DataFrame(attribution_rows),
        "coverage": coverage,
    }


def _run_lengths(mask: np.ndarray) -> np.ndarray:
    values: list[int] = []
    current = 0
    for item in mask:
        if bool(item):
            current += 1
        elif current:
            values.append(current)
            current = 0
    if current:
        values.append(current)
    return np.asarray(values, dtype=int)


def _path_metrics(pnl: np.ndarray, gross: np.ndarray) -> dict[str, float | int]:
    equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
    peaks = np.maximum.accumulate(equity)
    drawdown = (peaks - equity) / np.maximum(peaks, 1e-12)
    peak_indices = np.flatnonzero(drawdown <= 1e-15)
    open_underwater = (
        int(len(pnl) - int(peak_indices[-1])) if drawdown[-1] > 1e-15 else 0
    )
    runs = _run_lengths(pnl <= 0)
    payouts = gross[gross > 0]
    shares = payouts / payouts.sum() if payouts.sum() > 0 else np.array([], float)
    return {
        "max_drawdown_fraction": float(drawdown.max()),
        "longest_profitable_issue_losing_run": int(runs.max()) if len(runs) else 0,
        "losing_run_count": int(len(runs)),
        "median_losing_run": float(np.quantile(runs, 0.50)) if len(runs) else 0.0,
        "p75_losing_run": float(np.quantile(runs, 0.75)) if len(runs) else 0.0,
        "p90_losing_run": float(np.quantile(runs, 0.90)) if len(runs) else 0.0,
        "open_underwater_issues": open_underwater,
        "largest_payout_share": float(shares.max()) if len(shares) else 0.0,
        "payout_hhi": float(np.square(shares).sum()) if len(shares) else 0.0,
    }


def _circular_block_indices(
    length: int, draws: int, rng: np.random.Generator
) -> np.ndarray:
    block = min(MOVING_BLOCK_LENGTH, length)
    blocks_needed = math.ceil(length / block)
    starts = rng.integers(0, length, size=(draws, blocks_needed))
    offsets = np.arange(block)
    indices = (starts[:, :, None] + offsets[None, None, :]) % length
    return indices.reshape(draws, -1)[:, :length]


def _calibration(
    mapped: pd.DataFrame, settlement: pd.DataFrame
) -> pd.DataFrame:
    labeled = mapped.merge(
        settlement[["issue", "match_idx", "result_code", "settlement_available"]],
        left_on=["issue_code", "match_idx"],
        right_on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    labeled = labeled[
        labeled["settlement_available"].fillna(False)
        & labeled["result_code"].isin(OUTCOMES)
    ].copy()
    rows: list[dict[str, Any]] = []
    scopes = [(str(year), labeled[labeled["issue_year"].eq(year)]) for year in YEARS]
    scopes.append(("ALL", labeled))
    for scope, scoped in scopes:
        for policy in POLICIES:
            group = scoped[scoped["policy"].eq(policy)]
            probability = group[
                [f"q_effective_{outcome}" for outcome in OUTCOMES]
            ].to_numpy(float)
            position = np.asarray(
                [OUTCOME_ORDER[str(value)] for value in group["result_code"]]
            )
            observed = np.zeros_like(probability)
            observed[np.arange(len(group)), position] = 1.0
            rows.append(
                {
                    "scope": scope,
                    "policy": policy,
                    "rows": int(len(group)),
                    "issues": int(group["issue_code"].nunique()),
                    "multiclass_log_loss": float(
                        -np.log(
                            np.clip(
                                probability[np.arange(len(group)), position],
                                1e-15,
                                1.0,
                            )
                        ).mean()
                    ),
                    "multiclass_brier": float(
                        np.mean(np.square(probability - observed).sum(axis=1))
                    ),
                }
            )
    return pd.DataFrame(rows)


def _performance_and_risk(
    bundles: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    performance_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    for denominator, mask_column in (
        ("NATIVE", "native_included"),
        ("EXACT_COMMON", "arm_exact_common"),
    ):
        eligible = bundles[bundles[mask_column]].copy()
        scopes = [
            (str(year), eligible[eligible["issue_year"].eq(year)]) for year in YEARS
        ]
        scopes.append(("ALL", eligible))
        for scope, scoped in scopes:
            for (arm, policy), group in scoped.groupby(
                ["support_arm", "policy"], sort=True, observed=True
            ):
                group = group.sort_values(
                    ["issue_anchor_ts", "issue"], kind="stable"
                ).reset_index(drop=True)
                pnl = group["pnl_cny"].to_numpy(float)
                gross = group["gross_cny"].to_numpy(float)
                largest = int(np.argmax(gross)) if len(gross) else 0
                performance_rows.append(
                    {
                        "denominator": denominator,
                        "scope": scope,
                        "support_arm": arm,
                        "policy": policy,
                        "issues": int(len(group)),
                        "stake_cny": float(group["stake_cny"].sum()),
                        "gross_cny": float(gross.sum()),
                        "pnl_cny": float(pnl.sum()),
                        "ending_capital_cny": float(
                            STARTING_CAPITAL_CNY + pnl.sum()
                        ),
                        "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                        "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                        "issue_hit_rate": float(group["ticket_hit"].mean()),
                        "issue_profitable_rate": float(
                            group["issue_profitable"].mean()
                        ),
                        "conditional_gross_on_hit_cny": float(
                            group.loc[group["ticket_hit"], "gross_cny"].mean()
                        )
                        if group["ticket_hit"].any()
                        else 0.0,
                        "ex_largest_pnl_cny": float(
                            pnl.sum() - pnl[largest]
                        )
                        if len(pnl)
                        else 0.0,
                    }
                )
                metrics = _path_metrics(pnl, gross)
                risk_rows.append(
                    {
                        "denominator": denominator,
                        "scope": scope,
                        "support_arm": arm,
                        "policy": policy,
                        **metrics,
                    }
                )
                capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
                peaks = np.maximum.accumulate(
                    np.r_[STARTING_CAPITAL_CNY, capital]
                )[1:]
                for order, (row, value, peak) in enumerate(
                    zip(group.itertuples(), capital, peaks, strict=True), start=1
                ):
                    path_rows.append(
                        {
                            "denominator": denominator,
                            "scope": scope,
                            "support_arm": arm,
                            "policy": policy,
                            "issue_order": order,
                            "issue": str(row.issue),
                            "issue_year": int(row.issue_year),
                            "pnl_cny": float(row.pnl_cny),
                            "capital_cny": float(value),
                            "drawdown_fraction": float(
                                (peak - value) / max(peak, 1e-12)
                            ),
                        }
                    )
    return {
        "performance": pd.DataFrame(performance_rows),
        "risk": pd.DataFrame(risk_rows),
        "paths": pd.DataFrame(path_rows),
    }


def _matched_contrasts(bundles: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    common = bundles[bundles["arm_exact_common"]].copy()
    scopes = [(str(year), common[common["issue_year"].eq(year)]) for year in YEARS]
    scopes.append(("ALL", common))
    for scope, scoped in scopes:
        for arm in SUPPORT_ARMS:
            arm_rows = scoped[scoped["support_arm"].eq(arm)]
            wide = arm_rows.pivot(
                index=["issue_anchor_ts", "issue"],
                columns="policy",
                values="pnl_cny",
            ).sort_index(kind="stable")
            if set(wide.columns) != set(POLICIES) or wide.isna().any().any():
                raise ContractError("matched policy matrix is not exact common")
            equal = wide["EXPANDING_EQUAL"].to_numpy(float)
            for policy in POLICIES:
                delta = wide[policy].to_numpy(float) - equal
                largest = int(np.argmax(np.abs(delta))) if len(delta) else 0
                indices = _circular_block_indices(len(delta), BOOTSTRAP_DRAWS, rng)
                samples = delta[indices].sum(axis=1)
                rows.append(
                    {
                        "scope": scope,
                        "support_arm": arm,
                        "policy": policy,
                        "issues": int(len(delta)),
                        "matched_lift_vs_equal_cny": float(delta.sum()),
                        "matched_ex_largest_abs_delta_cny": float(
                            delta.sum() - delta[largest]
                        ),
                        "largest_abs_paired_delta_issue": str(wide.index[largest][1]),
                        "largest_abs_paired_delta_cny": float(abs(delta[largest])),
                        "block_length": min(MOVING_BLOCK_LENGTH, len(delta)),
                        "bootstrap_draws": BOOTSTRAP_DRAWS,
                        "moving_block_p05_lift_cny": float(
                            np.quantile(samples, 0.05)
                        ),
                        "moving_block_median_lift_cny": float(
                            np.quantile(samples, 0.50)
                        ),
                        "moving_block_p95_lift_cny": float(
                            np.quantile(samples, 0.95)
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _turnover(
    selected: pd.DataFrame, tickets: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for arm in SUPPORT_ARMS:
        arm_actions = selected[selected["support_arm"].eq(arm)]
        arm_tickets = tickets[tickets["support_arm"].eq(arm)]
        for issue in sorted(arm_actions["issue"].unique()):
            base_a = arm_actions[
                arm_actions["issue"].eq(issue)
                & arm_actions["policy"].eq("EXPANDING_EQUAL")
            ]
            base_t = set(
                arm_tickets[
                    arm_tickets["issue"].eq(issue)
                    & arm_tickets["policy"].eq("EXPANDING_EQUAL")
                ]["ticket_identity"]
            )
            base_fixtures = set(base_a["match_idx"].astype(int))
            base_support = base_a.set_index("match_idx")["active_support"].to_dict()
            for policy in POLICIES:
                current_a = arm_actions[
                    arm_actions["issue"].eq(issue)
                    & arm_actions["policy"].eq(policy)
                ]
                current_t = set(
                    arm_tickets[
                        arm_tickets["issue"].eq(issue)
                        & arm_tickets["policy"].eq(policy)
                    ]["ticket_identity"]
                )
                fixtures = set(current_a["match_idx"].astype(int))
                support = current_a.set_index("match_idx")["active_support"].to_dict()
                common = fixtures & base_fixtures
                rows.append(
                    {
                        "issue": str(issue),
                        "issue_year": int(current_a["issue_year"].iloc[0]),
                        "support_arm": arm,
                        "policy": policy,
                        "fixture_set_exact_vs_equal": fixtures == base_fixtures,
                        "fixture_jaccard_vs_equal": len(common)
                        / len(fixtures | base_fixtures),
                        "common_fixture_support_changes_vs_equal": sum(
                            support[key] != base_support[key] for key in common
                        ),
                        "ticket_jaccard_vs_equal": len(current_t & base_t)
                        / len(current_t | base_t),
                    }
                )
    return pd.DataFrame(rows)


def _interaction_contrasts(bundles: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    common = bundles[bundles["global_exact_common"]].copy()
    scopes = [(str(year), common[common["issue_year"].eq(year)]) for year in YEARS]
    scopes.append(("ALL", common))
    for scope, scoped in scopes:
        wide = scoped.pivot(
            index=["issue_anchor_ts", "issue"],
            columns=["support_arm", "policy"],
            values="pnl_cny",
        ).sort_index(kind="stable")
        for policy in POLICIES:
            shape_delta = (
                wide[(SECONDARY_ARM, policy)].to_numpy(float)
                - wide[(PRIMARY_ARM, policy)].to_numpy(float)
            )
            equal_shape_delta = (
                wide[(SECONDARY_ARM, "EXPANDING_EQUAL")].to_numpy(float)
                - wide[(PRIMARY_ARM, "EXPANDING_EQUAL")].to_numpy(float)
            )
            interaction = shape_delta - equal_shape_delta
            rows.append(
                {
                    "scope": scope,
                    "policy": policy,
                    "issues": int(len(interaction)),
                    "c1e3_minus_r3_cny": float(shape_delta.sum()),
                    "temporal_x_shape_interaction_cny": float(interaction.sum()),
                }
            )
    return pd.DataFrame(rows)


def evaluate(
    mapped: pd.DataFrame,
    settlement: pd.DataFrame,
    constructed: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    path = _performance_and_risk(constructed["bundles"])
    return {
        "calibration": _calibration(mapped, settlement),
        **path,
        "contrasts": _matched_contrasts(constructed["bundles"]),
        "turnover": _turnover(
            constructed["selected_actions"], constructed["tickets"]
        ),
        "interaction": _interaction_contrasts(constructed["bundles"]),
    }


def _decision(
    performance: pd.DataFrame,
    risk: pd.DataFrame,
    contrasts: pd.DataFrame,
    calibration: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    perf = performance[
        performance["denominator"].eq("EXACT_COMMON")
        & performance["support_arm"].eq(PRIMARY_ARM)
    ].copy()
    risk_primary = risk[
        risk["denominator"].eq("EXACT_COMMON")
        & risk["support_arm"].eq(PRIMARY_ARM)
    ].copy()
    all_perf = perf[perf["scope"].eq("ALL")].set_index("policy")
    all_risk = risk_primary[risk_primary["scope"].eq("ALL")].set_index("policy")
    all_contrast = contrasts[
        contrasts["scope"].eq("ALL")
        & contrasts["support_arm"].eq(PRIMARY_ARM)
    ].set_index("policy")
    annual_perf = perf[perf["scope"].isin(map(str, YEARS))]
    annual_contrast = contrasts[
        contrasts["scope"].isin(map(str, YEARS))
        & contrasts["support_arm"].eq(PRIMARY_ARM)
    ]
    calibration_all = calibration[calibration["scope"].eq("ALL")].set_index("policy")
    equal_risk = all_risk.loc["EXPANDING_EQUAL"]
    rows: list[dict[str, Any]] = []
    for policy in POLICIES[1:]:
        yearly_perf = annual_perf[annual_perf["policy"].eq(policy)]
        yearly_lift = annual_contrast[annual_contrast["policy"].eq(policy)]
        predicates = {
            "standalone_positive": bool(all_perf.loc[policy, "pnl_cny"] > 0),
            "standalone_ex_largest_positive": bool(
                all_perf.loc[policy, "ex_largest_pnl_cny"] > 0
            ),
            "matched_lift_positive": bool(
                all_contrast.loc[policy, "matched_lift_vs_equal_cny"] > 0
            ),
            "matched_ex_largest_positive": bool(
                all_contrast.loc[
                    policy, "matched_ex_largest_abs_delta_cny"
                ]
                > 0
            ),
            "annual_non_reversal": bool(
                yearly_perf["pnl_cny"].gt(0).all()
                and yearly_lift["matched_lift_vs_equal_cny"].ge(0).all()
            ),
            "max_drawdown_nonworse": bool(
                all_risk.loc[policy, "max_drawdown_fraction"]
                <= equal_risk["max_drawdown_fraction"]
            ),
            "losing_run_nonworse": bool(
                all_risk.loc[policy, "longest_profitable_issue_losing_run"]
                <= equal_risk["longest_profitable_issue_losing_run"]
            ),
            "underwater_nonworse": bool(
                all_risk.loc[policy, "open_underwater_issues"]
                <= equal_risk["open_underwater_issues"]
            ),
            "moving_block_p05_nonnegative": bool(
                all_contrast.loc[policy, "moving_block_p05_lift_cny"] >= 0
            ),
            "calibration_logloss_nonworse": bool(
                calibration_all.loc[policy, "multiclass_log_loss"]
                <= calibration_all.loc[
                    "EXPANDING_EQUAL", "multiclass_log_loss"
                ]
            ),
            "calibration_brier_nonworse": bool(
                calibration_all.loc[policy, "multiclass_brier"]
                <= calibration_all.loc["EXPANDING_EQUAL", "multiclass_brier"]
            ),
        }
        economic_keys = [
            "standalone_positive",
            "standalone_ex_largest_positive",
            "matched_lift_positive",
            "matched_ex_largest_positive",
            "annual_non_reversal",
            "max_drawdown_nonworse",
            "losing_run_nonworse",
            "underwater_nonworse",
            "moving_block_p05_nonnegative",
        ]
        rows.append(
            {
                "policy": policy,
                **predicates,
                "mechanism_gate_pass": bool(
                    all(predicates[key] for key in economic_keys)
                ),
            }
        )
    gates = pd.DataFrame(rows)
    passing = gates.loc[gates["mechanism_gate_pass"], "policy"].tolist()
    verdict = (
        "N7_RECENCY_HISTORICAL_MECHANISM_SIGNAL_NO_PROMOTION"
        if passing
        else "NO_N7_RECENCY_INCREMENT"
    )
    if verdict not in ALLOWED_VERDICTS:
        raise ContractError("decision vocabulary drifted")
    decision = {
        "contract": CONTRACT_ID,
        "verdict": verdict,
        "primary_arm": PRIMARY_ARM,
        "secondary_arm": SECONDARY_ARM,
        "passing_primary_temporal_policies": passing,
        "exposed_historical_only": True,
        "strategy_promoted": False,
        "prospective_authorized": False,
        "preserved_issues": [210, 218],
    }
    return gates, decision


def scientific_frames(
    repo_root: Path, data_root: Path | None = None, *, verify_upstreams: bool = True
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    data_root = locate_data_root(repo_root, data_root)
    upstream_hashes = (
        _verify_upstreams(repo_root, data_root)
        if verify_upstreams
        else {
            "cutoff_walkforward_manifest_sha256": sha256_file(
                repo_root / UPSTREAM_MAPPING_PACKAGE / "MANIFEST.json"
            ),
            "n7_chronology_manifest_sha256": sha256_file(
                repo_root / UPSTREAM_N7_PACKAGE / "MANIFEST.json"
            ),
            "n7_support_transfer_manifest_sha256": sha256_file(
                repo_root / UPSTREAM_SHAPE_PACKAGE / "MANIFEST.json"
            ),
        }
    )
    inputs = _load_inputs(repo_root)
    constructed = construct_downstream(inputs["mapped"], inputs["settlement"])
    evaluated = evaluate(inputs["mapped"], inputs["settlement"], constructed)
    gates, decision = _decision(
        evaluated["performance"],
        evaluated["risk"],
        evaluated["contrasts"],
        evaluated["calibration"],
    )
    source = {
        "contract": CONTRACT_ID,
        "upstream_hashes": upstream_hashes,
        "mapping_rows": int(len(inputs["mapped"])),
        "mapping_issues": int(inputs["mapped"]["issue_code"].nunique()),
        "mapping_policies": list(POLICIES),
        "settlement_frame_sha256": stable_frame_sha(inputs["settlement"]),
        "years": list(YEARS),
        "evaluation_role": "EXPOSED_HISTORICAL_MECHANISM_EVIDENCE",
        "primary_downstream": (
            "CORRECTED_N7_R3_CONTROL;128_COMPLETE_TICKETS;"
            "CNY1024;0.65_TICKET_LEVEL_ONCE"
        ),
        "secondary_downstream": (
            "CORRECTED_N7_C1E3_SECONDARY;216_COMPLETE_TICKETS;"
            "CNY1024;0.65_TICKET_LEVEL_ONCE"
        ),
        "temporal_policies": {
            "EXPANDING_EQUAL": {},
            "EXPANDING_EXPONENTIAL": {
                "half_life_days": EXPONENTIAL_HALF_LIFE_DAYS
            },
            "RECENT_STATE_BLEND": {
                "long_history_mass": 1.0 - RECENT_BLEND,
                "recent_mass": RECENT_BLEND,
                "recent_available_issues": RECENT_WINDOW_ISSUES,
            },
        },
        "shared_temporal_client": "src.cutoff_walkforward.fitting",
        "prospective_authorized": False,
    }
    return {
        "source": source,
        "mapped": inputs["mapped"],
        "receipts": inputs["receipts"],
        "receipt_summary": inputs["receipt_summary"],
        **constructed,
        **evaluated,
        "gates": gates,
        "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "per_issue_receipts.json.gz": "receipts",
    "receipt_summary.parquet": "receipt_summary",
    "mapped_probabilities.parquet": "mapped",
    "action_surface.parquet": "action_surface",
    "selected_actions.parquet": "selected_actions",
    "decisions.parquet": "decisions",
    "tickets.parquet": "tickets",
    "issue_bundles.parquet": "bundles",
    "support_attribution.parquet": "attribution",
    "settlement_coverage.csv": "coverage",
    "calibration.csv": "calibration",
    "performance.csv": "performance",
    "risk_diagnostics.csv": "risk",
    "capital_paths.parquet": "paths",
    "matched_contrasts.csv": "contrasts",
    "action_turnover.csv": "turnover",
    "support_shape_interaction.csv": "interaction",
    "decision_gates.csv": "gates",
    "decision.json": "decision",
}


def _write(path: Path, value: Any) -> None:
    if isinstance(value, pd.DataFrame):
        if path.suffix == ".parquet":
            value.to_parquet(path, index=False)
        else:
            value.to_csv(path, index=False, float_format="%.17g")
    elif path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
    else:
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(value) for value in frame.columns]
    values = [columns, ["---"] * len(columns)]
    values.extend(
        [[str(value) for value in row] for row in frame.itertuples(index=False, name=None)]
    )
    return "\n".join("| " + " | ".join(row) + " |" for row in values)


def _build_deliveries(repo_root: Path, frames: dict[str, Any]) -> None:
    report = repo_root / REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    primary = frames["performance"][
        frames["performance"]["denominator"].eq("EXACT_COMMON")
        & frames["performance"]["support_arm"].eq(PRIMARY_ARM)
    ].merge(
        frames["risk"][
            frames["risk"]["denominator"].eq("EXACT_COMMON")
            & frames["risk"]["support_arm"].eq(PRIMARY_ARM)
        ],
        on=["denominator", "scope", "support_arm", "policy"],
    ).merge(
        frames["contrasts"][frames["contrasts"]["support_arm"].eq(PRIMARY_ARM)],
        on=["scope", "support_arm", "policy"],
    )
    primary = primary.rename(columns={"issues_x": "issues"}).drop(
        columns=["issues_y"], errors="ignore"
    )
    secondary = frames["performance"][
        frames["performance"]["denominator"].eq("EXACT_COMMON")
        & frames["performance"]["support_arm"].eq(SECONDARY_ARM)
    ].merge(
        frames["risk"][
            frames["risk"]["denominator"].eq("EXACT_COMMON")
            & frames["risk"]["support_arm"].eq(SECONDARY_ARM)
        ],
        on=["denominator", "scope", "support_arm", "policy"],
    ).merge(
        frames["contrasts"][frames["contrasts"]["support_arm"].eq(SECONDARY_ARM)],
        on=["scope", "support_arm", "policy"],
    )
    secondary = secondary.rename(columns={"issues_x": "issues"}).drop(
        columns=["issues_y"], errors="ignore"
    )
    native = frames["performance"][
        frames["performance"]["denominator"].eq("NATIVE")
    ].merge(
        frames["risk"][frames["risk"]["denominator"].eq("NATIVE")],
        on=["denominator", "scope", "support_arm", "policy"],
    )
    columns = [
        "scope",
        "policy",
        "issues",
        "pnl_cny",
        "ending_capital_cny",
        "capital_return",
        "issue_hit_rate",
        "issue_profitable_rate",
        "ex_largest_pnl_cny",
        "matched_lift_vs_equal_cny",
        "matched_ex_largest_abs_delta_cny",
        "moving_block_p05_lift_cny",
        "max_drawdown_fraction",
        "longest_profitable_issue_losing_run",
        "open_underwater_issues",
        "largest_payout_share",
        "payout_hhi",
    ]
    native_columns = [
        "support_arm",
        "scope",
        "policy",
        "issues",
        "pnl_cny",
        "ending_capital_cny",
        "capital_return",
        "issue_hit_rate",
        "issue_profitable_rate",
        "ex_largest_pnl_cny",
        "max_drawdown_fraction",
        "longest_profitable_issue_losing_run",
        "open_underwater_issues",
        "largest_payout_share",
        "payout_hhi",
    ]
    turnover = (
        frames["turnover"]
        .groupby(["support_arm", "policy"], as_index=False)
        .agg(
            fixture_exact_rate=("fixture_set_exact_vs_equal", "mean"),
            mean_support_changes=("common_fixture_support_changes_vs_equal", "mean"),
            mean_ticket_jaccard=("ticket_jaccard_vs_equal", "mean"),
        )
    )
    coverage = (
        frames["coverage"]
        .groupby(["support_arm", "policy", "inclusion_status"], as_index=False)["issue"]
        .nunique()
        .rename(columns={"issue": "issues"})
    )
    report.write_text(
        "# Issue #392 — corrected N7 cutoff walk-forward temporal policy\n\n"
        f"Contract: `{CONTRACT_ID}`\n\n"
        f"Decision: `{frames['decision']['verdict']}`. 2022–2024 are exposed "
        "historical mechanism evidence; no promotion is authorized.\n\n"
        "## Frozen comparison\n\n"
        "Only mapping-history weighting changes. Corrected chronology, N=7, fixed "
        "R3 support semantics, ticket design, CNY1,024 budget, settlement and the "
        "ticket-level-once 0.65 factor remain fixed.\n\n"
        "## Mapping calibration\n\n"
        + _markdown_table(frames["calibration"])
        + "\n\n## Native denominators\n\n"
        + _markdown_table(native[native_columns])
        + "\n\n## Primary R3 CONTROL — exact-common\n\n"
        + _markdown_table(primary[columns])
        + "\n\n## Secondary C1E3 — exact-common\n\n"
        + _markdown_table(secondary[columns])
        + "\n\n## Temporal-policy x support-shape interaction\n\n"
        + _markdown_table(frames["interaction"])
        + "\n\n## Turnover versus expanding equal\n\n"
        + _markdown_table(turnover)
        + "\n\n## Settlement coverage\n\n"
        + _markdown_table(coverage)
        + "\n\n## Decision gates\n\n"
        + _markdown_table(frames["gates"])
        + "\n\n## Adversarial interpretation\n\n"
        "- The primary result rejects an increment from these two frozen recency "
        "policies on this corrected N7 R3 interface. It does not establish that "
        "all forms of temporal adaptation are useless.\n"
        "- EXPANDING_EQUAL has positive pooled point PnL, but its ex-largest PnL "
        "is negative, 2022 is negative, and payout concentration is high. It is "
        "therefore a historical control, not newly established deployable Edge.\n"
        "- Both recency policies worsen aggregate calibration, primary matched "
        "economics, tail-removed evidence and path risk. Their large action "
        "turnover indicates aggressive ranking changes rather than a stable "
        "increment.\n"
        "- The smoother C1E3 figures are secondary exposed diagnostics. They may "
        "motivate a future pre-frozen stability mechanism, but cannot select a "
        "temporal policy or support shape here.\n"
        + "\n\n## Evidence boundary\n\n"
        "The shared #382/#388 cutoff client and the source-bound #383 probability "
        "surface are reused. Every receipt binds cutoff, actual admitted-history "
        "hash, source hashes, transitive implementation closure, weights, ESS and "
        "policy identity. C1E3 is secondary and cannot be selected from this joint "
        "surface. #210 and #218 are unchanged.\n\n"
        "## Reproduction\n\n```bash\n"
        "PYTHONPATH=. python scripts/run_n7_cutoff_walkforward.py --data-root /path/to/data --force\n"
        "PYTHONPATH=. python scripts/verify_n7_cutoff_walkforward.py --data-root /path/to/data\n"
        "```\n",
        encoding="utf-8",
    )

    figure = repo_root / FIGURE_PATH
    figure.parent.mkdir(parents=True, exist_ok=True)
    paths = frames["paths"]
    paths = paths[
        paths["denominator"].eq("EXACT_COMMON")
        & paths["scope"].eq("ALL")
        & paths["support_arm"].eq(PRIMARY_ARM)
    ]
    fig, axis = plt.subplots(figsize=(11, 5.5))
    for policy in POLICIES:
        group = paths[paths["policy"].eq(policy)].sort_values("issue_order")
        axis.plot(group["issue_order"], group["capital_cny"], label=policy)
    axis.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8, alpha=0.5)
    axis.set(title="Issue #392 corrected N7 R3 temporal-policy capital paths", xlabel="Exact-common issue order", ylabel="Capital (CNY)")
    axis.legend()
    axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(figure, dpi=160)
    plt.close(fig)

    notebook_path = repo_root / NOTEBOOK_PATH
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                f"# Issue #392 N7 cutoff walk-forward\n\nContract: `{CONTRACT_ID}`"
            ),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\nimport json, pandas as pd\n"
                f"OUT=Path.cwd()/{RESULT_PACKAGE!r}\n"
                "decision=json.loads((OUT/'decision.json').read_text())\ndecision"
            ),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'calibration.csv')"),
            nbformat.v4.new_code_cell(
                "performance=pd.read_csv(OUT/'performance.csv')\n"
                "risk=pd.read_csv(OUT/'risk_diagnostics.csv')\n"
                "contrasts=pd.read_csv(OUT/'matched_contrasts.csv')\n"
                "performance.merge(risk,on=['denominator','scope','support_arm','policy'])"
                ".merge(contrasts,on=['scope','support_arm','policy'],how='left')"
            ),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'action_turnover.csv').groupby(['support_arm','policy']).mean(numeric_only=True)"),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'support_shape_interaction.csv')"),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'decision_gates.csv')"),
            nbformat.v4.new_markdown_cell(
                "All outcomes are exposed historical evidence. The notebook does not authorize promotion."
            ),
        ]
    )
    nbformat.write(notebook, notebook_path)
    NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    ).execute()
    nbformat.write(notebook, notebook_path)


def _manifest(repo_root: Path, target: Path) -> dict[str, Any]:
    return {
        "contract": CONTRACT_ID,
        "files": {
            name: {
                "bytes": (target / name).stat().st_size,
                "sha256": sha256_file(target / name),
            }
            for name in sorted(PACKAGE_FILES)
        },
        "implementation": implementation_closure(
            repo_root,
            ("src.n7_cutoff_walkforward.pipeline",),
            distributions=("numpy", "pandas", "matplotlib", "nbformat", "nbclient"),
        ),
        "deliveries": {
            path: sha256_file(repo_root / path)
            for path in (REPORT_PATH, NOTEBOOK_PATH, FIGURE_PATH)
        },
    }


def build_package(
    repo_root: Path,
    target: Path | None = None,
    data_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    target = (target or repo_root / RESULT_PACKAGE).resolve()
    frames = scientific_frames(repo_root, data_root, verify_upstreams=True)

    def populate(staging: Path) -> None:
        for name, key in PACKAGE_FILES.items():
            _write(staging / name, frames[key])

    atomic_publish_directory(target, populate, force=force)
    _build_deliveries(repo_root, frames)
    manifest = _manifest(repo_root, target)
    temporary = target / ".MANIFEST.json.tmp"
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, target / "MANIFEST.json")
    return frames["decision"]


def _read(path: Path) -> Any:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return _read_json(path)


def _assert_frame(actual: pd.DataFrame, expected: pd.DataFrame, name: str) -> None:
    actual = actual.copy()
    expected = expected.copy()
    for column in expected.columns:
        if pd.api.types.is_string_dtype(expected[column].dtype):
            actual[column] = actual[column].astype(str)
            expected[column] = expected[column].astype(str)
    try:
        pd.testing.assert_frame_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            rtol=0,
            atol=1e-10,
        )
    except AssertionError as error:
        raise ContractError(f"scientific frame differs: {name}") from error


def _verify_semantics(stored: dict[str, Any]) -> None:
    receipts = stored["receipts"]
    summaries = stored["receipt_summary"]
    receipt_index = {
        (str(item["issue"]), str(item["policy"])): item for item in receipts
    }
    expected_keys = set(
        map(tuple, summaries[["issue", "policy"]].astype(str).to_numpy())
    )
    if set(receipt_index) != expected_keys:
        raise ContractError("mapping receipt/summary key sets differ")
    for key, item in receipt_index.items():
        receipt = item["receipt"]
        verify_implementation_closure(
            Path(__file__).resolve().parents[2], receipt["implementation"]
        )
        expected_cache = stable_json_hash(
            {
                "upstream_cache_key": receipt["cache_key"],
                "admitted_history_sha256": receipt["admitted_history_sha256"],
                "cutoff_identity": receipt["cutoff_identity"],
                "policy": receipt["weight_receipt"]["policy"],
                "source_hashes": receipt["source_hashes"],
                "implementation_closure": receipt["implementation"][
                    "closure_sha256"
                ],
            }
        )
        if item["n7_cache_identity"] != expected_cache:
            raise ContractError(f"admitted-history cache binding differs: {key}")
        if not (
            pd.Timestamp(receipt["maximum_training_label_timestamp"])
            < pd.Timestamp(receipt["cutoff_ts"])
        ):
            raise ContractError(f"receipt crosses cutoff: {key}")
        if receipt["target_rows_seen"] != receipt["target_rows_excluded"]:
            raise ContractError(f"target identity reached learning context: {key}")

    decisions = stored["decisions"]
    tickets = stored["tickets"]
    bundles = stored["bundles"]
    if decisions.duplicated(["issue", "policy", "support_arm"]).any():
        raise ContractError("decision key set is duplicated")
    required_decisions = (
        decisions["issue"].nunique() * len(POLICIES) * len(SUPPORT_ARMS)
    )
    if len(decisions) != required_decisions:
        raise ContractError("decision key set is incomplete")
    expected_ticket_counts = {
        PRIMARY_ARM: PRIMARY_TICKETS,
        SECONDARY_ARM: SECONDARY_TICKETS,
    }
    for arm, expected in expected_ticket_counts.items():
        arm_tickets = tickets[tickets["support_arm"].eq(arm)]
        if not (
            arm_tickets.groupby(["issue", "policy"], observed=True)
            .size()
            .eq(expected)
            .all()
        ):
            raise ContractError(f"{arm} ticket count differs")
    if not (
        tickets.groupby(["issue", "policy", "support_arm"], observed=True)[
            "units"
        ]
        .sum()
        .eq(FUNDED_UNITS)
        .all()
    ):
        raise ContractError("ticket units do not sum to 512")
    if not (
        tickets.groupby(["issue", "policy", "support_arm"], observed=True)[
            "stake_cny"
        ]
        .sum()
        .eq(ISSUE_STAKE_CNY)
        .all()
    ):
        raise ContractError("ticket stake does not sum to CNY1,024")
    settled = bundles[bundles["settlement_complete"]].copy()
    if not np.allclose(
        settled["pnl_cny"],
        settled["gross_cny"] - settled["stake_cny"],
        rtol=0,
        atol=1e-10,
    ):
        raise ContractError("bundle PnL identity differs")
    attribution = stored["attribution"]
    for row in settled.itertuples():
        legs = attribution[
            attribution["issue"].astype(str).eq(str(row.issue))
            & attribution["policy"].eq(row.policy)
            & attribution["support_arm"].eq(row.support_arm)
        ].sort_values("match_idx", kind="stable")
        hit = bool(legs["realized_in_support"].all())
        winning_code = "|".join(legs["result_code"].astype(str))
        winning = tickets[
            tickets["issue"].astype(str).eq(str(row.issue))
            & tickets["policy"].eq(row.policy)
            & tickets["support_arm"].eq(row.support_arm)
            & tickets["ticket_code"].eq(winning_code)
        ]
        units = int(winning["units"].iloc[0]) if len(winning) else 0
        gross = (
            units
            * STAKE_PER_UNIT_CNY
            * PAYOUT_FACTOR
            * legs["winning_sp"].astype(float).prod()
            if hit
            else 0.0
        )
        if not math.isclose(float(row.gross_cny), float(gross), rel_tol=0, abs_tol=1e-9):
            raise ContractError(
                f"ticket-level-once payout reconciliation differs: {row.issue}/{row.policy}/{row.support_arm}"
            )


def verify_package(
    repo_root: Path,
    target: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, bool]:
    repo_root = repo_root.resolve()
    target = (target or repo_root / RESULT_PACKAGE).resolve()
    manifest = _read_json(target / "MANIFEST.json")
    if set(manifest.get("files", {})) != set(PACKAGE_FILES):
        raise ContractError("manifest exact file set differs")
    for name, receipt in manifest["files"].items():
        path = target / name
        if (
            not path.is_file()
            or path.stat().st_size != receipt["bytes"]
            or sha256_file(path) != receipt["sha256"]
        ):
            raise ContractError(f"manifest file differs: {name}")
    if manifest != _manifest(repo_root, target):
        raise ContractError("manifest implementation/delivery receipt differs")
    verify_implementation_closure(repo_root, manifest["implementation"])
    stored = {key: _read(target / name) for name, key in PACKAGE_FILES.items()}
    _verify_semantics(stored)
    expected = scientific_frames(repo_root, data_root, verify_upstreams=True)
    for name, key in PACKAGE_FILES.items():
        value = expected[key]
        if isinstance(value, pd.DataFrame):
            _assert_frame(stored[key], value, name)
        elif stored[key] != value:
            raise ContractError(f"receipt/decision differs: {name}")
    if stored["decision"]["verdict"] not in ALLOWED_VERDICTS:
        raise ContractError("decision vocabulary differs")
    if stored["decision"]["strategy_promoted"]:
        raise ContractError("exposed historical result attempted promotion")
    return {
        "manifest_and_deliveries": True,
        "upstream_source_bound_verifiers": True,
        "shared_cutoff_receipts": True,
        "admitted_history_cache_binding": True,
        "target_exclusion_and_strict_availability": True,
        "corrected_n7_r3_semantics": True,
        "c1e3_secondary_semantics": True,
        "complete_cartesian_and_budget": True,
        "settlement_and_payout_reconciliation": True,
        "native_and_exact_common_denominators": True,
        "moving_block_and_path_risk": True,
        "decision_gate_and_evidence_boundary": True,
    }
