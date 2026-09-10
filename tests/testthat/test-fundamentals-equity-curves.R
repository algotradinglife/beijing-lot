source('../../r/fundamentals_equity_curves.R')
testthat::test_that('equity uses retained cash, explicit order and one initial deposit', {
 x <- tibble::tibble(model='pure',policy='p',issue=c('002','001','003'),
  status='COMPLETE',stake=c(80,100,90),gross=c(0,150,100),net=c(-80,50,10),
  budget_cny=128,cash_cny=c(48,28,38))
 z <- strategy_equity_curves(x,c('001','002','003'),100)
 testthat::expect_equal(z$equity_cny,c(100,150,70,70))
 testthat::expect_equal(z$shadow_equity_cny,c(100,150,70,80))
 testthat::expect_equal(z$funded_stake_cny,c(0,100,80,0))
 testthat::expect_equal(z$stop_started,c(FALSE,FALSE,FALSE,TRUE))
 testthat::expect_equal(z$drawdown_cny,c(0,0,80,80))
 testthat::expect_equal(z$capital_return_percent,c(0,50,-30,-30))
 testthat::expect_true(is.na(z$issue[1]))
 y <- strategy_equity_curves(x,c('001','002','003'),100000)
 testthat::expect_equal(y$equity_cny,y$shadow_equity_cny)
 testthat::expect_equal(tail(y$equity_cny,1),100000+sum(x$net))
 testthat::expect_error(strategy_equity_curves(x,c('001','002'),100))
 testthat::expect_error(strategy_equity_curves(dplyr::bind_rows(x,x[1,]),c('001','002','003'),100))
 bad <- x;bad$net[1] <- NA_real_
 testthat::expect_error(strategy_equity_curves(bad,c('001','002','003'),100))
 bad <- x;bad$gross[1] <- 1
 testthat::expect_error(strategy_equity_curves(bad,c('001','002','003'),100))
 bad <- x;bad$status[1] <- 'PENDING'
 testthat::expect_error(strategy_equity_curves(bad,c('001','002','003'),100))
 testthat::expect_error(strategy_equity_curves(x[0,],character(),100))
 testthat::expect_error(strategy_equity_curves(x,c('001','002','003'),0))
 z$label <- 'strategy'
 p <- plot_strategy_equity(z,'funded',100)
 testthat::expect_s3_class(p,'ggplot')
 testthat::expect_equal(ggplot2::ggplot_build(p)$data[[2]]$y,z$equity_cny)
 testthat::expect_equal(nrow(ggplot2::ggplot_build(p)$data[[3]]),1)
 testthat::expect_equal(ggplot2::ggplot_build(plot_strategy_equity(z,'shadow',100))$data[[2]]$y,z$shadow_equity_cny)
 testthat::expect_error(plot_strategy_equity(z,'invalid',100))
})
testthat::test_that('zero stakes, exact affordability and models remain separate', {
 x <- tibble::tibble(model=rep(c('pure','expert'),each=3),policy='p',
  issue=rep(c('001','002','003'),2),status=rep(c('NO_BET','COMPLETE','COMPLETE'),2),
  stake=rep(c(0,100,100),2),gross=c(0,0,200,0,200,0),
  net=gross-stake,budget_cny=128,cash_cny=budget_cny-stake)
 z <- strategy_equity_curves(x,c('001','002','003'),100)
 testthat::expect_equal(z$equity_cny[z$model=='pure'],c(100,100,0,0))
 testthat::expect_equal(z$equity_cny[z$model=='expert'],c(100,100,200,100))
 testthat::expect_equal(sum(z$stop_started),1)
 bad <- x;bad$status[2] <- 'NO_BET'
 testthat::expect_error(strategy_equity_curves(bad,c('001','002','003'),100))
})
