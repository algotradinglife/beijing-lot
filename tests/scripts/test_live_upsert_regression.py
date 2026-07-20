from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scrape_500_bjdc import create_schema as create_500_schema
from scripts.scrape_500_bjdc import upsert_matches
from scripts.scrape_nowscore_bjdc import create_schema as create_nowscore_schema
from scripts.scrape_nowscore_bjdc import reconcile_finished_settlements
from scripts.scrape_nowscore_bjdc import upsert_match_rows
from src.sqlite_runtime import connect_sqlite


def _match_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "issue": "99123",
        "match_idx": 1,
        "fid": 1001,
        "league": "测试联赛",
        "home": "主队",
        "away": "客队",
        "end_time": "2026-07-04 20:00:00",
        "schedule_date": "2026-07-04",
        "handicap_line": 0.0,
        "disabled": "",
        "home_rank": 1,
        "away_rank": 2,
        "bg_color": "",
        "score": "2:1",
        "result_label": "胜",
        "result_code": "3",
        "winning_sp": 2.45,
        "sp_home": 2.45,
        "sp_draw": 3.20,
        "sp_away": 2.80,
        "avg_odds_home": 2.35,
        "avg_odds_draw": 3.10,
        "avg_odds_away": 2.95,
        "asian_handicap": "平手",
        "raw_value": "old-value",
        "raw_row_hash": "old-hash",
        "fetched_at": "2026-07-04 01:00:00",
    }
    row.update(overrides)
    return row


def _nowscore_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "issue": "99123",
        "match_idx": 1,
        "provider_match_id": "500001",
        "fetched_at": "2026-07-04T01:00:00Z",
        "schedule_date": "2026-07-04",
        "league": "测试联赛",
        "kickoff_time": "20:00",
        "status_text": "完场",
        "status": "finished",
        "can_sale": 0,
        "home": "主队",
        "away": "客队",
        "handicap_text": "0",
        "handicap_line": 0.0,
        "score": "2-1",
        "halftime_score": "1-0",
        "result_code": "3",
        "panlu_url": "https://example.test/panlu",
        "asian_url": "https://example.test/asian",
        "europe_url": "https://example.test/europe",
        "analysis_url": "https://example.test/analysis",
        "recommendation_url": "https://example.test/recommend",
        "sp_url": "https://example.test/sp",
        "raw_row_hash": "old-hash",
        "raw_row": "<tr>old</tr>",
    }
    row.update(overrides)
    return row


def test_500_match_upsert_preserves_settled_fields_against_empty_refresh(tmp_path: Path) -> None:
    db_path = tmp_path / "500.sqlite"
    with connect_sqlite(db_path, row_factory=True) as conn:
        create_500_schema(conn)
        upsert_matches(conn, [_match_row()])

        upsert_matches(
            conn,
            [
                _match_row(
                    league="",
                    home="",
                    away="",
                    score="",
                    result_label=None,
                    result_code=None,
                    winning_sp=None,
                    sp_home=None,
                    sp_draw=None,
                    sp_away=None,
                    fetched_at="2026-07-04 02:00:00",
                    raw_row_hash="empty-refresh",
                )
            ],
        )
        row = conn.execute("SELECT * FROM matches WHERE issue='99123' AND match_idx=1").fetchone()
        assert row["league"] == "测试联赛"
        assert row["home"] == "主队"
        assert row["score"] == "2:1"
        assert row["result_code"] == "3"
        assert row["winning_sp"] == 2.45
        assert row["sp_home"] == 2.45
        assert row["fetched_at"] == "2026-07-04 02:00:00"
        assert row["raw_row_hash"] == "empty-refresh"

        upsert_matches(conn, [_match_row(score="2:2", result_label="平", result_code="1", winning_sp=3.10)])
        corrected = conn.execute("SELECT score, result_code, winning_sp FROM matches").fetchone()
        assert dict(corrected) == {"score": "2:2", "result_code": "1", "winning_sp": 3.10}


def test_nowscore_upsert_preserves_finished_result_against_empty_refresh(tmp_path: Path) -> None:
    db_path = tmp_path / "nowscore.sqlite"
    with connect_sqlite(db_path, row_factory=True) as conn:
        create_nowscore_schema(conn)
        upsert_match_rows(conn, [_nowscore_row()])

        upsert_match_rows(
            conn,
            [
                _nowscore_row(
                    status_text="",
                    status="scheduled",
                    score="",
                    halftime_score="",
                    result_code=None,
                    fetched_at="2026-07-04T02:00:00Z",
                    raw_row_hash="empty-refresh",
                    raw_row="<tr>empty</tr>",
                )
            ],
        )
        row = conn.execute("SELECT * FROM nowscore_bjdc_matches WHERE issue='99123' AND match_idx=1").fetchone()
        assert row["status_text"] == "完场"
        assert row["status"] == "finished"
        assert row["score"] == "2-1"
        assert row["halftime_score"] == "1-0"
        assert row["result_code"] == "3"
        assert row["fetched_at"] == "2026-07-04T02:00:00Z"
        assert row["raw_row_hash"] == "empty-refresh"
        assert row["raw_row"] == "<tr>empty</tr>"

        upsert_match_rows(
            conn,
            [
                _nowscore_row(
                    score="2-2",
                    halftime_score="1-1",
                    result_code="1",
                    raw_row_hash="corrected",
                    raw_row="<tr>corrected</tr>",
                )
            ],
        )
        corrected = conn.execute(
            "SELECT score, halftime_score, result_code, raw_row_hash FROM nowscore_bjdc_matches"
        ).fetchone()
        assert dict(corrected) == {
            "score": "2-2",
            "halftime_score": "1-1",
            "result_code": "1",
            "raw_row_hash": "corrected",
        }


def test_nowscore_finished_row_backfills_missing_500_settlement(tmp_path: Path) -> None:
    db_path = tmp_path / "settlement.sqlite"
    with connect_sqlite(db_path, row_factory=True) as conn:
        create_500_schema(conn)
        create_nowscore_schema(conn)
        upsert_matches(
            conn,
            [
                _match_row(
                    score="",
                    result_label=None,
                    result_code=None,
                    winning_sp=None,
                    handicap_line=-1.0,
                    sp_home=2.45,
                    sp_draw=3.20,
                    sp_away=2.80,
                )
            ],
        )
        upsert_match_rows(
            conn,
            [
                _nowscore_row(
                    handicap_line=-1.0,
                    score="2-1",
                    result_code="1",
                )
            ],
        )

        assert reconcile_finished_settlements(conn, "99123") == 1
        settled = conn.execute(
            "SELECT score, result_label, result_code, winning_sp FROM matches"
        ).fetchone()
        assert dict(settled) == {
            "score": "2-1",
            "result_label": "平",
            "result_code": "1",
            "winning_sp": 3.20,
        }

        # A later score refresh cannot overwrite the completed official row.
        assert reconcile_finished_settlements(conn, "99123") == 0
