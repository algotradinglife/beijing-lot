# Independent post-settlement verification of incremental six-policy ledgers.
# CLI config is the same explicit JSON used by Quarto 222. No policy selection
# or output data is changed; only a new verification receipt is written.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1],simplifyVector=FALSE);root<-cfg$repository_root
library(dplyr);library(readr);library(jsonlite)
for(f in c('n7_sleeve_tables','joint_grid_monitor','joint_win_scale','joint_selective_add'))source(file.path(root,'r',paste0(f,'.R')))
reticulate::use_python(cfg$python,required=TRUE)
reader<-reticulate::import('src.strategy_diagnostic_inputs',convert=TRUE)
risk<-reticulate::import('src.n7_risk_context',convert=TRUE)
strat<-reticulate::import('src.temporal_learning.stratified',convert=TRUE)
rec<-fromJSON(file.path(cfg$output,'receipt.json'),simplifyVector=FALSE)
for(n in names(rec$files))stopifnot(digest::digest(file=file.path(cfg$output,n),algo='sha256')==rec$files[[n]])
h<-read_csv(file.path(cfg$output,'grid-history.csv'),col_types=cols(issue_code='c'))
clocks<-list();fr<-fromJSON(cfg$old_freeze,simplifyVector=FALSE)
for(p in names(fr$receipt$plan_hashes)) {
 b<-fromJSON(reader$read_verified_bundle_json(p,fr$receipt$plan_hashes[[p]]),simplifyVector=FALSE)
 clocks[[b$issue]]<-tibble(issue_code=b$issue,last_fixture_cutoff=max(unlist(b$cutoffs)))
}
plans<-list();bundles<-list()
for(p in names(rec$plans)) {
 stopifnot(digest::digest(file=p,algo='sha256')==rec$plans[[p]])
 plan<-fromJSON(p,simplifyVector=FALSE);job<-plan$source_bundle[[1]]
 b<-fromJSON(reader$read_verified_bundle_json(job$path,job$sha256),simplifyVector=FALSE)
 clocks[[b$issue]]<-tibble(issue_code=b$issue,last_fixture_cutoff=max(unlist(b$cutoffs)))
 plans[[b$issue]]<-plan;bundles[[b$issue]]<-b
}
residual<-h |> group_by(issue_code) |> summarise(hit_residual=sum(hits-expected)/sum(stake/2),.groups='drop')
history<-bind_rows(clocks) |> left_join(residual,by='issue_code',relationship='one-to-one') |> mutate(hit_residual=tidyr::replace_na(hit_residual,0),depth_residual=hit_residual)
rows<-list();checked<-0L
for(id in names(plans)) {
 p<-plans[[id]];b<-bundles[[id]];t<-bind_rows(p$tickets)
 if(!nrow(t))t<-tibble(issue=character(),sleeve_id=integer(),ticket_col_idx=integer(),ticket_id=character(),prob=double(),payout_hat=double(),prob_rank=integer(),cell=character(),base_copies=integer())
 cp<-file.path(cfg$output,paste0(id,'-context.json'))
 stopifnot(digest::digest(file=cp,algo='sha256')==p$context_sha256)
 ct<-fromJSON(cp,simplifyVector=FALSE)[[1]]
 # Decision ordering must use exact source doubles: JSON report decimals can
 # perturb near-equal EV products. Verify the display values, then restore the
 # authoritative, hash-bound enumeration probabilities/prices.
 v<-n7_sleeve_tables(b,b$cutoffs,cfg$original_settings$model_id)
 if(nrow(t)) {
  ix<-cbind(match(as.character(t$sleeve_id),rownames(v$prob_mat)),t$ticket_col_idx)
  stopifnot(all(is.finite(t$prob)),all(is.finite(t$payout_hat)),
   all(abs(t$prob-as.numeric(v$prob_mat[ix]))<=32*.Machine$double.eps*pmax(1,abs(as.numeric(v$prob_mat[ix])))),
   all(abs(t$payout_hat-as.numeric(v$payout_hat_mat[ix]))<=32*.Machine$double.eps*pmax(1,abs(as.numeric(v$payout_hat_mat[ix])))))
  t$prob<-as.numeric(v$prob_mat[ix]);t$payout_hat<-as.numeric(v$payout_hat_mat[ix])
 }
 target<-tibble(issue_code=id,fixture_decision_ts=min(unlist(b$cutoffs)))
 raw<-risk$n7_risk_contexts_json(toJSON(history,dataframe='rows',auto_unbox=TRUE),toJSON(target,dataframe='rows',auto_unbox=TRUE),repository_root=root,source_hashes_json=toJSON(ct$receipt$source_hashes,auto_unbox=TRUE),delay_hours=48,window_issues=20L,recent_blend=.5,minimum_ess=20)
 fullct<-fromJSON(strat$stratified_contexts_json(raw,toJSON(h |> select(issue_code,cell),dataframe='rows',auto_unbox=TRUE),minimum_ess=20,minimum_recent_ess=5),simplifyVector=FALSE)[[1]]
 # Future rows added after the original run must leave forecast values unchanged.
 f<-joint_grid_monitor(h,fullct,fullct$receipt,30,10,.8,1)
 original<-joint_grid_monitor(h,ct,ct$receipt,30,10,.8,1)
 stopifnot(isTRUE(all.equal(as.data.frame(f),as.data.frame(original),check.attributes=FALSE,tolerance=1e-12)))
 base<-joint_grid_allocate(t,original,ct$receipt,'long_hit_signal',2,1024)
 stopifnot(identical(as.integer(pmin(base$copies,1)),as.integer(t$base_copies)))
 s<-original;s$issue<-rep(id,nrow(s));attr(s,'signal_receipt')<-NULL
 attr(s,'input_receipt')<-list(cutoff=p$cutoff,hash=digest::digest(s,algo='sha256'))
 members<-bind_rows(lapply(b$sleeves,function(g)tibble(sleeve_id=g$id,fixture=as.character(unlist(g$fixture_indices)))))
 audit<-fromJSON(file.path(cfg$output,paste0(id,'-audit.json')))$fixtures
 returns<-numeric(nrow(t))
 for(g in b$sleeves) {
  fs<-bind_rows(b$expanded_pool$fixtures[as.integer(unlist(g$fixture_indices))+1L])
  aa<-left_join(fs |> select(issue,slot,provider_id),audit,by=c('issue','slot','provider_id'),relationship='one-to-one')
  stopifnot(nrow(aa)==7,!anyNA(aa$actual_direction),all(is.finite(aa$spf_sp)),all(aa$spf_sp>0))
  state<-1L+sum((match(aa$actual_direction,c('W','D','L'))-1L)*3^(6:0))
  ix<-which(t$sleeve_id==g$id & t$ticket_col_idx==state)
  returns[ix]<-2*.65*prod(aa$spf_sp)
 }
 for(policy in names(p$plans)) {
  a<-bind_rows(p$plans[[policy]])
  if(!nrow(a))a<-tibble(ticket_id=character(),copies=integer())
  copies<-a$copies[match(t$ticket_id,a$ticket_id)]
  if(policy!='BASE') {
   expected<-joint_selective_replay(t,members,s,p$cutoff,p$context_sha256,policy,cfg$add_settings)
   if(!identical(as.integer(copies),expected)) {print(list(issue=id,policy=policy,changed=which(copies!=expected)));print(t[which(copies!=expected),]);stop('Persisted selective replay differs')}
  }
  else stopifnot(identical(as.integer(copies),as.integer(t$base_copies)))
  rows[[paste(id,policy)]]<-tibble(issue=id,policy,stake=sum(copies*2),gross=sum(copies*returns),hits=sum(copies*(returns>0)))
 }
 checked<-checked+1L;message('Independent history/allocation/settlement ',checked,'/50')
}
observed<-read_csv(file.path(cfg$output,'new-rows.csv'),col_types=cols(issue='c'))
z<-left_join(bind_rows(rows),observed,by=c('issue','policy'),suffix=c('_replay',''),relationship='one-to-one')
stopifnot(nrow(z)==300,all(abs(z$stake_replay-z$stake)<1e-9),all(abs(z$gross_replay-z$gross)<1e-7),all(z$hits_replay==z$hits))
write_json(list(status='PASS',issues=checked,policy_rows=nrow(z),future_history_invariance=checked,base_replays=checked,selective_replays=checked*5,independent_official_settlement=TRUE,source_receipt_sha256=digest::digest(file=file.path(cfg$output,'receipt.json'),algo='sha256'),implementation_sha256=digest::digest(file=file.path(root,'scripts/check_joint_extension_replay.R'),algo='sha256')),file.path(cfg$output,'independent-replay.json'),auto_unbox=TRUE,pretty=TRUE)
