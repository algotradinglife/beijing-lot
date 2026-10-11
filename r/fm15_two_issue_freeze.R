# Finalize accepted blinded reviews; settlements remain unopened.
root <- normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
out <- file.path(root,'results/fm15-two-issues-20261012')
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm15-version-20261012/library'))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
shared <- reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend <- reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
stage <- readRDS(file.path(out,'native-stage.rds'))
scope_path <- file.path(out,'scope.json');scope <- fromJSON(scope_path)
stopifnot(scope$model_id=='FM-1.5.0',nrow(scope$forecast_inputs)==3L,all(map_chr(file.path(root,scope$forecast_inputs$path),~digest::digest(file=.x,algo='sha256'))==scope$forecast_inputs$sha256))
parents <- list()
for(issue in names(stage$inputs)) {
  hashes <- stage$inputs[[issue]]
  stopifnot(length(hashes)>0,all(map_chr(file.path(root,names(hashes)),~digest::digest(file=.x,algo='sha256'))==unlist(hashes,use.names=FALSE)))
  parent_path <- names(hashes)[endsWith(names(hashes),paste0(issue,'-frozen.rds'))]
  stopifnot(length(parent_path)==1L)
  parents[[issue]] <- readRDS(file.path(root,parent_path))
}
selection_files <- list.files(out,pattern='^pa-selection-[0-9]+[.]json$',full.names=TRUE)
reviews <- list(); local_reviews <- list(); trace_paths <- c(scope_path,file.path(out,'native-stage.rds'),file.path(out,'review-inputs.json'),selection_files)
for (path in selection_files) {
  s <- fromJSON(path)
  call_paths <- if(is.null(s$call_paths)) s$call_path else s$call_paths
  for(call_path in call_paths) {
    call <- file.path(root,call_path)
    receipt <- fromJSON(file.path(call,'receipt.json'))
    stopifnot(receipt$exit_code==0,!receipt$timed_out,receipt$model=='opencode/deepseek-v4.1-flash')
    prompt_path <- file.path(out,'prompt-receipts',paste0(receipt$prompt_sha256,'.txt'))
    stopifnot(file.exists(prompt_path),digest::digest(file=prompt_path,algo='sha256')==receipt$prompt_sha256,startsWith(receipt$cwd,paste0(out,'/')))
    trace_paths <- c(trace_paths,prompt_path,list.files(call,full.names=TRUE),list.files(receipt$cwd,pattern='^(input[.]json|summary[.]txt|review[.]json)$',full.names=TRUE))
  }
  rp <- file.path(root,s$review_path)
  reviews <- c(reviews,fromJSON(rp,simplifyVector=FALSE))
  for(lr_path in s$local_review_receipts) {
    lr <- fromJSON(file.path(root,lr_path));local_path <- file.path(root,lr$review_path)
    stopifnot(lr$reviewer=='ROOT_CODEX',lr$intended_use=='POSTHOC_HISTORICAL_DIAGNOSTIC',!lr$target_settlement_consulted_in_this_review,digest::digest(file=local_path,algo='sha256')==lr$review_sha256,digest::digest(file=file.path(root,lr$input_path),algo='sha256')==lr$input_sha256)
    local_reviews[[lr$fixture_id]] <- fromJSON(local_path,simplifyVector=FALSE)
    stopifnot(all(map_lgl(c('fixture_id','cutoff_utc','base_hash'),~identical(local_reviews[[lr$fixture_id]][[.x]],lr[[.x]]))))
    trace_paths <- c(trace_paths,file.path(root,lr_path),local_path)
  }
  trace_paths <- c(trace_paths,rp,file.path(dirname(rp),'input.json'))
}
stopifnot(length(reviews)==length(stage$entries),!anyDuplicated(map_chr(reviews,'fixture_id')),setequal(map_chr(reviews,'fixture_id'),names(stage$entries)))
trace_paths <- unique(c(trace_paths,list.files(out,pattern='^review-prompt-',full.names=TRUE),file.path(root,c('r/fm15_two_issue_freeze.R','scripts/fm15_two_issue_pa.py','scripts/fm15_review_first_batch.py','scripts/fm15_bind_pa_prompts.py','results/fm15-two-issues-20261012/failed-text-prototype/fm15_pa_text.py'))))
input_ledger <- tibble(path=substring(trace_paths,nchar(root)+2),sha256=map_chr(trace_paths,~digest::digest(file=.x,algo='sha256')))
outputs <- list(); probabilities <- list(); before <- list(); audit <- list()
for (review in reviews) {
  e <- stage$entries[[review$fixture_id]]; f <- e$fixture; p <- e$packet
  if(review$fixture_id %in% names(local_reviews)) stopifnot(identical(review,local_reviews[[review$fixture_id]]))
  if(review$fixture_id %in% names(local_reviews)) {
    allowed <- c('native_rates','top_margins','independent_market','asian_quotes','total_quotes','euro_quotes','missing',e$blinded$article_facts$evidence_id)
    stopifnot(length(review$evidence_ids)>=1L,length(review$evidence_ids)<=4L,all(unlist(review$evidence_ids) %in% allowed))
  }
  parent <- parents[[f$issue_id]]
  history <- as_tibble(map(parent$history,identity)) |> filter(fixture_id==f$fixture_id) |> mutate(row_key=paste(scope,match_id,sep=':'),event_date=as.character(event_date))
  replay_native <- beidan:::estimate_recent_venue_goals(history,f[c('fixture_id','issue_id','provider_id','home_id','away_id')],as.character(parent$fixtures$provider_id),shared$Cutoff$decision_epoch(f$issue_id,p$cutoff_utc),e$source_hashes,root,stage$policy)
  stopifnot(identical(replay_native,e$native))
  stopifnot(identical(review$base_hash,p$base_hash),identical(review$cutoff_utc,p$cutoff_utc),review$decision %in% c('apply','retain'),review$market_action %in% c('KEEP_NATIVE','UNIDENTIFIED_SHIFT'))
  stopifnot(review$market_action!='UNIDENTIFIED_SHIFT'||review$decision=='retain')
  cutoff <- list(issue_id=f$issue_id,cutoff_utc=f$cutoff_utc)
  ts <- e$native$admission_receipt$maximum_source_time
  source_time <- lubridate::ymd_hms(ts,tz='UTC')
  hashes <- c(e$source_hashes,list(native_output=e$native$output_hash,native_receipt=beidan:::.score_margin_hash(e$native$receipts),qualitative_review=beidan:::.score_margin_hash(review),input_ledger=beidan:::.score_margin_hash(input_ledger)))
  base <- list(grid=e$grid,cutoff=cutoff,model_id='FM-1.5.0_NATIVE',source_hashes=hashes,max_source_available_utc=source_time,intended_use='HISTORICAL_DIAGNOSTIC')
  evidence_id <- 'admitted-native-history'
  fixture <- tibble(fixture_id=f$fixture_id,issue_id=f$issue_id,home=f$home,away=f$away)
  rows <- list(list(evidence_id=evidence_id,fixture_id=f$fixture_id,source_hash=hashes$native_receipt,row_key=evidence_id,issue_code='NATIVE_HISTORY_PROXY',issue_year=as.integer(substr(ts,1,4)),label_available_ts=ts,data_available_ts=ts))
  # Bind every independently reviewed quote and article to its actual proxy time.
  for(kind in names(e$quotes)) for(k in seq_len(nrow(e$quotes[[kind]]))) {
    q <- as_tibble(e$quotes[[kind]])[k,]; qt <- format(q$quote_at,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'); id <- paste0(kind,'-',q$company_id)
    rows[[length(rows)+1L]] <- list(evidence_id=id,fixture_id=f$fixture_id,source_hash=beidan:::.score_margin_hash(q),row_key=id,issue_code='QUOTE_PROXY',issue_year=as.integer(substr(qt,1,4)),label_available_ts=qt,data_available_ts=qt)
  }
  for(k in seq_len(nrow(e$blinded$article_facts))) {
    q <- e$blinded$article_facts[k,]; qt <- format(q$availability_proxy_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
    rows[[length(rows)+1L]] <- list(evidence_id=q$evidence_id,fixture_id=f$fixture_id,source_hash=q$source_sha256,row_key=q$evidence_id,issue_code='ARTICLE_PUBLISH_PROXY',issue_year=as.integer(substr(qt,1,4)),label_available_ts=qt,data_available_ts=qt)
  }
  base$max_source_available_utc <- max(lubridate::ymd_hms(map_chr(rows,'data_available_ts'),tz='UTC'))
  stopifnot(base$max_source_available_utc < cutoff$cutoff_utc)
  policy <- beidan:::build_fm15_tail_judgement(base,review,evidence_id,cutoff,list(max_radius=2L,threshold=.1,coefficient=.3,tie_tolerance=1e-12))
  bindings <- c(hashes,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(policy$judgement),direction_implementation=beidan:::.score_margin_code(root),fm15_binding=policy$binding_hash))
  ctx <- backend$build_adjustment_evidence_context(rows,as.list(fixture),shared$Cutoff$decision_epoch(f$issue_id,p$cutoff_utc),bindings,shared$AvailabilityPolicy$historical_proxy('NATIVE_HISTORY_ARTICLE_QUOTE_POSTHOC_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',root)
  final <- adjust_score_margin_distribution(base,policy$judgement,ctx,fixture,cutoff,root)
  stopifnot(identical(final,adjust_score_margin_distribution(base,policy$judgement,ctx,fixture,cutoff,root)))
  path <- file.path(out,paste0('score-',gsub(':','-',f$fixture_id),'-',substr(final$seal,1,12),'.rds'))
  if(file.exists(path)) stopifnot(identical(readRDS(path),final)) else saveRDS(final,path)
  # Actual Northsingle handicap enters after the full final grid was frozen.
  probabilities[[f$fixture_id]] <- project_score_outcomes(final,as.integer(f$handicap),root) |> mutate(fixture_id=f$fixture_id,model='FM-1.5.0',.before=1)
  dm <- e$grid$home_goals-e$grid$away_goals+f$handicap
  before[[f$fixture_id]] <- tibble(fixture_id=f$fixture_id,model='FM15-native-before-tail',outcome=c('W','D','L'),probability=c(sum(e$grid$probability[dm>0]),sum(e$grid$probability[dm==0]),sum(e$grid$probability[dm<0])))
  outputs[[f$fixture_id]] <- list(final=final,policy=policy,review=review,base=base,evidence_rows=rows,bindings=bindings,score_path=substring(path,nchar(root)+2))
  audit[[f$fixture_id]] <- tibble(fixture_id=f$fixture_id,reviewer=if(f$fixture_id %in% names(local_reviews)) 'ROOT_CODEX' else 'PA_DEEPSEEK',lambda_home=e$native$parameters$lambda_home,lambda_away=e$native$parameters$lambda_away,center=policy$center,radius=policy$radius,core=paste(policy$core_margins,collapse=','),branch=policy$branch,market_action=review$market_action,reason=review$reason,counterevidence=review$counterevidence,market_review=review$market_review)
}
batch <- list(model_id='FM-1.5.0',input_ledger=input_ledger,entries=outputs,probabilities=bind_rows(probabilities),before=bind_rows(before),audit=bind_rows(audit),coverage=stage$ledger)
hash <- beidan:::.score_margin_hash(batch); path <- file.path(out,paste0('batch-',substr(hash,1,12),'.rds'))
if(file.exists(path)) stopifnot(identical(readRDS(path),batch)) else saveRDS(batch,path)
write_json(list(batch_file=basename(path),object_hash=hash,sha256=digest::digest(file=path,algo='sha256')),file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE)
write_csv(batch$probabilities,file.path(out,'probabilities.csv'));write_csv(batch$audit,file.path(out,'audit.csv'))
cat(length(outputs),'score artifacts frozen before settlement access.\n')
