"""Build and verify the corrected N6 R=0..6 exposed diagnostic matrix."""

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

from src.cutoff_mapping.package import (
    scientific_frames as cutoff_scientific_frames,
    verify_package as verify_cutoff_package,
)
from src.n6_chronology_sync.pipeline import (
    locate_data_root,
    verify_package as verify_upstream_package,
)
from src.source_schema.publication import atomic_publish_directory

from .contract import (
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    CUTOFF_PACKAGE,
    FUNDED_UNITS,
    ISSUE_BOOTSTRAP_DRAWS,
    ISSUE_STAKE_CNY,
    LEGACY_PACKAGE,
    MOVING_BLOCK_DRAWS,
    MOVING_BLOCK_LENGTH,
    N_LEGS,
    PAYOUT_FACTOR,
    R_VALUES,
    ROLLING_WINDOWS,
    STAKE_PER_TICKET_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    UNITS_PER_TICKET,
    UPSTREAM_PACKAGE,
    YEARS,
)


class ContractError(ValueError):
    """Raised when a frozen N6 fixed-R invariant fails."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame) -> str:
    projected = frame.loc[:, sorted(frame.columns)].copy()
    hashes = np.sort(
        pd.util.hash_pandas_object(projected, index=False, categorize=False).to_numpy(np.uint64)
    )
    schema = [(name, str(projected[name].dtype)) for name in projected.columns]
    digest = hashlib.sha256(json.dumps(schema, separators=(",", ":")).encode())
    digest.update(hashes.tobytes())
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _path_metrics(pnl: np.ndarray, gross: np.ndarray) -> dict[str, float | int]:
    capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
    peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL_CNY, capital])[1:]
    drawdown = (peaks - capital) / np.maximum(peaks, 1e-12)
    underwater = drawdown > 1e-15
    peaks_seen = np.flatnonzero(~underwater)
    open_underwater = (
        int(len(pnl) - peaks_seen[-1] - 1)
        if underwater[-1] and len(peaks_seen)
        else int(len(pnl)) if underwater[-1] else 0
    )
    runs = _run_lengths(pnl <= 0)
    payouts = gross[gross > 0]
    weights = payouts / payouts.sum() if payouts.sum() else np.array([], dtype=float)
    return {
        "max_drawdown_fraction": float(drawdown.max()),
        "longest_profitable_issue_losing_run": int(runs.max()) if len(runs) else 0,
        "open_underwater_issues": open_underwater,
        "largest_payout_share": float(weights.max()) if len(weights) else 0.0,
        "payout_hhi": float(np.square(weights).sum()) if len(weights) else 0.0,
    }


def _circular_indices(length: int, draws: int, rng: np.random.Generator) -> np.ndarray:
    block = min(MOVING_BLOCK_LENGTH, length)
    blocks = math.ceil(length / block)
    starts = rng.integers(0, length, (draws, blocks))
    indices = (starts[:, :, None] + np.arange(block)[None, None, :]) % length
    return indices.reshape(draws, -1)[:, :length]


def _load_actions(repo_root: Path, data_root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    upstream = repo_root / UPSTREAM_PACKAGE
    checks = verify_upstream_package(repo_root, upstream, data_root)
    if not all(checks.values()):
        raise ContractError("#376 source-bound verifier did not pass")
    actions = pd.read_parquet(upstream / "action_receipts.parquet")
    actions["issue"] = actions["issue"].astype(str)
    actions["issue_anchor_ts"] = pd.to_datetime(actions["issue_anchor_ts"], utc=True)
    if not actions["issue_year"].isin(YEARS).all():
        raise ContractError("action surface contains a non-contract year")
    if actions.duplicated(["issue", "match_idx"]).any():
        raise ContractError("action surface key is not unique")
    if not (pd.to_datetime(actions["training_label_available_max_ts"], utc=True)
            < pd.to_datetime(actions["fixture_decision_ts"], utc=True)).all():
        raise ContractError("action surface is not strictly causal")
    cutoff_package = repo_root / CUTOFF_PACKAGE
    cutoff_checks = verify_cutoff_package(repo_root, cutoff_package, data_root)
    if not all(cutoff_checks.values()):
        raise ContractError("#382 shared cutoff package did not verify")
    cutoff = cutoff_scientific_frames(repo_root, data_root)
    mapped = cutoff["mapped"].rename(columns={"issue_code": "issue"})
    probability = actions.merge(
        mapped,
        on=["issue", "issue_year", "match_idx"],
        suffixes=("_376", "_382"),
        validate="one_to_one",
    )
    if len(probability) != len(actions):
        raise ContractError("#382 cutoff mapping key set differs from #376 actions")
    parity_columns: list[str] = []
    for prefix_376, prefix_382 in [("q_eu", "q_mapped"), ("q_line", "q_line")]:
        for outcome in ["3", "1", "0"]:
            name = f"exact_{prefix_376}_{outcome}"
            parity_columns.append(name)
            left = (
                f"{prefix_376}_{outcome}_376"
                if prefix_376 == prefix_382
                else f"{prefix_376}_{outcome}"
            )
            right = (
                f"{prefix_382}_{outcome}_382"
                if prefix_376 == prefix_382
                else f"{prefix_382}_{outcome}"
            )
            probability[name] = np.isclose(
                probability[left],
                probability[right],
                rtol=0,
                atol=1e-12,
            )
    if not probability[parity_columns].all(axis=1).all():
        raise ContractError("#376 action probabilities differ from shared cutoff output")
    legacy_manifest = repo_root / LEGACY_PACKAGE / "MANIFEST.json"
    return actions, {
        "contract": CONTRACT_ID,
        "upstream_contract": _read_json(upstream / "MANIFEST.json")["contract"],
        "upstream_manifest_sha256": sha256_file(upstream / "MANIFEST.json"),
        "action_surface_frame_sha256": stable_frame_sha(actions),
        "cutoff_contract": cutoff["receipt"]["contract"],
        "cutoff_manifest_sha256": sha256_file(cutoff_package / "MANIFEST.json"),
        "cutoff_identity": cutoff["receipt"]["cutoff_identity"],
        "cutoff_ts": cutoff["receipt"]["cutoff_ts"],
        "cutoff_maximum_training_label_timestamp": cutoff["receipt"][
            "maximum_training_label_timestamp"
        ],
        "cutoff_model_identity": cutoff["receipt"]["model_identity"],
        "cutoff_cache_key": cutoff["receipt"]["cache_key"],
        "cutoff_probability_parity_rows": len(probability),
        "cutoff_probability_parity_exact_rows": int(
            probability[parity_columns].all(axis=1).sum()
        ),
        "legacy_manifest_sha256": sha256_file(legacy_manifest),
        "chronology": "SOURCE_ISSUE_REGISTRY_YEAR + FIXTURE_RELATIVE_10H",
        "evaluation_role": "EXPOSED_RETROSPECTIVE_COMPLETE_R_DIAGNOSTIC",
        "r_grid": list(R_VALUES),
        "selection": "EXACT_#376_TOP6_RETAINED_MASS",
        "ticket_design": "64_COMPLETE_CARTESIAN; 8_CNY2_UNITS_EACH; CNY1024",
        "payout_factor_application": "0.65_ONCE_PER_COMPLETE_WINNING_TICKET",
        "no_r_reselection": True,
    }


def construct_surface(actions: pd.DataFrame) -> dict[str, pd.DataFrame]:
    decision_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    bundle_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    saturation_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    for (issue, year, anchor), group in actions.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        selected = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
        ).head(N_LEGS).sort_values("match_idx", kind="stable").copy()
        complete = len(selected) == N_LEGS
        trusted = int(selected["settlement_available"].sum()) if complete else 0
        coverage_rows.append({
            "issue": str(issue), "issue_year": int(year), "issue_anchor_ts": anchor,
            "available_fixtures": int(len(group)), "selected_legs": int(len(selected)),
            "trusted_selected_legs": trusted,
            "settlement_complete": bool(complete and trusted == N_LEGS),
            "excluded_reason": "" if complete and trusted == N_LEGS else (
                "INSUFFICIENT_FIXTURES" if not complete else "UNTRUSTED_SELECTED_LEG"
            ),
        })
        if not complete:
            continue
        ranked = selected.sort_values(
            ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
        )
        fixture_order = selected["match_idx"].astype(int).tolist()
        previous_support_set: tuple[tuple[int, str], ...] | None = None
        for r in R_VALUES:
            activated = set(ranked.head(r)["match_idx"].astype(int))
            support_map = {
                int(row.match_idx): str(row.qeu_support if int(row.match_idx) in activated else row.baseline_support)
                for row in selected.itertuples()
            }
            support_set = tuple(sorted(support_map.items()))
            actual_changes = sum(
                support_map[int(row.match_idx)] != str(row.baseline_support)
                for row in selected.itertuples()
            )
            eligible = int(selected["support_changed"].astype(bool).sum())
            saturation_rows.append({
                "issue": str(issue), "issue_year": int(year), "r": r,
                "requested_depth": r, "eligible_changed_legs": eligible,
                "actual_changed_legs": int(actual_changes),
                "marginal_support_set_changed": bool(previous_support_set is not None and support_set != previous_support_set),
                "support_set_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
            })
            previous_support_set = support_set
            decision_rows.append({
                "issue": str(issue), "issue_year": int(year), "issue_anchor_ts": anchor,
                "r": r, "arm": f"R{r}",
                "selected_match_ids": "|".join(map(str, fixture_order)),
                "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                "requested_depth": r, "eligible_changes": eligible,
                "actual_changed_matches": int(actual_changes),
                "ticket_count": TICKETS, "funded_units": FUNDED_UNITS,
                "planned_stake_cny": ISSUE_STAKE_CNY,
                "settlement_status": "SETTLED" if trusted == N_LEGS else "UNTRUSTED_SELECTED_LEG",
            })
            supports = [support_map[key] for key in fixture_order]
            for ordinal, choices in enumerate(itertools.product((0, 1), repeat=N_LEGS)):
                outcomes = [support[choice] for support, choice in zip(supports, choices, strict=True)]
                ticket_rows.append({
                    "issue": str(issue), "issue_year": int(year), "r": r,
                    "ticket_ordinal": ordinal, "ticket_code": "|".join(outcomes),
                    "units": UNITS_PER_TICKET, "stake_cny": STAKE_PER_TICKET_CNY,
                })
            active = np.asarray([support_map[key] for key in fixture_order])
            realized = selected["result_code"].fillna("").astype(str).to_numpy()
            included = np.asarray([value in support for value, support in zip(realized, active, strict=True)])
            misses = int((~included).sum())
            gross = (
                float(STAKE_PER_TICKET_CNY * PAYOUT_FACTOR * selected["winning_sp"].prod())
                if trusted == N_LEGS and misses == 0 else 0.0
            )
            if trusted == N_LEGS:
                bundle_rows.append({
                    "issue": str(issue), "issue_year": int(year), "issue_anchor_ts": anchor,
                    "r": r, "arm": f"R{r}", "selected_match_ids": "|".join(map(str, fixture_order)),
                    "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                    "actual_changed_matches": int(actual_changes), "ticket_count": TICKETS,
                    "funded_units": FUNDED_UNITS, "stake_cny": ISSUE_STAKE_CNY,
                    "gross_cny": gross, "pnl_cny": gross - ISSUE_STAKE_CNY,
                    "miss_count": misses, "hit": bool(misses == 0),
                })
            pressure_rank = selected["support_pressure"].rank(method="first", ascending=False).astype(int)
            for row, support, ok, rank in zip(
                selected.itertuples(), active, included, pressure_rank, strict=True
            ):
                attribution_rows.append({
                    "issue": str(issue), "issue_year": int(year), "r": r,
                    "match_idx": int(row.match_idx), "pressure_rank": int(rank),
                    "support_pressure": float(row.support_pressure),
                    "baseline_support": str(row.baseline_support), "qeu_support": str(row.qeu_support),
                    "active_support": str(support),
                    "qeu_activated": bool(int(row.match_idx) in activated),
                    "support_actually_changed": bool(str(support) != str(row.baseline_support)),
                    "result_code": str(row.result_code), "winning_sp": float(row.winning_sp),
                    "settlement_available": bool(row.settlement_available),
                    "realized_in_support": bool(ok),
                })
    return {
        "decisions": pd.DataFrame(decision_rows), "tickets": pd.DataFrame(ticket_rows),
        "bundles": pd.DataFrame(bundle_rows), "attribution": pd.DataFrame(attribution_rows),
        "saturation": pd.DataFrame(saturation_rows), "coverage": pd.DataFrame(coverage_rows),
    }


def evaluate(bundles: pd.DataFrame) -> dict[str, pd.DataFrame]:
    perf_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    contrast_rows: list[dict[str, Any]] = []
    issue_boot_rows: list[dict[str, Any]] = []
    block_boot_rows: list[dict[str, Any]] = []
    rolling_rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    scopes = [(str(year), bundles[bundles["issue_year"].eq(year)]) for year in YEARS] + [("ALL", bundles)]
    for scope, scoped in scopes:
        wide = scoped.pivot(index=["issue_anchor_ts", "issue"], columns="r", values="pnl_cny").sort_index(kind="stable")
        if list(wide.columns) != list(R_VALUES) or wide.isna().any().any():
            raise ContractError("R surface does not share an exact common denominator")
        gross_wide = scoped.pivot(index=["issue_anchor_ts", "issue"], columns="r", values="gross_cny").loc[wide.index]
        for r in R_VALUES:
            group = scoped[scoped["r"].eq(r)].sort_values(["issue_anchor_ts", "issue"], kind="stable")
            pnl, gross = group["pnl_cny"].to_numpy(float), group["gross_cny"].to_numpy(float)
            largest_gross_idx = int(np.argmax(gross))
            perf_rows.append({
                "scope": scope, "r": r, "issues": len(group), "stake_cny": float(group["stake_cny"].sum()),
                "gross_cny": float(gross.sum()), "pnl_cny": float(pnl.sum()),
                "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                "ticket_hit_rate": float(group["hit"].sum() / group["ticket_count"].sum()),
                "issue_hit_rate": float(group["hit"].mean()),
                "issue_profitable_rate": float(group["pnl_cny"].gt(0).mean()),
                "armwise_ex_largest_pnl_cny": float(pnl.sum() - pnl[largest_gross_idx]),
            })
            risk_rows.append({"scope": scope, "r": r, **_path_metrics(pnl, gross)})
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL_CNY, capital])[1:]
            for order, (row, value, peak) in enumerate(zip(group.itertuples(), capital, peaks, strict=True), start=1):
                path_rows.append({
                    "scope": scope, "r": r, "issue_order": order, "issue": row.issue,
                    "issue_year": int(row.issue_year), "issue_anchor_ts": row.issue_anchor_ts,
                    "pnl_cny": float(row.pnl_cny), "capital_cny": float(value),
                    "drawdown_fraction": float((peak - value) / max(peak, 1e-12)),
                })
            if scope == "ALL":
                for window in ROLLING_WINDOWS:
                    roll = pd.Series(pnl).rolling(window).sum().dropna().to_numpy(float)
                    rolling_rows.append({
                        "r": r, "window_issues": window, "windows": len(roll),
                        "loss_probability": float((roll < 0).mean()),
                        "worst_window_pnl_cny": float(roll.min()),
                        "median_window_pnl_cny": float(np.median(roll)),
                    })
        base_pnl = wide[0].to_numpy(float)
        base_gross = gross_wide[0].to_numpy(float)
        base_ex = base_pnl.sum() - base_pnl[int(np.argmax(base_gross))]
        for r in R_VALUES:
            challenger = wide[r].to_numpy(float)
            challenger_gross = gross_wide[r].to_numpy(float)
            delta = challenger - base_pnl
            arm_ex = challenger.sum() - challenger[int(np.argmax(challenger_gross))]
            largest_delta_idx = int(np.argmax(np.abs(delta)))
            contrast_rows.append({
                "scope": scope, "r": r, "issues": len(delta),
                "matched_lift_cny": float(delta.sum()),
                "armwise_ex_largest_lift_cny": float(arm_ex - base_ex),
                "largest_absolute_paired_delta_cny": float(delta[largest_delta_idx]),
                "largest_absolute_paired_delta_issue": str(wide.index[largest_delta_idx][1]),
                "lift_ex_largest_absolute_paired_delta_cny": float(delta.sum() - delta[largest_delta_idx]),
            })
            iid = delta[rng.integers(0, len(delta), (ISSUE_BOOTSTRAP_DRAWS, len(delta)))].sum(axis=1)
            block = delta[_circular_indices(len(delta), MOVING_BLOCK_DRAWS, rng)].sum(axis=1)
            issue_boot_rows.append({
                "scope": scope, "r": r, "draws": ISSUE_BOOTSTRAP_DRAWS,
                "lift_p05_cny": float(np.quantile(iid, .05)), "lift_median_cny": float(np.median(iid)),
                "lift_p95_cny": float(np.quantile(iid, .95)),
            })
            block_boot_rows.append({
                "scope": scope, "r": r, "draws": MOVING_BLOCK_DRAWS,
                "block_length": min(MOVING_BLOCK_LENGTH, len(delta)),
                "lift_p05_cny": float(np.quantile(block, .05)), "lift_median_cny": float(np.median(block)),
                "lift_p95_cny": float(np.quantile(block, .95)),
            })
    return {
        "performance": pd.DataFrame(perf_rows), "risk": pd.DataFrame(risk_rows),
        "paths": pd.DataFrame(path_rows), "contrasts": pd.DataFrame(contrast_rows),
        "issue_bootstrap": pd.DataFrame(issue_boot_rows), "block_bootstrap": pd.DataFrame(block_boot_rows),
        "rolling": pd.DataFrame(rolling_rows),
    }


def saturation_summary(saturation: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (year, r), group in saturation.groupby(["issue_year", "r"], observed=True):
        rows.append({
            "scope": str(year), "r": int(r), "issues": len(group),
            "mean_eligible_changed_legs": float(group["eligible_changed_legs"].mean()),
            "mean_actual_changed_legs": float(group["actual_changed_legs"].mean()),
            "support_set_change_rate_vs_prior_r": float(group["marginal_support_set_changed"].mean()),
            "fully_saturated_rate": float(group["actual_changed_legs"].eq(group["eligible_changed_legs"]).mean()),
        })
    for r, group in saturation.groupby("r", observed=True):
        rows.append({
            "scope": "ALL", "r": int(r), "issues": len(group),
            "mean_eligible_changed_legs": float(group["eligible_changed_legs"].mean()),
            "mean_actual_changed_legs": float(group["actual_changed_legs"].mean()),
            "support_set_change_rate_vs_prior_r": float(group["marginal_support_set_changed"].mean()),
            "fully_saturated_rate": float(group["actual_changed_legs"].eq(group["eligible_changed_legs"]).mean()),
        })
    return pd.DataFrame(rows)


def legacy_comparison(repo_root: Path, bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    legacy = pd.read_parquet(repo_root / LEGACY_PACKAGE / "settled_bundles.parquet")
    legacy = legacy[legacy["n"].eq(6) & legacy["r"].isin(R_VALUES)].copy()
    legacy["issue"] = legacy["issue"].astype(str)
    old = legacy[["issue", "issue_year", "r", "selected_match_ids", "support_json", "stake_cny", "gross_cny", "pnl_cny", "hit"]]
    new = bundles[["issue", "issue_year", "r", "selected_match_ids", "support_json", "stake_cny", "gross_cny", "pnl_cny", "hit"]]
    merged = old.merge(new, on=["issue", "r"], how="outer", suffixes=("_legacy", "_corrected"), indicator=True)
    common = merged["_merge"].eq("both")
    merged["exact_year"] = common & merged["issue_year_legacy"].eq(merged["issue_year_corrected"])
    merged["exact_selected_fixtures"] = common & merged["selected_match_ids_legacy"].eq(merged["selected_match_ids_corrected"])
    merged["exact_support"] = common & merged["support_json_legacy"].eq(merged["support_json_corrected"])
    merged["exact_settlement"] = common & np.isclose(merged["pnl_cny_legacy"], merged["pnl_cny_corrected"], rtol=0, atol=1e-9)
    summary_rows = []
    for r, group in merged.groupby("r", observed=True):
        overlap = group[group["_merge"].eq("both")]
        summary_rows.append({
            "r": int(r), "legacy_rows": int(group["_merge"].isin(["both", "left_only"]).sum()),
            "corrected_rows": int(group["_merge"].isin(["both", "right_only"]).sum()),
            "common_rows": len(overlap), "year_exact_rows": int(overlap["exact_year"].sum()),
            "fixture_exact_rows": int(overlap["exact_selected_fixtures"].sum()),
            "support_exact_rows": int(overlap["exact_support"].sum()),
            "pnl_exact_rows": int(overlap["exact_settlement"].sum()),
            "changed_pnl_rows": int((~overlap["exact_settlement"]).sum()),
            "corrected_minus_legacy_common_pnl_cny": float((overlap["pnl_cny_corrected"] - overlap["pnl_cny_legacy"]).sum()),
        })
    return merged, pd.DataFrame(summary_rows)


def scientific_frames(repo_root: Path, data_root: Path) -> dict[str, Any]:
    actions, source = _load_actions(repo_root, data_root)
    constructed = construct_surface(actions)
    evaluated = evaluate(constructed["bundles"])
    saturation = saturation_summary(constructed["saturation"])
    legacy_rows, legacy_summary = legacy_comparison(repo_root, constructed["bundles"])
    upstream_bundles = pd.read_parquet(repo_root / UPSTREAM_PACKAGE / "issue_bundles.parquet")
    parity = constructed["bundles"][constructed["bundles"]["r"].isin([0, 3])].merge(
        upstream_bundles, left_on=["issue", "arm"], right_on=["issue", "arm"],
        suffixes=("_381", "_376"), validate="one_to_one", indicator=True,
    )
    parity["exact_pnl"] = np.isclose(parity["pnl_cny_381"], parity["pnl_cny_376"], rtol=0, atol=1e-9)
    parity["exact_support"] = parity["support_json_381"].eq(parity["support_json_376"])
    if len(parity) != 304 or not (parity["exact_pnl"] & parity["exact_support"]).all():
        raise ContractError("R0/R3 does not exactly reproduce #376")
    all_perf = evaluated["performance"][evaluated["performance"]["scope"].eq("ALL")]
    positive = all_perf.loc[all_perf["pnl_cny"].gt(0), "r"].astype(int).tolist()
    decision = {
        "contract": CONTRACT_ID,
        "verdict": "COMPLETE_CORRECTED_N6_R_SURFACE_DIAGNOSTIC_ONLY",
        "positive_standalone_point_estimate_r": positive,
        "fixed_r3_replaced": False, "expert_admitted_r": [],
        "eligible_for_378_as_exposed_comparator": positive,
        "promotable_to_210": False, "changes_to_210_or_218": False,
        "prospective_shadow_started": False,
    }
    return {
        "source": source, "actions": actions, **constructed, **evaluated,
        "saturation_summary": saturation, "legacy_rows": legacy_rows,
        "legacy_summary": legacy_summary, "r0_r3_parity": parity, "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source", "action_receipts.parquet": "actions",
    "decisions.parquet": "decisions", "tickets.parquet": "tickets",
    "issue_bundles.parquet": "bundles", "support_attribution.parquet": "attribution",
    "support_saturation.parquet": "saturation", "support_saturation_summary.csv": "saturation_summary",
    "coverage_ledger.csv": "coverage", "performance.csv": "performance",
    "risk_diagnostics.csv": "risk", "capital_paths.parquet": "paths",
    "matched_contrasts.csv": "contrasts", "issue_bootstrap.csv": "issue_bootstrap",
    "moving_block_bootstrap.csv": "block_bootstrap", "rolling_windows.csv": "rolling",
    "legacy_issue_r_comparison.parquet": "legacy_rows", "legacy_summary.csv": "legacy_summary",
    "r0_r3_parity.parquet": "r0_r3_parity", "decision.json": "decision",
}


def _write(path: Path, value: Any) -> None:
    if isinstance(value, pd.DataFrame):
        (value.to_parquet(path, index=False) if path.suffix == ".parquet" else value.to_csv(path, index=False))
    else:
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _implementation_hashes() -> dict[str, str]:
    repo_src = Path(__file__).parents[1]
    return {
        "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
        "pipeline.py": sha256_file(Path(__file__)),
        "cutoff_mapping/api.py": sha256_file(repo_src / "cutoff_mapping/api.py"),
        "temporal_learning/core.py": sha256_file(repo_src / "temporal_learning/core.py"),
    }


def build_package(repo_root: Path, target: Path, explicit_data_root: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    frames = scientific_frames(repo_root, data_root)
    deliveries = [
        "docs/research/Issue-381-N6-Corrected-All-R.md",
        "docs/research/figures/issue_381_n6_corrected_all_r.png",
        "notebooks/research/n6-corrected-all-r/n6_corrected_all_r.ipynb",
    ]
    def populate(staging: Path) -> None:
        for relative, key in PACKAGE_FILES.items():
            _write(staging / relative, frames[key])
        manifest = {
            "contract": CONTRACT_ID,
            "files": {name: {"sha256": sha256_file(staging / name), "bytes": (staging / name).stat().st_size} for name in sorted(PACKAGE_FILES)},
            "frame_hashes": {key: stable_frame_sha(value) for key, value in frames.items() if isinstance(value, pd.DataFrame)},
            "implementation": _implementation_hashes(),
            "delivery": {name: sha256_file(repo_root / name) for name in deliveries if (repo_root / name).is_file()},
        }
        (staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    atomic_publish_directory(target.resolve(), populate, force=force)
    return frames["decision"]


def verify_package(repo_root: Path, target: Path, explicit_data_root: Path | None = None) -> dict[str, bool]:
    repo_root, target = repo_root.resolve(), target.resolve()
    data_root = locate_data_root(repo_root, explicit_data_root)
    manifest = _read_json(target / "MANIFEST.json")
    if manifest.get("contract") != CONTRACT_ID or set(manifest.get("files", {})) != set(PACKAGE_FILES):
        raise ContractError("manifest contract/file set mismatch")
    for relative, receipt in manifest["files"].items():
        if not (target / relative).is_file() or sha256_file(target / relative) != receipt["sha256"]:
            raise ContractError(f"manifest mismatch: {relative}")
    if manifest.get("implementation") != _implementation_hashes():
        raise ContractError("implementation hash mismatch")
    expected = scientific_frames(repo_root, data_root)
    for relative, key in PACKAGE_FILES.items():
        value, path = expected[key], target / relative
        if isinstance(value, pd.DataFrame):
            if path.suffix == ".parquet":
                actual = pd.read_parquet(path)
                try:
                    pd.testing.assert_frame_equal(actual, value.reset_index(drop=True), check_dtype=False, check_categorical=False, check_exact=True)
                    matches = True
                except AssertionError:
                    matches = False
            else:
                matches = hashlib.sha256(value.to_csv(index=False).encode()).hexdigest() == sha256_file(path)
            if not matches:
                raise ContractError(f"scientific frame mismatch: {relative}")
        elif _read_json(path) != value:
            raise ContractError(f"receipt mismatch: {relative}")
    tickets = expected["tickets"].groupby(["issue", "r"], observed=True)
    if not tickets.size().eq(TICKETS).all() or not tickets["ticket_code"].nunique().eq(TICKETS).all():
        raise ContractError("ticket group is not complete Cartesian")
    if not tickets["units"].sum().eq(FUNDED_UNITS).all() or not np.isclose(tickets["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-12).all():
        raise ContractError("ticket funding mismatch")
    bundles = expected["bundles"]
    if not np.allclose(bundles["pnl_cny"], bundles["gross_cny"] - bundles["stake_cny"], rtol=0, atol=1e-9):
        raise ContractError("bundle PnL identity failed")
    keys = bundles.groupby("issue", observed=True)["r"].agg(lambda values: set(values))
    if not keys.map(lambda values: values == set(R_VALUES)).all():
        raise ContractError("settled R key set is incomplete")
    parity = expected["r0_r3_parity"]
    if len(parity) != 304 or not (parity["exact_pnl"] & parity["exact_support"]).all():
        raise ContractError("R0/R3 parity failed")
    delivery = {
        "docs/research/Issue-381-N6-Corrected-All-R.md",
        "docs/research/figures/issue_381_n6_corrected_all_r.png",
        "notebooks/research/n6-corrected-all-r/n6_corrected_all_r.ipynb",
    }
    if set(manifest.get("delivery", {})) != delivery:
        raise ContractError("delivery receipt set mismatch")
    for relative, expected_hash in manifest["delivery"].items():
        if not (repo_root / relative).is_file() or sha256_file(repo_root / relative) != expected_hash:
            raise ContractError(f"delivery mismatch: {relative}")
    notebook = nbformat.read(repo_root / "notebooks/research/n6-corrected-all-r/n6_corrected_all_r.ipynb", as_version=4)
    if any(cell.get("execution_count") is None for cell in notebook.cells if cell.cell_type == "code"):
        raise ContractError("notebook is not fully executed")
    return {
        "manifest": True, "source_bound_376": True, "complete_r_grid": True,
        "r0_r3_exact_parity": True, "fixed_budget": True, "ticket_level_once_payout": True,
        "exact_common_denominator": True, "two_tail_sensitivities": True,
        "issue_and_moving_block_bootstrap": True, "path_and_rolling_risk": True,
        "legacy_change_ledger": True, "no_reselection_or_promotion": True, "delivery": True,
    }


def _markdown_table(frame: pd.DataFrame) -> str:
    rendered = frame.copy()
    for column in rendered.select_dtypes(include="float").columns:
        rendered[column] = rendered[column].map(lambda value: f"{value:.4f}")
    header = "| " + " | ".join(rendered.columns) + " |"
    separator = "|" + "|".join("---" for _ in rendered.columns) + "|"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in rendered.itertuples(index=False, name=None)]
    return "\n".join([header, separator, *rows])


def build_notebook_and_report(repo_root: Path, package: Path) -> None:
    notebook_path = repo_root / "notebooks/research/n6-corrected-all-r/n6_corrected_all_r.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell("# Issue #381 — corrected N6 fixed R0–R6"),
        nbformat.v4.new_code_cell("from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\nROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/n6_corrected_all_r'"),
        nbformat.v4.new_code_cell("perf=pd.read_csv(OUT/'performance.csv')\nperf"),
        nbformat.v4.new_code_cell("contrasts=pd.read_csv(OUT/'matched_contrasts.csv')\ncontrasts"),
        nbformat.v4.new_code_cell("risk=pd.read_csv(OUT/'risk_diagnostics.csv')\nrisk"),
        nbformat.v4.new_code_cell("block=pd.read_csv(OUT/'moving_block_bootstrap.csv')\nblock"),
        nbformat.v4.new_code_cell("sat=pd.read_csv(OUT/'support_saturation_summary.csv')\nsat"),
        nbformat.v4.new_code_cell("legacy=pd.read_csv(OUT/'legacy_summary.csv')\nlegacy"),
        nbformat.v4.new_code_cell("paths=pd.read_parquet(OUT/'capital_paths.parquet')\nfor r,g in paths[paths.scope.eq('ALL')].groupby('r'): plt.plot(g.issue_order,g.capital_cny,label=f'R{r}')\nplt.axhline(100000,color='black',lw=.8); plt.legend(); plt.title('Corrected N6 fixed-R capital paths'); plt.show()"),
    ]
    NotebookClient(nb, timeout=300, kernel_name="python3").execute(cwd=str(notebook_path.parent))
    nbformat.write(nb, notebook_path)
    perf = pd.read_csv(package / "performance.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    contrasts = pd.read_csv(package / "matched_contrasts.csv")
    block = pd.read_csv(package / "moving_block_bootstrap.csv")
    rolling = pd.read_csv(package / "rolling_windows.csv")
    sat = pd.read_csv(package / "support_saturation_summary.csv")
    legacy = pd.read_csv(package / "legacy_summary.csv")
    decision = _read_json(package / "decision.json")
    source = _read_json(package / "source_receipt.json")
    full = perf[perf["scope"].eq("ALL")].merge(risk[risk["scope"].eq("ALL")], on=["scope", "r"]).merge(contrasts[contrasts["scope"].eq("ALL")], on=["scope", "r"])
    annual = perf[perf["scope"].ne("ALL")].pivot(index="r", columns="scope", values="pnl_cny").reset_index()
    figure = repo_root / "docs/research/figures/issue_381_n6_corrected_all_r.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    paths = pd.read_parquet(package / "capital_paths.parquet")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    for r, group in paths[paths["scope"].eq("ALL")].groupby("r"):
        axes[0].plot(group["issue_order"], group["capital_cny"], label=f"R{r}")
    axes[0].axhline(STARTING_CAPITAL_CNY, color="black", linewidth=.8)
    axes[0].legend()
    axes[0].set_title("Corrected N6 capital paths")
    axes[1].plot(full["r"], full["pnl_cny"], marker="o", label="PnL")
    axes[1].plot(full["r"], full["armwise_ex_largest_pnl_cny"], marker="o", label="Armwise ex-largest PnL")
    axes[1].axhline(0, color="black", linewidth=.8)
    axes[1].legend()
    axes[1].set_title("Return and tail sensitivity")
    fig.tight_layout()
    fig.savefig(figure, dpi=160)
    plt.close(fig)
    report = f"""# Issue #381 — corrected N6 fixed-R0–R6 diagnostic

