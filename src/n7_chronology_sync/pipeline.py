"""Rebuild the fixed N7 R0/R3 expert on the #360 chronology contract."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.qeu_threshold_n7.pipeline import prepare_match_actions
from src.low_n_selector_data.pipeline import verify_package as verify_corrected_source
from src.source_schema.publication import atomic_publish_directory, atomic_write_json

from .contract import (
    ARMS,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    CORRECTED_PACKAGE,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    LEGACY_MANIFEST_SHA256,
    LEGACY_PACKAGE,
    N_LEGS,
    OUTCOMES,
    PAYOUT_FACTOR,
    STAKE_PER_TICKET_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    UNITS_PER_TICKET,
    YEARS,
)


class ContractError(ValueError):
    """Raised when chronology, source, or settlement semantics fail closed."""


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


def locate_data_root(repo_root: Path, explicit: Path | None = None) -> Path:
    candidates = [] if explicit is None else [Path(explicit)]
    candidates.extend([repo_root / "data", Path("/home/drwho1985/workspace/soccer/beijing-lot/data")])
    for candidate in candidates:
        if (candidate / "derived/beidan_xlsm/beidan_xlsm.sqlite").is_file():
            return candidate.resolve()
    raise FileNotFoundError("canonical settlement data root not found")


def _verify_upstream_package(repo_root: Path) -> dict[str, str]:
    package = repo_root / CORRECTED_PACKAGE
    manifest = _read_json(package / "MANIFEST.json")
    files = manifest.get("files", {})
    required = {
        "features/selector_cells.parquet",
        "features/selector_features.parquet",
        "labels/selector_labels.parquet",
        "FREEZE_RECEIPT.json",
        "SOURCE_RECEIPT.json",
    }
    if not required.issubset(files):
        raise ContractError("#360 manifest lacks required corrected chronology files")
    for relative in sorted(required):
        path = package / relative
        if not path.is_file() or sha256_file(path) != files[relative]:
            raise ContractError(f"#360 source hash mismatch: {relative}")
    return {relative: files[relative] for relative in sorted(required)}


def _verify_legacy_package(repo_root: Path) -> dict[str, Any]:
    package = repo_root / LEGACY_PACKAGE
    manifest_path = package / "MANIFEST.json"
    if sha256_file(manifest_path) != LEGACY_MANIFEST_SHA256:
        raise ContractError("legacy N7 manifest is not the accepted frozen source")
    manifest = _read_json(manifest_path)
    required = {
        f"{LEGACY_PACKAGE}/action_receipts.parquet",
        f"{LEGACY_PACKAGE}/issue_bundles.parquet",
        f"{LEGACY_PACKAGE}/ticket_receipts.parquet",
    }
    files = manifest.get("files", {})
    if not required.issubset(files):
        raise ContractError("legacy N7 manifest lacks required parity inputs")
    consumed: dict[str, str] = {}
    for relative in sorted(required):
        path = repo_root / relative
        expected = files[relative].get("sha256")
        if not path.is_file() or sha256_file(path) != expected:
            raise ContractError(f"legacy N7 source hash mismatch: {relative}")
        consumed[relative] = str(expected)
    return {
        "manifest_sha256": LEGACY_MANIFEST_SHA256,
        "consumed_files": consumed,
    }


def _settlement_frame(data_root: Path, issues: list[str]) -> pd.DataFrame:
    path = data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    placeholders = ",".join("?" for _ in issues)
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        frame = pd.read_sql_query(
            f"""
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   CAST(result_code AS TEXT) AS result_code,
                   CAST(winning_sp AS REAL) AS winning_sp,
                   CAST(official_sp_3 AS REAL) AS official_sp_3,
                   CAST(official_sp_1 AS REAL) AS official_sp_1,
                   CAST(official_sp_0 AS REAL) AS official_sp_0,
                   CAST(has_trusted_settlement AS INTEGER) AS trusted,
                   settlement_quality
            FROM match_features
            WHERE CAST(issue AS TEXT) IN ({placeholders})
            ORDER BY CAST(issue AS TEXT), match_idx
            """,
            connection,
            params=issues,
        )
    if frame.duplicated(["issue", "match_idx"]).any():
        raise ContractError("settlement source has duplicate fixture keys")
    fallback = pd.Series(np.nan, index=frame.index, dtype=float)
    for outcome in OUTCOMES:
        mask = frame["result_code"].eq(outcome)
        fallback.loc[mask] = pd.to_numeric(
            frame.loc[mask, f"official_sp_{outcome}"], errors="coerce"
        )
    frame["winning_sp"] = pd.to_numeric(frame["winning_sp"], errors="coerce").fillna(fallback)
    frame["settlement_available"] = (
        frame["trusted"].eq(1)
        & frame["result_code"].isin(OUTCOMES)
        & frame["winning_sp"].gt(0)
    )
    return frame[
        [
            "issue",
            "match_idx",
            "result_code",
            "winning_sp",
            "settlement_available",
            "settlement_quality",
        ]
    ].copy()


def load_corrected_cells(
    repo_root: Path, data_root: Path
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    upstream_hashes = _verify_upstream_package(repo_root)
    legacy_source = _verify_legacy_package(repo_root)
    package = repo_root / CORRECTED_PACKAGE
    cells = pd.read_parquet(package / "features/selector_cells.parquet")
    labels = pd.read_parquet(package / "labels/selector_labels.parquet")
    cells = cells[cells["issue_year"].isin(YEARS)].copy()
    cells["issue"] = cells["issue"].astype(str)
    cells["outcome_code"] = cells["outcome_code"].astype(str)
    if cells.duplicated(["issue", "match_idx", "outcome_code"]).any():
        raise ContractError("corrected Mx3 source key is not unique")
    if not cells["issue_date_source"].eq("SOURCE_ISSUE_REGISTRY_YEAR").all():
        raise ContractError("corrected cells do not use registry-year routing")
    if not (pd.to_datetime(cells["training_label_available_max_ts"], utc=True)
            < pd.to_datetime(cells["fixture_decision_ts"], utc=True)).all():
        raise ContractError("training labels are not strictly prior to fixture decisions")
    triplets = cells.groupby(["issue", "match_idx"], observed=True)["outcome_code"].nunique()
    if not triplets.eq(3).all():
        raise ContractError("corrected source is not exact Mx3")
    labels["issue"] = labels["issue"].astype(str)
    labels = labels[labels["issue"].isin(cells["issue"].unique())].copy()
    settlement = _settlement_frame(data_root, sorted(cells["issue"].unique()))
    settlement = cells[["issue", "match_idx"]].drop_duplicates().merge(
        settlement,
        on=["issue", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    settlement["settlement_available"] = settlement["settlement_available"].fillna(False).astype(bool)
    label_check = labels.merge(
        settlement[["issue", "match_idx", "result_code", "settlement_available"]],
        on=["issue", "match_idx"], suffixes=("_360", "_sqlite"), validate="one_to_one",
    )
    observable = label_check["label_available"].astype(bool)
    if not label_check.loc[observable, "result_code_360"].astype(str).eq(
        label_check.loc[observable, "result_code_sqlite"].astype(str)
    ).all():
        raise ContractError("#360 labels disagree with canonical settlement result codes")
    if not label_check["label_available"].astype(bool).eq(label_check["settlement_available"].astype(bool)).all():
        raise ContractError("#360 label availability disagrees with canonical settlement")
    prepared = cells.rename(
        columns={"outcome_code": "outcome", "q_candidate": "q_eu"}
    ).merge(settlement, on=["issue", "match_idx"], how="left", validate="many_to_one")
    prepared["settlement_available"] = prepared["settlement_available"].fillna(False).astype(bool)
    prepared["issue_anchor_ts"] = pd.to_datetime(prepared["issue_anchor_ts"], utc=True)
    prepared["fixture_decision_ts"] = pd.to_datetime(prepared["fixture_decision_ts"], utc=True)
    receipt = {
        "contract": CONTRACT_ID,
        "corrected_source_contract": _read_json(package / "FREEZE_RECEIPT.json").get("contract"),
        "upstream_files": upstream_hashes,
        "legacy_parity_source": legacy_source,
        "corrected_cells_sha256": stable_frame_sha(cells),
        "corrected_labels_sha256": stable_frame_sha(labels),
        "consumed_settlement_sha256": stable_frame_sha(settlement),
        "issues": int(cells["issue"].nunique()),
        "fixtures": int(cells[["issue", "match_idx"]].drop_duplicates().shape[0]),
        "cells": int(len(cells)),
        "years": list(YEARS),
        "chronology": "SOURCE_ISSUE_REGISTRY_YEAR + FIXTURE_RELATIVE_10H",
        "external_data_root_committed": False,
    }
    return prepared, settlement, receipt


def prepare_actions(cells: pd.DataFrame) -> pd.DataFrame:
    actions = prepare_match_actions(cells)
    timing = cells.drop_duplicates(["issue", "match_idx"])[
        [
            "issue", "match_idx", "fixture_decision_ts", "training_label_available_max_ts",
            "prediction_role", "issue_date_source",
        ]
    ]
    actions = actions.merge(timing, on=["issue", "match_idx"], validate="one_to_one")
    labels = cells.drop_duplicates(["issue", "match_idx"])[
        ["issue", "match_idx", "result_code", "winning_sp", "settlement_available", "settlement_quality"]
    ]
    actions = actions.merge(labels, on=["issue", "match_idx"], validate="one_to_one")
    return actions.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def _active_support(selected: pd.DataFrame, arm: str) -> pd.Series:
    if arm == "R0":
        return selected["baseline_support"]
    ranked = selected.sort_values(
        ["support_pressure", "match_idx"], ascending=[False, True], kind="stable"
    )
    activated = set(ranked.head(3)["match_idx"].astype(int))
    return pd.Series(
        np.where(selected["match_idx"].isin(activated), selected["qeu_support"], selected["baseline_support"]),
        index=selected.index,
    )


def construct_expert(
    actions: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    decisions: list[dict[str, Any]] = []
    tickets: list[dict[str, Any]] = []
    settled: list[dict[str, Any]] = []
    attribution: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for (issue, year, anchor), group in actions.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        selected = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
        ).head(N_LEGS).copy()
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
        for arm in ARMS:
            supports = _active_support(selected, arm)
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
            activated = active != selected["baseline_support"].astype(str).to_numpy()
            pressure_rank = selected["support_pressure"].rank(method="first", ascending=False).astype(int)
            for row, support, use_qeu, ok, rank in zip(
                selected.itertuples(), active, activated, included, pressure_rank, strict=True
            ):
                attribution.append(
                    {
                        "issue": str(issue), "issue_year": int(year), "arm": arm,
                        "match_idx": int(row.match_idx), "fixture_decision_ts": row.fixture_decision_ts,
                        "pressure_rank": int(rank), "support_pressure": float(row.support_pressure),
                        "baseline_support": str(row.baseline_support), "qeu_support": str(row.qeu_support),
                        "active_support": str(support), "qeu_activated": bool(use_qeu),
                        "result_code": str(row.result_code), "winning_sp": float(row.winning_sp),
                        "settlement_available": bool(row.settlement_available),
                        "realized_in_support": bool(ok),
                    }
                )
    return (
        pd.DataFrame(decisions), pd.DataFrame(tickets), pd.DataFrame(settled),
        pd.DataFrame(attribution), pd.DataFrame(coverage),
    )


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


def evaluate(
    settled: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    performance: list[dict[str, Any]] = []
    risk: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    bootstrap: list[dict[str, Any]] = []
    scopes: list[tuple[str, pd.DataFrame]] = [(str(year), settled[settled["issue_year"].eq(year)]) for year in YEARS]
    scopes.append(("ALL", settled))
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for scope, scoped in scopes:
        common = set(scoped.loc[scoped["arm"].eq("R0"), "issue"]) & set(
            scoped.loc[scoped["arm"].eq("R3"), "issue"]
        )
        scoped = scoped[scoped["issue"].isin(common)].copy()
        for arm, group in scoped.groupby("arm", sort=True):
            group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            pnl = group["pnl_cny"].to_numpy(float)
            performance.append(
                {
                    "scope": scope, "arm": arm, "issues": int(len(group)),
                    "stake_cny": float(group["stake_cny"].sum()),
                    "gross_cny": float(group["gross_cny"].sum()),
                    "pnl_cny": float(pnl.sum()),
                    "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum()) if len(group) else math.nan,
                    "hit_rate": float(group["hit"].mean()) if len(group) else math.nan,
                }
            )
            risk.append({"scope": scope, "arm": arm, **_risk(group)})
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            for order, (row, value) in enumerate(zip(group.itertuples(), capital, strict=True), start=1):
                paths.append(
                    {
                        "scope": scope, "arm": arm, "issue_order": order,
                        "issue": row.issue, "issue_year": int(row.issue_year),
                        "issue_anchor_ts": row.issue_anchor_ts, "pnl_cny": float(row.pnl_cny),
                        "capital_cny": float(value),
                    }
                )
        wide = scoped.pivot(index="issue", columns="arm", values="pnl_cny").dropna()
        delta = (wide["R3"] - wide["R0"]).to_numpy(float) if not wide.empty else np.array([])
        draws = np.array([
            delta[rng.integers(0, len(delta), len(delta))].sum() for _ in range(BOOTSTRAP_DRAWS)
        ]) if len(delta) else np.array([math.nan])
        bootstrap.append(
            {
                "scope": scope, "issues": int(len(delta)), "matched_lift_cny": float(delta.sum()),
                "ex_largest_lift_cny": float(delta.sum() - delta[np.argmax(np.abs(delta))]) if len(delta) else math.nan,
                "bootstrap_p025_cny": float(np.nanquantile(draws, 0.025)),
                "bootstrap_median_cny": float(np.nanquantile(draws, 0.5)),
                "bootstrap_p975_cny": float(np.nanquantile(draws, 0.975)),
            }
        )
    return pd.DataFrame(performance), pd.DataFrame(risk), pd.DataFrame(paths), pd.DataFrame(bootstrap)


def build_parity(
    repo_root: Path, actions: pd.DataFrame, tickets: pd.DataFrame, settled: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    legacy_root = repo_root / LEGACY_PACKAGE
    legacy_bundles = pd.read_parquet(legacy_root / "issue_bundles.parquet")
    legacy_bundles = legacy_bundles[legacy_bundles["arm"].isin(["R0", "R3_CORRECTED"])].copy()
    legacy_bundles["arm"] = legacy_bundles["arm"].replace({"R3_CORRECTED": "R3"})
    old = legacy_bundles.rename(columns={name: f"old_{name}" for name in legacy_bundles.columns if name not in ["issue", "arm"]})
    new = settled.rename(columns={name: f"new_{name}" for name in settled.columns if name not in ["issue", "arm"]})
    issue_parity = old.merge(new, on=["issue", "arm"], how="outer", indicator=True)
    for column in ["issue_year", "selected_match_ids", "support_json", "stake_cny", "gross_cny", "pnl_cny", "hit"]:
        left, right = f"old_{column}", f"new_{column}"
        if left in issue_parity and right in issue_parity:
            if column in {"stake_cny", "gross_cny", "pnl_cny"}:
                issue_parity[f"exact_{column}"] = np.isclose(
                    issue_parity[left], issue_parity[right], rtol=0, atol=1e-9, equal_nan=False
                )
            else:
                issue_parity[f"exact_{column}"] = issue_parity[left].eq(issue_parity[right])
    def canonical_support(value: object) -> str:
        if pd.isna(value):
            return ""
        parsed = json.loads(str(value))
        normalized = {
            str(key): "".join(item) if isinstance(item, list) else str(item)
            for key, item in parsed.items()
        }
        return json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    issue_parity["exact_support_json"] = (
        issue_parity["old_support_json"].map(canonical_support)
        == issue_parity["new_support_json"].map(canonical_support)
    ) & issue_parity["_merge"].eq("both")
    issue_parity["exact_issue_arm"] = issue_parity["_merge"].eq("both")
    for column in [
        "exact_issue_year", "exact_selected_match_ids", "exact_support_json", "exact_stake_cny",
        "exact_gross_cny", "exact_pnl_cny", "exact_hit",
    ]:
        issue_parity["exact_issue_arm"] &= issue_parity[column]
    old_tickets = pd.read_parquet(legacy_root / "ticket_receipts.parquet")
    old_tickets = old_tickets[old_tickets["arm"].isin(["R0", "R3_CORRECTED"])].copy()
    old_tickets["arm"] = old_tickets["arm"].replace({"R3_CORRECTED": "R3"})
    ticket_parity = old_tickets.merge(
        tickets, on=["issue", "arm", "ticket_ordinal"], how="outer",
        suffixes=("_old", "_new"), indicator=True,
    )
    ticket_parity["exact_ticket"] = (
        ticket_parity["_merge"].eq("both")
        & ticket_parity["ticket_code_old"].eq(ticket_parity["ticket_code_new"])
        & ticket_parity["units_old"].eq(ticket_parity["units_new"])
        & np.isclose(ticket_parity["stake_cny_old"], ticket_parity["stake_cny_new"], rtol=0, atol=1e-12)
    )
    old_actions = pd.read_parquet(legacy_root / "action_receipts.parquet")
    new_actions = actions.copy()
    action_parity = old_actions.merge(
        new_actions,
        on=["issue", "match_idx"], how="outer", suffixes=("_old", "_new"), indicator=True,
    )
    common = action_parity["_merge"].eq("both")
    action_parity["exact_year"] = common & action_parity["issue_year_old"].eq(action_parity["issue_year_new"])
    action_parity["exact_baseline_support"] = common & action_parity["baseline_support_old"].eq(action_parity["baseline_support_new"])
    action_parity["exact_qeu_support"] = common & action_parity["qeu_support_old"].eq(action_parity["qeu_support_new"])
    action_parity["exact_score_surface"] = common
    for outcome in OUTCOMES:
        action_parity["exact_score_surface"] &= np.isclose(
            action_parity[f"q_eu_{outcome}_old"], action_parity[f"q_eu_{outcome}_new"],
            rtol=0, atol=1e-12, equal_nan=False,
        ) & np.isclose(
            action_parity[f"q_line_{outcome}_old"], action_parity[f"q_line_{outcome}_new"],
            rtol=0, atol=1e-12, equal_nan=False,
        )
    summary = pd.DataFrame(
        [
            {
                "layer": "issue_arm", "old_rows": len(old), "new_rows": len(new),
                "common_rows": int(issue_parity["_merge"].eq("both").sum()),
                "exact_rows": int(issue_parity["exact_issue_arm"].sum()),
                "year_exact_rows": int(issue_parity["exact_issue_year"].sum()),
                "fixture_exact_rows": int(issue_parity["exact_selected_match_ids"].sum()),
                "support_exact_rows": int(issue_parity["exact_support_json"].sum()),
                "settlement_exact_rows": int(issue_parity["exact_pnl_cny"].sum()),
                "score_exact_rows": math.nan,
            },
            {
                "layer": "ticket", "old_rows": len(old_tickets), "new_rows": len(tickets),
                "common_rows": int(ticket_parity["_merge"].eq("both").sum()),
                "exact_rows": int(ticket_parity["exact_ticket"].sum()),
                "year_exact_rows": math.nan, "fixture_exact_rows": math.nan,
                "support_exact_rows": math.nan, "settlement_exact_rows": math.nan,
                "score_exact_rows": math.nan,
            },
            {
                "layer": "action", "old_rows": len(old_actions), "new_rows": len(actions),
                "common_rows": int(common.sum()),
                "exact_rows": int(
                    (action_parity["exact_year"] & action_parity["exact_baseline_support"]
                     & action_parity["exact_qeu_support"] & action_parity["exact_score_surface"]).sum()
                ),
                "year_exact_rows": int(action_parity["exact_year"].sum()),
                "fixture_exact_rows": math.nan,
                "support_exact_rows": int(
                    (action_parity["exact_baseline_support"] & action_parity["exact_qeu_support"]).sum()
                ),
                "settlement_exact_rows": math.nan,
                "score_exact_rows": int(action_parity["exact_score_surface"].sum()),
            },
        ]
    )
    return issue_parity, ticket_parity, action_parity, summary


def _downstream_inventory() -> pd.DataFrame:
    rows = [
        (319, "top2_n7_stable", "REBUILT", "match selection/year/path depend on legacy anchor"),
        (336, "qeu_support_depth", "REBUILT_FIXED_R0_R3", "accepted fixed-R3 definition retained"),
        (338, "qeu_threshold_n7", "REBUILT_FIXED_R3_ONLY", "absolute-threshold atlas remains exposed legacy diagnostic"),
        (340, "qeu_dynamic_r_n7", "NON_CANONICAL_NOT_REPLAYED", "negative dynamic-R branch is not a future expert"),
        (342, "value_veto_r3_n7", "NON_CANONICAL_NOT_REPLAYED", "negative veto branch is not inherited"),
        (345, "paired_value_r3_n7", "NON_CANONICAL_NOT_REPLAYED", "legacy paired-value branch is not inherited"),
        (348, "multin_top2_r0", "N7_ROW_NON_CANONICAL", "future cross-N comparison must consume corrected expert interface"),
        (349, "multin_fixed_rn", "N7_ROW_NON_CANONICAL", "future cross-N comparison must consume corrected expert interface"),
    ]
    return pd.DataFrame(rows, columns=["issue", "package", "disposition", "reason"])


def _decision(performance: pd.DataFrame, bootstrap: pd.DataFrame, parity: pd.DataFrame) -> dict[str, Any]:
    all_perf = performance[performance["scope"].eq("ALL")].set_index("arm")
    all_lift = bootstrap[bootstrap["scope"].eq("ALL")].iloc[0]
    common = parity[parity["_merge"].eq("both")]
    changed = int((~common["exact_pnl_cny"]).sum()) if len(common) else 0
    return {
        "contract": CONTRACT_ID,
        "verdict": "CORRECTED_R3_CANONICAL",
        "legacy_conclusion_changed": bool(changed > 0),
        "legacy_common_issue_arm_rows": int(len(common)),
        "legacy_changed_pnl_rows": changed,
        "corrected_r0_pnl_cny": float(all_perf.loc["R0", "pnl_cny"]),
        "corrected_r3_pnl_cny": float(all_perf.loc["R3", "pnl_cny"]),
        "corrected_r3_lift_r0_cny": float(all_lift["matched_lift_cny"]),
        "bootstrap_p025_cny": float(all_lift["bootstrap_p025_cny"]),
        "promotable_to_210": False,
        "evidence_boundary": "EXPOSED_HISTORICAL_CHRONOLOGY_SYNCHRONIZATION",
    }


def scientific_frames(repo_root: Path, data_root: Path) -> dict[str, Any]:
    cells, settlement, source = load_corrected_cells(repo_root, data_root)
    actions = prepare_actions(cells)
    decisions, tickets, settled, attribution, coverage = construct_expert(actions)
    performance, risk, paths, bootstrap = evaluate(settled)
    issue_parity, ticket_parity, action_parity, parity_summary = build_parity(
        repo_root, actions, tickets, settled
    )
    downstream = _downstream_inventory()
    decision = _decision(performance, bootstrap, issue_parity)
    return {
        "source": source, "actions": actions, "decisions": decisions, "tickets": tickets,
        "settled": settled, "attribution": attribution, "coverage": coverage,
        "performance": performance, "risk": risk, "paths": paths, "bootstrap": bootstrap,
        "issue_parity": issue_parity, "ticket_parity": ticket_parity,
        "action_parity": action_parity, "parity_summary": parity_summary,
        "downstream": downstream, "decision": decision,
    }


PACKAGE_FILES = {
    "source_receipt.json": "source",
    "action_receipts.parquet": "actions",
    "decisions.parquet": "decisions",
    "tickets.parquet": "tickets",
    "issue_bundles.parquet": "settled",
    "support_attribution.parquet": "attribution",
    "coverage_ledger.csv": "coverage",
    "performance.csv": "performance",
    "risk_diagnostics.csv": "risk",
    "capital_paths.csv": "paths",
    "bootstrap_lift.csv": "bootstrap",
    "legacy_issue_parity.parquet": "issue_parity",
    "legacy_ticket_parity.parquet": "ticket_parity",
    "legacy_action_parity.parquet": "action_parity",
    "parity_summary.csv": "parity_summary",
    "downstream_inventory.csv": "downstream",
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
        if not path.is_file() or sha256_file(path) != receipt["sha256"]:
            raise ContractError(f"manifest file mismatch: {relative}")
    implementation = manifest.get("implementation", {})
    if implementation != {
        "contract.py": sha256_file(Path(__file__).with_name("contract.py")),
        "pipeline.py": sha256_file(Path(__file__)),
    }:
        raise ContractError("implementation hashes do not match current code")
    expected_delivery = {
        "docs/research/Issue-366-N7-Chronology-Sync.md",
        "docs/research/figures/issue_366_corrected_n7_capital.png",
        "notebooks/research/n7-chronology-sync/n7_chronology_sync.ipynb",
    }
    if set(manifest.get("delivery", {})) != expected_delivery:
        raise ContractError("delivery receipt file set mismatch")
    for relative, expected_hash in manifest["delivery"].items():
        delivery_path = repo_root / relative
        if not delivery_path.is_file() or sha256_file(delivery_path) != expected_hash:
            raise ContractError(f"delivery hash mismatch: {relative}")
    upstream_checks = verify_corrected_source(
        repo_root,
        repo_root / CORRECTED_PACKAGE,
        data_root,
    )
    if not all(upstream_checks.values()):
        raise ContractError("#360 source-bound verifier did not pass")
    expected = scientific_frames(repo_root, data_root)
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
    decisions = expected["decisions"]
    tickets = expected["tickets"]
    groups = tickets.groupby(["issue", "arm"], observed=True)
    if not groups.size().eq(TICKETS).all() or not groups["ticket_code"].nunique().eq(TICKETS).all():
        raise ContractError("ticket groups are not exact 128-ticket Cartesian sets")
    if not groups["units"].sum().eq(FUNDED_UNITS).all() or not np.isclose(
        groups["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-12
    ).all():
        raise ContractError("ticket funding semantics mismatch")
    expected_keys = set(map(tuple, decisions[["issue", "arm"]].to_numpy()))
    if set(groups.groups) != expected_keys:
        raise ContractError("ticket group keys differ from decisions")
    bundles = expected["settled"]
    if not np.allclose(bundles["pnl_cny"], bundles["gross_cny"] - bundles["stake_cny"], rtol=0, atol=1e-9):
        raise ContractError("bundle PnL identity failed")
    report = repo_root / "docs/research/Issue-366-N7-Chronology-Sync.md"
    notebook = repo_root / "notebooks/research/n7-chronology-sync/n7_chronology_sync.ipynb"
    figure = repo_root / "docs/research/figures/issue_366_corrected_n7_capital.png"
    if not report.is_file() or CONTRACT_ID not in report.read_text(encoding="utf-8"):
        raise ContractError("research report is missing or not contract-bound")
    if not notebook.is_file() or not figure.is_file() or figure.stat().st_size <= 0:
        raise ContractError("notebook or figure delivery is missing")
    executed = nbformat.read(notebook, as_version=4)
    code_cells = [cell for cell in executed.cells if cell.cell_type == "code"]
    if not code_cells or any(cell.get("execution_count") is None for cell in code_cells):
        raise ContractError("notebook is not fully executed")
    return {
        "manifest": True,
        "source_bound_replay": True,
        "corrected_chronology": True,
        "strict_temporal_boundary": True,
        "fixed_r0_r3": True,
        "ticket_budget_and_payout": True,
        "settlement_reconciliation": True,
        "legacy_parity_receipts": True,
        "delivery_artifacts": True,
    }


def build_notebook_and_report(repo_root: Path, package: Path) -> None:
    notebook_path = repo_root / "notebooks/research/n7-chronology-sync/n7_chronology_sync.ipynb"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_markdown_cell("# Issue #366 — corrected-chronology fixed N7 expert"),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\nimport matplotlib.pyplot as plt\nROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/n7_chronology_sync'"
        ),
        nbformat.v4.new_code_cell(
            "performance=pd.read_csv(OUT/'performance.csv')\nrisk=pd.read_csv(OUT/'risk_diagnostics.csv')\nbootstrap=pd.read_csv(OUT/'bootstrap_lift.csv')\ncoverage=pd.read_csv(OUT/'coverage_ledger.csv')\nparity=pd.read_csv(OUT/'parity_summary.csv')\nissue_parity=pd.read_parquet(OUT/'legacy_issue_parity.parquet')\nperformance"
        ),
        nbformat.v4.new_code_cell("risk"),
        nbformat.v4.new_code_cell("bootstrap"),
        nbformat.v4.new_code_cell(
            "coverage_summary=(coverage.groupby(['issue_year','settlement_complete'],dropna=False).size().rename('issues').reset_index())\ncoverage_summary"
        ),
        nbformat.v4.new_code_cell("parity"),
        nbformat.v4.new_code_cell(
            "changed=issue_parity[(issue_parity['_merge']=='both') & (~issue_parity['exact_issue_arm'])]\nchanged[['issue','arm','old_issue_year','new_issue_year','exact_selected_match_ids','exact_support_json','exact_pnl_cny']].head(20)"
        ),
        nbformat.v4.new_code_cell(
            "paths=pd.read_csv(OUT/'capital_paths.csv')\nfig,ax=plt.subplots(figsize=(9,4))\nfor arm,g in paths[paths.scope.eq('ALL')].groupby('arm'):\n    ax.plot(g.issue_order,g.capital_cny,label=arm)\nax.axhline(100000,color='black',lw=.8); ax.legend(); ax.set_title('Corrected chronology N7 capital'); plt.show()"
        ),
    ]
    NotebookClient(nb, timeout=300, kernel_name="python3").execute(cwd=str(notebook_path.parent))
    nbformat.write(nb, notebook_path)
    performance = pd.read_csv(package / "performance.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    bootstrap = pd.read_csv(package / "bootstrap_lift.csv")
    coverage = pd.read_csv(package / "coverage_ledger.csv")
    parity = pd.read_csv(package / "parity_summary.csv")
    decision = _read_json(package / "decision.json")
    figure = repo_root / "docs/research/figures/issue_366_corrected_n7_capital.png"
    figure.parent.mkdir(parents=True, exist_ok=True)
    paths = pd.read_csv(package / "capital_paths.csv")
    fig, ax = plt.subplots(figsize=(9, 4))
    for arm, group in paths[paths["scope"].eq("ALL")].groupby("arm"):
        ax.plot(group["issue_order"], group["capital_cny"], label=arm)
    ax.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8)
    ax.legend()
    ax.set_title("Issue #366 corrected chronology N7 capital")
    fig.tight_layout()
    fig.savefig(figure, dpi=160)
    plt.close(fig)
    def table(frame: pd.DataFrame) -> str:
        rendered = frame.copy()
        for column in rendered.select_dtypes(include=["float"]).columns:
            rendered[column] = rendered[column].map(lambda value: f"{value:.4f}")
        header = "| " + " | ".join(rendered.columns) + " |"
        separator = "|" + "|".join("---" for _ in rendered.columns) + "|"
        rows = ["| " + " | ".join(map(str, row)) + " |" for row in rendered.itertuples(index=False, name=None)]
        return "\n".join([header, separator, *rows])
    report = f"""# Issue #366 — corrected chronology fixed N7 expert

