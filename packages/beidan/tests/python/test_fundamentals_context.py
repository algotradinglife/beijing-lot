"""Synthetic documented source profiles; no live requests or real outcome labels."""
import copy
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pytest

from beidan_backend import fundamentals_context as ctx, versioning


def page(source, *, marker='(主)', competition='联赛', native='77', history=True,
         history_neutral=True, auxiliary=False):
    row=[None]*(16 if source=='titan' else 21)
    row[:11]=['26-01-01','007','历史联赛','#fff',1,'A(中)' if history_neutral else 'A',2,'B',1,0,'0-0']
    row[15 if source=='titan' else 20]=9001
    arrays='var h_data='+json.dumps([row] if history else [],ensure_ascii=False)+';var a_data=[];var v_data=[];'
    identity="var scheduleID=9;var hometeam='A';var guestteam='B';var h2h_home=1;var h2h_away=2;var strTime='2026-09-25 13:00:00';"
    if source=='titan':
        link=f'<a class="LName" href="//info.titan007.com/league_match/league_vs/2026/{native}.htm">{competition}</a>'
        team='//zq.titan007.com/cn/team/Summary/1.html'
    else:
        link=f'<a class="sclassName" href="//info.nowscore.com/aspx/Sclass.aspx?id={native}&amp;lang=0">{competition}</a>'
        team='//info.nowscore.com/cn/team/Summary.aspx?teamid=1'
    data='<script src="/analysisJs/data9.js"></script>' if auxiliary else '<script>'+arrays+'</script>'
    raw=('<html><title>数据分析</title><input id="hide_scheduleId" value="9"><script>'+identity+
         '</script>'+link+f'<a href="{team}">A{marker}</a>'+data+'</html>').encode()
    return raw,(identity+arrays).encode() if auxiliary else None


def parsed(source, **kwargs):
    raw,aux=page(source,**kwargs)
    receipt=dict(source=source,url=('https://zq.titan007.com/analysis/9cn.htm' if source=='titan'
        else 'https://live.nowscore.com/analysis/9cn.html'),observed_at='2026-10-18T00:00:00.123456+00:00',
        sha256=hashlib.sha256(raw).hexdigest())
    ar=None if aux is None else dict(source=source,url='https://live.nowscore.com/analysisJs/data9.js',
        observed_at=receipt['observed_at'],sha256=hashlib.sha256(aux).hexdigest())
    result=ctx.parse_source_context(raw,fixture_id='26098:1',source=source,
        identity=dict(provider_id='9',home_id='1',away_id='2'),receipt=receipt,
        auxiliary_raw=aux,auxiliary_receipt=ar)
    return result,raw,receipt,aux,ar


@pytest.fixture
def base():
    return [dict(fixture_id='26098:1',provider_id='9',home_id='1',away_id='2')], [dict(
        fixture_id='26098:1',scope='home_recent',match_id='9001',event_date='2026-01-01',
        home_id='1',away_id='2',selected_source='titan')]


@pytest.mark.parametrize('source',['titan','nowscore'])
@pytest.mark.parametrize('marker,expected',[('(主)',False),('(中)',True),('',None)])
def test_parse_real_profile_shapes_and_nullable_markers(source,marker,expected):
    p,*_=parsed(source,marker=marker)
    assert p['fixture']['neutral'] is expected
    assert p['fixture']['competition_id']=='77' and p['fixture']['competition']=='联赛'
    assert p['history'][0]['competition_id']=='007'
    assert p['history'][0]['explicit_neutral'] is True
    assert p['history'][0]['event_date']=='2026-01-01'


def test_auxiliary_actual_source_binding_and_unmarked_history():
    p,raw,r,aux,ar=parsed('nowscore',auxiliary=True,history_neutral=False)
    assert p['history'][0]['data_sha256']==ar['sha256']
    assert p['history'][0]['analysis_sha256']==r['sha256']
    assert p['history'][0]['explicit_neutral'] is None
    assert [x['resource'] for x in p['provenance']]==['analysis','auxiliary']
    ar['sha256']='0'*64
    with pytest.raises(ValueError,match='receipt'):
        ctx.parse_source_context(raw,fixture_id='26098:1',source='nowscore',
            identity=dict(provider_id='9',home_id='1',away_id='2'),receipt=r,
            auxiliary_raw=aux,auxiliary_receipt=ar)


