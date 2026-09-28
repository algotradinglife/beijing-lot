#' Synthetic two-ticket result through the production construction path
#' @param budget Per-group CNY budget; zero returns an unfunded result.
#' @return Frozen final result, with one-leg groups on separate fixtures.
LossDiagnosticFixture <- function(budget = 2) {
  cutoff <- list(issue_id = "00001", cutoff_utc = lubridate::ymd_hms("2026-09-01 00:00:00", tz = "UTC"))
  p <- tibble::tibble(fixture_id = rep(c("a", "b"), each = 3),
    outcome = rep(c("W", "D", "L"), 2), probability = c(.6,.3,.1,.5,.3,.2))
  sp <- dplyr::mutate(dplyr::select(p, fixture_id, outcome),
    quote_at = cutoff$cutoff_utc - 60, sp_raw = rep(c(2,4,3),2), source_url = "fixture://loss")
  settings <- parlay_settings(); settings$n_legs <- 1L
  pool <- parlay_construct_role_groups(parlay_role_scores(p,cutoff),cutoff,
    settings,pattern=1L,n_candidates=2L,probabilities=p,prematch_sp=sp)
  return(parlay_evaluate_portfolio(pool,group_budget_cny=budget,
    constraints=list(max_reuse=1L,max_overlap=0L),improve=FALSE)$final)
}

test_that("actual stakes and untouched tickets define exposure", {
  f <- LossDiagnosticFixture()
  f$plan$purchases$stake_cny <- f$funded$purchases$stake_cny <- f$history$purchases$stake_cny <- c(2,4)
  x <- beidan:::.ParlayLossExposure(f)
  expect_s3_class(x,"tbl_df")
  expect_equal(x$knockout_cny,c(0,2,2,0,4,4))
  expect_equal(x$knockout_fraction,c(0,2,2,0,4,4)/6)
  expect_equal(x$surviving_cny,6-c(0,2,2,0,4,4))
  expect_equal(x$plan_stake_cny,rep(6,6))
  # A third admitted but unpurchased fixture has zero knockout for all outcomes.
  f$probabilities <- dplyr::bind_rows(f$probabilities,
    tibble::tibble(fixture_id="c",outcome=c("W","D","L"),probability=c(.4,.3,.3)))
  y <- beidan:::.ParlayLossExposure(f)
  expect_equal(y$knockout_cny[y$fixture_id=="c"],rep(0,3))
  expect_equal(y$surviving_cny[y$fixture_id=="c"],rep(6,3))
})

test_that("empty exposure retains exact schema", {
  x <- beidan:::.ParlayLossExposure(LossDiagnosticFixture(0))
  expect_identical(x,beidan:::.ParlayLossExposureEmpty())
  expect_identical(vapply(x,typeof,character(1)),c(fixture_id="character",outcome="character",
    plan_stake_cny="double",knockout_cny="double",knockout_fraction="double",surviving_cny="double"))
})

test_that("bad ledger keys, stakes and physical legs fail", {
  f <- LossDiagnosticFixture()
  bad <- f; bad$plan$purchases$ticket_id[1] <- "bad"
  expect_error(beidan:::.ParlayLossExposure(bad),"ledger")
  bad <- f; bad$plan$ticket_legs <- dplyr::bind_rows(bad$plan$ticket_legs,bad$plan$ticket_legs[1,])
  expect_error(beidan:::.ParlayLossExposure(bad),"duplicate|unique")
  bad <- f; bad$plan$ticket_legs$outcome[1] <- "D"
  expect_error(beidan:::.ParlayLossExposure(bad),"physical")
  bad <- f; bad$plan$ticket_legs <- bad$plan$ticket_legs[-1,]
  expect_error(beidan:::.ParlayLossExposure(bad),"no frozen legs")
  bad <- f; bad$plan$purchases$stake_cny <- bad$funded$purchases$stake_cny <- bad$history$purchases$stake_cny <- c(3,2)
  expect_error(beidan:::.ParlayLossExposure(bad),"stake")
  expect_error(beidan:::.ParlayLossExposure(f$plan),"missing")
})

