#!/usr/bin/env python3
"""Capture or independently verify one frozen five-play batch."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.nowscore_history_capture import capture_history_batch, verify_history_batch, replay_history_batch  # noqa: E402
from src.nowscore_issue_inventory import canonical  # noqa: E402


def main(argv=None):
    """Read explicit inputs, execute one operation and print aggregate evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "verify", "replay"))
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--batch-id")
    parser.add_argument("--timeout", type=float, default=40)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--source-plan", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--generated-at")
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if args.mode == "capture":
        if not args.batch_id:
            parser.error("capture requires --batch-id")
        result = capture_history_batch(plan, inventory, args.batch_id, args.run_root,
                                       timeout=args.timeout, max_attempts=args.max_attempts)
    elif args.mode == "replay":
        if not args.source_plan or not args.source_root or not args.generated_at:
            parser.error("replay requires --source-plan, --source-root and --generated-at")
        result = replay_history_batch(plan, inventory, args.source_plan, args.source_root,
                                      args.run_root, generated_at=args.generated_at)
    else:
        result = verify_history_batch(plan, inventory, args.run_root)
    print(canonical({"batch_id": result["batch"]["batch_id"],
                     "data_pages": len(result["captures"]),
                     "source_empty_pages": sum(r["classification"] == "source_empty" for r in result["captures"]),
                     "quarantined_pages": sum(r["classification"] == "quarantined" for r in result["captures"]),
                     "controls": len(result["controls"])}))


if __name__ == "__main__":
    main()
