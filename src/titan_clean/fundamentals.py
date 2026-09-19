"""Parse Titan analysis-page fundamentals (pre-match snapshot).

Extracts venue/weather/temperature, both teams' recent form, head-to-head,
season stat tables and the standings link. All values are source-state raw
text/JSON; availability is the analysis page's own pre-match snapshot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class TitanFundamentalError(ValueError):
    """Raised when the analysis page cannot be parsed safely."""


@dataclass(frozen=True)
class AnalysisFundamentals:
    venue: str | None = None
    weather: str | None = None
    temperature: str | None = None
    home_form: str | None = None
    away_form: str | None = None
    h2h: str | None = None
    home_season_stats: str | None = None
    away_season_stats: str | None = None
    standings_link: str | None = None
    raw_blocks: dict[str, str] = field(default_factory=dict)


_WEATHER_RE = re.compile(
    r'class=["\']place["\'][^>]*>(?:<[^>]+>)*场地[:：]\s*([^<]+)</a>\s*天气[:：]\s*([^<\s&]+)[^<]*温度[:：]\s*([^<]+)',
    re.S,
)
_STANDINGS_RE = re.compile(
    r"info\.titan007\.com/score/(?P<season>[0-9]{4}-[0-9]{4})/(?P<league>\d+)\.htm",
)
_JS_ARRAY_RE = re.compile(r"var\s+(?P<name>h_data|a_data|v_data|h2_data|a2_data)\s*=\s*(?P<body>\[.*?\])\s*;", re.S)
_TEAM_TABLE_RE = re.compile(
    r"\[(?P<league>[^\]]+?)-(?P<rank>\d+)\](?P<team>[^<]+?)\s+(?P<body>.*?)(?=</table|$)",
    re.S,
)


def _js_array_text(text: str, name: str) -> str | None:
    for match in _JS_ARRAY_RE.finditer(text):
        if match.group("name") == name:
            return match.group("body")
    return None


def _season_table(text: str, ordinal: int) -> str | None:
    matches: list[str] = []
    for match in re.finditer(r"\[[^\]]+?-\d+\]", text):
        block = text[match.start():match.start() + 700]
        if "全场" in block and "胜" in block:
            matches.append(block)
    return matches[ordinal] if ordinal < len(matches) else None


def parse_analysis_fundamentals(payload: bytes) -> AnalysisFundamentals:
    """Extract pre-match fundamentals from a Titan analysis page."""
    text = payload.decode("utf-8", errors="replace")
    weather_match = _WEATHER_RE.search(text)
    venue = weather_match.group(1).strip() if weather_match else None
    weather = weather_match.group(2).strip() if weather_match else None
    temperature = weather_match.group(3).strip() if weather_match else None
    standings = _STANDINGS_RE.search(text)
    standings_link = f"info.titan007.com/score/{standings.group('season')}/{standings.group('league')}.htm" if standings else None
    raw_blocks = {name: _js_array_text(text, name) for name in ("h_data", "a_data", "v_data") if _js_array_text(text, name)}
    return AnalysisFundamentals(
        venue=venue,
        weather=weather,
        temperature=temperature,
        home_form=raw_blocks.get("h_data"),
        away_form=raw_blocks.get("a_data"),
        h2h=raw_blocks.get("v_data"),
        home_season_stats=_season_table(text, 0),
        away_season_stats=_season_table(text, 1),
        standings_link=standings_link,
        raw_blocks=raw_blocks,
    )
