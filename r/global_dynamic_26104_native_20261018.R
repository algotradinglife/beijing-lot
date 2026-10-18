# Rscript r/global_dynamic_26104_native_20261018.R ROOT IMPLEMENTATION_ROOT fit SHARD COUNT | ROOT IMPLEMENTATION_ROOT assemble
# Replays published factual bytes/metadata; no labels, source collection or priors.
args<-commandArgs(TRUE);stopifnot(length(args)%in%c(3L,5L),args[3]%in%c('fit','assemble'))
mode<-args[3]
if(mode=='fit'){stopifnot(length(args)==5L);shard<-as.integer(args[4]);shards<-as.integer(args[5]);stopifnot(!anyNA(c(shard,shards)),shards==3L,shard>=1L,shard<=shards)}else stopifnot(length(args)==3L)
root<-normalizePath(args[1],mustWork=TRUE);implementation_root<-normalizePath(args[2],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc='results/margin-combination-study-20261018/library')
invisible(python_backend(file.path(root,'.venv/bin/python')))
paths<-reticulate::import('beidan_backend.catalog.paths',convert=FALSE)
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend<-reticulate::import('beidan_backend.reviewed_opponent_goals',convert=FALSE)
coverage_backend<-reticulate::import('beidan_backend.euro_coverage',convert=FALSE)
pd<-reticulate::import('pandas',convert=FALSE)
out<-reticulate::py_str(paths$location('hot:global-dynamic-26104-20261018'))
input_path<-file.path(out,'inputs.json');metadata_path<-file.path(out,'metadata.json')
input<-jsonlite::fromJSON(input_path,simplifyVector=FALSE);metadata<-jsonlite::fromJSON(metadata_path,simplifyVector=FALSE)
stopifnot(metadata$inputs_sha256==digest::digest(file=input_path,algo='sha256'),input$issue_id=='26104')
fixtures<-bind_rows(input$fixtures) |> mutate(kickoff_at=lubridate::ymd_hms(kickoff_at,tz='UTC'),cutoff_utc=lubridate::ymd_hms(cutoff_utc,tz='UTC'),handicap=as.integer(handicap))
stopifnot(nrow(fixtures)==109L,!anyDuplicated(fixtures$fixture_id))
# Whole-issue inputs stay identical across workers; only target identities are sharded.
# Target and every known following issue ID are excluded regardless of source dates.
future_path<-'results/fm17-upcoming-20261017/schedule-26105.rds';future<-readRDS(future_path)
excluded<-unique(c(fixtures$provider_id,as.character(future$provider_id_nowscore)))
stopifnot(nrow(future)==365L,all(future$issue_id=='26105'),!anyNA(excluded))
policy<-list(recent_n=8L,alpha=.5,minimum_recent_matches=12L,minimum_recent_ess=8)
fit_policy<-list(ridge=.05,minimum_target_matches=12L,convergence_tolerance=1e-10,maximum_iterations=100000L)
bindings<-list(inputs=digest::digest(file=input_path,algo='sha256'),metadata=digest::digest(file=metadata_path,algo='sha256'),
 future=digest::digest(file=future_path,algo='sha256'),client=digest::digest(file='r/global_dynamic_26104_native_20261018.R',algo='sha256'))
meta_rows<-list();targets<-list()
for(packet in metadata$packets) {
 if(packet$state!='PARSED')next
 targets[[packet$fixture_id]]<-packet$result
 if(!length(packet$result$rows))next
 meta_rows[[packet$fixture_id]]<-bind_rows(packet$result$rows) |> transmute(fixture_id=packet$fixture_id,
 scope=recode(block,h_data='home_recent',a_data='away_recent',v_data='head_to_head'),match_id=history_id,
 metadata_date=event_date,metadata_home_id=home_id,metadata_away_id=away_id,metadata_home_score=home_score,metadata_away_score=away_score,
 competition_id,neutral_reported)
}
meta_rows<-bind_rows(meta_rows);history<-bind_rows(input$history)
stopifnot(!anyDuplicated(meta_rows[c('fixture_id','scope','match_id')]))
joined<-history |> left_join(meta_rows,by=c('fixture_id','scope','match_id'),relationship='one-to-one') |>
 mutate(metadata_agrees=!is.na(competition_id)&event_date==metadata_date&home_id==metadata_home_id&away_id==metadata_away_id&home_score==metadata_home_score&away_score==metadata_away_score)
