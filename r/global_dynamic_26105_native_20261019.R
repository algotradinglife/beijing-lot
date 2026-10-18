# Rscript r/global_dynamic_26105_native_20261019.R ROOT IMPLEMENTATION_ROOT fit SHARD COUNT | ROOT IMPLEMENTATION_ROOT assemble
# Replays published factual bytes/metadata; no labels, source collection or priors.
args<-commandArgs(TRUE);stopifnot(length(args)%in%c(3L,5L),args[3]%in%c('fit','assemble'))
mode<-args[3]
if(mode=='fit'){stopifnot(length(args)==5L);shard<-as.integer(args[4]);shards<-as.integer(args[5]);stopifnot(!anyNA(c(shard,shards)),shards==3L,shard>=1L,shard<=shards)}else stopifnot(length(args)==3L)
root<-normalizePath(args[1],mustWork=TRUE);implementation_root<-normalizePath(args[2],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse));library(beidan)
invisible(python_backend(file.path(root,'.venv/bin/python')))
paths<-reticulate::import('beidan_backend.catalog.paths',convert=FALSE)
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend<-reticulate::import('beidan_backend.reviewed_opponent_goals',convert=FALSE)
coverage_backend<-reticulate::import('beidan_backend.euro_coverage',convert=FALSE)
pd<-reticulate::import('pandas',convert=FALSE)
out<-reticulate::py_str(paths$location('hot:global-dynamic-26105-20261019'))
input_path<-file.path(out,'inputs.json');metadata_path<-reticulate::py_str(paths$location('hot:global-dynamic-26105-history-metadata-20261018-v2/metadata.json'))
inventory_path<-reticulate::py_str(paths$location('hot:global-dynamic-26105-channel-inventory-20261018/inventory.json'))
receipt_path<-file.path(out,'intake-receipt.json')
input_bytes<-readBin(input_path,'raw',n=file.info(input_path)$size)
metadata_bytes<-readBin(metadata_path,'raw',n=file.info(metadata_path)$size)
receipt_bytes<-readBin(receipt_path,'raw',n=file.info(receipt_path)$size)
input_sha<-digest::digest(input_bytes,serialize=FALSE,algo='sha256')
metadata_sha<-digest::digest(metadata_bytes,serialize=FALSE,algo='sha256')
receipt_sha<-digest::digest(receipt_bytes,serialize=FALSE,algo='sha256')
inventory_sha<-digest::digest(file=inventory_path,algo='sha256')
client_sha<-digest::digest(file='r/global_dynamic_26105_native_20261019.R',algo='sha256')
input<-jsonlite::fromJSON(rawToChar(input_bytes),simplifyVector=FALSE)
metadata<-jsonlite::fromJSON(rawToChar(metadata_bytes),simplifyVector=FALSE)
intake_receipt<-jsonlite::fromJSON(rawToChar(receipt_bytes),simplifyVector=FALSE)
if(!identical(intake_receipt$input_sha256,input_sha))stop('Intake receipt input hash mismatch')
if(input_sha!=digest::digest(file=input_path,algo='sha256') || metadata_sha!=digest::digest(file=metadata_path,algo='sha256') || receipt_sha!=digest::digest(file=receipt_path,algo='sha256') || inventory_sha!=digest::digest(file=inventory_path,algo='sha256'))stop('Native source changed during intake')
stopifnot(identical(intake_receipt$source_versions,input$source_versions),identical(intake_receipt$input_bindings,input$input_bindings))
if(mode=='assemble' && any(file.exists(file.path(out,c('fixtures.csv','native-chunks','native-forecasts.rds','native-manifest.json','coverage-census.rds','native-status.csv')))))stop('Immutable assembled output exists')
stopifnot(metadata$inventory_sha256==inventory_sha,metadata$issue_id=='26105',input$issue_id=='26105',metadata$network_attempts==0L,length(metadata$packets)==365L)
raw_fixtures<-as_tibble(jsonlite::fromJSON(rawToChar(input_bytes),simplifyVector=TRUE)$fixtures)
for(column in c('kickoff_at','cutoff_utc'))if(!is.character(raw_fixtures[[column]])&&!all(is.na(raw_fixtures[[column]])))stop('Source timestamps must be strings or actual missing values')
fixtures<-raw_fixtures |> mutate(kickoff_at=lubridate::ymd_hms(kickoff_at,tz='UTC',quiet=TRUE),cutoff_utc=lubridate::ymd_hms(cutoff_utc,tz='UTC',quiet=TRUE),handicap=as.integer(handicap))
if(any(!is.na(raw_fixtures$kickoff_at)&is.na(fixtures$kickoff_at))||any(!is.na(raw_fixtures$cutoff_utc)&is.na(fixtures$cutoff_utc)))stop('Invalid source kickoff or cutoff timestamp')
stopifnot(nrow(fixtures)==365L,!anyDuplicated(fixtures$fixture_id),identical(is.na(fixtures$kickoff_at),is.na(fixtures$cutoff_utc)),all(fixtures$cutoff_utc[!is.na(fixtures$cutoff_utc)]==fixtures$kickoff_at[!is.na(fixtures$kickoff_at)]-lubridate::hours(24)),!anyDuplicated(map_chr(metadata$packets,'fixture_id')),setequal(map_chr(metadata$packets,'fixture_id'),fixtures$fixture_id))
# Whole-issue inputs stay identical across workers; only target identities are sharded.
# Target and every known following issue ID are excluded regardless of source dates.
future_path<-reticulate::py_str(paths$location('hot:global-dynamic-26106-probe-20261019/future-exclusions.json'))
future_bytes<-readBin(future_path,'raw',n=file.info(future_path)$size)
future_sha<-digest::digest(future_bytes,serialize=FALSE,algo='sha256')
future_packet<-jsonlite::fromJSON(rawToChar(future_bytes),simplifyVector=FALSE)
checkmate::assert_choice(future_packet$coverage_state,c('VERIFIED_ROSTER','REQUEST_FAILED'))
stopifnot(identical(future_packet$target_issue,'26105'),identical(future_packet$following_issue,'26106'))
if(future_packet$coverage_state=='REQUEST_FAILED') {
 stopifnot(identical(future_packet$has_verified_future_roster,FALSE),'data'%in%names(future_packet$result),is.list(future_packet$result$data),length(future_packet$result$data)==0L,length(future_packet$observations)>0L)
 for(observation in future_packet$observations) {
  path<-file.path(root,observation$receipt_path);log_path<-file.path(root,observation$log_path)
  checkmate::assert_string(observation$receipt_sha256,pattern='^[0-9a-f]{64}$')
  checkmate::assert_string(observation$log_sha256,pattern='^[0-9a-f]{64}$')
  failure_bytes<-readBin(path,'raw',n=file.info(path)$size);log_bytes<-readBin(log_path,'raw',n=file.info(log_path)$size)
  stopifnot(observation$receipt_sha256==digest::digest(failure_bytes,serialize=FALSE,algo='sha256'),observation$log_sha256==digest::digest(log_bytes,serialize=FALSE,algo='sha256'))
  failure<-jsonlite::fromJSON(rawToChar(failure_bytes))
  checkmate::assert_number(failure$exit_status,lower=1,upper=1,finite=TRUE)
  lines<-strsplit(rawToChar(log_bytes),'\n',fixed=TRUE)[[1]]
  terminal<-tail(lines[nzchar(trimws(lines))],1L)
  expected_failure<-'beidan_backend.transport.FetchError: fetching https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&all=1&issueNum=26106 failed after 1 attempt(s): HTTP Error 500: Internal Server Error'
  if(!identical(terminal,expected_failure))stop('Expected terminal26106 HTTP500 failure')
 }
 future<-tibble(issue_id=character(),native_id=character())
} else {
 stopifnot(identical(future_packet$has_verified_future_roster,TRUE))
 future<-bind_rows(future_packet$result$data)
}
future_scope<-list(state=future_packet$coverage_state,exact_target_fixtures=nrow(fixtures),known_future_fixtures=nrow(future),future_issue='26106',intended_use='HISTORICAL_DIAGNOSTIC')
if(!all(c('issue_id','native_id')%in%names(future)))stop('Future roster requires issue_id and native_id')
checkmate::assert_character(future$issue_id,any.missing=FALSE)
checkmate::assert_character(future$native_id,any.missing=FALSE,pattern='^[1-9][0-9]*$')
stopifnot((nrow(future)>0L && future_packet$coverage_state=='VERIFIED_ROSTER') || (nrow(future)==0L && future_packet$coverage_state=='REQUEST_FAILED'),all(future$issue_id=='26106'),!anyDuplicated(future$native_id))
excluded<-unique(c(fixtures$provider_id,as.character(future$native_id)))
stopifnot(!anyNA(excluded))
# Bind each metadata packet to the exact published Titan analysis capture.
provenance<-bind_rows(input$provenance)
for(packet in metadata$packets) {
 checkmate::assert_string(packet$receipt$sha256,pattern='^[0-9a-f]{64}$')
 checkmate::assert_string(packet$receipt$url,min.chars=1L)
 checkmate::assert_string(packet$result$identity$provider_id,pattern='^[1-9][0-9]*$')
 checkmate::assert_string(packet$result$identity$home_id,pattern='^[1-9][0-9]*$')
 checkmate::assert_string(packet$result$identity$away_id,pattern='^[1-9][0-9]*$')
 evidence<-provenance |> filter(fixture_id==packet$fixture_id,source=='titan',url==packet$receipt$url)
 stopifnot(nrow(evidence)==1L,evidence$sha256==packet$receipt$sha256)
 identity<-packet$result$identity;target_fixture<-fixtures |> filter(fixture_id==packet$fixture_id)
 stopifnot(nrow(target_fixture)==1L,identity$provider_id==target_fixture$provider_id,
 identity$home_id==target_fixture$home_id,identity$away_id==target_fixture$away_id)
}
policy<-list(recent_n=8L,alpha=.5,minimum_recent_matches=12L,minimum_recent_ess=8)
fit_policy<-list(ridge=.05,minimum_target_matches=12L,convergence_tolerance=1e-10,maximum_iterations=100000L)
bindings<-list(inputs=input_sha,metadata=metadata_sha,intake_receipt=receipt_sha,inventory=inventory_sha,future=future_sha,client=client_sha)
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
 if(is.na(f$cutoff_utc)) {row$reason<-'Unresolved source kickoff; explicit cutoff unavailable';status[[id]]<-row;next}
 if(is.null(target)||is.null(target$target_competition_id)){status[[id]]<-row;next}
 context<-bind_rows(input$contexts) |> filter(fixture_id==id) |> mutate(kickoff_at=lubridate::ymd_hms(kickoff_at,tz='UTC'))
 schedule<-bind_rows(input$fixture_schedule) |> filter(fixture_id==id,resource=='roster')
 roster_clock<-lubridate::ymd_hms(paste(schedule$kickoff_date,schedule$kickoff_hhmm,'00'),tz='Asia/Shanghai',quiet=TRUE)
 if(nrow(context)!=2L||anyNA(context$kickoff_at)||any(context$kickoff_at!=f$kickoff_at)||length(roster_clock)!=1L||is.na(roster_clock)||roster_clock!=f$kickoff_at) {
  row$reason<-'Unresolved roster/analysis/market kickoff disagreement';status[[id]]<-row;next
 }
 fixture<-as.list(f[1,c('fixture_id','provider_id','home_id','away_id')]);fixture$issue_id<-'26105'
 fixture$competition_id<-target$target_competition_id;fixture$neutral_reported<-isTRUE(target$target_neutral_reported)
 cutoff<-list(issue_id='26105',cutoff_utc=f$cutoff_utc)
 epoch<-shared$Cutoff$decision_epoch('26105',format(f$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
 h<-joined |> filter(metadata_agrees,competition_id==fixture$competition_id) |>
 transmute(row_key=paste(fixture_id,scope,match_id,sep=':'),match_id,event_date,home_id,away_id,home_score,away_score,score_scope,competition_id,neutral_reported)
 domain<-jsonlite::fromJSON(jsonlite::toJSON(h,dataframe='rows',auto_unbox=TRUE,na='null',digits=NA),simplifyVector=FALSE)
 candidate<-tryCatch({
  prepared<-backend$prepare_reviewed_opponent_goals(domain,fixture,as.list(excluded),epoch,bindings,implementation_root,policy)
  if(reticulate::py_to_r(prepared$state)!='PREPARED')stop('Target venue support absent')
  native<-beidan:::FitOpponentGoals(prepared$prepared,fixture,epoch,fit_policy,implementation_root)
  list(native=native,future_exclusion_scope=future_scope,recent_reviews=reticulate::py_to_r(prepared$reviews),policy=policy,preparation_implementation=reticulate::py_to_r(prepared$implementation))
 },error=base::identity)
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
z<-list(status=bind_rows(status),fits=fits,native_policy=policy,future_exclusion_scope=future_scope,source_hashes=bindings,analysis_quality_accepted=FALSE,historical_admission=FALSE)
stopifnot(input_sha==digest::digest(file=input_path,algo='sha256'),metadata_sha==digest::digest(file=metadata_path,algo='sha256'),receipt_sha==digest::digest(file=receipt_path,algo='sha256'),inventory_sha==digest::digest(file=inventory_path,algo='sha256'),future_sha==digest::digest(file=future_path,algo='sha256'),client_sha==digest::digest(file='r/global_dynamic_26105_native_20261019.R',algo='sha256'))
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
z<-list(status=bind_rows(all_status) |> arrange(slot),fits=fits,native_policy=policy,future_exclusion_scope=future_scope,source_hashes=bindings,analysis_quality_accepted=FALSE,historical_admission=FALSE)
stopifnot(input_sha==digest::digest(file=input_path,algo='sha256'),metadata_sha==digest::digest(file=metadata_path,algo='sha256'),receipt_sha==digest::digest(file=receipt_path,algo='sha256'),inventory_sha==digest::digest(file=inventory_path,algo='sha256'),future_sha==digest::digest(file=future_path,algo='sha256'),client_sha==digest::digest(file='r/global_dynamic_26105_native_20261019.R',algo='sha256'))
write_csv(fixtures,file.path(out,'fixtures.csv'))
chunk_dir<-file.path(out,'native-chunks');dir.create(chunk_dir,showWarnings=FALSE)
path<-file.path(chunk_dir,'native-repair.rds');saveRDS(z,path)
jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256')),file.path(chunk_dir,'recent-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
path<-file.path(out,'native-forecasts.rds');saveRDS(list(entries=entries),path)
jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256')),file.path(out,'native-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
# Existing source-specific Euro coverage API owns freshness/tie/cutoff diagnostics.
version<-input$source_versions$euro
src<-beidan:::dataset_table_source('source_euro_issue_26105','euro_history',version=version)
beidan:::verify_table_files(src$files,src$hashes,'euro_history')
quotes<-dataset_query('source_euro_issue_26105',"SELECT fixture_id,source,company_id,source_order,quote_at,odds_home,odds_draw,odds_away,valid_decimal FROM euro_history ORDER BY fixture_id,source,company_id,source_order",'euro_history',version=version,memory_limit='1GB',threads=2L)
unavailable<-fixtures |> filter(is.na(cutoff_utc)) |> select(fixture_id,cutoff_utc) |> tidyr::crossing(source=c('titan','nowscore')) |> mutate(reason='Unresolved source kickoff; explicit cutoff unavailable')
latest<-coverage<-list();resources<-read_dataset('source_euro_issue_26105','resources',version=version)
for(i in seq_len(nrow(fixtures)))for(provider in c('titan','nowscore')) {
 f<-fixtures[i,];if(is.na(f$cutoff_utc))next
 state<-resources |> filter(fixture_id==f$fixture_id,source==provider)
 stopifnot(nrow(state)==1L,state$state=='VERIFIED')
 rows<-quotes |> filter(fixture_id==f$fixture_id,source==provider) |> select(-fixture_id,-source)
 frame<-reticulate::r_to_py(arrow::Table$create(rows))$to_pandas()
 epoch<-shared$Cutoff$decision_epoch('26105',format(f$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
 a<-coverage_backend$inspect_euro_coverage(frame,list(fixture_id=f$fixture_id,issue_id='26105',source=provider),epoch,'PARSED',bindings,list('281','115','82','432'),48,implementation_root)
 pa<-reticulate::import('pyarrow',convert=FALSE)
 key<-paste(f$fixture_id,provider)
 latest[[key]]<-as_tibble(arrow::as_arrow_table(pa$Table$from_pandas(a$latest,preserve_index=FALSE))) |> mutate(fixture_id=f$fixture_id,source=provider,.before=1)
 coverage[[key]]<-as_tibble(arrow::as_arrow_table(pa$Table$from_pandas(a$coverage,preserve_index=FALSE)))
}
stopifnot(input_sha==digest::digest(file=input_path,algo='sha256'),metadata_sha==digest::digest(file=metadata_path,algo='sha256'),receipt_sha==digest::digest(file=receipt_path,algo='sha256'),inventory_sha==digest::digest(file=inventory_path,algo='sha256'),future_sha==digest::digest(file=future_path,algo='sha256'),client_sha==digest::digest(file='r/global_dynamic_26105_native_20261019.R',algo='sha256'))
saveRDS(list(latest=bind_rows(latest),coverage=bind_rows(coverage),unavailable=unavailable,input_hashes=bindings),file.path(out,'coverage-census.rds'))
write_csv(z$status,file.path(out,'native-status.csv'))
print(z$status |> count(state,reason),n=Inf)
