"""Source-separated standings and dated participation observations; no adjudication."""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from bs4 import BeautifulSoup
from src.temporal_learning import Cutoff


def standings_observations(raw_fields, *, source, issue, slot, provider_id, home_id,
                           away_id, raw_sha256, identity_valid):
    """Extract FT scored league tables from saved generic HTML-cell tables.

    One row per observed team/table/scope, keeping duplicate tables explicit.
    Team ID comes from native team link, never table order or fuzzy name.
    Half-time and handicap-winning tables are excluded via exact column header.
    Nullable rank/league label are retained; malformed values yield error rows
    with raw cell values, never an assumed zero. All output is unadmitted source
    observation, not a contemporaneous league or season assignment. No writes.
    """
    if source not in ('titan','nowscore'):
        raise ValueError('Unsupported source')
    out=[]
    for table in (raw_fields or {}).get('page_tables',[]):
        rows=table['rows']
        if len(rows)<2 or len(rows[0])!=1:
            continue
        header=[c['text'].strip() for c in rows[1]]
        if len(header)<10 or header[0] not in ('','全场') or header[1:10]!=['赛','胜','平','负','得','失','净','得分','排名']:
            continue
        title=rows[0][0]['text']
        links=BeautifulSoup(rows[0][0]['html'],'html.parser').select('a[href]')
        ids={m[1] for a in links if (m:=re.search(r'/team/(\d+)\.htm(?:$|[?#])',a['href'],re.I))}
        team_id=next(iter(ids)) if len(ids)==1 else None
        role='home' if team_id==home_id else 'away' if team_id==away_id else None
        label=re.match(r'^\[(.+)-(\d+)\]',title)
        for cells in rows[2:]:
            values=[c['text'].strip() for c in cells]
            if not values or values[0] not in ('总','主','客','近6'):
                continue
            record=dict(issue=issue,slot=slot,source=source,provider_id=provider_id,
                table_ordinal=table['ordinal'],team_id=team_id,role=role,team_label=title,
                league_label=label[1] if label else None,scope=values[0],raw_values=values,
                raw_sha256=raw_sha256,identity_valid=bool(identity_valid),valid=False,error=None,
                season=None,statistics_as_of=None,historical_admission=False)
            keys=['played','wins','draws','losses','goals_for','goals_against','goal_difference','points','rank']
            record.update(dict.fromkeys(keys))
            try:
                if role is None:
                    raise ValueError('Unmatched or ambiguous native team ID')
                if len(values)<9:
                    raise ValueError('Incomplete scored standings row')
                for pos,key in enumerate(keys,1):
                    value=values[pos] if pos<len(values) else ''
                    if key=='rank' and value in ('','-','--'):
                        continue
                    if not re.fullmatch(r'-?\d+',value):
                        raise ValueError(f'Invalid {key}')
                    record[key]=int(value)
                if any(record[k]<0 for k in keys[:6]) or record['wins']+record['draws']+record['losses']!=record['played'] or record['goals_for']-record['goals_against']!=record['goal_difference']:
                    raise ValueError('Standings arithmetic contradiction')
                record['valid']=True
            except ValueError as exc:
                record['error']=str(exc)
            out.append(record)
    return out


def league_context_tables(report, pilot, *, cutoffs):
    """Return source tables and target-local dated competition participation.

    cutoffs must equal the pilot's explicitly declared epochs. Existing pilot
    integration owns temporal filtering and source-internal history exclusion.
    Participation row = target slot/team/competition/calendar year; observed
    min/max dates are NOT continuous membership dates or a season inference.
    Every opponent observed in existing rows is included, no new crawling or
    recursive team expansion. UNKNOWN category remains UNKNOWN. No ranking,
    learned window, league coefficient, field resolution, database writes or HTTP.
    """
    if cutoffs!=pilot['cutoffs'] or {str(f['slot']) for f in report['fixtures']}!=set(cutoffs):
        raise ValueError('Exact pilot cutoff map required')
    for value in cutoffs.values():
        Cutoff.decision_epoch(report['issue'],value)
    fixtures={f['slot']:f for f in report['fixtures']}
    observations={(o['slot'],o['source']):o for o in report['observations']}
    identities={(o['slot'],o['source']):o['identity_valid'] for o in pilot['source_fixtures']}
    standings=[]
    for field in report['page_fields']:
        f=fixtures[field['slot']];o=observations[field['slot'],field['source']]
        standings.extend(standings_observations(field['raw_fields'],source=field['source'],
            issue=report['issue'],slot=f['slot'],provider_id=f['provider_id'],
            home_id=f['home_id'],away_id=f['away_id'],raw_sha256=o.get('raw_sha256'),
            identity_valid=identities[field['slot'],field['source']]))
    groups=defaultdict(list)
    for h in pilot['integrated_history']:
        for side in ('home','away'):
            groups[h['slot'],h[side+'_id'],h['competition_id'],h['event_date'][:4]].append((h,side))
    participation=[]
    for (slot,team,competition,year),items in sorted(groups.items()):
        f=fixtures[slot]
        role='home' if team==f['home_id'] else 'away' if team==f['away_id'] else 'opponent'
        categories=sorted({h['competition_category'] for h,_ in items})
        participation.append(dict(issue=report['issue'],slot=slot,team_id=team,role=role,
            team_names=sorted({h[side] for h,side in items}),competition_id=competition,
            competition_names=sorted({h['competition_name'] for h,_ in items}),
            competition_categories=categories,calendar_year=int(year),
            first_observed_date=min(h['event_date'] for h,_ in items),
            last_observed_date=max(h['event_date'] for h,_ in items),
            observed_matches=len({h['history_id'] for h,_ in items}),
            history_ids=sorted({h['history_id'] for h,_ in items}),
            sources=sorted({h['source'] for h,_ in items}),
            raw_hashes=sorted({h['raw_sha256'] for h,_ in items}),
            membership_status='PARTICIPATION_ONLY_NOT_MEMBERSHIP',league_tier=None,
            season=None,historical_admission=False))
    totals=[s for s in standings if s['scope']=='总' and s['valid'] and s['identity_valid']]
    pairs=defaultdict(lambda:defaultdict(list))
    for t in totals:
        pairs[t['slot'],t['team_id']][t['source']].append(t)
    comparison=[]
    keys=['played','wins','draws','losses','goals_for','goals_against','goal_difference','points','rank']
    for (slot,team),sides in sorted(pairs.items()):
        if len(sides['titan'])==len(sides['nowscore'])==1:
            a=sides['titan'][0];b=sides['nowscore'][0]
            comparison.append(dict(slot=slot,team_id=team,differing_fields=[k for k in keys if a[k]!=b[k]],
                titan={k:a[k] for k in keys},nowscore={k:b[k] for k in keys},
                decision='UNRESOLVED_NOT_APPLIED'))
    availability=[]
    for f in report['fixtures']:
        for source in ('titan','nowscore'):
            selected=[s for s in standings if s['slot']==f['slot'] and s['source']==source]
            availability.append(dict(slot=f['slot'],source=source,identity_valid=identities[f['slot'],source],
                observed_rows=len(selected),valid_rows=sum(s['valid'] for s in selected),
                total_team_tables=sum(s['scope']=='总' for s in selected)))
    return dict(standings=standings,participation=participation,availability=availability,
        pending_comparison=comparison,receipt=dict(input_file_hashes=report['input_file_hashes'],
        upstream_implementation_hashes=pilot['implementation_hashes'],
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        cutoffs=cutoffs,historical_learning='NONE',historical_admission=False))
