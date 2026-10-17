# Rscript r/fm171_26103_native_freeze.R ROOT [replay|pilot]
# Target labels/SP do not enter native fitting, reliability/source or tail review.
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);setwd(root)
mode<-if(length(args)>1L)args[2]else'freeze'
replay<-mode%in%c('replay','replay-shard');pilot<-mode=='pilot';sharded<-mode%in%c('shard','replay-shard')
if(sharded) {
 stopifnot(length(args)==4L);shard_index<-as.integer(args[3]);shard_count<-as.integer(args[4])
 stopifnot(!anyNA(c(shard_index,shard_count)),shard_index>=1L,shard_index<=shard_count,shard_count<=4L)
}
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,'r_lib'))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
invisible(beidan::python_backend(file.path(root,'.venv/bin/python')))
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
backend<-reticulate::import('beidan_backend.opponent_goals',convert=FALSE)
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
adjustment<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
out<-file.path(root,'results/fm171-26103-draw-20261017')
ns<-new.env(parent=asNamespace('beidan'));sys.source(file.path(root,'packages/beidan/R/opponent_goals.R'),ns)
policy<-jsonlite::fromJSON('config/fundamental-models/FM-1.7.1.json');runtime<-jsonlite::fromJSON('config/fm17_opponent_lambda_runtime.json')
stopifnot(!policy$native_policy$opponent_strength_normalization,policy$native_policy$alpha==.5)
stopifnot(runtime$native_policy$recent_n==policy$native_policy$recent_n,
 runtime$native_policy$minimum_recent_matches==policy$native_policy$minimum_recent_matches,
 runtime$native_policy$minimum_recent_ess==policy$native_policy$minimum_recent_ess,
 runtime$fit_policy$minimum_target_matches==policy$native_policy$minimum_recent_matches)
inputs<-jsonlite::fromJSON(file.path(out,'inputs.json'),simplifyVector=FALSE)
metadata<-jsonlite::fromJSON(file.path(out,'metadata.json'),simplifyVector=FALSE)
stopifnot(metadata$network_attempts==0,metadata$input_sha256==digest::digest(file=file.path(out,'inputs.json'),algo='sha256'))
shared$verify_implementation_closure(reticulate::import('pathlib',convert=FALSE)$Path(root),metadata$implementation)
market_manifest<-jsonlite::fromJSON(file.path(out,'market-manifest.json'))
stopifnot(digest::digest(file=file.path(out,'market-stage.rds'),algo='sha256')==market_manifest$sha256)
markets<-readRDS(file.path(out,'market-stage.rds'))
fixtures<-bind_rows(inputs$fixtures);history<-bind_rows(inputs$history)
contexts<-bind_rows(inputs$contexts) |> mutate(kickoff_at=lubridate::ymd_hms(kickoff_at,tz='UTC'))
fixture_schedule<-readRDS(file.path(out,'fundamentals.rds'))$fixture_schedule
meta_rows<-map_dfr(keep(metadata$packets,~.x$state=='PARSED'),function(p) {
 bind_rows(p$result$rows) |> transmute(fixture_id=p$fixture_id,scope=recode(block,h_data='home_recent',a_data='away_recent',v_data='head_to_head'),
  match_id=history_id,metadata_date=event_date,metadata_home_id=home_id,metadata_away_id=away_id,
  metadata_home_score=home_score,metadata_away_score=away_score,competition_id,neutral_reported)
})
stopifnot(!anyDuplicated(meta_rows[c('fixture_id','scope','match_id')]))
enriched<-history |> left_join(meta_rows,by=c('fixture_id','scope','match_id'),relationship='one-to-one') |>
 mutate(metadata_agrees=!is.na(competition_id)&event_date==metadata_date&home_id==metadata_home_id&away_id==metadata_away_id&home_score==metadata_home_score&away_score==metadata_away_score)
ex<-jsonlite::fromJSON(file.path(out,'exclusion-rosters.json'),simplifyVector=FALSE)
excluded<-unique(unlist(map(ex,~map_chr(.x$rows,function(z)z$native_id %||% z$provider_id_nowscore))))
stopifnot(all(fixtures$provider_id%in%excluded))
bindings<-list(inputs=digest::digest(file=file.path(out,'inputs.json'),algo='sha256'),metadata=digest::digest(file=file.path(out,'metadata.json'),algo='sha256'),
 fundamentals_snapshot=digest::digest(file=file.path(out,'fundamentals.rds'),algo='sha256'),
 policy=digest::digest(file='config/fundamental-models/FM-1.7.1.json',algo='sha256'),study=digest::digest(file='config/fm171_26103_draw_study.json',algo='sha256'),
 client=digest::digest(file='r/fm171_26103_native_freeze.R',algo='sha256'),fit_R=digest::digest(file='packages/beidan/R/opponent_goals.R',algo='sha256'),
 runtime=digest::digest(file='config/fm17_opponent_lambda_runtime.json',algo='sha256'),exclusions=digest::digest(file=file.path(out,'exclusion-rosters.json'),algo='sha256'),
 market_stage=market_manifest$sha256,
 direction_implementation=beidan:::.score_margin_code(root))
