#!/usr/bin/env python3
"""Build or independently replay a saved Nowscore capture bundle, without network."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.settlement_storage import validate_settlement_storage
from src.nowscore_settlement import build_database, canonical  # noqa: E402


def main(argv=None):
    """Read explicit saved inputs and build one new database; never fetch or overwrite."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("build",))
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--mountpoint", type=Path)
    a = p.parse_args(argv)
    validate_settlement_storage(a.data_root, [a.output], mountpoint=a.mountpoint)
    print(canonical(build_database(a.run_root, a.output)))


if __name__ == "__main__":
    main()
