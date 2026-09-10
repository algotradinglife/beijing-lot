"""Read source-published integer lottery handicaps; no market probability inference."""
import re
from pathlib import Path
from bs4 import BeautifulSoup
from src.fundamentals_census import read_response
from src.fundamentals_issue_pages import issue_analysis_pages


def roster_handicaps(roster_path, *, issue, slots):
    """Return requested original slots and signed home-goal adjustments.

    Reads a saved unredirected HTTP-200 UTF-8 roster receipt. Validates native
    issue/fixture identity through the authoritative inventory parser. Missing,
    duplicate, noninteger slots/handicaps fail. Output is diagnostic only; no
    chronology admission, settlement parsing, network access or writes.
    """
    if not isinstance(slots, list) or not slots or any(type(s) is not int or s < 1 for s in slots) or len(set(slots)) != len(slots):
        raise ValueError("Distinct positive integer slots required")
    meta, raw = read_response(Path(roster_path))
    if meta["status"] != 200 or meta["url"] != meta["final_url"]:
        raise ValueError("Unredirected successful roster required")
    inventory = {f["slot"]: f for f in issue_analysis_pages(raw, roster_url=meta["url"], issue=issue, slots=slots)}
    soup = BeautifulSoup(raw.decode("utf-8-sig"), "html.parser")
    result = []
    for slot in slots:
        if slot not in inventory:
            raise ValueError("Requested slot missing")
        node = soup.select_one(f"tr#row_{slot}")
        value = node.get("polygoal", "")
        if not re.fullmatch(r"[+-]?\d+", value):
            raise ValueError("Explicit integer lottery handicap required")
        result.append(dict(slot=slot, provider_id=inventory[slot]["provider_id"],
            home_handicap=int(value), evidence_class="HISTORICAL_PROXY",
            historical_admission=False, raw_sha256=meta["sha256"]))
    return result
