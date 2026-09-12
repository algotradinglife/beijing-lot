#!/usr/bin/env python3
"""Freeze a five-play capture plan from a complete Nowscore inventory."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.nowscore_history_plan import make_history_capture_plan  # noqa: E402
from src.nowscore_issue_inventory import canonical  # noqa: E402


def main(argv=None):
    """Read explicit inventory, create a new plan file, print aggregate counts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--issues-per-batch", type=int, required=True)
    parser.add_argument("--control-issue", required=True)
    parser.add_argument("--interval", type=float, default=2)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    plan = make_history_capture_plan(
        inventory, issues_per_batch=args.issues_per_batch,
        control_issue=args.control_issue, interval_seconds=args.interval,
        generated_at=args.generated_at,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(canonical(plan) + "\n")
    print(canonical({key: plan[key] for key in (
        "plan_sha256", "issue_count", "batch_count", "data_request_count", "control_request_count"
    )}))


if __name__ == "__main__":
    main()
