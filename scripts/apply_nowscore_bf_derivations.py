#!/usr/bin/env python3
"""Thin command entry point for approved Nowscore BF derivations."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.nowscore_bf_derivations import main  # noqa: E402

if __name__ == '__main__':
    main()
