source('../../r/fundamentals_equity_curves.R')
source('../../r/market_conditional_summary.R')
source('../../r/n7_sleeve_expansion_report.R')
testthat::test_that('expanded pool accounting preserves full budget and returns', {
 rows<-tibble::tibble(issue=rep(c('001','002','003'),2),arm=rep(c('POOL24','POOL240'),each=3),seed=1L,
   stake=1024,gross=c(0,4096,0,0,2048,0),net=gross-stake,hits=ifelse(gross>0,1L,0L),groups=512L,
   status='COMPLETE',pool_size=rep(c(24L,240L),each=3),weighting='EXPECTED_GROSS',eval_coverage=.5)
 candidates<-rows |> dplyr::transmute(issue,pool_size,actual=pool_size,eligible=8L)
 a<-n7_sleeve_expansion_report(rows,candidates,c('001','002','003'),100000,1024)
 testthat::expect_equal(a$summary$roi_percent,c(100/3,-100/3))
 testthat::expect_equal(a$summary$max_drawdown,c(1024,1024))
 testthat::expect_equal(a$counts$exactly_eight,c(3L,3L))
 testthat::expect_equal(a$summary$hit_issues,c(1L,1L))
 testthat::expect_equal(a$matched$issues,c(3L,3L))
 testthat::expect_equal(a$summary$without_best_roi,c(-100,-100))
 stopped<-n7_sleeve_expansion_report(rows,candidates,c('001','002','003'),1024,1024)
 testthat::expect_equal(stopped$summary$stopped_issues,c(2L,2L))
 testthat::expect_equal(stopped$summary$net,c(-1024,-1024))
 bad<-rows;bad$stake[1]<-512
 testthat::expect_error(n7_sleeve_expansion_report(bad,candidates,c('001','002','003'),100000,1024))
 testthat::expect_error(n7_sleeve_expansion_report(dplyr::bind_rows(rows,rows[1,]),candidates,c('001','002','003'),100000,1024))
})
