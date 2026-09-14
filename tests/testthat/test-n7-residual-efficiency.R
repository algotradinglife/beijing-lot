source('../../r/n7_residual_efficiency.R')
testthat::test_that('paired cost ratios distinguish zero-spend and zero-gain cases',{
  x<-tibble::tibble(issue=c('001','002','003'),arm=c('A','B','C'),seed=1,
    variant='INCREMENTAL',mode='BREADTH',objective='any_hit',allocation_order='OPEN_FIRST',
    budget_cny=512,added_stake=c(0,20,20),added_eval_union=c(0,0,.1))
  z<-n7_residual_efficiency(x)
  testthat::expect_equal(z$per_issue$efficiency_status,
    c('NO_ADDITION','SPENT_WITHOUT_EVAL_GAIN','POSITIVE_EVAL_GAIN'))
  testthat::expect_equal(z$per_issue$cny_per_coverage_pp,c(NA_real_,NA_real_,2))
  testthat::expect_equal(z$paired$cny_per_expected_extra_hit_period,c(NA_real_,NA_real_,200))
  x$arm<-'A';z<-n7_residual_efficiency(x)
  testthat::expect_equal(z$paired$cny_per_summed_coverage_pp,4)
  testthat::expect_equal(z$paired$spent_zero_gain_issues,1)
  x$added_stake[1]<- -1
  testthat::expect_error(n7_residual_efficiency(x))
})
