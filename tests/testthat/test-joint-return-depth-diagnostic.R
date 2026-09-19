source(file.path('..','..','r','joint_return_depth_diagnostic.R'))
testthat::test_that('prefix truncation preserves prices, copies and cash',{
 g<-tibble::tibble(issue=c('a','a'),arm='JOINT',seed=0,sleeve_id=c('1','2'),stage='X',depth=c(4,2),stake=c(16,4),copies=c(2,1),actual_rank=c(3,1),actual_gross_cny=c(100,10))
 z<-joint_return_depth_diagnostic(g,c(2,4),2)
 testthat::expect_equal(z$totals$stake,c(12,20))
 testthat::expect_equal(z$totals$gross,c(10,210))
 testthat::expect_equal(z$totals$cash_saved,c(8,0))
 testthat::expect_equal(z$totals$net,c(-2,190))
 testthat::expect_equal(z$tails$mean_payout,105)
 testthat::expect_error(joint_return_depth_diagnostic(g,c(0,2),2))
 testthat::expect_error(joint_return_depth_diagnostic(dplyr::bind_rows(g,g),2,2))
 g$actual_rank[1]<-NA
 testthat::expect_error(joint_return_depth_diagnostic(g,2,2))
})
