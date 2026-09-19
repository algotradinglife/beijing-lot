import copy
import hashlib
import json
from pathlib import Path
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_scope_market import audit_fixture_market, run_scope_market_audit, project_source_key


@pytest.mark.parametrize('market', ['euro','total'])
def test_fixture_market_contracts(market):
    f=dict(issue='100909',slot=26,native_match_id='374124',home_id='1',away_id='2',
        home='H',away='A',status='完场',cutoff_text='截止时间：2010-09-18 02:30',kickoff_time='02:45')
    p=dict(provider_id='374124',home_team_id='1',away_team_id='2',
        kickoff_utc='2010-09-17T18:45:00Z',kickoff_local='2010-09-18 02:45',
        quotes=[dict(quote_id='1',company='A',quoted_at='2010-09-17T18:29:00Z'),
                dict(quote_id='2',company='B',quoted_at='2010-09-17T18:30:00Z')],
        changes=[dict(quote_id='10/A',company='A',quoted_local='9-18 02:29',phase='PREMATCH',line=2.5),
                 dict(quote_id='3/A',company='A',quoted_local='9-18 02:29',phase='PREMATCH',line=3),
                 dict(quote_id='2/B',company='B',quoted_local='9-18 02:30',phase='PREMATCH',line=2.5),
                 dict(quote_id='1/C',company='C',quoted_local='9-18 02:28',phase='LIVE',line=2.5)])
    args=dict(market=market,cutoff=Cutoff.decision_epoch('100909','2010-09-17T18:30:00Z'),
        source_hashes={'raw':'h'},implementation_hashes={'code':'h'})
    before=copy.deepcopy(p)
    r=audit_fixture_market(f,p,**args)
    assert r['status']=='QUOTES_PRIOR_DIAGNOSTIC' and r['prior_companies']==1
    assert r==audit_fixture_market(f,p,**args) and p==before
    if market=='total':
        assert r['rows'][0]['quote_id']=='3/A'
        assert len(r['window']['policy']['tie_ledger'])==1
    assert audit_fixture_market(dict(f,status='取消'),p,**args)['status']=='ORIGINAL_NOT_FINISHED'
    assert audit_fixture_market(dict(f,away_id='3'),p,**args)['status']=='IDENTITY_MISMATCH'
    later=dict(p,kickoff_local='2010-09-20 02:45',kickoff_utc='2010-09-19T18:45:00Z')
    assert audit_fixture_market(f,later,**args)['status']=='DAY_MISMATCH'
    empty=dict(p,quotes=[],changes=[])
    assert audit_fixture_market(f,empty,**args)['status']=='NO_PRIOR_QUOTES'
    bad=dict(args,cutoff=Cutoff.decision_epoch('100910','2010-09-17T18:30:00Z'))
    with pytest.raises(ValueError,match='context'): audit_fixture_market(f,p,**bad)


