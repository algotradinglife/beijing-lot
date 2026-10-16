testthat::test_that("full alpha freeze and paired comparisons reconcile", {
  root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
  source <- file.path(root, "results/fm18-three-issues-20261017")
  out <- tempfile("fm18-evaluate-"); dir.create(out)
  for (name in c("forecasts.rds", "manifest.json", "replay.json")) {
    testthat::expect_true(file.copy(file.path(source, name), file.path(out, name)))
  }
  log <- tempfile()
  status <- system2("/opt/R/4.6.1/bin/Rscript", shQuote(c(file.path(root, "r/fm18_three_issue_evaluate.R"), root, out)),
    env = paste0("R_LIBS=", shQuote(paste(.libPaths(), collapse = ":"))), stdout = log, stderr = log)
  testthat::expect_equal(status, 0L, info = paste(readLines(log), collapse = "\n"))
  m <- readr::read_csv(file.path(out, "metrics.csv"), show_col_types = FALSE)
  scores <- readr::read_csv(file.path(out, "scores.csv"), show_col_types = FALSE)
  changes <- readr::read_csv(file.path(out, "changes.csv"), show_col_types = FALSE)
  all <- dplyr::filter(m, dimension == "all")
  testthat::expect_true(all(all$n[all$comparison == "near_sale"] == 345))
  testthat::expect_true(all(all$n[all$comparison == "same_cutoff"] == 214))
  fm <- dplyr::filter(all, model == "FM-1.7.0", comparison == "near_sale")
  testthat::expect_equal(fm$hits1, 131); testthat::expect_equal(fm$hits2, 250)
  bd <- dplyr::filter(all, model == "BEIDAN_LATER")
  testthat::expect_equal(bd$hits1, 130); testthat::expect_equal(bd$hits2, 244)
  alpha <- dplyr::filter(all, model == "FM-1.8.0-alpha.1", comparison == "near_sale")
  testthat::expect_equal(alpha$hits1 - fm$hits1, sum(changes$saved_top1) - sum(changes$lost_top1))
  testthat::expect_equal(alpha$hits2 - fm$hits2, sum(changes$saved_top2) - sum(changes$lost_top2))
  testthat::expect_equal(nrow(changes), 345)
  testthat::expect_false(anyDuplicated(scores[c("comparison", "model", "fixture_id")]) > 0)
  for (dim in c("issue", "event_type", "source", "trigger", "draw_type")) {
    z <- dplyr::filter(m, dimension == dim, model == "FM-1.8.0-alpha.1", comparison == "near_sale")
    testthat::expect_equal(sum(z$n), 345)
    testthat::expect_equal(sum(z$hits1), alpha$hits1)
    testthat::expect_equal(sum(z$hits2), alpha$hits2)
    testthat::expect_equal(sum(z$brier*z$n)/345, alpha$brier, tolerance = 1e-12)
  }
  frozen <- readRDS(file.path(out, "forecasts.rds"))
  testthat::expect_equal(length(frozen$entries), 346)
  testthat::expect_equal(nrow(frozen$audit), 346)
  testthat::expect_equal(sum(frozen$audit$triggered), 331)
  testthat::expect_false(anyNA(frozen$audit$cutoff_utc))
  for (entry in frozen$entries) {
    testthat::expect_equal(sum(entry$grid$probability), 1, tolerance = 1e-12)
    testthat::expect_equal(sum(entry$probabilities$probability), 1, tolerance = 1e-12)
    testthat::expect_equal(entry$receipt$model_id, "FM-1.8.0-alpha.1")
  }
  r <- jsonlite::fromJSON(file.path(out, "evaluation.json"))
  testthat::expect_false(r$native_lambda_experiments_included)
  for (name in names(r$output_hashes)) testthat::expect_equal(
    digest::digest(file = file.path(out, paste0(name, ".csv")), algo = "sha256"), r$output_hashes[[name]])
  # Independent temporary copy: altered frozen model cannot reach scoring.
  altered <- frozen; altered$audit$triggered[1] <- !altered$audit$triggered[1]
  saveRDS(altered, file.path(out, "forecasts.rds"))
  failed_out <- file.path(out, "metrics.csv"); previous <- digest::digest(file = failed_out, algo = "sha256")
  status <- system2("/opt/R/4.6.1/bin/Rscript", shQuote(c(file.path(root, "r/fm18_three_issue_evaluate.R"), root, out)),
    env = paste0("R_LIBS=", shQuote(paste(.libPaths(), collapse = ":"))), stdout = log, stderr = log)
  testthat::expect_true(status != 0L)
  testthat::expect_equal(digest::digest(file = failed_out, algo = "sha256"), previous)
})
