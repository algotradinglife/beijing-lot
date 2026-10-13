# Matched-source sensitivity and partial-market controls; no production selection.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-diagnostic-iterations-20261013/library'))
out<-file.path(root,'results/fm17-diagnostic-iterations-20261013');src<-file.path(root,'results/fm17-three-issues-20261013')
ev<-fromJSON(file.path(src,'evaluation.json'));m<-fromJSON(file.path(src,'manifest.json'))
stopifnot(digest::digest(file=file.path(src,'forecasts.rds'),algo='sha256')==m$forecast_sha256,digest::digest(file=file.path(src,'scores.csv'),algo='sha256')==ev$scores_sha256,digest::digest(file=file.path(src,'labels.csv'),algo='sha256')==ev$labels_csv_sha256)
x<-readRDS(file.path(src,'forecasts.rds'));s<-readRDS(file.path(root,'results/fm16-three-issues-20261012/stage.rds'))
stopifnot(digest::digest(file=file.path(root,'results/fm16-three-issues-20261012/stage.rds'),algo='sha256')==m$source_hashes$parent_stage)
r1<-fromJSON(file.path(out,'round1-receipt.json'))
stopifnot(all(map_chr(file.path(out,r1$outputs$path),~digest::digest(file=.x,algo='sha256'))==r1$outputs$sha256))
metrics<-scores<-list();batches<-list()
labels<-read_csv(file.path(src,'labels.csv'),col_types=cols(fixture_id=col_character(),score=col_character(),actual_outcome=col_character()))
old_scores<-read_csv(file.path(src,'scores.csv'),show_col_types=FALSE) |> filter(issue_id=='ALL',cohort=='all')
for(kind in c('native','partial')) {
 manifest<-fromJSON(file.path(out,paste0('round3-',kind,'-manifest.json')))
 replay<-fromJSON(file.path(out,paste0('round3-',kind,'-replay.json')))
 path<-file.path(out,paste0('round3-',kind,'-forecasts.rds'))
 stopifnot(digest::digest(file=path,algo='sha256')==manifest$forecast_sha256,replay$status=='FULL_IDENTICAL_REPLAY',replay$sha256==manifest$forecast_sha256)
 batch<-readRDS(path);batches[[kind]]<-batch
 population<-names(batch$entries)
 p<-bind_rows(batch$probabilities |> select(fixture_id,model,outcome,probability),x$probabilities |> filter(fixture_id%in%population) |> select(fixture_id,model,outcome,probability))
 for(mode in c('same_cutoff','near_sale')) {
  bd_name<-if(mode=='same_cutoff')'北单-T24'else'北单-后期SP'
  bd<-old_scores |> filter(comparison==mode,model==bd_name)
  ids<-Reduce(intersect,list(labels$fixture_id,bd$fixture_id,population))
  for(issue in c('ALL','26098','26101','26102'))for(cohort in if(kind=='native')'all'else c('all','native','market')) {
   use<-ids
   if(issue!='ALL')use<-use[startsWith(use,paste0(issue,':'))]
   if(cohort!='all')use<-intersect(use,x$audit$fixture_id[x$audit$selected_source==cohort])
   if(!length(use))next
   d<-beidan:::DcAccuracyDiagnostic(p |> filter(fixture_id%in%use),labels |> filter(fixture_id%in%use) |> select(fixture_id,actual_outcome))
   z<-bd |> filter(fixture_id%in%use)
   metric<-bind_rows(d$summary,tibble(model=bd_name,n=nrow(z),hits1=sum(z$top1),hits2=sum(z$top2),top1=mean(z$top1),top2=mean(z$top2),brier=mean(z$brier),logloss=mean(z$logloss)))
   key<-paste(kind,mode,issue,cohort)
   metrics[[key]]<-metric |> mutate(experiment=kind,comparison=mode,issue_id=issue,cohort=cohort,.before=1)
   scores[[key]]<-d$scores |> mutate(experiment=kind,comparison=mode,issue_id=issue,cohort=cohort,.before=1)
  }
 }
}
metrics<-bind_rows(metrics);scores<-bind_rows(scores)
# Prediction-only native-window sensitivity, never label-conditioned.
na<-batches$native$audit |> select(fixture_id,model,alpha,lambda_home,lambda_away,lambda_difference)
nr<-batches$native$probabilities |> group_by(fixture_id,model) |> arrange(rank,.by_group=TRUE) |> summarise(top1=first(outcome),pair=paste(sort(outcome[1:2]),collapse='+'),.groups='drop')
ns<-na |> left_join(nr,by=c('fixture_id','model'),relationship='one-to-one') |>
 group_by(fixture_id) |> summarise(lambda_diff_min=min(lambda_difference),lambda_diff_max=max(lambda_difference),direction_flips=lambda_diff_min<0&&lambda_diff_max>0,top1_changes=n_distinct(top1)>1,top2_changes=n_distinct(pair)>1,.groups='drop')
