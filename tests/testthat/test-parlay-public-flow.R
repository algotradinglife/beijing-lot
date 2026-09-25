testthat::test_that('public parlay API runs the normal 6/7/8-leg path', {
  script <- testthat::test_path('..', '..', 'scripts', 'acceptance', 'parlay_api.R')
  source(script, local = TRUE)
})
