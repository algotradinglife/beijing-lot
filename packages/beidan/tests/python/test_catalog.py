"""Offline tests for the single data entry: roots, resolution, catalog, schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from beidan_backend import catalog
from beidan_backend.catalog import paths


def _fixture(tmp_path: Path) -> dict[str, str]:
    """A minimal frozen/hot/data layout with one dataset and one schema."""
    frozen = tmp_path / "frozen"
    hot = tmp_path / "hot"
    data = tmp_path / "data"
    for base, rel in [
        (frozen, "registry"), (frozen, "schemas"),
        (frozen, "datasets/demo/versions/v1"), (hot, ""), (data, ""),
    ]:
        (base / rel).mkdir(parents=True, exist_ok=True)

    (frozen / "registry/catalog.json").write_text(json.dumps({
        "schema": catalog.CATALOG_SCHEMA,
        "datasets": {
            "demo": {
                "kind": "dataset", "format": "parquet",
                "location": "frozen:datasets/demo", "version": "v1",
                "schema_id": "demo_v1", "owner": "test", "retention": "retained",
            }
        },
    }), encoding="utf-8")
    (frozen / "schemas/demo_v1.json").write_text(
        json.dumps({"schema_id": "demo_v1", "tables": {"obs": {"kind": "whole"}}}), encoding="utf-8")
    return {"BEIDAN_PARQUET_ROOT": str(frozen), "BEIDAN_HOT_ROOT": str(hot),
            "BEIDAN_DATA_ROOT": str(data)}


def test_root_path_resolves_declared_tiers(tmp_path):
    environ = _fixture(tmp_path)
    assert paths.root_path("frozen", environ=environ) == (tmp_path / "frozen").resolve()
    assert paths.root_path("hot", environ=environ) == (tmp_path / "hot").resolve()
    assert paths.root_path("data", environ=environ) == (tmp_path / "data").resolve()


def test_root_path_fails_closed(tmp_path):
    environ = _fixture(tmp_path)
    with pytest.raises(paths.LocationError, match="unknown root"):
        paths.root_path("nope", environ=environ)
    # unset variable
    with pytest.raises(paths.LocationError, match="is not set"):
        paths.root_path("frozen", environ={})
    # relative path
    with pytest.raises(paths.LocationError, match="must be an absolute path"):
        paths.root_path("frozen", environ={"BEIDAN_PARQUET_ROOT": "relative/path"})
    # missing directory
    with pytest.raises(paths.LocationError, match="does not exist"):
        paths.root_path("frozen", environ={"BEIDAN_PARQUET_ROOT": str(tmp_path / "absent")})


def test_location_token_binds_tier_and_relative_path(tmp_path):
    environ = _fixture(tmp_path)
    assert paths.location("frozen:registry", environ=environ).name == "registry"
    with pytest.raises(paths.LocationError, match="tier:relative/path"):
        paths.location("frozen-registry", environ=environ)
    with pytest.raises(paths.LocationError, match="does not exist"):
        paths.location("frozen:datasets/nope", environ=environ)


def test_dataset_path_owns_the_version_layout(tmp_path):
    environ = _fixture(tmp_path)
    base = paths.dataset_path("demo", environ=environ)
    assert base.name == "demo"
    version = paths.dataset_path("demo", "v1", environ=environ)
    assert version.parts[-3:] == ("demo", "versions", "v1")
    with pytest.raises(paths.LocationError, match="not found"):
        paths.dataset_path("demo", "v9", environ=environ)


def test_catalog_reads_and_validates(tmp_path):
    environ = _fixture(tmp_path)
    assert catalog.catalog_path(environ=environ).name == "catalog.json"
    entries = catalog.catalog_entries(environ=environ)
    assert set(entries) == {"demo"}
    assert catalog.catalog_entry("demo", environ=environ)["version"] == "v1"
    with pytest.raises(paths.LocationError, match="not in the catalog"):
        catalog.catalog_entry("missing", environ=environ)


def test_catalog_rejects_wrong_schema_and_missing_files(tmp_path):
    environ = _fixture(tmp_path)
    registry = Path(environ["BEIDAN_PARQUET_ROOT"]) / "registry/catalog.json"
    registry.write_text(json.dumps({"schema": "wrong", "datasets": {}}), encoding="utf-8")
    with pytest.raises(paths.LocationError, match="schema must be"):
        catalog.load_catalog(environ=environ)
    registry.write_text("{not json", encoding="utf-8")
    with pytest.raises(paths.LocationError, match="unreadable"):
        catalog.load_catalog(environ=environ)
    registry.unlink()
    with pytest.raises(paths.LocationError):
        catalog.load_catalog(environ=environ)


def test_schema_registry_entry(tmp_path):
    environ = _fixture(tmp_path)
    assert paths.schema_path("demo_v1", environ=environ).name == "demo_v1.json"
    assert catalog.schema_entry("demo_v1", environ=environ)["schema_id"] == "demo_v1"
    with pytest.raises(paths.LocationError, match="not registered"):
        catalog.schema_entry("absent_v1", environ=environ)


def test_live_frozen_store_catalog_when_mounted():
    """The real NAS catalog, when the store is reachable."""
    import os
    if not os.path.isdir("/mnt/nas/Data/beijing-lot"):
        pytest.skip("frozen store not mounted")
    os.environ.setdefault("BEIDAN_PARQUET_ROOT", "/mnt/nas/Data/beijing-lot")
    entry = catalog.catalog_entry("settlement")
    assert entry["format"] == "parquet"
    assert entry["schema_id"]
    assert catalog.dataset_path("settlement", entry["version"]).is_dir()
    doc = catalog.schema_entry(entry["schema_id"])
    assert doc["partition_by"] == entry["partition_by"]
