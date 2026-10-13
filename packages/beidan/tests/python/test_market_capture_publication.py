"""Catalog publication, immutable binding, rollback and chronology contracts."""
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import pyarrow as pa
import pytest
from beidan_backend import versioning
from beidan_backend.catalog.paths import LocationError
from beidan_backend.market_capture.publication import publish_market_snapshot


@pytest.fixture
def inputs(tmp_path):
    frozen=tmp_path/'frozen';hot=tmp_path/'hot';hot.mkdir();(frozen/'registry').mkdir(parents=True);(frozen/'schemas').mkdir()
    versioning.write_json_atomically(dict(schema='beijing_lot_catalog_v1',datasets={}),frozen/'registry/catalog.json')
    ct=datetime(2026,10,4,18,30,tzinfo=timezone.utc);qt=datetime(2026,10,4,16,tzinfo=timezone.utc)
    history=pa.table(dict(fixture_id=['26102:6'],market=['euro'],sequence=[1],company_id=['281'],quote_at=[qt],prior=[True]))
    latest=pa.table(dict(fixture_id=['26102:6'],market=['euro'],company_id=['281'],quote_at=[qt],qualified=[True],fresh=[True],supported=[True]))
    coverage=pa.table(dict(fixture_id=['26102:6']*3,market=['euro','asian','totals'],cutoff_utc=[ct]*3))
    provenance=coverage.append_column('collected_at',pa.array([datetime(2026,10,13,tzinfo=timezone.utc)]*3))
    for name,values in {'source_url':['https://example.test/history']*3,'response_sha256':['5'*64]*3,'request_error':['']*3,'availability':['HISTORICAL_QUOTE_PROXY']*3,'parser_sha256':['6'*64]*3,'packet_sha256':['7'*64]*3}.items():provenance=provenance.append_column(name,pa.array(values))
    receipt=dict(historical_admitted=False,scope_sha256='1'*64,input_hashes={'input':'2'*64},implementation_hashes={'code':'3'*64},cutoffs={'26102:6':ct.isoformat()})
    receipt.update(admission_implementation_hashes={'shared.py':'8'*64},admission_receipts={'26102:6':{'cutoff':{'issue_id':'26102','cutoff_utc':ct.isoformat()},'admission_state':'PRIOR_PROXY_QUOTES','shared':{'cutoff_identity':'DECISION_EPOCH_26102','cutoff_kind':'DECISION_EPOCH','cutoff_ts':ct.isoformat(),'target_issue':'26102','maximum_source_time':qt.isoformat(),'maximum_training_label_timestamp':qt.isoformat(),'availability':{'intended_use':'HISTORICAL_DIAGNOSTIC','policy':{'kind':'HISTORICAL_PROXY','prospective_capable':False}},'implementation':{'files':{'shared.py':'8'*64}},'implementation_hashes':{'shared.py':'8'*64},'source_hashes':{'input':'2'*64},'cache_key':'a'*64,'admitted_history_sha256':'b'*64}}})
    return dict(history=history,latest=latest,coverage=coverage,provenance=provenance),receipt,{'BEIDAN_PARQUET_ROOT':str(frozen),'BEIDAN_HOT_ROOT':str(hot)}


def test_publishes_and_identically_repeats(inputs):
    t,r,env=inputs;x=publish_market_snapshot(t,r,'20261013-v1',environ=env)
    assert x['status']=='published' and not x['historical_admitted']
    y=publish_market_snapshot(t,r,'20261013-v1',environ=env)
    assert y['status']=='unchanged' and x['binding_sha256']==y['binding_sha256']
    root=Path(env['BEIDAN_PARQUET_ROOT']);m=json.loads((root/'datasets/fm17_replayed_markets/versions/20261013-v1/manifest.json').read_bytes())
    assert set(m['tables'])=={'history','latest','coverage','provenance'}
    catalog=json.loads((root/'registry/catalog.json').read_bytes())
    assert catalog['datasets']['fm17_replayed_markets']['version']=='20261013-v1'
    changed=copy.deepcopy(r);changed['implementation_hashes']['code']='4'*64
    with pytest.raises(versioning.VersionError,match='receipt binding'):publish_market_snapshot(t,changed,'20261013-v1',environ=env)


