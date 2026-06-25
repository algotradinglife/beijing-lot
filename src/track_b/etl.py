"""Track B P0 — parse the 北单采集器 beidan.xlsm「数据」sheet into a clean
per-match feature table (sqlite). Header-driven + layout-validated so a changed
collector format fails loudly instead of silently mis-parsing.

Layout (verified on the 853-col sheet, 2014-2025):
  identity            cols 0..17
  欧赔 (1X2)           cols 18..197   (15 books × 12 = 4 timepoints × (H,D,A))
  凯利 (skip)          col 198 header, 199..378
  亚盘 (Asian hcp)     col 379 header, 380..595 (books × 12 = 4 tp × (homeHK,line,awayHK))
  大小球 (O/U)          col 596 header, 597..812 (books × 12 = 4 tp × (over,total,under))
  sclassid/score tail  col 813..
Timepoints within a 12-col block: 初=0, 赛前1小时=1, 赛前10小时=2, 终=3  → cols c+3·tp.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, Iterator, List, Optional, Tuple

from src.track_b.odds import (
    result_code, parse_rank, devig3, asian_devig, consensus_mean, valid_odds,
)

# identity column indices
ISSUE, DATE, LEAGUE, RANK_H, HOME, SCORE, AWAY, RANK_A = 0, 2, 3, 4, 5, 6, 7, 8
HCAP, HT_SCORE, WL, TOTGOALS, HT_FT, MATCHID, T10H, HOME_ID, AWAY_ID = \
    9, 10, 11, 12, 13, 14, 15, 16, 17

EURO_START, EURO_END = 18, 198
ASIAN_HEADER, ASIAN_START, ASIAN_END = 379, 380, 596
OU_HEADER, OU_START, OU_END = 596, 597, 813
KELLY_HEADER, SCLASSID = 198, 813
BOOK_W = 12
TP_OPEN, TP_CLOSE = 0, 3            # 初 / 终
CROWN_EU, PINNACLE_EU = 18, 174     # 皇冠 / Pinna* euro block starts


def validate_layout(r0: List) -> None:
    """Fail loudly if the collector's column template drifted."""
    def s(i):
        return str(r0[i]) if i < len(r0) and r0[i] is not None else ""
    checks = {ISSUE: "期号", HCAP: "让球", WL: "胜负", MATCHID: "编号",
              CROWN_EU: "皇冠", KELLY_HEADER: "凯利", ASIAN_HEADER: "亚盘",
              OU_HEADER: "大小球", SCLASSID: "sclassid", PINNACLE_EU: "Pinna*"}
    bad = {i: (exp, s(i)) for i, exp in checks.items() if s(i) != exp}
    if bad:
        raise ValueError(f"unexpected xlsm layout (col->[expected,got]): {bad}")
    for name, (lo, hi) in {"euro": (EURO_START, EURO_END),
                           "asian": (ASIAN_START, ASIAN_END),
                           "ou": (OU_START, OU_END)}.items():
        if (hi - lo) % BOOK_W:
            raise ValueError(f"{name} span {hi-lo} not a multiple of {BOOK_W}")


def book_starts(lo: int, hi: int) -> List[int]:
    return list(range(lo, hi, BOOK_W))


def _tp(row, c: int, tp: int) -> Tuple:
    """The 3 values of block at col c, timepoint tp."""
    b = c + 3 * tp
    return (row[b], row[b + 1], row[b + 2])


def euro_consensus_p(row, starts: List[int], tp: int) -> Optional[Tuple[float, float, float]]:
    """Mean de-vigged (p3,p1,p0) over books with valid (H,D,A) at timepoint tp."""
    ps = []
    for c in starts:
        h, d, a = _tp(row, c, tp)
        if valid_odds(h, d, a):
            ps.append(devig3(float(h), float(d), float(a)))
    if not ps:
        return None
    n = len(ps)
    return (sum(p[0] for p in ps) / n, sum(p[1] for p in ps) / n,
            sum(p[2] for p in ps) / n)


def euro_book_p(row, c: int, tp: int) -> Optional[Tuple[float, float, float]]:
    h, d, a = _tp(row, c, tp)
    return devig3(float(h), float(d), float(a)) if valid_odds(h, d, a) else None


