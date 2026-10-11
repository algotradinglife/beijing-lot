test_that('FM15 two-issue native stage covers the full roster without target labels', {
  root <- Sys.getenv('FM_NATIVE_TEST_ROOT');stopifnot(nzchar(root))
  out <- file.path(root,'results/fm15-two-issues-20261012')
  x <- readRDS(file.path(out,'native-stage.rds'))
  expect_s3_class(x$ledger,'tbl_df')
  expect_equal(nrow(x$ledger),261L)
  expect_equal(sum(x$ledger$status=='CUTOFF_UNAVAILABLE'),1L)
  expect_equal(length(x$entries),260L)
  expect_false(anyDuplicated(x$ledger$fixture_id)>0)
  expect_false(any(grepl('labels[.]rds|selected-sp',unlist(lapply(x$inputs,names)))))
  for(e in x$entries) {
    expect_equal(sum(e$grid$probability),1,tolerance=1e-12)
    expect_equal(e$native$rates$recent_matches,c(8L,8L))
    expect_true(all(e$native$rates$matches>=12L))
    expect_true(all(e$native$rates$ess>=8))
    expect_identical(e$packet$base_hash,beidan:::.score_margin_hash(e$grid))
    expect_true(lubridate::ymd_hms(e$native$admission_receipt$maximum_source_time,tz='UTC')<e$fixture$cutoff_utc)
    expect_equal(e$native$policy$alpha,.5)
  }
})

test_that('FM15 final artifacts bind native grids, reviews, chronology and projected classes', {
  root <- Sys.getenv('FM_NATIVE_TEST_ROOT');stopifnot(nzchar(root))
  out <- file.path(root,'results/fm15-two-issues-20261012')
  m <- jsonlite::fromJSON(file.path(out,'manifest.json'))
  path <- file.path(out,m$batch_file)
  expect_identical(digest::digest(file=path,algo='sha256'),m$sha256)
  x <- readRDS(path)
  expect_identical(beidan:::.score_margin_hash(x),m$object_hash)
  expect_equal(length(x$entries),260L)
  expect_false(any(grepl('labels[.]rds|selected-sp',x$input_ledger$path)))
  expect_true(nrow(x$input_ledger)>0)
  expect_true(all(purrr::map_chr(file.path(root,x$input_ledger$path),~digest::digest(file=.x,algo='sha256'))==x$input_ledger$sha256))
  for(e in x$entries) {
    expect_identical(readRDS(file.path(root,e$score_path)),e$final)
    expect_identical(e$review$base_hash,beidan:::.score_margin_hash(e$base$grid))
    expect_true(e$base$max_source_available_utc<e$base$cutoff$cutoff_utc)
    expect_false(any(c('handicap','beidan_handicap','roles') %in% names(e$base)))
    expect_equal(sum(e$final$grid$probability),1,tolerance=1e-12)
    expect_true(e$policy$radius<=2L || is.na(e$policy$radius))
  }
  sums <- dplyr::summarise(dplyr::group_by(x$probabilities,fixture_id),mass=sum(probability),rows=dplyr::n())
  expect_equal(sums$mass,rep(1,260),tolerance=1e-12)
  expect_equal(sums$rows,rep(3L,260))
})

