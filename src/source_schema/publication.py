"""Crash-durable atomic writers used by every Issue #234 artifact path.

No durability error is best-effort: file and parent-directory fsync failures
propagate.  Directory publication uses same-parent staging and rolls back to
the old immutable package on any BaseException through the commit point.
This is the same writer family used by #229/#232, kept package-local so the
contract package is self-contained.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

import pandas as pd


def fsync_file(path: Path) -> None:
    """Flush one completed file to durable storage, failing closed."""
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def fsync_dir(path: Path) -> None:
    """Flush directory entries to durable storage, failing closed."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _temp_path(path: Path) -> tuple[int, Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=f".tmp{path.suffix}", dir=str(path.parent)
    )
    return descriptor, Path(name)


def _commit_temp(temp: Path, target: Path) -> None:
    fsync_file(temp)
    os.replace(temp, target)
    fsync_dir(target.parent)


def atomic_write_bytes(path: Path, content: bytes) -> Path:
    descriptor, temp = _temp_path(path)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fsync_dir(path.parent)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return path


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, content.encode(encoding))


def atomic_write_json(path: Path, payload: object) -> Path:
    return atomic_write_text(
        path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> Path:
    descriptor, temp = _temp_path(path)
    os.close(descriptor)
    try:
        frame.to_csv(temp, index=False, encoding="utf-8")
        _commit_temp(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return path


def atomic_write_parquet(frame: pd.DataFrame, path: Path) -> Path:
    descriptor, temp = _temp_path(path)
    os.close(descriptor)
    try:
        frame.to_parquet(temp, index=False)
        _commit_temp(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return path


def fsync_tree(root: Path) -> None:
    """Fsync every file and directory, deepest entries first."""
    files = [path for path in root.rglob("*") if path.is_file()]
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for path in sorted(files):
        fsync_file(path)
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        fsync_dir(path)
    fsync_dir(root)


def _recover_stale(target: Path, previous: Path) -> None:
    """Recover an interrupted prior swap before attempting a new publication."""
    parent = target.parent
    if previous.exists() and not target.exists():
        os.replace(previous, target)
        fsync_dir(parent)
    elif previous.exists() and target.exists():
        shutil.rmtree(previous)
        fsync_dir(parent)
    for stale in parent.glob(f".{target.name}.staging-*"):
        shutil.rmtree(stale)
    fsync_dir(parent)


def atomic_publish_directory(
    target: Path,
    populate: Callable[[Path], None],
    *,
    force: bool = False,
) -> Path:
    """Populate and atomically install a complete immutable directory.

    The old target is moved to ``.<name>.previous`` only after the new staging
    tree is complete and durable.  Any BaseException before the new target's
    parent fsync completes restores the old target.  Stale staging/previous
    state from a killed prior run is recovered at entry, enabling immediate
    retry.
    """
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    previous = parent / f".{target.name}.previous"
    _recover_stale(target, previous)
    if target.exists() and not force:
        raise FileExistsError(
            f"refusing to replace existing package: {target} (use force=True)"
        )

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=parent))
    old_moved = False
    new_installed = False
    try:
        populate(staging)
        fsync_tree(staging)
        fsync_dir(parent)  # staging entry durable before either rename

        if target.exists():
            os.replace(target, previous)
            old_moved = True
            fsync_dir(parent)  # old -> previous durable

        os.replace(staging, target)
        new_installed = True
        fsync_dir(parent)  # publication commit point

        if previous.exists():
            shutil.rmtree(previous)
            fsync_dir(parent)
        return target
    except BaseException:
        try:
            if new_installed and target.exists() and old_moved and previous.exists():
                failed_new = parent / f".{target.name}.failed-new"
                if failed_new.exists():
                    shutil.rmtree(failed_new)
                os.replace(target, failed_new)
                os.replace(previous, target)
                shutil.rmtree(failed_new, ignore_errors=True)
            elif old_moved and not target.exists() and previous.exists():
                os.replace(previous, target)
            elif new_installed and not old_moved and target.exists():
                shutil.rmtree(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        raise
