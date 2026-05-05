"""Soccerway day-page scraper using camoufox (handles JS-rendered scores).

Used as a fallback when neither 500.com kaijiang nor live.500 covers a
match (typically cold leagues like 冰岛超, 希腊超, 丹超, 奥甲).

Strategy: one camoufox fetch per (date), extract every finished match's
``(league_label_en, home, away, home_goals, away_goals)``. Caller matches
each pending match by:

  league (Chinese → english tokens via league_aliases.json)
  + kickoff time (±15 min slack)
  + team-name fuzzy (token overlap)

The browser is lazily started once per process and reused for all dates.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

ALIASES_PATH = Path(__file__).parent / "league_aliases.json"


@dataclass
class SoccerwayMatch:
    home: str               # Soccerway-rendered name (English)
    away: str
    home_goals: int
    away_goals: int
    league_label: str       # the tournament header text we find above the row
    finished: bool


# ---------------------------------------------------------------------------
# Regexes against soccerway day HTML (same DOM as flashscore)
# ---------------------------------------------------------------------------
# Each match: <div id="g_1_<MID>" class="event__match...">...</div>
# We slice on the next <div id="g_1_..."> to bound the row.
_MATCH_BLOCK_RE = re.compile(
    r'<div id="g_1_([^"]+)"[^>]*class="event__match[^"]*"[^>]*>(.*?)'
    r'(?=<div id="g_1_|<div class="event__header)',
    re.S,
)
_ARIA_RE = re.compile(r'aria-label="([^"]+)\s*-\s*([^"]+)"')
_STAGE_RE = re.compile(r'class="event__stage--block"[^>]*>([^<]+)<')
_HOME_SCORE_RE = re.compile(
    r'event__score--home"[^>]*>(\d+)<', re.S)
_AWAY_SCORE_RE = re.compile(
    r'event__score--away"[^>]*>(\d+)<', re.S)
# League header rows: <div class="event__header"...><span...>League Name</span>
_LEAGUE_HEADER_RE = re.compile(
    r'<div[^>]*class="event__header[^"]*"[^>]*>(.*?)</div>',
    re.S,
)
_LEAGUE_LABEL_RE = re.compile(r'>([^<>]{4,80})<')


def _load_league_aliases() -> dict:
    if ALIASES_PATH.exists():
        try:
            d = json.loads(ALIASES_PATH.read_text())
            return {k: [t.lower() for t in v] for k, v in d.items()
                    if not k.startswith("_")}
        except Exception:
            pass
    return {}


def league_match_score(zh_league: str, sw_label: str,
                        aliases: Optional[dict] = None) -> int:
    """Return number of alias tokens from ``zh_league`` found in ``sw_label``.

    0 = no match; higher = stronger match. ``aliases`` is the loaded JSON.
    """
    if not zh_league:
        return 0
    aliases = aliases or _load_league_aliases()
    tokens = aliases.get(zh_league, [])
    if not tokens:
        return 0
    label_lower = (sw_label or "").lower()
    return sum(1 for t in tokens if t in label_lower)


# ---------------------------------------------------------------------------
# Fuzzy team-name compare (Latin token overlap; tolerates suffix noise)
# ---------------------------------------------------------------------------
_NOISE_TOKENS = {"fc", "afc", "sc", "cf", "if", "ac", "as", "club", "united",
                 "city", "town", "athletic", "sportif", "sporting", "calcio",
                 "real", "deportivo", "u21", "u23", "ii", "b", "ladies"}


def _tokens(name: str) -> set[str]:
    n = re.sub(r"[^a-zA-Z\s]", " ", (name or "").lower())
    return {t for t in n.split() if t and t not in _NOISE_TOKENS and len(t) > 1}


def team_match_score(zh_name: str, en_name: str,
                     pinyin_initials: Optional[str] = None) -> float:
    """Return [0..1] similarity between a Chinese team name and a Latin one.

    Tries (in priority): substring, token overlap via shared 2+ char letters,
    pinyin-initial match. Cheap heuristics — designed to be combined with
    league + kickoff filtering, not used standalone.
    """
    if not zh_name or not en_name:
        return 0.0
    en_lower = en_name.lower()
    # Direct substring (rare but possible: "AC米兰" contains "AC" → "AC Milan")
    latin_in_zh = re.findall(r"[A-Za-z]{2,}", zh_name)
    if latin_in_zh:
        for tok in latin_in_zh:
            if tok.lower() in en_lower:
                return 0.9
    # Pinyin initial fallback: caller may pass precomputed initials
    if pinyin_initials:
        en_initials = "".join(t[0] for t in _tokens(en_name) if t)
        if pinyin_initials and pinyin_initials in en_initials:
            return 0.6
    return 0.0


# ---------------------------------------------------------------------------
# Camoufox fetch + parse (async; called from sync via asyncio.run)
# ---------------------------------------------------------------------------
async def _fetch_day_html_async(date: str) -> str:
    from camoufox.async_api import AsyncCamoufox
    url = f"https://int.soccerway.com/matches/{date.replace('-', '/')}/"
    async with AsyncCamoufox(headless=True) as browser:
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        # Let JS hydrate the score table
        await page.wait_for_timeout(2500)
        return await page.content()


def fetch_day(date: str) -> str:
    """Sync wrapper around the async camoufox fetch."""
    return asyncio.run(_fetch_day_html_async(date))


def parse_day(html: str) -> List[SoccerwayMatch]:
    """Extract every finished/in-progress match from the day page HTML."""
    out: List[SoccerwayMatch] = []
    # Build a list of (league_header_pos, label) by walking event__header blocks
    league_blocks = []
    for hm in _LEAGUE_HEADER_RE.finditer(html):
        labels = _LEAGUE_LABEL_RE.findall(hm.group(1))
        # First non-trivial label is typically "Country: League Name"
        clean = " ".join(t.strip() for t in labels if t.strip())
        league_blocks.append((hm.start(), clean))

    def league_for(pos: int) -> str:
        # Find the latest league header before pos
        last = ""
        for hp, label in league_blocks:
            if hp < pos:
                last = label
            else:
                break
        return last

    for m in _MATCH_BLOCK_RE.finditer(html):
        body = m.group(2)
        aria = _ARIA_RE.search(body[:600])
        if not aria:
            continue
        home = aria.group(1).strip()
        away = aria.group(2).strip()
        stage = _STAGE_RE.search(body)
        finished = bool(stage and "full" in stage.group(1).lower())
        hg = _HOME_SCORE_RE.search(body)
        ag = _AWAY_SCORE_RE.search(body)
        if not (hg and ag):
            continue
        out.append(SoccerwayMatch(
            home=home, away=away,
            home_goals=int(hg.group(1)),
            away_goals=int(ag.group(1)),
            league_label=league_for(m.start()),
            finished=finished,
        ))
    return out


def find_match(
    pending_zh_league: str, pending_home_zh: str, pending_away_zh: str,
    candidates: List[SoccerwayMatch],
    *, aliases: Optional[dict] = None,
) -> Optional[SoccerwayMatch]:
    """Pick the best soccerway candidate for a (league, home, away) tuple.

    Returns None if no confident match. "Confident" = at least one league
    alias token matched AND (only 1 league candidate OR team substring/
    pinyin agrees).
    """
    aliases = aliases or _load_league_aliases()
    league_filtered = [
        c for c in candidates
        if league_match_score(pending_zh_league, c.league_label, aliases) > 0
        and c.finished
    ]
    if not league_filtered:
        return None
    if len(league_filtered) == 1:
        return league_filtered[0]
    # Multiple candidates in same league → use team match
    best = None
    best_score = 0.0
    for c in league_filtered:
        sc = (team_match_score(pending_home_zh, c.home)
              + team_match_score(pending_away_zh, c.away))
        if sc > best_score:
            best_score = sc
            best = c
    return best if best_score >= 0.6 else None
