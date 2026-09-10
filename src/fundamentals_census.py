"""Deterministic #407 acquisition contracts and offline source census.

No learning, decision-facing features, settlement edits or import-time I/O.
Inputs are explicit response receipts; timestamps are collection evidence only.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from importlib.metadata import version
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import json5
from bs4 import BeautifulSoup

from src.nowscore_settlement import parse_page


def canonical(value: object) -> str:
    """Return deterministic UTF-8-ready JSON; reject nonfinite numbers."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def read_response(path: Path) -> tuple[dict, bytes]:
    """Validate a saved transport receipt; return metadata and original entity bytes.

    Raises ValueError for invalid sizes, timestamps, base64 or HTTP metadata.
    Non-200 bodies remain evidence, never silently parsed as successful pages.
    """
    record = json.loads(path.read_text(encoding="utf-8"))
    for field in ("url", "final_url"):
        if urlparse(record[field]).scheme not in {"http", "https"}:
            raise ValueError(f"invalid {field}")
    start, end = [datetime.fromisoformat(record[k].replace("Z", "+00:00"))
                  for k in ("started_at_utc", "received_at_utc")]
    if start.utcoffset() is None or end.utcoffset() is None or end < start:
        raise ValueError("invalid capture chronology")
    if type(record["status"]) is not int or not 100 <= record["status"] <= 599:
        raise ValueError("invalid HTTP status")
    raw = base64.b64decode(record["body_base64"], validate=True)
    if len(raw) != record["byte_count"] or len(raw) > 10 * 1024 * 1024:
        raise ValueError("response size mismatch or exceeds 10 MiB")
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    declared_sha256 = record.get("sha256")
    if declared_sha256 is not None and (
            not re.fullmatch(r"[0-9a-f]{64}", str(declared_sha256)) or declared_sha256 != actual_sha256):
        raise ValueError("response SHA-256 mismatch")
    meta = {k: v for k, v in record.items() if k != "body_base64"}
    meta["sha256"] = actual_sha256
    return meta, raw


def roster_records(path: Path, issue: str) -> list[dict]:
    """Read a Nowscore SPF roster through its existing authoritative parser.

    One row per issue/slot; native IDs remain strings. The row grouping date is
    a lottery day, not necessarily the kickoff calendar day. Anchor the visible
    clock to the explicit sale-deadline date, advancing one day if before that
    deadline. This is a declared diagnostic reconstruction, verified separately
    against analysis identity; never a claim of actual kickoff or availability.
    Missing/bad deadline/clock or mismatched roster fails closed.
    """
    meta, raw = read_response(path)
    if meta["status"] != 200 or urlparse(meta["final_url"]).hostname != "cp.nowscore.com":
        raise ValueError("roster capture unsuccessful or wrong source")
    rows = parse_page(raw, issue, 5)
    output = []
    for row in rows:
        deadline_match = re.fullmatch(r"截止时间[：:]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", row["cutoff_text"])
        if deadline_match is None:
            raise ValueError("missing explicit roster sale deadline")
        deadline = datetime.strptime(deadline_match[1], "%Y-%m-%d %H:%M")
        clock = datetime.strptime(row["kickoff_time"], "%H:%M")
        dt = deadline.replace(hour=clock.hour, minute=clock.minute)
        if dt < deadline:
            dt += timedelta(days=1)
        output.append({"issue": issue, "slot": row["slot"], "provider_id": row["native_match_id"],
                       "league": row["league"], "roster_home": row["home"], "roster_away": row["away"],
                       "roster_home_id": row["home_id"], "roster_away_id": row["away_id"],
                       "kickoff_utc": dt.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc).isoformat(),
                       "status": row["status"], "roster_sha256": meta["sha256"],
                       "roster_group_date": row["schedule_date"], "roster_clock": row["kickoff_time"],
                       "roster_deadline_utc": deadline.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc).isoformat(),
                       "kickoff_basis": "DIAGNOSTIC_NEXT_CLOCK_AFTER_EXPLICIT_DEADLINE",
                       "roster_received_at_utc": meta["received_at_utc"]})
    if len({(r["issue"], r["slot"]) for r in output}) != len(output):
        raise ValueError("duplicate issue/slot")
    return output


