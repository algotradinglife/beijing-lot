# PI-owned numerical acceptance. Separate from implementation-owned helper tests.
testthat::test_that("role scores equal the approved arithmetic, not entropy", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 11:52:04",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep(c("26098:A","26098:B","26098:C"),each=3),
    outcome=rep(c("W","D","L"),3),probability=c(.90,.07,.03,.49,.48,.03,.35,.34,.31))
  scores <- beidan::parlay_role_scores(p,cutoff)
  testthat::expect_s3_class(scores,"tbl_df")
  testthat::expect_equal(nrow(scores),9L)
  for (role in 1:3) {
    rows <- dplyr::filter(scores,.data$role==!!role) |> dplyr::arrange(fixture_id)
    expected <- switch(role,c(.9,.49,.35),c(.97,.97,.69),c(.03,.03,.31))
    mass <- switch(role,c(.9,.49,.35),c(.97,.97,.69),rep(1,3))
    testthat::expect_equal(rows$score,expected)
    testthat::expect_equal(rows$retained_probability,mass)
    testthat::expect_equal(lengths(rows$allowed_outcomes),rep(role,3))
  }
  triples <- dplyr::filter(scores,role==3L) |> dplyr::arrange(rank)
  testthat::expect_identical(triples$fixture_id[1],"26098:C")
  shuffled <- beidan::parlay_role_scores(p[c(9,1,5,3,7,2,8,4,6),],cutoff)
  testthat::expect_equal(lapply(dplyr::arrange(scores,role,fixture_id),identity),
    lapply(dplyr::arrange(shuffled,role,fixture_id),identity))
})

testthat::test_that("equal outcomes follow W D L rather than alphabetic order", {
  cutoff <- list(issue_id="26098",cutoff_utc=lubridate::ymd_hms("2026-09-26 11:52:04",tz="UTC"))
  p <- tibble::tibble(fixture_id=rep("26098:1",3),outcome=c("L","D","W"),probability=rep(1/3,3))
  scores <- beidan::parlay_role_scores(p,cutoff)
  testthat::expect_identical(scores$allowed_outcomes[[which(scores$role==1L)]],"W")
  testthat::expect_identical(scores$allowed_outcomes[[which(scores$role==2L)]],c("W","D"))
})

testthat::test_that("current ranked rounds are role ordered and inputs remain immutable", {
 cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
 p <- tibble::tibble(fixture_id=rep(paste0("26098:",1:8),each=3),outcome=rep(c("W","D","L"),8),probability=c(rep(c(.4,.3,.3),4),rep(c(.5,.4,.1),4)))
 settings <- beidan::parlay_settings(); settings$n_legs <- 2L
 pool <- IndependentRankedPool(p,cutoff,settings,c(3L,2L),4L)
 before <- rlang::hash(pool)
 testthat::expect_equal(pool$role_legs$base_role,rep(c(3L,2L),4))
 testthat::expect_true(all(lengths(pool$role_legs$allowed_outcomes)==pool$role_legs$n_outcomes))
 baseline <- IndependentEvaluate(pool,group_budget_cny=12)
 improved <- beidan::parlay_evaluate_portfolio(pool,group_budget_cny=12,reuse_policy=list(max_reuse=4L),overlap_policy=list(max_overlap=3L),improve=TRUE)
 testthat::expect_gte(improved$summary$actual_coverage,baseline$summary$actual_coverage-1e-12)
 testthat::expect_identical(rlang::hash(pool),before)
 testthat::expect_equal(baseline$summary$spent_cny,sum(baseline$purchases$cost_cny))
})
