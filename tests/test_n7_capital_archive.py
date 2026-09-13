"""Portable archive I/O contracts; numerical replay has independent tests."""
import gzip
import hashlib
import json
from pathlib import Path
import pytest
import src.n7_capital_archive as archive
from src.temporal_learning.core import stable_json_hash

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def completed_cash_study(tmp_path,monkeypatch):
    study=tmp_path/'study';study.mkdir()
    p=dict(issue='001',seed=1,arm='CASH',model_id='unit-test',sleeve_keys=[],fixtures=[],
        stake=0,groups=0,budget_cny=512,unit_cny=2,payout_factor=.65,solver_status='Infeasible',solver={})
    p['seal']=stable_json_hash(p)
    pp=study/'plan.json.gz';pp.write_bytes(gzip.compress(json.dumps(p).encode()))
    rp=study/'001.json.gz';rp.write_bytes(gzip.compress(json.dumps(dict(curves=[dict(depth=0)])).encode()))
    receipt=dict(issues=['001'],parameters=dict(seeds=[1],budgets=[512]),cutoffs={'001':{'1':'2010-01-01'}},
        plan_hashes={str(pp):hashlib.sha256(pp.read_bytes()).hexdigest()},
        raw_hashes={str(rp):hashlib.sha256(rp.read_bytes()).hexdigest()})
    frozen=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (study/'plans-frozen.json').write_text(json.dumps(frozen))
    row=dict(issue='001',seed=1,arm='CASH',reference=False,stake=0,groups=0,hits=0,gross=0,net=0,roi=None,status='NO_BET')
    (study/'results.json').write_text(json.dumps(dict(rows=[row],issue_order=['001'],freeze_seal=frozen['seal'],historical_admission=False)))
    (study/'audit-snapshot.json').write_text(json.dumps(dict(rows=[])))
    er={f'{key}_sha256':hashlib.sha256((study/path).read_bytes()).hexdigest()
        for key,path in [('freeze','plans-frozen.json'),('result','results.json'),('audit','audit-snapshot.json')]}
    (study/'evaluation-receipt.json').write_text(json.dumps(er))
    # This test isolates packaging; the real common checker is exercised by
    # test_n7_joint_check and the capital arithmetic tests, and by full replay.
    monkeypatch.setattr(archive,'check_prefix_study',lambda *a,**kw:dict(status='PASS',plans_checked=1))
    return study,tmp_path/'report.json.gz'


def test_portable_package_binds_body_parameters_and_refuses_overwrite(completed_cash_study):
    study,out=completed_cash_study
    result=archive.package_capital_report(study,out,repository_root=ROOT,example_issue='001')
    wrapper=json.loads(gzip.decompress(out.read_bytes()));body=json.loads(wrapper['body'])
    assert hashlib.sha256(wrapper['body'].encode()).hexdigest()==wrapper['sha256']==result['sha256']
    assert body['parameters']['budgets']==[512] and body['settlement_replay']['plans_checked']==1
    assert body['sleeves']==[] and body['example_issue']=='001'
    with pytest.raises(ValueError,match='overwrite'):
        archive.package_capital_report(study,out,repository_root=ROOT,example_issue='001')


def test_changed_results_or_failed_replay_cannot_create_archive(completed_cash_study,monkeypatch):
    study,out=completed_cash_study
    original=(study/'results.json').read_bytes();(study/'results.json').write_bytes(original+b' ')
    with pytest.raises(ValueError,match='result binding'):
        archive.package_capital_report(study,out,repository_root=ROOT,example_issue='001')
    assert not out.exists()
    (study/'results.json').write_bytes(original)
    with pytest.raises(ValueError,match='Unknown curve'):
        archive.package_capital_report(study,out,repository_root=ROOT,example_issue='002')
    def fail(*args,**kwargs):raise ValueError('Independent replay failed')
    monkeypatch.setattr(archive,'check_prefix_study',fail)
    with pytest.raises(ValueError,match='Independent replay'):
        archive.package_capital_report(study,out,repository_root=ROOT,example_issue='001')
    assert not out.exists()
