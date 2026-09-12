source(file.path("..", "..", "r", "fundamentals_equity_curves.R"))
source(file.path("..", "..", "r", "market_conditional_summary.R"))
source(file.path("..", "..", "r", "n7_sleeve_summary.R"))
source(file.path("..", "..", "r", "n7_joint_report.R"))

testthat::test_that("joint report separates cash, matched budget and simulation diagnostics", {
  issues <- c("001", "002", "003", "004")
  rows <- tidyr::expand_grid(issue = issues,
    arm = c("MONOLITHIC_PROB512", "MONOLITHIC_COVERAGE512", "QUALITY_PROB", "JOINT_UNION", "JOINT_FULL"), seed = 1L) |>
    dplyr::mutate(stake = 1024, gross = ifelse(issue == "003", 4000, 0), net = gross - stake,
      groups = 512, hits = as.integer(gross > 0), status = "COMPLETE", decision_year = "2010",
      solver_status = "Optimal", train_coverage = .6, eval_coverage = .5,
      train_path_drawdown = 2000, eval_path_drawdown = 2200)
  no_bet <- rows$arm == "JOINT_FULL" & rows$issue == "001"
  rows[no_bet, c("stake", "gross", "net", "groups", "hits")] <- 0
  rows$status[no_bet] <- "NO_BET"; rows$solver_status[no_bet] <- "Infeasible"
  report <- n7_joint_report(rows, issues, 100000, 1024, 3072)
  g <- report$grid[report$grid$model == "JOINT_FULL", ]
  testthat::expect_equal(g$stake, 3072)
  testthat::expect_equal(g$roi, 100 * (4000 - 3072) / 3072)
  testthat::expect_equal(g$no_bet_issues, 1)
  paired <- report$paired |> dplyr::filter(arm == "JOINT_FULL", control == "QUALITY_PROB")
  testthat::expect_equal(paired$matched_issues, 3)
  testthat::expect_equal(paired$matched_net_difference, 0)
  testthat::expect_equal(report$numerical$optimism_pp, rep(10, 5), tolerance = 1e-10)
  testthat::expect_equal(nrow(report$segments), 10)
  testthat::expect_true(all(report$grid$max_drawdown_percent >= 0))
  bad <- rows; bad$net[1] <- NA_real_
  testthat::expect_error(n7_joint_report(bad, issues, 100000, 1024, 3072))
})

testthat::test_that("bootstrap resamples issue clusters and reports unavailable matches", {
  p <- tidyr::expand_grid(issue = c("01", "02", "03"), seed = 1:3, arm = c("A", "B")) |>
    dplyr::mutate(stake = 1024, net = ifelse(arm == "A", 102.4, 0))
  x <- n7_joint_bootstrap(p, "A", "B", 1024, 50, 42)
  testthat::expect_equal(x$matched_issues, 3)
  testthat::expect_equal(x$delta_roi_pp, 10)
  testthat::expect_equal(x$lower95_pp, 10)
  testthat::expect_equal(x$upper95_pp, 10)
  testthat::expect_identical(x, n7_joint_bootstrap(p, "A", "B", 1024, 50, 42))
  p$stake[p$arm == "A"] <- 0
  empty <- n7_joint_bootstrap(p, "A", "B", 1024, 50, 42)
  testthat::expect_equal(empty$status, "INSUFFICIENT_MATCHED_ISSUES")
  testthat::expect_true(is.na(empty$delta_roi_pp))
  testthat::expect_error(n7_joint_bootstrap(p[-1, ], "A", "B", 1024, 50, 42))
})