fi<-read_csv(file.path(out,'round1-fixtures.csv'),show_col_types=FALSE)
ordinary_draw<-fi |> group_by(selected_source,competition_type) |> summarise(n=n(),predicted_draw=mean(ordinary_draw),observed_draw=mean(actual_margin==0),ordinary_draw_brier=mean((ordinary_draw-(actual_margin==0))^2),.groups='drop')
write_csv(ordinary_draw,file.path(out,'ordinary-draw-diagnostic.csv'))
write_csv(metrics,file.path(out,'round3-metrics.csv'));write_csv(scores,file.path(out,'round3-scores.csv'));write_csv(ns,file.path(out,'round3-native-stability.csv'))
ages<-list()
for(id in names(batches$native$entries)) {
 e<-batches$native$entries[[id]];n<-e$results[['NATIVE_ALPHA_50']]$native
 for(i in seq_along(n$receipts)) {
  r<-n$receipts[[i]]
  ages[[paste(id,i)]]<-tibble(fixture_id=id,role=n$components[[i]]$role,cutoff_utc=e$cutoff$cutoff_utc,max_score_proxy_utc=lubridate::ymd_hms(r$maximum_source_time,tz='UTC'),latest_score_proxy_lag_days=as.numeric(difftime(e$cutoff$cutoff_utc,lubridate::ymd_hms(r$maximum_source_time,tz='UTC'),units='days')),matches=n$rates$matches[n$rates$role==n$components[[i]]$role])
 }
}
write_csv(bind_rows(ages),file.path(out,'round3-native-history-ages.csv'))
# Concrete case profiles: full frozen margins, quote facts and actual projection.
casepack<-readRDS(file.path(out,'round1-cases.rds'))
caseprob<-x$probabilities |> filter(fixture_id%in%casepack$cases$fixture_id)
caseprob<-bind_rows(caseprob,batches$native$probabilities |> filter(fixture_id%in%casepack$cases$fixture_id),batches$partial$probabilities |> filter(fixture_id%in%casepack$cases$fixture_id))
write_csv(caseprob,file.path(out,'round3-case-probabilities.csv'))
case_margins<-list()
for(kind in names(batches))for(id in intersect(names(batches[[kind]]$entries),casepack$cases$fixture_id))for(model in names(batches[[kind]]$entries[[id]]$results)) {
 case_margins[[paste(kind,id,model)]]<-batches[[kind]]$entries[[id]]$results[[model]]$final$margins |> mutate(fixture_id=id,stage=model,.before=1)
}
write_csv(bind_rows(case_margins),file.path(out,'round3-case-margins.csv'))
write_json(list(round=3,formal_FM17_changed=FALSE,target_label_optimization=FALSE,prior_history_refit=TRUE,native_population=length(batches$native$entries),partial_population=length(batches$partial$entries),parent_forecast_sha256=m$forecast_sha256,native_forecast_sha256=digest::digest(file=file.path(out,'round3-native-forecasts.rds'),algo='sha256'),partial_forecast_sha256=digest::digest(file=file.path(out,'round3-partial-forecasts.rds'),algo='sha256'),client_sha256=digest::digest(file=file.path(root,'r/fm17_diagnostic_round3_evaluate.R'),algo='sha256'),outputs=tibble(path=c('round3-metrics.csv','round3-scores.csv','round3-native-stability.csv','round3-case-probabilities.csv','ordinary-draw-diagnostic.csv','round3-case-margins.csv','round3-native-history-ages.csv'),sha256=map_chr(file.path(out,c('round3-metrics.csv','round3-scores.csv','round3-native-stability.csv','round3-case-probabilities.csv','ordinary-draw-diagnostic.csv','round3-case-margins.csv','round3-native-history-ages.csv')),~digest::digest(file=.x,algo='sha256')))),file.path(out,'round3-evaluation.json'),auto_unbox=TRUE,pretty=TRUE)
print(metrics |> filter(issue_id=='ALL',comparison=='near_sale') |> select(experiment,cohort,model,n,hits1,hits2,brier,logloss),n=30,width=Inf)
print(ns |> summarise(n=n(),direction_flips=sum(direction_flips),top1_changes=sum(top1_changes),top2_changes=sum(top2_changes)))
