#!/usr/bin/env python3
"""Semantic verifier for the Issue #334 result package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from neural_top2_residual.contract import FEATURE_COLUMNS, FORBIDDEN_FEATURE_TOKENS, FUNDED_UNITS, ISSUE_STAKE_CNY


def verify(output: Path) -> dict[str, bool]:
    hashes = json.loads((output / "SHA256SUMS.json").read_text())
    hash_ok = all(_sha256(output / name) == digest for name, digest in hashes.items())
    policies = pd.read_parquet(output / "issue_policies.parquet")
    allocations = pd.read_csv(output / "allocation_audit.csv")
    parity = pd.read_csv(output / "accepted_baseline_parity.csv")
    decision = json.loads((output / "decision.json").read_text())
    receipt = json.loads((output / "model_receipt.json").read_text())
    checks = {
        "hashes": hash_ok,
        "funded_units": bool(
            allocations["funded_units"].eq(FUNDED_UNITS).all()
        ),
        "matched_stake": bool(
            policies.loc[policies["settlement_status"].eq("SETTLED"), "stake_cny"].eq(ISSUE_STAKE_CNY).all()
        ),
        "minimum_support": bool(allocations["minimum_units"].ge(1).all()),
        "accepted_fallback_parity": bool(
            parity[["fixture_parity", "support_parity", "gross_parity"]].all().all()
        ),
        "no_2025": bool(policies["issue_year"].le(2024).all()),
        "feature_boundary": not any(
            any(token in name.lower() for token in FORBIDDEN_FEATURE_TOKENS)
            for name in FEATURE_COLUMNS
        ),
        "terminal_isolation_receipt": receipt["terminal_rows_seen_during_selection"] == 0,
        "notebook_executed": _notebook_executed(output.parents[1] / "notebooks/research/neural-top2-residual/neural_top2_residual.ipynb"),
        "decision_consistency": bool(decision["promotion"] == decision["unlock_210"]),
        "five_model_seeds": receipt["model_seeds"] == [33401, 33402, 33403, 33404, 33405],
    }
    return checks


def _notebook_executed(path: Path) -> bool:
    import nbformat

    notebook = nbformat.read(path, as_version=4)
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    return bool(code) and all(cell.execution_count is not None for cell in code)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/neural_top2_residual"))
    args = parser.parse_args()
    checks = verify(args.output_dir.resolve())
    print(json.dumps({"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}, indent=2, sort_keys=True))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
