#!/usr/bin/env python3
"""Seal or verify a fresh Titan-only release without touching settlement data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.titan_clean.release import seal_titan_release, verify_titan_release  # noqa: E402
from src.titan_clean.store import TitanRosterStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        problems = verify_titan_release(args.data_root, release_id=args.release_id)
        if problems:
            raise SystemExit("\n".join(problems))
        print({"release_id": args.release_id, "status": "valid"})
        return
    store = TitanRosterStore.open(args.data_root)
    try:
        path = seal_titan_release(store, release_id=args.release_id)
    finally:
        store.close()
    print({"release": str(path)})


if __name__ == "__main__":
    main()
