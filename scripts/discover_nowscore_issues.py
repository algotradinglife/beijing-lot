#!/usr/bin/env python3
"""Plan, capture, and merge source-native Nowscore issue inventory batches."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.nowscore_issue_inventory import (  # noqa: E402
    canonical,
    capture_batch,
    make_plan,
    merge_batches,
    replay_sealed_batch,
    validate_plan,
    verify_batch,
)


def _new_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(canonical(value) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--output", type=Path, required=True)
    plan_parser.add_argument("--legacy-start-year", type=int, required=True)
    plan_parser.add_argument("--legacy-end-year", type=int, required=True)
    plan_parser.add_argument("--legacy-max-monthly-serial", type=int, required=True)
    plan_parser.add_argument("--modern-start-year", type=int, required=True)
    plan_parser.add_argument("--modern-end-year", type=int, required=True)
    plan_parser.add_argument("--modern-max-serial", type=int, required=True)
    plan_parser.add_argument("--batch-size", type=int, required=True)
    plan_parser.add_argument("--control-issue", required=True)
    plan_parser.add_argument("--generated-at", required=True)
    plan_parser.add_argument("--request-interval", type=float, required=True)

    capture_parser = subparsers.add_parser("capture-batch")
    capture_parser.add_argument("--plan", type=Path, required=True)
    capture_parser.add_argument("--batch-id", required=True)
    capture_parser.add_argument("--run-root", type=Path, required=True)
    capture_parser.add_argument("--timeout", type=float, default=40)
    capture_parser.add_argument("--max-attempts", type=int, default=3)

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--plan", type=Path, required=True)
    merge_parser.add_argument("--batch-root", type=Path, action="append", required=True)
    merge_parser.add_argument("--output", type=Path, required=True)
    merge_parser.add_argument("--generated-at", required=True)

    verify_parser = subparsers.add_parser("verify-batch")
    verify_parser.add_argument("--plan", type=Path, required=True)
    verify_parser.add_argument("--batch-root", type=Path, required=True)

    replay_parser = subparsers.add_parser("replay-batch")
    replay_parser.add_argument("--plan", type=Path, required=True)
    replay_parser.add_argument("--source-plan", type=Path, required=True)
    replay_parser.add_argument("--source-root", type=Path, required=True)
    replay_parser.add_argument("--output-root", type=Path, required=True)
    replay_parser.add_argument("--generated-at", required=True)

    arguments = parser.parse_args(argv)
    if arguments.mode == "plan":
        result = make_plan(
            legacy_start_year=arguments.legacy_start_year,
            legacy_end_year=arguments.legacy_end_year,
            legacy_max_monthly_serial=arguments.legacy_max_monthly_serial,
            modern_start_year=arguments.modern_start_year,
            modern_end_year=arguments.modern_end_year,
            modern_max_serial=arguments.modern_max_serial,
            batch_size=arguments.batch_size,
            control_issue=arguments.control_issue,
            generated_at=arguments.generated_at,
            request_interval_seconds=arguments.request_interval,
        )
        _new_json(arguments.output, result)
    else:
        plan = json.loads(arguments.plan.read_text(encoding="utf-8"))
        validate_plan(plan)
        if arguments.mode == "capture-batch":
            result = capture_batch(
                plan,
                arguments.batch_id,
                arguments.run_root,
                timeout_seconds=arguments.timeout,
                max_attempts=arguments.max_attempts,
            )
        elif arguments.mode == "verify-batch":
            result = verify_batch(plan, arguments.batch_root)
        elif arguments.mode == "replay-batch":
            result = replay_sealed_batch(
                plan, arguments.source_plan, arguments.source_root, arguments.output_root,
                generated_at=arguments.generated_at,
            )
        else:
            result = merge_batches(
                plan,
                arguments.batch_root,
                arguments.output,
                generated_at=arguments.generated_at,
            )
    summary_keys = (
        "schema",
        "candidate_count",
        "batch_count",
        "issue_count",
        "source_empty_count",
        "five_play_pages_to_capture",
        "classification_counts",
    )
    print(canonical({key: result[key] for key in summary_keys if key in result}))


if __name__ == "__main__":
    main()
