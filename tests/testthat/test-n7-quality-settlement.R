source(file.path(normalizePath(file.path(testthat::test_path(),'../..')),'r/n7_quality_settlement.R'))
testthat::test_that('quality accounting retains cash rows and never reapplies payout factor', {
 rows<-tibble::tibble(issue=c('a','b'),arm='x',seed=1,stake=c(4,0),budget_cny=8,cash=c(4,8),groups=c(1,0))
 funded<-tibble::tibble(issue='a',arm='x',seed=1,sleeve_id='0',depth=2,copies=1,stake=4)
 ranks<-tibble::tibble(issue='a',sleeve_id='0',actual_rank=2,actual_gross_cny=13)
 out<-n7_quality_settlement(rows,funded,ranks)
 testthat::expect_equal(out$rows$gross,c(13,0))
 testthat::expect_equal(out$rows$net,c(9,0))
 testthat::expect_equal(out$rows$hits,c(1,0))
 ranks$actual_rank<-3
 testthat::expect_equal(n7_quality_settlement(rows,funded,ranks)$rows$net,c(-4,0))
 testthat::expect_error(n7_quality_settlement(rows,funded,ranks[0,]))
 testthat::expect_error(n7_quality_settlement(rows,funded,dplyr::bind_rows(ranks,ranks)))
 rows$stake[1]<-6;rows$cash[1]<-2
 testthat::expect_error(n7_quality_settlement(rows,funded,ranks))
})
