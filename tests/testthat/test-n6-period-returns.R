source(testthat::test_path('..','..','r','fundamentals_period_returns.R'))

test_that('period accounting reconciles and separates frequency from payout', {
 g <- tibble::tibble(issue=rep(c('01','02'),each=2),policy='p',group=rep(1:2,2),
  stake=10,gross=c(20,0,10,30),hit=c(TRUE,FALSE,TRUE,TRUE))
 r <- tibble::tibble(issue=c('01','02'),policy='p',groups=2,hits=c(1,2),
  stake=20,gross=c(20,40),net=c(0,20),optional=NA_real_)
 z <- n6_period_returns(r,g,c('01','02'),1)
 expect_equal(z$summary$mean_winning_gross,c(20,20))
 expect_equal(z$summary$median_winning_gross,c(20,20))
 expect_equal(z$summary$required_mean_gross,c(20,10))
 expect_equal(z$summary$net_without_best_group,c(-20,-10))
 expect_equal(z$change$hit_effect_pp,100)
 expect_equal(z$change$payout_effect_pp,0)
 expect_equal(z$change$recovery_change_pp,z$change$hit_effect_pp+z$change$payout_effect_pp)
 expect_error(n6_period_returns(r,g,c('01','02'),3))
 expect_error(n6_period_returns(r,rbind(g,g[1,]),c('01','02'),1))
 bad<-r;bad$hits[1]<-2
 expect_error(n6_period_returns(bad,g,c('01','02'),1))
 bad<-g;bad$stake[1]<-Inf
 expect_error(n6_period_returns(r,bad,c('01','02'),1))
 g$gross[1]<-0;g$hit[1]<-FALSE;r$gross[1]<-0;r$net[1]<- -20;r$hits[1]<-0
 z<-n6_period_returns(r,g,c('01','02'),1)
 expect_true(is.na(z$summary$mean_winning_gross[1]))
 expect_true(is.na(z$change$payout_effect_pp))
})
