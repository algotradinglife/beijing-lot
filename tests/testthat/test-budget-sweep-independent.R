testthat::test_that("ranked candidate generation is budget independent and purchased reuse is enforced", {
 cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
 p <- tibble::tibble(fixture_id=rep(sprintf("26098:%02d",1:18),each=3),outcome=rep(c("W","D","L"),18),probability=c(rep(c(.4,.3,.3),3),rep(c(.5,.4,.1),12),rep(c(.8,.1,.1),3)))
 settings <- beidan::parlay_settings();settings$n_legs <- 7L;settings$issue_budget_cny <- 128
 x <- IndependentRankedPool(p,cutoff,settings,c(3L,2L,2L,2L,2L,2L,1L),8L)
 settings$issue_budget_cny <- 4096
 y <- IndependentRankedPool(p,cutoff,settings,c(3L,2L,2L,2L,2L,2L,1L),8L)
 testthat::expect_equal(x$role_legs,y$role_legs)
 testthat::expect_equal(x$groups,y$groups)
 testthat::expect_gt(nrow(x$groups),1L)
 before <- rlang::hash(x)
 bad <- x;bad$probabilities$probability[1] <- .9
 testthat::expect_error(IndependentEvaluate(bad),"probabilit|binding|hash")
 result <- beidan::parlay_evaluate_portfolio(x,group_budget_cny=128,budget_cny=1024,reuse_policy=list(max_reuse=1L),overlap_policy=list(max_overlap=0L),improve=FALSE)
 legs <- result$plan$group_legs
 # Genuine triple masks are intentionally exempt from reuse quotas.
 double_ids <- x$role_legs$fixture_id[x$role_legs$n_outcomes<3L]
 testthat::expect_lte(max(c(0L,table(legs$fixture_id[legs$fixture_id %in% double_ids]))),1L)
 testthat::expect_lte(result$summary$spent_cny,1024)
 testthat::expect_identical(rlang::hash(x),before)
})

testthat::test_that("3222221 exact depth is independently enumerated and raw SP is retained", {
 cutoff <- list(issue_id="26098",cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
 p <- tibble::tibble(fixture_id=rep(paste0("26098:",1:7),each=3),outcome=rep(c("W","D","L"),7),probability=c(.4,.3,.3,rep(c(.5,.4,.1),5),.8,.1,.1))
 settings <- beidan::parlay_settings();settings$n_legs <- 7L
 sp <- dplyr::mutate(dplyr::select(p,fixture_id,outcome),quote_at=cutoff$cutoff_utc-60,sp_raw=12,source_url="fixture")
 pool <- IndependentRankedPool(p,cutoff,settings,c(3L,2L,2L,2L,2L,2L,1L),sp=sp)
 grid <- expand.grid(c(.4,.3,.3),c(.5,.4),c(.5,.4),c(.5,.4),c(.5,.4),c(.5,.4),.8)
 mass <- sort(apply(grid,1,prod),decreasing=TRUE)
 for (i in seq_along(c(128,160,192,300))) {
  cap <- c(128,160,192,300)[i];n <- c(64,80,96,96)[i]
  result <- IndependentEvaluate(pool,group_budget_cny=cap,budget_cny=1000)
  testthat::expect_equal(nrow(result$purchases),n)
  testthat::expect_equal(result$summary$spent_cny,2*n)
  testthat::expect_equal(result$summary$actual_coverage,sum(head(mass,n)))
  testthat::expect_equal(result$summary$unspent_cny,1000-2*n)
  testthat::expect_equal(result$purchases$ev_net_est,result$purchases$probability*2*.65*12^7-2)
 }
 testthat::expect_identical(pool$prematch_sp,sp)
})
