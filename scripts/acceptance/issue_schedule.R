# Control-side acceptance: use production R entry point and independently recorded
# source times. Caller explicitly loads beidan, backend and schedule_snapshot_dir.
stopifnot(dir.exists(schedule_snapshot_dir))
raw_500 <- readBin(file.path(schedule_snapshot_dir, "500.raw.html"), "raw",
                   n = file.info(file.path(schedule_snapshot_dir, "500.raw.html"))$size)
raw_nowscore <- readBin(file.path(schedule_snapshot_dir, "nowscore.all.raw.html"), "raw",
  n = file.info(file.path(schedule_snapshot_dir, "nowscore.all.raw.html"))$size)
raw_output <- tempfile("schedule-replay-")
schedule <- beidan::fetch_issue_schedule(
  "26098", raw_dir = raw_output, backend = backend,
  pages = list(
    "500" = raw_500, nowscore = raw_nowscore,
    "500_observed_at" = "2026-09-25T13:38:55.362121+00:00",
    "nowscore_observed_at" = "2026-09-25T13:44:39.900629+00:00"
  )
)
expected <- readr::read_csv(
  file.path(project_root, "scripts/acceptance/data/issue_26098_kickoff_expected.csv"),
  col_types = readr::cols(.default = readr::col_character())
)
stopifnot(nrow(readr::problems(expected)) == 0L)
testthat::expect_s3_class(schedule, "tbl_df")
testthat::expect_equal(nrow(schedule), 146L)
testthat::expect_equal(schedule$slot, seq_len(146L))
testthat::expect_equal(anyDuplicated(schedule$fixture_key), 0L)
testthat::expect_false(anyNA(schedule$kickoff_at))
testthat::expect_equal(
  as.numeric(schedule$kickoff_at),
  as.numeric(lubridate::ymd_hms(expected$kickoff_beijing, tz = "Asia/Shanghai"))
)
testthat::expect_equal(
  as.numeric(schedule$sale_end_at),
  as.numeric(lubridate::ymd_hms(expected$sale_end_beijing, tz = "Asia/Shanghai"))
)
testthat::expect_true(all(schedule$kickoff_at >= schedule$sale_end_at))
testthat::expect_equal(schedule$match_status[1:5], rep("finished", 5L))
testthat::expect_equal(schedule$match_status[6], "unknown")
testthat::expect_equal(schedule$raw_display_nowscore[6], "截止")
testthat::expect_true(all(schedule$match_status[7:146] == "unknown"))
testthat::expect_equal(
  as.numeric(schedule$observed_at),
  rep(as.numeric(lubridate::ymd_hms("2026-09-25 13:44:39.900629", tz = "UTC")), 146L),
  tolerance = 1e-6
)
# Evidence-preserving names: ambiguity remains visible, age/sex not discarded.
testthat::expect_equal(sum(schedule$identity_method == "normalized_name"), 121L)
testthat::expect_true(all(schedule$identity_method[c(1L,77L)] != "normalized_name"))
# Explicit independent export; fetching never exports a canonical CSV implicitly.
readr::write_csv(schedule, file.path(raw_output, "schedule.csv"))
cat("Full 26098 R-boundary acceptance passed: 146 rows and independent kickoff/deadline ledger.\n")