Contract: `{CONTRACT_ID}`

## Shared cutoff-learning lineage

This diagnostic is a downstream client of `{source['cutoff_contract']}` rather
than a local chronology implementation.  It passes the explicit
`{source['cutoff_identity']}` boundary at `{source['cutoff_ts']}`; the latest
admitted training label is `{source['cutoff_maximum_training_label_timestamp']}`.
The source-bound replay reconciles `{source['cutoff_probability_parity_exact_rows']}` /
`{source['cutoff_probability_parity_rows']}` mapped-probability cells exactly to
the shared cutoff client.  No detached mapping-acceptance boolean controls this
surface.

## Decision

`{decision['verdict']}`. Positive standalone point-estimate R rows: `{decision['positive_standalone_point_estimate_r']}`. None replaces fixed R3 or enters the expert pool; any positive row may enter #378 only as an explicitly exposed comparator.

## Full-sample economics, path risk and tail sensitivity

{_markdown_table(full)}

## Annual PnL

{_markdown_table(annual)}

## Matched lift moving-block evidence

{_markdown_table(block[block['scope'].eq('ALL')])}

## Action-depth saturation

{_markdown_table(sat[sat['scope'].eq('ALL')])}

## Rolling path risk

{_markdown_table(rolling)}

## Corrected versus legacy #352

{_markdown_table(legacy)}

## Interpretation boundary

R0 and R3 exactly reproduce #376 on 304 issue-arm rows. R1/R2/R4/R5/R6 are newly reconstructed on the same corrected source, not copied from #352. The complete matrix is exposed retrospective evidence and is not an R-selection surface. Two tail diagnostics are deliberately separate: armwise removal of each arm's largest payout and removal of the single largest absolute paired delta. #210/#218 and prospective evidence remain untouched.
"""
    (repo_root / "docs/research/Issue-381-N6-Corrected-All-R.md").write_text(report, encoding="utf-8")
