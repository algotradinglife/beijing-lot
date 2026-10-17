# Rscript r/fm171_26103_evaluate.R ROOT
# Descriptive scoring only. Target labels never return to the freeze clients.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,'r_lib'))
out<-file.path(root,'results/fm171-26103-draw-20261017')
paths<-c('native','calibration','sp');objects<-list();bindings<-list()
for(kind in paths) {
 m<-jsonlite::fromJSON(file.path(out,paste0(kind,'-manifest.json')))
 r<-jsonlite::fromJSON(file.path(out,paste0(kind,'-replay.json')))
 filename<-switch(kind,native='native-forecasts.rds',calibration='calibrated-forecasts.rds',sp='sp-forecasts.rds')
 stopifnot(r$status=='FULL_IDENTICAL_REPLAY',r$sha256==m$sha256,digest::digest(file=file.path(out,filename),algo='sha256')==m$sha256)
 objects[[kind]]<-readRDS(file.path(out,filename));bindings[[kind]]<-m$sha256
}
audit<-objects$native$audit;stopifnot(nrow(audit)==407,!anyDuplicated(audit$fixture_id))
label_path<-'docs/reviews/source-26103/roster.json'
raw_labels<-bind_rows(jsonlite::fromJSON(label_path,simplifyVector=FALSE)$data) |>
 mutate(fixture_id=paste0(issue_id,':',slot),label_usable=status=='完场'&str_detect(coalesce(score,''),'^[0-9]+[-:][0-9]+$'))
stopifnot(nrow(raw_labels)==407,!anyDuplicated(raw_labels$fixture_id))
stopifnot(digest::digest(file=file.path(out,'inputs.json'),algo='sha256')==objects$native$bindings$inputs)
frozen_identity<-bind_rows(jsonlite::fromJSON(file.path(out,'inputs.json'),simplifyVector=FALSE)$fixtures) |> select(fixture_id,provider_id)
label_binding<-raw_labels |> transmute(fixture_id,label_provider_id=native_id,label_handicap=handicap) |>
 inner_join(audit |> select(fixture_id,frozen_handicap=handicap),by='fixture_id',relationship='one-to-one') |>
 inner_join(frozen_identity,by='fixture_id',relationship='one-to-one')
stopifnot(nrow(label_binding)==407,!anyNA(label_binding),all(label_binding$label_provider_id==label_binding$provider_id),all(label_binding$label_handicap==label_binding$frozen_handicap))
labels<-raw_labels |> filter(label_usable) |>
 transmute(fixture_id,handicap,score,home_goals=as.integer(str_extract(score,'^[0-9]+')),away_goals=as.integer(str_extract(score,'[0-9]+$')),
  actual_outcome=case_when(home_goals-away_goals+handicap>0~'W',home_goals-away_goals+handicap==0~'D',TRUE~'L'))
write_csv(raw_labels |> filter(!label_usable) |> select(fixture_id,status,score),file.path(out,'label-exclusions.csv'))
write_csv(labels,file.path(out,'labels.csv'))
fm<-bind_rows(objects$calibration$probabilities,objects$native$probabilities |> filter(model=='BEFORE_TAIL'))
sp<-objects$sp$probabilities
metrics<-scores<-calibration<-recall<-list()
for(cohort in c('ALL_FM','PAIRED_T24','PAIRED_LATER_PREMATCH')) {
 ids<-intersect(unique(fm$fixture_id),labels$fixture_id)
 comparator<-switch(cohort,ALL_FM=NA_character_,PAIRED_T24='BD_T24',PAIRED_LATER_PREMATCH='BD_LATER_PREMATCH')
 if(!is.na(comparator))ids<-intersect(ids,sp$fixture_id[sp$model==comparator])
 if(!length(ids))next
 p<-fm |> filter(fixture_id%in%ids)
 if(!is.na(comparator))p<-bind_rows(p,sp |> filter(model==comparator,fixture_id%in%ids))
 d<-beidan:::DcAccuracyDiagnostic(p,labels |> filter(fixture_id%in%ids) |> select(fixture_id,actual_outcome))
 draw_scores<-p |> filter(outcome=='D') |> inner_join(labels |> select(fixture_id,actual_outcome),by='fixture_id',relationship='many-to-one') |>
  group_by(model) |> summarise(binary_draw_brier=mean((probability-as.double(actual_outcome=='D'))^2),.groups='drop')
 metrics[[cohort]]<-d$summary |> left_join(draw_scores,by='model',relationship='one-to-one') |> mutate(cohort=cohort,.before=1)
 scores[[cohort]]<-d$scores |> mutate(cohort=cohort,.before=1)
 calibration[[cohort]]<-d$calibration |> mutate(cohort=cohort,.before=1)
 recall[[cohort]]<-d$recall |> mutate(cohort=cohort,.before=1)
}
metrics<-bind_rows(metrics);scores<-bind_rows(scores);calibration<-bind_rows(calibration);recall<-bind_rows(recall)
changes<-scores |> filter(cohort=='ALL_FM') |> select(fixture_id,model,actual_outcome,top1,top2,brier,logloss) |>
 pivot_wider(names_from=model,values_from=c(top1,top2,brier,logloss)) |>
 left_join(audit,by='fixture_id',relationship='one-to-one')
