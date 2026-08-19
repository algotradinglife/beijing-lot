#!/usr/bin/env python3
"""Materialize #236's historical European 1X2 proxy views from raw workbook.

The provider's initial/10h/1h labels are emitted only as
RETROSPECTIVE_RELATIVE_PROXY; no row is Beijing SP or strict-forward evidence.
Raw workbook bytes remain external immutable evidence and are hash-bound in the
emitted manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eu_odds_timeseries.materialize import materialize_proxy_view  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--chunksize", type=int, default=100_000)
    args = parser.parse_args()
    workbook = args.data_root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
    target = args.out or args.data_root / "derived" / "bj236" / "eu_odds_proxy_v1"
    before = sha256(workbook)
    summary = materialize_proxy_view(workbook, target, source_sha256=before, chunksize=args.chunksize)
    print(f"BUILT {target}")
    for key in sorted(summary):
        print(f"{key}: {summary[key]}")
    print(f"source_sha256: {before}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