def asian_consensus(row, starts: List[int], tp: int) -> Tuple[Optional[float], Optional[float]]:
    """(mean p_home_cover, median handicap line) over books with valid prices."""
    ps, lines = [], []
    for c in starts:
        home, line, away = _tp(row, c, tp)
        if (home is not None and away is not None and _num(home) and _num(away)
                and float(home) > 0 and float(away) > 0):
            ph, _pa = asian_devig(float(home), float(away))
            ps.append(ph)
            if line is not None and _num(line):
                lines.append(float(line))
    p = sum(ps) / len(ps) if ps else None
    line = sorted(lines)[len(lines) // 2] if lines else None
    return p, line


def _num(v) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def season_year(issue) -> Optional[int]:
    try:
        return 2000 + int(str(issue)[:2])
    except (ValueError, TypeError):
        return None


def parse_match(row, eu_starts, as_starts) -> Optional[Dict]:
    """One data row -> feature dict, or None if no usable result."""
    rc = result_code(row[WL])
    if rc is None:
        return None
    eu_open = euro_consensus_p(row, eu_starts, TP_OPEN)
    eu_close = euro_consensus_p(row, eu_starts, TP_CLOSE)
    crown = euro_book_p(row, CROWN_EU, TP_CLOSE)
    pinn = euro_book_p(row, PINNACLE_EU, TP_CLOSE)
    as_open_p, _ = asian_consensus(row, as_starts, TP_OPEN)
    as_close_p, as_line = asian_consensus(row, as_starts, TP_CLOSE)
    d = row[DATE]
    rec = {
        "match_id": _s(row[MATCHID]), "issue": _s(row[ISSUE]),
        "season": season_year(row[ISSUE]),
        "kickoff": d.isoformat() if hasattr(d, "isoformat") else _s(d),
        "league": _s(row[LEAGUE]), "home": _s(row[HOME]), "away": _s(row[AWAY]),
        "home_id": _s(row[HOME_ID]), "away_id": _s(row[AWAY_ID]),
        # 让球 blank in the collector == no handicap == line 0 (straight 1X2,
        # O5-comparable). Verified by the line=0 calibration in P1.
        "beidan_hcap": (0.0 if _f(row[HCAP]) is None else _f(row[HCAP])),
        "result_code": rc,
        "score": _s(row[SCORE]), "ht_score": _s(row[HT_SCORE]),
        "total_goals": _f(row[TOTGOALS]),
        "rank_home": parse_rank(row[RANK_H]), "rank_away": parse_rank(row[RANK_A]),
        # consensus de-vigged probs (3/1/0), close + open (for movement)
        "p_close_3": _g(eu_close, 0), "p_close_1": _g(eu_close, 1), "p_close_0": _g(eu_close, 2),
        "p_open_3": _g(eu_open, 0), "p_open_1": _g(eu_open, 1), "p_open_0": _g(eu_open, 2),
        "crown_close_3": _g(crown, 0), "crown_close_1": _g(crown, 1), "crown_close_0": _g(crown, 2),
        "pinn_close_3": _g(pinn, 0), "pinn_close_1": _g(pinn, 1), "pinn_close_0": _g(pinn, 2),
        # asian handicap consensus
        "asian_p_home_close": as_close_p, "asian_p_home_open": as_open_p,
        "asian_line": as_line,
    }
    return rec


def _s(v):
    return None if v is None else str(v).strip()


def _f(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _g(t, i):
    return None if t is None else t[i]


def iter_matches(xlsm_path: str) -> Iterator[Dict]:
    import openpyxl
    wb = openpyxl.load_workbook(xlsm_path, read_only=True, data_only=True)
    ws = wb["数据"]
    it = ws.iter_rows(values_only=True)
    r0 = list(next(it))
    next(it)  # row1 sub-labels (unused; layout validated by r0)
    validate_layout(r0)
    eu_starts = book_starts(EURO_START, EURO_END)
    as_starts = book_starts(ASIAN_START, ASIAN_END)
    for row in it:
        if row is None or row[MATCHID] is None:
            continue
        rec = parse_match(list(row), eu_starts, as_starts)
        if rec is not None:
            yield rec
    wb.close()


COLUMNS = ["match_id", "issue", "season", "kickoff", "league", "home", "away",
           "home_id", "away_id", "beidan_hcap", "result_code", "score", "ht_score",
           "total_goals", "rank_home", "rank_away",
           "p_close_3", "p_close_1", "p_close_0", "p_open_3", "p_open_1", "p_open_0",
           "crown_close_3", "crown_close_1", "crown_close_0",
           "pinn_close_3", "pinn_close_1", "pinn_close_0",
           "asian_p_home_close", "asian_p_home_open", "asian_line"]


def build_sqlite(xlsm_path: str, db_path: str) -> int:
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE IF EXISTS matches")
    con.execute(f"CREATE TABLE matches ({', '.join(c + ' ' + _coltype(c) for c in COLUMNS)})")
    n = 0
    rows = []
    for rec in iter_matches(xlsm_path):
        rows.append(tuple(rec[c] for c in COLUMNS))
        if len(rows) >= 5000:
            con.executemany(f"INSERT INTO matches VALUES ({','.join('?' * len(COLUMNS))})", rows)
            n += len(rows); rows = []
    if rows:
        con.executemany(f"INSERT INTO matches VALUES ({','.join('?' * len(COLUMNS))})", rows)
        n += len(rows)
    con.execute("CREATE INDEX idx_season ON matches(season)")
    con.commit(); con.close()
    return n


def _coltype(c: str) -> str:
    if c in ("season",):
        return "INTEGER"
    if c.startswith(("p_", "crown_", "pinn_", "asian_")) or c in ("beidan_hcap", "total_goals", "rank_home", "rank_away"):
        return "REAL"
    return "TEXT"
