# Shadow AH+OU projection on every supported quote pair, including good controls.
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);replay<-length(args)>1&&args[2]=='replay'
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-diagnostic-iterations-20261013/library'))
out<-file.path(root,'results/fm17-diagnostic-iterations-20261013');src<-file.path(root,'results/fm17-three-issues-20261013')
m<-fromJSON(file.path(src,'manifest.json'));stopifnot(digest::digest(file=file.path(src,'forecasts.rds'),algo='sha256')==m$forecast_sha256)
x<-readRDS(file.path(src,'forecasts.rds'));s<-readRDS(file.path(root,'results/fm16-three-issues-20261012/stage.rds'))
stopifnot(digest::digest(file=file.path(root,'results/fm16-three-issues-20261012/stage.rds'),algo='sha256')==m$source_hashes$parent_stage)
impl<-s$implementation;reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE);backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
policy<-list(rho=-.1,total_bounds=c(.1,16),lambda_floor=.05,tail_tolerance=1e-10,max_quote_age_hours=48)
common<-list(parent_forecast=m$forecast_sha256,client=digest::digest(file=file.path(root,'r/fm17_diagnostic_round3_partial.R'),algo='sha256'))
entries<-probabilities<-audit<-coverage<-list();existing<-if(replay)readRDS(file.path(out,'round3-partial-forecasts.rds'))else NULL
for(id in names(x$entries)) {
 e<-x$entries[[id]];p<-s$packets[[id]];q<-p$asian;t<-p$totals;fixture<-e$fixture;cutoff<-e$cutoff
 reason<-NULL
 if(is.null(q)||is.null(t)||nrow(q)!=1L||nrow(t)!=1L)reason<-'MISSING_OR_MULTIPLE_SINGLE_COMPANY_CHANNEL'
 if(is.null(reason)&&(q$handicap*2!=round(q$handicap*2)||q$handicap==round(q$handicap)))reason<-'UNSUPPORTED_INTEGER_OR_QUARTER_ASIAN'
 if(is.null(reason)&&(t$line<2.5||t$line*4!=round(t$line*4)))reason<-'UNSUPPORTED_TOTAL_BELOW_2.5'
 if(!is.null(reason)){coverage[[id]]<-tibble(fixture_id=id,selected_source=e$parent_selection$selected_source,status='NOT_APPLICABLE',reason=reason);next}
 q<-q |> select(company_id,fixture_id,quote_at,handicap,home_decimal,away_decimal)
 t<-t |> select(fixture_id,company_id,quote_at,line,over_decimal,under_decimal)
 ct<-format(cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC');rows<-list()
 for(kind in c('asian','totals')) {
  row<-if(kind=='asian')q else t;ts<-format(row$quote_at,'%Y-%m-%dT%H:%M:%SZ',tz='UTC');eid<-paste0(kind,'-',row$company_id)
  rows[[kind]]<-list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(row),row_key=eid,issue_code='QUOTE_PROXY',issue_year=as.integer(substr(ts,1,4)),label_available_ts=ts,data_available_ts=ts)
 }
 hashes<-c(common,list(partial_input=beidan:::.score_margin_hash(list(asian=q,totals=t,policy=policy,fixture=fixture,cutoff=cutoff)),partial_code=digest::digest(paste(deparse(beidan:::.ProjectHalfAsianTotalDc),collapse='\n'),algo='sha256'),direction_implementation=beidan:::.score_margin_code(impl),partial_total_code=beidan:::.score_margin_hash(lapply(list(beidan:::total_market_constraint,beidan:::asian_total_probability),function(f)paste(deparse(f),collapse='\n')))))
 result<-tryCatch({
  ctx<-backend$build_adjustment_evidence_context(unname(rows),as.list(fixture),shared$Cutoff$decision_epoch(fixture$issue_id,ct),hashes,shared$AvailabilityPolicy$historical_proxy('FM17_ROUND3_HALF_AH_OU_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',impl)
  beidan:::.ProjectHalfAsianTotalDc(q,t,policy,ctx,fixture,cutoff,impl)
 },error=identity)
 if(inherits(result,'error')){coverage[[id]]<-tibble(fixture_id=id,selected_source=e$parent_selection$selected_source,status='REFUSED',reason=conditionMessage(result));next}
 coverage[[id]]<-tibble(fixture_id=id,selected_source=e$parent_selection$selected_source,status='READY',reason='Partial half-goal AH+OU; not FM17 source admission')
 b<-list(grid=result$grid,cutoff=cutoff,model_id='PARTIAL_HALF_AH_OU',source_hashes=list(partial_receipt=beidan:::.score_margin_hash(result$receipt)),max_source_available_utc=max(q$quote_at,t$quote_at),intended_use='HISTORICAL_DIAGNOSTIC')
 results<-list()
 for(model in c('HALF_AH_OU_RAW','HALF_AH_OU_TAIL')) {
  review<-list(decision=if(model=='HALF_AH_OU_RAW')'retain'else'apply',base_hash=beidan:::.score_margin_hash(b$grid),cutoff_utc=ct,reason='Uniform shadow partial-market experiment',counterevidence='One company each, half-goal only, no Euro consistency; diagnostic not source admission')
  core<-BuildFmTailJudgement(b,review,paste0('asian-',q$company_id),cutoff,list(coverage=.9,coefficient=.3,tie_tolerance=1e-12))
  bh<-c(hashes,list(base_artifact=beidan:::.score_margin_hash(b),margin_judgement=beidan:::.score_margin_hash(core$judgement),tail_binding=core$binding_hash))
  ctx<-backend$build_adjustment_evidence_context(unname(rows),as.list(fixture),shared$Cutoff$decision_epoch(fixture$issue_id,ct),bh,shared$AvailabilityPolicy$historical_proxy('FM17_ROUND3_HALF_AH_OU_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',impl)
  final<-adjust_score_margin_distribution(b,core$judgement,ctx,fixture,cutoff,impl)
  results[[model]]<-list(core=core,final=final,bindings=bh)
 }
 entry<-list(fixture=fixture,cutoff=cutoff,partial=result,results=results,rows=unname(rows),bindings=hashes)
 if(replay)stopifnot(identical(entry,existing$entries[[id]]))
 entries[[id]]<-entry
 for(model in names(results))probabilities[[paste(id,model)]]<-project_score_outcomes(results[[model]]$final,as.integer(s$native[[id]]$fixture$handicap),impl) |> mutate(fixture_id=id,model=model,.before=1)
 audit[[id]]<-result$parameters |> mutate(fixture_id=id,selected_source=e$parent_selection$selected_source,cutoff_utc=cutoff$cutoff_utc,asian_line=q$handicap,asian_target=result$asian_target,asian_model=result$asian_model,euro_companies=p$euro_companies,.before=1)
 if(length(entries)%%25==0)message(if(replay)'Replayed 'else'Frozen ',length(entries))
}
batch<-list(entries=entries,probabilities=bind_rows(probabilities),audit=bind_rows(audit),coverage=bind_rows(coverage),bindings=common)
path<-file.path(out,'round3-partial-forecasts.rds')
if(replay){stopifnot(identical(batch,existing));write_json(list(status='FULL_IDENTICAL_REPLAY',fixtures=length(entries),models=2,sha256=digest::digest(file=path,algo='sha256')),file.path(out,'round3-partial-replay.json'),auto_unbox=TRUE,pretty=TRUE)}else{
 if(file.exists(path))stopifnot(identical(batch,readRDS(path)))else saveRDS(batch,path)
 write_csv(batch$probabilities,file.path(out,'round3-partial-probabilities.csv'));write_csv(batch$audit,file.path(out,'round3-partial-audit.csv'));write_csv(batch$coverage,file.path(out,'round3-partial-coverage.csv'))
 write_json(list(round=3,fixtures=length(entries),covered=length(x$entries),forecast_sha256=digest::digest(file=path,algo='sha256'),bindings=common,training_or_source_admission=FALSE),file.path(out,'round3-partial-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
