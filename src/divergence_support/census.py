"""Issue #232 — source census.

Profiles every candidate source (committed upstream packages and gitignored
recoverable raw assets) with:

- presence / hash receipt (committed packages are SHA256-verified through the
  shared upstream manifest; raw assets are hashed when present and recorded
  as ``RAW_ASSET_ABSENT`` when not);
- row counts, issue ranges, timestamp semantics and grade.

No conclusion depends on a gitignored raw asset being present: the causal
waterfall is computed from committed packages, and raw assets only enrich the
recovery/reconciliation evidence with explicit presence receipts.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd
import pyarrow.parquet as pq

from . import contract


class CensusError(RuntimeError):
    """Raised when a committed upstream census read fails closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_manifest(package: Path) -> dict[str, str]:
    """Verify every file listed in the package SHA256SUMS.json (fail-closed)."""
    sums_path = package / "SHA256SUMS.json"
    if not sums_path.exists():
        raise CensusError(f"missing SHA256SUMS.json in {package}")
    expected = json.loads(sums_path.read_text(encoding="utf-8"))
    actual: dict[str, str] = {}
    for relative, wanted in expected.items():
        member = (package / relative).resolve()
        if not member.is_relative_to(package.resolve()):
            raise CensusError(f"manifest path escapes package: {relative}")
        if not member.exists():
            raise CensusError(f"manifest file missing: {relative}")
        digest = sha256_file(member)
        if digest != wanted:
            raise CensusError(
                f"SHA256 mismatch for {relative}: got {digest}, expected {wanted}"
            )
        actual[relative] = digest
    return actual


@dataclass(frozen=True)
class SourceCensusRow:
    key: str
    committed: bool
    grade: str
    present: bool
    hash_receipt: str | None
    rows: int
    issue_min: str | None
    issue_max: str | None
    timestamp_min: str | None
    timestamp_max: str | None
    clock: str
    note: str


@dataclass
class Census:
    root: Path
    rows: list[SourceCensusRow] = field(default_factory=list)
    committed_hashes: dict[str, dict[str, str]] = field(default_factory=dict)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([row.__dict__ for row in self.rows])


def _census_parquet_table(
    root: Path, table: str, clock: str
) -> tuple[bool, pd.DataFrame]:
    path = (root / table).resolve()
    if not path.exists():
        return False, pd.DataFrame()
    frame = pq.read_table(path).to_pandas()
    return True, frame


def _census_sqlite_table(
    root: Path, table: str, clock: str
) -> tuple[bool, pd.DataFrame]:
    db_path, _, table_name = table.partition(":")
    path = (root / db_path).resolve()
    if not path.exists():
        return False, pd.DataFrame()
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        frame = pd.read_sql_query(f'SELECT * FROM "{table_name}"', con)
    finally:
        con.close()
    return True, frame


def _census_committed_package(
    root: Path, key: str, table: str, clock: str, note: str, grade: str
) -> tuple[SourceCensusRow, dict[str, str]]:
    package_key = {
        "bj214_selected_market_observations": "bj214",
        "bj203_devig_euro_probability": "bj203",
        "bj204_avg_eu": "bj204",
        "bj180_match_probability_freeze": "bj180",
    }[key]
    package = contract.upstream_path(root, package_key)
    hashes = _verify_manifest(package)
    path = (root / table).resolve()
    if not path.exists():
        raise CensusError(f"committed source missing: {table}")
    if str(table).endswith(".csv.gz") or str(table).endswith(".csv"):
        frame = pd.read_csv(path, compression="gzip" if str(table).endswith(".gz") else None)
    else:
        frame = pq.read_table(path).to_pandas()
    # #214 observations carry issue inside match_id ("26051_001"); expose it.
    if key == "bj214_selected_market_observations" and "match_id" in frame.columns:
        frame["issue"] = frame["match_id"].astype(str).str.split("_").str[0]
    # #203 feature values are per-cell via cell_join_key; expose issue through
    # the identity map so census can report issue coverage.
    if key == "bj203_devig_euro_probability" and "cell_join_key" in frame.columns:
        identity = pq.read_table(
            contract.upstream_path(root, "bj203") / "inference/cell_identity.parquet"
        ).to_pandas()
        key_map = identity[["cell_join_key", "issue"]].drop_duplicates()
        key_map["cell_join_key"] = key_map["cell_join_key"].astype(str)
        issue_map = dict(zip(key_map["cell_join_key"], key_map["issue"].astype(str)))
        frame = frame.copy()
        frame["issue"] = frame["cell_join_key"].astype(str).map(issue_map)
    row = _profile_frame(key, True, grade, frame, clock, note, hashes=hashes)
    return row, hashes


