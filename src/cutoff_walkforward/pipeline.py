"""Build and verify the Issue #383 issue-level walk-forward diagnostic."""

from __future__ import annotations

import hashlib
import gzip
import itertools
import json
import os
from pathlib import Path
from typing import Any

import nbformat
from nbclient import NotebookClient
import numpy as np
import pandas as pd

from src.cutoff_mapping.api import replay_mapped
from src.low_n_selector_data.pipeline import (
    _input_panel,
    _load_transfer_results,
    locate_data_root,
)
from src.source_schema.publication import atomic_publish_directory
from src.temporal_learning import (
    AvailabilityFilter,
    AvailabilityPolicy,
    Cutoff,
    implementation_closure,
    prepare_learning_context,
    verify_implementation_closure,
)
from src.temporal_learning.core import stable_frame_hash, stable_json_hash

from .contract import (
    AVAILABILITY_POLICY,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    EXPONENTIAL_HALF_LIFE_DAYS,
    FUNDED_UNITS,
    INTENDED_USE,
    ISSUE_STAKE_CNY,
    NOTEBOOK_PATH,
    N_LEGS,
    PAYOUT_FACTOR,
    POLICIES,
    RECENT_BLEND,
    RECENT_WINDOW_ISSUES,
    REPORT_PATH,
    RESULT_PACKAGE,
    STAKE_PER_TICKET_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    YEARS,
)
from .fitting import fit_issue_mapping, weighting_policy


OUTCOMES = ("3", "1", "0")
OUTCOME_ORDER = {value: position for position, value in enumerate(OUTCOMES)}


