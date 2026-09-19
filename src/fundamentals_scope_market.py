"""Full-scope retrospective market audit; raw evidence and every exclusion retained."""
import hashlib
import json
from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from src.fundamentals_census import read_response, decode_analysis_text
from src.nowscore_settlement import parse_page
from src.fundamentals_titan_euro import parse_titan_euro
from src.fundamentals_titan_total import parse_titan_total_html
from src.fundamentals_euro_corroboration import corroborated_euro
from src.market_sqlite_capture import read_market_storage_receipt, read_market_storage_parsed, MarketNormalizationUnavailable
from src.fundamentals_exact_identity import exact_identity_match
from src.fundamentals_market_orientation import orient_market_view
from src.temporal_learning import Cutoff
from src.temporal_learning.roster_clock import roster_clock_alignment
from src.temporal_learning.partial_clock import diagnostic_monthday_quotes
from src.temporal_learning.diagnostic_window import diagnostic_quote_window
from src.temporal_learning.provenance import implementation_closure


def project_source_key(path, *, repository_root):
    """Return a portable repository-relative source key; outside paths fail."""
    return Path(path).resolve().relative_to(Path(repository_root).resolve()).as_posix()


def audit_fixture_market(fixture, parsed, *, market, cutoff, source_hashes,
                         implementation_hashes, decision=None):
    """Return diagnostic status, quotes and full clock/order ledger; no I/O.

    Fixture is an original Type 8 roster row; parsed is current Titan parser
    output. Explicit decision cutoff is mandatory. All timestamps use shared
    temporal machinery. Non-finished, identity/date failures select no quotes.
    """
    if market not in ('euro', 'total') or cutoff.target_issue != fixture['issue']:
        raise ValueError('Market/cutoff context mismatch')
    result = dict(issue=fixture['issue'], slot=fixture['slot'], market=market,
        provider_id=fixture['native_match_id'], original_status=fixture['status'],
        home=fixture['home'], away=fixture['away'], roster_ids=[fixture['home_id'],fixture['away_id']],
        cutoff_utc=cutoff.cutoff_ts.isoformat(), rows=[], prior_companies=0,
        historical_admission=False)
    if fixture['status'] != '完场':
        return dict(result, status='ORIGINAL_NOT_FINISHED')
    result['source_ids'] = [parsed['home_team_id'],parsed['away_team_id']]
    result['published_kickoff'] = parsed['kickoff_utc'] if market == 'euro' else parsed['kickoff_local']
    if decision is not None and decision.get('action') in ('REVERSE_MARKET_ORIENTATION','REVERSE_AND_HISTORICAL_ID'):
        orientation=orient_market_view(fixture,parsed,decision,market=market,cutoff=cutoff,source_hashes=source_hashes)
        parsed=orientation['parsed']
        result['orientation_adjudication']=orientation['receipt']
        result['effective_source_ids']=[parsed['home_team_id'],parsed['away_team_id']]
    identity = (fixture['native_match_id'],str(fixture['home_id']),str(fixture['away_id'])) == (
        parsed['provider_id'],parsed['home_team_id'],parsed['away_team_id'])
    if not identity:
        if decision is None:
            return dict(result, status='IDENTITY_MISMATCH')
        if parsed['home_team_id']==str(fixture['away_id']) or parsed['away_team_id']==str(fixture['home_id']):
            raise ValueError('Reverse sides require explicit orientation correction')
        result['identity_adjudication'] = exact_identity_match(fixture,parsed,decision,market=market,cutoff=cutoff)
    if decision is not None and decision.get('action') in ('CORRECT_EURO_EVENT_HEADER','CORRECT_TOTAL_EVENT_HEADER'):
        if decision['action'] != {'euro':'CORRECT_EURO_EVENT_HEADER','total':'CORRECT_TOTAL_EVENT_HEADER'}[market] or not identity:
            raise ValueError('Event date adjudication requires exact Euro identity')
        exact_identity_match(fixture,parsed,decision,market=market,cutoff=cutoff)
        evidence=[decision.get(k) for k in ('roster_path','capture_path','independent_evidence_path','second_independent_path')]
        if len(set(evidence))!=4 or any(not isinstance(k,str) or k not in decision.get('files',{}) or source_hashes.get(k)!=decision['files'][k] for k in evidence):
            raise ValueError('Event date adjudication requires two bound independent sources')
        original=parsed['kickoff_utc'] if market=='euro' else datetime.fromisoformat(parsed['kickoff_local']).replace(tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc).isoformat()
        corrected=decision['corrected_kickoff_utc']
        if original!=decision['original_kickoff_utc'] or original==corrected:
            raise ValueError('Event date source header mismatch')
        checked=roster_clock_alignment(dict(fixture,deadline_text=fixture['cutoff_text'],clock=fixture['kickoff_time']),
            {market:corrected},cutoff=cutoff,timezone='Asia/Shanghai',midnight_hours=12)
        if checked['status']!='ALIGNED' or corrected!=checked['canonical_kickoff_utc']:
            raise ValueError('Corrected event header must equal original roster clock')
        before=hashlib.sha256(json.dumps(parsed,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        parsed=deepcopy(parsed)
        if market=='euro':
            parsed['kickoff_utc']=corrected
        else:
            parsed['kickoff_local']=datetime.fromisoformat(corrected).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')
        result['event_date_adjudication']=dict(adjudication_id=decision['adjudication_id'],
            original_kickoff_utc=original,corrected_kickoff_utc=corrected,
            original_parsed_sha256=before,
            adjusted_parsed_sha256=hashlib.sha256(json.dumps(parsed,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
            source_hashes=decision['files'],cutoff_utc=cutoff.cutoff_ts.isoformat(),
            quote_timestamps_changed=False,historical_admission=False)
    kickoff = parsed['kickoff_utc'] if market == 'euro' else parsed['kickoff_local'].replace(' ','T')+':00+08:00'
    alignment = roster_clock_alignment(dict(fixture,deadline_text=fixture['cutoff_text'],clock=fixture['kickoff_time']),
        {market:kickoff},cutoff=cutoff,timezone='Asia/Shanghai',midnight_hours=12)
    result['alignment'] = alignment
    if alignment['status'] != 'ALIGNED':
        return dict(result,status=alignment['status'])
    if market == 'euro':
        window = diagnostic_quote_window(parsed['quotes'],cutoff=cutoff,
            source_hashes=source_hashes,implementation_hashes=implementation_hashes)
        result['observed_quotes'] = len(parsed['quotes'])
    else:
        changes = parsed['changes']
        result['phase_counts'] = dict(Counter(q['phase'] for q in changes))
        result['observed_quotes'] = len(changes)
        window = diagnostic_monthday_quotes([q for q in changes if q['phase']=='PREMATCH'],
            anchor_utc=alignment['canonical_kickoff_utc'],timezone='Asia/Shanghai',maximum_days=31,
            cutoff=cutoff,source_hashes=source_hashes,implementation_hashes=implementation_hashes)
    return dict(result,window=window,rows=window['rows'],prior_companies=len(window['rows']),
        status='QUOTES_PRIOR_DIAGNOSTIC' if window['rows'] else 'NO_PRIOR_QUOTES')


def run_scope_market_audit(scope_path, audit_path, followup_path, recovery_path,
                           decisions_path, output_path, *, repository_root, data_root, input_manifest_path):
    """Replay every scoped fixture/market into per-issue JSON and a summary.

    Data paths are relative to data_root; repository_root supplies code identity.
    Refuses existing output; verifies saved transport bodies
    and manifest hashes. Fetches nothing and writes only output_path. Parser
    failures are explicit per response; corrupted evidence fails the entire run.
    Current parsers run once per provider/market, never trusting cached parsed
    content. No prospective availability or model fitting is claimed.
    """
    root = Path(data_root).resolve(strict=True)
    out = root / output_path
    project_source_key(out, repository_root=root)
    if out.exists():
        raise ValueError('Output already exists')
    inputs = [root/p for p in (scope_path,audit_path,followup_path,recovery_path,decisions_path)]
    manifest_path=root/input_manifest_path
    manifest=json.loads(manifest_path.read_text())
    labels=('scope','audit','followup','recovery','decisions')
    if set(manifest['outputs'])!=set(labels) or set(manifest['source_inputs'])!=set(labels):
        raise ValueError('Portable input labels mismatch')
    for label,path in zip(labels,inputs):
        entry=manifest['outputs'][label]
        if (root/entry['path']).resolve()!=path.resolve() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Portable input manifest mismatch')
    scope, audit, followup, recovery, decisions = [json.loads(p.read_text()) for p in inputs]
    hashes = {project_source_key(p,repository_root=root):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    hashes[project_source_key(manifest_path,repository_root=root)]=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    for entry in manifest['source_inputs'].values():
        path=root/entry['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Pre-conversion input changed')
        hashes[project_source_key(path,repository_root=root)]=entry['sha256']
    closure = implementation_closure(Path(repository_root).resolve(strict=True),('src.fundamentals_scope_market',))['files']
    issues = scope['issues']
    inventory_issues = [i['issue'] for i in scope['inventories']]
    fixture_keys = [(f['issue'],f['slot']) for f in scope['fixtures']]
    if (not issues or len(issues)!=len(set(issues)) or inventory_issues!=issues
            or len(fixture_keys)!=len(set(fixture_keys))
            or {f['issue'] for f in scope['fixtures']}!=set(issues)):
        raise ValueError('Invalid issue/fixture scope')
    bound_scope = {(root/name).resolve():digest for name,digest in scope['source_hashes'].items()}
    if not bound_scope:
        raise ValueError('Unbound scope sources')
    stored_sources={(root/r['path']).resolve():r for r in audit if 'storage' in r}
    for path,digest in bound_scope.items():
        if path in stored_sources:
            item=stored_sources[path]
            if digest!=item['capture_sha256']:
                raise ValueError('Stored scope source hash mismatch')
            reference=item['storage']
            read_market_storage_receipt(reference,expected_sha256=digest,expected_url=reference['source_url'])
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Scope evidence changed')
        hashes[project_source_key(path,repository_root=root)]=digest
    for inventory in scope['inventories']:
        if (root/inventory['roster_path']).resolve() not in bound_scope:
            raise ValueError('Unbound original roster')
        fs=[f for f in scope['fixtures'] if f['issue']==inventory['issue']]
        if len(fs)!=inventory['fixture_count']:
            raise ValueError('Inventory fixture count mismatch')
        if {str(f['slot']):f['decision_ts'] for f in fs}!=inventory['cutoffs']:
            raise ValueError('Inventory cutoff mismatch')
    # Provider IDs are native event identifiers, not globally unique fixture
    # keys: the same event can legitimately be present in more than one
    # historical issue.  Keep issue in the audit key so a repeated ID cannot
    # overwrite a different issue's evidence.
    indexed_audit = []
    for r in audit:
        # Legacy single-issue callers did not repeat the issue in each market
        # row.  Infer it only when the frozen scope has exactly one issue;
        # multi-issue batches must bind the issue explicitly.
        audit_issue = r.get('issue')
        if audit_issue is None:
            if len(issues) != 1:
                raise ValueError('Multi-issue market capture requires issue key')
            audit_issue = issues[0]
        indexed_audit.append((audit_issue, r))
    index = {(issue, r['market'], r['provider_id']):{k:v for k,v in r.items() if k!='parsed'}
             for issue, r in indexed_audit}
    audit_count=len(audit)
    del audit
    if len(index)!=audit_count:
        raise ValueError('Duplicate market capture')
    expected = {(f['issue'],m,f['provider_id']) for f in scope['fixtures'] for m in ('euro','total')}
    expected_provider_markets = {(m,f['provider_id']) for f in scope['fixtures'] for m in ('euro','total')}
    if set(index)!=expected:
        raise ValueError('Market scope mismatch')
    peers = {r['provider_id']:r['path'] for r in followup['nowscore_comparison']}
    replacements = {('total',r['filename'].removeprefix('total-').removesuffix('.json')):r['path']
                    for r in followup['retries'] if r['parsed'] and r['filename'].startswith('total-')}
    replacements.update({('total',str(d['capture_path']).split('total-')[-1].removesuffix('.json')):d['capture_path'] for d in recovery})
    approved = {(d['issue'],d['slot'],d['market']):d for d in decisions}
    if len(approved)!=len(decisions):
        raise ValueError('Duplicate identity decision')
    if (not set(replacements)<=expected_provider_markets
            or not {('euro',p) for p in peers}<=expected_provider_markets
            or not set(approved)<={(f['issue'],f['slot'],m) for f in scope['fixtures'] for m in ('euro','total')}):
        raise ValueError('Followup evidence outside scope')
    for d in decisions:
        required = [d['capture_path'],d['roster_path']]
        if d.get('action') in ('REVERSE_MARKET_ORIENTATION','REVERSE_AND_HISTORICAL_ID') or 'independent_evidence_path' in d:
            required.append(d['independent_evidence_path'])
        if 'peer_path' in d:
            required.append(d['peer_path'])
        if any(p not in d['files'] for p in required):
            raise ValueError('Unbound decision input')
        for name,digest in d['files'].items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
                raise ValueError('Decision evidence changed')
            hashes[project_source_key(root/name,repository_root=root)]=digest
    out.mkdir(parents=True)
    parsed_cache, response_meta, issue_summary, all_rows, output_hashes = {}, {}, [], [], {}
    for inventory in scope['inventories']:
        issue=inventory['issue']
        rp=root/inventory['roster_path']
        rm,raw=read_response(rp)
        u=urlsplit(rm['url']); query=parse_qs(u.query)
        if (rm['status']!=200 or rm['url']!=rm['final_url'] or u.scheme!='https'
                or u.netloc!='cp.nowscore.com' or u.path!='/buy/DanChang.aspx'
                or query.get('issueNum')!=[issue] or query.get('TypeID')!=['8']):
            raise ValueError('Roster source mismatch')
        roster=parse_page(raw,issue,8)
        by_slot={}
        for f in roster:
            by_slot.setdefault(f['slot'],[]).append(f)
        fixtures=[f for f in scope['fixtures'] if f['issue']==issue]
        declared = {(f['slot'],f['provider_id']) for f in fixtures}
        excluded = {(f['slot'],f['provider_id']) for f in inventory['identity_exclusions']}
        original = {(f['slot'],f['native_match_id']) for f in roster}
        if (declared & excluded or declared | excluded != original
                or len(roster)!=inventory['original_fixture_count'] or len(original)!=len(roster)):
            raise ValueError('Original roster coverage mismatch')
        roster_hash=hashlib.sha256(rp.read_bytes()).hexdigest()
        hashes[project_source_key(rp,repository_root=root)]=roster_hash
        rows=[]
        for sf in fixtures:
            matches=by_slot.get(sf['slot'],[])
            if len(matches)!=1 or matches[0]['native_match_id']!=sf['provider_id']:
                raise ValueError('Original roster scope mismatch')
            f=matches[0]; cutoff=Cutoff.decision_epoch(issue,sf['decision_ts'])
            for market in ('euro','total'):
                key=(issue,market,sf['provider_id']); original=index[key]
                replacement_key=(market,sf['provider_id'])
                path=root/replacements.get(replacement_key,original['path'])
                if key not in parsed_cache:
                    op=root/original['path']
                    storage=original.get('storage')
                    if storage is not None:
                        if path!=op or (market=='euro' and sf['provider_id'] in peers):
                            raise ValueError('Structured replacement/peer requires an explicit stored evidence binding')
                        local_hashes={project_source_key(op,repository_root=root):original['capture_sha256']}
                        acceptance=storage['acceptance']
                        local_hashes[project_source_key(acceptance['path'],repository_root=root)]=acceptance['sha256']
                        # Validate integrity outside classification: corruption is fatal.
                        read_market_storage_receipt(storage,expected_sha256=original['capture_sha256'],expected_url=storage['source_url'])
                        try:
                            meta,parsed=read_market_storage_parsed(storage,expected_sha256=original['capture_sha256'],expected_url=storage['source_url'])
                            source=meta['url'].removeprefix('https://r.jina.ai/')
                            u=urlsplit(source)
                            valid=(u.netloc=='1x2d.titan007.com' and u.path=='/'+sf['provider_id']+'.js') if market=='euro' else (
                                u.netloc=='vip.titan007.com' and u.path=='/OverDown_n.aspx' and parse_qs(u.query).get('id')==[sf['provider_id']] and parse_qs(u.query).get('l')==['0'])
                            if not valid or u.scheme!='https' or meta['url']!=meta['final_url']:
                                raise MarketNormalizationUnavailable('SOURCE_URL_MISMATCH')
                            parsed_cache[key]=(parsed,None)
                        except MarketNormalizationUnavailable as exc:
                            parsed_cache[key]=(None,type(exc).__name__+': '+str(exc))
                    else:
                        if hashlib.sha256(op.read_bytes()).hexdigest()!=original['capture_sha256']:
                            raise ValueError('Original market evidence changed')
                        local_hashes={project_source_key(op,repository_root=root):original['capture_sha256'],project_source_key(path,repository_root=root):hashlib.sha256(path.read_bytes()).hexdigest()}
                        # Transport receipts have no response body; hash-bound original
                        # audit classifies them. Any actual response corruption is fatal.
                        transport_only = original['status']=='TRANSPORT_FAILURE' and path==op
                        meta,body = (None,None) if transport_only else read_response(path)
                        peer=root/peers[sf['provider_id']] if market=='euro' and sf['provider_id'] in peers else None
                        if peer is not None:
                            read_response(peer)
                            local_hashes[project_source_key(peer,repository_root=root)]=hashlib.sha256(peer.read_bytes()).hexdigest()
                        try:
                            if transport_only:
                                raise ValueError('TRANSPORT_FAILURE')
                            if meta['status']!=200:
                                raise ValueError('HTTP_'+str(meta['status']))
                            source=meta['url'].removeprefix('https://r.jina.ai/')
                            u=urlsplit(source)
                            valid=(u.netloc=='1x2d.titan007.com' and u.path=='/'+sf['provider_id']+'.js') if market=='euro' else (
                                u.netloc=='vip.titan007.com' and u.path=='/OverDown_n.aspx' and parse_qs(u.query).get('id')==[sf['provider_id']] and parse_qs(u.query).get('l')==['0'])
                            if not valid or u.scheme!='https' or meta['url']!=meta['final_url']:
                                raise ValueError('SOURCE_URL_MISMATCH')
                            if peer is not None:
                                parsed=corroborated_euro(path,peer)['parsed']
                            else:
                                parsed=parse_titan_euro(decode_analysis_text(body)[0]) if market=='euro' else parse_titan_total_html(body.decode('utf-8'))
                            parsed_cache[key]=(parsed,None)
                        except (ValueError,KeyError,UnicodeError) as exc:
                            parsed_cache[key]=(None,type(exc).__name__+': '+str(exc))
                    response_meta[key]=dict(capture_path=project_source_key(path,repository_root=root),source_hashes=local_hashes)
                    hashes.update(local_hashes)
                parsed,error=parsed_cache[key]
                rh=dict(response_meta[key]['source_hashes'],**{project_source_key(rp,repository_root=root):roster_hash})
                base=dict(issue=issue,slot=f['slot'],market=market,provider_id=f['native_match_id'],
                    home=f['home'],away=f['away'],original_status=f['status'],cutoff_utc=cutoff.cutoff_ts.isoformat(),
                    capture_path=project_source_key(path,repository_root=root),source_hashes=rh,rows=[],prior_companies=0,historical_admission=False)
                if error:
                    result=dict(base,status='ORIGINAL_NOT_FINISHED' if f['status']!='完场' else 'RESPONSE_UNAVAILABLE',error=error)
                else:
                    decision=approved.get((issue,f['slot'],market))
                    if decision is not None:
                        if ((root/decision['capture_path']).resolve()!=path.resolve()
                                or (root/decision['roster_path']).resolve()!=rp.resolve()):
                            raise ValueError('Decision capture/roster mismatch')
                        rh.update({project_source_key(root/name,repository_root=root):digest for name,digest in decision['files'].items()})
                    try:
                        result=audit_fixture_market(f,parsed,market=market,cutoff=cutoff,source_hashes=rh,
                            implementation_hashes=closure,decision=decision)
                        result.update(capture_path=project_source_key(path,repository_root=root),source_hashes=rh)
                    except (ValueError,KeyError) as exc:
                        result=dict(base,status='SEMANTIC_ERROR',error=type(exc).__name__+': '+str(exc))
                if original.get('storage') is not None:
                    # Preserve the verified binding for downstream migration after
                    # the historical capture_path has been retired.
                    result['storage']=original['storage']
                rows.append(result)
        issue_path=out/(issue+'.json')
        issue_path.write_text(json.dumps(rows,ensure_ascii=False,allow_nan=False))
        output_hashes[issue_path.name]=hashlib.sha256(issue_path.read_bytes()).hexdigest()
        compact=[{k:v for k,v in r.items() if k not in ('rows','window','source_hashes')} for r in rows]
        all_rows.extend(compact)
        counts=dict(Counter(r['status'] for r in rows))
        issue_summary.append(dict(issue=issue,fixture_count=len(fixtures),response_count=len(rows),counts=counts))
        print(json.dumps(issue_summary[-1],ensure_ascii=False),flush=True)
    summary=dict(issues=issue_summary,rows=all_rows,
        fixture_count=len(scope['fixtures']),unique_market_responses=len(index),
        fixture_market_rows=len(all_rows),counts=dict(Counter(r['status'] for r in all_rows)),
        source_hashes=hashes,output_hashes=output_hashes,implementation_hashes=closure,generated_at=datetime.now(timezone.utc).isoformat(),
        source_policy='TITAN_PRIMARY_NOWSCORE_CROSSCHECK_FILL',
        parameters=dict(timezone='Asia/Shanghai',midnight_hours=12,maximum_days=31,
            quote_cutoff='STRICTLY_PRIOR',total_selection='LATEST_PRIOR_PER_COMPANY',
            availability='HISTORICAL_PROXY'),
        historical_admission=False,scope_exclusions=[dict(issue=i['issue'],rows=i['identity_exclusions']) for i in scope['inventories'] if i['identity_exclusions']])
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,allow_nan=False))
    return summary
