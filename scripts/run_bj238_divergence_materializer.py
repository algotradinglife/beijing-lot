#!/usr/bin/env python3
"""Run Issue #238's issue-blocked chronological mapping experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.divergence_materializer import BuildInputs, build_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sqlite", type=Path, required=True)
    parser.add_argument("--proxy-root", type=Path, required=True)
    parser.add_argument("--label-sqlite", type=Path, required=True)
    parser.add_argument("--verification-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build_package(
        BuildInputs(
            candidate_sqlite=args.candidate_sqlite,
            proxy_root=args.proxy_root,
            label_sqlite=args.label_sqlite,
            verification_json=args.verification_json,
        ),
        args.output,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
