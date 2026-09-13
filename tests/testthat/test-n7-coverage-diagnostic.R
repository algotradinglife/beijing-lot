source(file.path(testthat::test_path(),'../../r/n7_coverage_diagnostic.R'))
test_that('cost screening uses model cost and charges every selected losing group', {
  r <- tibble::tibble(issue=c('001','002','003'),sleeve_id='0',cohort='old',
    actual_hit_cost_cny=c(2,8,10),actual_gross_cny=c(13,26,100),
    coverage_15_cost_cny=c(4,6,20),coverage_25_cost_cny=c(8,10,30))
  x <- n7_coverage_grid(r,c(15,25),10)
  expect_equal(nrow(x),4L);expect_equal(x$gross,c(13,0,13,26))
  y <- n7_coverage_summary(x)
  expect_equal(y$summary$roi,c(.3,39/18-1))
  expect_equal(y$summary$roi_without_best,c(-1,13/8-1))
  expect_equal(y$summary$best_issue,c('001','002'))
  expect_equal(nrow(n7_coverage_grid(r,15,1)),0L)
  expect_error(n7_coverage_grid(r,20,10))
  expect_error(n7_coverage_grid(r,NA,10))
  expect_error(n7_coverage_grid(r,15,Inf))
  expect_error(n7_coverage_grid(dplyr::bind_rows(r,r),15,10))
  r$coverage_15_cost_cny[1] <- 3
  expect_error(n7_coverage_grid(r,15,10))
  expect_error(n7_coverage_summary(dplyr::bind_rows(x,x)))
  expect_error(n7_coverage_summary(x[0,]))
  one <- n7_coverage_summary(x[1,])
  expect_true(is.na(one$summary$roi_without_best))
})
