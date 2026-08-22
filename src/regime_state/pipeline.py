"""End-to-end builder and verifier for Issue #330."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.top2_factorial.pipeline import locate_data_root, sha256_file, stable_frame_sha

from .contract import CONTRACT, DECISIONS, MARKET_FEATURES, TARGETS, YEARS
from .data import (
    add_lagged_state,
    attach_expert_targets,
    fixture_panel,
    issue_market_panel,
    load_market_rows,
)
from .model import (
    block_bootstrap_increment,
    chronological_predictions,
    decide,
    model_lag_columns,
    persistence_diagnostics,
    prediction_metrics,
)
from .reporting import annual_summary, write_figures, write_notebook, write_report


def _frame_sha(frame: pd.DataFrame) -> str:
    return stable_frame_sha(frame, list(frame.columns))


def _chronology_receipt(state: pd.DataFrame, lag_columns: list[str]) -> dict:
    anchor = pd.to_datetime(state.issue_anchor_ts, utc=True)
    timestamp_columns = [
        column for column in state.columns if column.endswith("_last_observation_ts")
    ]
    failures = 0
    comparisons = 0
    for column in timestamp_columns:
        observed = pd.to_datetime(state[column], utc=True, errors="coerce")
        usable = observed.notna()
        comparisons += int(usable.sum())
        failures += int((observed[usable] >= anchor[usable]).sum())
    model_lags = model_lag_columns(lag_columns)
    same_anchor_equal = all(
        len(group[model_lags].drop_duplicates()) == 1
        for _, group in state.groupby("issue_anchor_ts") if len(group) > 1
    )
    return {
        "independent_unit": "BEIJING_ISSUE",
        "rows": len(state), "unique_issue_codes": int(state.issue_code.nunique()),
        "anchor_is_unique": bool(pd.to_datetime(state.issue_anchor_ts, utc=True).is_unique),
        "same_anchor_groups_share_lagged_state": bool(same_anchor_equal),
        "last_observation_comparisons": comparisons,
        "same_or_future_timestamp_failures": failures,
        "lag_feature_count": len(lag_columns),
        "model_lag_feature_count": len(model_lags),
        "model_feature_columns": [*MARKET_FEATURES, *model_lags],
        "prohibited_feature_absent": not any(
            column in {"issue_year", "issue_code", "result_code", "winning_sp", "final_sp"}
            for column in [*MARKET_FEATURES, *model_lags]
        ),
    }


def _state_schema(lag_columns: list[str]) -> dict:
    return {
        "contract": CONTRACT, "independent_unit": "issue_code",
        "ordering": ["issue_anchor_ts", "issue_code"],
        "current_pre_event_features": list(MARKET_FEATURES),
        "lagged_features": lag_columns,
        "targets": list(TARGETS),
        "prohibited_model_inputs": [
            "issue_year", "issue_code", "calendar_year", "result_code", "winning_sp",
            "same_issue_realized_metric", "future_settlement", "final_official_sp",
        ],
    }


def build_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict:
    repo_root, output = repo_root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_root = locate_data_root(repo_root, data_root)
    market_rows, market_path = load_market_rows(source_root)
    settlement_path = source_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    fixtures = fixture_panel(market_rows, settlement_path)
    issue_panel = attach_expert_targets(repo_root, issue_market_panel(fixtures))
    state, lag_columns = add_lagged_state(issue_panel)
    chronology = _chronology_receipt(state, lag_columns)
    if (
        chronology["same_or_future_timestamp_failures"]
        or not chronology["same_anchor_groups_share_lagged_state"]
    ):
        raise ValueError("lagged-state chronology failed")

    state_path = output / "state_ledger.parquet"
    state.to_parquet(state_path, index=False)
    persisted_state = pd.read_parquet(state_path)

    freeze = {
        "issue": 330, "contract": CONTRACT, "years": list(YEARS),
        "excluded_years": [2025, 2026], "primary_horizon": "10h",
        "market_source": str(market_path), "market_source_sha256": sha256_file(market_path),
        "settlement_source": str(settlement_path),
        "settlement_source_sha256": sha256_file(settlement_path),
        "dynamic_allocator_manifest_sha256": sha256_file(
            repo_root / "results/dynamic_allocator/MANIFEST.json"
        ),
        "top2_stable_manifest_sha256": sha256_file(
            repo_root / "results/top2_n7_stable/MANIFEST.json"
        ),
        "state_sha256": _frame_sha(persisted_state),
        "state_file_sha256": sha256_file(state_path),
        "market_features": list(MARKET_FEATURES), "targets": list(TARGETS),
        "lag_features": lag_columns, "calendar_year_is_model_feature": False,
        "future_outcomes_opened": False,
    }
    (output / "freeze_receipt.json").write_text(
        json.dumps(freeze, indent=2, sort_keys=True) + "\n"
    )
    (output / "chronology_receipt.json").write_text(
        json.dumps(chronology, indent=2, sort_keys=True) + "\n"
    )
    (output / "state_schema.json").write_text(
        json.dumps(_state_schema(lag_columns), indent=2, sort_keys=True) + "\n"
    )
    predictions, model_receipts = chronological_predictions(state, lag_columns)
    metrics = prediction_metrics(predictions)
    bootstrap = block_bootstrap_increment(predictions)
    persistence, window_sensitivity = persistence_diagnostics(state)
    decision = decide(state, metrics, persistence, bootstrap)

    predictions.to_parquet(output / "oof_predictions.parquet", index=False)
    metrics.to_csv(output / "prediction_metrics.csv", index=False)
    bootstrap.to_csv(output / "bootstrap_increment.csv", index=False)
    persistence.to_csv(output / "persistence.csv", index=False)
    window_sensitivity.to_csv(output / "window_sensitivity.csv", index=False)
    annual_summary(state).to_csv(output / "annual_summary.csv", index=False)
    (output / "model_receipt.json").write_text(
        json.dumps(model_receipts, separators=(",", ":"), sort_keys=True) + "\n"
    )
    (output / "decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n"
    )
    write_report(repo_root, state, metrics, bootstrap, decision)
    write_figures(repo_root, state, metrics)
    write_notebook(repo_root)

    files = {}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name not in {"MANIFEST.json", "SHA256SUMS.json"}:
            files[path.name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    (output / "MANIFEST.json").write_text(
        json.dumps({"contract": CONTRACT, "files": files}, indent=2, sort_keys=True) + "\n"
    )
    sums = {
        path.name: sha256_file(path) for path in sorted(output.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (output / "SHA256SUMS.json").write_text(
        json.dumps(sums, indent=2, sort_keys=True) + "\n"
    )
    return decision


def verify_package(package: Path) -> dict:
    package = package.resolve()
    freeze = json.loads((package / "freeze_receipt.json").read_text())
    chronology = json.loads((package / "chronology_receipt.json").read_text())
    schema = json.loads((package / "state_schema.json").read_text())
    decision = json.loads((package / "decision.json").read_text())
    sums = json.loads((package / "SHA256SUMS.json").read_text())
    state = pd.read_parquet(package / "state_ledger.parquet")
    predictions = pd.read_parquet(package / "oof_predictions.parquet")
    checks = {
        "hashes": all(
            (package / name).is_file() and sha256_file(package / name) == digest
            for name, digest in sums.items()
        ),
        "state_freeze": _frame_sha(state) == freeze["state_sha256"],
        "state_file_freeze": sha256_file(package / "state_ledger.parquet") == freeze["state_file_sha256"],
        "one_issue_one_row": len(state) == state.issue_code.nunique(),
        "chronology": chronology["same_or_future_timestamp_failures"] == 0,
        "same_anchor_state": chronology["same_anchor_groups_share_lagged_state"] is True,
        "no_future_year": int(state.issue_year.max()) == 2024,
        "no_prohibited_feature": chronology["prohibited_feature_absent"] is True,
        "schema_no_year_feature": "issue_year" not in schema["current_pre_event_features"],
        "oof_prediction_years": set(predictions.issue_year.unique()).issubset({2022, 2023, 2024}),
        "decision": decision["disposition"] in DECISIONS,
        "no_promotion": decision["promotion"] is False and decision["unlock_210"] is False,
        "finite_predictions": bool(np.isfinite(predictions.prediction).all()),
    }
    result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
    if result["status"] != "PASS":
        raise ValueError(json.dumps(result, sort_keys=True))
    return result