def _profile_frame(
    key: str,
    committed: bool,
    grade: str,
    frame: pd.DataFrame,
    clock: str,
    note: str,
    *,
    hashes: dict[str, str] | None = None,
) -> SourceCensusRow:
    hash_receipt = None
    if hashes is not None:
        hash_receipt = hashlib.sha256(
            json.dumps(hashes, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
    if frame.empty:
        return SourceCensusRow(
            key=key, committed=committed, grade=grade, present=True,
            hash_receipt=hash_receipt, rows=0, issue_min=None, issue_max=None,
            timestamp_min=None, timestamp_max=None, clock=clock, note=note,
        )
    issue_min: str | None = None
    issue_max: str | None = None
    if "issue" in frame.columns:
        issues = frame["issue"].dropna().astype(str)
        if not issues.empty:
            issue_min = str(issues.min())
            issue_max = str(issues.max())
    timestamp_min = timestamp_max = None
    if clock in frame.columns:
        ts = pd.to_datetime(frame[clock], errors="coerce", utc=True).dropna()
        if not ts.empty:
            timestamp_min = ts.min().isoformat()
            timestamp_max = ts.max().isoformat()
    return SourceCensusRow(
        key=key, committed=committed, grade=grade, present=True,
        hash_receipt=hash_receipt, rows=len(frame), issue_min=issue_min,
        issue_max=issue_max, timestamp_min=timestamp_min,
        timestamp_max=timestamp_max, clock=clock, note=note,
    )


def _census_raw_asset(
    root: Path, candidate: dict, loader: Callable[[Path, str, str], tuple[bool, pd.DataFrame]]
) -> SourceCensusRow:
    present, frame = loader(root, candidate["table"], candidate["clock"])
    if not present:
        return SourceCensusRow(
            key=candidate["key"], committed=False, grade=candidate["grade"],
            present=False, hash_receipt=None, rows=0, issue_min=None,
            issue_max=None, timestamp_min=None, timestamp_max=None,
            clock=candidate["clock"], note=candidate["note"] + " [ASSET ABSENT]",
        )
    asset_path = (root / candidate["table"].partition(":")[0]).resolve()
    return _profile_frame(
        candidate["key"], False, candidate["grade"], frame, candidate["clock"],
        candidate["note"], hashes={"asset": sha256_file(asset_path)},
    )


def build_census(root: Path) -> Census:
    """Profile every SP/EU/POWER source candidate at ``root``."""
    census = Census(root=root)
    committed_hashes: dict[str, dict[str, str]] = {}

    for candidate in contract.SP_SOURCE_CANDIDATES:
        if candidate["committed"]:
            row, hashes = _census_committed_package(
                root, candidate["key"], candidate["table"],
                candidate["clock"], candidate["note"], candidate["grade"],
            )
            committed_hashes[candidate["key"]] = hashes
        else:
            row = _census_raw_asset(
                root, candidate,
                _census_sqlite_table
                if ":" in candidate["table"]
                else _census_parquet_table,
            )
        census.rows.append(row)

    for candidate in contract.EU_SOURCE_CANDIDATES + contract.POWER_SOURCE_CANDIDATES:
        row, hashes = _census_committed_package(
            root, candidate["key"], candidate["table"],
            candidate["clock"], candidate["note"], candidate["grade"],
        )
        committed_hashes[candidate["key"]] = hashes
        census.rows.append(row)

    census.committed_hashes = committed_hashes
    return census
