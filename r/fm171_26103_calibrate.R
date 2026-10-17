# Rscript r/fm171_26103_calibrate.R ROOT [replay]
# Fixed prior-issue domain calibration. All chronology/weights/receipts are shared.
args<-commandArgs(TRUE);root<-normalizePath(args[1],mustWork=TRUE);setwd(root);replay<-length(args)>1L&&args[2]=='replay'
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,'r_lib'))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
invisible(beidan::python_backend(file.path(root,'.venv/bin/python')))
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
core<-reticulate::import('beidan_backend.temporal_learning.core',convert=FALSE)
clock<-reticulate::import('beidan_backend.temporal_learning.diagnostic_labels',convert=FALSE)
models<-reticulate::import('beidan_backend.temporal_learning.issue_partitions',convert=FALSE)
adjustment<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
pd<-reticulate::import('pandas',convert=FALSE);pl<-reticulate::import('pathlib',convert=FALSE)
out<-file.path(root,'results/fm171-26103-draw-20261017');prior_dir<-file.path(root,'results/fm171-draw-calibration-20261017')
policy<-jsonlite::fromJSON('config/fm171_draw_history_study.json');study<-jsonlite::fromJSON('config/fm171_26103_draw_study.json')
stopifnot(identical(study$prior_issues,c('26098','26101','26102')),identical(study$calibration_models,'GLOBAL'),study$pseudocount_matches==policy$pseudocount_matches)
nm<-jsonlite::fromJSON(file.path(out,'native-manifest.json'));nr<-jsonlite::fromJSON(file.path(out,'native-replay.json'))
stopifnot(nr$status=='FULL_IDENTICAL_REPLAY',nr$sha256==nm$sha256,digest::digest(file=file.path(out,'native-forecasts.rds'),algo='sha256')==nm$sha256)
x<-readRDS(file.path(out,'native-forecasts.rds'))
pm<-jsonlite::fromJSON(file.path(prior_dir,'manifest.json'));pr<-jsonlite::fromJSON(file.path(prior_dir,'replay.json'))
stopifnot(pr$status=='FULL_IDENTICAL_REPLAY',pr$sha256==pm$sha256,digest::digest(file=file.path(prior_dir,'forecasts.rds'),algo='sha256')==pm$sha256)
prior<-readRDS(file.path(prior_dir,'forecasts.rds'))
label_path<-file.path(root,'results/fm17-three-issues-20261013/labels.csv')
stopifnot(digest::digest(file=label_path,algo='sha256')==prior$bindings$labels)
labels<-read_csv(label_path,col_types=cols(.default=col_character()))
observed<-read_csv(file.path(prior_dir,'label-source-observations.csv'),col_types=cols(issue_id=col_character(),observed_label_ts=col_character()))
history<-prior$audit |> filter(model=='GLOBAL_D48') |> select(fixture_id,issue_code=issue_id,decision_ts=cutoff_utc) |>
 inner_join(prior$probabilities |> filter(model=='FM171',outcome=='D') |> select(fixture_id,baseline_draw=probability),by='fixture_id',relationship='one-to-one') |>
 inner_join(labels |> select(fixture_id,actual_outcome),by='fixture_id',relationship='one-to-one') |>
 mutate(draw_target=as.double(actual_outcome=='D'),data_available_ts=decision_ts,issue_year=2026L) |>
 select(-actual_outcome)
stopifnot(nrow(history)==322L,!anyDuplicated(history$fixture_id),all(history$issue_code%in%study$prior_issues),!study$target_issue%in%history$issue_code,!anyNA(history))
bindings<-list(native=nm$sha256,prior_forecasts=pm$sha256,prior_labels=digest::digest(file=label_path,algo='sha256'),
 client=digest::digest(file='r/fm171_26103_calibrate.R',algo='sha256'),policy=digest::digest(file='config/fm171_draw_history_study.json',algo='sha256'),
 study=digest::digest(file='config/fm171_26103_draw_study.json',algo='sha256'),prior_client=digest::digest(file='r/fm171_draw_history_freeze.R',algo='sha256'),
 observed_label_sources=digest::digest(file=file.path(prior_dir,'label-source-observations.csv'),algo='sha256'),
 direction_implementation=beidan:::.score_margin_code(root))
