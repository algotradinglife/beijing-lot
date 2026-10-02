testthat::test_that("original raw SP is recovered before cutoff without late-price backfill", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  source(file.path(root,"r/recent_sp_replay.R"),local=TRUE)
  path <- file.path(root,"inputs/26098_walkthrough/print/26098-20260926-195204.rds")
  before <- digest::digest(file=path,algo="sha256")
  backend <- beidan::python_backend(file.path(root,".venv/bin/python"))
  raw_paths <- list(nowscore_raw=file.path(root,"tests/fixtures/recent_sp_recovery/26098.nowscore.raw.html"),
    source_meta=file.path(root,"tests/fixtures/recent_sp_recovery/26098.source.json"))
  r <- RecentSpReplay(path,backend,raw_paths)
  testthat::expect_equal(nrow(r$quotes),147L)
  testthat::expect_true(all(r$quotes$quote_at<r$source$cutoff$cutoff_utc))
  testthat::expect_equal(format(r$quotes$quote_at[1],tz="Asia/Shanghai","%H:%M:%S"),"19:38:21")
  testthat::expect_identical(before,digest::digest(file=path,algo="sha256"))
  z <- RecentSpSource(r)
  testthat::expect_identical(z$outputs$recovered$evaluated$cutoff,r$source$cutoff)
  testthat::expect_true(all(z$outputs$recovered$evaluated$portfolio$probabilities$fixture_id %in% r$source$probabilities$fixture_id))
  bad <- r;bad$quotes$sp_raw[1]<-99
  testthat::expect_error(RecentSpSource(bad),"binding")
  b <- readRDS(path);tmp<-tempfile(fileext=".rds");m<-jsonlite::read_json(raw_paths$source_meta)
  m$observed_at$nowscore<-"2026-09-26T15:15:51Z";j<-tempfile(fileext=".json")
  jsonlite::write_json(m,j,auto_unbox=TRUE);attr(b$schedule,"written")$source_meta<-j;saveRDS(b,tmp)
  changed_paths <- raw_paths; changed_paths$source_meta <- j
  testthat::expect_error(RecentSpReplay(tmp,backend,changed_paths),"not before cutoff")
  m$observed_at$nowscore<-"2026-09-26T11:38:21.598147Z";m$raw_sha256$nowscore<-"wrong"
  jsonlite::write_json(m,j,auto_unbox=TRUE)
  testthat::expect_error(RecentSpReplay(tmp,backend,changed_paths),"hash mismatch")
})
