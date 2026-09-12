source('../../r/fundamentals_score_shape.R')
source('../../r/fundamentals_signal_rate_projection.R')
source('../../r/probability_foundation_draw.R')

testthat::test_that('foundation maps draw scores and retains non-draw ratios', {
  g<-data.frame(home_goals=c(1,0,0),away_goals=c(0,0,1),probability=c(.4,.3,.3))
  p<-data.frame(q_W=.4,q_D=.3,q_L=.3,new_W=.2,new_D=.65,new_L=.15,
    cutoff_ts='2010-01-01T00:00:00+00:00',version='market-strength-draw-1.0.0-diagnostic')
  z<-foundation_score_grid(g,0,p,p$cutoff_ts)
  testthat::expect_equal(z$grid$probability,c(.2,.65,.15),tolerance=1e-12)
  testthat::expect_equal(sum(z$grid$probability),1)
  p$version<-'market-balance-draw-1.0.0-diagnostic'
  testthat::expect_equal(foundation_score_grid(g,0,p,p$cutoff_ts)$grid$probability,z$grid$probability)
  testthat::expect_error(foundation_score_grid(g,0,p,'wrong'))
  p$q_D<-.4
  testthat::expect_error(foundation_score_grid(g,0,p,p$cutoff_ts))
})
