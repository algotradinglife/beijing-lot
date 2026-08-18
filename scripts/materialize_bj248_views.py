#!/usr/bin/env python3
"""Materialize #248 relative/common-epoch Parquet views and an operations report."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from forward_snapshot import SnapshotStore, materialize_common_epoch_view, materialize_relative_horizon_view
from forward_snapshot.store import DATA_ROOT_ENV


def _atomic_parquet(frame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _atomic_json(payload: dict, path: Path) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epoch-json", type=Path, help="optional {issue: ISO-UTC epoch} map")
    args = parser.parse_args()
    root_text = os.environ.get(DATA_ROOT_ENV)
    if not root_text:
        parser.error(f"{DATA_ROOT_ENV} must be explicitly set")
    root = Path(root_text)
    epochs = json.loads(args.epoch_json.read_text(encoding="utf-8")) if args.epoch_json else None
    store = SnapshotStore.open(root)
    try:
        relative = materialize_relative_horizon_view(store)
        common = materialize_common_epoch_view(store, decision_epochs=epochs)
        output = root / "forward_snapshot" / "views"
        _atomic_parquet(relative, output / "relative_horizon_view.parquet")
        _atomic_parquet(common, output / "common_epoch_view.parquet")
        report = {
            "issue_count": int(common.issue_code.nunique()) if not common.empty else 0,
            "fixture_count": int(common.fixture_key.nunique()) if not common.empty else 0,
            "common_epoch_cells": int(len(common)),
            "relative_horizon_cells": int(len(relative)),
            "capture_receipts": store.count("capture_receipt"),
            "note": "zero is an observed materialization count, never a substituted missing quote",
        }
        report_path = output / "operations_report.json"
        _atomic_json(report, report_path)
        print(json.dumps(report, sort_keys=True))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
