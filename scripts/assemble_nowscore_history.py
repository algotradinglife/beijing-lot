#!/usr/bin/env python3
"""Verify and assemble all five-play batches into a new immutable bundle."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.nowscore_history_assembly import assemble_history_batches  # noqa: E402
from src.nowscore_issue_inventory import canonical  # noqa: E402


def main(argv=None):
    """Assemble explicit roots and print counts without raw or local path data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch-root", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args(argv)
    result = assemble_history_batches(
        json.loads(args.plan.read_text(encoding="utf-8")),
        json.loads(args.inventory.read_text(encoding="utf-8")),
        args.batch_root, args.output, generated_at=args.generated_at,
    )
    print(canonical({"requested_issues": len(result["requested_issues"]),
                     "data_pages": len(result["captures"]),
                     "batches": len(result["batch_receipts"])}))


if __name__ == "__main__":
    main()
