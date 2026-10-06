"""Read the single catalog: the authoritative list of what data exists.

The catalog answers, for every dataset: its name, kind, storage format, location
token, schema id, version, owner and retention state. It is the only place a
consumer learns that a dataset exists. Paths are never duplicated here — the
path shape belongs to :mod:`beidan_backend.catalog.location`.
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import LocationError, catalog_root, schema_path

CATALOG_SCHEMA = "beijing_lot_catalog_v1"
CATALOG_FILE = "catalog.json"


def catalog_path(*, require_exists: bool = True, environ=None) -> Path:
    """Resolve ``<frozen>/registry/catalog.json``."""
    return catalog_root(require_exists=require_exists, environ=environ) / CATALOG_FILE


def load_catalog(*, environ=None) -> dict:
    """Load and minimally validate the catalog.

    @raises LocationError when the catalog is absent or malformed, so a caller
        can never proceed against an unknown dataset universe.
    """
    path = catalog_path(environ=environ)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LocationError(f"catalog is unreadable: {path}: {error}") from error
    if payload.get("schema") != CATALOG_SCHEMA:
        raise LocationError(
            f"catalog schema must be {CATALOG_SCHEMA!r}; got {payload.get('schema')!r}")
    if not isinstance(payload.get("datasets"), dict):
        raise LocationError("catalog must contain a 'datasets' object")
    return payload


def catalog_entries(*, environ=None) -> dict:
    """Every dataset entry, keyed by name."""
    return load_catalog(environ=environ)["datasets"]


def catalog_entry(name: str, *, environ=None) -> dict:
    """One dataset entry.

    @raises LocationError when the dataset is not registered.
    """
    entries = catalog_entries(environ=environ)
    if name not in entries:
        raise LocationError(f"dataset {name!r} is not in the catalog; "
                            f"registered: {sorted(entries)}")
    return entries[name]


def schema_entry(schema_id: str, *, environ=None) -> dict:
    """Load a registered schema document by id.

    @raises LocationError when the schema is not registered.
    """
    path = schema_path(schema_id, environ=environ)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LocationError(f"schema {schema_id!r} is unreadable: {path}: {error}") from error
