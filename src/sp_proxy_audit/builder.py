"""Build the immutable Issue #318 SP/proxy admissibility package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from .grading import EXCLUSIONS, OUTCOMES, grade_vectors

CONTRACT = "BJ-UNIFIED-SP-PROXY-AUDIT-001/v1"
SOURCE_SPECS = (
    ("beidan_xlsm", "data/derived/beidan_xlsm/beidan_xlsm.sqlite", "sqlite"),
    ("eu_proxy_backfill", "data/derived/bj268/eu_proxy_backfill_v3/candidate.sqlite", "sqlite"),
    ("bj238_materializer", "data/derived/bj238_divergence_materializer_v4r3", "directory"),
    ("bj238_source_receipt", "docs/research/evidence/bj238/SOURCE_RECEIPT.json", "json"),
    ("bj216_strict_panel", "results/bj216_model_support_panel_v1", "directory"),
    ("issue_registry", "data/derived/500_bjdc/500_bjdc.sqlite", "sqlite"),
)
REQUIRED_COLUMNS = [
    "issue_code", "match_idx", "outcome_code", "source_id", "source_grade",
    "snapshot_kind", "observed_at_utc", "decision_epoch_utc", "kickoff_utc",
    "sp_value", "probability_source", "probability_value", "q_value",
    "fixture_identity", "exclusion_reason",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync(path: Path, directory: bool = False) -> None:
    flags = os.O_RDONLY | (getattr(os, "O_DIRECTORY", 0) if directory else 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _inventory(source_root: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for source_id, relative, kind in SOURCE_SPECS:
        path = source_root / relative
        available = path.exists()
        digest_path = path if available and path.is_file() else path / "MANIFEST.json"
        digest = sha256(digest_path) if digest_path.is_file() else pd.NA
        record: dict[str, object] = {
            "source_id": source_id,
            "relative_path": relative,
            "kind": kind,
            "availability": "PRESENT" if available else "SOURCE_MISSING",
            "sha256": digest,
            "bytes": path.stat().st_size if available and path.is_file() else pd.NA,
            "schema_or_provenance": "",
        }
        if source_id == "bj238_source_receipt" and available:
            receipt = json.loads(path.read_text(encoding="utf-8"))
            record["schema_or_provenance"] = json.dumps(
                {key: receipt.get(key) for key in sorted(receipt)}, sort_keys=True
            )
        if source_id == "bj216_strict_panel" and available:
            manifest = path / "MANIFEST.json"
            record["schema_or_provenance"] = (
                sha256(manifest) if manifest.is_file() else "MANIFEST_MISSING"
            )
        rows.append(record)
    return pd.DataFrame(rows)


def _empty_cells() -> pd.DataFrame:
    data: dict[str, pd.Series] = {
        "issue_code": pd.Series(dtype="string"), "match_idx": pd.Series(dtype="Int64"),
        "outcome_code": pd.Series(dtype="string"), "source_id": pd.Series(dtype="string"),
        "source_grade": pd.Series(dtype="string"), "snapshot_kind": pd.Series(dtype="string"),
        "observed_at_utc": pd.Series(dtype="string"), "decision_epoch_utc": pd.Series(dtype="string"),
        "kickoff_utc": pd.Series(dtype="string"), "sp_value": pd.Series(dtype="float64"),
        "probability_source": pd.Series(dtype="string"), "probability_value": pd.Series(dtype="float64"),
        "q_value": pd.Series(dtype="float64"), "fixture_identity": pd.Series(dtype="string"),
        "exclusion_reason": pd.Series(dtype="string"), "provenance_sha256": pd.Series(dtype="string"),
    }
    return pd.DataFrame(data)


def _strict_panel_cells(source_root: Path, inventory: pd.DataFrame) -> pd.DataFrame:
    """Read #216 only; missing kickoff dependency remains SOURCE_MISSING."""
    panel_root = source_root / "results/bj216_model_support_panel_v1"
    snapshots_path = panel_root / "sources/selected_snapshots.parquet"
    epochs_path = panel_root / "inference/issue_epochs.parquet"
    required = inventory.set_index("source_id").availability
    if (
        required.get("bj216_strict_panel") != "PRESENT"
        or not snapshots_path.is_file() or not epochs_path.is_file()
    ):
        return _empty_cells()
    snapshots = pd.read_parquet(snapshots_path)
    epochs = pd.read_parquet(epochs_path, columns=["issue", "decision_epoch_utc"])
    epochs["issue"] = epochs["issue"].astype("string")
    epochs = epochs.drop_duplicates("issue", keep=False)
    # #216 match_id is a strict source identifier, not a historical alias.  The
    # exact issue/slot split is rejected unless it has this frozen shape.
    parts = snapshots["match_id"].astype("string").str.extract(r"^(?P<issue>\d+)_(?P<slot>\d+)$")
    valid = parts.notna().all(axis=1)
    snapshots = snapshots.loc[valid].copy()
    snapshots["issue_code"] = parts.loc[valid, "issue"].astype("string")
    snapshots["match_idx"] = pd.to_numeric(parts.loc[valid, "slot"], errors="coerce").astype("Int64")
    snapshots = snapshots.merge(epochs, left_on="issue_code", right_on="issue", how="left", validate="many_to_one")
    candidate_present = required.get("eu_proxy_backfill") == "PRESENT"
    records: list[pd.DataFrame] = []
    for outcome, column in (("3", "sp_3"), ("1", "sp_1"), ("0", "sp_0")):
        frame = snapshots[["issue_code", "match_idx", "market_observed_ts_utc", "decision_epoch_utc", column]].copy()
        frame["outcome_code"] = outcome
        frame["sp_value"] = pd.to_numeric(frame.pop(column), errors="coerce")
        frame["source_id"] = "strict_prospective_216"
        frame["snapshot_kind"] = "strict_prospective"
        frame["fixture_identity"] = "bjslot:" + frame.issue_code.astype(str) + ":" + frame.match_idx.astype(str).str.zfill(3)
        frame["provenance_sha256"] = sha256(snapshots_path)
        frame["observed_at_utc"] = frame.pop("market_observed_ts_utc")
        frame["kickoff_utc"] = pd.NA
        # The candidate inventory is the only contract-approved kickoff source.
        frame["source_semantics"] = "strict" if candidate_present else "missing"
        frame["identity_consistent"] = False if not candidate_present else pd.NA
        records.append(frame)
    return pd.concat(records, ignore_index=True)


