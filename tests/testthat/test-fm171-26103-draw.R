testthat::test_that('26103 full pipeline reconciles native means, routing and tail mass', {
 root<-rprojroot::find_root(rprojroot::has_file('AGENTS.md'));out<-file.path(root,'results/fm171-26103-draw-20261017')
 m<-jsonlite::fromJSON(file.path(out,'native-manifest.json'));rp<-jsonlite::fromJSON(file.path(out,'native-replay.json'))
 testthat::expect_identical(rp$status,'FULL_IDENTICAL_REPLAY')
 testthat::expect_identical(digest::digest(file=file.path(out,'native-forecasts.rds'),algo='sha256'),m$sha256)
 x<-readRDS(file.path(out,'native-forecasts.rds'));testthat::expect_equal(nrow(x$audit),407L)
 testthat::expect_identical(x$bindings$fundamentals_snapshot,digest::digest(file=file.path(out,'fundamentals.rds'),algo='sha256'))
 cache_line<-readLines(file.path(root,'r/fm171_26103_native_freeze.R'))
 cache_line<-cache_line[grep('cached<-readRDS',cache_line,fixed=TRUE)]
 guard<-parse(text=sub('.*;','',cache_line))
 cache_env<-new.env(parent=baseenv());cache_env$bindings<-x$bindings;cache_env$cached<-list(bindings=x$bindings)
 testthat::expect_no_error(eval(guard,cache_env))
 cache_env$bindings$fundamentals_snapshot<-'changed-roster-clock'
 testthat::expect_error(eval(guard,cache_env))
 testthat::expect_false(anyDuplicated(x$audit$fixture_id)>0L)
 testthat::expect_true(length(x$entries)>0L)
 # Regression: ISO character clocks must be parsed before comparing to POSIXct.
 testthat::expect_identical(x$audit$state[x$audit$fixture_id=='26103:1'],'ESTIMATED')
 testthat::expect_identical(x$audit$reason[x$audit$fixture_id=='26103:2'],'Sparse target competition/venue support')
 testthat::expect_true(all(x$audit$state%in%c('ESTIMATED','UNESTIMATED')))
 ex<-jsonlite::fromJSON(file.path(out,'exclusion-rosters.json'),simplifyVector=FALSE)
 excluded<-unique(unlist(lapply(ex,function(z)vapply(z$rows,function(r)if(!is.null(r$native_id))r$native_id else r$provider_id_nowscore,character(1)))))
 testthat::expect_length(ex[['results/fm17-upcoming-20261017/schedule-26105.rds']]$rows,365L)
 for(id in names(x$entries)) {
  e<-x$entries[[id]];f<-e$identities;obs<-e$native$observations
  testthat::expect_false(any(obs$match_id%in%excluded))
  hv<-if(f$neutral_reported)'neutral'else'home';av<-if(f$neutral_reported)'neutral'else'away'
  h<-dplyr::filter(obs,team_id==f$home_id,venue==hv);a<-dplyr::filter(obs,team_id==f$away_id,venue==av)
  lh<-(stats::weighted.mean(h$goals,h$weight)+stats::weighted.mean(a$against,a$weight))/2
  la<-(stats::weighted.mean(a$goals,a$weight)+stats::weighted.mean(h$against,h$weight))/2
  testthat::expect_equal(e$native$same_support_raw$lambda_home,lh,tolerance=1e-12)
  testthat::expect_equal(e$native$same_support_raw$lambda_away,la,tolerance=1e-12)
  testthat::expect_gte(nrow(h),12L);testthat::expect_gte(nrow(a),12L)
  expected_source<-if(e$source_review$market_sufficient&&e$source_review$market_consistent)'market'else'native'
  testthat::expect_identical(e$selection$selected_source,expected_source)
  testthat::expect_identical(e$source_review$confidence,'uncertain')
  testthat::expect_equal(e$base$grid,if(expected_source=='native')e$native_base$grid else e$market_base$grid)
  g<-e$base$grid;d<-g$home_goals-g$away_goals
  expected<-g$probability*ifelse(d%in%e$core$core_margins,1,.3);expected<-expected/sum(expected)
  testthat::expect_equal(e$final$grid$probability,expected,tolerance=1e-12)
  testthat::expect_gt(e$core$core_mass,.9)
  testthat::expect_equal(sum(e$final$grid$probability),1,tolerance=1e-12)
  testthat::expect_true(all(e$final$grid$probability>=0))
  testthat::expect_lt(as.numeric(e$base$max_source_available_utc),as.numeric(e$cutoff$cutoff_utc))
 }
 testthat::expect_true(all(x$audit$fixture_id[x$audit$state=='UNESTIMATED']%in%setdiff(x$audit$fixture_id,names(x$entries))))
})

