"""Offline inputs and separate observed labels for home/away descriptive replay."""
import hashlib
import re
from pathlib import Path
from bs4 import BeautifulSoup
from src.fundamentals_census import read_response
from src.fundamentals_issue_pages import issue_analysis_pages
from src.fundamentals_roster_handicap import roster_handicaps
from src.temporal_learning import Cutoff
from src.temporal_learning.diagnostic_window import diagnostic_date_window
from src.fundamentals_adjudications import fixture_decisions
from src.temporal_learning.core import stable_json_hash


def home_away_windows(pilot, fixtures, *, cutoffs, window, minimum, repository_root):
    """Return per-slot same-venue-role windows, with all roster slots retained.

    Inputs are validated pilot tables and native roster fixtures, explicit
    fixture-relative cutoffs, fixed N/minimum and repo root. Titan-first
    integration is reused; cross-source differences do not veto valid Titan. Known neutral historical matches are
    excluded; neutral target matches remain visible but unavailable. Dates and
    unknown venue flags remain historical proxies. No target labels are read.
    """
    if {str(f['slot']) for f in fixtures} != set(cutoffs):
        raise ValueError('Cutoffs must cover exactly the roster')
    if len({f['slot'] for f in fixtures}) != len(fixtures):
        raise ValueError('Duplicate roster slot')
    integrated = {f['slot']: f for f in pilot['integrated_fixtures']}
    decisions = fixture_decisions(fixtures, pilot.get('adjudications'))
    files = ['src/fundamentals_home_away.py', 'src/fundamentals_adjudications.py', 'src/temporal_learning/diagnostic_window.py',
             'src/temporal_learning/core.py', 'r/fundamentals_home_away.R',
             'r/probability_exploration.R']
    hashes = {f: hashlib.sha256((Path(repository_root)/f).read_bytes()).hexdigest() for f in files}
    hashes.update(pilot['implementation_hashes'])
    hashes['adjudications_sha256'] = stable_json_hash(list(decisions.values()))
    excluded = {f['provider_id'] for f in fixtures}
    result = []
    for f in fixtures:
        slot = f['slot']; base = integrated[slot]
        decision = decisions.get(slot, {})
        mode = decision.get('history_mode', 'SAME_ROLE')
        floor = decision.get('minimum', minimum)
        cutoff = Cutoff.decision_epoch(f['issue'], cutoffs[str(slot)])
        row = dict(issue=f['issue'], slot=slot, provider_id=f['provider_id'],
            home=f['home'], away=f['away'], competition=f['competition'],
            cutoff_utc=cutoff.cutoff_ts.isoformat(), neutral_venue=base['neutral_venue'],
            status='OK_DIAGNOSTIC', identity_source=base['identity_source'],
            history_mode=mode, home_team_id=f['home_id'], away_team_id=f['away_id'],
            adjudication=decision)
        if base['identity_source'] is None:
            row['status'] = 'IDENTITY_UNAVAILABLE'
        elif base['neutral_venue'] is True and mode!='ALL_VENUES':
            row['status'] = 'NEUTRAL_TARGET'
        if decision.get('exclude'):
            row['status'] = 'OWNER_EXCLUDED'
        for side in ('home', 'away'):
            candidates = [r for r in pilot['integrated_history'] if r['slot'] == slot and
                          (f[side+'_id'] in (r['home_id'],r['away_id']) if mode=='ALL_VENUES' else r[side+'_id'] == f[side+'_id'])]
            neutral = [r for r in candidates if re.search(r'\(中\)|（中）|中立', r['home']+r['away'])]
            neutral_ids = {r['history_id'] for r in neutral}
            eligible = candidates if mode=='ALL_VENUES' else [r for r in candidates if r['history_id'] not in neutral_ids]
            if decision.get('exclude'):
                eligible = []
            selected = diagnostic_date_window(eligible, cutoff=cutoff, window=window,
                minimum=floor, timezone='Asia/Shanghai', excluded_ids=excluded,
                source_hashes=pilot['input_file_hashes'], implementation_hashes=hashes)
            row[side+'_window'] = selected['rows']
            row[side+'_receipt'] = selected['receipt']
            row[side+'_neutral_excluded'] = 0 if mode=='ALL_VENUES' else len(neutral)
            if selected['receipt']['status'] != 'OK_DIAGNOSTIC' and row['status'] == 'OK_DIAGNOSTIC':
                row['status'] = 'INSUFFICIENT_HISTORY'
        result.append(row)
    return result


def roster_observed_results(roster_path, *, issue, slots):
    """Read FT labels separately, never odds or ticket settlement.

    Only source rows explicitly marked 完场 with integer FT are scored; delayed,
    cancelled, empty or other states remain nullable and excluded. Published FT
    scope is not independently verified as regulation. Malformed completed
    scores fail closed. No writes or model changes.
    """
    handicaps = roster_handicaps(roster_path, issue=issue, slots=slots)
    meta, raw = read_response(Path(roster_path))
    soup = BeautifulSoup(raw.decode('utf-8-sig'), 'html.parser')
    out = []
    for h in handicaps:
        cells = soup.select_one(f"tr#row_{h['slot']}").select('td')
        if len(cells) < 8:
            raise ValueError('Roster result layout unavailable')
        state = cells[3].get_text(' ', strip=True)
        score = cells[5].get_text(' ', strip=True)
        match = re.fullmatch(r'(\d+)\s*[-:]\s*(\d+)', score)
        if state == '完场' and match is None:
            raise ValueError('Malformed completed score')
        valid = state == '完场' and match is not None
        out.append(dict(slot=h['slot'], provider_id=h['provider_id'], result_state=state,
            actual_home=int(match[1]) if valid else None,
            actual_away=int(match[2]) if valid else None, raw_score=score,
            result_source='nowscore_roster', raw_sha256=meta['sha256'],
            score_scope='SOURCE_PUBLISHED_FT_UNVERIFIED_REGULATION'))
    return out
