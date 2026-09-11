source(file.path('..','..','r','fundamentals_equity_curves.R'))
source(file.path('..','..','r','fundamentals_missed_summary.R'))
source(file.path('..','..','r','fundamentals_rescue_summary.R'))
testthat::test_that('original misses distinguish rescues, profits and original hits lost',{
 x<-tibble::tibble(policy=rep(c('MAIN','ALT'),each=4),issue=rep(c('001','002','003','004'),2),status='COMPLETE',
 stake=64,budget_cny=1024,cash_cny=960,groups=1,hits=c(0,0,1,1,1,1,0,1),
 gross=c(0,0,200,200,30,300,0,200),n6_hits=0) |> dplyr::mutate(net=gross-stake,n7_hits=hits)
 z<-missed_rescue_summary(x,'MAIN',c('001','002','003','004'),100000)
 a<-dplyr::filter(z$summary,policy=='ALT')
 testthat::expect_equal(a$rescued_issues,2L);testthat::expect_equal(a$profitable_old_misses,1L)
 testthat::expect_equal(a$lost_issues,1L);testthat::expect_equal(a$net_old_misses,202)
 testthat::expect_equal(a$miss_budget_ROI_percent,100*202/2048)
 testthat::expect_equal(a$ex_best_miss_net,-34);testthat::expect_equal(a$ex_best_lift,-170)
 testthat::expect_equal(nrow(z$missed_periods),4L)
 testthat::expect_error(missed_rescue_summary(x,'UNKNOWN',c('001','002','003','004'),100000))
 testthat::expect_error(missed_rescue_summary(dplyr::bind_rows(x,x[1,]),'MAIN',c('001','002','003','004'),100000))
})