@pytest.mark.parametrize('damage',['hash','time','provider','home','source','identity_type','aux_pair','foreign_link'])
def test_parser_failure_boundaries(damage):
    _,raw,r,_,_=parsed('titan');identity=dict(provider_id='9',home_id='1',away_id='2');source='titan';extra={}
    if damage=='hash':r['sha256']='0'*64
    elif damage=='time':r['observed_at']='2026-10-18T00:00:00'
    elif damage=='provider':identity['provider_id']='8'
    elif damage=='home':identity['home_id']='3'
    elif damage=='source':source='other'
    elif damage=='identity_type':identity['home_id']=1
    elif damage=='aux_pair':extra['auxiliary_raw']=b'var h_data=[];'
    else:
        raw=raw.replace(b'info.titan007.com/league_match',b'foreign.test/league_match')
        r['sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):ctx.parse_source_context(raw,fixture_id='26098:1',source=source,
        identity=identity,receipt=r,**extra)


def test_reconciliation_retains_variants_conflicts_and_base_source(base):
    f,h=base;a=parsed('titan',competition='联赛 第1轮')[0];b=parsed('nowscore')[0]
    before=copy.deepcopy([a,b]);out=ctx.reconcile_context([a,b],f,h)
    assert [a,b]==before and out['fixture'][0]['competition']=='联赛 第1轮'
    assert any(r['state']=='LABEL_VARIANT' for r in out['reconciliation'])
    assert out['history'][0]['competition_id']=='007'
    b['fixture']['neutral']=True
    assert ctx.reconcile_context([a,b],f,h)['fixture'][0]['neutral'] is None
    b['history'][0]['competition_id']='8'
    out=ctx.reconcile_context([a,b],f,h)
    assert out['history'][0]['competition_id'] is None and out['history'][0]['state']=='CONFLICT'
    with pytest.raises(ValueError,match='duplicate'):ctx.reconcile_context([a,a],f,h)
    with pytest.raises(ValueError,match='two-source'):ctx.reconcile_context([a],f,h)
    with pytest.raises(ValueError,match='duplicate'):ctx.reconcile_context([a,b],f,h+h)
    b['history'][0]['home_id']='4'
    with pytest.raises(ValueError,match='party/date'):ctx.reconcile_context([a,b],f,h)


def test_missing_supplement_and_preferred_cells(base):
    f,h=base;a=parsed('titan',marker='',history_neutral=False)[0];b=parsed('nowscore',marker='(中)')[0]
    out=ctx.reconcile_context([a,b],f,h)
    assert out['fixture'][0]['neutral'] is True and out['history'][0]['explicit_neutral'] is True
    h[0]['selected_source']='nowscore';out=ctx.reconcile_context([a,b],f,h)
    assert out['history'][0]['base_selected_source']=='nowscore'
    assert ctx._cell('x','x',None,None,'titan')['state']=='MISSING'
    assert ctx._cell('x','x','a','a','nowscore')['selected_source']=='nowscore'
    with pytest.raises(ValueError):ctx._cell('x','x',1,1,'invalid')
    a['history']=[];b['history']=[]
    with pytest.raises(ValueError,match='source missing'):ctx.reconcile_context([a,b],f,h)


def test_arrow_bool_empty_null_and_strict_scalars():
    schema=dict(id='character',neutral='logical',observed_at='timestamp')
    rows=[dict(id='0001',neutral=x,observed_at='2026-10-18T00:00:00.123456+00:00') for x in (True,False,None)]
    table=ctx.context_arrow_table(rows,schema)
    assert table['id'].to_pylist()==['0001']*3 and table['neutral'].to_pylist()==[True,False,None]
    assert pa.types.is_boolean(table.schema.field('neutral').type)
    assert table.schema.field('observed_at').type==pa.timestamp('us',tz='UTC')
    assert ctx.context_arrow_table([],schema).schema==table.schema
    rows[0]['neutral']=1
    with pytest.raises(ValueError,match='logical'):ctx.context_arrow_table(rows,schema)
    with pytest.raises(ValueError,match='columns'):ctx.context_arrow_table([{}],schema)


