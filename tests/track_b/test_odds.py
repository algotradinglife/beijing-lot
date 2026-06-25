"""TDD for src/track_b/odds.py — pure parse/odds helpers."""
import math

from src.track_b.odds import (
    result_code, parse_rank, devig3, asian_devig, consensus_mean, valid_odds,
)


def test_result_code():
    assert result_code("胜") == "3"
    assert result_code("平") == "1"
    assert result_code("负") == "0"
    assert result_code(None) is None
    assert result_code("") is None
    assert result_code("取消") is None


def test_parse_rank():
    assert parse_rank("[3]") == 3
    assert parse_rank("[18]") == 18
    assert parse_rank(None) is None
    assert parse_rank("[]") is None
    assert parse_rank("-") is None


def test_devig3_normalizes():
    p = devig3(2.0, 4.0, 4.0)
    assert abs(p[0] - 0.5) < 1e-12 and abs(p[1] - 0.25) < 1e-12 and abs(p[2] - 0.25) < 1e-12
    assert abs(sum(p) - 1.0) < 1e-12


def test_asian_devig_level_handicap():
    # equal HK odds -> 50/50
    ph, pa = asian_devig(1.0, 1.0)
    assert abs(ph - 0.5) < 1e-12 and abs(pa - 0.5) < 1e-12
    assert abs(ph + pa - 1.0) < 1e-12
    # lower home price -> home favoured (higher prob)
    ph2, pa2 = asian_devig(0.85, 1.03)
    assert ph2 > 0.5 and ph2 > pa2


def test_consensus_mean():
    assert consensus_mean([2.0, 4.0, None]) == 3.0
    assert consensus_mean([None, None]) is None
    assert consensus_mean([]) is None


def test_valid_odds():
    assert valid_odds(2.45, 3.2, 2.65)
    assert not valid_odds(2.45, None, 2.65)
    assert not valid_odds(2.45, 1.0, 2.65)   # 1.0 not > 1
    assert not valid_odds(2.45, "x", 2.65)
