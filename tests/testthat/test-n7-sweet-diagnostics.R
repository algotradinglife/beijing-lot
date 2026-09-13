source(file.path(testthat::test_path(),'../../r/n7_coverage_diagnostic.R'))
source(file.path(testthat::test_path(),'../../r/n7_sweet_diagnostics.R'))
test_that('descriptive blocks and whole-issue tail removals reconcile', {
  x <- tibble::tibble(issue=c('001','002','003','004','005','006'),sleeve_id='0',target=.25,
    cohort='old',stake=10,net=c(50,-10,-10,-10,-10,-10),gross=c(60,0,0,0,0,0),
    hit=c(TRUE,FALSE,FALSE,FALSE,FALSE,FALSE),coverage=.25)
  z <- n7_sweet_diagnostics(x,10,x$issue,2)
  expect_equal(z$grid$roi,0);expect_equal(z$blocks$roi,c(2,-1,-1))
  expect_equal(z$trimmed$roi,c(0,-1,-1,-1))
  expect_error(n7_sweet_diagnostics(x,10,x$issue[-1],2))
  expect_error(n7_sweet_diagnostics(dplyr::bind_rows(x,x),10,x$issue,2))
})
test_that('overlap reports shared fixtures without independence fiction', {
  sets <- list(a=as.character(1:7),b=as.character(2:8),c=as.character(15:21))
  z <- n7_sweet_overlap(c('a','b'),sets)
  expect_equal(z$mean_pair_overlap,6);expect_equal(z$fixtures,8)
  expect_equal(z$max_fixture_group_share,1)
  expect_true(is.na(n7_sweet_overlap('a',sets)$mean_pair_overlap))
  expect_equal(n7_sweet_overlap(character(),sets)$groups,0L)
  expect_error(n7_sweet_overlap('unknown',sets))
})
