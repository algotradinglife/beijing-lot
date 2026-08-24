#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.n7_chronology_sync.pipeline import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--package", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    package = (args.package or root / "results/n7_chronology_sync").resolve()
    checks = verify_package(root, package, args.data_root)
    print(json.dumps({"contract": "BJ-UNIFIED-N7-CHRONOLOGY-SYNC-001/v1", "checks": checks, "status": "PASS"}, indent=2))


if __name__ == "__main__":
    main()
