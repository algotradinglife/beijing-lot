"""Selected-window context for retrospective miss review, never model fitting."""
from src.fundamentals_league_context import league_context_tables
from src.temporal_learning import Cutoff


def score_review_context(report, pilot, windows, *, cutoffs):
    """Return fixture metadata and separate pending source-evidence queue.

    Only histories already selected by shared cutoff windows support league
    participation or selected-history discrepancy counts. Single league IDs on
    each side permit SAME/DIFFERENT observed participation, never league tier or
    membership inference. Missing/ambiguous evidence remains UNKNOWN. Counts
    refer to unique target-local histories, not duplicated home/away occurrences.
    No labels, new window rules, corrections, network, fitting or writes.
    """
    keys=('issue','slot','provider_id')
    if (len(windows)!=len(report['fixtures']) or
        {tuple(w[k] for k in keys) for w in windows}!={tuple(f[k] for k in keys) for f in report['fixtures']}):
        raise ValueError('Review window identity mismatch')
    for w in windows:
        cutoff=Cutoff.decision_epoch(report['issue'],cutoffs[str(w['slot'])])
        if w['cutoff_utc']!=cutoff.cutoff_ts.isoformat():
            raise ValueError('Review window cutoff mismatch')
    selected={(w['slot'],h['history_id']):h for w in windows for side in ('home','away') for h in w[side+'_window']}
    context=league_context_tables(report,dict(pilot,integrated_history=list(selected.values())),cutoffs=cutoffs)
    bases={f['slot']:f for f in pilot['integrated_fixtures']}
    rows=[];queue=[]
    for w in windows:
        slot=w['slot'];base=bases[slot]
        row=dict(issue=w['issue'],slot=slot,provider_id=w['provider_id'],
            competition_category=base['competition_category'] or 'UNKNOWN',
            history_mode=w['history_mode'],identity_source=w['identity_source'],
            adjudicated=bool(w['adjudication']),
            selected_nowscore_histories=sum(h['source']=='nowscore' for (s,_),h in selected.items() if s==slot))
        leagues={}
        for side in ('home','away'):
            evidence=[p for p in context['participation'] if p['slot']==slot and p['role']==side and p['competition_categories']==['LEAGUE']]
            leagues[side]={p['competition_id'] for p in evidence if p['competition_id'] is not None}
            row[side+'_league_evidence']=' / '.join(sorted({name for p in evidence for name in p['competition_names']})) or None
        row['league_relation']='UNKNOWN'
        if len(leagues['home'])==len(leagues['away'])==1:
            row['league_relation']='SAME_OBSERVED_LEAGUE' if leagues['home']==leagues['away'] else 'DIFFERENT_OBSERVED_LEAGUES'
        differences=[d for d in pilot['crosscheck_differences'] if d['slot']==slot and
                     (slot,d.get('history_id')) in selected]
        row['selected_history_crosschecks']=len({d['history_id'] for d in differences})
        errors=[o for o in report['observations'] if o['slot']==slot and o.get('error')]
        rows.append(row)
        for d in differences:
            queue.append(dict(issue=w['issue'],slot=slot,provider_id=w['provider_id'],kind='SELECTED_HISTORY_CROSSCHECK',evidence=d))
        for o in errors:
            queue.append(dict(issue=w['issue'],slot=slot,provider_id=w['provider_id'],kind='SOURCE_PARSER_ERROR',evidence=o))
    return dict(fixtures=rows,pending_queue=queue)
