"""Independent extraction and corroboration of externally verified half-time scores.

Issue #479 deliverable. The sealed Nowscore settlement build records the half-time
score exactly as the source served it, and its own audit correctly flags the rows
where that source value contradicts the full-time score. Correcting those rows is
therefore an *external* correction: the 500 and Nowscore sources carry the same wrong
value, so neither can corroborate the replacement. Evidence comes from independent
football result archives instead.

This module holds the only authoritative implementation of that extraction. Every
extractor is deterministic, offline and fail-closed: it either returns the scores it
can prove from the preserved bytes, or raises. Nothing is inferred from the
full-time score, no source is trusted to vouch for itself, and a page that cannot be
shown to be the right fixture is rejected.

Contract per extractor:

* ``payload`` -- the preserved evidence bytes (raw HTML)
* ``fixture`` -- ``{"home": str, "away": str, "date": "YYYY-MM-DD", "ft_home": int,
  "ft_away": int}``; the date is reformatted per source, and the full-time pair is
  used as a fixture identity gate
* returns -- ``{"home": int, "away": int, "ft_home": int, "ft_away": int}`` where the
  ``home``/``away`` pair is the half-time score
* raises ``ValueError`` when the claim is absent, ambiguous, conflicting, or when the
  page's full-time score disagrees with the expected fixture

Corroboration requires at least ``MIN_INDEPENDENT_SOURCES`` distinct sources that
agree on the half-time pair; disagreement is fatal rather than resolved by vote.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable

from bs4 import BeautifulSoup

MIN_INDEPENDENT_SOURCES = 2
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _text(payload: bytes) -> str:
    return BeautifulSoup(payload.decode("utf-8", errors="replace"), "html.parser").get_text(" ", strip=True)


def _fixture_date(fixture: dict) -> date:
    return date.fromisoformat(fixture["date"])


def _unique(pairs: set[tuple[int, int]], source: str, label: str) -> tuple[int, int]:
    if len(pairs) != 1:
        raise ValueError(f"{source}: expected exactly one {label} claim, found {sorted(pairs)}")
    return pairs.pop()


def _gate(source: str, claim: dict, fixture: dict) -> dict:
    """Reject a page whose full-time score is not the expected fixture's."""
    if (claim["ft_home"], claim["ft_away"]) != (fixture["ft_home"], fixture["ft_away"]):
        raise ValueError(
            f"{source}: full time {(claim['ft_home'], claim['ft_away'])} "
            f"is not the expected fixture {(fixture['ft_home'], fixture['ft_away'])}")
    if claim["home"] > claim["ft_home"] or claim["away"] > claim["ft_away"]:
        raise ValueError(f"{source}: half time exceeds the full time score")
    return claim


def extract_globalsportsarchive(payload: bytes, fixture: dict) -> dict:
    """Global Sports Archive prints the running score under a `1st Half h - a` heading."""
    text = _text(payload)
    home, away = _unique({(int(m.group(1)), int(m.group(2)))
                          for m in re.finditer(r"1st Half\s+(\d+)\s*-\s*(\d+)", text)},
                         "globalsportsarchive", "half time")
    ft_home, ft_away = _unique({(int(m.group(1)), int(m.group(2)))
                                for m in re.finditer(r"Full Time\s+(\d+)\s*-\s*(\d+)", text)},
                               "globalsportsarchive", "full time")
    return _gate("globalsportsarchive",
                 {"home": home, "away": away, "ft_home": ft_home, "ft_away": ft_away}, fixture)


def extract_24score(payload: bytes, fixture: dict) -> dict:
    """24score prints `FT:FT (HT:HT)` in the head-to-head score cell of the match row."""
    d = _fixture_date(fixture)
    anchor = f"{d.day:02d}.{d.month:02d}.{d.year % 100:02d}"
    soup = BeautifulSoup(payload.decode("utf-8", errors="replace"), "html.parser")
    cells = []
    for tr in soup.find_all("tr"):
        if anchor not in tr.get_text(" ", strip=True):
            continue
        cell = tr.select_one("td.score")
        if cell is not None:
            cells.append(cell.get_text(" ", strip=True))
    claims = set()
    for cell in cells:
        m = re.fullmatch(r"[WDL]\s*(\d+):(\d+)\s*\((\d+):(\d+)\)", cell)
        if m:
            claims.add((int(m.group(3)), int(m.group(4)), int(m.group(1)), int(m.group(2))))
    if len(claims) != 1:
        raise ValueError(f"24score: expected exactly one claim on {anchor}, found {sorted(claims)}")
    home, away, ft_home, ft_away = claims.pop()
    return _gate("24score",
                 {"home": home, "away": away, "ft_home": ft_home, "ft_away": ft_away}, fixture)