def select_panel(rows: list[dict], *, at_utc: str, leagues: list[str], quotas: dict[str, int], upcoming_issues: list[str]) -> tuple[list[dict], list[dict]]:
    """Freeze a diagnostic stratified sample; not a learned selection policy.

    Quotas key source-native issue IDs. Current/future membership is determined
    at explicit sampling time, not a model cutoff. Return panel and full census
    denominator with reasons. Round-robin leagues; stable hash order within each.
    Repeated provider IDs are logged and excluded, never silently deduplicated.
    """
    at = datetime.fromisoformat(at_utc.replace("Z", "+00:00"))
    if at.utcoffset() is None or not leagues or any(type(n) is not int or n <= 0 for n in quotas.values()):
        raise ValueError("invalid sampling contract")
    panel, denominator, seen = [], [], set()
    for row in rows:
        value = dict(row)
        future = datetime.fromisoformat(row["kickoff_utc"]) > at
        value["period"] = "upcoming" if future else "historical"
        value["reason"] = "eligible"
        if row["issue"] not in quotas:
            value["reason"] = "outside_issue_scope"
        elif row["league"] not in leagues:
            value["reason"] = "outside_competition_scope"
        elif row["issue"] in upcoming_issues and not future:
            value["reason"] = "current_issue_already_started"
        elif row["provider_id"] in seen:
            value["reason"] = "duplicate_provider_candidate"
        if value["reason"] == "eligible":
            seen.add(row["provider_id"])
        denominator.append(value)
    for issue, quota in quotas.items():
        groups = {league: sorted([r for r in denominator if r["issue"] == issue and r["league"] == league
                                 and r["reason"] == "eligible"],
                                key=lambda r: hashlib.sha256(f"407-v1:{issue}:{r['slot']}:{r['provider_id']}".encode()).hexdigest())
                  for league in leagues}
        chosen = []
        while len(chosen) < quota and any(groups.values()):
            for league in leagues:
                if groups[league] and len(chosen) < quota:
                    chosen.append(groups[league].pop(0))
        if len(chosen) != quota:
            raise ValueError(f"insufficient explicit sample population: {issue}, {len(chosen)}/{quota}")
        for row in chosen:
            row["reason"] = "selected"
            panel.append({**row, "panel_kind": "stratified", "sampled_at_utc": at_utc})
    for row in denominator:
        if row["reason"] == "eligible":
            row["reason"] = "eligible_not_selected"
    return panel, denominator


def js_value(text: str, name: str):
    """Parse one declared JS data literal using JSON5, never execute source code.

    Absent declarations return None; malformed/duplicate declarations raise.
    """
    matches = list(re.finditer(r"\bvar\s+" + re.escape(name) + r"\s*=\s*", text))
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"duplicate variable {name}")
    value, error, end = json5.parse(text, start=matches[0].end(), consume_trailing=False, allow_duplicate_keys=False)
    if error or not text[end:].lstrip().startswith(";"):
        raise ValueError(f"malformed data literal {name}: {error}")
    return value


def plain_text(html: str) -> str:
    """Strip source HTML markup and normalize whitespace; retain Unicode names."""
    return " ".join(BeautifulSoup(html, "html.parser").get_text(" ", strip=True).split())


def normalize_schedule_rows(rows: list[list[str]], *, source: str, fixture_local_date: date) -> list[dict]:
    """Map source-specific future-schedule cells to one typed comparison contract.

    ``fixture_local_date`` is the analysis fixture's Asia/Shanghai calendar date.
    Nowscore publishes a full date while Titan publishes month/day only; Titan's
    year is therefore the first matching calendar date on or after the fixture.
    Empty link/display cells are source presentation and are deliberately omitted.
    The caller retains ``rows`` separately as raw source-cell evidence. Malformed
    shapes, dates, team separators, or lead-day labels raise ``ValueError``.
    """
    if source not in {"nowscore", "titan"} or type(fixture_local_date) is not date:
        raise ValueError("invalid schedule normalization context")
    normalized = []
    for row in rows:
        if not isinstance(row, list) or any(not isinstance(value, str) for value in row):
            raise ValueError("malformed schedule row")
        if source == "nowscore":
            if len(row) != 4:
                raise ValueError("malformed Nowscore schedule row")
            competition, date_raw, teams_raw, lead_raw = row
            try:
                event_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
            except ValueError as exc:
                raise ValueError("invalid Nowscore schedule date") from exc
            separator = r"\s+VS\s+"
        else:
            if len(row) != 6 or row[4] or row[3] not in {"", "分析"}:
                raise ValueError("malformed Titan schedule row")
            date_raw, competition, teams_raw, _, _, lead_raw = row
            match = re.fullmatch(r"(\d{2})-(\d{2})", date_raw)
            if match is None:
                raise ValueError("invalid Titan schedule date")
            try:
                month, day = int(match[1]), int(match[2])
                candidate_year = fixture_local_date.year + int(
                    (month, day) < (fixture_local_date.month, fixture_local_date.day))
                event_date = date(candidate_year, month, day)
            except ValueError as exc:
                raise ValueError("invalid Titan schedule date") from exc
            separator = r"\s+-\s+"
        teams = re.split(separator, teams_raw.strip(), maxsplit=1)
        lead = re.fullmatch(r"(\d+)\s*天", lead_raw.strip())
        if (len(teams) != 2 or not all(teams) or not competition.strip() or lead is None or
                event_date < fixture_local_date or (event_date - fixture_local_date).days > 370):
            raise ValueError("invalid future schedule semantics")
        normalized.append({"event_date": event_date.isoformat(), "competition": competition.strip(),
                           "home": teams[0].strip(), "away": teams[1].strip(),
                           "published_lead_days": int(lead[1])})
    return normalized


