# Descriptive uniform counterfactual and prediction-only rank-stability analysis.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-release-20261013/library'))
out<-file.path(root,'results/fm17-diagnostic-iterations-20261013');src<-file.path(root,'results/fm17-three-issues-20261013')
ev<-fromJSON(file.path(src,'evaluation.json'));m<-fromJSON(file.path(src,'manifest.json'));cm<-fromJSON(file.path(out,'round2-manifest.json'));rp<-fromJSON(file.path(out,'round2-replay.json'))
stopifnot(digest::digest(file=file.path(src,'forecasts.rds'),algo='sha256')==m$forecast_sha256,digest::digest(file=file.path(out,'round2-forecasts.rds'),algo='sha256')==cm$forecast_sha256,rp$status=='FULL_IDENTICAL_REPLAY',rp$sha256==cm$forecast_sha256,digest::digest(file=file.path(src,'scores.csv'),algo='sha256')==ev$scores_sha256,digest::digest(file=file.path(src,'labels.csv'),algo='sha256')==ev$labels_csv_sha256)
x<-readRDS(file.path(src,'forecasts.rds'));cand<-readRDS(file.path(out,'round2-forecasts.rds'))
source<-x$audit |> select(fixture_id,issue_id,selected_source,cutoff_utc)
p<-bind_rows(x$probabilities |> select(fixture_id,model,outcome,probability),cand$probabilities |> select(fixture_id,model,outcome,probability))
# These ablations only reuse already sealed components, with explicit cutoff ledger.
for(kind in c('market','native')) {
 keep_raw<-source$fixture_id[source$selected_source==kind]
 routed<-x$probabilities |> filter((fixture_id%in%keep_raw&model=='FM17-source-before-tail')|(!fixture_id%in%keep_raw&model=='FM-1.7.0')) |> mutate(component=model,model=paste0(toupper(kind),'_RETAIN'))
 ledger<-routed |> distinct(fixture_id,model,component) |> left_join(source,by='fixture_id',relationship='many-to-one')
 stopifnot(nrow(ledger)==346L,!anyNA(ledger$cutoff_utc))
 ledger$component_seal<-map2_chr(ledger$fixture_id,ledger$component,~x$entries[[.x]]$results[[.y]]$final$seal)
 ledger$parent_forecast_sha256<-m$forecast_sha256
 ledger$recipe<-paste0('FIXED_DIAGNOSTIC_RETAIN_',toupper(kind),'_ONLY')
 write_csv(ledger,file.path(out,paste0('round2-',kind,'-component-ledger.csv')))
 p<-bind_rows(p,routed |> select(fixture_id,model,outcome,probability))
}
# Compute warnings before labels are opened: no label participates in this flag.
stability<-p |> group_by(fixture_id,model) |> arrange(desc(probability),match(outcome,c('W','D','L')),.by_group=TRUE) |>
 summarise(top1=first(outcome),pair=paste(sort(outcome[1:2]),collapse='+'),gap12=probability[1]-probability[2],gap23=probability[2]-probability[3],.groups='drop')
flags<-stability |> filter(model%in%c('FM-1.7.0','FM17-source-before-tail')) |> select(fixture_id,model,pair,top1,gap23) |> pivot_wider(names_from=model,values_from=c(pair,top1,gap23)) |>
 mutate(top2_set_changed=`pair_FM-1.7.0`!=`pair_FM17-source-before-tail`,top1_changed=`top1_FM-1.7.0`!=`top1_FM17-source-before-tail`) |> left_join(source,by='fixture_id',relationship='one-to-one')
