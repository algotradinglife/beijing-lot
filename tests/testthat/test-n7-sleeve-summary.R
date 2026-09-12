source('../../r/fundamentals_equity_curves.R')
source('../../r/market_conditional_summary.R')
source('../../r/n7_sleeve_summary.R')
testthat::test_that('sleeve accounting distinguishes no-bet, concentration and matched exposure',{
 x<-tibble::tibble(issue=rep(as.character(1:5),3),arm=rep(c('MONOLITHIC_PROB512','MONOLITHIC_COVERAGE512','8x64_PROB'),each=5),seed=1L,
  stake=c(rep(2,10),0,2,2,2,2),gross=c(0,0,10,0,0,0,4,4,0,0,0,0,10,0,0),decision_year='2010',
  train_coverage=.3,eval_coverage=.2) |> dplyr::mutate(net=gross-stake,groups=stake/2,hits=as.integer(gross>0),status=ifelse(stake>0,'COMPLETE','NO_BET'))
 z<-n7_sleeve_summary(x,as.character(1:5),100,2)
 s<-z$summary[z$summary$model=='8x64_PROB',]
 testthat::expect_equal(s$net,2)
 testthat::expect_equal(s$no_bet_issues,1)
 testthat::expect_equal(s$longest_losing_run,2)
 testthat::expect_equal(s$payout_hhi,1)
 testthat::expect_true(is.na(s$ex_year_roi))
 testthat::expect_equal(z$matched$matched_issues[z$matched$model=='8x64_PROB'],c(4,4))
 testthat::expect_equal(s$maximum_completed_recovery,1)
 testthat::expect_error(n7_sleeve_summary(x[-1,],as.character(1:5),100,2))
 testthat::expect_error(n7_sleeve_summary(x,as.character(1:5),100,4))
 stopped<-n7_sleeve_summary(x,as.character(1:5),2,2)$periods
 testthat::expect_true(any(stopped$stopped))
 testthat::expect_equal(stopped$stake+stopped$cash_cny,rep(2,nrow(stopped)))
 testthat::expect_equal(stopped$cash_cny[stopped$stopped],rep(2,sum(stopped$stopped)))
})

testthat::test_that('funded streaks bridge NO_BET and distinguish partial payouts',{
 x<-tidyr::expand_grid(arm=c('MONOLITHIC_PROB512','MONOLITHIC_COVERAGE512','8x64_PROB'),issue=as.character(1:7)) |>
  dplyr::mutate(seed=1L,stake=rep(c(2,0,2,2,0,2,2),3),gross=rep(c(0,0,0,1,0,4,0),3),
   net=gross-stake,groups=stake/2,hits=as.integer(gross>0),decision_year='2010',
   train_coverage=.3,eval_coverage=.2,status=ifelse(stake>0,'COMPLETE','NO_BET'))
 z<-n7_sleeve_summary(x,as.character(1:7),100,2)
 testthat::expect_equal(z$summary$longest_losing_run,rep(3,3))
 testthat::expect_equal(z$summary$longest_no_payout_run,rep(2,3))
 # All-cash policies have zero funded observations, not a seven-issue loss run.
 empty<-x |> dplyr::mutate(stake=0,gross=0,net=0,groups=0,hits=0,status='NO_BET')
 e<-n7_sleeve_summary(empty,as.character(1:7),100,2)
 testthat::expect_equal(e$summary$longest_losing_run,rep(0,3))
 testthat::expect_equal(e$summary$longest_no_payout_run,rep(0,3))
})