test_that("market comparison preserves raw SP ranking and model discrepancy", {
  f <- LossDiagnosticFixture()
  x <- beidan:::.ParlayLossMarketComparison(f$probabilities,f$prematch_sp,f$cutoff)
  expect_equal(x$model_probability,f$probabilities$probability)
  expect_identical(x$model_rank,rep(1:3,2))
  expect_identical(x$sp_rank,rep(c(1L,3L,2L),2))
  expect_true(all(x$disagreement))
  expect_equal(x$sp_raw,rep(c(2,4,3),2))
  expect_identical(x,beidan:::.ParlayLossMarketComparison(f$probabilities[6:1,],f$prematch_sp[6:1,],f$cutoff))
  sp <- f$prematch_sp; sp$sp_raw <- rep(c(2,3,12),2)
  y <- beidan:::.ParlayLossMarketComparison(f$probabilities,sp,f$cutoff)
  expect_equal(y$sp_raw,sp$sp_raw)
  expect_false(any(y$disagreement))
})

test_that("cutoff selects last prior quote and excludes future quotes", {
  f <- LossDiagnosticFixture()
  baseline <- beidan:::.ParlayLossMarketComparison(f$probabilities,f$prematch_sp,f$cutoff)
  future <- f$prematch_sp; future$quote_at <- f$cutoff$cutoff_utc; future$sp_raw <- 99
  later <- future; later$quote_at <- later$quote_at+3600; later$sp_raw <- 100
  expect_identical(baseline,beidan:::.ParlayLossMarketComparison(f$probabilities,
    dplyr::bind_rows(f$prematch_sp,future,later),f$cutoff))
  newer <- f$prematch_sp; newer$quote_at <- newer$quote_at+30; newer$sp_raw <- rep(c(3,2,4),2)
  x <- beidan:::.ParlayLossMarketComparison(f$probabilities,dplyr::bind_rows(f$prematch_sp,newer),f$cutoff)
  expect_equal(x$sp_raw,newer$sp_raw)
  conflict <- newer; conflict$sp_raw <- 7
  expect_error(beidan:::.ParlayLossMarketComparison(f$probabilities,
    dplyr::bind_rows(newer,conflict),f$cutoff),"conflict")
  expect_error(beidan:::.ParlayLossMarketComparison(f$probabilities,f$prematch_sp,NULL))
})

test_that("missing SP, deterministic ties and empty comparison are explicit", {
  f <- LossDiagnosticFixture()
  x <- beidan:::.ParlayLossMarketComparison(f$probabilities,f$prematch_sp[-1,],f$cutoff)
  expect_true(is.na(x$sp_raw[1])); expect_true(is.na(x$sp_rank[1]))
  expect_true(all(is.na(x$disagreement[1:3])))
  empty <- match_typed_empty("prematch_sp")
  y <- beidan:::.ParlayLossMarketComparison(f$probabilities,empty,f$cutoff)
  expect_true(all(is.na(y$sp_raw))); expect_true(all(is.na(y$disagreement)))
  p <- f$probabilities; p$probability <- 1/3
  sp <- f$prematch_sp; sp$sp_raw <- 3
  z <- beidan:::.ParlayLossMarketComparison(p,sp,f$cutoff)
  expect_identical(z$model_rank,rep(1:3,2)); expect_identical(z$sp_rank,rep(1:3,2))
  expect_false(any(z$disagreement))
  expect_identical(beidan:::.ParlayLossMarketComparison(p[0,],empty,f$cutoff),
    beidan:::.ParlayLossMarketComparisonEmpty())
  expect_error(beidan:::.ParlayLossMarketComparison(dplyr::bind_rows(p,p[1,]),sp,f$cutoff),"duplicate|unique")
})
