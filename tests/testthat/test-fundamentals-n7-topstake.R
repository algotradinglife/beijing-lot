root <- normalizePath('../..')
for(n in c('fundamentals_n7_baseline','fundamentals_n7_twocover','fundamentals_n7_topstake')) source(file.path(root,'r',paste0(n,'.R')))
testthat::test_that('underwater duration includes unrecovered tails but resets at equality', {
  testthat::expect_equal(n7_underwater_periods(numeric()),0)
  testthat::expect_equal(n7_underwater_periods(c(10,-5,2,3,-1,-1,-1)),3)
  testthat::expect_equal(n7_underwater_periods(c(-1,-1,2)),2)
  testthat::expect_equal(n7_underwater_periods(c(1,0,2)),0)
  testthat::expect_error(n7_underwater_periods(c(1,NA_real_)))
})
testthat::test_that('top group report differences and pending cohorts remain typed', {
  d <- tempfile();p <- tempfile()
  for(pair in list(c(d,'FALSE'),c(p,'TRUE'))) {
    status <- withr::with_dir(root,system2('Rscript',c('scripts/prepare_n7_topstake_fixture.R',pair)))
    testthat::expect_equal(status,0L)
  }
  y <- n7_topstake_report(d,root)
  testthat::expect_equal(y$top_per_issue$stake,c(256,256))
  testthat::expect_equal(y$top_per_issue$net,c(144,144))
  testthat::expect_equal(y$top_per_issue$hit,c(1L,1L))
  testthat::expect_true(all(y$top_summary$roi==144/256))
  testthat::expect_equal(nrow(n7_topstake_report(p,root)$summary),0L)
  testthat::expect_equal(nrow(n7_topstake_report(p,root)$top_summary),0L)
})
