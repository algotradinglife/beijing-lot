#!/usr/bin/env python3
"""Replay the frozen Issue #318 SP/proxy admissibility audit."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sp_proxy_audit.builder import build_package  # noqa: E402
from src.sp_proxy_audit.notebook import build_notebook  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("BEIJING_LOT_DATA_ROOT", ROOT)),
        help="portable root containing data/derived; defaults to BEIJING_LOT_DATA_ROOT or repository root",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/sp_proxy_audit")
    parser.add_argument(
        "--notebook",
        type=Path,
        default=ROOT / "notebooks/research/sp-proxy-audit/sp_proxy_audit.ipynb",
    )
    args = parser.parse_args()
    decision = build_package(ROOT, args.data_root, args.output)
    build_notebook(ROOT, args.notebook)
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
