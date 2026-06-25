"""TDD for src/track_b/etl.py — layout validation + per-row parsing (synthetic)."""
import pytest

from src.track_b import etl
from src.track_b.etl import (
    validate_layout, book_starts, season_year, parse_match,
    EURO_START, EURO_END, ASIAN_START, ASIAN_END,
)


def good_r0():
    r0 = [None] * 853
    r0[etl.ISSUE] = "期号"; r0[etl.HCAP] = "让球"; r0[etl.WL] = "胜负"
    r0[etl.MATCHID] = "编号"; r0[etl.CROWN_EU] = "皇冠"; r0[etl.KELLY_HEADER] = "凯利"
    r0[etl.ASIAN_HEADER] = "亚盘"; r0[etl.OU_HEADER] = "大小球"
    r0[etl.SCLASSID] = "sclassid"; r0[etl.PINNACLE_EU] = "Pinna*"
    return r0


def good_r1():
    r1 = [None] * 853
    for c in book_starts(etl.EURO_START, etl.EURO_END):
        r1[c] = "欧赔-初"; r1[c + 9] = "欧赔-终"
    for c in book_starts(etl.ASIAN_START, etl.ASIAN_END):
        r1[c] = "亚盘-初"; r1[c + 9] = "亚盘-终"
    return r1


def test_validate_layout_ok():
    validate_layout(good_r0(), good_r1())  # no raise


def test_validate_layout_detects_header_drift():
    r0 = good_r0(); r0[etl.ASIAN_HEADER] = "something else"
    with pytest.raises(ValueError):
        validate_layout(r0, good_r1())


def test_validate_layout_detects_per_block_drift():
    # a single shifted per-book sub-header must be caught
    r0, r1 = good_r0(), good_r1()
    r1[30] = "something"          # 澳门 euro block start label corrupted
    with pytest.raises(ValueError):
        validate_layout(r0, r1)


def test_book_starts():
    assert book_starts(EURO_START, EURO_END) == list(range(18, 198, 12))
    assert len(book_starts(EURO_START, EURO_END)) == 15
    assert len(book_starts(ASIAN_START, ASIAN_END)) == 18


def test_season_year():
    assert season_year("140101") == 2014
    assert season_year("25042") == 2025
    assert season_year(None) is None


def make_row():
    row = [None] * 853
    row[etl.ISSUE] = "140101"; row[etl.DATE] = "2014-01-01"; row[etl.WL] = "胜"
    row[etl.MATCHID] = "999"; row[etl.HCAP] = 0.0; row[etl.LEAGUE] = "x"
    row[etl.HOME] = "H"; row[etl.AWAY] = "A"; row[etl.HOME_ID] = "1"; row[etl.AWAY_ID] = "2"
    row[etl.RANK_H] = "[3]"; row[etl.RANK_A] = "[8]"; row[etl.TOTGOALS] = 2
    row[etl.SCORE] = "1-0"; row[etl.HT_SCORE] = "0-0"
    # euro: crown(18) close 27-29, open 18-20; book@30 close 39-41; pinnacle(174) close 183-185
    for c in (18, 30, 174):
        row[c + 9], row[c + 10], row[c + 11] = 2.0, 4.0, 4.0   # close (tp=3) -> p .5/.25/.25
    row[18], row[19], row[20] = 2.0, 4.0, 4.0                  # crown open
    # asian crown(380): close 389-391 = (home_hk, line, away_hk)
    row[389], row[390], row[391] = 1.0, 0.0, 1.0               # level -> p_home 0.5
    row[380], row[381], row[382] = 1.0, 0.0, 1.0
    return row


def test_parse_match_full():
    rec = parse_match(make_row(), book_starts(EURO_START, EURO_END),
                      book_starts(ASIAN_START, ASIAN_END))
    assert rec["result_code"] == "3"
    assert rec["match_id"] == "999" and rec["season"] == 2014
    assert rec["rank_home"] == 3 and rec["rank_away"] == 8
    assert abs(rec["p_close_3"] - 0.5) < 1e-9
    assert abs(rec["p_close_1"] - 0.25) < 1e-9 and abs(rec["p_close_0"] - 0.25) < 1e-9
    assert abs(rec["crown_close_3"] - 0.5) < 1e-9 and abs(rec["pinn_close_3"] - 0.5) < 1e-9
    assert abs(rec["asian_p_home_close"] - 0.5) < 1e-9 and rec["asian_line"] == 0.0
    assert rec["beidan_hcap"] == 0.0


def test_blank_handicap_maps_to_zero():
    row = make_row(); row[etl.HCAP] = None        # collector blank == no handicap
    rec = parse_match(row, book_starts(EURO_START, EURO_END),
                      book_starts(ASIAN_START, ASIAN_END))
    assert rec["beidan_hcap"] == 0.0


def test_parse_match_skips_no_result():
    row = make_row(); row[etl.WL] = "取消"
    assert parse_match(row, book_starts(EURO_START, EURO_END),
                       book_starts(ASIAN_START, ASIAN_END)) is None