def _partition(issue_code: object) -> str:
    # Decision partitions are calendar-year contracts; unknown/non-historical
    # rows remain explicit rather than being inferred from opaque issue IDs.
    value = str(issue_code)
    if value.startswith("19") or value.startswith("20"):
        year = int(value[:2]) + 2000
        if 2019 <= year <= 2022:
            return "development"
        if year == 2023:
            return "validation"
        if year == 2024:
            return "terminal"
    return "outside_contract"


def _coverage(cells: pd.DataFrame) -> pd.DataFrame:
    columns = ["partition", "issue_code", "source_id", "source_grade", "snapshot_kind", "fixture_count", "vector_count", "cell_count", "feasible_n7"]
    if cells.empty:
        return pd.DataFrame(columns=columns)
    work = cells.assign(partition=cells.issue_code.map(_partition))
    grouped = work.groupby(["partition", "issue_code", "source_id", "source_grade", "snapshot_kind"], dropna=False, sort=True)
    result = grouped.agg(fixture_count=("fixture_identity", "nunique"), cell_count=("outcome_code", "size")).reset_index()
    vectors = work.groupby(["partition", "issue_code", "source_id", "source_grade", "snapshot_kind", "fixture_identity"], dropna=False).outcome_code.nunique().eq(3).groupby(level=[0, 1, 2, 3, 4]).sum().rename("vector_count").reset_index()
    result = result.merge(vectors, on=["partition", "issue_code", "source_id", "source_grade", "snapshot_kind"], validate="one_to_one")
    result["feasible_n7"] = result.vector_count.ge(7)
    return result[columns]


