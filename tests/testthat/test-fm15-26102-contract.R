test_that('26102 native predictions cover the frozen roster with prior-only normalized components', {
  root <- Sys.getenv('FM_NATIVE_TEST_ROOT');stopifnot(nzchar(root))
  out <- file.path(root,'results/fm15-26102-20261012')
  m <- jsonlite::fromJSON(file.path(out,'native-manifest.json'))
  path <- file.path(out,m$native_file)
  expect_identical(digest::digest(file=path,algo='sha256'),m$sha256)
  x <- readRDS(path);expect_identical(beidan:::.score_margin_hash(x),m$object_hash)
  expect_equal(nrow(x$ledger),86L);expect_equal(length(x$entries),86L)
  expect_false(anyDuplicated(x$ledger$fixture_id)>0)
  expect_true(all(x$ledger$state=='NATIVE_READY'))
  expect_false(any(grepl('labels|selected-sp',names(x$source_hashes))))
  for(e in x$entries) {
    n <- e$native;r <- n$rates
    expect_s3_class(n$parameters,'tbl_df');expect_s3_class(r,'tbl_df')
    expect_true(all(r$matches>=12L & r$recent_matches==8L & r$ess>=8))
    expect_equal(r$goals_for,(r$long_for+r$recent_for)/2)
    expect_equal(r$goals_against,(r$long_against+r$recent_against)/2)
    expect_equal(n$parameters$lambda_home,(r$goals_for[r$role=='home']+r$goals_against[r$role=='away'])/2)
    expect_equal(n$parameters$lambda_away,(r$goals_for[r$role=='away']+r$goals_against[r$role=='home'])/2)
    expect_equal(sum(e$grid$probability),1,tolerance=1e-10)
    expect_true(all(e$grid$probability>=0))
    expect_identical(n$availability_mode,'HISTORICAL_DIAGNOSTIC')
    for(receipt in c(list(n$admission_receipt),n$receipts)) {
      expect_identical(receipt$target_issue,'26102')
      expect_lt(as.numeric(lubridate::ymd_hms(receipt$maximum_source_time,quiet=TRUE)),as.numeric(e$fixture$cutoff_utc))
      expect_lt(as.numeric(lubridate::ymd_hms(receipt$maximum_training_label_timestamp,quiet=TRUE)),as.numeric(e$fixture$cutoff_utc))
      expect_identical(receipt$availability$intended_use,'HISTORICAL_DIAGNOSTIC')
    }
  }
  inv <- jsonlite::fromJSON(file.path(out,'implementation-inventory.json'))
  expect_identical(inv$status,'RUN_BOUND_CURRENT_IMPLEMENTATION')
  for(i in seq_len(nrow(inv$files))) expect_identical(digest::digest(file=file.path(out,'implementation',inv$files$path[i]),algo='sha256'),inv$files$sha256[i])
})

test_that('26102 independent market diagnostics admit only identity-bound prior quotes', {
  root<-Sys.getenv('FM_NATIVE_TEST_ROOT');stopifnot(nzchar(root))
  out<-file.path(root,'results/fm15-26102-20261012')
  m<-jsonlite::fromJSON(file.path(out,'market-manifest.json'));p<-file.path(out,m$stage_file)
  expect_identical(digest::digest(file=p,algo='sha256'),m$sha256)
  x<-readRDS(p);expect_identical(beidan:::.score_margin_hash(x),m$object_hash)
  expect_equal(nrow(x$ledger),86L)
  expect_equal(sum(x$ledger$market_state=='COMPLETE'),71L)
  expect_equal(sum(x$ledger$market_state=='INCOMPLETE'),15L)
  expect_true(all(vapply(x$inputs$path,function(s)!grepl('labels|selected-sp',s),logical(1))))
  for(i in seq_len(nrow(x$inputs)))expect_identical(digest::digest(file=file.path(root,x$inputs$path[i]),algo='sha256'),x$inputs$sha256[i])
  n<-jsonlite::fromJSON(file.path(out,'native-manifest.json'));native<-readRDS(file.path(out,n$native_file))
  for(id in names(x$selected)) {
    f<-native$entries[[id]]$fixture;packet<-x$packets[[id]]
    expect_identical(packet$base_hash,beidan:::.score_margin_hash(native$entries[[id]]$grid))
    for(kind in names(x$selected[[id]])) {
      q<-x$selected[[id]][[kind]]
      expect_s3_class(q,'tbl_df');expect_s3_class(q$quote_at,'POSIXct')
      expect_true(all(q$fixture_id==id));expect_false(anyDuplicated(q$company_id)>0)
      expect_true(all(q$quote_at<f$cutoff_utc))
      expect_true(all(as.numeric(difftime(f$cutoff_utc,q$quote_at,units='hours'))<=48))
      numerical<-setdiff(names(q),c('fixture_id','company_id','quote_at'))
      expect_true(all(vapply(q[numerical],is.numeric,logical(1))))
    }
    if(!is.null(packet$independent_market))expect_equal(sum(packet$independent_market$probability),1,tolerance=1e-12)
  }
})

