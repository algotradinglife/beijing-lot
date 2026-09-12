"""Offline, missing-only settlement SP supplementation; no database writes or learning."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from decimal import Decimal

from bs4 import BeautifulSoup


def parse_500_bf(payload: bytes) -> list[dict]:
    """Parse GB18030 original HTML. Preserve SP text, native ID and sale-day context.

    Returns one row per slot. Invalid/duplicate identities or SP text raise.
    scheduleDate is a 10:00-to-next-10:00 sale day, not a calendar kickoff date.
    """
    soup = BeautifulSoup(payload.decode("gb18030"), "html.parser")
    rows = []
    for tr in soup.select("tr.vs_lines"):
        attrs = dict(re.findall(r"(\w+):'([^']*)'", tr["value"]))
        cells = tr.select("td")
        clock = cells[2]["title"].removeprefix("比赛时间：")
        kickoff = datetime.strptime(attrs["scheduleDate"] + " " + clock, "%Y-%m-%d %H:%M")
        if kickoff.hour < 10:
            kickoff += timedelta(days=1)
        score_node = tr.select_one('a.red.eng[title="析"]')
        sp_node = tr.select_one("td.h_br span.eng.red")
        raw_sp = sp_node.get_text(strip=True) if sp_node else ""
        if raw_sp and (not re.fullmatch(r"\d+(?:\.\d+)?", raw_sp) or Decimal(raw_sp) < 1):
            raise ValueError("Invalid settlement SP")
        rows.append(dict(slot=int(attrs["index"]), provider_id=tr["fid"],
                         home=attrs["homeTeam"], away=attrs["guestTeam"],
                         league=attrs["leagueName"], sale_day=attrs["scheduleDate"],
                         kickoff=kickoff.strftime("%Y-%m-%d %H:%M"), timezone="Asia/Shanghai",
                         score=score_node.get_text(strip=True).replace(":", "-") if score_node else "",
                         raw_sp=raw_sp))
    if not rows or len({r["slot"] for r in rows}) != len(rows):
        raise ValueError("Missing or duplicate slots")
    return rows


def build_sp_supplement(observations: list[dict], provider_rows: list[dict], *,
                        issue: str, source_sha256: str, aliases: dict[str, str]) -> dict:
    """Build exact-target approvals and full denominator audit, never overwrite.

    Inputs are native Nowscore payloads including expected_option and 500 rows.
    Explicit team aliases only; compare orientation, league, month/day/time and
    score. Historical year availability remains unproven. Blank SP alone is
    eligible; zero/invalid/nonblank existing cells are never replaced.
    """
    native = {r["slot"]: r for r in observations}
    other = {r["slot"]: r for r in provider_rows}
    if len(native) != len(observations) or len(other) != len(provider_rows) or native.keys() != other.keys():
        raise ValueError("Roster denominator mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("Invalid evidence hash")
    audit, corrections = [], []
    for slot, n in sorted(native.items()):
        if n["issue"] != issue or n["play"] != "bf":
            raise ValueError("Wrong issue/play")
        p = other[slot]
        mismatches = [field for field in ("home", "away")
                      if aliases.get(p[field], p[field]) != n[field]]
        if p["league"] != n["league"]:
            mismatches.append("league")
        if p["kickoff"][5:] != n["kickoff_time"]:
            mismatches.append("kickoff")
        if p["score"] != n["score"]:
            mismatches.append("score")
        options = n["options"]
        eligible = len(options) == 1 and options[0]["raw_sp"] == "" and options[0]["sp"] is None
        status = "preserved_existing"
        if eligible:
            status = "quarantined" if mismatches or not p["raw_sp"] else "approved_missing_only"
            if status == "approved_missing_only":
                if options[0]["option"] != n["expected_option"]:
                    raise ValueError("Winner does not match expected option")
                corrections.append(dict(issue=issue, slot=slot, play="bf", option=options[0]["option"],
                    home=n["home"], away=n["away"], score=n["score"], native_match_id=n["native_match_id"],
                    original_raw_sp="", original_source_sha256=n["source_sha256"],
                    replacement_raw_sp=p["raw_sp"], replacement_sp=float(Decimal(p["raw_sp"])),
                    replacement_source="500.com", replacement_source_sha256=source_sha256,
                    provider_id=p["provider_id"], status=status))
        audit.append(dict(slot=slot, status=status, mismatches=mismatches,
                          nowscore=n, provider=p))
    return dict(issue=issue, play="bf", corrections=corrections, audit=audit,
                aliases=aliases, historical_learning="NONE", prospective_availability="UNPROVEN")
