source('../../r/probability_exploration.R')
source('../../r/strength_market_scenario.R')
source('../../r/fundamentals_score_diagnostic.R')
source('../../r/fundamentals_score_shape.R')
source('../../r/fundamentals_market_comparison.R')
source('../../r/fundamentals_total_market.R')
source('../../r/n7_market_projection.R')

testthat::test_that('market-only projection equals existing projection without forms', {
  f <- tibble::tibble(issue='00101',slot=1L,provider_id='00123',handicap=-1L,
                     cutoff_utc='2010-01-01T00:00:00Z',odds_W=1.8,odds_D=3.5,odds_L=4)
  q <- tibble::tibble(issue='00101',slot=1L,provider_id='00123',company='A',
                     line=2.5,over_hk=.9,under_hk=.9)
  cuts <- list('00101'=list('1'=f$cutoff_utc))
  x <- project_n7_market_inputs(f,q,cuts,c(.1,16),1e-10)
  total <- total_market_constraint(q,c(.1,16))$lambda_total
  target <- 1/c(1.8,3.5,4);target <- target/sum(target)
  expected <- total_constrained_projection(total,target,-1,1e-10)
  testthat::expect_equal(x$grids[['00101/1']],expected$grid)
  testthat::expect_equal(as.numeric(x$fixtures[1,c('q_W','q_D','q_L')]),
                         unname(unlist(expected$fields[c('W','D','L')])))
  testthat::expect_identical(x$fixtures$provider_id,'00123')
  testthat::expect_false(x$historical_admission)
  testthat::expect_error(project_n7_market_inputs(f,q,list(),c(.1,16),1e-10),'cutoffs')
  testthat::expect_error(project_n7_market_inputs(f,q,list('00101'=list('1'='2011-01-01T00:00:00Z')),c(.1,16),1e-10),'cutoff mismatch')
  testthat::expect_error(project_n7_market_inputs(f,q[0,],cuts,c(.1,16),1e-10),'Missing')
  testthat::expect_error(project_n7_market_inputs(f,dplyr::bind_rows(q,q),cuts,c(.1,16),1e-10),'keys')
  testthat::expect_error(project_n7_market_inputs(dplyr::mutate(f,actual='W'),q,cuts,c(.1,16),1e-10),'schema')
  testthat::expect_error(project_n7_market_inputs(dplyr::mutate(f,odds_W=0),q,cuts,c(.1,16),1e-10),'numerical')
  empty <- project_n7_market_inputs(f[0,],q[0,],list(),c(.1,16),1e-10)
  testthat::expect_equal(nrow(empty$fixtures),0L)
  testthat::expect_type(empty$fixtures$q_D,'double')
})
