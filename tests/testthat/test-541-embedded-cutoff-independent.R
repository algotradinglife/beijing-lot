# Independent public boundary checks: embedded cutoff is mandatory even without tickets.
testthat::test_that("embedded cutoff is bound at construction and cannot be silently retimed", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(c("26098:1","26098:2"),each=3),
    outcome=rep(c("W","D","L"),2),probability=c(.5,.4,.1,.8,.15,.05))
  settings <- beidan::parlay_settings(); settings$n_legs <- 2L
  pool <- IndependentRankedPool(p,cutoff,settings,c(2L,1L))
  constraints <- list(max_reuse=1L,max_overlap=0L)
  result <- beidan::parlay_evaluate_portfolio(pool,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
  testthat::expect_identical(result$cutoff,cutoff)
  testthat::expect_equal(sum(result$purchases$cost_cny),4)
  testthat::expect_false("cutoff" %in% names(formals(beidan::parlay_evaluate_portfolio)))
  testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,cutoff=cutoff,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)),"unused argument")
  for (bad_cutoff in list(NULL,list(),list(issue_id="26098",cutoff_utc=NA),
      list(issue_id="26099",cutoff_utc=cutoff$cutoff_utc),
      list(issue_id="26098",cutoff_utc=cutoff$cutoff_utc+3600))) {
    changed <- pool; changed["cutoff"] <- list(bad_cutoff)
    testthat::expect_error(beidan::parlay_evaluate_portfolio(changed,
      budget_cny=0,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)),"cutoff|Cutoff")
  }
  missing_binding <- pool; missing_binding$cutoff_hash <- NULL
  testthat::expect_error(beidan::parlay_evaluate_portfolio(missing_binding,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)),"cutoff|Cutoff")
  # Same fixture slate at a newly constructed epoch is a legitimate new decision.
  later <- cutoff; later$cutoff_utc <- cutoff$cutoff_utc+3600
  rebuilt <- IndependentRankedPool(p,later,settings,c(2L,1L))
  replay <- beidan::parlay_evaluate_portfolio(rebuilt,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
  testthat::expect_identical(replay$cutoff,later)
  testthat::expect_false(identical(result$receipt$cutoff_hash,replay$receipt$cutoff_hash))
  testthat::expect_identical(replay$purchases$ticket_id,result$purchases$ticket_id)
})

testthat::test_that("empty candidate pools retain and enforce their embedded decision context", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 12:00:00",tz="UTC"))
  p <- beidan:::match_typed_empty("probabilities")
  settings <- beidan::parlay_settings(); settings$n_legs <- 2L
  pool <- IndependentRankedPool(p,cutoff,settings,c(2L,1L))
  constraints <- list(max_reuse=1L,max_overlap=0L)
  empty <- beidan::parlay_evaluate_portfolio(pool,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L))
  testthat::expect_equal(nrow(empty$purchases),0L)
  testthat::expect_identical(empty$cutoff,cutoff)
  pool$cutoff$cutoff_utc <- pool$cutoff$cutoff_utc+1
  testthat::expect_error(beidan::parlay_evaluate_portfolio(pool,
    reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L)),"cutoff|Cutoff")
})