status<-fits<-entries<-list()
if(mode=='fit') {
target_ids<-fixtures$fixture_id[(seq_len(nrow(fixtures))-1L)%%shards==shard-1L]
for(id in target_ids) {
 f<-fixtures |> filter(fixture_id==id);target<-targets[[id]]
 row<-tibble(fixture_id=id,slot=as.integer(f$slot),state='UNESTIMATED',reason='Missing target competition metadata')
 if(is.null(target)||is.null(target$target_competition_id)){status[[id]]<-row;next}
 context<-bind_rows(input$contexts) |> filter(fixture_id==id) |> mutate(kickoff_at=lubridate::ymd_hms(kickoff_at,tz='UTC'))
 schedule<-bind_rows(input$fixture_schedule) |> filter(fixture_id==id,resource=='roster')
 roster_clock<-lubridate::ymd_hms(paste(schedule$kickoff_date,schedule$kickoff_hhmm,'00'),tz='Asia/Shanghai',quiet=TRUE)
 if(nrow(context)!=2L||anyNA(context$kickoff_at)||any(context$kickoff_at!=f$kickoff_at)||length(roster_clock)!=1L||is.na(roster_clock)||roster_clock!=f$kickoff_at) {
  row$reason<-'Unresolved roster/analysis/market kickoff disagreement';status[[id]]<-row;next
 }
 fixture<-as.list(f[1,c('fixture_id','provider_id','home_id','away_id')]);fixture$issue_id<-'26104'
 fixture$competition_id<-target$target_competition_id;fixture$neutral_reported<-isTRUE(target$target_neutral_reported)
 cutoff<-list(issue_id='26104',cutoff_utc=f$cutoff_utc)
 epoch<-shared$Cutoff$decision_epoch('26104',format(f$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
 h<-joined |> filter(metadata_agrees,competition_id==fixture$competition_id) |>
 transmute(row_key=paste(fixture_id,scope,match_id,sep=':'),match_id,event_date,home_id,away_id,home_score,away_score,score_scope,competition_id,neutral_reported)
 domain<-jsonlite::fromJSON(jsonlite::toJSON(h,dataframe='rows',auto_unbox=TRUE,na='null',digits=NA),simplifyVector=FALSE)
 candidate<-tryCatch({
  prepared<-backend$prepare_reviewed_opponent_goals(domain,fixture,as.list(excluded),epoch,bindings,implementation_root,policy)
  if(reticulate::py_to_r(prepared$state)!='PREPARED')stop('Target venue support absent')
  native<-beidan:::FitOpponentGoals(prepared$prepared,fixture,epoch,fit_policy,implementation_root)
  list(native=native,recent_reviews=reticulate::py_to_r(prepared$reviews),policy=policy,preparation_implementation=reticulate::py_to_r(prepared$implementation))
 },error=identity)
 if(inherits(candidate,'error')) {
  reason<-conditionMessage(candidate)
  if(!grepl('Sparse target competition/venue support|Disconnected target strength network|No prior target-competition network|cutoff admits no prior observations|Nonempty unique factual rows required|Target venue support absent',reason))stop(candidate)
  row$reason<-reason;status[[id]]<-row;next
 }
 fits[[id]]<-candidate
 params<-candidate$native$same_support_raw
 g<-beidan:::dixon_coles_score_grid(params$lambda_home,params$lambda_away,0L,1e-10,-.1)$grid |> select(home_goals,away_goals,probability)
 latest<-lubridate::ymd_hms(candidate$native$receipt$admission$maximum_source_time,tz='UTC')
 base<-list(grid=g,cutoff=cutoff,model_id='FM171_SAME_SUPPORT_RAW',source_hashes=bindings,max_source_available_utc=latest,intended_use='HISTORICAL_DIAGNOSTIC')
 entries[[id]]<-list(identities=fixture,cutoff=cutoff,base=base,native_base=base)
 row$state<-'ESTIMATED_NATIVE_REPAIR';row$reason<-'Same competition/venue raw lambda, recent8 alpha.5, no calendar-age limit';status[[id]]<-row
 if(length(status)%%10L==0L)message('native shard ',shard,': ',length(status),' /',length(target_ids))
}
z<-list(status=bind_rows(status),fits=fits,native_policy=policy,source_hashes=bindings,analysis_quality_accepted=FALSE,historical_admission=FALSE)
shard_dir<-file.path(out,'native-fit-shards',paste0('shard-',shard));dir.create(shard_dir,recursive=TRUE,showWarnings=FALSE)
path<-file.path(shard_dir,'fits.rds')
payload<-list(result=z,entries=entries,scope=target_ids,shard=shard,shards=shards)
if(file.exists(path))stopifnot(identical(payload,readRDS(path)))else saveRDS(payload,path)
jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256'),scope=target_ids,shard=shard,shards=shards),file.path(shard_dir,'receipt.json'),auto_unbox=TRUE,pretty=TRUE)
print(z$status |> count(state,reason),n=Inf)
quit(status=0L,save='no')
}
all_status<-list();fits<-entries<-list();seen<-character()
for(shard in 1:3) {
 shard_dir<-file.path(out,'native-fit-shards',paste0('shard-',shard));path<-file.path(shard_dir,'fits.rds')
 receipt<-jsonlite::fromJSON(file.path(shard_dir,'receipt.json'));stopifnot(receipt$sha256==digest::digest(file=path,algo='sha256'))
 payload<-readRDS(path);stopifnot(identical(payload$result$source_hashes,bindings),!any(payload$scope%in%seen),setequal(payload$scope,payload$result$status$fixture_id))
 seen<-c(seen,payload$scope);all_status[[as.character(shard)]]<-payload$result$status
 fits<-c(fits,payload$result$fits);entries<-c(entries,payload$entries)
}
stopifnot(setequal(seen,fixtures$fixture_id),!anyDuplicated(seen),!anyDuplicated(names(fits)))
z<-list(status=bind_rows(all_status) |> arrange(slot),fits=fits,native_policy=policy,source_hashes=bindings,analysis_quality_accepted=FALSE,historical_admission=FALSE)
write_csv(fixtures,file.path(out,'fixtures.csv'))
chunk_dir<-file.path(out,'native-chunks');dir.create(chunk_dir,showWarnings=FALSE)
path<-file.path(chunk_dir,'native-repair.rds');saveRDS(z,path)
jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256')),file.path(chunk_dir,'recent-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
path<-file.path(out,'native-forecasts.rds');saveRDS(list(entries=entries),path)
jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256')),file.path(out,'native-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
# Existing source-specific Euro coverage API owns freshness/tie/cutoff diagnostics.
version<-input$source_versions$euro
src<-beidan:::dataset_table_source('source_euro_issue_26104','euro_history',version=version)
beidan:::verify_table_files(src$files,src$hashes,'euro_history')
quotes<-dataset_query('source_euro_issue_26104',"SELECT fixture_id,source,company_id,source_order,quote_at,odds_home,odds_draw,odds_away,valid_decimal FROM euro_history ORDER BY fixture_id,source,company_id,source_order",'euro_history',version=version,memory_limit='1GB',threads=2L)
latest<-coverage<-list();resources<-read_dataset('source_euro_issue_26104','resources',version=version)
for(i in seq_len(nrow(fixtures)))for(provider in c('titan','nowscore')) {
 f<-fixtures[i,];state<-resources |> filter(fixture_id==f$fixture_id,source==provider)
 stopifnot(nrow(state)==1L,state$state=='VERIFIED')
 rows<-quotes |> filter(fixture_id==f$fixture_id,source==provider) |> select(-fixture_id,-source)
 frame<-reticulate::r_to_py(arrow::Table$create(rows))$to_pandas()
 epoch<-shared$Cutoff$decision_epoch('26104',format(f$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
 a<-coverage_backend$inspect_euro_coverage(frame,list(fixture_id=f$fixture_id,issue_id='26104',source=provider),epoch,'PARSED',bindings,list('281','115','82','432'),48,implementation_root)
 pa<-reticulate::import('pyarrow',convert=FALSE)
 key<-paste(f$fixture_id,provider)
 latest[[key]]<-as_tibble(arrow::as_arrow_table(pa$Table$from_pandas(a$latest,preserve_index=FALSE))) |> mutate(fixture_id=f$fixture_id,source=provider,.before=1)
 coverage[[key]]<-as_tibble(arrow::as_arrow_table(pa$Table$from_pandas(a$coverage,preserve_index=FALSE)))
}
saveRDS(list(latest=bind_rows(latest),coverage=bind_rows(coverage),input_hashes=bindings),file.path(out,'coverage-census.rds'))
write_csv(z$status,file.path(out,'native-status.csv'))
print(z$status |> count(state,reason),n=Inf)
