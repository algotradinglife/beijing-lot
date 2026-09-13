"""Report packaging boundaries; real probability replay is tested separately."""
import gzip
import hashlib
import json
from pathlib import Path
import pandas as pd
import pytest
import src.n7_core_archive as archive
from src.n7_core_settlement import settle_core_layers
from src.n7_core_study import describe_core_plan
from src.temporal_learning.core import stable_json_hash

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def package_inputs(tmp_path,monkeypatch):
    study=tmp_path/'study';study.mkdir()
    x=json.loads(gzip.decompress((ROOT/'tests/fixtures/n7_core433_replay.json.gz').read_bytes()))
    p=x['plans'][0];p.pop('seal')
    # A cash-only packaging fixture; actual core/copy arithmetic has real tests.
    p.update(layers=[],groups=0,stake=0,cash_cny=1024,unique_tickets=0,allocation=[])
    p['policy']=dict(p['policy'],opportunity_cap_cny=0)
    p['seal']=stable_json_hash(p)
    audit=[dict(issue=f['issue'],slot=f['slot'],provider_id=f['provider_id'],handicap=f['handicap'],
                actual_direction='W',spf_sp=2.,status='READY') for f in p['fixtures']]
    result=settle_core_layers(p,pd.DataFrame(audit))
    path=study/'plan.json.gz';path.write_bytes(gzip.compress(json.dumps(p).encode()))
    config=dict(seeds=[p['seed']],policies=[p['policy']])
    receipt=dict(issues=[p['issue']],parameters=config,plan_hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest()})
    frozen=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (study/'plans-frozen.json').write_text(json.dumps(frozen))
    row=dict(result,arm=p['arm'],seed=p['seed'],reference=False,
        decision_year=min(p['cutoffs'].values())[:4],**describe_core_plan(p))
    payload=dict(rows=[row],issue_order=[p['issue']],freeze_seal=frozen['seal'],historical_admission=False)
    (study/'results.json').write_text(json.dumps(payload))
    (study/'audit-snapshot.json').write_text(json.dumps(dict(rows=audit)))
    er={key+'_sha256':hashlib.sha256((study/name).read_bytes()).hexdigest()
        for key,name in [('freeze','plans-frozen.json'),('result','results.json'),('audit','audit-snapshot.json')]}
    (study/'evaluation-receipt.json').write_text(json.dumps(er))
    base=dict(payload,rows=[dict(row,arm='BASE')],independent_replay=dict(status='PASS'),settlement_replay=dict(status='PASS'))
    body=json.dumps(base);digest=hashlib.sha256(body.encode()).hexdigest()
    baseline=tmp_path/'baseline.gz'
    baseline.write_bytes(gzip.compress(json.dumps(dict(schema='bj425_capital_report_v1',body=body,sha256=digest)).encode()))
    # Isolate archive contracts; never bypass replay in production entry points.
    monkeypatch.setattr(archive,'check_prefix_study',lambda *a,**kw:dict(status='PASS',plans_checked=1))
    return study,tmp_path/'report.gz',dict(frozen_source_root=ROOT,checker_root=ROOT,
        baseline_archive=baseline,baseline_body_sha256=digest,baseline_arm='BASE')


def test_core_archive_complete_rows_hash_and_overwrite(package_inputs):
    study,out,kwargs=package_inputs
    result=archive.package_core_report(study,out,**kwargs)
    wrapper=json.loads(gzip.decompress(out.read_bytes()));body=json.loads(wrapper['body'])
    assert result['rows']==2 and result['plans']==1
    assert hashlib.sha256(wrapper['body'].encode()).hexdigest()==result['sha256']
    assert body['settlement_replay']==dict(status='PASS',plans_checked=1)
    assert body['comparisons'][0]['control']=='BASE'
    assert body['allocations']==[] and body['sleeves']==[]
    with pytest.raises(ValueError,match='overwrite'):archive.package_core_report(study,out,**kwargs)


def test_core_archive_rejects_changed_inputs_and_failed_replay(package_inputs,monkeypatch):
    study,out,kwargs=package_inputs
    raw=(study/'results.json').read_bytes();(study/'results.json').write_bytes(raw+b' ')
    with pytest.raises(ValueError,match='result binding'):archive.package_core_report(study,out,**kwargs)
    assert not out.exists()

    (study/'results.json').write_bytes(raw)
    with pytest.raises(ValueError,match='Baseline archive identity'):
        archive.package_core_report(study,out,**dict(kwargs,baseline_body_sha256='wrong'))
    assert not out.exists()
    with pytest.raises(ValueError,match='Baseline paired grid'):
        archive.package_core_report(study,out,**dict(kwargs,baseline_arm='MISSING'))
    def fail(*a,**kw):raise ValueError('replay failed')
    monkeypatch.setattr(archive,'check_prefix_study',fail)
    with pytest.raises(ValueError,match='replay failed'):archive.package_core_report(study,out,**kwargs)
    assert not out.exists()


@pytest.mark.parametrize('field',['evaluation_any_hit','cash_cny','unique_tickets','cash','mode'])
def test_receipt_consistent_result_mutation_cannot_change_published_plan(package_inputs,field):
    study,out,kwargs=package_inputs
    payload=json.loads((study/'results.json').read_text())
    row=payload['rows'][0]
    row[field]='ALTERED' if field=='mode' else row[field]+1
    raw=json.dumps(payload).encode();(study/'results.json').write_bytes(raw)
    er=json.loads((study/'evaluation-receipt.json').read_text())
    er['result_sha256']=hashlib.sha256(raw).hexdigest()
    (study/'evaluation-receipt.json').write_text(json.dumps(er))
    with pytest.raises(ValueError):archive.package_core_report(study,out,**kwargs)
    assert not out.exists()
