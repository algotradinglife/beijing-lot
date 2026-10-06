"""The single data entry: one catalog, one resolver, one schema registry.

Every consumer asks this package where data lives and what shape it has, instead
of hard-coding a path or declaring its own tables. Importing performs no I/O.
"""

from __future__ import annotations

from .paths import (
    ROOTS,
    LocationError,
    catalog_root,
    dataset_path,
    location,
    root_path,
    schema_path,
)
from .registry import (
    CATALOG_SCHEMA,
    catalog_entries,
    catalog_entry,
    catalog_path,
    load_catalog,
    schema_entry,
)

__all__ = [
    "CATALOG_SCHEMA",
    "ROOTS",
    "LocationError",
    "catalog_entries",
    "catalog_entry",
    "catalog_path",
    "catalog_root",
    "dataset_path",
    "load_catalog",
    "location",
    "root_path",
    "schema_entry",
    "schema_path",
]
