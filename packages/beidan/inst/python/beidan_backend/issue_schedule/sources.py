"""One provider parser per source, returning raw-faithful provider rows.

Both parsers are pure: text in, list of dicts out. They keep the provider's own
name spelling, its own IDs, its own time strings and the raw row bytes so that
nothing downstream has to re-open the HTML and nothing is silently normalized
away.

Evidence rules learned from the frozen 26098 snapshot (146 matches each side):

* Nowscore cell 2 is the kickoff, always ``HH:mm`` with no date. Cell 3 is the
  *sale* column: its ``title`` attribute carries the full closing date
  (``截止时间：2026-09-25 12:55``), while its visible text is either ``完场`` (the
  five finished matches), ``截止`` (closed, kickoff passed) or a bare ``HH:mm``
  (still on sale). A bare ``HH:mm`` therefore says **nothing** about match
  status and is not a kickoff either.
* Nowscore cell 6 sometimes holds UI text such as ``析 亚 欧`` (an analysis
  link) rather than a result. That text is not a score and is reported as
  ``None``; no placeholder score is ever substituted for it.
* The row's ``name`` attribute is the *sales-grouping* date, not the kickoff
  calendar date: slot 146 of 26098 is grouped on 2026-09-28 but kicks off on
  2026-09-29. The page's script block carries the real calendar date in
  ``M[<slot>][2] = new Date(year, zero_based_month, day, h, m, s)``; that clock
  part is rewritten live while a match runs, so only its date is kickoff
  evidence.
* 500 has no match-status column at all; its ``endTime`` is the *sale* end, not
  the kickoff. The kickoff is the ``title="比赛时间：HH:MM"`` attribute.
"""

from __future__ import annotations

import re
import math
import warnings
from html import unescape as html_unescape
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, parse_qs

from bs4 import BeautifulSoup

#: Provider-visible status tokens are mapped to the canonical vocabulary in
#: ``contract``; these are the raw tokens this module recognises.
NOWSCORE_STATUS_FINISHED = "完场"
NOWSCORE_STATUS_CLOSED = "截止"

