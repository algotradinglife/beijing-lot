# Independent public boundary checks: embedded cutoff is mandatory even without tickets.
testthat::test_that("embedded cutoff is bound at construction and cannot be silently retimed", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(c("26098:1","26098:2"),each=3),
    outcome=rep(c("W","D","L"),2),probability=c(.6,.3,.1,.8,.15,.05))
  settings <- beidan::parlay_settings(); settings$n_legs <- 2L
  pool <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),
    cutoff,settings,c(2L,1L),n_candidates=1L,probabilities=p)
  constraints <- list(max_reuse=1L,max_overlap=0L)
  result <- beidan::parlay_evaluate_portfolio(pool,constraints=constraints,improve=FALSE)
  testthat::expect_identical(result$cutoff,cutoff)
  testthat::expect_equal(sum(result$tickets$cost_cny),4)
  testthat::expect_false("cutoff" %in% names(formals(beidan::parlay_evaluate_portfolio)))
  testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,cutoff=cutoff,
    constraints=constraints),"unused argument")
  for (bad_cutoff in list(NULL,list(),list(issue_id="26098",cutoff_utc=NA),
      list(issue_id="26099",cutoff_utc=cutoff$cutoff_utc),
      list(issue_id="26098",cutoff_utc=cutoff$cutoff_utc+3600))) {
    changed <- pool; changed["cutoff"] <- list(bad_cutoff)
    testthat::expect_error(beidan::parlay_evaluate_portfolio(changed,
      budget_cny=0,constraints=constraints),"cutoff|Cutoff")
  }
  missing_binding <- pool; missing_binding$cutoff_hash <- NULL
  testthat::expect_error(beidan::parlay_evaluate_portfolio(missing_binding,
    constraints=constraints),"cutoff|Cutoff")
  # Same fixture slate at a newly constructed epoch is a legitimate new decision.
  later <- cutoff; later$cutoff_utc <- cutoff$cutoff_utc+3600
  rebuilt <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,later),
    later,settings,c(2L,1L),n_candidates=1L,probabilities=p)
  replay <- beidan::parlay_evaluate_portfolio(rebuilt,constraints=constraints,improve=FALSE)
  testthat::expect_identical(replay$cutoff,later)
  testthat::expect_false(identical(result$receipt$cutoff_hash,replay$receipt$cutoff_hash))
  testthat::expect_identical(replay$tickets$ticket_id,result$tickets$ticket_id)
})

testthat::test_that("empty candidate pools retain and enforce their embedded decision context", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  p <- beidan:::match_typed_empty("probabilities")
  settings <- beidan::parlay_settings(); settings$n_legs <- 2L
  pool <- beidan::parlay_construct_role_groups(beidan::parlay_role_scores(p,cutoff),
    cutoff,settings,c(2L,1L),n_candidates=1L,probabilities=p)
  constraints <- list(max_reuse=1L,max_overlap=0L)
  empty <- beidan::parlay_evaluate_portfolio(pool,constraints=constraints)
  testthat::expect_equal(nrow(empty$tickets),0L)
  testthat::expect_identical(empty$cutoff,cutoff)
  pool$cutoff$cutoff_utc <- pool$cutoff$cutoff_utc+1
  testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
    constraints=constraints),"cutoff|Cutoff")
})
