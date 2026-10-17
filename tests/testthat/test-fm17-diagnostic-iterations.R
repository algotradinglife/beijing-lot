test_that('diagnostic inputs, labelled cases and fixed-policy candidates are bound', {
 root<-Sys.getenv('FM17_DIAG_ROOT');stopifnot(nzchar(root))
 out<-file.path(root,'results/fm17-diagnostic-iterations-20261013')
 r<-jsonlite::fromJSON(file.path(out,'round1-receipt.json'))
 expect_true(all(purrr::map_chr(file.path(root,r$inputs$path),~digest::digest(file=.x,algo='sha256'))==r$inputs$sha256))
 expect_true(all(purrr::map_chr(file.path(out,r$outputs$path),~digest::digest(file=.x,algo='sha256'))==r$outputs$sha256))
 a<-readr::read_csv(file.path(out,'round1-fixtures.csv'),show_col_types=FALSE)
 expect_equal(nrow(a),345L);expect_equal(sum(a$bd_top1_fm_top2_loss),7L)
 expect_equal(sum(a$raw_top2_tail_loss),13L)
 expect_lte(max(a$top23_gap[a$raw_top2_tail_loss]),.0256)
 expect_equal(sum(a$selected_source[a$bd_top1_fm_top2_loss]=='native'),6L)
 expect_equal(sum(a$selected_source=='native'&a$euro_companies==0&a$asian_rows==0&a$total_rows==0),64L)
 m<-jsonlite::fromJSON(file.path(out,'round2-manifest.json'));rp<-jsonlite::fromJSON(file.path(out,'round2-replay.json'))
 x<-readRDS(file.path(out,'round2-forecasts.rds'))
 expect_equal(length(x$entries),346L);expect_equal(nrow(x$probabilities),346L*2L*3L)
 expect_identical(digest::digest(file=file.path(out,'round2-forecasts.rds'),algo='sha256'),m$forecast_sha256)
 expect_identical(rp$sha256,m$forecast_sha256);expect_identical(rp$status,'FULL_IDENTICAL_REPLAY')
 for(e in x$entries)for(z in e$results) {
  expect_identical(z$final$cutoff,e$cutoff)
  expect_equal(sum(z$final$grid$probability),1,tolerance=1e-12)
  expect_identical(z$final$receipt$source_context$source_hashes$tail_binding,z$core$binding_hash)
  expect_true(z$core$policy$coefficient%in%c(.3,.6))
  expect_true(z$core$policy$coverage%in%c(.9,.95))
 }
 flags<-readr::read_csv(file.path(out,'round2-prediction-only-flags.csv'),show_col_types=FALSE)
 expect_equal(sum(flags$top2_set_changed),51L)
 c<-dplyr::left_join(a,flags |> dplyr::select(fixture_id,top2_set_changed),by='fixture_id',relationship='one-to-one')
 expect_true(all(c$top2_set_changed[c$raw_top2_tail_loss]))
 for(kind in c('market','native')) {
  l<-readr::read_csv(file.path(out,paste0('round2-',kind,'-component-ledger.csv')),show_col_types=FALSE)
  expect_equal(nrow(l),346L);expect_false(anyNA(l$cutoff_utc));expect_true(all(nchar(l$component_seal)>0))
 }
})

