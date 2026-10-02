# Independently specified #540 API/depth/cash/cutoff expectations.
testthat::test_that("one candidate obeys NULL caps, cash bounds and frozen quote identity", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  probabilities <- tibble::tibble(fixture_id=rep(c("26098:1","26098:2"),each=3),
    outcome=rep(c("W","D","L"),2),probability=c(.6,.3,.1,.8,.15,.05))
  settings <- beidan::parlay_settings();settings$n_legs <- 2L
  sp <- dplyr::mutate(dplyr::select(probabilities,fixture_id,outcome),
    quote_at=cutoff$cutoff_utc-lubridate::dminutes(1),sp_raw=2,
    source_url="https://example.test/beidan-reference")
  pool <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(probabilities,cutoff),
    cutoff,settings,c(2L,1L),n_candidates=1L,probabilities=probabilities,prematch_sp=sp)
  constraints <- list(max_reuse=1L,max_overlap=0L)
  x <- beidan::parlay_evaluate_portfolio(pool,constraints=constraints,improve=FALSE)
  testthat::expect_equal(nrow(x$tickets),2)
  testthat::expect_equal(sum(x$tickets$cost_cny),4)
  testthat::expect_true(is.na(x$metrics$unspent_cny[x$metrics$stage=="final"]))
  for (cap in c(4,100,1e20)) {
    capped <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=cap,
      constraints=constraints,improve=FALSE)
    testthat::expect_identical(capped$tickets$ticket_id,x$tickets$ticket_id)
  }
  shallow <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=3,
    budget_cny=3,constraints=constraints,improve=FALSE)
  testthat::expect_equal(nrow(shallow$tickets),1)
  testthat::expect_equal(shallow$metrics$unspent_cny[shallow$metrics$stage=="final"],1)
  too_small <- beidan::parlay_evaluate_portfolio(pool,budget_cny=3,
    constraints=constraints,improve=FALSE)
  testthat::expect_equal(nrow(too_small$tickets),0)
  for (cap in c(0,1)) {
    empty <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=cap,
      constraints=constraints,improve=TRUE)
    testthat::expect_equal(nrow(empty$tickets),0)
  }
  for (cap in c(NA_real_,NaN,Inf,-1)) {
    testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
      budget_cny=cap,constraints=constraints))
    testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
      group_budget_cny=cap,constraints=constraints))
  }
  for (cap in list(as.Date("2026-09-27"),matrix(2),as.difftime(2,units="days"))) {
    testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
      budget_cny=cap,constraints=constraints),"unclassed numeric scalar")
    testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
      group_budget_cny=cap,constraints=constraints),"unclassed numeric scalar")
  }
  altered <- pool; altered$prematch_sp$sp_raw[1] <- 12
  testthat::expect_error(beidan::parlay_evaluate_portfolio(altered,
    constraints=constraints),"SP|sp|hash|modified|match")
  ev <- beidan::parlay_evaluate_portfolio(pool,constraints=constraints,
    improve=FALSE,objective="ev")
  # 2CNY * 0.65 * 2 * 2 times each ticket probability, minus actual 4CNY cost.
  testthat::expect_equal(ev$metrics$ev_net_cny[ev$metrics$stage=="final"],
    sum(ev$tickets$probability)*5.2-4)
  testthat::expect_false(any(c("prior_purchases","probabilities","prematch_sp") %in%
    names(formals(beidan::parlay_evaluate_portfolio))))
})

testthat::test_that("3222221 uses legal-space cap rather than a hidden issue ceiling", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  probabilities <- tibble::tibble(fixture_id=rep(paste0("26098:",1:7),each=3),
    outcome=rep(c("W","D","L"),7),probability=rep(c(.6,.3,.1),7))
  settings <- beidan::parlay_settings();settings$issue_budget_cny <- 2
  pool <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(probabilities,cutoff),
    cutoff,settings,c(3L,2L,2L,2L,2L,2L,1L),n_candidates=1L,probabilities=probabilities)
  constraints <- list(max_reuse=1L,max_overlap=0L)
  full <- beidan::parlay_evaluate_portfolio(pool,constraints=constraints,improve=FALSE)
  testthat::expect_equal(nrow(full$tickets),96)
  testthat::expect_equal(sum(full$tickets$cost_cny),192)
  capped <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=256,
    constraints=constraints,improve=FALSE)
  testthat::expect_identical(capped$tickets$ticket_id,full$tickets$ticket_id)
  testthat::expect_equal(capped$group_summary$unspent_cny,0)
  testthat::expect_equal(full$group_summary$unspent_cny,0)
  partial <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=161,
    constraints=constraints,improve=FALSE)
  testthat::expect_equal(nrow(partial$tickets),80)
  testthat::expect_equal(sum(partial$tickets$cost_cny),160)
  testthat::expect_equal(partial$group_summary$unspent_cny,1)
  none <- beidan::parlay_evaluate_portfolio(pool,budget_cny=0,
    constraints=constraints,improve=TRUE)
  testthat::expect_equal(nrow(none$tickets),0)
  testthat::expect_equal(none$metrics$unspent_cny,rep(0,2))
})