def decode_analysis_text(raw: bytes) -> tuple[str, str]:
    """Strictly decode declared UTF-8/GB2312/GBK HTML; return text and codec.

    Unknown or conflicting declarations and malformed bytes raise ValueError.
    GB2312 follows the HTML GBK mapping. No I/O or replacement characters.
    """
    declarations = re.findall(br'<meta\b[^>]*\bcharset\s*=\s*[\"\x27]?\s*([A-Za-z0-9_-]+)',
                              raw[:4096], flags=re.IGNORECASE)
    labels = {value.decode("ascii").lower() for value in declarations}
    codecs_by_label = {"utf-8": "utf-8-sig", "utf8": "utf-8-sig", "gb2312": "gbk", "gbk": "gbk"}
    if labels - codecs_by_label.keys():
        raise ValueError("unsupported declared analysis encoding")
    encodings = {codecs_by_label[label] for label in labels}
    if len(encodings) > 1:
        raise ValueError("conflicting declared analysis encodings")
    encoding = next(iter(encodings), "utf-8-sig")
    return raw.decode(encoding, errors="strict"), "utf-8" if encoding == "utf-8-sig" else encoding


class AnalysisFieldError(ValueError):
    """A strict field failure carrying other parsed observations for diagnostics.

    The exception remains fatal to facts callers. partial_record is not accepted
    output; the failed normalized field is None and raw source cells are kept.
    """

    def __init__(self, field: str, message: str, partial_record: dict):
        super().__init__(message)
        self.field = field
        self.partial_record = partial_record