test_that('native sensitivities preserve chronology and separately reconciled mixtures', {
 root<-Sys.getenv('FM17_DIAG_ROOT');stopifnot(nzchar(root))
 out<-file.path(root,'results/fm17-diagnostic-iterations-20261013')
 x<-readRDS(file.path(out,'round3-native-forecasts.rds'))
 m<-jsonlite::fromJSON(file.path(out,'round3-native-manifest.json'));rp<-jsonlite::fromJSON(file.path(out,'round3-native-replay.json'))
 expect_true(m$prior_history_refit);expect_false(m$target_label_optimization)
 expect_identical(rp$status,'FULL_IDENTICAL_REPLAY');expect_identical(rp$sha256,m$forecast_sha256)
 expect_length(x$entries,117L);expect_equal(nrow(x$probabilities),117L*3L*3L)
 parent<-readRDS(file.path(root,'results/fm17-three-issues-20261013/forecasts.rds'))
 for(id in names(x$entries)) {
  e<-x$entries[[id]]
  for(z in e$results) {
   alpha<-z$native$policy$alpha
   expect_true(alpha%in%c(.25,.5,.75));expect_equal(sum(z$final$grid$probability),1,tolerance=1e-12)
   expect_identical(z$final$cutoff,e$cutoff)
   for(i in seq_along(z$native$components)) {
    c<-z$native$components[[i]];rec<-z$native$receipts[[i]]
    w<-tibble::as_tibble(jsonlite::fromJSON(c$ledger))
    d<-dplyr::bind_rows(c$distributions)
    # Prove each serialized 10-decimal row equals its exact policy weight;
    # use the exact weights for mass/ESS assertions rather than a relative
    # comparison of rounded aggregate masses. No tolerance is widened.
    n<-nrow(w);recent<-w$recent_mass>0
    expect_equal(n,rec$weight_receipt$rows)
    expect_equal(sum(recent),z$native$policy$recent_n)
    exact_long<-rep((1-alpha)/n,n)
    exact_recent<-ifelse(recent,alpha/z$native$policy$recent_n,0)
    exact_total<-exact_long+exact_recent
    expect_equal(w$long_mass,round(exact_long,10),tolerance=1e-14)
    expect_equal(w$recent_mass,round(exact_recent,10),tolerance=1e-14)
    expect_equal(w$total_mass,round(exact_total,10),tolerance=1e-14)
    expect_equal(sum(exact_long),1-alpha,tolerance=1e-12)
    expect_equal(sum(exact_recent),alpha,tolerance=1e-12)
    expect_equal(sum(exact_total),1,tolerance=1e-12)
    expect_equal(1/sum(exact_total^2),rec$weight_receipt$effective_sample_size,tolerance=1e-12)
    available<-as.POSIXct(w$label_available_ts,format='%Y-%m-%dT%H:%M:%S',tz='UTC')
    expect_gte(min(as.numeric(available[recent])),max(as.numeric(available[!recent])))
    expect_equal(rec$weight_receipt$long_history_mass,1-alpha,tolerance=1e-12)
    expect_equal(rec$weight_receipt$recent_state_mass,alpha,tolerance=1e-12)
    expect_equal(sum(d$long),1,tolerance=1e-12);expect_equal(sum(d$recent),1,tolerance=1e-12)
    expect_equal(d$mixture,(1-alpha)*d$long+alpha*d$recent,tolerance=1e-12)
    expect_gte(rec$weight_receipt$effective_sample_size,8)
    expect_lt(as.numeric(lubridate::ymd_hms(rec$maximum_source_time,tz='UTC')),as.numeric(e$cutoff$cutoff_utc))
    expect_lt(as.numeric(lubridate::ymd_hms(rec$maximum_training_label_timestamp,tz='UTC')),as.numeric(e$cutoff$cutoff_utc))
   }
  }
  expect_equal(e$results[['NATIVE_ALPHA_50']]$final$grid$probability,parent$entries[[id]]$results[['FM-1.7.0']]$final$grid$probability,tolerance=1e-10)
 }
})

test_that('partial-market projections have known independent constraint values and scope', {
 root<-Sys.getenv('FM17_DIAG_ROOT');stopifnot(nzchar(root))
 out<-file.path(root,'results/fm17-diagnostic-iterations-20261013')
 x<-readRDS(file.path(out,'round3-partial-forecasts.rds'))
 expect_length(x$entries,60L);expect_equal(nrow(x$coverage),346L)
 expect_equal(sum(x$coverage$status=='READY'&x$coverage$selected_source=='native'),9L)
 for(e in x$entries) {
  p<-e$partial
  expect_equal(sum(p$grid$probability),1,tolerance=1e-12)
  expect_equal(p$asian_model,p$asian_target,tolerance=1e-7)
  expect_identical(p$receipt$cutoff,e$cutoff)
  expect_true(p$asian$quote_at<e$cutoff$cutoff_utc);expect_true(p$totals$quote_at<e$cutoff$cutoff_utc)
  for(z in e$results){expect_identical(z$final$cutoff,e$cutoff);expect_equal(sum(z$final$grid$probability),1,tolerance=1e-12)}
 }
 e<-x$entries[['26102:6']]
 expect_equal(e$partial$parameters$lambda_home,1.6460335893018079,tolerance=1e-8)
 expect_equal(e$partial$parameters$lambda_away,1.0547264780573675,tolerance=1e-8)
 expect_equal(sum(e$partial$grid$probability[e$partial$grid$home_goals>e$partial$grid$away_goals]),.5,tolerance=1e-8)
 expect_equal(e$partial$parameters$total_mean,2.7007600673591754,tolerance=1e-8)
})

