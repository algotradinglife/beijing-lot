"""One-issue offline field integration; diagnostic observations, never model input admission."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import re
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

from src.fundamentals_census import plain_text

SOURCE_POLICY = 'TITAN_PRIMARY_NOWSCORE_FILL_CROSSCHECK_NONVETO'


def competition_context(links):
    """Extract a unique native competition link, ID, category and explicit season.

    Only labelled competition-material links qualify; general navigation does
    not. Unknown/ambiguous links retain missing metadata, never name guessing.
    """
    candidates = []
    for link in links:
        name = re.sub(r'\s*资料(?:库)?$', '', link['text']).strip()
        if name == link['text'] or name == '球队':
            continue
        u = urlparse(link['url'])
        query = {k.lower(): v for k, v in parse_qs(u.query).items()}
        match = re.search(r'/cup_match/([^/]+)/cupmatch_vs/cupmatch_(\d+)\.htm$', u.path)
        league = re.search(r'/league_match/league_vs/([^/]+)/(\d+)\.htm$', u.path)
        if match or league:
            m = match or league
            candidates.append(dict(competition_id=m[2], competition_name=name,
                competition_category='CUP' if match else 'LEAGUE', season=m[1], competition_url=link['url']))
        elif re.search(r'/(?:CupMatch|SubLeague|League)\.aspx$', u.path, re.I) and len(query.get('sclassid', [])) == 1:
            candidates.append(dict(competition_id=query['sclassid'][0], competition_name=name,
                competition_category='CUP' if 'cupmatch' in u.path.lower() else 'LEAGUE',
                season=(query.get('matchseason') or [None])[0], competition_url=link['url']))
    unique = {json.dumps(row, sort_keys=True): row for row in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else dict(
        competition_id=None, competition_name=None, competition_category='UNKNOWN', season=None, competition_url=None)


def weather_context(page_text):
    """Observe header weather independently from temperature, preserving blanks.

    Celsius point/range is parsed only with an explicit degree-C marker. No
    forecast/availability inference, unit guessing, fetching or mutation.
    """
    header = page_text[:1800]
    match = re.search(r'天气[：:]\s*(.*?)(?:倒计时|距开赛|联赛积分|对赛往绩|$)', header)
    raw = match[1].strip(' ,，') if match else None
    temp = re.search(r'([+-]?\d+(?:\.\d+)?)(?:\s*[~～]\s*([+-]?\d+(?:\.\d+)?))?\s*℃', raw or '')
    lo = float(temp[1]) if temp else None
    hi = float(temp[2] or temp[1]) if temp else None
    if lo is not None and lo > hi:
        raise ValueError('Reversed source temperature range')
    description = re.sub(r'\s+', ' ', raw[:temp.start()] if temp else raw or '').strip(' ,，℃') or None
    canonical = {'間中有雲': '间中有云', '多雲': '多云'}.get(description, description)
    return dict(weather_raw=raw, weather_description=description, weather_normalized=canonical,
                temperature_min_c=lo, temperature_max_c=hi, weather_availability='UNKNOWN')


def field_choice(titan, nowscore):
    """Prefer validated Titan; Nowscore fills missing values or flags differences.

    A cross-source difference is not proof that Titan is wrong. Both original
    observations stay in source tables; this choice never rewrites either one.
    """
    if titan is None and nowscore is None:
        return dict(value=None, source=None, status='MISSING')
    if titan is None:
        return dict(value=copy.deepcopy(nowscore), source='nowscore', status='NOWSCORE_FILL')
    if nowscore is not None and titan != nowscore:
        return dict(value=copy.deepcopy(titan), source='titan', status='TITAN_PRIMARY_CROSSCHECK_DIFFERENCE')
    return dict(value=copy.deepcopy(titan), source='titan', status='AGREEMENT' if nowscore is not None else 'TITAN_ONLY')


def history_observations(raw, *, issue, slot, source, provider_id, body_sha256, cutoff, categories):
    """Flatten raw arrays with original ordinal and per-row structural/date checks.

    One row is one page/block occurrence, not one global historical match.
    Same-day chronology is unknown; earlier dates are diagnostic proxies only.
    Source-published FT is NOT asserted to be regulation-time scoring. Weather
    and season are missing when absent from history rows; no target inheritance.
    """
    result = []
    for block in ('home_history_raw', 'away_history_raw', 'head_to_head_raw'):
        values = raw.get(block)
        if values is None:
            continue
        if not isinstance(values, list):
            continue  # Original block and parser diagnostics stay in source report.
        for ordinal, row in enumerate(values):
            index = 20 if source == 'nowscore' else 15
            record = dict(issue=issue, slot=slot, source=source, provider_id=provider_id,
                block=block, ordinal=ordinal, history_id=None, event_date=None,
                competition_id=None, competition_name=None, competition_category='UNKNOWN',
                season=None, home_id=None, away_id=None, home=None, away=None,
                home_goals=None, away_goals=None, halftime_home_goals=None, halftime_away_goals=None,
                score_scope='SOURCE_PUBLISHED_FULL_TIME_UNVERIFIED_REGULATION', weather=None,
                chronology='UNKNOWN', valid=False, error=None, raw_sha256=body_sha256,
                raw_value=copy.deepcopy(row))
            try:
                if not isinstance(row, list) or len(row) <= index:
                    raise ValueError('Malformed history row')
                if any(type(row[i]) is not int or row[i] <= 0 for i in (1, 4, 6, index)):
                    raise ValueError('Invalid history identifiers')
                if row[4] == row[6] or any(type(row[i]) is not int or row[i] < 0 for i in (8, 9)):
                    raise ValueError('Invalid history teams or full-time goals')
                day = str(row[0]); day = '20' + day if re.fullmatch(r'\d{2}-\d{2}-\d{2}', day) else day
                event = datetime.strptime(day, '%Y-%m-%d').date()
                half = re.fullmatch(r'(\d+)\s*[-:]\s*(\d+)', str(row[10]).strip())
                half_error = None
                if half and (int(half[1]) > row[8] or int(half[2]) > row[9]):
                    half_error = 'HALFTIME_QUARANTINED'
                    half = None
                elif not half and str(row[10]).strip() not in ('', '-', '--', 'None'):
                    half_error = 'HALFTIME_UNPARSED'
                category = categories.get((source, str(row[1])), 'UNKNOWN')
                # Explicit source labels, not a substring heuristic.
                if plain_text(str(row[2])) in ('球會友誼', '球会友谊', '友谊赛', '友誼賽'):
                    category = 'FRIENDLY'
                record.update(history_id=str(row[index]), event_date=event.isoformat(),
                    competition_id=str(row[1]), competition_name=plain_text(str(row[2])),
                    competition_category=category, home_id=str(row[4]), away_id=str(row[6]),
                    home=plain_text(str(row[5])), away=plain_text(str(row[7])), home_goals=row[8], away_goals=row[9],
                    halftime_home_goals=int(half[1]) if half else None, halftime_away_goals=int(half[2]) if half else None,
                    chronology='BEFORE_DATE_PROXY' if event < cutoff.date() else 'SAME_DAY_UNKNOWN' if event == cutoff.date() else 'POST_CUTOFF',
                    valid=True, error=half_error)
            except (ValueError, TypeError) as exc:
                record['error'] = str(exc)
            result.append(record)
    return result


def pilot_tables(report, *, cutoffs, adjudications=None):
    """Build aligned source fixtures, long histories and Titan-first diagnostic tables.

    cutoffs maps every slot string to an explicit timezone-aware decision time.
    Identity requires native team IDs and kickoff agreement with native roster
    clock after deadline. Name aliases alone do not block matched native IDs.
    Unavailable strict/partial identity prevents integration of that source.
    Optional identity-bound owner decisions may accept an exact Titan kickoff;
    native team IDs and deadline/day checks still apply. No historical admission.
    Returns JSON-compatible tables plus input/code identities in the report.
    """
    fixtures = {r['slot']: r for r in report['fixtures']}
    from src.fundamentals_adjudications import fixture_decisions
    decisions = fixture_decisions(report['fixtures'], adjudications)
    if set(cutoffs) != {str(slot) for slot in fixtures}:
        raise ValueError('Explicit cutoff required for every fixture')
    deadlines = {}
    for slot, fixture in fixtures.items():
        cutoff = datetime.fromisoformat(cutoffs[str(slot)].replace('Z', '+00:00'))
        if cutoff.utcoffset() is None:
            raise ValueError('Cutoff requires timezone')
        deadline = datetime.strptime(fixture['deadline_text'].split('：', 1)[-1].strip(), '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo('Asia/Shanghai'))
        if cutoff > deadline:
            raise ValueError('Cutoff exceeds declared lottery deadline')
        deadlines[slot] = (cutoff.astimezone(ZoneInfo('Asia/Shanghai')), deadline)
    source_rows = []; categories = {}; histories = []; source_exclusions = []
    for obs, fields in zip(report['observations'], report['page_fields'], strict=True):
        if any(obs[k] != fields[k] for k in ('issue', 'slot', 'source')):
            raise ValueError('Observation/field identity mismatch')
        raw = fields.get('raw_fields') or {}
        context_error = None
        try:
            context = competition_context(raw.get('page_links', []))
        except ValueError as exc:
            context = competition_context([]); context_error = str(exc)
            source_exclusions.append(dict(slot=obs['slot'],source=obs['source'],field='competition',
                reason='INVALID_SOURCE_COMPETITION',error=context_error,raw_sha256=obs.get('raw_sha256')))
        if context['competition_id'] is not None:
            key = (obs['source'], context['competition_id'])
            if key in categories and categories[key] != context['competition_category']:
                categories[key] = 'UNKNOWN'
                source_exclusions.append(dict(slot=obs['slot'],source=obs['source'],field='competition_category',
                    reason='AMBIGUOUS_SOURCE_CATEGORY_MAPPING',raw_sha256=obs.get('raw_sha256')))
            else:
                categories[key] = context['competition_category']
        row = {k: obs.get(k) for k in ('issue', 'slot', 'source', 'provider_id', 'url', 'raw_sha256', 'parse_state', 'home', 'away', 'home_id', 'away_id', 'kickoff_utc')}
        fixture = fixtures[obs['slot']]; cutoff, deadline = deadlines[obs['slot']]
        kickoff = datetime.fromisoformat(obs['kickoff_utc']) if obs.get('kickoff_utc') else None
        accepted = decisions.get(obs['slot'], {}).get('titan_kickoff_utc')
        accepted_time = (obs['source']=='titan' and accepted is not None and kickoff is not None and
                         kickoff == datetime.fromisoformat(accepted))
        identity = (obs.get('home_id') == fixture['home_id'] and obs.get('away_id') == fixture['away_id'] and
            kickoff is not None and
            (kickoff.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%H:%M') == fixture['clock'] or accepted_time) and
            deadline <= kickoff < deadline + timedelta(days=1))
        weather_error = None
        try:
            weather = weather_context(raw.get('page_text', ''))
        except ValueError as exc:
            weather_error = str(exc); weather = weather_context('')
            weather['weather_raw'] = raw.get('page_text', '')[:1800]
            source_exclusions.append(dict(slot=obs['slot'],source=obs['source'],field='weather',
                reason='INVALID_SOURCE_WEATHER',error=weather_error,raw_sha256=obs.get('raw_sha256')))
        row.update(context); row.update(weather)
        row.update(weather_parse_error=weather_error,competition_parse_error=context_error)
        row.update(identity_valid=bool(identity), approved_kickoff_used=bool(accepted_time), cutoff_utc=cutoff.isoformat(),
            neutral_venue=True if re.search(r'中立场|中立場', raw.get('page_text', '')[:1000]) else None,
            historical_admission=False)
        source_rows.append(row)
    # Build history after observing all category links, without crossing source IDs.
    for obs, fields in zip(report['observations'], report['page_fields'], strict=True):
        histories.extend(history_observations(fields.get('raw_fields') or {}, issue=obs['issue'], slot=obs['slot'],
            source=obs['source'], provider_id=obs['provider_id'], body_sha256=obs.get('raw_sha256'),
            cutoff=deadlines[obs['slot']][0], categories=categories))
    by_key = {(r['slot'], r['source']): r for r in source_rows}
    if len(by_key) != 2 * len(fixtures):
        raise ValueError('Two-source fixture cardinality required')
    integrated = []; crosscheck_differences = []
    selected_fields = ('competition_id', 'competition_category', 'season', 'weather_normalized',
                       'temperature_min_c', 'temperature_max_c', 'neutral_venue')
    for slot, fixture in fixtures.items():
        pair = {s: by_key[slot, s] for s in ('titan', 'nowscore')}
        for source in pair:
            pair[source]['integration_eligible'] = pair[source]['identity_valid'] and (
                source == 'titan' or pair['titan']['identity_valid'] or pair['titan']['raw_sha256'] is None)
        chosen = pair['titan'] if pair['titan']['integration_eligible'] else pair['nowscore'] if pair['nowscore']['integration_eligible'] else None
        row = dict(issue=report['issue'], slot=slot, provider_id=fixture['provider_id'],
            home=chosen['home'] if chosen else None, away=chosen['away'] if chosen else None,
            kickoff_utc=chosen['kickoff_utc'] if chosen else None,
            competition_name=chosen['competition_name'] if chosen else None,
            identity_source=chosen['source'] if chosen else None, historical_admission=False)
        for field in selected_fields:
            values = {s: pair[s][field] if pair[s]['integration_eligible'] else None for s in pair}
            if field == 'competition_category':
                values = {s: None if v == 'UNKNOWN' else v for s, v in values.items()}
            choice = field_choice(values['titan'], values['nowscore'])
            row[field] = choice['value']; row[field + '_source'] = choice['source']; row[field + '_status'] = choice['status']
        competition_id = row['competition_id']
        if competition_id is None:
            row['competition_name'] = None
            row['competition_name_source'] = None
            for dependent in ('competition_category', 'season'):
                row[dependent] = None
                row[dependent + '_source'] = None
                row[dependent + '_status'] = row['competition_id_status']
        else:
            same_competition = {s: pair[s] for s in pair if pair[s]['integration_eligible'] and pair[s]['competition_id'] == competition_id}
            name_source = 'titan' if 'titan' in same_competition else 'nowscore'
            row['competition_name'] = same_competition[name_source]['competition_name']
            row['competition_name_source'] = name_source
            for dependent in ('competition_category', 'season'):
                values = {s: same_competition.get(s, {}).get(dependent) for s in ('titan', 'nowscore')}
                choice = field_choice(values['titan'], values['nowscore'])
                row[dependent] = choice['value']; row[dependent + '_source'] = choice['source']; row[dependent + '_status'] = choice['status']
        for field in selected_fields:
            if row[field+'_status']=='TITAN_PRIMARY_CROSSCHECK_DIFFERENCE':
                crosscheck_differences.append(dict(slot=slot,history_id=None,fields=[field],
                    retained_source='titan',status='TITAN_RETAINED_PENDING_CROSSCHECK',
                    observations=[dict(source=s,raw_sha256=pair[s]['raw_sha256'],
                        url=pair[s]['url'],value=copy.deepcopy(pair[s][field])) for s in pair]))
        integrated.append(row)
    # One occurrence per fixture/history ID. Preserve every source/block row above.
    groups = {}
    excluded = source_exclusions
    for row in histories:
        target = fixtures[row['slot']]
        required = ({target['home_id']} if row['block'] == 'home_history_raw' else
                    {target['away_id']} if row['block'] == 'away_history_raw' else {target['home_id'], target['away_id']})
        teams = {row['home_id'], row['away_id']}
        if row['history_id'] == target['provider_id'] or not row['valid'] or not required.issubset(teams) or row['chronology'] != 'BEFORE_DATE_PROXY' or not by_key[row['slot'], row['source']]['integration_eligible']:
            excluded.append(dict(slot=row['slot'], source=row['source'], ordinal=row['ordinal'], block=row['block'], reason='INVALID_IDENTITY_VALUE_OR_CHRONOLOGY'))
            continue
        groups.setdefault((row['slot'], row['history_id']), []).append(row)
    integrated_history = []
    core = ('event_date', 'home_id', 'away_id', 'home_goals', 'away_goals', 'competition_id')
    for (slot, history_id), rows in sorted(groups.items()):
        primary = [r for r in rows if r['source'] == 'titan'] or rows
        variants = {tuple(r[k] for k in core) for r in primary}
        if len(variants) != 1:
            excluded.append(dict(slot=slot, history_id=history_id,
                reason=primary[0]['source'].upper()+'_INTERNAL_HISTORY_CONFLICT'))
            continue
        chosen = copy.deepcopy(primary[0])
        differing = [k for k in core if any(r[k] != chosen[k] for r in rows)]
        if differing:
            crosscheck_differences.append(dict(slot=slot, history_id=history_id, fields=differing,
                retained_source=chosen['source'], status='TITAN_RETAINED_PENDING_CROSSCHECK',
                observations=[{k:r[k] for k in ('source','raw_sha256')+core} for r in rows]))
        chosen.pop('raw_value')
        chosen.update(selection='TITAN_PRIMARY' if chosen['source'] == 'titan' else 'NOWSCORE_FILL',
            observed_sources=sorted({r['source'] for r in rows}), blocks=sorted({r['block'] for r in rows}),
            historical_admission=False)
        # Titan halftime remains primary; conflicts inside the source itself
        # quarantine that field, while Nowscore only fills an absent Titan field.
        core_matched = [r for r in rows if all(r[k]==chosen[k] for k in core)]
        nowscore_rows = [r for r in rows if r['source']=='nowscore']
        nowscore_consistent = len({tuple(r[k] for k in core) for r in nowscore_rows})<=1
        for field in ('halftime_home_goals', 'halftime_away_goals'):
            titan_available = [r for r in core_matched if r['source']=='titan' and r[field] is not None]
            if not titan_available and not nowscore_consistent:
                chosen[field]=None;chosen[field+'_source']=None
                chosen[field+'_status']='NOWSCORE_FILL_INTERNAL_CONFLICT'
                chosen['error']='HALFTIME_FILL_QUARANTINED'
                excluded.append(dict(slot=slot,history_id=history_id,field=field,
                    reason='NOWSCORE_INTERNAL_HISTORY_CONFLICT_HALFTIME_FILL'))
                continue
            available_rows = titan_available or [r for r in core_matched if r[field] is not None]
            vals = {r[field] for r in available_rows}
            if len(vals) > 1:
                chosen[field] = None
                chosen[field + '_source'] = None
                chosen[field + '_status'] = 'INTERNAL_SOURCE_CONFLICT'
                chosen['error'] = 'HALFTIME_CONFLICT_QUARANTINED'
            else:
                available = available_rows[0] if available_rows else None
                chosen[field] = available[field] if available else None
                chosen[field + '_source'] = available['source'] if available else None
                chosen[field + '_status'] = 'MISSING' if available is None else 'NOWSCORE_FILL' if available['source'] == 'nowscore' else 'TITAN_PRIMARY'
                if available and any(r[field] is not None and r[field]!=available[field] for r in rows):
                    chosen[field + '_status'] = 'TITAN_PRIMARY_CROSSCHECK_DIFFERENCE'
                    crosscheck_differences.append(dict(slot=slot,history_id=history_id,fields=[field],
                        retained_source=available['source'],status='TITAN_RETAINED_PENDING_CROSSCHECK',
                        observations=[{k:r[k] for k in ('source','raw_sha256',field)} for r in rows]))
        integrated_history.append(chosen)
    return dict(schema='bj411_one_issue_pilot_v1', source_policy=SOURCE_POLICY, adjudications=list(decisions.values()), source_fixtures=source_rows,
        source_history=histories, integrated_fixtures=integrated, integrated_history=integrated_history,
        exclusions=excluded, crosscheck_differences=crosscheck_differences, input_file_hashes=report['input_file_hashes'],
        cutoff_policy='EXPLICIT_DEADLINE; EARLIER_LOCAL_DATE_ONLY; HISTORICAL_PROXY_NOT_ADMITTED',
        cutoffs=copy.deepcopy(cutoffs), historical_learning='NONE',
        generated_at_utc=datetime.now(timezone.utc).isoformat(), runtime=copy.deepcopy(report['runtime']),
        implementation_hashes=copy.deepcopy(report['implementation_hashes']) | {
            'fundamentals_pilot.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
