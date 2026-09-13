source(file.path(testthat::test_path(),'../../r/n7_capital_depth.R'))
source(file.path(testthat::test_path(),'../../r/n7_sweet_region.R'))
test_that('coverage thresholds resolve exact crossings and cutoff identity', {
  c <- tibble::tibble(sleeve_id='0',depth=0:2187,coverage=c(0,cumsum(c(.2,.3,.5,rep(0,2184)))) ,
    stake=2*(0:2187),expected_gross=(0:2187)*1.3)
  cuts <- list(a='epoch')
  x <- n7_sweet_points(c,c(.2,.25,.5),cuts,cuts,2)
  expect_equal(x$depth,c(1L,2L,2L));expect_equal(x$coverage,c(.2,.5,.5))
  expect_error(n7_sweet_points(c,.2,cuts,list(b='wrong'),2))
  expect_error(n7_sweet_points(c,NA,cuts,cuts,2))
})
test_that('fixed budget and overlap hold without consulting labels', {
  cuts <- setNames(as.list(rep('epoch',21)),as.character(1:21))
  sets <- list(a=as.character(1:7),b=as.character(2:8),c=as.character(15:21))
  p <- tibble::tibble(sleeve_id=c('a','b','c'),target=.25,depth=c(200L,200L,200L),
    stake=400,coverage=c(.26,.25,.25),expected_gross=260)
  attr(p,'cutoffs') <- cuts
  z <- n7_sweet_allocate(p,sets,cuts,cuts,.25,512,1024,2,2,3)
  expect_setequal(z$ids,c('a','c'));expect_equal(z$stake,800);expect_equal(z$cash,224)
  expect_equal(n7_sweet_allocate(p,sets,cuts,cuts,.25,128,1024,2,2,3)$status,'EMPTY')
  # A label-bearing column must fail, not silently influence or survive selection.
  bad <- p;bad$actual_rank <- c(1,2,3)
  expect_error(n7_sweet_allocate(bad,sets,cuts,cuts,.25,512,1024,2,2,3))
  expect_error(n7_sweet_allocate(p,sets,cuts,list(x=1),.25,512,1024,2,2,3))
  expect_error(n7_sweet_allocate(p,sets,cuts,cuts,.25,512,1000,2,2,3))
  bad <- sets;bad$a[2] <- bad$a[1]
  expect_error(n7_sweet_allocate(p,bad,cuts,cuts,.25,512,1024,2,2,3))
  # Maximum sum coverage may choose overlapping a/b only when constraints allow.
  p$coverage[2] <- .27
  expect_setequal(n7_sweet_allocate(p,sets,cuts,cuts,.25,512,1024,2,2,7)$ids,c('a','b'))
})
