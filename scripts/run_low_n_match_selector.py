#!/usr/bin/env python3
"""Build and document the frozen Issue #355 experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.low_n_match_selector.pipeline import (
    build_package,
    finalize_manifest,
    verify_package,
    write_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output = (args.output_dir or repo_root / "results/low_n_match_selector").resolve()
    result = build_package(repo_root, output, args.data_root, force=args.force)
    report, notebook, figures = write_analysis(repo_root, output, result)
    finalize_manifest(repo_root, output, [report, notebook, *figures])
    checks = verify_package(repo_root, output, args.data_root)
    print(json.dumps({"decision": result["decision"], "checks": checks}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
