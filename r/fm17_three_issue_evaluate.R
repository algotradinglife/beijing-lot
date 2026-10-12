# Pure description of sealed forecasts; no fitting, review or decision updates.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE);dest<-file.path(root,'results/fm17-three-issues-20261013')
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-release-20261013/library'))
m<-fromJSON(file.path(dest,'manifest.json'));stopifnot(digest::digest(file=file.path(dest,'forecasts.rds'),algo='sha256')==m$forecast_sha256)
parent<-file.path(root,'results/fm16-three-issues-20261012')
if(digest::digest(file=file.path(parent,'stage.rds'),algo='sha256')!=m$source_hashes$parent_stage)stop('Parent stage hash differs; labels remain unopened')
if(digest::digest(file=file.path(parent,'forecasts.rds'),algo='sha256')!=m$source_hashes$parent_forecast)stop('Parent forecast hash differs; labels remain unopened')
x<-readRDS(file.path(dest,'forecasts.rds'));s<-readRDS(file.path(parent,'stage.rds'));old_fm16<-readRDS(file.path(parent,'forecasts.rds'))
if(!all(map_chr(file.path(root,s$inputs$path),~digest::digest(file=.x,algo='sha256'))==s$inputs$sha256))stop('Comparator/source snapshot hash differs; labels remain unopened')
replay<-fromJSON(file.path(dest,'replay.json'));stopifnot(replay$status=='FULL_IDENTICAL_REPLAY',replay$forecast_sha256==m$forecast_sha256)
comparator_inputs<-s$inputs |> filter(str_detect(path,'/batch-[a-f0-9]+[.]rds$'))
stopifnot(nrow(comparator_inputs)==2L)
fm<-x$probabilities |> select(fixture_id,model,outcome,probability)
old<-old_fm16$probabilities |> filter(model=='FM-1.6.0') |> select(fixture_id,model,outcome,probability)
roster<-map_dfr(s$native,~as_tibble(.x$fixture)[,c('fixture_id','handicap','cutoff_utc')])
# Immutable prior full-roster discovery evidence; missing numbers are not empty issues.
scope_root<-file.path(root,'results/beidan-full-issues-26092-26102-20261007')
scope_acceptance<-fromJSON(file.path(scope_root,'acceptance.json'))
scope_roster<-read_csv(file.path(scope_root,'full-issue-fixtures.csv'),col_types=cols(issue=col_character()),show_col_types=FALSE)
stopifnot(digest::digest(file=file.path(scope_root,'full-issue-fixtures.csv'),algo='sha256')==scope_acceptance$fixtures_csv_sha256)
scope_inventory<-fromJSON(file.path(scope_root,'raw/inventory.json'),simplifyVector=FALSE)
for(event in scope_inventory$events) {
 if(event$issue %in% c('26099','26100'))stopifnot(event$status=='ERROR')
 if(event$status=='PARSED') {
  receipt<-event$receipt
  stopifnot(basename(receipt$raw_file)==receipt$raw_file,
    digest::digest(file=file.path(scope_root,'raw',receipt$raw_file),algo='sha256')==receipt$sha256)
 }
}
scope_counts<-scope_roster |> transmute(issue_id=as.character(issue)) |> filter(as.integer(issue_id)>=26098L,as.integer(issue_id)<=26102L) |> count(issue_id,name='source_matches')
scope<-tibble(issue_id=as.character(26098:26102)) |> left_join(scope_counts,by='issue_id',relationship='one-to-one') |> mutate(status=if_else(is.na(source_matches),'SOURCE_NOT_LISTED_REQUEST_FAILED','SOURCE_LISTED'),source_matches=as.integer(source_matches))
stopifnot(sum(scope$source_matches,na.rm=TRUE)==347L)
write_csv(scope,file.path(dest,'scope.csv'))
label_path<-file.path(root,'results/fundamental-issues-20261011/inputs/labels.rds');sp_path<-file.path(root,'results/fundamental-beidan-history-20261011/analysis-20261011T024028.510576Z/selected-sp.csv')
y<-readRDS(label_path)
labels<-bind_rows(y[['26098']]$matches,y[['26101']]$matches,y[['26102']]$matches) |> transmute(fixture_id=paste0(issue_id,':',slot),status,score) |> filter(status=='完场',!is.na(score),str_detect(score,'^[0-9]+[-:][0-9]+$')) |> mutate(home_goals=as.integer(str_extract(score,'^[0-9]+')),away_goals=as.integer(str_extract(score,'[0-9]+$'))) |> inner_join(roster,by='fixture_id',relationship='one-to-one') |> transmute(fixture_id,score,actual_outcome=case_when(home_goals-away_goals+handicap>0~'W',home_goals-away_goals+handicap==0~'D',TRUE~'L'))
stopifnot(!anyDuplicated(labels$fixture_id),nrow(labels)==345L)
sp<-read_csv(sp_path,show_col_types=FALSE) |> inner_join(roster |> select(fixture_id,cutoff_utc),by='fixture_id',relationship='many-to-one')
stopifnot(nrow(problems(sp))==0,!anyDuplicated(sp[c('fixture_id','mode')]),all(sp$sp_w>0&sp$sp_d>0&sp$sp_l>0),all(sp$quote_at<sp$selection_cutoff),all(sp$quote_at<sp$kickoff_utc),all(sp$selection_cutoff[sp$mode=='same_cutoff']==sp$cutoff_utc[sp$mode=='same_cutoff']))
bd<-sp |> transmute(fixture_id,mode,W=1/sp_w,D=1/sp_d,L=1/sp_l) |> mutate(mass=W+D+L,across(c(W,D,L),~.x/mass)) |> select(-mass) |> pivot_longer(c(W,D,L),names_to='outcome',values_to='probability') |> mutate(model=if_else(mode=='same_cutoff','北单-T24','北单-后期SP'))
known<-c(paste0('26098:',c(4,74,79,96,104)),paste0('26101:',c(20,52)),paste0('26102:',c(4,10,11,23,24,59)))
metrics<-scores<-list()
for(issue in c('26098','26101','26102','ALL'))for(mode in c('same_cutoff','near_sale'))for(cohort in c('all','known-discussed','not-listed-as-discussed','market-selected','native-retained','non-uniform-SP')) {
 ids<-Reduce(intersect,list(fm$fixture_id,old$fixture_id,bd$fixture_id[bd$mode==mode],labels$fixture_id))
 if(issue!='ALL')ids<-ids[startsWith(ids,paste0(issue,':'))]
 if(cohort=='known-discussed')ids<-intersect(ids,known)
 if(cohort=='not-listed-as-discussed')ids<-setdiff(ids,known)
 if(cohort=='market-selected')ids<-intersect(ids,x$audit$fixture_id[x$audit$selected_source=='market'])
 if(cohort=='native-retained')ids<-intersect(ids,x$audit$fixture_id[x$audit$selected_source=='native'])
 if(cohort=='non-uniform-SP')ids<-intersect(ids,sp$fixture_id[sp$mode==mode&!(sp$sp_w==sp$sp_d&sp$sp_d==sp$sp_l)])
 if(!length(ids))next
 p<-bind_rows(fm,old,bd |> filter(.data$mode==.env$mode) |> select(-mode)) |> filter(fixture_id%in%ids)
 d<-beidan:::DcAccuracyDiagnostic(p,labels |> filter(fixture_id%in%ids) |> select(fixture_id,actual_outcome))
 key<-paste(issue,mode,cohort)
 metrics[[key]]<-d$summary |> mutate(issue_id=issue,comparison=mode,cohort=cohort,.before=1)
 scores[[key]]<-d$scores |> mutate(issue_id=issue,comparison=mode,cohort=cohort,.before=1)
}
metrics<-bind_rows(metrics);scores<-bind_rows(scores)
write_csv(metrics,file.path(dest,'metrics.csv'));write_csv(scores,file.path(dest,'scores.csv'));write_csv(labels,file.path(dest,'labels.csv'))
changes<-scores |> filter(issue_id=='ALL',comparison=='near_sale',cohort=='all',model%in%c('FM-1.7.0','FM-1.6.0','FM17-source-before-tail','北单-后期SP')) |> select(fixture_id,model,actual_outcome,top1,top2,brier,logloss) |> pivot_wider(names_from=model,values_from=c(top1,top2,brier,logloss)) |> left_join(x$audit,by='fixture_id',relationship='one-to-one')
write_csv(changes,file.path(dest,'changes.csv'))
write_json(list(scope_inventory_path=substring(file.path(scope_root,'raw/inventory.json'),nchar(root)+2L),scope_inventory_sha256=digest::digest(file=file.path(scope_root,'raw/inventory.json'),algo='sha256'),scope_csv_sha256=digest::digest(file=file.path(dest,'scope.csv'),algo='sha256'),label_path=substring(label_path,nchar(root)+2L),label_sha256=digest::digest(file=label_path,algo='sha256'),sp_path=substring(sp_path,nchar(root)+2L),sp_sha256=digest::digest(file=sp_path,algo='sha256'),forecast_sha256=m$forecast_sha256,parent_stage_sha256=m$source_hashes$parent_stage,comparator_inputs=comparator_inputs,evaluation_client_sha256=digest::digest(file=file.path(root,'r/fm17_three_issue_evaluate.R'),algo='sha256'),settled=nrow(labels),forecast_count=length(x$entries),known_case_inventory=known,inventory_complete=FALSE,not_listed_cohort_independent=FALSE,metrics_sha256=digest::digest(file=file.path(dest,'metrics.csv'),algo='sha256'),scores_sha256=digest::digest(file=file.path(dest,'scores.csv'),algo='sha256'),changes_sha256=digest::digest(file=file.path(dest,'changes.csv'),algo='sha256'),labels_csv_sha256=digest::digest(file=file.path(dest,'labels.csv'),algo='sha256'),intended_use='POSTHOC_HISTORICAL_DIAGNOSTIC'),file.path(dest,'evaluation.json'),auto_unbox=TRUE,pretty=TRUE)
print(metrics |> filter(issue_id=='ALL',cohort=='all'))
