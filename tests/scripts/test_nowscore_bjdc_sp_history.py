from __future__ import annotations

import sys
import json
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import nowscore_bjdc_sp_history as history  # noqa: E402
from src.multimarket_p0 import HKT  # noqa: E402


PAGE = b"""<html><head><title>Sp\xe5\x80\xbc\xe5\x8f\x98\xe5\x8c\x96\xe8\xa1\xa8 (X)</title></head><body>
<table><tr><td>0\xe7\x90\x83</td><td>1\xe7\x90\x83</td><td>2\xe7\x90\x83</td><td>3\xe7\x90\x83</td><td>4\xe7\x90\x83</td><td>5\xe7\x90\x83</td><td>6\xe7\x90\x83</td><td>7+\xe7\x90\x83</td><td>\xe5\x8f\x98\xe5\x8c\x96\xe6\x97\xb6\xe9\x97\xb4</td></tr>
<tr><td>8</td><td>5</td><td>3</td><td>4</td><td>8</td><td>15</td><td>30</td><td>50</td><td>07-16 14:01</td></tr>
<tr><td>9</td><td>6</td><td>3.2</td><td>4.1</td><td>8.2</td><td>16</td><td>31</td><td>51</td><td>07-16 13:59</td></tr>
<tr><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>07-16 13:30</td></tr>
</table></body></html>"""


def test_parse_and_strict_10h_selection() -> None:
    kickoff = datetime(2026, 7, 17, 0, 0, tzinfo=HKT)
    headers, vectors = history.parse_history_page(PAGE, 6, kickoff)
    assert headers == ("0球", "1球", "2球", "3球", "4球", "5球", "6球", "7+球")
    selected = history.select_asof(vectors, kickoff)
    assert selected.source_ts_hkt == "2026-07-16T13:59+08:00"
    assert selected.values[0] == 9


def test_common_segment_asof_produces_different_match_countdowns() -> None:
    asof = datetime(2026, 7, 16, 13, 59, tzinfo=HKT)
    headers, vectors = history.parse_history_page(PAGE, 6, datetime(2026, 7, 17, 0, 0, tzinfo=HKT))
    selected = history.select_at(vectors, asof)
    first = history.selected_rows(
        issue="X", match_idx=1, typeid=6, kickoff_hkt=datetime(2026, 7, 17, 0, 0, tzinfo=HKT),
        vector=selected, headers=headers, batch_id="B", source_url="U", asof_hkt=asof,
        selection_mode="segment_freeze",
    )[0]
    second = history.selected_rows(
        issue="X", match_idx=2, typeid=6, kickoff_hkt=datetime(2026, 7, 17, 3, 0, tzinfo=HKT),
        vector=selected, headers=headers, batch_id="B", source_url="U", asof_hkt=asof,
        selection_mode="segment_freeze",
    )[0]
    assert first["asof_hkt"] == second["asof_hkt"]
    assert first["minutes_to_kickoff"] == 601
    assert second["minutes_to_kickoff"] == 781


def test_year_inference_handles_new_year_boundary() -> None:
    kickoff = datetime(2027, 1, 1, 1, 0, tzinfo=HKT)
    assert history.infer_source_time("12-31 14:00", kickoff).isoformat() == "2026-12-31T14:00:00+08:00"


def test_rejects_incomplete_target_and_changed_header() -> None:
    kickoff = datetime(2026, 7, 17, 0, 0, tzinfo=HKT)
    _, vectors = history.parse_history_page(PAGE, 6, kickoff)
    with pytest.raises(history.NowscoreHistoryError, match="no complete"):
        history.select_asof(vectors, kickoff, hours_before=11)
    with pytest.raises(history.NowscoreHistoryError, match="header mismatch"):
        history.parse_history_page(PAGE.replace("0球".encode(), "零球".encode()), 6, kickoff)


def test_verify_manifest_accepts_legacy_10h_bundle(tmp_path: Path) -> None:
    manifest = {
        "schema_version": "nowscore_bjdc_sp_history_v1",
        "policy": {
            "execution_enabled": False,
            "roi_authorized": False,
            "selection_rule": "latest complete source vector at or before kickoff-10h",
        },
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert history.verify_manifest(path) == manifest
