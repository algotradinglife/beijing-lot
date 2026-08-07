#!/usr/bin/env python3
"""Build and verify the immutable, outcome-unexposed #204 Gate-A package."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unified_model.gate_a import build_package, verify_package  # noqa: E402


def _default_data_source(relative: str) -> Path:
    """Find a shared read-only archive from a nested git worktree."""

    for parent in (ROOT, *ROOT.parents):
        candidate = parent / relative
        if candidate.is_file():
            return candidate
    # Keep the command fail-closed with a useful, repository-relative default.
    return ROOT / relative


def _default_history_source() -> Path:
    return _default_data_source("data/beidan_history.db")


def _default_full_3sp_identity_source() -> Path:
    return _default_data_source("data/raw/beidan_full_3sp.csv")


def _default_pclose_source() -> Path:
    return _default_data_source("data/beidan_features.db")


def _atomic_build(
    output: Path, source: Path, history_source: Path, full_3sp_identity_source: Path, pclose_source: Path,
) -> dict[str, object]:
    output = output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to replace existing package: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage.", dir=output.parent))
    try:
        receipt = build_package(
            stage, source_package=source, history_source=history_source,
            full_3sp_identity_source=full_3sp_identity_source, pclose_source=pclose_source,
        )
        os.replace(stage, output)
        receipt["package"] = output.name
        return receipt
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--source", type=Path, default=ROOT / "results/bj203_causal_tensor_v2")
    freeze.add_argument("--history-source", type=Path, default=_default_history_source())
    freeze.add_argument("--full-3sp-identity-source", type=Path, default=_default_full_3sp_identity_source())
    freeze.add_argument("--pclose-source", type=Path, default=_default_pclose_source())
    verify = commands.add_parser("verify")
    verify.add_argument("--package", type=Path, default=ROOT / "results/bj204_gate_a_preoutcome_v3")
    arguments = parser.parse_args()
    receipt = (
        _atomic_build(
            arguments.output, arguments.source, arguments.history_source,
            arguments.full_3sp_identity_source, arguments.pclose_source,
        )
        if arguments.command == "freeze"
        else verify_package(arguments.package)
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
