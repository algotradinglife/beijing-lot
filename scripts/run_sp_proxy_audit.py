#!/usr/bin/env python3
"""Replay the frozen Issue #318 SP/proxy admissibility audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.sp_proxy_audit.builder import build_with_notebook  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "results/sp_proxy_audit")
    parser.add_argument("--notebook", type=Path, default=ROOT / "notebooks/research/sp-proxy-audit/sp_proxy_audit.ipynb")
    args = parser.parse_args()
    print(json.dumps(build_with_notebook(args.source_root, args.output, args.notebook), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
