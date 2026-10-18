"""Offline cup-table parsing, quarantine and immutable publication contracts."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from beidan_backend import cup_standings as cup, versioning


@pytest.fixture
def identity():
    return dict(provider_id='9',home_id='1',away_id='2')


def page(source, *, empty=False, absent=False):
    head="""<html><title>数据分析</title><input id="hide_scheduleId" value="9">
    <script>var hometeam='A';var guestteam='B';var h2h_home=1;var h2h_away=2;
    var strTime='2026-09-25 13:00:00';</script>"""
    if absent:return (head+'</html>').encode()
    if source=='titan':
        header=['排名','球队','总','胜','平','负','得','失','净','积分'];domain='zq.titan007.com'
        values=[['1','2','1','1','0','3','1','2','4'],['2','2','0','1','1','1','3','-2','1']]
    else:
        header=['排名','球队','赛','胜','平','负','得','失','积分'];domain='info.nowscore.com'
        values=[['1','2','1','1','0','3','1','4'],['2','2','0','1','1','1','3','1']]
    body='<tr>'+''.join('<td>'+v+'</td>' for v in header)+'</tr>'
    if not empty:
        for team,v in zip(['1','2'],values):
            cells=[v[0],f'<a href="//{domain}/cn/team/Summary/{team}.html">Team {team}</a>',*v[1:]]
            body+='<tr>'+''.join('<td>'+x+'</td>' for x in cells)+'</tr>'
    table='<table'+(' class="cup_jifen"' if source=='nowscore' else '')+'>'+body+'</table>'
    return (head+('<div id="cupScore">'+table+'</div>' if source=='titan' else table)+'</html>').encode()


def parsed(source, identity, **kwargs):
    raw=page(source,**kwargs)
    receipt=dict(source=source,url=f"https://{'zq.titan007.com' if source=='titan' else 'live.nowscore.com'}/analysis/9cn.{'htm' if source=='titan' else 'html'}",
                 observed_at='2026-10-18T00:00:00.123456+00:00',sha256=hashlib.sha256(raw).hexdigest())
    return raw,cup.parse_cup_standings(raw,fixture_id='26098:1',source=source,identity=identity,receipt=receipt)


def test_source_normalization_membership_and_reconciliation(identity):
    _,a=parsed('titan',identity);_,b=parsed('nowscore',identity)
    assert a['groups']==b['groups']
    assert a['rows'][1]['goal_difference']==b['rows'][1]['goal_difference']==-2
    assert b['rows'][0]['goal_difference_basis']=='GOALS_FOR_MINUS_AGAINST'
    original=copy.deepcopy([a,b]);out=cup.reconcile_cup_standings([a,b])
    assert [a,b]==original
    assert len(out['standings'])==2 and all(r['state']=='AGREEMENT' for r in out['standings'])
    assert len(out['source_standings'])==4
    assert cup.reconcile_cup_standings([])=={k:[] for k in cup.SCHEMAS}


@pytest.mark.parametrize('source',['titan','nowscore'])
def test_absent_empty_and_zero_are_distinct(identity,source):
    _,a=parsed(source,identity,absent=True);_,e=parsed(source,identity,empty=True)
    assert a['coverage']['group_count'] is None and a['coverage']['state']=='ABSENT'
    assert e['coverage']['group_count']==1 and e['coverage']['team_rows']==0
    assert e['coverage']['state']=='PUBLISHED_EMPTY'
    assert cup.reconcile_cup_standings([a])['standings']==[]
    assert cup.reconcile_cup_standings([e])['standings']==[]
    _,z=parsed(source,identity)
    # A published loss count of zero is retained, never converted to missing.
    assert z['rows'][0]['losses']==0


@pytest.mark.parametrize('replacement,message',[
    ('<td>4</td>','inconsistent'),('<td>x</td>','invalid cup integer')])
def test_numeric_errors_fail(identity,replacement,message):
    raw=page('titan').replace(b'<td>2</td>',replacement.encode(),1)
    _,p=parsed('titan',identity);receipt={**p['provenance'],'sha256':hashlib.sha256(raw).hexdigest()}
    with pytest.raises(ValueError,match=message):cup.parse_cup_standings(raw,fixture_id='26098:1',source='titan',identity=identity,receipt=receipt)


@pytest.mark.parametrize('damage',['hash','source','time','identity','header','duplicate','foreign','link','nested'])
def test_source_integrity_and_shapes_fail(identity,damage):
    raw,p=parsed('titan',identity);receipt=dict(p['provenance']);target=dict(identity)
    if damage=='hash':receipt['sha256']='0'*64
    elif damage=='source':receipt['source']='nowscore'
    elif damage=='time':receipt['observed_at']='2026-10-18T00:00:00'
    elif damage=='identity':target['home_id']='3'
    elif damage=='header':raw=raw.replace('积分'.encode(),'分数'.encode())
    elif damage=='duplicate':raw=raw.replace(b'Summary/2.html',b'Summary/1.html')
    elif damage=='foreign':raw=raw.replace(b'Summary/2.html',b'Summary/3.html')
    elif damage=='link':raw=raw.replace(b'//zq.titan007.com/cn/team/Summary/2.html',b'https://foreign.test/2')
    else:raw=raw.replace(b'<table>',b'<table><table></table>',1)
    if damage not in {'hash','source','time'}:receipt['sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):cup.parse_cup_standings(raw,fixture_id='26098:1',source='titan',identity=target,receipt=receipt)


def test_cells_and_membership_conflicts_quarantined(identity):
    _,a=parsed('titan',identity);_,b=parsed('nowscore',identity)
    b['rows'][0]['points']=5
    out=cup.reconcile_cup_standings([a,b]);assert out['standings'][0]['points'] is None
    assert out['standings'][0]['played']==2 and out['standings'][0]['state']=='CONFLICT'
    assert any(r['titan_json']=='4' and r['nowscore_json']=='5' for r in out['reconciliation'])
    b['groups']=['different'];assert cup.reconcile_cup_standings([a,b])['standings']==[]
    with pytest.raises(ValueError,match='duplicate'):cup.reconcile_cup_standings([a,a])
    assert all(r['state']=='PRIMARY_ONLY' for r in cup.reconcile_cup_standings([a])['standings'])
    assert all(r['state']=='SUPPLEMENTED' for r in cup.reconcile_cup_standings([parsed('nowscore',identity)[1]])['standings'])


@pytest.fixture
def publication(tmp_path,identity):
    frozen=tmp_path/'nas';hot=tmp_path/'hot';hot.mkdir();(frozen/'registry').mkdir(parents=True)
    (frozen/'registry/catalog.json').write_text(json.dumps({'schema':'beijing_lot_catalog_v1','datasets':{'other':{'owner':'unrelated'}}}))
    base=frozen/'datasets/source_issue_26098/versions/v1';base.mkdir(parents=True)
    (base/'manifest.json').write_text(json.dumps({'tables':{'match':{'rows':1}}}))
    rawroot=frozen/'reports/raw';(rawroot/'raw').mkdir(parents=True)
    parses=[];receipts=[]
    for source in ['titan','nowscore']:
        raw,p=parsed(source,identity);parses.append(p);r=p['provenance']
        path='raw/'+r['sha256']+'.bin';(rawroot/path).write_bytes(raw)
        receipts.append({**r,'path':path,'capture_observed_at':r['observed_at']})
    (rawroot/'raw-receipts.json').write_text(json.dumps(receipts))
    manifest={'dataset':'source_issue_26098','version':'v1','base_manifest_sha256':versioning.sha256_file(base/'manifest.json'),'members':{'raw-receipts.json':versioning.sha256_file(rawroot/'raw-receipts.json')}}
    (rawroot/'asset-manifest.json').write_text(json.dumps(manifest))
    return parses,dict(issue='26098',base_version='v1',base_manifest_sha256=manifest['base_manifest_sha256'],raw_evidence_relative='reports/raw',raw_manifest_sha256=versioning.sha256_file(rawroot/'asset-manifest.json'),base_reader=lambda *_:json.dumps([dict(fixture_id='26098:1',**identity)]),environ={'BEIDAN_PARQUET_ROOT':str(frozen),'BEIDAN_HOT_ROOT':str(hot)})


def test_publish_idempotence_readback_and_tamper_rejection(publication):
    rows,kwargs=publication;first=cup.publish_cup_standings(rows,**kwargs)
    assert first['status']=='published'
    assert cup.publish_cup_standings(rows,**kwargs)=={**first,'status':'unchanged'}
    frozen=Path(kwargs['environ']['BEIDAN_PARQUET_ROOT']);cat=json.loads((frozen/'registry/catalog.json').read_text())
    assert cat['datasets']['other']=={'owner':'unrelated'}
    directory=frozen/'datasets'/first['dataset']/'versions'/first['version']
    import pyarrow.parquet as pq
    assert pq.read_table(directory/'tables/standings.parquet').num_rows==2
    mutated=copy.deepcopy(rows);mutated[0]['rows'][0]['points']=12
    with pytest.raises(ValueError,match='pinned source'):cup.publish_cup_standings(mutated,**kwargs)
    (directory/'tables/coverage.parquet').write_bytes(b'corrupt')
    with pytest.raises(versioning.VersionError):cup.publish_cup_standings(rows,**kwargs)


def test_publish_rollback_and_retry(publication,monkeypatch):
    rows,kwargs=publication;original=versioning.write_json_atomically
    catalog=Path(kwargs['environ']['BEIDAN_PARQUET_ROOT'])/'registry/catalog.json'
    before=catalog.read_bytes()
    def fail(value,path):
        if Path(path)==catalog:raise OSError('simulated catalog failure')
        return original(value,path)
    monkeypatch.setattr(versioning,'write_json_atomically',fail)
    with pytest.raises(OSError,match='simulated'):cup.publish_cup_standings(rows,**kwargs)
    destination=catalog.parent.parent/'datasets/source_cup_standings_26098'
    assert not (destination/'current.json').exists() and catalog.read_bytes()==before
    monkeypatch.setattr(versioning,'write_json_atomically',original)
    assert cup.publish_cup_standings(rows,**kwargs)['status']=='published'


@pytest.mark.parametrize('field,value',[('base_manifest_sha256','0'*64),('raw_manifest_sha256','0'*64),('raw_evidence_relative','../bad')])
def test_publish_rejects_wrong_bindings(publication,field,value):
    rows,kwargs=publication;kwargs[field]=value
    with pytest.raises(ValueError):cup.publish_cup_standings(rows,**kwargs)


@pytest.mark.parametrize('case',['fixture_set','provider','home','away','duplicate','missing_type'])
def test_publisher_requires_exact_authoritative_base_identity(publication,case):
    rows,kwargs=publication
    base=json.loads(kwargs['base_reader']())
    if case=='fixture_set':base[0]['fixture_id']='26098:2'
    elif case=='duplicate':base.append(dict(base[0]))
    elif case=='missing_type':base[0]['home_id']=1
    else:base[0][{'provider':'provider_id','home':'home_id','away':'away_id'}[case]]='99'
    kwargs['base_reader']=lambda *_:json.dumps(base)
    with pytest.raises(ValueError):cup.publish_cup_standings(rows,**kwargs)
