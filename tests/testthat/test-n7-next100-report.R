source(testthat::test_path('../../r/n7_next100_report.R'))
testthat::test_that('requested coverage survives serialized empty predictions', {
  cfg <- list(historical_admission=FALSE,scope=list(issue_count=2,first='001',last='002'),model=list(version='frozen'))
  p <- list(historical_admission=FALSE,issue_order=c('001','002'),rows=list(),
    publication_coverage=data.frame(issue=c('001','002'),status='NOT_PUBLISHED',fixture_market_rows=0))
  x <- n7_next100_inputs(jsonlite::fromJSON(jsonlite::toJSON(p,auto_unbox=TRUE)),cfg)
  testthat::expect_equal(nrow(x$probabilities),0)
  testthat::expect_type(x$probabilities$slot,'integer')
  testthat::expect_equal(x$periods$issue,c('001','002'))
  testthat::expect_equal(x$periods$projected_fixtures,c(0L,0L))
  p$rows <- data.frame(issue='001',slot=1L,provider_id='42',handicap=0,q_W=.4,q_D=.3,q_L=.3,
                      new_W=.4,new_D=.3,new_L=.3,version='frozen')
  p$publication_coverage$fixture_market_rows[1] <- 2
  testthat::expect_equal(n7_next100_inputs(p,cfg)$periods$projected_fixtures,c(1L,0L))
  p$rows$q_W <- .7
  testthat::expect_error(n7_next100_inputs(p,cfg))
  p$rows$q_W <- .4;p$rows$issue <- '003'
  testthat::expect_error(n7_next100_inputs(p,cfg))
})

testthat::test_that('financial reporting requires successful complete replay evidence', {
  x <- list(historical_admission=FALSE,settlement_replay_status='PASS',issue_order=c('001','002'),
    independent_replay=list(status='PASS',plans_checked=2),
    settlement_replay=list(status='PASS',plans_checked=2),
    rows=data.frame(issue=c('001','002'),seed=1,arm='A'))
  testthat::expect_true(n7_next100_acceptance(x,c('001','002'),1,'A'))
  for (field in c('independent_replay','settlement_replay')) {
    bad <- x;bad[[field]] <- NULL
    testthat::expect_error(n7_next100_acceptance(bad,c('001','002'),1,'A'))
    bad <- x;bad[[field]]$status <- 'FAIL'
    testthat::expect_error(n7_next100_acceptance(bad,c('001','002'),1,'A'))
    bad <- x;bad[[field]]$plans_checked <- NULL
    testthat::expect_error(n7_next100_acceptance(bad,c('001','002'),1,'A'))
  }
  bad <- x;bad$rows$issue[2] <- '003'
  testthat::expect_error(n7_next100_acceptance(bad,c('001','002'),1,'A'))
})
