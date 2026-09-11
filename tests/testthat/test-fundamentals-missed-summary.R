source(file.path('..','..','r','fundamentals_equity_curves.R'))
source(file.path('..','..','r','fundamentals_missed_summary.R'))
testthat::test_that('summary separates hit frequency profit and drawdown',{
 x<-tibble::tibble(policy='A',issue=c('001','002','003'),status='COMPLETE',stake=64,gross=c(0,0,300),net=c(-64,-64,236),
 budget_cny=1024,cash_cny=960,groups=1,hits=c(0,0,1),n6_hits=c(0,0,1),n7_hits=0)
 s<-missed_strategy_summary(x,x$issue,100000)$summary
 testthat::expect_equal(s$longest_miss_streak,2L);testthat::expect_equal(s$hit_issues,1L)
 testthat::expect_equal(s$net_cny,108);testthat::expect_equal(s$max_drawdown_cny,128)
 testthat::expect_equal(s$budget_ROI_percent,100*108/3072)
 testthat::expect_error(missed_strategy_summary(dplyr::mutate(x,hits=2),x$issue,100000))
})
