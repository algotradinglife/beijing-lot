root<-normalizePath(file.path(testthat::test_path(),'../..'))
source(file.path(root,'r/n7_threshold_scatter.R'))
test_that('threshold counts are exact prefixes and diagonal includes equality',{
 x<-tibble::tibble(issue=c('001','001'),sleeve_id=c('0','1'),origin='TEST',actual_rank=c(15,20),
  coverage_15_cost_cny=c(30,20),coverage_20_cost_cny=c(40,40))
 z<-n7_threshold_points(x,c(.15,.2),2)
 expect_equal(z$theory_tickets,c(15,10,20,20));expect_equal(z$covered,c(TRUE,FALSE,TRUE,TRUE))
 expect_equal(z$actual_to_theory,c(1,2,.75,1));expect_equal(z$issue,rep('001',4))
 b<-n7_threshold_bins(z,c(0,15,32,2187),15)
 expect_equal(sum(b$sleeves),4);expect_equal(b$covered_rate,c(.5,1))
 expect_error(n7_threshold_points(x,c(.15,.25),2))
 bad<-x;bad$coverage_15_cost_cny[1]<-31;expect_error(n7_threshold_points(bad,.15,2))
 expect_error(n7_threshold_bins(z,c(0,10),15))
 bad<-x;bad$coverage_20_cost_cny[1]<-2
 expect_error(n7_threshold_points(bad,c(.15,.2),2))
 bad<-x;bad$coverage_15_cost_cny[1]<-5000
 expect_error(n7_threshold_points(bad,.15,2))
})
