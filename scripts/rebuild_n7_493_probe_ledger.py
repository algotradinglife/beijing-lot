#!/usr/bin/env python3
"""Thin entry point: rebuild the #493 probe request ledger from recoverable evidence.

Reusable logic lives in src/n7_493_probe_analysis.py. Importing this script does
nothing; it never issues a request.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.n7_493_probe_analysis import (  # noqa: E402
    rebuild_request_ledger, write_ledger,
)

OUT = ROOT / "results/data_collection/n7_493_3in1_probe_v1"
ENTRY = "https://live.nowscore.com/odds/3in1Odds.aspx"
URLS = {
    "base_no_company": f"{ENTRY}?id=3061587",
    "company_1": f"{ENTRY}?companyid=1&id=3061587",
    "company_0": f"{ENTRY}?companyid=0&id=3061587",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    manifest_path = args.out / "manifest.json"
    surviving = (json.loads(manifest_path.read_text(encoding="utf-8"))
                 if manifest_path.exists() else None)
    ledger, provenance = rebuild_request_ledger(args.out, surviving, URLS)
    write_ledger(ledger, args.out / "requests.jsonl")
    (args.out / "ledger_provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(provenance, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
