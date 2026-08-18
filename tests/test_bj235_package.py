"""Semantic package tests for Issue #235 historical proxy delivery."""
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
        con.executescript(
            """
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY,
                issue TEXT,
                match_idx INTEGER,
                handicap_line_norm REAL
            );
            CREATE TABLE market_consensus (
                match_id INTEGER,
                market TEXT,
                snapshot TEXT,
                v1_avg REAL,
                v2_avg REAL,
                v3_avg REAL
            );
            """
        )
        con.execute("INSERT INTO matches VALUES (?, ?, ?, ?)", (10, "14001", 1, -1.0))
        con.executemany(
            "INSERT INTO market_consensus VALUES (?, ?, ?, ?, ?, ?)",
            [
                (10, "euro_1x2", "initial", 2.0, 3.0, 4.0),
                (10, "euro_1x2", "10h", 2.1, 3.1, 4.1),
                (10, "euro_1x2", "1h", 2.2, 3.2, None),
            ],
        )
    return path


def test_package_rejects_remanifested_probability_and_source_label_tampering(tmp_path: Path) -> None:
    package = write_package(tmp_path / "package", _source(tmp_path / "history.sqlite"))
    assert verify_package(package)["status"] == "PASS"

    cells_path = package / "tables" / "historical_proxy_cells.parquet"
    cells = pd.read_parquet(cells_path)
    cells.loc[cells.index[0], "normalized_inverse_sp_probability"] = 0.99
    cells.to_parquet(cells_path, index=False)
    rehash_package(package)
    with pytest.raises(AssertionError, match="probability"):
        verify_package(package)

    package = write_package(tmp_path / "package", _source(tmp_path / "fresh.sqlite"))
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_id"] = "forged_source"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    rehash_package(package)
    with pytest.raises(AssertionError, match="source"):
        verify_package(package)
