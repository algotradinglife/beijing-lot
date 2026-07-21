#!/usr/bin/env python3
"""Create and verify immutable research freeze, settlement, and review packages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research_freeze_protocol import (  # noqa: E402
    DEFAULT_FREEZE_ROOT,
    DEFAULT_REVIEW_ROOT,
    DEFAULT_SETTLEMENT_ROOT,
    create_freeze_package,
    create_review_package,
    create_settlement_package,
    verify_freeze_package,
    verify_review_package,
    verify_settlement_package,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    freeze = commands.add_parser("freeze", help="atomically publish a new immutable research freeze")
    freeze.add_argument("--experiment-id", required=True)
    freeze.add_argument("--research-question", required=True)
    freeze.add_argument("--model-version", required=True)
    freeze.add_argument("--input", type=Path, action="append", required=True)
    freeze.add_argument("--decision", type=Path, action="append", required=True)
    freeze.add_argument("--config", type=Path, required=True)
    freeze.add_argument("--metadata", type=Path, action="append", default=[])
    freeze.add_argument("--output-dir", type=Path)
    freeze.add_argument("--git-commit")
    freeze.add_argument("--frozen-at-utc")

    verify_freeze = commands.add_parser("verify-freeze", help="verify one immutable freeze package")
    verify_freeze.add_argument("--package-dir", type=Path, required=True)

    settle = commands.add_parser("settle", help="capture real result evidence for a verified freeze")
    settle.add_argument("--freeze-dir", type=Path, required=True)
    settle.add_argument("--settlement-id", required=True)
    settle.add_argument("--result", type=Path, action="append", required=True)
    settle.add_argument("--output-dir", type=Path)
    settle.add_argument("--settled-at-utc")

    verify_settlement = commands.add_parser("verify-settlement", help="verify one settlement package")
    verify_settlement.add_argument("--package-dir", type=Path, required=True)

    review = commands.add_parser("review", help="publish an interpretive review for verified upstream packages")
    review.add_argument("--freeze-dir", type=Path, required=True)
    review.add_argument("--settlement-dir", type=Path, required=True)
    review.add_argument("--review-id", required=True)
    review.add_argument("--summary", type=Path, required=True)
    review.add_argument("--output-dir", type=Path)
    review.add_argument("--reviewed-at-utc")

    verify_review = commands.add_parser("verify-review", help="verify one review package")
    verify_review.add_argument("--package-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if arguments.command == "freeze":
        output = arguments.output_dir or DEFAULT_FREEZE_ROOT / arguments.experiment_id
        result = create_freeze_package(
            output,
            experiment_id=arguments.experiment_id,
            research_question=arguments.research_question,
            model_version=arguments.model_version,
            input_files=arguments.input,
            decision_files=arguments.decision,
            config_file=arguments.config,
            metadata_files=arguments.metadata,
            git_commit=arguments.git_commit,
            frozen_at_utc=arguments.frozen_at_utc,
        )
    elif arguments.command == "verify-freeze":
        result = verify_freeze_package(arguments.package_dir)
    elif arguments.command == "settle":
        freeze = verify_freeze_package(arguments.freeze_dir)
        output = arguments.output_dir or DEFAULT_SETTLEMENT_ROOT / freeze["freeze_id"] / arguments.settlement_id
        result = create_settlement_package(
            arguments.freeze_dir,
            output,
            settlement_id=arguments.settlement_id,
            result_files=arguments.result,
            settled_at_utc=arguments.settled_at_utc,
        )
    elif arguments.command == "verify-settlement":
        result = verify_settlement_package(arguments.package_dir)
    elif arguments.command == "review":
        freeze = verify_freeze_package(arguments.freeze_dir)
        output = arguments.output_dir or DEFAULT_REVIEW_ROOT / freeze["freeze_id"] / arguments.review_id
        result = create_review_package(
            arguments.freeze_dir,
            arguments.settlement_dir,
            output,
            review_id=arguments.review_id,
            summary_file=arguments.summary,
            reviewed_at_utc=arguments.reviewed_at_utc,
        )
    else:
        result = verify_review_package(arguments.package_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
