source('../../r/fundamentals_equity_curves.R')
source('../../r/market_conditional_summary.R')
source('../../r/n7_core_profit_summary.R')
testthat::test_that('funded metrics, ranges and paired counts retain per-period values',{
 x<-tibble::tibble(issue=rep(as.character(1:5),2),tag=rep(c('PROB','PROFIT'),each=5),seed=1L,
   stake=2,gross=c(0,0,10,0,0,0,4,4,0,0),groups=1,hits=as.integer(gross>0),
   train_profit=.3,eval_profit=.2,stress_low=.1,stress_high=.4) |> dplyr::mutate(net=gross-stake)
 z<-n7_core_profit_summary(x,as.character(1:5),100,2)
 s<-z$summary[z$summary$model=='PROB',]
 testthat::expect_equal(s$net,0)
 testthat::expect_equal(s$longest_losing_run,2)
 testthat::expect_equal(s$worst5,0)
 testthat::expect_true(is.na(s$worst10))
 testthat::expect_equal(s$max_drawdown,4)
 testthat::expect_equal(z$paired$new_vs_prob[z$paired$model=='PROFIT'],1)
 testthat::expect_equal(z$grid$min_profitable,c(1,2))
 testthat::expect_error(n7_core_profit_summary(x[-1,],as.character(1:5),100,2))
 testthat::expect_error(n7_core_profit_summary(x,as.character(1:5),100,1))
})
