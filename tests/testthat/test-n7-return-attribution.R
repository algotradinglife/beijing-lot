source(file.path('..','..','r','n7_return_attribution.R'))
testthat::test_that('return bridge conserves money and copies without reapplying payout factor',{
  f <- tibble::tibble(issue='01',arm='a',seed=1,sleeve_id=c('0','1'),
    depth=c(2,1),stake=c(8,2),expected_gross=c(6,1),coverage=c(.3,.2),copies=c(2,1))
  e <- tibble::tibble(issue='01',sleeve_id=c('0','1'),actual_rank=c(2,2),
    estimated_actual_payout=c(5,7),actual_gross_cny=c(8,10))
  z <- n7_return_attribution(f,e,2)
  testthat::expect_equal(z$groups$actual_gross,c(16,0))
  testthat::expect_equal(z$periods$model_net,-3)
  testthat::expect_equal(z$periods$outcome_residual,3)
  testthat::expect_equal(z$periods$price_residual,6)
  testthat::expect_equal(z$periods$actual_net,6)
  testthat::expect_equal(z$periods$expected_group_hits,.5)
  testthat::expect_equal(nrow(n7_return_attribution(f[0,],e,2)$groups),0)
  testthat::expect_error(n7_return_attribution(f,e[1,],2))
  testthat::expect_error(n7_return_attribution(f,dplyr::bind_rows(e,e),2))
  testthat::expect_error(n7_return_attribution(dplyr::bind_rows(f,f),e,2))
  for(col in c('depth','stake','expected_gross','coverage','copies')) {
    bad <- f; bad[[col]][1] <- NA_real_
    testthat::expect_error(n7_return_attribution(bad,e,2))
  }
  bad <- f;bad$copies[1]<-1.5
  testthat::expect_error(n7_return_attribution(bad,e,2))
  bad<-e;bad$actual_rank[1]<-0
  testthat::expect_error(n7_return_attribution(f,bad,2))
  testthat::expect_error(n7_return_attribution(f,e,1))
})
