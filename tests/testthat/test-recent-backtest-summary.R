source(testthat::test_path("..", "..", "r", "recent_backtest_summary.R"))

# Synthetic two-fixture two-ticket plan, built by public production APIs.
RecentSummaryFixture <- function() {
  cutoff <- list(issue_id="00001",cutoff_utc=as.POSIXct("2026-09-01",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(c("a","b"),each=3),outcome=rep(c("W","D","L"),2),probability=c(.5,.4,.1,.6,.3,.1))
  sp <- tibble::tibble(fixture_id=p$fixture_id,outcome=p$outcome,quote_at=cutoff$cutoff_utc-60,
    sp_raw=2,source_url="fixture://summary")
  settings <- beidan::parlay_settings(reset=TRUE);settings$n_legs <- 2L
  withr::defer(beidan::parlay_settings(reset=TRUE))
  matches <- tibble::tibble(fixture_id=c("a","b"),win=c(.5,.6),draw=c(.4,.3),lose=c(.1,.1))
  ranked <- beidan::rank_outcome_selections(beidan::prepare_outcome_selections(matches),cutoff)
  pool <- beidan::parlay_construct_role_groups(ranked,settings,pattern=c(2L,1L),
    max_candidates=1L,prematch_sp=sp)
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
  exposure <- x$exposures |>
    dplyr::mutate(outcome=factor(outcome,levels=c("W","D","L"))) |>
    dplyr::arrange(fixture_id,outcome)
  testthat::expect_equal(exposure$knockout_cny,c(2,2,4,0,4,4))
  testthat::expect_equal(exposure$surviving_cny,c(2,2,0,4,0,0))
  testthat::expect_equal(exposure$knockout_fraction,c(.5,.5,1,0,1,1))
  testthat::expect_equal(exposure$plan_stake_cny,rep(4,6))
  testthat::expect_s3_class(x$exposures,"tbl_df")
  testthat::expect_equal(nrow(x$exposures),6L)
  bad <- e;bad$results$funded$purchases$probability[1] <- .99
  testthat::expect_error(RecentBacktestSummary(bad,s,e$cutoff$cutoff_utc+120),"binding|hash|receipt")
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