def test_scope_runner_replays_and_validates(tmp_path,monkeypatch):
    import src.fundamentals_scope_market as m
    fixture=dict(issue='100909',slot=26,native_match_id='374124',home_id='1',away_id='2',
        home='H',away='A',status='完场',cutoff_text='截止时间：2010-09-18 02:30',kickoff_time='02:45')
    names=['scope','audit','followup','recovery','decisions']
    paths=[tmp_path/n for n in names]
    for n in ('roster','euro','total'): (tmp_path/n).write_text('raw')
    digest=hashlib.sha256(b'raw').hexdigest()
    objects=[
        dict(issues=['100909'],source_hashes={'roster':digest},fixtures=[dict(issue='100909',slot=26,provider_id='374124',decision_ts='2010-09-17T18:30:00Z')],
             inventories=[dict(issue='100909',roster_path='roster',identity_exclusions=[],fixture_count=1,original_fixture_count=1,cutoffs={'26':'2010-09-17T18:30:00Z'})]),
        [dict(market=m,provider_id='374124',path=m,capture_sha256=digest,status='PARSED') for m in ('euro','total')],
        dict(retries=[],nowscore_comparison=[]),[],[]]
    for p,v in zip(paths,objects):p.write_text(json.dumps(v))
    manifest_path=tmp_path/'manifest'
    def refresh_manifest():
        entries={n:dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n,p in zip(names,paths)}
        manifest_path.write_text(json.dumps(dict(outputs=entries,source_inputs=entries)))
    refresh_manifest()
    code_root=tmp_path/'separate-code-root'
    code_root.mkdir()
    runner_args=dict(repository_root=code_root,data_root=tmp_path,input_manifest_path=manifest_path)
    urls=dict(roster='https://cp.nowscore.com/buy/DanChang.aspx?TypeID=8&issueNum=100909',
        euro='https://1x2d.titan007.com/374124.js',
        total='https://vip.titan007.com/OverDown_n.aspx?id=374124&l=0')
    monkeypatch.setattr(m,'read_response',lambda p: (dict(status=200,url=urls[p.name],final_url=urls[p.name]),b'raw'))
    monkeypatch.setattr(m,'parse_page',lambda *args:[fixture])
    monkeypatch.setattr(m,'decode_analysis_text',lambda raw:('raw','utf-8'))
    closure_calls=[]
    monkeypatch.setattr(m,'implementation_closure',lambda root, modules: (closure_calls.append(root) or dict(files={'code':'hash'})))
    parsed=dict(provider_id='374124',home_team_id='1',away_team_id='2',
        kickoff_utc='2010-09-17T18:45:00Z',kickoff_local='2010-09-18 02:45',quotes=[],changes=[])
    monkeypatch.setattr(m,'parse_titan_euro',lambda text:parsed)
    monkeypatch.setattr(m,'parse_titan_total_html',lambda text:parsed)
    r=run_scope_market_audit(*paths,tmp_path/'output',**runner_args)
    assert r['counts']=={'NO_PRIOR_QUOTES':2}
    assert closure_calls==[code_root]
    assert not list(code_root.iterdir())
    with pytest.raises(ValueError):
        run_scope_market_audit(*paths,tmp_path.parent/'outside-data-root',**runner_args)
    assert not (tmp_path.parent/'outside-data-root').exists()
    assert json.loads((tmp_path/'output/100909.json').read_text())[0]['source_hashes']
    with pytest.raises(ValueError,match='already exists'):
        run_scope_market_audit(*paths,tmp_path/'output',**runner_args)
    original_scope=paths[0].read_bytes()
    paths[0].write_text('{}')
    with pytest.raises(ValueError,match='Portable input manifest mismatch'):
        run_scope_market_audit(*paths,tmp_path/'changed-normalized',**runner_args)
    paths[0].write_bytes(original_scope)
    ledger=json.loads(manifest_path.read_text())
    origin=tmp_path/'origin';origin.write_bytes(original_scope)
    ledger['source_inputs']['scope']=dict(path='origin',sha256=hashlib.sha256(original_scope).hexdigest())
    manifest_path.write_text(json.dumps(ledger));origin.write_text('changed original')
    with pytest.raises(ValueError,match='Pre-conversion input changed'):
        run_scope_market_audit(*paths,tmp_path/'changed-origin',**runner_args)
    refresh_manifest()
    assert len(r['output_hashes'])==1
    assert 'roster' in r['source_hashes']
    assert 'total' in r['source_hashes']
    relative=run_scope_market_audit(*[p.name for p in paths],'relative-output',**runner_args)
    assert relative['counts']==r['counts']
    for field,value in [('scheme',urls['total'].replace('https:','http:')),
                        ('query',urls['total'].replace('l=0','l=1'))]:
        old=urls['total'];urls['total']=value
        bad=run_scope_market_audit(*paths,tmp_path/field,**runner_args)
        assert bad['counts']['RESPONSE_UNAVAILABLE']==1
        urls['total']=old
    old=urls['roster'];urls['roster']=old.replace('/buy/DanChang.aspx','/wrong')
    with pytest.raises(ValueError,match='Roster source'):
        run_scope_market_audit(*paths,tmp_path/'bad-roster',**runner_args)
    urls['roster']=old
    (tmp_path/'roster').write_text('changed')
    with pytest.raises(ValueError,match='Scope evidence changed'):
        run_scope_market_audit(*paths,tmp_path/'bad-scope-hash',**runner_args)
    (tmp_path/'roster').write_text('raw')
    objects[0]['issues'].append('100910');paths[0].write_text(json.dumps(objects[0]));refresh_manifest()
    with pytest.raises(ValueError,match='issue/fixture'):
        run_scope_market_audit(*paths,tmp_path/'missing-issue',**runner_args)
    objects[0]['issues'].pop();paths[0].write_text(json.dumps(objects[0]));refresh_manifest()
    old_read=m.read_response
    def corrupt(path):
        if path.name=='euro': raise ValueError('response SHA-256 mismatch')
        return old_read(path)
    monkeypatch.setattr(m,'read_response',corrupt)
    with pytest.raises(ValueError,match='SHA-256 mismatch'):
        run_scope_market_audit(*paths,tmp_path/'corrupt-response',**runner_args)
    monkeypatch.setattr(m,'read_response',old_read)
    (tmp_path/'peer').write_text('raw')
    objects[2]['nowscore_comparison']=[{'provider_id':'374124','path':'peer'}]
    paths[2].write_text(json.dumps(objects[2]));refresh_manifest()
    def corrupt_peer(path):
        if path.name=='peer':raise ValueError('response SHA-256 mismatch')
        return old_read(path)
    monkeypatch.setattr(m,'read_response',corrupt_peer)
    with pytest.raises(ValueError,match='SHA-256 mismatch'):
        run_scope_market_audit(*paths,tmp_path/'corrupt-peer',**runner_args)
    monkeypatch.setattr(m,'read_response',old_read)
    objects[2]['nowscore_comparison']=[];paths[2].write_text(json.dumps(objects[2]));refresh_manifest()
    objects[1][0]['status']='TRANSPORT_FAILURE';paths[1].write_text(json.dumps(objects[1]));refresh_manifest()
    transport=run_scope_market_audit(*paths,tmp_path/'transport',**runner_args)
    assert transport['rows'][0]['error']=='ValueError: TRANSPORT_FAILURE'
    objects[1][0]['status']='PARSED';paths[1].write_text(json.dumps(objects[1]));refresh_manifest()
    objects[2]['nowscore_comparison']=[{'provider_id':'outside','path':'ignored'}]
    paths[2].write_text(json.dumps(objects[2]));refresh_manifest()
    with pytest.raises(ValueError,match='outside scope'):
        run_scope_market_audit(*paths,tmp_path/'outside',**runner_args)
    objects[2]['nowscore_comparison']=[];paths[2].write_text(json.dumps(objects[2]));refresh_manifest()
    # Explicit storage bindings must work after the original bodies are removed.
    acceptance=tmp_path/'storage-acceptance.json';acceptance.write_text('{}')
    for item in objects[1]:
        item['storage']=dict(source_url=urls[item['market']],acceptance=dict(
            path=str(acceptance),sha256=hashlib.sha256(acceptance.read_bytes()).hexdigest()))
        (tmp_path/item['path']).unlink()
        objects[0]['source_hashes'][item['path']]=digest
    monkeypatch.setattr(m,'read_market_storage_receipt',lambda ref,**kwargs:
                        dict(status=200,url=ref['source_url'],final_url=ref['source_url']))
    monkeypatch.setattr(m,'read_market_storage_parsed',lambda ref,**kwargs:
                        (dict(status=200,url=ref['source_url'],final_url=ref['source_url']),parsed))
    paths[0].write_text(json.dumps(objects[0]));paths[1].write_text(json.dumps(objects[1]));refresh_manifest()
    stored=run_scope_market_audit(*paths,tmp_path/'stored-source',**runner_args)
    assert stored['counts']==r['counts']
    persisted=json.loads((tmp_path/'stored-source'/'100909.json').read_text())
    assert all(row['storage']==next(item['storage'] for item in objects[1]
                                   if item['market']==row['market']) for row in persisted)
    assert not (tmp_path/'euro').exists() and not (tmp_path/'total').exists()
    def corrupt_stored_evidence(*args,**kwargs):
        raise ValueError('stored market record hash mismatch')
    monkeypatch.setattr(m,'read_market_storage_parsed',corrupt_stored_evidence)
    with pytest.raises(ValueError,match='record hash mismatch'):
        run_scope_market_audit(*paths,tmp_path/'corrupt-stored',**runner_args)
    for item in objects[1]:
        item.pop('storage');(tmp_path/item['path']).write_text('raw')
    objects[0]['source_hashes']={'roster':digest}
    paths[0].write_text(json.dumps(objects[0]));paths[1].write_text(json.dumps(objects[1]));refresh_manifest()
    (tmp_path/'euro').write_text('mutation')
    with pytest.raises(ValueError,match='evidence changed'):
        run_scope_market_audit(*paths,tmp_path/'changed',**runner_args)
    objects[1].append(objects[1][0]);paths[1].write_text(json.dumps(objects[1]));refresh_manifest()
    with pytest.raises(ValueError,match='Duplicate'):
        run_scope_market_audit(*paths,tmp_path/'duplicate',**runner_args)