_ROW_ID_RE = re.compile(r"^row_(\d+)$")
_KICKOFF_TITLE_RE = re.compile(r"比赛时间\s*[：:]\s*(\d{1,2}:\d{2})")
_CLOSING_TITLE_RE = re.compile(r"截止时间\s*[：:]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
_CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_SCORE_RE = re.compile(r"^\d{1,3}-\d{1,3}$")


class SourceParseError(ValueError):
    """A page did not contain the structure this parser is contracted to read."""


@dataclass
class ProviderRow:
    """One raw provider row, before any cross-source reconciliation.

    ``raw_display_*`` fields exist because the *displayed* text and the
    *attribute* text are different evidence: a bare ``23:25`` in the sale cell
    is a display string, while ``截止时间：2026-09-25 23:25`` in its ``title`` is
    a dated instant. Keeping both stops a later reader from treating the display
    string as if it had ever carried a date.
    """

    provider: str
    provider_match_id: str
    slot: int
    league: str
    home_name: str
    away_name: str
    handicap_raw: str
    handicap: float | None
    kickoff_hhmm: str | None
    schedule_date: str | None
    kickoff_js_date: str | None
    status_token: str
    can_sale: bool | None
    sale_end_raw: str | None
    sale_end_at: datetime | None
    score: str | None
    raw_row: str
    observed_at: str
    source_url: str
    kelly_url: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def parse_nowscore_rows(
    text: str, *, issue_id: str, observed_at: str, source_url: str
) -> list[ProviderRow]:
    """Parse a ``DanChang.aspx?all=1`` page into provider rows.

    @param text Decoded page text (see ``decode.decode_response``).
    @param issue_id Issue requested; the page's own issue selector must agree.
    @param observed_at ISO-8601 observation instant, stamped onto every row.
    @param source_url Exact URL the bytes came from.
    @return One ``ProviderRow`` per match, ordered by slot.
    @raises SourceParseError when the page is not a nowscore schedule page or
        the page-selected issue disagrees with ``issue_id``.
    """
    soup = BeautifulSoup(text, "html.parser")
    _assert_nowscore_issue(soup, issue_id)
    kickoff_dates, date_problems = parse_nowscore_kickoff_dates(text)
    rows: list[ProviderRow] = []
    for tr in soup.select("tr[id^=row_]"):
        match = _ROW_ID_RE.match(tr.get("id") or "")
        if match is None:
            raise SourceParseError("nowscore match row has invalid slot")
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 9:
            raise SourceParseError("truncated nowscore schedule row")
        slot = int(match.group(1))
        if slot <= 0:
            raise SourceParseError("nowscore match row has invalid slot")
        provider_match_id = _nowscore_provider_id(tr)
        status_cell = cells[3]
        display = _text(status_cell)
        sale_end_raw = _attr_title(status_cell.get("title"))
        sale_end_at = _parse_sale_end(sale_end_raw)
        kickoff = _text(cells[2]) or None
        if kickoff and not _is_clock(kickoff):
            raise SourceParseError(f"invalid kickoff clock: {kickoff}")
        home = _text(cells[4])
        away = _text(cells[7])
        handicap_text = _text(cells[5])
        score = _text(cells[6])
        can_sale = tr.get("cansale")
        extras = {
            "polygoal": tr.get("polygoal"),
            "matchid": tr.get("matchid"),
            "halftime_score": _text(cells[8]) or None,
            "kickoff_display": kickoff,
            "sale_display": display,
            "kickoff_js_problem": date_problems.get(slot),
        }
        rows.append(
            ProviderRow(
                provider="nowscore",
                provider_match_id=provider_match_id,
                slot=slot,
                league=_text(cells[1]),
                home_name=home,
                away_name=away,
                handicap_raw=handicap_text,
                handicap=_to_float(tr.get("polygoal"))
                if tr.get("polygoal") not in (None, "")
                else _to_float(handicap_text),
                kickoff_hhmm=kickoff if _is_clock(kickoff) else None,
                schedule_date=tr.get("name") or None,
                kickoff_js_date=kickoff_dates.get(slot),
                status_token=display,
                can_sale=_to_bool(can_sale),
                sale_end_raw=sale_end_raw,
                sale_end_at=sale_end_at,
                score=_score_or_none(score),
                raw_row=tr.decode(),
                observed_at=observed_at,
                source_url=source_url,
                kelly_url=_provider_url(provider_match_id) if provider_match_id else None,
                extras=extras,
            )
        )
    if not rows and not re.search(r"暂无(?:比赛|赛事)|没有比赛", soup.get_text()):
        raise SourceParseError("no schedule rows and no explicit empty-issue marker")
    rows.sort(key=lambda row: row.slot)
    return rows


def parse_500_rows(
    text: str, *, issue_id: str, observed_at: str, source_url: str
) -> list[ProviderRow]:
    """Parse a ``trade.500.com/bjdc/?expect=...`` page into provider rows.

    @param text Decoded page text.
    @param issue_id Issue requested; the page's own ``expect_select`` must agree.
    @param observed_at ISO-8601 observation instant, stamped onto every row.
    @param source_url Exact URL the bytes came from.
    @return One ``ProviderRow`` per match, ordered by slot. 500 exposes no match
        status at all, so ``status_token`` is always empty and ``can_sale`` is
        derived from its ``disabled`` hint only.
    @raises SourceParseError when the page is not a 500 schedule page or the
        page-selected issue disagrees with ``issue_id``.
    """
    soup = BeautifulSoup(text, "html.parser")
    _assert_500_issue(soup, issue_id)
    rows: list[ProviderRow] = []
    for tr in soup.select("tr.vs_lines"):
        info = _parse_500_value(tr.get("value") or "")
        if not info:
            raise SourceParseError("500 match row has no value fields")
        fid = tr.get("fid")
        if fid == "-1":
            warnings.warn("500 excluded one fid=-1 placeholder row", UserWarning)
            continue
        if fid is None or not fid.isdigit() or int(fid) <= 0:
            raise SourceParseError("500 match row has invalid fid")
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 9:
            raise SourceParseError("truncated nowscore schedule row")
        slot_raw = info.get("index")
        if not slot_raw or not str(slot_raw).isdigit() or int(slot_raw) <= 0:
            raise SourceParseError("500 match row has invalid index")
        kickoff = _kickoff_title(cells[2].get("title"))
        rows.append(
            ProviderRow(
                provider="500",
                provider_match_id=fid,
                slot=int(slot_raw),
                league=info.get("leagueName", ""),
                home_name=info.get("homeTeam", ""),
                away_name=info.get("guestTeam", ""),
                handicap_raw=info.get("rangqiuNum", ""),
                handicap=_to_float(info.get("rangqiuNum")),
                # 500's kickoff is only ever HH:mm; its endTime is the sale end.
                kickoff_hhmm=kickoff,
                schedule_date=info.get("scheduleDate") or None,
                kickoff_js_date=None,
                status_token="",
                can_sale=info.get("disabled", "").strip().lower() != "yes"
                if info.get("disabled") is not None
                else None,
                sale_end_raw=info.get("endTime") or None,
                sale_end_at=None,
                score=_score_or_none(_text(cells[7])),
                raw_row=tr.decode(),
                observed_at=observed_at,
                source_url=source_url,
                extras={
                    "disabled": info.get("disabled", ""),
                    "bg_color": info.get("bgColor", ""),
                    "home_rank": info.get("homeTeamRank"),
                    "away_rank": info.get("guestTeamRank"),
                    "end_time": info.get("endTime", ""),
                },
            )
        )
    if not rows and not re.search(r"暂无(?:比赛|赛事)|没有比赛", soup.get_text()):
        raise SourceParseError("no schedule rows and no explicit empty-issue marker")
    rows.sort(key=lambda row: row.slot)
    return rows


def parse_nowscore_kickoff_dates(
    text: str,
) -> tuple[dict[int, str | None], dict[int, str]]:
    """Read each match's kickoff *calendar date* from the page's script block.

    @param text Decoded page text.
    @return ``(dates, problems)``: ``dates`` maps slot -> ``YYYY-MM-DD`` for every
        slot whose ``M[slot][2]`` assignment could be read as a real calendar
        date, and ``problems`` maps slot -> a machine-readable reason for the
        slots whose assignment exists but is unusable (impossible JS date, or a
        duplicate/conflicting assignment for the same slot). A slot absent from
        both maps simply has no ``M[slot][2]`` assignment.
    @details Only the *date* is taken. The JS clock is deliberately dropped: the
        page rewrites it while a match is live (slot 1 of 26098 reads 14:02:11
        for a 13:00 kickoff), so it is not the planned kickoff.
    """
    dates: dict[int, str] = {}
    problems: dict[int, str] = {}
    for match in re.finditer(
        r"M\[\s*(\d+)\s*\]\[\s*2\s*\]\s*=\s*new\s+Date\(([^)]*)\)", text
    ):
        slot = int(match.group(1))
        parts = [part.strip() for part in match.group(2).split(",")]
        try:
            numbers = [int(part) for part in parts]
        except ValueError:
            problems.setdefault(slot, "kickoff-js-date-not-numeric")
            continue
        if len(numbers) < 3:
            problems.setdefault(slot, "kickoff-js-date-incomplete")
            continue
        year, month, day = numbers[0], numbers[1], numbers[2]
        try:
            parsed = datetime(year, month + 1, day).date().isoformat()
        except ValueError:
            problems.setdefault(slot, "kickoff-js-date-not-a-real-calendar-date")
            continue
        if slot in dates:
            if dates[slot] != parsed:
                dates.pop(slot)
                problems[slot] = "kickoff-js-date-assigned-twice-with-different-dates"
            continue
        dates[slot] = parsed
    for slot in problems:
        dates.pop(slot, None)
    return dates, problems


def _assert_nowscore_issue(soup: BeautifulSoup, issue_id: str) -> None:
    select = soup.find("select", id="dropIssueNum")
    if select is None:
        raise SourceParseError(
            "nowscore page has no #dropIssueNum selector; it is not a DanChang "
            "schedule page (an error page or a layout change)"
        )
    selected = select.find("option", selected=True)
    if selected is None:
        raise SourceParseError("nowscore issue selector has no selected option")
    found = (selected.get("value") or "").strip()
    if found != issue_id:
        raise SourceParseError(
            f"nowscore page selected issue {found!r} but {issue_id!r} was requested; "
            "refusing to attribute another issue's matches to this issue"
        )


def _assert_500_issue(soup: BeautifulSoup, issue_id: str) -> None:
    select = soup.find("select", id="expect_select")
    if select is None:
        raise SourceParseError(
            "500 page has no #expect_select selector; it is not a schedule page"
        )
    selected = select.find("option", selected=True)
    found = (selected.get("value") or "").strip() if selected else ""
    if found != issue_id:
        raise SourceParseError(
            f"500 page selected issue {found!r} but {issue_id!r} was requested; "
            "refusing to attribute another issue's matches to this issue"
        )


def _parse_500_value(raw: str) -> dict[str, str]:
    """Parse 500's ``value="{index:'1',homeTeam:'…'}"`` pseudo-object.

    The page is not JSON (unquoted keys, single quotes), so a targeted scan is
    used. Values are HTML-unescaped; unknown keys are preserved verbatim.
    """
    if not raw.strip():
        return {}
    out: dict[str, str] = {}
    for match in re.finditer(r"(\w+)\s*:\s*(?:'([^']*)'|([^,}]+))", raw):
        key, quoted, bare = match.group(1), match.group(2), match.group(3)
        value = quoted if quoted is not None else (bare or "").strip()
        out[key] = html_unescape(value)
    return out


def _kickoff_title(title: str | None) -> str | None:
    if not title:
        return None
    match = _KICKOFF_TITLE_RE.search(title)
    return match.group(1) if match else None


def _attr_instant(title: str | None) -> str | None:
    """Extract ``截止时间：YYYY-MM-DD HH:MM`` from a title attribute."""
    if not title:
        return None
    text = title.strip()
    match = _CLOSING_TITLE_RE.fullmatch(text)
    if match:
        return match.group(1)
    clock = re.sub(r"^截止时间\s*[：:]\s*", "", text)
    if _is_clock(clock):
        return None
    raise SourceParseError(f"invalid sales deadline: {title!r}")



def _parse_sale_end(title: str | None) -> datetime | None:
    """Turn a ``截止时间：`` title into an aware Beijing-time instant.

    @param title Raw ``title`` attribute of the nowscore status cell.
    @return An aware datetime, or ``None`` when the attribute is absent or does
        not carry a full date. A bare ``HH:mm`` display is *not* a date and never
        produces an instant here.
    """
    text = _attr_instant(title)
    if text is None:
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError as error:
        raise SourceParseError(f"invalid sales deadline: {title!r}") from error
    return parsed.replace(tzinfo=timezone(timedelta(hours=8)))


def _attr_title(title: str | None) -> str | None:
    return title.strip() if title else None


def _nowscore_provider_id(row: Any) -> str:
    """Parse complete Panlu query IDs; reject malformed or conflicting identifiers."""
    ids = set()
    for link in row.select("a[href]"):
        url = urlsplit(link["href"])
        if not url.path.lower().endswith("/panlu.aspx"):
            continue
        values = parse_qs(url.query, keep_blank_values=True).get("id", [])
        if len(values) != 1 or not values[0].isascii() or not values[0].isdigit() or int(values[0]) <= 0:
            raise SourceParseError("invalid nowscore provider id")
        ids.add(values[0])
    if len(ids) > 1:
        raise SourceParseError("conflicting nowscore provider ids")
    return next(iter(ids), "")


def _provider_url(provider_match_id: str) -> str:
    return f"https://cp.nowscore.com/Handle/Panlu.aspx?id={provider_match_id}"


def _text(node: Any) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _is_clock(value: str | None) -> bool:
    if not value or not _CLOCK_RE.fullmatch(value):
        return False
    hour, minute = map(int, value.split(":"))
    return hour <= 23 and minute <= 59


def _score_or_none(value: str | None) -> str | None:
    """Return ``value`` only when it really is a ``home-away`` score.

    @param value Cell text as displayed by the provider.
    @return The score string, or ``None``.
    @details Both sources put non-score UI text in the score cell — nowscore
        shows ``析 亚 欧`` (an analysis link) on the frozen 26098 page. Keeping
        that text as a "score" would let a UI affordance masquerade as a result,
        so anything that is not ``^\\d+-\\d+$`` becomes ``None``. The distinction
        between "no score published" and "a score we could not read" is carried
        by the raw row, which is retained alongside.
    """
    text = (value or "").strip()
    return text if _SCORE_RE.match(text) else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("nonfinite")
        return number
    except ValueError as error:
        raise SourceParseError(f"invalid handicap: {text!r}") from error


def _to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text not in {"true", "false"}:
        raise SourceParseError(f"invalid cansale flag: {value!r}")
    return text == "true"
