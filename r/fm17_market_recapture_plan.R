# Explicit diagnostic scope; no settlement or prices select the fixture population.
root <- normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
out <- file.path(root,'results/fm17-market-recapture-20261013')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
fp <- file.path(root,'results/fm17-three-issues-20261013/forecasts.rds')
sp <- file.path(root,'results/fm16-three-issues-20261012/stage.rds')
stopifnot(digest::digest(file=fp,algo='sha256')=='e537428c0a43f966542c703d3edf6264722c95a7551dbabf7853aa909354e786',
 digest::digest(file=sp,algo='sha256')=='39579898babb99215d9b298dfcedaffcfcd34de63d22de2debad2d81d61dcb68')
x<-readRDS(fp);s<-readRDS(sp)
ids<-names(x$entries)[map_chr(x$entries,~.x$parent_selection$selected_source)=='native']
stopifnot(length(ids)==117L)
rows<-list();sources<-list()
for(id in ids) {
 f<-s$native[[id]]$fixture;e<-x$entries[[id]]
 base<-switch(f$issue_id,'26098'='fm13-26098-20261011','26101'='fm14-26101-20261011','26102'='fm15-26102-20261012')
 p<-file.path(root,'results',base,'market-captures',paste0(gsub(':','_',id),'.json'))
 stopifnot(file.exists(p));cap<-fromJSON(p,simplifyVector=FALSE)
 stopifnot(cap$fixture$fixture_id==id,cap$fixture$provider_id_nowscore==f$provider_id,
 cap$fixture$home_nowscore==f$home,cap$fixture$away_nowscore==f$away,
 lubridate::ymd_hms(cap$fixture$kickoff_at,tz='UTC')-lubridate::hours(24)==e$cutoff$cutoff_utc)
 rows[[id]]<-as_tibble(cap$fixture) |> mutate(issue_id=f$issue_id,cutoff_utc=format(e$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'),cutoff_identity=e$cutoff$issue_id,original_capture=substring(p,nchar(root)+2),original_capture_sha256=digest::digest(file=p,algo='sha256'))
 for(q in cap$captures) if(!is.null(q$sha256)) {
  raw<-if(startsWith(q$raw_path,'/'))q$raw_path else file.path(root,q$raw_path)
  stopifnot(digest::digest(file=raw,algo='sha256')==q$sha256)
  sources[[length(sources)+1L]]<-tibble(path=substring(raw,nchar(root)+2),sha256=q$sha256)
 }
}
f<-bind_rows(rows);write_csv(f,file.path(out,'scope.csv'))
write_json(map(seq_len(nrow(f)),~as.list(f[.x,])),file.path(out,'scope.json'),auto_unbox=TRUE,pretty=TRUE)
write_json(list(scope='ALL_117_FM17_NATIVE_SOURCE_FIXTURES',intended_use='HISTORICAL_DIAGNOSTIC_ONLY',availability='HISTORICAL_QUOTE_PROXY',original_forecast_sha256=digest::digest(file=fp,algo='sha256'),stage_sha256=digest::digest(file=sp,algo='sha256'),plan_client_sha256=digest::digest(file=file.path(root,'r/fm17_market_recapture_plan.R'),algo='sha256'),scope_sha256=digest::digest(file=file.path(out,'scope.json'),algo='sha256'),original_sources=bind_rows(sources),unchanged_model_policy=list(max_quote_age_hours=48,euro_companies=c('281','115','82','432')),new_capture_policy=list(min_request_spacing_seconds=1,timeout_seconds=15,retries=1,max_attempts_per_key=1),formal_FM17_changed=FALSE),file.path(out,'plan.json'),auto_unbox=TRUE,pretty=TRUE)
print(f |> count(issue_id))
