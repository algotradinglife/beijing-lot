source(file.path('..','..','r','strategy_diagnostic_probabilities.R'))
source(file.path('..','..','r','strategy_handicap_diagnostic.R'))
test_that('signed handicap and outcome diagnostics preserve denominators and ties', {
  x <- tibble::tibble(issue=rep(c('001','002'),each=3),slot=1L,
    provider_id=rep(c('a','b'),each=3),model='p',handicap=-1,
    outcome=rep(c('W','D','L'),2),actual_outcome=rep(c('D','L'),each=3),
    probability=c(.5,.3,.2,.4,.3,.3))
  r <- strategy_handicap_diagnostic(x,'handicap',c('W','D','L'),seq(0,1,.1))
  d <- r$cells[r$cells$outcome=='D',]; l <- r$cells[r$cells$outcome=='L',]
  expect_equal(d$gap,.2);expect_equal(d$actual,1L)
  expect_equal(d$top2_recall,1);expect_true(is.na(d$top1_precision))
  expect_equal(l$top2_recall,0);expect_equal(l$top2_misses,1L)
  expect_equal(r$summary$top2,.5);expect_equal(sum(r$cells$expected),2)
  expect_equal(sum(r$cells$actual),2L)
  expect_equal(strategy_handicap_diagnostic(x[6:1,],'handicap',c('W','D','L'),c(0,1))$cells,r$cells)
  y<-x;y$handicap[1]<-1
  expect_error(strategy_handicap_diagnostic(y,'handicap',c('W','D','L'),c(0,1)))
  y<-x;y$probability[1]<-NA_real_
  expect_error(strategy_handicap_diagnostic(y,'handicap',c('W','D','L'),c(0,1)))
  expect_error(strategy_handicap_diagnostic(x[0,],'handicap',c('W','D','L'),c(0,1)))
  expect_error(strategy_handicap_diagnostic(dplyr::bind_rows(x,x),'handicap',c('W','D','L'),c(0,1)))
  y<-x;y$handicap<-.5
  expect_error(strategy_handicap_diagnostic(y,'handicap',c('W','D','L'),c(0,1)))
})