def analysis_record(raw: bytes, *, source: str, provider_id: str, auxiliary_raw: bytes | None = None) -> dict:
    """Parse factual analysis identity, data arrays and actual table cells.

    UTF-8 is the default; declared legacy GB2312/GBK HTML uses strict GBK
    decoding (the HTML-compatible GB2312 label mapping). Malformed bytes/literals,
    missing identity and wrong document IDs raise; absent optional blocks retain
    None, published empty arrays retain []. No scores are corrected or learned.
    """
    if source not in {"nowscore", "titan"} or not re.fullmatch(r"\d+", provider_id):
        raise ValueError("invalid source or provider ID")
    text, encoding = decode_analysis_text(raw)
    soup = BeautifulSoup(text, "html.parser")
    if soup.title is None or "分析" not in soup.title.get_text():
        raise ValueError("not an analysis document")
    home, away = js_value(text, "hometeam"), js_value(text, "guestteam")
    home_id, away_id = js_value(text, "h2h_home"), js_value(text, "h2h_away")
    if not all(isinstance(x, str) and x for x in (home, away)) or not all(type(x) is int and x > 0 for x in (home_id, away_id)):
        raise ValueError("missing team identity")
    if home_id == away_id:
        raise ValueError("same home and away team identity")
    hidden = soup.select_one("#hide_scheduleId")
    if hidden is not None:
        embedded_id = hidden.get("value")
    elif source == "titan":
        embedded_id = js_value(text, "scheduleID")
        if embedded_id is None:
            # Early Titan templates identify this page in both language links.
            # Require independent odds-navigation agreement, not arbitrary IDs
            # in historical arrays or the caller URL.
            language_ids = {match[1] for node in soup.select('a[href]')
                if node.select_one('img[src="image/gb.gif"], img[src="image/big5.gif"]')
                and (match := re.fullmatch(r"(\d+)(?:cn)?\.htm", node['href']))}
            odds_ids = {match[1] for node in soup.select('a[href]')
                if (match := re.fullmatch(r"(?:(?:https?:)?//)1x2\.bet007\.com/oddslist/(\d+)\.htm", node['href']))}
            if language_ids == odds_ids and len(language_ids) == 1:
                embedded_id = next(iter(language_ids))
    else:
        active_ids = {match[1] for node in soup.select("li.uu_on a[href]")
                      if (match := re.fullmatch(r"/analysis/(\d+)(?:cn)?\.html?", node.get("href", ""), re.I))}
        embedded_id = active_ids.pop() if len(active_ids) == 1 else None
    if str(embedded_id) != provider_id:
        raise ValueError("missing or mismatched response fixture ID")
    time_node = soup.select_one("#hide_matchTime")
    time_raw = time_node.get("value") if time_node else js_value(text, "strTime")
    if source == "nowscore" and not time_raw:
        # The archived inline document profile publishes its full timestamp
        # in a labelled team_info cell rather than a hidden/script field.
        visible_times = [re.fullmatch(r"比赛时间[：:]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*", plain_text(str(node)))
                         for node in soup.select("td.team_info strong")]
        visible_times = [match[1] for match in visible_times if match]
        if len(visible_times) > 1:
            raise ValueError("ambiguous visible fixture kickoff")
        time_raw = visible_times[0] if visible_times else None
    if source == "titan" and not time_raw:
        # Archived Titan pages publish the full timestamp in their clock script.
        clock_values = [re.fullmatch(r"CalcTime\.asp\?matchTime=(\d{4}[-/]\d{1,2}[-/]\d{1,2} \d{1,2}:\d{2}:\d{2})", node["src"])
                        for node in soup.select('script[src*="CalcTime.asp?"]')]
        if len(clock_values) != 1 or clock_values[0] is None:
            raise ValueError("missing or ambiguous archived Titan clock")
        time_raw = datetime.strptime(clock_values[0][1].replace("/", "-"), "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        visible_times = re.findall(r"开赛时间[：:]\s*(\d{4}-\d{2}-\d{2})\s*星期[一二三四五六日天]\s*(\d{1,2}:\d{2})",
                                   soup.get_text(" ", strip=True))
        if (len(visible_times) != 1 or
                datetime.strptime(" ".join(visible_times[0]), "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M") != time_raw[:16]):
            raise ValueError("archived Titan visible kickoff disagrees with clock")
    if not time_raw:
        raise ValueError("missing fixture kickoff")
    if not isinstance(time_raw, str) or not re.fullmatch(r"\d{4}[-/]\d{2}[-/]\d{2} \d{2}:\d{2}(?::\d{2})?", time_raw):
        raise ValueError("invalid source-local fixture kickoff")
    dt = datetime.fromisoformat(time_raw.replace("/", "-"))
    auxiliary_nodes = soup.select('script[src*="/analysisJs/data"]')
    if auxiliary_nodes:
        if source != "nowscore" or len(auxiliary_nodes) != 1 or auxiliary_nodes[0]["src"] != f"/analysisJs/data{provider_id}.js":
            raise ValueError("unexpected auxiliary data identity")
        if auxiliary_raw is None:
            raise ValueError("required analysis JS was not captured")
    blocks_from_auxiliary = bool(auxiliary_nodes)
    data_text = auxiliary_raw.decode("utf-8-sig", errors="strict") if blocks_from_auxiliary else text
    blocks = {name: js_value(data_text, name) for name in ("h_data", "a_data", "v_data")}
    history_id_column = 20 if source == "nowscore" else 15
    for name, records in blocks.items():
        if records is not None and (not isinstance(records, list) or any(not isinstance(row, list) or len(row) <= history_id_column for row in records)):
            raise ValueError(f"malformed {name} row shape")
    history = []
    for block, records in blocks.items():
        for ordinal, row in enumerate(records or []):
            if (not all(type(row[i]) is int for i in (4, 6, 8, 9, history_id_column)) or
                    any(row[i] <= 0 for i in (4, 6, history_id_column)) or row[4] == row[6] or
                    any(row[i] < 0 for i in (8, 9))):
                raise ValueError(f"invalid history integer in {block}")
            halftime_raw = str(row[10]).strip()
            halftime_match = re.fullmatch(r"(\d+)\s*[-:]\s*(\d+)", halftime_raw)
            if halftime_match is None and halftime_raw not in {"", "-", "--"}:
                raise ValueError(f"invalid halftime score in {block}")
            date_raw = str(row[0])
            if re.fullmatch(r"\d{2}-\d{2}-\d{2}", date_raw):
                date_raw = "20" + date_raw
            date = datetime.strptime(date_raw, "%Y-%m-%d").date().isoformat()
            halftime_home = int(halftime_match[1]) if halftime_match else None
            halftime_away = int(halftime_match[2]) if halftime_match else None
            if ((halftime_home is not None and halftime_home > row[8]) or
                    (halftime_away is not None and halftime_away > row[9])):
                raise ValueError(f"halftime score exceeds full-time score in {block}")
            history.append({"block": block, "ordinal": ordinal, "history_id": str(row[history_id_column]), "event_date": date,
                            "home_id": str(row[4]), "away_id": str(row[6]), "home_score": row[8], "away_score": row[9],
                            "halftime_home_score": halftime_home,
                            "halftime_away_score": halftime_away,
                            "score_scope": "SOURCE_PUBLISHED_FULL_TIME",
                            "home_text": plain_text(str(row[5])), "away_text": plain_text(str(row[7]))})
    standings_by_side = {}
    for table in soup.find_all("table"):
        if table.find("table"):
            continue
        rows = [[plain_text(str(td)) for td in tr.find_all(["td", "th"], recursive=False)]
                for tr in table.find_all("tr")]
        full = any(["得分" if c == "积分" else c for c in row[:10]] == ["全场", "赛", "胜", "平", "负", "得", "失", "净", "得分", "排名"] for row in rows)
        totals = [r for r in rows if r and r[0] == "总" and len(r) == 11]
        if full and totals:
            team_links = [link.get("href", "") for link in table.find_all("a", href=True)]
            team_ids = {match[1] for href in team_links
                        if (match := re.search(r"/team/(?:Summary/)?(\d+)\.html?(?:[?#].*)?$",
                                               href, flags=re.IGNORECASE))}
            if len(team_ids) != 1:
                raise ValueError("standings table requires one team identity")
            team_id = team_ids.pop()
            side = "home" if team_id == str(home_id) else "away" if team_id == str(away_id) else None
            if side is None or side in standings_by_side:
                raise ValueError("standings table has unknown or duplicate team identity")
            values = totals[0][1:10]
            if any(v not in {"", "-"} and not re.fullmatch(r"-?\d+", v) for v in values):
                raise ValueError("invalid standings integer")
            standings_by_side[side] = {"side": side, "team_id": team_id, "state": "POPULATED",
                                       "values": [None if v in {"", "-"} else int(v) for v in values]}
    season_tables = [standings_by_side.get(side, {"side": side,
                                                  "team_id": str(home_id if side == "home" else away_id),
                                                  "state": "ABSENT", "values": None})
                     for side in ("home", "away")]
    injuries, previous_lineup, schedule_source_rows = [], [], []
    injury_section_present = False
    previous_lineup_section_present = False
    schedule_section_present = False
    for table in soup.find_all("table"):
        if table.find("table"):
            continue
        rows = [[plain_text(str(td)) for td in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        if ["球员", "缺阵原因"] in rows:
            injury_section_present = True
            start = rows.index(["球员", "缺阵原因"]) + 1
            for row in rows[start:]:
                if any("上一场阵容" in x for x in row):
                    break
                if len(row) == 2 and all(row) and not any("暂无" in x for x in row):
                    injuries.append(row)
        if ["首发", "后备"] in rows:
            previous_lineup_section_present = True
            lineup_start = rows.index(["首发", "后备"]) + 1
            previous_lineup.extend(cell for row in rows[lineup_start:] if len(row) == 2 for cell in row if cell)
        elif any(row[:5] == ["号码", "球员", "位置", "首发", "评分"] for row in rows):
            previous_lineup_section_present = True
            previous_lineup.extend(row[0] + " " + row[1] for row in rows if len(row) >= 2 and row[0].isdigit() and row[1])
        if any(("日期" in row or "时间" in row) and "对阵" in row for row in rows):
            schedule_section_present = True
            schedule_source_rows.extend(row for row in rows if any(re.fullmatch(r"(?:\d{2,4}-)?\d{2}-\d{2}", c) for c in row))
    schedule_error = None
    try:
        schedules = normalize_schedule_rows(
            schedule_source_rows, source=source,
            fixture_local_date=dt.replace(tzinfo=ZoneInfo("Asia/Shanghai")).date())
    except ValueError as exc:
        schedules = None
        schedule_error = str(exc)
    top_text = plain_text(str(soup))[:1800]
    venue_match = re.search(r"场地[：:]\s*(.*?)\s*天气[：:]", top_text)
    weather_match = re.search(r"天气[：:]\s*(.*?)\s*温度[：:]", top_text)
    temperature_match = re.search(r"温度[：:]\s*([^\s]+)", top_text)
    season_links = sorted(set(re.findall(r"(?:score|league_vs)/([0-9]{4}(?:-[0-9]{4})?)/([0-9]+)", text)))
    record = {"source": source, "provider_id": provider_id, "home": home, "away": away,
            "home_id": str(home_id), "away_id": str(away_id),
            "kickoff_utc": dt.replace(tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(timezone.utc).isoformat(),
            "season_links": season_links, "blocks": blocks, "blocks_from_auxiliary": blocks_from_auxiliary,
            "history": history, "season_tables": season_tables,
            "injuries": injuries, "injury_section_present": injury_section_present,
            "previous_lineup": previous_lineup, "previous_lineup_section_present": previous_lineup_section_present,
            "schedules": schedules, "schedule_source_rows": schedule_source_rows,
            "schedule_section_present": schedule_section_present,
            "venue": venue_match[1].strip() or None if venue_match else None,
            "weather": weather_match[1].strip() or None if weather_match else None,
            "temperature": temperature_match[1] if temperature_match else None,
            "title": soup.title.get_text(" ", strip=True), "encoding": "utf-8" if encoding == "utf-8-sig" else encoding}
    if schedule_error is not None:
        record["quarantined_fields"] = ["schedules"]
        raise AnalysisFieldError("schedules", schedule_error, record)
    return record


def compare_pair(left: dict, right: dict) -> list[dict]:
    """Return all comparable identity/standing/history differences as audit rows.

    Matching native IDs is only a candidate crosswalk, not independent identity
    proof. Different target names/kickoff quarantine the fixture. Missing blocks
    are missingness, not agreement. Same-ID history differences remain unresolved.
    """
    findings = []
    for field in ("home", "away", "home_id", "away_id", "kickoff_utc"):
        if left[field] != right[field]:
            findings.append({"field": field, "left": canonical(left[field]), "right": canonical(right[field]),
                             "disposition": "IDENTITY_AMBIGUOUS"})
    if findings:
        return findings
    for field in ("season_tables", "schedules"):
        incomplete_standings = (field == "season_tables" and
                                any(row["state"] != "POPULATED" for row in left[field] + right[field]))
        if left[field] != right[field] or incomplete_standings:
            findings.append({"field": field, "left": canonical(left[field]), "right": canonical(right[field]),
                             "disposition": ("COVERAGE_DIFFERENCE"
                                             if bool(left[field]) != bool(right[field]) or incomplete_standings
                                             else "UNRESOLVED")})
    for block in ("h_data", "a_data", "v_data"):
        a = [r for r in left["history"] if r["block"] == block]
        b = [r for r in right["history"] if r["block"] == block]
        # Compare every occurrence, preserving duplicates and membership differences.
        keys = sorted(set(r["history_id"] for r in a + b))
        for key in keys:
            fields = ("event_date", "home_id", "away_id", "home_score", "away_score",
                      "halftime_home_score", "halftime_away_score", "score_scope")
            x = [tuple(r[f] for f in fields) for r in a if r["history_id"] == key]
            y = [tuple(r[f] for f in fields) for r in b if r["history_id"] == key]
            if x != y or len(x) != 1 or len(y) != 1:
                findings.append({"field": f"{block}:{key}", "left": canonical(x), "right": canonical(y),
                                 "disposition": "UNRESOLVED" if x and y else "COVERAGE_DIFFERENCE"})
    return findings


def write_rows(path: Path, rows: list[dict], columns: list[str]) -> None:
    """Write a tidy UTF-8 CSV with declared columns, including empty tables.

    None becomes an empty cell, zero remains zero. Nested values are JSON text.
    Caller owns transaction directory; unknown columns raise rather than drop.
    """
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: canonical(v) if isinstance(v, (dict, list, tuple)) else v for k, v in row.items()})


def build_outputs(root: Path, output: Path, *, generated_at_utc: str) -> dict:
    """Replay a declared raw capture directory into immutable tidy census tables.

    root contains panel.json, denominator.json and raw-browser/{source}-{id}.json.
    Missing/failed requests are explicit rows; invalid receipts stop the build.
    Parse failures stay PARSER_FAILURE, never optional-field absence. Output must
    not exist. Publish by directory rename only after all contracts/hashes pass;
    temporary work rolls back on error. Return machine-readable diagnostic receipt.
    """
    if output.exists():
        raise FileExistsError(output)
    implementation_paths = [Path(__file__), Path(__file__).with_name("nowscore_settlement.py"), Path(__file__).with_name("nowscore_bjdc_sp_history.py"), Path(__file__).with_name("multimarket_p0.py")]
    implementation_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in implementation_paths}
    generated = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00"))
    if generated.utcoffset() is None:
        raise ValueError("generation time requires timezone")
    panel = json.loads((root / "panel.json").read_text())
    denominator = json.loads((root / "denominator.json").read_text())
    fixture_keys = [(r["issue"], r["slot"]) for r in panel]
    keys = [(r["issue"], r["slot"], r["provider_id"]) for r in panel]
    if (not panel or len(fixture_keys) != len(set(fixture_keys)) or
            any(not isinstance(r.get(field), str) or not r[field].strip()
                for r in panel for field in ("roster_home", "roster_away")) or
            len({r["provider_id"] for r in panel}) != len(panel)):
        raise ValueError("empty, incomplete, or duplicate panel identity")
    counts = {k: sum((r["issue"], r["slot"], r["provider_id"]) == k for r in denominator) for k in keys}
    if any(n != 1 for n in counts.values()):
        raise ValueError("panel to denominator must be one-to-one")
    response_rows, identity_rows, field_rows, history_rows, findings = [], [], [], [], []
    roster_by_fixture = {}
    source_hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                     for name in ("panel.json", "denominator.json")}
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(row.get("roster_sha256", ""))) for row in panel):
        raise ValueError("panel requires roster provenance")
    for issue in sorted({row["issue"] for row in panel}):
        roster_path = root / f"roster-{issue}.json"
        roster_meta, _ = read_response(roster_path)
        if any(row["roster_sha256"] != roster_meta["sha256"] for row in denominator if row["issue"] == issue):
            raise ValueError("roster provenance differs from denominator")
        source_hashes[roster_path.name] = hashlib.sha256(roster_path.read_bytes()).hexdigest()
        for row in roster_records(roster_path, issue):
            roster_by_fixture[(row["issue"], row["slot"], row["provider_id"])] = row
    if any((row["issue"], row["slot"], row["provider_id"]) not in roster_by_fixture for row in panel):
        raise ValueError("panel fixture absent from authoritative roster")
    revision_path = root / "sampling-revision.json"
    if revision_path.exists():
        revision = json.loads(revision_path.read_text())
        if revision["new_panel_sha256"] != source_hashes["panel.json"]:
            raise ValueError("sampling revision panel hash mismatch")
        source_hashes[revision_path.name] = hashlib.sha256(revision_path.read_bytes()).hexdigest()
    for selected in panel:
        parsed = {}
        provider_id = selected["provider_id"]
        roster = roster_by_fixture[(selected["issue"], selected["slot"], provider_id)]
        for source in ("nowscore", "titan"):
            key = {"issue": selected["issue"], "slot": selected["slot"], "provider_id": provider_id,
                   "source": source, "league": selected["league"], "period": selected["period"],
                   "panel_kind": selected["panel_kind"]}
            path = root / "raw-browser" / f"{source}-{provider_id}.json"
            response = {**key, "status": None, "received_at_utc": None, "sha256": None,
                        "byte_count": None, "final_url": None, "content_type": None,
                        "capture_state": "NOT_ATTEMPTED", "parse_state": "NOT_PARSED", "error": None,
                        "evidence_class": None, "auxiliary_url": None, "auxiliary_sha256": None,
                        "auxiliary_received_at_utc": None, "auxiliary_status": None}
            if path.exists():
                source_hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
                document = json.loads(path.read_text())
                if "error" in document:
                    response.update(capture_state="TRANSPORT_FAILURE", error=document["error"])
                else:
                    meta, raw = read_response(path)
                    for k in ("status", "received_at_utc", "sha256", "byte_count", "final_url", "content_type"):
                        response[k] = meta[k]
                    expected_host = "live.nowscore.com" if source == "nowscore" else "zq.titan007.com"
                    suffix = "html" if source == "nowscore" else "htm"
                    expected_url = f"https://{expected_host}/analysis/{provider_id}cn.{suffix}"
                    if meta["url"] != expected_url:
                        raise ValueError("capture request identity mismatch")
                    response["capture_state"] = "HTTP_OK" if meta["status"] == 200 and meta["final_url"] == expected_url else "HTTP_FAILURE"
                    received = datetime.fromisoformat(meta["received_at_utc"].replace("Z", "+00:00"))
                    response["evidence_class"] = "OBSERVED" if received < datetime.fromisoformat(selected["kickoff_utc"]) else "HISTORICAL_PROXY"
                    if response["capture_state"] == "HTTP_OK":
                        try:
                            primary_received_at_utc = response["received_at_utc"]
                            primary_evidence_class = response["evidence_class"]
                            auxiliary_evidence_class = None
                            auxiliary_raw = None
                            auxiliary_path = root / "raw-browser" / f"nowscore-js-{provider_id}.json"
                            if source == "nowscore" and auxiliary_path.exists():
                                source_hashes[str(auxiliary_path.relative_to(root))] = hashlib.sha256(auxiliary_path.read_bytes()).hexdigest()
                                primary_soup = BeautifulSoup(raw.decode("utf-8-sig", errors="strict"), "html.parser")
                                if primary_soup.select('script[src*="/analysisJs/data"]'):
                                    auxiliary_document = json.loads(auxiliary_path.read_text())
                                    if "error" in auxiliary_document:
                                        raise ValueError(f"auxiliary transport failure: {auxiliary_document['error']}")
                                    auxiliary_meta, auxiliary_raw = read_response(auxiliary_path)
                                    response.update(auxiliary_url=auxiliary_meta["final_url"],
                                                    auxiliary_sha256=auxiliary_meta["sha256"],
                                                    auxiliary_received_at_utc=auxiliary_meta["received_at_utc"],
                                                    auxiliary_status=auxiliary_meta["status"])
                                    expected_url = f"https://live.nowscore.com/analysisJs/data{provider_id}.js"
                                    if auxiliary_meta["status"] != 200 or auxiliary_meta["final_url"] != expected_url or auxiliary_meta["url"] != expected_url:
                                        raise ValueError("auxiliary response failed or identity mismatch")
                                    auxiliary_received = datetime.fromisoformat(auxiliary_meta["received_at_utc"].replace("Z", "+00:00"))
                                    auxiliary_evidence_class = "OBSERVED" if auxiliary_received < datetime.fromisoformat(selected["kickoff_utc"]) else "HISTORICAL_PROXY"
                                    # Availability is no earlier than the last required response.
                                    if auxiliary_received > received:
                                        response["received_at_utc"] = auxiliary_meta["received_at_utc"]
                                        response["evidence_class"] = auxiliary_evidence_class
                            data = analysis_record(raw, source=source, provider_id=provider_id, auxiliary_raw=auxiliary_raw)
                            if not data["blocks_from_auxiliary"]:
                                response["received_at_utc"] = primary_received_at_utc
                                response["evidence_class"] = primary_evidence_class
                            parsed[source] = data
                            response["parse_state"] = "PARSED"
                        except ValueError as exc:
                            response.update(parse_state="PARSER_FAILURE", error=str(exc))
            response_rows.append(response)
            if source not in parsed:
                continue
            record = parsed[source]
            identity_rows.append({**key, **{k: record[k] for k in ("home", "away", "home_id", "away_id", "kickoff_utc", "season_links")},
                                  "roster_home_id_equal": record["home_id"] == roster["roster_home_id"],
                                  "roster_away_id_equal": record["away_id"] == roster["roster_away_id"],
                                  "roster_kickoff_equal": record["kickoff_utc"] == roster["kickoff_utc"]})
            for field in ("h_data", "a_data", "v_data", "season_tables", "injuries", "previous_lineup",
                          "schedules", "schedule_source_rows", "venue", "weather", "temperature"):
                value = record["blocks"].get(field) if field in record["blocks"] else record[field]
                n = len(value) if isinstance(value, list) else int(value is not None)
                state = "POPULATED" if n else "PUBLISHED_NO_DATA"
                if field == "season_tables" and any(row["state"] != "POPULATED" for row in value):
                    state = "PARTIAL"
                section_absent = ((field == "injuries" and not record["injury_section_present"]) or
                                  (field == "previous_lineup" and not record["previous_lineup_section_present"]) or
                                  (field in {"schedules", "schedule_source_rows"} and
                                   not record["schedule_section_present"]))
                if value is None or section_absent:
                    state = "ABSENT"
                from_auxiliary = field in record["blocks"] and record["blocks_from_auxiliary"]
                field_rows.append({**key, "field": field, "field_state": state, "record_count": n,
                                   "observed_value": canonical(value),
                                   "evidence_class": auxiliary_evidence_class if from_auxiliary else primary_evidence_class,
                                   "received_at_utc": response["auxiliary_received_at_utc"] if from_auxiliary else primary_received_at_utc,
                                   "raw_sha256": response["auxiliary_sha256"] if from_auxiliary else response["sha256"]})
            history_rows.extend({**key, **row} for row in record["history"])
        pair_findings = compare_pair(parsed["nowscore"], parsed["titan"]) if len(parsed) == 2 else []
        for field in ("roster_home", "roster_away", "kickoff_utc"):
            if selected[field] != roster[field]:
                pair_findings.append({"field": f"panel_{field}", "left": roster[field],
                                      "right": selected[field], "disposition": "IDENTITY_AMBIGUOUS"})
        for record in parsed.values():
            for field, roster_field in (("home_id", "roster_home_id"), ("away_id", "roster_away_id"),
                                        ("kickoff_utc", "kickoff_utc")):
                if record[field] != roster[roster_field]:
                    pair_findings.append({"field": f"roster_{field}:{record['source']}",
                                          "left": roster[roster_field], "right": record[field],
                                          "disposition": "IDENTITY_AMBIGUOUS"})
        for finding in pair_findings:
            findings.append({"issue": selected["issue"], "slot": selected["slot"], "provider_id": provider_id,
                             "league": selected["league"], "panel_kind": selected["panel_kind"], **finding})
    output.parent.mkdir(parents=True, exist_ok=True)
    base_columns = ["issue", "slot", "provider_id", "source", "league", "period", "panel_kind"]
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".census-build-") as tmp:
        stage = Path(tmp) / "release"
        stage.mkdir()
        write_rows(stage / "responses.csv", response_rows, base_columns + ["status", "received_at_utc", "sha256", "byte_count", "final_url", "content_type", "capture_state", "parse_state", "error", "evidence_class", "auxiliary_url", "auxiliary_sha256", "auxiliary_received_at_utc", "auxiliary_status"])
        write_rows(stage / "identity.csv", identity_rows, base_columns + ["home", "away", "home_id", "away_id", "kickoff_utc", "season_links", "roster_home_id_equal", "roster_away_id_equal", "roster_kickoff_equal"])
        write_rows(stage / "fields.csv", field_rows, base_columns + ["field", "field_state", "record_count", "observed_value", "evidence_class", "received_at_utc", "raw_sha256"])
        write_rows(stage / "history.csv", history_rows, base_columns + ["block", "ordinal", "history_id", "event_date", "home_id", "away_id", "home_score", "away_score", "halftime_home_score", "halftime_away_score", "score_scope", "home_text", "away_text"])
        write_rows(stage / "findings.csv", findings, ["issue", "slot", "provider_id", "league", "panel_kind", "field", "left", "right", "disposition"])
        write_rows(stage / "panel.csv", panel, list(panel[0]))
        write_rows(stage / "denominator.csv", denominator, list(denominator[0]))
        if implementation_hashes != {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in implementation_paths}:
            raise ValueError("implementation changed during replay")
        receipt = {"schema": "bj407_diagnostic_census_v1", "generated_at_utc": generated_at_utc,
                   "historical_learning": "NONE", "source_hashes": source_hashes,
                   "implementation_hashes": implementation_hashes,
                   "dependencies": {p: version(p) for p in ("json5", "beautifulsoup4")},
                   "output_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.glob("*.csv"))},
                   "panel_rows": len(panel), "response_rows": len(response_rows), "finding_rows": len(findings),
                   "admission": "DIAGNOSTIC_ONLY; unresolved fields/identity remain quarantined; no learned or settlement outputs"}
        (stage / "receipt.json").write_text(canonical(receipt) + "\n", encoding="utf-8")
        os.rename(stage, output)
    return receipt
