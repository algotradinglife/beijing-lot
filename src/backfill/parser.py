"""Parse 500.com kaijiang.php HTML into match records.

The page is GB2312-encoded and contains one <tr> per match with the structure
documented in docs/research/data-sources-beidan.md.

We use lenient regex extraction within each row block so that small layout
drift (extra whitespace, missing nbsp cells) does not break parsing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta

# A row is a <tr>...<td>idx</td>...</tr>.  We anchor on a leading numeric idx
# so we don't catch unrelated table rows (header etc.).
_ROW_RE = re.compile(
    r'<tr[^>]*>\s*<td>(?P<idx>\d+)</td>(?P<body>.*?)</tr>',
    re.S,
)

_LEAGUE_RE = re.compile(r'class="league"[^>]*title="([^"]+)"')
_TIME_RE = re.compile(r'<td class="eng">\s*([0-9]{2}-[0-9]{2}\s+[0-9]{2}:[0-9]{2})\s*</td>')
_HOME_RE = re.compile(r'<td class="text_r"><a[^>]*title="([^"]+)"')
_HANDICAP_RE = re.compile(
    r'<td class="eng">\s*<span class="(?:green|black|red)">\s*([+\-]?\d+)\s*</span>'
)
_AWAY_RE = re.compile(r'<td class="text_l"><a[^>]*title="([^"]+)"')
_SCORE_RE = re.compile(r'<td class="eng">\s*\(?(\d+)\s*:\s*(\d+)\)?\s*</td>')
# winning SP shown in red.  Result cell precedes it.
_RESULT_AND_SP_RE = re.compile(
    r'<td>\s*([3210胜平负])\s*</td>\s*'
    r'<td>(?:&nbsp;|\s)*</td>\s*'
    r'<td class="eng red">\s*([0-9]+\.[0-9]+)\s*</td>'
)
# the three average European odds — last three plain decimal cells in the row.
_DECIMAL_TD_RE = re.compile(r'<td>\s*([0-9]+\.[0-9]+)\s*</td>')


_RESULT_MAP = {
    "胜": "3",
    "平": "1",
    "负": "0",
    "3": "3",
    "1": "1",
    "0": "0",
}


@dataclass
class MatchRow:
    issue: str
    match_idx: int
    league: str | None
    kickoff_ts: str | None
    home: str | None
    away: str | None
    handicap_line: int | None
    fthg: int | None
    ftag: int | None
    result_code: str | None
    winning_sp: float | None
    avg_eu_home: float | None
    avg_eu_draw: float | None
    avg_eu_away: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _issue_to_year(issue: str) -> int:
    """Map 5-digit YYNNN (post-2020) or 6-digit YYMMNN (pre-2020) to a 4-digit year."""
    issue = str(issue)
    yy = int(issue[:2])
    return 2000 + yy


def _kickoff_iso(issue: str, mmdd_hhmm: str) -> str | None:
    """Build kickoff time from the issue month and the displayed month/day.

    A Beijing issue can straddle New Year (for example issue 25011 starts on
    2024-12-31).  Resolve a displayed month more than six months away from the
    issue month onto the adjacent calendar year instead of blindly assigning
    the two-digit issue year to every row.
    """
    try:
        issue = str(issue)
        year = _issue_to_year(issue)
        issue_month = int(issue[2:4])
        event_month = int(mmdd_hhmm.strip()[:2])
        delta = event_month - issue_month
        if delta > 6:
            year -= 1
        elif delta < -6:
            year += 1
        # The displayed time is Beijing local (UTC+8), but for our purposes
        # we just preserve naive local time as ISO.
        dt = datetime.strptime(
            f"{year}-{mmdd_hhmm.strip()}", "%Y-%m-%d %H:%M"
        )
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_issue_html(html: str, issue: str) -> list[MatchRow]:
    """Parse the kaijiang.php HTML for one issue, return all match rows."""
    out: list[MatchRow] = []

    for m in _ROW_RE.finditer(html):
        idx = int(m.group("idx"))
        body = m.group("body")
        # Skip header / aggregate rows: a real match row has at least a league title
        league_m = _LEAGUE_RE.search(body)
        if not league_m:
            continue
        league = league_m.group(1)

        time_m = _TIME_RE.search(body)
        kickoff_ts = _kickoff_iso(issue, time_m.group(1)) if time_m else None

        home_m = _HOME_RE.search(body)
        away_m = _AWAY_RE.search(body)
        home = home_m.group(1) if home_m else None
        away = away_m.group(1) if away_m else None

        h_m = _HANDICAP_RE.search(body)
        handicap = int(h_m.group(1)) if h_m else None

        s_m = _SCORE_RE.search(body)
        if s_m:
            fthg, ftag = int(s_m.group(1)), int(s_m.group(2))
        else:
            fthg = ftag = None

        rs_m = _RESULT_AND_SP_RE.search(body)
        if rs_m:
            result_code = _RESULT_MAP.get(rs_m.group(1))
            winning_sp = float(rs_m.group(2))
        else:
            result_code = None
            winning_sp = None

        # Average European odds: the trailing three plain <td>X.YZ</td> cells.
        decimals = _DECIMAL_TD_RE.findall(body)
        avg_eu_home = avg_eu_draw = avg_eu_away = None
        if len(decimals) >= 3:
            try:
                avg_eu_home = float(decimals[-3])
                avg_eu_draw = float(decimals[-2])
                avg_eu_away = float(decimals[-1])
            except ValueError:
                pass

        out.append(MatchRow(
            issue=issue,
            match_idx=idx,
            league=league,
            kickoff_ts=kickoff_ts,
            home=home,
            away=away,
            handicap_line=handicap,
            fthg=fthg,
            ftag=ftag,
            result_code=result_code,
            winning_sp=winning_sp,
            avg_eu_home=avg_eu_home,
            avg_eu_draw=avg_eu_draw,
            avg_eu_away=avg_eu_away,
        ))

    return out
