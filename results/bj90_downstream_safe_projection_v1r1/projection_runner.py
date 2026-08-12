#!/usr/bin/env python3
"""Project #90 evaluator output into a durable, outcome-safe downstream bundle."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = root()
GATE_A = ROOT / "results/bj90_gate_a_preoutcome_v4r1"
LEDGER = ROOT / "results/bj90_gate_b_target_ledger_v2r1"
EVALUATOR = ROOT / "results/bj90_gate_b_price_vectors_v4r1"
DIAGNOSTICS = ROOT / "results/bj90_gate_b_diagnostics_v4r2"
OUT = ROOT / "results/bj90_downstream_safe_projection_v1r1"

PROJECTION_FIELDS = [
    "match_id", "issue", "match_idx", "year", "fold", "deployed_method",
    "deployed_sp_3", "deployed_sp_1", "deployed_sp_0",
    "m2_conservative_sp_3", "m2_conservative_sp_1", "m2_conservative_sp_0",
]
FORBIDDEN_PROJECTION_SUBSTRINGS = (
    "target", "result", "score", "winning", "error", "coverage", "roi", "portfolio",
)
EXPECTED_OOS_ROWS = 100_589


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verified_manifest(bundle: Path) -> str:
    declared = json.loads((bundle / "SHA256SUMS.json").read_text())
    actual = {p.name: sha256(p) for p in bundle.iterdir() if p.is_file() and p.name != "SHA256SUMS.json"}
    if actual != declared:
        raise RuntimeError(f"input manifest mismatch: {bundle}")
    return sha256(bundle / "SHA256SUMS.json")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_projection(path: Path, rows: list[dict[str, str]]) -> None:
    # mtime=0 and filename="" make the gzip bytes deterministic for equal input.
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
            writer = csv.DictWriter(text, fieldnames=PROJECTION_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


def read_projection(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, mode="rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def copy_csv_with_lf(source: Path, destination: Path) -> None:
    """Preserve CSV cells and schema while making committed text byte-portable."""
    with source.open(newline="", encoding="utf-8") as input_handle, destination.open("w", newline="", encoding="utf-8") as output_handle:
        reader = csv.DictReader(input_handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"missing CSV header: {source}")
        writer = csv.DictWriter(output_handle, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(reader)


def project(row: dict[str, str]) -> dict[str, str]:
    method = row["deployed_method"]
    if method == "M0_EURO_10H":
        deployed_prefix = "m0"
    elif method == "M1_RIDGE_LOG_SP":
        deployed_prefix = "m1"
    else:
        raise RuntimeError(f"unknown deployed method: {method}")
    return {
        "match_id": row["match_id"], "issue": row["issue"], "match_idx": row["match_idx"],
        "year": row["year"], "fold": row["fold"], "deployed_method": method,
        "deployed_sp_3": row[f"{deployed_prefix}_3"], "deployed_sp_1": row[f"{deployed_prefix}_1"], "deployed_sp_0": row[f"{deployed_prefix}_0"],
        "m2_conservative_sp_3": row["m2_3"], "m2_conservative_sp_1": row["m2_1"], "m2_conservative_sp_0": row["m2_0"],
    }


def validate_projection(rows: list[dict[str, str]], source_rows: list[dict[str, str]]) -> None:
    if len(rows) != EXPECTED_OOS_ROWS:
        raise RuntimeError(f"unexpected projected row count: {len(rows)}")
    if any(set(row) != set(PROJECTION_FIELDS) for row in rows):
        raise RuntimeError("projection schema drift")
    unsafe = [field for field in PROJECTION_FIELDS if any(word in field.lower() for word in FORBIDDEN_PROJECTION_SUBSTRINGS)]
    if unsafe:
        raise RuntimeError(f"unsafe projection fields: {unsafe}")
    identities = [(row["match_id"], row["issue"], row["match_idx"], row["fold"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise RuntimeError("non-unique OOS projection identity")
    expected = [project(row) for row in source_rows]
    if rows != expected:
        raise RuntimeError("projection values differ from accepted evaluator output")


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage = Path(tempfile.mkdtemp(prefix="bj90-safe-projection-", dir=OUT.parent))
    try:
        manifests = {
            "gate_a_v4r1": verified_manifest(GATE_A),
            "ledger_v2r1": verified_manifest(LEDGER),
            "evaluator_v4r1": verified_manifest(EVALUATOR),
            "diagnostics_v4r2": verified_manifest(DIAGNOSTICS),
        }
        source_rows = read_csv(EVALUATOR / "oos_predictions.csv")
        projection_rows = [project(row) for row in source_rows]
        validate_projection(projection_rows, source_rows)
        projection_path = stage / "oos_prediction_vectors.csv.gz"
        write_projection(projection_path, projection_rows)
        # Read-after-write ensures compression did not alter rows or field names.
        validate_projection(read_projection(projection_path), source_rows)
        copy_csv_with_lf(EVALUATOR / "selector_decisions.csv", stage / "selector_decisions.csv")
        copy_csv_with_lf(EVALUATOR / "summary.csv", stage / "terminal_summary.csv")
        runner_hashes = {
            "gate_a_freeze_runner": sha256(GATE_A / "freeze_runner.py"),
            "gate_a_source_locator": sha256(GATE_A / "bj90_source_locator.py"),
            "ledger_runner": sha256(LEDGER / "ledger_runner.py"),
            "ledger_source_locator": sha256(LEDGER / "bj90_source_locator.py"),
            "evaluator_runner": sha256(EVALUATOR / "evaluation_runner.py"),
            "diagnostic_runner": sha256(DIAGNOSTICS / "diagnostic_runner.py"),
        }
        card = {
            "issue": 90,
            "stage": "DURABLE_OUTCOME_SAFE_DOWNSTREAM_OOS_PROJECTION",
            "contract": "prediction-only projection for blocked #91; no outcome-derived columns are exported",
            "oos_row_count": EXPECTED_OOS_ROWS,
            "projection_schema": PROJECTION_FIELDS,
            "forbidden_projection_substrings": FORBIDDEN_PROJECTION_SUBSTRINGS,
            "input_manifests": manifests,
            "runner_hashes": runner_hashes,
            "source_evaluator_output": "oos_predictions.csv; values are copied only after exact equality verification",
            "label": "RETROSPECTIVE_PRICE_TARGET; NOT_OBSERVED_PREBET_BJDC_QUOTE",
        }
        (stage / "projection_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
        shutil.copyfile(__file__, stage / "projection_runner.py")
        manifest = {p.name: sha256(p) for p in sorted(stage.iterdir()) if p.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        os.replace(stage, OUT)
        print(json.dumps({"output": str(OUT), "rows": EXPECTED_OOS_ROWS, "manifest_sha256": sha256(OUT / "SHA256SUMS.json")}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
