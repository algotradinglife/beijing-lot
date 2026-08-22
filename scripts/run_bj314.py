#!/usr/bin/env python3
"""Run Issue #314 freeze or terminal settlement."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue314.experiment import freeze, settle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("freeze", "settle"))
    args = parser.parse_args()
    print(freeze() if args.stage == "freeze" else settle())


if __name__ == "__main__":
    main()
