# Helper exercised through the real build/save/read pipeline below.
storage_result <- function() {
  issue <- make_example_issue("26097", match_kickoff_window("2026-09-22", 7L), seed = 42L)
  cutoff <- list(issue_id = "26097", cutoff_utc = as.POSIXct("2026-09-22 12:00:00", tz = "UTC"))
  inputs <- read_match_inputs(example_match_source(issue), "26097")
  prepared <- prepare_engine(inputs, cutoff,
    list(members = c("c01", "c02", "c03"), missing = "error"),
    list(companies = NULL, line = "nearest_main", watermark = "decimal"))
  estimated <- estimate_engine(prepared, cutoff, -.14, c(.1, 16), 1e-10)
  projection <- list(cutoff = cutoff, fixtures = prepared$fixtures,
    probabilities = estimated$probabilities, prematch_sp = prepared$prematch_sp,
    match_status = prepared$match_status, fit = estimated$fit, exclusions = estimated$exclusions)
  config <- parlay_allocation_configs(parlay_settings(reset = TRUE))[["A"]]
  parlay_build_plan(projection, config)
}

testthat::test_that("saved real build roundtrips and never overwrites", {
  result <- storage_result()
  path <- tempfile(fileext = ".rds")
  on.exit(unlink(path))
  recorded <- lubridate::ymd_hms("2026-09-22 20:01:00", tz = "Asia/Shanghai")
  parlay_save_result(result, path, recorded)
  restored <- parlay_read_result(path, "26097", lubridate::with_tz(result$plan$epoch_utc, "Asia/Shanghai"))
  testthat::expect_identical(restored, result)
  testthat::expect_gt(nrow(restored$plan$purchases), 0)
  original <- readBin(path, "raw", n = file.info(path)$size)
  testthat::expect_error(parlay_save_result(result, path, recorded), "overwrite")
  testthat::expect_identical(readBin(path, "raw", n = file.info(path)$size), original)
  testthat::expect_error(parlay_read_result(path, "26098", result$plan$epoch_utc), "mismatch")
  testthat::expect_error(parlay_read_result(path, "26097", result$plan$epoch_utc + 1), "mismatch")
  envelope <- readRDS(path)
  envelope$result$plan$purchases$stake_cny[1] <- 999
  saveRDS(envelope, path)
  testthat::expect_error(parlay_read_result(path, "26097", result$plan$epoch_utc), "integrity")
})

testthat::test_that("invalid chronology and result bindings leave no saved file", {
  result <- storage_result()
  path <- tempfile()
  testthat::expect_error(parlay_save_result(result, path, result$plan$epoch_utc - 1), "after decision")
  testthat::expect_error(parlay_save_result(result, path, Sys.time() + 3600), "future")
  testthat::expect_false(file.exists(path))
  broken <- result
  broken$cutoff$issue_id <- "26098"
  testthat::expect_error(parlay_save_result(broken, path, Sys.time()), "identity mismatch")
  broken <- result
  broken$funded$purchases$stake_cny[1] <- 999
  testthat::expect_error(parlay_save_result(broken, path, Sys.time()), "ledger mismatch")
  testthat::expect_error(parlay_save_result(list(), path, Sys.time()), "missing")
  testthat::expect_error(parlay_save_result(result, file.path(tempfile(), "x.rds"), Sys.time()), "directory")
  testthat::expect_error(parlay_read_result(path, "26097", result$plan$epoch_utc))
})

testthat::test_that("header edits and emptied financial ledgers cannot pass save", {
  result <- storage_result()
  path <- tempfile()
  broken <- result
  broken$plan$issue_id <- broken$cutoff$issue_id <- "26098"
  testthat::expect_error(parlay_save_result(broken, path, Sys.time()), "purchase decision")
  broken <- result
  broken$plan$epoch_utc <- broken$cutoff$cutoff_utc <- result$plan$epoch_utc + 60
  testthat::expect_error(parlay_save_result(broken, path, Sys.time()), "purchase decision")
  broken <- result
  broken$plan$funded <- broken$plan$funded[0, ]
  testthat::expect_error(parlay_save_result(broken, path, Sys.time()), "funded ledger")
  broken <- result
  broken$history <- list(purchases = match_typed_empty("purchases"), fixture_sets = list())
  testthat::expect_error(parlay_save_result(broken, path, Sys.time()), "history does not reconcile")
  broken <- result
  broken$history$purchases$epoch_at[1] <- result$plan$epoch_utc + 60
  testthat::expect_error(parlay_save_result(broken, path, Sys.time()), "chronology")
  testthat::expect_false(file.exists(path))
})