def extract_sportsmole(payload: bytes, fixture: dict) -> dict:
    """Sports Mole prints `h a HT : h a FT` beside the scoreline, or `FT (HT: h-a)`.

    Its pages also list historical head-to-head rows in the same format, so the
    inline form is read from a window after the fixture's own kickoff date rather
    than from the page at large.
    """
    text = _text(payload)
    d = _fixture_date(fixture)
    stamp = f"{_MONTHS[d.month - 1]} {d.day}, {d.year}"
    windowed = set()
    if text.count(stamp) == 1:
        i = text.index(stamp)
        rest = text[i + len(stamp):]
        nxt = re.search(r"\b(?:" + "|".join(_MONTHS) + r")\s+\d{1,2}, \d{4}\b", rest)
        segment = text[i:i + len(stamp) + (nxt.start() if nxt else 160)]
        windowed = {(int(m.group(3)), int(m.group(4)), int(m.group(1)), int(m.group(2)))
                    for m in re.finditer(r"(\d+)\s+(\d+)\s+HT\s*:\s*(\d+)\s+(\d+)\s+FT", segment)}
    bracketed = set()
    for m in re.finditer(r"FT\s*\(HT:\s*(\d+)-(\d+)\)", text):
        before = text[:m.start()]
        ft = [(int(x.group(1)), int(x.group(2)))
              for x in re.finditer(r"(\d+)\s*-\s*(\d+)\s*" + re.escape(fixture["away_en"]), before)]
        if ft:
            bracketed.add((int(m.group(1)), int(m.group(2)), *ft[-1]))
    claims = windowed | bracketed
    if len(claims) != 1:
        raise ValueError(f"sportsmole: expected exactly one claim for {stamp}, found {sorted(claims)}")
    home, away, ft_home, ft_away = claims.pop()
    return _gate("sportsmole",
                 {"home": home, "away": away, "ft_home": ft_home, "ft_away": ft_away}, fixture)


def extract_footballcritic(payload: bytes, fixture: dict) -> dict:
    """FootballCritic labels both scores explicitly in its match information block."""
    text = _text(payload)
    home, away = _unique({(int(m.group(1)), int(m.group(2)))
                          for m in re.finditer(r"Half Time Score:\s*(\d+)\s*-\s*(\d+)", text)},
                         "footballcritic", "half time")
    ft_home, ft_away = _unique({(int(m.group(1)), int(m.group(2)))
                                for m in re.finditer(r"Full Time Score:\s*(\d+)\s*-\s*(\d+)", text)},
                               "footballcritic", "full time")
    return _gate("footballcritic",
                 {"home": home, "away": away, "ft_home": ft_home, "ft_away": ft_away}, fixture)


def extract_transfermarkt(payload: bytes, fixture: dict) -> dict:
    """Transfermarkt renders the scoreline as `FT:FT (HT:HT)` in its match header."""
    text = _text(payload)
    claims = {(int(m.group(3)), int(m.group(4)), int(m.group(1)), int(m.group(2)))
              for m in re.finditer(r"(\d+):(\d+)\s*\(\s*(\d+):\s*(\d+)\s*\)", text)}
    if len(claims) != 1:
        raise ValueError(f"transfermarkt: expected exactly one claim, found {sorted(claims)}")
    home, away, ft_home, ft_away = claims.pop()
    return _gate("transfermarkt",
                 {"home": home, "away": away, "ft_home": ft_home, "ft_away": ft_away}, fixture)


EXTRACTORS: dict[str, Callable[[bytes, dict], dict]] = {
    "globalsportsarchive": extract_globalsportsarchive,
    "24score": extract_24score,
    "sportsmole": extract_sportsmole,
    "footballcritic": extract_footballcritic,
    "transfermarkt": extract_transfermarkt,
}


def corroborate(claims: dict[str, dict]) -> tuple[int, int]:
    """Return the half-time pair that >= MIN_INDEPENDENT_SOURCES distinct sources agree on.

    ``claims`` maps source_id to the dict returned by its extractor. Fewer than
    MIN_INDEPENDENT_SOURCES sources, or any disagreement on the half-time pair, is
    fatal: the correction is refused rather than resolved by majority.
    """
    if len(claims) < MIN_INDEPENDENT_SOURCES:
        raise ValueError(
            f"need >= {MIN_INDEPENDENT_SOURCES} independent sources, got {len(claims)}")
    pairs = {(c["home"], c["away"]) for c in claims.values()}
    if len(pairs) != 1:
        raise ValueError(f"independent sources disagree on half time: {sorted(pairs)}")
    return pairs.pop()
