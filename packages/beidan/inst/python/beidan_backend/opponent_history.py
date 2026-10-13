"""Offline competition/venue metadata beside the verified factual history.

This module does not admit rows, infer availability, fit, fetch or write. Source
IDs are preserved; neutral markers mean source-reported neutral, not proof of
non-neutrality when absent. Existing analysis_record owns identity/score parsing.
"""
import re
from bs4 import BeautifulSoup
from .fundamentals import analysis_record, plain_text


def parse_opponent_history(raw, *, source, provider_id, expected_identity,
                           auxiliary_raw=None):
    """Return competition metadata and factual keys from a bound analysis page.

    raw/auxiliary_raw are original UTF-8 bytes. expected_identity is the existing
    six-field oriented fixture identity. Historical competition ID/name come
    from positions 1/2 of validated source arrays; never from team name guesses.
    Invalid IDs fail; empty rendered names remain None with an explicit state.
    Published empty arrays remain empty. Target
    competition is the unique history ID matching the explicit title league;
    absent/ambiguous matching yields None, not a guessed league. No side effects.
    """
    if not isinstance(raw, bytes) or not isinstance(expected_identity, dict):
        raise ValueError('Original bytes and explicit fixture identity required')
    record = analysis_record(raw, source=source, provider_id=provider_id,
                             expected_identity=expected_identity,
                             auxiliary_raw=auxiliary_raw)
    for key in ('provider_id', 'home_id', 'away_id', 'kickoff_utc'):
        if record[key] != expected_identity[key]:
            raise ValueError('Bound analysis identity differs: ' + key)
    soup = BeautifulSoup(raw.decode('utf-8-sig'), 'html.parser')
    match = re.search(r'赛季([^()（）]+)[)）]', soup.title.get_text())
    target_name = match[1].strip() if match else None
    rows = []
    for factual in record['history']:
        original = record['blocks'][factual['block']][factual['ordinal']]
        if (type(original[1]) is not int or original[1] <= 0
                or not isinstance(original[2], str)):
            raise ValueError('Positive competition ID and textual name field required')
        name=plain_text(original[2]) or None
        rows.append({**factual, 'competition_id': str(original[1]),
                     'competition_name': name,
                     'competition_name_state':'PUBLISHED_NAME' if name else 'EMPTY_RENDERED_NAME',
                     'neutral_reported': '(中)' in factual['home_text']
                         or '(中)' in factual['away_text']})
    ids = sorted({r['competition_id'] for r in rows
                  if target_name is not None and r['competition_name'] == target_name})
    # First oriented team link belongs to the match header in these templates.
    home_links=[a for a in soup.select('a[href]') if re.search(
        r'/team/(?:Summary/)?'+re.escape(record['home_id'])+r'\.html?(?:[?#].*)?$',
        a['href'],flags=re.I)]
    target_neutral=bool(home_links and '(中)' in home_links[0].get_text())
    return dict(identity={k: record[k] for k in expected_identity}, rows=rows,
                target_competition_name=target_name,
                target_competition_id=ids[0] if len(ids) == 1 else None,
                target_neutral_reported=target_neutral,
                target_venue_evidence='SOURCE_HEADER_NEUTRAL_MARKER' if target_neutral else 'NEUTRALITY_NOT_REPORTED',
                target_competition_state='MATCHED_TITLE_HISTORY' if len(ids) == 1
                    else 'ABSENT_OR_AMBIGUOUS_TITLE_HISTORY')
