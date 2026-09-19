import json
from pathlib import Path
import pandas as pd
import pytest
import subprocess
import shutil
from src.n7_risk_context import n7_risk_context, n7_risk_contexts_json
from src.temporal_learning.core import Cutoff, TemporalContractError

ROOT=Path(__file__).resolve().parents[1]

def test_context_excludes_future_target_and_binds_weights():
    h=pd.DataFrame([dict(issue_code=str(i),last_fixture_cutoff=f'2010-01-{i:02d}T00:00:00Z',
        hit_residual=.1,depth_residual=.05) for i in range(1,10)])
    kw=dict(repository_root=ROOT,source_hashes={'fixture':'a'*64},delay_hours=48,
        window_issues=3,recent_blend=.8,minimum_ess=2)
    cut=Cutoff.decision_epoch('9','2010-01-08T00:00:00Z')
    c=n7_risk_context(h,cut,**kw)
    assert c['status']=='READY'
    assert [r['issue_code'] for r in c['rows']]==['1','2','3','4','5']
    assert sum(r['weight'] for r in c['rows'])==pytest.approx(1)
    assert c['receipt']['weight_receipt']['recent_state_mass']==pytest.approx(.8)
    precise=n7_risk_context(h,Cutoff.decision_epoch('9','2010-01-10T00:00:00Z'),**kw)
    assert sum(r['long_mass'] for r in precise['receipt']['full_weight_ledger'])==pytest.approx(.2,abs=1e-12,rel=0)
    changed=h.copy();changed.loc[changed.issue_code.isin(['6','7','8','9']),['hit_residual','depth_residual']]=-.9
    assert n7_risk_context(changed,cut,**kw)['rows']==c['rows']
    changed.loc[changed.issue_code=='9','last_fixture_cutoff']='2010-01-01T00:00:00Z'
    assert n7_risk_context(changed,cut,**kw)['rows']==c['rows']
    assert n7_risk_context(h,Cutoff.decision_epoch('2','2010-01-02T00:00:00Z'),**kw)['status']=='WARMUP'
    assert n7_risk_context(h,cut,**dict(kw,minimum_ess=100))['status']=='WARMUP'
    with pytest.raises(TemporalContractError):n7_risk_context(h,None,**kw)
    bad=h.copy();bad.loc[0,'last_fixture_cutoff']=None
    with pytest.raises(ValueError):n7_risk_context(bad,cut,**kw)
    with pytest.raises(ValueError):n7_risk_context(pd.concat([h,h]),cut,**kw)
    targets=[dict(issue_code='9',fixture_decision_ts='2010-01-08T00:00:00Z'),
             dict(issue_code='2',fixture_decision_ts='2010-01-02T00:00:00Z')]
    args=dict(kw);args['source_hashes_json']=json.dumps(args.pop('source_hashes'))
    out=json.loads(n7_risk_contexts_json(h.to_json(orient='records'),json.dumps(targets),**args))
    assert [r['receipt']['target_issue'] for r in out]==['2','9']
    assert out[1]['rows']==c['rows']