def test_portable_project_source_key(tmp_path):
    assert project_source_key(tmp_path/'data/raw.json',repository_root=tmp_path)=='data/raw.json'
    with pytest.raises(ValueError):
        project_source_key(tmp_path.parent/'outside',repository_root=tmp_path)


@pytest.mark.parametrize('market',['euro','total'])
def test_scope_orientation_is_explicit_and_precedes_quote_window(market):
    f=dict(issue='100609',slot=2,native_match_id='355292',home_id='649',away_id='803',
        home='France',away='South Africa',status='完场',
        cutoff_text='截止时间：2010-06-22 21:45',kickoff_time='22:00')
    p=dict(provider_id='355292',home_team_id='803',away_team_id='649',
        kickoff_utc='2010-06-22T14:00:00Z',kickoff_local='2010-06-22 22:00',
        quotes=[dict(quote_id='1',company='A',odds_W=4.5,odds_D=3.5,odds_L=1.8,quoted_at='2010-06-22T13:30:00Z')],
        overview=[dict(line=2.5,over_hk=.9,under_hk=.95)],
        changes=[dict(quote_id='1/A',company='A',phase='PREMATCH',quoted_local='6-22 21:30',line=2.5,over_hk=.9,under_hk=.95)])
    hashes={'roster.json':'a'*64,'market.json':'b'*64,'independent.json':'c'*64}
    cutoff=Cutoff.decision_epoch('100609','2010-06-22T13:45:00Z')
    d=dict(approved=True,action='REVERSE_MARKET_ORIENTATION',adjudication_id='EXACT-TEST',
        issue=f['issue'],slot=f['slot'],provider_id=f['native_match_id'],market=market,
        roster_ids=['649','803'],source_ids=['803','649'],cutoff_utc=cutoff.cutoff_ts.isoformat(),
        roster_path='roster.json',capture_path='market.json',independent_evidence_path='independent.json',files=hashes)
    args=dict(market=market,cutoff=cutoff,source_hashes=hashes,implementation_hashes={'code':'h'})
    assert audit_fixture_market(f,p,**args)['status']=='IDENTITY_MISMATCH'
    with pytest.raises(ValueError,match='Reverse sides'):
        audit_fixture_market(f,p,decision={k:v for k,v in d.items() if k!='action'},**args)
    r=audit_fixture_market(f,p,decision=d,**args)
    assert r['status']=='QUOTES_PRIOR_DIAGNOSTIC'
    assert r['source_ids']==['803','649'] and r['effective_source_ids']==['649','803']
    assert r['orientation_adjudication']['original_preserved'] is True
    assert p['home_team_id']=='803' and p['quotes'][0]['odds_W']==4.5
    if market=='euro':assert r['rows'][0]['odds_W']==1.8
    else:assert r['rows'][0]['over_hk']==.9 and r['rows'][0]['under_hk']==.95