gains<-map_dfr(c('GLOBAL_D48','GLOBAL_D72'),function(model) {
 tibble(model=model,save1=sum(!changes$top1_FM171 & changes[[paste0('top1_',model)]]),lose1=sum(changes$top1_FM171 & !changes[[paste0('top1_',model)]]),
  save2=sum(!changes$top2_FM171 & changes[[paste0('top2_',model)]]),lose2=sum(changes$top2_FM171 & !changes[[paste0('top2_',model)]]))
})
group_scores<-scores |> filter(cohort=='ALL_FM') |> left_join(audit |> select(fixture_id,league,handicap,cutoff_utc,selected_source),by='fixture_id',relationship='many-to-one') |>
 mutate(line_group=if_else(handicap==0,'ZERO','NONZERO'),decision_date=as.Date(cutoff_utc))
groups<-bind_rows(group_scores |> group_by(model,line_group) |> summarise(n=n(),hits1=sum(top1),hits2=sum(top2),brier=mean(brier),logloss=mean(logloss),.groups='drop') |> rename(group=line_group) |> mutate(dimension='handicap'),
 group_scores |> group_by(model,decision_date) |> summarise(n=n(),hits1=sum(top1),hits2=sum(top2),brier=mean(brier),logloss=mean(logloss),.groups='drop') |> mutate(group=as.character(decision_date),dimension='decision_date') |> select(-decision_date),
 group_scores |> group_by(model,selected_source) |> summarise(n=n(),hits1=sum(top1),hits2=sum(top2),brier=mean(brier),logloss=mean(logloss),.groups='drop') |> rename(group=selected_source) |> mutate(dimension='routing'))
scope<-audit |> left_join(raw_labels |> select(fixture_id,status,score,label_usable),by='fixture_id',relationship='one-to-one') |>
 left_join(objects$sp$audit |> group_by(fixture_id) |> summarise(sp_t24=any(mode=='same_cutoff'),sp_later=any(mode=='later_prematch'),.groups='drop'),by='fixture_id',relationship='one-to-one') |>
 mutate(across(c(sp_t24,sp_later),~coalesce(.x,FALSE)))
margin<-map_dfr(names(objects$calibration$entries),function(id) {
 e<-objects$calibration$entries[[id]]
 map_dfr(names(e$results),function(model) {
  v<-e$results[[model]];grid<-if(model=='FM171')v$grid else v$final$grid
  grid |> mutate(margin=home_goals-away_goals) |> group_by(margin) |> summarise(probability=sum(probability),.groups='drop') |>
   arrange(desc(probability),margin) |> mutate(fixture_id=id,model=model,rank=row_number(),.before=1)
 })
})
tables<-list(metrics=metrics,scores=scores,calibration=calibration,recall=recall,changes=changes,gains=gains,groups=groups,scope=scope,margins=margin)
stopifnot(digest::digest(file=file.path(out,'market-stage.rds'),algo='sha256')==objects$native$bindings$market_stage)
frozen_market<-readRDS(file.path(out,'market-stage.rds'))
euro_sha256<-digest::digest(file=file.path(out,'euro-selected.rds'),algo='sha256')
stopifnot(euro_sha256==frozen_market$bindings$euro)
bindings$euro_comparison<-euro_sha256
euro<-readRDS(file.path(out,'euro-selected.rds')) |> filter(tied_vectors==1L) |>
 mutate(W=1/odds_home,D=1/odds_draw,L=1/odds_away,mass=W+D+L,across(c(W,D,L),~.x/mass)) |>
 group_by(fixture_id) |> summarise(companies=n(),euro_W=mean(W),euro_D=mean(D),euro_L=mean(L),.groups='drop')
