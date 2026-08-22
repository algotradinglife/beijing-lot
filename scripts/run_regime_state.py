#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.regime_state import build_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("results/regime_state"))
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_package(ROOT, ROOT / args.output, args.data_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
