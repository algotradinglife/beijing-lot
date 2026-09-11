import copy
from pathlib import Path
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_updated_scope import audited_scope_market,prepare_updated_issue,updated_strategy_plans
from src.fundamentals_updated_freeze import freeze_updated_issue
from tests.test_fundamentals_clean_validation import sample


def test_audited_market_exact_keys_clocks_and_missing():
    f=[dict(issue='001',slot=1,provider_id='01')];cuts={'1':Cutoff.decision_epoch('001','2010-01-01T12:00:00Z')}
    records=[dict(**f[0],market=m,cutoff_utc=cuts['1'].cutoff_ts.isoformat(),historical_admission=False,
        status='QUOTES_PRIOR_DIAGNOSTIC',prior_companies=1,rows=[dict(company='C',quoted_at='2010-01-01T11:00:00Z',odds_W=2,odds_D=3,odds_L=4,line=2.5,over_hk=.9,under_hk=.9)]) for m in ('euro','total')]
    before=copy.deepcopy(records);kw=dict(cutoffs=cuts,source_hashes={'snapshot':'abc'})
    x=audited_scope_market(f,records,**kw)
    assert records==before and x['rows'][0]['odds_W']==2 and len(x['selected'])==1
    for altered in (records+records,records[:1]):
        with pytest.raises(ValueError):audited_scope_market(f,altered,**kw)
    changed=copy.deepcopy(records);changed[0]['rows'][0]['quoted_at']=cuts['1'].cutoff_ts.isoformat()
    with pytest.raises(ValueError):audited_scope_market(f,changed,**kw)
    changed=copy.deepcopy(records);changed[1].update(status='MISSING',rows=[],prior_companies=0)
    assert audited_scope_market(f,changed,**kw)['rows'][0]['status']=='AUDITED_MARKET_UNAVAILABLE'
    with pytest.raises(ValueError):audited_scope_market(f,records,cutoffs={},source_hashes={'x':'y'})


def test_prepare_adapter_excludes_ineligible_and_preserves_inputs(sample,monkeypatch):
    p,_,stamps=sample;f=p['fixtures'][0];p['clean']['integrated_fixtures'][0].update(integration_eligible=True,original_roster_status='完场',exclusion_reason=None)
    cuts={s:Cutoff.decision_epoch('100101',t) for s,t in stamps.items()};h=[dict(slot=1,provider_id='999',home_handicap=-2)]
    monkeypatch.setattr('src.fundamentals_updated_scope.read_response',lambda path:({'url':'x'},b'x'))
    monkeypatch.setattr('src.fundamentals_updated_scope.issue_analysis_pages',lambda *args,**kw:[f])
    monkeypatch.setattr('src.fundamentals_updated_scope.roster_handicaps',lambda *args,**kw:h)
    records=[dict(issue=f['issue'],slot=1,provider_id='999',market=m,cutoff_utc=stamps['1'],historical_admission=False,status='MISSING',rows=[],prior_companies=0) for m in ('euro','total')]
    report=dict(issue=f['issue'],clean=p['clean']);inv=dict(issue=f['issue'],cutoffs=stamps,roster_path='unused')
    kw=dict(cutoffs=cuts,source_hashes={'snapshot':'abc'},repository_root=Path(__file__).resolve().parents[1],window=10,minimum=10)
    before=copy.deepcopy(report);x=prepare_updated_issue(report,records,inv,**kw)
    assert report==before and x['forms']['windows'][0]['status']=='OK_DIAGNOSTIC'
    report['clean']['integrated_fixtures'][0].update(integration_eligible=False,exclusion_reason='ORIGINAL_NOT_COMPLETED')
    x=prepare_updated_issue(report,records,inv,**kw)
    assert x['forms']['windows'][0]['status']=='ANALYSIS_EXCLUDED:ORIGINAL_NOT_COMPLETED'
    assert x['forms']['windows'][0]['home_window']==[]
    with pytest.raises(ValueError):prepare_updated_issue(report,records,inv,**dict(kw,cutoffs={}))


