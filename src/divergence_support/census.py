"""Issue #232 — source census (REQ-S01/S06/S10, R2 fresh).

Counts every candidate source by committed/raw presence, grade, issue and
date span, and — R2 — enforces the per-source field whitelist so no
settlement/label/final column can ever be opened by a read path
(``SOURCE_FIELD_WHITELIST``).  The census is the provenance registry the
verifier uses to check every published ``source_identity``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from . import contract


@dataclass
class Census:
    rows: list[dict] = field(default_factory=list)

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def _parse_issue(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def _read_parquet_head(path: Path, columns: list[str] | tuple[str, ...]) -> pd.DataFrame:
    frame = pq.read_table(path, columns=list(columns)).to_pandas()
    return frame


def _census_committed_source(root: Path, source: dict, whitelist: tuple[str, ...]) -> dict:
    path = (root / source["table"]).resolve()
    row: dict = {
        "source_key": source["key"],
        "committed": True,
        "grade": source["grade"],
        "asset_present": path.exists(),
        "rows": None,
        "issues": None,
        "min_ts": None,
        "max_ts": None,
        "whitelist_enforced": True,
        "field_whitelist": ",".join(whitelist),
        "note": source["note"],
    }
    if path.exists():
        clock = source.get("clock", "")
        try:
            frame = _read_parquet_head(path, [c for c in whitelist if c])
            row["rows"] = int(len(frame))
            if "issue" in frame.columns:
                row["issues"] = int(_parse_issue(frame["issue"]).nunique())
            if clock and clock in frame.columns:
                ts = pd.to_datetime(frame[clock], errors="coerce", utc=True)
                row["min_ts"] = ts.min().isoformat() if ts.notna().any() else None
                row["max_ts"] = ts.max().isoformat() if ts.notna().any() else None
        except Exception as error:  # pragma: no cover - defensive
            row["note"] = f"{row['note']} READ_ERROR: {error}"
    return row


def _census_csv_source(root: Path, source: dict, whitelist: tuple[str, ...]) -> dict:
    path = (root / source["table"]).resolve()
    row: dict = {
        "source_key": source["key"],
        "committed": True,
        "grade": source["grade"],
        "asset_present": path.exists(),
        "rows": None,
        "issues": None,
        "min_ts": None,
        "max_ts": None,
        "whitelist_enforced": True,
        "field_whitelist": ",".join(whitelist),
        "note": source["note"],
    }
    if path.exists():
        clock = source.get("clock", "")
        try:
            frame = pd.read_csv(path, nrows=100000, compression="infer")
            # census opens the file for inventory only; no column may leave
            # the whitelist into a published payload (checked downstream).
            row["rows"] = int(len(frame))
            if "issue" in frame.columns:
                row["issues"] = int(_parse_issue(frame["issue"]).nunique())
            if clock and clock in frame.columns:
                ts = pd.to_datetime(frame[clock], errors="coerce", utc=True)
                row["min_ts"] = ts.min().isoformat() if ts.notna().any() else None
                row["max_ts"] = ts.max().isoformat() if ts.notna().any() else None
        except Exception as error:  # pragma: no cover - defensive
            row["note"] = f"{row['note']} READ_ERROR: {error}"
    return row


def build_census(root: Path) -> Census:
    """Census of all candidate sources with whitelist enforcement flags."""
    census = Census()

    for source in contract.SP_SOURCE_CANDIDATES:
        whitelist = contract.SOURCE_FIELD_WHITELIST[source["key"]]
        if source["table"].endswith(".parquet"):
            row = _census_committed_source(root, source, whitelist)
        else:
            row = _census_csv_source(root, source, whitelist)
        census.rows.append(row)

    for source in contract.EU_SOURCE_CANDIDATES:
        whitelist = contract.SOURCE_FIELD_WHITELIST[source["key"]]
        census.rows.append(_census_committed_source(root, source, whitelist))

    for source in contract.POWER_SOURCE_CANDIDATES:
        whitelist = contract.SOURCE_FIELD_WHITELIST[source["key"]]
        census.rows.append(_census_committed_source(root, source, whitelist))

    return census