@pytest.mark.parametrize('market',['euro','total'])
def test_compound_orientation_retains_intermediate_identity(market):
    f=dict(issue='101106',slot=23,native_match_id='444',home_id='1',away_id='2',
        home='A',away='B',status='完场',cutoff_text='截止时间：2010-11-06 21:45',kickoff_time='22:00')
    p=dict(provider_id='444',home_team_id='20',away_team_id='1',
        kickoff_utc='2010-11-06T14:00:00Z',kickoff_local='2010-11-06 22:00',
        quotes=[dict(quote_id='1',company='A',odds_W=4.,odds_D=3.,odds_L=2.,quoted_at='2010-11-06T13:30:00Z')],
        overview=[],changes=[dict(quote_id='1/A',company='A',phase='PREMATCH',quoted_local='11-6 21:30',line=2.5,over_hk=.9,under_hk=1.)])
    cutoff=Cutoff.decision_epoch('101106','2010-11-06T13:45:00Z')
    hashes={'roster':'a'*64,'market':'b'*64,'independent':'c'*64}
    d=dict(issue='101106',slot=23,provider_id='444',market=market,approved=True,
        action='REVERSE_AND_HISTORICAL_ID',adjudication_id='COMPOUND',
        roster_ids=['1','2'],source_ids=['20','1'],canonical_source_ids=['2','1'],
        cutoff_utc=cutoff.cutoff_ts.isoformat(),roster_path='roster',capture_path='market',
        independent_evidence_path='independent',files=hashes)
    args=dict(market=market,cutoff=cutoff,source_hashes=hashes,implementation_hashes={'code':'h'})
    original=copy.deepcopy(p)
    r=audit_fixture_market(f,p,decision=d,**args)
    assert r['status']=='QUOTES_PRIOR_DIAGNOSTIC' and p==original
    assert r['source_ids']==['20','1'] and r['effective_source_ids']==['1','2']
    receipt=r['orientation_adjudication']
    from src.temporal_learning.core import stable_json_hash
    mid=dict(p,home_team_id='2')
    assert receipt['original_parsed_sha256']==stable_json_hash(p)
    assert receipt['intermediate_parsed_sha256']==stable_json_hash(mid)
    assert receipt['identity_changes']==[dict(path='/home_team_id',before='20',after='2')]
    assert receipt['changes']==receipt['identity_changes']+receipt['orientation_changes']
    if market=='euro':assert r['rows'][0]['odds_W']==2.
    else:assert r['rows'][0]['over_hk']==.9 and r['rows'][0]['under_hk']==1.
    with pytest.raises(ValueError,match='Reverse sides'):
        audit_fixture_market(f,p,decision=dict(d,action='EXACT_FIXTURE_IDENTITY'),**args)
    with pytest.raises(ValueError,match='reversal'):
        audit_fixture_market(f,p,decision=dict(d,canonical_source_ids=['1','2']),**args)
    contradictory=dict(p,home_team_id='1',away_team_id='20')
    with pytest.raises(ValueError,match='contradicts'):
        audit_fixture_market(f,contradictory,decision=dict(d,source_ids=['1','20']),**args)

