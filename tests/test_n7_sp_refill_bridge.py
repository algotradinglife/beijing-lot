"""Exercise real Python enumeration -> R refill -> existing capital allocation."""
import json
import os
import subprocess
from pathlib import Path
import pandas as pd
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.n7_sleeve_states import enumerate_sleeve


def test_refill_bridge_and_allocator(tmp_path):
    fixtures=[dict(issue='001',slot=i,provider_id=str(i),handicap=0,
                   p_W=.6,p_D=.3,p_L=.1,q_W=.6,q_D=.3,q_L=.1) for i in range(9)]
    fixtures[-1].update(p_W=.9,p_D=.05,p_L=.05,q_W=.9,q_D=.05,q_L=.05)
    native={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in range(9)}
    sleeves=[]
    for gid,indices in enumerate([list(range(7)),list(range(2,9))]):
        e=enumerate_sleeve(pd.DataFrame([fixtures[i] for i in indices]),
            cutoffs={str(i):native[str(i)] for i in indices},unit_cny=2,payout_factor=.65)
        sleeves.append(dict(id=gid,fixture_indices=indices,origin='TEST',enumeration=e,options={}))
    cuts={str(i):next(iter(sleeves[0]['enumeration']['cutoffs'].values())) for i in range(9)}
    b=dict(issue='001',cutoffs=cuts,historical_admission=False,sleeves=sleeves,
        expanded_pool=dict(fixtures=fixtures,encoded_tickets=[[3*i for i in range(7)]],minimum_scalar_rank=[1]))
    b['seal']=stable_json_hash(b)
    path=tmp_path/'bundle.json';path.write_text(json.dumps(b))
    mutated=dict(b)
    mutated.pop('seal')
    mutated['post_cutoff_labels']={'001':{'actual_direction':'L','spf_sp':999}}
    mutated['future_issue_results']={'999':{'winner':'changed'}}
    mutated['seal']=stable_json_hash(mutated)
    changed_path=tmp_path/'post-cutoff-mutation.json';changed_path.write_text(json.dumps(mutated))
    script=tmp_path/'run.R'
    script.write_text('''
args<-commandArgs(TRUE)
for(f in c('n7_sleeve_tables','n7_joint_sleeves','n7_capital_depth','n7_capital_portfolio',
 'n7_core_opportunity','n7_sweet_union','n7_funding_modes','n7_sp_filter','n7_sp_refill','n7_sp_refill_prepare','n7_sp_refill_plans',
 'n7_residual_refill','n7_residual_plans'))source(paste0('r/',f,'.R'))
raw<-paste(readLines(args[1],warn=FALSE),collapse='\\n')
cuts<-jsonlite::fromJSON(raw,simplifyVector=FALSE)$cutoffs
p<-n7_sp_refill_prepare(raw,cuts,args[2],'fixed',1.3,2,11,100,c(15,32,64),c(.25,.3),.25,256,2,.65,7)
stopifnot(!p$unchanged,p$refill$actual==2,all(vapply(p$base$options,function(o)!9 %in% o$fixtures,logical(1))))
w<-n7_joint_worlds(p$base,cuts,11,32)
a<-n7_funding_allocate(p$base,p$partition,cuts,'DEPTH',w,128,256,1,'expected_net','OPEN_FIRST')
e<-n7_capital_evaluate(a$pool,a$fit$selected,a$scenarios,cuts,128)
stopifnot(e$stake<=128,e$cash+e$stake==128,is.finite(e$expected_net))
all<-n7_sp_refill_prepare(raw,cuts,args[2],'fixed',1,2,11,100,c(15,32,64),c(.25,.3),.25,256,2,.65,7)
stopifnot(all$unchanged,identical(all$bundle_json,raw))
original_depths<-sort(unique(vapply(all$base$options,function(o)o$depth,numeric(1))))
retained<-Filter(function(o)o$sleeve_id==0,p$base$options)
stopifnot(identical(sort(vapply(retained,function(o)o$depth,numeric(1))),original_depths),
 identical(p$refill$original_depth_grid,all$refill$original_depth_grid))
none<-n7_sp_refill_prepare(raw,cuts,args[2],'fixed',20,2,11,100,c(15,32,64),c(.25,.3),.25,256,2,.65,7)
stopifnot(length(none$partition$core_ids)==0,none$refill$actual==0)
cfg<-list(unit_cny=2,payout_factor=.65,max_copies=1,policies=data.frame(id='EXPECTED',mode='DEPTH',objective='expected_net',allocation_order='OPEN_FIRST'),budgets=c(64,128),allocation_worlds=32,evaluation_worlds=64,evaluation_seed_offset=1000,max_actions=256,target=.25,minimum_sp=1.3)
plans<-n7_sp_refill_plans(p,cuts,cfg,11)
stopifnot(nrow(plans$rows)==2,length(plans$plans)==2,
 all(plans$rows$stake+plans$rows$cash==cfg$budgets),
 all(vapply(plans$plans,function(x)x$groups*2==x$stake,logical(1))))
cash<-n7_sp_refill_plans(none,cuts,cfg,11)
stopifnot(all(cash$rows$stake==0),all(cash$rows$cash==cfg$budgets))
changed<-paste(readLines(args[3],warn=FALSE),collapse='\\n')
changed_pool<-n7_sp_refill_prepare(changed,cuts,args[2],'fixed',1.3,2,11,100,c(15,32,64),c(.25,.3),.25,256,2,.65,7)
changed_plans<-n7_sp_refill_plans(changed_pool,cuts,cfg,11)
stopifnot(identical(p$refill,changed_pool$refill),identical(plans,changed_plans))
cfg$python<-args[2];cfg$model_id<-'fixed'
funded<-data.frame(issue='001',seed=11,arm=paste0('T250_SP130_EXPECTED_B',cfg$budgets),
 sleeve_id='0',depth=15,copies=1,stake=30)
residual<-n7_residual_plans(p$bundle_json,p$refill,funded,cuts,cfg,11)
stopifnot(length(residual$plans)==6,all(residual$rows$stake>=30),
 all(residual$rows$stake<=residual$rows$budget_cny),
 all(vapply(residual$plans,function(x)0 %in% x$locked_sleeve_ids,logical(1))))
packed<-jsonlite::fromJSON(jsonlite::toJSON(residual$plans,auto_unbox=TRUE,digits=NA),simplifyVector=FALSE)
stopifnot(all(vapply(packed,function(x)is.list(x$locked_sleeve_ids),logical(1))))
stopifnot(identical(residual,n7_residual_plans(changed_pool$bundle_json,changed_pool$refill,funded,cuts,cfg,11)))
cat('BRIDGE_PASS')
''')
    import sys
    run=subprocess.run([os.environ.get('RSCRIPT','Rscript'),str(script),str(path),sys.executable,str(changed_path)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=120)
    assert run.returncode==0,run.stdout+run.stderr
    assert 'BRIDGE_PASS' in run.stdout
