# Independently specified #540 API/depth/cash/cutoff expectations.
testthat::test_that("one candidate obeys NULL caps, cash bounds and frozen quote identity", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  probabilities <- tibble::tibble(fixture_id=rep(c("26098:1","26098:2"),each=3),
    outcome=rep(c("W","D","L"),2),probability=c(.5,.4,.1,.8,.15,.05))
  settings <- beidan::parlay_settings();settings$n_legs <- 2L
  sp <- dplyr::mutate(dplyr::select(probabilities,fixture_id,outcome),
    quote_at=cutoff$cutoff_utc-lubridate::dminutes(1),sp_raw=2,
    source_url="https://example.test/beidan-reference")
  pool <- IndependentRankedPool(probabilities,cutoff,settings,c(2L,1L),sp=sp)
  constraints <- list(max_reuse=1L,max_overlap=0L)
  x <- beidan::parlay_evaluate_portfolio(pool,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
  testthat::expect_equal(nrow(x$purchases),2)
  testthat::expect_equal(sum(x$purchases$cost_cny),4)
  testthat::expect_true(is.na(x$summary$unspent_cny))
  for (cap in c(4,100,1e20)) {
    capped <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=cap,
      reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
    testthat::expect_identical(capped$purchases$ticket_id,x$purchases$ticket_id)
  }
  shallow <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=3,
    budget_cny=3,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
  testthat::expect_equal(nrow(shallow$purchases),1)
  testthat::expect_equal(shallow$summary$unspent_cny,1)
  too_small <- beidan::parlay_evaluate_portfolio(pool,budget_cny=1,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
  testthat::expect_equal(nrow(too_small$purchases),0)
  for (cap in c(0,1)) {
    empty <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=cap,
      reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=TRUE)
    testthat::expect_equal(nrow(empty$purchases),0)
  }
  for (cap in c(NA_real_,NaN,Inf,-1)) {
    testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
      budget_cny=cap,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)))
    testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
      group_budget_cny=cap,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)))
  }
  for (cap in list(as.Date("2026-09-27"),matrix(2),as.difftime(2,units="days"))) {
    testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
      budget_cny=cap,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)),NULL)
    testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
      group_budget_cny=cap,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)),NULL)
  }
  altered <- pool; altered$prematch_sp$sp_raw[1] <- 12
  testthat::expect_error(beidan::parlay_evaluate_portfolio(altered,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)),"SP|sp|hash|modified|match")
  ev <- beidan::parlay_evaluate_portfolio(pool,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),
    improve=FALSE)
  # 2CNY * 0.65 * 2 * 2 times each ticket probability, minus actual 4CNY cost.
  testthat::expect_equal(ev$summary$ev_net_cny,
    sum(ev$purchases$probability)*5.2-4)
  testthat::expect_false(any(c("prior_purchases","probabilities","prematch_sp") %in%
    names(formals(beidan::parlay_evaluate_portfolio))))
})

testthat::test_that("3222221 uses legal-space cap rather than a hidden issue ceiling", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  probabilities <- tibble::tibble(fixture_id=rep(paste0("26098:",1:7),each=3),
    outcome=rep(c("W","D","L"),7),probability=c(.4,.3,.3,rep(c(.5,.4,.1),5),.8,.1,.1))
  settings <- beidan::parlay_settings();settings$issue_budget_cny <- 2
  pool <- IndependentRankedPool(probabilities,cutoff,settings,c(3L,2L,2L,2L,2L,2L,1L))
  constraints <- list(max_reuse=1L,max_overlap=0L)
  full <- beidan::parlay_evaluate_portfolio(pool,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
  testthat::expect_equal(nrow(full$purchases),96)
  testthat::expect_equal(sum(full$purchases$cost_cny),192)
  capped <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=256,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
  testthat::expect_identical(capped$purchases$ticket_id,full$purchases$ticket_id)
  testthat::expect_true(is.na(capped$summary$unspent_cny))
  testthat::expect_true(is.na(full$summary$unspent_cny))
  partial <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=161,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
  testthat::expect_equal(nrow(partial$purchases),80)
  testthat::expect_equal(sum(partial$purchases$cost_cny),160)
  testthat::expect_equal(sum(partial$purchases$cost_cny),160)
  none <- beidan::parlay_evaluate_portfolio(pool,budget_cny=0,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=TRUE)
  testthat::expect_equal(nrow(none$purchases),0)
  testthat::expect_equal(none$summary$unspent_cny,0)
})