Contract: `{CONTRACT_ID}`

## Decision

`{decision['verdict']}`. This is exposed historical chronology synchronization, not a deployable promotion. `promotable_to_210=false`.

Legacy scientific conclusion changed: **{decision['legacy_conclusion_changed']}**. Common legacy issue-arm rows with changed PnL: **{decision['legacy_changed_pnl_rows']} / {decision['legacy_common_issue_arm_rows']}**.

## Corrected performance

{table(performance)}

## Corrected path risk

{table(risk)}

## Matched R3 minus R0 stability

{table(bootstrap)}

The all-period point lift is positive, but the ex-largest lift and bootstrap lower bound are negative. The corrected R3 therefore remains a historical long-tail challenger, not a stable standalone promotion.

## Settlement coverage

{table(coverage.groupby(['issue_year', 'settlement_complete'], dropna=False).size().rename('issues').reset_index())}

The corrected registry contains **{coverage['issue'].nunique()}** issues. Exactly **{int(coverage['settlement_complete'].sum())}** are settled for both fixed arms; **{int((~coverage['settlement_complete']).sum())}** are excluded because at least one selected leg lacks trusted settlement.

## Old-to-corrected parity

{table(parity)}

## Evidence boundary

- Registry year and fixture-relative 10h decision time come from the source-bound #360 contract.
- R0 and fixed R3 definitions are unchanged; their realized fixtures/actions/settlement are rebuilt rather than presumed identical.
- 2022–2024 are exposed historical evidence. No threshold, R, seed, allocator, or router is tuned here.
- Legacy #340/#342/#345 branches remain non-canonical for future expert comparison unless separately rebuilt.
- #210 and #218 are unchanged.

## Artifacts

- Package: `results/n7_chronology_sync/`
- Notebook: `notebooks/research/n7-chronology-sync/n7_chronology_sync.ipynb`
- Figure: `docs/research/figures/issue_366_corrected_n7_capital.png`
"""
    (repo_root / "docs/research/Issue-366-N7-Chronology-Sync.md").write_text(report, encoding="utf-8")
    manifest_path = package / "MANIFEST.json"
    manifest = _read_json(manifest_path)
    delivery = {
        "docs/research/Issue-366-N7-Chronology-Sync.md": sha256_file(
            repo_root / "docs/research/Issue-366-N7-Chronology-Sync.md"
        ),
        "docs/research/figures/issue_366_corrected_n7_capital.png": sha256_file(figure),
        "notebooks/research/n7-chronology-sync/n7_chronology_sync.ipynb": sha256_file(notebook_path),
    }
    manifest["delivery"] = delivery
    atomic_write_json(manifest_path, manifest)