write_csv(flags,file.path(out,'round2-prediction-only-flags.csv'));write_csv(stability,file.path(out,'round2-ranks.csv'))
old_scores<-read_csv(file.path(src,'scores.csv'),show_col_types=FALSE) |> filter(issue_id=='ALL',cohort=='all')
labels<-read_csv(file.path(src,'labels.csv'),col_types=cols(fixture_id=col_character(),score=col_character(),actual_outcome=col_character()))
metrics<-scores<-list()
for(mode in c('same_cutoff','near_sale')) {
 bd_name<-if(mode=='same_cutoff')'北单-T24'else'北单-后期SP'
 bd<-old_scores |> filter(comparison==mode,model==bd_name)
 ids<-intersect(labels$fixture_id,bd$fixture_id)
 f16<-old_scores |> filter(comparison==mode,model=='FM-1.6.0')
 # Existing baseline metrics retain exact original diagnostic scores.
 for(issue in c('ALL','26098','26101','26102'))for(cohort in c('all','native','market','rank_unstable','rank_stable')) {
  use<-ids
  if(issue!='ALL')use<-use[startsWith(use,paste0(issue,':'))]
  if(cohort%in%c('native','market'))use<-intersect(use,source$fixture_id[source$selected_source==cohort])
  if(cohort=='rank_unstable')use<-intersect(use,flags$fixture_id[flags$top2_set_changed])
  if(cohort=='rank_stable')use<-intersect(use,flags$fixture_id[!flags$top2_set_changed])
  if(!length(use))next
  d<-beidan:::DcAccuracyDiagnostic(p |> filter(fixture_id%in%use),labels |> filter(fixture_id%in%use) |> select(fixture_id,actual_outcome))
  key<-paste(mode,issue,cohort)
  metric<-d$summary
  for(baseline in list(bd,f16)) {
   z<-baseline |> filter(fixture_id%in%use)
   metric<-bind_rows(metric,tibble(model=first(z$model),n=nrow(z),hits1=sum(z$top1),hits2=sum(z$top2),top1=mean(z$top1),top2=mean(z$top2),brier=mean(z$brier),logloss=mean(z$logloss)))
  }
  metrics[[key]]<-metric |> mutate(comparison=mode,issue_id=issue,cohort=cohort,.before=1)
  scores[[key]]<-d$scores |> mutate(comparison=mode,issue_id=issue,cohort=cohort,.before=1)
 }
}
metrics<-bind_rows(metrics);scores<-bind_rows(scores)
write_csv(metrics,file.path(out,'round2-metrics.csv'));write_csv(scores,file.path(out,'round2-scores.csv'))
fi<-read_csv(file.path(out,'round1-fixtures.csv'),show_col_types=FALSE)
warning_eval<-flags |> inner_join(fi |> select(fixture_id,`top2_FM-1.7.0`,`top2_FM17-source-before-tail`,raw_top2_tail_loss),by='fixture_id',relationship='one-to-one') |> group_by(issue_id,selected_source,top2_set_changed) |> summarise(n=n(),fm17_top2=sum(`top2_FM-1.7.0`),raw_top2=sum(`top2_FM17-source-before-tail`),raw_tail_losses=sum(raw_top2_tail_loss),.groups='drop')
write_csv(warning_eval,file.path(out,'round2-warning-evaluation.csv'))
write_json(list(round=2,formal_model_changed=FALSE,parameter_selection=FALSE,forecast_sha256=cm$forecast_sha256,parent_forecast_sha256=m$forecast_sha256,client_sha256=digest::digest(file=file.path(root,'r/fm17_diagnostic_round2_evaluate.R'),algo='sha256'),outputs=tibble(path=c('round2-metrics.csv','round2-scores.csv','round2-prediction-only-flags.csv','round2-warning-evaluation.csv','round2-ranks.csv','round2-market-component-ledger.csv','round2-native-component-ledger.csv'),sha256=map_chr(file.path(out,c('round2-metrics.csv','round2-scores.csv','round2-prediction-only-flags.csv','round2-warning-evaluation.csv','round2-ranks.csv','round2-market-component-ledger.csv','round2-native-component-ledger.csv')),~digest::digest(file=.x,algo='sha256')))),file.path(out,'round2-evaluation.json'),auto_unbox=TRUE,pretty=TRUE)
print(metrics |> filter(issue_id=='ALL',cohort=='all') |> select(comparison,model,n,hits1,hits2,brier,logloss),n=20,width=Inf)
print(warning_eval,width=Inf)
