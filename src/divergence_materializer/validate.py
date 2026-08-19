"""Semantic and hash validation for an Issue #238 package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_package(root: Path) -> dict[str, object]:
    """Recompute the package's scientific invariants from persisted files."""

    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = root / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"package hash mismatch: {relative}")
    repository = Path(__file__).resolve().parents[2]
    for relative, expected in manifest.get("implementation_files", {}).items():
        path = repository / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"implementation hash mismatch: {relative}")
    summary = json.loads((root / "SUMMARY.json").read_text(encoding="utf-8"))
    inference = pd.read_parquet(root / "inference" / "relative_horizon_view.parquet")
    labels = pd.read_parquet(root / "development" / "labels_pre2024.parquet")

    forbidden = {
        "target_outcome",
        "home_goals",
        "away_goals",
        "score",
        "result_code",
        "winning_sp",
        "payout",
        "payout_factor",
    }
    overlap = forbidden & set(inference.columns)
    if overlap:
        raise ValueError(
            f"inference contains forbidden outcome fields: {sorted(overlap)}"
        )
    if len(inference) != int(summary["inference_cell_count"]):
        raise ValueError("inference row count does not match summary")
    if inference["q_bj_sp_available"].any() or inference["q_bj_sp_devig"].notna().any():
        raise ValueError(
            "historical package fabricated Beijing pre-event SP probability"
        )
    if labels["issue_year"].ge(2024).any():
        raise ValueError("sealed 2024+ label entered the development namespace")
    if not set(labels["temporal_role"]).issubset({"fit", "tune", "calibration"}):
        raise ValueError("development label has a non-development temporal role")

    keys = ["canonical_fixture_key", "snapshot_kind"]
    raw_sum = inference.groupby(keys, sort=False)["q_eu_raw_1x2"].sum()
    if not np.allclose(raw_sum.to_numpy(), 1.0, atol=1e-10):
        raise ValueError("raw European triplet sum failed")
    accepted = inference.loc[inference["mapping_accepted"]]
    mapped_sum = accepted.groupby(keys, sort=False)["q_eu_bjline"].sum()
    control_sum = accepted.groupby(keys, sort=False)["q_line_only_control"].sum()
    if not np.allclose(mapped_sum.to_numpy(), 1.0, atol=1e-10):
        raise ValueError("accepted translated triplet sum failed")
    if not np.allclose(control_sum.to_numpy(), 1.0, atol=1e-10):
        raise ValueError("line-only control triplet sum failed")
    unavailable = inference.loc[~inference["mapping_accepted"]]
    if unavailable["q_eu_bjline"].notna().any():
        raise ValueError("unaccepted mapping leaked into inference")
    if int(summary["sealed_label_rows_read"]) != 0:
        raise ValueError("summary reports sealed label access")
    return {
        "verdict": "PASS",
        "hashed_files": len(manifest["files"]),
        "implementation_files": len(manifest.get("implementation_files", {})),
        "inference_cells": int(len(inference)),
        "fixture_horizons": int(len(raw_sum)),
        "mapped_fixture_horizons": int(len(mapped_sum)),
        "development_label_fixtures": int(len(labels)),
        "sealed_label_rows": 0,
        "q_bj_sp_devig_cells": 0,
    }
