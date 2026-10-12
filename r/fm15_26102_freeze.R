# Freeze all26102 predictions before opening target labels/SP.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE);out<-file.path(root,'results/fm15-26102-20261012');impl<-file.path(out,'implementation')
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm15-version-20261012/library'))
source(file.path(impl,'packages/beidan/R/recent_venue_goals.R'),local=TRUE)
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE);reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE);backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
nm<-fromJSON(file.path(out,'native-manifest.json'));mm<-fromJSON(file.path(out,'market-manifest.json'))
np<-file.path(out,nm$native_file);mp<-file.path(out,mm$stage_file)
stopifnot(digest::digest(file=np,algo='sha256')==nm$sha256,digest::digest(file=mp,algo='sha256')==mm$sha256)
native<-readRDS(np);market<-readRDS(mp)
stopifnot(beidan:::.score_margin_code(impl)==native$source_hashes$DC_loaded_implementation)
stopifnot(beidan:::.score_margin_hash(native)==nm$object_hash,beidan:::.score_margin_hash(market)==mm$object_hash,length(native$entries)==86L)
file_keys<-setdiff(names(native$source_hashes),'DC_loaded_implementation')
stopifnot(all(map_chr(file.path(root,file_keys),~digest::digest(file=.x,algo='sha256'))==unlist(native$source_hashes[file_keys],use.names=FALSE)))
parent_path<-file.path(root,'results/fundamental-issues-20261011/run-20261011T011533.304058Z/26102-frozen.rds');parent<-readRDS(parent_path)
inv<-fromJSON(file.path(out,'implementation-inventory.json'));stopifnot(all(map_chr(file.path(impl,inv$files$path),~digest::digest(file=.x,algo='sha256'))==inv$files$sha256))
stopifnot(all(map_chr(file.path(root,market$inputs$path),~digest::digest(file=.x,algo='sha256'))==market$inputs$sha256))
selection_paths<-list.files(out,pattern='^pa-selection-[0-9]+[.]json$',full.names=TRUE);stopifnot(length(selection_paths)==43L)
reviews<-list();authors<-list();trace<-c(np,mp,parent_path,file.path(out,'scope.json'),file.path(out,'implementation-inventory.json'),file.path(root,'r/fm15_26102_freeze.R'),file.path(root,'scripts/fm15_26102_pa.py'),selection_paths,file.path(root,market$inputs$path))
allowed<-c('native_rates','top_margins','independent_market','total_constraint','asian_quotes','total_quotes','euro_quotes','missing')
for(path in selection_paths) {
  s<-fromJSON(path);ip<-file.path(root,s$input_path);rp<-file.path(root,s$review_path)
  local<-identical(s$reviewer,'ROOT_CODEX')
  if(local) {
    cp<-file.path(root,s$local_receipt_path);receipt<-fromJSON(cp)
    stopifnot(receipt$reviewer=='ROOT_CODEX',receipt$scope=='HISTORICAL_DIAGNOSTIC',!receipt$target_settlement_consulted_in_this_review,digest::digest(file=ip,algo='sha256')==receipt$input_sha256,digest::digest(file=rp,algo='sha256')==receipt$review_sha256)
    trace<-c(trace,cp)
  } else {
    pp<-file.path(root,s$prompt_path);call<-file.path(root,s$call_path);receipt<-fromJSON(file.path(call,'receipt.json'))
    stopifnot(receipt$exit_code==0,!receipt$timed_out,receipt$model=='opencode/deepseek-v4.1-flash',normalizePath(receipt$cwd)==normalizePath(dirname(ip)),digest::digest(file=pp,algo='sha256')==receipt$prompt_sha256)
    trace<-c(trace,pp,list.files(call,full.names=TRUE))
  }
  input<-fromJSON(ip,simplifyVector=FALSE);rows<-fromJSON(rp,simplifyVector=FALSE);stopifnot(length(input)==2L,length(rows)==2L)
  for(j in seq_along(rows)) {
    r<-rows[[j]];p<-input[[j]];expected<-fromJSON(toJSON(market$packets[[r$fixture_id]],auto_unbox=TRUE,digits=17,POSIXt='ISO8601',na='null'),simplifyVector=FALSE)
    stopifnot(identical(p,expected),setequal(names(r),c('fixture_id','cutoff_utc','base_hash','decision','market_action','reason','counterevidence','market_review','evidence_ids')))
    stopifnot(all(map_lgl(c('fixture_id','cutoff_utc','base_hash'),~identical(r[[.x]],p[[.x]]))),r$decision %in% c('apply','retain'),r$market_action %in% c('KEEP_NATIVE','UNIDENTIFIED_SHIFT'),r$market_action!='UNIDENTIFIED_SHIFT'||r$decision=='retain')
    stopifnot(length(r$evidence_ids)>=1L,length(r$evidence_ids)<=4L,all(unlist(r$evidence_ids) %in% allowed),all(map_lgl(c('reason','counterevidence','market_review'),~is.character(r[[.x]])&&nzchar(trimws(r[[.x]])))))
    if(local)stopifnot(receipt$cutoff_bindings$fixture_id[j]==r$fixture_id,receipt$cutoff_bindings$cutoff_utc[j]==r$cutoff_utc,receipt$cutoff_bindings$base_hash[j]==r$base_hash)
    stopifnot(is.null(reviews[[r$fixture_id]]));reviews[[r$fixture_id]]<-r;authors[[r$fixture_id]]<-if(local)'ROOT_CODEX'else'PA_DEEPSEEK'
  }
  trace<-c(trace,ip,rp)
}
stopifnot(setequal(names(reviews),names(native$entries)))
trace<-c(trace,list.files(file.path(out,'execution-evidence'),full.names=TRUE),list.files(out,pattern='^pa-call-',full.names=TRUE) |> map(~list.files(.x,full.names=TRUE)) |> unlist(use.names=FALSE))
trace<-unique(trace);input_ledger<-tibble(path=substring(trace,nchar(root)+2L),sha256=map_chr(trace,~digest::digest(file=.x,algo='sha256')))
outputs<-probabilities<-before<-audit<-list()
for(id in names(native$entries)) {
  e<-native$entries[[id]];f<-e$fixture;r<-reviews[[id]];quotes<-market$selected[[id]]
  h<-as_tibble(parent$history) |> filter(fixture_id==id) |> mutate(row_key=paste(scope,match_id,sep=':'),event_date=as.character(event_date))
  fresh<-estimate_recent_venue_goals(h,f[c('fixture_id','issue_id','provider_id','home_id','away_id')],as.character(parent$fixtures$provider_id),shared$Cutoff$decision_epoch('26102',r$cutoff_utc),e$source_hashes,impl,native$policy,'HISTORICAL_DIAGNOSTIC')
  stopifnot(identical(fresh,e$native))
  cutoff<-list(issue_id='26102',cutoff_utc=f$cutoff_utc)
  source_time<-lubridate::ymd_hms(e$native$admission_receipt$maximum_source_time,tz='UTC')
  for(q in quotes)if(nrow(q))source_time<-max(source_time,q$quote_at)
  stopifnot(source_time<f$cutoff_utc)
  hashes<-c(e$source_hashes,list(native_receipts=beidan:::.score_margin_hash(e$native),market_artifact=mm$object_hash,review=beidan:::.score_margin_hash(r),input_ledger=beidan:::.score_margin_hash(input_ledger)))
  base<-list(grid=e$grid,cutoff=cutoff,model_id='FM-1.5.0_NATIVE',source_hashes=hashes,max_source_available_utc=source_time,intended_use='HISTORICAL_DIAGNOSTIC')
  evidence_id<-'native-review';ts<-e$native$admission_receipt$maximum_source_time
  rows<-list(list(evidence_id=evidence_id,fixture_id=id,source_hash=hashes$native_receipts,row_key=evidence_id,issue_code='NATIVE_HISTORY_PROXY',issue_year=as.integer(substr(ts,1,4)),label_available_ts=ts,data_available_ts=ts))
  for(kind in names(quotes)) {
    q<-quotes[[kind]]
    for(j in seq_len(nrow(q))) {
      qt<-format(q$quote_at[j],'%Y-%m-%dT%H:%M:%SZ',tz='UTC');qid<-paste0(kind,'-',q$company_id[j])
      rows[[length(rows)+1L]]<-list(evidence_id=qid,fixture_id=id,source_hash=beidan:::.score_margin_hash(q[j,]),row_key=qid,issue_code='QUOTE_PROXY',issue_year=as.integer(substr(qt,1,4)),label_available_ts=qt,data_available_ts=qt)
    }
  }
  policy<-beidan:::build_fm15_tail_judgement(base,r,evidence_id,cutoff,list(max_radius=2L,threshold=.1,coefficient=.3,tie_tolerance=1e-12))
  bindings<-c(hashes,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(policy$judgement),direction_implementation=beidan:::.score_margin_code(impl),fm15_binding=policy$binding_hash))
  fixture<-tibble(fixture_id=id,issue_id='26102',home=f$home,away=f$away)
  ctx<-backend$build_adjustment_evidence_context(rows,as.list(fixture),shared$Cutoff$decision_epoch('26102',r$cutoff_utc),bindings,shared$AvailabilityPolicy$historical_proxy('NATIVE_VENUE_MARKET_PRIOR_QUOTES_DIAGNOSTIC_ONLY'),'HISTORICAL_DIAGNOSTIC',impl)
  final<-adjust_score_margin_distribution(base,policy$judgement,ctx,fixture,cutoff,impl)
  stopifnot(identical(final,adjust_score_margin_distribution(base,policy$judgement,ctx,fixture,cutoff,impl)))
  score_path<-file.path(out,paste0('score-',gsub(':','-',id),'-',substr(final$seal,1,12),'.rds'))
  if(file.exists(score_path))stopifnot(identical(readRDS(score_path),final))else saveRDS(final,score_path)
  # Actual integer Beijing line enters only after the score distribution is sealed.
  stopifnot(is.finite(f$handicap),f$handicap==round(f$handicap))
  probabilities[[id]]<-project_score_outcomes(final,as.integer(f$handicap),impl) |> mutate(fixture_id=id,model='FM-1.5.0',.before=1)
  dm<-e$grid$home_goals-e$grid$away_goals+f$handicap
  before[[id]]<-tibble(fixture_id=id,model='FM15-native-before-tail',outcome=c('W','D','L'),probability=c(sum(e$grid$probability[dm>0]),sum(e$grid$probability[dm==0]),sum(e$grid$probability[dm<0])))
  outputs[[id]]<-list(base=base,review=r,policy=policy,final=final,evidence_rows=rows,bindings=bindings,score_path=substring(score_path,nchar(root)+2L))
  audit[[id]]<-tibble(fixture_id=id,reviewer=authors[[id]],lambda_home=e$native$parameters$lambda_home,lambda_away=e$native$parameters$lambda_away,center=policy$center,radius=policy$radius,branch=policy$branch,market_action=r$market_action,reason=r$reason,counterevidence=r$counterevidence,market_review=r$market_review)
  message('Frozen ',id)
}
batch<-list(model='FM-1.5.0',issue_id='26102',entries=outputs,probabilities=bind_rows(probabilities),before=bind_rows(before),audit=bind_rows(audit),coverage=market$ledger,input_ledger=input_ledger)
id<-beidan:::.score_margin_hash(batch);path<-file.path(out,paste0('batch-',substr(id,1,12),'.rds'))
if(file.exists(path))stopifnot(identical(readRDS(path),batch))else saveRDS(batch,path)
write_json(list(batch_file=basename(path),object_hash=id,sha256=digest::digest(file=path,algo='sha256'),generated_at_utc=format(Sys.time(),'%Y-%m-%dT%H:%M:%SZ',tz='UTC')),file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
write_csv(batch$audit,file.path(out,'audit.csv'));write_csv(batch$probabilities,file.path(out,'probabilities.csv'));write_csv(batch$before,file.path(out,'before-tail.csv'))
message('All86 immutable forecasts frozen; target labels/SP remain unopened')