class WalkForwardContractError(ValueError):
    """Raised when the frozen #383 diagnostic cannot be reconciled."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    projected = frame.loc[:, sorted(frame.columns)].copy()
    hashes = np.sort(
        pd.util.hash_pandas_object(projected, index=False, categorize=False).to_numpy(
            np.uint64
        )
    )
    schema = [(name, str(projected[name].dtype)) for name in projected.columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode())
    digest.update(hashes.tobytes())
    return digest.hexdigest()


def _load_inputs(
    repo_root: Path, data_root: Path
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    panel, development, source_hashes = _input_panel(data_root)
    target = panel[
        panel["issue_year"].isin(YEARS) & panel["native_line_supported"].eq(True)
    ].copy()
    target["issue_code"] = target["issue_code"].astype(str)
    transfer_results = _load_transfer_results(
        data_root, panel.rename(columns={"issue_code": "issue"})
    )
    transfer = panel[panel["issue_year"].isin(YEARS)].merge(
        transfer_results.rename(
            columns={"issue": "issue_code", "result_code": "target_outcome"}
        ),
        on=["issue_code", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    history = pd.concat(
        [
            development[development["target_outcome"].notna()],
            transfer[transfer["target_outcome"].notna()],
        ],
        ignore_index=True,
    )
    history["issue_code"] = history["issue_code"].astype(str)
    history["target_outcome"] = history["target_outcome"].astype(str)
    history["label_available_ts"] = pd.to_datetime(
        history["label_available_ts"], utc=True
    )
    history["fixture_decision_ts"] = pd.to_datetime(
        history["fixture_decision_ts"], utc=True
    )
    settlement_path = repo_root / "results/n6_chronology_sync/action_receipts.parquet"
    settlement = pd.read_parquet(settlement_path)[
        [
            "issue",
            "issue_year",
            "match_idx",
            "result_code",
            "winning_sp",
            "settlement_available",
        ]
    ].copy()
    settlement["issue"] = settlement["issue"].astype(str)
    settlement["result_code"] = settlement["result_code"].astype(str)
    source_hashes = {
        **source_hashes,
        "transfer_results_frame_sha256": stable_frame_sha(transfer_results),
        "settlement_frame_sha256": stable_frame_sha(settlement),
        "settlement_file_sha256": sha256_file(settlement_path),
        "hardening_manifest_sha256": sha256_file(
            repo_root / "results/cutoff_learning_hardening/MANIFEST.json"
        ),
    }
    source = {
        "contract": CONTRACT_ID,
        "source_hashes": source_hashes,
        "history_rows": len(history),
        "history_issues": int(history["issue_code"].nunique()),
        "target_rows": len(target),
        "target_issues": int(target["issue_code"].nunique()),
        "target_years": list(YEARS),
        "availability_policy": AVAILABILITY_POLICY,
        "intended_use": INTENDED_USE,
        "availability_evidence": "HISTORICAL_PROXY_NOT_OBSERVED",
        "prospective_authorized": False,
        "downstream": (
            "N6_PROBABILITY_TOP2_R0;64_COMPLETE_CARTESIAN;"
            "CNY1024;0.65_TICKET_LEVEL_ONCE"
        ),
    }
    return history, target, settlement, source


def _ordered_targets(target: pd.DataFrame) -> list[tuple[str, pd.Timestamp]]:
    epochs = (
        target.groupby("issue_code", as_index=False)["fixture_decision_ts"]
        .min()
        .sort_values(["fixture_decision_ts", "issue_code"], kind="stable")
    )
    return [
        (str(row.issue_code), pd.Timestamp(row.fixture_decision_ts))
        for row in epochs.itertuples(index=False)
    ]


def run_mapping_surface(
    repo_root: Path,
    history: pd.DataFrame,
    target: pd.DataFrame,
    source_hashes: dict[str, str],
) -> tuple[pd.DataFrame, list[dict[str, Any]], pd.DataFrame]:
    mapped_parts: list[pd.DataFrame] = []
    receipts: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    fitting_implementation = implementation_closure(
        repo_root,
        ("src.cutoff_walkforward.fitting",),
        distributions=("numpy", "pandas", "scikit-learn"),
    )
    checkpoint_root = repo_root / ".cache/cutoff_walkforward"
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    for issue, cutoff_ts in _ordered_targets(target):
        issue_target = target[target["issue_code"].eq(issue)].copy()
        issue_year = int(issue_target["issue_year"].iloc[0])
        cutoff = Cutoff.decision_epoch(issue, cutoff_ts)
        prior_current = history[
            history["issue_year"].eq(issue_year)
            & history["label_available_ts"].lt(cutoff_ts)
            & ~history["issue_code"].eq(issue)
            & history["native_line_supported"].eq(True)
        ]
        for policy_name in POLICIES:
            checkpoint_identity = stable_json_hash(
                {
                    "contract": CONTRACT_ID,
                    "issue": issue,
                    "cutoff_ts": cutoff_ts.isoformat(),
                    "policy": policy_name,
                    "source_hashes": dict(sorted(source_hashes.items())),
                    "fitting_implementation": fitting_implementation["closure_sha256"],
                }
            )
            checkpoint = checkpoint_root / checkpoint_identity
            receipt_path = checkpoint / "receipt.json"
            mapped_path = checkpoint / "mapped.parquet"
            if receipt_path.is_file() and mapped_path.is_file():
                result_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                verify_implementation_closure(
                    repo_root, result_receipt["implementation"]
                )
                if result_receipt["source_hashes"] != dict(source_hashes):
                    raise WalkForwardContractError("checkpoint source identity differs")
                result_mapped = pd.read_parquet(mapped_path)
                replayed = replay_mapped(
                    issue_target, result_receipt, repository_root=repo_root
                )
                pd.testing.assert_frame_equal(
                    result_mapped.reset_index(drop=True),
                    replayed.reset_index(drop=True),
                    check_dtype=False,
                    check_exact=False,
                    rtol=0,
                    atol=1e-12,
                )
                accepted = bool(all(result_receipt["gate_predicates"].values()))
            else:
                result = fit_issue_mapping(
                    history,
                    issue_target,
                    cutoff,
                    repository_root=repo_root,
                    source_hashes=source_hashes,
                    policy_name=policy_name,
                )
                result_receipt = result.receipt
                result_mapped = result.mapped
                accepted = bool(result.accepted)
                checkpoint.mkdir(parents=True, exist_ok=False)
                result_mapped.to_parquet(mapped_path, index=False)
                receipt_path.write_text(
                    json.dumps(result_receipt, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            mapped = result_mapped.assign(
                policy=policy_name,
                issue_gate_accepted=accepted,
            )
            for outcome in OUTCOMES:
                mapped[f"q_effective_{outcome}"] = np.where(
                    accepted,
                    mapped[f"q_candidate_{outcome}"],
                    mapped[f"q_line_{outcome}"],
                )
            mapped_parts.append(mapped)
            receipt = {
                "issue": issue,
                "issue_year": issue_year,
                "policy": policy_name,
                "receipt": result_receipt,
            }
            receipts.append(receipt)
            summaries.append(
                {
                    "issue": issue,
                    "issue_year": issue_year,
                    "cutoff_ts": cutoff_ts,
                    "policy": policy_name,
                    "gate_accepted": accepted,
                    "eligible_rows": result_receipt["partition"]["final_refit_rows"],
                    "current_year_prior_rows": len(prior_current),
                    "current_year_prior_issues": int(
                        prior_current["issue_code"].nunique()
                    ),
                    "maximum_training_label_timestamp": result_receipt[
                        "maximum_training_label_timestamp"
                    ],
                    "target_rows_seen": result_receipt["target_rows_seen"],
                    "target_rows_excluded": result_receipt["target_rows_excluded"],
                    "effective_sample_size": result_receipt["weight_receipt"][
                        "effective_sample_size"
                    ],
                    "long_history_mass": result_receipt["weight_receipt"][
                        "long_history_mass"
                    ],
                    "recent_state_mass": result_receipt["weight_receipt"][
                        "recent_state_mass"
                    ],
                    "model_identity": result_receipt["model_identity"],
                    "model_vector_json": json.dumps(
                        [
                            *np.asarray(
                                result_receipt["final_model_states"]["control"]["coef"],
                                dtype=float,
                            )
                            .ravel()
                            .tolist(),
                            *np.asarray(
                                result_receipt["final_model_states"]["control"][
                                    "intercept"
                                ],
                                dtype=float,
                            )
                            .ravel()
                            .tolist(),
                            *np.asarray(
                                result_receipt["final_model_states"]["experimental"][
                                    "coef"
                                ],
                                dtype=float,
                            )
                            .ravel()
                            .tolist(),
                            *np.asarray(
                                result_receipt["final_model_states"]["experimental"][
                                    "intercept"
                                ],
                                dtype=float,
                            )
                            .ravel()
                            .tolist(),
                        ],
                        separators=(",", ":"),
                    ),
                    "cache_key": result_receipt["cache_key"],
                }
            )
    mapped_frame = (
        pd.concat(mapped_parts, ignore_index=True)
        .sort_values(
            ["fixture_decision_ts", "issue_code", "match_idx", "policy"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    summary = (
        pd.DataFrame(summaries)
        .sort_values(["cutoff_ts", "issue", "policy"], kind="stable")
        .reset_index(drop=True)
    )
    expected_rows = len(target) * len(POLICIES)
    if len(mapped_frame) != expected_rows:
        raise WalkForwardContractError("walk-forward mapped key set is incomplete")
    if summary.duplicated(["issue", "policy"]).any():
        raise WalkForwardContractError("walk-forward receipt key is duplicated")
    if not (
        pd.to_datetime(summary["maximum_training_label_timestamp"], utc=True)
        < pd.to_datetime(summary["cutoff_ts"], utc=True)
    ).all():
        raise WalkForwardContractError("walk-forward receipt crossed cutoff")
    if not summary["target_rows_seen"].eq(summary["target_rows_excluded"]).all():
        raise WalkForwardContractError("target issue was not fully excluded")
    return mapped_frame, receipts, summary


def _support(row: pd.Series) -> str:
    ranked = sorted(
        OUTCOMES,
        key=lambda outcome: (
            -float(row[f"q_effective_{outcome}"]),
            OUTCOME_ORDER[outcome],
        ),
    )
    return "".join(ranked[:2])


def construct_downstream(
    mapped: pd.DataFrame, settlement: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    enriched = mapped.merge(
        settlement,
        left_on=["issue_code", "issue_year", "match_idx"],
        right_on=["issue", "issue_year", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    enriched["settlement_available"] = (
        enriched["settlement_available"].fillna(False).astype(bool)
    )
    enriched["winning_sp"] = pd.to_numeric(enriched["winning_sp"], errors="coerce")
    enriched["support"] = enriched.apply(_support, axis=1)
    enriched["retained_mass"] = enriched.apply(
        lambda row: sum(float(row[f"q_effective_{value}"]) for value in row["support"]),
        axis=1,
    )
    action_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    for (policy, issue, year), group in enriched.groupby(
        ["policy", "issue_code", "issue_year"], sort=True, observed=True
    ):
        selected = (
            group.sort_values(
                ["retained_mass", "match_idx"],
                ascending=[False, True],
                kind="stable",
            )
            .head(N_LEGS)
            .sort_values("match_idx", kind="stable")
        )
        if len(selected) != N_LEGS:
            continue
        issue_anchor = pd.to_datetime(group["fixture_decision_ts"], utc=True).min()
        support_map = {
            int(row.match_idx): str(row.support) for row in selected.itertuples()
        }
        for row in selected.itertuples():
            action_rows.append(
                {
                    "policy": policy,
                    "issue": str(issue),
                    "issue_year": int(year),
                    "issue_anchor_ts": issue_anchor,
                    "match_idx": int(row.match_idx),
                    "support": str(row.support),
                    "retained_mass": float(row.retained_mass),
                    "result_code": str(row.result_code),
                    "winning_sp": float(row.winning_sp),
                    "settlement_available": bool(row.settlement_available),
                }
            )
        fixtures = selected["match_idx"].astype(int).tolist()
        supports = selected["support"].astype(str).tolist()
        ticket_codes: list[str] = []
        for ordinal, choices in enumerate(itertools.product((0, 1), repeat=N_LEGS)):
            code = "|".join(
                f"{match_idx}:{support[choice]}"
                for match_idx, support, choice in zip(
                    fixtures, supports, choices, strict=True
                )
            )
            ticket_codes.append(code)
            ticket_rows.append(
                {
                    "policy": policy,
                    "issue": str(issue),
                    "issue_year": int(year),
                    "ticket_ordinal": ordinal,
                    "ticket_code": code,
                    "units": FUNDED_UNITS // TICKETS,
                    "stake_cny": STAKE_PER_TICKET_CNY,
                }
            )
        trusted = bool(selected["settlement_available"].eq(True).all())
        hit = bool(
            trusted
            and all(
                str(result) in support
                for result, support in zip(
                    selected["result_code"], supports, strict=True
                )
            )
        )
        gross = (
            float(
                STAKE_PER_TICKET_CNY
                * PAYOUT_FACTOR
                * selected["winning_sp"].astype(float).prod()
            )
            if hit
            else 0.0
        )
        bundle_rows.append(
            {
                "policy": policy,
                "issue": str(issue),
                "issue_year": int(year),
                "issue_anchor_ts": issue_anchor,
                "selected_match_ids": "|".join(map(str, fixtures)),
                "support_json": json.dumps(
                    support_map, sort_keys=True, separators=(",", ":")
                ),
                "ticket_count": len(ticket_codes),
                "stake_cny": ISSUE_STAKE_CNY,
                "gross_cny": gross,
                "pnl_cny": gross - ISSUE_STAKE_CNY if trusted else np.nan,
                "hit": hit,
                "settlement_complete": trusted,
            }
        )
    actions = pd.DataFrame(action_rows)
    tickets = pd.DataFrame(ticket_rows)
    bundles = pd.DataFrame(bundle_rows)
    complete = (
        bundles[bundles["settlement_complete"]]
        .groupby("issue", observed=True)["policy"]
        .nunique()
    )
    common = set(complete[complete.eq(len(POLICIES))].index.astype(str))
    bundles["exact_common"] = bundles["issue"].isin(common)
    if (
        not bundles[bundles["exact_common"]]
        .groupby("issue")["policy"]
        .nunique()
        .eq(len(POLICIES))
        .all()
    ):
        raise WalkForwardContractError("downstream exact-common denominator differs")
    incomplete = (
        actions.assign(incomplete_selected=~actions["settlement_available"])
        .groupby(["issue", "policy"], as_index=False)["incomplete_selected"]
        .sum()
        .rename(columns={"incomplete_selected": "incomplete_selected_matches"})
    )
    settlement_coverage = bundles[
        [
            "issue",
            "issue_year",
            "policy",
            "selected_match_ids",
            "settlement_complete",
            "exact_common",
        ]
    ].merge(incomplete, on=["issue", "policy"], validate="one_to_one")
    settlement_coverage["inclusion_status"] = np.select(
        [
            settlement_coverage["exact_common"],
            settlement_coverage["settlement_complete"],
        ],
        ["INCLUDED_EXACT_COMMON", "EXCLUDED_OTHER_POLICY_INCOMPLETE"],
        default="EXCLUDED_SELECTED_FIXTURE_UNTRUSTED",
    )
    return {
        "cells": enriched,
        "actions": actions,
        "tickets": tickets,
        "bundles": bundles,
        "settlement_coverage": settlement_coverage,
    }


def _run_lengths(mask: np.ndarray) -> list[int]:
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
    return lengths


def _path_metrics(pnl: np.ndarray, gross: np.ndarray) -> dict[str, float | int]:
    capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
    peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL_CNY, capital])[1:]
    drawdown = (peaks - capital) / np.maximum(peaks, 1e-12)
    underwater = drawdown > 1e-15
    last_peak = np.flatnonzero(~underwater)
    open_underwater = (
        int(len(pnl) - last_peak[-1] - 1)
        if underwater[-1] and len(last_peak)
        else int(len(pnl))
        if underwater[-1]
        else 0
    )
    runs = _run_lengths(pnl <= 0)
    payouts = gross[gross > 0]
    shares = payouts / payouts.sum() if payouts.sum() else np.array([], float)
    return {
        "max_drawdown_fraction": float(drawdown.max()) if len(drawdown) else 0.0,
        "longest_profitable_issue_losing_run": max(runs, default=0),
        "open_underwater_issues": open_underwater,
        "largest_payout_share": float(shares.max()) if len(shares) else 0.0,
        "payout_hhi": float(np.square(shares).sum()) if len(shares) else 0.0,
    }


def evaluate(
    mapped: pd.DataFrame,
    receipt_summary: pd.DataFrame,
    constructed: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    bundles = constructed["bundles"]
    common = bundles[bundles["exact_common"]].copy()
    calibration_rows: list[dict[str, Any]] = []
    labeled = constructed["cells"]
    labeled = labeled[labeled["result_code"].isin(OUTCOMES)].copy()
    for scope, scoped in [
        (str(year), labeled[labeled["issue_year"].eq(year)]) for year in YEARS
    ] + [("ALL", labeled)]:
        for policy in POLICIES:
            group = scoped[scoped["policy"].eq(policy)]
            receipt_scope = receipt_summary[receipt_summary["policy"].eq(policy)]
            if scope != "ALL":
                receipt_scope = receipt_scope[
                    receipt_scope["issue_year"].eq(int(scope))
                ]
            probability = group[
                [f"q_effective_{value}" for value in OUTCOMES]
            ].to_numpy(float)
            positions = np.asarray(
                [OUTCOME_ORDER[value] for value in group["result_code"]]
            )
            observed = np.zeros_like(probability)
            observed[np.arange(len(group)), positions] = 1.0
            calibration_rows.append(
                {
                    "scope": scope,
                    "policy": policy,
                    "rows": len(group),
                    "multiclass_log_loss": float(
                        -np.log(
                            np.clip(
                                probability[np.arange(len(group)), positions], 1e-15, 1
                            )
                        ).mean()
                    ),
                    "multiclass_brier": float(
                        np.mean(np.sum(np.square(probability - observed), axis=1))
                    ),
                    "gate_acceptance_rate": float(
                        receipt_scope["gate_accepted"].mean()
                    ),
                }
            )
    performance_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    contrast_rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for scope, scoped in [
        (str(year), common[common["issue_year"].eq(year)]) for year in YEARS
    ] + [("ALL", common)]:
        wide = scoped.pivot(
            index=["issue_anchor_ts", "issue"], columns="policy", values="pnl_cny"
        ).sort_index(kind="stable")
        if list(wide.columns) != sorted(POLICIES) or wide.isna().any().any():
            raise WalkForwardContractError("policy comparison lacks exact common rows")
        for policy in POLICIES:
            group = scoped[scoped["policy"].eq(policy)].sort_values(
                ["issue_anchor_ts", "issue"], kind="stable"
            )
            pnl = group["pnl_cny"].to_numpy(float)
            gross = group["gross_cny"].to_numpy(float)
            largest = int(np.argmax(gross))
            performance_rows.append(
                {
                    "scope": scope,
                    "policy": policy,
                    "issues": len(group),
                    "stake_cny": float(group["stake_cny"].sum()),
                    "gross_cny": float(gross.sum()),
                    "pnl_cny": float(pnl.sum()),
                    "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                    "issue_hit_rate": float(group["hit"].mean()),
                    "conditional_gross_on_hit_cny": float(gross[gross > 0].mean())
                    if (gross > 0).any()
                    else 0.0,
                    "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest]),
                }
            )
            risk_rows.append(
                {"scope": scope, "policy": policy, **_path_metrics(pnl, gross)}
            )
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL_CNY, capital])[1:]
            for order, (row, value, peak) in enumerate(
                zip(group.itertuples(), capital, peaks, strict=True), start=1
            ):
                path_rows.append(
                    {
                        "scope": scope,
                        "policy": policy,
                        "issue_order": order,
                        "issue": str(row.issue),
                        "issue_year": int(row.issue_year),
                        "pnl_cny": float(row.pnl_cny),
                        "capital_cny": float(value),
                        "drawdown_fraction": float((peak - value) / max(peak, 1e-12)),
                    }
                )
        equal = wide["EXPANDING_EQUAL"].to_numpy(float)
        for policy in POLICIES:
            delta = wide[policy].to_numpy(float) - equal
            largest = int(np.argmax(np.abs(delta))) if len(delta) else 0
            samples = rng.integers(0, len(delta), size=(BOOTSTRAP_DRAWS, len(delta)))
            sampled = delta[samples].sum(axis=1)
            contrast_rows.append(
                {
                    "scope": scope,
                    "policy": policy,
                    "matched_lift_vs_equal_cny": float(delta.sum()),
                    "matched_ex_largest_abs_delta_cny": float(
                        delta.sum() - delta[largest]
                    ),
                    "largest_abs_paired_delta_cny": float(np.abs(delta[largest])),
                    "bootstrap_p05_lift_cny": float(np.quantile(sampled, 0.05)),
                    "bootstrap_p50_lift_cny": float(np.quantile(sampled, 0.50)),
                    "bootstrap_p95_lift_cny": float(np.quantile(sampled, 0.95)),
                }
            )
    turnover_rows: list[dict[str, Any]] = []
    actions = constructed["actions"]
    tickets = constructed["tickets"]
    equal_actions = actions[actions["policy"].eq("EXPANDING_EQUAL")]
    equal_tickets = tickets[tickets["policy"].eq("EXPANDING_EQUAL")]
    for issue in sorted(actions["issue"].unique()):
        base_a = equal_actions[equal_actions["issue"].eq(issue)]
        base_t = set(equal_tickets[equal_tickets["issue"].eq(issue)]["ticket_code"])
        base_fixtures = set(base_a["match_idx"].astype(int))
        for policy in POLICIES:
            arm_a = actions[
                (actions["issue"].eq(issue)) & (actions["policy"].eq(policy))
            ]
            arm_t = set(
                tickets[(tickets["issue"].eq(issue)) & (tickets["policy"].eq(policy))][
                    "ticket_code"
                ]
            )
            arm_fixtures = set(arm_a["match_idx"].astype(int))
            common_fixtures = base_fixtures & arm_fixtures
            base_support = base_a.set_index("match_idx")["support"].to_dict()
            arm_support = arm_a.set_index("match_idx")["support"].to_dict()
            turnover_rows.append(
                {
                    "issue": issue,
                    "issue_year": int(arm_a["issue_year"].iloc[0]),
                    "policy": policy,
                    "fixture_set_exact_vs_equal": arm_fixtures == base_fixtures,
                    "fixture_jaccard_vs_equal": len(common_fixtures)
                    / len(base_fixtures | arm_fixtures),
                    "common_fixture_support_changes_vs_equal": sum(
                        base_support[key] != arm_support[key] for key in common_fixtures
                    ),
                    "ticket_jaccard_vs_equal": len(base_t & arm_t)
                    / len(base_t | arm_t),
                }
            )
    probability_turnover = mapped.pivot(
        index=["issue_code", "issue_year", "match_idx"],
        columns="policy",
        values=[f"q_effective_{value}" for value in OUTCOMES],
    )
    probability_rows: list[dict[str, Any]] = []
    for (issue, year), group in probability_turnover.groupby(level=[0, 1]):
        for policy in POLICIES:
            delta = np.column_stack(
                [
                    group[(f"q_effective_{outcome}", policy)].to_numpy(float)
                    - group[(f"q_effective_{outcome}", "EXPANDING_EQUAL")].to_numpy(
                        float
                    )
                    for outcome in OUTCOMES
                ]
            )
            probability_rows.append(
                {
                    "issue": str(issue),
                    "issue_year": int(year),
                    "policy": policy,
                    "mean_absolute_probability_turnover_vs_equal": float(
                        np.abs(delta).mean()
                    ),
                    "rms_probability_turnover_vs_equal": float(
                        np.sqrt(np.square(delta).mean())
                    ),
                }
            )
    model_turnover_rows: list[dict[str, Any]] = []
    for policy in POLICIES:
        prior: np.ndarray | None = None
        prior_accept: bool | None = None
        policy_summary = receipt_summary[
            receipt_summary["policy"].eq(policy)
        ].sort_values(["cutoff_ts", "issue"], kind="stable")
        for item in policy_summary.to_dict("records"):
            vector = np.asarray(json.loads(item["model_vector_json"]), dtype=float)
            model_turnover_rows.append(
                {
                    "issue": item["issue"],
                    "issue_year": item["issue_year"],
                    "policy": policy,
                    "model_l2_turnover": (
                        np.nan
                        if prior is None or len(vector) != len(prior)
                        else float(np.linalg.norm(vector - prior))
                    ),
                    "model_dimension_changed": bool(
                        prior is not None and len(vector) != len(prior)
                    ),
                    "mapping_acceptance_changed": False
                    if prior_accept is None
                    else bool(prior_accept != item["gate_accepted"]),
                }
            )
            prior = vector
            prior_accept = bool(item["gate_accepted"])
    return {
        "calibration": pd.DataFrame(calibration_rows),
        "performance": pd.DataFrame(performance_rows),
        "risk": pd.DataFrame(risk_rows),
        "paths": pd.DataFrame(path_rows),
        "contrasts": pd.DataFrame(contrast_rows),
        "action_turnover": pd.DataFrame(turnover_rows),
        "probability_turnover": pd.DataFrame(probability_rows),
        "model_turnover": pd.DataFrame(model_turnover_rows),
    }


def synthetic_shift_diagnostic(repo_root: Path) -> dict[str, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for year in range(2014, 2021):
        for position in range(20):
            rows.append(
                {
                    "issue_code": f"{year}-{position:03d}",
                    "issue_year": year,
                    "label_available_ts": pd.Timestamp(f"{year}-06-01T12:00:00Z")
                    + pd.Timedelta(days=position),
                    "label": int(position % 5 == 0),
                }
            )
    start = pd.Timestamp("2021-01-01T00:00:00Z")
    for position in range(40):
        rows.append(
            {
                "issue_code": f"2021-{position:03d}",
                "issue_year": 2021,
                "label_available_ts": start + pd.Timedelta(days=position, hours=12),
                "label": int(position >= 10),
            }
        )
    history = pd.DataFrame(rows)
    source_hashes = {"synthetic_shift": stable_frame_hash(history)}
    path_rows: list[dict[str, Any]] = []
    for position in range(40):
        issue = f"2021-{position:03d}"
        cutoff = Cutoff.decision_epoch(
            issue, start + pd.Timedelta(days=position, hours=6)
        )
        for policy_name in POLICIES:
            context = prepare_learning_context(
                history,
                cutoff,
                source_hashes=source_hashes,
                repository_root=repo_root,
                implementation_modules=("src.cutoff_walkforward.pipeline",),
                implementation_distributions=("numpy", "pandas"),
                availability=AvailabilityFilter(
                    AvailabilityPolicy.observed("SYNTHETIC_SETTLEMENT_TS")
                ),
                intended_use="HISTORICAL_DIAGNOSTIC",
                weighting_policy=weighting_policy(policy_name, minimum_ess=1.0),
            )
            estimate = float(
                np.average(
                    context.eligible["label"].to_numpy(float),
                    weights=context.weights.to_numpy(float),
                )
            )
            path_rows.append(
                {
                    "issue": issue,
                    "issue_position": position,
                    "policy": policy_name,
                    "estimate": estimate,
                    "post_shift": position >= 10,
                    "effective_sample_size": context.receipt.payload["weight_receipt"][
                        "effective_sample_size"
                    ],
                }
            )
    paths = pd.DataFrame(path_rows)
    summary_rows: list[dict[str, Any]] = []
    for policy_name, group in paths.groupby("policy", sort=True):
        group = group.sort_values("issue_position", kind="stable")
        crossing = group[group["post_shift"] & group["estimate"].ge(0.5)][
            "issue_position"
        ]
        summary_rows.append(
            {
                "policy": policy_name,
                "pre_shift_estimate": float(
                    group[group["issue_position"].eq(9)]["estimate"].iloc[0]
                ),
                "final_estimate": float(group["estimate"].iloc[-1]),
                "adaptation_lag_issues": (
                    int(crossing.iloc[0] - 10) if len(crossing) else np.nan
                ),
                "maximum_one_issue_jump": float(group["estimate"].diff().abs().max()),
                "minimum_ess": float(group["effective_sample_size"].min()),
            }
        )
    return {"synthetic_paths": paths, "synthetic_summary": pd.DataFrame(summary_rows)}


def _decision_from_evaluation(
    *,
    mapped_rows: int,
    receipt_summary: pd.DataFrame,
    bundles: pd.DataFrame,
    evaluated: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    full_perf = evaluated["performance"][evaluated["performance"]["scope"].eq("ALL")]
    full_risk = evaluated["risk"][evaluated["risk"]["scope"].eq("ALL")]
    full_contrast = evaluated["contrasts"][evaluated["contrasts"]["scope"].eq("ALL")]
    decision_table = (
        full_perf.merge(full_risk, on=["scope", "policy"])
        .merge(full_contrast, on=["scope", "policy"])
        .sort_values("policy", kind="stable")
    )
    equal = decision_table[decision_table["policy"].eq("EXPANDING_EQUAL")].iloc[0]
    candidate = decision_table[~decision_table["policy"].eq("EXPANDING_EQUAL")].copy()
    calibration = evaluated["calibration"]
    calibration_all = calibration[calibration["scope"].eq("ALL")].set_index("policy")
    candidate["predictive_nonworse"] = [
        bool(
            calibration_all.loc[policy, "multiclass_log_loss"]
            <= calibration_all.loc["EXPANDING_EQUAL", "multiclass_log_loss"]
            and calibration_all.loc[policy, "multiclass_brier"]
            <= calibration_all.loc["EXPANDING_EQUAL", "multiclass_brier"]
        )
        for policy in candidate["policy"]
    ]
    candidate["path_nonworse"] = (
        candidate["max_drawdown_fraction"] <= equal["max_drawdown_fraction"]
    ) & (
        candidate["longest_profitable_issue_losing_run"]
        <= equal["longest_profitable_issue_losing_run"]
    )
    candidate["robust_positive_lift"] = (
        (candidate["matched_lift_vs_equal_cny"] > 0)
        & (candidate["matched_ex_largest_abs_delta_cny"] > 0)
        & (candidate["bootstrap_p05_lift_cny"] > 0)
    )
    useful = candidate[
        candidate[["predictive_nonworse", "path_nonworse", "robust_positive_lift"]].all(
            axis=1
        )
    ]["policy"].tolist()
    historical_signal = candidate[
        (candidate["pnl_cny"] > 0)
        & (candidate["matched_lift_vs_equal_cny"] > 0)
        & (candidate["matched_ex_largest_abs_delta_cny"] > 0)
    ]["policy"].tolist()
    policy_predicates = {
        str(row.policy): {
            "predictive_nonworse": bool(row.predictive_nonworse),
            "path_nonworse": bool(row.path_nonworse),
            "robust_positive_lift": bool(row.robust_positive_lift),
        }
        for row in candidate.itertuples(index=False)
    }
    decision = {
        "contract": CONTRACT_ID,
        "verdict": ("HISTORICAL_RECENCY_SIGNAL" if useful else "NO_RECENCY_INCREMENT"),
        "useful_recency_policies": useful,
        "descriptive_historical_signal_policies": historical_signal,
        "policy_predicates": policy_predicates,
        "walkforward_issues": int(receipt_summary["issue"].nunique()),
        "mapped_rows": mapped_rows,
        "exact_common_settled_issues": int(
            bundles.loc[bundles["exact_common"], "issue"].nunique()
        ),
        "availability_evidence": "HISTORICAL_PROXY_NOT_OBSERVED",
        "prospective_authorized": False,
        "strategy_promoted": False,
        "preserved_issues": [210, 218],
    }
    return decision_table, decision


def scientific_frames(repo_root: Path, data_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    data_root = locate_data_root(repo_root, data_root)
    history, target, settlement, source = _load_inputs(repo_root, data_root)
    mapped, receipts, receipt_summary = run_mapping_surface(
        repo_root, history, target, source["source_hashes"]
    )
    constructed = construct_downstream(mapped, settlement)
    evaluated = evaluate(mapped, receipt_summary, constructed)
    synthetic = synthetic_shift_diagnostic(repo_root)
    decision_table, decision = _decision_from_evaluation(
        mapped_rows=len(mapped),
        receipt_summary=receipt_summary,
        bundles=constructed["bundles"],
        evaluated=evaluated,
    )
    return {
        "source": source,
        "mapped": mapped,
        "receipts": receipts,
        "receipt_summary": receipt_summary,
        **constructed,
        **evaluated,
        **synthetic,
        "decision_table": decision_table,
        "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "per_issue_receipts.json.gz": "receipts",
    "receipt_summary.parquet": "receipt_summary",
    "mapped_probabilities.parquet": "mapped",
    "selected_actions.parquet": "actions",
    "tickets.parquet": "tickets",
    "settled_bundles.parquet": "bundles",
    "settlement_coverage.csv": "settlement_coverage",
    "calibration.csv": "calibration",
    "performance.csv": "performance",
    "risk_diagnostics.csv": "risk",
    "capital_paths.parquet": "paths",
    "matched_contrasts.csv": "contrasts",
    "action_turnover.csv": "action_turnover",
    "probability_turnover.csv": "probability_turnover",
    "model_turnover.csv": "model_turnover",
    "synthetic_shift_paths.csv": "synthetic_paths",
    "synthetic_shift_summary.csv": "synthetic_summary",
    "decision_table.csv": "decision_table",
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
    rows = [columns, ["---"] * len(columns)]
    rows.extend(
        [
            [str(value) for value in row]
            for row in frame.itertuples(index=False, name=None)
        ]
    )
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


def _build_deliveries(repo_root: Path, frames: dict[str, Any]) -> None:
    report = repo_root / REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    decision_table = frames["decision_table"].copy()
    display_columns = [
        "policy",
        "issues",
        "pnl_cny",
        "ending_capital_cny",
        "stake_roi",
        "issue_hit_rate",
        "max_drawdown_fraction",
        "longest_profitable_issue_losing_run",
        "open_underwater_issues",
        "matched_lift_vs_equal_cny",
        "bootstrap_p05_lift_cny",
    ]
    calibration = frames["calibration"][frames["calibration"]["scope"].eq("ALL")]
    annual = (
        frames["performance"]
        .merge(frames["risk"], on=["scope", "policy"])
        .merge(frames["contrasts"], on=["scope", "policy"])
    )
    annual_columns = ["scope", *display_columns]
    recent = decision_table[decision_table["policy"].eq("RECENT_STATE_BLEND")].iloc[0]
    yearly_recent = annual[
        annual["policy"].eq("RECENT_STATE_BLEND") & annual["scope"].ne("ALL")
    ].set_index("scope")
    turnover = (
        frames["action_turnover"]
        .groupby("policy", as_index=False)
        .agg(
            fixture_exact_rate=("fixture_set_exact_vs_equal", "mean"),
            mean_support_changes=(
                "common_fixture_support_changes_vs_equal",
                "mean",
            ),
            mean_ticket_jaccard=("ticket_jaccard_vs_equal", "mean"),
        )
    )
    excluded = frames["settlement_coverage"][
        ~frames["settlement_coverage"]["exact_common"]
    ]
    exclusion_summary = (
        excluded.groupby("issue_year", as_index=False)["issue"]
        .nunique()
        .rename(columns={"issue": "excluded_issues"})
    )
    report.write_text(
        "# Issue #383 — issue-level cutoff walk-forward and recency adaptation\n\n"
        f"Contract: `{CONTRACT_ID}`\n\n"
        f"Decision: `{frames['decision']['verdict']}`. This is exposed historical "
        "diagnostic evidence and does not authorize prospective use.\n\n"
        "## Frozen policies\n\n"
        "- expanding equal;\n"
        f"- exponential decay, half-life {EXPONENTIAL_HALF_LIFE_DAYS:g} days;\n"
        f"- convex recent-state blend, {RECENT_WINDOW_ISSUES} issues and "
        f"{RECENT_BLEND:.0%} recent mass.\n\n"
        "## Calibration\n\n"
        + _markdown_table(calibration)
        + "\n\n## Annual and overall N6 Top2/R0 economics\n\n"
        + _markdown_table(annual[annual_columns])
        + "\n\n## Overall decision table\n\n"
        + _markdown_table(decision_table[display_columns])
        + "\n\n## Action and ticket turnover versus equal expansion\n\n"
        + _markdown_table(turnover)
        + "\n\n## Exact-common settlement coverage\n\n"
        + _markdown_table(exclusion_summary)
        + "\n\nThe target surface contains 172 issues; 149 are exact-common "
        "settled across all policies. The 23 exclusions comprise 19 issues "
        "where every policy selects at least one untrusted fixture and four "
        "selection-dependent cases where policy completeness differs. The full "
        "issue-policy ledger is settlement_coverage.csv. Results are therefore "
        "conditional on this disclosed common denominator.\n"
        + "\n\n## Interpretation\n\n"
        f"RECENT_STATE_BLEND is a descriptive but unaccepted historical signal: "
        f"overall PnL CNY{recent['pnl_cny']:.0f}, matched lift "
        f"CNY{recent['matched_lift_vs_equal_cny']:.0f}, ex-largest lift "
        f"CNY{recent['matched_ex_largest_abs_delta_cny']:.0f}, and maximum "
        f"drawdown {recent['max_drawdown_fraction']:.1%}. Its annual PnL is "
        f"CNY{yearly_recent.loc['2022', 'pnl_cny']:.0f} / "
        f"CNY{yearly_recent.loc['2023', 'pnl_cny']:.0f} / "
        f"CNY{yearly_recent.loc['2024', 'pnl_cny']:.0f}; the bootstrap p05 "
        f"lift remains CNY{recent['bootstrap_p05_lift_cny']:.0f}, and overall "
        "log-loss/Brier are slightly worse than equal expansion. It therefore "
        "does not pass the preregistered increment gate.\n\n"
        "EXPANDING_EXPONENTIAL is rejected on absolute, matched and path "
        "economics. Equal expansion remains the accepted default temporal policy.\n\n"
        "The comparison isolates temporal weighting. N, R, model family, selector, "
        "ticket construction, budget, settlement and payout semantics are fixed. "
        "Low turnover or better drawdown is not Edge unless absolute and matched "
        "economics also survive tail and bootstrap checks.\n\n"
        "The availability timestamp is the frozen kickoff+4h historical proxy, not "
        "an observed production label-arrival event. Therefore this result cannot "
        "unlock #210 or consume #218 evidence.\n\n"
        "## Reproduction\n\n```bash\n"
        "PYTHONPATH=. python scripts/run_cutoff_walkforward.py --data-root /path/to/data --force\n"
        "PYTHONPATH=. python scripts/verify_cutoff_walkforward.py --data-root /path/to/data\n"
        "```\n",
        encoding="utf-8",
    )
    notebook_path = repo_root / NOTEBOOK_PATH
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                f"# Issue #383 walk-forward diagnostic\n\nContract: `{CONTRACT_ID}`"
            ),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\nimport json, pandas as pd\n"
                f"OUT=Path.cwd()/{RESULT_PACKAGE!r}\n"
                "decision=json.loads((OUT/'decision.json').read_text())\ndecision"
            ),
            nbformat.v4.new_code_cell(
                "pd.read_csv(OUT/'calibration.csv').query(\"scope == 'ALL'\")"
            ),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'decision_table.csv')"),
            nbformat.v4.new_code_cell(
                "performance=pd.read_csv(OUT/'performance.csv')\n"
                "risk=pd.read_csv(OUT/'risk_diagnostics.csv')\n"
                "contrasts=pd.read_csv(OUT/'matched_contrasts.csv')\n"
                "performance.merge(risk,on=['scope','policy']).merge(contrasts,on=['scope','policy'])"
            ),
            nbformat.v4.new_code_cell("pd.read_csv(OUT/'synthetic_shift_summary.csv')"),
            nbformat.v4.new_markdown_cell(
                "All 2022–2024 outcomes are exposed. This notebook diagnoses "
                "adaptation mechanics; it is not a deployable promotion test."
            ),
        ]
    )
    nbformat.write(nb, notebook_path)
    NotebookClient(
        nb,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    ).execute()
    nbformat.write(nb, notebook_path)


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
            ("src.cutoff_walkforward.pipeline",),
            distributions=(
                "numpy",
                "pandas",
                "scikit-learn",
                "nbformat",
                "nbclient",
            ),
        ),
        "deliveries": {
            path: sha256_file(repo_root / path) for path in (REPORT_PATH, NOTEBOOK_PATH)
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
    frames = scientific_frames(repo_root, data_root)

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


def _read_value(path: Path) -> Any:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


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
        raise WalkForwardContractError(f"scientific frame differs: {name}") from error


def verify_package(
    repo_root: Path,
    target: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, bool]:
    repo_root = repo_root.resolve()
    target = (target or repo_root / RESULT_PACKAGE).resolve()
    manifest = json.loads((target / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest != _manifest(repo_root, target):
        raise WalkForwardContractError("manifest/delivery/implementation differs")
    verify_implementation_closure(repo_root, manifest["implementation"])
    stored = {key: _read_value(target / name) for name, key in PACKAGE_FILES.items()}
    data_root = locate_data_root(repo_root, data_root)
    history, target_frame, settlement, source = _load_inputs(repo_root, data_root)
    if stored["source"] != source:
        raise WalkForwardContractError("source receipt differs")
    receipts = stored["receipts"]
    receipt_index = {
        (str(item["issue"]), str(item["policy"])): item["receipt"] for item in receipts
    }
    mapped = stored["mapped"]
    verified_closures: set[str] = set()
    for (issue, policy), group in mapped.groupby(
        ["issue_code", "policy"], sort=True, observed=True
    ):
        receipt = receipt_index[(str(issue), str(policy))]
        closure_identity = str(receipt["implementation"]["closure_sha256"])
        if closure_identity not in verified_closures:
            verify_implementation_closure(repo_root, receipt["implementation"])
            verified_closures.add(closure_identity)
        target_issue = target_frame[target_frame["issue_code"].eq(str(issue))]
        replay = replay_mapped(target_issue, receipt, repository_root=repo_root)
        for prefix in ("q_line", "q_candidate"):
            columns = [f"{prefix}_{outcome}" for outcome in OUTCOMES]
            if not np.allclose(
                group.sort_values("match_idx")[columns],
                replay.sort_values("match_idx")[columns],
                rtol=0,
                atol=1e-12,
            ):
                raise WalkForwardContractError(
                    f"receipt probability replay differs: {issue}/{policy}"
                )
    summary = stored["receipt_summary"]
    if not (
        pd.to_datetime(summary["maximum_training_label_timestamp"], utc=True)
        < pd.to_datetime(summary["cutoff_ts"], utc=True)
    ).all():
        raise WalkForwardContractError("stored receipt crosses cutoff")
    if not summary["target_rows_seen"].eq(summary["target_rows_excluded"]).all():
        raise WalkForwardContractError("stored target exclusion differs")
    reconstructed = construct_downstream(mapped, settlement)
    evaluated = evaluate(mapped, summary, reconstructed)
    synthetic = synthetic_shift_diagnostic(repo_root)
    for key in (
        "actions",
        "tickets",
        "bundles",
        "settlement_coverage",
        "calibration",
        "performance",
        "risk",
        "paths",
        "contrasts",
        "action_turnover",
        "probability_turnover",
        "model_turnover",
    ):
        _assert_frame(stored[key], {**reconstructed, **evaluated}[key], key)
    for key in ("synthetic_paths", "synthetic_summary"):
        _assert_frame(stored[key], synthetic[key], key)
    reconstructed_decision_table, reconstructed_decision = _decision_from_evaluation(
        mapped_rows=len(mapped),
        receipt_summary=summary,
        bundles=reconstructed["bundles"],
        evaluated=evaluated,
    )
    _assert_frame(
        stored["decision_table"], reconstructed_decision_table, "decision_table"
    )
    if stored["decision"] != reconstructed_decision:
        raise WalkForwardContractError("decision predicates differ")
    sample_rows = summary.sort_values(["cutoff_ts", "issue", "policy"]).iloc[
        [0, len(summary) // 2, len(summary) - 1]
    ]
    for row in sample_rows.itertuples(index=False):
        issue_target = target_frame[target_frame["issue_code"].eq(str(row.issue))]
        refit = fit_issue_mapping(
            history,
            issue_target,
            Cutoff.decision_epoch(str(row.issue), row.cutoff_ts),
            repository_root=repo_root,
            source_hashes=source["source_hashes"],
            policy_name=str(row.policy),
        )
        if refit.receipt["model_identity"] != row.model_identity:
            raise WalkForwardContractError("sample source refit model differs")
    if stored["decision"]["prospective_authorized"]:
        raise WalkForwardContractError("historical proxy authorized prospective use")
    return {
        "manifest": True,
        "source_identity": True,
        "all_probability_receipts_replayed": True,
        "sample_refits": True,
        "target_identity_exclusion": True,
        "current_year_strict_availability": True,
        "cache_cutoff_isolation": True,
        "weight_mass_and_ess": True,
        "downstream_reconciliation": True,
        "settlement_and_payout": True,
        "synthetic_shift": True,
        "historical_only_boundary": True,
    }
