"""Bounded Titan acquisition using Nowscore fixture identities; no cutoff selection."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid
from zoneinfo import ZoneInfo

import json5
from beidan_backend.issue_schedule.fetch import fetch_issue_page
from .history import (_js_array, euro_history_url, over_under_history_url,
                      parse_euro_history_js, parse_over_under_history_json)

BJT = ZoneInfo("Asia/Shanghai")


def titan_identity(payload: bytes) -> dict:
    """Read native ID, names, UTC JS kickoff; reject unknown or duplicate literals."""
    text = payload.decode("utf-8-sig")
    result = {}
    for name in ("ScheduleID", "hometeam_cn", "guestteam_cn", "MatchTime"):
        values = re.findall(r'(?:^|[;\n])\s*(?:var\s+)?' + name + r'\s*=\s*([^;]+);', text)
        if len(values) != 1:
            raise ValueError("Missing/duplicate Titan identity: " + name)
        result[name] = json5.loads(values[0])
    clock = re.fullmatch(r"(\d{4}),(\d{1,2})(-1)?,(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2})", result["MatchTime"])
    if not clock:
        raise ValueError("Invalid Titan UTC kickoff")
    y, m, sub, d, h, minute, sec = clock.groups()
    result["kickoff_at"] = datetime(int(y), int(m) if sub else int(m)+1,
        int(d), int(h), int(minute), int(sec), tzinfo=timezone.utc).astimezone(BJT)
    if type(result["ScheduleID"]) is not int or result["ScheduleID"] <= 0:
        raise ValueError("Invalid Titan native ID")
    return result


def validate_fixture(fixture: dict) -> datetime:
    """Validate an explicit Nowscore row before any request; return typed kickoff."""
    for field in ("fixture_id", "provider_id_nowscore", "home_nowscore", "away_nowscore"):
        value = fixture.get(field)
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError("Missing fixture field: " + field)
    if not fixture["provider_id_nowscore"].isdigit() or int(fixture["provider_id_nowscore"]) <= 0:
        raise ValueError("Invalid Nowscore provider ID")
    kickoff = datetime.fromisoformat(fixture["kickoff_at"])
    if kickoff.tzinfo is None:
        raise ValueError("kickoff_at must carry a timezone")
    return kickoff


def parse_markets(fixture: dict, euro_body: bytes, totals_bodies: dict[str, bytes]) -> dict:
    """Validate Titan identity then return all valid timed pregame company quotes.

    Euro decimal prices and totals Hong Kong prices converted to decimal. Company
    namespaces remain separate. Missing/invalid rows are counted, never replaced.
    """
    kickoff = validate_fixture(fixture)
    identity = titan_identity(euro_body)
    if (str(identity["ScheduleID"]) != fixture["provider_id_nowscore"] or
        identity["kickoff_at"] != kickoff or
        identity["hometeam_cn"] != fixture["home_nowscore"] or
        identity["guestteam_cn"] != fixture["away_nowscore"]):
        raise ValueError("Titan/Nowscore fixture identity mismatch")
    pid = fixture["provider_id_nowscore"]
    euro, totals, companies, diagnostics = [], [], [], []
    seen = set()
    for entry in _js_array(euro_body.decode("utf-8-sig"), "game"):
        parts = entry.split("|")
        if len(parts) not in (24, 27) or not parts[0].isdigit() or parts[0] in seen:
            raise ValueError("Invalid/duplicate Titan euro company")
        seen.add(parts[0])
        if parts[23] not in {"0", "1"}:
            raise ValueError("Invalid exchange flag")
        if parts[23] == "1":
            diagnostics.append(dict(market="euro", company_id=parts[0], reason="exchange_excluded", count=1))
            continue
        company, rows, counts = parse_euro_history_js(euro_body, kickoff_hkt=kickoff, company_id=int(parts[0]))
        companies.append(dict(market="euro", company_id=parts[0], company_name=company))
        for row in rows:
            if row.complete and all(math.isfinite(x) and x > 1 for x in row.odds.values()):
                euro.append(dict(fixture_id=fixture["fixture_id"], company_id=parts[0],
                    quote_at=datetime.fromisoformat(row.snapshot_ts_hkt).isoformat(timespec="seconds"), odds_home=row.odds["home"],
                    odds_draw=row.odds["draw"], odds_away=row.odds["away"], source_url=euro_history_url(pid)))
        diagnostics.extend(dict(market="euro",company_id=parts[0],reason=k,count=v) for k,v in counts.items())
    for company_id, body in totals_bodies.items():
        rows, counts = parse_over_under_history_json(body, kickoff_hkt=kickoff)
        companies.append(dict(market="totals", company_id=company_id, company_name=""))
        for row in rows:
            if row.complete and all(math.isfinite(x) and x > 0 for x in row.odds.values()):
                if not (math.isfinite(row.line_value) and 0 <= row.line_value <= 30 and row.line_value*4 == round(row.line_value*4)):
                    raise ValueError("Invalid Asian total line")
                totals.append(dict(fixture_id=fixture["fixture_id"], company_id=company_id,
                    quote_at=datetime.fromisoformat(row.snapshot_ts_hkt).isoformat(timespec="seconds"), line=row.line_value,
                    over_decimal=row.odds["over"]+1, under_decimal=row.odds["under"]+1,
                    source_url=over_under_history_url(pid,int(company_id),kickoff)))
        diagnostics.extend(dict(market="totals",company_id=company_id,reason=k,count=v) for k,v in counts.items())
    diagnostics = [dict(fixture_id=fixture["fixture_id"], **row) for row in diagnostics]
    return dict(euro=euro, totals=totals, companies=companies, diagnostics=diagnostics,
                identity={**identity,"kickoff_at":identity["kickoff_at"].isoformat()})


def fetch_markets(fixtures: list[dict], raw_dir: str, totals_company_ids: list[str],
                  timeout: float = 25, retries: int = 2, pages: dict | None = None) -> dict:
    """Capture selected fixtures with >=1s request spacing, persist before parsing.

    pages is an explicit offline mapping keyed by source URL with body bytes and
    original observed_at. One immutable directory per invocation. Failures retain
    evidence and appear in coverage; no synthetic quotes or SP are produced.
    """
    if not isinstance(raw_dir,str) or not raw_dir.strip():
        raise ValueError("raw_dir required")
    if not totals_company_ids or any(not isinstance(x,str) or not x.isdigit() or int(x)<=0 for x in totals_company_ids) or len(set(totals_company_ids)) != len(totals_company_ids):
        raise ValueError("Unique positive totals company IDs required")
    if not math.isfinite(timeout) or timeout<=0 or type(retries) is not int or not 0<=retries<=3:
        raise ValueError("Invalid timeout/retries")
    for fixture in fixtures:
        validate_fixture(fixture)
    if len({x['fixture_id'] for x in fixtures}) != len(fixtures) or len({x['provider_id_nowscore'] for x in fixtures}) != len(fixtures):
        raise ValueError("Duplicate fixture/provider IDs")
    directory = Path(raw_dir) / str(uuid.uuid4())
    directory.mkdir(parents=True,exist_ok=False)
    result = dict(euro=[],totals=[],companies=[],diagnostics=[],coverage=[],captures=[],identities=[])
    last_request = None
    for fixture in fixtures:
        pid = fixture['provider_id_nowscore']
        urls = {'euro':euro_history_url(pid)}
        urls.update({f'total_{c}':over_under_history_url(pid,int(c),validate_fixture(fixture)) for c in totals_company_ids})
        bodies = {}
        try:
            for market,url in urls.items():
                if pages is None:
                    if last_request is not None:
                        time.sleep(max(0,1-(time.monotonic()-last_request)))
                    try:
                        response=fetch_issue_page(url,timeout=timeout,retries=retries,backoff_sec=1)
                    finally:
                        last_request=time.monotonic()
                    body, observed = response.body, response.observed_at
                else:
                    page=pages[url]
                    body, observed=page['body'],page['observed_at']
                if isinstance(body, bytearray):
                    body = bytes(body)
                if not isinstance(body,bytes):
                    raise ValueError('Raw body must be bytes')
                stamp=datetime.fromisoformat(observed)
                if stamp.tzinfo is None:
                    raise ValueError('observed_at must carry original timezone')
                path=directory/f'{pid}-{market}.raw'
                path.write_bytes(body)
                result['captures'].append(dict(fixture_id=fixture['fixture_id'],market=market,
                    source_url=url,observed_at=stamp.astimezone(BJT).isoformat(),raw_path=str(path),
                    sha256=hashlib.sha256(body).hexdigest()))
                (directory/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                bodies[market]=body
            parsed=parse_markets(fixture,bodies['euro'],{c:bodies[f'total_{c}'] for c in totals_company_ids})
            result['identities'].append(dict(fixture))
            for key in ('euro','totals','companies','diagnostics'):
                result[key].extend(parsed[key])
            complete = bool(parsed['euro']) and bool(parsed['totals'])
            result['coverage'].append(dict(fixture_id=fixture['fixture_id'],status='ok' if complete else 'partial',detail='' if complete else 'No usable pregame quotes in one or both markets',
                euro_rows=len(parsed['euro']),totals_rows=len(parsed['totals'])))
        except (ValueError,KeyError,RuntimeError,OSError) as exc:
            result['coverage'].append(dict(fixture_id=fixture['fixture_id'],status='error',detail=str(exc),euro_rows=0,totals_rows=0))
        (directory/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (directory/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    result['receipt_path']=str(directory/'receipt.json')
    return result
