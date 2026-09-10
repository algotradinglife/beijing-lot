source('../../r/probability_exploration.R')
source('../../r/fundamentals_home_away.R')
source('../../r/goal_distribution_experiment.R')

test_that('paired robust treatment retains ledger and original bytes semantics', {
  x <- list(list(history_id='a',home_goals=9L,away_goals=1L),list(history_id='b',home_goals=1L,away_goals=1L),list(history_id='c',home_goals=2L,away_goals=0L))
  original <- x
  expect_equal(goal_window_descriptor(x,'raw')$home_mean,4)
  d <- goal_window_descriptor(x,'drop_max');expect_equal(d$home_mean,1.5);expect_equal(d$n,2)
  expect_false(d$ledger$retained[1])
  c <- goal_window_descriptor(x,'cap_max');expect_equal(c$ledger$scale[1],.2)
  expect_equal(c$ledger$used_home[1],1.8);expect_equal(c$ledger$used_away[1],.2)
  expect_identical(x,original)
  expect_error(goal_window_descriptor(x,'bad'))
  x[[1]]$away_goals <- NA_integer_;expect_error(goal_window_descriptor(x,'raw'),'scores')
})

test_that('full score distributions preserve means and labels cannot alter predictions', {
  cutoff <- '2010-01-01T00:00:00+00:00'
  receipt <- list(cutoff_ts=cutoff,historical_admission=FALSE,intended_use='RETROSPECTIVE_DESCRIPTION_ONLY')
  rows <- list(list(history_id='a',home_goals=4L,away_goals=1L),list(history_id='b',home_goals=1L,away_goals=0L))
  w <- list(slot=1L,provider_id='001',home='H',away='A',competition='cup',cutoff_utc=cutoff,
    status='OK_DIAGNOSTIC',home_window=rows,away_window=rows,home_receipt=receipt,away_receipt=receipt)
  h <- tibble::tibble(slot=1L,provider_id='001',home_handicap=-1L)
  base <- home_away_probabilities(list(w),h,list(`1`=cutoff),5L,1e-10)
  e <- goal_distribution_experiment(base,list(`1`=cutoff),c(.7,1.3),c(.5,.5),1e-10)
  expect_equal(nrow(e$fixtures),4)
  expect_equal(e$fixtures$lambda_home[e$fixtures$variant=='raw'],e$fixtures$lambda_home[e$fixtures$variant=='raw_mixture'])
  for(g in e$grids) expect_equal(sum(g$probability),1)
  expect_equal(e$fixtures$ordinary_W+e$fixtures$ordinary_D+e$fixtures$ordinary_L,rep(1,4),tolerance=1e-10)
  g0 <- e$grids[['1/raw']]
  expect_equal(e$fixtures$ordinary_D[e$fixtures$variant=='raw'],sum(g0$probability[g0$home_goals==g0$away_goals]))
  f <- e$fixtures;expect_true(all(f$home_ge4<=f$home_ge3 & f$home_ge3<=f$home_ge2))
  g <- e$grids[['1/raw_mixture']]
  expect_equal(sum(g$home_goals*g$probability),2.5,tolerance=1e-8)
  labels <- tibble::tibble(slot=1L,provider_id='001',result_state='完场',actual_home=3L,actual_away=0L)
  original <- e; v <- evaluate_goal_distributions(e,labels)
  expect_equal(v$summary$actual_home_big,rep(1,4));expect_equal(v$summary$n,rep(1L,4))
  expect_identical(e,original)
  labels$actual_home <- 100L
  extreme <- evaluate_goal_distributions(e,labels)
  expect_true(all(is.finite(extreme$fixtures$score_nll)))
  expect_equal(extreme$fixtures$lambda_home,v$fixtures$lambda_home)
  labels$actual_home <- NA_integer_; labels$actual_away <- NA_integer_;labels$result_state <- '推迟'
  expect_equal(nrow(evaluate_goal_distributions(e,labels)$summary),0)
  expect_error(goal_distribution_experiment(base,list(`1`='2011-01-01T00:00:00Z'),c(.7,1.3),c(.5,.5),1e-10),'Cutoff')
  expect_error(goal_distribution_experiment(base,list(`1`=cutoff),c(.7,1.3),c(.2,.8),1e-10),'mixture')
})
