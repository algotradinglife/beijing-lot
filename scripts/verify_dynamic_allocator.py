#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dynamic_allocator import verify_package  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path("results/dynamic_allocator"))
    args = parser.parse_args()
    print(json.dumps(verify_package(args.package), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
