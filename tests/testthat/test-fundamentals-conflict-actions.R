source(file.path('..','..','r','fundamentals_integration_weight.R'))
source(file.path('..','..','r','fundamentals_conflict_actions.R'))

test_that('stage tables separate incremental cost, score returns and proper scores', {
  x <- tibble::tibble(stage='PROTECT',partition='TEST8',issue=rep(c('001','002'),2),policy=rep(c('CURRENT','SCORE'),each=2),
    stake=c(256,256,258,258),gross=c(512,0,520,0),net=gross-stake,hits=c(1,0,1,0),groups=1,
    status='COMPLETE',main_stake=256,main_gross=c(512,0,512,0),score_stake=c(0,0,2,2),
    score_gross=c(0,0,8,0),score_bets=c(0,0,1,1),score_hits=c(0,0,1,0),base_stake=256,
    expanded_matches=0,distinct_tickets=128,betting_units=128)
  metrics <- tibble::tibble(issue='001',slot=1L,provider_id='0001',policy='CURRENT',partition='TEST8',
    conflict=TRUE,actual_direction='W',p_W=.5,p_D=.3,p_L=.2,p_actual_score=.25,score_outside_support=FALSE)
  z <- conflict_action_tables(list(list(rows=x,prediction_metrics=metrics)),1e-12)
  score <- dplyr::filter(z$summary,policy=='SCORE')
  expect_equal(score$net_lift,4)
  expect_equal(score$stake_delta,4)
  expect_equal(score$incremental_roi,1)
  expect_equal(score$score_roi,1)
  expect_equal(score$max_drawdown_cny,258)
  expect_equal(z$probability_diagnostics$mean_WDL_brier,.38)
  expect_equal(z$probability_diagnostics$mean_score_log_loss,-log(.25))
  expect_equal(nrow(z$periods),4)
  expect_error(conflict_action_tables(list(list(rows=dplyr::bind_rows(x,x),prediction_metrics=metrics)),1e-12))
  x$gross[1] <- 0
  expect_error(conflict_action_tables(list(list(rows=x,prediction_metrics=metrics)),1e-12))
})