testthat::test_that('target and post-cutoff mutation cannot change the actual calibration fit expression', {
 root<-rprojroot::find_root(rprojroot::has_file('AGENTS.md'));out<-file.path(root,'results/fm171-26103-draw-20261017')
 x<-readRDS(file.path(out,'calibrated-forecasts.rds'));e<-x$entries[[1]];h<-e$results$GLOBAL_D48$admitted
 beidan::python_backend(file.path(root,'.venv/bin/python'))
 shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
 core<-reticulate::import('beidan_backend.temporal_learning.core',convert=FALSE)
 pd<-reticulate::import('pandas',convert=FALSE);pl<-reticulate::import('pathlib',convert=FALSE)
 ct<-shared$Cutoff$decision_epoch('26103',format(e$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
 target<-h[1,];target$fixture_id<-'26103:FAKE';target$issue_code<-'26103'
 target$data_available_ts<-target$label_available_ts<-format(e$cutoff$cutoff_utc-lubridate::days(2),'%Y-%m-%dT%H:%M:%OS3Z',tz='UTC')
 future<-h[1,];future$fixture_id<-'26104:FAKE';future$issue_code<-'26104'
 future$data_available_ts<-future$label_available_ts<-format(e$cutoff$cutoff_utc+lubridate::days(2),'%Y-%m-%dT%H:%M:%OS3Z',tz='UTC')
 lines<-readLines(file.path(root,'r/fm171_26103_calibrate.R'))
 fit<-parse(text=lines[grep('^  n<-sum',lines):grep('^  params<-list',lines)])
 values<-keys<-list()
 for(i in 1:2) {
  hh<-dplyr::bind_rows(h,target,future)
  hh$draw_target[hh$issue_code%in%c('26103','26104')]<-i-1
  frame<-pd$DataFrame(jsonlite::fromJSON(jsonlite::toJSON(hh,dataframe='rows',auto_unbox=TRUE,digits=NA),simplifyVector=FALSE))
  ctx<-shared$prepare_learning_context(frame,ct,source_hashes=list(client=digest::digest(file=file.path(root,'r/fm171_26103_calibrate.R'),algo='sha256'),input=reticulate::py_to_r(core$stable_frame_hash(frame))),repository_root=pl$Path(root),
   implementation_modules=list('beidan_backend.temporal_learning.issue_partitions'),implementation_distributions=list('pandas','numpy'),
   availability=shared$AvailabilityFilter(shared$AvailabilityPolicy$historical_proxy('FM171_MUTATION_REGRESSION'),data_available_column='data_available_ts'),
   intended_use='HISTORICAL_DIAGNOSTIC',partition_policy=shared$PartitionPolicy('FIXED_PRIOR_FIT',0L,0L,1L),weighting_policy=shared$WeightingPolicy$expanding_equal(minimum_ess=50))
  admitted<-dplyr::bind_rows(jsonlite::fromJSON(reticulate::py_to_r(ctx$partitions[['fit']]$to_json(orient='records',date_format='iso',double_precision=15L)),simplifyVector=FALSE))
  testthat::expect_setequal(admitted$fixture_id,h$fixture_id)
  env<-new.env(parent=asNamespace('stats'));env$admitted<-admitted;env$weights<-as.numeric(reticulate::py_to_r(ctx$weights$to_numpy()))
  env$policy<-jsonlite::fromJSON(file.path(root,'config/fm171_draw_history_study.json'));env$delay<-48L
  eval(fit,env);values[[i]]<-env$params;keys[[i]]<-reticulate::py_to_r(ctx$receipt$payload)$cache_key
 }
 testthat::expect_identical(values[[1]],values[[2]])
 testthat::expect_equal(values[[1]]$delta,e$results$GLOBAL_D48$receipt$parameters$delta,tolerance=1e-12)
 testthat::expect_false(identical(keys[[1]],keys[[2]]))
})

testthat::test_that('26103 calibration preserves full sides and uses only prior shared-admitted labels', {
 root<-rprojroot::find_root(rprojroot::has_file('AGENTS.md'));out<-file.path(root,'results/fm171-26103-draw-20261017')
 x<-readRDS(file.path(out,'calibrated-forecasts.rds'));native<-readRDS(file.path(out,'native-forecasts.rds'))
 policy<-jsonlite::fromJSON(file.path(root,'config/fm171_draw_history_study.json'))
 rp<-jsonlite::fromJSON(file.path(out,'calibration-replay.json'));m<-jsonlite::fromJSON(file.path(out,'calibration-manifest.json'))
 testthat::expect_identical(rp$status,'FULL_IDENTICAL_REPLAY');testthat::expect_identical(rp$sha256,m$sha256)
 testthat::expect_false(m$target_labels_admitted);testthat::expect_false(m$versions_modified)
 testthat::expect_setequal(names(x$entries),names(native$entries))
 for(id in names(x$entries)) {
  e<-x$entries[[id]];g<-e$results$FM171$grid;handicap<-native$audit$handicap[match(id,native$audit$fixture_id)]
  d<-g$home_goals-g$away_goals;is_draw<-d== -handicap;p<-sum(g$probability[is_draw])
  for(name in c('GLOBAL_D48','GLOBAL_D72')) {
   z<-e$results[[name]];h<-z$admitted;w<-z$ledger$weight
   testthat::expect_true(all(h$issue_code%in%c('26098','26101','26102')))
   testthat::expect_false(any(h$issue_code=='26103'))
   testthat::expect_true(all(lubridate::ymd_hms(h$label_available_ts,tz='UTC')<e$cutoff$cutoff_utc))
   testthat::expect_true(all(lubridate::ymd_hms(h$data_available_ts,tz='UTC')<e$cutoff$cutoff_utc))
   testthat::expect_equal(w,rep(1,nrow(h)),tolerance=1e-12)
   n<-sum(w);mu<-weighted.mean(h$baseline_draw,w);r<-weighted.mean(h$draw_target,w)
   rs<-(n*r+50*mu)/(n+50);delta<-qlogis(rs)-qlogis(mu);q<-plogis(qlogis(p)+delta)
   testthat::expect_gte(n,policy$minimum_global_ess)
   testthat::expect_equal(z$receipt$parameters$delta,delta,tolerance=1e-12)
   expected<-g$probability*ifelse(is_draw,q/p,(1-q)/(1-p))
   testthat::expect_equal(z$final$grid$probability,expected,tolerance=1e-11)
   testthat::expect_equal(sum(z$final$grid$probability),1,tolerance=1e-12)
   testthat::expect_equal(sum(z$final$grid$probability[is_draw]),q,tolerance=1e-12)
  }
 }
})

testthat::test_that('observed SP and paired scores have explicit valid clocks and independently reconciled metrics', {
 root<-rprojroot::find_root(rprojroot::has_file('AGENTS.md'));out<-file.path(root,'results/fm171-26103-draw-20261017')
 x<-readRDS(file.path(out,'sp-forecasts.rds'));a<-x$audit
 testthat::expect_equal(sum(a$mode=='same_cutoff'),20L);testthat::expect_equal(sum(a$mode=='later_prematch'),196L)
 testthat::expect_true(all(a$quote_at<a$selection_cutoff));testthat::expect_true(all(a$quote_at<a$kickoff_at))
 for(k in names(x$receipts)) {
  r<-x$receipts[[k]];selected<-r$selected
  p<-(1/selected$sp_raw)/sum(1/selected$sp_raw)
  id<-r$admitted$fixture_id[1];model<-if(grepl('same_cutoff$',k))'BD_T24'else'BD_LATER_PREMATCH'
  actual<-dplyr::filter(x$probabilities,fixture_id==id,.data$model==.env$model)
  testthat::expect_equal(actual$probability[match(selected$outcome,actual$outcome)],p,tolerance=1e-12)
 }
 scores<-readr::read_csv(file.path(out,'scores.csv'),show_col_types=FALSE);metrics<-readr::read_csv(file.path(out,'metrics.csv'),show_col_types=FALSE)
 all_p<-dplyr::bind_rows(readRDS(file.path(out,'calibrated-forecasts.rds'))$probabilities,
  dplyr::filter(readRDS(file.path(out,'native-forecasts.rds'))$probabilities,model=='BEFORE_TAIL'),x$probabilities)
 for(i in seq_len(nrow(metrics))) {
  m<-metrics[i,];s<-dplyr::filter(scores,cohort==m$cohort,model==m$model)
  testthat::expect_equal(nrow(s),m$n);testthat::expect_equal(sum(s$top1),m$hits1);testthat::expect_equal(sum(s$top2),m$hits2)
  testthat::expect_equal(mean(s$brier),m$brier,tolerance=1e-12);testthat::expect_equal(mean(-log(s$actual_probability)),m$logloss,tolerance=1e-12)
  dp<-dplyr::filter(all_p,model==m$model,outcome=='D',fixture_id%in%s$fixture_id)
  outcome<-s$actual_outcome[match(dp$fixture_id,s$fixture_id)]
  testthat::expect_equal(mean((dp$probability-as.double(outcome=='D'))^2),m$binary_draw_brier,tolerance=1e-12)
 }
 # Exercise the actual label-boundary assertion with a corrected post-freeze line.
 expressions<-as.list(parse(file.path(root,'r/fm171_26103_evaluate.R')))
 assertion<-Filter(function(z)is.call(z)&&identical(z[[1]],as.name('stopifnot'))&&grepl('label_handicap',paste(deparse(z),collapse=' ')),expressions)
 testthat::expect_length(assertion,1L)
 env<-new.env(parent=baseenv())
 env$label_binding<-tibble::tibble(label_provider_id=as.character(1:407),provider_id=as.character(1:407),label_handicap=rep(0,407),frozen_handicap=rep(0,407))
 testthat::expect_no_error(eval(assertion[[1]],env))
 env$label_binding$label_handicap[1]<-1
 testthat::expect_error(eval(assertion[[1]],env))
})

testthat::test_that('metadata and market intake bind transitive parsers and retain unavailable channels', {
 root<-rprojroot::find_root(rprojroot::has_file('AGENTS.md'));out<-file.path(root,'results/fm171-26103-draw-20261017')
 meta<-jsonlite::fromJSON(file.path(out,'metadata.json'),simplifyVector=FALSE)
 testthat::expect_length(meta$packets,407L);testthat::expect_equal(meta$network_attempts,0)
 testthat::expect_true(length(meta$implementation$files)>0L)
 testthat::expect_identical(meta$client_sha256,digest::digest(file=file.path(root,'src/fm171_26103_metadata.py'),algo='sha256'))
 mr<-jsonlite::fromJSON(file.path(out,'metadata-replay.json'));testthat::expect_identical(mr$status,'IDENTICAL_METADATA_REPLAY')
 market<-readRDS(file.path(out,'market-stage.rds'));testthat::expect_equal(nrow(market$audit),407L)
 testthat::expect_equal(sum(market$audit$sufficient&market$audit$consistent),3L)
 testthat::expect_true(all(!market$audit$sufficient[!market$audit$available]))
 # Regression: empty Asian/total candidates return typed empty tibbles without max(-Inf) warnings.
 empty<-tibble::tibble(company_id=character(),quote_at=as.POSIXct(character(),tz='UTC'))
 testthat::expect_no_warning(z<-dplyr::slice_max(dplyr::group_by(empty,company_id),quote_at,n=1L,with_ties=TRUE))
 testthat::expect_equal(nrow(z),0L)
})