test_that('every blinded review has an authenticated author and grid binding', {
  root<-Sys.getenv('FM_NATIVE_TEST_ROOT');stopifnot(nzchar(root))
  out<-file.path(root,'results/fm15-two-issues-20261012')
  packets<-jsonlite::fromJSON(file.path(out,'review-inputs.json'),simplifyVector=FALSE)$fixtures
  by_id<-stats::setNames(packets,vapply(packets,`[[`,character(1),'fixture_id'))
  selections<-list.files(out,pattern='^pa-selection-[0-9]+[.]json$',full.names=TRUE)
  expect_equal(length(selections),44L)
  ids<-character();local_ids<-character()
  for(path in selections) {
    s<-jsonlite::fromJSON(path)
    rows<-jsonlite::fromJSON(file.path(root,s$review_path),simplifyVector=FALSE)
    for(row in rows) {
      p<-by_id[[row$fixture_id]]
      expect_identical(row$base_hash,p$base_hash)
      expect_identical(row$cutoff_utc,p$cutoff_utc)
      expect_true(row$decision %in% c('apply','retain'))
      expect_true(row$market_action %in% c('KEEP_NATIVE','UNIDENTIFIED_SHIFT'))
      expect_true(row$market_action!='UNIDENTIFIED_SHIFT'||row$decision=='retain')
      ids<-c(ids,row$fixture_id)
    }
    for(lp in s$local_review_receipts) {
      r<-jsonlite::fromJSON(file.path(root,lp))
      expect_identical(r$reviewer,'ROOT_CODEX')
      expect_false(r$target_settlement_consulted_in_this_review)
      expect_identical(digest::digest(file=file.path(root,r$review_path),algo='sha256'),r$review_sha256)
      expect_identical(digest::digest(file=file.path(root,r$input_path),algo='sha256'),r$input_sha256)
      local_ids<-c(local_ids,r$fixture_id)
    }
    calls<-if(is.null(s$call_paths)) s$call_path else s$call_paths
    for(cp in calls) {
      r<-jsonlite::fromJSON(file.path(root,cp,'receipt.json'))
      expect_equal(r$exit_code,0L);expect_false(r$timed_out)
      expect_identical(r$model,'opencode/deepseek-v4.1-flash')
      expect_identical(digest::digest(file=file.path(out,'prompt-receipts',paste0(r$prompt_sha256,'.txt')),algo='sha256'),r$prompt_sha256)
    }
  }
  expect_setequal(ids,names(by_id));expect_false(anyDuplicated(ids)>0)
  expect_equal(length(local_ids),111L)
  expect_equal(length(ids)-length(local_ids),149L)
})

test_that('historical implementation snapshots authenticate full independent replay', {
  root <- Sys.getenv('FM_NATIVE_TEST_ROOT');stopifnot(nzchar(root))
  out <- file.path(root,'results/fm15-two-issues-20261012')
  inv <- jsonlite::fromJSON(file.path(out,'implementation-snapshot-inventory.json'))
  snapshot <- file.path(out,'implementation-snapshot')
  for(i in seq_len(nrow(inv$files))) {
    expect_identical(digest::digest(file=file.path(snapshot,inv$files$path[i]),algo='sha256'),inv$files$sha256[i])
  }
  receipt <- jsonlite::fromJSON(file.path(out,'replay-receipt.json'))
  manifest <- jsonlite::fromJSON(file.path(out,'manifest.json'))
  ledger <- readr::read_csv(file.path(out,'replay-ledger.csv'),show_col_types=FALSE)
  expect_identical(receipt$status,'FULL_IDENTICAL_REPLAY')
  expect_identical(receipt$forecast_sha256,manifest$sha256)
  expect_identical(receipt$snapshot_inventory_sha256,digest::digest(file=file.path(out,'implementation-snapshot-inventory.json'),algo='sha256'))
  expect_identical(receipt$replay_code_sha256,digest::digest(file=file.path(root,'r/fm15_two_issue_replay.R'),algo='sha256'))
  expect_equal(nrow(ledger),260L)
  expect_false(anyDuplicated(ledger$fixture_id)>0)
  expect_true(all(as.matrix(dplyr::select(ledger,-fixture_id))))
  # Any changed byte invalidates the archived implementation identity.
  original <- readBin(file.path(snapshot,inv$files$path[1]),'raw',n=file.info(file.path(snapshot,inv$files$path[1]))$size)
  bad <- tempfile();on.exit(unlink(bad),add=TRUE);writeBin(c(original,as.raw(0)),bad)
  expect_false(identical(digest::digest(file=bad,algo='sha256'),inv$files$sha256[1]))
})