@pytest.mark.parametrize('kind',['admission','scope','duplicate','clock','future','unknown','root'])
def test_bad_contracts_fail_closed(inputs,kind):
    t,r,env=inputs;t=t.copy();r=copy.deepcopy(r);env=env.copy()
    if kind=='admission':r['historical_admitted']=True
    if kind=='scope':r['cutoffs']={'wrong':r['cutoffs']['26102:6']}
    if kind=='duplicate':t['latest']=pa.concat_tables([t['latest'],t['latest']])
    if kind=='clock':t['history']=t['history'].set_column(t['history'].column_names.index('quote_at'),'quote_at',pa.array(['2026-10-04T16:00:00+00:00']))
    if kind=='future':t['latest']=t['latest'].set_column(t['latest'].column_names.index('quote_at'),'quote_at',pa.array([datetime(2026,10,5,tzinfo=timezone.utc)]))
    if kind=='unknown':t['coverage']=t['coverage'].set_column(1,'market',pa.array(['euro','asian','wrong']))
    if kind=='root':del env['BEIDAN_PARQUET_ROOT']
    with pytest.raises((ValueError,LocationError)):publish_market_snapshot(t,r,'bad-v1',environ=env)
    assert not (Path(inputs[2]['BEIDAN_PARQUET_ROOT'])/'datasets/fm17_replayed_markets/current.json').exists()


def test_failed_registration_restores_prior_pointer(inputs,monkeypatch):
    t,r,env=inputs;publish_market_snapshot(t,r,'20261013-v1',environ=env)
    base=Path(env['BEIDAN_PARQUET_ROOT'])/'datasets/fm17_replayed_markets';before=versioning.read_current(base)
    original=versioning.write_json_atomically
    def fail_catalog(value,path):
        if Path(path).name=='catalog.json':raise OSError('injected registration failure')
        return original(value,path)
    monkeypatch.setattr(versioning,'write_json_atomically',fail_catalog)
    with pytest.raises(OSError,match='injected'):publish_market_snapshot(t,r,'20261013-v2',environ=env)
    assert versioning.read_current(base)==before
    assert not (base/'versions/20261013-v2').exists()
    assert (base/'.failed-20261013-v2').is_dir()
    assert json.loads((Path(env['BEIDAN_PARQUET_ROOT'])/'registry/catalog.json').read_bytes())['datasets']['fm17_replayed_markets']['version']=='20261013-v1'


@pytest.mark.parametrize('kind',['missing','cutoff','closure'])
def test_detached_admission_receipts_fail_closed(inputs,kind):
    t,r,env=inputs;r=copy.deepcopy(r)
    if kind=='missing':r['admission_receipts']={}
    if kind=='cutoff':r['admission_receipts']['26102:6']['cutoff']['cutoff_utc']='2026-10-04T19:30:00+00:00'
    if kind=='closure':r['admission_receipts']['26102:6']['shared']['implementation']['files']['shared.py']='9'*64
    with pytest.raises(ValueError):publish_market_snapshot(t,r,'bad-admission',environ=env)


@pytest.mark.parametrize('kind',['missing_shared','shared_cutoff','shared_issue','future_max','availability','cache','files'])
def test_inner_context_is_mandatory_for_admitted_quotes(inputs,kind):
    t,r,env=inputs;r=copy.deepcopy(r);x=r['admission_receipts']['26102:6']
    if kind=='missing_shared':del x['shared']
    if kind=='shared_cutoff':x['shared']['cutoff_ts']='2026-10-05T18:30:00+00:00'
    if kind=='shared_issue':x['shared']['target_issue']='26101'
    if kind=='future_max':x['shared']['maximum_source_time']='2026-10-05T18:30:00+00:00'
    if kind=='availability':x['shared']['availability']['policy']['prospective_capable']=True
    if kind=='cache':del x['shared']['cache_key']
    if kind=='files':x['shared']['implementation']['files']={}
    with pytest.raises(ValueError):publish_market_snapshot(t,r,'bad-inner',environ=env)
    assert not (Path(env['BEIDAN_PARQUET_ROOT'])/'datasets/fm17_replayed_markets/current.json').exists()


def test_explicit_zero_admission_does_not_require_nonexistent_context(inputs):
    from beidan_backend.temporal_learning.core import Cutoff
    from beidan_backend.temporal_learning.quote_receipt import validate_quote_admission_receipt
    _,r,_=inputs;x=copy.deepcopy(r['admission_receipts']['26102:6']);x['admission_state']='NO_PRIOR_QUOTES';x['shared']={'error':'cutoff admits no prior observations'}
    ct=Cutoff.decision_epoch('26102',r['cutoffs']['26102:6'])
    assert validate_quote_admission_receipt(x,ct,0,r['admission_implementation_hashes']) is None
    with pytest.raises(ValueError):validate_quote_admission_receipt(x,ct,1,r['admission_implementation_hashes'])
    with pytest.raises(ValueError):validate_quote_admission_receipt(x,ct,-1,r['admission_implementation_hashes'])
