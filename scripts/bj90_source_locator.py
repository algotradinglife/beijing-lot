"""Deterministic local-input locator shared by Issue #90 runners."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


RELATIVE_SOURCE = Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite")
ENVIRONMENT_VARIABLE = "BJ90_SOURCE_DB"


def add_source_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-db",
        type=Path,
        help=f"path to local historical SQLite input (overrides ${ENVIRONMENT_VARIABLE})",
    )


def _checked(path: Path, attempted: list[Path]) -> Path | None:
    candidate = path.expanduser().resolve()
    attempted.append(candidate)
    return candidate if candidate.is_file() else None


def resolve_source(repository_root: Path, explicit: Path | None = None) -> Path:
    """Return exactly one usable source path or fail closed with every attempt.

    The normal repository-relative path is primary.  A checked-out worktree
    directly below ``.worktrees`` may use its containing repository's data
    directory as a documented fallback.  Explicit CLI and environment paths
    are intentional operator overrides and do not silently fall through.
    """
    root = repository_root.resolve()
    attempted: list[Path] = []
    if explicit is not None:
        found = _checked(explicit, attempted)
        if found:
            return found
        raise FileNotFoundError("BJ90 source database not found; attempted: " + ", ".join(map(str, attempted)))
    environment = os.environ.get(ENVIRONMENT_VARIABLE)
    if environment:
        found = _checked(Path(environment), attempted)
        if found:
            return found
        raise FileNotFoundError("BJ90 source database not found; attempted: " + ", ".join(map(str, attempted)))
    found = _checked(root / RELATIVE_SOURCE, attempted)
    if found:
        return found
    if root.parent.name == ".worktrees":
        found = _checked(root.parent.parent / RELATIVE_SOURCE, attempted)
        if found:
            return found
    raise FileNotFoundError("BJ90 source database not found; attempted: " + ", ".join(map(str, attempted)))
