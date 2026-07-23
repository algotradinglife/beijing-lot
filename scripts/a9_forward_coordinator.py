#!/usr/bin/env python3
"""Publish and coordinate paper-only A9 forward comparison events."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.a9_coordination import (  # noqa: E402
    SubprocessResearchAdapter,
    event_path,
    process_freeze,
    process_settlement,
    publish_input_ready,
    scan_ready_events,
    verify_input_ready,
)


DEFAULT_COORDINATION_ROOT = ROOT / "results/coordination"
DEFAULT_RESEARCH_ROOT = Path(
    os.environ.get(
        "A9_RESEARCH_ROOT",
        ROOT / ".worktrees/feature-strategy-beijing-lot-model-betting-20260712",
    )
)


def add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--coordination-root", type=Path, default=DEFAULT_COORDINATION_ROOT)
    parser.add_argument("--research-root", type=Path, default=DEFAULT_RESEARCH_ROOT)
    parser.add_argument("--research-python", type=Path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish = subparsers.add_parser("publish")
    publish.add_argument("--issue", required=True)
    publish.add_argument("--overlap-dir", type=Path, required=True)
    publish.add_argument("--coordination-root", type=Path, default=DEFAULT_COORDINATION_ROOT)

    verify = subparsers.add_parser("verify-event")
    verify.add_argument("--event-dir", type=Path, required=True)

    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--issue", required=True)
    add_runtime_arguments(freeze)

    settle = subparsers.add_parser("settle")
    settle.add_argument("--issue", required=True)
    add_runtime_arguments(settle)

    scan = subparsers.add_parser("scan")
    add_runtime_arguments(scan)
    return parser.parse_args()


def adapter(arguments: argparse.Namespace) -> SubprocessResearchAdapter:
    return SubprocessResearchAdapter(arguments.research_root, arguments.research_python)


def main() -> int:
    arguments = parse_args()
    if arguments.command == "publish":
        result = publish_input_ready(
            arguments.coordination_root,
            arguments.issue,
            arguments.overlap_dir,
        )
    elif arguments.command == "verify-event":
        result = verify_input_ready(arguments.event_dir)
    elif arguments.command == "freeze":
        result = process_freeze(
            event_path(arguments.coordination_root, arguments.issue),
            adapter(arguments),
        )
    elif arguments.command == "settle":
        result = process_settlement(
            event_path(arguments.coordination_root, arguments.issue),
            adapter(arguments),
        )
    else:
        result = scan_ready_events(arguments.coordination_root, adapter(arguments))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
