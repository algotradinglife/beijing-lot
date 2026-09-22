"""End-to-end Issue #238 package builder."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.source_schema.publication import (
    atomic_publish_directory,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_parquet,
)

from src.issue_codes import SOURCE_ISSUE_DATE_SOURCE

from .contract import CONTRACT_VERSION, HORIZONS, MODEL_VERSION, OUTCOMES
from .data import (
    attach_native_labels,
    load_development_labels,
    load_issue_roles,
    load_proxy_panel,
)
from .model import HorizonModel, fit_horizon_models, predict_panel


@dataclass(frozen=True)
class BuildInputs:
    candidate_sqlite: Path
    proxy_root: Path
    label_sqlite: Path
    verification_json: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _model_receipt(models: list[HorizonModel]) -> dict[str, object]:
    horizons: list[dict[str, object]] = []
    for fitted in models:
        record: dict[str, object] = {
            "horizon": fitted.horizon,
            "accepted_nonzero_mapping": fitted.accepted,
        }
        for name, pipeline in (
            ("line_only_control", fitted.control),
            ("eu_plus_line_logit", fitted.experimental),
        ):
            transform = pipeline.named_steps["features"]
            model = pipeline.named_steps["model"]
            record[name] = {
                "classes": [str(value) for value in model.classes_],
                "feature_names": [
                    str(value) for value in transform.get_feature_names_out()
                ],
                "coef": model.coef_.tolist(),
                "intercept": model.intercept_.tolist(),
                "n_iter": model.n_iter_.tolist(),
            }
        horizons.append(record)
    return {
        "model_version": MODEL_VERSION,
        "library": "scikit-learn LogisticRegression",
        "fixed_model_selection": "2022 tune; untouched 2023 directional confirmation",
        "horizons": horizons,
    }


def _implementation_receipt() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    files = [
        root / "src" / "divergence_materializer" / name
        for name in ("__init__.py", "builder.py", "contract.py", "data.py", "model.py")
    ]
    files.append(root / "scripts" / "run_bj238_divergence_materializer.py")
    return {str(path.relative_to(root)): _sha256(path) for path in files}


def _long_inference(predicted: pd.DataFrame) -> pd.DataFrame:
    identity = [
        "canonical_fixture_key",
        "issue_code",
        "match_idx",
        "snapshot_kind",
        "issue_anchor_ts",
        "issue_year",
        "issue_date_source",
        "temporal_role",
        "native_handicap_line_raw",
        "native_handicap_line",
        "native_line_supported",
        "handicap_norm_source",
        "n_available_books",
        "causal_grade",
        "mapping_accepted",
        "mapping_status",
        "model_version",
    ]
    frames: list[pd.DataFrame] = []
    for code in OUTCOMES:
        frame = predicted[identity].copy()
        frame["outcome_code"] = code
        frame["q_eu_raw_1x2"] = predicted[f"q_eu_{code}"]
        frame["q_line_only_control"] = predicted[f"q_line_control_{code}"]
        frame["q_eu_bjline"] = predicted[f"q_eu_bjline_{code}"]
        frame["q_eu_bjline_candidate_diagnostic"] = predicted[
            f"q_eu_bjline_candidate_{code}"
        ]
        frame["eu_vs_line_divergence"] = predicted[f"divergence_{code}"]
        frame["q_bj_sp_devig"] = np.nan
        frame["q_bj_sp_available"] = False
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True)
    result["outcome_code"] = pd.Categorical(
        result["outcome_code"], categories=list(OUTCOMES), ordered=True
    )
    return result.sort_values(
        ["issue_code", "match_idx", "snapshot_kind", "outcome_code"],
        kind="mergesort",
    ).reset_index(drop=True)


def _issue_capacity(predicted: pd.DataFrame) -> pd.DataFrame:
    available = predicted.loc[predicted["mapping_accepted"]].copy()
    capacity = (
        available.groupby(["temporal_role", "issue_code", "snapshot_kind"], sort=True)[
            "canonical_fixture_key"
        ]
        .nunique()
        .rename("available_fixtures")
        .reset_index()
    )
    capacity["feasible_n7"] = capacity["available_fixtures"].ge(7)
    return capacity


def _support_summary(
    panel: pd.DataFrame, predicted: pd.DataFrame, capacity: pd.DataFrame
) -> pd.DataFrame:
    base = (
        panel.groupby(["temporal_role", "snapshot_kind"], sort=True)
        .agg(
            issues=("issue_code", "nunique"),
            fixtures=("canonical_fixture_key", "nunique"),
            with_native_line=("native_handicap_line", "count"),
            with_supported_native_line=("native_line_supported", "sum"),
        )
        .reset_index()
    )
    accepted = (
        predicted.loc[predicted["mapping_accepted"]]
        .groupby(["temporal_role", "snapshot_kind"], sort=True)
        .agg(
            mapped_fixtures=("canonical_fixture_key", "nunique"),
            nonzero_mapped_fixtures=(
                "native_handicap_line",
                lambda value: int(value.ne(0).sum()),
            ),
        )
        .reset_index()
    )
    n7 = (
        capacity.groupby(["temporal_role", "snapshot_kind"], sort=True)
        .agg(
            capacity_issues=("issue_code", "nunique"),
            feasible_n7_issues=("feasible_n7", "sum"),
            median_available_fixtures=("available_fixtures", "median"),
            p10_available_fixtures=(
                "available_fixtures",
                lambda value: float(value.quantile(0.10)),
            ),
        )
        .reset_index()
    )
    return base.merge(
        accepted,
        on=["temporal_role", "snapshot_kind"],
        how="left",
    ).merge(n7, on=["temporal_role", "snapshot_kind"], how="left")


def _divergence_profile(inference: pd.DataFrame) -> pd.DataFrame:
    available = inference.loc[inference["eu_vs_line_divergence"].notna()].copy()
    grouped = available.groupby(
        [
            "temporal_role",
            "snapshot_kind",
            "native_handicap_line",
            "outcome_code",
        ],
        observed=True,
        sort=True,
    )["eu_vs_line_divergence"]
    return grouped.agg(
        cells="size",
        mean="mean",
        mean_abs=lambda value: float(value.abs().mean()),
        q10=lambda value: float(value.quantile(0.10)),
        median="median",
        q90=lambda value: float(value.quantile(0.90)),
    ).reset_index()


def _development_label_table(development: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "canonical_fixture_key",
        "issue_code",
        "match_idx",
        "temporal_role",
        "issue_year",
        "home_goals",
        "away_goals",
        "native_handicap_line",
        "target_outcome",
    ]
    return (
        development.loc[development["target_outcome"].notna(), columns]
        .drop_duplicates(["canonical_fixture_key"])
        .sort_values(["issue_code", "match_idx"], kind="mergesort")
        .reset_index(drop=True)
    )


def _frame_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_receipt(
    inputs: BuildInputs, roles: pd.DataFrame, labels: pd.DataFrame
) -> dict[str, object]:
    verification = json.loads(inputs.verification_json.read_text(encoding="utf-8"))
    candidate_hash = str(verification.get("candidate_sqlite_sha256", ""))
    parquet_hash = str(verification.get("parquet_manifest_sha256", ""))
    manifest_path = inputs.proxy_root / "MANIFEST.json"
    if _sha256(manifest_path) != parquet_hash:
        raise ValueError("#268 proxy manifest does not match its accepted verification")
    return {
        "candidate_sqlite": str(inputs.candidate_sqlite),
        "candidate_sqlite_sha256_from_accepted_268_verification": candidate_hash,
        "proxy_manifest_sha256": parquet_hash,
        "label_source": str(inputs.label_sqlite),
        "consumed_development_label_rows": int(len(labels)),
        "consumed_development_labels_sha256": _frame_sha256(labels),
        "issue_year_source": SOURCE_ISSUE_DATE_SOURCE,
        "consumed_issue_roles_sha256": _frame_sha256(roles),
        "label_boundary": "allow-listed pre-2024 issues only",
    }


def build_package(inputs: BuildInputs, target: Path) -> dict[str, object]:
    """Build one immutable #238 experiment package."""

    roles = load_issue_roles(inputs.candidate_sqlite)
    panel = load_proxy_panel(inputs.proxy_root, roles)
    development_issues = set(
        roles.loc[
            roles["temporal_role"].isin(["fit", "tune", "calibration"]),
            "issue_code",
        ].astype(str)
    )
    labels = load_development_labels(inputs.label_sqlite, development_issues)
    development = attach_native_labels(panel, labels)
    models = fit_horizon_models(development)
    predicted = predict_panel(panel, models)
    inference = _long_inference(predicted)
    capacity = _issue_capacity(predicted)
    support = _support_summary(panel, predicted, capacity)
    divergence_profile = _divergence_profile(inference)
    metrics = pd.concat([model.metrics for model in models], ignore_index=True)
    bootstrap = pd.concat([model.bootstrap for model in models], ignore_index=True)
    development_labels = _development_label_table(development)
    source_receipt = _source_receipt(inputs, roles, labels)
    accepted_horizons = [model.horizon for model in models if model.accepted]
    disposition = (
        "READY_FOR_209_PI_MODELABILITY_REVIEW"
        if accepted_horizons
        else "UNRECOVERABLE_WITH_CURRENT_HISTORICAL_SOURCES"
    )

    def populate(staging: Path) -> None:
        atomic_write_parquet(
            inference, staging / "inference" / "relative_horizon_view.parquet"
        )
        atomic_write_parquet(
            inference.iloc[0:0].assign(
                common_epoch_unavailable_reason=pd.Series(dtype="string")
            ),
            staging / "inference" / "common_epoch_view.parquet",
        )
        atomic_write_parquet(
            development_labels, staging / "development" / "labels_pre2024.parquet"
        )
        atomic_write_csv(metrics, staging / "analysis" / "mapping_metrics.csv")
        atomic_write_csv(bootstrap, staging / "analysis" / "issue_bootstrap.csv")
        atomic_write_csv(capacity, staging / "analysis" / "issue_capacity.csv")
        atomic_write_csv(support, staging / "analysis" / "support_summary.csv")
        atomic_write_csv(
            divergence_profile, staging / "analysis" / "divergence_profile.csv"
        )
        atomic_write_csv(roles, staging / "analysis" / "issue_roles.csv")
        atomic_write_json(staging / "MODEL_RECEIPT.json", _model_receipt(models))
        atomic_write_json(staging / "SOURCE_RECEIPT.json", source_receipt)
        summary = {
            "contract": CONTRACT_VERSION,
            "disposition": disposition,
            "accepted_nonzero_mapping_horizons": accepted_horizons,
            "rejected_nonzero_mapping_horizons": [
                horizon for horizon in HORIZONS if horizon not in accepted_horizons
            ],
            "frozen_issue_count": int(len(roles)),
            "proxy_fixture_horizon_count": int(len(panel)),
            "inference_cell_count": int(len(inference)),
            "development_label_fixture_count": int(len(development_labels)),
            "sealed_label_rows_read": 0,
            "q_bj_sp_devig_available_cells": 0,
            "common_epoch_rows": 0,
            "scientific_boundary": (
                "line-only control is a coarse handicap prior, not a de-vigged Beijing SP probability"
            ),
        }
        atomic_write_json(staging / "SUMMARY.json", summary)
        hashes = {
            str(path.relative_to(staging)): _sha256(path)
            for path in sorted(staging.rglob("*"))
            if path.is_file()
        }
        atomic_write_json(
            staging / "MANIFEST.json",
            {
                "contract": CONTRACT_VERSION,
                "model_version": MODEL_VERSION,
                "implementation_files": _implementation_receipt(),
                "files": hashes,
                "summary": summary,
            },
        )

    atomic_publish_directory(target, populate)
    return json.loads((target / "SUMMARY.json").read_text(encoding="utf-8"))