test_that('all26102 final scores, author receipts and independent replay are bound before evaluation', {
  root<-Sys.getenv('FM_NATIVE_TEST_ROOT');stopifnot(nzchar(root));out<-file.path(root,'results/fm15-26102-20261012')
  m<-jsonlite::fromJSON(file.path(out,'manifest.json'));bp<-file.path(out,m$batch_file)
  expect_identical(digest::digest(file=bp,algo='sha256'),m$sha256)
  x<-readRDS(bp);expect_identical(beidan:::.score_margin_hash(x),m$object_hash)
  expect_equal(length(x$entries),86L);expect_equal(nrow(x$probabilities),258L)
  expect_equal(sum(x$audit$reviewer=='PA_DEEPSEEK'),76L);expect_equal(sum(x$audit$reviewer=='ROOT_CODEX'),10L)
  expect_false(any(grepl('labels|selected-sp',x$input_ledger$path)))
  for(i in seq_len(nrow(x$input_ledger)))expect_identical(digest::digest(file=file.path(root,x$input_ledger$path[i]),algo='sha256'),x$input_ledger$sha256[i])
  for(id in names(x$entries)) {
    e<-x$entries[[id]]
    expect_identical(readRDS(file.path(root,e$score_path)),e$final)
    expect_equal(sum(e$final$grid$probability),1,tolerance=1e-12)
    expect_true(all(e$final$grid$probability>=0))
    expect_lt(as.numeric(e$base$max_source_available_utc),as.numeric(e$base$cutoff$cutoff_utc))
    expect_false(any(c('handicap','beidan_handicap','roles') %in% names(e$base)))
    expect_identical(e$review$base_hash,beidan:::.score_margin_hash(e$base$grid))
    if(e$policy$branch=='symmetric_center_tail') {
      expect_lte(e$policy$radius,2L)
      expect_identical(e$policy$core_margins,seq.int(e$policy$center-e$policy$radius,e$policy$center+e$policy$radius))
    }
    pp<-dplyr::filter(x$probabilities,fixture_id==id);expect_equal(sum(pp$probability),1,tolerance=1e-12)
  }
  selections<-list.files(out,pattern='^pa-selection-[0-9]+[.]json$',full.names=TRUE);expect_equal(length(selections),43L)
  for(path in selections) {
    s<-jsonlite::fromJSON(path);ip<-file.path(root,s$input_path);rp<-file.path(root,s$review_path)
    if(identical(s$reviewer,'ROOT_CODEX')) {
      r<-jsonlite::fromJSON(file.path(root,s$local_receipt_path));expect_identical(r$reviewer,'ROOT_CODEX');expect_false(r$target_settlement_consulted_in_this_review)
      expect_identical(digest::digest(file=ip,algo='sha256'),r$input_sha256);expect_identical(digest::digest(file=rp,algo='sha256'),r$review_sha256)
    } else {
      r<-jsonlite::fromJSON(file.path(root,s$call_path,'receipt.json'));expect_equal(r$exit_code,0L);expect_false(r$timed_out);expect_identical(r$model,'opencode/deepseek-v4.1-flash')
      expect_identical(digest::digest(file=file.path(root,s$prompt_path),algo='sha256'),r$prompt_sha256)
    }
  }
  replay<-jsonlite::fromJSON(file.path(out,'replay-receipt.json'));ledger<-readr::read_csv(file.path(out,'replay-ledger.csv'),show_col_types=FALSE)
  expect_identical(replay$status,'FULL_IDENTICAL_REPLAY');expect_identical(replay$forecast_sha256,m$sha256);expect_equal(nrow(ledger),86L);expect_true(all(as.matrix(dplyr::select(ledger,-fixture_id))))
})

