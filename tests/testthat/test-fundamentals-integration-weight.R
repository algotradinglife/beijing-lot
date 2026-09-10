source(file.path('..','..','r','fundamentals_integration_weight.R'))
testthat::test_that('integration summary uses ordered equity and stake ROI', {
  x <- tibble::tibble(partition='TEST',issue=c('3','1','2'),policy='fixed',stake=100,
    gross=c(140,150,0),net=c(40,50,-100),hits=c(1,1,0),groups=1,status='COMPLETE')
  r <- integration_weight_summary(x)
  testthat::expect_equal(r$max_drawdown_cny,100)
  testthat::expect_equal(r$roi,-10/300)
  testthat::expect_error(integration_weight_summary(dplyr::bind_rows(x,x)))
  x$status[1] <- 'PENDING';testthat::expect_error(integration_weight_summary(x))
})
testthat::test_that('no-bet and empty summaries preserve missing ROI and reject missing hits', {
 x <- tibble::tibble(partition='TEST',issue='1',policy='fixed',stake=0,gross=0,net=0,hits=0,groups=0,status='NO_BET')
 testthat::expect_true(is.na(integration_weight_summary(x)$roi))
 testthat::expect_equal(nrow(integration_weight_summary(x[0,])),0L)
 x$hits <- NA_real_;testthat::expect_error(integration_weight_summary(x))
})
