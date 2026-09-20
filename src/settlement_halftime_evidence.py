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


def _okooo_soup(payload: bytes) -> BeautifulSoup:
    """okooo serves GB2312 pages; decoding as UTF-8 would silently mangle team names."""
    for encoding in ("gbk", "gb18030"):
        try:
            return BeautifulSoup(payload.decode(encoding), "html.parser")
        except UnicodeDecodeError:
            continue
    raise ValueError("okooo: page is not decodable as GB2312")


def _okooo_row(soup: BeautifulSoup, slot: int, minimum_cells: int, source: str) -> list:
    """Return the single row for ``slot``; its slot cell is the first cell."""
    rows = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td", recursive=False)
        if len(tds) < minimum_cells:
            continue
        text = tds[0].get_text(" ", strip=True)
        ident = re.match(r"^(\d+)(?:\s|$)", text)
        if ident and int(ident.group(1)) == slot:
            rows.append(tds)
    if len(rows) != 1:
        raise ValueError(f"{source}: expected exactly one row for slot {slot}, found {len(rows)}")
    return rows[0]


def extract_okooo_livecenter(payload: bytes, fixture: dict) -> dict:
    """okooo's live centre prints the half time in a red cell inside the away-team cell."""
    soup = _okooo_soup(payload)
    tds = _okooo_row(soup, fixture["slot"], 7, "okooo")
    ft = re.fullmatch(r"(\d+)\s*-\s*(\d+)", tds[5].get_text(" ", strip=True))
    if ft is None:
        raise ValueError("okooo: unreadable full time score")
    halves = set()
    for nested in tds[6].find_all("td"):
        children = nested.find_all(recursive=False)
        if len(children) != 1 or children[0].name != "span":
            continue
        if "font_red" not in (children[0].get("class") or []):
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", children[0].get_text(" ", strip=True))
        if m:
            halves.add((int(m.group(1)), int(m.group(2))))
    home, away = _unique(halves, "okooo", "half time")
    return _gate("okooo", {"home": home, "away": away,
                           "ft_home": int(ft.group(1)), "ft_away": int(ft.group(2))}, fixture)


# okooo's half/full page encodes the settlement as "<half>-<full>" in the 3/1/0 domain,
# with 3 = home win, 1 = draw, 0 = away win; this project spells them 胜/平/负.
_RESULT_CODES = {"3": "胜", "1": "平", "0": "负"}


def outcome(home: int, away: int) -> str:
    return "胜" if home > away else "负" if home < away else "平"


def half_full_option(half_time: tuple[int, int], full_time: tuple[int, int]) -> str:
    """The half/full winning option, matching the build's own derivation exactly."""
    return outcome(*half_time) + "-" + outcome(*full_time)


def extract_okooo_half_full(payload: bytes, fixture: dict) -> dict:
    """okooo's half/full page prints the settlement code and its settlement SP.

    Columns: slot+league, kickoff, teams, settlement SP, betting area, quick pick, all,
    pick, full-time score, settlement code, analysis.
    """
    soup = _okooo_soup(payload)
    tds = _okooo_row(soup, fixture["slot"], 9, "okooo_half_full")
    ft = re.fullmatch(r"(\d+)\s*-\s*(\d+)", tds[7].get_text(" ", strip=True))
    if ft is None:
        raise ValueError("okooo_half_full: unreadable full time score")
    code = re.fullmatch(r"([0-3])\s*-\s*([0-3])", tds[8].get_text(" ", strip=True))
    if code is None:
        raise ValueError("okooo_half_full: unreadable settlement code")
    sp_text = tds[3].get_text(" ", strip=True)
    sp = None
    if sp_text:
        try:
            sp = float(sp_text)
        except ValueError as exc:
            raise ValueError(f"okooo_half_full: unreadable settlement SP {sp_text!r}") from exc
    claim = {"option": _RESULT_CODES[code.group(1)] + "-" + _RESULT_CODES[code.group(2)],
             "sp": sp, "ft_home": int(ft.group(1)), "ft_away": int(ft.group(2))}
    if (claim["ft_home"], claim["ft_away"]) != (fixture["ft_home"], fixture["ft_away"]):
        raise ValueError(
            f"okooo_half_full: full time {(claim['ft_home'], claim['ft_away'])} "
            f"is not the expected fixture {(fixture['ft_home'], fixture['ft_away'])}")
    return claim


HALF_FULL_EXTRACTORS: dict[str, Callable[[bytes, dict], dict]] = {
    "okooo_half_full": extract_okooo_half_full,
}


EXTRACTORS: dict[str, Callable[[bytes, dict], dict]] = {
    "globalsportsarchive": extract_globalsportsarchive,
    "24score": extract_24score,
    "sportsmole": extract_sportsmole,
    "footballcritic": extract_footballcritic,
    "transfermarkt": extract_transfermarkt,
    "okooo": extract_okooo_livecenter,
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


def corroborate_half_full(half_time: tuple[int, int], full_time: tuple[int, int],
                          claims: dict[str, dict]) -> dict:
    """Return the corroborated half/full settlement option and its settlement SP.

    The option is not taken on trust: it must equal the one derived from the
    *corrected* half time and the full time, so a source that inherited the
    half-time error cannot re-assert itself here. Every source that publishes an SP
    must publish the same value; a missing SP is refused rather than guessed.
    """
    if not claims:
        raise ValueError("need at least one half/full settlement source")
    expected = half_full_option(half_time, full_time)
    options = {c["option"] for c in claims.values()}
    if options != {expected}:
        raise ValueError(
            f"half/full settlement {sorted(options)} disagrees with the corrected half time "
            f"{expected}")
    sps = {c["sp"] for c in claims.values()}
    if len(sps) != 1 or None in sps:
        raise ValueError(f"sources disagree on the half/full settlement SP: {sorted(sps, key=str)}")
    sp = sps.pop()
    if sp < 1:
        raise ValueError(f"half/full settlement SP {sp} is below 1")
    return {"option": expected, "sp": sp}