test_that('all descriptive candidate scores use matched denominators and reproducible sums', {
 root<-Sys.getenv('FM17_DIAG_ROOT');stopifnot(nzchar(root))
 out<-file.path(root,'results/fm17-diagnostic-iterations-20261013')
 for(round in c('round2','round3')) {
  m<-readr::read_csv(file.path(out,paste0(round,'-metrics.csv')),show_col_types=FALSE)
  s<-readr::read_csv(file.path(out,paste0(round,'-scores.csv')),show_col_types=FALSE)
  key<-c(if(round=='round3')'experiment', 'comparison','issue_id','cohort')
  for(i in seq_len(nrow(m))) {
   r<-m[i,];if(startsWith(r$model,'北单')||r$model=='FM-1.6.0')next
   z<-s[s$model==r$model,,drop=FALSE]
   for(k in key)z<-z[z[[k]]==r[[k]],,drop=FALSE]
   expect_equal(nrow(z),r$n);expect_equal(sum(z$top1),r$hits1);expect_equal(sum(z$top2),r$hits2)
   expect_equal(mean(z$brier),r$brier);expect_equal(mean(z$logloss),r$logloss)
  }
  groups<-m |> dplyr::group_by(dplyr::across(dplyr::all_of(key))) |> dplyr::summarise(n=dplyr::n_distinct(n),.groups='drop')
  expect_true(all(groups$n==1L))
 }
})

test_that('native prior fits ignore future scores and target identity even with bad early dates', {
 root<-Sys.getenv('FM17_DIAG_ROOT');stopifnot(nzchar(root))
 out<-file.path(root,'results/fm17-diagnostic-iterations-20261013')
 x<-readRDS(file.path(out,'round3-native-forecasts.rds'))
 s<-readRDS(file.path(root,'results/fm16-three-issues-20261012/stage.rds'))
 e<-x$entries[['26102:6']];f<-s$native[['26102:6']]$fixture;impl<-s$implementation
 parent<-readRDS(file.path(root,'results/fundamental-issues-20261011/run-20261011T011533.304058Z/26102-frozen.rds'))
 h<-tibble::as_tibble(parent$history) |> dplyr::filter(fixture_id=='26102:6') |> dplyr::mutate(row_key=paste(scope,match_id,sep=':'),event_date=as.character(event_date))
 # The current installed wrapper selects its own backend; old source wrappers
 # cannot be imported into a process already initialized from the installed package.
 reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
 reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
 shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
 ct<-format(e$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
 r<-e$results[['NATIVE_ALPHA_50']]
 for(kind in c('future','target')) {
  row<-h[h$scope=='home_recent',][1,]
  row$match_id<-if(kind=='future')'SYNTHETIC_FUTURE'else f$provider_id
  row$home_id<-f$home_id;row$away_id<-f$away_id;row$home_score<-7L;row$away_score<-0L
  row$row_key<-paste(row$scope,row$match_id,sep=':')
  row$event_date<-format(e$cutoff$cutoff_utc+if(kind=='future')86400 else -2*86400,'%Y-%m-%d',tz='UTC')
  hm<-h |> dplyr::filter(match_id!=row$match_id) |> dplyr::bind_rows(row)
  hashes<-x$bindings;hashes$mutation_test<-beidan:::.score_margin_hash(hm)
  n<-beidan:::estimate_recent_venue_goals(hm,f[c('fixture_id','issue_id','provider_id','home_id','away_id')],as.character(parent$fixtures$provider_id),shared$Cutoff$decision_epoch('26102',ct),hashes,root,r$native$policy,'HISTORICAL_DIAGNOSTIC')
  expect_equal(n$parameters,r$native$parameters,tolerance=1e-10)
  expect_equal(n$rates,r$native$rates,tolerance=1e-10)
  expect_false(identical(n$admission_receipt$cache_key,r$native$admission_receipt$cache_key))
  if(kind=='target')expect_gt(n$admission_receipt$target_rows_excluded,0L)
 }
})

test_that('report inventory rejects mutated input content', {
 root <- normalizePath(Sys.getenv('FM17_DIAG_ROOT', getwd()))
 q <- readLines(file.path(root,'quarto/fm17_diagnostic_iterations_20261013.qmd'))
 guard <- q[startsWith(q,'for(i in seq_len(nrow(inv$files)))')]
 expect_length(guard,1L)
 td <- tempfile('fm17-qmd-guard-');dir.create(td)
 on.exit(unlink(td,recursive=TRUE),add=TRUE)
 writeLines('declared snapshot',file.path(td,'input.csv'))
 env <- new.env(parent=globalenv());env$root <- td
 env$inv <- list(files=tibble::tibble(path='input.csv',sha256=digest::digest(file=file.path(td,'input.csv'),algo='sha256')))
 expect_error(eval(parse(text=guard),envir=env),NA)
 writeLines('post-publication mutation',file.path(td,'input.csv'))
 expect_error(eval(parse(text=guard),envir=env))
})
