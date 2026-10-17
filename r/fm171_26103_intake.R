# Offline pinned-data intake. Analysis tables are typed tibbles at the R boundary.
# Rscript r/fm171_26103_intake.R ROOT
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,'r_lib'))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
out<-file.path(root,'results/fm171-26103-draw-20261017');dir.create(out,recursive=TRUE,showWarnings=FALSE)
p<-jsonlite::fromJSON('config/fm171_26103_draw_study.json')
stopifnot(p$target_issue=='26103',!p$target_parameter_tuning,!p$official_version_change)
f<-list()
for(t in c('match','history','standings','coverage','fixture_schedule','status','conflicts','provenance'))
 f[[t]]<-beidan::read_dataset(p$fundamentals$dataset,t,version=p$fundamentals$version)
stopifnot(nrow(f$match)==407L,!anyDuplicated(f$match$fixture_id),!anyDuplicated(f$history[c('fixture_id','scope','match_id')]))
saveRDS(f,file.path(out,'fundamentals.rds'))
roster<-bind_rows(jsonlite::fromJSON('docs/reviews/source-26103/roster.json',simplifyVector=FALSE)$data)
stopifnot(nrow(roster)==407,!anyDuplicated(roster$slot),setequal(roster$slot,1:407))
fixtures<-f$match |> left_join(roster |> transmute(fixture_id=paste0(issue_id,':',slot),slot,league,handicap),by='fixture_id',relationship='one-to-one') |>
 mutate(cutoff_utc=kickoff_at-lubridate::hours(p$decision_hours_before_kickoff))
write_csv(fixtures,file.path(out,'fixtures.csv'))
contexts<-beidan::read_dataset(p$euro$dataset,'contexts',version=p$euro$version)
saveRDS(contexts,file.path(out,'euro-contexts.rds'))
jsonlite::write_json(list(fixtures=fixtures,history=f$history,provenance=f$provenance,contexts=contexts),file.path(out,'inputs.json'),
 dataframe='rows',auto_unbox=TRUE,na='null',digits=NA,POSIXt='ISO8601')
# Exactly the prior fixed four-company basket; no target outcome in the quote query.
euro_source<-beidan:::dataset_table_source(p$euro$dataset,'euro_history',version=p$euro$version)
beidan:::verify_table_files(euro_source$files,euro_source$hashes,'euro_history')
euro<-beidan::dataset_query(p$euro$dataset,"SELECT * FROM euro_history WHERE source='titan' AND valid_decimal AND company_id IN ('281','115','82','432')",'euro_history',version=p$euro$version,memory_limit='1GB',threads=2L)
stopifnot(tibble::is_tibble(euro),inherits(euro$quote_at,'POSIXct'),!anyDuplicated(euro[c('fixture_id','source','company_id','source_order')]))
euro<-euro |> inner_join(fixtures |> select(fixture_id,cutoff_utc),by='fixture_id',relationship='many-to-one')
# Strictly prior, maximum48h old. Same-minute conflicting vectors are not silently chosen.
selected<-euro |> filter(!is.na(cutoff_utc),quote_at<cutoff_utc,as.numeric(difftime(cutoff_utc,quote_at,units='hours'))<=48) |>
 group_by(fixture_id,company_id) |> filter(quote_at==max(quote_at)) |> ungroup() |>
 distinct(fixture_id,company_id,quote_at,odds_home,odds_draw,odds_away) |>
 group_by(fixture_id,company_id) |> mutate(tied_vectors=n()) |> ungroup()
saveRDS(selected,file.path(out,'euro-selected.rds'))
write_csv(selected |> count(fixture_id,tied_vectors),file.path(out,'euro-coverage.csv'))
# Full target roster plus the explicitly published following two issues. Never use a numeric date proxy to admit these IDs.
exclusions<-list()
for(path in c('docs/reviews/source-26103/roster.json','docs/reviews/source-26104/roster.json','results/fm17-upcoming-20261017/roster.json')) {
 z<-jsonlite::fromJSON(path,simplifyVector=FALSE)
 rows<-z$data %||% z
 exclusions[[path]]<-list(path=path,sha256=digest::digest(file=path,algo='sha256'),rows=rows)
}
# The operational roster.json is a selected betting window, not the full issue.
# Exclusion uses the independently saved FULL365-fixture future schedule instead.
future_path<-'results/fm17-upcoming-20261017/schedule-26105.rds'
future<-readRDS(future_path)
stopifnot(nrow(future)==365L,!anyDuplicated(future$fixture_key),all(future$issue_id=='26105'),!anyNA(future$provider_id_nowscore))
exclusions[[future_path]]<-list(path=future_path,sha256=digest::digest(file=future_path,algo='sha256'),
 rows=map(seq_len(nrow(future)),~list(fixture_key=future$fixture_key[.x],provider_id_nowscore=future$provider_id_nowscore[.x])))
jsonlite::write_json(exclusions,file.path(out,'exclusion-rosters.json'),auto_unbox=TRUE,na='null',digits=NA)
jsonlite::write_json(list(policy_sha256=digest::digest(file='config/fm171_26103_draw_study.json',algo='sha256'),
 client_sha256=digest::digest(file='r/fm171_26103_intake.R',algo='sha256'),
 fundamentals_manifest=beidan::dataset_manifest(p$fundamentals$dataset,p$fundamentals$version),
 euro_manifest=beidan::dataset_manifest(p$euro$dataset,p$euro$version),
 fixtures=407,history=nrow(f$history),euro_rows=nrow(euro),euro_selected=nrow(selected),
 target_roster_contains_known_settlement=TRUE,target_parameter_tuning=FALSE,
 historical_admission=FALSE,mode=p$mode),file.path(out,'intake.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
print(tibble(fixture_count=nrow(fixtures),history_count=nrow(f$history),selected_euro=nrow(selected),kickoff_missing=sum(is.na(fixtures$kickoff_at))))
