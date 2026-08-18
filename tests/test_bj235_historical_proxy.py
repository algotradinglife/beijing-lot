"""Contract tests for #235's v2 historical relative-horizon proxy adapter.

The adapter reads only the source's fixture identity, native line, horizon label,
and pre-event 3/1/0 consensus prices.  It must not open outcomes, settlement, or
final snapshots to fill a missing historical proxy cell.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from bj235_timeseries import HistoricalProxyError, build_historical_proxy_frame


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
                # The missing away price must remain an explicit unavailable cell.
                (10, "euro_1x2", "1h", 2.2, 3.2, None),
                # Final is a prohibited horizon, not a fill source.
                (10, "euro_1x2", "final", 9.0, 9.0, 9.0),
            ],
        )
    return path


def test_historical_proxy_preserves_horizon_line_and_missingness_without_final_fill(tmp_path: Path) -> None:
    frame = build_historical_proxy_frame(_source(tmp_path / "history.sqlite"))

    assert set(frame["snapshot_horizon"]) == {"initial", "10h", "1h"}
    assert len(frame) == 9  # 3 horizons × canonical 3/1/0 cells
    assert set(frame["outcome_code"]) == {"3", "1", "0"}
    assert frame["source_id"].eq("beidan_xlsm_workbook").all()
    assert frame["time_semantics"].eq("SOURCE_RELATIVE_LABEL").all()
    assert frame["causal_grade"].eq("HISTORICAL_PROXY_LABEL_ONLY").all()
    assert frame["native_handicap_line"].eq(-1.0).all()
    assert frame["native_line_state_id"].nunique() == 1

    one_hour = frame.loc[frame["snapshot_horizon"].eq("1h")].set_index("outcome_code")
    assert bool(one_hour.loc["3", "availability_mask"]) is False
    assert one_hour.loc["0", "unavailable_reason"] == "INCOMPLETE_TRIPLET"
    assert pd.isna(one_hour.loc["0", "raw_sp"])
    assert one_hour.loc["3", "raw_sp"] == 2.2
    assert one_hour.loc["3", "normalized_inverse_sp_probability"] == 0.0

    initial = frame.loc[frame["snapshot_horizon"].eq("initial")].set_index("outcome_code")
    assert initial.loc["3", "raw_sp"] == 2.0
    assert initial.loc["3", "normalized_inverse_sp_probability"] == pytest.approx(6 / 13)


def test_historical_proxy_marks_non_numeric_native_line_unavailable(tmp_path: Path) -> None:
    source = _source(tmp_path / "history.sqlite")
    with sqlite3.connect(source) as con:
        con.execute("UPDATE matches SET handicap_line_norm = ? WHERE match_id = 10", ("bad-line",))
    frame = build_historical_proxy_frame(source)
    assert not frame["availability_mask"].any()
    assert frame["unavailable_reason"].eq("MISSING_NATIVE_LINE").all()


def test_historical_proxy_quarantines_null_identity_without_collapsing_it(tmp_path: Path) -> None:
    source = _source(tmp_path / "history.sqlite")
    with sqlite3.connect(source) as con:
        con.execute("INSERT INTO matches VALUES (?, ?, ?, ?)", (11, None, 2, -1.0))
        con.execute("INSERT INTO market_consensus VALUES (?, ?, ?, ?, ?, ?)", (11, "euro_1x2", "initial", 2.0, 3.0, 4.0))
    frame = build_historical_proxy_frame(source)
    assert len(frame) == 9
    assert frame.attrs["source_exclusion_counts"]["NULL_CANONICAL_IDENTITY"] == 1


def test_historical_proxy_rejects_duplicate_source_horizon_cell(tmp_path: Path) -> None:
    source = _source(tmp_path / "history.sqlite")
    with sqlite3.connect(source) as con:
        con.execute("INSERT INTO market_consensus VALUES (?, ?, ?, ?, ?, ?)", (10, "euro_1x2", "initial", 2.0, 3.0, 4.0))
    with pytest.raises(HistoricalProxyError, match="duplicate"):
        build_historical_proxy_frame(source)
