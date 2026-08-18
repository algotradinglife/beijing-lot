"""REQ-E06 remanifested semantic attacks against #235's proxy package."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bj235_package import rehash_package, verify_package, write_package


def _source(path: Path) -> Path:
    with sqlite3.connect(path) as con:
        con.executescript("CREATE TABLE matches (match_id INTEGER PRIMARY KEY, issue TEXT, match_idx INTEGER, handicap_line_norm REAL); CREATE TABLE market_consensus (match_id INTEGER, market TEXT, snapshot TEXT, v1_avg REAL, v2_avg REAL, v3_avg REAL);")
        con.execute("INSERT INTO matches VALUES (1, '14001', 1, -1.0)")
        con.executemany("INSERT INTO market_consensus VALUES (1, 'euro_1x2', ?, 2.0, 3.0, 4.0)", [("initial",), ("10h",), ("1h",)])
    return path


def _package(tmp_path: Path) -> Path:
    return write_package(tmp_path / "package", _source(tmp_path / "source.sqlite"))


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("raw_sp", 9.0, "probability"),
        ("snapshot_horizon", "final", "horizon"),
    ],
)
def test_remanifested_decision_cell_tamper_fails(tmp_path: Path, column: str, value: object, message: str) -> None:
    package = _package(tmp_path)
    cells_path = package / "tables" / "historical_proxy_cells.parquet"
    cells = pd.read_parquet(cells_path)
    cells.loc[cells.index[0], column] = value
    cells.to_parquet(cells_path, index=False)
    rehash_package(package)
    with pytest.raises(AssertionError, match=message):
        verify_package(package)


def test_remanifested_coverage_ledger_rebalancing_fails(tmp_path: Path) -> None:
    package = _package(tmp_path)
    coverage_path = package / "tables" / "coverage_by_issue_horizon.csv"
    coverage = pd.read_csv(coverage_path, dtype={"issue_code": str})
    coverage.loc[0, "available_cell_count"] += 3
    coverage.to_csv(coverage_path, index=False)
    rehash_package(package)
    with pytest.raises(AssertionError, match="coverage"):
        verify_package(package)


def test_remanifested_manifest_source_trace_forgery_fails(tmp_path: Path) -> None:
    package = _package(tmp_path)
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["time_semantics"] = "TIMESTAMPED_UTC"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    rehash_package(package)
    with pytest.raises(AssertionError, match="time semantics"):
        verify_package(package)
