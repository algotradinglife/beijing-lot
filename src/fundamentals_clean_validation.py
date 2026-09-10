"""Read approved cleaned releases and project fixed historical diagnostic inputs."""
import hashlib
import json
from pathlib import Path
from src.temporal_learning import Cutoff
from src.temporal_learning.core import utc
from src.temporal_learning.diagnostic_window import diagnostic_date_window, diagnostic_quote_window
from src.temporal_learning.partial_clock import diagnostic_monthday_quotes
from src.temporal_learning.predictor_clock import diagnostic_predictor_clock
from src.temporal_learning.provenance import implementation_closure
from src.fundamentals_home_away import home_away_windows
from src.fundamentals_draw_context import draw_form_summary


def read_clean_validation_release(study, *, cutoffs):
    """Read-only hash verification; return approved payloads/markets and receipt.

    cutoffs explicitly maps issue -> slot -> original timestamp. No outcome
    selection or model fitting. Missing/changed inputs or incomplete identities
    fail; raw release files remain unchanged. Source chronology stays proxy.
    """
    path=Path(study)/'cleanup-manifest.json';manifest=json.loads(path.read_text())
    if manifest['historical_admission'] is not False or manifest['source_policy']!='TITAN_PRIMARY_NOWSCORE_CROSSCHECK_FILL':
        raise ValueError('Expected Titan-primary diagnostic release')
    for name,h in manifest['files'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h:raise ValueError('Changed release input: '+name)
    payloads={};sources={}
    for name in manifest['analysis_paths']:
        payload=json.loads(Path(name).read_text());clean=payload['clean']
        issues={f['issue'] for f in payload['fixtures']}
        if len(issues)!=1:raise ValueError('One issue per payload required')
        issue=next(iter(issues))
        if issue in payloads or issue not in cutoffs or clean['cutoffs']!=cutoffs[issue]:raise ValueError('Release cutoff/issue mismatch')
        keys=[(f['slot'],f['provider_id']) for f in payload['fixtures']]
        if len(set(keys))!=len(keys) or {str(s) for s,p in keys}!=set(cutoffs[issue]):raise ValueError('Release fixture scope mismatch')
        if sorted(keys)!=sorted((f['slot'],f['provider_id']) for f in clean['integrated_fixtures']):raise ValueError('Integrated fixture identity mismatch')
        payloads[issue]=payload;sources[name]=manifest['files'][name]
    if set(payloads)!=set(cutoffs):raise ValueError('Missing declared release issues')
    sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    markets=json.loads(Path(manifest['market_path']).read_text())
    if len({(m['market'],m['provider_id']) for m in markets})!=len(markets):raise ValueError('Duplicate market identity')
    return dict(payloads=payloads,markets=markets,source_hashes=sources,manifest=manifest)


def clean_validation_forms(payload, handicaps, *, cutoffs, window, minimum, source_hashes, repository_root):
    """Pure fixed form projection of already adjudicated rows; no raw reparse.

    Uses shared date windows and authoritative orientation summaries. Returns
    windows plus sealed expert context. All slots persist, including failures.
    History dates remain diagnostic proxies, and unavailable identities remain
    unavailable. Explicit cutoff maps must equal the approved snapshot.
    """
    clean=payload['clean'];fixtures=payload['fixtures']
    if clean['cutoffs']!=cutoffs or not source_hashes:raise ValueError('Explicit source/cutoff binding required')
    if {(r['slot'],r['provider_id']) for r in handicaps}!={(f['slot'],f['provider_id']) for f in fixtures} or len(handicaps)!=len(fixtures):
        raise ValueError('Handicap fixture identity mismatch')
    if any(type(r['home_handicap']) not in (int,float) or int(r['home_handicap'])!=r['home_handicap'] for r in handicaps):raise ValueError('Integer handicap required')
    code=implementation_closure(Path(repository_root),['src.fundamentals_clean_validation'])['files']
    pilot=dict(clean,input_file_hashes=source_hashes,implementation_hashes=code)
    windows=home_away_windows(pilot,fixtures,cutoffs=cutoffs,window=window,minimum=minimum,repository_root=repository_root)
    rows=[];receipts=[];excluded={f['provider_id'] for f in fixtures};issue=fixtures[0]['issue']
    for f,v in zip(fixtures,windows):
        h=next(r['home_handicap'] for r in handicaps if r['slot']==f['slot'])
        base=next(r for r in clean['integrated_fixtures'] if r['slot']==f['slot'])
        cutoff=Cutoff.decision_epoch(issue,cutoffs[str(f['slot'])])
        row=dict(issue=issue,slot=f['slot'],provider_id=f['provider_id'],handicap=h,home_team_id=f['home_id'],away_team_id=f['away_id'],
                 competition_category=base['competition_category'],status=v['status'],venue_mode=v['history_mode'])
        ledger=dict(issue=issue,slot=f['slot'],provider_id=f['provider_id'],views={})
        for side in ['home','away']:
            tid=f[side+'_id'];candidates=[r for r in clean['integrated_history'] if r['slot']==f['slot'] and tid in (r['home_id'],r['away_id'])]
            overall=diagnostic_date_window(candidates,cutoff=cutoff,window=window,minimum=v['adjudication'].get('minimum',minimum),
                timezone='Asia/Shanghai',excluded_ids=excluded,source_hashes=source_hashes,implementation_hashes=code)
            venue=dict(rows=v[side+'_window'],receipt=v[side+'_receipt'])
            for name,selection in [('overall',overall),('venue',venue)]:
                summary=draw_form_summary(selection,team_id=tid,target_net=int(-h if side=='home' else h),cutoff=cutoff)
                row.update({side+'_'+name+'_'+k:z for k,z in summary.items()});ledger['views'][side+'_'+name]=selection
        rows.append(row);receipts.append(ledger)
    context=dict(rows=rows,receipts=receipts,cutoffs={issue:cutoffs},input_file_hashes=source_hashes,implementation_hashes=code,
                 window=window,minimum=minimum,historical_admission=False)
    encoded=json.dumps(context,ensure_ascii=True,separators=(',',':'),allow_nan=False)
    return dict(windows=windows,context=dict(context,canonical_json=encoded,seal=hashlib.sha256(encoded.encode()).hexdigest()))


def clean_validation_market(payload, markets, *, cutoffs, source_hashes, repository_root):
    """Select dated Euro/OU quotes from the approved parsing view, read-only.

    One status per roster slot; quarantined, missing or clock/identity mismatched
    pages remain excluded. Explicit approved fixture associations do not bypass
    quote clocks or known wrong-team quarantine. Returns selected company rows,
    mean decimal Euro odds, shared receipts and model predictor clocks.
    """
    clean=payload['clean']
    if clean['cutoffs']!=cutoffs or not source_hashes:raise ValueError('Explicit market cutoff/source binding required')
    index={(m['market'],m['provider_id']):m for m in markets}
    if len(index)!=len(markets):raise ValueError('Duplicate parsed market')
    code=implementation_closure(Path(repository_root),['src.fundamentals_clean_validation'])['files'];rows=[];selected=[];receipts=[]
    for f in clean['integrated_fixtures']:
        issue=f['issue'];slot=f['slot'];pid=f['provider_id'];cutoff=Cutoff.decision_epoch(issue,cutoffs[str(slot)])
        row=dict(issue=issue,slot=slot,provider_id=pid,status='MARKET_UNAVAILABLE',cutoff_utc=cutoffs[str(slot)])
        rows.append(row)
        e,t=index.get(('euro',pid)),index.get(('total',pid))
        if not e or not t:continue
        if e['status']!='PARSED' or t['status']!='PARSED':row['status']='PARSE_OR_QUARANTINE';continue
        if any(str(m.get('quote_identity_status','')).startswith('QUARANTINED') for m in [e,t]):row['status']='QUARANTINED_IDENTITY';continue
        ep,tp=e['parsed'],t['parsed']
        source=next((s for s in clean['source_fixtures'] if s['slot']==slot and s['source']=='titan'),None)
        if source is None or f['identity_source'] is None or f['kickoff_utc'] is None:row['status']='IDENTITY_UNAVAILABLE';continue
        approved=all(m.get('quote_identity_status')=='FIXTURE_ASSOCIATION_ONLY_QUOTES_NOT_INDEPENDENTLY_VERIFIED' and
                     m.get('adjudicated_fixture',{}).get('issue')==issue and m['adjudicated_fixture'].get('slot')==slot for m in [e,t])
        ids=all(str(source.get(side+'_id'))==ep[side+'_team_id']==tp[side+'_team_id'] for side in ['home','away'])
        if ep['provider_id']!=pid or tp['provider_id']!=pid or not (ids or approved):row['status']='TEAM_ID_MISMATCH';continue
        tk=utc(tp['kickoff_local'].replace(' ','T')+':00+08:00')
        if utc(ep['kickoff_utc'])!=utc(f['kickoff_utc']) or tk!=utc(f['kickoff_utc']):row['status']='CLOCK_MISMATCH';continue
        hashes={**source_hashes,e['path']:e['capture_sha256'],t['path']:t['capture_sha256']}
        euro=diagnostic_quote_window(ep['quotes'],cutoff=cutoff,source_hashes=hashes,implementation_hashes=code)
        try:
            total=diagnostic_monthday_quotes([q for q in tp['changes'] if q['phase']=='PREMATCH'],anchor_utc=ep['kickoff_utc'],
                timezone='Asia/Shanghai',maximum_days=31,cutoff=cutoff,source_hashes=hashes,implementation_hashes=code)
        except ValueError as exc:row.update(status='QUOTE_CLOCK_CONFLICT',detail=str(exc));continue
        if not euro['rows'] or not total['rows']:row['status']='NO_PRIOR_QUOTES';continue
        row.update(status='READY',euro_companies=len(euro['rows']),total_companies=len(total['rows']),
                   identity_evidence='APPROVED_ASSOCIATION' if not ids else 'NATIVE_IDS',capture_path=e['path'],capture_sha256=e['capture_sha256'])
        for k in ['odds_W','odds_D','odds_L']:row[k]=sum(q[k] for q in euro['rows'])/len(euro['rows'])
        selected.extend(dict(issue=issue,slot=slot,provider_id=pid,**q) for q in total['rows'])
        receipts.append(dict(issue=issue,slot=slot,provider_id=pid,euro=euro,total=total,source_hashes=hashes))
    return dict(rows=rows,selected=selected,receipts=receipts,cutoffs=cutoffs,implementation_hashes=code)


def validation_predictor_clocks(context, market, *, cutoffs):
    """Bind actual selected history dates and quote timestamps using shared clock.

    Return one diagnostic clock per market-ready, form-ready fixture. No invented
    availability, missing-clock fill, labels, I/O or learning. Keys/cutoffs fail closed.
    """
    clocks=[];by_slot={r['slot']:r for r in context['receipts']}
    if len(by_slot)!=len(context['receipts']):raise ValueError('Duplicate context fixture')
    for r in market['receipts']:
        ledger=by_slot[r['slot']]
        if (ledger['issue'],ledger['provider_id'])!=(r['issue'],r['provider_id']):raise ValueError('Predictor identity mismatch')
        dates=[h['event_date'] for v in ledger['views'].values() for h in v['rows']]
        if not dates:continue
        cutoff=Cutoff.decision_epoch(r['issue'],cutoffs[str(r['slot'])])
        q=r['euro']['rows']+r['total']['rows']
        clock=diagnostic_predictor_clock(dates,[x['quoted_at'] for x in q],cutoff=cutoff,timezone='Asia/Shanghai',source_hashes=r['source_hashes'])
        clocks.append(dict(issue=r['issue'],slot=r['slot'],provider_id=r['provider_id'],predictor_clock_ts=clock['receipt']['maximum_predictor_clock'],clock=clock))
    return clocks
