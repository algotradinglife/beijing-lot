source(testthat::test_path("..", "..", "r", "recent_frozen_backtest.R"))

testthat::test_that("old frozen replay keeps chronology and reconciles canceled winning legs", {
  root <- normalizePath(testthat::test_path("..", ".."))
  p <- file.path(root, "inputs/26098_walkthrough/print")
  paths <- file.path(p, c("26098-20260926-195204.rds", "26098-195204-3333222-256.rds", "settlement-20260928-192221.rds"))
  original <- readRDS(paths[1])
  before <- vapply(paths, function(p) digest::digest(file=p,algo="sha256"), character(1))
  x <- recent_frozen_backtest(paths[1], paths[2], paths[3], original$result$cutoff)
  testthat::expect_identical(unname(x$receipt$source_hashes), unname(before))
  testthat::expect_identical(vapply(paths, function(p) digest::digest(file=p,algo="sha256"), character(1)), before)
  testthat::expect_equal(x$summary$stake_cny, c(768,1024,1024,1024,1024,768))
  testthat::expect_true(all(x$summary$pending_stake_cny == 0))
  testthat::expect_equal(x$summary$net_cny, x$summary$payout_cny-x$summary$stake_cny)
  w <- dplyr::filter(x$winning_tickets, scenario=="published_3222221")
  testthat::expect_equal(nrow(w),2L)
  testthat::expect_equal(dplyr::n_distinct(w$group_id),1L)
  legs <- dplyr::filter(x$winning_legs, scenario=="published_3222221")
  testthat::expect_equal(sum(legs$actual_outcome=="ALL"),2L)
  independent <- legs |> dplyr::group_by(ticket_id) |>
    dplyr::summarise(payout=2*.65*prod(settled_sp), .groups="drop")
  testthat::expect_equal(sort(w$payout_cny),sort(independent$payout), tolerance=1e-8)
  for (plan in x$plans) testthat::expect_identical(plan$probabilities,original$result$probabilities)
  testthat::expect_false(x$source_eligibility$decision_eligible[x$source_eligibility$signal=="prematch_sp"])
  for (plan in x$plans[grepl("^fixed_",names(x$plans))]) {
    testthat::expect_true(all(is.na(plan$built$valued$ev_net_est)))
  }
  wrong <- original$result$cutoff;wrong$cutoff_utc <- wrong$cutoff_utc+1
  testthat::expect_error(recent_frozen_backtest(paths[1],paths[2],paths[3],wrong),"cutoff")
  testthat::expect_error(recent_frozen_backtest(paths[1],paths[2],paths[3],original$result$cutoff,patterns="4444444"))
  altered <- original; altered$market_captures$observed_at[1] <- wrong$cutoff_utc
  tmp <- tempfile(fileext=".rds");saveRDS(altered,tmp)
  testthat::expect_error(recent_frozen_backtest(tmp,paths[2],paths[3],original$result$cutoff),"source hash")
  altered_alt <- readRDS(paths[2]); altered_alt$source_sha256 <- digest::digest(file=tmp,algo="sha256")
  tmp_alt <- tempfile(fileext=".rds");saveRDS(altered_alt,tmp_alt)
  testthat::expect_error(recent_frozen_backtest(tmp,tmp_alt,paths[3],original$result$cutoff),"post-cutoff")
  testthat::expect_error(recent_frozen_backtest(tempfile(),paths[2],paths[3],original$result$cutoff))
})
