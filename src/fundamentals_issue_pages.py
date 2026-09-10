"""Extract only an explicitly designated issue's analysis-page inventory.

No network or persistence occurs here. Same numeric cross-source IDs produce
candidate URLs, not accepted fixture matches. Settlement fields are not parsed.
"""
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup


def issue_analysis_pages(raw: bytes, *, roster_url: str, issue: str, slots: list[int] | None = None, allow_repeated_provider_ids: bool = False) -> list[dict]:
    """Return one row per roster slot, preserving source names and clock text.

    Inputs are original UTF-8 roster bytes, its HTTPS URL, and a string issue ID.
    Output includes candidate analysis URLs, source-native team IDs, displayed
    date group/clock/deadline (not inferred UTC), and UNVERIFIED pairing status.
    Missing, duplicate or conflicting identity and off-host links raise ValueError.
    Explicit slots restrict extraction without renumbering. Repetition opt-in
    is for an inventory audit only; consumers must quarantine repeated IDs.
    Default whole-roster uniqueness remains enforced.
    No settlement values, linked team histories, I/O, or historical admission.
    """
    if slots is not None and (not isinstance(slots,list) or not slots or any(type(s) is not int or s<1 for s in slots) or len(slots)!=len(set(slots))):
        raise ValueError('invalid explicit roster slot set')
    if type(allow_repeated_provider_ids) is not bool:raise ValueError('Explicit repetition policy required')
    selected_slots=set(slots) if slots is not None else None
    url = urlparse(roster_url)
    if (not isinstance(issue, str) or not re.fullmatch(r"\d+", issue) or
            url.scheme != "https" or url.netloc != "cp.nowscore.com" or
            url.path != "/buy/DanChang.aspx" or
            parse_qs(url.query).get("issueNum") != [issue]):
        raise ValueError("invalid designated issue URL")
    soup = BeautifulSoup(raw.decode("utf-8-sig", errors="strict"), "html.parser")
    selected = soup.select('select#dropIssueNum option[selected]')
    if len(selected) != 1 or selected[0].get('value') != issue:
        raise ValueError("roster issue identity mismatch")
    result = []
    seen_slots, ids = set(), set()
    for row in soup.select('tr[id^="row_"]'):
        slot = row.get("matchid", "")
        if not re.fullmatch(r"[1-9]\d*", slot) or row['id'] != f"row_{slot}" or slot in seen_slots:
            raise ValueError("invalid or duplicate roster slot")
        seen_slots.add(slot)
        if selected_slots is not None and int(slot) not in selected_slots:continue
        links = [urljoin(roster_url, a['href']) for a in row.select('a[href]')
                 if a.get_text(strip=True) == '析']
        if len(links) != 1:
            raise ValueError("missing or ambiguous analysis link")
        match = re.fullmatch(r'https://live\.nowscore\.com/analysis/(\d+)cn\.html', links[0])
        if not match or (match[1] in ids and not allow_repeated_provider_ids):
            raise ValueError("invalid or duplicate analysis identity")
        provider = match[1]
        teams = {}
        for role, prefix in [('home', 'HomeTeam'), ('away', 'GuestTeam')]:
            nodes = row.select(f'a#{prefix}_{provider}')
            if len(nodes) != 1 or not nodes[0].get_text(strip=True):
                raise ValueError("missing team identity")
            native = re.search(rf'/temp/{provider}_(\d+)\.htm', nodes[0].get('onmouseover', ''))
            if not native:
                raise ValueError("missing native team ID")
            teams[role] = nodes[0].get_text(strip=True)
            teams[f'{role}_id'] = native[1]
        # Zero is a missing source ID, not a shared real team identity.
        # Keep source values explicit; downstream analysis pairing stays unverified.
        if teams['home_id'] == teams['away_id'] and (teams['home_id'] != '0' or teams['home'] == teams['away']):
            raise ValueError("same home and away identity")
        cells = row.find_all('td', recursive=False)
        if len(cells) < 4 or not row.get('gamename'):
            raise ValueError("missing roster metadata")
        result.append(dict(issue=issue, slot=int(slot), provider_id=provider,
                           competition=row['gamename'], **teams,
                           date_group=row.get('name'), clock=cells[2].get_text(strip=True),
                           deadline_text=cells[3].get('title'), nowscore_url=links[0],
                           titan_candidate_url=f'https://zq.titan007.com/analysis/{provider}cn.htm',
                           pairing_status='UNVERIFIED'))
        ids.add(provider)
    if selected_slots is not None and {r['slot'] for r in result}!=selected_slots:
        raise ValueError('Requested roster slot set missing')
    if not result:
        raise ValueError("no designated fixtures")
    return result