def test_updated_plans_reuse_rules_cash_and_failures():
    rows=[dict(issue='001',slot=s,provider_id=str(s),handicap=1,p_W=.6,p_D=.3,p_L=.1,
        q_W=.7,q_D=.2 if s<7 else .1,q_L=.1 if s<7 else .2) for s in range(1,8)]
    frame=pd.DataFrame(rows);cuts={str(s):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for s in range(1,8)}
    kw=dict(cutoffs=cuts,seeds=[0,1],budget_cny=1024,unit_cny=2,payout_factor=.65)
    z=updated_strategy_plans(frame,**kw);assert len(z['plans'])==12
    for name,plan in z['plans'].items():
        assert plan['stake']<=1024 and plan['cash_cny']==1024-plan['stake']
        if name.startswith('MIX'):assert plan['stake']<=1024
        else:
            for part in plan['components']:assert sum(len(l['support'])==1 for l in part['legs'])==2
    assert z['plans']['N5_NO_SWAP']['components'][0]['tickets']==z['plans']['N5_S000']['components'][0]['tickets']
    with pytest.raises(ValueError):updated_strategy_plans(frame,**dict(kw,seeds=[0,0]))
    with pytest.raises(ValueError):updated_strategy_plans(frame,**dict(kw,cutoffs={}))
    empty=frame.copy();empty['handicap']=0;empty['q_D']=.1;empty['q_L']=.2
    with pytest.raises(ValueError,match='No retained'):updated_strategy_plans(empty,**kw)


def test_immutable_freeze_empty(tmp_path):
    import gzip,json,hashlib
    path=tmp_path/'issue.json.gz';kw=dict(cutoffs={},seeds=[0],budget_cny=1024,unit_cny=2,payout_factor=.65,output_path=path)
    z=freeze_updated_issue(pd.DataFrame(),**kw)
    assert z['policies']==0 and z['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert json.loads(gzip.decompress(path.read_bytes()))['exclusions']['reason']=='NO_READY_FACTORS'
    with pytest.raises(FileExistsError):freeze_updated_issue(pd.DataFrame(),**kw)
    with pytest.raises(ValueError):freeze_updated_issue(pd.DataFrame(),**dict(kw,cutoffs={'1':'bad'},output_path=tmp_path/'bad.gz'))


def test_independent_checker_accepts_unused_missing_sp(tmp_path):
    import gzip,itertools,json,subprocess,sys
    from src.temporal_learning.core import stable_json_hash
    legs=[dict(issue='new',slot=s,provider_id=str(s),support='3' if s<3 else '31') for s in range(1,6)]
    part=dict(legs=legs,stake=16,tickets=[dict(code=''.join(c),units=1) for c in itertools.product(*(l['support'] for l in legs))]);part['seal']=stable_json_hash(part)
    plan=dict(components=[part],stake=16);plan['seal']=stable_json_hash(plan)
    (tmp_path/'plans').mkdir();(tmp_path/'plans/new.json.gz').write_bytes(gzip.compress(json.dumps(dict(plans={'N5_NO_SWAP':plan})).encode()))
    rows=[dict(issue=i,policy='N5_NO_SWAP',groups=1,hits=0,stake=16,gross=0,net=-16) for i in ('old','new')]
    (tmp_path/'results.json').write_text(json.dumps(dict(rows=rows[1:],prior_rows=rows[:1],issue_order=['new'],prior_issue_order=['old'])))
    audit=[dict(issue='new',slot=s,provider_id=str(s),actual_direction='L' if s==1 else 'W',status='spf:MISSING_WINNING_SP' if s==1 else 'READY',spf_sp=None if s==1 else 2) for s in range(1,6)]
    (tmp_path/'settlement-audit.json').write_text(json.dumps(dict(rows=audit)))
    pd.DataFrame([dict(cohort=c,policy='N5_NO_SWAP',stake=16*n,net=-16*n,ROI_percent=-100,max_drawdown=16*n) for c,n in [('原48期',1),('新增100期',1),('合计148期',2)]]).to_csv(tmp_path/'metrics.csv',index=False)
    pd.DataFrame([dict(issue=i,policy='N5_NO_SWAP',period=n,equity_cny=100000-16*n,drawdown_cny=16*n) for n,i in enumerate(['initial','old','new'])]).to_csv(tmp_path/'curves.csv',index=False)
    root=Path(__file__).resolve().parents[1]
    z=subprocess.run([sys.executable,str(root/'scripts/check_updated_strategies.py'),'--study',str(tmp_path)],capture_output=True,text=True)
    assert z.returncode==0,z.stderr