test_that('26102 accuracy uses matched cohorts and reconciles all score means and hits', {
  root<-Sys.getenv('FM_NATIVE_TEST_ROOT');out<-file.path(root,'results/fm15-26102-20261012')
  metrics<-readr::read_csv(file.path(out,'metrics.csv'),show_col_types=FALSE);scores<-readr::read_csv(file.path(out,'scores.csv'),show_col_types=FALSE)
  expect_equal(nrow(metrics),12L)
  counts<-metrics |> dplyr::group_by(comparison,coverage) |> dplyr::summarise(unique_n=dplyr::n_distinct(n),.groups='drop');expect_true(all(counts$unique_n==1L))
  for(i in seq_len(nrow(metrics))) {
    r<-metrics[i,];s<-scores |> dplyr::filter(comparison==r$comparison,coverage==r$coverage,model==r$model)
    expect_equal(nrow(s),r$n);expect_equal(sum(s$top1),r$hits1);expect_equal(sum(s$top2),r$hits2)
    expect_equal(mean(s$brier),r$brier,tolerance=1e-12);expect_equal(mean(s$logloss),r$logloss,tolerance=1e-12)
  }
  expect_equal(metrics$n[metrics$comparison=='near_sale' & metrics$coverage=='all_native'],rep(86L,3))
  inputs<-jsonlite::fromJSON(file.path(out,'evaluation-inputs.json'));manifest<-jsonlite::fromJSON(file.path(out,'manifest.json'))
  expect_identical(inputs$forecast_sha256,manifest$sha256)
  expect_identical(inputs$label_sha256,digest::digest(file=file.path(root,inputs$label_path),algo='sha256'))
  expect_identical(inputs$sp_sha256,digest::digest(file=file.path(root,inputs$sp_path),algo='sha256'))
  expect_gt(as.numeric(lubridate::ymd_hms(inputs$evaluation_generated_at_utc)),as.numeric(lubridate::ymd_hms(inputs$forecast_generated_at_utc)))
})

test_that('market DC references remain separate normalized prior-cutoff diagnostics', {
  root<-Sys.getenv('FM_NATIVE_TEST_ROOT');out<-file.path(root,'results/fm15-26102-20261012')
  m<-jsonlite::fromJSON(file.path(out,'market-diagnostic-manifest.json'));p<-file.path(out,m$diagnostic_file)
  expect_identical(digest::digest(file=p,algo='sha256'),m$sha256);x<-readRDS(p);expect_identical(beidan:::.score_margin_hash(x),m$object_hash)
  expect_equal(length(x$references),71L);expect_equal(nrow(x$ledger),86L)
  for(e in x$references) {
    expect_s3_class(e$model$parameters,'tbl_df');expect_equal(sum(e$model$grid$probability),1,tolerance=1e-12)
    expect_equal(e$model$parameters$lambda_home+e$model$parameters$lambda_away,e$total_mean,tolerance=1e-10)
    expect_equal(e$model$parameters$rho,-.1)
    for(row in e$evidence_rows)expect_lt(as.numeric(lubridate::ymd_hms(row$data_available_ts)),as.numeric(e$cutoff$cutoff_utc))
  }
  final<-jsonlite::fromJSON(file.path(out,'manifest.json'));batch<-readRDS(file.path(out,final$batch_file))
  expect_false(any(grepl('market-diagnostic',batch$input_ledger$path)))
})

test_that('fixed-basket completeness excludes every partial Euro basket without changing forecasts', {
  root<-Sys.getenv('FM_NATIVE_TEST_ROOT');out<-file.path(root,'results/fm15-26102-20261012')
  cm<-jsonlite::fromJSON(file.path(out,'coverage-manifest.json'));p<-file.path(out,cm$coverage_file)
  expect_identical(digest::digest(file=p,algo='sha256'),cm$sha256);x<-readRDS(p);expect_identical(beidan:::.score_margin_hash(x),cm$object_hash)
  fm<-jsonlite::fromJSON(file.path(out,'manifest.json'));expect_identical(x$forecast_sha256,fm$sha256);expect_false(cm$probabilities_changed)
  mm<-jsonlite::fromJSON(file.path(out,'market-manifest.json'));market<-readRDS(file.path(out,mm$stage_file))
  expect_equal(sum(x$coverage$market_state=='COMPLETE'),43L);expect_equal(sum(x$coverage$channels_complete),71L)
  expect_equal(sum(x$coverage$channels_complete & x$coverage$market_state!='COMPLETE'),28L)
  expect_equal(length(x$market_references),43L)
  for(id in names(market$selected)) {
    q<-market$selected[[id]];row<-dplyr::filter(x$coverage,fixture_id==id)
    expected<-all(vapply(q,nrow,integer(1))>0L)&&setequal(q$euro$company_id,c('281','115','82','432'))
    expect_identical(row$market_state=='COMPLETE',expected)
    expect_equal(row$euro_company_count,nrow(q$euro))
    if(nrow(q$euro)<4L)expect_identical(row$market_state,'INCOMPLETE')
  }
  for(id in c('26102:5','26102:16','26102:81'))expect_identical(x$coverage$market_state[match(id,x$coverage$fixture_id)],'INCOMPLETE')
  expect_true(setequal(names(x$market_references),x$coverage$fixture_id[x$coverage$market_state=='COMPLETE']))
  probs<-readr::read_csv(file.path(out,'probabilities.csv'),show_col_types=FALSE);original<-readRDS(file.path(out,fm$batch_file))$probabilities
  # Binary artifact identity is exact; decimal CSV conversion may differ by one ULP.
  expect_identical(digest::digest(file=file.path(out,fm$batch_file),algo='sha256'),cm$forecast_sha256)
  expect_equal(probs$probability,original$probability,tolerance=1e-15)
})
