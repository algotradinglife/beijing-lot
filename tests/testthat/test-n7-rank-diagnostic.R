root <- normalizePath(file.path(testthat::test_path(),'../..'))
source(file.path(root,'r/n7_rank_diagnostic.R'))
test_that('actual identity and prefix costs are exact and audited', {
  p <- c(.6,.3,.1,rep(0,2184))
  f <- data.frame(issue='001',slot=1:7,provider_id=as.character(11:17),handicap=0)
  a <- transform(f,actual_direction='W',spf_sp=2,status='READY')
  a$actual_direction[7] <- 'D'
  x <- list(issue='001',cutoffs=list(a='epoch'),evidence_class='POST_SETTLEMENT_DIAGNOSTIC',
    fixtures=f,audit=a,sleeves=tibble::tibble(id='0',origin='QUALITY',fixture_indices=list(0:6)),
    curves=tibble::tibble(sleeve_id='0',depth=0:2187,state_id=c(NA,0:2186),
      coverage=c(0,cumsum(p)),stake=2*(0:2187),expected_gross=c(0,cumsum(10*p))))
  y <- n7_rank_diagnostic(x,2,.65,c(.1,.5,1))
  expect_equal(y$top64_coverage,1);expect_equal(y$top128_coverage,1);
  expect_equal(y$actual_rank,2);expect_equal(y$actual_hit_cost_cny,4)
  expect_equal(y$actual_gross_cny,1.3*2^7);expect_equal(y$actual_prefix_net_cny,1.3*2^7-4)
  expect_equal(y$model_expected_hit_cost_cny,3);expect_equal(y$coverage_100_cost_cny,6)
  z <- n7_rank_summary(y,c(2,4));expect_equal(z$oracle_any_hit,c(FALSE,TRUE))
  expect_equal(z$profitable_affordable_candidates,c(0L,1L))
  expect_error(n7_rank_summary(dplyr::bind_rows(y,y),4))
  expect_error(n7_rank_summary(y,NA_real_))
  bad <- x;bad$audit$handicap[1] <- 1;expect_error(n7_rank_diagnostic(bad,2,.65,.5))
  bad <- x;bad$audit$spf_sp[1] <- NA;expect_error(n7_rank_diagnostic(bad,2,.65,.5))
  bad <- x;bad$audit <- bad$audit[-1,];expect_error(n7_rank_diagnostic(bad,2,.65,.5))
  bad <- x;bad$curves$state_id[2] <- 1;expect_error(n7_rank_diagnostic(bad,2,.65,.5))
  expect_error(n7_rank_diagnostic(x,2,.65,NA_real_))
})
test_that('rank diagnosis reproduces funded and cash-only actual returns', {
  rows <- tibble::tibble(issue='001',sleeve_id=c('0','1'),actual_rank=c(2,4),actual_gross_cny=c(10,20))
  a <- tibble::tibble(issue='001',seed=1,arm='funded',sleeve_id=c('0','1'),depth=c(2,3))
  y <- tibble::tibble(issue='001',seed=1,arm=c('funded','cash'),hits=c(1,0),gross=c(10,0))
  expect_equal(n7_rank_allocation_check(rows,a,y)$plans,2L)
  a$sleeve_id <- as.integer(a$sleeve_id)
  expect_equal(n7_rank_allocation_check(rows,a,y)$plans,2L)
  y$gross[1] <- 20;expect_error(n7_rank_allocation_check(rows,a,y))
  y$gross[1] <- 10;a$sleeve_id[1] <- 'unknown';expect_error(n7_rank_allocation_check(rows,a,y))
})
