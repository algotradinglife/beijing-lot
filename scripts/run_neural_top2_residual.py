#!/usr/bin/env python3
"""Run the Issue #334 neural Top-2 residual experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from neural_top2_residual.pipeline import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--no-reuse-models", action="store_true")
    args = parser.parse_args()
    output = args.output_dir or args.repo_root / "results/neural_top2_residual"
    decision = run_experiment(args.repo_root, output, reuse_models=not args.no_reuse_models)
    print(json.dumps(decision, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
