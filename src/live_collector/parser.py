"""HTML parsers for the Beidan live + settlement pages.

Three parsers, each operating on a string of HTML decoded to unicode:

- ``parse_issue_list(html)`` -> list of issue codes (期号) found in the
  trade.500.com bjdc page's ``<select id="expect_select">`` dropdown.
- ``parse_bet_page_500(html)`` -> list of MatchSnapshot rows scraped from
  the 500.com bjdc page (`tr class="vs_lines"`). Captures 3-SP vector,
  vol_pct vector (`tzbl`), avg European odds (`pjoz`), kickoff, teams,
  league, handicap.
- ``parse_bet_page_zgzcw(html)`` -> list of MatchSnapshot rows from the
  cp.zgzcw.com bdplayvsforJsp page (`tr id="tr_N"`). Used as fallback /
  cross-check; this page exposes ``spArr`` even when 500.com row is
  partially blanked.
- ``parse_kaijiang(html, issue)`` -> list of Settlement rows from
  zx.500.com/zqdc/kaijiang.php?playid=1.

All parsers tolerate missing fields by returning ``None`` for that field.
They never raise on a single bad row — they log + skip.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class MatchSnapshot:
    issue: str
    match_idx: int
    league: Optional[str] = None
    kickoff_ts: Optional[str] = None  # ISO string, may be None
    home: Optional[str] = None
    away: Optional[str] = None
    handicap_line: Optional[float] = None
    sp_3: Optional[float] = None  # home/win SP
    sp_1: Optional[float] = None  # draw SP
    sp_0: Optional[float] = None  # away/loss SP
    vol_pct_3: Optional[float] = None
    vol_pct_1: Optional[float] = None
    vol_pct_0: Optional[float] = None
    pool_total: Optional[float] = None
    eu_h: Optional[float] = None
    eu_d: Optional[float] = None
    eu_a: Optional[float] = None
    fid: Optional[str] = None  # 500.com per-match id (used by livescore scraper)

    @property
    def match_id(self) -> str:
        return f"{self.issue}_{self.match_idx:03d}"


@dataclass
class Settlement:
    match_id: str
    issue: str
    match_idx: int
    fthg: Optional[int] = None
    ftag: Optional[int] = None
    result_code: Optional[str] = None  # "3" / "1" / "0"
    winning_sp: Optional[float] = None
    avg_eu_h: Optional[float] = None
    avg_eu_d: Optional[float] = None
    avg_eu_a: Optional[float] = None


# ---------------------------------------------------------------------------
# Issue list (trade.500.com bjdc page)
# ---------------------------------------------------------------------------
_EXPECT_RE = re.compile(r'<option[^>]*value="(\d{5,6})"', re.I)


def parse_issue_list(html: str) -> List[str]:
    """Extract distinct issue codes from the bjdc / projectlist page.

    Uses regex on ``<option value="NNNNN">`` tags so we tolerate either the
    5-digit (post-2020) or 6-digit (pre-2020) issue formats.
    """
    seen = []
    out = []
    for m in _EXPECT_RE.finditer(html):
        v = m.group(1)
        if v not in seen:
            seen.append(v)
            out.append(v)
    return out


def find_current_issue(html: str) -> Optional[str]:
    """The *current* issue is in a hidden input on the bjdc page."""
    m = re.search(r'<input[^>]*name="expect"[^>]*value="(\d{5,6})"', html, re.I)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# 500.com bjdc bet page
# ---------------------------------------------------------------------------
_VS_LINE_RE = re.compile(
    r'<tr[^>]*class="vs_lines[^"]*"[^>]*value="(?P<meta>\{[^}]*\})"(?P<rest>[^>]*)>(?P<body>.*?)</tr>',
    re.S,
)
_FID_RE = re.compile(r'fid="(\d+)"')
# meta is single-quoted JS-object-literal-ish: index:'1',leagueName:'挪超',...
_META_KV_RE = re.compile(r"(\w+):\s*'([^']*)'")


def _parse_meta(meta: str) -> dict:
    return {k: v for k, v in _META_KV_RE.findall(meta)}


def _to_float(s: str) -> Optional[float]:
    s = s.strip()
    if not s or s in ("--", "-", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_handicap(s: str) -> Optional[float]:
    """e.g. '-2', '+1', '0' -> -2.0, 1.0, 0.0."""
    if s is None:
        return None
    s = s.strip().replace("＋", "+")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_bet_page_500(html: str, issue: Optional[str] = None) -> List[MatchSnapshot]:
    """Parse the trade.500.com bjdc page rows.

    The match data is split across:
      - ``<tr class="vs_lines" value="{...}" fid="...">`` — has meta
      - inside the row: spans ``.pjoz`` (3 avg-EU odds), ``.tzbl`` (3 vol
        %), ``.sp_value`` (3 SP values: W, D, L cells).
    """
    if issue is None:
        issue = find_current_issue(html) or ""

    rows: List[MatchSnapshot] = []
    for m in _VS_LINE_RE.finditer(html):
        try:
            meta = _parse_meta(m.group("meta"))
            body = m.group("body")
            idx = int(meta.get("index", "0") or "0")
            if not idx:
                continue

            snap = MatchSnapshot(issue=issue, match_idx=idx)
            fid_m = _FID_RE.search(m.group("rest") or "")
            snap.fid = fid_m.group(1) if fid_m else None
            snap.league = meta.get("leagueName") or None
            snap.home = meta.get("homeTeam") or None
            snap.away = meta.get("guestTeam") or None
            snap.handicap_line = _to_handicap(meta.get("rangqiuNum", ""))

            # kickoff: endTime is bet-cutoff. Look for "比赛时间：HH:MM" in title.
            kickoff = None
            t_title = re.search(r'title="比赛时间：(\d{2}:\d{2})"', body)
            sched_date = meta.get("scheduleDate")  # YYYY-MM-DD
            end_time = meta.get("endTime")  # YYYY-MM-DD HH:MM
            if t_title and sched_date:
                # match-time HH:MM may be on next day if late kickoff.
                hhmm = t_title.group(1)
                # guess: if kickoff hour < end hour, it's next day
                try:
                    base = datetime.strptime(sched_date, "%Y-%m-%d")
                    h, mi = map(int, hhmm.split(":"))
                    kickoff = base.replace(hour=h, minute=mi).isoformat()
                    if end_time:
                        et = datetime.strptime(end_time, "%Y-%m-%d %H:%M")
                        kt = datetime.fromisoformat(kickoff)
                        if kt < et:
                            kt = kt.replace(day=et.day, month=et.month, year=et.year)
                            kickoff = kt.isoformat()
                except Exception:
                    kickoff = None
            elif end_time:
                kickoff = end_time
            snap.kickoff_ts = kickoff

            # avg European odds
            pjoz = re.findall(r'class="[^"]*pjoz[^"]*"[^>]*>([^<]+)<', body)
            if len(pjoz) >= 3:
                snap.eu_h = _to_float(pjoz[0])
                snap.eu_d = _to_float(pjoz[1])
                snap.eu_a = _to_float(pjoz[2])

            # vol_pct (tzbl) — values are "--" post-settlement, "23%" pre.
            tzbl = re.findall(r'class="[^"]*tzbl[^"]*"[^>]*>([^<]+)<', body)
            if len(tzbl) >= 3:
                snap.vol_pct_3 = _pct(tzbl[0])
                snap.vol_pct_1 = _pct(tzbl[1])
                snap.vol_pct_0 = _pct(tzbl[2])

            # SP values: three .sp_value spans
            sps = re.findall(r'class="[^"]*sp_value[^"]*"[^>]*>([^<]+)<', body)
            if len(sps) >= 3:
                snap.sp_3 = _to_float(sps[0])
                snap.sp_1 = _to_float(sps[1])
                snap.sp_0 = _to_float(sps[2])
            elif len(sps) == 1:
                # only one SP span (the winning one) — happens post-settle.
                # Leave others as None; backfill via kaijiang/zgzcw merge.
                snap.sp_3 = _to_float(sps[0])

            rows.append(snap)
        except Exception as e:  # pragma: no cover - defensive
            log.warning("bet_500: failed to parse row: %s", e)
            continue
    return rows


_PCT_RE = re.compile(r"([\d.]+)\s*%")


def _pct(s: str) -> Optional[float]:
    s = (s or "").strip()
    if not s or s in ("--", "-", "—"):
        return None
    m = _PCT_RE.search(s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return _to_float(s)


# ---------------------------------------------------------------------------
# cp.zgzcw.com bet page (lottery=200)
# ---------------------------------------------------------------------------
_ZGZCW_TR_RE = re.compile(
    r'<tr[^>]*\bid="tr_(?P<idx>\d+)"[^>]*\brq="(?P<rq>[^"]*)"[^>]*\bt="(?P<t>[^"]*)"[^>]*>(?P<body>.*?)</tr>',
    re.S,
)
_ZGZCW_SPARR_RE = re.compile(r'class="spArr"\s+value="([^"]+)"')


def parse_bet_page_zgzcw(html: str, issue: Optional[str] = None) -> List[MatchSnapshot]:
    """Parse cp.zgzcw.com bdplayvsforJsp.action page.

    Rows look like::

        <tr id="tr_1" rq="-2" t="2026-05-01 00:55:00" m="挪超" ...>
          ...
          <td class="wh-4 t-r" tn="博德闪耀">...</td>
          <td class="wh-6 t-l" tn="斯达">...</td>
          <input class="spArr" value="W D L" />
          <input id="esp_1" value="EUh EUd EUa">
    """
    rows: List[MatchSnapshot] = []
    for m in _ZGZCW_TR_RE.finditer(html):
        try:
            idx = int(m.group("idx"))
            rq = m.group("rq")
            t = m.group("t")
            body = m.group("body")

            snap = MatchSnapshot(issue=(issue or ""), match_idx=idx)
            snap.handicap_line = _to_handicap(rq)
            try:
                # t looks like "2026-05-01 00:55:00" — bet cutoff
                snap.kickoff_ts = datetime.strptime(t, "%Y-%m-%d %H:%M:%S").isoformat()
            except Exception:
                snap.kickoff_ts = t or None

            league_m = re.search(r'class="g_[^"]*"[^>]*><s></s>([^<]+)<', body)
            if league_m:
                snap.league = league_m.group(1).strip()
            home_m = re.search(r'class="wh-4[^"]*"[^>]*\btn="([^"]+)"', body)
            away_m = re.search(r'class="wh-6[^"]*"[^>]*\btn="([^"]+)"', body)
            if home_m:
                snap.home = home_m.group(1)
            if away_m:
                snap.away = away_m.group(1)

            sparr = _ZGZCW_SPARR_RE.search(body)
            if sparr:
                # convention "W D L"; minus prefix marks the settled-paying side.
                parts = sparr.group(1).split()
                if len(parts) == 3:
                    snap.sp_3 = _abs_or_none(parts[0])
                    snap.sp_1 = _abs_or_none(parts[1])
                    snap.sp_0 = _abs_or_none(parts[2])

            esp = re.search(r'id="esp_\d+"[^>]*value="([^"]+)"', body)
            if esp:
                parts = esp.group(1).split()
                if len(parts) == 3:
                    snap.eu_h = _to_float(parts[0])
                    snap.eu_d = _to_float(parts[1])
                    snap.eu_a = _to_float(parts[2])

            rows.append(snap)
        except Exception as e:  # pragma: no cover
            log.warning("bet_zgzcw: failed to parse row: %s", e)
            continue
    return rows


def _abs_or_none(s: str) -> Optional[float]:
    f = _to_float(s)
    if f is None or f == 0:
        return None
    return abs(f)


# ---------------------------------------------------------------------------
# 500.com kaijiang (settlement) page
# ---------------------------------------------------------------------------
def parse_kaijiang(html: str, issue: str) -> List[Settlement]:
    """Parse the settlement page at zx.500.com/zqdc/kaijiang.php?playid=1."""
    out: List[Settlement] = []
    soup = BeautifulSoup(html, "lxml")
    # Each match row is a <tr> with the structure described in
    # docs/research/data-sources-beidan.md. We look for rows whose first
    # <td> is a small integer (the match_idx) AND that contain a
    # "<td class=eng red>SP" cell — that uniquely picks out match rows
    # rather than header/sub rows.
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 12:
            continue
        first = tds[0].get_text(strip=True)
        if not first.isdigit():
            continue
        try:
            idx = int(first)
        except ValueError:
            continue
        # skim cells
        try:
            league_a = tds[1].find("a", class_="league")
            if not league_a:
                continue
            score = tds[6].get_text(strip=True)
            result = tds[7].get_text(strip=True)
            sp_cell = tds[9].get_text(strip=True)
            eu_h = tds[11].get_text(strip=True) if len(tds) > 11 else ""
            eu_d = tds[12].get_text(strip=True) if len(tds) > 12 else ""
            eu_a = tds[13].get_text(strip=True) if len(tds) > 13 else ""

            fthg = ftag = None
            sm = re.match(r"\(?(\d+):(\d+)", score)
            if sm:
                fthg, ftag = int(sm.group(1)), int(sm.group(2))

            # normalise result code: 胜/平/负 -> 3/1/0
            rc_map = {"胜": "3", "平": "1", "负": "0", "3": "3", "1": "1", "0": "0"}
            rc = rc_map.get(result)

            s = Settlement(
                match_id=f"{issue}_{idx:03d}",
                issue=issue,
                match_idx=idx,
                fthg=fthg,
                ftag=ftag,
                result_code=rc,
                winning_sp=_to_float(sp_cell),
                avg_eu_h=_to_float(eu_h),
                avg_eu_d=_to_float(eu_d),
                avg_eu_a=_to_float(eu_a),
            )
            out.append(s)
        except Exception as e:  # pragma: no cover
            log.warning("kaijiang: failed to parse row idx=%s: %s", first, e)
            continue
    return out


# ---------------------------------------------------------------------------
# Per-match livescore: live.500.com/?gameid=<fid>
# ---------------------------------------------------------------------------
_LIVE500_ROW_RE = re.compile(
    r'<tr[^>]*\bid="a(?P<fid>\d+)"[^>]*>(?P<body>.*?)</tr>',
    re.S,
)
# Status cell uses <span class="red">完</span> for finished matches
_LIVE500_FINISHED_RE = re.compile(r'class="red"\s*>\s*完\s*<')
# Final score cell: <td align="center" class="red">2 - 0</td>
_LIVE500_SCORE_RE = re.compile(
    r'<td[^>]*class="red"[^>]*>\s*(\d+)\s*-\s*(\d+)\s*</td>'
)
# Handicap cell on this page: <span class="sp_rq">(-1)</span> — sign matches
# the home team. We use the parent matches table's handicap_line instead.


def parse_livescore_500_all(html: str) -> dict[str, tuple[int, int]]:
    """Return ``{fid: (home_goals, away_goals)}`` for every finished match
    on the page. Lets one HTTP fetch cover ~30 nearby matches.
    """
    out: dict[str, tuple[int, int]] = {}
    for m in _LIVE500_ROW_RE.finditer(html):
        body = m.group("body")
        if not _LIVE500_FINISHED_RE.search(body):
            continue
        sm = _LIVE500_SCORE_RE.search(body)
        if not sm:
            continue
        out[m.group("fid")] = (int(sm.group(1)), int(sm.group(2)))
    return out


def parse_livescore_500_for_fid(html: str, fid: str) -> Optional[tuple[int, int]]:
    """Return ``(home_goals, away_goals)`` if the row for ``fid`` is finished.
    Thin wrapper around ``parse_livescore_500_all`` for backward compat.
    """
    return parse_livescore_500_all(html).get(str(fid))


def compute_result_code(
    fthg: int, ftag: int, handicap_line: Optional[float]
) -> str:
    """Beijing Lot rule: result_code = '3' (主胜) / '1' (平) / '0' (客胜)
    after applying the handicap to the home team's goals.

    handicap_line follows 500.com convention: a value of ``-1`` means
    "home owes 1 goal" — subtract from home before comparing.
    """
    h = int(handicap_line) if handicap_line is not None else 0
    home_eff = fthg + h
    if home_eff > ftag:
        return "3"
    if home_eff < ftag:
        return "0"
    return "1"


# ---------------------------------------------------------------------------
# Removed 2026-05-05: dongqiudi fallback parser.
# Site migrated from Next.js (server-rendered __NEXT_DATA__) to Nuxt.js
# (IIFE shell + lazy fetch via token-protected APIs). No static-HTML scraping
# is feasible; would require Playwright or reverse-engineered mobile API.
# 500.com remains the sole settlement source.
# ---------------------------------------------------------------------------
# (parse_dongqiudi_day and is_dongqiudi_finished removed; see banner above.)


# ---------------------------------------------------------------------------
# 500.com zqdc.php fallback (per-fid scoreboard, faster than kaijiang)
# ---------------------------------------------------------------------------
# Kaijiang can lag hours on certain leagues. live.500.com/zqdc.php?id={fid}
# returns a scoreboard whose row for that fid has status="4" (finished)
# and inline home/away goal spans even when kaijiang still shows '-'.

_ZQDC_ROW_RE_TPL = (
    r'<tr id="a{fid}"[^>]*\bstatus="(?P<status>\d+)"[^>]*>'
    r'(?P<body>.*?)</tr>'
)

# Inside the row body: home team has yellowcard span BEFORE its team link,
# away team has yellowcard span AFTER its team link.
_ZQDC_HOME_GOALS_RE = re.compile(
    r'<span class="yellowcard">(\d+)</span>\s*<a[^>]*team/\d+/[^>]*>',
    re.S,
)
_ZQDC_AWAY_GOALS_RE = re.compile(
    r'<a[^>]*team/\d+/[^>]*>[^<]+</a>\s*<span class="yellowcard">(\d+)</span>',
    re.S,
)


# Issue id markers on zqdc.php pages. Multiple signals exist; we try them
# in order of reliability:
#   1. ``window.live_cur_expect = "26052";`` — JS var, single source of truth
#   2. ``<select id="sel_expect"><option value="26052">`` — visible UI dropdown
#   3. ``window.live_json_path = 'zqdc/26052';`` — last-resort path hint
_ZQDC_CUR_EXPECT_RE = re.compile(
    r'live_cur_expect\s*=\s*["\'](\d{5,6})["\']'
)
_ZQDC_SEL_EXPECT_RE = re.compile(
    r'id="sel_expect"[^>]*>\s*<option[^>]*value="(\d{5,6})"', re.S
)
_ZQDC_JSON_PATH_RE = re.compile(
    r"live_json_path\s*=\s*['\"]zqdc/(\d{5,6})['\"]"
)


def parse_500_zqdc_issue(html: str) -> Optional[str]:
    """Extract the current 北单 issue id from a live.500.com/zqdc.php page.

    Used as the fallback when ``trade.500.com`` issue discovery is down.
    Returns None if no issue marker is found.
    """
    if not html:
        return None
    for rx in (_ZQDC_CUR_EXPECT_RE, _ZQDC_SEL_EXPECT_RE, _ZQDC_JSON_PATH_RE):
        m = rx.search(html)
        if m:
            return m.group(1)
    return None


def parse_500_zqdc_score(html: str, fid: str
                         ) -> Optional[Tuple[int, int, str]]:
    """Locate the row for the given ``fid`` in a zqdc.php response and
    return ``(home_goals, away_goals, status)``. Returns None if the row
    isn't found or scores can't be extracted. Caller should treat status
    == "4" as finished.
    """
    row_re = re.compile(_ZQDC_ROW_RE_TPL.format(fid=re.escape(str(fid))), re.S)
    m = row_re.search(html)
    if not m:
        return None
    status = m.group("status")
    body = m.group("body")
    mh = _ZQDC_HOME_GOALS_RE.search(body)
    ma = _ZQDC_AWAY_GOALS_RE.search(body)
    if not mh or not ma:
        return None
    try:
        return int(mh.group(1)), int(ma.group(1)), status
    except ValueError:
        return None
