# Rscript r/fm171_26103_sp_freeze.R ROOT [replay]
# Shared explicit admission of observed prematch reference SP. Never settlement SP.
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);setwd(root);replay<-length(args)>1L&&args[2]=='replay'
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,'r_lib'))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
invisible(beidan::python_backend(file.path(root,'.venv/bin/python')))
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
pd<-reticulate::import('pandas',convert=FALSE);pl<-reticulate::import('pathlib',convert=FALSE)
out<-file.path(root,'results/fm171-26103-draw-20261017')
q<-jsonlite::fromJSON(file.path(out,'sp-observed-inputs.json'),simplifyVector=FALSE)
stopifnot(q$network_attempts==0)
shared$verify_implementation_closure(pl$Path(root),q$implementation)
fixtures<-read_csv(file.path(out,'fixtures.csv'),col_types=cols(.default=col_character(),handicap=col_double(),slot=col_integer(),kickoff_at=col_datetime(),cutoff_utc=col_datetime()))
quotes<-bind_rows(q$quotes) |> mutate(quote_at=lubridate::ymd_hms(quote_at,tz='UTC'),scheduled_kickoff=lubridate::ymd_hms(scheduled_kickoff,tz='UTC'))
stopifnot(all(quotes$sp_raw>0),!anyNA(quotes))
bound<-quotes |> left_join(fixtures |> select(fixture_id,native_id=provider_id,target_handicap=handicap,target_kickoff=kickoff_at),by='fixture_id',relationship='many-to-one') |>
 mutate(identity_matches=provider_id==native_id & handicap==target_handicap & scheduled_kickoff==target_kickoff)
write_csv(bound |> filter(!identity_matches|is.na(identity_matches)),file.path(out,'sp-identity-rejections.csv'))
quotes<-bound |> filter(identity_matches) |> select(fixture_id,outcome,quote_at,sp_raw,raw_sha256,receipt_sha256) |> distinct()
bindings<-list(input=digest::digest(file=file.path(out,'sp-observed-inputs.json'),algo='sha256'),fixtures=digest::digest(file=file.path(out,'fixtures.csv'),algo='sha256'),
 client=digest::digest(file='r/fm171_26103_sp_freeze.R',algo='sha256'))
probabilities<-audit<-receipts<-list()
for(id in fixtures$fixture_id) {
 f<-fixtures |> filter(fixture_id==id);h<-quotes |> filter(fixture_id==id)
 if(!nrow(h))next
 h<-h |> mutate(row_key=paste(fixture_id,outcome,quote_at,raw_sha256,sep=':'),issue_code='SP_CAPTURE',issue_year=2026L,
  label_available_ts=format(quote_at,'%Y-%m-%dT%H:%M:%OS6Z',tz='UTC'),data_available_ts=label_available_ts)
 stopifnot(!anyDuplicated(h$row_key))
 for(mode in c('same_cutoff','later_prematch')) {
  cutoff_time<-if(mode=='same_cutoff')f$cutoff_utc else f$kickoff_at
  cutoff<-shared$Cutoff$decision_epoch('26103',format(cutoff_time,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
  frame<-pd$DataFrame(jsonlite::fromJSON(jsonlite::toJSON(h,dataframe='rows',auto_unbox=TRUE,digits=NA,POSIXt='ISO8601'),simplifyVector=FALSE))
  ctx<-tryCatch(shared$prepare_learning_context(frame,cutoff,source_hashes=c(bindings,list(mode=beidan:::.score_margin_hash(mode),fixture=beidan:::.score_margin_hash(id))),repository_root=pl$Path(root),
   implementation_modules=list('beidan_backend.temporal_learning.issue_partitions'),implementation_distributions=list('numpy','pandas'),
   availability=shared$AvailabilityFilter(shared$AvailabilityPolicy$observed('SAVED_PREMATCH_REFERENCE_SP_CAPTURE'),data_available_column='data_available_ts'),
   intended_use='HISTORICAL_DIAGNOSTIC',partition_policy=shared$PartitionPolicy('FIXED_PRIOR_FIT',0L,0L,1L),weighting_policy=shared$WeightingPolicy$expanding_equal(minimum_ess=1)),error=function(e)e)
  if(inherits(ctx,'error')) {
   if(!grepl('cutoff admits no prior observations',conditionMessage(ctx)))stop(ctx)
   next
  }
  admitted<-bind_rows(jsonlite::fromJSON(reticulate::py_to_r(ctx$partitions[['fit']]$to_json(orient='records',date_format='iso',double_precision=15L)),simplifyVector=FALSE)) |>
   mutate(quote_at=lubridate::ymd_hms(quote_at,tz='UTC'))
  latest<-admitted |> filter(quote_at==max(quote_at)) |> distinct(outcome,sp_raw,quote_at)
  if(nrow(latest)!=3||!setequal(latest$outcome,c('W','D','L')))stop('Conflicting or incomplete latest observed SP vector: ',id)
  p<-latest |> mutate(probability=(1/sp_raw)/sum(1/sp_raw),fixture_id=id,model=if(mode=='same_cutoff')'BD_T24'else'BD_LATER_PREMATCH')
  probabilities[[paste(id,mode)]]<-p |> select(fixture_id,model,outcome,probability)
  receipt<-reticulate::py_to_r(ctx$receipt$payload)
  audit[[paste(id,mode)]]<-tibble(fixture_id=id,mode=mode,quote_at=max(latest$quote_at),selection_cutoff=cutoff_time,kickoff_at=f$kickoff_at,
   lead_hours=as.numeric(difftime(f$kickoff_at,max(latest$quote_at),units='hours')),uniform=length(unique(latest$sp_raw))==1L)
  receipts[[paste(id,mode)]]<-list(receipt=receipt,admitted=admitted,selected=latest)
 }
}
x<-list(probabilities=bind_rows(probabilities),audit=bind_rows(audit),receipts=receipts,bindings=bindings)
path<-file.path(out,'sp-forecasts.rds')
if(replay) {
 stopifnot(identical(x,readRDS(path)));jsonlite::write_json(list(status='FULL_IDENTICAL_REPLAY',sha256=digest::digest(file=path,algo='sha256')),file.path(out,'sp-replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else {
 if(file.exists(path))stopifnot(identical(x,readRDS(path)))else saveRDS(x,path)
 write_csv(x$audit,file.path(out,'sp-audit.csv'));jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256'),bindings=bindings),file.path(out,'sp-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
print(x$audit |> group_by(mode) |> summarise(fixtures=n(),uniform=sum(uniform),min_lead=min(lead_hours),max_lead=max(lead_hours),.groups='drop'))
