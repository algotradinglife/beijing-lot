source(testthat::test_path("..", "..", "r", "recent_backtest_summary.R"))

# Synthetic two-fixture two-ticket plan, built by public production APIs.
RecentSummaryFixture <- function() {
  cutoff <- list(issue_id="00001",cutoff_utc=as.POSIXct("2026-09-01",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(c("a","b"),each=3),outcome=rep(c("W","D","L"),2),probability=rep(c(.6,.3,.1),2))
  sp <- tibble::tibble(fixture_id=p$fixture_id,outcome=p$outcome,quote_at=cutoff$cutoff_utc-60,
    sp_raw=2,source_url="fixture://summary")
  settings <- beidan::parlay_settings();settings$n_legs <- 2L
  pool <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),cutoff,
    settings,pattern=c(2L,1L),n_candidates=1L,probabilities=p,prematch_sp=sp)
  scenarios <- tibble::tibble(scenario_id=c("funded","cash"),pattern="p",group_budget_cny=4,
    budget_cny=c(4,0),max_reuse=1L,max_overlap=1L)
  e <- beidan::parlay_explore_portfolios(list(p=pool),scenarios)
  list(results=e$results,metadata=tibble::tibble(scenario_id=c("funded","cash")),cutoff=cutoff)
}

testthat::test_that("group model math, ALL multiple payouts, cash and pending reconcile", {
  e <- RecentSummaryFixture()
  s <- tibble::tibble(issue_id="00001",fixture_id=c("a","b"),outcome=c("ALL","W"),settled_sp=c(1,2),
    label_available_at=e$cutoff$cutoff_utc+60,status=c("all_options_one","settled"),source_url="fixture://summary")
  x <- RecentBacktestSummary(e,s,e$cutoff$cutoff_utc+120)
  testthat::expect_equal(x$summary$actual_cost_cny,c(4,0))
  testthat::expect_equal(x$summary$known_payout_cny,c(5.2,0))
  testthat::expect_equal(x$summary$final_net_cny,c(1.2,0))
  testthat::expect_equal(x$summary$n_winning_tickets,c(2L,0L))
  testthat::expect_equal(x$groups$q,.54)
  testthat::expect_equal(x$groups$expected_gross_cny,.54*2*.65*4)
  testthat::expect_equal(x$groups$conditional_gross_cny,2*.65*4)
  testthat::expect_equal(x$groups$required_break_even_gross_cny,4/.54)
  testthat::expect_equal(x$summary$max_knockout_fraction,c(1,0))
  testthat::expect_equal(nrow(x$groups),1L)
  pending <- RecentBacktestSummary(e,s,e$cutoff$cutoff_utc+30)
  testthat::expect_equal(pending$summary$pending_stake_cny,c(4,0))
  testthat::expect_equal(pending$summary$final_net_cny,c(NA_real_,0))
  testthat::expect_true(is.na(pending$groups$final_net_cny))
  testthat::expect_identical(x$groups$q,pending$groups$q)
  testthat::expect_identical(x$groups$expected_gross_cny,pending$groups$expected_gross_cny)
  testthat::expect_false(x$receipt$settlement_used_for_selection)
  bad <- e;bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc+1
  testthat::expect_error(RecentBacktestSummary(bad,s,e$cutoff$cutoff_utc+120),"cutoff")
  bad <- e;bad$metadata$scenario_id[1] <- "unknown"
  testthat::expect_error(RecentBacktestSummary(bad,s,e$cutoff$cutoff_utc+120),"metadata")
  testthat::expect_error(RecentBacktestSummary(e,s,e$cutoff$cutoff_utc),"follow")
})