@pytest.fixture
def publication(tmp_path,base):
    frozen=tmp_path/'nas';hot=tmp_path/'hot';hot.mkdir();(frozen/'registry').mkdir(parents=True)
    (frozen/'registry/catalog.json').write_text(json.dumps({'schema':'beijing_lot_catalog_v1','datasets':{}}))
    directory=frozen/'datasets/source_issue_26098/versions/v1';directory.mkdir(parents=True)
    (directory/'manifest.json').write_text(json.dumps({'tables':{'match':{'rows':1},'history':{'rows':1}}}))
    rawroot=frozen/'reports/raw';(rawroot/'raw').mkdir(parents=True);receipts=[]
    for source in ('titan','nowscore'):
        _,raw,r,_,_=parsed(source);name='raw/'+r['sha256']+'.bin';(rawroot/name).write_bytes(raw)
        receipts.append(dict(fixture_id='26098:1',**r,path=name,capture_observed_at=r['observed_at']))
    (rawroot/'raw-receipts.json').write_text(json.dumps(receipts))
    manifest=dict(dataset='source_issue_26098',version='v1',base_manifest_sha256=versioning.sha256_file(directory/'manifest.json'),
        members={'raw-receipts.json':versioning.sha256_file(rawroot/'raw-receipts.json')})
    (rawroot/'asset-manifest.json').write_text(json.dumps(manifest))
    f,h=base
    return dict(issue='26098',base_version='v1',base_manifest_sha256=manifest['base_manifest_sha256'],
        raw_evidence_relative='reports/raw',raw_manifest_sha256=versioning.sha256_file(rawroot/'asset-manifest.json'),
        base_reader=lambda dataset,table,version,root:json.dumps(f if table=='match' else h),
        environ={'BEIDAN_PARQUET_ROOT':str(frozen),'BEIDAN_HOT_ROOT':str(hot)})


def test_publication_repeat_readback_and_corruption(publication):
    first=ctx.publish_fundamentals_context(**publication)
    assert first['status']=='published'
    assert ctx.publish_fundamentals_context(**publication)=={**first,'status':'unchanged'}
    root=Path(publication['environ']['BEIDAN_PARQUET_ROOT']);d=root/'datasets'/first['dataset']/'versions'/first['version']
    import pyarrow.parquet as pq
    assert pq.read_table(d/'tables/fixture.parquet')['neutral'].to_pylist()==[False]
    assert pq.read_table(d/'tables/history.parquet')['competition_id'].to_pylist()==['007']
    (d/'receipt.json').write_text('{}')
    with pytest.raises(versioning.VersionError):ctx.publish_fundamentals_context(**publication)


def test_publication_rollback_and_retry(publication,monkeypatch):
    original=versioning.write_json_atomically;root=Path(publication['environ']['BEIDAN_PARQUET_ROOT']);catalog=root/'registry/catalog.json';before=catalog.read_bytes()
    def fail(value,path):
        if Path(path)==catalog:raise OSError('catalog failure')
        return original(value,path)
    monkeypatch.setattr(versioning,'write_json_atomically',fail)
    with pytest.raises(OSError,match='catalog failure'):ctx.publish_fundamentals_context(**publication)
    assert catalog.read_bytes()==before and not (root/'datasets/source_fundamentals_context_26098/current.json').exists()
    monkeypatch.setattr(versioning,'write_json_atomically',original)
    assert ctx.publish_fundamentals_context(**publication)['status']=='published'


@pytest.mark.parametrize('damage',['base_hash','raw_hash','path','source_bytes','base_identity','history_key','base_type'])
def test_publication_rejects_unbound_inputs(publication,damage):
    if damage=='base_hash':publication['base_manifest_sha256']='0'*64
    elif damage=='raw_hash':publication['raw_manifest_sha256']='0'*64
    elif damage=='path':publication['raw_evidence_relative']='../outside'
    elif damage=='source_bytes':
        next((Path(publication['environ']['BEIDAN_PARQUET_ROOT'])/'reports/raw/raw').glob('*.bin')).write_bytes(b'changed')
    else:
        original=publication['base_reader']
        f=json.loads(original('','match','',''));h=json.loads(original('','history','',''))
        if damage=='base_identity':f[0]['home_id']='3'
        elif damage=='history_key':h[0]['match_id']='999'
        else:f[0]['home_id']=1
        publication['base_reader']=lambda dataset,table,version,root:json.dumps(f if table=='match' else h)
    with pytest.raises((ValueError,KeyError)):ctx.publish_fundamentals_context(**publication)


