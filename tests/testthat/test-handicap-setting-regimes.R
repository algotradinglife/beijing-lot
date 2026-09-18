source(testthat::test_path('..','..','r','strategy_diagnostic_probabilities.R'))
source(testthat::test_path('..','..','r','handicap_setting_regimes.R'))

test_that('setting shifts reconcile with complete common support',{
 x<-data.frame(issue=c('001','001','002','002'),slot=c(1,2,1,2),provider_id=as.character(1:4),year=c('2010','2010','2011','2011'),
 handicap=c(0,0,0,-1),odds_W=2,odds_D=3,odds_L=4,lambda_home=1.5,lambda_away=1)
 z<-handicap_setting_regimes(x,c(-1,0,1),c(0,3,Inf),c('2010','2011'),1)
 expect_equal(z$annual$zero_share,c(1,.5));expect_equal(z$standardized$standard_zero,c(1,.5))
 expect_equal(z$decomposition$within,-.5);expect_equal(z$decomposition$composition,0)
 expect_equal(z$coverage$common_share,c(1,1))
 expect_equal(z$fixtures$euro_W,rep((1/2)/(1/2+1/3+1/4),4))
 x$lambda_home[1:2]<-NA_real_
 z<-handicap_setting_regimes(x,c(-1,0,1),c(0,3,Inf),c('2010','2011'),1)
 expect_equal(nrow(z$standardized),0);expect_equal(z$coverage$common_n,c(0L,0L))
 expect_equal(sum(z$fixtures$total_bin=='UNKNOWN'),2)
 expect_named(z$standardized,c('year','standard_zero','common_cells'))
 f<-tempfile(fileext='.csv');readr::write_csv(z$standardized,f)
 expect_equal(nrow(readr::read_csv(f,show_col_types=FALSE)),0)
 expect_silent(ggplot2::ggplot_build(ggplot2::ggplot(z$standardized,ggplot2::aes(year,standard_zero))+ggplot2::geom_point()))
 z2<-handicap_setting_regimes(x,c(-1,0,1),c(0,3,Inf),c('2010','2011'),1,FALSE)
 expect_equal(z2$coverage$common_share,c(1,1));expect_equal(z2$standardized$standard_zero,c(1,.5))
 x$odds_W[1]<-1;expect_error(handicap_setting_regimes(x,c(-1,0,1),c(0,3,Inf),c('2010','2011'),1))
})

test_that('identity and parameter contract failures stop',{
 x<-data.frame(issue=c('001','002'),slot=1,provider_id=c('1','2'),year=c('2010','2011'),handicap=0,
 odds_W=2,odds_D=3,odds_L=4,lambda_home=1.5,lambda_away=1)
 expect_error(handicap_setting_regimes(rbind(x,x),c(-1,1),c(0,Inf),c('2010','2011'),1))
 expect_error(handicap_setting_regimes(x,c(-1,1),c(0,Inf),c('2010','2012'),1))
 x$handicap[1]<-.5;expect_error(handicap_setting_regimes(x,c(-1,1),c(0,Inf),c('2010','2011'),1))
 x$handicap[1]<-0;x$lambda_home[1]<--1;expect_error(handicap_setting_regimes(x,c(-1,1),c(0,Inf),c('2010','2011'),1))
})