entries<-audit<-probabilities<-list();existing<-if(replay)readRDS(file.path(out,'native-forecasts.rds'))else NULL
scope<-fixtures$fixture_id;if(pilot)scope<-head(scope,2)
if(sharded)scope<-scope[(seq_along(scope)-1L)%%shard_count==shard_index-1L]
dir.create(file.path(out,'entry-cache'),showWarnings=FALSE)
for(id in scope) {
 if(match(id,scope)%%10L==0L)message('Attempt ',match(id,scope),'/',length(scope),' estimated ',length(entries))
 cache_path<-file.path(out,'entry-cache',paste0(gsub(':','-',id),'.rds'))
 if(!replay&&!pilot&&file.exists(cache_path)) {
  cached<-readRDS(cache_path);stopifnot(identical(cached$bindings,bindings))
  if(!is.null(cached$entry))entries[[id]]<-cached$entry
  audit[[id]]<-cached$row
  for(k in names(cached$probabilities))probabilities[[k]]<-cached$probabilities[[k]]
  next
 }
 f<-fixtures |> filter(fixture_id==id);packet<-keep(metadata$packets,~.x$fixture_id==id&&.x$state=='PARSED')
 row<-tibble(fixture_id=id,slot=f$slot,home=f$home,away=f$away,league=f$league,handicap=f$handicap,
  cutoff_utc=f$cutoff_utc,state='UNESTIMATED',reason='',confidence='uncertain',market_sufficient=FALSE,
  market_consistent=FALSE,market_gap='No admitted same-cutoff Asian/totals channel',lambda_home=NA_real_,lambda_away=NA_real_,
  competition_id=NA_character_,fit_rows=NA_integer_,metadata_missing=sum(!enriched$metadata_agrees),selected_source=NA_character_,
  native_lambda_home=NA_real_,native_lambda_away=NA_real_)
 if(length(packet)!=1L||is.null(packet[[1]]$result$target_competition_id)) {
  row$reason<-'Absent/ambiguous source title competition identity';audit[[id]]<-row
  if(!replay&&!pilot)saveRDS(list(entry=NULL,row=row,bindings=bindings,probabilities=list()),cache_path)
  next
 }
 tm<-packet[[1]]$result
 # Three clocks must agree: roster wall clock, factual analysis, and market page clock.
 clock<-contexts |> filter(fixture_id==id)
 roster_clock<-fixture_schedule |>
  filter(fixture_id==id,resource=='roster')
 roster_kickoff<-lubridate::ymd_hms(paste(roster_clock$kickoff_date,roster_clock$kickoff_hhmm,'00'),tz='Asia/Shanghai',quiet=TRUE)
 actual_kickoff<-lubridate::ymd_hms(f$kickoff_at,tz='UTC')
 if(nrow(clock)!=2L||anyNA(clock$kickoff_at)||any(clock$kickoff_at!=actual_kickoff)||
    length(roster_kickoff)!=1L||is.na(roster_kickoff)||roster_kickoff!=actual_kickoff) {
  row$reason<-'Unresolved roster/analysis/market kickoff disagreement';audit[[id]]<-row
  if(!replay&&!pilot)saveRDS(list(entry=NULL,row=row,bindings=bindings,probabilities=list()),cache_path)
  next
 }
 fixture<-as.list(f[1,c('fixture_id','provider_id','home_id','away_id')]);fixture$issue_id<-'26103'
 fixture$competition_id<-tm$target_competition_id;fixture$neutral_reported<-tm$target_neutral_reported
 row$competition_id<-fixture$competition_id
 cutoff<-list(issue_id='26103',cutoff_utc=lubridate::ymd_hms(f$cutoff_utc,tz='UTC'))
 ct<-format(cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC');pycut<-shared$Cutoff$decision_epoch('26103',ct)
 h<-enriched |> filter(metadata_agrees,competition_id==fixture$competition_id) |>
  transmute(row_key=paste(fixture_id,scope,match_id,sep=':'),match_id,event_date,home_id,away_id,home_score,away_score,score_scope,competition_id,neutral_reported)
 native<-tryCatch({
  domain<-jsonlite::fromJSON(jsonlite::toJSON(h,dataframe='rows',auto_unbox=TRUE,na='null',digits=NA),simplifyVector=FALSE)
  prepared<-backend$prepare_opponent_goals(domain,fixture,as.list(excluded),pycut,bindings,root,runtime$native_policy)
  ns$FitOpponentGoals(prepared,fixture,pycut,runtime$fit_policy,root)
 },error=function(e)e)
 if(inherits(native,'error')) {
  row$reason<-conditionMessage(native)
  if(!grepl('Sparse target competition/venue support|Disconnected target strength network|No prior target-competition network|cutoff admits no prior observations|Nonempty unique factual rows required',row$reason))stop('Critical fit failure ',id,': ',row$reason)
  audit[[id]]<-row
  if(!replay&&!pilot)saveRDS(list(entry=NULL,row=row,bindings=bindings,probabilities=list()),cache_path)
  next
 }
 parameters<-native$same_support_raw
 row$lambda_home<-parameters$lambda_home;row$lambda_away<-parameters$lambda_away;row$fit_rows<-native$receipt$fitted_rows
 row$native_lambda_home<-parameters$lambda_home;row$native_lambda_away<-parameters$lambda_away
 # Only same_support_raw is the formal FM171 input; opponent-normalized parameters never enter the grid.
 grid<-beidan:::dixon_coles_score_grid(parameters$lambda_home,parameters$lambda_away,0L,1e-10,policy$native_policy$rho)$grid |>
  select(home_goals,away_goals,probability)
 latest<-max(lubridate::ymd_hms(native$receipt$admission$maximum_source_time,tz='UTC'),
  map_dbl(native$receipts,~as.numeric(lubridate::ymd_hms(.x$maximum_source_time,tz='UTC'))))
 latest<-as.POSIXct(as.numeric(latest),origin='1970-01-01',tz='UTC')
 base<-list(grid=grid,cutoff=cutoff,model_id='FM-1.7.1_SAME_SUPPORT_RAW',source_hashes=bindings,max_source_available_utc=latest,intended_use='HISTORICAL_DIAGNOSTIC')
 native_base<-base
 ft<-tibble(fixture_id=id,issue_id='26103',home=f$home,away=f$away)
 eid<-'native-reliability';evidence_time<-format(latest,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
 evidence<-list(list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(native$receipt),row_key=eid,issue_code='PRIOR_EVIDENCE',issue_year=2026L,label_available_ts=evidence_time,data_available_ts=evidence_time))
 ma<-markets$audit |> filter(fixture_id==id);ref<-markets$references[[id]];market_base<-NULL
 if(!is.null(ref)) {
  evidence<-c(evidence,ref$evidence)
  market_base<-list(grid=ref$model$grid,cutoff=cutoff,model_id='FM171_JOINT_MARKET',
   source_hashes=list(market_stage=market_manifest$sha256,market_receipt=beidan:::.score_margin_hash(ref$model$receipt)),
   max_source_available_utc=max(lubridate::ymd_hms(map_chr(ref$evidence,'data_available_ts'),tz='UTC')),intended_use='HISTORICAL_DIAGNOSTIC')
 }
 row$market_sufficient<-ma$sufficient;row$market_consistent<-ma$consistent;row$market_gap<-ma$reason
 review<-list(confidence='uncertain',market_sufficient=ma$sufficient,market_consistent=ma$consistent,
  reason=paste('Same competition and venue support passed; roster/analysis/Euro clocks agree. Native support rows',native$receipt$fitted_rows,'; missing lineups/injuries, unadjusted opponent strength and source full-time regulation scope. Market:',ma$reason,'Euro companies',ma$euro_companies,'max residuals',ma$max_euro_residual,ma$max_asian_residual,'; fixed prior criteria >=3 companies and both residuals<=5pp, quote age<=48h.'),
  counterevidence=paste('Not JEV, no calibrated confidence score. Source post-event capture and date proxies are diagnostic only. Unknown squad-cycle comparability; league',f$league),
  evidence_ids=map_chr(evidence,'evidence_id'),cutoff_utc=ct,native_hash=beidan:::.score_margin_hash(base),market_hash=if(is.null(market_base))'ABSENT'else beidan:::.score_margin_hash(market_base),author='Codex evidence audit',review_version='FM171_26103_FIXED_AUDIT_1')
 selection_bindings<-c(bindings,list(fm_source_selection_inputs=beidan:::.score_margin_hash(list(native=base,market=market_base,review=review,fixture=ft,cutoff=cutoff)),
  fm_source_selection_code=digest::digest(paste(deparse(SelectFmProbabilitySource),collapse='\n'),algo='sha256'),fm_source_selection_dependencies=beidan:::.score_margin_code(root)))
 ctx<-adjustment$build_adjustment_evidence_context(evidence,as.list(ft),pycut,selection_bindings,shared$AvailabilityPolicy$historical_proxy('FM171_26103_POSTEVENT_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',root)
 selection<-SelectFmProbabilitySource(base,market_base,review,ctx,ft,cutoff,root)
 base<-selection$base
 row$selected_source<-selection$selected_source
 if(selection$selected_source=='market') {
  parameters<-ref$model$parameters;row$lambda_home<-parameters$lambda_home;row$lambda_away<-parameters$lambda_away
 }
 tail_review<-list(decision='apply',base_hash=beidan:::.score_margin_hash(base$grid),cutoff_utc=ct,
  reason='Fixed FM171 cumulative90% core and coefficient.3; no outcome or ticket-line input',counterevidence=review$counterevidence)
 core<-BuildFmTailJudgement(base,tail_review,eid,cutoff,policy$tail_policy)
 tail_bindings<-c(bindings,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(core$judgement),tail_binding=core$binding_hash))
 ctx<-adjustment$build_adjustment_evidence_context(evidence,as.list(ft),pycut,tail_bindings,shared$AvailabilityPolicy$historical_proxy('FM171_26103_POSTEVENT_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',root)
 final<-adjust_score_margin_distribution(base,core$judgement,ctx,ft,cutoff,root)
 entry<-list(fixture=ft,identities=fixture,cutoff=cutoff,native=native,native_base=native_base,market_base=market_base,base=base,selection=selection,source_review=review,core=core,tail_review=tail_review,final=final,evidence=evidence)
 entries[[id]]<-entry
 probabilities[[paste(id,'FM171')]]<-project_score_outcomes(final,as.integer(f$handicap),root) |>
  mutate(fixture_id=id,model='FM171',.before=1)
 before<-beidan:::dixon_coles_score_grid(parameters$lambda_home,parameters$lambda_away,as.integer(f$handicap),1e-10,policy$native_policy$rho)$probability
 probabilities[[paste(id,'BEFORE_TAIL')]]<-tibble(fixture_id=id,model='BEFORE_TAIL',outcome=names(before),probability=unname(before))
 row$state<-'ESTIMATED';row$reason<-paste('Formal same-support native; source',selection$selected_source,'; fixed FM171 tail')
 audit[[id]]<-row
 if(!replay&&!pilot)saveRDS(list(entry=entry,row=row,bindings=bindings,probabilities=probabilities[paste(id,c('FM171','BEFORE_TAIL'))]),cache_path)
 if(length(audit)%%10L==0L)message('Processed ',length(audit),' estimated ',length(entries))
}
x<-list(entries=entries,audit=bind_rows(audit),probabilities=bind_rows(probabilities),bindings=bindings)
path<-file.path(out,if(pilot)'pilot-native.rds'else if(sharded)paste0('native-shard-',shard_index,'of',shard_count,'.rds')else'native-forecasts.rds')
if(replay) {
 reference<-if(sharded)list(entries=existing$entries[names(entries)],audit=existing$audit |> filter(fixture_id%in%scope),
  probabilities=existing$probabilities |> filter(fixture_id%in%scope),bindings=existing$bindings)else existing
 stopifnot(identical(x,reference))
 jsonlite::write_json(list(status='FULL_IDENTICAL_REPLAY',forecasts=length(entries),processed_fixture_ids=scope,
  bindings_sha256=beidan:::.score_margin_hash(bindings),sha256=digest::digest(file=file.path(out,'native-forecasts.rds'),algo='sha256')),
  file.path(out,if(sharded)paste0('native-replay-',shard_index,'of',shard_count,'.json')else'native-replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else {
 if(file.exists(path))stopifnot(identical(x,readRDS(path)))else saveRDS(x,path)
 write_csv(x$audit,file.path(out,if(pilot)'pilot-native-audit.csv'else if(sharded)paste0('native-shard-',shard_index,'of',shard_count,'-audit.csv')else'native-audit.csv'))
 if(!pilot&&!sharded)jsonlite::write_json(list(forecasts=length(entries),scope=407,sha256=digest::digest(file=path,algo='sha256'),bindings=bindings,
  target_parameter_tuning=FALSE,target_roster_contains_known_settlement=TRUE,intended_use='POSTHOC_DIAGNOSTIC',prospective_validated=FALSE,
  market_note='Available saved three-channel quotes reviewed using fixed prior criteria; no euro-only substitution; others explicitly retain uncertain native'),file.path(out,'native-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
print(x$audit |> count(state,reason));print(head(x$audit,5))
