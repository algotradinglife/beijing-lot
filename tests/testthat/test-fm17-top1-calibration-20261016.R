testthat::test_that("frozen calibration client reconciles known universes and receipt hashes", {
  root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
  out <- tempfile("top1-reliability-")
  log <- tempfile()
  status <- system2("/opt/R/4.6.1/bin/Rscript", shQuote(c(
    file.path(root, "r/fm17_top1_calibration.R"), root, out)),
    env = paste0("R_LIBS=", shQuote(paste(.libPaths(), collapse = ":"))), stdout = log, stderr = log)
  testthat::expect_equal(status, 0L, info = paste(readLines(log), collapse = "\n"))
  s <- readr::read_csv(file.path(out, "summary.csv"), show_col_types = FALSE)
  b <- readr::read_csv(file.path(out, "bins.csv"), show_col_types = FALSE)
  f <- readr::read_csv(file.path(out, "fixtures.csv"), show_col_types = FALSE)
  all <- dplyr::filter(s, dimension == "all", model == "FM-1.7.0")
  testthat::expect_equal(all$n[match(c("same_cutoff", "near_sale"), all$comparison)], c(214, 345))
  testthat::expect_equal(all$hits1[all$comparison == "near_sale"], 131)
  testthat::expect_equal(all$hits2[all$comparison == "near_sale"], 250)
  all_bins <- dplyr::filter(b, comparison == "near_sale", dimension == "all", model == "FM-1.7.0")
  testthat::expect_equal(all_bins$n, c(83, 186, 54, 14, 6, 2, 0))
  testthat::expect_equal(all_bins$hits1, c(30, 75, 19, 4, 2, 1, 0))
  testthat::expect_equal(sum(all_bins$n * tidyr::replace_na(all_bins$mean_p1, 0))/345,
    all$mean_p1[all$comparison == "near_sale"])
  testthat::expect_false(anyNA(f$cutoff_utc))
  testthat::expect_false(anyDuplicated(f[c("comparison", "fixture_id", "model")]) > 0)
  for (dimension in c("issue", "source", "event_type")) {
    z <- s |> dplyr::filter(dimension == .env$dimension, comparison == "near_sale", model == "FM-1.7.0")
    testthat::expect_equal(sum(z$n), 345)
    testthat::expect_equal(sum(z$hits1), 131)
  }
  r <- jsonlite::fromJSON(file.path(out, "receipt.json"))
  testthat::expect_setequal(names(r$output_hashes), c("fixtures", "bins", "summary"))
  for (name in names(r$output_hashes)) testthat::expect_equal(
    digest::digest(file = file.path(out, paste0(name, ".csv")), algo = "sha256"), r$output_hashes[[name]])
  testthat::expect_equal(r$mode, "POSTHOC_DESCRIPTION_NO_CALIBRATION_FIT")
})
