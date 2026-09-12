source('../../r/fundamentals_equity_curves.R')
source('../../r/market_conditional_summary.R')
source('../../r/n7_capital_report.R')

test_that('capital reporting preserves variable spend ROI cash and bankroll stops',{
  rows<-tibble::tibble(issue=rep(c('001','002','003'),2),arm=rep(c('A','B'),each=3),seed=1,
    reference=FALSE,budget_cny=512,stake=c(512,256,512,512,0,512),
    gross=c(0,768,0,1024,0,512),net=gross-stake,groups=stake/2,hits=as.integer(gross>0),
    status=ifelse(stake>0,'COMPLETE','NO_BET'))
  result<-n7_capital_report(rows,c('001','002','003'),100000,1024)
  a<-result$summary[result$summary$model=='A',]
  expect_equal(a$stake,1280);expect_equal(a$net,-512);expect_equal(a$roi_percent,-40)
  expect_equal(a$without_best_roi,-100);expect_equal(a$max_drawdown,512)
  expect_equal(a$longest_underwater,1);expect_equal(a$maximum_completed_recovery,1)
  expect_equal(a$cash_cny,256)
  paired<-n7_capital_matched(result$periods,'A','B')
  expect_equal(paired$matched_issues,2);expect_equal(paired$matched_stake_cny,1024)
  expect_equal(paired$roi_delta_pp,-150)
  stop<-n7_capital_report(rows,c('001','002','003'),512,1024)
  stopped<-stop$periods[stop$periods$arm=='A',]
  expect_equal(stopped$stake,c(512,0,0));expect_equal(stopped$net,c(-512,0,0))
  expect_equal(stopped$cash_cny,c(0,512,512));expect_equal(stopped$groups,c(256,0,0))
  expect_true(all(stopped$equity_cny==0))
  bad<-rows;bad$net[1]<-1
  expect_error(n7_capital_report(bad,c('001','002','003'),100000,1024))
  expect_error(n7_capital_matched(result$periods[-1,],'A','B'))
})

test_that('unfunded strategies keep undefined ROI and archived budgets explicit',{
  rows<-tibble::tibble(issue=c('01','02'),arm='CASH',seed=1,reference=FALSE,budget_cny=512,
    stake=0,gross=0,net=0,groups=0,hits=0,status='NO_BET')
  x<-n7_capital_report(rows,c('01','02'),100000,1024)
  expect_true(is.na(x$summary$roi_percent));expect_equal(x$summary$funded_issues,0)
  expect_true(is.na(x$summary$payout_hhi));expect_equal(x$summary$cash_cny,1024)
  rows$reference<-TRUE;rows$budget_cny<-NA_real_
  expect_equal(n7_capital_report(rows,c('01','02'),100000,1024)$summary$cash_cny,2048)
  both<-dplyr::bind_rows(x$periods,dplyr::mutate(x$periods,arm='OTHER'))
  match<-n7_capital_matched(both,'CASH','OTHER')
  expect_equal(match$matched_issues,0);expect_true(is.na(match$roi_delta_pp))
})

test_that('model answers include failed allocations and separate money weighting',{
 rows<-tibble::tibble(reference=FALSE,arm='A',budget_cny=512,stake=c(512,0),
   solver_status=c('OPTIMAL_WITHIN_TOLERANCE','Infeasible'),funded_sleeves=c(4,0),
   evaluation_expected_net=c(-128,0),evaluation_any_hit=c(.6,0),evaluation_at_least_two=c(.2,0),
   evaluation_zero_hit=c(.4,1),evaluation_profit_probability=c(.4,0),evaluation_loss_probability=c(.6,0),
   evaluation_payoff_ratio=c(2,NA),evaluation_coverage_mean=c(.15,NA),
   evaluation_coverage_weighted_mean=c(.2,NA),evaluation_gain_support=c(200,0),
   evaluation_loss_support=c(300,0),training_any_hit=c(.7,0),evaluation_distinct_fixture_count=c(20,0))
 x<-n7_capital_answers(rows)
 expect_equal(x$funded_trials,1);expect_equal(x$infeasible_trials,1)
 expect_equal(x$mean_stake_cny,256);expect_equal(x$modeled_roi_percent,-25)
 expect_equal(x$any_hit_percent,30);expect_equal(x$equal_sleeve_coverage_percent,15)
 expect_equal(x$money_weighted_coverage_percent,20);expect_equal(x$optimism_pp,5)
 expect_equal(x$conditional_ratio_supported_trials,1)
 expect_error(n7_capital_answers(rows[,setdiff(names(rows),'evaluation_any_hit')]))
})
