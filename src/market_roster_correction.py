"""Explicit, evidence-bound roster display-name corrections; never write raw data."""
import hashlib
import re

from bs4 import BeautifulSoup


def correct_roster_names(raw, *, issue, corrections, evidence):
    """Return derived HTML and receipt, without IO or modifying input bytes.

    Each correction specifies slot, provider_id, role, team_id and name. Only an
    existing empty team anchor may be filled. Evidence maps SHA-256 to saved
    bytes; each correction names its supporting hashes. Decisions must already
    be adjudicated by the caller; hash verification does not establish truth.
    Replaying against the original bytes is deterministic. Applying to already
    corrected HTML fails, preventing silent changes to nonempty source names.
    """
    if not isinstance(raw, bytes) or not corrections:
        raise ValueError('raw bytes and nonempty corrections required')
    for digest, body in evidence.items():
        if not isinstance(body, bytes) or hashlib.sha256(body).hexdigest() != digest:
            raise ValueError('evidence hash mismatch')
    soup = BeautifulSoup(raw.decode('utf-8-sig'), 'html.parser')
    selected = soup.select('select#dropIssueNum option[selected]')
    if len(selected) != 1 or selected[0].get('value') != issue:
        raise ValueError('correction issue mismatch')
    changes, seen = [], set()
    for item in corrections:
        slot, provider, role, team = (item[k] for k in ('slot', 'provider_id', 'role', 'team_id'))
        if (type(slot) is not int or slot <= 0 or role not in ('home', 'away') or
                any(not isinstance(v, str) or not re.fullmatch(r'[1-9][0-9]*', v)
                    for v in (provider, team))):
            raise ValueError('invalid correction identity')
        key = (slot, role)
        if key in seen:
            raise ValueError('duplicate correction')
        seen.add(key)
        name = item['name']
        if not isinstance(name, str) or not name.strip() or name != name.strip():
            raise ValueError('invalid corrected name')
        hashes = item['evidence_sha256']
        if not hashes or any(h not in evidence for h in hashes):
            raise ValueError('missing correction evidence')
        rows = soup.select(f'tr#row_{slot}[matchid="{slot}"]')
        if len(rows) != 1:
            raise ValueError('correction slot mismatch')
        prefix = 'HomeTeam' if role == 'home' else 'GuestTeam'
        nodes = rows[0].select(f'a#{prefix}_{provider}')
        if len(nodes) != 1 or nodes[0].get_text(strip=True):
            raise ValueError('correction requires exactly one empty name')
        if not re.search(rf'/temp/{provider}_{team}\.htm', nodes[0].get('onmouseover', '')):
            raise ValueError('correction native team mismatch')
        nodes[0].string = name
        changes.append(dict(item, old_name='', new_name=name))
    derived = str(soup).encode('utf-8')
    return derived, dict(issue=issue, source_sha256=hashlib.sha256(raw).hexdigest(),
                        derived_sha256=hashlib.sha256(derived).hexdigest(),
                        corrections=changes)
