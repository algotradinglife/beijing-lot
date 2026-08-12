#!/usr/bin/env python3
"""Render #192's manifest-covered Stage-4 decision charts from a package.

This is deliberately a package reader: it never opens the author checkpoint
or replays tickets.  Supply a fresh output directory when re-rendering so the
immutable settlement package itself remains unchanged.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "settle_bj192_stage4_portfolio_gate_b.py"


def runner():
    spec = importlib.util.spec_from_file_location("bj192_gate_b_chart_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load #192 Gate-B runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package, output = args.package.resolve(), args.output.resolve()
    if output.exists():
        raise RuntimeError("chart output must be a new directory")
    manifest = json.loads((package / "table_manifest.json").read_text(encoding="utf-8"))
    module = runner()
    names = ("issue_ledger", "sleeve_funding_ledger", "capital_summary", "holding_metrics", "baseline_lift")
    tables = {}
    for name in names:
        filename = manifest[name]["filename"]
        path = package / filename
        tables[name] = module.read_gzip(path) if filename.endswith(".gz") else module.read_csv(path)
    output.mkdir(parents=True)
    try:
        receipt = module.minimal_stage4_decision_artifacts(output, tables)
        (output / "render_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


if __name__ == "__main__":
    main()