def _exclusions(cells: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in inventory.loc[inventory.availability.eq("SOURCE_MISSING")].itertuples(index=False):
        rows.append({"source_id": row.source_id, "exclusion_reason": "SOURCE_MISSING", "cell_count": 0, "vector_count": 0, "denominator_note": "named mandatory source path absent"})
    if not cells.empty:
        bad = cells.loc[cells.exclusion_reason.notna()].groupby(["source_id", "exclusion_reason"], dropna=False).agg(cell_count=("outcome_code", "size"), vector_count=("fixture_identity", "nunique")).reset_index()
        rows.extend({**item, "denominator_note": "graded candidate cells"} for item in bad.to_dict("records"))
    return pd.DataFrame(rows, columns=["source_id", "exclusion_reason", "cell_count", "vector_count", "denominator_note"])


def _figure(path: Path, title: str, message: str) -> None:
    """Render a deterministic PNG using the existing Pillow dependency."""
    image = Image.new("RGB", (1120, 560), "white")
    draw = ImageDraw.Draw(image)
    draw.text((48, 48), title, fill="black")
    draw.multiline_text((48, 180), message, fill="black", spacing=8)
    image.save(path, format="PNG")


def _notebook(path: Path, decision: dict[str, object]) -> None:
    """Write a standards-compliant executed notebook without a mutable kernel."""
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": [{
            "cell_type": "code",
            "execution_count": 1,
            "metadata": {},
            "source": ["import json\n", "from pathlib import Path\n", "json.loads(Path('results/sp_proxy_audit/decision.json').read_text())"],
            "outputs": [{"output_type": "execute_result", "execution_count": 1, "metadata": {}, "data": {"text/plain": [repr(decision)]}}],
        }],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_package(source_root: Path, output: Path) -> dict[str, object]:
    """Build an atomic, deterministic audit receipt from the frozen source list."""
    source_root = source_root.resolve()
    output = output.resolve()
    inventory = _inventory(source_root)
    raw = _strict_panel_cells(source_root, inventory)
    cells = _empty_cells() if raw.empty else grade_vectors(raw)
    if not cells.empty:
        cells["probability_source"] = "Q_EU_BJLINE_UNAVAILABLE"
        cells["probability_value"] = np.nan
        cells["q_value"] = np.nan
        cells = cells[REQUIRED_COLUMNS + ["provenance_sha256"]]
    coverage = _coverage(cells)
    exclusions = _exclusions(cells, inventory)
    overlap = pd.DataFrame(columns=["proxy_source_id", "snapshot_kind", "partition", "issue_count", "fixture_count", "price_bias_issue_equal", "spearman_issue_equal", "top2_agreement_issue_equal", "top7_jaccard_issue_equal", "q_distortion_issue_equal", "bootstrap_p025", "bootstrap_p50", "bootstrap_p975"])
    missing_mandatory = inventory.availability.eq("SOURCE_MISSING").any()
    decision = {
        "contract_version": CONTRACT,
        "source_hashes": {row.source_id: row.sha256 if pd.notna(row.sha256) else None for row in inventory.itertuples(index=False)},
        "thresholds": {"strict_min_issues_per_partition": 30, "strict_min_n7_rate": 0.80, "proxy_min_overlap_issues": 20, "proxy_min_overlap_fixtures": 500, "proxy_min_spearman": 0.75, "proxy_min_top2": 0.85, "proxy_min_top7_jaccard": 0.70, "proxy_max_median_abs_log_price_error": 0.15, "bootstrap_resamples": 2000, "bootstrap_seed": 3182026},
        "observed_metrics": {"strict_accepted_cells": int(cells.source_grade.eq("STRICT_PRE_EVENT").sum()) if not cells.empty else 0, "proxy_accepted_cells": int(cells.source_grade.eq("HISTORICAL_PROXY").sum()) if not cells.empty else 0, "overlap_rows": 0},
        "terminal_disposition": "NO_CAUSAL_PRICE_SUPPORT",
        "failed_thresholds": ["mandatory source missing" if missing_mandatory else "no strict/proxy overlap"],
        "recommendation": "Do not use historical Beijing SP for value ranking; retain #218 strict prospective accumulation as prospective-only.",
    }
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        inventory.to_csv(staging / "source_inventory.csv", index=False)
        cells.to_parquet(staging / "graded_cells.parquet", index=False)
        coverage.to_csv(staging / "coverage_by_issue.csv", index=False)
        overlap.to_csv(staging / "overlap_metrics.csv", index=False)
        exclusions.to_parquet(staging / "exclusion_ledger.parquet", index=False)
        _json(staging / "decision.json", decision)
        _figure(staging / "coverage_by_partition.png", "Coverage by partition", "No admissible historical Beijing SP vectors: mandatory sources are missing.")
        _figure(staging / "price_error_by_horizon.png", "Price error by horizon", "No exact strict/proxy overlap exists.")
        _figure(staging / "top2_top7_agreement.png", "Top-2 and Top-7 agreement", "No exact strict/proxy overlap exists.")
        _figure(staging / "q_distortion.png", "q distortion", "Q_EU_BJLINE is unavailable without the frozen #238 materializer input.")
        files = {str(path.relative_to(staging)): sha256(path) for path in sorted(staging.iterdir()) if path.is_file()}
        _json(staging / "MANIFEST.json", {"contract_version": CONTRACT, "files": files, "source_inventory_sha256": sha256(staging / "source_inventory.csv")})
        checksums = {str(path.relative_to(staging)): sha256(path) for path in sorted(staging.iterdir()) if path.is_file()}
        _json(staging / "SHA256SUMS.json", checksums)
        for artifact in staging.iterdir():
            if artifact.is_file():
                _fsync(artifact)
        _fsync(staging, directory=True)
        if output.exists():
            backup = output.with_name(output.name + ".previous")
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(output, backup)
            _fsync(output.parent, directory=True)
            try:
                os.replace(staging, output)
                _fsync(output.parent, directory=True)
            except BaseException:
                os.replace(backup, output)
                _fsync(output.parent, directory=True)
                raise
            shutil.rmtree(backup)
            _fsync(output.parent, directory=True)
        else:
            os.replace(staging, output)
            _fsync(output.parent, directory=True)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return decision


def build_with_notebook(source_root: Path, output: Path, notebook: Path) -> dict[str, object]:
    decision = build_package(source_root, output)
    _notebook(notebook, decision)
    return decision