@pytest.mark.parametrize('field,value',[('version','wrong'),('location','frozen:datasets/other'),
    ('schema_id','other'),('format','csv'),('tables',1)])
def test_noop_rejects_catalog_binding_drift(publication,field,value):
    first=ctx.publish_fundamentals_context(**publication)
    root=Path(publication['environ']['BEIDAN_PARQUET_ROOT']);path=root/'registry/catalog.json'
    catalog=json.loads(path.read_text());catalog['datasets'][first['dataset']][field]=value
    path.write_text(json.dumps(catalog))
    with pytest.raises(versioning.VersionError,match='catalog/current'):ctx.publish_fundamentals_context(**publication)


def test_noop_uses_verified_inputs_without_reparsing(publication,monkeypatch):
    first=ctx.publish_fundamentals_context(**publication)
    monkeypatch.setattr(ctx,'parse_source_context',lambda *a,**k:(_ for _ in ()).throw(AssertionError('unexpected parse')))
    assert ctx.publish_fundamentals_context(**publication)=={**first,'status':'unchanged'}


@pytest.mark.parametrize('file',['tables/history.parquet','manifest.json','schema'])
def test_noop_checks_data_metadata_and_schema(publication,file):
    first=ctx.publish_fundamentals_context(**publication);root=Path(publication['environ']['BEIDAN_PARQUET_ROOT'])
    path=(root/'schemas/beidan_fundamentals_context_v1.json' if file=='schema' else
          root/'datasets'/first['dataset']/'versions'/first['version']/file)
    path.write_bytes(b'{}')
    with pytest.raises(versioning.VersionError):ctx.publish_fundamentals_context(**publication)


def test_concurrent_identical_publications_share_one_version(publication):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:ctx.publish_fundamentals_context(**publication),range(2)))
    assert sorted(r['status'] for r in results)==['published','unchanged']
    assert len({r['version'] for r in results})==1


def test_empty_published_history_is_not_an_error():
    a=parsed('titan',history=False)[0];b=parsed('nowscore',history=False)[0]
    f=[dict(fixture_id='26098:1',provider_id='9',home_id='1',away_id='2')]
    out=ctx.reconcile_context([a,b],f,[])
    assert out['history']==out['source_history']==[]
    for table,rows in out.items():ctx.context_arrow_table(rows,ctx.SCHEMAS[table]).validate(full=True)


def test_history_labels_are_not_silently_numeric_and_ids_keep_nulls():
    _,raw,r,_,_=parsed('titan')
    for value,valid in [(None,True),(12,False)]:
        changed=raw.replace('"历史联赛"'.encode(),json.dumps(value).encode())
        receipt={**r,'sha256':hashlib.sha256(changed).hexdigest()}
        args=dict(fixture_id='26098:1',source='titan',identity=dict(provider_id='9',home_id='1',away_id='2'),receipt=receipt)
        if valid:assert ctx.parse_source_context(changed,**args)['history'][0]['competition'] is None
        else:
            with pytest.raises(ValueError,match='label must be text'):ctx.parse_source_context(changed,**args)


def test_invalid_receipt_hash_cannot_escape_raw_directory(publication,monkeypatch):
    root=Path(publication['environ']['BEIDAN_PARQUET_ROOT']);raw=root/'reports/raw'
    receipts=json.loads((raw/'raw-receipts.json').read_text())
    receipts[0].update(sha256='../outside',path='raw/../outside.bin')
    (raw/'raw-receipts.json').write_text(json.dumps(receipts))
    manifest=json.loads((raw/'asset-manifest.json').read_text())
    manifest['members']['raw-receipts.json']=versioning.sha256_file(raw/'raw-receipts.json')
    (raw/'asset-manifest.json').write_text(json.dumps(manifest))
    publication['raw_manifest_sha256']=versioning.sha256_file(raw/'asset-manifest.json')
    original=versioning.sha256_file
    def guard(path):
        assert Path(path)!=raw/'raw/../outside.bin'
        return original(path)
    monkeypatch.setattr(versioning,'sha256_file',guard)
    with pytest.raises(ValueError,match='canonical raw'):ctx.publish_fundamentals_context(**publication)
