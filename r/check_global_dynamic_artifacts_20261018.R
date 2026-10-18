# Rscript r/check_global_dynamic_artifacts_20261018.R ROOT
# Explicit required real-data acceptance; not a routine unit test or a skip.
args<-commandArgs(TRUE);stopifnot(length(args)==1L)
root<-normalizePath(args[1],mustWork=TRUE);setwd(root)
Sys.setenv(BEIDAN_REPO_ROOT=root)
suppressPackageStartupMessages(library(testthat))
test_that('frozen full-issue forecasts retain causal scalar calibration and explicit exclusions', {
 root<-Sys.getenv('BEIDAN_REPO_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 for(issue in c('26103','26104')) {
  out<-file.path(root,'results/global-dynamic-walkforward-20261018',issue)
  x<-readRDS(file.path(out,'frozen-forecasts.rds'))
  manifest<-jsonlite::fromJSON(file.path(out,'forecast-manifest.json'))
  replay<-jsonlite::fromJSON(file.path(out,'forecast-replay.json'))
  expect_equal(nrow(x$audit),if(issue=='26103')407L else 109L)
  expect_false(anyDuplicated(x$audit$fixture_id)>0L)
  expect_equal(length(x$entries),sum(x$audit$state=='ESTIMATED_FULL100'))
  expect_false(x$prospective_admission);expect_false(x$target_labels_opened)
  expect_identical(replay$status,'FULL_IDENTICAL_REPLAY')
  expect_identical(replay$sha256,manifest$sha256)
  expect_identical(manifest$sha256,digest::digest(file=file.path(out,'frozen-forecasts.rds'),algo='sha256'))
  keys<-character()
  for(f in x$calibration) {
   expect_true(all(as.integer(f$admitted$issue_code)<as.integer(issue)))
   expect_true(all(lubridate::ymd_hms(f$admitted$label_available_ts,tz='UTC')<f$cutoff$cutoff_utc))
   expect_true(all(lubridate::ymd_hms(f$admitted$data_available_ts,tz='UTC')<f$cutoff$cutoff_utc))
   expect_gte(nrow(f$admitted),100L)
   keys<-c(keys,f$receipt$cache_key)
  }
  expect_false(anyDuplicated(keys)>0L)
  for(id in names(x$entries)) {
   e<-x$entries[[id]];f<-x$calibration[[e$calibration_key]]
   p<-e$RAW$probability[match(c('W','D','L'),e$RAW$outcome)]
   intercepts<-vapply(f$coefficients,unname,numeric(1))
   oracle<-stats::plogis(stats::qlogis(p)+intercepts[c('W','D','L')]);oracle<-oracle/sum(oracle)
   expect_equal(e$GLOBAL$probability[match(c('W','D','L'),e$GLOBAL$outcome)],unname(oracle),tolerance=1e-12)
   expect_identical(e$cutoff,f$cutoff)
   expect_equal(sum(e$margins$probability),1,tolerance=1e-12)
   expect_equal(e$final$grid$probability,e$base$grid$probability,tolerance=1e-12)
   expect_lt(e$base$max_source_available_utc,e$cutoff$cutoff_utc)
   native<-e$native$native;nf<-native$receipt$fixture;obs<-native$observations
   home_venue<-if(nf$neutral_reported)'neutral'else'home';away_venue<-if(nf$neutral_reported)'neutral'else'away'
   home<-obs[obs$team_id==nf$home_id & obs$venue==home_venue,];away<-obs[obs$team_id==nf$away_id & obs$venue==away_venue,]
   oracle_home<-(stats::weighted.mean(home$goals,home$weight)+stats::weighted.mean(away$against,away$weight))/2
   oracle_away<-(stats::weighted.mean(away$goals,away$weight)+stats::weighted.mean(home$against,home$weight))/2
   expect_equal(native$same_support_raw$lambda_home,oracle_home,tolerance=1e-12)
   expect_equal(native$same_support_raw$lambda_away,oracle_away,tolerance=1e-12)
   expect_true(lubridate::ymd_hms(native$receipt$admission$maximum_source_time,tz='UTC')<e$cutoff$cutoff_utc)
   a<-x$audit[x$audit$fixture_id==id,]
   expect_gte(a$euro_companies,3L);expect_equal(a$asian_rows,1L);expect_equal(a$total_rows,1L)
   expect_identical(a$selected_source,if(a$market_consistent)'market'else'native')
  }
 }
})

test_that('paired full-space purchases hold matches, physical budget and pending outcomes fixed', {
 root<-Sys.getenv('BEIDAN_REPO_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
 for(issue in c('26103','26104')) {
  out<-file.path(root,'results/global-dynamic-walkforward-20261018',issue)
  x<-readRDS(file.path(out,'frozen-rounds.rds'))
  expect_false(x$target_labels_opened)
  for(z in x$rounds) {
   expect_gte(length(z$fixture_ids),8L);expect_lte(length(z$fixture_ids),x$policy$rounds$maximum_pool)
   expect_true(all(z$forecast_cutoffs$cutoff_utc<=z$cutoff$cutoff_utc))
   expect_true(all(z$cutoff$cutoff_utc<z$forecast_cutoffs$kickoff_at))
   expect_equal(as.integer(table(z$groups$group_id)),rep(7L,8))
   expect_equal(length(unique(z$groups$group_id)),8L)
   expect_setequal(z$outputs$RAW$decision$probabilities$fixture_id,z$outputs$GLOBAL$decision$probabilities$fixture_id)
   for(model in c('RAW','GLOBAL')) {
    o<-z$outputs[[model]]
    expect_identical(o$decision$cutoff,z$cutoff)
    expect_equal(nrow(o$decision$candidates),8L*3^7)
    for(policy in c('FIXED','TOP','DYNAMIC_WINDOW','DYNAMIC_SET')) {
     t<-o$selection$purchases[o$selection$purchases$policy==policy,]
     expect_equal(nrow(t),1000L)
     expect_equal(as.integer(table(t$group_id)),rep(125L,8))
     expect_equal(tail(o$selection$trace$cost_cny[o$selection$trace$policy==policy],1),2000)
    }
   }
  }
  scores<-readr::read_csv(file.path(out,'evaluation','scores.csv'),show_col_types=FALSE)
  expect_setequal(scores$fixture_id[scores$model=='RAW'],scores$fixture_id[scores$model=='GLOBAL'])
  results<-readr::read_csv(file.path(out,'evaluation','rounds.csv'),show_col_types=FALSE)
  expect_true(all(results$cost_cny==2000));expect_true(all(is.na(results$payout_cny[!results$monetary_complete])));expect_true(all(is.finite(results$payout_cny[results$monetary_complete])))
 }
})
