#!/usr/bin/env python3
"""Build and verify the immutable #203 causal tensor package."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from unified_tensor.builder import (  # noqa: E402
    build_development_labels,
    build_inference,
    compare_inference_replay,
    finalize_package,
    verify_package,
    verify_superseded_package,
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    build_all = commands.add_parser("build-all")
    build_all.add_argument("--output", type=Path, required=True)
    build_all.add_argument("--database", type=Path, required=True)
    build_all.add_argument(
        "--heldout-historical-database", type=Path, required=True
    )
    build_all.add_argument("--heldout-live-database", type=Path, required=True)
    inference = commands.add_parser("build-inference")
    inference.add_argument("--output", type=Path, required=True)
    source = inference.add_mutually_exclusive_group(required=True)
    source.add_argument("--database", type=Path)
    source.add_argument("--identity-extension", type=Path)
    heldout_source = inference.add_mutually_exclusive_group(required=True)
    heldout_source.add_argument("--heldout-identity-extension", type=Path)
    heldout_source.add_argument(
        "--heldout-source-databases", action="store_true"
    )
    inference.add_argument("--heldout-historical-database", type=Path)
    inference.add_argument("--heldout-live-database", type=Path)
    labels = commands.add_parser("build-labels")
    labels.add_argument("--output", type=Path, required=True)
    labels.add_argument("--database", type=Path, required=True)
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--package", type=Path, required=True)
    verify_superseded = commands.add_parser("verify-superseded")
    verify_superseded.add_argument("--package", type=Path, required=True)
    compare = commands.add_parser("compare-inference")
    compare.add_argument("--frozen", type=Path, required=True)
    compare.add_argument("--replay", type=Path, required=True)
    return value


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command == "build-all":
        output = arguments.output.resolve()
        if output.exists():
            raise SystemExit(f"refusing to replace existing output: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent)
        ).resolve()
        try:
            receipt = {
                "inference": build_inference(
                    stage,
                    database=arguments.database,
                    heldout_historical_database=(
                        arguments.heldout_historical_database
                    ),
                    heldout_live_database=arguments.heldout_live_database,
                ),
                "labels": build_development_labels(stage, database=arguments.database),
                "final": finalize_package(stage),
            }
            os.replace(stage, output)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    elif arguments.command == "build-inference":
        if arguments.heldout_source_databases and (
            arguments.heldout_historical_database is None
            or arguments.heldout_live_database is None
        ):
            raise SystemExit(
                "--heldout-source-databases requires both held-out database paths"
            )
        receipt = build_inference(
            arguments.output,
            database=arguments.database,
            identity_extension=arguments.identity_extension,
            heldout_historical_database=(
                arguments.heldout_historical_database
                if arguments.heldout_source_databases
                else None
            ),
            heldout_live_database=(
                arguments.heldout_live_database
                if arguments.heldout_source_databases
                else None
            ),
            heldout_identity_extension=arguments.heldout_identity_extension,
        )
    elif arguments.command == "build-labels":
        receipt = build_development_labels(
            arguments.output, database=arguments.database
        )
    elif arguments.command == "finalize":
        receipt = finalize_package(arguments.output)
    elif arguments.command == "compare-inference":
        receipt = compare_inference_replay(arguments.frozen, arguments.replay)
    elif arguments.command == "verify-superseded":
        receipt = verify_superseded_package(arguments.package)
    else:
        receipt = verify_package(arguments.package)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
