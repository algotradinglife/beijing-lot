source(file.path(testthat::test_path(),'../../r/n7_rank_return.R'))
test_that('fixed prefixes include losses and never apply payout twice', {
  c <- tibble::tibble(sleeve_id=rep(0:1,each=2),depth=rep(c(1,2),2),
    stake=rep(c(2,4),2),coverage=c(.2,.4,.3,.5),expected_gross=c(1.3,2.6,1.3,2.6))
  r <- tibble::tibble(issue='001',sleeve_id=c('0','1'),actual_rank=c(1,2),actual_gross_cny=c(13,26))
  p <- n7_rank_return_prefixes(c,r,c(1,2),2)
  expect_equal(p$realized_gross,c(13,13,0,26))
  expect_equal(p$expected_net,c(-.7,-1.4,-.7,-1.4))
  p$cohort <- 'old'
  s <- n7_rank_return_summary(p)
  expect_equal(s$actual_hit,c(.5,1));expect_equal(s$actual_roi,c(13/4-1,39/8-1))
  expect_equal(s$expected_roi,c(-.35,-.35))
  expect_error(n7_rank_return_prefixes(c,r,c(1,1),2))
  expect_error(n7_rank_return_prefixes(c,r,NA,2))
  expect_error(n7_rank_return_prefixes(c,r,1.5,2))
  expect_error(n7_rank_return_prefixes(c[-1,],r,1:2,2))
  expect_error(n7_rank_return_prefixes(c,dplyr::bind_rows(r,r),1:2,2))
  expect_error(n7_rank_return_prefixes(c,r,1:2,1))
  c$expected_gross[1] <- NA_real_
  expect_error(n7_rank_return_prefixes(c,r,1:2,2))
  expect_error(n7_rank_return_summary(dplyr::bind_rows(p,p)))
  expect_error(n7_rank_return_summary(p[0,]))
})