ordinary<-map_dfr(names(objects$native$entries),function(id) {
 g<-objects$native$entries[[id]]$native_base$grid;dm<-g$home_goals-g$away_goals
 tibble(fixture_id=id,native_W=sum(g$probability[dm>0]),native_D=sum(g$probability[dm==0]),native_L=sum(g$probability[dm<0]))
}) |> left_join(euro,by='fixture_id',relationship='one-to-one')
tables$ordinary_euro<-ordinary
tables$market_candidates<-frozen_market$audit |> filter(sufficient,consistent) |>
 left_join(audit |> select(fixture_id,native_state=state,native_reason=reason,selected_source),by='fixture_id',relationship='one-to-one')
stopifnot(digest::digest(file=file.path(out,'fundamentals.rds'),algo='sha256')==objects$native$bindings$fundamentals_snapshot)
clock_roster<-readRDS(file.path(out,'fundamentals.rds'))$fixture_schedule |> filter(resource=='roster') |>
 transmute(fixture_id,roster_utc=lubridate::with_tz(lubridate::ymd_hms(paste(kickoff_date,kickoff_hhmm,'00'),tz='Asia/Shanghai'),'UTC'))
clock_input<-jsonlite::fromJSON(file.path(out,'inputs.json'),simplifyVector=FALSE)
clock_market<-bind_rows(clock_input$contexts) |> select(fixture_id,source,kickoff_at) |>
 mutate(kickoff_at=lubridate::ymd_hms(kickoff_at,tz='UTC')) |> pivot_wider(names_from=source,values_from=kickoff_at,names_prefix='market_')
tables$clock_audit<-bind_rows(clock_input$fixtures) |> transmute(fixture_id,analysis_utc=lubridate::ymd_hms(kickoff_at,tz='UTC')) |>
 left_join(clock_roster,by='fixture_id',relationship='one-to-one') |>
 left_join(clock_market,by='fixture_id',relationship='one-to-one') |>
 mutate(roster_delta_minutes=as.numeric(difftime(roster_utc,analysis_utc,units='mins')),
  titan_delta_minutes=as.numeric(difftime(market_titan,analysis_utc,units='mins')),
  nowscore_delta_minutes=as.numeric(difftime(market_nowscore,analysis_utc,units='mins'))) |>
 left_join(audit |> select(fixture_id,state,reason),by='fixture_id',relationship='one-to-one')
for(name in names(tables))write_csv(tables[[name]],file.path(out,paste0(name,'.csv')))
jsonlite::write_json(list(bindings=bindings,label_path=label_path,label_sha256=digest::digest(file=label_path,algo='sha256'),
 label_scope='SOURCE_PUBLISHED_FULL_TIME from accepted roster; not independently certified regulation90min',
 client_sha256=digest::digest(file='r/fm171_26103_evaluate.R',algo='sha256'),
 scorer_sha256=digest::digest(paste(deparse(beidan:::DcAccuracyDiagnostic),collapse='\n'),algo='sha256'),
 scope=407,estimated=nrow(audit |> filter(state=='ESTIMATED')),settled=nrow(labels),paired_metrics=metrics,
 outputs=tibble(path=paste0(names(tables),'.csv'),sha256=map_chr(file.path(out,paste0(names(tables),'.csv')),~digest::digest(file=.x,algo='sha256'))),
 prospective_validated=FALSE,official_model_changed=FALSE),file.path(out,'evaluation.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
print(metrics,n=Inf);print(gains)
