source(file.path('..','..','r','n7_prefix_settlement.R'))
testthat::test_that('cutting a winning prefix loses its payout and preserves cash issues', {
  plans<-data.frame(issue='001',arm='a',seed=1,sleeve_id='g',variant=c('FILTER_ONLY','CAP'),
    depth=c(64,32),copies=1,stake=c(128,64),expected_gross=c(80,40),saved_stake=c(0,64),lost_coverage=c(0,.1))
  ranks<-data.frame(issue='001',sleeve_id='g',actual_rank=40,actual_gross_cny=500)
  old<-data.frame(issue=c('001','002'),arm='a',seed=1,cohort='x',mode='x',objective='x',allocation_order='x',budget_cny=512,
    stake=c(128,0),gross=c(500,0),hits=c(1,0))
  x<-n7_prefix_settlement(plans,ranks,old,c('FILTER_ONLY','CAP'))
  testthat::expect_equal(nrow(x$rows),4)
  testthat::expect_equal(x$groups$gross,c(500,0))
  testthat::expect_equal(x$rows$cash[x$rows$issue=='002'],c(512,512))
  testthat::expect_error(n7_prefix_settlement(plans[1,],ranks,old,c('FILTER_ONLY','CAP')))
  testthat::expect_error(n7_prefix_settlement(plans,ranks[FALSE,],old,c('FILTER_ONLY','CAP')))
  old$gross[1]<-400;testthat::expect_error(n7_prefix_settlement(plans,ranks,old,c('FILTER_ONLY','CAP')))
})