@pytest.mark.parametrize('market', ['euro','total'])
def test_exact_event_header_keeps_quote_clocks(market):
    f=dict(issue='101120',slot=7,native_match_id='491147',home_id='295',away_id='1949',
        home='H',away='A',status='完场',cutoff_text='截止时间：2010-11-26 04:45',kickoff_time='08:30')
    p=dict(provider_id='491147',home_team_id='295',away_team_id='1949',kickoff_utc='2010-11-27T00:30:00+00:00',
        quotes=[dict(quote_id='1',company='A',quoted_at='2010-11-25T20:44:00Z'),
                dict(quote_id='2',company='B',quoted_at='2010-11-26T20:44:00Z')])
    cutoff=Cutoff.decision_epoch('101120','2010-11-25T20:45:00+00:00')
    files={k:'a'*64 for k in ('roster','capture','first','second')}
    d=dict(issue='101120',slot=7,provider_id='491147',market='euro',roster_ids=['295','1949'],
        source_ids=['295','1949'],cutoff_utc=cutoff.cutoff_ts.isoformat(),approved=True,
        action='CORRECT_EURO_EVENT_HEADER',adjudication_id='date-fix',roster_path='roster',
        capture_path='capture',independent_evidence_path='first',second_independent_path='second',
        files=files,original_kickoff_utc=p['kickoff_utc'],corrected_kickoff_utc='2010-11-26T00:30:00+00:00')
    if market=='total':
        p=dict(provider_id='491147',home_team_id='295',away_team_id='1949',kickoff_local='2010-11-27 08:30',overview=[],changes=[dict(quote_id='1/A',company='A',quoted_local='11-26 04:44',phase='PREMATCH',line=2.5,over_hk=0.9,under_hk=0.9),dict(quote_id='2/B',company='B',quoted_local='11-27 04:44',phase='PREMATCH',line=2.5,over_hk=0.9,under_hk=0.9)])
        d.update(market='total',action='CORRECT_TOTAL_EVENT_HEADER')
    args=dict(market=market,cutoff=cutoff,source_hashes=files,implementation_hashes={'code':'h'})
    before=copy.deepcopy(p)
    assert audit_fixture_market(f,p,**args)['status']=='DAY_MISMATCH'
    r=audit_fixture_market(f,p,decision=d,**args)
    assert r['status']=='QUOTES_PRIOR_DIAGNOSTIC' and len(r['rows'])==1
    assert r['rows'][0]['quote_id']==('1' if market=='euro' else '1/A') and p==before
    assert r['event_date_adjudication']['quote_timestamps_changed'] is False
    for change in [dict(slot=8),dict(approved=False),dict(second_independent_path='first'),
                   dict(original_kickoff_utc='bad'),dict(corrected_kickoff_utc='2010-11-27T00:30:00+00:00'),
                   dict(corrected_kickoff_utc='2010-11-26T01:30:00+00:00')]:
        with pytest.raises(ValueError): audit_fixture_market(f,p,decision=dict(d,**change),**args)
    with pytest.raises(ValueError):
        audit_fixture_market(f,p,decision=d,**dict(args,source_hashes={}))