horizon<-shared$Cutoff$decision_epoch('DIAGNOSTIC_CLOCK_HORIZON',policy$clock_horizon)
by_delay<-list()
for(delay in study$diagnostic_label_delays_hours) {
 h<-history;h$label_available_ts<-map_chr(h$decision_ts,~reticulate::py_to_r(clock$diagnostic_label_clock(.x,cutoff=horizon,delay_hours=delay)))
 by_delay[[as.character(delay)]]<-h
}
entries<-audit<-list();probabilities<-list(FM171=x$probabilities |> filter(model=='FM171'))
for(id in names(x$entries)) {
 e<-x$entries[[id]];f<-x$audit |> filter(fixture_id==id);ct<-format(e$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
 cutoff<-shared$Cutoff$decision_epoch('26103',ct);results<-list(FM171=e$final)
 original<-x$probabilities |> filter(fixture_id==id,model=='FM171') |> select(outcome,probability)
 for(delay in study$diagnostic_label_delays_hours) {
  name<-paste0('GLOBAL_D',delay);h<-by_delay[[as.character(delay)]]
  frame<-pd$DataFrame(jsonlite::fromJSON(jsonlite::toJSON(h,dataframe='rows',auto_unbox=TRUE,digits=NA),simplifyVector=FALSE))
  sources<-c(bindings,list(history_frame=reticulate::py_to_r(core$stable_frame_hash(frame)),nominated=beidan:::.score_margin_hash(study$prior_issues),delay=beidan:::.score_margin_hash(delay)))
  ctx<-shared$prepare_learning_context(frame,cutoff,source_hashes=sources,repository_root=pl$Path(root),
   implementation_modules=list('beidan_backend.temporal_learning.issue_partitions','beidan_backend.temporal_learning.diagnostic_labels'),implementation_distributions=list('numpy','pandas'),
   availability=shared$AvailabilityFilter(shared$AvailabilityPolicy$historical_proxy('FM171_DECISION_PLUS_DELAY_NOT_OBSERVED'),data_available_column='data_available_ts'),
   intended_use='HISTORICAL_DIAGNOSTIC',partition_policy=shared$PartitionPolicy('FIXED_PRIOR_FIT',0L,0L,1L),
   weighting_policy=shared$WeightingPolicy$expanding_equal(minimum_ess=policy$minimum_global_ess))
  admitted<-bind_rows(jsonlite::fromJSON(reticulate::py_to_r(ctx$partitions[['fit']]$to_json(orient='records',date_format='iso',double_precision=15L)),simplifyVector=FALSE))
  weights<-as.numeric(reticulate::py_to_r(ctx$weights$to_numpy()))
  stopifnot(all(admitted$issue_code%in%study$prior_issues),!any(admitted$issue_code=='26103'),length(weights)==nrow(admitted),
   min(sum(admitted$draw_target==1),sum(admitted$draw_target==0))>=policy$minimum_global_class_count)
  # Same fixed domain moment-shrinkage formula as the previously frozen GLOBAL candidate; no tuning.
  n<-sum(weights);mu<-weighted.mean(admitted$baseline_draw,weights);observed_rate<-weighted.mean(admitted$draw_target,weights)
  shrunk<-(n*observed_rate+policy$pseudocount_matches*mu)/(n+policy$pseudocount_matches)
  delta<-qlogis(shrunk)-qlogis(mu)
  params<-list(model='GLOBAL',delay_hours=delay,n=n,mu=mu,observed=observed_rate,shrunk=shrunk,delta=delta,pseudocount_matches=policy$pseudocount_matches)
  receipt<-reticulate::py_to_r(models$bind_model_receipt(ctx,cutoff,model_identity='FM171_DRAW_HISTORY_GLOBAL',model_parameters=params))
  receipt$R_bindings<-bindings;receipt$parameters<-params
  ledger<-bind_rows(jsonlite::fromJSON(reticulate::py_to_r(ctx$weight_ledger$to_json(orient='records',date_format='iso',double_precision=15L)),simplifyVector=FALSE));ledger$fixture_id<-admitted$fixture_id
  p<-original$probability[original$outcome=='D'];q<-plogis(qlogis(p)+delta)
  target<-original |> mutate(probability=if_else(outcome=='D',q,(1-q)*probability/(1-p)))
  base<-list(grid=e$final$grid |> select(home_goals,away_goals,probability),cutoff=e$cutoff,model_id='FM171_PLUS_GLOBAL_HISTORY',source_hashes=bindings,
   max_source_available_utc=max(e$base$max_source_available_utc,lubridate::ymd_hms(receipt$maximum_source_time,tz='UTC'),
    lubridate::ymd_hms(receipt$maximum_training_label_timestamp,tz='UTC')),intended_use='HISTORICAL_DIAGNOSTIC')
  dd<--as.integer(f$handicap);eid<-'prior-draw-calibration'
  judgement<-list(model_id=name,rationale='Frozen prior-only historical let-draw log-odds residual; preserve both complete side proportions',
   bins=tibble(bin_id=c('lower','draw','upper'),min_margin=c(-Inf,dd,dd+1),max_margin=c(dd-1,dd,Inf),
    target_mass=target$probability[match(c('L','D','W'),target$outcome)],evidence_id=eid,reason='Fixed prior-only empirical-rate calibration'))
  time<-format(base$max_source_available_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
  rows<-list(list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(receipt),row_key=eid,issue_code='PRIOR_CALIBRATION_EVIDENCE',issue_year=2026L,label_available_ts=time,data_available_ts=time))
  binding<-c(bindings,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(judgement),fitted_model=beidan:::.score_margin_hash(receipt)))
  score_ctx<-adjustment$build_adjustment_evidence_context(rows,as.list(e$fixture),cutoff,binding,shared$AvailabilityPolicy$historical_proxy('FM171_EMPIRICAL_DRAW_DIAGNOSTIC_ONLY'),'HISTORICAL_DIAGNOSTIC',root)
  final<-adjust_score_margin_distribution(base,judgement,score_ctx,e$fixture,e$cutoff,root)
  projected<-project_score_outcomes(final,as.integer(f$handicap),root) |> select(outcome,probability)
  stopifnot(max(abs(projected$probability[match(target$outcome,projected$outcome)]-target$probability))<1e-10)
  results[[name]]<-list(final=final,receipt=receipt,admitted=admitted,ledger=ledger)
  probabilities[[paste(id,name)]]<-projected |> mutate(fixture_id=id,model=name,.before=1)
  observed_history<-history |> left_join(observed |> transmute(issue_code=issue_id,observed_label_ts),by='issue_code',relationship='many-to-one')
  observed_clock<-lubridate::ymd_hms(observed_history$observed_label_ts,tz='UTC')
  audit[[paste(id,name)]]<-tibble(fixture_id=id,model=name,delay_hours=delay,training_n=n,delta=delta,original_draw=p,calibrated_draw=q,cutoff_utc=ct,
   observed_prior_labels_before_cutoff=sum(observed_clock<e$cutoff$cutoff_utc),
   maximum_source_time=receipt$maximum_source_time,maximum_label_time=receipt$maximum_training_label_timestamp)
 }
 entries[[id]]<-list(fixture=e$fixture,cutoff=e$cutoff,results=results)
 if(length(entries)%%50==0)message('Calibrated ',length(entries))
}
batch<-list(entries=entries,probabilities=bind_rows(probabilities),audit=bind_rows(audit),bindings=bindings)
path<-file.path(out,'calibrated-forecasts.rds')
if(replay) {
 stopifnot(identical(batch,readRDS(path)));jsonlite::write_json(list(status='FULL_IDENTICAL_REPLAY',forecasts=length(entries),sha256=digest::digest(file=path,algo='sha256')),file.path(out,'calibration-replay.json'),auto_unbox=TRUE,pretty=TRUE)
}else {
 if(file.exists(path))stopifnot(identical(batch,readRDS(path)))else saveRDS(batch,path)
 write_csv(batch$probabilities,file.path(out,'probabilities.csv'));write_csv(batch$audit,file.path(out,'calibration-audit.csv'))
 jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256'),bindings=bindings,forecasts=length(entries),prior_issues=study$prior_issues,target_labels_admitted=FALSE,
  retrospective_label_catalog_opened=TRUE,observed_availability_validated=FALSE,versions_modified=FALSE),file.path(out,'calibration-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
}
print(batch$audit |> group_by(model) |> summarise(fixtures=n(),min_history=min(training_n),max_history=max(training_n),min_delta=min(delta),max_delta=max(delta),.groups='drop'))
