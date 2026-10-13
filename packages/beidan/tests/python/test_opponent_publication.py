"""Immutable NAS lifecycle and typed contracts, with isolated catalog roots."""
from copy import deepcopy
import hashlib
from datetime import datetime,timezone
import json
from pathlib import Path
import pyarrow as pa
import pytest
from beidan_backend import versioning
from beidan_backend.opponent_publication import publish_opponent_research
from beidan_backend.temporal_learning.provenance import implementation_closure
from test_serialized_opponent_fit import fitted,ROOT


@pytest.fixture
def publication(fitted,tmp_path):
    fit,cutoff=fitted
    frozen=tmp_path/'frozen';hot=tmp_path/'hot';hot.mkdir();(frozen/'registry').mkdir(parents=True);(frozen/'schemas').mkdir()
    versioning.write_json_atomically(dict(schema='beijing_lot_catalog_v1',datasets={}),frozen/'registry/catalog.json')
    f='26102:6';ct=datetime(2020,2,1,tzinfo=timezone.utc)
    tables=dict(audit=pa.table(dict(fixture_id=[f],state=['ESTIMATED'],cutoff_utc=[ct])),
        probabilities=pa.table(dict(fixture_id=[f]*3,model=['OPPONENT_NATIVE']*3,outcome=['W','D','L'],probability=[.5,.3,.2])),
        metrics=pa.table(dict(cohort=['ESTIMATED_PAIRED'],issue_id=['ALL'],comparison=['model_only'],model=['OPPONENT_NATIVE'],n=[1])),
        lambdas=pa.table(dict(fixture_id=[f],lambda_home=[2.],lambda_away=[1.])),
        margins=pa.table(dict(fixture_id=[f]*3,model=['OPPONENT_NATIVE']*3,stage=['base']*3,margin=[-1,0,1],probability=[.2,.3,.5])),
        coefficients=pa.table(dict(fixture_id=[f],term=['Intercept'],value=[.1])),
        observations=pa.table(dict(fixture_id=[f],row_key=['m1:home'],goals=[2])),
        support=pa.table(dict(fixture_id=[f],team_id=['A'],venue=['home'],matches=[12])),
        snapshots=pa.table(dict(snapshot_id=['inputs'],payload=['{}'],sha256=[hashlib.sha256(b'{}').hexdigest()])))
    receipt=dict(intended_use='POSTHOC_HISTORICAL_DIAGNOSTIC',formal_FM_unchanged=True,
        input_hashes={'forecasts':'a'*64},implementation_hashes={'code':'b'*64},
        independent_replay=dict(status='FULL_IDENTICAL_REPLAY',sha256='a'*64),
        publication_implementation=implementation_closure(ROOT,('beidan_backend.opponent_publication',),distributions=('pyarrow','pandas','numpy','filelock')),
        fits={f:fit},cutoffs={f:ct.isoformat()})
    return tables,receipt,{'BEIDAN_PARQUET_ROOT':str(frozen),'BEIDAN_HOT_ROOT':str(hot)}


def test_publishes_and_same_label_is_immutable(publication):
    tables,receipt,env=publication
    first=publish_opponent_research(tables,receipt,'20261013-v1',environ=env,repository_root=ROOT)
    assert first['status']=='published'
    assert publish_opponent_research(tables,receipt,'20261013-v1',environ=env,repository_root=ROOT)['status']=='unchanged'
    altered=deepcopy(receipt);altered['implementation_hashes']['code']='c'*64
    with pytest.raises(versioning.VersionError):publish_opponent_research(tables,altered,'20261013-v1',environ=env,repository_root=ROOT)
    changed=tables.copy();changed['probabilities']=tables['probabilities'].set_column(3,'probability',pa.array([.6,.2,.2]))
    with pytest.raises(versioning.VersionError):publish_opponent_research(changed,receipt,'20261013-v1',environ=env,repository_root=ROOT)
    manifest=json.loads((Path(env['BEIDAN_PARQUET_ROOT'])/'datasets/fm17_opponent_research/versions/20261013-v1/manifest.json').read_bytes())
    assert set(manifest['tables'])==set(tables)


@pytest.mark.parametrize('change',['cutoff','cutoff_array','foreign','duplicate','mass','missing_fit','no_replay','infinite_lambda','snapshot'])
def test_invalid_publication_fails_closed(publication,change):
    tables,receipt,env=publication;tables=tables.copy();receipt=deepcopy(receipt)
    if change=='cutoff':receipt['cutoffs']['26102:6']='2020-02-02T00:00:00Z'
    if change=='cutoff_array':receipt['cutoffs']=list(receipt['cutoffs'].values())
    if change=='foreign':tables['observations']=pa.table(dict(fixture_id=['26102:99'],row_key=['r'],goals=[2]))
    if change=='duplicate':tables['audit']=pa.concat_tables([tables['audit'],tables['audit']])
    if change=='mass':tables['probabilities']=tables['probabilities'].set_column(3,'probability',pa.array([.5,.5,.5]))
    if change=='missing_fit':receipt['fits']={}
    if change=='no_replay':receipt['independent_replay']={}
    if change=='infinite_lambda':tables['lambdas']=tables['lambdas'].set_column(1,'lambda_home',pa.array([float('inf')]))
    if change=='snapshot':tables['snapshots']=tables['snapshots'].set_column(1,'payload',pa.array(['changed']))
    with pytest.raises(ValueError):publish_opponent_research(tables,receipt,'bad-v1',environ=env,repository_root=ROOT)
    assert not (Path(env['BEIDAN_PARQUET_ROOT'])/'datasets/fm17_opponent_research/current.json').exists()


def test_registration_failure_restores_previous_pointer(publication,monkeypatch):
    tables,receipt,env=publication
    publish_opponent_research(tables,receipt,'20261013-v1',environ=env,repository_root=ROOT)
    base=Path(env['BEIDAN_PARQUET_ROOT'])/'datasets/fm17_opponent_research';before=versioning.read_current(base)
    original=versioning.write_json_atomically
    def reject_registration(value,path):
        if Path(path).name=='catalog.json':raise OSError('injected catalog failure')
        return original(value,path)
    monkeypatch.setattr(versioning,'write_json_atomically',reject_registration)
    with pytest.raises(OSError,match='injected'):
        publish_opponent_research(tables,receipt,'20261013-v2',environ=env,repository_root=ROOT)
    assert versioning.read_current(base)==before
    assert (base/'.failed-20261013-v2').is_dir()
    assert not (base/'versions/20261013-v2').exists()