def test_mutation_replay_through_R_states_budgets_prefixes_and_cash(tmp_path):
    h=pd.DataFrame([dict(issue_code=str(i),last_fixture_cutoff=f'2010-01-{i:02d}T00:00:00Z',
        hit_residual=-.1,depth_residual=-.1) for i in range(1,26)])
    kw=dict(repository_root=ROOT,source_hashes={'fixture':'a'*64},delay_hours=48,
        window_issues=3,recent_blend=.8,minimum_ess=2)
    targets=[dict(issue_code=i,fixture_decision_ts=t) for i,t in [
        ('16','2010-01-16T06:00:00Z'),('17','2010-01-17T06:00:00Z'),
        ('18','2010-01-17T07:00:00Z'),('19','2010-01-19T06:00:00Z')]]
    args=dict(kw);args['source_hashes_json']=json.dumps(args.pop('source_hashes'))
    base=json.loads(n7_risk_contexts_json(h.to_json(orient='records'),json.dumps(targets),**args))
    assert base[1]['history_identity']==base[2]['history_identity']
    changed=h.copy();changed.loc[changed.issue_code.astype(int)>=19,['hit_residual','depth_residual']]=.9
    future=json.loads(n7_risk_contexts_json(changed.to_json(orient='records'),json.dumps(targets),**args))
    changed.loc[changed.issue_code=='19','last_fixture_cutoff']='2010-01-01T00:00:00Z'
    target=[*base[:-1],n7_risk_context(changed,Cutoff.decision_epoch('19',targets[-1]['fixture_decision_ts']),**kw)]
    script=tmp_path/'replay.R'
    script.write_text("""args<-commandArgs(trailingOnly=TRUE)
source(file.path(args[1],'r/n7_risk_monitor.R'))
source(file.path(args[1],'r/n7_budget_policy.R'))
source(file.path(args[1],'r/n7_core_opportunity.R'))
source(file.path(args[1],'r/n7_capital_portfolio.R'))
cs<-jsonlite::fromJSON(args[2],simplifyVector=FALSE);prev<-NULL;rows<-list()
g<-data.frame(sleeve_id=c('a','b','c'),depth=c(200,150,100),stake=c(400,300,200),coverage=c(.25,.26,.27))
for(ct in cs) {
 ct$rows<-dplyr::bind_rows(ct$rows)
 z<-n7_risk_state(ct,prev,ct$receipt$cutoff_identity,-.05,0,2,3)
 budget<-switch(z$state,WARMUP=0,NORMAL=1024,DEFENSIVE=512,RECOVERING=768)
 cut<-list(fixture=ct$receipt$cutoff_ts)
 pool<-list(issue=ct$receipt$target_issue,cutoffs=cut,mode='BREADTH',opening_options=1:3,
 opportunity_options=integer(),options=lapply(1:3,function(i)list(sleeve_id=as.numeric(i),
 depth=g$depth[i],stake=g$stake[i],expected_gross=200,unit_copies=1,coverage=g$coverage[i],fixtures=i:(i+6))))
 sc<-list(cutoffs=cut,hits=diag(3),gross=diag(3)*600)
 expansions<-list()
 for(kind in c('FIXED','DYNAMIC'))for(cap in c(1024,1536,2048)) {
  e<-n7_budget_policy(pool,sc,cut,ct,z,kind,cap,512,768,2,256,Sys.getenv('RETICULATE_PYTHON'))
  expansions[[paste(kind,cap)]]<-list(selected=e$selected,limit=e$risk_limit,stake=e$metrics$stake,cash=e$metrics$cash)
 }
 for(mode in c('ORIGINAL','HIGH')) {
  f<-n7_risk_fund(g,budget,mode,2,ct$receipt,ct$receipt$cutoff_identity)
  rows[[length(rows)+1L]]<-list(state=z,budget=budget,mode=mode,expansions=expansions,tickets=f$groups,stake=f$stake,cash=f$cash)
 }
 prev<-z
}
jsonlite::write_json(rows,args[3],auto_unbox=TRUE,digits=NA)
""")
    outputs=[]
    for name,contexts in [('base',base),('future',future),('target',target)]:
        inp=tmp_path/f'{name}.json';out=tmp_path/f'{name}-result.json'
        inp.write_text(json.dumps(contexts))
        subprocess.run([shutil.which('Rscript'),str(script),str(ROOT),str(inp),str(out)],check=True,capture_output=True,text=True)
        outputs.append(json.loads(out.read_text()))
    assert outputs[0]==outputs[1]==outputs[2]
    assert outputs[0][0]['budget']==1024
    assert outputs[0][2]['budget']==512
    assert outputs[0][2]['state']['bad']==outputs[0][4]['state']['bad']
    assert outputs[0][2]['tickets']!=outputs[0][3]['tickets']
