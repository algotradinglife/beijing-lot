"""Issue #232 — atomic writers (self-contained, no divergence_profile import).

R2 fresh: R1 re-exported from ``divergence_profile.publication``; that
indirect dependency made the replay/verify path resolve the WRONG package
(EV E3).  R2 implements the same crash-durable primitives directly so the
#232 package is self-contained: temp file + fsync + rename + parent fsync.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd


def fsync_file(path: Path) -> None:
    """fsync a regular file (no-op on platforms without fsync support)."""
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def fsync_dir(path: Path) -> None:
    """fsync a directory so renames are durable."""
    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_tree(path: Path) -> None:
    """fsync every regular file under path, then the directory itself."""
    if path.is_file():
        fsync_file(path)
        fsync_dir(path.parent)
        return
    for child in sorted(path.rglob("*")):
        if child.is_file():
            fsync_file(child)
    fsync_dir(path)


def atomic_write_bytes(path: Path, payload: bytes) -> Path:
    """Write bytes atomically (temp + fsync + rename + parent fsync)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        fsync_dir(path.parent)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return path


def atomic_write_text(path: Path, text: str) -> Path:
    return atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, payload: dict | list) -> Path:
    return atomic_write_bytes(
        path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    )


def atomic_write_csv(path: Path, frame: pd.DataFrame) -> Path:
    return atomic_write_bytes(path, frame.to_csv(index=False).encode("utf-8"))


def atomic_write_parquet(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    os.close(descriptor)
    try:
        frame.to_parquet(temp_path, index=False)
        with temp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        fsync_dir(path.parent)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
    return path


def atomic_publish_directory(target: Path, staging: Path) -> Path:
    """Publish a staging directory atomically (rename + parent fsync)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_name(target.name + ".prev")
        if backup.exists():
            import shutil

            shutil.rmtree(backup)
        os.replace(target, backup)
    os.replace(staging, target)
    fsync_dir(target.parent)
    return target


__all__ = [
    "fsync_file",
    "fsync_dir",
    "fsync_tree",
    "atomic_write_bytes",
    "atomic_write_text",
    "atomic_write_json",
    "atomic_write_csv",
    "atomic_write_parquet",
    "atomic_publish_directory",
]
