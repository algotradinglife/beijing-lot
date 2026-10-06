"""Resolve every data location through one explicit, fail-closed entry.

There is exactly one root name per physical tier, each supplied by an explicit
parameter or a single environment variable. There are no machine-specific
defaults and no fallbacks: an unresolved or absent root raises instead of
silently resolving somewhere else.

Tiers:
  ``frozen``  the persistent store (NAS Parquet)            -> BEIDAN_PARQUET_ROOT
  ``hot``     short-lived working set (NVMe)                -> BEIDAN_HOT_ROOT
  ``data``    disposable local scratch that may be recollected -> BEIDAN_DATA_ROOT
"""

from __future__ import annotations

import os
from pathlib import Path

ROOTS = {
    "frozen": ("BEIDAN_PARQUET_ROOT", "frozen store (NAS Parquet)"),
    "hot": ("BEIDAN_HOT_ROOT", "hot working set (NVMe)"),
    "data": ("BEIDAN_DATA_ROOT", "disposable scratch (recollectable)"),
}


class LocationError(RuntimeError):
    """A root or location cannot be resolved."""


def root_path(name: str, *, require_exists: bool = True, environ=None) -> Path:
    """Resolve the absolute path of a named root.

    @param name One of ``ROOTS``.
    @param require_exists When true (default) the root must exist on disk.
    @param environ Mapping to read the environment from (defaults to ``os.environ``).
    @raises LocationError for an unknown root, an unset variable, a relative path
        or (when required) a missing directory.
    """
    environ = os.environ if environ is None else environ
    if name not in ROOTS:
        raise LocationError(f"unknown root {name!r}; known roots: {sorted(ROOTS)}")
    variable, purpose = ROOTS[name]
    raw = str(environ.get(variable) or "").strip()
    if not raw:
        raise LocationError(f"{variable} is not set (needed for the {purpose} root)")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise LocationError(f"{variable} must be an absolute path; got {raw!r}")
    if require_exists and not path.is_dir():
        raise LocationError(f"{variable} does not exist or is not a directory: {path}")
    return path.resolve()


def location(token: str, *, require_exists: bool = True, environ=None) -> Path:
    """Resolve a ``tier:relative/path`` token.

    The token is the only supported way to name a data location: it binds a tier
    to a path relative to that tier's root, so no absolute path is written in
    consuming code.
    """
    if ":" not in token:
        raise LocationError(f"location token must be 'tier:relative/path'; got {token!r}")
    tier, relative = token.split(":", 1)
    base = root_path(tier, require_exists=require_exists, environ=environ)
    candidate = (base / relative).resolve() if relative else base
    if require_exists and not candidate.exists():
        raise LocationError(f"location {token!r} does not exist: {candidate}")
    return candidate


def catalog_root(*, require_exists: bool = True, environ=None) -> Path:
    """Resolve the catalog directory inside the frozen store."""
    return location("frozen:registry", require_exists=require_exists, environ=environ)


def dataset_path(name: str, version: str | None = None, *, require_exists: bool = True,
                 environ=None) -> Path:
    """Resolve a dataset directory: ``<frozen>/datasets/<name>/[versions/<version>]``.

    The caller passes the dataset name and (optionally) an explicit version; the
    path shape is owned here, not in every consumer.
    """
    base = location("frozen:datasets", require_exists=require_exists, environ=environ) / name
    if version is not None:
        base = base / "versions" / version
    if require_exists and not base.is_dir():
        raise LocationError(f"dataset {name!r}"
                            + (f" version {version!r}" if version else "") + f" not found: {base}")
    return base


def schema_path(schema_id: str, *, require_exists: bool = True, environ=None) -> Path:
    """Resolve a registered schema document: ``<frozen>/schemas/<schema_id>.json``."""
    base = location("frozen:schemas", require_exists=require_exists, environ=environ)
    path = base / f"{schema_id}.json"
    if require_exists and not path.is_file():
        raise LocationError(f"schema {schema_id!r} is not registered: {path}")
    return path
